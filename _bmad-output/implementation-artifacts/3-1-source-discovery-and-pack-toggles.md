# Story 3.1: Source discovery and pack toggles

Status: in-progress

## Story

As a Snowflake administrator (Maya),
I want to see available Event Tables and ACCOUNT_USAGE views (and custom views that reference them) displayed as full FQNs, enable or disable Monitoring Packs, and check/uncheck individual sources,
So that I can choose what telemetry to export without writing SQL.

## Acceptance Criteria

1. **Given** I have the required Snowflake privileges (`IMPORTED PRIVILEGES ON SNOWFLAKE DB`), **When** I open the Telemetry sources page, **Then** the app discovers Event Tables (via `SNOWFLAKE.ACCOUNT_USAGE.TABLES`) and the supported MVP Performance Pack `ACCOUNT_USAGE` views (validated via `SNOWFLAKE.INFORMATION_SCHEMA.TABLES`) plus custom views that reference either those supported `ACCOUNT_USAGE` views or any discovered Event Table (via `SNOWFLAKE.ACCOUNT_USAGE.VIEWS`). `INFORMATION_SCHEMA` table functions are **not** selectable telemetry sources in this story.

2. **Given** the app has discovered sources, **When** I view the Telemetry sources page, **Then** categories (Distributed Tracing, Query Performance & Execution) are shown with collapsible headers, a status dot, and an enable/disable toggle per category.

3. **Given** categories are displayed, **When** I view a category header, **Then** each category shows a count of effectively-polled/total sources (e.g. "2/9") and a description of the category purpose. When the category toggle is OFF, the count is "0/{total}" regardless of checkbox states.

4. **Given** I expand either telemetry category, **Then** I see an editable `st.data_editor` with columns: **Poll** (checkbox, editable) and **View name** (text, read-only, shown as full FQN). For Event Tables, future columns such as telemetry types and telemetry sources remain hidden until a later story populates them with real data. When a source's Poll is unchecked, its entire row is visually greyed out.

5. **Given** a category toggle is ON and I check a source's Poll checkbox, **When** I view the category header, **Then** the count increments (e.g. "3/9"). **When** I uncheck it, the count decrements and that source's row is visually greyed out.

