"""Unit tests for the real helpers in ``pages/telemetry_sources.py``."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from snowflake.snowpark.exceptions import SnowparkSQLException


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app" / "streamlit"))

from utils.source_discovery import CATEGORIES, DiscoveredSource, source_slug


class _SessionState(dict):
    """Small stand-in for Streamlit's session-state container."""

    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError as exc:  # pragma: no cover - defensive parity
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value) -> None:
        self[name] = value


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeStreamlit(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("streamlit")
        self.session_state = _SessionState()
        self.rerun_count = 0

    def markdown(self, *args, **kwargs) -> None:
        return None

    def header(self, *args, **kwargs) -> None:
        return None

    def caption(self, *args, **kwargs) -> None:
        return None

    def error(self, *args, **kwargs) -> None:
        return None

    def warning(self, *args, **kwargs) -> None:
        return None

    def info(self, *args, **kwargs) -> None:
        return None

    def divider(self, *args, **kwargs) -> None:
        return None

    def toast(self, *args, **kwargs) -> None:
        return None

    def button(self, *args, **kwargs) -> bool:
        return False

    def toggle(self, *args, **kwargs) -> bool:
        return False

    def data_editor(self, *args, **kwargs) -> None:
        return None

    def columns(self, spec, **kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        return [_NullContext() for _ in range(count)]

    def container(self, **kwargs) -> _NullContext:
        return _NullContext()

    def fragment(self, func=None, **kwargs):
        if func is None:
            return lambda inner: inner
        return func

    def rerun(self) -> None:
        self.rerun_count += 1


@pytest.fixture
def telemetry_page(monkeypatch):
    fake_streamlit = _FakeStreamlit()

    fake_config = types.ModuleType("utils.config")
    fake_config.load_config_like = lambda session, prefix: {}
    fake_config.save_config = lambda session, key, value: None
    fake_config.save_config_batch = lambda session, pairs: None

    fake_snowflake = types.ModuleType("utils.snowflake")
    fake_snowflake.get_session = lambda: None

    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
    monkeypatch.setitem(sys.modules, "utils.config", fake_config)
    monkeypatch.setitem(sys.modules, "utils.snowflake", fake_snowflake)
    monkeypatch.delitem(sys.modules, "pages.telemetry_sources", raising=False)

    module = importlib.import_module("pages.telemetry_sources")
    yield module

    monkeypatch.delitem(sys.modules, "pages.telemetry_sources", raising=False)


def _account_usage_category():
    return next(cat for cat in CATEGORIES if cat.source_family == "account_usage")


def _event_table_category():
    return next(cat for cat in CATEGORIES if cat.source_family == "event_table")


def _make_source(
    fqn: str,
    category: str,
    *,
    is_custom: bool = False,
    parent_account_usage_view: str | None = None,
) -> DiscoveredSource:
    return DiscoveredSource(
        fqn,
        fqn,
        category,
        is_custom,
        "",
        "",
        parent_account_usage_view,
    )


def _prime_session_state_for_reset(
    module,
    grouped: dict[str, list[DiscoveredSource]],
) -> None:
    for category in CATEGORIES:
        sources = grouped.get(category.key, [])
        polls = [False] * len(sources)
        module.st.session_state[module._ss_df_key(category.key)] = module._build_category_df(
            sources,
            polls,
            category,
        )
        module.st.session_state[module._ss_pack_key(category.key)] = True
        module.st.session_state[module._ss_editor_version_key(category.key)] = 0


class TestTelemetrySourcesPageHelpers:
    def test_build_category_df_uses_parent_view_defaults_for_custom_au(self, telemetry_page):
        category = _account_usage_category()
        sources = [
            _make_source(
                "MY_DB.PUBLIC.MY_LOCKS",
                category.key,
                is_custom=True,
                parent_account_usage_view="LOCK_WAIT_HISTORY",
            ),
        ]

        df = telemetry_page._build_category_df(sources, [True], category)

        assert list(df.columns) == telemetry_page._ALL_DF_COLUMNS
        assert df["interval_seconds"].iloc[0] == 900
        assert df["overlap_minutes"].iloc[0] == 66

    def test_display_columns_uses_real_module_logic(self, telemetry_page):
        au_category = _account_usage_category()
        et_category = _event_table_category()
        au_df = telemetry_page._build_category_df(
            [_make_source("SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY", au_category.key)],
            [False],
            au_category,
        )
        et_df = telemetry_page._build_category_df(
            [_make_source("SNOWFLAKE.TELEMETRY.EVENTS", et_category.key)],
            [False],
            et_category,
        )

        assert telemetry_page._display_columns(au_df, au_category) == [
            "poll",
            "view_name",
            "interval_seconds",
            "overlap_minutes",
        ]
        assert telemetry_page._display_columns(et_df, et_category) == [
            "poll",
            "view_name",
            "interval_seconds",
        ]

    def test_effective_values_reads_real_editor_state(self, telemetry_page):
        category = _account_usage_category()
        df = telemetry_page._build_category_df(
            [
                _make_source("SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY", category.key),
                _make_source("SNOWFLAKE.ACCOUNT_USAGE.LOCK_WAIT_HISTORY", category.key),
            ],
            [False, False],
            category,
        )
        editor_key = telemetry_page._editor_key(category.key)
        telemetry_page.st.session_state[editor_key] = {
            "edited_rows": {
                "1": {
                    "interval_seconds": 3600,
                    "overlap_minutes": 120,
                },
            },
        }

        intervals = telemetry_page._effective_values(df, editor_key, "interval_seconds")
        overlaps = telemetry_page._effective_values(df, editor_key, "overlap_minutes")

        assert list(intervals) == [900, 3600]
        assert list(overlaps) == [50, 120]

    def test_apply_pack_state_consolidates_interval_and_overlap_edits(self, telemetry_page):
        category = _account_usage_category()
        df_key = telemetry_page._ss_df_key(category.key)
        editor_key = telemetry_page._editor_key(category.key)
        version_key = telemetry_page._ss_editor_version_key(category.key)

        telemetry_page.st.session_state[version_key] = 0
        telemetry_page.st.session_state[df_key] = telemetry_page._build_category_df(
            [
                _make_source("SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY", category.key),
                _make_source("SNOWFLAKE.ACCOUNT_USAGE.LOCK_WAIT_HISTORY", category.key),
            ],
            [False, False],
            category,
        )
        telemetry_page.st.session_state[editor_key] = {
            "edited_rows": {
                "0": {"poll": True, "interval_seconds": 120},
                "1": {"overlap_minutes": 100},
            },
        }

        telemetry_page._apply_pack_state(category.key, True)

        updated_df = telemetry_page.st.session_state[df_key]
        assert bool(updated_df["poll"].iloc[0]) is True
        assert updated_df["interval_seconds"].iloc[0] == 120
        assert updated_df["overlap_minutes"].iloc[1] == 100
        assert telemetry_page.st.session_state[version_key] == 1
        assert editor_key not in telemetry_page.st.session_state

    def test_reset_to_defaults_restores_real_module_defaults(self, telemetry_page):
        au_category = _account_usage_category()
        et_category = _event_table_category()
        grouped = {
            au_category.key: [
                _make_source(
                    "MY_DB.PUBLIC.MY_LOCKS",
                    au_category.key,
                    is_custom=True,
                    parent_account_usage_view="LOCK_WAIT_HISTORY",
                ),
            ],
            et_category.key: [
                _make_source("SNOWFLAKE.TELEMETRY.EVENTS", et_category.key),
            ],
        }
        _prime_session_state_for_reset(telemetry_page, grouped)

        au_df_key = telemetry_page._ss_df_key(au_category.key)
        et_df_key = telemetry_page._ss_df_key(et_category.key)
        telemetry_page.st.session_state[au_df_key].at[0, "poll"] = True
        telemetry_page.st.session_state[au_df_key].at[0, "interval_seconds"] = 120
        telemetry_page.st.session_state[au_df_key].at[0, "overlap_minutes"] = 5
        telemetry_page.st.session_state[et_df_key].at[0, "interval_seconds"] = 600

        telemetry_page._reset_to_defaults(grouped)

        au_df = telemetry_page.st.session_state[au_df_key]
        et_df = telemetry_page.st.session_state[et_df_key]
        assert bool(au_df["poll"].iloc[0]) is False
        assert au_df["interval_seconds"].iloc[0] == 900
        assert au_df["overlap_minutes"].iloc[0] == 66
        assert et_df["interval_seconds"].iloc[0] == 60
        assert et_df["overlap_minutes"].iloc[0] is None
        assert telemetry_page.st.session_state[telemetry_page._ss_pack_key(au_category.key)] is False
        assert telemetry_page.st.session_state[telemetry_page._ss_pack_key(et_category.key)] is False


# ---------------------------------------------------------------------------
# Helpers for persistence round-trip tests
# ---------------------------------------------------------------------------
def _mixed_grouped():
    """Two AU sources and one ET source — the canonical mixed test scenario."""
    au_cat = _account_usage_category()
    et_cat = _event_table_category()
    return {
        au_cat.key: [
            _make_source("SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY", au_cat.key),
            _make_source("SNOWFLAKE.ACCOUNT_USAGE.LOCK_WAIT_HISTORY", au_cat.key),
        ],
        et_cat.key: [
            _make_source("SNOWFLAKE.TELEMETRY.EVENTS", et_cat.key),
        ],
    }


def _setup_for_save(module, grouped, *, au_polls=None, et_polls=None):
    """Prime session state with DataFrames so capture/save can run."""
    au_cat = _account_usage_category()
    et_cat = _event_table_category()
    au_sources = grouped.get(au_cat.key, [])
    et_sources = grouped.get(et_cat.key, [])
    au_polls = au_polls or [False] * len(au_sources)
    et_polls = et_polls or [False] * len(et_sources)

    module.st.session_state[module._ss_df_key(au_cat.key)] = (
        module._build_category_df(au_sources, au_polls, au_cat)
    )
    module.st.session_state[module._ss_df_key(et_cat.key)] = (
        module._build_category_df(et_sources, et_polls, et_cat)
    )
    module.st.session_state[module._ss_pack_key(au_cat.key)] = True
    module.st.session_state[module._ss_pack_key(et_cat.key)] = True
    module.st.session_state[module._ss_editor_version_key(au_cat.key)] = 0
    module.st.session_state[module._ss_editor_version_key(et_cat.key)] = 0


def _capture_save_pairs(module, state):
    """Call _save_current_configuration and return the pairs dict it would write."""
    captured: dict[str, str] = {}
    original = module.save_config_batch

    def spy(session, pairs):
        captured.update(pairs)

    module.save_config_batch = spy
    try:
        module._save_current_configuration(MagicMock(), state)
    finally:
        module.save_config_batch = original
    return captured


class TestSaveCurrentConfiguration:
    """Task 5.1 — verify _save_current_configuration produces correct config pairs."""

    def test_save_produces_correct_keys_for_mixed_sources(self, telemetry_page):
        grouped = _mixed_grouped()
        _setup_for_save(telemetry_page, grouped, au_polls=[True, False], et_polls=[True])

        telemetry_page.st.session_state[
            telemetry_page._ss_df_key(_account_usage_category().key)
        ].at[0, "interval_seconds"] = 1800

        state = telemetry_page._capture_current_state(grouped)
        captured_pairs = _capture_save_pairs(telemetry_page, state)

        assert captured_pairs["pack_enabled.distributed_tracing"] == "true"
        assert captured_pairs["pack_enabled.query_performance"] == "true"

        qh_slug = source_slug("SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY")
        assert captured_pairs[f"source.{qh_slug}.view_fqn"] == "SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY"
        assert captured_pairs[f"source.{qh_slug}.poll"] == "true"
        assert captured_pairs[f"source.{qh_slug}.poll_interval_seconds"] == "1800"
        assert f"source.{qh_slug}.overlap_minutes" in captured_pairs

        lw_slug = source_slug("SNOWFLAKE.ACCOUNT_USAGE.LOCK_WAIT_HISTORY")
        assert captured_pairs[f"source.{lw_slug}.poll"] == "false"
        assert f"source.{lw_slug}.overlap_minutes" in captured_pairs

        et_slug = source_slug("SNOWFLAKE.TELEMETRY.EVENTS")
        assert captured_pairs[f"source.{et_slug}.view_fqn"] == "SNOWFLAKE.TELEMETRY.EVENTS"
        assert captured_pairs[f"source.{et_slug}.poll"] == "true"
        assert captured_pairs[f"source.{et_slug}.poll_interval_seconds"] == "60"
        assert f"source.{et_slug}.overlap_minutes" not in captured_pairs

    def test_save_does_not_write_pack_enabled_dummy(self, telemetry_page):
        grouped = _mixed_grouped()
        _setup_for_save(telemetry_page, grouped)

        state = telemetry_page._capture_current_state(grouped)
        captured_pairs = _capture_save_pairs(telemetry_page, state)

        assert "pack_enabled.dummy" not in captured_pairs


class TestLoadSavedControlsRoundTrip:
    """Task 5.2 — verify save→load round-trip restores exact state."""

    def test_round_trip_restores_saved_values(self, telemetry_page):
        grouped = _mixed_grouped()
        _setup_for_save(
            telemetry_page, grouped,
            au_polls=[True, False], et_polls=[True],
        )
        au_cat = _account_usage_category()
        et_cat = _event_table_category()

        telemetry_page.st.session_state[
            telemetry_page._ss_df_key(au_cat.key)
        ].at[0, "interval_seconds"] = 1800
        telemetry_page.st.session_state[
            telemetry_page._ss_df_key(au_cat.key)
        ].at[0, "overlap_minutes"] = 120

        state_before_save = telemetry_page._capture_current_state(grouped)
        saved_db = _capture_save_pairs(telemetry_page, state_before_save)

        def mock_load_config_like(_session, prefix):
            return {k: v for k, v in saved_db.items() if k.startswith(prefix)}

        original_load = telemetry_page.load_config_like
        telemetry_page.load_config_like = mock_load_config_like
        telemetry_page.st.session_state.pop(telemetry_page._DISCOVERY_SIGNATURE_KEY, None)
        telemetry_page.st.session_state.pop(telemetry_page._SAVED_STATE_KEY, None)
        try:
            telemetry_page._load_saved_controls(MagicMock(), grouped)
        finally:
            telemetry_page.load_config_like = original_load

        state_after_load = telemetry_page._capture_current_state(grouped)
        assert state_after_load == state_before_save

        au_df = telemetry_page.st.session_state[telemetry_page._ss_df_key(au_cat.key)]
        assert au_df["interval_seconds"].iloc[0] == 1800
        assert au_df["overlap_minutes"].iloc[0] == 120
        assert bool(au_df["poll"].iloc[0]) is True
        assert bool(au_df["poll"].iloc[1]) is False

        et_df = telemetry_page.st.session_state[telemetry_page._ss_df_key(et_cat.key)]
        assert bool(et_df["poll"].iloc[0]) is True

        assert telemetry_page.st.session_state[telemetry_page._ss_pack_key(au_cat.key)] is True
        assert telemetry_page.st.session_state[telemetry_page._ss_pack_key(et_cat.key)] is True


class TestCaptureCurrentState:
    """Task 5.3 — verify _capture_current_state reflects editor-modified values."""

    def test_reflects_editor_interval_change(self, telemetry_page):
        grouped = _mixed_grouped()
        _setup_for_save(telemetry_page, grouped, au_polls=[True, False])
        au_cat = _account_usage_category()

        editor_key = telemetry_page._editor_key(au_cat.key)
        telemetry_page.st.session_state[editor_key] = {
            "edited_rows": {"0": {"interval_seconds": 7200}},
        }

        state = telemetry_page._capture_current_state(grouped)
        qh_state = state["sources"]["SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY"]
        assert qh_state["interval_seconds"] == 7200

    def test_et_source_has_no_overlap_key(self, telemetry_page):
        grouped = _mixed_grouped()
        _setup_for_save(telemetry_page, grouped, et_polls=[True])

        state = telemetry_page._capture_current_state(grouped)
        et_state = state["sources"]["SNOWFLAKE.TELEMETRY.EVENTS"]
        assert "overlap_minutes" not in et_state

    def test_au_source_has_overlap_key(self, telemetry_page):
        grouped = _mixed_grouped()
        _setup_for_save(telemetry_page, grouped, au_polls=[True, False])

        state = telemetry_page._capture_current_state(grouped)
        qh_state = state["sources"]["SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY"]
        assert "overlap_minutes" in qh_state


class TestUnsavedChangesDetection:
    """Task 5.4 — verify no false positives after load and correct diffs on edit."""

    def test_no_false_positive_after_load(self, telemetry_page):
        grouped = _mixed_grouped()
        _setup_for_save(telemetry_page, grouped)

        saved_state = telemetry_page._capture_current_state(grouped)
        telemetry_page.st.session_state[telemetry_page._SAVED_STATE_KEY] = saved_state

        current_state = telemetry_page._capture_current_state(grouped)
        assert current_state == saved_state

    def test_detects_poll_change(self, telemetry_page):
        grouped = _mixed_grouped()
        _setup_for_save(telemetry_page, grouped, au_polls=[False, False])

        saved_state = telemetry_page._capture_current_state(grouped)
        telemetry_page.st.session_state[telemetry_page._SAVED_STATE_KEY] = saved_state

        editor_key = telemetry_page._editor_key(_account_usage_category().key)
        telemetry_page.st.session_state[editor_key] = {
            "edited_rows": {"0": {"poll": True}},
        }

        current_state = telemetry_page._capture_current_state(grouped)
        assert current_state != saved_state

    def test_detects_pack_toggle_change(self, telemetry_page):
        grouped = _mixed_grouped()
        _setup_for_save(telemetry_page, grouped)

        saved_state = telemetry_page._capture_current_state(grouped)
        telemetry_page.st.session_state[telemetry_page._SAVED_STATE_KEY] = saved_state

        au_cat = _account_usage_category()
        telemetry_page.st.session_state[telemetry_page._ss_pack_key(au_cat.key)] = False

        current_state = telemetry_page._capture_current_state(grouped)
        assert current_state != saved_state

    def test_detects_interval_change(self, telemetry_page):
        grouped = _mixed_grouped()
        _setup_for_save(telemetry_page, grouped, au_polls=[True, False])

        saved_state = telemetry_page._capture_current_state(grouped)
        telemetry_page.st.session_state[telemetry_page._SAVED_STATE_KEY] = saved_state

        editor_key = telemetry_page._editor_key(_account_usage_category().key)
        telemetry_page.st.session_state[editor_key] = {
            "edited_rows": {"0": {"interval_seconds": 9999}},
        }

        current_state = telemetry_page._capture_current_state(grouped)
        assert current_state != saved_state

    def test_detects_overlap_change(self, telemetry_page):
        grouped = _mixed_grouped()
        _setup_for_save(telemetry_page, grouped, au_polls=[True, False])

        saved_state = telemetry_page._capture_current_state(grouped)
        telemetry_page.st.session_state[telemetry_page._SAVED_STATE_KEY] = saved_state

        editor_key = telemetry_page._editor_key(_account_usage_category().key)
        telemetry_page.st.session_state[editor_key] = {
            "edited_rows": {"0": {"overlap_minutes": 999}},
        }

        current_state = telemetry_page._capture_current_state(grouped)
        assert current_state != saved_state


class TestResetSaveRoundTrip:
    """Task 5.5 — verify reset-to-defaults → save correctly persists defaults."""

    def test_reset_then_save_persists_defaults(self, telemetry_page):
        grouped = _mixed_grouped()
        _setup_for_save(telemetry_page, grouped, au_polls=[True, False], et_polls=[True])
        au_cat = _account_usage_category()

        telemetry_page.st.session_state[
            telemetry_page._ss_df_key(au_cat.key)
        ].at[0, "interval_seconds"] = 9999
        telemetry_page.st.session_state[
            telemetry_page._ss_df_key(au_cat.key)
        ].at[0, "overlap_minutes"] = 999

        telemetry_page._reset_to_defaults(grouped)

        state = telemetry_page._capture_current_state(grouped)
        captured_pairs = _capture_save_pairs(telemetry_page, state)

        qh_slug = source_slug("SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY")
        assert captured_pairs[f"source.{qh_slug}.poll_interval_seconds"] == "900"
        assert captured_pairs[f"source.{qh_slug}.overlap_minutes"] == "50"
        assert captured_pairs[f"source.{qh_slug}.poll"] == "false"
        assert captured_pairs["pack_enabled.query_performance"] == "false"
        assert captured_pairs["pack_enabled.distributed_tracing"] == "false"


class TestSaveErrorHandling:
    """Task 5.6 — verify SnowparkSQLException during save preserves unsaved state."""

    def test_save_error_preserves_unsaved_state(self, telemetry_page):
        grouped = _mixed_grouped()
        _setup_for_save(telemetry_page, grouped, au_polls=[True, False])

        telemetry_page.st.session_state[telemetry_page._JUST_SAVED_KEY] = False
        telemetry_page.st.session_state[telemetry_page._SAVED_STATE_KEY] = {
            "packs": {}, "sources": {},
        }

        state = telemetry_page._capture_current_state(grouped)

        def exploding_batch(session, pairs):
            raise SnowparkSQLException("simulated write failure")

        original = telemetry_page.save_config_batch
        telemetry_page.save_config_batch = exploding_batch
        try:
            with pytest.raises(SnowparkSQLException, match="simulated write failure"):
                telemetry_page._save_current_configuration(MagicMock(), state)
        finally:
            telemetry_page.save_config_batch = original

        assert telemetry_page.st.session_state[telemetry_page._JUST_SAVED_KEY] is False


class TestEventTableOverlapExclusion:
    """Task 5.1/AC7 — overlap_minutes is absent for ET sources in save output."""

    def test_et_source_overlap_not_in_saved_pairs(self, telemetry_page):
        grouped = _mixed_grouped()
        _setup_for_save(telemetry_page, grouped, et_polls=[True])

        state = telemetry_page._capture_current_state(grouped)
        captured_pairs = _capture_save_pairs(telemetry_page, state)

        et_slug = source_slug("SNOWFLAKE.TELEMETRY.EVENTS")
        overlap_keys = [k for k in captured_pairs if k.endswith(".overlap_minutes")]
        et_overlap_keys = [k for k in overlap_keys if et_slug in k]
        assert et_overlap_keys == []

    def test_load_tolerates_missing_overlap_for_et(self, telemetry_page):
        et_cat = _event_table_category()
        et_fqn = "SNOWFLAKE.TELEMETRY.EVENTS"
        et_slug = source_slug(et_fqn)
        grouped = {
            _account_usage_category().key: [],
            et_cat.key: [_make_source(et_fqn, et_cat.key)],
        }
        saved_db = {
            f"pack_enabled.{et_cat.key}": "true",
            f"source.{et_slug}.view_fqn": et_fqn,
            f"source.{et_slug}.poll": "true",
            f"source.{et_slug}.poll_interval_seconds": "120",
        }

        def mock_load_config_like(_session, prefix):
            return {k: v for k, v in saved_db.items() if k.startswith(prefix)}

        original_load = telemetry_page.load_config_like
        telemetry_page.load_config_like = mock_load_config_like

        for cat in CATEGORIES:
            telemetry_page.st.session_state[telemetry_page._ss_editor_version_key(cat.key)] = 0
        telemetry_page.st.session_state.pop(telemetry_page._DISCOVERY_SIGNATURE_KEY, None)
        telemetry_page.st.session_state.pop(telemetry_page._SAVED_STATE_KEY, None)
        try:
            telemetry_page._load_saved_controls(MagicMock(), grouped)
        finally:
            telemetry_page.load_config_like = original_load

        et_df = telemetry_page.st.session_state[telemetry_page._ss_df_key(et_cat.key)]
        assert bool(et_df["poll"].iloc[0]) is True
        assert et_df["interval_seconds"].iloc[0] == 120
        assert et_df["overlap_minutes"].iloc[0] is None
