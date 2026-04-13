# Story 4.3: Deterministic OTLP Retry and Terminal Failure Handling

Status: done

## Story

As an operator (Sam),
I want retryable OTLP errors to be retried automatically and non-retryable errors to be recorded as terminal batch failures without endless retry,
so that transient failures recover while permanent failures remain visible and bounded.

### Definition — `terminal`

In this story, `terminal` means a **final batch-level export outcome for the current invocation**: the export layer has no more recovery work to do for that batch. After a terminal outcome, the caller should record the failure and advance instead of retrying the same batch again in an endless loop.

`terminal` does **not** mean app shutdown, task termination, whole-pipeline failure, or app-level health-state change.

## Acceptance Criteria

1. **Given** the OTLP export foundation is sending a batch
   **When** a transport or protocol error occurs whose gRPC status is in the upstream `opentelemetry-python` OTLP gRPC exporter's retry set (`CANCELLED`, `DEADLINE_EXCEEDED`, `RESOURCE_EXHAUSTED`, `ABORTED`, `OUT_OF_RANGE`, `UNAVAILABLE`, `DATA_LOSS`)
   **Then** the OTel SDK's built-in gRPC retry policy retries automatically within the configured export timeout window
   **And** the wrapper adds **no** custom retry loop, backoff policy, or alternate transport logic
   **And** the export function returns a structured `ExportOutcome` that includes the final success/failure status, a sanitized error message (no secrets), `duration_ms`, and `retryable` information when the underlying gRPC status is directly observable
   **And** raw upstream exporter or gRPC code names are used as-is in `error_code` when available (`FAILURE` or the observed `grpc.StatusCode.name`)
   **And** existing callers that check `if export_spans(batch):` continue to work because `ExportOutcome.__bool__` returns `True` on success
   **And** the existing diagnostic smoke-harness JSON contract keeps `span_export`, `log_export`, and `metric_export` as boolean keys for backward compatibility

2. **Given** the export function returns a failure after the upstream exporter has applied its own retry handling
   **When** the public exporter surface returns `FAILURE` without surfacing the underlying gRPC status code
   **Then** the `ExportOutcome` includes `success=False`, `terminal=True`, `retryable=None`, `error_code='FAILURE'`, and a sanitized `error_message` explaining that the public exporter returned `FAILURE` without exposing the underlying status
   **And** if a gRPC status code is directly observable through a surfaced `grpc.RpcError`, `retryable` mirrors the upstream exporter's exact retry set and `error_code` is the raw observed `grpc.StatusCode.name`
   **And** if no upstream code is available because the failure happened before or outside the exporter surface, `error_code` is set to `type(exc).__name__` (e.g. `RuntimeError`) for queryability rather than `None` — this is an intentional improvement over the original spec, which said `None`, agreed during implementation after live failure testing showed that a populated `error_code` is essential for structured event table queries
   **And** the caller receives an explicit terminal batch-failure result so the surrounding pipeline can advance or record the failure without entering an endless resend loop

3. **Given** a successful or terminal `ExportOutcome` and caller-owned export context (`pipeline_name`, `source_name`, `run_id`)
   **When** the caller invokes the OTLP operational logging helper
   **Then** the helper emits structured Python logging events with fields `pipeline`, `source`, `run_id`, `signal_type`, `error_code`, `error_message`, `batch_size`, `duration_ms`, and `retryable`
   **And** those logs are emitted to the consumer event table using standard Snowflake Native App logging behavior
   **And** provider-side sharing of those logs is enabled by the manifest `telemetry_event_definitions` block rather than by app-level health-status APIs
   **And** the low-level `otlp_export.py` functions do **not** duplicate this caller-context logging internally

4. **Given** a terminal batch-failure `ExportOutcome` is returned
   **When** the caller invokes the pipeline health recording helper
   **Then** a terminal batch failure row is written to `_metrics.pipeline_health` with `METRIC_NAME = 'rows_failed'`, the affected `PIPELINE_NAME` and `SOURCE_NAME`, and `METADATA` containing `error_code`, `error_message`, `signal_type`, `retryable`, `batch_size`, and `duration_ms`
   **And** the recording completes within the NFR24 observability window (< 1 minute after the error occurs)
   **And** no secret or credential values (endpoint URLs with auth tokens, PEM material, passwords) appear in the recorded failure metadata or log output

5. **Given** the export functions are called with an empty batch or `None`
   **When** the export function returns
   **Then** it returns a success `ExportOutcome` immediately (no network call, no error) as a no-op fast path
   **And** `batch_size = 0`

6. **Given** a batch export succeeds on the first attempt or after internal SDK retry
   **When** the export returns
   **Then** the `ExportOutcome` has `success=True`, `terminal=False`, `error_code=None`, `retryable=None`, and evaluates as truthy
   **And** `batch_size` is computed consistently: `len(batch)` for span/log sequences and total data-point count for `MetricsData`

7. **Given** `init_exporters()` has not been called before an export function is invoked
   **When** the export returns
   **Then** the `ExportOutcome` has `success=False`, `terminal=True`, `error_code=None`, a sanitized explanatory message, and evaluates as falsy

8. **Given** the health recording helper receives a Snowpark session and an `ExportOutcome`
   **When** it writes to `_metrics.pipeline_health`
   **Then** it uses parameterized SQL (bind variables) for the INSERT to prevent injection
   **And** fails gracefully (logs warning, does not raise) if the INSERT itself errors — health recording must not crash the pipeline

9. **Given** the app manifest is updated for OTLP export operational logging
   **When** this story is implemented
   **Then** `app/manifest.yml` `configuration` block includes a `telemetry_event_definitions` list with `ERRORS_AND_WARNINGS` set to `MANDATORY` and `DEBUG_LOGS` set to `OPTIONAL` — these control what the **provider** can see when the consumer enables event sharing
   **And** the existing `log_level: INFO`, `trace_level: ALWAYS`, `metric_level: ALL` remain unchanged — these control what the app emits to the **consumer's** event table
   **And** the story explicitly scopes this to OTLP export operational logs and event sharing
   **And** the story does **not** add app-level `SYSTEM$REPORT_HEALTH_STATUS(...)` calls or treat per-batch OTLP failures as whole-app health state changes

