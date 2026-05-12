# Bridge Decision Revisited — ZeekJS Prototype Default, Swap-In Paths Documented

**Date:** 2026-05-12
**Status:** Supersedes the operative conclusion of [bridge-investigation-findings.md](bridge-investigation-findings.md). The historical investigation in that file (which packages were checked, why each was rejected) remains accurate and is the record of work.
**Trigger:** A closer pass on Zeek's bundled JavaScript runtime and Zeek 8's Storage Framework Redis backend surfaced one option and ruled out another that the original §6.0 investigation did not separate cleanly.

---

## What changes

The original §6.0 investigation evaluated two third-party packages (`sedarasecurity/zeek-redis`, `mbispham/zeekjs-redis`), found neither wrote to Redis Streams, and concluded "no viable plugin exists → Stage 1's bridge is Vector." That conclusion collapsed two independent decision axes and missed the simplest path:

- **Axis 1 — where the buffer lives:** in-process (producer crashes lose in-flight events; no disk buffer) vs. on-disk before the bridge (Vector or Python sidecar buffers via files or a built-in disk queue).
- **Axis 2 — producer language:** C++ plugin (footprint-minimal, build-cycle slow, fork to maintain) vs. JavaScript via ZeekJS (footprint heavier, iteration fast, no fork to maintain).

These are independent. The original framing treated "no off-the-shelf plugin" as forcing the sidecar choice; it did not. **Bespoke ZeekJS — a ~30-line user script invoked as `zeek -i <iface> send-to-redis.js` — is an in-process producer that doesn't require maintaining a forked plugin.**

This doc records the revised Stage 1 default and the explicit swap-in paths.

---

## ZeekJS as the Stage 1 prototype default

**ZeekJS is bundled with Zeek as a built-in plugin since v6.0**, automatically included when Node.js development headers are present at Zeek build time. It is *not* a third-party package — it is in-tree Zeek.

Quoting the official docs: *"JavaScript support is an optional Zeek feature. When Node.js development headers and libraries are found when building Zeek from source, the plugin is automatically included."* See https://docs.zeek.org/en/master/scripting/javascript.html.

From JavaScript, a script has:

- `zeek.on('event_name', handler)` — subscribe to any Zeek event.
- `zeek.hook('Conn::log_policy', (rec, id, filter) => {...})` — observe (and optionally veto) log records with full typed-field access.
- The full npm ecosystem via embedded Node.js (`require('redis')`, etc.).
- Integrated I/O loops — Node's libuv runs interleaved with Zeek's event loop.

### Minimal Stage 1 bridge

```javascript
// send-to-redis.js
const { createClient } = require('redis');
const r = createClient({ url: 'redis://localhost:6379' });

zeek.on('zeek_init', async () => { await r.connect(); });

zeek.hook('Conn::log_policy', (rec, _id, _filter) => {
  r.xAdd('zeek:events', '*', {
    ts: String(rec.ts),
    src: rec['id.orig_h'],
    dst: rec['id.resp_h'],
    proto: rec.proto,
    service: rec.service ?? '',
    duration: String(rec.duration ?? 0),
  });
});

zeek.on('zeek_done', async () => { await r.quit(); });
```

```bash
npm install redis
zeek -C -i eth0 send-to-redis.js
```

That is the entire bridge.

### Why this is the Stage 1 default

- **Smallest code surface to validate the architecture.** ~30 lines, no new daemon, no fork to maintain.
- **Fastest iteration.** Edit `.js`, restart Zeek. No C++ rebuild cycle.
- **Native typed access to Zeek records.** No log parsing.
- **Integration boundary is unchanged.** The bridge produces `XADD` to `zeek:events`; the consumer reads via `XREADGROUP`. Whatever bridge implementation produces that contract works — bridges are swappable behind the stream.

### Costs (honest)

- **No disk buffer.** Node's `redis` client offline queue is RAM-only. If Redis is down for long, RAM fills and Zeek backs up.
- **In-process coupling.** Zeek now runtime-depends on Redis being reachable. The Node client's reconnect/offline-queue behavior needs to be verified for the deploy target.
- **Two runtimes in one process.** v8 + libuv alongside Zeek's C++. New failure modes (Node memory growth, GC pauses, swallowed promises) live inside the packet-handling process.
- **Node.js footprint at deploy.** ~50MB extra. Open whether acceptable on a small-hospital sensor.

The first three are the cost of *any* in-process producer (they apply equally to the C-plugin path). The fourth is JS-specific and is the trigger for swapping to the C-plugin path if production deploy footprint becomes binding.

---

## Storage Framework KV side-channel: evaluated, rejected

