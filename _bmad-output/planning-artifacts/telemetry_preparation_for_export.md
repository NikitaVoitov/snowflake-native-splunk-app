# Telemetry Preparation for Export

> **Audience:** Engineers implementing Snowflake-side data preparation for OTLP export stored procedures.
> **Status:** Verified from live Snowflake metadata (account `LFB71918`, 2026-04-05) and cross-referenced against official Snowflake documentation (13 pages scraped 2026-04-05).
> **Scope:** Exact field schemas, data types, extraction patterns, limits, configuration dependencies, and pushdown rules for every telemetry source.
> **Companion docs:** `grpc_research.md` (transport layer), `otel_semantic_conventions_snowflake_research.md` (convention mapping), `splunk_snowflake_native_app_vision.md` (architecture), `evt_architecture_adversarial_review.md` (incremental-read primitive decision — `CHANGES` + self-managed watermark), `event_table_entity_discrimination_strategy.md` (entity filtering).
>
> **Pipeline primitives (this document is aligned with):** Event Table and AI-observability sources are consumed via the Snowflake `CHANGES(INFORMATION => APPEND_ONLY)` clause with explicit `AT(TIMESTAMP => :watermark) END(TIMESTAMP => :batch_end)` bounds and a self-managed watermark in `_internal.export_watermarks`. ACCOUNT_USAGE sources do not support `CHANGES`, so they use watermark + overlap + `QUALIFY ROW_NUMBER()` deduplication. Both pipelines are driven by independent scheduled tasks (default 1 min cadence). No Snowflake streams are used anywhere in this design.

---

## 1. Canonical Sources (Verified Live)

| Source | Object | Pipeline | Access Pattern |
|---|---|---|---|
| Standard event table (base) | `SNOWFLAKE.TELEMETRY.EVENTS` | Event Table pipeline | `CHANGES(INFORMATION => APPEND_ONLY) AT(TIMESTAMP => :watermark) END(TIMESTAMP => :batch_end)` driven by scheduled task (default 1 min) |
| Standard event table (view) | `SNOWFLAKE.TELEMETRY.EVENTS_VIEW` | — | Not a supported direct source for this app; `CHANGES` requires `CHANGE_TRACKING = TRUE` on the target object, and the app cannot enable it on this system view |
| Consumer custom view over ET | Consumer-created view over any ET | Event Table pipeline | `CHANGES(INFORMATION => APPEND_ONLY) AT(...) END(...)` driven by scheduled task. Requires consumer to set `CHANGE_TRACKING = TRUE` on the view (owner operation — cannot be performed by the app) |
| AI observability | `SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS` | Event Table pipeline | `CHANGES(INFORMATION => APPEND_ONLY) AT(...) END(...)` driven by scheduled task |
| Query performance | `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` | ACCOUNT_USAGE pipeline | Watermark + overlap window + `QUALIFY ROW_NUMBER()` dedup (scheduled task) — `CHANGES` is not supported on ACCOUNT_USAGE views |
| Authentication | `SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY` | ACCOUNT_USAGE pipeline | Watermark + overlap + dedup (scheduled task) |
| Data access governance | `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY` | ACCOUNT_USAGE pipeline | Watermark + overlap + dedup (scheduled task) |

---

**Source-selection note:** Snowflake supports `CHANGES` reads on both event tables and views, provided `CHANGE_TRACKING = TRUE`. Our exclusion of `SNOWFLAKE.TELEMETRY.EVENTS_VIEW` is narrower: live metadata shows `CHANGE_TRACKING = OFF` for this system view and the app does not have privileges to enable it. For consumer-owned custom views over an Event Table, the consumer must run `ALTER VIEW <view> SET CHANGE_TRACKING = TRUE` before the app can read that source. The app detects the missing flag and surfaces the `CHANGE_TRACKING_DISABLED` diagnostic in the health dashboard.

**Time-travel window dependency:** `CHANGES` relies on Snowflake time travel. Standard and Enterprise Edition accounts provide a minimum 1-day window, which the app's default 1-minute scheduled cadence stays well inside. If a task is suspended long enough for the watermark to fall outside the time-travel window (for example, during a lengthy app upgrade), the collector catches the resulting `Time travel data is not available` error, resets the watermark to `CURRENT_TIMESTAMP() - event_table.watermark_reset_buffer_seconds`, records `WATERMARK_EXPIRED` in `_metrics.pipeline_health`, and resumes on the next scheduled run. See Section 10 for the full lifecycle.

## 2. Event Table Schema (Both Sources)

Both `SNOWFLAKE.TELEMETRY.EVENTS` and `SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS` share the same 13-column structure:

| Column | SQL Type | Description |
|---|---|---|
| `TIMESTAMP` | `TIMESTAMP_NTZ(9)` | Event end time (span end, log emit, metric scrape). UTC. |
| `START_TIMESTAMP` | `TIMESTAMP_NTZ(9)` | Span start time. NULL for logs and non-sum metrics. |
| `OBSERVED_TIMESTAMP` | `TIMESTAMP_NTZ(9)` | Currently same as TIMESTAMP for logs. NULL for spans. |
| `TRACE` | `OBJECT` | `{trace_id, span_id}`. Present for SPAN, SPAN_EVENT. NULL for LOG, METRIC, EVENT. |
| `RESOURCE` | `OBJECT` | Reserved for future use. Always NULL in live data. |
| `RESOURCE_ATTRIBUTES` | `OBJECT` | Source identification: user, warehouse, executable, database, schema, service. |
| `SCOPE` | `OBJECT` | `{name}` — instrumentation scope. Per official docs: "not used for trace events." Used for LOG events as the namespace of emitting code (e.g. class name). Present for AI obs logs. |
| `SCOPE_ATTRIBUTES` | `OBJECT` | Reserved for future use. Always NULL in live data. |
| `RECORD_TYPE` | `VARCHAR` | Signal discriminator: `SPAN`, `SPAN_EVENT`, `LOG`, `METRIC`, `EVENT`. |
| `RECORD` | `OBJECT` | Signal-specific fixed fields. Shape varies by RECORD_TYPE (see below). |
| `RECORD_ATTRIBUTES` | `OBJECT` | Signal-specific variable attributes. Shape varies by RECORD_TYPE (see below). |
| `VALUE` | `VARIANT` | Primary payload for logs (VARCHAR) and metrics (DECIMAL/INTEGER/OBJECT). NULL for spans. |
| `EXEMPLARS` | `ARRAY` | Reserved for future use. Always NULL in live data. |

---

## 3. Per-Signal RECORD Shape (Verified from Live Samples)

### 3.1 SPAN

**RECORD keys:** `kind`, `name`, `parent_span_id`, `status`, `dropped_attributes_count`, `snow.process.memory.usage.max` (optional)

| Path | Extraction | Live Values / Notes |
|---|---|---|
| `RECORD:"kind"::STRING` | Span kind enum | `SPAN_KIND_SERVER` (SQL-traced), `SPAN_KIND_INTERNAL` (handler code), `SPAN_KIND_CLIENT` (SPCS OTel SDK). Per docs: SQL → SERVER, non-SQL handler → INTERNAL. |
| `RECORD:"name"::STRING` | Span name | Python: handler function name. SQL: statement type (`SELECT`, `INSERT`, `CALL`). Non-Python/non-SQL: `snow.auto_instrumented`. Client code: client-side API name. |
| `RECORD:"parent_span_id"::STRING` | Parent link | Hex string or empty. Present when proc/UDF was called by another proc in a call chain. |
| `RECORD:"status":"code"::STRING` | Status code | Per docs: `STATUS_CODE_ERROR` on unhandled exception, `STATUS_CODE_UNSET` otherwise. `STATUS_CODE_OK` observed in live data from custom spans/OTel SDK. |
| `RECORD:"status":"message"::STRING` | Error detail | Present only when code = `STATUS_CODE_ERROR`. Can be long. |
| `RECORD:"dropped_attributes_count"::NUMBER` | Dropped attrs | Count of attributes dropped after the 128 max. Not set for JavaScript spans. |
| `RECORD:"snow.process.memory.usage.max"::STRING` | Peak memory | Max memory in bytes used during span execution. Optional. |

**TRACE keys:** `trace_id`, `span_id`

| Path | Extraction |
|---|---|
| `TRACE:"trace_id"::STRING` | 32-char hex trace ID. Unique per query; same for all spans within a single query execution. |
| `TRACE:"span_id"::STRING` | 16-char hex span ID. For UDFs, there may be multiple spans (one per execution thread) sharing the same trace_id. |

**VALUE:** Always NULL for SPAN rows.

**SCOPE:** Per official docs: "not used for trace events." May be present for SPCS OTel SDK spans that set their own instrumentation scope.

### 3.2 SPAN_EVENT

**RECORD keys:** `name`, `dropped_attributes_count` (optional, not set for JavaScript)

| Path | Extraction | Live Values |
|---|---|---|
| `RECORD:"name"::STRING` | Event name | `exception` (unhandled exception events), or user-defined event names |
| `RECORD:"dropped_attributes_count"::NUMBER` | Dropped attrs | Count of event attributes dropped after limit. Not set for JavaScript. |

**RECORD_ATTRIBUTES keys (verified):**

| Key | Presence | Type |
|---|---|---|
| `exception.message` | Always on exception events | STRING |
| `exception.type` | Always on exception events | STRING (numeric error code) |
| `exception.stacktrace` | On unhandled exceptions | STRING (stack trace formatted by language runtime) |
| `exception.escaped` | On unhandled exceptions | BOOLEAN (`true` when exception was not caught) |

**TRACE:** Same structure as SPAN — links the event to its parent span via shared `trace_id` AND `span_id`. Join pattern: `SPAN_EVENT.TRACE:"span_id" = SPAN.TRACE:"span_id"`.

**VALUE:** Always NULL.

**Relationship to parent SPAN:** When a SPAN_EVENT with `name=exception` exists, the parent SPAN row gets `RECORD:"status":"code" = STATUS_CODE_ERROR`.

### 3.3 LOG

**RECORD keys:** `severity_number`, `severity_text` — OR NULL (container stderr logs have no RECORD).

Three distinct LOG populations exist:

