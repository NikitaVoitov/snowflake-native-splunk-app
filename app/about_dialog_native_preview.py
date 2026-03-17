"""Local-only preview for native sidebar navigation and About dialog."""

import streamlit as st

DOCS_URL = "https://docs.splunk.com"
GETTING_STARTED_TASKS = [
    ("Connect your Splunk environment", "getting_started_task_1"),
    ("Review telemetry sources", "getting_started_task_2"),
    ("Configure app settings", "getting_started_task_3"),
    ("Validate governance defaults", "getting_started_task_4"),
]

for _, task_key in GETTING_STARTED_TASKS:
    if task_key not in st.session_state:
        st.session_state[task_key] = False

completed_getting_started_tasks = sum(
    bool(st.session_state[task_key]) for _, task_key in GETTING_STARTED_TASKS
)
total_getting_started_tasks = len(GETTING_STARTED_TASKS)
getting_started_progress = (
    f"{completed_getting_started_tasks}/{total_getting_started_tasks}"
)
show_getting_started_page = completed_getting_started_tasks < total_getting_started_tasks

preview_css = """
    <style>
    div[data-testid="stDialog"] [role="dialog"] {
        width: min(34rem, calc(100vw - 2rem)) !important;
        max-width: 34rem !important;
    }
    div[data-testid="stDialog"] [data-testid="stMarkdownContainer"] h3 {
        margin-bottom: 0.25rem !important;
    }
    div[data-testid="stDialog"] [data-testid="stDialogHeader"] {
        min-height: 2rem;
    }
    div[data-testid="stDialog"] [data-testid="stDialogHeader"] span {
        display: none;
    }
    [data-testid="stSidebar"][aria-expanded="true"] {
        width: 241px !important;
        min-width: 241px !important;
        max-width: 241px !important;
        flex-basis: 241px !important;
    }
    [data-testid="stSidebar"] > div:nth-child(2) {
        display: none !important;
    }
    [data-testid="stSidebar"][aria-expanded="false"] {
        width: 0 !important;
        min-width: 0 !important;
        max-width: 0 !important;
        flex-basis: 0 !important;
        overflow: visible !important;
    }
    [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarContent"] {
        width: 0 !important;
        overflow: visible !important;
    }
    [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarHeader"] {
        width: 0 !important;
        overflow: visible !important;
    }
    [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarCollapseButton"] {
        position: fixed !important;
        left: 0.5rem !important;
        top: 0.5rem !important;
        right: auto !important;
        z-index: 1000 !important;
    }
    [data-testid="stSidebarContent"] {
        display: flex !important;
        flex-direction: column !important;
        overflow-y: hidden !important;
    }
    [data-testid="stSidebarNav"] {
        flex-shrink: 0 !important;
    }
    [data-testid="stSidebarNavSeparator"] {
        display: none !important;
    }
    [data-testid="stSidebarUserContent"] {
        flex: 1 1 auto !important;
        display: flex !important;
        flex-direction: column !important;
        justify-content: flex-end !important;
        min-height: 0 !important;
        padding-top: 0.5rem !important;
        padding-bottom: 0.5rem !important;
        overflow: hidden !important;
    }
    [data-testid="stSidebarUserContent"] > div {
        display: flex !important;
        flex-direction: column !important;
        flex: 1 1 auto !important;
        min-height: 100% !important;
    }
    [data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] {
        display: flex !important;
        flex-direction: column !important;
        justify-content: flex-end !important;
        gap: 0.25rem !important;
        min-height: 100% !important;
    }
    [data-testid="stSidebarUserContent"] hr {
        margin-left: -1rem !important;
        margin-top: 0 !important;
        margin-bottom: 0.25rem !important;
        margin-right: -1.5rem !important;
        width: calc(100% + 2.5rem) !important;
    }
    [data-testid="stSidebarUserContent"] [data-testid="stButton"] button {
        justify-content: flex-start !important;
        padding-left: 0.5rem !important;
    }
    [data-testid="stSidebarUserContent"] [data-testid="stButton"] button > div {
        justify-content: flex-start !important;
    }
    </style>
    """

