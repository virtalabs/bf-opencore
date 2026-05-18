// Stage 1 ZeekJS bridge: fan-in from multiple Zeek sources -> Redis Streams XADD.
//
// Sources currently wired:
//   conn  -- Conn::log_policy hook; one entry per connection (TCP/UDP/ICMP)
//   arp   -- raw arp_request / arp_reply events; one entry per ARP frame
//
// Every entry on the Stream has a uniform keyset — consumers can read the
// same fields regardless of source and branch on the `source` discriminator.
// Source-specific required fields are enforced at validation time so a
// conn-log record with no uid still drops loudly (preserves the a52bcbf
// guarantee), while ARP records (which legitimately have no uid) don't.
//
// Configuration via environment:
//   REDIS_URL  default redis://localhost:6379
//   STREAM_KEY default zeek:events

const { createClient } = require("redis");

const REDIS_URL = process.env.REDIS_URL || "redis://localhost:6379";
const STREAM_KEY = process.env.STREAM_KEY || "zeek:events";

const client = createClient({ url: REDIS_URL });
client.on("error", (err) => {
  console.error("[bridge] redis client error:", err.message);
});

zeek.on("zeek_init", async () => {
  await client.connect();
  console.log(`[bridge] connected to ${REDIS_URL}, stream=${STREAM_KEY}`);
});

// Per-source required fields. ts is universal. Conn records need the
// 5-tuple + uid to be a meaningful connection observation. ARP records
// need at least one MAC + the operation to be a meaningful L2 observation.
function validate(source, f) {
  if (f.ts === undefined || f.ts === null) return ["ts"];
  if (source === "conn") {
    const missing = [];
    if (!f.uid) missing.push("uid");
    if (!f.src_ip) missing.push("src_ip");
    if (!f.dst_ip) missing.push("dst_ip");
    if (!f.proto) missing.push("proto");
    return missing;
  }
  if (source === "arp") {
    const missing = [];
    if (!f.src_mac && !f.dst_mac) missing.push("src_mac|dst_mac");
    if (!f.operation) missing.push("operation");
    return missing;
  }
  return ["unknown-source"];
}

function emit(source, f) {
  const missing = validate(source, f);
  if (missing.length > 0) {
    console.error(
      `[bridge] dropping malformed ${source} record: missing ${missing.join(", ")}`,
    );
    return;
  }
  // Known gap (see D.14 in spikes/zeek-channels/docs/test-status.md):
  // this .catch() only fires for per-command rejections of xAdds that
  // were already in flight when the failure occurred (e.g. an
  // ECONNRESET after the bytes hit the socket). It does NOT cover the
  // node-redis@4 offlineQueue -- xAdds issued while the client is
  // disconnected go into a queue and sit there until reconnection. If
  // the client gives up reconnecting OR client.quit() is called before
  // it reconnects, those queued commands drop silently without
  // rejecting their promises, so this .catch() never fires for them.
  // Under sustained redis loss the bridge silently loses ~99% of data;
  // only the small set of in-flight writes at the moment of failure
  // surface an error. Fix requires a bounded retry-strategy + explicit
  // offlineQueue flush-and-reject on quit (see node-redis socket
  // options reconnectStrategy and disableOfflineQueue).
  client
    .xAdd(STREAM_KEY, "*", {
      source,
      ts: String(f.ts),
      uid: f.uid ?? "",
      src_ip: f.src_ip ?? "",
      dst_ip: f.dst_ip ?? "",
      src_mac: f.src_mac ?? "",
      dst_mac: f.dst_mac ?? "",
      proto: f.proto ?? "",
      service: f.service ?? "",
      duration: f.duration ?? "",
      operation: f.operation ?? "",
    })
    .catch((err) => {
      console.error("[bridge] xAdd failed:", err.message);
    });
}

zeek.hook("Conn::log_policy", (rec, _id, _filter) => {
  // Field nesting reminder (see prior commits 2e4ee21 / a22da90):
  //   - 5-tuple (orig_h/resp_h/...) is nested under rec.id
  //   - mac-logging fields (orig_l2_addr/resp_l2_addr) are flat on rec
  emit("conn", {
    ts: rec.ts,
    uid: rec.uid,
    src_ip: rec.id?.orig_h,
    dst_ip: rec.id?.resp_h,
    src_mac: rec.orig_l2_addr,
    dst_mac: rec.resp_l2_addr,
    proto: rec.proto,
    service: rec.service,
    duration: rec.duration !== undefined ? String(rec.duration) : "",
  });
});

// Raw ARP events. Stock Zeek 6.x has no arp.log script, so the bridge
// IS the log policy for ARP. SPA/TPA are protocol addrs (IPs), SHA/THA
// are payload hardware addrs; for C.8's "MAC appears on the stream"
// assertion the Ethernet header MACs (mac_src/mac_dst) are what matter.
zeek.on("arp_request", (mac_src, mac_dst, SPA, _SHA, TPA, _THA) => {
  emit("arp", {
    ts: zeek.invoke("network_time"),
    src_ip: SPA,
    dst_ip: TPA,
    src_mac: mac_src,
    dst_mac: mac_dst,
    proto: "arp",
    operation: "REQUEST",
  });
});

zeek.on("arp_reply", (mac_src, mac_dst, SPA, _SHA, TPA, _THA) => {
  emit("arp", {
    ts: zeek.invoke("network_time"),
    src_ip: SPA,
    dst_ip: TPA,
    src_mac: mac_src,
    dst_mac: mac_dst,
    proto: "arp",
    operation: "REPLY",
  });
});

zeek.on("zeek_done", async () => {
  try {
    await client.quit();
    console.log("[bridge] redis client closed");
  } catch (err) {
    console.error("[bridge] error closing redis:", err.message);
  }
});
