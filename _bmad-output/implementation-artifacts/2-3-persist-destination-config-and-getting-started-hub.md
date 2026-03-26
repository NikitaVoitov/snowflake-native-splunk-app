# Story 2.3: Persist destination config and Getting Started hub

Status: review

## Story

As a consumer admin,
I want Splunk destination settings and onboarding progress persisted in the app,
so that configuration survives sessions and I have a clear hub for first-time setup.

## Acceptance Criteria

1. **Given** I am in the Splunk Observability Native App **When** I open Splunk Settings and enter endpoint URL, optional auth token, and optional PEM (or leave PEM empty) **Then** values are validated and saved to app-owned storage (`APP_PUBLIC.CONFIG` keys `splunk.endpoint_url`, `splunk.auth_token`, `splunk.skip_tls_verify`) **And** when PEM is provided it is stored in an **app-owned secret** (`_internal.otlp_pem_secret` via `save_pem_secret`) **And** the PEM text area on Splunk Settings is **always visible** and **hydrated** from `get_pem_secret` on load when a secret exists **And** I see success or actionable error feedback **And** Splunk Settings remains accessible from the sidebar at all times.

2. **Given** destination fields are saved **When** I return to Splunk Settings **Then** previously saved endpoint URL, token presence (masked), skip TLS verify, and PEM (when stored) are shown **And** empty PEM is a valid state (clears the secret).

3. **Given** I am on Getting Started **When** I use the Splunk Settings tile or link **Then** I am routed to Splunk Settings **And** after saving I can return to Getting Started (including auto-return when I arrived via drill-down from Getting Started).

4. **Given** I am on Getting Started **When** the hub loads **Then** I see the four setup tasks with short descriptions **And** each incomplete task shows a primary CTA **And** completed tasks show a completed state **And** overall progress is summarized (e.g. X of 4 complete).

5. **Given** task 1 (Splunk destination) is incomplete **When** I view Getting Started **Then** task 1 shows incomplete until endpoint URL is saved in config (and PEM, if required by product rules, is satisfied via secret or explicit empty).

6. **Given** tasks 2–4 **When** I use the app **Then** task 2 (telemetry sources) and task 3 (data governance) can be marked complete via **explicit UAT controls** on those pages (`pack_enabled.dummy`, `governance.acknowledged` in `APP_PUBLIC.CONFIG`) **And** task 4 reflects observability health readiness (`observability.ready` in `APP_PUBLIC.CONFIG`, set when prerequisites are met).

7. **Given** I complete a task from Getting Started **When** I use the primary CTA **Then** I am taken to the correct page **And** completion state updates when the underlying config keys change (live read from Snowflake on each run).

8. **Given** I have completed all four tasks **When** I use the app **Then** Getting Started **remains** in the sidebar with badge `4/4` (no auto-hide of the hub).

9. **Given** I am developing or testing **When** I need a clean onboarding state **Then** I can run `scripts/dev_reset_onboarding.sql` (Snow CLI) which calls `APP_PUBLIC.RESET_ONBOARDING_DEV_STATE()` **And** onboarding-related config keys and the PEM secret are cleared **Note:** reset runs with app owner rights; direct `DELETE` on `_internal` from provider session is not permitted.

10. **Given** the app is deployed **When** Streamlit loads **Then** navigation lists Getting Started and Splunk Settings **And** the Getting Started nav item shows a **live** `completed/total` badge derived from `APP_PUBLIC.CONFIG` (not a sticky “complete” flag that hides the hub).

11. **Given** certificate / TLS validation behavior from Story 2.2 **When** I use Splunk Settings **Then** optional PEM supports Splunk platform OTel export trust as implemented (secret-backed PEM, `skip_tls_verify`, connection test).

### Out of scope (unchanged)

- No automated Splunk-side validation beyond existing connection test patterns.
- No new consumer-managed secret type for PEM in `manifest.yml` for this story; PEM is app-owned secret + procedures.

## Tasks / Subtasks

- [x] AC1: Config keys + PEM secret + Splunk Settings save/load (mask token, hydrate PEM, always-show textarea)
- [x] AC2: Return visit shows saved state
- [x] AC3: Getting Started routing + drill-down return
- [x] AC4: Hub UI + progress
- [x] AC5: Task 1 completion rule
- [x] AC6: Tasks 2–4 completion (dummy + health)
- [x] AC7: CTAs and live completion
- [x] AC8: Getting Started stays in nav with 4/4 badge
- [x] AC9: Dev reset script + owner procedure
- [x] AC10: Sidebar nav + live badge
- [x] AC11: PEM / TLS alignment with 2.2

## Dev Notes

### Architecture patterns and constraints

