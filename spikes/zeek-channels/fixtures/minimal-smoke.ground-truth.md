# F-MINIMAL — ground truth

**Fixture:** `minimal-smoke.pcap`
**Generator:** `minimal_smoke.py`
**Source:** scapy synthesis (byte-exact)

## Contents

A single TCP exchange, five frames total:

| # | Direction | Flags | Notes |
|---|---|---|---|
| 1 | A → B | SYN | client opens |
| 2 | B → A | SYN-ACK | server replies |
| 3 | A → B | ACK | client completes handshake |
| 4 | A → B | PSH-ACK | client sends `GET / HTTP/1.0\r\n\r\n` |
| 5 | A → B | FIN-ACK | client closes |

## Layer-2 ground truth

| Device | MAC | IP |
|---|---|---|
| A (client) | `aa:bb:cc:00:00:01` | `10.0.0.10` |
| B (server) | `aa:bb:cc:00:00:02` | `10.0.0.20` |

Both MACs are unicast. They happen to have the locally-administered bit set
(`aa` = `0b10101010`), but the bit pattern is not significant for this
fixture — F-LOCAL-ADMIN exists to test that bit specifically.

## What tests assert against this fixture

| Test | Assertion |
|---|---|
| **A.2** Bridge produces something | At least one entry appears on the Redis Stream after replay |
| **A.3** Stream reachable from a separate consumer | Same entries are readable from a second client |
| **E.17** Stream depth visible | `XLEN` / `XINFO` returns a predictable, non-zero count |

Frame count is small and deterministic, which is the whole point — tests
that assert "depth grew by N" need a known N.

## Verifying the pcap matches this doc

```bash
tshark -r minimal-smoke.pcap | wc -l                          # → 5
tshark -T fields -e eth.src -r minimal-smoke.pcap | sort -u   # → 2 MACs
tshark -T fields -e tcp.flags -r minimal-smoke.pcap           # → S, SA, A, PA, FA
```
