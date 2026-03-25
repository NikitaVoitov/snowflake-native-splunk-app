"""Shared OTLP endpoint parsing for provisioning and connection test stored procedures."""

from __future__ import annotations

import ipaddress
from typing import Final

import validators

_DEFAULT_GRPC_PORT: Final[int] = 4317


def _is_ipv4(host: str) -> bool:
    """Return True when *host* is a valid dotted-decimal IPv4 address."""
    try:
        ipaddress.IPv4Address(host)
        return True
    except ValueError:
        return False


def parse_endpoint(endpoint: str) -> tuple[str, int]:
    """Parse and validate an OTLP endpoint; return (host, port).

    Accepts ``host:port``, ``host``, or ``https://host[:port]``.
    The host must be a fully-qualified domain name (RFC 1034/1123) or a
    valid IPv4 address.  Default port is 4317 (gRPC OTLP).
    """
    if endpoint is None:
        raise ValueError("Endpoint is empty")
    s = endpoint.strip()
    if not s:
        raise ValueError("Endpoint is empty")

    lowered = s.lower()
    if lowered.startswith("http://"):
        raise ValueError(
            "Plain HTTP is not supported; use gRPC with TLS (e.g. host:4317 or https://host:4317)",
        )
    if lowered.startswith("https://"):
        s = s[8:]

    if " " in s or "\t" in s or "\n" in s:
        raise ValueError("Whitespace is not allowed inside the endpoint")
    if ";" in s or "'" in s or '"' in s or "\\" in s:
        raise ValueError("Invalid characters in endpoint")
    if "/" in s or "?" in s or "#" in s:
        raise ValueError("Path, query, and fragments are not allowed")

    port = _DEFAULT_GRPC_PORT
    host_part = s
    if ":" in s:
        host_part, port_str = s.rsplit(":", 1)
        if not port_str.isdigit():
            raise ValueError("Port must be numeric")
        port = int(port_str)
        if port < 1 or port > 65535:
            raise ValueError(f"Port {port} is out of the valid range (1-65535)")

    host = host_part.strip()
    if not host:
        raise ValueError("Host is empty")

    if _is_ipv4(host):
        raise ValueError(
            "IP addresses are not supported for Snowflake external access. "
            "Use a fully-qualified hostname instead (e.g. collector.example.com).",
        )

    if not validators.domain(host):
        raise ValueError(
            f"'{host}' is not a valid fully-qualified domain name. "
            "Use a complete hostname like collector.example.com.",
        )

    return host, port


def host_port_string(host: str, port: int) -> str:
    """Format host:port for network rules and gRPC target."""
    return f"{host}:{port}"
