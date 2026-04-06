# Story 4.1: Secure OTLP Export Foundation

Status: done

## Story

As an operator (Sam),
I want the app to establish a secure, reusable OTLP export foundation for all telemetry signals,
so that later activation and pipeline runs can send data to the configured collector without duplicating transport logic.

## Acceptance Criteria

1. **Given** the app has `otlp.endpoint` and an optional PEM secret reference in `_internal.config`
   **When** the export layer initializes in a task sandbox
   **Then** module-level OTLP exporters are created for the required signals (Span, Metric, Log) using TLS credentials from the default CA bundle or the configured PEM secret

2. **Given** any exporter initialization
   **When** the endpoint scheme is `http://`, `insecure=True`, or plaintext transport is otherwise requested
   **Then** initialization fails with a clear error — no plaintext OTLP path exists

3. **Given** the export module is loaded in a stored procedure sandbox
   **When** the same collector or diagnostic procedure runs multiple times on the same warm warehouse node within the idle window
   **Then** the gRPC channel and exporter instances are reused via module-level caching (BP-2), avoiding ~300–500ms cold-start per call
   **And** if Snowflake recycles the sandbox, `init_exporters()` transparently rebuilds the exporters on the next call without requiring caller-side recovery logic

4. **Given** the export module is called from a collector or diagnostic procedure
   **When** the caller passes a batch of OTLP spans, logs, or metrics
   **Then** the export function sends the batch synchronously and returns an explicit success/failure result the caller can act on

5. **Given** a procedure execution completes successfully
   **When** the handler returns
   **Then** cached exporters are NOT closed on the normal return path
   **And** explicit close/reset is reserved for idle-timeout eviction, endpoint or PEM changes, or diagnostic teardown

6. **Given** the app is deployed to Snowflake dev
   **When** the team runs a dedicated diagnostic OTLP export stored procedure twice in the same warm session
   **Then** the returned JSON includes non-secret debug metadata (`test_id`, target endpoint, exporter ids or generation, per-signal results) sufficient to verify collector delivery and cache reuse

## Tasks / Subtasks

