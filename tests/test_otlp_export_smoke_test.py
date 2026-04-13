"""Unit tests for the diagnostic runtime harness (otlp_export_smoke_test)."""

from __future__ import annotations

import json
import sys
import types
from unittest.mock import ANY, MagicMock, patch

import otlp_export
import otlp_export_smoke_test
from opentelemetry.sdk._logs.export import LogExportResult
from opentelemetry.sdk.metrics.export import Metric, MetricExportResult
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import SpanExportResult


def _reset_module() -> None:
    otlp_export._span_exporter = None
    otlp_export._metric_exporter = None
    otlp_export._log_exporter = None
    otlp_export._initialized_endpoint = None
    otlp_export._initialized_pem_fingerprint = None
    otlp_export._generation = 0
    otlp_export._last_used = 0.0
    otlp_export._active_exports = 0
    otlp_export._reinitializing = False


def _wire_mocks(
    mock_cred: MagicMock,
    mock_span: MagicMock,
    mock_metric: MagicMock,
    mock_log: MagicMock,
    *,
    span_ok: bool = True,
    metric_ok: bool = True,
    log_ok: bool = True,
) -> None:
    """Wire up builder mocks with configurable export results."""
    mock_cred.return_value = MagicMock()

    span_exp = MagicMock()
    span_exp.export.return_value = (
        SpanExportResult.SUCCESS if span_ok else SpanExportResult.FAILURE
    )
    mock_span.return_value = span_exp

    metric_exp = MagicMock()
    metric_exp.export.return_value = (
        MetricExportResult.SUCCESS if metric_ok else MetricExportResult.FAILURE
    )
    mock_metric.return_value = metric_exp

    log_exp = MagicMock()
    log_exp.export.return_value = (
        LogExportResult.SUCCESS if log_ok else LogExportResult.FAILURE
    )
    mock_log.return_value = log_exp


