# Story 1.2: Config and state tables

Status: done

## Story

As a Snowflake administrator (Maya),
I want the app to preserve my configuration and pipeline state in durable Snowflake tables,
So that setup choices, health history, and pipeline progress survive reruns and upgrades.

## Acceptance Criteria

1. **`_internal.config` table exists and accepts key-value data**
   Given setup.sql has been run,
   when the app or Streamlit code writes to `_internal.config`:
   - The table exists with columns `CONFIG_KEY`, `CONFIG_VALUE`, `UPDATED_AT`.
   - Config keys follow the canonical dotted convention: `otlp.*`, `pack_enabled.*`, `source.<name>.*`.
   - Older mixed examples such as `otlp_endpoint` or `source:<name>:view_fqn` are deprecated planning-era artifacts and must not be used.
   - INSERT and UPDATE operations succeed for valid key-value pairs.
   - Duplicate key INSERT is prevented by the primary key constraint.

2. **`_internal.export_watermarks` table exists**
   Given setup.sql has been run,
   when pipeline code writes to `_internal.export_watermarks`:
   - The table exists with columns `SOURCE_NAME`, `WATERMARK_VALUE`, `UPDATED_AT`.
   - One row per source is maintained via primary key on `SOURCE_NAME`.

3. **`_metrics.pipeline_health` table exists**
   Given setup.sql has been run,
   when pipeline code inserts run metrics:
   - The table exists with columns `RUN_ID`, `PIPELINE_NAME`, `SOURCE_NAME`, `METRIC_NAME`, `METRIC_VALUE`, `METADATA`, `RECORDED_AT`.
   - Multiple metric rows per run are supported (one row per metric name per run).

4. **`_staging.stream_offset_log` table exists (empty)**
   Given setup.sql has been run:
   - The table exists in `_staging` and is permanently empty.
   - It is used for the zero-row INSERT stream-advancement pattern in later stories.

5. **All DDL is idempotent**
   When setup.sql is run a second time:
   - No DDL statement fails.
   - Existing data in all four tables is preserved.

6. **Streamlit can read config and health data**
   Given the app_admin role is used by Streamlit:
   - `app_admin` has `USAGE` on `_internal` and `_metrics` schemas.
   - `app_admin` has `SELECT`, `INSERT`, `UPDATE` on `_internal.config` (for Streamlit read/write).
   - `app_admin` has `SELECT` on `_internal.export_watermarks` (for health/freshness display).
   - `app_admin` has `SELECT` on `_metrics.pipeline_health` (for Observability Health page).

## Tasks / Subtasks

- [x] **Task 0: Verify stateful schema visibility from app context** (AC: 5, prerequisite)
  - [x] Do **not** use provider-side `SHOW SCHEMAS IN APPLICATION SPLUNK_OBSERVABILITY_DEV_APP` as the pass/fail check for this story. Story 1.1 already showed that provider-side visibility may expose only `APP_PUBLIC` and `INFORMATION_SCHEMA`.
  - [x] Verify stateful schemas and tables from the installed app context instead: use a Snowsight worksheet opened for the app, or another query path that executes against the installed application database.
  - [x] Treat successful `snow app run --connection dev` execution plus app-context table visibility as the authoritative validation signal.

- [x] **Task 1: Create `_internal.config` table in setup.sql** (AC: 1, 5)
  - [x] Add `CREATE TABLE IF NOT EXISTS _internal.config` DDL after schema creation.
  - [x] Columns: `CONFIG_KEY VARCHAR(256) NOT NULL`, `CONFIG_VALUE VARCHAR(16384)`, `UPDATED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()`.
  - [x] Primary key on `CONFIG_KEY` (prevents duplicate keys).

- [x] **Task 2: Create `_internal.export_watermarks` table in setup.sql** (AC: 2, 5)
  - [x] Add `CREATE TABLE IF NOT EXISTS _internal.export_watermarks` DDL.
  - [x] Columns: `SOURCE_NAME VARCHAR(256) NOT NULL`, `WATERMARK_VALUE TIMESTAMP_LTZ NOT NULL`, `UPDATED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()`.
  - [x] Primary key on `SOURCE_NAME` (one watermark per source).

