# F-LOCAL-ADMIN — ground truth

**Fixture:** `randomized-mac.pcap`
**Generator:** `randomized_mac.py`
**Source:** scapy synthesis

## Contents

A standard three-frame TCP handshake. The bit pattern of the source MAC
is the only thing this fixture exists to exercise — the L4 traffic shape
is incidental.

| # | Direction | Flags |
|---|---|---|
| 1 | privacy device → peer | SYN |
| 2 | peer → privacy device | SYN-ACK |
| 3 | privacy device → peer | ACK |

## Layer-2 ground truth

| Device | MAC | Bit-1 of first byte | Meaning |
|---|---|---|---|
| privacy device | `02:1a:2b:3c:4d:5e` | `1` | **locally administered** |
| peer | `00:1b:21:00:00:01` | `0` | globally administered (Intel OUI) |

First-byte breakdown for `02`:

```
  0x02 = 0b00000010
                ^^
                |+-- bit-0 = 0 → unicast (not multicast)
                +--- bit-1 = 1 → locally administered
```

## Why this MAC, specifically

`02:1a:2b:3c:4d:5e` is a representative privacy MAC — it's the shape
recent iOS and Android devices emit when "private Wi-Fi address" or
"MAC randomization" is on. The bridge must treat it as a normal MAC.

## What tests assert against this fixture

| Test | Assertion |
|---|---|
| **B.7** Special MAC types round-trip correctly (locally-administered slice) | `02:1a:2b:3c:4d:5e` appears in the Stream entry unchanged — not flagged as invalid, not normalized to `*:1a:2b:3c:4d:5e`, not dropped, not silently rewritten with the locally-administered bit cleared. |

## Forward-looking note for the Asset model

Privacy MACs are non-stable identifiers — the same physical device emits
a different one per SSID (and rotates them periodically). This fixture
tests *capture fidelity* only. Asset-model dedup against privacy MACs is
a separate concern handled downstream of the bridge.

## Verifying the pcap matches this doc

```bash
tshark -T fields -e eth.src -r randomized-mac.pcap | sort -u
# → 00:1b:21:00:00:01
#   02:1a:2b:3c:4d:5e

# Confirm bit-1 of the first byte of the privacy MAC is set:
python -c "print(bin(0x02))"   # → 0b10
```
