---
stepsCompleted: [1, 2, 3, 4, 5, 6]
status: complete
inputDocuments:
  - _bmad-output/planning-artifacts/splunk_snowflake_native_app_vision.md
date: 2026-02-15
lastUpdated: 2026-02-22
author: Nik
updateNote: "Aligned with PRD decisions: governed view architecture, entity discrimination (SQL/Snowpark compute scope), simplified Governance Awareness panel, app operational logging via Native App event definitions, stream auto-recovery, per-source schedule configuration, independent scheduled tasks, volume estimator deferred to post-MVP"
---

# Product Brief: snowflake-native-splunk-app

## Executive Summary

Splunk Observability for Snowflake is a turnkey Snowflake Native App distributed via the Snowflake Marketplace that captures and exports Snowflake-native telemetry to Splunk backends. The app delivers a frictionless three-step experience: install from the Marketplace, configure destinations and monitoring packs via a guided Streamlit UI, and observe Snowflake telemetry in Splunk immediately.

**MVP Scope:** The app targets **SQL/Snowpark compute telemetry** — Stored Procedures, UDFs/UDTFs, and SQL queries — by collecting telemetry from two complementary Snowflake-native sources:

- **Event Tables** (real-time application telemetry): Spans, metrics, and logs emitted by stored procedures, UDFs/UDTFs, and SQL queries — scoped via entity discrimination filter (`snow.executable.type IN ('procedure','function','query','sql')`) — exported via OTLP/gRPC to Splunk Observability Cloud (traces, metrics) and via HEC HTTP to Splunk Enterprise/Cloud (logs).
- **ACCOUNT_USAGE views** (operational telemetry): Query performance (QUERY_HISTORY), task execution (TASK_HISTORY, COMPLETE_TASK_GRAPHS), and lock contention (LOCK_WAIT_HISTORY) — exported via HEC HTTP to Splunk Enterprise/Cloud as CIM-normalized structured events.

The architecture employs a dual-pipeline design: an event-driven pipeline (Governed View → Stream → Serverless Triggered Task) for near-real-time Event Table export, and a poll-based pipeline (Governed View → Independent Serverless Scheduled Tasks with watermark-based incremental reads) for ACCOUNT_USAGE data. Every data source flows through a **custom governed view** created by the app — the universal data contract that enables Snowflake-native governance policy enforcement (masking, row access, projection) at the platform layer. Both pipelines run entirely within Snowflake using serverless compute — no consumer warehouse management, no external infrastructure, no additional dependencies.

MVP ships with the **Distributed Tracing Pack** (Event Table spans, metrics, logs → Splunk with OTel DB Client semantic conventions) and the **Performance Pack** (QUERY_HISTORY, TASK_HISTORY, COMPLETE_TASK_GRAPHS, LOCK_WAIT_HISTORY → Splunk with CIM normalization). The governed view architecture ensures all exported data respects Snowflake-native governance policies (masking, row access, projection) applied by the consumer. Additional packs (Cost, Security, Data Pipeline) and full governance UI features are delivered iteratively post-MVP.

---

## Core Vision

### Problem Statement

Organizations running workloads on Snowflake lack a frictionless way to get their Snowflake telemetry into Splunk. Snowflake generates rich observability data — distributed traces from stored procedures and UDFs via Event Tables, query performance metrics via ACCOUNT_USAGE views, warehouse cost data, task execution history, and security audit logs — but this telemetry remains siloed inside Snowflake with no native export path to external observability platforms.

Today, teams attempting to bridge this gap rely on fragmented, high-friction approaches: configuring standalone OTel Collectors to scrape metrics externally, or deploying Splunk DB Connect to pull data from Snowflake tables into Splunk. Both approaches require significant setup expertise, produce data gaps, demand ongoing maintenance, and fail to deliver the real-time, comprehensive coverage that SREs and Snowflake administrators need.

### Problem Impact

When Snowflake telemetry stays siloed and never reaches Splunk, the consequences are material:

- **Application degradation and outages go undetected** — SREs cannot correlate Snowflake-side trace data with broader application observability in Splunk, creating blind spots in incident response.
- **Warehouse cost overruns accumulate silently** — without credit consumption and metering data flowing into Splunk dashboards and alerts, teams discover budget overages after the fact.
- **Slow queries impact downstream business applications** — performance degradation in Snowflake-powered apps (analytics, ML pipelines, data products) goes undiagnosed until users complain.
- **Security incidents are missed** — failed login patterns, privilege escalation, and suspicious access patterns visible in ACCOUNT_USAGE never reach the SOC team's Splunk environment.

### Why Existing Solutions Fall Short

| Current Approach | Limitation |
|---|---|
| **OTel Collector (external scraping)** | Requires deploying and maintaining external infrastructure. Limited to metrics scraping — no native access to Event Table streams or ACCOUNT_USAGE views. Significant setup complexity and operational overhead. |
| **Splunk DB Connect** | Pulls data from Snowflake tables via JDBC. Requires a dedicated heavy forwarder, driver configuration, and ongoing credential management. Not designed for real-time telemetry; introduces latency and data gaps. Cannot access Event Table streams natively. |
| **Custom ETL pipelines** | Bespoke engineering effort per telemetry source. No standardization, no packaging, high maintenance burden. Breaks on Snowflake schema changes. |
| **No solution (status quo)** | Snowflake telemetry remains siloed. Teams operate blind to Snowflake-side performance, cost, and security signals in their primary observability platform. |

None of these approaches deliver the install-and-observe simplicity that a Snowflake Native App enables.

### Proposed Solution

