---
stepsCompleted: [step-01-validate-prerequisites, step-02-design-epics, step-03-create-stories, step-04-final-validation]
status: complete
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/architecture.md
  - _bmad-output/planning-artifacts/ux-design-specification.md
---

# snowflake-native-splunk-app - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for snowflake-native-splunk-app, decomposing the requirements from the PRD, UX Design, and Architecture into implementable stories.

**Implementation order note:** Epics are grouped by user value, but technical dependencies require interleaving. Story 4.3 (Activate) provisions DDL objects (streams, tasks, EAI) that reference stored procedures implemented in Epic 5, which depend on the OTLP module from Epic 6. The recommended sprint order is: Sprint 1 (Epic 1) → Sprint 2 (Epic 2) → Sprint 3 (Epic 3) → Sprint 4 (Epic 6) → Sprint 5 (Epic 5) → Sprint 6/MVP (Epic 4) → Sprint 7 (Epic 7) → Sprint 8 (Epic 8). See `sprint-status.yaml` for the full sprint plan with deliverables and acceptance tests.

## Requirements Inventory

### Functional Requirements

FR1: Maya can install the app from the Snowflake Marketplace without provisioning vendor-managed infrastructure outside Snowflake.
FR2: Maya can review and approve the Snowflake privileges the app requires during install or upgrade flows.
FR3: Maya can complete first-time setup in the app so that an OTLP destination is saved, at least one telemetry source is selected, governance review is acknowledged, and export activation is enabled.
FR4: Maya can discover which supported ACCOUNT_USAGE views and Event Tables are available for selection in the current Snowflake account when operating with the required Snowflake privileges.
FR5: Maya can enable or disable each Monitoring Pack independently.
FR6: Maya can view the default execution interval for each selected telemetry source before activation.
FR7: Maya can change the execution interval for any supported telemetry source without reinstalling the app.
FR8: Maya can configure the OTLP export destination used to send telemetry to Splunk or another OTLP-compatible collector.
FR9: Maya can provide any certificate material required for a private or self-signed OTLP destination and receive a pass-or-fail trust validation before saving the configuration.
FR10: Maya can run a connection test and receive a pass or fail result before saving an OTLP destination.
FR11: Maya can view and change the execution interval used for Event Table collection after initial setup within the supported minimum and maximum interval bounds published for the app.
FR12: Maya can choose, for each supported telemetry source, either the default Snowflake source or a custom source she controls.
FR13: Maya can review, for each enabled source, whether it is a default or custom source and whether masking, row access, and projection controls will be preserved, and must record acknowledgement before export is enabled.
FR14: Maya can receive a blocking disclosure when a default ACCOUNT_USAGE view or Event Table is selected that Snowflake masking and row access controls require a custom source, and must acknowledge that disclosure before export is enabled.
FR15: Maya can select a custom source and have exported data reflect the Snowflake masking, row access, and projection policies enforced on that source.
FR16: Maya can select a custom source with masking policies applied and have masked values preserved in exported telemetry.
FR17: Maya can select a custom source with row access policies applied and have only permitted rows included in exported telemetry.
FR18: Maya can select a custom source with projection policies applied and have export continue with blocked columns emitted as NULL and a warning recorded for the affected run.
FR19: Sam can export new Event Table telemetry produced after activation without re-exporting records already delivered successfully.
FR20: Maya can scope Event Table export to the MVP telemetry categories supported by enabled Monitoring Packs: Snowflake SQL and Snowpark compute telemetry.
FR21: Sam can run each enabled ACCOUNT_USAGE source on an independent collection schedule so one source can be delayed, changed, or recovered without blocking others.
FR22: Maya can view and edit per-source operational settings, including enabled state, execution interval, overlap window (for ACCOUNT_USAGE sources), and batch size.
FR22a: Maya can adjust the overlap window for each ACCOUNT_USAGE source to control how far back the watermark query re-scans for late-arriving rows. The default is set to the documented maximum latency for that view plus a small safety margin.
FR23: Sam can deliver all enabled Event Table and ACCOUNT_USAGE telemetry through the configured OTLP destination for downstream use in Splunk.
FR24: Ravi can analyze exported Event Table spans in Splunk using query or executable identity, database and schema context, warehouse context, and trace correlation fields.
FR25: Ravi can rely on original Event Table attributes remaining intact in exported telemetry, with any app-added attributes added without renaming or removing source attributes.
FR26: Sam can rely on retryable OTLP delivery failures being retried automatically and on non-retryable failures being recorded as terminal batch failures without endless retry.
FR27: Sam can view a health summary that shows destination status, source freshness, export throughput, failures, and recent operational issues.
FR28: Sam can inspect each telemetry source to see current status, freshness, recent runs, current errors, and its editable configuration.
FR29: Sam can access structured app operational events in the consumer's Snowflake event table via Snowsight.
FR30: Sam can query app operational events in Snowsight to diagnose OTLP delivery failures, processing failures, and recovery actions.
FR31: Sam can see Event Table collection resume automatically after a recoverable Event Table collection interruption within the recovery window defined by NFR16, without manually repairing the pipeline.
FR32: Sam can identify any data gap caused by a recoverable collection interruption or sustained destination outage, including the affected source and time window.
FR33: Sam can have a repeatedly failing source automatically suspended without stopping healthy sources, and can see the suspended status for that source.
FR34: Sam can review per-run pipeline metrics for each source, including records collected, records exported, failures, and processing latency.
FR35: Tom can publish supported app upgrades through Snowflake Marketplace so consumers receive them under their maintenance policy.
FR36: Maya can retain configuration, source progress, and pipeline health history across supported version upgrades.
FR37: Maya can upgrade the app without re-entering configuration, and in-flight scheduled work either completes or resumes automatically with no more than one missed scheduled run per source.
FR38: Sam can access structured upgrade progress events in the Snowflake event table for each upgrade attempt.
FR39: Tom can submit a release candidate for Snowflake Marketplace approval after install, configuration, export, and upgrade workflows pass in a clean consumer account and reviewer guidance is complete.

