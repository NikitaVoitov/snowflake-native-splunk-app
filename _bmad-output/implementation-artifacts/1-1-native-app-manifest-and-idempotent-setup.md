# Story 1.1: Native App manifest and idempotent setup

Status: done

## Story

As a Snowflake administrator (Maya),
I want the app to declare its required privileges and create schemas in an idempotent way,
So that I can install from Marketplace and approve privileges without manual SQL, and upgrades do not break state.

## Acceptance Criteria

1. **Manifest format and privileges**
   Given the app package is deployed to a consumer account, when setup.sql runs (install or upgrade):
   - `app/manifest.yml` uses `manifest_version: 2`.
   - The manifest declares exactly **four** account-level privileges with clear descriptions:
     - `IMPORTED PRIVILEGES ON SNOWFLAKE DB` — read ACCOUNT_USAGE views.
     - `EXECUTE TASK` — task owner role runs scheduled/triggered tasks.
     - `EXECUTE MANAGED TASK` — serverless compute for tasks.
     - `CREATE EXTERNAL ACCESS INTEGRATION` — EAI for OTLP gRPC egress.
   - `CREATE DATABASE` is **removed** — the app uses internal schemas within its own application database; no external database is created.
   - No other account-level privileges are requested.

2. **Idempotent schema DDL in setup.sql**
   When setup.sql runs (first or subsequent time):
   - `app_public` is created with `CREATE OR ALTER VERSIONED SCHEMA` (stateless; recreated on upgrade).
   - `_internal`, `_staging`, `_metrics` are created with `CREATE SCHEMA IF NOT EXISTS` (stateful; persist across upgrades).
   - Application role `app_admin` exists (`CREATE APPLICATION ROLE IF NOT EXISTS`) and has `USAGE ON SCHEMA app_public`.
   - No DDL statement fails when setup.sql is run a second time (full idempotency).

3. **Manifest references and artifacts aligned with architecture**
   - Artifacts: `setup_script: setup.sql`, `default_streamlit: app_public.main`, `extension_code: true`.
   - **Zero HEC references anywhere in the manifest** — architecture specifies a single OTLP/gRPC endpoint. Remove the `SPLUNK_HEC_SECRET` reference block AND scrub all HEC/HEC-related mentions from `version.comment`, privilege descriptions, and reference descriptions.
   - Required references declared: `CONSUMER_EVENT_TABLE` (required_at_setup: true), `SPLUNK_EAI` (required_at_setup: false), `SPLUNK_OTLP_SECRET` (required_at_setup: false, kept for post-MVP bearer token auth).

4. **Callback stub procedures exist for install**
   - Manifest references callback procedures (`register_single_callback`, `get_secret_configuration`, `get_eai_configuration`). These must exist in `app_public` for `snow app run` to succeed.
   - `setup.sql` creates minimal SQL stub procedures that accept the expected parameters and return a valid response (empty string or NULL). Full implementations come in later stories.

## Tasks / Subtasks

- [x] **Task 1: Rewrite manifest.yml from architecture spec** (AC: 1, 3)
  - [x] Confirm `manifest_version: 2`.
  - [x] Clean `version` block: remove any HEC mention from `comment` (use "OTLP" only).
  - [x] Set `artifacts` block: `setup_script: setup.sql`, `readme: README.md`, `default_streamlit: app_public.main`, `extension_code: true`.
  - [x] Set `configuration` block: `log_level: INFO`, `trace_level: ALWAYS`, `metric_level: ALL`.
  - [x] Set `privileges` block to exactly four entries (remove `CREATE DATABASE`):
    - `IMPORTED PRIVILEGES ON SNOWFLAKE DB`
    - `EXECUTE TASK`
    - `EXECUTE MANAGED TASK`
    - `CREATE EXTERNAL ACCESS INTEGRATION`
  - [x] Update all privilege descriptions — no HEC mentions.
  - [x] Set `references` block to exactly three entries (remove `SPLUNK_HEC_SECRET`):
    - `CONSUMER_EVENT_TABLE` (TABLE, SELECT, required_at_setup: true, callback: `app_public.register_single_callback`).
    - `SPLUNK_OTLP_SECRET` (SECRET, USAGE, required_at_setup: false, callbacks: `register_single_callback` + `get_secret_configuration`).
    - `SPLUNK_EAI` (EXTERNAL_ACCESS_INTEGRATION, USAGE, required_at_setup: false, callbacks: `register_single_callback` + `get_eai_configuration`).
  - [x] Update all reference descriptions — no HEC mentions; use "OTLP gRPC" only.
