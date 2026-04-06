"""Diagnostic runtime harness for OTLP export validation.

Provides two Snowflake stored procedure entrypoints and a ``run_smoke_test``
function that can be called identically from local dev or from within a
Snowflake SP sandbox.  The harness emits uniquely tagged span, log, and
metric batches and returns JSON results with non-secret debug metadata.
"""

from __future__ import annotations

import json
import time
import uuid

import otlp_export
from opentelemetry.sdk.metrics.export import (
    Gauge,
    Metric,
    MetricsData,
    NumberDataPoint,
    ResourceMetrics,
    ScopeMetrics,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.trace import SpanContext, SpanKind, TraceFlags
from opentelemetry.trace.status import Status, StatusCode
from snowflake.snowpark import Session

# This diagnostic harness is imported in both the Snowflake 1.38 runtime and the
# local dev venv, so it keeps the log-model compatibility shims that the
# production-only export module no longer needs.
try:
    from opentelemetry.sdk._logs import ReadableLogRecord as OTelLogBatchItem
    from opentelemetry.sdk._logs._internal import LogRecord as APILogRecord

    _LOG_BATCH_STYLE = "readable"
except ImportError:
    from opentelemetry.sdk._logs import LogData as OTelLogBatchItem
    from opentelemetry.sdk._logs import LogRecord as APILogRecord

    _LOG_BATCH_STYLE = "log_data"

_SCOPE = InstrumentationScope("otlp_export_smoke_test")


def _make_test_span(test_id: str, resource: Resource) -> ReadableSpan:
    """Build a minimal ReadableSpan tagged with *test_id*."""
    ctx = SpanContext(
        trace_id=int(uuid.uuid4().hex[:32], 16),
        span_id=int(uuid.uuid4().hex[:16], 16),
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    return ReadableSpan(
        name=f"smoke_test/{test_id}",
        context=ctx,
        kind=SpanKind.INTERNAL,
        resource=resource,
        instrumentation_scope=_SCOPE,
        attributes={"test.id": test_id, "test.signal": "span"},
        start_time=time.time_ns() - 1_000_000,
        end_time=time.time_ns(),
        status=Status(StatusCode.OK),
    )


def _make_test_log(
    test_id: str,
    resource: Resource,
) -> OTelLogBatchItem:
    """Build a minimal log batch item tagged with *test_id*."""
    common_kwargs = {
        "timestamp": time.time_ns(),
        "observed_timestamp": time.time_ns(),
        "body": f"Smoke test log record: {test_id}",
        "severity_text": "INFO",
        "severity_number": 9,
        "attributes": {"test.id": test_id, "test.signal": "log"},
    }

    if _LOG_BATCH_STYLE == "readable":
        api_record = APILogRecord(**common_kwargs)
        return OTelLogBatchItem(
            log_record=api_record,
            resource=resource,
            instrumentation_scope=_SCOPE,
        )

    api_record = APILogRecord(resource=resource, **common_kwargs)
    return OTelLogBatchItem(
        log_record=api_record,
        instrumentation_scope=_SCOPE,
    )


def _make_test_metrics(test_id: str, resource: Resource) -> MetricsData:
    """Build a minimal MetricsData with one gauge tagged with *test_id*."""
    now_ns = time.time_ns()
    dp = NumberDataPoint(
        attributes={"test.id": test_id, "test.signal": "metric"},
        start_time_unix_nano=now_ns - 1_000_000_000,
        time_unix_nano=now_ns,
        value=1.0,
    )
    gauge = Gauge(data_points=[dp])

    metric_obj = Metric(
        name=f"smoke_test.gauge.{test_id}",
        description="smoke test gauge",
        unit="1",
        data=gauge,
    )

    scope_metrics = ScopeMetrics(
        scope=_SCOPE,
        metrics=[metric_obj],
        schema_url="",
    )
    resource_metrics = ResourceMetrics(
        resource=resource,
        scope_metrics=[scope_metrics],
        schema_url="",
    )
    return MetricsData(resource_metrics=[resource_metrics])


def run_smoke_test(
    endpoint: str,
    pem_cert: str | None = None,
    test_id: str | None = None,
) -> dict:
    """Execute OTLP export smoke test -- callable locally and from SP sandbox.

    Returns a dict with per-signal results and debug metadata.
    """
    if not test_id:
        test_id = f"smoke_{int(time.time())}"

    result: dict[str, object] = {"test_id": test_id, "endpoint": endpoint}

    try:
        snap_before = otlp_export.debug_snapshot()
        otlp_export.init_exporters(endpoint, pem_cert)
        snap_after = otlp_export.debug_snapshot()

        result["generation_before"] = snap_before["generation"]
        result["generation_after"] = snap_after["generation"]
        result["span_exporter_id"] = snap_after["span_exporter_id"]
        result["metric_exporter_id"] = snap_after["metric_exporter_id"]
        result["log_exporter_id"] = snap_after["log_exporter_id"]
    except Exception as exc:
        result["init_error"] = str(exc)
        return result

    resource = Resource.create(
        {"service.name": "otlp_export_smoke_test", "test.id": test_id},
    )

    span = _make_test_span(test_id, resource)
    result["span_export"] = otlp_export.export_spans([span])

    log_record = _make_test_log(test_id, resource)
    result["log_export"] = otlp_export.export_logs([log_record])

    metrics_data = _make_test_metrics(test_id, resource)
    result["metric_export"] = otlp_export.export_metrics(metrics_data)

    result["debug_snapshot"] = otlp_export.debug_snapshot()
    return result


def test_otlp_export_runtime(
    _session: Session,
    endpoint: str,
    cert_pem: str,
    test_id: str,
) -> str:
    """Snowflake SP entrypoint: OTLP export smoke test with caller-provided PEM."""
    pem = cert_pem.strip() if cert_pem else None
    result = run_smoke_test(endpoint, pem, test_id)
    return json.dumps(result, default=str)


def test_otlp_export_runtime_with_secret(
    _session: Session,
    endpoint: str,
    test_id: str,
) -> str:
    """Snowflake SP entrypoint: OTLP export smoke test reading PEM from bound secret."""
    import _snowflake  # pyright: ignore[reportMissingImports]

    pem = _snowflake.get_generic_secret_string("otlp_pem_cert")
    result = run_smoke_test(endpoint, pem or None, test_id)
    return json.dumps(result, default=str)