A Snowflake Native App — **Splunk Observability for Snowflake** — distributed via the Snowflake Marketplace, that delivers complete Snowflake observability into Splunk in three steps:

1. **Install** — One-click install from the Snowflake Marketplace, regardless of the customer's Snowflake region. Everything is packaged as a Native App with no external dependencies.
2. **Configure** — A guided Streamlit UI walks the user through granting privileges, binding Event Tables and Splunk credentials, selecting Monitoring Packs, and connecting to Splunk destinations (Observability Cloud via OTLP/gRPC, Enterprise/Cloud via HEC).
3. **Observe** — Telemetry flows to Splunk immediately. Distributed traces appear in Splunk Observability Cloud. Logs, query history, task execution, and operational events appear in Splunk Enterprise/Cloud.

The app runs entirely within Snowflake using serverless compute. No consumer warehouses to manage, no external collectors to deploy, no infrastructure to maintain.

### Key Differentiators

- **Snowflake Marketplace distribution** — Single-click install for any Snowflake customer worldwide. Positions Splunk as the verified, vendor-recommended observability solution for the Snowflake ecosystem. Drives GTM partnership with Snowflake and official Marketplace partner status.
- **Zero external dependencies** — The entire app — pipelines, configuration UI, health dashboard — runs inside Snowflake as a Native App. No external collectors, no additional infrastructure, no driver configurations.
- **Governed view architecture** — Every data source (Event Tables AND ACCOUNT_USAGE views) flows through a custom governed view created by the app. Governed views are the universal data contract that enables Snowflake-native governance policy enforcement (masking, row access, projection) at the platform layer. Consumers attach policies to governed views; the app never bypasses them.
- **Dual-pipeline architecture** — Event-driven (Governed View → Stream → Serverless Triggered Task) for near-real-time Event Table telemetry, plus poll-based (Governed View → Independent Serverless Scheduled Tasks + Watermarks) for ACCOUNT_USAGE views. Each ACCOUNT_USAGE source gets its own independent task with source-specific schedule. Covers both real-time application traces and operational telemetry.
- **Monitoring Pack model** — Pre-built, domain-specific packs (Distributed Tracing, Performance, Cost, Security, Data Pipeline) that customers enable with toggle switches. No Snowflake expertise required to select the right telemetry sources. Enables iterative product delivery — each pack developed, tested, and released independently.
- **Frictionless first value** — The "aha" moment: SREs see their first Snowflake distributed trace in Splunk Observability Cloud and their first UDF/stored procedure logs in Splunk Enterprise within minutes of setup — not days of configuration.

---

## Target Users

### Primary Users

#### Persona 1: Maya — Snowflake Platform Administrator

**Role:** Senior Snowflake Administrator at a mid-to-large enterprise running 50+ warehouses with hundreds of users across multiple teams (analytics, data engineering, ML, application development).

**Day-to-day:** Maya's morning starts with checking warehouse credit usage, reviewing failed jobs (Snowpipe, Tasks, COPY INTO), analyzing slow-running queries flagged overnight, and responding to user tickets about access issues or performance problems. She manages RBAC (role-based access control), enforces MFA and network policies, monitors storage growth, and ensures compliance with SOC2 and GDPR requirements. She reviews ACCOUNT_USAGE views (QUERY_HISTORY, WAREHOUSE_METERING_HISTORY, LOGIN_HISTORY) directly in Snowsight — but these views stay inside Snowflake, disconnected from the rest of her organization's operational tooling.

**Current pain:** Maya's observability is fragmented. Snowflake's built-in Snowsight dashboards show query history and warehouse load, but she cannot correlate Snowflake performance data with broader infrastructure alerts in Splunk. When a warehouse shows unexpected credit spikes, she has to manually query ACCOUNT_USAGE, export CSV reports, and paste findings into incident tickets. There is no automated pipeline from Snowflake operational telemetry to the Splunk dashboards her ops team relies on. Cost anomalies go unnoticed for days. Failed task executions are only caught during her morning manual review.

**Success with this app:** Maya installs the app from the Snowflake Marketplace, enables the Performance Pack, configures her Splunk Enterprise HEC endpoint, and within minutes sees QUERY_HISTORY, TASK_HISTORY, and WAREHOUSE_METERING data flowing into Splunk. She builds Splunk alerts for slow queries, warehouse credit spikes, and consecutive task failures. Her morning manual review is replaced by proactive Splunk alerts that fire in real time. Cost reports that used to be manual CSV exports are now live Splunk dashboards.

**What makes her say "this is exactly what I needed":** Zero infrastructure to manage — the app runs inside Snowflake with serverless compute. No DB Connect heavy forwarder, no JDBC drivers, no credential rotation headaches. Just toggle on a Monitoring Pack and data flows.

---

#### Persona 2: Ravi — Site Reliability Engineer (SRE)

**Role:** SRE on a platform engineering team responsible for the reliability of business-critical applications that depend on Snowflake — ML pipelines, real-time analytics APIs, data products built with Snowpark stored procedures and UDFs, and Cortex AI-powered features.

**Day-to-day:** Ravi lives in Splunk Observability Cloud for distributed tracing and Splunk Enterprise for log analysis and alerting. When an application incident occurs, he traces requests end-to-end across microservices using Splunk APM. But the trace breaks at the Snowflake boundary — the stored procedure that runs a critical ML scoring UDF emits spans and logs into a Snowflake Event Table, and Ravi has no visibility into that data from Splunk. He has to context-switch into Snowsight, manually query the Event Table, and try to correlate timestamps across two disconnected systems.

