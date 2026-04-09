"""Event Table SPAN + SPAN_EVENT → OTel ReadableSpan mapper.

Pure data transformation: receives pre-shaped Pandas DataFrames with the
projected columns from ``telemetry_preparation_for_export.md`` §8 and returns
OTel SDK ``ReadableSpan`` objects.  No SQL, no Snowpark, no network calls.
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult  # noqa: F401
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.trace import SpanContext, SpanKind, TraceFlags
from opentelemetry.trace.status import Status, StatusCode
from telemetry_constants import (
    AI_OBS_COST_INPUT_TOKENS,
    AI_OBS_COST_MODEL,
    AI_OBS_COST_OUTPUT_TOKENS,
    AI_OBS_OBJECT_NAME,
    COL_AGENT_NAME,
    COL_DATABASE_NAME,
    COL_END_TIME,
    COL_EVENT_NAME,
    COL_EVENT_TIME,
    COL_EXCEPTION_ESCAPED,
    COL_EXCEPTION_MESSAGE,
    COL_EXCEPTION_STACKTRACE,
    COL_EXCEPTION_TYPE,
    COL_EXEC_NAME,
    COL_EXEC_TYPE,
    COL_PARENT_SPAN_ID,
    COL_RECORD_ATTRIBUTES,
    COL_RESOURCE_ATTRIBUTES,
    COL_SCHEMA_NAME,
    COL_SPAN_ID,
    COL_SPAN_KIND,
    COL_SPAN_NAME,
    COL_SPAN_TYPE,
    COL_START_TIME,
    COL_STATUS_CODE,
    COL_STATUS_MESSAGE,
    COL_TRACE_ID,
    DB_NAMESPACE,
    DB_OPERATION_NAME,
    DB_SYSTEM_NAME,
    DB_SYSTEM_SNOWFLAKE,
    DEFAULT_SERVICE_NAME,
    EXCEPTION_MESSAGE,
    EXCEPTION_STACKTRACE,
    EXCEPTION_TYPE,
    GEN_AI_AGENT_NAME,
    GEN_AI_CONVERSATION_ID,
    GEN_AI_OPERATION_NAME,
    GEN_AI_PROVIDER_NAME,
    GEN_AI_PROVIDER_SNOWFLAKE,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
    MAPPER_SCOPE_NAME,
    SERVICE_NAME,
    SNOWFLAKE_ACCOUNT_NAME,
    SNOWFLAKE_RECORD_TYPE,
    SPAN_KIND_MAP,
    STATUS_CODE_MAP,
)

log = logging.getLogger(__name__)

_SCOPE = InstrumentationScope(name=MAPPER_SCOPE_NAME)

_SQL_EXEC_TYPES = frozenset({"QUERY", "SQL", "STATEMENT"})
_SQL_VERBS = frozenset(
    {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "MERGE",
        "CREATE",
        "ALTER",
        "DROP",
        "TRUNCATE",
        "CALL",
        "COPY",
        "PUT",
        "GET",
        "LIST",
        "REMOVE",
        "DESCRIBE",
        "SHOW",
        "GRANT",
        "REVOKE",
        "USE",
        "SET",
        "UNSET",
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
    }
)


# ── Helpers ───────────────────────────────────────────────────────


def _is_nullish(val: Any) -> bool:
    """Return True for pandas/NumPy null scalars."""
    if val is None:
        return True
    with contextlib.suppress(TypeError, ValueError):
        return bool(pd.isna(val))
    return False


def _safe_variant(val: Any) -> dict[str, Any]:
    """Safely parse VARIANT/OBJECT columns to dict."""
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
    """Convert pd.Timestamp, datetime, or ISO-8601 string to nanoseconds since epoch."""
    if _is_nullish(ts):
        return 0
    if isinstance(ts, pd.Timestamp):
        return int(ts.value)
    if isinstance(ts, str):
        parsed = pd.Timestamp(ts, tz="UTC")
        return int(parsed.value)
    if hasattr(ts, "timestamp"):
        return int(ts.timestamp() * 1_000_000_000)
    return 0


def _safe_str(val: Any) -> str | None:
    """Return non-empty string or None."""
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


def _hex_to_int(hex_str: str | None, _width: int) -> int:
    """Convert hex trace/span ID to int, returning 0 on failure."""
    if _is_nullish(hex_str) or not hex_str:
        return 0
    try:
        return int(str(hex_str).strip(), 16)
    except (ValueError, TypeError):
        return 0


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
    database_name: str | None = None,
    schema_name: str | None = None,
) -> Resource:
    attrs = _filter_nullish_attrs(row_resource_attrs)

    attrs[DB_SYSTEM_NAME] = DB_SYSTEM_SNOWFLAKE

    db = _safe_str(database_name) or _safe_str(row_resource_attrs.get("snow.database.name"))
    schema = _safe_str(schema_name) or _safe_str(row_resource_attrs.get("snow.schema.name"))
    if db and schema:
        attrs[DB_NAMESPACE] = f"{db}|{schema}"
    elif db:
        attrs[DB_NAMESPACE] = db
    elif schema:
        attrs[DB_NAMESPACE] = schema

    attrs[SNOWFLAKE_ACCOUNT_NAME] = account_name

    attrs[SERVICE_NAME] = _derive_service_name(row_resource_attrs)
    return Resource(attrs)


def _parse_span_kind(kind_str: str | None) -> SpanKind:
    if not kind_str:
        return SpanKind.INTERNAL
    code = SPAN_KIND_MAP.get(str(kind_str).strip(), 0)
    return SpanKind(code)


def _parse_status(code_str: str | None, message_str: str | None) -> Status:
    if not code_str:
        return Status(StatusCode.UNSET)
    code_int = STATUS_CODE_MAP.get(str(code_str).strip(), 0)
    sc = StatusCode(code_int)
    desc = _safe_str(message_str) if sc == StatusCode.ERROR else None
    return Status(sc, desc)


def _derive_db_operation_name(
    record_attrs: dict[str, Any],
    exec_type: str | None,
    span_name: str | None,
) -> str | None:
    """Derive db.operation.name per the story's attribution rules."""
    existing = _safe_str(record_attrs.get(DB_OPERATION_NAME))
    if existing:
        return existing

    if not exec_type:
        return None

    upper_exec = exec_type.upper()

    if upper_exec == "PROCEDURE":
        return "CALL"

    if upper_exec in _SQL_EXEC_TYPES:
        return _safe_str(span_name)

    if upper_exec == "FUNCTION":
        if span_name:
            first_word = (
                span_name.strip().split()[0].upper() if span_name.strip() else None
            )
            if first_word and first_word in _SQL_VERBS:
                return first_word
        return None

    return None


