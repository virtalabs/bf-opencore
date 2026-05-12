#!/usr/bin/env python3
"""F-DHCP-DORA generator — produces ``dhcp-dora.pcap``.

A full DHCP DORA exchange (Discover / Offer / Request / Ack) where the
client's MAC is visible in *both* the L2 Ethernet header and the BOOTP
``chaddr`` payload field. Used by C.9 (DHCP-discovered devices captured).

The test asserts the client MAC appears in the resulting Stream entry
even though at DISCOVER time the client has no IP yet — verifying that
L2 discovery does not require L3 state.

See ``dhcp-dora.ground-truth.md`` for assertion targets.
"""

from pathlib import Path

from scapy.layers.dhcp import BOOTP, DHCP
from scapy.layers.inet import IP, UDP
from scapy.layers.l2 import Ether
from scapy.utils import mac2str, wrpcap

CLIENT_MAC = "ca:fe:ba:be:00:42"
SERVER_MAC = "00:50:56:0d:c0:01"
CLIENT_IP_OFFERED = "10.0.0.50"
SERVER_IP = "10.0.0.1"
SUBNET_MASK = "255.255.255.0"
LEASE_SECONDS = 3600
BROADCAST_MAC = "ff:ff:ff:ff:ff:ff"
BROADCAST_IP = "255.255.255.255"
UNASSIGNED_IP = "0.0.0.0"  # noqa: S104 — DHCP-protocol-mandated unassigned IP, not a socket bind
DHCP_CLIENT_PORT = 68
DHCP_SERVER_PORT = 67
BOOTREQUEST = 1
BOOTREPLY = 2
TRANSACTION_ID = 0x12345678

OUTPUT = Path(__file__).parent / "dhcp-dora.pcap"


def _client_chaddr() -> bytes:
    # BOOTP.chaddr is a 16-byte fixed field; scapy pads NUL but we set
    # it explicitly so the byte layout is auditable from the script.
    return mac2str(CLIENT_MAC) + b"\x00" * 10


def _client_to_server() -> Ether:
    return (
        Ether(src=CLIENT_MAC, dst=BROADCAST_MAC)
        / IP(src=UNASSIGNED_IP, dst=BROADCAST_IP)
        / UDP(sport=DHCP_CLIENT_PORT, dport=DHCP_SERVER_PORT)
    )


def _server_to_client() -> Ether:
    return (
        Ether(src=SERVER_MAC, dst=CLIENT_MAC)
        / IP(src=SERVER_IP, dst=CLIENT_IP_OFFERED)
        / UDP(sport=DHCP_SERVER_PORT, dport=DHCP_CLIENT_PORT)
    )


def build_frames() -> list:
    chaddr = _client_chaddr()

    discover = (
        _client_to_server()
        / BOOTP(
            op=BOOTREQUEST,
            chaddr=chaddr,
            xid=TRANSACTION_ID,
        )
        / DHCP(options=[("message-type", "discover"), "end"])
    )

    offer = (
        _server_to_client()
        / BOOTP(
            op=BOOTREPLY,
            chaddr=chaddr,
            xid=TRANSACTION_ID,
            yiaddr=CLIENT_IP_OFFERED,
            siaddr=SERVER_IP,
        )
        / DHCP(
            options=[
                ("message-type", "offer"),
                ("server_id", SERVER_IP),
                ("lease_time", LEASE_SECONDS),
                ("subnet_mask", SUBNET_MASK),
                "end",
            ]
        )
    )

    request = (
        _client_to_server()
        / BOOTP(
            op=BOOTREQUEST,
            chaddr=chaddr,
            xid=TRANSACTION_ID,
        )
        / DHCP(
            options=[
                ("message-type", "request"),
                ("requested_addr", CLIENT_IP_OFFERED),
                ("server_id", SERVER_IP),
                "end",
            ]
        )
    )

    ack = (
        _server_to_client()
        / BOOTP(
            op=BOOTREPLY,
            chaddr=chaddr,
            xid=TRANSACTION_ID,
            yiaddr=CLIENT_IP_OFFERED,
            siaddr=SERVER_IP,
        )
        / DHCP(
            options=[
                ("message-type", "ack"),
                ("server_id", SERVER_IP),
                ("lease_time", LEASE_SECONDS),
                ("subnet_mask", SUBNET_MASK),
                "end",
            ]
        )
    )

    return [discover, offer, request, ack]


def main() -> None:
    wrpcap(str(OUTPUT), build_frames())


if __name__ == "__main__":
    main()
