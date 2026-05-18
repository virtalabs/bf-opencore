# Stage 1 bridge — smoke-test docker compose

Brings up Redis + a Zeek container with the ZeekJS bridge loaded, against
the F-MINIMAL pcap fixture. Covers smoke tests A.1 / A.2 / A.3 from
[`/tmp/zeek-l2-pipeline-tests.md`](../../../tmp).

## Prerequisites

1. Generate F-MINIMAL — it's gitignored and the compose bind-mounts it:

   ```bash
   cd spikes/zeek-channels/fixtures
   uv run python minimal_smoke.py
   ```

2. Docker Desktop (or equivalent) running.

## Run

From `spikes/zeek-channels/`:

```bash
docker compose build         # one-time; rebuilds when Dockerfile changes
docker compose up            # foreground: see Zeek + bridge logs interleaved
```

Zeek replays the pcap, the bridge writes to the `zeek:events` stream,
then Zeek exits. The `redis` service stays up.

## Verify (A.2 / A.3)

In a second terminal:

```bash
# How many entries did the bridge write?
docker compose exec redis redis-cli XLEN zeek:events

# Read them all back (separate-consumer reachability — A.3)
docker compose exec redis redis-cli XRANGE zeek:events - +
```

F-MINIMAL is a 5-frame TCP exchange; Zeek collapses it into a single
conn-log record, so expect `XLEN` of 1.

## Verify (A.1, bridge-starts-cleanly)

A.1 is satisfied by a clean Zeek exit + no errors on stderr after
`docker compose up`:

```bash
docker compose up --exit-code-from zeek
echo "Zeek exit: $?"          # should print 0
```

A `[bridge] connected to ...` log line on stdout confirms the JS loaded
and the Node redis client reached steady state.

## Teardown

```bash
docker compose down -v        # -v also drops the named/anonymous volumes
```

## Known assumptions to validate on first run

- **`zeek/zeek:latest` bundles ZeekJS.** If `docker compose up` errors
  with "unable to load script" or similar, the base image was built
  without Node headers. Fix in `Dockerfile.zeek`:

  ```dockerfile
  RUN zkg install --force zeekjs
  ```

- **Node redis client version.** Pinned to `^4.7.0`. Older 3.x lacks
  promise-based `xAdd`.

## D.14 — Redis down mid-stream

Orchestration script under `docker/run-d14-redis-kill.sh`. Requires
the `arp-flood.pcap` fixture (generate via
`fixtures/arp_flood.py`). The script brings up redis, runs zeek
against the flood in the background, SIGKILLs redis once the bridge
has connected, and asserts three things: zeek exited cleanly, the
kill landed mid-burst, and **no silent loss** (every dropped xAdd
either landed on the stream or surfaced as `[bridge] xAdd failed`).

The third assertion currently FAILS against bridge `2f1501f`: under
sustained redis loss the node-redis@4 offlineQueue silently drops
~99% of queued commands. See `docs/test-status.md` (row D.14, and
the **OPEN** entry under "Bugs surfaced") and the comment in
`bridge/send-to-redis.js` near the `.catch()` for the failure
mechanism and the fix shape.

## Next steps (not yet built)

- B-series fidelity tests (MAC round-trip): **done** at `a22da90` —
  see `docs/test-status.md`.
- D-series resilience tests: D.14 wired up (currently failing — see
  above). D.13/D.15/D.16 still need the capture-required `F-SUSTAINED`
  fixture (see `fixtures/sustained-load.capture-notes.md`).
- The pytest harness that drives this compose programmatically.