def _enrich_span_name(
    original_name: str | None,
    db_op: str | None,
    db_ns: str | None,
    exec_name: str | None,
    exec_type: str | None,
) -> str:
    """Enrich span name per OTel DB client conventions."""
    if (
        exec_type
        and exec_type.upper() in ("PROCEDURE", "FUNCTION")
        and db_op
        and db_ns
        and exec_name
    ):
        return f"{db_op} {db_ns}.{exec_name}"
    return original_name or "unknown"


# ── Public API ────────────────────────────────────────────────────


def map_span_events(df: pd.DataFrame) -> dict[str, list[Any]]:
    """Convert SPAN_EVENT rows into a dict keyed by span_id.

    Returns a mapping of ``span_id`` → ``list[Event]`` for attachment
    to parent spans via ``map_span_chunk(..., span_events_by_span_id=...)``.
    """
    from opentelemetry.sdk.trace import Event

    result: dict[str, list[Event]] = {}

    if df.empty:
        return result

    column_indexes = {column: idx for idx, column in enumerate(df.columns)}

    for row in df.itertuples(index=False, name=None):
        span_id_hex = _safe_str(_row_value(row, column_indexes, COL_SPAN_ID))
        if not span_id_hex:
            continue

        record_attrs = _safe_variant(_row_value(row, column_indexes, COL_RECORD_ATTRIBUTES))
        event_name = _safe_str(_row_value(row, column_indexes, COL_EVENT_NAME))
        event_name = event_name or "unknown"
        event_time_ns = _ts_to_ns(_row_value(row, column_indexes, COL_EVENT_TIME))

        event_attrs: dict[str, Any] = {}
        for k, v in record_attrs.items():
            if not _is_nullish(v):
                event_attrs[k] = v

        exc_type = _safe_str(_row_value(row, column_indexes, COL_EXCEPTION_TYPE))
        if exc_type:
            event_name = "exception"
            event_attrs[EXCEPTION_TYPE] = exc_type
            exc_msg = _safe_str(_row_value(row, column_indexes, COL_EXCEPTION_MESSAGE))
            if exc_msg:
                event_attrs[EXCEPTION_MESSAGE] = exc_msg
            exc_stack = _safe_str(
                _row_value(row, column_indexes, COL_EXCEPTION_STACKTRACE)
            )
            if exc_stack:
                event_attrs[EXCEPTION_STACKTRACE] = exc_stack
            exc_escaped = _row_value(row, column_indexes, COL_EXCEPTION_ESCAPED)
            if not _is_nullish(exc_escaped):
                event_attrs["exception.escaped"] = bool(exc_escaped)

        event_attrs[SNOWFLAKE_RECORD_TYPE] = "SPAN_EVENT"

        evt = Event(
            name=event_name,
            attributes=event_attrs,
            timestamp=event_time_ns,
        )

        result.setdefault(span_id_hex, []).append(evt)

    return result


