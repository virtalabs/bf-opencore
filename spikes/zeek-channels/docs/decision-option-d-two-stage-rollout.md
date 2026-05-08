# DECISION: Adopt Option D (Streams-Buffered Ingest), with Channels Layered in Stage 2

**Status:** Decided 2026-05-08
**Decision:** Adopt **Option D** — Zeek → bridge → Redis Streams → Django consumer → PostgreSQL — and roll it out in two stages:
- **Stage 1** ships the ingestion pipeline. Asset state is materialized in Postgres from Zeek-derived events. No live browser updates yet.
- **Stage 2** layers Channels on top as a *second consumer* of the same stream, providing live browser fan-out. The Stage 1 path is unchanged.

Stage 1 is shippable on its own and delivers the core asset-discovery value. Stage 2 is purely additive — it adds a capability without modifying the ingestion path.

**Companion analysis** (kept separate so this decision doc stays small):

- [zeek-and-channels-ideal-usage.md](zeek-and-channels-ideal-usage.md) — how Channels and Zeek each want to be deployed in isolation.
- [zeek-to-django-integration-options.md](zeek-to-django-integration-options.md) — four-option analysis (A: Channels, B: Celery, C: log-tail sidecar, D: Streams consumer) across effort, compatibility, and tradeoffs.
- [existing-telemetry-ingestion-solutions.md](existing-telemetry-ingestion-solutions.md) — survey of mature stacks; pattern extraction; validation that Option D matches the canon.

---

## Context

The spike began with a question: how should Zeek-derived events reach the BlueFlow Asset model? The four-option analysis evaluated Channels (live, ephemeral), Celery (durable async work queue), a log-tail sidecar (no broker), and a Redis Streams consumer (durable buffer, no Celery). The existing-solutions survey validated that the Streams-consumer shape matches what Security Onion, Malcolm, Sentry, PostHog, and Loki all converge on at their respective scales.

A decision is needed now so prototype work can begin with a fixed target architecture, retention policy can be set, and the bridge mechanism can be chosen.

---

## Decision

**Adopt Option D.** Roll it out in two stages, where the staging axis is *product capability* (ingestion only → ingestion + live UX), not implementation choices within ingestion. The bridge mechanism (zeek-redis plugin if viable, Vector otherwise) is an implementation choice within Stage 1 — fixed by investigation before implementation begins, but not a staging axis.

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

- **Bridge mechanism** (one of the following, in preference order):
  1. **zeek-redis plugin** — *first choice if viable.* In-process to Zeek; no separate bridge daemon. Simplest topology and lowest operational surface. Requires investigation (see open question §6.0) to confirm a maintained plugin exists for the target Zeek version with Redis Streams (`XADD`) support, not just pub/sub. If that confirmation lands, this is the bridge.
  2. **Vector** — *fallback when zeek-redis is not viable.* Off-the-shelf shipper recommended by survey §5.2. Battle-tested rotation handling, retry/backoff, observability, disk buffering. Adds one daemon to operate.
  3. **Custom Python tailer** — *not recommended.* Listed only for completeness. Reimplements rotation handling, offset persistence, and back-pressure that off-the-shelf shippers have solved. Survey §4.2 specifically argues against this path. If both options above are blocked for hard reasons (no viable plugin, Vector adoption blocked operationally), revisit the decision rather than fall through to custom code.

  The bridge investigation (open question §6.0) must complete before Stage 1 implementation begins, so the bridge choice is fixed before code is written.
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

## Consequences

**What Stage 1 commits us to**

- Operating Redis Streams as a durable buffer with a defined retention policy. This is a new operational responsibility distinct from existing Celery use of Redis.
- Maintaining a Django management command consumer as a long-running process supervised at the same tier as Celery workers.
- A bridge mechanism — zeek-redis plugin if viable, Vector otherwise. Custom Python is explicitly not in the recommended set.
- Treating the Streams payload contract as a real interface — versioned, evolved with care.
- Reserving the `blueflow-fanout` consumer group name for Stage 2 use.

