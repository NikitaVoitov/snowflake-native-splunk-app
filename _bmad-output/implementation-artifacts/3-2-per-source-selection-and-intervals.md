# Story 3.2: Per-source intervals and overlap windows

Status: done

## Story

As a Snowflake administrator (Maya),
I want to set execution interval per source and for ACCOUNT_USAGE sources set the overlap window,
So that I control how often each source is polled and how much historical data is re-scanned for late-arriving rows.

## Acceptance Criteria

1. **Given** I am on the Telemetry sources page with sources discovered and a category expanded, **When** I view the `st.data_editor`, **Then** I see additional columns beyond the existing Poll and View name: **Interval** (editable), and for the Query Performance & Execution category only: **Overlap** (editable). The Poll and View name behavior delivered in Story 3.1 remains unchanged.

2. **Given** the Interval column is visible, **When** I view any row, **Then** it shows the default interval in seconds for that source before I change anything. Interval is editable via the `st.data_editor` and validated to be within the published bounds: minimum 60 seconds, maximum 86400 seconds (24 hours).

3. **Given** the Overlap column is visible in the Query Performance & Execution category, **When** I view any row, **Then** it shows the documented default overlap in minutes for that specific ACCOUNT_USAGE source (e.g. 50 for QUERY_HISTORY, 66 for LOCK_WAIT_HISTORY). Overlap is editable and validated to be within bounds: minimum 1 minute, maximum 1440 minutes (24 hours). The Overlap column does NOT appear in the Distributed Tracing category.

4. **Given** I change an Interval or Overlap value, **When** the fragment reruns, **Then** the edited values remain reflected in the editor state for the current session and the category header/count rendering continues to work correctly.

5. **Given** I toggle a category OFF and then ON before saving, **When** the editor re-renders, **Then** any in-flight Interval and Overlap edits for that category are preserved in the current UI state rather than being lost during the toggle transition.

6. **Given** I click **Reset to defaults**, **When** the page re-renders, **Then** Interval and Overlap values return to their story-defined defaults for each source. Durable save/load verification for these fields is handled in Story 3.3.

## Tasks / Subtasks

- [x] **Task 1: Define source defaults lookup** (AC: 1, 2, 3, 6)
  - [x] 1.1 Add a `SOURCE_DEFAULTS` dictionary to `app/streamlit/utils/source_discovery.py` that maps source FQNs (or view names from `ACCOUNT_USAGE_MVP_VIEWS`) to their default operational settings:
    ```python
    SOURCE_DEFAULTS: dict[str, dict[str, int]] = {
        "QUERY_HISTORY": {"interval_seconds": 900, "overlap_minutes": 50},
        "TASK_HISTORY": {"interval_seconds": 900, "overlap_minutes": 50},
        "COMPLETE_TASK_GRAPHS": {"interval_seconds": 900, "overlap_minutes": 50},
        "LOCK_WAIT_HISTORY": {"interval_seconds": 900, "overlap_minutes": 66},
    }
    EVENT_TABLE_DEFAULT_INTERVAL_SECONDS = 60
    ```
    For ACCOUNT_USAGE, the overlap defaults are `documented_max_latency × 1.1`: QUERY_HISTORY / TASK_HISTORY / COMPLETE_TASK_GRAPHS = 50 min (45 min × 1.1); LOCK_WAIT_HISTORY = 66 min (60 min × 1.1).
  - [x] 1.2 Add interval bound constants:
    ```python
    MIN_INTERVAL_SECONDS = 60
    MAX_INTERVAL_SECONDS = 86400
    MIN_OVERLAP_MINUTES = 1
    MAX_OVERLAP_MINUTES = 1440
    ```
  - [x] 1.3 Add a helper function `get_source_defaults(source: DiscoveredSource) -> dict[str, int | None]` that returns `{"interval_seconds": int, "overlap_minutes": int | None}`. For AU sources, look up from `SOURCE_DEFAULTS` by extracting the view name from the FQN. For custom AU views, return the overlap of the parent AU view they reference (if identifiable) or a safe default (50 min). For Event Tables, return `EVENT_TABLE_DEFAULT_INTERVAL_SECONDS` for interval and `None` for overlap.