- [x] **Task 3: Create `_metrics.pipeline_health` table in setup.sql** (AC: 3, 5)
  - [x] Add `CREATE TABLE IF NOT EXISTS _metrics.pipeline_health` DDL.
  - [x] Columns: `RUN_ID VARCHAR(36) NOT NULL`, `PIPELINE_NAME VARCHAR(256) NOT NULL`, `SOURCE_NAME VARCHAR(256) NOT NULL`, `METRIC_NAME VARCHAR(256) NOT NULL`, `METRIC_VALUE NUMBER(38,6)`, `METADATA VARIANT`, `RECORDED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()`.
  - [x] No primary key — append-only metrics store; multiple rows per run (one per metric name).

- [x] **Task 4: Create `_staging.stream_offset_log` table in setup.sql** (AC: 4, 5)
  - [x] Add `CREATE TABLE IF NOT EXISTS _staging.stream_offset_log` DDL.
  - [x] Single column: `_OFFSET_CONSUMED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()`.
  - [x] This table is permanently empty. The zero-row INSERT pattern in Story 5.1 will use: `INSERT INTO _staging.stream_offset_log(_OFFSET_CONSUMED_AT) SELECT CURRENT_TIMESTAMP() FROM <stream> WHERE 0 = 1`. The single-column design is schema-agnostic — it works regardless of the stream's source columns.

- [x] **Task 5: Add grants for app_admin on stateful schemas and tables** (AC: 6)
  - [x] `GRANT USAGE ON SCHEMA _internal TO APPLICATION ROLE app_admin`.
  - [x] `GRANT USAGE ON SCHEMA _metrics TO APPLICATION ROLE app_admin`.
  - [x] `GRANT SELECT, INSERT, UPDATE ON TABLE _internal.config TO APPLICATION ROLE app_admin`.
  - [x] `GRANT SELECT ON TABLE _internal.export_watermarks TO APPLICATION ROLE app_admin`.
  - [x] `GRANT SELECT ON TABLE _metrics.pipeline_health TO APPLICATION ROLE app_admin`.
  - [x] No grants needed on `_staging` — only owner-mode stored procedures access it.

- [x] **Task 6: Validate with `snow app run`** (AC: 1–6)
  - [x] Run `snow app run --connection dev` — app installs, tables created, no errors.
  - [x] Run a second time — idempotent, no DDL errors, no data loss.
  - [x] Verify `_STAGING.STREAM_OFFSET_LOG`: provider-side metadata queries still do not expose `_STAGING`, but a temporary owner-rights procedure `app_public.verify_stream_offset_log()` was added, deployed, called successfully from `snow sql`, and returned `table_exists=true` with `row_count=0`. The helper was then removed from `setup.sql` and a follow-up deploy confirmed it is no longer callable.
  - [x] Verify config round-trip: INSERT `test.key`/`test_value` succeeded, SELECT returned row, UPDATE to `test_value_updated` succeeded, SELECT confirmed update. DELETE correctly denied (no DELETE grant to `app_admin`).
  - [x] Verify grants: Snowsight worksheet SELECT on `_INTERNAL.CONFIG`, `_INTERNAL.EXPORT_WATERMARKS`, `_METRICS.PIPELINE_HEALTH` all succeeded. INSERT and UPDATE on `_INTERNAL.CONFIG` succeeded. DELETE correctly denied.

## Dev Notes

### Architecture compliance

