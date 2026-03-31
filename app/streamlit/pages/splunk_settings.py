# Target: Streamlit 1.52.2+ on Snowflake Warehouse Runtime
# Figma: Splunk Settings / Export settings (node 4495:47505) — layout mapped to native Streamlit components

from __future__ import annotations

import hashlib
import ipaddress
import json
from datetime import UTC, datetime
from typing import Any

import validators
from snowflake.snowpark.exceptions import SnowparkSQLException
from utils.config import load_config, save_config
from utils.snowflake import get_session

import streamlit as st

APPROVAL_WARNING = (
    "External access approval required. In Snowsight, go to **Data Products > Apps**, "
    "open this app, then select the **Configurations** tab. Under the **Connections** "
    "section you will see *Updates pending review* -- click **Review**, toggle the "
    "**OTLP gRPC Export** entry on, and click **Save**. You must use a role with the "
    "MANAGE APPLICATION SPECIFICATIONS privilege (granted by default to SECURITYADMIN). "
    "Then return here and click **Test connection** again."
)

_APPROVAL_HINTS = (
    "approve",
    "approval",
    "specification",
    "external access",
    "not approved",
    "pending approval",
    "app specification",
)


def _is_ipv4(host: str) -> bool:
    try:
        ipaddress.IPv4Address(host)
        return True
    except ValueError:
        return False


def _validate_endpoint_format(endpoint: str) -> str | None:
    """Client-side format check using validators + ipaddress. Returns error or None."""
    s = endpoint.strip()
    if not s:
        return None

    low = s.lower()
    if low.startswith("http://"):
        return "Plain HTTP is not supported. Use hostname:port format (e.g. collector.example.com:4317)."
    if low.startswith("https://"):
        s = s[8:]

    if any(c in s for c in (" ", "\t", "\n", ";", "'", '"', "\\", "/", "?", "#")):
        return "Endpoint contains invalid characters. Use hostname:port format."

    host_part = s
    if ":" in s:
        host_part, port_str = s.rsplit(":", 1)
        if not port_str.isdigit():
            return "Port must be a number."
        port_val = int(port_str)
        if port_val < 1 or port_val > 65535:
            return f"Port {port_val} is out of the valid range (1-65535)."

    host = host_part.strip()
    if not host:
        return "Hostname is empty."

    if _is_ipv4(host):
        return (
            "IP addresses are not supported for Snowflake external access. "
            "Use a fully-qualified hostname instead (e.g. collector.example.com)."
        )

    if not validators.domain(host):
        return f"'{host}' is not a valid fully-qualified domain name. Use a complete hostname like collector.example.com."

    return None


def _is_approval_related(text: str) -> bool:
    low = text.lower()
    return any(hint in low for hint in _APPROVAL_HINTS)


def _pem_fingerprint(raw_pem: str) -> str:
    """SHA-256 fingerprint of the PEM after normalizing line endings."""
    normalized = raw_pem.strip().replace("\r\n", "\n").encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def _load_saved_endpoint() -> str:
    """Load saved OTLP endpoint from _internal.config; return empty string on failure."""
    sess = get_session()
    if sess is None:
        return ""
    try:
        return load_config(sess, "otlp.endpoint") or ""
    except SnowparkSQLException:
        return ""


def _pem_secret_stored() -> bool:
    """Return True when an app-owned PEM secret has been stored."""
    sess = get_session()
    if sess is None:
        return False
    try:
        return (load_config(sess, "otlp.pem_secret_ref") or "") == "stored"
    except SnowparkSQLException:
        return False


def _load_saved_pem() -> str:
    """Load the stored PEM certificate from the app-owned secret via SP."""
    sess = get_session()
    if sess is None:
        return ""
    try:
        result = sess.call("app_public.get_pem_secret")
        return (result or "").strip() if isinstance(result, str) else ""
    except SnowparkSQLException:
        return ""


