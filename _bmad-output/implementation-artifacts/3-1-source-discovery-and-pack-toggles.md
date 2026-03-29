# Story 3.1: Source discovery and pack toggles

Status: ready-for-dev

## Story

As a Snowflake administrator (Maya),
I want to see available Event Tables and ACCOUNT_USAGE views (and custom views that reference them), enable or disable Monitoring Packs, and check/uncheck individual sources,
So that I can choose what telemetry to export without writing SQL.

## Acceptance Criteria

1. **Given** I have the required Snowflake privileges (`IMPORTED PRIVILEGES ON SNOWFLAKE DB`), **When** I open the Telemetry sources page, **Then** the app discovers Event Tables (via `SNOWFLAKE.ACCOUNT_USAGE.TABLES`) and the supported MVP Performance Pack `ACCOUNT_USAGE` views (validated via `SNOWFLAKE.INFORMATION_SCHEMA.TABLES`) plus custom views that reference them (via `SNOWFLAKE.ACCOUNT_USAGE.VIEWS`). `INFORMATION_SCHEMA` table functions are **not** selectable telemetry sources in this story.

2. **Given** the app has discovered sources, **When** I view the Telemetry sources page, **Then** categories (Distributed Tracing, Query Performance & Execution) are shown with collapsible headers, a status dot, and an enable/disable toggle per category.

3. **Given** categories are displayed, **When** I view a category header, **Then** each category shows a count of effectively-polled/total sources (e.g. "2/9") and a description of the category purpose. When the category toggle is OFF, the count is "0/{total}" regardless of checkbox states.

4. **Given** I expand the **Distributed Tracing** category (Event Tables), **Then** I see an editable `st.data_editor` with columns: **Poll** (checkbox, editable), **View name** (text, read-only), **Collection** (text, read-only — account name or database name), **Telemetry types** (text, read-only — Logs/Traces/Metrics/Events), **Telemetry sources** (text, read-only — StoredProc/Function/StreamlitApp/etc.). When a source's Poll is unchecked, its entire row is visually greyed out. **Given** I expand the **Query Performance & Execution** category (ACCOUNT_USAGE views), **Then** I see an editable `st.data_editor` with columns: **Poll** (checkbox, editable) and **View name** (text, read-only) only — no Source type column since there is no universal "source of event" column across ACCOUNT_USAGE views.

5. **Given** a category toggle is ON and I check a source's Poll checkbox, **When** I view the category header, **Then** the count increments (e.g. "3/9"). **When** I uncheck it, the count decrements and that source's row is visually greyed out.

6. **Given** I toggle a category OFF, **When** I view the page, **Then** the status dot is gray, the `st.data_editor` is rendered as **read-only and greyed out** (all columns disabled, but the table and all checkbox states remain visible — nothing is hidden or unchecked), and the count reflects "0/{total}" because no sources in a disabled category are polled.

7. **Given** I toggle a category ON for the **first time**, **When** I view the page, **Then** all Poll checkboxes are checked by default (select-all-on-first-enable), the count shows "{total}/{total}", and the source table is fully interactive. **Given** I toggle a category OFF and then ON again (subsequent toggle), **Then** the user's previous checkbox selections are restored exactly as they were before the toggle-off.

8. **Given** the page loads for the first time, **Then** all category toggles default to OFF (user must explicitly enable each category). All status dots show gray (meaning "awaiting activation" — export has not been activated via Getting Started step 4). Status dots remain gray until export activation is completed in a future story (Epic 6).

9. **Given** the page renders, **Then** the page header shows title "Telemetry Sources" and subtitle per Figma, an `st.info` banner explains how to enable categories and custom views, and a footer area is reserved for future unsaved-changes controls (Story 3.3).

## Tasks / Subtasks

