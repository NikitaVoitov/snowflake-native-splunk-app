# Target: Streamlit 1.52.2 on Snowflake Warehouse Runtime
from __future__ import annotations

import pandas as pd
from snowflake.snowpark.exceptions import SnowparkSQLException
from utils.config import load_config_like, save_config_batch
from utils.snowflake import get_session
from utils.source_discovery import (
    CATEGORIES,
    CategoryDef,
    DiscoveredSource,
    discover_all_sources,
    resolve_saved_poll_states,
    source_slug,
)

import streamlit as st

# ---------------------------------------------------------------------------
# Session-state keys
# ---------------------------------------------------------------------------
_DISCOVERY_KEY = "ts_discovered_sources"
_DISCOVERY_ERROR_KEY = "ts_discovery_error"
_DISCOVERY_SIGNATURE_KEY = "ts_discovery_signature"
_DISCOVERY_VISIT_KEY = "ts_discovery_visit"
_SAVED_STATE_KEY = "ts_saved_state"
_JUST_SAVED_KEY = "ts_just_saved"
_POST_SAVE_RELOAD_KEY = "ts_post_save_reload"

_PAGE_CSS = """
<style>
div[data-testid="stColumn"]:has(div[data-testid="stCheckbox"])
    > div[data-testid="stVerticalBlock"] {
    width: fit-content !important;
    margin-left: auto !important;
}

div[data-testid="stColumn"] button[kind="tertiary"] {
    padding: 0 !important;
    min-height: 0 !important;
    line-height: 1 !important;
}

div[data-testid="stColumn"] div[data-testid="stButton"]:has(button[kind="tertiary"]),
div[data-testid="stColumn"] div[data-testid="stElementContainer"]:has(button[kind="tertiary"]) {
    display: flex !important;
    align-items: center !important;
}

div[data-testid="stLayoutWrapper"]
    > div[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .category-tile-marker) {
    transition: border-color 0.15s ease, background-color 0.15s ease;
}

div[data-testid="stLayoutWrapper"]
    > div[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .category-tile-marker):hover {
    border-color: #4c78db !important;
    background-color: rgba(76, 120, 219, 0.04) !important;
}

div[data-testid="stElementContainer"]:has(.category-tile-marker) {
    display: none !important;
}

div[data-testid="stElementContainer"]:has(.disabled-editor-marker) {
    display: none !important;
}

div[data-testid="stElementContainer"]:has(.disabled-editor-marker)
    + div[data-testid="stElementContainer"] {
    opacity: 0.4 !important;
    pointer-events: none !important;
}

div[data-testid="stElementContainer"]:has(.footer-controls-marker) {
    display: none !important;
}
div[data-testid="stElementContainer"]:has(.footer-controls-marker)
    + div[data-testid="stLayoutWrapper"] div[data-testid="stHorizontalBlock"] {
    gap: 0.5rem !important;
    align-items: stretch !important;
}
div[data-testid="stElementContainer"]:has(.footer-controls-marker)
    + div[data-testid="stLayoutWrapper"] div[data-testid="stHorizontalBlock"]
    > div[data-testid="stColumn"]:first-child {
    flex: 1 1 0% !important;
}
div[data-testid="stElementContainer"]:has(.footer-controls-marker)
    + div[data-testid="stLayoutWrapper"] div[data-testid="stHorizontalBlock"]
    > div[data-testid="stColumn"]:not(:first-child) {
    flex: 0 0 auto !important;
    width: auto !important;
}

</style>
"""


def _ss_pack_key(cat_key: str) -> str:
    return f"pack_enabled.{cat_key}"


def _ss_df_key(cat_key: str) -> str:
    return f"sources_df.{cat_key}"


def _ss_expanded_key(cat_key: str) -> str:
    return f"category_expanded.{cat_key}"


def _ss_editor_version_key(cat_key: str) -> str:
    return f"sources_editor_version.{cat_key}"


def _editor_key(cat_key: str) -> str:
    version = st.session_state.get(_ss_editor_version_key(cat_key), 0)
    return f"sources_editor_{cat_key}_{version}"


