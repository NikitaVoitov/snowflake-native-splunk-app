# Telemetry Preparation for Export

> **Audience:** Engineers implementing Snowflake-side data preparation for OTLP export stored procedures.
> **Status:** Verified from live Snowflake metadata (account `LFB71918`, 2026-04-05) and cross-referenced against official Snowflake documentation (13 pages scraped 2026-04-05).
> **Scope:** Exact field schemas, data types, extraction patterns, limits, configuration dependencies, and pushdown rules for every telemetry source.
> **Companion docs:** `grpc_research.md` (transport layer), `otel_semantic_conventions_snowflake_research.md` (convention mapping), `splunk_snowflake_native_app_vision.md` (architecture), `event_table_streams_governance_research.md` (stream creation & governance), `event_table_entity_discrimination_strategy.md` (entity filtering).

---

## 1. Canonical Sources (Verified Live)

| Source | Object | Pipeline | Access Pattern |
|---|---|---|---|
| Standard event table (base) | `SNOWFLAKE.TELEMETRY.EVENTS` | Event-driven | Stream on event table → Triggered task |
| Standard event table (view) | `SNOWFLAKE.TELEMETRY.EVENTS_VIEW` | — | Not a supported direct source for this app; live `CREATE STREAM` probe failed because `CHANGE_TRACKING` is not enabled and the app cannot enable it on the system view |
| Consumer custom view over ET | Consumer-created view over any ET | Event-driven | Stream on view (`APPEND_ONLY = TRUE`) → Triggered task |
| AI observability | `SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS` | Event-driven | Stream on event table → Triggered task |
| Query performance | `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` | Poll-based | Watermark + overlap + dedup (scheduled task) |
| Authentication | `SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY` | Poll-based | Watermark + overlap + dedup (scheduled task) |
| Data access governance | `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY` | Poll-based | Watermark + overlap + dedup (scheduled task) |

---

**Source-selection note:** Snowflake documentation supports streams on views, including secure views, in general. Our exclusion of `SNOWFLAKE.TELEMETRY.EVENTS_VIEW` is narrower: live metadata shows `CHANGE_TRACKING = OFF` for this system view, and a 2026-04-06 live probe failed with `Insufficient privileges to operate on stream source without CHANGE_TRACKING enabled 'EVENTS_VIEW'`.

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

This project uses a **dual-pipeline architecture**. Rules are split by pipeline type because event table sources and ACCOUNT_USAGE sources have fundamentally different data access patterns:

- **Event Table sources** (standard ET, consumer custom views, AI observability): **Stream-based reads**. No time-range predicates, no dedup — the stream acts as the cursor and surfaces only unconsumed rows. For custom views, use `APPEND_ONLY = TRUE`. For event tables, live validation also showed `APPEND_ONLY` mode is accepted, although the main `CREATE STREAM` syntax block does not show that parameter for `ON EVENT TABLE`.
- **ACCOUNT_USAGE sources** (QUERY_HISTORY, LOGIN_HISTORY, ACCESS_HISTORY): **Watermark-based polling** with overlap windows and `QUALIFY` dedup. Streams are not supported on ACCOUNT_USAGE views.

### Event Table Pipeline Rules (Stream-Based)

#### Rule ET-1: Read from the Stream, Not the Source Table

The collector reads from the stream object, which surfaces only rows inserted since the last consumption:

```sql
SELECT ... FROM <stream_name> WHERE RECORD_TYPE = 'SPAN'
```

No `TIMESTAMP >= :watermark` predicates. The stream already scopes to rows inserted since last consumption. The only predicates are `RECORD_TYPE` and entity discrimination.

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

Append-only streams on event tables guarantee each row appears exactly once. Do NOT add `QUALIFY ROW_NUMBER()` to event table extraction queries — it adds unnecessary window-function sort overhead with zero benefit.

**Exception:** If future Snowflake behavior or a specific edge case produces duplicate rows in the stream (not observed as of 2026-04), add dedup as a defensive measure at that time.

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
FROM <stream_name>
WHERE RECORD_TYPE = 'SPAN'
  AND UPPER(RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING)
      IN ('PROCEDURE', 'FUNCTION', 'QUERY', 'SQL', 'STATEMENT')
