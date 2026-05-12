# F-LOOPBACK — capture notes (preferred over synth)

**Fixture:** `loopback-no-l2.pcap`
**Method:** real capture on the host's loopback interface
**Why preferred over synth:** authentic linktype on the running OS; no
risk of the synthesized pcap diverging from how real loopback captures
behave through Zeek.

The scapy fallback in `loopback_no_l2.py` is fine if capture is
inconvenient (e.g., CI without privileged access), but capture is the
default. Either output satisfies the fixture's contract — the test only
asserts L2 fields are absent and the bridge handles that.

## Capture command

### macOS

```bash
sudo tcpdump -i lo0 -w loopback-no-l2.pcap
```

In a second terminal, generate some loopback traffic:

```bash
curl http://localhost:8000   # or whatever's running
# or:
nc -l 9999 &
nc localhost 9999 <<< "hello"
```

Stop the capture (Ctrl-C) once you have at least a handful of frames.

macOS lo0 captures as **`DLT_NULL`** (linktype 0).

### Linux

```bash
sudo tcpdump -i lo -w loopback-no-l2.pcap
```

In a second terminal:

```bash
curl http://localhost:8000
# or:
python3 -m http.server 8000 &
curl http://localhost:8000
```

Linux lo captures as **`DLT_LINUX_SLL2`** (linktype 276) on modern
tcpdump, or `DLT_LINUX_SLL` (113) on older versions. Both have no
Ethernet header. Either is acceptable for this fixture.

## Confirming the linktype

```bash
capinfos loopback-no-l2.pcap | grep -i "data link"
# Expected (macOS):
#   Data link type: NULL (DLT 0)
# Expected (Linux, modern tcpdump):
#   Data link type: Linux cooked v2 (DLT 276)
```

If the linktype is `EN10MB` (1) you captured on the wrong interface;
recapture with `-i lo` (Linux) or `-i lo0` (macOS).

## Sanitization

Loopback traffic from a developer machine may contain identifiers from
local services. Before checking in:

- If the capture session was a controlled `curl localhost:<port>` against
  a known service, no scrub needed.
- If the capture caught background traffic from other apps, redact with
  `tcprewrite` or recapture more narrowly:
  ```bash
  sudo tcpdump -i lo0 -w loopback-no-l2.pcap port 8000
  ```

## What to write back into the ground-truth doc

After capturing, record in `loopback-no-l2.ground-truth.md`:

- Exact linktype value (from `capinfos`)
- Actual frame count
- What was generating traffic during capture
- That this is a real capture, not the scapy fallback

This makes the fixture's provenance auditable in CI later.
