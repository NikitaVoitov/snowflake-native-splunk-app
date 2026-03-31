"""Unit tests for utils/onboarding.py — onboarding completion logic."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from snowflake.snowpark.exceptions import SnowparkSQLException


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app" / "streamlit"))

from utils.onboarding import (
    ONBOARDING_TASKS,
    get_completed_count,
    load_task_completion,
    load_task_completion_state,
)


def _mock_load_config(session, key):
    """Simulate config lookups for known keys."""
    store = getattr(session, "_test_store", {})
    return store.get(key)


def _mock_load_config_like(session, prefix):
    store = getattr(session, "_test_store", {})
    return {k: v for k, v in store.items() if k.startswith(prefix)}


class TestLoadTaskCompletion:
    @patch("utils.onboarding.load_config", side_effect=_mock_load_config)
    @patch("utils.onboarding.load_config_like", side_effect=_mock_load_config_like)
    def test_all_incomplete(self, mock_like, mock_cfg):
        session = MagicMock()
        session._test_store = {}
        result = load_task_completion(session)
        assert all(v is False for v in result.values())
        assert len(result) == 4

    @patch("utils.onboarding.load_config", side_effect=_mock_load_config)
    @patch("utils.onboarding.load_config_like", side_effect=_mock_load_config_like)
    def test_task1_complete(self, mock_like, mock_cfg):
        session = MagicMock()
        session._test_store = {"otlp.endpoint": "host:4317"}
        result = load_task_completion(session)
        assert result[1] is True
        assert result[2] is False
        assert result[3] is False
        assert result[4] is False

    @patch("utils.onboarding.load_config", side_effect=_mock_load_config)
    @patch("utils.onboarding.load_config_like", side_effect=_mock_load_config_like)
    def test_task2_requires_at_least_one_pack(self, mock_like, mock_cfg):
        session = MagicMock()
        session._test_store = {
            "pack_enabled.distributed_tracing": "true",
            "pack_enabled.cost": "false",
        }
        result = load_task_completion(session)
        assert result[2] is True

    @patch("utils.onboarding.load_config", side_effect=_mock_load_config)
    @patch("utils.onboarding.load_config_like", side_effect=_mock_load_config_like)
    def test_task2_incomplete_when_no_packs_true(self, mock_like, mock_cfg):
        session = MagicMock()
        session._test_store = {
            "pack_enabled.cost": "false",
        }
        result = load_task_completion(session)
        assert result[2] is False

    @patch("utils.onboarding.load_config", side_effect=_mock_load_config)
    @patch("utils.onboarding.load_config_like", side_effect=_mock_load_config_like)
    def test_task2_is_case_insensitive(self, mock_like, mock_cfg):
        session = MagicMock()
        session._test_store = {
            "pack_enabled.distributed_tracing": "TRUE",
        }
        result = load_task_completion(session)
        assert result[2] is True

    @patch("utils.onboarding.load_config", side_effect=_mock_load_config)
    @patch("utils.onboarding.load_config_like", side_effect=_mock_load_config_like)
    def test_task2_ignores_legacy_dummy_pack_key(self, mock_like, mock_cfg):
        session = MagicMock()
        session._test_store = {
            "pack_enabled.dummy": "true",
            "pack_enabled.distributed_tracing": "false",
        }
        result = load_task_completion(session)
        assert result[2] is False

    @patch("utils.onboarding.load_config", side_effect=_mock_load_config)
    @patch("utils.onboarding.load_config_like", side_effect=_mock_load_config_like)
    def test_task2_ignores_unrelated_pack_enabled_keys(self, mock_like, mock_cfg):
        session = MagicMock()
        session._test_store = {
            "pack_enabled.tracing": "true",
            "pack_enabled.query_performance_legacy": "true",
        }
        result = load_task_completion(session)
        assert result[2] is False

    @patch("utils.onboarding.load_config", side_effect=_mock_load_config)
    @patch("utils.onboarding.load_config_like", side_effect=_mock_load_config_like)
    def test_all_complete(self, mock_like, mock_cfg):
        session = MagicMock()
        session._test_store = {
            "otlp.endpoint": "collector:4317",
            "pack_enabled.query_performance": "true",
            "governance.acknowledged": "true",
            "activation.completed": "true",
        }
        result = load_task_completion(session)
        assert all(v is True for v in result.values())

    @patch("utils.onboarding.load_config", side_effect=_mock_load_config)
    @patch("utils.onboarding.load_config_like", side_effect=_mock_load_config_like)
    def test_tasks_3_and_4_are_case_insensitive(self, mock_like, mock_cfg):
        session = MagicMock()
        session._test_store = {
            "governance.acknowledged": "TRUE",
            "activation.completed": "True",
        }
        result = load_task_completion(session)
        assert result[3] is True
        assert result[4] is True

    def test_none_session_returns_all_false(self):
        result = load_task_completion(None)
        assert all(v is False for v in result.values())
        assert len(result) == 4

    @patch(
        "utils.onboarding.load_config",
        side_effect=SnowparkSQLException("config table unavailable"),
    )
    @patch("utils.onboarding.load_config_like", side_effect=_mock_load_config_like)
    def test_sql_errors_return_default_completion_and_error(self, mock_like, mock_cfg):
        session = MagicMock()
        state = load_task_completion_state(session)
        assert all(v is False for v in state.completion.values())
        assert state.error_message is not None
        assert "Could not load onboarding progress from Snowflake" in state.error_message
        assert "config table unavailable" in state.error_message

    def test_none_session_returns_no_error(self):
        state = load_task_completion_state(None)
        assert all(v is False for v in state.completion.values())
        assert state.error_message is None


class TestGetCompletedCount:
    def test_zero(self):
        assert get_completed_count({1: False, 2: False, 3: False, 4: False}) == 0

    def test_partial(self):
        assert get_completed_count({1: True, 2: False, 3: True, 4: False}) == 2

    def test_all(self):
        assert get_completed_count({1: True, 2: True, 3: True, 4: True}) == 4


class TestOnboardingTaskDefinitions:
    def test_four_tasks_defined(self):
        assert len(ONBOARDING_TASKS) == 4

    def test_steps_are_sequential(self):
        steps = [t.step for t in ONBOARDING_TASKS]
        assert steps == [1, 2, 3, 4]

    def test_task4_has_no_page_path(self):
        task4 = ONBOARDING_TASKS[3]
        assert task4.page_path is None

    def test_all_tasks_have_config_key(self):
        for task in ONBOARDING_TASKS:
            assert task.config_key