- **Schema topology**: Tables are placed in stateful schemas (`_internal`, `_staging`, `_metrics`) created with `CREATE SCHEMA IF NOT EXISTS` in Story 1.1. These persist across upgrades. [Source: architecture.md § Schema Topology]
- **Naming**: Tables use `snake_case` (`config`, `export_watermarks`, `pipeline_health`, `stream_offset_log`). Columns use `UPPER_CASE` per Snowflake convention (`CONFIG_KEY`, `METRIC_VALUE`, etc.). [Source: architecture.md § Naming Patterns]
- **Config key convention**: Keys follow dotted notation — `otlp.<setting>`, `pack_enabled.<pack_name>`, `source.<source_name>.<setting>`. The `CONFIG_VALUE` column is `VARCHAR(16384)` to accommodate PEM certificate references and serialized JSON config. [Source: architecture.md § Config Table Key Naming]
- **Canonical key format**: The dotted convention above is the only valid format going forward. Older mixed examples such as `otlp_endpoint`, `source:<name>:view_fqn`, and `pack_enabled:<pack_name>` are deprecated planning artifacts and must not be copied into new code or stories. [Source: architecture.md § Config Table Key Naming]
- **Pipeline health metric names**: `rows_collected`, `rows_exported`, `rows_failed`, `export_latency_ms`, `error_count`, `source_lag_seconds`. Stored as individual rows per `(RUN_ID, METRIC_NAME)` pair. [Source: architecture.md § Pipeline Health Metric Names]
- **Watermark design**: One row per enabled `ACCOUNT_USAGE` source. `WATERMARK_VALUE` stores the latest exported timestamp. Updated after successful export. Read with overlap window in Story 5.2. [Source: architecture.md § ACCOUNT_USAGE Pipeline]
- **Stream offset log**: Permanently empty table for zero-row INSERT pattern (V4). Used inside `BEGIN`/`COMMIT` transaction to advance Event Table stream without storing data. [Source: architecture.md § V4]
- **Idempotency**: All DDL uses `CREATE TABLE IF NOT EXISTS`. Existing data is never dropped. `setup.sql` must remain safe for re-execution on every upgrade. [Source: architecture.md § Cross-Cutting Concerns]
- **RBAC**: Grants to `app_admin` for Streamlit access. Owner-mode stored procedures (`EXECUTE AS OWNER`) bypass grants and access tables directly. [Source: architecture.md § V14]

### Critical investigation from Story 1.1

The original Story 1.1 note is no longer current. Latest validation in this account shows:

1. `SHOW SCHEMAS IN APPLICATION SPLUNK_OBSERVABILITY_DEV_APP` returns `APP_PUBLIC`, `INFORMATION_SCHEMA`, `_INTERNAL`, and `_METRICS`.
2. `_STAGING` is still **not** visible from the provider `ACCOUNTADMIN` / `snow sql --connection dev` context.
3. `SHOW TABLES IN SCHEMA SPLUNK_OBSERVABILITY_DEV_APP._STAGING` returns `Object does not exist, or operation cannot be performed.`
4. `SELECT ... FROM SPLUNK_OBSERVABILITY_DEV_APP.INFORMATION_SCHEMA.SCHEMATA/TABLES WHERE ... = '_STAGING'` returns no rows from this context.
5. A temporary owner-rights procedure `app_public.verify_stream_offset_log()` was used to query `_staging.stream_offset_log` from inside the app security boundary; it returned `table_exists=true` and `row_count=0`, proving the table exists and is empty even though provider-side metadata queries cannot see it.

For this story, `_INTERNAL` and `_METRICS` are directly visible from provider-side metadata queries, while `_STAGING` is verified only via an owner-rights app-internal execution path. For future stories, use the same pattern for owner-only objects instead of relying on provider-side `SHOW` or `INFORMATION_SCHEMA`.

### Deferred to later stories

- **Config seed data** — No default config values are inserted. Story 2.3 (persist destination) will write `otlp.endpoint` after a successful connection test; Story 2.1 adds read-only hydration from config in the UI. Story 3.3 will write `pack_enabled.*` and `source.*.*` keys.
- **Pipeline health INSERT logic** — The table is created empty. Story 4.3 (retry/failure handling) and Story 5.1/5.2 (collectors) will insert health metrics via the `record_run_metrics()` pattern.
- **Watermark seed data** — No initial watermarks. Story 6.5 (`ACCOUNT_USAGE` task provisioning) will seed watermark rows for each enabled source.
- **Grants on `_staging`** — Only owner-mode SPs access `_staging.stream_offset_log`. No grants to `app_admin` needed.

### Files to touch

| Path | Action |
|------|--------|
| `app/setup.sql` | Add four `CREATE TABLE IF NOT EXISTS` statements and grants after existing schema DDL. |

### Table schemas reference

