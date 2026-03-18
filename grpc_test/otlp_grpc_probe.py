#!/usr/bin/env python3
"""
OTLP gRPC connectivity probe — Approaches A & B from grpc_connectivity_testing_nites.md.

Approach A: Pure gRPC/TLS readiness probe — wait for channel READY.
Approach B: Same + subscribe to connectivity state transitions for diagnostics.

Usage:
  python otlp_grpc_probe.py otelcol.israelcentral.cloudapp.azure.com:4317
  python otlp_grpc_probe.py otelcol.israelcentral.cloudapp.azure.com:4317 --approach b
  python otlp_grpc_probe.py host:port --tls --pem /path/to/ca.pem
  python otlp_grpc_probe.py host:port --diagnose --pem /path/to/ca.pem  # plaintext vs TLS comparison
"""

from __future__ import annotations

import argparse
import socket
import ssl
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import grpc


DEFAULT_TIMEOUT = 10.0
DIAGNOSE_TIMEOUT = (
    3.0  # Shorter timeout for plaintext probe to distinguish TLS vs network
)
_ERRNO_CONNREFUSED = 111


@dataclass(slots=True)
class StateTransition:
    """A single connectivity state change with timestamp."""

    state: str
    timestamp: str


@dataclass(slots=True)
class ProbeResult:
    """Structured probe result for diagnostics."""

    success: bool
    final_state: str
    state_transitions: list[StateTransition] = field(default_factory=list)
    message: str = ""
    error: str | None = None


def _state_name(state: grpc.ChannelConnectivity) -> str:
    """Map gRPC connectivity enum to string."""
    names = {
        grpc.ChannelConnectivity.IDLE: "IDLE",
        grpc.ChannelConnectivity.CONNECTING: "CONNECTING",
        grpc.ChannelConnectivity.READY: "READY",
        grpc.ChannelConnectivity.TRANSIENT_FAILURE: "TRANSIENT_FAILURE",
        grpc.ChannelConnectivity.SHUTDOWN: "SHUTDOWN",
    }
    return names.get(state, str(state))


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_endpoint(endpoint: str) -> tuple[str, int]:
    """Parse host:port into (host, port)."""
    if ":" in endpoint:
        host, port_str = endpoint.rsplit(":", 1)
        return host, int(port_str)
    return endpoint, 4317


@dataclass(slots=True)
class SslCheckResult:
    """Result of SSL handshake check for cert error diagnostics."""

    success: bool
    error_type: str  # "CERT_VERIFY", "CONNECTION_REFUSED", "TIMEOUT", "OTHER"
    message: str


def _ssl_cert_check(
    endpoint: str,
    root_pem: bytes,
    timeout: float = 3.0,
) -> SslCheckResult:
    """
    Perform TLS handshake with Python ssl to capture cert verification errors.
    gRPC surfaces these as generic timeout; this gives actionable diagnostics.
    """
    host, port = _parse_endpoint(endpoint)
    ctx = ssl.create_default_context()
    try:
        ctx.load_verify_locations(cadata=root_pem.decode("utf-8"))
    except ssl.SSLError as e:
        return SslCheckResult(
            success=False,
            error_type="PEM_INVALID",
            message=f"Invalid PEM/CA: {e}",
        )
    except Exception as e:
        return SslCheckResult(
            success=False,
            error_type="PEM_INVALID",
            message=str(e),
        )

    try:
        with (
            socket.create_connection((host, port), timeout=timeout) as sock,
            ctx.wrap_socket(sock, server_hostname=host),
        ):
            pass
        return SslCheckResult(success=True, error_type="", message="TLS handshake OK")
    except ssl.SSLCertVerificationError as e:
        msg = str(e).strip()
        err_type = (
            "HOSTNAME_MISMATCH"
            if "hostname" in msg.lower() or "doesn't match" in msg.lower()
            else "CERT_VERIFY"
        )
        return SslCheckResult(success=False, error_type=err_type, message=msg)
    except ssl.SSLError as e:
        return SslCheckResult(success=False, error_type="SSL_ERROR", message=str(e))
    except (ConnectionRefusedError, OSError) as e:
        err = e.errno if hasattr(e, "errno") else None
        err_type = (
            "CONNECTION_REFUSED"
            if err == _ERRNO_CONNREFUSED or "refused" in str(e).lower()
            else "NETWORK"
        )
        return SslCheckResult(success=False, error_type=err_type, message=str(e))
    except TimeoutError:
        return SslCheckResult(
            success=False, error_type="TIMEOUT", message="Connection timed out"
        )
    except Exception as e:
        return SslCheckResult(success=False, error_type="OTHER", message=str(e))


