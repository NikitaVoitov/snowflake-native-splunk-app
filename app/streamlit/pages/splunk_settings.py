# Target: Streamlit 1.52.2+ on Snowflake Warehouse Runtime
# Figma: Splunk Settings / Export settings (node 4495:47505) — layout mapped to native Streamlit components

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import streamlit as st

_PEM_HEADER = "-----BEGIN CERTIFICATE-----"
_PEM_FOOTER = "-----END CERTIFICATE-----"

APPROVAL_WARNING = (
    "External access approval required. Please approve the 'OTLP gRPC Export' "
    "specification in the app configuration panel (Snowsight → Data Products → Apps → "
    "Splunk Observability → Manage Access). Then run Test connection again."
)


def _snowpark_session() -> Any:
    try:
        from snowflake.snowpark.context import get_active_session

        return get_active_session()
    except Exception:
        return None


def _load_saved_endpoint() -> str:
    """Load saved OTLP endpoint from _internal.config; return empty string on failure."""
    sess = _snowpark_session()
    if sess is None:
        return ""
    try:
        rows = sess.sql(
            "SELECT CONFIG_VALUE FROM _internal.config WHERE CONFIG_KEY = 'otlp.endpoint'",
        ).collect()
        if rows and rows[0][0]:
            return str(rows[0][0]).strip()
    except Exception:  # noqa: S110 — config row may not exist yet
        pass
    return ""


def _init_session_state() -> None:
    if "otlp_endpoint_hydrated" not in st.session_state:
        st.session_state.otlp_endpoint = _load_saved_endpoint()
        st.session_state.otlp_endpoint_hydrated = True

    if "connection_test_result" not in st.session_state:
        st.session_state.connection_test_result = None
    if "eai_needs_approval" not in st.session_state:
        st.session_state.eai_needs_approval = False
    if "last_test_success_at" not in st.session_state:
        st.session_state.last_test_success_at = None
    if "last_test_success_endpoint" not in st.session_state:
        st.session_state.last_test_success_endpoint = None
    if "cert_validation_result" not in st.session_state:
        st.session_state.cert_validation_result = None


def _call_proc_json(session: Any, proc_fqn: str, *args: str) -> dict[str, Any]:
    raw = session.call(proc_fqn, *args)
    s = raw if isinstance(raw, str) else str(raw)
    return json.loads(s)


def _clear_connection_state() -> None:
    """Invalidate the last connection test outcome."""
    st.session_state.connection_test_result = None
    st.session_state.eai_needs_approval = False
    st.session_state.last_test_success_at = None
    st.session_state.last_test_success_endpoint = None


def _on_connection_inputs_change() -> None:
    """Require a fresh test whenever connection inputs change."""
    _clear_connection_state()
    st.session_state.cert_validation_result = None


def _on_clear() -> None:
    """Callback: reset all form state. Runs before widgets on next rerun."""
    st.session_state.otlp_endpoint = ""
    st.session_state.otlp_cert_pem = ""
    _clear_connection_state()
    st.session_state.cert_validation_result = None


def _on_reset() -> None:
    """Callback: reload saved endpoint, clear transient state."""
    st.session_state.otlp_endpoint = _load_saved_endpoint()
    st.session_state.otlp_cert_pem = ""
    _clear_connection_state()
    st.session_state.cert_validation_result = None


def _run_connection_workflow(endpoint: str, cert_pem: str = "") -> None:
    session = _snowpark_session()
    if session is None:
        st.session_state.connection_test_result = {
            "success": False,
            "message": (
                "Snowflake session unavailable. Open this page from the installed Native App "
                "to run the connection test."
            ),
        }
        return

    try:
        with st.spinner("Provisioning outbound access and testing connection…"):
            prov = _call_proc_json(session, "app_public.provision_otlp_egress", endpoint)
            if not prov.get("provisioned"):
                st.session_state.connection_test_result = {
                    "success": False,
                    "message": prov.get("message", "Provisioning failed"),
                }
                return

            st.session_state.eai_needs_approval = bool(prov.get("needs_approval"))

            if prov.get("needs_approval"):
                st.session_state.connection_test_result = {
                    "success": False,
                    "message": "Approval required",
                    "approval": True,
                }
                return

            test = _call_proc_json(
                session, "app_public.test_otlp_connection", endpoint, cert_pem,
            )
    except Exception as e:
        st.session_state.connection_test_result = {
            "success": False,
            "message": f"Provisioning or connection test failed: {e!s}",
        }
        return

    if test.get("success"):
        st.session_state.connection_test_result = {
            "success": True,
            "message": test.get("message", "Connection successful"),
        }
        st.session_state.last_test_success_at = datetime.now(UTC).strftime(
            "%Y-%m-%d %H:%M:%S UTC",
        )
        st.session_state.last_test_success_endpoint = endpoint.strip()
        return

    if test.get("approval_related"):
        st.session_state.connection_test_result = {
            "success": False,
            "message": test.get("message", "Approval may be required"),
            "approval": True,
        }
        return

    st.session_state.connection_test_result = {
        "success": False,
        "message": test.get("message", "Connection failed"),
        "details": test.get("details", ""),
    }