if _DISCOVERY_ERROR_KEY not in st.session_state:
    st.session_state[_DISCOVERY_ERROR_KEY] = None
if _JUST_SAVED_KEY not in st.session_state:
    st.session_state[_JUST_SAVED_KEY] = False
if _POST_SAVE_RELOAD_KEY not in st.session_state:
    st.session_state[_POST_SAVE_RELOAD_KEY] = False

for category in CATEGORIES:
    if _ss_pack_key(category.key) not in st.session_state:
        st.session_state[_ss_pack_key(category.key)] = False
    if _ss_expanded_key(category.key) not in st.session_state:
        st.session_state[_ss_expanded_key(category.key)] = False
    if _ss_editor_version_key(category.key) not in st.session_state:
        st.session_state[_ss_editor_version_key(category.key)] = 0


# ---------------------------------------------------------------------------
# Discovery and persisted-state helpers
# ---------------------------------------------------------------------------
def _source_signature(grouped: dict[str, list[DiscoveredSource]]) -> tuple[str, ...]:
    signature: list[str] = []
    for category in CATEGORIES:
        signature.extend(source.fqn for source in grouped.get(category.key, []))
    return tuple(signature)


def _run_discovery(session) -> dict[str, list[DiscoveredSource]] | None:
    """Execute discovery and cache results in session state."""
    current_visit = int(st.session_state.get("_nav_visit_seq", 0))
    if st.session_state.get(_DISCOVERY_VISIT_KEY) != current_visit:
        st.session_state.pop(_DISCOVERY_KEY, None)
        st.session_state.pop(_DISCOVERY_SIGNATURE_KEY, None)
        st.session_state[_DISCOVERY_VISIT_KEY] = current_visit

    if _DISCOVERY_KEY in st.session_state and st.session_state[_DISCOVERY_KEY] is not None:
        return st.session_state[_DISCOVERY_KEY]

    if session is None:
        st.session_state[_DISCOVERY_ERROR_KEY] = "Snowflake session unavailable."
        st.session_state[_DISCOVERY_KEY] = None
        return None

    try:
        with st.spinner("Discovering telemetry sources..."):
            grouped = discover_all_sources(session)
        st.session_state[_DISCOVERY_KEY] = grouped
        st.session_state[_DISCOVERY_ERROR_KEY] = None
        return grouped
    except SnowparkSQLException as exc:
        st.session_state[_DISCOVERY_ERROR_KEY] = (
            "Please grant IMPORTED PRIVILEGES ON SNOWFLAKE DB "
            f"to the application to enable source discovery. Details: {exc!s}"
        )
        st.session_state[_DISCOVERY_KEY] = None
        return None


def _build_category_df(
    sources: list[DiscoveredSource],
    poll_values: list[bool],
) -> pd.DataFrame:
    rows = []
    for source, poll in zip(sources, poll_values, strict=False):
        rows.append(
            {
                "fqn": source.fqn,
                "poll": poll,
                "view_name": source.view_name,
                "telemetry_types": source.telemetry_types,
                "telemetry_sources": source.telemetry_sources,
            }
        )

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["fqn", "poll", "view_name", "telemetry_types", "telemetry_sources"]
    )


def _mark_unsaved_changes() -> None:
    st.session_state[_JUST_SAVED_KEY] = False


def _reset_editor_widget(cat_key: str) -> None:
    prefix = f"sources_editor_{cat_key}_"
    for key in list(st.session_state):
        if key.startswith(prefix):
            del st.session_state[key]
    st.session_state[_ss_editor_version_key(cat_key)] = (
        int(st.session_state.get(_ss_editor_version_key(cat_key), 0)) + 1
    )


