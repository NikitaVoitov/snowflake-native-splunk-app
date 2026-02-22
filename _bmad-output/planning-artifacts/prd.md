---
stepsCompleted: [step-01-init, step-02-discovery, step-03-success, step-04-journeys, step-05-domain, step-06-innovation, step-07-project-type, step-08-scoping, step-09-functional, step-10-nonfunctional, step-11-polish, step-12-complete]
status: complete
inputDocuments:
  - _bmad-output/planning-artifacts/product-brief-snowflake-native-splunk-app-2026-02-15.md
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

**Author:** Nik
**Date:** 2026-02-15

## Executive Summary

**Splunk Observability for Snowflake** is a Snowflake Native App distributed via the Snowflake Marketplace that exports Snowflake telemetry — distributed traces, metrics, logs, and operational events — to Splunk Observability Cloud and Splunk Enterprise with zero external infrastructure. Install from Marketplace, configure in Streamlit, observe in Splunk — in under 15 minutes.

**Product Differentiator:** The only observability bridge that runs entirely inside the consumer's Snowflake account using serverless compute, governed views as a universal data contract for privacy/compliance, and additive OTel semantic convention enrichment — replacing external OTel Collectors, DB Connect pipelines, and custom ETL with a single Marketplace install.

**Target Users:** Snowflake Administrators (Maya) who manage Snowflake accounts and need telemetry in Splunk, SREs (Ravi) who need distributed traces through the Snowflake boundary, and DevOps engineers (Sam) who monitor pipeline health.

**MVP Scope:** Distributed Tracing Pack (Event Table → OTLP/gRPC + HEC) and Performance Pack (ACCOUNT_USAGE → HEC, CIM-normalized), with governed view architecture, Streamlit configuration UI, pipeline health monitoring, and app operational logging. Target ship: Mid-March 2026, solo engineer.

## Success Criteria

### User Success

