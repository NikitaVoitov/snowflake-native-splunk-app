# Native App Warehouse Assignment Guide

**Date:** 2026-04-01  
**Project:** `snowflake-native-splunk-app`  
**Status:** Working reference for planning and implementation

---

## Purpose

This guide consolidates what we confirmed in this project about warehouse assignment for a Snowflake Native App that includes:

- a Streamlit UI,
- stored procedures,
- scheduled tasks,
- and consumer-selected warehouse references.

The goal is to have one document we can rely on when making design and implementation decisions.

---

## Source Hierarchy

Use the following confidence order when this document is referenced later:

1. **Highest confidence:** official Snowflake documentation reviewed during this chat.
2. **High confidence:** live inspection of this repo and installed app metadata.
3. **Supporting context only:** Cortex CLI research output in terminal `2.txt`.

When Cortex output conflicts with official docs, this guide follows the official docs.

---

## Executive Summary

### Confirmed rules

1. **Streamlit in a Native App can run on a warehouse runtime and use `QUERY_WAREHOUSE`.**
   For warehouse runtimes, `QUERY_WAREHOUSE` is the warehouse used to run the Streamlit app code and, unless changed in code, the SQL issued by that app.

2. **If `QUERY_WAREHOUSE` is not set, the Streamlit app uses the consumer session context.**
   In practice, that means the warehouse used by the Streamlit session is driven by the consumer's active session warehouse when they open the app.

3. **Native App warehouse references do not bind directly to Streamlit `QUERY_WAREHOUSE`.**
   Official docs are explicit: Streamlit in a Native App supports `USE WAREHOUSE`, but references to warehouses are not supported for Streamlit warehouse binding.

4. **Streamlit can still switch warehouses at runtime.**
   `USE WAREHOUSE` is supported, which means Streamlit code can move onto a consumer-selected warehouse after startup if the warehouse name is known.

5. **Stored procedures inherit the caller's session warehouse by default.**
   `EXECUTE AS OWNER` and `EXECUTE AS RESTRICTED CALLER` affect privileges, not the fundamental rule that execution uses the calling session's warehouse unless changed.

6. **Tasks can use a warehouse reference directly.**
   Official Native App docs show `CREATE TASK ... WAREHOUSE = reference('consumer_warehouse')` as a supported pattern.

7. **The consumer can choose a warehouse through native Snowsight UI.**
   A `WAREHOUSE` reference declared in `manifest.yml` can be surfaced in Snowsight's Security flow and via the Python Permission SDK.

### Practical implication

The most reliable pattern for "one consumer-chosen warehouse for both UI-triggered backend work and tasks" is:

- declare a `WAREHOUSE` reference in `manifest.yml`,
- let the consumer bind it in native Snowsight UI,
- use `WAREHOUSE = reference('CONSUMER_WAREHOUSE')` for tasks,
- and have Streamlit read the bound warehouse name and call `session.use_warehouse(...)` early in app startup.

This avoids relying on unsupported direct binding from `reference(...)` into `QUERY_WAREHOUSE`.

---

## Current Project State

### What this repo currently does

- `app/manifest.yml` defines a `CONSUMER_WAREHOUSE` reference:
  - object type: `WAREHOUSE`
  - privileges: `USAGE`, `OPERATE`
  - callback: `app_public.register_single_callback`

- `app/setup.sql` creates the Streamlit object **without** `QUERY_WAREHOUSE`:

```sql
CREATE OR REPLACE STREAMLIT app_public.main
    FROM '/streamlit'
    MAIN_FILE = '/main.py'
    TITLE = 'Splunk Observability';
```

- `app/setup.sql` already documents the key limitation:
  - warehouse references are not supported as Streamlit `QUERY_WAREHOUSE` bindings.
  - the Streamlit app uses consumer session context and can issue `USE WAREHOUSE` at runtime if needed.

- The current callback procedure only performs reference registration:

```sql
SELECT SYSTEM$SET_REFERENCE(:ref_name, :ref_or_alias);
```

### What that means today

- The Streamlit UI is **not pinned** to one warehouse.
- The UI uses the consumer's active session warehouse unless app code later switches it.
- The manifest reference is useful for:
  - native Snowsight warehouse selection,
  - tasks using `reference('CONSUMER_WAREHOUSE')`,
  - and any app logic that needs to resolve the consumer-selected warehouse name.

---

## Officially Confirmed Behavior

## 1. Streamlit

### 1.1 `QUERY_WAREHOUSE`

For warehouse runtime Streamlit:

- `QUERY_WAREHOUSE` sets the warehouse used to run the app code.
- If the app does not switch warehouses inside Python, the same warehouse is used for queries.

This is standard Snowflake Streamlit behavior and applies to Native Apps as well.

### 1.2 Warehouse references are not supported for Streamlit binding

This is the most important rule for this project:

- Streamlit in a Native App supports `USE WAREHOUSE`.
- Streamlit in a Native App does **not** support warehouse references as a direct binding mechanism for Streamlit warehouse selection.

