"""Event Table LOG → OTel log mapper.

Pure data transformation: receives pre-shaped Pandas DataFrames with the
projected columns from ``telemetry_preparation_for_export.md`` §8.3 and
returns OTel SDK log batch items.  Uses ``LogData`` on SDK 1.38.0
(Snowflake runtime) or ``ReadableLogRecord`` on 1.39.1+ (local dev).
"""

from __future__ import annotations

import contextlib
import json
import logging
from typing import Any

import pandas as pd
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.util.instrumentation import InstrumentationScope

# OTel SDK 1.38.0 (Snowflake runtime) exposes LogData + LogRecord directly;
# SDK 1.39.1+ (local dev venv) moved to ReadableLogRecord + LogRecord in _internal.
try:
    from opentelemetry.sdk._logs import ReadableLogRecord as LogBatchItem
    from opentelemetry.sdk._logs._internal import LogRecord as _APILogRecord

    _LOG_BATCH_STYLE = "readable"
except ImportError:
    from opentelemetry.sdk._logs import (
        LogData as LogBatchItem,  # type: ignore[assignment]
    )
    from opentelemetry.sdk._logs import (
        LogRecord as _APILogRecord,  # type: ignore[assignment]
    )

    _LOG_BATCH_STYLE = "log_data"

try:
    from opentelemetry._logs import SeverityNumber
except ImportError:
    from opentelemetry.sdk._logs import (
        SeverityNumber,  # type: ignore[assignment,no-redef]
    )

from telemetry_constants import (
    COL_EXCEPTION_MESSAGE,
    COL_EXCEPTION_STACKTRACE,
    COL_EXCEPTION_TYPE,
    COL_LOG_TIME,
    COL_MESSAGE,
    COL_RECORD_ATTRIBUTES,
    COL_RESOURCE_ATTRIBUTES,
    COL_SCOPE_NAME,
    COL_SEVERITY_NUMBER,
    COL_SEVERITY_TEXT,
    DB_NAMESPACE,
    DB_SYSTEM_NAME,
    DB_SYSTEM_SNOWFLAKE,
    DEFAULT_SERVICE_NAME,
    EXCEPTION_MESSAGE,
    EXCEPTION_STACKTRACE,
    EXCEPTION_TYPE,
    MAPPER_SCOPE_NAME,
    SERVICE_NAME,
    SNOWFLAKE_ACCOUNT_NAME,
    SNOWFLAKE_RECORD_TYPE,
)

log = logging.getLogger(__name__)

_SEVERITY_TEXT_MAP: dict[str, SeverityNumber] = {
    "TRACE": SeverityNumber.TRACE,
    "DEBUG": SeverityNumber.DEBUG,
    "INFO": SeverityNumber.INFO,
    "WARN": SeverityNumber.WARN,
    "WARNING": SeverityNumber.WARN,
    "ERROR": SeverityNumber.ERROR,
    "FATAL": SeverityNumber.FATAL,
}


# ── Helpers (duplicated from span_mapper for module independence) ─


def _is_nullish(val: Any) -> bool:
    if val is None:
        return True
    with contextlib.suppress(TypeError, ValueError):
        return bool(pd.isna(val))
    return False


def _safe_variant(val: Any) -> dict[str, Any]:
    if _is_nullish(val):
        return {}
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _ts_to_ns(ts: Any) -> int:
    if _is_nullish(ts):
        return 0
    if isinstance(ts, pd.Timestamp):
        return int(ts.value)
    if isinstance(ts, str):
        return int(pd.Timestamp(ts, tz="UTC").value)
    if hasattr(ts, "timestamp"):
        return int(ts.timestamp() * 1_000_000_000)
    return 0


def _safe_str(val: Any) -> str | None:
    if _is_nullish(val):
        return None
    s = str(val).strip()
    return s if s else None


def _row_value(
    row: tuple[Any, ...],
    column_indexes: dict[str, int],
    column_name: str,
) -> Any:
    idx = column_indexes.get(column_name)
    return row[idx] if idx is not None else None


def _derive_service_name(resource_attrs: dict[str, Any]) -> str:
    return (
        _safe_str(resource_attrs.get("service.name"))
        or _safe_str(resource_attrs.get("snow.service.name"))
        or _safe_str(resource_attrs.get("snow.application.name"))
        or _safe_str(resource_attrs.get("snow.executable.name"))
        or DEFAULT_SERVICE_NAME
    )


def _filter_nullish_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    """Drop nullish members before handing attrs to OTel Resource."""
    return {k: v for k, v in attrs.items() if not _is_nullish(v)}


def _build_resource(
    row_resource_attrs: dict[str, Any],
    account_name: str,
) -> Resource:
    attrs = _filter_nullish_attrs(row_resource_attrs)

    attrs[DB_SYSTEM_NAME] = DB_SYSTEM_SNOWFLAKE

    db = _safe_str(row_resource_attrs.get("snow.database.name"))
    schema = _safe_str(row_resource_attrs.get("snow.schema.name"))
    if db and schema:
        attrs[DB_NAMESPACE] = f"{db}|{schema}"
    elif db:
        attrs[DB_NAMESPACE] = db
    elif schema:
        attrs[DB_NAMESPACE] = schema

    attrs[SNOWFLAKE_ACCOUNT_NAME] = account_name

    attrs[SERVICE_NAME] = _derive_service_name(row_resource_attrs)
    return Resource(attrs)


