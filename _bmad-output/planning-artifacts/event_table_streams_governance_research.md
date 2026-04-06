# Snowflake Event Table Streams & Data Governance -- Full Research Summary

*Research conducted 2026-02-17 with later architecture addendum from live validation on 2026-04-06 in Snowflake account `LFB71918`*
*All tests executed via Snow CLI (connection: dev) and Snowflake MCP tools*

> **Decision update (current project direction):**
> - The app's default path is a **direct stream on the selected event table**.
> - The app does **not** create or manage a dedicated governance/masking view layer.
> - Consumers may still create their **own custom views over event tables** and point the app at those views if they want their own governance controls.
> - `SNOWFLAKE.TELEMETRY.EVENTS_VIEW` is **not** our source path because live validation showed we cannot create a stream on it without inaccessible `CHANGE_TRACKING` privileges.

---

## Table of Contents

1. [Research Question](#1-research-question)
2. [Background: Event Tables in Snowflake](#2-background-event-tables-in-snowflake)
3. [Live Test Results: Stream Creation](#3-live-test-results-stream-creation)
4. [Live Test Results: Data Governance Policies on Event Tables](#4-live-test-results-data-governance-policies-on-event-tables)
5. [Live Test Results: Grants on System Objects](#5-live-test-results-grants-on-system-objects)
6. [Stream Operational Details](#6-stream-operational-details)
7. [Gaps & Limitations: View-Based Streams vs Direct Event Table Streams](#7-gaps--limitations-view-based-streams-vs-direct-event-table-streams)  
   - [View recreation and stream handling (Cortex Search verification)](#view-recreation-and-stream-handling-cortex-search-verification)
8. [Architecture Patterns](#8-architecture-patterns)
9. [Recommendation for the Native App](#9-recommendation-for-the-native-app)
10. [Documentation References](#10-documentation-references)

---

## 1. Research Question

Can we create a stream on the default event table (`SNOWFLAKE.TELEMETRY.EVENTS`) or its
system-managed view (`SNOWFLAKE.TELEMETRY.EVENTS_VIEW`)? What data governance policies
(RAP, masking, projection) can be applied to event tables and custom views to control
sensitive data before it flows through a stream to Splunk?

---

## 2. Background: Event Tables in Snowflake

Snowflake includes a **default event table** named `SNOWFLAKE.TELEMETRY.EVENTS` that
collects telemetry data (logs, traces, metrics) from procedures, UDFs, Streamlit apps,
and Snowpark Container Services.

Snowflake also provides a **predefined view** `SNOWFLAKE.TELEMETRY.EVENTS_VIEW` for controlled access patterns, but it is **not a viable direct stream source for this app** because live tests showed the app cannot enable the required `CHANGE_TRACKING` on that system-managed view.

Both objects are owned by the `SNOWFLAKE` application and reside in the system-managed
`SNOWFLAKE.TELEMETRY` schema.

Users can also create their own **custom event tables** via `CREATE EVENT TABLE`.

### Event Table Columns (Predefined)

| Column | Type | Sensitive Data Risk |
|--------|------|-------------------|
| TIMESTAMP | TIMESTAMP_NTZ | Low |
| START_TIMESTAMP | TIMESTAMP_NTZ | Low |
| OBSERVED_TIMESTAMP | TIMESTAMP_NTZ | Low |
| TRACE | OBJECT | Medium (span/trace IDs) |
| RESOURCE | OBJECT | Medium |
| RESOURCE_ATTRIBUTES | OBJECT | **High** (database names, query IDs, service names, container info) |
| SCOPE | OBJECT | Medium |
| SCOPE_ATTRIBUTES | OBJECT | Medium |
| RECORD_TYPE | VARCHAR | Low |
| RECORD | OBJECT | **High** (log content, stack traces) |
| RECORD_ATTRIBUTES | OBJECT | Medium |
| VALUE | VARIANT | **High** (user-logged messages, could contain PII/credentials) |
| EXEMPLARS | ARRAY | Low |

### CREATE STREAM Syntax for Event Tables

```sql
-- Dedicated syntax variant for event tables
CREATE [ OR REPLACE ] STREAM [IF NOT EXISTS]
  <name>
  ON EVENT TABLE <table_name>
  [ COMMENT = '<string_literal>' ]
```

Note: The event table syntax does NOT support `AT | BEFORE` (Time Travel) or
`SHOW_INITIAL_ROWS` options. The main syntax block also does not advertise `APPEND_ONLY`
for `ON EVENT TABLE`, but live validation later showed `APPEND_ONLY = TRUE` is accepted
and `SHOW STREAMS` reports `APPEND_ONLY` mode for event-table streams.

---

## 3. Live Test Results: Stream Creation

### Test 3.1: Stream on Default Event Table (Direct)

**Command:**
```sql
CREATE STREAM IF NOT EXISTS SPLUNKDB.PUBLIC.TEST_EVENT_STREAM
  ON EVENT TABLE SNOWFLAKE.TELEMETRY.EVENTS APPEND_ONLY = TRUE;
```

**Result:** SUCCESS -- `Stream TEST_EVENT_STREAM successfully created.`

**Verification (SHOW STREAMS):**
```json
{
    "name": "TEST_EVENT_STREAM",
    "database_name": "SPLUNKDB",
    "schema_name": "PUBLIC",
    "table_name": "SNOWFLAKE.TELEMETRY.EVENTS",
    "source_type": "Table",
    "base_tables": "SNOWFLAKE.TELEMETRY.EVENTS",
    "type": "DELTA",
    "stale": "false",
    "mode": "APPEND_ONLY",
    "stale_after": "2026-03-03T04:00:38.155000-08:00"
}
```

**Data check:** `SELECT COUNT(*) FROM stream` returned 0 rows (expected -- stream only
captures events arriving after creation).

**Cleanup:** Stream dropped successfully.

**Key insight:** The stream must be created in a **user-owned schema** (e.g.
`SPLUNKDB.PUBLIC`). Attempting to create it inside `SNOWFLAKE.TELEMETRY` fails:

```sql
CREATE STREAM SNOWFLAKE.TELEMETRY.TEST_STREAM
  ON EVENT TABLE SNOWFLAKE.TELEMETRY.EVENTS;
-- ERROR: Schema 'SNOWFLAKE.TELEMETRY' does not exist or not authorized.
```

---

### Test 3.2: Stream on System-Managed EVENTS_VIEW

**Step 1 -- Verify view is accessible:**
```sql
DESCRIBE VIEW SNOWFLAKE.TELEMETRY.EVENTS_VIEW;
-- SUCCESS: Returns 13 columns (TIMESTAMP, START_TIMESTAMP, ..., VALUE, EXEMPLARS)

SELECT * FROM SNOWFLAKE.TELEMETRY.EVENTS_VIEW LIMIT 1;
-- SUCCESS: Returns data (confirmed RECORD_TYPE: "LOG", with RESOURCE_ATTRIBUTES
-- containing snow.database.name, snow.service.name, etc.)
```

**Step 2 -- Attempt stream creation:**
```sql
CREATE STREAM IF NOT EXISTS SPLUNKDB.PUBLIC.TEST_EVENTS_VIEW_STREAM
  ON VIEW SNOWFLAKE.TELEMETRY.EVENTS_VIEW APPEND_ONLY = TRUE;
```

**Result:** FAILED
```
SQL access control error:
Insufficient privileges to operate on stream source
without CHANGE_TRACKING enabled 'EVENTS_VIEW'.
```

**Step 3 -- Attempt to enable change tracking:**
```sql
ALTER VIEW SNOWFLAKE.TELEMETRY.EVENTS_VIEW SET CHANGE_TRACKING = TRUE;
```

**Result:** FAILED (even with ACCOUNTADMIN + EVENTS_ADMIN)
```
SQL access control error:
Insufficient privileges to operate on view 'EVENTS_VIEW'.
```

**Root cause:** The view is owned by the `SNOWFLAKE` application. No user role can ALTER
it. Without change tracking, streams on this specific system-managed view are impossible.
This is **not** a general prohibition on streams over secure views or user-owned views.

---

### Test 3.3: Stream on Custom View Over Default Event Table

**Step 1 -- Create custom view:**
```sql
CREATE OR REPLACE VIEW SPLUNKDB.PUBLIC.TEST_EVENTS_VIEW
  AS SELECT * FROM SNOWFLAKE.TELEMETRY.EVENTS;
-- SUCCESS: View TEST_EVENTS_VIEW successfully created.
```

**Step 2 -- Create stream on custom view:**
```sql
CREATE STREAM IF NOT EXISTS SPLUNKDB.PUBLIC.TEST_VIEW_STREAM
  ON VIEW SPLUNKDB.PUBLIC.TEST_EVENTS_VIEW APPEND_ONLY = TRUE;
-- SUCCESS: Stream TEST_VIEW_STREAM successfully created.
```

**Verification (SHOW STREAMS):**
```json
{
    "name": "TEST_VIEW_STREAM",
    "database_name": "SPLUNKDB",
    "schema_name": "PUBLIC",
    "table_name": "SPLUNKDB.PUBLIC.TEST_EVENTS_VIEW",
    "source_type": "View",
    "base_tables": "SNOWFLAKE.TELEMETRY.EVENTS",
    "type": "DELTA",
    "stale": "false",
    "mode": "APPEND_ONLY",
    "stale_after": "2026-03-03T04:14:47.507000-08:00"
}
```

**Key insight:** Change tracking auto-enables when you create the first stream on a view
you own. The `base_tables` still resolves to `SNOWFLAKE.TELEMETRY.EVENTS`.

**Cleanup:** Both stream and view dropped successfully.

---

### Test 3.4: Stream on User-Created Event Table

**Step 1 -- Create event table:**
```sql
CREATE EVENT TABLE IF NOT EXISTS SPLUNKDB.PUBLIC.TEST_CUSTOM_EVENT_TABLE;
-- SUCCESS: Table TEST_CUSTOM_EVENT_TABLE successfully created.
```

**Step 2 -- Create stream:**
```sql
CREATE STREAM IF NOT EXISTS SPLUNKDB.PUBLIC.TEST_PROTECTED_ET_STREAM
  ON EVENT TABLE SPLUNKDB.PUBLIC.TEST_CUSTOM_EVENT_TABLE APPEND_ONLY = TRUE;
-- SUCCESS: Stream TEST_PROTECTED_ET_STREAM successfully created.
```

**Cleanup:** Stream and event table dropped successfully.

---

### Stream Creation Summary

| # | Source | Syntax | Result |
|---|--------|--------|--------|
| 3.1 | Default event table `SNOWFLAKE.TELEMETRY.EVENTS` | `ON EVENT TABLE` | **SUCCESS** |
| 3.2 | System-managed view `SNOWFLAKE.TELEMETRY.EVENTS_VIEW` | `ON VIEW` | **FAILED** (no change tracking, can't enable) |
| 3.3 | Custom view on default event table | `ON VIEW` | **SUCCESS** |
| 3.4 | User-created event table | `ON EVENT TABLE` | **SUCCESS** |

---

## 4. Live Test Results: Data Governance Policies on Event Tables

All tests performed on a user-created event table (`SPLUNKDB.PUBLIC.TEST_CUSTOM_EVENT_TABLE`).

### Test 4.1: Row Access Policy (RAP)

**Step 1 -- Create RAP:**
```sql
CREATE OR REPLACE ROW ACCESS POLICY SPLUNKDB.PUBLIC.TEST_RAP_EVENTS
  AS (resource_attrs OBJECT) RETURNS BOOLEAN ->
    CASE
      WHEN IS_ROLE_IN_SESSION('ACCOUNTADMIN') THEN TRUE
      ELSE FALSE
    END;
-- SUCCESS: Row access policy 'TEST_RAP_EVENTS' is successfully created.
```

Note: Event table columns are `OBJECT` type, not `VARIANT`. Initial attempt with
`VARIANT` type failed with: `Column 'RESOURCE_ATTRIBUTES' data type 'OBJECT' does not
match with Row access policy data type 'VARIANT'.`

**Step 2 -- Attach RAP to event table:**
```sql
ALTER TABLE SPLUNKDB.PUBLIC.TEST_CUSTOM_EVENT_TABLE
  ADD ROW ACCESS POLICY SPLUNKDB.PUBLIC.TEST_RAP_EVENTS ON (RESOURCE_ATTRIBUTES);
-- SUCCESS: Statement executed successfully.
```

**Result:** RAP on event tables -- **WORKS**

---

### Test 4.2: Masking Policy

**Step 1 -- Create masking policy:**
```sql
CREATE OR REPLACE MASKING POLICY SPLUNKDB.PUBLIC.TEST_MASK_VALUE
  AS (val VARIANT) RETURNS VARIANT ->
    CASE
      WHEN IS_ROLE_IN_SESSION('ACCOUNTADMIN') THEN val
      ELSE NULL
    END;
-- SUCCESS: Masking policy TEST_MASK_VALUE successfully created.
```

**Step 2 -- Attach to event table column:**
```sql
ALTER TABLE SPLUNKDB.PUBLIC.TEST_CUSTOM_EVENT_TABLE
  ALTER COLUMN VALUE SET MASKING POLICY SPLUNKDB.PUBLIC.TEST_MASK_VALUE;
```

**Result:** FAILED
```
Unsupported feature 'INVALID OPERATION FOR EVENT TABLES'.
```

**Result:** Masking policy on event tables -- **BLOCKED** (explicit Snowflake limitation)

---

### Test 4.3: Projection Policy (Column-Level Filtering)

**Step 1 -- Create projection policy:**
```sql
CREATE OR REPLACE PROJECTION POLICY SPLUNKDB.PUBLIC.TEST_PROJ_POLICY
  AS () RETURNS PROJECTION_CONSTRAINT -> PROJECTION_CONSTRAINT(ALLOW => false);
-- SUCCESS: Projection policy 'TEST_PROJ_POLICY' is successfully created.
```

**Step 2 -- Attach to event table column:**
```sql
ALTER TABLE SPLUNKDB.PUBLIC.TEST_CUSTOM_EVENT_TABLE
  ALTER COLUMN VALUE SET PROJECTION POLICY SPLUNKDB.PUBLIC.TEST_PROJ_POLICY;
-- SUCCESS: Statement executed successfully.
```

**Result:** Projection policy on event tables -- **WORKS**

---

### Test 4.4: Stream on Policy-Protected Event Table

With both RAP and projection policy active on the event table:

```sql
CREATE STREAM IF NOT EXISTS SPLUNKDB.PUBLIC.TEST_PROTECTED_ET_STREAM
  ON EVENT TABLE SPLUNKDB.PUBLIC.TEST_CUSTOM_EVENT_TABLE APPEND_ONLY = TRUE;
-- SUCCESS: Stream TEST_PROTECTED_ET_STREAM successfully created.
```

**Result:** Stream on governance-protected event table -- **WORKS**

---

### Test 4.5: Verify All Policies Active

```sql
SELECT * FROM TABLE(SPLUNKDB.INFORMATION_SCHEMA.POLICY_REFERENCES(
  REF_ENTITY_NAME => 'SPLUNKDB.PUBLIC.TEST_CUSTOM_EVENT_TABLE',
  REF_ENTITY_DOMAIN => 'TABLE'
));
```

**Result:**
```json
[
    {
        "POLICY_NAME": "TEST_PROJ_POLICY",
        "POLICY_KIND": "PROJECTION_POLICY",
        "REF_ENTITY_NAME": "TEST_CUSTOM_EVENT_TABLE",
        "REF_ENTITY_DOMAIN": "EVENT_TABLE",
        "REF_COLUMN_NAME": "VALUE",
        "POLICY_STATUS": "ACTIVE"
    },
    {
        "POLICY_NAME": "TEST_RAP_EVENTS",
        "POLICY_KIND": "ROW_ACCESS_POLICY",
        "REF_ENTITY_NAME": "TEST_CUSTOM_EVENT_TABLE",
        "REF_ENTITY_DOMAIN": "EVENT_TABLE",
        "REF_COLUMN_NAME": null,
        "REF_ARG_COLUMN_NAMES": "[ \"RESOURCE_ATTRIBUTES\" ]",
        "POLICY_STATUS": "ACTIVE"
    }
]
```

Both policies confirmed **ACTIVE** on the event table with the stream successfully created
on top.

---

### Data Governance Policy Summary

| Policy Type | On User-Created Event Table | On Custom View | On Default Event Table | On System EVENTS_VIEW |
|---|:---:|:---:|:---:|:---:|
| **Row Access Policy** | **Works** | **Works** | Cannot test (system-owned) | Cannot alter (system-owned) |
| **Projection Policy** | **Works** | **Works** | Cannot test (system-owned) | Cannot alter (system-owned) |
| **Masking Policy** | **BLOCKED** (`INVALID OPERATION FOR EVENT TABLES`) | **Works** (on views) | Cannot test (system-owned) | Cannot alter (system-owned) |
| **Stream after policies applied** | **Works** | **Works** | N/A | N/A |

### How Streams Respect Policies (from Snowflake docs)

> *"Snowflake does not support attaching a row access policy to the stream object itself,
> but does apply the row access policy to the table when the stream accesses a table
> protected by a row access policy."*
> -- [Understanding row access policies](https://docs.snowflake.com/en/user-guide/security-row-intro)

This means:
- You **cannot** attach policies to a stream object directly
- Streams **DO respect** RAP and projection policies on the underlying table or view
- Policy evaluation happens at **stream consumption time** based on the consuming role

---

## 5. Live Test Results: Grants on System Objects

### SHOW GRANTS ON VIEW SNOWFLAKE.TELEMETRY.EVENTS_VIEW

```json
[
    {
        "privilege": "SELECT",
        "granted_on": "VIEW",
        "granted_to": "APPLICATION_ROLE",
        "grantee_name": "EVENTS_ADMIN",
        "granted_by": "SNOWFLAKE"
    },
    {
        "privilege": "SELECT",
        "granted_on": "VIEW",
        "granted_to": "APPLICATION_ROLE",
        "grantee_name": "EVENTS_VIEWER",
        "granted_by": "SNOWFLAKE"
    },
    {
        "privilege": "OWNERSHIP",
        "granted_on": "VIEW",
        "granted_to": "APPLICATION",
        "grantee_name": "SNOWFLAKE",
        "grant_option": "true"
    }
]
```

### SHOW GRANTS ON EVENT TABLE SNOWFLAKE.TELEMETRY.EVENTS

```json
[
    {
        "privilege": "DELETE",
        "granted_on": "EVENT_TABLE",
        "granted_to": "APPLICATION_ROLE",
        "grantee_name": "EVENTS_ADMIN"
    },
    {
        "privilege": "SELECT",
        "granted_on": "EVENT_TABLE",
        "granted_to": "APPLICATION_ROLE",
        "grantee_name": "EVENTS_ADMIN"
    },
    {
        "privilege": "TRUNCATE",
        "granted_on": "EVENT_TABLE",
        "granted_to": "APPLICATION_ROLE",
        "grantee_name": "EVENTS_ADMIN"
    },
    {
        "privilege": "OWNERSHIP",
        "granted_on": "EVENT_TABLE",
        "granted_to": "APPLICATION",
        "grantee_name": "SNOWFLAKE",
        "grant_option": "true"
    }
]
```

**Key takeaway:** Both system objects are OWNED by the SNOWFLAKE application. No user
role has ALTER or OWNERSHIP privileges. The `EVENTS_ADMIN` role only provides
SELECT/TRUNCATE/DELETE on the table and SELECT on the view.

---

## 6. Stream Operational Details

| Property | Value |
|----------|-------|
| Recommended mode | `APPEND_ONLY = TRUE` (event tables primarily receive inserts) |
| Staleness window | ~14 days (observed `stale_after` ≈ creation + 14 days) |
| Time Travel / AT / BEFORE | **Not supported** for event table streams |
| `SHOW_INITIAL_ROWS` | **Not supported** for event table streams |
| Source type in SHOW STREAMS | `Table` (direct on event table) or `View` (via custom view) |
| Base tables resolution | Always resolves to the underlying event table regardless of approach |
| Data retention extension | Use `MAX_DATA_EXTENSION_TIME_IN_DAYS` to prevent stream staleness |

---

## 7. Gaps & Limitations: View-Based Streams vs Direct Event Table Streams

When a consumer chooses a **custom view + stream** approach instead of direct event table
streaming, there are important trade-offs and operational risks to understand. These are
real constraints, which is why this project no longer recommends an app-managed governance
view layer as the default architecture.

### 7.1 View Breakage -- CRITICAL RISK

> *"Any stream on a given view breaks if the source view or underlying tables are dropped
> or recreated (using CREATE OR REPLACE VIEW)."*
> -- [CREATE STREAM docs](https://docs.snowflake.com/en/sql-reference/sql/create-stream)

If **anyone** runs `CREATE OR REPLACE VIEW` on the custom view, **all streams on it become
stale and unrecoverable**. The stream must be recreated, and the offset is lost -- meaning
any unconsumed change data between the last consumption and the view recreation is gone.

With a direct event table stream, only dropping/recreating the event table itself (very
unlikely for a production telemetry table) causes this.

**Mitigation:**
- Use `ALTER VIEW` for all policy changes (add/drop RAP, masking policies) -- this does
  NOT break streams
- Never use `CREATE OR REPLACE VIEW` after streams are created
- Document this prominently in customer-facing setup guides
- Consider monitoring stream staleness via `SHOW STREAMS` in the Streamlit UI

---

### 7.2 Strict View Query Restrictions

Snowflake imposes strict limits on what SQL operations a view can use if a stream will be
created on it. The view must only contain:

| Allowed in View Definition | NOT Allowed in View Definition |
|---|---|
| Projections (SELECT columns) | GROUP BY clauses |
| Filters (WHERE clauses) | QUALIFY clauses |
| Inner or cross joins | Subqueries not in FROM clause |
| UNION ALL | Correlated subqueries |
| Nested views/subqueries in FROM | LIMIT clauses |
| System-defined scalar functions | DISTINCT clauses |
| | User-defined functions (UDFs) |

Source: [Introduction to streams - Streams on views](https://docs.snowflake.com/en/user-guide/streams-intro)

This means views like `SELECT DISTINCT RECORD_TYPE, ...` or
`SELECT ... GROUP BY RECORD_TYPE` **will not work** with streams. The custom view must be a
simple projection/filter over the event table.

**Impact on governance view design:** Column transformations using system scalar functions
(e.g., `OBJECT_DELETE`, `REGEXP_REPLACE`) are allowed. Complex aggregations or
deduplication are not.

---

### 7.3 Change Tracking Lock on First Stream Creation

> *"When either creating or altering a view to specify CHANGE_TRACKING, the associated
> dependent database objects are automatically updated to enable change tracking. During
> the operation, the underlying resources are **locked**, which can cause latency for
> DDL/DML operations."*
> -- [Manage streams](https://docs.snowflake.com/en/user-guide/streams-manage)

The first time a stream is created on the custom view, Snowflake **locks the underlying
event table** to add hidden change tracking columns. For a busy production event table
receiving high-volume telemetry, this can cause momentary latency for all telemetry
ingestion.

This is a **one-time cost** -- subsequent stream creations on the same view (or other views
over the same table) do not require re-locking.

**Mitigation:** Schedule the initial stream creation during a maintenance window or
low-activity period.

---

### 7.4 Staleness Window Tied to Underlying Table, Not the View

For view-based streams, the staleness window is governed by the **underlying table's**
`DATA_RETENTION_TIME_IN_DAYS` and `MAX_DATA_EXTENSION_TIME_IN_DAYS` parameters, not any
setting on the view itself.

| Source | Can control retention params? | Staleness risk |
|--------|:---:|------|
| Direct stream on user-created ET | Yes (`ALTER TABLE ... SET MAX_DATA_EXTENSION_TIME_IN_DAYS = 90`) | Low |
| View on user-created ET | Indirectly (via underlying ET params) | Low |
| Direct stream on default ET | No (system-owned) | Medium |
| View on default ET | No (system-owned) | Medium |

For the **default event table** (`SNOWFLAKE.TELEMETRY.EVENTS`), you cannot modify these
parameters since it's system-owned. You're at the mercy of Snowflake's default retention
settings. Streams must be consumed frequently to avoid staleness.

Source: [Introduction to streams - Data retention period and staleness](https://docs.snowflake.com/en/user-guide/streams-intro)

---

### 7.5 Secure Views Do NOT Auto-Extend Retention

> *"The retention period for the underlying tables is **not extended automatically** to
> prevent any streams on the secure view from becoming stale."*
> -- [CREATE STREAM docs](https://docs.snowflake.com/en/sql-reference/sql/create-stream)

If you create the custom view as a **secure view** (`CREATE SECURE VIEW`), Snowflake will
**not** automatically extend the data retention period to keep the stream alive. The stream
will go stale faster if not consumed regularly.

For non-secure views, Snowflake automatically extends retention up to 14 days (or the
`MAX_DATA_EXTENSION_TIME_IN_DAYS` value) to prevent staleness.

**Mitigation:**
- Do NOT use `CREATE SECURE VIEW` unless strictly required by compliance
- If secure views are required, ensure the stream is consumed very frequently (every 1-5
  minutes via a triggered or scheduled task)

---

### 7.6 Triggered Tasks Fire on ALL Underlying Table Changes

> *"When a task is triggered by Streams on Views, then any changes to tables referenced
> by the Streams on Views query will also trigger the task, **regardless of any joins,
> aggregations, or filters in the query**."*
> -- [Introduction to streams - Limitations](https://docs.snowflake.com/en/user-guide/streams-intro)

Even if the custom view filters to only `WHERE RECORD_TYPE = 'LOG'`, a triggered task
using `SYSTEM$STREAM_HAS_DATA()` fires on **any** insert to the event table -- including
traces, metrics, and any other record types. The view's WHERE filter only takes effect when
the task actually queries the stream, not when deciding whether to trigger.

This results in more task executions (and compute cost) than expected. Many task runs will
query the stream, find no matching rows after view filtering, and do nothing.

**Mitigation:**
- Use **serverless tasks** to minimize cost for "empty" runs (no warehouse spin-up overhead)
- Accept that some false-positive task runs are an inherent trade-off of view-filtered
  streams
- Consume the stream even when empty to advance the offset (see staleness avoidance in
  [Manage streams](https://docs.snowflake.com/en/user-guide/streams-manage)):
  ```sql
  CREATE TEMPORARY TABLE _unused AS SELECT * FROM my_stream WHERE 1=0;
  ```

---

### 7.7 METADATA$ROW_ID Differs Between Table and View Streams

> *"A stream `stream_view` on view `view1` is **not guaranteed** to produce the same
> METADATA$ROW_IDs as `stream1` [on the underlying table], even if view is defined using
> the statement `CREATE VIEW view AS SELECT * FROM table1`."*
> -- [Introduction to streams - Stream columns](https://docs.snowflake.com/en/user-guide/streams-intro)

If you use `METADATA$ROW_ID` for deduplication or exactly-once delivery tracking, the IDs
from a view-based stream will differ from those produced by a direct event table stream.
You cannot correlate rows across the two stream types using this ID.

---

### 7.8 Non-Deterministic Functions in View Definitions

> *"Streams based on views where the view uses non-deterministic functions can return
> non-deterministic results."*
> -- [CREATE STREAM docs](https://docs.snowflake.com/en/sql-reference/sql/create-stream)

If the custom view uses functions like `CURRENT_DATE`, `CURRENT_USER`, `CURRENT_ROLE`, or
`RANDOM()`, the stream results may differ each time they're queried. These functions are
evaluated at query time, not at insert time.

**Mitigation:** Avoid non-deterministic functions in the view definition. Use only
deterministic scalar functions like `OBJECT_DELETE`, `REGEXP_REPLACE`, `COALESCE`, etc.

---

### 7.9 Storage Cost from Change Tracking and Retention Extension

Change tracking adds hidden columns to the **underlying event table** (not the view). These
columns consume additional storage proportional to the volume of changes.

Additionally:
> *"If the data retention period for a table is less than 14 days and a stream hasn't been
> consumed, Snowflake temporarily extends this period... Extending the data retention
> period requires additional storage which will be reflected in your monthly storage
> charges."*
> -- [Introduction to streams - Billing](https://docs.snowflake.com/en/user-guide/streams-intro)

The stream keeps event table data around longer than it otherwise would. For high-volume
telemetry event tables, this incremental storage cost should be factored into the design.

---

### 7.10 Event Table Alterations Not Propagated to Views

> *"Changes to an event table are not automatically propagated to views created on that
> event table."*
> -- [ALTER TABLE (event tables)](https://docs.snowflake.com/en/sql-reference/sql/alter-table-event-table)

If the event table schema changes (unlikely for event tables since columns are predefined,
but possible for metadata/behavior changes), the custom view will not automatically
reflect those changes.

---

### Summary: View-Based Stream Limitations

| # | Limitation | Severity | Affects Direct ET Stream? | Mitigation |
|---|-----------|:---:|:---:|------------|
| 7.1 | `CREATE OR REPLACE VIEW` breaks all streams | **CRITICAL** | No | Use `ALTER VIEW` only; document for customers |
| 7.2 | View must use only simple SQL (no GROUP BY, DISTINCT, UDFs) | **MEDIUM** | No | Keep view as simple projection/filter |
| 7.3 | First stream creation locks underlying table | **MEDIUM** | No (ET has built-in tracking) | Schedule during maintenance window |
| 7.4 | Staleness window tied to underlying table retention | **MEDIUM** | Same risk for default ET | Consume stream frequently |
| 7.5 | Secure views don't auto-extend retention | **MEDIUM** | N/A | Avoid secure views unless required |
| 7.6 | Triggered tasks fire on all underlying changes | **MEDIUM** | No | Use serverless tasks; accept false positives |
| 7.7 | METADATA$ROW_ID differs from table stream IDs | **LOW** | N/A | Don't correlate IDs across stream types |
| 7.8 | Non-deterministic functions cause unstable results | **LOW** | N/A | Use only deterministic functions in view |
| 7.9 | Additional storage cost (change tracking + retention) | **LOW** | Same | Factor into cost estimates |
| 7.10 | ET alterations not propagated to views | **LOW** | N/A | Monitor for Snowflake platform changes |

### View recreation and stream handling (Cortex Search verification)

*Verified via Snowflake MCP `cortex_search` against `CKE_SNOWFLAKE_DOCS_SERVICE` (SNOWFLAKE_DOCUMENTATION.SHARED) with `columns: ['chunk']` to retrieve document snippets.*

**Questions answered:**

1. **Can we detect when the user re-created the view with `CREATE OR REPLACE VIEW`?**  
   We do not need to detect the view DDL itself. As soon as the view is recreated, **any stream on that view becomes stale and unreadable**. Snowflake docs state: *"Recreating or swapping a view drops its change data, which makes any stream on the view stale. A stale stream is unreadable."* We can detect the problem by:
   - **SHOW STREAMS** (or equivalent INFORMATION_SCHEMA): the **`stale`** column is `TRUE` when the stream can no longer be read.
   - **Querying the stream**: reading from a stale stream fails; the app can treat repeated read failures as an orphaned stream.

2. **What can we do so streams still work on the new view?**  
   Nothing. The docs are explicit: *"Any stream on a given view breaks if the source view or underlying tables are dropped or recreated (using CREATE OR REPLACE VIEW)."* The stream’s offset is tied to the previous view instance; it cannot be “repaired” to point at the new view. The only resolution is to **recreate the stream** (e.g. `CREATE OR REPLACE STREAM`), which starts at the current table version and **accepts a data gap** for changes that occurred between the old stream’s last consumed offset and the recreation.

3. **Should we mark the view as orphaned in the telemetry health dashboard and stop streaming?**  
   **Yes.** Recommended behavior:
   - **Detect**: Use `SHOW STREAMS` (or stream metadata) to check the **stale** flag, and/or treat persistent stream read failures as “stream broken.”
   - **Mark**: In Pipeline Health / Telemetry dashboard, mark the affected source (view + stream) as **orphaned** or **broken** with a clear message that the source view was likely recreated and the stream is no longer valid.
   - **Stop**: Do not attempt to consume the stream; reads will fail.
   - **Recovery**: Require the user to **re-select the (recreated) view** as the telemetry source. The app can then **drop and recreate the stream** on the current view (with an explicit warning about the one-time data gap). Do not try to “re-attach” the old stream to the new view.

**Cortex Search quotes (docs):**

- *"Any stream on a given view breaks if the source view or underlying tables are dropped or recreated (using CREATE OR REPLACE VIEW)."*
- *"Recreating or swapping a view drops its change data, which makes any stream on the view stale. A stale stream is unreadable."*
- *"When a stream is stale, it cannot be read. Recreate the stream to resume reading from it."*
- *"To resolve this issue, recreate the stream in the primary database (using CREATE OR REPLACE STREAM)."*

---

## 8. Architecture Patterns

### Pattern A: Direct Stream on Event Table (Preferred MVP Default)

```
Event Table ──→ Stream (APPEND_ONLY) ──→ Task ──→ Splunk
```

- No governance layer between event table and export pipeline
- All raw data flows through (including sensitive content in VALUE, RECORD,
  RESOURCE_ATTRIBUTES)
- Works for both default and user-created event tables
- Lowest operational fragility: no view breakage, no view SQL restrictions, no false-positive task triggers from filtered views
- **Use when:** Default MVP path; consumer wants the simplest and most robust setup

### Pattern B: Event Table + RAP/Projection + Stream (Moderate Security)

```
Event Table (RAP + Projection Policies) ──→ Stream ──→ Task ──→ Splunk
```

- Row-level filtering via RAP (e.g., only export events from specific databases/services)
- Column blocking via projection policy (e.g., hide VALUE column entirely)
- **Cannot** redact values within semi-structured columns (masking policies blocked)
- Only works on **user-created** event tables (cannot attach policies to default)
- **Use when:** The consumer uses their own user-created event table and row filtering / projection are sufficient

### Pattern C: Consumer-Managed Custom View + Stream (Optional Escape Hatch)

```
Event Table ──→ Consumer Custom View ──→ Stream ──→ Task ──→ Splunk
```

- Works on **both** default and user-created event tables when the consumer owns the custom view
- Lets the consumer apply their own governance policies and column transformations
- Can support masking on the view, which event tables themselves do not support
- Adds real operational constraints: `CREATE OR REPLACE VIEW` breakage, view SQL restrictions, false-positive task triggers, and potential secure-view retention caveats
- **Use when:** The consumer explicitly wants a custom view and accepts the extra operational burden

#### Example: Optional Consumer-Managed View for Splunk Export

```sql
-- Optional consumer-managed custom view.
-- Keep the view simple if a stream will be created on it.
CREATE OR REPLACE VIEW SPLUNKDB.PUBLIC.SPLUNK_EVENTS_EXPORT AS
SELECT
    TIMESTAMP,
    START_TIMESTAMP,
    OBSERVED_TIMESTAMP,
    TRACE,
    RECORD_TYPE,
    RECORD,
    RECORD_ATTRIBUTES,
    RESOURCE_ATTRIBUTES,
    SCOPE,
    SCOPE_ATTRIBUTES,
    VALUE
FROM SNOWFLAKE.TELEMETRY.EVENTS;

-- Create stream for CDC
CREATE STREAM SPLUNKDB.PUBLIC.SPLUNK_EVENTS_STREAM
  ON VIEW SPLUNKDB.PUBLIC.SPLUNK_EVENTS_EXPORT APPEND_ONLY = TRUE;
```

If the consumer wants RAP, masking, or extra transformations on the view, that remains
their choice, but it is no longer the app's default or recommended architecture.

---

## 9. Recommendation for the Native App

**Current project recommendation:** use **Pattern A (direct stream on event table)** as the
default architecture. Treat **Pattern C (consumer-managed custom view + stream)** as an
optional source type the app can support, but not create or manage on the consumer's
behalf.

| Concern | Pattern A (Direct) | Pattern B (ET + Policies) | Pattern C (Consumer View + Stream) |
|---------|:---:|:---:|:---:|
| Works with default event table | **Yes** | No (can't attach policies) | Yes |
| Works with user-created event tables | **Yes** | Yes | Yes |
| Row-level filtering (RAP) | No | Yes | Yes |
| Column blocking (projection) | No | Yes | Yes |
| Value-level redaction (masking) | No | No (blocked on ETs) | Yes |
| Operational fragility | **Lowest** | Low | Highest |
| `CREATE OR REPLACE VIEW` breakage risk | **Low** | Low | **CRITICAL** |
| View SQL restrictions | N/A | N/A | Yes |
| Triggered task false positives | No | No | Yes |
| Secure-view retention caveat | N/A | N/A | Possible |
| App-managed complexity | **Lowest** | Medium | Highest |

Why Pattern A is now preferred:
1. It works directly against `SNOWFLAKE.TELEMETRY.EVENTS` and other event tables without introducing view-stream fragility.
2. It avoids maintaining an app-defined governance contract that the project ultimately decided not to own.
3. It keeps source selection simple: either stream the event table directly, or let the consumer provide their own custom view if they need one.
4. It aligns with the updated planning docs: the app supports consumer-created custom views, but it does not require or generate them.

### Operational Guidance

Default path:
1. Use `APPEND_ONLY = TRUE` on event-table streams.
2. Consume the stream frequently and monitor `STALE_AFTER`.
3. Prefer direct event-table streams unless the consumer explicitly needs a custom view.

If the consumer chooses a custom view:
1. **Never use `CREATE OR REPLACE VIEW`** after streams exist. Use `ALTER VIEW` for view changes.
2. Keep the view simple: projection/filter only, no `GROUP BY`, `DISTINCT`, `LIMIT`, or UDFs.
3. Avoid non-deterministic functions in the view definition.
4. Be aware that triggered tasks on view streams can fire on underlying-table changes even when the view filter later returns zero rows.
5. Treat masking/redaction on the view as a consumer-managed choice, not an app-owned default.

---

## 10. Documentation References

- [CREATE STREAM](https://docs.snowflake.com/en/sql-reference/sql/create-stream) -- Stream syntax including event table variant
- [Working with event tables](https://docs.snowflake.com/en/developer-guide/logging-tracing/event-table-operations) -- Supported operations, stream section
- [Event table overview](https://docs.snowflake.com/en/developer-guide/logging-tracing/event-table-setting-up) -- Default vs custom event tables, EVENTS_VIEW
- [ALTER TABLE (event tables)](https://docs.snowflake.com/en/sql-reference/sql/alter-table-event-table) -- RAP, projection, tag support on event tables
- [Understanding row access policies](https://docs.snowflake.com/en/user-guide/security-row-intro) -- RAP behavior with streams, views, and tables
- [Introduction to streams](https://docs.snowflake.com/en/user-guide/streams-intro) -- Stream fundamentals, staleness, offset management, view limitations
- [Manage streams](https://docs.snowflake.com/en/user-guide/streams-manage) -- Change tracking setup, staleness avoidance, stream consumption
- [CREATE VIEW](https://docs.snowflake.com/en/sql-reference/sql/create-view) -- View recreation and stream breakage warning