**`_internal.config`** — Durable key-value store for app settings:

```sql
CREATE TABLE IF NOT EXISTS _internal.config (
    CONFIG_KEY   VARCHAR(256)   NOT NULL,
    CONFIG_VALUE VARCHAR(16384),
    UPDATED_AT   TIMESTAMP_LTZ  DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_config PRIMARY KEY (CONFIG_KEY)
);
```

Key examples: `otlp.endpoint`, `otlp.pem_secret_ref`, `pack_enabled.distributed_tracing`, `source.query_history.poll_interval_seconds`, `source.query_history.overlap_minutes`, `source.query_history.view_fqn`, `source.query_history.source_type`.

**`_internal.export_watermarks`** — Per-source incremental progress:

```sql
CREATE TABLE IF NOT EXISTS _internal.export_watermarks (
    SOURCE_NAME     VARCHAR(256)   NOT NULL,
    WATERMARK_VALUE TIMESTAMP_LTZ  NOT NULL,
    UPDATED_AT      TIMESTAMP_LTZ  DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_export_watermarks PRIMARY KEY (SOURCE_NAME)
);
```

**`_metrics.pipeline_health`** — Per-run operational metrics (append-only):

```sql
CREATE TABLE IF NOT EXISTS _metrics.pipeline_health (
    RUN_ID        VARCHAR(36)    NOT NULL,
    PIPELINE_NAME VARCHAR(256)   NOT NULL,
    SOURCE_NAME   VARCHAR(256)   NOT NULL,
    METRIC_NAME   VARCHAR(256)   NOT NULL,
    METRIC_VALUE  NUMBER(38, 6),
    METADATA      VARIANT,
    RECORDED_AT   TIMESTAMP_LTZ  DEFAULT CURRENT_TIMESTAMP()
);
```

**`_staging.stream_offset_log`** — Permanently empty, stream advancement:

```sql
CREATE TABLE IF NOT EXISTS _staging.stream_offset_log (
    _OFFSET_CONSUMED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);
```

### Development environment

| Setting | Value |
|---------|-------|
| Snowflake account | `LFB71918` (US West — Oregon) |
| Snowsight URL | https://lfb71918.snowflakecomputing.com |
| Snow CLI connection | `dev` (defined in Snow CLI config) |
| User | `NVOITOV` |
| Role | `ACCOUNTADMIN` |
| Warehouse | `SPLUNK_APP_DEV_WH` |
| Auth | Key-pair — requires `PRIVATE_KEY_PASSPHRASE` env var set before running Snow CLI commands |

**Before running any `snow` commands**, export the passphrase:

```bash
export PRIVATE_KEY_PASSPHRASE='<passphrase from .env or secrets manager>'
```

### Previous Story Intelligence (Story 1.1)

**What was established:**
- `app/manifest.yml` — manifest_version 2, four privileges, three references, zero HEC mentions.
- `app/setup.sql` — `app_admin` role, `app_public` (versioned schema), `_internal` / `_staging` / `_metrics` (stateful schemas), Streamlit placeholder, three callback stubs with grants.
- `snowflake.yml` — artifact mapping for dev package (manifest, setup.sql, README, environment.yml, streamlit/).
- `.gitignore` — includes `output/` for Snow CLI build artifacts.

**Learnings to apply:**
- `snow app run --connection dev` is the deploy-and-test command. Use `--force` flag if you need to override a stuck state.
- **Idempotency is verified by running `snow app run` twice** — no errors on second run.
- `GRANT USAGE ON SCHEMA app_public TO APPLICATION ROLE app_admin` must be re-applied after `CREATE OR ALTER VERSIONED SCHEMA` (grants are implicitly revoked on replace). This is already handled in the existing setup.sql.
- `required_at_setup` for TABLE references was rejected by runtime in this account — documented deviation, not relevant for this story.
- IDE schema lint warnings on `app/manifest.yml` and `snowflake.yml` are caused by local schema files, not Snowflake runtime validation — ignore them.
- Files staged by `snow app run` are visible via `LIST @SPLUNK_OBSERVABILITY_DEV_PKG.STAGE_CONTENT.APP_STAGE`.
- Provider-side metadata queries do not expose every app-internal schema. If a future story depends on an owner-only schema/table such as `_STAGING`, verify it with a temporary `EXECUTE AS OWNER` diagnostic procedure, capture the result, then remove the helper and redeploy.

