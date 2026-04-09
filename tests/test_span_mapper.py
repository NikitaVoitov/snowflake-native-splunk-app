"""Unit tests for span_mapper — Event Table SPAN + SPAN_EVENT → OTel ReadableSpan."""

from __future__ import annotations

import logging

import pandas as pd
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import StatusCode
from span_mapper import (
    map_ai_observability_span_chunk,
    map_span_chunk,
    map_span_events,
)
from telemetry_constants import (
    DB_NAMESPACE,
    DB_OPERATION_NAME,
    DB_SYSTEM_NAME,
    EXCEPTION_MESSAGE,
    EXCEPTION_STACKTRACE,
    EXCEPTION_TYPE,
    GEN_AI_AGENT_NAME,
    GEN_AI_CONVERSATION_ID,
    GEN_AI_OPERATION_NAME,
    GEN_AI_PROVIDER_NAME,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
    SERVICE_NAME,
    SNOWFLAKE_ACCOUNT_NAME,
    SNOWFLAKE_RECORD_TYPE,
)


ACCOUNT = "LFB71918"


def _span_row(**overrides):
    """Build a realistic standard SPAN row dict."""
    base = {
        "trace_id": "0af7651916cd43dd8448eb211c80319c",
        "span_id": "b7ad6b7169203331",
        "span_name": "GENERATE_TEST_SPANS",
        "span_kind": "SPAN_KIND_INTERNAL",
        "parent_span_id": "00f067aa0ba902b7",
        "status_code": "STATUS_CODE_OK",
        "status_message": None,
        "end_time": pd.Timestamp("2026-04-06 12:00:01.000000000"),
        "start_time": pd.Timestamp("2026-04-06 12:00:00.000000000"),
        "db_user": "NVOITOV",
        "exec_type": "PROCEDURE",
        "exec_name": "GENERATE_TEST_SPANS",
        "query_id": "01b6a123-0000-abcd-0000-000000000001",
        "warehouse_name": "SPLUNK_APP_DEV_WH",
        "database_name": "SPLUNK_OBSERVABILITY_DEV_APP",
        "schema_name": "APP_PUBLIC",
        "sdk_language": "python",
        "RECORD_ATTRIBUTES": {
            "test.id": "test-001",
            "snow.auto_instrumented": "true",
        },
        "RESOURCE_ATTRIBUTES": {
            "snow.executable.type": "PROCEDURE",
            "snow.executable.name": "GENERATE_TEST_SPANS",
            "snow.warehouse.name": "SPLUNK_APP_DEV_WH",
            "snow.database.name": "SPLUNK_OBSERVABILITY_DEV_APP",
            "snow.schema.name": "APP_PUBLIC",
            "snow.query.id": "01b6a123-0000-abcd-0000-000000000001",
            "db.user": "NVOITOV",
            "telemetry.sdk.language": "python",
        },
    }
    base.update(overrides)
    return base


def _span_event_row(**overrides):
    """Build a realistic SPAN_EVENT row dict."""
    base = {
        "trace_id": "0af7651916cd43dd8448eb211c80319c",
        "span_id": "b7ad6b7169203331",
        "event_name": "test_event_with_attrs",
        "event_time": pd.Timestamp("2026-04-06 12:00:00.500000000"),
        "exception_message": None,
        "exception_type": None,
        "exception_stacktrace": None,
        "exception_escaped": None,
        "RECORD_ATTRIBUTES": {"test.key1": "value1", "test.key2": "value2"},
        "RESOURCE_ATTRIBUTES": {},
    }
    base.update(overrides)
    return base


