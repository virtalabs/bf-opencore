# F-VLAN-TAGGED — capture notes

**Fixture:** `vlan-trunk.pcap`
**Method:** capture from a real 802.1Q trunk port (no synth path)

**This is the riskiest fixture to acquire.** If trunk-port access isn't
available, defer C.11 rather than fake it. A synthesized fake-trunk
capture would defeat the test's purpose — see the fixture-generation
plan's "NOT practically generatable" section.

## What you need

- Access to a switch with at least one configured 802.1Q trunk port
  (cisco / aruba / juniper / mikrotik — any vendor that supports VLAN
  tagging on a port)
- A capture host whose NIC is connected to a SPAN / mirror port that
  mirrors the trunk
- At least two VLANs with active devices on each
- At least one identifiable device per VLAN whose MAC you can pre-record

## Capture command

```bash
# Linux capture host with trunk on enp2s0:
sudo tcpdump -i <span-iface> -w vlan-trunk.pcap

# Let it run long enough to see ARP/DHCP from each tagged VLAN.
# 60s minimum; longer is better if VLANs are quiet.
```

If your capture interface is not VLAN-aware (some NICs strip tags before
tcpdump sees them), enable promiscuous + non-stripping mode:

```bash
sudo ethtool -K <span-iface> rxvlan off
```

Confirm captured frames have `vlan.id` populated before proceeding —
if every frame's `vlan.id` is empty, the tags were stripped at the NIC
and the fixture will not exercise the test path.

## Extracting ground truth

```bash
# All VLAN IDs in the pcap
tshark -T fields -e vlan.id -r vlan-trunk.pcap | sort -u

# Per-VLAN distinct device MACs
for vlan in $(tshark -T fields -e vlan.id -r vlan-trunk.pcap | sort -u); do
    echo "VLAN $vlan:"
    tshark -Y "vlan.id == $vlan" -T fields -e eth.src \
        -r vlan-trunk.pcap | sort -u
done

# Untagged frames (should be sparse on a true trunk)
tshark -Y "not vlan" -r vlan-trunk.pcap | wc -l
```

The per-VLAN MAC inventory is the load-bearing ground truth — C.11
asserts the MAC arriving in Redis is the device's MAC inside the tag,
NOT the trunk-port MAC or the switch's MAC.

## The trunk-port MAC

Find the switch's trunk-port MAC and call it out explicitly in the
ground-truth doc:

```bash
# On the switch CLI, e.g. cisco:
show mac address-table interface <trunk-port>
```

C.11 fails if the bridge reports the trunk-port MAC instead of the
inner device MAC. Naming both in ground truth makes the assertion
unambiguous.

## Sanitization checklist

Trunk captures from production networks contain a *lot* of incidental
traffic across multiple VLANs. Before checking in:

- [ ] **Use a lab switch / test environment if at all possible.** This
      reduces the surface area for accidentally leaking production
      data.
- [ ] **Filter to the protocols you actually need** when capturing:
      ```bash
      sudo tcpdump -i <span-iface> -w vlan-trunk.pcap 'arp or dhcp or icmp'
      ```
      ARP and DHCP are usually sufficient to exercise C.11.
- [ ] **Strip payloads** with `tcprewrite` if HTTP/DNS/TLS captures
      ended up included.
- [ ] **MACs are the point** — preserve them, but document any that
      might be tied to person-owned devices.

## Ground-truth template — fill in after capture

```markdown
# F-VLAN-TAGGED — ground truth

**Fixture:** vlan-trunk.pcap
**Source:** real trunk-port capture
**Capture date:** YYYY-MM-DD
**Switch / trunk port:** <model> / <port id>
**Trunk-port MAC:** xx:xx:xx:xx:xx:xx

## VLANs observed

| VLAN ID | Device MAC(s) inside the tag |
|---|---|
| 10 | aa:bb:cc:dd:ee:01 |
| 20 | aa:bb:cc:dd:ee:02, aa:bb:cc:dd:ee:03 |

## What tests assert

| Test | Assertion |
|---|---|
| C.11 VLAN-tagged preserves device MAC | For each VLAN above, the Stream entries contain the device MAC, NOT the trunk-port MAC (xx:xx:xx:xx:xx:xx) |
```

## If trunk access is not available

Defer C.11. Document in the bridge implementation tracking that the
test is not yet covered. Do **not** synthesize a fake. The whole point
of C.11 is to catch divergence between synthetic and real trunk
captures.

Public sanitized trunk captures with documented per-VLAN MACs are rare.
If you find one (e.g., on Wireshark sample-captures), provenance and
the per-VLAN MAC inventory must be reconstructed from the pcap before
using it.
