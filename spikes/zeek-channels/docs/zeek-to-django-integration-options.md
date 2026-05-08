# SPIKE: Zeek → Django Integration Options

**Date:** 2026-05-08
**Status:** In progress — analyzing options, not yet recommending one.
**Companion doc:** [zeek-and-channels-ideal-usage.md](zeek-and-channels-ideal-usage.md) — describes how each system wants to be used in isolation. Read that first; this doc assumes its terminology.

---

## Goal

Compare concrete ways for Zeek-derived events to reach Django (and ultimately the BlueFlow `Asset` model) along three dimensions:

- **Effort** — new dependencies, code surface, ops surface, testing burden.
- **Compatibility** — how well the option fits BlueFlow's existing stack (PostgreSQL, Redis, Celery, DRF, ASGI-not-yet-deployed) and Zeek's native output shapes.
- **Tradeoffs** — durability, latency, failure modes, observability.

Four options analyzed:

- **A.** Zeek → Django Channels → Django (live, ephemeral)
- **B.** Zeek → Celery → Django (durable async work queue)
- **C.** Zeek → log files → tail sidecar → Django ORM (no broker)
- **D.** Zeek → Redis Streams → Django consumer → Django ORM (durable stream, no Celery)

A side-by-side comparison table follows the per-option sections, and a closing list flags options not analyzed this pass.

---

## Common assumptions

These hold for every option below; flagging once to keep each section focused.

- Zeek emits JSON-line logs (`@load policy/tuning/json-logs`). Every option benefits from JSON output and most assume it.
- The Asset upsert path already exists (`AssetViewSet.upsert`, `Asset.objects.update_or_create(...)`) and tolerates idempotent retries on `mac_address`. Any option's "write to Django" step is a thin wrapper over that.
- Redis is already deployed for Celery. Adding Channels' Redis layer or Redis Streams is a reuse, not a new dependency.
- **Redis Streams is treated as a first-class buffer primitive in this analysis.** It is the append-only, durable, consumer-group-aware data structure available in Redis ≥ 5.0 — distinct from Redis pub/sub. Where an option benefits from Streams (or is changed by it being available), this is called out per-section.
- **`zeek-redis` (the plugin) was investigated and ruled out for Stage 1.** No current Zeek package writes to Redis Streams — both `sedarasecurity/zeek-redis` and `mbispham/zeekjs-redis` use Redis Lists; the legacy Bro::Redis is documented as not production-ready by its own author. See [bridge-investigation-findings.md](bridge-investigation-findings.md). The decision doc accordingly commits to **Vector** as the Stage 1 bridge. The bridge layer is swappable behind the stream — if Streams support lands in the Zeek-Redis ecosystem later, Vector can be replaced without changing the consumer.
- The target deployment is the small-hospital sensor described in `BlueFlow product positioning`. Throughput is hundreds of Mbps, not data-center scale. This rules out Kafka-grade infrastructure as the default but does not rule it out forever.

---

## Option A — Zeek → Django Channels → Django

### A.1 Topology

```
┌─────────┐    ┌──────────────┐    ┌───────────────┐    ┌─────────────┐
│  Zeek   │───►│ bridge proc  │───►│ Redis channel │───►│ ASGI worker │
│ workers │    │ (broker sub  │    │     layer     │    │ (Channels   │
│         │    │  or log tail)│    │  best-effort  │    │  consumer)  │
└─────────┘    └──────────────┘    └───────────────┘    └──────┬──────┘
                                                               │
                                                          ORM upsert
                                                               ▼
                                                        ┌─────────────┐
                                                        │  PostgreSQL │
                                                        └─────────────┘
```

### A.2 How data flows

1. A bridge process subscribes to Zeek (via Broker bindings) or tails its JSON logs.
2. The bridge calls `channel_layer.group_send("zeek-events", {"type": "zeek.event", ...})`.
3. The ASGI deployment runs a Channels consumer subscribed to that group; its `zeek_event` handler runs `sync_to_async(Asset.objects.update_or_create)(...)`.

