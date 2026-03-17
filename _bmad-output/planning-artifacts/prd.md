---
workflowType: 'prd'
workflow: 'edit'
stepsCompleted: [step-e-01-discovery, step-e-02-review, step-e-03-edit]
status: complete
inputDocuments:
  - _bmad-output/planning-artifacts/product-brief.md
  - _bmad-output/planning-artifacts/ux-design-specification.md
  - _bmad-output/planning-artifacts/splunk_snowflake_native_app_vision.md
  - _bmad-output/planning-artifacts/streamlit_component_compatibility_snowflake.csv
  - _bmad-output/planning-artifacts/snowflake_data_governance_privacy_features.md
  - _bmad-output/planning-artifacts/event_table_streams_governance_research.md
  - _bmad-output/planning-artifacts/otel_semantic_conventions_snowflake_research.md
  - _bmad-output/planning-artifacts/event_table_entity_discrimination_strategy.md
  - _bmad-output/planning-artifacts/prd-validation-report.md
  - _bmad-output/planning-artifacts/Native_App_Approval_Process_Guide.md
documentCounts:
  briefs: 1
  research: 4
  projectDocs: 7
  projectContext: 0
classification:
  projectType: saas_b2b (Snowflake Native App)
  domain: Cloud Infrastructure / Observability
  complexity: high
  projectContext: greenfield
date: 2026-02-15
lastEdited: 2026-03-15
editHistory:
  - date: 2026-03-15
    changes: "Aligned PRD to validation findings, added Tom persona, normalized scope/journeys/requirements, and prepared Product Brief sync."
---

# Product Requirements Document - snowflake-native-splunk-app

**Author:** Nikita Voitov (Cisco)
**Date:** 2026-02-15

## Executive Summary

**Splunk Observability for Snowflake** is a Snowflake Native App delivered through the Snowflake Marketplace that brings Snowflake telemetry into Splunk without requiring customers to stand up separate collection infrastructure. The MVP focuses on two capabilities: a **Distributed Tracing Pack** for Snowflake Event Table telemetry relevant to SQL and Snowpark compute, and a **Performance Pack** for selected `ACCOUNT_USAGE` telemetry, so teams can investigate Snowflake behavior inside the same Splunk workflows they already use for application and platform operations.

**Product Differentiator:** The product does not invent a new telemetry protocol. It provides a better operating model: installation, configuration, and core execution stay on Snowflake; customers can export from either governed custom sources or default Snowflake sources; and the app makes governance implications explicit when default sources are chosen. This reduces operational toil, shortens time to first telemetry, and keeps the experience aligned with Snowflake Marketplace approval expectations.

**Target Users:** **Maya** (Snowflake Administrator) activates the app and manages source selection, **Ravi** (SRE) uses exported telemetry to troubleshoot Snowflake-related incidents inside Splunk, **Sam** (DevOps / Operations Engineer) monitors pipeline health and diagnoses failures, and **Tom** (Security & Compliance / Marketplace Approval lead) validates release readiness, governance posture, and Marketplace approval readiness.

**MVP Scope:** Deliver first-value telemetry quickly, keep the core product experience on Snowflake, preserve Splunk relevance for traces and operational events, and make governance and approval constraints explicit rather than implicit.

**Architecture Note:** MVP remains constrained by Snowflake Native App and Marketplace rules: the core experience stays in Snowflake, Event Table and `ACCOUNT_USAGE` remain the primary source families, and exported telemetry must stay compatible with Splunk through an OTLP-capable delivery path.

## Success Criteria

### User Outcomes

| Outcome | Target | Measurement Method |
|---|---|---|
| **Time to first telemetry** | `< 15 minutes` from Marketplace install to first data visible in Splunk | End-to-end install-to-first-data validation |
| **No manual Snowflake-to-Splunk pipeline for MVP use cases** | Replaces DB Connect, custom ETL, or collector-only work for MVP tracing and performance use cases | Customer before/after comparison |
| **Faster incident resolution** | `50%` reduction in MTTR for Snowflake-related incidents | Incident comparison for teams using the app |
| **Unified investigation flow** | Snowflake context is visible inside Splunk alongside application and infrastructure signals | Validated through traced incident scenarios |

### Business Outcomes

These remain business and GTM outcomes, not user journeys.

| Outcome | Target | Timeframe | Measurement Method |
|---|---|---|---|
| **Marketplace listing live** | App listed and approved on Snowflake Marketplace | MVP launch | Review Marketplace listing status and Snowflake approval record |
| **Active installs** | `5+` accounts with active pipelines | 6 months post-launch | Count consumer accounts with at least one enabled source and one successful pipeline run in the trailing 30 days |
| **New customer acquisition** | At least `1` new Splunk customer via Snowflake Marketplace | 12 months post-launch | Review Marketplace-attributed closed-won account records |
| **Marketplace partner milestones** | Milestone 1 and Milestone 2 deliverables completed | 3 months and 9 months post-listing | Verify milestone acceptance against the Snowflake partner program checklist |

### Technical Outcomes

| Outcome | Target | Measurement Method |
|---|---|---|
| **Export success rate** | `>= 99.5%` successful batches | Pipeline health telemetry |
| **Event Table export latency** | `< 60 seconds` from write to visibility in Splunk | End-to-end benchmark |
| **`ACCOUNT_USAGE` freshness** | Within one polling cycle of the source's inherent latency | Source-to-Splunk validation |
| **Pipeline uptime** | `99.9%` per enabled source | Uptime tracking |
| **Happy-path completeness** | `100%` of rows exported when the destination is reachable | Reconciliation checks |
| **Collector-path parity** | Latency and reliability at least equal to a comparable collector-based export path | Benchmark report from a side-by-side comparison against a comparable collector-based export path |

`Collector-path parity` is a technical benchmark validated by benchmark evidence and is not treated as a standalone user journey outcome.

### Release Readiness & Quality Gates

