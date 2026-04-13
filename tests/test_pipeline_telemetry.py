"""Unit tests for pipeline_telemetry module — structured logging + health recording."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from export_result import ExportOutcome
from pipeline_telemetry import (
    ExportContext,
    _build_health_metadata,
    _build_log_extra,
    log_export_success,
    log_terminal_failure,
    record_batch_failure,
    record_export_success,
)


@pytest.fixture
def ctx() -> ExportContext:
    return ExportContext(
        pipeline_name="event_table_mapper",
        source_name="SNOWFLAKE.TELEMETRY.EVENTS",
        run_id="run-abc-123",
    )


@pytest.fixture
def terminal_outcome() -> ExportOutcome:
    return ExportOutcome(
        success=False,
        terminal=True,
        error_code="PERMISSION_DENIED",
        error_message="gRPC PERMISSION_DENIED: access denied",
        signal_type="spans",
        batch_size=42,
        retryable=False,
        duration_ms=350,
    )


@pytest.fixture
def success_outcome() -> ExportOutcome:
    return ExportOutcome.success_result("spans", 10, 150)


# ── _build_log_extra ──────────────────────────────────────────────


class TestBuildLogExtra:
    def test_all_fields_present(
        self, ctx: ExportContext, terminal_outcome: ExportOutcome,
    ) -> None:
        extra = _build_log_extra(ctx, terminal_outcome)
        assert extra["pipeline"] == "event_table_mapper"
        assert extra["source"] == "SNOWFLAKE.TELEMETRY.EVENTS"
        assert extra["run_id"] == "run-abc-123"
        assert extra["signal_type"] == "spans"
        assert extra["error_code"] == "PERMISSION_DENIED"
        assert extra["batch_size"] == 42
        assert extra["duration_ms"] == 350
        assert extra["retryable"] is False


# ── log_terminal_failure ──────────────────────────────────────────


class TestLogTerminalFailure:
    def test_emits_error_log(
        self, ctx: ExportContext, terminal_outcome: ExportOutcome,
    ) -> None:
        with patch("pipeline_telemetry.log") as mock_log:
            log_terminal_failure(ctx, terminal_outcome)
            mock_log.error.assert_called_once()
            args, kwargs = mock_log.error.call_args
            assert "terminal failure" in args[0].lower()
            assert kwargs["extra"]["error_code"] == "PERMISSION_DENIED"


# ── log_export_success ────────────────────────────────────────────


class TestLogExportSuccess:
    def test_emits_info_log(
        self, ctx: ExportContext, success_outcome: ExportOutcome,
    ) -> None:
        with patch("pipeline_telemetry.log") as mock_log:
            log_export_success(ctx, success_outcome)
            mock_log.info.assert_called_once()
            args, kwargs = mock_log.info.call_args
            assert "success" in args[0].lower()
            assert kwargs["extra"]["batch_size"] == 10


# ── _build_health_metadata ────────────────────────────────────────


class TestBuildHealthMetadata:
    def test_valid_json(self, terminal_outcome: ExportOutcome) -> None:
        raw = _build_health_metadata(terminal_outcome)
        parsed = json.loads(raw)
        assert parsed["error_code"] == "PERMISSION_DENIED"
        assert parsed["batch_size"] == 42
        assert parsed["retryable"] is False


# ── record_batch_failure ──────────────────────────────────────────


class TestRecordBatchFailure:
    def test_inserts_to_pipeline_health(
        self, terminal_outcome: ExportOutcome,
    ) -> None:
        session = MagicMock()
        session.sql.return_value.collect.return_value = []

        record_batch_failure(
            session, "my_pipe", "my_source", terminal_outcome, "run-xyz",
        )

        session.sql.assert_called_once()
        call_args = session.sql.call_args
        assert "INSERT INTO _metrics.pipeline_health" in call_args[0][0]
        params = call_args[1]["params"] if "params" in call_args[1] else call_args[0][1]
        assert params[0] == "run-xyz"
        assert params[1] == "my_pipe"
        assert params[2] == "my_source"
        assert params[3] == "rows_failed"
        assert params[4] == 42

    def test_graceful_on_sql_error(
        self, terminal_outcome: ExportOutcome,
    ) -> None:
        session = MagicMock()
        session.sql.side_effect = RuntimeError("DB down")

        record_batch_failure(
            session, "pipe", "src", terminal_outcome, "run-1",
        )


# ── record_export_success ─────────────────────────────────────────


class TestRecordExportSuccess:
    def test_inserts_to_pipeline_health(self) -> None:
        session = MagicMock()
        session.sql.return_value.collect.return_value = []

        record_export_success(session, "pipe", "src", "spans", 10, "run-2")

        session.sql.assert_called_once()
        call_args = session.sql.call_args
        params = call_args[1]["params"] if "params" in call_args[1] else call_args[0][1]
        assert params[3] == "rows_exported"
        assert params[4] == 10

    def test_graceful_on_sql_error(self) -> None:
        session = MagicMock()
        session.sql.side_effect = RuntimeError("timeout")

        record_export_success(session, "pipe", "src", "logs", 5, "run-3")
