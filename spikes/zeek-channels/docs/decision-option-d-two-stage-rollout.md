# DECISION: Adopt Option D (Streams-Buffered Ingest), with Channels Layered in Stage 2

**Status:** Decided 2026-05-08; bridge-mechanism amended 2026-05-12 (see Decision section below).
**Decision:** Adopt **Option D** — Zeek → bridge → Redis Streams → Django consumer → PostgreSQL — and roll it out in two stages:
- **Stage 1** ships the ingestion pipeline. Asset state is materialized in Postgres from Zeek-derived events. No live browser updates yet.
- **Stage 2** layers Channels on top as a *second consumer* of the same stream, providing live browser fan-out. The Stage 1 path is unchanged.

Stage 1 is shippable on its own and delivers the core asset-discovery value. Stage 2 is purely additive — it adds a capability without modifying the ingestion path.

**Companion analysis** (kept separate so this decision doc stays small):

- [zeek-and-channels-ideal-usage.md](zeek-and-channels-ideal-usage.md) — how Channels and Zeek each want to be deployed in isolation.
- [zeek-to-django-integration-options.md](zeek-to-django-integration-options.md) — four-option analysis (A: Channels, B: Celery, C: log-tail sidecar, D: Streams consumer) across effort, compatibility, and tradeoffs.
- [existing-telemetry-ingestion-solutions.md](existing-telemetry-ingestion-solutions.md) — survey of mature stacks; pattern extraction; validation that Option D matches the canon.
- [bridge-investigation-findings.md](bridge-investigation-findings.md) — original §6.0 investigation. Catalogs `sedarasecurity/zeek-redis`, `mbispham/zeekjs-redis`, and the legacy `Bro::Redis`; concluded "no off-the-shelf plugin → Vector." Operative conclusion **superseded by the doc below**.
- [bridge-decision-revisited.md](bridge-decision-revisited.md) — **operative bridge decision.** ZeekJS as Stage 1 prototype default; C-plugin fork and Vector as documented swap-in paths; Storage Framework KV evaluated and rejected.

---

## Context

The spike began with a question: how should Zeek-derived events reach the BlueFlow Asset model? The four-option analysis evaluated Channels (live, ephemeral), Celery (durable async work queue), a log-tail sidecar (no broker), and a Redis Streams consumer (durable buffer, no Celery). The existing-solutions survey validated that the Streams-consumer shape matches what Security Onion, Malcolm, Sentry, PostHog, and Loki all converge on at their respective scales.

A decision is needed now so prototype work can begin with a fixed target architecture, retention policy can be set, and the bridge mechanism can be chosen.

---

## Decision

**Adopt Option D.** Roll it out in two stages, where the staging axis is *product capability* (ingestion only → ingestion + live UX), not implementation choices within ingestion.

