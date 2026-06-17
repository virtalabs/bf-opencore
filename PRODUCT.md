# BlueFlow — Agent Reference

| Field    | Value |
|----------|-------|
| Document | Agent-optimized product reference |
| Repo     | `blueflow` (installable Django app + standalone `project/`) |
| Stack    | Django 5.2 · DRF · PostgreSQL (required) · Celery · django-simple-history · django-netfields |
| Date     | 2026-05-28 |

---

## 1. What BlueFlow is

BlueFlow is a Django-based asset-management and vulnerability-tracking store. Its primary job: receive device-inventory records from scanners (TapirXL, Nessus, CSV) and network-telemetry tools (Zeek, ping), persist them as `Asset` records, track associated vulnerabilities and remediation state, and expose all of it via a REST API consumed by the VirtaLabs product suite and external integrations (Viper).

**Two deployment surfaces:**
- **`blueflow` app** — installable via `INSTALLED_APPS`; consumed by blueflow-saas and other products.
- **`project/`** — minimal standalone Django project for local dev and Docker.

---

## 2. Hard invariants (do not violate)

**I1 — PostgreSQL only.** `django-netfields` (`InetAddressField`, `MACAddressField`, `CidrAddressField`) and `ArrayField` require PostgreSQL. SQLite will break at migration time.

**I2 — Asset identity priority: external_keys > mac_address > ip_address.** This order is enforced by `AssetManager.get_by_priority()` and `update_or_create_by_priority()`. Never bypass it with a direct `.get(ip_address=x)` in upsert flows.

**I3 — external_keys are append-only; never overwrite.** `update_or_create_by_priority()` raises `ValidationError` if a defaults dict would overwrite a key already in `asset.external_keys` with a different value. External keys may not be `None` or `""`.

**I4 — `modified` is the Viper sync anchor.** `Asset.modified` (from `TimeStampedModel`) updates on every `save()`. `last_pinged` updates only on network observation and is NOT a "recently changed" signal.

**I5 — PHI never stored.** BlueFlow is a downstream consumer of already-PHI-redacted TapirXL output. It performs no PHI redaction itself; it just stores what it receives. Do not add fields that store patient names, DOBs, or patient IDs.

**I6 — `hostname` is nullable but never empty-string.** A `CheckConstraint` enforces `hostname IS NULL OR hostname != ''`. Setting hostname to `""` will raise `IntegrityError`.

**I7 — open_ports_tcp range 1–65535.** `validate_tcp_port_range` runs on every save. Ports outside this range raise `ValidationError`. Use `asset.open_ports_tcp_add()` for safe append.

**I8 — Authentication is DRF token auth (`Authorization: Token …`).** Not Bearer/JWT. Viper webhook and all API consumers must use this scheme.

**I9 — JSON output only on stdout.** Follows TapirXL's N6 discipline: JSONL from TapirXL must not contain tshark noise. BlueFlow itself is a Django API server — this invariant applies to TapirXL's stdout contract upstream.

**I10 — `AssetVulnerability.date_remediated` takes precedence over `date_ignored`.** An AssetVulnerability with both dates set is classified as `remediated`. The `.open()` queryset requires BOTH null.

---

## 3. Data model

### 3.1 Asset (`blueflow/models/asset.py`)

Primary entity. One record per physical device.

**Identity fields (priority order for upsert):**

| Field | Type | Constraint |
|-------|------|------------|
| `external_keys` | JSONField, nullable | Dict of `{"system": "id"}`; keys append-only |
| `mac_address` | MACAddressField, nullable | unique; auto-populates `nic_vendor` on save |
| `ip_address` | InetAddressField, nullable | NOT unique (device may change IP) |

**Descriptive fields:**