```

**Lean vs relay mode** applies here exactly as before:

- **Lean mode**: omit full `RECORD_ATTRIBUTES` and `RESOURCE_ATTRIBUTES`; export only the explicitly extracted typed columns. Use when the exported attribute set is fully known at build time.
- **Relay mode**: keep full `RECORD_ATTRIBUTES` and `RESOURCE_ATTRIBUTES` for convention-transparent forwarding of original attributes unknown at build time.

Prefer lean mode for well-known signal types. Use relay mode for event-table sources only when preserving the full attribute bag is a requirement.

#### Rule ET-5: One Query Per Signal Type

Do not mix `RECORD_TYPE` values in a single query. Each signal type has different RECORD/VALUE shapes. Issue separate queries per signal type against the same stream within the same transaction.

#### Rule ET-6: Materialize via `to_pandas_batches()` Only

```python
for chunk in df.to_pandas_batches():
    otlp_batch = serialize_to_otlp(chunk)
    exporter.export(otlp_batch)
```

Never use `collect()` for bulk export. Never use `to_pandas()` without bounding the result set.

#### Rule ET-7: Snapshot and Consume the Stream Atomically; Export After Commit

Materialize the per-signal snapshot and advance the stream offset within the same explicit transaction. Perform OTLP export only **after** that transaction commits:

```sql
BEGIN;
  -- 1. Materialize per-signal temp batches from the stream
  -- 2. Advance stream offset:
  INSERT INTO _staging.stream_offset_log(_OFFSET_CONSUMED_AT)
    SELECT CURRENT_TIMESTAMP() FROM <stream_name> WHERE 0 = 1;
COMMIT;

-- 3. Export the materialized batches outside the transaction
```

The zero-row INSERT references the stream (advancing the offset on commit) but writes zero actual rows. `_staging.stream_offset_log` is permanently empty.

**Transaction guarantees:**

- **Atomicity**: Offset advances only on successful COMMIT. If the SP crashes before COMMIT, the transaction rolls back and the stream offset stays put — the same data reappears on the next invocation.
- **Repeatable read**: Within the transaction, all queries to the same stream return identical data. The DataFrame reads and the zero-row INSERT see the same stream snapshot.
- **Validated consume pattern**: On 2026-04-06, a live scratch test confirmed that `INSERT INTO <single-column-log-table> SELECT CURRENT_TIMESTAMP() FROM <stream> WHERE 0 = 1` advances the stream offset while inserting zero rows.
- **Recommended OTLP interaction**: Keep blocking OTLP/gRPC I/O outside the stream transaction. This is an architectural recommendation based on Snowflake stream/task behavior and operational risk, not a documented Snowflake prohibition.
- **Failure handling (MVP)**: If export fails **after** the transaction commits, the event-table batch is already consumed. Log the failed batch to `_metrics.pipeline_health` and treat Event Table export as best-effort.

### ACCOUNT_USAGE Pipeline Rules (Watermark-Based)

#### Rule AU-1: Filter by Time with Overlap Window

```sql
WHERE START_TIME > :watermark - INTERVAL :overlap_minutes MINUTE
  AND START_TIME <= CURRENT_TIMESTAMP() - INTERVAL :lag_buffer MINUTE
```

The overlap window re-scans past the watermark to catch late-arriving rows. The lag buffer prevents reading rows still materializing in Snowflake.

#### Rule AU-2: Dedup with QUALIFY Using Verified Natural Keys

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

### Shared Rules (Both Pipelines)

#### Rule S-1: Never Use `SELECT *` in Production Extraction Queries

Always project only the needed columns with explicit type casts.

#### Rule S-2: Push All Relational Work to Snowflake Engine

No Python-side filtering, deduplication, joins, or type casting. The Python layer only serializes and exports.

---

## 8. Per-Signal Extraction Templates

### Event Table Pipeline (Stream-Based)

Unless otherwise noted, the templates below are shown in **relay mode** because they preserve full `RECORD_ATTRIBUTES` and `RESOURCE_ATTRIBUTES`. For production implementations where the exported attribute set is fully known, prefer a lean variant that omits those full `OBJECT` columns and exports only the typed scalar extracts.

All event table templates read from the **stream object** (not the source table/view). No time-range predicates are needed. Entity discrimination (`snow.executable.type` filter) is applied to all queries using normalized comparisons. No `QUALIFY` dedup is required (append-only stream behavior guarantees uniqueness for this design).

#### 8.1 SPAN Extraction (Event Table Stream)

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
FROM <stream_name>
WHERE RECORD_TYPE = 'SPAN'
  AND UPPER(RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING)
      IN ('PROCEDURE', 'FUNCTION', 'QUERY', 'SQL', 'STATEMENT')
```