## Tasks / Subtasks

- [x] Task 1: Create `app/python/export_result.py` — structured export outcome, upstream status classification, and shared batch-size helpers (AC: 1, 2, 5, 6, 7)
  - [x] 1.1 Define `ExportOutcome` dataclass with fields: `success: bool`, `terminal: bool`, `error_code: str | None`, `error_message: str | None`, `signal_type: str`, `batch_size: int`, `retryable: bool | None`, `duration_ms: int`
  - [x] 1.2 Implement `ExportOutcome.__bool__()` returning `self.success` for backward-compatible truthiness, plus `to_dict()` for JSON serialization
  - [x] 1.3 Define `UPSTREAM_RETRYABLE_GRPC_CODES` so it mirrors the pinned upstream `opentelemetry-python` OTLP gRPC exporter exactly: `CANCELLED`, `DEADLINE_EXCEEDED`, `RESOURCE_EXHAUSTED`, `ABORTED`, `OUT_OF_RANGE`, `UNAVAILABLE`, `DATA_LOSS`
  - [x] 1.4 Implement direct-status classification for surfaced `grpc.StatusCode` / `grpc.RpcError` values so `retryable` mirrors `UPSTREAM_RETRYABLE_GRPC_CODES` exactly and `error_code` is the raw observed `grpc.StatusCode.name`
  - [x] 1.5 Implement `classify_export_failure_without_status(signal_type, batch_size, duration_ms) -> ExportOutcome` for the main `4.1` failure mode where `exporter.export()` returns `FAILURE` with no surfaced `grpc.RpcError`; set `retryable=None`, `terminal=True`, `error_code='FAILURE'`, and an explanatory sanitized message rather than inventing false precision
  - [x] 1.6 Implement `classify_unexpected_exception(exc: Exception, ...) -> ExportOutcome` for non-gRPC exceptions that surface outside the public exporter result path; set `error_code=type(exc).__name__` for queryability (deviation from original `None` — agreed during live failure testing), `retryable=None`, `terminal=True`, and use a sanitized explanatory message
  - [x] 1.7 Implement `_sanitize_error_message(msg: str) -> str` that strips potential secret material (URLs with credentials, PEM blocks, auth tokens) before recording
  - [x] 1.8 Implement shared batch-size helpers so all three exporters and diagnostics count consistently: `len(batch)` for span/log sequences, total data-point count for `MetricsData`, and `0` for empty or `None`
  - [x] 1.9 Define factory helpers: `success_result(signal_type, batch_size, duration_ms)`, `noop_result(signal_type)`, `not_initialized(signal_type)`, and any failure helper needed for the public-exporter bare-`FAILURE` path

- [x] Task 2: Modify `app/python/otlp_export.py` — change export functions to return `ExportOutcome` while preserving the `4.1` foundation contract (AC: 1, 2, 5, 6, 7)
  - [x] 2.1 Change `export_spans()` return type from `bool` to `ExportOutcome`; return `ExportOutcome.noop_result("spans")` for empty batches; compute `batch_size` via the shared helper; measure `duration_ms`; evaluate the export result enum first; map bare `FAILURE` via `classify_export_failure_without_status(...)`; handle surfaced `grpc.RpcError` only as a secondary path; preserve the existing `_state_cond` concurrency model from Story 4.1
  - [x] 2.2 Change `export_metrics()` return type from `bool` to `ExportOutcome` with the same classification pattern, using the shared helper that counts total metric data points rather than wrapper objects
  - [x] 2.3 Change `export_logs()` return type from `bool` to `ExportOutcome` with the same classification pattern, using the shared sequence batch-size helper and preserving the OTel 1.38/1.39 `LogExportResult` name comparison shim
  - [x] 2.4 Return structured outcomes only; do **not** emit caller-context OTLP operational logs from `otlp_export.py`. Keep module logging limited to low-level internal diagnostics because `pipeline`, `source`, and `run_id` belong to callers
  - [x] 2.5 Preserve boolean truthiness for direct Python callers (`if export_spans(batch):`)
  - [x] 2.6 Preserve the existing `4.1` smoke-harness contract by keeping `span_export`, `log_export`, and `metric_export` as booleans in returned JSON while adding explicit `span_export_outcome`, `log_export_outcome`, and `metric_export_outcome` serialized dicts for detailed diagnostics

- [x] Task 3: Create `app/python/pipeline_telemetry.py` — OTLP operational logging and health recording helpers with DRY/SOLID structure (AC: 3, 4, 8)
  - [x] 3.1 Define a typed caller-context helper input (for example an `ExportContext` dataclass) carrying `pipeline_name`, `source_name`, and `run_id`
  - [x] 3.2 Implement a shared private log-payload builder (for example `_build_log_extra(context, outcome)`) plus a shared private emitter helper so success and failure logging reuse the same field-shaping code
  - [x] 3.3 Implement `log_terminal_failure(...)` and `log_export_success(...)` as thin wrappers over the shared helper, using `logging.error()` / `logging.info()` with the mandatory operational log fields (`pipeline`, `source`, `run_id`, `signal_type`, `error_code`, `error_message`, `batch_size`, `duration_ms`, `retryable`)
  - [x] 3.4 Implement a shared private SQL helper for `_metrics.pipeline_health` INSERTs so success and failure metric writes do not duplicate bind/JSON assembly logic
  - [x] 3.5 Implement `record_batch_failure(session, pipeline_name: str, source_name: str, outcome: ExportOutcome, run_id: str) -> None` — INSERT into `_metrics.pipeline_health` with `METRIC_NAME='rows_failed'`, `METRIC_VALUE=outcome.batch_size`, `METADATA` as JSON containing `error_code`, `error_message`, `signal_type`, `retryable`, `batch_size`, and `duration_ms`
  - [x] 3.6 Implement `record_export_success(session, pipeline_name: str, source_name: str, signal_type: str, batch_size: int, run_id: str) -> None` — INSERT with `METRIC_NAME='rows_exported'` and `METRIC_VALUE=batch_size`; use parameterized SQL (`session.sql(query, params=[...])`) and log warning without raising if the INSERT fails

