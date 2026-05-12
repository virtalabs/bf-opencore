#!/usr/bin/env python3
"""F-BROADCAST-MAC generator — produces ``broadcast-dest.pcap``.

Two frames whose Ethernet ``dst`` is the all-ones broadcast MAC. Used by
B.7 (special MAC types round-trip correctly) — specifically, that
``ff:ff:ff:ff:ff:ff`` is not normalized away, replaced, or flagged as
malformed on its way to the Stream.

See ``broadcast-dest.ground-truth.md`` for assertion targets.
"""

from pathlib import Path

from scapy.layers.dhcp import BOOTP, DHCP
from scapy.layers.inet import IP, UDP
from scapy.layers.l2 import ARP, Ether
from scapy.utils import mac2str, wrpcap

CLIENT_MAC = "12:34:56:78:9a:bc"
CLIENT_IP = "192.168.10.42"
BROADCAST_MAC = "ff:ff:ff:ff:ff:ff"
BROADCAST_IP = "255.255.255.255"
UNASSIGNED_IP = "0.0.0.0"  # noqa: S104 — DHCP-protocol-mandated unassigned IP, not a socket bind
DHCP_CLIENT_PORT = 68
DHCP_SERVER_PORT = 67
BOOTREQUEST = 1
ARP_REQUEST = 1
TRANSACTION_ID = 0xAABBCCDD

OUTPUT = Path(__file__).parent / "broadcast-dest.pcap"


def build_frames() -> list:
    dhcp_discover = (
        Ether(src=CLIENT_MAC, dst=BROADCAST_MAC)
        / IP(src=UNASSIGNED_IP, dst=BROADCAST_IP)
        / UDP(sport=DHCP_CLIENT_PORT, dport=DHCP_SERVER_PORT)
        / BOOTP(
            op=BOOTREQUEST,
            chaddr=mac2str(CLIENT_MAC) + b"\x00" * 10,
            xid=TRANSACTION_ID,
        )
        / DHCP(options=[("message-type", "discover"), "end"])
    )

    # Gratuitous ARP: device announces its own IP. Both psrc and pdst
    # are CLIENT_IP, and the Ether dst is broadcast.
    gratuitous_arp = Ether(src=CLIENT_MAC, dst=BROADCAST_MAC) / ARP(
        op=ARP_REQUEST,
        hwsrc=CLIENT_MAC,
        psrc=CLIENT_IP,
        hwdst="00:00:00:00:00:00",
        pdst=CLIENT_IP,
    )

    return [dhcp_discover, gratuitous_arp]


def main() -> None:
    wrpcap(str(OUTPUT), build_frames())


if __name__ == "__main__":
    main()
