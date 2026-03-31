# `st.fragment` Design — Splunk Observability Native App

**Date:** 2026-03-31
**Streamlit version:** 1.52.2 on Snowflake Warehouse Runtime
**Pages affected:** Telemetry Sources, Splunk Settings, Getting Started

---

## Problem Statement

Every widget interaction in Streamlit triggers a full top-to-bottom script rerun. On the Snowflake warehouse runtime, this causes all UI elements (navigation bar, page headings, info boxes, data editors, toggles) to grey out for 1-2 seconds while the script re-executes — including expensive SQL queries and Snowpark calls.

User-reported symptoms:
- Checking a checkbox in `st.data_editor` caused the entire page (nav bar, headings, other categories) to grey out.
- Enabling/disabling a category toggle greyed out unrelated UI sections.
- Clicking a navigation button on the Getting Started page caused unnecessary SQL re-execution before navigating away.

---

## Solution Architecture

### Core Pattern: Single `@st.fragment` Per Page

Each page follows the same structure:

```
┌──────────────────────────────────────────────┐
│  STATIC CHROME (outside fragment)            │
│  • st.markdown(_PAGE_CSS)                    │
│  • st.header("Page Title")                   │
│  • st.caption("Description")                 │
│  • st.info("Helpful info")                   │
│  • session = get_session()                   │
│  • data = expensive_query(session)           │
├──────────────────────────────────────────────┤
│  @st.fragment                                │
│  def _interactive_content(session, data):    │
│  ┌────────────────────────────────────────┐  │
│  │ Interactive widgets (toggles,          │  │
│  │ data editors, text inputs, buttons)    │  │
│  ├────────────────────────────────────────┤  │
│  │ Footer (Save, Reset, unsaved changes)  │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

**Key insight:** Only the fragment body re-executes on widget interaction. Static chrome and expensive data loading above the fragment remain untouched.

### Why Single Fragment (Not Per-Widget)

We evaluated two options:

| Approach | Pros | Cons |
|---|---|---|
| **Option A: Single fragment** (selected) | Simple state management; footer always reflects all changes; no cross-fragment sync needed | All interactive content reruns on any widget click |
| **Option B: Per-widget fragments** | Maximum isolation; only clicked widget reruns | Complex cross-fragment state sync; footer must poll all fragments; harder to maintain |

Option A was chosen because:
1. Widget reruns within the fragment are fast (no SQL, no data loading).
2. Tightly coupled widgets (e.g. category toggle + data editor, endpoint + certificate) share state naturally.
3. Footer (unsaved changes, save/reset) needs to reflect all widget state immediately — a single fragment makes this trivial.

---

## Per-Page Implementation

### 1. Telemetry Sources (`pages/telemetry_sources.py`)

**Static chrome (outside fragment):**
- `_PAGE_CSS` injection
- `st.header("Telemetry Sources")`
- `st.caption(...)` + `st.info(...)`
- `get_session()` + `_run_discovery(session)` — expensive ACCOUNT_USAGE SQL queries

**Fragment content:**
- Category loop: toggle, expand/collapse, `st.data_editor` per category
- Footer: divider, unsaved changes message, Reset to defaults, Save configuration

```python
@st.fragment
def _interactive_content(session, grouped):
    if total_sources == 0:
        st.warning("No telemetry sources found...")
    else:
        for category in CATEGORIES:
            _render_category(category)
    _render_footer(grouped, session)
```

**Fragment-specific CSS patterns:**

1. **Category tile hover** — uses a marker-based `:has()` with direct child combinator to prevent the fragment container from matching:

```css
/* Inject <span class="category-tile-marker"> inside each category tile */
div[data-testid="stLayoutWrapper"]
    > div[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .category-tile-marker):hover {
    border-color: #4c78db !important;
    background-color: rgba(76, 120, 219, 0.04) !important;
}
/* Hide the marker element itself */
div[data-testid="stElementContainer"]:has(.category-tile-marker) {
    display: none !important;
}
```

Without the `>` combinator, the fragment's outer `stVerticalBlock` also matches `:has(.category-tile-marker)` because the marker is a nested descendant.

2. **Disabled editor overlay** — sibling marker pattern:
```css
div[data-testid="stElementContainer"]:has(.disabled-editor-marker) {
    display: none !important;
}
div[data-testid="stElementContainer"]:has(.disabled-editor-marker)
    + div[data-testid="stElementContainer"] {
    opacity: 0.4 !important;
    pointer-events: none !important;
}
```

3. **Footer button layout** — sibling marker for `st.columns()`:
```css
div[data-testid="stElementContainer"]:has(.footer-controls-marker)
    + div[data-testid="stLayoutWrapper"] div[data-testid="stHorizontalBlock"] {
    gap: 0.5rem !important;
    align-items: stretch !important;
}
```

---

### 2. Splunk Settings (`pages/splunk_settings.py`)

**Static chrome (outside fragment):**
- `_PAGE_CSS` injection (fragment hover suppression)
- `_init_session_state()`
- `st.header("Splunk Settings")`
- `st.tabs(["Export settings"])`

**Fragment content:**
- OTLP endpoint card: text input, test/clear buttons, connection status
- Certificate card: text area, validation result
- Footer: divider, unsaved changes message, Reset to defaults, Save settings

```python
@st.fragment
def _interactive_content():
    st.subheader("OTLP Export")
    with st.container(border=True):
        # OTLP endpoint card...
    with st.container(border=True):
        # Certificate card...
    _render_footer()
