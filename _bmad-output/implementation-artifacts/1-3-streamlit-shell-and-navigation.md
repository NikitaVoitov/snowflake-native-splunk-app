# Story 1.3: Streamlit shell and navigation

Status: done

## Story

As a Snowflake administrator (Maya),
I want to open the app and see a clear navigation (Getting started, Observability health, Telemetry sources, Splunk settings, Data governance) and an About dialog,
So that I can move between setup and monitoring without leaving Snowsight.

## Acceptance Criteria

1. **`st.navigation()` router with correct sidebar order**
   Given the app is installed and opened in Snowsight,
   when the Streamlit app loads:
   - `main.py` uses `st.navigation()` with `st.Page()` entries in sidebar order: Getting started, Observability health, Telemetry sources, Splunk settings, Data governance.
   - Icons: `:material/rocket_launch:`, `:material/dashboard:`, `:material/database:`, `:material/settings:`, `:material/shield:` respectively.
   - The navigation label remains exactly `Getting started` in this story; the `X/4` progress badge is deferred to Story 2.3.
   - The returned page object's `.run()` method is called to render the selected page.

2. **Sidebar header**
   When the sidebar renders:
   - It shows "Splunk Observability" as the app name and "for Snowflake" as the subtitle above the navigation links.
   - Uses `st.sidebar` with `st.markdown` or native text elements — no external CSS or fonts.

3. **About dialog**
   When the user clicks the "About" link (with `:material/info:` icon) in the sidebar footer:
   - The footer item is visually separated from the navigation and anchored at the bottom of the sidebar, matching the UX reference as closely as Streamlit in Snowflake allows.
   - A `@st.dialog` modal opens showing (centered):
     - "Splunk Observability" (bold)
     - "for Snowflake" (muted)
     - "Version 1.0.0" (muted, small)
     - "Copyright © 2026 Splunk Inc." / "All rights reserved."
     - "Documentation" link with external link icon
   - The Documentation link uses a native Streamlit link element and opens the external docs in a new tab.
   - Prefer native Streamlit components for the dialog and footer item. Small self-contained inline HTML/CSS is allowed only if needed to achieve the footer placement or centered modal presentation shown in UX, and only if it does not load any external CSS, fonts, scripts, or images.

4. **Each nav item routes to the correct page**
   When a sidebar item is clicked:
   - The corresponding page file (`pages/getting_started.py`, `pages/observability_health.py`, etc.) is rendered.
   - Pages render a stub/empty-state with a title and descriptive placeholder (e.g. `st.info("This page will be implemented in a future story.")`).

5. **Getting Started visibility logic (placeholder)**
   For this story:
   - Getting Started is **always shown** in the sidebar (full onboarding logic deferred to Story 2.3).
   - Getting Started is the **default page** when the app opens.
   - A session-state key `onboarding_complete` is initialized to `False` — later stories will use this to control visibility and default page.

6. **Deployment succeeds and pages load**
   When `snow app run --connection dev` is run:
   - The app deploys without errors.
   - Opening the app in Snowsight shows the sidebar with all five pages.
   - Clicking each page renders without errors.
   - Running `snow app run` a second time succeeds (idempotent).

## Tasks / Subtasks

- [x] **Task 1: Update `snowflake.yml` artifact mapping for pages subdirectory** (AC: 6)
  - [x] Replace the current mapping `app/streamlit/*` → `streamlit/` with a directory-based mapping that copies the full Streamlit tree (`app/streamlit/` → `streamlit/`). Use an explicit `pages/*` fallback only if the local bundle proves the directory form is unsupported in the current Snow CLI version.
  - [x] Run `snow app bundle` before deployment and inspect the bundled output to confirm it contains `streamlit/main.py` and all five `streamlit/pages/*.py` files.
  - [x] After updating, verify with `snow app run` that all files appear on the stage via `LIST @SPLUNK_OBSERVABILITY_DEV_PKG.STAGE_CONTENT.APP_STAGE PATTERN='.*streamlit.*'`.