class TestRunSmokeTest:
    """Validates run_smoke_test logic with mocked exporters."""

    def setup_method(self) -> None:
        _reset_module()

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_returns_per_signal_results(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        _wire_mocks(mock_cred, mock_span, mock_metric, mock_log)

        result = otlp_export_smoke_test.run_smoke_test(
            endpoint="https://collector.example.com:4317",
            test_id="test_001",
        )

        assert result["test_id"] == "test_001"
        assert result["span_export"] is True
        assert result["log_export"] is True
        assert result["metric_export"] is True
        assert result["span_outcome"]["success"] is True
        assert result["log_outcome"]["success"] is True
        assert result["metric_outcome"]["success"] is True
        assert result["generation_after"] == 1
        assert "debug_snapshot" in result

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_returns_failure_on_export_error(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        _wire_mocks(
            mock_cred,
            mock_span,
            mock_metric,
            mock_log,
            span_ok=False,
        )

        result = otlp_export_smoke_test.run_smoke_test(
            endpoint="https://collector.example.com:4317",
            test_id="test_fail",
        )

        assert result["span_export"] is False
        assert result["log_export"] is True
        assert result["metric_export"] is True
        assert result["span_outcome"]["terminal"] is True
        assert result["span_outcome"]["error_code"] == "FAILURE"

    def test_init_error_returned(self) -> None:
        result = otlp_export_smoke_test.run_smoke_test(
            endpoint="http://insecure.example.com:4317",
            test_id="test_insecure",
        )
        assert "init_error" in result
        assert "span_export" not in result

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_auto_generates_test_id(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        _wire_mocks(mock_cred, mock_span, mock_metric, mock_log)

        result = otlp_export_smoke_test.run_smoke_test(
            endpoint="https://collector.example.com:4317",
        )
        assert result["test_id"].startswith("smoke_")

    def test_make_test_metrics_uses_sdk_metric_type(self) -> None:
        metrics_data = otlp_export_smoke_test._make_test_metrics(
            "metric_type_test",
            Resource.create({"service.name": "test"}),
        )
        metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]
        assert isinstance(metric, Metric)


class TestSPEntrypoints:
    """Validates the stored procedure handler signatures."""

    def setup_method(self) -> None:
        _reset_module()

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_sp_entrypoint_returns_json(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        _wire_mocks(mock_cred, mock_span, mock_metric, mock_log)

        session = MagicMock()
        raw = otlp_export_smoke_test.test_otlp_export_runtime(
            session,
            "https://collector.example.com:4317",
            "",
            "sp_test_001",
        )
        data = json.loads(raw)
        assert data["test_id"] == "sp_test_001"
        assert "span_export" in data
        assert "span_outcome" in data

    @patch("otlp_export_smoke_test.run_smoke_test")
    def test_secret_backed_entrypoint_reads_bound_secret(
        self,
        mock_run_smoke_test: MagicMock,
    ) -> None:
        mock_run_smoke_test.return_value = {"test_id": "sp_secret_001", "span_export": True}
        fake_snowflake = types.SimpleNamespace(
            get_generic_secret_string=lambda key: "secret-pem" if key == "otlp_pem_cert" else "",
        )

        with patch.dict(sys.modules, {"_snowflake": fake_snowflake}):
            raw = otlp_export_smoke_test.test_otlp_export_runtime_with_secret(
                MagicMock(),
                "https://collector.example.com:4317",
                "sp_secret_001",
            )

        data = json.loads(raw)
        mock_run_smoke_test.assert_called_once_with(
            "https://collector.example.com:4317",
            "secret-pem",
            "sp_secret_001",
        )
        assert data["test_id"] == "sp_secret_001"


class TestObservabilitySmokeTest:
    def setup_method(self) -> None:
        _reset_module()

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    @patch("otlp_export_smoke_test.record_export_success")
    @patch("otlp_export_smoke_test.log_export_success")
    def test_observability_success_path_emits_logs_and_health(
        self,
        mock_log_success: MagicMock,
        mock_record_success: MagicMock,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        _wire_mocks(mock_cred, mock_span, mock_metric, mock_log)

        result = otlp_export_smoke_test.run_observability_smoke_test(
            MagicMock(),
            endpoint="https://collector.example.com:4317",
            test_id="obs_ok_001",
        )

        assert result["observability_emitted"] is True
        assert result["pipeline_name"] == "otlp_export_observability_smoke"
        assert result["source_name"] == "app_public.test_otlp_export_observability"
        assert "run_id" in result
        assert mock_log_success.call_count == 3
        assert mock_record_success.call_count == 3

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    @patch("otlp_export_smoke_test.record_batch_failure")
    @patch("otlp_export_smoke_test.log_terminal_failure")
    @patch("otlp_export_smoke_test.record_export_success")
    @patch("otlp_export_smoke_test.log_export_success")
    def test_observability_failure_path_emits_terminal_failure(
        self,
        mock_log_success: MagicMock,
        mock_record_success: MagicMock,
        mock_log_failure: MagicMock,
        mock_record_failure: MagicMock,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        _wire_mocks(
            mock_cred,
            mock_span,
            mock_metric,
            mock_log,
            span_ok=False,
        )

        result = otlp_export_smoke_test.run_observability_smoke_test(
            MagicMock(),
            endpoint="https://collector.example.com:4317",
            test_id="obs_fail_001",
        )

        assert result["span_outcome"]["success"] is False
        assert result["observability_emitted"] is True
        assert mock_log_failure.call_count == 1
        assert mock_record_failure.call_count == 1
        assert mock_log_success.call_count == 2
        assert mock_record_success.call_count == 2

    @patch("otlp_export_smoke_test.run_observability_smoke_test")
    def test_observability_entrypoint_returns_json(
        self,
        mock_run_observability: MagicMock,
    ) -> None:
        mock_run_observability.return_value = {
            "test_id": "obs_sp_001",
            "run_id": "run-001",
            "observability_emitted": True,
        }

        raw = otlp_export_smoke_test.test_otlp_export_observability(
            MagicMock(),
            "https://collector.example.com:4317",
            "",
            "obs_sp_001",
        )

        data = json.loads(raw)
        mock_run_observability.assert_called_once_with(
            ANY,
            "https://collector.example.com:4317",
            None,
            "obs_sp_001",
        )
        assert data["observability_emitted"] is True

    @patch("otlp_export_smoke_test.run_observability_smoke_test")
    def test_observability_secret_entrypoint_reads_bound_secret(
        self,
        mock_run_observability: MagicMock,
    ) -> None:
        mock_run_observability.return_value = {
            "test_id": "obs_secret_001",
            "run_id": "run-002",
            "observability_emitted": True,
        }
        fake_snowflake = types.SimpleNamespace(
            get_generic_secret_string=lambda key: "secret-pem" if key == "otlp_pem_cert" else "",
        )

        with patch.dict(sys.modules, {"_snowflake": fake_snowflake}):
            raw = otlp_export_smoke_test.test_otlp_export_observability_with_secret(
                MagicMock(),
                "https://collector.example.com:4317",
                "obs_secret_001",
            )

        data = json.loads(raw)
        mock_run_observability.assert_called_once_with(
            ANY,
            "https://collector.example.com:4317",
            "secret-pem",
            "obs_secret_001",
        )
        assert data["observability_emitted"] is True
