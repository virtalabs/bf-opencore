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
  client
    .xAdd(STREAM_KEY, "*", {
      ts: String(rec.ts ?? ""),
      uid: rec.uid ?? "",
      src_ip: rec.id?.orig_h ?? "",
      dst_ip: rec.id?.resp_h ?? "",
      src_mac: rec.id?.orig_l2_addr ?? "",
      dst_mac: rec.id?.resp_l2_addr ?? "",
      proto: rec.proto ?? "",
      service: rec.service ?? "",
      duration: String(rec.duration ?? 0),
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