- [x] **Task 2: Create page stub files** (AC: 4)
  - [x] Create `app/streamlit/pages/getting_started.py` — stub with title "Getting started" and placeholder content.
  - [x] Create `app/streamlit/pages/observability_health.py` — stub with title "Observability health" and empty-state message.
  - [x] Create `app/streamlit/pages/telemetry_sources.py` — stub with title "Telemetry sources" and placeholder content.
  - [x] Create `app/streamlit/pages/splunk_settings.py` — stub with title "Splunk settings" and placeholder content.
  - [x] Create `app/streamlit/pages/data_governance.py` — stub with title "Data governance" and placeholder content.
  - [x] Each page imports `streamlit as st` and renders a header + `st.info()` with a descriptive message about what will be built in the future story.

- [x] **Task 3: Rewrite `app/streamlit/main.py` as navigation router** (AC: 1, 2, 3, 5)
  - [x] Replace the placeholder content with the full `st.navigation()` router.
  - [x] Define pages using `st.Page()` with file paths, titles, and icons.
  - [x] Add sidebar header ("Splunk Observability" / "for Snowflake") using `st.sidebar.markdown()`.
  - [x] Add sidebar footer with an "About" item (`:material/info:` icon + "About" text, muted) visually separated from the nav list and positioned at the bottom of the sidebar as closely as Streamlit layout permits.
  - [x] Clicking the footer item triggers a `@st.dialog` About modal.
  - [x] Initialize `st.session_state.onboarding_complete` to `False` if not present.
  - [x] Set Getting Started as the default page using `default=True` on its `st.Page(...)` definition.
  - [x] Call `pg.run()` to render the selected page.

- [x] **Task 4: Validate with `snow app run`** (AC: 6)
  - [x] Run `snow app run --connection dev` — app deploys, no errors.
  - [x] Open in Snowsight (`snow app open --connection dev`) — sidebar shows all 5 pages with correct labels and icons.
  - [x] Click each page — renders without errors.
  - [x] Run `snow app run --connection dev` a second time — idempotent, no errors.

## Dev Notes

### Architecture compliance

- **Navigation**: `st.navigation()` API (Streamlit 1.52.2) is the required routing approach. Do NOT use the `pages/` folder auto-discovery convention as the routing mechanism. Once `st.navigation()` is executed, Streamlit ignores the `pages/` directory for auto-discovery across sessions. We use `pages/` only as an organizational directory for page files that are explicitly registered via `st.Page()`.
- **Page file structure**: Place pages in `app/streamlit/pages/` directory. Files use `snake_case.py` naming.
- **Sidebar order**: Getting started → Observability health → Telemetry sources → Splunk settings → Data governance.
- **Icons**: Use Streamlit `:material/` icon syntax:
  - Getting started → `:material/rocket_launch:`
  - Observability health → `:material/dashboard:`
  - Telemetry sources → `:material/database:`
  - Splunk settings → `:material/settings:`
  - Data governance → `:material/shield:`
- **Getting Started badge**: The final `X/4` progress badge next to Getting started is deferred to Story 2.3. Do not invent custom navigation hacks in Story 1.3 to force a badge into the built-in nav label.
- **About footer + dialog**: Uses `@st.dialog` decorator (Streamlit 1.35+). Sidebar footer shows an "About" item with `:material/info:` icon, visually separated from the nav list and placed at the bottom like the UX reference. Dialog displays centered app name, subtitle, version, copyright, and a "Documentation" external link.
- **Allowed presentation technique**: Prefer native Streamlit layout and text elements first. If exact footer placement or centered dialog composition cannot be achieved cleanly with native primitives alone, limited inline `unsafe_allow_html=True` is acceptable for wrapper/layout markup only. Do not use external CSS, fonts, scripts, icons, or images.
- **No `st.set_page_config`**: Not supported in Snowflake Native Apps. Do not call it.
- **Native components only**: No external CSS, fonts, scripts, or third-party components.
- **State management**: Use `st.session_state` for transient UI state. The `onboarding_complete` flag is initialized here as `False`; Story 2.3 will read from `_internal.config` to determine actual completion state.

### Critical: `snowflake.yml` artifact mapping

The current `snowflake.yml` maps `app/streamlit/*` → `streamlit/`. Official Snowflake CLI docs allow `src` values that are specific files, directories, or glob patterns, but they do **not** explicitly define recursive wildcard behavior for `*`. In the current dev package stage, only `app_stage/streamlit/main.py` is present, which strongly indicates the current mapping is **not** bringing in `pages/`.

