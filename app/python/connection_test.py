"""gRPC TLS channel readiness probe for OTLP connectivity (stored procedure handler)."""

from __future__ import annotations

import json
import socket

import grpc
from endpoint_parse import host_port_string, parse_endpoint
from snowflake.snowpark import Session

TIMEOUT_SECONDS = 10.0

_APPROVAL_HINTS = (
    "approve",
    "approval",
    "specification",
    "external access",
    "not approved",
    "pending approval",
    "app specification",
)


def _classify_exception(exc: BaseException) -> tuple[str, str]:
    """Return (short_message, details) for UI."""
    msg = str(exc).strip()
    low = msg.lower()

    if isinstance(exc, (grpc.FutureTimeoutError, TimeoutError)):
        return (
            "Connection timed out — check that the endpoint is reachable and firewall rules allow egress",
            msg,
        )

    if isinstance(exc, socket.gaierror):
        return (
            "DNS resolution failed — verify the hostname",
            msg,
        )

    if "refused" in low or "connection refused" in low:
        return (
            "Connection refused — nothing is listening on the port or the path is blocked",
            msg,
        )

    if "certificate" in low or "ssl" in low or "tls" in low or "handshake" in low:
        return (
            "TLS handshake failed — certificate verification error or incompatible TLS",
            msg,
        )

    if any(h in low for h in _APPROVAL_HINTS):
        return (
            "External access may require approval — approve the OTLP gRPC Export specification and retry",
            msg,
        )

    return (
        "Connection test failed — see details",
        msg,
    )


def test_connection(_session: Session, endpoint: str, cert_pem: str = "") -> str:
    """Open a gRPC TLS channel and wait until READY or timeout."""

    try:
        host, port = parse_endpoint(endpoint)
    except ValueError as e:
        return json.dumps(
            {
                "success": False,
                "message": "Invalid endpoint format",
                "details": str(e),
            },
        )

    target = host_port_string(host, port)
    root_ca = cert_pem.strip().encode("utf-8") if cert_pem and cert_pem.strip() else None
    credentials = grpc.ssl_channel_credentials(root_certificates=root_ca)
    channel = grpc.secure_channel(target, credentials)
    try:
        fut = grpc.channel_ready_future(channel)
        fut.result(timeout=TIMEOUT_SECONDS)
        return json.dumps(
            {
                "success": True,
                "message": "Connection successful",
                "details": target,
            },
        )
    except grpc.FutureTimeoutError as e:
        short_msg, details = _classify_exception(e)
        return json.dumps(
            {
                "success": False,
                "message": short_msg,
                "details": details,
                "approval_related": False,
            },
        )
    except Exception as e:
        short_msg, details = _classify_exception(e)
        low = details.lower()
        approval = any(h in low for h in _APPROVAL_HINTS)
        return json.dumps(
            {
                "success": False,
                "message": short_msg,
                "details": details,
                "approval_related": approval,
            },
        )
    finally:
        channel.close()