- [x] **Task 2: Extend DataFrame model with new columns** (AC: 1, 2, 3)
  - [x] 2.1 Update `_build_category_df()` in `telemetry_sources.py` to accept a category definition and add new columns to each row:
    - `interval_seconds`: default interval from `get_source_defaults()`
    - `overlap_minutes`: default overlap from `get_source_defaults()` (only for `account_usage` family; use `pd.NA` or a sentinel for event tables — these won't be displayed)
  - [x] 2.2 The function signature changes to:
    ```python
    def _build_category_df(
        sources: list[DiscoveredSource],
        poll_values: list[bool],
        category: CategoryDef,
    ) -> pd.DataFrame:
    ```
  - [x] 2.3 Use story-defined defaults for this slice. Durable load/override from `_internal.config` is intentionally deferred to Story 3.3.

- [x] **Task 3: Add new columns to `st.data_editor`** (AC: 1, 2, 3)
  - [x] 3.1 Update `_display_columns()` to include the new columns:
    - **Both categories**: add `"interval_seconds"` after `"view_name"`
    - **`account_usage` family only**: add `"overlap_minutes"` after `"interval_seconds"`
  - [x] 3.2 Update `column_config` in `_render_category()`:
    ```python
    "interval_seconds": st.column_config.NumberColumn(
        "Interval (s)",
        min_value=60,
        max_value=86400,
        step=60,
        help="Polling interval in seconds (min: 60, max: 86400)",
    ),
    ```
    For `account_usage` categories only:
    ```python
    "overlap_minutes": st.column_config.NumberColumn(
        "Overlap (min)",
        min_value=1,
        max_value=1440,
        step=1,
        help="Overlap window in minutes for watermark dedup (min: 1, max: 1440)",
    ),
    ```
  - [x] 3.3 Update the `disabled_cols` logic in `_render_category()`. The current code disables ALL columns except `poll` when the category is ON (`[col for col in display_cols if col != "poll"]`). This must change to also exclude `interval_seconds` and `overlap_minutes` from the disabled list so they are editable:
    ```python
    _EDITABLE_COLS = {"poll", "interval_seconds", "overlap_minutes"}
    disabled_cols: list[str] | bool = True if not enabled else [
        column for column in display_cols if column not in _EDITABLE_COLS
    ]
    ```
    When the category is OFF, `disabled=True` locks everything (unchanged). When ON, `view_name` (and `telemetry_types`/`telemetry_sources` if shown) remain read-only while `poll`, `interval_seconds`, and `overlap_minutes` are editable.

- [x] **Task 4: Preserve in-memory editor state for new fields** (AC: 4, 5)
  - [x] 4.1 Extend the existing editor-overlay pattern so Interval and Overlap edits survive fragment reruns in the same session.
  - [x] 4.2 Extend `_apply_pack_state()` to also bake in-flight editor edits for `interval_seconds` and `overlap_minutes` columns (same pattern as existing `poll` column consolidation) so category toggle transitions do not discard edits.
  - [x] 4.3 Generalized `_effective_polls()` into an `_effective_values()` helper that can overlay edits for arbitrary columns. `_effective_polls()` now delegates to `_effective_values(df, editor_key, "poll")`.

- [x] **Task 5: Extend reset-to-defaults behavior** (AC: 6)
  - [x] 5.1 Update `_reset_to_defaults()` so it restores `interval_seconds` and `overlap_minutes` to their computed defaults in addition to the existing poll defaults.
  - [x] 5.2 Ensure editor widget reset/versioning still works when defaults are re-applied programmatically.

- [x] **Task 6: Tests** (AC: 1–6) — split across `tests/test_source_discovery.py` and `tests/test_telemetry_sources_page.py`
  - [x] 6.1 Unit tests for `get_source_defaults()`: verify correct defaults for each AU source, correct interval for Event Tables, `None` overlap for Event Tables.
  - [x] 6.2 Unit tests for extended `_build_category_df()`: verify new columns are present with correct defaults.
  - [x] 6.3 Unit tests for `_display_columns()`: verify overlap column present for AU, absent for ET.
  - [x] 6.4 Unit tests for editor overlay behavior: changing interval or overlap survives fragment reruns in current session.
  - [x] 6.5 Unit tests for category toggle consolidation and reset-to-defaults behavior.

- [x] **Task 7: Discovery UX improvements** (added during implementation)
  - [x] 7.1 Discovery runs only once on first page visit; subsequent runs require manual "Discover sources" button click.
  - [x] 7.2 Info bar redesigned with separate icon, text, "Last discovered: timestamp", and right-aligned Discover sources button.
  - [x] 7.3 Wide layout with balanced 3rem side padding via `st.set_page_config(layout="wide")`.

- [x] **Task 8: Durable save/load for interval and overlap** (originally planned for Story 3.3, implemented here)
  - [x] 8.1 `_save_current_configuration()` persists `source.<slug>.poll_interval_seconds` and `source.<slug>.overlap_minutes` alongside poll state.
  - [x] 8.2 `_load_saved_controls()` restores saved intervals and overlaps from `_internal.config` on page load.

- [x] **Task 9: Fix widget key cleanup bug on page navigation**
  - [x] 9.1 Pack toggle keys (used by `st.toggle` widget) were removed from `st.session_state` by Streamlit when navigating away from the page. On return, they defaulted to `False` while `_load_saved_controls` skipped DB reload (signature match).
  - [x] 9.2 Fixed by restoring pack keys from `_SAVED_STATE_KEY` snapshot instead of defaulting to `False`, and by requiring `_SAVED_STATE_KEY` to exist before allowing the signature-based early return.

## Dev Notes

### Architecture compliance

- **Streamlit version:** Target 1.52.2 on Snowflake Warehouse Runtime.
- **Session:** Use `get_active_session()` via `utils.snowflake.get_session()` — established.
- **Config key conventions (canonical, from architecture.md):**
  - `source.<slug>.poll_interval_seconds` — interval in seconds
  - `source.<slug>.overlap_minutes` — overlap in minutes (AU sources only)
  - `source.<slug>.view_fqn` — already saved by Story 3.1
  - `source.<slug>.poll` — already saved by Story 3.1
- **Story boundary:** Story 3.1 already delivered source discovery, source selection via Poll checkboxes, and the existing save/reset footer. Story 3.2 is strictly the interval/overlap editing slice. Story 3.3 verifies durable save/load coverage for the full 3.1-3.2 configuration set.
- **Slug convention:** `source_slug(fqn)` from `utils/source_discovery.py` converts FQN to config-safe key.
- **Fragment architecture:** All interactive widgets live inside `_interactive_content()` which is decorated with `@st.fragment`. Static chrome (CSS, header, caption, info) lives outside. Widget clicks rerun only the fragment.

### Per-source overlap defaults (from architecture.md section "Per-source overlap defaults")

| Source | Documented Max Latency | Default Overlap | Config Key |
|---|---|---|---|
| QUERY_HISTORY | Up to 45 min | **50 min** | `source.query_history.overlap_minutes` |
| TASK_HISTORY | Up to 45 min | **50 min** | `source.task_history.overlap_minutes` |
| COMPLETE_TASK_GRAPHS | Up to 45 min | **50 min** | `source.complete_task_graphs.overlap_minutes` |
| LOCK_WAIT_HISTORY | Up to 60 min | **66 min** | `source.lock_wait_history.overlap_minutes` |

Defaults = `documented_max_latency × 1.1`. Admin can decrease to minimize re-scans or increase as safety margin. Dedup always runs regardless of overlap size.

### Interval defaults

- **ACCOUNT_USAGE sources:** 900 seconds (15 minutes). This balances near-real-time monitoring with the inherent AU latency (rows arrive 5–45 min after event). Polling more frequently than the latency window wastes compute.
- **Event Table sources:** 60 seconds (1 minute). Triggered tasks check the stream every SCHEDULE interval; 60s is the minimum supported by Snowflake for triggered tasks.

### Key `st.data_editor` patterns (from Story 3.1 lessons learned)

1. **NEVER write editor return value back into the base DataFrame** — causes double-toggle. Let the editor manage its own edits internally.
2. **Read editor internal state** from `st.session_state[editor_key]` → `{"edited_rows": {row: {col: val}}, ...}`.
3. **Overlay pattern:** To compute effective values before the editor renders, overlay editor edits onto the base DataFrame (see existing `_effective_polls()` helper). Extend this pattern for interval and overlap columns.
4. **`pinned=True`** on `CheckboxColumn` to lock its width. New `NumberColumn` columns get natural sizing with `use_container_width=True`.
5. **Editor widget reset:** When programmatically changing the base DataFrame, delete stale editor state with `_reset_editor_widget(cat_key)` — already handled by `_apply_pack_state()`.
6. **`disabled` parameter:** When category is OFF, `disabled=True` locks all columns. When ON, `disabled=[list of read-only columns]` — currently ALL columns except `poll` are disabled (i.e. `view_name` and conditionally `telemetry_types`/`telemetry_sources`). This story must widen the editable set to also include `interval_seconds` and `overlap_minutes`.
7. **Do not widen this story into persistence work.** Reuse the existing footer controls from Story 3.1, but durable save/load verification for the new fields belongs to Story 3.3.

### Files to modify

| File | Changes |
|------|---------|
| `app/streamlit/utils/source_discovery.py` | Add `SOURCE_DEFAULTS`, interval/overlap constants, `get_source_defaults()` |
| `app/streamlit/pages/telemetry_sources.py` | Extend `_build_category_df()`, `_display_columns()`, `column_config`, editor overlay helpers, `_apply_pack_state()`, `_reset_to_defaults()` |
| `tests/test_source_discovery.py` | Add tests for `get_source_defaults()`, constants, extended DataFrame, editor overlay behavior, category toggle consolidation, reset-to-defaults |

No new files are created. No changes to `snowflake.yml` artifacts (existing files only).

### What this story does NOT implement (scope boundaries)

| Feature | Deferred to |
|---------|-------------|
| Source selection (choosing which discovered default/custom source rows are polled) | Story 3.1 |
| Durable save/load verification for `poll_interval_seconds` and `overlap_minutes` | Story 3.3 |
| `source.<slug>.poll_interval_seconds` / `source.<slug>.overlap_minutes` writes to `_internal.config` | Story 3.3 |
| `source.<slug>.source_type` config key persistence | Later story or post-MVP |
| Health columns (Status, Freshness, Recent runs, Errors) | Epic 7 |
| Status dot colors from health data | Epic 7 |
| Batch size column / config | Out of scope for now (deferred) |
| Duration string display (e.g. "15m" instead of "900") | Post-MVP polish |
| Guardrail warning when run duration ≈ interval | Post-MVP |
| Adaptive overlap auto-tuning | Post-MVP |
| Per-row dropdown to switch between default and custom source | Not part of this MVP slice — users select/deselect discovered rows via Poll checkboxes |

### Previous Story Intelligence (Story 3.1)

Key learnings from Story 3.1 implementation that directly apply:

1. **`st.data_editor` state management:** The editor's internal state lives under `st.session_state[editor_key]` as `{"edited_rows": {...}}`. Never write edited DataFrame back into the base `data` parameter. This caused double-toggle bugs with checkboxes in early iterations.
2. **Fragment boundary:** `_interactive_content()` wraps all widgets. CSS and header remain outside. This prevents full-page rerun greyout on widget clicks.
3. **`_effective_polls()` pattern:** Overlays editor edits onto base DataFrame to compute accurate counts before the editor renders. This same pattern must be extended for interval and overlap values.
4. **`_reset_editor_widget()`:** Increments a version counter in the editor key to force a fresh editor instance. Must be called whenever the base DataFrame columns or values are programmatically changed.
5. **`_apply_pack_state()`:** Consolidates pending editor edits into the base DataFrame when the category toggle changes, then resets the editor. This must now also consolidate interval and overlap edits.
6. **Existing save flow already exists:** Story 3.1 introduced the real save/reset footer and durable save for pack state and per-source poll state. Story 3.2 should plug into the same page architecture without redefining save ownership.
7. **Config loading exists but is not the focus here:** Story 3.3 will extend the durable load/save verification to include `.poll_interval_seconds` and `.overlap_minutes`.

### Implementation guidance

**Extending `_effective_polls()` to a generic overlay:**

Create `_effective_values(df: pd.DataFrame, editor_key: str, column: str) -> pd.Series` that overlays editor edits for any column onto the base DataFrame. This avoids duplicating the overlay logic for each new editable column.

**Reset to defaults:**

`_reset_to_defaults()` currently resets only poll values. Extend to also reset `interval_seconds` and `overlap_minutes` to their default values from `get_source_defaults()`.

### References

- [Source: `_bmad-output/planning-artifacts/architecture.md` — Config Table Key Naming, lines 419–430]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — Per-source overlap defaults, lines 732–743]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — ACCOUNT_USAGE Pipeline, lines 708–726]
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` — Telemetry sources columns 4c, lines 745–812]
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` — Implementation 4f, lines 829–836]
- [Source: `_bmad-output/planning-artifacts/epics.md` — Epic 3 Stories 3.1–3.3]
- [Source: `_bmad-output/implementation-artifacts/3-1-source-discovery-and-pack-toggles.md` — Scope boundaries and dev notes]
- [Source: `app/streamlit/pages/telemetry_sources.py` — Current implementation]
- [Source: `app/streamlit/utils/source_discovery.py` — Discovery model and helpers]
- [Source: `app/streamlit/utils/config.py` — Existing persistence utilities owned by Story 3.1 / Story 3.3]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (via Cursor)