class TestMapSpanChunkHappyPath:
    def test_full_attribute_set(self):
        df = pd.DataFrame([_span_row()])
        spans = map_span_chunk(df, ACCOUNT)

        assert len(spans) == 1
        span = spans[0]

        assert DB_SYSTEM_NAME not in span.attributes
        assert SNOWFLAKE_ACCOUNT_NAME not in span.attributes
        assert span.attributes[SNOWFLAKE_RECORD_TYPE] == "SPAN"

        assert span.resource.attributes[DB_SYSTEM_NAME] == "snowflake"
        assert span.resource.attributes[SNOWFLAKE_ACCOUNT_NAME] == ACCOUNT
        assert (
            span.resource.attributes[DB_NAMESPACE]
            == "SPLUNK_OBSERVABILITY_DEV_APP|APP_PUBLIC"
        )
        assert span.resource.attributes[SERVICE_NAME] == "GENERATE_TEST_SPANS"

    def test_no_redundant_snowflake_aliases(self):
        """Raw snow.* attributes should NOT be duplicated as snowflake.* aliases."""
        df = pd.DataFrame([_span_row()])
        spans = map_span_chunk(df, ACCOUNT)
        span = spans[0]

        assert "snowflake.database.name" not in span.attributes
        assert "snowflake.schema.name" not in span.attributes
        assert "snowflake.warehouse.name" not in span.attributes
        assert "snowflake.query.id" not in span.attributes

        assert "snowflake.database.name" not in span.resource.attributes
        assert "snowflake.schema.name" not in span.resource.attributes
        assert "snowflake.warehouse.name" not in span.resource.attributes
        assert "snowflake.query.id" not in span.resource.attributes

    def test_original_snow_attributes_preserved(self):
        df = pd.DataFrame([_span_row()])
        spans = map_span_chunk(df, ACCOUNT)
        span = spans[0]

        assert span.attributes["test.id"] == "test-001"
        assert span.attributes["snow.auto_instrumented"] == "true"

    def test_span_name_enriched_for_procedure(self):
        df = pd.DataFrame([_span_row()])
        spans = map_span_chunk(df, ACCOUNT)
        span = spans[0]

        assert (
            span.name
            == "CALL SPLUNK_OBSERVABILITY_DEV_APP|APP_PUBLIC.GENERATE_TEST_SPANS"
        )

    def test_db_operation_name_procedure(self):
        df = pd.DataFrame([_span_row()])
        spans = map_span_chunk(df, ACCOUNT)
        assert spans[0].attributes[DB_OPERATION_NAME] == "CALL"

    def test_db_operation_name_query(self):
        df = pd.DataFrame([_span_row(exec_type="QUERY", span_name="SELECT")])
        spans = map_span_chunk(df, ACCOUNT)
        assert spans[0].attributes[DB_OPERATION_NAME] == "SELECT"

    def test_db_operation_name_function_with_sql_verb(self):
        df = pd.DataFrame([_span_row(exec_type="FUNCTION", span_name="SELECT")])
        spans = map_span_chunk(df, ACCOUNT)
        assert spans[0].attributes[DB_OPERATION_NAME] == "SELECT"

    def test_db_operation_name_function_without_sql_verb(self):
        df = pd.DataFrame(
            [_span_row(exec_type="FUNCTION", span_name="calculate_score")]
        )
        spans = map_span_chunk(df, ACCOUNT)
        assert DB_OPERATION_NAME not in spans[0].attributes

    def test_parent_span_id_extraction(self):
        df = pd.DataFrame([_span_row()])
        spans = map_span_chunk(df, ACCOUNT)
        span = spans[0]
        assert span.parent is not None
        assert span.parent.span_id == int("00f067aa0ba902b7", 16)

    def test_span_kind_mapping(self):
        df = pd.DataFrame([_span_row(span_kind="SPAN_KIND_SERVER")])
        spans = map_span_chunk(df, ACCOUNT)
        assert spans[0].kind == SpanKind.SERVER

    def test_status_code_mapping(self):
        df = pd.DataFrame(
            [_span_row(status_code="STATUS_CODE_ERROR", status_message="err msg")]
        )
        spans = map_span_chunk(df, ACCOUNT)
        assert spans[0].status.status_code == StatusCode.ERROR
        assert spans[0].status.description == "err msg"

    def test_timestamp_nanoseconds(self):
        df = pd.DataFrame([_span_row()])
        spans = map_span_chunk(df, ACCOUNT)
        assert spans[0].start_time > 0
        assert spans[0].end_time > spans[0].start_time

    def test_trace_span_id_hex_to_int(self):
        df = pd.DataFrame([_span_row()])
        spans = map_span_chunk(df, ACCOUNT)
        ctx = spans[0].context
        assert ctx.trace_id == int("0af7651916cd43dd8448eb211c80319c", 16)
        assert ctx.span_id == int("b7ad6b7169203331", 16)

    def test_events_attached_from_span_events_map(self):
        span_event_df = pd.DataFrame([_span_event_row()])
        events_map = map_span_events(span_event_df)

        df = pd.DataFrame([_span_row()])
        spans = map_span_chunk(df, ACCOUNT, span_events_by_span_id=events_map)
        assert len(spans[0].events) == 1
        assert spans[0].events[0].name == "test_event_with_attrs"
        assert spans[0].events[0].attributes["test.key1"] == "value1"

    def test_pandas_na_values_do_not_leak_into_span_name_or_attrs(self):
        df = pd.DataFrame(
            [
                _span_row(
                    span_name=pd.NA,
                    RECORD_ATTRIBUTES={
                        "test.id": pd.NA,
                        "snow.auto_instrumented": "true",
                    },
                )
            ]
        )
        spans = map_span_chunk(df, ACCOUNT)

        assert spans[0].name == "CALL SPLUNK_OBSERVABILITY_DEV_APP|APP_PUBLIC.GENERATE_TEST_SPANS"
        assert "test.id" not in spans[0].attributes
        assert spans[0].attributes["snow.auto_instrumented"] == "true"


