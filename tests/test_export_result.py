"""Unit tests for export_result module — ExportOutcome, classification, sanitisation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from export_result import (
    UPSTREAM_RETRYABLE_GRPC_CODES,
    ExportOutcome,
    _sanitize_error_message,
    classify_export_failure_without_status,
    classify_export_failure_without_status_exception,
    classify_grpc_status,
    classify_unexpected_exception,
    count_metric_data_points,
    count_sequence_batch,
)


# ── ExportOutcome dataclass ──────────────────────────────────────


class TestExportOutcomeBool:
    """AC-1: ExportOutcome.__bool__ returns self.success for backward compat."""

    def test_success_is_truthy(self) -> None:
        o = ExportOutcome(success=True, terminal=False)
        assert o
        assert bool(o) is True

    def test_failure_is_falsy(self) -> None:
        o = ExportOutcome(success=False, terminal=True)
        assert not o
        assert bool(o) is False


class TestExportOutcomeFactories:
    def test_success_result(self) -> None:
        o = ExportOutcome.success_result("spans", 42, 150)
        assert o.success is True
        assert o.terminal is False
        assert o.signal_type == "spans"
        assert o.batch_size == 42
        assert o.duration_ms == 150
        assert o.error_code is None
        assert o.error_message is None
        assert o.retryable is None

    def test_noop_result(self) -> None:
        o = ExportOutcome.noop_result("logs")
        assert o.success is True
        assert o.terminal is False
        assert o.batch_size == 0
        assert o.duration_ms == 0

    def test_not_initialized(self) -> None:
        o = ExportOutcome.not_initialized("metrics")
        assert o.success is False
        assert o.terminal is True
        assert o.signal_type == "metrics"
        assert "not initialized" in (o.error_message or "").lower()

    def test_to_dict_round_trip(self) -> None:
        o = ExportOutcome.success_result("spans", 10, 5)
        d = o.to_dict()
        assert d["success"] is True
        assert d["batch_size"] == 10
        assert isinstance(d, dict)


# ── UPSTREAM_RETRYABLE_GRPC_CODES ────────────────────────────────


class TestUpstreamRetryableSet:
    """AC-2: exact match with the SDK's _RETRYABLE_ERROR_CODES."""

    EXPECTED = frozenset(
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

    def test_exact_membership(self) -> None:
        assert UPSTREAM_RETRYABLE_GRPC_CODES == self.EXPECTED

    @pytest.mark.parametrize(
        "code",
        ["PERMISSION_DENIED", "UNAUTHENTICATED", "UNIMPLEMENTED", "NOT_FOUND", "INTERNAL"],
    )
    def test_non_retryable_codes_excluded(self, code: str) -> None:
        assert code not in UPSTREAM_RETRYABLE_GRPC_CODES


# ── classify_grpc_status ─────────────────────────────────────────


class TestClassifyGrpcStatus:
    def _mock_code(self, name: str) -> MagicMock:
        code = MagicMock()
        code.name = name
        return code

    def test_retryable_code(self) -> None:
        o = classify_grpc_status(
            self._mock_code("UNAVAILABLE"), "connection refused", "spans", 5, 200,
        )
        assert o.success is False
        assert o.terminal is True
        assert o.retryable is True
        assert o.error_code == "UNAVAILABLE"
        assert o.batch_size == 5
        assert o.duration_ms == 200
        assert "UNAVAILABLE" in (o.error_message or "")

    def test_non_retryable_code(self) -> None:
        o = classify_grpc_status(
            self._mock_code("PERMISSION_DENIED"), "access denied", "logs", 3, 100,
        )
        assert o.retryable is False
        assert o.terminal is True
        assert o.error_code == "PERMISSION_DENIED"

    def test_details_none(self) -> None:
        o = classify_grpc_status(
            self._mock_code("INTERNAL"), None, "metrics", 1, 50,
        )
        assert "gRPC INTERNAL" in (o.error_message or "")


# ── classify_export_failure_without_status ────────────────────────


class TestClassifyExportFailureWithoutStatus:
    def test_basic_fields(self) -> None:
        o = classify_export_failure_without_status("spans", 10, 300)
        assert o.success is False
        assert o.terminal is True
        assert o.error_code == "FAILURE"
        assert o.retryable is None
        assert o.batch_size == 10
        assert o.duration_ms == 300
        assert "FAILURE" in (o.error_message or "")

    def test_typeerror_hidden_status_is_normalized(self) -> None:
        o = classify_export_failure_without_status_exception(
            TypeError("cannot unpack non-iterable bool object"),
            "metrics",
            3,
            1000,
        )
        assert o is not None
        assert o.error_code == "FAILURE"
        assert o.retryable is None
        assert "TypeError" in (o.error_message or "")

    def test_unrelated_exception_not_normalized(self) -> None:
        o = classify_export_failure_without_status_exception(
            RuntimeError("boom"),
            "spans",
            1,
            10,
        )
        assert o is None


# ── classify_unexpected_exception ─────────────────────────────────


class TestClassifyUnexpectedException:
    def test_runtime_error(self) -> None:
        o = classify_unexpected_exception(
            RuntimeError("boom"), "logs", 7, 120,
        )
        assert o.success is False
        assert o.terminal is True
        assert o.retryable is None
        assert o.error_code == "RuntimeError"
        assert "RuntimeError" in (o.error_message or "")
        assert "boom" in (o.error_message or "")

    def test_url_in_exception_sanitised(self) -> None:
        o = classify_unexpected_exception(
            RuntimeError("Failed to connect to https://secret.example.com:4317/v1"),
            "spans", 1, 10,
        )
        assert "https://" not in (o.error_message or "")
        assert "[URL-REDACTED]" in (o.error_message or "")


# ── _sanitize_error_message ───────────────────────────────────────


class TestSanitizeErrorMessage:
    def test_none_passthrough(self) -> None:
        assert _sanitize_error_message(None) is None

    def test_empty_passthrough(self) -> None:
        assert _sanitize_error_message("") == ""

    def test_pem_block_redacted(self) -> None:
        msg = "Error with -----BEGIN CERTIFICATE-----\nMIIB...\n-----END CERTIFICATE----- tail"
        result = _sanitize_error_message(msg)
        assert "-----BEGIN" not in result
        assert "[PEM-REDACTED]" in result

    def test_url_credentials_redacted(self) -> None:
        msg = "connect to https://user:pass@collector.example.com:4317"
        result = _sanitize_error_message(msg)
        assert "user:pass" not in result

    def test_auth_header_redacted(self) -> None:
        msg = "Authorization: Bearer sk_live_ABCDEF1234567890"
        result = _sanitize_error_message(msg)
        assert "sk_live" not in result
        assert "[AUTH-REDACTED]" in result

    def test_bearer_token_redacted(self) -> None:
        msg = "header Bearer eyJhbGciOiJIUz.payload.sig"
        result = _sanitize_error_message(msg)
        assert "eyJhbGci" not in result

    def test_full_url_redacted(self) -> None:
        msg = "Failed connecting to https://collector.example.com:4317/v1/traces"
        result = _sanitize_error_message(msg)
        assert "https://" not in result
        assert "[URL-REDACTED]" in result

    def test_truncation(self) -> None:
        msg = "x" * 1000
        result = _sanitize_error_message(msg)
        assert len(result) <= 512 + 3
        assert result.endswith("...")

    def test_safe_message_unchanged(self) -> None:
        msg = "gRPC UNAVAILABLE: connection refused"
        assert _sanitize_error_message(msg) == msg


# ── count_metric_data_points ──────────────────────────────────────


class TestCountMetricDataPoints:
    def test_nested_structure(self) -> None:
        dp1, dp2, dp3 = MagicMock(), MagicMock(), MagicMock()
        data1 = MagicMock(data_points=[dp1, dp2])
        data2 = MagicMock(data_points=[dp3])
        metric1 = MagicMock(data=data1)
        metric2 = MagicMock(data=data2)
        scope = MagicMock(metrics=[metric1, metric2])
        rm = MagicMock(scope_metrics=[scope])
        metrics_data = MagicMock(resource_metrics=[rm])
        assert count_metric_data_points(metrics_data) == 3

    def test_empty_metrics_data(self) -> None:
        metrics_data = MagicMock(resource_metrics=[])
        assert count_metric_data_points(metrics_data) == 0

    def test_none_data_attribute(self) -> None:
        metric = MagicMock(data=None)
        scope = MagicMock(metrics=[metric])
        rm = MagicMock(scope_metrics=[scope])
        metrics_data = MagicMock(resource_metrics=[rm])
        assert count_metric_data_points(metrics_data) == 0

    def test_none_input(self) -> None:
        assert count_metric_data_points(None) == 0


# ── count_sequence_batch ──────────────────────────────────────────


class TestCountSequenceBatch:
    def test_normal_list(self) -> None:
        assert count_sequence_batch([1, 2, 3]) == 3

    def test_empty_list(self) -> None:
        assert count_sequence_batch([]) == 0

    def test_none(self) -> None:
        assert count_sequence_batch(None) == 0
