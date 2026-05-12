# F-MULTICAST-MAC — ground truth

**Fixture:** `multicast-dest.pcap`
**Generator:** `multicast_dest.py`
**Source:** scapy synthesis

## Contents

Three frames, each targeting a different multicast MAC family:

| # | Protocol | Ether dst | IP dst | Why this family matters |
|---|---|---|---|---|
| 1 | mDNS query | `01:00:5e:00:00:fb` | `224.0.0.251` | mDNS/Bonjour — common on every Apple/Linux LAN |
| 2 | LLMNR query | `01:00:5e:00:00:fc` | `224.0.0.252` | Windows name resolution fallback |
| 3 | IPv6 NS | `33:33:00:00:00:01` | `ff02::1` | IPv6 link-local discovery |

## Layer-2 ground truth

| Field | Value |
|---|---|
| Source MAC (all frames) | `a4:b1:c2:d3:e4:f5` |
| mDNS dest MAC | `01:00:5e:00:00:fb` |
| LLMNR dest MAC | `01:00:5e:00:00:fc` |
| IPv6 all-nodes dest MAC | `33:33:00:00:00:01` |

## Multicast MAC family encoding (background)

- `01:00:5e:**:**:**` is the IPv4 multicast prefix; the low 23 bits of the
  MAC mirror the low 23 bits of the multicast IPv4 address. `224.0.0.251`
  → `01:00:5e:00:00:fb` (low 24 bits of `224.0.0.251` are `00:00:fb`,
  with the top bit cleared to fit 23-bit window).
- `33:33:**:**:**:**` is the IPv6 multicast prefix; the low 32 bits of
  the MAC mirror the low 32 bits of the multicast IPv6 address.

If the bridge "helpfully" reverses this derivation or replaces multicast
destinations with the underlying IP, this fixture surfaces the bug.

## What tests assert against this fixture

| Test | Assertion |
|---|---|
| **B.7** Special MAC types round-trip correctly (multicast slice) | All three destination MACs (`01:00:5e:00:00:fb`, `01:00:5e:00:00:fc`, `33:33:00:00:00:01`) appear verbatim in the Stream — not translated to the underlying multicast IP, not collapsed to `multicast`, not normalized to lowercase-with-hyphens, not dropped. |

## Verifying the pcap matches this doc

```bash
tshark -T fields -e eth.dst -r multicast-dest.pcap
# → 01:00:5e:00:00:fb
#   01:00:5e:00:00:fc
#   33:33:00:00:00:01

tshark -T fields -e eth.src -r multicast-dest.pcap | sort -u
# → a4:b1:c2:d3:e4:f5
```
