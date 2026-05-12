# F-MIXED-L2-EMPTY — ground truth

**Fixture:** `mixed-l2-empty.pcap`
**Generator:** `mixed_l2_empty.py` (composite via `mergecap`)
**Source:** combination of `known-mac-tcp.pcap` × 9 and `loopback-no-l2.pcap` × 1

## How the ratio is computed

The L2-empty fraction is the load-bearing property of this fixture — the
test (E.18) needs a known number to compare the bridge's reported
empty-L2 rate against.

Assuming both prerequisite pcaps match their respective ground-truth
docs and no capture-path divergence on F-LOOPBACK:

| Input | Frames per copy | Copies | Subtotal | Type |
|---|---|---|---|---|
| `known-mac-tcp.pcap` | 3 | 9 | 27 | L2-bearing |
| `loopback-no-l2.pcap` (synth path) | 4 | 1 | 4 | L2-empty |

**Totals (synth path):**

- Total frames: **31**
- L2-empty frames: **4**
- L2-empty fraction: **4 / 31 ≈ 12.9 %**

The plan asked for a 90/10 target. 87.1/12.9 is what you actually get
from "9 × IPv4 + 1 × loopback." Close enough — the test threshold
should be set against the **measured** ratio, not the aspirational one.

## If F-LOOPBACK was captured rather than synthesized

If `loopback-no-l2.pcap` came from a real `tcpdump -i lo` session, its
frame count will differ. Recompute and update this doc:

```bash
LOOPBACK_FRAMES=$(tshark -r loopback-no-l2.pcap 2>/dev/null | wc -l)
IPV4_FRAMES=$((3 * 9))
TOTAL=$((IPV4_FRAMES + LOOPBACK_FRAMES))
echo "L2-empty fraction: $LOOPBACK_FRAMES / $TOTAL"
```

The fraction in *this doc* must match the fraction in *this pcap*. If
F-LOOPBACK is regenerated, regenerate this fixture and update the
numbers above.

## What tests assert against this fixture

| Test | Assertion |
|---|---|
| **E.18** Empty-L2 rate detectable | The bridge (or a side channel) reports an empty-L2 fraction that matches the documented ground truth within a stated tolerance. A high empty rate is the canonical signal that capture is broken or the hook is buggy — the test verifies that signal exists and is measurable. |

## Why we don't try harder to hit exactly 90/10

The plan called for the option of duplicating inputs to hit a target
ratio. We could split F-LOOPBACK into fewer frames (e.g., 3 instead of
4) to get 27/3 = 90/10 exactly. But:

- The 3-frame loopback variant requires either editing the script or
  capturing exactly 3 frames, both of which are fiddlier than just
  documenting whatever ratio falls out.
- The test asserts "the bridge can *see* the rate accurately," not "the
  rate is exactly 10%." Documented ground truth at 12.9% serves the same
  testing purpose.

## Verifying the pcap matches this doc

```bash
# Total frame count
tshark -r mixed-l2-empty.pcap | wc -l

# Frames that have an Ethernet layer (L2-bearing)
tshark -Y "eth" -r mixed-l2-empty.pcap | wc -l

# Frames without an Ethernet layer (loopback)
tshark -Y "not eth" -r mixed-l2-empty.pcap | wc -l

# Linktype mix
capinfos mixed-l2-empty.pcap | grep -i "data link"
```

**Note on mergecap mechanics:** mergecap interleaves by timestamp. All
synthesized frames in our inputs have timestamp 0, so the merged output
will clump the inputs rather than interleave them across the timeline.
That's fine for E.18 — the ratio is what matters, not the ordering.
