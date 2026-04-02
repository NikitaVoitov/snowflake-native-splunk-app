# Story 3.3: Save source configuration

Status: done

## Story

As a Snowflake administrator (Maya),
I want to save my source and pack configuration and see an unsaved changes indicator until I save,
So that I do not lose changes and know when the app state matches the UI.

## Acceptance Criteria

1. **Given** I have changed pack toggles, source polling, intervals, or overlaps on Telemetry sources, **When** I have not yet saved, **Then** a footer shows "You have unsaved changes" and "Save configuration" (primary) is available.

2. **Given** I click "Save configuration", **When** the save completes, **Then** `pack_enabled.*` and `source.<slug>.*` keys (`view_fqn`, `poll`, `poll_interval_seconds`, `overlap_minutes`) are written to `_internal.config`, where `<slug>` is derived from `source_slug(fqn)`.

3. **Given** a save completed successfully, **When** I reload the page (navigate away and back, or full browser refresh), **Then** the page restores the saved pack toggle states, poll checkbox states, interval values, and overlap values exactly as they were before the reload.

4. **Given** a save completed successfully, **Then** the unsaved indicator clears, the footer shows "Configuration saved successfully.", and `st.session_state` is synced with config so that no diff is detected.

5. **Given** I have saved a configuration, **When** Getting Started checks Task 2 completion, **Then** Task 2 is marked complete if at least one pack is enabled (via `pack_enabled.*` keys in `_internal.config`).

6. **Given** I save, then change something, then click "Reset to defaults", **When** I then click "Save configuration", **Then** the defaults are persisted correctly and a subsequent reload shows default values.

7. **Given** a source that only exists in the Distributed Tracing category (Event Table), **When** I save its configuration, **Then** `overlap_minutes` is NOT written to config for that source (because Event Tables have no overlap concept).

8. **Given** a SnowparkSQLException occurs during save, **Then** an error message is shown and the unsaved state is preserved so the user can retry.

## Tasks / Subtasks

- [x] **Task 1: Audit and verify the existing save flow** (AC: 1, 2, 4)
  - [x] 1.1 Review `_save_current_configuration()` in `app/streamlit/pages/telemetry_sources.py`: confirm it writes `pack_enabled.<cat_key>`, `source.<slug>.view_fqn`, `source.<slug>.poll`, `source.<slug>.poll_interval_seconds`, and `source.<slug>.overlap_minutes` via `save_config_batch()`. **Already implemented in Story 3.2 Task 8** — verify correctness, not rebuild.
  - [x] 1.2 Verify `_capture_current_state()` correctly captures the effective state (overlaying editor edits onto the base DataFrame) for all categories and fields.
  - [x] 1.3 Verify the unsaved-changes comparison in `_render_footer()`: `current_state != saved_state` must produce correct diffs for pack toggles, poll checkboxes, interval values, and overlap values. Confirm that the `_JUST_SAVED_KEY` flag clears on the next user edit.
  - [x] 1.4 Verify the save handler no longer depends on `pack_enabled.dummy` for any onboarding or completion behavior: Getting Started Task 2 already uses real `PACK_ENABLED_CONFIG_KEYS`, so the dummy write is obsolete and safe to remove.

- [x] **Task 2: Audit and verify the load flow** (AC: 3, 5)
  - [x] 2.1 Review `_load_saved_controls()`: confirm it reads `pack_enabled.*` and `source.*` from `_internal.config` via `load_config_like()`, parses slug→FQN mappings, and restores pack toggles, poll states, interval values, and overlap values into the correct session state keys and DataFrames.
  - [x] 2.2 Verify the `_DISCOVERY_SIGNATURE_KEY` caching: `_load_saved_controls()` early-returns when the signature matches AND `_SAVED_STATE_KEY` exists. After a save, the signature is cleared (`st.session_state[_DISCOVERY_SIGNATURE_KEY] = None`) and `_POST_SAVE_RELOAD_KEY` is set, triggering a full page rerun that reloads from DB.
  - [x] 2.3 Verify that Getting Started Task 2 checks real `pack_enabled.*` keys (see `app/streamlit/utils/onboarding.py` `load_task_completion_state`): it calls `load_config_like(session, "pack_enabled.")` and checks `PACK_ENABLED_CONFIG_KEYS` (`pack_enabled.distributed_tracing`, `pack_enabled.query_performance`).
  - [x] 2.4 Verify cross-page navigation resilience: the widget key cleanup fix from Story 3.2 (pack toggle keys restored from `_SAVED_STATE_KEY` snapshot) must survive save→navigate→return cycles.