| Field | Type | Notes |
|-------|------|-------|
| `hostname` | TextField, nullable, unique | `NULL` or non-empty (CheckConstraint) |
| `name` | CharField(126), nullable | user-friendly label |
| `nic_vendor` | TextField, nullable | auto-set from MAC OUI on save |
| `manufacturer` | TextField, nullable | |
| `model` | TextField, nullable | |
| `serial_number` | TextField, nullable | |
| `udi` | TextField, nullable | Unique Device Identifier |
| `tag_number` | TextField, nullable | |
| `category` | TextField, nullable | device role/class |
| `owner` | TextField, nullable | |
| `os` | TextField, nullable | |
| `app_sw_version` | TextField, nullable | |
| `last_scanned` | DateTimeField, nullable | |
| `last_pinged` | DateTimeField, nullable | network-layer only; NOT the sync anchor |
| `open_ports_tcp` | ArrayField(IntegerField), default=[] | 1–65535; sorted, deduplicated |

**Relations:**

| Relation | Through table | Extra fields on join |
|----------|---------------|----------------------|
| `groups` → Group | AssetGroup | `date_added`, `provenance` |
| `tags` → Tag | AssetTag | `date_added`, `provenance` |
| `vulnerabilities` → Vulnerability | AssetVulnerability | `date_added`, `date_remediated`, `date_ignored`, `provenance` |
| `custom_fields` → AssetCustomFieldName | AssetCustomField | `value_text`, `date_added` |

**Auto fields:** `created`, `modified` (TimeStampedModel); `history` (HistoricalRecords).

**Key properties:**

| Property | Returns |
|----------|---------|
| `display_name` | `name` > `hostname` > `manufacturer model` > `nic_vendor` > `Asset-{id}` |
| `is_identified` | `bool`: manufacturer AND model AND (ip_address OR mac_address) |
| `cpe` | CPE 2.3 string |

**Key manager methods** (`Asset.objects.*`):

| Method | Behavior |
|--------|----------|
| `get_by_priority(**kwargs)` | Lookup by external_keys > mac > ip; raises `DoesNotExist` if not found |
| `update_or_create_by_priority(defaults, **kwargs)` | Upsert with priority logic; merges JSONFields; returns `(asset, Created)` |
| `in_network(network_id)` | QuerySet of assets whose IP is contained by any CIDR in that network |
| `no_network()` | Assets with an IP that is not contained by any registered CIDR |
| `identified_statistics()` | `{"num", "not", "pct", "not_pct"}` |
| `vulnerability_statistics()` | `{"total", "open", "remediated", "accepted", "avg_dwell_open", ...}` |

**`Created` enum** (`blueflow/utils/__init__.py`): `CREATED`, `UPDATED`, `UPTODATE`.

---

### 3.2 Network & Cidr (`blueflow/models/network.py`)

**Network:**

| Field | Type | Constraint |
|-------|------|------------|
| `name` | CharField(126) | unique |
| `ok_to_scan` | BooleanField | default=False |

- `cidr` property: list of CIDR strings; managed via `Cidr` join table.
- `NetworkManager.create_network(name, network, ok_to_scan)` — factory; creates Network + Cidr(s).

**Cidr:**

| Field | Type |
|-------|------|
| `cidr` | CidrAddressField |
| `network` | FK(Network, CASCADE) |

**SavedSearch:**

| Field | Type | Constraint |
|-------|------|------------|
| `name` | CharField(126) | unique |
| `search_query` | JSONField | unique |
| `ok_to_scan` | BooleanField | default=False |

---

### 3.3 Vulnerability (`blueflow/models/vulnerability.py`)

**Vulnerability:**

| Field | Type | Constraint |
|-------|------|------------|
| `name` | CharField(126) | unique; e.g., `"Nessus 10001"` |
| `synopsis` | TextField, nullable | display name |
| `description` | TextField, nullable | |
| `solution` | TextField, nullable | |
| `cvss_score` | FloatField, nullable | |
| `cves` | ArrayField(TextField), nullable | e.g., `["CVE-2024-1234"]` |
| `external_page_url` | ArrayField(TextField), nullable | advisory links |

- `Vulnerability.objects.weighted()`: orders by `Count(asset) * cvss_score`, filtering to open+unaccepted only.

**AssetVulnerability (join):**

| Field | Type | Constraint |
|-------|------|------------|
| `asset` | FK(Asset, CASCADE) | |
| `vulnerability` | FK(Vulnerability, CASCADE) | |
| `date_added` | DateTimeField | default=now |
| `date_remediated` | DateTimeField, nullable | |
| `date_ignored` | DateTimeField, nullable | "accepted" |
| `provenance` | TextField, nullable | scanner name |