**Current pain:** The Snowflake boundary is a black box. When a Snowpark stored procedure takes 10x longer than expected, Ravi cannot see the distributed trace that shows *why* — was it a slow downstream UDF call, a warehouse queuing bottleneck, or a data skew issue? Event Table telemetry (spans, metrics, logs) stays trapped in Snowflake. Ravi's existing OTel Collector setup can scrape some Snowflake metrics externally, but it cannot access Event Table streams or ACCOUNT_USAGE views natively. The data gaps are unacceptable for production incident response.

**Success with this app:** Ravi's team installs the app, enables the Distributed Tracing Pack, binds their Event Table, and configures the Splunk Observability Cloud OTLP endpoint. Within minutes, Snowflake-emitted spans appear in Splunk APM — stitched into the same traces as the rest of the application. Stored procedure logs flow to Splunk Enterprise via HEC. The Snowflake black box is now transparent. When the next incident hits, Ravi traces end-to-end from the API gateway through Kubernetes services through the Snowflake stored procedure and back — all in one Splunk trace view.

**What makes him say "this is exactly what I needed":** Full distributed traces across the Snowflake boundary, in the same Splunk APM view he already uses. No custom ETL, no external collectors, no data gaps. The "aha" moment: clicking on a slow span in Splunk APM and seeing it is a Snowflake UDF — with the warehouse name, query ID, and execution context right there in the span attributes.

---

### Secondary Users

#### Security / SOC Analyst

Consumes LOGIN_HISTORY, ACCESS_HISTORY, and GRANTS data in Splunk Enterprise for security monitoring — failed login detection, privilege escalation alerting, suspicious access pattern analysis. Does not install or configure the app but benefits from the Security Pack (post-MVP) data flowing into their existing Splunk security dashboards and correlation searches.

#### FinOps / Engineering Manager

Reviews Snowflake cost data (METERING_HISTORY, WAREHOUSE_METERING_HISTORY, STORAGE_USAGE) in Splunk dashboards to track credit consumption trends, identify cost anomalies, and optimize warehouse sizing. Benefits from the Cost Pack (post-MVP). Typically the budget holder who approves the app installation after seeing the value demonstrated by the Admin or SRE.

#### Decision Maker / Approver

The Snowflake ACCOUNTADMIN or IT/Platform Engineering leader who has the privileges to install Marketplace apps and grant the required account-level permissions (EXECUTE TASK, EXECUTE MANAGED TASK, IMPORTED PRIVILEGES ON SNOWFLAKE DB, CREATE EXTERNAL ACCESS INTEGRATION). May be the same person as the Snowflake Administrator (Maya persona) in smaller organizations, or a separate role in enterprises with strict privilege separation. Needs to see clear value justification and understand what privileges the app requires before approving installation.

---

### User Journey

#### Discovery
- **Snowflake Marketplace:** Snowflake customers searching for observability, monitoring, or Splunk integration solutions find the app directly in the Marketplace catalog.
- **Splunk sales / SE recommendation:** Splunk field teams recommend the app to existing Splunk customers who also run Snowflake workloads, positioning it as the native solution for Snowflake observability.
- **GTM activities:** Blog posts, conference announcements (Snowflake Summit, .conf), joint Splunk-Snowflake webinars, and partner marketing drive awareness.

#### Onboarding (First 30 Minutes)
1. **Install** — ACCOUNTADMIN clicks "Get" on the Marketplace listing. The app installs in the customer's Snowflake account regardless of region.
2. **Grant privileges** — The Streamlit UI guides the admin through granting required privileges (EXECUTE TASK, IMPORTED PRIVILEGES ON SNOWFLAKE DB, etc.) using the Python Permission SDK — native Snowsight prompts, no manual SQL.
3. **Configure destinations** — Enter Splunk Observability Cloud realm + access token (for OTLP/gRPC) and/or Splunk Enterprise HEC endpoint + token (for HEC HTTP). Tokens stored as Snowflake Secrets.
4. **Select Monitoring Packs** — Toggle on Distributed Tracing Pack and/or Performance Pack. Each selected ACCOUNT_USAGE source displays its default schedule interval (e.g., QUERY_HISTORY: 30 min) — admin can modify any interval inline before activation. Advanced users can expand packs to deselect individual sources.
5. **Bind Event Table** — For the Distributed Tracing Pack, bind the consumer's Event Table (e.g., SNOWFLAKE.TELEMETRY.EVENTS) via the reference mechanism. The Event Table source displays its default stream polling interval (e.g., 30 seconds) — admin can modify it inline before activation.
6. **Activate** — The app provisions networking (EAI + Network Rule), creates **governed views** over each enabled source (Event Tables AND ACCOUNT_USAGE), applies default masking on high-risk fields (QUERY_TEXT → REDACT), creates streams (Event Table) and independent serverless scheduled tasks (ACCOUNT_USAGE — one task per source). Pipelines start flowing. The **Governance Awareness** panel displays all governed views and their default masking state.

#### Core Usage (Day-to-Day)
- **Maya (Admin):** Monitors Snowflake operational health via Splunk Enterprise dashboards built on Performance Pack data (CIM-normalized QUERY_HISTORY, TASK_HISTORY). Receives proactive alerts on slow queries, task failures. Reviews the app's Pipeline Health Overview tab in Streamlit for export status. Queries the app's operational logs via Snowsight for detailed error diagnostics when needed.
- **Ravi (SRE):** Traces application requests end-to-end through Snowflake in Splunk APM — spans enriched with OTel DB Client semantic conventions (`db.system.name = "snowflake"`, `db.namespace`, `db.operation.name`, `db.stored_procedure.name`) and custom Snowflake attributes (`snowflake.warehouse.name`, `snowflake.query.id`). Investigates stored procedure / UDF performance using Event Table spans and logs in Splunk. Correlates Snowflake-side latency with application-level SLOs.

