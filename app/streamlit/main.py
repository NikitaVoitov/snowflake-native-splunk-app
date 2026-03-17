import streamlit as st

DOCS_URL = "https://docs.splunk.com"

st.markdown(
    """
    <style>
    /* ── Sidebar flex layout ── */
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

    /* ── Full-width dividers ── */
    [data-testid="stSidebarUserContent"] hr {
        margin-left: -20px !important;
        margin-right: -20px !important;
        width: calc(100% + 40px) !important;
    }

    /* ── Header divider (2nd element): tight spacing ── */
    [data-testid="stSidebarUserContent"]
        [data-testid="stVerticalBlock"]
        > [data-testid="stElementContainer"]:nth-child(2) hr {
        margin-top: 0.25rem !important;
        margin-bottom: 0.5rem !important;
    }

    /* ── Footer divider: push to bottom ── */
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

    /* ── About button: left-align to match page links ── */
    [data-testid="stSidebarUserContent"] [data-testid="stButton"] button {
        justify-content: flex-start !important;
        padding-left: 8px !important;
    }
    [data-testid="stSidebarUserContent"] [data-testid="stButton"] button > div {
        justify-content: flex-start !important;
    }

    /* ── About dialog: hide title text, keep close button ── */
    div[data-testid="stDialog"] [data-testid="stDialogHeader"] {
        min-height: 2rem;
    }
    div[data-testid="stDialog"] [data-testid="stDialogHeader"] span {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "onboarding_complete" not in st.session_state:
    st.session_state.onboarding_complete = False


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


pages = [
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

pg = st.navigation(pages, position="hidden")

with st.sidebar:
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