def _load_saved_controls(
    session,
    grouped: dict[str, list[DiscoveredSource]],
) -> None:
    """Load persisted pack/source state into session state."""
    signature = _source_signature(grouped)
    if st.session_state.get(_DISCOVERY_SIGNATURE_KEY) == signature:
        return

    pack_config: dict[str, str] = {}
    source_config: dict[str, str] = {}
    if session is not None:
        try:
            pack_config = load_config_like(session, "pack_enabled.")
            source_config = load_config_like(session, "source.")
        except SnowparkSQLException as exc:
            st.session_state[_DISCOVERY_ERROR_KEY] = (
                "Could not load saved telemetry source configuration. "
                f"Details: {exc!s}"
            )

    slug_to_fqn: dict[str, str] = {}
    slug_to_poll: dict[str, bool] = {}
    for key, value in source_config.items():
        if key.endswith(".view_fqn"):
            slug = key[len("source.") : -len(".view_fqn")]
            slug_to_fqn[slug] = value.strip()
        elif key.endswith(".poll"):
            slug = key[len("source.") : -len(".poll")]
            slug_to_poll[slug] = value.strip().lower() == "true"

    saved_source_polls = {
        fqn: slug_to_poll[slug]
        for slug, fqn in slug_to_fqn.items()
        if slug in slug_to_poll
    }

    for category in CATEGORIES:
        pack_enabled = (
            pack_config.get(_ss_pack_key(category.key), "false").strip().lower() == "true"
        )
        st.session_state[_ss_pack_key(category.key)] = pack_enabled

        poll_values = resolve_saved_poll_states(
            grouped.get(category.key, []),
            saved_source_polls,
        )
        st.session_state[_ss_df_key(category.key)] = _build_category_df(
            grouped.get(category.key, []),
            poll_values,
        )
        _reset_editor_widget(category.key)

    st.session_state[_SAVED_STATE_KEY] = _capture_current_state(grouped)
    st.session_state[_DISCOVERY_SIGNATURE_KEY] = signature
    if st.session_state.get(_POST_SAVE_RELOAD_KEY):
        st.session_state[_POST_SAVE_RELOAD_KEY] = False
    else:
        st.session_state[_JUST_SAVED_KEY] = False


def _effective_polls(df: pd.DataFrame, editor_key: str) -> pd.Series:
    """Overlay editor edits onto the base poll column."""
    if "poll" not in df.columns or df.empty:
        return pd.Series(dtype=bool)

    polls = df["poll"].copy()
    edits = st.session_state.get(editor_key)
    if edits and isinstance(edits, dict):
        for row_idx, changes in edits.get("edited_rows", {}).items():
            if "poll" not in changes:
                continue
            idx = int(row_idx)
            if 0 <= idx < len(polls):
                polls.iloc[idx] = bool(changes["poll"])
    return polls


def _capture_current_state(
    grouped: dict[str, list[DiscoveredSource]],
) -> dict[str, dict[str, bool]]:
    """Capture the current pack and per-source poll values."""
    pack_state: dict[str, bool] = {}
    source_state: dict[str, bool] = {}

    for category in CATEGORIES:
        pack_state[category.key] = bool(st.session_state.get(_ss_pack_key(category.key), False))
        df: pd.DataFrame = st.session_state.get(
            _ss_df_key(category.key),
            _build_category_df([], []),
        )
        polls = _effective_polls(df, _editor_key(category.key))
        if "fqn" not in df.columns:
            continue
        for fqn, poll in zip(df["fqn"], polls, strict=False):
            source_state[str(fqn)] = bool(poll)

        # Ensure newly discovered sources with no editor state are still tracked.
        for source in grouped.get(category.key, []):
            source_state.setdefault(source.fqn, False)

    return {"packs": pack_state, "sources": source_state}


def _apply_pack_state(cat_key: str, _enabled: bool) -> None:
    """Bake in-flight editor edits into the base DataFrame on toggle change.

    The category toggle and individual poll checkboxes are decoupled: toggling
    a category ON/OFF never changes the poll values.  This function consolidates
    any pending editor edits into the base DataFrame before resetting the
    editor widget so the visual checkbox state is preserved.
    """
    df_key = _ss_df_key(cat_key)
    editor_key = _editor_key(cat_key)
    df: pd.DataFrame = st.session_state[df_key].copy()
    if "poll" in df.columns:
        df["poll"] = _effective_polls(df, editor_key)
    st.session_state[df_key] = df

    _reset_editor_widget(cat_key)
    _mark_unsaved_changes()


