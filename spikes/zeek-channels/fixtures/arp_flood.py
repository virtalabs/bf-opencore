#!/usr/bin/env python3
"""F-ARP-FLOOD generator — produces ``arp-flood.pcap``.

A synthesis stand-in for the capture-required ``F-SUSTAINED`` fixture
(see ``sustained-load.capture-notes.md``), used **only** for D.14
(Redis down mid-stream).

Deliberate exception from F-SUSTAINED's design: F-SUSTAINED wanted
several minutes of mixed real traffic so all four D-series tests
(D.13/D.14/D.15/D.16) could share one capture. F-ARP-FLOOD provides
exactly one property F-SUSTAINED would have provided — enough
independent bridge events to produce sustained xAdd pressure during
Zeek processing time, so an external orchestrator can land a kill
mid-burst at a predictable point.

Why ARP and not conn-log: each ARP frame fires a discrete bridge event
on receipt. Conn-log records batch at ``connection_state_remove``,
which in offline replay fires after the pcap completes — meaning
conn-only fixtures produce all xAdds in a single end-of-pcap burst,
not spread across processing time. D.14 needs the latter.

This fixture is **not** a substitute for F-SUSTAINED on D.13/D.15/D.16
— those tests need traffic shape and timing that arp-flood doesn't
provide. Use the real capture for those.

See ``arp-flood.ground-truth.md`` for assertion targets.
"""

from pathlib import Path

from scapy.layers.l2 import ARP, Ether
from scapy.utils import wrpcap

FRAME_COUNT = 10000
BROADCAST = "ff:ff:ff:ff:ff:ff"
TARGET_IP = "10.0.0.1"
ARP_REQUEST = 1

OUTPUT = Path(__file__).parent / "arp-flood.pcap"


def mac_for_index(i: int) -> str:
    # Locally-administered MAC (bit-1 of first byte set), parameterized
    # over the low 16 bits of i. 10000 fits comfortably.
    return f"02:00:00:00:{(i >> 8) & 0xFF:02x}:{i & 0xFF:02x}"


def ip_for_index(i: int) -> str:
    # Synthetic /16 of source IPs in 10.42.0.0/16.
    return f"10.42.{(i >> 8) & 0xFF}.{i & 0xFF}"


def build_frames() -> list:
    frames = []
    for i in range(FRAME_COUNT):
        src_mac = mac_for_index(i)
        src_ip = ip_for_index(i)
        frame = Ether(src=src_mac, dst=BROADCAST) / ARP(
            op=ARP_REQUEST,
            hwsrc=src_mac,
            psrc=src_ip,
            hwdst="00:00:00:00:00:00",
            pdst=TARGET_IP,
        )
        frames.append(frame)
    return frames


def main() -> None:
    wrpcap(str(OUTPUT), build_frames())


if __name__ == "__main__":
    main()
