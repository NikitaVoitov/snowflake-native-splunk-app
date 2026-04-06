# gRPC OTLP Export: Research & Design for Snowflake Stored Procedures

> **Audience:** Developers implementing the OTLP telemetry pipeline (Epic 4/5) in the Splunk Snowflake Native App.
> **Last updated:** 2026-04-06
> **Scope:** Reading Snowflake event table streams and `ACCOUNT_USAGE` views, preparing export-ready OTLP semantic-convention fields inside Snowflake/Snowpark, and exporting them to an OpenTelemetry Collector.
> **Sources:** OTel Python SDK source (GitHub, tag `v1.38.0`), OTel GitHub issues, gRPC documentation (incl. Python-specific performance guide), gRPC performance cross-reference (6 sources, 2026-04-05), Snowflake streams/tasks/view/event-table docs, live Snow CLI validation in account `LFB71918` (2026-04-06), Snowflake SP best practices (project-internal).
> **Companion docs:** `telemetry_preparation_for_export.md` (field schemas, extraction templates, pushdown rules), `event_table_streams_governance_research.md` (stream creation & governance), `event_table_entity_discrimination_strategy.md` (entity filtering).

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [OTLP Python Exporter Behavior (v1.38.0)](#otlp-python-exporter-behavior-v1380)
3. [Design Decision: Direct Synchronous Export Only](#design-decision-direct-synchronous-export-only)
4. [Failure Modes and Mitigations](#failure-modes-and-mitigations)
5. [gRPC Channel Optimization](#grpc-channel-optimization)
6. [Python-Specific gRPC Performance Considerations](#python-specific-grpc-performance-considerations)
7. [Export Cursor Patterns](#export-cursor-patterns)
8. [Timeout Budget](#timeout-budget)
9. [Implementation Checklist](#implementation-checklist)
10. [Appendix: Research Sources](#appendix-research-sources)

---

## Executive Summary

**Primary goal:** Read Snowflake telemetry sources, prepare export-ready OTLP fields inside Snowflake/Snowpark, and export them reliably to an OpenTelemetry Collector.

**Design decision:** Use **direct synchronous `exporter.export(batch)`** calls only. Do **not** add self-instrumentation, `TracerProvider`, `BatchSpanProcessor`, or `force_flush()` to the pipeline design.

Why:
1. The exported customer telemetry is the product requirement; tracing the stored procedure itself is not.
2. Direct export gives a deterministic success/failure result per batch.
3. It removes lifecycle complexity around processors, buffered queues, worker threads, and flush/shutdown behavior.

**Dual-pipeline cursor semantics:**

- **Event Table pipeline (stream-based):** Use a two-phase pattern. Inside one explicit `BEGIN`/`COMMIT` transaction, read the stream snapshot per signal type, materialize export-ready batches, and advance the stream offset via the zero-row INSERT pattern. Perform `exporter.export(batch)` only **after** that transaction commits. This preserves Snowflake stream snapshot semantics while avoiding long-lived stream locks and warehouse time spent waiting on network I/O. In MVP, if export later fails after retries exhaust, the batch is already consumed and the failure is logged to `_metrics.pipeline_health`.
- **ACCOUNT_USAGE pipeline (watermark-based):** On export success, the watermark advances. On export failure, the watermark is held — the same time window replays on the next invocation.

**Operational model:**
- Initialize cached OTLP exporters once per warm runtime.
- Push all filtering, projection, entity discrimination, and semantic-convention mapping into Snowflake/Snowpark. Deduplication is pushed down only for ACCOUNT_USAGE sources (event table streams guarantee uniqueness).
- For event-table streams, separate the **stream snapshot/consume** transaction from the later OTLP export step.
- Fetch already-prepared export batches from Snowflake via `to_pandas_batches()`.
- Perform only the minimal exporter-boundary serialization required by the OTel Python API.
- Call `exporter.export(batch)` synchronously.
- Advance cursors per the dual-pipeline semantics above.
- Rely on exporter timeout plus Snowflake statement timeout as the outer safety guards.

---

## OTLP Python Exporter Behavior (v1.38.0)

### Authoritative Findings

Verified against `open-telemetry/opentelemetry-python` tag `v1.38.0` via GitHub:

1. `OTLPSpanExporter`, `OTLPMetricExporter`, and `OTLPLogExporter` each own their own gRPC client/channel internally.
2. Export is synchronous from the caller's point of view: `export(...)` blocks until success, failure, or timeout.
3. The exporter timeout is configured in **seconds** via constructor parameter `timeout=...`.
4. The generic `OTEL_EXPORTER_OTLP_TIMEOUT` env var handling is still confusing in Python and should not be relied on for millisecond semantics.
5. The exporter contains retry logic within the overall deadline budget.
6. The stock exporter API does **not** accept raw Snowflake rows or pre-rendered SQL strings directly; it expects Python-side SDK/proto input objects.

### What Matters for This Project

For this pipeline, the important contract is:

```python
result = exporter.export(batch)
```

That call is the ACK gate for Snowflake cursor movement. We do not need higher-level provider/processor wiring to achieve the core data flow.

### Consequences

- We should configure timeout explicitly on the exporter constructor.
- We should treat one export call as a bounded blocking operation.
- We should not assume a shared channel across signals; each cached exporter instance owns its own gRPC channel.
- We should optimize around exporter reuse, not provider/processor reuse.
- Snowflake/Snowpark can and should do all business shaping and semantic mapping first.
- With the current stock OTel exporter design, Python still remains the thin transport-boundary serializer. If we ever require literal raw-row-to-wire passthrough with zero Python object assembly, we would need a custom lower-level gRPC/protobuf path instead of the current exporter wrapper.

---

## Design Decision: Direct Synchronous Export Only

### Responsibility Split

| Layer | Responsibilities | Explicitly Not Responsible For |
|---|---|---|
| Snowflake SQL / Snowpark | Filter by `RECORD_TYPE` + entity discrimination, project, extract/cast semi-structured fields, deduplicate (ACCOUNT_USAGE only — event table streams guarantee uniqueness), semantic-convention mapping, chunk shaping, selecting only needed columns, materializing per-signal event-table batches before stream consumption | gRPC transport, retry outcome handling, OTLP network export |
| Python stored procedure | Config lookup, transaction management for stream snapshot + consume, batch iteration via `to_pandas_batches()`, thin exporter-boundary serialization, synchronous `exporter.export(batch)`, stream offset advancement (zero-row INSERT), watermark updates | Relational business logic, semantic enrichment, heavy transforms, filtering, deduplication, joins |

**Rule:** All business/data shaping happens in Snowflake first. Python is a transport adapter, not a transformation engine.

### Pipeline Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ Event Table Collector SP (triggered task)                        │
│                                                                  │
│ 1. BEGIN transaction                                             │
│ 2. Read stream per signal type (SPAN, SPAN_EVENT, LOG, METRIC)  │
│    with RECORD_TYPE + entity discrimination filter               │
│ 3. Materialize temp export batches per signal type              │
│ 4. Zero-row INSERT to advance stream offset                     │
│ 5. COMMIT (atomically advances offset)                          │
│ 6. Export temp batches via synchronous OTLP calls               │
│ 7. On persistent failure after commit: log to pipeline_health   │
│                                                                  │
│ ┌──────────────────────────────────────────────────────────────┐ │
│ │ otlp_export.py — Cached exporter instances                   │ │
│ │                                                              │ │
│ │ • _span_exporter (OTLPSpanExporter)                          │ │
│ │ • _metric_exporter (OTLPMetricExporter)                      │ │
│ │ • _log_exporter (OTLPLogExporter)                            │ │
│ │                                                              │ │
│ │ Lifecycle:                                                   │ │
│ │ • init on first use                                          │ │
│ │ • rebuild on endpoint / PEM change                           │ │
│ │ • idle eviction after warm-runtime inactivity                │ │
│ └──────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ ACCOUNT_USAGE Collector SP (scheduled task)                      │
│                                                                  │
│ 1. Read last watermark from _internal.config                     │
│ 2. Query source with overlap window + lag buffer + QUALIFY dedup │
│ 3. to_pandas_batches() → serialize → exporter.export(batch)     │
│ 4. On success: advance watermark                                 │
│ 5. On failure: hold watermark (same window replays)              │
└──────────────────────────────────────────────────────────────────┘
```

### Explicit Non-Goals

This design intentionally excludes:

- `TracerProvider`
- `BatchSpanProcessor`
- `SimpleSpanProcessor`
- `force_flush()`
- self-instrumentation spans about stored procedure execution

If pipeline observability is needed later, it should be added as a separate story with separate acceptance criteria.

### Why Direct Export Fits the Requirement Best

| Concern | Direct `exporter.export(batch)` |
|---|---|
| Maps to business requirement | Yes |
| Cursor advancement gate | Deterministic |
| Buffered data inside SDK | No |
| Extra flush step required | No |
| SP lifecycle complexity | Minimal |
| Retry behavior | Simple and explicit |

### Pushdown-First Clarification

This document uses **pushdown-first** in the Snowflake sense:

1. Use SQL/Snowpark for all relational work.
2. Shape result sets so they already reflect OTel semantic-convention meaning before Python sees them.
3. Keep Python free of filtering, enrichment, joins, deduplication, windowing, and business rules.

With the current `otlp_export.py` design, Python may still need a very small serialization/binding step because the stock OTel exporters accept SDK/proto objects rather than raw Snowflake rows. That thin API-boundary step is allowed; business transformation in Python is not.

---

## Failure Modes and Mitigations

### 1. Collector Unreachable or Slow

**Root cause:** Network failure, TLS issue, collector outage, or collector backpressure.

**Behavior:** `exporter.export(batch)` blocks until the export succeeds, fails, or the exporter's deadline budget is exhausted.

**Mitigations:**
1. Set constructor timeout explicitly, e.g. `OTLPSpanExporter(timeout=10)`.
2. Keep Snowflake `STATEMENT_TIMEOUT_IN_SECONDS` larger than the exporter timeout.
3. **Event Table pipeline:** Keep OTLP export outside the stream-consumption transaction. On persistent failure after the stream has already been consumed, log the failure to `_metrics.pipeline_health`.
4. **ACCOUNT_USAGE pipeline:** Do not advance the watermark when export returns failure — the same window replays.

### 2. Export Returns Failure After Partial Work in the Exporter

**Impact:** From the stored procedure perspective, the batch is not acknowledged by the collector.

**Mitigation:**
- **Event Table pipeline:** Treat as persistent failure. Advance stream offset to prevent staleness. Log batch metadata (signal type, row count, time range) to `_metrics.pipeline_health` for post-incident replay if needed.
- **ACCOUNT_USAGE pipeline:** Hold watermark. The same window replays on the next invocation, which may produce duplicates at the collector — acceptable under at-least-once semantics.

### 3. Stored Procedure Crashes Before COMMIT (Event Table Pipeline)

**Impact:** The `BEGIN`/`COMMIT` transaction rolls back. Stream offset does not advance. Same rows reappear on next invocation.

**Mitigation:** This is the correct default behavior — the transaction boundary provides automatic rollback safety. No data is lost, and the stream replays the same rows.

### 4. Stored Procedure Crashes After Export but Before Watermark Update (ACCOUNT_USAGE Pipeline)

**Impact:** Replay can produce duplicate OTLP payload delivery.

**Mitigation options:**
1. Accept at-least-once semantics for the initial implementation.
2. Include stable identifiers in exported telemetry where possible (e.g., `QUERY_ID` for QUERY_HISTORY).
3. Minimize the gap between successful export and watermark update.

### 5. Warm Runtime Reuse with Stale Exporters

**Impact:** Idle channels or changed endpoint/PEM material can make cached exporters invalid.

**Mitigation:** Rebuild exporters on:
- idle timeout
- endpoint change
- PEM fingerprint change

This is already the intended lifecycle for `otlp_export.py`.

### 6. Oversized Batch or Payload

**Impact:** Export can fail due to gRPC message limits, memory pressure, or collector-side limits.

**Mitigation:**
1. Bound batch sizes explicitly.
2. Keep `grpc.max_send_message_length` aligned with expected payload size.
3. Prefer many small deterministic batches over one very large batch.

### 7. Stream Staleness (Event Table Pipeline)

**Root cause:** Stream not consumed within `DATA_RETENTION_TIME_IN_DAYS + MAX_DATA_EXTENSION_TIME_IN_DAYS`. Can happen if the triggered task is suspended (e.g., during app upgrade) or the stream has a persistent configuration error.

**Impact:** Stream becomes stale and unrecoverable. All unconsumed data in the stream is lost.

**Mitigations:**
1. Monitor `STALE_AFTER` timestamp via `DESCRIBE STREAM` and surface in health dashboard.
2. Auto-recover: detect stale stream → drop → recreate → record data gap in `_metrics.pipeline_health`.
3. Set `MAX_DATA_EXTENSION_TIME_IN_DAYS` to extend the staleness window during known maintenance periods.

### 8. View Breakage (Consumer Custom View)

**Root cause:** Consumer runs `CREATE OR REPLACE VIEW` instead of `ALTER VIEW` on their custom view over the event table.

**Impact:** All streams on that view become stale and unrecoverable. One-time data gap.

**Mitigations:**
1. Detect via `SHOW STREAMS` stale flag or stream read failure.
2. Mark source as broken in health dashboard.
3. Require consumer to re-select the source to trigger stream recreation.
4. Document this risk clearly in the Streamlit UI.

---

## gRPC Channel Optimization

### Recommended Channel Options

```python
_CHANNEL_OPTIONS: tuple[tuple[str, int | bool], ...] = (
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
```

### Rationale

| Option | Value | Why |
|---|---|---|
| `keepalive_time_ms` | 30000 | Helps warm runtimes survive EAI/NAT idle windows |
| `keepalive_timeout_ms` | 10000 | Detect dead connections quickly |
| `keepalive_permit_without_calls` | 1 | Keep idle exporter-owned channels healthy between invocations |
| `initial_reconnect_backoff_ms` | 100 | Fast first reconnect for short-lived SPs |
| `max_reconnect_backoff_ms` | 1000 | Prevent retry sleeps from consuming the whole SP window |
| `dns_min_time_between_resolutions_ms` | 10000 | Avoid excessive DNS churn |
| `max_send_message_length` | 4 MB | Keeps batch sizing explicit and bounded |
| `max_receive_message_length` | 4 MB | Symmetric limit; sufficient for small export responses |

### Compression

OTLP protobuf payloads benefit from gzip, but not enough to justify heavy compression levels in a short-lived SP. Recommended default:

- `compression=Gzip`
- low/default gzip level

Why:
1. Native support in gRPC Python.
2. Useful network savings for cross-network collector export.
3. No custom codec dependency in Snowflake runtime.

### Latency Model

Indicative export cost:

| Phase | Same Region | Cross Region | Notes |
|---|---|---|---|
| Cold connection setup | 5-12 ms | 75-330 ms | DNS + TCP + TLS + HTTP/2 setup |
| Warm export RPC | 3-12 ms | 31-128 ms | Existing exporter/channel reuse |
| Serialization + gzip | 0.1-5 ms | 0.1-5 ms | Payload dependent |

**Takeaway:** Exporter reuse matters. Cold-start connection cost is real, so cached exporter instances are worth keeping.

---

## Python-Specific gRPC Performance Considerations

Cross-referencing the official gRPC performance guide, community benchmarks, and Python-specific documentation reveals several constraints that specifically validate and inform our design choices.

### Unary RPCs Are Faster Than Streaming in Python

The official gRPC performance guide ([grpc.io/docs/guides/performance](https://grpc.io/docs/guides/performance/)) explicitly warns:

> "Streaming RPCs create extra threads for receiving and possibly sending the messages, which makes **streaming RPCs much slower than unary RPCs** in gRPC Python, unlike the other languages supported by gRPC."

The general gRPC advice to "use streaming RPCs when handling a long-lived logical flow of data" carries a footnote: *"This does not apply to Python."*

**Impact on our design:** Our synchronous unary `exporter.export(batch)` pattern is the **correct** choice for Python gRPC performance. A streaming approach (e.g., opening a long-lived bidirectional stream to the collector) would actively degrade performance due to the per-stream thread overhead in the Python gRPC runtime. Batched unary calls — one RPC per export batch — are strictly faster.

### Avoid the Python gRPC Future API

The official guide also states:

> "Using the future API in the sync stack results in the creation of an extra thread. **Avoid the future API** if possible."

The stock OTel `OTLPSpanExporter._export()` uses synchronous blocking gRPC calls, which is the recommended pattern. Our design inherits this correctly by calling `exporter.export(batch)` synchronously from the SP handler.

### AsyncIO Is Not Suitable for Snowflake SPs

While the gRPC Python guide notes that "using asyncio could improve performance," this is unsuitable for our runtime:

1. **Blocking risk:** Snowpark session calls (`session.sql(...).collect()`) are inherently blocking. Accidentally calling them inside an asyncio event loop would stall the entire coroutine scheduler — worse than synchronous code.
2. **SP sandbox constraints:** Snowflake stored procedures run in a constrained container; the asyncio event loop lifecycle and daemon-thread behavior are unpredictable.
3. **No concurrency benefit:** Our pipeline is sequential by design (query → serialize → export → ACK). There is no I/O overlap to exploit within a single batch iteration.

Multiple sources ([RealPython](https://realpython.com/python-microservices-grpc/), [grpc.io](https://grpc.io/docs/guides/performance/)) confirm that async contexts require extreme care to avoid blocking, and our synchronous design is the safer choice.

### GIL Confirms Serialization as the Optimizable Path

Python's GIL prevents true CPU parallelism within a single process. In our Snowflake SP sandbox:

- Multiprocessing (`SO_REUSEPORT`, `fork`) is unavailable.
- Thread-based parallelism provides no speedup for CPU-bound serialization.
- The gRPC channel's internal I/O threads are the only concurrency, and they run outside the GIL in C extensions.

This means the **Python-side object construction and serialization** (building `ReadableSpan` or protobuf objects from Snowflake rows) is the dominant cost we can control. Network I/O and protobuf binary encoding happen in C-backed code outside the GIL. This supports the serialization optimization tiers documented in our earlier analysis.

### HTTP/2 Flow Control and Batch Sizing

HTTP/2 flow control uses per-connection and per-stream buffer windows ([Microsoft](https://learn.microsoft.com/en-us/aspnet/core/grpc/performance)). If an export RPC payload approaches or exceeds the receiver's buffer window, data transmission switches to start/stop bursts, adding latency.

Our bounded batch sizing (4 MB `max_send_message_length`) and preference for "many small deterministic batches over one very large batch" already mitigate this. Keeping individual export RPCs well below the 4 MB ceiling ensures smooth HTTP/2 flow control.

### Client-Side Interceptors (Future Enhancement)

gRPC Python supports client-side interceptors that can wrap every RPC call ([RealPython](https://realpython.com/python-microservices-grpc/)). A lightweight interceptor could automatically record export health metrics (latency, success/failure counts, batch sizes) into `_metrics.pipeline_health` without modifying the core export code path.

The stock `OTLPSpanExporter` does not expose an easy hook for injecting interceptors into its internal channel. This would require either:
- Creating the gRPC channel externally and passing it to the exporter, or
- Using a custom exporter subclass (aligns with the Tier 2 serialization optimization).

**Status:** Not needed for initial implementation. Logged as a potential enhancement for pipeline observability.

### Summary of Python-Specific Guidance

| Guidance | Source | Our Design |
|---|---|---|
| Unary faster than streaming in Python | [grpc.io](https://grpc.io/docs/guides/performance/) | Unary `export(batch)` — correct |
| Avoid future API in sync stack | [grpc.io](https://grpc.io/docs/guides/performance/) | Synchronous blocking calls — correct |
| AsyncIO risky with blocking callers | [grpc.io](https://grpc.io/docs/guides/performance/), [RealPython](https://realpython.com/python-microservices-grpc/) | Synchronous SP design — correct |
| Reuse channels / stubs always | [grpc.io](https://grpc.io/docs/guides/performance/), [OneUptime](https://oneuptime.com/blog/post/2026-01-24-grpc-performance/view), [RealPython](https://realpython.com/python-microservices-grpc/) | Module-level singletons — correct |
| Keepalive for idle connections | [grpc.io](https://grpc.io/docs/guides/performance/), [Microsoft](https://learn.microsoft.com/en-us/aspnet/core/grpc/performance) | 30s keepalive configured — correct |
| Bounded message sizes | [Microsoft](https://learn.microsoft.com/en-us/aspnet/core/grpc/performance), [Medium](https://medium.com/@dikshant.nagar.mec19/building-scalable-services-with-grpc-and-python-a-practical-guide-e6dd0e41cc12) | 4 MB limit — correct |
| Multi-process for CPU-bound Python | [Medium](https://medium.com/@dikshant.nagar.mec19/building-scalable-services-with-grpc-and-python-a-practical-guide-e6dd0e41cc12) | N/A in Snowflake SP sandbox |

---

## Export Cursor Patterns

### Pattern A: Event Table Stream (Snapshot -> Consume -> Export)

The event table collector runs as a triggered task (`WHEN SYSTEM$STREAM_HAS_DATA()`). Use one explicit transaction for **stream snapshot + materialization + offset advancement**, then export the materialized batches **after** commit.

```python
def run(session):
    session.sql("BEGIN").collect()

    try:
        for signal_type in SIGNAL_EXPORTERS:
            session.sql(f"""
                CREATE OR REPLACE TEMP TABLE TMP_{signal_type} AS
                SELECT ...
                FROM {STREAM_NAME}
                WHERE RECORD_TYPE = '{signal_type}'
                  AND UPPER(RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING)
                      IN ('PROCEDURE', 'FUNCTION', 'QUERY', 'SQL', 'STATEMENT')
            """).collect()

        # Advance stream offset after the snapshot has been materialized.
        session.sql(f"""
            INSERT INTO _staging.stream_offset_log(_OFFSET_CONSUMED_AT)
            SELECT CURRENT_TIMESTAMP() FROM {STREAM_NAME} WHERE 0 = 1
        """).collect()

        session.sql("COMMIT").collect()

    except Exception:
        # If commit never happens, the stream position is preserved.
        session.sql("ROLLBACK").collect()
        raise

    exported_count = 0
    for signal_type, exporter_fn in SIGNAL_EXPORTERS.items():
        df = session.table(f"TMP_{signal_type}")
        for chunk in df.to_pandas_batches():
            batch = serialize_to_otlp(chunk, signal_type)
            result = exporter_fn(batch)
            if result != SUCCESS:
                _log_export_failure(session, signal_type, len(chunk))
            exported_count += len(chunk)

    return f"exported:{exported_count}"
```

**Key design points:**

- **Transaction wraps the stream snapshot only.** `BEGIN` before any stream read, `COMMIT` after temp-batch materialization plus the zero-row INSERT. Within that transaction, all signal-type queries see the same stream snapshot (repeatable read).
- **Export stays outside the transaction.** This avoids holding a stream lock and warehouse resources across blocking OTLP/gRPC I/O.
- **Zero-row INSERT, not data INSERT.** `INSERT INTO _staging.stream_offset_log SELECT ... FROM <stream> WHERE 0 = 1` references the stream (advancing the offset on commit) but writes zero rows. This exact pattern was validated live on 2026-04-06 against a scratch stream and mismatched target table.
- **Best-effort event-table semantics are explicit.** Once the commit succeeds, the event-table batch is consumed. A later export failure is logged but does not replay in MVP.
- **ROLLBACK before COMMIT preserves stream position.** If an unhandled exception occurs before commit, the transaction rolls back and the stream offset stays put — the same data reappears on the next task invocation.
- **Entity discrimination filter.** Every signal-type query includes `RESOURCE_ATTRIBUTES:"snow.executable.type"` as a positive include-list to exclude SPCS/container telemetry.
- **No dedup needed.** Append-only streams guarantee each row appears exactly once.
- **`to_pandas_batches()` at the boundary.** Materialization from the temp batches happens only at the exporter API boundary, keeping memory bounded.

### Pattern B: `ACCOUNT_USAGE` via Timestamp Watermark

`ACCOUNT_USAGE` views do not support streams. Use a watermark with overlap window and dedup.

```python
def run(session):
    watermark = _read_watermark(session, SOURCE_KEY)
    if watermark is None:
        watermark = _bootstrap_start(session, SOURCE_KEY)

    source_config = AU_SOURCE_CONFIGS[SOURCE_KEY]
    upper_bound = _compute_upper_bound(
        session, watermark,
        lag_minutes=source_config.lag_buffer,
    )

    if watermark >= upper_bound:
        return "within_lag_buffer:skip"

    df = session.sql(f"""
        SELECT {source_config.projection}
        FROM {source_config.fqn}
        WHERE {source_config.ts_col} > DATEADD('minute', -{source_config.overlap}, :watermark)
          AND {source_config.ts_col} <= :upper_bound
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY {source_config.natural_key}
            ORDER BY {source_config.ts_col} DESC
        ) = 1
    """)

    exported_count = 0
    for chunk in df.to_pandas_batches():
        batch = serialize_to_otlp(chunk, source_config.signal_type)
        result = source_config.exporter_fn(batch)
        if result != SUCCESS:
            _log_export_failure(session, SOURCE_KEY, len(chunk))
            return f"export_failed:cursor_held_at:{watermark}"
        exported_count += len(chunk)

    _update_watermark(session, SOURCE_KEY, upper_bound)
    return f"exported:{exported_count}"
```

**Key design points:**

- **Overlap window.** Re-scans past the watermark by `source_config.overlap` minutes to catch late-arriving rows. Required because ACCOUNT_USAGE views have significant materialization latency.
- **Lag buffer.** `upper_bound` is `CURRENT_TIMESTAMP() - lag_buffer` to avoid reading rows still being written by Snowflake.
- **QUALIFY dedup.** Mandatory because the overlap window intentionally re-reads rows from previous polls. Uses the source's natural key (e.g., `QUERY_ID` for QUERY_HISTORY).
- **Hold watermark on failure.** Unlike the stream pattern, the watermark does NOT advance on failure — the same window replays. This is safe because ACCOUNT_USAGE views don't have staleness constraints.
- **Source-specific configuration.** Each ACCOUNT_USAGE source has its own timestamp column, natural key, overlap window, and lag buffer (see `telemetry_preparation_for_export.md` Rule AU-3).

### Failure and Retry Behavior

| Scenario | Event Table Stream | `ACCOUNT_USAGE` Watermark |
|---|---|---|
| Export fails (transport) | Stream offset has already advanced; failure logged | Watermark held; same window replays |
| SP crashes before COMMIT | Transaction rolls back; stream replays same rows | Watermark not updated; same window replays |
| Collector backpressure | Batch returns failure after stream commit; failure logged | Batch returns failure; watermark held |
| Crash after COMMIT, before export completes | Stream already consumed; partial or full loss possible in MVP | Watermark not updated; window replays (possible duplicate at collector) |
| Stream becomes stale | Auto-recover: drop → recreate → data gap logged | N/A |
| View breakage (`CREATE OR REPLACE VIEW`) | Stream unrecoverable; requires consumer re-selection | N/A |

---

## Timeout Budget

Example budget:

```
SP wall clock (STATEMENT_TIMEOUT_IN_SECONDS):  30s
├── Query + Snowpark/SQL preparation:          ~10s
├── Direct export call:                        ~5-10s
└── Safety margin:                             ~10-15s
```

### Key Rules

1. The exporter constructor timeout is the real per-call guard:
   - `OTLPSpanExporter(timeout=10)`
2. Do not rely on OTLP timeout environment variables for millisecond precision semantics in Python.
3. Keep Snowflake `STATEMENT_TIMEOUT_IN_SECONDS` above the exporter deadline.
4. Use smaller batches if the query/preparation/export budget becomes too tight.

---

## Implementation Checklist

### Transport Layer
- [ ] Pipeline uses direct synchronous `exporter.export(batch)` only
- [ ] No `TracerProvider`, span processors, or `force_flush()` in the pipeline design
- [ ] Exporter timeout is set explicitly via constructor parameter
- [ ] Cached exporters rebuild on endpoint change, PEM change, or idle eviction
- [ ] gRPC channel options include keepalive and short reconnect backoff
- [ ] gzip compression is enabled
- [ ] Batch sizes are bounded to avoid oversized payloads
- [ ] `STATEMENT_TIMEOUT_IN_SECONDS` is configured as an outer safety guard

### Event Table Pipeline (Stream-Based)
- [ ] All stream reads + temp-batch materialization + offset advancement wrapped in explicit `BEGIN`/`COMMIT`
- [ ] OTLP export runs after the stream transaction commits
- [ ] Zero-row INSERT (`SELECT ... FROM <stream> WHERE 0 = 1`) used for offset advancement
- [ ] Stream offset advances on both success AND persistent failure (pipeline never stalls)
- [ ] Export failures logged to `_metrics.pipeline_health`
- [ ] Transaction rolls back on pre-commit SP crash (stream replays same rows)
- [ ] Entity discrimination filter applied to all stream queries
- [ ] No dedup applied (append-only stream guarantees uniqueness)
- [ ] Separate query per signal type within the same transaction

### ACCOUNT_USAGE Pipeline (Watermark-Based)
- [ ] Watermark advances only after export success
- [ ] Overlap window re-scans past watermark to catch late-arriving rows
- [ ] Lag buffer prevents reading still-materializing rows
- [ ] `QUALIFY ROW_NUMBER()` dedup applied using source-specific natural key
- [ ] Source-specific lag buffers and overlap windows configured per `telemetry_preparation_for_export.md` Rule AU-3

### Pushdown
- [ ] Snowflake/Snowpark performs all filtering, projection, and OTel semantic mapping
- [ ] Python performs no business transformation; only thin exporter-boundary serialization
- [ ] Materialization uses `to_pandas_batches()` at the export boundary

---

## Appendix: Research Sources

### OTel Python SDK / GitHub (Authoritative)

- `OTLPSpanExporter` (`trace_exporter/__init__.py`) at `v1.38.0`
- `OTLPExporterMixin` (`exporter.py`) at `v1.38.0`
- Issue #4044: `OTEL_EXPORTER_OTLP_TIMEOUT` unit mismatch / ambiguity — [link](https://github.com/open-telemetry/opentelemetry-python/issues/4044)
- Issue #4555: OTLP export timeout env/config not doing what users expect — [link](https://github.com/open-telemetry/opentelemetry-python/issues/4555)

### gRPC Documentation

- gRPC Performance Best Practices: [grpc.io/docs/guides/performance](https://grpc.io/docs/guides/performance/) — **Python-specific section** confirms unary > streaming and warns against future API
- gRPC Keepalive Guide: [grpc.io/docs/guides/keepalive](https://grpc.io/docs/guides/keepalive/)
- gRPC Channel Args Reference: [grpc.github.io/grpc/core](https://grpc.github.io/grpc/core/group__grpc__arg__keys.html)
- gRPC Python API Reference: [grpc.github.io/grpc/python](https://grpc.github.io/grpc/python/grpc.html)

### gRPC Performance Cross-Reference Sources (2026-04-05)

- OneUptime: [How to Fix gRPC Performance Issues](https://oneuptime.com/blog/post/2026-01-24-grpc-performance/view) — connection management, keepalive patterns
- Microsoft: [ASP.NET Core gRPC Performance](https://learn.microsoft.com/en-us/aspnet/core/grpc/performance) — HTTP/2 flow control, binary payload optimization concepts
- Medium / dk_underline: [Building Scalable Services with gRPC and Python](https://medium.com/@dikshant.nagar.mec19/building-scalable-services-with-grpc-and-python-a-practical-guide-e6dd0e41cc12) — Python multiprocessing patterns, GIL constraints
- ByteSizeGo: [How to Use gRPC Effectively](https://www.bytesizego.com/blog/effective-grpc-usage-go) — message size optimization, connection reuse (Go-focused, concepts transfer)
- RealPython: [Python Microservices With gRPC](https://realpython.com/python-microservices-grpc/) — client-side interceptors, asyncio warnings, channel lifecycle

### Snowflake / Project-Internal Guidance

- `_bmad-output/planning-artifacts/python_stored_procedure_best_practices_snowflake_native_app.md`
- `_bmad-output/planning-artifacts/telemetry_preparation_for_export.md` — field schemas, extraction templates, pushdown rules
- `_bmad-output/planning-artifacts/event_table_streams_governance_research.md` — stream creation, governance, staleness
- `_bmad-output/planning-artifacts/event_table_entity_discrimination_strategy.md` — entity filtering design

### Community / Secondary Sources

- gRPC vs HTTP/2 OTLP benchmark notes
- Compression comparisons for gzip vs alternatives

> Secondary sources were used only to estimate latency and compression tradeoffs. Source-of-truth behavior comes from GitHub-tagged OTel Python code and issues. The gRPC performance cross-reference sources (2026-04-05) were used to validate design choices against industry best practices.
