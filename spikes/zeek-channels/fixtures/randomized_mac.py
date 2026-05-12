#!/usr/bin/env python3
"""F-LOCAL-ADMIN generator — produces ``randomized-mac.pcap``.

A short TCP exchange whose source MAC has the locally-administered bit
set, mimicking the privacy MACs that recent iOS / Android devices emit.
Used by B.7 (special MAC types round-trip correctly).

Bit-pattern primer for ``02:1a:2b:3c:4d:5e``:
    first byte = 0x02 = 0b00000010
                          ^^
                          ||
                          |+-- bit-0 LSB = 0 → unicast
                          +--- bit-1     = 1 → locally administered

This MAC is well-formed and unicast; the test guards against the bridge
mistakenly treating "locally administered" as "malformed" or stripping
the bit.

See ``randomized-mac.ground-truth.md`` for assertion targets.
"""

from pathlib import Path

from scapy.layers.inet import IP, TCP
from scapy.layers.l2 import Ether
from scapy.utils import wrpcap

PRIVACY_MAC = "02:1a:2b:3c:4d:5e"
PEER_MAC = "00:1b:21:00:00:01"
PRIVACY_IP = "10.0.50.42"
PEER_IP = "10.0.50.1"
PORT_CLIENT = 51000
PORT_SERVER = 443
SEQ_CLIENT = 4000
SEQ_SERVER = 5000

OUTPUT = Path(__file__).parent / "randomized-mac.pcap"


def build_frames() -> list:
    c_to_s = Ether(src=PRIVACY_MAC, dst=PEER_MAC) / IP(src=PRIVACY_IP, dst=PEER_IP)
    s_to_c = Ether(src=PEER_MAC, dst=PRIVACY_MAC) / IP(src=PEER_IP, dst=PRIVACY_IP)

    syn = c_to_s / TCP(
        sport=PORT_CLIENT,
        dport=PORT_SERVER,
        flags="S",
        seq=SEQ_CLIENT,
    )
    synack = s_to_c / TCP(
        sport=PORT_SERVER,
        dport=PORT_CLIENT,
        flags="SA",
        seq=SEQ_SERVER,
        ack=SEQ_CLIENT + 1,
    )
    ack = c_to_s / TCP(
        sport=PORT_CLIENT,
        dport=PORT_SERVER,
        flags="A",
        seq=SEQ_CLIENT + 1,
        ack=SEQ_SERVER + 1,
    )

    return [syn, synack, ack]


def main() -> None:
    wrpcap(str(OUTPUT), build_frames())


if __name__ == "__main__":
    main()