**Required approach for this story**: switch to a directory-based artifact copy first, then validate with `snow app bundle` before deploying. Use an explicit subdirectory fallback only if the bundled output proves the directory form is unsupported in the installed Snow CLI version.

```yaml
# Preferred
- src: app/streamlit/
  dest: streamlit/
```

**Fallback only if needed:**

```yaml
- src: app/streamlit/*
  dest: streamlit/
- src: app/streamlit/pages/*
  dest: streamlit/pages/
```

Validate in this order:

1. `snow app bundle` — confirm bundled output contains `streamlit/main.py` and all `streamlit/pages/*.py` files.
2. `snow app run --connection dev` — deploy the app.
3. `LIST @SPLUNK_OBSERVABILITY_DEV_PKG.STAGE_CONTENT.APP_STAGE PATTERN='.*streamlit.*';` — confirm the staged files match expectations.

Expected files:

```text
streamlit/main.py
streamlit/pages/getting_started.py
streamlit/pages/observability_health.py
streamlit/pages/telemetry_sources.py
streamlit/pages/splunk_settings.py
streamlit/pages/data_governance.py
```

Stage verification SQL:

```sql
LIST @SPLUNK_OBSERVABILITY_DEV_PKG.STAGE_CONTENT.APP_STAGE PATTERN='.*streamlit.*';
```

### `st.navigation()` API usage

The `st.navigation()` function accepts a list or dict of page-like objects and returns the current page. The entrypoint then calls `.run()` on the returned page. Key API details validated against current Streamlit docs:

```python
import streamlit as st

pg = st.navigation([
    st.Page("pages/getting_started.py", title="Getting started", icon=":material/rocket_launch:", default=True),
    st.Page("pages/observability_health.py", title="Observability health", icon=":material/dashboard:"),
    st.Page("pages/telemetry_sources.py", title="Telemetry sources", icon=":material/database:"),
    st.Page("pages/splunk_settings.py", title="Splunk settings", icon=":material/settings:"),
    st.Page("pages/data_governance.py", title="Data governance", icon=":material/shield:"),
])
pg.run()
```

- `st.Page(...)` supports Python file paths and callables.
- `default=True` on the Getting started page is supported in Streamlit 1.52.2 and should be used directly.
- File paths are relative to the entrypoint (`main.py`), so `pages/getting_started.py` is correct.
- Position defaults to `"sidebar"` and should remain there for this story.
- Elements rendered from the entrypoint file act as a shared frame around all pages, so the sidebar header/footer should also be owned by `main.py`.
- After `st.navigation()` is executed, Streamlit ignores `pages/` auto-discovery. Only pages passed to `st.navigation()` are routable.

### `@st.dialog` for About modal

```python
@st.dialog("About")
def show_about():
    left, content, right = st.columns([1, 3, 1])
    with content:
        st.markdown("**Splunk Observability**")
        st.caption("for Snowflake")
        st.caption("Version 1.0.0")
        st.write("Copyright © 2026 Splunk Inc.")
        st.write("All rights reserved.")
        st.page_link("https://docs.splunk.com", label="Documentation", icon=":material/open_in_new:")
```

Call `show_about()` when the About button is clicked. The `@st.dialog` decorator creates a modal overlay. The close (X) button is provided natively by `@st.dialog`.

Implementation constraints from the current docs:

- Calling the decorated function opens the dialog.
- Default dismissal includes the native X button, outside click, and `Esc`.
- Only one dialog can be opened in a single script run.
- `st.sidebar` is not supported inside the dialog function.

### Getting started visibility logic (Story 1.3 scope)

For **this story only**: Getting started is always shown. The full conditional logic for hiding it after onboarding completion will be implemented in Story 2.3 (persist destination config and Getting Started hub). The logic from the UX spec is:

- **Visible when**: at least one of 4 tasks is incomplete, OR all complete but user is still on the page.
- **Hidden when**: all 4 tasks complete AND user navigated to another page.
- **Permanent**: once hidden, stays hidden even when navigating between other pages.

For now, initialize `st.session_state.onboarding_complete = False` and always include Getting Started in the pages list. Story 2.3 will add the config-backed logic.