- [ ] **Task 1: Source discovery logic** (AC: 1)
  - [ ] 1.1 Create `app/streamlit/utils/source_discovery.py` with functions to discover Event Tables and the validated MVP Performance Pack `ACCOUNT_USAGE` views. Use account-wide metadata queries that rely on `IMPORTED PRIVILEGES ON SNOWFLAKE DB`. Do **not** discover or expose `INFORMATION_SCHEMA` table functions as selectable sources in this story.
  - [ ] 1.2 Event Table discovery: `SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES WHERE TABLE_TYPE = 'EVENT TABLE' AND DELETED IS NULL`. Derive the **Collection** column from `TABLE_CATALOG`: if `TABLE_CATALOG = 'SNOWFLAKE'` and `TABLE_SCHEMA = 'TELEMETRY'`, show the account name; otherwise show `Database: {TABLE_CATALOG}`. Set `telemetry_types` and `telemetry_sources` to "—" (populated in a future story when SELECT access is available via references). All discovered event tables are treated uniformly — no special labels. Do NOT use `SNOWFLAKE.ACCOUNT_USAGE.EVENT_TABLES` (does not exist) or `INFORMATION_SCHEMA.EVENT_TABLES` (database-scoped).
  - [ ] 1.3 ACCOUNT_USAGE view validation: `SELECT TABLE_NAME FROM SNOWFLAKE.INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'ACCOUNT_USAGE' AND TABLE_TYPE = 'VIEW' AND TABLE_NAME IN (...)` with the validated MVP known list: `QUERY_HISTORY`, `TASK_HISTORY`, `COMPLETE_TASK_GRAPHS`, `LOCK_WAIT_HISTORY`. This query is metadata validation only; it does **not** make `INFORMATION_SCHEMA` table functions part of the MVP source model.
  - [ ] 1.4 Custom view discovery: `SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, VIEW_DEFINITION FROM SNOWFLAKE.ACCOUNT_USAGE.VIEWS WHERE DELETED IS NULL AND TABLE_CATALOG != 'SNOWFLAKE' AND (VIEW_DEFINITION ILIKE '%ACCOUNT_USAGE%' OR ...)`. Do NOT use `INFORMATION_SCHEMA.VIEWS` (database-scoped, fails without `USE DATABASE`). Parse `VIEW_DEFINITION` to assign custom views to the matching source category, but only for the validated MVP source families.
  - [ ] 1.5 Return structured data: list of sources with fields `view_name`, `fqn` (fully qualified name), `category` (Distributed Tracing or Query Performance & Execution), `is_custom` (bool). For Event Tables also include: `collection` (account name or `Database: {TABLE_CATALOG}`), `telemetry_types` (default "—" until SELECT access), `telemetry_sources` (default "—" until SELECT access). No `source_type` tag needed — column schemas differ per category.

- [ ] **Task 2: Category definitions and data model** (AC: 2, 3)
  - [ ] 2.1 Define MVP category constants in `app/streamlit/utils/source_discovery.py` or a shared constants location:
    - **Distributed Tracing**: Event Table-based sources (active account event table, task execution events, native app event tables, other discovered event tables, custom trace views).
    - **Query Performance & Execution**: ACCOUNT_USAGE-based MVP sources (`QUERY_HISTORY`, `TASK_HISTORY`, `COMPLETE_TASK_GRAPHS`, `LOCK_WAIT_HISTORY`) and custom views referencing them.
  - [ ] 2.2 Build a dataclass or NamedTuple for `DiscoveredSource` (view_name, fqn, category, is_custom). For Event Tables, extend with `collection`, `telemetry_types`, `telemetry_sources` (initially "—" for the latter two until SELECT access is available via references).
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
  - [ ] 3.5 Pack toggle state: store enabled/disabled per category in `st.session_state` (keys: `pack_enabled.distributed_tracing`, `pack_enabled.query_performance`). **Default: all toggles OFF** on first load. Do NOT persist to `_internal.config` yet — that is Story 3.3.
  - [ ] 3.6 Toggle OFF behavior: render the `st.data_editor` as **read-only and greyed out** (`disabled=True` on all columns). Do NOT clear or modify checkbox states — the user's selections must be preserved visually. Count shows "0/{total}" because a disabled category means zero effective polls. Toggle ON behavior: **first-time enable** → set all Poll checkboxes to `True`; **subsequent re-enable** → restore the user's previous checkbox selections exactly as they were before the toggle-off. The source table becomes fully interactive.
  - [ ] 3.7 Count formula: when toggle is ON, `{sum of True polls}/{total}`; when toggle is OFF, `0/{total}`.
  - [ ] 3.8 Status dot: gray (○) for all categories — meaning "awaiting activation" (export not yet activated). Green/amber/red come with Epic 7 after export activation.

