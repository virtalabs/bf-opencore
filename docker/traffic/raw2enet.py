#!/usr/bin/env python3
"""Convert a Raw IP pcap to Ethernet-framed pcap.

Reads a pcap with DLT_RAW (link type 101) and writes a new pcap with
DLT_EN10MB (link type 1), prepending a 14-byte Ethernet header to each
packet. Needed because tcpreplay requires Ethernet framing for veth pairs.

Usage:
    python3 raw2enet.py input.pcap output.pcap
"""

import struct
import sys
from pathlib import Path

# pcap global header: magic, version_major, version_minor, thiszone,
# sigfigs, snaplen, network
GLOBAL_HDR_FMT = "<IHHiIII"
GLOBAL_HDR_SIZE = struct.calcsize(GLOBAL_HDR_FMT)

# pcap packet header: ts_sec, ts_usec, incl_len, orig_len
PKT_HDR_FMT = "<IIII"
PKT_HDR_SIZE = struct.calcsize(PKT_HDR_FMT)

# Fake Ethernet header: dst(6) + src(6) + ethertype(2)
ETHER_IPV4 = b"\x00\x00\x00\x00\x00\x01" + b"\x00\x00\x00\x00\x00\x02" + b"\x08\x00"
ETHER_IPV6 = b"\x00\x00\x00\x00\x00\x01" + b"\x00\x00\x00\x00\x00\x02" + b"\x86\xdd"
ETHER_HDR_LEN = 14

DLT_EN10MB = 1
IP_VERSION_6 = 6
EXPECTED_ARGC = 3


def convert(inpath, outpath):
    with Path(inpath).open("rb") as fin, Path(outpath).open("wb") as fout:
        ghdr = fin.read(GLOBAL_HDR_SIZE)
        magic, vmaj, vmin, tz, sigfigs, snaplen, _ = struct.unpack(GLOBAL_HDR_FMT, ghdr)

        # Write new global header with Ethernet link type
        fout.write(
            struct.pack(
                GLOBAL_HDR_FMT,
                magic,
                vmaj,
                vmin,
                tz,
                sigfigs,
                snaplen + ETHER_HDR_LEN,
                DLT_EN10MB,
            )
        )

        count = 0
        while True:
            phdr = fin.read(PKT_HDR_SIZE)
            if len(phdr) < PKT_HDR_SIZE:
                break
            ts_sec, ts_usec, incl_len, orig_len = struct.unpack(PKT_HDR_FMT, phdr)
            data = fin.read(incl_len)
            if len(data) < incl_len:
                break

            # Pick ethertype based on IP version nibble
            ip_version = (data[0] >> 4) if data else 0
            ether_hdr = ETHER_IPV6 if ip_version == IP_VERSION_6 else ETHER_IPV4

            fout.write(
                struct.pack(
                    PKT_HDR_FMT,
                    ts_sec,
                    ts_usec,
                    incl_len + ETHER_HDR_LEN,
                    orig_len + ETHER_HDR_LEN,
                )
            )
            fout.write(ether_hdr)
            fout.write(data)
            count += 1

    return count


if __name__ == "__main__":
    if len(sys.argv) != EXPECTED_ARGC:
        print(f"Usage: {sys.argv[0]} input.pcap output.pcap")  # noqa: T201
        sys.exit(1)
    n = convert(sys.argv[1], sys.argv[2])
    print(f"Converted {n} packets: Raw IP -> Ethernet")  # noqa: T201