**What Stage 2 commits us to (additionally)**

- ASGI deployment alongside (or in place of) the existing WSGI deployment.
- `channels` and `channels_redis` as runtime dependencies.
- A second consumer group on the `zeek:events` stream and a Channels consumer process.
- A WebSocket auth model and a documented browser-side contract.
- Frontend integration to consume the live channel (out of this spike's scope, but a real downstream commitment).

**What this decision still does NOT commit us to**

- A specific bridge implementation. zeek-redis plugin is the first choice pending investigation; Vector is the fallback. Custom Python is excluded.
- A specific Stage 2 consumer shape (stream-direct vs. post-commit signal). Deferred to Stage 2 design.
- A specific raw-archive strategy. Survey §5.4 surfaced this; on the open-questions list, not part of this decision.
- A specific multi-tenant or multi-sensor topology. Single-sensor scope only.
- The Zeek Broker subscriber as the bridge mechanism. If low-latency live ingestion later dominates over file durability, Broker is a possible Stage 3 replacement for the bridge.
- A specific `zeek-redis` plugin package as the production bridge. Investigation (§6.0) names the candidate; that decision is downstream of this one.

---

## Risks and mitigations

| Risk | Stage | Impact | Mitigation |
|---|---|---|---|
| Streams retention misconfigured (too short) → consumer falls behind → data loss | 1 | **High** — silent data loss | Monitor `XPENDING` and `XLEN`; alert on growth beyond a configured threshold; document the retention SLA explicitly |
| Bridge investigation (§6.0) finds neither zeek-redis plugin viable nor Vector adoption clear | 1 | High — blocks Stage 1 | Schedule investigation early; if both paths block, the decision returns here for revision rather than falling through to custom code |
| zeek-redis plugin chosen but plugin proves unstable in production | 1 | Medium — bridge swap required | Stage 1's payload contract on the stream is the same regardless of bridge; switching from zeek-redis to Vector is a bridge replacement, not a consumer change |
| Redis becomes a hard dependency for ingest | 1 | Medium — already shared with Celery | Configure AOF persistence to limit data loss across restarts; document Redis as a Tier-1 dependency in the runbook |
| At-least-once delivery means duplicate ORM writes | 1 | Low — by design | `Asset.objects.update_or_create` on `mac_address` is already idempotent. Document this contract in the consumer's module docstring so future maintainers don't break it |
| Stage 2 design choice (stream vs. signal) ambiguous | 2 | Medium if unresolved | Decision deferred to Stage 2 design pass; tradeoff documented above. Not a blocker for Stage 1 |
| ASGI deployment in Stage 2 destabilizes existing WSGI traffic | 2 | High if mishandled | Stage 2 design must specify whether ASGI and WSGI coexist or one replaces the other; load test before cutover |
| Browser WebSocket auth gap | 2 | High — security surface | Explicit auth model required as Stage 2 exit criterion; do not ship Stage 2 without review |
| Channels consumer in `blueflow-fanout` falls behind under bursty load | 2 | Medium — affects live UX, not state | Streams retention is shared between groups, so retention sized for ingestion is also sized for fan-out as long as consumers are similarly fast. Monitor `XPENDING` per group |

---

## Open questions that must be resolved before Stage 1 ships

These are imported from the integration-options doc's open-questions list, narrowed to those that block Stage 1.

0. **Bridge investigation.** Identify the current state of zeek-redis plugins. Specifically: which package(s) are maintained as of investigation, which Zeek versions they support, whether any of them write to Redis Streams (vs. only pub/sub), and whether anyone is running them in production at non-trivial scale. If a viable plugin is identified, the bridge is zeek-redis. Otherwise, the bridge is Vector. Custom Python is not in the decision tree. Output of this investigation: a one-page findings doc with a clear "use X" recommendation. Estimated effort: a few hours. **Must complete before Stage 1 implementation begins.**
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
