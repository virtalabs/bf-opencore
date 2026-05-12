#!/usr/bin/env python3
"""F-IPV4-TCP generator — produces ``known-mac-tcp.pcap``.

Single bidirectional TCP handshake (SYN / SYN-ACK / ACK) with one known
source MAC and one known destination MAC. Used by B.4 (MAC fidelity), B.5
(both src/dst captured) and F.20 (replay determinism).

See ``known-mac-tcp.ground-truth.md`` for assertion targets.
"""

from pathlib import Path

from scapy.layers.inet import IP, TCP
from scapy.layers.l2 import Ether
from scapy.utils import wrpcap

MAC_CLIENT = "00:11:22:33:44:55"
MAC_SERVER = "66:77:88:99:aa:bb"
IP_CLIENT = "192.168.1.10"
IP_SERVER = "192.168.1.20"
PORT_CLIENT = 50000
PORT_SERVER = 443
SEQ_CLIENT = 100
SEQ_SERVER = 200

OUTPUT = Path(__file__).parent / "known-mac-tcp.pcap"


def build_frames() -> list:
    c_to_s = Ether(src=MAC_CLIENT, dst=MAC_SERVER) / IP(src=IP_CLIENT, dst=IP_SERVER)
    s_to_c = Ether(src=MAC_SERVER, dst=MAC_CLIENT) / IP(src=IP_SERVER, dst=IP_CLIENT)

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