def map_span_chunk(
    df: pd.DataFrame,
    account_name: str,
    span_events_by_span_id: Mapping[str, Sequence[Any]] | None = None,
) -> list[ReadableSpan]:
    """Convert pre-shaped standard SPAN rows to OTel ReadableSpan objects."""
    if df.empty:
        return []

    spans: list[ReadableSpan] = []
    events_map = span_events_by_span_id or {}
    column_indexes = {column: idx for idx, column in enumerate(df.columns)}
    resource_cache: dict[tuple[Any, ...], Resource] = {}

    for row in df.itertuples(index=False, name=None):
        trace_id_hex = _safe_str(_row_value(row, column_indexes, COL_TRACE_ID))
        span_id_hex = _safe_str(_row_value(row, column_indexes, COL_SPAN_ID))
        if not trace_id_hex or not span_id_hex:
            log.warning("Skipping span row with missing trace_id or span_id")
            continue

        trace_id = _hex_to_int(trace_id_hex, 32)
        span_id = _hex_to_int(span_id_hex, 16)
        if trace_id == 0 or span_id == 0:
            log.warning(
                "Skipping span row with zero trace_id=%s or span_id=%s",
                trace_id_hex,
                span_id_hex,
            )
            continue

        record_attrs = _safe_variant(_row_value(row, column_indexes, COL_RECORD_ATTRIBUTES))
        resource_attrs = _safe_variant(
            _row_value(row, column_indexes, COL_RESOURCE_ATTRIBUTES)
        )

        exec_type = _safe_str(_row_value(row, column_indexes, COL_EXEC_TYPE))
        exec_name = _safe_str(_row_value(row, column_indexes, COL_EXEC_NAME))
        span_name_raw = _safe_str(_row_value(row, column_indexes, COL_SPAN_NAME))
        database_name = _safe_str(_row_value(row, column_indexes, COL_DATABASE_NAME))
        schema_name = _safe_str(_row_value(row, column_indexes, COL_SCHEMA_NAME))

        db_op = _derive_db_operation_name(record_attrs, exec_type, span_name_raw)

        resource_key = (
            account_name,
            database_name,
            schema_name,
            tuple(sorted(resource_attrs.items())),
        )
        resource = resource_cache.get(resource_key)
        if resource is None:
            resource = _build_resource(
                resource_attrs,
                account_name,
                database_name,
                schema_name,
            )
            resource_cache[resource_key] = resource
        db_ns = resource.attributes.get(DB_NAMESPACE)

        enriched_name = _enrich_span_name(
            span_name_raw, db_op, db_ns, exec_name, exec_type
        )

        span_attrs: dict[str, Any] = {}
        for k, v in record_attrs.items():
            if not _is_nullish(v):
                span_attrs[k] = v

        if db_op:
            span_attrs[DB_OPERATION_NAME] = db_op
        span_attrs[SNOWFLAKE_RECORD_TYPE] = "SPAN"

        context = SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            is_remote=False,
            trace_flags=TraceFlags(0x01),
        )

        parent_span_id_hex = _safe_str(
            _row_value(row, column_indexes, COL_PARENT_SPAN_ID)
        )
        parent_ctx: SpanContext | None = None
        if parent_span_id_hex:
            parent_sid = _hex_to_int(parent_span_id_hex, 16)
            if parent_sid:
                parent_ctx = SpanContext(
                    trace_id=trace_id,
                    span_id=parent_sid,
                    is_remote=True,
                    trace_flags=TraceFlags(0x01),
                )

        span_events = list(events_map.get(span_id_hex, []))

        span = ReadableSpan(
            name=enriched_name,
            context=context,
            parent=parent_ctx,
            kind=_parse_span_kind(
                _safe_str(_row_value(row, column_indexes, COL_SPAN_KIND))
            ),
            attributes=span_attrs,
            events=span_events,
            links=[],
            resource=resource,
            instrumentation_scope=_SCOPE,
            start_time=_ts_to_ns(_row_value(row, column_indexes, COL_START_TIME)),
            end_time=_ts_to_ns(_row_value(row, column_indexes, COL_END_TIME)),
            status=_parse_status(
                _safe_str(_row_value(row, column_indexes, COL_STATUS_CODE)),
                _safe_str(_row_value(row, column_indexes, COL_STATUS_MESSAGE)),
            ),
        )
        spans.append(span)

    return spans


