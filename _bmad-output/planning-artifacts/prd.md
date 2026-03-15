---
stepsCompleted: [step-01-init, step-02-discovery, step-03-success, step-04-journeys, step-05-domain, step-06-innovation, step-07-project-type, step-08-scoping, step-09-functional, step-10-nonfunctional, step-11-polish, step-12-complete]
status: complete
inputDocuments:
  - _bmad-output/planning-artifacts/product-brief-snowflake-native-splunk-app-2026-02-15.md
  - _bmad-output/planning-artifacts/ux-design-specification.md
  - _bmad-output/planning-artifacts/splunk_snowflake_native_app_vision.md
  - _bmad-output/planning-artifacts/streamlit_component_compatibility_snowflake.csv
  - _bmad-output/planning-artifacts/snowflake_data_governance_privacy_features.md
  - _bmad-output/planning-artifacts/event_table_streams_governance_research.md
  - _bmad-output/planning-artifacts/otel_semantic_conventions_snowflake_research.md
  - _bmad-output/planning-artifacts/event_table_entity_discrimination_strategy.md
workflowType: 'prd'
documentCounts:
  briefs: 1
  research: 4
  projectDocs: 5
  projectContext: 0
classification:
  projectType: saas_b2b (Snowflake Native App)
  domain: Cloud Infrastructure / Observability
  complexity: high
  projectContext: greenfield
date: 2026-02-15
---

# Product Requirements Document - snowflake-native-splunk-app

**Author:** Nikita Voitov (Cisco)
**Date:** 2026-02-15

## Executive Summary

**Splunk Observability for Snowflake** is a Snowflake Native App distributed via the Snowflake Marketplace that exports Snowflake telemetry — distributed traces, metrics, logs, and operational events — to Splunk Observability Cloud and Splunk Enterprise with zero external infrastructure. Install from Marketplace, configure in Streamlit, observe in Splunk — in under 15 minutes.

**Product Differentiator:** The only observability bridge that runs entirely inside the consumer's Snowflake account using serverless compute, user-selected sources with clear governance guidance, and additive OTel semantic convention enrichment — replacing external OTel Collectors, DB Connect pipelines, and custom ETL with a single Marketplace install.

**Target Users:** Snowflake Administrators (Maya) who manage Snowflake accounts and need telemetry in Splunk, SREs (Ravi) who need distributed traces through the Snowflake boundary, and DevOps engineers (Sam) who monitor pipeline health.

**MVP Scope:** Distributed Tracing Pack (Event Table → OTLP/gRPC) and Performance Pack (ACCOUNT_USAGE → OTLP), with user-selected sources, Streamlit configuration UI (Getting Started, Observability health view, Telemetry sources, Splunk settings with OTLP export, Data governance page), and app operational logging.

## Existing players



## Success Criteria

### User Success

| Criteria | Target | How We Know |
|---|---|---|
| **Time to first telemetry** | < 15 minutes from Marketplace install to first data visible in Splunk | Measured end-to-end: "Get" click → privilege binding → pack selection → first span/event in Splunk |
| **Zero manual pipelines** | Replaces all manual Snowflake-to-Splunk data pipelines (DB Connect, custom ETL, OTel Collector scraping) | Customer self-reported before/after comparison |
| **MTTR reduction** | 50% reduction in Mean Time to Resolution for Snowflake-related issues | Enabled by Splunk's cross-system correlation — Snowflake telemetry correlated with application, service, and infrastructure data |
| **Context-switching eliminated** | SREs investigate Snowflake issues entirely within Splunk APM/Enterprise along with the rest of their non-Snowflake infra | Qualitative: end-to-end traces through Snowflake boundary visible in single Splunk view |
| **Pipeline parity** | Export latency and reliability at least equal to equivalent OTel Collector-based pipelines | Benchmarked: Event Table → Splunk latency vs external OTel Collector → Splunk latency |

**Emotional Success Moments:**
- **Ravi (SRE):** Clicks a slow span in Splunk APM and sees it's a Snowflake UDF — with warehouse name, query ID, and execution context in span attributes. The Snowflake black box is gone.
- **Maya (Admin):** Receives a Splunk alert at 10:15 AM about a 3x warehouse credit spike before anyone on the analytics team notices. She right-sizes the warehouse before finance sees the bill.

### Business Success

| Metric | Target | Timeframe |
|---|---|---|
| **Marketplace listing live** | App listed and approved on Snowflake Marketplace | MVP launch |
| **Active installs** | 5+ accounts with active pipelines | 6 months post-launch |
| **New customer acquisition** | At least 1 new Splunk customer via Snowflake Marketplace channel | 12 months post-launch |
| **Marketplace Partner Milestone 1** | Complete all deliverables → unlock Snowflake marketing support | 3 months post-listing |
| **Marketplace Partner Milestone 2** | Complete all deliverables → unlock marketing funding + co-marketing | 9 months post-listing |

### Technical Success

| Criteria | Target | Measurement |
|---|---|---|
| **Export success rate** | >= 99.5% batches exported successfully (transport retries included) | `_metrics.pipeline_health` — rows_exported vs rows_collected |
| **Event Table export latency** | < 60 seconds from Event Table write to data visible in Splunk | Stream trigger (30s) + export processing. Parity with OTel Collector. |
| **ACCOUNT_USAGE freshness** | Data in Splunk within 1 polling cycle of Snowflake's inherent view latency | e.g., QUERY_HISTORY (45 min latency) in Splunk within ~75 min |
| **Pipeline uptime** | 99.9% (< 8.7 hours downtime/year) | Per-source via last successful run timestamp |
| **Zero data loss (happy path)** | 100% telemetry rows exported when Splunk endpoints are reachable | Stream checkpointing + watermark tracking |
| **Security scan** | APPROVED status on all versions submitted for Marketplace | Automated scan via DISTRIBUTION=EXTERNAL |
| **Zero P1/P2 bugs** | No Priority 1/2 defects open at Marketplace submission | Issue tracker |
| **No critical/high CVEs** | All dependencies CVE-free at Critical/High severity | Dependency audit |

### Measurable Outcomes

**3-Month Outcomes (MVP Launch):**
- App live on Snowflake Marketplace with APPROVED security scan
- Distributed Tracing Pack and Performance Pack fully operational
- E2E user workflow verified across cross-account test installs
- Marketplace Partner Milestone 1 content piece published

**6-Month Outcomes:**
- 5+ active installs with at least 1 Monitoring Pack enabled
- 3 Joint Customer Win Wires submitted to Snowflake
- Export latency benchmarked and documented vs OTel Collector baseline

**12-Month Outcomes:**
- At least 1 new Splunk customer acquired through Marketplace channel
- Publicly referenceable Customer Success Story submitted
- Post-MVP packs (Cost, Security) in development or released

## Product Scope

### MVP — Minimum Viable Product

**Target Ship Date:** Mid-March 2026 (1 month)