class TestMapSpanEvents:
    def test_non_exception_event(self):
        df = pd.DataFrame([_span_event_row()])
        result = map_span_events(df)
        assert "b7ad6b7169203331" in result
        evts = result["b7ad6b7169203331"]
        assert len(evts) == 1
        assert evts[0].name == "test_event_with_attrs"
        assert evts[0].attributes["test.key1"] == "value1"
        assert evts[0].attributes[SNOWFLAKE_RECORD_TYPE] == "SPAN_EVENT"

    def test_exception_event(self):
        df = pd.DataFrame(
            [
                _span_event_row(
                    event_name="exception",
                    exception_type="100132",
                    exception_message="deliberate_test_exception_001",
                    exception_stacktrace="Traceback (most recent call last)...",
                    RECORD_ATTRIBUTES={"exception.type": "100132"},
                )
            ]
        )
        result = map_span_events(df)
        evts = result["b7ad6b7169203331"]
        assert evts[0].name == "exception"
        assert evts[0].attributes[EXCEPTION_TYPE] == "100132"
        assert evts[0].attributes[EXCEPTION_MESSAGE] == "deliberate_test_exception_001"
        assert (
            evts[0].attributes[EXCEPTION_STACKTRACE]
            == "Traceback (most recent call last)..."
        )
        assert evts[0].attributes[SNOWFLAKE_RECORD_TYPE] == "SPAN_EVENT"

    def test_exception_event_preserves_existing_exception_attributes(self):
        df = pd.DataFrame(
            [
                _span_event_row(
                    event_name="exception",
                    exception_type="RuntimeError",
                    exception_message="boom",
                    exception_stacktrace="Traceback...",
                    exception_escaped=True,
                    RECORD_ATTRIBUTES={
                        "exception.type": "RuntimeError",
                        "exception.message": "boom",
                        "exception.stacktrace": "Traceback...",
                        "exception.escaped": True,
                        "custom.detail": "keep-me",
                    },
                )
            ]
        )
        result = map_span_events(df)
        attrs = result["b7ad6b7169203331"][0].attributes

        assert attrs["exception.escaped"] is True
        assert attrs["custom.detail"] == "keep-me"

    def test_empty_dataframe(self):
        df = pd.DataFrame()
        assert map_span_events(df) == {}