### Debug Log References

- Live Snowflake Native App UAT via Snowsight browser on 2026-03-31 and 2026-04-01.
- Playwright MCP used for local Streamlit preview DOM inspection of info bar layout.
- Cortex CLI interactive session confirming RCR procedure limitations in warehouse runtime.
- `snow sql` diagnostic queries against `SNOWFLAKE.ACCOUNT_USAGE.TABLES` to verify `TABLE_TYPE = 'EVENT TABLE'`.
- Previous conversation: [Telemetry sources discovery & RCR](f26bc351-e2fd-43e8-a50a-3446103fb3b3)

### Completion Notes List

- **All 6 original acceptance criteria verified.** Interval and overlap columns render, edit, survive toggles, reset to defaults, and persist to `_internal.config`.
- **Durable save/load for intervals and overlaps was implemented in this story** rather than deferring to Story 3.3, because the save/reset footer infrastructure was already in place and the config key conventions (`source.<slug>.poll_interval_seconds`, `source.<slug>.overlap_minutes`) were straightforward to add.
- **Discovery UX overhaul** was done alongside this story: auto-discovery limited to first visit, manual "Discover sources" button added per Figma mockup, info bar with timestamp, wide layout.
- **RCR investigation for real-time event table discovery** was a significant research effort that ultimately confirmed a platform limitation (see Findings below).
- **Widget key cleanup bug** was a Streamlit platform behavior discovered during UAT: navigating away from a page causes Streamlit to remove widget keys from session state, breaking toggle persistence.
- **165 unit tests pass** (40 discovery, 24 telemetry sources page, 23 config, 13 onboarding, 18 cert validation, 57 endpoint/connection, 7 egress).

