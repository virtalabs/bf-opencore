# F-LOOPBACK — ground truth

**Fixture:** `loopback-no-l2.pcap`
**Generators:** `loopback_no_l2.py` (scapy fallback) **or** capture (preferred)
**Sources:** scapy synthesis with `DLT_NULL`, or `tcpdump -i lo` on a host

See `loopback-no-l2.capture-notes.md` for the preferred capture method.

## Contents

Four IP frames over the BSD loopback linktype:

| # | Direction | Flags |
|---|---|---|
| 1 | 127.0.0.1 → 127.0.0.1 | SYN |
| 2 | 127.0.0.1 → 127.0.0.1 | SYN-ACK |
| 3 | 127.0.0.1 → 127.0.0.1 | ACK |
| 4 | 127.0.0.1 → 127.0.0.1 | PSH-ACK with `hello` payload |

When captured rather than synthesized, the exact payload and frame count
will differ — what matters is that the *linktype* is DLT_NULL (or
DLT_LINUX_SLL / DLT_LINUX_SLL2 on Linux). The L2-field assertion is
linktype-derived, not content-derived.

## Layer-2 ground truth

**There is no Layer-2 ground truth.** That's the point. The pcap's
linktype is `DLT_NULL` (value `0`) instead of `DLT_EN10MB` (value `1`),
which means there are no Ethernet headers. Zeek records derived from
these frames will have empty / unset `orig_l2_addr` / `resp_l2_addr`
(or equivalent) fields.

| Field | Value |
|---|---|
| pcap linktype | `DLT_NULL` = 0 (BSD loopback) — synth path |
| pcap linktype | `DLT_LINUX_SLL` / `DLT_LINUX_SLL2` — Linux capture path |
| Source MAC | *unset / missing* |
| Destination MAC | *unset / missing* |
| Source IP | `127.0.0.1` |
| Destination IP | `127.0.0.1` |

## What tests assert against this fixture

| Test | Assertion |
|---|---|
| **B.6** Empty / missing L2 fields handled | The bridge produces a Stream entry for each Zeek record without crashing. The L2 fields in those entries are represented consistently — same shape every time, recognizable as "missing" (e.g., `null`, empty string, or a documented sentinel), not "zero" (e.g., `00:00:00:00:00:00`) which would be ambiguous with a wire MAC. |

The bridge's contract for "missing" must be picked deliberately. Common
options and the tradeoff:

- **`null`** — JSON-y, easy to filter on. Most downstream-friendly.
- **Empty string `""`** — easy to produce. Ambiguous with "we tried but
  got nothing."
- **Sentinel `"00:00:00:00:00:00"`** — would collide with any device on
  the wire that emits a zero MAC (rare but possible during boot).

Recommendation for the bridge: **`null`**. The test in this fixture
verifies whatever sentinel is picked is applied consistently.

## Why synth is a fallback rather than primary

scapy can write `DLT_NULL` pcaps via `PcapWriter(linktype=0)`, but:

- The wrapper around `wrpcap` has to be replaced with `PcapWriter`, and
  the `Loopback()` layer has to substitute for the missing `Ether()`.
- The synth path produces a pcap that *looks* like a loopback capture
  but isn't one — if Zeek treats some specific Linux-loopback edge case
  differently than BSD-loopback (e.g., DLT_LINUX_SLL2 cooked-mode
  artifacts), the synth fixture won't catch it.

The captured pcap is closer to production behavior. Use synth only when
capture is impractical.

## Verifying the pcap matches this doc

```bash
# Linktype confirmation — should NOT be EN10MB
capinfos loopback-no-l2.pcap | grep -i "data link"
# → Data link type: NULL (synth) or LINUX_SLL2 (Linux capture)

tshark -r loopback-no-l2.pcap | wc -l
# → 4 (synth path) or whatever the capture session produced

# Confirm no Ethernet layer:
tshark -V -c 1 -r loopback-no-l2.pcap | head -20
# → first protocol after "Frame" should be IP, not Ethernet II
```
