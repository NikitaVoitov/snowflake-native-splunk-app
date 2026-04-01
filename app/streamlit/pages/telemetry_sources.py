# Target: Streamlit 1.52.2 on Snowflake Warehouse Runtime
from __future__ import annotations

import contextlib
from datetime import datetime

import pandas as pd
from snowflake.snowpark.exceptions import SnowparkSQLException
from utils.config import load_config_like, save_config, save_config_batch
from utils.snowflake import get_session
from utils.source_discovery import (
    CATEGORIES,
    CategoryDef,
    DiscoveredSource,
    discover_all_sources,
    get_source_defaults,
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
_DISCOVERY_RUNNING_KEY = "ts_discovery_running"
_DISCOVERY_TIMESTAMP_KEY = "ts_last_discovered"
_DISCOVERY_DONE_KEY = "ts_discovery_done_once"
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
    div[data-testid="stColumn"]:first-child {
    flex: 0 0 auto !important;
    width: auto !important;
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
if _DISCOVERY_RUNNING_KEY not in st.session_state:
    st.session_state[_DISCOVERY_RUNNING_KEY] = False
if _DISCOVERY_TIMESTAMP_KEY not in st.session_state:
    st.session_state[_DISCOVERY_TIMESTAMP_KEY] = None
if _DISCOVERY_DONE_KEY not in st.session_state:
    st.session_state[_DISCOVERY_DONE_KEY] = False
if _JUST_SAVED_KEY not in st.session_state:
    st.session_state[_JUST_SAVED_KEY] = False
if _POST_SAVE_RELOAD_KEY not in st.session_state:
    st.session_state[_POST_SAVE_RELOAD_KEY] = False

for category in CATEGORIES:
    if _ss_pack_key(category.key) not in st.session_state:
        # Streamlit removes widget keys when navigating away from the page.
        # Restore from the saved-state snapshot so the toggle reflects
        # what was last persisted (or loaded from DB), not a hard False.
        _saved = st.session_state.get(_SAVED_STATE_KEY, {})
        st.session_state[_ss_pack_key(category.key)] = (
            _saved.get("packs", {}).get(category.key, False)
        )
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


def _start_discovery() -> None:
    st.session_state[_DISCOVERY_RUNNING_KEY] = True


def _render_info_bar() -> None:
    """Render the info bar with separate icon, text, and 'Discover sources' button."""
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


def _run_discovery(session) -> dict[str, list[DiscoveredSource]] | None:
    """Execute discovery and cache results in session state.

    Auto-runs on the very first visit to the page.  Subsequent runs require an
    explicit click on the "Discover sources" button.
    """
    is_running = st.session_state.get(_DISCOVERY_RUNNING_KEY, False)
    has_run_before = st.session_state.get(_DISCOVERY_DONE_KEY, False)
    has_cache = (
        _DISCOVERY_KEY in st.session_state
        and st.session_state[_DISCOVERY_KEY] is not None
    )

    if has_cache and not is_running:
        return st.session_state[_DISCOVERY_KEY]

    should_run = is_running or not has_run_before
    if not should_run:
        return st.session_state.get(_DISCOVERY_KEY)

    if session is None:
        st.session_state[_DISCOVERY_ERROR_KEY] = "Snowflake session unavailable."
        st.session_state[_DISCOVERY_KEY] = None
        st.session_state[_DISCOVERY_RUNNING_KEY] = False
        return None

    try:
        grouped = discover_all_sources(session)
        st.session_state[_DISCOVERY_KEY] = grouped
        st.session_state[_DISCOVERY_ERROR_KEY] = None
        st.session_state[_DISCOVERY_DONE_KEY] = True
        st.session_state[_DISCOVERY_RUNNING_KEY] = False
        st.session_state[_DISCOVERY_TIMESTAMP_KEY] = datetime.now()
        st.session_state.pop(_DISCOVERY_SIGNATURE_KEY, None)
        return grouped
    except SnowparkSQLException as exc:
        st.session_state[_DISCOVERY_ERROR_KEY] = (
            "Please grant IMPORTED PRIVILEGES ON SNOWFLAKE DB "
            f"to the application to enable source discovery. Details: {exc!s}"
        )
        st.session_state[_DISCOVERY_KEY] = None
        st.session_state[_DISCOVERY_RUNNING_KEY] = False
        return None


_ALL_DF_COLUMNS = [
    "fqn", "poll", "view_name", "interval_seconds",
    "overlap_minutes", "telemetry_types", "telemetry_sources",
]


def _build_category_df(
    sources: list[DiscoveredSource],
    poll_values: list[bool],
    category: CategoryDef,  # noqa: ARG001 — reserved for future per-category logic
) -> pd.DataFrame:
    rows = []
    for source, poll in zip(sources, poll_values, strict=False):
        defaults = get_source_defaults(source)
        rows.append(
            {
                "fqn": source.fqn,
                "poll": poll,
                "view_name": source.view_name,
                "interval_seconds": defaults["interval_seconds"],
                "overlap_minutes": defaults["overlap_minutes"],
                "telemetry_types": source.telemetry_types,
                "telemetry_sources": source.telemetry_sources,
            }
        )

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=_ALL_DF_COLUMNS,
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
        # Verify saved-state snapshot exists (first visit may have stale
        # signature from a prior discovery without a DB load yet).
        if _SAVED_STATE_KEY in st.session_state:
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
    slug_to_interval: dict[str, int] = {}
    slug_to_overlap: dict[str, int] = {}
    for key, value in source_config.items():
        if key.endswith(".view_fqn"):
            slug = key[len("source.") : -len(".view_fqn")]
            slug_to_fqn[slug] = value.strip()
        elif key.endswith(".poll"):
            slug = key[len("source.") : -len(".poll")]
            slug_to_poll[slug] = value.strip().lower() == "true"
        elif key.endswith(".poll_interval_seconds"):
            slug = key[len("source.") : -len(".poll_interval_seconds")]
            with contextlib.suppress(ValueError, TypeError):
                slug_to_interval[slug] = int(value.strip())
        elif key.endswith(".overlap_minutes"):
            slug = key[len("source.") : -len(".overlap_minutes")]
            with contextlib.suppress(ValueError, TypeError):
                slug_to_overlap[slug] = int(value.strip())

    saved_source_polls = {
        fqn: slug_to_poll[slug]
        for slug, fqn in slug_to_fqn.items()
        if slug in slug_to_poll
    }
    saved_intervals: dict[str, int] = {
        fqn: slug_to_interval[slug]
        for slug, fqn in slug_to_fqn.items()
        if slug in slug_to_interval
    }
    saved_overlaps: dict[str, int] = {
        fqn: slug_to_overlap[slug]
        for slug, fqn in slug_to_fqn.items()
        if slug in slug_to_overlap
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
        df = _build_category_df(
            grouped.get(category.key, []),
            poll_values,
            category,
        )
        for idx, source in enumerate(grouped.get(category.key, [])):
            if idx >= len(df):
                break
            if source.fqn in saved_intervals and "interval_seconds" in df.columns:
                df.at[idx, "interval_seconds"] = saved_intervals[source.fqn]
            if source.fqn in saved_overlaps and "overlap_minutes" in df.columns:
                df.at[idx, "overlap_minutes"] = saved_overlaps[source.fqn]
        st.session_state[_ss_df_key(category.key)] = df
        _reset_editor_widget(category.key)

    st.session_state[_SAVED_STATE_KEY] = _capture_current_state(grouped)
    st.session_state[_DISCOVERY_SIGNATURE_KEY] = signature
    if st.session_state.get(_POST_SAVE_RELOAD_KEY):
        st.session_state[_POST_SAVE_RELOAD_KEY] = False
    else:
        st.session_state[_JUST_SAVED_KEY] = False


def _effective_values(df: pd.DataFrame, editor_key: str, column: str) -> pd.Series:
    """Overlay editor edits for *column* onto the base DataFrame."""
    if column not in df.columns or df.empty:
        return pd.Series(dtype=object)

    values = df[column].copy()
    edits = st.session_state.get(editor_key)
    if edits and isinstance(edits, dict):
        for row_idx, changes in edits.get("edited_rows", {}).items():
            if column not in changes:
                continue
            idx = int(row_idx)
            if 0 <= idx < len(values):
                values.iloc[idx] = changes[column]
    return values


def _effective_polls(df: pd.DataFrame, editor_key: str) -> pd.Series:
    """Overlay editor edits onto the base poll column."""
    series = _effective_values(df, editor_key, "poll")
    return series.astype(bool) if not series.empty else pd.Series(dtype=bool)


def _capture_current_state(
    grouped: dict[str, list[DiscoveredSource]],
) -> dict[str, object]:
    """Capture the current pack and per-source control values."""
    pack_state: dict[str, bool] = {}
    source_state: dict[str, dict[str, object]] = {}

    for category in CATEGORIES:
        pack_state[category.key] = bool(st.session_state.get(_ss_pack_key(category.key), False))
        df: pd.DataFrame = st.session_state.get(
            _ss_df_key(category.key),
            _build_category_df([], [], category),
        )
        editor_key = _editor_key(category.key)
        polls = _effective_polls(df, editor_key)
        intervals = _effective_values(df, editor_key, "interval_seconds")
        overlaps = _effective_values(df, editor_key, "overlap_minutes")
        if "fqn" not in df.columns:
            continue
        for i, fqn in enumerate(df["fqn"]):
            entry: dict[str, object] = {"poll": bool(polls.iloc[i])}
            if not intervals.empty:
                entry["interval_seconds"] = int(intervals.iloc[i])
            if not overlaps.empty and overlaps.iloc[i] is not None and pd.notna(overlaps.iloc[i]):
                entry["overlap_minutes"] = int(overlaps.iloc[i])
            source_state[str(fqn)] = entry

        for source in grouped.get(category.key, []):
            source_state.setdefault(source.fqn, {"poll": False})

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
    for col in ("interval_seconds", "overlap_minutes"):
        if col in df.columns:
            df[col] = _effective_values(df, editor_key, col)
    st.session_state[df_key] = df

    _reset_editor_widget(cat_key)
    _mark_unsaved_changes()


def _reset_to_defaults(
    grouped: dict[str, list[DiscoveredSource]] | None = None,
) -> None:
    """Reset all controls to default UI values (unsaved until persisted)."""
    for category in CATEGORIES:
        st.session_state[_ss_pack_key(category.key)] = False
        df_key = _ss_df_key(category.key)
        df: pd.DataFrame = st.session_state[df_key].copy()
        if "poll" in df.columns:
            df["poll"] = False

        sources = (grouped or {}).get(category.key, [])
        for idx, source in enumerate(sources):
            if idx >= len(df):
                break
            defaults = get_source_defaults(source)
            if "interval_seconds" in df.columns:
                df.at[idx, "interval_seconds"] = defaults["interval_seconds"]
            if "overlap_minutes" in df.columns:
                df.at[idx, "overlap_minutes"] = defaults["overlap_minutes"]

        st.session_state[df_key] = df
        _reset_editor_widget(category.key)
    _mark_unsaved_changes()


def _save_current_configuration(
    session,
    current_state: dict[str, object],
) -> None:
    """Persist pack and per-source state to _internal.config (single SQL)."""
    pairs: dict[str, str] = {}
    for cat_key, enabled in current_state["packs"].items():
        pairs[f"pack_enabled.{cat_key}"] = "true" if enabled else "false"

    for fqn, entry in current_state["sources"].items():
        slug = source_slug(fqn)
        pairs[f"source.{slug}.view_fqn"] = fqn
        pairs[f"source.{slug}.poll"] = "true" if entry.get("poll") else "false"
        if "interval_seconds" in entry:
            pairs[f"source.{slug}.poll_interval_seconds"] = str(entry["interval_seconds"])
        if "overlap_minutes" in entry:
            pairs[f"source.{slug}.overlap_minutes"] = str(entry["overlap_minutes"])

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
    columns = ["poll", "view_name", "interval_seconds"]
    if cat.source_family == "account_usage":
        columns.append("overlap_minutes")
    elif cat.source_family == "event_table":
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
            "interval_seconds": st.column_config.NumberColumn(
                "Interval (s)",
                min_value=60,
                max_value=86400,
                step=60,
                help="Polling interval in seconds (min: 60, max: 86400)",
            ),
        }
        if "overlap_minutes" in display_cols:
            column_config["overlap_minutes"] = st.column_config.NumberColumn(
                "Overlap (min)",
                min_value=1,
                max_value=1440,
                step=1,
                help="Overlap window in minutes for watermark dedup (min: 1, max: 1440)",
            )
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

        editable_cols = {"poll", "interval_seconds", "overlap_minutes"}
        disabled_cols: list[str] | bool = True if not enabled else [
            column for column in display_cols if column not in editable_cols
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
        st.button(
            "Reset to defaults",
            type="secondary",
            on_click=_reset_to_defaults,
            args=(grouped,),
        )
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
                save_config(session, "pack_enabled.dummy", "false")
                st.session_state[_SAVED_STATE_KEY] = current_state
                st.session_state[_JUST_SAVED_KEY] = True
                st.session_state[_POST_SAVE_RELOAD_KEY] = True
                st.session_state[_DISCOVERY_SIGNATURE_KEY] = None
                st.session_state.drilled_from_getting_started = False
                st.toast("Configuration saved successfully.")
                # Full page rerun (not fragment-scoped) is intentional:
                # discovery signature was cleared so the outer page must
                # reload saved state from _internal.config.
                st.rerun()
            except SnowparkSQLException as exc:
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

if not st.session_state.get(_DISCOVERY_DONE_KEY) and not st.session_state.get(
    _DISCOVERY_RUNNING_KEY,
):
    st.session_state[_DISCOVERY_RUNNING_KEY] = True

_render_info_bar()

session = get_session()
_discovery_was_running = st.session_state.get(_DISCOVERY_RUNNING_KEY, False)
grouped = _run_discovery(session)

if _discovery_was_running and grouped is not None:
    st.rerun()

if st.session_state.get(_DISCOVERY_ERROR_KEY):
    st.error(st.session_state[_DISCOVERY_ERROR_KEY])
elif grouped is not None:
    _load_saved_controls(session, grouped)
    _interactive_content(session, grouped)
