# Executive Summary

The objective is to provide a turnkey Splunk Observability-as-a-Service Native App for Snowflake that captures and exports Snowflake-native telemetry to external Splunk backends. The app supports two complementary export protocols:
- **OTLP/gRPC** → Splunk Observability Cloud — for OTel-native telemetry (spans, metrics) originating from Event Tables.
- **Splunk HEC (HTTP)** → Splunk Enterprise/Cloud — for logs (including Event Table logs) and structured operational data originating from ACCOUNT_USAGE views.

The architecture employs a **dual-pipeline design**:
1. **Event-driven pipeline**: Snowflake Streams + Serverless Triggered Tasks export Event Table telemetry in near real-time (~20–30s latency).
2. **Poll-based pipeline**: Scheduled Serverless Tasks with watermark-based incremental reads export ACCOUNT_USAGE operational telemetry at configurable intervals.

Both pipelines export telemetry directly to Splunk destinations without intermediate data staging. Retry handling in MVP relies on transport-level retries built into the OTLP SDK and `httpx`/`tenacity`. A **zero-copy failure tracking layer** (post-MVP) will record lightweight references (hashes or natural keys) for persistently failed batches, enabling dedicated retry logic while eliminating 99%+ of staging storage overhead.

The app is distributed via the Snowflake Marketplace and designed for iterative delivery through pre-built **Monitoring Packs**. MVP ships with the **Distributed Tracing Pack** and **Performance Pack**; additional packs (Cost, Security, Data Pipeline) are delivered iteratively post-MVP.

---

# MVP Scope

This section defines the boundary of the first shipped version. Everything described in the vision document remains the **target architecture**; this section clarifies what ships in v1 versus what is deferred.

## In Scope (MVP)

### Monitoring Packs
| Pack | Sources | Pipeline |
|---|---|---|
| **Distributed Tracing Pack** | User-selected Event Tables (spans, metrics, logs) | Event-driven (Streams + Triggered Tasks) → OTLP/gRPC (spans & metrics) + HEC HTTP (logs) |
| **Performance Pack** | QUERY_HISTORY, TASK_HISTORY, COMPLETE_TASK_GRAPHS, LOCK_WAIT_HISTORY | Poll-based (Task Graph + Watermarks) → HEC HTTP |

### App Deployment & Configuration
- Full `manifest.yml` v2 with privileges, references, and event sharing (Section 1).
- Streamlit UI for privilege binding (Python Permission SDK), pack selection, destination setup, and retry settings (Section 2).
- Automated infrastructure provisioning: networking/EAI, streams, task graph, internal tables (Section 3).

### Pipelines
- **Event-driven pipeline**: Streams on Event Tables → Triggered Tasks → `event_table_collector` → OTLP/gRPC + HEC.
- **Poll-based pipeline**: Task Graph (root + child tasks per Performance Pack source + finalizer) → `account_usage_source_collector` → HEC.
- Stream checkpointing with zero-row INSERT offset advancement (Section 8).

### Design Decisions (Implemented in MVP)
- **7.1 Batching Strategy** — chunked exports with configurable batch sizes.
- **7.2 Retry Strategy** — transport-level retries only, using native capabilities of each protocol's client library:
  - OTLP/gRPC: Built-in OTel SDK application-level retry with exponential backoff (~6 retries over ~63s) for transient gRPC errors (UNAVAILABLE, DEADLINE_EXCEEDED, RESOURCE_EXHAUSTED).
  - HEC HTTP: `httpx` with `tenacity` for exponential backoff retries on 429/5xx status codes.
  - **No application-level failure tracking** — if all transport retries exhaust, the batch is lost and the pipeline advances. This is acceptable for MVP because transport-level retries handle the vast majority of transient failures.
- **7.6 Parallel Processing via Task Graph** — DAG with parallel child tasks per source.
- **7.7 Source Prioritization** — priority ordering within the task graph.
- **7.8 Latency-Aware Adaptive Polling Schedule** — 30-minute root interval with early-exit pattern per source.
- **7.9 OTLP Transport Selection** — OTLP/gRPC for spans & metrics, HEC HTTP for logs and ACCOUNT_USAGE.
- **7.11 Vectorized Transformations** — Snowpark DataFrame filtering + `to_pandas_batches()` chunked processing.
- **7.12 Snowpark Best Practices** — push relational work to Snowflake engine.
- **7.13 Data Transformation Optimization for Event Tables** — per-signal-type Snowpark projections.

### Pipeline Health Observability (MVP)
- **Internal metrics table** (`_metrics.pipeline_health`) — records per-run operational metrics.
- **Streamlit Overview Tab only**, with three KPI cards:
  - Total rows collected / exported / failed (last 24h).
  - Current failed batches awaiting retry (transport-level retry failures within the current run).
  - Pipeline up/down status per source (based on last successful run timestamp).
- **Volume estimator** (`_internal.volume_estimator`) — initial and on-demand throughput projection.

## Out of Scope (Post-MVP)

### Monitoring Packs (Deferred)
- **Cost Pack** — METERING_HISTORY, WAREHOUSE_METERING_HISTORY, PIPE_USAGE_HISTORY, SERVERLESS_TASK_HISTORY, AUTOMATIC_CLUSTERING_HISTORY, STORAGE_USAGE, DATABASE_STORAGE_USAGE_HISTORY, DATA_TRANSFER_HISTORY, REPLICATION_USAGE_HISTORY, SNOWPARK_CONTAINER_SERVICES_HISTORY, EVENT_USAGE_HISTORY.
- **Security Pack** — LOGIN_HISTORY, ACCESS_HISTORY, SESSIONS, GRANTS_TO_USERS, GRANTS_TO_ROLES, NETWORK_POLICIES.
- **Data Pipeline Pack** — COPY_HISTORY, LOAD_HISTORY, PIPE_USAGE_HISTORY.

### Failure Tracking & Recovery (Deferred)
- **Zero-copy reference-based failure tracking** (Section 5) — `_staging.failed_event_batches`, `_staging.failed_account_usage_refs` tables. In MVP, if transport-level retries exhaust, the batch is dropped and the pipeline advances.
- **Dedicated retry task** (`_internal.failed_batch_retrier`) — periodic re-export of persistently failed batches.
- **Lazy hash computation / natural key extraction** (Section 7.4) — only needed when failure tracking is enabled.
- **Automatic cleanup task** for failed batch references.
- Configuration settings: `max_retry_attempts`, `failed_batch_retention_days` (UI fields deferred).

### Rate Limit Handling (Deferred)
- **In-app rate limiting** (Section 7.10) — request pacing, adaptive throttling, 429 backoff with Retry-After.
- **Rate Limits Dashboard Tab** (Section 9.3) — HEC/OTLP rate limit metrics visualization.

### Exporter Features (Deferred)
- PII redaction / field masking.
- Sampling.
- Attribute/label normalization or renaming.
- Content-based routing beyond basic source-type split.
- Advanced load-shedding or dynamic sampling based on backend pressure.
- Complex processor chains (metric transformations, span processors, etc.).

### Pipeline Health Dashboard Tabs (Deferred)
- **Throughput Tab** — rows exported over time, export latency distribution.
- **Errors & Failures Tab** — failed batches by source, recent errors table (requires failure tracking).
- **Volume Estimation Tab** — estimated vs. actual volume comparison.
- **Rate Limits Tab** — HEC/OTLP rate limit metrics (requires rate limit handling).
- **Stream health status** per Event Table stream (STALE_AFTER monitoring).

### Advanced Optimizations (Deferred)
- `ThreadPoolExecutor` + `httpx.Client` connection pooling for concurrent HEC exports (BP-7). Note: `asyncio` + `httpx.AsyncClient` was evaluated and rejected — unverified in Snowflake's sandbox, no official examples exist. See BP-7 in Section 7.12 for full analysis.
- Vectorized UDFs for hash computation (BP-6).
- Thread-safe Snowpark sessions for parallelism within procedures (Section 7.6 post-MVP note).
- OTLP HTTP fallback if gRPC is blocked.

---

# High-Level Workflow

## 1. Deployment & Consumer Activation

**Action**: Snowflake customer installs the Splunk Observability Native App via Snowflake Marketplace.

**Initialization**: The app's `setup.sql` script creates the necessary internal schemas (`_internal`, `_staging`, `_metrics`) and application objects while maintaining provider IP protection.

**Required Consumer Privileges** (declared in `manifest.yml` with `manifest_version: 2`):
```yaml
privileges:
  - IMPORTED PRIVILEGES ON SNOWFLAKE DB:
      description: "Required to read ACCOUNT_USAGE views for cost, performance, and security monitoring"
  - EXECUTE TASK:
      description: "Required for the app's task owner role to run scheduled and triggered tasks"
  - EXECUTE MANAGED TASK:
      description: "Required to provision serverless compute resources for tasks (no consumer warehouse needed)"
  - CREATE DATABASE:
      description: "Required to create internal state database for watermarks and configuration"
  - CREATE EXTERNAL ACCESS INTEGRATION:
      description: "Required to create EAI for egress to Splunk endpoints (OTLP gRPC and HEC HTTP)"
```

**References** (declared in `manifest.yml`):
- **Event Table references**: Consumer's Event Tables (e.g., `SNOWFLAKE.TELEMETRY.EVENTS` or custom) — bound via reference mechanism so the app can create streams and read telemetry data.
- **Secret references**: Snowflake Secrets storing Splunk tokens (OTLP access token, HEC token) — bound to the EAI for authenticated egress.

**Event Sharing** (declared in `manifest.yml`):
- `SNOWFLAKE$ERRORS_AND_WARNINGS` (mandatory) — enables provider-side detection of app failures in consumer accounts.
- `SNOWFLAKE$USAGE_LOGS`, `SNOWFLAKE$TRACES` (optional, via Python Permission SDK) — for deeper diagnostics when consumers opt-in. See Marketplace Compliance section for details.