The framing trick to notice: Channels' channel layer is being asked to do *ingestion*, not its native job of *fan-out*. The path works mechanically but uses the layer against its design intent.

### A.3 Effort

| Dimension | Cost |
|---|---|
| New dependencies | `channels`, `channels_redis`, an ASGI server (Daphne or Uvicorn) |
| Code surface | ASGI app (`project/asgi.py`), one `AsyncJsonWebsocketConsumer` or generic `AsyncConsumer`, routing config, the bridge process, and Django settings additions |
| Ops surface | New ASGI process to run alongside (or instead of) WSGI; supervised (systemd / Docker / k8s); the bridge process; Channels-specific health checks |
| Testing burden | Channels test client + `pytest-asyncio`; harness needs to fake the Redis layer with `InMemoryChannelLayer` for unit tests |

### A.4 Compatibility with current stack

- **Reuses Redis** — already deployed for Celery, runs `channels_redis` alongside without contention if separate logical DB.
- **Forces ASGI deployment** — BlueFlow currently runs WSGI. Adding Channels means either dual deployment (WSGI for HTTP, ASGI for WebSockets) or migrating HTTP to ASGI. Both are non-trivial.
- **Doesn't fit Zeek's output shape natively.** Zeek does not speak the channel-layer protocol; the bridge process is the unavoidable adapter.
- **No existing Channels code in the repo.** This option is greenfield.

### A.5 Tradeoffs

**Pros**

- Lowest end-to-end latency once events are on the layer (sub-second to consumer).
- The same Channels infrastructure can fan out to browser dashboards, which is Channels' actual native job — so if live dashboards are a near-term goal, the investment pays double.
- Async-native consumer; no thread-per-request overhead.

**Cons**

- **Channel layer is best-effort.** A slow consumer or a Redis hiccup drops Zeek events. There is no retry, no DLQ, no offset commit. Lost events are lost silently.
- **No durability across restarts.** Restarting the ASGI deployment means in-flight messages disappear.
- **The bridge is still required and unspecified.** Whatever puts events onto the channel layer is real work; the option name hides it.
- **ASGI deployment is a meaningful operational change** for a project that does not currently need it.

### A.6 Failure modes

| What fails | What happens | Data loss? |
|---|---|---|
| ASGI consumer slow / dead | Channel layer hits queue depth limit → drops messages | **Yes — silent** |
| Redis restart | Layer state cleared; in-flight messages lost | **Yes** |
| Bridge process crash | No events reach Channels until it restarts | Yes, until restart |
| PostgreSQL slow | `sync_to_async` ORM calls block the event loop unless offloaded carefully | Possible cascading drops |

### A.7 Note on Redis Streams as upstream buffer

The best-effort durability concern in A.5 / A.6 is specifically about *the channel layer*, not about Channels itself. If a Redis Streams buffer sits *in front of* the Channels consumer (Zeek → Streams → Channels consumer reading via `XREADGROUP`), the durability problem moves: Streams retains, the consumer reads at its own pace, and only post-commit fan-out events flow through the channel layer.

That topology is essentially **Option D plus Channels for browser fan-out**, not Option A as defined here. It is a sensible target shape if both durable ingestion *and* live browser push are goals, but it should be reasoned about as an additive layering on D rather than as a defense of A's standalone design. The cost stays the same — ASGI deployment plus a stream consumer plus the bridge — but the durability story is now sound.

---

## Option B — Zeek → Celery → Django

### B.1 Topology

```
┌─────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Zeek   │───►│ bridge proc  │───►│ Redis broker │───►│ Celery worker│
│ workers │    │ enqueues     │    │ (durable     │    │ (existing    │
│         │    │ task.delay() │    │  queue)      │    │  process)    │
└─────────┘    └──────────────┘    └──────────────┘    └──────┬───────┘
                                                              │
                                                         ORM upsert
                                                              ▼
                                                       ┌──────────────┐
                                                       │  PostgreSQL  │
                                                       └──────────────┘
```

### B.2 The arrow that hides a real choice

The "Zeek → Celery" arrow elides a question: *what produces Celery tasks?* Celery does not subscribe to Zeek; something has to call `task.delay(payload)`. Three concrete bridge variants:

