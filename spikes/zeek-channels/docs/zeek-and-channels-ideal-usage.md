# SPIKE: Zeek and Django Channels — Ideal Usage in Isolation

**Date:** 2026-05-08
**Status:** In progress — describing each system on its own; integration design comes later.
**Goal of this document:** Capture how Django Channels and Zeek each *want* to be deployed in isolation, before designing any join between them. Integration choices that fight either tool's native shape tend to be the ones that bite later.

---

## Why describe them separately first

Channels and Zeek were built for unrelated jobs. Reaching for both in the same spike is itself the design risk: it's easy to assume the join is a small adapter, when in fact each system has opinions about process model, transport, and lifecycle that constrain what the join can be.

This document is descriptive, not prescriptive. It captures each tool's idiomatic deployment so a follow-up document can evaluate join points against those constraints honestly.

Out of scope for this revision:

- Any concrete Zeek → Channels topology
- Performance benchmarking
- BlueFlow-specific Asset model mapping
- Operational concerns (monitoring, packaging, deployment automation) beyond what's needed to describe the runtime

---

## 1. Django Channels — Ideal Usage

### 1.1 What it is

Django Channels extends Django from a synchronous request/response framework into one that also speaks long-lived, asynchronous protocols — primarily WebSockets, but also generic background workers and protocol consumers. It does this by replacing the WSGI entrypoint with an ASGI application and introducing a *channel layer* abstraction that lets multiple processes coordinate by name.

It is not a queue, not a message broker, and not a replacement for Celery. It is a routing-and-consumer framework for connection-oriented protocols on top of Django.

### 1.2 The runtime shape Channels expects

```
┌──────────────┐    ASGI     ┌────────────────┐
│ ASGI server  │ ──────────► │ ProtocolRouter │ ──► HTTP → Django views
│ (Daphne /    │             │ (per-protocol) │ ──► WebSocket → Consumer
│  Uvicorn)    │             │                │ ──► Channels worker
└──────────────┘             └────────────────┘
                                      │
                                      ▼
                           ┌──────────────────────┐
                           │    Channel Layer     │
                           │  (Redis / in-memory) │
                           └──────────────────────┘
                                      ▲
                           Other ASGI processes connect
                           to the same layer to fan out.
```

What this means in practice:

- **One ASGI application object.** `project/asgi.py` becomes the deployment entrypoint instead of `wsgi.py`. Daphne and Uvicorn are the two common ASGI servers; both run consumers as long-lived async tasks.
- **Consumers, not views.** Each protocol (`websocket`, `channel`, custom) routes to a `Consumer` class that handles its own lifecycle: `connect`, `receive`, `disconnect`. Consumers can be sync or async; async is preferred for I/O-heavy paths.
- **Process model.** Channels does not fork worker processes for you. You run N ASGI server processes and let the channel layer broker between them. Sync Django HTTP traffic can still be served by the same ASGI app or kept on a separate WSGI deployment — both are valid.

### 1.3 The channel layer

The channel layer is a named-message broker shared across ASGI processes. Channels ships two implementations:

| Layer | Use for | Avoid for |
|---|---|---|
| `channels.layers.InMemoryChannelLayer` | Tests, single-process dev | Anything multi-process — messages do not cross processes |
| `channels_redis.core.RedisChannelLayer` | All production deployments | Single-tenant cases where Redis is overhead |

Channels' production sweet spot is Redis. Messages have at-most-once delivery semantics with bounded queue depth — if a consumer is slow, the layer drops or rejects, it does not buffer indefinitely. This is intentional: the layer is for coordinating live connections, not for durable work.

If durability matters (the message must be processed even if no consumer is listening *right now*), Channels is the wrong layer — that's Celery's job.

### 1.4 Consumer lifecycle in the WebSocket case

```
 client                   consumer                  channel layer
   │                         │                            │
   │── WS handshake ────────►│                            │
   │                         │── group_add(name) ────────►│
   │                         │                            │
   │── frame ───────────────►│                            │
   │                         │                            │
   │                         │◄── group_send (from elsewhere) ─│
   │◄── frame ───────────────│                            │
   │                         │                            │
   │── close ───────────────►│── group_discard ──────────►│
```

Two ideas matter here:

