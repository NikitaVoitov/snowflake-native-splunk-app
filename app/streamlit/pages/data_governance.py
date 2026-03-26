from snowflake.snowpark.exceptions import SnowparkSQLException
from utils.config import load_config, save_config
from utils.snowflake import get_session

import streamlit as st

_GOVERNANCE_ACK_KEY = "governance.acknowledged"
_REDIRECT_PENDING_KEY = "data_governance_redirect_pending"


def _load_governance_acknowledged() -> bool:
    session = get_session()
    if session is None:
        return False
    try:
        return (load_config(session, _GOVERNANCE_ACK_KEY) or "").lower() == "true"
    except SnowparkSQLException:
        return False


def _on_governance_toggle() -> None:
    session = get_session()
    if session is None:
        st.session_state.data_governance_dummy_error = (
            "Snowflake session unavailable. Could not persist dummy governance acknowledgement."
        )
        return
    try:
        value = "true" if st.session_state.data_governance_dummy_complete else "false"
        save_config(session, _GOVERNANCE_ACK_KEY, value)
        st.session_state.data_governance_dummy_error = None
        st.session_state[_REDIRECT_PENDING_KEY] = (
            value == "true" and st.session_state.get("drilled_from_getting_started", False)
        )
    except SnowparkSQLException as exc:
        st.session_state.data_governance_dummy_error = (
            f"Could not persist dummy governance acknowledgement: {exc!s}"
        )

if "data_governance_dummy_complete" not in st.session_state:
    st.session_state.data_governance_dummy_complete = _load_governance_acknowledged()
if "data_governance_dummy_error" not in st.session_state:
    st.session_state.data_governance_dummy_error = None
if _REDIRECT_PENDING_KEY not in st.session_state:
    st.session_state[_REDIRECT_PENDING_KEY] = False

st.header("Data governance")
st.info("This page will be implemented in a future story.")

with st.container(border=True):
    st.markdown("**Temporary UAT completion control**")
    st.caption(
        "Use this dummy checkbox to mark the Data Governance onboarding step as complete."
    )
    st.checkbox(
        "Mark Data Governance as reviewed",
        key="data_governance_dummy_complete",
        on_change=_on_governance_toggle,
    )

    if st.session_state.data_governance_dummy_error:
        st.error(st.session_state.data_governance_dummy_error)

if st.session_state.get(_REDIRECT_PENDING_KEY):
    st.session_state[_REDIRECT_PENDING_KEY] = False
    st.session_state.drilled_from_getting_started = False
    st.switch_page("pages/getting_started.py")
