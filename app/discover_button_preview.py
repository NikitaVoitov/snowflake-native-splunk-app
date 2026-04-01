# Target: Streamlit 1.52.2 on Snowflake Warehouse Runtime
# Local preview for the Discover Sources button + info bar layout
from __future__ import annotations

import time
from datetime import datetime

import streamlit as st

_DISCOVERY_RUNNING_KEY = "ts_discovery_running"
_DISCOVERY_TIMESTAMP_KEY = "ts_last_discovered"
_DISCOVERY_DONE_KEY = "ts_discovery_done_once"

if _DISCOVERY_RUNNING_KEY not in st.session_state:
    st.session_state[_DISCOVERY_RUNNING_KEY] = False
if _DISCOVERY_TIMESTAMP_KEY not in st.session_state:
    st.session_state[_DISCOVERY_TIMESTAMP_KEY] = None
if _DISCOVERY_DONE_KEY not in st.session_state:
    st.session_state[_DISCOVERY_DONE_KEY] = False

_PAGE_CSS = """
<style>
div[data-testid="stElementContainer"]:has(.info-bar-marker) {
    display: none !important;
}
div[data-testid="stElementContainer"]:has(.info-bar-marker)
    + div[data-testid="stLayoutWrapper"] div[data-testid="stHorizontalBlock"] {
    background-color: rgba(151, 166, 195, 0.15);
    border-radius: 0.5rem;
    padding: 0.75rem 1rem;
    align-items: center !important;
    flex-wrap: nowrap !important;
}
div[data-testid="stElementContainer"]:has(.info-bar-marker)
    + div[data-testid="stLayoutWrapper"] div[data-testid="stHorizontalBlock"]
    div[data-testid="stMarkdownContainer"] {
    margin-bottom: 0 !important;
}
div[data-testid="stElementContainer"]:has(.info-bar-marker)
    + div[data-testid="stLayoutWrapper"] div[data-testid="stHorizontalBlock"]
    div[data-testid="stMarkdownContainer"] p {
    margin: 0 !important;
}
div[data-testid="stElementContainer"]:has(.info-bar-marker)
    + div[data-testid="stLayoutWrapper"] div[data-testid="stHorizontalBlock"]
    div[data-testid="stColumn"] {
    margin: 0 !important;
}
div[data-testid="stElementContainer"]:has(.info-bar-marker)
    + div[data-testid="stLayoutWrapper"] div[data-testid="stHorizontalBlock"]
    div[data-testid="stColumn"]:first-child span[role="img"] {
    font-size: 1.25rem !important;
    color: rgba(49, 51, 63, 0.6) !important;
    vertical-align: middle !important;
}
div[data-testid="stElementContainer"]:has(.info-bar-marker)
    + div[data-testid="stLayoutWrapper"] div[data-testid="stHorizontalBlock"]
    div[data-testid="stColumn"]:first-child {
    flex: 0 0 auto !important;
    width: auto !important;
}
div[data-testid="stElementContainer"]:has(.info-bar-marker)
    + div[data-testid="stLayoutWrapper"] div[data-testid="stHorizontalBlock"]
    div[data-testid="stColumn"]:nth-child(2) {
    flex: 1 1 0 !important;
    min-width: 0 !important;
}
div[data-testid="stElementContainer"]:has(.info-bar-marker)
    + div[data-testid="stLayoutWrapper"] div[data-testid="stHorizontalBlock"]
    div[data-testid="stColumn"]:last-child {
    flex: 0 0 auto !important;
    width: auto !important;
}
div[data-testid="stElementContainer"]:has(.info-bar-marker)
    + div[data-testid="stLayoutWrapper"] div[data-testid="stHorizontalBlock"]
    div[data-testid="stColumn"]:last-child div[data-testid="stButton"] button {
    white-space: nowrap !important;
    min-width: 10.5rem !important;
}
</style>
"""


def _start_discovery():
    st.session_state[_DISCOVERY_RUNNING_KEY] = True


def _render_info_bar():
    timestamp = st.session_state.get(_DISCOVERY_TIMESTAMP_KEY)
    is_running = st.session_state.get(_DISCOVERY_RUNNING_KEY, False)

    st.markdown('<span class="info-bar-marker"></span>', unsafe_allow_html=True)
    icon_col, text_col, btn_col = st.columns(
        [0.3, 7.7, 2], vertical_alignment="center",
    )

    with icon_col:
        st.markdown(":material/info:")

    with text_col:
        text = (
            "Enable categories and individual sources to start collecting telemetry. "
            "Custom views allow you to apply Snowflake masking and row-access policies "
            "to exported data."
        )
        if timestamp:
            ts_str = timestamp.strftime("%-I:%M:%S %p")
            text += f" · :blue[Last discovered: {ts_str}]"
        st.markdown(text)

    with btn_col:
        if is_running:
            st.button(
                "Discovering...",
                icon="spinner",
                disabled=True,
                key="discover_btn",
            )
        else:
            st.button(
                "Discover sources",
                icon=":material/sync:",
                on_click=_start_discovery,
                key="discover_btn",
            )


st.markdown(_PAGE_CSS, unsafe_allow_html=True)
st.header("Telemetry Sources")
st.caption(
    "Configure monitoring packs and select data sources from Event Tables "
    "and ACCOUNT_USAGE views. Set polling intervals and batch sizes for each source."
)

_render_info_bar()

if st.session_state.get(_DISCOVERY_RUNNING_KEY):
    time.sleep(3)
    st.session_state[_DISCOVERY_RUNNING_KEY] = False
    st.session_state[_DISCOVERY_TIMESTAMP_KEY] = datetime.now()
    st.session_state[_DISCOVERY_DONE_KEY] = True
    st.rerun()

if st.session_state.get(_DISCOVERY_DONE_KEY):
    st.success("Discovery complete! (mock)")
    with st.container(border=True):
        st.write("Category tiles would go here...")