The Stage 1 bridge mechanism is **bespoke ZeekJS** (a ~30-line in-process producer using Zeek's bundled JavaScript runtime, calling `redis.xAdd(...)` from a `Conn::log_policy` hook). The C-plugin fork (`sedarasecurity/zeek-redis` patched `LPUSH`→`XADD`) and Vector are documented swap-in paths, neither of which requires changing the consumer. The Storage Framework KV side-channel is evaluated and explicitly rejected.

The bridge decision was originally fixed to Vector on 2026-05-08 by the §6.0 investigation ([bridge-investigation-findings.md](bridge-investigation-findings.md)). That conclusion was **amended on 2026-05-12** after closer reading of ZeekJS (bundled with Zeek since v6.0, not a third-party package) and Zeek 8's Storage Framework. See [bridge-decision-revisited.md](bridge-decision-revisited.md) for the full revised analysis.

### Target architecture (Stage 2 — full picture)

```
                                                    ┌──────────────┐
                                              ┌────►│ Django mgmt  │──► PostgreSQL
                                              │     │ command      │   (Asset state)
┌─────────┐    ┌────────┐    ┌──────────────┐ │     │ XREADGROUP   │
│  Zeek   │───►│ bridge │───►│Redis Streams │─┤     │ group:       │
│ workers │    │        │    │ zeek:events  │ │     │  blueflow-   │
│         │    │        │    │              │ │     │   ingest     │
│         │    │        │    │              │ │     └──────────────┘
└─────────┘    └────────┘    └──────────────┘ │
                                              │     ┌──────────────┐
                                              └────►│ Channels     │──► Browser WS
                                                    │ consumer     │   (live updates)
                                                    │ XREADGROUP   │
                                                    │ group:       │
                                                    │  blueflow-   │
                                                    │   fanout     │
                                                    └──────────────┘
```

**Stage 1** runs only the upper consumer (`blueflow-ingest`). **Stage 2** adds the lower consumer (`blueflow-fanout`) reading the same stream. Two consumer groups means each consumer reads every entry independently, with its own offset tracking — Streams' native primitive for this exact pattern.

---

## Why Option D, briefly

Long form is in the companion docs. Headline reasons:

1. **Matches the canonical three-stage shape** every comparable mature stack uses (collector → durable buffer → consumer/materializer). The survey makes this concrete: Security Onion, Malcolm, Sentry, PostHog, Loki, and Arkime all map onto the same shape with different primitives. Option D is the version of that shape that fits BlueFlow's scale.
2. **Reuses Redis** — already deployed for Celery; no new runtime infrastructure.
3. **Durable, replayable, at-least-once.** Streams retention + consumer groups give explicit acknowledgment, redelivery via `XPENDING` / `XCLAIM`, and replay for re-derivation if consumer logic changes. None of this is true of Option A's channel layer used as ingestion.
4. **Avoids Celery's structurally redundant hop.** For asset upsert specifically, putting Celery between Streams and the ORM duplicates buffering without adding properties. Celery remains the right tool elsewhere in BlueFlow for genuinely task-shaped work.
5. **Cleanly extensible to Channels-based browser push** — exactly the Stage 2 layering. A second consumer group on the same stream means Stage 2 does not modify Stage 1.

### Why not A, B, C — one line each

- **A (Channels-as-ingest):** channel layer is best-effort by design; using it for ingestion drops events under back-pressure. Channels is the right tool for browser fan-out — which is precisely what Stage 2 uses it for, on top of D.
- **B (Celery):** the Celery hop is redundant when Streams already provides durability and offset semantics. B remains correct for *task-shaped* work, not for ingest-to-state.
- **C (log-tail sidecar, no buffer):** simplest path but no buffering between sensor and ORM, and rotation handling is custom code we'd own. Cheaper than D in the short term, weaker in operational primitives, and the C → D migration is a real swap rather than a free upgrade.

---

## Two-stage rollout

### Stage 1 — Ship the ingestion pipeline

**Goal:** real assets discovered by Zeek land in Postgres via the Streams-buffered consumer pipeline. Browser-side reactivity comes in Stage 2.

**Components**

- **Bridge mechanism: bespoke ZeekJS** (revised 2026-05-12). A ~30-line script invoked as `zeek -i <iface> send-to-redis.js` that subscribes to `Conn::log_policy` (and other relevant log hooks) and calls `redis.xAdd('zeek:events', '*', {...})` per record. ZeekJS is bundled with Zeek as a built-in plugin since v6.0 — not a third-party package. The full minimal example is in [bridge-decision-revisited.md](bridge-decision-revisited.md). Two swap-in paths are documented and leave the consumer unchanged: (i) **C-plugin fork** of `sedarasecurity/zeek-redis` with `LPUSH`→`XADD` (~20-line patch) for production hardening when Node footprint becomes binding; (ii) **Vector** when disk-buffered durability across Redis outages matters more than in-process simplicity. Custom Python tailing remains explicitly excluded per survey §4.2.
- **Redis stream `zeek:events`.** Single stream, retention configured per open question §6.1. Lives in the same Redis instance as Celery, in a separate logical DB.
- **Consumer group `blueflow-ingest`.** Starts with one consumer; horizontal scaling deferred until Stage 1 data shows it's needed.
- **Django management command** (`python manage.py zeek_stream_consume`). Runs an `XREADGROUP BLOCK` loop, parses payloads, calls `Asset.objects.update_or_create(...)`, then `XACK`s. Permanently-failing entries route to a dead-letter stream (`zeek:dead`) and the main entry is acked.
- **Tests.** `fakeredis[lua]` for end-to-end stream tests; fixture log files for bridge tests; standard `pytest-django` for ORM-side tests.

**What we're explicitly proving in Stage 1**

- End-to-end pipeline works on real Zeek output, not synthetic fixtures.
- Throughput envelope is acceptable for the target sensor (a small-hospital VLAN at hundreds of Mbps).
- Retention policy is sensible — consumer can keep up; pending entries don't grow unbounded.
- Failure modes (consumer crash mid-batch, parse error, ORM failure, broker disconnect) behave as designed.

**Stage 1 explicitly does NOT include**

- Channels deployment, ASGI deployment, browser WebSocket push — all Stage 2.
- Multi-tenant or multi-sensor topology.
- The raw Zeek log archive separation surfaced by the survey (open question §6.4). For Stage 1, raw logs are whatever Zeek's logger writes by default.

**Stage 1 reserves a name now to avoid Stage 2 churn**

- Reserve `blueflow-fanout` as the consumer group name for the Stage 2 Channels layer. Document this convention in the consumer's module docstring so the future Stage 2 implementer doesn't pick a conflicting name.

**Stage 1 exit criteria**

Stage 1 is complete when:

- A real Zeek deployment feeds events into the `zeek:events` stream for at least one full week without an ops intervention.
- Asset upsert from those events is verified against ground-truth data (a small set of known devices on the test network).
- `XPENDING` for the `blueflow-ingest` group stays bounded under sustained load — i.e., the consumer does not fall behind the producer.
- A documented runbook exists for the three most likely failures (consumer crash, parse error, Redis restart).
- Throughput, retention, and consumer-group sizing numbers are recorded for use in Stage 2 sizing.

### Stage 2 — Layer Channels on top for browser fan-out

**Goal:** live browser updates as Zeek-derived events flow through, without modifying the Stage 1 ingestion path.

**What's added**

- **ASGI deployment.** Daphne or Uvicorn, supervised at the same tier as the existing WSGI process (or replacing it via migration — that decision is part of Stage 2's design pass).
- **`channels` and `channels_redis`** added as runtime dependencies. The Redis channel layer reuses the existing Redis instance, in a separate logical DB from both Celery and the `zeek:events` stream.
- **Second consumer group `blueflow-fanout`** reading the same `zeek:events` stream. Each consumer group tracks its own offsets, so the ingestion path and the fan-out path read the same events independently.
- **Channels consumer** that reads stream entries and `group_send`s them to a WebSocket group.
- **Authenticated WebSocket route** + browser-side subscription. Frontend integration shape is out of this spike's scope, but the contract — what channel name, what message format — needs to be specified as part of Stage 2 design.

**What stays the same**

- Stage 1's ingestion consumer keeps running unchanged.
- The Streams configuration, the stream name, and the bridge process are unchanged.
- The Asset upsert path is unchanged.
- Stage 1's exit criteria stay met — Stage 2 must not degrade Stage 1's properties.

**Stage 2 design choice to resolve before implementation**

The Channels consumer can take one of two shapes:

| Shape | What Channels reads | Tradeoff |
|---|---|---|
| **(a) Stream consumer** | Reads `zeek:events` directly via `XREADGROUP` in `blueflow-fanout` | Architecturally cleanest — Streams is the single source of truth. Browsers see all events including any the ingestion consumer drops or transforms |
| **(b) Post-commit signal** | Listens for Django `post_save` signals on Asset; ingestion consumer fires the signal | More idiomatic Django; browsers see *committed state changes* only. Couples Channels to ORM events; Channels-side state is whatever the ingest consumer chose to materialize |

Shape (a) is closer to the survey's pattern (Sentry/PostHog/Loki all materialize state from stream consumers, fan-out is also stream-based). Shape (b) is closer to typical Django + Channels examples. The decision depends on whether browsers need to see "raw events" or "asset state changes." Defer to Stage 2 design pass; document the tradeoff now so it doesn't get smuggled past.

**What Stage 2 commits us to**

- **ASGI deployment.** This is a real operational change — a new process tier, new monitoring, new failure modes around WebSocket connection lifetimes. The integration-options doc treated this as a cost when it was the default ingestion path; for fan-out it is the *correct* cost because Channels is doing its native job here.
- **Channels' best-effort layer is acceptable here** because Streams provides the durability upstream. The channel layer is between the Channels consumer and the WebSocket clients, where lossy fan-out (a slow browser drops messages, others continue) is appropriate behavior.
- **A WebSocket auth model.** Has to be decided as part of Stage 2 — this spike does not cover it.

**Stage 2 exit criteria**

Stage 2 is complete when:

- Browser clients receive live updates within a target latency envelope (specific number to be set during Stage 2 design — probably sub-second end-to-end).
- Stage 1's ingestion consumer is unaffected by Stage 2 load (verified by load test).
- Connection-loss and reconnect behavior is documented and tested for representative client failure modes.
- Auth model for WebSocket connections is documented and reviewed.

---

## Direction and timeline

The bridge implementation choice evolves with the project's lifecycle. The Stage 1 / Stage 2 rollout above stages *product capability* (ingestion-only → ingestion + live UX); this section stages *bridge implementation*. The two are orthogonal — the consumer side stays stable across all three implementation stages because the integration boundary is the payload contract on `zeek:events`, not the bridge process itself.

### Short-term: native ZeekJS (hackathon-shaped work)

For short-term needs — **hackathon prototypes, internal demos, and the Stage 1 spike validation** — the native ZeekJS path is best. A ~30-line `send-to-redis.js` invoked as `zeek -i <iface> send-to-redis.js`, with zero new daemons and zero new packages: ZeekJS is bundled with Zeek as a built-in plugin since v6.0. Edit-then-restart iteration loop, native typed access to Zeek records, time-to-working-prototype measured in hours rather than days. Full example and rationale in [bridge-decision-revisited.md](bridge-decision-revisited.md).

This is explicitly the right choice for time-boxed work where iteration speed dominates and the production-deploy constraints haven't bitten yet.

### Mid-term: fork a community C++ plugin

When the prototype graduates to a hardened production deploy — long enough on a real sensor that Node.js footprint (~50MB) and in-process coupling start mattering — the next step is to **fork a community C++ Zeek plugin** as the bridge. Two reasonable fork bases, both leaving the Django consumer unchanged:

- **`sedarasecurity/zeek-redis`** — the literal Redis writer plugin. Swap `LPUSH` for `XADD` in `DoWrite` (already supported by `redis-plus-plus`). ~20-line C++ patch. Upstream stale (last functional change 2024-05-08), so we take over de facto maintenance.
- **`SeisoLLC/zeek-kafka`** — better-maintained plugin in the same architectural shape (Apache-2.0, actively tracking Zeek master). Reasonable base if rebasing rather than patching; the CMake glue and `zkg.meta` patterns transfer cleanly, with the Kafka-client → Redis-client substitution as the bulk of the work.

Either fork swaps the ~50MB Node.js runtime for ~200KB of hiredis. Mid-term commitment is real because we own the fork — track Zeek plugin-API changes across versions, ship binaries per release.

### Long-term: explore replacing Redis entirely

Redis Streams is the right primitive *now*: already deployed for Celery, the team operates it, and it provides Option D's required durability/replay/consumer-group properties out of the box. But the brokering layer is **not architecturally load-bearing in the deeper sense** — the bridge produces structured events, the consumer reads them, and the integration boundary is the payload contract. Whether that contract rides on Redis Streams, Kafka topics, NATS JetStream, or no broker at all (a direct Zeek-Broker subscriber) is a swap that doesn't change the consumer's shape.

Long-term, when the project's needs grow past what Redis comfortably provides — multi-sensor topologies, multi-tenant fan-out, durability guarantees that exceed Redis AOF, geo-distribution — **re-evaluating the broker entirely** is on the table. Candidates already surfaced in the integration-options analysis:

- **Kafka** — defensible at multi-sensor / multi-tenant scale, overkill on a single small-hospital sensor today. See [zeek-to-django-integration-options.md](zeek-to-django-integration-options.md) "What's not analyzed."
- **NATS JetStream** — lighter than Kafka, similar at-least-once durability semantics, but a runtime the team hasn't operated.
- **Zeek Broker → direct subscriber** — no broker at all between Zeek and Django; lowest latency, no durable buffer; documented as a possible Stage 3 alternative if low-latency live ingestion ever dominates over file durability.

This is explicitly *not a Stage 1 decision*. It's a flagged direction for when the operational envelope expands past what a single-sensor Redis deployment comfortably handles. The takeaway for short-term and mid-term work: build against the `zeek:events` payload contract, not against Redis-specific primitives in the consumer.

### Candidate bridges at a glance

The full per-axis analysis is in [bridge-decision-revisited.md](bridge-decision-revisited.md). Summary:

| Property | **ZeekJS (Stage 1 default)** | **C plugin (forked)** | Storage Framework KV | **Vector** | Python sidecar |
|---|---|---|---|---|---|
| Lines we own | ~30 JS | C++ plugin + build glue | Zeek scripts + scan/sub consumer | ~50 TOML/VRL config | ~150–250 Py |
| New daemons | 0 | 0 | 1 (KV consumer) | 1 (Vector) | 1 (sidecar) |
| Producer mechanism | In-Zeek JS hook → `XADD` | In-Zeek C++ → `XADD` | In-Zeek `Storage::put` (SET/HSET) | Tail logs → `XADD` | Tail logs → `XADD` |
| Disk buffer when Redis is down | **No** (RAM offline queue) | No | No | **Yes** (configurable) | Yes (log files = buffer) |
| Delivery semantics | At-least-once if write ack'd, else lost | Same | **Lossy (pubsub)** or **stale (poll)** | At-least-once, disk-durable | At-least-once if offset persisted |
| Replay capability | Yes (Streams) | Yes (Streams) | **No** | Yes | Yes |
| Iteration speed | Fast (edit file, restart) | Slow (rebuild C++) | Medium | Fast (edit config) | Fast |
| Runtime deps | Node.js (~50MB) | hiredis (~200KB) | hiredis | Vector binary (~50–100MB) | Python (already installed) |
| Failure blast radius | Inside Zeek process | Inside Zeek process | Inside Zeek + KV consumer | Independent process | Independent process |
| Long-term maintenance | npm `redis` (community) | We own the fork | Zeek script + custom consumer | Vector upstream | We own the tailer |
| Off-the-shelf? | Mostly (npm `redis`) | Plugin needs forking | First-class Zeek | Yes | No |
| **Suits short-term (hackathon)** | ★ best | Worst | Wrong shape | Heavy | Medium |
| **Suits mid-term (hardened production)** | OK with coupling caveats | **Strong** | No | **Strong** | Strong |

The "★ best" cell aligns with the short-term row of the timeline above; the "Strong" cells under the C-plugin and Vector columns align with the mid-term options. Storage Framework KV is wrong-shape at every horizon and is excluded. The long-term option (replacing Redis entirely) is not represented on this table because the table is *Redis-bridge candidates* — by definition every column assumes Redis Streams as the buffer.

---

## Consequences

**What Stage 1 commits us to**

- Operating Redis Streams as a durable buffer with a defined retention policy. This is a new operational responsibility distinct from existing Celery use of Redis.
- Maintaining a Django management command consumer as a long-running process supervised at the same tier as Celery workers.
- A ZeekJS-based in-process bridge for the Stage 1 prototype, with the explicit Node.js footprint and in-process-coupling caveats documented in [bridge-decision-revisited.md](bridge-decision-revisited.md). Production hardening may swap to the C-plugin path; that swap is a ~20-line patch and does not change the consumer.
- Treating the Streams payload contract on `zeek:events` as a real interface — versioned, evolved with care. This contract is the bridge/consumer integration boundary that survives all documented bridge swaps.
- Reserving the `blueflow-fanout` consumer group name for Stage 2 use.

**What Stage 2 commits us to (additionally)**

- ASGI deployment alongside (or in place of) the existing WSGI deployment.
- `channels` and `channels_redis` as runtime dependencies.
- A second consumer group on the `zeek:events` stream and a Channels consumer process.
- A WebSocket auth model and a documented browser-side contract.
- Frontend integration to consume the live channel (out of this spike's scope, but a real downstream commitment).

**What this decision still does NOT commit us to**

- A specific Stage 2 consumer shape (stream-direct vs. post-commit signal). Deferred to Stage 2 design.
- A specific raw-archive strategy. Survey §5.4 surfaced this; on the open-questions list, not part of this decision.
- A specific multi-tenant or multi-sensor topology. Single-sensor scope only.
- The Zeek Broker subscriber as the bridge mechanism. If low-latency live ingestion later dominates over file durability, Broker remains a possible Stage 3 replacement for the in-process producer. The §6.0 findings explicitly leave this door open.
- Long-term commitment to ZeekJS as the bridge. The payload contract on `zeek:events` is the integration boundary that survives across bridge implementations. The C-plugin fork, Vector, a Broker subscriber, or a future Streams-supporting community plugin are all swap-in candidates without consumer-side change.

---

## Risks and mitigations

| Risk | Stage | Impact | Mitigation |
|---|---|---|---|
| Streams retention misconfigured (too short) → consumer falls behind → data loss | 1 | **High** — silent data loss | Monitor `XPENDING` and `XLEN`; alert on growth beyond a configured threshold; document the retention SLA explicitly |
| ZeekJS bridge fails in production (Node memory growth, GC pause, in-process coupling intolerable) | 1 | High — affects Stage 1 viability in prod | Two documented swap-ins, neither of which changes the consumer: fork `sedarasecurity/zeek-redis` to a C-plugin (~20-line patch) if footprint/coupling is the issue, or swap to Vector if disk-buffered durability is the issue. See [bridge-decision-revisited.md](bridge-decision-revisited.md) |
| Bridge payload shape drifts from consumer's expectations (any bridge implementation) | 1 | Medium — bug-shaped, not architectural | Pin the payload schema on `zeek:events` before Stage 1 ships; add a contract test that runs the bridge against fixture Zeek output and asserts the consumer parses the resulting `XADD` payloads correctly. The contract is the bridge/consumer interface — it must survive bridge swaps |
| Redis becomes a hard dependency for ingest | 1 | Medium — already shared with Celery | Configure AOF persistence to limit data loss across restarts; document Redis as a Tier-1 dependency in the runbook |
| At-least-once delivery means duplicate ORM writes | 1 | Low — by design | `Asset.objects.update_or_create` on `mac_address` is already idempotent. Document this contract in the consumer's module docstring so future maintainers don't break it |
| Stage 2 design choice (stream vs. signal) ambiguous | 2 | Medium if unresolved | Decision deferred to Stage 2 design pass; tradeoff documented above. Not a blocker for Stage 1 |
| ASGI deployment in Stage 2 destabilizes existing WSGI traffic | 2 | High if mishandled | Stage 2 design must specify whether ASGI and WSGI coexist or one replaces the other; load test before cutover |
| Browser WebSocket auth gap | 2 | High — security surface | Explicit auth model required as Stage 2 exit criterion; do not ship Stage 2 without review |
| Channels consumer in `blueflow-fanout` falls behind under bursty load | 2 | Medium — affects live UX, not state | Streams retention is shared between groups, so retention sized for ingestion is also sized for fan-out as long as consumers are similarly fast. Monitor `XPENDING` per group |

---

## Open questions that must be resolved before Stage 1 ships

These are imported from the integration-options doc's open-questions list, narrowed to those that block Stage 1.

0. ~~**Bridge investigation.**~~ **RESOLVED 2026-05-08; AMENDED 2026-05-12.** No current third-party zeek-redis package supports Redis Streams ([bridge-investigation-findings.md](bridge-investigation-findings.md)). However, bespoke ZeekJS — Zeek's bundled JavaScript runtime, in-tree since v6.0 — provides a ~30-line in-process producer path that the original investigation did not separate from third-party packages. Stage 1's prototype bridge is **bespoke ZeekJS**, with the **C-plugin fork** (~20-line patch to `sedarasecurity/zeek-redis`) and **Vector** as documented swap-in paths. The Zeek 8 Storage Framework KV side-channel is evaluated and explicitly rejected. Full revised analysis in [bridge-decision-revisited.md](bridge-decision-revisited.md).
1. **Streams retention bound** — concrete number (length, time, or both). Defines the SLA: "consumer can be down for X before data is lost." Cannot be left as a placeholder.
2. **Which Zeek streams matter** — the bridge filter set. `conn.log`, `dns.log`, `software.log` are the obvious candidates; the full list and the field subset of each must be enumerated.
3. **Consumer group sizing** — how many consumers in `blueflow-ingest`? Stage 1 starts at one; verify under expected load before declaring exit.
4. **Asset replay semantics for mutable state** — `mac_address`-keyed upsert is idempotent for static fields, but `last_seen`, `open_ports_tcp`, and similar mutable fields need a defined replay policy (last-write-wins? max-of? union?).
5. **Dead-letter handling SLA** — how often is `zeek:dead` reviewed? What triggers an alert? Decision needed before Stage 1 ships, even if the SLA is informal.

## Open questions that must be resolved before Stage 2 ships

6. **Channels consumer shape** — stream-direct (a) or post-commit signal (b). See Stage 2 design-choice section above.
7. **WebSocket auth model.** Token-based? Session-cookie compatibility? Per-asset authorization?
8. **ASGI deployment topology.** Coexist with WSGI, replace it, or run as a sidecar? Migration plan if replacement.
9. **Browser-side message contract.** What does the WebSocket message format look like? Versioning?

These Stage 2 questions are deferred — they should be answered when Stage 2 is being designed, not now.

---

## What this decision does NOT cover (deferred entirely)

- **Raw Zeek log archive** separate from Asset state. Survey §5.4 surfaced this as an open question; resolution can wait until either stage's design pass surfaces a need.
- **Multi-sensor / multi-tenant topology.** Single-sensor scope only.
- **Migration from a pre-existing ingest path.** No prior path exists; this decision builds the first one.
- **Buy-vs-build for the SIEM-shaped portion of the product.** BlueFlow remains an asset-management product. Tools surveyed in the existing-solutions doc are referenced for patterns, not adopted as products.
- **Frontend integration shape for Stage 2.** The Channels-side contract is in scope; the actual UI work is downstream.

---

## References

- Companion: [zeek-and-channels-ideal-usage.md](zeek-and-channels-ideal-usage.md)
- Companion: [zeek-to-django-integration-options.md](zeek-to-django-integration-options.md)
- Companion: [existing-telemetry-ingestion-solutions.md](existing-telemetry-ingestion-solutions.md)
- Spike branch: `feature/spike-zeek-channels`
- Redis Streams documentation: https://redis.io/docs/latest/develop/data-types/streams/
- Vector documentation: https://vector.dev/docs/
- Django Channels documentation: https://channels.readthedocs.io/
