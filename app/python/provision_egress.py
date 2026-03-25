"""Provision outbound network rule and app specification for OTLP gRPC egress."""

from __future__ import annotations

import json
import re

from endpoint_parse import host_port_string, parse_endpoint
from snowflake.snowpark import Session

_NETWORK_RULE_FQN = "_internal.otlp_egress_rule"
_APP_SPEC_NAME = "otlp_egress_spec"
_APP_SPEC_LABEL = "OTLP gRPC Export"
_APP_SPEC_DESC = (
    "Connect to the configured OTLP/gRPC collector endpoint for telemetry export"
)


def _get_desc_value_list(session: Session) -> str | None:
    """Read VALUE_LIST from DESC NETWORK RULE output."""
    rows = session.sql(f"DESC NETWORK RULE {_NETWORK_RULE_FQN}").collect()
    if not rows:
        return None
    d = rows[0].as_dict() if hasattr(rows[0], "as_dict") else {}
    for k, v in d.items():
        if str(k).lower() == "value_list" and v is not None:
            return str(v)
    return None


def _normalize_value_list_entry(raw: str) -> str | None:
    """Extract first host:port from VALUE_LIST cell text."""
    if not raw:
        return None
    s = raw.strip()
    m = re.search(
        r"([A-Za-z0-9][A-Za-z0-9.-]*:\d+)",
        s,
    )
    if m:
        return m.group(1).lower()
    return None


def _get_current_app_name(session: Session) -> str | None:
    """Return the current application/database name when available."""
    try:
        rows = session.sql("SELECT CURRENT_DATABASE()").collect()
    except Exception:
        return None
    if not rows or not rows[0][0]:
        return None
    return str(rows[0][0]).strip().strip('"')


def _extract_host_ports_from_definition(raw: str) -> list[str]:
    """Extract host:port entries from SHOW SPECIFICATIONS definition JSON text."""
    return re.findall(r'"([A-Za-z0-9][A-Za-z0-9.-]*:\d+)"', raw or "")


def _get_latest_spec(session: Session) -> tuple[str | None, set[str]]:
    """Return (status, host_ports) for the highest-sequence OTLP spec.

    *host_ports* is a set of lower-cased ``host:port`` strings from the
    spec definition.  Returns ``(None, set())`` when no spec exists.
    """
    app_name = _get_current_app_name(session)
    if not app_name:
        return None, set()

    try:
        rows = session.sql(f"SHOW SPECIFICATIONS IN APPLICATION {app_name}").collect()
    except Exception:
        return None, set()

    best_seq = -1
    best_status: str | None = None
    best_hosts: set[str] = set()

    for row in rows:
        data = row.as_dict() if hasattr(row, "as_dict") else {}
        lowered = {str(k).lower(): v for k, v in data.items()}
        if str(lowered.get("name", "")).upper() != _APP_SPEC_NAME.upper():
            continue
        try:
            seq = int(lowered.get("sequence_number"))
        except (TypeError, ValueError):
            seq = -1
        if seq > best_seq:
            best_seq = seq
            best_status = str(lowered.get("status", "") or "").upper() or None
            definition = str(lowered.get("definition", "") or "")
            best_hosts = {
                e.lower() for e in _extract_host_ports_from_definition(definition)
            }

    return best_status, best_hosts


def _friendly_provision_error(raw: str, host_port: str) -> str:
    """Translate Snowflake SQL errors into actionable user messages."""
    low = raw.lower()
    if "value_list" in low and "invalid value" in low:
        return (
            f"Snowflake rejected '{host_port}' as a network rule target. "
            "HOST_PORT rules require a valid hostname (not an IP address). "
            "Use a fully-qualified domain name like collector.example.com:4317."
        )
    if "does not exist or not authorized" in low:
        return (
            "Network rule or integration object not found. "
            "Reinstall the application or contact support."
        )
    return f"Provisioning failed: {raw}"


def _set_spec_host_ports(session: Session, host_ports: set[str]) -> None:
    """Write the accumulated HOST_PORTS list to the app specification."""
    hp_sql = ", ".join(f"'{hp}'" for hp in sorted(host_ports))
    session.sql(
        f"""
        ALTER APPLICATION SET SPECIFICATION {_APP_SPEC_NAME}
            TYPE = EXTERNAL_ACCESS
            LABEL = '{_APP_SPEC_LABEL}'
            DESCRIPTION = '{_APP_SPEC_DESC}'
            HOST_PORTS = ({hp_sql})
        """,
    ).collect()


def provision_egress(session: Session, endpoint: str) -> str:
    """Update network rule and app specification for the given OTLP endpoint.

    The **network rule** always contains exactly one entry -- the active
    endpoint.  The **app specification** ``HOST_PORTS`` accumulates every
    hostname the consumer has tested so that switching back to a
    previously-approved host does not require re-approval.
    """
    try:
        host, port = parse_endpoint(endpoint)
    except ValueError as e:
        return json.dumps(
            {
                "provisioned": False,
                "host_port": "",
                "specification_changed": False,
                "needs_approval": False,
                "message": str(e),
            },
        )

    host_port = host_port_string(host, port)
    host_port_norm = host_port.lower()

    try:
        current_raw = _get_desc_value_list(session)
    except Exception:
        current_raw = None
    current_rule_host = _normalize_value_list_entry(current_raw) if current_raw else None

    spec_status, spec_hosts = _get_latest_spec(session)
    host_already_in_spec = host_port_norm in spec_hosts
    rule_already_matches = current_rule_host == host_port_norm

    if rule_already_matches and host_already_in_spec:
        needs_approval = spec_status == "PENDING"
        return json.dumps(
            {
                "provisioned": True,
                "host_port": host_port,
                "specification_changed": False,
                "needs_approval": needs_approval,
                "message": (
                    f"Approval is still pending for {host_port}"
                    if needs_approval
                    else f"Already provisioned for {host_port}"
                ),
            },
        )

    try:
        if not rule_already_matches:
            session.sql(
                f"ALTER NETWORK RULE {_NETWORK_RULE_FQN} SET VALUE_LIST = ('{host_port}')",
            ).collect()

        if not host_already_in_spec:
            accumulated = spec_hosts | {host_port_norm}
            _set_spec_host_ports(session, accumulated)
    except Exception as e:
        msg = _friendly_provision_error(str(e), host_port)
        return json.dumps(
            {
                "provisioned": False,
                "host_port": host_port,
                "specification_changed": False,
                "needs_approval": False,
                "message": msg,
            },
        )

    if host_already_in_spec and spec_status == "APPROVED":
        return json.dumps(
            {
                "provisioned": True,
                "host_port": host_port,
                "specification_changed": False,
                "needs_approval": False,
                "message": f"Provisioned egress for {host_port}",
            },
        )

    spec_status_after, _ = _get_latest_spec(session)
    needs_approval = spec_status_after == "PENDING"

    return json.dumps(
        {
            "provisioned": True,
            "host_port": host_port,
            "specification_changed": True,
            "needs_approval": needs_approval,
            "message": (
                f"Provisioned egress for {host_port}; approval is pending."
                if needs_approval
                else f"Provisioned egress for {host_port}"
            ),
        },
    )