#### Success Moment ("Aha!")
- **Ravi** sees a Snowflake stored procedure span appear in his Splunk APM trace waterfall for the first time — stitched seamlessly into the same trace as the upstream API call and downstream database query. The Snowflake black box is gone.
- **Maya** receives a Splunk alert at 10:15 AM that warehouse `ANALYTICS_WH` credit consumption spiked 3x in the last hour — before anyone on the analytics team notices. She right-sizes the warehouse before the monthly bill surprises finance.

#### Long-Term Value
- The app becomes invisible infrastructure — always running, always exporting, zero maintenance. Monitoring Packs are toggled on as new observability domains become relevant (Security Pack after a compliance audit, Cost Pack when FinOps matures). Splunk becomes the single pane of glass for Snowflake observability, eliminating the need to context-switch into Snowsight for operational investigations.

---

## Success Metrics

### User Success Metrics

| Metric | Target | Measurement Method |
|---|---|---|
| **Time to first telemetry in Splunk** | < 15 minutes from install to first data visible in Splunk | Measured from Marketplace "Get" click to first span/event appearing in Splunk Observability Cloud or Splunk Enterprise |
| **Manual pipelines eliminated** | Zero manual Snowflake-to-Splunk data pipelines to maintain | Customer self-reported; replaces DB Connect, custom ETL, or OTel Collector scraping setups |
| **MTTR reduction for Snowflake issues** | 50% reduction in Mean Time to Resolution | Customer-reported before/after comparison; enabled by Splunk's deep analytics, AI assistants, and cross-system correlation (Snowflake telemetry correlated with application, service, and infrastructure data) |
| **Observability context-switching eliminated** | Users no longer need to switch between Snowsight and Splunk for incident investigation | Qualitative: SREs can trace end-to-end through Snowflake in Splunk APM without opening Snowsight; Admins receive proactive Splunk alerts instead of morning manual ACCOUNT_USAGE reviews |
| **Export pipeline parity with OTel Collector** | Export latency and reliability at least equal to equivalent OTel Collector-based pipelines | Benchmark: Event Table telemetry delivered to Splunk within comparable latency to an external OTel Collector scraping the same data; pipeline reliability (successful export rate) matches or exceeds OTel Collector baseline |

### Business Objectives

| Objective | Target | Timeframe |
|---|---|---|
| **Marketplace installs** | 5+ active installs on Snowflake Marketplace | First 6 months post-launch |
| **New customer acquisition via Snowflake channel** | At least 1 new Splunk customer acquired through the Snowflake Marketplace | First 12 months post-launch |
| **Snowflake Marketplace Partner — Milestone 1** | Complete all Milestone 1 deliverables to unlock Snowflake marketing support | Within 3 months of Marketplace listing going live |
| **Snowflake Marketplace Partner — Milestone 2** | Complete Milestone 2 to unlock marketing funding and deeper co-marketing | Within 9 months of Marketplace listing going live |

#### Snowflake Marketplace Partner Milestone Details

**Milestone 1 — Partner Deliverables (required before Milestone 2):**
- 1 published content piece addressing how the Marketplace listing adds value for customers (blog post, technical guide, or video)
- 3 Joint Customer Win Wires submitted to Snowflake (must be joint wins; do not need to be publicly referenceable)
- Partner email to database announcing or linking to the live Snowflake Marketplace listing

**Milestone 1 — Snowflake Marketing Support (unlocked):**
- Featured in Snowflake Customer Newsletter
- Marketplace Monday Post on Snowflake Corporate LinkedIn
- Customer Win Wires shared with internal Snowflake sellers
- Logo displayed on Snowflake Marketplace featured section
- Invitation to "Do It Better with Snowflake" YouTube series
- Social post on official Snowflake channels promoting content

