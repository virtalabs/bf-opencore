# SPIKE: Existing Solutions for Similar Telemetry Ingestion Problems

**Date:** 2026-05-08
**Status:** Survey — descriptive, not prescriptive.
**Companion docs:**
- [zeek-and-channels-ideal-usage.md](zeek-and-channels-ideal-usage.md) — how each system wants to be used in isolation
- [zeek-to-django-integration-options.md](zeek-to-django-integration-options.md) — the four options under consideration

---

## Why this document exists

Before committing to one of the four options in the integration analysis, it is worth asking: *who has already solved this shape, and what shape did they converge on?* Network telemetry ingestion into a structured store is not a novel problem. Many systems — open source and commercial — have thought hard about it.

The goal here is not to find a tool to drop in. BlueFlow is an asset-management product, not a SIEM, and most of the solutions surveyed below have a different north star. The goal is to extract **patterns** that mature stacks converge on, validate our option analysis against those patterns, and notice if any survey item collapses to a clear "use X off the shelf" answer.

Knowledge-cutoff caveat: this survey reflects publicly documented states as of early 2026. Several of these projects iterate quickly; verify current architecture before committing to any specific tool.

### What this document is NOT

- **Not a buy-vs-build recommendation.** That decision depends on commercial terms, support requirements, and product positioning — none of which a written spike resolves.
- **Not exhaustive.** Adjacent categories (enterprise SIEMs, tracing-specific tooling, packet-capture archival) are intentionally out of scope; their lessons don't transfer to BlueFlow's scale or telemetry shape.
- **Not a competitive analysis.** Where commercial products are mentioned, they are referenced for architectural lessons, not market positioning.

---

## Categories surveyed

1. **Direct comparisons** — Zeek-based NSM/AMP stacks. Closest to the BlueFlow problem.
2. **Generic ingestion shippers** — the "bridge process" layer in our Option D, generalized. Production-grade alternatives to a custom Python tailer.
3. **App-side ingestion patterns** — high-volume application-layer event ingestion (Sentry, PostHog, Loki). Lessons for the consumer side.
4. **Pattern extraction** — what the survey reveals as universal shapes and recurring antipatterns.
5. **Implications for the four-option analysis.**

---

## 1. Direct comparisons — Zeek-based NSM/AMP stacks

### 1.1 Security Onion

A free, open-source security-monitoring distribution that bundles Zeek, Suricata, and Wazuh into a turnkey sensor and analyst workstation.

**Ingestion shape (publicly documented):**

```
Zeek → JSON logs → Filebeat → Logstash (or Elastic Agent) →
Elasticsearch / OpenSearch → Kibana / SOC interface
```

- **Bridge:** Filebeat (file tailer) — Elastic-stack default; battle-tested rotation handling; explicit acknowledgment back to Logstash.
- **Buffer:** Logstash queues internally (memory or persistent file-backed); Elasticsearch itself absorbs spikes via its bulk-index API.
- **Consumer:** Logstash pipelines parse and enrich; Elasticsearch is the durable store.
- **Fan-out:** Kibana over HTTP for analysts; no live push to browsers in the default stack.

**Lessons for BlueFlow:**