| Variant | Bridge runs | Notes |
|---|---|---|
| **B-tail** | A Python sidecar tailing Zeek JSON logs, calling `task.delay()` per line | Simplest; depends on file rotation handling |
| **B-broker** | A Python process using Zeek Broker bindings, subscribing to events, calling `task.delay()` | Lowest latency; requires Broker library and a Zeek script that publishes the right events |
| **B-stream** | A Python consumer reading Redis Streams, calling `task.delay()` per entry | If you have Streams, the Celery hop is usually redundant — see **Option D** for the variant that drops it |

The rest of this analysis assumes **B-tail** as the dominant variant — it is the lowest-effort, most-similar-to-existing-stack option. B-broker is called out where it changes the picture. B-stream is folded into Option D below, since putting Celery downstream of Streams duplicates Streams' own buffering and offset semantics; Celery's value over a raw Streams consumer (retry framework, scheduling, chains) does not apply to the asset-upsert workload.

### B.3 How data flows (B-tail)

1. Zeek writes JSON-line logs to disk; logger node rotates files on schedule.
2. A sidecar Python process (`zeek_celery_bridge.py`) tails `conn.log`, `dns.log`, etc., tracking byte offsets in a small state file for restart-safety.
3. Per relevant log line, the bridge calls `ingest_zeek_event.delay(stream, payload)`.
4. Celery picks up the task in an existing worker, deserializes, calls into the Asset upsert path.
5. Failures are retried per Celery's standard retry policy. Permanently-failing tasks land in a dead-letter handler.

### B.4 Effort

| Dimension | Cost |
|---|---|
| New dependencies | None at the broker level (Redis + Celery already deployed). The bridge needs a file-tail library (`watchfiles` or stdlib `os`) for B-tail; for B-broker, the `broker` PyPI package |
| Code surface | One Celery task module, one bridge process, a small offset-state file, configuration for which Zeek streams to consume |
| Ops surface | One additional supervised process (the bridge); existing Celery worker handles the rest |
| Testing burden | Standard Celery test patterns (`CELERY_TASK_ALWAYS_EAGER=True` is already configured for tests per `CLAUDE.md`); bridge can be unit-tested with fixture log files |

### B.5 Compatibility with current stack

- **Reuses Celery and Redis directly.** Tasks run in the existing worker pool. No new runtime is introduced.
- **Reuses existing test idioms.** `CELERY_TASK_ALWAYS_EAGER=True` and `pytest` fixtures cover the worker side. The bridge tests are file-fixture-based, similar to the HL7 spike's pcap-fixture pattern.
- **No ASGI requirement.** WSGI deployment continues unchanged.
- **Works with Zeek's default output (logs).** B-tail is the path of least resistance against Zeek's idiomatic shape.

### B.6 Tradeoffs

**Pros**

- **Durable.** Redis-backed Celery queues survive consumer restarts. Tasks persist until acknowledged.
- **Built-in retry, DLQ, scheduling.** Celery already provides what Channels does not — retries with backoff, dead-letter handling, periodic tasks.
- **Familiar runtime.** The team already operates Celery; this option does not introduce a new failure surface to learn.
- **Decouples Zeek throughput from Django response time.** Zeek can produce faster than Django consumes; the queue absorbs.

**Cons**

- **Higher per-event latency than Channels.** A Celery task hop adds ~tens of milliseconds before the ORM write — fine for asset upsert, not for sub-second live dashboards.
- **Bridge process is required and is custom code** (same as Option A — neither option escapes the bridge).
- **B-tail's file-tailing is its own micro-engineering problem.** Rotation, gzip-on-rotate, partial-line reads, and offset persistence all have to be handled correctly. There are libraries; there is also enough surface area to get wrong.
- **Per-event task overhead at high volumes.** At thousands of events/sec the per-task Celery overhead adds up. A batched task (`ingest_zeek_batch`) is the usual mitigation but adds complexity.

### B.7 Failure modes