- [x] **Task 3: Fix — skip `overlap_minutes` for Event Table sources** (AC: 7)
  - [x] 3.1 In `_save_current_configuration()`, the current code writes `overlap_minutes` if the key exists in the `entry` dict. For Event Table sources, `_capture_current_state()` skips overlap when the value is `None` or `pd.isna()`, so this should already be handled. **Verify** by tracing through the code path for an Event Table source with `overlap_minutes = None` in the DataFrame.
  - [x] 3.2 If `overlap_minutes` is being written as `"None"` (string) for Event Tables, fix `_save_current_configuration()` to explicitly skip when the overlap value is `None` or not a valid integer.
  - [x] 3.3 Verify `_load_saved_controls()` tolerates missing `overlap_minutes` keys for ET sources (they should simply not be present in `saved_overlaps`).

- [x] **Task 4: Fix — remove stale `pack_enabled.dummy` write** (AC: 2)
  - [x] 4.1 The save handler in `_render_footer()` still calls `save_config(session, "pack_enabled.dummy", "false")` after saving the real configuration. This is a legacy artifact from Story 2.3. The onboarding module no longer checks `pack_enabled.dummy` — it checks real `PACK_ENABLED_CONFIG_KEYS`. **Remove** the `save_config(session, "pack_enabled.dummy", "false")` call to eliminate dead config writes.
  - [x] 4.2 Verify no remaining code path in Telemetry Sources or Getting Started depends on `pack_enabled.dummy`, and keep all pack completion logic tied to the real pack keys only.