### NonFunctional Requirements

NFR1: Event Table telemetry p95 end-to-end latency is <= 60 seconds from Event Table write time to visibility in Splunk.
NFR2: ACCOUNT_USAGE telemetry p95 latency from source availability to visibility in Splunk is <= one configured polling cycle.
NFR3: Core app pages p95 load-to-render time is <= 5 seconds for setup, telemetry sources, governance, and health pages.
NFR4: Health views use data no older than the most recent completed run for the represented source or category.
NFR5: Batch export processing p95 time from batch start to OTLP send result is <= 30 seconds.
NFR6: Zero instances of credentials or certificate material in code, config tables, app metadata tables, or logs.
NFR7: 100% of successful OTLP sessions use encrypted transport; plaintext OTLP connection attempts fail.
NFR8: Zero successful outbound connections to destinations not explicitly approved by the consumer for this app.
NFR9: 100% of exported records originate from the Snowflake sources Maya selected; policy-protected test fields and rows remain governed in exports.
NFR10: 100% of submitted versions pass the automated Marketplace security scan with zero Critical or High findings.
NFR11: Zero secret or credential findings across event tables, pipeline health outputs, and UI renders in normal and failure scenarios.
NFR12: Zero open P1 or P2 defects and zero Critical or High unresolved third-party component vulnerabilities at release cut.
NFR13: Scheduled availability is >= 99.9% per source over a rolling 30-day window.
NFR14: >= 99.5% of batches complete successfully after retry handling over a rolling 7-day window.
NFR15: In induced single-source failure tests, 100% of unaffected sources still start and complete within their next scheduled interval.
NFR16: 100% of induced stale stream conditions are detected and export resumes within 10 minutes or 2 scheduled executions, whichever is longer, without manual action.
NFR17: Zero missing or duplicate records in controlled upgrade reconciliation; 100% retention of configuration and source progress across supported upgrade paths.
NFR18: Zero permanently lost batches for induced destination outages lasting up to 60 seconds.
NFR19: A triggered execution completes with 1,000,000 representative Event Table rows without timeout or unrecoverable memory failure.
NFR20: With 10 enabled sources, >= 99% of scheduled runs start within one interval and complete successfully.
NFR21: Doubling supported task compute yields at least 1.7x throughput until destination saturation or the NFR19 workload ceiling is reached.
NFR22: 100% of sampled spans include the database and Snowflake context required by the telemetry contract, pass OTLP schema validation, and are searchable as traces in Splunk APM.
NFR23: 100% of exported spans, metrics, and logs include the mandatory routing fields for source identity, Snowflake account identity, telemetry type, and service or resource identity.
NFR24: 100% of retryable OTLP errors trigger automatic retry; 100% of non-retryable OTLP errors generate a terminal failure record within 1 minute with no endless retry loop.

### Additional Requirements

- Project bootstrapped from `snow init --template app_streamlit_python`; maintain Snowflake Native App structure (manifest_version: 2, setup.sql idempotent, versioned + stateful schemas).
- Configuration storage: hybrid — manifest references for Snowflake objects (CONSUMER_EVENT_TABLE, SPLUNK_EAI, optional PEM Secret); _internal.config table for app settings (otlp.endpoint, pack_enabled.*, source.*.*).
- Schema topology: app_public (versioned), _internal, _staging, _metrics (stateful with CREATE SCHEMA IF NOT EXISTS).
- OTLP exporter topology: 3 separate exporters (Span, Metric, Log) per Event Table collector; module-level init; TLS-only MVP (optional custom PEM via Snowflake Secret).
- Streamlit state: st.session_state as cache; _internal.config as durable store; explicit Save pattern; unsaved changes indicator.
- Independent serverless scheduled tasks per ACCOUNT_USAGE source; one triggered task for Event Table pipeline; stream on user-selected source (view or event table).
- Entity discrimination: positive include-list on RESOURCE_ATTRIBUTES:"snow.executable.type" (procedure, function, query, sql).
- OTel conventions: db.* (Database Client) + snowflake.* (custom); convention-transparent relay of original Event Table attributes.
- Pipeline health: _metrics.pipeline_health per-run metrics; Native App event definitions for structured operational logs.
- Stale stream recovery: detect via DESCRIBE STREAM; DROP and CREATE STREAM on selected source; record data gap.
- Naming: Snowflake objects (snake_case, _prefix for internal schemas); config keys (otlp.*, pack_enabled.*, source.<name>.*); Python PEP 8 + ruff.
- Testing: unit mocks + integration against dev schema + E2E via Cursor agents (Playwright for Snowsight, SSH for collector verification).
- Multi-package strategy: dev (INTERNAL) → scan (EXTERNAL) → test (INTERNAL) → prod (EXTERNAL) for Marketplace.

### UX Design Requirements

