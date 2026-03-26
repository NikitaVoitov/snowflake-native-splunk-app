from snowflake.snowpark.exceptions import SnowparkSQLException
from utils.config import load_config, save_config
from utils.snowflake import get_session

import streamlit as st

_DUMMY_PACK_KEY = "pack_enabled.dummy"
_REDIRECT_PENDING_KEY = "telemetry_sources_redirect_pending"


def _load_dummy_pack_enabled() -> bool:
    session = get_session()
    if session is None:
        return False
    try:
        return (load_config(session, _DUMMY_PACK_KEY) or "").lower() == "true"
    except SnowparkSQLException:
        return False


def _on_dummy_pack_toggle() -> None:
    session = get_session()
    if session is None:
        st.session_state.telemetry_sources_dummy_error = (
            "Snowflake session unavailable. Could not persist dummy pack selection."
        )
        return
    try:
        value = "true" if st.session_state.telemetry_sources_dummy_complete else "false"
        save_config(session, _DUMMY_PACK_KEY, value)
        st.session_state.telemetry_sources_dummy_error = None
        st.session_state[_REDIRECT_PENDING_KEY] = (
            value == "true" and st.session_state.get("drilled_from_getting_started", False)
        )
    except SnowparkSQLException as exc:
        st.session_state.telemetry_sources_dummy_error = (
            f"Could not persist dummy pack selection: {exc!s}"
        )

if "telemetry_sources_dummy_complete" not in st.session_state:
    st.session_state.telemetry_sources_dummy_complete = _load_dummy_pack_enabled()
if "telemetry_sources_dummy_error" not in st.session_state:
    st.session_state.telemetry_sources_dummy_error = None
if _REDIRECT_PENDING_KEY not in st.session_state:
    st.session_state[_REDIRECT_PENDING_KEY] = False

st.header("Telemetry sources")
st.info("This page will be implemented in a future story.")

with st.container(border=True):
    st.markdown("**Temporary UAT completion control**")
    st.caption(
        "Use this dummy checkbox to mark the Telemetry Sources onboarding step as complete."
    )
    st.checkbox(
        "Mark Telemetry Sources as configured",
        key="telemetry_sources_dummy_complete",
        on_change=_on_dummy_pack_toggle,
    )

    if st.session_state.telemetry_sources_dummy_error:
        st.error(st.session_state.telemetry_sources_dummy_error)

if st.session_state.get(_REDIRECT_PENDING_KEY):
    st.session_state[_REDIRECT_PENDING_KEY] = False
    st.session_state.drilled_from_getting_started = False
    st.switch_page("pages/getting_started.py")
