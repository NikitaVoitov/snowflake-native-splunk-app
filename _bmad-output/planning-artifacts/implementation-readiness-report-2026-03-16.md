---
stepsCompleted:
  - step-01-document-discovery
  - step-02-prd-analysis
  - step-03-epic-coverage-validation
  - step-04-ux-alignment
  - step-05-epic-quality-review
  - step-06-final-assessment
status: complete
selectedDocuments:
  prd:
    - _bmad-output/planning-artifacts/prd.md
  architecture:
    - _bmad-output/planning-artifacts/architecture.md
  epics:
    - _bmad-output/planning-artifacts/epics.md
  ux:
    - _bmad-output/planning-artifacts/ux-design-specification.md
supportingDocuments:
  - _bmad-output/planning-artifacts/prd-validation-report.md
lastUpdated: 2026-03-16
assessor: Cursor GPT-5.4
---
# Implementation Readiness Assessment Report

**Date:** 2026-03-16  
**Project:** snowflake-native-splunk-app  
**Status:** READY FOR IMPLEMENTATION

## Step 1: Document Discovery

### Selected Core Documents

- PRD: `_bmad-output/planning-artifacts/prd.md`
- Architecture: `_bmad-output/planning-artifacts/architecture.md`
- Epics and Stories: `_bmad-output/planning-artifacts/epics.md`
- UX Design: `_bmad-output/planning-artifacts/ux-design-specification.md`

### Supporting Reference Documents

- `_bmad-output/planning-artifacts/prd-validation-report.md`

### Discovery Notes

- No whole-vs-sharded duplicates were found for PRD, architecture, epics, or UX artifacts.
- No required core planning document appears to be missing.
- `prd-validation-report.md` was retained as a supporting reference rather than a canonical input artifact.

## PRD Analysis

### Functional Requirements

FR1: Maya can install the app from the Snowflake Marketplace without provisioning vendor-managed infrastructure outside Snowflake.

FR2: Maya can review and approve the Snowflake privileges the app requires during install or upgrade flows.

FR3: Maya can complete first-time setup in the app so that an OTLP destination is saved, at least one telemetry source is selected, governance review is acknowledged, and export activation is enabled.

FR4: Maya can discover which supported `ACCOUNT_USAGE` views and Event Tables are available for selection in the current Snowflake account when operating with the required Snowflake privileges.

FR5: Maya can enable or disable each Monitoring Pack independently.

FR6: Maya can view the default execution interval for each selected telemetry source before activation.

FR7: Maya can change the execution interval for any supported telemetry source without reinstalling the app.

FR8: Maya can configure the OTLP export destination used to send telemetry to Splunk or another OTLP-compatible collector.

FR9: Maya can provide any certificate material required for a private or self-signed OTLP destination and receive a pass-or-fail trust validation before saving the configuration.

FR10: Maya can run a connection test and receive a pass or fail result before saving an OTLP destination.

FR11: Maya can view and change the execution interval used for Event Table collection after initial setup within the supported minimum and maximum interval bounds published for the app.

FR12: Maya can choose, for each supported telemetry source, either the default Snowflake source or a custom source she controls.

FR13: Maya can review, for each enabled source, whether it is a default or custom source and whether masking, row access, and projection controls will be preserved, and must record acknowledgement before export is enabled.

FR14: Maya can receive a blocking disclosure when a default `ACCOUNT_USAGE` view or Event Table is selected that Snowflake masking and row access controls require a custom source, and must acknowledge that disclosure before export is enabled.

FR15: Maya can select a custom source and have exported data reflect the Snowflake masking, row access, and projection policies enforced on that source.

FR16: Maya can select a custom source with masking policies applied and have masked values preserved in exported telemetry.

FR17: Maya can select a custom source with row access policies applied and have only permitted rows included in exported telemetry.

FR18: Maya can select a custom source with projection policies applied and have export continue with blocked columns emitted as `NULL` and a warning recorded for the affected run.

FR19: Sam can export new Event Table telemetry produced after activation without re-exporting records already delivered successfully.

FR20: Maya can scope Event Table export to the MVP telemetry categories supported by enabled Monitoring Packs: Snowflake SQL and Snowpark compute telemetry.