The consumer is explicitly prompted (via the Streamlit UI, using the [Python Permission SDK](https://docs.snowflake.com/en/developer-guide/native-apps/requesting-privs-permissions-sdk)) to grant privileges and bind references. For example, `IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO APPLICATION <app_name>` provides read access to all ACCOUNT_USAGE views. The UI clearly explains what data each privilege exposes and why it is required.

## 2. Configuration (Streamlit UI)

**Privilege & Reference Binding**: On first launch, the Streamlit UI uses the [Python Permission SDK](https://docs.snowflake.com/en/developer-guide/native-apps/requesting-privs-permissions-sdk) (`snowflake-native-apps-permission` package) to guide the consumer through granting required privileges (Section 1) and binding references (Event Tables, Secrets). The SDK provides native Snowsight-integrated prompts — no manual SQL required from the consumer.

**Telemetry Enablement**: The Streamlit interface then guides the user to enable account-level telemetry collection.

**Monitoring Pack Selection**: Instead of requiring the user to manually select individual telemetry sources (which demands Snowflake expertise), the app offers pre-built Monitoring Packs. Each pack is a curated group of telemetry sources designed for a specific observability domain:

| Pack | Included Telemetry Sources | Use Case |
|---|---|---|
| **Distributed Tracing Pack** | User-selected Event Tables (SNOWFLAKE.TELEMETRY.EVENTS or custom) | Distributed traces (→ OTLP/gRPC), custom metrics (→ OTLP/gRPC), application logs (→ HEC), error tracking |
| **Performance Pack** | QUERY_HISTORY, TASK_HISTORY, COMPLETE_TASK_GRAPHS, LOCK_WAIT_HISTORY | Slow query detection, task failure alerting, concurrency bottlenecks |
| **Cost Pack** | METERING_HISTORY, WAREHOUSE_METERING_HISTORY, PIPE_USAGE_HISTORY, SERVERLESS_TASK_HISTORY, AUTOMATIC_CLUSTERING_HISTORY, STORAGE_USAGE, DATABASE_STORAGE_USAGE_HISTORY, DATA_TRANSFER_HISTORY, REPLICATION_USAGE_HISTORY, SNOWPARK_CONTAINER_SERVICES_HISTORY, EVENT_USAGE_HISTORY | Credit consumption, storage growth, data egress cost tracking |
| **Security Pack** | LOGIN_HISTORY, ACCESS_HISTORY, SESSIONS, GRANTS_TO_USERS, GRANTS_TO_ROLES, NETWORK_POLICIES | Failed login alerting, access auditing, privilege drift detection |
| **Data Pipeline Pack** | COPY_HISTORY, LOAD_HISTORY, PIPE_USAGE_HISTORY | Ingestion failure detection, pipeline throughput monitoring |


The user enables packs via toggle switches. Advanced users can expand each pack to deselect individual sources. This approach enables iterative development — each pack can be built, tested, and released independently.

**Destination Setup**: The user inputs backend credentials:
- Splunk Observability Cloud Connection Settings:
  - `SPLUNK_REALM`
  - `SPLUNK_ACCESS_TOKEN`
- Splunk Enterprise/Cloud Connection Settings:
  - `HEC endpoint`
  - `HEC token`

Tokens/secrets are securely stored using Snowflake Secrets. The OTLP exporter sends Event Table spans and metrics via OTLP/gRPC exclusively to Splunk Observability Cloud (see Section 7.9 for transport rationale). Event Table logs and all ACCOUNT_USAGE data are sent as structured JSON events through HTTP to the configured HEC endpoint.

**Performance Tuning**: Parameters (`export_batch_size`, `max_batches_per_run`) use hardcoded defaults optimized for typical workloads and are not exposed in the MVP UI to reduce configuration complexity. Retry behavior relies entirely on transport-level retries built into the OTLP SDK and `httpx`/`tenacity` (see MVP Scope and Section 7.2) — no user-configurable retry settings in MVP.

All settings are stored in the app's configuration table (`_internal.config`) and can be adjusted via the Streamlit UI Settings panel.


## 3. Infrastructure Provisioning (Automated Setup)

The app programmatically executes a setup routine to create the following components:

**Networking & Security** (requires `manifest_version: 2` and `CREATE EXTERNAL ACCESS INTEGRATION` privilege via automated granting):
- Network Rule to allow egress traffic from Snowflake to Splunk endpoints (OTLP gRPC and HEC HTTP).
- External Access Integration (EAI): Created in the setup script; combines the NETWORK RULE (allowing egress) and the SECRET (for authentication).
- App Specification: Defines the allowed HOST_PORTS for consumer approval of external endpoint connections (consumers must approve the app specification to enable egress).

**Staging Layer** (MVP — minimal):
- Stream offset advancement table (permanently empty — used only for the zero-row INSERT that consumes the stream):
  - `_staging.stream_offset_log`: Schema matches Event Table; never accumulates data (see Section 8.0)
```sql
-- Schema mirrors the Event Table structure; table is NEVER populated.
-- Used solely as the target for zero-row INSERT that consumes the stream (see Section 8.0).
CREATE TRANSIENT TABLE _staging.stream_offset_log LIKE <event_table>;
-- Alternatively, a minimal fixed schema if LIKE is not feasible:
-- CREATE TRANSIENT TABLE _staging.stream_offset_log (
--     _placeholder NUMBER  -- never receives rows
-- );
```

> **Note (Post-MVP):** Failure tracking tables (`_staging.failed_event_batches`, `_staging.failed_account_usage_refs`) and the zero-copy reference architecture (Section 5) are deferred to post-MVP. In MVP, if transport-level retries exhaust, the batch is dropped and the pipeline advances. See MVP Scope for details.

**Configuration & State Tables** (`_internal` schema):
- App configuration table (`_internal.config`): Stores all user-configurable settings from the Streamlit UI (Section 2).
```sql
CREATE TABLE _internal.config (
    config_key VARCHAR PRIMARY KEY,    -- e.g., 'splunk_realm', 'hec_endpoint', 'max_retry_attempts'
    config_value VARCHAR,              -- string value (cast at read time)
    config_type VARCHAR DEFAULT 'STRING', -- STRING, NUMBER, BOOLEAN, SECRET_REF
    description VARCHAR,
    updated_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    updated_by VARCHAR DEFAULT CURRENT_USER()
);
```
  Key entries include: `splunk_realm`, `splunk_access_token_secret` (SECRET reference name), `hec_endpoint`, `hec_token_secret` (SECRET reference name), `export_batch_size`, `max_batches_per_run`, and per-pack enablement flags (`pack_enabled:distributed_tracing`, `pack_enabled:performance`, etc.). Secrets are stored as Snowflake Secret objects — only the **reference name** is stored in `_internal.config`, never the token value itself. Post-MVP entries (deferred): `max_retry_attempts`, `failed_batch_retention_days`, `retry_interval_minutes`.

- High-Watermark State Table (`_internal.export_watermarks`): Defined below in the Poll-Based Pipeline section.

**Pipeline Health Observability Tables** (`_metrics` schema):
- Operational metrics table (`_metrics.pipeline_health`): Records metrics for every pipeline run. Full schema and metrics list defined in Section 9.1.
```sql
CREATE TABLE _metrics.pipeline_health (
    metric_id NUMBER AUTOINCREMENT,
    timestamp TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    pipeline_name VARCHAR,       -- 'event_table_collector', 'account_usage_source_collector'
    source_name VARCHAR,         -- 'QUERY_HISTORY', 'LOGIN_HISTORY', 'event_table:my_db.my_schema.events', etc.
    metric_name VARCHAR,         -- 'rows_collected', 'rows_exported', 'rows_failed', 'export_latency_ms', etc.
    metric_value NUMBER,
    metadata VARIANT             -- additional context (error messages, batch details)
);
```

**Event-Driven Pipeline (Event Table Pack)**:
- Python Stored Procedure (`_internal.event_table_collector`): Based on the `opentelemetry-sdk` to read Event Table streams and export directly to Splunk via OTLP. Advances the stream offset via a zero-row INSERT pattern within an explicit transaction (see Section 8.0). In MVP, relies on transport-level retries only (OTel SDK built-in retry for gRPC, `httpx`/`tenacity` for HEC); if all retries exhaust, the batch is logged as failed in `_metrics.pipeline_health` and the pipeline advances.
- Change Tracking (Stream): An `APPEND_ONLY` stream created on each selected Event Table to capture new telemetry records without duplicates ([Streams docs](https://docs.snowflake.com/en/user-guide/streams-intro): append-only streams are "notably more performant" for insert-only sources like Event Tables). Streams use a namespaced naming convention (`_splunk_obs_stream_<event_table_name>`) to avoid conflicts if the consumer has their own streams on the same Event Table. The setup script should also set `MAX_DATA_EXTENSION_TIME_IN_DAYS = 90` on tracked Event Tables to maximize the staleness prevention window (see Section 8.1).
- Serverless Triggered Task: Configured with `WHEN SYSTEM$STREAM_HAS_DATA('stream_name')` — the `SCHEDULE` parameter is **not** set (triggered and scheduled are mutually exclusive for triggered tasks). `TARGET_COMPLETION_INTERVAL` is **required** for serverless triggered tasks ([triggered tasks docs](https://docs.snowflake.com/en/user-guide/tasks-triggered)). Executes the collector procedure as soon as new telemetry data is available. Minimum trigger interval is 30 seconds by default (`USER_TASK_MINIMUM_TRIGGER_INTERVAL_IN_SECONDS`). If the task hasn't run for 12 hours, Snowflake schedules an automatic health check to prevent stream staleness. Note: `SYSTEM$STREAM_HAS_DATA()` calls on an empty stream also prevent staleness by resetting the staleness clock. See Tasks Architecture section for full DDL pattern and parameter reference.

**Poll-Based Pipeline (MVP: Performance Pack only; post-MVP: Cost / Security / Data Pipeline Packs)**:
- Python Stored Procedure (`_internal.account_usage_source_collector`): A shared, parameterized procedure that queries a single ACCOUNT_USAGE view using watermark-based incremental reads and exports directly to Splunk via HEC. Accepts source name as parameter. In MVP, relies on transport-level retries only (`httpx`/`tenacity`); if all retries exhaust, the batch is logged as failed in `_metrics.pipeline_health` and the watermark advances.
- High-Watermark State Table (`_internal.export_watermarks`): Tracks the last exported timestamp per source to avoid duplicates and missed records.
  - Schema: `(source_name VARCHAR PRIMARY KEY, last_exported_timestamp TIMESTAMP_LTZ, last_run_at TIMESTAMP_LTZ, rows_collected NUMBER, poll_interval_seconds NUMBER, last_poll_time TIMESTAMP_LTZ)`
- Serverless [Task Graph](https://docs.snowflake.com/en/user-guide/tasks-graphs) (DAG): A root task (`_internal.account_usage_root`) scheduled at configurable intervals (default: every 30 minutes, aligned with the fastest source cadence — see Section 7.8) with one child task per enabled ACCOUNT_USAGE source. Child tasks of the same parent run in parallel, each calling `account_usage_source_collector` for its designated source. A **finalizer task** (`_internal.pipeline_health_recorder_task`) is attached to the DAG and runs after all child tasks complete (regardless of success/failure) — it aggregates per-source metrics and writes them to `_metrics.pipeline_health` (see Section 7.6 for detailed architecture). All tasks in the graph must reside in the same schema (`_internal`) and share the same owner role ([task graph ownership](https://docs.snowflake.com/en/user-guide/tasks-graphs#manage-task-graph-ownership)). The task graph is managed programmatically via the [Snowflake Python API DAG classes](https://docs.snowflake.com/en/developer-guide/snowflake-python-api/snowflake-python-managing-tasks), allowing the Streamlit UI to dynamically add/remove child tasks when monitoring packs are enabled/disabled. `ALLOW_OVERLAPPING_EXECUTION` is `FALSE` (default) — only one graph run at a time. See Tasks Architecture section for full DDL patterns, parameter reference, and lifecycle management.

**Export Pipeline (Shared)**:
- Note: The `event_table_collector` and `account_usage_source_collector` procedures above each handle their own data reading AND export within a single procedure call. The "exporter" logic is embedded within each collector — there is no separate standalone exporter process. For the Event Table pipeline, transactional atomicity is achieved via explicit BEGIN/COMMIT wrapping a zero-row INSERT that consumes the stream (see Section 8.0). For the ACCOUNT_USAGE pipeline, each source runs as a parallel child task in a task graph (see Section 7.6), with each child calling the shared `account_usage_source_collector` procedure for its designated source.

> **Note (Post-MVP):** A dedicated retry task (`_internal.failed_batch_retrier`) will be added to periodically re-export persistently failed batches using the zero-copy failure tracking references. See MVP Scope for details.

**Pipeline Health Observability**:
- Internal metrics table (`_metrics.pipeline_health`): Records operational metrics for each pipeline run (schema defined above in Configuration & State Tables; full metrics list in Section 9.1).
- Streamlit dashboard page for pipeline health visualization (Sections 9.1–9.3).

**Volume Estimation** (created on initial setup):
- Python Stored Procedure (`_internal.volume_estimator`): Queries existing data in each enabled source to project expected daily/monthly throughput, helping consumers understand the data volume their Splunk environment will receive (see Section 9.2 for details). Runs during initial setup and can be re-run on demand from the Streamlit UI.

## 4. Telemetry Capture (The Producers)

### 4.1 Event Table Producer

Scope: Any Snowflake-supported code (UDFs, UDTFs, Stored Procedures, or Snowpark APIs) executing within the consumer account.

Ingestion: Snowflake automatically captures OTel-compatible events (Metrics, Logs, Traces) and writes them asynchronously to the designated Event Table. The Event Table is the only Snowflake telemetry source that supports Streams (change tracking), enabling the near-real-time event-driven pipeline.

### 4.2 ACCOUNT_USAGE Producer

Beyond the Event Table, Snowflake stores extensive operational telemetry in the `SNOWFLAKE.ACCOUNT_USAGE` schema. These are secure shared views with inherent latency (45 minutes to 3 hours depending on the view) and 1-year retention. They do not support Streams, so the app uses scheduled polling with watermark-based incremental reads.

The complete catalog of all telemetry sources is documented in **Appendix A: Comprehensive Snowflake Telemetry Source Catalog**.

## 5. The Staging Layer — Zero-Copy Reference Architecture (Post-MVP)

> **MVP Note:** This entire section describes the post-MVP failure tracking architecture. In MVP, the staging layer contains only `_staging.stream_offset_log` (for stream offset advancement). No failure tracking tables are created. See MVP Scope for details.

The app employs a **zero-copy reference-based failure tracking architecture** that eliminates data duplication while maintaining full retry capability. In the happy path (99%+ of batches), telemetry exports directly from source to destination with zero staging overhead. Only failed batches are tracked via lightweight references (hashes or natural keys) stored in dedicated failure tracking tables, achieving 99% storage reduction compared to traditional staging approaches.

### 5.1 Design Rationale

Heavy Snowpark workloads can generate millions of Event Table rows per day. Active accounts can produce millions of QUERY_HISTORY records daily. A traditional staging approach (copying all data before export) would:
- Double storage consumption
- Add significant write I/O overhead
- Create a table requiring aggressive cleanup and maintenance
- Introduce an additional bottleneck in the pipeline

The zero-copy approach eliminates these problems by leveraging two key insights:
**Insight 1 — Event Tables and ACCOUNT_USAGE views are immutable append-only sources**. Once written, rows never change. This means we can safely store lightweight pointers and re-query the original data on retry without risk of the data changing between collection and retry.

**Insight 2 — Export failures are rare (<1% of batches in healthy systems)**. Most batches export successfully on the first attempt. Storing full row copies for 99%+ of data that never needs retry is wasteful. The staging layer should only materialize references for the small minority of batches that actually fail.

### 5.2 Zero-Copy Strategy by Source Type

#### 5.2.1 Event Table Pipeline: Time-Window + Hash References

Event Table rows have no natural unique key or primary key column. To enable re-identification of specific failed rows without storing full payloads, the app uses **XXH3_128 hashing** combined with **time-window narrowing**:

**On successful export**: Zero storage overhead. The Stream is consumed (offset advances) and no staging data is written.

**On batch failure** (after all retry attempts within the exporter): The collector computes a lightweight hash for each row and stores only:
- `time_window_start` / `time_window_end`: The TIMESTAMP range of the failed batch (enables partition pruning on retry)
- `row_hashes`: An ARRAY of XXH3_128 hex strings (32 bytes per hash)
- `row_count`: How many rows this reference represents

Storage per 10K-row failed batch: ~320 KB (vs. ~15 MB for full VARIANT payloads) — **98% reduction**.

**Hash computation (pseudo)** (minimal field set for uniqueness):

```
FUNCTION compute_event_hash(row):
    SWITCH row.RECORD_TYPE:
        CASE 'SPAN':
            # SPANs have globally unique IDs - use them directly
            hash_input = trace_id + span_id
            
        CASE 'LOG':
            # LOGs identified by timestamp + message + severity
            hash_input = timestamp + value + severity_text
            
        CASE 'METRIC':
            # METRICs identified by timestamp + metric name + value
            hash_input = timestamp + metric_name + value
            
        CASE 'SPAN_EVENT':
            # SPAN_EVENTs identified by parent span + timestamp + event name
            hash_input = trace_id + span_id + timestamp + event_name
            
        CASE 'EVENT':
            # Iceberg automated refresh events — skip (not exported)
            RETURN None
            
        DEFAULT:
            # Fallback for unknown types
            hash_input = timestamp + value
    
    RETURN XXH3_128(hash_input) as hex string

```

**Why XXH3_128?**
- **Fast**: 7.5× faster than SHA-256
- **Sufficient collision resistance**: 128-bit hash provides negligible collision probability (<10^-18) for 10K-item batches
- **Lightweight**: Non-cryptographic hash optimized for speed (cryptographic properties not needed for row identification)

**Retry process**:
1. Query the Event Table using time-window narrowing: `WHERE TIMESTAMP BETWEEN :start AND :end`
   - This enables Snowflake's partition pruning (Event Tables are naturally clustered by TIMESTAMP)
   - Scans only ~100K rows (30-second window) instead of billions
2. Compute hash for each row in the time window (in Python, in-memory)
3. Filter to rows matching the stored hashes
4. Re-export the matched rows

#### 5.2.2 ACCOUNT_USAGE Pipeline: Natural Key References

ACCOUNT_USAGE views have deterministic, re-queryable rows with natural unique keys or timestamp-based identifiers. No hashing is needed — the app stores direct references:

| View | Natural Key | Reference Strategy |
|---|---|---|
| QUERY_HISTORY | `QUERY_ID` | Store array of QUERY_IDs for failed batch |
| LOGIN_HISTORY | `EVENT_ID` | Store array of EVENT_IDs |
| ACCESS_HISTORY | `QUERY_ID` + `QUERY_START_TIME` | Store array of composite keys |
| TASK_HISTORY | `QUERY_ID` + `NAME` | Store array of composite keys |
| METERING_HISTORY | `START_TIME` + `SERVICE_TYPE` | Store time range (rows identified by timestamp) |
| WAREHOUSE_METERING_HISTORY | `START_TIME` + `WAREHOUSE_ID` | Store time range |
| All other *_HISTORY views | Timestamp-based | Store time range |

**On successful export**: Zero storage overhead. The watermark advances and no staging data is written.

**On batch failure**: Store only the reference coordinates (not the data):
- For views with unique IDs: `ref_type='KEY_LIST'`, `ref_keys=['query_id_1', 'query_id_2', ...]`
- For timestamp-based views: `ref_type='TIME_RANGE'`, `ref_time_start`, `ref_time_end`

Storage per 10K-row failed batch: ~100 bytes (for time range) or ~10 KB (for key array) — **99.9% reduction** compared to full row copy.

**Retry process (pseudo)**:
```
FUNCTION retry_failed_account_usage_ref(ref):
    IF ref.ref_type == 'KEY_LIST':
        QUERY ACCOUNT_USAGE.{source_name} WHERE natural_key IN (ref_keys)
    ELSE IF ref.ref_type == 'TIME_RANGE':
        QUERY ACCOUNT_USAGE.{source_name} WHERE START_TIME BETWEEN ref_time_start AND ref_time_end
    
    EXPORT rows to Splunk via HEC
    DELETE failure reference
```

ACCOUNT_USAGE views have 1-year retention, so references remain valid for retry within any reasonable timeframe.

### 5.3 Storage Impact Comparison

| Scenario | Traditional staging (full copy) | Zero-copy reference approach |
|---|---|---|
| 10M Event Table rows/day, 0% failure | 10M rows × 1.5 KB = **15 GB/day** | **0 bytes** |
| 10M Event Table rows/day, 0.1% failure rate | 10M rows × 1.5 KB = **15 GB/day** | ~10K rows × 32 bytes = **~320 KB** (failed only) |
| 1M ACCOUNT_USAGE rows/day, 0% failure | 1M rows × 0.5 KB = **500 MB/day** | **0 bytes** |
| 1M ACCOUNT_USAGE rows/day, 0.1% failure rate | 1M rows × 0.5 KB = **500 MB/day** | ~100 reference rows × 100 bytes = **~10 KB** |
| Sustained 4-hour Splunk outage | Millions of rows buffered | **~240 time-range refs** (ACCOUNT_USAGE) + Event Table failed batch hashes |

The zero-copy approach eliminates 99.9%+ of staging storage overhead while maintaining full retry capability.

### 5.4 Benefits

- **No storage overhead for the happy path**: 99%+ of batches that export successfully never touch the failure tracking layer. Zero staging writes, zero storage consumption for normal operations.
- **98-99% storage reduction for failures**: Failed batches store only lightweight references (~320 KB for 10K-row Event Table batch vs. ~15 MB full copy; ~100 bytes to 10 KB for ACCOUNT_USAGE batches). Massive storage savings with no loss of reliability.
- **Unified failure tracking across source types**: Both Event Table and ACCOUNT_USAGE pipelines use consistent reference-based retry logic. Event Tables use time-window + hash references; ACCOUNT_USAGE uses natural key references. Both approaches store <1% of original data size.
- **Non-blocking pipeline advancement**: If Splunk is temporarily unreachable, the collectors record lightweight failure references and continue advancing (Stream offsets advance via zero-row INSERT + COMMIT per Section 8.0; watermarks advance for ACCOUNT_USAGE). The pipeline never stalls. Failed batches are preserved via references and retried independently by a separate retry task.
- **Failure isolation**: Export failures affect only the specific failed batch. A single failed Event Table batch (stored as ~320 KB of hashes) doesn't block millions of subsequent rows from being collected and exported. Failed ACCOUNT_USAGE batches (stored as ~100 bytes of time ranges or key arrays) similarly don't impact other sources.
- **Re-fetch from authoritative source**: Retry always queries fresh data from the original Event Table or ACCOUNT_USAGE view using stored references. No risk of stale data from an intermediate buffer. ACCOUNT_USAGE views retain 1 year of history, ensuring references remain valid.
- **Observable failure surface**: The failure tracking tables (`failed_event_batches`, `failed_account_usage_refs`) are the single source of truth for pipeline health. They remain small (proportional to actual failure rate, not total throughput) and surface only genuine export problems in the Pipeline Health Dashboard.
- **Simplified maintenance**: No aggressive cleanup required; reference tables remain small even under sustained failures (proportional to actual failure rate, not total throughput).

## 6. Near-Real-Time Export (The Exporter)

Each collector stored procedure (`event_table_collector` and `account_usage_source_collector`) embeds export logic within its own execution, handling routing, batching, export, and failure tracking. The Event Table pipeline uses triggered tasks (fires when stream has data), while the ACCOUNT_USAGE pipeline uses a task graph with parallel child tasks — one per enabled source — with latency-aware adaptive polling (see Sections 7.6 and 7.8).

### 6.1 Exporter Features (MVP Scope)

The exporter implements only a minimal set of features that are commonly available in the standard OpenTelemetry Collector and are required for reliable operation at scale. Features are listed in priority order for the MVP.

#### 6.1.1 Batched Export (Required)

- **What:** Batch processor semantics: export telemetry in batches instead of per-row.
- **Behavior (aligned with OTel Batch Processor):**
  - Dual trigger per signal type:
    - **Size trigger:** when batch reaches a configured item count (e.g., spans/logs/metrics/events).
    - **Time trigger:** when a maximum wait time (timeout) is reached, even if batch is not full.
- **Why:** Reduces network overhead, stabilizes throughput, and matches how OTel Collector handles batching.

#### 6.1.2 Retry on Transient Failures (Required)

- **What:** Automatic retries for transient transport issues, using native client capabilities.
- **Implementation:**
  - **OTLP/gRPC:** Use built-in retry/backoff behavior of the OTel Python OTLP exporters.
  - **HEC HTTP:** Use `httpx` + `tenacity` for retry with exponential backoff on connection/timeout/5xx/429 responses. (`httpx-retry` is not available on the Snowflake Anaconda Channel; `tenacity` provides equivalent functionality.)
- **Why:** Matches Collector's retry behavior; avoids manual re-send logic for temporary network or backend errors.

#### 6.1.3 Basic Rate Limiting / Backoff (Required at Destination Edge)

- **What:** Respect backend rate limits to avoid being throttled or dropped.
- **Implementation:**
  - **HEC:** Use a lightweight in-app token-bucket rate limiter to cap requests per second in line with Splunk HEC limits. Note: dedicated rate-limiting libraries (`httpx-ratelimit`, `httpx_ratelimiter`, `httpx-limiter`) are not available on the Snowflake Anaconda Channel, so the app implements its own. In practice, the adaptive polling schedule (Section 7.8) keeps HEC throughput at ~0.01 req/s — well below the 400 req/s safety cap — so this limiter acts as a safety net, not a primary throttle.
  - **OTLP/gRPC:** Rely on OTLP exporter's handling of `RESOURCE_EXHAUSTED` and backoff behavior.
- **Why:** Equivalent to Collector's exporter-level backoff/queueing behavior to protect backends.

#### 6.1.4 Minimal Filtering / Routing by Source (Required)

- **What:** Route data to the correct backend and format, without complex transformations.
- **Behavior:**
  - Event Tables → OTLP/gRPC to Splunk Observability Cloud (spans/logs/metrics mapping).
  - ACCOUNT_USAGE → HEC HTTP as structured JSON events.
- **Why:** Matches Collector's role of routing telemetry to appropriate exporters.

---

#### 6.1.5 Out of Scope for MVP (Exporter-Specific)

The following exporter features are deferred post-MVP (see also the consolidated **MVP Scope** section at the top of this document):

- PII redaction / field masking.
- Sampling.
- Attribute/label normalization or renaming.
- Content-based routing beyond basic source-type split.
- Advanced load-shedding or dynamic sampling based on backend pressure.
- Complex processor chains (metric transformations, span processors, etc.).
- Application-level failure tracking and dedicated retry task (see MVP Scope → Failure Tracking & Recovery).

---

### 6.2 Export Routing

The exporter reads batches directly from data sources (**Streams for Event Tables**, **watermark queries for ACCOUNT_USAGE**) and routes them based on source type and signal type:

**Event Table Streams → Split Routing by Signal Type**

- **Spans & Metrics → OTLP/gRPC (Splunk Observability Cloud)**
  
  **Spans**: Maps Event Table columns to OTLP `Span` objects:
  - `TRACE['trace_id']` → `trace_id` (unique identifier for the trace)
  - `TRACE['span_id']` → `span_id` (unique identifier for the span)
  - `RECORD['parent_span_id']` → `parent_span_id` (parent span reference; from RECORD, not TRACE)
  - `START_TIMESTAMP` → `start_time_unix_nano` (span start time)
  - `TIMESTAMP` → `end_time_unix_nano` (span end time)
  - `RECORD['name']` → `name` (span name)
  - `RECORD['kind']` → `kind` (e.g., `SPAN_KIND_INTERNAL`, `SPAN_KIND_SERVER`)
  - `RECORD['status']` → `status` (flat string, not nested; e.g., `STATUS_CODE_UNSET`, `STATUS_CODE_ERROR`)
  - `RECORD_ATTRIBUTES` → `attributes` (user-defined span attributes)
  - `SCOPE['name']` → `scope.name` (namespace of code emitting the event)
  
  **Metrics**: Maps Event Table columns to OTLP metric data points:
  - `RECORD['metric']['name']` → metric name
  - `VALUE` → metric value
  - `TIMESTAMP` → time of measurement
  - `RECORD_ATTRIBUTES` → metric attributes
  
  **Resource Attributes** (injected into OTLP `Resource` for all signals from Event Tables):
  - `RESOURCE_ATTRIBUTES['snow.executable.name']` → `snowflake.executable.name` (UDF/procedure/Streamlit name with signature)
  - `RESOURCE_ATTRIBUTES['snow.executable.type']` → `snowflake.executable.type` (FUNCTION, PROCEDURE, STREAMLIT)
  - `RESOURCE_ATTRIBUTES['snow.query.id']` → `snowflake.query.id` (query ID that initiated the trace)
  - `RESOURCE_ATTRIBUTES['snow.warehouse.name']` → `snowflake.warehouse.name`
  - `RESOURCE_ATTRIBUTES['snow.database.name']` → `snowflake.database.name`
  - `RESOURCE_ATTRIBUTES['snow.schema.name']` → `snowflake.schema.name`
  - `RESOURCE_ATTRIBUTES['db.user']` → `snowflake.user` (user executing the function/procedure)
  - `RESOURCE_ATTRIBUTES['snow.owner.name']` → `snowflake.owner` (role with OWNERSHIP privilege)
  - `RESOURCE_ATTRIBUTES['snow.session.role.primary.name']` → `snowflake.session.role` (primary role in session)
  - Account name (retrieved from Snowflake context) → `snowflake.account.name`

- **Logs → Splunk HEC HTTP (Splunk Enterprise/Cloud)**
  
  Event Table logs are application logs, naturally suited for HEC indexing. Each log row becomes a HEC event with:
  
  **HEC Event Structure:**
  - `sourcetype`: `snowflake:event_table_log`
  - `source`: `snowflake_observability_app`
  - `time`: `TIMESTAMP` (when event was ingested into Event Table)
  - `event`: Structured JSON containing:
    - `message`: `VALUE` (log message text)
    - `severity`: `RECORD['severity_text']` (e.g., "INFO", "ERROR", "WARN", "DEBUG")
    - `severity_number`: `RECORD['severity_number']` (optional; not in current Snowflake Event Table RECORD schema for LOG — include if present in RECORD_ATTRIBUTES or future schema)
    - `scope_name`: `SCOPE['name']` (logger name/class name, e.g., "python_logger", "ScalaLoggingHandler")
    - `record_type`: `RECORD_TYPE` (always "LOG" for log entries)
    - `resource_attributes`: Full `RESOURCE_ATTRIBUTES` object containing Snowflake context:
      - `snow.executable.name`: UDF/procedure name with full signature (e.g., "DO_LOGGING():VARCHAR(16777216)")
      - `snow.executable.type`: Type of executable (FUNCTION, PROCEDURE, etc.)
      - `snow.database.name`: Database containing the code
      - `snow.schema.name`: Schema containing the code
      - `snow.warehouse.name`: Warehouse running the query
      - `snow.query.id`: Query ID that generated the log entry
      - `db.user`: User executing the code
      - `snow.owner.name`: Owner of the executable
      - `snow.session.role.primary.name`: Primary role in the session
    - `record_attributes`: `RECORD_ATTRIBUTES` (user-defined log attributes if any)
  
  **Example HEC Event (to be revised at dev stage):**
  ```json
  {
    "time": 1681939249,
    "sourcetype": "snowflake:event_table_log",
    "source": "snowflake_observability_app",
    "event": {
      "message": "Logging from Python function start.",
      "severity": "INFO",
      "scope_name": "python_logger",
      "record_type": "LOG",
      "resource_attributes": {
        "snow.executable.name": "ADD_TWO_NUMBERS(A FLOAT, B FLOAT):FLOAT",
        "snow.database.name": "MY_DB",
        "snow.schema.name": "PUBLIC",
        "snow.warehouse.name": "COMPUTE_WH",
        "snow.query.id": "01a2b3c4-...",
        "db.user": "ANALYST_USER",
        "snow.session.role.primary.name": "ACCOUNTADMIN"
      }
    }
  }
```

**ACCOUNT_USAGE (Watermark Queries) → Splunk HEC HTTP (Splunk Enterprise/Cloud)**

ACCOUNT_USAGE views contain operational and usage metadata for the entire Snowflake account. This data is inherently tabular (not OTel-native), so rows are exported as structured JSON events to Splunk HEC without OTLP conversion.

**Data Source Access Pattern:**
- Read via **watermark-based incremental queries** (not Streams - ACCOUNT_USAGE views don't support change tracking)
- Latency-aware adaptive polling schedule per source
- Overlap window + deduplication to catch late-arriving data

**HEC Event Structure (Common to All ACCOUNT_USAGE Sources):**

Each ACCOUNT_USAGE row becomes a HEC event with:
- `sourcetype`: `snowflake:<view_name_lowercase>` (dynamically set per source)
- `source`: `snowflake_observability_app`
- `time`: Timestamp field from the source (varies by view - see table below)
- `event`: The full row as a JSON object (all columns preserved as-is)

**Per-Source Timestamp Mapping: (to be revised at dev stage)**

| ACCOUNT_USAGE View | Timestamp Field for `time` | Example Sourcetype |
|---|---|---|
| QUERY_HISTORY | `START_TIME` | `snowflake:query_history` |
| LOGIN_HISTORY | `EVENT_TIMESTAMP` | `snowflake:login_history` |
| ACCESS_HISTORY | `QUERY_START_TIME` | `snowflake:access_history` |
| TASK_HISTORY | `SCHEDULED_TIME` | `snowflake:task_history` |
| METERING_HISTORY | `START_TIME` | `snowflake:metering_history` |
| WAREHOUSE_METERING_HISTORY | `START_TIME` | `snowflake:warehouse_metering_history` |
| COPY_HISTORY | `LAST_LOAD_TIME` | `snowflake:copy_history` |
| LOAD_HISTORY | `LAST_LOAD_TIME` | `snowflake:load_history` |
| PIPE_USAGE_HISTORY | `START_TIME` | `snowflake:pipe_usage_history` |
| STORAGE_USAGE | `USAGE_DATE` | `snowflake:storage_usage` |
| DATABASE_STORAGE_USAGE_HISTORY | `USAGE_DATE` | `snowflake:database_storage_usage_history` |
| AUTOMATIC_CLUSTERING_HISTORY | `START_TIME` | `snowflake:automatic_clustering_history` |
| SERVERLESS_TASK_HISTORY | `START_TIME` | `snowflake:serverless_task_history` |
| DATA_TRANSFER_HISTORY | `START_TIME` | `snowflake:data_transfer_history` |
| REPLICATION_USAGE_HISTORY | `START_TIME` | `snowflake:replication_usage_history` |
| SESSIONS | `CREATED_ON` | `snowflake:sessions` |
| GRANTS_TO_USERS | `CREATED_ON` | `snowflake:grants_to_users` |
| GRANTS_TO_ROLES | `CREATED_ON` | `snowflake:grants_to_roles` |
| NETWORK_POLICIES | `CREATED` (note: not CREATED_ON) | `snowflake:network_policies` |

**Example HEC Events:**

**QUERY_HISTORY:**
```json
{
  "time": 1707649200,
  "sourcetype": "snowflake:query_history",
  "source": "snowflake_observability_app",
  "event": {
    "QUERY_ID": "01a2b3c4-5678-90ab-cdef-1234567890ab",
    "QUERY_TEXT": "SELECT * FROM CUSTOMERS WHERE REGION = 'EMEA'",
    "DATABASE_NAME": "SALES_DB",
    "SCHEMA_NAME": "PUBLIC",
    "QUERY_TYPE": "SELECT",
    "SESSION_ID": 987654321,
    "USER_NAME": "ANALYST_USER",
    "ROLE_NAME": "ANALYST_ROLE",
    "WAREHOUSE_NAME": "COMPUTE_WH",
    "WAREHOUSE_SIZE": "MEDIUM",
    "WAREHOUSE_TYPE": "STANDARD",
    "CLUSTER_NUMBER": 1,
    "QUERY_TAG": "monthly_report",
    "EXECUTION_STATUS": "SUCCESS",
    "ERROR_CODE": null,
    "ERROR_MESSAGE": null,
    "START_TIME": "2024-02-11T10:00:00.000Z",
    "END_TIME": "2024-02-11T10:00:15.234Z",
    "TOTAL_ELAPSED_TIME": 15234,
    "BYTES_SCANNED": 104857600,
    "PERCENTAGE_SCANNED_FROM_CACHE": 75.5,
    "BYTES_WRITTEN": 524288,
    "BYTES_WRITTEN_TO_RESULT": 524288,
    "ROWS_PRODUCED": 1250,
    "ROWS_INSERTED": 0,
    "ROWS_UPDATED": 0,
    "ROWS_DELETED": 0,
    "ROWS_UNLOADED": 0,
    "BYTES_DELETED": 0,
    "PARTITIONS_SCANNED": 12,
    "PARTITIONS_TOTAL": 48,
    "BYTES_SPILLED_TO_LOCAL_STORAGE": 0,
    "BYTES_SPILLED_TO_REMOTE_STORAGE": 0,
    "BYTES_SENT_OVER_THE_NETWORK": 1048576,
    "COMPILATION_TIME": 150,
    "EXECUTION_TIME": 15084,
    "QUEUED_PROVISIONING_TIME": 0,
    "QUEUED_REPAIR_TIME": 0,
    "QUEUED_OVERLOAD_TIME": 0,
    "TRANSACTION_BLOCKED_TIME": 0,
    "OUTBOUND_DATA_TRANSFER_CLOUD": "AWS",
    "OUTBOUND_DATA_TRANSFER_REGION": "us-east-1",
    "OUTBOUND_DATA_TRANSFER_BYTES": 0,
    "INBOUND_DATA_TRANSFER_CLOUD": null,
    "INBOUND_DATA_TRANSFER_REGION": null,
    "INBOUND_DATA_TRANSFER_BYTES": 0,
    "CREDITS_USED_CLOUD_SERVICES": 0.000123
  }
}
```

**LOGIN_HISTORY:**
```json
{
  "time": 1707649150,
  "sourcetype": "snowflake:login_history",
  "source": "snowflake_observability_app",
  "event": {
    "EVENT_ID": 123456789,
    "EVENT_TIMESTAMP": "2024-02-11T09:59:10.000Z",
    "EVENT_TYPE": "LOGIN",
    "USER_NAME": "ANALYST_USER",
    "CLIENT_IP": "203.0.113.42",
    "REPORTED_CLIENT_TYPE": "SNOWFLAKE_UI",
    "REPORTED_CLIENT_VERSION": "2024.01.15",
    "FIRST_AUTHENTICATION_FACTOR": "PASSWORD",
    "SECOND_AUTHENTICATION_FACTOR": "MFA_TOKEN",
    "IS_SUCCESS": "YES",
    "ERROR_CODE": null,
    "ERROR_MESSAGE": null,
    "RELATED_EVENT_ID": null,
    "CONNECTION": null
  }
}
```

**ACCESS_HISTORY:**
```json
{
  "time": 1707649200,
  "sourcetype": "snowflake:access_history",
  "source": "snowflake_observability_app",
  "event": {
    "QUERY_ID": "01a2b3c4-5678-90ab-cdef-1234567890ab",
    "QUERY_START_TIME": "2024-02-11T10:00:00.000Z",
    "USER_NAME": "ANALYST_USER",
    "DIRECT_OBJECTS_ACCESSED": [
      {
        "objectName": "SALES_DB.PUBLIC.CUSTOMERS",
        "objectDomain": "Table",
        "columns": [
          {"columnName": "CUSTOMER_ID"},
          {"columnName": "REGION"},
          {"columnName": "REVENUE"}
        ]
      }
    ],
    "BASE_OBJECTS_ACCESSED": [
      {
        "objectName": "SALES_DB.PUBLIC.CUSTOMERS",
        "objectDomain": "Table",
        "columns": [
          {"columnName": "CUSTOMER_ID"},
          {"columnName": "REGION"},
          {"columnName": "REVENUE"}
        ]
      }
    ],
    "OBJECTS_MODIFIED": [],
    "POLICIES_REFERENCED": []
  }
}
```
Key Characteristics:
- All columns preserved: No projection or filtering - full row exported as-is
- Consistent sourcetype pattern: Always snowflake:<view_name_lowercase>
- Time field alignment: Maps to the primary timestamp column of each view for chronological indexing in Splunk
- Nested objects preserved: Complex fields like DIRECT_OBJECTS_ACCESSED (ACCESS_HISTORY) sent as nested JSON
- Null handling: Null values preserved (not stripped) to maintain schema consistency


## 7. Design Decisions

This section explains the algorithms, strategies, and optimizations applied during the export process, including rationale and trade-offs.


### 7.1 Batching Strategy

The exporter uses an **OTel Batch Processor dual-trigger pattern** for all pipelines: batches are sent when **either** a time threshold (timeout) or size threshold (item count) is reached, whichever comes first. This ensures low latency for low-volume sources and high throughput for high-volume sources.

A batch is sent when either condition is met (whichever comes first):
1. Time-based trigger (timeout): Maximum wait time before sending batch
  - Default: 200ms for OTLP (low latency)
  - Default: 1000ms for HEC (latency-tolerant)

2. Size-based trigger (send_batch_size): Target number of items per batch
  - OTLP SPANs: 1024 (optimized for Splunk Observability Cloud)
  - OTLP LOGs: 2048 (logs are smaller, batch more)
  - OTLP METRICs: 512 (metrics are tiny)
  - HEC: 5000 rows (HEC optimal batch size)

3. Hard size limit (send_batch_max_size): Safety valve to split oversized batches
  - OTLP SPANs: 2048 (2× target, prevents gRPC message size rejection)
  - HEC: 10000 (prevents 1MB HEC payload limit)

Rationale:
- Low-volume sources: Timeout ensures data isn't stuck waiting (e.g., 10 spans/minute → exported within 200ms)
- High-volume sources: Size trigger ensures efficiency (e.g., 100K spans/minute → batches of 1024 exported every ~600ms)
- Predictable latency: Maximum export delay = timeout value (200ms for OTLP, 1s for HEC)
- Backend safety: send_batch_max_size prevents oversized batches from being rejected by Splunk

Configuration (per signal type):

```
BATCH_CONFIG per signal type:
    SPAN:   timeout = 200ms,  batch_size = 1024,  max_size = 2048
    LOG:    timeout = 200ms,  batch_size = 2048,  max_size = 4096
    METRIC: timeout = 200ms,  batch_size = 512,   max_size = 1024
    HEC:    timeout = 1000ms, batch_size = 5000,  max_size = 10000
```

**Event Table Pipeline (OTLP/gRPC):**

FOR each Event Table stream:
  READ rows from stream and route to signal-specific batchers (SPAN/LOG/METRIC)

```
EACH batcher triggers export when:
    - Timeout reached (200ms default), OR
    - Batch size reached (1024 spans, 2048 logs, 512 metrics)

ON export trigger:
    TRY:
        CONVERT batch to OTLP protobuf objects
        EXPORT via OTLP/gRPC (built-in gzip compression + retry)
        INSERT INTO _staging.stream_offset_log SELECT * FROM <stream> WHERE 0 = 1
        COMMIT transaction (zero-row INSERT consumes stream; offset advances)
        
    CATCH persistent failure (after gRPC retries exhausted):
        COMPUTE hashes for failed batch rows (lazy - only on failure)
        STORE failure reference (time_window, row_hashes)
        INSERT INTO _staging.stream_offset_log SELECT * FROM <stream> WHERE 0 = 1
        COMMIT transaction (zero-row INSERT consumes stream; offset advances despite failure)
```

**ACCOUNT_USAGE Pipeline (HEC HTTP):**
FOR each enabled ACCOUNT_USAGE source:
CHECK if source should be polled (latency-aware adaptive schedule)

```
IF poll due:
    GET current watermark
    READ batch from ACCOUNT_USAGE view (adaptive batch size per source)
    DEDUPLICATE if source has natural keys (handles late arrivals)
    
    Feed to HEC batcher (dual trigger: 1s timeout OR 5000 rows)
    
    ON export trigger:
        TRY:
            EXPORT via HEC HTTP as JSON events
            UPDATE watermark
            
        CATCH persistent failure:
            EXTRACT natural keys or time range (lazy - only on failure)
            STORE failure reference
            UPDATE watermark (advance to prevent stall)
```

**Key guarantees:**
- **Happy path** (99%+ of batches): Zero staging overhead, direct export from source to destination
- **Failure path**: Only lightweight references stored (hashes/keys, not full data)
- **Non-blocking**: Pipelines always advance (Streams/watermarks) even on failure
- **Recoverable**: Failed batches retried independently by dedicated retry task

---

### 7.2 Retry Strategy

Export failures are handled by **transport-level retries** using native capabilities of each protocol's client library. No custom application-level retry wrapper needed.

**OTLP/gRPC (Event Tables → Splunk Observability Cloud)**

Uses OpenTelemetry Python SDK's built-in gRPC retry mechanism:

```
CREATE OTLP/gRPC span exporter:
    endpoint = "ingest.{SPLUNK_REALM}.signalfx.com:443"
    headers  = {"X-SF-Token": SPLUNK_ACCESS_TOKEN}
    TLS      = enabled
    compression = gzip
    timeout  = 30 seconds per request
    
    # gRPC automatically retries on:
    #   UNAVAILABLE (network blip)
    #   DEADLINE_EXCEEDED (timeout)
    #   RESOURCE_EXHAUSTED (rate limit — with backoff)

CREATE similar exporters for metrics using same pattern.
```
The OTel Python OTLP/gRPC exporter implements its own application-level retry with exponential backoff (1s, 2s, 4s, 8s, 16s, 32s — ~6 retries totaling ~63s) for transient gRPC errors (UNAVAILABLE, DEADLINE_EXCEEDED, RESOURCE_EXHAUSTED). No additional retry logic needed — if all retries fail, the batch is logged as failed in `_metrics.pipeline_health` and the pipeline advances (MVP). Post-MVP: zero-copy failure tracking will record a reference for dedicated retry.

Note: The default exporter timeout is 10 seconds per attempt. The timeout parameter is in **seconds** (not milliseconds — see [open-telemetry/opentelemetry-python#4044](https://github.com/open-telemetry/opentelemetry-python/issues/4044)). Traces and Metrics signals are Stable; Logs signal is still in Development with breaking changes, which is why Event Table logs are routed via HEC, not OTLP.

**HEC HTTP (ACCOUNT_USAGE → Splunk Enterprise/Cloud)**

Uses `httpx` HTTP client with retry via `tenacity` for unified retry logic:

```
CREATE HEC HTTP client:
    base_url = "{HEC_ENDPOINT}/services/collector"
    headers  = {"Authorization": "Splunk {HEC_TOKEN}", "Content-Type": "application/json"}
    timeout  = 30 seconds

RETRY POLICY (via tenacity):
    max_attempts     = 5
    backoff          = exponential (1s, 2s, 4s, 8s, 16s)
    retry_on_status  = [429, 500, 502, 503, 504]

SEND batch:
    POST /event with JSON payload
    ON 429 response: retry with exponential backoff (tenacity)
    ON 5xx response: retry with exponential backoff (tenacity)
```

> **Note (Post-MVP):** In-app rate limiting (request pacing, Retry-After header parsing, adaptive throttling) is deferred. See MVP Scope and Section 7.10.

### 7.3 Failure Handling (Post-MVP)

> **MVP Note:** This entire section describes the post-MVP zero-copy failure tracking architecture. In MVP, failure handling is limited to transport-level retries (Section 7.2). If all retries exhaust, the batch is logged as failed in `_metrics.pipeline_health` and the pipeline advances. No failure references are stored, no dedicated retry task exists.

The app uses a **zero-copy reference-based failure tracking** approach that stores only lightweight pointers to failed batches, not full row data.

**Failure detection and tracking**:

1. **Transient failures** (network blips, temporary Splunk unavailability): Handled by exporter-level retries within the collector procedure. For OTLP/gRPC, the OTel Python exporter's built-in application-level retry handles transient errors (~6 retries with exponential backoff over ~63s). For HEC HTTP, `tenacity` provides unified retry logic with exponential backoff (5 retries configurable). If all retries fail within a single export attempt, the batch is marked as failed.

2. **Persistent batch failures** (batch still fails after all immediate retries): The exporter writes a lightweight reference to the failed batch into the appropriate staging table:
   - **Event Table batches** → `_staging.failed_event_batches` (stores time window + XXH3_128 hashes, ~320 KB per 10K-row batch)
   - **ACCOUNT_USAGE batches** → `_staging.failed_account_usage_refs` (stores natural keys or time ranges, ~100 bytes to 10 KB per batch)

3. **Pipeline advancement** (non-blocking): After recording the failure reference:
   - **Event Table**: The collector executes a zero-row INSERT referencing the stream (`INSERT INTO ... SELECT * FROM <stream> WHERE 0 = 1`) and commits the transaction. This consumes the stream (advancing the offset) without writing any data, preventing the pipeline from stalling on persistent failures (see Section 8.0).
   - **ACCOUNT_USAGE**: The collector advances the watermark for that source. This prevents the pipeline from re-reading the same failed data indefinitely.

The failed batch is preserved via its reference and can be retried later by the dedicated retry task.

**Retry mechanism (pseudo)**:
A separate low-frequency task (`_internal.failed_batch_retrier`) runs periodically (default: every 30 minutes) to retry failed batches:

```
GET max_retry_attempts from config (default: 5)

# Retry Event Table failures
FOR each failed_event_batch WHERE retry_attempts < max_retry_attempts:
    TRY:
        QUERY Event Table WHERE timestamp BETWEEN time_window_start AND time_window_end
        COMPUTE hashes for returned rows
        FILTER rows to only those matching stored row_hashes
        
        EXPORT matched rows to Splunk via OTLP
        
        DELETE failure reference (success)
        RECORD retry_success metric
        
    CATCH retry failure:
        INCREMENT retry_attempts counter
        UPDATE last_error message
        RECORD retry_failed metric

# Retry ACCOUNT_USAGE failures
FOR each failed_account_usage_ref WHERE retry_attempts < max_retry_attempts:
    TRY:
        IF ref_type == 'KEY_LIST':
            QUERY ACCOUNT_USAGE view WHERE natural_key IN (stored_keys)
        ELSE IF ref_type == 'TIME_RANGE':
            QUERY ACCOUNT_USAGE view WHERE timestamp BETWEEN time_start AND time_end
        
        EXPORT rows to Splunk via HEC
        
        DELETE failure reference (success)
        RECORD retry_success metric
        
    CATCH retry failure:
        INCREMENT retry_attempts counter
        UPDATE last_error message
        RECORD retry_failed metric

```

Automatic cleanup (no manual intervention in MVP):
- Failed batches exceeding `max_retry_attempts` (default: 5, configurable) stop being retried but remain in the failure tracking tables for observability until cleaned up.
- A daily scheduled cleanup task automatically purges failed batch references older than `failed_batch_retention_days` (default: 30 days, configurable via Streamlit UI). This prevents unbounded growth during sustained Splunk outages without requiring any manual action.
- Successfully retried batches are deleted immediately upon retry success.
- The Pipeline Health Dashboard surfaces persistent failures with full context (error messages, timestamps, row counts) for **read-only monitoring** — no manual retry or clear buttons in MVP.

Why this works for MVP:
- Simple: Uses only Snowflake-native primitives (tables, tasks, stored procedures) — no manual intervention required
- Reliable: Failed batches are preserved with minimal storage overhead until auto-purged
- Observable: All failures visible in Pipeline Health Dashboard with full error context
- Self-healing: Automatic retries handle transient issues; automatic cleanup handles unrecoverable failures after retention period
- Non-blocking: Pipelines never stall due to failures (Streams/watermarks always advance after recording failure reference)

### 7.4 Lazy Processing for Failed Batches (Post-MVP)

> **MVP Note:** This section is deferred post-MVP — requires failure tracking (Section 7.3).

Approach: Hash computation (Event Tables) and natural key extraction (ACCOUNT_USAGE) are performed only on batch failure, not proactively during happy-path exports.

**Event Tables (Hash-Based References):**
```
ON export success:
    # NO hash computation
    INSERT INTO _staging.stream_offset_log SELECT * FROM <stream> WHERE 0 = 1
    COMMIT transaction  # zero-row INSERT consumes stream; offset advances
    
ON export failure (after retries):
    # ONLY NOW compute hashes
    hashes = [compute_xxh3_128_hash(row) FOR row IN failed_batch]
    STORE (time_window, hashes)
    INSERT INTO _staging.stream_offset_log SELECT * FROM <stream> WHERE 0 = 1
    COMMIT transaction  # stream still advances; failed batch tracked for retry
```

**ACCOUNT_USAGE (Natural Key References):**
```
ON export success:
    # NO key extraction
    UPDATE watermark
    
ON export failure:
    # ONLY NOW extract keys
    IF source has unique IDs:
        keys = [row['QUERY_ID'] FOR row IN failed_batch]
        STORE (source_name, ref_type='KEY_LIST', keys)
    ELSE:
        STORE (source_name, ref_type='TIME_RANGE', time_start, time_end)
```

Rationale:
- 99%+ of batches succeed on first export attempt in healthy systems
- Computing hashes/keys proactively wastes CPU for data that never needs retry
- Lazy computation shifts overhead to the cold path (failures), keeping the hot path (successful exports) fast

### 7.5 Deduplication Strategy (ACCOUNT_USAGE Late Arrivals)
Problem: ACCOUNT_USAGE views have inherent latency (45 min to 3 hours). Data can arrive late with older timestamps than the current watermark, causing missed rows if watermark is advanced too aggressively.

Approach: Use overlap window + deduplication to catch late arrivals while preventing duplicate exports.

```sql
-- Query with overlap window (1.5× source latency)
SELECT *, ROW_NUMBER() OVER (PARTITION BY QUERY_ID ORDER BY START_TIME DESC) AS rn
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME > :watermark - (:source_latency * 1.5)
  AND START_TIME <= CURRENT_TIMESTAMP() - :source_latency
QUALIFY rn = 1  -- Deduplication via window function
LIMIT :batch_size
```

Rationale:
- Overlap window (watermark - 1.5× latency): Re-queries recent data to catch late arrivals
- Latency cutoff (NOW() - latency): Don't read data still in Snowflake's latency window (incomplete)
- QUALIFY ROW_NUMBER(): Snowflake-native deduplication — must remain as Snowpark DataFrame operations pushed to Snowflake SQL, never pulled into Pandas for dedup ([Snowpark DataFrames are 8X faster than Pandas](https://www.snowflake.com/en/developers/guides/snowpark-python-top-three-tips-for-optimal-performance/))
- Natural key partitioning (QUERY_ID, EVENT_ID): Ensures each row exported only once
- **Column projection**: Use explicit `.select()` to project only the columns needed for export, rather than `SELECT *`. This is especially important for wide views like QUERY_HISTORY (~50 columns) and ACCESS_HISTORY (nested JSON columns), where unnecessary data transfer wastes I/O and memory ([Better Practices](https://medium.com/snowflake/lets-talk-about-some-better-practices-with-snowpark-python-python-udfs-and-stored-procs-903314944402)). Since our HEC export sends full rows as JSON (Section 6.2), projection should include all columns that will be in the HEC event payload — but the Snowpark query should still use explicit `.select()` rather than relying on implicit `SELECT *`.

Per-Source Configuration:
| Source           | Latency | Overlap Window | Natural Key                              |
| ---------------- | ------- | -------------- | ---------------------------------------- |
| QUERY_HISTORY    | 45 min  | 67 min         | QUERY_ID                                 |
| LOGIN_HISTORY    | 2 hours | 3 hours        | EVENT_ID                                 |
| ACCESS_HISTORY   | 3 hours | 4.5 hours      | QUERY_ID + QUERY_START_TIME              |
| METERING_HISTORY | 3 hours | 4.5 hours      | START_TIME + SERVICE_TYPE (no unique ID) |

### 7.6 Parallel Processing via Task Graph

Approach: Use a Snowflake [task graph](https://docs.snowflake.com/en/user-guide/tasks-graphs) (DAG) to parallelize ACCOUNT_USAGE source collection. Each enabled source gets its own serverless child task that runs in parallel, with session isolation and independent error handling.

**Architecture: ACCOUNT_USAGE Collector Task Graph**

```
Root Scheduled Task (_internal.account_usage_root)
  │  schedule: every 30 minutes (serverless, matches fastest source cadence)
  │  body: determines which sources are due for polling (latency-aware schedule from Section 7.8)
  │
  ├── Child Task: query_history_collector       ── runs in parallel ──┐
  ├── Child Task: login_history_collector        ── runs in parallel ──┤
  ├── Child Task: metering_history_collector     ── runs in parallel ──┤
  ├── Child Task: task_history_collector         ── runs in parallel ──┤
  ├── Child Task: ... (one per enabled source)   ── runs in parallel ──┤
  │                                                                    │
  └── Finalizer Task: pipeline_health_recorder_task  ◄── runs after all ─┘
        body: CALL _internal.pipeline_health_recorder()
              records pipeline health metrics for all sources
```

Each child task calls a shared stored procedure (`_internal.account_usage_source_collector`) parameterized by source name. The root task uses `SYSTEM$SET_RETURN_VALUE` to pass the list of sources due for polling, and child tasks read it via `SYSTEM$GET_PREDECESSOR_RETURN_VALUE` ([task graph runtime values](https://docs.snowflake.com/en/user-guide/tasks-graphs#pass-return-values-between-tasks)). Alternatively, each child task independently checks the watermark table to determine if polling is due.

**Why task graphs over the alternatives:**

| Factor | Task graph (chosen) | UNION ALL (previously considered) | Thread-safe sessions |
|---|---|---|---|
| Parallelism | Native — child tasks of same parent [run in parallel](https://docs.snowflake.com/en/user-guide/tasks-graphs) | Single query, Snowflake engine parallelizes internally | Requires account-level flag `FEATURE_THREAD_SAFE_PYTHON_SESSION` ([blog](https://medium.com/snowflake/snowpark-python-supports-thread-safe-session-objects-d66043f36115)) |
| Session isolation | Yes — each task gets its own session | N/A (single query) | No — shared session, [no concurrent transactions](https://medium.com/snowflake/snowpark-python-supports-thread-safe-session-objects-d66043f36115) |
| Error isolation | Each task fails independently; `TASK_AUTO_RETRY_ATTEMPTS` for automatic retry | Single query — one source failure fails entire query | One thread crash can affect others |
| Consumer compatibility | Works in all accounts, no feature flags | Works in all accounts | Cannot guarantee flag enabled in consumer accounts |
| Watermark management | Each child manages its own watermark atomically | Complex — all sources in one transaction | Manual per-thread watermark coordination |
| Observability | Built-in `TASK_HISTORY`, `COMPLETE_TASK_GRAPHS` views | Single query — no per-source visibility | Manual metrics |
| Serverless scaling | Each task auto-scales independently | Single warehouse | Single procedure resources |
| Schema alignment | Not needed — each source queried independently | Required — different column sets need projection alignment | Not needed |

**Rationale:**

- **No feature flags**: Task graphs work in every consumer account. Thread-safe sessions require `FEATURE_THREAD_SAFE_PYTHON_SESSION` ([Snowpark docs](https://docs.snowflake.com/en/developer-guide/snowpark/python/working-with-dataframes#submit-snowpark-queries-concurrently)), which we cannot guarantee. The [Reddit community](https://www.reddit.com/r/snowflake/comments/1m8o304/async_stored_procedure_calls_vs_dynamically/) also confirms that ASYNC calls within a stored procedure share the same session, causing conflicts.
- **Session isolation**: Each child task runs as an independent stored procedure call with its own session. No shared state issues, no temp table conflicts ([task graph docs](https://docs.snowflake.com/en/user-guide/tasks-graphs)).
- **Native retry**: `TASK_AUTO_RETRY_ATTEMPTS` on the root task provides automatic retry for the entire graph. Individual child task failures don't block other sources. Additionally, `SUSPEND_TASK_AFTER_NUM_FAILURES` (default 10) auto-suspends after consecutive failures to prevent runaway costs ([docs](https://docs.snowflake.com/en/user-guide/tasks-intro#automatically-suspend-tasks-after-failed-runs)).
- **Native monitoring**: `COMPLETE_TASK_GRAPHS` view gives end-to-end DAG execution visibility that feeds directly into our Pipeline Health Dashboard (Section 9).
- **Finalizer task**: Runs after all child tasks complete (or fail), recording pipeline health metrics and performing cleanup — a perfect fit for our observability requirements. Each root task can have exactly one finalizer; the finalizer cannot have child tasks.
- **No overlapping execution**: `ALLOW_OVERLAPPING_EXECUTION` defaults to `FALSE` — if a graph run exceeds the schedule interval, the next run is skipped rather than overlapping. This is critical for watermark-based pipeline correctness.
- **Per-task timeouts**: `USER_TASK_TIMEOUT_MS` on the root task applies to the entire graph; the same parameter on child tasks overrides the root timeout for that specific child ([graph timeouts docs](https://docs.snowflake.com/en/user-guide/tasks-graphs#task-graph-timeouts)).

**Task graph management via Python API:**

Task graphs can be managed programmatically using the [Snowflake Python API `DAG` and `DAGTask` classes](https://docs.snowflake.com/en/developer-guide/snowflake-python-api/snowflake-python-managing-tasks), enabling the Streamlit UI to dynamically add/remove child tasks when the consumer enables/disables monitoring packs. See the Tasks Architecture section for full DDL patterns, lifecycle management, and the complete task inventory.

**Post-MVP optimization** (thread-safe sessions):

For consumer accounts with `FEATURE_THREAD_SAFE_PYTHON_SESSION` enabled and Snowpark >= 1.24, a single stored procedure could use `threading.Thread` + `ThreadPoolExecutor` to submit concurrent DataFrame queries for multiple sources within one task. This reduces task management overhead for high-source-count deployments. However, the task graph approach remains the default for maximum compatibility.

### 7.7 Source Prioritization
Approach: Process Event Table streams and ACCOUNT_USAGE sources in priority order to ensure critical telemetry exports first.

Priority Ranking:
- Active distributed traces (Event Tables with recent SPANs) — Real-time debugging dependency
- QUERY_HISTORY — High-volume performance monitoring (slow query detection)
- LOGIN_HISTORY, ACCESS_HISTORY — Security-sensitive data
- Cost sources (METERING_HISTORY, WAREHOUSE_METERING_HISTORY) — Financial tracking
- Low-volume sources (STORAGE_USAGE, REPLICATION_USAGE) — Daily granularity data

```
FUNCTION prioritize_sources():
    sources = empty list
    FOR each stream IN event_table_streams:
        latest_timestamp = GET latest timestamp from stream
        age_seconds = NOW() - latest_timestamp
        record_type_dist = GET record type distribution from stream
        
        priority = 0
        IF record_type_dist['SPAN'] > 50% AND age_seconds < 60:
            priority += 100   # Active traces (recent SPANs)
        IF row_count(stream) > 100,000:
            priority += 50    # High-volume backlog
        IF age_seconds > 3600:
            priority -= 30    # Old data (lower priority)
        
        APPEND (stream, priority) to sources
    
    RETURN sources SORTED BY priority descending
```

Rationale:
- Active traces need continuity: Exporting parent-child spans together improves backend correlation
- Prevent head-of-line blocking: Low-priority sources don't starve high-priority sources
- Better user experience: Recent errors/failures visible faster in Splunk

### 7.8 Latency-Aware Adaptive Polling Schedule
Problem: Polling all ACCOUNT_USAGE sources on every root task invocation wastes queries on sources whose data hasn't changed yet (due to inherent Snowflake latency).

Approach: The root task runs every **30 minutes** (matching the fastest source cadence — QUERY_HISTORY at 45 min latency). Each child task checks its own `should_poll_source()` watermark before doing any work. If a source is not yet due, the child exits immediately (**early-exit pattern**) with minimal serverless compute overhead. This aligns the task graph schedule (Section 7.6) with per-source polling cadences below.

Per-Source Poll Intervals:
| Source           | Snowflake Latency    | Poll Interval | Polls per day | Early-exit ratio* |
| ---------------- | -------------------- | ------------- | ------------- | ----------------- |
| QUERY_HISTORY    | 45 min               | 30 min        | 48            | 0% (polls every cycle) |
| TASK_HISTORY     | 45 min               | 30 min        | 48            | 0% (polls every cycle) |
| LOGIN_HISTORY    | 2 hours              | 60 min        | 24            | 50% (skips every other) |
| ACCESS_HISTORY   | 3 hours              | 90 min        | 16            | 67% (skips 2 of 3)     |
| METERING_HISTORY | 3 hours              | 90 min        | 16            | 67% (skips 2 of 3)     |
| STORAGE_USAGE    | 2 hours (daily data) | 6 hours       | 4             | 92% (skips 11 of 12)   |

*Early-exit ratio: fraction of root invocations where this child task starts, checks watermark, and exits without querying. Minimal compute cost (~1–2 seconds per early exit).

**Early-exit pattern (child task):**
```
FUNCTION child_task_body(source_name):
    # Step 1: Check if this source is due for polling
    IF NOT should_poll_source(source_name):
        RETURN  # Early exit — no compute, no query
    
    # Step 2: Source is due — proceed with collection
    CALL account_usage_source_collector(source_name)
```

```
FUNCTION should_poll_source(source_name):
    latency_seconds = LOOKUP source latency (e.g., 45*60 for QUERY_HISTORY)
    poll_interval = latency_seconds * 0.66  # Poll at ~2/3 of latency period
    last_poll_time = GET last poll time for source_name
    
    RETURN (NOW() - last_poll_time) >= poll_interval
```

Storage (extend export_watermarks table):
```sql
ALTER TABLE _internal.export_watermarks 
ADD COLUMN poll_interval_seconds NUMBER,
ADD COLUMN last_poll_time TIMESTAMP_LTZ;
```
Rationale:
- **Root interval = fastest source cadence (30 min):** Ensures QUERY_HISTORY and TASK_HISTORY (45 min latency) are polled optimally while slower sources skip most cycles via early exit
- ACCOUNT_USAGE views have documented latency windows — polling faster than latency is wasteful
- Polling at ~2/3 of latency period ensures data is available when query runs
- Early-exit child tasks consume negligible serverless compute (~1–2 sec each), far less than a full source query
- Finalizer task still runs every cycle to record pipeline health, including which sources were polled vs. skipped

### 7.9 OTLP Transport Selection
Decision: Use OTLP/gRPC exclusively for Event Table exports to Splunk Observability Cloud. No HTTP fallback in MVP.

Rationale:
- Splunk recommendation: Splunk explicitly recommends gRPC for SDK-based exports due to superior auth handling and retry capabilities
- Built-in compression: gRPC includes gzip compression by default (3-5× payload reduction)
- Native retry logic: gRPC automatically retries on transient failures with exponential backoff
- Protobuf efficiency: Binary serialization is more compact than JSON
- Lower latency: HTTP/2 persistent connections with multiplexing

MVP Constraint:
- No fallback to OTLP/HTTP. If gRPC is blocked by firewall/proxy, installation fails with clear error message directing user to configure network rules allowing gRPC egress to ingest.{realm}.signalfx.com:443.

Network Requirements (documented in setup guide):
- Egress allowed to ingest.*.signalfx.com:443 (gRPC/TLS)
- Protocol: HTTP/2 over TLS
- Network Rule in Snowflake Native App to allow OTLP/gRPC traffic

### 7.10 Alignment with Splunk Rate Limits (Post-MVP)

> **MVP Note:** In-app rate limiting is deferred post-MVP. MVP relies on transport-level retry handling for 429/RESOURCE_EXHAUSTED responses (Section 7.2). The analysis below informs the post-MVP implementation.

The app aligns with two distinct Splunk backend rate limits: Splunk Observability Cloud (OTLP/gRPC) and Splunk HEC (HTTP). Each has different constraints and rate limiting strategies.

Splunk Observability Cloud Rate Limits (OTLP/gRPC)
Key Limits:
| Metric                       | Limit                                    | App Strategy                                                             |
| ---------------------------- | ---------------------------------------- | ------------------------------------------------------------------------ |
| MTS creations per minute     | 6,000 (or subscription-based)            | Monitor via sf.org.numMetricTimeSeriesCreated, warn if approaching limit |
| MTS creations per hour       | 60× per-minute limit                     | Spread Event Table exports across hour with 200ms batch timeout          |
| DPM (data points per minute) | Subscription-based                       | Dual-trigger batching smooths DPM rate (no spikes)                       |
| Burst capacity               | 10× per-minute limit (up to 20 min/hour) | Leveraged during backfill/recovery scenarios                             |

**Rate Limit Configuration (OTLP Exporter):**
The OpenTelemetry gRPC exporter respects HTTP/2 flow control and Splunk's gRPC server-side rate limiting. When Splunk returns RESOURCE_EXHAUSTED status, the exporter automatically backs off.

MTS Cardinality Control:
To prevent unbounded MTS creation, the app:
- Only includes low-cardinality Snowflake metadata as OTLP resource attributes
- Excludes high-cardinality attributes (query_id, user_id, session_id) from dimensions

**Splunk HEC Rate Limits (HTTP):**
Key Limits:
| Metric              | Limit                                         | App Strategy                                               |
| ------------------- | --------------------------------------------- | ---------------------------------------------------------- |
| Requests per second | 500 requests/second (per HEC endpoint)        | In-app token-bucket limiter set to 400 req/s (80% of limit) |
| Payload size        | 1 MB per request (recommended max)            | Batch size capped at 10,000 rows (~800 KB typical)         |
| Total throughput    | No hard limit (dependent on indexer capacity) | Adaptive batch timeout (1s) prevents overwhelming indexers |

Rate Limit Configuration (pseudo):
```
HEC CLIENT CONFIGURATION:
    Layer 1 — Retry (via tenacity):
        max_attempts       = 5
        backoff_factor     = 1.0 (exponential: 1s, 2s, 4s, 8s, 16s)
        retry_on_status    = [429, 500, 502, 503, 504]

    Layer 2 — Rate Limiting (in-app token-bucket, pure Python):
        max_requests       = 400 per second (80% of HEC 500 req/s limit)
    
    Client:
        base_url = "{HEC_ENDPOINT}/services/collector"
        headers  = {"Authorization": "Splunk {HEC_TOKEN}"}
        timeout  = 30 seconds
```

How It Works:
- Proactive rate limiting: In-app token-bucket limiter enforces 400 req/s locally (never sends >400 requests/second to HEC). Actual throughput is ~0.01 req/s during normal operation (see "Adaptive Polling Prevents HEC Overload" below), so the limiter rarely activates.
- Reactive retry: If HEC still returns 429 Too Many Requests, `tenacity` backs off exponentially
- Persistent failure: If all 5 retry attempts fail, batch marked as failed and stored for later retry

Payload Size Control:
HEC recommends <1 MB per request. The app enforces this via send_batch_max_size:
```
HEC BATCH CONFIG:
    timeout          = 1000ms (1 second)
    send_batch_size  = 5000 rows (target)
    send_batch_max   = 10000 rows (safety valve, ~1 MB for ACCOUNT_USAGE rows)
```
Each ACCOUNT_USAGE row averages ~100-500 bytes, so 10,000 rows = ~500-800 KB (well below 1 MB limit).

Adaptive Polling Prevents HEC Overload:

Latency-aware polling (Section 7.8) ensures HEC isn't overwhelmed:
- 15 ACCOUNT_USAGE sources polled adaptively → ~18 queries/hour
- Each query → 1-2 HEC requests (5000-row batches)
- Total: ~30-40 HEC requests/hour (~0.01 req/s, 0.0025% of limit)

Even during recovery after sustained outage, failed batch retries stay within limits:
- Retry task runs every 30 min
- Processes max 50 batches per run
- 50 batches × 2 retries/hour = 100 HEC requests/hour (~0.03 req/s, well below 400 req/s)

### 7.11 Vectorized Transformations (Snowpark + Chunked DataFrames)
Problem: Transforming millions of Event Table rows into OTLP protobuf objects in pure Python row-by-row loops creates a CPU bottleneck and inefficient memory usage.

Approach: Use Snowpark for all heavy relational work (filtering, projection, deduplication) and perform OTLP/HEC conversion in vectorized, chunked batches in Python using [`DataFrame.to_pandas_batches()`](https://docs.snowflake.com/en/developer-guide/snowpark/reference/python/latest/snowpark/api/snowflake.snowpark.DataFrame.to_pandas_batches) — avoiding global `collect()` and per-row loops over entire datasets.

**Concrete API — `to_pandas_batches()`:**

[`DataFrame.to_pandas_batches()`](https://docs.snowflake.com/en/developer-guide/snowpark/reference/python/latest/snowpark/api/snowflake.snowpark.DataFrame.to_pandas_batches) executes the query and returns an **iterator of Pandas DataFrames** (each containing a subset of rows). This is the Snowpark-native mechanism for memory-bounded chunked processing — always available, no feature flags, no threading.

```python
# Within each collector stored procedure (per-source child task):
df = session.table("SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY").filter(
    (col("START_TIME") > watermark - overlap_window) &
    (col("START_TIME") <= current_timestamp() - source_latency)
)

for chunk in df.to_pandas_batches():    # memory-bounded Pandas DataFrames
    hec_events = convert_to_hec_json(chunk)  # vectorized Pandas → HEC JSON
    hec_client.export(hec_events)            # synchronous HEC HTTP
    # watermark advanced after all chunks exported successfully
```

For the Event Table pipeline (OTLP/HEC export), filtering and VARIANT extraction are pushed to Snowpark **per signal type** before `to_pandas_batches()` — Python never splits by RECORD_TYPE (see BP-1 in Section 7.12 and Section 7.13):

```python
# Step 1: Snowpark — filter by RECORD_TYPE and project/extract per signal
stream_df = session.table("stream_on_event_table")

spans_projected = stream_df.filter(col("RECORD_TYPE") == "SPAN").select(
    col("TIMESTAMP"), col("START_TIMESTAMP"),
    col("TRACE")["trace_id"].cast("string").alias("trace_id"),
    col("TRACE")["span_id"].cast("string").alias("span_id"),
    col("RECORD")["parent_span_id"].cast("string").alias("parent_span_id"),
    col("RECORD")["name"].cast("string").alias("span_name"),
    col("RECORD")["kind"].cast("string").alias("span_kind"),
    col("RECORD")["status"].cast("string").alias("status_code"),
    col("RECORD_ATTRIBUTES"), col("RESOURCE_ATTRIBUTES"), col("SCOPE")
)

logs_projected = stream_df.filter(col("RECORD_TYPE") == "LOG").select(
    col("TIMESTAMP"), col("VALUE"),
    col("RECORD")["severity_text"].cast("string").alias("severity_text"),
    col("RECORD_ATTRIBUTES"), col("RESOURCE_ATTRIBUTES"), col("SCOPE")
)

metrics_projected = stream_df.filter(col("RECORD_TYPE") == "METRIC").select(
    col("TIMESTAMP"), col("VALUE"),
    col("RECORD")["metric.name"].cast("string").alias("metric_name"),
    col("RECORD_ATTRIBUTES"), col("RESOURCE_ATTRIBUTES")
)

# Step 2: Python — chunked serialization and export (per signal type)
for chunk in spans_projected.to_pandas_batches():
    otlp_exporter.export_spans(convert_to_otlp_spans(chunk))

for chunk in logs_projected.to_pandas_batches():
    hec_client.export(convert_to_hec_logs(chunk))

for chunk in metrics_projected.to_pandas_batches():
    otlp_exporter.export_metrics(convert_to_otlp_metrics(chunk))
```

> **Key alignment with BP-1 and Section 7.13:** All filtering (`RECORD_TYPE`), VARIANT field extraction (`col["field"]`), and projection happen server-side in Snowpark. By the time `to_pandas_batches()` delivers chunks to Python, each row is already the right signal type with pre-extracted, typed columns — Python only serializes into OTLP protobuf or HEC JSON.

**Query optimization**: Enable `session.sql_simplifier_enabled = True` at the start of each stored procedure handler. This flattens nested subqueries generated by chained Snowpark DataFrame operations (filter + project + dedup), improving query plan efficiency ([Top Tips](https://www.snowflake.com/en/developers/guides/snowpark-python-top-tips-for-optimal-performance/)). During development, use `df.explain()` to preview the generated SQL plan and verify partition pruning on time-window filters.

Design Rationale:
1. **Snowflake engine is the workhorse**
  - Scanning Event Tables, filtering by RECORD_TYPE and time window, extracting VARIANT fields, projecting columns, and deduplicating are all set-based operations
  - Snowpark pushes these operations down to Snowflake's execution engine, which is columnar and parallelized
  - Each signal type gets its own optimized query plan with partition pruning on RECORD_TYPE

2. **Python only serializes shaped batches**
  - After Snowpark processing, each chunk is already filtered to a single signal type, projected to the exact columns needed, and deduplicated
  - Python maps pre-extracted Pandas DataFrame columns → OTLP span/log/metric objects or HEC JSON events per chunk
  - No Python-side filtering, VARIANT parsing, or type conversion needed — Snowflake already handled it

3. **Chunked processing controls memory and network**
  - `to_pandas_batches()` streams moderate-size chunks (default chunk size determined by Snowpark, typically 5K–20K rows)
  - Build OTLP/HEC payloads in vectorized style (list comprehensions over Pandas columns, minimal object churn)
  - Export each chunk synchronously before fetching the next — prevents Python memory bloat and respects gRPC/HEC message size limits
  - No threading needed — the bottleneck is network I/O (export), not CPU

Benefits:
- Maximal use of Snowflake's strengths: Parallel, columnar engine handles all relational operations
- Bounded Python work: Complexity is O(number_of_chunks), not O(total_rows) from memory perspective
- Cache locality: Building 1K–2K spans per batch is ideal for OTLP/gRPC internal batching and compression
- Always available: `to_pandas_batches()` has no feature flag requirements (unlike thread-safe sessions)

Performance Comparison:
| Approach                                       | Memory Usage  | CPU Overhead                      | Complexity    |
| ---------------------------------------------- | ------------- | --------------------------------- | ------------- |
| Naive (`collect()` all rows, loop in Python)   | O(total_rows) | High (millions of Python objects) | O(total_rows) |
| Vectorized (`to_pandas_batches()` + Snowpark)  | O(chunk_size) | Low (bounded batches)             | O(num_chunks) |

### 7.12 Snowpark Best Practices for Implementation

The following checklist maps Snowpark best practices (sourced from Snowflake engineering blogs, official guides, and community expertise) to specific implementation decisions in our app. This section is intended as a binding reference for AI-assisted development.

**BP-1. Push all relational work to Snowflake via Snowpark DataFrames — never pull into Pandas for filtering, dedup, or projection** ([8X faster than Pandas](https://www.snowflake.com/en/developers/guides/snowpark-python-top-three-tips-for-optimal-performance/), [Better Practices](https://medium.com/snowflake/lets-talk-about-some-better-practices-with-snowpark-python-python-udfs-and-stored-procs-903314944402)).
- Applies to: Section 7.5 (dedup via `QUALIFY ROW_NUMBER()`), Section 7.8 (watermark queries), Section 7.11 (`to_pandas_batches()` for serialization only).
- **Avoid `SELECT *`** on wide ACCOUNT_USAGE views — use explicit column projection (`df.select(col("QUERY_ID"), col("START_TIME"), ...)`) especially for QUERY_HISTORY (~50 columns) and ACCESS_HISTORY (nested JSON). Full-row export (Section 6.2) should still project all needed columns via Snowpark, not via `session.table()` alone.

**BP-2. Initialize expensive objects at module scope, not per handler call** ([Designing Python UDFs](https://docs.snowflake.com/en/developer-guide/udf/python/udf-python-designing), [External Access blog](https://www.snowflake.com/en/engineering-blog/snowpark-network-access-parallel-processing/)).
- **gRPC/OTLP exporter**: Create the `OTLPSpanExporter` and `OTLPMetricExporter` instances at module scope. Snowflake caches imported modules across invocations on the same warehouse, so the gRPC channel (HTTP/2 persistent connection) persists across task runs, avoiding ~300-500ms cold-start per invocation.
- **HEC HTTP client**: Create `httpx.Client()` at module scope with connection keep-alive. This reuses TCP connections across `to_pandas_batches()` chunk iterations within a single handler call and across repeated task invocations.
- **Config lookups**: Use `cachetools` (`@cached(cache=TTLCache(...))`) for any repeated reads from config tables or stage files within a handler.

**BP-3. Reuse TCP connections — do not create per-request** ([External Access blog](https://www.snowflake.com/en/engineering-blog/snowpark-network-access-parallel-processing/)).
- Snowflake imposes limits on TCP connections per sandbox. One `httpx.Client` (with built-in connection pooling) and one OTLP exporter per stored procedure is sufficient. Never create new clients per batch or per chunk.
- For HEC: the module-scoped `httpx.Client` handles connection pooling automatically.
- For gRPC: the OTLP exporter maintains a single HTTP/2 multiplexed connection internally.

**BP-4. Never use `df.cache_result()` for single-use DataFrames** ([Better Practices](https://medium.com/snowflake/lets-talk-about-some-better-practices-with-snowpark-python-python-udfs-and-stored-procs-903314944402)).
- Our ACCOUNT_USAGE and Event Table queries are single-use (read, transform, export). `cache_result()` would create unnecessary temp tables and I/O overhead.

**BP-5. Enable SQL simplifier and inspect generated SQL** ([Top Tips](https://www.snowflake.com/en/developers/guides/snowpark-python-top-tips-for-optimal-performance/), [Better Practices](https://medium.com/snowflake/lets-talk-about-some-better-practices-with-snowpark-python-python-udfs-and-stored-procs-903314944402)).
- Set `session.sql_simplifier_enabled = True` at the start of every stored procedure handler. This flattens nested subqueries from chained Snowpark operations (filter + project + dedup), improving query plan efficiency.
- During development: use `df.explain()` to preview query plans, and check Query History to verify partition pruning on Event Table time-window filters and ACCOUNT_USAGE watermark queries.

**BP-6. Consider vectorized UDFs for hash computation (post-MVP)** ([Top Three Tips Lab 2](https://www.snowflake.com/en/developers/guides/snowpark-python-top-three-tips-for-optimal-performance/) — 30-40% faster for numerical ops).
- If XXH3_128 hash computation for zero-copy failure tracking (Section 5.2.1) becomes a bottleneck on large failed batches, refactor to a vectorized UDF processing Pandas Series of concatenated row fields.
- Do NOT use vectorized UDFs for string-heavy operations (HEC JSON serialization) — benchmarks show they are slower for non-numeric data.

**BP-7. Use `ThreadPoolExecutor` + `httpx.Client` connection pooling for concurrent HEC exports (post-MVP)** ([External Access blog](https://www.snowflake.com/en/engineering-blog/snowpark-network-access-parallel-processing/)).
- For MVP: synchronous `httpx.Client` with a single connection is sufficient (HEC throughput is ~0.01 req/s).
- Post-MVP optimization for high-volume accounts: use `concurrent.futures.ThreadPoolExecutor` with a pool of synchronous `httpx.Client` instances for concurrent HEC batch exports within a single chunk iteration. This is the proven pattern demonstrated in Snowflake's official engineering blog for concurrent external network access.
- **Why not `asyncio` + `httpx.AsyncClient`?** Research findings:
  - Snowflake's stored procedure sandbox **blocks raw socket creation** ([Security Practices docs](https://docs.snowflake.com/en/developer-guide/udf-stored-procedure-security-practices): "You can't use a handler to create sockets"). All network traffic is routed through the External Access Integration proxy layer.
  - `asyncio` relies on the `selectors` module (epoll/kqueue/select) for I/O multiplexing over non-blocking sockets — it is **unknown** whether these system calls are compatible with the sandbox's network proxy.
  - The Snowflake blog mentions `asyncio` and `httpx` only in passing ("can be used to implement asynchronous tasks") but provides **zero working examples** of `asyncio` inside stored procedures or UDFs. Every official Snowflake concurrency example uses `ThreadPoolExecutor` or `joblib.Parallel`.
  - `ThreadPoolExecutor` is proven to work because Python threads release the GIL during I/O operations (network calls), achieving true concurrency for I/O-bound workloads without needing an event loop or non-blocking sockets.
  - Official concurrency pattern for stored procedures: `joblib.Parallel` with `threading` backend ([Python stored procedure examples](https://docs.snowflake.com/en/developer-guide/stored-procedure/python/procedure-python-examples)).
- Note: Snowpark's `collect_nowait()` and Snowflake Scripting's `ASYNC` keyword ([async child jobs docs](https://docs.snowflake.com/en/developer-guide/snowflake-scripting/asynchronous-child-jobs)) provide async execution for **Snowflake SQL queries** only — they are not applicable to external HTTP calls.

**BP-8. Structure code for modularity, testing, and CI/CD** ([Infinite Lambda](https://infinitelambda.com/snowpark-for-python-best-practices/)).
- Separate Python packages: `collectors/` (per-source logic), `exporters/` (OTLP + HEC clients), `ui/` (Streamlit pages), `common/` (config, watermarks, health metrics).
- Use `pytest` with Snowpark DataFrame API for integration tests against a dev schema.
- Use `poetry` or `conda` with `environment.yml` for reproducible dependency management (already pinned — see Python Runtime & Dependencies section).
- Branch-based environment isolation: feature branches deploy to separate Snowflake schemas; main branch is the single source of truth for production.

### 7.13 Data Transformation Optimization for Event Tables

Event Table rows contain VARIANT/OBJECT columns (`RECORD`, `RECORD_ATTRIBUTES`, `RESOURCE_ATTRIBUTES`, `SCOPE`, `TRACE`) that require field extraction before export. The following optimizations push transformation work into Snowflake's columnar engine rather than performing it in Python, based on Snowflake transformation best practices ([Well-Architected Framework](https://www.snowflake.com/en/developers/guides/well-architected-framework-performance/), [Coalesce guide](https://coalesce.io/data-insights/the-complete-guide-to-snowflake-data-transformation/)).

**1. Filter by `RECORD_TYPE` first** — Before any projection or extraction, filter the stream by signal type (`SPAN`, `LOG`, `METRIC`, `SPAN_EVENT`) as the first Snowpark DataFrame operation. This enables Snowflake's partition pruning and ensures each signal-specific code path only processes relevant rows:

> **Note:** `RECORD_TYPE` can also be `EVENT` (used for Iceberg automated refresh events). The app filters to `LOG`, `SPAN`, `SPAN_EVENT`, `METRIC` only; `EVENT` rows are excluded unless Iceberg event export is added in a future release.

```python
stream_df = session.table("stream_on_event_table")
spans_df  = stream_df.filter(col("RECORD_TYPE") == "SPAN")
logs_df   = stream_df.filter(col("RECORD_TYPE") == "LOG")
metrics_df = stream_df.filter(col("RECORD_TYPE") == "METRIC")
```

**2. Push VARIANT extraction into Snowpark SQL** — Use Snowflake's native `:` path notation (via Snowpark's `col["field"]` syntax) to extract typed fields from VARIANT columns server-side. Python then receives pre-extracted, typed columns — not raw VARIANT blobs:

```python
# SPAN extraction — pushed to Snowflake engine
spans_projected = spans_df.select(
    col("TIMESTAMP"),
    col("START_TIMESTAMP"),
    col("RECORD")["name"].cast("string").alias("span_name"),
    col("RECORD")["kind"].cast("string").alias("span_kind"),
    col("RECORD")["status"].cast("string").alias("status_code"),
    col("TRACE")["trace_id"].cast("string").alias("trace_id"),
    col("TRACE")["span_id"].cast("string").alias("span_id"),
    col("RECORD")["parent_span_id"].cast("string").alias("parent_span_id"),
    col("RECORD_ATTRIBUTES"),
    col("RESOURCE_ATTRIBUTES")
)

# LOG extraction — pushed to Snowflake engine
logs_projected = logs_df.select(
    col("TIMESTAMP"),
    col("VALUE").cast("string").alias("message"),
    col("RECORD")["severity_text"].cast("string").alias("severity"),
    col("SCOPE")["name"].cast("string").alias("scope_name"),
    col("RECORD_ATTRIBUTES"),
    col("RESOURCE_ATTRIBUTES")
)
```

This is critical for performance: Snowflake's columnar engine handles VARIANT path extraction orders of magnitude faster than Python-side JSON parsing. Python only handles OTLP protobuf / HEC JSON serialization of the pre-shaped Pandas chunks from `to_pandas_batches()`.

**3. Use higher-order functions for array processing** — When processing array-valued VARIANT fields (e.g., if `RECORD_ATTRIBUTES` contains nested arrays), prefer Snowflake's `FILTER`, `TRANSFORM`, and `REDUCE` higher-order functions over `LATERAL FLATTEN`:

- `REDUCE` is ~2X faster than `LATERAL FLATTEN` and ~3X faster than JavaScript UDFs ([Snowflake REDUCE blog](https://www.snowflake.com/en/engineering-blog/reduce-function-simplify-array-processing/))
- Use path notation (`:` operator) for simple field extraction; reserve FLATTEN only for true array explosion
- Example: Merge key-value pairs from an array attribute into a flat object:
  ```sql
  REDUCE(record_attributes, OBJECT_CONSTRUCT(), (acc, item) ->
      OBJECT_INSERT(acc, item['key'], item['value']))
  ```

**4. Use CTEs for complex watermark queries** — Structure watermark-based incremental queries (Section 7.5) using Common Table Expressions for readability and maintainability ([Coalesce guide](https://coalesce.io/data-insights/the-complete-guide-to-snowflake-data-transformation/), [Integrate.io](https://www.integrate.io/blog/snowflake-data-transformation/)):

```sql
WITH raw_data AS (
    SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    WHERE START_TIME > :watermark - INTERVAL '67 MINUTES'
      AND START_TIME <= CURRENT_TIMESTAMP() - INTERVAL '45 MINUTES'
),
deduped AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY QUERY_ID ORDER BY START_TIME DESC) AS rn
    FROM raw_data
    QUALIFY rn = 1
)
SELECT * EXCLUDE rn FROM deduped LIMIT :batch_size
```

**5. TRANSIENT tables for staging are correct** — Our failure tracking tables (`_staging.failed_event_batches`, `_staging.failed_account_usage_refs`) already use `CREATE TRANSIENT TABLE`, which avoids Fail-safe storage overhead. This is the recommended pattern for ephemeral operational data.

---

## 8. Stream Checkpointing (Event-Driven Pipeline Safety)

The most critical advantage of using a Stored Procedure for the Event Table collector is transaction control. However, a key Snowflake constraint governs how stream offsets advance:

> **Critical Snowflake rule:** *"Querying a stream alone does not advance its offset, even within an explicit transaction; the stream contents must be consumed in a DML statement."* ([Streams docs](https://docs.snowflake.com/en/user-guide/streams-intro#table-versioning))

This means simply reading from the stream via a Snowpark DataFrame and exporting to Splunk is **not sufficient** to advance the stream offset. The offset only advances when the stream is referenced in a DML statement (INSERT INTO, CTAS, COPY INTO) within a committed transaction.

### 8.0 Stream Offset Advancement Mechanism

To advance the stream offset while maintaining the zero-copy architecture (Section 5), the collector uses the **zero-row INSERT pattern** documented by Snowflake:

> *"Insert the current change data into a temporary table. In the INSERT statement, query the stream but include a WHERE clause that filters out all of the change data (e.g. `WHERE 0 = 1`)."* ([Streams docs](https://docs.snowflake.com/en/user-guide/streams-intro#table-versioning))

This DML statement references the stream (which advances the offset on commit) but writes zero actual rows, preserving the zero-copy design.

**Collector procedure flow:**

```
BEGIN TRANSACTION
  |
  ├── 1. Read stream via Snowpark DataFrame (repeatable read within txn)
  │      → filter by RECORD_TYPE, project/extract fields (Section 7.13)
  │      → to_pandas_batches() → serialize → export to Splunk (Section 7.11)
  |
  ├── 2a. On export SUCCESS:
  │      → Execute: INSERT INTO _staging.stream_offset_log
  │                 SELECT * FROM <stream> WHERE 0 = 1;
  │        (zero rows written; stream consumed; offset will advance on commit)
  │      → COMMIT  ✓  offset advances
  |
  └── 2b. On export FAILURE (after all retries):
         → Compute hashes for failed batch (Section 7.4)
         → INSERT failure reference INTO _staging.failed_event_batches
         → Execute: INSERT INTO _staging.stream_offset_log
                    SELECT * FROM <stream> WHERE 0 = 1;
           (zero rows written; stream consumed; offset will advance on commit)
         → COMMIT  ✓  offset advances, failed batch tracked for retry
```

> **Why `_staging.stream_offset_log`?** Any existing table can serve as the target for the zero-row INSERT. Using a dedicated (permanently empty) table makes the intent explicit and avoids side effects. The table schema matches the stream's source Event Table but never accumulates data.

**Transaction control guarantees:**

- **Atomicity**: The stream offset advances **only** when the zero-row INSERT and COMMIT both succeed. If the procedure crashes before COMMIT, the transaction rolls back and the stream offset remains unchanged — the same data will be available on the next task invocation ([Streams docs](https://docs.snowflake.com/en/user-guide/streams-intro): "To ensure multiple statements access the same change records, surround them with an explicit transaction... This locks the stream.").
- **Repeatable read isolation**: Within a transaction, all queries to the same stream return the same data ([Streams docs](https://docs.snowflake.com/en/user-guide/streams-intro#repeatable-read-isolation)). This is critical — the Snowpark DataFrame read (step 1) and the zero-row INSERT (step 2) both see the same stream snapshot. The offset advances past exactly the rows that were exported.
- **Failure handling**: On persistent export failure, the procedure records a lightweight failure reference (hashes + time window) and still advances the stream offset via the zero-row INSERT. This prevents pipeline stall while preserving retry capability.
- **Non-blocking**: The pipeline never stalls on persistent failures. The Stream always advances (via the zero-row INSERT + COMMIT), and failed batches are retried independently by the dedicated retry task.

Note: Stream checkpointing applies only to the Event Table pipeline. The ACCOUNT_USAGE poll-based pipeline uses watermark-based tracking instead (the `export_watermarks` table), which provides equivalent exactly-once-delivery semantics.

### 8.1 Stream Staleness Prevention (Critical Operational Risk)

**The risk**: A stream becomes stale when its offset falls outside the data retention period for its source table. Stale streams **cannot be recovered** — they must be recreated, and all unconsumed data between the stale offset and the current table state is lost ([Snowflake docs](https://docs.snowflake.com/en/user-guide/streams-intro#data-retention-period-and-staleness)).

**How staleness occurs in our app**:
- Default `DATA_RETENTION_TIME_IN_DAYS` for Event Tables may be as low as 1 day.
- If the data retention period is less than 14 days and a stream hasn't been consumed, Snowflake temporarily extends the retention period to the stream's offset, up to `MAX_DATA_EXTENSION_TIME_IN_DAYS` (default 14 days). This means the effective staleness window is `max(DATA_RETENTION_TIME_IN_DAYS, MAX_DATA_EXTENSION_TIME_IN_DAYS)` days from the last stream consumption ([Streams docs](https://docs.snowflake.com/en/user-guide/streams-intro#data-retention-period-and-staleness)).
- If the triggered task is suspended (app upgrade, consumer-side suspension, prolonged Splunk outage with exports failing), the stream's offset stops advancing. If this suspension exceeds the extended retention period, the stream becomes stale. Note: Snowflake automatically schedules a health check for triggered tasks that haven't run for 12 hours to help prevent stream staleness ([triggered tasks docs](https://docs.snowflake.com/en/user-guide/tasks-triggered#allow-a-triggered-task-to-run)), but this only helps when the task is **resumed** — if the task is suspended, the health check does not occur.
- `SYSTEM$STREAM_HAS_DATA()` calls (from our triggered task's `WHEN` condition) **prevent staleness only when the stream is empty** — they reset the staleness clock, provided the function returns `FALSE` ([Streams docs](https://docs.snowflake.com/en/user-guide/streams-intro#data-retention-period-and-staleness): "calling SYSTEM$STREAM_HAS_DATA on the stream prevents it from becoming stale, provided the stream is empty and the SYSTEM$STREAM_HAS_DATA function returns FALSE"). When data IS accumulating but not being consumed (export failures), `SYSTEM$STREAM_HAS_DATA()` returns `TRUE` but does NOT prevent staleness.

**Mitigation strategy**:

1. **Set `MAX_DATA_EXTENSION_TIME_IN_DAYS`** on the Event Table to the maximum safe value (up to 90 days). This should be documented as a consumer setup requirement or configured automatically in the setup script if the app has the necessary privileges:
   ```sql
   ALTER TABLE <event_table> SET MAX_DATA_EXTENSION_TIME_IN_DAYS = 90;
   ```

2. **Monitor `STALE_AFTER` timestamp** via `SHOW STREAMS` or `DESCRIBE STREAM` in the Pipeline Health Dashboard. The `STALE_AFTER` column shows when the stream is predicted to become stale. Add this as a pipeline health metric (see Section 9).

3. **Staleness alert**: Fire an alert when `STALE_AFTER` is less than 2 days in the future, displayed prominently in the Streamlit UI.

4. **Stream naming convention**: Use a distinct, namespaced name for each stream (`_splunk_obs_stream_<event_table_name>`) to avoid conflicts if the consumer also creates streams on the same Event Table for their own purposes ([Snowflake docs](https://docs.snowflake.com/en/user-guide/streams-intro#multiple-consumers-of-streams): "We recommend that users create a separate stream for each consumer").

5. **Recovery procedure** (documented in README and surfaced in Streamlit UI):
   - If a stream becomes stale, the app must recreate it: `CREATE OR REPLACE STREAM ...`
   - Data between the stale offset and current table state is lost — this is an unrecoverable gap
   - The Pipeline Health Dashboard should surface stale stream status and guide the consumer through recreation

## 9. Pipeline Health Observability

The app includes a built-in Pipeline Health Dashboard implemented as a Streamlit page using **Plotly** charts (via `st.plotly_chart`) and native Streamlit components (`st.metric`, `st.dataframe`, `st.tabs`, `st.columns`). All visualization libraries are available on the Snowflake Anaconda channel and compatible with the warehouse runtime used by Snowflake Native Apps.

### 9.1 Internal Metrics Collection

Every pipeline run (collector + exporter) records operational metrics into `_metrics.pipeline_health`:

```sql
CREATE TABLE _metrics.pipeline_health (
    metric_id NUMBER AUTOINCREMENT,
    timestamp TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    pipeline_name VARCHAR,       -- 'event_table_collector', 'account_usage_source_collector'
    source_name VARCHAR,         -- 'QUERY_HISTORY', 'LOGIN_HISTORY', 'event_table:my_db.my_schema.events', etc.
    metric_name VARCHAR,         -- 'rows_collected', 'rows_exported', 'rows_failed', 'export_latency_ms', 'batch_size', 'error_count'
    metric_value NUMBER,
    metadata VARIANT             -- additional context (error messages, batch details)
);
```

Key metrics tracked (MVP — used to power the Overview Tab):
- **rows_collected**: Number of rows ingested per collector run (per source).
- **rows_exported**: Number of rows successfully exported per exporter run.
- **rows_failed**: Number of rows that failed export after all transport-level retries exhausted.
- **export_latency_ms**: End-to-end latency from collection to successful export.
- **failed_batches_pending_retry**: Current count of failed batch references awaiting retry in `failed_event_batches` and `failed_account_usage_refs` tables.
- **error_count**: Number of export errors per run.
- **source_lag**: Time difference between the latest available data in a source and the latest exported data (indicates how "behind" the pipeline is).
- **stream_stale_after**: `STALE_AFTER` timestamp for each Event Table stream (retrieved via `DESCRIBE STREAM`). Used to drive the staleness alert in the Overview Tab (see Section 8.1).

### 9.2 Volume Estimation

On initial setup and periodically thereafter, the app runs a **telemetry volume estimator** that queries existing data in each enabled source to project expected throughput. This helps the user understand the data volume their Splunk environment will receive and assists in capacity planning:

```sql
-- Example: Estimate QUERY_HISTORY volume
SELECT 
    'QUERY_HISTORY' AS source_name,
    COUNT(*) AS rows_last_24h,
    COUNT(*) * 30 AS estimated_rows_per_month,
    ROUND(COUNT(*) * 0.5 / 1024, 2) AS estimated_mb_per_day
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME > DATEADD(hour, -24, CURRENT_TIMESTAMP());
```

The estimator runs similar queries for each enabled source and presents results in the Pipeline Health Dashboard. Estimated volumes per source (rough baselines for typical accounts):

| Source | Avg Row Size | Typical Volume (Medium Account) | Typical Volume (Large Enterprise) |
|---|---|---|---|
| Event Table (logs) | 0.5-2 KB | 100K-1M rows/day | 10M-100M rows/day |
| Event Table (spans) | 1-3 KB | 50K-500K rows/day | 5M-50M rows/day |
| QUERY_HISTORY | ~0.5 KB | 50K-200K rows/day | 1M-10M rows/day |
| LOGIN_HISTORY | ~0.3 KB | 500-5K rows/day | 10K-100K rows/day |
| WAREHOUSE_METERING_HISTORY | ~0.2 KB | 100-500 rows/day | 1K-5K rows/day |
| METERING_HISTORY | ~0.2 KB | 200-1K rows/day | 2K-10K rows/day |
| ACCESS_HISTORY | ~1 KB | 50K-200K rows/day | 1M-5M rows/day |
| TASK_HISTORY | ~0.4 KB | 1K-10K rows/day | 50K-500K rows/day |
| COPY_HISTORY | ~0.4 KB | 1K-10K rows/day | 50K-200K rows/day |
| STORAGE_USAGE | ~0.1 KB | 1 row/day | 1 row/day |

### 9.3 Pipeline Health Dashboard

The dashboard is built using native Streamlit layout components (`st.tabs`, `st.columns`) with Plotly charts (`st.plotly_chart`) and `st.metric` KPI cards.

**Overview Tab** (MVP):
- Total rows collected / exported / failed (last 24h) — displayed as `st.metric` KPI cards and a Plotly grouped bar chart by source. Data sourced from `_metrics.pipeline_health` (metrics: `rows_collected`, `rows_exported`, `rows_failed`).
- Current failed batches awaiting retry — displayed as a prominent `st.metric` card with color coding (green = 0, yellow < 10, red ≥ 10). In MVP, this reflects transport-level retry failures from the current run cycle (not persistent failure tracking).
- Pipeline up/down status per source — based on last successful run timestamp from `_metrics.pipeline_health`. Color coding: green (< 2× expected interval), yellow (2-5× expected interval), red (> 5× expected interval or never run).

**Post-MVP Dashboard Tabs** (deferred — see MVP Scope):

**Throughput Tab**:
- Rows exported over time (Plotly line chart, 1-hour resolution, last 7 days) — one line per source.
- Export latency distribution (Plotly bar chart, p50/p90/p99).

**Errors & Failures Tab** (requires failure tracking):
- Failed batches by source (Plotly bar chart, last 7 days) — shows count of batch references, not row count.
- Recent errors table via `st.dataframe` with: timestamp, source, error message, retry_attempts, row_count.
- Failed batches are automatically retried (up to `max_retry_attempts`) and auto-purged after `failed_batch_retention_days`. Manual retry/clear buttons deferred further.

**Stream Health Tab**:
- Stream health status per Event Table stream — shows `STALE_AFTER` timestamp from `SHOW STREAMS`, with color coding: green (> 7 days remaining), yellow (2-7 days remaining), red (< 2 days remaining or already stale). Stale streams trigger a prominent warning banner with a link to the recovery procedure (see Section 8.1).

**Volume Estimation Tab**:
- Estimated daily/monthly volume per enabled source (`st.dataframe` + Plotly bar chart).
- Comparison of estimated vs. actual exported volume.

**Rate Limits Tab** (requires rate limit handling):
- Splunk Observability Cloud (To be defined)
- Splunk HEC:
  - hec.requests_sent (HEC API calls per minute)
  - hec.requests_rate_limited (count of 429 responses)
  - hec.avg_batch_size (tracks payload efficiency)

---

# Appendix A: Comprehensive Snowflake Telemetry Source Catalog

This catalog covers all Snowflake-native telemetry sources useful for observability monitoring. Sources are organized by monitoring domain.

## A.1 Application Telemetry (Event Table)

The Event Table is the primary real-time telemetry source and the only source that supports Streams (change tracking). It is the foundation of the event-driven pipeline.

| Attribute | Details |
|---|---|
| **Location** | `SNOWFLAKE.TELEMETRY.EVENTS` (default) or custom event tables |
| **Data Types** | LOG, SPAN, SPAN_EVENT, METRIC |
| **Update Frequency** | Real-time (sub-second writes by Snowflake runtime) |
| **Data Latency** | None — rows appear immediately after emission |
| **Retention** | Configurable (governed by table retention settings) |
| **Supports Streams** | Yes — APPEND_ONLY streams supported |
| **Volume** | Highly variable; heavy Snowpark workloads can generate millions of rows/day |
| **Key Columns** | `TIMESTAMP`, `RESOURCE_ATTRIBUTES`, `RECORD` (severity/span name), `RECORD_TYPE` (LOG/SPAN/SPAN_EVENT/METRIC/EVENT), `RECORD_ATTRIBUTES`, `VALUE`, `SCOPE`, `TRACE` (OBJECT with keys `trace_id`, `span_id` — not top-level columns), `START_TIMESTAMP`, `OBSERVED_TIMESTAMP` |
| **Resource Attributes** | `snow.database.name`, `snow.schema.name`, `snow.warehouse.name`, `snow.query.id`, `snow.executable.name`, `snow.executable.type`, `snow.session.id`, `db.user` |
| **Example Record (LOG)** | `RECORD_TYPE=LOG`, `RECORD={severity_text: "INFO"}`, `VALUE="Processing batch 42"`, `RESOURCE_ATTRIBUTES={snow.warehouse.name: "COMPUTE_WH"}` |
| **Example Record (SPAN)** | `RECORD_TYPE=SPAN`, `RECORD={name: "my_procedure", kind: "SERVER", parent_span_id: "def456...", status: "STATUS_CODE_UNSET"}`, `START_TIMESTAMP=2026-02-10T10:00:00Z`, `TRACE={trace_id: "abc123...", span_id: "789xyz..."}` |
| **Example Record (METRIC)** | `RECORD_TYPE=METRIC`, `RECORD={metric.name: "rows_processed"}`, `VALUE=1500` |
| **Monitoring Use Cases** | Application debugging, distributed tracing, custom metrics, error detection, performance profiling of UDFs/procedures |

## A.2 Cost & Credit Monitoring

These views track financial/resource consumption. None support Streams — the app uses poll-based collection.

| View | Latency | Retention | Key Columns | Monitoring Use Case | Approx. Volume |
|---|---|---|---|---|---|
| **METERING_HISTORY** | 3 hours | 1 year | `SERVICE_TYPE`, `ENTITY_ID`, `NAME`, `CREDITS_USED`, `CREDITS_USED_COMPUTE`, `CREDITS_USED_CLOUD_SERVICES`, `START_TIME`, `END_TIME` | Overall account credit consumption by service type | 1 row/hour/service entity |
| **WAREHOUSE_METERING_HISTORY** | 3 hours | 1 year | `WAREHOUSE_NAME`, `WAREHOUSE_ID`, `CREDITS_USED`, `CREDITS_USED_COMPUTE`, `CREDITS_USED_CLOUD_SERVICES` | Per-warehouse credit usage, idle time detection | 1 row/hour/active warehouse |
| **PIPE_USAGE_HISTORY** | 3 hours | 1 year | `PIPE_NAME`, `PIPE_ID`, `CREDITS_USED`, `BYTES_INSERTED`, `FILES_INSERTED`, `START_TIME`, `END_TIME` | Snowpipe credit consumption, ingestion throughput | 1 row/hour/active pipe |
| **SERVERLESS_TASK_HISTORY** | 3 hours | 1 year | `START_TIME`, `END_TIME`, `CREDITS_USED` | Credit consumption by serverless tasks | 1 row/hour/task |
| **AUTOMATIC_CLUSTERING_HISTORY** | 3 hours | 1 year | `TABLE_NAME`, `CREDITS_USED`, `NUM_BYTES_RECLUSTERED`, `NUM_ROWS_RECLUSTERED`, `START_TIME`, `END_TIME` | Clustering cost tracking, over-clustered table detection | 1 row/hour/clustered table |
| **DATABASE_STORAGE_USAGE_HISTORY** | 2 hours | 1 year | `USAGE_DATE`, `DATABASE_NAME`, `DATABASE_ID`, `AVERAGE_DATABASE_BYTES`, `AVERAGE_FAILSAFE_BYTES` | Storage growth tracking per database | 1 row/day/database |
| **STORAGE_USAGE** | 2 hours | 1 year | `USAGE_DATE`, `STORAGE_BYTES`, `STAGE_BYTES`, `FAILSAFE_BYTES`, `HYBRID_TABLE_STORAGE_BYTES` | Account-wide storage trending and forecasting | 1 row/day |
| **DATA_TRANSFER_HISTORY** | 2 hours | 1 year | `SOURCE_CLOUD`, `SOURCE_REGION`, `TARGET_CLOUD`, `TARGET_REGION`, `BYTES_TRANSFERRED`, `TRANSFER_TYPE` | Cross-cloud/cross-region data egress cost tracking | 1 row/hour/transfer type |
| **REPLICATION_USAGE_HISTORY** | 3 hours | 1 year | `DATABASE_NAME`, `CREDITS_USED`, `BYTES_TRANSFERRED`, `START_TIME`, `END_TIME` | Replication credit and bandwidth monitoring | 1 row/hour/replicated DB |
| **SNOWPARK_CONTAINER_SERVICES_HISTORY** | 3 hours | 1 year | `START_TIME`, `END_TIME`, `COMPUTE_POOL_NAME`, `IS_EXCLUSIVE`, `APPLICATION_NAME`, `APPLICATION_ID`, `CREDITS_USED` | SPCS compute pool credit usage | 1 row/hour/compute pool |
| **EVENT_USAGE_HISTORY** | 3 hours | 1 year | `START_TIME`, `END_TIME`, `CREDITS_USED`, `BYTES_INGESTED` | Cost of event table telemetry ingestion | 1 row/hour |
| **DATA_QUALITY_MONITORING_USAGE_HISTORY** | varies | 1 year | `START_TIME`, `END_TIME`, `CREDITS_USED` | DMF (Data Metric Function) execution cost | 1 row/hour |

## A.3 Performance & Query Monitoring

| View | Latency | Retention | Key Columns | Monitoring Use Case | Approx. Volume |
|---|---|---|---|---|---|
| **QUERY_HISTORY** | 45 min | 1 year | `QUERY_ID`, `QUERY_TEXT`, `USER_NAME`, `WAREHOUSE_NAME`, `EXECUTION_STATUS`, `TOTAL_ELAPSED_TIME`, `EXECUTION_TIME`, `COMPILATION_TIME`, `QUEUED_OVERLOAD_TIME`, `BYTES_SCANNED`, `BYTES_SPILLED_TO_LOCAL_STORAGE`, `BYTES_SPILLED_TO_REMOTE_STORAGE`, `ROWS_PRODUCED`, `CREDITS_USED_CLOUD_SERVICES`, `QUERY_TAG`, `START_TIME`, `END_TIME` | Slow query detection, warehouse sizing, spill analysis, cost-per-query attribution | 1 row/query; millions/day for active accounts |
| **TASK_HISTORY** | 45 min | 1 year | `NAME`, `QUERY_TEXT`, `STATE` (SUCCEEDED/FAILED/CANCELLED/SKIPPED), `SCHEDULED_TIME`, `COMPLETED_TIME`, `ERROR_CODE`, `ERROR_MESSAGE`, `QUERY_ID` | Task failure alerting, task SLA monitoring, pipeline health | 1 row/task execution |
| **COMPLETE_TASK_GRAPHS** | 45 min | 1 year | `ROOT_TASK_NAME`, `STATE`, `FIRST_ERROR_TASK_NAME`, `FIRST_ERROR_MESSAGE`, `SCHEDULED_TIME`, `COMPLETED_TIME`, `GRAPH_VERSION` | End-to-end pipeline (DAG) health, failure root cause in task chains | 1 row/graph execution |
| **COPY_HISTORY** | 2 hours (up to 2 days*) | 1 year | `FILE_NAME`, `STAGE_LOCATION`, `TABLE_NAME`, `STATUS`, `ROW_COUNT`, `ROW_PARSED`, `FILE_SIZE`, `ERROR_COUNT`, `FIRST_ERROR_MESSAGE` | Data ingestion monitoring, COPY INTO failure detection | 1 row/file/load operation |
| **LOAD_HISTORY** | 90 min (up to 2 days*) | 1 year | `TABLE_NAME`, `FILE_NAME`, `STATUS`, `ROW_COUNT`, `ROW_PARSED`, `FIRST_ERROR_MESSAGE`, `LAST_LOAD_TIME` | Historical data load tracking | 1 row/file/load |
| **LOCK_WAIT_HISTORY** | 1 hour | 1 year | `QUERY_ID`, `TABLE_NAME`, `LOCK_TYPE`, `LOCK_WAIT_STARTED`, `LOCK_WAIT_ENDED` | Concurrency bottleneck detection, DML contention alerting | 1 row/lock wait event |

*COPY_HISTORY (2 hours) / LOAD_HISTORY (90 minutes) base latency can increase up to 2 days if fewer than 32 DML statements or 100 rows have been added to the target table since the last update ([COPY_HISTORY docs](https://docs.snowflake.com/en/sql-reference/account-usage/copy_history), [LOAD_HISTORY docs](https://docs.snowflake.com/en/sql-reference/account-usage/load_history)).

## A.4 Security & Access Monitoring

| View | Latency | Retention | Key Columns | Monitoring Use Case | Approx. Volume |
|---|---|---|---|---|---|
| **LOGIN_HISTORY** | 2 hours | 1 year | `EVENT_TIMESTAMP`, `USER_NAME`, `CLIENT_IP`, `REPORTED_CLIENT_TYPE`, `IS_SUCCESS`, `ERROR_CODE`, `FIRST_AUTHENTICATION_FACTOR`, `SECOND_AUTHENTICATION_FACTOR` | Failed login alerting, brute-force detection, MFA compliance | 1 row/login attempt |
| **ACCESS_HISTORY** | 3 hours | 1 year | `QUERY_ID`, `QUERY_START_TIME`, `USER_NAME`, `DIRECT_OBJECTS_ACCESSED`, `BASE_OBJECTS_ACCESSED`, `OBJECTS_MODIFIED`, `POLICIES_REFERENCED` | Data access auditing, column-level lineage, sensitive data access tracking | 1 row/query (Enterprise+) |
| **SESSIONS** | 3 hours | 1 year | `SESSION_ID`, `LOGIN_EVENT_ID`, `USER_NAME`, `AUTHENTICATION_METHOD`, `CLIENT_APPLICATION_ID`, `CREATED_ON` | Session analytics, audit trail (join with LOGIN_HISTORY) | 1 row/session |
| **DATA_CLASSIFICATION_LATEST** | 3 hours | current | Classification tags, object identifiers | Sensitive data inventory, compliance posture monitoring | 1 row/classified column |
| **GRANTS_TO_USERS** | 2 hours | current (snapshot) | `ROLE`, `GRANTEE_NAME`, `GRANTED_BY`, `CREATED_ON` | Privilege escalation detection | 1 row/grant |
| **GRANTS_TO_ROLES** | 2 hours | current (snapshot) | `PRIVILEGE`, `GRANTED_ON` (object kind), `NAME`, `GRANTED_TO`, `GRANTEE_NAME`, `CREATED_ON`, `DELETED_ON` | Permission drift monitoring | 1 row/grant |
| **NETWORK_POLICIES** | 2 hours | current | `NAME`, `ALLOWED_IP_LIST`, `BLOCKED_IP_LIST`, `CREATED`, `LAST_ALTERED` | Network security posture | 1 row/policy |

## A.5 Object Metadata (Snapshot Views)

These provide current-state metadata for inventory enrichment and drift detection. Useful as context for other telemetry.

| View | Latency | Key Columns | Monitoring Use Case |
|---|---|---|---|
| **DATABASES** | 2 hours | `DATABASE_NAME`, `DATABASE_OWNER`, `CREATED`, `DELETED`, `IS_TRANSIENT` | Database inventory, drift detection |
| **SCHEMAS** | 2 hours | `SCHEMA_NAME`, `CATALOG_NAME`, `SCHEMA_OWNER`, `CREATED`, `DELETED` | Schema inventory |
| **TABLES** | 90 min | `TABLE_NAME`, `TABLE_TYPE`, `ROW_COUNT`, `BYTES`, `CLUSTERING_KEY`, `IS_TRANSIENT` | Table growth monitoring, row count anomalies |
| **COLUMNS** | 2 hours | `COLUMN_NAME`, `TABLE_NAME`, `DATA_TYPE`, `IS_NULLABLE` | Schema change detection |
| **WAREHOUSES** | 2 hours | `WAREHOUSE_NAME`, `SIZE`, `TYPE`, `AUTO_SUSPEND`, `AUTO_RESUME`, `MIN_CLUSTER_COUNT`, `MAX_CLUSTER_COUNT` | Warehouse configuration auditing |
| **USERS** | 2 hours | `NAME`, `LOGIN_NAME`, `DISABLED`, `LAST_SUCCESS_LOGIN` | Dormant account detection |
| **ROLES** | 2 hours | `NAME`, `OWNER`, `CREATED_ON`, `DELETED_ON` | RBAC inventory |
| **FUNCTIONS** | 2 hours | `FUNCTION_NAME`, `FUNCTION_SCHEMA`, `ARGUMENT_SIGNATURE`, `FUNCTION_LANGUAGE` | UDF/UDTF inventory |
| **PROCEDURES** | 2 hours | `PROCEDURE_NAME`, `PROCEDURE_SCHEMA`, `ARGUMENT_SIGNATURE` | Stored procedure inventory |
| **PIPES** | 2 hours | `PIPE_NAME`, `DEFINITION`, `IS_AUTOINGEST_ENABLED` | Pipe configuration audit |
| **FILE_FORMATS** | 2 hours | `FILE_FORMAT_NAME`, `FILE_FORMAT_TYPE` | File format inventory |
| **SEQUENCES** | 2 hours | `SEQUENCE_NAME`, `NEXT_VALUE`, `INCREMENT` | Sequence inventory |

> **Note:** Column lists in Appendix A are **representative** (key columns for monitoring use cases), not exhaustive. Many ACCOUNT_USAGE views contain additional columns. Implementers should consult the per-view documentation for full schemas: [ACCOUNT_USAGE view list](https://docs.snowflake.com/en/sql-reference/account-usage), [COPY_HISTORY](https://docs.snowflake.com/en/sql-reference/account-usage/copy_history), [LOAD_HISTORY](https://docs.snowflake.com/en/sql-reference/account-usage/load_history), etc.

---

# Technical Prerequisites

**Standard Compliance**:
- Must strictly follow the OpenTelemetry data model for relational-to-OTLP mapping (Event Table data only)
- Must define clear mapping rules for ACCOUNT_USAGE tabular data to Splunk HEC JSON format
- Must strictly follow Snowflake Event Table syntax, schema, and querying best practices:
  - Event table overview & common rules: https://docs.snowflake.com/en/developer-guide/logging-tracing/event-table-setting-up
  - Working with event tables: https://docs.snowflake.com/en/developer-guide/logging-tracing/event-table-operations
  - Event Table columns: https://docs.snowflake.com/en/developer-guide/logging-tracing/event-table-columns
  - Unhandled exceptions handling: https://docs.snowflake.com/en/developer-guide/logging-tracing/unhandled-exception-messages
  - Querying Log Messages: https://docs.snowflake.com/en/developer-guide/logging-tracing/logging-accessing-messages
  - Querying Metric Data: https://docs.snowflake.com/en/developer-guide/logging-tracing/metrics-viewing-data
  - Querying Trace Data: https://docs.snowflake.com/en/developer-guide/logging-tracing/tracing-accessing-events
- Streamlit UI patterns and design must be algined with Streamlit limitations  in Snowflake: https://docs.snowflake.com/en/developer-guide/streamlit/limitations 
- ACCOUNT_USAGE reference (full view list and per-view schemas): https://docs.snowflake.com/en/sql-reference/account-usage
- Snowflake Native App privilege model: https://docs.snowflake.com/en/developer-guide/native-apps/requesting-privs

> **Implementation note:** Before coding, implementers must verify all ACCOUNT_USAGE view/column names and data types against the linked Snowflake reference docs (per-view pages under [ACCOUNT_USAGE](https://docs.snowflake.com/en/sql-reference/account-usage)) and Event Table column definitions at [event-table-columns](https://docs.snowflake.com/en/developer-guide/logging-tracing/event-table-columns). Snowflake may update schemas between releases; run `DESCRIBE TABLE` or check `INFORMATION_SCHEMA` at build time to catch any environment or version differences.

**Security**: Must use External Network Access and Secrets to avoid exposing backend credentials in plaintext.

**Scalability**: Must utilize Snowflake Serverless compute to handle variable telemetry volumes without manual warehouse management.

**Configuration Persistence**: Must store own settings (Splunk connections, enabled monitoring packs, alert rules, watermarks, pipeline health metrics) in internal Snowflake tables within the app's schema.

**Required Consumer Privileges** (declared in `manifest.yml` with `manifest_version: 2`):
- `IMPORTED PRIVILEGES ON SNOWFLAKE DB` — access to ACCOUNT_USAGE views
- `EXECUTE TASK` — authorize the app's task owner role to run tasks
- `EXECUTE MANAGED TASK` — provision serverless compute for tasks
- `CREATE DATABASE` — create internal state/config database (if needed)
- `CREATE EXTERNAL ACCESS INTEGRATION` — create EAI for egress to Splunk endpoints (via automated granting; requires app specification for consumer approval)
- References to consumer's custom Event Tables (via Snowflake Native App reference mechanism)

## OpenTelemetry Python SDK: Known Issues & Constraints

The app depends on the [OpenTelemetry Python SDK](https://github.com/open-telemetry/opentelemetry-python) (specifically `opentelemetry-sdk` and `opentelemetry-exporter-otlp-proto-grpc`) for Event Table telemetry export. The following known issues and constraints must be accounted for during development.

### Signal Stability

| Signal | SDK Status | App Usage |
|---|---|---|
| **Traces (Spans)** | ✅ Stable | Event Table SPANs → OTLP/gRPC → Splunk Observability Cloud |
| **Metrics** | ✅ Stable | Event Table METRICs → OTLP/gRPC → Splunk Observability Cloud |
| **Logs** | ⚠️ Development (breaking changes expected) | **Not used via OTLP** — Event Table LOGs are routed via HEC HTTP to avoid dependency on the unstable Logs API. If Logs signal reaches Stable in the future, OTLP log export can be reconsidered as a post-MVP optimization. |

### gRPC Exporter Retry Behavior

The OTLP/gRPC exporter implements its **own application-level retry** (not native gRPC retry) inside `OTLPExporterMixin._export()`:
- Exponential backoff: `1s → 2s → 4s → 8s → 16s → 32s` (~6 retries, ~63s total)
- Retries on transient gRPC status codes: `UNAVAILABLE`, `DEADLINE_EXCEEDED`, `RESOURCE_EXHAUSTED`, `CANCELLED`, `ABORTED`
- Default timeout: **10 seconds** per attempt (overridable via `timeout` parameter, in **seconds** not milliseconds)
- After all retries exhausted, the exporter returns `FAILURE` — at which point our zero-copy failure tracking records a lightweight reference for later retry by the dedicated retry task.

### Known Issues (Resolved) — Design Validation

| Issue | Resolution | How Our Design Accounts For It |
|---|---|---|
| [#4517](https://github.com/open-telemetry/opentelemetry-python/issues/4517) — gRPC `UNAVAILABLE` retry gets stuck permanently after collector restart | Fixed in recent versions | Use latest SDK version; our failure tracking handles persistent failures regardless |
| [#4435](https://github.com/open-telemetry/opentelemetry-python/issues/4435) — gRPC exporter doesn't reconnect if endpoint down at start | Fixed | Validates need for robust failure tracking even during initial setup |
| [#4688](https://github.com/open-telemetry/opentelemetry-python/issues/4688) — `OTLPLogExporter` infinite loop when collector down + logs on root logger | Fixed | **Avoided by design** — we do NOT use OTLP for logs, and must NEVER attach OTel export handlers to Python's root logger in stored procedures |
| [#3309](https://github.com/open-telemetry/opentelemetry-python/issues/3309) — Shutdown takes >60s when destination unreachable | Fixed | Critical for stored procedure execution time budgets; resolved in recent SDK versions |
| [#2710](https://github.com/open-telemetry/opentelemetry-python/issues/2710) — gRPC fails with >4MB payload (`RESOURCE_EXHAUSTED`) | Fixed (configurable) | **Validates our `send_batch_max_size` design**: 2048 spans × ~1.5KB ≈ 3MB, well under the 4MB gRPC default limit |

### Known Issues (Open) — Risks to Monitor

| Issue | Status | Risk & Mitigation |
|---|---|---|
| [#4044](https://github.com/open-telemetry/opentelemetry-python/issues/4044) — `OTEL_EXPORTER_OTLP_TIMEOUT` env var treated as seconds, not milliseconds (spec non-compliance) | Open | **Must set timeout via constructor parameter (in seconds), not env var.** Our pseudo-code already specifies `timeout = 30 seconds` which is correct. |
| [#3833](https://github.com/open-telemetry/opentelemetry-python/issues/3833) — HTTP OTLP exporter doesn't support HTTP/2 (uses `requests` library) | Open | **Validates our gRPC-only decision** — the HTTP exporter cannot work with HTTP/2-only endpoints. Not a risk since we use gRPC exclusively. |
| [#4171](https://github.com/open-telemetry/opentelemetry-python/issues/4171) — Slow import time (~367ms for HTTP exporter, similar for gRPC due to protobuf + grpcio) | Open | **Cold-start concern for stored procedures.** The first invocation of each stored procedure will incur ~300-500ms import overhead for OTel + protobuf + grpcio. Mitigation: Snowflake caches imported packages across invocations on the same warehouse, so subsequent calls are fast. Factor this into `TARGET_COMPLETION_INTERVAL` for triggered tasks. |

### Constraints for Snowflake Stored Procedure Environment

#### 1. `BatchSpanProcessor` daemon thread is incompatible — use `SimpleSpanProcessor`

**The problem**: The OTel Python SDK's `BatchSpanProcessor` delegates to an internal `BatchProcessor` class ([source: `opentelemetry-sdk/_shared_internal/__init__.py`](https://github.com/open-telemetry/opentelemetry-python/blob/main/opentelemetry-sdk/src/opentelemetry/sdk/_shared_internal/__init__.py)) which spawns a **daemon background thread** on construction:

```python
# From BatchProcessor.__init__() in opentelemetry-sdk
self._worker_thread = threading.Thread(
    name=f"OtelBatch{exporting}RecordProcessor",
    target=self.worker,
    daemon=True,    # <-- daemon thread
)
self._worker_thread.start()
```

This daemon thread runs a `while not self._shutdown` loop that sleeps for `schedule_delay` (default 5s), then wakes up to export queued spans. Spans submitted via `emit()` are buffered in a `collections.deque` and only exported when the worker thread wakes up — either on the schedule timer or when the queue exceeds `max_export_batch_size`.

**Why this fails in Snowflake stored procedures**: Snowflake stored procedures have a request-response execution model — the Python handler function runs, returns a result, and the runtime terminates ([Snowflake docs: Stored procedures overview](https://docs.snowflake.com/en/developer-guide/stored-procedure/stored-procedures-overview)). Additionally, the [Python stored procedure limitations](https://docs.snowflake.com/en/developer-guide/stored-procedure/python/procedure-python-limitations) page explicitly states: **"Creating processes is not supported in stored procedures."** While `threading.Thread` is technically distinct from `subprocess`/`os.fork()`, daemon threads are terminated abruptly when the main thread exits ([Python docs: `threading.Thread.daemon`](https://docs.python.org/3/library/threading.html#threading.Thread.daemon) — "Daemon threads are abruptly stopped at shutdown"). In a stored procedure, the main thread exits when the handler returns. Any spans still queued in the `BatchProcessor._queue` deque at that point will be **silently lost** — the daemon worker thread is killed before it can export them.

Furthermore, Snowflake's [UDF/procedure design guidance](https://docs.snowflake.com/en/developer-guide/udf/python/udf-python-designing) explicitly recommends: **"Write UDF handlers that are single-threaded. Snowflake will handle partitioning the data and scaling."** And that handlers should protect shared state using `threading` synchronization primitives only when necessary for initialization caching — not for background processing.

**The mitigation — `SimpleSpanProcessor` (synchronous export)**:

Use `SimpleSpanProcessor` instead. It exports spans **synchronously inline** on each `on_end()` call — no background thread, no buffering, no daemon. From the same OTel SDK source file:

```python
# From SimpleSpanProcessor.on_end() in opentelemetry-sdk
def on_end(self, span: ReadableSpan) -> None:
    if not (span.context and span.context.trace_flags.sampled):
        return
    token = attach(set_value(_SUPPRESS_INSTRUMENTATION_KEY, True))
    try:
        self.span_exporter.export((span,))  # <-- exports immediately, inline
    except Exception:
        logger.exception("Exception while exporting Span.")
    detach(token)
```

This is safe for stored procedures: every span is exported before the handler returns, no daemon threads, no risk of data loss. The tradeoff is higher per-span latency (each span triggers a network call), which is why our architecture uses **application-level batching** in the collector procedure itself (accumulating spans in a list, then calling `exporter.export(batch)` directly) rather than relying on OTel's `BatchSpanProcessor` for batching.

**Alternative — `BatchSpanProcessor` with explicit `force_flush()` before return**:

If `BatchSpanProcessor` is preferred for its batching, it can work if the handler explicitly calls `force_flush()` before returning. `force_flush()` is a **blocking, synchronous** call that drains the queue on the calling thread (not the daemon thread):

```python
# From BatchProcessor.force_flush() in opentelemetry-sdk
def force_flush(self, timeout_millis: Optional[int] = None) -> bool:
    if self._shutdown:
        return False
    self._export(BatchExportStrategy.EXPORT_ALL)  # <-- blocking, runs on caller's thread
    return True
```

However, this approach is fragile: if the handler crashes or an exception is not caught before `force_flush()` is called, buffered spans are lost. `SimpleSpanProcessor` is the recommended default for stored procedure environments.

#### 2. Creating processes is not allowed

[Python stored procedure limitations](https://docs.snowflake.com/en/developer-guide/stored-procedure/python/procedure-python-limitations): **"Creating processes is not supported in stored procedures."** This prohibits `subprocess`, `multiprocessing`, and `os.fork()`. Our app does not use any of these — all work is done via `threading` (allowed) and synchronous gRPC/HTTP calls.

#### 3. Concurrent queries — constrained by default, mitigated by task graph architecture

[Python stored procedure limitations](https://docs.snowflake.com/en/developer-guide/stored-procedure/python/procedure-python-limitations): **"Running concurrent queries is not supported in stored procedures."** By default, a single stored procedure cannot issue multiple Snowpark queries in parallel.

**Nuances discovered through research:**

- **Thread-safe sessions** (Snowpark >= 1.24) can override this limitation when the account-level flag `FEATURE_THREAD_SAFE_PYTHON_SESSION` is enabled. The Snowpark server-side [releases the GIL before submitting queries](https://medium.com/snowflake/snowpark-python-supports-thread-safe-session-objects-d66043f36115), enabling true concurrency from multiple threads. However, we **cannot rely on this** because we cannot guarantee the flag is enabled in consumer accounts.

- **Async jobs** (`DataFrame.collect_nowait()`) can submit queries non-blocking, but [fire-and-forget is not supported](https://docs.snowflake.com/en/developer-guide/stored-procedure/python/procedure-python-writing) — child queries are canceled when the handler returns. Additionally, async jobs ["do not allow multiple queries to be submitted at the same time"](https://medium.com/snowflake/snowpark-python-supports-thread-safe-session-objects-d66043f36115) — they are non-blocking but still serialized.

**Our mitigation — task graph parallelism (Section 7.6):**

Instead of trying to parallelize within a single stored procedure, we use a [task graph](https://docs.snowflake.com/en/user-guide/tasks-graphs) where each ACCOUNT_USAGE source runs as an independent child task. Child tasks of the same parent [run in parallel](https://docs.snowflake.com/en/user-guide/tasks-graphs), each with its own session — no feature flags, no shared state, no concurrent query limitations. This architecture sidesteps the stored procedure concurrency constraint entirely.

#### 4. Package availability (verified)

All required packages (`opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-grpc`, `grpcio`, etc.) are verified available on the Snowflake Anaconda Channel — see the **Python Runtime & Dependencies** section for pinned versions.

#### 5. gRPC egress requires External Access Integration

Requires EAI with network rules allowing egress to `ingest.{realm}.signalfx.com:443` over HTTP/2 (gRPC/TLS). Consumer must approve the app specification for this external connection.

#### 6. Module-level initialization for network clients (critical performance optimization)

Snowflake's [UDF/procedure design guidance](https://docs.snowflake.com/en/developer-guide/udf/python/udf-python-designing) states: **"Put expensive initialization code into the module scope. There, it will be performed once when the UDF is initialized."** The [Snowpark External Access blog](https://www.snowflake.com/en/engineering-blog/snowpark-network-access-parallel-processing/) reinforces this for network clients: global connection pools initialized at module scope avoid TCP connection creation overhead per handler invocation.

Our stored procedures must follow this pattern:
- **OTLP exporter** (`OTLPSpanExporter`, `OTLPMetricExporter`): Create at module scope. The gRPC HTTP/2 channel persists across task invocations on the same warehouse. Snowflake caches imported modules, so subsequent calls skip the ~300-500ms `protobuf + grpcio` import overhead.
- **HEC HTTP client** (`httpx.Client`): Create at module scope with connection keep-alive enabled. Reuses TCP connections across `to_pandas_batches()` chunk iterations and across repeated serverless task invocations.
- **Snowflake imposes TCP connection limits** per sandbox — never create clients per batch, per chunk, or per handler call. One `httpx.Client` and one OTLP exporter instance per stored procedure module is sufficient.

See Section 7.12 (BP-2 and BP-3) for the full best practice checklist.

---

## Snowflake Native App Workflow

This section consolidates the end-to-end Snowflake Native App Framework decisions for our app — from package structure through development, testing, versioning, publishing, and upgrade maintenance. It complements the detailed publishing checklist in the next section ("Snowflake Marketplace Publishing Compliance") and maps each framework concept to a concrete decision for this app.

**References:**
- [About the Snowflake Native App Framework](https://docs.snowflake.com/en/developer-guide/native-apps/native-apps-about)
- [Create and manage an application package](https://docs.snowflake.com/en/developer-guide/native-apps/creating-app-package)
- [Create the manifest file](https://docs.snowflake.com/en/developer-guide/native-apps/manifest-overview)
- [Manifest file reference](https://docs.snowflake.com/en/developer-guide/native-apps/manifest-reference)
- [Create the setup script](https://docs.snowflake.com/en/developer-guide/native-apps/creating-setup-script)
- [Install and test an app locally](https://docs.snowflake.com/en/developer-guide/native-apps/installing-testing-application)
- [Use versioned schemas](https://docs.snowflake.com/en/developer-guide/native-apps/versioned-schema)
- [Publish an app using release channels](https://docs.snowflake.com/en/developer-guide/native-apps/release-channels)
- [Security requirements and guidelines](https://docs.snowflake.com/en/developer-guide/native-apps/security-overview)
- [Tutorial 1: Create a basic Snowflake Native App](https://docs.snowflake.com/en/developer-guide/native-apps/tutorials/getting-started-tutorial)
- [Snowflake CLI — Native Apps overview](https://docs.snowflake.com/en/developer-guide/snowflake-cli/native-apps/overview)
- [Guidelines and requirements for listing Apps on Marketplace](https://docs.snowflake.com/en/collaboration/guidelines-reqs-for-listing-apps)
- [Run the automated security scan](https://docs.snowflake.com/en/developer-guide/native-apps/security-run-scan)
- [3 Tips to Speed Up Native App Development (Jim Pan, Snowflake Blog)](https://medium.com/snowflake/3-tips-to-speed-up-your-snowflake-native-app-development-and-deployment-processes-41211afcb2c7)

### Step-by-Step Guide: Getting Started with App Development

This subsection walks through the essential steps to bootstrap and iteratively develop the Splunk Observability Native App using Snowflake CLI and the Snowflake Native App Framework. It follows the workflow described in [Tutorial 1: Create a basic Snowflake Native App](https://docs.snowflake.com/en/developer-guide/native-apps/tutorials/getting-started-tutorial). Steps 1–7 target the **dev package** (`splunk_observability_dev_pkg`) for fast local iteration. Step 8 covers the promotion pipeline through the [Multi-Package Strategy](#multi-package-strategy-for-development-testing--publishing) (scan → test → prod → publish).

#### Step 1: Install and configure Snowflake CLI

Install [Snowflake CLI](https://docs.snowflake.com/en/developer-guide/snowflake-cli/index) (v3.0.0+) and create a named connection for development:

```bash
# Install Snowflake CLI (if not installed)
pip install snowflake-cli

# Create a named connection for development (if not created)
snow connection add
# → Name: dev (check if exists before adding)
# → Role: <your_dev_role>  (must have CREATE APPLICATION PACKAGE and CREATE APPLICATION privileges)
# → Warehouse: <your_dev_warehouse>

# Verify the connection
snow connection test -c dev
```

**Required privileges** for the development role:
```sql
GRANT CREATE APPLICATION PACKAGE ON ACCOUNT TO ROLE <dev_role>;
GRANT CREATE APPLICATION ON ACCOUNT TO ROLE <dev_role>;
```

#### Step 2: Initialize the project from a template

Use `snow init` to scaffold the project directory with the standard Snowflake Native App structure:

```bash
# Initialize from the app_basic template
snow init --template app_basic splunk-observability-native-app

# Other available templates (run `snow init --help` for full list):
#   app_basic          — minimal Native App skeleton
#   app_streamlit      — Native App with Streamlit UI
#   app_python         — Native App with Python UDFs/procedures
```

This creates a `splunk-observability-native-app/` directory with:
- `snowflake.yml` — project definition file (at project root)
- `app/manifest.yml` — app manifest
- `app/setup_script.sql` — setup script stub
- `app/README.md` — consumer-facing readme

> **Note:** `snowflake.yml` must exist at the project root. All paths in the manifest and project definition are relative to their respective files.

#### Step 3: Customize the project definition (`snowflake.yml`)

Replace the generated `snowflake.yml` with our project-specific configuration (see the [Project Definition File](#project-definition-file-snowflakeyml) section below for the full skeleton). The project definition targets the **dev package** for local iterative development (see [Multi-Package Strategy](#multi-package-strategy-for-development-testing--publishing) for the full package topology). Key settings:
- **`identifier`**: `splunk_observability_dev_pkg` / `splunk_observability_dev_app` (dev package — `DISTRIBUTION=INTERNAL`, no security scan overhead)
- **`stage`**: `stage_content.app_stage`
- **`manifest`**: `app/manifest.yml`
- **`artifacts`**: map `app/*`, `python/`, and `streamlit/` to the stage
- **`meta.post_deploy`**: SQL scripts for shared data setup
- **`debug: true`**: enables debug mode for internal object inspection during development

#### Step 4: Create the manifest file (`manifest.yml`)

Replace the generated `app/manifest.yml` with our full manifest configuration (see the [Manifest File](#manifest-file-manifestyml) section below). The manifest declares:
- `manifest_version: 2` for automated privilege granting
- `artifacts` block with setup script, readme, default Streamlit app, and extension code
- `configuration` block with logging, tracing, and metrics levels
- `privileges` block with all account-level privileges the app needs
- `references` block with all consumer objects the app needs bound (Event Table, Secrets, EAI)

#### Step 5: Write the setup script (`setup.sql`)

Create `app/setup.sql` with all DDL for the app's schemas, stored procedures, tasks, grants, and Streamlit objects. The setup script runs on install and upgrade. Key patterns:
- Use `CREATE OR ALTER VERSIONED SCHEMA` for stateless objects (procedures, UDFs, Streamlit)
- Use `CREATE SCHEMA IF NOT EXISTS` + `CREATE TABLE IF NOT EXISTS` for stateful objects (config, watermarks)
- Create application roles and grant privileges to them
- Use `EXECUTE IMMEDIATE FROM` for modular script organization (optional)

```sql
-- Example: minimal setup.sql structure
CREATE APPLICATION ROLE IF NOT EXISTS app_admin;

CREATE OR ALTER VERSIONED SCHEMA app_public;
GRANT USAGE ON SCHEMA app_public TO APPLICATION ROLE app_admin;

CREATE SCHEMA IF NOT EXISTS _internal;
-- ... stateful tables, tasks, procedures, grants ...
```

#### Step 6: Add application logic and Streamlit UI

- Place Python handler modules under `app/python/` (referenced via `IMPORTS` in stored procedure DDL)
- Place Streamlit files under `app/streamlit/` (referenced by `default_streamlit` in manifest)
- Add `app/environment.yml` with pinned Python dependencies from the Snowflake Anaconda Channel

#### Step 7: Deploy and test locally (iterative development loop)

Use Snowflake CLI for rapid iteration against the **dev package** (`splunk_observability_dev_pkg`) without creating formal versions or triggering security scans:

```bash
# Deploy files to stage + create/upgrade the dev app in one command
snow app run -c dev

# This command:
# 1. Creates the dev application package splunk_observability_dev_pkg (if it doesn't exist)
# 2. Creates the named stage and uploads all artifacts
# 3. Runs post-deploy scripts (shared_content.sql)
# 4. Creates or upgrades the dev application object splunk_observability_dev_app from staged files
# 5. Outputs a Snowsight URL to view the app

# Test procedures via CLI
snow sql -q "CALL splunk_observability_dev_app.app_public.hello()" -c dev

# Open the Streamlit UI in the browser
snow app open -c dev
```

**Debug mode** is enabled by default (`debug: true` in `snowflake.yml`). To inspect internal objects:
```sql
-- debug: true in snowflake.yml automatically sets DEBUG_MODE = TRUE
-- All internal schemas, tables, task states, and procedure outputs are now visible.
-- Or explicitly: ALTER APPLICATION splunk_observability_dev_app SET DEBUG_MODE = TRUE;
```

**Power-user tip: Direct DDL with DEBUG_MODE** ([Jim Pan's Tip 1](https://medium.com/snowflake/3-tips-to-speed-up-your-snowflake-native-app-development-and-deployment-processes-41211afcb2c7))

For rapid SQL prototyping (e.g., iterating on a new stored procedure or UDF), you can skip the full upload cycle entirely. With `DEBUG_MODE = TRUE`, you can run DDL statements directly against the application object — creating schemas, tables, procedures, and UDFs in real-time, with **immediate SQL syntax validation**:

```sql
USE APPLICATION splunk_observability_dev_app;

-- Iterate on procedure logic directly — syntax errors caught immediately
CREATE OR REPLACE PROCEDURE app_public.my_new_procedure()
  RETURNS STRING
  LANGUAGE SQL
  AS 'BEGIN RETURN ''Hello''; END;';

-- Test immediately
CALL app_public.my_new_procedure();
```

This avoids the upload → stage → create cycle for each code change. Once satisfied, incorporate the tested DDL into `setup.sql` and resume the normal `snow app run` workflow. This approach is particularly valuable for:
- Prototyping complex SQL logic before committing it to the setup script
- Debugging permission issues by testing grants interactively
- Rapid experimentation with UDF implementations

> **Caution:** Changes made directly via DDL are not persisted in your local files. Always back-port working code into `setup.sql` and the Python handler files before moving on.

#### Step 8: Promote through the multi-package pipeline (scan → test → prod → publish)

Once the app is stable in the dev environment (Step 7), the path to production follows the [Multi-Package Strategy](#multi-package-strategy-for-development-testing--publishing). Each stage uses a dedicated application package to isolate concerns and avoid security scan delays blocking development.

**8a. Pre-validate security scan (`splunk_observability_scan_pkg`)**

Before touching the production package, create a version on the dedicated scan-testing package (`DISTRIBUTION=EXTERNAL`) to catch CVEs and policy violations early:

```bash
# Upload code to the scan-testing package and add a version
snow app version create V1_0 --package splunk_observability_scan_pkg -c prod-connection

# Set DISTRIBUTION=EXTERNAL to trigger the automated security scan
snow sql -q "ALTER APPLICATION PACKAGE splunk_observability_scan_pkg SET DISTRIBUTION = EXTERNAL;" -c prod-connection

# Monitor scan status (NOT_REVIEWED → IN_PROGRESS → APPROVED / REJECTED)
snow sql -q "SHOW VERSIONS IN APPLICATION PACKAGE splunk_observability_scan_pkg;" -c prod-connection
```

**Security scan statuses** ([docs](https://docs.snowflake.com/en/developer-guide/native-apps/security-run-scan#view-the-status-of-the-security-scan)):
| Status | Meaning | Action |
|---|---|---|
| `NOT_REVIEWED` | Scan has not been initiated | Set `DISTRIBUTION = EXTERNAL` or add a version while it's already EXTERNAL |
| `IN_PROGRESS` | Scan is running | Wait (can take minutes to hours) |
| `APPROVED` | Scan passed | Proceed to next step |
| `REJECTED` | Scan failed | Fix issues and resubmit, or [appeal](https://docs.snowflake.com/en/developer-guide/native-apps/security-appeal) via severity 4 support ticket |

**8b. E2E integration test (`splunk_observability_test_pkg`)**

Create a version on the test package (`DISTRIBUTION=INTERNAL`) and install via internal listing in the E2E Test Account. This validates cross-account install, privilege binding, and full data flow without waiting for security scan:

```bash
# Create version on the test package (INTERNAL — no scan delay)
snow app version create V1_0 --package splunk_observability_test_pkg -c prod-connection

# Install in E2E Test Account via internal listing
# (Consumer installs from the private listing shared to the E2E Test Account)
# Validate: Streamlit UI, privilege binding, pipeline execution, data export to Splunk
```

**8c. Create version on production package (`splunk_observability_prod_pkg`)**

Only after scan approval (8a) and E2E validation (8b):

```bash
# Create version V1_0 from the current staged files on the production package
snow app version create V1_0 --package splunk_observability_prod_pkg -c prod-connection

# Set DISTRIBUTION=EXTERNAL (triggers security scan on the 10 most recent versions)
snow sql -q "ALTER APPLICATION PACKAGE splunk_observability_prod_pkg SET DISTRIBUTION = EXTERNAL;" -c prod-connection

# Monitor until APPROVED (should pass quickly since 8a already validated)
snow sql -q "SHOW VERSIONS IN APPLICATION PACKAGE splunk_observability_prod_pkg;" -c prod-connection

# Verify
snow app version list --package splunk_observability_prod_pkg -c prod-connection
```

**8d. Publish via release channel**

```bash
# Attach version to the DEFAULT release channel
snow app release-channel add-version --version V1_0 default -c prod-connection

# Set the release directive
snow app publish --version V1_0 --patch 0 --channel DEFAULT -c prod-connection
```

**8e. Marketplace listing pre-flight checklist**

Before submitting to Snowflake Marketplace, verify compliance with the [enforced standards](https://docs.snowflake.com/en/collaboration/guidelines-reqs-for-listing-apps#enforced-standards):

- [ ] **Immediate utility**: App is operational after install; Streamlit UI guides setup; README documents all consumer steps.
- [ ] **Standalone**: Core experience on Snowflake; no pass-through to external services for core functionality.
- [ ] **Data-centric**: App leverages Snowflake data (ACCOUNT_USAGE views, Event Tables).
- [ ] **Transparent & secure**: All privileges and references in `manifest.yml`; all resources in `marketplace.yml`; privileges requested via Python Permission SDK.
- [ ] **README**: Describes app functionality, consumer setup steps, stored procedures/UDFs, required privileges, and example SQL as code blocks.
- [ ] **Security scan**: Status is `APPROVED` for the version being published.
- [ ] **No typos**: Review listing text, README, and Streamlit UI for errors.

See the [Snowflake Marketplace Publishing Compliance](#snowflake-marketplace-publishing-compliance) section for the full binding checklist.

#### Step 9: View and test in Snowsight

1. Sign in to Snowsight and switch to the development role.
2. Navigate to **Catalog > Apps** and select `splunk_observability_dev_app`.
3. The **About** tab shows the `README.md` content.
4. Click the Streamlit tab to interact with the UI.
5. Open a worksheet to run SQL tests against the installed dev app:
   ```sql
   USE APPLICATION splunk_observability_dev_app;
   -- Test procedures, views, and pipeline execution
   ```

> **Important:** Do **not** add versions or set `DISTRIBUTION=EXTERNAL` during active development. This avoids unnecessary security scan triggers and keeps the feedback loop fast ([best practice](https://docs.snowflake.com/en/collaboration/guidelines-reqs-for-listing-apps#best-practices-when-publishing-a-snowflake-native-app)).

### Application Package Structure

The application package is the distributable container that encapsulates all data content, application logic, and metadata for the app.

**Our package layout (named stage):**

```
@<app_package>.stage/
├── manifest.yml              # manifest_version: 2 — declares privileges, references, event definitions, default Streamlit
├── marketplace.yml           # resource requirements for Snowsight consumer readiness check
├── setup.sql                 # primary setup script (may delegate via EXECUTE IMMEDIATE FROM)
├── README.md                 # consumer-facing documentation
├── environment.yml           # Python dependencies (Anaconda channel packages)
├── streamlit/                # Streamlit UI files
│   └── main.py
│   └── pages/
│       └── ...
└── python/                   # Python handler modules for stored procedures
    ├── event_table_collector.py
    ├── account_usage_source_collector.py
    ├── otlp_export.py
    ├── hec_export.py
    ├── volume_estimator.py
    └── pipeline_health_recorder.py
```

**Key decisions:**
- **`manifest_version: 2`** — enables automated privilege granting. Consumer sees requested privileges at install time; the app receives them automatically without explicit `GRANT` by the consumer ([docs](https://docs.snowflake.com/en/developer-guide/native-apps/manifest-overview#version-1-and-version-2-of-the-manifest-file)).
- **Modular setup script** — the primary `setup.sql` may use `EXECUTE IMMEDIATE FROM` to call secondary scripts for schemas, procedures, tasks, and grants, keeping each file focused and maintainable ([docs](https://docs.snowflake.com/en/developer-guide/native-apps/creating-setup-script#create-modular-setup-scripts)).
- **Staged Python handlers** — all procedure logic in separate `.py` files under `/python/`, referenced via `IMPORTS` clause. No in-line `AS $$ ... $$` code blocks ([handler organization docs](https://docs.snowflake.com/en/developer-guide/inline-or-staged)).
- **`environment.yml`** pinned to exact versions from the Snowflake Anaconda Channel for reproducible builds.

#### Manifest File (`manifest.yml`)

The manifest file is the core metadata descriptor required by the Snowflake Native App Framework. It must be named `manifest.yml` and reside at the root of the named stage. All paths (setup script, readme, Streamlit files) are relative to this file. Full reference: [Manifest file reference](https://docs.snowflake.com/en/developer-guide/native-apps/manifest-reference).

**Our `manifest.yml` skeleton:**

```yaml
# ─────────────────────────────────────────────────────────────────
# manifest.yml — Splunk Observability Native App
# Reference: https://docs.snowflake.com/en/developer-guide/native-apps/manifest-reference
# ─────────────────────────────────────────────────────────────────

# --- Required: manifest file format version ---
# Version 2 enables automated privilege granting — Snowflake grants declared
# privileges to the app automatically at install time without consumer SQL.
manifest_version: 2

# --- Optional: app version metadata ---
version:
  name: V1_0
  label: "Splunk Observability for Snowflake — MVP"
  comment: "Initial release: Event Table telemetry + ACCOUNT_USAGE metrics export to Splunk via OTLP/HEC"

# --- Required: artifacts block ---
artifacts:
  # Path to the SQL setup script run on install/upgrade (relative to manifest.yml)
  setup_script: setup.sql
  # Consumer-facing README displayed in Snowsight
  readme: README.md
  # Default Streamlit app shown to consumers (schema-qualified name created in setup.sql)
  default_streamlit: app_public.main
  # Enable Python/Java/Scala extension code in stored procedures and UDFs
  extension_code: true

# --- Optional: configuration block ---
configuration:
  log_level: INFO
  trace_level: ALWAYS
  metric_level: ALL

# --- Required for our app: privileges block ---
# These are account-level privileges the app requests from the consumer.
# With manifest_version: 2, they are granted automatically at install time.
privileges:
  - IMPORTED PRIVILEGES ON SNOWFLAKE DB:
      description: "Required to read ACCOUNT_USAGE views for cost, performance, and security monitoring"
  - EXECUTE TASK:
      description: "Required for the app's task owner role to run scheduled and triggered tasks"
  - EXECUTE MANAGED TASK:
      description: "Required to provision serverless compute resources for tasks (no consumer warehouse needed)"
  - CREATE DATABASE:
      description: "Required to create internal state database for watermarks and configuration"
  - CREATE EXTERNAL ACCESS INTEGRATION:
      description: "Required to create EAI for egress to Splunk endpoints (OTLP gRPC and HEC HTTP)"

# --- Required for our app: references block ---
# References are consumer-side objects the app needs bound at install or post-install.
references:
  - CONSUMER_EVENT_TABLE:
      label: "Event Table"
      description: "Consumer's Event Table (e.g. SNOWFLAKE.TELEMETRY.EVENTS or custom) for reading telemetry data"
      privileges:
        - SELECT
      object_type: TABLE
      multi_valued: false
      register_callback: app_public.register_single_callback
      required_at_setup: true

  - SPLUNK_OTLP_SECRET:
      label: "Splunk OTLP Token Secret"
      description: "Snowflake Secret storing the Splunk Observability access token for OTLP export"
      privileges:
        - USAGE
      object_type: SECRET
      register_callback: app_public.register_single_callback
      configuration_callback: app_public.get_secret_configuration
      required_at_setup: false

  - SPLUNK_HEC_SECRET:
      label: "Splunk HEC Token Secret"
      description: "Snowflake Secret storing the Splunk HEC token for metrics/logs export"
      privileges:
        - USAGE
      object_type: SECRET
      register_callback: app_public.register_single_callback
      configuration_callback: app_public.get_secret_configuration
      required_at_setup: false

  - SPLUNK_EAI:
      label: "Splunk External Access Integration"
      description: "EAI allowing egress traffic from the app to Splunk endpoints (OTLP gRPC + HEC HTTPS)"
      privileges:
        - USAGE
      object_type: EXTERNAL_ACCESS_INTEGRATION
      register_callback: app_public.register_single_callback
      configuration_callback: app_public.get_eai_configuration
      required_at_setup: false
```

**Manifest field summary:**

| Field | Required | Our Value | Purpose |
|---|---|---|---|
| `manifest_version` | Yes | `2` | Enables automated privilege granting; consumer sees requested privileges at install |
| `version.name` | No | `V1_0` | Version label (overridable via `ALTER APPLICATION PACKAGE`) |
| `version.label` | No | Display string | Shown to consumers in Snowsight |
| `artifacts.setup_script` | Yes | `setup.sql` | SQL script executed on install/upgrade |
| `artifacts.readme` | No (recommended) | `README.md` | Displayed in Snowsight app detail page |
| `artifacts.default_streamlit` | Conditional | `app_public.main` | Required if app includes a Streamlit UI |
| `artifacts.extension_code` | No | `true` | Required for Python/Java/Scala stored procedures and UDFs |
| `configuration.log_level` | No | `INFO` | Controls log capture level for provider diagnostics |
| `configuration.trace_level` | No | `ALWAYS` | Captures query and procedure traces |
| `configuration.metric_level` | No | `ALL` | Emits auto-instrumented resource metrics |
| `privileges` | Conditional | 5 privileges | Account-level privileges requested from consumer |
| `references` | Conditional | 4 references | Consumer objects the app needs bound (Event Table, Secrets, EAI) |

#### Project Definition File (`snowflake.yml`)

Snowflake CLI uses a project definition file named `snowflake.yml` at the root of the local project to describe deployable objects. This file controls the application package name, stage location, artifact mappings, and application entity. All paths (manifest, setup script, app files) are relative to this file. See: [Project definition reference](https://docs.snowflake.com/en/developer-guide/snowflake-cli/native-apps/project-definitions).

**Our `snowflake.yml` skeleton:**

```yaml
# ─────────────────────────────────────────────────────────────────
# snowflake.yml — Snowflake CLI project definition
# Must be at the project root. All paths are relative to this file.
#
# This file defines the DEV package and app for local iterative development.
# For the full multi-package strategy (dev → scan → test → prod), see the
# "Multi-Package Strategy for Development, Testing & Publishing" section.
# ─────────────────────────────────────────────────────────────────

definition_version: 2

entities:
  # --- Application Package (dev — per-developer iterative development) ---
  # Uses DISTRIBUTION=INTERNAL (default) — no security scan overhead.
  # See Multi-Package Strategy for scan/test/prod packages.
  splunk_observability_dev_pkg:
    type: application package
    identifier: splunk_observability_dev_pkg
    stage: stage_content.app_stage
    manifest: app/manifest.yml
    artifacts:
      - src: app/*
        dest: ./
      - python/
      - streamlit/
    meta:
      post_deploy:
        - sql_script: scripts/shared_content.sql

  # --- Application Object (dev — installs from dev package for local testing) ---
  splunk_observability_dev_app:
    type: application
    from:
      target: splunk_observability_dev_pkg
    debug: true   # Enable debug mode during development
```

**How it works:**
- `snow app run` reads `snowflake.yml`, creates the application package `splunk_observability_dev_pkg` with schema `stage_content` and stage `app_stage`, uploads all artifacts to the stage, runs post-deploy scripts, and creates/upgrades the application object `splunk_observability_dev_app`.
- The `artifacts` mapping copies `app/*` (manifest, setup script, README, environment.yml) to the stage root, plus Python handlers and Streamlit files.
- `debug: true` during development enables `DEBUG_MODE` so all internal objects are visible for inspection.
- The dev package uses `DISTRIBUTION=INTERNAL` (default) — no security scan triggers, no delays. For scan pre-validation and production release, use the dedicated packages described in the [Multi-Package Strategy](#multi-package-strategy-for-development-testing--publishing).

#### Local Project Directory Structure

The local filesystem layout contains two categories of files: (1) **staged files** that get uploaded to Snowflake via `snow app run`, and (2) **local-only files** for development tooling, testing, and project management that never leave the developer's machine.

```
snowflake-native-splunk-app/              # Project root (git repo)
│
│── ── Snowflake Native App (staged → uploaded to @<pkg>.stage_content.app_stage) ──
│
├── snowflake.yml                         # Snowflake CLI project definition (dev package)
├── app/                                  # Staged app files
│   ├── manifest.yml                      # App manifest (manifest_version: 2)
│   ├── setup.sql                         # Primary setup script (DDL: schemas, procs, tasks, grants)
│   ├── README.md                         # Consumer-facing documentation (shown in Snowsight)
│   ├── environment.yml                   # Runtime Python deps (Snowflake Anaconda channel, pinned)
│   ├── pyproject.toml                    # LOCAL ONLY — Streamlit 3.11 preview runner (not staged)
│   ├── .venv/                            # LOCAL ONLY — Python 3.11 venv for `streamlit run` (not staged)
│   ├── streamlit/                        # Streamlit UI files (Python 3.11 at runtime in SiS)
│   │   ├── main.py
│   │   └── pages/
│   │       └── ...
│   └── python/                           # Python handler modules (Python 3.13 at runtime in procs)
│       ├── event_table_collector.py
│       ├── account_usage_source_collector.py
│       ├── otlp_export.py
│       ├── hec_export.py
│       ├── volume_estimator.py
│       └── pipeline_health_recorder.py
├── scripts/                              # Post-deploy SQL hooks (run by snow app run, not staged)
│   └── shared_content.sql                # Shared data setup run via post_deploy
├── marketplace.yml                       # Resource requirements for Marketplace readiness check
│
│── ── Local Development Only (never uploaded to Snowflake) ──────────────────────
│
├── .venv/                                # Primary dev venv (uv-managed, Python 3.13)
│                                         #   - ALL code: backend + Streamlit (IDE, linting, tests)
│                                         #   - Mirrors runtime deps for autocompletion
├── pyproject.toml                        # Local dev dependency spec (managed by uv)
├── uv.lock                              # Locked dev dependencies (deterministic installs)
├── .env                                  # Local env vars: PRIVATE_KEY_PASSPHRASE, connection config
├── .env.example                          # Template for .env (committed, no real secrets)
├── .gitignore                            # Git exclusions (.venv, .env, __pycache__, etc.)
├── LICENSE                               # Project license
├── tests/                                # Local test suite (unit tests, integration stubs)
│   └── ...
│
│── ── Planning & Documentation (local tooling) ─────────────────────────────────
│
├── _bmad/                                # BMAD framework config (planning tooling)
└── _bmad-output/                         # BMAD outputs (vision, architecture, stories)
    └── planning-artifacts/
        └── splunk_snowflake_native_app_vision.md
```

**Key distinctions:**
- **`app/environment.yml`** (Conda format) — runtime dependencies resolved by Snowflake's Anaconda channel. Pinned to exact versions. This is what runs inside Snowflake. Covers both stored procedures (Python 3.13) and Streamlit (Python 3.11).
- **`pyproject.toml`** (root) + **`uv.lock`** — primary local dev dependencies managed by `uv` (Python 3.13). Mirrors runtime packages for IDE autocompletion + adds linters (`ruff`), type checkers (`mypy`/`pyright`), test frameworks (`pytest`). These never leave the developer's machine.
- **`app/pyproject.toml`** + **`app/uv.lock`** — lightweight Streamlit preview runner managed by `uv` (Python 3.11). Contains only `streamlit` + `plotly`. Not staged to Snowflake.
- **`.venv/`** — primary dev venv (Python 3.13). Created with `uv sync` at root. Used for ALL code development, linting, testing, IDE autocompletion. Never committed.
- **`app/.venv/`** — Streamlit preview runner (Python 3.11). Created with `cd app && uv sync`. Used only for `uv run streamlit run streamlit/main.py` to visually test UI layouts locally with mock data. Never committed.
- **`.env`** — Snowflake connection secrets (`PRIVATE_KEY_PASSPHRASE`). Never committed. Use `.env.example` with placeholder values as documentation.

### Schema Strategy: Versioned vs. Stateful

The app uses two categories of schemas following [Snowflake's versioned schema guidance](https://docs.snowflake.com/en/developer-guide/native-apps/versioned-schema):

**Versioned schema** (`CREATE OR ALTER VERSIONED SCHEMA`) — for stateless objects that are recreated on each version/upgrade:
- Stored procedures (all collectors, estimator, health recorder)
- Streamlit app reference
- UDFs (if any)

Versioned schemas provide **version pinning**: if a long-running task is mid-execution during an upgrade, its queries remain pinned to the old version until completion. This is critical for our pipeline tasks which may take minutes to process large batches.

**Regular schemas** (`CREATE SCHEMA IF NOT EXISTS`) — for stateful objects that persist across versions:
- `_internal` — configuration tables (`config`, `watermarks`), state that must survive upgrades
- `_staging` — zero-copy staging tables (post-MVP)
- `_metrics` — pipeline health metrics history

**Setup script pattern for stateful tables:**
```sql
-- Stateful: preserve existing data, add new columns on upgrade
CREATE SCHEMA IF NOT EXISTS _internal;
CREATE TABLE IF NOT EXISTS _internal.config (
  key STRING, value STRING, updated_at TIMESTAMP
);
ALTER TABLE _internal.config ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
```

**Restrictions relevant to our app:** Tasks cannot be created in versioned schemas — they must live in regular schemas. Application roles must also be in regular schemas. Both are handled by placing them in `_internal`.

### Application Roles

Application roles control consumer access to app objects. They are defined in the setup script, automatically granted to the installing role, and can be further delegated by the consumer.

**Our app defines a single role:**
- **`APP_ADMIN`** — full access: configure Splunk connections, manage monitoring packs, start/stop pipelines, view health dashboards. Granted `USAGE` on all app procedures and the Streamlit UI.

A single role keeps the permission model simple and avoids unnecessary complexity for MVP. The consumer who installs the app receives `APP_ADMIN` automatically and can delegate it to other roles in their account as needed. A read-only `APP_VIEWER` role can be introduced post-MVP if consumers request fine-grained access separation.

**Key constraint:** Application roles cannot own objects and cannot be created in versioned schemas. They are created in the setup script at the top level, outside any schema.

### Development Workflow

**Tooling:** [Snowflake CLI](https://docs.snowflake.com/en/developer-guide/snowflake-cli/native-apps/overview) (`snow app run`, `snow app deploy`) for iterative local development. The CLI creates the application package, uploads files to a named stage, and creates or upgrades the app — all in a single command, without adding formal versions or triggering security scans.

**Iterative development cycle:**
1. Edit Python handlers, Streamlit files, or `setup.sql` locally.
2. Run `snow app deploy` to sync files to the named stage.
3. Run `snow app run` to create/upgrade the app from staged files (development mode).
4. Test in Snowsight — verify Streamlit UI, trigger pipelines, inspect data flow.
5. Use **debug mode** (`ALTER APPLICATION ... SET DEBUG_MODE = TRUE`) to inspect all internal objects (tables, task states, procedure outputs) that are normally invisible to consumers.
6. Use **session debug mode** (`SYSTEM$BEGIN_DEBUG_APPLICATION(...)`) for deeper testing with `AS_APPLICATION` or `AS_SETUP_SCRIPT` privilege context — validates that procedures have the correct grants.
7. Repeat from step 1.

**Important:** Do **not** add versions or set `DISTRIBUTION=EXTERNAL` during active development. This avoids unnecessary security scan triggers and keeps the feedback loop fast ([best practice](https://docs.snowflake.com/en/collaboration/guidelines-reqs-for-listing-apps#best-practices-when-publishing-a-snowflake-native-app)).

### Testing Strategy

**Single-account testing:** The Snowflake Native App Framework allows testing within the same account as the application package — no separate consumer account needed during development.

| Testing Phase | Method | What It Validates |
|---|---|---|
| **Setup script correctness** | `snow app run` (staged files) | Schema creation, procedure DDL, task DDL, grant statements, idempotency |
| **Consumer perspective** | Development mode (default) | Only objects granted to application roles are visible — matches real consumer experience |
| **Internal object inspection** | Debug mode | All schemas, tables, task states, procedure outputs visible — validates hidden state |
| **Privilege correctness** | Session debug mode (`AS_APPLICATION`) | Verifies procedures can access internal tables, ACCOUNT_USAGE views, EAI, and Secrets with the exact privilege set they'll have in production |
| **Upgrade safety** | `ALTER APPLICATION ... UPGRADE USING @stage` | Validates that stateful tables survive upgrade, new columns added, versioned objects replaced cleanly |
| **Event sharing** | Development mode + `AUTHORIZE_TELEMETRY_EVENT_SHARING = TRUE` | Validates that event definitions emit to local event table, simulating provider telemetry |
| **End-to-end pipeline** | Full install + Streamlit configuration + pipeline execution | Validates complete data flow: Event Table → OTLP export, ACCOUNT_USAGE → HEC export |

**Setup script idempotency** is critical: the script may run multiple times during install or upgrade, especially on failure retry. All `CREATE` statements use `CREATE OR REPLACE` (for versioned objects) or `CREATE IF NOT EXISTS` (for stateful objects). `GRANT` statements are re-applied after `CREATE OR REPLACE` since replacement implicitly revokes prior grants.

### Multi-Package Strategy for Development, Testing & Publishing

A single application package is insufficient for a robust SDLC. We use **separate application packages** for distinct purposes to avoid security scan delays blocking development, prevent developer collisions, and enable pre-validation of the security scan before production release. This approach is recommended by [Jim Pan's tried-and-true development tips](https://medium.com/snowflake/3-tips-to-speed-up-your-snowflake-native-app-development-and-deployment-processes-41211afcb2c7) and aligns with the [Snowflake Marketplace best practices](https://docs.snowflake.com/en/collaboration/guidelines-reqs-for-listing-apps#best-practices-when-publishing-a-snowflake-native-app).

**Why multiple packages?** When an application package has `DISTRIBUTION = EXTERNAL`, every new version/patch automatically triggers the [automated security scan](https://docs.snowflake.com/en/developer-guide/native-apps/security-run-scan). This scan can take hours or fail unexpectedly. If you use the same package for development and production, you cannot do listing-based cross-account testing until the scan passes — blocking your CI/CD pipeline.

#### Account & Package Topology

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Provider Organization                           │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │              Listing Account (Production)                        │  │
│  │                                                                  │  │
│  │  Code DB                                                         │  │
│  │  ├── Schema_V1  ─── Stage_Main ──┐                               │  │
│  │  │                Stage_V1_1 ──┤                                  │  │
│  │  │                              ├──► App Pkg (Prod)               │  │
│  │  │                              │    DISTRIBUTION=EXTERNAL        │  │
│  │  │                              │    ├──► Listing (Customers)     │  │
│  │  │                              │    │    └──► Consumer Accounts  │  │
│  │  │                              │                                 │  │
│  │  └── Schema_V2  ─── Stage_V2_12 ┤                                │  │
│  │                      Stage_V2_13 ┘                                │  │
│  │                              ├──► App Pkg (Test)                  │  │
│  │                              │    DISTRIBUTION=INTERNAL           │  │
│  │                              │    └──► Listing (Internal)         │  │
│  │                              │         └──► E2E Test Account      │  │
│  │                              │                                    │  │
│  │                              └──► App Pkg (Scan)                  │  │
│  │                                   DISTRIBUTION=EXTERNAL           │  │
│  │                                   (security scan pre-validation)  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  ┌─────────────────────────┐  ┌──────────────────────────────┐        │
│  │     Dev Account          │  │     E2E Test Account          │       │
│  │  App Pkg ──► Test App    │  │  (installs from Internal      │       │
│  │  DISTRIBUTION=INTERNAL   │  │   listing for cross-account   │       │
│  │  (per-developer)         │  │   end-to-end testing)         │       │
│  └─────────────────────────┘  └──────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────────┘

┌────────────────────────┐    ┌────────────────────────┐
│   Consumer Account 1   │    │   Consumer Account 2   │
│   Installed App 1      │    │   Installed App 2      │
└────────────────────────┘    └────────────────────────┘
```

#### Application Package Inventory

| Package | Account | `DISTRIBUTION` | Purpose | Listing |
|---|---|---|---|---|
| **`splunk_observability_prod_pkg`** | Listing (Prod) | `EXTERNAL` | Customer-facing release. Security scan runs on each version/patch. | Marketplace (Customers) |
| **`splunk_observability_test_pkg`** | Listing (Prod) | `INTERNAL` | E2E integration testing with internal listing. No security scan delays. | Private (Internal) |
| **`splunk_observability_scan_pkg`** | Listing (Prod) or any | `EXTERNAL` | Pre-validates security scan before promoting code to prod package. Catches CVEs and scan rejections early. | None |
| **`splunk_observability_dev_pkg`** | Dev Account | `INTERNAL` | Per-developer iterative development. Fast `snow app run` loop. | None |

#### Workflow Integration

1. **Develop** in Dev Account using `splunk_observability_dev_pkg` — fast `snow app run` loop, debug mode, no scan overhead.
2. **Pre-validate security scan** by creating a version on `splunk_observability_scan_pkg` (EXTERNAL) — catches CVE and policy issues before committing to the production package.
3. **E2E test** by creating a version on `splunk_observability_test_pkg` (INTERNAL) + installing via internal listing in the E2E Test Account — validates cross-account install, privilege binding, and full data flow without waiting for security scan.
4. **Release to production** by creating a version on `splunk_observability_prod_pkg` (EXTERNAL) — scan runs, then promote to DEFAULT release channel and update Marketplace listing.

**Code DB rationale:** Separate schemas (e.g., `Schema_V1`, `Schema_V2`) with separate stages in the Code DB prevent user errors where dev-only code accidentally gets deployed to production. Each schema/stage maps to a specific version lineage. If CI/CD deploys directly from source control, a single stage per package may suffice ([Jim Pan's advice](https://medium.com/snowflake/3-tips-to-speed-up-your-snowflake-native-app-development-and-deployment-processes-41211afcb2c7)).

#### Cross-Region Considerations

If using [Cross-Cloud Auto-Fulfillment](https://other-docs.snowflake.com/en/collaboration/provider-listings-auto-fulfillment) for multi-region distribution (post-MVP):
- New version/patch is replicated to other regions on the next refresh schedule — consumers in other regions won't see the update immediately.
- Shared Data Content may lag behind — app logic must handle missing or stale data gracefully.
- Test fresh installation **and** upgrades across regions, not just same-region.
- Monitor version rollout status via the [APPLICATION_STATE view](https://docs.snowflake.com/en/sql-reference/data-sharing-usage/application-state-view).

### Versioning & Release Channels

**Release channels** (enabled by default on new application packages) manage the release lifecycle:

| Channel | Purpose | Audience | Cost |
|---|---|---|---|
| **QA** | Internal validation by provider team | Provider test accounts only | Free |
| **ALPHA** | Pre-release testing with select consumers | Explicitly added consumer accounts | Free |
| **DEFAULT** | Production release to all consumers | All consumers via listing | Per pricing plan |

**Version management workflow:**
1. **Register** a new version: `ALTER APPLICATION PACKAGE ... REGISTER VERSION V2 USING '@stage/path'` — creates the version without assigning it to any channel.
2. **Add to QA channel**: `ALTER APPLICATION PACKAGE ... MODIFY RELEASE CHANNEL QA ADD VERSION V2` — enables internal testing.
3. **Set QA release directive**: `ALTER APPLICATION PACKAGE ... MODIFY RELEASE CHANNEL QA SET DEFAULT RELEASE DIRECTIVE VERSION=V2 PATCH=0`.
4. **Test in QA** — install from QA channel, validate end-to-end.
5. **Promote to DEFAULT** — add version to DEFAULT channel and set release directive for production consumers.
6. **Deregister old version** when all consumers have upgraded.

**Patch workflow:** Patches are applied within a version (e.g., V1 PATCH 1, PATCH 2). When a version is added to a release channel, subsequent patches for that version are automatically bound to that channel.

**Constraint:** A release channel can hold at most two simultaneous versions. An application package can have at most two unassigned (not-yet-added-to-any-channel) versions at a time.

### Publishing & Distribution

Publishing is a multi-step process that transitions the app from internal-only to consumer-facing:

1. **Set `DISTRIBUTION = EXTERNAL`** on the application package — signals intent to publish outside your organization. This triggers the [automated security scan](https://docs.snowflake.com/en/developer-guide/native-apps/security-overview) (NAAAPS) on each new version/patch.
2. **Pass security scan** — NAAAPS scans code for vulnerabilities, malware, anti-patterns (data exfiltration, dynamic code execution, obfuscated code, CVEs). Auto-approved or sent to manual review (up to 5 business days). See "Security Scan Requirements" below for specifics.
3. **Create a listing** — attach the application package to a Snowflake Marketplace listing or a private listing. Configure pricing (free for MVP), description, and consumer-facing documentation.
4. **Set DEFAULT release directive** — determines which version consumers receive on install and auto-upgrade.

**For our app (MVP):**
- **Free listing** on Snowflake Marketplace.
- **Single instance** per consumer account (default; `MULTIPLE_INSTANCES` left as `FALSE`).
- `DISTRIBUTION = EXTERNAL` set only when code is stable and all security scan blockers resolved (specifically: `protobuf >= 6.33.5` for CVE-2026-0994).

### Upgrade & Maintenance

When a provider publishes a new version, installed consumer apps are **auto-upgraded** according to the release directive. The setup script re-executes during upgrade.

**Upgrade safety design for our app:**
- **Stateful objects** (config, watermarks, metrics history) use `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN IF NOT EXISTS` — survive upgrade without data loss.
- **Stateless objects** (procedures, UDFs, Streamlit) in versioned schema — cleanly replaced by new version. Version pinning ensures in-flight task executions complete against old procedure code before the old version is finalized.
- **Tasks** are in regular schemas and use `CREATE OR REPLACE TASK` — re-created with updated parameters on each upgrade. Suspended before upgrade, resumed after setup script completes.
- **Application roles** are not versioned — we never drop them, only add new ones. Privileges are re-granted after `CREATE OR REPLACE` on procedures.

**Consumer-side maintenance policies:** Consumers can configure [maintenance policies](https://docs.snowflake.com/en/developer-guide/native-apps/release-channels-upgrade) that control when auto-upgrades are applied (e.g., a specific maintenance window). Our app should be resilient to upgrades occurring at any time.

**Provider-side maintenance cadence:**
- **Quarterly** dependency audit — re-verify all packages on Snowflake Anaconda Channel, check for new CVEs.
- **Per-release** security scan validation — monitor scan status via `SHOW VERSIONS IN APPLICATION PACKAGE`.
- **Continuous** monitoring of Snowflake documentation for schema changes in ACCOUNT_USAGE views and Event Table columns that could break our queries.

### IP Protection

The Snowflake Native App Framework provides built-in intellectual property protection:
- **Owner's rights procedures** — consumers cannot call `GET_DDL()` to inspect handler source code (see Stored Procedure Architecture section).
- **Query redaction** — query text from app procedures is hidden from QUERY_HISTORY and ACCESS_HISTORY in the consumer account.
- **Staged handler code** — Python files on the app's internal stage are not directly accessible to consumers.
- **Application roles** gate all access — consumers see only objects explicitly granted to their application role.

---

## Snowflake Marketplace Publishing Compliance

This section captures the key requirements and constraints from the [Snowflake Marketplace listing guidelines](https://docs.snowflake.com/en/collaboration/guidelines-reqs-for-listing-apps) and the [Native App security requirements](https://docs.snowflake.com/en/developer-guide/native-apps/security-run-scan) that must be satisfied for successful publication. It is intended as a binding checklist for development and AI-assisted implementation.

### Enforced Standards — How This App Aligns

| Standard | Requirement | Our Compliance Strategy |
|---|---|---|
| **Immediate utility** | App must deliver advertised functionality; must not be a shell. Must include clear setup instructions. ([Guidelines](https://docs.snowflake.com/en/collaboration/guidelines-reqs-for-listing-apps)) | Streamlit UI guides full setup; pipelines activate immediately after configuration. README documents all consumer steps. |
| **Standalone** | Core product experience delivered on Snowflake; external services accessed through Snowflake features only. Apps must not be pass-through. | Pipeline management, configuration, health observability — all within Snowflake. External egress to Splunk uses Snowflake EAI + Secrets (not consumer Snowflake credentials). |
| **Data-centric** | App must leverage data stored in Snowflake. | Reads ACCOUNT_USAGE views and Event Tables — 100% Snowflake-native data sources. |
| **Transparent & secure** | All privileges and references declared in `manifest.yml`; resource requirements in `marketplace.yml`; privileges requested via Snowsight or [Python Permission SDK](https://docs.snowflake.com/en/developer-guide/native-apps/requesting-privs-permissions-sdk). | `manifest_version: 2` with all privileges; `marketplace.yml` at root; Streamlit UI uses Python Permission SDK for grants and reference binding. |

### Required Artifacts Checklist

All of the following must be present in the application package's named stage ([best practices](https://docs.snowflake.com/en/collaboration/guidelines-reqs-for-listing-apps#best-practices-when-publishing-a-snowflake-native-app)):

- **`manifest.yml`** (`manifest_version: 2`) — declares all account-level privileges (`IMPORTED PRIVILEGES ON SNOWFLAKE DB`, `EXECUTE TASK`, `EXECUTE MANAGED TASK`, `CREATE DATABASE`, `CREATE EXTERNAL ACCESS INTEGRATION`), all references (Event Table refs, EAI ref, Secret ref), `default_streamlit_app`, log/trace levels, and [event definitions](https://docs.snowflake.com/en/developer-guide/native-apps/event-sharing-about).
- **`marketplace.yml`** — declares resource requirements (connections, external endpoints) so Snowsight can validate consumer readiness before install ([docs](https://docs.snowflake.com/en/developer-guide/native-apps/creating-marketplace-yml)).
- **`setup.sql`** — setup script creating all internal schemas, procedures, tasks, and the [app specification](https://docs.snowflake.com/en/developer-guide/native-apps/requesting-external-access) for EAI host ports (consumer must approve egress to Splunk endpoints).
- **`README.md`** — required if no default Streamlit, but recommended regardless. Must describe: what the app does, consumer configuration steps, stored procedures/UDFs used, required privileges, and example SQL commands as code blocks.
- **Streamlit app files** — including `environment.yml` with `snowflake-native-apps-permission` dependency for the Python Permission SDK.
- **All Python source code** — un-obfuscated, human-readable (minified JS requires source maps). All dependencies from the [Snowflake Anaconda Channel](https://repo.anaconda.com/pkgs/snowflake/).

### Security Scan Requirements

Before setting `DISTRIBUTION = EXTERNAL`, the app must pass the [automated security scan](https://docs.snowflake.com/en/developer-guide/native-apps/security-run-scan). Key constraints:

1. **No external code loading** — all code and library dependencies must be inside the application package. No dynamic imports from outside the package.
2. **No obfuscated code** — all Python/SQL must be human-readable.
3. **No critical/high CVEs** — all dependencies must be CVE-free at Critical/High severity. As of 2026-02-11 audit: all packages clean except `protobuf<6.33.5` ([CVE-2026-0994](https://nvd.nist.gov/vuln/detail/CVE-2026-0994), HIGH — fix pending on Snowflake Anaconda Channel, tracked in [snowpark-python#4056](https://github.com/snowflakedb/snowpark-python/issues/4056)). Re-audit all dependencies before each `DISTRIBUTION=EXTERNAL` submission. Update third-party libraries at least quarterly per [Snowflake security best practices](https://docs.snowflake.com/en/developer-guide/native-apps/security-requirements-best-practices).
4. **No plaintext secrets** — tokens and credentials must use [Snowflake Secrets](https://docs.snowflake.com/en/sql-reference/sql/create-secret); never stored in config tables or code.
5. **Minimum privileges only** — request only what the app needs. All privileges and API integrations must be declared in the manifest.
6. **SQL injection prevention** — all stored procedures accepting user input must use bound parameters.

### Event Sharing for Provider Telemetry

Configure [event definitions](https://docs.snowflake.com/en/developer-guide/native-apps/event-sharing-configure) in the manifest to enable provider-side observability of the installed app:

- **Mandatory**: `SNOWFLAKE$ERRORS_AND_WARNINGS` — critical for provider to detect app failures in consumer accounts.
- **Optional** (via Python Permission SDK): `SNOWFLAKE$USAGE_LOGS`, `SNOWFLAKE$TRACES` — for deeper diagnostics when consumers opt-in.
- Keep mandatory definitions minimal to avoid rejection; add new mandatory definitions only when strictly necessary (version upgrades with new mandatory events force consumer re-approval).

### Development & Testing Workflow

1. Develop and test locally using `CREATE APPLICATION` from files on a named stage — do **not** add versions or set `DISTRIBUTION=EXTERNAL` during development ([best practice](https://docs.snowflake.com/en/collaboration/guidelines-reqs-for-listing-apps#best-practices-when-publishing-a-snowflake-native-app)).
2. Test Streamlit UI in Snowsight; verify seamless interaction between UI and Worksheets.
3. Use [Snowflake CLI](https://docs.snowflake.com/en/developer-guide/snowflake-cli/native-apps/overview) (`snow app run`, `snow app deploy`) for iterative development without triggering security scans.
4. When ready to publish: add version → set `DISTRIBUTION=EXTERNAL` → automated scan runs on the 10 most recent patches → monitor via `SHOW VERSIONS IN APPLICATION PACKAGE`.
5. If scan results in `REJECTED`, fix issues and resubmit (manual review may take up to 5 business days).

### Key Risks to Monitor

| Risk | Mitigation |
|---|---|
| `grpcio` or `opentelemetry-*` packages not on Snowflake Anaconda channel | **VERIFIED** — all packages confirmed available (OTel 1.38.0, gRPC 1.74.1). No fallback needed. Re-verify if pinning to newer versions. |
| gRPC egress blocked in some consumer environments | Document network requirements clearly; provide clear error messaging if connectivity fails. |
| Security scan rejects due to CVE in dependency | **ACTIVE**: `protobuf==6.33.0` has [CVE-2026-0994](https://nvd.nist.gov/vuln/detail/CVE-2026-0994) (HIGH). Fix is `>=6.33.5`, not yet on Snowflake channel as of 2026-02-11 but expected imminently. Pin `>=6.33.5` and re-verify before submission. Maintain quarterly audit cadence for all deps. |
| App rejected as "pass-through" because core function sends data externally | Ensure Streamlit UI, pipeline health dashboard, and configuration all deliver substantive in-Snowflake value beyond just forwarding data. |

---

## Python Runtime & Dependencies

### Python Runtime Version

The app uses **two different Python runtimes** in Snowflake due to a platform limitation:

- **Stored procedures** (`app/python/`): **Python 3.13** (latest GA). Requires `snowflake-snowpark-python >= 1.9.0` ([setup docs](https://docs.snowflake.com/en/developer-guide/snowpark/python/setup#prerequisites)). Stored procedure `RUNTIME_VERSION = '3.13'`.
- **Streamlit in Snowflake** (`app/streamlit/`): **Python 3.11** (max supported). SiS warehouse runtime only supports Python 3.9, 3.10, 3.11 ([SiS limitations](https://docs.snowflake.com/en/developer-guide/streamlit/limitations)).

Stored procedure supported GA versions: 3.9 (deprecated), 3.10, 3.11, 3.12, **3.13**. We target the latest for security patches, performance, and language features.
- Verify consumer account compatibility: `SELECT * FROM INFORMATION_SCHEMA.PACKAGES WHERE LANGUAGE = 'python';` ([CREATE PROCEDURE docs](https://docs.snowflake.com/en/sql-reference/sql/create-procedure#python)).

**Local development environments:**
- **`.venv/`** (Python 3.13) — primary development venv for ALL code (backend + Streamlit), IDE autocompletion, linting, and tests.
- **`app/.venv/`** (Python 3.11) — lightweight Streamlit preview runner for visually testing the UI locally with mock data. Contains only `streamlit` + `plotly`.

### Dependencies (`environment.yml`)

All packages must be available on the [Snowflake Anaconda Channel](https://repo.anaconda.com/pkgs/snowflake/) for warehouse runtime compatibility. Versions below are the latest available on the channel as of 2026-02-11 (verified via `information_schema.packages`). Pin exact versions in `environment.yml` to ensure reproducible builds and avoid unexpected breakage from upstream updates.

### Direct Dependencies

**Core Application Framework:**
- `streamlit==1.52.2` — Native app UI framework (latest on Snowflake Anaconda channel as of Feb 2026)
- `snowflake-snowpark-python==1.9.0` — Snowflake native data processing, stored procedure runtime, and chart data preparation
- `snowflake-native-apps-permission==0.1.9` — [Python Permission SDK](https://docs.snowflake.com/en/developer-guide/native-apps/requesting-privs-permissions-sdk) for requesting consumer privileges and binding references via Streamlit UI
- `snowflake-telemetry-python==0.6.0` — Snowflake telemetry library for [event sharing](https://docs.snowflake.com/en/developer-guide/native-apps/event-sharing-about) (provider-side observability of installed app)

**Visualization & Dashboard:**
- `plotly==6.5.0` — Interactive chart library (Bar, Line, Scatter, Heatmap, Gauge, Indicator) via `st.plotly_chart`
- Native Streamlit components used without additional packages: `st.metric`, `st.dataframe`, `st.tabs`, `st.columns`, `st.button`

**Telemetry Export (OTLP/gRPC):**
- `opentelemetry-sdk==1.38.0` — OpenTelemetry SDK for telemetry data model and processing
- `opentelemetry-exporter-otlp-proto-grpc==1.38.0` — OTLP gRPC exporter for Event Table spans/metrics → Splunk Observability Cloud
- `grpcio==1.74.1` — gRPC transport layer (explicit pin to avoid version conflicts with OTel)
- `protobuf>=6.33.5` — Protocol Buffers serialization (explicit pin to avoid version conflicts with OTel/gRPC). **CVE-2026-0994 (HIGH)**: versions `<6.33.5` have a DoS vulnerability in `json_format.ParseDict()` ([NVD](https://nvd.nist.gov/vuln/detail/CVE-2026-0994)). Fixed in `6.33.5` ([PR #25239](https://github.com/protocolbuffers/protobuf/pull/25239)). As of 2026-02-11 the Snowflake Anaconda Channel only has `6.33.0`; `6.33.5` is expected imminently ([snowpark-python#4056](https://github.com/snowflakedb/snowpark-python/issues/4056)). Re-verify and pin exact version before first `DISTRIBUTION=EXTERNAL` submission.

**HTTP Client & Retry:**
- `httpx==0.28.1` — Modern HTTP client with HTTP/2 support for Splunk HEC exports
- `tenacity==9.1.2` — Unified retry logic for HEC HTTP exports with exponential backoff, jitter, and custom exception handling (OTLP/gRPC uses its own built-in retry). Also replaces the role of `httpx-retry` (not available on Snowflake Anaconda Channel).
- **Note on rate limiting**: Dedicated rate-limiting libraries (`httpx-ratelimit`, `httpx_ratelimiter`, `httpx-limiter` and their backends `aiolimiter`, `pyrate-limiter`) are **not available** on the Snowflake Anaconda Channel. The app implements a lightweight in-app token-bucket rate limiter — a standard algorithm that refills tokens at a fixed rate and blocks/delays requests when the bucket is empty. Configured at 400 req/s (80% of HEC's 500 req/s limit), it acts as a safety net. Actual HEC throughput during normal operation is ~0.01 req/s, so the limiter rarely activates.

**Zero-Copy Staging:**
- `python-xxhash==3.5.0` — Fast non-cryptographic hash (XXH3_128) for Event Table row identification in zero-copy failure tracking (computed in Python within stored procedures, not a Snowflake SQL function). **Important**: The Anaconda channel has two packages — `xxhash` (v0.8.0, lacks XXH3) and `python-xxhash` (v3.5.0, includes XXH3_128). The `environment.yml` must specify `python-xxhash`, not `xxhash`.

**Data Serialization:**
- `orjson==3.9.15` — Fast JSON serialization for ACCOUNT_USAGE data export to HEC

### Key Transitive Dependencies (auto-resolved, listed for reference)

These are pulled in automatically by the direct dependencies above. Listed here to document the verified dependency tree.

| Package | Version | Required By |
|---|---|---|
| `opentelemetry-api` | 1.38.0 | `opentelemetry-sdk` |
| `opentelemetry-proto` | 1.38.0 | `opentelemetry-exporter-otlp-proto-grpc` |
| `opentelemetry-exporter-otlp-proto-common` | 1.38.0 | `opentelemetry-exporter-otlp-proto-grpc` |
| `googleapis-common-protos` | 1.69.2 | `opentelemetry-proto`, `grpcio-status` |
| `grpcio-status` | 1.74.0 | `opentelemetry-exporter-otlp-proto-grpc` |
| `pandas` | >= 1.0.0 | `snowflake-snowpark-python` (required for `to_pandas_batches()` — core to our chunked export architecture, Section 7.11) |
| `pyarrow` | >= 8.0.0 | `snowflake-snowpark-python` (Pandas integration prerequisite; auto-installed by Snowpark, [setup docs](https://docs.snowflake.com/en/developer-guide/snowpark/python/setup#prerequisites-for-using-pandas-dataframes)) |

> **Pandas DataFrame prerequisites** ([docs](https://docs.snowflake.com/en/developer-guide/snowpark/python/setup#prerequisites-for-using-pandas-dataframes)): Our architecture relies on `DataFrame.to_pandas_batches()` for memory-bounded chunked processing (Section 7.11). This API requires `pandas >= 1.0.0` and `pyarrow >= 8.0.0`. Both are auto-resolved by `snowflake-snowpark-python` — no explicit pinning needed in `environment.yml`. Do not install a different `pyarrow` version after installing Snowpark.

## Stored Procedure Architecture

Snowflake supports [five methods for creating stored procedures](https://docs.snowflake.com/en/developer-guide/stored-procedure/stored-procedures-creating#tools-for-creating-procedures): SQL DDL, Snowpark API, Snowflake CLI, Python API, and REST API. For Native Apps, **SQL DDL** (`CREATE OR REPLACE PROCEDURE`) in the `setup.sql` script is the only applicable method — the setup script is pure SQL, and all other methods are client-side tools not available within the app packaging workflow.

**Handler code organization — staged handlers** ([keeping handler code in-line or on a stage](https://docs.snowflake.com/en/developer-guide/inline-or-staged)):
- Handler logic lives in separate Python modules (`.py` files) bundled in the app package stage.
- The `CREATE PROCEDURE` DDL references them via the `IMPORTS` clause and `HANDLER = 'module.function'` syntax.
- This is preferred over in-line handlers (`AS $$ ... $$`) for maintainability, testability, and code reuse across procedures.
- Example pattern used in `setup.sql`:
  ```sql
  CREATE OR REPLACE PROCEDURE _internal.event_table_collector()
    RETURNS VARCHAR
    LANGUAGE PYTHON
    RUNTIME_VERSION = '3.13'
    PACKAGES = ('snowflake-snowpark-python==1.9.0', 'opentelemetry-sdk==1.38.0',
                'opentelemetry-exporter-otlp-proto-grpc==1.38.0', 'grpcio==1.74.1',
                'httpx==0.28.1', 'tenacity==9.1.2', 'orjson==3.9.15')
    IMPORTS = ('/python/event_table_collector.py', '/python/otlp_export.py', '/python/hec_export.py')
    HANDLER = 'event_table_collector.main'
    EXTERNAL_ACCESS_INTEGRATIONS = (reference('splunk_eai_ref'))
    SECRETS = ('splunk_otlp_token' = reference('splunk_otlp_secret_ref'),
               'splunk_hec_token' = reference('splunk_hec_secret_ref'))
    EXECUTE AS OWNER;
  ```
- Per [setup script best practices](https://docs.snowflake.com/en/developer-guide/native-apps/creating-setup-script#best-practices-when-creating-the-setup-script): use `CREATE OR REPLACE` (idempotent for install/upgrade), always qualify with target schema.

**Procedure types and rights model** ([caller vs owner rights](https://docs.snowflake.com/en/developer-guide/stored-procedure/stored-procedures-rights)):

All app procedures are **permanent** (not `TEMP`) and use **`EXECUTE AS OWNER`** (the default):
- **Permanent**: persist across sessions and survive app upgrades. Required for task-invoked procedures. Temporary procedures are session-scoped and would not survive between task executions.
- **Owner's rights** (`EXECUTE AS OWNER`): the procedure runs with the privileges of the app (the owner), not the consumer's caller role. This is the correct choice for our app for the following reasons:
  - **IP protection**: consumers (non-owners) cannot call `GET_DDL()` on owner's rights procedures — handler source code is invisible to them.
  - **Schema context isolation**: owner's rights procedures use the database and schema the procedure was **created in** (e.g., `_internal`), not the caller's current database/schema. Our procedures always resolve unqualified table names against `_internal` / `_staging` / `_metrics` schemas automatically.
  - **Session variable isolation**: owner's rights procedures cannot read or set the caller's session variables. All configuration is stored in `_internal.config` and read explicitly — no dependency on consumer session state.
  - **Privilege delegation**: the app can read `SNOWFLAKE.ACCOUNT_USAGE` views and write to internal tables using its own grants, without exposing those privileges to the consumer role.
  - **Nested calls remain owner's rights**: if an owner's rights procedure calls another procedure, the inner procedure also behaves as owner's rights regardless of its declaration — our entire call chain is protected.
- **Owner's rights restrictions** (all acceptable for our design):
  - Cannot execute `ALTER USER` implicitly on the current user (not needed).
  - Only a [subset of session parameters](https://docs.snowflake.com/en/developer-guide/stored-procedure/stored-procedures-rights#understanding-the-effects-of-a-caller-s-session-parameters-on-an-owner-s-rights-procedure) from the caller's session are inherited (e.g., `TIMEZONE`, `TIMESTAMP_OUTPUT_FORMAT`, `QUERY_TAG`). For other parameters, the owner's account-level default is used.
  - SQL statement restrictions: DDL, DML, SELECT, GRANT/REVOKE, DESCRIBE, SHOW (with limitations) are all supported. Statements like `USE DATABASE` or `USE SCHEMA` are not needed since the procedure already operates in its creation context.
- `EXECUTE AS CALLER` is **prohibited** in Native App setup scripts ([setup script restrictions](https://docs.snowflake.com/en/developer-guide/native-apps/creating-setup-script#restrictions-on-the-setup-script)). `EXECUTE AS RESTRICTED CALLER` exists but is not applicable — our procedures need owner privileges to access internal tables.

**Procedure inventory and per-procedure configuration:**

| Procedure | Parameters | Called By | Needs EAI/Secrets | Purpose |
|---|---|---|---|---|
| `_internal.event_table_collector` | — | Triggered task (stream-driven) | Yes (OTLP + HEC) | Read Event Table streams, export spans/metrics via OTLP/gRPC, logs via HEC |
| `_internal.account_usage_source_collector` | `source_name VARCHAR` | Child tasks (task graph) | Yes (HEC) | Query one ACCOUNT_USAGE view, export via HEC |
| `_internal.volume_estimator` | — | Streamlit UI (on demand) | No | Estimate daily/monthly data volume per source |
| `_internal.pipeline_health_recorder` | — | Finalizer task (task graph) | No | Record pipeline execution metrics to `_metrics.pipeline_health` |

- Procedures that need external network access declare `EXTERNAL_ACCESS_INTEGRATIONS` and `SECRETS` in their DDL (bound at install via the reference mechanism).
- Procedures that are purely internal (no egress) omit these clauses.
- The `Session` argument is **not** declared in `CREATE PROCEDURE` parameters — Snowflake auto-injects it at runtime ([CREATE PROCEDURE docs](https://docs.snowflake.com/en/sql-reference/sql/create-procedure#required-parameters)).

**Access control requirements for procedure creation** ([docs](https://docs.snowflake.com/en/developer-guide/stored-procedure/stored-procedures-creating#access-control-requirements)):
- `CREATE PROCEDURE` privilege on the target schema — handled automatically within the Native App's own schemas (`_internal`, etc.) since the app owns them.
- `USAGE` on External Access Integrations specified in the DDL — granted by the consumer during install (via reference binding).
- `READ` on Secrets specified in the DDL — granted by the consumer during install (via reference binding).
- `USAGE` on schemas containing those secrets — granted transitively.
- After creation, the setup script grants `USAGE ON PROCEDURE` to the appropriate application role so tasks and the Streamlit UI can invoke them.

**Why not Snowpark API (`session.sproc.register()`) or other creation methods:**
- Snowflake supports [five creation methods](https://docs.snowflake.com/en/developer-guide/stored-procedure/stored-procedures-creating#tools-for-creating-procedures): SQL, Snowpark API, CLI, Python API, REST. Only SQL DDL is available in the Native App setup script context.
- The Snowpark API methods (`@sproc` decorator, `session.sproc.register()`) create stored procedures dynamically at runtime from a Python client. They support temporary and permanent procedures ([Creating Stored Procedures for DataFrames](https://docs.snowflake.com/en/developer-guide/snowpark/python/creating-sprocs)).
- For Native Apps, this approach is **not applicable**: the setup script is pure SQL, and all procedure DDL must be deterministic and idempotent. Handler code must be pre-staged, not generated at runtime.
- Snowflake CLI (`snow object create`) and Python API (`snowflake.core`) are client-side tools for managing Snowflake objects — useful for development/testing but not for packaging within a distributable app.
- We use Snowpark **within** handler code (DataFrames, `to_pandas_batches()`, `session.sql()`) but create the procedures themselves via SQL DDL.

## Tasks Architecture

This section consolidates all task-related design decisions, DDL patterns, and operational considerations for the app's two pipelines. It complements Section 7.6 (Parallel Processing via Task Graph) by providing the implementation-level details needed to build, deploy, and operate the tasks.

**References:**
- [Introduction to tasks](https://docs.snowflake.com/en/user-guide/tasks-intro)
- [Task graphs (DAGs)](https://docs.snowflake.com/en/user-guide/tasks-graphs)
- [Triggered tasks](https://docs.snowflake.com/en/user-guide/tasks-triggered)
- [CREATE TASK](https://docs.snowflake.com/en/sql-reference/sql/create-task)
- [ALTER TASK](https://docs.snowflake.com/en/sql-reference/sql/alter-task)
- [Managing tasks with Python API](https://docs.snowflake.com/en/developer-guide/snowflake-python-api/snowflake-python-managing-tasks)

### Compute Model: Serverless

All app tasks use the **serverless compute model** — the `CREATE TASK` DDL omits the `WAREHOUSE` parameter, and Snowflake automatically provisions and scales compute resources based on workload analysis ([serverless tasks docs](https://docs.snowflake.com/en/user-guide/tasks-intro#serverless-tasks)).

**Why serverless for a Native App:**
- **No consumer warehouse dependency**: the app cannot guarantee a specific warehouse exists or is appropriately sized in consumer accounts. Serverless tasks manage compute automatically.
- **Auto-tuning**: Snowflake dynamically sizes compute based on a "dynamic analysis of the most recent runs of the same task" ([docs](https://docs.snowflake.com/en/user-guide/tasks-intro#serverless-tasks)). After each task completes, Snowflake reviews performance and adjusts compute resources for future runs — tasks become more efficient over time.
- **Compute bounds**: the maximum compute for a serverless task is equivalent to an **XXLARGE warehouse**. This can be constrained via `SERVERLESS_TASK_MIN_STATEMENT_SIZE` (default: XSMALL) and `SERVERLESS_TASK_MAX_STATEMENT_SIZE` (default: XXLARGE) ([docs](https://docs.snowflake.com/en/user-guide/tasks-intro#cost-and-performance-warehouse-sizes)). For MVP, defaults are sufficient; post-MVP, constraining the max size can help control costs.
- **Schedule adherence**: for serverless scheduled tasks, "if a run of a standalone task or scheduled task graph exceeds the interval, Snowflake increases the size of the compute resources" ([docs](https://docs.snowflake.com/en/user-guide/tasks-intro#recommendations-for-choosing-a-compute-model)). This means our 30-minute ACCOUNT_USAGE schedule is self-enforcing — Snowflake scales up to keep runs within the window.
- **Per-run billing**: consumers pay only for actual compute used, measured in **compute-hours** credit usage. Serverless task credits have a multiplier vs. standard warehouse credits (see the "Serverless Feature Credit Table" in the [Snowflake Service Consumption Table](https://www.snowflake.com/legal-files/CreditConsumptionTable.pdf)). Despite the multiplier, total cost is often lower than a user-managed warehouse because there is no idle warehouse time and compute is right-sized automatically.
- **Requires `EXECUTE MANAGED TASK`**: this global privilege is declared in `manifest.yml` and granted by the consumer during install.

**Python/Java support for serverless tasks** ([docs](https://docs.snowflake.com/en/user-guide/tasks-python-jvm)): serverless tasks can invoke Python stored procedures (with Snowpark) and UDFs — this is the pattern our app uses. All task `AS` clauses use `CALL _internal.<procedure>()` which invokes the Python handlers. This has been GA since September 2024.

**Serverless cost tracking**: serverless task costs appear in `METERING_HISTORY` and `METERING_DAILY_HISTORY` views (Account Usage) with `service_type = 'SERVERLESS_TASK'` or `'SERVERLESS_TASK_FLEX'`. Per-task credit breakdown is available via `SERVERLESS_TASK_HISTORY` (both Information Schema table function and Account Usage view). The Pipeline Health Dashboard (Section 9) should surface these for consumer cost awareness.

### Task Types Used

The app uses two distinct task patterns, one for each pipeline:

#### 1. Serverless Triggered Task (Event Table Pipeline)

**Purpose**: Export Event Table telemetry (spans, metrics, logs) in near real-time as soon as new data arrives.

**Key characteristics** ([triggered tasks docs](https://docs.snowflake.com/en/user-guide/tasks-triggered)):
- Uses `WHEN SYSTEM$STREAM_HAS_DATA('<stream>')` instead of `SCHEDULE` — the two are mutually exclusive for triggered tasks.
- `TARGET_COMPLETION_INTERVAL` is **required** for serverless triggered tasks — Snowflake uses it to estimate and scale resources. Note: "when a task is already at its maximum warehouse size and is running too long, the target completion interval is ignored" ([docs](https://docs.snowflake.com/en/user-guide/tasks-intro#target-completion-interval)) — the `USER_TASK_TIMEOUT_MS` is the hard timeout that always applies.
- Only one instance runs at a time. If the task is still running when new data arrives, the next run starts after the current one completes.
- **Minimum trigger interval**: triggered tasks run at most every 30 seconds by default. This can be lowered to 10 seconds via `USER_TASK_MINIMUM_TRIGGER_INTERVAL_IN_SECONDS` ([docs](https://docs.snowflake.com/en/sql-reference/parameters#label-user-task-minimum-trigger-interval-in-seconds)). For MVP, the default 30-second interval is sufficient for observability use cases.
- **12-hour health check**: if a triggered task hasn't run for 12 hours, Snowflake schedules a health check to prevent stream staleness. If no changes are detected, the task is skipped without using compute. This provides an additional staleness safety net beyond our `SYSTEM$STREAM_HAS_DATA()` calls (see Section 8.1).

**DDL pattern in `setup.sql`:**
```sql
CREATE OR REPLACE TASK _internal.event_table_export_task
  TARGET_COMPLETION_INTERVAL = '5 MINUTES'
  SUSPEND_TASK_AFTER_NUM_FAILURES = 10
  USER_TASK_TIMEOUT_MS = 300000               -- 5-minute hard timeout per run
  WHEN SYSTEM$STREAM_HAS_DATA('_splunk_obs_stream_<event_table>')
  AS CALL _internal.event_table_collector();
```

> **Note**: Tasks are created in the SUSPENDED state. The setup script resumes them after all dependencies (streams, procedures, EAI) are created. One triggered task is created per Event Table stream selected by the consumer.

#### 2. Serverless Scheduled Task Graph (ACCOUNT_USAGE Pipeline)

**Purpose**: Orchestrate parallel collection and export of ACCOUNT_USAGE views on a schedule, with a finalizer for health recording.

**Key characteristics** ([task graphs docs](https://docs.snowflake.com/en/user-guide/tasks-graphs)):
- Root task uses `SCHEDULE = '30 MINUTES'` (aligned with fastest source cadence — see Section 7.8).
- Child tasks use `AFTER <parent_task>` — siblings of the same parent run in parallel.
- Finalizer task uses `FINALIZE = <root_task>` — runs after all other tasks complete or fail.
- `ALLOW_OVERLAPPING_EXECUTION` defaults to `FALSE` — only one graph run at a time. If a run exceeds the schedule interval, the next run is skipped. This is the correct behavior for our watermark-based pipeline (prevents duplicate exports).

**Ownership and schema constraints** ([task graph ownership docs](https://docs.snowflake.com/en/user-guide/tasks-graphs#manage-task-graph-ownership)):
- **All tasks in a task graph must have the same owner role and reside in the same database and schema.** Our entire task graph lives in the `_internal` schema, owned by the app's application role — this requirement is naturally satisfied.

**DDL patterns in `setup.sql`:**

Root task:
```sql
CREATE OR REPLACE TASK _internal.account_usage_root
  SCHEDULE = '30 MINUTES'
  SUSPEND_TASK_AFTER_NUM_FAILURES = 10
  TASK_AUTO_RETRY_ATTEMPTS = 1                -- retry entire graph once on child failure
  USER_TASK_TIMEOUT_MS = 1800000              -- 30-minute graph timeout
  ALLOW_OVERLAPPING_EXECUTION = FALSE
  AS CALL _internal.account_usage_root_handler();
  -- Root determines which sources are due for polling and sets return value
```

Child task (one per enabled ACCOUNT_USAGE source):
```sql
CREATE OR REPLACE TASK _internal.query_history_collector
  USER_TASK_TIMEOUT_MS = 600000               -- 10-minute per-child timeout
  AFTER _internal.account_usage_root
  AS CALL _internal.account_usage_source_collector('QUERY_HISTORY');
```

Finalizer task:
```sql
CREATE OR REPLACE TASK _internal.pipeline_health_recorder_task
  USER_TASK_TIMEOUT_MS = 120000               -- 2-minute timeout for metrics recording
  FINALIZE = _internal.account_usage_root
  AS CALL _internal.pipeline_health_recorder();
```

> **Finalizer constraints**: each root task can have only one finalizer, and a finalizer cannot have child tasks. The finalizer runs only when no other tasks are running or queued in the current graph run. If the root task is skipped (e.g., overlap prevention), the finalizer also does not run.

### Task Lifecycle in setup.sql

Tasks start in the **SUSPENDED** state upon creation ([docs](https://docs.snowflake.com/en/user-guide/tasks-intro#define-schedules-or-triggers)). The `setup.sql` script follows this lifecycle:

1. **Create procedures** — all stored procedures must exist before tasks reference them.
2. **Create streams** — streams on Event Tables must exist before triggered tasks reference them.
3. **Create tasks** — `CREATE OR REPLACE TASK` for all tasks (root, children, finalizer, triggered). All created in SUSPENDED state.
4. **Resume child tasks and finalizer first** — child tasks and finalizer must be resumed before the root task.
5. **Resume root task last** — resuming the root task activates the entire graph.

For the task graph, use `SYSTEM$TASK_DEPENDENTS_ENABLE()` to atomically resume all tasks:
```sql
-- Resume all tasks in the graph at once (children + finalizer + root)
SELECT SYSTEM$TASK_DEPENDENTS_ENABLE('_internal.account_usage_root');
```

For triggered tasks (Event Table pipeline):
```sql
ALTER TASK _internal.event_table_export_task RESUME;
```

**Modifying a running task graph** ([versioning docs](https://docs.snowflake.com/en/user-guide/tasks-graphs#versioning)):
- Suspend the **root task** first (`ALTER TASK _internal.account_usage_root SUSPEND`). Child tasks retain their state but stop receiving new triggers.
- Make modifications (add/remove child tasks, alter parameters).
- Resume the root task — Snowflake sets a new version of the entire graph.
- If a run is in progress when the root is suspended, it completes using the current version.

This is relevant for **app upgrades**: the setup script uses `CREATE OR REPLACE TASK`, which effectively drops and recreates each task. The `SYSTEM$TASK_DEPENDENTS_ENABLE()` call at the end re-establishes the graph and sets a new version.

### Dynamic Task Management (Streamlit UI)

When the consumer enables/disables monitoring packs, the Streamlit UI dynamically manages child tasks using the [Snowflake Python API DAG classes](https://docs.snowflake.com/en/developer-guide/snowflake-python-api/snowflake-python-managing-tasks) or direct SQL:

**Adding a child task** (when enabling a new source):
```sql
ALTER TASK _internal.account_usage_root SUSPEND;

CREATE OR REPLACE TASK _internal.login_history_collector
  USER_TASK_TIMEOUT_MS = 600000
  AFTER _internal.account_usage_root
  AS CALL _internal.account_usage_source_collector('LOGIN_HISTORY');

ALTER TASK _internal.login_history_collector RESUME;
ALTER TASK _internal.account_usage_root RESUME;
```

**Removing a child task** (when disabling a source):
```sql
ALTER TASK _internal.account_usage_root SUSPEND;
DROP TASK IF EXISTS _internal.login_history_collector;
ALTER TASK _internal.account_usage_root RESUME;
```

**Suspending a child task** (temporary skip — e.g., during maintenance):
- A suspended child task is **skipped** by the graph — downstream tasks (if any) run as if it succeeded. Since our graph is flat (all children → finalizer), suspending a child simply means that source is not polled.

### Key Task Parameters

| Parameter | Where Set | Value | Purpose |
|---|---|---|---|
| `SCHEDULE` | Root task | `'30 MINUTES'` | Poll interval for ACCOUNT_USAGE pipeline (Section 7.8) |
| `TARGET_COMPLETION_INTERVAL` | Triggered task | `'5 MINUTES'` | Serverless scaling target for Event Table processing |
| `WHEN` | Triggered task | `SYSTEM$STREAM_HAS_DATA(...)` | Stream-driven trigger condition |
| `TASK_AUTO_RETRY_ATTEMPTS` | Root task | `1` | Auto-retry entire graph once on child failure |
| `SUSPEND_TASK_AFTER_NUM_FAILURES` | All tasks | `10` (default) | Auto-suspend after 10 consecutive failures to prevent runaway costs ([docs](https://docs.snowflake.com/en/user-guide/tasks-intro#automatically-suspend-tasks-after-failed-runs)) |
| `USER_TASK_TIMEOUT_MS` | All tasks | Varies per task | Hard timeout per task run. On root task, applies to entire graph; on child task, overrides root timeout for that child ([docs](https://docs.snowflake.com/en/user-guide/tasks-graphs#task-graph-timeouts)) |
| `ALLOW_OVERLAPPING_EXECUTION` | Root task | `FALSE` (default) | Prevent concurrent graph runs — critical for watermark-based pipeline correctness |
| `SERVERLESS_TASK_MIN_STATEMENT_SIZE` | Optional | Not set (default XSMALL) | Minimum compute size floor. Snowflake auto-tunes within this range after each run. Default XSMALL is sufficient for MVP |
| `SERVERLESS_TASK_MAX_STATEMENT_SIZE` | Optional | Not set (default XXLARGE) | Maximum compute size ceiling. Snowflake auto-scales up to this limit. Constrain post-MVP for cost control (e.g., `'LARGE'` cap) |
| `USER_TASK_MINIMUM_TRIGGER_INTERVAL_IN_SECONDS` | Triggered task | `30` (default) | Minimum seconds between triggered task runs — default is appropriate |

### Task Security & Privileges

**Privileges required for serverless tasks** ([task security docs](https://docs.snowflake.com/en/user-guide/tasks-intro#task-security)):

| Object | Privilege | Declared In | Notes |
|---|---|---|---|
| Account | `EXECUTE MANAGED TASK` | `manifest.yml` | Required for serverless compute model |
| Account | `EXECUTE TASK` | `manifest.yml` | Required for the task owner role to run any tasks it owns |
| Schema | `CREATE TASK` | Automatic (app-owned schema) | The app owns `_internal` schema and has full DDL privileges |
| Task | `OWNERSHIP` | Automatic (created by app) | The app role owns all tasks it creates |
| Task | `OPERATE` | Granted to app role | Required to suspend/resume tasks programmatically |

> **Important**: Both `EXECUTE MANAGED TASK` **and** `EXECUTE TASK` are required. `EXECUTE MANAGED TASK` authorizes serverless compute; `EXECUTE TASK` authorizes the task owner role to actually run the tasks. The manifest must declare both.

**Tasks run as system service**: by default, Snowflake runs tasks using a system service with the task owner's privileges — not tied to any individual user ([docs](https://docs.snowflake.com/en/user-guide/tasks-intro#tasks-run-by-a-system-service)). This is ideal for Native Apps because:
- No dependency on a specific consumer user existing or being active.
- The task runs with the app role's privileges (which include access to internal schemas, ACCOUNT_USAGE, and EAI).
- If a consumer user is dropped or locked, the tasks continue running without interruption.

### Task Observability

Tasks provide built-in observability that our Pipeline Health Dashboard (Section 9) leverages:

| View/Function | Scope | What It Shows |
|---|---|---|
| `TASK_HISTORY()` | Information Schema | Per-task run history: state (SUCCEEDED/FAILED/CANCELLED/SKIPPED), scheduled time, query start/completion time, error messages ([docs](https://docs.snowflake.com/en/sql-reference/functions/task_history)) |
| `COMPLETE_TASK_GRAPHS()` | Information Schema | End-to-end DAG execution: scheduled time, completed time, state, root task ID. Available for runs completed in past 60 minutes ([docs](https://docs.snowflake.com/en/sql-reference/functions/complete_task_graphs)) |
| `COMPLETE_TASK_GRAPHS` | Account Usage | Same as above but with extended retention (1 year). Used by our Performance Pack for task failure alerting |
| `CURRENT_TASK_GRAPHS()` | Information Schema | Currently running or scheduled graph runs ([docs](https://docs.snowflake.com/en/sql-reference/functions/current_task_graphs)) |
| `TASK_HISTORY` | Account Usage | Extended retention (1 year) task history. Exported by Performance Pack |
| `SERVERLESS_TASK_HISTORY` | Account Usage/Information Schema | Credit consumption per serverless task. Exported by Cost Pack (post-MVP) |
| `TASK_VERSIONS` | Account Usage | History of task version changes — useful for tracking app upgrade impacts |

**Runtime introspection functions** (available within task body / stored procedure):
- `SYSTEM$TASK_RUNTIME_INFO('CURRENT_ROOT_TASK_UUID')` — unique identifier for the current graph run
- `SYSTEM$TASK_RUNTIME_INFO('CURRENT_TASK_GRAPH_ORIGINAL_SCHEDULED_TIMESTAMP')` — when the graph run was originally scheduled
- `SYSTEM$TASK_RUNTIME_INFO('CURRENT_TASK_NAME')` — name of the currently executing task
- `SYSTEM$SET_RETURN_VALUE()` / `SYSTEM$GET_PREDECESSOR_RETURN_VALUE()` — pass data between tasks in the graph (used by root task to communicate which sources are due for polling — see Section 7.6)
- `SYSTEM$GET_TASK_GRAPH_CONFIG()` — read task graph configuration (available if we use the `CONFIG` parameter)

### Task Graph Configuration (`CONFIG` Parameter)

The task graph supports a `CONFIG` JSON parameter on the root task that can be read by all tasks in the graph via `SYSTEM$GET_TASK_GRAPH_CONFIG()` ([docs](https://docs.snowflake.com/en/user-guide/tasks-graphs#pass-configuration-information-to-the-task-graph)). This is useful for passing shared configuration without requiring each child task to read `_internal.config` independently:

```sql
ALTER TASK _internal.account_usage_root SET
  CONFIG = '{"batch_size": 5000, "max_batches_per_run": 100}';
```

Child tasks can then read: `SELECT SYSTEM$GET_TASK_GRAPH_CONFIG('batch_size')`. This is a **post-MVP optimization** — in MVP, each procedure reads configuration from `_internal.config` directly.

### Task Inventory

| Task | Type | Schema | Trigger/Schedule | Calls Procedure | Notes |
|---|---|---|---|---|---|
| `_internal.event_table_export_task` | Triggered (serverless) | `_internal` | `WHEN SYSTEM$STREAM_HAS_DATA(...)` | `_internal.event_table_collector` | One per Event Table stream; near real-time |
| `_internal.account_usage_root` | Scheduled (serverless) | `_internal` | `SCHEDULE = '30 MINUTES'` | Root handler (determines due sources) | Root of task graph DAG |
| `_internal.query_history_collector` | Child (serverless) | `_internal` | `AFTER account_usage_root` | `_internal.account_usage_source_collector('QUERY_HISTORY')` | MVP: Performance Pack |
| `_internal.task_history_collector` | Child (serverless) | `_internal` | `AFTER account_usage_root` | `_internal.account_usage_source_collector('TASK_HISTORY')` | MVP: Performance Pack |
| `_internal.complete_task_graphs_collector` | Child (serverless) | `_internal` | `AFTER account_usage_root` | `_internal.account_usage_source_collector('COMPLETE_TASK_GRAPHS')` | MVP: Performance Pack |
| `_internal.lock_wait_history_collector` | Child (serverless) | `_internal` | `AFTER account_usage_root` | `_internal.account_usage_source_collector('LOCK_WAIT_HISTORY')` | MVP: Performance Pack |
| `_internal.pipeline_health_recorder_task` | Finalizer (serverless) | `_internal` | `FINALIZE = account_usage_root` | `_internal.pipeline_health_recorder` | Records metrics after graph run |

> **Naming convention**: child tasks are named `_internal.<source_name_lowercase>_collector` for clarity in `TASK_HISTORY` views. The finalizer task uses `_task` suffix to avoid name collision with the procedure it calls.

### Operational Considerations

**Auto-suspend on consecutive failures**: the `SUSPEND_TASK_AFTER_NUM_FAILURES` parameter (default 10) automatically suspends a task after consecutive failures. This prevents runaway serverless compute costs. The Pipeline Health Dashboard should surface suspended tasks prominently so the consumer can investigate and resume.

**Manual retry**: use `EXECUTE TASK _internal.account_usage_root RETRY LAST` to retry the task graph from the last failed task ([docs](https://docs.snowflake.com/en/sql-reference/sql/execute-task)). This is useful for operators recovering from transient Splunk outages.

**Manual execution**: use `EXECUTE TASK _internal.account_usage_root` to trigger an immediate one-time graph run outside the schedule — useful for testing and initial data backfill.

**App upgrade safety**: the `setup.sql` script uses `CREATE OR REPLACE TASK`, which recreates all tasks. On upgrade:
1. The existing root task is suspended automatically (CREATE OR REPLACE drops the old task).
2. All tasks are recreated with updated definitions.
3. `SYSTEM$TASK_DEPENDENTS_ENABLE()` resumes the entire graph.
4. Snowflake sets a new task graph version.
5. If a graph run was in progress at upgrade time, the old run completes with the old version. The new version applies from the next run.

**Cost monitoring**: serverless task costs can be tracked via:
- `SERVERLESS_TASK_HISTORY` (Information Schema table function and Account Usage view) — per-task credit breakdown.
- `METERING_HISTORY` / `METERING_DAILY_HISTORY` (Account Usage) — filter by `service_type IN ('SERVERLESS_TASK', 'SERVERLESS_TASK_FLEX')`.
- Serverless credits have a multiplier vs. standard warehouse credits (see "Serverless Feature Credit Table" in [Snowflake Service Consumption Table](https://www.snowflake.com/legal-files/CreditConsumptionTable.pdf)).
- For post-MVP Cost Pack, the app exports `SERVERLESS_TASK_HISTORY` to Splunk, enabling consumers to monitor the cost of the app itself.

---