**Milestone 2 — Partner Deliverables:**
- 1 publicly referenceable Customer Success Story submitted through the Snowflake Customer Stories Pathway
- 2 additional content pieces addressing key Snowflake priority areas (Cortex, Snowpark Container Services, quantifiable business outcomes, Snowflake's competitive advantage)

**Milestone 2 — Snowflake Marketing Support (unlocked):**
- Access to Snowflake Marketing Funding for up to 1 campaign per Marketplace Listing (up to $5k Snowflake contribution)
- Promotion of Customer Success story on Snowflake LinkedIn and Twitter
- Segment in webinar spotlight series
- Inside the Data Cloud Blog spotlight series

### Key Performance Indicators

#### Pipeline Reliability & Performance KPIs

| KPI | Target | Notes |
|---|---|---|
| **Export success rate** | >= 99.5% of batches exported successfully on first attempt (transport-level retries included) | Measured via `_metrics.pipeline_health` (rows_exported vs rows_collected). Parity with OTel Collector reliability. |
| **Event Table export latency** | < 60 seconds from Event Table write to data visible in Splunk | Stream trigger interval (30s default) + export processing time. Comparable to OTel Collector pipeline latency. |
| **ACCOUNT_USAGE export freshness** | Data in Splunk within 1 polling cycle of Snowflake's inherent view latency | e.g., QUERY_HISTORY (45 min Snowflake latency) available in Splunk within ~75 min of the original query execution |
| **Pipeline uptime** | 99.9% (no more than ~8.7 hours of pipeline downtime per year) | Measured per-source via last successful run timestamp in `_metrics.pipeline_health` |
| **Zero data loss in happy path** | 100% of telemetry rows collected are exported to Splunk when Splunk endpoints are reachable | Stream checkpointing (Section 8.0) and watermark-based tracking ensure exactly-once delivery semantics |

#### Adoption & Engagement KPIs

| KPI | Target | Timeframe |
|---|---|---|
| **Marketplace listing live** | App listed and approved on Snowflake Marketplace | MVP launch milestone |
| **Active installs** | 5+ accounts with active pipelines (at least 1 Monitoring Pack enabled and exporting) | 6 months post-launch |
| **Pack adoption breadth** | Average of 1.5+ Monitoring Packs enabled per active install | 6 months post-launch |
| **Milestone 1 content piece published** | 1 blog post or technical guide promoting the Marketplace listing | Within 1 month of listing going live |
| **Joint Customer Win Wires** | 3 submitted to Snowflake | Within 3 months of listing going live |
| **Publicly referenceable Customer Success Story** | 1 submitted through Snowflake Customer Stories Pathway | Within 9 months of listing going live |

---

## MVP Scope

**Target Ship Date:** 1 month from project start (mid-March 2026)

### Core Features

#### Monitoring Packs (MVP)

| Pack | Sources | Entity Scope | Pipeline | Export Destination |
|---|---|---|---|---|
| **Distributed Tracing Pack** | User-selected Event Tables (spans, metrics, logs) | SQL/Snowpark compute only — stored procedures, UDFs/UDTFs, SQL queries (entity discrimination: `snow.executable.type IN ('procedure','function','query','sql')`) | Event-driven (Governed View → Stream → Serverless Triggered Task) | OTLP/gRPC → Splunk Observability Cloud (spans & metrics with OTel DB Client conventions); HEC HTTP → Splunk Enterprise/Cloud (logs) |
| **Performance Pack** | QUERY_HISTORY, TASK_HISTORY, COMPLETE_TASK_GRAPHS, LOCK_WAIT_HISTORY | N/A | Poll-based (Governed View → Independent Serverless Scheduled Tasks + Watermarks — one task per source) | HEC HTTP → Splunk Enterprise/Cloud (CIM-normalized) |

#### Streamlit Configuration UI

- **Privilege & Reference Binding** — Python Permission SDK (`snowflake-native-apps-permission`) guides the consumer through granting required privileges and binding references via native Snowsight prompts. No manual SQL required.
- **Telemetry Enablement** — Guides user to enable account-level telemetry collection.
- **Observability Target Selection** — Allows the customer to discover and select Event Tables and ACCOUNT_USAGE views available in their environment as observability targets for the app. Supports both default Snowflake telemetry tables (e.g., `SNOWFLAKE.TELEMETRY.EVENTS`) and custom Event Tables. Each selected source displays its **default schedule interval** (e.g., QUERY_HISTORY: 30 min, Event Table stream: 30 sec) with inline modification capability.
- **Monitoring Pack Selection** — Toggle switches for each pack. Advanced users can expand packs to deselect individual sources. Informational banner explains MVP scope: "This release processes **SQL/Snowpark compute telemetry** (SQL queries, stored procedures, UDFs, UDTFs). Telemetry from other Snowflake services (SPCS, Streamlit, Cortex AI) is filtered out. Future releases will add support for additional telemetry categories."
- **Destination Setup** — Splunk Observability Cloud (realm + access token) and Splunk Enterprise/Cloud (HEC endpoint + HEC token). Tokens stored as Snowflake Secrets.
- **Governance Awareness Panel** — Simplified informational panel that highlights the importance of Snowflake-native governance, lists all governed views created by the app and their default masking state (e.g., `governed_query_history` — QUERY_TEXT: REDACT). Includes QUERY_TEXT privacy toggle (REDACT/FULL/CUSTOM). Displays schema change notifications when source Event Table schemas are modified (columns added/removed/renamed) — alerts consumer to re-apply governance policies after automatic view recreation. *(Post-MVP: Full Governance Compliance tab with classification awareness, policy detection, consumer policy enumeration.)*
- **Settings Panel** — All configuration stored in `_internal.config`, adjustable via the Streamlit UI. Performance tuning parameters (`export_batch_size`, `max_batches_per_run`) use hardcoded defaults and are not exposed in the MVP UI.

#### Pipeline Health Dashboard (Streamlit)

- **Overview Tab** (MVP) — Three KPI cards:
  - Total rows collected / exported / failed (last 24h)
  - Current failed batches awaiting retry (transport-level failures within the current run)
  - Pipeline up/down status per source (based on last successful run timestamp)
- **Internal metrics table** (`_metrics.pipeline_health`) — Records per-run operational metrics for all pipeline executions.
- **Stream Staleness Alert** — Prominent warning when `STALE_AFTER` is less than 2 days in the future.
- *(Post-MVP: Volume Estimator, Throughput Tab, Errors & Failures Tab, Volume Estimation Tab, Rate Limits Tab, Streamlit Logging tab with verbosity selector and keyword search.)*

#### Pipelines

- **Governed View Architecture**: Every data source (Event Tables AND ACCOUNT_USAGE views) flows through a custom governed view created by the app. Governed views are the universal data contract — consumers attach Snowflake-native governance policies (masking, row access, projection) to any governed view, and the app automatically honors them at the platform layer.
- **Event-driven pipeline**: Governed Event Table View → Append-only Stream → Serverless Triggered Task → `event_table_collector` stored procedure (entity discrimination filter: SQL/Snowpark compute only) → OTLP/gRPC (spans & metrics with OTel DB Client conventions) + HEC HTTP (logs).
- **Poll-based pipeline**: Governed ACCOUNT_USAGE View → Independent Serverless Scheduled Task (one per enabled source, each with source-specific schedule) → `account_usage_source_collector` stored procedure → HEC HTTP (CIM-normalized). High-watermark state table (`_internal.export_watermarks`) for incremental reads.
- **Stream checkpointing**: Zero-row INSERT offset advancement pattern within explicit transactions.
- **Automatic stream recovery**: Stale Event Table streams are auto-recovered by the app (drop/recreate stream on governed view — data gap recorded in `_metrics.pipeline_health` and app event table).
- **Governed view auto-refresh**: Hourly serverless alert detects Event Table schema changes (columns added/removed/renamed) via MD5 hash fingerprinting. When detected, governed views are recreated (`CREATE OR REPLACE VIEW` — drops policies, breaks streams). Streamlit UI notifies consumer to re-apply governance policies. Stream auto-recovery handles broken streams automatically.

#### Design Decisions Implemented in MVP

| Decision | Implementation |
|---|---|
| **Batching Strategy** (7.1) | Chunked exports with configurable batch sizes via `to_pandas_batches()` |
| **Retry Strategy** (7.2) | Transport-level retries only — OTel SDK built-in retry for gRPC (~6 retries over ~63s); `httpx` + `tenacity` exponential backoff for HEC HTTP on 429/5xx. No application-level failure tracking. |
| **Independent Scheduled Tasks** (7.6) | One standalone serverless task per ACCOUNT_USAGE source with source-specific schedule; inline health metrics recording |
| **Source Prioritization** (7.7) | Priority ordering for Event Table streams; ACCOUNT_USAGE sources prioritized by schedule frequency |
| **Per-Source Polling** (7.8) | Each source task runs at an interval aligned with its Snowflake latency (e.g., 30 min for QUERY_HISTORY, 90 min for ACCESS_HISTORY) |
| **OTLP Transport** (7.9) | OTLP/gRPC exclusively for spans & metrics to Splunk Observability Cloud with OTel DB Client semantic conventions (`db.*`) and custom Snowflake conventions (`snowflake.*`); HEC HTTP for logs and ACCOUNT_USAGE data with CIM normalization |
| **Vectorized Transformations** (7.11) | Snowpark DataFrame filtering + `to_pandas_batches()` chunked processing |
| **Snowpark Best Practices** (7.12) | Push relational work to Snowflake engine; Python for export logic only |
| **Event Table Optimization** (7.13) | Per-signal-type Snowpark projections for efficient Event Table processing; entity discrimination filter applied as first DataFrame operation (pushdown optimization) |
| **Governed View Pattern** (Pattern C) | Custom governed view per source as universal data contract; consumer-attached policies enforced at platform layer |
| **Stream Auto-Recovery** | Automatic stale stream detection and recovery (drop/recreate stream on governed view); data gap recorded in pipeline_health and app event table |
| **Governed View Auto-Refresh** | Hourly serverless alert detects Event Table schema changes via MD5 fingerprinting; automatic recreation when columns added/removed/renamed; Streamlit UI notification for policy re-application |

---

#### Governed View Auto-Refresh Design

**Overview:** The app automatically recreates governed views when their source Event Table schemas change (columns added/removed/renamed). Consumers are notified via Streamlit UI to re-apply governance policies if needed.

**Detection Mechanism:**
- Schema fingerprinting: `hash = MD5(concatenate(column_names ordered by position))`
- Hourly serverless alert compares current hash vs stored hash
- If hashes differ → mark for recreation, call stored procedure

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
  CREATE OR REPLACE VIEW governed_view AS SELECT * FROM source_table
  UPDATE registry SET:
    source_schema_hash = new_hash
    schema_changed = true
```

**Impact of Recreation:**
- Masking policies → DROPPED
- Row access policies → DROPPED  
- Tags → DROPPED
- Streams → BROKEN (existing stream auto-recovery recreates them)

**Consumer Notification (Streamlit UI Governance Awareness Panel):**
```
View: GOVERNED_SNOWFLAKE_TELEMETRY_EVENT_TABLE
Status: ⚠️ Schema changed - view recreated
Action: Re-apply governance policies if needed
```

Status displays only when `schema_changed = true`. Consumer acknowledges notification, which resets flag to false.

**Schema Changes Detected:** Column added, column removed, column renamed. DML operations (data inserts) do NOT trigger recreation.

---

#### App Deployment & Packaging

- Full `manifest.yml` (`manifest_version: 2`) — declares all privileges, references, event definitions (`ERRORS_AND_WARNINGS` mandatory, `DEBUG_LOGS` optional), `log_level: INFO`, `trace_level: ALWAYS`, and default Streamlit app.
- `marketplace.yml` — declares resource requirements for Snowsight consumer readiness validation.
- `setup.sql` — DDL for all internal schemas, procedures, tasks, governed views, and EAI host port specification. Idempotent design: `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ADD COLUMN IF NOT EXISTS`, `CREATE OR ALTER VERSIONED SCHEMA`, `CREATE OR REPLACE TASK`. Event Table governed view uses `ALTER VIEW` only (never `CREATE OR REPLACE VIEW` to protect streams).
- `README.md` — Consumer-facing documentation with setup steps, procedures used, required privileges, governed view architecture, and example SQL.
- `environment.yml` — Pinned Python dependencies from the Snowflake Anaconda Channel (dual runtime: Python 3.11 for Streamlit, Python 3.13 for backend procedures).
- Automated infrastructure provisioning: networking/EAI, governed views, streams, independent scheduled tasks, internal tables — all created programmatically on first setup.
- **App Operational Logging**: Structured logs written to consumer's account-level event table via Native App event definitions. Queryable via Snowsight for pipeline debugging and error analysis.

### Out of Scope for MVP

#### Monitoring Packs (Deferred)
- **Cost Pack** — METERING_HISTORY, WAREHOUSE_METERING_HISTORY, PIPE_USAGE_HISTORY, SERVERLESS_TASK_HISTORY, AUTOMATIC_CLUSTERING_HISTORY, STORAGE_USAGE, DATABASE_STORAGE_USAGE_HISTORY, DATA_TRANSFER_HISTORY, REPLICATION_USAGE_HISTORY, SNOWPARK_CONTAINER_SERVICES_HISTORY, EVENT_USAGE_HISTORY.
- **Security Pack** — LOGIN_HISTORY, ACCESS_HISTORY, SESSIONS, GRANTS_TO_USERS, GRANTS_TO_ROLES, NETWORK_POLICIES.
- **Data Pipeline Pack** — COPY_HISTORY, LOAD_HISTORY, PIPE_USAGE_HISTORY.
- **Cortex AI Pack** — Telemetry from Cortex Services (Cortex AI Functions, Cortex Agents, Cortex Search) via `AI_OBSERVABILITY_EVENTS` table accessed through `GET_AI_OBSERVABILITY_EVENTS()` function. Enriched with OTel `gen_ai.*` semantic conventions for generative AI observability. Aligns with Snowflake's strategic priority areas and Marketplace Partner Milestone 2 content requirements.
- **Openflow Pack** — Event Table telemetry from Openflow pipelines (entity discrimination: `RESOURCE_ATTRIBUTES:"application" = 'openflow'`). Covers Openflow pipeline execution traces, task orchestration, and data flow monitoring.

#### Failure Tracking & Recovery (Deferred to Post-MVP)
- Zero-copy reference-based failure tracking (`_staging.failed_event_batches`, `_staging.failed_account_usage_refs`). **MVP trade-off:** If transport-level retries exhaust, the batch is dropped and the pipeline advances (watermark/stream offset advances). Data gaps occur during sustained Splunk outages.
- Dedicated retry task (`_internal.failed_batch_retrier`).
- Lazy hash computation / natural key extraction — only needed when failure tracking is enabled.
- Automatic cleanup task for failed batch references.
- Configuration settings: `max_retry_attempts`, `failed_batch_retention_days`.
- **MVP mitigation:** Transport-level retries handle transient blips (seconds). Pipeline Health dashboard is early warning system. Failures logged to `_metrics.pipeline_health` and app event table.

#### Rate Limit Handling (Deferred)
- In-app rate limiting — request pacing, adaptive throttling, 429 backoff with Retry-After.
- Rate Limits Dashboard Tab.

#### Exporter Features (Deferred)
- PII redaction / field masking, sampling, attribute/label normalization, content-based routing, advanced load-shedding, complex processor chains.

#### Pipeline Health Dashboard Tabs (Deferred to Post-MVP)
- Throughput Tab, Errors & Failures Tab, Volume Estimation Tab, Rate Limits Tab, Stream health status per Event Table stream.
- **Streamlit Logging Tab** (deferred) — Verbosity selector (`st.pills`: ERROR/WARN/INFO/DEBUG), scrollable log display with keyword search, filters by source/task name and time range. **MVP:** Ops engineer queries app's event table directly via Snowsight for error diagnostics.

#### Advanced Optimizations (Deferred)
- `ThreadPoolExecutor` + `httpx.Client` connection pooling for concurrent HEC exports.
- Vectorized UDFs for hash computation.
- Thread-safe Snowpark sessions for parallelism within procedures.
- OTLP HTTP fallback if gRPC is blocked.

### MVP Success Criteria (Go/No-Go Gates)

The following gates must all be satisfied before the app is published on the Snowflake Marketplace:

#### Functional Gates
- [ ] **E2E user workflows verified** — Install → Configure → Observe cycle works end-to-end in a cross-account test install (via `splunk_observability_test_pkg` internal listing).
- [ ] **Governed view architecture operational** — All sources (Event Tables AND ACCOUNT_USAGE) flow through custom governed views; consumer-attached policies are honored.
- [ ] **Distributed Tracing Pack operational** — Event Table spans (OTel DB Client conventions) appear in Splunk Observability Cloud APM; Event Table logs appear in Splunk Enterprise/Cloud via HEC. Entity discrimination filter (SQL/Snowpark compute only) verified.
- [ ] **Performance Pack operational** — QUERY_HISTORY, TASK_HISTORY, COMPLETE_TASK_GRAPHS, LOCK_WAIT_HISTORY data (CIM-normalized) flowing to Splunk Enterprise/Cloud via HEC. QUERY_TEXT masked by default (REDACT mode).
- [ ] **Streamlit UI complete** — Privilege binding, observability target selection with per-source schedule interval display/modification, pack configuration, destination setup, Governance Awareness panel with schema change notifications, and Pipeline Health Overview Tab all functional.
- [ ] **App operational logging functional** — Structured logs written to consumer's event table; queryable via Snowsight for error diagnostics.
- [ ] **Stream auto-recovery verified** — Stale Event Table stream detection and automatic recovery (drop/recreate stream on governed view) works; data gap recorded.
- [ ] **Governed view auto-refresh operational** — Event Table schema change detection (MD5 fingerprinting) works; governed views recreate automatically when source schema changes; Streamlit UI displays schema change notifications; stream auto-recovery handles broken streams.

#### Performance Gates
- [ ] **Export latency parity with OTel Collector** — Event Table export latency is similar to or less than equivalent OTel Collector-based pipelines (target: < 60 seconds from Event Table write to data visible in Splunk).
- [ ] **Pipeline reliability** — Export success rate >= 99.5% of batches on first attempt (transport-level retries included).

#### Quality Gates
- [ ] **No P1/P2 bugs** — Zero Priority 1 or Priority 2 defects open at time of Marketplace submission.
- [ ] **No critical/high CVEs** — All dependencies CVE-free at Critical/High severity. `protobuf >= 6.33.5` verified on Snowflake Anaconda Channel.

#### Marketplace Compliance Gates
- [ ] **Security scan APPROVED** — Automated security scan status is `APPROVED` for the version being published.
- [ ] **Immediate utility** — App is operational after install; Streamlit UI guides setup; README documents all consumer steps.
- [ ] **Standalone** — Core experience delivered on Snowflake; external services accessed through Snowflake EAI + Secrets only.
- [ ] **Data-centric** — App leverages Snowflake-native data (ACCOUNT_USAGE views, Event Tables).
- [ ] **Transparent & secure** — All privileges and references in `manifest.yml`; all resources in `marketplace.yml`; privileges requested via Python Permission SDK. No plaintext secrets. SQL injection prevention via bound parameters.
- [ ] **README complete** — Describes app functionality, consumer setup steps, stored procedures/UDFs, required privileges, and example SQL as code blocks.
- [ ] **No typos** — Listing text, README, and Streamlit UI reviewed for errors.
- [ ] **Event sharing configured** — `SNOWFLAKE$ERRORS_AND_WARNINGS` (mandatory) and `SNOWFLAKE$USAGE_LOGS`, `SNOWFLAKE$TRACES` (optional, via Permission SDK) declared in manifest.

### Future Vision

#### Post-MVP Pack Roadmap
1. **Cost Pack** (v1.1) — METERING_HISTORY, WAREHOUSE_METERING_HISTORY, PIPE_USAGE_HISTORY, SERVERLESS_TASK_HISTORY, AUTOMATIC_CLUSTERING_HISTORY, STORAGE_USAGE, DATABASE_STORAGE_USAGE_HISTORY, DATA_TRANSFER_HISTORY, REPLICATION_USAGE_HISTORY, SNOWPARK_CONTAINER_SERVICES_HISTORY, EVENT_USAGE_HISTORY. Enables the FinOps persona and unlocks Snowflake Marketplace Partner Milestone content on quantifiable business outcomes.
2. **Security Pack** (v1.2) — LOGIN_HISTORY, ACCESS_HISTORY, SESSIONS, GRANTS_TO_USERS, GRANTS_TO_ROLES, NETWORK_POLICIES. Failed login alerting, access auditing, privilege drift detection. Serves the Security/SOC Analyst persona and strengthens the Splunk-as-SIEM narrative for Snowflake environments.
3. **Data Pipeline Pack** (v1.3) — COPY_HISTORY, LOAD_HISTORY, PIPE_USAGE_HISTORY. Ingestion failure detection, pipeline throughput monitoring. Completes the operational observability picture.

#### Platform Evolution (6-12 Months)
- **Zero-copy failure tracking** — Reference-based architecture for persistent failure recovery with dedicated retry task and automatic cleanup. Elevates pipeline reliability from 99.5% to 99.99%+ for sustained Splunk outages. Closes the MVP data gap trade-off.
- **Full Governance Compliance tab** — Classification awareness (queries `TAG_REFERENCES`, `DATA_CLASSIFICATION_LATEST`), policy detection (queries `POLICY_REFERENCES`), consumer policy enumeration. Replaces the simplified Governance Awareness panel.
- **Streamlit Logging tab** — Verbosity selector, scrollable log display with keyword search, filters by source/task name and time range. Replaces Snowsight-based log queries.
- **Volume estimator** — Projects expected daily/monthly throughput during initial setup. Re-runnable on demand from the Streamlit UI.
- **Advanced Pipeline Health Dashboard** — Throughput Tab, Errors & Failures Tab, Volume Estimation Tab, Rate Limits Tab, and per-stream health monitoring.
- **In-app rate limiting** — Token-bucket rate limiter, Retry-After header parsing, adaptive throttling.
- **Performance optimizations** — `ThreadPoolExecutor` for concurrent HEC exports, vectorized UDFs for hash computation.

#### Long-Term Vision (12-24 Months)
- **Additional Event Table service categories** — SPCS (`snow.executable.type = 'spcs'`), Streamlit (`snow.executable.type = 'streamlit'`), Openflow (`RESOURCE_ATTRIBUTES:"application" = 'openflow'`) telemetry via service category registry and convention-specific enrichers. Expands beyond SQL/Snowpark compute scope.
- **Cortex AI Pack** — Dedicated pack for Cortex Services telemetry via `AI_OBSERVABILITY_EVENTS` table (accessed through `GET_AI_OBSERVABILITY_EVENTS()` function), enriched with OTel `gen_ai.*` semantic conventions. Purpose-built observability for Cortex AI Functions, Cortex Agents, and Cortex Search — aligns with Snowflake's strategic priority areas and Marketplace Partner Milestone 2 content requirements.
- **Openflow Pack** — Dedicated pack for Openflow pipeline telemetry from Event Tables (entity discrimination: `RESOURCE_ATTRIBUTES:"application" = 'openflow'`). Covers Openflow pipeline execution traces, task orchestration, and data flow monitoring.
- **Bi-directional integration** — Splunk alerting triggers Snowflake actions (warehouse scaling, task restarts) via reverse integration.
- **Multi-tenant scale** — Proven at 100+ concurrent installs with diverse warehouse topologies and telemetry volumes.
