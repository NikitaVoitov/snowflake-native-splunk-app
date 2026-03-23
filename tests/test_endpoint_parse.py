"""Unit tests for OTLP endpoint parsing (Story 2.1)."""

from __future__ import annotations

import pytest
from endpoint_parse import host_port_string, parse_endpoint


def test_parse_host_port() -> None:
    h, p = parse_endpoint("collector.example.com:4317")
    assert h == "collector.example.com"
    assert p == 4317
    assert host_port_string(h, p) == "collector.example.com:4317"


def test_parse_https_and_default_port() -> None:
    h, p = parse_endpoint("https://otel.example.com")
    assert h == "otel.example.com"
    assert p == 4317


def test_parse_rejects_http() -> None:
    with pytest.raises(ValueError, match="HTTP"):
        parse_endpoint("http://otel.example.com:4317")


def test_parse_rejects_path() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        parse_endpoint("https://host/v1/traces")


def test_parse_rejects_bad_port() -> None:
    with pytest.raises(ValueError, match="range"):
        parse_endpoint("host:99999")
