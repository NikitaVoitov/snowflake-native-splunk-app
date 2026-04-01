from utils.onboarding import get_completed_count, load_task_completion_state
from utils.snowflake import get_session

import streamlit as st

st.set_page_config(layout="wide")

DOCS_URL = "https://docs.splunk.com"

# ── Onboarding state (evaluated before sidebar build) ────────────
_session = get_session()
_onboarding_state = load_task_completion_state(_session)
_completion = _onboarding_state.completion
_completed = get_completed_count(_completion)
_total = len(_completion)

# Build sidebar badge CSS for Getting Started nav item.
_sel = (
    '[data-testid="stSidebarUserContent"]'
    ' [data-testid="stElementContainer"]:has(hr)'
    ' + [data-testid="stElementContainer"]'
    ' [data-testid="stPageLink-NavLink"]'
)
_badge_css = (
    f"{_sel} {{"
    " position: relative; padding-right: 3rem !important; }"
    f" {_sel}::after {{"
    f' content: "{_completed}/{_total}";'
    " position: absolute; right: 12px; top: 50%;"
    " transform: translateY(-50%);"
    " background: #ececf0; color: #0a0a0a;"
    " font-size: 12px; font-weight: 600;"
    " padding: 2px 8px; border-radius: 8px; }"
)

_GLOBAL_CSS = (
    "<style>"
    + _badge_css
    + """
    [data-testid="stSidebarContent"] {
        display: flex !important;
        flex-direction: column !important;
        position: relative !important;
    }
    [data-testid="stSidebarHeader"] {
        flex-shrink: 0;
        height: 0 !important;
        min-height: 0 !important;
        overflow: visible !important;
        padding: 0 !important;
    }
    [data-testid="stLogoSpacer"] { display: none !important; }
    [data-testid="stSidebarCollapseButton"] {
        position: absolute !important;
        top: 33px !important;
        right: 12px !important;
        z-index: 10 !important;
    }
    [data-testid="stSidebarUserContent"] {
        flex: 1 1 0 !important;
        display: flex !important;
        flex-direction: column !important;
        min-height: 0;
        padding-top: 1rem !important;
        padding-bottom: 0.5rem !important;
    }
    [data-testid="stSidebarUserContent"] > div {
        flex: 1 1 0;
        display: flex !important;
        flex-direction: column !important;
    }

    [data-testid="stSidebarUserContent"] hr {
        margin-left: -20px !important;
        margin-right: -20px !important;
        width: calc(100% + 40px) !important;
    }

    [data-testid="stSidebarUserContent"]
        [data-testid="stVerticalBlock"]
        > [data-testid="stElementContainer"]:nth-child(2) hr {
        margin-top: 0.25rem !important;
        margin-bottom: 0.5rem !important;
    }

    [data-testid="stSidebarUserContent"]
        [data-testid="stVerticalBlock"]
        > [data-testid="stElementContainer"]:nth-last-child(2) {
        margin-top: auto !important;
        padding-bottom: 0 !important;
    }
    [data-testid="stSidebarUserContent"]
        [data-testid="stVerticalBlock"]
        > [data-testid="stElementContainer"]:nth-last-child(2) hr {
        margin-bottom: 0.5rem !important;
    }

    [data-testid="stSidebarUserContent"] [data-testid="stButton"] button {
        justify-content: flex-start !important;
        padding-left: 8px !important;
    }
    [data-testid="stSidebarUserContent"] [data-testid="stButton"] button > div {
        justify-content: flex-start !important;
    }

    [data-testid="stMain"] {
        align-items: flex-start !important;
    }
    [data-testid="stHeader"] {
        height: 0 !important;
        min-height: 0 !important;
        overflow: visible !important;
        padding: 0 !important;
        position: relative !important;
    }
    [data-testid="stExpandSidebarButton"] {
        position: absolute !important;
        top: 33px !important;
        left: 12px !important;
        z-index: 10 !important;
    }
    [data-testid="stMainBlockContainer"] {
        padding-top: 2rem !important;
        padding-left: 3rem !important;
        padding-right: 3rem !important;
    }

    [data-testid="stMainBlockContainer"] [data-testid="stButton"] button {
        white-space: nowrap !important;
    }

    [role="tabpanel"] [data-testid="stHorizontalBlock"] {
        gap: 0.5rem !important;
    }
    [role="tabpanel"] [data-testid="stHorizontalBlock"]
        > [data-testid="stColumn"]:has([data-testid="stButton"]) {
        flex: 0 0 auto !important;
        width: auto !important;
    }
    [role="tabpanel"] [data-testid="stHorizontalBlock"]
        > [data-testid="stColumn"]:not(:has([data-testid="stButton"])) {
        flex: 1 1 0 !important;
    }

    [role="tabpanel"] > [data-testid="stVerticalBlock"] {
        min-height: calc(100vh - 14rem);
    }
    [role="tabpanel"] > [data-testid="stVerticalBlock"]
        > [data-testid="stElementContainer"]:has(hr) {
        margin-top: auto !important;
    }

    div[data-testid="stDialog"] [data-testid="stDialogHeader"] {
        min-height: 2rem;
    }
    div[data-testid="stDialog"] [data-testid="stDialogHeader"] span {
        display: none;
    }
    </style>
    """
)