_init_session_state()

st.header("Splunk Settings")

tabs = st.tabs(["Export settings"])
with tabs[0]:
    st.subheader("OTLP Export")
    st.caption("Configure OTLP/gRPC export to your remote OpenTelemetry collector.")

    with st.container(border=True):
        st.markdown("**OTLP endpoint (gRPC)**")
        st.caption("Maps to OTEL_EXPORTER_OTLP_ENDPOINT.")
        st.text_input(
            "OTLP endpoint",
            key="otlp_endpoint",
            placeholder="collector.example.com:4317",
            label_visibility="collapsed",
            on_change=_on_connection_inputs_change,
        )

        ep = st.session_state.otlp_endpoint.strip()

        bc1, bc2, _ = st.columns([2, 1, 5], gap="small")
        with bc1:
            test_clicked = st.button(
                "Test connection",
                type="secondary",
                disabled=not ep,
            )
        with bc2:
            st.button("Clear", type="secondary", on_click=_on_clear)

        if test_clicked:
            cert = st.session_state.get("otlp_cert_pem", "")
            _run_connection_workflow(ep, cert)

        res = st.session_state.connection_test_result
        if res:
            if res.get("success"):
                st.success("Connection successful")
            elif res.get("approval"):
                st.warning(APPROVAL_WARNING)
            else:
                st.error(res.get("message", "Connection failed"))

    with st.container(border=True):
        st.markdown("**Certificate (optional)**")
        st.caption(
            "Paste a PEM-encoded certificate if your collector uses a "
            "private/self-signed certificate. Leave empty to use the system trust "
            "store (OTEL_EXPORTER_OTLP_CERTIFICATE).",
        )
        st.text_area(
            "Certificate PEM",
            key="otlp_cert_pem",
            height=120,
            placeholder=(
                "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----\n"
            ),
            label_visibility="collapsed",
            on_change=_on_connection_inputs_change,
        )

        cert_text = st.session_state.get("otlp_cert_pem", "").strip()
        cert_empty = not cert_text

        validate_clicked = st.button(
            "Validate certificate",
            type="secondary",
            disabled=cert_empty,
        )

        if validate_clicked and not cert_empty:
            if _PEM_HEADER not in cert_text or _PEM_FOOTER not in cert_text:
                st.session_state.cert_validation_result = {
                    "ok": False,
                    "msg": "Not a valid PEM certificate — missing BEGIN/END CERTIFICATE markers.",
                }
            elif cert_text.count(_PEM_HEADER) != cert_text.count(_PEM_FOOTER):
                st.session_state.cert_validation_result = {
                    "ok": False,
                    "msg": "Mismatched BEGIN/END CERTIFICATE markers.",
                }
            else:
                st.session_state.cert_validation_result = {
                    "ok": True,
                    "msg": "PEM format looks valid.",
                }

        vr = st.session_state.cert_validation_result
        if vr:
            if vr["ok"]:
                st.success(vr["msg"])
            else:
                st.error(vr["msg"])

    st.divider()

    if st.session_state.last_test_success_at and st.session_state.last_test_success_endpoint:
        st.caption(
            f"✓ Last test succeeded {st.session_state.last_test_success_at} to "
            f"`{st.session_state.last_test_success_endpoint}`",
        )

    fc_msg, fc2, fc3 = st.columns([3, 2, 2], gap="small")
    with fc_msg:
        st.caption("You have unsaved changes.")
    with fc2:
        st.button("Reset to defaults", type="secondary", on_click=_on_reset)
    save_disabled = not (
        st.session_state.connection_test_result
        and st.session_state.connection_test_result.get("success")
        and st.session_state.last_test_success_endpoint == ep
    )
    with fc3:
        save_clicked = st.button(
            "Save settings",
            type="primary",
            disabled=save_disabled,
        )

    if save_clicked:
        st.info("Save functionality is coming in the next story.")
