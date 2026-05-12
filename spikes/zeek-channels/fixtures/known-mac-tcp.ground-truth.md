# F-IPV4-TCP — ground truth

**Fixture:** `known-mac-tcp.pcap`
**Generator:** `known_mac_tcp.py`
**Source:** scapy synthesis (byte-exact)

## Contents

Three frames — a single TCP handshake, no data, no close:

| # | Direction | Flags |
|---|---|---|
| 1 | client → server | SYN |
| 2 | server → client | SYN-ACK |
| 3 | client → server | ACK |

## Layer-2 ground truth

| Device | MAC | IP |
|---|---|---|
| client | `00:11:22:33:44:55` | `192.168.1.10` |
| server | `66:77:88:99:aa:bb` | `192.168.1.20` |

Both MACs are unicast. The client MAC is globally-administered (`00` =
`0b00000000`); the server MAC has the locally-administered bit set
(`66` = `0b01100110`). Tests should not depend on either property — this
fixture is the canonical "two ordinary devices" case.

## What tests assert against this fixture

| Test | Assertion |
|---|---|
| **B.4** MAC addresses arrive intact | `00:11:22:33:44:55` appears in the Stream entry unchanged — same byte order, same case, no truncation |
| **B.5** Both src/dst MACs captured | The Stream entry for the conn record contains *both* `00:11:22:33:44:55` and `66:77:88:99:aa:bb` (the bridge does not drop one side) |
| **F.20** Replayed traffic produces consistent output | Two independent replays produce identical Stream entries (same MAC fields, same count) |

## Why byte-exact matters here

The point of synthesizing this fixture (rather than capturing) is that we
*chose* the MAC bytes. B.4 asserts the exact byte sequence round-trips. If
the bridge silently lowercases, strips colons, reorders octets, or pads,
the assertion fails with a known-good expected value.

## Verifying the pcap matches this doc

```bash
tshark -r known-mac-tcp.pcap | wc -l                          # → 3
tshark -T fields -e eth.src -e eth.dst -r known-mac-tcp.pcap  # → both MACs in each row
tshark -T fields -e tcp.flags -r known-mac-tcp.pcap           # → S, SA, A
```
