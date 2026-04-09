"""Integration tests: Event Table → mappers → OTel objects → OTLP export.

Requires a deployed SPLUNK_OBSERVABILITY_DEV_APP with the telemetry test
generators registered.  Run with:

    SPLUNK_ENTERPRISE_PASSWORD=... \
    PYTHONPATH=app/python .venv/bin/python -m pytest tests/integration/ -v -m integration

Set `SPLUNK_ACCESS_TOKEN` and `SPLUNK_REALM` to enable the live Splunk
Observability REST assertions for metric metadata, raw MTS, and trace retrieval.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from log_mapper import map_log_chunk
from metric_mapper import map_metric_chunk
from otlp_export import (
    close_exporters,
    export_logs,
    export_metrics,
    export_spans,
    init_exporters,
)
from span_mapper import map_span_chunk, map_span_events
from telemetry_constants import (
    DB_SYSTEM_NAME,
    EXCEPTION_MESSAGE,
    EXCEPTION_TYPE,
    SERVICE_NAME,
    SNOWFLAKE_ACCOUNT_NAME,
    SNOWFLAKE_RECORD_TYPE,
)

from .conftest import (
    ACCOUNT_NAME,
    _collector_trace_excerpt,
    _normalize_hex_id,
    _o11y_trace_spans,
    _parse_collector_trace_spans,
    _poll_until_result,
)


pytestmark = pytest.mark.integration

YEAR_2020_NS = 1_577_836_800_000_000_000
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OTLP_ENDPOINT = "otelcol.israelcentral.cloudapp.azure.com:4317"
DEFAULT_OTLP_CA_PATH = PROJECT_ROOT / "grpc_test" / "tls-setup" / "ca.crt"


def _get_resource(batch_item: Any) -> Any:
    """Extract resource from either LogData (1.38) or ReadableLogRecord (1.39+)."""
    if hasattr(batch_item, "resource"):
        return batch_item.resource
    return batch_item.log_record.resource


def _export_live_telemetry(
    *,
    spans_df: pd.DataFrame,
    span_events_df: pd.DataFrame,
    logs_df: pd.DataFrame,
    metrics_df: pd.DataFrame,
) -> dict[str, bool | None]:
    """Export mapped telemetry to the live dev collector and return success flags."""
    endpoint = os.environ.get("OTLP_TEST_ENDPOINT", DEFAULT_OTLP_ENDPOINT)
    pem_path = Path(os.environ.get("OTLP_TEST_CA_CERT_PATH", str(DEFAULT_OTLP_CA_PATH)))
    if not pem_path.exists():
        pytest.fail(f"Collector CA PEM not found: {pem_path}")

    pem_text = pem_path.read_text(encoding="utf-8")
    events_by_span = map_span_events(span_events_df)
    spans = map_span_chunk(spans_df, ACCOUNT_NAME, events_by_span)
    logs = map_log_chunk(logs_df, ACCOUNT_NAME)
    metrics = map_metric_chunk(metrics_df, ACCOUNT_NAME)

    close_exporters()
    init_exporters(endpoint, pem_text)
    try:
        results: dict[str, bool | None] = {
            "span_export": export_spans(spans),
            "log_export": export_logs(logs),
            "metric_export": None,
        }
        if metrics.resource_metrics:
            results["metric_export"] = export_metrics(metrics)
        return results
    finally:
        close_exporters()


@pytest.fixture(scope="module")
def live_export_results(
    spans_df: pd.DataFrame,
    span_events_df: pd.DataFrame,
    logs_df: pd.DataFrame,
    metrics_df: pd.DataFrame,
) -> dict[str, bool | None]:
    return _export_live_telemetry(
        spans_df=spans_df,
        span_events_df=span_events_df,
        logs_df=logs_df,
        metrics_df=metrics_df,
    )


@pytest.fixture(scope="module")
def rich_live_export_results(
    rich_spans_df: pd.DataFrame,
    rich_span_events_df: pd.DataFrame,
    rich_logs_df: pd.DataFrame,
    rich_metrics_df: pd.DataFrame,
) -> dict[str, bool | None]:
    return _export_live_telemetry(
        spans_df=rich_spans_df,
        span_events_df=rich_span_events_df,
        logs_df=rich_logs_df,
        metrics_df=rich_metrics_df,
    )


@pytest.fixture(scope="module")
def rich_trace_export_summary(
    rich_live_export_results: dict[str, bool | None],
    rich_target_trace_df: pd.DataFrame,
    rich_target_trace_id: str,
    wait_for_rich_event_table: str,
    o11y_access: dict[str, str],
) -> dict[str, Any]:
    """Export the rich trace scenario and verify it in collector + O11y."""
    del o11y_access
    assert rich_live_export_results["span_export"] is True
    assert rich_live_export_results["log_export"] is True

    snowflake_ids = {
        _normalize_hex_id(str(value))
        for value in rich_target_trace_df["span_id"].dropna().tolist()
    }

    collector_spans = _poll_until_result(
        lambda: (
            parsed := (
                (excerpt := _collector_trace_excerpt(rich_target_trace_id))
                and _parse_collector_trace_spans(
                    excerpt,
                    trace_id=rich_target_trace_id,
                )
            )
        )
        and {
            _normalize_hex_id(item.get("span_id"))
            for item in parsed
            if item.get("span_id")
        }
        == snowflake_ids
        and parsed,
        timeout_s=180,
        description=(
            "collector trace for "
            f"test_id={wait_for_rich_event_table} trace_id={rich_target_trace_id}"
        ),
    )

    o11y_spans = _poll_until_result(
        lambda: (
            spans := _o11y_trace_spans(rich_target_trace_id)
        )
        and {
            _normalize_hex_id(item.get("spanId"))
            for item in spans
            if item.get("spanId")
        }
        == snowflake_ids
        and spans,
        timeout_s=420,
        description=(
            "Splunk O11y rich trace for "
            f"test_id={wait_for_rich_event_table} trace_id={rich_target_trace_id}"
        ),
    )

    collector_ids = {
        _normalize_hex_id(item.get("span_id"))
        for item in collector_spans
        if item.get("span_id")
    }
    o11y_ids = {
        _normalize_hex_id(item.get("spanId"))
        for item in o11y_spans
        if item.get("spanId")
    }

    return {
        "test_id": wait_for_rich_event_table,
        "trace_id": rich_target_trace_id,
        "snowflake_span_count": len(snowflake_ids),
        "collector_span_count": len(collector_ids),
        "o11y_span_count": len(o11y_ids),
        "snowflake_equals_collector": snowflake_ids == collector_ids,
        "snowflake_equals_o11y": snowflake_ids == o11y_ids,
        "collector_equals_o11y": collector_ids == o11y_ids,
        "collector_spans": collector_spans,
        "o11y_spans": o11y_spans,
    }


@pytest.mark.integration_foundation
class TestSpanMapping:
    """Verify SPAN extraction → map_span_chunk produces valid OTel ReadableSpans."""

    def test_span_count_minimum(self, spans_df: pd.DataFrame) -> None:
        assert not spans_df.empty, "No SPAN rows extracted from Event Table"
        spans = map_span_chunk(spans_df, ACCOUNT_NAME)
        assert len(spans) >= 2, f"Expected ≥2 spans, got {len(spans)}"

    def test_db_system_attribute(self, spans_df: pd.DataFrame) -> None:
        spans = map_span_chunk(spans_df, ACCOUNT_NAME)
        for s in spans:
            assert s.resource.attributes.get(DB_SYSTEM_NAME) == "snowflake"
            assert s.attributes.get(DB_SYSTEM_NAME) is None

    def test_account_name_attribute(self, spans_df: pd.DataFrame) -> None:
        spans = map_span_chunk(spans_df, ACCOUNT_NAME)
        for s in spans:
            assert s.resource.attributes.get(SNOWFLAKE_ACCOUNT_NAME) == ACCOUNT_NAME
            assert s.attributes.get(SNOWFLAKE_ACCOUNT_NAME) is None

    def test_record_type_attribute(self, spans_df: pd.DataFrame) -> None:
        spans = map_span_chunk(spans_df, ACCOUNT_NAME)
        for s in spans:
            assert s.attributes.get(SNOWFLAKE_RECORD_TYPE) == "SPAN"

    def test_resource_contains_live_snow_attributes(
        self, spans_df: pd.DataFrame
    ) -> None:
        spans = map_span_chunk(spans_df, ACCOUNT_NAME)
        first = spans[0]
        res = first.resource.attributes
        assert res.get("snow.executable.type") or res.get(SERVICE_NAME)
        assert res.get("snow.warehouse.name") or res.get("snow.database.name")

    def test_valid_trace_and_span_ids(self, spans_df: pd.DataFrame) -> None:
        spans = map_span_chunk(spans_df, ACCOUNT_NAME)
        for s in spans:
            assert s.context.trace_id != 0
            assert s.context.span_id != 0

    def test_timestamps_are_valid_epoch_ns(self, spans_df: pd.DataFrame) -> None:
        spans = map_span_chunk(spans_df, ACCOUNT_NAME)
        now_ns = time.time_ns()
        for s in spans:
            assert s.start_time > YEAR_2020_NS
            assert s.end_time > YEAR_2020_NS
            assert s.end_time <= now_ns
            assert s.end_time >= s.start_time


@pytest.mark.integration_foundation
class TestSpanEventMapping:
    """Verify SPAN_EVENT extraction → map_span_events → event attachment."""

    def test_non_exception_event_present(
        self,
        spans_df: pd.DataFrame,
        span_events_df: pd.DataFrame,
    ) -> None:
        if span_events_df.empty:
            pytest.skip("No SPAN_EVENT rows extracted")
        events_by_span = map_span_events(span_events_df)
        all_names = [e.name for evts in events_by_span.values() for e in evts]
        assert "test_event_with_attrs" in all_names

    def test_exception_event_present(
        self,
        span_events_df: pd.DataFrame,
    ) -> None:
        if span_events_df.empty:
            pytest.skip("No SPAN_EVENT rows extracted")
        events_by_span = map_span_events(span_events_df)
        exception_events = [
            e for evts in events_by_span.values() for e in evts if e.name == "exception"
        ]
        assert len(exception_events) >= 1
        exc = exception_events[0]
        assert EXCEPTION_TYPE in exc.attributes
        assert EXCEPTION_MESSAGE in exc.attributes

    def test_events_attached_to_parent_spans(
        self,
        spans_df: pd.DataFrame,
        span_events_df: pd.DataFrame,
    ) -> None:
        if span_events_df.empty:
            pytest.skip("No SPAN_EVENT rows extracted")
        events_by_span = map_span_events(span_events_df)
        spans = map_span_chunk(spans_df, ACCOUNT_NAME, events_by_span)
        spans_with_events = [s for s in spans if s.events]
        assert len(spans_with_events) >= 1


@pytest.mark.integration_foundation
class TestLogMapping:
    """Verify LOG extraction → map_log_chunk produces valid OTel log batch items."""

    def test_instrumented_log_present(self, logs_df: pd.DataFrame) -> None:
        assert not logs_df.empty, "No LOG rows extracted from Event Table"
        logs = map_log_chunk(logs_df, ACCOUNT_NAME)
        assert len(logs) >= 1
        bodies = [lr.log_record.body for lr in logs if lr.log_record.body]
        assert any("test log" in b for b in bodies), (
            f"No 'test log' found in bodies: {bodies[:5]}"
        )

    def test_db_system_on_log_attributes(self, logs_df: pd.DataFrame) -> None:
        logs = map_log_chunk(logs_df, ACCOUNT_NAME)
        for lr in logs:
            assert lr.log_record.attributes.get(DB_SYSTEM_NAME) == "snowflake"

    def test_resource_service_name_populated(self, logs_df: pd.DataFrame) -> None:
        logs = map_log_chunk(logs_df, ACCOUNT_NAME)
        for lr in logs:
            res = _get_resource(lr)
            assert res.attributes.get(SERVICE_NAME)

    def test_exception_log_present(self, logs_df: pd.DataFrame) -> None:
        logs = map_log_chunk(logs_df, ACCOUNT_NAME)
        exc_logs = [
            lr for lr in logs if lr.log_record.attributes.get(EXCEPTION_MESSAGE)
        ]
        assert len(exc_logs) >= 1, "No exception LOG rows found"

    def test_valid_timestamps(self, logs_df: pd.DataFrame) -> None:
        logs = map_log_chunk(logs_df, ACCOUNT_NAME)
        now_ns = time.time_ns()
        for lr in logs:
            assert lr.log_record.timestamp > YEAR_2020_NS
            assert lr.log_record.timestamp <= now_ns


@pytest.mark.integration_foundation
class TestMetricMapping:
    """Verify METRIC extraction → map_metric_chunk produces valid MetricsData."""

    def test_metric_rows_present(self, metrics_df: pd.DataFrame) -> None:
        assert not metrics_df.empty, "No METRIC rows extracted from Event Table"

    def test_metrics_data_contains_resource_metrics(
        self, metrics_df: pd.DataFrame
    ) -> None:
        metrics = map_metric_chunk(metrics_df, ACCOUNT_NAME)
        assert len(metrics.resource_metrics) >= 1

    def test_metric_resource_is_enriched(self, metrics_df: pd.DataFrame) -> None:
        metrics = map_metric_chunk(metrics_df, ACCOUNT_NAME)
        for resource_metrics in metrics.resource_metrics:
            assert resource_metrics.resource.attributes.get(DB_SYSTEM_NAME) == "snowflake"
            assert (
                resource_metrics.resource.attributes.get(SNOWFLAKE_ACCOUNT_NAME)
                == ACCOUNT_NAME
            )
            assert resource_metrics.resource.attributes.get(SERVICE_NAME)

    def test_metric_datapoints_have_record_type(
        self, metrics_df: pd.DataFrame
    ) -> None:
        metrics = map_metric_chunk(metrics_df, ACCOUNT_NAME)
        for resource_metrics in metrics.resource_metrics:
            for scope_metrics in resource_metrics.scope_metrics:
                for metric in scope_metrics.metrics:
                    for data_point in metric.data.data_points:
                        assert data_point.attributes.get(SNOWFLAKE_RECORD_TYPE) == "METRIC"


@pytest.mark.integration_foundation
class TestLiveOtlpExport:
    """Verify mapped telemetry can be exported via the Story 4.1 foundation."""

    def test_span_export_succeeds(
        self, live_export_results: dict[str, bool | None]
    ) -> None:
        assert live_export_results["span_export"] is True

    def test_log_export_succeeds(
        self, live_export_results: dict[str, bool | None]
    ) -> None:
        assert live_export_results["log_export"] is True

    def test_metric_export_succeeds_when_metrics_present(
        self, live_export_results: dict[str, bool | None]
    ) -> None:
        if live_export_results["metric_export"] is None:
            pytest.skip("No METRIC rows were available for export verification")
        assert live_export_results["metric_export"] is True


@pytest.mark.integration_collector
class TestCollectorJournalVerification:
    """Verify the live collector observed the exported integration payload."""

    def test_collector_journal_contains_current_test_id(
        self,
        collector_journal_excerpt: str,
        wait_for_event_table: str,
    ) -> None:
        assert wait_for_event_table in collector_journal_excerpt

    def test_collector_journal_contains_contract_attributes(
        self,
        collector_journal_excerpt: str,
    ) -> None:
        assert "db.system.name" in collector_journal_excerpt


@pytest.mark.integration_collector
class TestSplunkEnterpriseVerification:
    """Verify exported logs become searchable in Splunk Enterprise."""

    def test_splunk_search_returns_current_test_id(
        self,
        splunk_search_results_fixture: list[dict[str, Any]],
        wait_for_event_table: str,
    ) -> None:
        raws = [str(row.get("_raw", "")) for row in splunk_search_results_fixture]
        assert raws, "Splunk Enterprise search returned no _raw payloads"
        assert any(wait_for_event_table in raw for raw in raws)

    def test_splunk_search_returns_exported_test_logs(
        self,
        splunk_search_results_fixture: list[dict[str, Any]],
        wait_for_event_table: str,
    ) -> None:
        raws = [str(row.get("_raw", "")) for row in splunk_search_results_fixture]
        assert any(f"test log {wait_for_event_table}" in raw for raw in raws)
        assert any(f"test error log {wait_for_event_table}" in raw for raw in raws)


@pytest.mark.integration_o11y
@pytest.mark.slow
class TestSplunkO11yMetricVerification:
    """Verify the exported metrics are visible in Splunk O11y via REST."""

    def test_o11y_metric_metadata_exists_for_event_table_metrics(
        self,
        metrics_df: pd.DataFrame,
        o11y_metric_metadata_fixture: dict[str, dict[str, Any]],
    ) -> None:
        expected_names = {
            str(name).strip()
            for name in metrics_df["metric_name"].dropna().tolist()
            if str(name).strip()
        }
        assert expected_names
        assert set(o11y_metric_metadata_fixture) == expected_names
        for metric_name, metadata in o11y_metric_metadata_fixture.items():
            assert metadata.get("name") == metric_name

    def test_o11y_raw_mts_has_points_in_exact_metric_window(
        self,
        o11y_raw_mts_results: dict[str, dict[str, Any]],
    ) -> None:
        assert o11y_raw_mts_results
        for metric_name, result in o11y_raw_mts_results.items():
            assert result["errors"] == [], f"Unexpected O11y errors for {metric_name}"
            assert result["mts_count"] > 0, f"No MTS returned for {metric_name}"
            assert result["point_count"] > 0, f"No datapoints returned for {metric_name}"
            assert (
                result["points_in_exact_window"] > 0
            ), f"No datapoints landed in the exact run window for {metric_name}"


@pytest.mark.integration_o11y
@pytest.mark.slow
class TestSplunkO11yTraceVerification:
    """Verify the collector-observed trace is retrievable from Splunk O11y."""

    def test_o11y_trace_matches_collector_trace_identity(
        self,
        collector_attribute_span: dict[str, Any],
        o11y_trace_segment_fixture: dict[str, Any],
    ) -> None:
        target_span = o11y_trace_segment_fixture["target_span"]
        assert target_span["traceId"] == collector_attribute_span["trace_id"]
        assert target_span["spanId"] == collector_attribute_span["span_id"]
        assert target_span["operationName"] == collector_attribute_span["name"]

    def test_o11y_trace_preserves_row_count_attributes(
        self,
        wait_for_event_table: str,
        collector_attribute_span: dict[str, Any],
        o11y_trace_segment_fixture: dict[str, Any],
    ) -> None:
        target_span = o11y_trace_segment_fixture["target_span"]
        tags = target_span.get("tags", {})
        process_tags = target_span.get("processTags", {})
        collector_attrs = collector_attribute_span["attributes"]

        assert tags.get("test.id") == wait_for_event_table
        assert int(tags["snow.input.rows"]) == collector_attrs["snow.input.rows"]
        assert int(tags["snow.output.rows"]) == collector_attrs["snow.output.rows"]
        assert (
            int(tags["snow.process.memory.usage.max"])
            == collector_attrs["snow.process.memory.usage.max"]
        )
        assert tags.get("db.system.name") is None
        assert tags.get("snowflake.account.name") is None
        assert process_tags.get("db.system.name") == "snowflake"
        assert process_tags.get("snowflake.account.name") == ACCOUNT_NAME


@pytest.mark.integration_foundation
class TestRichTraceGeneration:
    """Verify the richer caller-side SQL/procedure/function scenario."""

    def test_rich_trace_collapses_into_one_trace_tree(
        self,
        rich_spans_df: pd.DataFrame,
    ) -> None:
        assert not rich_spans_df.empty, "No rich SPAN rows extracted from Event Table"
        assert rich_spans_df["trace_id"].nunique() == 1
        assert len(rich_spans_df) >= 10

    def test_rich_trace_contains_mixed_exec_types(
        self,
        rich_target_trace_df: pd.DataFrame,
    ) -> None:
        exec_types = {
            str(item).upper()
            for item in rich_target_trace_df["exec_type"].dropna().tolist()
        }
        assert {"QUERY", "STATEMENT", "PROCEDURE", "FUNCTION"} <= exec_types

    def test_rich_trace_contains_sql_and_routine_span_names(
        self,
        rich_target_trace_df: pd.DataFrame,
    ) -> None:
        span_names = {str(item) for item in rich_target_trace_df["span_name"].tolist()}
        assert "call" in span_names
        assert "select" in span_names
        assert "snow.auto_instrumented" in span_names
        assert any("generate_test_logs" in name for name in span_names)
        assert any("generate_test_spans" in name for name in span_names)
        assert any("generate_test_udf_telemetry" in name for name in span_names)
        assert any("generate_test_exception" in name for name in span_names)


@pytest.mark.integration_o11y
@pytest.mark.slow
class TestRichTraceExportVerification:
    """Verify the rich trace reaches collector and O11y intact."""

    def test_rich_trace_reaches_o11y_with_matching_span_counts(
        self,
        rich_trace_export_summary: dict[str, Any],
    ) -> None:
        assert rich_trace_export_summary["snowflake_span_count"] >= 10
        assert (
            rich_trace_export_summary["collector_span_count"]
            == rich_trace_export_summary["snowflake_span_count"]
        )
        assert (
            rich_trace_export_summary["o11y_span_count"]
            == rich_trace_export_summary["snowflake_span_count"]
        )
        assert rich_trace_export_summary["snowflake_equals_collector"] is True
        assert rich_trace_export_summary["snowflake_equals_o11y"] is True
        assert rich_trace_export_summary["collector_equals_o11y"] is True

    def test_rich_trace_o11y_contains_expected_operation_mix(
        self,
        rich_trace_export_summary: dict[str, Any],
    ) -> None:
        operation_names = {
            str(span.get("operationName"))
            for span in rich_trace_export_summary["o11y_spans"]
        }
        assert "call" in operation_names
        assert "select" in operation_names
        assert "snow.auto_instrumented" in operation_names
        assert any("GENERATE_TEST_LOGS" in name for name in operation_names)
        assert any("GENERATE_TEST_SPANS" in name for name in operation_names)
        assert any("generate_test_udf_telemetry" in name for name in operation_names)
        assert any("GENERATE_TEST_EXCEPTION" in name for name in operation_names)