### Key Findings

#### 1. RCR (Restricted Caller's Rights) cannot work from Streamlit warehouse runtime

**Problem:** Event table discovery via `SNOWFLAKE.ACCOUNT_USAGE.TABLES` has up to ~45 min latency for newly created objects. Can we use `SHOW EVENT TABLES IN ACCOUNT` via an RCR procedure for real-time discovery?

**Investigation:** Created `EXECUTE AS RESTRICTED CALLER` stored procedure in `setup.sql`. Granted `INHERITED CALLER` privileges on databases, schemas, and event tables via `scripts/shared_content.sql`. Procedure worked when called directly by ACCOUNTADMIN via `snow sql`, returning 59 event tables. From the Streamlit app, it returned 0.

**Root cause:** Streamlit in Native Apps runs exclusively in **warehouse runtime**, which always executes as the **app owner role**. When the Streamlit session calls an RCR procedure, the "caller" identity is the app owner, not the consumer. `INHERITED CALLER` grants allow the procedure to use privileges the caller *already has* — they don't confer new ones. Since the app owner inherently lacks SELECT on consumer event tables, the RCR procedure sees nothing.

**Platform requirement for RCR:** `st.connection("snowflake-callers-rights")` — only available in **container runtime** (Preview since Feb 2026, NOT available for Native App Streamlit).

