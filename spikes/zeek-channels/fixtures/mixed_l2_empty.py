#!/usr/bin/env python3
"""F-MIXED-L2-EMPTY generator — produces ``mixed-l2-empty.pcap``.

Composite fixture built by ``mergecap``-ing nine copies of
``known-mac-tcp.pcap`` (3 frames x 9 = 27 L2-bearing frames) together
with one copy of ``loopback-no-l2.pcap`` (4 L2-empty frames). Result is
a single pcap with a known fraction of L2-empty records, used by E.18
(empty-L2 rate detectable).

Requires both prerequisite pcaps to already exist next to this script.
Run ``known_mac_tcp.py`` and ``loopback_no_l2.py`` (or capture the
loopback variant per ``loopback-no-l2.capture-notes.md``) first.

Also requires ``mergecap`` on PATH (ships with wireshark / tshark; on
macOS install via ``brew install wireshark``).

See ``mixed-l2-empty.ground-truth.md`` for the exact L2-empty ratio.
"""

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
IPV4_TCP_PCAP = HERE / "known-mac-tcp.pcap"
LOOPBACK_PCAP = HERE / "loopback-no-l2.pcap"
OUTPUT = HERE / "mixed-l2-empty.pcap"

IPV4_TCP_COPIES = 9
LOOPBACK_COPIES = 1


def main() -> None:
    mergecap = shutil.which("mergecap")
    if mergecap is None:
        sys.exit(
            "mergecap not found on PATH. Install wireshark/tshark "
            "(macOS: brew install wireshark; Linux: apt install wireshark-common).",
        )

    missing = [p for p in (IPV4_TCP_PCAP, LOOPBACK_PCAP) if not p.exists()]
    if missing:
        sys.exit(
            "Prerequisite pcap(s) missing: "
            + ", ".join(str(p) for p in missing)
            + ". Run known_mac_tcp.py and loopback_no_l2.py first.",
        )

    inputs = [str(IPV4_TCP_PCAP)] * IPV4_TCP_COPIES + [
        str(LOOPBACK_PCAP)
    ] * LOOPBACK_COPIES
    cmd = [mergecap, "-F", "pcapng", "-w", str(OUTPUT), *inputs]
    subprocess.run(cmd, check=True)  # noqa: S603


if __name__ == "__main__":
    main()