- `unique_together = ("asset", "vulnerability")`
- **State logic:** `.open()` = both null · `.remediated()` = date_remediated NOT NULL · `.accepted()` = date_ignored NOT NULL AND date_remediated NULL
- `.add_dwell()` / `.avg_dwell()` — annotate/aggregate time-in-state.

---

### 3.4 Tag & Group

**Tag:** `name` (unique), `color` (hex string, e.g., `"#FF0000"`).  
**AssetTag:** `asset`, `tag`, `date_added`, `provenance`. `unique_together = ("asset", "tag")`.

**Group:** `name` (unique).  
**AssetGroup:** `asset`, `group`, `date_added`, `provenance`. `unique_together = ("asset", "group")`.

---

### 3.5 NetworkEndpoint (`blueflow/models/network_endpoint.py`)

Device observed on the wire (Zeek / netflow). May not have a matching `Asset` yet.

| Field | Type | Notes |
|-------|------|-------|
| `mac_address` | MACAddressField, nullable, unique | |
| `ipv4_address` | InetAddressField, nullable, unique | |
| `ipv6_address` | InetAddressField, nullable, unique | |
| `_user_asset_match` | FK(Asset, SET_NULL), nullable | manual override |
| `_asset_match_blacklist` | ArrayField(IntegerField) | ruled-out asset IDs |
| `transmit_ports` | ArrayField(CharField) | e.g., `["80/TCP", "443/TCP", "ICMP"]` |
| `receive_ports` | ArrayField(CharField) | |
| `max_confidence` | SmallIntegerField | highest confidence score across suggestions |

- At least one of MAC/IPv4/IPv6 required.
- `asset` property: user match > single unambiguous suggestion > None.
- `compare(asset)` → confidence score (0–13): +1–3 network, +4 MAC OUI, +3 shared ports (max 3).
- `update_suggestions()` → rebuilds `EndpointSuggestion` rows.
- `merge(other)` → combines two endpoints if no field conflicts.

**EndpointSuggestion:** `asset`, `network_endpoint`, `confidence`, `confidence_limit`, `evidence` (JSONField list of `{"reason": str, "value": str}`).

---

### 3.6 Usage (`blueflow/models/usage.py`)

Per-asset hourly observation counts, deduplicated within 5-minute windows.

| Field | Type | Notes |
|-------|------|-------|
| `asset` | FK(Asset, CASCADE) | |
| `day_of_week` | IntegerField | 0=Monday, 6=Sunday (ISO 8601) |
| `hour_00`…`hour_23` | IntegerField | observation count per hour |
| `last_window_started_at` | DateTimeField, nullable | dedup anchor |

- `unique_together = ("asset", "day_of_week")`.
- `USAGE_WINDOW_MINUTES = 5`.
- `floor_to_window(when)` class method: round datetime down to 5-min bucket.
- Call `asset.update_usage(timestamp)` — do NOT write Usage rows directly.

---

### 3.7 Viper integration (`blueflow/models/viper.py`)

**ViperWebhookJob:**

| Field | Type |
|-------|------|
| `id` | UUIDField (PK, default=uuid4) |
| `callback` | CharField — webhook callback URL |
| `since` | DateTimeField — sync anchor (`modified__gte`) |
| `before` | DateTimeField, nullable |
| `request_body` | JSONField |
| `status` | `pending` → `started` → `finished` / `error` |

- POST `/api/viper/webhook/` → enqueues Celery task, returns `job_id` (HTTP 202).
- Assets delivered to callback as paginated `ViperWebhookResponse` objects.
- Wire shape: `{"ip", "hostname", "mac_address", "serial_number", "vendor", "product", "cpe", "utilization"}`.
- `ViperWebhookResponseList.from_request()` — generator yielding paginated pages.

---

### 3.8 Other models

| Model | File | Purpose |
|-------|------|---------|
| `Alert` | `models/alert.py` | UI notifications; `date_read` marks read |
| `Scan` | `models/scan.py` | Scan execution record (legacy) |
| `Attachment` | `models/attachment.py` | File uploads attached to an Asset |
| `AssetCustomFieldName` | `models/asset_custom_field.py` | Schema for custom fields |
| `AssetCustomField` | `models/asset_custom_field.py` | Custom field value per asset |