- [x] Task 4: Align manifest, setup wiring, and staged artifacts with the `4.1` foundation (AC: all, 9)
  - [x] 4.1 Update `app/manifest.yml` to add `telemetry_event_definitions` inside the existing `configuration:` block (after `metric_level: ALL`). Use the exact Snowflake syntax: `- type: ERRORS_AND_WARNINGS` / `sharing: MANDATORY` and `- type: DEBUG_LOGS` / `sharing: OPTIONAL`. Do NOT create a separate `configuration:` key — nest under the existing one.
  - [x] 4.2 Add `src: app/python/export_result.py` → `dest: python/export_result.py` to `snowflake.yml` artifacts
  - [x] 4.3 Add `src: app/python/pipeline_telemetry.py` → `dest: python/pipeline_telemetry.py` to `snowflake.yml` artifacts
  - [x] 4.4 Update **both** diagnostic OTLP runtime stored procedure `IMPORTS` blocks in `app/setup.sql` to include `'/python/export_result.py'` and `'/python/pipeline_telemetry.py'` because `otlp_export.py` and `otlp_export_smoke_test.py` import them directly in the Snowflake runtime
  - [x] 4.5 Add `telemetry:` section to the dev app entity in `snowflake.yml` with `share_mandatory_events: true` and `optional_shared_events: [DEBUG_LOGS]` for dev-mode event sharing (`MANAGE EVENT SHARING` global privilege is confirmed available on the dev account `LFB71918` as of 2026-04-09)

- [x] Task 5: Write unit tests (AC: 1–9)
  - [x] 5.1 `tests/test_export_result.py`: Test that `UPSTREAM_RETRYABLE_GRPC_CODES` matches the pinned upstream exporter exactly: `CANCELLED`, `DEADLINE_EXCEEDED`, `RESOURCE_EXHAUSTED`, `ABORTED`, `OUT_OF_RANGE`, `UNAVAILABLE`, `DATA_LOSS`
  - [x] 5.2 `tests/test_export_result.py`: Test direct-status classification for surfaced gRPC codes — `UNAVAILABLE` → retryable with `error_code='UNAVAILABLE'`; `PERMISSION_DENIED` → non-retryable with `error_code='PERMISSION_DENIED'`; `OUT_OF_RANGE` → retryable; `DATA_LOSS` → retryable; `INVALID_ARGUMENT` → non-retryable
  - [x] 5.3 `tests/test_export_result.py`: Test the main public-exporter failure path — bare `FAILURE` with no surfaced status yields `terminal=True`, `retryable=None`, and `error_code='FAILURE'`
  - [x] 5.4 `tests/test_export_result.py`: Test unexpected exception handling — non-gRPC exceptions set `error_code=type(exc).__name__` (deviation from original `None` spec — see AC-2), preserve sanitized explanatory messages, and never invent app-defined OTLP alias codes
  - [x] 5.5 `tests/test_export_result.py`: Test `ExportOutcome.__bool__` — success is truthy, all failure variants are falsy
  - [x] 5.6 `tests/test_export_result.py`: Test `_sanitize_error_message` — strips PEM blocks, URLs with credentials, auth headers, and long error details while preserving the useful error type and summary
  - [x] 5.7 `tests/test_export_result.py`: Test factory helpers, `to_dict()`, and batch-size helpers — `success_result`, `noop_result`, `not_initialized`, bare-`FAILURE` outcomes, sequence sizing, and metrics data-point sizing return correctly populated instances including `duration_ms`
  - [x] 5.8 `tests/test_pipeline_telemetry.py`: Test `record_batch_failure` — verify correct SQL params, verify METADATA JSON structure (including nullable `retryable` and `duration_ms`), verify no secret leakage in recorded data
  - [x] 5.9 `tests/test_pipeline_telemetry.py`: Test `record_batch_failure` graceful failure — if `session.sql()` raises, function logs warning but does not raise
  - [x] 5.10 `tests/test_pipeline_telemetry.py`: Test `record_export_success` — correct metric name and value
  - [x] 5.11 `tests/test_pipeline_telemetry.py`: Test structured log output from `log_terminal_failure` and `log_export_success` — verify all mandatory fields present including `duration_ms`, `retryable`, and raw upstream `error_code` strings when available
  - [x] 5.12 `tests/test_otlp_export.py`: Update existing export tests to handle `ExportOutcome` return type — verify direct truthiness still works, verify bare `FAILURE` classification through the normal export path, verify the surfaced-`grpc.RpcError` fallback path, and verify shared batch-size rules are applied consistently
  - [x] 5.13 `tests/test_otlp_export.py`: Test empty batch returns noop result with `batch_size=0`; test uninitialized exporter returns a terminal result with `error_code=None`
  - [x] 5.14 `tests/test_otlp_export_smoke_test.py`: Verify the smoke harness preserves boolean keys (`span_export`, `log_export`, `metric_export`) and also emits serialized `*_outcome` payloads

