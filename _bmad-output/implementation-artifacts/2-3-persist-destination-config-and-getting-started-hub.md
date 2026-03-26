# Story 2.3: Persist destination config and Getting Started hub

Status: done

## Story

As a Snowflake administrator (Maya),
I want to save the OTLP endpoint (and optional cert reference) to the app config and see Getting Started with task tiles and progress,
So that my destination is persisted and I can complete the rest of setup in order.

## Acceptance Criteria

1. **Given** connection test (and certificate handling per Stories 2.1–2.2) has succeeded for the current inputs, **When** I click **Save settings** on Splunk Settings, **Then** non-secret settings are written to `_internal.config` with key `otlp.endpoint`, **And** non-empty PEM is stored via `save_pem_secret` in the app-owned secret `_internal.otlp_pem_secret`, **And** clearing PEM on save removes the secret per app logic, **And** the PEM textarea is always shown and hydrated from `get_pem_secret` when a secret exists, **And** I see success or actionable error feedback, **And** Splunk Settings stays in the sidebar.

2. **Given** I saved destination fields, **When** I return to Splunk Settings, **Then** I see the saved endpoint URL and PEM when stored (loaded from secret), **And** empty PEM is a valid persisted state.

3. **Given** I am on Getting Started, **When** I use the Splunk Settings tile or CTA, **Then** I navigate to Splunk Settings, **And** I can return to Getting Started (including Back / auto-return after save when I drilled down from Getting Started).

4. **Given** I am on Getting Started, **When** the hub loads, **Then** I see four task tiles (Configure Splunk Settings, Select Telemetry Sources, Review Data Governance, Activate Export) with completed/pending state, **And** each tile uses `st.container(border=True)` with left column (checkmark or step number), center (title + description), Completed badge when done, right column drill-down, **And** progress shows X of 4 tasks completed (with percentage), **And** Task 1 is complete after destination save; sidebar badge matches hub progress, **And** clicking a tile or drill-down navigates via `st.page_link` / equivalent.

5. **Given** Task 1 is incomplete, **When** I view Getting Started, **Then** Task 1 shows incomplete until `otlp.endpoint` is present in `_internal.config`.

6. **Given** Tasks 2–4, **When** I use the app, **Then** Task 2 and Task 3 can be marked complete using controls on Telemetry sources and Data governance that set `pack_enabled.dummy` and `governance.acknowledged` in `_internal.config`, **And** Task 4 uses an interim `activation.completed` stub so the Getting Started flow can be exercised before the real Observability health / export activation work is implemented.

7. **Given** I use a task primary CTA from Getting Started, **When** I complete the underlying save or toggle, **Then** I land on the correct page, **And** completion updates from Snowflake config on rerun (not a stale client-only flag after DB reset).

8. **Given** all four tasks are complete, **When** I use the app, **Then** Getting Started remains in `st.navigation` with badge 4/4 and shows a completed hub summary and next-step actions.

9. **Given** I need a clean onboarding state for dev/test, **When** I run `scripts/dev_reset_onboarding.sql` (Snow CLI), **Then** it calls `CALL APP_PUBLIC.RESET_ONBOARDING_DEV_STATE()` and clears listed onboarding config keys and the PEM secret (owner context inside the app).

10. **Given** the app is deployed, **When** Streamlit loads, **Then** `st.navigation` includes Getting Started and Splunk Settings, **And** the Getting Started nav item shows a `completed/total` badge from the same config keys as the hub.

11. **Given** Story 2.2 TLS/certificate behavior, **When** I use Splunk Settings, **Then** optional PEM works with connection test, validation SP, and secret-backed persistence.

## Tasks / Subtasks

- [x] **Task 1: Durable config (`_internal.config`)** (AC: 1, 2, 5, 6, 7, 9)
  - [x] 1.1 Keys: `otlp.endpoint`, `otlp.pem_secret_ref`, onboarding keys per `utils/onboarding.py`.
  - [x] 1.2 Merge/load helpers in `app/streamlit/utils/config.py` (parameterized Snowpark SQL).

- [x] **Task 2: PEM secret + read path** (AC: 1, 2, 11)
  - [x] 2.1 `_internal.otlp_pem_secret`, `save_pem_secret`, `get_pem_secret` in `app/setup.sql` with grants to `app_admin`.
  - [x] 2.2 Handler `app/python/secret_reader.py` and `snowflake.yml` artifacts.
  - [x] 2.3 `get_pem_secret` UDF: `SECRETS` and `EXTERNAL_ACCESS_INTEGRATIONS = (otlp_egress_eai)` (both required).
  - [x] 2.4 Splunk Settings Save calls secret save/clear with config save.

- [x] **Task 3: Splunk Settings load/save** (AC: 1, 2, 3, 11)
  - [x] 3.1 Load config + `get_pem_secret` on page load; hydrate widgets.
  - [x] 3.2 Preserve 2.1–2.2 gating; Save writes durable state.
  - [x] 3.3 Dirty-state / unsaved warning when leaving drill-down where applicable.
  - [x] 3.4 Back to Getting Started and post-save auto-return when `drilled_from_getting_started`.

- [x] **Task 4: Getting Started hub UI** (AC: 4, 5, 6, 7, 8)
  - [x] 4.1 Four tiles, containers, badges, CTAs per UX-DR3.
  - [x] 4.2 X of 4 progress via `load_task_completion` / `get_completed_count`.
  - [x] 4.3 CSS: full-height columns, contained hit targets for tiles.

- [x] **Task 5: Onboarding utils** (AC: 4–7)
  - [x] 5.1 `app/streamlit/utils/onboarding.py`: task defs, `load_task_completion`, `get_completed_count`, drill-down session helpers.
  - [x] 5.2 Completion from DB each run (`@st.cache_data` TTL or direct read per project pattern).

