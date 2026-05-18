# Zeek L2 pipeline — test status

Running ledger for the L2 pipeline spike's tests. The per-fixture
assertions are specified in the `fixtures/*.ground-truth.md` sidecars;
the master test plan that enumerated all series (A/B/C/D/E/F) lived at
`/tmp/zeek-l2-pipeline-tests.md` and was lost when /tmp cleared. The
numbering holes below reflect that loss — see "Gaps" at the bottom.

Status values:

- `pass` — verified against the commit listed
- `fail` — failed at the commit listed; see Notes for the surfaced bug
- `not run` — has a sidecar spec, has never been executed
- `spec missing` — referenced only indirectly; no sidecar yet

When updating: always cite the commit short hash in "Verified". Don't
promote `not run` to `pass` based on indirect evidence — re-run the test.

## A-series — bridge plumbing

| Test | Fixture | Status | Verified | Notes |
|---|---|---|---|---|
| A.1 | F-MINIMAL | pass | `a52bcbf` | Zeek exits 0, bridge logs `connected`, no stderr errors. Documented in `docker/README.md`. |
| A.2 | F-MINIMAL | pass | `a52bcbf` | `XLEN zeek:events` = 1 after replay. |
| A.3 | F-MINIMAL | pass | `a52bcbf` | `XRANGE` from a second `redis-cli` client returns the entry. |

## B-series — L2 / MAC fidelity

| Test | Fixture | Status | Verified | Notes |
|---|---|---|---|---|
| B.4 | F-IPV4-TCP | pass | `a22da90` | `00:11:22:33:44:55` round-trips byte-exact (case, colons, no truncation). |
| B.5 | F-IPV4-TCP | pass | `a22da90` | Both src and dst MACs present on the single entry. |
| B.6 | F-LOOPBACK | pass | `a22da90` | DLT_NULL pcap produces a conn-log entry with `src_mac=""` and `dst_mac=""`. Empty string is in the sidecar's accepted-sentinel list and is distinct from `00:00:00:00:00:00`. Sidecar *recommends* `null` over empty string for downstream filtering ergonomics — see "Bridge conventions" below. |
| B.7 | F-BROADCAST-MAC | pass | `a22da90` | `ff:ff:ff:ff:ff:ff` verbatim in dst_mac of the DHCP-DISCOVER conn entry. The gratuitous-ARP frame produces no conn record (bridge only hooks `Conn::log_policy`), so the broadcast assertion is satisfied solely via the DHCP path. |
| B.7 | F-MULTICAST-MAC | pass | `a22da90` | All three dst MACs verbatim across three conn entries: `01:00:5e:00:00:fb` (mDNS, udp), `01:00:5e:00:00:fc` (LLMNR, udp), `33:33:00:00:00:01` (IPv6 NS, icmp). |
| B.7 | F-LOCAL-ADMIN | pass | `a22da90` | `02:1a:2b:3c:4d:5e` verbatim — locally-administered bit (bit-1 of first byte) preserved, not rewritten, not flagged. |

## C-series — non-conn-log L2 sources

| Test | Fixture | Status | Verified | Notes |
|---|---|---|---|---|
| C.8 | F-ARP-ONLY | not run | — | Expected to fail at current head: bridge only hooks `Conn::log_policy`, doesn't consume `arp.log`. Running it would confirm and pin the gap. |
| C.9 | F-DHCP-DORA | not run | — | Bridge must emit even for the DISCOVER frame where the client has no L3. Likely passes for the conn-log entry produced for the later DHCP frames; the "from frame 1" assertion may fail. |

## D-series — resilience

| Test | Fixture | Status | Verified | Notes |
|---|---|---|---|---|
| D.* | — | spec missing | — | Master plan called out D as "Redis offline mid-replay surfaces the error, not swallows it" (per `docker/README.md` Next steps). Individual D.N test IDs are not reconstructable from the sidecars. |

## E-series — visibility / metrics

| Test | Fixture | Status | Verified | Notes |
|---|---|---|---|---|
| E.17 | F-MINIMAL | pass | `a52bcbf` | Implicitly verified alongside A.2 — `XLEN` returns a predictable non-zero count. |
| E.18 | F-MIXED-L2-EMPTY | not run | — | Bridge or side channel reports an empty-L2 fraction within tolerance. Requires bridge instrumentation that doesn't exist yet. |

## F-series — replay / consistency

| Test | Fixture | Status | Verified | Notes |
|---|---|---|---|---|
| F.20 | F-IPV4-TCP | pass | `a22da90` | Two replays produce identical entries modulo Redis Stream ID and Zeek's per-run random `uid`. |

## Bugs surfaced (chronological)

Cross-reference for which test runs surfaced which bridge fixes:

| Commit | Surfaced by | Bug |
|---|---|---|
| `2e4ee21` | A.1/A.2/A.3 first run | Bridge accessed `id$orig_h` flat; needed nested `rec.id.orig_h`. |
| `a52bcbf` | A.1/A.2/A.3 follow-up | Bridge silently wrote empty entries when required fields were missing; now validates and drops loudly. |
| `a22da90` | B.4/B.5 first run | Bridge accessed `id$orig_l2_addr` nested; mac-logging actually puts MACs flat on `Conn::Info` — mirror image of `2e4ee21`. |

Pattern worth tracking: every new fixture has surfaced a field-shape
assumption the bridge got wrong. A canonical conn-log schema (or even a
small JSON Schema) co-owned by the bridge and the Django consumer would
collapse this class of bug.

## Bridge conventions established by these runs

- **Missing-MAC sentinel = empty string `""`.** The bridge emits `""` for
  `orig_l2_addr` / `resp_l2_addr` when they aren't populated (e.g.,
  DLT_NULL pcaps, or runs without `mac-logging` loaded). The F-LOOPBACK
  sidecar recommends `null` for downstream filter ergonomics; the
  current choice is consistent and unambiguous with a wire MAC, so B.6
  passes as-specified. Revisit if downstream consumers need to
  distinguish "field absent" from "field empty by design."
- **conn-log is the only ingest path.** The bridge hooks only
  `Conn::log_policy`. F-BROADCAST and F-DHCP-related fixtures get partial
  coverage via the UDP entries Zeek synthesizes into conn.log; ARP-only
  and gratuitous-ARP frames produce no entry. C.8 and any future
  arp.log / dhcp.log-specific assertion will require a second hook.
- **First protocol/service signals observed.** The B.7 runs incidentally
  produced the first non-TCP and non-empty-service Stream entries:
  `proto=udp` with `service=dhcp` (F-BROADCAST), `proto=udp` with empty
  `service` (F-MULTICAST mDNS/LLMNR), and `proto=icmp` (F-MULTICAST IPv6
  NS — Zeek classifies ICMPv6 NS as `icmp`, not `icmpv6`). These weren't
  asserted on but are useful priors for whichever test exercises
  `service`-population next.

## Gaps

The master test plan is gone. The numbering above has holes — A.1
(only in docker README), B.1–B.3, C.1–C.7, C.10+, all D.*, E.1–E.16,
E.19+, F.1–F.19, F.21+. Each hole is a test that existed in the
original plan but has neither a sidecar nor a reconstructable record.

Two ways out (decision pending):

1. Treat the sidecars as the new authoritative spec, renumber from
   scratch, drop the holes.
2. Reconstruct the master plan from memory / context the next time it
   surfaces, restore the gap-tests to the ledger.

Capture-required fixtures (`F-MULTI-DEVICE`, `F-VLAN-TAGGED`,
`F-SUSTAINED`) have no test IDs in their `capture-notes.md` — those
tests lived in the master plan too.