---

## 4. API surface

**Base path:** `api/` (wired in `project/urls.py`).  
**Auth:** `POST api/api-token-auth/` → `{"token": "..."}`. Header: `Authorization: Token <token>`.  
**Docs:** `GET api/docs/` (Scalar UI). Schema: `GET api/schema/` (OpenAPI JSON).  
**Pagination:** `HugeLimitOffsetPagination` → `?limit=N&offset=M`.  
**CSV export:** `Accept: text/csv` on list endpoints.

### Asset endpoints

| Method | Path | Action |
|--------|------|--------|
| GET | `api/assets/` | List (filterable, searchable, orderable) |
| POST | `api/assets/` | Create |
| GET | `api/assets/{id}/` | Retrieve |
| PUT/PATCH | `api/assets/{id}/` | Full / partial update |
| DELETE | `api/assets/{id}/` | Delete |
| POST | `api/assets/upsert/` | Upsert via scanner payload (calls `update_or_create_by_priority`) |
| GET | `api/assets/{id}/tags/` | Asset's tags |
| GET | `api/assets/{id}/scans/` | Asset's scans |
| GET | `api/assets/{id}/history/` | Historical versions (simple-history) |
| GET | `api/assets/{id}/changelog/` | Annotated field-level diffs |

### Other registered routers

| Prefix | Description |
|--------|-------------|
| `api/alerts/` | CRUD |
| `api/vulnerabilities/` | CRUD; default order by `.weighted()` |
| `api/assetvulnerabilities/` | CRUD; set `date_remediated`/`date_ignored` here |
| `api/networks/` | CRUD; `cidr` setter re-creates Cidr rows |
| `api/cidrs/` | Read-only (managed via Network) |
| `api/savedsearches/` | CRUD |
| `api/groups/` / `api/assetgroups/` | CRUD |
| `api/tags/` / `api/assettags/` | CRUD |
| `api/scans/` | CRUD |
| `api/users/` | Read |
| `api/crontabs/` / `api/intervals/` / `api/periodictask/` | Celery Beat schedule management |

### Special endpoints

| Method | Path | Notes |
|--------|------|-------|
| POST | `api/viper/webhook/` | Async; returns `{"job_id": UUID}` (HTTP 202) |
| GET | `api/topology/` | Network topology snapshot (stub, schema v0.1.0) |

---

## 5. Key algorithms

### 5.1 Asset upsert priority (`asset_manager.py:get_by_priority`)

```
Input: external_keys__<key>=V, mac_address=M, ip_address=I

1. If external_keys key provided and non-empty:
   → GET by that key. Match → return asset.
   → DoesNotExist → fall through.

2. If mac_address provided and non-empty:
   → GET by mac_address. Match → return asset.
   → DoesNotExist → fall through.

3. If ip_address provided and non-empty:
   → GET by ip_address.
   → MultipleObjectsReturned AND (mac or ekey provided) → raise DoesNotExist (coerce).
   → Match found AND asset.mac_address set AND mac_kwarg provided → raise DoesNotExist (refuse clobber).
   → Match found AND asset.external_keys set AND ekey_kwarg provided → raise DoesNotExist (refuse clobber).
   → Otherwise → return asset.

4. No match at any level → raise DoesNotExist.
```

`update_or_create_by_priority()` wraps this with:
- JSONField dict-merge (not overwrite) for `external_keys` and similar fields.
- ValidationError if `defaults` would overwrite an existing `external_keys` key with a different value.
- Returns `(asset, Created.CREATED | UPDATED | UPTODATE)`.

### 5.2 AssetVulnerability state machine

```
date_remediated=NULL, date_ignored=NULL  → OPEN
date_remediated=SET                      → REMEDIATED (takes precedence)
date_remediated=NULL, date_ignored=SET   → ACCEPTED
```

Use queryset methods: `.open()`, `.remediated()`, `.accepted()`. Do not filter manually.

### 5.3 NetworkEndpoint confidence scoring (`network_endpoint.py:compare`)

