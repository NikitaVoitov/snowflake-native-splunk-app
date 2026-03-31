"""Unit tests for utils/config.py — config CRUD helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# Make the streamlit utils importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app" / "streamlit"))

from utils.config import (
    _MERGE_SQL,
    _SELECT_ONE_SQL,
    load_all_config,
    load_config,
    load_config_like,
    save_config,
    save_config_batch,
)


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.sql.return_value.collect.return_value = []
    return session


class TestSaveConfig:
    def test_calls_merge_with_params(self, mock_session):
        save_config(mock_session, "otlp.endpoint", "collector.example.com:4317")
        mock_session.sql.assert_called_once_with(
            _MERGE_SQL,
            params=["otlp.endpoint", "collector.example.com:4317"],
        )
        mock_session.sql.return_value.collect.assert_called_once()

    def test_empty_value(self, mock_session):
        save_config(mock_session, "some.key", "")
        mock_session.sql.assert_called_once_with(
            _MERGE_SQL, params=["some.key", ""]
        )


class TestSaveConfigBatch:
    def test_empty_dict_is_noop(self, mock_session):
        save_config_batch(mock_session, {})
        mock_session.sql.assert_not_called()

    def test_single_pair(self, mock_session):
        save_config_batch(mock_session, {"key1": "val1"})
        call_args = mock_session.sql.call_args
        sql = call_args[0][0]
        params = call_args[1]["params"]
        assert "MERGE INTO _internal.config" in sql
        assert "(?, ?)" in sql
        assert params == ["key1", "val1"]

    def test_multiple_pairs_single_sql_call(self, mock_session):
        pairs = {"a": "1", "b": "2", "c": "3"}
        save_config_batch(mock_session, pairs)
        mock_session.sql.assert_called_once()
        call_args = mock_session.sql.call_args
        sql = call_args[0][0]
        params = call_args[1]["params"]
        assert sql.count("(?, ?)") == 3
        assert len(params) == 6
        for key in pairs:
            assert key in params

    def test_params_preserve_key_value_pairing(self, mock_session):
        pairs = {"pack_enabled.dt": "true", "pack_enabled.qp": "false"}
        save_config_batch(mock_session, pairs)
        params = mock_session.sql.call_args[1]["params"]
        for i in range(0, len(params), 2):
            key, val = params[i], params[i + 1]
            assert pairs[key] == val


class TestLoadConfig:
    def test_returns_value_when_present(self, mock_session):
        mock_session.sql.return_value.collect.return_value = [
            ("collector.example.com:4317",)
        ]
        result = load_config(mock_session, "otlp.endpoint")
        assert result == "collector.example.com:4317"
        mock_session.sql.assert_called_once_with(
            _SELECT_ONE_SQL, params=["otlp.endpoint"]
        )

    def test_returns_none_when_missing(self, mock_session):
        mock_session.sql.return_value.collect.return_value = []
        assert load_config(mock_session, "nonexistent") is None

    def test_returns_none_for_null_value(self, mock_session):
        mock_session.sql.return_value.collect.return_value = [(None,)]
        assert load_config(mock_session, "null.key") is None

    def test_strips_whitespace(self, mock_session):
        mock_session.sql.return_value.collect.return_value = [
            ("  some-value  ",)
        ]
        assert load_config(mock_session, "k") == "some-value"


class TestLoadAllConfig:
    def test_returns_dict(self, mock_session):
        mock_session.sql.return_value.collect.return_value = [
            ("otlp.endpoint", "host:4317"),
            ("otlp.pem_secret_ref", "bound"),
        ]
        result = load_all_config(mock_session)
        assert result == {
            "otlp.endpoint": "host:4317",
            "otlp.pem_secret_ref": "bound",
        }

    def test_empty_table(self, mock_session):
        assert load_all_config(mock_session) == {}

    def test_skips_null_keys(self, mock_session):
        mock_session.sql.return_value.collect.return_value = [
            (None, "value"),
            ("good.key", "good.value"),
        ]
        assert load_all_config(mock_session) == {"good.key": "good.value"}

    def test_skips_null_values(self, mock_session):
        mock_session.sql.return_value.collect.return_value = [
            ("null.value", None),
            ("good.key", "good.value"),
        ]
        assert load_all_config(mock_session) == {"good.key": "good.value"}

    def test_strips_loaded_values(self, mock_session):
        mock_session.sql.return_value.collect.return_value = [
            ("good.key", "  good.value  "),
        ]
        assert load_all_config(mock_session) == {"good.key": "good.value"}


class TestLoadConfigLike:
    def test_prefix_match(self, mock_session):
        mock_session.sql.return_value.collect.return_value = [
            ("pack_enabled.distributed_tracing", "true"),
            ("pack_enabled.cost", "false"),
        ]
        result = load_config_like(mock_session, "pack_enabled.")
        assert result == {
            "pack_enabled.distributed_tracing": "true",
            "pack_enabled.cost": "false",
        }
        mock_session.sql.assert_called_once()
        args = mock_session.sql.call_args
        assert "LIKE ?" in args[0][0]
        assert args[1]["params"] == ["pack_enabled.%"]