#### 8.2 SPAN_EVENT Extraction (Event Table Stream)

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
FROM <stream_name>
WHERE RECORD_TYPE = 'SPAN_EVENT'
  AND UPPER(RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING)
      IN ('PROCEDURE', 'FUNCTION', 'QUERY', 'SQL', 'STATEMENT')
```

**Note:** SPAN_EVENT rows share the same entity discrimination attribute (`snow.executable.type`) as their parent SPAN, so the same filter applies.

#### 8.3 LOG Extraction (Event Table Stream)

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
FROM <stream_name>
WHERE RECORD_TYPE = 'LOG'
  AND UPPER(RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING)
      IN ('PROCEDURE', 'FUNCTION', 'QUERY', 'SQL', 'STATEMENT')
```

#### 8.4 METRIC Extraction (Event Table Stream)

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
FROM <stream_name>
WHERE RECORD_TYPE = 'METRIC'
  AND UPPER(RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING)
      IN ('PROCEDURE', 'FUNCTION', 'QUERY', 'SQL', 'STATEMENT')
```

Note: `VALUE` is kept as VARIANT because its concrete type depends on `metric_type` (DECIMAL for gauges, INTEGER for sums, OBJECT for histograms).

### AI Observability Pipeline (Stream-Based)

AI observability events reside in a separate table (`SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS`) and do not require entity discrimination filtering (the entire table is AI-specific).

#### 8.5 AI Observability SPAN Extraction (Stream)

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
FROM <ai_obs_stream_name>
WHERE RECORD_TYPE = 'SPAN'
```

### Stream Transaction Wrapper (Event Table + AI Obs)

All stream-based extraction queries execute within a single explicit transaction per pipeline invocation for **snapshot materialization + offset advancement**. OTLP export should occur after commit:

```python
# Collector SP pseudocode (event_table_collector)
session.sql("BEGIN").collect()

try:
    # Step 1: Snapshot each signal type into temp batches
    session.sql("CREATE OR REPLACE TEMP TABLE tmp_spans   AS SELECT ... FROM <stream> WHERE RECORD_TYPE = 'SPAN' AND ...").collect()
    session.sql("CREATE OR REPLACE TEMP TABLE tmp_events  AS SELECT ... FROM <stream> WHERE RECORD_TYPE = 'SPAN_EVENT' AND ...").collect()
    session.sql("CREATE OR REPLACE TEMP TABLE tmp_logs    AS SELECT ... FROM <stream> WHERE RECORD_TYPE = 'LOG' AND ...").collect()
    session.sql("CREATE OR REPLACE TEMP TABLE tmp_metrics AS SELECT ... FROM <stream> WHERE RECORD_TYPE = 'METRIC' AND ...").collect()

    # Step 2: Advance stream offset (Rule ET-7)
    session.sql("""
        INSERT INTO _staging.stream_offset_log(_OFFSET_CONSUMED_AT)
        SELECT CURRENT_TIMESTAMP() FROM <stream> WHERE 0 = 1
    """).collect()

    session.sql("COMMIT").collect()

except Exception:
    session.sql("ROLLBACK").collect()
    raise

# Step 3: Export after commit
for temp_name in ["tmp_spans", "tmp_events", "tmp_logs", "tmp_metrics"]:
    for chunk in session.table(temp_name).to_pandas_batches():
        serialize_and_export(chunk)
# On export failure here: log to _metrics.pipeline_health; do not expect replay in MVP
```

