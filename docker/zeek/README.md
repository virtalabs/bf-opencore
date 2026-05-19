# virtalabsinc/zeek-probe

Standalone, long-running Zeek probe that captures conn + ARP traffic on
a configured interface and ships device observations to a BlueFlow API
via the bundled sidecar.

The image is the operational counterpart to `blueflow/zeek/` — it
bundles `arp_extract.zeek` and `sidecar.py` directly from the repo so a
single Docker pull gives you the full ingest path.

## Build

The build context MUST be the repo root so the Dockerfile can `COPY`
from `blueflow/zeek/`. For local-only iteration on the current host
architecture:

```bash
docker build -f docker/zeek/Dockerfile -t virtalabsinc/zeek-probe:dev .
```

For anything intended to ship (`:latest` or a SHA-tagged release), use
the multi-arch flow under "Push to DockerHub" below — a plain
`docker build` only produces a single-arch image and will silently
break ARM pullers.

## Environment

| Var | Required | Default | Purpose |
|---|---|---|---|
| `ZEEK_INTERFACE` | yes | — | Interface to capture on (e.g. `eth0`) |
| `BLUEFLOW_URL` | yes | — | BlueFlow base URL (e.g. `http://blueflow.internal:8000`) |
| `BLUEFLOW_TOKEN` | no | unset | DRF token; omitted = anonymous PUT |
| `PUSH_INTERVAL_SECONDS` | no | `60` | How often the sidecar pushes accumulated logs |
| `ZEEK_LOG_DIR` | no | `/var/log/zeek` | Where Zeek writes conn.log + arp.log |

If `ZEEK_INTERFACE` or `BLUEFLOW_URL` is missing, the entrypoint exits
with a clear message before Zeek starts.

## Run

Live capture needs raw-socket access to a host interface. Two
prerequisites:

1. `--network host` — without it the container only sees its own
   internal veth pair, not whatever NIC you actually want to monitor.
2. `--cap-add NET_ADMIN --cap-add NET_RAW` — Zeek's libpcap calls
   require both even when the process is uid 0 inside the container.

```bash
docker run --rm \
  --network host \
  --cap-add NET_ADMIN --cap-add NET_RAW \
  -e ZEEK_INTERFACE=eth0 \
  -e BLUEFLOW_URL=http://blueflow.internal:8000 \
  -e BLUEFLOW_TOKEN=<token> \
  virtalabsinc/zeek-probe:latest
```

On `docker stop` (SIGTERM) the entrypoint stops Zeek, runs one final
sidecar push so nothing observed in the last interval is lost, and
exits 0.

## Operational notes

- **Log growth is unbounded** in this MVP — Zeek writes to
  `$ZEEK_LOG_DIR/conn.log` and `arp.log` continuously, the sidecar reads
  from offset 0 every cycle, and nothing is rotated or truncated. Asset
  upsert is idempotent (`mac_address`-keyed; `open_ports_tcp` merges)
  so cumulative pushes are safe but wasteful. Restart the container, or
  later wire in `Log::default_rotation_interval`, if disk becomes a
  concern.
- **`PUSH_INTERVAL_SECONDS` is the latency floor** for an observation
  reaching BlueFlow. Set it low for demos, higher (5–15 min) in steady
  state.
- **No JSON-mode flag needed at runtime** — `LogAscii::use_json=T` is
  set on the Zeek command line inside the entrypoint so logs land as
  one JSON object per line, which is what the sidecar parses.

## Push to DockerHub

The image is published as a multi-arch manifest (linux/amd64 +
linux/arm64). Building and pushing both architectures requires the
`docker-container` buildx driver — the default `desktop-linux` /
`docker` driver cannot produce manifest lists and will silently emit a
single-arch image.

One-time setup of a multi-arch builder (if `docker buildx ls` does not
already show one):

```bash
docker buildx create --name multiarch --driver docker-container --use
docker buildx inspect --bootstrap
```

Build + push both tags in one shot from the repo root:

```bash
SHA=$(git rev-parse --short HEAD)
docker buildx build \
  --builder multiarch \
  --platform linux/amd64,linux/arm64 \
  -f docker/zeek/Dockerfile \
  -t virtalabsinc/zeek-probe:latest \
  -t virtalabsinc/zeek-probe:"$SHA" \
  --push \
  .
```

`--push` uploads the manifest list directly to the registry; the local
image store never holds the multi-arch result. Verify the result:

```bash
docker buildx imagetools inspect virtalabsinc/zeek-probe:latest
```

You should see one manifest entry per platform plus a couple of
`unknown/unknown` entries — those are SBOM/provenance attestations
buildx attaches by default and are safe to ignore.

(`virtalabsinc` is the DockerHub org for Virta Laboratories images. The
GitHub org is `virtalabs` without the `inc` — don't confuse them.)
