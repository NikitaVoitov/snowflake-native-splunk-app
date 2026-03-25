"""gRPC TLS channel readiness probe for OTLP connectivity (stored procedure handler)."""

from __future__ import annotations

import json
import socket

import dns.exception
import dns.resolver
import grpc
from endpoint_parse import host_port_string, parse_endpoint
from snowflake.snowpark import Session

TIMEOUT_SECONDS = 10.0
_PROBE_TIMEOUT_SECONDS = 2.0

_APPROVAL_HINTS = (
    "approve",
    "approval",
    "specification",
    "external access",
    "not approved",
    "pending approval",
    "app specification",
)

_TLS_KEYWORDS = ("ssl", "tls", "certificate", "handshake", "verify", "x509", "alert")


def _is_tls_error(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in _TLS_KEYWORDS)


def _classify_exception(exc: BaseException, *, using_custom_cert: bool = False) -> tuple[str, str]:
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

    if _is_tls_error(msg):
        if using_custom_cert:
            hint = (
                "TLS handshake failed — the provided certificate may not match "
                "the server's CA chain. Verify the PEM content."
            )
        else:
            hint = (
                "TLS handshake failed — the server's certificate is not trusted "
                "by the system trust store. If the collector uses a private or "
                "self-signed certificate, paste its CA certificate in the "
                "Certificate field and retry."
            )
        return hint, msg

    if any(h in low for h in _APPROVAL_HINTS):
        return (
            "External access may require approval — approve the OTLP gRPC Export specification and retry",
            msg,
        )

    return (
        "Connection test failed — see details",
        msg,
    )


def _probe_channel_error(channel: grpc.Channel) -> str | None:
    """Make a trivial unary RPC to surface the real failure reason.

    After ``channel_ready_future`` times out, the channel is typically in
    TRANSIENT_FAILURE due to a TLS handshake error.  A quick unary call
    fails immediately with the actual gRPC status (including TLS details)
    instead of a generic timeout.

    Returns the error details string, or None if the probe itself times out
    (indicating a genuine connectivity timeout, not a TLS issue).
    """
    try:
        stub = channel.unary_unary(
            "/grpc.health.v1.Health/Check",
            request_serializer=lambda x: x,
            response_deserializer=lambda x: x,
        )
        stub(b"", timeout=_PROBE_TIMEOUT_SECONDS)
    except grpc.RpcError as rpc_err:
        return rpc_err.details() or str(rpc_err)
    except Exception:
        return None
    return None


def _resolve_dns(host: str, _port: int) -> tuple[str | None, str | None]:
    """Best-effort authoritative DNS pre-check.

    ``dnspython`` gives us more reliable semantics than ``socket.getaddrinfo``
    inside Snowflake's Python runtime:
    - ``NXDOMAIN`` is authoritative: the hostname does not exist.
    - ``NoAnswer`` for both A and AAAA is authoritative: no address records.
    - timeout / nameserver / OS errors are treated as inconclusive; in that
      case we allow the real gRPC connection attempt to proceed.
    """
    resolver = dns.resolver.Resolver(configure=True)
    resolver.timeout = 2.0
    resolver.lifetime = 4.0

    no_answer = 0
    for rdtype in ("A", "AAAA"):
        try:
            answer = resolver.resolve(host, rdtype)
            if len(answer) > 0:
                return None, None
        except dns.resolver.NXDOMAIN:
            return "not_found", f"DNS lookup failed for '{host}': NXDOMAIN"
        except dns.resolver.NoAnswer:
            no_answer += 1
            continue
        except (dns.resolver.NoNameservers, dns.exception.Timeout, OSError) as e:
            return "unavailable", f"DNS lookup could not be completed for '{host}': {e}"

    if no_answer == 2:
        return "not_found", f"DNS lookup failed for '{host}': no A or AAAA records found"

    return None, None


def _dns_enriched_timeout_msg(host: str, dns_status: str | None, _dns_details: str | None) -> str:
    """Build a user-facing timeout message without over-trusting Python DNS.

    Snowflake's Python runtime has returned false NXDOMAIN results for valid
    external endpoints, so DNS outcomes are treated as advisory only and never
    surfaced as the primary conclusion when the real gRPC connection timed out.
    """
    if dns_status == "unavailable":
        return (
            f"Connection timed out while Snowflake's DNS pre-check was inconclusive for '{host}'. "
            "Verify the hostname is correct and that firewall rules allow egress."
        )
    return (
        "Connection timed out -- check that the endpoint is reachable "
        "and firewall rules allow egress"
    )


def test_connection(_session: Session, endpoint: str, cert_pem: str = "") -> str:
    """Open a gRPC TLS channel and wait until READY or timeout."""

    try:
        host, port = parse_endpoint(endpoint)
    except ValueError as e:
        return json.dumps(
            {
                "success": False,
                "message": str(e),
                "details": str(e),
            },
        )

    target = host_port_string(host, port)

    dns_status, dns_details = _resolve_dns(host, port)

    root_ca = cert_pem.strip().encode("utf-8") if cert_pem and cert_pem.strip() else None
    using_custom_cert = root_ca is not None
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
    except grpc.FutureTimeoutError:
        fut.cancel()
        probe_details = _probe_channel_error(channel)
        if probe_details and _is_tls_error(probe_details):
            if using_custom_cert:
                short_msg = (
                    "TLS handshake failed -- the provided certificate may not "
                    "match the server's CA chain. Verify the PEM content."
                )
            else:
                short_msg = (
                    "TLS handshake failed -- the server's certificate is not "
                    "trusted by the system trust store. If the collector uses a "
                    "private or self-signed certificate, paste its CA certificate "
                    "in the Certificate field and retry."
                )
            return json.dumps(
                {
                    "success": False,
                    "message": short_msg,
                    "details": probe_details,
                    "approval_related": False,
                },
            )
        combined_details = dns_details or probe_details or "Timed out waiting for channel READY"
        return json.dumps(
            {
                "success": False,
                "message": _dns_enriched_timeout_msg(host, dns_status, dns_details),
                "details": combined_details,
                "approval_related": False,
            },
        )
    except Exception as e:
        short_msg, details = _classify_exception(e, using_custom_cert=using_custom_cert)
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