- [ ] **Task 4: Source table with Poll checkbox per category** (AC: 4, 5)
  - [ ] 4.1 **Distributed Tracing** (Event Tables) — `st.data_editor` columns:
    - **Poll** — `st.column_config.CheckboxColumn`, editable.
    - **View name** — `st.column_config.TextColumn`, read-only. Event table name (e.g. `EVENTS`, `TEST_EVENTS`).
    - **Collection** — `st.column_config.TextColumn`, read-only. Shows where the event table collects from: account name (for `SNOWFLAKE.TELEMETRY.EVENTS`) or database name (for database-scoped event tables). Derive from `TABLE_CATALOG` in discovery results.
    - **Telemetry types** — `st.column_config.TextColumn`, read-only. Comma-separated list of telemetry kinds present: `Logs`, `Traces`, `Metrics`, `Events`. Derived from `RECORD_TYPE` values. Shows "—" until data is accessible (requires SELECT via references in a future story).
    - **Telemetry sources** — `st.column_config.TextColumn`, read-only. Comma-separated normalized source categories: `Stored procedures`, `Functions`, `SQL queries`, `Streamlit apps`, `SnowServices`, `Dynamic tables`, `Iceberg refresh`, `Native Apps`. Derived from `RESOURCE_ATTRIBUTES`. Shows "—" until data is accessible.
  - [ ] 4.2 **Query Performance & Execution** (ACCOUNT_USAGE views) — `st.data_editor` columns:
    - **Poll** — `st.column_config.CheckboxColumn`, editable.
    - **View name** — `st.column_config.TextColumn`, read-only. View name (e.g. `QUERY_HISTORY`, `TASK_HISTORY`).
    - No Source type column — there is no universal "source of event" concept across ACCOUNT_USAGE views.
  - [ ] 4.3 Build a pandas DataFrame per category with the columns above. Add a `poll` boolean column. On first-time category enable, default all polls to `True`. Store a `first_enabled` flag per category in session state to distinguish first-enable from re-enable.
  - [ ] 4.4 Store the edited DataFrame in `st.session_state` (key per category, e.g. `sources_df.distributed_tracing`) so poll state and user edits survive reruns and toggle OFF/ON cycles.
  - [ ] 4.5 On every `st.data_editor` change, recalculate the category header count from the `poll` column (only when toggle is ON).
  - [ ] 4.6 Use `hide_index=True`, `use_container_width=True`. Lock read-only columns: for Distributed Tracing `disabled=["view_name", "collection", "telemetry_types", "telemetry_sources"]`; for Query Performance `disabled=["view_name"]`.
  - [ ] 4.7 When the category toggle is OFF, render the `st.data_editor` with `disabled=True` (ALL columns locked including Poll — table is visible but greyed out, checkbox states preserved). When a source's Poll is unchecked (and category is ON), visually grey out that source's entire row to indicate it won't be polled.

- [ ] **Task 5: Preserve Getting Started drill-down behavior** (AC: 9)
  - [ ] 5.1 Preserve the existing `drilled_from_getting_started` session state flag from Story 2.3 so that the Getting Started → Telemetry Sources drill-down still works.
  - [ ] 5.2 Keep the existing `pack_enabled.dummy` interim completion mechanism working until Story 3.3 replaces it with real completion logic. Do NOT break the Getting Started Task 2 completion — the dummy toggle must still function alongside the new real UI.
  - [ ] 5.3 Place the interim dummy toggle in a clearly separated section (e.g. at the bottom in a collapsible "UAT Controls" expander) so it does not conflict with the real category toggles.

- [ ] **Task 6: Error handling and loading states** (AC: 1, 9)
  - [ ] 6.1 Wrap discovery queries in try/except; show `st.error` with a user-friendly message if discovery fails (e.g. missing `SNOWFLAKE` database access or insufficient privileges).
  - [ ] 6.2 Use `st.spinner("Discovering telemetry sources...")` while discovery queries execute.
  - [ ] 6.3 If zero sources are discovered, show `st.warning("No telemetry sources found. Ensure the app has the required Snowflake privileges (IMPORTED PRIVILEGES ON SNOWFLAKE DB).")`.