**Repeatable-read guarantee:** Within the transaction, all four signal-type queries see the same stream snapshot. The zero-row INSERT at the end advances the offset past exactly the rows that were materialized into the temp batches.

---

## 9. SQL vs Snowpark Decision

This section is intentionally aligned with the project rules in `snowflake-sql-rules.mdc` and `snowflake-snowpark-rules.mdc`.

### 9.1 Prefer Plain SQL for Single-Step Relational Extraction

Use `session.sql(...)` when the prep logic is one static relational statement:

- stream read with signal-type filter + entity discrimination (event table pipeline)
- watermark time-window read with overlap + dedup (ACCOUNT_USAGE pipeline)
- explicit projection with semi-structured extraction and casting

This is the best fit for most production export queries in this project because:

- the logic is single-step and relational
- SQL path syntax is clearer than equivalent Snowpark expressions for `OBJECT` / `VARIANT` extracts
- stream reads are simple `SELECT ... FROM <stream> WHERE ...` — no complex multi-step pipeline
- `QUALIFY` (for ACCOUNT_USAGE dedup) is first-class in SQL and keeps dedup readable

**Event Table stream example:**

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
    FROM {stream_name}
    WHERE RECORD_TYPE = 'SPAN'
      AND UPPER(RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING)
          IN ('PROCEDURE', 'FUNCTION', 'QUERY', 'SQL', 'STATEMENT')
""")
```

**ACCOUNT_USAGE watermark example:**

```sql
session.sql("""
    SELECT QUERY_ID, QUERY_TYPE, START_TIME, END_TIME, ...
    FROM {source_name}
    WHERE START_TIME > :watermark - INTERVAL :overlap MINUTE
      AND START_TIME <= CURRENT_TIMESTAMP() - INTERVAL :lag MINUTE
    QUALIFY ROW_NUMBER() OVER (PARTITION BY QUERY_ID ORDER BY START_TIME DESC) = 1
