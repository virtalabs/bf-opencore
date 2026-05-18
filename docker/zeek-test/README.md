# docker/zeek-test

Self-contained compose harness for demoing the `virtalabsinc/zeek-probe`
image end-to-end against a **real BlueFlow** (Django + PostgreSQL).
Synthesizes ARP + TCP traffic, captures it with the probe, ships device
observations to BlueFlow via `/api/assets/upsert/`, then fetches the
resulting assets and prints them. Built for screenshotting.

## Run

```bash
docker compose -f docker/zeek-test/docker-compose.yml up --build \
                                                       --abort-on-container-exit
```

First run takes ~3–4 min (BlueFlow image + Zeek base + scapy). Cached
runs are ~30s.

`traffic-gen` exits 0 once it has fetched `/api/assets/` and printed
the materialized devices; `--abort-on-container-exit` then brings the
rest down. For full cleanup:

```bash
docker compose -f docker/zeek-test/docker-compose.yml down -v
```

## What to screenshot

Toward the end of the run (~25–35s in), `traffic-gen` prints the
materialized assets. Real observed output:

```text
zeek-test-traffic   | [traffic-gen] BlueFlow has 6 asset(s):
zeek-test-traffic   | [traffic-gen]   mac=00:11:22:33:44:55  ip=10.0.0.20  ports=[]
zeek-test-traffic   | [traffic-gen]   mac=aa:bb:cc:dd:ee:ff  ip=10.0.0.50  ports=[80, 443]
zeek-test-traffic   | [traffic-gen]   mac=52:6d:fc:2a:0f:71  ip=172.25.0.3  ports=[]
zeek-test-traffic   | [traffic-gen]   mac=aa:63:8b:90:23:18  ip=172.25.0.4  ports=[]
zeek-test-traffic   | [traffic-gen]   mac=de:ad:be:ef:00:01  ip=10.0.0.5   ports=[]
zeek-test-traffic   | [traffic-gen]   mac=00:50:56:c0:00:01  ip=10.0.0.1   ports=[]
zeek-test-traffic exited with code 0
```

Three things to call out in the screenshot caption:

1. **`de:ad:be:ef:00:01` was discovered from ARP only** — that MAC sent
   no IP traffic; without `arp_extract.zeek` it would be invisible to
   BlueFlow. The asset comes from the SPA→SHA binding in an ARP request.
2. **`aa:bb:cc:dd:ee:ff` has `ports=[80, 443]`** — the responder of
   the two TCP exchanges; `id.resp_p` was correctly attributed only to
   the server side.
3. **`00:11:22:33:44:55` has `ports=[]`** — the originator's ephemeral
   source ports (54321, 54322) were *not* recorded, confirming the
   asymmetric port attribution in the sidecar's conn handler.

### About the "ambient" devices (`172.25.0.*`)

The two `172.25.0.*` rows (random MACs) are **zeek-probe's own eth0**
and **blueflow's eth0** on the docker bridge. They show up because the
probe is faithfully recording every device it observes on the wire —
including itself and BlueFlow exchanging the upsert PUTs. This is the
probe behaving correctly, not a defect; you can mention it as a bonus
proof that "everything on the wire becomes an Asset." Their MACs and
IPs will be different on each `docker compose up`.

### Why `policy/protocols/conn/mac-logging` is loaded

Stock Zeek conn.log does **not** include `orig_l2_addr` /
`resp_l2_addr`. Without that policy script the sidecar falls back to
`mac_from_ip()` and the TCP scenario shows synthesized `02:00:*` MACs
instead of the crafted `00:11:22:33:44:55` / `aa:bb:cc:dd:ee:ff`.
`blueflow/zeek/scripts/arp_extract.zeek` `@load`s mac-logging for this
reason.

## Topology

```
              ┌─────────────┐     ┌──────────────────────────────────┐
              │  postgres   │ ◄── │  blueflow (real Django + DRF)    │
              │  :5432      │     │  bootstrap: migrate + waffle     │
              └─────────────┘     │  serves /api/assets/upsert/      │
                                  └────────────▲─────────────────────┘
                                               │ http
                ┌──────────────────────────────┴──────────────────┐
                │     zeek-probe (network namespace)              │
                │     - zeek -i eth0 arp_extract.zeek             │
                │     - sidecar.py pushes every 10s               │
                └────────────────────▲────────────────────────────┘
                                     │ shares ns (network_mode: service:zeek-probe)
                                     │
                           ┌─────────┴─────────┐
                           │   traffic-gen     │
                           │   scapy sendp     │
                           │   then GET /api/  │
                           └───────────────────┘
```

`network_mode: "service:zeek-probe"` is the load-bearing trick:
traffic-gen's `eth0` *is* zeek-probe's `eth0`, so `sendp()` lands on
the same NIC Zeek is listening on without needing `--network host`.

## Layout

```text
docker/zeek-test/
  docker-compose.yml
  blueflow-bootstrap.sh   # mounted into the BlueFlow container as /bootstrap.sh
  traffic-gen/
    Dockerfile            # python:3.12-slim + scapy
    generate.py           # ARP + full TCP handshake synthesis + verify GET
```