class TestMapAiObservabilitySpanChunk:
    def _ai_row(self, **overrides):
        base = {
            "trace_id": "0af7651916cd43dd8448eb211c80319c",
            "span_id": "b7ad6b7169203331",
            "span_name": "generation",
            "span_kind": "SPAN_KIND_INTERNAL",
            "parent_span_id": None,
            "status_code": "STATUS_CODE_OK",
            "end_time": pd.Timestamp("2026-04-06 12:00:01"),
            "start_time": pd.Timestamp("2026-04-06 12:00:00"),
            "span_type": "generation",
            "agent_name": "my_agent",
            "object_type": "cortex_complete",
            "run_name": None,
            "record_id": None,
            "RECORD_ATTRIBUTES": {
                "ai.observability.cost.model": "claude-3-5-sonnet",
                "ai.observability.cost.num_prompt_tokens": 100,
                "ai.observability.cost.num_completion_tokens": 50,
            },
            "RESOURCE_ATTRIBUTES": {
                "snow.application.name": "SPLUNK_OBSERVABILITY_DEV_APP",
            },
        }
        base.update(overrides)
        return base

    def test_gen_ai_attributes_populated(self):
        df = pd.DataFrame([self._ai_row()])
        spans = map_ai_observability_span_chunk(df, ACCOUNT)
        assert len(spans) == 1
        span = spans[0]

        assert span.attributes[GEN_AI_REQUEST_MODEL] == "claude-3-5-sonnet"
        assert span.attributes[GEN_AI_USAGE_INPUT_TOKENS] == 100
        assert span.attributes[GEN_AI_USAGE_OUTPUT_TOKENS] == 50
        assert span.attributes[GEN_AI_AGENT_NAME] == "my_agent"
        assert span.attributes[GEN_AI_PROVIDER_NAME] == "snowflake"
        assert span.attributes[GEN_AI_OPERATION_NAME] == "chat"

    def test_span_name_pattern(self):
        df = pd.DataFrame([self._ai_row()])
        spans = map_ai_observability_span_chunk(df, ACCOUNT)
        assert spans[0].name == "chat claude-3-5-sonnet"

    def test_standard_gen_ai_keys_take_precedence(self):
        ra = {
            "gen_ai.request.model": "gpt-4",
            "ai.observability.cost.model": "claude-3-5-sonnet",
            "gen_ai.usage.input_tokens": 200,
            "ai.observability.cost.num_prompt_tokens": 100,
        }
        df = pd.DataFrame([self._ai_row(RECORD_ATTRIBUTES=ra)])
        spans = map_ai_observability_span_chunk(df, ACCOUNT)
        assert spans[0].attributes[GEN_AI_REQUEST_MODEL] == "gpt-4"
        assert spans[0].attributes[GEN_AI_USAGE_INPUT_TOKENS] == 200

    def test_gen_ai_conversation_id_preserved(self):
        ra = {
            "gen_ai.conversation.id": "conv-abc-123",
            "ai.observability.cost.model": "claude-3-5-sonnet",
        }
        df = pd.DataFrame([self._ai_row(RECORD_ATTRIBUTES=ra)])
        spans = map_ai_observability_span_chunk(df, ACCOUNT)
        assert spans[0].attributes[GEN_AI_CONVERSATION_ID] == "conv-abc-123"

    def test_mandatory_routing_fields(self):
        df = pd.DataFrame([self._ai_row()])
        spans = map_ai_observability_span_chunk(df, ACCOUNT)
        span = spans[0]
        assert DB_SYSTEM_NAME not in span.attributes
        assert SNOWFLAKE_ACCOUNT_NAME not in span.attributes
        assert span.resource.attributes[DB_SYSTEM_NAME] == "snowflake"
        assert span.resource.attributes[SNOWFLAKE_ACCOUNT_NAME] == ACCOUNT
        assert span.resource.attributes[SERVICE_NAME] == "SPLUNK_OBSERVABILITY_DEV_APP"
        assert span.attributes[SNOWFLAKE_RECORD_TYPE] == "SPAN"