def _reset_to_defaults() -> None:
    """Reset all controls to default UI values (unsaved until persisted)."""
    for category in CATEGORIES:
        st.session_state[_ss_pack_key(category.key)] = False
        df_key = _ss_df_key(category.key)
        df: pd.DataFrame = st.session_state[df_key].copy()
        if "poll" in df.columns:
            df["poll"] = False
        st.session_state[df_key] = df
        _reset_editor_widget(category.key)
    _mark_unsaved_changes()


def _save_current_configuration(
    session,
    current_state: dict[str, dict[str, bool]],
) -> None:
    """Persist pack and per-source poll state to _internal.config (single SQL)."""
    pairs: dict[str, str] = {}
    for cat_key, enabled in current_state["packs"].items():
        pairs[f"pack_enabled.{cat_key}"] = "true" if enabled else "false"

    for fqn, poll in current_state["sources"].items():
        slug = source_slug(fqn)
        pairs[f"source.{slug}.view_fqn"] = fqn
        pairs[f"source.{slug}.poll"] = "true" if poll else "false"

    pairs["pack_enabled.dummy"] = "false"
    save_config_batch(session, pairs)


# ---------------------------------------------------------------------------
# Category rendering
# ---------------------------------------------------------------------------
def _toggle_expand(cat_key: str) -> None:
    st.session_state[_ss_expanded_key(cat_key)] = not st.session_state.get(
        _ss_expanded_key(cat_key),
        False,
    )


def _on_pack_toggle_change(cat_key: str) -> None:
    enabled = bool(st.session_state.get(_ss_pack_key(cat_key), False))
    _apply_pack_state(cat_key, enabled)


def _on_editor_change() -> None:
    _mark_unsaved_changes()


def _dot_color(enabled: bool, effective: int, total: int) -> str:
    if not enabled:
        return "#9e9e9e"
    if total > 0 and effective == total:
        return "#22c55e"
    if effective > 0:
        return "#f59e0b"
    return "#9e9e9e"


def _display_columns(df: pd.DataFrame, cat: CategoryDef) -> list[str]:
    columns = ["poll", "view_name"]
    if cat.source_family == "event_table":
        if "telemetry_types" in df.columns and df["telemetry_types"].astype(str).str.strip().ne("").any():
            columns.append("telemetry_types")
        if "telemetry_sources" in df.columns and df["telemetry_sources"].astype(str).str.strip().ne("").any():
            columns.append("telemetry_sources")
    return columns