""")
```

### 9.2 Use Snowpark DataFrames for Composed, Reusable Pipelines

Use Snowpark DataFrames only when composition improves maintainability without moving relational work into Python:

- reusable upstream filters
- programmatic source selection (switching between stream name and AU view name)
- per-signal branches built from a common base DataFrame
- reusable extraction helpers shared across collectors

When using Snowpark:

- chain operations lazily
- prefer `col("...")["field"].cast("string").alias("...")`
- keep a consistent column-access style
- use a single terminal action at the boundary, typically `to_pandas_batches()`
- do not call `collect()` on large export paths

**Stream-based Snowpark example:**

```python
from snowflake.snowpark.functions import col, upper

base_df = session.table(stream_name)

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

**Note:** This Snowpark example omits the transaction wrapper for brevity. In production, all stream reads must be wrapped in `BEGIN`/`COMMIT` per Rule ET-7.

### 9.3 Hard Rules

Regardless of whether prep is written as SQL or Snowpark:

- never use `SELECT *` in production extraction queries
- for event table sources: read from the stream, not the source table/view
- for ACCOUNT_USAGE sources: filter by time first with overlap window
- push entity discrimination and `RECORD_TYPE` filtering down before materialization
- cast hot-path semi-structured fields server-side
- avoid Python-side filtering, deduplication, or joins
- use `to_pandas_batches()` as the bulk materialization boundary
- reserve `.collect()` for small control-flow queries only (config reads, watermark reads, `DESCRIBE STREAM`)

### 9.4 Where `QUALIFY` Lives

`QUALIFY` is needed only for ACCOUNT_USAGE sources (overlap-based dedup). For those queries, prefer SQL via `session.sql(...)` since `QUALIFY` is first-class in SQL and keeps dedup readable. Event table stream reads do not need `QUALIFY`.

---

## 10. Runtime Compatibility

### Warm Runtime and Exporter Reuse

The current `app/python/otlp_export.py` caches exporters at module scope with idle eviction. Preparation queries must not assume cold starts. gRPC channels persist across task invocations on the same warehouse.

### Stream Transaction Lifecycle

Each triggered task invocation should use a single explicit transaction for the **stream snapshot phase**:

1. `BEGIN` — opens the transaction, locks the stream for repeatable read
2. Snowpark/SQL reads from the stream (per signal type, with entity discrimination) and materializes temp batches
3. Zero-row INSERT to advance stream offset
4. `COMMIT` — atomically advances the stream offset
5. `to_pandas_batches()` on the temp batches → serialize → export via OTLP/gRPC

If the SP crashes at any point before COMMIT, the transaction rolls back and the stream offset remains unchanged. The next task invocation sees the same data. If the crash happens after COMMIT but before export completes, the stream has already advanced; this is an accepted MVP best-effort tradeoff for Event Table telemetry.

### Stream Staleness Prevention

The triggered task's `WHEN SYSTEM$STREAM_HAS_DATA()` condition serves a dual purpose:

1. **Triggering**: fires the task when new data arrives in the stream
2. **Staleness prevention**: when the stream is empty, `SYSTEM$STREAM_HAS_DATA()` returns `FALSE` and resets the staleness clock

If the stream has accumulated data but is not being consumed (export failures, task suspension), `SYSTEM$STREAM_HAS_DATA()` returns `TRUE` but does NOT prevent staleness. The `STALE_AFTER` timestamp from `DESCRIBE STREAM` must be monitored.

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

### SPAN ↔ SPAN_EVENT Correlation (Event Table Stream)

SPAN_EVENT rows share the same `trace_id` AND `span_id` as their parent SPAN.

**For export:** do **not** join `SPAN` and `SPAN_EVENT` in SQL. Query them independently from the stream (per Rule ET-5), then correlate during Python serialization by matching `(trace_id, span_id)` in-memory. This avoids a self-join on the stream.

Within a single transaction, the stream's repeatable-read isolation guarantees that both the SPAN and SPAN_EVENT queries see the same snapshot — no rows can appear in one but not the other.

### trace_id Groups All Spans in a Query

All spans within a single query execution share the same `trace_id`. For export, treat this as a grouping concept during serialization.

### Event Table Access Roles

| Role | Capabilities |
|---|---|
| `SNOWFLAKE.EVENTS_VIEWER` | SELECT on EVENTS_VIEW |
| `SNOWFLAKE.EVENTS_ADMIN` | SELECT, TRUNCATE, DELETE on default event table + SELECT on EVENTS_VIEW + RAP management |

Row access policies can be applied to EVENTS_VIEW via `SNOWFLAKE.TELEMETRY.ADD_ROW_ACCESS_POLICY_ON_EVENTS_VIEW()` (Enterprise Edition, requires EVENTS_ADMIN).

### Stream Creation by Source Type

| User Selection | Stream DDL | Notes |
|---|---|---|
| Default Event Table (`SNOWFLAKE.TELEMETRY.EVENTS`) | `CREATE STREAM ... ON EVENT TABLE <ref> [APPEND_ONLY = TRUE]` | Live 2026-04-06 probe accepted `APPEND_ONLY = TRUE` and `SHOW STREAMS` reported `APPEND_ONLY` mode, even though the primary syntax block omits this parameter for event tables |
| Consumer's custom view over Event Table | `CREATE STREAM ... ON VIEW <user_view_fqn> APPEND_ONLY = TRUE` | Valid when the view satisfies streams-on-views constraints. Creating the first stream can auto-enable change tracking only when the creator owns both the view and underlying tables; enabling it locks underlying objects |
| `SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS` | `CREATE STREAM ... ON EVENT TABLE <ref> [APPEND_ONLY = TRUE]` | Live 2026-04-06 probe succeeded. Current live data in this account is `SPAN` + `LOG` only |
| Default ACCOUNT_USAGE view | No stream — watermark-based polling | Streams not supported on ACCOUNT_USAGE views |
| Consumer's custom view over ACCOUNT_USAGE | No stream — watermark-based polling | Streams not supported on ACCOUNT_USAGE views |

### Stream Naming Convention

Streams use namespaced names: `_splunk_obs_stream_<source_name>` (e.g., `_splunk_obs_stream_telemetry_events`). This avoids conflicts if the consumer has their own streams on the same Event Table.

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

### Stream-Specific Behavioral Notes

**View-based stream false positives:** When the stream is created on a consumer's custom view over the event table, the triggered task fires on ANY insert to the underlying event table — regardless of the view's filter or the entity discrimination filter. Many task runs may read the stream, apply the `RECORD_TYPE` + entity discrimination filter, and find zero matching rows. This is expected behavior. The serverless task model minimizes cost for these empty runs.

**Stream consumption with zero matching rows:** If the stream has data but all rows are filtered out by `RECORD_TYPE` + entity discrimination (e.g., all new rows are SPCS telemetry, not SQL/Snowpark), the collector must still execute the zero-row INSERT + COMMIT to advance the stream offset. Otherwise, the same non-matching rows accumulate indefinitely and the stream never advances.

**Stream staleness during prolonged outage:** If the OTLP destination is unreachable for an extended period, the collector continues to advance the stream offset (logging failures to `_metrics.pipeline_health`). The stream never stalls. However, if the **task itself** is suspended (e.g., during app upgrade), the stream is not consumed and will eventually become stale after the data retention + extension window. Monitor `STALE_AFTER` via `DESCRIBE STREAM`.

**View breakage:** If the consumer runs `CREATE OR REPLACE VIEW` on their custom view (instead of `ALTER VIEW`), all streams on that view become stale and unrecoverable. The app must detect this (via `SHOW STREAMS` stale flag or stream read failure), mark the source as broken in the health dashboard, and require the consumer to re-select the source to trigger stream recreation. This results in a one-time data gap. See `event_table_streams_governance_research.md` Section 7.1 for full details.

---

## 15. Implementation Checklist

### Schema & Extraction
- [ ] Each event table signal type has a dedicated extraction query reading from the **stream**
- [ ] Each ACCOUNT_USAGE source has a dedicated extraction query with watermark + overlap + dedup
- [ ] Event table queries filter by `RECORD_TYPE` and entity discrimination (`snow.executable.type`)
- [ ] Event table queries do NOT include time-range predicates or `QUALIFY` dedup
- [ ] ACCOUNT_USAGE queries filter by time with overlap window and use `QUALIFY ROW_NUMBER()` dedup
- [ ] All hot-path semi-structured fields use `:"key"::TYPE` extraction
- [ ] `trace_id` and `span_id` are extracted from `TRACE`, not `RECORD`
- [ ] `status` is extracted as `RECORD:"status":"code"::STRING` (nested OBJECT with optional `message`)
- [ ] Metric names are extracted as `RECORD:"metric":"name"::STRING` (nested OBJECT)
- [ ] `dropped_attributes_count` preserved from SPAN and SPAN_EVENT RECORD
- [ ] SPAN_EVENT extraction includes `exception.stacktrace` and `exception.escaped`
- [ ] LOG extraction handles three populations: container, instrumented, and unhandled-exception
- [ ] Unhandled exception LOG `VALUE` = string `exception` (not the error message — that's in RECORD_ATTRIBUTES)
- [ ] EVENT extraction handles task, container, and Native App lifecycle subtypes

### Stream Lifecycle & Transaction
- [ ] Stream created on the user-selected source; use normalized event-table/view guidance rather than assuming one syntax line applies everywhere
- [ ] Stream uses namespaced naming: `_splunk_obs_stream_<source_name>`
- [ ] Collector SP wraps stream snapshot materialization + offset advancement in explicit `BEGIN`/`COMMIT`; OTLP export runs after COMMIT
- [ ] Zero-row INSERT (`SELECT ... FROM <stream> WHERE 0 = 1`) used for offset advancement
- [ ] `_staging.stream_offset_log` table exists (permanently empty, used only as INSERT target)
- [ ] Stream offset advances on both success AND failure (pipeline never stalls)
- [ ] Zero-matching-row runs still advance stream offset via zero-row INSERT + COMMIT
- [ ] `STALE_AFTER` timestamp monitored and surfaced in health dashboard
- [ ] Stale stream auto-recovery: detect → drop → recreate → record data gap

### Sources & Access
- [ ] AI observability uses `SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS` via separate stream
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
- [ ] Streamlit UI warns against `CREATE OR REPLACE VIEW` on custom views with active streams
- [ ] Stream staleness monitoring explained in Observability health page

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
