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


def provision_egress(session: Session, endpoint: str) -> str:
    """Update network rule and app specification for the given OTLP endpoint."""
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
    current_norm = _normalize_value_list_entry(current_raw) if current_raw else None

    if current_norm == host_port_norm:
        return json.dumps(
            {
                "provisioned": True,
                "host_port": host_port,
                "specification_changed": False,
                "needs_approval": False,
                "message": f"Already provisioned for {host_port}",
            },
        )

    try:
        session.sql(
            f"ALTER NETWORK RULE {_NETWORK_RULE_FQN} SET VALUE_LIST = ('{host_port}')",
        ).collect()

        session.sql(
            f"""
            ALTER APPLICATION SET SPECIFICATION {_APP_SPEC_NAME}
                TYPE = EXTERNAL_ACCESS
                LABEL = '{_APP_SPEC_LABEL}'
                DESCRIPTION = '{_APP_SPEC_DESC}'
                HOST_PORTS = ('{host_port}')
            """,
        ).collect()
    except Exception as e:
        return json.dumps(
            {
                "provisioned": False,
                "host_port": host_port,
                "specification_changed": False,
                "needs_approval": False,
                "message": f"Provisioning failed: {e!s}",
            },
        )

    return json.dumps(
        {
            "provisioned": True,
            "host_port": host_port,
            "specification_changed": True,
            "needs_approval": True,
            "message": f"Provisioned egress for {host_port}; approve app specification if required",
        },
    )
