# F-DHCP-DORA — ground truth

**Fixture:** `dhcp-dora.pcap`
**Generator:** `dhcp_dora.py`
**Source:** scapy synthesis

## Contents

A full DORA exchange — four DHCP frames:

| # | Type | Ether src → dst | IP src → dst | Notes |
|---|---|---|---|---|
| 1 | DISCOVER | client → broadcast | 0.0.0.0 → 255.255.255.255 | client has no IP yet |
| 2 | OFFER | server → client | 10.0.0.1 → 10.0.0.50 | server offers `yiaddr` |
| 3 | REQUEST | client → broadcast | 0.0.0.0 → 255.255.255.255 | client accepts offer |
| 4 | ACK | server → client | 10.0.0.1 → 10.0.0.50 | lease confirmed |

## Layer-2 ground truth

| Device | MAC | IP (after DORA) |
|---|---|---|
| client | `ca:fe:ba:be:00:42` | `10.0.0.50` (only after frame 4) |
| server | `00:50:56:0d:c0:01` | `10.0.0.1` |

**Critical property:** the client MAC appears in *two* places inside the
pcap — the L2 Ethernet `src` field of frames 1 and 3, and the BOOTP
`chaddr` payload of all four frames. The bridge can pick it up from
either. The test should not assume which.

## BOOTP `chaddr` byte layout

BOOTP allocates 16 bytes for client hardware address. We write:

```
ca fe ba be 00 42 00 00 00 00 00 00 00 00 00 00
└─── MAC ──────┘ └──── NUL padding ────────────┘
```

The `chaddr` ground-truth bytes are explicit in the script so a reviewer
can audit them without running scapy.

## DHCP transaction ID

All four frames share `xid = 0x12345678`. Real DHCP exchanges use random
xids; the fixed value here is deterministic for replay.

## What tests assert against this fixture

| Test | Assertion |
|---|---|
| **C.9** DHCP-discovered devices captured | A Stream entry containing `ca:fe:ba:be:00:42` is produced from this pcap. Critically, that entry must exist even from frame 1 (DISCOVER) where the client has no IP — the bridge must not require L3 state before emitting L2. |

## Why scapy and not capture

Capturing a real DHCP exchange is possible (e.g., `tcpdump -i eth0 port
67 or port 68`) but introduces non-determinism: the xid is random, the
server MAC is whatever your local DHCP server is, lease times vary. For
a regression fixture, synthesis gives byte-exact ground truth.

Open question for the bridge implementer: the test relies on Zeek's
`dhcp.log` being enabled. By default it is, but verify against the Zeek
version in use.

## Verifying the pcap matches this doc

```bash
tshark -r dhcp-dora.pcap | wc -l                                # → 4
tshark -T fields -e bootp.hw.mac_addr -r dhcp-dora.pcap         # → ca:fe:ba:be:00:42 ×4
tshark -T fields -e dhcp.option.dhcp -r dhcp-dora.pcap          # → 1, 2, 3, 5 (Discover, Offer, Request, Ack)
```
