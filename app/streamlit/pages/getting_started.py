# Target: Streamlit 1.52.2+ on Snowflake Warehouse Runtime
# Figma: Getting Started page (node 4499:49308)

from __future__ import annotations

from utils.config import save_config
from utils.onboarding import (
    ONBOARDING_TASKS,
    get_completed_count,
    load_task_completion_state,
)
from utils.snowflake import get_session

import streamlit as st

# ── Session state init ──────────────────────────────────────────

if "drilled_from_getting_started" in st.session_state:
    st.session_state.drilled_from_getting_started = False

session = get_session()
onboarding_state = load_task_completion_state(session)
completion = onboarding_state.completion
completed = get_completed_count(completion)
total = len(ONBOARDING_TASKS)
pct = int(completed / total * 100) if total else 0


# ── Activate Export dialog (temporary placeholder for Story 2.3) ──


@st.dialog("Activate Export")
def _activate_export_dialog() -> None:
    st.markdown(
        "This is a **temporary placeholder** until the real activation "
        "workflow is implemented in Story 6.3."
    )
    st.markdown(
        "Clicking **Activate** will mark this onboarding task as complete "
        "so you can exercise the full Getting Started flow."
    )
    if st.button("Activate", type="primary", use_container_width=True):
        sess = get_session()
        if sess is not None:
            try:
                save_config(sess, "activation.completed", "true")
                st.toast("Export activated successfully.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to activate: {e!s}")
        else:
            st.error("Snowflake session unavailable.")


# ── Card renderer ────────────────────────────────────────────────

_CARD_MIN_H = 120

def _render_task_card(index: int, title: str, description: str, done: bool) -> None:
    """Render a single task card as inline HTML + transparent button overlay."""
    if done:
        bg = "rgba(236,253,245,0.3)"
        border_css = "2px solid #a4f4cf"
        icon_html = (
            '<div style="width:40px;height:40px;border-radius:50%;background:#00bc7d;'
            "display:flex;align-items:center;justify-content:center;"
            'flex-shrink:0;color:#fff;font-size:18px;font-weight:700;">&#10003;</div>'
        )
        title_color = "#717182"
        badge_html = (
            '<span style="display:inline-block;background:#d0fae5;color:#007a55;'
            'padding:3px 8px;border-radius:8px;font-size:12px;font-weight:500;'
            'margin-top:4px;">Completed</span>'
        )
    else:
        bg = "#ffffff"
        border_css = "2px solid rgba(0,0,0,0.1)"
        icon_html = (
            f'<div style="width:40px;height:40px;border-radius:50%;background:#ececf0;'
            f"display:flex;align-items:center;justify-content:center;"
            f'flex-shrink:0;color:#0a0a0a;font-size:16px;font-weight:500;">{index}</div>'
        )
        title_color = "#0a0a0a"
        badge_html = (
            '<span style="display:inline-block;visibility:hidden;'
            'padding:3px 8px;font-size:12px;margin-top:4px;">&nbsp;</span>'
        )

    cursor = "default" if done else "pointer"
    arrow = "" if done else '<span style="color:#717182;font-size:20px;flex-shrink:0;">\u2192</span>'
    card_html = (
        f'<div style="display:flex;align-items:center;gap:16px;'
        f"padding:26px;min-height:{_CARD_MIN_H}px;box-sizing:border-box;"
        f"background:{bg};border:{border_css};border-radius:14px;"
        f'cursor:{cursor};margin-bottom:16px;">'
        f"{icon_html}"
        f'<div style="flex:1;min-width:0;">'
        f'<div style="font-size:18px;font-weight:500;color:{title_color};margin-bottom:4px;">'
        f"{title}</div>"
        f'<div style="font-size:14px;color:#717182;line-height:1.4;">'
        f"{description}</div>"
        f"{badge_html}"
        f"</div>"
        f"{arrow}"
        f"</div>"
    )
    st.markdown(card_html, unsafe_allow_html=True)


# ── Page layout ──────────────────────────────────────────────────

st.header("Welcome to Splunk Observability for Snowflake")
st.caption(
    "Follow the setup guide to start exporting telemetry to your collector."
)
if onboarding_state.error_message:
    st.warning(onboarding_state.error_message)

# Progress bar section
prog_left, prog_right = st.columns([1, 1])
with prog_left:
    st.markdown("**Setup Progress**")
with prog_right:
    st.markdown(
        f'<div style="text-align:right;font-weight:500;">'
        f"{completed} of {total} tasks completed</div>",
        unsafe_allow_html=True,
    )
st.progress(completed / total if total else 0)
st.markdown(
    f'<div style="text-align:right;font-size:12px;color:#717182;margin-top:-8px;'
    f'margin-bottom:16px;">'
    f"{pct}% complete</div>",
    unsafe_allow_html=True,
)

# Task cards — each card + button grouped in st.container() so
# CSS absolute-positioning overlays the button on the correct card.
for task in ONBOARDING_TASKS:
    done = completion.get(task.step, False)
    with st.container():
        _render_task_card(task.step, task.title, task.description, done)
        if not done and st.button(
            f"Open {task.title}",
            key=f"task_nav_{task.step}",
            use_container_width=True,
            type="tertiary",
        ):
            if task.page_path is not None:
                st.session_state.drilled_from_getting_started = True
                st.switch_page(task.page_path)
            else:
                _activate_export_dialog()

# Button overlay CSS — each card+button lives inside an st.container
# whose inner stVerticalBlock becomes the positioning context.
# The button's wrapper is absolutely positioned to fill the container
# so clicking anywhere on the card triggers the correct button.
_overlay_css = """<style>
[data-testid="stMainBlockContainer"]
  [data-testid="stVerticalBlock"]
  [data-testid="stVerticalBlock"]:has([data-testid="stBaseButton-tertiary"]) {
    position: relative;
}
[data-testid="stMainBlockContainer"]
  [data-testid="stVerticalBlock"]
  [data-testid="stVerticalBlock"]
  > [data-testid="stElementContainer"]:has([data-testid="stBaseButton-tertiary"]) {
    position: absolute !important;
    inset: 0 !important;
    height: 100% !important;
    width: 100% !important;
    z-index: 2;
    margin: 0 !important;
    padding: 0 !important;
}
[data-testid="stMainBlockContainer"]
  [data-testid="stElementContainer"]:has([data-testid="stBaseButton-tertiary"])
  [data-testid="stButton"] {
    position: absolute !important;
    inset: 0 !important;
    height: 100% !important;
    width: 100% !important;
    margin: 0 !important;
}
[data-testid="stMainBlockContainer"] [data-testid="stBaseButton-tertiary"] {
    opacity: 0 !important;
    position: absolute !important;
    inset: 0 !important;
    width: 100% !important;
    height: 100% !important;
    min-height: 0 !important;
    padding: 0 !important;
    margin: 0 !important;
    cursor: pointer !important;
}
</style>"""
st.markdown(_overlay_css, unsafe_allow_html=True)

# Footer
st.caption(
    "Need help? Click on any task card above to navigate to the configuration page. "
    "You can complete tasks in any order, though we recommend following the "
    "suggested sequence for the smoothest experience."
)
