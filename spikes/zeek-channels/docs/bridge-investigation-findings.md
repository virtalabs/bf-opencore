# Bridge Investigation Findings — Decision Doc §6.0

**Date:** 2026-05-08
**Status:** Amended 2026-05-12 — operative conclusion superseded by [bridge-decision-revisited.md](bridge-decision-revisited.md). Historical investigation preserved below.
**Original resolution (2026-05-08):** No current zeek-redis package supports Redis Streams. Stage 1's bridge is Vector. Custom Python remains excluded.
**Revised resolution (2026-05-12):** Stage 1 prototype default is **bespoke ZeekJS** (~30-line in-process producer using Zeek's bundled JavaScript runtime). The C-plugin fork (`sedarasecurity/zeek-redis` patched `LPUSH`→`XADD`) and Vector are documented swap-in paths. The Storage Framework KV side-channel is evaluated and explicitly rejected. See [bridge-decision-revisited.md](bridge-decision-revisited.md) for the full revised analysis.
**Related:** [decision-option-d-two-stage-rollout.md §6.0](decision-option-d-two-stage-rollout.md)

---

> **AMENDED 2026-05-12.** The original conclusion below ("no plugin → Vector") collapsed two independent decision axes (buffer location and producer language) and missed bespoke ZeekJS as a third architectural point. The package-by-package findings in this doc remain accurate as a record of what was checked; only the operative conclusion is superseded. **For the current Stage 1 bridge decision, read [bridge-decision-revisited.md](bridge-decision-revisited.md) first.**

---

## The question

The decision doc's open question §6.0 was the gating investigation before Stage 1 could be implemented:

> Identify the current state of zeek-redis plugins. Specifically: which package(s) are maintained as of investigation, which Zeek versions they support, whether any of them write to Redis Streams (vs. only pub/sub), and whether anyone is running them in production at non-trivial scale. If a viable plugin is identified, the bridge is zeek-redis. Otherwise, the bridge is Vector.

This document records what was checked, what was found, and the resolution.

---

## Method

- Surveyed the Zeek package manager registry at `packages.zeek.org` for Redis-related packages.
- GitHub search for repositories matching `zeek-redis` / `bro-redis`.
- GitHub code search for `XADD` in `*.zeek` files (i.e., any Zeek script anywhere on GitHub publishing to Redis Streams).
- Inspected each candidate's source, recent commit history, release tags, and adoption signals.
- Read the two relevant Zeek community discussion threads on log-to-Redis shipping.

---

## Packages evaluated

### `sedarasecurity/zeek-redis`

C++ Zeek logging-framework plugin. Registers `Log::WRITER_REDISWRITER`; ships log entries to Redis via the hiredis client.

| Field | Value |
|---|---|
| Last commit | 2024-05-08 (`v0.2.1` tag) |
| Previous commit | 2021-09-10 (~3-year gap) |
| Tags | `v0.2.1`, `v0.2.0`, `v0.1.1` |
| Stars / forks | 7 / 0 |
| Open issues | 1 (from 2022, "Add to `zkg` package source" — never resolved) |
| In Zeek package manager | No |
| Redis primitives used | **Lists (`LPUSH`) and Sets (`SADD`)** with `EXPIRE` |
| Streams (`XADD`) support | **None** |

The Redis-primitive finding was confirmed by reading `src/RedisWriter.cc`. The only Redis client method calls in the writer are `redis_client->lpush(...)`, `redis_client->sadd(...)`, and `redis_client->expire(...)`. There is no `xadd` invocation anywhere in the source.

**Not viable.** Wrong primitive for Option D's architectural needs, low adoption, never registered in the official package manager.

### `mbispham/zeekjs-redis`

ZeekJS-based logger that hooks `Log::log_stream_policy` and writes log records to Redis from JavaScript running inside Zeek.

| Field | Value |
|---|---|
| Last commit | 2024-07-23 |
| Stars / forks / watchers | 0 / 0 / 1 |
| In Zeek package manager | Yes (currently the only Redis-related package listed) |
| Zeek version requirement | > 6.0.2 with **experimental** ZeekJS as a builtin package |
| Redis primitives used | **Lists (`rPush`)** |
| Streams (`XADD`) support | **None** |

The Redis-primitive finding was confirmed by reading `scripts/index.js`. The only Redis client method called is `client.rPush(redisKey, serializedData)`.

**Not viable.** Same primitive mismatch as `sedarasecurity/zeek-redis`, with the additional dependency on experimental ZeekJS — a stack we have no other reason to adopt.

### `Bro::Redis` (legacy)

Original Bro logging plugin from the Bro 2.5.5 era (~2017). Predates the Zeek rename and predates Redis Streams (Streams shipped in Redis 5.0, 2018).

| Field | Value |
|---|---|
| Era | Bro 2.5.5 (~2017) |
| Self-description in docs | "code is not production ready" |
| Streams support | None — predates Streams entirely |

**Out of consideration.**

---

## Wider GitHub search

A code search across all of GitHub for `XADD` in `*.zeek` files returned zero results. Combined with the package manager survey, this is strong evidence that **no Zeek script or plugin currently in any public repository writes to Redis Streams.** The combination "Zeek + Redis Streams" appears to be unimplemented in the public ecosystem as of this investigation.

---

## Community context

Two Zeek community threads frame the state:

- **2023 thread** — [Send logs from zeek to redis i.e. a Redis log writer](https://community.zeek.org/t/send-logs-from-zeek-to-redis-i-e-a-redis-log-writer/6980). Active discussion of how to ship Zeek logs to Redis. Community recommendations were either "fork `sedarasecurity/zeek-redis`" or "use ZeekJS for testing only." A core Zeek maintainer noted that building a proper writer requires a full plugin and is "beyond the scope" of casual forum work. **No mention of Streams in the entire thread** — discussion was framed around pub/sub.
- **2015 thread** — [Redis Log Writer](https://community.zeek.org/t/redis-log-writer/3687). The original conversation that led to `sedarasecurity/zeek-redis`. Predates Redis Streams (which arrived in Redis 5.0, three years later), so the design naturally never considered them.

The takeaway is that Streams arrived after the Zeek-Redis ecosystem was built, and the ecosystem has not caught up.

---

## Resolution

**Stage 1's bridge is Vector.** The conditional in the decision doc ("zeek-redis if viable, Vector otherwise") collapses to Vector.

Custom Python remains excluded for the same reasons originally stated — survey §4.2 argues against re-implementing rotation handling and offset persistence, and that argument is unaffected by this investigation.

---

## What was not pursued (and why)

| Path | Why deferred or rejected |
|---|---|
| **Fork `sedarasecurity/zeek-redis` to swap `LPUSH` for `XADD`** | Technically a small change — the plugin already implements all the C++ scaffolding needed to write to Redis from a Zeek log writer. But forking turns Stage 1 from "use off-the-shelf" into "maintain a fork," which has ongoing cost (rebuilding against new Zeek versions, tracking upstream if it revives) and contradicts the survey's reasoning for using off-the-shelf bridges. Revisitable if Vector adoption is operationally blocked, but should not be the default path |
| **Wait for someone in the Zeek ecosystem to build Streams support** | Possible but unbounded in time. A Stage 1 decision cannot wait on it |
| **Use Apache Metron's Kafka writer plugin instead** | Real and maintained, but introduces Kafka as a runtime dependency. Survey §1.5 already deferred Kafka as overkill for a small-hospital sensor. Same conclusion applies here |
| **Skip the bridge daemon entirely via direct Zeek Broker → Python subscriber** | Listed in the integration-options deferred table as a real alternative. Lower latency, no buffer between Zeek and Django. Still possible as a *Stage 3* if low-latency live ingestion later dominates over file durability — but for Stage 1 the Vector path is more conservative and uses the buffer Option D was chosen for |
| **Lists-based bridge (using one of the existing plugins)** | Lists give a queue (`BRPOP` from the consumer side), but BRPOP is destructive and single-consumer-shaped. Lists cannot provide consumer groups, replay, or `XPENDING`-style observability — exactly the properties Option D was chosen for. A Lists-based bridge would invalidate Option D's architecture, not just substitute its primitive |

---

## Implication beyond Stage 1

Worth recording for future reference: *if and when* Streams support lands in the Zeek-Redis ecosystem (either via a new plugin, a fork of `sedarasecurity/zeek-redis`, or a Zeek-side script using ZeekJS to call `XADD`), the Stage 1 architecture supports a bridge swap with no consumer-side change. The payload contract on the `zeek:events` stream is what survives across bridge implementations; Vector and any future zeek-redis plugin both need to produce that same contract.

This is the same property that makes Stage 1 → Stage 2 (D → D + Channels) additive: the buffer is the integration boundary, and bridges or consumers can change independently behind it.

---

## Sources

- [sedarasecurity/zeek-redis on GitHub](https://github.com/sedarasecurity/zeek-redis)
- [mbispham/zeekjs-redis on GitHub](https://github.com/mbispham/zeekjs-redis)
- [zeekjs-redis on the Zeek package manager](https://packages.zeek.org/packages/view/30e17a1d-0904-11ef-bc0c-0a598146b5c6)
- [Zeek community: "Send logs from zeek to redis i.e. a Redis log writer" (2023)](https://community.zeek.org/t/send-logs-from-zeek-to-redis-i-e-a-redis-log-writer/6980)
- [Zeek community: "Redis Log Writer" (2015)](https://community.zeek.org/t/redis-log-writer/3687)
- [Bro 2.5.5: Bro Redis Logging legacy docs](https://old.zeek.org/manual/2.5.5/components/bro-plugins/redis/README.html)
- [Zeek Package Manager directory](https://packages.zeek.org/)
