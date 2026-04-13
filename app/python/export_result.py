"""Structured export outcome, upstream status classification, and batch-size helpers.

Provides ``ExportOutcome`` — a frozen dataclass that wraps the result of an
OTLP export call.  The upstream ``opentelemetry-python`` OTLP gRPC exporter's
retry set is mirrored exactly so that directly surfaced gRPC status codes are
classified consistently with the SDK's internal behaviour.
"""

from __future__ import annotations

import dataclasses
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    import grpc

_MAX_ERROR_MESSAGE_LEN = 512

UPSTREAM_RETRYABLE_GRPC_CODES: frozenset[str] = frozenset(
    {
        "CANCELLED",
        "DEADLINE_EXCEEDED",
        "RESOURCE_EXHAUSTED",
        "ABORTED",
        "OUT_OF_RANGE",
        "UNAVAILABLE",
        "DATA_LOSS",
    }
)

_PEM_BLOCK_RE = re.compile(
    r"-----BEGIN[^-]*-----[\s\S]*?-----END[^-]*-----",
    re.DOTALL,
)
_URL_CRED_RE = re.compile(r"://[^@/\s]+@")
_AUTH_HEADER_RE = re.compile(
    r"(Authorization\s*:\s*(?:Bearer\s+)?|Bearer\s+)\S+",
    re.IGNORECASE,
)
_FULL_URL_RE = re.compile(r"https?://\S+")
_HIDDEN_STATUS_TYPEERROR_FRAGMENT = "cannot unpack non-iterable bool object"


def _sanitize_error_message(msg: str | None) -> str | None:
    """Strip potential secret material before recording."""
    if not msg:
        return msg
    cleaned = _PEM_BLOCK_RE.sub("[PEM-REDACTED]", msg)
    cleaned = _URL_CRED_RE.sub("://[REDACTED]@", cleaned)
    cleaned = _AUTH_HEADER_RE.sub("[AUTH-REDACTED]", cleaned)
    cleaned = _FULL_URL_RE.sub("[URL-REDACTED]", cleaned)
    if len(cleaned) > _MAX_ERROR_MESSAGE_LEN:
        cleaned = cleaned[:_MAX_ERROR_MESSAGE_LEN] + "..."
    return cleaned


def sanitize_error_message(msg: str | None) -> str | None:
    """Public wrapper for secret-safe error-message sanitisation."""
    return _sanitize_error_message(msg)


def count_metric_data_points(metrics_data: Any) -> int:
    """Count total metric data points across all ResourceMetrics."""
    total = 0
    for rm in getattr(metrics_data, "resource_metrics", ()):
        for sm in getattr(rm, "scope_metrics", ()):
            for metric in getattr(sm, "metrics", ()):
                data = getattr(metric, "data", None)
                if data is not None:
                    total += len(getattr(data, "data_points", ()))
    return total


def count_sequence_batch(batch: Sequence[Any] | None) -> int:
    """Count items in a span or log sequence batch."""
    if batch is None:
        return 0
    return len(batch)


@dataclasses.dataclass(frozen=True, slots=True)
class ExportOutcome:
    """Structured result of an OTLP export attempt."""

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

    def to_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)

    @staticmethod
    def success_result(
        signal_type: str,
        batch_size: int,
        duration_ms: int,
    ) -> ExportOutcome:
        return ExportOutcome(
            success=True,
            terminal=False,
            signal_type=signal_type,
            batch_size=batch_size,
            duration_ms=duration_ms,
        )

    @staticmethod
    def noop_result(signal_type: str) -> ExportOutcome:
        return ExportOutcome(
            success=True,
            terminal=False,
            signal_type=signal_type,
            batch_size=0,
            duration_ms=0,
        )

    @staticmethod
    def not_initialized(signal_type: str) -> ExportOutcome:
        return ExportOutcome(
            success=False,
            terminal=True,
            signal_type=signal_type,
            error_message="Exporter not initialized; call init_exporters() first",
        )


def classify_grpc_status(
    status_code: grpc.StatusCode,
    error_details: str | None,
    signal_type: str,
    batch_size: int,
    duration_ms: int,
) -> ExportOutcome:
    """Classify a directly surfaced gRPC status code."""
    code_name = status_code.name
    retryable = code_name in UPSTREAM_RETRYABLE_GRPC_CODES
    return ExportOutcome(
        success=False,
        terminal=True,
        error_code=code_name,
        error_message=_sanitize_error_message(
            f"gRPC {code_name}: {error_details}" if error_details else f"gRPC {code_name}"
        ),
        signal_type=signal_type,
        batch_size=batch_size,
        retryable=retryable,
        duration_ms=duration_ms,
    )


def classify_export_failure_without_status(
    signal_type: str,
    batch_size: int,
    duration_ms: int,
) -> ExportOutcome:
    """Classify the main 4.1 failure mode: public exporter returned FAILURE
    with no surfaced gRPC status."""
    return ExportOutcome(
        success=False,
        terminal=True,
        error_code="FAILURE",
        error_message=(
            "Public exporter returned FAILURE without exposing "
            "the underlying gRPC status code"
        ),
        signal_type=signal_type,
        batch_size=batch_size,
        retryable=None,
        duration_ms=duration_ms,
    )


def classify_export_failure_without_status_exception(
    exc: Exception,
    signal_type: str,
    batch_size: int,
    duration_ms: int,
) -> ExportOutcome | None:
    """Normalize public-exporter internal failures that hide the gRPC status.

    In live outage testing, the upstream OTLP Python exporter sometimes raises a
    ``TypeError`` from inside its retry/error-handling path instead of returning
    ``FAILURE`` or surfacing a ``grpc.RpcError``. Treat that as the same
    hidden-status terminal failure bucket.
    """
    summary = f"{type(exc).__name__}: {exc}"
    if _HIDDEN_STATUS_TYPEERROR_FRAGMENT not in summary:
        return None
    sanitized_summary = _sanitize_error_message(summary)
    return ExportOutcome(
        success=False,
        terminal=True,
        error_code="FAILURE",
        error_message=(
            "Public exporter failed before exposing the underlying gRPC "
            f"status code ({sanitized_summary})"
        ),
        signal_type=signal_type,
        batch_size=batch_size,
        retryable=None,
        duration_ms=duration_ms,
    )


def classify_unexpected_exception(
    exc: Exception,
    signal_type: str,
    batch_size: int,
    duration_ms: int,
) -> ExportOutcome:
    """Classify a non-gRPC exception from outside the public exporter path."""
    return ExportOutcome(
        success=False,
        terminal=True,
        error_code=type(exc).__name__,
        error_message=_sanitize_error_message(
            f"{type(exc).__name__}: {exc}"
        ),
        signal_type=signal_type,
        batch_size=batch_size,
        retryable=None,
        duration_ms=duration_ms,
    )