| Population | RECORD | RECORD_ATTRIBUTES | VALUE |
|---|---|---|---|
| Container logs (SPCS stderr/stdout) | NULL | `{log.iostream: "stderr"}` | VARCHAR — the log line |
| Instrumented logs (Python/Java handler code) | `{severity_number, severity_text}` | `{code.filepath, code.function, code.lineno, code.namespace, thread.id, thread.name}` | VARCHAR — the log message |
| Unhandled exception logs | `{severity_number, severity_text}` | `{exception.message, exception.type, exception.stacktrace, exception.escaped}` | VARCHAR — the string `exception` (not the error message) |

**Severity values (verified):** `severity_text` ∈ {`TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL`}. `severity_number` is an integer (e.g. 9 = INFO). For unhandled exceptions, `severity_text` is the highest-severity level for the language runtime (e.g. `FATAL` for Python).

**VALUE type:** Always VARCHAR for LOG rows. **Important:** For unhandled exception logs, `VALUE` is the literal string `exception`, not the error message. The actual error message is in `RECORD_ATTRIBUTES:"exception.message"`.

**TRACE:** NULL for all observed LOG rows.

**Dual capture:** Unhandled exceptions can appear as both LOG entries AND SPAN_EVENT entries simultaneously, depending on `LOG_LEVEL` and `TRACE_LEVEL` settings.

### 3.4 METRIC

**RECORD keys:** `metric`, `metric_type`, `value_type` — plus conditionally `aggregation_temporality` and `is_monotonic`.

Three distinct metric shapes:

| metric_type | Additional RECORD Keys | VALUE Type |
|---|---|---|
| `gauge` | `value_type` = `DOUBLE` | DECIMAL or INTEGER |
| `sum` | `aggregation_temporality`, `is_monotonic`, `value_type` = `INT` | INTEGER |
| `histogram` | `aggregation_temporality` | OBJECT (bucket boundaries + counts) |

**`RECORD:"metric"` is itself a nested OBJECT:**

| Path | Type | Example |
|---|---|---|
| `RECORD:"metric":"name"::STRING` | Metric name | `container.cpu.usage`, `container.memory.usage` |
| `RECORD:"metric":"description"::STRING` | Human description | `Average number of CPU cores used...` |
| `RECORD:"metric":"unit"::STRING` | Unit string | `cpu`, `byte`, `1` |

**TRACE:** NULL for all observed METRIC rows.

**RECORD_ATTRIBUTES:** Usually NULL for container metrics. Present (http.* keys) for instrumented HTTP server metrics from SPCS services.

### 3.5 EVENT

**RECORD keys:** `name`, `severity_number`, `severity_text`

| Path | Live Values |
|---|---|
| `RECORD:"name"::STRING` | `execution.status`, `CONTAINER.STATUS_CHANGE`, `application.state_change` (Native App lifecycle) |
| `RECORD:"severity_text"::STRING` | `INFO`, `WARN`, `ERROR`, `DEBUG` |

**VALUE:** OBJECT (structured JSON).

| EVENT subtype | VALUE keys (examples) |
|---|---|
| Task execution | `{state: "SUCCEEDED"}` |
| Container status | `{status: "DONE", message: "Completed successfully"}` |
| Native App lifecycle | `{upgrade_state, upgrade_attempt, target_upgrade_version, target_upgrade_patch, upgrade_failure_reason, health_status, action, privileges}` |

**RECORD_ATTRIBUTES:** NULL for all observed EVENT rows.

**TRACE:** NULL for all observed EVENT rows.

---

## 4. RECORD_ATTRIBUTES Key Catalog (Verified Exhaustive)

### 4.1 SNOWFLAKE.TELEMETRY.EVENTS

#### SPAN RECORD_ATTRIBUTES

| Key | Observed Count | Category |
|---|---|---|
| `db.query.table.names` | 1732 | SQL trace — tables accessed |
| `db.query.view.names` | (documented) | SQL trace — views accessed (per official docs) |
| `db.query.executable.names` | 79 | SQL trace — executables called |
| `db.query.text` | (requires `SQL_TRACE_QUERY_TEXT=ON`) | SQL text up to 1024 chars. Requires ACCOUNTADMIN to enable. |
| `snow.input.rows` | (documented for UDFs) | Input rows processed by function span |
| `snow.output.rows` | (documented for UDFs) | Output rows emitted by function span |
| `snow.application.update.attempt` | 175 | Native App lifecycle |
| `snow.application.create.attempt` | 9 | Native App lifecycle |
| `gen_ai.evaluation.sampled` | 25 | GenAI — Cortex Agent evaluation |
| `gen_ai.provider.name` | 21 | GenAI — provider identification |
| `gen_ai.operation.name` | 14 | GenAI — operation type |
| `gen_ai.step.name` | 11 | GenAI — agent step |
| `gen_ai.step.type` | 11 | GenAI — agent step |
| `gen_ai.response.model` | 7 | GenAI — model response |
| `gen_ai.request.model` | 7 | GenAI — model request |
| `gen_ai.usage.input_tokens` | 7 | GenAI — token counts |
| `gen_ai.usage.output_tokens` | 7 | GenAI — token counts |
| `gen_ai.response.finish_reasons` | 7 | GenAI — finish reasons |
| `gen_ai.tool.call.id` | 4 | GenAI — tool calls |
| `gen_ai.tool.name` | 4 | GenAI — tool calls |
| `gen_ai.tool.type` | 4 | GenAI — tool calls |
| `gen_ai.workflow.name` | 3 | GenAI — workflow |
| `gen_ai.workflow.description` | 3 | GenAI — workflow |
| `gen_ai.workflow.type` | 3 | GenAI — workflow |
| `gen_ai.framework` | 3 | GenAI — framework |
| `snowflake.cortex_analyst.*` | 4 each | Cortex Analyst — request details, SQL, model, semantic model |
| `snowflake.database` / `snowflake.schema` / `snowflake.warehouse` | 4 each | Cortex Analyst — context |
| `http.*` | 2-4 each | SPCS HTTP server spans |
| `code.filepath` / `code.lineno` / `method.chain` | 8 each | Instrumented code spans |
| `asgi.event.type` | 8 | ASGI framework spans |

#### LOG RECORD_ATTRIBUTES

| Key | Observed Count | Category |
|---|---|---|
| `log.iostream` | 78909 | Container log source (stderr/stdout) |
| `code.filepath` | 19765 | Instrumented log — source file |
| `code.function` | 19765 | Instrumented log — function name |
| `code.lineno` | 19765 | Instrumented log — line number |
| `code.namespace` | (documented) | Instrumented log — namespace of emitting code |
| `thread.id` | (documented) | Thread ID where log was created |
| `thread.name` | (documented) | Thread name where log was created |
| `exception.message` | 18 | Unhandled exception |
| `exception.type` | 18 | Exception type |
| `exception.escaped` | 12 | Exception escaped flag |
| `exception.stacktrace` | 6 | Stack trace |

#### METRIC RECORD_ATTRIBUTES

Usually NULL (176,447 of 176,511 rows). When present, contains HTTP server metric dimensions: `http.server_name`, `http.flavor`, `http.scheme`, `http.method`, `http.host`, `http.status_code`, `http.target`, `net.host.port`.

#### SPAN_EVENT RECORD_ATTRIBUTES

| Key | Count |
|---|---|
| `exception.message` | 10 |
| `exception.type` | 10 |

#### EVENT RECORD_ATTRIBUTES

Always NULL.

### 4.2 SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS

#### AI Obs SPAN RECORD_ATTRIBUTES

**Always present (all 1776 rows):**

| Key | Description |
|---|---|
| `snow.ai.observability.database.id` | AI obs database ID |
| `snow.ai.observability.database.name` | AI obs database name |
| `snow.ai.observability.schema.id` | AI obs schema ID |
| `snow.ai.observability.schema.name` | AI obs schema name |
| `snow.ai.observability.object.id` | Agent/app object ID |
| `snow.ai.observability.object.name` | Agent/app name |
| `snow.ai.observability.object.type` | `EXTERNAL AGENT` |
| `snow.ai.observability.object.version.id` | Version ID |
| `snow.ai.observability.object.version.name` | Version name |
| `snow.ai.observability.run.id` | Run ID |
| `snow.ai.observability.run.name` | Run name |
| `ai.observability.record_id` | Unique record ID |
| `ai.observability.span_type` | `retrieval`, `generation`, `unknown` |

**TruLens SDK spans (1335 rows):**

| Key | Description |
|---|---|
| `ai.observability.app_id` | Application hash ID |
| `ai.observability.run.name` | Experiment/run name |
| `ai.observability.input_id` | Input hash ID |
| `name` | Function/method name |
| `ai.observability.call.function` | Fully qualified function name |
| `ai.observability.call.return` | Return value (can be very large) |
| `ai.observability.call.kwargs.*` | Function arguments (input, config, query, etc.) |

**Retrieval spans (119-151 rows):**

| Key | Description |
|---|---|
| `ai.observability.retrieval.query_text` | Search query |
| `ai.observability.retrieval.retrieved_contexts` | Retrieved document snippets |
| `ai.observability.retrieval.num_contexts` | Number of contexts |

**Evaluation spans (336-449 rows):**

| Key | Description |
|---|---|
| `ai.observability.eval.metric_name` | Metric being evaluated |
| `ai.observability.eval.metric_type` | Metric type |
| `ai.observability.eval.target_record_id` | Record being evaluated |
| `ai.observability.eval.eval_root_id` | Root evaluation ID |
| `ai.observability.eval.score` | Evaluation score |
| `ai.observability.eval.explanation` | LLM judge explanation |
| `ai.observability.eval.llm_judge_name` | Judge model name |
| `ai.observability.eval.criteria` | Evaluation criteria |
| `ai.observability.eval.args` | Evaluation arguments |

**Cost tracking (35-39 rows):**

| Key | Description |
|---|---|
| `ai.observability.cost.cost` | Cost value |
| `ai.observability.cost.model` | Model name |
| `ai.observability.cost.num_prompt_tokens` | Prompt token count |
| `ai.observability.cost.num_completion_tokens` | Completion token count |
| `ai.observability.cost.num_tokens` | Total token count |

**GenAI standard attributes (rare, 1-32 rows):**

| Key | Count |
|---|---|
| `gen_ai.system` | 32 |
| `gen_ai.completion` | 31 |
| `gen_ai.prompt` | 30 |
| `gen_ai.request.model` | 1 |
| `gen_ai.response.model` | 1 |
| `gen_ai.usage.input_tokens` | 1 |
| `gen_ai.usage.output_tokens` | 1 |
| `gen_ai.usage.total_tokens` | 1 |

