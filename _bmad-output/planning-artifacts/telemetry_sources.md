# Snowflake telemetry sources for the Native App MVP

Validated on 2026-03-27.

This note validates the earlier Cortex draft against current Snowflake documentation, plus targeted checks with Perplexity MCP, Firecrawl MCP, and Snowflake MCP.

## Bottom line

For the MVP, keep the source strategy as:

- **Distributed Tracing Pack**: use **Event Tables**.
- **Performance Pack**: use **`SNOWFLAKE.ACCOUNT_USAGE` views as the exported source of record**.
- **Do not make `INFORMATION_SCHEMA` table functions the baseline MVP export source**.
- **Do not use a "both by default" model in MVP**. It adds privilege, deduplication, and operator complexity without enough MVP value.

Use `INFORMATION_SCHEMA` only as a **future, optional live supplement** for narrowly scoped in-app diagnostics if we later decide we need sub-hour freshness for operator UX.

## Why this is the right MVP choice

### 1. The MVP Performance Pack needs historical telemetry, not just ultra-fresh telemetry

The PRD positions the Performance Pack as exported telemetry for **query, task, and lock visibility in Splunk**, not just a live Snowflake dashboard. For that use case, **365-day retention** is more valuable than zero-latency access:

- `ACCOUNT_USAGE` historical usage views retain **1 year** of data, but have **45 minutes to 3 hours** of latency depending on view. [Account Usage docs](https://docs.snowflake.com/en/sql-reference/account-usage)
- `INFORMATION_SCHEMA` table functions have **no materialization latency**, but retention is much shorter and varies by function. [Information Schema docs](https://docs.snowflake.com/en/sql-reference/info-schema)

For the specific signals we care about:

| Signal | `ACCOUNT_USAGE` | `INFORMATION_SCHEMA` | MVP recommendation |
|---|---|---|---|
| `QUERY_HISTORY` | 365 days, up to 45 min latency | last 7 days, `RESULT_LIMIT` max 10,000 | Use `ACCOUNT_USAGE` |
| `TASK_HISTORY` | 365 days, up to 45 min latency | past 7 days plus next 8 days, `RESULT_LIMIT` max 10,000 | Use `ACCOUNT_USAGE` |
| `COMPLETE_TASK_GRAPHS` | historical view, up to 45 min latency | past 60 minutes only, `RESULT_LIMIT` max 10,000 | Use `ACCOUNT_USAGE` |
| `LOCK_WAIT_HISTORY` | historical view, 24h latency per Account Usage catalog | no official `INFORMATION_SCHEMA` equivalent | Use `ACCOUNT_USAGE` |

Relevant docs:

- [Account Usage](https://docs.snowflake.com/en/sql-reference/account-usage)
- [`ACCOUNT_USAGE.QUERY_HISTORY`](https://docs.snowflake.com/en/sql-reference/account-usage/query_history)
- [`ACCOUNT_USAGE.TASK_HISTORY`](https://docs.snowflake.com/en/sql-reference/account-usage/task_history)
- [`ACCOUNT_USAGE.COMPLETE_TASK_GRAPHS`](https://docs.snowflake.com/en/sql-reference/account-usage/complete_task_graphs)
- [`ACCOUNT_USAGE.LOCK_WAIT_HISTORY`](https://docs.snowflake.com/en/sql-reference/account-usage/lock_wait_history)
- [`INFORMATION_SCHEMA.QUERY_HISTORY`](https://docs.snowflake.com/en/sql-reference/functions/query_history)
- [`INFORMATION_SCHEMA.TASK_HISTORY`](https://docs.snowflake.com/en/sql-reference/functions/task_history)
- [`INFORMATION_SCHEMA.COMPLETE_TASK_GRAPHS`](https://docs.snowflake.com/en/sql-reference/functions/complete_task_graphs)

### 2. `INFORMATION_SCHEMA` does not cover the MVP signal set cleanly

The Cortex draft was directionally right that `INFORMATION_SCHEMA` is fresher, but it understated the coverage problem:

- `LOCK_WAIT_HISTORY` is an MVP-relevant performance signal and **does not have an official `INFORMATION_SCHEMA` equivalent** in the current docs. [Information Schema docs](https://docs.snowflake.com/en/sql-reference/info-schema)
- `COMPLETE_TASK_GRAPHS` in `INFORMATION_SCHEMA` covers only the **past 60 minutes**, which is too narrow for a durable exported performance dataset. [Function docs](https://docs.snowflake.com/en/sql-reference/functions/complete_task_graphs)
- `TASK_HISTORY` and `QUERY_HISTORY` table functions are capped at **10,000 rows per call**, which is manageable for interactive troubleshooting but much less attractive for a durable export pipeline. [Task history docs](https://docs.snowflake.com/en/sql-reference/functions/task_history), [Query history docs](https://docs.snowflake.com/en/sql-reference/functions/query_history)

Because `LOCK_WAIT_HISTORY` forces `ACCOUNT_USAGE` anyway, an `INFORMATION_SCHEMA`-first MVP would still end up being a mixed-source design.

### 3. The Native App privilege model makes `INFORMATION_SCHEMA` less attractive than it first appears

This is the most important correction to the Cortex draft.

`INFORMATION_SCHEMA` is not "free" or automatically easy inside a Native App:

- Snowflake Native Apps **do not support unrestricted caller's rights**. [Native App restricted caller's rights docs](https://docs.snowflake.com/en/developer-guide/native-apps/restricted-callers-rights)
- If we want an executable to use caller privileges, the consumer must explicitly grant **restricted caller's rights**. [Grant flow docs](https://docs.snowflake.com/en/developer-guide/native-apps/ui-consumer-restricted-callers-rights)
- Access to `INFORMATION_SCHEMA` functions depends on the caller's current privileges, and the required privileges are fragmented:
  - `QUERY_HISTORY`: requires `MONITOR` or `OPERATE` on the relevant user-managed warehouses; task-executed queries also require `MONITOR EXECUTION`. [Docs](https://docs.snowflake.com/en/sql-reference/functions/query_history)
  - `TASK_HISTORY`: requires task-level `OWNERSHIP`, `MONITOR`, or `OPERATE`, or global `MONITOR EXECUTION`. [Docs](https://docs.snowflake.com/en/sql-reference/functions/task_history)
  - `COMPLETE_TASK_GRAPHS` and `CURRENT_TASK_GRAPHS`: same pattern. [Docs](https://docs.snowflake.com/en/sql-reference/functions/complete_task_graphs), [Docs](https://docs.snowflake.com/en/sql-reference/functions/current_task_graphs)
- Accessing consumer objects outside the app generally requires **references**, and references require explicit consumer authorization. [Reference docs](https://docs.snowflake.com/en/developer-guide/native-apps/requesting-refs)

So for a Native App that wants account-wide performance telemetry, `INFORMATION_SCHEMA` usually implies one or more of:

- restricted caller's rights setup,
- object or schema level grants,
- warehouse or task specific privilege management,
- or references to consumer objects.

That is a much heavier UX and security story than "just call the functions".

### 4. `ACCOUNT_USAGE` has the better MVP operator model

`ACCOUNT_USAGE` fits the MVP export pipeline better:

- one consistent source family,
- one consistent watermark/overlap/dedup pattern,
- much better historical value once the data lands in Splunk,
- no need to reconcile a "fast temporary copy" from `INFORMATION_SCHEMA` with a later "durable copy" from `ACCOUNT_USAGE`.

Given that the Distributed Tracing Pack already gives us the low-latency telemetry story through Event Tables, the Performance Pack does not need to also solve sub-minute freshness in MVP.

## Validated corrections to the Cortex draft

The Cortex answer was useful, but these points needed correction or tightening:

### Correct or mostly correct

- `ACCOUNT_USAGE` has much longer retention than `INFORMATION_SCHEMA`. [Account Usage](https://docs.snowflake.com/en/sql-reference/account-usage)
- `INFORMATION_SCHEMA` is much fresher. [Information Schema](https://docs.snowflake.com/en/sql-reference/info-schema)
- A hybrid model can make sense in some cases.

### Needed correction

1. **`INFORMATION_SCHEMA` retention is not uniformly 7 days**

It varies by function:

- `QUERY_HISTORY`: last 7 days. [Docs](https://docs.snowflake.com/en/sql-reference/functions/query_history)
- `TASK_HISTORY`: past 7 days plus next 8 days. [Docs](https://docs.snowflake.com/en/sql-reference/functions/task_history)
- `COMPLETE_TASK_GRAPHS`: past 60 minutes only. [Docs](https://docs.snowflake.com/en/sql-reference/functions/complete_task_graphs)
- Some other functions retain 14 days or 6 months. [Information Schema catalog](https://docs.snowflake.com/en/sql-reference/info-schema)

2. **`INFORMATION_SCHEMA` is not automatically easier for a Native App**

The docs show that Native Apps require restricted caller's rights for caller-privilege execution, and the function privilege requirements are object/global privilege dependent. That is operationally non-trivial. [Restricted caller's rights](https://docs.snowflake.com/en/developer-guide/native-apps/restricted-callers-rights)

3. **`ACCOUNT_USAGE` access is not limited to `IMPORTED PRIVILEGES`**

Snowflake also supports granting **database roles** on the `SNOWFLAKE` database, and a database role can be granted directly to an application. [Grant database role docs](https://docs.snowflake.com/en/sql-reference/sql/grant-database-role), [Account Usage docs](https://docs.snowflake.com/en/sql-reference/account-usage)

4. **`LOCK_WAIT_HISTORY` alone prevents an `INFORMATION_SCHEMA`-only MVP**

There is no official `INFORMATION_SCHEMA` table function for it in the current docs. [Information Schema docs](https://docs.snowflake.com/en/sql-reference/info-schema)

5. **`COMPLETE_TASK_GRAPHS` function is much narrower than the view**

For `INFORMATION_SCHEMA`, it only returns the **past 60 minutes**, not a durable recent history window. [Docs](https://docs.snowflake.com/en/sql-reference/functions/complete_task_graphs)

## What to use in the MVP

### Distributed Tracing Pack

Stay with the current design:

- Use **Event Tables** for Snowflake SQL and Snowpark compute telemetry.
- This remains the low-latency signal path.

### Performance Pack

Use these `ACCOUNT_USAGE` views as the MVP exported telemetry set:

- `QUERY_HISTORY`
- `TASK_HISTORY`
- `COMPLETE_TASK_GRAPHS`
- `LOCK_WAIT_HISTORY`

Optional if they remain in scope for the UI and pack definition:

- `WAREHOUSE_LOAD_HISTORY`
- `QUERY_ACCELERATION_HISTORY`

Live Snowflake MCP validation in the dev account confirmed that these views are present in `SNOWFLAKE.ACCOUNT_USAGE` today:

- `COMPLETE_TASK_GRAPHS`
- `LOCK_WAIT_HISTORY`
- `QUERY_ACCELERATION_HISTORY`
- `QUERY_HISTORY`
- `TASK_HISTORY`
- `WAREHOUSE_LOAD_HISTORY`

## Privilege guidance for MVP

There are two realistic options.

### Option A: simplest documented install/setup path

Request:

- `IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE`

Why this is the best MVP default:

- it is explicitly documented in the Native App privilege request flow,
- it is easy for the consumer to understand and approve,
- it avoids additional manual role grant instructions during MVP onboarding.

Relevant docs:

- [Request global privileges from consumers](https://docs.snowflake.com/en/developer-guide/native-apps/requesting-privs)
- [Allow access to a consumer account](https://docs.snowflake.com/en/developer-guide/native-apps/ui-consumer-granting-privs)

### Option B: least-privilege manual hardening path

If we later want a narrower grant model, the docs support granting database roles directly to an application via `GRANT DATABASE ROLE ... TO APPLICATION ...`. [Docs](https://docs.snowflake.com/en/sql-reference/sql/grant-database-role)

For the current MVP performance view set, the documented role mapping is:

| View | Required `SNOWFLAKE` database role |
|---|---|
| `QUERY_HISTORY` | `GOVERNANCE_VIEWER` |
| `TASK_HISTORY` | `USAGE_VIEWER` |
| `COMPLETE_TASK_GRAPHS` | `OBJECT_VIEWER` |
| `LOCK_WAIT_HISTORY` | `USAGE_VIEWER` |
| `WAREHOUSE_LOAD_HISTORY` | `USAGE_VIEWER` |
| `QUERY_ACCELERATION_HISTORY` | `USAGE_VIEWER` |

So a least-privilege Performance Pack would need at least:

- `GOVERNANCE_VIEWER`
- `USAGE_VIEWER`
- `OBJECT_VIEWER`

Important nuance:

- I found official SQL docs for granting a database role to an application.
- I did **not** find equally clear Native App manifest documentation showing a first-class request flow for specific `SNOWFLAKE` database roles.

Because of that, **Option A (`IMPORTED PRIVILEGES`) is the safer documented MVP path**, while Option B is a good post-MVP tightening path if we are willing to support extra consumer setup.

## Recommended collector behavior

For MVP collectors, align schedules to source latency instead of chasing "real time":

| Source | Suggested cadence | Why |
|---|---|---|
| `QUERY_HISTORY` | every 60 minutes with overlap | source latency is up to 45 minutes |
| `TASK_HISTORY` | every 60 minutes with overlap | source latency is up to 45 minutes |
| `COMPLETE_TASK_GRAPHS` | every 60 minutes with overlap | source latency is up to 45 minutes |
| `LOCK_WAIT_HISTORY` | every 24 hours with overlap | source is much slower and mainly useful for retrospective analysis |

This lines up with the PRD's own NFR framing: `ACCOUNT_USAGE` freshness only needs to be within one polling cycle of the source's inherent latency.

## When `INFORMATION_SCHEMA` becomes worth adding later

Do not use it as the MVP export baseline, but it becomes attractive later if we explicitly want one of these:

- an in-app "live now" diagnostics pane,
- very fresh operator-facing visibility for current or just-finished queries,
- live task graph status via `CURRENT_TASK_GRAPHS`,
- a separate high-freshness troubleshooting mode that we clearly distinguish from the historical export pipeline.

If we add it later, treat it as:

- **supplemental**, not authoritative,
- **UI/diagnostics-oriented**, not the main Splunk export source,
- and guarded by a clearly documented privilege model.

## Final MVP recommendation

For MVP, the cleanest and most defensible design is:

1. **Distributed Tracing Pack**: Event Tables.
2. **Performance Pack**: `ACCOUNT_USAGE` views only.
3. **Privilege model**: start with documented `IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE`.
4. **Future enhancement**: consider selective `INFORMATION_SCHEMA` use only for live diagnostics, not for the baseline export pipeline.

This preserves the current PRD direction and avoids a premature mixed-source design that would add privilege complexity, deduplication logic, and operator confusion without materially improving the MVP outcome.