**Core Deliverables:**
1. **Distributed Tracing Pack** — Event Table telemetry scoped to **SQL/Snowpark compute** (stored procedures, UDFs/UDTFs, SQL queries) via entity filter (`snow.executable.type IN ('procedure','function','query','sql')`). Spans/metrics/logs → OTLP/gRPC to a remote OpenTelemetry collector (e.g. Splunk distribution). OTel DB Client `db.*` semantic conventions + custom `snowflake.*` namespace.
2. **Performance Pack** — QUERY_HISTORY, TASK_HISTORY, COMPLETE_TASK_GRAPHS, LOCK_WAIT_HISTORY → OTLP/gRPC to the same remote OpenTelemetry collector. The collector routes data to Splunk Observability Cloud (traces/metrics) and Splunk Enterprise/Cloud (logs).
3. **User-Selected Sources** — For each data source (Event Tables and ACCOUNT_USAGE), the user selects the telemetry source: either their own custom view (with masking/row access policies attached) or the default view/event table. The app does not create or maintain any views. Serverless tasks read or stream from the user selected sources. When the user selects a default ACCOUNT_USAGE view or event table, the **Data governance page** informs them that masking and row access policies cannot be applied to those sources and that they must create their own custom views to enforce governance.
4. **Streamlit Configuration UI** — Five main pages via `st.navigation`: (1) **Getting Started** (tile hub with drill-down, visible until onboarding complete), (2) **Observability health** (helicopter view with destination health, aggregated KPIs, throughput chart, category summary, errors feed), (3) **Telemetry sources** (`st.data_editor` with category headers, per-source health columns, editable interval/batch), (4) **Splunk settings** (Export settings tab with single OTLP endpoint, optional PEM certificate, Test connection), (5) **Data governance** (read-only table of enabled sources with Status, View name, Source type, Governance message, Sensitive columns).
5. **Observability Health Dashboard** — Helicopter view with destination health card (OTLP status), 4 aggregated KPI cards (Sources OK, Rows exported 24h, Failed batches 24h, Avg freshness), export throughput trend chart, category health summary table with drill-down to Telemetry sources, and recent errors feed. Per-source detail lives on Telemetry sources page. *(Volume estimator deferred to post-MVP.)*
6. **App Operational Logging** — The app writes structured operational logs (errors, warnings, info, debug) to the consumer's account-level event table using Snowflake's Native App [event definition](https://docs.snowflake.com/en/developer-guide/native-apps/event-definition) framework (`log_level` and `trace_level` configured in `manifest.yml`). Consumers query the event table directly via Snowsight for pipeline debugging and error analysis. *(Streamlit Logging tab — verbosity selector, scrollable display, keyword search — deferred to post-MVP.)*
7. **Dual-Pipeline Architecture** — Event-driven (User-Selected Source → Stream → Serverless Triggered Task) for Event Tables (stream on user's view or on event table); poll-based (User-Selected Source → Independent Serverless Scheduled Tasks + Watermarks) for ACCOUNT_USAGE (read from user's view or default view). Each ACCOUNT_USAGE source gets its own independent task with a source-specific schedule. Stale Event Table streams are auto-recovered by the app (drop/recreate stream on the selected source — data gap recorded in pipeline_health). All telemetry is exported via **single OTLP/gRPC endpoint** to a remote Splunk OTEL collector or Splunk Observability Cloud.
8. **Marketplace-Ready Packaging** — manifest.yml v2, marketplace.yml, setup.sql, README.md, environment.yml, security scan APPROVED (manual scan on test build per Snowflake Marketplace [automated security scan workflow](https://docs.snowflake.com/en/developer-guide/native-apps/security-run-scan)).

**MVP Go/No-Go Gates:** 
- GO gates:Functional (E2E workflows), Performance (latency parity with OTel Collector), Quality (zero P1/P2), Marketplace Compliance (security scan, enforced standards).
- No-GO gates: slow telemetry data processing/export performance.

### Growth & Vision (Post-MVP)

*Detailed phased roadmap with priorities and dependencies is documented in [Project Scoping & Phased Development](#project-scoping--phased-development).*

**Phase 2 — Growth:** Streamlit Logging tab, enhanced Data governance page (classification awareness, policy detection), volume estimator, Cost Pack, Security Pack, zero-copy failure tracking, advanced Observability health dashboard.

**Phase 3 — Expansion:** Additional Event Table service categories (SPCS, Streamlit), Openflow Pack (Event Table telemetry with `RESOURCE_ATTRIBUTES:"application" = 'openflow'`), Cortex AI Pack (dedicated `AI_OBSERVABILITY_EVENTS` table with `gen_ai.*` conventions), bi-directional integration (Splunk alerts → Snowflake actions), multi-tenant scale (100+ concurrent installs). Integration with Cortex AI services.

## User Journeys

### Journey 1: Maya's First Day — Install, Configure, Observe (Happy Path)

**Persona:** Maya — Senior Snowflake Administrator, 50+ warehouses, hundreds of users across analytics, data engineering, ML, and application development teams.

**Opening Scene:** It's Monday morning. Maya's inbox has three tickets from the analytics team about slow queries over the weekend, and her manager just forwarded an email from finance asking why last month's Snowflake bill was 40% higher than projected. She sighs — her morning ritual of manually querying ACCOUNT_USAGE views in Snowsight begins. She opens QUERY_HISTORY, filters for long-running queries, exports to CSV, and pastes the results into a ticket. Then she opens WAREHOUSE_METERING_HISTORY and repeats the process for cost data. None of this reaches the Splunk dashboards her ops team actually monitors.

**Rising Action:**
1. Maya navigates to the Snowflake Marketplace and searches for "Splunk observability." She finds **Splunk Observability for Snowflake** and clicks "Get." The app installs in her account in seconds — no region restrictions, no external infrastructure.
2. On first launch, the Streamlit UI shows the **Getting Started** page — a tile hub with progress indicator (e.g. "0/4 completed") in the sidebar. The Python Permission SDK presents native Snowsight privilege prompts — she clicks "Grant" for IMPORTED PRIVILEGES ON SNOWFLAKE DB.
3. Maya drills into the **Splunk settings** tile → **Export settings** tab. She enters her **OTLP endpoint** (gRPC URL with port) pointing to her remote OpenTelemetry collector (e.g. Splunk distribution). Optionally she pastes a **PEM certificate** for a collector using a private/self-signed cert. **Test connection** validates OTLP reachability.
4. Maya drills into the **Telemetry sources** tile. She sees the `st.data_editor` table grouped by category (Distributed Tracing, Query Performance & Execution). She enables sources, selects custom views or defaults, and adjusts intervals as needed.
5. Behind the scenes: the app provisions networking (EAI + Network Rule) and creates **independent serverless scheduled tasks** — one per ACCOUNT_USAGE source, each reading from the **source Maya selected** (her custom view or the default ACCOUNT_USAGE view). Maya sees the **Observability health** page update — green status indicators appear in the category summary.
6. The **Data governance** page shows the selected source per category (e.g. her custom view or default QUERY_HISTORY). When a default view is selected, the per-row governance message **informs** her that masking and row access policies cannot be applied to that source and that to enforce governance she must create her own custom view and select it as the source. When she has selected a custom view, policies on that view are honored automatically.

**Climax:** Seven minutes after clicking "Get," Maya opens Splunk. QUERY_HISTORY data is already flowing via her OTEL collector. She creates an alert for queries exceeding 5 minutes and a dashboard for warehouse credit consumption trends. The data that was trapped in Snowsight is now in her team's primary operational platform.

**Resolution:** Maya's morning manual review is replaced by proactive Splunk alerts. The cost report that took her 45 minutes every Monday is now a live Splunk dashboard that updates automatically. When the next warehouse spike happens, she gets a Splunk alert at 10:15 AM — before anyone else notices — and right-sizes the warehouse in minutes.

**Capabilities Revealed:** Marketplace install, Streamlit privilege binding (Permission SDK), Getting Started hub with drill-down, Telemetry sources `st.data_editor` with category headers and per-source health, per-source selection (custom view or default), per-source schedule interval display and inline modification, OTLP destination configuration (Splunk settings → Export settings tab), independent scheduled task provisioning (reading from user-selected source), Data governance page (per-row governance message when default selected), Observability health helicopter view.

---

### Journey 2: Ravi Traces Through the Snowflake Boundary (Happy Path)

**Persona:** Ravi — SRE on a platform engineering team. Responsible for the reliability of business-critical applications that depend on Snowflake — ML pipelines, real-time analytics APIs, Snowpark stored procedures.

**Opening Scene:** 2:47 AM. PagerDuty fires. The ML scoring API is returning 504s. Ravi opens Splunk Observability Cloud and pulls up the trace for a failed request. He follows the trace from the API gateway → Kubernetes service → ... and then the trace just stops. The next hop is a Snowflake stored procedure that runs a critical ML scoring UDF, but its spans are in a Snowflake Event Table — invisible from Splunk. Ravi context-switches to Snowsight, manually queries the Event Table by timestamp, and tries to correlate. It takes him 35 minutes to find the root cause: the UDF hit a warehouse queuing bottleneck.

**Rising Action:**
1. After the postmortem, Ravi's team installs **Splunk Observability for Snowflake** from the Marketplace (Maya, their admin, handled the install and privilege binding).
2. Ravi opens the app and navigates to **Telemetry sources** (via sidebar). He sees the `st.data_editor` table with category headers. Under **Distributed Tracing**, he enables the Event Table (`SNOWFLAKE.TELEMETRY.EVENTS`). The UI displays an informational banner: "This release processes **SQL/Snowpark compute telemetry** (SQL queries, stored procedures, UDFs, UDTFs). Telemetry from other Snowflake services (SPCS, Streamlit, Cortex AI) is filtered out." The Event Table source shows its **default stream polling interval** (e.g., 30 seconds) — Ravi can modify it inline in the Interval column.
3. Ravi navigates to **Splunk settings** → **Export settings** tab. He enters the **OTLP endpoint** (gRPC URL with port) pointing to their remote OTEL collector. **Test connection** validates reachability.
4. Ravi selects the telemetry source on **Telemetry sources** — either **his team's governed view** (a custom view over the Event Table with policies attached) or the **event table** directly. The app creates an **append-only stream** on the selected source (view or table) and provisions a **serverless triggered task**. The pipeline's entity filter targets `snow.executable.type IN ('procedure','function','query','sql')` — only SQL/Snowpark compute telemetry is collected and transformed. Within minutes, spans begin flowing via OTLP/gRPC with OTel DB Client semantic conventions (`db.system.name = "snowflake"`, `db.namespace`, `db.operation.name`, `db.stored_procedure.name`, `snowflake.warehouse.name`, `snowflake.query.id`). If he selected the event table directly, the **Data governance** page per-row message informs him that masking cannot be applied on event tables and he can use a custom view for governance.
5. Ravi opens Splunk APM. For the first time, he sees Snowflake stored procedure spans stitched into the same traces as the rest of his application — the Snowflake boundary is transparent. The spans carry `db.system.name = "snowflake"` and Splunk's DB monitoring views recognize them natively.

**Climax:** Two weeks later, 3:12 AM. PagerDuty fires again. Ravi opens Splunk APM, pulls up the trace, and this time the trace continues *through* Snowflake. He clicks on the slow span — it's a Snowflake UDF. The span attributes show `snowflake.warehouse.name: ML_SCORING_WH`, `snowflake.query.id`, `db.operation.name: CALL`, `db.stored_procedure.name: ML_SCORING_UDF`, and duration breakdown. He sees the UDF waited 8 seconds in warehouse queue. Root cause identified in under 3 minutes — no Snowsight context-switching, no manual Event Table queries.

**Resolution:** Ravi's MTTR for Snowflake-related incidents drops from 35+ minutes to under 5 minutes. The Snowflake black box is gone. His team adds Snowflake-side SLOs in Splunk APM — if any stored procedure exceeds its latency budget, they know immediately and can see exactly why.

**Capabilities Revealed:** Telemetry sources `st.data_editor` with category headers and per-source health, per-source selection (user's governed view or event table), entity discrimination (SQL/Snowpark compute scope), stream polling interval display and inline modification, OTel DB Client convention enrichment (`db.*` + `snowflake.*`), Distributed Tracing Pack configuration, OTLP/gRPC destination setup (Splunk settings → Export settings tab), stream creation on selected source (view or table), triggered task provisioning, span export to Splunk via OTLP.

---

### Journey 3: Maya & Ravi — When Things Go Wrong (Edge Cases)

**Persona:** Maya and Ravi, now regular users of the app, face critical failure scenarios.

#### Scenario A — OTLP Endpoint Down (All Telemetry)

**Opening Scene:** The remote OpenTelemetry collector (e.g. Splunk distribution) undergoes scheduled maintenance. The OTLP/gRPC endpoint is unreachable for 2 hours. All telemetry export is affected — both Performance Pack (ACCOUNT_USAGE) and Distributed Tracing Pack (Event Table spans/metrics/logs).

**Rising Action:**
1. The `account_usage_source_collector` for QUERY_HISTORY reads from the **selected source** (Maya's custom view or default ACCOUNT_USAGE.QUERY_HISTORY) and attempts to export via OTLP/gRPC. The OTel SDK's built-in gRPC retry kicks in — exponential backoff (1s, 2s, 4s, 8s, 16s, 32s — ~6 retries over ~63s) for transient gRPC errors (UNAVAILABLE, DEADLINE_EXCEEDED). All retries exhaust.
2. Simultaneously, the `event_table_collector` reads from the stream on the **selected source** (user's view or event table) and attempts to export spans/metrics/logs via OTLP. Same OTel SDK retry pattern. All retries exhaust.
3. Both failures are logged in `_metrics.pipeline_health` with error details (gRPC UNAVAILABLE or connection refused, timestamps, row counts, source name).
4. **Critical MVP trade-off:** For the poll-based pipeline, the watermark advances — the ACCOUNT_USAGE batch is lost. For the event-driven pipeline, the stream offset advances (zero-row INSERT pattern) — the Event Table batch is lost.
5. The **Observability health** page updates: the "Failed Batches" KPI card increments; the destination health card shows OTLP status as red; category summary shows affected categories with amber/red status.

**Recovery:** OTLP endpoint recovers. Next scheduled runs succeed. Data from the outage window is permanently missing in MVP. Post-MVP: zero-copy failure tracking will record references for failed batches and a dedicated retry task will re-export them.

**Climax:** Maya documents the data gaps and the MVP trade-off in her runbook. She sets up Splunk alerts on the `_metrics.pipeline_health` table to detect export failures in real time — so the team knows immediately rather than discovering gaps during incident investigation.

**Resolution:** The team understands the MVP boundary: transport-level retries handle transient blips (seconds), but sustained outages (minutes to hours) create data gaps. The **Observability health** helicopter view is their early warning system. Post-MVP failure tracking will close this gap.

#### Scenario B — Event Table Stream Goes Stale

**Opening Scene:** Ravi's team temporarily suspends the app's triggered task during a major Snowflake migration. The suspension lasts longer than expected — 16 days. The append-only stream on the **selected source** (user's view or event table) exceeds `MAX_DATA_EXTENSION_TIME_IN_DAYS` (14 days) and goes stale.

**Rising Action:**
1. When the task is resumed, the triggered task detects the stale stream condition (`SYSTEM$STREAM_HAS_DATA()` returns an error).
2. **Automatic recovery:** The app's task logic catches the staleness error, drops the stale stream, and recreates a new append-only stream on the **same selected source** (view or event table). The new stream starts from the current table state. (Only the stream is dropped and recreated — no view is created or altered by the app.)
3. The task logs the recovery event (stream name, staleness detected timestamp, data gap window) to the app's event table log. The `_metrics.pipeline_health` table records the incident with `recovery_type = 'stream_auto_recreate'` and the data gap window.
4. On the next task trigger, the new stream picks up new Event Table data and the pipeline resumes exporting to Splunk normally.

**Climax:** The pipeline self-heals without manual intervention. The next time Ravi opens the Streamlit UI, the Observability health page shows a past incident note: "Stream auto-recreated on [date]. Data gap: [last consumed offset] → [stream recreation timestamp]." The detailed recovery log entry is queryable in the app's event table via Snowsight.

**Resolution:** The app treats stream staleness as an **automatic recovery event**, not a manual intervention scenario. A task suspended for longer than `MAX_DATA_EXTENSION_TIME_IN_DAYS` results in a data gap that is acknowledged in the pipeline health record, but the stream is restored automatically — no user action required. The design assumes it is unrealistic to have a task suspended for 14+ days in normal operations, making this a rare edge case handled transparently.

**Capabilities Revealed:** Transport-level retry (OTel SDK for gRPC), failure logging to pipeline_health, watermark/stream advancement on failure, status visualization in Observability health (destination card, KPIs, category summary), automatic stream staleness recovery (drop/recreate stream on selected source — no app-created views), data gap recording in pipeline_health, app event table logging for recovery events.

---

### Journey 4: Ops Engineer — Monitoring App Health (Pipeline Debugging)

**Persona:** Sam — DevOps engineer on Maya's team. Not the installer or primary user, but responsible for ensuring the app's pipelines run reliably as part of the team's operational infrastructure.

**Opening Scene:** Sam's morning dashboard review includes a check on the Splunk Observability Native App. He opens the Streamlit UI — the app loads with **Observability health** as the default home page.

**Rising Action:**
1. **Quick health check (Observability health — helicopter view):** Sam scans the page in 3 seconds:
   - **Destination health card:** OTLP endpoint shows green status, last export 2 min ago.
   - **Four aggregated KPI cards:** Sources OK (12/14), Rows exported 24h (45,198), Failed batches 24h (0), Avg freshness (0.3h). All green.
   - **Export throughput trend chart:** Steady line, no dips.
   - **Category health summary:** Distributed Tracing ● Green (3/5), Query Performance ● Green (6/9). All categories healthy.
   - **Recent errors feed:** Empty (no errors in 24h). Good.
2. **Investigating a dip:** Sam notices the "Rows exported 24h" KPI is lower than usual. He clicks the **Query Performance & Execution** row in the category summary → drills down to **Telemetry sources** page filtered to that category. The `st.data_editor` shows per-source detail: TASK_HISTORY exported only 12 rows. He checks the Freshness chart (flat near zero) and Recent runs (+10/10). Not an export problem — simply low task activity. Normal.
3. **Investigating an export failure:** One morning, Sam sees a non-zero "Failed Batches (24h)" KPI and the destination card shows OTLP status as amber. The **Recent errors feed** shows: "OTLP export failed · 14:23 · gRPC UNAVAILABLE". He knows *what* failed, but needs *why*.
4. **Diagnosing the root cause via Snowsight:** The app writes structured operational logs to the consumer's account-level event table using Snowflake's Native App [event definition](https://docs.snowflake.com/en/developer-guide/native-apps/event-definition) framework (`log_level`, `trace_level` configured in `manifest.yml`). Sam clicks "View all in Snowsight" from the errors feed (or opens a Snowsight worksheet) and queries the app's log entries, filtering by severity = ERROR. He finds: `"OTLP export failed: TLS handshake error — certificate verify failed for endpoint https://collector.corp.example.com:4317. Check that the OTLP endpoint uses a CA-signed certificate trusted by Snowflake's EAI network rule, or configure a custom PEM certificate in Splunk settings."` Root cause found in seconds.

*(Post-MVP: A dedicated Streamlit Logging tab will provide an in-app experience — verbosity selector, scrollable log display, keyword search — so Sam won't need to leave the Streamlit UI for log analysis. Post-MVP: A volume estimator will help Sam project monthly throughput and plan capacity.)*

**Concrete errors the app operational logs surface:**
- OTLP failures: gRPC UNAVAILABLE, DEADLINE_EXCEEDED, TLS handshake error, connection reset, rate limiting, authentication failures
- Processing failures: Snowpark DataFrame transformation errors, schema mismatch on selected view/source, unexpected NULL columns (projection policy), entity discrimination filter yielding zero rows
- Stream/task issues: stream auto-recreated (staleness recovery), task auto-suspended after consecutive failures (`SUSPEND_TASK_AFTER_NUM_FAILURES`), task resumed after manual intervention

**Climax:** Sam resolves the certificate issue by navigating to **Splunk settings** → **Export settings** tab and pasting the correct PEM certificate. **Test connection** succeeds. The next task run exports successfully. He documents the root cause in the team's runbook — no escalation to Maya required.

**Resolution:** The combination of the **Observability health** helicopter view (what failed — destination card, KPIs, category summary, errors feed) and the app's structured event table logs queryable via Snowsight (why it failed) gives Sam a complete debugging workflow. **Observability health** is his 3-second daily health check; **Telemetry sources** drill-down shows per-source detail; Snowsight log queries are his go-to when something goes red.

**Capabilities Revealed:** Observability health helicopter view (destination health card, 4 KPI cards, throughput chart, category summary with drill-down, recent errors feed), Telemetry sources `st.data_editor` with per-source health columns, `_metrics.pipeline_health` table queryability, app operational logging via Snowflake Native App event definitions (`manifest.yml` log_level/trace_level), structured log queries via Snowsight (severity filtering, keyword search). *(Post-MVP: Streamlit Logging tab, volume estimator.)*

---

### Journey 5: Seamless App Upgrade

**Persona:** Maya — the app admin. Splunk publishes version V1_1 with the Cost Pack and bug fixes.

**Opening Scene:** Maya receives a notification (or discovers during her next Streamlit UI visit) that a new version of the Splunk Observability app is available. Her Snowflake account's maintenance policy allows auto-upgrades during the configured maintenance window (weekdays 2:00-4:00 AM).

**Rising Action:**
1. At 2:15 AM, Snowflake auto-upgrades the app from V1_0 to V1_1. The setup script (`setup.sql`) re-executes. The app logs an INFO message: `"Upgrade started: V1_0 → V1_1"`.
2. **Stateless objects rebuilt:** `CREATE OR ALTER VERSIONED SCHEMA app_public` cleanly replaces all stored procedures, UDFs, and the Streamlit UI with the new version. Snowflake's version pinning ensures any in-flight task executions complete against the old procedure code — no mid-execution code swap. Logged: `"Versioned schema app_public rebuilt"`.
3. **Stateful objects preserved:** `_internal.config`, `_internal.export_watermarks`, `_metrics.pipeline_health` tables survive the upgrade — `CREATE TABLE IF NOT EXISTS` is idempotent. `ALTER TABLE ADD COLUMN IF NOT EXISTS` adds any new columns required by V1_1 (e.g., new config keys for the Cost Pack) without touching existing data. Logged: `"Stateful tables preserved. New columns added: [list]"` (or `"No schema changes"` if none).
4. **Tasks recreated:** The app does not create or rebuild governed views — consumers select their own views or default sources. `CREATE OR REPLACE TASK` rebuilds each independent scheduled task with any new tasks (Cost Pack sources). Each task is resumed after creation — other sources are only briefly interrupted during their own replacement. Logged: `"Tasks recreated and resumed: [list]"`.
5. **Application roles preserved:** Roles are never dropped, only augmented. Existing grants survive. New procedures receive grants from the setup script. Logged: `"Roles preserved. New grants applied: [list]"`.

**Climax:** At 2:17 AM, the upgrade completes. The app logs: `"Upgrade complete: V1_1. Duration: 2m 3s. All pipelines resumed."` The pipelines resume with zero data loss — watermarks pick up exactly where they left off. The Streamlit UI now shows a new "Cost Pack" toggle in Monitoring Pack Selection.

**Resolution:** Maya arrives at work, opens the Streamlit UI, and sees the Cost Pack is now available. She enables it, and METERING_HISTORY/WAREHOUSE_METERING_HISTORY data starts flowing to Splunk. Her existing Performance Pack and Distributed Tracing Pack pipelines were uninterrupted. Zero consumer action was required for the upgrade itself — only pack enablement for new features.

**Capabilities Revealed:** Auto-upgrade via release directive, idempotent setup.sql design, versioned schema for stateless objects, version pinning for in-flight tasks, stateful table preservation (IF NOT EXISTS + ADD COLUMN IF NOT EXISTS), per-task recreation, watermark continuity across upgrades, consumer maintenance policy respect, structured upgrade logging (per-step INFO messages to app event table). (No app-created governed views — upgrade does not create or alter consumer views.)

---

### Journey 6: Maya Configures Data Governance (Privacy & Compliance)

**Persona:** Maya — Snowflake Administrator. Her security team has classified sensitive data across the account using Snowflake's automated classification and applied masking policies to PII columns. Maya needs to ensure the Splunk export pipeline respects these governance measures.

**Opening Scene:** Maya's CISO asks: "That new Splunk app — does it export raw QUERY_TEXT? Our queries contain customer email addresses and SSNs in WHERE clauses." Maya opens the Streamlit UI to investigate.

**Rising Action:**
1. **Data governance page:** Maya navigates to the **Data governance** page via the sidebar. The page shows a read-only table of **enabled sources only** with five columns: **Status**, **View name**, **Source type**, **Governance message** (per row), and **Sensitive columns** (per-row list of columns that may contain sensitive info and should be masked/redacted via policy). When she has selected **default views or event tables**, the per-row governance message **informs** her clearly: "Default source — masking and row access policies cannot be applied; use a custom view for governance." When she has selected **her own custom views**, the message notes: "Custom view — Snowflake masking/row policies apply."
2. **QUERY_TEXT privacy:** For QUERY_HISTORY, Maya sees the **Sensitive columns** column lists `QUERY_TEXT`, `USER_NAME`, `CLIENT_IP` — columns that may contain PII. She can select her organization's **custom view** (e.g. one with a masking policy on QUERY_TEXT) as the source on **Telemetry sources** — then no raw SQL leaves Snowflake. If she selects the default ACCOUNT_USAGE.QUERY_HISTORY view, the Data governance page per-row message informs her that policies cannot be applied to that view and she should create a custom view to enforce governance. She shows the page to her CISO; trust is established when she uses a custom view with masking.
3. **Custom masking for QUERY_TEXT:** Maya's security team creates a custom view over QUERY_HISTORY, applies a regex-based masking policy to strip emails and SSNs from QUERY_TEXT, and Maya **selects that view** as the source on **Telemetry sources**. The app reads from it; Snowflake enforces the mask. No app-owned view or toggle.
4. **Event Table governance:** For the Distributed Tracing Pack, if Maya (or Ravi) selects a **custom view** over the Event Table with masking on RECORD, RECORD_ATTRIBUTES, and/or VALUE, the app streams from that view and policies are honored. If they select the event table directly, the Data governance page per-row message informs that masking cannot be applied on event tables and they should use a custom view for value-level redaction. The **Sensitive columns** column shows which Event Table columns may contain sensitive data. Maya flags this for the security team.
5. **Row-level filtering:** Maya's compliance team creates a custom view over QUERY_HISTORY with a row access policy that excludes internal service accounts, and Maya selects that view as the source on **Telemetry sources**. The app exports only rows that pass the filter. No app changes required.

**Climax:** Maya walks the CISO through the governance model: the app reads or streams from the **source the user selected** (custom view or default). When she uses her team's custom views with masking and row access policies, Snowflake enforces them at the platform layer. When default views or event tables are selected, the **Data governance** page clearly states per row that policies can't be applied and that custom views are required for governance. The **Sensitive columns** column helps identify which columns need masking policies. The CISO approves the app for production use.

**Resolution:** Maya's team controls what data leaves Snowflake by creating custom views with Snowflake-native policies and selecting those views as the app's source. The app never creates or maintains views — it only informs when default sources are selected that governance policies cannot be applied there. "Leverage, Don't Replicate" — the app relies on the consumer's views and policies created using Snowflake built-in features.

**Capabilities Revealed:** Data governance page (read-only table of enabled sources with Status, View name, Source type, per-row Governance message, per-row Sensitive columns), user-selected source per category (custom view or default) on Telemetry sources, consumer-created views with masking/RAP as source, "Leverage, Don't Replicate" design philosophy.

---

### Journey 7: Event Table Schema Change — User-Owned View Responsibility

**Persona:** Maya — Snowflake Administrator. Her development team adds a new column to their custom Event Table. The app uses a **user-selected source** (either the event table directly or the user's custom view over it).

**Opening Scene:** Maya's dev team notifies her: "We just added a `deployment_environment` column to our Event Table to track prod vs staging spans. The Splunk export should pick this up automatically, right?"

**Rising Action:**
1. The dev team runs `ALTER TABLE custom_events ADD COLUMN deployment_environment VARCHAR`. The Event Table schema changes.
2. **If the app's telemetry source is the event table directly:** The app streams from the table; the new column is included in the stream. The pipeline may need to handle the new column in transformation (schema evolution). No view to update — the app does not create views.
3. **If the app's telemetry source is the user's custom view:** The user (or their DBA) is responsible for updating that view to include the new column (e.g. `CREATE OR REPLACE VIEW my_events_export AS SELECT *, deployment_environment FROM custom_events`). Note: `CREATE OR REPLACE VIEW` on the user's view will break any stream on that view — the user must drop/recreate the stream or the app's staleness recovery will do so, with a data gap. The app does not create, alter, or refresh the user's view; it only reads/streams from whatever source the user selected.

**Climax:** Maya confirms with the DBA: when they use a custom view over the Event Table, they own schema changes to that view. The Data governance page and docs state that the app does not create or maintain views — if the underlying table schema changes, the user updates their view and re-applies policies as needed.

**Resolution:** Clear ownership: the app never auto-creates or auto-refreshes governed views. Schema evolution of the Event Table is handled by streaming from the table directly (new columns flow through) or by the user updating their view and accepting stream drop/recreate if they use a view. No app-managed governed view registry or automatic view recreation.

**Capabilities Revealed:** User-owned view responsibility for schema changes, no app-created views (no auto-refresh), stream on selected source (table or user's view), documentation/panel guidance that user must update their view if underlying table schema changes.

---

### Journey Requirements Summary

| Journey | Key Capabilities Required |
|---|---|
| **Maya Happy Path** | Marketplace install, Permission SDK privilege binding, Getting Started tile hub with drill-down, Telemetry sources `st.data_editor` with category headers and per-source health, per-source selection (custom view or default), per-source schedule interval display/modification, OTLP destination config (Splunk settings → Export settings tab), independent scheduled task provisioning (read from user-selected source), Data governance page (per-row governance message when default selected), Observability health helicopter view |
| **Ravi Happy Path** | Telemetry sources `st.data_editor` with category headers, per-source selection (user's governed view or event table), entity discrimination (SQL/Snowpark scope), stream polling interval display/modification, OTel DB Client convention enrichment (`db.*` + `snowflake.*`), OTLP destination config (Splunk settings → Export settings tab), stream creation on selected source (view or table), triggered task provisioning, OTLP/gRPC span export |
| **Edge Case: OTLP Down** | OTLP/gRPC transport-level retry (OTel SDK), pipeline reads from selected source, failure logging to pipeline_health, watermark advancement on failure, stream offset advancement on failure, status visualization in Observability health (destination card, KPIs, category summary) |
| **Edge Case: Stale Stream** | Automatic stream staleness detection and auto-recovery (drop/recreate stream on selected source — no app-created views), data gap recording in pipeline_health, recovery event logging to app event table |
| **Observability Health Monitoring** | Observability health helicopter view (destination health card, 4 KPIs, throughput chart, category summary with drill-down, recent errors feed), Telemetry sources per-source detail, pipeline_health table, app operational logging via Native App event definitions, structured log queries via Snowsight. *(Post-MVP: Streamlit Logging tab, volume estimator.)* |
| **Seamless Upgrade** | Idempotent setup.sql, versioned schema, version pinning, stateful table preservation, per-task recreation, watermark continuity, application role preservation, structured upgrade logging (per-step INFO messages to app event table). No app-created governed views. |
| **Data Governance** | Data governance page (read-only table of enabled sources with Status, View name, Source type, per-row Governance message, per-row Sensitive columns), user-selected source per category (custom view or default), consumer-created views with masking/RAP as source, "Leverage, Don't Replicate". *(Post-MVP: Full Governance tab with classification awareness, policy detection, consumer policy enumeration.)* |
| **Event Table Schema Change** | User-owned view responsibility; app does not create or refresh views; when user's view is source, user updates view if underlying table schema changes; stream on selected source (table or user's view) |

## Technical & Platform Requirements

**Product Type:** SaaS / B2B Platform — Snowflake Native App (Marketplace-distributed)
**Domain:** Cloud Infrastructure / Observability
**Complexity:** High
**Reference Research:** Data Governance & Privacy Features, Event Table Streams & Governance Research, OTel Semantic Conventions Research, Event Table Entity Discrimination Strategy

This product is a **Snowflake Native App** distributed via the Snowflake Marketplace. Unlike traditional SaaS where the vendor hosts infrastructure, the app runs entirely inside the consumer's Snowflake account using serverless compute. The vendor (Splunk) publishes app versions; Snowflake manages distribution, upgrades, and security scanning. Licensing and billing are handled outside the app — through existing Splunk product licenses.

### 1. Platform Identity

#### 1.1 Tenant & Isolation Model

| Aspect | Detail |
|---|---|
| **Tenancy model** | Single-tenant per install. Each consumer Snowflake account gets its own isolated app instance. |
| **Data isolation** | Complete — each install has its own stateful tables (`_internal.config`, `_internal.export_watermarks`, `_metrics.pipeline_health`), streams (on user-selected source), tasks, secrets, and EAI objects. No cross-account data mixing. No app-created governed views. |
| **Compute isolation** | Each install uses the consumer's own serverless compute (serverless tasks). No shared compute between installs. |
| **Namespace isolation** | App objects live in the app's owned schemas (`app_public` versioned schema, `_internal`, `_metrics`). Consumer selects their own views or default views/tables; streams and tasks reference the selected source. No app-created governed views. |
| **Upgrade isolation** | Each consumer's maintenance policy controls when upgrades apply. Different consumers can run different versions during rollout windows. |

#### 1.2 Permission & RBAC Model

**Design principle: KISS — single application role.**

| Role | Name | Scope | Rationale |
|---|---|---|---|
| **App Admin** | `app_admin` | Full access to all app capabilities: configuration, pack management, destination setup, data governance, observability health, logging tab | A Snowflake administrator who installs a Marketplace app is inherently a privileged user. Adding viewer/operator roles adds complexity without clear value for MVP — the admin can share observability dashboards via Splunk instead. |

**Privilege binding (via Python Permission SDK):**

| Privilege | Purpose | Binding Method |
|---|---|---|
| `IMPORTED PRIVILEGES ON SNOWFLAKE DB` | Access to ACCOUNT_USAGE views | Permission SDK → Snowsight grant prompt |
| `EXECUTE TASK` | Run serverless tasks | Permission SDK → Snowsight grant prompt |
| `EXECUTE MANAGED TASK` | Serverless task compute | Permission SDK → Snowsight grant prompt |
| `CREATE EXTERNAL ACCESS INTEGRATION` | Outbound networking to Splunk endpoints | Permission SDK → Snowsight grant prompt |

**Stored procedure execution model:**

| Context | Execution Model | Implication |
|---|---|---|
| Pipeline collectors (ACCOUNT_USAGE, Event Table) | `EXECUTE AS OWNER` (owner's rights) | Procedures run with app's privileges, not caller's. Governed view policies are enforced by Snowflake at the platform layer — the owner role sees masked data (safe default). |
| Streamlit UI callbacks | Caller's rights | UI procedures run as the interactive user (admin). |

#### 1.3 Subscription & Pricing Model

| Aspect | Detail |
|---|---|
| **MVP pricing** | Free — no charge for the Snowflake Native App itself |
| **Licensing** | Managed entirely through existing Splunk product licenses (Splunk Enterprise, Splunk Observability Cloud). |
| **Snowflake compute costs** | Borne by the consumer — serverless task executions, warehouse compute for stored procedures. Documented in consumer-facing sizing guide. |
| **Billable events** | Not used. No Snowflake billable events framework integration planne so far. |
| **Future monetization** | Not applicable — value accrues to Splunk's core products (increased data ingest, expanded platform usage). The app is a GTM/ecosystem play. |

### 2. Compliance & Regulatory

#### 2.1 Snowflake Marketplace Compliance

The app follows the Snowflake Marketplace application lifecycle — no independent compliance attestation (SOC 2, ISO 27001, etc.) is required for the app itself. Compliance requirements:

| Requirement | How We Comply |
|---|---|
| **Security scan (APPROVED)** | Manual scan on test build before submission, per Marketplace publishing workflow guidelines |
| **DISTRIBUTION = EXTERNAL** | App package configured for Marketplace distribution; triggers automated security scan on every version |
| **No hardcoded credentials** | All secrets stored in Snowflake Secrets (SECRET object); OTLP access tokens and PEM certificates never in code |
| **Enforced standards compliance** | manifest.yml v2, setup.sql idempotent, no blocked functions in shared content |
| **Content Security Policy (CSP)** | Streamlit UI complies with Snowflake's CSP restrictions — no external JS/CSS/fonts/images, no `unsafe_allow_html`, no third-party components |

#### 2.2 Data Privacy & Governance — "Leverage, Don't Replicate"

The app does NOT implement its own data classification or privacy enforcement engine. This is a **foundational design decision.** Snowflake's governance policies are enforced at the **platform layer** — below our application code. The app leverages Snowflake Horizon Catalog capabilities:

| Snowflake Capability | How the App Leverages It |
|---|---|
| **Automated sensitive data classification** (ML-based, semantic/privacy category tags) | *(Post-MVP)* App queries classification metadata (`TAG_REFERENCES`, `DATA_CLASSIFICATION_LATEST`) to populate the enhanced Data governance page. MVP: Data governance page shows enabled sources with per-row governance messages and sensitive columns. When default views/event tables are selected, informs that policies can't be applied. |
| **Dynamic data masking** (column-level, role-based, tag-based) | When the user selects a **custom view** as the source, Snowflake enforces masking on that view automatically. The app does not create views or apply default masking. User creates views with masking and selects them as the source. |
| **Row access policies** (row-level filtering) | When the user selects a custom view with RAP attached, Snowflake enforces it. User creates views with RAP and selects them as the source. Example: exclude internal service account queries. |
| **Projection policies** (column blocking) | Consumer attaches projection policies to block specific columns from export. |
| **Tag-based policy assignment** (scalable governance) | Policies assigned to tags propagate to all tagged columns automatically. The app reads `POLICY_REFERENCES` to show which policies are active. |

**Key constraint — blocked context functions:** In the Native App Framework, `IS_ROLE_IN_SESSION()`, `CURRENT_ROLE()`, and `CURRENT_USER()` return NULL in shared content and owner's-rights stored procedures. Masking policies that use role-based conditions always evaluate the NULL branch. This is actually the **desired behavior** for export use cases — the app always sees the masked data (safe default). Consumer guidance in the Streamlit UI explains this.

#### 2.3 QUERY_TEXT Privacy (ACCOUNT_USAGE)

`QUERY_TEXT` in QUERY_HISTORY is the highest-risk field — may contain literal PII values embedded in SQL (email addresses, SSNs, passwords in WHERE clauses). The app does not create views or apply default masking. **User selects the source:** a **custom view** (with masking on QUERY_TEXT) or the **default** ACCOUNT_USAGE.QUERY_HISTORY view. When the default is selected, the Data governance page informs the user that masking/row policies cannot be applied and they must create a custom view to enforce governance.

#### 2.4 Event Table Span/Log Attribute Privacy

Span and log attributes (RECORD, RECORD_ATTRIBUTES, VALUE columns in Event Tables) are OBJECT/VARIANT type and may contain PII logged by consumer applications. Masking policies are **blocked on event tables directly**. If the user selects a **custom view** over the Event Table and attaches masking to RECORD, RECORD_ATTRIBUTES, and/or VALUE, Snowflake enforces it when the app streams from that view. If the user selects the event table directly, the Data governance page informs them that masking cannot be applied and they should use a custom view for value-level redaction.

### 3. Technical Constraints

#### 3.1 User-Selected Sources

The app **does not create or maintain governed views**. For each data source, the **user selects** the telemetry source: either their **own custom view** (with masking/row access policies) or the **default** view/event table. This is the uniform data access pattern:

| Pipeline | Data Path | User Responsibility |
|---|---|---|
| **Event Table (event-driven)** | User selects: **custom view** or **event table** → Stream (APPEND_ONLY on selected source) → Triggered Task → OTLP | If user selects a custom view, they attach RAP + masking (masking is blocked on event tables directly). If user selects event table, Data governance page informs that masking can't be applied. |
| **ACCOUNT_USAGE (poll-based)** | User selects: **custom view** or **default ACCOUNT_USAGE view** → Independent Scheduled Task (watermark) → Splunk | If user selects custom view, they attach RAP + masking + projection. If user selects default view, panel informs that policies can't be applied; user must create custom view for governance. |

**When user uses their own view + stream (Event Table):** `CREATE OR REPLACE VIEW` on the user's view **breaks all streams** on it — offset is lost. Consumer documentation explains that policy changes should use `ALTER VIEW`; if they recreate the view, the app's stream staleness recovery (drop/recreate stream) will run with a data gap. The app never creates or alters the user's view.

**Event Table schema changes:** If the user's view is the source and the underlying Event Table schema changes, the **user** is responsible for updating their view. The app does not implement governed view auto-refresh or a governed view registry.

#### 3.2 Entity Filtering — Event Table Telemetry Scope

Snowflake's Event Table is a shared, multi-service telemetry sink. The app uses a **positive include-list filter** on `RESOURCE_ATTRIBUTES:"snow.executable.type"` to target MVP-scope telemetry:

| Value | Service Category | MVP Scope |
|---|---|---|
| `procedure` | SQL/Snowpark — Stored Procedure | **IN SCOPE** |
| `function` | SQL/Snowpark — UDF/UDTF | **IN SCOPE** |
| `query` | SQL/Snowpark — SQL within a procedure | **IN SCOPE** |
| `sql` | SQL/Snowpark — Snowflake Scripting block | **IN SCOPE** |
| `spcs` | Snowpark Container Services | Out of scope (post-MVP) |
| `streamlit` | Streamlit in Snowflake | Out of scope (post-MVP) |
| N/A (uses `RESOURCE_ATTRIBUTES:"application"`) | Openflow pipelines | Out of scope (post-MVP — **Openflow Pack**) |
| N/A (separate `AI_OBSERVABILITY_EVENTS` table) | Cortex Services (AI Functions, Agents, Search) | Out of scope (post-MVP — **Cortex AI Pack**) |

Filter is applied as a **Snowpark pushdown** (first DataFrame operation after stream read) — only matching rows are scanned. The positive include-list is resilient to new entity types Snowflake may add in the future.

**Post-MVP expansion:**
- **SPCS / Streamlit**: Additional service categories added by registering new filter predicates (`snow.executable.type = 'spcs'` / `'streamlit'`) and convention-specific enrichers in the service category registry.
- **Openflow Pack**: Event Table telemetry filtered by `RESOURCE_ATTRIBUTES:"application" = 'openflow'`. Covers Openflow pipeline execution traces, task orchestration, and data flow monitoring.
- **Cortex AI Pack**: Separate data source (`AI_OBSERVABILITY_EVENTS` table accessed via `GET_AI_OBSERVABILITY_EVENTS()` function). Cortex AI Functions, Cortex Agents, Cortex Search telemetry enriched with OTel `gen_ai.*` conventions. User-selected source (custom view or default) + poll-based pipeline (not Event Table stream).

#### 3.3 Independent Serverless Scheduled Tasks

Each enabled ACCOUNT_USAGE source gets its own standalone serverless scheduled task.

| Advantage | Detail |
|---|---|
| **Source-specific schedules** | Each task's `SCHEDULE` aligned to its source's Snowflake latency (e.g., 30 min for QUERY_HISTORY, 90 min for ACCESS_HISTORY post-MVP) |
| **True error isolation** | A failing source only blocks its own next run; all other sources continue on schedule |
| **Operational simplicity** | Add source = `CREATE TASK` + `ALTER TASK RESUME`. Remove source = `DROP TASK`. No root suspend/resume. |
| **Cost savings** | No root task or finalizer invocations. No wasted invocations for sources with different cadences. |
| **Inline health recording** | Each collector writes its own metrics to `_metrics.pipeline_health` at end of run — no finalizer aggregation needed. |
| **Native retry per task** | `TASK_AUTO_RETRY_ATTEMPTS` retries only the failed source. `SUSPEND_TASK_AFTER_NUM_FAILURES` (default 10) auto-suspends only the failing source. |

#### 3.4 Dual Python Runtime

| Component | Python Version | Reason |
|---|---|---|
| **Streamlit UI** | Python 3.11 | Maximum supported version for Streamlit in Snowflake |
| **Backend stored procedures** | Python 3.13 | Latest supported version for stored procedures; better performance, newer language features |

#### 3.5 App Operational Logging (Native App Event Definitions)

The app uses Snowflake's [Native App event definition framework](https://docs.snowflake.com/en/developer-guide/native-apps/event-definition) to write structured operational logs to the consumer's account-level event table. This provides full visibility into pipeline processing, export outcomes, and error diagnostics.

| Aspect | Detail |
|---|---|
| **manifest.yml configuration** | `log_level: INFO`, `trace_level: ALWAYS` (configurable per app version). Event definitions: `ERRORS_AND_WARNINGS` (MANDATORY), `DEBUG_LOGS` (OPTIONAL). |
| **Log sources** | Each pipeline task (ACCOUNT_USAGE collectors, Event Table collector), Streamlit UI operations, stream auto-recovery events, export transport errors |
| **Structured log fields** | Severity (ERROR/WARN/INFO/DEBUG), timestamp, source/task name, error code, HTTP status, endpoint URL, row counts, duration, recovery actions |
| **MVP debugging** | Consumer queries the account event table via Snowsight for pipeline debugging, error analysis, and programmatic alerting |
| **Post-MVP: Streamlit Logging tab** | *(Deferred)* Verbosity selector (`st.pills`: ERROR/WARN/INFO/DEBUG), scrollable log display with keyword search, filters by source/task name and time range |
| **Auto-recovery logging** | Stream staleness auto-recovery events include: stream name, staleness detection timestamp, data gap window, recovery outcome |

#### 3.6 Deployment & Operations

| Consideration | Decision | Rationale |
|---|---|---|
| **Deployment model** | Snowflake Marketplace (auto-install, auto-upgrade) | Zero consumer infrastructure. Snowflake manages distribution. |
| **Upgrade strategy** | Auto-upgrade via release directive + consumer maintenance policy | Consumer controls timing. Setup script is idempotent. Stateful objects preserved. |
| **State management** | Internal tables (`_internal.config`, `_internal.export_watermarks`) + streams on selected source | State survives upgrades. Watermarks ensure exactly-once semantics (happy path). No app-created governed views. |
| **Networking** | EAI + Network Rules per Splunk destination | Snowflake-native outbound networking. No VPN or PrivateLink required (MVP). |
| **Secret management** | Snowflake Secrets for all credentials | Never in code, never in config tables. Rotatable without app restart. |
| **Self-monitoring** | App event table logging (Native App event definitions) + `_metrics.pipeline_health` table | Observability health page in Streamlit UI. Log queries via Snowsight (MVP). *(Post-MVP: Streamlit Logging tab.)* |
| **Error handling** | Transport-level retry per destination + failure logging + pipeline advancement | MVP trade-off: data gap on sustained outage. Post-MVP: zero-copy failure tracking. |
| **Testing** | Cross-account install testing + manual security scan on test build | Marketplace compliance. E2E validation before submission. |

### 4. Integration Architecture

#### 4.1 Outbound Integrations (App → Splunk)

| Integration | Protocol | Purpose | Auth | MVP |
|---|---|---|---|---|
| **Remote OpenTelemetry Collector (OTLP)** | gRPC (TLS) | Export all telemetry (spans, metrics, logs, events) from both Event Tables and ACCOUNT_USAGE | Optional PEM certificate (Snowflake Secret) for private/self-signed collector certs | Yes |

**Note:** The app exports all telemetry via a **single OTLP/gRPC endpoint** pointing to a remote OpenTelemetry collector (e.g. Splunk distribution of the OTEL collector). The collector is responsible for routing: traces/metrics to Splunk Observability Cloud, logs/events to Splunk Enterprise/Cloud. The app does not configure HEC or Splunk-specific endpoints directly — that configuration lives in the collector.

#### 4.2 Inbound Data Sources (Snowflake → App)

| Integration | Access Method | Purpose | MVP |
|---|---|---|---|
| **ACCOUNT_USAGE views** (QUERY_HISTORY, TASK_HISTORY, COMPLETE_TASK_GRAPHS, LOCK_WAIT_HISTORY) | SQL via user-selected source (custom view or default; poll-based, watermark) | Performance Pack telemetry | Yes |
| **Event Table** (`SNOWFLAKE.TELEMETRY.EVENTS` or user-created) | Stream on user-selected source (custom view or event table; event-driven) | Distributed Tracing Pack telemetry (spans, metrics, logs) | Yes |
| **ACCOUNT_USAGE governance metadata** (TAG_REFERENCES, DATA_CLASSIFICATION_LATEST, POLICY_REFERENCES) | SQL read-only | *(Post-MVP)* Enhanced Data governance page — classification awareness, policy display. MVP Data governance page shows enabled sources with per-row governance messages and sensitive columns. | No (post-MVP) |
| **ACCOUNT_USAGE views** (METERING_HISTORY, WAREHOUSE_METERING_HISTORY, …) | SQL via user-selected source (poll-based) | Cost Pack (post-MVP) | No |
| **ACCOUNT_USAGE views** (LOGIN_HISTORY, ACCESS_HISTORY, SESSIONS, …) | SQL via user-selected source (poll-based) | Security Pack (post-MVP) | No |
| **ACCOUNT_USAGE views** (COPY_HISTORY, LOAD_HISTORY, PIPE_USAGE_HISTORY) | SQL via user-selected source (poll-based) | Data Pipeline Pack (post-MVP) | No |
| **Event Table** (Openflow telemetry with `RESOURCE_ATTRIBUTES:"application" = 'openflow'`) | Stream on user-selected source (event-driven) | Openflow Pack (post-MVP) — pipeline execution traces, task orchestration, data flow monitoring | No |
| **AI_OBSERVABILITY_EVENTS** (via `GET_AI_OBSERVABILITY_EVENTS()` function) | SQL/function call via user-selected source (poll-based) | Cortex AI Pack (post-MVP) — Cortex AI Functions, Cortex Agents, Cortex Search telemetry enriched with OTel `gen_ai.*` conventions | No |

#### 4.3 Snowflake Platform Services (App ↔ Snowflake)

| Service | Purpose | MVP |
|---|---|---|
| **Python Permission SDK** | Privilege binding via native Snowsight grant prompts | Yes |
| **External Access Integration (EAI) + Network Rules** | Outbound networking to OTLP endpoint | Yes |
| **Snowflake Secrets** | Secure storage for optional PEM certificates | Yes |
| **Serverless Tasks** (scheduled + triggered) | Pipeline execution — poll-based and event-driven | Yes |
| **Streams** (append-only on user-selected source: view or event table) | Change data capture for Event Table pipeline | Yes |
| **Versioned Schemas** | Stateless object management for upgrades | Yes |
| **Native App Event Definitions** | App operational logging to consumer's event table | Yes |
| **Snowflake Horizon Catalog** (classification, masking, RAP, projection, tags) | Governance policy enforcement when user selects a custom view as source | Yes (leveraged, not called directly) |
| **Marketplace Publishing Pipeline** | App distribution, security scanning, version management | Yes |

#### 4.4 OTel Semantic Conventions (Event Table → OTLP/gRPC → Splunk Observability Cloud)

The app operates as a **convention-transparent telemetry relay** with additive enrichment. No original attributes are stripped or renamed.

**MVP Convention Stack:**

| Layer | Convention | Purpose | Stability |
|---|---|---|---|
| **0 — Relay** | Convention-transparent | Preserve ALL original Event Table attributes from producers | Architecture |
| **1 — Database** | `db.*` (Database Client) | SQL/Snowpark operations — `db.system.name = "snowflake"`, `db.namespace`, `db.operation.name`, `db.stored_procedure.name`, `db.query.text`, `db.collection.name` | **Stable** |
| **4 — Resource** | `service.*`, `cloud.*` | Cross-cutting app/cloud identification | Stable |
| **5 — Custom** | `snowflake.*` | Snowflake-specific context — `snowflake.warehouse.name`, `snowflake.query.id`, `snowflake.session.role`, `snowflake.user`, `snowflake.executable.name` | Custom |

**Post-MVP Convention Extensions:**
- `gen_ai.*` — Generative AI conventions for Cortex AI Pack telemetry (separate `AI_OBSERVABILITY_EVENTS` table accessed via `GET_AI_OBSERVABILITY_EVENTS()` function). Covers Cortex AI Functions, Cortex Agents, and Cortex Search. Key attributes: `gen_ai.system`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.operation.name`.
- `k8s.*` / `container.*` — Container orchestration conventions for SPCS workloads (`snow.executable.type = 'spcs'`)
- Openflow-specific attributes — For Openflow Pack telemetry (entity discrimination: `RESOURCE_ATTRIBUTES:"application" = 'openflow'`). Pipeline execution traces, task orchestration metadata, data flow lineage.

**Splunk Observability Cloud alignment:** Splunk APM adopted OTel DB Client convention updates in August 2025 (`db.system.name`, `db.namespace`, `db.operation.name`) — our enrichment maps directly to Splunk's DB monitoring views, Tag Spotlight, and trace waterfall.

#### 4.5 OTLP Telemetry Structure

All telemetry is exported via OTLP/gRPC to a remote OpenTelemetry collector. The collector is responsible for routing and transformation to downstream systems (Splunk Observability Cloud, Splunk Enterprise/Cloud).

**Telemetry Types Exported:**

| Source | Signal Type | OTLP Resource/Span Attributes |
|---|---|---|
| **Event Table (Distributed Tracing)** | Spans, Metrics, Logs | OTel DB Client conventions (`db.*`), custom Snowflake conventions (`snowflake.*`), original Event Table attributes preserved |
| **ACCOUNT_USAGE (Performance Pack)** | Logs/Events | Source-specific attributes (query_id, warehouse_name, user_name, etc.), resource attributes for routing |

**Collector Routing (Example):**
- Spans/Metrics → Splunk Observability Cloud (OTLP/gRPC or Splunk HEC)
- Logs/Events → Splunk Enterprise/Cloud (Splunk HEC)

The app does not configure downstream routing — that is the collector's responsibility. This separation of concerns simplifies app configuration while leveraging the collector's flexibility.

### 5. Risk Mitigations

#### 5.1 Stream Breakage — Event Table Governed View

| Risk | Severity | Mitigation |
|---|---|---|
| `CREATE OR REPLACE VIEW` on governed Event Table view breaks all streams (offset lost, unrecoverable) | **CRITICAL** | App upgrade process uses `ALTER VIEW` only. Consumer documentation prominently warns against view recreation. If stream becomes stale, app auto-recovers (drop/recreate stream, data gap recorded). |
| First stream creation locks underlying Event Table (one-time change tracking setup) | **MEDIUM** | Schedule during low-activity period. One-time cost per Event Table. Documented in consumer setup guide. |
| Secure views do NOT auto-extend retention (faster staleness) | **MEDIUM** | App uses non-secure views. Consumer guidance advises against `CREATE SECURE VIEW`. |

#### 5.2 Stream Staleness

| Risk | Severity | Mitigation |
|---|---|---|
| Default Event Table staleness window (~14 days) | **MEDIUM** | Set `MAX_DATA_EXTENSION_TIME_IN_DAYS = 90` on user-created Event Tables during setup. For default Event Table (`SNOWFLAKE.TELEMETRY.EVENTS`), consume stream frequently (triggered task with 30s minimum interval). |
| Task suspension longer than staleness window | **LOW** | **Automatic recovery:** The app detects the stale stream at task execution, drops and recreates the stream on the **selected source** (user's view or event table), records the data gap in `_metrics.pipeline_health`, and logs the recovery event to the app's event table. No manual user action required. The design assumes task suspension > 14 days is an exceptional edge case. |

#### 5.3 Marketplace Delisting

| Risk | Severity | Mitigation |
|---|---|---|
| Security scan failure on submitted version | **HIGH** | Manual security scan on test build before submission (allowed by Marketplace workflow). Fix all findings before formal submission. |
| Non-compliance with Marketplace enforced standards | **MEDIUM** | Automated checks in CI: manifest.yml v2 validation, blocked function detection, `DISTRIBUTION=EXTERNAL` scan. |

#### 5.4 Data Loss (MVP Trade-off)

| Risk | Severity | Mitigation |
|---|---|---|
| Sustained OTLP endpoint outage causes permanent data gaps (MVP — no failure tracking) | **MEDIUM** | Transport-level retries handle transient blips (seconds). Sustained outages (minutes to hours) create gaps. Observability health page is early warning. Post-MVP: zero-copy failure tracking with reference-based retry will close this gap. |
| OTLP endpoint down | **MEDIUM** | All telemetry export fails. Observability health shows destination error. Retry with exponential backoff. Documented MVP trade-off. |

#### 5.5 Governance Policy Interaction

| Risk | Severity | Mitigation |
|---|---|---|
| Consumer's role-based masking policies always hit NULL branch (blocked context functions in Native App) | **LOW** | This is the **desired behavior** for export — app always sees masked data when reading from consumer's view. Consumer guidance: use unconditional masking (regex scrubbing) on their custom view, not role-based conditions. |
| Consumer applies `CREATE OR REPLACE VIEW` to their view (breaking streams) | **MEDIUM** | Documentation warns that view recreation breaks streams. App auto-recovers stale/broken streams (drop/recreate stream on selected source, data gap recorded). App does not create or alter consumer views. |
| Projection policy blocks a column the pipeline needs | **LOW** | Pipeline gracefully handles NULL columns. Logs warning to `_metrics.pipeline_health`. |
| Governed view auto-refresh drops consumer-applied policies | **MEDIUM** | Streamlit UI displays schema change notification when recreation occurs. Consumer acknowledges and re-applies policies. Hourly detection interval limits notification frequency. Stream auto-recovery handles broken streams automatically. |
| DML operations trigger false positive schema changes | **LOW** | MD5 hash fingerprinting detects only DDL changes (column add/remove/rename). DML operations (data inserts) do not change column structure and do not trigger recreation. |

#### 5.6 Innovation-Specific Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Future Snowflake Event Table schema changes break enrichment logic | **LOW** | Defensive parsing — unknown attributes pass through; only known attributes are enriched |
| Serverless compute limits (max concurrent tasks, memory) at high telemetry volume | **MEDIUM** | Document sizing guidance; post-MVP: compute pool option for high-volume accounts |
| Auto-recovery creates silent data gaps user doesn't notice | **LOW** | Data gap window logged to `_metrics.pipeline_health` and app event table; Observability health page shows past incident notes |

## Innovation & Novel Patterns

### Detected Innovation Areas

**1. Governed View as Universal Data Contract**
No existing Snowflake Native App or connector makes **user-selected sources** (custom governed views or default views/tables) the explicit contract for observability export with clear governance guidance. The standard pattern is direct reads from ACCOUNT_USAGE or Event Tables. Our design addresses the gap: you can't apply masking, row access, or projection policies to system ACCOUNT_USAGE views or Event Tables directly — so we let the user **select** their own custom view (with policies) as the source, or the default, and we **inform** them when the default is selected that policies can't be applied and they must create custom views for governance. The app does not create or maintain views; the user owns governance. This is a simplified, user-responsible approach that works for both pipeline types (event-driven and poll-based).

**2. Convention-Transparent Telemetry Relay with Additive Enrichment**
Most telemetry pipelines strip, rename, or reshape attributes during processing. This app preserves ALL original Event Table attributes from producers and enriches additively with OTel semantic convention layers (`db.*`, `snowflake.*`, `service.*`, `cloud.*`). The "preserve everything, enrich only" pattern is an architectural differentiator — it respects the producer's telemetry while making it Splunk-native. No original context is lost.

**3. Zero-Infrastructure Observability Bridge**
Shipping an observability pipeline as a Marketplace-installable Snowflake Native App (zero external infrastructure, zero agents, zero collectors) is fundamentally different from the OTel Collector pattern used by every other Snowflake observability solution. The pipeline runs inside the customer's Snowflake account using serverless compute — no VMs, no containers, no network infrastructure to manage. Install-to-first-data in minutes, not hours.

**4. "Leverage, Don't Replicate" Governance Philosophy**
Instead of building its own data classification, masking, or privacy engine, the app deliberately delegates to Snowflake's existing Horizon Catalog governance stack. This philosophy-level design decision reduces attack surface, eliminates maintenance burden for governance logic, and prevents governance policy drift. The app inherits every current and future governance feature Snowflake ships — without code changes.

**5. Entity Filtering — Scoped Telemetry from Shared Multi-Service Sink**
Snowflake's Event Table is a shared telemetry sink for all Snowflake services. Filtering it with a positive include-list on `RESOURCE_ATTRIBUTES:"snow.executable.type"` to scope MVP telemetry to SQL/Snowpark compute — while remaining inherently resilient to new entity types Snowflake adds in the future. The positive include-list pattern means new service categories are safely excluded until explicitly registered. Post-MVP expansion includes SPCS (`snow.executable.type = 'spcs'`), Streamlit (`snow.executable.type = 'streamlit'`), and Openflow (`RESOURCE_ATTRIBUTES:"application" = 'openflow'`) via the service category registry. The Cortex AI Pack uses a separate dedicated data source (`AI_OBSERVABILITY_EVENTS` table) rather than Event Tables.

**6. Self-Healing Pipelines**
Stale stream detection with automatic drop/recreate recovery — including data gap logging to both `_metrics.pipeline_health` and the app's event table — makes the pipeline self-healing without manual intervention. Combined with `SUSPEND_TASK_AFTER_NUM_FAILURES` for export errors and `TASK_AUTO_RETRY_ATTEMPTS`, the app handles failure modes transparently. No manual "fix it" buttons.

**7. Single OTLP Export with Collector-Based Routing**
All telemetry (spans, metrics, logs, events) is exported via a single OTLP/gRPC endpoint to a remote OpenTelemetry collector. The collector handles routing to Splunk Observability Cloud (traces/metrics) and Splunk Enterprise/Cloud (logs). This architecture simplifies app configuration (one endpoint) while leveraging the collector's flexibility for downstream routing, filtering, and transformation.

### Market Context & Competitive Landscape

| Existing Approach | Limitation | Our Innovation |
|---|---|---|
| **OTel Collector with Snowflake receiver** | External infrastructure required (VMs/containers), network configuration, separate credential management, no Snowflake-native governance | Zero-infrastructure Native App, user-selected sources with governance guidance, Marketplace install, single OTLP endpoint to existing collector |
| **Snowflake DB Connect for Splunk** | JDBC-based polling, no Event Table support, no OTel conventions, no governance intermediary | Dual-pipeline (event-driven + poll-based), OTel DB Client conventions, user-selected sources (custom view or default) |
| **Custom ETL (Airflow, dbt + scripts)** | High maintenance, no standardization, no self-healing | Marketplace-managed upgrades, auto-recovery, zero operator toil |
| **Snowflake's built-in event sharing** | Provider-to-consumer only, no existing Splunk integration, no governance view layer | Consumer selects custom views (with policies) as source; direct OTLP export; Data governance page informs when default selected |

### Validation Approach

| Innovation | Validation Method |
|---|---|
| **User-selected source with governance** | E2E test: user selects custom view (with masking + RAP) as source → verify exported data is masked and row-filtered in Splunk |
| **Convention-transparent relay** | Compare exported span attributes with raw Event Table attributes — assert zero attribute loss, additive enrichment only |
| **Zero-infrastructure pipeline** | Measure install-to-first-data latency (target < 15 min). Compare with OTel Collector setup time (typically hours) |
| **"Leverage, Don't Replicate"** | User selects custom views with 5+ different policy combinations as source → verify all honored in export without app code changes |
| **Entity discrimination** | Export with filter → verify zero out-of-scope service category rows in Splunk. Add new service type to Event Table → verify it is excluded |
| **Self-healing pipeline** | Suspend triggered task for > 14 days → verify stream auto-recreates, pipeline resumes, data gap is logged |
| **Single OTLP export** | Kill OTLP endpoint → verify failure logged → verify Observability health shows destination card red, Failed batches KPI increments |

*Innovation-specific risks are consolidated in Technical & Platform Requirements § 5.6.*

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach:** Platform MVP — prove that a Snowflake Native App can serve as a zero-infrastructure observability bridge with comparable telemetry export performance to external OTel Collector pipelines.

**Core Learning Goal:** Can a single Marketplace-installable app, running entirely inside the consumer's Snowflake account, deliver telemetry to Splunk with latency parity or better than external collectors — with zero consumer infrastructure?

**Key Scoping Decisions:**

| Decision | Rationale |
|---|---|
| **Keep streams for Event Table pipeline** | Polling an unclustered Event Table with millions of rows is fundamentally different from polling pre-filtered ACCOUNT_USAGE views. Streams give efficient delta processing, < 60s latency, cost efficiency (triggered task), and exactly-once row guarantees. The staleness and breakage risks are already mitigated (auto-recovery, ALTER VIEW only). |
| **Simplify Data governance page** | MVP: Data governance page — read-only table showing enabled sources with Status, View name, Source type, per-row Governance message, per-row Sensitive columns. When default views or event tables are selected, clearly informs that masking/row policies can't be applied and user must create their own custom views for governance. No policy detection, no classification awareness in MVP. Full governance UI deferred to post-MVP. |
| **Defer Logging tab (Streamlit UI)** | MVP: app logs to the consumer's event table via Native App event definitions (structured logs with severity, source, error details). Debugging via direct event table queries in Snowsight. Streamlit Logging tab (verbosity selector, search, scrollable display) deferred to post-MVP. |
| **Defer volume estimator** | Not essential for core export workflow. Deferred to post-MVP. |
| **Keep CIM normalization** | Low effort — just correct JSON field naming per CIM conventions. Essential for Splunk-side value (ES dashboards, data model acceleration). |

### MVP Feature Set (Phase 1)

**Core Journeys Supported:** All 7 journeys are supported, with scoping simplifications noted.

| Journey | MVP Coverage | Simplifications |
|---|---|---|
| **1. Maya Install/Configure** | Full | Getting Started tile hub, Telemetry sources `st.data_editor`, Splunk settings Export settings tab |
| **2. Ravi Traces** | Full | None |
| **3. Edge Cases (OTLP Down, Stale Stream)** | Full | Auto-recovery included |
| **4. Pipeline Debugging (Sam)** | Full | Observability health helicopter view (4 KPIs, destination card, category summary, errors feed). Telemetry sources per-source detail. Logging tab deferred — Sam queries event table via Snowsight for error details. |
| **5. Seamless Upgrade** | Full | None |
| **6. Data Governance (Maya)** | Full | Data governance page — read-only table of enabled sources with Status, View name, Source type, per-row Governance message, per-row Sensitive columns. No app-created views. |
| **7. Event Table Schema Change** | Full | None |

**Must-Have Capabilities:**
1. Marketplace install + Permission SDK privilege binding
2. User-Selected Sources Architecture (custom views or default views/event tables)
3. Distributed Tracing Pack (Event Table → Stream → Triggered Task → OTLP/gRPC)
4. Performance Pack (ACCOUNT_USAGE → Scheduled Tasks → OTLP/gRPC)
5. Streamlit Configuration UI via `st.navigation`: Getting Started tile hub, Observability health helicopter view, Telemetry sources `st.data_editor` with category headers, Splunk settings (Export settings tab with OTLP endpoint + optional PEM certificate), Data governance page (read-only, 5 columns)
6. Observability health helicopter view (destination health card, 4 KPI cards, throughput chart, category summary with drill-down, recent errors feed)
7. Telemetry sources per-source health (Status, Freshness chart, Recent runs, Errors, editable Interval/Batch size)
8. App Operational Logging (event definitions → consumer event table, queryable via Snowsight)
9. Transport retries (OTLP) with failure logging to `_metrics.pipeline_health`
10. Auto-recovery for stale Event Table streams
11. Marketplace-ready packaging (manifest.yml v2, setup.sql, security scan)

### Post-MVP Features (Phase 2 — Growth)

| Feature | Priority | Dependency |
|---|---|---|
| **Streamlit Logging tab** (verbosity selector, search, scrollable display) | High | App logging already in place — UI only |
| **Enhanced Data governance page** (classification awareness, policy detection, consumer policy enumeration) | High | Governance metadata queries already available |
| **Volume estimator** | Medium | Pipeline health data already collected |
| **Cost Pack** (METERING_HISTORY, WAREHOUSE_METERING_HISTORY, …) | Medium | New sources (user selects custom view or default) + scheduled tasks |
| **Security Pack** (LOGIN_HISTORY, ACCESS_HISTORY, SESSIONS, GRANTS_TO_USERS, GRANTS_TO_ROLES, NETWORK_POLICIES) | Medium | New sources (user-selected) + CIM mappings |
| **Data Pipeline Pack** (COPY_HISTORY, LOAD_HISTORY, PIPE_USAGE_HISTORY) | Medium | New sources (user-selected) + CIM mappings |
| **Zero-copy failure tracking** (reference-based retry for data gaps) | Medium | New retry task + failure reference table |
| **Advanced Observability health dashboard** (Throughput, Errors, Volume tabs) | Low | Extends existing Observability health |
| **In-app rate limiting** (token-bucket, Retry-After parsing) | Low | Optimization |

### Post-MVP Features (Phase 3 — Expansion)

| Feature | Dependency |
|---|---|
| Additional Event Table service categories (SPCS: `snow.executable.type = 'spcs'`, Streamlit: `snow.executable.type = 'streamlit'`) | Convention extensions + service category registry |
| **Openflow Pack** (Event Table telemetry with `RESOURCE_ATTRIBUTES:"application" = 'openflow'`) | Entity discrimination filter + service category registry |
| **Cortex AI Pack** (Cortex Services telemetry via `AI_OBSERVABILITY_EVENTS` table accessed through `GET_AI_OBSERVABILITY_EVENTS()` function, enriched with OTel `gen_ai.*` conventions for Cortex AI Functions, Cortex Agents, Cortex Search) | Separate data source + convention enricher + governed view for AI_OBSERVABILITY_EVENTS |
| Bi-directional integration (Splunk alerts → Snowflake actions) | New inbound integration |
| Multi-tenant scale (100+ concurrent installs) | Performance testing + optimization |

### Risk-Based Scoping

**Technical Risk (highest):** Event Table pipeline end-to-end (user-selected source → stream → triggered task → OTLP export). Touches the most Snowflake primitives and has the tightest latency requirement (< 60s). **Mitigation:** Build and test this pipeline first. If it works, everything else is lower risk.

**Solo-engineer Risk:** Single point of failure for a 1-month timeline. **Mitigation:** Prioritize backend pipelines first (weeks 1-2), Streamlit UI second (week 3), Marketplace packaging and testing last (week 4). If time runs short, the Data governance page and Observability health can ship with minimal UI polish.

**Market Risk:** Low — the Snowflake + Splunk joint customer base is well-established. The risk is execution speed, not market fit. **Mitigation:** MVP go/no-go gates (latency parity, zero P1/P2, security scan) are binary — ship or don't ship. No soft launches.

**Streams vs Polling Decision (documented):** Streams were evaluated against watermark-based polling for Event Tables. Streams kept for MVP due to: efficient delta processing on unclustered high-volume tables, < 60s latency achievable, cost-efficient triggered tasks, exactly-once row guarantees. Polling would degrade with Event Table volume and require additional dedup logic.

## Functional Requirements

UX/UI behavior, layout, and interaction details (pages, components, flows) are specified in the [UX Design Specification](_bmad-output/planning-artifacts/ux-design-specification.md). The requirements below state *what* the system must do; the UX spec defines *how* it is presented and operated.

### Installation & Setup

- **FR1:** Admin can install the app from the Snowflake Marketplace with zero external infrastructure provisioning
- **FR2:** Admin can grant required privileges through native Snowflake permission prompts during first launch
- **FR3:** Admin can complete initial setup through a **Getting Started tile hub** with drill-down to task-specific pages (Splunk settings, Telemetry sources, Data governance, Activate) and progress tracking in the sidebar

### Source Configuration

- **FR4:** Admin can discover available ACCOUNT_USAGE views and Event Tables in their Snowflake environment
- **FR5:** Admin can enable or disable Monitoring Packs (Distributed Tracing Pack, Performance Pack) independently
- **FR6:** Admin can view the default schedule interval for each selected data source
- **FR7:** Admin can modify the schedule interval for any individual data source
- **FR8:** Admin can configure a single **OTLP/gRPC endpoint** (Splunk settings → Export settings tab) pointing to a remote OpenTelemetry collector
- **FR9:** Admin can optionally configure a **PEM certificate** for OTLP endpoints using private/self-signed certificates; admin can validate the certificate before saving; when no certificate is provided, the system uses Snowflake's default trust store (Mozilla/certifi CA bundle) which includes major public CAs (DigiCert, Let's Encrypt, GlobalSign, etc.)
- **FR10:** Admin can **Test connection** to validate OTLP endpoint reachability before saving configuration
- **FR11:** Admin can view and modify the Event Table triggered task interval on Telemetry sources

### Data Governance & Privacy

- **FR12:** Admin can select, per data source on **Telemetry sources**, the telemetry source: either a custom view (with masking/row access policies) or the default ACCOUNT_USAGE view / event table
- **FR13:** The **Data governance** page shows a read-only table of **enabled sources only** with columns for status, view name, source type, governance message, and sensitive columns; admin can acknowledge governance implications during onboarding
- **FR14:** When default views or event tables are selected, the per-row Governance message informs the admin that masking and row access policies cannot be applied to those sources and that they must create their own custom views to enforce governance
- **FR15:** When the admin selects a custom view as the source, the system reads or streams from that view and Snowflake enforces any masking/row access/projection policies attached to it
- **FR16:** Consumer DBA can create custom views with Snowflake-native masking policies and the admin selects those views as the source on Telemetry sources; the export pipeline honors the policies automatically
- **FR17:** Consumer DBA can attach row access policies to their custom views; when the admin selects such a view as the source, the export pipeline exports only rows that pass the filter
- **FR18:** Consumer DBA can attach projection policies to their custom view columns; when selected as source, the pipeline gracefully handles resulting NULL columns

### Telemetry Collection

- **FR19:** The system collects Event Table telemetry incrementally using change data capture (new rows only)
- **FR20:** The system filters Event Table telemetry to SQL/Snowpark compute scope (stored procedures, UDFs/UDTFs, SQL queries) via entity filtering
- **FR21:** The system collects each enabled ACCOUNT_USAGE source independently on its own schedule using watermark-based incremental reads
- **FR22:** Admin can view and edit per-source configuration (enable/disable polling, interval, batch size) on **Telemetry sources** page

### Telemetry Export

- **FR23:** The system exports all telemetry (Event Table spans, metrics, logs; ACCOUNT_USAGE events) via **single OTLP/gRPC endpoint** to a remote OpenTelemetry collector
- **FR24:** The system enriches Event Table spans with OTel DB Client semantic conventions (`db.*`) and custom Snowflake conventions (`snowflake.*`)
- **FR25:** The system preserves all original Event Table attributes from producers and enriches additively (no attribute stripping or renaming)
- **FR26:** The system retries failed export batches at the transport level using OTel SDK built-in gRPC retry with exponential backoff

### Pipeline Operations & Health

- **FR27:** Ops engineer can view **Observability health** helicopter view showing: destination health card (OTLP status), 4 aggregated KPI cards (Sources OK, Rows exported 24h, Failed batches 24h, Avg freshness), export throughput trend chart, category health summary table with drill-down, and recent errors feed
- **FR28:** Ops engineer can view per-source pipeline status on **Telemetry sources** page including status, freshness, recent run history, errors, and editable configuration
- **FR29:** The system logs structured operational events (errors, warnings, info, debug) to the consumer's account-level event table using Native App event definitions
- **FR30:** Ops engineer can query the app's operational logs via Snowsight to diagnose pipeline errors (OTLP failures, processing errors, stream recovery events)
- **FR31:** The system automatically detects and recovers stale Event Table streams by dropping and recreating the stream on the user-selected source
- **FR32:** The system records data gaps resulting from stream recovery or sustained destination outages in the pipeline health metrics
- **FR33:** The system auto-suspends a failing source after consecutive failures without affecting other sources with appropriate status change for this source
- **FR34:** The system records per-run metrics (rows collected, rows exported, failures, latency) for each pipeline source

### App Lifecycle & Marketplace

- **FR35:** The system supports auto-upgrades via Snowflake release directives, respecting the consumer's maintenance policy
- **FR36:** The system preserves all stateful data (configuration, watermarks, pipeline health metrics) across version upgrades
- **FR37:** The system rebuilds stateless objects (procedures, UDFs, Streamlit UI) cleanly during upgrades without interrupting in-flight task executions
- **FR38:** The system logs structured upgrade progress messages (per-step start, completion, errors) to the app's event table
- **FR39:** The system passes Snowflake Marketplace security scanning requirements for all submitted versions

## Non-Functional Requirements

### Performance

- **NFR1:** Event Table telemetry is visible in Splunk within 60 seconds of being written to the Event Table (stream trigger + processing + export)
- **NFR2:** ACCOUNT_USAGE data is visible in Splunk within one polling cycle of Snowflake's inherent view latency (e.g., QUERY_HISTORY with ~45 min Snowflake latency appears in Splunk within ~75 min)
- **NFR3:** Streamlit UI pages load and render within 5 seconds under normal conditions (Snowflake serverless compute startup included)
- **NFR4:** Observability health KPI cards reflect data no older than the most recent completed task run
- **NFR5:** Export batch processing (data transformation + network send) completes within 30 seconds per batch for OTLP destination

### Security

- **NFR6:** All credentials (optional PEM certificates) are stored exclusively in Snowflake Secrets — never in code, config tables, or logs
- **NFR7:** All outbound connections (OTLP) use TLS encryption 
- **NFR8:** All outbound connections are strictly governed by Snowflake External Access Integrations and Network Rules — no outbound network traffic occurs outside of what is explicitly defined and approved by the consumer
- **NFR9:** The app never bypasses Snowflake-native governance policies — all data reads flow through user-selected sources where platform-layer policies are enforced
- **NFR10:** All app versions pass Snowflake Marketplace automated security scanning with zero Critical or High findings
- **NFR11:** No credential material appears in app operational logs, pipeline health metrics, or Streamlit UI displays
- **NFR12:** All dependencies are free of Critical/High CVEs at the time of Marketplace submission

### Reliability

- **NFR13:** Pipeline uptime >= 99.9% per source (< 8.7 hours unplanned downtime per year), measured by consecutive successful task runs
- **NFR14:** Export success rate >= 99.5% of batches exported successfully (transport retries included), measured via `_metrics.pipeline_health`
- **NFR15:** A single failing source does not impact the availability or scheduling of any other source's pipeline
- **NFR16:** Stale Event Table streams are recovered without manual intervention — pipeline resumes autonomously
- **NFR17:** App upgrades complete with zero data loss — watermarks and stream offsets resume from their pre-upgrade positions
- **NFR18:** Transport retries handle transient destination failures (network blips, brief rate limiting) without data loss for outages lasting up to 60 seconds

### Scalability

- **NFR19:** The Event Table pipeline processes up to 1 million rows per triggered task execution without timeout or memory failure
- **NFR20:** The system supports up to 10 concurrent independent ACCOUNT_USAGE scheduled tasks without resource contention
- **NFR21:** Pipeline throughput scales linearly with serverless task compute allocation — no architectural bottlenecks that prevent vertical scaling

### Integration Quality

- **NFR22:** All OTLP-exported spans conform to OTel DB Client semantic conventions (`db.*` namespace) and pass Splunk APM's span validation (visible in Tag Spotlight, trace waterfall)
- **NFR23:** All OTLP-exported telemetry includes appropriate resource and span attributes for downstream routing by the OpenTelemetry collector
- **NFR24:** The app correctly handles OTLP error responses (gRPC status codes) with appropriate retry or failure-logging behavior per response type