Zeek 8 ships an in-tree Redis storage backend (`policy/frameworks/storage/backend/redis`). It exposes `Storage::Sync::put` / `Storage::Sync::get` / `Storage::Sync::erase` (and async variants) — a **simple key-value store API** designed for Zeek-script-internal state ("have I seen this hostname before?").

This is **not** a log-shipping path. Treating it as a side channel for our pipeline means:

| Read mechanism downstream | What it gives | Why it breaks Option D |
|---|---|---|
| `GET` (point lookup) | Current value of a known key | We don't know the keys ahead of time — that's the thing we're trying to learn |
| `SCAN` (enumerate) | All keys matching a prefix, cursor-based | Race under concurrent writes; no "changes since last poll" semantics; transient overwrites are invisible |
| **Keyspace notifications** (`__keyspace@0__:*` pubsub) | Pubsub message per key change | **Fire-and-forget, disabled by default, lossy on reconnect.** Redis docs: *"if your Pub/Sub client disconnects, and reconnects later, all the events delivered during the time the client was disconnected are lost."* Also CPU-costly — the docs note the feature is disabled by default for that reason |

Picking the KV path means choosing Option D's architecture (durable buffer, replay, consumer groups, `XPENDING`-style observability) and then handing the bridge a transport with Option A's loss model. **It is structurally wrong for our pipeline contract.**

The Storage Framework's deliberate KV shape exists because it abstracts over SQLite / Redis / PostgreSQL backends — the framework's whole point is interchangeable backends, which constrains it to a narrow KV API. That same narrowness is why it can't be a stream.

A residual sub-use *might* exist: Zeek scripts using Storage Framework + Redis to dedupe a local "seen" set before producing to Streams. That is an optimization, not a bridge.

**Decision: Storage Framework KV is out. Not in the running for the bridge. Document it as evaluated-and-rejected so future-us doesn't re-litigate it.**

---

## C-plugin fork as production-hardening swap-in

If Node.js footprint or in-process coupling proves unacceptable in production, the swap-in is to fork `sedarasecurity/zeek-redis` and replace `redis_client->lpush(...)` with `redis_client->xadd(...)` in `src/RedisWriter.cc`.

The plugin's mechanical state, as of investigation:

- **Lifetime commits:** 7. Last functional change 2024-05-08; previous commit 2021-09-10 (~2y8mo gap before that).
- **Codebase size:** ~13.7KB total across the writer files (`Plugin.cc` 525B, `Plugin.h` 352B, `RedisWriter.cc` 10.8KB, `RedisWriter.h` 2.1KB) plus `redis.bif` (303B) and `zkg.meta` + CMake build glue.
- **Redis-write sites:** three in `DoWrite` — `sadd`, `expire`, `lpush`, all synchronous via `redis-plus-plus`.
- **The XADD swap:** one site changes. `redis-plus-plus` already supports `xadd` natively (it wraps hiredis, which does).
- **License:** BSD-3-Clause. 7 stars, 0 forks, 1 stale issue.

What "fork it" actually costs:

- **Initial patch:** ~20 lines of C++ across `RedisWriter.cc` (XADD call) and `redis.bif` (stream-key config), plus a small Zeek script policy to register the writer.
- **Build pipeline:** CMake against Zeek's plugin API, rebuilt per Zeek version. Standard Zeek plugin development; not exotic.
- **Long-term maintenance:** We become the plugin's de facto maintainer — track Zeek plugin-API changes across versions; ship binaries per Zeek release. The base plugin has not seen non-trivial activity since 2024-05.
- **Runtime deps:** hiredis (~200KB) instead of Node.js (~50MB). A real footprint win.
- **In-process failure surface:** native C++ inside Zeek. Minimal new failure modes vs. ZeekJS's v8/GC.

For a *prototype*, this is the wrong choice — build-cycle time alone slows the spike's feedback loop by ~100×, and we'd be maintaining a fork before validating the architecture works end-to-end. For *production hardening*, it is the strongest option: no Node runtime in the packet path, minimal footprint, native to Zeek's process model.

**Decision: the C plugin is the documented production-hardening swap-in. Not the starting point.**

### A note on fork base

`SeisoLLC/zeek-kafka` (Apache-2.0, last pushed 2025-08-18; ~54 stars, ~21 forks; recent commit "Fix a build warning with the latest Zeek master") is a more actively maintained plugin in the same architectural shape. If forking, consider whether to base on its structure rather than the stale `sedarasecurity/zeek-redis`, even though the destination protocol differs — the CMake glue and `zkg.meta` patterns transfer cleanly, and the Kafka client/Redis client substitution is the smaller surface.

---

## Vector as the on-disk-buffer swap-in path