#### AI Obs LOG RECORD_ATTRIBUTES

| Key | Count |
|---|---|
| `thread.name` | 6604 |
| `exception.type` | 6 |
| `exception.stacktrace` | 6 |
| `exception.message` | 6 |

---

## 5. RESOURCE_ATTRIBUTES Key Catalog (Verified Exhaustive)

### 5.1 SQL/Snowpark Compute Spans (`snow.executable.type` varies by context)

Always present:

| Key | Type | Example |
|---|---|---|
| `db.user` | STRING | `NVOITOV` |
| `snow.executable.type` | STRING | Official docs enumerate `procedure`, `function`, `query`, `sql`, `spcs`, `streamlit`; live account data also contains `STATEMENT` and `TASK`. Normalize with `UPPER(...)` before filtering. |
| `snow.query.id` | STRING | `01c193da-0107-6d81-000c-01c30074079e` |
| `snow.session.id` | NUMBER | `3379636754354742` |
| `snow.session.role.primary.id` | NUMBER | `5` |
| `snow.session.role.primary.name` | STRING | `ACCOUNTADMIN` |
| `snow.user.id` | NUMBER | `111` |
| `snow.warehouse.id` | NUMBER | `30` |
| `snow.warehouse.name` | STRING | `PAYERS_CC_WH` |

Conditionally present (procedures/functions but not bare queries):

| Key | Type |
|---|---|
| `snow.database.id` | NUMBER |
| `snow.database.name` | STRING |
| `snow.schema.id` | NUMBER |
| `snow.schema.name` | STRING |
| `snow.executable.id` | NUMBER |
| `snow.executable.name` | STRING (full signature) |
| `snow.owner.id` | NUMBER |
| `snow.owner.name` | STRING |
| `telemetry.sdk.language` | STRING (`python`, `sql`, `java`, `javascript`) |
| `snow.executable.runtime.version` | STRING (e.g. `3.11`) |

### 5.2 Native App Context

Additional keys present when the event originates from a Native App:

| Key | Type | Example |
|---|---|---|
| `snow.application.id` | NUMBER | `177` |
| `snow.application.name` | STRING | `SPLUNK_OBSERVABILITY_DEV_APP` |
| `snow.version` | STRING | `UNVERSIONED` |
| `snow.patch` | NUMBER | `32` |
| `snow.release.version` | STRING | Snowflake release running when event was generated (e.g. `7.9.0`) |
| `snow.application.consumer.name` | STRING | Consumer's account name (documented, not observed in dev) |
| `snow.application.consumer.organization` | STRING | Consumer's organization name (documented) |
| `snow.application.package.name` | STRING | Application package name (documented) |
| `snow.listing.global_name` | STRING | Listing identifier (documented) |
| `snow.listing.name` | STRING | Listing name (documented) |

### 5.3 SPCS / Container Service Context

Additional keys present for Snowpark Container Services events:

| Key | Type | Example |
|---|---|---|
| `snow.account.name` | STRING | `LFB71918` |
| `snow.compute_pool.id` | NUMBER | `3` |
| `snow.compute_pool.name` | STRING | `AGENTS_POOL` |
| `snow.compute_pool.node.id` | STRING | IP address |
| `snow.compute_pool.node.instance_family` | STRING | `CPU_X64_M` |
| `snow.service.id` | NUMBER | `5` |
| `snow.service.name` | STRING | `HEALTHCARE_AGENTS_SERVICE` |
| `snow.service.type` | STRING | `Service` |
| `snow.service.instance` | STRING | `0` |
| `snow.service.container.name` | STRING | `healthcare-agent` |
| `snow.service.container.instance` | STRING | `0` |
| `snow.service.container.run.id` | STRING | `b7ad85` |
| `snow.executable.engine` | STRING | `SnowparkContainers` |

### 5.4 OTel SDK Instrumented (SPCS apps using OTel SDK)

Additional keys when the app emits its own OTel telemetry:

| Key | Type |
|---|---|
| `service.name` | STRING |
| `service.version` | STRING |
| `deployment.environment` | STRING |
| `telemetry.sdk.name` | STRING |
| `telemetry.sdk.version` | STRING |

---

## 6. ACCOUNT_USAGE View Schemas (Verified Live)

### 6.1 QUERY_HISTORY (79 columns, latency ≤ 45 min)

**Timestamp anchor:** `START_TIME` (`TIMESTAMP_LTZ(6)`)

**Recommended export projection (19 columns):**

| Column | SQL Type | OTLP Mapping |
|---|---|---|
| `QUERY_ID` | `VARCHAR` | Natural key, `snowflake.query.id` |
| `QUERY_TYPE` | `VARCHAR` | `db.operation.name` |
| `QUERY_TEXT` | `VARCHAR` | `db.query.text` (large, optional) |
| `START_TIME` | `TIMESTAMP_LTZ(6)` | Span start / watermark anchor |
| `END_TIME` | `TIMESTAMP_LTZ(6)` | Span end |
| `TOTAL_ELAPSED_TIME` | `NUMBER(38,0)` | Duration (ms) |
| `COMPILATION_TIME` | `NUMBER(38,0)` | Compile phase (ms) |
| `EXECUTION_TIME` | `NUMBER(38,0)` | Execute phase (ms) |
| `BYTES_SCANNED` | `NUMBER(38,0)` | I/O metric |
| `ROWS_PRODUCED` | `NUMBER(38,0)` | `db.response.returned_rows` |
| `WAREHOUSE_NAME` | `VARCHAR` | `snowflake.warehouse.name` |
| `WAREHOUSE_SIZE` | `VARCHAR` | Warehouse tier |
| `USER_NAME` | `VARCHAR` | `snowflake.user` |
| `ROLE_NAME` | `VARCHAR` | `snowflake.session.role` |
| `DATABASE_NAME` | `VARCHAR` | `db.namespace` part 1 |
| `SCHEMA_NAME` | `VARCHAR` | `db.namespace` part 2 |
| `EXECUTION_STATUS` | `VARCHAR` | SUCCESS, FAIL, INCIDENT |
| `ERROR_CODE` | `VARCHAR` | `db.response.status_code` |
| `ERROR_MESSAGE` | `VARCHAR` | Error detail |

### 6.2 LOGIN_HISTORY (18 columns, latency ≤ 120 min)

**Timestamp anchor:** `EVENT_TIMESTAMP` (`TIMESTAMP_LTZ(6)`)

| Column | SQL Type | Notes |
|---|---|---|
| `EVENT_ID` | `NUMBER(38,0)` | Natural key |
| `EVENT_TIMESTAMP` | `TIMESTAMP_LTZ(6)` | Watermark anchor |
| `EVENT_TYPE` | `VARCHAR` | `LOGIN` / `LOGOUT` |
| `USER_NAME` | `VARCHAR` | CIM `user` |
| `CLIENT_IP` | `VARCHAR` | CIM `src` |
| `REPORTED_CLIENT_TYPE` | `VARCHAR` | `SNOWFLAKE_UI`, `PYTHON_DRIVER`, etc. |
| `REPORTED_CLIENT_VERSION` | `VARCHAR` | Client version |
| `FIRST_AUTHENTICATION_FACTOR` | `VARCHAR` | `PASSWORD`, `KEYPAIR`, etc. |
| `SECOND_AUTHENTICATION_FACTOR` | `VARCHAR` | MFA factor |
| `IS_SUCCESS` | `VARCHAR(3)` | `YES` / `NO` |
| `ERROR_CODE` | `NUMBER(38,0)` | Failure error code |
| `ERROR_MESSAGE` | `VARCHAR` | Failure detail |
| `RELATED_EVENT_ID` | `NUMBER(38,0)` | Links LOGIN ↔ LOGOUT |
| `CONNECTION` | `VARCHAR` | Connection name |

### 6.3 ACCESS_HISTORY (12 columns, latency ≤ 180 min)

**Timestamp anchor:** `QUERY_START_TIME` (`TIMESTAMP_LTZ(9)`)

| Column | SQL Type | Notes |
|---|---|---|
| `QUERY_ID` | `VARCHAR` | Natural key (with QUERY_START_TIME) |
| `QUERY_START_TIME` | `TIMESTAMP_LTZ(9)` | Watermark anchor |
| `USER_NAME` | `VARCHAR` | CIM `user` |
| `DIRECT_OBJECTS_ACCESSED` | `ARRAY` | Nested: `[{objectName, objectDomain, columns: [{columnName}]}]` |
| `BASE_OBJECTS_ACCESSED` | `ARRAY` | Underlying base tables |
| `OBJECTS_MODIFIED` | `ARRAY` | Modified objects |
| `OBJECT_MODIFIED_BY_DDL` | `OBJECT` | DDL-modified object |
| `POLICIES_REFERENCED` | `ARRAY` | Masking/row access policies |
| `PARENT_QUERY_ID` | `VARCHAR` | Parent query link |
| `ROOT_QUERY_ID` | `VARCHAR` | Root query link |

---

## 7. Pushdown Preparation Rules

This project uses a **dual-pipeline architecture**. Rules are split by pipeline type because event table sources and ACCOUNT_USAGE sources have fundamentally different incremental-read primitives:

- **Event Table sources** (standard ET, consumer custom views, AI observability): `CHANGES(INFORMATION => APPEND_ONLY) AT(TIMESTAMP => :watermark) END(TIMESTAMP => :batch_end)` with a self-managed watermark in `_internal.export_watermarks`. Both `watermark` and `batch_end` are exclusive/inclusive bounds resolved by Snowflake's time-travel engine; the collector captures `batch_end = CURRENT_TIMESTAMP()` once at the start of the run and uses the same value for every per-signal read in that run. Watermark advances only on full export success; on terminal failure it is held unchanged for exact retry on the next scheduled run.
- **ACCOUNT_USAGE sources** (QUERY_HISTORY, LOGIN_HISTORY, ACCESS_HISTORY): `CHANGES` is not supported on ACCOUNT_USAGE views, so reads use a watermark + overlap window + `QUALIFY ROW_NUMBER()` deduplication pattern with the same advance-on-success semantics.

### Event Table Pipeline Rules (`CHANGES` + Self-Managed Watermark)

#### Rule ET-1: Read via `CHANGES(INFORMATION => APPEND_ONLY) AT/END`, Not the Source Table

