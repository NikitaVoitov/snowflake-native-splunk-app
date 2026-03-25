"""Unit tests for accumulated app-spec HOST_PORTS behavior."""

from __future__ import annotations

import json

import provision_egress


class _FakeResult:
    def collect(self) -> list[object]:
        return []


class _FakeSession:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def sql(self, statement: str) -> _FakeResult:
        self.statements.append(statement)
        return _FakeResult()


def _parse(raw: str) -> dict[str, object]:
    return json.loads(raw)


def test_provision_egress_accumulates_new_host_and_keeps_rule_single_entry(monkeypatch) -> None:
    session = _FakeSession()

    monkeypatch.setattr(provision_egress, "parse_endpoint", lambda endpoint: ("new.example.com", 4317))
    monkeypatch.setattr(
        provision_egress,
        "_get_desc_value_list",
        lambda _session: "VALUE_LIST = ('old.example.com:4317')",
    )

    spec_states = iter(
        [
            ("APPROVED", {"old.example.com:4317"}),
            ("PENDING", {"old.example.com:4317", "new.example.com:4317"}),
        ],
    )
    monkeypatch.setattr(provision_egress, "_get_latest_spec", lambda _session: next(spec_states))

    result = _parse(provision_egress.provision_egress(session, "new.example.com:4317"))

    assert result["provisioned"] is True
    assert result["specification_changed"] is True
    assert result["needs_approval"] is True

    network_rule_sql = next(stmt for stmt in session.statements if "ALTER NETWORK RULE" in stmt)
    assert "VALUE_LIST = ('new.example.com:4317')" in network_rule_sql
    assert "old.example.com:4317" not in network_rule_sql

    spec_sql = next(stmt for stmt in session.statements if "ALTER APPLICATION SET SPECIFICATION" in stmt)
    assert "'old.example.com:4317'" in spec_sql
    assert "'new.example.com:4317'" in spec_sql


def test_provision_egress_switch_back_to_approved_host_skips_spec_update(monkeypatch) -> None:
    session = _FakeSession()

    monkeypatch.setattr(provision_egress, "parse_endpoint", lambda endpoint: ("old.example.com", 4317))
    monkeypatch.setattr(
        provision_egress,
        "_get_desc_value_list",
        lambda _session: "VALUE_LIST = ('new.example.com:4317')",
    )
    monkeypatch.setattr(
        provision_egress,
        "_get_latest_spec",
        lambda _session: ("APPROVED", {"old.example.com:4317", "new.example.com:4317"}),
    )

    result = _parse(provision_egress.provision_egress(session, "old.example.com:4317"))

    assert result["provisioned"] is True
    assert result["specification_changed"] is False
    assert result["needs_approval"] is False

    network_rule_sql = next(stmt for stmt in session.statements if "ALTER NETWORK RULE" in stmt)
    assert "VALUE_LIST = ('old.example.com:4317')" in network_rule_sql

    assert not any("ALTER APPLICATION SET SPECIFICATION" in stmt for stmt in session.statements)


def test_provision_egress_noop_when_rule_already_matches_and_host_is_approved(monkeypatch) -> None:
    session = _FakeSession()

    monkeypatch.setattr(provision_egress, "parse_endpoint", lambda endpoint: ("old.example.com", 4317))
    monkeypatch.setattr(
        provision_egress,
        "_get_desc_value_list",
        lambda _session: "VALUE_LIST = ('old.example.com:4317')",
    )
    monkeypatch.setattr(
        provision_egress,
        "_get_latest_spec",
        lambda _session: ("APPROVED", {"old.example.com:4317", "new.example.com:4317"}),
    )

    result = _parse(provision_egress.provision_egress(session, "old.example.com:4317"))

    assert result["provisioned"] is True
    assert result["specification_changed"] is False
    assert result["needs_approval"] is False
    assert session.statements == []
