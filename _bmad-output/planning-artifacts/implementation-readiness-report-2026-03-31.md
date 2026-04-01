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
  stories:
    - _bmad-output/implementation-artifacts/3-2-per-source-selection-and-intervals.md
supportingDocuments:
  - _bmad-output/planning-artifacts/prd-validation-report.md
lastUpdated: 2026-03-31
assessor: Cursor GPT-5.4
---
# Implementation Readiness Assessment Report

**Date:** 2026-03-31  
**Project:** snowflake-native-splunk-app  
**Status:** READY FOR IMPLEMENTATION

## Step 1: Document Discovery

### Selected Core Documents

- PRD: `_bmad-output/planning-artifacts/prd.md`
- Architecture: `_bmad-output/planning-artifacts/architecture.md`
- Epics and Stories: `_bmad-output/planning-artifacts/epics.md`
- UX Design: `_bmad-output/planning-artifacts/ux-design-specification.md`
- Story Under Review: `_bmad-output/implementation-artifacts/3-2-per-source-selection-and-intervals.md`

### Supporting Reference Documents

- `_bmad-output/planning-artifacts/prd-validation-report.md`

### Discovery Notes

- No whole-vs-sharded duplicates were found for PRD, architecture, epics, or UX artifacts.
- No required core planning document appears to be missing.
- `prd-validation-report.md` is being treated as a supporting reference rather than a canonical planning input.

## PRD Analysis

### Functional Requirements

FR1: Maya can install the app from the Snowflake Marketplace without provisioning vendor-managed infrastructure outside Snowflake.

FR2: Maya can review and approve the Snowflake privileges the app requires during install or upgrade flows.

FR2a: Maya can bind an existing warehouse to the app during install so that the Streamlit UI, tasks, and stored procedures have a warehouse for query execution.

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

- The PRD explicitly ties the Telemetry Sources experience to user journeys for Maya and Sam and requires the app to keep the core configuration experience inside Snowflake.
- The source-configuration scope relevant to story `3.2` is anchored by FR6, FR7, FR21, FR22, and FR22a.
- The PRD defines a broader per-source operational-settings capability, but the current Epic 3 plan now explicitly scopes Story `3.2` to Interval and Overlap only, with batch size deferred for now.
- Governance messaging and custom-vs-default source behavior remain first-class requirements and cannot be regressed while implementing per-source interval and overlap editing.
- The PRD places health visibility and per-source inspection in later capabilities (FR27-FR34), which helps separate current scope from future health/status columns.

### PRD Completeness Assessment

- The PRD is complete enough to support traceability for story `3.2`.
- The strongest requirement trace for this story is present and explicit: FR22 and FR22a directly require editable per-source interval and overlap settings, while FR21 explains why the settings are per-source rather than pack-wide.
- The PRD remains compatible with the clarified story scope as long as the team treats batch size as deferred and keeps persistence verification in Story `3.3`.

## Epic Coverage Validation

### Coverage Matrix

| FR Number | PRD Requirement | Epic Coverage | Status |
| --------- | --------------- | ------------- | ------ |
| FR1 | Install from Marketplace without vendor infrastructure | Epic 1 | Covered |
| FR2 | Review and approve Snowflake privileges | Epic 1 | Covered |
| FR2a | Bind an existing warehouse during install | Epic 1 | Covered |
| FR3 | Complete first-time setup | Epic 2 | Covered |
| FR4 | Discover supported sources | Epic 3 | Covered |
| FR5 | Enable or disable each Monitoring Pack | Epic 3 | Covered |
| FR6 | View default execution interval per source | Epic 3 | Covered |
| FR7 | Change execution interval without reinstall | Epic 3 | Covered |
| FR8 | Configure OTLP destination | Epic 2 | Covered |
| FR9 | Provide and validate certificate material | Epic 2 | Covered |
| FR10 | Run connection test before saving | Epic 2 | Covered |
| FR11 | View and change Event Table interval after setup | Epic 3 | Covered |
| FR12 | Choose default or custom source per telemetry source | Epic 3 | Covered |
| FR13 | Review source type and governance implications | Epic 6 | Covered |
| FR14 | Receive blocking disclosure for default sources | Epic 6 | Covered |
| FR15 | Custom-source exports reflect Snowflake policies | Epic 6 | Covered |
| FR16 | Masked values preserved in exported telemetry | Epic 6 | Covered |
| FR17 | Row-access policies preserved in exported telemetry | Epic 6 | Covered |
| FR18 | Projection-blocked columns exported as `NULL` with warning | Epic 6 | Covered |
| FR19 | Incremental Event Table export without re-export | Epic 5 | Covered |
| FR20 | Scope Event Table export to MVP telemetry categories | Epic 5 | Covered |
| FR21 | Independent schedule per enabled `ACCOUNT_USAGE` source | Epic 5 | Covered |
| FR22 | View and edit per-source operational settings | Epic 3 | Covered |
| FR22a | Adjust overlap window per `ACCOUNT_USAGE` source | Epic 3 | Covered |
| FR23 | Deliver all enabled telemetry through OTLP | Epic 6 | Covered |
| FR24 | Analyze exported spans in Splunk with required context | Epic 4 | Covered |
| FR25 | Preserve original Event Table attributes | Epic 4 | Covered |
| FR26 | Retryable OTLP failures retried; terminal failures recorded | Epic 4 | Covered |
| FR27 | View health summary | Epic 7 | Covered |
| FR28 | Inspect per-source status and configuration | Epic 7 | Covered |
| FR29 | Access structured operational events in Snowflake event table | Epic 7 | Covered |
| FR30 | Query app events for diagnosis | Epic 7 | Covered |
| FR31 | Event Table collection resumes after recoverable interruption | Epic 7 | Covered |
| FR32 | Identify data gaps after interruption or outage | Epic 7 | Covered |
| FR33 | Auto-suspend repeatedly failing sources | Epic 7 | Covered |
| FR34 | Review per-run pipeline metrics | Epic 7 | Covered |
| FR35 | Publish supported app upgrades through Marketplace | Epic 8 | Covered |
| FR36 | Retain configuration and health history across upgrades | Epic 8 | Covered |
| FR37 | Upgrade without re-entering configuration | Epic 8 | Covered |
| FR38 | Access structured upgrade progress events | Epic 8 | Covered |
| FR39 | Submit Marketplace release candidate after validation | Epic 8 | Covered |