class TestNullAndEmptyHandling:
    def test_empty_dataframe_returns_empty_list(self):
        assert map_span_chunk(pd.DataFrame(), ACCOUNT) == []

    def test_null_record_attributes(self):
        df = pd.DataFrame([_span_row(RECORD_ATTRIBUTES=None)])
        spans = map_span_chunk(df, ACCOUNT)
        assert len(spans) == 1
        assert DB_SYSTEM_NAME not in spans[0].attributes
        assert spans[0].resource.attributes[DB_SYSTEM_NAME] == "snowflake"

    def test_null_resource_attributes(self):
        df = pd.DataFrame([_span_row(RESOURCE_ATTRIBUTES=None)])
        spans = map_span_chunk(df, ACCOUNT)
        assert len(spans) == 1
        assert (
            spans[0].resource.attributes[SERVICE_NAME] == "splunk-snowflake-native-app"
        )

    def test_nullish_resource_members_are_filtered_before_resource_creation(
        self, caplog
    ):
        df = pd.DataFrame(
            [
                _span_row(
                    RESOURCE_ATTRIBUTES={
                        "snow.application.name": "SPLUNK_OBSERVABILITY_DEV_APP",
                        "nullish.attr": pd.NA,
                        "none.attr": None,
                    }
                )
            ]
        )
        with caplog.at_level(logging.WARNING, logger="opentelemetry.attributes"):
            spans = map_span_chunk(df, ACCOUNT)

        attrs = spans[0].resource.attributes
        assert attrs["snow.application.name"] == "SPLUNK_OBSERVABILITY_DEV_APP"
        assert "nullish.attr" not in attrs
        assert "none.attr" not in attrs
        assert not any("Invalid type" in record.message for record in caplog.records)

    def test_missing_trace_id_skips_row(self):
        df = pd.DataFrame([_span_row(trace_id=None)])
        assert map_span_chunk(df, ACCOUNT) == []

    def test_missing_span_id_skips_row(self):
        df = pd.DataFrame([_span_row(span_id=None)])
        assert map_span_chunk(df, ACCOUNT) == []

    def test_no_parent_span_id(self):
        df = pd.DataFrame([_span_row(parent_span_id=None)])
        spans = map_span_chunk(df, ACCOUNT)
        assert spans[0].parent is None

    def test_variant_as_json_string(self):
        df = pd.DataFrame(
            [
                _span_row(
                    RECORD_ATTRIBUTES='{"custom.key": "json_value"}',
                    RESOURCE_ATTRIBUTES='{"snow.database.name": "TESTDB"}',
                )
            ]
        )
        spans = map_span_chunk(df, ACCOUNT)
        assert spans[0].attributes["custom.key"] == "json_value"


class TestMandatoryRoutingFields:
    def test_all_routing_fields_present(self):
        df = pd.DataFrame([_span_row()])
        spans = map_span_chunk(df, ACCOUNT)
        span = spans[0]

        assert DB_SYSTEM_NAME not in span.attributes
        assert SNOWFLAKE_ACCOUNT_NAME not in span.attributes
        assert span.resource.attributes[DB_SYSTEM_NAME] == "snowflake"
        assert span.resource.attributes[SNOWFLAKE_ACCOUNT_NAME] == ACCOUNT
        assert span.resource.attributes[SERVICE_NAME] is not None
        assert span.attributes[SNOWFLAKE_RECORD_TYPE] == "SPAN"
