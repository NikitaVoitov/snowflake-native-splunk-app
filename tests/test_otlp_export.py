"""Unit tests for otlp_export module -- mocked gRPC/OTel layer."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import otlp_export
import pytest
from export_result import ExportOutcome
from opentelemetry.sdk._logs.export import LogExportResult
from opentelemetry.sdk.metrics.export import MetricExportResult
from opentelemetry.sdk.trace.export import SpanExportResult


def _reset_module() -> None:
    """Reset all module-level singletons between tests."""
    otlp_export._span_exporter = None
    otlp_export._metric_exporter = None
    otlp_export._log_exporter = None
    otlp_export._initialized_endpoint = None
    otlp_export._initialized_pem_fingerprint = None
    otlp_export._generation = 0
    otlp_export._last_used = 0.0
    otlp_export._active_exports = 0
    otlp_export._reinitializing = False


class TestTLSEnforcement:
    """Plaintext endpoint raises ValueError (AC 2)."""

    def test_http_scheme_rejected(self) -> None:
        _reset_module()
        with pytest.raises(ValueError, match=r"Plaintext|Plain HTTP"):
            otlp_export.init_exporters("http://collector.example.com:4317")

    def test_insecure_marker_rejected(self) -> None:
        _reset_module()
        with pytest.raises(ValueError, match=r"(?i)plaintext|insecure"):
            otlp_export.init_exporters(
                "insecure=True&host=collector.example.com:4317",
            )

    def test_empty_endpoint_rejected(self) -> None:
        _reset_module()
        with pytest.raises(ValueError, match=r"must not be empty"):
            otlp_export.init_exporters("")


class TestCredentialConstruction:
    """Default trust store (AC 1) and custom PEM (AC 1)."""

    @patch("otlp_export.grpc.ssl_channel_credentials")
    def test_default_trust_store(self, mock_ssl: MagicMock) -> None:
        mock_ssl.return_value = MagicMock()
        creds = otlp_export._build_credentials(None)
        mock_ssl.assert_called_once_with()
        assert creds is not None

    @patch("otlp_export.grpc.ssl_channel_credentials")
    def test_custom_pem(self, mock_ssl: MagicMock) -> None:
        mock_ssl.return_value = MagicMock()
        pem = "-----BEGIN CERTIFICATE-----\nMIIB...\n-----END CERTIFICATE-----"
        creds = otlp_export._build_credentials(pem)
        mock_ssl.assert_called_once_with(
            root_certificates=pem.encode("utf-8"),
        )
        assert creds is not None

    @patch("otlp_export.grpc.ssl_channel_credentials")
    def test_empty_pem_uses_default(self, mock_ssl: MagicMock) -> None:
        mock_ssl.return_value = MagicMock()
        otlp_export._build_credentials("")
        mock_ssl.assert_called_once_with()

    @patch("otlp_export.grpc.ssl_channel_credentials")
    def test_whitespace_pem_uses_default(self, mock_ssl: MagicMock) -> None:
        mock_ssl.return_value = MagicMock()
        otlp_export._build_credentials("   ")
        mock_ssl.assert_called_once_with()


def _mock_metrics_data(n_data_points: int = 1) -> MagicMock:
    """Build a mock MetricsData with countable data points."""
    data_points = [MagicMock() for _ in range(n_data_points)]
    data = MagicMock(data_points=data_points)
    metric = MagicMock(data=data)
    scope = MagicMock(metrics=[metric])
    rm = MagicMock(scope_metrics=[scope])
    return MagicMock(resource_metrics=[rm])


def _init_with_mocks(
    mock_cred: MagicMock,
    mock_span: MagicMock,
    mock_metric: MagicMock,
    mock_log: MagicMock,
    *,
    span_result: object = SpanExportResult.SUCCESS,
    metric_result: object = MetricExportResult.SUCCESS,
    log_result: object = LogExportResult.SUCCESS,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Wire up mocks and init exporters, return (span_exp, metric_exp, log_exp)."""
    mock_cred.return_value = MagicMock()

    span_exp = MagicMock()
    span_exp.export.return_value = span_result
    mock_span.return_value = span_exp

    metric_exp = MagicMock()
    metric_exp.export.return_value = metric_result
    mock_metric.return_value = metric_exp

    log_exp = MagicMock()
    log_exp.export.return_value = log_result
    mock_log.return_value = log_exp

    otlp_export.init_exporters("https://collector.example.com:4317")
    return span_exp, metric_exp, log_exp