- The Filebeat → Logstash pattern is essentially Option D with Filebeat as the bridge and Logstash as the consumer — but with a search index as the destination instead of a relational asset model. The shape is the same.
- The durable buffer lives between bridge and consumer (Logstash queue, then Elasticsearch's own buffering). Two layers of durability, not one.
- Security Onion does not try to be an asset-management product. It is a *log search and detection* system. Reusing it wholesale would put BlueFlow's data in a search index, not a structured asset model — wrong tool for this product.

### 1.2 Corelight (commercial)

Commercial productization of Zeek by the project's original authors. Sells appliance-style sensors plus an investigation/analytics platform.

**Ingestion shape (from public marketing and a few engineering blog posts):**

```
Zeek (on Corelight Sensor) → JSON or binary export →
Corelight Investigator / Splunk / Elastic / customer's SIEM
```

- Sensors run a hardened Zeek build; export goes over network to one of several supported destinations.
- Internals of the Investigator product are not public; from the outside it is "another SIEM-shaped consumer."

**Lessons for BlueFlow:**

- The "Zeek runs on a sensor; output ships over the network to a destination of choice" model is the dominant shape for productized Zeek. This is what BlueFlow likely looks like long-term: a sensor process with a single export path.
- Corelight monetizes the *sensor + curated detections + investigation UI* triple. BlueFlow's monetization is asset management, which is a different value proposition. The ingestion path can borrow ideas; the product cannot.
- The lack of public architecture detail means specific lessons here are limited to "yes, productized Zeek exists and uses standard SIEM transports."

### 1.3 Malcolm (CISA)

Open-source network traffic analysis suite from CISA, packaged as a Docker Compose stack. Bundles Zeek, Suricata, Arkime, and OpenSearch.

**Ingestion shape:**

```
Zeek + Suricata → JSON logs → Filebeat → Logstash →
OpenSearch → Dashboards UI / Arkime UI
```

- Same general pattern as Security Onion but with explicit Docker packaging and CISA-curated dashboards.
- Logstash performs significant enrichment (GeoIP, threat-intel correlation) before indexing.

**Lessons for BlueFlow:**

- Validates the Filebeat → Logstash → search-index pattern as the *de facto* default for OSS Zeek deployments.
- The enrichment-in-Logstash step is interesting: detection logic and IP-to-asset correlation happens at the consumer, not at Zeek. BlueFlow would do similar work in the consumer (Asset upsert with enrichment from CMDB-style tables).
- Same caveat as Security Onion: search-index destination, not asset model.

### 1.4 Arkime (formerly Moloch)

Full-packet-capture and session indexer. Originally Moloch; renamed to Arkime when it moved to a vendor-supported model. Captures pcap, decodes via its own engine (and increasingly via Zeek/Suricata integration), indexes session metadata in OpenSearch.

**Ingestion shape:**

```
Network capture → Arkime capture daemon → OpenSearch (sessions index)
                                       → S3 / disk (pcap files)
```

- Capture daemon writes session metadata directly to OpenSearch via bulk index API.
- Pcap is written to local disk or object storage; sessions reference offsets.

**Lessons for BlueFlow:**

- Arkime is a counter-example: it skips a buffer entirely and writes to the destination index in real time. Possible because OpenSearch's bulk API absorbs back-pressure.
- This is the equivalent of "Zeek → Django ORM directly, no buffer" — workable when the destination can handle the write rate. PostgreSQL with `update_or_create` can probably handle BlueFlow's volume similarly, which is exactly Option C's bet.
- Arkime's separation of *metadata* (indexed for fast search) and *raw payload* (cheap object storage) is a useful pattern even when the payloads are different. For BlueFlow, the analog might be Asset records (PostgreSQL) plus raw Zeek log archive (object storage / cheap disk) for forensic replay.

### 1.5 Apache Metron (archived)

Defunct Apache project that aimed to be the open-source SIEM platform. Used Zeek's Kafka writer plugin to feed events into a Kafka-based stream-processing pipeline (Storm, Spark) and ultimately HDFS / HBase.

**Lessons for BlueFlow:**

- Notable because Metron is the *origin* of the Zeek → Kafka writer plugin that still exists. The plugin is more mature than the project that motivated it.
- The Metron architecture (Kafka + Storm + HDFS) is overbuilt for any small-hospital deployment. Mentioned because the *plugin* is real and could be a bridge mechanism for Option D — Kafka instead of Streams — at higher scale.
- Project's archival is itself a lesson: stream-processing-first architectures need scale to justify their operational cost. BlueFlow does not have that scale today.

---

## 2. Generic ingestion shippers — candidates for the bridge slot

These are the production-grade alternatives to "a custom Python file tailer." Any of them could fill the bridge role in Option D (or, frankly, in B-tail).

### 2.1 Vector (Datadog, OSS)

Written in Rust. Single static binary. Designed as a unified observability data pipeline — sources, transforms, sinks — with very low resource footprint.

**Relevant features:**

- File source with proper rotation handling, gzip support, fingerprint-based dedup across rotations.
- Redis sink, including Streams (`XADD`), with at-least-once delivery and configurable retry.
- Disk buffers for sources or sinks — survives Vector restarts without losing events.
- Built-in observability: metrics endpoint, internal logs, configurable verbosity.
- VRL (Vector Remap Language) for in-flight transforms — strip fields, reshape, drop noisy events before they hit the buffer.

**Fit for Option D:**

- Direct replacement for the custom Python bridge. Vector tails Zeek logs and writes to Redis Streams; the BlueFlow side reads `XREADGROUP`.
- Buys you rotation handling, retry/backoff, observability, and per-source disk buffers without writing or maintaining any of that.
- Cost: one more daemon to operate. Smaller than a JVM-based shipper, larger than zero.

**Caveats:**

- Vector's Redis Streams sink works but is less commonly cited than Kafka or HTTP sinks. Test under load before committing.
- VRL is a real DSL with real syntax to learn. Adequate documentation but not zero-cost.

### 2.2 Fluent Bit

Written in C. Even smaller footprint than Vector — designed for edge / embedded / sidecar use. CNCF-graduated.

**Relevant features:**

- File source (`tail` plugin) with rotation handling and offset persistence.
- Output plugins for HTTP, Kafka, OpenSearch, S3, and many more.
- Lua scripting for custom transforms.
- Redis output plugin exists but is *not* the focus of the project; less mature than Kafka or HTTP outputs.

**Fit for Option D:**

- Workable but Vector is a better match because its Redis Streams support is more first-class.
- Better fit if the bridge target becomes HTTP (POSTing batches to a Django endpoint) or Kafka.

**Caveats:**

- The Fluent Bit ecosystem has historically prioritized Kafka and Elasticsearch outputs. Redis Streams is supported but not headline.

### 2.3 Logstash (Elastic)

Written in JRuby on the JVM. The original "ingestion pipeline" tool; still common in Elastic-stack deployments. Used by Security Onion and Malcolm.

**Relevant features:**

- Mature file input with rotation handling.
- Hundreds of input/output plugins; Redis output supports Streams.
- Persistent queue between input and output stages — durable buffer built in.
- Powerful filter chain (Grok, mutate, ruby).

**Fit for Option D:**

- Capable but heavy. JVM footprint is unjustifiable for a small-hospital sensor when Vector or Fluent Bit can do the same job at a fraction of the resources.
- Mentioned because BlueFlow operators familiar with Elastic stacks may default to Logstash; the survey is partly to head off that default.

**Caveats:**

- Resource cost is real. A Logstash instance is ~200MB+ baseline; Vector is ~30MB.

### 2.4 OpenTelemetry Collector

CNCF project that has become the standard for vendor-neutral telemetry collection. Originally trace-focused; now solidly handles metrics and logs as well.

**Relevant features:**

- File log receiver (`filelog`) with rotation handling.
- Exporters for OTLP, Kafka, many SIEMs. Redis is *not* a first-class exporter as of writing.
- Processors for batching, filtering, attribute manipulation.
- Designed for log-as-event-stream, not log-as-text-search.

**Fit for Option D:**

- Awkward. Without a first-class Redis Streams exporter, OTel Collector would either need a custom exporter or a Kafka detour. Not the right tool today.
- Worth tracking: the OTel ecosystem is moving fast and Redis support may improve.

**Caveats:**

- The "collector" role here is generic — OTel's appeal is when other systems also speak OTLP, which is not yet true in the Zeek world.

### 2.5 Comparison summary for the bridge slot

| Shipper | Footprint | Rotation handling | Redis Streams sink | When to pick it |
|---|---|---|---|---|
| **Vector** | ~30MB | First-class | First-class | Default choice for Option D's bridge |
| **Fluent Bit** | ~15MB | First-class | Functional, not headline | When HTTP-batch or Kafka is the target instead |
| **Logstash** | ~200MB+ JVM | First-class | First-class | When the team already operates Elastic stack |
| **OTel Collector** | ~50MB | First-class | Custom exporter required | Defer until Redis support matures or destination changes |
| **Custom Python tailer** | trivial | Library-dependent | Trivial | When the bridge needs are minimal and dependency cost is the dominant constraint |

The first four are all viable; "custom" stays in the table for completeness, but §4.2 concludes against it and the decision doc excludes it from the recommended set. Of the off-the-shelf options Vector is the strongest match for Option D as defined here. Note that a Zeek-native option — `zeek-redis` (in-process, no separate daemon) — is not in this table because it is not a generic shipper; it is described separately in the integration-options doc and chosen ahead of these candidates if a viable maintained package is confirmed.

---

## 3. App-side ingestion patterns — high-volume web apps

These systems are not Zeek consumers, but they solve the *consumer side* of the same shape: high-volume telemetry → relational/columnar database, with a Django or Django-adjacent app on top.

### 3.1 Sentry (Django)

The poster child for "Django app handling massive event volume." Sentry is open-source error and performance monitoring; their engineering blog is unusually candid about architecture.

**Ingestion shape (publicly documented):**

```
SDK → HTTP POST → Relay (Rust) → Kafka topics →
Snuba consumers (Python) → ClickHouse  (events)
                       ↓
                       Postgres (project metadata)
```

- **Relay** is a Rust service in front of Django. It absorbs the HTTP write rate, applies sampling and rate-limiting, and writes to Kafka. Sentry's Django app does not see raw event traffic.
- **Kafka** is the durable buffer. Topic partitioning is the scaling primitive.
- **Consumers** are Python processes that read from Kafka and write to ClickHouse (events) or Postgres (metadata, project state).
- **Django** serves the UI and APIs against ClickHouse/Postgres, but is not on the ingestion path.

**Lessons for BlueFlow:**

- **Django stays out of the ingestion hot path.** The pattern is "non-Django service eats the raw ingest rate; Django reads materialized state." Even at our scale, this is the right framing — Option D's consumer is a *worker* command, not a request handler.
- **The buffer is the architecture.** Sentry's Kafka is structurally identical to Option D's Redis Streams, just at a different scale. Both decouple producers from consumers and provide replay.
- **Asset model fits Postgres, not ClickHouse.** Sentry uses ClickHouse for *events* (write-heavy, append-only, queried analytically). BlueFlow's Asset model is *state* (mutable, queried by attribute, ~tens of thousands of rows). PostgreSQL is the right destination; we are not Sentry.
- **Sampling at the bridge is a real lever.** Relay drops events before they hit the buffer. The BlueFlow analog: filter Zeek logs to relevant streams (`conn.log`, `dns.log`, `software.log`) at the bridge, not at the consumer. Drop noise early.

### 3.2 PostHog (Django + Plugin Server + ClickHouse)

Open-source product analytics. Architecture is a Django app paired with a Node-based plugin server and ClickHouse for events.

**Ingestion shape:**

```
SDK → HTTP POST → Django capture endpoint (light) →
Kafka → Plugin Server (Node, transforms) → ClickHouse
                                        ↘
                                          Postgres (people, cohorts)
```

- Capture endpoint in Django is intentionally minimal — write to Kafka and acknowledge.
- Plugin Server reads Kafka, applies user-defined transforms, writes to ClickHouse.
- Person/cohort state in Postgres updated by separate consumers.

**Lessons for BlueFlow:**

- Same "Django capture is thin; durable buffer in front; consumer materializes state" pattern as Sentry, with smaller scale and a similar split.
- The notion of *capture endpoints that just enqueue* is interesting. It is essentially "Option B with the bridge being an HTTP webhook, but Celery replaced by Kafka." Not directly applicable to Zeek (which doesn't naturally POST to HTTP) but the *consumer side* — a worker that materializes state from a stream — is the same pattern as Option D's Django management command.
- PostHog's choice of Kafka is interesting because their volume is much smaller than Sentry's. They picked Kafka anyway for the operational primitives (replay, partitioning, retention). Redis Streams gives most of those at lower operational cost.

### 3.3 Grafana Loki

Log aggregation system. Different shape from Sentry/PostHog because logs are the destination, not events feeding a state model.

**Ingestion shape:**

```
Promtail / Vector / Fluent Bit → HTTP push → Loki (distributor) →
Loki (ingester) → object storage (chunks) + index DB (BoltDB / BigTable)
```

- The agent (Promtail or any compatible shipper) is the bridge.
- Loki distributors validate and shard; ingesters buffer and write chunks.
- Long-term storage is object-store-cheap; index keeps log search affordable.

**Lessons for BlueFlow:**

- **Cheap storage for raw, expensive storage for indexed.** Loki's separation is the same Arkime pattern from §1.4. For BlueFlow, the analog: keep raw Zeek log archive on cheap disk, parse and index only what's needed for the Asset model.
- **HTTP push as the bridge protocol.** Loki accepts pushes from any compatible agent, and the agents (Promtail, Vector, Fluent Bit) handle file-tailing and rotation. This is essentially Vector → HTTP → app. A BlueFlow alternative to Option D's Streams is "Vector → HTTP → Django capture endpoint" — but it puts ingest load on Django's request handlers, which the Sentry pattern argues against.

### 3.4 The unifying pattern

All three of these systems put a *non-Django process* between the wire and the database, even when Django is present. The Django app is for queries against materialized state, not ingestion.

That pattern matches Option D exactly — the bridge writes to Streams, the consumer (which is Django code but not a Django request handler) materializes Asset state. It also explains why **Option B's Celery hop is structurally redundant for this workload**: in Sentry/PostHog terms, the Streams consumer *is* what would otherwise be the Celery worker. Putting Celery in front of it adds a layer with no new property.

---

## 4. Patterns extracted from the survey

Five patterns recur across categories. Each is a constraint or principle the integration design should respect.

### 4.1 The three-stage shape is universal

```
collector / bridge   →   durable buffer   →   consumer / materializer
   (lightweight)        (decoupling layer)        (writes state)
```

Every mature stack surveyed maps onto this shape:

| System | Bridge | Buffer | Consumer |
|---|---|---|---|
| Security Onion | Filebeat | Logstash queue | Logstash filters → Elasticsearch |
| Malcolm | Filebeat | Logstash queue | Logstash filters → OpenSearch |
| Arkime | (built-in capture) | OpenSearch bulk API | OpenSearch indexer |
| Sentry | Relay | Kafka | Snuba → ClickHouse |
| PostHog | Django capture endpoint | Kafka | Plugin Server → ClickHouse |
| Loki | Promtail / Vector | Loki distributor | Loki ingester → object store |
| **Option D (decided)** | **Vector** (per §6.0 bridge investigation; zeek-redis ruled out for Stage 1) | **Redis Streams** | **Django mgmt command → Postgres** |

This is the strongest validation in the survey: Option D has the same shape as the canon. Option C skips the buffer (like Arkime); Option A puts the buffer in the wrong layer (channel layer is not durable); Option B duplicates the buffer (Celery on top of Streams is two buffers).

### 4.2 The bridge is a solved problem

Every NSM/observability stack uses an off-the-shelf shipper as the bridge. Custom file-tailing is rare in mature systems because rotation handling, offset persistence, and back-pressure are subtle and worth not re-implementing.

For BlueFlow specifically: dependency minimalism is the only honest argument for a custom tailer, and that argument loses on examination. Off-the-shelf options solve the hard parts — rotation handling, offset persistence, back-pressure — that a custom tailer would have to reimplement. The decision doc accordingly excludes custom Python from the recommended set; Stage 1's bridge is **Vector**, with the in-process `zeek-redis` path investigated and ruled out for now ([findings](bridge-investigation-findings.md)).

### 4.3 Django apps stay out of the ingest hot path

Sentry, PostHog, and Loki all use a non-Django (or near-non-Django) process to absorb the ingest rate. Django serves queries against materialized state.

This is the same conclusion Option D reaches but is worth saying out loud: a BlueFlow design where Zeek output reaches a DRF endpoint synchronously is fighting the entire industry's pattern. The Sentry "Relay" role is exactly the bridge process in our model.

### 4.4 Sampling and filtering happen at the bridge

Every system surveyed filters or samples *before* the durable buffer, not after. Reasons:

- The buffer's cost is proportional to volume retained.
- Once events are durable, there is psychological friction to dropping them.
- Filtering is a known shape (rules, allow-lists) that fits a small DSL or config file at the bridge.

For BlueFlow: the bridge is where "which Zeek log streams do we care about" gets answered. `conn.log` for IP/MAC pairs, `dns.log` for hostnames, `software.log` for fingerprints — drop the rest before `XADD`. This belongs in bridge config, not in the consumer's parsing logic.

### 4.5 Separate state storage from raw archive

Arkime stores session metadata in OpenSearch and packets on cheap disk. Loki stores chunks in object storage and index in a small DB. Sentry stores events in ClickHouse and project state in Postgres.

For BlueFlow this means: even if Asset records live in Postgres, **the raw Zeek logs are worth keeping somewhere cheap**, separately, for forensic replay and re-derivation if the consumer's parsing logic changes. This was not in the original four-option analysis and deserves a follow-up question.

---

## 5. Implications for the four-option analysis

The survey does not surface a fifth option. It does refine the existing four:

### 5.1 Option D is the canonical shape, not the unconventional one

Reading the option doc cold, "Redis Streams + Django management command consumer" might look like a clever invention. The survey shows it is the same three-stage shape every mature stack uses, with sensible primitive choices. That is a meaningful update to how Option D should be presented: not as one of four, but as **the option that matches industry practice at our scale**.

### 5.2 Off-the-shelf is the bridge default, not "custom tailer"

Off-the-shelf options should be promoted ahead of any custom-code path: every comparable stack in §1–§3 uses an off-the-shelf shipper. The original framing of this section also held out `zeek-redis` (in-process to Zeek itself) as potentially even simpler than a separate shipper. **That option was investigated and ruled out** — see [bridge-investigation-findings.md](bridge-investigation-findings.md): no current Zeek package writes to Redis Streams, so the in-process path is unavailable today.

The resolved preference for Option D's bridge slot:

1. **Vector** — committed Stage 1 bridge per the decision doc. Survey §2.1 covers it; battle-tested rotation handling, retry/backoff, observability, disk buffering.
2. **Zeek Broker subscriber** — Stage 3 candidate if low-latency live ingestion later dominates over file durability.
3. **`zeek-redis` plugin** — revisitable only if a Streams-supporting package emerges in the ecosystem; not viable today.
4. **Custom Python tailing** — excluded. Reimplements rotation handling and offset persistence that off-the-shelf options have solved (see §4.2).

### 5.3 Option B's redundancy is now a stronger claim

When the option doc said "Celery on top of Streams is duplicative," that was an internal-architecture argument. The survey adds external evidence: no comparable system puts a task framework between buffer and state writer for this workload shape. The Sentry consumer pattern, PostHog plugin server pattern, and Loki ingester pattern are all the equivalent of "Streams consumer writes directly to state." None of them route through a task framework.

Celery's value remains real for *task-shaped* work elsewhere in BlueFlow. It is not the right tool specifically for the ingest-to-state path.

### 5.4 Asset model in Postgres is correct; raw archive needs a decision

Sentry's split (Postgres for state, ClickHouse for events) and Arkime's split (OpenSearch for sessions, disk for pcap) both argue for a similar split in BlueFlow:

- **Asset model** lives in Postgres. Already true. The survey validates the choice.
- **Raw Zeek logs** should live somewhere cheap and separate, retained according to a forensic-replay SLA. This was not surfaced in the original option analysis. It is a question worth adding to the open-questions list.

### 5.5 No off-the-shelf product fits the BlueFlow product mission

Security Onion, Malcolm, Corelight, and friends are all *security-monitoring* products. BlueFlow is an *asset-management* product that happens to use Zeek as a discovery source. Adopting any of these wholesale would change BlueFlow's product surface. The survey's value is architectural lessons, not product replacement.

---

## 6. Open questions surfaced by the survey

Adding to the open-questions list in the option doc:

- **Should raw Zeek logs be retained separately from the Asset model?** If yes, where (cheap disk, S3-compatible storage), and for how long? This is a forensic-replay and re-derivation question — if the consumer's parsing logic ever changes, raw logs are the only way to back-fill.
- **Bridge mechanism choice** — ~~resolved by the decision doc as `zeek-redis` if viable, Vector otherwise~~. **Updated 2026-05-08:** the §6.0 [bridge investigation findings](bridge-investigation-findings.md) ruled out current zeek-redis packages (none support Redis Streams); Stage 1's bridge is committed to **Vector**.
- **Sampling/filtering policy at the bridge.** Which Zeek streams do we care about, and at what rate? Filebeat / Vector / Fluent Bit configs are where this lives if we adopt one of them.
- **Is there appetite for an HTTP-push variant of the bridge?** Loki's Promtail-style HTTP push is a real alternative to Streams as the buffer protocol. Worth considering only if a Django capture endpoint can be made cheap enough (Sentry's Relay pattern, but in Python — which is harder than in Rust).

---

## References

- Companion: [zeek-and-channels-ideal-usage.md](zeek-and-channels-ideal-usage.md)
- Companion: [zeek-to-django-integration-options.md](zeek-to-django-integration-options.md)
- Security Onion: https://docs.securityonion.net/en/2.4/architecture.html
- Corelight (public-facing architecture overview): https://corelight.com/
- Malcolm (CISA): https://github.com/cisagov/Malcolm
- Arkime: https://arkime.com/architecture
- Apache Metron (archived, still informative): https://metron.apache.org/
- Vector: https://vector.dev/docs/
- Fluent Bit: https://docs.fluentbit.io/
- Logstash: https://www.elastic.co/guide/en/logstash/current/
- OpenTelemetry Collector: https://opentelemetry.io/docs/collector/
- Sentry architecture (engineering blog): https://sentry.engineering/
- PostHog architecture: https://posthog.com/handbook/engineering/databases
- Grafana Loki architecture: https://grafana.com/docs/loki/latest/get-started/architecture/