- [x] **Task 6: Telemetry sources & Data governance hooks** (AC: 6)
  - [x] 6.1 Telemetry sources: set `pack_enabled.dummy` for Task 2.
  - [x] 6.2 Data governance: set `governance.acknowledged` for Task 3.

- [x] **Task 7: Task 4 interim stub** (AC: 6)
  - [x] 7.1 Use `activation.completed` from the Getting Started placeholder dialog until real activation / Observability health logic is implemented.

- [x] **Task 8: Sidebar badge** (AC: 8, 10)
  - [x] 8.1 `main.py` CSS for Getting Started nav `completed/total` badge.

- [x] **Task 9: Developer reset** (AC: 9)
  - [x] 9.1 `APP_PUBLIC.RESET_ONBOARDING_DEV_STATE()` in `setup.sql`.
  - [x] 9.2 `scripts/dev_reset_onboarding.sql` for Snow CLI.

- [x] **Task 10: Tests** (AC: 1–7, 11)
  - [x] 10.1 `tests/test_config.py`
  - [x] 10.2 `tests/test_getting_started.py`
  - [x] 10.3 `tests/test_cert_validate.py` as needed for PEM assumptions

## Dev Notes

### Architecture

- Streamlit: `get_active_session()` via `utils.snowflake`; cache session resource; onboarding/config reads hit Snowflake on each run because completion state must stay live.
- Source of truth: `_internal.config` and the PEM secret. `st.session_state` holds drill-down flags, dirty PEM, connection/validation results; after `RESET_ONBOARDING_DEV_STATE`, open sessions may need rerun/new session to match DB.

### Product / UX references

- Epic 2 — FR3, FR8, FR9, FR10; Getting Started hub and Splunk Settings Connection Card.
- UX-DR2: tile hub, X of 4 progress; UX-DR3: tile layout (`st.container(border=True)`, checkmark/step, Completed badge, drill-down).

### Config and secrets

- Non-secret application settings: `_internal.config` (key/value). PEM: `_internal.otlp_pem_secret`, `save_pem_secret` / `get_pem_secret`.
- `get_pem_secret` handler must list both `SECRETS` and `EXTERNAL_ACCESS_INTEGRATIONS = (otlp_egress_eai)` or Snowflake errors with `invalid property 'SECRETS' for 'FUNCTION'`.

### Security (NFR6)

- Do not log raw PEM or tokens. Mask token in UI.

### Dev reset

- Provider sessions cannot rely on ad-hoc `DELETE` on internal tables; use `CALL APP_PUBLIC.RESET_ONBOARDING_DEV_STATE()`. Reset via CLI can be slow (warehouse startup).

### Implementation notes

- PEM persistence uses app-owned secret; not consumer manifest `request_reference` for this flow.
- Getting Started stays in `st.navigation` at 4/4 (hub always reachable).
- Tasks 2–3 use interim config keys for UAT until Epic 3+ flows own full persistence.
- Sidebar badge uses DOM-targeted CSS on the current Streamlit sidebar structure; verify visually after Streamlit upgrades because the badge selector is intentionally implementation-dependent.

### References

- `_bmad-output/planning-artifacts/epics.md` — Epic 2, Story 2.3
- `2-2-optional-certificate-and-validation.md`, `2-1-otlp-endpoint-and-connection-test.md`

### File changes summary

| File | Purpose |
|------|---------|
| `app/setup.sql` | CONFIG, secret, procedures, reset, grants |
| `snowflake.yml` | Project packaging / deployment config |
| `app/python/secret_reader.py` | PEM secret read UDF handler |
| `app/streamlit/main.py` | Nav, tile + badge CSS |
| `app/streamlit/pages/getting_started.py`, `splunk_settings.py`, `telemetry_sources.py`, `data_governance.py`, `observability_health.py` | UI |
| `app/streamlit/utils/config.py`, `onboarding.py` | Config + onboarding |
| `scripts/dev_reset_onboarding.sql` | Dev reset entrypoint |
| `tests/test_config.py`, `tests/test_getting_started.py`, `tests/test_cert_validate.py` | Unit tests |

## Dev Agent Record

### Context Reference

- `_bmad-output/planning-artifacts/epics.md` — Story 2.3

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- PEM in app-owned secret; `get_pem_secret` needs SECRETS + otlp_egress_eai on the UDF.
- Getting Started always in nav; live x/4 badge from config keys.
- Reset: `RESET_ONBOARDING_DEV_STATE()`; provider DELETE on internal config not viable.
- Tasks 2–3: `pack_enabled.dummy`, `governance.acknowledged`; Task 4 uses interim `activation.completed`.
- Manual UAT on the deployed dev app passed for the current Story 2.3 scope (Splunk Settings persistence, Getting Started progress, drill-down completion redirects, and reset flow).
- `st.switch_page()` is treated as terminal navigation; the save path now uses `st.stop()` after switching back to Getting Started to make the control flow explicit.

### File List

- `app/setup.sql`
- `snowflake.yml`
- `app/manifest.yml`
- `app/python/secret_reader.py`
- `app/python/connection_test.py`
- `app/streamlit/main.py`
- `app/streamlit/pages/getting_started.py`
- `app/streamlit/pages/splunk_settings.py`
- `app/streamlit/pages/telemetry_sources.py`
- `app/streamlit/pages/data_governance.py`
- `app/streamlit/pages/observability_health.py`
- `app/streamlit/utils/config.py`
- `app/streamlit/utils/onboarding.py`
- `app/streamlit/utils/snowflake.py`
- `scripts/dev_reset_onboarding.sql`
- `tests/test_config.py`
- `tests/test_getting_started.py`
- `tests/test_cert_validate.py`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