The collector reads from the source object (event table or consumer-owned view with `CHANGE_TRACKING = TRUE`) through the `CHANGES` clause, which returns rows appended in the half-open interval `(watermark, batch_end]`:

```sql
SELECT ... FROM <source>
CHANGES(INFORMATION => APPEND_ONLY)
  AT(TIMESTAMP => :watermark)
  END(TIMESTAMP => :batch_end)
WHERE RECORD_TYPE = 'SPAN'
```

Both `:watermark` and `:batch_end` are `TIMESTAMP_LTZ` bound parameters. `:batch_end` is captured once per run as `CURRENT_TIMESTAMP()` and reused across every per-signal read in the same run so that all signal queries see a consistent window.

#### Rule ET-2: Entity Discrimination as First Filter

Apply a **normalized, configurable** include-list immediately after `RECORD_TYPE`:

```sql
WHERE RECORD_TYPE = 'SPAN'
  AND UPPER(RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING)
      IN ('PROCEDURE', 'FUNCTION', 'QUERY', 'SQL', 'STATEMENT')
```

Why this shape:

- Official docs explicitly list `query` and `sql`.
- Live account data on 2026-04-06 contained `QUERY`, `PROCEDURE`, `STATEMENT`, `TASK`, and `STREAMLIT`.
- `STATEMENT` should therefore be included **in addition to** `SQL`, not as a replacement.
- `TASK` is real telemetry but is out of MVP scope unless task-originated events are intentionally exported.

This pushes entity filtering to the Snowflake engine before any VARIANT extraction while staying resilient to documented-vs-live vocabulary drift. See `event_table_entity_discrimination_strategy.md` for the broader filter design.

#### Rule ET-3: No Dedup Required

`CHANGES(INFORMATION => APPEND_ONLY) AT/END` is an append-only change set over an immutable time-travel snapshot — each row appears exactly once in the `(watermark, batch_end]` window, and the same row is not re-returned by subsequent runs because the watermark advances strictly monotonically on success. Do NOT add `QUALIFY ROW_NUMBER()` to Event Table extraction queries — it adds a window-function sort with zero benefit.

#### Rule ET-4: Extract and Cast in SQL, Not Python

Same principle as always — typed extraction server-side:

```sql
SELECT
    TRACE:"trace_id"::STRING              AS trace_id,
    TRACE:"span_id"::STRING               AS span_id,
    RECORD:"name"::STRING                 AS span_name,
    RECORD:"kind"::STRING                 AS span_kind,
    TIMESTAMP                             AS end_time,
    START_TIMESTAMP                       AS start_time,
    RECORD_ATTRIBUTES,
    RESOURCE_ATTRIBUTES
FROM <source>
CHANGES(INFORMATION => APPEND_ONLY)
  AT(TIMESTAMP => :watermark)
  END(TIMESTAMP => :batch_end)
WHERE RECORD_TYPE = 'SPAN'
  AND UPPER(RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING)
      IN ('PROCEDURE', 'FUNCTION', 'QUERY', 'SQL', 'STATEMENT')
```

**Lean vs relay mode** applies here exactly as before:

- **Lean mode**: omit full `RECORD_ATTRIBUTES` and `RESOURCE_ATTRIBUTES`; export only the explicitly extracted typed columns. Use when the exported attribute set is fully known at build time.
- **Relay mode**: keep full `RECORD_ATTRIBUTES` and `RESOURCE_ATTRIBUTES` for convention-transparent forwarding of original attributes unknown at build time.

Prefer lean mode for well-known signal types. Use relay mode for event-table sources only when preserving the full attribute bag is a requirement.

#### Rule ET-5: One Query Per Signal Type, Same `[watermark, batch_end]` Window

Do not mix `RECORD_TYPE` values in a single query. Each signal type has different RECORD/VALUE shapes. Issue separate `CHANGES(...) AT/END` queries per signal type using the **same `:watermark` and `:batch_end` values** within the run — this guarantees the four per-signal queries see a mutually consistent snapshot and enables in-memory `(trace_id, span_id)` correlation between `SPAN` and `SPAN_EVENT` without a self-join.

#### Rule ET-6: Materialize via `to_pandas_batches()` Only

```python
for chunk in df.to_pandas_batches():
    otlp_batch = serialize_to_otlp(chunk)
    exporter.export(otlp_batch)
```

Never use `collect()` for bulk export. Never use `to_pandas()` without bounding the result set.

#### Rule ET-7: Advance Watermark Only on Full Export Success (Hold-on-Failure)

The watermark is managed explicitly by the app in `_internal.export_watermarks`, not by any Snowflake-owned cursor:

```python
watermark  = read_watermark(session, source_name)
batch_end  = session.sql("SELECT CURRENT_TIMESTAMP()").collect()[0][0]

try:
    per_signal_export(source_name, watermark, batch_end)  # all four signal reads + OTLP
except SnowparkSQLException as e:
    if _is_time_travel_expired(e):
        # See Rule ET-8 — WATERMARK_EXPIRED self-heal.
        reset_watermark(session, source_name,
                        batch_end - timedelta(seconds=reset_buffer_seconds))
        record_health(session, source_name, "watermark_reset", 1,
                      {"error_code": "WATERMARK_EXPIRED"})
        return "WATERMARK_RESET"
    raise

if all_signal_exports_succeeded:
    # Advance atomically to the same batch_end used for every signal query.
    session.sql("""
        MERGE INTO _internal.export_watermarks t
        USING (SELECT :source_name AS source_name, :batch_end AS watermark) s
        ON t.source_name = s.source_name
        WHEN MATCHED THEN UPDATE SET t.watermark = s.watermark
        WHEN NOT MATCHED THEN INSERT (source_name, watermark)
            VALUES (s.source_name, s.watermark)
    """, params=[source_name, batch_end]).collect()
else:
    # Hold watermark unchanged — next scheduled run retries the exact same window.
    pass
```

**Guarantees:**

- **Atomic advance:** A single `MERGE` writes the new watermark only after every signal export in the run returned `ExportOutcome.SUCCESS`. Partial batches never advance the watermark.
- **Exact retry:** On any terminal transport failure the watermark is held unchanged, so the next scheduled run reads the same `(watermark, batch_end_next]` window — where `batch_end_next > batch_end` — and replays the previously failed rows along with anything newly arrived.
- **No transaction around OTLP:** The OTLP/gRPC call is deliberately performed **outside** of any Snowflake transaction. The watermark MERGE runs only after export success; the Event Table itself is read-only for this app, so there is nothing to "roll back" on failure.

#### Rule ET-8: Handle `WATERMARK_EXPIRED` Automatically

`CHANGES` uses Snowflake time travel. If the watermark is older than the available time-travel window (minimum 1 day on Standard / Enterprise Edition), Snowflake raises `Time travel data is not available for table ... The requested time is either too far in the past or before table creation`. The collector **must** catch this specific error, reset the watermark, and resume on the next scheduled run:

```python
def _is_time_travel_expired(exc) -> bool:
    msg = str(exc)
    return "Time travel data is not available" in msg

# on catch:
reset_watermark(session, source_name,
                CURRENT_TIMESTAMP() - INTERVAL :reset_buffer_seconds SECOND)
record_health(source_name, "watermark_reset", 1,
              {"error_code": "WATERMARK_EXPIRED"})
```

`reset_buffer_seconds` (config key: `event_table.watermark_reset_buffer_seconds`, default `60`) keeps the new watermark a safe distance behind `CURRENT_TIMESTAMP()` so the next run's `CHANGES(...) AT/END` window lands inside the time-travel retention. The reset is recorded in `_metrics.pipeline_health` with `watermark_reset = 1` and a known, finite data gap is accepted for that recovery cycle.

#### Rule ET-9: Diagnose `CHANGE_TRACKING_DISABLED` on Custom Views

For consumer-owned custom views, `CHANGES` returns the error `Change tracking is not enabled on the object` if the consumer has not run `ALTER VIEW <view> SET CHANGE_TRACKING = TRUE`. The collector detects this, records `CHANGE_TRACKING_DISABLED` in `_metrics.pipeline_health`, and pauses the source until the consumer remediates. The Streamlit governance page surfaces the exact remediation command — the app never attempts to enable tracking itself because that requires ownership of the view and its underlying tables.

### ACCOUNT_USAGE Pipeline Rules (Watermark + Overlap + `QUALIFY`)

#### Rule AU-1: Filter by Time with Overlap Window and Explicit `batch_end`

```sql
WHERE <timestamp_col> > :watermark - INTERVAL :overlap_minutes MINUTE
  AND <timestamp_col> <= :batch_end
```

`:batch_end` is captured once per run as `CURRENT_TIMESTAMP()` (optionally minus a small `lag_buffer` if the documented max latency requires it). The overlap window re-scans past the watermark to catch late-arriving rows that ACCOUNT_USAGE materializes asynchronously.

#### Rule AU-2: Dedup with `QUALIFY` Using Verified Natural Keys

```sql
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY QUERY_ID
    ORDER BY START_TIME DESC
) = 1
```

Dedup is mandatory for ACCOUNT_USAGE because the overlap window intentionally re-reads rows from previous polls.

#### Rule AU-3: Source-Specific Lag Buffers and Overlap Defaults

| Source | Timestamp Column | Max Latency | Default Overlap | Recommended Lag Buffer |
|---|---|---|---|---|
| `QUERY_HISTORY` | `START_TIME` | 45 minutes | 50 minutes | 67 minutes |
| `LOGIN_HISTORY` | `EVENT_TIMESTAMP` | 120 minutes | 132 minutes | 180 minutes |
| `ACCESS_HISTORY` | `QUERY_START_TIME` | 180 minutes | 198 minutes | 270 minutes |

Overlap defaults: `documented_max_latency × 1.1`. Lag buffer: `documented_max_latency × 1.5`. Both are configurable per source via `_internal.config`.

#### Rule AU-4: One Query Per Source, Extract and Cast Server-Side

Same typed-extraction principle as ET-4. Each ACCOUNT_USAGE source is queried independently — never join wide AU views.

#### Rule AU-5: Materialize via `to_pandas_batches()` Only

Same as ET-6. Never use `collect()` for bulk export.

#### Rule AU-6: Advance Watermark Only on Full Export Success (Hold-on-Failure)