**Code review action items tracked (from Story 1.1):**
- [L1] `CONSUMER_EVENT_TABLE required_at_setup` — not relevant to this story.
- [L2] Stored Procedures section in README — not relevant to this story.

### setup.sql structure after this story

The new DDL should be appended to the existing `setup.sql` in this order:

1. *(existing)* Application role creation
2. *(existing)* Versioned schema `app_public` + grant
3. *(existing)* Stateful schemas `_internal`, `_staging`, `_metrics`
4. **NEW: Table DDL** — `_internal.config`, `_internal.export_watermarks`, `_metrics.pipeline_health`, `_staging.stream_offset_log`
5. **NEW: Schema grants** — `USAGE` on `_internal` and `_metrics` to `app_admin`
6. **NEW: Table grants** — `SELECT`/`INSERT`/`UPDATE` on config; `SELECT` on watermarks and health
7. *(existing)* Streamlit placeholder
8. *(existing)* Callback stubs + grants

Place the new DDL **after** the schema creation and **before** the Streamlit placeholder, so tables exist before any UI code that might reference them.

### Stream offset log pattern

Snowflake's streams documentation says a stream offset advances only when the stream is used in a committed DML transaction; querying a stream alone does not advance it. The docs also note that you can advance a stream without retaining its rows by inserting from the stream into a temporary table with a filter. We are standardizing on this schema-agnostic variant for the project:

```sql
INSERT INTO _staging.stream_offset_log(_OFFSET_CONSUMED_AT)
SELECT CURRENT_TIMESTAMP()
FROM <stream>
WHERE 0 = 1;
```

This keeps `_staging.stream_offset_log` permanently empty while avoiding any dependency on the stream's source column shape.

### Testing

- **Primary**: `snow app run --connection dev` — app installs, no SQL errors.
- **Idempotency**: Run `snow app run --connection dev` a second time — no DDL errors, no data loss.
- **Table verification** (from installed app context, not provider-side schema inspection):
  ```sql
  SHOW TABLES IN SCHEMA _INTERNAL;
  SHOW TABLES IN SCHEMA _STAGING;
  SHOW TABLES IN SCHEMA _METRICS;
  ```
- **Config round-trip** (via `app_admin` / app context):
  ```sql
  INSERT INTO _internal.config (CONFIG_KEY, CONFIG_VALUE)
  VALUES ('test.key', 'test_value');
  SELECT * FROM _internal.config WHERE CONFIG_KEY = 'test.key';
  UPDATE _internal.config
  SET CONFIG_VALUE = 'test_value_updated'
  WHERE CONFIG_KEY = 'test.key';
  SELECT * FROM _internal.config WHERE CONFIG_KEY = 'test.key';
  ```
