"""Reusable OTLP/gRPC export foundation for Snowflake Native App telemetry pipelines.

Provides module-level exporter singletons (span, metric, log) with TLS-only
enforcement, idle-timeout eviction, and thread-safe initialization.  Designed
for direct ``exporter.export()`` calls from stored procedure handlers -- no
BatchSpanProcessor or provider pipelines.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Sequence
from typing import Any

import grpc
from endpoint_parse import host_port_string, parse_endpoint
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs.export import LogExportResult
from opentelemetry.sdk.metrics.export import MetricExportResult, MetricsData
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult

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

_EXPORT_TIMEOUT_S = 10
_EXPORT_COMPRESSION = grpc.Compression.Gzip

# ── Module-level singletons (BP-2) ───────────────────────────────
_init_lock = threading.Lock()
_state_cond = threading.Condition(_init_lock)
_span_exporter: OTLPSpanExporter | None = None
_metric_exporter: OTLPMetricExporter | None = None
_log_exporter: OTLPLogExporter | None = None
_initialized_endpoint: str | None = None
_initialized_pem_fingerprint: str | None = None
_generation: int = 0
_last_used: float = 0.0
_MAX_IDLE_S: int = 55
_active_exports: int = 0
_reinitializing: bool = False


def _pem_fingerprint(pem_cert: str | None) -> str:
    """Compute a short SHA-256 fingerprint of the PEM material."""
    stripped_pem = pem_cert.strip() if pem_cert else ""
    if not stripped_pem:
        return ""
    import hashlib

    return hashlib.sha256(stripped_pem.encode("utf-8")).hexdigest()[:16]


def _build_credentials(pem_cert: str | None) -> grpc.ChannelCredentials:
    """Build TLS channel credentials from default trust store or custom PEM."""
    stripped_pem = pem_cert.strip() if pem_cert else ""
    if stripped_pem:
        return grpc.ssl_channel_credentials(root_certificates=stripped_pem.encode("utf-8"))
    return grpc.ssl_channel_credentials()


def _validate_endpoint(endpoint: str) -> str:
    """Parse endpoint, reject plaintext, return ``host:port`` for gRPC.

    Raises:
        ValueError: For ``http://`` schemes or ``insecure=True`` markers.
    """
    if not endpoint:
        msg = "Endpoint must not be empty"
        raise ValueError(msg)

    lowered = endpoint.strip().lower()
    # Heuristic defense-in-depth against callers accidentally passing a transport
    # flag inside an endpoint-like string; endpoint_parse handles the real parse.
    if lowered.startswith("http://") or "insecure=true" in lowered.replace(" ", ""):
        msg = (
            "Plaintext OTLP transport is not allowed. "
            "Use a TLS-enabled endpoint (https:// or host:port with TLS)."
        )
        raise ValueError(msg)

    host, port = parse_endpoint(endpoint)
    return host_port_string(host, port)


def _build_span_exporter(
    target: str,
    creds: grpc.ChannelCredentials,
) -> OTLPSpanExporter:
    return OTLPSpanExporter(
        endpoint=target,
        credentials=creds,
        insecure=False,
        timeout=_EXPORT_TIMEOUT_S,
        compression=_EXPORT_COMPRESSION,
        channel_options=_CHANNEL_OPTIONS,
    )


def _build_metric_exporter(
    target: str,
    creds: grpc.ChannelCredentials,
) -> OTLPMetricExporter:
    return OTLPMetricExporter(
        endpoint=target,
        credentials=creds,
        insecure=False,
        timeout=_EXPORT_TIMEOUT_S,
        compression=_EXPORT_COMPRESSION,
        channel_options=_CHANNEL_OPTIONS,
    )


def _build_log_exporter(
    target: str,
    creds: grpc.ChannelCredentials,
) -> OTLPLogExporter:
    return OTLPLogExporter(
        endpoint=target,
        credentials=creds,
        insecure=False,
        timeout=_EXPORT_TIMEOUT_S,
        compression=_EXPORT_COMPRESSION,
        channel_options=_CHANNEL_OPTIONS,
    )


def _mark_export_activity_unlocked(now: float | None = None) -> None:
    """Update the last-used timestamp while holding the state lock."""
    global _last_used
    _last_used = now if now is not None else time.monotonic()


def _wait_for_no_active_exports_unlocked() -> None:
    """Block re-init/close until all in-flight exports have finished."""
    while _active_exports > 0:
        _state_cond.wait()


def _acquire_exporter_for_export_unlocked(
    exporter: Any | None,
    signal_name: str,
) -> Any | None:
    """Wait out re-init, then reserve an exporter for one export call."""
    global _active_exports
    while _reinitializing:
        _state_cond.wait()
    if exporter is None:
        log.error("%s called before init_exporters", signal_name)
        return None
    _active_exports += 1
    _mark_export_activity_unlocked()
    return exporter


def _release_exporter_after_export() -> None:
    """Release one in-flight export reservation and notify waiters."""
    global _active_exports
    with _state_cond:
        _active_exports -= 1
        _mark_export_activity_unlocked()
        if _active_exports == 0:
            _state_cond.notify_all()


def init_exporters(endpoint: str, pem_cert: str | None = None) -> None:
    """Initialize or reinitialize exporters for the given endpoint.

    Thread-safe.  Handles idle-timeout eviction and transparent rebuild
    after sandbox recycle.  Called by the SP handler before each export cycle.
    """
    global _span_exporter, _metric_exporter, _log_exporter
    global _initialized_endpoint, _initialized_pem_fingerprint
    global _generation, _reinitializing

    with _state_cond:
        now = time.monotonic()
        target = _validate_endpoint(endpoint)
        fp = _pem_fingerprint(pem_cert)

        needs_init = (
            _span_exporter is None
            or _metric_exporter is None
            or _log_exporter is None
            or _initialized_endpoint != target
            or _initialized_pem_fingerprint != fp
            or (now - _last_used) > _MAX_IDLE_S
        )
        if not needs_init:
            _mark_export_activity_unlocked(now)
            return

        _reinitializing = True
        try:
            _wait_for_no_active_exports_unlocked()
            _close_exporters_unlocked()

            creds = _build_credentials(pem_cert)
            span_exporter = _build_span_exporter(target, creds)
            metric_exporter = _build_metric_exporter(target, creds)
            log_exporter = _build_log_exporter(target, creds)

            _span_exporter = span_exporter
            _metric_exporter = metric_exporter
            _log_exporter = log_exporter
            _initialized_endpoint = target
            _initialized_pem_fingerprint = fp
            _generation += 1
            _mark_export_activity_unlocked(now)
            log.info(
                "Exporters initialized: generation=%d endpoint=%s",
                _generation,
                target,
            )
        finally:
            _reinitializing = False
            _state_cond.notify_all()


def export_spans(batch: Sequence[ReadableSpan]) -> bool:
    """Export a batch of spans.  Returns True on success, False on failure."""
    with _state_cond:
        exporter = _acquire_exporter_for_export_unlocked(_span_exporter, "export_spans")
    if exporter is None:
        return False
    try:
        result = exporter.export(batch)
    except Exception:
        log.exception("export_spans failed")
        return False
    finally:
        _release_exporter_after_export()
    return result == SpanExportResult.SUCCESS


def export_metrics(batch: MetricsData) -> bool:
    """Export a metrics batch.  Returns True on success, False on failure."""
    with _state_cond:
        exporter = _acquire_exporter_for_export_unlocked(
            _metric_exporter,
            "export_metrics",
        )
    if exporter is None:
        return False
    try:
        result = exporter.export(batch)
    except Exception:
        log.exception("export_metrics failed")
        return False
    finally:
        _release_exporter_after_export()
    return result == MetricExportResult.SUCCESS


def export_logs(batch: Sequence[Any]) -> bool:
    """Export a batch of log records.  Returns True on success, False on failure.

    Snowflake's pinned OTel 1.38 runtime supplies `LogData` items here.
    """
    with _state_cond:
        exporter = _acquire_exporter_for_export_unlocked(_log_exporter, "export_logs")
    if exporter is None:
        return False
    try:
        result = exporter.export(batch)
    except Exception:
        log.exception("export_logs failed")
        return False
    finally:
        _release_exporter_after_export()
    # Keep Snowflake's 1.38 import surface fixed, but compare by enum name so the
    # local smoke harness can still recognize SUCCESS on newer OTel versions.
    return getattr(result, "name", None) == LogExportResult.SUCCESS.name


def debug_snapshot() -> dict[str, object]:
    """Return non-secret cache metadata for tests and diagnostic procedures."""
    return {
        "generation": _generation,
        "initialized_endpoint": _initialized_endpoint,
        "pem_fingerprint": _initialized_pem_fingerprint or "",
        "span_exporter_id": id(_span_exporter) if _span_exporter else None,
        "metric_exporter_id": id(_metric_exporter) if _metric_exporter else None,
        "log_exporter_id": id(_log_exporter) if _log_exporter else None,
        "last_used": _last_used,
        "max_idle_s": _MAX_IDLE_S,
        "active_exports": _active_exports,
    }


def close_exporters() -> None:
    """Explicitly close cached exporters.

    Use for idle eviction, endpoint/PEM changes, or diagnostic teardown.
    Do NOT call on the normal successful collector return path.
    """
    global _initialized_endpoint, _initialized_pem_fingerprint
    global _reinitializing

    with _state_cond:
        _reinitializing = True
        try:
            _wait_for_no_active_exports_unlocked()
            _close_exporters_unlocked()
            _initialized_endpoint = None
            _initialized_pem_fingerprint = None
            _mark_export_activity_unlocked(0.0)
        finally:
            _reinitializing = False
            _state_cond.notify_all()


def _close_exporters_unlocked() -> None:
    """Internal: shut down exporters without acquiring ``_init_lock``."""
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