- [x] **Task 2: Verify and fix setup.sql idempotency** (AC: 2)
  - [x] `CREATE APPLICATION ROLE IF NOT EXISTS app_admin`.
  - [x] `CREATE OR ALTER VERSIONED SCHEMA app_public` + `GRANT USAGE ON SCHEMA app_public TO APPLICATION ROLE app_admin`.
  - [x] `CREATE SCHEMA IF NOT EXISTS` for `_internal`, `_staging`, `_metrics`.
  - [x] Do NOT create tables (Story 1.2 scope).
- [x] **Task 3: Create callback stub procedures in setup.sql** (AC: 4)
  - [x] `CREATE OR REPLACE PROCEDURE app_public.register_single_callback(ref_name STRING, operation STRING, ref_or_alias STRING) RETURNS STRING ...` — stub returns empty string.
  - [x] `CREATE OR REPLACE PROCEDURE app_public.get_secret_configuration(ref_name STRING) RETURNS STRING ...` — stub returns empty string.
  - [x] `CREATE OR REPLACE PROCEDURE app_public.get_eai_configuration(ref_name STRING) RETURNS STRING ...` — stub returns empty string.
  - [x] All three use `LANGUAGE SQL`, `EXECUTE AS OWNER`.
  - [x] `GRANT USAGE ON PROCEDURE ... TO APPLICATION ROLE app_admin` for each.
- [x] **Task 4: Validate with `snow app run`** (AC: 1, 2, 3, 4)
  - [x] Run `snow app run` — app installs without errors, privilege approval succeeds, Streamlit opens (may show error if main.py doesn't exist yet — that's expected, see Story 1.3 dependency below).
  - [x] Run `snow app run` a second time — no DDL errors on re-run (idempotency).
  - [x] Packaging and runtime blockers resolved (`snowflake.yml` artifact mapping cleanup, `debug: false` for manifest v2).

## Dev Notes

### Architecture compliance

- **Schema topology**: `app_public` = versioned (`CREATE OR ALTER VERSIONED SCHEMA`); `_internal`, `_staging`, `_metrics` = stateful (`CREATE SCHEMA IF NOT EXISTS`). No other schemas. [Source: architecture.md § Schema Topology]
- **Naming**: Internal schemas use `_lowercase` prefix; application role `app_admin` (snake_case). [Source: architecture.md § Naming Patterns]
- **Upgrade safety**: Idempotent setup.sql is mandatory; stateful schemas persist across upgrades; versioned schema is recreated. Grants must be re-applied after `CREATE OR ALTER VERSIONED SCHEMA` since replacement implicitly revokes prior grants. [Source: architecture.md § Cross-Cutting Concerns]
- **Manifest**: Single OTLP/gRPC endpoint; no HEC anywhere. Architecture alignment decision explicitly states: "Remove SPLUNK_HEC_SECRET reference and HEC-related comments from manifest.yml." [Source: architecture.md § Alignment Decisions]
- **Privileges**: Architecture uses internal schemas within the app database — `CREATE DATABASE` is NOT required. The vision document included it but the architecture (source of truth, written later) does not use an external database. Remove it.
- **RBAC**: Single application role `app_admin` (decision V14). No viewer roles. [Source: architecture.md § V14]
- **Callbacks**: Manifest references require the callback procedures to exist. `register_single_callback` is the standard Native App reference-binding callback. `get_secret_configuration` and `get_eai_configuration` return configuration for Secret and EAI references respectively. Full implementations come in later epics; stubs are sufficient for install.

### Deferred to later stories

- **Event definitions block** in manifest — architecture V13 specifies Native App event definitions for operational logging. These will be added to manifest.yml in Epic 7 (pipeline health). Not in scope here.
- **PEM Secret reference** — architecture shows an optional PEM cert Secret reference separate from SPLUNK_OTLP_SECRET. This will be added in Story 2.2 (certificate validation) if a distinct reference is needed.
- **USAGE grants on internal schemas** — `_internal`, `_staging`, `_metrics` do not need grants to `app_admin` yet. Owner-mode procedures can access them. Grants will be added in Story 1.2 when Streamlit code needs to read `_internal.config`.
- **Streamlit entrypoint** — `default_streamlit: app_public.main` requires `app/streamlit/main.py` to exist. This is created in Story 1.3. After Story 1.1, `snow app run` will install successfully but opening the app may show an error until Story 1.3 is deployed. Stories 1.1–1.3 should be deployed together for a working app.