FR21: Sam can run each enabled `ACCOUNT_USAGE` source on an independent collection schedule so one source can be delayed, changed, or recovered without blocking others.

FR22: Maya can view and edit per-source operational settings, including enabled state, execution interval, overlap window (for `ACCOUNT_USAGE` sources), and batch size.

FR22a: Maya can adjust the overlap window for each `ACCOUNT_USAGE` source to control how far back the watermark query re-scans for late-arriving rows. The default is set to the documented maximum latency for that view plus a small safety margin. Decreasing the overlap reduces redundant re-scanning; the app always deduplicates using natural keys regardless of the configured overlap.

FR23: Sam can deliver all enabled Event Table and `ACCOUNT_USAGE` telemetry through the configured OTLP destination for downstream use in Splunk.

FR24: Ravi can analyze exported Event Table spans in Splunk using query or executable identity, database and schema context, warehouse context, and trace correlation fields.

FR25: Ravi can rely on original Event Table attributes remaining intact in exported telemetry, with any app-added attributes added without renaming or removing source attributes.

FR26: Sam can rely on retryable OTLP delivery failures being retried automatically and on non-retryable failures being recorded as terminal batch failures without endless retry.

FR27: Sam can view a health summary that shows destination status, source freshness, export throughput, failures, and recent operational issues.

FR28: Sam can inspect each telemetry source to see current status, freshness, recent runs, current errors, and its editable configuration.

FR29: Sam can access structured app operational events in the consumer's Snowflake event table via Snowsight.

FR30: Sam can query app operational events in Snowsight to diagnose OTLP delivery failures, processing failures, and recovery actions.

FR31: Sam can see Event Table collection resume automatically after a recoverable Event Table collection interruption within the recovery window defined by `NFR16`, without manually repairing the pipeline.

FR32: Sam can identify any data gap caused by a recoverable collection interruption or sustained destination outage, including the affected source and time window.

FR33: Sam can have a repeatedly failing source automatically suspended without stopping healthy sources, and can see the suspended status for that source.

FR34: Sam can review per-run pipeline metrics for each source, including records collected, records exported, failures, and processing latency.

FR35: Tom can publish supported app upgrades through Snowflake Marketplace so consumers receive them under their maintenance policy.

FR36: Maya can retain configuration, source progress, and pipeline health history across supported version upgrades.

FR37: Maya can upgrade the app without re-entering configuration, and in-flight scheduled work either completes or resumes automatically with no more than one missed scheduled run per source.

FR38: Sam can access structured upgrade progress events in the Snowflake event table for each upgrade attempt.

FR39: Tom can submit a release candidate for Snowflake Marketplace approval after install, configuration, export, and upgrade workflows pass in a clean consumer account and reviewer guidance is complete.

Total FRs: 40

### Non-Functional Requirements

NFR1: Criterion: Event Table telemetry reaches Splunk promptly. Metric: p95 end-to-end latency is `<= 60 seconds` from Event Table write time to visibility in Splunk. Method: compare source timestamps to Splunk ingest timestamps in an instrumented reference flow. Context: normal operation with a reachable OTLP destination.

NFR2: Criterion: `ACCOUNT_USAGE` telemetry arrives soon after Snowflake makes it available. Metric: p95 latency from source availability to visibility in Splunk is `<= one configured polling cycle`. Method: compare Snowflake source availability timestamps to Splunk ingest timestamps. Context: supported `ACCOUNT_USAGE` sources under normal operation.

NFR3: Criterion: Core app pages are responsive for admins and operators. Metric: p95 load-to-render time is `<= 5 seconds` for setup, telemetry sources, governance, and health pages. Method: scripted page-load timing in a reviewer account. Context: supported data volume, including initial Snowflake app startup.

NFR4: Criterion: Health views reflect current pipeline state. Metric: `100%` of sampled KPI values use data no older than the most recent completed run for the represented source or category. Method: compare displayed timestamps to recorded run timestamps. Context: after at least one successful run has completed.

NFR5: Criterion: Batch export processing completes quickly enough to sustain near-real-time delivery. Metric: p95 time from batch start to OTLP send result is `<= 30 seconds`. Method: timing instrumentation around export execution. Context: supported batch sizes with a reachable OTLP destination.