| What fails | What happens | Data loss? |
|---|---|---|
| Celery worker dead | Tasks queue up in Redis until a worker returns | No (within Redis memory limit) |
| Bridge process crashes mid-file | Restart resumes from persisted offset | No, if offset is fsync'd carefully |
| Bridge crashes between read and `task.delay()` | The line that was read but not enqueued is lost | **Possible** — depends on offset-commit ordering |
| Redis OOM / restart | Configured persistence (AOF/RDB) determines recovery; default Celery setup loses in-flight unacked tasks | Depends on Redis durability config |
| Zeek log rotation | Bridge must follow rotation; missing this drops events between rotation and detection | Possible, mitigated by good rotation handling |

---

## Option C — Zeek → log files → tail sidecar → Django ORM

The "no broker" baseline. Same file-tailing mechanism as B-tail, but the sidecar talks to Django directly rather than going through Celery.

### C.1 Topology

```
┌─────────┐    ┌──────────────────────────────┐    ┌──────────────┐
│  Zeek   │───►│ Python sidecar               │───►│  PostgreSQL  │
│ workers │    │  - tails *.log (JSON)        │    │              │
│         │    │  - loaded with Django        │    └──────────────┘
│         │    │  - calls Asset.objects.* )   │
│         │    │  - persists offsets          │
└─────────┘    └──────────────────────────────┘
```

### C.2 How data flows

1. Zeek writes JSON-line logs.
2. The sidecar process is a Django management command (or a standalone script with `django.setup()`) that tails the logs in a polling loop.
3. Per line, it calls `Asset.objects.update_or_create(...)` directly. Failures retry in-process with backoff; permanent failures land in a local error log file or a `dead_letter` table.
4. Byte offsets are persisted to a small state file (or a `BridgeCursor` model) on every batch commit, so restarts resume cleanly.

### C.3 Effort

| Dimension | Cost |
|---|---|
| New dependencies | A file-watching library (`watchfiles` is the modern choice) or stdlib polling. Nothing else |
| Code surface | One management command (`python manage.py zeek_ingest`) or one script, plus a small cursor model or state file. The Asset upsert call is already implemented |
| Ops surface | One additional supervised process. No new infrastructure |
| Testing burden | Lowest of the three — pytest with fixture log files, no async machinery, no broker setup. Reuses standard `pytest-django` fixtures |

### C.4 Compatibility with current stack

- **Adds nothing new.** No Channels, no broker beyond what's there. The sidecar is "Django-as-library."
- **Matches Zeek's default output shape exactly.** No bridge protocol negotiation; just files.
- **Conflicts with Django's normal request/response model the least** — there is no request, just a long-running consumer of files.
- **Mirrors the HL7 spike's existing pattern.** That spike uses a similar file-driven pipeline (`extract.py | emit.py`), so this option fits an established repo idiom.

### C.5 Tradeoffs

**Pros**

- **Simplest possible path.** Fewer moving parts than either A or B. One process, one input shape, one output shape.
- **Easiest to reason about and debug.** A failure is either "sidecar isn't running" or "ORM call failed" — no intermediate broker state to inspect.
- **No queue depth, no channel layer drops, no broker misconfiguration.** What the sidecar reads, it writes (or surfaces an error you can see).
- **Natural fit for a small-hospital deployment** where adding services has a real cost.

**Cons**

- **No async buffering between Zeek and Django.** If PostgreSQL is slow, the sidecar slows down with it; if the sidecar can't keep up, log files grow on disk until rotation.
- **No retry across process restarts unless explicitly engineered.** Restart resumes from persisted offset, but a failed ORM call needs an in-process retry strategy or a local DLQ.
- **Single-process bottleneck.** If one sensor's traffic exceeds what one Python process can handle, scaling means sharding by Zeek log stream — workable but not free.
- **Not extensible to live dashboards out of the box.** No fan-out path. If browser push later becomes a goal, you would add Channels on top of this — at which point this option converges with a hybrid.
- **File durability is the simpler primitive, but not strictly the better one.** Redis Streams (Option D) is the alternative durability layer with consumer groups, retention policy, and replay built in. Choosing C over D is choosing "disk is the boring durability primitive everyone knows" over "Streams gives me operational primitives I'd otherwise build by hand." For a small-hospital sensor with one consumer, C's simplicity wins; for a multi-consumer or multi-tenant deployment, D's primitives become valuable.