Vector remains a valid swap-in path if the in-process producer's lack of disk buffering proves operationally unacceptable.

**Vector's distinctive advantage is disk-buffered durability across Redis outages.** Everything else Vector does — `XADD` to a stream, retry/backoff, observability — a ~30-line ZeekJS script or a small C-plugin patch can match.

The decision rule is environmental:

- **Reliable Redis** (single-appliance deploy, Redis on the same box, supervisor restart on failure) → disk buffer is overkill; ZeekJS or C plugin is simpler.
- **Flaky or remote Redis** (Redis on another host, multi-tenant, planned-maintenance windows that exceed Node's offline queue capacity) → disk buffer is load-bearing; Vector becomes the right answer.

For the target small-hospital sensor deploy, Redis is co-located. The disk buffer is overkill at Stage 1. If deployment topology evolves (multi-sensor cluster, remote Redis), revisit.

---

## Two independent decision axes

The tradeoff to recognize explicitly:

| Axis | Choice | Implication |
|---|---|---|
| **Buffer location** | In-process (ZeekJS / C plugin) vs. on-disk before bridge (Vector / Python sidecar) | Durability when Redis is unreachable |
| **Producer language** | C++ plugin vs. JavaScript via ZeekJS | Runtime footprint, iteration speed, maintenance burden |

The original §6.0 conclusion collapsed both — it found no off-the-shelf plugin and jumped to Vector. The right framing is:

- Choose **buffer location** based on Redis reliability in the deploy environment.
- Choose **producer language** based on iteration-speed and footprint constraints.

For the spike's Stage 1 prototype, in-process + JavaScript (ZeekJS) wins on both axes — until we have a deploy environment that forces one of the swap-in paths.

---

## Side-by-side: candidate bridges for Option D

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
| **Suits Stage 1 prototype** | ★ best | Worst | Wrong shape | Heavy | Medium |
| **Suits hardened production** | OK with coupling caveats | **Strong** | No | **Strong** | Strong |

---

## Revised Stage 1 plan

**Prototype with ZeekJS.** Validate the rest of the pipeline (consumer, stream contract, Postgres materialization, dead-letter handling) end-to-end against real Zeek output as fast as possible.

**Hold two swap-in paths in reserve, both of which leave the consumer unchanged:**

- **If Node footprint or in-process coupling proves unacceptable in production:** fork `sedarasecurity/zeek-redis` (or rebase on `SeisoLLC/zeek-kafka`'s better-maintained structure), swap `LPUSH` for `XADD`. ~20-line C++ patch. Pipeline unchanged.
- **If Redis-downtime tolerance matters more than in-process simplicity:** swap ZeekJS for Vector. Pipeline unchanged.

The integration boundary is the payload contract on `zeek:events`. Bridges can be swapped without changing the consumer.

**Reject explicitly:** Storage Framework KV as a side channel. The KV shape is structurally incompatible with Option D's durability properties.

---

## What this means for the implementer

If you arrived here looking for "what do I build for Stage 1?":

1. Write `send-to-redis.js` (~30 lines) — see the example above.
2. Run `zeek -C -i <iface> send-to-redis.js` against a fixture pcap or a test interface.
3. Implement the Django consumer (`python manage.py zeek_stream_consume`) reading from `zeek:events` via `XREADGROUP` in group `blueflow-ingest`.
4. Verify the end-to-end shape against open questions §6.1–§6.5 in [decision-option-d-two-stage-rollout.md](decision-option-d-two-stage-rollout.md) before declaring Stage 1 prototype complete.

If at any point the production constraints rule out the JS runtime in-process: the C-plugin path is a documented ~20-line patch against a known plugin. If the deploy environment demands disk-buffered durability: Vector is the swap-in. Neither changes the consumer.

---

## Sources

- [ZeekJS upstream](https://github.com/corelight/zeekjs)
- [JavaScript — Book of Zeek (master)](https://docs.zeek.org/en/master/scripting/javascript.html)
- [Zeek Storage Framework docs](https://docs.zeek.org/en/master/frameworks/storage.html)
- [Storage Framework Redis backend policy](https://docs.zeek.org/en/master/scripts/policy/frameworks/storage/backend/redis/main.zeek.html)
- [Zeek's Storage Framework Explained (zeek.org blog)](https://zeek.org/2025/09/zeeks-storage-framework-explained/)
- [Redis keyspace notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
- [sedarasecurity/zeek-redis (C++ plugin)](https://github.com/sedarasecurity/zeek-redis)
- [SeisoLLC/zeek-kafka (better-maintained reference for plugin structure)](https://github.com/SeisoLLC/zeek-kafka)
- [node-redis client](https://github.com/redis/node-redis)