def _enrich_attrs_from_resource(
    attrs: dict[str, Any],
    resource_attrs: dict[str, Any],
    account_name: str,
) -> None:
    """Add log-level routing fields derived from resource attributes."""
    db = _safe_str(resource_attrs.get("snow.database.name"))
    schema = _safe_str(resource_attrs.get("snow.schema.name"))
    if db and schema:
        attrs[DB_NAMESPACE] = f"{db}|{schema}"
    elif db:
        attrs[DB_NAMESPACE] = db
    elif schema:
        attrs[DB_NAMESPACE] = schema

    attrs[SNOWFLAKE_ACCOUNT_NAME] = account_name


def _parse_severity(
    severity_number: Any,
    severity_text: str | None,
) -> tuple[SeverityNumber, str | None]:
    """Resolve severity from number or text, with fallback derivation."""
    sn = SeverityNumber.UNSPECIFIED
    text = severity_text

    if severity_number is not None and not (
        isinstance(severity_number, float) and pd.isna(severity_number)
    ):
        with contextlib.suppress(ValueError, TypeError):
            sn = SeverityNumber(int(severity_number))

    if sn == SeverityNumber.UNSPECIFIED and text:
        sn = _SEVERITY_TEXT_MAP.get(text.upper(), SeverityNumber.UNSPECIFIED)

    return sn, text


# ── Public API ────────────────────────────────────────────────────


def map_log_chunk(
    df: pd.DataFrame,
    account_name: str,
) -> list[LogBatchItem]:
    """Convert pre-shaped LOG rows to OTel log batch items.

    Returns ``LogData`` on SDK 1.38.0 (Snowflake runtime) or
    ``ReadableLogRecord`` on SDK 1.39.1+ (local dev venv).  Both types
    are accepted by ``OTLPLogExporter.export()``.
    """
    if df.empty:
        return []

    results: list[LogBatchItem] = []
    column_indexes = {column: idx for idx, column in enumerate(df.columns)}
    resource_cache: dict[tuple[Any, ...], Resource] = {}

    for row in df.itertuples(index=False, name=None):
        record_attrs = _safe_variant(_row_value(row, column_indexes, COL_RECORD_ATTRIBUTES))
        resource_attrs = _safe_variant(
            _row_value(row, column_indexes, COL_RESOURCE_ATTRIBUTES)
        )

        resource_key = (account_name, tuple(sorted(resource_attrs.items())))
        resource = resource_cache.get(resource_key)
        if resource is None:
            resource = _build_resource(resource_attrs, account_name)
            resource_cache[resource_key] = resource

        body = _safe_str(_row_value(row, column_indexes, COL_MESSAGE))
        if not body:
            body = _safe_str(_row_value(row, column_indexes, COL_EXCEPTION_MESSAGE))
            if not body:
                body = _safe_str(record_attrs.get(EXCEPTION_MESSAGE))

        log_attrs: dict[str, Any] = {}
        for k, v in record_attrs.items():
            if not _is_nullish(v):
                log_attrs[k] = v

        log_attrs[DB_SYSTEM_NAME] = DB_SYSTEM_SNOWFLAKE
        _enrich_attrs_from_resource(log_attrs, resource_attrs, account_name)
        log_attrs[SNOWFLAKE_RECORD_TYPE] = "LOG"

        exc_type = _safe_str(_row_value(row, column_indexes, COL_EXCEPTION_TYPE))
        if exc_type:
            log_attrs[EXCEPTION_TYPE] = exc_type
        exc_msg = _safe_str(_row_value(row, column_indexes, COL_EXCEPTION_MESSAGE))
        if exc_msg:
            log_attrs[EXCEPTION_MESSAGE] = exc_msg
        exc_stack = _safe_str(
            _row_value(row, column_indexes, COL_EXCEPTION_STACKTRACE)
        )
        if exc_stack:
            log_attrs[EXCEPTION_STACKTRACE] = exc_stack

        severity_number, severity_text = _parse_severity(
            _row_value(row, column_indexes, COL_SEVERITY_NUMBER),
            _safe_str(_row_value(row, column_indexes, COL_SEVERITY_TEXT)),
        )

        timestamp_ns = _ts_to_ns(_row_value(row, column_indexes, COL_LOG_TIME))

        scope_name = _safe_str(_row_value(row, column_indexes, COL_SCOPE_NAME))
        scope_name = scope_name or MAPPER_SCOPE_NAME
        scope = InstrumentationScope(name=scope_name)

        common_kwargs: dict[str, Any] = {
            "timestamp": timestamp_ns,
            "observed_timestamp": timestamp_ns,
            "severity_number": severity_number,
            "severity_text": severity_text,
            "body": body,
            "attributes": log_attrs,
        }

        if _LOG_BATCH_STYLE == "readable":
            api_record = _APILogRecord(**common_kwargs)
            batch_item = LogBatchItem(
                log_record=api_record,
                resource=resource,
                instrumentation_scope=scope,
            )
        else:
            api_record = _APILogRecord(resource=resource, **common_kwargs)
            batch_item = LogBatchItem(
                log_record=api_record,
                instrumentation_scope=scope,
            )

        results.append(batch_item)

    return results
