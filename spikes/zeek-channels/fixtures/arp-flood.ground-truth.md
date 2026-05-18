# F-ARP-FLOOD — ground truth

**Fixture:** `arp-flood.pcap`
**Generator:** `arp_flood.py`
**Source:** scapy synthesis

## Deliberate exception from F-SUSTAINED

This fixture is a synthesis stand-in for `F-SUSTAINED` (see
`sustained-load.capture-notes.md`), used **only** for D.14
(Redis down mid-stream). F-SUSTAINED's design called for several
minutes of mixed real traffic so all four D-series tests
(D.13/D.14/D.15/D.16) could share one capture; F-ARP-FLOOD provides
exactly one of the properties F-SUSTAINED would have provided —
enough independent bridge events to produce sustained xAdd pressure
during Zeek processing time.

The substitution is deliberate, not a quiet shortcut:

- D.14 only needs xAdd cadence, not traffic shape, payload variety,
  or timing fidelity.
- D.13 (Redis down at startup), D.15 (Zeek restart), and D.16 (slow
  consumer) need behavior this fixture doesn't model — they should
  continue to use F-SUSTAINED when that capture becomes available.

Why ARP specifically: each ARP frame fires a discrete bridge event on
receipt (`arp_request` → one `xAdd`). Conn-log records batch at
`connection_state_remove`, which in offline replay fires after the
pcap completes — meaning a conn-only fixture of the same size would
produce all its xAdds in a single end-of-pcap burst, leaving no
mid-stream window to kill into.

## Contents

| Property | Value |
|---|---|
| Frames | 10000 ARP requests |
| Source MACs | 10000 unique, locally-administered (`02:00:00:00:**:**`) |
| Source IPs | 10000 unique within `10.42.0.0/16` |
| Destination MAC | `ff:ff:ff:ff:ff:ff` (broadcast) |
| Destination IP | `10.0.0.1` (target of the who-has) |
| ARP operation | `1` (request) only — no replies |

There is no per-device ground truth. The fixture is bulk-by-design.

## What tests assert against this fixture

| Test | Sub-assertion | What it catches |
|---|---|---|
| **D.14a** No silent loss | `XLEN_final + count("[bridge] xAdd failed" lines) >= FRAME_COUNT * 0.99` | The spec phrase "rather than swallowing it silently." Each ARP frame fires one xAdd; if zeek exited 0, all FRAME_COUNT xAdds happened; therefore every one must either land on the stream or surface as an error log. Anything less is a silent drop. |
| **D.14b** Graceful degradation | `zeek exit code == 0` | The bridge handles the failure without unhandled rejection or crash propagating up into Zeek. |
| **D.14c** Kill landed mid-burst | `XLEN_final < FRAME_COUNT` | Sanity guard. If the kill happened too late (zeek finished before the kill) all writes succeed and the test would vacuously pass D.14a — D.14c forces the test to actually exercise the failure path. |

D.14 passes iff all three hold. Run via
`docker/run-d14-redis-kill.sh`.

### Current state at bridge `2f1501f`

D.14b and D.14c PASS. **D.14a FAILS**: typical run reports
`silent loss: ~9996 of 10000 dropped without an error log`. Cause:
node-redis@4's offlineQueue receives the post-kill xAdds and drops
them silently when `client.quit()` runs without reconnection — only
the small set of writes already in-flight at the moment of the kill
get their `.catch()` invoked. See the comment in
`bridge/send-to-redis.js` near the `.catch()` for the fix shape
(bounded retry-strategy + explicit offlineQueue flush-and-reject).
The test is wired up and committed so the gap is visible in the
ledger; fixing it is queued as the next bridge feature, not a
prerequisite for shipping D.14 as a regression check.

## Tuning N

`FRAME_COUNT = 10000` is sized to give Zeek's offline replay ~1–2s of
processing time on modern hardware — long enough to land an external
SIGKILL at a predictable midpoint. If Zeek processes faster than that
on your host (and the orchestration script reports D.14c FAIL because
the kill landed too late), scale `FRAME_COUNT` up. The fixture has no
other fidelity constraints, so size up freely.

## Verifying the pcap matches this doc

```bash
tshark -r arp-flood.pcap | wc -l                                # → 10000
tshark -T fields -e eth.src -r arp-flood.pcap | sort -u | wc -l # → 10000
tshark -T fields -e arp.opcode -r arp-flood.pcap | sort -u      # → 1
tshark -T fields -e eth.dst -r arp-flood.pcap | sort -u         # → ff:ff:ff:ff:ff:ff
```