- **Optional cleanup**: If you want to remove `test.key`, do it from owner/admin context. `DELETE` is intentionally **not** granted to `app_admin`.
- **Grant verification**: From Streamlit or `app_admin` context, `SELECT * FROM _internal.config` and `SELECT * FROM _metrics.pipeline_health` should succeed.
- No unit tests needed for DDL-only changes.

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 1, Story 1.2]
- [Source: _bmad-output/planning-artifacts/architecture.md — Schema Topology, Naming Patterns, Config Table Key Naming, Pipeline Health Metric Names, Data Architecture (D1), Data Flow (V4)]
- [Source: _bmad-output/implementation-artifacts/1-1-native-app-manifest-and-idempotent-setup.md — Completion Notes, Deferred Items, Code Review Action Items]
- [Source: Snowflake Documentation — Introduction to streams (official docs; verified via Firecrawl scrape during story validation)]
- Snowflake docs: [CREATE TABLE](https://docs.snowflake.com/en/sql-reference/sql/create-table), [Native App setup script](https://docs.snowflake.com/en/developer-guide/native-apps/creating-setup-script)

## Dev Agent Record

### Agent Model Used

gpt-5.3-codex-high

### Debug Log References

- `snow app run --connection dev` succeeded (upgrade completed).
- Second `snow app run --connection dev` succeeded with no deploy drift and no DDL errors (idempotency check).
- Snowflake MCP and Snow CLI JSON checks against `SPLUNK_OBSERVABILITY_DEV_APP` confirm:
  - schemas visible: `APP_PUBLIC`, `INFORMATION_SCHEMA`, `_INTERNAL`, `_METRICS`.
  - tables visible: `_INTERNAL.CONFIG`, `_INTERNAL.EXPORT_WATERMARKS`, `_METRICS.PIPELINE_HEALTH`.
  - expected grants exist on application role `APP_ADMIN` for `_INTERNAL`/`_METRICS` and required tables.
- Information schema confirms column shapes for `CONFIG`, `EXPORT_WATERMARKS`, and `PIPELINE_HEALTH`.
- Snowsight config round-trip verified by user: INSERT 1 row, SELECT returned row, UPDATE 1 row, SELECT confirmed `test_value_updated`, DELETE correctly denied (no DELETE grant).
- Snowsight SELECT on `EXPORT_WATERMARKS` and `PIPELINE_HEALTH` succeeded (empty, no error).
- Latest `snow sql --connection dev` verification shows `_INTERNAL` and `_METRICS` schemas are visible in `SHOW SCHEMAS IN APPLICATION SPLUNK_OBSERVABILITY_DEV_APP`; `_STAGING` is not visible from this context.
- `SHOW TABLES IN SCHEMA SPLUNK_OBSERVABILITY_DEV_APP._STAGING` fails with `Object does not exist, or operation cannot be performed.` and `INFORMATION_SCHEMA` returns no `_STAGING` rows from this context.
- Temporary owner-rights procedure `CALL SPLUNK_OBSERVABILITY_DEV_APP.APP_PUBLIC.VERIFY_STREAM_OFFSET_LOG()` returned `{"schema_name":"_STAGING","table_name":"STREAM_OFFSET_LOG","table_exists":true,"row_count":0}`.
- After removing the helper from `setup.sql` and redeploying, the same `CALL` fails with `Unknown user-defined function`, confirming the diagnostic was removed cleanly.

### Completion Notes List

- Added four `CREATE TABLE IF NOT EXISTS` statements to `app/setup.sql`: `_internal.config`, `_internal.export_watermarks`, `_metrics.pipeline_health`, `_staging.stream_offset_log`.
- Added grants for `app_admin`: `USAGE` on `_internal`/`_metrics`, `SELECT/INSERT/UPDATE` on `config`, `SELECT` on `export_watermarks` and `pipeline_health`. No grants on `_staging` (owner-mode only).
- Verified idempotency: `snow app run --connection dev` succeeded twice with no DDL errors or data loss.
- Verified column shapes via `INFORMATION_SCHEMA.COLUMNS` for all three visible tables.
- Verified `PK_CONFIG` primary key constraint exists via `INFORMATION_SCHEMA.TABLE_CONSTRAINTS`.
- Verified grants via `SHOW GRANTS TO APPLICATION ROLE SPLUNK_OBSERVABILITY_DEV_APP.APP_ADMIN` — all expected permissions present.
- Snowsight config round-trip: INSERT/SELECT/UPDATE/SELECT all succeeded; DELETE correctly denied (confirms grant scope is exact).
- `_STAGING.STREAM_OFFSET_LOG` was conclusively verified with a temporary owner-rights diagnostic procedure that returned `table_exists=true` and `row_count=0`.
- The diagnostic helper was removed immediately after verification and a follow-up deploy confirmed it no longer exists in the app.

### Change Log

- 2026-03-16: Story 1.2 implemented — four config/state tables added to setup.sql with idempotent DDL and app_admin grants.
- 2026-03-16: `_STAGING.STREAM_OFFSET_LOG` verified via temporary owner-rights diagnostic procedure; helper removed after verification.

### File List

- app/setup.sql
- _bmad-output/implementation-artifacts/sprint-status.yaml
- _bmad-output/implementation-artifacts/1-2-config-and-state-tables.md
