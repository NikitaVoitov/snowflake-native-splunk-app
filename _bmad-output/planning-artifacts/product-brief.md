---
stepsCompleted: [1, 2, 3, 4, 5, 6]
status: complete
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/splunk_snowflake_native_app_vision.md
  - _bmad-output/planning-artifacts/Native_App_Approval_Process_Guide.md
date: 2026-02-15
lastUpdated: 2026-03-15
author: Nik
updateNote: "Synced to current PRD: user-selected default or custom sources, OTLP-compatible export path, governance guidance instead of app-owned governance objects, Tom persona, Marketplace review readiness, and updated MVP/post-MVP boundaries."
---

# Product Brief: snowflake-native-splunk-app

## Executive Summary

Splunk Observability for Snowflake is a Snowflake Native App that helps teams bring Snowflake telemetry into Splunk through a Snowflake-first setup experience and an OTLP-compatible export path. The MVP focuses on two packs: a Distributed Tracing Pack for Event Table telemetry relevant to SQL and Snowpark compute, and a Performance Pack for selected `ACCOUNT_USAGE` sources.

The core promise is fast first value without hiding governance tradeoffs. Maya can install the app, select the sources her team wants to expose, understand when default Snowflake sources are sufficient versus when custom governed sources are needed, and activate export from inside Snowflake. Ravi can investigate Snowflake-related incidents in Splunk using exported trace and performance context. Sam can monitor pipeline health and troubleshoot failures. Tom can validate that the release is reviewer-ready, security-ready, and aligned with Snowflake Marketplace approval expectations before submission.

## Core Vision

Build the easiest trustworthy path from Snowflake telemetry to Splunk for the MVP source families, while keeping the core product experience on Snowflake and making governance and approval constraints explicit.

| Vision Principle | What it means |
|---|---|
| **Snowflake-first experience** | Installation, approval, configuration, activation, and health visibility stay centered in Snowflake. |
| **User-selected sources** | Customers choose which supported Event Table and `ACCOUNT_USAGE` sources to export, including whether to use default Snowflake sources or custom sources they control. |
| **Governance guidance, not a second policy engine** | The product explains governance implications clearly and respects customer source choices rather than creating or managing governed views on the customer's behalf. |
| **Splunk-aligned interoperability** | Telemetry exits through an OTLP-compatible delivery path that fits Splunk-aligned downstream routing instead of hardwiring multiple destination models into the app. |
| **Approval-ready by design** | Marketplace review readiness, security posture, and reviewer usability are treated as part of the product, not as last-minute release packaging. |

## Target Users

The brief centers on two primary personas, one operational persona, and one approval stakeholder.

| Persona | Role | Priority | Primary need |
|---|---|---|---|
| **Maya** | Snowflake Administrator | Primary | Install the app, approve access, choose sources, understand governance implications, and reach first telemetry quickly. |
| **Ravi** | Site Reliability Engineer | Primary | Investigate Snowflake-related incidents inside Splunk with trace and performance context that would otherwise stay inside Snowflake. |
| **Sam** | DevOps / Operations Engineer | Supporting ops persona | Monitor source freshness, destination health, failures, and recovery signals so the export path stays reliable. |
| **Tom** | Security & Compliance / Marketplace Approval lead | Supporting approval stakeholder | Confirm reviewer readiness, governance messaging, release quality, and Marketplace submission readiness without expanding the product's scope. |

### User Journey

| Stage | Lead persona | Brief journey |
|---|---|---|
| **Install and configure** | Maya | Maya installs the app from Snowflake Marketplace, completes approvals, configures the OTLP-compatible destination, and enables the MVP packs she needs. |
| **Choose sources with governance clarity** | Maya | She selects supported Event Table and `ACCOUNT_USAGE` sources, choosing default Snowflake sources for speed or custom sources when masking, row access, or projection controls must be enforced before export. |
| **Reach operational value** | Ravi and Sam | Ravi uses exported Snowflake context in Splunk to investigate incidents faster, while Sam uses health and operational evidence to monitor freshness, diagnose failures, and maintain confidence in the export path. |
| **Clear approval gates** | Tom | Tom validates that the release works in a separate consumer-style account, that reviewer guidance is complete, and that security, quality, and Marketplace readiness gates are green before submission. |

## Success Metrics

| Category | Metric | Target |
|---|---|---|
| **User value** | Time to first telemetry | `< 15 minutes` from Marketplace install to first data visible in Splunk |
| **User value** | Incident resolution improvement | `50%` reduction in MTTR for Snowflake-related incidents |
| **User value** | Unified investigation flow | Snowflake context is visible inside Splunk for MVP incident scenarios |
| **Operational quality** | Export success rate | `>= 99.5%` successful batches |
| **Operational quality** | Event Table delivery latency | `< 60 seconds` from Event Table write to visibility in Splunk |
| **Release readiness** | Consumer-account functional readiness | Reviewer can install, configure, and use the app without setup or privilege blockers |
| **Release readiness** | Submission quality gate | `0` open P1/P2 defects and `0` critical/high CVEs at submission |
| **Business traction** | Adoption | `5+` active installs in 6 months and at least `1` new customer in 12 months |

## MVP Scope

MVP is intentionally narrow: prove that a Snowflake Native App can deliver fast, useful, reviewer-ready Snowflake telemetry into Splunk with clear governance guidance.

| Area | In MVP | Not in MVP |
|---|---|---|
| **Telemetry packs** | Distributed Tracing Pack and Performance Pack | Cost, Security, Data Pipeline, Openflow, and Cortex AI packs |
| **Source coverage** | User-selected Event Table telemetry for SQL and Snowpark compute, plus selected `ACCOUNT_USAGE` sources | Broader Event Table service categories such as SPCS and Streamlit |
| **Configuration** | In-Snowflake install, approval, source selection, OTLP-compatible destination setup, activation, and first-data validation | Off-Snowflake primary setup experience or destination families beyond the OTLP-compatible path |
| **Governance** | Clear guidance on default versus custom sources and support for customer-owned governed sources | In-app governance authoring, policy management, or a separate app-owned governance engine |
| **Operations** | Health visibility, troubleshooting evidence, and recovery awareness for enabled sources | Advanced governance intelligence, in-app log explorer, volume estimation, and durable replay for prolonged outages |
| **Release** | Marketplace submission readiness, reviewer steps, and approval evidence | Broader expansion work not required for MVP launch |

## Future Vision

Post-MVP growth expands depth and coverage without changing the core model: Snowflake-native operation, user-selected sources, explicit governance posture, and OTLP-compatible delivery into Splunk-aligned downstream systems.

| Horizon | Focus |
|---|---|
| **Post-MVP growth** | Richer governance visibility, in-app log exploration, volume estimation, stronger failure handling and replay, and additional packs such as Cost, Security, and Data Pipeline. |
| **Expansion** | Broader Event Table coverage, Openflow and Cortex AI oriented packs, wider integration patterns, and validation at higher install scale. |