def map_ai_observability_span_chunk(
    df: pd.DataFrame,
    account_name: str,
) -> list[ReadableSpan]:
    """Convert pre-shaped AI Observability SPAN rows to ReadableSpan objects."""
    if df.empty:
        return []

    spans: list[ReadableSpan] = []
    column_indexes = {column: idx for idx, column in enumerate(df.columns)}
    resource_cache: dict[tuple[Any, ...], Resource] = {}

    for row in df.itertuples(index=False, name=None):
        trace_id_hex = _safe_str(_row_value(row, column_indexes, COL_TRACE_ID))
        span_id_hex = _safe_str(_row_value(row, column_indexes, COL_SPAN_ID))
        if not trace_id_hex or not span_id_hex:
            log.warning("Skipping AI span row with missing trace_id or span_id")
            continue

        trace_id = _hex_to_int(trace_id_hex, 32)
        span_id = _hex_to_int(span_id_hex, 16)
        if trace_id == 0 or span_id == 0:
            continue

        record_attrs = _safe_variant(_row_value(row, column_indexes, COL_RECORD_ATTRIBUTES))
        resource_attrs = _safe_variant(
            _row_value(row, column_indexes, COL_RESOURCE_ATTRIBUTES)
        )

        resource_key = (account_name, None, None, tuple(sorted(resource_attrs.items())))
        resource = resource_cache.get(resource_key)
        if resource is None:
            resource = _build_resource(resource_attrs, account_name)
            resource_cache[resource_key] = resource

        span_attrs: dict[str, Any] = {}
        for k, v in record_attrs.items():
            if not _is_nullish(v):
                span_attrs[k] = v

        span_attrs[SNOWFLAKE_RECORD_TYPE] = "SPAN"

        # gen_ai.request.model — prefer standard key, fall back to ai.observability
        model = _safe_str(record_attrs.get(GEN_AI_REQUEST_MODEL)) or _safe_str(
            record_attrs.get(AI_OBS_COST_MODEL)
        )
        if model:
            span_attrs[GEN_AI_REQUEST_MODEL] = model

        # gen_ai.usage.input_tokens
        input_tokens = record_attrs.get(GEN_AI_USAGE_INPUT_TOKENS)
        if _is_nullish(input_tokens):
            input_tokens = record_attrs.get(AI_OBS_COST_INPUT_TOKENS)
        if not _is_nullish(input_tokens):
            with contextlib.suppress(ValueError, TypeError):
                span_attrs[GEN_AI_USAGE_INPUT_TOKENS] = int(input_tokens)

        # gen_ai.usage.output_tokens
        output_tokens = record_attrs.get(GEN_AI_USAGE_OUTPUT_TOKENS)
        if _is_nullish(output_tokens):
            output_tokens = record_attrs.get(AI_OBS_COST_OUTPUT_TOKENS)
        if not _is_nullish(output_tokens):
            with contextlib.suppress(ValueError, TypeError):
                span_attrs[GEN_AI_USAGE_OUTPUT_TOKENS] = int(output_tokens)

        # gen_ai.agent.name — from projected column or RECORD_ATTRIBUTES
        agent_name = _safe_str(_row_value(row, column_indexes, COL_AGENT_NAME)) or _safe_str(
            record_attrs.get(AI_OBS_OBJECT_NAME)
        )
        if agent_name:
            span_attrs[GEN_AI_AGENT_NAME] = agent_name

        # gen_ai.conversation.id
        conv_id = _safe_str(record_attrs.get(GEN_AI_CONVERSATION_ID))
        if conv_id:
            span_attrs[GEN_AI_CONVERSATION_ID] = conv_id

        # gen_ai.operation.name — prefer existing, else derive from span_type
        gen_op = _safe_str(record_attrs.get(GEN_AI_OPERATION_NAME))
        if not gen_op:
            span_type = _safe_str(_row_value(row, column_indexes, COL_SPAN_TYPE))
            if span_type:
                lower_type = span_type.lower()
                if lower_type == "generation":
                    gen_op = "chat"
                elif lower_type == "retrieval":
                    gen_op = "retrieval"
                else:
                    gen_op = lower_type
        if gen_op:
            span_attrs[GEN_AI_OPERATION_NAME] = gen_op

        # gen_ai.provider.name — always set to "snowflake" when absent
        if GEN_AI_PROVIDER_NAME not in span_attrs:
            span_attrs[GEN_AI_PROVIDER_NAME] = GEN_AI_PROVIDER_SNOWFLAKE

        # Span naming: "{op} {model}" when both present
        span_name_raw = _safe_str(_row_value(row, column_indexes, COL_SPAN_NAME))
        enriched_name = span_name_raw or "unknown"
        if gen_op and model:
            enriched_name = f"{gen_op} {model}"

        context = SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            is_remote=False,
            trace_flags=TraceFlags(0x01),
        )

        parent_span_id_hex = _safe_str(
            _row_value(row, column_indexes, COL_PARENT_SPAN_ID)
        )
        parent_ctx: SpanContext | None = None
        if parent_span_id_hex:
            parent_sid = _hex_to_int(parent_span_id_hex, 16)
            if parent_sid:
                parent_ctx = SpanContext(
                    trace_id=trace_id,
                    span_id=parent_sid,
                    is_remote=True,
                    trace_flags=TraceFlags(0x01),
                )

        span = ReadableSpan(
            name=enriched_name,
            context=context,
            parent=parent_ctx,
            kind=_parse_span_kind(_safe_str(_row_value(row, column_indexes, COL_SPAN_KIND))),
            attributes=span_attrs,
            events=[],
            links=[],
            resource=resource,
            instrumentation_scope=_SCOPE,
            start_time=_ts_to_ns(_row_value(row, column_indexes, COL_START_TIME)),
            end_time=_ts_to_ns(_row_value(row, column_indexes, COL_END_TIME)),
            status=_parse_status(
                _safe_str(_row_value(row, column_indexes, COL_STATUS_CODE)),
                None,
            ),
        )
        spans.append(span)

    return spans