Same semantics as ET-7: on success, `MERGE` the new watermark (`= :batch_end`) into `_internal.export_watermarks`; on terminal transport failure, leave the watermark untouched so the next scheduled run repeats the same window plus any freshly materialized ACCOUNT_USAGE rows.

### Shared Rules (Both Pipelines)

#### Rule S-1: Never Use `SELECT *` in Production Extraction Queries

Always project only the needed columns with explicit type casts.

#### Rule S-2: Push All Relational Work to Snowflake Engine

No Python-side filtering, deduplication, joins, or type casting. The Python layer only serializes and exports.

#### Rule S-3: Unified Watermark State, Per-Source

Both pipelines share the same `_internal.export_watermarks` table. Each `source_name` (e.g. `telemetry_events`, `ai_observability_events`, `query_history`) has exactly one watermark row. The only differences between the two pipelines are the incremental-read primitive used on the wire (`CHANGES` vs `WHERE + QUALIFY`) and the config-key family (`event_table.*` vs `source.<name>.overlap_minutes`).

---

## 8. Per-Signal Extraction Templates

### Event Table Pipeline (`CHANGES` + Self-Managed Watermark)

Unless otherwise noted, the templates below are shown in **relay mode** because they preserve full `RECORD_ATTRIBUTES` and `RESOURCE_ATTRIBUTES`. For production implementations where the exported attribute set is fully known, prefer a lean variant that omits those full `OBJECT` columns and exports only the typed scalar extracts.

All event-table templates read from the source object (event table or consumer-owned view with `CHANGE_TRACKING = TRUE`) via `CHANGES(INFORMATION => APPEND_ONLY) AT(TIMESTAMP => :watermark) END(TIMESTAMP => :batch_end)`. No `TIMESTAMP >= ...` predicates are needed — `CHANGES` is the cursor. `:watermark` and `:batch_end` are identical across all per-signal queries in a single run. Entity discrimination (`snow.executable.type` filter) is applied to all queries using normalized comparisons. No `QUALIFY` dedup is required.

#### 8.1 SPAN Extraction (Event Table `CHANGES`)

```sql
SELECT
    TRACE:"trace_id"::STRING              AS trace_id,
    TRACE:"span_id"::STRING               AS span_id,
    RECORD:"name"::STRING                 AS span_name,
    RECORD:"kind"::STRING                 AS span_kind,
    RECORD:"parent_span_id"::STRING       AS parent_span_id,
    RECORD:"status":"code"::STRING        AS status_code,
    RECORD:"status":"message"::STRING     AS status_message,
    TIMESTAMP                             AS end_time,
    START_TIMESTAMP                       AS start_time,
    RESOURCE_ATTRIBUTES:"db.user"::STRING AS db_user,
    RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING AS exec_type,
    RESOURCE_ATTRIBUTES:"snow.executable.name"::STRING AS exec_name,
    RESOURCE_ATTRIBUTES:"snow.query.id"::STRING AS query_id,
    RESOURCE_ATTRIBUTES:"snow.warehouse.name"::STRING AS warehouse_name,
    RESOURCE_ATTRIBUTES:"snow.database.name"::STRING AS database_name,
    RESOURCE_ATTRIBUTES:"snow.schema.name"::STRING AS schema_name,
    RESOURCE_ATTRIBUTES:"telemetry.sdk.language"::STRING AS sdk_language,
    RECORD_ATTRIBUTES,
    RESOURCE_ATTRIBUTES
FROM <source>
CHANGES(INFORMATION => APPEND_ONLY)
  AT(TIMESTAMP => :watermark)
  END(TIMESTAMP => :batch_end)
WHERE RECORD_TYPE = 'SPAN'
  AND UPPER(RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING)
      IN ('PROCEDURE', 'FUNCTION', 'QUERY', 'SQL', 'STATEMENT')
```

#### 8.2 SPAN_EVENT Extraction (Event Table `CHANGES`)

```sql
SELECT
    TRACE:"trace_id"::STRING              AS trace_id,
    TRACE:"span_id"::STRING               AS span_id,
    RECORD:"name"::STRING                 AS event_name,
    TIMESTAMP                             AS event_time,
    RECORD_ATTRIBUTES:"exception.message"::STRING    AS exception_message,
    RECORD_ATTRIBUTES:"exception.type"::STRING       AS exception_type,
    RECORD_ATTRIBUTES:"exception.stacktrace"::STRING AS exception_stacktrace,
    RECORD_ATTRIBUTES:"exception.escaped"::BOOLEAN   AS exception_escaped,
    RECORD_ATTRIBUTES,
    RESOURCE_ATTRIBUTES
FROM <source>
CHANGES(INFORMATION => APPEND_ONLY)
  AT(TIMESTAMP => :watermark)
  END(TIMESTAMP => :batch_end)
WHERE RECORD_TYPE = 'SPAN_EVENT'
  AND UPPER(RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING)
      IN ('PROCEDURE', 'FUNCTION', 'QUERY', 'SQL', 'STATEMENT')
```

**Note:** SPAN_EVENT rows share the same entity discrimination attribute (`snow.executable.type`) as their parent SPAN, so the same filter applies. Because this query uses the same `:watermark` and `:batch_end` as the SPAN query, parent-event correlation can be done in-memory on `(trace_id, span_id)` without a Snowflake-side join.

#### 8.3 LOG Extraction (Event Table `CHANGES`)

```sql
SELECT
    TIMESTAMP                             AS log_time,
    VALUE::STRING                         AS message,
    RECORD:"severity_text"::STRING        AS severity_text,
    RECORD:"severity_number"::NUMBER      AS severity_number,
    SCOPE:"name"::STRING                  AS scope_name,
    RECORD_ATTRIBUTES:"log.iostream"::STRING       AS log_iostream,
    RECORD_ATTRIBUTES:"code.filepath"::STRING      AS code_filepath,
    RECORD_ATTRIBUTES:"code.function"::STRING      AS code_function,
    RECORD_ATTRIBUTES:"code.lineno"::NUMBER        AS code_lineno,
    RECORD_ATTRIBUTES:"code.namespace"::STRING     AS code_namespace,
    RECORD_ATTRIBUTES:"thread.id"::NUMBER          AS thread_id,
    RECORD_ATTRIBUTES:"thread.name"::STRING        AS thread_name,
    RECORD_ATTRIBUTES:"exception.message"::STRING  AS exception_message,
    RECORD_ATTRIBUTES:"exception.type"::STRING     AS exception_type,
    RECORD_ATTRIBUTES:"exception.stacktrace"::STRING AS exception_stacktrace,
    RECORD_ATTRIBUTES:"exception.escaped"::BOOLEAN AS exception_escaped,
    RECORD_ATTRIBUTES,
    RESOURCE_ATTRIBUTES
FROM <source>
CHANGES(INFORMATION => APPEND_ONLY)
  AT(TIMESTAMP => :watermark)
  END(TIMESTAMP => :batch_end)
WHERE RECORD_TYPE = 'LOG'
  AND UPPER(RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING)
      IN ('PROCEDURE', 'FUNCTION', 'QUERY', 'SQL', 'STATEMENT')
```

#### 8.4 METRIC Extraction (Event Table `CHANGES`)

```sql
SELECT
    TIMESTAMP                             AS metric_time,
    START_TIMESTAMP                       AS metric_start_time,
    RECORD:"metric":"name"::STRING        AS metric_name,
    RECORD:"metric":"description"::STRING AS metric_description,
    RECORD:"metric":"unit"::STRING        AS metric_unit,
    RECORD:"metric_type"::STRING          AS metric_type,
    RECORD:"value_type"::STRING           AS value_type,
    RECORD:"aggregation_temporality"::STRING AS aggregation_temporality,
    RECORD:"is_monotonic"::BOOLEAN        AS is_monotonic,
    VALUE                                 AS metric_value,
    RECORD_ATTRIBUTES,
    RESOURCE_ATTRIBUTES
FROM <source>
CHANGES(INFORMATION => APPEND_ONLY)
  AT(TIMESTAMP => :watermark)
  END(TIMESTAMP => :batch_end)
WHERE RECORD_TYPE = 'METRIC'
  AND UPPER(RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING)
      IN ('PROCEDURE', 'FUNCTION', 'QUERY', 'SQL', 'STATEMENT')
```

Note: `VALUE` is kept as VARIANT because its concrete type depends on `metric_type` (DECIMAL for gauges, INTEGER for sums, OBJECT for histograms).

### AI Observability Pipeline (`CHANGES` + Self-Managed Watermark)

AI observability events reside in a separate table (`SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS`) and do not require entity discrimination filtering (the entire table is AI-specific). The same `CHANGES(...) AT/END` primitive applies.

#### 8.5 AI Observability SPAN Extraction (`CHANGES`)

```sql
SELECT
    TRACE:"trace_id"::STRING              AS trace_id,
    TRACE:"span_id"::STRING               AS span_id,
    RECORD:"name"::STRING                 AS span_name,
    RECORD:"kind"::STRING                 AS span_kind,
    RECORD:"parent_span_id"::STRING       AS parent_span_id,
    RECORD:"status":"code"::STRING        AS status_code,
    TIMESTAMP                             AS end_time,
    START_TIMESTAMP                       AS start_time,
    RECORD_ATTRIBUTES:"ai.observability.span_type"::STRING AS span_type,
    RECORD_ATTRIBUTES:"snow.ai.observability.object.name"::STRING AS agent_name,
    RECORD_ATTRIBUTES:"snow.ai.observability.object.type"::STRING AS object_type,
    RECORD_ATTRIBUTES:"snow.ai.observability.run.name"::STRING AS run_name,
    RECORD_ATTRIBUTES:"ai.observability.record_id"::STRING AS record_id,
    RECORD_ATTRIBUTES,
    RESOURCE_ATTRIBUTES
FROM SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS
CHANGES(INFORMATION => APPEND_ONLY)
  AT(TIMESTAMP => :watermark)
  END(TIMESTAMP => :batch_end)
WHERE RECORD_TYPE = 'SPAN'
```

### Collector Run Structure (Event Table + AI Obs)

A single scheduled run executes the per-signal `CHANGES(...) AT/END` queries, exports them via OTLP, and only **then** advances the watermark with a single `MERGE`. No Snowflake transaction is wrapped around the OTLP call — the Event Table is read-only for this app, and the watermark MERGE is the only state change. The `WATERMARK_EXPIRED` branch is the sole exception path:

