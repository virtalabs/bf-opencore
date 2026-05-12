# F-BROADCAST-MAC — ground truth

**Fixture:** `broadcast-dest.pcap`
**Generator:** `broadcast_dest.py`
**Source:** scapy synthesis

## Contents

Two frames, both with Ethernet `dst = ff:ff:ff:ff:ff:ff`:

| # | Type | Ether src → dst | Purpose |
|---|---|---|---|
| 1 | DHCP DISCOVER | `12:34:56:78:9a:bc` → `ff:ff:ff:ff:ff:ff` | classic L3 broadcast |
| 2 | Gratuitous ARP | `12:34:56:78:9a:bc` → `ff:ff:ff:ff:ff:ff` | classic L2 broadcast |

## Layer-2 ground truth

| Field | Value |
|---|---|
| Client (source) MAC | `12:34:56:78:9a:bc` |
| Destination MAC | `ff:ff:ff:ff:ff:ff` (both frames) |
| Client IP (gratuitous ARP) | `192.168.10.42` |

## What tests assert against this fixture

| Test | Assertion |
|---|---|
| **B.7** Special MAC types round-trip correctly (broadcast slice) | `ff:ff:ff:ff:ff:ff` appears in the Stream entry's destination-MAC field exactly as `ff:ff:ff:ff:ff:ff` — not lowercased to oblivion, not converted to `<broadcast>`, not stripped, not silently replaced with `null` or empty. |

## Why both DHCP and gratuitous ARP

The two frames cover two different code paths in Zeek:

- **DHCP DISCOVER** lands in `dhcp.log`, so the bridge picks up the
  broadcast MAC via the DHCP path.
- **Gratuitous ARP** lands in `arp.log` (when enabled), so the bridge
  picks up the broadcast MAC via the ARP path.

If the bridge normalizes broadcast destinations in one path but not the
other, this fixture will surface that asymmetry.

## Verifying the pcap matches this doc

```bash
tshark -T fields -e eth.dst -r broadcast-dest.pcap   # → ff:ff:ff:ff:ff:ff ×2
tshark -T fields -e eth.src -r broadcast-dest.pcap   # → 12:34:56:78:9a:bc ×2
```
