# F-SUSTAINED — capture notes

**Fixture:** `sustained-load.pcap`
**Method:** capture from any real network with permission (no synth path)

Used by all four D-series resilience tests (D.13/D.14/D.15/D.16). The
fixture exists to provide several minutes of mixed real traffic so the
bridge can be put through realistic failure scenarios — Redis down at
startup, Redis down mid-stream, Zeek restart, slow consumer.

## What you need

- Permission to capture on a network with steady ambient traffic
  (office network during business hours, a busy lab segment, a home
  network with multiple devices)
- ~5 minutes of capture time
- Enough volume to backpressure a slow Redis consumer (target: tens of
  thousands of frames over the capture window)

## Capture command

```bash
sudo tcpdump -i <iface> -w sustained-load.pcap
# Let it run ~5 minutes, then Ctrl-C
```

You can use a filter to keep the file size manageable while preserving
the resilience-test contract:

```bash
sudo tcpdump -i <iface> -w sustained-load.pcap \
    'arp or icmp or dhcp or (tcp and (port 53 or port 80 or port 443))'
```

The resilience tests don't assert on specific packet content — only on
"the bridge survived and resumed producing." So payload filtering is
fine; you mostly need volume and time.

## Extracting ground truth

The ground-truth here is an envelope, not per-event values:

```bash
# Total frames
tshark -r sustained-load.pcap | wc -l

# Duration
capinfos sustained-load.pcap | grep -i "duration"

# Average packets/second
capinfos sustained-load.pcap | grep -i "average packet rate"

# Peak rate (rough — packets in busiest 10-second window)
tshark -q -z io,stat,10 -r sustained-load.pcap
```

Record these in the ground-truth doc. D.13–D.16 use the avg/peak rate
to set expectations for "what should I see when I unblock the consumer."

## Sanitization checklist

5 minutes of office traffic is *the* most likely capture to contain
private data. Mandatory checks:

- [ ] **Filter at capture time** rather than after — once payloads are
      in the file, scrubbing is harder than preventing.
- [ ] **Avoid HTTPS payload capture** unless TLS is irrelevant for the
      test (it is — D-series tests don't care about content).
- [ ] **Strip DNS query names** with `tcprewrite` if DNS payloads
      ended up in the capture and might leak internal hostnames.
- [ ] **Check user-agent strings** — even short HTTP payloads can
      expose internal browser fingerprints. Filter or strip.
- [ ] **MAC addresses are not sensitive** for this fixture (the test
      doesn't assert on specific MACs), so you can `tcprewrite
      --enet-smac` / `--enet-dmac` to anonymize them if needed.

## Ground-truth template — fill in after capture

```markdown
# F-SUSTAINED — ground truth

**Fixture:** sustained-load.pcap
**Source:** real network capture
**Capture date:** YYYY-MM-DD
**Capture host / iface:** <hostname / iface>
**Filter applied:** arp or icmp or dhcp or tcp ...

## Envelope

| Metric | Value |
|---|---|
| Total frames | ~50000 |
| Duration | 5m 12s |
| Avg packets/sec | ~160 |
| Peak packets/sec (10s window) | ~400 |
| File size | 12 MB |

## What tests assert

| Test | Assertion |
|---|---|
| D.13 Redis down at startup | Bridge starts with Redis offline, doesn't crash Zeek, recovers when Redis returns. Once Redis returns, Stream depth grows at roughly avg packets/sec. |
| D.14 Redis down mid-stream | Take Redis offline mid-replay, bring back. Bridge survives; in-flight data loss is bounded and observable. |
| D.15 Zeek restart leaves bridge healthy | Restart Zeek while replay is running; bridge resumes without manual intervention. |
| D.16 Slow consumer doesn't crash producer | Don't read from Stream while bridge produces; bridge keeps producing; back-pressure lands on Redis retention, not on Zeek. |
```

## Public-source alternative

For F-SUSTAINED specifically, public sanitized "office network" pcaps
are widely available — Wireshark sample-captures and similar archives
include multi-minute mixed-traffic samples. Using one of those avoids
the sanitization burden of doing a fresh capture.

Note the provenance + envelope in the ground-truth doc, as if it were
your own capture.