```
Max score: 13
  +1–3  IP in same network as asset IP (up to 3 networks)
  +4    MAC OUI (first 3 octets) matches asset MAC OUI
  +3    shared TCP ports (up to 3 overlapping ports count)
```

`EndpointSuggestion` rows are rebuilt by `update_suggestions()`. Read `asset` property for resolved match.

---

## 6. File map

### Models
| File | Contains |
|------|----------|
| `blueflow/models/__init__.py` | Re-exports all models |
| `blueflow/models/asset.py` | `Asset` model, constants |
| `blueflow/models/asset_manager.py` | `AssetManager`, `AssetQuerySet` |
| `blueflow/models/network.py` | `Network`, `Cidr`, `SavedSearch` |
| `blueflow/models/vulnerability.py` | `Vulnerability`, `AssetVulnerability`, querysets |
| `blueflow/models/tag.py` | `Tag`, `AssetTag` |
| `blueflow/models/group.py` | `Group`, `AssetGroup` |
| `blueflow/models/network_endpoint.py` | `NetworkEndpoint`, `EndpointSuggestion` |
| `blueflow/models/viper.py` | `ViperWebhookJob`, dataclasses |
| `blueflow/models/usage.py` | `Usage`, `DayOfWeek` |
| `blueflow/models/alert.py` | `Alert` |
| `blueflow/models/scan.py` | `Scan` |
| `blueflow/models/attachment.py` | `Attachment` |
| `blueflow/models/asset_custom_field.py` | `AssetCustomFieldName`, `AssetCustomField` |

### Views & serializers
| File | Contains |
|------|----------|
| `blueflow/views/__init__.py` | Re-exports all ViewSets |
| `blueflow/views/asset.py` | `AssetViewSet`, `AssetSerializer`, `AssetUpsertSerializer` |
| `blueflow/views/vulnerability.py` | `VulnerabilityViewSet` |
| `blueflow/views/assetvulnerability.py` | `AssetVulnerabilityViewSet` |
| `blueflow/views/network.py` | `NetworkViewSet`, `CidrViewSet`, `SavedSearchViewSet` |
| `blueflow/views/viper.py` | `ViperViewSet` |
| `blueflow/views/topology.py` | `TopologyView` (stub) |
| `blueflow/views/utils.py` | `ChangeReasonMixin`, `PaginateRelationsMixin`, `HugeLimitOffsetPagination` |

### Routing, config, async
| File | Contains |
|------|----------|
| `blueflow/urls.py` | DRF DefaultRouter + custom paths |
| `project/urls.py` | Project-level routing; mounts blueflow at `api/` |
| `project/settings/base.py` | Shared Django settings |
| `blueflow/celery/tasks.py` | `viper_webhook` Celery task |
| `blueflow/zeek/` | Zeek log ingestion, HL7 sidecar |
| `blueflow/csv/__init__.py` | `process_csv()` import pipeline |

### Utilities & schema
| File | Contains |
|------|----------|
| `blueflow/utils/__init__.py` | `Created` enum, `FieldMap`, `NullUnlessChanged` |
| `blueflow/spectacular.py` | drf-spectacular extensions (netfields types) |
| `blueflow/admin.py` | Admin registrations |

### Tests
| Path | Scope |
|------|-------|
| `blueflow/tests/` | App-level integration tests |
| `blueflow/tests/factories.py` | `factory_boy` factories |
| `tests/` | Project-level smoke tests (schema, URL wiring, migrations) |

### Migrations
| File | Notable change |
|------|----------------|
| `blueflow/migrations/0001_initial.py` | Base schema |
| `blueflow/migrations/0007_*` | Make migrations |
| `blueflow/migrations/0010_*` | product → model rename |
| `blueflow/migrations/0011_*` | vendor normalization + CPE |
| `blueflow/migrations/0012_*` | Usage table |

---

## 7. Anti-patterns — do not do these

**A1 — Do not bypass `get_by_priority` for upserts.**  
Direct `Asset.objects.get(ip_address=x)` in upsert code breaks the identity contract. IP addresses are non-unique across time. Use `update_or_create_by_priority()`.

**A2 — Do not write `{"external_keys": None}` or `{"external_keys": {"k": ""}}`.**  
Raises `ValidationError` at the manager layer. Always provide non-null, non-empty values.