```python
# Collector SP pseudocode (event_table_collector)
source_name = "telemetry_events"       # or "ai_observability_events" / custom view FQN
watermark   = read_watermark(session, source_name)
batch_end   = session.sql("SELECT CURRENT_TIMESTAMP()").collect()[0][0]

try:
    # One lazily-evaluated Snowpark DataFrame per signal type, all pinned to the
    # same [watermark, batch_end] window.
    spans_df   = session.sql(SPAN_SQL,       params=[watermark, batch_end])
    events_df  = session.sql(SPAN_EVENT_SQL, params=[watermark, batch_end])
    logs_df    = session.sql(LOG_SQL,        params=[watermark, batch_end])
    metrics_df = session.sql(METRIC_SQL,     params=[watermark, batch_end])

    outcomes = []
    for df, mapper, exporter in (
        (spans_df,   span_mapper,   span_exporter),
        (events_df,  span_mapper,   span_exporter),   # merged into parent spans
        (logs_df,    log_mapper,    log_exporter),
        (metrics_df, metric_mapper, metric_exporter),
    ):
        for chunk in df.to_pandas_batches():
            outcomes.append(exporter.export(mapper(chunk)))

except SnowparkSQLException as e:
    if _is_time_travel_expired(e):
        # Rule ET-8: WATERMARK_EXPIRED self-heal.
        reset_watermark(session, source_name,
                        batch_end - timedelta(seconds=reset_buffer_seconds))
        record_health(session, source_name, "watermark_reset", 1,
                      {"error_code": "WATERMARK_EXPIRED"})
        return "WATERMARK_RESET"
    raise

if all(o == ExportOutcome.SUCCESS for o in outcomes):
    update_watermark(session, source_name, batch_end)   # MERGE to :batch_end
else:
    # Rule ET-7: hold watermark for exact retry on the next scheduled run.
    record_health(session, source_name, "export_failed", 1,
                  {"error_code": classify_grpc_status(outcomes)})
```

**Consistency guarantee:** Every per-signal query is a `CHANGES(...) AT(:watermark) END(:batch_end)` read against the same half-open time-travel window. Snowflake's time-travel engine returns a single consistent snapshot for that window, so the four per-signal result sets cover exactly the same set of underlying rows — enabling in-memory `(trace_id, span_id)` correlation between SPAN and SPAN_EVENT without a Snowflake-side join. Failed runs leave the watermark untouched, so the next run reads `(watermark, batch_end_next]` and replays anything that failed along with anything newly arrived.

---

## 9. SQL vs Snowpark Decision

This section is intentionally aligned with the project rules in `snowflake-sql-rules.mdc` and `snowflake-snowpark-rules.mdc`.

### 9.1 Prefer Plain SQL for Single-Step Relational Extraction

Use `session.sql(...)` when the prep logic is one static relational statement:

- `CHANGES(...) AT/END` read with signal-type filter + entity discrimination (Event Table pipeline)
- watermark time-window read with overlap + dedup (ACCOUNT_USAGE pipeline)
- explicit projection with semi-structured extraction and casting

This is the best fit for most production export queries in this project because:

- the logic is single-step and relational
- SQL path syntax is clearer than equivalent Snowpark expressions for `OBJECT` / `VARIANT` extracts
- `CHANGES(...) AT/END` is a SQL-native clause — the equivalent Snowpark expression adds no value for a single static read
- `QUALIFY` (for ACCOUNT_USAGE dedup) is first-class in SQL and keeps dedup readable

**Event Table `CHANGES` example:**

```sql
session.sql("""
    SELECT
        TRACE:"trace_id"::STRING AS trace_id,
        TRACE:"span_id"::STRING  AS span_id,
        RECORD:"name"::STRING    AS span_name,
        RECORD:"kind"::STRING    AS span_kind,
        TIMESTAMP                AS end_time,
        START_TIMESTAMP          AS start_time,
        RECORD_ATTRIBUTES,
        RESOURCE_ATTRIBUTES
    FROM {source}
    CHANGES(INFORMATION => APPEND_ONLY)
      AT(TIMESTAMP => :watermark)
      END(TIMESTAMP => :batch_end)
    WHERE RECORD_TYPE = 'SPAN'
      AND UPPER(RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING)
          IN ('PROCEDURE', 'FUNCTION', 'QUERY', 'SQL', 'STATEMENT')
""", params=[watermark, batch_end])
```

**ACCOUNT_USAGE watermark example:**

```sql
session.sql("""
    SELECT QUERY_ID, QUERY_TYPE, START_TIME, END_TIME, ...
    FROM {source_name}
    WHERE START_TIME >  :watermark - INTERVAL :overlap MINUTE
      AND START_TIME <= :batch_end
    QUALIFY ROW_NUMBER() OVER (PARTITION BY QUERY_ID ORDER BY START_TIME DESC) = 1
""", params=[watermark, overlap, batch_end])
```

### 9.2 Use Snowpark DataFrames for Composed, Reusable Pipelines

Use Snowpark DataFrames only when composition improves maintainability without moving relational work into Python:

- reusable upstream filters
- programmatic source selection (switching between configured Event Table / view FQN and an ACCOUNT_USAGE view name)
- per-signal branches built from a common base DataFrame
- reusable extraction helpers shared across collectors

When using Snowpark:

- chain operations lazily
- prefer `col("...")["field"].cast("string").alias("...")`
- keep a consistent column-access style
- use a single terminal action at the boundary, typically `to_pandas_batches()`
- do not call `collect()` on large export paths

**`CHANGES`-based Snowpark example:**

The `CHANGES` clause itself is still expressed in SQL (there is no first-class Snowpark DataFrame API for it); compose the per-signal projection and filter chain on top of that SQL base:

```python
from snowflake.snowpark.functions import col, upper

base_sql = """
    SELECT TRACE, RECORD, RECORD_TYPE, TIMESTAMP, START_TIMESTAMP,
           RECORD_ATTRIBUTES, RESOURCE_ATTRIBUTES
    FROM {source}
    CHANGES(INFORMATION => APPEND_ONLY)
      AT(TIMESTAMP => :watermark)
      END(TIMESTAMP => :batch_end)
"""
base_df = session.sql(base_sql, params=[watermark, batch_end])

spans_df = (
    base_df
    .filter(col("RECORD_TYPE") == "SPAN")
    .filter(
        upper(col("RESOURCE_ATTRIBUTES")["snow.executable.type"].cast("string"))
        .isin("PROCEDURE", "FUNCTION", "QUERY", "SQL", "STATEMENT")
    )
    .select(
        col("TRACE")["trace_id"].cast("string").alias("trace_id"),
        col("TRACE")["span_id"].cast("string").alias("span_id"),
        col("RECORD")["name"].cast("string").alias("span_name"),
        col("RECORD")["kind"].cast("string").alias("span_kind"),
        col("TIMESTAMP").alias("end_time"),
        col("START_TIMESTAMP").alias("start_time"),
        col("RECORD_ATTRIBUTES"),
        col("RESOURCE_ATTRIBUTES"),
    )
)

for chunk in spans_df.to_pandas_batches():
    export_spans(chunk)
```

Prefer Snowpark only when the composition actually pays for itself (shared base DataFrame across all four signal types, reusable helpers). For a single per-signal query, plain SQL is simpler and equally efficient.

### 9.3 Hard Rules

Regardless of whether prep is written as SQL or Snowpark:

- never use `SELECT *` in production extraction queries
- for Event Table sources: use `CHANGES(INFORMATION => APPEND_ONLY) AT(TIMESTAMP => :watermark) END(TIMESTAMP => :batch_end)`; do not `SELECT ... FROM <source> WHERE TIMESTAMP > :watermark`
- for ACCOUNT_USAGE sources: use `WHERE <timestamp_col> > :watermark - INTERVAL :overlap MINUTE AND <timestamp_col> <= :batch_end` plus `QUALIFY ROW_NUMBER() ... = 1`
- use the **same `:watermark` and `:batch_end`** across every per-signal query in the same run
- advance the watermark only on full export success; hold it unchanged on terminal failure
- push entity discrimination and `RECORD_TYPE` filtering down before materialization
- cast hot-path semi-structured fields server-side
- avoid Python-side filtering, deduplication, or joins
- use `to_pandas_batches()` as the bulk materialization boundary
- reserve `.collect()` for small control-flow queries only (config reads, watermark reads, `CURRENT_TIMESTAMP()`, `MERGE INTO _internal.export_watermarks`)

### 9.4 Where `QUALIFY` Lives

`QUALIFY` is needed only for ACCOUNT_USAGE sources (overlap-based dedup). For those queries, prefer SQL via `session.sql(...)` since `QUALIFY` is first-class in SQL and keeps dedup readable. Event Table `CHANGES(...) AT/END` reads do not need `QUALIFY` — the append-only change set over an immutable time-travel snapshot already guarantees uniqueness.

---

## 10. Runtime Compatibility

### Warm Runtime and Exporter Reuse

The current `app/python/otlp_export.py` caches exporters at module scope with idle eviction. Preparation queries must not assume cold starts. gRPC channels persist across task invocations on the same warehouse.

### Collector Run Lifecycle (`CHANGES` + Self-Managed Watermark)

Each scheduled task invocation runs a single pipeline function; no Snowflake transaction is wrapped around the OTLP network call (gRPC is not transactional). The ordering is:

1. `read_watermark(source_name)` from `_internal.export_watermarks` (single-row `.collect()`).
2. Compute `batch_end = SELECT CURRENT_TIMESTAMP()` (single-row `.collect()`).
3. Build one lazy Snowpark DataFrame / SQL query per signal type, each pinned to the **same** `[watermark, batch_end]` window via `CHANGES(INFORMATION => APPEND_ONLY) AT(TIMESTAMP => :watermark) END(TIMESTAMP => :batch_end)`.
4. Stream each per-signal query through `to_pandas_batches()` → mapper → `exporter.export(...)`.
5. If **all** per-signal exports succeed, `MERGE INTO _internal.export_watermarks SET watermark = :batch_end`.
6. If any per-signal export returns a terminal failure, leave the watermark unchanged (Rule ET-7 hold-on-failure) and record a `pipeline_health` entry. The next scheduled run will re-read the same `(watermark, batch_end_next]` window, replaying the failed rows together with anything newly arrived.