- [x] Task 6: Update integration and diagnostic harnesses for `ExportOutcome` without breaking `4.1` callers (AC: 1, 2)
  - [x] 6.1 Update `app/python/otlp_export_smoke_test.py` to keep `result["span_export"]`, `result["log_export"]`, and `result["metric_export"]` as booleans while adding `result["span_export_outcome"]`, `result["log_export_outcome"]`, and `result["metric_export_outcome"]` using `ExportOutcome.to_dict()`
  - [x] 6.2 Update `tests/test_otlp_export_smoke_test.py` to continue asserting boolean smoke keys while also validating the new structured outcome payloads
  - [x] 6.3 Update `tests/integration/test_mapper_real_data.py` and `tests/integration/conftest.py` so direct Python export calls assert `result.success` or `bool(result)` rather than `is True`

## Dev Notes

### Story Boundary

This story adds **deterministic terminal export handling, structured export results, caller-side OTLP operational logging, manifest-backed OTLP operational event sharing, and pipeline health recording** to the OTLP export foundation established in Story 4.1. It creates two new pure-Python modules (`export_result.py`, `pipeline_telemetry.py`), updates `otlp_export.py` to return structured results instead of plain booleans, and aligns the manifest with Native App event-definition support for OTLP export operational logs.

**This story does NOT implement:**
- Application-level retry loops with custom backoff — the MVP relies on OTel SDK built-in gRPC retry per V12
- 60-second outage durability (`NFR18`) — that is explicitly post-MVP and out of scope for this story
- The collector procedures that call the export functions — Epic 5
- Stream recovery, auto-suspend, or task-level retry (`TASK_AUTO_RETRY_ATTEMPTS`) — Epic 7
- Dead-letter queue or zero-copy failure tracking — post-MVP
- End-to-end pipeline orchestration — Epic 5 + Epic 6
- App-level `SYSTEM$REPORT_HEALTH_STATUS(...)` reporting — this story is about OTLP export events and per-batch pipeline health, not whole-app health state transitions

**This story DOES implement:**
- Exact alignment with the upstream OTLP Python exporter's retry set for any directly observed gRPC status
- Raw upstream exporter or gRPC code usage (`FAILURE` or `grpc.StatusCode.name`) instead of app-defined OTLP alias codes
- Deterministic handling of the main `4.1` public-exporter failure mode (`exporter.export()` returns `FAILURE` with no surfaced status)
- Structured `ExportOutcome` that the Epic 5 collectors will consume
- Pipeline health recording helpers that Epic 5 collectors will call
- Structured OTLP operational logging helpers that Epic 5 collectors will call, using standard Snowflake Native App logging behavior
- Manifest `telemetry_event_definitions` configuration for provider-side event sharing
- Secret-safe error message sanitization

### Architecture Compliance

**Target Snowflake runtime:** Python 3.13 for stored procedures. Uses `opentelemetry-sdk==1.38.0` and `grpcio` from the Snowflake Anaconda channel. New modules (`export_result.py`, `pipeline_telemetry.py`) are testable from the root venv (Python 3.13).

**Key decisions that MUST be followed:**

1. **V12 — Transport-level retry only (MVP):** The OTel SDK's built-in gRPC retry handles transient failures within the configured `_EXPORT_TIMEOUT_S = 10` window. Story 4.3 does NOT add application-level retry loops with `httpx`, `tenacity`, queueing, or replay logic. It wraps the SDK's terminal export result and surfaces it to the caller.

2. **Use upstream status names only for OTLP export:** The public exporter result surface is `SUCCESS` / `FAILURE`. If a `grpc.RpcError` is surfaced to our wrapper, store `error.code().name` verbatim (for example `UNAVAILABLE`, `PERMISSION_DENIED`, `DATA_LOSS`). Do **not** invent OTLP alias codes for export outcomes.

3. **NFR24 is in scope; NFR18 is not:** This story must satisfy deterministic observable handling (`NFR24`) by recording terminal export failures within 1 minute. `NFR18` 60-second outage durability is post-MVP and is intentionally **not** promised by this story or by the current MVP design.

4. **`ExportOutcome` backward compatibility with Story 4.1:** The return type change from `bool` to `ExportOutcome` must NOT break any existing caller. `ExportOutcome.__bool__` returns `self.success`, so `if export_spans(batch):` continues to work. In addition, the existing `4.1` smoke-harness JSON keys (`span_export`, `log_export`, `metric_export`) must remain booleans, with detailed structured outcomes added alongside them rather than replacing them.

5. **No secret leakage in logs or health records:** Error messages from gRPC or TLS exceptions may contain endpoint URLs, certificate details, or authentication tokens. The `_sanitize_error_message()` function must strip these before recording. Never log the PEM material, the full endpoint URL with credentials, or Snowflake secret values.

6. **DRY/SOLID logging and health design:** `otlp_export.py` is the low-level export wrapper and should only return `ExportOutcome`. `pipeline_telemetry.py` owns caller-context side effects such as structured OTLP operational logs and `_metrics.pipeline_health` writes because only callers know `pipeline`, `source`, and `run_id`. Use shared private helpers for log payload assembly and metric INSERT assembly so success and failure paths do not duplicate code.

7. **`pipeline_telemetry.py` uses Snowpark session for SQL:** Unlike the mappers (pure functions), the pipeline telemetry module receives a Snowpark `Session` parameter for database writes. It is NOT a pure function — it performs SQL INSERTs. This is intentional: health recording requires database access.