### C.6 Failure modes

| What fails | What happens | Data loss? |
|---|---|---|
| Sidecar process dead | Logs accumulate on disk until rotation deletes them | **Yes if rotation outpaces restart**, otherwise resumed |
| ORM call fails (DB hiccup) | In-process retry with backoff; persistent failure surfaced via logging or DLQ table | No, if retry logic is correct |
| Sidecar crashes mid-batch | Resume from last persisted offset; events in the unflushed batch may be replayed | Duplicates possible (idempotent upsert handles this) |
| Disk fills up | Zeek logger fails or rotates aggressively | Yes — same risk as any file-based pipeline |
| Log rotation | Library handles rotation correctly (`watchfiles` does); naïve polling can miss the file swap | Possible without correct handling |

---

## Option D — Zeek → Redis Streams → Django consumer → Django ORM

The "durable buffer without a task framework" baseline. Uses Redis Streams as the persistence layer between Zeek and Django, and runs a consumer that calls the ORM directly — no Celery, no Channels.

### D.1 Topology

```
┌─────────┐    ┌──────────────┐    ┌─────────────────┐    ┌──────────────┐
│  Zeek   │───►│ bridge proc  │───►│  Redis Streams  │───►│ Django mgmt  │
│ workers │    │  (broker sub │    │  - durable      │    │ command      │
│         │    │   or tailer) │    │  - retention    │    │  XREADGROUP  │
│         │    │  XADD per    │    │  - consumer     │    │  XACK        │
│         │    │   event      │    │    groups       │    │  ORM upsert  │
└─────────┘    └──────────────┘    └─────────────────┘    └──────┬───────┘
                                                                  │
                                                             ORM upsert
                                                                  ▼
                                                           ┌──────────────┐
                                                           │  PostgreSQL  │
                                                           └──────────────┘
```

### D.2 How data flows

1. A bridge mechanism writes each relevant Zeek event to a Redis stream via `XADD zeek:events * stream <name> payload <json>`. The bridge is **Vector** as committed by the decision doc (§6.0 [investigation findings](bridge-investigation-findings.md) ruled out current zeek-redis packages; a Broker subscriber remains a real Stage 3 alternative). Custom Python tailing is excluded from the recommended set per survey §4.2.
2. The stream is configured with a retention policy — by approximate length (`MAXLEN ~ 10000000`) or by ID-based trimming on a schedule. Retention is the operational SLA for "how long can the consumer be down before data is lost?"
3. A Django management command (`python manage.py zeek_stream_consume`) runs an `XREADGROUP` loop in a consumer group, blocking on new entries.
4. Per entry, the consumer parses the payload, calls `Asset.objects.update_or_create(...)`, then `XACK`s.
5. Failures are retried in-process. Permanently-failing entries are routed to a dead-letter stream (`zeek:dead`) or a `dead_letter` table; offset is acked so the main stream advances.

### D.3 Effort

| Dimension | Cost |
|---|---|
| New dependencies | `redis` Python client (already a Celery transitive dep — likely already installed). No new infrastructure |
| Code surface | One bridge process, one management command, a small parser per Zeek log type, dead-letter handling. Asset upsert call is already implemented |
| Ops surface | Bridge + consumer (can be co-located in one process). Stream retention policy needs to be configured and monitored. No new daemons beyond what the team already operates |
| Testing burden | `fakeredis[lua]` supports Streams natively; tests can run a fake stream end-to-end without a real Redis. Higher than C, lower than A |

### D.4 Compatibility with current stack

- **Reuses Redis directly.** Streams live in the same Redis instance Celery uses; a separate logical DB (`db=1`) keeps namespaces clean.
- **No ASGI requirement.** WSGI deployment continues unchanged.
- **No new framework concepts beyond Streams.** The team already operates Redis; Streams is a feature within that, not a new service.
- **Matches Zeek's idiomatic output (events).** The bridge transforms log lines or Broker messages to `XADD` calls — a thin shim, not a protocol translation.
- **Cleanly extensible to fan-out.** The same stream can be read by a Channels consumer later (or in parallel) for browser push, without changing the ingestion path. That makes "Option D now, Channels added later" a real migration, not a rewrite.