if show_getting_started_page:
    preview_css += """
    <style>
    [data-testid="stSidebarNavItems"] > li:first-child [data-testid="stSidebarNavLink"] {
        padding-right: 0.5rem !important;
    }
    [data-testid="stSidebarNavItems"] > li:first-child [data-testid="stSidebarNavLink"]::after {
        content: "__GETTING_STARTED_PROGRESS__";
        margin-left: auto;
        padding-left: 0.75rem;
        font-size: 0.95rem;
        font-weight: 600;
        line-height: 1;
        color: rgb(49, 51, 63);
    }
    </style>
    """

st.markdown(
    preview_css.replace("__GETTING_STARTED_PROGRESS__", getting_started_progress),
    unsafe_allow_html=True,
)


@st.dialog(" ", width="medium")
def show_about_dialog() -> None:
    _, content, _ = st.columns([1.1, 1.8, 1.1], vertical_alignment="top")

    with content:
        st.markdown(
            "### Splunk Observability",
            width="stretch",
            text_alignment="center",
        )
        st.markdown(
            ":gray[for Snowflake]  \n:gray[Version 1.0.0]",
            width="stretch",
            text_alignment="center",
        )
        st.markdown("")
        st.markdown(
            "Copyright © 2026 Splunk Inc.  \nAll rights reserved.",
            width="stretch",
            text_alignment="center",
        )
        st.markdown("")

    _, button_col, _ = st.columns([1.05, 1.45, 1.05])
    with button_col:
        st.link_button(
            "Documentation",
            DOCS_URL,
            icon=":material/open_in_new:",
            width="stretch",
        )


def render_page(title: str, description: str) -> None:
    st.title(title)
    st.caption("Local-only preview using native `st.navigation(position='sidebar')`.")
    st.info(description)

    _, center, _ = st.columns([1, 1.25, 1])
    with center:
        if st.button(
            "Open About Dialog",
            icon=":material/info:",
            width="stretch",
            type="primary",
        ):
            show_about_dialog()


def getting_started_page() -> None:
    st.title("Getting started")
    st.caption("Local-only preview using native `st.navigation(position='sidebar')`.")
    st.info(
        "This page previews live onboarding progress in a native sidebar item. "
        "When all four tasks are completed, the sidebar item disappears."
    )

    st.subheader(f"Progress: {getting_started_progress}")
    for task_label, task_key in GETTING_STARTED_TASKS:
        st.checkbox(task_label, key=task_key)

    _, center, _ = st.columns([1, 1.25, 1])
    with center:
        if st.button(
            "Open About Dialog",
            icon=":material/info:",
            width="stretch",
            type="primary",
        ):
            show_about_dialog()


def observability_health_page() -> None:
    render_page(
        "Observability health",
        "Stub content for the native-navigation preview.",
    )


def telemetry_sources_page() -> None:
    render_page(
        "Telemetry sources",
        "Stub content for the native-navigation preview.",
    )


def splunk_settings_page() -> None:
    render_page(
        "Splunk settings",
        "Stub content for the native-navigation preview.",
    )


def data_governance_page() -> None:
    render_page(
        "Data governance",
        "Stub content for the native-navigation preview.",
    )


pages = []

if show_getting_started_page:
    pages.append(
        st.Page(
            getting_started_page,
            title="Getting started",
            icon=":material/rocket_launch:",
            default=True,
        )
    )

pages.extend(
    [
        st.Page(
            observability_health_page,
            title="Observability health",
            icon=":material/dashboard:",
            default=not show_getting_started_page,
        ),
        st.Page(
            telemetry_sources_page,
            title="Telemetry sources",
            icon=":material/database:",
        ),
        st.Page(
            splunk_settings_page,
            title="Splunk settings",
            icon=":material/settings:",
        ),
        st.Page(
            data_governance_page,
            title="Data governance",
            icon=":material/shield:",
        ),
    ]
)

current_page = st.navigation(pages, position="sidebar", expanded=True)

with st.sidebar:
    st.divider()
    if st.button(
        "About",
        icon=":material/info:",
        width="stretch",
        type="tertiary",
    ):
        show_about_dialog()

current_page.run()
