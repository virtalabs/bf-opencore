#!/usr/bin/env python3
"""F-ARP-ONLY generator — produces ``arp-only.pcap``.

Two frames: an ARP who-has from a device with no other traffic, and the
gateway's is-at reply. Used by C.8 (ARP-only devices captured).

The key property is that ``KNOWN_MAC`` appears **only** in ARP, not in any
IP-layer frame. The test validates that the bridge picks up L2-only
protocols, not just conn.log records.

See ``arp-only.ground-truth.md`` for assertion targets.
"""

from pathlib import Path

from scapy.layers.l2 import ARP, Ether
from scapy.utils import wrpcap

KNOWN_MAC = "de:ad:be:ef:00:01"
GATEWAY_MAC = "00:50:56:c0:00:01"
KNOWN_IP = "10.0.0.5"
GATEWAY_IP = "10.0.0.1"
BROADCAST = "ff:ff:ff:ff:ff:ff"
ARP_REQUEST = 1
ARP_REPLY = 2

OUTPUT = Path(__file__).parent / "arp-only.pcap"


def build_frames() -> list:
    request = Ether(src=KNOWN_MAC, dst=BROADCAST) / ARP(
        op=ARP_REQUEST,
        hwsrc=KNOWN_MAC,
        psrc=KNOWN_IP,
        hwdst="00:00:00:00:00:00",
        pdst=GATEWAY_IP,
    )
    reply = Ether(src=GATEWAY_MAC, dst=KNOWN_MAC) / ARP(
        op=ARP_REPLY,
        hwsrc=GATEWAY_MAC,
        psrc=GATEWAY_IP,
        hwdst=KNOWN_MAC,
        pdst=KNOWN_IP,
    )
    return [request, reply]


def main() -> None:
    wrpcap(str(OUTPUT), build_frames())


if __name__ == "__main__":
    main()
