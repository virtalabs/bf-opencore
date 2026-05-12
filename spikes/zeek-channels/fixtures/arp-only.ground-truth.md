# F-ARP-ONLY — ground truth

**Fixture:** `arp-only.pcap`
**Generator:** `arp_only.py`
**Source:** scapy synthesis

## Contents

Two ARP frames, nothing else:

| # | Type | Ether src | Ether dst | ARP psrc | ARP pdst |
|---|---|---|---|---|---|
| 1 | who-has request | `de:ad:be:ef:00:01` | `ff:ff:ff:ff:ff:ff` | `10.0.0.5` | `10.0.0.1` |
| 2 | is-at reply | `00:50:56:c0:00:01` | `de:ad:be:ef:00:01` | `10.0.0.1` | `10.0.0.5` |

## Layer-2 ground truth

| Device | MAC | Role |
|---|---|---|
| target device | `de:ad:be:ef:00:01` | The "ARP-only" device under test |
| gateway | `00:50:56:c0:00:01` | Responds to the who-has |

**Critical invariant:** `de:ad:be:ef:00:01` appears in the pcap *only*
inside ARP frames. There are zero IP-layer frames from this MAC. That's
what makes this fixture meaningful — a device that would be invisible to
a conn-log-only consumer.

## What tests assert against this fixture

| Test | Assertion |
|---|---|
| **C.8** ARP-only devices captured | A Stream entry containing `de:ad:be:ef:00:01` is produced from this pcap, despite there being no IP-layer traffic from that device. The bridge must consume Zeek's `arp.log` (or equivalent), not just `conn.log`. |

## Why this fixture isn't captured from a real network

Real-network captures often pick up incidental traffic from the same MAC
(e.g., the device sends an mDNS query 30 seconds after the ARP, or a
stale conn entry survives). For C.8 to validate "ARP-only path works,"
the fixture must guarantee there is **no** IP traffic from the device —
something only synthesis can promise.

## Open question for the bridge implementer

C.8 requires the bridge to subscribe to Zeek's `arp.log`. By default,
`arp.log` isn't enabled — it needs `@load policy/protocols/arp` (or
similar; verify against the Zeek version in use). The fixture is correct
regardless, but the bridge's Zeek script must be configured to see ARP.

## Verifying the pcap matches this doc

```bash
tshark -r arp-only.pcap | wc -l                       # → 2
tshark -T fields -e arp.opcode -r arp-only.pcap       # → 1, 2
tshark -Y "ip" -r arp-only.pcap                       # → empty (no IP frames)
```
