# Adversarial Architectural Review: Event Table & ACCOUNT_USAGE Telemetry Export

> **Reviewer posture:** Principal Snowflake Architect — cynical, zero patience for hand-waving.
> **Date:** 2026-04-13 (initial findings), 2026-04-15 (live testing, final decisions)
> **Content reviewed:** Story 5.1 design, `telemetry_preparation_for_export.md`, `event_table_streams_governance_research.md`, `architecture.md` pipeline patterns, `grpc_research.md` Pattern A, dual-pipeline architecture.
> **Verification:** Snowflake official docs, Perplexity deep research (Sonar Deep Research, 50 citations), Firecrawl-scraped articles, Snowflake MCP Cortex Search, **live SQL testing** against dev account `LFB71918` via Snow CLI and Snowflake MCP.

**TL;DR:** The proposed stream-based Event Table collection (Story 5.1) is fundamentally broken. Live testing confirms the **CHANGES clause** works on Event Tables, custom views, and views with masking policies. It does **NOT** work on ACCOUNT_USAGE views (hard platform constraint). **Streams are not needed at all** — not for data reading, not for task triggering. The final architecture is: scheduled serverless tasks + CHANGES clause + self-managed watermark table for Event Tables; watermark + overlap + dedup for ACCOUNT_USAGE; unified orchestration for both.

---

## Part 1: Findings Against Story 5.1 (Stream-Based Design)

### FINDING 1: CRITICAL — `CREATE OR REPLACE TEMP TABLE` Inside `BEGIN`/`COMMIT` Destroys Transactional Atomicity

The entire Story 5.1 architecture hinges on Rule ET-7: "BEGIN → CTAS temp tables → zero-row INSERT → COMMIT" as a single atomic transaction. **This is fundamentally broken.**

Snowflake documentation explicitly states:

