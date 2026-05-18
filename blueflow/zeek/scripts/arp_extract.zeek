## Emit one record per ARP frame to arp.log.
##
## Stock Zeek 6.x ships no arp.log script -- this fills that gap so the
## conn + arp sidecar can read ARP observations from disk alongside
## conn.log. Mirrors the ARP event handlers in the feature/spike-zeek-channels
## ZeekJS bridge (see spikes/zeek-channels/bridge/send-to-redis.js), but
## emits a log file via Log::write instead of pushing to Redis Streams.
##
## SHA/THA (the hardware addresses inside the ARP payload) are intentionally
## ignored: the Ethernet-header MACs (mac_src/mac_dst) are what the sidecar
## needs to bind a device to an Asset row.
##
## Usage:
##   zeek -Cr <pcap> arp_extract.zeek
##   zeek -i <iface> arp_extract.zeek

module ARP;

export {
    redef enum Log::ID += { LOG };

    type Info: record {
        ts:         time   &log;
        src_mac:    string &log &default="";
        dst_mac:    string &log &default="";
        src_ip:     addr   &log;
        dst_ip:     addr   &log;
        operation:  string &log;
    };
}

event zeek_init() &priority=5 {
    Log::create_stream(ARP::LOG, [$columns=Info, $path="arp"]);
}

event arp_request(mac_src: string, mac_dst: string, SPA: addr, SHA: string,
                  TPA: addr, THA: string) {
    Log::write(ARP::LOG, Info(
        $ts=network_time(),
        $src_mac=mac_src,
        $dst_mac=mac_dst,
        $src_ip=SPA,
        $dst_ip=TPA,
        $operation="REQUEST"
    ));
}

event arp_reply(mac_src: string, mac_dst: string, SPA: addr, SHA: string,
                TPA: addr, THA: string) {
    Log::write(ARP::LOG, Info(
        $ts=network_time(),
        $src_mac=mac_src,
        $dst_mac=mac_dst,
        $src_ip=SPA,
        $dst_ip=TPA,
        $operation="REPLY"
    ));
}