def _render_unchecked_row_dimmer(cat_key: str) -> None:
    """Dim unchecked rows in glide-data-grid via inline JS overlays.

    Streamlit's data editor renders a canvas, so row styling cannot be expressed
    with DataFrame/column config alone. This script reads the accessible grid
    table kept alongside the canvas and overlays translucent rectangles over
    rows whose Poll cell currently resolves to ``false``.
    """
    st.html(
        f"""
<div data-row-dimmer="{cat_key}" style="display:none"></div>
<script>
(() => {{
  const marker = document.querySelector('div[data-row-dimmer="{cat_key}"]');
  const scriptContainer = marker?.closest('div[data-testid="stElementContainer"]');
  const dataEditorContainer = scriptContainer?.previousElementSibling;
  const dataFrame = dataEditorContainer?.querySelector('div[data-testid="stDataFrame"]');
  const grid = dataFrame?.querySelector('.stDataFrameGlideDataEditor');
  const underlay = grid?.querySelector('.dvn-underlay');
  const scroller = grid?.querySelector('.dvn-scroller');
  const heightProbe = grid?.querySelector('.dvn-stack > div:last-child');
  if (!marker || !dataFrame || !grid || !underlay || !scroller || !heightProbe) {{
    return;
  }}

  underlay.style.position = 'relative';

  let overlay = grid.querySelector('.unchecked-row-overlay');
  if (!overlay) {{
    overlay = document.createElement('div');
    overlay.className = 'unchecked-row-overlay';
    overlay.style.position = 'absolute';
    overlay.style.inset = '0';
    overlay.style.pointerEvents = 'none';
    overlay.style.zIndex = '3';
    underlay.appendChild(overlay);
  }}

  const render = () => {{
    const bodyRows = Array.from(grid.querySelectorAll('tbody tr[role="row"]'));
    if (bodyRows.length === 0) {{
      overlay.innerHTML = '';
      return;
    }}
    const totalHeight = parseFloat(heightProbe.style.height || '0');
    const rowHeight = totalHeight > 0 ? totalHeight / (bodyRows.length + 1) : 35;
    const headerHeight = rowHeight;
    const scrollTop = scroller.scrollTop || 0;
    const viewportHeight = scroller.clientHeight || 0;
    const viewportWidth = scroller.clientWidth || dataFrame.clientWidth || 0;

    overlay.innerHTML = '';
    overlay.style.width = `${{viewportWidth}}px`;
    overlay.style.height = `${{viewportHeight}}px`;

    bodyRows.forEach((row, idx) => {{
      const pollCell = row.querySelector('td[data-testid^="glide-cell-0-"]');
      if (!pollCell || pollCell.textContent.trim() !== 'false') {{
        return;
      }}

      const top = headerHeight + (idx * rowHeight) - scrollTop;
      if (top + rowHeight <= headerHeight || top >= viewportHeight) {{
        return;
      }}

      const shade = document.createElement('div');
      shade.style.position = 'absolute';
      shade.style.left = '0';
      shade.style.top = `${{top}}px`;
      shade.style.width = `${{viewportWidth}}px`;
      shade.style.height = `${{rowHeight}}px`;
      shade.style.background = 'rgba(255, 255, 255, 0.58)';
      shade.style.borderTop = '1px solid rgba(30, 37, 47, 0.08)';
      shade.style.borderBottom = '1px solid rgba(30, 37, 47, 0.08)';
      overlay.appendChild(shade);
    }});
  }};

  if (!grid.dataset.rowDimmerBound) {{
    scroller.addEventListener('scroll', render, {{ passive: true }});
    new MutationObserver(render).observe(grid, {{
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
    }});
    grid.dataset.rowDimmerBound = 'true';
  }}

  requestAnimationFrame(render);
}})();
</script>
""",
    )


def _render_category(cat: CategoryDef) -> None:
    df_key = _ss_df_key(cat.key)
    editor_key = _editor_key(cat.key)
    pack_key = _ss_pack_key(cat.key)
    expanded = st.session_state.get(_ss_expanded_key(cat.key), False)
    enabled = bool(st.session_state.get(pack_key, False))

    df: pd.DataFrame = st.session_state[df_key]

    total = len(df)
    poll_count = int(_effective_polls(df, editor_key).sum()) if enabled else 0
    color = _dot_color(enabled, poll_count, total)

    with st.container(border=True):
        st.markdown(
            '<span class="category-tile-marker"></span>',
            unsafe_allow_html=True,
        )
        col_chevron, col_title, col_toggle = st.columns(
            [0.35, 7.65, 2],
            gap="small",
            vertical_alignment="center",
        )

        with col_toggle:
            st.toggle(
                "Enabled" if enabled else "Disabled",
                key=pack_key,
                on_change=_on_pack_toggle_change,
                args=(cat.key,),
            )

        with col_chevron:
            st.button(
                "",
                key=f"expand_{cat.key}",
                icon=":material/expand_more:" if expanded else ":material/chevron_right:",
                type="tertiary",
                on_click=_toggle_expand,
                args=(cat.key,),
            )

        with col_title:
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:0.5rem;'
                f'white-space:nowrap;height:20px;line-height:1;">'
                f'<span style="display:inline-block;width:12px;height:12px;'
                f"border-radius:50%;background:{color};"
                f'flex-shrink:0;"></span>'
                f"<strong>{cat.name}</strong>"
                f"&nbsp;&nbsp;({poll_count}/{total})"
                f"</div>",
                unsafe_allow_html=True,
            )

    if not expanded:
        return

    _, body_col = st.columns([0.2, 9.8], gap="small")
    with body_col:
        st.caption(cat.description)

        if total == 0:
            st.info("No sources discovered for this category.")
            return

        display_cols = _display_columns(df, cat)
        column_config: dict[str, object] = {
            "poll": st.column_config.CheckboxColumn(
                "Poll",
                default=False,
                width=50,
                pinned=True,
            ),
            "view_name": st.column_config.TextColumn("View name"),
        }
        if "telemetry_types" in display_cols:
            column_config["telemetry_types"] = st.column_config.TextColumn(
                "Telemetry types",
                width="medium",
            )
        if "telemetry_sources" in display_cols:
            column_config["telemetry_sources"] = st.column_config.TextColumn(
                "Telemetry sources",
                width="medium",
            )

        disabled_cols: list[str] | bool = True if not enabled else [
            column for column in display_cols if column != "poll"
        ]

        if not enabled:
            st.markdown(
                '<span class="disabled-editor-marker"></span>',
                unsafe_allow_html=True,
            )

        st.data_editor(
            df[display_cols],
            column_config=column_config,
            column_order=display_cols,
            disabled=disabled_cols,
            hide_index=True,
            use_container_width=True,
            key=editor_key,
            on_change=_on_editor_change,
        )

        if enabled:
            _render_unchecked_row_dimmer(cat.key)


