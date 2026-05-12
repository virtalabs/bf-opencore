#!/usr/bin/env python3
"""F-MULTICAST-MAC generator — produces ``multicast-dest.pcap``.

Three frames covering the three multicast MAC families a BlueFlow
deployment will encounter most often:

* ``01:00:5e:00:00:fb`` — IPv4 mDNS group
* ``01:00:5e:00:00:fc`` — IPv4 LLMNR group
* ``33:33:00:00:00:01`` — IPv6 all-nodes link-local

Used by B.7 (special MAC types round-trip). The bridge must not normalize,
drop, or misclassify any of these.

See ``multicast-dest.ground-truth.md`` for assertion targets.
"""

from pathlib import Path

from scapy.layers.dns import DNS, DNSQR
from scapy.layers.inet import IP, UDP
from scapy.layers.inet6 import ICMPv6ND_NS, IPv6
from scapy.layers.l2 import Ether
from scapy.utils import wrpcap

DEVICE_MAC = "a4:b1:c2:d3:e4:f5"
DEVICE_IP4 = "192.168.10.100"
DEVICE_IP6 = "fe80::a6b1:c2ff:fed3:e4f5"

MDNS_MAC = "01:00:5e:00:00:fb"
MDNS_IP4 = "224.0.0.251"
MDNS_PORT = 5353

LLMNR_MAC = "01:00:5e:00:00:fc"
LLMNR_IP4 = "224.0.0.252"
LLMNR_PORT = 5355

IPV6_ALLNODES_MAC = "33:33:00:00:00:01"
IPV6_ALLNODES = "ff02::1"
IPV6_TARGET = "fe80::1"

OUTPUT = Path(__file__).parent / "multicast-dest.pcap"


def build_frames() -> list:
    mdns = (
        Ether(src=DEVICE_MAC, dst=MDNS_MAC)
        / IP(src=DEVICE_IP4, dst=MDNS_IP4)
        / UDP(sport=MDNS_PORT, dport=MDNS_PORT)
        / DNS(rd=0, qd=DNSQR(qname="_services._dns-sd._udp.local", qtype="PTR"))
    )

    llmnr = (
        Ether(src=DEVICE_MAC, dst=LLMNR_MAC)
        / IP(src=DEVICE_IP4, dst=LLMNR_IP4)
        / UDP(sport=LLMNR_PORT, dport=LLMNR_PORT)
        / DNS(rd=0, qd=DNSQR(qname="testhost", qtype="A"))
    )

    ipv6_ns = (
        Ether(src=DEVICE_MAC, dst=IPV6_ALLNODES_MAC)
        / IPv6(src=DEVICE_IP6, dst=IPV6_ALLNODES)
        / ICMPv6ND_NS(tgt=IPV6_TARGET)
    )

    return [mdns, llmnr, ipv6_ns]


def main() -> None:
    wrpcap(str(OUTPUT), build_frames())


if __name__ == "__main__":
    main()