- [ ] **Task 7: Tests** (AC: 1–9)
  - [ ] 7.1 Unit tests for source discovery logic (mock Snowpark session, verify category assignment, custom view detection).
  - [ ] 7.2 Unit tests for category model (definitions, counts, toggle state transitions, poll count recalculation).
  - [ ] 7.3 Unit tests for poll state: first-time enable sets all polls true, toggle off preserves checkbox state but count = 0, toggle on again restores previous checkboxes, manual uncheck updates count.
  - [ ] 7.4 Unit tests for Event Table Collection derivation: `SNOWFLAKE.TELEMETRY.*` maps to account name, other `TABLE_CATALOG` values map to `Database: {name}`. Verify `telemetry_types` and `telemetry_sources` default to "—".
  - [ ] 7.5 Unit tests for different column schemas per category: Distributed Tracing has 5 columns, Query Performance has 2 columns.
  - [ ] 7.6 Integration test concept: verify discovery queries run against the dev account without error.

## Dev Notes

### Architecture compliance

- **Streamlit version:** Target 1.52.2 on Snowflake Warehouse Runtime.
- **Session:** Use `get_active_session()` via `utils.snowflake.get_session()` — already established in the project.
- **State management:** `st.session_state` for toggle and poll states; no `_internal.config` writes in this story. Story 3.3 handles persistence.
- **Caching:** The project uses `@st.cache_resource` for session (`utils/snowflake.py`). Follow that pattern. Avoid `@st.cache_data` for discovery queries — SiS caches are single-session only and discovery results may change between page loads. Cache the session, not the data.
- **Config key conventions:** When Story 3.3 persists state, it will use `pack_enabled.distributed_tracing`, `pack_enabled.query_performance`. This story must name session state keys consistently with these future config keys. Per-source poll state will use `source.<fqn>.poll` in Story 3.3.

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

`SNOWFLAKE.TELEMETRY.EVENTS` is the well-known default active account event table and will appear in the discovery results from query 1. Do NOT give it special UI treatment (no bold, no "default" label) — display it uniformly with all other event tables. Its Collection column should show the account name (since it is the account-level event table). `SHOW PARAMETERS` is not available to Native Apps — do not attempt it.

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
  AND (
    VIEW_DEFINITION ILIKE '%ACCOUNT_USAGE%'
    OR VIEW_DEFINITION ILIKE '%QUERY_HISTORY%'
    OR VIEW_DEFINITION ILIKE '%TASK_HISTORY%'
    OR VIEW_DEFINITION ILIKE '%COMPLETE_TASK_GRAPHS%'
    OR VIEW_DEFINITION ILIKE '%LOCK_WAIT_HISTORY%'
    OR VIEW_DEFINITION ILIKE '%TELEMETRY.EVENTS%'
  )
ORDER BY TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME;
```

Verified: VIEW_DEFINITION is populated and parseable. Empty set on dev account (no custom views yet).

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
    {"poll": True, "view_name": "EVENTS", "collection": "Account",
     "telemetry_types": "Logs, Traces, Metrics", "telemetry_sources": "Stored procedures, Functions"},
    {"poll": True, "view_name": "TEST_EVENTS", "collection": "Database: HEALTHCARE_DB",
     "telemetry_types": "—", "telemetry_sources": "—"},
])

edited_df = st.data_editor(
    df_et,
    column_config={
        "poll": st.column_config.CheckboxColumn("Poll", default=True),
        "view_name": st.column_config.TextColumn("View name"),
        "collection": st.column_config.TextColumn("Collection"),
        "telemetry_types": st.column_config.TextColumn("Telemetry types"),
        "telemetry_sources": st.column_config.TextColumn("Telemetry sources"),
    },
    disabled=["view_name", "collection", "telemetry_types", "telemetry_sources"],
    hide_index=True,
    use_container_width=True,
    key="sources_editor_distributed_tracing",
)
```