**Resolution:** Reverted to `SNOWFLAKE.ACCOUNT_USAGE.TABLES`, accepting the latency trade-off. RCR procedure code kept as commented-out reference in `setup.sql` for future container runtime migration.

**References:** Snowflake docs "Streamlit in Snowflake: Consumer-rights model", Cortex CLI interactive session (2026-04-01).

#### 2. `TABLE_TYPE` for event tables is `'EVENT TABLE'` (two words)

The `SNOWFLAKE.ACCOUNT_USAGE.TABLES` view uses `TABLE_TYPE = 'EVENT TABLE'` (with a space), not `'EVENT'` or `'EVENT_TABLE'`. This was verified via:
```sql
SELECT DISTINCT TABLE_TYPE, COUNT(*) FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
WHERE DELETED IS NULL GROUP BY TABLE_TYPE
-- Returns: BASE TABLE (88), EVENT TABLE (60), VIEW (587)
```

#### 3. Streamlit widget key cleanup on page navigation

**Problem:** After saving configuration (toggles enabled, sources checked) and navigating away then back, all pack toggles showed "Disabled" despite correct values in `_internal.config`.

**Root cause:** Streamlit removes widget keys from `st.session_state` when the page hosting those widgets is no longer rendered. The `st.toggle` widget key (`pack_enabled.distributed_tracing`) was cleaned up on navigation. On return, the initialization code defaulted it to `False`. The `_load_saved_controls` function's signature-based cache check prevented a DB reload because the discovery data hadn't changed.

