// Stage 1 ZeekJS bridge: Conn::log_policy hook -> Redis Streams XADD.
//
// Reads from Zeek's bundled JavaScript runtime (in-tree since v6.0). Emits
// one XADD entry per conn-log record onto the `zeek:events` stream. The
// payload contract here is the bridge/consumer integration boundary --
// alterations should be co-ordinated with the Django XREADGROUP consumer.
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

zeek.hook("Conn::log_policy", (rec, _id, _filter) => {
  // Required fields. A conn-log record without any of these is malformed;
  // dropping noisily beats writing empties downstream, where they'd
  // pollute Asset upserts and erase the signal that something is broken
  // (this exact pattern was hiding a field-access bug previously).
  const ts = rec.ts;
  const uid = rec.uid;
  const srcIp = rec.id?.orig_h;
  const dstIp = rec.id?.resp_h;
  const proto = rec.proto;

  const missing = [];
  if (ts === undefined || ts === null) missing.push("ts");
  if (!uid) missing.push("uid");
  if (!srcIp) missing.push("id.orig_h");
  if (!dstIp) missing.push("id.resp_h");
  if (!proto) missing.push("proto");

  if (missing.length > 0) {
    console.error(
      `[bridge] dropping malformed conn-log record: missing ${missing.join(", ")}`,
    );
    return;
  }

  // Optional fields -- empty here is legitimate, not a bug signal:
  //   service: Zeek may not identify the application protocol.
  //   id.orig_l2_addr / id.resp_l2_addr: only populated when
  //     policy/protocols/conn/mac-logging is @load'd (see B.4 follow-up).
  //   duration: absent for in-flight connections. 0 is a real value
  //     (instantaneous flows), so don't conflate "missing" with "zero".
  client
    .xAdd(STREAM_KEY, "*", {
      ts: String(ts),
      uid,
      src_ip: srcIp,
      dst_ip: dstIp,
      src_mac: rec.id?.orig_l2_addr ?? "",
      dst_mac: rec.id?.resp_l2_addr ?? "",
      proto,
      service: rec.service ?? "",
      duration: rec.duration !== undefined ? String(rec.duration) : "",
    })
    .catch((err) => {
      console.error("[bridge] xAdd failed:", err.message);
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
