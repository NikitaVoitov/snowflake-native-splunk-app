"""Unit tests for the real helpers in ``pages/telemetry_sources.py``."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app" / "streamlit"))

from utils.source_discovery import CATEGORIES, DiscoveredSource


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