So this is **not** a supported design:

```sql
CREATE STREAMLIT app_public.main
  FROM '/streamlit'
  MAIN_FILE = '/main.py'
  QUERY_WAREHOUSE = reference('CONSUMER_WAREHOUSE');
```

Treat that as unsupported.

### 1.3 Runtime switching is supported

Inside Streamlit, the app can switch warehouse after startup:

```python
session = get_active_session()
session.use_warehouse("MY_WAREHOUSE")
```

This is the supported bridge between:

- "consumer chose a warehouse through Native App reference UI"
- and "Streamlit should actually run its work on that warehouse".

### 1.4 Session-context fallback

If `QUERY_WAREHOUSE` is unset and the app does not call `USE WAREHOUSE`, Streamlit uses consumer session context.

Operationally this means:

- different consumers can hit different warehouses,
- the same consumer can hit different warehouses across sessions,
- and warehouse behavior is not deterministic unless the app actively controls it.

---

## 2. Stored Procedures

### 2.1 Warehouse comes from the caller session

For Native App stored procedures:

- the warehouse normally comes from the calling session,
- while `EXECUTE AS OWNER` or `EXECUTE AS RESTRICTED CALLER` controls privileges.

This matters because:

- a procedure called from Streamlit inherits the Streamlit session warehouse,
- a procedure called from a task inherits the task warehouse.

### 2.2 `EXECUTE AS OWNER` vs `EXECUTE AS RESTRICTED CALLER`

Important distinction:

- **`EXECUTE AS OWNER`**
  - uses application-owner privileges,
  - but does not magically choose a different warehouse.

- **`EXECUTE AS RESTRICTED CALLER`**
  - uses filtered caller privileges,
  - but still operates within caller-session warehouse context.

For warehouse planning, focus first on the **caller session**, then separately on the privilege model.

### 2.3 Implication for this app

If Streamlit switches to a consumer-selected warehouse using `session.use_warehouse(...)`, then:

- UI-triggered SQL runs there,
- UI-triggered `CALL ...` runs there,
- and the invoked procedure inherits that warehouse.

---

## 3. Tasks

### 3.1 Official supported pattern

Official Native App docs include this supported syntax:

```sql
CREATE TASK app_task
  WAREHOUSE = reference('consumer_warehouse')
  ...;

ALTER TASK app_task SET WAREHOUSE = reference('consumer_warehouse');
```

This is important because earlier Cortex output suggested task warehouse references must be resolved manually in dynamic SQL. Official docs are stronger than that claim, so this guide treats direct task usage of `reference(...)` as supported.

### 3.2 Serverless tasks are still an option

Instead of using a warehouse reference, tasks can run serverlessly when that better fits the design:

- requires `EXECUTE MANAGED TASK`,
- avoids warehouse binding complexity,
- but does not align compute with the consumer's chosen warehouse.

### 3.3 Implication for this app

If the requirement is "tasks should run on the same consumer-selected warehouse", the clean task-side implementation is:

```sql
CREATE OR REPLACE TASK ...
  WAREHOUSE = reference('CONSUMER_WAREHOUSE')
  ...
```

No extra warehouse-name resolution layer should be added unless a platform limitation is observed in live testing.

---

## 4. Consumer Selection via Native Snowsight UI

### 4.1 What the consumer sees

Because `CONSUMER_WAREHOUSE` is defined in `manifest.yml`, the consumer can select a warehouse through native Snowflake UI:

- in the Security tab / approval flow,
- or through a Streamlit onboarding page that uses the Python Permission SDK.

### 4.2 Permission SDK functions that matter

The key supported APIs are:

- `permissions.request_reference("CONSUMER_WAREHOUSE")`
- `permissions.get_reference_associations("CONSUMER_WAREHOUSE")`
- `permissions.get_detailed_reference_associations("CONSUMER_WAREHOUSE")`

The detailed association API is especially useful because it returns structured info, including the chosen object `name`.

That gives Streamlit a supported way to learn the chosen warehouse name, then switch to it.

### 4.3 What this does not do automatically

Binding the warehouse reference in Snowsight does **not** automatically set Streamlit `QUERY_WAREHOUSE`.

That is the gap this project must account for explicitly.

---

## Recommended Patterns

## Option A: Simplest operational model

### Pattern

- Streamlit uses consumer session warehouse.
- Tasks use serverless compute.

### Pros

- Minimal setup.
- No extra warehouse switching logic.
- Works well for MVP and lower operational complexity.

### Cons

- UI and tasks do not share the same compute model.
- Warehouse behavior depends on consumer session state.
- Harder to reason about cost and performance consistently.

### When to choose it

- MVP,
- low task volume,
- low sensitivity to warehouse alignment,
- fast path to production.

---

## Option B: Single consumer-selected warehouse for everything

### Pattern