UX-DR1: Implement multi-page navigation using st.navigation() with sidebar order: Getting started (with progress badge X/4) → Observability health → Telemetry sources → Splunk settings → Data governance. Sidebar header "Splunk Observability" / "for Snowflake"; footer "About" link opening st.dialog with app version, build info, documentation links.
UX-DR2: Implement Getting Started page as a tile hub: 4 task cards (Configure Splunk Settings, Select Telemetry Sources, Review Data Governance, Activate Export) with completed/pending states, drill-down to corresponding page or modal; progress bar "X of 4 tasks completed"; remove Getting started from sidebar when all 4 tasks complete AND user navigates away.
UX-DR3: Implement Getting Started Tile component: st.container(border=True) with left column (checkmark or step number), center (title + description), green "Completed" badge when done, right column drill-down arrow; st.page_link or st.button for navigation; completion state from session_state.
UX-DR4: Implement Splunk settings page with Export settings tab (st.tabs): OTLP endpoint st.text_input, Test connection and Clear buttons, optional PEM st.text_area, Validate certificate button, Save settings (primary) disabled until connection test succeeds and certificate (if provided) is validated; success/error alerts; unsaved changes indicator in footer.
UX-DR5: Implement Connection Card as st.container(border=True) wrapping OTLP endpoint, certificate section, Test connection, Validate certificate, and Save; st.status or callouts for connection and certificate feedback; state in session_state.
UX-DR6: Implement Telemetry sources page with st.data_editor: category headers (collapsible, status dot, enabled toggle, "X/Y" count); columns Poll (checkbox), Status (dot), View name, Source type (tag), Freshness chart (sparkline), Recent runs (net score + sparkline), Errors (24h), Interval (editable), Overlap (editable, ACCOUNT_USAGE only); category status roll-up rules (green/amber/red/gray); source discovery from INFORMATION_SCHEMA / SHOW EVENT TABLES and ACCOUNT_USAGE custom views.
UX-DR7: Implement Observability health page helicopter view: Row 1 — Destination health card (OTLP status, endpoint, last export); Row 2 — Four st.metric KPIs (Sources OK, Rows exported 24h, Failed batches 24h, Avg freshness); Row 3 — Export Throughput chart (24h/7d toggle, rows exported + failed batches); Row 4 — Category Health Summary table (one row per pack, View → drill-down to Telemetry sources); Row 5 — Recent Errors (conditional, with "View all in Snowsight" link).
UX-DR8: Implement Empty State on Observability health when no pipelines configured: st.info or st.warning with message "Complete Getting started to see pipeline health" and optional link/button to Getting started.
UX-DR9: Implement Data governance page: read-only st.dataframe with enabled sources only; five columns — Status, View name, Source type, Governance (per-row message), Sensitive columns (per-row list); same category headers as Telemetry sources (status dot, no toggle); "Agree" button to record governance acknowledgement.
UX-DR10: Implement Activate Export modal (st.dialog): header "Activate Telemetry Export", info box "What will happen", bullet list of created objects (tasks, streams, network rules, secrets), Cancel and "Enable Auto-Export" (primary) buttons; in-progress spinner; success close + toast.
UX-DR11: Use native Streamlit components only (no external CSS/fonts/scripts); inline HTML/CSS/JS only when necessary via st.markdown(unsafe_allow_html=True) or st.html(); design tokens from Snowsight light theme; st.metric, st.dataframe with column_config, st.plotly_chart or st.altair_chart for charts.
UX-DR12: Health and KPIs computed on page load or manual refresh only; no live polling or auto-refresh.
UX-DR13: All form inputs use descriptive label parameters; status communicated via text and icon, not color alone; accessibility for callouts and tables.

### FR Coverage Map

FR1: Epic 1 — Install from Marketplace without vendor infrastructure
FR2: Epic 1 — Review and approve Snowflake privileges during install/upgrade
FR3: Epic 2 — Complete first-time setup (OTLP saved, source selected, governance acknowledged, export activated)
FR4: Epic 3 — Discover available ACCOUNT_USAGE views and Event Tables
FR5: Epic 3 — Enable or disable each Monitoring Pack independently
FR6: Epic 3 — View default execution interval per source
FR7: Epic 3 — Change execution interval without reinstall
FR8: Epic 2 — Configure OTLP export destination
FR9: Epic 2 — Provide and validate certificate for private/self-signed OTLP
FR10: Epic 2 — Run connection test before saving
FR11: Epic 3 — View and change Event Table collection interval within bounds
FR12: Epic 3 — Choose default or custom source per telemetry source
FR13: Epic 4 — Review default vs custom and masking/row access per source; acknowledge before export
FR14: Epic 4 — Blocking disclosure when default source selected; acknowledge before export
FR15: Epic 4 — Custom source exports reflect Snowflake policies
FR16: Epic 4 — Custom source with masking preserves masked values in export
FR17: Epic 4 — Custom source with row access exports only permitted rows
FR18: Epic 4 — Custom source with projection: blocked columns NULL, warning recorded
FR19: Epic 5 — Export new Event Table telemetry incrementally (no re-export)
FR20: Epic 5 — Scope Event Table export to MVP categories (SQL/Snowpark compute)
FR21: Epic 5 — Each ACCOUNT_USAGE source on independent schedule
FR22: Epic 3 — View and edit per-source settings (enabled, interval, overlap, batch size)
FR22a: Epic 3 — Adjust overlap window per ACCOUNT_USAGE source
FR23: Epic 6 — Deliver all enabled telemetry through OTLP to Splunk
FR24: Epic 6 — Analyze exported spans in Splunk (identity, context, trace correlation)
FR25: Epic 6 — Original Event Table attributes intact; app-added only additive
FR26: Epic 6 — Retryable OTLP retried; non-retryable recorded as terminal
FR27: Epic 7 — View health summary (destination, freshness, throughput, failures, issues)
FR28: Epic 7 — Inspect each source (status, freshness, runs, errors, config)
FR29: Epic 7 — Access structured app operational events in Snowflake event table via Snowsight
FR30: Epic 7 — Query app events to diagnose OTLP/processing failures and recovery
FR31: Epic 7 — Event Table collection resumes automatically after recoverable interruption
FR32: Epic 7 — Identify data gap (source and time window) after interruption or outage
FR33: Epic 7 — Repeatedly failing source auto-suspended; see suspended status
FR34: Epic 7 — Review per-run pipeline metrics per source
FR35: Epic 8 — Publish app upgrades via Marketplace
FR36: Epic 8 — Retain configuration and pipeline health history across upgrades
FR37: Epic 8 — Upgrade without re-entering config; in-flight work completes or resumes
FR38: Epic 8 — Access structured upgrade progress events in event table
FR39: Epic 8 — Submit release for Marketplace approval after consumer-account validation

