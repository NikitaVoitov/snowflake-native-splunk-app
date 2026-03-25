"""Unit tests for connection_test helpers."""

from __future__ import annotations

import connection_test
import dns.exception
import dns.resolver


def test_resolve_dns_returns_error_for_nxdomain(monkeypatch) -> None:
    class FakeResolver:
        timeout = 0.0
        lifetime = 0.0

        def resolve(self, *_args, **_kwargs):
            raise dns.resolver.NXDOMAIN()

    monkeypatch.setattr(connection_test.dns.resolver, "Resolver", lambda configure=True: FakeResolver())

    status, details = connection_test._resolve_dns("missing.example.com", 4317)

    assert status == "not_found"
    assert details is not None
    assert "NXDOMAIN" in details


def test_resolve_dns_ignores_inconclusive_errors(monkeypatch) -> None:
    class FakeResolver:
        timeout = 0.0
        lifetime = 0.0

        def resolve(self, *_args, **_kwargs):
            raise dns.exception.Timeout()

    monkeypatch.setattr(connection_test.dns.resolver, "Resolver", lambda configure=True: FakeResolver())

    status, details = connection_test._resolve_dns("otelcol.israelcentral.cloudapp.azure.com", 4317)

    assert status == "unavailable"
    assert details is not None
    assert "could not be completed" in details


def test_resolve_dns_no_answer_for_a_and_aaaa(monkeypatch) -> None:
    class FakeResolver:
        timeout = 0.0
        lifetime = 0.0

        def resolve(self, *_args, **_kwargs):
            raise dns.resolver.NoAnswer()

    monkeypatch.setattr(connection_test.dns.resolver, "Resolver", lambda configure=True: FakeResolver())

    status, details = connection_test._resolve_dns("no-records.example.com", 4317)

    assert status == "not_found"
    assert details is not None
    assert "no A or AAAA records found" in details
