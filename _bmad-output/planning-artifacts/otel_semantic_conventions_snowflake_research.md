# OTel Semantic Conventions for Snowflake Telemetry — Research & Recommendation

**Date:** 2026-02-17 (Rev 4)
**Context:** Splunk Observability Native App for Snowflake — selecting the best-fit OTel semantic conventions for instrumenting Snowflake telemetry collection (traces, events, logs, metrics).

---

## 1. Executive Summary

**Key insight: The Snowflake Event Table is a multi-convention telemetry store.** It captures OTel-native spans, metrics, and logs from fundamentally different Snowflake services — each of which maps to different OTel semantic conventions. The app must be **convention-transparent** (relay what producers emitted) and **convention-aware** (understand what to expect and enrich).

**No single OTel convention covers all Snowflake telemetry.** The recommended convention stack is:

| Layer | Convention | Purpose | Status |
|---|---|---|---|
| **0 — Relay** | Convention-transparent | Preserve ALL original attributes from Event Table data | Architecture |
| **1 — Database** | `db.*` (Database Client) | SQL/Snowpark operations, Snowflake execution context | **Stable** |
| **2 — GenAI** | `gen_ai.*` (Generative AI) | Cortex AI services (LLM, Agents, Search, Analyst, Document AI) | Development |
| **3 — Infrastructure** | `k8s.*`, `container.*` | Openflow, Snowpark Container Services | Mixed |
| **4 — Resource** | `service.*`, `cloud.*` | Cross-cutting app/cloud identification | Stable / Dev |
| **5 — Custom** | `snowflake.*` | Snowflake-specific context (warehouse, role, query ID, etc.) | Custom |