- **Groups** are the unit of fan-out. A consumer subscribes itself to a named group on connect, the rest of the system sends to that group, and Channels delivers to every consumer in it. Groups are flat strings; there is no hierarchy.
- **Senders are anywhere.** Anything that can construct an `AsyncToSync(channel_layer.group_send)` call can broadcast — a Django view, a Celery task, a management command, an external process with the right Redis credentials. Channels does not require the sender be inside the ASGI app.

That last property is what makes Channels relevant to a Zeek integration discussion at all.

### 1.5 Where Channels shines

- Pushing live updates to browser clients (dashboards, alerting UIs, log tails).
- Coordinating long-lived per-connection state (chat-style protocols, collaboration features).
- Cases where Django models are the source of truth and frontends need to react to changes.

### 1.6 Where Channels is the wrong tool

- Durable work queues — Celery exists for that, with retries, schedules, and persistence.
- High-volume telemetry ingestion where every message must be processed exactly once. The channel layer drops under backpressure.
- Internal RPC between services. gRPC, REST, or a real broker (Kafka, NATS) are better matches.
- Anything that needs persistence across restarts — Channels' layer is ephemeral.

### 1.7 Key constraints to remember

1. Channels needs an ASGI deployment. WSGI-only deployments cannot host consumers.
2. The channel layer is best-effort, not durable.
3. Consumers run as async tasks inside the ASGI process; CPU-bound work blocks the event loop and must be offloaded (`sync_to_async`, Celery, or a thread pool).
4. Redis is effectively required in production. BlueFlow already runs Redis for Celery, so this is a reuse rather than a new dependency.

---

## 2. Zeek — Ideal Usage

### 2.1 What it is

Zeek (formerly Bro) is a network security monitor: a passive traffic analyzer that turns observed packets into structured, protocol-aware events. It is not a signature-matching IDS — its strength is protocol semantics. Zeek understands HTTP, DNS, TLS, SSH, SMB, SIP, modbus, and dozens more well enough to emit field-level records (`http.log`, `dns.log`, `ssl.log`, etc.) that describe *what happened* at the application layer, not just *what bytes moved*.

It carries its own scripting language (also called Zeek). Detection logic, event correlation, and custom outputs are expressed as Zeek scripts loaded by the runtime.

### 2.2 The runtime shape Zeek expects

```
                  ┌───────────┐
                  │  Manager  │  ← cluster coordination, alerts
                  └─────┬─────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
   ┌────▼────┐     ┌────▼────┐     ┌────▼────┐
   │ Logger  │     │  Proxy  │     │ Workers │  ← sees raw traffic
   │ writes  │     │ shared  │     │ N procs │
   │ *.log   │     │  state  │     │ pinned  │
   └─────────┘     └─────────┘     └─────────┘
                                        ▲
                                  ┌─────┴─────┐
                                  │ SPAN/TAP  │
                                  │ AF_PACKET │
                                  └───────────┘
```

The cluster splits responsibilities by role:

- **Workers** receive raw packets and run protocol analyzers and scripts. Sized to packet rate; usually one worker per CPU core, pinned, with a load balancer (`PF_RING`, `AF_PACKET fanout`) distributing flows.
- **Logger** is the single sink that serializes log events to disk. Centralizing log writes keeps file output coherent across workers.
- **Manager** coordinates cluster lifecycle, ingests notices/alerts, and is where most "global state" scripts execute.
- **Proxy** holds shared script state (e.g., SumStats results) so workers can collaborate without N² communication.

A **standalone** Zeek is the same software with a single process playing all roles. It is the right shape for low-throughput sensors (a small hospital VLAN at hundreds of Mbps) and for development. Cluster mode becomes worthwhile around the point where one core can no longer keep up with the SPAN feed.

### 2.3 What Zeek wants from its environment

- **A copy of traffic, not the traffic itself.** Zeek is strictly passive. It needs a SPAN/mirror port, a network tap, or a tap-mode NIC capture. Inline placement is not its job.
- **A dedicated capture interface.** The capture NIC is best left without an IP address and with offloads disabled (`ethtool -K iface gro off lro off`). Hardware offloads merge or alter packets in ways that confuse protocol analyzers.
- **Tuning for packet rate.** Default kernel ring buffers and capture flags are usually wrong. Production deployments use `AF_PACKET` with multiple fanout sockets, or PF_RING / Myricom drivers at higher rates.
- **Filesystem for logs.** Even when downstream consumers exist, the default logger expects a writable directory. Log rotation is handled by Zeek itself (`Log::default_rotation_interval`).