These gates trace to **Tom** and define when the MVP is approval-ready.

| Gate | Target | Measurement Method |
|---|---|---|
| **Automated security review** | `APPROVED` on the submitted version | Snowflake security review status |
| **Functional review readiness** | Reviewer can install, configure, and use the app from a separate consumer account without setup or privilege blockers | External consumer-account dry run |
| **On-Snowflake core experience** | Majority of setup, configuration, and core functionality remains on Snowflake | Release checklist against Marketplace approval guidance |
| **Release quality** | `0` open P1/P2 defects at submission | Defect review |
| **Dependency hygiene** | `0` critical/high CVEs at submission | Dependency audit |
| **Reviewer enablement** | README, test steps, sample data, and any required test credentials are complete and usable | Submission readiness checklist |

### Measurable Outcomes

**3-Month Outcomes (MVP Launch):**

| Outcome | Target | Measurement Method |
|---|---|---|
| Marketplace launch | App live on Snowflake Marketplace with an approved security review | Review listing status and Snowflake approval record |
| MVP pack readiness | Distributed Tracing Pack and Performance Pack operational in consumer-account testing | Review consumer-account test report |
| Workflow validation | End-to-end install, approval, configuration, and export workflows verified in a separate consumer-style account | Review external validation checklist |
| Partner milestone content | Marketplace Partner Milestone 1 content piece published | Review published partner-marketing asset |

**6-Month Outcomes:**

| Outcome | Target | Measurement Method |
|---|---|---|
| Active installs | `5+` installs with at least one Monitoring Pack enabled | Review active-pipeline account counts |
| Joint wins | `3` Joint Customer Win Wires submitted to Snowflake | Count submitted win-wire records |
| Competitive benchmark | Export latency benchmarked and documented against a comparable collector-based export path | Review published benchmark report from a side-by-side comparison |

**12-Month Outcomes:**

| Outcome | Target | Measurement Method |
|---|---|---|
| New customer acquisition | At least `1` new Splunk customer acquired through the Marketplace channel | Review Marketplace-attributed closed-won account records |
| Customer story | Publicly referenceable Customer Success Story submitted | Review approved customer-story submission |
| Post-MVP expansion | Post-MVP packs such as Cost or Security in development or released | Review product roadmap approval or released pack record |

## Product Scope

### MVP — Minimum Viable Product

**Target Ship Date:** Mid-March 2026 (1 month)

**Core Deliverables:**
1. **Distributed Tracing Pack** — Export Snowflake Event Table telemetry relevant to SQL and Snowpark compute so Snowflake work can appear in Splunk investigations.
2. **Performance Pack** — Export selected `ACCOUNT_USAGE` telemetry for query, task, and lock visibility in Splunk.
3. **Source selection with governance clarity** — Let admins enable sources, choose either governed custom sources or default Snowflake sources, and understand the implications of each choice.
4. **In-Snowflake configuration and activation** — Support install, approval, destination setup, source activation, and first-data validation from inside Snowflake.
5. **Operational visibility** — Expose enough health and logging evidence for teams to monitor export health and troubleshoot failures.
6. **Marketplace readiness** — Ship the packaging, documentation, testing evidence, and approval readiness needed for Snowflake security and functional review.

**MVP Go/No-Go Gates:**
- **Functional:** End-to-end install, approval, configuration, activation, export, governance disclosure, and pipeline monitoring workflows succeed in a separate consumer-style account.
- **Performance:** Event Table and `ACCOUNT_USAGE` telemetry meet the latency and reliability targets defined in Success Criteria.
- **Quality:** Tom confirms zero open P1/P2 defects and zero critical/high dependency CVEs at submission time.
- **Marketplace Compliance:** Tom confirms the submitted version satisfies Snowflake security review, enforced standards, and reviewer-readiness requirements.

### Out of Scope for MVP

- Cost, Security, Data Pipeline, Openflow, and Cortex AI packs
- Event Table telemetry outside MVP SQL and Snowpark compute scope, including SPCS and Streamlit service categories
- In-app governance authoring, policy management, or an app-owned masking or classification engine
- In-app log console, advanced governance intelligence, and volume estimation
- Durable replay and zero-copy recovery for prolonged destination outages
- A primary setup or control-plane experience that depends on leaving Snowflake
- Direct destination families beyond the OTLP-compatible export path used for Splunk-aligned delivery

### Growth & Vision (Post-MVP)