## Epic List

### Epic 1: App foundation and installation
Maya can install the app from the Snowflake Marketplace and complete required privilege approval; the app has a working Native App shell (manifest v2, idempotent setup.sql, config and state schemas), Streamlit entrypoint with st.navigation() and sidebar (Getting started, Observability health, Telemetry sources, Splunk settings, Data governance, About), and foundational config storage so all later setup and pipeline code can persist and read settings.
**FRs covered:** FR1, FR2

### Epic 2: First-time setup and destination configuration
Maya can complete first-time setup by configuring the OTLP export destination (endpoint, optional PEM certificate, test connection, validate certificate) and saving settings; the Getting Started hub shows progress and task tiles with drill-down; the Splunk settings page exposes the Export settings tab with Connection Card behavior and Save disabled until connection test (and certificate validation if provided) succeeds.
**FRs covered:** FR3, FR8, FR9, FR10

### Epic 3: Telemetry source selection and pack management
Maya can discover available Event Tables and ACCOUNT_USAGE (and custom views), enable or disable Monitoring Packs, choose default or custom source per supported source, view and change execution intervals and per-source settings (interval, overlap for ACCOUNT_USAGE, batch size), and persist source configuration; the Telemetry sources page provides category-based st.data_editor with enable/interval/overlap and source discovery.
**FRs covered:** FR4, FR5, FR6, FR7, FR11, FR12, FR22, FR22a

### Epic 4: Data governance review and activation
Maya can review governance implications per enabled source (default vs custom, masking/row access/projection), receive and acknowledge blocking disclosure when default sources are selected, and activate export so the app provisions tasks, streams, and network/secret objects; the Data governance page shows enabled sources with Status, View name, Source type, Governance message, and Sensitive columns; the Activate Export modal confirms and triggers provisioning.
**FRs covered:** FR13, FR14, FR15, FR16, FR17, FR18

### Epic 5: Collection pipeline handlers
Sam (via the app’s automated pipelines) gets incremental Event Table export without re-exporting delivered records, with MVP entity scoping (SQL/Snowpark compute); each enabled ACCOUNT_USAGE source runs on its own independent schedule. DDL provisioning (streams, tasks, EAI) is handled by Story 4.3; this epic implements the Python stored-procedure handlers that those tasks call.
**FRs covered:** FR19, FR20, FR21

### Epic 6: OTLP export and Splunk-ready telemetry
Sam can deliver all enabled Event Table and ACCOUNT_USAGE telemetry through the configured OTLP destination; Ravi can analyze exported spans in Splunk with correct identity, database/schema/warehouse context, and trace correlation; original Event Table attributes are preserved with additive enrichment only; retryable OTLP failures are retried automatically and non-retryable failures are recorded as terminal without endless retry.
**FRs covered:** FR23, FR24, FR25, FR26

### Epic 7: Pipeline operations and observability health
Sam can view a health summary (destination status, source freshness, export throughput, failures, recent issues), inspect each telemetry source for status, freshness, recent runs, errors, and editable configuration, access structured app operational events in the consumer’s Snowflake event table via Snowsight, and benefit from automatic Event Table stream recovery and per-source auto-suspend; Observability health page provides destination card, KPI metrics, throughput chart, category summary with drill-down, and conditional recent errors; empty state when no pipelines are configured.
**FRs covered:** FR27, FR28, FR29, FR30, FR31, FR32, FR33, FR34

### Epic 8: App lifecycle and Marketplace release
Tom can publish supported app upgrades through Snowflake Marketplace; Maya retains configuration, source progress, and pipeline health history across upgrades and can upgrade without re-entering config; Sam can access structured upgrade progress events; Tom can submit a release candidate for Marketplace approval after install, configuration, export, and upgrade workflows pass in a clean consumer account with reviewer guidance complete.
**FRs covered:** FR35, FR36, FR37, FR38, FR39

---

## Epic 1: App foundation and installation

Maya can install the app from the Snowflake Marketplace and complete required privilege approval; the app has a working Native App shell (manifest v2, idempotent setup.sql, config and state schemas), Streamlit entrypoint with st.navigation() and sidebar, and foundational config storage.

### Story 1.1: Native App manifest and idempotent setup

As a Snowflake administrator (Maya),
I want the app to declare its required privileges and create schemas and tables in an idempotent way,
So that I can install from Marketplace and approve privileges without manual SQL, and upgrades do not break state.

**Acceptance Criteria:**

**Given** the app package is deployed to a consumer account  
**When** setup.sql runs (install or upgrade)  
**Then** manifest.yml uses manifest_version: 2 and declares all required privileges (IMPORTED PRIVILEGES ON SNOWFLAKE DB, EXECUTE TASK, EXECUTE MANAGED TASK, CREATE EXTERNAL ACCESS INTEGRATION)  
**And** setup.sql creates app_public (CREATE OR ALTER VERSIONED SCHEMA), _internal, _staging, _metrics (CREATE SCHEMA IF NOT EXISTS)  
**And** no DDL fails when run a second time (idempotent)

