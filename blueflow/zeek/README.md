# blueflow.zeek

Zeek log ingest for BlueFlow Asset records. Consumes the conn.log Zeek
produces by default, plus the arp.log produced by the bundled
`arp_extract.zeek` script (stock Zeek 6.x ships no ARP log policy).

The original HL7-specific implementation (promoted from spike #111,
`zeek-hl7-spike-frozen`) is preserved at `hl7/`. See `hl7/README.md`
for that history; it is no longer wired into the live `zeek_ingest`
management command.

## Components

```text
blueflow/zeek/
  __init__.py
  sidecar.py                 # conn.log + arp.log loader + aggregator
  scripts/
    arp_extract.zeek         # arp_request/arp_reply -> arp.log
  data/                      # pcap fixtures (gitignored — see below)
  hl7/                       # archived HL7 sidecar + scripts + tests
```

## Pipeline

```text
pcap or live iface
   │
   ▼
zeek -r <pcap> blueflow/zeek/scripts/arp_extract.zeek
   │
   ├──▶ conn.log   (stock Zeek; one record per connection, incl. orig/resp L2 MACs)
   └──▶ arp.log    (from arp_extract.zeek; one record per arp_request/arp_reply)
   │
   ▼
python manage.py zeek_ingest --logdir <dir>
   │
   ▼
Asset upsert (keyed on mac_address; open_ports_tcp merged across runs)
```

### What the sidecar records

- **conn.log** — both endpoints become Assets. The originator gets a row
  for the L2/L3 observation; the responder additionally records
  `id.resp_p` as `open_ports_tcp` (TCP only; UDP/ICMP do not contribute
  open ports).
- **arp.log** — the *source* of each ARP frame becomes an Asset (SPA→SHA
  binding). Destinations are skipped: a REQUEST's dst is broadcast, and
  a REPLY's dst is the original querier, which we will have already
  observed as the src of its own REQUEST.
- **Broadcast / multicast / zero MACs are dropped.** ARP-flood fixtures
  with `02:00:00:00:**:**` source MACs are recorded normally (locally
  administered ≠ multicast).
- **No-L2 fallback** — pcaps without Ethernet headers (loopback replay)
  miss `orig_l2_addr` / `resp_l2_addr`. The sidecar synthesizes a
  deterministic locally-administered MAC from the IP via `mac_from_ip()`
  so re-runs upsert the same Asset.

## Test pcap fixture

The end-to-end harness (`docker/`) mounts `blueflow/zeek/data/` to source
a pcap. The fixture itself is **never tracked** by git — `*.pcap` is
gitignored project-wide and `blueflow/zeek/data/.gitignore` walls off
the directory contents. This prevents accidental commits of pcaps that
may carry PHI.

The `feature/spike-zeek-channels` branch ships several synthesized ARP
and conn fixtures (`spikes/zeek-channels/fixtures/*.py`) that are useful
sources of test pcaps. Generate one and drop it into `data/`:

```bash
git show feature/spike-zeek-channels:spikes/zeek-channels/fixtures/arp_only.py \
  > /tmp/arp_only.py
python /tmp/arp_only.py blueflow/zeek/data/arp-only.pcap
```

## Running

```bash
# Replay a pcap into a temp log dir, then ingest.
mkdir -p /tmp/zeek-out && cd /tmp/zeek-out
zeek -Cr <path-to-pcap> <repo>/blueflow/zeek/scripts/arp_extract.zeek
python <repo>/project/manage.py zeek_ingest --logdir /tmp/zeek-out/
```

`zeek_ingest` is the entry point for ORM-side ingest. Assets are
upserted by `mac_address`, with `open_ports_tcp` merged across runs —
same merge semantics as `PUT /api/assets/upsert/`.

## Field mapping (current)

| Asset field      | Source                                                    |
|------------------|-----------------------------------------------------------|
| `mac_address`    | `conn.orig_l2_addr` / `conn.resp_l2_addr` / `arp.src_mac` |
| `ip_address`     | `conn.id.orig_h` / `conn.id.resp_h` / `arp.src_ip`        |
| `open_ports_tcp` | `conn.id.resp_p` (when `proto=tcp`)                       |

No `name`, `serial_number`, or `external_keys` enrichment in this path
— those came from the HL7 protocol fields and are not present in
conn/arp data. See `hl7/` for the prior implementation.

## Docker harness

The integration harness in top-level `docker/zeek/` currently runs the
HL7 pipeline. Rewiring it to drive conn + arp is the next change on
this branch.
