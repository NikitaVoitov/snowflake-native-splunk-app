# Story 5.1: Incremental Event Table Collection and Export

Status: ready-for-dev

## Story

As an operator (Sam),
I want Event Table telemetry to be collected incrementally via a self-managed watermark and Snowflake's `CHANGES` clause, scoped to MVP entity types, and handed to the OTLP export foundation with advance-on-success / hold-on-failure semantics,
so that only relevant new SQL and Snowpark compute telemetry is delivered to Splunk, with exact retry on export failure and no silent data loss.

## Acceptance Criteria

1. **Given** the Event Table collector procedure is executed against a selected Event Table source (either `SNOWFLAKE.TELEMETRY.EVENTS` or a consumer-managed custom view over an Event Table)
   **When** the procedure runs from an integration harness or from the scheduled serverless task that Epic 6 will provision (default cadence: every 1 minute)
   **Then** it sets `session.sql_simplifier_enabled = True`, loads config from `_internal.config`, initialises the OTLP exporters via `init_exporters(endpoint, pem)`, generates a UUID `run_id`, captures `batch_end = SELECT CURRENT_TIMESTAMP()` **once at the start of the run**, and reads the current watermark for the source from `_internal.export_watermarks`
   **And** if no watermark row exists yet for the source, the collector seeds one to `batch_end - INTERVAL '{event_table.initial_seed_buffer_seconds} SECONDS'` using that same captured `batch_end` as the seed anchor (default `60` seconds — one task cadence behind `batch_end` so the first run captures the immediately-preceding 60-second window of telemetry rather than a zero-width window; operators who want more aggressive backfill can raise the buffer in `_internal.config`, capped at the source's time-travel retention minus a 60-second safety margin)
   **And** the procedure does NOT open any explicit transaction and does NOT materialise any temp or staging tables — the `CHANGES` clause plus the watermark is the only incremental primitive

2. **Given** the collector is reading incremental rows
   **When** it queries the source
   **Then** it issues **one `session.sql(...)` query per signal type** (`SPAN`, `SPAN_EVENT`, `LOG`, `METRIC`) against `{source_fqn}` using the following read primitive:
   ```sql
   SELECT <typed projection per signal, see AC 3>
   FROM {source_fqn}
   CHANGES(INFORMATION => APPEND_ONLY)
     AT(TIMESTAMP => '{watermark_iso}'::TIMESTAMP_LTZ)
     END(TIMESTAMP => '{batch_end_iso}'::TIMESTAMP_LTZ)
   WHERE RECORD_TYPE = '{signal}'
     AND UPPER(RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING)
         IN ({include_list})
   ```
   **And** the entity-discrimination include-list is loaded from `_internal.config` key `entity_discrimination.include_list` (comma-separated, uppercase), falling back to `('PROCEDURE','FUNCTION','QUERY','SQL','STATEMENT')` as documented in `event_table_entity_discrimination_strategy.md` §5.1 and `telemetry_preparation_for_export.md` §7 Rule ET-2
   **And** the entity filter uses `UPPER(...)` normalisation for case-insensitive matching
   **And** no `QUALIFY ROW_NUMBER()` dedup is applied — Event Table CHANGES rows are already unique by Snowflake's internal change-tracking metadata
   **And** no `WHERE TIMESTAMP >= ...` predicate is applied — the `CHANGES AT/END(TIMESTAMP)` window is the only time scope (the `TIMESTAMP` column is not a unique row key and must not be used as a watermark anchor)

3. **Given** each per-signal `CHANGES` query projects columns
   **When** the query is constructed
   **Then** it uses the explicit typed extraction template from `telemetry_preparation_for_export.md` §8 (§8.1 SPAN, §8.2 SPAN_EVENT, §8.3 LOG, §8.4 METRIC) with `:"key"::TYPE` SQL path syntax for all VARIANT field access
   **And** the projected column aliases match the `COL_*` constants in `app/python/telemetry_constants.py` so that `span_mapper.map_span_chunk(...)` and `map_span_events(...)` (and the log/metric mappers) consume the DataFrames without renaming
   **And** no `SELECT *` is ever used (Rule S-1)
   **And** no joins, dedup, or casts are performed in Python that could have been pushed to SQL (Rule S-2)

4. **Given** each per-signal `CHANGES` query is executed
   **When** the collector iterates results
   **Then** it calls **`df.to_pandas_batches()` directly on the `session.sql(query)` DataFrame** — with no intermediate CTAS, no staging table, no `.collect()`, no `.to_pandas()` (Rule ET-6 / S-2)
   **And** each pandas chunk is mapped and exported in-loop (one chunk → map → export → next chunk), bounding peak memory

5. **Given** the collector must bind SPAN_EVENT rows to their parent SPAN rows for export
   **When** it processes the two related signals
   **Then** it buffers `SPAN_EVENT` chunks for the current run into a `{(trace_id, span_id): [events]}` in-memory index via `span_mapper.map_span_events(df)`
   **And** passes that index as `span_events_by_span_key` to `span_mapper.map_span_chunk(df, account_name, span_events_by_span_key=...)` when mapping SPAN chunks
   **And** to guarantee events are available when mapping spans, the collector processes signal types in this order: **`SPAN_EVENT` first (fully materialised into the index), then `SPAN` (streaming chunks, exported in-loop), then `LOG`, then `METRIC`**
   **And** `event_table.max_span_events_per_run` (default `50_000`) is a warning threshold for the buffered SPAN_EVENT volume in a single run — if the threshold is exceeded, the collector logs a warning and continues the run normally; it does NOT perform mid-run flushes, partial exports, or alternate control-flow in MVP

6. **Given** each mapped batch is ready to export
   **When** the collector dispatches to OTLP
   **Then** it calls:
   - `export_spans(spans_batch)` from `app/python/otlp_export.py` for SPAN rows (where `spans_batch` is `list[ReadableSpan]` produced by `span_mapper.map_span_chunk(df, account_name, span_events_by_span_key=...)`)
   - `export_logs(logs_batch)` for LOG rows (where `logs_batch` is `list[LogBatchItem]` produced by `log_mapper.map_log_chunk(df, account_name)`)
   - `export_metrics(metrics_batch)` for METRIC rows (where `metrics_batch` is `MetricsData` produced by `metric_mapper.map_metric_chunk(df, account_name)`)
   **And** `account_name` is a required positional argument for all three mappers and is derived once at the top of the run via `session.sql("SELECT CURRENT_ACCOUNT()").collect()[0][0]`, then threaded through unchanged
   **And** each call returns an `ExportOutcome` (from `export_result.py`)
   **And** no Python-side retry loop is added — the OTel SDK's built-in gRPC retry is the only retry layer

7. **Given** a per-chunk export returns a successful `ExportOutcome`
   **When** the success is recorded
   **Then** the collector calls `record_export_success(session, "event_table_collector", source_name, signal_type, batch_size, run_id)` from `app/python/pipeline_telemetry.py`
   **And** calls `log_export_success(ExportContext(...), outcome)` to emit a structured INFO log with fields `pipeline`, `source`, `run_id`, `signal_type`, `batch_size`, `duration_ms`

8. **Given** a per-chunk export returns a terminal failure (`outcome.terminal is True`)
   **When** the failure is observed
   **Then** the collector:
   1. Calls `record_batch_failure(session, "event_table_collector", source_name, outcome, run_id)`
   2. Calls `log_terminal_failure(ExportContext(...), outcome)`
   3. **Stops the run immediately — does NOT advance the watermark, does NOT attempt subsequent signal types or chunks, returns the run summary with `status = "failed"`**
   **And** on the next invocation the collector re-reads the unchanged watermark and re-executes the same `AT(TIMESTAMP => watermark)` window — producing an exact retry of the lost batch (advance-on-success / hold-on-failure)
   **And** the retry replays **every** chunk from that window — including any chunks from earlier signal types that already exported successfully in the failed run. This yields **at-least-once** delivery semantics: on a partial-success retry, some rows will be exported twice (e.g. if SPAN_EVENT and SPAN succeeded but LOG failed terminally, the next run re-exports the SPAN_EVENT and SPAN rows alongside LOG). This is an accepted MVP trade-off in exchange for simple, provably correct watermark semantics; downstream dedup (if required) is a Splunk-side concern (e.g. `dedup` search-time filtering on `run_id` + `trace_id`/`span_id`).

9. **Given** all chunks across all signal types have been successfully exported
   **When** the run completes
   **Then** the collector calls `update_watermark(session, source_name, batch_end)` which performs an atomic `MERGE` into `_internal.export_watermarks` setting `WATERMARK_VALUE = batch_end` and `UPDATED_AT = CURRENT_TIMESTAMP()`
   **And** watermark advancement happens **outside and after** the export loop — never mid-run
   **And** if the `CHANGES` query window contains zero matching rows for every signal (e.g. the source has no PROCEDURE/FUNCTION/QUERY activity in that window), the watermark is still advanced to `batch_end`

10. **Given** the `CHANGES AT(TIMESTAMP => watermark)` query raises a Snowflake time-travel error (e.g. `"Time travel data is not available for ..."` indicating the watermark has fallen outside the source's retention window)
    **When** the error is caught
    **Then** the collector treats this as a recoverable `WATERMARK_EXPIRED` condition:
    1. Emits a structured WARNING log with fields `pipeline="event_table_collector"`, `source`, `run_id`, `watermark_expired=True`, `old_watermark`, Snowflake error code/message
    2. Records a health row with `METRIC_NAME='watermark_reset'` and `METRIC_VALUE=1` (the lowercase metric name aligned with `architecture.md` Pipeline Health Metric Names; `WATERMARK_EXPIRED` remains the uppercase operational log-event code)
    3. Resets the watermark to `SELECT CURRENT_TIMESTAMP() - INTERVAL '{event_table.watermark_reset_buffer_seconds} SECONDS'` (default `60` seconds — one task cadence behind `CURRENT_TIMESTAMP()` and safely inside the default 1-day time-travel window)
    4. Returns from the run with `status = "watermark_reset"`
    **And** the next scheduled invocation resumes normally from the reset watermark — some intervening data is lost, but the pipeline self-heals

11. **Given** the selected source is a consumer-managed custom view over an Event Table
    **When** the collector reads from the view via `CHANGES`
    **Then** exported data reflects Snowflake-enforced masking, row-access, and projection outcomes transparently — the collector does not add its own governance layer
    **And** the collector code path is identical for direct Event Tables and custom views — the `source_fqn` parameter is the only variable
    **And** if the consumer has not enabled `CHANGE_TRACKING = TRUE` on the view, the `CHANGES` query will fail with a Snowflake error; the collector catches it, records a health row with `METRIC_NAME='source_change_tracking_disabled'`, emits a structured ERROR log, and returns with `status="source_change_tracking_disabled"` — it does NOT advance the watermark (the consumer must remediate by running `ALTER VIEW ... SET CHANGE_TRACKING = TRUE`)

12. **Given** a VARIANT field required for OTel enrichment is missing or NULL in a CHANGES row
    **When** the mapper processes that row
    **Then** `span_mapper` / `log_mapper` / `metric_mapper` handle the NULL gracefully (existing behaviour from Story 4.2)
    **And** the collector does not abort the run — the row is exported with the available fields (best-effort enrichment)

13. **Given** the collector procedure completes (success, watermark-reset, or terminal failure)
    **When** the run finishes
    **Then** it records aggregate run rows in `_metrics.pipeline_health` with `PIPELINE_NAME = 'event_table_collector'`, `SOURCE_NAME = source_name`, `RUN_ID = run_id`: per-signal `rows_exported` counters (one row per signal type, emitted by `record_export_success`), `rows_failed` on terminal failure (emitted by `record_batch_failure`), `watermark_reset` on reset, and a final `run_duration_ms` row aggregating wall-clock time for the run
    **And** the procedure returns a JSON string summarising the run with fields: `run_id`, `source_name`, `status` (one of `"success"`, `"failed"`, `"watermark_reset"`, `"source_change_tracking_disabled"`), `watermark_before`, `watermark_after`, per-signal counts (`spans_exported`, `span_events_buffered`, `logs_exported`, `metrics_exported`), `total_failed`, `duration_ms`

14. **Given** the `source_fqn` parameter is user-visible (passed from the scheduled task or UI in a later story) and interpolated into `session.sql(f"... FROM {source_fqn} CHANGES(...)")`
    **When** the collector accepts the parameter
    **Then** it validates `source_fqn` against a strict 3-part identifier pattern (`^[A-Z_][A-Z0-9_]{0,254}\.[A-Z_][A-Z0-9_]{0,254}\.[A-Z_][A-Z0-9_]{0,254}$`, case-normalised to upper) before any SQL construction
    **And** it validates the entity-discrimination include-list values against `^[A-Z][A-Z0-9_]{0,63}$` per element (no quotes, commas, or semicolons)
    **And** it validates `source_name` (the logical key used in `_internal.export_watermarks`) against `^[A-Za-z0-9_.-]{1,256}$` — non-empty, length ≤ 256, alphanumeric plus `_`, `.`, `-` only. Although `source_name` is always parameter-bound (never interpolated into SQL), an empty or malformed value would silently corrupt watermark state for the lifetime of the deployment, so the collector enforces the contract at the SP boundary
    **And** any validation failure raises a SQL error and records a health row with `METRIC_NAME='invalid_source_parameter'` — the collector never executes unvalidated identifiers

## Tasks / Subtasks

- [ ] **Task 1: Create `app/python/watermark.py` — shared watermark helpers** (AC: 1, 9, 10)
  - [ ] 1.1 `read_watermark(session, source_name, initial_seed_buffer_seconds: int, batch_end_anchor: datetime) -> datetime`: run `SELECT WATERMARK_VALUE FROM _internal.export_watermarks WHERE SOURCE_NAME = ?` via parameterised `session.sql(query, params=[source_name]).collect()`; if no row, `MERGE` a seed row with `WATERMARK_VALUE = DATEADD(SECOND, -initial_seed_buffer_seconds, ?)` using the caller-supplied `batch_end_anchor`, and return the seeded value
  - [ ] 1.2 `update_watermark(session, source_name, batch_end: datetime) -> None`: atomic `MERGE INTO _internal.export_watermarks ... WHEN MATCHED THEN UPDATE SET WATERMARK_VALUE = ?, UPDATED_AT = CURRENT_TIMESTAMP() WHEN NOT MATCHED THEN INSERT ...`
  - [ ] 1.3 `reset_watermark(session, source_name, buffer_seconds: int) -> datetime`: `MERGE` with `WATERMARK_VALUE = DATEADD(SECOND, -buffer_seconds, CURRENT_TIMESTAMP())`, return new value
  - [ ] 1.4 `from __future__ import annotations`; use `TYPE_CHECKING` for `Session`; export all three functions; no Streamlit imports (stored-procedure-only module)

- [ ] **Task 2: Create `app/python/event_table_collector.py` — the collector SP handler** (AC: 1–14)
  - [ ] 2.1 Define the handler signature: `collect_event_table(session: Session, source_fqn: str, source_name: str) -> str` (returns JSON summary) and set `session.sql_simplifier_enabled = True` before any collector queries
  - [ ] 2.2 Validate `source_fqn`, `source_name`, and the include-list early using the regex patterns from AC 14; on mismatch record an `invalid_source_parameter` health row and raise `ValueError`. `source_name` is validated first (before any `_metrics.pipeline_health` INSERT), because a malformed `source_name` would itself poison the health row — in that case log the error and raise directly without attempting the health INSERT
  - [ ] 2.3 Load config from `_internal.config` via a small parameterised `session.sql(..., params=[...])` helper on the SP side (the Streamlit-side `utils/config.py` pattern is not importable here; mirror the same "read key → scalar" shape inline). Keys needed: `entity_discrimination.include_list`, `otlp.endpoint`, `event_table.max_span_events_per_run`, `event_table.initial_seed_buffer_seconds`, `event_table.watermark_reset_buffer_seconds`. Use `.collect()` for these small control-flow queries. Example helper:
    ```python
    def _read_config(session, key: str, default: str | None = None) -> str | None:
        rows = session.sql(
            "SELECT CONFIG_VALUE FROM _internal.config WHERE CONFIG_KEY = ?",
            params=[key],
        ).collect()
        if rows and rows[0][0] is not None:
            return str(rows[0][0]).strip()
        return default
    ```
    Numeric keys are cast via `int(...)` at the call site with a try/except that falls back to the documented default and logs a WARNING
  - [ ] 2.4 Read the PEM from the `otlp_pem_cert` secret via `secret_reader.get_pem_secret(session)`; call `init_exporters(endpoint, pem)` once
  - [ ] 2.5 Generate `run_id = str(uuid.uuid4())` and build a shared `ExportContext(pipeline_name="event_table_collector", source_name=source_name, run_id=run_id)` for all logging calls
  - [ ] 2.6 Query `SELECT CURRENT_TIMESTAMP()` once at the start of the run → `batch_end`; then call `watermark.read_watermark(session, source_name, initial_seed_buffer_seconds, batch_end)` → `watermark_ts`. With the default `initial_seed_buffer_seconds=60`, the first-ever run for a source yields `watermark_ts = batch_end - 60s`, so the first `CHANGES` window captures the immediately-preceding 60-second interval of telemetry
  - [ ] 2.7 Build per-signal CHANGES SQL using the §8.1–§8.4 projection templates; format the include-list into a comma-separated quoted tuple (values already regex-validated); format `watermark_ts` and `batch_end` as ISO-8601 literals with `.isoformat(timespec='microseconds')` to pin microsecond precision (matches the `TIMESTAMP_LTZ` column resolution and avoids platform-dependent default formatting). The Snowflake `TIMESTAMP_LTZ` cast accepts this canonical shape directly. Note: `session.sql("SELECT CURRENT_TIMESTAMP()").collect()[0][0]` returns a **timezone-aware `datetime`** (Snowpark binds `TIMESTAMP_LTZ` to `datetime` with a UTC offset); do not strip the tzinfo or compare against naive datetimes. The same aware `datetime` is threaded through `read_watermark` → `build_changes_sql` → `update_watermark` unchanged, so `.isoformat(timespec='microseconds')` emits e.g. `2026-04-21T14:23:07.842193+00:00`
  - [ ] 2.8 Update `app/python/span_mapper.py` so:
    - `map_span_events(df: pd.DataFrame) -> dict[tuple[str, str], list[Event]]` returns a mapping keyed by the composite `(trace_id_hex, span_id_hex)` tuple (current implementation keys by `span_id_hex` alone — rename the internal variable from `result[span_id_hex]` to `result[(trace_id_hex, span_id_hex)]` and read `trace_id` via `_safe_str(_row_value(row, column_indexes, COL_TRACE_ID))`; skip the event if either id is missing)
    - `map_span_chunk(df, account_name, span_events_by_span_key: Mapping[tuple[str, str], Sequence[Event]] | None = None)` consumes the composite-key mapping — rename the keyword argument from `span_events_by_span_id` to `span_events_by_span_key`, and change the internal lookup from `events_map.get(span_id_hex, [])` to `events_map.get((trace_id_hex, span_id_hex), [])`
    - This is a **breaking rename** — the existing `span_events_by_span_id` keyword is retired. Verified there are no other callers of `map_span_events` or the `span_events_by_span_id` keyword outside this story's collector (`rg "span_events_by_span_id\\|map_span_events" app/` returns only `span_mapper.py` itself)
    - Update `tests/test_span_mapper.py` in Task 6.12 to assert the new composite-key contract
  - [ ] 2.9 Signal-processing order: SPAN_EVENT first — materialise via `span_mapper.map_span_events(df)` into `span_events_by_span_key` using `to_pandas_batches()`; if buffered event count exceeds `event_table.max_span_events_per_run`, log a warning and continue normally; then SPAN — stream chunks, map via `span_mapper.map_span_chunk(df, account_name, span_events_by_span_key=...)`, export in-loop; then LOG — stream chunks, map via `log_mapper.map_log_chunk(df, account_name)`, export in-loop; then METRIC — stream chunks, map via `metric_mapper.map_metric_chunk(df, account_name)`, export in-loop. All three mappers take `account_name` as a required positional argument (see AC 6)
  - [ ] 2.10 For each exported chunk branch on `outcome.success`: success → `record_export_success(...)` + `log_export_success(...)` + continue; terminal failure → `record_batch_failure(...)` + `log_terminal_failure(...)` + **return immediately with `status="failed"` and watermark unchanged** (AC 8)
  - [ ] 2.11 On full success across all signals: `watermark.update_watermark(session, source_name, batch_end)` → return JSON with `status="success"`
  - [ ] 2.12 Wrap the per-signal query execution in a targeted `except Exception as e` that inspects the error string for:
    - Time-travel markers (`"Time travel data is not available"`, `"SQL compilation error: Time travel"`) → WATERMARK_EXPIRED path (AC 10): `watermark.reset_watermark(session, source_name, watermark_reset_buffer_seconds)`, record `watermark_reset` health row, log WARNING (with structured field `watermark_expired=True` as the log-event code), return `status="watermark_reset"`
    - Change-tracking disabled markers (`"Change tracking is not enabled"`, `"Change tracking is not supported"`) → record `source_change_tracking_disabled` health row, log ERROR, return `status="source_change_tracking_disabled"` with watermark unchanged (AC 11)
    - All other exceptions → re-raise so the SP fails loudly
  - [ ] 2.13 Derive `account_name` once at the top of the run via `session.sql("SELECT CURRENT_ACCOUNT()").collect()[0][0]` and thread it unchanged into every `map_span_chunk(df, account_name, ...)`, `map_log_chunk(df, account_name)`, and `map_metric_chunk(df, account_name)` call — all three mappers require this positional argument for the OTel `Resource` builder (verified against `app/python/log_mapper.py:213`, `metric_mapper.py:221`, `span_mapper.py:349`)
  - [ ] 2.14 Measure overall `duration_ms` via `time.perf_counter()`; emit a final `run_duration_ms` health row with an inline parameterised `INSERT` matching the shape used by `pipeline_telemetry._INSERT_SQL`; include `duration_ms` in the returned JSON summary

- [ ] **Task 3: Entity-discrimination config loader** (AC: 2, 14)
  - [ ] 3.1 Define `_DEFAULT_ENTITY_INCLUDE = ('PROCEDURE', 'FUNCTION', 'QUERY', 'SQL', 'STATEMENT')` in `event_table_collector.py`
  - [ ] 3.2 Parse the config string (comma-separated) with `str.split(",")`, `.strip()`, `.upper()`, regex-validate each token per AC 14; reject the config and fall back to the default on any validation failure (log a WARNING)
  - [ ] 3.3 Build the SQL `IN (...)` fragment by joining single-quoted validated tokens with commas

- [ ] **Task 4: Register the collector stored procedure in `app/setup.sql`** (AC: 1, 11)
  - [ ] 4.1 Add `CREATE OR REPLACE PROCEDURE _internal.collect_event_table(source_fqn VARCHAR, source_name VARCHAR)`:
    - `RETURNS VARCHAR`
    - `LANGUAGE PYTHON`
    - `RUNTIME_VERSION = '3.13'`
    - `PACKAGES = ('snowflake-snowpark-python', 'opentelemetry-sdk', 'opentelemetry-exporter-otlp-proto-grpc', 'grpcio', 'pandas')` — the `source_fqn` / include-list validation uses stdlib `re` only, so `validators` is not required
    - `HANDLER = 'event_table_collector.collect_event_table'`
    - `IMPORTS` — full list (see Dev Notes → IMPORTS Chain)
    - `EXTERNAL_ACCESS_INTEGRATIONS = (otlp_egress_eai)`
    - `SECRETS = ('otlp_pem_cert' = _internal.otlp_pem_secret)`
    - `EXECUTE AS OWNER`
  - [ ] 4.2 Register in `_internal` (not `app_public`) — this SP is invoked by the Epic 6 scheduled task, not directly by the consumer. No `GRANT TO app_admin` needed

- [ ] **Task 5: Update `snowflake.yml` artifacts** (AC: all)
  - [ ] 5.1 Add `- src: app/python/event_table_collector.py` / `dest: python/event_table_collector.py`
  - [ ] 5.2 Add `- src: app/python/watermark.py` / `dest: python/watermark.py`
  - [ ] 5.3 Verify `span_mapper.py`, `log_mapper.py`, `metric_mapper.py`, `telemetry_constants.py`, `otlp_export.py`, `export_result.py`, `pipeline_telemetry.py`, `endpoint_parse.py`, `secret_reader.py` all already have artifact entries

- [ ] **Task 6: Unit tests — `tests/test_event_table_collector.py`** (AC: 1–14)
  - [ ] 6.1 Mock `Session.sql(...).collect()` / `.to_pandas_batches()`; verify that on a non-empty watermark + non-empty CHANGES response the collector issues **exactly 4 CHANGES queries** (one per signal type), in the order `SPAN_EVENT → SPAN → LOG → METRIC`, each with the expected `AT(TIMESTAMP=>...)` / `END(TIMESTAMP=>...)` and entity filter
  - [ ] 6.2 Verify the collector emits exactly one `MERGE INTO _internal.export_watermarks` call, and only on a fully successful run (never mid-run)
  - [ ] 6.3 Entity-discrimination tests:
    - Default include-list produces exactly `('PROCEDURE','FUNCTION','QUERY','SQL','STATEMENT')` IN-clause
    - Config override of `entity_discrimination.include_list` is honoured when all tokens pass validation
    - Malformed config tokens (contain `'`, `;`, lowercase, empty) cause fallback to default with a WARNING log
  - [ ] 6.4 Watermark lifecycle tests:
    - First-run seeding with default `initial_seed_buffer_seconds=60`: collector captures `batch_end = T₀` first, no `_internal.export_watermarks` row exists, `read_watermark(..., batch_end_anchor=T₀)` seeds watermark to `T₀ - 60 seconds`, first-run `CHANGES` window is `AT(T₀ - 60s) END(T₀)` (one cadence wide), rows from the preceding minute are exported, and the watermark row persists at `T₀`
    - First-run seeding with override `initial_seed_buffer_seconds=300`: collector captures `batch_end = T₀`, `read_watermark(..., batch_end_anchor=T₀)` seeds watermark to `T₀ - 300 seconds`
    - First-run seeding with override `initial_seed_buffer_seconds=0` (zero-width opt-out): watermark seeded to exactly `T₀`, first-run `CHANGES` window is `AT(T₀) END(T₀)` and exports zero rows
    - Success path: watermark is `update_watermark`'d to `batch_end` exactly once, after all exports succeed
    - Failure path: mock `export_spans` to return terminal `ExportOutcome` → verify `update_watermark` is NOT called → verify `record_batch_failure` + `log_terminal_failure` ARE called → verify JSON status `"failed"`
  - [ ] 6.5 WATERMARK_EXPIRED path: raise a simulated Snowflake error containing `"Time travel data is not available"` on the first CHANGES query → verify `reset_watermark` called with `watermark_reset_buffer_seconds` (default 60) → verify health row `METRIC_NAME='watermark_reset'` with `METRIC_VALUE=1` → verify JSON status `"watermark_reset"`
  - [ ] 6.6 CHANGE_TRACKING disabled path: raise `"Change tracking is not enabled"` → verify `source_change_tracking_disabled` health row → verify watermark NOT reset → verify JSON status `"source_change_tracking_disabled"`
  - [ ] 6.7 Zero-row run: CHANGES DataFrames yield zero pandas batches across all signals → verify watermark IS advanced to `batch_end`
  - [ ] 6.8 SPAN ↔ SPAN_EVENT correlation: feed SPAN_EVENT DataFrame chunks keyed by `(trace_id, span_id)` — including two traces that reuse the same `span_id` — and verify `span_events_by_span_key` is passed into `map_span_chunk` and events attach only to the correct parent spans
  - [ ] 6.9 SPAN_EVENT warning threshold: feed more than `event_table.max_span_events_per_run` events → verify a warning is logged and export still proceeds normally with no special flush/truncation path
  - [ ] 6.10 `source_fqn` and `source_name` validation:
    - Accept `DB.SCHEMA.VIEW`, `DB.SCHEMA.EVENT_TABLE`
    - Accept lowercase `db.schema.view` and verify the collector upper-cases it before regex validation and before SQL construction (AC 14 "case-normalised to upper")
    - Reject `db.schema.view; DROP TABLE foo`
    - Reject `DB.SCHEMA."weird"` (double-quoted identifiers)
    - Reject single-part or two-part identifiers (`FOO`, `DB.SCHEMA`)
    - Reject identifiers with leading digits (`1DB.SCHEMA.VIEW`) or invalid characters (`DB-NAME.SCHEMA.VIEW`)
    - Accept `source_name` values like `prod_events`, `snowflake.telemetry.events`, `consumer-view-01`
    - Reject empty `source_name`, whitespace-only, length > 256, or values containing `;`, `'`, `"`, or SQL-wildcard characters
  - [ ] 6.11 Run-summary JSON shape: verify every field listed in AC 13 is present
  - [ ] 6.12 Update `tests/test_span_mapper.py` expectations for the new composite-key SPAN_EVENT contract so mapper unit tests enforce `(trace_id, span_id)` correlation explicitly

- [ ] **Task 7: Watermark-helper unit tests — `tests/test_watermark.py`** (AC: 1, 9, 10)
  - [ ] 7.1 `read_watermark` with pre-existing row returns the row's value unchanged
  - [ ] 7.2 `read_watermark` with no row and default `initial_seed_buffer_seconds=60` seeds exactly 60 seconds behind the caller-supplied `batch_end_anchor` and returns that value
  - [ ] 7.3 `read_watermark` with no row and override `initial_seed_buffer_seconds=0` seeds exactly at the caller-supplied `batch_end_anchor` (zero-width opt-out)
  - [ ] 7.4 `read_watermark` with no row and override `initial_seed_buffer_seconds=300` seeds exactly 300 seconds behind the caller-supplied `batch_end_anchor`
  - [ ] 7.5 `update_watermark` issues the expected `MERGE` and updates `UPDATED_AT`
  - [ ] 7.6 `reset_watermark(buffer_seconds=60)` yields a value ~60 seconds behind `CURRENT_TIMESTAMP()` (tolerate a few seconds of drift)

- [ ] **Task 8: Integration test — `tests/integration/test_event_table_collector.py`** (AC: 1, 2, 4, 6, 7, 9, 11, 13)
  - [ ] 8.1 Use Epic 4's `generate_test_spans` / `generate_test_logs` / `generate_test_exception` procedures to emit fresh rows into `SNOWFLAKE.TELEMETRY.EVENTS` with a known `test_id`
  - [ ] 8.2 Pre-seed `_internal.export_watermarks` for the test source to a timestamp just before the test generation started
  - [ ] 8.3 Call `_internal.collect_event_table(source_fqn => 'SNOWFLAKE.TELEMETRY.EVENTS', source_name => 'test_et_source')` via `snow sql`
  - [ ] 8.4 Verify the OTLP collector journal (per `dev_environment.mdc` — `ssh otelcol "sudo journalctl ..."`) shows the test_id spans/logs
  - [ ] 8.5 Verify spans appear in Splunk Observability APM (realm REST API) and logs in Splunk Enterprise (REST export) within the configured wait window
  - [ ] 8.6 Verify `_internal.export_watermarks` advanced to `batch_end`
  - [ ] 8.7 Verify `_metrics.pipeline_health` has per-signal `rows_exported` rows and a `run_duration_ms` row tagged with the run's `run_id`
  - [ ] 8.8 Second-run idempotence check: invoke the collector again immediately → verify zero rows exported (all filtered by the advanced watermark) → watermark still advances
  - [ ] 8.9 Failure replay: to force a terminal OTLP failure without redeploying the app, run:
    ```sql
    UPDATE _internal.config SET CONFIG_VALUE = 'invalid.example.com:4317' WHERE CONFIG_KEY = 'otlp.endpoint';
    CALL _internal.collect_event_table('SNOWFLAKE.TELEMETRY.EVENTS', 'test_et_source');
    ```
    in a fresh session (the collector's `init_exporters(...)` is called once per SP invocation, so a new session picks up the invalid endpoint immediately); verify watermark does NOT advance and `rows_failed` is recorded; then run:
    ```sql
    UPDATE _internal.config SET CONFIG_VALUE = '<good endpoint>' WHERE CONFIG_KEY = 'otlp.endpoint';
    CALL _internal.collect_event_table('SNOWFLAKE.TELEMETRY.EVENTS', 'test_et_source');
    ```
    in another fresh session and verify the previously-skipped rows are now exported (advance-on-success / hold-on-failure contract)

- [ ] **Task 9: Scalability benchmark and operational guardrails** (AC: 5, 13; NFR19)
  - [ ] 9.1 Run a representative Event Table benchmark that exercises up to `1,000,000` rows for a single scheduled run, including enough `SPAN_EVENT` volume to stress the in-memory correlation path, and capture completion time plus whether the collector hits timeout or unrecoverable memory failure
  - [ ] 9.2 Record the observed safe operating envelope for the MVP collector (task cadence, warehouse size, approximate buffered `SPAN_EVENT` count, warning behavior from `event_table.max_span_events_per_run`) in the story completion notes or a linked benchmark artifact before marking the story done
  - [ ] 9.3 If the benchmark exposes instability against the NFR19 target, document the required MVP guardrail recommendation (for example tighter cadence, larger warehouse, or lower tolerated per-run SPAN_EVENT volume) and carry the bounded-buffering follow-up as post-MVP work rather than silently accepting the gap

## Dev Notes

### Story Boundary

This story creates the **Event Table collector stored procedure** and its backing watermark helper module — the first real data pipeline in the app. It reads from the source (Event Table or consumer custom view) via Snowflake's `CHANGES(INFORMATION => APPEND_ONLY) AT(TIMESTAMP=>watermark) END(TIMESTAMP=>batch_end)` primitive, applies entity discrimination in SQL, exports per-signal chunks via the Epic 4 OTLP foundation, and advances the watermark only on full success.

**This story implements:**

- `app/python/watermark.py` — shared `read_watermark` / `update_watermark` / `reset_watermark` helpers keyed on `SOURCE_NAME` in `_internal.export_watermarks` (reused by Story 5.2)
- `app/python/event_table_collector.py` — the SP handler with advance-on-success / hold-on-failure semantics
- `app/python/span_mapper.py` — updated SPAN_EVENT correlation contract keyed by `(trace_id, span_id)` for this collector
- Entity discrimination as the first pushdown filter after `RECORD_TYPE` (Rule ET-2)
- Per-signal `CHANGES` extraction using the §8.1–§8.4 typed projections
- `WATERMARK_EXPIRED` auto-reset recovery and `CHANGE_TRACKING` disabled diagnostics
- Integration with `span_mapper.py`, `log_mapper.py`, `metric_mapper.py` for OTel object construction (SPAN ↔ SPAN_EVENT correlation is in Python, not SQL)
- Integration with `otlp_export.py` export helpers and `pipeline_telemetry.py` for health + structured logs
- Memory-bounded export via direct `session.sql(query).to_pandas_batches()`
- Strict input validation for `source_fqn` and the include-list to prevent SQL injection
- SP registration in `_internal.collect_event_table(source_fqn, source_name)`

**Out of scope:**

- The scheduled serverless task DDL that invokes the collector — **Epic 6** (`6-4-event-table-export-provisioning`, default cadence 1 minute)
- The ACCOUNT_USAGE watermark + overlap + dedup collector — **Story 5.2**
- The Streamlit UI for picking sources and configuring `signal_types` per source — separate UX story
- Stale-watermark health alerting / auto-suspend — **Epic 7** (`7-4-stale-stream-recovery-and-auto-suspend`, to be reframed around stale-watermark recovery)
- AI Observability event-table row shapes — post-MVP

**Accepted MVP risks:**

- **At-least-once delivery on partial-success retry.** The collector's advance-on-success / hold-on-failure watermark is scoped to the entire run, not per-signal. If SPAN_EVENT and SPAN chunks export successfully but a subsequent LOG chunk hits a terminal OTLP failure, the watermark is held at its pre-run value; on the next invocation the same `[watermark, batch_end)` window is re-read and **all** signals re-exported — producing duplicates of the SPAN_EVENT and SPAN rows in Splunk. This keeps the pipeline's correctness property (no silent data loss) clean at the cost of at-least-once delivery. **Mitigation:** downstream Splunk searches needing exactly-once views can `dedup run_id, trace_id, span_id` (or the equivalent natural key per signal) at search time. A per-signal watermark design (with four independent watermark rows per source) is deferred post-MVP.
- **SPAN_EVENT in-memory index is unbounded.** The collector fully materialises `span_events_by_span_key` for the run before streaming SPAN chunks, and `event_table.max_span_events_per_run` is only a **warning threshold** — no mid-run flushing or partial-export alternate path is implemented. For pathological telemetry volumes in a single task cadence (e.g. a consumer app emitting millions of span events per minute), the SP heap could exceed the Snowflake Python sandbox limit and raise a memory error. **Mitigation:** operators can reduce the task cadence (shorten the `[watermark, batch_end)` window, which proportionally shrinks the buffered event count per run), lower `max_span_events_per_run` to surface the warning earlier, or raise the warehouse size. A bounded buffer with mid-run flushing is deferred post-MVP. This story therefore requires the explicit Task 9 benchmark/guardrail evidence before closeout so NFR19 is evaluated deliberately rather than assumed.

### Architecture Compliance

**Target runtime:** Python 3.13 for stored procedures. The collector runs as `EXECUTE AS OWNER` in `_internal` schema.

**Architectural rules that MUST be followed:**

1. **Rule ET-1 (CHANGES is the incremental primitive):** Use `CHANGES(INFORMATION => APPEND_ONLY) AT(TIMESTAMP=>watermark) END(TIMESTAMP=>batch_end)` against the source FQN. The `TIMESTAMP` column is not a unique row key and must not be used as a watermark anchor.
2. **Rule ET-2 (Entity discrimination is the first filter after `RECORD_TYPE`):** Configurable via `_internal.config`, default `('PROCEDURE','FUNCTION','QUERY','SQL','STATEMENT')`, `UPPER(...)` normalised.
3. **Rule ET-3 (No dedup):** CHANGES rows are unique by Snowflake change-tracking metadata. Do NOT add `QUALIFY ROW_NUMBER()`.
4. **Rule ET-4 (Extract and cast in SQL, not Python):** All `:"key"::TYPE` extraction server-side. Python consumes pre-typed columns.
5. **Rule ET-5 (One query per signal type):** SPAN_EVENT, SPAN, LOG, METRIC each run as their own `CHANGES` query in the same run.
6. **Rule ET-6 (`to_pandas_batches` only, directly on the `session.sql` DataFrame):** No `collect()`, no `to_pandas()`, no intermediate CTAS.
7. **Rule ET-7 (Advance-on-success / hold-on-failure):** Advance the watermark with a single `MERGE` only after every signal and every chunk has exported successfully. On any terminal export failure, return early with the watermark unchanged.
8. **Rule S-1 (No `SELECT *`):** Always explicit projection with type casts.
9. **Rule S-2 (Push all relational work to Snowflake):** No Python-side filtering, dedup, joins, or type casting on the export path.
10. **V12 (Transport-level retry only):** No custom retry in the collector. The OTel SDK's gRPC exporter handles retry internally; `ExportOutcome.terminal` is the final verdict.
11. **Flat `app/python/` directory:** No subdirectories. Both new files sit at `app/python/*.py`.
12. **Module import pattern:** `from __future__ import annotations`; sibling imports by plain name (`from otlp_export import init_exporters, export_spans, export_logs, export_metrics`, `from watermark import read_watermark, update_watermark, reset_watermark`); `TYPE_CHECKING` guard for the `Session` annotation.
13. **Collector session setup:** Set `session.sql_simplifier_enabled = True` before any collector queries for consistency with the project's Snowpark performance guidance.

### Watermark Lifecycle with 1-Minute Default Cadence

The Epic 6 scheduled task invokes this collector once per minute by default. The watermark lifecycle on that cadence:

| Run | Before run | `CHANGES` window | Rows | After run |
|---|---|---|---|---|
| First run (first ever — no row in `_internal.export_watermarks`) | no row | collector captures `batch_end = T₀`, seeds watermark to `T₀ − 60s` (default `initial_seed_buffer_seconds = 60`), then runs `AT(T₀ − 60s) END(T₀)` (one cadence wide) | N₁ | `WATERMARK_VALUE = T₀` |
| Run 2 (one minute later at T₀+60s) | `T₀` | `AT(T₀) END(T₀+60s)` | N₂ | `WATERMARK_VALUE = T₀+60s` |
| Run 3 (T₀+120s) | `T₀+60s` | `AT(T₀+60s) END(T₀+120s)` | N₃ | `WATERMARK_VALUE = T₀+120s` |
| Run 4, export fails | `T₀+120s` | `AT(T₀+120s) END(T₀+180s)` | any count | watermark **unchanged** at `T₀+120s` |
| Run 5 (T₀+240s), export succeeds | `T₀+120s` | `AT(T₀+120s) END(T₀+240s)` (two cadences wide — replay of run 4 plus run 5) | N₄+N₅ | `WATERMARK_VALUE = T₀+240s` |

**Key properties of this lifecycle:**

- The default `initial_seed_buffer_seconds = 60` aligns the first-run window with exactly one task cadence of history, so "activation starts collection" captures the immediately-preceding minute of telemetry rather than discarding it. Operators who prefer a zero-width first run (no backfill at all) can set the buffer to `0` before first run.
- On failure the window widens to cover the failed interval plus the current interval, and the OTel SDK's native retries execute again inside the single export call. The pipeline self-heals without human intervention as long as consecutive failures stay within the source's time-travel retention window.
- `initial_seed_buffer_seconds` and `watermark_reset_buffer_seconds` are both operator-tunable via `_internal.config`. An operator who wants to backfill, say, the last 10 minutes at activation can set `initial_seed_buffer_seconds = 600` before first run.
- Neither buffer may exceed the source's time-travel retention (default 1 day for Event Tables). Collector validation enforces an implicit upper bound by letting Snowflake raise a time-travel error; the `WATERMARK_EXPIRED` handler then self-resets.

### SPAN ↔ SPAN_EVENT Correlation

Per `telemetry_preparation_for_export.md` §13: SPAN and SPAN_EVENT are **not** joined in SQL. The collector runs them as two independent CHANGES queries (Rule ET-5) against the same `[watermark, batch_end]` window, then correlates during Python serialization by `(trace_id, span_id)` in memory. Because both queries use the same `AT/END(TIMESTAMP)` window, they see a consistent view.

For this story, update the mapper contract to use the true parent-span identity rather than `span_id` alone:

- `span_mapper.map_span_events(df: pd.DataFrame) -> dict[tuple[str, str], list[Any]]`
- `span_mapper.map_span_chunk(df, account_name, span_events_by_span_key=...)`

This avoids accidental cross-trace attachment when two traces reuse the same `span_id`.

**Ordering constraint:** Process `SPAN_EVENT` first and fully materialise the index, then stream SPAN chunks and export in-loop. LOG and METRIC then run independently.

### Extraction SQL Templates

Column aliases MUST match `app/python/telemetry_constants.py::COL_*` constants (verified in `span_mapper.py` via `_row_value(row, column_indexes, COL_*)`):

- **SPAN** (`telemetry_preparation_for_export.md` §8.1): `trace_id`, `span_id`, `span_name`, `span_kind`, `parent_span_id`, `status_code`, `status_message`, `end_time`, `start_time`, `db_user`, `exec_type`, `exec_name`, `query_id`, `warehouse_name`, `database_name`, `schema_name`, `sdk_language`, `RECORD_ATTRIBUTES`, `RESOURCE_ATTRIBUTES`
- **SPAN_EVENT** (§8.2): `trace_id`, `span_id`, `event_name`, `event_time`, `exception_message`, `exception_type`, `exception_stacktrace`, `exception_escaped`, `RECORD_ATTRIBUTES`, `RESOURCE_ATTRIBUTES`
- **LOG** (§8.3): `log_time`, `message`, `severity_text`, `severity_number`, `scope_name`, `log_iostream`, `code_filepath`, `code_function`, `code_lineno`, `code_namespace`, `thread_id`, `thread_name`, `exception_message`, `exception_type`, `exception_stacktrace`, `exception_escaped`, `RECORD_ATTRIBUTES`, `RESOURCE_ATTRIBUTES`
- **METRIC** (§8.4): `metric_time`, `metric_start_time`, `metric_name`, `metric_description`, `metric_unit`, `metric_type`, `value_type`, `aggregation_temporality`, `is_monotonic`, `metric_value`, `RECORD_ATTRIBUTES`, `RESOURCE_ATTRIBUTES`

### IMPORTS Chain for the Collector SP

```text
IMPORTS = (
    '/python/event_table_collector.py',
    '/python/watermark.py',
    '/python/otlp_export.py',
    '/python/export_result.py',
    '/python/pipeline_telemetry.py',
    '/python/span_mapper.py',
    '/python/log_mapper.py',
    '/python/metric_mapper.py',
    '/python/telemetry_constants.py',
    '/python/endpoint_parse.py',
    '/python/secret_reader.py'
)
```

### Config Key Conventions

Dotted-format keys in `_internal.config`:

| Key | Purpose | Default |
|---|---|---|
| `entity_discrimination.include_list` | Comma-separated uppercase tokens for the entity filter | `PROCEDURE,FUNCTION,QUERY,SQL,STATEMENT` |
| `otlp.endpoint` | OTLP gRPC endpoint `host:port` | (operator-configured in Epic 3) |
| `otlp.pem_secret_ref` | Presence indicator for the PEM cert | (operator-configured) |
| `event_table.max_span_events_per_run` | Warning threshold for buffered SPAN_EVENT volume in a single run | `50000` |
| `event_table.initial_seed_buffer_seconds` | Seconds behind the run's captured `batch_end` anchor to seed the watermark on first run (no row yet in `_internal.export_watermarks`) | `60` |
| `event_table.watermark_reset_buffer_seconds` | Seconds behind `CURRENT_TIMESTAMP()` for watermark reset after `WATERMARK_EXPIRED` | `60` |

### Watermark Table Shape

`_internal.export_watermarks` already exists in `setup.sql`:

```sql
CREATE TABLE IF NOT EXISTS _internal.export_watermarks (
    SOURCE_NAME     VARCHAR(256) NOT NULL,
    WATERMARK_VALUE TIMESTAMP_LTZ NOT NULL,
    UPDATED_AT      TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_export_watermarks PRIMARY KEY (SOURCE_NAME)
);
```

No DDL change required for this story. Both Event Table sources and ACCOUNT_USAGE sources (Story 5.2) share this table.

### Pipeline Health Recording

Use the existing `pipeline_telemetry.py` helpers as-is:

```python
record_export_success(session, "event_table_collector", source_name, signal_type, batch_size, run_id)
record_batch_failure(session, "event_table_collector", source_name, outcome, run_id)
log_export_success(context, outcome)
log_terminal_failure(context, outcome)
```

Additional health rows emitted by this collector (new metric names):

| `METRIC_NAME` | When | `METRIC_VALUE` |
|---|---|---|
| `watermark_reset` | On time-travel recovery (paired with the `WATERMARK_EXPIRED` log-event code) | `1` |
| `source_change_tracking_disabled` | On CHANGES error indicating `CHANGE_TRACKING = FALSE` | `1` |
| `invalid_source_parameter` | On `source_fqn` / include-list validation failure | `1` |
| `run_duration_ms` | At end of every run | wall-clock ms |

These use inline parameterised `INSERT` statements matching the shape of `pipeline_telemetry._INSERT_SQL`. Do not modify `pipeline_telemetry.py` in this story — keep its existing API surface stable.

### Collector Skeleton (pseudocode)

```python
def collect_event_table(session, source_fqn: str, source_name: str) -> str:
    start = time.perf_counter()
    session.sql_simplifier_enabled = True
    _validate_source_fqn(source_fqn)

    cfg = _load_config(session)
    include_list = _resolve_include_list(cfg)
    init_exporters(cfg["otlp.endpoint"], get_pem_secret(session))

    run_id = str(uuid.uuid4())
    ctx = ExportContext("event_table_collector", source_name, run_id)
    account_name = session.sql("SELECT CURRENT_ACCOUNT()").collect()[0][0]

    batch_end = session.sql("SELECT CURRENT_TIMESTAMP()").collect()[0][0]
    watermark = read_watermark(
        session, source_name,
        cfg["event_table.initial_seed_buffer_seconds"],
        batch_end,
    )

    try:
        # 1. SPAN_EVENT — materialise index for correlation
        span_events_by_span_key = _build_span_event_index(
            session, source_fqn, watermark, batch_end, include_list, cfg, ctx,
        )

        # 2. SPAN — stream + export in-loop, with event attachment
        if _stream_and_export_spans(
            session, source_fqn, watermark, batch_end, include_list,
            account_name, span_events_by_span_key, ctx,
        ) is EXPORT_FAILED:
            return _failure_summary(run_id, source_name, watermark, batch_end, start)

        # 3. LOG — stream + export
        if _stream_and_export_logs(
            session, source_fqn, watermark, batch_end, include_list, ctx,
        ) is EXPORT_FAILED:
            return _failure_summary(...)

        # 4. METRIC — stream + export
        if _stream_and_export_metrics(
            session, source_fqn, watermark, batch_end, include_list, ctx,
        ) is EXPORT_FAILED:
            return _failure_summary(...)

    except _TimeTravelExpired as e:
        reset_watermark(
            session, source_name,
            cfg["event_table.watermark_reset_buffer_seconds"],
        )
        _record_health_event(session, run_id, source_name, "watermark_reset", 1, {"error": str(e)})
        return _watermark_reset_summary(...)

    except _ChangeTrackingDisabled as e:
        _record_health_event(
            session, run_id, source_name, "source_change_tracking_disabled", 1, {"error": str(e)},
        )
        return _ct_disabled_summary(...)

    update_watermark(session, source_name, batch_end)
    duration_ms = int((time.perf_counter() - start) * 1000)
    _record_health_event(session, run_id, source_name, "run_duration_ms", duration_ms, {})
    return _success_summary(...)
```

### Implementation Patterns (from Epic 4 modules consumed here)

1. **Module imports:** All `app/python/*.py` files use `from __future__ import annotations` and import siblings by plain name.
2. **OTel SDK version:** The Snowflake runtime pins `opentelemetry-sdk==1.38.0`. The mappers were written against this version.
3. **`snowflake.yml`:** No wildcard for `app/python/`. Every new file (including `watermark.py` and `event_table_collector.py`) must be individually listed in the artifacts block.
4. **Exporter initialisation:** `otlp_export.py` initialises exporters under an internal lock. The collector is single-threaded but must still call `init_exporters(...)` once — the locking is handled inside.
5. **`ExportOutcome` control flow:** Use explicit `outcome.success` / `outcome.terminal` for clarity.
6. **Pipeline telemetry separation:** `otlp_export.py` returns structured outcomes only. `pipeline_telemetry.py` owns caller-context side effects. The collector wires these together.
7. **Parameterised health INSERTs:** All INSERTs into `_metrics.pipeline_health` use `session.sql(query, params=[...])` — no f-string value interpolation.
8. **Duration fields:** The export helpers already populate `outcome.duration_ms` for the per-export call. The collector measures its own overall `run_duration_ms` separately via `time.perf_counter()`.
9. **PEM secret:** `secret_reader.get_pem_secret(session)` reads via `_snowflake.get_generic_secret_string('otlp_pem_cert')`. The SP registration MUST include `SECRETS = ('otlp_pem_cert' = _internal.otlp_pem_secret)`.

### Testing Strategy

**Tier 1: Unit tests (root venv, no Snowflake connection)**

```bash
PYTHONPATH=app/python .venv/bin/python -m pytest tests/test_event_table_collector.py tests/test_watermark.py -v
```

Mock `Session.sql()`, `.collect()`, and `.to_pandas_batches()`. Verify the exact SQL shape for each CHANGES query, the ordering of signals, the watermark lifecycle, error recovery paths, and validation.

**Tier 2: Integration tests (dev Snowflake account `LFB71918`)**

```bash
PRIVATE_KEY_PASSPHRASE=qwerty123 PYTHONPATH=app/python .venv/bin/python -m pytest tests/integration/test_event_table_collector.py -v -m integration
```

Uses Epic 4's test-signal generators, the live dev app, and the OTLP collector + Splunk realm REST API. See `dev_environment.mdc` for required env vars and the OTLP collector journal verification pattern.

**Tier 3: Benchmark / guardrail verification (NFR19 evidence)**

Run the Task 9 representative high-volume Event Table benchmark and capture whether the collector completes a single scheduled-run workload of up to `1,000,000` representative rows without timeout or unrecoverable memory failure. If the collector does not meet that bar with the current unbounded SPAN_EVENT buffer, record the validated operating envelope and required MVP guardrails explicitly before marking the story done.

**Linting**

```bash
.venv/bin/ruff check app/python/event_table_collector.py app/python/watermark.py tests/test_event_table_collector.py tests/test_watermark.py
```

### Project Structure Notes

**New files:**

| Path | Description |
|---|---|
| `app/python/watermark.py` | `read_watermark`, `update_watermark`, `reset_watermark` — shared helpers for `_internal.export_watermarks`, reused by Story 5.2 |
| `app/python/event_table_collector.py` | Event Table collector SP handler — CHANGES reader, entity discrimination, signal ordering, export loop, health + log recording, `WATERMARK_EXPIRED` and `source_change_tracking_disabled` recovery |
| `tests/test_watermark.py` | Unit tests for watermark helpers |
| `tests/test_event_table_collector.py` | Unit tests for the collector |
| `tests/integration/test_event_table_collector.py` | Integration harness against dev Snowflake + OTLP collector + Splunk |

**Modified files:**

| Path | Change |
|---|---|
| `app/python/span_mapper.py` | Update SPAN_EVENT correlation to use composite `(trace_id, span_id)` keys and `span_events_by_span_key` |
| `tests/test_span_mapper.py` | Update mapper unit tests to assert composite-key SPAN_EVENT correlation |
| `app/setup.sql` | Add `CREATE OR REPLACE PROCEDURE _internal.collect_event_table(source_fqn VARCHAR, source_name VARCHAR)` registration |
| `snowflake.yml` | Add artifact entries for `event_table_collector.py` and `watermark.py` |

**Not modified (consumed as-is from Epic 4):**

- `app/python/otlp_export.py`
- `app/python/export_result.py`
- `app/python/pipeline_telemetry.py`
- `app/python/log_mapper.py`
- `app/python/metric_mapper.py`
- `app/python/telemetry_constants.py`
- `app/python/secret_reader.py`
- `app/python/endpoint_parse.py`
- `app/manifest.yml` — no new privileges
- `scripts/shared_content.sql` — no new grants
- `app/environment.yml` — no new dependencies

### References

- [Source: `_bmad-output/planning-artifacts/telemetry_preparation_for_export.md` — §1 Canonical Sources, §2 Event Table Schema, §3 Per-Signal RECORD Shape, §5 RESOURCE_ATTRIBUTES, §7 Pushdown Rules (ET-1 through ET-7, S-1, S-2), §8 Per-Signal Extraction Templates, §9 SQL vs Snowpark Decision, §10 Runtime Compatibility, §13 Access Patterns and Correlation, §14 Behavioral Notes, §15 Implementation Checklist]
- [Source: `_bmad-output/planning-artifacts/event_table_entity_discrimination_strategy.md` — §2 Primary Discriminator, §5 MVP Positive Include-List Strategy, §7 Edge Cases, §10 Decision Summary]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — Dual-pipeline architecture, Entity Discrimination Filter, OTLP Exporter Topology, Naming Patterns, Python Module Organization, Pipeline Health Metric Names]
- [Source: `_bmad-output/planning-artifacts/prd.md` — FR19 (Event Table incremental collection), FR20 (entity discrimination), NFR1 (serverless tasks), NFR19 (to_pandas_batches)]
- [Source: `_bmad-output/implementation-artifacts/epic-4-retro-2026-04-13.md` — Epic 4 completion, proven OTLP foundation, `ExportOutcome` contract, `pipeline_telemetry` helpers]
- [Source: `_bmad-output/implementation-artifacts/4-3-deterministic-otlp-retry-and-terminal-failure-handling.md` — `ExportOutcome` design, pipeline-health INSERT pattern, module import pattern, flat directory convention]
- [Source: `app/python/span_mapper.py` — `map_span_chunk(df, account_name, span_events_by_span_key=...)`, `map_span_events(df)`]
- [Source: `app/python/log_mapper.py` — existing log mapper for LOG → OTel `LogData`]
- [Source: `app/python/metric_mapper.py` — existing metric mapper for METRIC → OTel `MetricsData`]
- [Source: `app/python/otlp_export.py` — `init_exporters`, `export_spans`, `export_logs`, `export_metrics` returning `ExportOutcome`]
- [Source: `app/python/pipeline_telemetry.py` — `record_batch_failure`, `record_export_success`, `log_terminal_failure`, `log_export_success`, `ExportContext`]
- [Source: `app/python/export_result.py` — `ExportOutcome`, `UPSTREAM_RETRYABLE_GRPC_CODES`, sanitisation helpers]
- [Source: `app/python/telemetry_constants.py` — `COL_*` column name constants]
- [Source: `app/python/secret_reader.py` — `get_pem_secret(session)` for `otlp_pem_cert`]
- [Source: `app/setup.sql` — SP registration patterns, `_internal.export_watermarks` DDL, `_metrics.pipeline_health` DDL, `otlp_egress_eai` EAI, `otlp_pem_secret`]
- [Source: Snowflake Docs — [CHANGES Clause](https://docs.snowflake.com/en/sql-reference/constructs/changes), [Event Table Operations](https://docs.snowflake.com/en/developer-guide/logging-tracing/event-table-operations), [ALTER TABLE for Event Tables](https://docs.snowflake.com/en/sql-reference/sql/alter-table-event-table), [`DataFrame.to_pandas_batches()`](https://docs.snowflake.com/en/developer-guide/snowpark/reference/python/latest/snowpark/api/snowflake.snowpark.DataFrame.to_pandas_batches)]

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List