### Missing Requirements

- No PRD functional requirements are missing from the epic coverage map.
- No extra epic-level FR claims were found that fall outside the PRD inventory.
- The planning set provides explicit epic ownership for every PRD FR, including `FR22` and `FR22a`, which are the primary trace points for story `3.2`.

### Coverage Statistics

- Total PRD FRs: 40
- FRs covered in epics: 40
- Coverage percentage: 100%

## UX Alignment Assessment

### UX Document Status

- Found: `_bmad-output/planning-artifacts/ux-design-specification.md`
- The UX specification explicitly covers the Telemetry Sources page, including editable `Interval` and `Overlap` behavior, category headers, and page-level interaction timing.

### Alignment Issues

- The UX specification now aligns with the clarified Epic 3 slice: source selection is handled by Story `3.1`, Interval/Overlap editing is handled by Story `3.2`, and durable save/load verification is handled by Story `3.3`.
- UX and architecture align on `Overlap` semantics: `ACCOUNT_USAGE` only, default derived from documented source latency plus a safety margin, and hidden for Event Table rows.
- UX and PRD align on per-source configuration intent: editable interval and overlap are consistent with FR6, FR7, FR22, and FR22a.
- There is an internal UX inconsistency around source-type presentation: the high-level UX requirements mention a visible Source type column or tag, while the detailed row layout describes the type as a subtle tag inside `View name` rather than a standalone column.
- Batch size has now been explicitly deferred out of scope for the current MVP Telemetry Sources UI.

### Warnings

- No blocking UX alignment issues remain after the scope normalization made on 2026-03-31.
- Minor planning differences such as later health columns remain explicitly deferred to their own stories and epics.

## Epic Quality Review

### Overall Epic Structure

- The epic set is generally strong: epics are user-outcome oriented, sequenced logically, and maintain clear FR traceability.
- No obvious technical-only epics were found.
- No clear forward epic dependency violations were found in the overall epic ordering.

### Findings

#### 🟠 Major Issues

- No major issues remain after the Epic 3 scope normalization performed on 2026-03-31.

#### 🟡 Minor Concerns

- **Source-type presentation is still not perfectly uniform across all planning documents:** some documents imply a dedicated column while others treat it as a tag or later capability. This is no longer blocking Story `3.2`, but should be cleaned up when the next source-configuration story is authored.

### Recommendations

- Keep Story `3.2` strictly focused on Interval and Overlap editing.
- Keep Story `3.3` focused on durable save/load and dirty-state verification for the full 3.1-3.2 Telemetry Sources configuration set.
- Treat batch size as deferred until a future product decision reintroduces it.

## Summary and Recommendations

### Overall Readiness Status

READY FOR IMPLEMENTATION

### Critical Issues Requiring Immediate Action

- No critical blockers remain for Story `3.2` after the 2026-03-31 scope clarification.

### Recommended Next Steps

1. Implement Story `3.2` as the Interval/Overlap editing slice only.
2. Create or update the Story `3.3` implementation artifact so it verifies durable save/load and dirty-state coverage for pack, poll, interval, and overlap settings together.
3. Clean up the remaining non-blocking `source_type` wording drift when the next Telemetry Sources planning pass happens.

### Final Note

The original assessment identified scope and boundary issues, and those issues have now been resolved by normalizing the Epic 3 planning artifacts. Story `3.2` is ready to hand to a dev agent with the clarified scope captured in the updated documents.