- [x] **Task 5: Add comprehensive persistence round-trip tests** (AC: 1–8)
  - [x] 5.1 Test `_save_current_configuration()` produces the correct config keys and values for a mixed scenario: 2 AU sources (one polled, one not) and 1 ET source (polled). Verify:
    - `pack_enabled.distributed_tracing` and `pack_enabled.query_performance` keys are present
    - `source.<slug>.view_fqn`, `.poll`, `.poll_interval_seconds` for all sources
    - `source.<slug>.overlap_minutes` present only for AU sources, absent for ET sources
  - [x] 5.2 Test `_load_saved_controls()` round-trip: mock `load_config_like()` to return saved keys from Task 5.1, then verify that session state DataFrames match the saved values (pack toggles, polls, intervals, overlaps).
  - [x] 5.3 Test `_capture_current_state()` accurately reflects editor-modified values (user changed interval but hasn't saved yet).
  - [x] 5.4 Test unsaved-changes detection: after `_load_saved_controls()`, `_capture_current_state()` must equal `_SAVED_STATE_KEY` (no false positives). After modifying a poll checkbox, they must differ.
  - [x] 5.5 Test save → reset-to-defaults → save round-trip: defaults are correctly persisted.
  - [x] 5.6 Test error handling: mock `save_config_batch()` to raise `SnowparkSQLException` and verify the error is surfaced (the `_JUST_SAVED_KEY` remains False).
  - [x] 5.7 Confirm existing Getting Started tests already cover real pack-key completion logic and ignore `pack_enabled.dummy`; add or adjust onboarding tests only if Task 2.3 uncovers a real regression. New test work in this story should stay focused on source/pack persistence behavior.

- [x] **Task 6: Live verification on Snowflake** (AC: 1–8)
  - [x] 6.1 Deploy with `PRIVATE_KEY_PASSPHRASE=qwerty123 snow app run -c dev`.
  - [x] 6.2 Manual test: open Telemetry Sources → enable a pack → check some sources → change an interval → save → navigate to Getting Started → verify Task 2 complete → navigate back to Telemetry Sources → verify values persisted.
  - [x] 6.3 Manual test: verify `SELECT * FROM _internal.config WHERE CONFIG_KEY LIKE 'source.%' OR CONFIG_KEY LIKE 'pack_enabled.%'` returns expected rows.
  - [x] 6.4 Manual test: reset to defaults → save → verify config rows updated.
  - [x] 6.5 Manual test: verify no `overlap_minutes` config key exists for Event Table sources.

## Dev Notes

### Critical context: persistence is already implemented

Stories 3.1 and 3.2 **already implemented** the save/load infrastructure. Story 3.2's completion notes explicitly state:

> "Durable save/load for intervals and overlaps was implemented in this story rather than deferring to Story 3.3, because the save/reset footer infrastructure was already in place."

**This story is a verification, hardening, and cleanup story** — not a greenfield implementation. The primary value is:
1. Audit the existing save/load code for correctness and edge cases
2. Add targeted tests that prove round-trip persistence works
3. Clean up legacy config artifacts that are no longer part of the real product behavior (`pack_enabled.dummy`)
4. Verify Event Table sources don't leak `overlap_minutes` into config
5. Confirm Getting Started task completion works end-to-end

### Architecture compliance

- **Streamlit version:** Target 1.52.2 on Snowflake Warehouse Runtime.
- **Session:** `get_active_session()` via `utils.snowflake.get_session()`.
- **Config key conventions (canonical, from architecture.md):**
  - `pack_enabled.distributed_tracing` / `pack_enabled.query_performance`
  - `source.<slug>.view_fqn` — fully qualified name of the source
  - `source.<slug>.poll` — `"true"` or `"false"`
  - `source.<slug>.poll_interval_seconds` — integer as string
  - `source.<slug>.overlap_minutes` — integer as string (AU sources only)
- **Slug convention:** `source_slug(fqn)` from `app/streamlit/utils/source_discovery.py` converts FQN like `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` to `snowflake_account_usage_query_history`.
- **State management (D4):** `st.session_state` as cache, `_internal.config` as durable store. Explicit Save pattern. `_SAVED_STATE_KEY` holds last-saved snapshot for comparison.
- **Fragment architecture:** All interactive widgets inside `_interactive_content()` decorated with `@st.fragment`. Static chrome outside. Widget clicks rerun only the fragment; `st.rerun()` inside the save handler triggers a full page rerun intentionally.

### Existing save flow (in `app/streamlit/pages/telemetry_sources.py`)

```python
# _render_footer() line 873:
if save_clicked:
    _save_current_configuration(session, current_state, grouped)
    st.session_state[_SAVED_STATE_KEY] = current_state
    st.session_state[_JUST_SAVED_KEY] = True
    st.session_state[_POST_SAVE_RELOAD_KEY] = True
    st.session_state[_DISCOVERY_SIGNATURE_KEY] = None
    st.session_state.drilled_from_getting_started = False
    st.toast("Configuration saved successfully.")
    st.rerun()
```

The `st.rerun()` triggers a full page rerun. Because `_DISCOVERY_SIGNATURE_KEY` is cleared, `_load_saved_controls()` re-reads from DB, confirming the save. `_POST_SAVE_RELOAD_KEY` prevents clearing `_JUST_SAVED_KEY` on that reload.

### Existing load flow (in `app/streamlit/pages/telemetry_sources.py`)

```python
# _load_saved_controls() loads:
# 1. pack_config = load_config_like(session, "pack_enabled.")
# 2. source_config = load_config_like(session, "source.")
# 3. Parses slug→FQN, slug→poll, slug→interval, slug→overlap
# 4. Applies saved overlaps only to ACCOUNT_USAGE rows
# 5. Sets session state: pack toggles, per-source DataFrames with saved values
# 6. Captures _SAVED_STATE_KEY snapshot and returns True
```

If config loading fails with `SnowparkSQLException`, `_load_saved_controls()` now returns
`False`, preserves the previously loaded UI/session snapshot, and surfaces the error instead
of rebuilding a default state and treating it as saved.

### Unsaved-changes detection

`_render_footer()` calls `_capture_current_state(grouped)` every fragment rerun and compares it against `st.session_state[_SAVED_STATE_KEY]`. This comparison uses plain dict equality, which works because all values are Python primitives (`bool`, `int`).

**Known subtlety:** `_capture_current_state()` uses `_effective_values()` to overlay editor edits onto the base DataFrame. This means even unsaved editor changes (user typed a new interval but hasn't saved) are reflected in `current_state`, correctly triggering the unsaved indicator.

### Getting Started Task 2 completion

From `app/streamlit/utils/onboarding.py`:
```python
elif task.step == 2:
    packs = load_config_like(session, task.config_key)  # "pack_enabled."
    result[task.step] = any(
        (packs.get(key) or "").lower() == "true"
        for key in PACK_ENABLED_CONFIG_KEYS
    )
```

This checks `pack_enabled.distributed_tracing` and `pack_enabled.query_performance`. At least one must be `"true"` for Task 2 to be complete. `pack_enabled.dummy` is no longer part of the functional contract and should not be written by the Telemetry Sources save flow.

### Widget key cleanup resilience (Story 3.2 fix)

Streamlit removes widget keys from `st.session_state` when navigating away from a page. The pack toggle keys (`pack_enabled.distributed_tracing`) are `st.toggle` widget keys and get cleaned up. On return, they are restored from the `_SAVED_STATE_KEY` snapshot:

```python
for category in CATEGORIES:
    if _ss_pack_key(category.key) not in st.session_state:
        _saved = st.session_state.get(_SAVED_STATE_KEY, {})
        st.session_state[_ss_pack_key(category.key)] = (
            _saved.get("packs", {}).get(category.key, False)
        )
```

### Event Table overlap handling

In `_capture_current_state()`:
```python
if (
    category.source_family == "account_usage"
    and not overlaps.empty
    and overlaps.iloc[i] is not None
    and pd.notna(overlaps.iloc[i])
):
    entry["overlap_minutes"] = int(overlaps.iloc[i])
```

This story now enforces the Event Table rule in **all three** persistence phases:

1. **Load:** `_load_saved_controls()` only applies saved overlaps to ACCOUNT_USAGE rows, so stale `source.<et_slug>.overlap_minutes` rows in `_internal.config` are ignored.
2. **Capture:** `_capture_current_state()` only includes `overlap_minutes` for ACCOUNT_USAGE categories.
3. **Save:** `_save_current_configuration()` only writes `source.<slug>.overlap_minutes` for discovered ACCOUNT_USAGE sources.

That means even if a legacy or manually inserted Event Table overlap key exists in `_internal.config`,
the UI will not rehydrate it and a subsequent save will not write it back.

In `_save_current_configuration()`:
```python
if fqn in overlap_supported_fqns and "overlap_minutes" in entry:
    pairs[f"source.{slug}.overlap_minutes"] = str(entry["overlap_minutes"])
```

### Files to modify

| File | Changes |
|------|---------|
| `app/streamlit/pages/telemetry_sources.py` | Remove `save_config(session, "pack_enabled.dummy", "false")`; apply any edge-case fixes found during the audit |
| `tests/test_telemetry_sources_page.py` | Add or expand round-trip persistence tests, unsaved-changes tests, reset/save tests, and save error handling tests for source and pack configuration |

No new files are created. No changes to `snowflake.yml` artifacts.

### What this story does NOT implement (scope boundaries)

| Feature | Deferred to |
|---------|-------------|
| Health columns (Status, Freshness, Recent runs, Errors) | Epic 7 |
| Status dot colors from health data | Epic 7 |
| Batch size column / config | Out of scope (deferred) |
| Data governance acknowledgement (Task 3) | Story 6.1 / 6.2 |
| Export activation (Task 4) | Story 6.3–6.6 |
| Source type (`default`/`custom`) persistence | Post-MVP |

### Previous Story Intelligence (Story 3.2)

Key learnings that apply directly:

1. **Save/load already works:** Story 3.2 Task 8 implemented `_save_current_configuration()` persisting `source.<slug>.poll_interval_seconds` and `source.<slug>.overlap_minutes` alongside poll state. `_load_saved_controls()` restores them on page load.

2. **Widget key cleanup bug (fixed):** Pack toggle keys (`pack_enabled.<cat>`) are Streamlit widget keys and get cleaned up on navigation. Fixed by restoring from `_SAVED_STATE_KEY` snapshot instead of defaulting to `False`. Also added a guard in `_load_saved_controls` requiring `_SAVED_STATE_KEY` to exist before allowing signature-based early return.

3. **Discovery runs only once:** Auto-discovery on first visit; manual "Discover sources" button for re-runs. This means the discovery → load → render cycle happens exactly once per session start, reducing the surface for stale-state bugs.

4. **`st.rerun()` inside `@st.fragment` triggers a FULL page rerun** — this is intentional in the save handler because it needs to reload from DB. The `_POST_SAVE_RELOAD_KEY` flag prevents the "just saved" message from being cleared during the reload.

5. **`_effective_values()` pattern:** Generic overlay of editor edits onto base DataFrame. Used for `poll`, `interval_seconds`, and `overlap_minutes`. All three must be correctly captured by `_capture_current_state()` for unsaved-changes detection.

6. **165 unit tests pass** across the project (40 discovery, 24 telemetry sources page, 23 config, 13 onboarding, 18 cert validation, 57 endpoint/connection, 7 egress).

### Testing approach

- **Root venv** for all tests: `PYTHONPATH=app/python .venv/bin/python -m pytest tests/ -v`
- Use the existing `telemetry_page` fixture in `tests/test_telemetry_sources_page.py` which mocks `streamlit`, `utils.config`, and `utils.snowflake`.
- For persistence round-trip tests, make `save_config_batch` capture its `pairs` argument and feed them back through `load_config_like`.
- Existing `tests/test_getting_started.py` coverage already verifies that Task 2 uses real `PACK_ENABLED_CONFIG_KEYS` and ignores `pack_enabled.dummy`; do not add new onboarding tests unless the Task 2.3 audit exposes a real gap.

### References

- [Source: `_bmad-output/planning-artifacts/architecture.md` — Config Table Key Naming, D4 State Management]
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` — §4 Telemetry Sources footer, unsaved changes]
- [Source: `_bmad-output/planning-artifacts/epics.md` — Epic 3, Story 3.3]
- [Source: `_bmad-output/implementation-artifacts/3-2-per-source-selection-and-intervals.md` — Task 8 durable save/load, widget key fix]
- [Source: `_bmad-output/implementation-artifacts/3-1-source-discovery-and-pack-toggles.md` — Save/reset footer, config key conventions]
- [Source: `app/streamlit/pages/telemetry_sources.py` — Current implementation]
- [Source: `app/streamlit/utils/config.py` — save_config_batch, load_config_like]
- [Source: `app/streamlit/utils/onboarding.py` — Task 2 completion logic]
- [Source: `tests/test_telemetry_sources_page.py` — Existing test patterns]

## Dev Agent Record

### Agent Model Used

Claude claude-4.6-opus-high-thinking (Cursor Agent)

### Debug Log References

- `PYTHONPATH=app/streamlit .venv/bin/python -m pytest tests/test_telemetry_sources_page.py tests/test_getting_started.py -q`
- `PRIVATE_KEY_PASSPHRASE=qwerty123 snow app run -c dev`

### Completion Notes List

- **Task 1 (Save flow audit):** `_save_current_configuration()` correctly writes all config keys via `save_config_batch()`. `_capture_current_state()` correctly overlays editor edits via `_effective_values()`. Unsaved-changes comparison in `_render_footer()` uses plain dict equality and works correctly. `_JUST_SAVED_KEY` clears via `_mark_unsaved_changes()` on any user edit.
- **Task 2 (Load flow audit):** `_load_saved_controls()` correctly reads from `_internal.config` via `load_config_like()`, parses slug→FQN/poll/interval/overlap mappings, and restores into session state DataFrames. Discovery signature caching works correctly with the `_SAVED_STATE_KEY` existence guard. Getting Started Task 2 uses real `PACK_ENABLED_CONFIG_KEYS` (confirmed in `onboarding.py` and `test_getting_started.py`). Widget key cleanup resilience from Story 3.2 is in place. Post-review hardening now preserves the last good UI state when config reload fails, instead of rebuilding defaults and treating them as saved.
- **Task 3 (ET overlap verification):** Code now skips `overlap_minutes` for Event Table sources during load, capture, and save. This closes the edge case where a stale `source.<et_slug>.overlap_minutes` row in `_internal.config` could otherwise be rehydrated and re-persisted. Live DB confirms zero `overlap_minutes` keys for ET sources. Added tests `test_et_source_overlap_not_in_saved_pairs`, `test_load_tolerates_missing_overlap_for_et`, and `test_load_ignores_stale_overlap_for_et_and_does_not_resave_it` to lock this behavior.
- **Task 4 (Remove dummy write):** Removed `save_config(session, "pack_enabled.dummy", "false")` from `_render_footer()` save handler. Also removed unused `save_config` import. Verified no code depends on `pack_enabled.dummy` — `test_task2_ignores_legacy_dummy_pack_key` in `test_getting_started.py` confirms this. Added `test_save_does_not_write_pack_enabled_dummy` to prevent regression.
- **Task 5 (Tests):** Expanded the telemetry page/unit coverage to exercise the real footer save error path, stale Event Table overlap contamination, and load-failure state preservation in addition to the original round-trip persistence checks. Focused suites now pass: `tests/test_telemetry_sources_page.py` and `tests/test_getting_started.py` (`41 passed`).
- **Task 6 (Live verification):** Re-deployed via `snow app run -c dev` after post-review hardening. Snowflake upgraded `splunk_observability_dev_app` successfully, so the UAT environment reflects the final story implementation.

### File List

- `app/streamlit/pages/telemetry_sources.py` — Removed the legacy dummy write, guarded Event Table overlap handling across load/capture/save, and preserved the last good UI state on config-load failure
- `tests/test_telemetry_sources_page.py` — Expanded persistence tests to cover stale ET overlap rows, load-failure preservation, and the real footer-level save error flow
