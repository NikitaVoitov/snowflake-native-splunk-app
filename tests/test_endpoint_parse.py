"""Unit tests for OTLP endpoint parsing (Story 2.1 + validators-based validation)."""

from __future__ import annotations

import pytest
from endpoint_parse import host_port_string, parse_endpoint


# ── Valid endpoints ───────────────────────────────────────────────

def test_parse_host_port() -> None:
    h, p = parse_endpoint("collector.example.com:4317")
    assert h == "collector.example.com"
    assert p == 4317
    assert host_port_string(h, p) == "collector.example.com:4317"


def test_parse_https_and_default_port() -> None:
    h, p = parse_endpoint("https://otel.example.com")
    assert h == "otel.example.com"
    assert p == 4317


def test_parse_custom_port() -> None:
    h, p = parse_endpoint("collector.example.com:443")
    assert h == "collector.example.com"
    assert p == 443


# ── Rejected: IP addresses (Snowflake HOST_PORT limitation) ───────

def test_rejects_ipv4() -> None:
    with pytest.raises(ValueError, match="IP addresses are not supported"):
        parse_endpoint("10.0.1.50:4317")


def test_rejects_ipv4_default_port() -> None:
    with pytest.raises(ValueError, match="IP addresses are not supported"):
        parse_endpoint("192.168.1.1")


def test_rejects_ipv4_loopback() -> None:
    with pytest.raises(ValueError, match="IP addresses are not supported"):
        parse_endpoint("127.0.0.1:4317")


# ── Rejected: protocol / structure ────────────────────────────────

def test_parse_rejects_http() -> None:
    with pytest.raises(ValueError, match="HTTP"):
        parse_endpoint("http://otel.example.com:4317")


def test_parse_rejects_path() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        parse_endpoint("https://host.example.com/v1/traces")


# ── Rejected: port ────────────────────────────────────────────────

def test_parse_rejects_bad_port() -> None:
    with pytest.raises(ValueError, match="range"):
        parse_endpoint("host.example.com:99999")


def test_parse_rejects_zero_port() -> None:
    with pytest.raises(ValueError, match="range"):
        parse_endpoint("host.example.com:0")


def test_parse_rejects_non_numeric_port() -> None:
    with pytest.raises(ValueError, match="numeric"):
        parse_endpoint("host.example.com:abc")


# ── Rejected: single-label hostnames (no dots) ───────────────────

def test_rejects_single_label_hostname() -> None:
    with pytest.raises(ValueError, match="not a valid"):
        parse_endpoint("localhost:4317")


def test_rejects_garbage_single_label() -> None:
    with pytest.raises(ValueError, match="not a valid"):
        parse_endpoint("lgktrlgktrlgktrlgktrlgktr121212")


def test_rejects_single_word() -> None:
    with pytest.raises(ValueError, match="not a valid"):
        parse_endpoint("collector")


# ── Rejected: invalid hostnames ───────────────────────────────────

def test_rejects_whitespace_in_host() -> None:
    with pytest.raises(ValueError, match="Whitespace"):
        parse_endpoint("host name.example.com:4317")


def test_rejects_special_chars() -> None:
    with pytest.raises(ValueError, match="Invalid characters"):
        parse_endpoint("host;drop.example.com")


def test_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        parse_endpoint("")


def test_rejects_none() -> None:
    with pytest.raises(ValueError, match="empty"):
        parse_endpoint(None)  # type: ignore[arg-type]


# ── Rejected: invalid IPv4 ───────────────────────────────────────

def test_rejects_ipv4_out_of_range() -> None:
    with pytest.raises(ValueError, match="not a valid"):
        parse_endpoint("999.999.999.999:4317")


def test_rejects_partial_ipv4() -> None:
    with pytest.raises(ValueError, match="not a valid"):
        parse_endpoint("192:4317")