### D.5 Tradeoffs

**Pros**

- **Durable, replayable buffer.** Streams retain entries until trimmed; consumer groups track offsets per consumer; failed entries can be re-read via `XPENDING` / `XCLAIM`.
- **At-least-once delivery with explicit acks.** No silent drops. The consumer decides when to ack, and unacked entries can be redelivered to another consumer in the group.
- **Operational primitives included.** `XINFO STREAM`, `XPENDING`, `XLEN`, and `XLEN`-based retention give visibility into queue depth, lag, and pending entries without custom monitoring code.
- **Scales horizontally on the consumer side.** Multiple consumers in a group share work; entries are distributed via `XREADGROUP`'s built-in load balancing.
- **No Celery overhead.** One fewer hop than B; one fewer abstraction to learn for this path.
- **Same simplicity profile as C** for a single-consumer deployment, with strictly better durability properties (and a small operational learning curve as the cost).

**Cons**

- **Streams is a primitive the team may not have operated before.** Tooling, debugging idioms, and failure-mode intuition are different from Celery or file-tailing. Real but bounded learning cost.
- **Redis becomes a hard dependency for the ingest path.** A Redis outage stops both Celery and ingestion. C avoids this; B already shares the dependency.
- **Stream retention is a real configuration choice.** Set too short and a slow consumer loses data; set too long and Redis memory grows. There is no "just works" default.
- **No built-in retry/scheduling framework.** If the asset-upsert workload ever needs Celery's task semantics (retries with backoff schedules, periodic tasks, chains), they'd have to be reintroduced — or that work moves into Celery while Streams stays as the buffer (which is B-stream, but specifically *only* for those tasks).
- **Bridge is still required as a process.** The Stage 1 bridge is Vector ([investigation findings](bridge-investigation-findings.md)); no current zeek-redis plugin would have eliminated it, and the survey explicitly argues against custom code in this role. Same operational caveat as A and B — the "Zeek → Streams" arrow needs a process to draw it.

### D.6 Failure modes

| What fails | What happens | Data loss? |
|---|---|---|
| Consumer dead | Stream retains entries up to retention bound; consumer resumes from last unacked offset on restart | No, within retention window |
| Bridge crashes mid-event | Depending on bridge implementation, the in-flight event may or may not be `XADD`ed | Possible — single-event window |
| Redis OOM / restart | Stream durability depends on Redis persistence config (AOF preferred for at-least-once); without AOF, recent entries may be lost | Depends on Redis durability config |
| Slow PostgreSQL | Consumer slows; pending entries accumulate; `XPENDING` grows; eventually retention trims oldest | Yes, only if slowness exceeds retention window |
| Consumer parses but errors before `XACK` | Entry is redelivered (to same or another consumer in the group) on next `XREADGROUP` | No — duplicate possible, idempotent upsert handles |
| Stream retention misconfigured (too short) | Entries trimmed before consumer reads them | **Yes — silent unless monitored** |
| Bridge mechanism fails (Broker disconnect, log rotation missed) | No new entries reach the stream | Yes, until bridge resumes |

---

## Side-by-side comparison

Heuristic ratings: ✅ strong, 🟡 acceptable, 🔴 weak. These are *relative* across the three options, not absolute claims.