### Page stub pattern

Each page stub should follow this minimal pattern:

```python
import streamlit as st

st.header("Page Title")
st.info("This page will be implemented in Story X.Y.")
```

**Do not** add complex placeholder content, mock data, or commented-out future code. Keep stubs minimal. Future stories will replace them entirely.

### Figma design reference

**Sidebar structure:**

| Element | Detail |
|---------|--------|
| Header | "Splunk Observability" (Inter Semi Bold, 20px, #0a0a0a) / "for Snowflake" (Inter Regular, 12px, #717182) |
| Sidebar bg | #fafafa with right border #e5e5e5 |
| Nav items | 5 items, 40px height each, 4px gap, 8px horizontal padding |
| Active state | bg #f5f5f5, 4px-wide dark (#030213) left accent bar with rounded right corners |
| Active text | #171717 (inactive: #0a0a0a) |
| Footer | "About" link with `:material/info:` icon (Inter Medium, 12px, #717182), top border #e5e5e5 |

**Icons (Figma Lucide → Streamlit Material):**

| Page | Figma icon | Streamlit icon |
|------|------------|----------------|
| Getting started | `Rocket` | `:material/rocket_launch:` |
| Observability health | `LayoutDashboard` | `:material/dashboard:` |
| Telemetry sources | `Database` | `:material/database:` |
| Splunk settings | `Settings` | `:material/settings:` |
| Data governance | `Shield` | `:material/shield:` |

**About dialog content (centered):**
- "Splunk Observability" — Semi Bold, 20px
- "for Snowflake" — Regular, 14px, #717182
- "Version 1.0.0" — Regular, 12px, #717182
- "Copyright © 2026 Splunk Inc." / "All rights reserved." — Regular, 14px, #717182
- "Documentation" link with `:material/open_in_new:` icon — Regular, 14px, #030213
- Close (X) button top-right (native to `@st.dialog`)

**Getting Started nav badge (deferred to Story 2.3):**
- "X/4" progress badge next to "Getting started" — rounded 8px pill (bg rgba(236,236,240,0.5), 12px text).

### Deferred to later stories

- **Getting Started tile hub** (progress bar, 4 task cards, drill-down) — Story 2.3.
- **Getting Started visibility toggling** (hide after onboarding) — Story 2.3.
- **Onboarding completion state from `_internal.config`** — Story 2.3.
- **Full page implementations** — Stories 2.x, 3.x, 6.x, 7.x.
- **Components directory** (`app/streamlit/components/`) — Created when first reusable component is needed (Story 2.x).

### Files to touch

| Path | Action |
|------|--------|
| `app/streamlit/main.py` | Rewrite: replace placeholder with `st.navigation()` router, sidebar header, About dialog. |
| `app/streamlit/pages/getting_started.py` | Create: stub page. |
| `app/streamlit/pages/observability_health.py` | Create: stub page with empty-state. |
| `app/streamlit/pages/telemetry_sources.py` | Create: stub page. |
| `app/streamlit/pages/splunk_settings.py` | Create: stub page. |
| `app/streamlit/pages/data_governance.py` | Create: stub page. |
| `snowflake.yml` | Update: artifact mapping to include `pages/` subdirectory. |

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

### Previous Story Intelligence (Story 1.1 + 1.2)

**What was established:**
- `app/manifest.yml` — manifest_version 2, four privileges, three references, zero HEC mentions. `default_streamlit: app_public.main`.
- `app/setup.sql` — `app_admin` role, `app_public` (versioned schema), `_internal` / `_staging` / `_metrics` (stateful schemas), four config/state tables, grants, Streamlit placeholder (`CREATE OR REPLACE STREAMLIT app_public.main FROM '/streamlit' MAIN_FILE = '/main.py'`), three callback stubs.
- `snowflake.yml` — artifact mapping: `app/streamlit/*` → `streamlit/` (needs updating for `pages/` subdirectory).
- `app/environment.yml` — `streamlit==1.52.2`, `snowflake-snowpark-python==1.9.0`, `plotly==6.5.0`, OTel SDK deps.
- `app/streamlit/main.py` — current placeholder: 3-line file with `st.title`, `st.caption`, `st.info`. To be fully replaced.

**Learnings to apply:**
- `snow app run --connection dev` is the deploy-and-test command. Use `--force` if stuck.
- Idempotency verified by running `snow app run` twice.
- Stage contents visible via `LIST @SPLUNK_OBSERVABILITY_DEV_PKG.STAGE_CONTENT.APP_STAGE`.
- IDE schema lint warnings on `manifest.yml` and `snowflake.yml` are local — ignore.
- Provider-side metadata queries do not expose every internal schema — not relevant for this story (UI only).
- The Streamlit object `app_public.main` is created in `setup.sql` with `FROM '/streamlit' MAIN_FILE = '/main.py'`. This means the stage path root for Streamlit is `/streamlit/` and the entrypoint is `/main.py` relative to that root. Page file references in code (e.g. `"pages/getting_started.py"`) are relative to the entrypoint location.

### Latest validated technical notes

- Official Streamlit docs confirm `st.navigation()` returns the current page and requires `.run()` in the entrypoint router.
- Official Streamlit docs confirm `st.Page(..., default=True)` is supported in the targeted version, so no fallback default-selection workaround is needed.
- Official Streamlit docs confirm `st.page_link()` supports external URLs and opens them in a new tab, so it is valid for the About dialog documentation link.
- Official Streamlit docs confirm entrypoint elements form a shared frame around all pages, which is why the sidebar header/footer should stay in `main.py`.
- Official Snowflake CLI docs confirm `snowflake.yml` artifacts support file, directory, and glob `src` values, but do not clearly document recursive `*` behavior.
- Official Snowflake CLI docs confirm `snow app bundle` is primarily a manual inspection tool. `snow app run` and related deploy commands invoke bundling automatically; keep manual `snow app bundle` in this story only as an optional preflight check when validating artifact mapping.
- Live Snowflake package metadata currently reports `streamlit=1.52.2`, `plotly=6.5.0`, and `snowflake-snowpark-python=1.9.0`, matching `app/environment.yml`.
- Live dev-package stage inspection currently shows only `app_stage/streamlit/main.py`, which is why the artifact mapping change is required before implementation starts.

### Testing

- **Artifact validation (optional preflight)**: `snow app bundle` — inspect bundled output and confirm `streamlit/main.py` plus all five `streamlit/pages/*.py` files are present before deployment when you want to inspect artifacts manually.
- **Primary**: `snow app run --connection dev` — app deploys, no errors.
- **Visual**: `snow app open --connection dev` — sidebar shows all 5 pages with correct labels (Getting started, Observability health, Telemetry sources, Splunk settings, Data governance) and icons.
- **Navigation**: Click each sidebar item — page renders without Streamlit error.
- **About dialog**: Click the bottom footer "About" item — modal opens with centered "Splunk Observability" / "for Snowflake" / "Version 1.0.0" / copyright / Documentation link.
- **Idempotency**: Run `snow app run --connection dev` a second time — no errors.
- **Stage verification**: `LIST @SPLUNK_OBSERVABILITY_DEV_PKG.STAGE_CONTENT.APP_STAGE PATTERN='.*streamlit.*'` — shows `main.py` and all 5 page files.
- No unit tests needed for UI-only changes. Unit tests will be added when page logic becomes non-trivial.

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 1, Story 1.3]
- [Source: _bmad-output/planning-artifacts/architecture.md — Streamlit Page Organization, Frontend Architecture (D4), Enforcement Guidelines, Structure Patterns]
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md — Chosen Direction (Direction 3), Sidebar order, Getting Started UX approach, Sidebar header/footer]
- [Source: .cursor/rules/streamlit_snowflake_design_rules.mdc — Hard Constraints, Multipage Navigation, Component Compatibility]
- [Source: _bmad-output/implementation-artifacts/1-1-native-app-manifest-and-idempotent-setup.md — Completion Notes, File List]
- [Source: _bmad-output/implementation-artifacts/1-2-config-and-state-tables.md — Completion Notes]
- Streamlit docs: [st.navigation](https://docs.streamlit.io/develop/api-reference/navigation/st.navigation), [st.Page](https://docs.streamlit.io/develop/api-reference/navigation/st.page), [st.dialog](https://docs.streamlit.io/develop/api-reference/execution-flow/st.dialog)
- Snowflake docs: [Project definition files](https://docs.snowflake.com/en/developer-guide/snowflake-cli/native-apps/project-definitions), [Preparing a local folder with configured Snowflake Native App artifacts](https://docs.snowflake.com/en/developer-guide/snowflake-cli/native-apps/bundle-app), [snow app bundle](https://docs.snowflake.com/en/en/developer-guide/snowflake-cli/command-reference/native-apps-commands/bundle-app)
- Figma designs:
  - [Getting Started page](https://www.figma.com/design/0ieSwN62nwAvR9ybSlvPG5/Snowflake-Native-App-Design?node-id=4495-49138&m=dev) (node 4495:49138)
  - [Data governance page](https://www.figma.com/design/0ieSwN62nwAvR9ybSlvPG5/Snowflake-Native-App-Design?node-id=4495-47617&m=dev) (node 4495:47617)
  - [About link in sidebar](https://www.figma.com/design/0ieSwN62nwAvR9ybSlvPG5/Snowflake-Native-App-Design?node-id=4499-49308&m=dev) (node 4499:49308)
  - [About dialog](https://www.figma.com/design/0ieSwN62nwAvR9ybSlvPG5/Snowflake-Native-App-Design?node-id=4499-49748&m=dev) (node 4499:49748)

## Dev Agent Record

### Agent Model Used

gpt-5.3-codex-high

### Debug Log References

- `uv run ruff check app/streamlit --fix` followed by `uv run ruff check app/streamlit` (pass).
- `snow app bundle --package-entity-id splunk_observability_dev_pkg` (pass) and bundle inspection via `ls output/deploy/streamlit`.
- `snow app run --connection dev --package-entity-id splunk_observability_dev_pkg --app-entity-id splunk_observability_dev_app --force` run twice (both pass).
- `snow sql --connection dev --query "LIST @SPLUNK_OBSERVABILITY_DEV_PKG.STAGE_CONTENT.APP_STAGE PATTERN='.*streamlit.*';"` (confirmed staged files).
- `snow app open --connection dev --package-entity-id splunk_observability_dev_pkg --app-entity-id splunk_observability_dev_app` (browser launch succeeded).

### Completion Notes List

- Implemented Streamlit shell router in `app/streamlit/main.py` using `st.navigation()` and explicit `st.Page(...)` definitions in the required order and icon set.
- Added sidebar header branding and a bottom-separated About footer action that opens an `@st.dialog` modal with the required copy and external Documentation link.
- Initialized `st.session_state.onboarding_complete` to `False` and set Getting started as default via `default=True`.
- Added five page stubs under `app/streamlit/pages/` with required titles and `st.info()` placeholder messages.
- Validated artifact packaging and deployment end-to-end: bundle includes `streamlit/main.py` and all five `streamlit/pages/*.py`; stage listing confirms all expected files; `snow app run` is idempotent.
- Snow CLI directory copy (`app/streamlit/` -> `streamlit/`) produced nested `streamlit/streamlit/` in this environment, so mapping was finalized with explicit file mappings to preserve required stage layout.
- Tested an alternate native-sidebar prototype in `app/about_dialog_native_preview.py`; it can support routing and progress behavior, but it required more DOM/CSS overrides for footer placement, fixed width, collapsed-arrow positioning, and right-aligned progress text, so the shipped app keeps the current `st.navigation(position="hidden")` plus custom sidebar shell.

### File List

- `snowflake.yml`
- `app/streamlit/main.py`
- `app/streamlit/pages/getting_started.py`
- `app/streamlit/pages/observability_health.py`
- `app/streamlit/pages/telemetry_sources.py`
- `app/streamlit/pages/splunk_settings.py`
- `app/streamlit/pages/data_governance.py`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/implementation-artifacts/1-3-streamlit-shell-and-navigation.md`

### Change Log

- 2026-03-16: Implemented Story 1.3 navigation shell, page stubs, About dialog/footer, artifact mapping fixes, and Snow CLI deployment/stage validation; moved status to review.
- 2026-03-17: Marked Story 1.3 done and documented the alternate native-sidebar experiment in `app/about_dialog_native_preview.py` for possible future reconsideration.