NFR6: Criterion: Sensitive OTLP connection material is stored only in approved Snowflake secret storage. Metric: `0` instances of credentials or certificate material in code, config tables, app metadata tables, or logs. Method: static review plus runtime table and log inspection. Context: release candidates and failure-path testing.

NFR7: Criterion: All outbound OTLP transport is encrypted. Metric: `100%` of successful OTLP sessions use encrypted transport, and plaintext OTLP connection attempts fail. Method: transport inspection and positive or negative connection tests. Context: all outbound OTLP connections.

NFR8: Criterion: Outbound connectivity is limited to consumer-approved destinations. Metric: `0` successful outbound connections occur to destinations not explicitly approved by the consumer for this app. Method: positive and negative network-access tests against approved and unapproved destinations. Context: configured consumer account.

NFR9: Criterion: The app does not bypass Snowflake governance controls. Metric: `100%` of exported records originate from the Snowflake sources Maya selected, and policy-protected test fields and rows remain governed in exports. Method: controlled datasets with masking, row access, and projection policies. Context: custom-source operation.

NFR10: Criterion: Every version Tom submits satisfies Snowflake Marketplace security review requirements. Metric: `100%` of submitted versions pass the automated Marketplace security scan with `0` Critical or High findings. Method: review Marketplace scan results before submission. Context: Tom's pre-submission release gate.

NFR11: Criterion: Secret material never appears in operational surfaces. Metric: `0` secret or credential findings across event tables, pipeline health outputs, and UI renders in normal and failure scenarios. Method: automated secret scanning plus manual inspection. Context: supported error flows.

NFR12: Criterion: Tom submits only release candidates that meet quality and third-party component hygiene gates. Metric: `0` open P1 or P2 defects and `0` Critical or High unresolved third-party component vulnerabilities at release cut. Method: issue tracker review and component-vulnerability audit. Context: Tom's Marketplace submission gate.

NFR13: Criterion: Each enabled source remains highly available. Metric: scheduled availability is `>= 99.9%` per source over a rolling 30-day window. Method: compare successful runs to planned runs from pipeline health records. Context: deployed supported accounts.

NFR14: Criterion: Export remains dependable after automatic retries. Metric: `>= 99.5%` of batches complete successfully after retry handling over a rolling 7-day window. Method: calculate terminal success rate from pipeline health records. Context: enabled sources with reachable destinations outside declared fault windows.

NFR15: Criterion: A single source failure stays isolated. Metric: in induced single-source failure tests, `100%` of unaffected sources still start and complete within their next scheduled interval. Method: fault-injection test with multiple enabled sources. Context: at least two sources enabled.

NFR16: Criterion: Stale Event Table stream conditions recover autonomously. Metric: `100%` of induced stale stream conditions are detected and export resumes within `10 minutes` or `2 scheduled executions`, whichever is longer, without manual action. Method: controlled stale-stream recovery test. Context: Event Table collection.

NFR17: Criterion: Supported upgrades preserve data continuity. Metric: `0` missing or duplicate records in controlled upgrade reconciliation and `100%` retention of configuration and source progress across supported upgrade paths. Method: before-and-after reconciliation test. Context: version-to-version upgrades supported for release.

NFR18: Criterion: Brief OTLP destination outages do not cause data loss. Metric: `0` permanently lost batches for induced destination outages lasting up to `60 seconds`. Method: outage injection and batch reconciliation. Context: destination outage only, with Snowflake services otherwise healthy.

NFR19: Criterion: Event Table processing supports the target burst size. Metric: a triggered execution completes with `1,000,000` representative Event Table rows without timeout or unrecoverable memory failure. Method: benchmark load test. Context: supported compute allocation and representative telemetry mix.

NFR20: Criterion: The app supports concurrent scheduled collection across multiple `ACCOUNT_USAGE` sources. Metric: with `10` enabled sources, `>= 99%` of scheduled runs start within one interval and complete successfully. Method: concurrent load test. Context: representative source mix and supported scheduling settings.

NFR21: Criterion: Throughput improves materially with additional supported compute. Metric: doubling supported task compute yields at least `1.7x` throughput until destination saturation or the `NFR19` workload ceiling is reached. Method: benchmark the same workload across adjacent supported compute levels. Context: controlled performance environment.