8. **Structured logging, event tables, and event definitions are separate layers:** Use Python `logging.error()` / `logging.info()` with `extra={}` dict containing the mandatory fields: `pipeline`, `source`, `run_id`, `signal_type`, `error_code`, `error_message`, `batch_size`, `duration_ms`, `retryable`. The existing `log_level: INFO` / `trace_level: ALWAYS` in `manifest.yml` `configuration` control what the app emits to the **consumer** event table — those are already set and this story does not change them. `configuration.telemetry_event_definitions` is an additive block that controls what may be shared back to the **provider** when event sharing is enabled by the consumer. This story adds OTLP-operational event definitions in `manifest.yml` and does **not** call `SYSTEM$REPORT_HEALTH_STATUS(...)`.

   **Exact manifest YAML syntax** (from [Snowflake docs](https://docs.snowflake.com/en/developer-guide/native-apps/event-definition)):
   ```yaml
   configuration:
     log_level: INFO
     trace_level: ALWAYS
     metric_level: ALL
     telemetry_event_definitions:
       - type: ERRORS_AND_WARNINGS
         sharing: MANDATORY
       - type: DEBUG_LOGS
         sharing: OPTIONAL
   ```

   The `type` values are Snowflake-defined constants with internal names: `SNOWFLAKE$ERRORS_AND_WARNINGS` (filters `RECORD_TYPE = 'LOG' AND RECORD:severity_text in ('FATAL', 'ERROR', 'WARN')`) and `SNOWFLAKE$DEBUG_LOGS` (filters `RECORD_TYPE = 'LOG' AND RECORD:severity_text in ('DEBUG', 'TRACE')`). In the manifest YAML, use the short names `ERRORS_AND_WARNINGS` and `DEBUG_LOGS`. The `sharing` value is either `MANDATORY` (consumer cannot disable) or `OPTIONAL` (consumer can toggle).

   **Dev-mode telemetry sharing in `snowflake.yml`:** For `snow app run` dev mode, the dev application entity should also enable event sharing so the dev account acts as both consumer and provider:
   ```yaml
   splunk_observability_dev_app:
     type: application
     from:
       target: splunk_observability_dev_pkg
     debug: false
     telemetry:
       share_mandatory_events: true
       optional_shared_events:
         - DEBUG_LOGS
   ```
   `MANAGE EVENT SHARING` global privilege is confirmed available on the dev account `LFB71918` (verified 2026-04-09).

9. **`duration_ms` belongs inside `ExportOutcome`:** Measure export duration inside `otlp_export.py` around the synchronous `exporter.export(...)` call and store it on the returned `ExportOutcome`. This keeps the result self-contained for logging, pipeline health, smoke-harness serialization, and future collector callers without adding parallel duration arguments to every helper.

10. **Batch-size rules must be centralized:** Use shared helpers so all code paths agree on `batch_size`. For spans and logs, `batch_size = len(batch)`. For `MetricsData`, `batch_size` is the total number of exported metric data points across all `ResourceMetrics` / `ScopeMetrics` / metrics. For empty or `None` batches, `batch_size = 0` and the export is a no-op success.

11. **Module import pattern:** Follow Story 4.1/4.2 flat `app/python/` convention. `export_result.py` imports nothing from Snowflake. `pipeline_telemetry.py` imports `export_result` by plain name and receives `Session` as a parameter (not imported at module scope — use `TYPE_CHECKING` guard for the Session type annotation).

12. **`_metrics.pipeline_health` INSERT pattern:** The architecture doc shows the INSERT uses columns `pipeline_name`, `source_name`, `metric_name`, `metric_value`, `metadata`. The actual DDL in `setup.sql` has `RUN_ID`, `PIPELINE_NAME`, `SOURCE_NAME`, `METRIC_NAME`, `METRIC_VALUE`, `METADATA`, `RECORDED_AT`. Use `RUN_ID` for the caller-provided run ID. `RECORDED_AT` defaults to `CURRENT_TIMESTAMP()`.

### OTel SDK gRPC Retry Behavior (v1.38.0)

The OTel Python OTLP gRPC exporter has built-in retry logic in its private `_export()` method:

- **Public exporter result codes:** `SUCCESS`, `FAILURE`
- **Retryable gRPC status codes** (must mirror upstream exactly): `CANCELLED`, `DEADLINE_EXCEEDED`, `RESOURCE_EXHAUSTED`, `ABORTED`, `OUT_OF_RANGE`, `UNAVAILABLE`, `DATA_LOSS`
- **Retry budget:** `_MAX_RETRYS = 6`, additionally bounded by the exporter's `timeout` parameter (10 seconds in this project per `_EXPORT_TIMEOUT_S`)
- **Backoff:** exponential with jitter, starting at ~1 second (`2**retry_num * random.uniform(0.8, 1.2)`), with `RetryInfo` overrides when provided by the server

**Critical `4.1` foundation nuance:** the public `opentelemetry-python` exporter catches `RpcError` inside its own `_export()` method and usually returns `FAILURE` to the caller for both:
1. retryable failures whose internal retry budget was exhausted, and
2. non-retryable failures returned immediately by the exporter.

That means the `otlp_export.py` wrapper in this repo usually sees only `SUCCESS` / `FAILURE`, not the original `grpc.StatusCode`.

To handle this correctly without bypassing the `4.1` foundation or re-implementing exporter internals:
1. Measure `duration_ms` around `exporter.export(...)`
2. Check the public export result enum first (`SUCCESS` vs `FAILURE`)
3. If `FAILURE` and no `grpc.RpcError` was surfaced to our wrapper → classify via `classify_export_failure_without_status(...)` using `retryable=None` and `error_code='FAILURE'`
4. If a direct `grpc.RpcError` is surfaced to our wrapper (fallback path) → classify by the exact observed status using the upstream retry set and store `error.code().name` verbatim in `error_code`
5. If some other `Exception` is surfaced → keep `error_code=None`, preserve the sanitized message, and do not invent an alias code

**Do not** add custom retry loops, inspect private exporter state, or bypass the `4.1` public-exporter pattern just to recover hidden status codes.

### Upstream Code Handling

- **Public exporter result codes:** `SUCCESS`, `FAILURE`
- **Direct gRPC status codes available when surfaced:** `OK`, `CANCELLED`, `UNKNOWN`, `INVALID_ARGUMENT`, `DEADLINE_EXCEEDED`, `NOT_FOUND`, `ALREADY_EXISTS`, `PERMISSION_DENIED`, `RESOURCE_EXHAUSTED`, `FAILED_PRECONDITION`, `ABORTED`, `OUT_OF_RANGE`, `UNIMPLEMENTED`, `INTERNAL`, `UNAVAILABLE`, `DATA_LOSS`, `UNAUTHENTICATED`
- For OTLP export events, store the raw upstream code string in `error_code` when available. If the exporter does not expose one, leave `error_code` as `None` and rely on the sanitized `error_message`.

### Batch Size Rules

- **Span batches:** `batch_size = len(batch)`
- **Log batches:** `batch_size = len(batch)`
- **Metrics batches:** `batch_size` is the total number of exported metric data points across all `ResourceMetrics` / `ScopeMetrics` / metrics
- **Empty or `None` batches:** `batch_size = 0` and the export is a no-op success
- Use shared helpers in `export_result.py` so all three export functions, logging helpers, pipeline-health writes, and smoke diagnostics stay consistent

### ExportOutcome Design

```python
from __future__ import annotations
import dataclasses

@dataclasses.dataclass(frozen=True, slots=True)
class ExportOutcome:
    success: bool
    terminal: bool
    error_code: str | None = None
    error_message: str | None = None
    signal_type: str = ""
    batch_size: int = 0
    retryable: bool | None = None
    duration_ms: int = 0

    def __bool__(self) -> bool:
        return self.success

    @staticmethod
    def success_result(signal_type: str, batch_size: int, duration_ms: int) -> ExportOutcome: ...

    @staticmethod
    def noop_result(signal_type: str) -> ExportOutcome: ...

    @staticmethod
    def not_initialized(signal_type: str) -> ExportOutcome: ...

    def to_dict(self) -> dict[str, object]: ...
```

### Pipeline Health INSERT Pattern

```python
def record_batch_failure(session, pipeline_name, source_name, outcome, run_id):
    session.sql(
        """INSERT INTO _metrics.pipeline_health
           (RUN_ID, PIPELINE_NAME, SOURCE_NAME, METRIC_NAME, METRIC_VALUE, METADATA)
           VALUES (?, ?, ?, 'rows_failed', ?, PARSE_JSON(?))""",
        params=[
            run_id,
            pipeline_name,
            source_name,
            outcome.batch_size,
            json.dumps({
                "error_code": outcome.error_code,
                "error_message": outcome.error_message,
                "signal_type": outcome.signal_type,
                "retryable": outcome.retryable,
                "batch_size": outcome.batch_size,
                "duration_ms": outcome.duration_ms,
            }),
        ],
    ).collect()
```

### Error Message Sanitization Rules

The `_sanitize_error_message()` function must:
1. Strip PEM certificate blocks (`-----BEGIN.*-----` to `-----END.*-----`)
2. Strip URL credentials (anything matching `://user:pass@` or `://token@`)
3. Strip authorization headers (anything after `Authorization:` or `Bearer`)
4. Truncate to a maximum of 512 characters
5. Preserve any directly observed gRPC status code name and the first line of the error description when available
6. Never include the raw endpoint URL — use `_initialized_endpoint` from debug_snapshot if needed (it's already validated and contains only host:port)

### Structured Log Format for Native App Events

```python
log.error(
    "OTLP export terminal failure: %s",
    outcome.error_code,
    extra={
        "pipeline": pipeline_name,
        "source": source_name,
        "run_id": run_id,
        "signal_type": outcome.signal_type,
        "error_code": outcome.error_code,
        "error_message": outcome.error_message,
        "batch_size": outcome.batch_size,
        "duration_ms": outcome.duration_ms,
        "retryable": outcome.retryable,
    },
)
```

### Previous Story Intelligence (Stories 4.1 + 4.2)

1. **Module import pattern:** All `app/python/` modules use `from __future__ import annotations` and import siblings by plain name (e.g., `from export_result import ExportOutcome`). Follow this pattern.

2. **OTel SDK version (1.38.0):** Snowflake runtime pins `opentelemetry-sdk==1.38.0`. The local dev root venv has 1.39.1. Story 4.1 handled log type differences. Story 4.3 should not introduce new version-sensitive imports.

3. **`snowflake.yml` artifacts — no wildcard for `app/python/`:** Each new file MUST be individually listed. See Task 4.

4. **Thread safety pattern:** `otlp_export.py` uses `_state_cond` (a `threading.Condition` over `_init_lock`) for thread-safe access. The export result classification should happen INSIDE the existing try/except blocks of `export_spans()` etc. — no new locking is needed for the classification logic itself. `pipeline_telemetry.py` does not need thread safety — it's called from single-threaded SP handlers.

5. **Flat `app/python/` directory:** Do NOT create subdirectories. Story 4.1 established this pattern because Snowflake `IMPORTS` resolves flat top-level module names.

6. **Diagnostic SP registration pattern:** The smoke test SPs in `app/setup.sql` check export results. When updating the smoke test to handle `ExportOutcome`, keep the existing boolean keys by using `bool(result)` and add parallel `*_outcome` dicts via `result.to_dict()`. Do NOT change the smoke test SP signatures.

7. **Integration test `snow sql` subprocess pattern:** Story 4.2 established `_snow_sql_script()` for multi-statement SQL. The integration tests that call `otlp_export.export_spans()` directly from Python (not via `snow sql`) need to be updated for `ExportOutcome` return type.

8. **`grpc` import already exists:** `otlp_export.py` already imports `grpc` at the top level. `grpc.RpcError` and `grpc.StatusCode` are available without new dependencies.

### Testing Strategy

#### Tier 1: Unit Tests (root venv, pytest, fast, no Snowflake connection)

```bash
PYTHONPATH=app/python .venv/bin/python -m pytest tests/test_export_result.py tests/test_pipeline_telemetry.py -v
```

**`test_export_result.py` categories:**
1. gRPC status code classification (all codes in the mapping table)
2. Bare public-exporter `FAILURE` classification when no status is surfaced
3. Unexpected exception handling without inventing OTLP alias codes
4. `ExportOutcome.__bool__` truthiness
5. Factory helpers (`success_result`, `noop_result`, `not_initialized`) plus shared batch-size helpers
6. `_sanitize_error_message` stripping rules
7. `to_dict()` JSON-serializable output including `duration_ms`

**`test_pipeline_telemetry.py` categories:**
1. `record_batch_failure` — mock `session.sql()`, verify params
2. `record_batch_failure` graceful failure — mock `session.sql()` to raise, verify no exception propagated
3. `record_export_success` — verify correct metric name/value
4. Structured log output verification (capture log records, check `extra` fields)

**Updated `test_otlp_export.py` categories:**
1. Verify `export_spans()` returns `ExportOutcome` (not `bool`)
2. Verify `ExportOutcome.__bool__` preserves existing test logic
3. Verify the normal export path maps bare `FAILURE` results correctly without pretending the hidden status is known
4. Verify the surfaced-`grpc.RpcError` fallback path when `exporter.export()` raises directly
5. Verify empty batch returns noop result
6. Verify uninitialized exporter returns a terminal result with `error_code=None`

**Linting:**
```bash
.venv/bin/ruff check app/python/export_result.py app/python/pipeline_telemetry.py
```

#### Tier 2: Integration Smoke (existing suite)

Update `tests/integration/test_mapper_real_data.py` and `tests/integration/conftest.py` export-phase assertions to handle `ExportOutcome` objects. The live export should still succeed (returning `ExportOutcome` with `success=True`) while the smoke harness continues to expose boolean keys for compatibility. No new integration tests are needed for failure paths — those are covered by unit tests with mocked exporter results and surfaced exceptions.

### What to Avoid

- **Do NOT add application-level retry loops.** MVP uses OTel SDK built-in gRPC retry only (V12). No tenacity, no httpx, no custom backoff loops.
- **Do NOT pretend the hidden underlying gRPC status is known when the public exporter only returns `FAILURE`.** In that case, use `retryable=None` and `error_code='FAILURE'`.
- **Do NOT create `app/python/retry/` or `app/python/errors/` subdirectories.** Flat `app/python/` pattern.
- **Do NOT change `_EXPORT_TIMEOUT_S` without architecture review.** 10 seconds is the current MVP retry budget; changing it alters the documented retry window and failure behavior.
- **Do NOT store full error tracebacks in `_metrics.pipeline_health`.** Tracebacks go to Python logging (Native App events), not the health table. Health table gets sanitized, machine-readable error codes and summaries.
- **Do NOT make `pipeline_telemetry.py` import Snowpark at module scope.** Use `TYPE_CHECKING` guard for the `Session` type annotation. The module may be imported in contexts where Snowpark is unavailable (e.g., unit tests).
- **Do NOT change the `_metrics.pipeline_health` table DDL in `setup.sql`.** The existing schema (`RUN_ID`, `PIPELINE_NAME`, `SOURCE_NAME`, `METRIC_NAME`, `METRIC_VALUE`, `METADATA`, `RECORDED_AT`) is sufficient. Story 4.3 writes to it; it does not alter it.
- **Do NOT add `INSERT` grants on `_metrics.pipeline_health` to `app_admin`.** The collector SPs run in owner context (created in `_internal` schema), which already has write access. The `app_admin` role only needs `SELECT` for the Streamlit health page.
- **Do NOT log the raw endpoint URL in error messages.** The endpoint may contain path segments with tokens. Log only the host:port portion (already validated and stored in `_initialized_endpoint`).
- **Do NOT treat per-batch OTLP export failures as whole-app health-state transitions.** `SYSTEM$REPORT_HEALTH_STATUS(...)` is out of scope for this story.

### Project Structure Notes

**New files:**

| Path | Description |
|---|---|
| `app/python/export_result.py` | `ExportOutcome` dataclass + upstream retry-set constants + raw status classification + shared batch-size helpers |
| `app/python/pipeline_telemetry.py` | OTLP operational logging helpers + pipeline-health recording helpers |
| `tests/test_export_result.py` | Unit tests for error classification and ExportOutcome |
| `tests/test_pipeline_telemetry.py` | Unit tests for health recording and structured logging |

**Modified files:**

| Path | Change |
|---|---|
| `app/python/otlp_export.py` | Change `export_spans/metrics/logs` to return `ExportOutcome` instead of `bool`; handle the normal bare-`FAILURE` path first; preserve surfaced-`grpc.RpcError` fallback classification |
| `app/python/otlp_export_smoke_test.py` | Preserve boolean smoke-result keys and add structured `*_outcome` JSON payloads |
| `app/manifest.yml` | Add `telemetry_event_definitions` for OTLP operational logs (`ERRORS_AND_WARNINGS` mandatory, `DEBUG_LOGS` optional) |
| `app/setup.sql` | Add `'/python/export_result.py'` to both diagnostic OTLP runtime procedure `IMPORTS` blocks |
| `snowflake.yml` | Add 2 new artifact entries (`export_result.py`, `pipeline_telemetry.py`); optionally add `telemetry:` section to dev app entity for event sharing |
| `tests/test_otlp_export.py` | Update assertions for `ExportOutcome` return type |
| `tests/test_otlp_export_smoke_test.py` | Update assertions for `ExportOutcome` handling |
| `tests/integration/test_mapper_real_data.py` | Update direct export-phase assertions for `ExportOutcome` |
| `tests/integration/conftest.py` | Update shared export fixtures and assertions for `ExportOutcome` |

**No changes to:**
- `scripts/shared_content.sql` — no new grants
- `app/environment.yml` — no new Streamlit dependencies
- `pyproject.toml` — no new test markers needed

**IMPORTS chain for Snowflake SPs:** When `otlp_export.py` imports `export_result`, Snowflake needs `export_result.py` in the IMPORTS list of any SP that uses `otlp_export.py`. Update both existing smoke test SP registrations in `app/setup.sql` to include `'/python/export_result.py'`.

### References

- [Source: `_bmad-output/planning-artifacts/architecture.md` — V12 Failure handling (MVP), Operational Code Taxonomy, Pipeline Health Metric Names, Structured Log Format, Health Recording INSERT pattern]
- [Source: `_bmad-output/planning-artifacts/prd.md` — FR26, NFR24, §3.5 Native App event definitions, §3.6 Error handling trade-off, §5.4 Data loss MVP trade-off]
- [Source: `_bmad-output/planning-artifacts/epics.md` — Epic 4 Story 4.3 requirements and acceptance criteria]
- [Source: `_bmad-output/implementation-artifacts/4-1-secure-otlp-export-foundation.md` — Module import patterns, thread safety, OTel SDK version, flat file structure, export API surface, gRPC channel options]
- [Source: `_bmad-output/implementation-artifacts/4-2-splunk-compatible-telemetry-contract.md` — Previous story intelligence, integration test patterns, smoke test update patterns]
- [Source: OpenTelemetry Python exporter source v1.38.0 — `_RETRYABLE_ERROR_CODES`, `_MAX_RETRYS`, and public `_export()` behavior in `exporter.py`]
- [Source: `app/python/otlp_export.py` — Current export API (`export_spans`, `export_metrics`, `export_logs` returning `bool`), `_EXPORT_TIMEOUT_S = 10`, `grpc` import, `_CHANNEL_OPTIONS`]
- [Source: `app/setup.sql` — `_metrics.pipeline_health` DDL (RUN_ID, PIPELINE_NAME, SOURCE_NAME, METRIC_NAME, METRIC_VALUE, METADATA, RECORDED_AT)]
- [Source: OTel Python SDK v1.38.0 — OTLP gRPC exporter retry behavior, `SpanExportResult`, `MetricExportResult`, `LogExportResult`]
- [Source: gRPC Python API — `grpc.RpcError`, `grpc.StatusCode`, status code semantics]
- [Source: Snowflake Docs — Configure event definitions for an app (`configuration.telemetry_event_definitions`, supported definitions, sharing modes)]
- [Source: Snowflake Docs — Use logging and event tracing for an app]
- [Source: Snowflake Docs — Use monitoring for an app (`SYSTEM$REPORT_HEALTH_STATUS`) — intentionally out of scope for this story]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (Cursor Agent)

### Debug Log References

- Live failure tests with invalid PEM cert and disabled gRPC port confirmed expected behavior in `SNOWFLAKE.TELEMETRY.EVENTS` and `_METRICS.PIPELINE_HEALTH` tables (run_ids correlated across log types)
- Invalid PEM cert: app logged `SSL_ERROR_SSL` with `error_code=FAILURE`, `signal_type=spans/metrics/logs`
- gRPC port disabled: app logged `TypeError` normalization as `error_code=FAILURE` with `error_message` identifying the OTel SDK `cannot unpack non-iterable bool object` pattern
- Post-fix redeploy with `pipeline_telemetry.py` added to SP IMPORTS confirmed non-observability SPs (`test_otlp_export_runtime`, `test_otlp_export_runtime_with_secret`) no longer fail with `ModuleNotFoundError`

### Completion Notes List

1. **AC-2 deviation (intentional):** `classify_unexpected_exception` sets `error_code=type(exc).__name__` (e.g. `RuntimeError`) instead of `None` as originally specified. Agreed during live failure testing — a populated `error_code` is essential for structured event table queries. Story AC-2 and Task 1.6/5.4 updated to reflect this.
2. **Task 4.4 expanded:** Original task only mentioned adding `export_result.py` to SP IMPORTS. During code review, discovered `pipeline_telemetry.py` was also missing from both non-observability SP IMPORTS lists (imported transitively via `otlp_export_smoke_test.py`). Fixed and task description updated.
3. **TypeError normalization:** Added `classify_export_failure_without_status_exception` to handle the OTel SDK's `TypeError: cannot unpack non-iterable bool object` pattern, which surfaces when the gRPC channel is completely down and the SDK's internal retry unpacking fails. This is not a spec deviation — it's an additional failure mode discovered during live testing that required explicit handling.
4. **Low-level WARN logging in otlp_export.py:** `_log_export_exception` emits structured `WARN` logs with `signal_type`, `error_code`, and `error_message` as `extra` fields. This is internal diagnostic logging (Task 2.4 allows "low-level internal diagnostics"), not caller-context operational logging.

### File List

- `app/python/export_result.py` — NEW: `ExportOutcome` dataclass, gRPC status classification, sanitization, batch-size helpers, factory methods
- `app/python/pipeline_telemetry.py` — NEW: `ExportContext` dataclass, structured operational logging helpers, pipeline health recording helpers
- `app/python/otlp_export.py` — MODIFIED: return type changed from `bool` to `ExportOutcome`, integrated classification functions
- `app/python/otlp_export_smoke_test.py` — MODIFIED: emits `*_outcome` dicts alongside boolean keys
- `app/manifest.yml` — MODIFIED: added `telemetry_event_definitions` block
- `app/setup.sql` — MODIFIED: added `export_result.py` and `pipeline_telemetry.py` to SP IMPORTS
- `snowflake.yml` — MODIFIED: added artifact entries and dev telemetry sharing config
- `tests/test_export_result.py` — NEW: comprehensive unit tests for `export_result.py`
- `tests/test_pipeline_telemetry.py` — NEW: unit tests for `pipeline_telemetry.py`
- `tests/test_otlp_export.py` — MODIFIED: updated for `ExportOutcome` return type
- `tests/test_otlp_export_smoke_test.py` — MODIFIED: updated for `*_outcome` payloads (file existed previously)
- `tests/integration/conftest.py` — MODIFIED: `live_export_results` fixture uses `ExportOutcome.success`
- `tests/integration/test_mapper_real_data.py` — MODIFIED: asserts `result.success` from `ExportOutcome`