def _init_session_state() -> None:
    if "otlp_endpoint_hydrated" not in st.session_state:
        saved = _load_saved_endpoint()
        st.session_state.otlp_endpoint = saved
        st.session_state.endpoint_saved = saved or None
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
    if "endpoint_format_error" not in st.session_state:
        st.session_state.endpoint_format_error = None
    if "settings_just_saved" not in st.session_state:
        st.session_state.settings_just_saved = False
    if "pem_ref_bound" not in st.session_state:
        st.session_state.pem_ref_bound = False

    st.session_state.pem_ref_bound = _pem_secret_stored()

    if "otlp_cert_pem_hydrated" not in st.session_state:
        saved_pem = _load_saved_pem() if st.session_state.pem_ref_bound else ""
        st.session_state.otlp_cert_pem = saved_pem
        st.session_state.pem_saved_value = saved_pem
        st.session_state.otlp_cert_pem_hydrated = True


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
    """Require a fresh test whenever the endpoint changes."""
    _clear_connection_state()
    st.session_state.cert_validation_result = None
    st.session_state.endpoint_format_error = None
    st.session_state.settings_just_saved = False


def _on_cert_change() -> None:
    """Reset cert validation when the PEM text changes (does not invalidate connection test)."""
    st.session_state.cert_validation_result = None
    st.session_state.settings_just_saved = False


def _on_clear() -> None:
    """Callback: reset all form state. Runs before widgets on next rerun."""
    st.session_state.otlp_endpoint = ""
    st.session_state.otlp_cert_pem = ""
    _clear_connection_state()
    st.session_state.cert_validation_result = None
    st.session_state.endpoint_format_error = None


def _on_reset() -> None:
    """Callback: reload saved endpoint and saved PEM, clear transient state."""
    st.session_state.otlp_endpoint = _load_saved_endpoint()
    saved_pem = _load_saved_pem() if _pem_secret_stored() else ""
    st.session_state.otlp_cert_pem = saved_pem
    st.session_state.pem_saved_value = saved_pem
    _clear_connection_state()
    st.session_state.cert_validation_result = None
    st.session_state.endpoint_format_error = None