st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)

@st.dialog(" ")
def show_about() -> None:
    st.markdown(
        """
        <div style="text-align: center; padding: 0.5rem 0 0 0;">
            <p style="font-size: 1.25rem; font-weight: 700; margin: 0 0 0.25rem 0;">
                Splunk Observability</p>
            <p style="color: #717182; margin: 0 0 0.25rem 0;">for Snowflake</p>
            <p style="color: #717182; font-size: 0.85rem; margin: 0 0 1.25rem 0;">
                Version 1.0.0</p>
            <p style="margin: 0 0 0.1rem 0;">Copyright &copy; 2026 Splunk Inc.</p>
            <p style="margin: 0 0 1.5rem 0;">All rights reserved.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _, center, _ = st.columns([1, 1.8, 1])
    with center:
        st.link_button(
            "Documentation",
            DOCS_URL,
            icon=":material/open_in_new:",
            width="stretch",
        )


pages: list = []
pages.extend(
    [
        st.Page(
            "pages/getting_started.py",
            title="Getting started",
            icon=":material/rocket_launch:",
            default=True,
        ),
        st.Page(
            "pages/observability_health.py",
            title="Observability health",
            icon=":material/dashboard:",
        ),
        st.Page(
            "pages/telemetry_sources.py",
            title="Telemetry sources",
            icon=":material/database:",
        ),
        st.Page(
            "pages/splunk_settings.py",
            title="Splunk settings",
            icon=":material/settings:",
        ),
        st.Page(
            "pages/data_governance.py",
            title="Data governance",
            icon=":material/shield:",
        ),
    ]
)

pg = st.navigation(pages, position="hidden")

_current_page = pg.url_path or ""
if st.session_state.get("_nav_current_page") != _current_page:
    st.session_state["_nav_previous_page"] = st.session_state.get("_nav_current_page")
    st.session_state["_nav_current_page"] = _current_page
    st.session_state["_nav_visit_seq"] = int(st.session_state.get("_nav_visit_seq", 0)) + 1

with st.sidebar:
    if _onboarding_state.error_message:
        st.warning(_onboarding_state.error_message)

    st.markdown(
        '<div style="margin-bottom: 0.25rem;">'
        '<div style="font-size: 1.05rem; font-weight: 600; color: #0a0a0a;'
        ' line-height: 1.2;">Splunk Observability</div>'
        '<div style="font-size: 0.75rem; color: #717182;'
        ' margin-top: 0.15rem;">for Snowflake</div>'
        "</div>",
        unsafe_allow_html=True,
    )

    st.divider()

    for page in pages:
        st.page_link(page)

    st.divider()
    if st.button(
        "About",
        icon=":material/info:",
        width="stretch",
        type="tertiary",
    ):
        show_about()

pg.run()