`CHANGES` provides Snowflake-side snapshot isolation for the half-open window: all per-signal queries see exactly the same set of underlying rows, even though they run outside a BEGIN/COMMIT envelope. This removes the need for a Snowflake transaction around export and eliminates the "COMMIT succeeded but export failed" data-loss window that a stream-based design would have.

### Watermark Lifecycle and `WATERMARK_EXPIRED` Self-Heal

`CHANGES` relies on Snowflake time travel. The minimum guaranteed time-travel window on Standard and Enterprise accounts is **1 day**, which the default 1-minute task cadence stays well inside. The collector must still handle the edge case where the watermark has fallen outside the time-travel window (for example, during a prolonged app upgrade or task suspension):

1. The `CHANGES(...) AT(:watermark)` query raises `SnowparkSQLException` with the substring `Time travel data is not available`.
2. The collector catches this specific error (`_is_time_travel_expired(e)`), resets the watermark to `CURRENT_TIMESTAMP() - event_table.watermark_reset_buffer_seconds`, and records `WATERMARK_EXPIRED` / `watermark_reset` in `_metrics.pipeline_health`.
3. The run exits cleanly (no export attempted). On the next scheduled run, the reset watermark is well inside the time-travel window and normal collection resumes — with a one-time, observable data gap.

Because the watermark is an app-owned row in `_internal.export_watermarks`, there is no "stale stream" object to drop and recreate. `WATERMARK_EXPIRED` recovery is a value update, not a DDL operation.

### Initial Seeding

When a source is enabled for the first time, its watermark row is inserted with `watermark = CURRENT_TIMESTAMP() - event_table.initial_seed_buffer_seconds` (default: 60 seconds). This small backward offset guarantees the first `CHANGES(...) AT/END` window is non-empty even on a quiet account and avoids reading an unbounded historical backlog.

### Custom View Change Tracking

`CHANGES` requires `CHANGE_TRACKING = TRUE` on the target object. The app cannot enable this on consumer-owned custom views. When the flag is off, the `CHANGES` query returns `Change tracking is not enabled on the object`; the collector catches this, records `CHANGE_TRACKING_DISABLED` in `_metrics.pipeline_health`, and surfaces it in the health dashboard so the consumer can run `ALTER VIEW <view> SET CHANGE_TRACKING = TRUE`. The source stays paused (watermark held) until remediated.

### Package Availability (Verified Live)

All required packages are in the Snowflake Anaconda channel at compatible versions:

| Package | Latest Available |
|---|---|
| `grpcio` | 1.78.0 |
| `protobuf` | 6.33.5 |
| `opentelemetry-api` | 1.38.0 |
| `opentelemetry-sdk` | 1.38.0 |
| `opentelemetry-exporter-otlp-proto-grpc` | 1.38.0 |
| `opentelemetry-proto` | 1.38.0 |

No manual bundling is required.

---

## 11. Limits and Constraints (from Official Docs)

| Constraint | Value | Source |
|---|---|---|
| Max span events per span | 128 | Python drops FIFO; Java/JS/Scala/Snowflake Scripting drop new events at limit |
| Max span attributes per span | 128 | Additional attributes silently dropped |
| `db.query.text` max length | 1024 characters | Truncated by Snowflake |
| Trace events emitted only after execution completes | If execution unit fails before completion, events may not be emitted | Official docs |
| `dropped_*_count` not set for JavaScript | JavaScript OTel SDK does not report dropped counts | Official docs |
| UDFs may produce multiple spans per call | Snowflake executes UDFs on multiple threads; each thread gets its own span_id with shared trace_id | Official docs |
| Streamlit: one span per user session | Single span captures entire session | Official docs |
| Metrics only from Java and Python handlers | JavaScript, Scala, Snowflake Scripting do NOT emit metrics | Official docs |
| Event table replication not supported | Event tables in primary databases are skipped during replication | Official docs |
| SQL tracing NOT supported in Native Apps | "SQL statements in a Snowflake Native App" explicitly listed as unsupported | Official docs |
| UDF log messages emitted per input row | Large tables can produce enormous log volumes | Official docs |

**Critical for our pipeline:** SQL tracing is not supported in Native Apps. This means our own app's SQL statements will NOT produce trace data in the event table. We only export the consumer's telemetry, not our own.

---

## 12. Configuration Dependencies

These Snowflake parameters control what data appears in event tables. The export pipeline must document these as prerequisites for consumers.

| Parameter | Effect | Default | Required For |
|---|---|---|---|
| `TRACE_LEVEL` | Controls trace event verbosity | `OFF` | Must be `ALWAYS` or `ON_EVENT` for any trace data to appear |
| `LOG_LEVEL` | Controls log message verbosity | varies | Must be `ERROR` or more verbose to capture unhandled exceptions as logs |
| `METRIC_LEVEL` | Controls auto-instrumented resource metrics | `NONE` | Must be `ALL` to emit container/process metrics |
| `ENABLE_UNHANDLED_EXCEPTIONS_REPORTING` | Controls automatic exception logging | `true` | Set to `false` to suppress sensitive data in exception logs |
| `SQL_TRACE_QUERY_TEXT` | Includes SQL text in trace data | `OFF` | Must be `ON` (requires ACCOUNTADMIN) for `db.query.text` attribute |
| `EVENT_TABLE` | Directs telemetry to specific event table | Account default | Can be set per-database (takes precedence over account-level) |

**For our Streamlit UI:** The "Telemetry Sources" or "Configuration" page should inform consumers which parameters to set for full telemetry visibility.

---

## 13. Access Patterns and Correlation

### SPAN ↔ SPAN_EVENT Correlation (Event Table `CHANGES`)

SPAN_EVENT rows share the same `trace_id` AND `span_id` as their parent SPAN.

**For export:** do **not** join `SPAN` and `SPAN_EVENT` in SQL. Query them independently via two `CHANGES(INFORMATION => APPEND_ONLY) AT(:watermark) END(:batch_end)` reads (per Rule ET-5), then correlate during Python serialization by matching `(trace_id, span_id)` in-memory. This avoids a self-join on the source object.

Because both queries use the **same** `:watermark` and `:batch_end` bounds, Snowflake's time-travel engine returns a single consistent snapshot over the same half-open window for both signal types — no rows can appear in one per-signal result set but not the other.

### trace_id Groups All Spans in a Query

All spans within a single query execution share the same `trace_id`. For export, treat this as a grouping concept during serialization.

### Event Table Access Roles

| Role | Capabilities |
|---|---|
| `SNOWFLAKE.EVENTS_VIEWER` | SELECT on EVENTS_VIEW |
| `SNOWFLAKE.EVENTS_ADMIN` | SELECT, TRUNCATE, DELETE on default event table + SELECT on EVENTS_VIEW + RAP management |

Row access policies can be applied to EVENTS_VIEW via `SNOWFLAKE.TELEMETRY.ADD_ROW_ACCESS_POLICY_ON_EVENTS_VIEW()` (Enterprise Edition, requires EVENTS_ADMIN).

### Incremental-Read Primitive by Source Type

The app does **not** create Snowflake streams on any source. All Event Table / view sources are read via `CHANGES(INFORMATION => APPEND_ONLY) AT/END`, and all ACCOUNT_USAGE sources are read via watermark + overlap + `QUALIFY`:

| User Selection | Incremental-read primitive | Notes |
|---|---|---|
| Default Event Table (`SNOWFLAKE.TELEMETRY.EVENTS`) | `CHANGES(INFORMATION => APPEND_ONLY) AT(TIMESTAMP => :watermark) END(TIMESTAMP => :batch_end)` | `CHANGE_TRACKING` is on by default for Snowflake-managed Event Tables. No DDL required from app or consumer. |
| Consumer's custom view over Event Table | `CHANGES(INFORMATION => APPEND_ONLY) AT(TIMESTAMP => :watermark) END(TIMESTAMP => :batch_end)` | Consumer must run `ALTER VIEW <view> SET CHANGE_TRACKING = TRUE` first. If the flag is off, the collector records `CHANGE_TRACKING_DISABLED` in `_metrics.pipeline_health` and pauses the source. |
| `SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS` | `CHANGES(INFORMATION => APPEND_ONLY) AT(TIMESTAMP => :watermark) END(TIMESTAMP => :batch_end)` | Treated as a standard Event Table source. Current live data in this account is `SPAN` + `LOG` only. |
| Default ACCOUNT_USAGE view | `WHERE <ts_col> > :watermark - INTERVAL :overlap MINUTE AND <ts_col> <= :batch_end` + `QUALIFY ROW_NUMBER() OVER (PARTITION BY <natural_key> ORDER BY <ts_col> DESC) = 1` | `CHANGES` is not supported on ACCOUNT_USAGE views. |
| Consumer's custom view over ACCOUNT_USAGE | Same watermark + overlap + `QUALIFY` pattern as above | `CHANGES` is not supported on ACCOUNT_USAGE views. |

### Watermark Naming Convention

Watermarks live in `_internal.export_watermarks` keyed by `source_name`. Each enabled source has exactly one row. Suggested `source_name` values:

- `telemetry_events` — default Event Table
- `ai_observability_events` — `SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS`
- `<fully_qualified_view_name>` — consumer's custom view (Event Table or ACCOUNT_USAGE)
- `query_history`, `login_history`, `access_history` — default ACCOUNT_USAGE views

There are no Snowflake stream objects to namespace, so there is no opportunity for the app to conflict with any consumer-owned stream on the same source.

### Custom Event Tables

Event tables can be associated per-database (`ALTER DATABASE ... SET EVENT_TABLE = ...`). Database-level takes precedence over account-level. The consumer's setup determines which event table the app reads from.

---

## 14. Behavioral Notes for Export Pipeline

### Custom Spans

Users can create custom spans via the OpenTelemetry API in Python/Java/JavaScript/Scala handlers. Custom spans:
- inherit `trace_id` from the Snowflake auto-instrumented parent span
- set `parent_span_id` linking back to the auto-instrumented span
- use `SPAN_KIND_INTERNAL`
- have user-defined names (not following Snowflake naming patterns)
- must be closed before the handler completes or data is lost

The export pipeline must handle these without assuming all spans follow the `snow.auto_instrumented` or SQL-statement naming patterns.

### Metric Language Support Matrix

