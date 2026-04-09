"""Event Table METRIC → OTel MetricsData mapper.

Pure data transformation: receives pre-shaped Pandas DataFrames with the
projected columns from ``telemetry_preparation_for_export.md`` §8.4 and
returns an OTel SDK ``MetricsData`` object.
"""

from __future__ import annotations

import contextlib
import json
import logging
from typing import Any

import pandas as pd
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    Gauge,
    MetricsData,
    NumberDataPoint,
    ResourceMetrics,
    ScopeMetrics,
    Sum,
)
from opentelemetry.sdk.metrics.export import (
    Metric as SdkMetric,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from telemetry_constants import (
    COL_AGGREGATION_TEMPORALITY,
    COL_IS_MONOTONIC,
    COL_METRIC_DESCRIPTION,
    COL_METRIC_NAME,
    COL_METRIC_START_TIME,
    COL_METRIC_TIME,
    COL_METRIC_TYPE,
    COL_METRIC_UNIT,
    COL_METRIC_VALUE,
    COL_RECORD_ATTRIBUTES,
    COL_RESOURCE_ATTRIBUTES,
    COL_VALUE_TYPE,
    DB_NAMESPACE,
    DB_SYSTEM_NAME,
    DB_SYSTEM_SNOWFLAKE,
    DEFAULT_SERVICE_NAME,
    MAPPER_SCOPE_NAME,
    SERVICE_NAME,
    SNOWFLAKE_ACCOUNT_NAME,
    SNOWFLAKE_RECORD_TYPE,
)

log = logging.getLogger(__name__)

_SCOPE = InstrumentationScope(name=MAPPER_SCOPE_NAME)


# ── Helpers ───────────────────────────────────────────────────────


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


def _coerce_number(val: Any, value_type: Any) -> int | float | None:
    if _is_nullish(val):
        return None

    declared_type = (_safe_str(value_type) or "").upper()
    try:
        if declared_type == "INT":
            return int(val)
        if declared_type in {"DOUBLE", "FLOAT"}:
            return float(val)

        if isinstance(val, bool):
            return int(val)
        if isinstance(val, int):
            return val

        with contextlib.suppress(TypeError, ValueError):
            as_int = int(val)
            if str(val).strip() == str(as_int):
                return as_int

        return float(val)
    except (ValueError, TypeError):
        return None


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
    """Add data-point routing fields derived from resource attributes."""
    db = _safe_str(resource_attrs.get("snow.database.name"))
    schema = _safe_str(resource_attrs.get("snow.schema.name"))
    if db and schema:
        attrs[DB_NAMESPACE] = f"{db}|{schema}"
    elif db:
        attrs[DB_NAMESPACE] = db
    elif schema:
        attrs[DB_NAMESPACE] = schema

    attrs[SNOWFLAKE_ACCOUNT_NAME] = account_name


def _resource_key(resource: Resource) -> str:
    """Hashable key for grouping metrics by resource."""
    items = sorted(resource.attributes.items())
    return str(items)


def _parse_temporality(val: Any) -> AggregationTemporality:
    s = _safe_str(val)
    if not s:
        return AggregationTemporality.CUMULATIVE
    upper = s.upper()
    if "DELTA" in upper:
        return AggregationTemporality.DELTA
    return AggregationTemporality.CUMULATIVE


def _parse_bool(val: Any) -> bool:
    if _is_nullish(val):
        return False
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ("true", "1", "yes")


# ── Public API ────────────────────────────────────────────────────


def map_metric_chunk(
    df: pd.DataFrame,
    account_name: str,
) -> MetricsData:
    """Convert pre-shaped METRIC rows to an OTel MetricsData envelope."""
    if df.empty:
        return MetricsData(resource_metrics=[])

    resource_groups: dict[str, tuple[Resource, dict[tuple[Any, ...], dict[str, Any]]]] = {}
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
        rk = _resource_key(resource)

        metric_name = _safe_str(_row_value(row, column_indexes, COL_METRIC_NAME))
        if not metric_name:
            log.warning("Skipping metric row with missing metric_name")
            continue

        metric_type = (
            _safe_str(_row_value(row, column_indexes, COL_METRIC_TYPE)) or ""
        ).lower()
        if metric_type not in ("gauge", "sum"):
            log.warning(
                "Skipping unsupported metric type: %s for %s", metric_type, metric_name
            )
            continue

        metric_desc = _safe_str(_row_value(row, column_indexes, COL_METRIC_DESCRIPTION))
        metric_desc = metric_desc or ""
        metric_unit = _safe_str(_row_value(row, column_indexes, COL_METRIC_UNIT)) or ""

        time_ns = _ts_to_ns(_row_value(row, column_indexes, COL_METRIC_TIME))
        start_time_ns = _ts_to_ns(
            _row_value(row, column_indexes, COL_METRIC_START_TIME)
        )

        dp_attrs: dict[str, Any] = {}
        for k, v in record_attrs.items():
            if not _is_nullish(v):
                dp_attrs[k] = v
        dp_attrs[DB_SYSTEM_NAME] = DB_SYSTEM_SNOWFLAKE
        _enrich_attrs_from_resource(dp_attrs, resource_attrs, account_name)
        dp_attrs[SNOWFLAKE_RECORD_TYPE] = "METRIC"

        value = _coerce_number(
            _row_value(row, column_indexes, COL_METRIC_VALUE),
            _row_value(row, column_indexes, COL_VALUE_TYPE),
        )
        if value is None:
            log.warning("Skipping metric row with invalid metric_value for %s", metric_name)
            continue

        data_point = NumberDataPoint(
            attributes=dp_attrs,
            start_time_unix_nano=start_time_ns,
            time_unix_nano=time_ns,
            value=value,
        )

        temporality = None
        is_monotonic = None
        if metric_type == "gauge":
            metric_key = (metric_name, metric_desc, metric_unit, metric_type)
        else:
            temporality = _parse_temporality(
                _row_value(row, column_indexes, COL_AGGREGATION_TEMPORALITY)
            )
            is_monotonic = _parse_bool(
                _row_value(row, column_indexes, COL_IS_MONOTONIC)
            )
            metric_key = (
                metric_name,
                metric_desc,
                metric_unit,
                metric_type,
                temporality,
                is_monotonic,
            )

        if rk not in resource_groups:
            resource_groups[rk] = (resource, {})

        metric_groups = resource_groups[rk][1]
        if metric_key not in metric_groups:
            metric_groups[metric_key] = {
                "name": metric_name,
                "description": metric_desc,
                "unit": metric_unit,
                "type": metric_type,
                "temporality": temporality,
                "is_monotonic": is_monotonic,
                "data_points": [],
            }
        metric_groups[metric_key]["data_points"].append(data_point)

    resource_metrics_list: list[ResourceMetrics] = []
    for resource, metric_groups in resource_groups.values():
        metrics: list[SdkMetric] = []
        for metric_group in metric_groups.values():
            data_points = metric_group["data_points"]
            if metric_group["type"] == "gauge":
                metric_data = Gauge(data_points=data_points)
            else:
                metric_data = Sum(
                    data_points=data_points,
                    aggregation_temporality=metric_group["temporality"],
                    is_monotonic=metric_group["is_monotonic"],
                )
            metrics.append(
                SdkMetric(
                    name=metric_group["name"],
                    description=metric_group["description"],
                    unit=metric_group["unit"],
                    data=metric_data,
                )
            )
        scope_metrics = ScopeMetrics(scope=_SCOPE, metrics=metrics, schema_url="")
        rm = ResourceMetrics(
            resource=resource,
            scope_metrics=[scope_metrics],
            schema_url="",
        )
        resource_metrics_list.append(rm)

    return MetricsData(resource_metrics=resource_metrics_list)
