# Event Table Entity Discrimination Strategy — MVP Filtering for SQL/Snowpark Compute

**Date:** 2026-02-18
**Context:** Splunk Observability Native App for Snowflake — How to isolate SQL/Snowpark compute telemetry in the shared event table, excluding SPCS, Streamlit, Openflow, Cortex, Iceberg, and future entity types. Supports incremental addition of service categories post-MVP.

---

## 1. The Problem

Snowflake's event table is a **shared telemetry sink**. Every service category writes logs, traces, and metrics into the same table:

| Service Category | Entity Types | Writes To Event Table |
|---|---|---|
| **SQL/Snowpark compute** (MVP) | Stored Procedures, UDFs/UDTFs, SQL Queries | Yes |
| Snowpark Container Services (SPCS) | Services, Jobs | Yes |
| Streamlit in Snowflake | Streamlit apps | Yes |
| Openflow | Data pipelines/CDC | Yes |
| Iceberg Automated Refresh | Iceberg tables | Yes |
| Native Apps | Provider/consumer apps | Yes (with app-specific resource attrs) |
| Cortex AI | Agents, LLM functions, AI Observability | **Separate table** (`SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS`) |

**MVP Goal:** Collect ONLY SQL/Snowpark compute telemetry (Stored Procedures, UDFs/UDTFs, Queries) and transform to OTLP with `db.*` semantic conventions. Exclude everything else.

**Post-MVP:** Incrementally add SPCS, Streamlit, Openflow, Cortex as separate service categories / monitoring packs.

---

## 2. Primary Discriminator: `RESOURCE_ATTRIBUTES:"snow.executable.type"`

The `RESOURCE_ATTRIBUTES` column is set by Snowflake and **cannot be changed by user code**. The `snow.executable.type` attribute is the primary discriminator across entity types.

### Documented Values of `snow.executable.type`

| Value | Service Category | MVP Scope |
|---|---|---|
| `procedure` | SQL/Snowpark — Stored Procedure | **IN SCOPE** |
| `function` | SQL/Snowpark — UDF/UDTF | **IN SCOPE** |
| `query` | SQL/Snowpark — SQL executed within a procedure | **IN SCOPE** |
| `sql` | SQL/Snowpark — Single SQL query (Snowflake Scripting block) | **IN SCOPE** |
| `spcs` | Snowpark Container Services | OUT OF SCOPE |
| `streamlit` | Streamlit in Snowflake | OUT OF SCOPE |