### 2.4 Output mechanisms — how Zeek emits events

Zeek's idea of "output" is plural. Choose the mechanism that fits the consumer; do not assume there is one.

| Mechanism | Form | Idiomatic use | Limits |
|---|---|---|---|
| **Log files** (default) | TSV or JSON-lines, one file per stream | Durable post-hoc analysis, SIEM ingestion via filebeat / Vector / Fluent Bit | File-based; consumers must tail and handle rotation |
| **Kafka writer plugin** | Pub/sub to Kafka topics, one per stream | High-throughput pipelines feeding stream processors | Adds Kafka dependency; plugin (Apache Metron / community) must be installed |
| **Broker** | Pub/sub events over Zeek's native IPC | Live programmatic consumption from another Zeek node, or from Python/C++ via Broker bindings | Custom protocol; requires Broker library on the consumer side |
| **`Reporter::info` / `print`** | stdout / stderr | Debug only | Not a production output |
| **Notice framework** | Specialized event stream for alerts | Security alerts that need email / paging / external action | Carries policy semantics — not a general-purpose channel |

Two of these are worth highlighting because they shape any integration:

- **Log files are the lingua franca.** Every Zeek deployment produces them, every observability stack knows how to read them. JSON output (`@load policy/tuning/json-logs`) makes them trivially parseable. The cost is the file-tailing pattern: a downstream needs to watch for rotation and resume from offsets.
- **Broker is the only first-class live output.** It is Zeek's own IPC, designed for cluster nodes to talk to each other but explicitly exposed for external consumers via Python (`broker` PyPI package) and C++ bindings. Broker carries typed Zeek events, not pre-serialized log records — consumers receive them at a higher semantic level.

### 2.5 Where Zeek shines

- Passive discovery of devices and services from observed traffic — exactly the BlueFlow asset-discovery use case.
- Protocol decoding at the semantic level (a DNS query, a TLS handshake with parsed SNI/JA3, an HTTP transaction with method/URI/status), not packet-level forensics.
- Long-running stateful detection (rare beaconing, scan detection, certificate anomalies) expressed as scripts.
- Read-only deployments where in-line failure is unacceptable — Zeek failing closed never breaks production traffic, because it is not in the path.

### 2.6 Where Zeek is the wrong tool

- **Inline enforcement.** Zeek does not block, drop, or rate-limit. A deployment that needs to act on traffic in real time wants a firewall or NGFW, not Zeek.
- **Signature matching at line rate.** Suricata is the better fit for "fire on this regex / Snort rule." Zeek can be coerced into doing this but it is not what it optimizes for.
- **Deep inspection of encrypted payloads.** Zeek can fingerprint TLS metadata (JA3/JA4), see SNI, and follow handshake state — but the encrypted application data is opaque. For HL7-over-TLS or HTTPS payload visibility, decryption (TLS interception, key sharing) has to happen elsewhere.
- **Microsecond decision loops.** Zeek's analysis is event-driven and runs after a flow's relevant packets have been seen. Sub-millisecond response is not its model.

### 2.7 Key constraints to remember

1. Zeek is its own process tree, not a library. Integrations talk to it across a process boundary — file, socket, or Broker.
2. Output is event-stream-shaped. Anything that pulls from Zeek should be designed for line-oriented or pub/sub consumption, not request/response.
3. Workers are the throughput bottleneck. Capacity planning is "how many cores can keep up with the SPAN feed," not "how many requests per second."
4. The deployment topology (standalone vs. cluster) should track traffic volume. A small hospital sensor is almost always standalone; a hospital system aggregator may need a cluster.
5. Zeek scripts are first-class. Behavior changes (which logs are emitted, what fields they carry, when notices fire) live in Zeek script, not in the consumer.

---

## 3. What this document does not answer

- How Zeek output should reach Channels — that is the next document.
- Whether Channels is the right layer for Zeek-driven events at all (a Celery + Redis Streams shape may fit better; that comparison belongs in the integration doc).
- BlueFlow Asset / Topology model mapping for Zeek-derived data.

---

## References

- Django Channels documentation — https://channels.readthedocs.io/
- ASGI specification — https://asgi.readthedocs.io/
- channels_redis — https://github.com/django/channels_redis
- Zeek documentation — https://docs.zeek.org/ (referenced in §2)
