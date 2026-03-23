"""Shared OTLP endpoint parsing for provisioning and connection test stored procedures."""

from __future__ import annotations

import re
from typing import Final

_DEFAULT_GRPC_PORT: Final[int] = 4317

# Host labels: letters, digits, hyphen; dots between labels. Allows single-label (e.g. localhost).
_HOST_RE = re.compile(
    r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$",
)


def parse_endpoint(endpoint: str) -> tuple[str, int]:
    """Parse and validate OTLP endpoint; return (host, port). TLS gRPC; default port 4317."""
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
            raise ValueError("Port out of range")

    host = host_part.strip()
    if not host:
        raise ValueError("Host is empty")
    if len(host) > 253:
        raise ValueError("Hostname is too long")
    if not _HOST_RE.match(host):
        raise ValueError("Invalid hostname format")

    return host, port


def host_port_string(host: str, port: int) -> str:
    """Format host:port for network rules and gRPC target."""
    return f"{host}:{port}"
