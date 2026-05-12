# F-MULTI-DEVICE — capture notes

**Fixture:** `multi-device-broadcast-domain.pcap`
**Method:** capture from a small real network (no synth path)

This fixture cannot be cleanly synthesized — see the
fixture-generation plan's "NOT practically generatable" section. The
test (C.10) validates that the bridge handles concurrent multi-device
traffic; a too-uniform synthesized fixture would mask exactly the
issues the test is supposed to detect.

## What you need

- 3–5 distinct devices on the same broadcast domain (any home network,
  small office network, or isolated test VLAN works)
- A capture host on that network with privileged access to `tcpdump`
- ~30 seconds of mixed protocol traffic during the capture window
  (HTTP, DNS, mDNS, ARP, anything)

## Capture command

```bash
sudo tcpdump -i <iface> -w multi-device-broadcast-domain.pcap
# Let it run ~30 seconds, then Ctrl-C
```

Pick `<iface>` so the capture sees ALL device MACs — usually an
ethernet interface on a switch that's mirroring the broadcast domain
to it, or simply a Wi-Fi interface if 3–5 devices share an AP.

## Extracting ground truth

Run after capture, paste output into the ground-truth doc:

```bash
# Distinct source MACs in the pcap
tshark -T fields -e eth.src -r multi-device-broadcast-domain.pcap | sort -u

# Frame count per source MAC
tshark -T fields -e eth.src -r multi-device-broadcast-domain.pcap | sort | uniq -c | sort -rn

# Protocol mix
tshark -T fields -e _ws.col.Protocol -r multi-device-broadcast-domain.pcap | sort | uniq -c | sort -rn

# Approximate duration
capinfos multi-device-broadcast-domain.pcap | grep -i "duration"
```

The distinct-MAC list is the load-bearing ground truth — C.10 asserts
that every one of those MACs appears in the resulting Stream entries.

## Sanitization checklist

This pcap will come from a real network. Before checking it in:

- [ ] **Redact payload content** that might contain identifiable
      hostnames, user-agent strings, or DNS queries to sensitive
      domains. `tcprewrite` can strip payloads; alternatively
      recapture with a filter:
      ```bash
      sudo tcpdump -i <iface> -w out.pcap 'arp or icmp or (port 53 and host <known-resolver>)'
      ```
- [ ] **Confirm MAC addresses are non-sensitive.** MACs are the *point*
      of this fixture, so don't strip them — but check there's no MAC
      tied to a person's personally-owned device they wouldn't want in
      a repo. Use lab devices or generic infrastructure where possible.
- [ ] **No production secrets.** If the capture caught any auth
      cookies, API tokens, or TLS-handshake-leaked SNIs, redact or
      recapture.

## Ground-truth template — fill in after capture

Create `multi-device-broadcast-domain.ground-truth.md` with:

```markdown
# F-MULTI-DEVICE — ground truth

**Fixture:** multi-device-broadcast-domain.pcap
**Source:** real capture
**Capture date:** YYYY-MM-DD
**Capture host:** <hostname / iface>
**Capture duration:** ~30s

## Devices observed

| MAC | Frame count | Protocols seen |
|---|---|---|
| aa:bb:cc:dd:ee:01 | 42 | ARP, HTTP, DNS |
| aa:bb:cc:dd:ee:02 | 17 | mDNS, DNS |
| ... | ... | ... |

## What tests assert

| Test | Assertion |
|---|---|
| C.10 Multiple devices distinguished | Every MAC in the table above appears in at least one Stream entry, with no collisions or overwrites |
```

## Public-source alternative

Before doing a fresh capture, consider whether a public sanitized capture
suffices:

- Wireshark sample-captures wiki
- malware-traffic-analysis.net (filter for non-malicious LAN captures)
- PacketTotal

For C.10, the property needed is "multiple devices on one broadcast
domain, mixed protocols." Many public LAN captures qualify. Note the
provenance in the ground-truth doc if you use one.
