## Zeek script for HL7 message extraction from MLLP frames.
##
## Parses HL7 v2.x fields from MLLP-framed messages and writes them to hl7.log.
## Designed to produce equivalent output to spikes/hl7/extract.py.
##
## Usage:
##   zeek -Cr <pcap> mllp.spicy mllp.evt hl7_extract.zeek
##   zeek -i <iface> mllp.spicy mllp.evt hl7_extract.zeek

module HL7;

export {
    redef enum Log::ID += { LOG };

    type Info: record {
        ts:                  time     &log;
        uid:                 string   &log;
        id:                  conn_id  &log;
        is_orig:             bool     &log;
        sending_app:         string   &log &default="";
        sending_facility:    string   &log &default="";
        receiving_app:       string   &log &default="";
        receiving_facility:  string   &log &default="";
        message_timestamp:   string   &log &default="";
        message_type:        string   &log &default="";
        message_id:          string   &log &default="";
        hl7_version:         string   &log &default="";
        patient_location:    string   &log &default="";
        equipment_id:        string   &log &default="";
    };
}

event zeek_init() &priority=5 {
    Log::create_stream(HL7::LOG, [$columns=Info, $path="hl7"]);
}

# Extract a field from an HL7 segment line by field index (1-based, pipe-delimited).
function extract_field(segment: string, field_num: count): string {
    local parts = split_string(segment, /\|/);
    if ( field_num < |parts| )
        return parts[field_num];
    return "";
}

# Find a segment by its 3-character ID (e.g. "MSH", "PV1", "OBX").
function find_segment(segments: vector of string, seg_id: string): string {
    for ( i in segments ) {
        if ( |segments[i]| >= 3 && segments[i][:3] == seg_id )
            return segments[i];
    }
    return "";
}

event mllp_message(c: connection, is_orig: bool, payload: string) {
    local segments = split_string(payload, /\r/);

    local msh = find_segment(segments, "MSH");
    if ( msh == "" )
        return;

    local msg_type = extract_field(msh, 8);

    # MSH-9 may be composite (e.g. "ACK^A01^ACK"); only the first component
    # carries the message code, so split on '^' before comparing.
    local msg_kind = split_string(msg_type, /\^/)[0];
    if ( msg_kind == "ACK" )
        return;

    local pv1 = find_segment(segments, "PV1");
    local obx = find_segment(segments, "OBX");

    local info = Info(
        $ts=network_time(),
        $uid=c$uid,
        $id=c$id,
        $is_orig=is_orig,
        $sending_app=extract_field(msh, 2),
        $sending_facility=extract_field(msh, 3),
        $receiving_app=extract_field(msh, 4),
        $receiving_facility=extract_field(msh, 5),
        $message_timestamp=extract_field(msh, 6),
        $message_type=msg_type,
        $message_id=extract_field(msh, 9),
        $hl7_version=extract_field(msh, 11)
    );

    if ( pv1 != "" )
        info$patient_location = extract_field(pv1, 3);

    if ( obx != "" )
        info$equipment_id = extract_field(obx, 18);

    Log::write(HL7::LOG, info);
}