NFR22: Criterion: OTLP-exported Event Table spans interoperate with Splunk APM. Metric: `100%` of sampled spans include the database and Snowflake context required by the telemetry contract, pass OTLP schema validation, and are searchable as traces in Splunk APM. Method: contract validation plus end-to-end ingest testing. Context: release validation for Event Table spans.

NFR23: Criterion: Exported telemetry supports downstream routing and attribution. Metric: `100%` of exported spans, metrics, and logs from Event Table and `ACCOUNT_USAGE` include the mandatory routing fields for source identity, Snowflake account identity, telemetry type, and service or resource identity. Method: collector-side contract assertions during integration tests. Context: all enabled telemetry types.

NFR24: Criterion: OTLP error handling is deterministic and observable. Metric: `100%` of retryable OTLP errors trigger automatic retry, and `100%` of non-retryable OTLP errors generate a terminal failure record within `1 minute` with no endless retry loop. Method: simulated OTLP error-class testing. Context: reachable destination returning protocol or application errors.

Total NFRs: 24

### Additional Requirements

- MVP monitoring scope is intentionally limited to a Distributed Tracing Pack for Snowflake Event Table telemetry relevant to SQL and Snowpark compute and a Performance Pack for selected `ACCOUNT_USAGE` telemetry.
- Governance follows a user-selected source model: the consumer chooses either default Snowflake sources or their own custom governed sources; the app does not create, refresh, or repair governed views or policies.
- The core experience must remain on Snowflake for Marketplace approval readiness, including install, approval, destination setup, source activation, health visibility, and reviewer enablement.
- OTLP-compatible export is the single interoperability path for Splunk-aligned delivery; direct non-OTLP destination families are out of scope for MVP.
- The app uses a single application role, `app_admin`, for MVP.
- Event Table MVP scope explicitly excludes SPCS, Streamlit service categories, Openflow, Cortex AI, and broader post-MVP telemetry families.
- Durable replay and zero-copy recovery for prolonged destination outages are out of scope for MVP, though brief outages must not cause data loss under `NFR18`.
- Marketplace release readiness is a first-class workflow owned by Tom, including security review readiness, functional review readiness, documentation, reviewer steps, and submission go/no-go authority.

### PRD Completeness Assessment

- The PRD is strong on explicit traceability: requirements are numbered, measurable, and grouped by functional and non-functional domains.
- Release-readiness, governance, and upgrade-continuity requirements are unusually well specified for an MVP and materially reduce downstream ambiguity.
- The PRD also captures important non-FR constraints that the later artifacts must preserve, especially the user-selected source model, OTLP-only export path, and on-Snowflake experience requirement.
- The main validation risk now is no longer PRD incompleteness, but whether epics, UX flows, and architecture preserve all of this operational and compliance detail without gaps.

## Epic Coverage Validation

### Coverage Matrix