*Detailed phased roadmap with priorities and dependencies is documented in [Project Scoping & Phased Development](#project-scoping--phased-development).*

**Phase 2 — Growth:** Richer governance visibility, in-app log exploration, volume estimation, Cost Pack, Security Pack, Data Pipeline Pack, zero-copy failure tracking, and deeper operational reporting.

**Phase 3 — Expansion:** Additional Event Table service categories, Openflow Pack, Cortex AI Pack, broader integration patterns, and scale validation for larger install counts.

**Architecture Note:** The app does not create or manage governed views; consumers decide whether to use custom governed sources or default Snowflake sources. MVP deliberately preserves two source families and one interoperability boundary: Event Table for tracing-oriented telemetry, `ACCOUNT_USAGE` for performance-oriented telemetry, and OTLP-compatible export into Splunk-aligned downstream flows.

**UX Note:** Narrative sections describe the outcomes users achieve. Detailed page structure, widgets, and interaction patterns belong in the UX specification.

## User Journeys

### Journey 1: Maya Activates the App and Reaches First Value

**Persona:** Maya — Snowflake Administrator responsible for setup, source selection, and governance choices.

1. Maya installs the app from the Snowflake Marketplace and completes the required approvals — including granting the app access to a warehouse for query execution — inside Snowflake.
2. She configures the Splunk destination, enables the MVP packs she needs, and selects either governed custom sources or default Snowflake sources for each enabled feed.
3. The app makes the governance tradeoff explicit: default sources are fast to activate, while custom sources are how her organization applies masking or row-level controls.
4. Maya confirms first telemetry in Splunk and hands the resulting operational views to the teams that depend on them.

**Outcome:** Snowflake telemetry becomes usable in Splunk within the onboarding window, without Maya building or operating a separate export pipeline.

**UX Note:** Onboarding should emphasize approval (privileges and warehouse), destination setup, source choice, governance clarity, and first-value confirmation.

---

### Journey 2: Ravi Traces an Incident Through the Snowflake Boundary

**Persona:** Ravi — SRE responsible for debugging business-critical systems that depend on Snowflake.

1. Ravi investigates a slow or failing service in Splunk and follows the trace into the Snowflake portion of the request path.
2. He uses the exported Snowflake context to identify the slow query, stored procedure, or warehouse-related bottleneck without switching to a separate manual telemetry workflow.
3. He confirms the cause, routes remediation to the right owner, and closes the incident faster.

**Outcome:** Snowflake is no longer a blind spot in end-to-end investigations; the same Splunk workflow covers both application and Snowflake context.

**Architecture Note:** MVP Event Table coverage is intentionally limited to SQL and Snowpark compute telemetry that supports this tracing use case.

---

### Journey 3: Sam Monitors Health and Handles Failure States

**Persona:** Sam — DevOps / Operations Engineer responsible for day-to-day pipeline reliability.

1. Sam reviews app health to see whether enabled sources are current and whether the destination is healthy.
2. When exports slow down or fail, he distinguishes between source freshness issues, destination problems, and recoverable pipeline incidents.
3. He uses Snowflake-native operational evidence to troubleshoot the issue, document any resulting data gap, and restore confidence in the export path.

**Outcome:** Operational issues become visible early, and the team can explain whether telemetry is delayed, partially missing, or fully healthy.

---

### Journey 4: Maya Governs Sensitive Data and Owns Source Boundaries

**Persona:** Maya — Snowflake Administrator responsible for governance choices on exported telemetry.

1. Maya reviews which enabled sources can rely on default Snowflake access and which require consumer-governed custom sources.
2. Her team applies masking, row access, or projection policies to custom sources when sensitive fields or rows must be controlled before export.
3. When an underlying source schema changes, Maya updates the custom source her team owns and accepts any operational implications of that change.

**Outcome:** Governance stays in Snowflake, source ownership stays with the consumer, and the app does not become a second policy engine.

**Architecture Note:** The app never creates, refreshes, or repairs consumer-owned governance objects. It reads from the selected source and reports the consequences of that choice.

---

### Journey 5: Maya Upgrades the App Without Re-Starting from Scratch

**Persona:** Maya — Snowflake Administrator responsible for ongoing version adoption.

1. Maya receives a new version through the consumer's Snowflake maintenance policy.
2. The app upgrades without forcing her to re-enter configuration, rebuild source choices, or lose pipeline health history.
3. She confirms that upgraded workflows are available and that telemetry collection resumes with expected continuity.

**Outcome:** Version adoption is operationally safe and low-friction for Maya.

---

### Journey 6: Tom Clears Security, Compliance, and Marketplace Approval

**Persona:** Tom — Security & Compliance / Marketplace Approval lead responsible for release readiness.

1. Tom verifies that the core setup, configuration, and user experience remain on Snowflake and that the app's requested privileges match its actual behavior.
2. He confirms the release passes a separate consumer-account install and configuration test, with complete README guidance, reviewer steps, and any required test data or credentials ready for functional review.
3. He reviews governance messaging for default versus custom sources, ensures known quality and security gates are green, and only then submits the release for Marketplace approval.

**Outcome:** Marketplace approval readiness is treated as a first-class product workflow, not a last-minute packaging task.

**Architecture Note:** This journey is the explicit trace path for the security scan, functional review readiness, zero P1/P2 bug gate, critical/high CVE gate, and published collector-path benchmark used in release validation. Business growth targets remain non-journey outcomes.

---

### Journey Requirements Summary

| Journey | Key Capabilities Required |
|---|---|
| **Maya First Value** | Marketplace install, privilege approval, warehouse binding, destination setup, source selection, governance review, activation, first-value confirmation |
| **Ravi Incident Investigation** | Event Table export for SQL/Snowpark compute, Splunk-compatible context enrichment, preserved source attributes, searchable Snowflake spans in Splunk |
| **Sam Health & Recovery** | Destination health visibility, source freshness visibility, per-source inspection, structured operational logs, retry behavior, data gap reporting, automatic recovery signals |
| **Maya Governance & Source Ownership** | Custom-source selection, governance disclosure, policy-respecting export behavior, user-owned source maintenance guidance |
| **Maya Upgrade Continuity** | Upgrade continuity, preserved configuration and progress, upgrade event visibility |
| **Tom Release Readiness** | Security review readiness, functional review readiness, enforced standards compliance, reviewer enablement, submission go/no-go authority |

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
| **App Admin** | `app_admin` | Full access to all app capabilities: configuration, pack management, destination setup, data governance, observability health, logging tab | A Snowflake administrator who installs a Marketplace app is inherently a privileged user. Adding viewer/operator roles adds complexity without clear value for MVP — Maya can share observability dashboards via Splunk instead. |

**Privilege binding (via Python Permission SDK):**

| Privilege | Purpose | Binding Method |
|---|---|---|
| `IMPORTED PRIVILEGES ON SNOWFLAKE DB` | Access to ACCOUNT_USAGE views | Permission SDK → Snowsight grant prompt |
| `EXECUTE TASK` | Run serverless tasks | Permission SDK → Snowsight grant prompt |
| `EXECUTE MANAGED TASK` | Serverless task compute | Permission SDK → Snowsight grant prompt |
| `CREATE EXTERNAL ACCESS INTEGRATION` | Outbound networking to Splunk endpoints | Permission SDK → Snowsight grant prompt |

**Warehouse binding (via manifest reference + Permission SDK):**

| Reference | Purpose | Binding Method |
|---|---|---|
| `CONSUMER_WAREHOUSE` (WAREHOUSE, USAGE + OPERATE) | Query execution for Streamlit UI, tasks, and stored procedures | Permission SDK → Snowsight warehouse picker (consumer selects an existing warehouse). Callback stores binding via `SYSTEM$SET_REFERENCE` and sets `QUERY_WAREHOUSE` on the Streamlit object via `ALTER STREAMLIT`. |

**Warehouse binding constraint:** Snowflake docs explicitly state that `reference()` is **not supported** for Streamlit `QUERY_WAREHOUSE`. Tasks can use `WAREHOUSE = reference('consumer_warehouse')`, but the Streamlit object requires `ALTER STREAMLIT ... SET QUERY_WAREHOUSE = <warehouse_name>`. The register callback handles both paths: it binds the reference for tasks and also runs `ALTER STREAMLIT` to set the warehouse on the Streamlit object.

**Stored procedure execution model:**

| Context | Execution Model | Implication |
|---|---|---|
| Pipeline collectors (ACCOUNT_USAGE, Event Table) | `EXECUTE AS OWNER` (owner's rights) | Procedures run with app's privileges, not caller's. Policies on the selected custom source are enforced by Snowflake at the platform layer, so the owner role sees the governed result (safe default). |
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

#### 2.1 Snowflake Marketplace Compliance & Release Readiness

This subsection is the canonical source for release constraints, approval mechanics, and Marketplace submission gates.

| Requirement | Canonical Constraint / Decision |
|---|---|
| **Security review gate** | Every release candidate must pass Snowflake's security review before Marketplace submission. If the automated scan is rejected, findings must be resolved and any required manual review completed before the version can proceed. |
| **Functional review gate** | Only a security-approved application package or version may be attached to the Marketplace listing and submitted via **Submit for approval**. Marketplace Operations then validates installation, configuration, and end-to-end functionality from a new-consumer perspective. |
| **Manifest and app-spec compliance** | `manifest.yml` uses `manifest_version: 2` and explicitly declares all required privileges. Any External Access Integration or other app-spec request must be surfaced through Snowflake's native consumer approval flow during install or upgrade. |
| **Enforced build standards** | `setup.sql` must remain idempotent, shared content must avoid blocked functions, `DISTRIBUTION = EXTERNAL` must be set for Marketplace distribution, and the Streamlit UI must comply with Snowflake CSP restrictions. |
| **Submission evidence** | Before submission, the candidate must be validated end-to-end in a consumer-style account, including install or upgrade flow, privilege approval flow, source selection, Event Table and/or `ACCOUNT_USAGE` pipeline execution, and OTLP export to Splunk. Reviewer credentials, sample data, and configuration steps must be prepared if functional review requires them. |
| **Release-readiness owner** | **Tom is the owner of release readiness and approval submission.** Tom owns the go or no-go decision for `Submit for approval`, confirms the approved package or version, verifies enforced-standard checks, ensures listing metadata and contact details are current, and confirms the reviewer handoff material is complete. |
| **Rejected review path** | If security review or functional review is rejected, the team must fix the issues in a new version or patch, re-run the required review gates, update the release directive to the approved version, and resubmit the listing. |
| **Secret handling** | OTLP access tokens, certificates, and related connection material must be stored in Snowflake-approved secret mechanisms. No hardcoded credentials are permitted in app code, sample content, or listing artifacts. |

#### 2.2 Data Privacy & Governance — User-Selected Source Model

The app does not create, manage, refresh, or recreate governed views. Governance is enforced at the Snowflake platform layer on the **user-selected source**.

| Source Type | What the App Supports | Governance Responsibility |
|---|---|---|
| **Custom source** | The consumer selects their own custom view over a supported Snowflake source, such as an `ACCOUNT_USAGE` view or Event Table. The app creates streams and tasks only against that selected source. | The consumer owns masking, row access, projection, tagging, and schema maintenance on the custom source. |
| **Default source** | The consumer selects the default Snowflake source directly, such as `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` or `SNOWFLAKE.TELEMETRY.EVENTS`. | The app reads the default source as exposed by Snowflake and displays explicit governance guidance that policy enforcement requires a consumer-created custom source when the default source cannot carry the needed controls. |
| **App-managed objects** | The app manages only its own operational objects: streams on the selected source, tasks, internal state tables, secrets, EAI objects, and OTLP export configuration. | The app never creates or alters consumer governance objects. |

**Blocked context-function constraint:** In Native App shared content and `EXECUTE AS OWNER` procedures, `IS_ROLE_IN_SESSION()`, `CURRENT_ROLE()`, and `CURRENT_USER()` may evaluate to `NULL`. Consumers must validate that masking and row-access logic on their custom source behaves correctly under that execution model. The app relies on Snowflake to enforce the resulting policy outcome; it does not replicate governance logic.

#### 2.3 QUERY_TEXT Privacy (ACCOUNT_USAGE)

`QUERY_TEXT` remains the highest-risk `ACCOUNT_USAGE` field because SQL text may contain literal PII, secrets, or business-sensitive values. The app never applies masking itself and never creates a governed view. For `QUERY_HISTORY` and similar exports, the supported patterns are:

- **Custom source:** the consumer selects a custom view that masks, excludes, or otherwise governs `QUERY_TEXT` before export.
- **Default source:** the consumer selects the default `ACCOUNT_USAGE` view and explicitly accepts that the app exports what Snowflake exposes. The Data governance page must state that governance controls for `QUERY_TEXT` require selecting a custom source.

#### 2.4 Event Table Span / Log Attribute Privacy

Event Table fields such as `RECORD`, `RECORD_ATTRIBUTES`, and `VALUE` may contain application-level PII or other sensitive payloads. Masking cannot be attached directly to the Event Table itself, so the supported patterns are:

- **Custom source:** the consumer selects a custom view over the Event Table with any required masking, projection, or row filtering already applied by Snowflake.
- **Default source:** the consumer selects the Event Table directly for low-latency streaming, with explicit Data governance guidance that value-level redaction requires a consumer-created custom source.

The app may create an append-only stream on the selected source and export via OTLP, but it never creates, refreshes, or re-applies governance views or policies on the consumer's behalf.

### 3. Technical Constraints

#### 3.1 User-Selected Sources

The app **does not create or maintain governed views**. For each data source, the **user selects** the telemetry source: either their **own custom view** (with masking/row access policies) or the **default** view/event table. This is the uniform data access pattern:

| Pipeline | Data Path | User Responsibility |
|---|---|---|
| **Event Table (event-driven)** | User selects: **custom view** or **event table** → Stream (APPEND_ONLY on selected source) → Triggered Task → OTLP | If user selects a custom view, they attach RAP + masking (masking is blocked on event tables directly). If user selects event table, Data governance page informs that masking can't be applied. |
| **ACCOUNT_USAGE (poll-based)** | User selects: **custom view** or **default ACCOUNT_USAGE view** → Independent Scheduled Task (watermark) → Splunk | If user selects custom view, they attach RAP + masking + projection. If user selects default view, panel informs that policies can't be applied; user must create custom view for governance. |

**When user uses their own view + stream (Event Table):** `CREATE OR REPLACE VIEW` on the user's view **breaks all streams** on it — offset is lost. Consumer documentation explains that policy changes should use `ALTER VIEW`; if they recreate the view, the app's stream staleness recovery (drop/recreate stream) will run with a data gap. The app never creates or alters the user's view.

**Event Table schema changes:** If the user's view is the source and the underlying Event Table schema changes, the **user** is responsible for updating their view. The app does not implement custom-source auto-refresh or any app-managed source registry.

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
| **Warehouse binding** | Consumer warehouse reference (`CONSUMER_WAREHOUSE`) in manifest.yml | Consumer selects an existing warehouse during install; used for Streamlit UI queries, tasks, and stored procedures. No `CREATE WAREHOUSE` privilege needed. |
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

#### 5.1 Stream Breakage — Consumer-Selected Event Table Custom Source

| Risk | Severity | Mitigation |
|---|---|---|
| `CREATE OR REPLACE VIEW` on a consumer-selected custom source over the Event Table breaks all streams on that source (offset lost, unrecoverable) | **CRITICAL** | Consumer guidance requires `ALTER VIEW` for compatible changes. The app never creates or alters the consumer's custom source. If the stream becomes stale or broken, the app recreates the stream on the selected source, records the resulting data gap, and surfaces the incident in pipeline health. |
| First stream creation enables change tracking on the underlying Event Table and may create a one-time operational lock or overhead event | **MEDIUM** | Schedule initial enablement during a low-activity window and document the one-time operational effect in setup guidance. |
| Consumer selects a secure custom source over the Event Table, reducing effective stream retention and increasing staleness risk | **MEDIUM** | Recommend a non-secure custom source unless secure-view semantics are explicitly required. If a secure custom source is used, document the shorter retention and higher staleness risk. |

#### 5.2 Stream Staleness

| Risk | Severity | Mitigation |
|---|---|---|
| Default Event Table staleness window (~14 days) | **MEDIUM** | Set `MAX_DATA_EXTENSION_TIME_IN_DAYS = 90` on user-created Event Tables during setup. For default Event Table (`SNOWFLAKE.TELEMETRY.EVENTS`), consume stream frequently (triggered task with 30s minimum interval). |
| Task suspension longer than staleness window | **LOW** | **Automatic recovery:** The app detects the stale stream at task execution, drops and recreates the stream on the **selected source** (user's view or event table), records the data gap in `_metrics.pipeline_health`, and logs the recovery event to the app's event table. No manual user action required. The design assumes task suspension > 14 days is an exceptional edge case. |

#### 5.3 Marketplace Approval / Release Readiness

| Risk | Severity | Mitigation |
|---|---|---|
| Release candidate fails Snowflake security review | **HIGH** | **Tom owns release readiness.** No version is submitted until the candidate has passed the required security gate and all enforced-standard checks are green: `manifest_version: 2`, explicit privilege declarations, required app-spec approval flow, idempotent `setup.sql`, blocked-function compliance, `DISTRIBUTION = EXTERNAL`, and approved secret handling. |
| Marketplace Operations functional review fails due to install, configuration, or reviewer-handoff gaps | **HIGH** | Tom owns the submission bundle: security-approved package or version, consumer-style install or upgrade test evidence, reviewer credentials or sample data if needed, accurate Marketplace contacts, and clear instructions for configuring Event Table and `ACCOUNT_USAGE` sources and OTLP destinations before `Submit for approval`. |
| Review rejection delays launch | **MEDIUM** | Tom coordinates remediation, creates a new version or patch, re-runs the required Snowflake review gates, updates the release directive to the approved version, and resubmits the listing. |

#### 5.4 Data Loss (MVP Trade-off)

| Risk | Severity | Mitigation |
|---|---|---|
| Sustained OTLP endpoint outage causes permanent data gaps (MVP — no failure tracking) | **MEDIUM** | Transport-level retries handle transient blips (seconds). Sustained outages (minutes to hours) create gaps. Observability health page is early warning. Post-MVP: zero-copy failure tracking with reference-based retry will close this gap. |
| OTLP endpoint down | **MEDIUM** | All telemetry export fails. Observability health shows destination error. Retry with exponential backoff. Documented MVP trade-off. |

#### 5.5 Governance Policy Interaction

| Risk | Severity | Mitigation |
|---|---|---|
| Consumer masking or row-access logic depends on `CURRENT_ROLE()`, `CURRENT_USER()`, or `IS_ROLE_IN_SESSION()` and evaluates unexpectedly under Native App owner's-rights execution | **LOW** | Document that these context functions may resolve to `NULL` in shared content and `EXECUTE AS OWNER` procedures. Consumers should validate the `NULL` branch and prefer policy logic that yields the intended export-safe result on their custom source. |
| Consumer uses `CREATE OR REPLACE VIEW` on a selected custom source | **MEDIUM** | Documentation warns that view recreation breaks streams. The app can recreate the stream on the selected source and record any resulting data gap, but it never recreates or repairs the consumer's custom source. |
| Underlying schema changes and the consumer-owned custom source is not updated | **MEDIUM** | The consumer owns schema maintenance for custom sources. The app surfaces source or stream failures and guidance, but it does not auto-refresh, rebuild, or re-apply policies to custom sources. |
| Projection or masking on the custom source removes a field required for enrichment or export | **LOW** | Pipelines must tolerate `NULL` or missing fields where possible, log the impact to `_metrics.pipeline_health`, and document the minimum required fields per source. |
| DML operations trigger false-positive schema change detection | **LOW** | Schema fingerprints are based on structural metadata only; data churn does not trigger custom-source maintenance logic. |

#### 5.6 Innovation-Specific Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Future Snowflake Event Table schema changes break enrichment logic | **LOW** | Defensive parsing — unknown attributes pass through; only known attributes are enriched |
| Serverless compute limits (max concurrent tasks, memory) at high telemetry volume | **MEDIUM** | Document sizing guidance; post-MVP: compute pool option for high-volume accounts |
| Auto-recovery creates silent data gaps user doesn't notice | **LOW** | Data gap window logged to `_metrics.pipeline_health` and app event table; Observability health page shows past incident notes |

## Innovation & Novel Patterns

### Detected Innovation Areas

**1. Governed source selection as the product contract**  
The app treats the customer's chosen source, whether a governed custom source or a default Snowflake source, as the export contract. That keeps governance inside Snowflake instead of recreating policy logic in the app.

**2. Marketplace-native observability bridge**  
The core install, configuration, and execution experience remains on Snowflake, turning a historically external integration pattern into a Marketplace-native product experience.

**3. Convention-transparent export with additive enrichment**  
The app preserves original telemetry context and enriches it only enough to make the data more useful in Splunk.

**4. Scoped Event Table use rather than generic ingestion**  
MVP intentionally focuses on Event Table telemetry relevant to SQL and Snowpark compute, giving a precise first use case and a clean path to later expansion.

**5. Operational transparency as a product feature**  
Health signals, logging evidence, and approval-ready documentation make reliability and compliance visible to admins, operators, and approvers rather than hiding them in implementation detail.

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

**Architecture Note:** The novelty is in the product contract and operating model, not in inventing a new governance engine or telemetry protocol. The design stays Snowflake-native, preserves Splunk relevance, and uses an OTLP-compatible export path instead of creating a separate control plane.

## Project Scoping & Phased Development

### Phase 1 — MVP

**Goal:** Prove that a Snowflake Native App can deliver Snowflake telemetry to Splunk quickly enough, clearly enough, and safely enough to earn Marketplace approval and real operational use.

**Includes:**
- Distributed Tracing Pack for Event Table telemetry in MVP scope
- Performance Pack for selected `ACCOUNT_USAGE` sources
- In-Snowflake onboarding, destination setup, source selection, governance guidance, health visibility, and operational logging
- Marketplace submission readiness across packaging, testing, documentation, and reviewer enablement

**Go / No-Go gates owned by Tom:**
- Automated security review returns `APPROVED`
- Separate consumer-account install and configuration test passes end to end
- README, reviewer steps, sample data, and any required test credentials are ready for functional review
- Zero open P1/P2 defects and no critical/high CVEs remain at submission

**Explicit MVP out of scope:**
- Additional monitoring packs beyond Distributed Tracing and Performance
- Advanced governance intelligence, in-app log explorer, and volume estimation
- Durable replay for prolonged destination outages
- Broader Event Table coverage for SPCS, Streamlit, Openflow, or Cortex AI telemetry
- Off-Snowflake primary setup or control-plane experiences

### Phase 2 — Growth

Focus on expanding operational depth and governance confidence after MVP validation.

- Richer governance visibility and policy awareness
- In-app log exploration and volume estimation
- Additional packs such as Cost, Security, and Data Pipeline
- Better failure handling and replay for sustained destination outages

### Phase 3 — Expansion

Focus on broader source coverage and strategic platform reach.

- Additional Event Table service categories and new telemetry packs
- Cortex AI and Openflow-oriented coverage
- Broader integration patterns and higher install scale

Business growth outcomes such as active installs, customer acquisition, and Marketplace milestone completion are tracked across these phases, but they are not themselves user journeys.

**Architecture Note:** Each phase extends the same core model rather than replacing it: Snowflake-native execution, governed source selection, Event Table and `ACCOUNT_USAGE` as the primary source families, and OTLP-compatible delivery into Splunk-aligned downstream systems.

## Functional Requirements

Detailed UX behavior plus integration, processing, and release implementation mechanics belong in the companion UX and architecture artifacts. The requirements below define the required capabilities and observable outcomes.

### Installation & Setup

- **FR1:** Maya can install the app from the Snowflake Marketplace without provisioning vendor-managed infrastructure outside Snowflake.
- **FR2:** Maya can review and approve the Snowflake privileges the app requires during install or upgrade flows.
- **FR2a:** Maya can bind an existing warehouse to the app during install so that the Streamlit UI, tasks, and stored procedures have a warehouse for query execution.
- **FR3:** Maya can complete first-time setup in the app so that an OTLP destination is saved, at least one telemetry source is selected, governance review is acknowledged, and export activation is enabled.

### Source Configuration

- **FR4:** Maya can discover which supported `ACCOUNT_USAGE` views and Event Tables are available for selection in the current Snowflake account when operating with the required Snowflake privileges.
- **FR5:** Maya can enable or disable each Monitoring Pack independently.
- **FR6:** Maya can view the default execution interval for each selected telemetry source before activation.
- **FR7:** Maya can change the execution interval for any supported telemetry source without reinstalling the app.
- **FR8:** Maya can configure the OTLP export destination used to send telemetry to Splunk or another OTLP-compatible collector.
- **FR9:** Maya can provide any certificate material required for a private or self-signed OTLP destination and receive a pass-or-fail trust validation before saving the configuration.
- **FR10:** Maya can run a connection test and receive a pass or fail result before saving an OTLP destination.
- **FR11:** Maya can view and change the execution interval used for Event Table collection after initial setup within the supported minimum and maximum interval bounds published for the app.

### Data Governance & Privacy

- **FR12:** Maya can choose, for each supported telemetry source, either the default Snowflake source or a custom source she controls.
- **FR13:** Maya can review, for each enabled source, whether it is a default or custom source and whether masking, row access, and projection controls will be preserved, and must record acknowledgement before export is enabled.
- **FR14:** Maya can receive a blocking disclosure when a default `ACCOUNT_USAGE` view or Event Table is selected that Snowflake masking and row access controls require a custom source, and must acknowledge that disclosure before export is enabled.
- **FR15:** Maya can select a custom source and have exported data reflect the Snowflake masking, row access, and projection policies enforced on that source.
- **FR16:** Maya can select a custom source with masking policies applied and have masked values preserved in exported telemetry.
- **FR17:** Maya can select a custom source with row access policies applied and have only permitted rows included in exported telemetry.
- **FR18:** Maya can select a custom source with projection policies applied and have export continue with blocked columns emitted as `NULL` and a warning recorded for the affected run.

### Telemetry Collection

- **FR19:** Sam can export new Event Table telemetry produced after activation without re-exporting records already delivered successfully.
- **FR20:** Maya can scope Event Table export to the MVP telemetry categories supported by enabled Monitoring Packs: Snowflake SQL and Snowpark compute telemetry.
- **FR21:** Sam can run each enabled `ACCOUNT_USAGE` source on an independent collection schedule so one source can be delayed, changed, or recovered without blocking others.
- **FR22:** Maya can view and edit per-source operational settings, including enabled state, execution interval, overlap window (for `ACCOUNT_USAGE` sources), and batch size.
- **FR22a:** Maya can adjust the overlap window for each `ACCOUNT_USAGE` source to control how far back the watermark query re-scans for late-arriving rows. The default is set to the documented maximum latency for that view plus a small safety margin. Decreasing the overlap reduces redundant re-scanning; the app always deduplicates using natural keys regardless of the configured overlap.

### Telemetry Export

- **FR23:** Sam can deliver all enabled Event Table and `ACCOUNT_USAGE` telemetry through the configured OTLP destination for downstream use in Splunk.
- **FR24:** Ravi can analyze exported Event Table spans in Splunk using query or executable identity, database and schema context, warehouse context, and trace correlation fields.
- **FR25:** Ravi can rely on original Event Table attributes remaining intact in exported telemetry, with any app-added attributes added without renaming or removing source attributes.
- **FR26:** Sam can rely on retryable OTLP delivery failures being retried automatically and on non-retryable failures being recorded as terminal batch failures without endless retry.

### Pipeline Operations & Health

- **FR27:** Sam can view a health summary that shows destination status, source freshness, export throughput, failures, and recent operational issues.
- **FR28:** Sam can inspect each telemetry source to see current status, freshness, recent runs, current errors, and its editable configuration.
- **FR29:** Sam can access structured app operational events in the consumer's Snowflake event table via Snowsight.
- **FR30:** Sam can query app operational events in Snowsight to diagnose OTLP delivery failures, processing failures, and recovery actions.
- **FR31:** Sam can see Event Table collection resume automatically after a recoverable Event Table collection interruption within the recovery window defined by `NFR16`, without manually repairing the pipeline.
- **FR32:** Sam can identify any data gap caused by a recoverable collection interruption or sustained destination outage, including the affected source and time window.
- **FR33:** Sam can have a repeatedly failing source automatically suspended without stopping healthy sources, and can see the suspended status for that source.
- **FR34:** Sam can review per-run pipeline metrics for each source, including records collected, records exported, failures, and processing latency.

### App Lifecycle & Marketplace

- **FR35:** Tom can publish supported app upgrades through Snowflake Marketplace so consumers receive them under their maintenance policy.
- **FR36:** Maya can retain configuration, source progress, and pipeline health history across supported version upgrades.
- **FR37:** Maya can upgrade the app without re-entering configuration, and in-flight scheduled work either completes or resumes automatically with no more than one missed scheduled run per source.
- **FR38:** Sam can access structured upgrade progress events in the Snowflake event table for each upgrade attempt.
- **FR39:** Tom can submit a release candidate for Snowflake Marketplace approval after install, configuration, export, and upgrade workflows pass in a clean consumer account and reviewer guidance is complete.

## Non-Functional Requirements

### Performance

- **NFR1:** Criterion: Event Table telemetry reaches Splunk promptly. Metric: p95 end-to-end latency is `<= 60 seconds` from Event Table write time to visibility in Splunk. Method: compare source timestamps to Splunk ingest timestamps in an instrumented reference flow. Context: normal operation with a reachable OTLP destination.
- **NFR2:** Criterion: `ACCOUNT_USAGE` telemetry arrives soon after Snowflake makes it available. Metric: p95 latency from source availability to visibility in Splunk is `<= one configured polling cycle`. Method: compare Snowflake source availability timestamps to Splunk ingest timestamps. Context: supported `ACCOUNT_USAGE` sources under normal operation.
- **NFR3:** Criterion: Core app pages are responsive for admins and operators. Metric: p95 load-to-render time is `<= 5 seconds` for setup, telemetry sources, governance, and health pages. Method: scripted page-load timing in a reviewer account. Context: supported data volume, including initial Snowflake app startup.
- **NFR4:** Criterion: Health views reflect current pipeline state. Metric: `100%` of sampled KPI values use data no older than the most recent completed run for the represented source or category. Method: compare displayed timestamps to recorded run timestamps. Context: after at least one successful run has completed.
- **NFR5:** Criterion: Batch export processing completes quickly enough to sustain near-real-time delivery. Metric: p95 time from batch start to OTLP send result is `<= 30 seconds`. Method: timing instrumentation around export execution. Context: supported batch sizes with a reachable OTLP destination.

### Security

- **NFR6:** Criterion: Sensitive OTLP connection material is stored only in approved Snowflake secret storage. Metric: `0` instances of credentials or certificate material in code, config tables, app metadata tables, or logs. Method: static review plus runtime table and log inspection. Context: release candidates and failure-path testing.
- **NFR7:** Criterion: All outbound OTLP transport is encrypted. Metric: `100%` of successful OTLP sessions use encrypted transport, and plaintext OTLP connection attempts fail. Method: transport inspection and positive or negative connection tests. Context: all outbound OTLP connections.
- **NFR8:** Criterion: Outbound connectivity is limited to consumer-approved destinations. Metric: `0` successful outbound connections occur to destinations not explicitly approved by the consumer for this app. Method: positive and negative network-access tests against approved and unapproved destinations. Context: configured consumer account.
- **NFR9:** Criterion: The app does not bypass Snowflake governance controls. Metric: `100%` of exported records originate from the Snowflake sources Maya selected, and policy-protected test fields and rows remain governed in exports. Method: controlled datasets with masking, row access, and projection policies. Context: custom-source operation.
- **NFR10:** Criterion: Every version Tom submits satisfies Snowflake Marketplace security review requirements. Metric: `100%` of submitted versions pass the automated Marketplace security scan with `0` Critical or High findings. Method: review Marketplace scan results before submission. Context: Tom's pre-submission release gate.
- **NFR11:** Criterion: Secret material never appears in operational surfaces. Metric: `0` secret or credential findings across event tables, pipeline health outputs, and UI renders in normal and failure scenarios. Method: automated secret scanning plus manual inspection. Context: supported error flows.
- **NFR12:** Criterion: Tom submits only release candidates that meet quality and third-party component hygiene gates. Metric: `0` open P1 or P2 defects and `0` Critical or High unresolved third-party component vulnerabilities at release cut. Method: issue tracker review and component-vulnerability audit. Context: Tom's Marketplace submission gate.

### Reliability

- **NFR13:** Criterion: Each enabled source remains highly available. Metric: scheduled availability is `>= 99.9%` per source over a rolling 30-day window. Method: compare successful runs to planned runs from pipeline health records. Context: deployed supported accounts.
- **NFR14:** Criterion: Export remains dependable after automatic retries. Metric: `>= 99.5%` of batches complete successfully after retry handling over a rolling 7-day window. Method: calculate terminal success rate from pipeline health records. Context: enabled sources with reachable destinations outside declared fault windows.
- **NFR15:** Criterion: A single source failure stays isolated. Metric: in induced single-source failure tests, `100%` of unaffected sources still start and complete within their next scheduled interval. Method: fault-injection test with multiple enabled sources. Context: at least two sources enabled.
- **NFR16:** Criterion: Stale Event Table stream conditions recover autonomously. Metric: `100%` of induced stale stream conditions are detected and export resumes within `10 minutes` or `2 scheduled executions`, whichever is longer, without manual action. Method: controlled stale-stream recovery test. Context: Event Table collection.
- **NFR17:** Criterion: Supported upgrades preserve data continuity. Metric: `0` missing or duplicate records in controlled upgrade reconciliation and `100%` retention of configuration and source progress across supported upgrade paths. Method: before-and-after reconciliation test. Context: version-to-version upgrades supported for release.
- **NFR18:** Criterion: Brief OTLP destination outages do not cause data loss. Metric: `0` permanently lost batches for induced destination outages lasting up to `60 seconds`. Method: outage injection and batch reconciliation. Context: destination outage only, with Snowflake services otherwise healthy.

### Scalability

- **NFR19:** Criterion: Event Table processing supports the target burst size. Metric: a triggered execution completes with `1,000,000` representative Event Table rows without timeout or unrecoverable memory failure. Method: benchmark load test. Context: supported compute allocation and representative telemetry mix.
- **NFR20:** Criterion: The app supports concurrent scheduled collection across multiple `ACCOUNT_USAGE` sources. Metric: with `10` enabled sources, `>= 99%` of scheduled runs start within one interval and complete successfully. Method: concurrent load test. Context: representative source mix and supported scheduling settings.
- **NFR21:** Criterion: Throughput improves materially with additional supported compute. Metric: doubling supported task compute yields at least `1.7x` throughput until destination saturation or the `NFR19` workload ceiling is reached. Method: benchmark the same workload across adjacent supported compute levels. Context: controlled performance environment.

### Integration Quality

- **NFR22:** Criterion: OTLP-exported Event Table spans interoperate with Splunk APM. Metric: `100%` of sampled spans include the database and Snowflake context required by the telemetry contract, pass OTLP schema validation, and are searchable as traces in Splunk APM. Method: contract validation plus end-to-end ingest testing. Context: release validation for Event Table spans.
- **NFR23:** Criterion: Exported telemetry supports downstream routing and attribution. Metric: `100%` of exported spans, metrics, and logs from Event Table and `ACCOUNT_USAGE` include the mandatory routing fields for source identity, Snowflake account identity, telemetry type, and service or resource identity. Method: collector-side contract assertions during integration tests. Context: all enabled telemetry types.
- **NFR24:** Criterion: OTLP error handling is deterministic and observable. Metric: `100%` of retryable OTLP errors trigger automatic retry, and `100%` of non-retryable OTLP errors generate a terminal failure record within `1 minute` with no endless retry loop. Method: simulated OTLP error-class testing. Context: reachable destination returning protocol or application errors.
