#!/usr/bin/env python3
"""F-MINIMAL generator — produces ``minimal-smoke.pcap``.

Five-frame TCP exchange between two known MACs. Smallest fixture that still
produces *some* output through the bridge. Consumed by A.2, A.3, and E.17.

See ``minimal-smoke.ground-truth.md`` for the per-test assertion targets.
"""

from pathlib import Path

from scapy.layers.inet import IP, TCP
from scapy.layers.l2 import Ether
from scapy.packet import Raw
from scapy.utils import wrpcap

MAC_A = "aa:bb:cc:00:00:01"
MAC_B = "aa:bb:cc:00:00:02"
IP_A = "10.0.0.10"
IP_B = "10.0.0.20"
PORT_CLIENT = 40000
PORT_SERVER = 80
SEQ_CLIENT = 1000
SEQ_SERVER = 2000
PAYLOAD = b"GET / HTTP/1.0\r\n\r\n"

OUTPUT = Path(__file__).parent / "minimal-smoke.pcap"


def build_frames() -> list:
    a_to_b = Ether(src=MAC_A, dst=MAC_B) / IP(src=IP_A, dst=IP_B)
    b_to_a = Ether(src=MAC_B, dst=MAC_A) / IP(src=IP_B, dst=IP_A)

    syn = a_to_b / TCP(
        sport=PORT_CLIENT,
        dport=PORT_SERVER,
        flags="S",
        seq=SEQ_CLIENT,
    )
    synack = b_to_a / TCP(
        sport=PORT_SERVER,
        dport=PORT_CLIENT,
        flags="SA",
        seq=SEQ_SERVER,
        ack=SEQ_CLIENT + 1,
    )
    ack = a_to_b / TCP(
        sport=PORT_CLIENT,
        dport=PORT_SERVER,
        flags="A",
        seq=SEQ_CLIENT + 1,
        ack=SEQ_SERVER + 1,
    )
    data = (
        a_to_b
        / TCP(
            sport=PORT_CLIENT,
            dport=PORT_SERVER,
            flags="PA",
            seq=SEQ_CLIENT + 1,
            ack=SEQ_SERVER + 1,
        )
        / Raw(PAYLOAD)
    )
    fin = a_to_b / TCP(
        sport=PORT_CLIENT,
        dport=PORT_SERVER,
        flags="FA",
        seq=SEQ_CLIENT + 1 + len(PAYLOAD),
        ack=SEQ_SERVER + 1,
    )

    return [syn, synack, ack, data, fin]


def main() -> None:
    wrpcap(str(OUTPUT), build_frames())


if __name__ == "__main__":
    main()