**Splunk Observability Cloud alignment:**
- **DB Client (`db.*`):** Natively supported since [August 2025 release](https://community.splunk.com/t5/Product-News-Announcements/What-s-New-in-Splunk-Observability-August-2025/ba-p/752193) in APM traces, Tag Spotlight, and DB query monitoring
- **GenAI (`gen_ai.*`):** Splunk Observability Cloud APM supports OpenTelemetry spans natively; GenAI traces will render as standard traces with GenAI-specific attributes

---

## 2. Why Not "Only Database Client"?

The previous version of this document recommended Database Client as the sole primary convention. This was **too narrow**. Snowflake is no longer "just a database" — it is a **multi-service cloud platform** that hosts:

| Snowflake Service Category | Examples | Primary Operation Type |
|---|---|---|
| SQL/Snowpark compute | Stored Procedures, UDFs/UDTFs, Queries | Database operations |
| Generative AI | Cortex LLM functions (COMPLETE, SUMMARIZE, SENTIMENT, TRANSLATE), Cortex Agents, Cortex Search, Cortex Analyst, Document AI | LLM inference, agent reasoning, retrieval |
| Data Integration | Openflow (data pipelines/CDC) | Pipeline/connector operations |
| Container compute | Snowpark Container Services | Arbitrary workloads |
| Web applications | Streamlit in Snowflake | HTTP serving/user interaction |
| Machine Learning | Snowpark ML, Feature Store | Model training/inference |
| Data pipelines | Tasks, Task Graphs, Dynamic Tables, Snowpipe | Scheduled/triggered data movement |

**All of these can write telemetry to Event Tables.** The app reads from Event Tables and relays that telemetry. Forcing everything into `db.*` would:
1. **Lose semantic meaning** — An LLM inference call is not a "database operation"
2. **Break Splunk integration paths** — GenAI traces in Splunk APM should have GenAI attributes for proper visualization
3. **Conflict with producer intent** — Snowflake's own AI Observability system (TruLens-based) stores GenAI traces in Event Tables using GenAI-aligned attributes

---

## 3. Snowflake Services → OTel Convention Mapping

### 3.1 Database Client (`db.*`) — SQL/Snowpark Operations

**Stability:** Stable (spans and core metrics as of v1.33.0)
**Spec:** [docs/db/](https://github.com/open-telemetry/semantic-conventions/tree/main/docs/db)

**Applies to:** Stored Procedures, UDFs/UDTFs, SQL queries, Snowpark DataFrame operations

#### Why It Fits

1. **Snowflake IS a SQL database.** The DB Client convention defines how to describe database operations. An [open issue (#2583)](https://github.com/open-telemetry/semantic-conventions/issues/2583) exists to add `snowflake` as a well-known `db.system.name` value.

2. **Direct attribute mapping for QUERY_HISTORY and Event Table data:**

   | Snowflake Source | OTel DB Client Attribute | Notes |
   |---|---|---|
   | `QUERY_TEXT` / SQL in stored proc | `db.query.text` | Stable. Sanitization rules apply. |
   | `DATABASE_NAME` / `snow.database.name` | `db.namespace` | Stable. Concatenated `database\|schema`. |
   | `QUERY_TYPE` (SELECT, INSERT, etc.) | `db.operation.name` | Stable. |
   | Error codes | `db.response.status_code` | Stable. New in v1.33.0. |
   | `TOTAL_ELAPSED_TIME` | `db.client.operation.duration` metric | Required metric. |
   | Table/view accessed | `db.collection.name` | Stable. |
   | Procedure name / `snow.executable.name` | `db.stored_procedure.name` | Stable. New in v1.33.0. |

3. **Splunk Observability Cloud already adopted these conventions.** The [August 2025 release](https://help.splunk.com/en/splunk-observability-cloud/release-notes/august-2025) updated APM, Tag Spotlight, and DB query monitoring:
   - `db.system` → `db.system.name`
   - `db.name` → `db.namespace`
   - `db.statement` → `db.query.text`
   - `db.operation` → `db.operation.name`

4. **`db.system.name = "snowflake"`** serves as the universal **execution context identifier** — even GenAI spans executing within Snowflake should carry this resource attribute to indicate they run on the Snowflake platform.

---

### 3.2 Generative AI (`gen_ai.*`) — Cortex AI Services (Post MVP)

**Stability:** Development (active, rapidly evolving, vendor-specific extensions for OpenAI/Anthropic/Azure/AWS Bedrock already defined)
**Spec:** [docs/gen-ai/](https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai)

**Applies to:** Cortex LLM Functions, Cortex Agents, Cortex Search, Cortex Analyst, Document AI, custom GenAI apps using AI Observability

#### Why It's Necessary

1. **Snowflake Cortex AI has native OTel-based observability.** The [AI Observability documentation](https://docs.snowflake.com/en/user-guide/snowflake-cortex/ai-observability) confirms: traces capture "inputs, outputs, and intermediate steps of interactions with an LLM application." The [Snowflake blog (Aug 2025)](https://www.snowflake.com/en/blog/ai-observability-trust-cortex-enterprise/) explicitly states these use "**OpenTelemetry traces**."

2. **AI Observability uses TruLens**, which instruments GenAI operations with attributes that align with the `gen_ai.*` namespace (model name, token counts, prompt/completion content, latency).

3. **Cortex Agents** have native observability for "agent planning, tool selection, execution and response generation steps" — directly mapping to OTel GenAI Agent spans (`gen_ai.operation.name`, `gen_ai.agent.name`, `gen_ai.agent.id`, tool execution spans).

4. **CRITICAL: These traces are stored in a SEPARATE event table** — `SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS`, NOT the customer's standard event table. See §7 for the detailed mapping of this table to OTel conventions.

#### Key GenAI Convention Attributes Expected in Event Table Data

| GenAI Convention Attribute | Snowflake Cortex Source | Notes |
|---|---|---|
| `gen_ai.operation.name` | `chat`, `generate_content`, `text_completion`, `create_agent`, `invoke_agent`, `execute_tool` | Operation type |
| `gen_ai.provider.name` | Could be `"snowflake"` or underlying model provider | Provider identification |
| `gen_ai.request.model` | Model name (e.g., `"mistral-large2"`, `"llama3.1-70b"`, `"snowflake-arctic"`) | Model used for inference |
| `gen_ai.usage.input_tokens` | Token usage for Cortex COMPLETE calls | Cost tracking |
| `gen_ai.usage.output_tokens` | Token usage for Cortex COMPLETE calls | Cost tracking |
| `gen_ai.agent.name` | Cortex Agent name | Agent identification |
| `gen_ai.agent.id` | Cortex Agent ID | Agent identification |

#### Splunk Integration Path

GenAI spans flow through OTLP/gRPC → Splunk APM as standard traces. GenAI-specific attributes will be available in:
- **APM Trace waterfall** — showing agent orchestration, tool calls, LLM inference as span hierarchy
- **Tag Spotlight** — filtering by `gen_ai.request.model`, `gen_ai.operation.name`, etc.
- **Custom dashboards** — token usage, latency by model, error rates

> **Note:** The OTel GenAI conventions are in "Development" status. However, they are under active development with vendor-specific extensions already defined for OpenAI, Anthropic, Azure AI Inference, and AWS Bedrock. The trajectory is toward stability. Snowflake's own adoption validates this direction.

---

### 3.3 Kubernetes & Container (`k8s.*`, `container.*`) — Openflow & Container Services (Post MVP)

**Stability:** Development (`k8s.*`), Development (`container.*`)
**Spec:** [docs/resource/](https://github.com/open-telemetry/semantic-conventions/tree/main/docs/resource)

**Applies to:** Openflow data pipelines, Snowpark Container Services

#### Openflow Telemetry in Event Tables

[Openflow monitoring documentation](https://docs.snowflake.com/en/user-guide/data-integration/openflow/monitor) confirms Openflow writes LOG and METRIC records to Event Tables with rich resource attributes:

| Resource Attribute | OTel Convention | Description |
|---|---|---|
| `application: "openflow"` | Custom | Fixed identifier |
| `cloud.service.provider` | `cloud.provider` (close mapping) | `aws`, `azure`, `gcp`, `spcs` |
| `k8s.container.name` | `k8s.container.name` | **Already uses OTel convention** |
| `k8s.namespace.name` | `k8s.namespace.name` | **Already uses OTel convention** |
| `k8s.pod.name` | `k8s.pod.name` | **Already uses OTel convention** |
| `k8s.pod.uid` | `k8s.pod.uid` | **Already uses OTel convention** |
| `k8s.pod.start_time` | Close to `k8s.pod.start_time` | Pod lifecycle |
| `k8s.node.name` | `k8s.node.name` | **Already uses OTel convention** |
| `container.id` | `container.id` | **Already uses OTel convention** |
| `container.image.name` | `container.image.name` | **Already uses OTel convention** |
| `container.image.tag` | `container.image.tag` | **Already uses OTel convention** |
| `openflow.dataplane.id` | Custom | Deployment identifier |

Openflow metrics use domain-specific names (`connection.*`, `processor.*`, `processgroup.*`, `port.*`, `jvm.*`, `storage.*`) that don't map to any standard OTel metric convention — they are pipeline/dataflow-specific.

**Key takeaway:** Openflow **already uses standard OTel `k8s.*` and `container.*` resource attributes**. The app should preserve these when relaying Openflow telemetry. No re-mapping needed.

---

### 3.4 HTTP Client (`http.*`) — External Functions & Exporter Spans

**Stability:** Stable
**Spec:** [docs/http/](https://github.com/open-telemetry/semantic-conventions/tree/main/docs/http)

**Applies to:**
- **External Functions** — Snowflake calling external REST APIs from within SQL
- **App's own exporter spans** — HEC HTTP calls, OTLP/gRPC calls to Splunk

This is a **secondary/supplementary** convention. HTTP attributes may appear on:
- Spans from External Functions that make HTTP calls to external services
- The app's own exporter spans when it calls Splunk HEC (HTTP) or OTLP endpoints

---

### 3.5 Exceptions (`exception.*`) — Cross-Cutting Error Enrichment

**Stability:** Stable
**Spec:** [docs/exceptions/](https://github.com/open-telemetry/semantic-conventions/tree/main/docs/exceptions)

**Applies to:** All telemetry types — error details on any span regardless of domain

| Attribute | Usage |
|---|---|
| `exception.type` | Exception class name |
| `exception.message` | Error description |
| `exception.stacktrace` | Stack trace string |
| `error.type` | General error classification (also part of DB Client and GenAI conventions) |

---

### 3.6 General Resource Attributes (`service.*`, `cloud.*`) — REQUIRED FOR ALL

**Stability:** Stable (`service.*`), Development (`cloud.*`)
**Spec:** [docs/resource/](https://github.com/open-telemetry/semantic-conventions/tree/main/docs/resource)

#### Service Resource Attributes

| Attribute | Recommended Value | Notes |
|---|---|---|
| `service.name` | `"splunk-snowflake-native-app"` | The app as telemetry relay |
| `service.namespace` | `"snowflake"` or account name | Groups related services |
| `service.version` | App version (e.g., `"1.0.0"`) | Tracks which app version |
| `service.instance.id` | Unique per-installation ID | Differentiates installations |

#### Cloud Resource Attributes

| Attribute | Recommended Value | Notes |
|---|---|---|
| `cloud.provider` | `"aws"` / `"azure"` / `"gcp"` | Underlying cloud provider |
| `cloud.region` | Snowflake region | Deployment region |
| `cloud.account.id` | Snowflake account identifier | Account ID |
| `cloud.platform` | `"snowflake"` (custom) | No well-known value exists |

---

### 3.7 Custom `snowflake.*` Namespace — REQUIRED FOR DOMAIN-SPECIFIC CONTEXT

OTel's extensibility model explicitly supports custom attribute namespaces. Snowflake's Event Table resource attributes (`snow.*`) should be mapped to a `snowflake.*` namespace.

| Snowflake Event Table Source | Proposed OTel Attribute | Description |
|---|---|---|
| `snow.executable.name` | `snowflake.executable.name` | UDF/procedure name with full signature |
| `snow.executable.type` | `snowflake.executable.type` | FUNCTION, PROCEDURE, STREAMLIT |
| `snow.query.id` | `snowflake.query.id` | Query ID that initiated the trace |
| `snow.warehouse.name` | `snowflake.warehouse.name` | Warehouse executing the operation |
| `snow.database.name` | `db.namespace` (part 1) + `snowflake.database.name` | Maps to both standard + custom |
| `snow.schema.name` | `db.namespace` (part 2) + `snowflake.schema.name` | Maps to both standard + custom |
| `db.user` | `snowflake.user` | User executing the operation |
| `snow.owner.name` | `snowflake.owner` | Role with OWNERSHIP privilege |
| `snow.session.role.primary.name` | `snowflake.session.role` | Primary role in session |
| Account name (from context) | `snowflake.account.name` | Snowflake account identifier |

---

## 4. Convention Detection & Enrichment Architecture

The app operates as a **telemetry relay** — it reads from Event Tables and forwards to Splunk. The critical architectural principle is:

### 4.1 Convention-Transparent Relay (Layer 0)

```
Event Table Record
  ├── RESOURCE_ATTRIBUTES   →  Preserve as-is in OTel Resource
  ├── RECORD_ATTRIBUTES     →  Preserve as-is in Span/Metric Attributes
  ├── RECORD (span/metric)  →  Preserve structure
  └── VALUE (logs)          →  Preserve content
```

**Rule: Never strip, rename, or re-map attributes the original producer set.** Whether a span has `gen_ai.request.model` or `db.operation.name` or `processor.invocations`, preserve it.

### 4.2 Convention Detection

The app can identify the source service and applicable convention from Event Table attributes:

| Detection Signal | Detected Convention | Source Service |
|---|---|---|
| `snow.executable.type` = `FUNCTION` or `PROCEDURE` | DB Client | Stored Procedures / UDFs |
| `snow.executable.type` = `STREAMLIT` | Custom (HTTP patterns) | Streamlit apps |
| `RESOURCE_ATTRIBUTES:application` = `"openflow"` | K8s/Container + Custom pipeline | Openflow |
| Presence of `gen_ai.*` attributes in RECORD_ATTRIBUTES | GenAI | Cortex AI services |
| Presence of `k8s.*` attributes | K8s/Container | Container Services / Openflow |
| SCOPE containing `"trulens"` or AI Observability markers | GenAI | Cortex AI Observability |

### 4.3 Enrichment (Added by the App)

Regardless of which convention the original telemetry uses, the app ADDS:

```
Always added to all relayed telemetry:
  db.system.name           = "snowflake"        (execution platform context)
  service.name             = "splunk-snowflake-native-app"
  service.version          = "<app_version>"
  cloud.provider           = "<underlying_cloud>"
  cloud.region             = "<snowflake_region>"
  snowflake.account.name   = "<account>"

Conditionally added (from snow.* resource attributes):
  snowflake.warehouse.name = "<warehouse>"       (if present)
  snowflake.query.id       = "<query_id>"        (if present)
  snowflake.session.role   = "<role>"            (if present)
  snowflake.user           = "<user>"            (if present)
  db.namespace             = "<database>|<schema>" (if snow.database.name present)
```

---

## 5. Per-Pipeline Convention Mapping

### 5.1 Event Table Pipeline (OTLP/gRPC → Splunk Observability)

**Spans from traditional SQL/Snowpark:**
```
Resource:  db.system.name = "snowflake", service.name, cloud.*
Span:      db.namespace, db.operation.name, db.stored_procedure.name,
           db.query.text, snowflake.executable.*, snowflake.warehouse.name
```

**Spans from Cortex AI (LLM/Agent/Search):**
```
Resource:  db.system.name = "snowflake", service.name, cloud.*
Span:      gen_ai.operation.name, gen_ai.request.model, gen_ai.provider.name,
           gen_ai.usage.input_tokens, gen_ai.usage.output_tokens,
           gen_ai.agent.name (if agent), snowflake.warehouse.name
```

**Metrics/Logs from Openflow:**
```
Resource:  application = "openflow", k8s.*, container.*, openflow.dataplane.id,
           cloud.service.provider, service.name, db.system.name = "snowflake"
Metric:    connection.*, processor.*, processgroup.* (original names preserved)
Log:       Structured JSON with level, loggerName, formattedMessage, throwable
```

**Generic/unknown spans:** Preserve all attributes, add snowflake.* enrichment.

### 5.2 ACCOUNT_USAGE Pipeline (HEC → Splunk Enterprise/Cloud)

ACCOUNT_USAGE data is exported as structured JSON events to HEC. OTel conventions don't directly apply to the wire format, but **DB Client convention naming should inform field mapping** for consistency:

| Splunk Field | Convention-Informed Name | Source |
|---|---|---|
| `sourcetype` | `snowflake:query_history`, etc. | Splunk sourcetype convention |
| Query text field | Named to align with `db.query.text` | QUERY_HISTORY.QUERY_TEXT |
| Database field | Named to align with `db.namespace` | QUERY_HISTORY.DATABASE_NAME |
| Operation field | Named to align with `db.operation.name` | QUERY_HISTORY.QUERY_TYPE |

### 5.3 App's Own Operational Telemetry

```
Resource:  service.name = "splunk-snowflake-native-app"
           service.namespace = "snowflake"
           service.version = "<app_version>"
Metrics:   snowflake.pipeline.* (e.g., rows_exported, export_latency_ms)
Spans:     HTTP/RPC conventions for exporter calls to Splunk endpoints
```

---

## 6. Event Table → OTel Database Client Span Mapping (Stored Procedures / UDFs)

**References:**
- [OTel Database Client Spans](https://opentelemetry.io/docs/specs/semconv/db/database-spans/) (Stable)
- [OTel SQL Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/db/sql/) (Stable)
- [OTel Span API — Naming Rules](https://github.com/open-telemetry/opentelemetry-specification/blob/v1.53.0/specification/trace/api.md#span)
- [Snowflake Event Table Columns](https://docs.snowflake.com/en/developer-guide/logging-tracing/event-table-columns)

This section provides the **complete field-by-field mapping** of every Event Table column and nested attribute (for SPAN records emitted by stored procedures, UDFs, UDTFs, and SQL tracing) to the corresponding OTel Database Client and SQL semantic convention attributes. It also identifies enrichment the app must perform and gaps where no Snowflake data source exists.

### 6.1 Event Table Schema Overview (SPAN Records)

When a stored procedure or UDF executes, Snowflake writes rows to the Event Table with `RECORD_TYPE = 'SPAN'`. Each row has the following top-level columns:

| Column | Data Type | OTel Concept | For SPAN Records |
|---|---|---|---|
| `TIMESTAMP` | TIMESTAMP_NTZ | Span end time | UTC time at which execution concluded |
| `START_TIMESTAMP` | TIMESTAMP_NTZ | Span start time | UTC time when the span began |
| `OBSERVED_TIMESTAMP` | TIMESTAMP_NTZ | — | Not used for trace events |
| `TRACE` | OBJECT | Trace context | Contains `trace_id` and `span_id` |
| `RESOURCE` | OBJECT | — | Reserved for future use |
| `RESOURCE_ATTRIBUTES` | OBJECT | OTel Resource | Source identification (set by Snowflake, immutable) |
| `SCOPE` | OBJECT | InstrumentationScope | Code namespace (e.g., class name) |
| `SCOPE_ATTRIBUTES` | OBJECT | — | Reserved for future use |
| `RECORD_TYPE` | STRING | — | `SPAN` for span records |
| `RECORD` | OBJECT | Span fields | Name, kind, status, parent_span_id |
| `RECORD_ATTRIBUTES` | OBJECT | Span attributes | Query metadata, row counts, user-defined attrs |
| `VALUE` | VARIANT | — | Not used for spans (used for logs/metrics) |
| `EXEMPLARS` | ARRAY | — | Reserved for future use |

### 6.2 TRACE Column → OTel Trace Context

The `TRACE` column is **already OTel-native**. No transformation needed — relay directly.

| TRACE Key | Type | OTel Field | Mapping | Notes |
|---|---|---|---|---|
| `trace_id` | Hex string | `TraceId` | **Direct (1:1)** | Unique per query. Same for all spans within a query. Equals `snow.query.id` without dashes. |
| `span_id` | Hex string | `SpanId` | **Direct (1:1)** | Unique per span. Procedures: single span. UDFs: one span per execution thread. |

### 6.3 RECORD Column (SPAN) → OTel Span Fields

The `RECORD` column for `RECORD_TYPE = 'SPAN'` contains the span's structural fields. These map to core OTel Span properties.

| RECORD Key | Type | OTel Span Field | Mapping | Notes |
|---|---|---|---|---|
| `name` | string | Span name | **Direct, but needs re-naming** (see §6.8) | Python: handler function name. SQL: statement type (SELECT, INSERT). Non-Python: `snow.auto_instrumented`. |
| `kind` | string | `SpanKind` | **Direct** | `SPAN_KIND_INTERNAL` for handler code, `SPAN_KIND_SERVER` for SQL statements. |
| `status` | string | `SpanStatus` | **Direct** | `STATUS_CODE_ERROR` on unhandled exception, `STATUS_CODE_UNSET` otherwise. Note: no `STATUS_CODE_OK` — Snowflake uses UNSET for success. |
| `parent_span_id` | Hex string | Parent SpanId | **Direct (1:1)** | Present when proc/UDF was called by another proc in a call chain. Links to parent span's `span_id`. |
| `dropped_attributes_count` | int | `droppedAttributesCount` | **Direct (1:1)** | Number of attributes ignored after max limit reached. |
| `snow.process.memory.usage.max` | string | — (custom metric) | **Preserve as-is** | Max memory (bytes) used during span. Map to `snowflake.process.memory.usage.max`. |

### 6.4 RESOURCE_ATTRIBUTES → OTel Resource + DB Client Attributes

The `RESOURCE_ATTRIBUTES` column is set by Snowflake and **cannot be changed by user code**. It contains two categories of attributes: event source identity and execution environment.

#### 6.4.1 Event Source Identity

| RESOURCE_ATTRIBUTES Key | Type | OTel Attribute | Req Level | Mapping | Notes |
|---|---|---|---|---|---|
| `snow.database.name` | string | **`db.namespace`** | Cond. Required | **Enrich** | Concatenate: `{snow.database.name}\|{snow.schema.name}` per OTel spec (most general → most specific, `\|` separator). |
| `snow.schema.name` | string | **`db.namespace`** (part 2) | — | **Enrich** | Combined with database.name above. Also preserve as `snowflake.schema.name`. |
| `snow.executable.name` | string | **`db.stored_procedure.name`** | Recommended | **Enrich (procedures only)** | Full signature (e.g., `MY_PROC(X FLOAT):FLOAT`). Extract name portion for `db.stored_procedure.name`. Keep full value as `snowflake.executable.name`. |
| `snow.executable.type` | string | Informs `db.operation.name` | — | **Detection signal** | Values: `procedure`, `function`, `query`, `sql`, `spcs`, `streamlit`. Determines convention and enrichment. |
| `snow.executable.id` | int | — | — | **Preserve** | `snowflake.executable.id` |
| `snow.executable.runtime.version` | string | — | — | **Preserve** | `snowflake.executable.runtime.version` (e.g., "3.11" for Python) |
| `snow.database.id` | int | — | — | **Preserve** | `snowflake.database.id` |
| `snow.schema.id` | int | — | — | **Preserve** | `snowflake.schema.id` |
| `snow.owner.name` | string | — | — | **Preserve** | `snowflake.owner.name` — role with OWNERSHIP privilege |
| `snow.owner.id` | int | — | — | **Preserve** | `snowflake.owner.id` |
| `snow.owner.type` | string | — | — | **Preserve** | `snowflake.owner.type` — `ROLE` or `APPLICATION` |
| `snow.table.name` | string | **`db.collection.name`** | Recommended | **Enrich** | Table associated with the executable. Map to `db.collection.name` if present. |
| `telemetry.sdk.language` | string | `telemetry.sdk.language` | — | **Direct (1:1)** | Already OTel-standard resource attribute. Values: `java`, `scala`, `python`, `javascript`, `sql`. |

#### 6.4.2 Execution Environment

| RESOURCE_ATTRIBUTES Key | Type | OTel Attribute | Req Level | Mapping | Notes |
|---|---|---|---|---|---|
| `db.user` | string | — (not in OTel DB spec) | — | **Preserve + alias** | Snowflake uses `db.user` but OTel has no `db.user` attribute. Preserve original. Also set `snowflake.user`. |
| `snow.query.id` | string | — | — | **Preserve** | `snowflake.query.id` — query that initiated the trace |
| `snow.session.id` | int | — | — | **Preserve** | `snowflake.session.id` |
| `snow.session.role.primary.name` | string | — | — | **Preserve** | `snowflake.session.role` |
| `snow.session.role.primary.id` | int | — | — | **Preserve** | `snowflake.session.role.id` |
| `snow.user.id` | int | — | — | **Preserve** | `snowflake.user.id` |
| `snow.warehouse.name` | string | — | — | **Preserve** | `snowflake.warehouse.name` — execution destination |
| `snow.warehouse.id` | int | — | — | **Preserve** | `snowflake.warehouse.id` |
| `snow.release.version` | string | — | — | **Preserve** | `snowflake.release.version` — Snowflake release running when event was generated |

**Example RESOURCE_ATTRIBUTES** (from Snowflake docs):
```json
{
  "db.user": "MYUSERNAME",
  "snow.database.id": 13,
  "snow.database.name": "MY_DB",
  "snow.executable.id": 197,
  "snow.executable.name": "UDF_VARCHAR(X VARCHAR):VARCHAR(16777216)",
  "snow.executable.type": "FUNCTION",
  "snow.owner.id": 2,
  "snow.owner.name": "MY_ROLE",
  "snow.query.id": "01ab0f07-0000-15c8-0000-0129000592c2",
  "snow.schema.id": 16,
  "snow.schema.name": "PUBLIC",
  "snow.session.id": 1275605667850,
  "snow.session.role.primary.id": 2,
  "snow.session.role.primary.name": "MY_ROLE",
  "snow.user.id": 25,
  "snow.warehouse.id": 5,
  "snow.warehouse.name": "MYWH",
  "telemetry.sdk.language": "python"
}
```

### 6.5 RECORD_ATTRIBUTES (SPAN) → OTel Span Attributes

The `RECORD_ATTRIBUTES` column for `RECORD_TYPE = 'SPAN'` contains attributes set by Snowflake and/or handler code.

#### 6.5.1 Snowflake-Set Span Attributes

| RECORD_ATTRIBUTES Key | Type | OTel Attribute | Req Level | Mapping | Notes |
|---|---|---|---|---|---|
| `db.query.text` | string | **`db.query.text`** | Recommended | **Direct (1:1)** | SQL text of the traced query. Only present if `SQL_TRACE_QUERY_TEXT` parameter is `ON`. Up to 1024 characters. |
| `db.query.table.names` | string | **`db.collection.name`** (partial) | Recommended | **Enrich** | Snowflake-specific attribute listing all tables read/modified. Use first table for `db.collection.name` if single-table operation. Preserve original as-is. |
| `db.query.view.names` | string | — | — | **Preserve** | Snowflake-specific. Views accessed in the query. No OTel equivalent, but useful for `db.query.summary` generation. |
| `db.query.executable.names` | string | — | — | **Preserve** | Snowflake-specific. Names of executables executed under the traced query. |
| `snow.input.rows` | int | — | — | **Preserve** | `snowflake.input.rows` — input rows processed by the function span |
| `snow.output.rows` | int | **`db.response.returned_rows`** | Opt-In | **Enrich** | Map to `db.response.returned_rows` (Development status). Also preserve as `snowflake.output.rows`. |

> **Note on `db.query.text`:** This is the **only Snowflake Event Table attribute that is an exact OTel DB Client attribute name match**. Snowflake already uses the OTel naming convention for this field. The others (`db.query.table.names`, `db.query.view.names`, `db.query.executable.names`) use the `db.query.*` namespace but are **Snowflake-specific extensions**, not standard OTel attributes.

#### 6.5.2 SQL Statement Tracing Attributes

When `snow.executable.type = 'QUERY'` (SQL traced inside a procedure), the following appear in RECORD_ATTRIBUTES:

| Attribute | Source | Notes |
|---|---|---|
| `db.query.table.names` | Snowflake-set | Tables read/modified |
| `db.query.view.names` | Snowflake-set | Views accessed |
| `db.query.executable.names` | Snowflake-set | Executables called |
| `db.query.text` | Snowflake-set (if enabled) | SQL text (requires `SQL_TRACE_QUERY_TEXT = ON`) |

The RECORD.name for SQL-traced spans is the SQL statement type (e.g., `SELECT`, `INSERT`, `CALL`), which maps directly to `db.operation.name`.

#### 6.5.3 User-Defined Custom Attributes

Handler code can add arbitrary key-value pairs to `RECORD_ATTRIBUTES`:
```json
{
  "MyFunctionVersion": "1.1.0",
  "example.boolean": true,
  "example.double": 2.5
}
```
**Rule:** Preserve all user-defined attributes as-is. Do not transform, rename, or drop.

### 6.6 SPAN_EVENT Records → OTel Span Events

Span events (`RECORD_TYPE = 'SPAN_EVENT'`) are attached to a parent span via shared `trace_id` and `span_id` in the TRACE column. Up to 128 span events per span.

| Column / Key | OTel Span Event Field | Notes |
|---|---|---|
| `TIMESTAMP` | Event timestamp | Wall-clock time the event was emitted |
| `RECORD.name` | Event name | User-defined event name (e.g., `"testEvent"`) |
| `RECORD.dropped_attributes_count` | droppedAttributesCount | Attributes over limit |
| `RECORD_ATTRIBUTES.*` | Event attributes | User-defined key-value pairs |
| `TRACE.trace_id` / `TRACE.span_id` | Links to parent span | Same span_id as the parent SPAN record |

#### 6.6.1 Unhandled Exception Span Events

Snowflake automatically records exception data as span events. These map **exactly** to OTel exception semantic conventions:

| RECORD_ATTRIBUTES Key | OTel Attribute | Mapping | Notes |
|---|---|---|---|
| `exception.message` | `exception.message` | **Direct (1:1)** | Error message text |
| `exception.type` | `exception.type` | **Direct (1:1)** | Exception class name |
| `exception.stacktrace` | `exception.stacktrace` | **Direct (1:1)** | Stack trace formatted by language runtime |
| `exception.escaped` | `exception.escaped` | **Direct (1:1)** | `true` for unhandled exceptions |

The RECORD column for exception span events: `{"name": "exception", "dropped_attributes_count": 0}`
The parent SPAN's RECORD.status: `STATUS_CODE_ERROR`

### 6.7 SCOPE Column → OTel InstrumentationScope

| SCOPE Key | OTel Field | Mapping | Notes |
|---|---|---|---|
| `name` | `InstrumentationScope.name` | **Direct (1:1)** | Code namespace (e.g., `com.sample.MyClass`). Not used for trace spans in most cases. |

### 6.8 Span Naming Convention Alignment

This is a **critical gap** between Snowflake's Event Table data and OTel spec requirements.

#### OTel Span Naming Rules (from [database-spans](https://opentelemetry.io/docs/specs/semconv/db/database-spans/#name))

The span name SHOULD follow this priority:
1. `{db.query.summary}` — if a summary is available
2. `{db.operation.name} {target}` — if a low-cardinality operation name is available
3. `{target}` — if only the target is available
4. `{db.system.name}` — fallback ("snowflake")

Where `{target}` is one of:
- `db.collection.name` (for table operations)
- `db.stored_procedure.name` (for procedure calls)
- `db.namespace` (for namespace-scoped operations)
- `server.address:server.port` (for server-scoped operations)

#### What Snowflake Produces (RECORD.name)

| `snow.executable.type` | RECORD.name Value | Example | OTel Alignment |
|---|---|---|---|
| `procedure` (Python) | Handler function name | `my_handler` | **MISALIGNED** — should be `CALL MY_PROC` |
| `function` (Python UDF) | Handler function name | `calculate_score` | **MISALIGNED** — should be `{operation} {table}` or function-specific |
| `function` (Python UDTF) | Handler class name | `MyTableFunction` | **MISALIGNED** |
| `query` / `sql` (SQL traced) | SQL statement type | `SELECT`, `INSERT`, `CALL` | **PARTIAL MATCH** — this IS `db.operation.name`, but `{target}` is missing |
| Non-Python handlers | Fixed string | `snow.auto_instrumented` | **MISALIGNED** — no operation/target info |

#### Enrichment Strategy for Span Names

The app SHOULD generate OTel-compliant span names based on available data:

```
For snow.executable.type = "procedure":
  span_name = "CALL {extracted_procedure_name}"
  db.operation.name = "CALL"
  db.stored_procedure.name = extracted name from snow.executable.name
  
  Example: snow.executable.name = "MY_PROC(X FLOAT):FLOAT"
           → span_name = "CALL MY_PROC"
           → db.stored_procedure.name = "MY_PROC"
           → db.operation.name = "CALL"

For snow.executable.type = "function":
  span_name = "{db.operation.name} {snow.executable.name_extracted}"
  Keep original RECORD.name as snowflake.handler.name
  
  Example: RECORD.name = "calculate_score", 
           snow.executable.name = "CALC_SCORE(X FLOAT):FLOAT"
           → span_name = "CALC_SCORE"
           → snowflake.handler.name = "calculate_score"

For snow.executable.type = "query" or "sql":
  span_name = "{RECORD.name} {db.query.table.names[0]}"
  db.operation.name = RECORD.name (SELECT, INSERT, etc.)
  db.collection.name = first table from db.query.table.names
  
  Example: RECORD.name = "SELECT", db.query.table.names = "ORDERS"
           → span_name = "SELECT ORDERS"
           → db.operation.name = "SELECT"
           → db.collection.name = "ORDERS"

Fallback (no target available):
  span_name = "{db.operation.name}" or "snowflake"
```

> **Important:** The original `RECORD.name` MUST be preserved — either within the enriched span name or as a separate attribute (`snowflake.handler.name`). The OTel-compliant span name is generated as **additive enrichment**.

### 6.9 OTel DB Client Attributes — App Enrichment Summary

The following table summarizes all OTel Database Client attributes, their requirement level per spec, and whether the Event Table provides the data or the app must enrich.

| OTel DB Attribute | Req Level | Source in Event Table | App Action |
|---|---|---|---|
| **`db.system.name`** | **Required** | Not present | **MUST enrich** = `"snowflake"` |
| **`db.namespace`** | Cond. Required | `RESOURCE_ATTRIBUTES:snow.database.name` + `snow.schema.name` | **MUST enrich** = `"{db}\|{schema}"` |
| **`db.operation.name`** | Cond. Required | `RECORD.name` (for SQL traces: SELECT, INSERT, etc.) | **Enrich** from RECORD.name + executable.type |
| **`db.collection.name`** | Cond. Required | `RECORD_ATTRIBUTES:db.query.table.names` | **Enrich** (first table if single-table op) |
| **`db.response.status_code`** | Cond. Required | Not present | **Gap** — Snowflake does not expose SQLSTATE or error codes in Event Table |
| **`error.type`** | Cond. Required | `RECORD_ATTRIBUTES:exception.type` (on span events) | **Enrich** from exception.type; set to `_OTHER` if error but no type |
| `server.port` | Cond. Required | Not present | **N/A** — Snowflake is SaaS, always port 443 |
| `db.query.text` | Recommended | `RECORD_ATTRIBUTES:db.query.text` | **Direct (1:1)** — requires `SQL_TRACE_QUERY_TEXT = ON` |
| `db.query.summary` | Recommended | Not present | **Enrich** — generate from `db.operation.name` + `db.collection.name` |
| `db.stored_procedure.name` | Recommended | `RESOURCE_ATTRIBUTES:snow.executable.name` (if procedure) | **Enrich** — extract name from signature |
| `db.operation.batch.size` | Recommended | Not present | **N/A** — not applicable for single-execution spans |
| `server.address` | Recommended | Not present | **Enrich** — set to Snowflake account URL (e.g., `{account}.snowflakecomputing.com`) |
| `network.peer.address` | Recommended | Not present | **N/A** — internal Snowflake networking, not exposed |
| `network.peer.port` | Recommended | Not present | **N/A** |
| `db.query.parameter.<key>` | Opt-In | Not present | **N/A** — Snowflake does not expose query parameters in Event Table |
| `db.response.returned_rows` | Opt-In | `RECORD_ATTRIBUTES:snow.output.rows` | **Enrich** (Development status) |

### 6.10 Gap Analysis

#### Attributes the OTel Spec Expects but Snowflake Event Table Does NOT Provide

| Missing OTel Attribute | Impact | Mitigation |
|---|---|---|
| `db.system.name` | **High** — Required attribute | App MUST always enrich with `"snowflake"` |
| `db.response.status_code` | **Medium** — Cond. Required on error | Cannot be populated. `RECORD.status = STATUS_CODE_ERROR` + `exception.*` attributes partially compensate. Consider requesting Snowflake add SQLSTATE to Event Table. |
| `db.query.summary` | **Low** — Recommended | App can generate: `{db.operation.name} {db.collection.name}` |
| `server.address` | **Low** — Recommended | App can set to Snowflake account URL from configuration |
| `db.query.text` | **Medium** — Recommended but gated | Requires customer to enable `SQL_TRACE_QUERY_TEXT = ON` (account-level parameter, ACCOUNTADMIN role required). App documentation must inform customers. |

#### Snowflake Attributes with No OTel Standard Equivalent (Preserve as Custom)

| Snowflake Attribute | Proposed Custom Namespace | Value |
|---|---|---|
| `snow.executable.name` | `snowflake.executable.name` | Full signature (e.g., `MY_PROC(X FLOAT):FLOAT`) |
| `snow.executable.type` | `snowflake.executable.type` | `procedure`, `function`, `query`, `sql`, `spcs`, `streamlit` |
| `snow.executable.id` | `snowflake.executable.id` | Internal ID |
| `snow.query.id` | `snowflake.query.id` | Query ID |
| `snow.warehouse.name` | `snowflake.warehouse.name` | Warehouse name |
| `snow.warehouse.id` | `snowflake.warehouse.id` | Warehouse internal ID |
| `snow.session.id` | `snowflake.session.id` | Session ID |
| `snow.session.role.primary.name` | `snowflake.session.role` | Primary session role |
| `snow.owner.name` | `snowflake.owner.name` | Role with OWNERSHIP |
| `snow.release.version` | `snowflake.release.version` | Snowflake release version |
| `db.user` | `snowflake.user` (also preserve `db.user`) | Executing user |
| `snow.input.rows` | `snowflake.input.rows` | Input rows to function |
| `snow.output.rows` | `snowflake.output.rows` (also → `db.response.returned_rows`) | Output rows from function |
| `db.query.table.names` | Preserve as-is | Snowflake extension of `db.query.*` |
| `db.query.view.names` | Preserve as-is | Snowflake extension of `db.query.*` |
| `db.query.executable.names` | Preserve as-is | Snowflake extension of `db.query.*` |
| `snow.process.memory.usage.max` | `snowflake.process.memory.usage.max` | Max memory (bytes) during span |

### 6.11 Complete Enrichment Flow (Example)

**Input:** Event Table row for a Python stored procedure span

```
TIMESTAMP:            2026-02-17 10:30:02.500
START_TIMESTAMP:      2026-02-17 10:30:00.100
RECORD_TYPE:          SPAN
TRACE:                {"trace_id": "01ab0f070000...", "span_id": "b4c28078330873a2"}
RECORD:               {"name": "process_orders", "kind": "SPAN_KIND_INTERNAL", 
                       "status": "STATUS_CODE_UNSET", "dropped_attributes_count": 0}
RESOURCE_ATTRIBUTES:  {"db.user": "ANALYST", "snow.database.name": "ANALYTICS_DB",
                       "snow.schema.name": "PUBLIC", "snow.executable.name": 
                       "PROCESS_ORDERS():VARCHAR(16777216)", "snow.executable.type": 
                       "procedure", "snow.warehouse.name": "COMPUTE_WH",
                       "snow.query.id": "01ab0f07-0000-15c8-0000-0129000592c2",
                       "telemetry.sdk.language": "python", ...}
RECORD_ATTRIBUTES:    {"db.query.table.names": "ORDERS", 
                       "db.query.text": "SELECT * FROM ORDERS WHERE status = 'pending'"}
```

**Output:** OTel Span (OTLP/gRPC)

```
TraceId:          01ab0f070000...
SpanId:           b4c28078330873a2
Name:             "CALL PROCESS_ORDERS"                    ← ENRICHED (was "process_orders")
Kind:             SPAN_KIND_INTERNAL                       ← PRESERVED
Status:           STATUS_CODE_UNSET                        ← PRESERVED
StartTime:        2026-02-17T10:30:00.100Z                 ← PRESERVED
EndTime:          2026-02-17T10:30:02.500Z                 ← PRESERVED

Resource Attributes:
  db.system.name              = "snowflake"                ← ENRICHED (not in source)
  db.namespace                = "ANALYTICS_DB|PUBLIC"       ← ENRICHED (from snow.database.name + snow.schema.name)
  service.name                = "splunk-snowflake-native-app"  ← ENRICHED
  service.version             = "1.0.0"                    ← ENRICHED
  cloud.provider              = "aws"                      ← ENRICHED (from config)
  cloud.region                = "us-west-2"                ← ENRICHED (from config)
  server.address              = "myaccount.snowflakecomputing.com"  ← ENRICHED (from config)
  telemetry.sdk.language      = "python"                   ← PRESERVED
  db.user                     = "ANALYST"                  ← PRESERVED (original)
  snowflake.user              = "ANALYST"                  ← ALIAS
  snowflake.executable.name   = "PROCESS_ORDERS():VARCHAR(16777216)"  ← PRESERVED
  snowflake.executable.type   = "procedure"                ← PRESERVED
  snowflake.query.id          = "01ab0f07-0000-15c8-0000-0129000592c2"  ← PRESERVED
  snowflake.warehouse.name    = "COMPUTE_WH"               ← PRESERVED
  snowflake.account.name      = "myaccount"                ← ENRICHED (from config)

Span Attributes:
  db.operation.name           = "CALL"                     ← ENRICHED (from executable.type = procedure)
  db.stored_procedure.name    = "PROCESS_ORDERS"           ← ENRICHED (extracted from executable.name)
  db.collection.name          = "ORDERS"                   ← ENRICHED (from db.query.table.names)
  db.query.text               = "SELECT * FROM ORDERS WHERE status = 'pending'"  ← PRESERVED (1:1)
  db.query.summary            = "CALL PROCESS_ORDERS"      ← ENRICHED (generated)
  db.query.table.names        = "ORDERS"                   ← PRESERVED (Snowflake-specific)
  snowflake.handler.name      = "process_orders"           ← PRESERVED (original RECORD.name)
```

---

## 7. AI_OBSERVABILITY_EVENTS → OTel GenAI Semantic Convention Mapping (Cortex Agents / AI Observability)

### 7.1 Critical Architectural Discovery

Cortex Agent traces and AI Observability data are **NOT stored in the customer's standard event table**. They reside in a **dedicated system-managed table**:

```
SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS
```

**Key Differences from Standard Event Table:**

| Aspect | Standard Event Table | AI_OBSERVABILITY_EVENTS |
|---|---|---|
| **Location** | `<db>.<schema>.<event_table>` (customer-configured) | `SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS` (system-managed) |
| **Schema** | Standard [event table columns](https://docs.snowflake.com/en/developer-guide/logging-tracing/event-table-columns) | Same event table column structure |
| **Access** | Direct `SELECT` on event table | Via `GET_AI_OBSERVABILITY_EVENTS()` table function |
| **Privileges** | Event table read privileges | `MONITOR` / `OWNERSHIP` on AGENT + `CORTEX_USER` database role |
| **Data producers** | Stored procedures, UDFs, Streamlit, Openflow, SQL tracing | Cortex Agents, TruLens-instrumented GenAI apps |
| **Modifiable** | Yes (standard table) | No (immutable; only `AI_OBSERVABILITY_ADMIN` can delete) |
| **Primary OTel domain** | `db.*` (Database Client) | `gen_ai.*` (Generative AI) |

**Implication for our app:** The app must collect from **TWO distinct event table sources** using different access patterns and map them to different OTel convention namespaces.

### 7.2 Two Data Producers

#### A. Cortex Agent Monitoring (Native — Automatic)

Cortex Agents **automatically** log detailed execution traces. Per the [Cortex Agent monitoring docs](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-monitor), spans include:

| Span Type | Description | OTel GenAI Operation |
|---|---|---|
| **LLM Planning** | Agent's reasoning/planning step | `invoke_agent` (root) or `chat` (LLM call) |
| **Tool Execution** | Cortex Search, Cortex Analyst, web search, custom tools (UDFs/SPs) | `execute_tool` |
| **LLM Response Generation** | Final response generation from LLM | `chat` or `text_completion` |
| **SQL Execution** | SQL generated and executed by Cortex Analyst | `execute_tool` (tool type: `datastore`) |
| **Chart Generation** | Visualization generation | `execute_tool` |
| **User Feedback** | Feedback on agent responses (`RECORD:name='CORTEX_AGENT_FEEDBACK'`) | N/A — OTel span event or separate log |

**Query pattern:**
```sql
SELECT * FROM TABLE(
  SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<database_name>', '<schema_name>', '<agent_name>', 'CORTEX AGENT'
  )
)
```

#### B. TruLens-Instrumented Applications (SDK — Developer-Configured)

[AI Observability](https://docs.snowflake.com/en/user-guide/snowflake-cortex/ai-observability) uses the [TruLens SDK](https://trulens.org) to instrument external GenAI apps (RAG pipelines, summarizers, etc.). The SDK provides:

| TruLens Span Type | Description | OTel GenAI Equivalent |
|---|---|---|
| `RECORD_ROOT` | Entry point of the application | `invoke_agent` or root span |
| `RETRIEVAL` | Search/retrieval function (e.g., Cortex Search) | `execute_tool` (tool type: `datastore`) |
| `GENERATION` | LLM inference call (e.g., Cortex COMPLETE) | `chat` or `text_completion` |
| `UNKNOWN` | Unclassified instrumented function | Generic `INTERNAL` span |

**TruLens Reserved Attributes (stored in RECORD_ATTRIBUTES):**

| TruLens Attribute | Description | OTel GenAI Mapping |
|---|---|---|
| `RECORD_ROOT.INPUT` | Input prompt to the LLM | `gen_ai.input.messages` (Opt-In) |
| `RECORD_ROOT.OUTPUT` | Generated response from LLM | `gen_ai.output.messages` (Opt-In) |
| `RECORD_ROOT.INPUT_ID` | Unique input identifier | `gen_ai.response.id` or custom attribute |
| `RECORD_ROOT.GROUND_TRUTH_OUTPUT` | Expected output (evaluation) | Custom: `snowflake.ai_obs.ground_truth` |
| `RETRIEVAL.QUERY_TEXT` | User query for RAG | Part of `gen_ai.input.messages` |
| `RETRIEVAL.RETRIEVED_CONTEXTS` | Retrieved context documents | Custom: `snowflake.ai_obs.retrieved_contexts` |

**TruLens Evaluation Metrics (stored in VALUE or RECORD_ATTRIBUTES):**

| Metric | OTel Convention | Notes |
|---|---|---|
| Context Relevance (0-1) | Custom: `snowflake.ai_obs.metric.context_relevance` | LLM-as-a-judge score |
| Groundedness (0-1) | Custom: `snowflake.ai_obs.metric.groundedness` | LLM-as-a-judge score |
| Answer Relevance (0-1) | Custom: `snowflake.ai_obs.metric.answer_relevance` | LLM-as-a-judge score |
| Correctness (0-1) | Custom: `snowflake.ai_obs.metric.correctness` | Against ground truth |
| Coherence (0-1) | Custom: `snowflake.ai_obs.metric.coherence` | Response quality |
| Usage Cost | `gen_ai.usage.input_tokens` + `gen_ai.usage.output_tokens` | From Cortex COMPLETE |
| Latency | Span duration (`START_TIMESTAMP` → `TIMESTAMP`) | Standard OTel span timing |

### 7.3 Event Table Columns → OTel GenAI Span Mapping

Since `AI_OBSERVABILITY_EVENTS` uses the standard event table structure, the column-level mapping follows the same pattern as §6 but targets `gen_ai.*` conventions:

| Event Table Column | Data Type | OTel GenAI Concept | App Action |
|---|---|---|---|
| `TIMESTAMP` | TIMESTAMP_NTZ | Span end time | **Direct** |
| `START_TIMESTAMP` | TIMESTAMP_NTZ | Span start time | **Direct** |
| `TRACE` | OBJECT | `{ trace_id, span_id }` | **Direct** — 1:1 mapping |
| `RESOURCE_ATTRIBUTES` | OBJECT | Resource attributes (agent name, database, schema, user) | **Map** — see §7.4 |
| `SCOPE` | OBJECT | `InstrumentationScope` | **Direct** |
| `RECORD_TYPE` | STRING | `SPAN`, `SPAN_EVENT`, `LOG` | **Direct** — route by type |
| `RECORD` | OBJECT | Span name, kind, status, parent_span_id | **Enrich** — see §7.5 |
| `RECORD_ATTRIBUTES` | OBJECT | GenAI-specific attributes (inputs, outputs, tool calls) | **Map** — see §7.6 |
| `VALUE` | VARIANT | Evaluation scores, additional metadata | **Preserve** as custom attributes |

### 7.4 RESOURCE_ATTRIBUTES → OTel Resource + GenAI Attributes

**Expected RESOURCE_ATTRIBUTES for Cortex Agent spans:**

| Snowflake Resource Attribute | OTel GenAI Target | App Action |
|---|---|---|
| `snow.database.name` | `db.namespace` (if DB context relevant) | **Alias** |
| `snow.schema.name` | Resource attribute | **Preserve** as `snowflake.schema.name` |
| `snow.executable.name` (agent name) | `gen_ai.agent.name` | **Enrich** |
| `db.user` | `enduser.id` | **Direct** |
| `snow.query.id` | `snowflake.query.id` | **Preserve** |
| Agent object identifier | `gen_ai.agent.id` | **Enrich** (from agent metadata) |

**App enrichment (always set):**

| OTel Attribute | Value | Source |
|---|---|---|
| `gen_ai.provider.name` | `"snowflake"` | **Constant** — Snowflake is not yet in OTel well-known providers, use custom value |
| `gen_ai.system.name` | `"snowflake_cortex"` | **Constant** |
| `service.name` | `"snowflake-cortex-agent"` or app-specific | **Enriched** from agent metadata |

### 7.5 RECORD Column → OTel Span Fields (GenAI Context)

For SPAN records, `RECORD` contains the same structure as the standard event table:

| RECORD Field | OTel GenAI Span Field | Enrichment Strategy |
|---|---|---|
| `name` | `Span.name` | **Enrich** — rewrite to `{gen_ai.operation.name} {target}` format |
| `kind` | `SpanKind` | **Direct** (`CLIENT` for remote agent calls, `INTERNAL` for local tool execution) |
| `status` | `SpanStatus` | **Direct** |
| `parent_span_id` | `parent_span_id` | **Direct** |

**Span Naming Enrichment (Cortex Agent spans):**

| Snowflake RECORD.name Pattern | OTel Span Name | `gen_ai.operation.name` |
|---|---|---|
| Agent invocation root span | `invoke_agent {agent_name}` | `invoke_agent` |
| LLM planning step | `chat {model_name}` | `chat` |
| Cortex Search tool call | `execute_tool cortex_search` | `execute_tool` |
| Cortex Analyst tool call | `execute_tool cortex_analyst` | `execute_tool` |
| Web search tool call | `execute_tool web_search` | `execute_tool` |
| Custom tool (UDF/SP) call | `execute_tool {tool_name}` | `execute_tool` |
| LLM response generation | `chat {model_name}` | `chat` |
| SQL execution | `execute_tool sql_execution` | `execute_tool` |
| Feedback record | N/A (not a span — log/event) | N/A |

**TruLens Span Naming:**

| TruLens Span Type | OTel Span Name | `gen_ai.operation.name` |
|---|---|---|
| `RECORD_ROOT` | `invoke_agent {app_name}` | `invoke_agent` |
| `RETRIEVAL` | `execute_tool {retriever_name}` | `execute_tool` |
| `GENERATION` | `chat {model_name}` | `chat` |
| `UNKNOWN` | Preserve original function name | (omit or use custom) |

### 7.6 RECORD_ATTRIBUTES → OTel GenAI Span Attributes

**Cortex Agent trace attributes (inferred from documented span content):**

| Snowflake RECORD_ATTRIBUTE | OTel GenAI Attribute | Notes |
|---|---|---|
| Input/prompt content | `gen_ai.input.messages` (Opt-In) | Inputs for each span |
| Output/response content | `gen_ai.output.messages` (Opt-In) | Outputs for each span |
| Model name used | `gen_ai.request.model` | e.g., `"claude-3-5-sonnet"`, `"llama3.1-70b"` |
| Tool name | `gen_ai.tool.name` | For tool execution spans |
| Tool type | `gen_ai.tool.type` | `function`, `extension`, `datastore` |
| Tool call arguments | `gen_ai.tool.call.arguments` (Opt-In) | Parameters passed to tool |
| Tool call result | `gen_ai.tool.call.result` (Opt-In) | Result returned by tool |
| Token usage (input) | `gen_ai.usage.input_tokens` | From Cortex COMPLETE calls |
| Token usage (output) | `gen_ai.usage.output_tokens` | From Cortex COMPLETE calls |
| Thread/conversation ID | `gen_ai.conversation.id` | Cortex Agent thread ID |
| Feedback (positive/negative) | Custom: `snowflake.cortex_agent.feedback.type` | CORTEX_AGENT_FEEDBACK records |
| Feedback text | Custom: `snowflake.cortex_agent.feedback.text` | User-provided text feedback |
| Agent request ID | Custom: `snowflake.cortex_agent.request_id` | System-generated ID |

> **Important Caveat:** Snowflake has NOT published the exact RECORD_ATTRIBUTES schema for Cortex Agent spans. The above mapping is **inferred** from documented behavior ("inputs and outputs associated with each span", model names, tool names). The actual attribute keys used internally by Snowflake may differ. Once access to real data is available, this mapping must be validated empirically.

### 7.7 Evaluation Data → OTel Attributes

TruLens evaluation metrics do NOT have a direct OTel GenAI convention equivalent. They represent a Snowflake-specific "LLM-as-a-judge" evaluation framework. **Recommended mapping:**

| Evaluation Concept | Recommended OTel Attribute | Namespace |
|---|---|---|
| Evaluation run ID | `snowflake.ai_obs.run.id` | Custom |
| Evaluation run status | `snowflake.ai_obs.run.status` | Custom |
| Application name | `gen_ai.agent.name` or `service.name` | Standard |
| Application version | `service.version` | Standard |
| Metric: Context Relevance | `snowflake.ai_obs.metric.context_relevance` | Custom |
| Metric: Groundedness | `snowflake.ai_obs.metric.groundedness` | Custom |
| Metric: Answer Relevance | `snowflake.ai_obs.metric.answer_relevance` | Custom |
| Metric: Correctness | `snowflake.ai_obs.metric.correctness` | Custom |
| Metric: Coherence | `snowflake.ai_obs.metric.coherence` | Custom |
| LLM Judge model | `snowflake.ai_obs.judge.model` | Custom |

### 7.8 Gap Analysis

#### OTel GenAI attributes NOT available in AI_OBSERVABILITY_EVENTS

| OTel Attribute | Status | Mitigation |
|---|---|---|
| `gen_ai.provider.name` | **Gap** — Snowflake not in OTel well-known providers | App enriches with `"snowflake"` |
| `gen_ai.request.temperature` | **Gap** — Not surfaced in event table | Cannot enrich without API access |
| `gen_ai.request.max_tokens` | **Gap** — Not surfaced in event table | Cannot enrich without API access |
| `gen_ai.request.top_p` | **Gap** — Not surfaced in event table | Cannot enrich without API access |
| `gen_ai.response.finish_reasons` | **Gap** — Not surfaced in event table | Cannot enrich |
| `gen_ai.system_instructions` | **Gap** — Agent instructions not in traces | Cannot enrich from event data |
| `server.address` | **Gap** — Internal Snowflake service | Not applicable |

#### Snowflake AI Observability data with NO OTel equivalent

| Snowflake Concept | Proposed Custom Attribute | Notes |
|---|---|---|
| TruLens evaluation scores | `snowflake.ai_obs.metric.*` | Unique to LLM-as-a-judge pattern |
| Ground truth output | `snowflake.ai_obs.ground_truth` | Evaluation-specific |
| Retrieved contexts (array) | `snowflake.ai_obs.retrieved_contexts` | Could map to future OTel RAG convention |
| EXTERNAL AGENT object | `snowflake.ai_obs.external_agent` | Snowflake-specific object type |
| Agent request feedback | `snowflake.cortex_agent.feedback.*` | Snowflake-specific |
| Data source ID | `gen_ai.data_source.id` | Available in OTel (Development) |

#### Detailed RECORD_ATTRIBUTES schema NOT publicly documented

The most significant gap is that **Snowflake has not published the exact attribute keys** used within `RECORD` and `RECORD_ATTRIBUTES` for Cortex Agent spans. The documentation describes what information is collected at a high level (inputs, outputs, tool names, model names) but does not enumerate the JSON keys. This means:

1. **MVP approach:** Preserve all attributes as-is under `snowflake.cortex_agent.*` namespace
2. **Validation required:** Once real data access is available, empirically inspect actual rows from `GET_AI_OBSERVABILITY_EVENTS()` to validate and refine the mapping
3. **Adaptive mapping:** The app's enrichment pipeline should detect known keys and map them to `gen_ai.*` attributes while preserving unknown keys under the custom namespace

### 7.9 Complete Enrichment Flow (Cortex Agent Example)

**Raw AI_OBSERVABILITY_EVENTS row (Cortex Agent — LLM response generation span):**
```
TIMESTAMP           = 2026-02-17 10:30:05.123
START_TIMESTAMP     = 2026-02-17 10:30:04.500
TRACE               = { "trace_id": "abc123...", "span_id": "def456..." }
RESOURCE_ATTRIBUTES = {
  "snow.database.name": "ANALYTICS_DB",
  "snow.schema.name": "AI_AGENTS",
  "snow.executable.name": "SALES_ASSISTANT_AGENT",
  "db.user": "ANALYST_USER"
}
RECORD_TYPE         = "SPAN"
RECORD              = {
  "name": "llm_response_generation",
  "kind": 3,
  "status": { "status_code": "STATUS_CODE_UNSET" },
  "parent_span_id": "parent789..."
}
RECORD_ATTRIBUTES   = {
  "model": "claude-3-5-sonnet",
  "input_tokens": 1250,
  "output_tokens": 380,
  "thread_id": "thread_abc123"
}
```

**Enriched OTel GenAI Span:**
```
Span.name            = "chat claude-3-5-sonnet"          ← ENRICHED
Span.kind            = CLIENT                            ← DIRECT
Span.status          = STATUS_CODE_UNSET                 ← DIRECT
Span.start_time      = 2026-02-17T10:30:04.500Z          ← DIRECT
Span.end_time        = 2026-02-17T10:30:05.123Z          ← DIRECT
trace_id             = "abc123..."                        ← DIRECT
span_id              = "def456..."                        ← DIRECT
parent_span_id       = "parent789..."                     ← DIRECT

-- Resource Attributes --
service.name         = "snowflake-cortex-agent"           ← ENRICHED
db.namespace         = "ANALYTICS_DB"                     ← ALIASED from snow.database.name

-- Span Attributes --
gen_ai.operation.name    = "chat"                         ← ENRICHED
gen_ai.provider.name     = "snowflake"                    ← ENRICHED (constant)
gen_ai.request.model     = "claude-3-5-sonnet"            ← MAPPED from RECORD_ATTRIBUTES.model
gen_ai.agent.name        = "SALES_ASSISTANT_AGENT"        ← MAPPED from snow.executable.name
gen_ai.usage.input_tokens  = 1250                         ← MAPPED from RECORD_ATTRIBUTES
gen_ai.usage.output_tokens = 380                          ← MAPPED from RECORD_ATTRIBUTES
gen_ai.conversation.id   = "thread_abc123"                ← MAPPED from RECORD_ATTRIBUTES.thread_id
snowflake.schema.name    = "AI_AGENTS"                    ← PRESERVED
snowflake.query.id       = (from resource if present)     ← PRESERVED
snowflake.handler.name   = "llm_response_generation"      ← PRESERVED (original RECORD.name)
```

### 7.10 Implications for App Architecture

1. **Dual Event Table Collection:** The app must implement a **second collector** for `SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS`, using `GET_AI_OBSERVABILITY_EVENTS()` rather than direct `SELECT`.

2. **Different Privilege Model:** Collecting from AI_OBSERVABILITY_EVENTS requires `MONITOR` or `OWNERSHIP` on each AGENT object plus the `CORTEX_USER` database role — different from standard event table privileges.

3. **Convention Router:** The enrichment pipeline must detect whether a span originates from Cortex Agent / AI Observability (→ `gen_ai.*` enrichment) or from standard stored procedures/UDFs (→ `db.*` enrichment). A convention router based on data source is essential.

4. **Schema Discovery Phase:** Since the detailed RECORD_ATTRIBUTES schema is not publicly documented, the MVP should implement a **discovery/validation phase** that inspects actual data and logs unknown attribute keys for future mapping refinement.

5. **Export Path:** GenAI spans from this table should flow through OTLP/gRPC → Splunk APM alongside DB spans, but with `gen_ai.*` attributes that enable GenAI-specific views in Splunk (AI-specific dashboards, token usage tracking, agent workflow visualization).

---

## 8. Splunk CIM Data Model Mapping for ACCOUNT_USAGE Pipeline (HEC)

The ACCOUNT_USAGE pipeline exports structured JSON events to Splunk via HEC. While OTel semantic conventions govern the Event Table pipeline (OTLP), the **Splunk Common Information Model (CIM)** governs how ACCOUNT_USAGE data should be normalized for Splunk Platform consumers (Enterprise Security, ITSI, CIM-aware apps and dashboards).

Reference: [Splunk CIM Add-on v6.4](https://help.splunk.com/en/data-management/common-information-model/6.4/introduction/overview-of-the-splunk-common-information-model)

### 8.1 QUERY_HISTORY → [Databases](https://help.splunk.com/en/data-management/common-information-model/6.4/data-models/databases) CIM Model — EXCELLENT FIT

**MVP-critical.** QUERY_HISTORY is the highest-value ACCOUNT_USAGE view and maps directly to the Databases CIM model's `Database_Query` and `Query_Stats` datasets.

**Tags:** `database query` (constrains to Database_Query dataset)

| QUERY_HISTORY Column | CIM Field | CIM Dataset | Notes |
|---|---|---|---|
| `QUERY_TEXT` | `query` | Database_Query | Full SQL text |
| `QUERY_ID` | `query_id` | Database_Query | Unique query identifier |
| `START_TIME` | `query_time` | Database_Query | Query initiation timestamp |
| `ROWS_PRODUCED` | `records_affected` | Database_Query | Rows returned/affected |
| `TOTAL_ELAPSED_TIME` (ms→s) | `duration` | All_Databases | Convert to seconds |
| `COMPILATION_TIME` (ms→s) | `response_time` | All_Databases | Time to first response |
| `USER_NAME` | `user` | All_Databases | Database process user |
| `WAREHOUSE_NAME` | `dest` | All_Databases | Execution destination |
| `DATABASE_NAME` | `object` | All_Databases | Database object name |
| `EXECUTION_STATUS` | maps to event tag / status field | — | SUCCESS, FAIL, INCIDENT |
| Tables accessed (if available) | `tables_hit` | Query_Stats | Tables hit by query |
| `QUERY_TYPE` | Custom field (no direct CIM equivalent) | — | SELECT, INSERT, CREATE, etc. |
| — | `vendor_product` = `"Snowflake"` | All_Databases | Always set |

**Sourcetype:** `snowflake:query_history`

**Example HEC event with CIM normalization:**
```json
{
  "sourcetype": "snowflake:query_history",
  "event": {
    "query": "SELECT * FROM orders WHERE ...",
    "query_id": "01b3f4a2-0000-...",
    "query_time": "2026-02-17T10:30:00Z",
    "records_affected": 1523,
    "duration": 2.45,
    "response_time": 0.12,
    "user": "ANALYST_USER",
    "dest": "COMPUTE_WH",
    "object": "ANALYTICS_DB",
    "vendor_product": "Snowflake"
  }
}
```

### 8.2 LOGIN_HISTORY → [Authentication](https://help.splunk.com/en/data-management/common-information-model/6.4/data-models/authentication) CIM Model — EXCELLENT FIT

**Security-critical.** LOGIN_HISTORY maps perfectly to the Authentication CIM model. This enables Snowflake login data to appear in Splunk Enterprise Security authentication dashboards, correlation searches, and UBA.

**Tags:** `authentication` (constrains to Authentication dataset)

| LOGIN_HISTORY Column | CIM Field | Notes |
|---|---|---|
| `USER_NAME` | `user` | User logging in (recommended, required for pytest) |
| `IS_SUCCESS` = `'YES'` → `success`, `'NO'` → `failure` | `action` | Prescribed CIM values (recommended, required) |
| `CLIENT_IP` | `src` | Source IP of auth attempt (recommended) |
| `REPORTED_CLIENT_TYPE` | `app` | `SNOWFLAKE_UI`, `JDBC_DRIVER`, `ODBC_DRIVER`, `PYTHON_DRIVER`, etc. (recommended, required) |
| Snowflake account endpoint | `dest` | Authentication target (recommended) |
| `FIRST_AUTHENTICATION_FACTOR` | `authentication_method` | `PASSWORD`, `KEYPAIR`, `OAUTH_ACCESS_TOKEN`, etc. (optional) |
| `ERROR_CODE` | `signature_id` | Numeric error code on failure |
| `ERROR_MESSAGE` | `signature` | Human-readable error description |
| `EVENT_TYPE` (`LOGIN` / `LOGOUT`) | Maps to event segmentation | Could split into separate events |
| — | `vendor_product` = `"Snowflake"` | Always set |

**Sourcetype:** `snowflake:login_history`

### 8.3 ACCESS_HISTORY → [Data Access](https://help.splunk.com/en/data-management/common-information-model/6.4/data-models/data-access) CIM Model — EXCELLENT FIT

**Governance-critical.** ACCESS_HISTORY tracks which users accessed which tables/columns — mapping directly to the Data Access CIM model's intent of detecting "unauthorized data access, misuse, exfiltration."

**Tags:** `data access` (constrains to Data_Access dataset)

| ACCESS_HISTORY Column | CIM Field | Notes |
|---|---|---|
| `USER_NAME` | `user` | User who accessed data (recommended) |
| `DIRECT_OBJECTS_ACCESSED[].objectName` | `object` | Table/view name accessed (recommended) |
| `DIRECT_OBJECTS_ACCESSED[].objectDomain` | `object_category` | `Table`, `View`, `Stage`, `Stream`, etc. (recommended) |
| `DIRECT_OBJECTS_ACCESSED[].columns[].columnName` | `object_attrs` | Specific columns read (recommended) |
| `BASE_OBJECTS_ACCESSED[].objectName` | `parent_object` | Underlying base objects |
| `QUERY_ID` | `object_id` | Query that triggered the access (recommended) |
| `DATABASE_NAME` + `SCHEMA_NAME` | `dest` | Where data resides (recommended) |
| Query type → `action` mapping | `action` | `read` (SELECT), `modified` (UPDATE), `created` (INSERT), `deleted` (DELETE) (recommended) |
| Snowflake account | `vendor_account` | Account context (recommended) |
| — | `vendor_product` = `"Snowflake"` | Always set (recommended) |

**Sourcetype:** `snowflake:access_history`

### 8.4 GRANTS_TO_ROLES / GRANTS_TO_USERS → [Change](https://help.splunk.com/en/data-management/common-information-model/6.4/data-models/change) CIM Model — EXCELLENT FIT

**Security-critical.** Grant/revoke operations map to the Change model's `Account_Management` dataset. Enables Splunk ES to detect privilege escalation, unauthorized grants, and policy violations.

**Tags:** `change account` (constrains to Account_Management dataset)

| GRANTS Column | CIM Field | CIM Dataset | Notes |
|---|---|---|---|
| `GRANTEE_NAME` | `user` | All_Changes | Account that was changed (recommended, required) |
| `GRANTED_BY` / `MODIFIED_BY` | `src_user` | Account_Management | User performing the change (recommended) |
| `PRIVILEGE` | `object` | All_Changes | e.g., `SELECT`, `USAGE`, `OWNERSHIP` (recommended, required) |
| `GRANTED_ON_TYPE` | `object_category` | All_Changes | `TABLE`, `SCHEMA`, `DATABASE`, `WAREHOUSE`, `ROLE` (recommended, required) |
| `TABLE_NAME` / `NAME` | `object_id` | All_Changes | Specific object affected (recommended, required) |
| GRANT → `created`, REVOKE → `deleted` | `action` | All_Changes | Prescribed CIM values (recommended, required) |
| `"AAA"` or `"account"` | `change_type` | All_Changes | Auth/Authorization/Accounting (recommended, required) |
| `"success"` | `status` | All_Changes | Grants in ACCOUNT_USAGE are successful (recommended, required) |
| Snowflake account | `vendor_account` | All_Changes | Account context |
| — | `vendor_product` = `"Snowflake"` | All_Changes | Always set (recommended, required) |

**Sourcetype:** `snowflake:grants`

### 8.5 TASK_HISTORY & SESSIONS → [Databases](https://help.splunk.com/en/data-management/common-information-model/6.4/data-models/databases) CIM Model — GOOD FIT

**TASK_HISTORY** maps to `Database_Query` (tasks execute SQL):

| TASK_HISTORY Column | CIM Field | Notes |
|---|---|---|
| `QUERY_ID` | `query_id` | Task's query ID |
| `DATABASE_NAME` | `object` | Database context |
| `NAME` (task name) | Custom: `task_name` | No direct CIM field |
| `STATE` | Custom: `task_state` | `SUCCEEDED`, `FAILED`, `SKIPPED` |
| `SCHEDULED_TIME` / `COMPLETED_TIME` | `query_time` / `duration` | Timing |

**SESSIONS** maps to `Session_Info`:

| SESSIONS Column | CIM Field | Notes |
|---|---|---|
| `SESSION_ID` | `session_id` | Session identifier |
| `USER_NAME` | `user` | Session user |
| `LOGIN_EVENT_ID` | Links to LOGIN_HISTORY | Cross-reference |
| `CLIENT_APPLICATION_ID` | `machine` | Client app |

**Tags:** `database query` (tasks), `database session` (sessions)
**Sourcetypes:** `snowflake:task_history`, `snowflake:sessions`

### 8.6 No Clean CIM Match — Custom Sourcetypes Only

These ACCOUNT_USAGE views carry operational/billing data with no CIM model equivalent. They ship as custom sourcetypes with Snowflake-specific field names.

| ACCOUNT_USAGE View | Why No CIM Fit | Sourcetype |
|---|---|---|
| **METERING_HISTORY** | Cloud credit/billing — no CIM cost model | `snowflake:metering_history` |
| **STORAGE_USAGE** | Storage billing metrics | `snowflake:storage_usage` |
| **WAREHOUSE_METERING_HISTORY** | Warehouse credit consumption (billing) | `snowflake:warehouse_metering` |
| **COPY_HISTORY** | Data loading operations | `snowflake:copy_history` |
| **PIPE_USAGE_HISTORY** | Snowpipe billing | `snowflake:pipe_usage` |
| **REPLICATION_USAGE_HISTORY** | Replication billing | `snowflake:replication_usage` |

### 8.7 CIM Mapping Summary

| ACCOUNT_USAGE View | CIM Data Model | CIM Dataset(s) | Fit | Tags | Sourcetype |
|---|---|---|---|---|---|
| **QUERY_HISTORY** | **Databases** | Database_Query, Query_Stats | Excellent | `database query` | `snowflake:query_history` |
| **LOGIN_HISTORY** | **Authentication** | Authentication | Excellent | `authentication` | `snowflake:login_history` |
| **ACCESS_HISTORY** | **Data Access** | Data_Access | Excellent | `data access` | `snowflake:access_history` |
| **GRANTS_TO_**** | **Change** | Account_Management | Excellent | `change account` | `snowflake:grants` |
| **TASK_HISTORY** | **Databases** | Database_Query | Good | `database query` | `snowflake:task_history` |
| **SESSIONS** | **Databases** | Session_Info | Good | `database session` | `snowflake:sessions` |
| **METERING_HISTORY** | None | — | N/A | — | `snowflake:metering_history` |
| **STORAGE_USAGE** | None | — | N/A | — | `snowflake:storage_usage` |
| **WAREHOUSE_METERING** | None | — | N/A | — | `snowflake:warehouse_metering` |

**Why CIM compliance matters:** CIM-normalized data automatically surfaces in Splunk Enterprise Security dashboards (authentication events, change tracking), ITSI service monitoring, and any CIM-accelerated search. This gives customers immediate out-of-the-box value without building custom dashboards for every Snowflake data source.

---

## 9. Comprehensive Convention Applicability Matrix

| OTel Convention Area | Applicable? | For Which Snowflake Services | Stability | Role |
|---|---|---|---|---|
| **Database Client** (`db.*`) | **Yes — Primary** | Stored Procs, UDFs, SQL Queries; also as execution context for all | Stable | Primary + Context |
| **Generative AI** (`gen_ai.*`) | **Yes — Primary** | Cortex LLM Functions, Cortex Agents, Cortex Search, Cortex Analyst, Document AI, custom GenAI apps | Development | Primary for AI workloads |
| **K8s Resource** (`k8s.*`) | **Yes — As-is relay** | Openflow, Snowpark Container Services | Development | Preserved from source |
| **Container Resource** (`container.*`) | **Yes — As-is relay** | Openflow, Snowpark Container Services | Development | Preserved from source |
| **HTTP** (`http.*`) | **Yes — Secondary** | External Functions, app's own exporter spans | Stable | Supplementary |
| **Exceptions** (`exception.*`) | **Yes — Cross-cutting** | All services — error details on any span | Stable | Error enrichment |
| **Service Resource** (`service.*`) | **Yes — Required** | All telemetry — identifies the app | Stable | Required |
| **Cloud Resource** (`cloud.*`) | **Yes — Required** | All telemetry — identifies the platform | Development | Required |
| Custom `snowflake.*` | **Yes — Required** | All relayed telemetry — Snowflake-specific context | Custom | Required |
| **Messaging** (`messaging.*`) | No | Streams are change-tracking, not message queues | — | — |
| **RPC** (`rpc.*`) | Marginal | Only for app's own OTLP/gRPC exporter spans | Stable | Internal only |
| **FaaS** (`faas.*`) | No | Semantic mismatch, Development status, no Splunk DB alignment | Development | Rejected |
| **CI/CD** (`cicd.*`) | No | Tasks are not CI/CD pipelines | — | — |
| **CloudEvents** | No | Event Tables are not CloudEvents | — | — |
| **Feature Flags** | No | Not applicable | — | — |
| **Browser / Mobile** | No | Not applicable | — | — |
| **GraphQL** | No | Not applicable | — | — |
| **Object Stores** | No | Stages could loosely map, but too tangential | — | — |
| **DNS / NFS / Hardware** | No | Infrastructure internals not exposed | — | — |

---

## 10. Key References

### OTel Semantic Conventions
- [Database Client Spans (Stable)](https://opentelemetry.io/docs/specs/semconv/db/database-spans/) — span definition, naming, attributes, sanitization
- [SQL Semantic Conventions (Stable)](https://opentelemetry.io/docs/specs/semconv/db/sql/) — SQL-specific attributes and span naming
- [OTel Trace API — Span Naming Rules (v1.53.0)](https://github.com/open-telemetry/opentelemetry-specification/blob/v1.53.0/specification/trace/api.md#span) — general span naming guidelines
- [Database Client Spans (GitHub)](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/db/database-spans.md)
- [Database Client Metrics (Stable core)](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/db/database-metrics.md)
- [SQL Conventions (GitHub)](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/db/sql.md)
- [DB Migration Guide (v1.24→v1.33)](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/non-normative/db-migration.md)
- [GenAI Model Spans (Development)](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-spans.md)
- [GenAI Agent Spans (Development)](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-agent-spans.md)
- [GenAI Metrics (Development)](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-metrics.md)
- [GenAI Events (Development)](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-events.md)
- [MCP Conventions (Development)](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/mcp.md)
- [Service Resource (Stable)](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/resource/service.md)
- [Cloud Resource (Development)](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/resource/cloud.md)

### Snowflake Documentation
- [Event Table Columns](https://docs.snowflake.com/en/developer-guide/logging-tracing/event-table-columns) — complete schema definition for all Event Table columns
- [Viewing Trace Data](https://docs.snowflake.com/en/developer-guide/logging-tracing/tracing-trace-data) — querying Event Table for trace entries
- [SQL Statement Tracing](https://docs.snowflake.com/en/developer-guide/logging-tracing/tracing-sql) — SQL_TRACE_QUERY_TEXT parameter and SQL trace data in Event Table
- [AI Observability in Snowflake Cortex](https://docs.snowflake.com/en/user-guide/snowflake-cortex/ai-observability) — AI Observability overview (TruLens-based evaluation & tracing)
- [AI Observability Reference](https://docs.snowflake.com/en/user-guide/snowflake-cortex/ai-observability/reference) — detailed reference for datasets, metrics, runs, access control, and observability data storage
- [Evaluate AI Applications](https://docs.snowflake.com/en/user-guide/snowflake-cortex/ai-observability/evaluate-ai-applications) — TruLens SDK instrumentation patterns, span types, reserved attributes
- [Monitor Cortex Agent Requests](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-monitor) — Cortex Agent monitoring, AI_OBSERVABILITY_EVENTS table, GET_AI_OBSERVABILITY_EVENTS function, access control
- [LOCAL Schema](https://docs.snowflake.com/en/sql-reference/snowflake-db/local) — SNOWFLAKE.LOCAL schema tables (AI_OBSERVABILITY_EVENTS, CORTEX_ANALYST_REQUESTS_RAW), views, and functions
- [Monitor Openflow](https://docs.snowflake.com/en/user-guide/data-integration/openflow/monitor) — confirms Openflow telemetry schema in Event Tables with k8s/container attributes
- [How Snowflake Represents Trace Events](https://docs.snowflake.com/en/developer-guide/logging-tracing/tracing-how-events-work) — Event Table OTel data model
- [Event Table Overview](https://docs.snowflake.com/en/developer-guide/logging-tracing/event-table-setting-up) — confirms Event Table structure supports OTel data model
- [AI Observability Blog (Aug 2025)](https://www.snowflake.com/en/blog/ai-observability-trust-cortex-enterprise/) — "OpenTelemetry traces" for Cortex Agent observability

### Snowflake in OTel Community
- [Issue #2583: Define Snowflake as a db system](https://github.com/open-telemetry/semantic-conventions/issues/2583) — Open, confirms community intent to add `snowflake` to `db.system.name`

### Splunk Alignment
- [Splunk Observability Aug 2025 — DB Convention Update](https://community.splunk.com/t5/Product-News-Announcements/What-s-New-in-Splunk-Observability-August-2025/ba-p/752193)
- [Splunk Release Notes — Updated DB Attributes](https://help.splunk.com/en/splunk-observability-cloud/release-notes/august-2025)

### Splunk Common Information Model (CIM)
- [CIM Add-on v6.4 Overview](https://help.splunk.com/en/data-management/common-information-model/6.4/introduction/overview-of-the-splunk-common-information-model)
- [Databases Data Model](https://help.splunk.com/en/data-management/common-information-model/6.4/data-models/databases)
- [Authentication Data Model](https://help.splunk.com/en/data-management/common-information-model/6.4/data-models/authentication)
- [Data Access Data Model](https://help.splunk.com/en/data-management/common-information-model/6.4/data-models/data-access)
- [Change Data Model](https://help.splunk.com/en/data-management/common-information-model/6.4/data-models/change)

---

## 11. Decision Summary

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  RECOMMENDED CONVENTION STACK FOR SNOWFLAKE TELEMETRY                        │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Layer 0 (Architecture):  Convention-Transparent Relay                        │
│  └─ Preserve ALL original attributes from Event Table producers              │
│     (never strip, never force-fit into a single convention)                  │
│                                                                              │
│  Layer 1 (Primary — DB):  Database Client (db.*)            [STABLE]        │
│  ├─ db.system.name = "snowflake" (ALWAYS, as platform context)              │
│  ├─ db.namespace, db.operation.name, db.query.text                          │
│  ├─ db.stored_procedure.name, db.collection.name                            │
│  ├─ db.response.status_code, error.type                                     │
│  └─ db.client.operation.duration metric                                     │
│                                                                              │
│  Layer 2 (Primary — AI):  Generative AI (gen_ai.*)          [DEVELOPMENT]   │
│  ├─ gen_ai.operation.name, gen_ai.request.model                             │
│  ├─ gen_ai.provider.name, gen_ai.usage.*                                    │
│  ├─ gen_ai.agent.name, gen_ai.agent.id (for Cortex Agents)                 │
│  └─ gen_ai events: input/output messages, tool calls                        │
│                                                                              │
│  Layer 3 (Infrastructure): K8s + Container (k8s.*, container.*)             │
│  ├─ k8s.pod.name, k8s.namespace.name, k8s.node.name                        │
│  ├─ container.id, container.image.name, container.image.tag                 │
│  └─ Openflow-specific: openflow.dataplane.id, processor.*, connection.*     │
│                                                                              │
│  Layer 4 (Resource):  Service + Cloud                       [STABLE]        │
│  ├─ service.name, service.namespace, service.version                        │
│  └─ cloud.provider, cloud.region, cloud.account.id                          │
│                                                                              │
│  Layer 5 (Custom):    snowflake.* namespace                 [CUSTOM]        │
│  ├─ snowflake.executable.name, snowflake.executable.type                    │
│  ├─ snowflake.query.id, snowflake.warehouse.name                            │
│  ├─ snowflake.user, snowflake.owner, snowflake.session.role                 │
│  └─ snowflake.account.name                                                  │
│                                                                              │
│  Cross-cutting: Exceptions (exception.*, error.type)        [STABLE]        │
│                                                                              │
│  NOT USED:                                                                   │
│  ├─ FaaS (faas.*) — semantic mismatch with Snowflake model                  │
│  ├─ Messaging (messaging.*) — Streams ≠ message queues                      │
│  ├─ CI/CD (cicd.*) — Tasks ≠ CI/CD pipelines                               │
│  └─ CloudEvents, Feature Flags, Browser, Mobile — not applicable            │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 12. Implications for App Architecture

1. **TWO Event Table data sources.** The app must collect from both the customer's standard event table (stored procs, UDFs, Openflow, etc. → `db.*` enrichment) AND `SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS` (Cortex Agents, AI Observability → `gen_ai.*` enrichment). These require different access patterns and privileges (see §7.1).

2. **Convention-aware routing.** A **convention router** must detect whether a span originates from standard event table (→ `db.*` enrichment) or AI_OBSERVABILITY_EVENTS (→ `gen_ai.*` enrichment). This is determined by data source, not by parsing attributes.

3. **Enrichment is additive.** Always add `db.system.name = "snowflake"` (for DB spans), `gen_ai.provider.name = "snowflake"` (for GenAI spans), `snowflake.*` context, `service.*`, and `cloud.*` — but never overwrite existing attributes.

4. **Export routing remains the same.** Spans/metrics → OTLP/gRPC, Logs → HEC — regardless of which convention the spans use.

5. **Splunk will render each convention appropriately.** DB Client spans → DB monitoring views. GenAI spans → APM trace waterfall with GenAI attributes. Openflow metrics → custom dashboards.

6. **ACCOUNT_USAGE HEC events must be CIM-normalized.** Map fields to CIM-compliant names at export time (e.g., `USER_NAME` → `user`, `QUERY_TEXT` → `query`) and set correct `sourcetype` and CIM tags per view. This ensures automatic surface in Splunk Enterprise Security, ITSI, and CIM-accelerated searches.

7. **Triple normalization model.** Standard event table = OTel `db.*` conventions. AI_OBSERVABILITY_EVENTS = OTel `gen_ai.*` conventions. ACCOUNT_USAGE pipeline = Splunk CIM (HEC). Each pipeline uses the normalization standard native to its data domain and target consumer.

8. **Schema discovery for AI_OBSERVABILITY_EVENTS.** Since the detailed RECORD_ATTRIBUTES schema for Cortex Agent spans is not publicly documented, the MVP must include a discovery phase that inspects real data and adaptively maps known keys to `gen_ai.*` while preserving unknown keys as `snowflake.cortex_agent.*`.

9. **Future-proof.** As Snowflake adds more services (more AI features, Snowflake Postgres, etc.), their telemetry will flow through Event Tables. The convention-transparent architecture handles this without app changes.
