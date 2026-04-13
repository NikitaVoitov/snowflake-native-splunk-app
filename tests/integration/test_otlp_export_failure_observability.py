"""Manual live integration test for OTLP retry/failure observability.

Requires:
- a deployed ``SPLUNK_OBSERVABILITY_DEV_APP`` containing the observability smoke SP
- a valid bound PEM secret for the collector certificate
- a temporary collector gRPC outage so the export path fails after internal retry

Run only during the controlled outage window:

    RUN_OTLP_FAILURE_LIVE=1 \
    PYTHONPATH=app/python .venv/bin/python -m pytest \
      tests/integration/test_otlp_export_failure_observability.py -v -m integration
"""

# ruff: noqa: S608

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

import pytest

from .conftest import APP_NAME, _poll_until_result, _snow_sql_json


pytestmark = pytest.mark.integration

DEFAULT_OTLP_ENDPOINT = "otelcol.israelcentral.cloudapp.azure.com:4317"
DEFAULT_MIN_RETRY_DURATION_MS = 2_000
EXPECTED_FAILURE_SIGNALS = {"spans", "logs", "metrics"}


def _require_live_failure_mode() -> None:
    if os.environ.get("RUN_OTLP_FAILURE_LIVE") != "1":
        pytest.skip(
            "Set RUN_OTLP_FAILURE_LIVE=1 before running the controlled outage test",
        )


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")


def _snow_call_json(query: str) -> dict[str, Any]:
    rows = _snow_sql_json(query)
    if len(rows) != 1:
        raise AssertionError(f"Expected one row from CALL result, got {len(rows)}")
    row = rows[0]
    if len(row) != 1:
        raise AssertionError(f"Expected one column from CALL result, got keys={list(row)}")
    value = next(iter(row.values()))
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise AssertionError(
            f"Expected parsed JSON object from CALL result, got {type(value)!r}",
        )
    return value


def _event_log_rows(run_id: str) -> list[dict[str, Any]]:
    sql = f"""
SELECT
    TIMESTAMP AS event_time,
    VALUE::STRING AS message,
    RECORD:"severity_text"::STRING AS severity_text,
    RECORD_ATTRIBUTES:"pipeline"::STRING AS pipeline,
    RECORD_ATTRIBUTES:"source"::STRING AS source,
    RECORD_ATTRIBUTES:"run_id"::STRING AS run_id,
    RECORD_ATTRIBUTES:"signal_type"::STRING AS signal_type,
    RECORD_ATTRIBUTES:"error_code"::STRING AS error_code,
    RECORD_ATTRIBUTES:"error_message"::STRING AS error_message,
    RECORD_ATTRIBUTES:"batch_size"::NUMBER AS batch_size,
    RECORD_ATTRIBUTES:"duration_ms"::NUMBER AS duration_ms,
    RECORD_ATTRIBUTES:"retryable" AS retryable
FROM SNOWFLAKE.TELEMETRY.EVENTS
WHERE RECORD_TYPE = 'LOG'
  AND RESOURCE_ATTRIBUTES:"snow.application.name"::STRING = '{APP_NAME}'
  AND TIMESTAMP >= DATEADD('minute', -30, CURRENT_TIMESTAMP())
  AND RECORD_ATTRIBUTES:"run_id"::STRING = '{_sql_literal(run_id)}'
ORDER BY TIMESTAMP DESC
LIMIT 50
"""
    return _snow_sql_json(sql)


def _health_rows(run_id: str) -> list[dict[str, Any]]:
    sql = f"""
SELECT
    RUN_ID,
    PIPELINE_NAME,
    SOURCE_NAME,
    METRIC_NAME,
    METRIC_VALUE,
    METADATA
FROM {APP_NAME}._METRICS.PIPELINE_HEALTH
WHERE RUN_ID = '{_sql_literal(run_id)}'
ORDER BY RECORDED_AT DESC
"""
    return _snow_sql_json(sql)


class TestOtlpFailureObservability:
    """Verify event-table logs and health rows are produced on terminal export failure."""

    def test_failure_events_and_health_rows_are_recorded(self) -> None:
        _require_live_failure_mode()

        endpoint = os.environ.get("OTLP_TEST_ENDPOINT", DEFAULT_OTLP_ENDPOINT)
        test_id = f"retry_fail_{int(time.time())}_{uuid.uuid4().hex[:6]}"

        result = _snow_call_json(
            "CALL "
            f"{APP_NAME}.APP_PUBLIC.test_otlp_export_observability_with_secret("
            f"'{_sql_literal(endpoint)}', '{_sql_literal(test_id)}')",
        )

        assert result.get("init_error") is None, result.get("init_error")
        assert result["test_id"] == test_id
        assert result["observability_emitted"] is True
        assert result["pipeline_name"] == "otlp_export_observability_smoke"
        assert result["source_name"] == "app_public.test_otlp_export_observability"

        for key in ("span_outcome", "log_outcome", "metric_outcome"):
            assert result[key]["success"] is False, (
                "The controlled outage test expects terminal export failure. "
                "If this returned success, disable the collector gRPC port first."
            )
            assert result[key]["terminal"] is True

        run_id = str(result["run_id"])

        event_rows = _poll_until_result(
            lambda: _event_log_rows(run_id),
            timeout_s=90,
            description=f"event-table log rows for run_id={run_id}",
        )
        failure_rows = [
            row
            for row in event_rows
            if str(row.get("severity_text") or "").upper() == "ERROR"
        ]
        assert failure_rows, "Expected ERROR log rows for terminal export failures"
        assert {
            str(row.get("signal_type"))
            for row in failure_rows
            if row.get("signal_type")
        } == EXPECTED_FAILURE_SIGNALS
        assert all(str(row.get("run_id")) == run_id for row in failure_rows)
        assert all(
            str(row.get("pipeline")) == "otlp_export_observability_smoke"
            for row in failure_rows
        )
        assert all(
            "https://" not in str(row.get("error_message") or "")
            for row in failure_rows
        )

        min_retry_duration_ms = int(
            os.environ.get(
                "OTLP_RETRY_MIN_DURATION_MS",
                str(DEFAULT_MIN_RETRY_DURATION_MS),
            ),
        )
        durations = [
            int(row.get("duration_ms") or 0)
            for row in failure_rows
        ]
        if min_retry_duration_ms > 0:
            assert max(durations) >= min_retry_duration_ms, (
                "Observed failure duration was too short to demonstrate internal retry. "
                "Keep the collector gRPC port disabled and rerun, or lower "
                "OTLP_RETRY_MIN_DURATION_MS if your environment fails faster."
            )

        health_rows = _poll_until_result(
            lambda: _health_rows(run_id),
            timeout_s=90,
            description=f"pipeline_health rows for run_id={run_id}",
        )
        failed_rows = [
            row
            for row in health_rows
            if str(row.get("metric_name")) == "rows_failed"
        ]
        assert len(failed_rows) == 3
        assert {
            str((row.get("metadata") or {}).get("signal_type"))
            for row in failed_rows
        } == EXPECTED_FAILURE_SIGNALS
        assert all(
            "https://" not in str((row.get("metadata") or {}).get("error_message") or "")
            for row in failed_rows
        )
