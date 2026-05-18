# docker/_hl7-harness — ARCHIVED HL7 integration test harness

This folder is the end-to-end test rig that drove the **old HL7-only**
Zeek ingest pipeline (spike #111). It is preserved as-is for reference
when the conn + arp pipeline grows its own integration harness on this
branch.

> **NOTE — paths inside this folder are stale.** The compose file,
> `run-local.sh`, and `verify.py` were written assuming the harness
> lived at `docker/` (one level shallower). Internal references like
> `docker compose -f docker/docker-compose.yml ...` and `context: ..`
> point at the wrong locations now. Treat invocations as illustrative,
> not directly runnable.
>
> To actually run this harness, check it out at the commit immediately
> preceding the docker pivot (`git log -- docker/_hl7-harness` gives the
> rename commit; the parent of that is the last working state).

The old `docker/zeek/Dockerfile` and `entrypoint.sh` that this harness
expected at `docker/zeek/` were moved into `zeek-hl7/` here so the
archive is self-contained. The current `docker/zeek/` slot holds the
standalone probe image that replaces them.

## Original purpose

End-to-end test rig for `blueflow.zeek` (HL7 era). Containers replayed
a pcap of HL7 traffic into a live Zeek instance and verified the
sidecar's HTTP push to a BlueFlow endpoint. Two compose profiles
selected what was on the receiving end:

- **`stub`** — a tiny Python `HTTPServer` that accepted any PUT and
  wrote a JSONL ledger. Fast (~3s start), no DB. Exercised plumbing only.
- **`real`** — the actual BlueFlow image + ephemeral Postgres. Exercised
  serializer validation, ORM upsert, entity resolution.

## Layout (as preserved)

```text
_hl7-harness/
  docker-compose.yml          # 5-service compose (stub + real profiles)
  run-local.sh                # non-docker zeek + sidecar local run
  verify.py                   # post-run assertion script (stub mode)
  blueflow/                   # [stub profile] — tiny HTTP server
  blueflow-real/              # [real profile] — bootstrap for real BlueFlow
  traffic/                    # tcpreplay container
  zeek-hl7/                   # was docker/zeek/ — HL7-specific Zeek probe
```

The unit-test counterpart for the HL7 sidecar's correlation +
aggregation logic still runs as part of `pytest`; it lives at
`blueflow/zeek/hl7/tests/test_zeek_ingest.py`.