def _run_connection_workflow(endpoint: str, cert_pem: str = "") -> None:
    session = get_session()
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
                    "message": prov.get("message", "Approval required"),
                    "approval": True,
                }
                return

            normalized_pem = cert_pem.strip().replace("\r\n", "\n") if cert_pem else ""
            if not normalized_pem and st.session_state.get("pem_ref_bound"):
                test = _call_proc_json(
                    session, "app_public.test_otlp_connection_with_secret", endpoint,
                )
            else:
                test = _call_proc_json(
                    session, "app_public.test_otlp_connection", endpoint, normalized_pem,
                )
    except Exception as e:
        msg = str(e)
        if _is_approval_related(msg):
            st.session_state.connection_test_result = {
                "success": False,
                "message": msg,
                "approval": True,
            }
            return
        st.session_state.connection_test_result = {
            "success": False,
            "message": f"Provisioning or connection test failed: {msg}",
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


def _run_cert_validation(cert_text: str) -> None:
    """Call the server-side SP to validate the PEM certificate."""
    session = get_session()
    if session is None:
        st.session_state.cert_validation_result = {
            "ok": False,
            "message": "Snowflake session unavailable.",
            "pem_fingerprint": None,
        }
        return

    normalized = cert_text.strip().replace("\r\n", "\n")
    try:
        with st.spinner("Validating certificate…"):
            result = _call_proc_json(
                session, "app_public.validate_otlp_certificate_pem", normalized,
            )
    except Exception as e:
        st.session_state.cert_validation_result = {
            "ok": False,
            "message": f"Certificate validation failed: {e!s}",
            "pem_fingerprint": _pem_fingerprint(cert_text),
        }
        return

    result["pem_fingerprint"] = result.get("pem_fingerprint") or _pem_fingerprint(cert_text)
    st.session_state.cert_validation_result = result


# ---------------------------------------------------------------------------
# Interactive fragment — widget reruns stay inside; static chrome is stable
# ---------------------------------------------------------------------------
@st.fragment
def _interactive_content():
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
            fmt_err = _validate_endpoint_format(ep)
            if fmt_err:
                st.session_state.endpoint_format_error = fmt_err
                st.session_state.connection_test_result = None
            else:
                st.session_state.endpoint_format_error = None
                cert = st.session_state.get("otlp_cert_pem", "")
                _run_connection_workflow(ep, cert)

        fmt_err = st.session_state.endpoint_format_error
        if fmt_err:
            st.error(fmt_err)

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
            on_change=_on_cert_change,
        )

        cert_text = st.session_state.get("otlp_cert_pem", "").strip()
        cert_empty = not cert_text

        validate_clicked = st.button(
            "Validate certificate",
            type="secondary",
            disabled=cert_empty,
        )

        if validate_clicked and not cert_empty:
            _run_cert_validation(cert_text)

        vr = st.session_state.cert_validation_result
        if vr:
            if vr.get("ok"):
                st.success(vr.get("message", "Certificate is valid"))
            else:
                st.error(vr.get("message", "Certificate validation failed"))

    st.divider()

    if st.session_state.last_test_success_at and st.session_state.last_test_success_endpoint:
        st.caption(
            f"✓ Last test succeeded {st.session_state.last_test_success_at} to "
            f"`{st.session_state.last_test_success_endpoint}`",
        )

    connection_ok = (
        st.session_state.connection_test_result
        and st.session_state.connection_test_result.get("success")
        and st.session_state.last_test_success_endpoint == ep
    )

    just_saved = st.session_state.settings_just_saved
    current_pem = st.session_state.get("otlp_cert_pem", "").strip()
    saved_pem = st.session_state.get("pem_saved_value", "").strip()
    cert_changed = current_pem != saved_pem
    has_unsaved = (
        (ep != (st.session_state.endpoint_saved or "") or cert_changed)
        and not just_saved
    )
    save_disabled = not connection_ok or just_saved

    fc_msg, fc2, fc3 = st.columns([3, 2, 2], gap="small")
    with fc_msg:
        if just_saved:
            st.caption("Settings saved successfully.")
        elif has_unsaved and not connection_ok:
            st.caption("Run a connection test before saving.")
        elif has_unsaved:
            st.caption("You have unsaved changes.")
    with fc2:
        st.button("Reset to defaults", type="secondary", on_click=_on_reset)
    with fc3:
        save_clicked = st.button(
            "Saved" if just_saved else "Save settings",
            type="primary",
            disabled=save_disabled,
        )

    if save_clicked:
        session = get_session()
        if session is None:
            st.error("Snowflake session unavailable. Cannot save settings.")
        else:
            try:
                save_config(session, "otlp.endpoint", ep)
                st.session_state.endpoint_saved = ep

                cert = st.session_state.get("otlp_cert_pem", "").strip()
                if cert != saved_pem:
                    session.call("app_public.save_pem_secret", cert)
                    st.session_state.pem_ref_bound = bool(cert)
                    st.session_state.pem_saved_value = cert

                st.session_state.settings_just_saved = True
                st.toast("Settings saved successfully.")

                if st.session_state.get("drilled_from_getting_started"):
                    st.session_state.drilled_from_getting_started = False
                    st.switch_page("pages/getting_started.py")
                    st.stop()

                st.rerun()
            except Exception as e:
                st.error(f"Failed to save settings: {e!s}")


_PAGE_CSS = """<style>
/* Suppress Streamlit fragment container hover highlight */
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    background-color: transparent !important;
}
</style>"""


# ── Page render ──────────────────────────────────────────────────

_init_session_state()

st.markdown(_PAGE_CSS, unsafe_allow_html=True)
st.header("Splunk Settings")

tabs = st.tabs(["Export settings"])
with tabs[0]:
    _interactive_content()