class TestExportResults:
    """Export returns ExportOutcome with correct success/failure and backward compat (AC 4)."""

    def setup_method(self) -> None:
        _reset_module()

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_export_spans_success(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        _init_with_mocks(mock_cred, mock_span, mock_metric, mock_log)
        outcome = otlp_export.export_spans([MagicMock()])
        assert isinstance(outcome, ExportOutcome)
        assert outcome  # backward compat: truthy on success
        assert outcome.success is True
        assert outcome.terminal is False
        assert outcome.signal_type == "spans"
        assert outcome.batch_size == 1
        assert outcome.duration_ms >= 0

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_export_spans_failure(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        _init_with_mocks(
            mock_cred,
            mock_span,
            mock_metric,
            mock_log,
            span_result=SpanExportResult.FAILURE,
        )
        outcome = otlp_export.export_spans([MagicMock()])
        assert not outcome  # backward compat: falsy on failure
        assert outcome.success is False
        assert outcome.terminal is True
        assert outcome.error_code == "FAILURE"

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_export_logs_success(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        _init_with_mocks(mock_cred, mock_span, mock_metric, mock_log)
        outcome = otlp_export.export_logs([MagicMock()])
        assert outcome
        assert outcome.success is True

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_export_logs_failure(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        _init_with_mocks(
            mock_cred,
            mock_span,
            mock_metric,
            mock_log,
            log_result=LogExportResult.FAILURE,
        )
        outcome = otlp_export.export_logs([MagicMock()])
        assert not outcome
        assert outcome.terminal is True

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_export_logs_accepts_success_name_from_newer_sdk(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        compat_success = type("CompatSuccess", (), {"name": "SUCCESS"})()
        _init_with_mocks(
            mock_cred,
            mock_span,
            mock_metric,
            mock_log,
            log_result=compat_success,
        )
        outcome = otlp_export.export_logs([MagicMock()])
        assert outcome
        assert outcome.success is True

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_export_metrics_success(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        _init_with_mocks(mock_cred, mock_span, mock_metric, mock_log)
        outcome = otlp_export.export_metrics(_mock_metrics_data())
        assert outcome
        assert outcome.success is True

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_export_metrics_failure(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        _init_with_mocks(
            mock_cred,
            mock_span,
            mock_metric,
            mock_log,
            metric_result=MetricExportResult.FAILURE,
        )
        outcome = otlp_export.export_metrics(_mock_metrics_data())
        assert not outcome
        assert outcome.terminal is True

    def test_export_spans_before_init(self) -> None:
        outcome = otlp_export.export_spans([MagicMock()])
        assert not outcome
        assert outcome.terminal is True
        assert "not initialized" in (outcome.error_message or "").lower()

    def test_export_logs_before_init(self) -> None:
        outcome = otlp_export.export_logs([MagicMock()])
        assert not outcome
        assert outcome.terminal is True

    def test_export_metrics_before_init(self) -> None:
        outcome = otlp_export.export_metrics(_mock_metrics_data())
        assert not outcome
        assert outcome.terminal is True

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_export_spans_exception_returns_terminal(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        span_exp, _, _ = _init_with_mocks(
            mock_cred,
            mock_span,
            mock_metric,
            mock_log,
        )
        span_exp.export.side_effect = RuntimeError("gRPC unavailable")
        outcome = otlp_export.export_spans([MagicMock()])
        assert not outcome
        assert outcome.terminal is True
        assert "RuntimeError" in (outcome.error_message or "")

    @patch("otlp_export.log")
    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_export_spans_exception_logs_sanitized_summary(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log_exporter: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        span_exp, _, _ = _init_with_mocks(
            mock_cred,
            mock_span,
            mock_metric,
            mock_log_exporter,
        )
        span_exp.export.side_effect = RuntimeError(
            "failed connecting to https://secret.example.com:4317/v1/traces",
        )

        outcome = otlp_export.export_spans([MagicMock()])

        assert not outcome
        mock_log.warning.assert_called_once()
        logged_summary = mock_log.warning.call_args[0][2]
        assert "https://secret.example.com" not in logged_summary
        assert "[URL-REDACTED]" in logged_summary
        assert mock_log.warning.call_args[1]["extra"]["signal_type"] == "spans"
        assert mock_log.warning.call_args[1]["extra"]["error_code"] == "RuntimeError"
        assert "[URL-REDACTED]" in mock_log.warning.call_args[1]["extra"]["error_message"]

    @patch("otlp_export.log")
    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_export_spans_hidden_status_typeerror_normalized_to_failure(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log_exporter: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        span_exp, _, _ = _init_with_mocks(
            mock_cred,
            mock_span,
            mock_metric,
            mock_log_exporter,
        )
        span_exp.export.side_effect = TypeError(
            "cannot unpack non-iterable bool object",
        )

        outcome = otlp_export.export_spans([MagicMock()])

        assert not outcome
        assert outcome.error_code == "FAILURE"
        assert "underlying gRPC status code" in (outcome.error_message or "")
        assert "TypeError" in (outcome.error_message or "")
        mock_log.warning.assert_called_once()
        assert mock_log.warning.call_args[1]["extra"]["signal_type"] == "spans"
        assert mock_log.warning.call_args[1]["extra"]["error_code"] == "FAILURE"

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_export_logs_exception_returns_terminal(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        _, _, log_exp = _init_with_mocks(
            mock_cred,
            mock_span,
            mock_metric,
            mock_log,
        )
        log_exp.export.side_effect = RuntimeError("gRPC unavailable")
        outcome = otlp_export.export_logs([MagicMock()])
        assert not outcome
        assert outcome.terminal is True

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_export_metrics_exception_returns_terminal(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        _, metric_exp, _ = _init_with_mocks(
            mock_cred,
            mock_span,
            mock_metric,
            mock_log,
        )
        metric_exp.export.side_effect = RuntimeError("gRPC unavailable")
        outcome = otlp_export.export_metrics(_mock_metrics_data())
        assert not outcome
        assert outcome.terminal is True

    def test_export_spans_empty_batch_is_noop(self) -> None:
        outcome = otlp_export.export_spans([])
        assert outcome
        assert outcome.batch_size == 0
        assert outcome.signal_type == "spans"

    def test_export_spans_none_batch_is_noop(self) -> None:
        outcome = otlp_export.export_spans(None)
        assert outcome
        assert outcome.batch_size == 0

    def test_export_logs_empty_batch_is_noop(self) -> None:
        outcome = otlp_export.export_logs([])
        assert outcome
        assert outcome.batch_size == 0


class TestCloseExporters:
    """close_exporters calls shutdown for all three exporters (AC 5)."""

    def setup_method(self) -> None:
        _reset_module()

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_close_calls_shutdown(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        span_exp, metric_exp, log_exp = _init_with_mocks(
            mock_cred,
            mock_span,
            mock_metric,
            mock_log,
        )

        otlp_export.close_exporters()

        span_exp.shutdown.assert_called_once()
        metric_exp.shutdown.assert_called_once()
        log_exp.shutdown.assert_called_once()
        assert otlp_export._span_exporter is None
        assert otlp_export._metric_exporter is None
        assert otlp_export._log_exporter is None
        assert otlp_export._initialized_endpoint is None
        assert otlp_export._initialized_pem_fingerprint is None

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_close_tolerates_shutdown_exception(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        span_exp, metric_exp, log_exp = _init_with_mocks(
            mock_cred,
            mock_span,
            mock_metric,
            mock_log,
        )
        span_exp.shutdown.side_effect = RuntimeError("shutdown fail")

        otlp_export.close_exporters()

        assert otlp_export._span_exporter is None
        metric_exp.shutdown.assert_called_once()
        log_exp.shutdown.assert_called_once()


class TestSingletonBehavior:
    """Second warm call returns same exporter instances (AC 3)."""

    def setup_method(self) -> None:
        _reset_module()

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_warm_call_reuses_exporters(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        _init_with_mocks(mock_cred, mock_span, mock_metric, mock_log)
        snap1 = otlp_export.debug_snapshot()

        otlp_export.init_exporters("https://collector.example.com:4317")
        snap2 = otlp_export.debug_snapshot()

        assert snap1["span_exporter_id"] == snap2["span_exporter_id"]
        assert snap1["metric_exporter_id"] == snap2["metric_exporter_id"]
        assert snap1["log_exporter_id"] == snap2["log_exporter_id"]
        assert snap1["generation"] == snap2["generation"]
        mock_span.assert_called_once()


class TestIdleTimeoutEviction:
    """Exporters recreated after _MAX_IDLE_S seconds (AC 3)."""

    def setup_method(self) -> None:
        _reset_module()

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    @patch("otlp_export.time.monotonic")
    def test_idle_eviction_recreates(
        self,
        mock_time: MagicMock,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        call_count = [0]

        def make_span(*_args: object, **_kwargs: object) -> MagicMock:
            call_count[0] += 1
            return MagicMock(name=f"span_exp_{call_count[0]}")

        mock_span.side_effect = make_span
        mock_metric.return_value = MagicMock()
        mock_log.return_value = MagicMock()
        mock_cred.return_value = MagicMock()

        mock_time.return_value = 1000.0
        otlp_export.init_exporters("https://collector.example.com:4317")
        gen1 = otlp_export._generation

        mock_time.return_value = 1000.0 + otlp_export._MAX_IDLE_S + 1
        otlp_export.init_exporters("https://collector.example.com:4317")
        gen2 = otlp_export._generation

        assert gen2 == gen1 + 1
        assert mock_span.call_count == 2

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    @patch("otlp_export.time.monotonic")
    def test_recent_export_activity_prevents_idle_recreation(
        self,
        mock_time: MagicMock,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        mock_cred.return_value = MagicMock()
        span_exp = MagicMock()
        span_exp.export.return_value = SpanExportResult.SUCCESS
        mock_span.return_value = span_exp
        metric_exp = MagicMock()
        metric_exp.export.return_value = MetricExportResult.SUCCESS
        mock_metric.return_value = metric_exp
        log_exp = MagicMock()
        log_exp.export.return_value = LogExportResult.SUCCESS
        mock_log.return_value = log_exp

        mock_time.side_effect = [1000.0, 1056.0, 1057.0, 1057.0, 1058.0, 1058.0]
        otlp_export.init_exporters("https://collector.example.com:4317")
        assert otlp_export.export_spans([MagicMock()])  # truthy ExportOutcome

        gen_before = otlp_export._generation
        otlp_export.init_exporters("https://collector.example.com:4317")

        assert otlp_export._generation == gen_before
        mock_span.assert_called_once()


class TestThreadSafeInit:
    """Concurrent init_exporters calls do not corrupt state (AC 3)."""

    def setup_method(self) -> None:
        _reset_module()

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_concurrent_init(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        mock_cred.return_value = MagicMock()
        mock_span.return_value = MagicMock()
        mock_metric.return_value = MagicMock()
        mock_log.return_value = MagicMock()

        errors: list[Exception] = []

        def worker() -> None:
            try:
                otlp_export.init_exporters(
                    "https://collector.example.com:4317",
                )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert otlp_export._span_exporter is not None
        assert otlp_export._metric_exporter is not None
        assert otlp_export._log_exporter is not None
        assert otlp_export._generation >= 1


class _ControlledSpanExporter:
    def __init__(
        self,
        export_started: threading.Event,
        allow_finish: threading.Event,
    ) -> None:
        self._export_started = export_started
        self._allow_finish = allow_finish
        self.shutdown_called = False
        self.shutdown_during_export = False
        self.export_in_progress = False

    def export(self, _batch: object) -> SpanExportResult:
        self.export_in_progress = True
        self._export_started.set()
        self._allow_finish.wait(timeout=5.0)
        self.export_in_progress = False
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        self.shutdown_called = True
        if self.export_in_progress:
            self.shutdown_during_export = True


class _PassiveExporter:
    def __init__(self, result: object) -> None:
        self._result = result
        self.shutdown_called = False

    def export(self, _batch: object) -> object:
        return self._result

    def shutdown(self) -> None:
        self.shutdown_called = True


class TestConcurrentReinitDuringExport:
    def setup_method(self) -> None:
        _reset_module()

    @patch("otlp_export._build_credentials")
    def test_reinit_waits_for_inflight_export(
        self,
        mock_cred: MagicMock,
    ) -> None:
        export_started = threading.Event()
        allow_finish = threading.Event()
        span_exporters: list[_ControlledSpanExporter] = []

        def build_span(_target: str, _creds: object) -> _ControlledSpanExporter:
            exporter = _ControlledSpanExporter(export_started, allow_finish)
            span_exporters.append(exporter)
            return exporter

        mock_cred.return_value = MagicMock()

        with (
            patch("otlp_export._build_span_exporter", side_effect=build_span),
            patch(
                "otlp_export._build_metric_exporter",
                return_value=_PassiveExporter(MetricExportResult.SUCCESS),
            ),
            patch(
                "otlp_export._build_log_exporter",
                return_value=_PassiveExporter(LogExportResult.SUCCESS),
            ),
        ):
            otlp_export.init_exporters("https://collector.example.com:4317")
            old_exporter = span_exporters[0]
            export_result: dict[str, object] = {}

            def do_export() -> None:
                export_result["value"] = otlp_export.export_spans([MagicMock()])

            export_thread = threading.Thread(target=do_export)
            reinit_thread = threading.Thread(
                target=otlp_export.init_exporters,
                args=("https://collector2.example.com:4317",),
            )

            export_thread.start()
            assert export_started.wait(timeout=5.0)

            reinit_thread.start()
            time.sleep(0.05)
            allow_finish.set()

            export_thread.join(timeout=5.0)
            reinit_thread.join(timeout=5.0)

            assert export_result["value"]  # truthy ExportOutcome
            assert not old_exporter.shutdown_during_export
            assert old_exporter.shutdown_called is True
            assert otlp_export._generation == 2


class TestDebugSnapshot:
    """Non-secret metadata, generation increments (AC 6)."""

    def setup_method(self) -> None:
        _reset_module()

    def test_snapshot_before_init(self) -> None:
        snap = otlp_export.debug_snapshot()
        assert snap["generation"] == 0
        assert snap["initialized_endpoint"] is None
        assert snap["span_exporter_id"] is None

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_snapshot_after_init(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        _init_with_mocks(mock_cred, mock_span, mock_metric, mock_log)
        snap = otlp_export.debug_snapshot()

        assert snap["generation"] == 1
        assert snap["initialized_endpoint"] == "collector.example.com:4317"
        assert snap["span_exporter_id"] is not None
        assert snap["metric_exporter_id"] is not None
        assert snap["log_exporter_id"] is not None
        assert "pem_fingerprint" in snap

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_generation_increments_on_reinit(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        _init_with_mocks(mock_cred, mock_span, mock_metric, mock_log)
        assert otlp_export._generation == 1

        otlp_export.close_exporters()
        mock_cred.return_value = MagicMock()
        mock_span.return_value = MagicMock()
        mock_metric.return_value = MagicMock()
        mock_log.return_value = MagicMock()
        otlp_export.init_exporters("https://collector.example.com:4317")
        assert otlp_export._generation == 2


class TestChannelOptions:
    """_CHANNEL_OPTIONS are passed to exporter constructors."""

    def setup_method(self) -> None:
        _reset_module()

    @patch("otlp_export.OTLPLogExporter")
    @patch("otlp_export.OTLPMetricExporter")
    @patch("otlp_export.OTLPSpanExporter")
    @patch("otlp_export._build_credentials")
    def test_channel_options_passed(
        self,
        mock_cred: MagicMock,
        mock_span_cls: MagicMock,
        mock_metric_cls: MagicMock,
        mock_log_cls: MagicMock,
    ) -> None:
        mock_cred.return_value = MagicMock()

        otlp_export.init_exporters("https://collector.example.com:4317")

        expected_opts = tuple(otlp_export._CHANNEL_OPTIONS)
        for mock_cls in (mock_span_cls, mock_metric_cls, mock_log_cls):
            mock_cls.assert_called_once()
            call_kwargs = mock_cls.call_args[1]
            assert call_kwargs["channel_options"] == expected_opts
            assert call_kwargs["insecure"] is False
            assert call_kwargs["endpoint"] == "collector.example.com:4317"
            assert call_kwargs["compression"] == otlp_export._EXPORT_COMPRESSION
            assert call_kwargs["timeout"] == otlp_export._EXPORT_TIMEOUT_S


class TestEndpointChange:
    """Endpoint or PEM change triggers exporter recreation."""

    def setup_method(self) -> None:
        _reset_module()

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_endpoint_change_recreates(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        _init_with_mocks(mock_cred, mock_span, mock_metric, mock_log)
        gen1 = otlp_export._generation

        mock_cred.return_value = MagicMock()
        mock_span.return_value = MagicMock()
        mock_metric.return_value = MagicMock()
        mock_log.return_value = MagicMock()
        otlp_export.init_exporters("https://collector2.example.com:4317")
        gen2 = otlp_export._generation

        assert gen2 == gen1 + 1

    @patch("otlp_export._build_log_exporter")
    @patch("otlp_export._build_metric_exporter")
    @patch("otlp_export._build_span_exporter")
    @patch("otlp_export._build_credentials")
    def test_pem_change_recreates(
        self,
        mock_cred: MagicMock,
        mock_span: MagicMock,
        mock_metric: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        _init_with_mocks(mock_cred, mock_span, mock_metric, mock_log)
        gen1 = otlp_export._generation

        mock_cred.return_value = MagicMock()
        mock_span.return_value = MagicMock()
        mock_metric.return_value = MagicMock()
        mock_log.return_value = MagicMock()
        otlp_export.init_exporters(
            "https://collector.example.com:4317",
            pem_cert="-----BEGIN CERTIFICATE-----\nABC\n-----END CERTIFICATE-----",
        )
        gen2 = otlp_export._generation

        assert gen2 == gen1 + 1
