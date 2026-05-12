# Zeek L2 pipeline — pcap fixtures

Generators and ground-truth sidecars for the pcap fixtures called out in
`/tmp/zeek-l2-pipeline-tests.md` and `/tmp/zeek-l2-pipeline-fixture-generation.md`.

The `.pcap` outputs themselves are **not** checked in — the scripts are
canonical. Regenerate before use.

## What's here

| File | Kind | Purpose |
|---|---|---|
| `minimal_smoke.py` | Generator | F-MINIMAL — 5-frame TCP exchange |
| `known_mac_tcp.py` | Generator | F-IPV4-TCP — SYN/SYN-ACK/ACK with known MACs |
| `arp_only.py` | Generator | F-ARP-ONLY — ARP-only device |
| `dhcp_dora.py` | Generator | F-DHCP-DORA — DHCP Discover/Offer/Request/Ack |
| `broadcast_dest.py` | Generator | F-BROADCAST-MAC — ff:ff:ff:ff:ff:ff destinations |
| `multicast_dest.py` | Generator | F-MULTICAST-MAC — 01:00:5e:* + 33:33:* destinations |
| `randomized_mac.py` | Generator | F-LOCAL-ADMIN — locally-administered source MAC |
| `loopback_no_l2.py` | Generator | F-LOOPBACK — DLT_NULL pcap (synth path; capture preferred) |
| `mixed_l2_empty.py` | Generator | F-MIXED-L2-EMPTY — composite via mergecap |
| `<name>.ground-truth.md` | Sidecar | What each fixture's downstream tests should assert |
| `<name>.capture-notes.md` | Sidecar | Capture instructions for fixtures that can't be synthesized cleanly |

The three capture-required fixtures (F-MULTI-DEVICE, F-VLAN-TAGGED,
F-SUSTAINED) live only as `.capture-notes.md` here — they need real wire
access to produce.

## Install

Scapy is gated behind the `pcap-fixtures` optional-dependencies group so it
doesn't bloat the runtime install. From the repo root:

```bash
uv sync --extra pcap-fixtures
```

`F-MIXED-L2-EMPTY` additionally shells out to `mergecap` (from the
wireshark/tshark package — `brew install wireshark` on macOS).

## Regenerate everything

```bash
cd spikes/zeek-channels/fixtures
uv run python minimal_smoke.py
uv run python known_mac_tcp.py
uv run python arp_only.py
uv run python dhcp_dora.py
uv run python broadcast_dest.py
uv run python multicast_dest.py
uv run python randomized_mac.py
uv run python loopback_no_l2.py
uv run python mixed_l2_empty.py   # depends on known_mac_tcp + loopback_no_l2 having run
```

Each generator writes its pcap next to itself and exits silently on success.
Failure surfaces as an unhandled scapy exception.

## Verify a fixture

Generators are deliberately silent so they stay ruff-clean. To confirm a
fixture matches its sidecar, use `tshark`:

```bash
# Frame count
tshark -r minimal-smoke.pcap | wc -l

# Source MACs present
tshark -T fields -e eth.src -r minimal-smoke.pcap | sort -u

# Full decode of one frame
tshark -V -c 1 -r minimal-smoke.pcap
```

The `<name>.ground-truth.md` sidecar for each fixture lists the exact MAC
addresses, frame count, and per-test assertion targets.

## Why scripts and not committed pcaps?

The fixture-generation plan (`/tmp/zeek-l2-pipeline-fixture-generation.md`,
"Notes and open items") settled this:

- Scripts regenerate after scapy layer-constructor changes.
- Scripts make the "ground truth" diff-readable in code review.
- Pcaps in a binary diff look identical even when meaningful content changed.

Once the test harness lands, we may revisit and commit the pcaps too so CI
doesn't need scapy. For now, scripts are the source of truth.

## Capture-required fixtures

`multi-device-broadcast-domain.capture-notes.md`,
`vlan-trunk.capture-notes.md`, and `sustained-load.capture-notes.md` document
how to acquire those fixtures from real networks — they can't be cleanly
synthesized (see the plan doc's "NOT practically generatable" section for why).

`loopback-no-l2.capture-notes.md` documents the **preferred** capture path
for F-LOOPBACK; the scapy script is provided as a fallback but the captured
version is more authentic.
