"""OTLP operational logging and pipeline health recording helpers.

Callers (Epic 5 collectors and diagnostic harnesses) own the export context
(``pipeline_name``, ``source_name``, ``run_id``) and invoke these helpers
after receiving an ``ExportOutcome`` from ``otlp_export``.

The low-level ``otlp_export.py`` module returns structured outcomes only;
caller-context side effects (structured logs, ``_metrics.pipeline_health``
writes) are handled here per the DRY/SOLID design in Story 4.3.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from typing import TYPE_CHECKING

from export_result import ExportOutcome

if TYPE_CHECKING:
    from snowflake.snowpark import Session

log = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True, slots=True)
class ExportContext:
    """Caller-owned export context for logging and health recording."""

    pipeline_name: str
    source_name: str
    run_id: str


def _build_log_extra(
    context: ExportContext,
    outcome: ExportOutcome,
) -> dict[str, object]:
    """Assemble the structured log ``extra`` dict shared by all log helpers."""
    return {
        "pipeline": context.pipeline_name,
        "source": context.source_name,
        "run_id": context.run_id,
        "signal_type": outcome.signal_type,
        "error_code": outcome.error_code,
        "error_message": outcome.error_message,
        "batch_size": outcome.batch_size,
        "duration_ms": outcome.duration_ms,
        "retryable": outcome.retryable,
    }


def log_terminal_failure(
    context: ExportContext,
    outcome: ExportOutcome,
) -> None:
    """Emit a structured ``logging.error`` for a terminal export failure."""
    log.error(
        "OTLP export terminal failure: %s",
        outcome.error_code,
        extra=_build_log_extra(context, outcome),
    )


def log_export_success(
    context: ExportContext,
    outcome: ExportOutcome,
) -> None:
    """Emit a structured ``logging.info`` for a successful export."""
    log.info(
        "OTLP export success: %s batch_size=%d",
        outcome.signal_type,
        outcome.batch_size,
        extra=_build_log_extra(context, outcome),
    )


_INSERT_SQL = (
    "INSERT INTO _metrics.pipeline_health "
    "(RUN_ID, PIPELINE_NAME, SOURCE_NAME, METRIC_NAME, METRIC_VALUE, METADATA) "
    "SELECT ?, ?, ?, ?, ?, PARSE_JSON(?)"
)


def _build_health_metadata(outcome: ExportOutcome) -> str:
    """Serialize the health INSERT metadata JSON."""
    return json.dumps(
        {
            "error_code": outcome.error_code,
            "error_message": outcome.error_message,
            "signal_type": outcome.signal_type,
            "retryable": outcome.retryable,
            "batch_size": outcome.batch_size,
            "duration_ms": outcome.duration_ms,
        },
    )


def record_batch_failure(
    session: Session,
    pipeline_name: str,
    source_name: str,
    outcome: ExportOutcome,
    run_id: str,
) -> None:
    """INSERT a terminal batch failure row into ``_metrics.pipeline_health``.

    Fails gracefully — logs a warning but does not raise.
    """
    try:
        session.sql(
            _INSERT_SQL,
            params=[
                run_id,
                pipeline_name,
                source_name,
                "rows_failed",
                outcome.batch_size,
                _build_health_metadata(outcome),
            ],
        ).collect()
    except Exception:
        log.warning(
            "Failed to record batch failure in _metrics.pipeline_health",
            exc_info=True,
        )


def record_export_success(
    session: Session,
    pipeline_name: str,
    source_name: str,
    signal_type: str,
    batch_size: int,
    run_id: str,
) -> None:
    """INSERT a successful export row into ``_metrics.pipeline_health``.

    Fails gracefully — logs a warning but does not raise.
    """
    metadata = json.dumps({"signal_type": signal_type})
    try:
        session.sql(
            _INSERT_SQL,
            params=[
                run_id,
                pipeline_name,
                source_name,
                "rows_exported",
                batch_size,
                metadata,
            ],
        ).collect()
    except Exception:
        log.warning(
            "Failed to record export success in _metrics.pipeline_health",
            exc_info=True,
        )