| FR Number | PRD Requirement | Epic Coverage | Status |
| --- | --- | --- | --- |
| FR1 | Maya can install the app from the Snowflake Marketplace without provisioning vendor-managed infrastructure outside Snowflake. | Epic 1 | Covered |
| FR2 | Maya can review and approve the Snowflake privileges the app requires during install or upgrade flows. | Epic 1 | Covered |
| FR3 | Maya can complete first-time setup in the app so that an OTLP destination is saved, at least one telemetry source is selected, governance review is acknowledged, and export activation is enabled. | Epic 2 | Covered |
| FR4 | Maya can discover which supported `ACCOUNT_USAGE` views and Event Tables are available for selection in the current Snowflake account when operating with the required Snowflake privileges. | Epic 3 | Covered |
| FR5 | Maya can enable or disable each Monitoring Pack independently. | Epic 3 | Covered |
| FR6 | Maya can view the default execution interval for each selected telemetry source before activation. | Epic 3 | Covered |
| FR7 | Maya can change the execution interval for any supported telemetry source without reinstalling the app. | Epic 3 | Covered |
| FR8 | Maya can configure the OTLP export destination used to send telemetry to Splunk or another OTLP-compatible collector. | Epic 2 | Covered |
| FR9 | Maya can provide any certificate material required for a private or self-signed OTLP destination and receive a pass-or-fail trust validation before saving the configuration. | Epic 2 | Covered |
| FR10 | Maya can run a connection test and receive a pass or fail result before saving an OTLP destination. | Epic 2 | Covered |
| FR11 | Maya can view and change the execution interval used for Event Table collection after initial setup within the supported minimum and maximum interval bounds published for the app. | Epic 3 | Covered |
| FR12 | Maya can choose, for each supported telemetry source, either the default Snowflake source or a custom source she controls. | Epic 3 | Covered |
| FR13 | Maya can review, for each enabled source, whether it is a default or custom source and whether masking, row access, and projection controls will be preserved, and must record acknowledgement before export is enabled. | Epic 6 | Covered |
| FR14 | Maya can receive a blocking disclosure when a default `ACCOUNT_USAGE` view or Event Table is selected that Snowflake masking and row access controls require a custom source, and must acknowledge that disclosure before export is enabled. | Epic 6 | Covered |
| FR15 | Maya can select a custom source and have exported data reflect the Snowflake masking, row access, and projection policies enforced on that source. | Epic 6 | Covered |
| FR16 | Maya can select a custom source with masking policies applied and have masked values preserved in exported telemetry. | Epic 6 | Covered |
| FR17 | Maya can select a custom source with row access policies applied and have only permitted rows included in exported telemetry. | Epic 6 | Covered |
| FR18 | Maya can select a custom source with projection policies applied and have export continue with blocked columns emitted as `NULL` and a warning recorded for the affected run. | Epic 6 | Covered |
| FR19 | Sam can export new Event Table telemetry produced after activation without re-exporting records already delivered successfully. | Epic 5 | Covered |
| FR20 | Maya can scope Event Table export to the MVP telemetry categories supported by enabled Monitoring Packs: Snowflake SQL and Snowpark compute telemetry. | Epic 5 | Covered |
| FR21 | Sam can run each enabled `ACCOUNT_USAGE` source on an independent collection schedule so one source can be delayed, changed, or recovered without blocking others. | Epic 5 | Covered |
| FR22 | Maya can view and edit per-source operational settings, including enabled state, execution interval, overlap window (for `ACCOUNT_USAGE` sources), and batch size. | Epic 3 | Covered |
| FR22a | Maya can adjust the overlap window for each `ACCOUNT_USAGE` source to control how far back the watermark query re-scans for late-arriving rows. The default is set to the documented maximum latency for that view plus a small safety margin. Decreasing the overlap reduces redundant re-scanning; the app always deduplicates using natural keys regardless of the configured overlap. | Epic 3 | Covered |
| FR23 | Sam can deliver all enabled Event Table and `ACCOUNT_USAGE` telemetry through the configured OTLP destination for downstream use in Splunk. | Epic 6 | Covered |
| FR24 | Ravi can analyze exported Event Table spans in Splunk using query or executable identity, database and schema context, warehouse context, and trace correlation fields. | Epic 4 | Covered |
| FR25 | Ravi can rely on original Event Table attributes remaining intact in exported telemetry, with any app-added attributes added without renaming or removing source attributes. | Epic 4 | Covered |
| FR26 | Sam can rely on retryable OTLP delivery failures being retried automatically and on non-retryable failures being recorded as terminal batch failures without endless retry. | Epic 4 | Covered |
| FR27 | Sam can view a health summary that shows destination status, source freshness, export throughput, failures, and recent operational issues. | Epic 7 | Covered |
| FR28 | Sam can inspect each telemetry source to see current status, freshness, recent runs, current errors, and its editable configuration. | Epic 7 | Covered |
| FR29 | Sam can access structured app operational events in the consumer's Snowflake event table via Snowsight. | Epic 7 | Covered |
| FR30 | Sam can query app operational events in Snowsight to diagnose OTLP delivery failures, processing failures, and recovery actions. | Epic 7 | Covered |
| FR31 | Sam can see Event Table collection resume automatically after a recoverable Event Table collection interruption within the recovery window defined by `NFR16`, without manually repairing the pipeline. | Epic 7 | Covered |
| FR32 | Sam can identify any data gap caused by a recoverable collection interruption or sustained destination outage, including the affected source and time window. | Epic 7 | Covered |
| FR33 | Sam can have a repeatedly failing source automatically suspended without stopping healthy sources, and can see the suspended status for that source. | Epic 7 | Covered |
| FR34 | Sam can review per-run pipeline metrics for each source, including records collected, records exported, failures, and processing latency. | Epic 7 | Covered |
| FR35 | Tom can publish supported app upgrades through Snowflake Marketplace so consumers receive them under their maintenance policy. | Epic 8 | Covered |
| FR36 | Maya can retain configuration, source progress, and pipeline health history across supported version upgrades. | Epic 8 | Covered |
| FR37 | Maya can upgrade the app without re-entering configuration, and in-flight scheduled work either completes or resumes automatically with no more than one missed scheduled run per source. | Epic 8 | Covered |
| FR38 | Sam can access structured upgrade progress events in the Snowflake event table for each upgrade attempt. | Epic 8 | Covered |
| FR39 | Tom can submit a release candidate for Snowflake Marketplace approval after install, configuration, export, and upgrade workflows pass in a clean consumer account and reviewer guidance is complete. | Epic 8 | Covered |