**A3 — Do not set `hostname = ""`.**  
Use `None` for absent hostnames. An empty string violates the `CheckConstraint` and raises `IntegrityError`.

**A4 — Do not treat `last_pinged` as a "recently modified" signal.**  
Only `modified` is the sync anchor. `last_pinged` is written by network-layer code only and is explicitly excluded from the Viper sync filter.

**A5 — Do not skip the `Usage.update_usage(timestamp)` path.**  
The 5-minute dedup window logic lives there. Writing `Usage` hour fields directly bypasses deduplication.

**A6 — Do not add `dspy`, `ollama`, or LM-runtime imports to the blueflow app.**  
BlueFlow is a pure asset store. Agent / LM enrichment belongs in TapirXL's experimental tier, not here.

**A7 — Do not add HTTP client calls (`requests`, `httpx`) inside model code.**  
Network I/O belongs in Celery tasks or view-layer service calls. Models must remain callable in tests without network access.

**A8 — Do not add `unique=True` to `ip_address`.**  
Multiple assets may legitimately share an IP over time (DHCP reassignment, VLAN migration). The schema intentionally keeps ip_address non-unique; uniqueness is handled at the MAC and external_keys level.

**A9 — Do not filter `AssetVulnerability` for "open" manually.**  
Use `.open()` from `AssetVulnerabilityQuerySet`. The definition (`date_remediated IS NULL AND date_ignored IS NULL`) may evolve; the queryset method is the canonical place.

**A10 — Do not write new serializers that expose raw `password`, `token`, or `external_keys` values without explicit authorization review.**  
`external_keys` may contain third-party system IDs; confirm the API consumer is authorized before adding those fields to serializer output.

---

## 8. Environment & running

**Required env vars:**
```
DATABASE_URL=postgresql://user:pass@host:5432/blueflow
DJANGO_SETTINGS_MODULE=project.settings.{development|production|test}
REDIS_URL=redis://localhost:6379
BASE_URL=http://localhost:8000
```

**Run tests:**
```bash
uv sync --all-extras
export DATABASE_URL=postgresql://blueflow:blueflow@localhost:5432/blueflow
uv run pytest                    # all tests
uv run pytest blueflow/tests/    # app-level only
uv run pytest tests/             # smoke tests only
```

**Docker:**
```bash
docker-compose up                                   # starts PostgreSQL + Django (migrations auto-applied)
docker-compose run web uv run pytest                # tests in container
```

**Migrations:**
```bash
python project/manage.py migrate --noinput          # apply
python project/manage.py makemigrations blueflow    # generate new
```

---

## 9. Integration context

### TapirXL → BlueFlow

TapirXL (passive network scanner) ships `InventoryRecord` JSONL via Vector Remap Language (VRL) at `configs/upload-vector.vrl` (in the TapirXL repo). The VRL transform maps `InventoryRecord` fields to BlueFlow's `Asset` payload and POSTs to `api/assets/upsert/`. PHI is already redacted before it reaches BlueFlow (TapirXL invariant A3).

Field mapping:
- `vendor` → `manufacturer`
- `product` → `model`
- `mac_address` → `mac_address` (identity)
- `ip_address` → `ip_address`
- `hostname` → `hostname`
- `open_ports` → `open_ports_tcp`
- `version` → `app_sw_version`
- `device_class` → `category`
- `confidence` → stored in `external_keys` or custom field (check VRL for current mapping)

### Viper → BlueFlow

Viper POSTs to `api/viper/webhook/` with `{"callback", "since", "before"}`. BlueFlow queues a Celery task that pages through `Asset.objects.filter(modified__gte=since)` and delivers `ViperAsset` payloads to the callback URL. `ViperAsset` fields: `ip`, `hostname`, `mac_address`, `serial_number`, `vendor`, `product`, `cpe`, `utilization`.

### Zeek → BlueFlow

`blueflow/zeek/sidecar.py` ingests Zeek connection logs and creates/updates `NetworkEndpoint` records. `blueflow/zeek/hl7/sidecar.py` handles HL7-annotated Zeek logs. NetworkEndpoints run `update_suggestions()` to match against existing Assets.