| Dimension | A: Channels | B: Celery (B-tail) | C: Log-tail sidecar | D: Streams consumer |
|---|:---:|:---:|:---:|:---:|
| **Effort to first working pipeline** | 🔴 high (ASGI + bridge + consumer + tests) | 🟡 moderate (bridge + Celery task) | ✅ low (one sidecar) | 🟡 moderate (bridge + consumer + retention config) |
| **New dependencies** | 🔴 `channels`, `channels_redis`, ASGI server | ✅ none beyond existing | ✅ none beyond `watchfiles` (optional) | ✅ none beyond existing (`redis-py` already transitive) |
| **New runtime processes** | 🔴 ASGI deployment + bridge | 🟡 bridge | 🟡 sidecar | 🟡 bridge + consumer (can co-locate) |
| **Fit with Zeek's native output** | 🟡 (bridge required) | ✅ (logs in, tasks out) | ✅ (logs in, ORM out) | 🟡 (bridge converts to XADD) |
| **Durability** | 🔴 best-effort, drops on backpressure | ✅ Redis-backed, retries, DLQ | 🟡 file-durable on Zeek side, in-process on ingest side | ✅ Streams retention + consumer groups + at-least-once |
| **End-to-end latency** | ✅ sub-second | 🟡 tens of ms + queue time | 🟡 polling interval (sub-second with `watchfiles`) | ✅ sub-second (XREAD BLOCK) |
| **Throughput ceiling** | 🟡 limited by channel layer queue depth | ✅ scales by adding workers | 🟡 single-process per stream | ✅ scales by adding consumers in a group |
| **Existing test idioms cover it** | 🔴 needs new async test infra | ✅ Celery patterns already used in repo | ✅ pytest with fixture files | 🟡 `fakeredis[lua]` supports Streams; new pattern for the repo |
| **Operational learning curve for the team** | 🔴 new (Channels semantics, ASGI) | ✅ familiar (Celery) | ✅ familiar (Django mgmt commands) | 🟡 Streams is a new primitive; debugging idioms differ |
| **Extensibility to browser fan-out later** | ✅ native job — already there | 🟡 would need Channels added | 🟡 same | ✅ same stream can be tailed by a Channels consumer in parallel |
| **Failure visibility** | 🔴 silent drops | ✅ Celery monitoring tools | ✅ logs, mgmt-command status | ✅ `XINFO`, `XPENDING`, `XLEN` |

### Reading the table

A few patterns:

1. **C wins on "first working pipeline" but loses long-term flexibility.** Lowest cost to ship, no new infrastructure, fits Zeek's shape — but it has no buffering, no fan-out, and rotation handling is a real micro-engineering concern.
2. **D is the most "boring" durable answer.** It uses parts BlueFlow already operates (Redis), gives at-least-once semantics with native operational primitives, and avoids both Channels' best-effort layer and Celery's task-framework overhead for a workload that is not actually task-shaped.
3. **B is only attractive if Celery's framework features matter.** Once Streams is treated as a first-class buffer (Option D), the case for putting Celery in front of asset-upsert specifically becomes weak — Streams already provides the durability Celery would have brought.
4. **A's strengths are real but specific.** Channels is the right tool when fan-out to live browser clients is the goal. As an ingestion path it fights its own design; the cleanest way to get Channels' fan-out is to layer it on top of Option D rather than treat A as standalone.

A reasonable phasing — *not a recommendation, just an observation that follows from the table* — is **C → D**, with Channels added on top of D if and only if live dashboards become a product goal:

- **C → D** is a bounded migration: swap the file-tail mechanism for a Streams consumer; the Asset upsert call is identical. The bridge process either keeps tailing logs and writes to the stream, or moves to Broker bindings.
- **D → D + Channels** is purely additive: a second consumer in a *different* consumer group reads the same stream and `group_send`s post-commit events to browsers. No change to the ingest path.
- The path through B is no longer the natural middle stop; B is appropriate only if specific Celery-framework features (scheduling, periodic tasks, retry chains) become useful for related work — at which point B and D coexist for different workloads.

---

## What's not analyzed in this pass

These were considered and deliberately deferred. Each could become a fourth option section if a follow-up iteration justifies it.