```

**Fragment-specific CSS:**
```css
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    background-color: transparent !important;
}
```

The Splunk Settings page uses `stVerticalBlockBorderWrapper` (unlike Telemetry Sources which uses `stLayoutWrapper > stVerticalBlock`). This difference was discovered via Playwright DOM inspection.

---

### 3. Getting Started (`pages/getting_started.py`)

**Static chrome (outside fragment):**
- Onboarding state SQL queries: `load_task_completion_state(session)` — executes multiple queries against ACCOUNT_USAGE, config tables, etc.
- `st.header(...)` + `st.caption(...)`
- Progress bar section
- Footer caption

**Fragment content:**
- Task card loop: card HTML + navigation button per task
- `st.switch_page()` on button click (triggers full rerun — expected since it navigates away)

```python
@st.fragment
def _interactive_cards():
    for task in ONBOARDING_TASKS:
        done = completion.get(task.step, False)
        with st.container():
            _render_task_card(task.step, task.title, task.description, done)
            if not done and st.button(...):
                st.switch_page(task.page_path)
```

**Performance benefit:** Button clicks skip the expensive `load_task_completion_state()` SQL queries entirely. Navigation to other pages is nearly instant. The progress bar updates correctly on full page reload (when the user returns to Getting Started).

**Fragment-specific CSS:**
```css
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    background-color: transparent !important;
}
```

---

## Fragment Hover Highlight Problem

### Root Cause

`@st.fragment` wraps its content in a container element that may have a default hover highlight (light-blue background). This is a Streamlit framework behavior, not custom CSS.

### Manifestation by Page

| Page | Container type | Hover behavior |
|---|---|---|
| **Telemetry Sources** | `stLayoutWrapper > stVerticalBlock` | Custom `:has()` rule accidentally matched the fragment container when using `.category-tile-marker` without direct child combinator |
| **Splunk Settings** | `stVerticalBlockBorderWrapper` | Default hover highlight on the wrapper |
| **Getting Started** | `stVerticalBlockBorderWrapper` | Default hover highlight on the wrapper |

### Fixes Applied

1. **Telemetry Sources:** Changed `:has(.category-tile-marker)` to `:has(> [data-testid="stElementContainer"] .category-tile-marker)` to prevent ancestor matching.

2. **Splunk Settings / Getting Started:** Added generic suppression:
```css
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    background-color: transparent !important;
}
```

---

## SiS Bytecode Cache and Fragment Deployment

CSS changes embedded in Python files (e.g. `_PAGE_CSS` strings) are subject to Snowflake's aggressive bytecode caching. After modifying fragment CSS:

1. **First try:** `snow app run -c dev` — sufficient if only data or new files changed.
2. **If CSS is stale:** Full teardown cycle required:
   - Comment out `GRANT` statements in `scripts/shared_content.sql`
   - `snow app teardown --cascade --force -c dev`
   - `snow app run -c dev`
   - Restore `GRANT` statements
   - `snow app run -c dev`
   - Wait 15-20 seconds before testing

**Verification:** Use Playwright MCP to inspect `<style>` tags in the live DOM. Compare with source `_PAGE_CSS` to confirm the correct CSS is loaded.

---

## Known Limitations

1. **`st.rerun()` inside a fragment** triggers a full page rerun, not fragment-scoped. Use `on_click`/`on_change` callbacks to avoid explicit `st.rerun()` wherever possible.

2. **Nav bar flash on page navigation:** When navigating from Getting Started to Telemetry Sources, the nav bar briefly shows default Streamlit navigation for ~1 second while the target page initializes (heavy SQL queries). This is a Streamlit framework timing issue — the new page's `main.py` must complete before custom CSS and `st.navigation()` are applied.

3. **Stale layout after warehouse idle:** When the warehouse auto-suspends and the user returns, the Streamlit frontend briefly shows default navigation (alphabetical, no icons) until the Python backend completes its first rerun. Mitigated by setting warehouse `AUTO_SUSPEND` to 6 hours for development.

4. **Fragment DOM structure varies by page.** The wrapper element type (`stVerticalBlockBorderWrapper` vs `stLayoutWrapper > stVerticalBlock`) is not consistent across pages. Always verify with Playwright before writing CSS selectors.

---

## Design Decisions Log

| Decision | Rationale |
|---|---|
| Single fragment per page (not per-widget) | Simpler state management; footer always reflects all changes; no polling needed |
| Footer inside fragment | Must reflect unsaved changes immediately; avoids cross-fragment sync complexity |
| CSS markers for targeting (`category-tile-marker`, `disabled-editor-marker`, `footer-controls-marker`) | Stable anchor points for CSS sibling/descendant selectors; `st.markdown` HTML cannot wrap other Streamlit components |
| Direct child combinator in `:has()` | Prevents fragment container from matching CSS rules meant for nested elements |
| Fragment hover suppression CSS per page | Different pages use different wrapper elements; a single global rule would not cover all cases |
| Expensive SQL outside fragment | Ensures widget clicks never trigger SQL re-execution; data is loaded once at page level |

---

## Files Modified

| File | Change |
|---|---|
| `app/streamlit/pages/telemetry_sources.py` | Wrapped category loop + footer in `@st.fragment`; added CSS marker classes for hover, disabled editor, and footer layout |
| `app/streamlit/pages/splunk_settings.py` | Wrapped both cards + footer in `@st.fragment`; added hover suppression CSS |
| `app/streamlit/pages/getting_started.py` | Wrapped task card loop in `@st.fragment`; added hover suppression CSS |