> "Each DDL statement executes as a separate transaction. If a DDL statement is executed while a transaction is active, the DDL statement: (1) Implicitly commits the active transaction. (2) Executes the DDL statement as a separate transaction."
> — [Snowflake Transactions docs](https://docs.snowflake.com/en/sql-reference/transactions)

`CREATE OR REPLACE TEMP TABLE ... AS SELECT` is DDL, not DML. The first CTAS implicitly commits the `BEGIN`, and each subsequent CTAS auto-commits independently. There is no atomicity.

```python
# THIS DOES NOT WORK AS INTENDED
session.sql("BEGIN").collect()
try:
    session.sql("CREATE OR REPLACE TEMP TABLE tmp_spans AS ...").collect()      # ← implicitly commits BEGIN
    session.sql("CREATE OR REPLACE TEMP TABLE tmp_span_events AS ...").collect() # ← separate auto-commit
    session.sql("CREATE OR REPLACE TEMP TABLE tmp_logs AS ...").collect()         # ← separate auto-commit
    session.sql("CREATE OR REPLACE TEMP TABLE tmp_metrics AS ...").collect()      # ← separate auto-commit
    session.sql("INSERT INTO ... WHERE 0 = 1").collect()                         # ← separate auto-commit
    session.sql("COMMIT").collect()                                              # ← nothing to commit
except Exception:
    session.sql("ROLLBACK").collect()                                            # ← nothing to rollback
    raise
```

**Severity: CRITICAL.** The proposed transaction lifecycle does not work as described.

---

### FINDING 2: HIGH — Stream-Based Architecture Adds Unnecessary Complexity

The architecture mandates streams for Event Tables while using watermark polling for ACCOUNT_USAGE views. This creates a Rube Goldberg machine of temp tables, zero-row INSERTs, and explicit transactions to work around the fact that streams don't provide a simple "read and export" pattern without consuming the offset.

**Severity: HIGH.** The wrong architectural pattern was chosen.

---

### FINDING 3: HIGH — "Best-Effort" Export After Commit Is Silent Data Loss

If the gRPC export to Splunk fails after the stream offset has advanced, the data is **permanently lost**. There is no replay mechanism. The "best-effort" label is euphemistic — it is a silent data loss design.

**Severity: HIGH.** The stream-based pipeline has no recovery path for export failures.

---

### FINDING 4: HIGH — Four Temp Tables Per Invocation Is Expensive and Unnecessary

4 CTAS operations × 12 times/hour × 24 hours = **1,152 CTAS operations per day**, each materializing data that could be read once with a single `to_pandas_batches()` call.

**Severity: HIGH.** Quadrupled materialization cost with no architectural benefit.

---

### FINDING 5: MEDIUM — Rule ET-3 "No Dedup Required" Is Asserted Without Evidence

The story asserts "Append-only streams guarantee uniqueness" for Event Tables based on standard-stream documentation. Event Table streams are a distinct variant with documented behavioral differences. The uniqueness guarantee is assumed, not verified.

**Severity: MEDIUM.**

---

### FINDING 6: MEDIUM — The Zero-Row INSERT Pattern Is Fragile

The `INSERT INTO ... SELECT CURRENT_TIMESTAMP() FROM <stream> WHERE 0 = 1` pattern has operational fragility: cross-schema DDL dependency, 1,152 phantom INSERTs per day, and failure cascade if the target table is dropped.

**Severity: MEDIUM.**

---

### FINDING 7: MEDIUM — Stream Staleness Risk Affects MVP Correctness

If the task is suspended or the app is not activated for >14 days, the stream goes stale — **losing its offset entirely** with no recovery path and no user notification.

**Severity: MEDIUM.**

---

### FINDING 8: MEDIUM — Dual-Pipeline Architecture Creates Unnecessary Code Divergence

Two entirely separate collector implementations, two sets of tests, two debugging playbooks — when both sources could use the same watermark-based pattern.

**Severity: MEDIUM.**

---

### FINDING 9: MEDIUM — `to_pandas_batches()` on Temp Tables Adds a Redundant Data Scan

Stream → CTAS → temp table → `to_pandas_batches()` scans the data **twice**. Direct `session.sql(query).to_pandas_batches()` scans once.

**Severity: MEDIUM.**

---

### FINDING 10: LOW — Entity Discrimination Include-List Has No TASK or STREAMLIT Coverage Rationale

The default include-list excludes `TASK` and `STREAMLIT` without justification. No customer-facing documentation explains what telemetry is collected vs silently discarded.

**Severity: LOW.**

---

### FINDING 11: LOW — SQL Injection Surface in `source_stream_fqn` Parameter

The `source_stream_fqn` VARCHAR parameter is used in f-string SQL construction with owner privileges. No validation code is specified.

**Severity: LOW.**

---

### FINDING 12: LOW — No Backpressure or Rate Limiting on Export

The collector exports all available data in a single invocation with no batch limit, no max-rows-per-run cap, and no circuit breaker.

**Severity: LOW.**

---

## Part 2: Live Test Evidence

All tests executed against dev account `LFB71918` on 2026-04-15. No syntax was guessed — every statement was validated against docs before execution.

### DDL Syntax Correction

`ALTER EVENT TABLE ...` does **not exist** in Snowflake. The correct syntax for all ALTER operations on Event Tables is `ALTER TABLE <event_table_name> SET ...`.

### Test 1: Row Timestamps — NOT SUPPORTED on Event Tables

| Step | SQL | Result |
|---|---|---|
| 1a | `ALTER TABLE SNOWFLAKE.TELEMETRY.EVENTS SET ROW_TIMESTAMP = TRUE` | **FAILED**: `invalid property 'ROW_TIMESTAMP' for 'EVENT_TABLE'` |
| 1b | Same on user-created ET | **FAILED**: Same error |
| 1c | `SELECT METADATA$ROW_LAST_COMMIT_TIME FROM SNOWFLAKE.TELEMETRY.EVENTS LIMIT 1` | **FAILED**: `invalid identifier` |

**Verdict: ELIMINATED.** `ROW_TIMESTAMP` is not available on Event Tables.

---

### Test 2: CHANGES Clause — FULLY FUNCTIONAL on Event Tables

| Step | SQL | Result |
|---|---|---|
| 2a | `SHOW TABLES LIKE 'EVENTS' IN SCHEMA SNOWFLAKE.TELEMETRY` | `change_tracking: ON` (enabled by default on system ET) |
| 2b | `CHANGES(INFORMATION => APPEND_ONLY) AT(OFFSET => -86400)` | **SUCCESS** |
| 2c | `CHANGES(INFORMATION => DEFAULT) AT(OFFSET => -86400)` | **SUCCESS** — all metadata columns available |
| 2d | Session variables: `SET watermark_ts = ...; SELECT ... AT(TIMESTAMP => $watermark_ts)` | **SUCCESS** |
| 2e | Bounded interval: `AT(TIMESTAMP => $start) END(TIMESTAMP => $end)` | **SUCCESS** |
| 2f | Stream offset: `AT(STREAM => 'EVT_STREAM')` | **SUCCESS** |
| 2g | Empty interval | **SUCCESS** — returns 0 rows gracefully |
| 2h | Full column projections | **SUCCESS** — all ET columns returned |

**CHANGES clause rules (from live testing):**

1. `AT(TIMESTAMP => $session_var)` requires `SET var = (SELECT ...)`
2. `AT(TIMESTAMP => 'literal')` requires literal string, not `CURRENT_TIMESTAMP()`
3. `AT(STREAM => 'fully.qualified.name')` uses stream's offset as starting point
4. `AT(OFFSET => -N)` where N is seconds — limited by retention period
5. `END(TIMESTAMP => ...)` is optional; defaults to `CURRENT_TIMESTAMP()`
6. Empty intervals return 0 rows (no error)
7. `METADATA$ACTION`, `METADATA$ISUPDATE`, `METADATA$ROW_ID` are available

**Verdict: SELECTED.** CHANGES is the data-reading primitive for Event Tables.

---

### Test 3: TIMESTAMP Is Unreliable as a Watermark Anchor

| Metric | Value |
|---|---|
| Total rows in system ET | 284,558 |
| Distinct timestamps | 193,693 |
| **Duplicate timestamps** | **90,865 (31.9%)** |

| RECORD_TYPE | Total | Duplicates | Collision Rate |
|---|---|---|---|
| METRIC | 177,857 | 88,937 | **50.0%** |
| LOG | 103,120 | 1,928 | 1.9% |
| SPAN | 3,136 | 0 | 0.0% |
| EVENT | 337 | 0 | 0.0% |
| SPAN_EVENT | 108 | 0 | 0.0% |

**Verdict:** `TIMESTAMP` is completely unreliable for watermarking. METRIC records have 50% collision rate. This is why CHANGES (which uses commit-sequence metadata, not TIMESTAMP) is essential.

---

### Test 4: System Event Table Properties

| Property | Value |
|---|---|
| `change_tracking` | **ON** (enabled by default) |
| `row_timestamp` | **OFF** (not supported) |
| `retention_time` | **1** (1 day time travel) |
| `is_event` | **Y** |
| Span `(trace_id, span_id)` uniqueness | **0 duplicates** — perfectly unique |

---

### Test 5: ACCOUNT_USAGE Views — CHANGES Is Structurally Impossible

| View | Error |
|---|---|
| `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` | `Change tracking is not supported on queries with 'Table Function'` |
| `SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY` | `Change tracking is not supported on queries with 'Materialized View'` |

| Attempted Fix | Result |
|---|---|
| `ALTER VIEW ... SET CHANGE_TRACKING = TRUE` | `Insufficient privileges to operate on view` |
| `CREATE STREAM ON VIEW ...` | Same table function error |

ACCOUNT_USAGE views are internally backed by table functions and materialized views. These are **hard platform constraints** — no consumer, ACCOUNTADMIN, or Native App can enable change tracking on them.

**Verdict:** Watermark + overlap + `QUALIFY ROW_NUMBER()` dedup is the **only viable approach** for ACCOUNT_USAGE views. This is not a design choice — it's a platform constraint.

---

### Test 6: Custom Views on Event Tables — CHANGES Works

All tests against views referencing `SNOWFLAKE.TELEMETRY.EVENTS`:

| View Type | Result |
|---|---|
| Regular view (projections + `WHERE` filter) + `CHANGE_TRACKING = TRUE` | **SUCCESS** |
| `SECURE` view + `CHANGE_TRACKING = TRUE` | **SUCCESS** |
| View with Snowflake **masking policy** on column | **SUCCESS** — masking enforced transparently |
| View with literal-masked column | **SUCCESS** |
| View with `GROUP BY` | **BLOCKED at CREATE time** |
| View with `DISTINCT` | **BLOCKED at CREATE time** |

**Supported view operations for CHANGES:**

| Supported | Not Supported |
|---|---|
| Column projections, scalar functions | `GROUP BY` |
| `WHERE` filters | `DISTINCT` |
| Inner / cross joins | `QUALIFY` |
| `UNION ALL` | `LIMIT` |
| Column masking policies | Correlated subqueries |
| Row access policies | Subqueries outside `FROM` |
| `SECURE` views | |

**Verdict:** CHANGES works on consumer custom views over Event Tables, provided the view uses only supported operations and has `CHANGE_TRACKING = TRUE`.

---

### Test 7: Stream Triggering — Not Worth the Complexity

Streams on the system Event Table were tested and are functional:

| Step | Result |
|---|---|
| `CREATE STREAM ... ON EVENT TABLE SNOWFLAKE.TELEMETRY.EVENTS APPEND_ONLY = TRUE` | SUCCESS (must be in user schema) |
| `SYSTEM$STREAM_HAS_DATA(...)` | Returns boolean correctly |
| `SYSTEM$STREAM_GET_TABLE_TIMESTAMP(...)` | Returns nanosecond timestamp |

However, **the stream-as-task-trigger adds complexity with negligible benefit:**

- Stream object creation and lifecycle management
- Staleness monitoring (14-day window)
- Native App privilege verification for stream creation on system ET
- `SYSTEM$STREAM_HAS_DATA()` saves maybe $0.05/month in compute vs. a scheduled task that returns 0 rows in <1 second
- Every consumer view would need its own stream

A simple **scheduled serverless task** (every 5 minutes, configurable) is simpler, has no failure modes from stream state, and costs effectively the same.

**Verdict: ELIMINATED.** Use scheduled tasks. No streams needed anywhere in the architecture.

---

## Part 3: Architecture Decision

### Design: Pure CHANGES + Self-Managed Watermark + Scheduled Tasks

**No streams. No temp tables. No zero-row INSERTs. No DDL transactions. No staleness risk.**

#### Event Table Collection

```python
def collect_event_table(session, source_config):
    watermark = read_watermark(session, source_config.key)
    batch_end = session.sql("SELECT CURRENT_TIMESTAMP()").collect()[0][0]

    for signal_type in source_config.signal_types:
        df = session.sql(f"""
            SELECT {source_config.projection[signal_type]}
            FROM {source_config.source_fqn}
            CHANGES(INFORMATION => APPEND_ONLY)
            AT(TIMESTAMP => '{watermark}'::TIMESTAMP_LTZ)
            END(TIMESTAMP => '{batch_end}'::TIMESTAMP_LTZ)
            WHERE RECORD_TYPE = '{signal_type}'
              AND UPPER(RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING)
                  IN ({source_config.include_list})
        """)

        for chunk in df.to_pandas_batches():
            result = export_otlp(chunk, signal_type)
            if not result.success:
                log_failure(session, source_config, signal_type, result)
                return  # watermark NOT advanced — exact retry next run

    update_watermark(session, source_config.key, batch_end)
```

#### ACCOUNT_USAGE Collection

```python
def collect_account_usage(session, source_config):
    watermark = read_watermark(session, source_config.key)
    batch_end = session.sql("SELECT CURRENT_TIMESTAMP()").collect()[0][0]
    overlap_start = watermark - timedelta(minutes=source_config.overlap_minutes)

    df = session.sql(f"""
        SELECT {source_config.projection}
        FROM {source_config.source_fqn}
        WHERE {source_config.timestamp_col} > '{overlap_start}'::TIMESTAMP_LTZ
          AND {source_config.timestamp_col} <= '{batch_end}'::TIMESTAMP_LTZ
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY {source_config.natural_key}
            ORDER BY {source_config.timestamp_col} DESC
        ) = 1
    """)

    for chunk in df.to_pandas_batches():
        result = export_otlp(chunk, source_config.signal_type)
        if not result.success:
            log_failure(session, source_config, result)
            return  # watermark NOT advanced

    update_watermark(session, source_config.key, batch_end)
```

#### Task Scheduling

Simple scheduled serverless tasks, configurable interval (default 5 minutes). No stream triggers.

```sql
CREATE OR REPLACE TASK _INTERNAL.COLLECT_TELEMETRY
  SCHEDULE = '5 MINUTE'
  WAREHOUSE = reference('consumer_warehouse')
  AS CALL _INTERNAL.RUN_COLLECTION();
```

---

### Unified Orchestration Framework

```
                  ┌──────────────────────────────────────────┐
                  │         Unified Watermark Table           │
                  │  _INTERNAL.EXPORT_WATERMARKS              │
                  │  (source_key, watermark_ts,               │
                  │   last_success_at, last_failure_reason)   │
                  └──────────────────┬───────────────────────┘
                                     │
                  ┌──────────────────┴──────────────────┐
                  │                                     │
         ┌────────▼────────┐               ┌────────────▼──────────┐
         │  Event Tables   │               │   ACCOUNT_USAGE       │
         │  + Custom Views │               │   Views               │
         ├─────────────────┤               ├───────────────────────┤
         │ CHANGES(...)    │               │ WHERE ts > wm-overlap │
         │ AT(TS => wm)    │               │   AND ts <= end       │
         │ END(TS => end)  │               │ QUALIFY ROW_NUMBER()  │
         │                 │               │   dedup               │
         │ Dedup: none     │               │                       │
         │ Overlap: none   │               │ Overlap: required     │
         └────────┬────────┘               └───────────┬───────────┘
                  │                                     │
                  └──────────────────┬──────────────────┘
                                     │
                        ┌────────────▼────────────┐
                        │  On success:             │
                        │  UPDATE watermark = end  │
                        │                          │
                        │  On failure:             │
                        │  watermark holds         │
                        │  → exact retry next run  │
                        └─────────────────────────┘
```

**Why the query generators differ:**

| Aspect | Event Tables / Custom Views | ACCOUNT_USAGE Views |
|---|---|---|
| Query primitive | `CHANGES(INFORMATION => APPEND_ONLY) AT(...) END(...)` | `WHERE col > :wm AND col <= :end` + `QUALIFY` |
| Dedup | None — Snowflake change-tracking metadata | `QUALIFY ROW_NUMBER()` on natural key |
| Overlap | None | Required (45-180 min latency) |
| Reason | CHANGES gives Snowflake-managed incremental reads | **CHANGES is structurally impossible** — views are table-function/materialized-view backed |

**What's unified:**

- Same watermark table (`_INTERNAL.EXPORT_WATERMARKS`)
- Same advance-on-success / hold-on-failure logic
- Same OTLP export pipeline and retry semantics
- Same health monitoring (watermark age alerting)
- Same backpressure/batch-limit controls
- Same `source_config` pattern (source_key, source_fqn, projection, signal_types)
- Same scheduled task infrastructure

---

### The 1-Day Retention Constraint and Mitigations

The system Event Table has `retention_time = 1` (1 day). If the pipeline fails continuously for >24 hours, the watermark falls outside the time travel window and the CHANGES query fails. Mitigations:

1. **Frequent polling (every 5 minutes):** 288 retry opportunities per day. Watermark is always <5 minutes behind under normal operation.

2. **Health monitoring:** Watermark table records `last_success_at`. Alert fires if age exceeds threshold (e.g., 6 hours), giving 18 hours to intervene.

3. **Graceful degradation:** On time-travel error, log `WATERMARK_EXPIRED`, reset watermark to `CURRENT_TIMESTAMP() - retention_time + buffer`, resume. Some data lost, but pipeline self-heals.

4. **Consumer-configurable retention:**
   ```sql
   ALTER TABLE SNOWFLAKE.TELEMETRY.EVENTS SET DATA_RETENTION_TIME_IN_DAYS = 7;
   ```
   Up to 90 days on Enterprise edition.

---

### Consumer View Configuration Guide

For consumers who want the Native App to pull telemetry from a **custom view** (e.g., with masking policies) instead of the raw Event Table:

**1. Create the view with change tracking enabled.**

```sql
CREATE OR REPLACE VIEW my_db.my_schema.my_telemetry_view
  CHANGE_TRACKING = TRUE
AS
SELECT TIMESTAMP, RESOURCE_ATTRIBUTES, RECORD_TYPE, RECORD, RECORD_ATTRIBUTES
FROM SNOWFLAKE.TELEMETRY.EVENTS
WHERE <optional filters>;
```

Or enable on an existing view:

```sql
ALTER VIEW my_db.my_schema.my_telemetry_view SET CHANGE_TRACKING = TRUE;
```

**2. The underlying Event Table must have change tracking enabled.** The system Event Table (`SNOWFLAKE.TELEMETRY.EVENTS`) has it ON by default. For custom Event Tables:

```sql
ALTER TABLE my_db.my_schema.my_event_table SET CHANGE_TRACKING = TRUE;
```

**3. The view query must only use supported operations.** Allowed: projections, `WHERE` filters, scalar functions, inner joins, `UNION ALL`, masking policies, row access policies, `SECURE` views. **NOT allowed** (Snowflake rejects at creation time): `GROUP BY`, `DISTINCT`, `QUALIFY`, `LIMIT`, correlated subqueries.

**4. Grant the Native App access.**

```sql
GRANT SELECT ON VIEW my_db.my_schema.my_telemetry_view
  TO APPLICATION SPLUNK_OBSERVABILITY_APP;
```

**5. The app cannot enable change tracking on consumer views.** The Native App lacks `ALTER VIEW` privileges on consumer-owned objects. Change tracking must be enabled by the consumer. The app's source configuration page should validate `change_tracking = ON` (via `SHOW VIEWS`) and display remediation steps if it's off.

---

### Decision Matrix

| Approach | Live Test Result | Disposition |
|---|---|---|
| Stream + Temp Tables (Story 5.1) | Transaction broken (Finding 1) | **REJECTED** |
| Row Timestamps (`METADATA$ROW_LAST_COMMIT_TIME`) | Not supported on Event Tables | **ELIMINATED** |
| Stream + CHANGES Hybrid | Re-introduces stream complexity with negligible benefit | **ELIMINATED** |
| TIMESTAMP-based watermark + overlap + dedup | 50% collision rate for METRIC; no natural key for LOG/METRIC | **ELIMINATED** |
| Stream-triggered tasks | Works but $0.05/month savings vs. scheduled task | **ELIMINATED** |
| **Pure CHANGES + watermark + scheduled tasks** | Fully functional on ETs, custom views, secure views, masked views | **SELECTED** |
| CHANGES on ACCOUNT_USAGE views | Structurally impossible (table function / materialized view backing) | Watermark + overlap + dedup is the **only option** |

---

## Appendix A: Verification Sources

| Source | Key Insight |
|---|---|
| [Snowflake Transactions Docs](https://docs.snowflake.com/en/sql-reference/transactions) | DDL implicitly commits active transactions |
| [Snowflake Streams Intro](https://docs.snowflake.com/en/user-guide/streams-intro) | Zero-row INSERT pattern, stream offset semantics |
| [Snowflake CHANGES Clause](https://docs.snowflake.com/en/sql-reference/constructs/changes) | Time-windowed CDC without stream; APPEND_ONLY mode |
| [Snowflake Event Table Operations](https://docs.snowflake.com/en/developer-guide/logging-tracing/event-table-operations) | Supported operations, stream creation syntax |
| [Snowflake Row Timestamps](https://docs.snowflake.com/en/user-guide/data-engineering/row-timestamps) | `METADATA$ROW_LAST_COMMIT_TIME` — not supported on Event Tables |
| [Snowflake Event Table Setup](https://docs.snowflake.com/en/developer-guide/logging-tracing/event-table-setting-up) | "sent asynchronously... not immediately available... after a few minutes" |
| [Snowflake ALTER Event Table](https://docs.snowflake.com/en/sql-reference/sql/alter-table-event-table) | Supported ALTER properties; correct syntax is `ALTER TABLE`, not `ALTER EVENT TABLE` |
| Perplexity Deep Research (2 sessions, 50 citations) | Comprehensive comparison favoring watermark approach |
| Live SQL testing (Snow CLI + Snowflake MCP, 2026-04-15) | All CHANGES tests, ACCOUNT_USAGE tests, custom view tests, timestamp analysis |

## Appendix B: Live Test Verification (ACCOUNT_USAGE + Custom Views, 2026-04-15)

| Test | Method | Result |
|---|---|---|
| `QUERY_HISTORY` CHANGES | Snowflake MCP | `Change tracking is not supported on queries with 'Table Function'` |
| `TASK_HISTORY` CHANGES | Snowflake MCP | `Change tracking is not supported on queries with 'Materialized View'` |
| `ALTER VIEW QUERY_HISTORY SET CHANGE_TRACKING = TRUE` | Snowflake MCP | `Insufficient privileges` |
| `CREATE STREAM ON VIEW QUERY_HISTORY` | Snowflake MCP | Same table function error |
| Regular view on ET + CHANGES | Snow CLI | SUCCESS |
| SECURE view on ET + CHANGES | Snow CLI | SUCCESS |
| View with masking policy + CHANGES | Snow CLI | SUCCESS — masking enforced transparently |
| View with GROUP BY + CHANGE_TRACKING | Snow CLI | BLOCKED at CREATE time |
| View with DISTINCT + CHANGE_TRACKING | Snow CLI | BLOCKED at CREATE time |

## Appendix C: Severity Definitions

| Severity | Definition |
|---|---|
| **CRITICAL** | Architecture does not work as designed. Must fix before implementation. |
| **HIGH** | Significant cost, risk, or complexity issue. Should fix before implementation. |
| **MEDIUM** | Suboptimal design choice. Should address in story refinement or follow-up. |
| **LOW** | Minor issue or missing rationale. Address when convenient. |