| Option | Why deferred |
|---|---|
| **Direct HTTP webhook** — Zeek scripts POST to a DRF endpoint | Zeek is not idiomatically an HTTP client; this couples Zeek's loop to Django's response time and creates a synchronous failure dependency in the wrong direction. Also requires writing the POST in Zeek script, which is awkward |
| **Kafka pipeline** — Zeek's Kafka writer plugin → Kafka topic → Django consumer | Adds Kafka as a runtime dependency. Defensible at multi-sensor / multi-tenant scale; overkill for a small-hospital sensor today. If multi-tenancy lands, Kafka becomes a serious alternative to Redis Streams (Option D) |
| **Zeek Broker direct → Django ORM** (no Streams, no Celery, no Channels) — a Python process subscribed to Broker events, calling ORM directly | A real option, distinct from Option D in that it has *no* durable buffer between Zeek and Django. Subscriber downtime drops events. Lowest latency available; lowest durability. Worth a pass if live ingestion latency dominates and durability is tolerable (e.g., sub-second telemetry where occasional gaps are fine) |
| **Vector / Filebeat as bridge for Option D** — Vector tails Zeek logs and `XADD`s to Streams | A bridge variant of Option D, not a separate option. Vector is the off-the-shelf fallback chosen by the decision doc when `zeek-redis` is not viable. Battle-tested file→stream shipper with retry, backoff, and observability built in; the cost is one more daemon to operate |
| **`zeek-redis` plugin as primary bridge for Option D** — Zeek scripts publish to a Redis stream directly via a community plugin | Investigated and ruled out for Stage 1 — no current package writes to Redis Streams. See [bridge-investigation-findings.md](bridge-investigation-findings.md). Revisitable if a Streams-supporting package emerges; the bridge layer is swappable behind the stream |
| **Hybrid C + A** — sidecar writes to ORM and `group_send`s to Channels for browser fan-out | Subsumed by **D + Channels** in the comparison-table phasing notes. Listed here for completeness; not a separate option |

---

## Open questions for the next iteration

1. **Which Zeek log streams matter for asset discovery?** `conn.log` for IP/MAC pairs, `dns.log` for hostnames, `software.log` for fingerprints — enumerate before designing the bridge so its filter set is concrete.
2. **What is the asset upsert rate envelope?** Determines whether per-event Celery tasks are fine or batching is needed. `conn.log` alone can be tens of thousands of records/hour on a busy network; not all of those need to upsert assets.
3. **Is live browser push a near-term product goal?** If yes within the same fiscal year as this spike, Option A's investment pays double. If not, A is over-engineering.
4. **Standalone or cluster Zeek?** Affects where the bridge runs (logger node has the logs; Broker can be subscribed from anywhere). Documented in the companion ideal-usage doc; the answer is probably standalone for the small-hospital target but worth confirming.
5. **What happens to events the sidecar can't map to an Asset?** A DLQ table, a side log, or a notice — needs a decision so the design isn't silent on the unhappy path.
6. **Idempotency window.** Asset upserts on `mac_address` are idempotent; replays are safe. But what about events that update mutable state (last-seen timestamps, port lists)? Replay semantics need to be specified before any option is wired up.
7. **Streams retention policy.** If Option D is on the table, the retention bound (length, time, or both) defines the operational SLA — "the consumer can be down for X before data is lost." Needs a number, not a placeholder, before any code is written.
8. **Bridge mechanism for Option D.** ~~Pending investigation.~~ **Resolved 2026-05-08** as **Vector** — the [bridge investigation findings](bridge-investigation-findings.md) found no current zeek-redis package with Streams support; a Broker subscriber remains a possible Stage 3 alternative if low-latency live ingestion later dominates over file durability.

---

## References

- Companion: [zeek-and-channels-ideal-usage.md](zeek-and-channels-ideal-usage.md)
- HL7 spike (precedent for file-based pipelines): [../../hl7/README.md](../../hl7/README.md)
- Django Channels: https://channels.readthedocs.io/
- Celery: https://docs.celeryq.dev/
- Redis Streams introduction: https://redis.io/docs/latest/develop/data-types/streams/
- Redis Streams commands (`XADD`, `XREADGROUP`, `XPENDING`, `XCLAIM`): https://redis.io/commands/?group=stream
- Zeek logging framework: https://docs.zeek.org/en/master/frameworks/logging.html
- Zeek Broker (Python bindings): https://docs.zeek.org/projects/broker/en/stable/python.html