### Story 1.2: Config and state tables

As a developer (app backend),
I want _internal.config and related state tables to exist and be writable by the app,
So that destination and source settings can be persisted and read by pipelines and UI.

**Acceptance Criteria:**

**Given** setup.sql has been run  
**When** the app or pipeline code writes to _internal.config (key/value) or _internal.export_watermarks or _metrics.pipeline_health  
**Then** the tables exist and accept inserts/updates  
**And** config keys follow the convention (otlp.*, pack_enabled.*, source.<name>.*)  
**And** _staging.stream_offset_log exists (empty, for zero-row INSERT pattern)

### Story 1.3: Streamlit shell and navigation

As a Snowflake administrator (Maya),
I want to open the app and see a clear navigation (Getting started, Observability health, Telemetry sources, Splunk settings, Data governance) and an About dialog,
So that I can move between setup and monitoring without leaving Snowsight.

**Acceptance Criteria:**

**Given** the app is installed and opened in Snowsight  
**When** the Streamlit app loads  
**Then** main.py uses st.navigation() with sidebar order: Getting started (with progress badge placeholder), Observability health, Telemetry sources, Splunk settings, Data governance  
**And** Sidebar header shows "Splunk Observability" / "for Snowflake"  
**And** Footer has an "About" link that opens a st.dialog with app version, build info, and documentation links  
**And** Each nav item routes to the correct page (pages may be stubs)

---

## Epic 2: First-time setup and destination configuration

Maya can complete first-time setup by configuring the OTLP destination (endpoint, optional PEM, test connection, validate certificate) and saving settings; Getting Started hub and Splunk settings page work end-to-end.

### Story 2.1: OTLP endpoint and connection test

As a Snowflake administrator (Maya),
I want to enter the OTLP gRPC endpoint and run a connection test before saving,
So that I know the destination is reachable and avoid saving a broken configuration.

**Acceptance Criteria:**