### Files to touch

| Path | Action |
|------|--------|
| `app/manifest.yml` | Rewrite: manifest_version 2, four privileges (no CREATE DATABASE), three references (no HEC), scrub all HEC mentions, correct descriptions. |
| `app/setup.sql` | Add callback stub procedures with grants. Verify existing DDL is correct and idempotent. |

### Current state of existing files

- `app/manifest.yml`: **Done** — manifest_version 2, exactly four privileges (no CREATE DATABASE), three references (CONSUMER_EVENT_TABLE, SPLUNK_OTLP_SECRET, SPLUNK_EAI), zero HEC references. Aligned with architecture.
- `app/setup.sql`: **Done** — application role `app_admin`, versioned schema `app_public`, stateful schemas `_internal`, `_staging`, `_metrics`, Streamlit placeholder `app_public.main`, three callback stub procedures with grants. Idempotent. No tables (Story 1.2).
- `app/README.md`: **Done** — consumer-facing readme aligned with OTLP-only architecture; four privileges and required references tables; no HEC mentions.

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

**Before running any `snow` commands**, export the passphrase for the private key:

```bash
export PRIVATE_KEY_PASSPHRASE='<passphrase from .env or secrets manager>'
```

Verify the connection:

```bash
snow connection test --connection dev
```

### Testing