1. Consumer binds `CONSUMER_WAREHOUSE` through native Snowsight UI.
2. Streamlit reads the bound warehouse name using the Permission SDK.
3. Streamlit calls `session.use_warehouse(chosen_name)` very early.
4. Tasks use `WAREHOUSE = reference('CONSUMER_WAREHOUSE')`.

### Pros

- Single consumer-chosen warehouse for:
  - Streamlit queries,
  - UI-triggered procedure calls,
  - background tasks.
- Consumer retains control over size/cost/policy.
- Uses supported primitives end-to-end.

### Cons

- Slightly more initialization logic in Streamlit.
- Initial app startup before the switch still begins in consumer session context.
- Requires the warehouse reference to be bound before the app fully behaves as intended.

### Recommended implementation sketch

```python
import snowflake.permissions as permissions
from snowflake.snowpark.context import get_active_session

def activate_consumer_warehouse() -> str | None:
    session = get_active_session()
    refs = permissions.get_detailed_reference_associations("CONSUMER_WAREHOUSE")
    if refs:
        wh_name = refs[0].get("name")
        if wh_name:
            session.use_warehouse(wh_name)
            return wh_name
    return None
```

Task side:

```sql
CREATE OR REPLACE TASK ...
  WAREHOUSE = reference('CONSUMER_WAREHOUSE')
  ...
```

### When to choose it

- when "same warehouse for UI and backend" is a real requirement,
- when the consumer should choose the warehouse,
- and when we want a documented, supportable pattern.

---

## Option C: Manual persistent `QUERY_WAREHOUSE`

### Pattern

After install, a consumer admin manually runs:

```sql
ALTER STREAMLIT <app>.<schema>.<streamlit_name>
  SET QUERY_WAREHOUSE = <warehouse_name>;
```

Tasks can still use `reference('CONSUMER_WAREHOUSE')` or serverless compute.

### Pros

- Fully supported SQL operation.
- Streamlit object is explicitly pinned.

### Cons

- Not automatically driven by the Native App reference flow.
- Requires manual admin SQL or a separate automation step.
- Still needs coordination with task warehouse design.

### When to choose it

- platform admin controlled deployments,
- internal deployments where post-install SQL steps are acceptable.

---

## Patterns We Should Not Rely On

## 1. Direct Streamlit reference binding

Do **not** rely on:

```sql
QUERY_WAREHOUSE = reference('CONSUMER_WAREHOUSE')
```

That is unsupported for Streamlit in Native Apps.

## 2. Manual dynamic task warehouse resolution as the default design

Cortex research suggested tasks must dynamically resolve warehouse names and recreate tasks with raw warehouse strings.

Official docs show a simpler supported syntax:

```sql
WAREHOUSE = reference('consumer_warehouse')
```

Therefore, dynamic SQL should be treated as a fallback only if live testing exposes a limitation.

## 3. Assuming owner-rights procedures imply owner-selected warehouse

`EXECUTE AS OWNER` controls privileges, not warehouse selection. Do not design around the assumption that owner-rights procedures magically move work onto an app-owned warehouse.

## 4. Assuming Streamlit is deterministically pinned when `QUERY_WAREHOUSE` is unset

If we do nothing, Streamlit follows consumer session context. That is functional, but not deterministic.

---

## Recommended Project Decision

For this project, the best supported long-term pattern is:

1. Keep `CONSUMER_WAREHOUSE` in `manifest.yml`.
2. Let the consumer bind it through native Snowsight UI.
3. Use `permissions.get_detailed_reference_associations("CONSUMER_WAREHOUSE")` in Streamlit.
4. Call `session.use_warehouse(...)` near the start of the Streamlit session.
5. Use `WAREHOUSE = reference('CONSUMER_WAREHOUSE')` for tasks.
6. Let stored procedures inherit from whichever context called them:
   - Streamlit session warehouse for UI-triggered calls,
   - task warehouse for scheduled calls.

This gives one consumer-chosen warehouse across the parts of the app that matter operationally, without depending on unsupported direct reference binding for Streamlit.

---

## Validation Checklist for Future Changes

Before changing warehouse behavior, confirm:

- `manifest.yml` still defines `CONSUMER_WAREHOUSE`.
- Streamlit startup code still activates the selected warehouse if that pattern is in use.
- Tasks still use `reference('CONSUMER_WAREHOUSE')` or are intentionally serverless.
- No code assumes `QUERY_WAREHOUSE` can consume a warehouse reference directly.
- Any new stored procedure design separates:
  - privilege model,
  - warehouse model,
  - task invocation model.

---

## Related Project Artifacts

- `app/manifest.yml`
- `app/setup.sql`
- `_bmad-output/planning-artifacts/architecture.md`
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-03-31.md`

Supplementary research context:

- terminal output reviewed from `terminals/2.txt`
- official Snowflake docs on:
  - Native Apps adding Streamlit
  - Native Apps requesting references
  - Native Apps Permission SDK
  - Streamlit runtime environments
  - `CREATE STREAMLIT`