**Source:** [Event Table Columns — RESOURCE_ATTRIBUTES](https://docs.snowflake.com/en/developer-guide/logging-tracing/event-table-columns#resource-attributes-for-event-source)

### Key Insight
`snow.executable.type` is sufficient as the sole filter for MVP scope. The four in-scope values (`procedure`, `function`, `query`, `sql`) cover all SQL/Snowpark compute telemetry.

---

## 3. Secondary Discriminators: SPCS-Specific Resource Attributes

SPCS telemetry in the event table carries a **completely different set of resource attributes** that SQL/Snowpark compute does NOT have:

### SPCS-Only Resource Attributes (NOT present on SQL/Snowpark records)

| Attribute | Description | Example |
|---|---|---|
| `snow.service.name` | Service name | `ECHO_SERVICE` |
| `snow.service.id` | Service internal ID | `114` |
| `snow.service.type` | `Service` or `Job` | `Service` |
| `snow.service.container.name` | Container name | `echo` |
| `snow.service.container.instance` | Container instance ordinal | `0` |
| `snow.service.container.run.id` | Container run ID | `b30566` |
| `snow.compute_pool.name` | Compute pool name | `TUTORIAL_COMPUTE_POOL` |
| `snow.compute_pool.id` | Compute pool internal ID | `20` |
| `snow.compute_pool.node.id` | Node ID within compute pool | `a17e8157` |
| `snow.compute_pool.node.instance_family` | Instance family | `CPU_X64_XS` |
| `snow.account.name` | Account name (SPCS-specific) | `SPCSDOCS1` |

**Source:** [SPCS Monitoring — Resource Attributes](https://docs.snowflake.com/en/developer-guide/snowpark-container-services/monitoring-services)

### SQL/Snowpark-Only Resource Attributes (NOT present on SPCS records)

| Attribute | Description | Example |
|---|---|---|
| `snow.warehouse.name` | Warehouse executing the operation | `COMPUTE_WH` |
| `snow.warehouse.id` | Warehouse internal ID | `5` |
| `snow.session.id` | Session ID | `1275605667850` |
| `snow.session.role.primary.name` | Primary session role | `MY_ROLE` |
| `snow.owner.name` | Role with OWNERSHIP | `MY_ROLE` |
| `telemetry.sdk.language` | Handler language | `python`, `java`, `sql` |

### Comparison: Side-by-Side Resource Attributes

```
SQL/Snowpark (Stored Procedure)          SPCS (Container Service)
─────────────────────────────            ──────────────────────────
db.user: "ANALYST"                       snow.account.name: "ACCT1"
snow.database.name: "MY_DB"              snow.compute_pool.id: 20
snow.schema.name: "PUBLIC"               snow.compute_pool.name: "MY_POOL"
snow.executable.name: "MY_PROC(...)"     snow.compute_pool.node.id: "a17e..."
snow.executable.type: "procedure"  ←     snow.compute_pool.node.instance_family: "CPU_X64_XS"
snow.executable.id: 197                  snow.database.name: "MY_DB"
snow.owner.name: "MY_ROLE"              snow.schema.name: "MY_SCHEMA"
snow.query.id: "01ab..."                snow.service.container.instance: "0"
snow.session.id: 1275605667850          snow.service.container.name: "echo"
snow.session.role.primary.name: "..."   snow.service.container.run.id: "b30566"
snow.user.id: 25                        snow.service.id: 114
snow.warehouse.id: 5                    snow.service.name: "ECHO_SERVICE"
snow.warehouse.name: "COMPUTE_WH" ←    snow.service.type: "Service"  ←
telemetry.sdk.language: "python"  ←     snow.query.id: "01ab..."
```

---

## 4. Additional Discriminators by Service Category

### 4.1 Openflow
- `RESOURCE_ATTRIBUTES:application = "openflow"` (fixed identifier)
- Presence of `k8s.*` and `container.*` attributes (e.g., `k8s.pod.name`, `container.id`)
- Custom attributes: `openflow.dataplane.id`, `cloud.service.provider`

### 4.2 SPCS Platform Events
- `RECORD_TYPE = 'EVENT'`
- `SCOPE:"name" = 'snow.spcs.platform'`
- `RECORD:"name"` values like `CONTAINER.STATUS_CHANGE`

### 4.3 SPCS Platform Metrics (vs SQL/Snowpark Metrics)
- SPCS metrics: `SCOPE:"name" = 'snow.spcs.platform'`, metric names like `container.cpu.usage`, `container.memory.usage`
- SQL/Snowpark metrics: `RECORD:"metric.name"` in (`process.memory.usage`, `process.cpu.utilization`), NO `snow.service.*` attributes

### 4.4 SPCS Application Metrics/Traces (user-emitted)
- `RESOURCE_ATTRIBUTES:"snow.service.name"` IS NOT NULL
- `SCOPE:"name" != 'snow.spcs.platform'` (user scope, not platform)
- May have user-defined OTel attributes

### 4.5 Iceberg Automated Refresh Events
- `RECORD_TYPE = 'EVENT'`
- `RESOURCE_ATTRIBUTES:"snow.catalog.integration.name"` present
- `RESOURCE_ATTRIBUTES:"snow.catalog.table.name"` present
- `RECORD:"name" = 'iceberg_auto_refresh_snapshot_lifecycle'`

### 4.6 Cortex AI (Separate Table — No Collision)
- Stored in `SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS`, NOT the customer event table
- Accessed via `GET_AI_OBSERVABILITY_EVENTS()` table function
- No filtering needed in the standard event table pipeline

### 4.7 Streamlit Apps
- `RESOURCE_ATTRIBUTES:"snow.executable.type" = 'streamlit'`
- Streamlit apps use the same standard logging/tracing APIs and write to the same event table
- `SCOPE:"name"` may contain the logger name (e.g., `simple_logger`)

### 4.8 Native Apps
- Presence of `snow.application.*` resource attributes:
  - `snow.application.name`, `snow.application.id`
  - `snow.application.package.name`
  - `snow.application.consumer.name`, `snow.application.consumer.organization`
  - `snow.listing.name`, `snow.listing.global_name`

---

## 5. Recommended MVP Filtering Strategy

### 5.1 Primary Filter: Positive Include List (Recommended)

Use `snow.executable.type` as a **positive include list**. This is the safest approach because:
1. It explicitly selects only the entity types we want
2. It naturally excludes ALL other entity types (SPCS, Streamlit, Openflow, Iceberg, Native Apps, future types)
3. It is resilient to new entity types Snowflake may add in the future

```
Filter: RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING IN ('procedure', 'function', 'query', 'sql')
```

### 5.2 Alternative: Negative Exclude List (NOT recommended for MVP)

```
Filter: RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING NOT IN ('spcs', 'streamlit')
    AND RESOURCE_ATTRIBUTES:"snow.service.name" IS NULL
    AND RESOURCE_ATTRIBUTES:"application" IS NULL
```

**Why not:** Fragile — new entity types added by Snowflake would leak through unless the exclude list is maintained. The positive include list is safer.

### 5.3 Data Access Architecture: Custom Views + Streams

The app does NOT read directly from customer event tables. Instead, it follows a **layered data access pattern**:

```
Customer Event Table(s)
  │
  ├─ Custom View (created by Native App on top of user-selected event tables)
  │   ├─ Enables consumer-configured Row Access Policies
  │   ├─ Enables consumer-configured Masking Policies
  │   └─ Provides a governance-safe access layer
  │
  ├─ Stream (created on the Custom View, not the raw event table)
  │   └─ Captures incremental changes for event-driven processing
  │
  └─ Snowpark DataFrame reads from the Stream
      └─ Entity-type filter applied as Snowpark pushdown (first operation)
```

**Why Custom Views:** Snowflake consumers need to attach row access policies, masking policies, and other governance controls to the data the app reads. Creating a custom view on top of the user-selected event table(s) provides this intermediary governance layer — the consumer controls what the app can see.

### 5.4 Snowpark-First Processing Philosophy

All filtering, sorting, and data preparation happens through **Snowpark DataFrame operations**, not raw SQL. This is a deliberate architectural choice:

1. **Pushdown optimization** — Snowpark translates DataFrame operations into SQL that the Snowflake engine optimizes. The entity-type filter pushes down to the engine, minimizing data scanned from the Stream.
2. **Avoids custom view SQL constraints** — Complex SQL queries against views can hit limitations; Snowpark DataFrame operations compose cleanly and avoid these pitfalls.
3. **Separation of concerns** — Snowpark handles all relational work (filtering, projection, splitting by signal type). Python stored procedures only receive already-filtered, ready-to-convert DataFrames and handle the OTLP serialization + export.

**Processing chain:**
- **Snowpark layer:** Entity-type filter → signal-type split (SPAN/LOG/METRIC) → column projection → batching
- **Python SP layer:** Receives filtered DataFrames → OTel enrichment → OTLP/gRPC or HEC serialization → export to Splunk

### 5.5 Combined Filter Chain

```
Customer Event Table(s)
  │
  └─ Custom View (governance layer: RAP, masking, etc.)
      │
      └─ Stream (incremental change capture)
          │
          └─ Snowpark DataFrame Processing
              │
              ├─ Filter 1: snow.executable.type IN ('procedure','function','query','sql')
              │   → Excludes: SPCS, Streamlit, Openflow, Iceberg, Native Apps
              │
              ├─ Split by RECORD_TYPE (still Snowpark, still pushdown)
              │   ├─ SPAN / SPAN_EVENT → enrichment → OTLP/gRPC
              │   ├─ LOG               → formatting  → HEC HTTP
              │   └─ METRIC            → enrichment → OTLP/gRPC
              │
              └─ (Future: additional entity type filters for other service categories)
```

---

## 6. Incremental Service Category Addition (Post-MVP)

The architecture supports adding new service categories by introducing new filter branches, each with its own convention mapping:

### 6.1 Service Category Registry (Conceptual)

Each service category is defined by three elements: a **filter predicate** (which rows belong to this category), an **OTel convention** (how to enrich/map attributes), and a **data source** (which table/view to read from).

| Category | Filter Predicate | OTel Convention | Data Source | Status |
|---|---|---|---|---|
| **SQL/Snowpark** | `snow.executable.type` IN (`procedure`, `function`, `query`, `sql`) | `db.*` | Customer event table (via custom view + stream) | **MVP** |
| SPCS | `snow.service.name` IS NOT NULL | `k8s.*` + `container.*` | Customer event table (via custom view + stream) | Post-MVP |
| Streamlit | `snow.executable.type` = `streamlit` | `http.*` + custom | Customer event table (via custom view + stream) | Post-MVP |
| Openflow | `RESOURCE_ATTRIBUTES:application` = `openflow` | `k8s.*` + `container.*` + custom pipeline | Customer event table (via custom view + stream) | Post-MVP |
| Cortex AI | N/A (separate table) | `gen_ai.*` | `SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS` via `GET_AI_OBSERVABILITY_EVENTS()` | Post-MVP |

### 6.2 Adding a New Service Category Checklist

1. **Define the filter predicate** — which `RESOURCE_ATTRIBUTES` values identify this category
2. **Identify the OTel convention** — which semantic convention namespace applies
3. **Implement the enricher** — convention-specific attribute mapping/enrichment
4. **Register in the service category registry** — add filter + enricher + convention
5. **Update the Streamlit UI** — add the new category as a selectable monitoring pack
6. **Test with real data** — validate filter accuracy against actual event table rows

### 6.3 Filter Ordering and Mutual Exclusivity

The filters are **mutually exclusive by design** because `snow.executable.type` values do not overlap across categories:

| `snow.executable.type` | Category |
|---|---|
| `procedure`, `function`, `query`, `sql` | SQL/Snowpark (MVP) |
| `spcs` | SPCS |
| `streamlit` | Streamlit |

For Openflow, the discriminator is different (`RESOURCE_ATTRIBUTES:application = "openflow"`), but Openflow records do NOT have `snow.executable.type` set, so there is no overlap.

For Cortex AI, it uses a completely separate table, so no collision.

---

## 7. Edge Cases and Considerations

### 7.1 SQL Traced Within SPCS

If a Snowpark Container Services container calls a stored procedure or UDF, that inner procedure/UDF execution **will have its own event table rows** with `snow.executable.type = 'procedure'` or `'function'`. These would pass our MVP filter.

**Impact:** Low. The inner SP/UDF is a legitimate SQL/Snowpark compute event. The call chain (parent_span_id) links it to the SPCS context. In MVP, we collect it as a standalone DB span. Post-MVP, when SPCS is added, the parent-child span relationship can be reconstructed.

### 7.2 Streamlit Calling Stored Procedures

A Streamlit app calling a stored procedure generates two types of events:
- Streamlit app events: `snow.executable.type = 'streamlit'` → filtered OUT in MVP
- SP execution events: `snow.executable.type = 'procedure'` → filtered IN for MVP

**Impact:** Correct behavior. The SP execution is captured; the Streamlit app context is not (added post-MVP).

### 7.3 Native App Code Executing SPs/UDFs

Native App stored procedures have both `snow.executable.type = 'procedure'` AND `snow.application.*` attributes.

**Impact:** These pass the MVP filter, which is correct — they are SQL/Snowpark compute. The `snow.application.*` attributes are preserved as-is in the relay (convention-transparent). Post-MVP, a "Native Apps" service category can filter by `snow.application.name IS NOT NULL`.

### 7.4 RECORD_TYPE = 'EVENT' (Platform Events)

SPCS platform events use `RECORD_TYPE = 'EVENT'` and `SCOPE:"name" = 'snow.spcs.platform'`. Iceberg automated refresh also uses `RECORD_TYPE = 'EVENT'`.

**Impact:** Our MVP filter on `snow.executable.type` will exclude these because platform events have SPCS-specific or Iceberg-specific resource attributes, not `snow.executable.type` in our include list.

### 7.5 Metrics: SQL/Snowpark vs SPCS

- **SQL/Snowpark metrics:** `process.memory.usage`, `process.cpu.utilization` — with `snow.executable.type` in MVP include list
- **SPCS metrics:** `container.cpu.usage`, `container.memory.usage` — with `snow.service.name` present, NOT matching MVP filter

**Impact:** Correctly separated by the primary filter.

### 7.6 Volume and Cost Implications

Filtering early via Snowpark pushdown through the custom view + stream means:
- Only rows matching `snow.executable.type IN (...)` are scanned from the Stream
- SPCS telemetry (potentially very high volume — container metrics at up to 1 MB/s per node) is never read
- Openflow telemetry (potentially high volume from pipeline metrics) is never read
- Only SQL/Snowpark compute telemetry is processed and transformed

This is critical for cost optimization — the customer pays for serverless task compute, and Snowpark pushdown minimizes data scanned. The custom view layer adds no materialization cost (it's a logical view), and the stream only tracks incremental changes since the last consumption.

---

## 8. Validation Strategy

Filter accuracy should be validated during development and onboarding using Snowpark-based profiling:

1. **Entity type distribution** — Group by `snow.executable.type` and `RECORD_TYPE` to understand the composition of a customer's event table. This informs whether the MVP filter covers the expected workloads and confirms that non-target categories (SPCS, Streamlit, Openflow) are cleanly separated.

2. **Exclusion verification** — Confirm that rows with SPCS attributes (`snow.service.name`), Openflow attributes (`application = "openflow"`), and Iceberg events are NOT present in the filtered output.

3. **Unclassified row detection** — Identify rows that have no `snow.executable.type`, no `snow.service.name`, and no `application` attribute. These could be Snowflake-internal telemetry or future entity types. Understanding their volume and content informs whether the positive include filter is sufficient or needs refinement.

4. **Volume estimator integration** — The app's volume estimator (from vision doc `_internal.volume_estimator`) should run these profiling checks as Snowpark operations to project throughput for the customer's specific workload mix, without any raw SQL penalty.

All profiling uses the same Snowpark-first approach as the production pipeline — DataFrame operations against the custom view, with full pushdown to the Snowflake engine.

---

## 9. Key References

- [Event Table Columns](https://docs.snowflake.com/en/developer-guide/logging-tracing/event-table-columns) — complete schema with RESOURCE_ATTRIBUTES reference including `snow.executable.type` values
- [SPCS Monitoring](https://docs.snowflake.com/en/developer-guide/snowpark-container-services/monitoring-services) — SPCS resource attributes (`snow.service.*`, `snow.compute_pool.*`), platform metrics, platform events
- [Logging, Tracing, and Metrics Overview](https://docs.snowflake.com/en/developer-guide/logging-tracing/logging-tracing-overview) — scope: function/procedure handler code + Snowpark APIs
- [Streamlit Logging and Tracing](https://docs.snowflake.com/en/developer-guide/streamlit/object-management/logging-tracing) — Streamlit apps writing to event table
- [Openflow Monitoring](https://docs.snowflake.com/en/user-guide/data-integration/openflow/monitor) — Openflow resource attributes with `k8s.*` conventions
- [OTel Semantic Conventions Research](./otel_semantic_conventions_snowflake_research.md) — convention mapping per service category

---

## 10. Decision Summary

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  MVP EVENT TABLE FILTERING STRATEGY                                          │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  DATA ACCESS PATH:                                                           │
│    Customer Event Table → Custom View (RAP/masking) → Stream → Snowpark     │
│                                                                              │
│  PRIMARY FILTER (Snowpark pushdown, first operation):                        │
│    RESOURCE_ATTRIBUTES:"snow.executable.type" IN                             │
│      ('procedure', 'function', 'query', 'sql')                              │
│                                                                              │
│  PROCESSING MODEL:                                                           │
│    Snowpark handles ALL filtering/projection/splitting (pushdown)            │
│    Python SPs receive READY data → OTLP conversion → export to Splunk       │
│                                                                              │
│  WHAT THIS INCLUDES:                                                         │
│  ├─ Stored Procedure spans, logs, metrics                                    │
│  ├─ UDF/UDTF spans, logs, metrics                                            │
│  ├─ SQL statement traces within procedures                                   │
│  └─ Snowflake Scripting block traces                                         │
│                                                                              │
│  WHAT THIS EXCLUDES (automatically):                                         │
│  ├─ SPCS services/jobs     (snow.executable.type = 'spcs')                   │
│  ├─ Streamlit apps         (snow.executable.type = 'streamlit')              │
│  ├─ Openflow pipelines     (no snow.executable.type; uses 'application')     │
│  ├─ Iceberg refresh events (RECORD_TYPE = 'EVENT', no exec type)             │
│  ├─ SPCS platform events   (RECORD_TYPE = 'EVENT', SCOPE = 'snow.spcs...')   │
│  ├─ SPCS platform metrics  (no matching exec type)                           │
│  └─ Cortex AI              (separate table entirely)                         │
│                                                                              │
│  CONVENTION: db.* (Database Client semantic conventions)                     │
│  ENRICHMENT: Per otel_semantic_conventions_snowflake_research.md §6          │
│                                                                              │
│  POST-MVP EXTENSIBILITY:                                                     │
│  Add new service categories by registering new filter predicates +           │
│  convention-specific enrichers. Filters are mutually exclusive.              │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```