- [x] Task 1: Create `app/python/otlp_export.py` — the reusable export module (AC: 1, 2, 3, 4, 5)
  - [x] 1.1 Define module-level exporter singletons for spans, metrics, and logs, plus cache metadata (`generation`, `last_used`, endpoint or PEM fingerprint), protected by `threading.Lock`
  - [x] 1.2 Implement `_build_credentials()` — resolve default trust store vs custom PEM secret
  - [x] 1.3 Implement `_build_channel_options()` — gRPC keepalive + reconnect backoff configuration
  - [x] 1.4 Implement `_build_span_exporter()`, `_build_metric_exporter()`, and `_build_log_exporter()` with TLS-only enforcement
  - [x] 1.5 Implement `init_exporters()` — lazy initialization with idle-timeout eviction fallback and transparent rebuild after sandbox recycle
  - [x] 1.6 Implement `export_spans(spans_batch)`, `export_metrics(metrics_batch)`, and `export_logs(logs_batch)` — synchronous send with explicit result
  - [x] 1.7 Implement `debug_snapshot()` — non-secret cache metadata for local and Snowflake runtime verification
  - [x] 1.8 Implement `close_exporters()` / `_close_exporters_unlocked()` for idle eviction, endpoint or PEM changes, and explicit diagnostic cleanup only
  - [x] 1.9 Reject plaintext endpoints (http:// or insecure=True) with `ValueError`
- [x] Task 2: Add a diagnostic runtime harness that can be executed locally and in Snowflake (AC: 3, 4, 6)
  - [x] 2.1 Create `app/python/otlp_export_smoke_test.py` — a thin diagnostic handler that imports `otlp_export`, emits uniquely tagged span/log/metric batches, and returns JSON results
  - [x] 2.2 Register `app_public.test_otlp_export_runtime(endpoint VARCHAR, cert_pem VARCHAR, test_id VARCHAR)` in `app/setup.sql` with `PACKAGES = ('snowflake-snowpark-python', 'opentelemetry-sdk', 'opentelemetry-exporter-otlp-proto-grpc', 'grpcio', 'validators')`, `IMPORTS = ('/python/otlp_export_smoke_test.py', '/python/otlp_export.py', '/python/endpoint_parse.py')`, and `EXTERNAL_ACCESS_INTEGRATIONS = (otlp_egress_eai)`
  - [x] 2.3 Register `app_public.test_otlp_export_runtime_with_secret(endpoint VARCHAR, test_id VARCHAR)` in `app/setup.sql` with the same `PACKAGES` and `IMPORTS` as 2.2, plus `SECRETS = ('otlp_pem_cert' = _internal.otlp_pem_secret)` for real Snowflake validation
  - [x] 2.4 Keep these procedures explicitly diagnostic-only; production collector procedures remain in Epic 5
- [x] Task 3: Add the export module and diagnostic harness to `snowflake.yml` artifacts (AC: all)
  - [x] 3.1 Add `src: app/python/otlp_export.py` → `dest: python/otlp_export.py` entry
  - [x] 3.2 Add `src: app/python/otlp_export_smoke_test.py` → `dest: python/otlp_export_smoke_test.py` entry
- [x] Task 4: Write unit tests in `tests/test_otlp_export.py` and `tests/test_otlp_export_smoke_test.py` (AC: 1–5)
  - [x] 4.1 Test TLS-only enforcement — plaintext endpoint raises ValueError
  - [x] 4.2 Test default trust store path (no PEM) — exporter creates with `credentials=grpc.ssl_channel_credentials()`
  - [x] 4.3 Test custom PEM path — exporter creates with `credentials=grpc.ssl_channel_credentials(root_certificates=pem_bytes)`
  - [x] 4.4 Test `export_spans` returns explicit success/failure result
  - [x] 4.5 Test `export_logs` returns explicit success/failure result
  - [x] 4.6 Test `export_metrics` returns explicit success/failure result
  - [x] 4.7 Test `close_exporters()` calls exporter.shutdown() for all three exporters and clears cache metadata
  - [x] 4.8 Test module-level singleton behavior (second warm call returns the same exporter instances)
  - [x] 4.9 Test idle-timeout eviction — exporters are recreated after `_MAX_IDLE_S` seconds
  - [x] 4.10 Test thread-safe init — concurrent `init_exporters()` calls do not corrupt state
  - [x] 4.11 Test `debug_snapshot()` exposes only non-secret metadata and increments `generation` on reinit
  - [x] 4.12 Test `_CHANNEL_OPTIONS` are passed to span, metric, and log exporter constructors
- [x] Task 5: Local-first integration test against the real OTel collector (AC: 2, 4, 5, 6)
  - [x] 5.1 Reuse the existing transport probe at `grpc_test/otlp_grpc_probe.py` and the setup guide at `grpc_test/tls-setup/README.md` to prove TLS reachability before debugging exporter logic
  - [x] 5.2 Write a local runtime smoke test that imports `otlp_export_smoke_test.py` directly, calls the same handler function used by the Snowflake stored procedure, and sends uniquely tagged span/log/metric payloads to the dev OTel collector
  - [x] 5.3 Verify arrival via SSH using the unique `test_id` marker and the collector journal commands documented in this story
  - [x] 5.4 If TLS or routing fails, use the existing probe and collector-side config inspection commands before changing exporter code
- [x] Task 6: Deployed Snowflake runtime validation (AC: 3, 4, 5, 6)
  - [x] 6.1 Deploy with `PRIVATE_KEY_PASSPHRASE=qwerty123 snow app run -c dev`
  - [x] 6.2 Use the diagnostic stored procedure in Snowsight or `snow sql` to send uniquely tagged span/log/metric payloads from the real Snowflake SP sandbox
  - [x] 6.3 Call the diagnostic stored procedure twice in the same warm SQL session and compare returned exporter ids or generation to confirm cache reuse on the warm path
  - [x] 6.4 Verify collector arrival via SSH logs keyed by `test_id`, and treat exporter recreation after warehouse suspend/resume or sandbox recycle as expected cold-path behavior

## Dev Notes

### Story Boundary

This story creates the **reusable export module** (`otlp_export.py`) that Epic 5 collectors will import, plus a **diagnostic runtime harness** that lets the team validate the module locally and from the real Snowflake SP sandbox. It does NOT create production collectors, tasks, streams, or pipeline orchestration. The module and harness encapsulate:
- OTLP exporter construction (TLS credentials, endpoint parsing)
- Three dedicated exporters (Span, Metric, Log)
- Synchronous batch export (spans, logs, metrics)
- Explicit success/failure return for caller error handling
- Non-secret debug metadata for cache reuse and collector verification
- Explicit close/reset only for idle eviction, endpoint or PEM changes, and diagnostics

Story 4.2 (telemetry contract) will build on this foundation to add attribute mapping and enrichment. Story 4.3 (retry/terminal failure) will add failure classification around the export results from this module.

### Architecture Compliance

**Target Snowflake runtime:** Stored procedures in this story target Python 3.13. Streamlit remains on Python 3.11 and uses `app/environment.yml`; do not use that file as the source of truth for stored procedure runtime selection. For the current Snowflake Anaconda Channel on Python 3.13, use `snowflake-snowpark-python==1.48.0`, `opentelemetry-sdk==1.38.0`, and `opentelemetry-exporter-otlp-proto-grpc==1.38.0`.

**Key design decisions that MUST be followed:**

1. **Module-level exporter initialization (BP-2, §7.12):** Create `OTLPSpanExporter`, `OTLPMetricExporter`, and `OTLPLogExporter` instances at module scope. Snowflake caches imported modules across invocations on the same warehouse, so the gRPC channels can persist across task runs. **Must be protected by `threading.Lock`** — Snowflake may invoke handlers from multiple threads concurrently on the same node.

2. **TLS-only transport (NFR7):** Zero successful outbound connections without encrypted transport. Reject `http://` schemes and `insecure=True`. Always use `grpc.ssl_channel_credentials()`.

3. **Single connection per procedure (BP-3, §7.12):** One dedicated exporter per signal type is sufficient. Never create new clients per batch or per chunk.

4. **Synchronous export (§7.11, MVP):** Export each `to_pandas_batches()` chunk synchronously before fetching the next. No threading in MVP (BP-7 is post-MVP).

5. **Direct exporter use, not provider pipelines:** For stored procedure lifecycle, **use the OTel exporters directly** (call `exporter.export()`) rather than going through `TracerProvider` / `MeterProvider` + processor pipelines. The collectors in Epic 5 and the diagnostic harness in this story will construct OTel SDK objects (`ReadableSpan`, `ReadableLogRecord`, `MetricsData`) and pass them directly to the exporter `export()` methods. This avoids BatchSpanProcessor thread lifecycle issues in short-lived SP sandboxes.

6. **Batch processor rationale and normal return behavior:** `BatchSpanProcessor` uses a daemon worker thread. Snowflake terminates SP sandbox processes with SIGKILL-like behavior — `atexit` handlers, `__del__` methods, and `finally` blocks in background threads are NOT guaranteed to run. Daemon threads are killed immediately when the handler returns. Calling `exporter.export(batch)` directly is the deterministic pattern, and because export is synchronous the normal handler return path must preserve the cached exporters rather than shutting them down after every call.

7. **gRPC keepalive + idle-timeout eviction (dual defense):** Configure gRPC keepalive pings to prevent NAT gateway from closing idle connections. As a fallback, implement idle-timeout eviction that recreates exporters after prolonged inactivity. See "Snowflake SP Sandbox & gRPC Channel Lifecycle" section below.

8. **Local-first validation is mandatory:** Reuse `grpc_test/otlp_grpc_probe.py` and `grpc_test/tls-setup/README.md` before diagnosing exporter logic or Snowflake runtime behavior. The transport path must be proven independently from the exporter module.

### Snowflake SP Sandbox & gRPC Channel Lifecycle (Research Findings)

These findings come from Cortex CLI and Perplexity deep research, cross-referenced against Snowflake and gRPC documentation. They directly affect the module's design.

**1. Module-level caching is best-effort, not guaranteed:**
- Within a single SQL session, consecutive SP calls MAY reuse the same Python process (warm-start optimization).
- Module-level globals CAN survive across invocations on the same warehouse node, but Snowflake may recycle the sandbox at any time (scaling events, node rebalancing, memory pressure, warehouse suspend/resume).
- Across different SQL sessions or after warehouse suspend/resume → fresh Python interpreter, no state survives.
- **Implication:** Every code path accessing a module-level singleton MUST include a `if _exporter is None` guard. Design to work correctly even if re-initialized on every call.

**2. `atexit` and daemon threads are NOT safe:**
- Snowflake terminates SP processes like SIGKILL, not graceful `sys.exit()`.
- `atexit` handlers, `__del__`, and `finally` blocks in background threads may never execute.
- Daemon threads (used by `BatchSpanProcessor`) are killed immediately when the main thread exits.
- **Implication:** NEVER use `BatchSpanProcessor`. Use direct `exporter.export()` calls. Do **not** close cached exporters on the normal successful SP return path; close them only during idle eviction, endpoint or PEM changes, or explicit diagnostic teardown.

**3. Handlers may be called from multiple threads concurrently:**
- Snowflake may invoke the same handler from multiple threads within a single Python process on the same node.
- Module-level globals are shared across these threads.
- **Implication:** The `threading.Lock` protecting `init_exporters()` / exporter swap is mandatory. The OTel exporter's `export()` method already has its own internal `threading.Lock`, so the export path is inherently thread-safe.

**4. NAT gateway idle timeout (60–350s) and gRPC channel recovery:**
- Outbound SP traffic goes through Snowflake's NAT gateway. Idle TCP connections are closed after 60–350 seconds.
- When NAT closes a connection, the next gRPC `export()` call gets `UNAVAILABLE` status code.
- gRPC channel **auto-reconnects** transparently with exponential backoff (`initial_reconnect_backoff_ms` → `max_reconnect_backoff_ms`). The exporter does NOT need to be recreated for transient TCP resets.
- However, Snowflake's intermediate network infrastructure **may not honor** gRPC keepalive frames.
- **Implication:** Use dual defense: (a) gRPC keepalive as primary prevention, (b) idle-timeout eviction as fallback.

**5. gRPC keepalive + channel configuration (primary defense against NAT idle close):**
```python
_CHANNEL_OPTIONS = [
    ("grpc.keepalive_time_ms", 30_000),          # PING every 30s
    ("grpc.keepalive_timeout_ms", 10_000),        # wait 10s for PONG
    ("grpc.keepalive_permit_without_calls", 1),   # PING even when idle
    ("grpc.http2.max_pings_without_data", 0),     # unlimited idle PINGs
    ("grpc.initial_reconnect_backoff_ms", 100),   # fast first reconnect for short-lived SPs
    ("grpc.max_reconnect_backoff_ms", 1_000),     # prevent retry sleeps from consuming SP window
    ("grpc.dns_min_time_between_resolutions_ms", 10_000),  # avoid excessive DNS churn
    ("grpc.max_send_message_length", 4 * 1024 * 1024),    # 4 MB bounded batch sizing
    ("grpc.max_receive_message_length", 4 * 1024 * 1024), # symmetric limit
]
```
These options are passed to the OTLPSpanExporter constructor. If the NAT gateway respects PING frames, this prevents idle connection closure entirely. If not, the auto-reconnect backoff kicks in. The reconnect backoff values were tuned per `grpc_research.md` §5 to favor fast recovery in short-lived SP windows. Message size limits enforce the bounded batch-sizing constraint.

**6. Idle-timeout eviction (fallback defense):**
If keepalive fails to prevent NAT closure and the auto-reconnect backoff causes unacceptable latency, recreate the exporter after `_MAX_IDLE_S` (55 seconds, conservatively under the 60s minimum NAT timeout):
```python
import time, threading

_init_lock = threading.Lock()
_span_exporter = None
_last_used = 0.0
_MAX_IDLE_S = 55

def _get_or_create_exporter(endpoint, pem_cert):
    global _span_exporter, _last_used
    with _init_lock:
        now = time.monotonic()
        if _span_exporter is None or (now - _last_used) > _MAX_IDLE_S:
            if _span_exporter is not None:
                try:
                    _span_exporter.shutdown()
                except Exception:
                    pass
            _span_exporter = _create_exporter(endpoint, pem_cert)
        _last_used = now
        return _span_exporter
```

**7. OTel exporter `export()` thread safety:**
- Both `OTLPSpanExporter` and `OTLPLogExporter` use an internal `threading.Lock()` that serializes all `export()` calls.
- The OTel spec mandates: "Export() will never be called concurrently for the same exporter instance" — the lock enforces this.
- The underlying `grpc.Channel` is also fully thread-safe.
- `shutdown()` acquires the same lock — it blocks if an export is in progress. Recent SDK fixes ensure shutdown interrupts retry-sleep phases and completes within timeout.
- **Implication:** No additional locking is needed around `export_spans()` / `export_logs()` calls. `export_metrics()` is still executed synchronously by the caller in MVP. Only the init or swap path needs our `_init_lock`.

**8. Memory budget:**
- Snowflake SP sandbox has ~284 MB base overhead per Python interpreter initialization.
- gRPC channel + OTel exporter adds modest overhead (~10–20 MB).
- Memory scales with warehouse size; not a concern for this module.

**9. Multi-node behavior:**
- When Snowflake scales a warehouse from 1 to N nodes, each new node starts with a completely fresh Python environment — no state migration.
- Module-level singletons exist independently per node. This is fine — each node creates its own exporter on first use.

**10. `splunk-opentelemetry` package (2.8.0) — skip it:**
- This is the Splunk Distribution of OTel Python, designed for long-running app processes (auto-instrumentation, profiling, runtime metrics).
- Most features (auto-instrumentation, AlwaysOn profiling) are irrelevant in SP sandbox.
- Adds large dependency tree for unused features.
- Stick with standard `opentelemetry-sdk` + `opentelemetry-exporter-otlp-proto-grpc` for explicit lifecycle control.

### OTel Python SDK API Reference (v1.38.0)

**Imports for exporters:**
```python
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
```

**CRITICAL:** The log exporter module is `_log_exporter` (with underscore prefix), NOT `log_exporter`.

**Constructor signatures (span and log share the same pattern; metric adds metric-specific kwargs but supports the same transport kwargs):**
```python
OTLPSpanExporter(
    endpoint: str | None = None,       # "host:port" — no scheme prefix
    insecure: bool | None = None,      # True = plaintext, False/None = TLS
    credentials: ChannelCredentials | None = None,  # grpc.ssl_channel_credentials(...)
    headers: dict[str, str] | None = None,
    timeout: float | None = None,      # seconds (NOT milliseconds)
    compression: Compression | None = None,
)
```

**TLS credential construction:**
```python
import grpc

# Default system trust store
creds = grpc.ssl_channel_credentials()

# Custom PEM CA certificate
pem_bytes: bytes = pem_string.encode("utf-8")
creds = grpc.ssl_channel_credentials(root_certificates=pem_bytes)
```

When `credentials` is passed to the exporter, it is used directly — the SDK does not override it with env-var-based credentials.

**Export method:** `exporter.export(batch)` returns `SpanExportResult.SUCCESS` or `SpanExportResult.FAILURE`. For logs: `LogExportResult.SUCCESS` / `LogExportResult.FAILURE`. For metrics: `MetricExportResult.SUCCESS` / `MetricExportResult.FAILURE`.

```python
from opentelemetry.sdk.trace.export import SpanExportResult
result = span_exporter.export(spans)
if result == SpanExportResult.SUCCESS:
    ...
```

**Shutdown:** `exporter.shutdown()` closes the gRPC channel. In this story, that operation is reserved for `close_exporters()` during idle eviction, endpoint or PEM changes, or explicit diagnostic teardown. Do **not** call it on the normal successful SP return path, because that would destroy the module-level cache that AC3 requires.

### Snowflake EAI / Secret Integration

The module needs to read the PEM certificate at runtime. Two approaches exist in the codebase:

1. **Secret via `_snowflake` (preferred for SP context):** The calling stored procedure binds `SECRETS = ('otlp_pem_cert' = _internal.otlp_pem_secret)` and `EXTERNAL_ACCESS_INTEGRATIONS = (otlp_egress_eai)`. The module calls:
   ```python
   import _snowflake
   pem = _snowflake.get_generic_secret_string("otlp_pem_cert")
   ```
   
2. **PEM passed as argument:** The caller reads the secret and passes the PEM string to the export module. This keeps the module testable without `_snowflake`.

**Recommended:** Option 2 for the module (keeps it testable). The calling SP or diagnostic handler reads the secret and passes `pem_string` to the init function. The module accepts `Optional[str]` for PEM.

**Existing infrastructure (already provisioned):**
- `_internal.otlp_pem_secret` — `GENERIC_STRING` secret for PEM material
- `_internal.otlp_egress_rule` — `HOST_PORT` network rule (updated by `provision_egress.py`)
- `otlp_egress_eai` — EAI with `ALLOWED_NETWORK_RULES` + `ALLOWED_AUTHENTICATION_SECRETS`

**Endpoint format:** The `endpoint_parse.py` module already handles `https://host:port` → `(host, port)` extraction. Reuse `parse_endpoint()` and `host_port_string()` from it. The OTel exporter expects `"host:port"` without scheme.

### Config Reading Pattern

The export module itself does NOT read from `_internal.config`. The calling SP (in Epic 5) reads config and passes `endpoint` and `pem_string` to the module's init function. This keeps the module a pure library with no Snowflake SQL dependencies.

Config keys (for reference — read by the caller, not by this module):
- `otlp.endpoint` — the OTLP gRPC endpoint (e.g., `https://collector.example.com:4317`)
- `otlp.pem_secret_ref` — marker/config value indicating the PEM secret is populated and should be used by secret-bound procedures

### File Structure

**Canonical module path:** Use `app/python/otlp_export.py`. If older planning documents mention `app/python/exporters/otlp_grpc.py`, treat that as a planning-era alias and do **not** create a second implementation under a new `exporters/` directory.

**New files:**
| Path | Description |
|------|-------------|
| `app/python/otlp_export.py` | Reusable OTLP export module |
| `app/python/otlp_export_smoke_test.py` | Diagnostic handler reusable locally and from Snowflake SP runtime |
| `tests/test_otlp_export.py` | Unit tests (mocked gRPC/OTel) |
| `tests/test_otlp_export_smoke_test.py` | Unit tests for the diagnostic runtime harness |

**Modified files:**
| Path | Change |
|------|--------|
| `app/environment.yml` | Clarify that Streamlit remains on Python 3.11 while stored procedures target Python 3.13, and document the current Snowpark package split between those runtimes |
| `app/setup.sql` | Register diagnostic OTLP runtime test procedures |
| `snowflake.yml` | Add `otlp_export.py` and `otlp_export_smoke_test.py` artifact entries |

**No changes to:**
- `app/manifest.yml` — no new privileges needed
- `scripts/shared_content.sql` — no new grants

### Module Design

```python
# app/python/otlp_export.py — high-level structure

"""Reusable OTLP/gRPC export foundation for Snowflake Native App telemetry pipelines."""

from __future__ import annotations
import logging
import threading
import time
import grpc
from endpoint_parse import parse_endpoint, host_port_string
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk.metrics.export import MetricExportResult
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.sdk._logs._internal.export import LogExportResult

log = logging.getLogger(__name__)

# ── gRPC channel options ──────────────────────────────────────────
# Tuned per grpc_research.md §5: fast reconnect for short-lived SPs,
# bounded message sizes, and DNS churn prevention.
_CHANNEL_OPTIONS: tuple[tuple[str, int], ...] = (
    ("grpc.keepalive_time_ms", 30_000),
    ("grpc.keepalive_timeout_ms", 10_000),
    ("grpc.keepalive_permit_without_calls", 1),
    ("grpc.http2.max_pings_without_data", 0),
    ("grpc.initial_reconnect_backoff_ms", 100),
    ("grpc.max_reconnect_backoff_ms", 1_000),
    ("grpc.dns_min_time_between_resolutions_ms", 10_000),
    ("grpc.max_send_message_length", 4 * 1024 * 1024),
    ("grpc.max_receive_message_length", 4 * 1024 * 1024),
)

# ── Module-level singletons (BP-2) ───────────────────────────────
# Protected by _init_lock (Snowflake may call handlers from multiple threads).
_init_lock = threading.Lock()
_span_exporter: OTLPSpanExporter | None = None
_metric_exporter: OTLPMetricExporter | None = None
_log_exporter: OTLPLogExporter | None = None
_initialized_endpoint: str | None = None
_initialized_pem_fingerprint: str | None = None
_generation: int = 0
_last_used: float = 0.0
_MAX_IDLE_S: int = 55  # conservative, under typical NAT idle timeout (60–350s)

def _build_credentials(pem_cert: str | None) -> grpc.ChannelCredentials:
    """Build TLS channel credentials from default trust store or custom PEM."""
    ...

def _validate_endpoint(endpoint: str) -> str:
    """Parse endpoint, reject plaintext, return 'host:port' for gRPC."""
    ...

def init_exporters(endpoint: str, pem_cert: str | None = None) -> None:
    """Initialize or reinitialize exporters for the given endpoint.

    Thread-safe. Handles idle-timeout eviction of stale channels.
    Called by the SP handler before each export cycle.
    """
    global _span_exporter, _metric_exporter, _log_exporter
    global _initialized_endpoint, _initialized_pem_fingerprint, _generation, _last_used
    with _init_lock:
        now = time.monotonic()
        target = _validate_endpoint(endpoint)
        pem_fingerprint = _pem_fingerprint(pem_cert)
        needs_init = (
            _span_exporter is None
            or _metric_exporter is None
            or _log_exporter is None
            or _initialized_endpoint != target
            or _initialized_pem_fingerprint != pem_fingerprint
            or (now - _last_used) > _MAX_IDLE_S
        )
        if not needs_init:
            _last_used = now
            return
        # Close stale exporters if they exist
        _close_exporters_unlocked()
        # Build fresh exporters
        creds = _build_credentials(pem_cert)
        _span_exporter = OTLPSpanExporter(
            endpoint=target, credentials=creds, channel_options=tuple(_CHANNEL_OPTIONS)
        )
        _metric_exporter = OTLPMetricExporter(
            endpoint=target, credentials=creds, channel_options=tuple(_CHANNEL_OPTIONS)
        )
        _log_exporter = OTLPLogExporter(
            endpoint=target, credentials=creds, channel_options=tuple(_CHANNEL_OPTIONS)
        )
        _initialized_endpoint = target
        _initialized_pem_fingerprint = pem_fingerprint
        _generation += 1
        _last_used = now
    ...

def export_spans(batch) -> bool:
    """Export a batch of spans. Returns True on success, False on failure.

    Thread-safe (OTel exporter has internal lock).
    """
    ...

def export_metrics(batch) -> bool:
    """Export a metrics batch. Returns True on success, False on failure."""
    ...

def export_logs(batch) -> bool:
    """Export a batch of log records. Returns True on success, False on failure."""
    ...

def debug_snapshot() -> dict[str, object]:
    """Return non-secret cache metadata for tests and diagnostic procedures."""
    ...

def close_exporters() -> None:
    """Explicitly close cached exporters.

    Use for idle eviction, endpoint or PEM changes, or diagnostic teardown.
    Do not call on the normal successful collector return path.
    """
    global _span_exporter, _metric_exporter, _log_exporter
    global _initialized_endpoint, _initialized_pem_fingerprint
    with _init_lock:
        _close_exporters_unlocked()
        _initialized_endpoint = None
        _initialized_pem_fingerprint = None
    ...

def _close_exporters_unlocked() -> None:
    """Internal: shut down exporters without acquiring _init_lock."""
    global _span_exporter, _metric_exporter, _log_exporter
    for exp in (_span_exporter, _metric_exporter, _log_exporter):
        if exp is not None:
            try:
                exp.shutdown()
            except Exception:
                log.warning("Exporter shutdown failed", exc_info=True)
    _span_exporter = None
    _metric_exporter = None
    _log_exporter = None
```

### What This Story Does NOT Implement

- **Telemetry contract mapping** (Event Table → OTel attributes) → Story 4.2
- **Retry classification / terminal failure recording** → Story 4.3
- **Production collector procedures** that call this module for real pipeline execution → Epic 5
- **`_metrics.pipeline_health` writes** → Epic 5 / Story 4.3
- **Tasks, streams, and activation orchestration** → Epic 5 / Epic 6
- **Provider/processor pipeline wiring** (`TracerProvider`, `MeterProvider`, `BatchSpanProcessor`) — direct `exporter.export()` is the MVP pattern
- **Consumer-facing Streamlit diagnostics UI** — out of scope; this story validates via local tests, SQL procedure calls, and collector-side SSH inspection

### Testing Strategy

**1. Unit tests (root venv, `pytest`):**
```bash
PYTHONPATH=app/python .venv/bin/python -m pytest tests/test_otlp_export.py tests/test_otlp_export_smoke_test.py -v
```

Mock `grpc.ssl_channel_credentials`, `OTLPSpanExporter`, `OTLPMetricExporter`, and `OTLPLogExporter` constructors. Test:
- TLS enforcement (ValueError on `http://` endpoints)
- Credential construction (default vs custom PEM)
- Singleton behavior (init once, get same instance)
- Export result propagation (SUCCESS → True, FAILURE → False) for spans, metrics, and logs
- `close_exporters()` calls exporter.shutdown() with exception safety for all three exporters
- Idle-timeout eviction: mock `time.monotonic()` to simulate >55s gap, verify exporter is recreated
- Thread-safe init: use `threading.Thread` to call `init_exporters()` concurrently, assert no corruption
- Debug snapshot: verify only non-secret metadata is returned and `generation` increments on reinit
- Channel options: verify `_CHANNEL_OPTIONS` are passed to exporter constructors (keepalive, reconnect backoff)

**2. Local transport/TLS pre-check (must happen before exporter debugging):**

Reuse the existing probe and TLS setup assets already in the repo:

```bash
uv run python grpc_test/otlp_grpc_probe.py otelcol.israelcentral.cloudapp.azure.com:4317 \
  --tls --pem grpc_test/tls-setup/ca.crt --approach b -v
```

If the probe fails, follow `grpc_test/tls-setup/README.md` before changing `otlp_export.py`. This separates collector transport issues from exporter-implementation issues.

**3. Local SP-style runtime smoke test against the real collector:**

Run a local smoke test that imports the same diagnostic handler used by Snowflake (`app/python/otlp_export_smoke_test.py`) and executes it directly under the root venv. This is the local equivalent of the Snowflake stored procedure call and must emit:
- one uniquely tagged span batch
- one uniquely tagged log batch
- one uniquely tagged metrics batch
- a shared `test_id` marker (for example `story4_1_local_<timestamp>`)

After sending the payloads, verify arrival using the `test_id` marker:

```bash
ssh otelcol "sudo journalctl -u splunk-otel-collector --since '3 minutes ago' --no-pager 2>/dev/null" | grep -B5 -A15 "<test_id>"
ssh otelcol "sudo journalctl -u splunk-otel-collector -n 300 --no-pager 2>/dev/null" | grep -B5 -A15 "<test_id>"
```

If broader collector debugging is needed, the operator may also inspect config on the host, but **must never copy returned secret values into notes, logs, or Git**:

```bash
ssh otelcol "sudo cat /etc/otel/collector/splunk-otel-collector.conf | grep -E '(SPLUNK_REALM|SPLUNK_ACCESS_TOKEN|SPLUNK_INGEST_URL|SPLUNK_API_URL)'" 2>&1
```

**4. Deployed Snowflake runtime validation:**

The story must prove the exact same code path works from a real Snowflake Python SP sandbox:

1. Deploy with `PRIVATE_KEY_PASSPHRASE=qwerty123 snow app run -c dev`
2. If using the dev TLS CA, load it into the app secret:
   ```sql
   CALL app_public.save_pem_secret($$<contents of grpc_test/tls-setup/ca.crt>$$);
   ```
3. Call the diagnostic procedure from the same SQL session with a unique `test_id`:
   ```sql
   CALL app_public.test_otlp_export_runtime_with_secret(
     'https://otelcol.israelcentral.cloudapp.azure.com:4317',
     'story4_1_sf_001'
   );
   ```
4. Call it again within the idle window from the same warm session and compare returned `generation` / exporter ids. The warm-path expectation is reuse. If Snowflake recycled the sandbox between calls, transparent reinit is acceptable and should be visible in the returned metadata.
5. Verify collector arrival with the same SSH commands keyed by `test_id`.

**5. Debugging expectations:**

- Prove raw TLS connectivity first with `grpc_test/otlp_grpc_probe.py`
- Then prove local SP-style runtime behavior via `otlp_export_smoke_test.py`
- Then prove real Snowflake SP runtime behavior via `CALL app_public.test_otlp_export_runtime...`
- Only after those steps should exporter code or Snowflake deployment wiring be changed

**Dev environment (from `.cursor/rules/dev_environment.mdc`):**
- Run all tests with the root venv: `PYTHONPATH=app/python .venv/bin/python -m pytest tests/ -v`
- Root venv is Python 3.13, managed by `uv`
- Linting: `.venv/bin/ruff check .`
- Use the same root venv for local probe and local SP-style smoke tests

### OTel Collector Infrastructure (Dev Environment)

The dev OTel Collector runs on `otelcol.israelcentral.cloudapp.azure.com` (Azure VM, hostname `OTELCOL`) as a systemd service (`splunk-otel-collector`, Splunk Distribution v0.140.0). Configuration lives at `/etc/otel/collector/agent_config.yaml` (owned by `splunk-otel-collector` user; edits require `sudo`).

**SSH access:** `ssh otelcol` (resolved via `~/.ssh/config`). The `azureuser` account has passwordless `sudo`. Firewall rules may need updating if SSH times out.

**Service management:**
```bash
ssh otelcol "sudo systemctl restart splunk-otel-collector"
ssh otelcol "sudo systemctl is-active splunk-otel-collector"
ssh otelcol "sudo systemctl --no-pager --full status splunk-otel-collector"
```

**Journal inspection (primary debugging tool):**
```bash
ssh otelcol "sudo journalctl -u splunk-otel-collector --since '5 min ago' --no-pager"
ssh otelcol "sudo journalctl -u splunk-otel-collector --since '5 min ago' --no-pager" | grep "<test_id>"
```

**Config inspection:**
```bash
ssh otelcol "sudo python3 -c \"
from pathlib import Path
text = Path('/etc/otel/collector/agent_config.yaml').read_text()
for i, line in enumerate(text.splitlines(), start=1):
    if 197 <= i <= 240: print(f'{i}: {line}')
\""
```

**Config backup convention:** Before editing, create a timestamped backup:
```
/etc/otel/collector/agent_config.yaml.bak-<YYYYMMDDTHHMMSSZ>
```

#### Signal Routing Model (Verified 2026-04-03)

The collector receives OTLP signals from our app via gRPC on port 4317, then routes them to two destinations with no duplication:

| Pipeline | Receivers | Exporters | Destination |
|---|---|---|---|
| `traces` | `jaeger, otlp, zipkin` | `debug, otlphttp, signalfx` | Splunk O11y Cloud |
| `metrics` | `hostmetrics, otlp` | `signalfx, debug` | Splunk O11y Cloud |
| `metrics/internal` | `prometheus/internal` | `signalfx, debug` | Splunk O11y Cloud |
| `logs/signalfx` | `smartagent/processlist` | `signalfx, debug` | Splunk O11y Cloud |
| `logs/entities` | `nop` | `otlphttp/entities` | Splunk O11y Cloud |
| `logs` | `fluentforward, otlp` | `splunk_hec/profiling, splunk_hec/splunk_enterprise` | O11y Profiling + Splunk Enterprise |

Key points:
- `otlphttp` sends traces to `${SPLUNK_INGEST_URL}/v2/trace/otlp` (O11y)
- `signalfx` sends metrics + events + trace correlation to O11y
- `splunk_hec/splunk_enterprise` sends logs to Splunk Enterprise via HEC on port 8099
- `splunk_hec/profiling` sends AlwaysOn Profiling data to O11y (has `log_data_enabled: false` so regular logs are not duplicated)
- Traces and metrics are NOT sent to Splunk Enterprise
- Logs are NOT sent to Splunk O11y (only profiling data goes there via logs pipeline)

**Previous misconfiguration (fixed 2026-04-03):** The `splunk_hec/splunk_enterprise` exporter was initially wired into ALL three main pipelines (traces, metrics, logs). This caused metrics and trace JSON to be indexed into `index=otelcol` alongside logs. The fix removed `splunk_hec/splunk_enterprise` from the `traces` and `metrics` pipelines and removed the default `splunk_hec` exporter from the `logs` pipeline (it pointed to O11y and was producing 404 errors on `/v1/log`).

#### Splunk Enterprise HEC Configuration

| Setting | Value |
|---|---|
| Exporter name in collector config | `splunk_hec/splunk_enterprise` |
| HEC endpoint | `https://eda.israelcentral.cloudapp.azure.com:8099` |
| HEC token | Stored directly in config (should be moved to env var) |
| Target index | `otelcol` |
| Source | `otel` |
| Sourcetype | `otel` |
| TLS | `insecure_skip_verify: true` |

**Splunk Enterprise REST API (search/management):**
- URL: `https://eda.israelcentral.cloudapp.azure.com:8089`
- Auth: basic auth (`admin:<password>`)
- Streaming search (recommended for scripted validation):
  ```bash
  curl -k -sS --connect-timeout 10 --max-time 45 \
    'https://eda.israelcentral.cloudapp.azure.com:8089/services/search/jobs/export' \
    -u 'admin:<password>' \
    --data-urlencode 'search=search index=otelcol earliest=-10m "<test_id>" | fields _time host index sourcetype source _raw | head 20' \
    --data-urlencode 'output_mode=json'
  ```
- Index content summary:
  ```bash
  curl -k -sS ... --data-urlencode 'search=search index=otelcol earliest=-10m | stats count by sourcetype' ...
  ```

**Network ports:**
- `8099` — HEC ingest (HTTPS only; HTTP is refused)
- `8089` — Splunk REST/management API (HTTPS, basic auth)
- Both may require firewall rules to be reachable from local dev machines

### End-to-End Validation Procedures

#### Procedure A: Snowflake SP → Collector → Splunk Enterprise (logs) + O11y (traces/metrics)

1. Generate a unique `test_id` (e.g., `sf_verify_<uuid_hex[:12]>`)
2. Call the deployed diagnostic procedure from Snowflake:
   ```sql
   CALL SPLUNK_OBSERVABILITY_DEV_APP.APP_PUBLIC.test_otlp_export_runtime_with_secret(
     'otelcol.israelcentral.cloudapp.azure.com:4317',
     '<test_id>'
   );
   ```
   Or via Snow CLI:
   ```bash
   PRIVATE_KEY_PASSPHRASE=qwerty123 snow sql -c dev --format JSON_EXT \
     --query "CALL SPLUNK_OBSERVABILITY_DEV_APP.APP_PUBLIC.test_otlp_export_runtime_with_secret('otelcol.israelcentral.cloudapp.azure.com:4317', '<test_id>');"
   ```
3. Verify procedure result JSON shows `span_export=true`, `log_export=true`, `metric_export=true`
4. Verify collector received all three signals:
   ```bash
   ssh otelcol "sudo journalctl -u splunk-otel-collector --since '3 min ago' --no-pager" | grep "<test_id>"
   ```
   Expected: span name `smoke_test/<test_id>`, metric name `smoke_test.gauge.<test_id>`, log body `Smoke test log record: <test_id>`
5. Verify only the log was indexed in Splunk Enterprise:
   ```bash
   curl -k -sS ... 'search=search index=otelcol earliest=-10m "<test_id>" | fields _time sourcetype _raw | head 20' ...
   ```
   Expected: exactly one result with `_raw = Smoke test log record: <test_id>`, no trace JSON, no `metric` entries
6. Verify collector exporter counters confirm the split (optional, for deep debugging):
   ```bash
   ssh otelcol "sudo journalctl -u splunk-otel-collector --since '3 min ago' --no-pager" | grep -A20 "otelcol_exporter_sent_spans"
   ```
   Expected: `otelcol_exporter_sent_spans` shows `debug`, `otlphttp`, `signalfx` only (no `splunk_hec/splunk_enterprise`)

#### Procedure B: Local SP-style → same validation

```bash
PYTHONPATH=app/python .venv/bin/python grpc_test/local_otlp_runtime_smoke_test.py \
  otelcol.israelcentral.cloudapp.azure.com:4317 \
  --pem grpc_test/tls-setup/ca.crt \
  --test-id <test_id>
```
Then follow steps 4-6 from Procedure A.

#### Procedure C: Verify clean index after deletion

After deleting all events from `index=otelcol` via Splunk Enterprise UI, run Procedure A with a fresh `test_id`. Then:
```bash
curl -k -sS ... 'search=search index=otelcol earliest=-10m | stats count values(_raw) as raws by sourcetype' ...
```
Expected: only `sourcetype=otel` with `count=1` and `raws=Smoke test log record: <test_id>`

### OTel SDK Version Compatibility

| Environment | OTel SDK Version | Log Batch Item Type | Log Export Result Type |
|---|---|---|---|
| Snowflake runtime | 1.38.0 | `LogData` | `LogExportResult` |
| Local dev (root venv) | 1.39.1 | `ReadableLogRecord` | `LogRecordExportResult` |

Both `otlp_export.py` and `otlp_export_smoke_test.py` use dynamic imports to handle this:
```python
try:
    from opentelemetry.sdk._logs import ReadableLogRecord as OTelLogBatchItem
except ImportError:
    from opentelemetry.sdk._logs import LogData as OTelLogBatchItem
```

#### Snowflake EAI Approval Workflow

When the OTLP egress network rule (`_internal.otlp_egress_rule`) changes its `HOST_PORTS`, Snowflake increments the external access specification sequence number. This requires manual approval before egress is allowed:

1. Check pending sequence: `SHOW SPECIFICATIONS IN APPLICATION SPLUNK_OBSERVABILITY_DEV_APP;`
2. Approve: `ALTER APPLICATION SPLUNK_OBSERVABILITY_DEV_APP APPROVE SPECIFICATION OTLP_EGRESS_SPEC SEQUENCE_NUMBER = <n>;`
3. Without approval, all three exports return `false` (no error, just failure).

### Previous Story Intelligence

1. **Module import pattern:** All `app/python/` modules use `from __future__ import annotations` and import sibling modules by plain name (e.g., `from endpoint_parse import ...`). This works because Snowflake's `IMPORTS` clause makes them available as top-level modules.

2. **Return JSON pattern:** Existing SP handlers (`connection_test.py`, `cert_validate.py`) return `json.dumps(...)` strings for Streamlit consumption. The diagnostic runtime harness in this story should follow the same pattern. The export module does NOT need JSON — it returns Python objects (bool, enum) since it's called by other Python modules.

3. **No session dependency in pure library code:** `secret_reader.py` takes `_session: Session` as required SP parameter but doesn't use it. The export module should NOT take a session parameter — it's a pure library. The diagnostic handler may take `_session` because it is a stored procedure entrypoint.

4. **`_snowflake` import inside functions:** Following `secret_reader.py` pattern, `import _snowflake` should be a deferred import inside functions, not at module scope (it's only available inside SP sandbox).

5. **Existing endpoint parsing:** `endpoint_parse.py` provides `parse_endpoint(url) → (host, port)` and `host_port_string(host, port) → "host:port"`. Reuse these instead of reimplementing URL parsing.

6. **snowflake.yml artifact list has no wildcard for `app/python/`:** Each Python file must be individually listed. Must add `otlp_export.py` and `otlp_export_smoke_test.py` entries.

7. **Existing local transport assets are canonical:** Reuse `grpc_test/otlp_grpc_probe.py`, `grpc_test/tls-setup/README.md`, and `grpc_test/tls-setup/ca.crt` instead of inventing a new ad hoc TLS probe or collector setup flow.

### Snowpark / SQL Rules Compliance

- This module does NOT execute any SQL or use Snowpark DataFrames directly.
- The diagnostic stored procedures in this story are thin wrappers only; they exist to validate runtime behavior, EAI wiring, secret binding, and cache reuse.
- Epic 5 collectors that use this module will follow BP-1 (pushdown-first), BP-5 (`sql_simplifier_enabled`), and §7.11 (`to_pandas_batches()` pattern).
- The export module is designed to receive pre-shaped batches from collectors — it never reads from Snowflake tables.

### References

- [Source: `_bmad-output/planning-artifacts/splunk_snowflake_native_app_vision.md` — §6.1.1 Batched Export]
- [Source: `_bmad-output/planning-artifacts/splunk_snowflake_native_app_vision.md` — §6.1.2 Retry on Transient Failures]
- [Source: `_bmad-output/planning-artifacts/splunk_snowflake_native_app_vision.md` — §6.2 Export Routing]
- [Source: `_bmad-output/planning-artifacts/splunk_snowflake_native_app_vision.md` — §7.2 Retry Strategy (TLS/PEM)]
- [Source: `_bmad-output/planning-artifacts/splunk_snowflake_native_app_vision.md` — §7.11 Vectorized Transformations]
- [Source: `_bmad-output/planning-artifacts/splunk_snowflake_native_app_vision.md` — §7.12 Snowpark Best Practices BP-2, BP-3]
- [Source: `_bmad-output/planning-artifacts/splunk_snowflake_native_app_vision.md` — §7.13 Data Transformation Optimization]
- [Source: `_bmad-output/planning-artifacts/splunk_snowflake_native_app_vision.md` — §7B Entity Discrimination & OTel Conventions]
- [Source: `_bmad-output/planning-artifacts/otel_semantic_conventions_snowflake_research.md` — Full mapping reference]
- [Source: `_bmad-output/planning-artifacts/python_stored_procedure_best_practices_snowflake_native_app.md` — Python SP runtime checklist for future pipeline stories]
- [Source: `_bmad-output/planning-artifacts/epics.md` — Epic 4, Story 4.1]
- [Source: `app/python/connection_test.py` — gRPC TLS channel + PEM credential pattern]
- [Source: `app/python/secret_reader.py` — `_snowflake.get_generic_secret_string` pattern]
- [Source: `app/python/endpoint_parse.py` — endpoint URL parsing and host:port extraction]
- [Source: `app/setup.sql` — existing Python SP registration pattern, EAI binding, and secret-bound procedures]
- [Source: `app/environment.yml` — opentelemetry-sdk 1.38.0, opentelemetry-exporter-otlp-proto-grpc 1.38.0]
- [Source: `snowflake.yml` — artifact staging, per-file entries for app/python/]
- [Source: `grpc_test/otlp_grpc_probe.py` — canonical local TLS/gRPC transport probe]
- [Source: `grpc_test/tls-setup/README.md` — collector TLS setup and restart flow]
- [Source: `grpc_test/tls-setup/ca.crt` — dev CA fixture for local and Snowflake secret-backed tests]
- [Source: OTel Python SDK v1.38.0 — `OTLPSpanExporter`, `OTLPMetricExporter`, `OTLPLogExporter`, `SpanExportResult`, `MetricExportResult`]
- [Source: Snowflake docs — External Access Integration, Secret API Reference, `_snowflake.get_generic_secret_string`]
- [Source: Cortex CLI — SP sandbox lifecycle: atexit NOT guaranteed, daemon threads killed, module caching best-effort]
- [Source: Cortex CLI — NAT idle timeout 60–350s, keepalive may not be honored, idle-timeout eviction pattern]
- [Source: Cortex CLI — `splunk-opentelemetry` 2.8.0 designed for long-running processes, skip for SP sandbox]
- [Source: Perplexity research — gRPC TCP reset returns UNAVAILABLE, channel auto-reconnects with configurable backoff]
- [Source: Perplexity research — gRPC keepalive options: `keepalive_time_ms`, `keepalive_permit_without_calls`, `initial_reconnect_backoff_ms`]
- [Source: Perplexity research — OTel exporter `export()` thread-safe via internal `threading.Lock()`, spec mandates non-concurrent]
- [Source: Perplexity research — OTel exporter `shutdown()` acquires same lock, recent SDK fixes prevent indefinite hangs]
- [Source: Perplexity research — Snowflake SP: ~284 MB base memory, handlers called from multiple threads, `joblib` over `multiprocessing`]
- [Source: Perplexity research — Snowflake multi-node: each node fresh Python env, no state migration on auto-scale]
- [Source: Snowflake Anaconda channel — all OTel packages confirmed at latest: sdk/exporter 1.38.0, grpcio 1.78.0, protobuf 6.33.5]

## Dev Agent Record

### Agent Model Used

GPT-5.4 (Tasks 1-6), Claude 4.6 Opus (collector reconfiguration, HEC validation, story documentation)

### Debug Log References

**Task 5 — Local integration:**
- Verified TLS transport with `.venv/bin/python grpc_test/otlp_grpc_probe.py otelcol.israelcentral.cloudapp.azure.com:4317 --tls --pem grpc_test/tls-setup/ca.crt --approach b -v` and observed `READY`.
- Ran `.venv/bin/python grpc_test/local_otlp_runtime_smoke_test.py --test-id local_smoke_20260403_a` and received `span_export=true`, `log_export=true`, and `metric_export=true`.
- Verified collector-side arrival over SSH with `journalctl` output filtered by `test.id=local_smoke_20260403_a`; traces, logs, and metrics all appeared in the collector debug exporter output.

**Task 6 — Snowflake runtime:**
- Deployed the app to Snowflake dev, saved the CA PEM in the app-owned secret, and observed that `CALL ...PROVISION_OTLP_EGRESS(...)` returned `needs_approval=true` for `otelcol.israelcentral.cloudapp.azure.com:4317`.
- Approved the pending external access specification with `ALTER APPLICATION SPLUNK_OBSERVABILITY_DEV_APP APPROVE SPECIFICATION OTLP_EGRESS_SPEC SEQUENCE_NUMBER = 1`, after which `CALL ...TEST_OTLP_CONNECTION_WITH_SECRET(...)` returned `success=true`.
- Initial Snowflake runtime attempts failed before approval (`span_export=false`, `log_export=false`, `metric_export=false`) and were accompanied by the expected pending-approval state.
- After approval, two Snowflake-runtime diagnostic calls succeeded for `story4_1_sf_003` and `story4_1_sf_004`, with all three export results returning `true`.
- Verified collector-side arrival for `story4_1_sf_003` and `story4_1_sf_004` after firewall/SSH access was restored. The collector journal showed both `test.id` values, trace spans `smoke_test/story4_1_sf_003` / `smoke_test/story4_1_sf_004`, and matching metric/resource entries.

**HEC integration and signal routing validation:**
- Verified HEC ingest connectivity with `curl -k` to `https://eda.israelcentral.cloudapp.azure.com:8099/services/collector` using the HEC token; received `HTTP 200`.
- Discovered that traces and metrics were being duplicated to Splunk Enterprise (`index=otelcol`); `stats count by sourcetype` showed ~1690 `otel` events including `metric` and trace JSON alongside log records.
- Root cause: the live collector config wired `splunk_hec/splunk_enterprise` into the `traces` and `metrics` pipelines in addition to `logs`.
- Reconfigured the collector (2026-04-03) by removing `splunk_hec/splunk_enterprise` from `traces` and `metrics` pipelines and removing the stale `splunk_hec` exporter from `logs` pipeline. Backup saved as `agent_config.yaml.bak-20260403T165002Z`.
- After clearing `index=otelcol` in Splunk Enterprise, ran fresh Snowflake validation with `test_id=sf_verify_39cdbe43db48`.
- Snowflake procedure returned `span_export=true`, `log_export=true`, `metric_export=true`.
- Splunk Enterprise search for `sf_verify_39cdbe43db48` returned exactly one event: `_raw = Smoke test log record: sf_verify_39cdbe43db48`. No trace or metric data present.
- Collector journal exporter counters confirmed the split: `otelcol_exporter_sent_log_records{exporter="splunk_hec/splunk_enterprise"}=1.0` with zero `sent_spans` and zero `sent_metric_points` for that exporter. Meanwhile `otelcol_exporter_sent_spans{exporter="otlphttp"}` and `signalfx` showed positive values.

### Completion Notes List

**Code quality and compatibility:**
- Re-verified the implementation before Task 5 with `ruff check`, `ruff format --check`, `ReadLints`, the targeted OTLP test files, and the full `tests/` suite; all checks passed.
- Aligned the implementation with the actual installed OTel Python API by pinning the production export module to the Snowflake runtime's log export result type (`LogExportResult`) while keeping local-vs-runtime log-model compatibility shims in the diagnostic smoke harness.
- Replaced the smoke-test metric duck typing with the SDK's real `Metric` type and added exception-path tests for log and metric export failures.

**Local integration (Task 5):**
- Added `grpc_test/local_otlp_runtime_smoke_test.py` as a local SP-style runner that imports the Snowflake diagnostic handler and exercises the same code path against the real collector.
- Local integration validation succeeded end-to-end for the unique marker `local_smoke_20260403_a`, with collector journal evidence for the trace span name, log resource attributes, and metric datapoint.

**Snowflake runtime (Task 6):**
- Real Snowflake runtime export was initially blocked by a pending external access specification approval, not by exporter code or TLS trust. Approval is a required Task 6 step whenever `HOST_PORTS` changes.
- After approval, the secret-backed Snowflake connection test and the diagnostic export procedure both succeeded for traces, logs, and metrics.
- Calling the diagnostic procedure twice in the same `snow sql` invocation did not show exporter reuse: both calls reported `generation_before=0`, `generation_after=1`, and different exporter ids. This indicates Snowflake created a fresh Python sandbox per call in this run, so warm-path reuse was not observed even though the module cache logic remains correct for runtimes that do preserve the sandbox.
- Collector-side verification is now complete for the Snowflake-specific test ids. The trace IDs seen in `otelcol` were `f32dbcb4928b4b8a844e96c79f174fad` for `story4_1_sf_003` and `8d6f298fc26449c8a9a5c87a1c79a67b` for `story4_1_sf_004`.

**Collector routing investigation and reconfiguration (2026-04-03):**
- Initial HEC validation revealed that traces and metrics were being duplicated to Splunk Enterprise in addition to O11y. The `otelcol` index showed ~1690 events across `sourcetype=otel` including raw `metric` strings and trace JSON.
- Root cause: the live collector config at `/etc/otel/collector/agent_config.yaml` listed `splunk_hec/splunk_enterprise` in the `traces`, `metrics`, and `logs` pipeline exporters. The intended design is traces/metrics to O11y only, logs to Splunk Enterprise only.
- Also identified a stale `splunk_hec` exporter (O11y-pointed) in the `logs` pipeline that was producing `HTTP "/v1/log" 404 "Not Found"` errors. O11y does not expose a `/v1/log` endpoint for plain HEC; profiling data uses `splunk_hec/profiling` with `log_data_enabled: false` instead.
- Reconfigured the collector via SSH/`sudo` Python script. Created backup `agent_config.yaml.bak-20260403T165002Z`. New pipeline wiring: `traces=[debug, otlphttp, signalfx]`, `metrics=[signalfx, debug]`, `logs=[splunk_hec/profiling, splunk_hec/splunk_enterprise]`.
- Restarted `splunk-otel-collector` service; verified `is-active` returned `active`.
- After clearing the `otelcol` index in Splunk Enterprise, ran a fresh Snowflake validation with `test_id=sf_verify_39cdbe43db48`.
- Snowflake procedure returned `span_export=true`, `log_export=true`, `metric_export=true`.
- Splunk Enterprise search confirmed exactly one event for the test ID: the log record. No trace or metric data was indexed.
- Collector journal exporter counters provided definitive proof of the split: `otelcol_exporter_sent_log_records{exporter="splunk_hec/splunk_enterprise"}=1.0`, while `sent_spans` and `sent_metric_points` for that exporter showed zero increments. Meanwhile `otlphttp` and `signalfx` correctly processed spans and metrics for O11y.
- The 404 errors from the stale `splunk_hec` exporter stopped after it was removed from the `logs` pipeline.

**Findings for future Epic 5 development:**
- The `otlp_export.py` module is confirmed working end-to-end from both local and Snowflake runtimes. Epic 5 collectors can import it directly.
- The diagnostic smoke test `test_id` marker pattern works for tracing signals from source through the collector to their final destination (O11y or Splunk Enterprise). Future collectors should embed a similar correlation marker.
- For log data specifically, the HEC exporter indexes the entire OTLP log body into `_raw` in Splunk Enterprise. The `sourcetype=otel` and `source=otel` values come from the `splunk_hec/splunk_enterprise` exporter config, not from the OTLP payload attributes. To customize sourcetype/source per signal in production, use the `splunk_hec` exporter's `hec_metadata_to_otel_attrs` mappings or configure multiple named HEC exporters.
- The shared OTLP export module currently uses a fixed 30-second export timeout. If future production collectors need per-environment tuning, add that as an explicit follow-up through the Splunk settings UX rather than broadening this story's MVP surface.
- The collector's `debug` exporter (configured with `verbosity: detailed`) is invaluable for confirming signal receipt before checking downstream destinations. It logs full OTLP payloads to the service journal.
- Splunk Enterprise REST API at port 8089 supports streaming search export (`/services/search/jobs/export`) which is faster for scripted validation than the async job creation + polling pattern.
- Network connectivity between environments requires careful attention: local machine to collector SSH (22), app to collector OTLP (4317), collector to Splunk Enterprise HEC (8099), local machine to Splunk Enterprise REST (8089) are all separate paths with independent firewall rules.

**Post-completion alignment with grpc_research.md (2026-04-06):**
- Updated `_CHANNEL_OPTIONS` to match `grpc_research.md` §5: `initial_reconnect_backoff_ms` 500→100, `max_reconnect_backoff_ms` 10000→1000, added `dns_min_time_between_resolutions_ms`, `max_send_message_length`, `max_receive_message_length`.
- Enabled gzip compression (`grpc.Compression.Gzip`) on all three exporters per `grpc_research.md` §5 compression recommendation.
- Reduced `_EXPORT_TIMEOUT_S` from 30→10 to fit the SP timeout budget (30s total: ~10s query + ~10s export + ~10s safety margin) per `grpc_research.md` §8.
- Added unit test assertion for `compression` and `timeout` parameters passed to exporter constructors.
- Re-validated locally (`grpc_tuning_local_001`) and from Snowflake SP runtime (`grpc_tuning_sf_001`): all three signals (span, log, metric) confirmed at collector with gzip-compressed payloads.

**Post-review fixes and validation closure (2026-04-06):**
- Code review identified two runtime issues in `otlp_export.py`: `_last_used` was only updated in `init_exporters()` rather than on real export activity, and concurrent exporter re-initialization could shut down an exporter while another thread was still inside `export()`.
- Fixed the idle-activity bug by updating cache activity on exporter acquire/release around every export call, so a successful export refreshes the idle timer before the next `init_exporters()` check.
- Fixed the hot-swap race by introducing a condition-protected export reservation model: re-init and explicit close now wait for in-flight exports to finish before calling `shutdown()`, while new exports wait out a reinitialization in progress.
- Added a deterministic stress harness at `grpc_test/otlp_export_concurrency_race_harness.py` to reproduce the race against the real `otlp_export` coordination logic using controlled test doubles.
- Added regression coverage for both discovered issues: `test_recent_export_activity_prevents_idle_recreation`, `test_reinit_waits_for_inflight_export`, and `test_secret_backed_entrypoint_reads_bound_secret`.
- Re-ran the targeted OTLP unit suite after the fixes: `PYTHONPATH=app/python .venv/bin/python -m pytest tests/test_otlp_export.py tests/test_otlp_export_smoke_test.py -v` → `40 passed`.
- Re-ran the deterministic race harness with `--expect not-reproduced`; all 5 iterations avoided the previous failure mode (`reproduced_count=0`, `old_span_shutdown_during_export=false` in every iteration).
- Re-ran the live idle-cache proof against the real collector with `review_local_idle_fixed_20260406_a`; after waiting 56 seconds and exporting successfully, the subsequent `init_exporters()` call kept `generation_after_reinit=1` and preserved the span exporter id, proving warm-cache reuse on recent export activity.
- Re-deployed to Snowflake dev and re-ran the secret-backed runtime smoke with `review_sf_fixed_20260406_a`; `span_export=true`, `log_export=true`, and `metric_export=true`, and collector journal verification confirmed trace and metric arrival for the fixed marker.

### Validated Test IDs (Reference)

| Test ID | Source | Date | Result |
|---|---|---|---|
| `local_smoke_20260403_a` | Local runner | 2026-04-03 | All 3 signals to collector |
| `story4_1_sf_003` | Snowflake SP | 2026-04-03 | All 3 signals to collector (trace ID `f32dbcb4...`) |
| `story4_1_sf_004` | Snowflake SP | 2026-04-03 | All 3 signals to collector (trace ID `8d6f298f...`) |
| `sf_verify_39cdbe43db48` | Snowflake SP | 2026-04-03 | All 3 signals to collector; logs only in Splunk Enterprise |
| `grpc_tuning_local_001` | Local runner | 2026-04-06 | All 3 signals to collector (post gRPC tuning + gzip) |
| `grpc_tuning_sf_001` | Snowflake SP | 2026-04-06 | All 3 signals to collector (post gRPC tuning + gzip) |
| `review_local_idle_fixed_20260406_a` | Local runner | 2026-04-06 | All 3 signals to collector; exporter reused after 56s idle gap following real export activity |
| `review_sf_fixed_20260406_a` | Snowflake SP | 2026-04-06 | All 3 signals to collector after post-review concurrency and idle-cache fixes |

### File List

- `app/environment.yml`
- `app/python/otlp_export.py`
- `app/python/otlp_export_smoke_test.py`
- `app/setup.sql`
- `snowflake.yml`
- `grpc_test/local_otlp_runtime_smoke_test.py`
- `grpc_test/otlp_export_concurrency_race_harness.py`
- `tests/test_otlp_export.py`
- `tests/test_otlp_export_smoke_test.py`

### Senior Developer Review (AI)

- Outcome: approved after fixes
- Initial review found two high-severity runtime issues (`_last_used` not tracking real export activity, and concurrent re-init shutting down exporters during in-flight export), one medium-severity test gap (missing secret-backed entrypoint coverage), and one medium-severity story audit discrepancy (`app/environment.yml` changed but was omitted from the file list).
- All identified high and medium issues were fixed in this story before closure.
- Empirical validation now covers:
  - targeted unit regressions (`40 passed`)
  - deterministic concurrency stress harness (`reproduced_count=0` after fix)
  - live collector proof for idle-cache reuse (`review_local_idle_fixed_20260406_a`)
  - live Snowflake secret-backed smoke validation (`review_sf_fixed_20260406_a`)

### Change Log

- 2026-04-06: Closed code review findings, fixed exporter activity tracking and concurrent re-init coordination, added secret-path and race regressions, added deterministic stress harness, and re-validated locally plus in Snowflake dev.
