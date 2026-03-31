"""Unit tests for utils/source_discovery.py."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app" / "streamlit"))

from utils.source_discovery import (
    ACCOUNT_USAGE_MVP_VIEWS,
    CATEGORIES,
    DiscoveredSource,
    PACK_ENABLED_CONFIG_KEYS,
    build_event_table_match_tokens,
    classify_custom_view,
    discover_account_usage_views,
    discover_all_sources,
    discover_custom_views,
    discover_event_tables,
    normalize_view_definition,
    resolve_saved_poll_states,
    source_slug,
)


class TestCategoryDefinitions:
    def test_two_categories_defined(self):
        assert len(CATEGORIES) == 2

    def test_distributed_tracing_is_event_table(self):
        dt = next(category for category in CATEGORIES if category.key == "distributed_tracing")
        assert dt.source_family == "event_table"
        assert dt.name == "Distributed Tracing"

    def test_query_performance_is_account_usage(self):
        qp = next(category for category in CATEGORIES if category.key == "query_performance")
        assert qp.source_family == "account_usage"
        assert qp.name == "Query Performance & Execution"

    def test_mvp_views_list(self):
        assert set(ACCOUNT_USAGE_MVP_VIEWS) == {
            "QUERY_HISTORY",
            "TASK_HISTORY",
            "COMPLETE_TASK_GRAPHS",
            "LOCK_WAIT_HISTORY",
        }

    def test_pack_enabled_config_keys(self):
        assert set(PACK_ENABLED_CONFIG_KEYS) == {
            "pack_enabled.distributed_tracing",
            "pack_enabled.query_performance",
        }


class TestCustomViewClassification:
    def test_account_usage_reference(self):
        defn = "SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY WHERE ..."
        assert classify_custom_view(defn) == "query_performance"

    def test_account_usage_schema_qualified_reference(self):
        defn = "SELECT * FROM ACCOUNT_USAGE.QUERY_HISTORY WHERE ..."
        assert classify_custom_view(defn) == "query_performance"

    def test_bare_view_name_reference_is_excluded(self):
        defn = "SELECT * FROM some_db.public.v_query_history WHERE QUERY_HISTORY ..."
        assert classify_custom_view(defn) is None

    def test_case_insensitive(self):
        defn = "select * from snowflake.account_usage.task_history"
        assert classify_custom_view(defn) == "query_performance"

    def test_unsupported_account_usage_view_is_excluded(self):
        defn = "SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY"
        assert classify_custom_view(defn) is None

    def test_event_table_reference(self):
        event_tables = [
            DiscoveredSource(
                "SNOWFLAKE.TELEMETRY.EVENTS",
                "SNOWFLAKE.TELEMETRY.EVENTS",
                "distributed_tracing",
                False,
                "",
                "",
            ),
        ]
        tokens = build_event_table_match_tokens(event_tables)
        defn = "SELECT * FROM SNOWFLAKE.TELEMETRY.EVENTS WHERE ..."
        assert classify_custom_view(defn, tokens) == "distributed_tracing"

    def test_custom_event_table_reference_uses_schema_qualified_match(self):
        event_tables = [
            DiscoveredSource(
                "HEALTHCARE_DB.OBSERVABILITY.TEST_EVENTS",
                "HEALTHCARE_DB.OBSERVABILITY.TEST_EVENTS",
                "distributed_tracing",
                False,
                "",
                "",
            ),
        ]
        tokens = build_event_table_match_tokens(event_tables)
        defn = 'SELECT * FROM "OBSERVABILITY"."TEST_EVENTS"'
        assert classify_custom_view(defn, tokens) == "distributed_tracing"

    def test_et_takes_priority_over_au(self):
        event_tables = [
            DiscoveredSource(
                "SNOWFLAKE.TELEMETRY.EVENTS",
                "SNOWFLAKE.TELEMETRY.EVENTS",
                "distributed_tracing",
                False,
                "",
                "",
            ),
        ]
        tokens = build_event_table_match_tokens(event_tables)
        defn = "SELECT * FROM SNOWFLAKE.TELEMETRY.EVENTS JOIN ACCOUNT_USAGE.QUERY_HISTORY"
        assert classify_custom_view(defn, tokens) == "distributed_tracing"

    def test_unrelated_view_returns_none(self):
        assert classify_custom_view("SELECT col1 FROM my_db.public.some_table") is None

    def test_none_definition_returns_none(self):
        assert classify_custom_view(None) is None

    def test_empty_definition_returns_none(self):
        assert classify_custom_view("") is None

    def test_normalize_view_definition_strips_quotes(self):
        defn = 'SELECT * FROM "SNOWFLAKE"."ACCOUNT_USAGE"."QUERY_HISTORY"'
        assert normalize_view_definition(defn) == (
            "SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY"
        )


class TestDiscoverEventTables:
    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        session.sql.return_value.collect.return_value = []
        return session

    def test_empty_result(self, mock_session):
        assert discover_event_tables(mock_session) == []

    def test_event_table_uses_fqn_for_view_name(self, mock_session):
        mock_session.sql.return_value.collect.return_value = [
            ("SNOWFLAKE", "TELEMETRY", "EVENTS"),
        ]
        result = discover_event_tables(mock_session)
        assert len(result) == 1
        source = result[0]
        assert source.view_name == "SNOWFLAKE.TELEMETRY.EVENTS"
        assert source.fqn == "SNOWFLAKE.TELEMETRY.EVENTS"
        assert source.category == "distributed_tracing"
        assert source.is_custom is False
        assert source.telemetry_types == ""
        assert source.telemetry_sources == ""

    def test_multiple_event_tables(self, mock_session):
        mock_session.sql.return_value.collect.return_value = [
            ("HEALTHCARE_DB", "OBSERVABILITY", "TEST_EVENTS"),
            ("SNOWFLAKE", "LOCAL", "AI_OBSERVABILITY_EVENTS"),
            ("SNOWFLAKE", "TELEMETRY", "EVENTS"),
        ]
        result = discover_event_tables(mock_session)
        assert len(result) == 3
        names = [source.view_name for source in result]
        assert "HEALTHCARE_DB.OBSERVABILITY.TEST_EVENTS" in names
        assert "SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS" in names
        assert "SNOWFLAKE.TELEMETRY.EVENTS" in names


class TestDiscoverAccountUsageViews:
    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        session.sql.return_value.collect.return_value = []
        return session

    def test_all_four_views_present(self, mock_session):
        mock_session.sql.return_value.collect.return_value = [
            ("COMPLETE_TASK_GRAPHS",),
            ("LOCK_WAIT_HISTORY",),
            ("QUERY_HISTORY",),
            ("TASK_HISTORY",),
        ]
        result = discover_account_usage_views(mock_session)
        assert len(result) == 4
        names = {source.view_name for source in result}
        assert names == {
            "SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY",
            "SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY",
            "SNOWFLAKE.ACCOUNT_USAGE.COMPLETE_TASK_GRAPHS",
            "SNOWFLAKE.ACCOUNT_USAGE.LOCK_WAIT_HISTORY",
        }

    def test_all_sources_are_query_performance(self, mock_session):
        mock_session.sql.return_value.collect.return_value = [("QUERY_HISTORY",)]
        result = discover_account_usage_views(mock_session)
        assert result[0].category == "query_performance"
        assert result[0].is_custom is False

    def test_uses_parameterized_query(self, mock_session):
        discover_account_usage_views(mock_session)
        call_args = mock_session.sql.call_args
        assert call_args[1]["params"] == list(ACCOUNT_USAGE_MVP_VIEWS)


class TestDiscoverCustomViews:
    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        session.sql.return_value.collect.return_value = []
        return session

    def test_empty_result(self, mock_session):
        assert discover_custom_views(mock_session, []) == []

    def test_au_custom_view(self, mock_session):
        mock_session.sql.return_value.collect.return_value = [
            (
                "MY_DB",
                "PUBLIC",
                "MY_QUERY_HIST",
                "SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY",
            ),
        ]
        result = discover_custom_views(mock_session, [])
        assert len(result) == 1
        source = result[0]
        assert source.category == "query_performance"
        assert source.is_custom is True
        assert source.fqn == "MY_DB.PUBLIC.MY_QUERY_HIST"

    def test_unsupported_account_usage_view_is_excluded(self, mock_session):
        mock_session.sql.return_value.collect.return_value = [
            (
                "MY_DB",
                "PUBLIC",
                "MY_LOGIN_VIEW",
                "SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY",
            ),
        ]
        assert discover_custom_views(mock_session, []) == []

    def test_default_event_table_custom_view(self, mock_session):
        mock_session.sql.return_value.collect.return_value = [
            (
                "MY_DB",
                "PUBLIC",
                "MY_TRACES",
                "SELECT * FROM SNOWFLAKE.TELEMETRY.EVENTS WHERE ...",
            ),
        ]
        event_tables = [
            DiscoveredSource(
                "SNOWFLAKE.TELEMETRY.EVENTS",
                "SNOWFLAKE.TELEMETRY.EVENTS",
                "distributed_tracing",
                False,
                "",
                "",
            ),
        ]
        result = discover_custom_views(mock_session, event_tables)
        assert len(result) == 1
        assert result[0].category == "distributed_tracing"
        assert result[0].view_name == "MY_DB.PUBLIC.MY_TRACES"

    def test_custom_event_table_view_is_discovered(self, mock_session):
        mock_session.sql.return_value.collect.return_value = [
            (
                "MY_DB",
                "PUBLIC",
                "MY_CUSTOM_EVENT_VIEW",
                'SELECT * FROM "OBSERVABILITY"."TEST_EVENTS"',
            ),
        ]
        event_tables = [
            DiscoveredSource(
                "HEALTHCARE_DB.OBSERVABILITY.TEST_EVENTS",
                "HEALTHCARE_DB.OBSERVABILITY.TEST_EVENTS",
                "distributed_tracing",
                False,
                "",
                "",
            ),
        ]
        result = discover_custom_views(mock_session, event_tables)
        assert len(result) == 1
        assert result[0].category == "distributed_tracing"

    def test_unclassified_view_excluded(self, mock_session):
        mock_session.sql.return_value.collect.return_value = [
            ("DB", "SCH", "V", "SELECT 1"),
        ]
        assert discover_custom_views(mock_session, []) == []


class TestDiscoverAllSources:
    def test_groups_by_category(self):
        session = MagicMock()
        event_table_rows = [
            ("SNOWFLAKE", "TELEMETRY", "EVENTS"),
            ("HEALTHCARE_DB", "OBS", "TEST_EVENTS"),
        ]
        account_usage_rows = [("QUERY_HISTORY",), ("TASK_HISTORY",)]
        custom_rows = []
        call_count = 0

        def sql_side_effect(query, **kwargs):
            nonlocal call_count
            result = MagicMock()
            if call_count == 0:
                result.collect.return_value = event_table_rows
            elif call_count == 1:
                result.collect.return_value = account_usage_rows
            else:
                result.collect.return_value = custom_rows
            call_count += 1
            return result

        session.sql.side_effect = sql_side_effect
        grouped = discover_all_sources(session)

        assert len(grouped["distributed_tracing"]) == 2
        assert len(grouped["query_performance"]) == 2
        assert all(source.category == "distributed_tracing" for source in grouped["distributed_tracing"])
        assert all(source.category == "query_performance" for source in grouped["query_performance"])


class TestDiscoveredSourceModel:
    def test_fqn_is_shown_in_view_name(self):
        source = DiscoveredSource(
            view_name="SNOWFLAKE.TELEMETRY.EVENTS",
            fqn="SNOWFLAKE.TELEMETRY.EVENTS",
            category="distributed_tracing",
            is_custom=False,
            telemetry_types="",
            telemetry_sources="",
        )
        assert source.view_name == "SNOWFLAKE.TELEMETRY.EVENTS"
        assert source.telemetry_types == ""
        assert source.telemetry_sources == ""


class TestPersistedPollStateLogic:
    """Poll state is decoupled from the category toggle.

    ``resolve_saved_poll_states`` returns the user's persisted checkbox
    selections regardless of whether the parent category is enabled or
    disabled.  Unknown (newly discovered) sources default to ``False``.
    """

    def test_no_saved_state_defaults_all_polls_false(self):
        sources = [
            DiscoveredSource("X.Y.A", "X.Y.A", "distributed_tracing", False, "", ""),
            DiscoveredSource("X.Y.B", "X.Y.B", "distributed_tracing", False, "", ""),
        ]
        assert resolve_saved_poll_states(sources, {}) == [False, False]

    def test_unsaved_sources_default_to_false(self):
        sources = [
            DiscoveredSource("X.Y.A", "X.Y.A", "distributed_tracing", False, "", ""),
            DiscoveredSource("X.Y.B", "X.Y.B", "distributed_tracing", False, "", ""),
        ]
        assert resolve_saved_poll_states(sources, {}) == [False, False]

    def test_restores_saved_polls(self):
        sources = [
            DiscoveredSource("X.Y.A", "X.Y.A", "distributed_tracing", False, "", ""),
            DiscoveredSource("X.Y.B", "X.Y.B", "distributed_tracing", False, "", ""),
        ]
        assert resolve_saved_poll_states(
            sources,
            {"X.Y.A": True, "X.Y.B": False},
        ) == [True, False]

    def test_saved_true_values_preserved_regardless_of_pack_state(self):
        """Checkbox state is independent of the category toggle."""
        sources = [
            DiscoveredSource("X.Y.A", "X.Y.A", "distributed_tracing", False, "", ""),
            DiscoveredSource("X.Y.B", "X.Y.B", "distributed_tracing", False, "", ""),
        ]
        assert resolve_saved_poll_states(
            sources,
            {"X.Y.A": True, "X.Y.B": True},
        ) == [True, True]

    def test_mixed_saved_and_new_sources(self):
        sources = [
            DiscoveredSource("X.Y.A", "X.Y.A", "distributed_tracing", False, "", ""),
            DiscoveredSource("X.Y.B", "X.Y.B", "distributed_tracing", False, "", ""),
            DiscoveredSource("X.Y.NEW", "X.Y.NEW", "distributed_tracing", False, "", ""),
        ]
        assert resolve_saved_poll_states(
            sources,
            {"X.Y.A": True, "X.Y.B": False},
        ) == [True, False, False]

    def test_source_slug_is_config_safe(self):
        assert source_slug("SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY") == (
            "snowflake_account_usage_query_history"
        )

    def test_source_slug_normalizes_custom_view_name(self):
        assert source_slug("My DB.Public.Custom-View") == "my_db_public_custom_view"


class TestSaveAndRestoreRoundTrip:
    """Verify that saved poll states can be reconstructed from config keys."""

    def test_slug_round_trip_for_account_usage(self):
        fqn = "SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY"
        slug = source_slug(fqn)
        config_key = f"source.{slug}.view_fqn"
        assert slug == "snowflake_account_usage_query_history"
        assert config_key == "source.snowflake_account_usage_query_history.view_fqn"

    def test_slug_round_trip_for_event_table(self):
        fqn = "SNOWFLAKE.TELEMETRY.EVENTS"
        slug = source_slug(fqn)
        poll_key = f"source.{slug}.poll"
        assert poll_key == "source.snowflake_telemetry_events.poll"

    def test_resolve_from_simulated_config_load(self):
        """Simulate loading saved config and resolving poll states."""
        sources = [
            DiscoveredSource("SNOWFLAKE.TELEMETRY.EVENTS", "SNOWFLAKE.TELEMETRY.EVENTS",
                             "distributed_tracing", False, "", ""),
            DiscoveredSource("SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY",
                             "SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY",
                             "query_performance", False, "", ""),
        ]

        saved_pairs = {}
        for src, poll_val in zip(sources, [True, False]):
            slug = source_slug(src.fqn)
            saved_pairs[f"source.{slug}.view_fqn"] = src.fqn
            saved_pairs[f"source.{slug}.poll"] = str(poll_val).lower()

        slug_to_fqn = {}
        slug_to_poll = {}
        for key, value in saved_pairs.items():
            if key.endswith(".view_fqn"):
                s = key[len("source."):-len(".view_fqn")]
                slug_to_fqn[s] = value
            elif key.endswith(".poll"):
                s = key[len("source."):-len(".poll")]
                slug_to_poll[s] = value.lower() == "true"

        saved_source_polls = {
            fqn: slug_to_poll[s] for s, fqn in slug_to_fqn.items() if s in slug_to_poll
        }

        restored = resolve_saved_poll_states(sources, saved_source_polls)
        assert restored == [True, False]