### Missing Requirements

- No uncovered PRD functional requirements were found in the epic coverage map.
- No extra epic-level FR mappings were found that fall outside the PRD FR inventory.

### Coverage Statistics

- Total PRD FRs: 40
- FRs covered in epics: 40
- Coverage percentage: 100%

## UX Alignment Assessment

### UX Document Status

Found: `_bmad-output/planning-artifacts/ux-design-specification.md`

### Alignment Notes

- **Certificate input wording has been normalized to paste-only PEM entry.**
  - The UX specification now consistently describes certificate handling as paste-only via `st.text_area`, which matches the Snowflake Native App constraint set.

- **The extra UX specificity relative to the PRD is an accepted project choice.**
  - Details such as the sidebar `X/4` progress badge, precise Getting Started removal behavior, the `About` dialog, the helicopter-view composition of Observability Health, and the category-based `st.data_editor` layout are being treated as binding implementation detail rather than as alignment defects.

### Warnings

- **PRD ↔ UX alignment is otherwise strong.**
  - The UX journeys map cleanly to PRD journeys: first-time setup, daily health monitoring, governance review, and post-onboarding source management.
  - The UX design reinforces the PRD's key product contract: on-Snowflake setup, OTLP-only destination configuration, and user-selected governed versus default sources.

- **UX ↔ Architecture alignment is also broadly strong.**
  - Architecture explicitly supports the UX's native-Streamlit approach with `st.navigation()`, the same sidebar order, Streamlit page breakdown, Connection Card, source table, health cards, governance page, and manual-refresh evaluation model.
  - Architecture also carries the PRD performance expectation for responsive pages and the Native App constraints that shape the UX.

- **Primary architectural readiness warning for UX is precision, not absence.**
  - The system has enough architectural support for the designed experience, but implementation should treat the UX detail level as normative so the final app does not collapse into a generic admin UI that technically satisfies FRs while missing the intended onboarding and operational flow.

## Epic Quality Review

### Compliance Summary

| Epic | User Value | Independent | No Forward Dependencies | Story Sizing | Overall |
| --- | --- | --- | --- | --- | --- |
| Epic 1 | Yes | Yes | Yes | Good | Strong |
| Epic 2 | Yes | Yes | Yes | Good | Strong |
| Epic 3 | Yes | Yes | Yes | Good | Strong |
| Epic 4 | Yes | Yes | Yes | Good | Strong |
| Epic 5 | Yes | Yes | Yes | Good | Strong |
| Epic 6 | Yes | Yes | Yes | Good | Strong |
| Epic 7 | Yes | Mostly yes | Yes | Good | Strong |
| Epic 8 | Yes | Mostly yes | Yes | Good | Strong |

### Remaining Issues

- **None.** Epic order matches implementation dependency order (1 → 2 → 3 → 4 → 5 → 6 → 7 → 8); stories are sized and scoped for independent delivery; implementation detail is captured under user-facing stories.

## Summary and Recommendations

### Overall Readiness Status

**READY FOR IMPLEMENTATION**

### Remaining Issues

- **None.** No critical or blocking planning issues remain. PRD coverage is complete; UX, architecture, epics, and sprint plan are aligned to implementation order 1 → 8.

### Recommended Next Steps

1. Create story files from the epic breakdown in order: Epic 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8.
2. Treat UX onboarding and operational behaviors as binding implementation detail during development and review.
3. Implement story-by-story using the sprint plan; run code review per story or sprint.