| Language | Metrics Supported | Metric Semantics |
|---|---|---|
| Java | Yes | JVM metrics shared across all Java/Scala UDFs in same query. Memory = sum, CPU = average. |
| Python | Yes | Per-function metrics. UDF across processes: memory = sum, CPU = average. |
| JavaScript | No | N/A |
| Scala | No | N/A |
| Snowflake Scripting | No | N/A |

### Unhandled Exception Dual Capture

An unhandled exception can produce entries in BOTH of these:
1. A LOG row (if `LOG_LEVEL` ≥ `ERROR`)
2. A SPAN_EVENT row attached to the parent span (if `TRACE_LEVEL` = `ALWAYS` or `ON_EVENT`)

The export pipeline should handle both without producing duplicate error reports. The recommended approach: export span events as part of the span, and export exception logs independently as log records.

### `CHANGES` / Watermark Behavioral Notes

**Empty windows are the common case, not a failure mode:** A scheduled run that returns zero rows from every per-signal `CHANGES(...) AT/END` query is normal. The collector still advances the watermark to `:batch_end` because the empty set is a valid export outcome. On a quiet account, almost every 1-minute run is empty and cheap. There is no stream object that can fall behind during idle periods.

**Zero matching rows after filtering:** If a source returns rows from `CHANGES` but all are filtered out by `RECORD_TYPE` + entity discrimination (for example, all new rows are SPCS telemetry, not SQL/Snowpark), the collector still advances the watermark to `:batch_end`. The watermark tracks window progress, not per-signal row counts; nothing accumulates between runs because `CHANGES` re-reads the next window from time travel, not from an offset cursor.

**Prolonged export outage (OTLP unreachable, non-expired watermark):** While the watermark is still inside the time-travel window, the collector holds the watermark unchanged on each terminal failure (Rule ET-7) and records `export_failed` in `_metrics.pipeline_health`. The next scheduled run re-reads the same `(watermark, batch_end_next]` window and replays failed rows along with anything newly arrived. There is no unbounded backlog inside Snowflake — the retry window grows linearly with outage duration, which is a bounded cost because Event Table retention is finite.

**Prolonged task suspension (watermark falls outside time travel):** If the task is suspended (for example, during app upgrade) long enough for the watermark to fall outside the minimum 1-day time-travel window, the first `CHANGES(...) AT(:watermark)` query after resume raises `Time travel data is not available`. The collector self-heals per Rule ET-8: it resets the watermark to `CURRENT_TIMESTAMP() - event_table.watermark_reset_buffer_seconds`, records `WATERMARK_EXPIRED` / `watermark_reset` in `_metrics.pipeline_health`, and resumes on the next scheduled run with an observable, bounded data gap. No DDL is required to recover.

**Custom view change tracking lost (`CREATE OR REPLACE VIEW`):** If the consumer runs `CREATE OR REPLACE VIEW` on their custom view, `CHANGE_TRACKING` may be cleared on the replacement view. The next `CHANGES(...) AT/END` query returns `Change tracking is not enabled on the object`. The collector records `CHANGE_TRACKING_DISABLED` in `_metrics.pipeline_health` and pauses that source; the health dashboard instructs the consumer to re-enable change tracking with `ALTER VIEW <view> SET CHANGE_TRACKING = TRUE`. Once re-enabled, collection resumes from the held watermark with no stream recreation required — the recovery is a single DDL statement on the consumer side, not a coordinated stream drop / recreate on the app side.

---

## 15. Implementation Checklist

### Schema & Extraction
- [ ] Each Event Table signal type has a dedicated extraction query using `CHANGES(INFORMATION => APPEND_ONLY) AT(TIMESTAMP => :watermark) END(TIMESTAMP => :batch_end)`
- [ ] Each ACCOUNT_USAGE source has a dedicated extraction query with watermark + overlap + `QUALIFY` dedup
- [ ] Event Table queries filter by `RECORD_TYPE` and entity discrimination (`snow.executable.type`)
- [ ] Event Table queries do NOT include `TIMESTAMP > :watermark` predicates (the `CHANGES` clause is the cursor) and do NOT use `QUALIFY` dedup
- [ ] ACCOUNT_USAGE queries filter by time with overlap window and use `QUALIFY ROW_NUMBER()` dedup
- [ ] All per-signal queries in one collector run use the same `:watermark` and `:batch_end` bind values
- [ ] All hot-path semi-structured fields use `:"key"::TYPE` extraction
- [ ] `trace_id` and `span_id` are extracted from `TRACE`, not `RECORD`
- [ ] `status` is extracted as `RECORD:"status":"code"::STRING` (nested OBJECT with optional `message`)
- [ ] Metric names are extracted as `RECORD:"metric":"name"::STRING` (nested OBJECT)
- [ ] `dropped_attributes_count` preserved from SPAN and SPAN_EVENT RECORD
- [ ] SPAN_EVENT extraction includes `exception.stacktrace` and `exception.escaped`
- [ ] LOG extraction handles three populations: container, instrumented, and unhandled-exception
- [ ] Unhandled exception LOG `VALUE` = string `exception` (not the error message — that's in RECORD_ATTRIBUTES)
- [ ] EVENT extraction handles task, container, and Native App lifecycle subtypes

### Watermark Lifecycle (`CHANGES` + Self-Managed Watermark)
- [ ] `_internal.export_watermarks` has exactly one row per enabled source (keyed by `source_name`)
- [ ] Initial seed inserts `watermark = CURRENT_TIMESTAMP() - event_table.initial_seed_buffer_seconds` (default 60s)
- [ ] Each collector run reads `watermark` and computes `batch_end = SELECT CURRENT_TIMESTAMP()` once, then pins every per-signal query to the same window
- [ ] OTLP export runs **after** the lazy `CHANGES` queries materialize via `to_pandas_batches()` — no Snowflake transaction wraps the gRPC call
- [ ] Watermark advances via `MERGE INTO _internal.export_watermarks SET watermark = :batch_end` only when every per-signal export returns `SUCCESS`
- [ ] On terminal export failure, the watermark is held unchanged and a `pipeline_health` entry is recorded (Rule ET-7)
- [ ] Collector catches `SnowparkSQLException` containing `Time travel data is not available`, resets the watermark to `CURRENT_TIMESTAMP() - event_table.watermark_reset_buffer_seconds`, and records `WATERMARK_EXPIRED` / `watermark_reset` (Rule ET-8)
- [ ] Collector detects `Change tracking is not enabled on the object` and records `CHANGE_TRACKING_DISABLED` against the source (Rule ET-9); source stays paused until the consumer enables `CHANGE_TRACKING`
- [ ] No Snowflake stream objects are created anywhere in the app
- [ ] No `_staging.stream_offset_log` or equivalent offset table is used

### Sources & Access
- [ ] AI observability source (`SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS`) is read via its own watermark row and `CHANGES(...) AT/END`
- [ ] ACCOUNT_USAGE views use source-specific lag buffers and overlap windows
- [ ] SPAN ↔ SPAN_EVENT correlation uses `(trace_id, span_id)` matching during serialization
- [ ] Custom spans (user OTel API) handled without assuming Snowflake naming patterns

### Materialization
- [ ] Materialization uses `to_pandas_batches()` at the export boundary
- [ ] No `collect()` for bulk export
- [ ] No Python-side `RECORD_TYPE` or entity-discrimination filtering

### Convention & Relay
- [ ] Lean vs relay mode is chosen explicitly per source/query
- [ ] Full `RECORD_ATTRIBUTES` and `RESOURCE_ATTRIBUTES` preserved for relay mode
- [ ] `snow.application.consumer.*` and `snow.listing.*` resource attributes handled when present
- [ ] Exporter reuse is compatible with `app/python/otlp_export.py` warm-runtime model

### Consumer Documentation
- [ ] Streamlit UI documents required `TRACE_LEVEL`, `LOG_LEVEL`, `METRIC_LEVEL` settings
- [ ] Streamlit UI documents `SQL_TRACE_QUERY_TEXT` opt-in for SQL text capture
- [ ] Streamlit UI notes that SQL tracing is not supported within the Native App itself
- [ ] Streamlit UI instructs consumers to run `ALTER VIEW <view> SET CHANGE_TRACKING = TRUE` on any custom Event Table view selected as a source, and warns that `CREATE OR REPLACE VIEW` may clear the flag and require re-enabling it
- [ ] `CHANGE_TRACKING_DISABLED` and `WATERMARK_EXPIRED` states are surfaced with remediation guidance on the Observability health page

---

## 16. Discovery Queries Reference

These queries are for schema exploration and validation only. They are intentionally broader than production export queries and are the only place in this document where wider inspection patterns are acceptable.

> **Cost note:** Some of these discovery queries scan entire event tables and use `LATERAL FLATTEN`. On large production accounts, add a bounded time predicate such as `WHERE TIMESTAMP >= DATEADD('day', -7, CURRENT_TIMESTAMP())` before running them.

Re-run these if Snowflake adds new signal types or attribute keys:

```sql
-- Signal type distribution
SELECT RECORD_TYPE, COUNT(*) FROM <source> GROUP BY 1;

-- RECORD shape per signal type
SELECT RECORD_TYPE, OBJECT_KEYS(RECORD) FROM <source> GROUP BY 1, 2;

-- RECORD_ATTRIBUTES key catalog
SELECT RECORD_TYPE, f.key, COUNT(*)
FROM <source>, LATERAL FLATTEN(INPUT => RECORD_ATTRIBUTES, OUTER => TRUE) f
GROUP BY 1, 2 ORDER BY 1, 3 DESC;

-- RESOURCE_ATTRIBUTES key catalog
SELECT RECORD_TYPE, f.key, COUNT(*)
FROM <source>, LATERAL FLATTEN(INPUT => RESOURCE_ATTRIBUTES) f
GROUP BY 1, 2 ORDER BY 1, 3 DESC;

-- VALUE type per signal
SELECT RECORD_TYPE, TYPEOF(VALUE), COUNT(*)
FROM <source> GROUP BY 1, 2;

-- Status shape for spans
SELECT DISTINCT RECORD:"status" FROM <source> WHERE RECORD_TYPE = 'SPAN';

-- Span kind values
SELECT DISTINCT RECORD:"kind"::STRING FROM <source> WHERE RECORD_TYPE = 'SPAN';

-- Metric type/value_type combinations
SELECT DISTINCT RECORD:"metric_type"::STRING, RECORD:"value_type"::STRING
FROM <source> WHERE RECORD_TYPE = 'METRIC';
```