**Given** I am on the Splunk settings page, Export settings tab  
**When** I enter an OTLP endpoint URL (e.g. https://collector.example.com:4317) and click "Test connection"  
**Then** the app attempts a gRPC connection (or health check) to that endpoint  
**And** I see a clear success (e.g. green "Connection successful") or error message (e.g. network/TLS error)  
**And** "Save settings" remains disabled until the test succeeds

### Story 2.2: Optional certificate and validation

As a Snowflake administrator (Maya),
I want to optionally paste a PEM certificate for a private/self-signed collector and validate it before saving,
So that TLS trust is confirmed and Save is only enabled when both connection and certificate (if provided) are valid.

**Acceptance Criteria:**

**Given** I am on the Export settings tab  
**When** I paste PEM content into the certificate text area and click "Validate certificate"  
**Then** the app validates the PEM and shows success (e.g. "Valid certificate (expires YYYY-MM-DD)") or an error  
**And** If I provided a certificate, "Save settings" is enabled only when both connection test and certificate validation have succeeded  
**And** If I leave certificate empty, Save is enabled when connection test succeeds (system trust store)

### Story 2.3: Persist destination config and Getting Started hub

As a Snowflake administrator (Maya),
I want to save the OTLP endpoint (and optional cert reference) to the app config and see Getting Started with task tiles and progress,
So that my destination is persisted and I can complete the rest of setup in order.

**Acceptance Criteria:**

**Given** connection test (and certificate validation if applicable) has succeeded  
**When** I click "Save settings"  
**Then** otlp.endpoint (and optional PEM secret reference or stored PEM path) is written to _internal.config  
**And** The Getting Started page shows 4 task tiles (Configure Splunk Settings, Select Telemetry Sources, Review Data Governance, Activate Export) with completed/pending state  
**And** Each tile uses st.container(border=True) with left column (green checkmark for completed, gray step number for pending), center (title + description), green "Completed" badge when done, and right column drill-down arrow  
**And** A progress bar shows "X of 4 tasks completed" with percentage  
**And** Task 1 (Configure Splunk Settings) is marked complete after save; progress badge shows 1/4  
**And** Clicking a tile (or its drill-down arrow) navigates to the corresponding page or modal via st.page_link

---

## Epic 3: Telemetry source selection and pack management

Maya can discover sources, enable packs, choose default or custom source per source, and set intervals/overlap; Telemetry sources page provides the data_editor and discovery.

### Story 3.1: Source discovery and pack toggles

As a Snowflake administrator (Maya),
I want to see available Event Tables and ACCOUNT_USAGE views (and custom views that reference them) and enable or disable Monitoring Packs,
So that I can choose what telemetry to export without writing SQL.

**Acceptance Criteria:**

**Given** I have the required Snowflake privileges  
**When** I open the Telemetry sources page  
**Then** The app discovers Event Tables (e.g. via INFORMATION_SCHEMA / SHOW EVENT TABLES) and supported ACCOUNT_USAGE views plus custom views that reference them  
**And** Categories (e.g. Distributed Tracing, Query Performance & Execution) are shown with collapsible headers and an enable toggle per category  
**And** Each category shows a count of enabled/total sources (e.g. "2/9")

### Story 3.2: Per-source selection and intervals

As a Snowflake administrator (Maya),
I want to select default or custom source per row, set execution interval, and for ACCOUNT_USAGE set overlap window,
So that I control what data is exported and how often it is polled.

**Acceptance Criteria:**

**Given** I am on the Telemetry sources page with sources discovered  
**When** I use the table (st.data_editor): Poll checkbox, View name, Source type, Interval (editable), Overlap (editable for ACCOUNT_USAGE only), Batch size (editable)  
**Then** I can select for each source either the default Snowflake source or a custom view/table (e.g. from a dropdown or selector)  
**And** Each source shows its default execution interval before I change anything  
**And** Interval is within published min/max bounds; Overlap defaults to documented max latency × 1.1 for AU sources  
**And** Changes are reflected in session_state and can be saved

### Story 3.3: Save source configuration

As a Snowflake administrator (Maya),
I want to save my source and pack configuration and see an unsaved changes indicator until I save,
So that I do not lose changes and know when the app state matches the UI.

**Acceptance Criteria:**

**Given** I have changed pack toggles, source selection, or intervals on Telemetry sources  
**When** I have not yet saved  
**Then** A footer or banner shows "You have unsaved changes" and "Save configuration" (primary) is available  
**When** I click "Save configuration"  
**Then** pack_enabled.* and source.<name>.* keys (view_fqn, source_type, poll_interval_seconds, overlap_minutes, etc.) are written to _internal.config  
**And** The unsaved indicator clears and session_state is synced with config

---

## Epic 4: Data governance review and activation

Maya can review governance per source, acknowledge disclosure when using default sources, and activate export so the app provisions tasks, streams, and network objects.

### Story 4.1: Data governance page

As a security or compliance reviewer,
I want to see a read-only list of enabled sources with governance message and sensitive columns per row,
So that I can verify governance posture without editing anything.

**Acceptance Criteria:**

**Given** At least one source is enabled  
**When** I open the Data governance page  
**Then** A read-only table shows enabled sources only with columns: Status, View name, Source type, Governance (per-row message), Sensitive columns (per-row list)  
**And** Category headers match Telemetry sources (with status dot, no toggle)  
**And** Governance message states for default source that masking/row access require a custom view; for custom source that Snowflake policies apply  
**And** An "Agree" button is shown to record governance acknowledgement (required during Getting Started flow; re-confirmable later)

### Story 4.2: Governance disclosure and acknowledgement

As a Snowflake administrator (Maya),
I want to see a blocking disclosure when I have selected a default source and must acknowledge before export is enabled,
So that I understand governance implications before activating.

**Acceptance Criteria:**

**Given** At least one enabled source is a default ACCOUNT_USAGE view or Event Table  
**When** I attempt to activate export (or complete the governance task in Getting Started)  
**Then** The app shows a blocking disclosure that masking and row access policies cannot be applied to default sources and that a custom source is required for governance  
**And** I must explicitly acknowledge (e.g. "Agree" or checkbox) before activation can proceed  
**And** The acknowledgement is recorded (e.g. in config or session_state)

### Story 4.3: Activate export provisioning

As a Snowflake administrator (Maya),
I want to click "Enable Auto-Export" and have the app create tasks, streams, and network/secret objects,
So that telemetry starts flowing without me running SQL or scripts.

**Acceptance Criteria:**

**Given** OTLP destination is configured, at least one source is enabled, and governance is acknowledged  
**When** I open the Activate Export modal (st.dialog) from the Getting Started tile or equivalent  
**Then** The modal shows header "Activate Telemetry Export" with rocket icon, an info box ("What will happen"), a bullet list of objects to be created (scheduled tasks, streams, network rules, secret objects), a "Cancel" (secondary) button, and "Enable Auto-Export" (primary) button  
**When** I click "Enable Auto-Export"  
**Then** The app provisions the following Snowflake objects from the saved source configuration:  
**And** For each enabled Event Table source: an APPEND_ONLY stream on the user-selected source (view or event table) with naming convention _splunk_obs_stream_<source_name>, and a triggered task (WHEN SYSTEM$STREAM_HAS_DATA) that calls the Event Table collector procedure, named _splunk_obs_task_<source_name>  
**And** For each enabled ACCOUNT_USAGE source: an independent serverless scheduled task with source-specific interval that calls the ACCOUNT_USAGE collector procedure, named _splunk_obs_task_<source_name>; an initial watermark row in _internal.export_watermarks  
**And** EAI + Network Rules for OTLP egress, and optional Snowflake Secret reference for custom PEM certificate  
**And** I see in-progress feedback (spinner on button, Cancel disabled) and then success (modal closes, st.success toast) or a clear error with retry option  
**And** After success, Getting Started task 4 is complete and (when all 4 are complete and I navigate away) Getting started is removed from the sidebar  

**Implementation note:** The stored procedures referenced by tasks (event_table_collector, account_usage_collector) are registered in setup.sql (Story 1.1). Their Python handler implementations are delivered by Epic 5. This story creates the DDL infrastructure; Epic 5 implements the handler behavior.

---

## Epic 5: Collection pipeline handlers

Sam (via automated pipelines) gets incremental Event Table export with entity scoping, and independent ACCOUNT_USAGE collection with watermark, overlap, and dedup. This epic implements the Python handler code for the stored procedures that are registered in setup.sql (Story 1.1) and whose tasks are provisioned by Story 4.3.

### Story 5.1: Event Table collector procedure

As an operator (Sam),
I want the Event Table collector to read from the stream, filter to MVP entity types, and hand off to export,
So that only SQL/Snowpark compute telemetry is processed and exported.

**Acceptance Criteria:**

**Given** The Event Table triggered task fires (stream has data, task provisioned by Story 4.3)  
**When** The collector procedure executes  
**Then** It sets session.sql_simplifier_enabled = True, loads config from _internal.config (otlp.endpoint, batch settings)  
**And** Within an explicit BEGIN/COMMIT transaction: reads from the stream using Snowpark DataFrame, applies entity discrimination filter (snow.executable.type IN procedure, function, query, sql) as the first pushdown operation  
**And** It uses to_pandas_batches() for bounded memory; calls the OTLP export layer (Story 6.1) with each batch  
**And** Advances the stream via zero-row INSERT into _staging.stream_offset_log within the same transaction  
**And** Records run metrics to _metrics.pipeline_health (rows_collected, rows_exported, rows_failed, export_latency_ms, duration_ms)  
**And** Emits structured log events via Native App event definitions (pipeline, source, run_id, duration_ms, error_code)  
**And** When the user-selected source is a custom view with masking, row access, or projection policies, exported data reflects those policies (Snowflake enforces at read time)  
**And** If a column expected by the enrichment layer is NULL or missing (e.g. due to projection policy), the pipeline continues with that field as NULL and records a warning for the affected run in _metrics.pipeline_health

### Story 5.2: ACCOUNT_USAGE collector procedure

As an operator (Sam),
I want the ACCOUNT_USAGE collector to query the selected source with watermark and overlap, map rows to OTLP log/event, update the watermark, and record health,
So that performance telemetry is exported incrementally and reliably.

**Acceptance Criteria:**

**Given** An ACCOUNT_USAGE scheduled task fires (task provisioned by Story 4.3)  
**When** The collector procedure executes  
**Then** It sets session.sql_simplifier_enabled = True, loads config from _internal.config (otlp.endpoint, source view_fqn, overlap_minutes, batch_size)  
**And** Reads the current watermark from _internal.export_watermarks for this source  
**And** Runs a Snowpark query with: overlap window (WHERE ts > watermark - INTERVAL overlap_minutes), latency cutoff (AND ts <= NOW() - INTERVAL overlap_minutes), dedup (QUALIFY ROW_NUMBER() OVER (PARTITION BY natural_key ORDER BY ts DESC) = 1), and batch limit  
**And** Uses to_pandas_batches() to map rows to OTLP log/event format with source-specific attributes and mandatory routing fields (source identity, Snowflake account identity, telemetry type); calls the OTLP export layer (Story 6.1) with each batch  
**And** Updates the watermark in _internal.export_watermarks after successful export  
**And** Records run metrics to _metrics.pipeline_health; emits structured log events via Native App event definitions  
**And** When the user-selected source is a custom view with masking, row access, or projection policies, exported data reflects those policies (Snowflake enforces at read time)  
**And** If a column expected by the mapping is NULL or missing (e.g. due to projection policy), the pipeline continues with that field as NULL and records a warning for the affected run in _metrics.pipeline_health

---

## Epic 6: OTLP export and Splunk-ready telemetry

Sam can deliver all telemetry via OTLP; Ravi can analyze spans in Splunk with correct conventions; retry and terminal failure handling behave as specified.

### Story 6.1: OTLP gRPC exporter module

As a developer (backend),
I want a single OTLP gRPC export module with module-level exporter init and TLS support,
So that all collectors can send telemetry without duplicating connection logic and connections are reused within the sandbox.

**Acceptance Criteria:**

**Given** The app has otlp.endpoint (and optional PEM secret reference) in config  
**When** The export module is first used in a task  
**Then** OTLP exporters (Span, Metric, Log for Event Table; Log for ACCOUNT_USAGE) are initialized at module level with TLS credentials (default CA or custom PEM from secret)  
**And** Export uses gRPC over TLS only; no plaintext OTLP  
**And** SimpleSpanProcessor (or equivalent) is used so export completes within the procedure lifecycle

### Story 6.2: Event Table span and log mapping

As an SRE (Ravi),
I want exported Event Table spans to include db.* and snowflake.* attributes and to preserve all original attributes,
So that I can trace and search in Splunk APM with correct context and no attribute loss.

**Acceptance Criteria:**

**Given** Event Table rows are read by the collector  
**When** They are mapped to OTLP spans/logs/metrics  
**Then** db.system.name, db.namespace, db.operation.name, db.stored_procedure.name, and other db.* and snowflake.* attributes are set per OTel and project conventions  
**And** Original Event Table attributes are preserved (convention-transparent relay); no renaming or removal  
**And** Mandatory routing fields (source identity, Snowflake account identity, telemetry type, service/resource identity) are present

### Story 6.3: Retry and terminal failure handling

As an operator (Sam),
I want retryable OTLP errors to be retried automatically and non-retryable errors to be recorded as terminal without endless retry,
So that transient failures recover and permanent failures are visible and do not spin.

**Acceptance Criteria:**

**Given** The OTLP export layer is sending a batch  
**When** A retryable error occurs (e.g. temporary network failure)  
**Then** The OTel SDK (or app) retries according to the defined policy (e.g. ~6 attempts over ~63s)  
**When** Retries are exhausted or a non-retryable error occurs  
**Then** The failure is logged (Native App event definitions) and recorded as a terminal batch failure in _metrics.pipeline_health  
**And** The pipeline advances (e.g. stream consumed or watermark updated) so the next run does not re-send the same batch indefinitely

---

## Epic 7: Pipeline operations and observability health

Sam can view health summary, destination and per-source status, operational events, auto-recovery, and auto-suspend; Observability health page and Telemetry sources health columns are implemented.

### Story 7.1: Pipeline health recording and operational logs

As an operator (Sam),
I want each pipeline run to write metrics to _metrics.pipeline_health and structured events to the app event table,
So that I can monitor success/failure and diagnose issues in Snowsight.

**Acceptance Criteria:**

**Given** A collector (Event Table or ACCOUNT_USAGE) completes a run  
**When** The run finishes (success or failure)  
**Then** Rows are inserted into _metrics.pipeline_health (e.g. rows_collected, rows_exported, rows_failed, export_latency_ms, error_count, source_lag_seconds)  
**And** Structured log events are emitted via Native App event definitions (pipeline, source, run_id, duration_ms, error_code when applicable)  
**And** No secret or credential values appear in metrics or logs

### Story 7.2: Observability health page

As an operator (Sam),
I want the Observability health page to show destination status, aggregated KPIs, throughput chart, and category summary with drill-down,
So that I can answer "is everything OK?" in seconds.

**Acceptance Criteria:**

**Given** At least one source has run and written to _metrics.pipeline_health  
**When** I open the Observability health page  
**Then** I see: destination health card (OTLP status, endpoint, last export), four st.metric KPIs (Sources OK, Rows exported 24h, Failed batches 24h, Avg freshness), Export Throughput chart (24h/7d), and Category Health Summary table with "View →" to Telemetry sources  
**And** Data is computed on page load or manual refresh only (no live polling)  
**And** If no pipelines are configured, the Empty State is shown (message + optional link to Getting started)

### Story 7.3: Telemetry sources per-source health columns

As an operator (Sam),
I want the Telemetry sources table to show per-source status, freshness sparkline, recent runs, and errors (24h),
So that I can drill into which source is failing or lagging.

**Acceptance Criteria:**

**Given** I am on the Telemetry sources page  
**When** The page loads  
**Then** Each source row shows: Status (green/amber/red dot), Freshness (sparkline or lag value), Recent runs (net score or success/failure count), Errors (24h) when > 0  
**And** Category header status roll-up follows the defined rules (green/amber/red/gray)  
**And** Optional "View log" or similar links to Snowsight for that task’s logs

### Story 7.4: Stale stream recovery and auto-suspend

As an operator (Sam),
I want the Event Table pipeline to detect a stale stream, recreate it, and record a data gap; and failing tasks to auto-suspend after N failures,
So that I do not have to manually fix streams and one bad source does not spin forever.

**Acceptance Criteria:**

**Given** The Event Table stream has become stale (e.g. task suspended longer than stream retention)  
**When** The triggered task runs  
**Then** The collector detects staleness (e.g. via DESCRIBE STREAM), drops and recreates the stream on the user-selected source, records the data gap (source and time window) in _metrics.pipeline_health, and logs the recovery event  
**And** Export resumes for new data within 10 minutes or 2 scheduled executions (whichever is longer) without manual action  
**Given** An ACCOUNT_USAGE (or Event Table) task fails repeatedly  
**When** Failures exceed the configured threshold (e.g. SUSPEND_TASK_AFTER_NUM_FAILURES)  
**Then** Only that task is suspended; other sources continue  
**And** The Telemetry sources page shows the suspended status for that source

### Story 7.5: Recent errors feed and empty state

As an operator (Sam),
I want to see a recent errors feed on Observability health when there are errors, and a clear empty state when no pipelines exist,
So that I can act on failures quickly and understand when setup is incomplete.

**Acceptance Criteria:**

**Given** There is at least one error in the last 24h  
**When** I am on the Observability health page  
**Then** A "Recent Errors" section shows timestamp, source name, and error message with a "View all in Snowsight" link  
**Given** No sources are enabled or no pipeline has ever run  
**When** I open Observability health  
**Then** An empty state is shown (e.g. st.info or st.warning) with message like "Complete Getting started to see pipeline health" and optional link to Getting started

---

## Epic 8: App lifecycle and Marketplace release

Tom can publish upgrades and submit for Marketplace approval; Maya retains config across upgrades; upgrade events are visible.

### Story 8.1: Versioned and stateful schema upgrade

As a release manager (Tom),
I want setup.sql to use versioned schema for app_public and stateful schemas for _internal, _staging, _metrics,
So that upgrades recreate only stateless objects and preserve config, watermarks, and health data.

**Acceptance Criteria:**

**Given** A new app version is deployed  
**When** setup.sql runs  
**Then** app_public is created or altered with CREATE OR ALTER VERSIONED SCHEMA  
**And** _internal, _staging, _metrics use CREATE SCHEMA IF NOT EXISTS and are not dropped  
**And** Existing rows in _internal.config, _internal.export_watermarks, and _metrics.pipeline_health remain after upgrade

### Story 8.2: Upgrade continuity and upgrade events

As a Snowflake administrator (Maya),
I want configuration and pipeline progress to survive upgrades and to see upgrade progress in the event table,
So that I do not have to reconfigure and operators can verify upgrade success.

**Acceptance Criteria:**

**Given** I have configured the app and run pipelines  
**When** I upgrade to a supported new version  
**Then** _internal.config and _internal.export_watermarks are unchanged; tasks and streams are recreated from config where needed  
**And** In-flight scheduled work completes or resumes with at most one missed run per source  
**And** Upgrade progress or completion is written to the Snowflake event table (e.g. via Native App event definitions) so Sam can query it in Snowsight

### Story 8.3: Marketplace packaging and submission readiness

As a release and compliance lead (Tom),
I want a multi-package build (dev → scan → test → prod), security scan pass, and reviewer guidance so I can submit for Marketplace approval,
So that the release meets Snowflake security and functional review requirements.

**Acceptance Criteria:**

**Given** The team has a release candidate  
**When** Tom runs the packaging and scan workflow  
**Then** Build produces packages for dev (INTERNAL), scan (EXTERNAL), test (INTERNAL), prod (EXTERNAL) as defined  
**And** The scan package passes Snowflake security review (zero Critical/High findings)  
**And** Reviewer guidance (README, test steps, sample data, credentials if needed) is complete so a consumer-account install and configuration test can be run  
**And** Tom can attach the approved version to the listing and submit for approval after consumer-account validation