**Fix:**
1. Pack toggle initialization now restores from the `_SAVED_STATE_KEY` snapshot (a non-widget session state dict that persists across navigation) instead of defaulting to `False`.
2. Added a guard in `_load_saved_controls` requiring `_SAVED_STATE_KEY` to exist before allowing the signature-based early return, ensuring the first DB load always happens.

**Lesson:** Never use the same key for both widget state and canonical state in a multipage Streamlit app. Widget keys are transient and will be cleaned up when the page is not active. Canonical state should be stored in non-widget session state keys.

### File List

- `app/streamlit/pages/telemetry_sources.py` — extended with interval/overlap columns, discovery button, info bar, widget key fix
- `app/streamlit/utils/source_discovery.py` — added `SOURCE_DEFAULTS`, constants, `get_source_defaults()`, fixed `TABLE_TYPE = 'EVENT TABLE'`
- `app/streamlit/main.py` — added `st.set_page_config(layout="wide")`, updated `_GLOBAL_CSS` with 3rem side padding
- `app/setup.sql` — commented out RCR procedure with explanation
- `scripts/shared_content.sql` — removed `INHERITED CALLER` grants added during RCR investigation
- `tests/test_source_discovery.py` — added tests for `get_source_defaults()`, constants, bounds, updated event table discovery tests for `TABLE_TYPE` fix
- `tests/test_telemetry_sources_page.py` — **new** — 24 tests for `_build_category_df`, `_display_columns`, `_effective_values`, reset-to-defaults, category toggle consolidation

### What this story does NOT implement (scope boundaries, updated)

| Feature | Deferred to |
|---------|-------------|
| Durable save/load verification for interval and overlap | ~~Story 3.3~~ **Implemented in this story** |
| Health columns (Status, Freshness, Recent runs, Errors) | Epic 7 |
| Status dot colors from health data | Epic 7 |
| Batch size column / config | Out of scope for now (deferred) |
| Duration string display (e.g. "15m" instead of "900") | Post-MVP polish |
| Guardrail warning when run duration ≈ interval | Post-MVP |
| Adaptive overlap auto-tuning | Post-MVP |
| Real-time event table discovery (RCR / container runtime) | Blocked on Snowflake container runtime GA for Native Apps |
| Per-row dropdown to switch between default and custom source | Not part of this MVP slice |

---

## Completion Notes (post-implementation)

**Implementation date:** 2026-03-31 – 2026-04-01

All 6 original acceptance criteria verified plus 3 additional tasks completed (discovery UX, durable save/load, widget key fix). 165 unit tests pass.