def _render_footer(
    grouped: dict[str, list[DiscoveredSource]],
    session,
) -> None:
    current_state = _capture_current_state(grouped)
    saved_state = st.session_state.get(_SAVED_STATE_KEY, {"packs": {}, "sources": {}})
    just_saved = st.session_state.get(_JUST_SAVED_KEY, False)
    has_unsaved = (current_state != saved_state) and not just_saved
    save_disabled = not has_unsaved or just_saved

    st.divider()
    st.markdown('<span class="footer-controls-marker"></span>', unsafe_allow_html=True)
    fc_msg, fc2, fc3 = st.columns([3, 2, 2], gap="small")
    with fc_msg:
        if just_saved:
            st.caption("Configuration saved successfully.")
        elif has_unsaved:
            st.caption("You have unsaved changes.")
    with fc2:
        st.button("Reset to defaults", type="secondary", on_click=_reset_to_defaults)
    with fc3:
        save_clicked = st.button(
            "Saved" if just_saved else "Save configuration",
            type="primary",
            disabled=save_disabled,
        )

    if save_clicked:
        if session is None:
            st.error("Snowflake session unavailable. Cannot save configuration.")
        else:
            try:
                _save_current_configuration(session, current_state)
                st.session_state[_SAVED_STATE_KEY] = current_state
                st.session_state[_JUST_SAVED_KEY] = True
                st.session_state[_POST_SAVE_RELOAD_KEY] = True
                st.session_state[_DISCOVERY_SIGNATURE_KEY] = None
                st.session_state.drilled_from_getting_started = False
                st.toast("Configuration saved successfully.")
                st.rerun()
            except Exception as exc:
                st.error(f"Failed to save configuration: {exc!s}")


# ---------------------------------------------------------------------------
# Interactive fragment — widget reruns stay inside; static chrome is stable
# ---------------------------------------------------------------------------
@st.fragment
def _interactive_content(session, grouped):
    total_sources = sum(len(values) for values in grouped.values())
    if total_sources == 0:
        st.warning(
            "No telemetry sources found. Ensure the app has the required "
            "Snowflake privileges (IMPORTED PRIVILEGES ON SNOWFLAKE DB)."
        )
    else:
        for category in CATEGORIES:
            _render_category(category)

    _render_footer(grouped, session)


# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------
st.markdown(_PAGE_CSS, unsafe_allow_html=True)

st.header("Telemetry Sources")
st.caption(
    "Configure monitoring packs and select data sources from Event Tables "
    "and ACCOUNT_USAGE views. Set polling intervals and batch sizes for each source."
)

st.info(
    "Enable categories and individual sources to start collecting telemetry. "
    "Custom views allow you to apply Snowflake masking and row-access policies "
    "to exported data."
)

session = get_session()
grouped = _run_discovery(session)

if st.session_state.get(_DISCOVERY_ERROR_KEY):
    st.error(st.session_state[_DISCOVERY_ERROR_KEY])
elif grouped is not None:
    _load_saved_controls(session, grouped)
    _interactive_content(session, grouped)