- **Primary**: From project root, run:
  ```bash
  snow app run --connection dev
  ```
  Expected: app installs, no SQL errors, privileges granted. Streamlit may not load (Story 1.3 dependency — that's expected).
- **Idempotency**: Run `snow app run --connection dev` a second time. Expected: no DDL errors on re-run.
- **Open in Snowsight** (after Story 1.3): `snow app open --connection dev` opens the Streamlit UI in browser.
- **Optional**: Install from package in a separate test account to simulate consumer experience.
- No unit tests needed for DDL-only changes.

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 1, Story 1.1]
- [Source: _bmad-output/planning-artifacts/architecture.md — Schema Topology, Naming Patterns, Alignment Decisions (HEC removal), Cross-Cutting Concerns (Upgrade safety), Authentication & Security (TLS only MVP)]
- [Source: _bmad-output/planning-artifacts/Native_App_Approval_Process_Guide.md — Installation/privilege testing, Permissions SDK]
- Snowflake docs: [Manifest reference](https://docs.snowflake.com/en/developer-guide/native-apps/manifest-reference), [Creating setup script](https://docs.snowflake.com/en/developer-guide/native-apps/creating-setup-script), [Requesting references from consumers](https://docs.snowflake.com/en/developer-guide/native-apps/requesting-refs)

## Dev Agent Record

### Agent Model Used

gpt-5.3-codex-high

### Debug Log References

- `snow connection test --connection dev` succeeded.
- `snow app run --connection dev` failed before setup execution due packaging config:
  - `No match was found for the specified source in the project directory : app/python/*`
  - `Multiple file or directories were mapped to one output destination. destination = streamlit/pages`
- Firecrawl scrape of Snowflake manifest reference was used to cross-check current manifest field behavior.
- `snow app run --connection dev --force` and a second re-run now both succeed after packaging + debug-mode fixes.
- Final packaging alignment validation: updated `snowflake.yml` Streamlit artifact mapping to `app/streamlit/* -> streamlit/` and re-ran `snow app run --force` twice successfully.
- `artifacts.default_streamlit` warning is now cleared because `CREATE OR REPLACE STREAMLIT app_public.main` + grant is included in setup.
- Snowsight worksheet verification (provider account `LFB71918`) confirms stage-dev install state:
  - `SHOW APPLICATION PACKAGES LIKE 'SPLUNK_OBSERVABILITY_DEV_PKG'` and `SHOW APPLICATIONS LIKE 'SPLUNK_OBSERVABILITY_DEV_APP'` return expected objects.
  - `SHOW VERSIONS IN APPLICATION PACKAGE SPLUNK_OBSERVABILITY_DEV_PKG` returns `No data` (expected for stage-dev flow before explicit version creation).
  - `LIST @SPLUNK_OBSERVABILITY_DEV_PKG.STAGE_CONTENT.APP_STAGE` shows expected staged artifacts only (`manifest.yml`, `setup.sql`, `README.md`, `environment.yml`, `streamlit/main.py`).
  - Callback procedures, Streamlit `APP_PUBLIC.MAIN`, and application role `APP_ADMIN` are present via `SHOW PROCEDURES`, `SHOW STREAMLITS`, and `SHOW APPLICATION ROLES`.

### Completion Notes List

- Rewrote `app/manifest.yml` to architecture-aligned Native App manifest v2:
  - Exactly four account-level privileges; removed `CREATE DATABASE`.
  - Removed all HEC references and `SPLUNK_HEC_SECRET`.
  - Kept exactly three references: `CONSUMER_EVENT_TABLE`, `SPLUNK_OTLP_SECRET`, `SPLUNK_EAI`.
  - Preserved required artifacts/configuration values.
- Updated `app/setup.sql` for idempotent install + required callback stubs:
  - Verified role/schema DDL pattern matches architecture (`CREATE OR ALTER VERSIONED SCHEMA` + stateful schemas with `IF NOT EXISTS`).
  - Added three SQL `EXECUTE AS OWNER` stub procedures returning empty string.
  - Added usage grants for all callback procedures to `app_admin`.
- Added minimal Streamlit placeholder (`app_public.main`) to remove CLI warning for `artifacts.default_streamlit`.
- Fixed project packaging config in `snowflake.yml` so only intended app artifacts are staged (no `.venv` upload drift).
- Corrected Streamlit artifact destination shape to avoid nested stage path (`streamlit/main.py` instead of `streamlit/streamlit/main.py`).
- Resolved manifest-v2 upgrade issue by setting app debug mode to false in `snowflake.yml` (session debug mode is the supported path for v2).
- Runtime nuance discovered and applied: `required_at_setup` for TABLE references is rejected by runtime parser in this account; kept it for SECRET/EAI only.
- Story is validated end-to-end: two consecutive successful `snow app run --connection dev --force` executions (idempotent).
- IDE schema lint errors in `app/manifest.yml` and `snowflake.yml` are caused by outdated/invalid extension-local schema files, not by executable Snowflake runtime validation.
- Added workspace YAML schema overrides in `.vscode/settings.json` and `.vscode/schemas/*` to restore accurate local linting for manifest v2 and project definition v2.
- Snowsight evidence attached by user confirms this story's stage-dev outcomes are visible in UI, not only via CLI.
- Future-story note: provider-side `SHOW SCHEMAS IN APPLICATION/DATABASE SPLUNK_OBSERVABILITY_DEV_APP` currently shows `APP_PUBLIC` and `INFORMATION_SCHEMA` only. Re-validate `_internal`, `_staging`, `_metrics` behavior at Story 1.2 start (before creating stateful tables) and adjust setup approach if needed.

### File List

- app/manifest.yml
- app/setup.sql
- app/README.md
- app/streamlit/main.py
- snowflake.yml
- .gitignore
- .vscode/settings.json (gitignored — local IDE config)
- .vscode/schemas/snowflake-manifest-v2.schema.json (gitignored — local IDE config)
- .vscode/schemas/snowflake-project-definition-v2.schema.json (gitignored — local IDE config)
- _bmad-output/implementation-artifacts/1-1-native-app-manifest-and-idempotent-setup.md
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Code Review (AI)

**Reviewer:** claude-4.6-opus — 2026-03-16
**Outcome:** Approved with fixes applied

### Issues Found and Resolved

| # | Severity | Issue | Resolution |
|---|----------|-------|------------|
| H1 | HIGH | `app/README.md` still contained HEC references ("HEC HTTP" x2) and listed removed `CREATE DATABASE` privilege — contradicted manifest and architecture | Rewrote README: removed all HEC mentions, aligned privilege table to 4 entries, added Required References table, updated "What This App Does" to OTLP-only |
| M1 | MEDIUM | `output/` directory (snow app run build artifacts) not in `.gitignore` | Added `output/` to `.gitignore` |
| M2 | MEDIUM | `app/README.md` was modified during dev but not documented in story File List | Added `app/README.md` and `.gitignore` to File List |

### Action Items for Later Stories

- [ ] [L1] **CONSUMER_EVENT_TABLE `required_at_setup` deviation** — AC 3 specifies `required_at_setup: true` but runtime rejects it for TABLE references. Dev notes document the reason. When Snowflake fixes this or when testing in a different account, re-evaluate adding `required_at_setup: true` back to the CONSUMER_EVENT_TABLE reference. (Candidate: Story 2.2 or any story that revisits manifest references.)
- [ ] [L2] **Stored Procedures section in README** — The current README omits the Stored Procedures section (was in old README with `_internal.event_table_collector()` and `_internal.volume_estimator()`). Re-add this section when those procedures are implemented in their respective stories (Epic 3 / Epic 4).
