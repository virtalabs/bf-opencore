"""Read raw TCP stream bytes from stdin, extract MLLP-framed HL7 messages, and dump parsed fields.

Usage:
    cat <stream_file> | python sender.py
"""

import sys
from dataclasses import asdict, dataclass

import hl7

MLLP_START = b"\x0b"
MLLP_END = b"\x1c\x0d"


@dataclass
class HL7Message:
    sending_app: str
    sending_facility: str
    receiving_app: str
    receiving_facility: str
    message_timestamp: str
    message_type: str
    message_id: str
    hl7_version: str
    patient_location: str
    equipment_id: str

    def to_dict(self):
        return asdict(self)


def extract_messages(stream_data: bytes) -> list[str]:
    """Scan raw bytes for MLLP frames and return decoded HL7 message strings."""
    messages = []
    pos = 0
    while pos < len(stream_data):
        start = stream_data.find(MLLP_START, pos)
        if start == -1:
            break
        end = stream_data.find(MLLP_END, start + 1)
        if end == -1:
            break
        raw = stream_data[start + 1 : end].decode("ascii", errors="replace")
        messages.append(raw)
        pos = end + len(MLLP_END)
    return messages


def _field(msg: hl7.Message, segment_id: str, field_num: int) -> str:
    """Safely extract a field from a parsed HL7 message, returning empty string if missing."""
    try:
        seg = msg.segment(segment_id)
        return str(seg(field_num))
    except (KeyError, IndexError):
        return ""


def parse_message(raw: str) -> HL7Message:
    """Parse a raw HL7 message string into an HL7Message dataclass."""
    msg = hl7.parse(raw)
    return HL7Message(
        sending_app=_field(msg, "MSH", 3),
        sending_facility=_field(msg, "MSH", 4),
        receiving_app=_field(msg, "MSH", 5),
        receiving_facility=_field(msg, "MSH", 6),
        message_timestamp=_field(msg, "MSH", 7),
        message_type=_field(msg, "MSH", 9),
        message_id=_field(msg, "MSH", 10),
        hl7_version=_field(msg, "MSH", 12),
        patient_location=_field(msg, "PV1", 3),
        equipment_id=_field(msg, "OBX", 18),
    )


def main():
    stream_data = sys.stdin.buffer.read()
    raw_messages = extract_messages(stream_data)

    if not raw_messages:
        print("No MLLP-framed HL7 messages found in input.")
        return

    for i, raw in enumerate(raw_messages):
        msg = parse_message(raw)
        print(f"--- Message {i + 1} ---")
        for k, v in msg.to_dict().items():
            print(f"  {k}: {v}")
        print()

    print(f"Total: {len(raw_messages)} messages")


if __name__ == "__main__":
    main()