**Query Performance & Execution (ACCOUNT_USAGE views):**
```python
df_au = pd.DataFrame([
    {"poll": True, "view_name": "QUERY_HISTORY"},
    {"poll": True, "view_name": "TASK_HISTORY"},
    {"poll": False, "view_name": "LOCK_WAIT_HISTORY"},
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
- The returned `edited_df` reflects user edits. Store it in `st.session_state` so edits survive reruns AND toggle OFF/ON cycles.
- Use a unique `key` per category to avoid widget key collisions.
- When category toggle is OFF, render with `disabled=True` (all columns locked, table greyed out but visible — checkbox states preserved as-is).
- When a source's Poll is unchecked (category ON), its entire row should appear visually dimmed. This can be achieved via row styling or conditional rendering.

### Event Table column derivation rules

See `_bmad-output/planning-artifacts/snowflake-event-tables-design.md` for full specification.

**Collection** — derive at discovery time from `TABLE_CATALOG`:
- `SNOWFLAKE.TELEMETRY.EVENTS` → show account name (account-level event table)
- Other event tables → show `Database: {TABLE_CATALOG}` (database-scoped)

**Telemetry types** — derived from `RECORD_TYPE` values in the event table:
- `LOG` → `Logs`, `SPAN`/`SPAN_EVENT` → `Traces`, `METRIC` → `Metrics`, `EVENT` → `Events`
- Requires SELECT access to the event table → show "—" until consumer binds references (future story). Once references are bound, populate by querying `SELECT DISTINCT RECORD_TYPE FROM <event_table>`.

**Telemetry sources** — derived from `RESOURCE_ATTRIBUTES` in the event table:
- Normalized to: `Stored procedures`, `Functions`, `SQL queries`, `Streamlit apps`, `SnowServices`, `Dynamic tables`, `Iceberg refresh`, `Native Apps`
- Detection priority: `snow.executable.type` first, then `snow.app.*` attributes, then Iceberg-specific keys
- Requires SELECT access → show "—" until consumer binds references (future story).

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

This pattern keeps the toggle always visible, always renders the source table (greyed out when disabled), and preserves checkbox states across toggle OFF/ON.

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
   ┌──────┬─────────────┬────────────────┬─────────────────┬──────────────────────┐
   │ Poll │ View name   │ Collection     │ Telemetry types │ Telemetry sources    │
   ├──────┼─────────────┼────────────────┼─────────────────┼──────────────────────┤
   │ ☑    │ EVENTS      │ Account        │ Logs, Traces    │ Stored procs, Funcs  │  ← normal
   │ ☑    │ TEST_EVENTS │ DB: ANALYTICS  │ —               │ —                    │  ← normal
   │ ☐    │ AI_OBS_EVE  │ DB: AI_DB      │ —               │ —                    │  ← greyed row
   └──────┴─────────────┴────────────────┴─────────────────┴──────────────────────┘

ENABLED CATEGORY — Query Performance & Execution (toggle ON):
○ Query Performance & Execution (3/4)                    Enabled [toggle=ON]
▼ Query Performance & Execution sources
   Understand workload patterns and query behavior via ACCOUNT_USAGE views.
   ┌──────┬─────────────────────────┐
   │ Poll │ View name               │
   ├──────┼─────────────────────────┤
   │ ☑    │ QUERY_HISTORY           │  ← normal row
   │ ☑    │ TASK_HISTORY            │  ← normal row
   │ ☐    │ COMPLETE_TASK_GRAPHS    │  ← greyed-out row (unchecked)
   │ ☑    │ LOCK_WAIT_HISTORY       │  ← normal row
   └──────┴─────────────────────────┘

DISABLED CATEGORY (toggle OFF — any category):
○ Distributed Tracing (0/3)                              Disabled [toggle=OFF]
▼ Distributed Tracing sources (greyed out, read-only)
   Capture and correlate execution events from...
   ┌──────┬─────────────┬────────────────┬─────────────────┬──────────────────────┐
   │ ☑    │ EVENTS      │ Account        │ —               │ —                    │  ← all greyed,
   │ ☑    │ TEST_EVENTS │ DB: ANALYTICS  │ —               │ —                    │    preserved,
   │ ☐    │ AI_OBS_EVE  │ DB: AI_DB      │ —               │ —                    │    NOT editable
   └──────┴─────────────┴────────────────┴─────────────────┴──────────────────────┘
```
- Status dot: gray (○) = "awaiting activation" for all categories until export activation (Epic 6). Green/amber/red come with Epic 7.
- Count when ON: `{sum of checked polls}/{total}`. Count when OFF: `0/{total}`.
- Toggle: `st.toggle` per category. Default OFF on first load. Toggle label shows "Disabled" when OFF per Figma.
- Unchecked source rows: visually greyed out (entire row dimmed) when category is ON.
- Disabled category: entire table greyed out, all columns locked, checkbox states preserved.