def probe_approach_a(
    target: str,
    *,
    use_tls: bool = False,
    root_pem: bytes | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> ProbeResult:
    """
    Approach A — Pure gRPC/TLS readiness probe.

    Open channel, wait for READY. No state transition logging.
    """
    if use_tls and root_pem:
        credentials = grpc.ssl_channel_credentials(root_certificates=root_pem)
        channel = grpc.secure_channel(target, credentials)
    else:
        channel = grpc.insecure_channel(target)

    try:
        grpc.channel_ready_future(channel).result(timeout=timeout)
        return ProbeResult(
            success=True,
            final_state="READY",
            message="Channel reached READY",
        )
    except grpc.FutureTimeoutError:
        return ProbeResult(
            success=False,
            final_state="TIMEOUT",
            message="Connection timed out before reaching READY",
            error="channel_ready_future timeout",
        )
    except Exception as e:
        return ProbeResult(
            success=False,
            final_state="ERROR",
            message=str(e),
            error=type(e).__name__,
        )
    finally:
        channel.close()


def probe_approach_b(
    target: str,
    *,
    use_tls: bool = False,
    root_pem: bytes | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> ProbeResult:
    """
    Approach B — Readiness probe with connectivity-state diagnostics.

    Same as Approach A, but subscribes to state transitions and records them.
    """
    transitions: list[StateTransition] = []

    def on_connectivity_change(state: grpc.ChannelConnectivity) -> None:
        name = _state_name(state)
        transitions.append(StateTransition(state=name, timestamp=_now_iso()))

    if use_tls and root_pem:
        credentials = grpc.ssl_channel_credentials(root_certificates=root_pem)
        channel = grpc.secure_channel(target, credentials)
    else:
        channel = grpc.insecure_channel(target)

    channel.subscribe(on_connectivity_change, try_to_connect=True)

    try:
        grpc.channel_ready_future(channel).result(timeout=timeout)
        return ProbeResult(
            success=True,
            final_state="READY",
            state_transitions=transitions,
            message="Channel reached READY",
        )
    except grpc.FutureTimeoutError:
        return ProbeResult(
            success=False,
            final_state="TIMEOUT",
            state_transitions=transitions,
            message="Connection timed out before reaching READY",
            error="channel_ready_future timeout",
        )
    except Exception as e:
        return ProbeResult(
            success=False,
            final_state="ERROR",
            state_transitions=transitions,
            message=str(e),
            error=type(e).__name__,
        )
    finally:
        channel.close()


def _run_diagnose(
    endpoint: str,
    root_pem: bytes,
    timeout: float,
    verbose: bool,
) -> int:
    """
    Run plaintext and TLS probes; report comparison to distinguish TLS-only vs network.
    """
    plain_result = probe_approach_b(
        endpoint,
        use_tls=False,
        root_pem=None,
        timeout=DIAGNOSE_TIMEOUT,
    )
    tls_result = probe_approach_b(
        endpoint,
        use_tls=True,
        root_pem=root_pem,
        timeout=timeout,
    )

    plain_ok = plain_result.success
    tls_ok = tls_result.success

    print("--- Diagnostic: plaintext vs TLS ---")
    print(f"Plaintext: {'OK' if plain_ok else 'FAILED'} ({plain_result.final_state})")
    if not plain_ok and plain_result.error:
        print(f"  Error: {plain_result.error}")
    if plain_result.state_transitions:
        path = " -> ".join(t.state for t in plain_result.state_transitions)
        print(f"  States: {path}")

    print(f"TLS:      {'OK' if tls_ok else 'FAILED'} ({tls_result.final_state})")
    if not tls_ok and tls_result.error:
        print(f"  Error: {tls_result.error}")
    if tls_result.state_transitions:
        path = " -> ".join(t.state for t in tls_result.state_transitions)
        print(f"  States: {path}")

    print()
    if not plain_ok and tls_ok:
        print("Conclusion: Server requires TLS (plaintext failed, TLS succeeded).")
        print("Use --tls --pem <ca.pem> for connectivity.")
    elif plain_ok and tls_ok:
        print("Conclusion: Server accepts both plaintext and TLS.")
    elif plain_ok and not tls_ok:
        print("Conclusion: Plaintext works but TLS failed. Checking cert...")
        ssl_check = _ssl_cert_check(endpoint, root_pem, timeout=DIAGNOSE_TIMEOUT)
        if ssl_check.error_type == "CERT_VERIFY":
            print(f"  Cert error: {ssl_check.message}")
            print(
                "  → Wrong CA or cert chain. Ensure PEM is the CA that signs the server cert."
            )
        elif ssl_check.error_type == "HOSTNAME_MISMATCH":
            print(f"  Hostname mismatch: {ssl_check.message}")
            print("  → Server cert CN/SAN does not match endpoint hostname.")
        elif ssl_check.error_type == "PEM_INVALID":
            print(f"  PEM invalid: {ssl_check.message}")
            print("  → Run pem_validator.py on your PEM file.")
        elif ssl_check.error_type in ("CONNECTION_REFUSED", "TIMEOUT", "NETWORK"):
            print(f"  Network: {ssl_check.message}")
        else:
            print(f"  TLS error: {ssl_check.message}")
    else:
        print("Conclusion: Both plaintext and TLS failed. Checking cert...")
        ssl_check = _ssl_cert_check(endpoint, root_pem, timeout=DIAGNOSE_TIMEOUT)
        if ssl_check.error_type == "CERT_VERIFY":
            print(f"  Cert error: {ssl_check.message}")
            print(
                "  → Wrong CA or cert chain. Ensure PEM is the CA that signs the server cert."
            )
        elif ssl_check.error_type == "HOSTNAME_MISMATCH":
            print(f"  Hostname mismatch: {ssl_check.message}")
        elif ssl_check.error_type == "PEM_INVALID":
            print(f"  PEM invalid: {ssl_check.message}")
        elif ssl_check.error_type in ("CONNECTION_REFUSED", "TIMEOUT", "NETWORK"):
            print(f"  Network: {ssl_check.message}")
            print("  → Host unreachable, port not listening, or firewall blocking.")
        else:
            print(f"  Error: {ssl_check.message}")

    if verbose:
        print("\n--- Plaintext result ---")
        print(f"  Message: {plain_result.message}")
        print("\n--- TLS result ---")
        print(f"  Message: {tls_result.message}")

    return 0 if tls_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="OTLP gRPC connectivity probe (Approach A or B)",
    )
    parser.add_argument(
        "endpoint",
        help="OTLP endpoint as host:port (e.g. otelcol.example.com:4317)",
    )
    parser.add_argument(
        "--approach",
        choices=["a", "b"],
        default="b",
        help="Approach A: readiness only. Approach B: readiness + state diagnostics (default)",
    )
    parser.add_argument(
        "--tls",
        action="store_true",
        help="Use TLS (requires --pem for root CA)",
    )
    parser.add_argument(
        "--pem",
        type=Path,
        help="Path to PEM file (root CA or cert chain) for TLS",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print full structured result",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Run plaintext and TLS probes; report comparison to distinguish TLS-only vs network issues (requires --pem)",
    )
    args = parser.parse_args()

    root_pem: bytes | None = None
    if args.tls and (not args.pem or not args.pem.exists()):
        print("Error: --tls requires --pem with a valid file path", file=sys.stderr)
        return 1
    if args.diagnose and (not args.pem or not args.pem.exists()):
        print(
            "Error: --diagnose requires --pem with a valid file path", file=sys.stderr
        )
        return 1
    if (args.tls or args.diagnose) and args.pem:
        root_pem = args.pem.read_bytes()

    if args.diagnose and root_pem:
        return _run_diagnose(args.endpoint, root_pem, args.timeout, args.verbose)

    probe_fn = probe_approach_b if args.approach == "b" else probe_approach_a
    result = probe_fn(
        args.endpoint,
        use_tls=args.tls,
        root_pem=root_pem,
        timeout=args.timeout,
    )

    if args.verbose:
        print("--- Probe result ---")
        print(f"Success: {result.success}")
        print(f"Final state: {result.final_state}")
        print(f"Message: {result.message}")
        if result.error:
            print(f"Error: {result.error}")
        if result.state_transitions:
            print("State transitions:")
            for t in result.state_transitions:
                print(f"  {t.timestamp}  {t.state}")
    else:
        status = "OK" if result.success else "FAILED"
        print(f"{status}: {result.message}")
        if result.state_transitions:
            path = " -> ".join(t.state for t in result.state_transitions)
            print(f"  States: {path}")
        if not result.success:
            if result.state_transitions:
                last = result.state_transitions[-1].state
                if last == "TRANSIENT_FAILURE":
                    print(
                        "  Hint: TRANSIENT_FAILURE often means TLS mismatch (plaintext→TLS server). Try --diagnose --pem <ca.pem>"
                    )
                elif last == "CONNECTING":
                    print(
                        "  Hint: Timed out in CONNECTING. Check network/firewall/port. Try --diagnose --pem <ca.pem> to compare plaintext vs TLS."
                    )
            if args.tls and root_pem:
                ssl_check = _ssl_cert_check(
                    args.endpoint, root_pem, timeout=min(args.timeout, 5.0)
                )
                if not ssl_check.success and ssl_check.error_type in (
                    "CERT_VERIFY",
                    "HOSTNAME_MISMATCH",
                    "PEM_INVALID",
                ):
                    print(f"  Cert diagnostic: {ssl_check.message}")

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
