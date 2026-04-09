"""Unit tests for log_mapper — Event Table LOG → OTel log batch items."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from log_mapper import map_log_chunk


try:
    from opentelemetry._logs import SeverityNumber
except ImportError:
    from opentelemetry.sdk._logs import (
        SeverityNumber,  # type: ignore[assignment,no-redef]
    )

from telemetry_constants import (
    DB_NAMESPACE,
    DB_SYSTEM_NAME,
    EXCEPTION_MESSAGE,
    EXCEPTION_STACKTRACE,
    EXCEPTION_TYPE,
    SERVICE_NAME,
    SNOWFLAKE_ACCOUNT_NAME,
    SNOWFLAKE_RECORD_TYPE,
)


def _get_resource(batch_item: Any) -> Any:
    """Extract resource from either LogData (1.38) or ReadableLogRecord (1.39+)."""
    if hasattr(batch_item, "resource"):
        return batch_item.resource
    return batch_item.log_record.resource


ACCOUNT = "LFB71918"


def _log_row(**overrides):
    """Build a realistic LOG row dict."""
    base = {
        "log_time": pd.Timestamp("2026-04-06 12:00:00.000000000"),
        "message": "test log test-001",
        "severity_text": "INFO",
        "severity_number": 9,
        "scope_name": "telemetry_test_generators",
        "log_iostream": "stdout",
        "code_filepath": "/python/telemetry_test_generators.py",
        "code_function": "generate_test_logs",
        "code_lineno": "42",
        "code_namespace": None,
        "thread_id": None,
        "thread_name": None,
        "exception_message": None,
        "exception_type": None,
        "exception_stacktrace": None,
        "exception_escaped": None,
        "RECORD_ATTRIBUTES": {
            "code.filepath": "/python/telemetry_test_generators.py",
            "code.function": "generate_test_logs",
            "code.lineno": 42,
        },
        "RESOURCE_ATTRIBUTES": {
            "snow.executable.type": "PROCEDURE",
            "snow.executable.name": "GENERATE_TEST_LOGS",
            "snow.warehouse.name": "SPLUNK_APP_DEV_WH",
            "snow.database.name": "SPLUNK_OBSERVABILITY_DEV_APP",
            "snow.schema.name": "APP_PUBLIC",
            "db.user": "NVOITOV",
        },
    }
    base.update(overrides)
    return base


class TestMapLogChunkHappyPath:
    def test_log_body_from_message(self):
        df = pd.DataFrame([_log_row()])
        logs = map_log_chunk(df, ACCOUNT)
        assert len(logs) == 1
        assert logs[0].log_record.body == "test log test-001"

    def test_db_and_snowflake_enrichment(self):
        df = pd.DataFrame([_log_row()])
        logs = map_log_chunk(df, ACCOUNT)
        lr = logs[0].log_record
        assert lr.attributes[DB_SYSTEM_NAME] == "snowflake"
        assert (
            lr.attributes[DB_NAMESPACE] == "SPLUNK_OBSERVABILITY_DEV_APP|APP_PUBLIC"
        )
        assert lr.attributes[SNOWFLAKE_ACCOUNT_NAME] == ACCOUNT
        assert lr.attributes[SNOWFLAKE_RECORD_TYPE] == "LOG"

    def test_no_redundant_snowflake_aliases(self):
        """Raw snow.* attributes should NOT be duplicated as snowflake.* aliases."""
        df = pd.DataFrame([_log_row()])
        logs = map_log_chunk(df, ACCOUNT)
        lr = logs[0].log_record

        assert "snowflake.database.name" not in lr.attributes
        assert "snowflake.schema.name" not in lr.attributes
        assert "snowflake.warehouse.name" not in lr.attributes
        assert "snowflake.query.id" not in lr.attributes

    def test_resource_service_name(self):
        df = pd.DataFrame([_log_row()])
        logs = map_log_chunk(df, ACCOUNT)
        assert _get_resource(logs[0]).attributes[SERVICE_NAME] == "GENERATE_TEST_LOGS"

    def test_severity_number_and_text(self):
        df = pd.DataFrame([_log_row()])
        logs = map_log_chunk(df, ACCOUNT)
        lr = logs[0].log_record
        assert lr.severity_number == SeverityNumber.INFO
        assert lr.severity_text == "INFO"

    def test_scope_name_from_projected_column(self):
        df = pd.DataFrame([_log_row()])
        logs = map_log_chunk(df, ACCOUNT)
        assert logs[0].instrumentation_scope.name == "telemetry_test_generators"

    def test_timestamp_nanoseconds(self):
        df = pd.DataFrame([_log_row()])
        logs = map_log_chunk(df, ACCOUNT)
        assert logs[0].log_record.timestamp > 0

    def test_no_trace_or_span_id_invented(self):
        df = pd.DataFrame([_log_row()])
        logs = map_log_chunk(df, ACCOUNT)
        lr = logs[0].log_record
        assert lr.trace_id == 0
        assert lr.span_id == 0

    def test_original_attributes_preserved(self):
        df = pd.DataFrame([_log_row()])
        logs = map_log_chunk(df, ACCOUNT)
        assert (
            logs[0].log_record.attributes["code.filepath"]
            == "/python/telemetry_test_generators.py"
        )


class TestExceptionLogHandling:
    def test_exception_log_body_from_exception_message(self):
        df = pd.DataFrame(
            [
                _log_row(
                    message=None,
                    exception_message="deliberate_test_exception_001",
                    exception_type="RuntimeError",
                    exception_stacktrace="Traceback...",
                    RECORD_ATTRIBUTES={
                        "exception.type": "RuntimeError",
                        "exception.message": "deliberate_test_exception_001",
                        "exception.stacktrace": "Traceback...",
                    },
                )
            ]
        )
        logs = map_log_chunk(df, ACCOUNT)
        assert len(logs) == 1
        assert logs[0].log_record.body == "deliberate_test_exception_001"

    def test_exception_attributes_populated(self):
        df = pd.DataFrame(
            [
                _log_row(
                    exception_type="RuntimeError",
                    exception_message="deliberate_test_exception_001",
                    exception_stacktrace="Traceback...",
                    RECORD_ATTRIBUTES={
                        "exception.type": "RuntimeError",
                        "exception.message": "deliberate_test_exception_001",
                    },
                )
            ]
        )
        logs = map_log_chunk(df, ACCOUNT)
        attrs = logs[0].log_record.attributes
        assert attrs[EXCEPTION_TYPE] == "RuntimeError"
        assert attrs[EXCEPTION_MESSAGE] == "deliberate_test_exception_001"
        assert attrs[EXCEPTION_STACKTRACE] == "Traceback..."


class TestSeverityFallback:
    def test_severity_from_text_when_number_null(self):
        df = pd.DataFrame([_log_row(severity_number=None, severity_text="ERROR")])
        logs = map_log_chunk(df, ACCOUNT)
        assert logs[0].log_record.severity_number == SeverityNumber.ERROR

    def test_severity_unspecified_when_both_null(self):
        df = pd.DataFrame([_log_row(severity_number=None, severity_text=None)])
        logs = map_log_chunk(df, ACCOUNT)
        assert logs[0].log_record.severity_number == SeverityNumber.UNSPECIFIED


class TestNullAndEmptyHandling:
    def test_empty_dataframe_returns_empty_list(self):
        assert map_log_chunk(pd.DataFrame(), ACCOUNT) == []

    def test_null_record_attributes(self):
        df = pd.DataFrame([_log_row(RECORD_ATTRIBUTES=None)])
        logs = map_log_chunk(df, ACCOUNT)
        assert len(logs) == 1

    def test_null_resource_attributes(self):
        df = pd.DataFrame([_log_row(RESOURCE_ATTRIBUTES=None)])
        logs = map_log_chunk(df, ACCOUNT)
        assert len(logs) == 1
        assert (
            _get_resource(logs[0]).attributes[SERVICE_NAME]
            == "splunk-snowflake-native-app"
        )

    def test_nullish_resource_members_are_filtered_before_resource_creation(
        self, caplog
    ):
        df = pd.DataFrame(
            [
                _log_row(
                    RESOURCE_ATTRIBUTES={
                        "snow.application.name": "SPLUNK_OBSERVABILITY_DEV_APP",
                        "nullish.attr": pd.NA,
                        "none.attr": None,
                    }
                )
            ]
        )
        with caplog.at_level(logging.WARNING, logger="opentelemetry.attributes"):
            logs = map_log_chunk(df, ACCOUNT)

        attrs = _get_resource(logs[0]).attributes
        assert attrs["snow.application.name"] == "SPLUNK_OBSERVABILITY_DEV_APP"
        assert "nullish.attr" not in attrs
        assert "none.attr" not in attrs
        assert not any("Invalid type" in record.message for record in caplog.records)

    def test_scope_name_fallback_when_null(self):
        df = pd.DataFrame([_log_row(scope_name=None)])
        logs = map_log_chunk(df, ACCOUNT)
        assert (
            logs[0].instrumentation_scope.name
            == "splunk.snowflake.native_app.telemetry_mapper"
        )

    def test_pandas_na_values_do_not_leak_into_log_attrs(self):
        df = pd.DataFrame(
            [
                _log_row(
                    RECORD_ATTRIBUTES={
                        "code.filepath": "/python/telemetry_test_generators.py",
                        "nullish.attr": pd.NA,
                    }
                )
            ]
        )
        logs = map_log_chunk(df, ACCOUNT)
        attrs = logs[0].log_record.attributes

        assert "nullish.attr" not in attrs
        assert attrs["code.filepath"] == "/python/telemetry_test_generators.py"


class TestMandatoryRoutingFields:
    def test_all_routing_fields_present(self):
        df = pd.DataFrame([_log_row()])
        logs = map_log_chunk(df, ACCOUNT)
        lr = logs[0].log_record
        assert lr.attributes[DB_SYSTEM_NAME] == "snowflake"
        assert lr.attributes[SNOWFLAKE_ACCOUNT_NAME] == ACCOUNT
        assert _get_resource(logs[0]).attributes[SERVICE_NAME] is not None
        assert lr.attributes[SNOWFLAKE_RECORD_TYPE] == "LOG"