6. **Given** I toggle a category OFF, **When** I view the page, **Then** the status dot is gray, the `st.data_editor` is rendered as **read-only and greyed out** (all columns disabled), Poll checkboxes **retain their visual state** (preserving the user's selection intent), and the count reflects "0/{total}" because no sources in a disabled category are effectively polled. Toggling OFF is a non-destructive "pause" — turning the category back ON restores the exact checkbox selections that were in place before.

7. **Given** I toggle a category ON, **When** I view the page, **Then** the source table becomes fully interactive and Poll checkboxes **retain their current state** (they are NOT auto-checked). On first enable (no prior selections), all checkboxes start unchecked — the user must manually check the sources they want to poll. The count shows the actual number of checked sources (e.g. "0/4" on first enable, "3/4" after the user checks three).

8. **Given** the page loads for the first time, **Then** all category toggles default to OFF (user must explicitly enable each category), and all Poll checkboxes start unchecked because their parent category is disabled.

9. **Given** the page renders, **Then** the page header shows title "Telemetry Sources" and subtitle per Figma, an `st.info` banner explains how to enable categories and custom views, and the footer shows unsaved-changes controls with **Reset to defaults** and **Save configuration** actions. Saving persists the real pack and per-source poll controls to `_internal.config`.

## Tasks / Subtasks

- [ ] **Task 1: Source discovery logic** (AC: 1)
  - [ ] 1.1 Create `app/streamlit/utils/source_discovery.py` with functions to discover Event Tables and the validated MVP Performance Pack `ACCOUNT_USAGE` views. Use account-wide metadata queries that rely on `IMPORTED PRIVILEGES ON SNOWFLAKE DB`. Do **not** discover or expose `INFORMATION_SCHEMA` table functions as selectable sources in this story.
  - [ ] 1.2 Event Table discovery: `SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES WHERE TABLE_TYPE = 'EVENT TABLE' AND DELETED IS NULL`. Show the discovered Event Table as a full FQN in the UI. Keep `telemetry_types` and `telemetry_sources` as empty strings for now; these are intentionally not populated in this story because deriving them would require expensive row-content inspection of each Event Table. Do NOT use `SNOWFLAKE.ACCOUNT_USAGE.EVENT_TABLES` (does not exist) or `INFORMATION_SCHEMA.EVENT_TABLES` (database-scoped).
  - [ ] 1.3 ACCOUNT_USAGE view validation: `SELECT TABLE_NAME FROM SNOWFLAKE.INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'ACCOUNT_USAGE' AND TABLE_TYPE = 'VIEW' AND TABLE_NAME IN (...)` with the validated MVP known list: `QUERY_HISTORY`, `TASK_HISTORY`, `COMPLETE_TASK_GRAPHS`, `LOCK_WAIT_HISTORY`. After validation, surface these objects in the UI as full FQNs (`SNOWFLAKE.ACCOUNT_USAGE.<VIEW_NAME>`). This query is metadata validation only; it does **not** make `INFORMATION_SCHEMA` table functions part of the MVP source model.
  - [ ] 1.4 Custom view discovery: `SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, VIEW_DEFINITION FROM SNOWFLAKE.ACCOUNT_USAGE.VIEWS WHERE DELETED IS NULL AND TABLE_CATALOG != 'SNOWFLAKE' AND VIEW_DEFINITION IS NOT NULL`. Do NOT use `INFORMATION_SCHEMA.VIEWS` (database-scoped, fails without `USE DATABASE`). Parse `VIEW_DEFINITION` to assign custom views to the matching source category, but only for the validated MVP `ACCOUNT_USAGE` views and the discovered Event Tables.
  - [ ] 1.5 Return structured data: list of sources with fields `view_name` (full FQN), `fqn` (fully qualified name), `category` (Distributed Tracing or Query Performance & Execution), `is_custom` (bool), `telemetry_types` (empty string for now), and `telemetry_sources` (empty string for now). No `source_type` tag needed — column schemas differ per category.

- [ ] **Task 2: Category definitions and data model** (AC: 2, 3)
  - [ ] 2.1 Define MVP category constants in `app/streamlit/utils/source_discovery.py` or a shared constants location:
    - **Distributed Tracing**: Event Table-based sources (active account event table, task execution events, native app event tables, other discovered event tables, custom trace views).
    - **Query Performance & Execution**: ACCOUNT_USAGE-based MVP sources (`SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`, `SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY`, `SNOWFLAKE.ACCOUNT_USAGE.COMPLETE_TASK_GRAPHS`, `SNOWFLAKE.ACCOUNT_USAGE.LOCK_WAIT_HISTORY`) and custom views referencing them.
  - [ ] 2.2 Build a dataclass or NamedTuple for `DiscoveredSource` (view_name, fqn, category, is_custom, telemetry_types, telemetry_sources). `view_name` is the full FQN for this story. `telemetry_types` and `telemetry_sources` remain empty strings until a future story populates them from collected telemetry data.
  - [ ] 2.3 Build a dataclass or NamedTuple for `CategoryDef` (name, description, source_family: "event_table" | "account_usage").

- [ ] **Task 3: Telemetry sources page UI — category headers and pack toggles** (AC: 2, 3, 6, 7, 8, 9)
  - [ ] 3.1 Replace the current placeholder `app/streamlit/pages/telemetry_sources.py` with the real implementation.
  - [ ] 3.2 Page header: `st.header("Telemetry Sources")` + subtitle caption per UX spec / Figma.
  - [ ] 3.3 Info banner: `st.info("Enable categories and individual sources to start collecting telemetry. Custom views allow you to apply Snowflake masking and row-access policies to exported data.")`.
  - [ ] 3.4 For each category, render a collapsible section. **Layout note:** `st.expander` does not support inline widgets in its header label. Use a pattern like `st.columns` above the expander for the toggle + status line, then `st.expander` for the body. Example layout per category:
    ```
    [col1: ○ Distributed Tracing (2/3)] [col2: Enabled [st.toggle]]
    ▼ st.expander body:
       Description text
       st.data_editor table
    ```
  - [ ] 3.5 Pack toggle state: store enabled/disabled per category in `st.session_state` and persist the saved state to `_internal.config` using the real keys `pack_enabled.distributed_tracing` and `pack_enabled.query_performance`. **Default: all toggles OFF** on first load.
  - [ ] 3.6 Toggle OFF behavior: render the `st.data_editor` as **read-only and greyed out** (`disabled=True` on all columns); **preserve existing checkbox states** (do not reset to False); show count `0/{total}`. Toggle ON behavior: make the source table fully interactive; **preserve existing checkbox states** (do not auto-check to True). The category toggle and individual source checkboxes are decoupled: the toggle is a master enable/disable switch, checkboxes represent user selection intent.
  - [ ] 3.7 Count formula: when toggle is ON, `{sum of True polls}/{total}`; when toggle is OFF, `0/{total}`.
  - [ ] 3.8 Status dot: keep the current placeholder status-dot behavior in place for this story. Real health/status semantics arrive later with telemetry source health tracking.

- [ ] **Task 4: Source table with Poll checkbox per category** (AC: 4, 5)
  - [ ] 4.1 **Distributed Tracing** (Event Tables) — `st.data_editor` columns:
    - **Poll** — `st.column_config.CheckboxColumn`, editable.
    - **View name** — `st.column_config.TextColumn`, read-only. Show the full FQN for the Event Table.
    - **Telemetry types** / **Telemetry sources** — hidden in this story because their values are intentionally left empty until a future story computes them from collected telemetry data.
  - [ ] 4.2 **Query Performance & Execution** (ACCOUNT_USAGE views) — `st.data_editor` columns:
    - **Poll** — `st.column_config.CheckboxColumn`, editable.
    - **View name** — `st.column_config.TextColumn`, read-only. Show the full FQN for the validated MVP view (e.g. `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`, `SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY`).
    - No Source type column — there is no universal "source of event" concept across ACCOUNT_USAGE views.
  - [ ] 4.3 Build a pandas DataFrame per category with the columns above. Add a `poll` boolean column. Default all polls to `False`. The poll column reflects the user's explicit selection intent and is **independent of the category toggle state** — enabling a category does not auto-check polls, and disabling a category does not reset polls.
  - [ ] 4.4 Store the edited DataFrame in `st.session_state` (key per category, e.g. `sources_df.distributed_tracing`) so current UI state survives reruns.
  - [ ] 4.5 On every `st.data_editor` change, recalculate the category header count from the `poll` column (only when toggle is ON).
  - [ ] 4.6 Use `hide_index=True`, `use_container_width=True`. Lock read-only columns: for both categories `disabled=["view_name"]` for editable mode, and `disabled=True` for the fully disabled category state.
  - [ ] 4.7 When the category toggle is OFF, render the `st.data_editor` with `disabled=True` (ALL columns locked including Poll — table is visible but greyed out; checkboxes retain their visual state but all sources are functionally disabled). When a source's Poll is unchecked (and category is ON), visually grey out that source's entire row to indicate it won't be polled.

- [ ] **Task 5: Preserve Getting Started drill-down behavior** (AC: 9)
  - [ ] 5.1 Preserve the existing `drilled_from_getting_started` session state flag from Story 2.3 so that the Getting Started → Telemetry Sources drill-down still works.
  - [ ] 5.2 Replace the interim `pack_enabled.dummy` completion mechanism with the real saved controls. Getting Started Task 2 must now derive from the real `pack_enabled.<category>` values, not the dummy key.
  - [ ] 5.3 After a successful save from the drilled-down Getting Started flow, keep the user on the Telemetry Sources page, show save confirmation there, and clear `drilled_from_getting_started` so there is no automatic redirect back to Getting Started.

- [ ] **Task 6: Error handling and loading states** (AC: 1, 9)
  - [ ] 6.1 Wrap discovery queries in try/except; show `st.error` with a user-friendly message if discovery fails (e.g. missing `SNOWFLAKE` database access or insufficient privileges).
  - [ ] 6.2 Use `st.spinner("Discovering telemetry sources...")` while discovery queries execute.
  - [ ] 6.3 If zero sources are discovered, show `st.warning("No telemetry sources found. Ensure the app has the required Snowflake privileges (IMPORTED PRIVILEGES ON SNOWFLAKE DB).")`.

- [ ] **Task 7: Tests** (AC: 1–9)
  - [ ] 7.1 Unit tests for source discovery logic (mock Snowpark session, verify category assignment, custom view detection).
  - [ ] 7.2 Unit tests for category model (definitions, counts, toggle state transitions, poll count recalculation).
  - [ ] 7.3 Unit tests for poll state: default (no saved config) resolves to all polls false regardless of pack state, saved source-poll config is restored independently of the category toggle state, and `resolve_saved_poll_states` returns saved values (defaulting to False for unknown sources).
  - [ ] 7.4 Unit tests for Event Table discovery: discovered Event Tables use full FQNs, and `telemetry_types` / `telemetry_sources` intentionally default to empty strings.
  - [ ] 7.5 Unit tests for custom view detection: custom views referencing supported `SNOWFLAKE.ACCOUNT_USAGE.<VIEW_NAME>` objects are included, unsupported `ACCOUNT_USAGE` views are excluded, and views over discovered Event Tables are categorized as Distributed Tracing.
  - [ ] 7.6 Integration test concept: verify discovery queries run against the dev account without error.

## Dev Notes

### Architecture compliance

- **Streamlit version:** Target 1.52.2 on Snowflake Warehouse Runtime.
- **Session:** Use `get_active_session()` via `utils.snowflake.get_session()` — already established in the project.
- **State management:** `st.session_state` remains the live UI source of truth, and saved pack/poll state is persisted to `_internal.config` in this story so Getting Started Task 2 reflects the real controls.
- **Caching:** The project uses `@st.cache_resource` for session (`utils/snowflake.py`). Follow that pattern. Avoid `@st.cache_data` for discovery queries — SiS caches are single-session only and discovery results may change between page loads. Cache the session, not the data.
- **Config key conventions:** Persist real pack state to `pack_enabled.distributed_tracing` / `pack_enabled.query_performance`. Persist per-source poll state using `source.<slug>.view_fqn` plus `source.<slug>.poll`, where `<slug>` is a config-safe normalization of the source FQN.

### Permission model for source discovery (validated against Snowflake docs, live SQL, and telemetry source research on 2026-03-27)

#### MVP source strategy

- **Distributed Tracing** uses Event Tables.
- **Performance Pack** uses `SNOWFLAKE.ACCOUNT_USAGE` views as the MVP exported source of record.
- `INFORMATION_SCHEMA` table functions are intentionally **out of scope** for selectable MVP telemetry sources in this story. They remain a possible future diagnostic supplement, but not part of the baseline export model due to shorter retention, row limits, and Native App privilege complexity.

#### What `IMPORTED PRIVILEGES ON SNOWFLAKE DB` grants

When a consumer runs `GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO APPLICATION <app>`, the app inherits all 4 SNOWFLAKE database roles:

| Database Role | Grants access to |
|--------------|-----------------|
| `OBJECT_VIEWER` | `ACCOUNT_USAGE.TABLES`, `ACCOUNT_USAGE.VIEWS`, `ACCOUNT_USAGE.COLUMNS`, `ACCOUNT_USAGE.DATABASES`, etc. |
| `USAGE_VIEWER` | Usage/cost/history views |
| `GOVERNANCE_VIEWER` | `QUERY_HISTORY`, `ACCESS_HISTORY`, masking/row-access policies, etc. |
| `SECURITY_VIEWER` | `ROLES`, `USERS`, `GRANTS_TO_ROLES`, login history, etc. |

This is the **default documented MVP path** and is sufficient for all discovery queries in this story. No additional privileges are needed for metadata discovery.

**Future hardening option:** Snowflake also supports granting database roles directly to an application via `GRANT DATABASE ROLE ... TO APPLICATION ...`, but the Native App manifest/request-flow documentation is clearer for `IMPORTED PRIVILEGES` than for specific `SNOWFLAKE` database roles. Keep Story 3.1 on the simpler documented path.

**Important for future stories (Epic 5/6):** To actually **read data** from discovered event tables, the app will need `references` in `manifest.yml` so the consumer can bind specific tables. This is NOT needed for Story 3.1 (discovery/display only).

#### What does NOT work from a Native App

| Command | Why it fails |
|---------|-------------|
| `SHOW EVENT TABLES IN ACCOUNT` | Only returns tables the app role has explicit object-level privileges on — IMPORTED PRIVILEGES does not grant object-level access to consumer tables |
| `SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT` | Requires ACCOUNTADMIN — a Native App cannot be granted ACCOUNTADMIN |
| `SNOWFLAKE.ACCOUNT_USAGE.EVENT_TABLES` | Does not exist as a view (verified: "Object does not exist" error) |
| `INFORMATION_SCHEMA.VIEWS` (unqualified) | Database-scoped; fails without `USE DATABASE`; not viable for cross-database discovery |
| `INFORMATION_SCHEMA.EVENT_TABLES` (unqualified) | Database-scoped; same problem |
| `INFORMATION_SCHEMA` table functions as MVP export sources | Out of scope for Story 3.1 and MVP baseline source selection due to short retention, 10,000-row limits on key functions, missing `LOCK_WAIT_HISTORY` equivalent, and Native App restricted-caller-rights / privilege complexity |

### Source discovery SQL — validated against LFB71918 on 2026-03-26

All queries below were tested live. They rely solely on `IMPORTED PRIVILEGES ON SNOWFLAKE DB` (already in `manifest.yml`) and work within a Native App consumer context.

#### 1. Event Table discovery

```sql
-- Account-wide via ACCOUNT_USAGE (OBJECT_VIEWER role). No USE DATABASE needed.
-- Up to 45-min latency — acceptable for UI discovery.
-- TABLE_TYPE is 'EVENT TABLE' (two words, verified).
SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME
FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
WHERE TABLE_TYPE = 'EVENT TABLE'
  AND DELETED IS NULL
ORDER BY TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME;
```

Verified result (7 event tables on dev account):

| TABLE_CATALOG | TABLE_SCHEMA | TABLE_NAME |
|--------------|-------------|------------|
| HEALTHCARE_DB | OBSERVABILITY | TEST_EVENTS |
| SNOWFLAKE | LOCAL | AI_OBSERVABILITY_EVENTS |
| SNOWFLAKE | LOCAL | CORTEX_ANALYST_REQUESTS_RAW |
| SNOWFLAKE | LOCAL | DATA_QUALITY_MONITORING_RESULTS_RAW |
| SNOWFLAKE | LOCAL | PROFILER_EVENTS_RAW |
| SNOWFLAKE | TELEMETRY | DEFAULT_NOTIFIABLE_EVENTS |
| SNOWFLAKE | TELEMETRY | EVENTS |

#### 2. Active account event table

`SNOWFLAKE.TELEMETRY.EVENTS` is the well-known default active account event table and will appear in the discovery results from query 1. Do NOT give it special UI treatment (no bold, no "default" label) — display it uniformly with all other event tables as a full FQN. `SHOW PARAMETERS` is not available to Native Apps — do not attempt it.

#### 3. ACCOUNT_USAGE view validation

```sql
-- Confirms which of our validated MVP Performance Pack views exist in the SNOWFLAKE DB.
SELECT TABLE_NAME
FROM SNOWFLAKE.INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'ACCOUNT_USAGE'
  AND TABLE_TYPE = 'VIEW'
  AND TABLE_NAME IN (
    'QUERY_HISTORY',
    'TASK_HISTORY',
    'COMPLETE_TASK_GRAPHS',
    'LOCK_WAIT_HISTORY'
  )
ORDER BY TABLE_NAME;
```

All 4 views confirmed present.

#### 4. Custom view discovery

```sql
-- Account-wide scan via ACCOUNT_USAGE (OBJECT_VIEWER role).
SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, VIEW_DEFINITION
FROM SNOWFLAKE.ACCOUNT_USAGE.VIEWS
WHERE DELETED IS NULL
  AND TABLE_CATALOG != 'SNOWFLAKE'
  AND VIEW_DEFINITION IS NOT NULL
ORDER BY TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME;
```

Verified: `VIEW_DEFINITION` is populated and parseable. Match only against the validated MVP `ACCOUNT_USAGE` views and the set of discovered Event Tables.

#### Error handling for missing privileges

If the consumer has not granted `IMPORTED PRIVILEGES ON SNOWFLAKE DB`, all ACCOUNT_USAGE queries fail. Detect with a single try/except around the first discovery query and show:
```python
st.error("Please grant IMPORTED PRIVILEGES ON SNOWFLAKE DB to the application to enable source discovery.")
```

### st.data_editor usage — different schemas per category

**Distributed Tracing (Event Tables):**
```python
import pandas as pd

df_et = pd.DataFrame([
    {"poll": True, "view_name": "SNOWFLAKE.TELEMETRY.EVENTS"},
    {"poll": True, "view_name": "HEALTHCARE_DB.OBSERVABILITY.TEST_EVENTS"},
])

edited_df = st.data_editor(
    df_et,
    column_config={
        "poll": st.column_config.CheckboxColumn("Poll", default=True),
        "view_name": st.column_config.TextColumn("View name"),
    },
    disabled=["view_name"],
    hide_index=True,
    use_container_width=True,
    key="sources_editor_distributed_tracing",
)
```

**Query Performance & Execution (ACCOUNT_USAGE views):**
```python
df_au = pd.DataFrame([
    {"poll": True, "view_name": "SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY"},
    {"poll": True, "view_name": "SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY"},
    {"poll": False, "view_name": "SNOWFLAKE.ACCOUNT_USAGE.LOCK_WAIT_HISTORY"},
])

edited_df = st.data_editor(
    df_au,
    column_config={
        "poll": st.column_config.CheckboxColumn("Poll", default=True),
        "view_name": st.column_config.TextColumn("View name"),
    },
    disabled=["view_name"],
    hide_index=True,
    use_container_width=True,
    key="sources_editor_query_performance",
)
```

Key `st.data_editor` behaviors to handle:
- The returned `edited_df` reflects user edits. Store or reconstruct effective poll values from session state so edits survive reruns.
- Use a unique `key` per category to avoid widget key collisions.
- When category toggle is OFF, render with `disabled=True` (all columns locked, table greyed out, all Poll values false).
- When a source's Poll is unchecked (category ON), its entire row should appear visually dimmed. This can be achieved via row styling or conditional rendering.

### Event Table metadata notes

See `_bmad-output/planning-artifacts/snowflake-event-tables-design.md` for full specification.

**Telemetry types** — derived from `RECORD_TYPE` values in the event table:
- `LOG` → `Logs`, `SPAN`/`SPAN_EVENT` → `Traces`, `METRIC` → `Metrics`, `EVENT` → `Events`
- Determining these values requires querying row contents from each Event Table. That is intentionally deferred because it is too expensive for this story's page load path.
- For Story 3.1, keep `telemetry_types` as `""` and hide the column whenever the category contains no populated values.

**Telemetry sources** — derived from `RESOURCE_ATTRIBUTES` in the event table:
- Normalized to: `Stored procedures`, `Functions`, `SQL queries`, `Streamlit apps`, `SnowServices`, `Dynamic tables`, `Iceberg refresh`, `Native Apps`
- Detection priority: `snow.executable.type` first, then `snow.app.*` attributes, then Iceberg-specific keys
- As with telemetry types, keep this field empty in Story 3.1 and hide the column until a later story computes real values.

### Category toggle + expander layout pattern

`st.expander` does not support inline widgets in its header. Use `st.columns` for the status/toggle row, followed by `st.expander` for the collapsible body:

```python
for cat in categories:
    col_label, col_toggle = st.columns([4, 1])
    with col_label:
        total = len(sources[cat.key])
        count = poll_count(cat) if is_enabled(cat) else 0
        st.markdown(f"○ **{cat.name}** ({count}/{total})")
    with col_toggle:
        # Default OFF — user must explicitly enable
        enabled = st.toggle("Enabled", key=f"pack_enabled.{cat.key}", value=False)

    with st.expander(f"{cat.name} sources", expanded=enabled):
        st.caption(cat.description)
        # Always render st.data_editor — disabled=True when toggle OFF
        readonly_cols = (
            ["view_name", "collection", "telemetry_types", "telemetry_sources"]
            if cat.source_family == "event_table"
            else ["view_name"]
        )
        edited_df = st.data_editor(
            df, ...,
            disabled=True if not enabled else readonly_cols,
            key=f"sources_editor_{cat.key}",
        )
```

This pattern keeps the toggle always visible, always renders the source table, and allows the page to swap between disabled/all-false and enabled/all-true category defaults.

### UX/UI specifications (from Figma and UX spec)

**Page header:**
- Title: "Telemetry Sources"
- Subtitle: "Configure monitoring packs and select data sources from Event Tables and ACCOUNT_USAGE views. Set polling intervals and batch sizes for each source."

**Info banner:** `st.info("Enable categories and individual sources to start collecting telemetry. Custom views allow you to apply Snowflake masking and row-access policies to exported data.")`

**Category header pattern (per UX spec §4b and Figma):**
```
ENABLED CATEGORY — Distributed Tracing (toggle ON):
○ Distributed Tracing (2/3)                              Enabled [toggle=ON]
▼ Distributed Tracing sources
   Capture and correlate execution events from...
   ┌──────┬──────────────────────────────────────────────┐
   │ Poll │ View name                                    │
   ├──────┼──────────────────────────────────────────────┤
   │ ☑    │ SNOWFLAKE.TELEMETRY.EVENTS                   │  ← normal
   │ ☑    │ HEALTHCARE_DB.OBSERVABILITY.TEST_EVENTS      │  ← normal
   │ ☐    │ AI_DB.OBS.PUBLIC.CUSTOM_TRACE_VIEW           │  ← greyed row
   └──────┴──────────────────────────────────────────────┘

ENABLED CATEGORY — Query Performance & Execution (toggle ON):
○ Query Performance & Execution (3/4)                    Enabled [toggle=ON]
▼ Query Performance & Execution sources
   Understand workload patterns and query behavior via ACCOUNT_USAGE views.
   ┌──────┬─────────────────────────┐
   │ Poll │ View name               │
   ├──────┼─────────────────────────┤
   │ ☑    │ SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY        │  ← normal row
   │ ☑    │ SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY         │  ← normal row
   │ ☐    │ SNOWFLAKE.ACCOUNT_USAGE.COMPLETE_TASK_GRAPHS │  ← greyed-out row (unchecked)
   │ ☑    │ SNOWFLAKE.ACCOUNT_USAGE.LOCK_WAIT_HISTORY    │  ← normal row
   └──────┴─────────────────────────┘

DISABLED CATEGORY (toggle OFF — any category):
○ Distributed Tracing (0/3)                              Disabled [toggle=OFF]
▼ Distributed Tracing sources (greyed out, read-only)
   Capture and correlate execution events from...
   ┌──────┬──────────────────────────────────────────────┐
   │ ☐    │ SNOWFLAKE.TELEMETRY.EVENTS                   │  ← all greyed,
   │ ☐    │ HEALTHCARE_DB.OBSERVABILITY.TEST_EVENTS      │    unchecked,
   │ ☐    │ AI_DB.OBS.PUBLIC.CUSTOM_TRACE_VIEW           │    NOT editable
   └──────┴──────────────────────────────────────────────┘
```
- Count when ON: `{sum of checked polls}/{total}`. Count when OFF: `0/{total}`.
- Toggle: `st.toggle` per category. Default OFF on first load. Toggle label shows "Disabled" when OFF per Figma.
- Unchecked source rows: visually greyed out (entire row dimmed) when category is ON.
- Disabled category: entire table greyed out, all columns locked, all Poll values false.

**Column schemas differ by category:**
- **Distributed Tracing**: Poll, View name
- **Query Performance & Execution**: Poll, View name

**Footer:** "You have unsaved changes." + "Reset to defaults" + "Save configuration"

### Category definitions (from UX spec §4a)

**1. Distributed Tracing**
- Description: "Capture and correlate execution events from functions, procedures, tasks, and custom services."
- Sources: Event Table-based (active account event table, task execution events in event table, native app event tables, other discovered event tables, custom trace views on event tables).

**2. Query Performance & Execution**
- Description: "Understand workload patterns and query behavior via ACCOUNT_USAGE views."
- Sources: `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`, `SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY`, `SNOWFLAKE.ACCOUNT_USAGE.COMPLETE_TASK_GRAPHS`, `SNOWFLAKE.ACCOUNT_USAGE.LOCK_WAIT_HISTORY`, plus custom views referencing them.

### What this story does NOT implement (scope boundaries)

| Feature | Implemented in |
|---------|---------------|
| Per-source interval/overlap/batch editing | Story 3.2 |
| Default vs custom source selection dropdown | Story 3.2 |
| Health columns (Freshness, Recent runs, Errors) | Epic 7 (Story 7.3) |
| Status dot colors (green/amber/red) from health data | Epic 7 |

### Previous story intelligence (Story 2.3)

Key patterns and decisions from the last story that apply here:

1. **Config loading pattern:** Use `utils/config.py` `load_config()` and `load_config_like()` for reading config. Parameterized SQL with `session.sql(params=[...])`.
2. **Session state initialization:** Initialize all session state keys before widget calls (top-of-file pattern). Use `if "key" not in st.session_state:` guards.
3. **Drill-down from Getting Started:** The `drilled_from_getting_started` session state flag is established and should be preserved for drill-down tracking only. Do **not** automatically redirect back to Getting Started after save; keep the user on Telemetry Sources and show confirmation in place.
4. **Real completion signal:** Getting Started Task 2 should now derive from the real saved `pack_enabled.<category>` values rather than the legacy `pack_enabled.dummy` key.
5. **`st.switch_page()` is terminal:** After calling `st.switch_page()`, call `st.stop()` to make control flow explicit.
6. **Snowpark SQL:** Always use `session.sql(query, params=[...]).collect()` for parameterized queries. Never concatenate user input into SQL.
7. **Error handling:** Wrap Snowpark calls in `try/except SnowparkSQLException` and surface with `st.error()`.

### Epic 2 retrospective carry-forward

From the Epic 2 retro, these items are explicitly required for Epic 3:

1. **Replace `pack_enabled.dummy` with real Task 2 completion logic.** Story 3.1 now owns that replacement.
2. **Keep completion state DB-backed, not session-only.** Discovery and poll state can be session-only for now, but when Story 3.3 adds persistence, all completion signals must come from `_internal.config`.
3. **Preserve config-key conventions:** Use dotted key patterns: `pack_enabled.<pack_name>`, `source.<name>.view_fqn`, `source.<name>.poll`.
4. **Validate discovery against real account behavior.** Test the actual SQL against the dev Snowflake account — do not rely on theoretical correctness alone.

### File structure

| File | Purpose |
|------|---------|
| `app/streamlit/pages/telemetry_sources.py` | Replace placeholder with real Telemetry Sources page |
| `app/streamlit/utils/source_discovery.py` | **New** — source discovery queries and category definitions |
| `tests/test_source_discovery.py` | **New** — unit tests for discovery logic and poll state |
| `tests/test_getting_started.py` | Update onboarding completion tests for real pack controls |

### Existing files to be aware of (do not break)

| File | Why |
|------|-----|
| `app/streamlit/main.py` | Navigation, sidebar, CSS — do not modify |
| `app/streamlit/utils/config.py` | Config CRUD — reuse, do not modify |
| `app/streamlit/utils/onboarding.py` | Task completion — do not modify; Task 2 checks `pack_enabled.` prefix |
| `app/streamlit/utils/snowflake.py` | Session helper — reuse |
| `app/streamlit/pages/getting_started.py` | Getting Started hub — do not modify |
| `app/setup.sql` | DDL — no changes needed for this story |

### Project Structure Notes

- Source discovery module goes in `app/streamlit/utils/source_discovery.py` — consistent with existing `utils/config.py` and `utils/onboarding.py`.
- The Telemetry Sources page imports from `utils/source_discovery.py`, `utils/config.py`, `utils/snowflake.py`.
- Tests go in `tests/test_source_discovery.py` and `tests/test_getting_started.py` using `PYTHONPATH=app/python .venv/bin/python -m pytest tests/ -v` (root venv, Python 3.13).

### References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Epic 3, Story 3.1]
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` — §4 Telemetry sources page, §4a Category definitions, §4b Category header pattern, §4c Row layout, §4f Implementation]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — Config key naming, Schema topology, Streamlit page organization, Source discovery]
- [Source: `_bmad-output/planning-artifacts/prd.md` — FR4, FR5, FR6]
- [Source: `_bmad-output/planning-artifacts/telemetry_sources.md` — validated MVP telemetry source guidance]
- [Source: `_bmad-output/planning-artifacts/snowflake-event-tables-design.md` — Event Table list column design: Collection, Telemetry types, Telemetry sources]
- [Source: `_bmad-output/implementation-artifacts/epic-2-retro-2026-03-26.md` — Epic 3 readiness, carry-forward items]
- [Source: `_bmad-output/implementation-artifacts/2-3-persist-destination-config-and-getting-started-hub.md` — Previous story patterns]
- [Source: Figma node 4495:47149 — Telemetry Sources page mockup]

## Dev Agent Record

### Agent Model Used

GPT-5.4

### Debug Log References

- Live Snowflake Native App DOM inspection via Playwright MCP on 2026-03-30 to validate the real `st.data_editor` / `glide-data-grid` structure before implementing unchecked-row dimming.

### Completion Notes List

- Updated Story 3.1 to reflect the agreed UI contract: full FQNs in `View name`, empty Event Table metadata fields hidden until a later story populates them, and real persisted save/reset controls in this story.
- Replaced the interim dummy onboarding completion path with real config-backed pack and per-source poll persistence.
- Tightened custom-view classification so only supported MVP `ACCOUNT_USAGE` views are accepted, while custom views over discovered Event Tables are included in Distributed Tracing.

### File List

- `app/streamlit/pages/telemetry_sources.py`
- `app/streamlit/main.py`
- `app/streamlit/utils/source_discovery.py`
- `app/streamlit/utils/config.py`
- `app/streamlit/utils/onboarding.py`
- `tests/test_source_discovery.py`
- `tests/test_getting_started.py`
- `_bmad-output/implementation-artifacts/3-1-source-discovery-and-pack-toggles.md`
