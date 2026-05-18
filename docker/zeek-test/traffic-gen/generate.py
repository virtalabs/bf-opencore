#!/usr/bin/env python3
"""Synthesize ARP + TCP traffic for the zeek-probe compose test.

Sends two storylines on the interface shared with zeek-probe:

1. ARP-only device discovery -- the spike's flagship case. A target
   MAC (de:ad:be:ef:00:01) sends one ARP request and never produces
   any IP traffic. A conn-log-only consumer would miss it. The conn +
   arp sidecar should still emit it as an Asset because arp_extract.zeek
   captured the SPA->SHA binding.

2. TCP open-port discovery. A client opens connections on :80 and :443
   to a server. Full handshake + FIN teardown is sent so Zeek records
   the connection at connection_state_remove and id.resp_p lands in
   conn.log -- otherwise the sidecar would have to wait for Zeek's
   default 5-minute inactivity timeout.

After sending, waits for at least one zeek-probe push cycle, then GETs
/api/assets/ on the BlueFlow service and prints the materialized
assets. Exits 0 on success so `--abort-on-container-exit` brings the
whole compose down cleanly.
"""

import json
import os
import sys
import time
import urllib.request

from scapy.all import ARP, IP, TCP, Ether, sendp

IFACE = "eth0"

ARP_TARGET_MAC = "de:ad:be:ef:00:01"
ARP_TARGET_IP = "10.0.0.5"
ARP_GATEWAY_MAC = "00:50:56:c0:00:01"
ARP_GATEWAY_IP = "10.0.0.1"

TCP_CLIENT_MAC = "00:11:22:33:44:55"
TCP_CLIENT_IP = "10.0.0.20"
TCP_SERVER_MAC = "aa:bb:cc:dd:ee:ff"
TCP_SERVER_IP = "10.0.0.50"


def banner(msg: str) -> None:
    print(f"[traffic-gen] {msg}", flush=True)  # noqa: T201


def send_arp_only() -> None:
    """Replay the arp-only.pcap storyline: target MAC visible only via ARP."""
    banner(
        f"ARP REQUEST  {ARP_TARGET_MAC} ({ARP_TARGET_IP}) -> who-has {ARP_GATEWAY_IP}"
    )
    req = Ether(src=ARP_TARGET_MAC, dst="ff:ff:ff:ff:ff:ff") / ARP(
        op=1,
        hwsrc=ARP_TARGET_MAC,
        psrc=ARP_TARGET_IP,
        hwdst="00:00:00:00:00:00",
        pdst=ARP_GATEWAY_IP,
    )
    sendp(req, iface=IFACE, verbose=False)

    banner(
        f"ARP REPLY    {ARP_GATEWAY_MAC} ({ARP_GATEWAY_IP})"
        f" -> is-at -> {ARP_TARGET_MAC}"
    )
    rep = Ether(src=ARP_GATEWAY_MAC, dst=ARP_TARGET_MAC) / ARP(
        op=2,
        hwsrc=ARP_GATEWAY_MAC,
        psrc=ARP_GATEWAY_IP,
        hwdst=ARP_TARGET_MAC,
        pdst=ARP_TARGET_IP,
    )
    sendp(rep, iface=IFACE, verbose=False)


def send_tcp_session(sport: int, dport: int) -> None:
    """Full TCP handshake + close so Zeek logs the connection promptly."""
    banner(
        f"TCP          {TCP_CLIENT_MAC} ({TCP_CLIENT_IP}):{sport}"
        f" <-> {TCP_SERVER_MAC} ({TCP_SERVER_IP}):{dport}"
        f"  (SYN/SYN-ACK/ACK/FIN/FIN-ACK)"
    )
    eth_out = Ether(src=TCP_CLIENT_MAC, dst=TCP_SERVER_MAC)
    eth_in = Ether(src=TCP_SERVER_MAC, dst=TCP_CLIENT_MAC)
    ip_out = IP(src=TCP_CLIENT_IP, dst=TCP_SERVER_IP)
    ip_in = IP(src=TCP_SERVER_IP, dst=TCP_CLIENT_IP)
    seq_c, seq_s = 1000, 2000

    syn = eth_out / ip_out / TCP(sport=sport, dport=dport, flags="S", seq=seq_c)
    syn_ack = (
        eth_in
        / ip_in
        / TCP(sport=dport, dport=sport, flags="SA", seq=seq_s, ack=seq_c + 1)
    )
    ack = (
        eth_out
        / ip_out
        / TCP(sport=sport, dport=dport, flags="A", seq=seq_c + 1, ack=seq_s + 1)
    )
    fin = (
        eth_out
        / ip_out
        / TCP(sport=sport, dport=dport, flags="FA", seq=seq_c + 1, ack=seq_s + 1)
    )
    fin_ack = (
        eth_in
        / ip_in
        / TCP(sport=dport, dport=sport, flags="FA", seq=seq_s + 1, ack=seq_c + 2)
    )
    sendp([syn, syn_ack, ack, fin, fin_ack], iface=IFACE, verbose=False)


def main() -> None:
    # Give zeek-probe a moment to start capturing before we send anything.
    banner("waiting 3s for zeek to settle...")
    time.sleep(3)

    banner("=" * 60)
    banner("Scenario 1: ARP-only device discovery")
    banner("=" * 60)
    send_arp_only()
    time.sleep(1)

    banner("=" * 60)
    banner("Scenario 2: TCP open-port discovery")
    banner("=" * 60)
    send_tcp_session(sport=54321, dport=80)
    time.sleep(0.5)
    send_tcp_session(sport=54322, dport=443)

    wait_for = int(os.environ.get("VERIFY_WAIT_SECONDS", "20"))
    banner(f"waiting {wait_for}s for zeek to push to BlueFlow...")
    time.sleep(wait_for)

    blueflow_url = os.environ.get("BLUEFLOW_URL", "http://blueflow:8000")
    fetch_url = f"{blueflow_url.rstrip('/')}/api/assets/?limit=100"
    banner("=" * 60)
    banner(f"GET {fetch_url}")
    banner("=" * 60)
    try:
        with urllib.request.urlopen(fetch_url, timeout=10) as resp:  # noqa: S310
            body = json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        banner(f"FAIL: could not fetch assets: {exc}")
        sys.exit(1)

    results = body.get("results", body if isinstance(body, list) else [])
    banner(f"BlueFlow has {len(results)} asset(s):")
    for asset in results:
        mac = asset.get("mac_address", "?")
        ip = asset.get("ip_address", "(none)")
        ports = asset.get("open_ports_tcp", [])
        banner(f"  mac={mac}  ip={ip}  ports={ports}")

    banner("=" * 60)
    banner("done.")
    sys.exit(0)


if __name__ == "__main__":
    main()