**Column schemas differ by category:**
- **Distributed Tracing**: Poll, View name, Collection, Telemetry types, Telemetry sources
- **Query Performance & Execution**: Poll, View name (no Source type column)

**Footer:** Reserve space for "You have unsaved changes." + "Reset to defaults" + "Save configuration" (Story 3.3 implements this).

### Category definitions (from UX spec §4a)

**1. Distributed Tracing**
- Description: "Capture and correlate execution events from functions, procedures, tasks, and custom services."
- Sources: Event Table-based (active account event table, task execution events in event table, native app event tables, other discovered event tables, custom trace views on event tables).

**2. Query Performance & Execution**
- Description: "Understand workload patterns and query behavior via ACCOUNT_USAGE views."
- Sources: QUERY_HISTORY, TASK_HISTORY, COMPLETE_TASK_GRAPHS, LOCK_WAIT_HISTORY, plus custom views referencing them.

### What this story does NOT implement (scope boundaries)

| Feature | Implemented in |
|---------|---------------|
| Per-source interval/overlap/batch editing | Story 3.2 |
| Default vs custom source selection dropdown | Story 3.2 |
| Save configuration to `_internal.config` | Story 3.3 |
| Unsaved changes indicator and Save/Reset buttons | Story 3.3 |
| Replace `pack_enabled.dummy` with real Task 2 completion | Story 3.3 |
| Health columns (Freshness, Recent runs, Errors) | Epic 7 (Story 7.3) |
| Status dot colors (green/amber/red) from health data | Epic 7 |

### Previous story intelligence (Story 2.3)

Key patterns and decisions from the last story that apply here:

1. **Config loading pattern:** Use `utils/config.py` `load_config()` and `load_config_like()` for reading config. Parameterized SQL with `session.sql(params=[...])`.
2. **Session state initialization:** Initialize all session state keys before widget calls (top-of-file pattern). Use `if "key" not in st.session_state:` guards.
3. **Drill-down from Getting Started:** The `drilled_from_getting_started` session state flag and redirect-on-completion pattern are established. Preserve this behavior.
4. **Dummy completion toggle:** `pack_enabled.dummy` in `_internal.config` drives Getting Started Task 2 completion. Keep this working; Story 3.3 replaces it.
5. **`st.switch_page()` is terminal:** After calling `st.switch_page()`, call `st.stop()` to make control flow explicit.
6. **Snowpark SQL:** Always use `session.sql(query, params=[...]).collect()` for parameterized queries. Never concatenate user input into SQL.
7. **Error handling:** Wrap Snowpark calls in `try/except SnowparkSQLException` and surface with `st.error()`.

### Epic 2 retrospective carry-forward

From the Epic 2 retro, these items are explicitly required for Epic 3:

1. **Replace `pack_enabled.dummy` with real Task 2 completion logic.** Story 3.1 preserves the dummy; Story 3.3 replaces it. Do not break it here.
2. **Keep completion state DB-backed, not session-only.** Discovery and poll state can be session-only for now, but when Story 3.3 adds persistence, all completion signals must come from `_internal.config`.
3. **Preserve config-key conventions:** Use dotted key patterns: `pack_enabled.<pack_name>`, `source.<name>.view_fqn`, `source.<name>.poll`.
4. **Validate discovery against real account behavior.** Test the actual SQL against the dev Snowflake account — do not rely on theoretical correctness alone.

### File structure

| File | Purpose |
|------|---------|
| `app/streamlit/pages/telemetry_sources.py` | Replace placeholder with real Telemetry Sources page |
| `app/streamlit/utils/source_discovery.py` | **New** — source discovery queries and category definitions |
| `tests/test_source_discovery.py` | **New** — unit tests for discovery logic and poll state |

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
- Tests go in `tests/test_source_discovery.py` using `PYTHONPATH=app/python .venv/bin/python -m pytest tests/ -v` (root venv, Python 3.13).

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

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List
