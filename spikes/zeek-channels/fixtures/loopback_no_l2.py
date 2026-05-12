#!/usr/bin/env python3
"""F-LOOPBACK generator — produces ``loopback-no-l2.pcap`` (synth fallback).

A pcap with BSD ``DLT_NULL`` linktype (4-byte address-family header, no
Ethernet). Zeek records derived from this fixture will have unset L2
fields, which is the point.

============================================================
PREFER CAPTURE OVER THIS SCRIPT.
============================================================
The plan recommends capturing via ``tcpdump -i lo`` instead — see
``loopback-no-l2.capture-notes.md``. The captured pcap is more authentic
(real linktype on the local interface, real timing) and the workflow is
shorter. This script exists as a fallback for environments where running
tcpdump on ``lo`` is inconvenient (e.g., CI without privileged access).

Used by B.6 (empty / missing L2 fields handled).

See ``loopback-no-l2.ground-truth.md`` for assertion targets.
"""

from pathlib import Path

from scapy.layers.inet import IP, TCP
from scapy.layers.l2 import Loopback
from scapy.packet import Raw
from scapy.utils import PcapWriter

LOCALHOST = "127.0.0.1"
PORT_CLIENT = 52000
PORT_SERVER = 8080
SEQ_CLIENT = 9000
SEQ_SERVER = 9500
PAYLOAD = b"hello"

DLT_NULL = 0
AF_INET = 2  # BSD AF_INET — the value stamped into the 4-byte family header

OUTPUT = Path(__file__).parent / "loopback-no-l2.pcap"


def build_frames() -> list:
    base = Loopback(type=AF_INET) / IP(src=LOCALHOST, dst=LOCALHOST)
    syn = base / TCP(
        sport=PORT_CLIENT,
        dport=PORT_SERVER,
        flags="S",
        seq=SEQ_CLIENT,
    )
    synack = base / TCP(
        sport=PORT_SERVER,
        dport=PORT_CLIENT,
        flags="SA",
        seq=SEQ_SERVER,
        ack=SEQ_CLIENT + 1,
    )
    ack = base / TCP(
        sport=PORT_CLIENT,
        dport=PORT_SERVER,
        flags="A",
        seq=SEQ_CLIENT + 1,
        ack=SEQ_SERVER + 1,
    )
    data = (
        base
        / TCP(
            sport=PORT_CLIENT,
            dport=PORT_SERVER,
            flags="PA",
            seq=SEQ_CLIENT + 1,
            ack=SEQ_SERVER + 1,
        )
        / Raw(PAYLOAD)
    )

    return [syn, synack, ack, data]


def main() -> None:
    # PcapWriter is used here (not wrpcap) because we need to force
    # DLT_NULL — the loopback linktype — rather than the default DLT_EN10MB.
    with PcapWriter(str(OUTPUT), linktype=DLT_NULL) as writer:
        for frame in build_frames():
            writer.write(frame)


if __name__ == "__main__":
    main()