- **Streamlit in Snowflake:** `get_active_session()`, `@st.cache_resource` for session, `@st.cache_data` for reads with TTL; no `st.set_page_config` page_title/icon/menu_items.
- **Config storage:** `APP_PUBLIC.CONFIG` (key/value) for non-secret settings; **PEM in app-owned secret** `_internal.otlp_pem_secret` with `save_pem_secret` / `get_pem_secret` (Python handler in `app/python/secret_reader.py`).
- **Onboarding helpers:** `app/streamlit/utils/onboarding.py` — `load_task_completion`, `get_completed_count`, `mark_task_complete`, `clear_drilldown_flag`, `set_drilldown_from_getting_started`.
- **Drill-down:** `st.session_state["drilled_from_getting_started"]` set when leaving Getting Started via task CTA; Splunk Settings “Back to Getting Started” clears flag and switches page; saving from drill-down triggers auto-return.

### Learnings from previous story

- Story 2.2: optional PEM file upload and cert validation; reuse `connection_test` and TLS patterns.

### Project Structure Notes

- Streamlit entry: `app/streamlit/main.py` (global CSS for Getting Started tiles + nav badge).
- Pages: `getting_started.py`, `splunk_settings.py`, `telemetry_sources.py`, `data_governance.py`, `observability_health.py`.
- SQL: `app/setup.sql` — config table, secret, procedures, `reset_onboarding_dev_state`, grants.

### References

- Epics: `_bmad-output/planning-artifacts/epics.md` — Epic 2, Story 2.3.
- Story 2.2 artifact: `2-2-optional-certificate-and-validation.md`.

## Dev Agent Record

### Context Reference

- `_bmad-output/planning-artifacts/epics.md` — Story 2.3.

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- PEM stored in app-owned secret; manifest consumer reference for PEM removed.
- `get_pem_secret` Python UDF requires `SECRETS` and **`EXTERNAL_ACCESS_INTEGRATIONS = (otlp_egress_eai)`** — Snowflake rejects `SECRETS` alone on the function without EAI in this app.
- Getting Started **always** in sidebar; badge shows live `x/4` from config; no `onboarding.complete` nav hide.
- Dev reset: `CALL APP_PUBLIC.RESET_ONBOARDING_DEV_STATE()` (owner procedure); script `scripts/dev_reset_onboarding.sql` for Snow CLI; provider-role direct DELETE on `_internal.config` fails with insufficient privileges.
- Tasks 2–3: dummy completion toggles for UAT; task 4: `observability.ready` from health page logic.

### File List

- `app/setup.sql`
- `app/snowflake.yml`
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

---

## Implementation insights (Story 2.3)

### Secrets and PEM

- **Consumer manifest `request_reference` for PEM was removed.** PEM is only in `_internal.otlp_pem_secret`, written via `save_pem_secret` from Streamlit.
- **`get_pem_secret` (Python UDF handler)** must declare both `SECRETS = ('_internal.otlp_pem_secret')` and **`EXTERNAL_ACCESS_INTEGRATIONS = (otlp_egress_eai)`**. Using `SECRETS` without EAI produced: `invalid property 'SECRETS' for 'FUNCTION'`.
- **Provider visibility:** In dev, `ACCOUNTADMIN` on the provider account may not see the app-owned secret in `SHOW SECRETS` for the app database context; rely on app procedures and Streamlit for verification.

### State management

- **Onboarding completion** is derived **only** from `APP_PUBLIC.CONFIG` keys on each load (`load_task_completion`); there is no long-lived Streamlit flag that hides Getting Started when all tasks are done.
- **`st.session_state`** is used for **UX only** (e.g. `drilled_from_getting_started`, PEM dirty flag, form dirty warning). Resetting onboarding in Snowflake does not clear an already-open Streamlit session’s widget state until rerun or new session.
- **Badge** in the sidebar is computed at runtime from the same config keys as the hub (single source of truth in Snowflake).

### Navigation and gating

- **Getting Started** is always listed in `st.navigation`; **Splunk Settings** is always available (no gating on incomplete onboarding).
- **Completed hub:** When all four tasks are complete, the hub still shows **Completed** summary and **Explore the app**; the nav item remains with badge `4/4`.

### Dev reset and privileges

- **`scripts/dev_reset_onboarding.sql`** executes `CALL APP_PUBLIC.RESET_ONBOARDING_DEV_STATE();` Implementation initially used `DELETE` from `_internal.config` as provider; Snowflake returned **42501 insufficient privileges**. The **owner procedure** performs `DELETE` and `REMOVE SECRET` inside the app.
- **Latency:** `snow sql -f scripts/dev_reset_onboarding.sql` can take **on the order of 1–3+ minutes** in dev (warehouse spin-up / platform); not a tight loop for local UI refresh.

### Getting Started UI

- **Tile layout:** Overlays use `st.container` + CSS (`stElementContainer` / `stVerticalBlock` height 100%, tertiary `stButton` stretched) so the **hand cursor** does not leak outside the tile; primary/secondary buttons share one full-height column.

### Testing

- **Unit tests** mock Snowflake session and avoid real `GET_DDL` / secret I/O where possible (`tests/test_config.py`, `tests/test_getting_started.py`, `tests/test_cert_validate.py`).