| Criteria | Target | How We Know |
|---|---|---|
| **Time to first telemetry** | < 15 minutes from Marketplace install to first data visible in Splunk | Measured end-to-end: "Get" click → privilege binding → pack selection → first span/event in Splunk |
| **Zero manual pipelines** | Replaces all manual Snowflake-to-Splunk data pipelines (DB Connect, custom ETL, OTel Collector scraping) | Customer self-reported before/after comparison |
| **MTTR reduction** | 50% reduction in Mean Time to Resolution for Snowflake-related issues | Enabled by Splunk's cross-system correlation — Snowflake telemetry correlated with application, service, and infrastructure data |
| **Context-switching eliminated** | SREs investigate Snowflake issues entirely within Splunk APM/Enterprise without opening Snowsight | Qualitative: end-to-end traces through Snowflake boundary visible in single Splunk view |
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
| **Pack adoption breadth** | Average 1.5+ Monitoring Packs per active install | 6 months post-launch |
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
| **No critical/high CVEs** | All dependencies CVE-free at Critical/High severity | Dependency audit (protobuf >= 6.33.5 verified) |

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
1. **Distributed Tracing Pack** — Event Table telemetry scoped to **SQL/Snowpark compute** (stored procedures, UDFs/UDTFs, SQL queries) via entity discrimination filter (`snow.executable.type IN ('procedure','function','query','sql')`). Spans/metrics → OTLP/gRPC to Splunk Observability Cloud (OTel DB Client `db.*` semantic conventions + custom `snowflake.*` namespace); logs → HEC to Splunk Enterprise/Cloud.
2. **Performance Pack** — QUERY_HISTORY, TASK_HISTORY, COMPLETE_TASK_GRAPHS, LOCK_WAIT_HISTORY → HEC to Splunk Enterprise/Cloud. Events CIM-normalized per Splunk Common Information Model (Databases data model, `snowflake:query_history` / `snowflake:task_history` sourcetypes).
3. **Governed View Architecture** — Every data source (Event Tables AND all ACCOUNT_USAGE views) flows through a custom governed view created by the app. Governed views are the **data contract** between the consumer's Snowflake account and the export pipeline. Consumers attach Snowflake-native governance policies (dynamic data masking, row access, projection) to any governed view. Default masking on high-risk sources (e.g., QUERY_TEXT in `governed_query_history` defaults to REDACT mode).
4. **Streamlit Configuration UI** — Privilege binding (Permission SDK), observability target selection (Event Tables + ACCOUNT_USAGE) with per-source schedule interval display and inline modification, pack toggles, destination setup (HEC + OTLP), QUERY_TEXT privacy toggle (REDACT/FULL/CUSTOM), simplified Governance Awareness panel (informational — highlights importance of Snowflake-native governance, lists governed views and default masking state; no policy detection or classification awareness), Pipeline Health Overview tab.
5. **Pipeline Health Dashboard** — Overview Tab with 3 KPI cards, per-source status. *(Volume estimator deferred to post-MVP.)*
6. **App Operational Logging** — The app writes structured operational logs (errors, warnings, info, debug) to the consumer's account-level event table using Snowflake's Native App [event definition](https://docs.snowflake.com/en/developer-guide/native-apps/event-definition) framework (`log_level` and `trace_level` configured in `manifest.yml`). Consumers query the event table directly via Snowsight for pipeline debugging and error analysis. *(Streamlit Logging tab — verbosity selector, scrollable display, keyword search — deferred to post-MVP.)*
7. **Dual-Pipeline Architecture** — Event-driven (Governed View → Stream → Serverless Triggered Task) for Event Tables; poll-based (Governed View → Independent Serverless Scheduled Tasks + Watermarks) for ACCOUNT_USAGE. Each ACCOUNT_USAGE source gets its own independent task with a source-specific schedule. Stale Event Table streams are auto-recovered by the app (drop/recreate stream — data gap recorded in pipeline_health).
8. **Marketplace-Ready Packaging** — manifest.yml v2, marketplace.yml, setup.sql, README.md, environment.yml, security scan APPROVED (manual scan on test build per Snowflake Marketplace [automated security scan workflow](https://docs.snowflake.com/en/developer-guide/native-apps/security-run-scan)).

**MVP Go/No-Go Gates:** 
- GO gates:Functional (E2E workflows), Performance (latency parity with OTel Collector), Quality (zero P1/P2), Marketplace Compliance (security scan, enforced standards).
- No-GO gates: slow telemetry data processing/export performance.

### Growth & Vision (Post-MVP)

*Detailed phased roadmap with priorities and dependencies is documented in [Project Scoping & Phased Development](#project-scoping--phased-development).*

**Phase 2 — Growth:** Streamlit Logging tab, full Governance Compliance tab, volume estimator, Cost Pack, Security Pack, zero-copy failure tracking, advanced Pipeline Health Dashboard, in-app rate limiting.

**Phase 3 — Expansion:** Additional Event Table service categories (SPCS, Streamlit), Openflow Pack (Event Table telemetry with `RESOURCE_ATTRIBUTES:"application" = 'openflow'`), Cortex AI Pack (dedicated `AI_OBSERVABILITY_EVENTS` table with `gen_ai.*` conventions), bi-directional integration (Splunk alerts → Snowflake actions), multi-tenant scale (100+ concurrent installs).

## User Journeys

### Journey 1: Maya's First Day — Install, Configure, Observe (Happy Path)

**Persona:** Maya — Senior Snowflake Administrator, 50+ warehouses, hundreds of users across analytics, data engineering, ML, and application development teams.

**Opening Scene:** It's Monday morning. Maya's inbox has three tickets from the analytics team about slow queries over the weekend, and her manager just forwarded an email from finance asking why last month's Snowflake bill was 40% higher than projected. She sighs — her morning ritual of manually querying ACCOUNT_USAGE views in Snowsight begins. She opens QUERY_HISTORY, filters for long-running queries, exports to CSV, and pastes the results into a ticket. Then she opens WAREHOUSE_METERING_HISTORY and repeats the process for cost data. None of this reaches the Splunk dashboards her ops team actually monitors.

**Rising Action:**
1. Maya navigates to the Snowflake Marketplace and searches for "Splunk observability." She finds **Splunk Observability for Snowflake** and clicks "Get." The app installs in her account in seconds — no region restrictions, no external infrastructure.
2. On first launch, the Streamlit UI greets her with a guided setup wizard. The Python Permission SDK presents native Snowsight privilege prompts — she clicks "Grant" for IMPORTED PRIVILEGES ON SNOWFLAKE DB, EXECUTE TASK, EXECUTE MANAGED TASK, and CREATE EXTERNAL ACCESS INTEGRATION. No manual SQL.
3. The app discovers available ACCOUNT_USAGE views and Event Tables in her environment. She selects her sources and enables the **Performance Pack** toggle (QUERY_HISTORY, TASK_HISTORY, COMPLETE_TASK_GRAPHS, LOCK_WAIT_HISTORY). Each selected source displays its **default schedule interval** (e.g., QUERY_HISTORY: 30 min, TASK_HISTORY: 30 min) — Maya can modify any interval inline before activation.
4. She enters her Splunk Enterprise HEC endpoint and token. The UI validates connectivity. She clicks "Activate."
5. Behind the scenes: the app provisions networking (EAI + Network Rule), creates **governed views** over each enabled ACCOUNT_USAGE source (`governed_query_history`, `governed_task_history`, etc.), applies a default masking policy on `QUERY_TEXT` (REDACT mode), and creates **independent serverless scheduled tasks** — one per source, each with a schedule aligned to its Snowflake latency. Maya sees the Pipeline Health Overview tab update — green status indicators appear for each source.
6. The **Governance Awareness** panel shows "QUERY_TEXT mode: REDACT (default masking active)" and lists all governed views with their default masking state. Maya sees that her existing Snowflake governance policies (masking, row access) will be honored automatically.

**Climax:** Seven minutes after clicking "Get," Maya opens Splunk Enterprise. QUERY_HISTORY data is already flowing. She creates an alert for queries exceeding 5 minutes and a dashboard for warehouse credit consumption trends. The data that was trapped in Snowsight is now in her team's primary operational platform.

**Resolution:** Maya's morning manual review is replaced by proactive Splunk alerts. The cost report that took her 45 minutes every Monday is now a live Splunk dashboard that updates automatically. When the next warehouse spike happens, she gets a Splunk alert at 10:15 AM — before anyone else notices — and right-sizes the warehouse in minutes.

**Capabilities Revealed:** Marketplace install, Streamlit privilege binding (Permission SDK), observability target discovery/selection, Monitoring Pack toggle UI, per-source schedule interval display and inline modification, HEC destination configuration, governed view creation with default masking, independent scheduled task provisioning, Governance Awareness panel, Pipeline Health Overview tab.

---

### Journey 2: Ravi Traces Through the Snowflake Boundary (Happy Path)

**Persona:** Ravi — SRE on a platform engineering team. Responsible for the reliability of business-critical applications that depend on Snowflake — ML pipelines, real-time analytics APIs, Snowpark stored procedures.

**Opening Scene:** 2:47 AM. PagerDuty fires. The ML scoring API is returning 504s. Ravi opens Splunk Observability Cloud and pulls up the trace for a failed request. He follows the trace from the API gateway → Kubernetes service → ... and then the trace just stops. The next hop is a Snowflake stored procedure that runs a critical ML scoring UDF, but its spans are in a Snowflake Event Table — invisible from Splunk. Ravi context-switches to Snowsight, manually queries the Event Table by timestamp, and tries to correlate. It takes him 35 minutes to find the root cause: the UDF hit a warehouse queuing bottleneck.

**Rising Action:**
1. After the postmortem, Ravi's team installs **Splunk Observability for Snowflake** from the Marketplace (Maya, their admin, handled the install and privilege binding).
2. Ravi enables the **Distributed Tracing Pack** and binds their Event Table (`SNOWFLAKE.TELEMETRY.EVENTS`). The UI displays an informational banner: "This release processes **SQL/Snowpark compute telemetry** (SQL queries, stored procedures, UDFs, UDTFs). Telemetry from other Snowflake services (SPCS, Streamlit, Cortex AI) is filtered out. Future releases will add support for additional telemetry categories." The Event Table source shows its **default stream polling interval** (e.g., 30 seconds) — Ravi can modify it inline before activation. He enters the Splunk Observability Cloud realm and access token (OTLP endpoint).
3. The app creates a **governed view** over the Event Table (enabling consumer-attached governance policies), then an **append-only stream** on the governed view, and provisions a **serverless triggered task**. The pipeline's entity discrimination filter targets `snow.executable.type IN ('procedure','function','query','sql')` — only SQL/Snowpark compute telemetry is collected and transformed. Within minutes, spans begin flowing to Splunk Observability Cloud via OTLP/gRPC with OTel DB Client semantic conventions (`db.system.name = "snowflake"`, `db.namespace`, `db.operation.name`, `db.stored_procedure.name`, `snowflake.warehouse.name`, `snowflake.query.id`).
4. Ravi opens Splunk APM. For the first time, he sees Snowflake stored procedure spans stitched into the same traces as the rest of his application — the Snowflake boundary is transparent. The spans carry `db.system.name = "snowflake"` and Splunk's DB monitoring views recognize them natively.

**Climax:** Two weeks later, 3:12 AM. PagerDuty fires again. Ravi opens Splunk APM, pulls up the trace, and this time the trace continues *through* Snowflake. He clicks on the slow span — it's a Snowflake UDF. The span attributes show `snowflake.warehouse.name: ML_SCORING_WH`, `snowflake.query.id`, `db.operation.name: CALL`, `db.stored_procedure.name: ML_SCORING_UDF`, and duration breakdown. He sees the UDF waited 8 seconds in warehouse queue. Root cause identified in under 3 minutes — no Snowsight context-switching, no manual Event Table queries.

**Resolution:** Ravi's MTTR for Snowflake-related incidents drops from 35+ minutes to under 5 minutes. The Snowflake black box is gone. His team adds Snowflake-side SLOs in Splunk APM — if any stored procedure exceeds its latency budget, they know immediately and can see exactly why.

**Capabilities Revealed:** Event Table binding (reference mechanism), governed view creation over Event Table, entity discrimination (SQL/Snowpark compute scope), stream polling interval display and inline modification, OTel DB Client convention enrichment (`db.*` + `snowflake.*`), Distributed Tracing Pack configuration, OTLP/gRPC destination setup, stream creation on governed view, triggered task provisioning, span/log export to Splunk, Event Table log export via HEC.

---

### Journey 3: Maya & Ravi — When Things Go Wrong (Edge Cases)

**Persona:** Maya and Ravi, now regular users of the app, face critical failure scenarios.

#### Scenario A1 — Splunk Enterprise HEC Down (Logs & Events)

**Opening Scene:** Maya's Splunk Enterprise instance undergoes scheduled maintenance. The HEC endpoint is unreachable for 2 hours. Both the Performance Pack (ACCOUNT_USAGE data via poll-based pipeline) and the Distributed Tracing Pack's log export (Event Table logs via event-driven pipeline) are affected.

**Rising Action:**
1. The `account_usage_source_collector` for QUERY_HISTORY reads from `governed_query_history` (where QUERY_TEXT is masked by default) and attempts to export to HEC. `httpx` + `tenacity` retry with exponential backoff on 5xx/connection errors — configurable retries over ~30 seconds. All retries exhaust.
2. Simultaneously, the `event_table_collector` reads from the governed Event Table view stream and attempts to export logs to HEC. Same `httpx` + `tenacity` retry pattern. All retries exhaust.
3. Both failures are logged in `_metrics.pipeline_health` with error details (HTTP 503 or connection refused, timestamps, row counts, source name).
4. **Critical MVP trade-off:** For the poll-based pipeline, the watermark advances — the ACCOUNT_USAGE batch is lost. For the event-driven pipeline, the stream offset advances (zero-row INSERT pattern) — the Event Table log batch is lost.
5. The Pipeline Health Overview tab updates: the "Failed Batches" KPI card increments for affected sources. Pipeline status shows warning indicators for QUERY_HISTORY, TASK_HISTORY, and Event Table logs.

**Recovery:** HEC comes back online. Next scheduled runs succeed. Data from the outage window is permanently missing in MVP. Post-MVP: zero-copy failure tracking will record references for failed batches and a dedicated retry task will re-export them.

#### Scenario A2 — Splunk Observability Cloud OTLP Down (Traces & Metrics)

**Opening Scene:** Splunk Observability Cloud's OTLP/gRPC ingest endpoint experiences a transient outage for 45 minutes. The Distributed Tracing Pack's span and metric exports are affected. HEC exports (logs, ACCOUNT_USAGE) are unaffected — they target Splunk Enterprise, which is healthy.

**Rising Action:**
1. The `event_table_collector` processes Event Table rows and separates signals by type: spans and metrics route to OTLP/gRPC, logs route to HEC.
2. The OTel SDK's built-in gRPC retry kicks in — exponential backoff (1s, 2s, 4s, 8s, 16s, 32s — ~6 retries over ~63s) for transient gRPC errors (UNAVAILABLE, DEADLINE_EXCEEDED). All retries exhaust.
3. The span/metric batch export fails. The failure is logged in `_metrics.pipeline_health`. The stream offset advances — spans and metrics from this batch are lost in MVP.
4. **Meanwhile, logs export succeeds** — HEC is healthy, so Event Table logs for the same batch are delivered to Splunk Enterprise without issue. This is a partial failure — some signals from the same Event Table batch reach Splunk, others don't.
5. The Pipeline Health Overview shows a split status: Event Table spans/metrics show failure, Event Table logs show success, ACCOUNT_USAGE sources show success.

**Recovery:** OTLP endpoint recovers. Next triggered task run exports spans and metrics successfully. Ravi sees a gap in his Splunk APM traces for the 45-minute window, but logs for that same period are present in Splunk Enterprise.

**Climax (both scenarios):** Maya documents the data gaps and the MVP trade-off in her runbook. She sets up Splunk alerts on the `_metrics.pipeline_health` table to detect export failures in real time — so the team knows immediately rather than discovering gaps during incident investigation.

**Resolution:** The team understands the MVP boundary: transport-level retries handle transient blips (seconds), but sustained outages (minutes to hours) create data gaps. The Pipeline Health dashboard is their early warning system. Post-MVP failure tracking will close this gap for both HEC and OTLP exports.

#### Scenario B — Event Table Stream Goes Stale

**Opening Scene:** Ravi's team temporarily suspends the app's triggered task during a major Snowflake migration. The suspension lasts longer than expected — 16 days. The append-only stream on the **governed Event Table view** exceeds `MAX_DATA_EXTENSION_TIME_IN_DAYS` (14 days) and goes stale.

**Rising Action:**
1. When the task is resumed, the triggered task detects the stale stream condition (`SYSTEM$STREAM_HAS_DATA()` returns an error).
2. **Automatic recovery:** The app's task logic catches the staleness error, drops the stale stream, and recreates a new append-only stream on the governed view. The new stream starts from the current table state. (The governed view itself is NOT recreated — only the stream is dropped and recreated.)
3. The task logs the recovery event (stream name, staleness detected timestamp, data gap window) to the app's event table log. The Pipeline Health `_metrics.pipeline_health` table records the incident with `recovery_type = 'stream_auto_recreate'` and the data gap window.
4. On the next task trigger, the new stream picks up new Event Table data and the pipeline resumes exporting to Splunk normally.

**Climax:** The pipeline self-heals without manual intervention. The next time Ravi opens the Streamlit UI, the Pipeline Health Overview shows a past incident note: "Stream auto-recreated on [date]. Data gap: [last consumed offset] → [stream recreation timestamp]." The detailed recovery log entry is queryable in the app's event table via Snowsight.

**Resolution:** The app treats stream staleness as an **automatic recovery event**, not a manual intervention scenario. A task suspended for longer than `MAX_DATA_EXTENSION_TIME_IN_DAYS` results in a data gap that is acknowledged in the pipeline health record, but the stream is restored automatically — no user action required. The design assumes it is unrealistic to have a task suspended for 14+ days in normal operations, making this a rare edge case handled transparently.

**Capabilities Revealed:** Transport-level retry (httpx/tenacity for HEC, OTel SDK for gRPC), independent failure per protocol, partial success handling (logs succeed while spans fail), failure logging to pipeline_health, watermark/stream advancement on failure, split status visualization in Pipeline Health, automatic stream staleness recovery (drop/recreate stream on governed view — never `CREATE OR REPLACE VIEW`), data gap recording in pipeline_health, app event table logging for recovery events.

---

### Journey 4: Ops Engineer — Monitoring App Health (Pipeline Debugging)

**Persona:** Sam — DevOps engineer on Maya's team. Not the installer or primary user, but responsible for ensuring the app's pipelines run reliably as part of the team's operational infrastructure.

**Opening Scene:** Sam's morning dashboard review includes a check on the Splunk Observability Native App. He opens the Streamlit UI and navigates to the Pipeline Health Overview tab.

**Rising Action:**
1. **Quick health check:** Sam scans the three KPI cards:
   - Total rows collected/exported/failed (last 24h): 45,230 collected, 45,198 exported, 32 failed — 99.93% success rate. Good.
   - Current failed batches: 0 (all transport retries succeeded or failures were logged and pipeline advanced).
   - Pipeline status per source: all green — QUERY_HISTORY, TASK_HISTORY, COMPLETE_TASK_GRAPHS, LOCK_WAIT_HISTORY, and Event Table stream all show "last successful run" within expected intervals.
2. **Investigating a dip:** Sam notices TASK_HISTORY exported only 12 rows in the last 24 hours — unusually low. He checks the `_metrics.pipeline_health` table directly (via a Snowsight worksheet) and sees the `rows_collected` for TASK_HISTORY is also 12. Not an export problem — simply low task activity. Normal.
3. **Investigating an export failure:** One morning, Sam sees a non-zero "Failed Batches" KPI and a red status indicator on the Event Table pipeline. The KPI tells him *what* failed, but not *why*.
4. **Diagnosing the root cause via Snowsight:** The app writes structured operational logs to the consumer's account-level event table using Snowflake's Native App [event definition](https://docs.snowflake.com/en/developer-guide/native-apps/event-definition) framework (`log_level`, `trace_level` configured in `manifest.yml`). Sam opens a Snowsight worksheet and queries the app's log entries, filtering by severity = ERROR. He finds: `"HEC export failed: SSL handshake error — certificate verify failed for endpoint https://hec.corp.example.com:8088. Check that the HEC endpoint uses a CA-signed certificate trusted by Snowflake's EAI network rule."` Root cause found in seconds. He broadens the filter to WARN and discovers: `"OTLP export: 3 consecutive retries exhausted (gRPC UNAVAILABLE). Batch dropped. 847 spans lost."` — an earlier transient OTLP issue. Filtering at INFO level gives him full operational context — task start/end timestamps, rows processed per source, export latencies.

*(Post-MVP: A dedicated Streamlit Logging tab will provide an in-app experience — verbosity selector, scrollable log display, keyword search — so Sam won't need to leave the Streamlit UI for log analysis. Post-MVP: A volume estimator will help Sam project monthly throughput and plan Splunk HEC capacity.)*

**Concrete errors the app operational logs surface:**
- HEC failures: HTTPS handshake mismatch, certificate errors, 401 (invalid token), 429 (rate limiting), 503 (service unavailable), connection refused
- OTLP failures: gRPC UNAVAILABLE, DEADLINE_EXCEEDED, connection reset, rate limiting, authentication failures
- Processing failures: Snowpark DataFrame transformation errors, schema mismatch on governed view, unexpected NULL columns (projection policy), entity discrimination filter yielding zero rows
- Stream/task issues: stream auto-recreated (staleness recovery), task auto-suspended after consecutive failures (`SUSPEND_TASK_AFTER_NUM_FAILURES`), task resumed after manual intervention

**Climax:** Sam resolves the HEC certificate issue by updating the EAI network rule's allowed list. The next task run succeeds. He documents the root cause in the team's runbook — no escalation to Maya required.

**Resolution:** The combination of the Pipeline Health Overview tab (what failed) and the app's structured event table logs queryable via Snowsight (why it failed) gives Sam a complete debugging workflow. The Pipeline Health tab is his 3-minute daily health check; Snowsight log queries are his go-to when something goes red.

**Capabilities Revealed:** Pipeline Health Overview tab (3 KPI cards), per-source status monitoring, `_metrics.pipeline_health` table queryability, app operational logging via Snowflake Native App event definitions (`manifest.yml` log_level/trace_level), structured log queries via Snowsight (severity filtering, keyword search). *(Post-MVP: Streamlit Logging tab, volume estimator.)*

---

### Journey 5: Seamless App Upgrade

**Persona:** Maya — the app admin. Splunk publishes version V1_1 with the Cost Pack and bug fixes.

**Opening Scene:** Maya receives a notification (or discovers during her next Streamlit UI visit) that a new version of the Splunk Observability app is available. Her Snowflake account's maintenance policy allows auto-upgrades during the configured maintenance window (weekdays 2:00-4:00 AM).

**Rising Action:**
1. At 2:15 AM, Snowflake auto-upgrades the app from V1_0 to V1_1. The setup script (`setup.sql`) re-executes. The app logs an INFO message: `"Upgrade started: V1_0 → V1_1"`.
2. **Stateless objects rebuilt:** `CREATE OR ALTER VERSIONED SCHEMA app_public` cleanly replaces all stored procedures, UDFs, and the Streamlit UI with the new version. Snowflake's version pinning ensures any in-flight task executions complete against the old procedure code — no mid-execution code swap. Logged: `"Versioned schema app_public rebuilt"`.
3. **Stateful objects preserved:** `_internal.config`, `_internal.export_watermarks`, `_metrics.pipeline_health` tables survive the upgrade — `CREATE TABLE IF NOT EXISTS` is idempotent. `ALTER TABLE ADD COLUMN IF NOT EXISTS` adds any new columns required by V1_1 (e.g., new config keys for the Cost Pack) without touching existing data. Logged: `"Stateful tables preserved. New columns added: [list]"` (or `"No schema changes"` if none).
4. **ACCOUNT_USAGE governed views rebuilt:** `CREATE OR REPLACE VIEW` safely rebuilds poll-based governed views (no stream breakage risk — ACCOUNT_USAGE uses watermark-based pipelines, not streams). New views for Cost Pack sources are created. **Event Table governed view is NOT recreated** — `ALTER VIEW` is used for any policy changes to protect the stream. Logged: `"Governed views rebuilt: [list]. Event Table view preserved (ALTER only)"`.
5. **Tasks recreated:** `CREATE OR REPLACE TASK` rebuilds each independent scheduled task with any new tasks (Cost Pack sources). Each task is resumed after creation — other sources are only briefly interrupted during their own replacement. Logged: `"Tasks recreated and resumed: [list]"`.
6. **Application roles preserved:** Roles are never dropped, only augmented. Existing grants survive. New procedures receive grants from the setup script. Logged: `"Roles preserved. New grants applied: [list]"`.

**Climax:** At 2:17 AM, the upgrade completes. The app logs: `"Upgrade complete: V1_1. Duration: 2m 3s. All pipelines resumed."` The pipelines resume with zero data loss — watermarks pick up exactly where they left off. The Streamlit UI now shows a new "Cost Pack" toggle in Monitoring Pack Selection.

**Resolution:** Maya arrives at work, opens the Streamlit UI, and sees the Cost Pack is now available. She enables it, and METERING_HISTORY/WAREHOUSE_METERING_HISTORY data starts flowing to Splunk. Her existing Performance Pack and Distributed Tracing Pack pipelines were uninterrupted. Zero consumer action was required for the upgrade itself — only pack enablement for new features.

**Capabilities Revealed:** Auto-upgrade via release directive, idempotent setup.sql design, versioned schema for stateless objects, version pinning for in-flight tasks, stateful table preservation (IF NOT EXISTS + ADD COLUMN IF NOT EXISTS), per-task recreation, ACCOUNT_USAGE governed view safe rebuild (no stream dependency), Event Table governed view preserved via ALTER VIEW only, watermark continuity across upgrades, consumer maintenance policy respect, structured upgrade logging (per-step INFO messages to app event table).

---

### Journey 6: Maya Configures Data Governance (Privacy & Compliance)

**Persona:** Maya — Snowflake Administrator. Her security team has classified sensitive data across the account using Snowflake's automated classification and applied masking policies to PII columns. Maya needs to ensure the Splunk export pipeline respects these governance measures.

**Opening Scene:** Maya's CISO asks: "That new Splunk app — does it export raw QUERY_TEXT? Our queries contain customer email addresses and SSNs in WHERE clauses." Maya opens the Streamlit UI to investigate.

**Rising Action:**
1. **Governance Awareness panel:** Maya navigates to the Governance Awareness section in the Streamlit UI. The panel provides informational guidance:
   - A description of the governed view architecture — explaining that all data flows through custom views where Snowflake-native governance policies are enforced at the platform layer.
   - A list of all governed views created by the app and their current default masking state (e.g., `governed_query_history` — QUERY_TEXT: REDACT).
   - A reminder: "All Snowflake governance policies (masking, row access, projection) you or your security team attach to these governed views are automatically honored by the export pipeline. Manage governance via your existing Snowflake tools before exporting telemetry."
2. **QUERY_TEXT privacy:** Under the governed views list, Maya sees `governed_query_history` with "QUERY_TEXT mode: REDACT (default masking active)." The app ships with QUERY_TEXT masked by default — no raw SQL leaves Snowflake unless Maya explicitly opts in. She shows this to her CISO. Trust established.
3. **Custom masking for QUERY_TEXT:** Later, Maya's security team wants a middle ground — strip emails and SSNs from QUERY_TEXT but keep the query structure for debugging in Splunk. The DBA creates a regex-based masking policy and applies it to the governed view using `ALTER VIEW governed_query_history ALTER COLUMN QUERY_TEXT SET MASKING POLICY consumer_schema.scrub_query_pii FORCE`. Maya updates the QUERY_TEXT toggle to "CUSTOM" mode.
4. **Event Table governance:** Maya considers the governed Event Table view (`governed_events_export`). The governance panel notes that consumers can attach masking policies to the governed view's RECORD, RECORD_ATTRIBUTES, and/or VALUE columns if their applications log sensitive data in span attributes. Maya flags this for the security team to review.
5. **Row-level filtering:** Maya's compliance team wants to exclude queries from internal service accounts from the Splunk export. The DBA creates a row access policy and attaches it to `governed_query_history` — the app's pipeline automatically exports only rows that pass the filter. No app changes required.

**Climax:** Maya walks the CISO through the governance architecture: governed views as the universal data contract, default QUERY_TEXT masking, consumer-controlled policy attachment points, and the "Leverage, Don't Replicate" philosophy. The CISO approves the app for production use.

**Resolution:** The governed view architecture means Maya's team controls exactly what data leaves Snowflake using the same Snowflake-native governance tools they already know. The app never bypasses governance — it reads from governed views where policies are enforced at the platform layer. Any future policy changes the security team makes are automatically honored without app updates.

**Capabilities Revealed:** Governance Awareness panel (informational — governed view listing, default masking state, schema change notifications, guidance text), governed view as data contract, default QUERY_TEXT masking (REDACT mode), REDACT/FULL/CUSTOM toggle, consumer-applied masking (regex PII scrubbing via `ALTER VIEW`), consumer-applied row access policy, Event Table governed view with masking hooks on RECORD/RECORD_ATTRIBUTES/VALUE, governed view auto-refresh on Event Table schema changes, "Leverage, Don't Replicate" design philosophy. *(Post-MVP: Full Governance Compliance tab with classification awareness, policy detection, consumer policy enumeration.)*

---

### Journey 7: Event Table Schema Change — Automatic Governed View Refresh

**Persona:** Maya — Snowflake Administrator. Her development team adds a new column to their custom Event Table to capture additional telemetry context.

**Opening Scene:** Maya's dev team notifies her: "We just added a `deployment_environment` column to our Event Table to track prod vs staging spans. The Splunk export should pick this up automatically, right?"

**Rising Action:**
1. The dev team runs `ALTER TABLE custom_events ADD COLUMN deployment_environment VARCHAR`. The Event Table schema changes — column count increases from 8 to 9.
2. **Hourly detection alert runs:** Within the next hour, the `governed_view_schema_drift_alert` serverless alert executes. It calculates the current MD5 hash of the Event Table's column names and compares it to the stored hash in the governed view registry table. Hashes differ → schema change detected.
3. The alert calls the `recreate_stale_governed_views()` stored procedure. The procedure executes `CREATE OR REPLACE VIEW governed_custom_events AS SELECT * FROM custom_events`. The governed view now includes the new `deployment_environment` column.
4. **Impact:** The `CREATE OR REPLACE VIEW` operation drops all consumer-applied governance policies (masking policies on RECORD/VALUE columns, row access policies, tags). The stream on the governed view breaks — offset is lost.
5. The procedure updates the registry: `source_schema_hash = new_hash`, `schema_changed = true`. The procedure logs the recreation event to the app's event table: `"Governed view recreated: governed_custom_events. Reason: schema change detected (column added). Policies dropped. Stream broken."`
6. **Stream auto-recovery:** On the next triggered task execution, the task detects the broken stream, drops it, and recreates a new append-only stream on the governed view. The new stream starts from the current Event Table state (data gap from the recreation window). The recovery is logged to `_metrics.pipeline_health` and the app event table.

**Climax:** Maya opens the Streamlit UI and navigates to the Governance Awareness panel. She sees a warning notification:

```
View: GOVERNED_CUSTOM_EVENTS
Status: ⚠️ Schema changed - view recreated
Action: Re-apply governance policies if needed
```

Maya realizes the masking policy her security team applied to the `RECORD` column last month was dropped. She notifies the DBA to re-apply it.

**Resolution:** The DBA re-applies the masking policy: `ALTER VIEW governed_custom_events ALTER COLUMN RECORD SET MASKING POLICY consumer_schema.mask_pii FORCE`. Maya acknowledges the notification in the Streamlit UI — the `schema_changed` flag resets to false, and the warning disappears. The pipeline continues exporting with the new column included and governance policies restored.

**Capabilities Revealed:** Hourly schema change detection (MD5 fingerprinting), automatic governed view recreation, governed view registry table (schema hash storage, change flag), Streamlit UI schema change notification in Governance Awareness panel, consumer acknowledgment workflow, integration with existing stream auto-recovery, policy re-application guidance.

---

### Journey Requirements Summary

| Journey | Key Capabilities Required |
|---|---|
| **Maya Happy Path** | Marketplace install, Permission SDK privilege binding, observability target discovery, pack selection UI with per-source schedule interval display/modification, HEC destination config, governed view creation with default masking, independent scheduled task provisioning, Governance Awareness panel, Pipeline Health Overview |
| **Ravi Happy Path** | Event Table reference binding, governed view over Event Table, entity discrimination (SQL/Snowpark scope), stream polling interval display/modification, OTel DB Client convention enrichment (`db.*` + `snowflake.*`), OTLP destination config, stream creation on governed view, triggered task provisioning, OTLP/gRPC span export, HEC log export |
| **Edge Case: Splunk Enterprise Down** | HEC transport-level retry (httpx/tenacity), governed view pipeline reads, failure logging to pipeline_health, watermark advancement on failure, stream offset advancement on failure, failure KPI visualization |
| **Edge Case: Splunk O11y Cloud Down** | OTLP/gRPC transport-level retry (OTel SDK), independent failure per protocol, partial success handling (logs succeed while spans fail), split status visualization |
| **Edge Case: Stale Stream** | Automatic stream staleness detection and auto-recovery (drop/recreate stream on governed view — never `CREATE OR REPLACE VIEW`), data gap recording in pipeline_health, recovery event logging to app event table |
| **Pipeline Health Monitoring** | Pipeline Health Overview tab (3 KPIs), per-source status, pipeline_health table, app operational logging via Native App event definitions, structured log queries via Snowsight. *(Post-MVP: Streamlit Logging tab, volume estimator.)* |
| **Seamless Upgrade** | Idempotent setup.sql, versioned schema, version pinning, stateful table preservation, ACCOUNT_USAGE governed view safe rebuild, Event Table governed view preserved (ALTER only), per-task recreation, watermark continuity, application role preservation, structured upgrade logging (per-step INFO messages to app event table) |
| **Data Governance** | Governance Awareness panel (informational — governed view listing, default masking state, schema change notifications, guidance), governed view as data contract for ALL sources, default QUERY_TEXT masking (REDACT), REDACT/FULL/CUSTOM toggle, consumer-applied masking/RAP on governed views, Event Table governed view with masking hooks (RECORD, RECORD_ATTRIBUTES, VALUE), governed view auto-refresh on Event Table schema changes, "Leverage, Don't Replicate". *(Post-MVP: Full Governance Compliance tab with classification awareness, policy detection, consumer policy enumeration.)* |
| **Event Table Schema Change** | Hourly schema change detection (MD5 fingerprinting), automatic governed view recreation, governed view registry table, Streamlit UI schema change notification, consumer acknowledgment workflow, integration with stream auto-recovery |

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
| **Data isolation** | Complete — each install has its own stateful tables (`_internal.config`, `_internal.export_watermarks`, `_metrics.pipeline_health`), governed views, streams, tasks, secrets, and EAI objects. No cross-account data mixing. |
| **Compute isolation** | Each install uses the consumer's own serverless compute (serverless tasks). No shared compute between installs. |
| **Namespace isolation** | App objects live in the app's owned schemas (`app_public` versioned schema, `_internal`, `_metrics`). Consumer objects (governed views, streams, tasks) are created in a consumer-granted database/schema. |
| **Upgrade isolation** | Each consumer's maintenance policy controls when upgrades apply. Different consumers can run different versions during rollout windows. |

#### 1.2 Permission & RBAC Model

**Design principle: KISS — single application role.**

| Role | Name | Scope | Rationale |
|---|---|---|---|
| **App Admin** | `app_admin` | Full access to all app capabilities: configuration, pack management, destination setup, governance tab, pipeline health, logging tab | A Snowflake administrator who installs a Marketplace app is inherently a privileged user. Adding viewer/operator roles adds complexity without clear value for MVP — the admin can share Pipeline Health dashboards via Splunk instead. |

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
| **Licensing** | Managed entirely through existing Splunk product licenses (Splunk Enterprise, Splunk Observability Cloud). The app is a delivery mechanism, not a separately licensed product. |
| **Snowflake compute costs** | Borne by the consumer — serverless task executions, warehouse compute for stored procedures. Documented in consumer-facing sizing guide. |
| **Billable events** | Not used. No Snowflake billable events framework integration planned. |
| **Future monetization** | Not applicable — value accrues to Splunk's core products (increased data ingest, expanded platform usage). The app is a GTM/ecosystem play. |

### 2. Compliance & Regulatory

#### 2.1 Snowflake Marketplace Compliance

The app follows the Snowflake Marketplace application lifecycle — no independent compliance attestation (SOC 2, ISO 27001, etc.) is required for the app itself. Compliance requirements:

| Requirement | How We Comply |
|---|---|
| **Security scan (APPROVED)** | Manual scan on test build before submission, per Marketplace publishing workflow guidelines |
| **DISTRIBUTION = EXTERNAL** | App package configured for Marketplace distribution; triggers automated security scan on every version |
| **No hardcoded credentials** | All secrets stored in Snowflake Secrets (SECRET object); HEC tokens and OTLP access tokens never in code |
| **Enforced standards compliance** | manifest.yml v2, setup.sql idempotent, no blocked functions in shared content |
| **Content Security Policy (CSP)** | Streamlit UI complies with Snowflake's CSP restrictions — no external JS/CSS/fonts/images, no `unsafe_allow_html`, no third-party components |

#### 2.2 Data Privacy & Governance — "Leverage, Don't Replicate"

The app does NOT implement its own data classification or privacy enforcement engine. This is a **foundational design decision.** Snowflake's governance policies are enforced at the **platform layer** — below our application code. The app leverages Snowflake Horizon Catalog capabilities:

| Snowflake Capability | How the App Leverages It |
|---|---|
| **Automated sensitive data classification** (ML-based, semantic/privacy category tags) | *(Post-MVP)* App queries classification metadata (`TAG_REFERENCES`, `DATA_CLASSIFICATION_LATEST`) to populate the full Governance Compliance tab. MVP: Governance Awareness panel provides informational guidance only. |
| **Dynamic data masking** (column-level, role-based, tag-based) | Enforced automatically by Snowflake on governed view queries. High-risk sources get app-provided default masking (QUERY_TEXT → REDACT). Consumer can apply custom masking to any governed view. |
| **Row access policies** (row-level filtering) | Consumer attaches RAP to any governed view to control which rows are exported. Example: exclude internal service account queries. |
| **Projection policies** (column blocking) | Consumer attaches projection policies to block specific columns from export. |
| **Tag-based policy assignment** (scalable governance) | Policies assigned to tags propagate to all tagged columns automatically. The app reads `POLICY_REFERENCES` to show which policies are active. |

**Key constraint — blocked context functions:** In the Native App Framework, `IS_ROLE_IN_SESSION()`, `CURRENT_ROLE()`, and `CURRENT_USER()` return NULL in shared content and owner's-rights stored procedures. Masking policies that use role-based conditions always evaluate the NULL branch. This is actually the **desired behavior** for export use cases — the app always sees the masked data (safe default). Consumer guidance in the Streamlit UI explains this.

#### 2.3 QUERY_TEXT Privacy (ACCOUNT_USAGE)

`QUERY_TEXT` in QUERY_HISTORY is the highest-risk field — may contain literal PII values embedded in SQL (email addresses, SSNs, passwords in WHERE clauses). The governed view architecture addresses this:

| Mode | Behavior | Default? |
|---|---|---|
| **REDACT** | App's built-in masking policy active on `QUERY_TEXT`. All queries return `'***REDACTED***'`. | **Yes** |
| **FULL** | App removes the masking policy. `QUERY_TEXT` flows as-is. Consumer explicitly acknowledges privacy implications. | No |
| **CUSTOM** | Consumer's own masking policy detected (e.g., regex PII scrubbing). App shows consumer's policy name. | No |

#### 2.4 Event Table Span/Log Attribute Privacy

Span and log attributes (RECORD, RECORD_ATTRIBUTES, VALUE columns in Event Tables) are OBJECT/VARIANT type and may contain PII logged by consumer applications. Masking policies are **blocked on event tables directly** — the governed view is the only place to apply value-level redaction. All three high-risk columns are included in the governed view (the pipeline needs them); the consumer protects sensitive content by attaching masking policies to the governed view columns.

### 3. Technical Constraints

#### 3.1 Governed View Architecture (Pattern C)

Every data source flows through a **custom governed view** created by the app. This is the uniform data access pattern for both pipeline types:

| Pipeline | Data Path | Governed View Role |
|---|---|---|
| **Event Table (event-driven)** | Event Table → Governed View → Stream (APPEND_ONLY) → Triggered Task → Splunk | Consumer attaches RAP + masking. Masking is blocked on Event Tables directly; the view is the only governance intermediary. Stream respects policies on the view. |
| **ACCOUNT_USAGE (poll-based)** | ACCOUNT_USAGE System View → Governed View → Independent Scheduled Task (watermark) → Splunk | Consumer attaches RAP + masking + projection. Cannot apply policies to system ACCOUNT_USAGE views directly; governed view is the workaround. |

**Critical operational constraint (Event Table views):** `CREATE OR REPLACE VIEW` on the governed Event Table view **breaks all streams** on it — offset is lost, unrecoverable. All policy changes MUST use `ALTER VIEW`. The app's upgrade process and consumer documentation explicitly prohibit view recreation after streams exist. ACCOUNT_USAGE governed views are safe to `CREATE OR REPLACE` (no streams, poll-based pipeline).

**Governed View Auto-Refresh (Event Table Schema Changes):**

When a consumer modifies the schema of a source Event Table (columns added/removed/renamed), the governed view becomes stale and must be recreated. The app implements automatic detection and recreation:

**Detection Mechanism:**
- Schema fingerprinting using MD5 hash of column names (ordered by position)
- Serverless alert runs hourly, comparing current hash vs stored hash
- If hashes differ → schema changed, trigger recreation

**Metadata Storage (Governed View Registry Table):**
```
- governed_view_name          VARCHAR
- source_event_table_name     VARCHAR  
- source_event_table_database VARCHAR
- source_event_table_schema   VARCHAR
- source_schema_hash          VARCHAR(32)
- schema_changed              BOOLEAN
```

**Recreation Process:**
```
FOR each governed_view WHERE schema_changed = true:
  CREATE OR REPLACE VIEW (policies dropped, streams broken)
  UPDATE registry: new hash, schema_changed = true
```

**Impact:** `CREATE OR REPLACE VIEW` drops all governance policies (masking, row access, projection, tags) and breaks streams. Consumer must re-apply policies after recreation. Existing stream auto-recovery mechanism handles broken streams.

**Consumer Notification:** Streamlit UI Governance Awareness panel displays status warning when `schema_changed = true`. Consumer acknowledges notification, which resets flag to false.

#### 3.2 Entity Discrimination — Event Table Telemetry Scope

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
- **Cortex AI Pack**: Separate data source (`AI_OBSERVABILITY_EVENTS` table accessed via `GET_AI_OBSERVABILITY_EVENTS()` function). Cortex AI Functions, Cortex Agents, Cortex Search telemetry enriched with OTel `gen_ai.*` conventions. Uses governed view + poll-based pipeline (not Event Table stream).

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
| **State management** | Internal tables (`_internal.config`, `_internal.export_watermarks`) + governed views + streams | State survives upgrades. Watermarks ensure exactly-once semantics (happy path). |
| **Networking** | EAI + Network Rules per Splunk destination | Snowflake-native outbound networking. No VPN or PrivateLink required (MVP). |
| **Secret management** | Snowflake Secrets for all credentials | Never in code, never in config tables. Rotatable without app restart. |
| **Self-monitoring** | App event table logging (Native App event definitions) + `_metrics.pipeline_health` table | Pipeline Health Overview tab in Streamlit UI. Log queries via Snowsight (MVP). *(Post-MVP: Streamlit Logging tab.)* |
| **Error handling** | Transport-level retry per destination + failure logging + pipeline advancement | MVP trade-off: data gap on sustained outage. Post-MVP: zero-copy failure tracking. |
| **Testing** | Cross-account install testing + manual security scan on test build | Marketplace compliance. E2E validation before submission. |

### 4. Integration Architecture

#### 4.1 Outbound Integrations (App → Splunk)

| Integration | Protocol | Purpose | Auth | MVP |
|---|---|---|---|---|
| **Splunk Enterprise / Cloud (HEC)** | HTTPS (REST) | Export ACCOUNT_USAGE events + Event Table logs | HEC token (Snowflake Secret) | Yes |
| **Splunk Observability Cloud (OTLP)** | gRPC (TLS) | Export Event Table spans + metrics | Access token (Snowflake Secret) | Yes |

#### 4.2 Inbound Data Sources (Snowflake → App)

| Integration | Access Method | Purpose | MVP |
|---|---|---|---|
| **ACCOUNT_USAGE views** (QUERY_HISTORY, TASK_HISTORY, COMPLETE_TASK_GRAPHS, LOCK_WAIT_HISTORY) | SQL via governed views (poll-based, watermark) | Performance Pack telemetry | Yes |
| **Event Table** (`SNOWFLAKE.TELEMETRY.EVENTS` or user-created) | SQL via governed view + stream (event-driven) | Distributed Tracing Pack telemetry (spans, metrics, logs) | Yes |
| **ACCOUNT_USAGE governance metadata** (TAG_REFERENCES, DATA_CLASSIFICATION_LATEST, POLICY_REFERENCES) | SQL read-only | *(Post-MVP)* Full Governance Compliance tab — classification awareness, policy display. MVP Governance Awareness panel is informational only. | No (post-MVP) |
| **ACCOUNT_USAGE views** (METERING_HISTORY, WAREHOUSE_METERING_HISTORY, PIPE_USAGE_HISTORY, SERVERLESS_TASK_HISTORY, AUTOMATIC_CLUSTERING_HISTORY, STORAGE_USAGE, DATABASE_STORAGE_USAGE_HISTORY, DATA_TRANSFER_HISTORY, REPLICATION_USAGE_HISTORY, SNOWPARK_CONTAINER_SERVICES_HISTORY, EVENT_USAGE_HISTORY) | SQL via governed views (poll-based) | Cost Pack (post-MVP) | No |
| **ACCOUNT_USAGE views** (LOGIN_HISTORY, ACCESS_HISTORY, SESSIONS, GRANTS_TO_USERS, GRANTS_TO_ROLES, NETWORK_POLICIES) | SQL via governed views (poll-based) | Security Pack (post-MVP) | No |
| **ACCOUNT_USAGE views** (COPY_HISTORY, LOAD_HISTORY, PIPE_USAGE_HISTORY) | SQL via governed views (poll-based) | Data Pipeline Pack (post-MVP) | No |
| **Event Table** (Openflow telemetry with `RESOURCE_ATTRIBUTES:"application" = 'openflow'`) | SQL via governed view + stream (event-driven) | Openflow Pack (post-MVP) — pipeline execution traces, task orchestration, data flow monitoring | No |
| **AI_OBSERVABILITY_EVENTS** (via `GET_AI_OBSERVABILITY_EVENTS()` function) | SQL/function call via governed view (poll-based) | Cortex AI Pack (post-MVP) — Cortex AI Functions, Cortex Agents, Cortex Search telemetry enriched with OTel `gen_ai.*` conventions | No |

#### 4.3 Snowflake Platform Services (App ↔ Snowflake)

| Service | Purpose | MVP |
|---|---|---|
| **Python Permission SDK** | Privilege binding via native Snowsight grant prompts | Yes |
| **External Access Integration (EAI) + Network Rules** | Outbound networking to Splunk HEC and OTLP endpoints | Yes |
| **Snowflake Secrets** | Secure storage for HEC tokens and OTLP access tokens | Yes |
| **Serverless Tasks** (scheduled + triggered) | Pipeline execution — poll-based and event-driven | Yes |
| **Streams** (append-only on governed views) | Change data capture for Event Table pipeline | Yes |
| **Versioned Schemas** | Stateless object management for upgrades | Yes |
| **Native App Event Definitions** | App operational logging to consumer's event table | Yes |
| **Snowflake Horizon Catalog** (classification, masking, RAP, projection, tags) | Governance policy enforcement on governed views | Yes (leveraged, not called directly) |
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

#### 4.5 Splunk CIM Mapping (ACCOUNT_USAGE → HEC → Splunk Enterprise/Cloud)

ACCOUNT_USAGE data is exported as structured JSON events to HEC with Splunk Common Information Model (CIM) normalization. This enables automatic surface in Splunk Enterprise Security dashboards, ITSI, and CIM-accelerated searches.

**MVP CIM Mappings:**

| ACCOUNT_USAGE View | CIM Data Model | CIM Tags | Sourcetype | Fit |
|---|---|---|---|---|
| **QUERY_HISTORY** | Databases | `database query` | `snowflake:query_history` | Excellent |
| **TASK_HISTORY** | Databases | `database query` | `snowflake:task_history` | Good |
| **COMPLETE_TASK_GRAPHS** | — (custom) | — | `snowflake:task_graphs` | Custom |
| **LOCK_WAIT_HISTORY** | — (custom) | — | `snowflake:lock_wait_history` | Custom |

**Post-MVP CIM Mappings:**

| ACCOUNT_USAGE View | CIM Data Model | CIM Tags | Sourcetype |
|---|---|---|---|
| **LOGIN_HISTORY** | Authentication | `authentication` | `snowflake:login_history` |
| **ACCESS_HISTORY** | Data Access | `data access` | `snowflake:access_history` |
| **GRANTS_TO_ROLES/USERS** | Change | `change account` | `snowflake:grants` |
| **SESSIONS** | Databases | `database session` | `snowflake:sessions` |

Key CIM field mappings for QUERY_HISTORY (MVP): `QUERY_TEXT` → `query`, `QUERY_ID` → `query_id`, `USER_NAME` → `user`, `WAREHOUSE_NAME` → `dest`, `DATABASE_NAME` → `object`, `TOTAL_ELAPSED_TIME` (ms→s) → `duration`, `vendor_product` = `"Snowflake"`.

#### 4.6 Splunk Source Types

The app defines and registers Splunk source types for each ACCOUNT_USAGE view. Source types follow the `snowflake:<view_name>` naming convention. CIM-mapped source types include tags for automatic data model acceleration.

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
| Task suspension longer than staleness window | **LOW** | **Automatic recovery:** The app detects the stale stream at task execution, drops and recreates the stream on the governed view, records the data gap in `_metrics.pipeline_health`, and logs the recovery event to the app's event table. No manual user action required. The design assumes task suspension > 14 days is an exceptional edge case. |

#### 5.3 Marketplace Delisting

| Risk | Severity | Mitigation |
|---|---|---|
| Security scan failure on submitted version | **HIGH** | Manual security scan on test build before submission (allowed by Marketplace workflow). Fix all findings before formal submission. |
| Non-compliance with Marketplace enforced standards | **MEDIUM** | Automated checks in CI: manifest.yml v2 validation, blocked function detection, `DISTRIBUTION=EXTERNAL` scan. |

#### 5.4 Data Loss (MVP Trade-off)

| Risk | Severity | Mitigation |
|---|---|---|
| Sustained Splunk outage causes permanent data gaps (MVP — no failure tracking) | **MEDIUM** | Transport-level retries handle transient blips (seconds). Sustained outages (minutes to hours) create gaps. Pipeline Health dashboard is early warning. Post-MVP: zero-copy failure tracking with reference-based retry will close this gap. |
| Partial signal loss (OTLP down but HEC up, or vice versa) | **LOW** | Independent export per protocol. Pipeline Health shows split status. Documented MVP trade-off. |

#### 5.5 Governance Policy Interaction

| Risk | Severity | Mitigation |
|---|---|---|
| Consumer's role-based masking policies always hit NULL branch (blocked context functions in Native App) | **LOW** | This is the **desired behavior** for export — app always sees masked data (safe default). Consumer guidance in Streamlit UI explains: use unconditional masking (regex scrubbing) or REDACT/FULL toggle, not role-based conditions. |
| Consumer applies `CREATE OR REPLACE VIEW` to governed view (breaking streams) | **MEDIUM** | Prominent documentation warns against view recreation. App auto-recovers stale/broken streams (drop/recreate stream, data gap recorded). |
| Projection policy blocks a column the pipeline needs | **LOW** | Pipeline gracefully handles NULL columns. Logs warning to `_metrics.pipeline_health`. |
| Governed view auto-refresh drops consumer-applied policies | **MEDIUM** | Streamlit UI displays schema change notification when recreation occurs. Consumer acknowledges and re-applies policies. Hourly detection interval limits notification frequency. Stream auto-recovery handles broken streams automatically. |
| DML operations trigger false positive schema changes | **LOW** | MD5 hash fingerprinting detects only DDL changes (column add/remove/rename). DML operations (data inserts) do not change column structure and do not trigger recreation. |

#### 5.6 Innovation-Specific Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Future Snowflake Event Table schema changes break enrichment logic | **LOW** | Defensive parsing — unknown attributes pass through; only known attributes are enriched |
| Serverless compute limits (max concurrent tasks, memory) at high telemetry volume | **MEDIUM** | Document sizing guidance; post-MVP: compute pool option for high-volume accounts |
| Auto-recovery creates silent data gaps user doesn't notice | **LOW** | Data gap window logged to `_metrics.pipeline_health` and app event table; Pipeline Health Overview shows past incident notes |

## Innovation & Novel Patterns

### Detected Innovation Areas

**1. Governed View as Universal Data Contract**
No existing Snowflake Native App or connector uses custom governed views as the uniform intermediary between all Snowflake telemetry sources and an external export pipeline. The standard pattern is direct reads from ACCOUNT_USAGE or Event Tables. The governed view pattern solves a real unaddressed gap — you can't apply masking, row access, or projection policies to system ACCOUNT_USAGE views or Event Tables directly. The governed view is the only governance intermediary, and it works uniformly for both pipeline types (event-driven and poll-based). This is a genuinely novel contribution to the Snowflake Native App ecosystem.

**2. Convention-Transparent Telemetry Relay with Additive Enrichment**
Most telemetry pipelines strip, rename, or reshape attributes during processing. This app preserves ALL original Event Table attributes from producers and enriches additively with OTel semantic convention layers (`db.*`, `snowflake.*`, `service.*`, `cloud.*`). The "preserve everything, enrich only" pattern is an architectural differentiator — it respects the producer's telemetry while making it Splunk-native. No original context is lost.

**3. Zero-Infrastructure Observability Bridge**
Shipping an observability pipeline as a Marketplace-installable Snowflake Native App (zero external infrastructure, zero agents, zero collectors) is fundamentally different from the OTel Collector pattern used by every other Snowflake observability solution. The pipeline runs inside the customer's Snowflake account using serverless compute — no VMs, no containers, no network infrastructure to manage. Install-to-first-data in minutes, not hours.

**4. "Leverage, Don't Replicate" Governance Philosophy**
Instead of building its own data classification, masking, or privacy engine, the app deliberately delegates to Snowflake's existing Horizon Catalog governance stack. This philosophy-level design decision reduces attack surface, eliminates maintenance burden for governance logic, and prevents governance policy drift. The app inherits every current and future governance feature Snowflake ships — without code changes.

**5. Entity Discrimination — Scoped Telemetry from Shared Multi-Service Sink**
Snowflake's Event Table is a shared telemetry sink for all Snowflake services. Filtering it with a positive include-list on `RESOURCE_ATTRIBUTES:"snow.executable.type"` to scope MVP telemetry to SQL/Snowpark compute — while remaining inherently resilient to new entity types Snowflake adds in the future — is a novel approach no other Snowflake observability tool uses. The positive include-list pattern means new service categories are safely excluded until explicitly registered. Post-MVP expansion includes SPCS (`snow.executable.type = 'spcs'`), Streamlit (`snow.executable.type = 'streamlit'`), and Openflow (`RESOURCE_ATTRIBUTES:"application" = 'openflow'`) via the service category registry. The Cortex AI Pack uses a separate dedicated data source (`AI_OBSERVABILITY_EVENTS` table) rather than Event Tables.

**6. Self-Healing Pipelines**
Stale stream detection with automatic drop/recreate recovery — including data gap logging to both `_metrics.pipeline_health` and the app's event table — makes the pipeline self-healing without manual intervention. Combined with `SUSPEND_TASK_AFTER_NUM_FAILURES` for export errors and `TASK_AUTO_RETRY_ATTEMPTS`, the app handles failure modes transparently. No manual "fix it" buttons.

**7. Dual-Destination Export with Independent Failure Handling**
A single Event Table pipeline splits into HEC (logs/events) and OTLP/gRPC (spans/metrics) with independent failure handling per destination. One destination can fail while the other succeeds — partial success is tracked and displayed in the Pipeline Health dashboard with split status indicators. This partial-success model is unusual in telemetry pipelines, where most treat export as all-or-nothing.

### Market Context & Competitive Landscape

| Existing Approach | Limitation | Our Innovation |
|---|---|---|
| **OTel Collector with Snowflake receiver** | External infrastructure required (VMs/containers), network configuration, separate credential management, no Snowflake-native governance | Zero-infrastructure Native App, governed views for policy enforcement, Marketplace install |
| **Snowflake DB Connect for Splunk** | JDBC-based polling, no Event Table support, no OTel conventions, no governance intermediary | Dual-pipeline (event-driven + poll-based), OTel DB Client conventions, governed view architecture |
| **Custom ETL (Airflow, dbt + scripts)** | High maintenance, no standardization, no CIM mapping, no self-healing | Marketplace-managed upgrades, CIM normalization, auto-recovery, zero operator toil |
| **Snowflake's built-in event sharing** | Provider-to-consumer only, no Splunk integration, no governance view layer | Consumer-side governed views with full policy attachment, direct Splunk export |

### Validation Approach

| Innovation | Validation Method |
|---|---|
| **Governed View pattern** | E2E test: attach masking + RAP to governed view → verify exported data is masked and row-filtered in Splunk |
| **Convention-transparent relay** | Compare exported span attributes with raw Event Table attributes — assert zero attribute loss, additive enrichment only |
| **Zero-infrastructure pipeline** | Measure install-to-first-data latency (target < 15 min). Compare with OTel Collector setup time (typically hours) |
| **"Leverage, Don't Replicate"** | Attach 5+ different policy combinations to governed views → verify all honored in export without app code changes |
| **Entity discrimination** | Export with filter → verify zero out-of-scope service category rows in Splunk. Add new service type to Event Table → verify it is excluded |
| **Self-healing pipeline** | Suspend triggered task for > 14 days → verify stream auto-recreates, pipeline resumes, data gap is logged |
| **Dual-destination export** | Kill HEC endpoint → verify OTLP export continues → verify Pipeline Health shows split status per destination |

*Innovation-specific risks are consolidated in Technical & Platform Requirements § 5.6.*

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach:** Platform MVP — prove that a Snowflake Native App can serve as a zero-infrastructure observability bridge with comparable telemetry export performance to external OTel Collector pipelines.

**Core Learning Goal:** Can a single Marketplace-installable app, running entirely inside the consumer's Snowflake account, deliver telemetry to Splunk with latency parity or better than external collectors — with zero consumer infrastructure?

**Resource:** Solo engineer + PM (same person). 1 month to Marketplace submission.

**Key Scoping Decisions:**

| Decision | Rationale |
|---|---|
| **Keep streams for Event Table pipeline** | Polling an unclustered Event Table with millions of rows is fundamentally different from polling pre-filtered ACCOUNT_USAGE views. Streams give efficient delta processing, < 60s latency, cost efficiency (triggered task), and exactly-once row guarantees. The staleness and breakage risks are already mitigated (auto-recovery, ALTER VIEW only). |
| **Simplify Governance Compliance tab** | MVP: high-level governance awareness panel — informational text highlighting the importance of managing data governance via Snowflake capabilities before exporting telemetry. Lists governed views and their default masking state. No policy detection, no classification awareness, no consumer policy enumeration. Full governance UI deferred to post-MVP. |
| **Defer Logging tab (Streamlit UI)** | MVP: app logs to the consumer's event table via Native App event definitions (structured logs with severity, source, error details). Debugging via direct event table queries in Snowsight. Streamlit Logging tab (verbosity selector, search, scrollable display) deferred to post-MVP. |
| **Defer volume estimator** | Not essential for core export workflow. Deferred to post-MVP. |
| **Keep CIM normalization** | Low effort — just correct JSON field naming per CIM conventions. Essential for Splunk-side value (ES dashboards, data model acceleration). |

### MVP Feature Set (Phase 1)

**Core Journeys Supported:** All 7 journeys are supported, with scoping simplifications noted.

| Journey | MVP Coverage | Simplifications |
|---|---|---|
| **1. Maya Install/Configure** | Full | Schedule interval display included |
| **2. Ravi Traces** | Full | None |
| **3. Edge Cases (Splunk Down, Stale Stream)** | Full | Auto-recovery included |
| **4. Pipeline Debugging (Sam)** | Partial | Pipeline Health Overview (3 KPIs, per-source status) included. Logging tab deferred — Sam queries event table via Snowsight for error details. |
| **5. Seamless Upgrade** | Full | None |
| **6. Data Governance (Maya)** | Partial | Simplified governance awareness panel — informational, no policy detection. QUERY_TEXT REDACT/FULL/CUSTOM toggle included. |
| **7. Event Table Schema Change** | Full | None |

**Must-Have Capabilities:**
1. Marketplace install + Permission SDK privilege binding
2. Governed View Architecture (all sources)
3. Distributed Tracing Pack (Event Table → Stream → Triggered Task → OTLP/gRPC + HEC)
4. Performance Pack (ACCOUNT_USAGE → Scheduled Tasks → HEC, CIM-normalized)
5. Streamlit Configuration UI (setup wizard, pack toggles, schedule config, destination setup, QUERY_TEXT privacy toggle, simplified governance awareness panel with schema change notifications)
6. Pipeline Health Overview (3 KPI cards, per-source status)
7. App Operational Logging (event definitions → consumer event table, queryable via Snowsight)
8. Transport retries (HEC + OTLP) with failure logging to `_metrics.pipeline_health`
9. Auto-recovery for stale Event Table streams
10. Governed view auto-refresh (hourly schema change detection, automatic recreation, Streamlit UI notification)
11. Marketplace-ready packaging (manifest.yml v2, setup.sql, security scan)

### Post-MVP Features (Phase 2 — Growth)

| Feature | Priority | Dependency |
|---|---|---|
| **Streamlit Logging tab** (verbosity selector, search, scrollable display) | High | App logging already in place — UI only |
| **Full Governance Compliance tab** (classification awareness, policy detection, consumer policy enumeration) | High | Governance metadata queries already available |
| **Volume estimator** | Medium | Pipeline health data already collected |
| **Cost Pack** (METERING_HISTORY, WAREHOUSE_METERING_HISTORY, PIPE_USAGE_HISTORY, SERVERLESS_TASK_HISTORY, AUTOMATIC_CLUSTERING_HISTORY, STORAGE_USAGE, DATABASE_STORAGE_USAGE_HISTORY, DATA_TRANSFER_HISTORY, REPLICATION_USAGE_HISTORY, SNOWPARK_CONTAINER_SERVICES_HISTORY, EVENT_USAGE_HISTORY) | Medium | New governed views + scheduled tasks |
| **Security Pack** (LOGIN_HISTORY, ACCESS_HISTORY, SESSIONS, GRANTS_TO_USERS, GRANTS_TO_ROLES, NETWORK_POLICIES) | Medium | New governed views + CIM mappings |
| **Data Pipeline Pack** (COPY_HISTORY, LOAD_HISTORY, PIPE_USAGE_HISTORY) | Medium | New governed views + CIM mappings |
| **Zero-copy failure tracking** (reference-based retry for data gaps) | Medium | New retry task + failure reference table |
| **Advanced Pipeline Health Dashboard** (Throughput, Errors, Volume tabs) | Low | Extends existing Pipeline Health |
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

**Technical Risk (highest):** Event Table pipeline end-to-end (governed view → stream → triggered task → signal splitting → OTLP + HEC). Touches the most Snowflake primitives and has the tightest latency requirement (< 60s). **Mitigation:** Build and test this pipeline first. If it works, everything else is lower risk.

**Solo-engineer Risk:** Single point of failure for a 1-month timeline. **Mitigation:** Prioritize backend pipelines first (weeks 1-2), Streamlit UI second (week 3), Marketplace packaging and testing last (week 4). If time runs short, the simplified Governance panel and Pipeline Health can ship with minimal UI polish.

**Market Risk:** Low — the Snowflake + Splunk joint customer base is well-established. The risk is execution speed, not market fit. **Mitigation:** MVP go/no-go gates (latency parity, zero P1/P2, security scan) are binary — ship or don't ship. No soft launches.

**Streams vs Polling Decision (documented):** Streams were evaluated against watermark-based polling for Event Tables. Streams kept for MVP due to: efficient delta processing on unclustered high-volume tables, < 60s latency achievable, cost-efficient triggered tasks, exactly-once row guarantees. Polling would degrade with Event Table volume and require additional dedup logic.

## Functional Requirements

### Installation & Setup

- **FR1:** Admin can install the app from the Snowflake Marketplace with zero external infrastructure provisioning
- **FR2:** Admin can grant required privileges through native Snowflake permission prompts during first launch
- **FR3:** Admin can complete initial setup through a guided wizard that walks through privilege binding, source selection, and destination configuration

### Source Configuration

- **FR4:** Admin can discover available ACCOUNT_USAGE views and Event Tables in their Snowflake environment
- **FR5:** Admin can enable or disable Monitoring Packs (Distributed Tracing Pack, Performance Pack) independently
- **FR6:** Admin can view the default schedule interval for each selected data source
- **FR7:** Admin can modify the schedule interval for any individual data source
- **FR8:** Admin can configure HEC destination credentials and endpoint for Splunk Enterprise/Cloud export
- **FR9:** Admin can configure OTLP/gRPC destination credentials and endpoint for Splunk Observability Cloud export
- **FR10:** Admin can view and modify the Event Table stream polling interval

### Data Governance & Privacy

- **FR11:** Admin can view a list of all governed views created by the app and their current default masking state
- **FR12:** Admin can toggle QUERY_TEXT export mode between REDACT (default), FULL, and CUSTOM
- **FR13:** The system enforces QUERY_TEXT masking by default (REDACT mode) — no raw SQL leaves Snowflake unless the admin explicitly opts in
- **FR14:** Consumer DBA can attach Snowflake-native masking policies to any governed view, and the export pipeline automatically honors them
- **FR15:** Consumer DBA can attach row access policies to any governed view, and the export pipeline automatically filters exported rows
- **FR16:** Consumer DBA can attach projection policies to governed view columns, and the pipeline gracefully handles resulting NULL columns
- **FR17:** Admin can view governance guidance that explains the importance of managing data governance via Snowflake capabilities before exporting telemetry

### Telemetry Collection

- **FR18:** The system collects Event Table telemetry incrementally using change data capture (new rows only)
- **FR19:** The system filters Event Table telemetry to SQL/Snowpark compute scope (stored procedures, UDFs/UDTFs, SQL queries) via entity discrimination
- **FR20:** The system collects each enabled ACCOUNT_USAGE source independently on its own schedule using watermark-based incremental reads
- **FR21:** The system creates a governed view for every enabled data source (Event Tables and ACCOUNT_USAGE views) as the uniform data access intermediary
- **FR22:** The system stores schema fingerprints (MD5 hash of column names) for each governed view's source Event Table in a registry table
- **FR23:** The system detects Event Table schema changes by comparing current schema fingerprint against stored fingerprint via hourly serverless alert
- **FR24:** The system automatically recreates governed views when source Event Table schema changes are detected (columns added/removed/renamed)
- **FR25:** The system records schema change status in the governed view registry and displays notification in Streamlit UI Governance Awareness panel
- **FR26:** Admin can acknowledge governed view schema change notifications, which resets the notification status
- **FR27:** The system excludes DML operations from schema change detection — only DDL changes (add/remove/rename columns) trigger recreation

### Telemetry Export

- **FR28:** The system exports Event Table spans and metrics to Splunk Observability Cloud via OTLP/gRPC with OTel DB Client semantic conventions (`db.*`) and custom Snowflake conventions (`snowflake.*`)
- **FR29:** The system exports Event Table logs to Splunk Enterprise/Cloud via HEC with CIM-normalized field naming
- **FR30:** The system exports ACCOUNT_USAGE events to Splunk Enterprise/Cloud via HEC with CIM-normalized field naming (Databases data model)
- **FR31:** The system preserves all original Event Table attributes from producers and enriches additively (no attribute stripping or renaming)
- **FR32:** The system retries failed export batches at the transport level for both HEC and OTLP destinations independently
- **FR33:** The system handles partial export success — one destination can fail while the other succeeds, with independent status tracking per destination

### Pipeline Operations & Health

- **FR34:** Ops engineer can view pipeline health summary showing total rows collected, exported, and failed over a configurable time window
- **FR35:** Ops engineer can view per-source pipeline status showing last successful run and current state
- **FR36:** The system logs structured operational events (errors, warnings, info, debug) to the consumer's account-level event table using Native App event definitions
- **FR37:** Ops engineer can query the app's operational logs via Snowsight to diagnose pipeline errors (HEC failures, OTLP failures, processing errors, stream recovery events)
- **FR38:** The system automatically detects and recovers stale Event Table streams by dropping and recreating the stream on the governed view
- **FR39:** The system records data gaps resulting from stream recovery or sustained destination outages in the pipeline health metrics
- **FR40:** The system auto-suspends a failing source after consecutive failures without affecting other sources
- **FR41:** The system records per-run metrics (rows collected, rows exported, failures, latency) for each pipeline source

### App Lifecycle & Marketplace

- **FR42:** The system supports auto-upgrades via Snowflake release directives, respecting the consumer's maintenance policy
- **FR43:** The system preserves all stateful data (configuration, watermarks, pipeline health metrics, governed view registry) across version upgrades
- **FR44:** The system rebuilds stateless objects (procedures, UDFs, Streamlit UI) cleanly during upgrades without interrupting in-flight task executions
- **FR45:** The system uses ALTER VIEW (not CREATE OR REPLACE VIEW) for Event Table governed view changes during upgrades to protect existing streams
- **FR46:** The system logs structured upgrade progress messages (per-step start, completion, errors) to the app's event table
- **FR47:** The system passes Snowflake Marketplace security scanning requirements for all submitted versions

## Non-Functional Requirements

### Performance

- **NFR1:** Event Table telemetry is visible in Splunk within 60 seconds of being written to the Event Table (stream trigger + processing + export)
- **NFR2:** ACCOUNT_USAGE data is visible in Splunk within one polling cycle of Snowflake's inherent view latency (e.g., QUERY_HISTORY with ~45 min Snowflake latency appears in Splunk within ~75 min)
- **NFR3:** Streamlit UI pages load and render within 5 seconds under normal conditions (Snowflake serverless compute startup included)
- **NFR4:** Pipeline Health Overview KPI cards reflect data no older than the most recent completed task run
- **NFR5:** Export batch processing (data transformation + network send) completes within 30 seconds per batch for both HEC and OTLP destinations

### Security

- **NFR6:** All credentials (HEC tokens, OTLP access tokens) are stored exclusively in Snowflake Secrets — never in code, config tables, or logs
- **NFR7:** All outbound connections (HEC, OTLP) use TLS encryption
- **NFR8:** All outbound connections are strictly governed by Snowflake External Access Integrations and Network Rules — no outbound network traffic occurs outside of what is explicitly defined and approved by the consumer
- **NFR9:** QUERY_TEXT is masked by default (REDACT mode) — raw SQL is never exported without explicit admin opt-in
- **NFR10:** The app never bypasses Snowflake-native governance policies — all data reads flow through governed views where platform-layer policies are enforced
- **NFR11:** All app versions pass Snowflake Marketplace automated security scanning with zero Critical or High findings
- **NFR12:** No credential material appears in app operational logs, pipeline health metrics, or Streamlit UI displays
- **NFR13:** All dependencies are free of Critical/High CVEs at the time of Marketplace submission

### Reliability

- **NFR14:** Pipeline uptime >= 99.9% per source (< 8.7 hours unplanned downtime per year), measured by consecutive successful task runs
- **NFR15:** Export success rate >= 99.5% of batches exported successfully (transport retries included), measured via `_metrics.pipeline_health`
- **NFR16:** A single failing source does not impact the availability or scheduling of any other source's pipeline
- **NFR17:** Stale Event Table streams are automatically recovered without manual intervention — data gap is recorded but pipeline resumes autonomously
- **NFR18:** App upgrades complete with zero data loss — watermarks and stream offsets resume from their pre-upgrade positions
- **NFR19:** Transport retries handle transient destination failures (network blips, brief rate limiting) without data loss for outages lasting up to 60 seconds

### Scalability

- **NFR20:** The Event Table pipeline processes up to 1 million rows per triggered task execution without timeout or memory failure
- **NFR21:** The system supports up to 10 concurrent independent ACCOUNT_USAGE scheduled tasks without resource contention
- **NFR22:** Pipeline throughput scales linearly with serverless task compute allocation — no architectural bottlenecks that prevent vertical scaling

### Integration Quality

- **NFR23:** All OTLP-exported spans conform to OTel DB Client semantic conventions (`db.*` namespace) and pass Splunk APM's span validation (visible in Tag Spotlight, trace waterfall)
- **NFR24:** All HEC-exported events conform to Splunk CIM field naming for their respective data models (Databases) and are surface-able in CIM-accelerated searches
- **NFR25:** Splunk source types follow the `snowflake:<view_name>` naming convention and are correctly set on all exported events
- **NFR26:** The app correctly handles HEC and OTLP error responses (4xx, 5xx, gRPC status codes) with appropriate retry or failure-logging behavior per response type
