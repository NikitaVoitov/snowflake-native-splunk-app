---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: complete
completedAt: '2026-03-15'
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/product-brief.md
  - _bmad-output/planning-artifacts/splunk_snowflake_native_app_vision.md
  - _bmad-output/planning-artifacts/ux-design-specification.md
  - _bmad-output/planning-artifacts/event_table_streams_governance_research.md
  - _bmad-output/planning-artifacts/otel_semantic_conventions_snowflake_research.md
  - _bmad-output/planning-artifacts/snowflake_data_governance_privacy_features.md
  - _bmad-output/planning-artifacts/event_table_entity_discrimination_strategy.md
  - _bmad-output/planning-artifacts/evt_architecture_adversarial_review.md
  - _bmad-output/planning-artifacts/prd-validation-report.md
  - _bmad-output/planning-artifacts/Native_App_Approval_Process_Guide.md
workflowType: 'architecture'
project_name: 'snowflake-native-splunk-app'
user_name: 'Nik'
date: '2026-03-15'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements (39 FRs across 6 categories):**

| Category | FRs | Architectural Implication |
|---|---|---|
| Installation & Setup (FR1–FR3) | Marketplace install, privilege approval, first-time setup | Native App framework, Python Permission SDK, idempotent setup.sql |
| Source Configuration (FR4–FR11) | Pack management, intervals, OTLP destination, certs, connection test | Config state table, EAI provisioning, Snowflake Secrets, dynamic task management |
| Data Governance & Privacy (FR12–FR18) | Custom/default source selection, governance disclosure, policy-respecting export | User-selected source model, consumer-owned `CHANGE_TRACKING = TRUE` on custom Event Table views, NULL-tolerant pipelines |
| Telemetry Collection (FR19–FR22) | Incremental export, entity scoping, independent schedules, per-source settings | Dual-pipeline (both scheduled-task-driven, unified self-managed watermark), entity discrimination filter, `CHANGES` clause for Event Tables, watermark + overlap + `QUALIFY` for ACCOUNT_USAGE |
| Telemetry Export (FR23–FR26) | OTLP delivery, Splunk-compatible spans, convention transparency, retry/failure | OTLP/gRPC client, OTel convention mapping, transport-level retry |
| Pipeline Operations & Health (FR27–FR34) | Health summary, source inspection, operational events, auto-recovery, auto-suspend | Internal metrics table, Native App event definitions, `WATERMARK_EXPIRED` self-heal, `CHANGE_TRACKING_DISABLED` diagnostic |
| App Lifecycle (FR35–FR39) | Upgrades, config preservation, submission readiness | Versioned schemas, stateful object preservation, multi-package publish pipeline |

**Non-Functional Requirements (24 NFRs across 5 domains):**

| Domain | Key Targets | Architectural Driver |
|---|---|---|
| Performance | Event Table ≤60s e2e, AU ≤1 poll cycle, page render ≤5s, batch ≤30s | Scheduled serverless tasks (default 1 min cadence), Snowpark pushdown, chunked processing |
| Security | Secrets in Snowflake Secrets only, TLS-only OTLP, no governance bypass, security scan pass | EAI + Network Rules, secret references (not values) in config, policy-transparent reads |
| Reliability | 99.9% per-source availability, 99.5% batch success, watermark self-heal ≤10min, fault isolation | Independent scheduled tasks, advance-on-success / hold-on-failure watermark, auto-suspend, `WATERMARK_EXPIRED` reset-and-resume |
| Scalability | 1M Event Table rows per scheduled run, 10 concurrent AU sources, 1.7× throughput scaling | Serverless compute, `to_pandas_batches()` chunking, independent scheduled-task architecture |
| Integration | Splunk APM interop, mandatory routing fields, deterministic error handling | OTel DB Client conventions, resource attribute enrichment, retryable vs terminal classification |

**Scale & Complexity:**

- Primary domain: Cloud Infrastructure / Observability — Snowflake Native App (Marketplace-distributed)
- Complexity level: **High**
- Architectural component count: ~15 major components (2 pipelines, 2 collector SPs, OTLP export layer, config/watermark/metrics state, shared watermark helpers, scheduled-task lifecycle, Streamlit UI with 5+ pages, EAI/networking, secret management, operational logging, governance layer, upgrade machinery, Marketplace packaging)

### Technical Constraints & Dependencies

| Constraint | Source | Impact |
|---|---|---|
| Runs entirely in consumer's Snowflake account | Native App framework | Zero vendor infrastructure; serverless compute only |
| `manifest_version: 2` required | Marketplace compliance | Automated privilege granting; all privileges declared in manifest |
| Dual Python runtime (3.11 Streamlit, 3.13 SPs) | Snowflake platform versions | Separate dependency resolution; test both runtimes |
| Blocked context functions (`CURRENT_ROLE`, `IS_ROLE_IN_SESSION` → NULL) | Native App shared content | Consumer masking/RAP logic must handle NULL branch; app cannot replicate governance |
| No process creation in stored procedures | SP sandbox | No subprocess, multiprocessing, or os.fork(); threading allowed |
| `BatchSpanProcessor` daemon thread incompatible | SP request-response lifecycle | Must use `SimpleSpanProcessor` or explicit `force_flush()`; application-level batching |
| Limited concurrent queries per session | SP default behavior | Independent tasks (not intra-procedure parallelism) for source concurrency |
| Masking policies blocked on Event Tables | Snowflake platform | Custom view required for value-level redaction on Event Table telemetry |
| Streamlit `QUERY_WAREHOUSE` does not support `reference()` | Snowflake Native App framework | Warehouse binding for Streamlit requires `ALTER STREAMLIT SET QUERY_WAREHOUSE`; tasks can use `reference()` directly |
| ACCOUNT_USAGE views don't support the `CHANGES` clause | Snowflake platform | Watermark + configurable overlap window + `QUALIFY ROW_NUMBER()` dedup required for AU sources |
| Event Table `CHANGES` requires 1-day time-travel window | Snowflake platform | Frequent scheduled polling (default 1 min) keeps watermark well inside the window; `WATERMARK_EXPIRED` error caught and watermark reset behind `CURRENT_TIMESTAMP()` for self-heal |
| Custom views over Event Tables require `CHANGE_TRACKING = TRUE` | Snowflake platform | Consumer must set on their view; app cannot `ALTER VIEW` on consumer objects; collector detects the failure and emits `source_change_tracking_disabled` health event with remediation guidance |
| Event Table shared multi-service sink | Snowflake telemetry model | Entity discrimination filter required (positive include-list on `snow.executable.type`) |
| EAI + Network Rules for outbound connectivity | Snowflake networking model | Consumer must approve app specification for OTLP egress |
| Snowflake Anaconda Channel packages only | SP/Streamlit runtime | All dependencies must be available on Anaconda Channel; version pinning critical |
| OTel Python Logs signal in development status | opentelemetry-python SDK | Breaking changes possible; pin SDK versions carefully |

### Cross-Cutting Concerns Identified

| Concern | Scope | Resolution Approach |
|---|---|---|
| **Governance enforcement** | All data access paths | User-selected source model; Snowflake enforces policies at platform layer; app reads governed result |
| **Operational observability** | All pipelines, all sources | `_metrics.pipeline_health` table + Native App event definitions + Streamlit health page |
| **Upgrade safety** | All stateful objects | `CREATE OR ALTER VERSIONED SCHEMA` for stateless; `CREATE IF NOT EXISTS` for stateful; idempotent setup.sql |
| **Marketplace compliance** | Packaging, security, documentation | Tom's release-readiness workflow; security scan; functional review; enforced standards checklist |
| **Error handling & data gaps** | Both pipelines | Transport-level retry (MVP); failure logging; watermark held unchanged on terminal failure for exact retry on next scheduled run; `WATERMARK_EXPIRED` triggers watermark reset (bounded data loss) with self-heal |
| **Secret management** | OTLP endpoint, certificates | Snowflake Secrets only; reference names in config table, never values; rotatable without restart |
| **Platform constraints** | SP environment, Native App sandbox | SimpleSpanProcessor, module-level init, independent scheduled tasks, NULL-tolerant policy handling |

### Key Architectural Decisions

The architecture is anchored by the following 14 major decisions:

1. Dual-pipeline design — both scheduled-task-driven with unified self-managed watermark state
2. User-selected sources (no app-created governed views)
3. Independent serverless scheduled tasks per source (Event Table and ACCOUNT_USAGE alike)
4. Advance-on-success / hold-on-failure watermark semantics — single `MERGE INTO _internal.export_watermarks` only after every chunk of every signal exports successfully; watermark unchanged on any terminal failure (exact retry on next run); `WATERMARK_EXPIRED` self-heal resets the watermark behind `CURRENT_TIMESTAMP()` by a configurable buffer
5. Single OTLP/gRPC endpoint (collector handles routing)
6. Snowpark pushdown-first processing philosophy
7. `to_pandas_batches()` for memory-bounded chunked processing
8. `SimpleSpanProcessor` for SP-compatible synchronous export
9. Module-level OTLP exporter initialization (connection reuse)
10. Entity discrimination via positive include-list (`snow.executable.type`)
11. OTel semantic convention layering (`db.*`, `snowflake.*`)
12. Transport-level retry only (MVP; zero-copy failure tracking post-MVP)
13. Native App event definitions for operational logging
14. Single application role (`app_admin`) — KISS principle

## Starter Template & Project Foundation

### Primary Technology Domain

**Snowflake Native App** — platform-dictated stack with no alternative framework choices. The project was bootstrapped from `snow init --template app_streamlit_python` and has been customized beyond the raw template.

### Project Structure (actual, as of March 2026)

```
snowflake-native-splunk-app/
├── snowflake.yml                    # Snowflake CLI project definition (definition_version: 2)
├── pyproject.toml                   # Root — Python 3.13 dev env (uv, ruff, mypy, pytest)
├── uv.lock                          # Lockfile for root venv
├── README.md                        # Project readme
├── LICENSE
├── app/
│   ├── manifest.yml                 # manifest_version: 2 (privileges, references, event defs)
│   ├── setup.sql                    # Idempotent DDL (app_public, _internal, _metrics)
│   ├── README.md                    # Consumer-facing documentation
│   ├── environment.yml              # Anaconda Channel deps (pinned)
│   ├── pyproject.toml               # Streamlit 3.11 local preview venv (uv)
│   ├── streamlit/                   # [to create] Multi-page Streamlit UI
│   │   ├── main.py
│   │   └── pages/
│   └── python/                      # [to create] SP handler modules
│       ├── event_table_collector.py
│       ├── account_usage_source_collector.py
│       └── otlp_export.py
├── scripts/
│   └── shared_content.sql           # Post-deploy shared data setup
├── tests/                           # [to create] pytest test suite
└── docs/                            # [to create] Developer documentation
```

### Dual-Venv Strategy (project-specific, not from template)

| Venv | Location | Python | Purpose | Package Manager |
|---|---|---|---|---|
| Root | `/.venv` | 3.13 | Backend SP code, OTel SDK, linting, testing | uv |
| Streamlit Preview | `/app/.venv` | 3.11 | Local Streamlit UI preview with mock data | uv |

This ensures IDE autocompletion and linting work correctly for both runtimes while the Snowflake runtime resolves dependencies from `app/environment.yml` (Anaconda Channel).

### Runtime Versions

| Component | Version | Verification |
|---|---|---|
| Python (SPs) | **3.13** GA | 3.9–3.13 GA; 3.13 decommission 2029 |
| Python (Streamlit) | **3.11** (max supported) | 3.8–3.11 supported; 3.11 is default |
| Streamlit library | **1.52.2** (latest on Anaconda) | Verified via live `INFORMATION_SCHEMA.PACKAGES` query 2026-03-15 |
| OTel SDK | **1.38.0** | Pinned in environment.yml |
| gRPC | **1.78.0** | Pinned in environment.yml (latest on Anaconda as of 2026-03-15) |
| Protobuf | **6.33.5** | Pinned in environment.yml (latest on Anaconda as of 2026-03-15) |

### Alignment Decisions

| Item | Decision | Rationale |
|---|---|---|
| **HEC references in manifest** | **Remove** — single OTLP/gRPC endpoint only | PRD and vision converged on single OTLP/gRPC; remote collector handles routing to Splunk backends. `SPLUNK_HEC_SECRET` reference and HEC-related comments to be removed from `manifest.yml`. |
| **Warehouse binding** | **WAREHOUSE reference in manifest** — consumer binds existing warehouse; dual binding for tasks (`reference()`) and Streamlit (`ALTER STREAMLIT SET QUERY_WAREHOUSE`) | Snowflake docs confirm `reference()` is not supported for Streamlit `QUERY_WAREHOUSE`. Tasks can use `WAREHOUSE = reference('consumer_warehouse')`. Custom register callback handles both paths. No `CREATE WAREHOUSE` privilege needed — consumer selects an existing warehouse. Validated via Firecrawl scrape of Snowflake docs + live Snowflake MCP confirming `query_warehouse = null` on deployed Streamlit. |
| **Streamlit version** | **Pin to 1.52.2** (latest on Anaconda) | Verified via live Snowflake Anaconda channel query (2026-03-15). |
| **httpx / tenacity deps** | **Removed from MVP** | MVP uses OTel SDK built-in gRPC retry exclusively. Removed from `environment.yml`; will be added back when post-MVP retry logic is implemented. |

### Streamlit in Native App Constraints

Unsupported features per current Snowflake docs (Native App warehouse runtime):
- Custom components **not supported** (no React embeds, no custom JS widgets)
- `st.cache_data`, `st.cache_resource` **not supported** (session state + manual caching only)
- `st.bokeh_chart` **not supported**
- `st.file_uploader` **not supported** (PEM certificates must be pasted, not uploaded)
- `st.set_page_config` page_title/page_icon **not supported**

Components listed as unsupported in docs but may have updated status — **verify at dev time**:
- `st.image` — docs list as unsupported in Native Apps; standalone SiS may differ; test with stage-loaded bytes
- `st.pyplot` — docs list as unsupported in Native Apps; standalone SiS may support; test at dev time
- `st.scatter_chart` — docs list as unsupported in Native Apps; standalone SiS may support; test at dev time

Primary charting path: Plotly via `st.plotly_chart`, native `st.line_chart` / `st.bar_chart` / `st.area_chart`

### Build & Deploy Tooling

| Command | Purpose |
|---|---|
| `snow app run` | Deploy to dev package + create/upgrade dev app (no versioning) |
| `snow app version create` | Create versioned release for testing/production |
| `snow app open` | Open Streamlit UI in browser |
| `DEBUG_MODE = TRUE` | Direct DDL iteration against dev app (set via `debug: true` in snowflake.yml) |

Multi-package promotion: dev (`INTERNAL`) → scan (`EXTERNAL`, security scan) → test (`INTERNAL`, E2E) → prod (`EXTERNAL`, Marketplace)

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Configuration storage model | **Hybrid** — manifest references for Snowflake objects, config table for app settings | Framework requires references for consumer objects; config table stores non-Snowflake values (URLs, flags, intervals) |
| D2 | OTLP authentication model | **TLS only (MVP)** — default CA bundle + optional custom PEM | MVP destination is OTel collector (not direct-to-Splunk); bearer token auth deferred post-MVP |
| D3 | OTLP exporter instance topology | **3 separate exporters** (Span, Metric, Log), module-level init, verify TCP limits during dev | Standard OTel pattern; gRPC HTTP/2 multiplexing keeps connections low; least-effort fallback if limits hit |
| D4 | Streamlit state management | **`st.session_state` as cache + config table as durable store** | Streamlit best practice; responsive UI; explicit save pattern; reduces DB round-trips |
| D5 | Testing approach | **Hybrid** — unit mocks + integration against dev schema + fully automated E2E via Cursor agents | Playwright CLI for Snowsight automation and SSH for collector verification |

**Formalized Architectural Decisions:**

| # | Decision | Choice | Source |
|---|---|---|---|
| V1 | Pipeline architecture | Dual-pipeline: both scheduled-task-driven with per-source self-managed watermark. Event Tables use `CHANGES(INFORMATION => APPEND_ONLY) AT(TIMESTAMP => :wm) END(TIMESTAMP => :batch_end)`. ACCOUNT_USAGE views use `WHERE ts > :wm - overlap AND ts <= :batch_end` + `QUALIFY ROW_NUMBER()` dedup | `evt_architecture_adversarial_review.md` Part 3 |
| V2 | Data governance model | User-selected sources only — no app-created governed views | Vision §7A, PRD §2.2 |
| V3 | Task architecture | Independent serverless scheduled tasks — one per enabled source (Event Table and ACCOUNT_USAGE alike), source-specific schedule, default 1 minute for Event Table sources | Vision §7.6, `evt_architecture_adversarial_review.md` Part 3 |
| V4 | Watermark advancement | Advance-on-success / hold-on-failure — single atomic `MERGE INTO _internal.export_watermarks` only after every signal and chunk exports successfully; on any terminal failure the watermark is unchanged so the next scheduled invocation replays the exact same `[watermark, batch_end)` window; on time-travel `WATERMARK_EXPIRED` the watermark is reset to `CURRENT_TIMESTAMP() - event_table.watermark_reset_buffer_seconds` | `evt_architecture_adversarial_review.md` Part 3 |
| V5 | OTLP transport | Single OTLP/gRPC endpoint — remote collector handles routing to Splunk backends | Vision §7.9, PRD §4.1 |
| V6 | Data processing philosophy | Snowpark pushdown-first — all relational work (filter, project, dedup) pushed to Snowflake engine; Python only serializes | Vision §7.11, §7.12 |
| V7 | Memory management | `to_pandas_batches()` for chunked processing — bounded memory, no global `collect()` | Vision §7.11 |
| V8 | OTel span processor | `SimpleSpanProcessor` (synchronous) — `BatchSpanProcessor` daemon thread incompatible with SP lifecycle | Vision §Technical Prerequisites |
| V9 | Network client lifecycle | Module-level OTLP exporter initialization — gRPC channel persists across task invocations via Snowflake module caching | Vision §7.12 BP-2, BP-3 |
| V10 | Event Table entity filtering | Positive include-list on `RESOURCE_ATTRIBUTES:"snow.executable.type"` — values: `procedure`, `function`, `query`, `sql` | Vision §7B, Entity Discrimination Strategy |
| V11 | OTel semantic conventions | Layered: `db.*` (Database Client, stable) + `snowflake.*` (custom namespace) + convention-transparent relay of original attributes | Vision §7B, OTel Conventions Research |
| V12 | Failure handling (MVP) | Transport-level retry only via the built-in Python OTLP/gRPC exporter retry logic; retry is additionally bounded by the configured exporter timeout (`_EXPORT_TIMEOUT_S = 10` in this project). No application-level retry loop in MVP; on exhaustion: log failure + advance pipeline | Vision §7.2 |
| V13 | Operational logging | Native App event definitions — structured logs to consumer's account-level event table; queryable via Snowsight | Vision §3.5, PRD §3.5 |
| V14 | RBAC model | Single role: `app_admin` — KISS principle; admin shares dashboards via Splunk, not in-app viewer roles | Vision §1, PRD §1.2 |

### Data Architecture

**Configuration Storage (D1 — Hybrid):**

| Setting Category | Storage | Resolution |
|---|---|---|
| Consumer warehouse | Manifest reference (`CONSUMER_WAREHOUSE`) | `REFERENCE('CONSUMER_WAREHOUSE')` in task DDL; `ALTER STREAMLIT` for Streamlit binding |
| Event Table reference | Manifest reference (`CONSUMER_EVENT_TABLE`) | `REFERENCE('CONSUMER_EVENT_TABLE')` in SQL |
| EAI reference | Manifest reference (`SPLUNK_EAI`) | `REFERENCE('SPLUNK_EAI')` in SQL |
| PEM cert Secret reference | Manifest reference (optional, `required_at_setup: false`) | Resolve Secret content via reference at runtime |
| OTLP endpoint URL | `_internal.config` (key: `otlp.endpoint`) | Query config table at pipeline startup |
| Per-source custom view FQNs | `_internal.config` (key: `source.<name>.view_fqn`) | Query config table; used in collector SQL (resolved via `REFERENCE(...)`) and scheduled-task DDL |
| Pack enablement flags | `_internal.config` (key: `pack_enabled.<pack_name>`) | Query config table; drives task create/drop |
| Per-source batch size and interval | `_internal.config` (keys: `source.<name>.batch_size`, `source.<name>.poll_interval_seconds`) | Query config table; per-source operational settings for MVP |
| Per-source overlap window (ACCOUNT_USAGE only) | `_internal.config` (key: `source.<name>.overlap_minutes`) | Configurable overlap for AU watermark dedup; default = documented max latency × 1.1 |
| Event Table initial seed buffer | `_internal.config` (key: `event_table.initial_seed_buffer_seconds`) | Seconds behind `CURRENT_TIMESTAMP()` for the first-run watermark seed when no row exists yet for a source; default `60` to align with the 1-minute scheduled cadence so the first run captures exactly one cadence of preceding telemetry instead of a zero-width window |
| Event Table watermark reset buffer | `_internal.config` (key: `event_table.watermark_reset_buffer_seconds`) | Seconds behind `CURRENT_TIMESTAMP()` the watermark is reset to on `WATERMARK_EXPIRED` recovery; default `60` |
| Event Table SPAN_EVENT cap | `_internal.config` (key: `event_table.max_span_events_per_run`) | Soft cap on SPAN_EVENT rows indexed in memory per run for SPAN ↔ SPAN_EVENT correlation |
| Watermark state (unified) | `_internal.export_watermarks` (dedicated table) | Per-source (`source_name`) watermark tracking for both Event Table and ACCOUNT_USAGE pipelines |
| Pipeline health metrics | `_metrics.pipeline_health` (dedicated table) | Per-run operational metrics |

**Schema Topology:**

| Schema | Type | Purpose | Upgrade Behavior |
|---|---|---|---|
| `app_public` | Versioned (`CREATE OR ALTER VERSIONED SCHEMA`) | Procedures, Streamlit, grants | Recreated on upgrade |
| `_internal` | Stateful (`CREATE SCHEMA IF NOT EXISTS`) | `config`, `export_watermarks`, collector SPs | Persists across upgrades |
| `_metrics` | Stateful | `pipeline_health` operational metrics | Persists across upgrades |

### Authentication & Security

**OTLP Transport Security (D2):**

| Aspect | MVP | Post-MVP |
|---|---|---|
| Transport | gRPC over TLS (always) | Same |
| CA trust | Snowflake default CA bundle (Mozilla/certifi) | Same |
| Custom PEM cert | Optional — consumer creates Snowflake Secret with PEM, binds via manifest reference; app reads PEM bytes for `ssl_channel_credentials(root_certificates=pem_bytes)` | Same |
| Bearer token auth | Not supported — MVP destination is OTel collector (already configured with Splunk tokens) | `SPLUNK_OTLP_SECRET` manifest reference for direct-to-Splunk-Observability-Cloud export |
| Manifest cleanup | Remove `SPLUNK_HEC_SECRET` reference; optionally remove or keep `SPLUNK_OTLP_SECRET` with `required_at_setup: false` | Add `SPLUNK_OTLP_SECRET` as active reference |

### Pipeline Architecture

**Incremental Read Primitive by Source Type:**

| User Selection | Read Primitive | Notes |
|---|---|---|
| Default Event Table (`SNOWFLAKE.TELEMETRY.EVENTS`) | `SELECT <projection> FROM <source_fqn> CHANGES(INFORMATION => APPEND_ONLY) AT(TIMESTAMP => :watermark) END(TIMESTAMP => :batch_end) WHERE RECORD_TYPE = :signal AND UPPER(RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING) IN (:include_list)` | Event Tables always have change tracking enabled |
| Consumer's custom view over Event Table | Same `CHANGES` clause against the view FQN | Consumer must run `ALTER VIEW <fqn> SET CHANGE_TRACKING = TRUE`; the app detects the failure case and emits `source_change_tracking_disabled` health with remediation guidance (the app cannot `ALTER VIEW` on consumer-owned objects) |
| Default ACCOUNT_USAGE view | `SELECT <projection> FROM <source_fqn> WHERE :timestamp_col > :watermark - INTERVAL :overlap_minutes AND :timestamp_col <= :batch_end QUALIFY ROW_NUMBER() OVER (PARTITION BY :natural_key ORDER BY :timestamp_col DESC) = 1 LIMIT :batch_size` | `CHANGES` is not supported on ACCOUNT_USAGE views; overlap re-scans absorb trailing ACCOUNT_USAGE latency; `QUALIFY` removes previously exported rows |
| Consumer's custom view over ACCOUNT_USAGE | Same watermark + overlap + `QUALIFY` pattern | Requires consumer-provided natural key and timestamp column metadata in `_internal.config` |

**Unified Watermark Orchestration:**

```
_internal.export_watermarks
  (source_name, watermark_ts, last_success_at, last_failure_reason, last_run_id)
       │
       ├── Event Table pipelines ── CHANGES(...) AT/END(TIMESTAMP)
       └── ACCOUNT_USAGE pipelines ── WHERE ts BETWEEN watermark-overlap AND batch_end + QUALIFY

  On success of the run:  MERGE ... SET watermark_ts = batch_end
  On terminal failure:    watermark unchanged  →  exact retry on next scheduled run
  On WATERMARK_EXPIRED:   MERGE ... SET watermark_ts = CURRENT_TIMESTAMP() - buffer
```

Shared helpers live in `app/python/watermark.py` (`read_watermark`, `update_watermark`, `reset_watermark`) and are used by both collector SPs so advance-on-success / hold-on-failure semantics are identical across pipelines.

**OTLP Exporter Topology (D3):**

```
Event Table Collector SP (module-level init):
├── OTLPSpanExporter(endpoint=otlp_url, credentials=tls_creds)     ← 1 gRPC channel
├── OTLPMetricExporter(endpoint=otlp_url, credentials=tls_creds)   ← 1 gRPC channel
└── OTLPLogExporter(endpoint=otlp_url, credentials=tls_creds)      ← 1 gRPC channel
                                                                     = 3 TCP connections

ACCOUNT_USAGE Collector SP (module-level init):
└── OTLPLogExporter(endpoint=otlp_url, credentials=tls_creds)      ← 1 gRPC channel
                                                                     = 1 TCP connection per sandbox
```

- Standard OTel pattern — 3 separate exporters per signal type
- Module-level initialization — gRPC channels persist across task invocations within the same sandbox
- **TCP connection model**: Each serverless task invocation runs in its own isolated sandbox. Module-level init means 1 exporter instance per sandbox lifetime. N concurrent ACCOUNT_USAGE tasks = N separate sandboxes, each with 1 TCP connection — connections do NOT multiply within a single sandbox. The TCP limit is per sandbox, not per account.
- **Event Table collector**: 3 exporters in one sandbox = 3 TCP connections. Verify during dev that this stays within sandbox limits.
- **Least-effort fallback if limit hit**: serialize exports sequentially through a single exporter

### Frontend Architecture (Streamlit)

**State Management Pattern (D4):**

```
┌─ Page Load ─────────────────────────────────────────────┐
│ if "config_loaded" not in st.session_state:             │
│     rows = session.sql("SELECT * FROM _internal.config")│
│     for row in rows:                                    │
│         st.session_state[row.key] = row.value           │
│     st.session_state["config_loaded"] = True            │
└─────────────────────────────────────────────────────────┘

┌─ User Interaction ──────────────────────────────────────┐
│ Widget changes → update st.session_state (immediate)    │
│ "Save" button → persist session_state → config table    │
│ "Discard" → reload from config table → reset session    │
└─────────────────────────────────────────────────────────┘

┌─ Cross-Page Navigation ────────────────────────────────┐
│ st.session_state persists across pages (Streamlit native)│
│ Config table is the durable backing store               │
│ "Unsaved changes" indicator when session ≠ config table │
└─────────────────────────────────────────────────────────┘
```

### Infrastructure & Testing

**Testing Strategy (D5 — Hybrid with Cursor Agent Automation):**

| Layer | Tool | Scope | Automation |
|---|---|---|---|
| **(a) Unit/mock** | pytest + Snowpark local testing | SP logic, data transforms, OTel mapping, config parsing | CI — every commit |
| **(b) Integration** | pytest + `snow sql` against dev schema | SP execution, watermark advance/hold/reset, `CHANGES` behavior, task lifecycle | CI — pre-merge against dev account |
| **(c) E2E — Snowflake side** | Cursor agent + Playwright CLI | `snow app run` → Snowsight UI automation: install, configure, activate, verify health page | Pre-release — fully automated via Cursor |
| **(c) E2E — Splunk side** | Cursor agent + SSH to OTel collector | Connect to collector instance, query logs, verify exported telemetry format, OTel conventions, attribute completeness | Pre-release — fully automated via Cursor |

E2E is fully automated — Cursor agents drive Playwright CLI (minimizing token usage) for Snowsight browser automation and SSH into the OTel collector to verify exported telemetry end-to-end.

### Decision Impact Analysis

**Implementation Sequence:**

1. **D1 (Config storage)** → First: `_internal.config` and `_internal.export_watermarks` schemas + manifest reference callbacks must exist before any pipeline code
2. **Watermark helpers** → Second: `app/python/watermark.py` (`read_watermark`, `update_watermark`, `reset_watermark`) — shared advance-on-success / hold-on-failure primitives used by both collectors
3. **D3 (Exporter topology)** → Third: OTLP export module with 3 exporters, TLS setup from D2
4. **V6, V7, V8** → Fourth: collector SPs using Snowpark pushdown + `to_pandas_batches()` + `SimpleSpanProcessor`; Event Table collector uses `CHANGES`, ACCOUNT_USAGE collector uses watermark + overlap + `QUALIFY`
5. **D4 (Streamlit state)** → Fifth: UI reads config via session_state pattern
6. **D5 (Testing)** → Ongoing: unit tests from day 1, integration tests as SPs land, E2E at feature-complete

**Cross-Component Dependencies:**

| Decision | Depends On | Affects |
|---|---|---|
| D1 (Config hybrid) | Manifest reference definitions | All pipelines (read config at startup), Streamlit UI (read/write config) |
| D2 (TLS only) | D1 (PEM secret reference) | OTLP exporter initialization (D3) |
| D3 (3 exporters) | D2 (TLS credentials) | Event Table collector, ACCOUNT_USAGE collector |
| V4 (Watermark semantics) | D1 (`_internal.export_watermarks` schema) | Both collector SPs — shared `app/python/watermark.py` helpers |
| D4 (Session state) | D1 (config table schema) | All Streamlit pages |
| D5 (Testing) | All above | Release quality gates |

## Implementation Patterns & Consistency Rules

### Project Foundation Patterns

**Dual-Venv Strategy:**

| Venv | Location | Python | Purpose | Package Manager |
|---|---|---|---|---|
| Root | `/.venv` | 3.13 | Backend SP code, OTel SDK, linting (ruff), type checking (mypy), testing (pytest) | **uv** |
| Streamlit Preview | `/app/.venv` | 3.11 | Local Streamlit UI preview with mock data | **uv** |

**Dependency Pinning:**
- `app/environment.yml` — Snowflake Anaconda Channel runtime deps (authoritative for Snowflake runtime)
- `pyproject.toml` (root) — IDE/dev deps mirroring runtime pins for autocompletion
- `app/pyproject.toml` — Streamlit preview deps (3.11 subset)
- `uv.lock` — lockfile for root venv reproducibility

**Multi-Package Strategy:**
- `splunk_observability_dev_pkg` (INTERNAL) — fast iteration, `debug: true`
- `splunk_observability_scan_pkg` (EXTERNAL) — pre-validate security scan
- `splunk_observability_test_pkg` (INTERNAL) — E2E integration via internal listing
- `splunk_observability_prod_pkg` (EXTERNAL) — Marketplace publication

**Schema Topology (from `setup.sql`):**

| Schema | Type | DDL | Purpose |
|---|---|---|---|
| `app_public` | Versioned | `CREATE OR ALTER VERSIONED SCHEMA` | Procedures, Streamlit, grants — recreated on upgrade |
| `_internal` | Stateful | `CREATE SCHEMA IF NOT EXISTS` | `config`, `export_watermarks`, collector SPs — persists across upgrades |
| `_metrics` | Stateful | `CREATE SCHEMA IF NOT EXISTS` | `pipeline_health` operational metrics — persists across upgrades |

### Naming Patterns

**Snowflake Object Naming:**

| Object Type | Convention | Example | Anti-Pattern |
|---|---|---|---|
| Schemas (app-internal) | `_lowercase` prefix | `_internal`, `_metrics` | `Internal`, `INTERNAL` |
| Schemas (consumer-facing) | `snake_case` | `app_public` | `AppPublic` |
| Tables | `snake_case` | `pipeline_health`, `export_watermarks` | `PipelineHealth` |
| Columns | `UPPER_CASE` (Snowflake convention) | `CONFIG_KEY`, `METRIC_VALUE` | `config_key` in DDL |
| Stored procedures | `snake_case` | `event_table_collector` | `EventTableCollector` |
| Tasks | `_splunk_obs_task_<source_name>` | `_splunk_obs_task_query_history` | `task_1` |
| Application role | `snake_case` | `app_admin` | `APP_ADMIN` |

**Python Code Naming (PEP 8 — enforced by ruff):**

| Element | Convention | Example |
|---|---|---|
| Modules | `snake_case.py` | `event_table_collector.py`, `otlp_grpc.py` |
| Functions | `snake_case` | `collect_event_table()`, `export_otlp_batch()` |
| Classes | `PascalCase` | `PipelineHealthRecorder`, `OtlpExportConfig` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_BATCH_SIZE`, `DEFAULT_POLL_INTERVAL` |
| Variables | `snake_case` | `batch_count`, `export_latency_ms` |

**Config Table Key Naming:**

| Category | Key Pattern | Example |
|---|---|---|
| OTLP settings | `otlp.<setting>` | `otlp.endpoint`, `otlp.pem_secret_ref` |
| Pack flags | `pack_enabled.<pack_name>` | `pack_enabled.distributed_tracing` |
| Source settings | `source.<source_name>.<setting>` | `source.query_history.poll_interval_seconds` |
| ACCOUNT_USAGE overlap window | `source.<source_name>.overlap_minutes` | `source.query_history.overlap_minutes` (default: 50) |
| Source view FQNs | `source.<source_name>.view_fqn` | `source.query_history.view_fqn` |
| Source type | `source.<source_name>.source_type` | Value: `default` or `custom` |
| Event Table collector tuning | `event_table.<setting>` | `event_table.initial_seed_buffer_seconds` (default: `60`), `event_table.watermark_reset_buffer_seconds` (default: `60`), `event_table.max_span_events_per_run` (default: `50000`) |

This dotted format is the canonical config-key convention for the project. Older mixed examples such as `otlp_endpoint`, `source:<name>:view_fqn`, `pack_enabled:<pack_name>`, or `export_batch_size` are deprecated planning-era artifacts and must not be used in new stories or implementation code.

**OTel Attribute Naming:**

| Layer | Namespace | Convention | Example |
|---|---|---|---|
| OTel standard (DB) | `db.*` | Stable, lowercase dot-separated | `db.system.name`, `db.namespace` |
| Snowflake custom | `snowflake.*` | Lowercase dot-separated | `snowflake.warehouse.name`, `snowflake.query.id` |
| OTLP resource | `service.*`, `cloud.*` | OTel resource conventions | `service.name`, `cloud.provider` |
| Original pass-through | `snow.*` | Preserved as-is from Event Table | `snow.executable.type` |

### Structure Patterns

**Python Module Organization (flat layout — `snowflake.yml` lists every file explicitly):**

```
app/python/
├── event_table_collector.py      # Event Table collector SP — CHANGES + watermark, per-signal SELECTs
├── account_usage_collector.py    # ACCOUNT_USAGE collector SP — watermark + overlap + QUALIFY ROW_NUMBER()
├── watermark.py                  # Shared: read_watermark / update_watermark / reset_watermark against _internal.export_watermarks
├── otlp_export.py                # Module-level OTLP exporter singletons (Span / Metric / Log), TLS enforcement
├── export_result.py              # ExportOutcome dataclass + gRPC status classification (retryable vs terminal)
├── pipeline_telemetry.py         # Structured logging + _metrics.pipeline_health inserts
├── span_mapper.py                # SPAN + SPAN_EVENT rows → OTel ReadableSpan (in-memory correlation)
├── log_mapper.py                 # LOG row → OTel LogData
├── metric_mapper.py              # METRIC row → OTel MetricsData
├── account_usage_mapper.py       # ACCOUNT_USAGE row → OTel LogData
├── telemetry_constants.py        # COL_* column-name constants + signal filters
├── secret_reader.py              # PEM secret reader via manifest reference
├── endpoint_parse.py             # OTLP endpoint validation/parsing
└── config_reader.py              # _internal.config accessor with typed getters
```

The flat layout is mandatory — Snowflake Native App stages do not auto-discover files; every module must have an explicit `src → dest` entry in `snowflake.yml` under `artifacts`. Adding or renaming any module requires updating `snowflake.yml` in the same change.

**Streamlit Page Organization (from UX Design Specification — `st.navigation()` API):**

Sidebar order (exact labels and icons from Figma design):

| # | Sidebar Label | Icon | File | Visibility |
|---|---|---|---|---|
| 1 | **Getting started** | 🚀 | `pages/getting_started.py` | Until all 4 onboarding tasks complete AND user navigates away; then removed permanently |
| 2 | **Observability health** | 📊 | `pages/observability_health.py` | Always (home page after onboarding) |
| 3 | **Telemetry sources** | 💾 | `pages/telemetry_sources.py` | Always |
| 4 | **Splunk settings** | ⚙️ | `pages/splunk_settings.py` | Always |
| 5 | **Data governance** | 🛡️ | `pages/data_governance.py` | Always |

Sidebar header: **"Splunk Observability"** / **"for Snowflake"**. Footer: **"About"** link that opens a `st.dialog` modal with app version, build info, documentation links, etc.

```
app/streamlit/
├── main.py                            # Entry point — st.navigation() router
├── pages/
│   ├── getting_started.py             # 🚀 Tile hub with 4 task cards + drill-down
│   ├── observability_health.py        # 📊 Helicopter view: dest health, KPIs, throughput, errors
│   ├── telemetry_sources.py           # 💾 Pack selection, st.data_editor source table
│   ├── splunk_settings.py             # ⚙️ Export settings tab (OTLP endpoint, PEM cert, test)
│   └── data_governance.py             # 🛡️ Read-only enabled sources with governance messages
└── components/
    ├── __init__.py
    ├── getting_started_tile.py        # Reusable task card (completed/pending states)
    ├── connection_card.py             # OTLP endpoint + cert + test connection
    ├── health_cards.py                # KPI metric cards for observability health
    ├── source_table.py                # st.data_editor source config with category headers
    ├── empty_state.py                 # Reusable empty state pattern
    └── config_loader.py               # session_state ↔ config table bridge
```

**Reusable Composed Components (from UX spec — not a separate package, implemented as shared helpers):**

| Component | Purpose | Implementation |
|---|---|---|
| Getting Started Tile | Task card with completed/pending states and drill-down | `st.container(border=True)` + columns + `st.page_link` |
| Connection Card | OTLP endpoint + cert + test + save inside Export settings tab | `st.container(border=True)` + `st.text_input` + `st.text_area` + `st.button` |
| Empty State | Consistent "no data yet" UI across pages | `st.container` + centered text + icon |
| Source Table | `st.data_editor` with category headers, status, freshness, editable intervals | `st.data_editor` + `column_config` |
| Health KPI Row | `st.metric` cards in `st.columns` for helicopter view | `st.columns` + `st.metric` with delta |

**Test Organization:**

```
tests/
├── unit/
│   ├── test_span_mapper.py                 # SPAN + SPAN_EVENT → ReadableSpan
│   ├── test_log_mapper.py                  # LOG row → LogData
│   ├── test_metric_mapper.py               # METRIC row → MetricsData
│   ├── test_account_usage_mapper.py        # ACCOUNT_USAGE row → LogData
│   ├── test_config_reader.py               # Typed _internal.config accessors
│   ├── test_pipeline_telemetry.py          # Structured logs + _metrics.pipeline_health writes
│   ├── test_export_result.py               # gRPC status classification (retryable vs terminal)
│   ├── test_secret_reader.py               # PEM secret reference resolution
│   └── test_endpoint_parse.py              # OTLP endpoint validation
├── integration/
│   ├── test_event_table_collector.py       # CHANGES-based incremental reads, per-signal SELECTs
│   ├── test_account_usage_collector.py     # Watermark + overlap + QUALIFY dedup
│   ├── test_watermark.py                   # advance-on-success / hold-on-failure / WATERMARK_EXPIRED self-heal
│   ├── test_scheduled_tasks.py             # Task lifecycle, schedule updates, suspend/resume
│   └── test_otlp_export.py                 # Live OTLP/gRPC against dev collector
└── e2e/
    ├── test_install_configure.py           # Playwright MCP — Snowsight install + Getting Started flow
    └── test_export_verification.py         # SSH to collector + Splunk Obs Cloud REST verification
```

### Format Patterns

**Pipeline Health Metric Names:**

| Metric Name | Type | When Recorded |
|---|---|---|
| `rows_collected` | NUMBER | End of each collector run |
| `rows_exported` | NUMBER | End of each export batch |
| `rows_failed` | NUMBER | When transport retries exhaust |
| `export_latency_ms` | NUMBER | Per-batch export duration |
| `error_count` | NUMBER | Errors per run |
| `source_lag_seconds` | NUMBER | `CURRENT_TIMESTAMP()` minus watermark (exported high-water mark) |
| `watermark_value` | TIMESTAMP_LTZ | Current value from `_internal.export_watermarks` after the run |
| `watermark_reset` | NUMBER | `1` if this run reset the watermark due to `WATERMARK_EXPIRED`, else absent |

**Structured Log Format (Native App Event Definitions):**

```python
logger.info("Pipeline run complete", extra={
    "pipeline": "event_table_collector",
    "source": source_name,
    "rows_collected": row_count,
    "rows_exported": exported_count,
    "duration_ms": duration,
    "run_id": run_id,
})
```

| Field | Type | Required | Description |
|---|---|---|---|
| `pipeline` | string | Yes | `event_table_collector` or `account_usage_source_collector` |
| `source` | string | Yes | Source identifier |
| `run_id` | string | Yes | Unique ID per pipeline invocation (UUID) |
| `rows_collected` | int | On success | Rows read from source |
| `rows_exported` | int | On success | Rows successfully exported |
| `rows_failed` | int | On failure | Rows that failed export |
| `duration_ms` | int | Yes | Total run duration |
| `error_code` | string | On error | For OTLP export events, the raw upstream exporter or gRPC code name when available (for example `FAILURE`, `UNAVAILABLE`, `PERMISSION_DENIED`) |
| `error_message` | string | On error | Human-readable error detail |

For OTLP export operational events, build the structured log payload in one caller-side helper and emit it through Python `logging`. The low-level exporter wrapper should return structured outcomes and avoid duplicating `pipeline` / `source` / `run_id` logging that only callers know.

**Operational Code Taxonomy:**

**OTLP Export Status Codes (use raw upstream names; do not invent aliases):**

| Surface | Code(s) | Meaning |
|---|---|---|
| Public exporter result enum | `SUCCESS`, `FAILURE` | The only result codes guaranteed by the Python OTLP exporter public API |
| Directly observed gRPC status | `OK`, `CANCELLED`, `UNKNOWN`, `INVALID_ARGUMENT`, `DEADLINE_EXCEEDED`, `NOT_FOUND`, `ALREADY_EXISTS`, `PERMISSION_DENIED`, `RESOURCE_EXHAUSTED`, `FAILED_PRECONDITION`, `ABORTED`, `OUT_OF_RANGE`, `UNIMPLEMENTED`, `INTERNAL`, `UNAVAILABLE`, `DATA_LOSS`, `UNAUTHENTICATED` | Use `grpc.RpcError.code().name` verbatim only when surfaced to app code |
| Upstream retryable direct gRPC status subset | `CANCELLED`, `DEADLINE_EXCEEDED`, `RESOURCE_EXHAUSTED`, `ABORTED`, `OUT_OF_RANGE`, `UNAVAILABLE`, `DATA_LOSS` | Mirrors `_RETRYABLE_ERROR_CODES` in the upstream exporter |

For OTLP export operational logs and `_metrics.pipeline_health` metadata, store the raw upstream code string in `error_code` when available. If no upstream code is exposed, leave `error_code` null and rely on a sanitized `error_message`.

**Non-OTLP Pipeline / Configuration Codes:**

| Code | Category | Example |
|---|---|---|
| `WATERMARK_EXPIRED` | Pipeline | `CHANGES` end-timestamp older than 1-day time-travel window; watermark reset to `CURRENT_TIMESTAMP() - event_table.watermark_reset_buffer_seconds` and run skipped for this cycle |
| `CHANGE_TRACKING_DISABLED` | Pipeline | Custom Event Table view missing `CHANGE_TRACKING = TRUE`; `CHANGES` unsupported — source paused and diagnostic surfaced to consumer |
| `SOURCE_UNAVAILABLE` | Pipeline | ACCOUNT_USAGE view query failed (latency, auth, or view missing) |
| `CONFIG_MISSING` | Configuration | Required config key not found |
| `REFERENCE_UNBOUND` | Configuration | Manifest reference not yet bound by consumer |

### Process Patterns

**Config Loading (every SP handler):**

```python
def handler(session, *args):
    config = load_config(session)
    otlp_endpoint = config.get("otlp.endpoint")
    if not otlp_endpoint:
        log_error("CONFIG_MISSING", "otlp.endpoint not configured")
        record_health(session, source, "error_count", 1, {"error_code": "CONFIG_MISSING"})
        return "ERROR: otlp.endpoint not configured"
```

**Health Recording (end of every pipeline run):**

```python
def record_run_metrics(session, pipeline_name, source_name, metrics: dict):
    for metric_name, metric_value in metrics.items():
        session.sql("""
            INSERT INTO _metrics.pipeline_health
            (pipeline_name, source_name, metric_name, metric_value, metadata)
            VALUES (?, ?, ?, ?, ?)
        """, params=[pipeline_name, source_name, metric_name, metric_value,
                     json.dumps(metadata)]).collect()
```

**Watermark Expiry Self-Heal (Event Table collector):**

```
try:
    batch_end = CURRENT_TIMESTAMP()
    df = session.sql(f"""
        SELECT ... FROM <source>
        CHANGES(INFORMATION => APPEND_ONLY)
          AT(TIMESTAMP => '{watermark}'::TIMESTAMP_LTZ)
          END(TIMESTAMP => '{batch_end}'::TIMESTAMP_LTZ)
        WHERE <entity/signal filters>
    """)
except SnowparkSQLException as e:
    if "Time travel data is not available" in str(e):
        # 1-day time-travel window expired — reset watermark to safe buffer behind now,
        # hold this run, record WATERMARK_EXPIRED, resume next scheduled run.
        reset_watermark(session, source, CURRENT_TIMESTAMP() - INTERVAL reset_buffer_seconds)
        record_health(session, source, "watermark_reset", 1,
                      {"error_code": "WATERMARK_EXPIRED"})
        return "WATERMARK_RESET"
    raise
```

Watermark advances only on full export success (see V4). On terminal transport failure the watermark is held unchanged so the next scheduled run retries the exact same `[watermark, batch_end]` window.

### Enforcement Guidelines

**All AI Agents MUST follow these Cursor rules:**

| Rule File | Scope | Key Mandates |
|---|---|---|
| `.cursor/rules/python-coding-rules.mdc` | All Python code | Prefer functions + dataclasses; flat over nested; EAFP; duck typing; composition over inheritance; Protocols for abstraction |
| `.cursor/rules/python-coding-standards-rules.mdc` | All Python code | ruff linting (full rule set); mypy type checking; no bare `except`; no mutable defaults; no `print()` in production; uv for deps; pre-commit hooks |
| `.cursor/rules/snowflake-snowpark-rules.mdc` | SP handler code | Pushdown-first; no `collect()` on large data; chain DataFrame ops; `to_pandas_batches()` for serialization only; `@sproc` with type hints; module-level init |
| `.cursor/rules/snowflake-sql-rules.mdc` | All SQL | No `SELECT *` in production; sargable predicates; early filters; window functions over self-joins; `QUALIFY`; CTEs for clarity |
| `.cursor/rules/streamlit_snowflake_design_rules.mdc` | All Streamlit UI code | Target Streamlit 1.51.0+; native components only; no external CSS/fonts/scripts; `column_config` for tables; `st.session_state` for state; images from stages only; 32MB message limit |

**Additional mandatory patterns for this project:**

1. Never create or own Snowflake views — the app reads directly from consumer-selected sources (default Event Table / ACCOUNT_USAGE views, or consumer-owned custom views with `CHANGE_TRACKING = TRUE`)
2. Initialize OTLP exporters at module scope, never inside handler functions
3. Use `session.sql_simplifier_enabled = True` at the start of every SP handler
4. Advance watermarks **only** on full export success via `MERGE INTO _internal.export_watermarks` — never advance on partial batches or terminal transport failures (hold watermark for exact retry on next scheduled run)
5. For Event Tables, always use the `CHANGES(INFORMATION => APPEND_ONLY) AT(TIMESTAMP => :watermark) END(TIMESTAMP => :batch_end)` clause with an explicit `batch_end` captured at run start; for ACCOUNT_USAGE (which does not support `CHANGES`), use `WHERE timestamp_col > :watermark - INTERVAL :overlap AND timestamp_col <= :batch_end` plus `QUALIFY ROW_NUMBER() OVER (PARTITION BY natural_key ORDER BY timestamp_col DESC) = 1`
6. Always wrap the Event Table `CHANGES` read in a `WATERMARK_EXPIRED` handler that resets the watermark to `CURRENT_TIMESTAMP() - event_table.watermark_reset_buffer_seconds` and records `watermark_reset=1` in `_metrics.pipeline_health`
7. Resolve manifest references via `REFERENCE('ref_name')` in SQL, not hardcoded object names
8. Record pipeline health metrics at the end of every SP run (success or failure), including `watermark_value` and `source_lag_seconds`
9. Use structured logging with mandatory fields (pipeline, source, run_id, duration_ms); use raw upstream OTLP/gRPC code names in `error_code` — never invent aliases
10. Use the config key naming convention (`otlp.*`, `pack_enabled.*`, `source.*.*`, `event_table.*`)
11. Follow the Getting Started → Observability health → Telemetry sources → Splunk settings → Data governance sidebar order
12. Use `st.navigation()` API for page routing (not `pages/` folder convention alone)
13. Every new file under `app/python/` or `app/streamlit/utils/` must have an explicit `src → dest` entry in `snowflake.yml` in the same change — the Native App stage does not auto-discover files

## Project Structure & Boundaries

*Complete directory structure documented in Starter Template section above. This section defines architectural boundaries, data flow, and requirement mapping.*

### Architectural Boundaries

```
┌─────────────────────────── Consumer's Snowflake Account ───────────────────────────┐
│                                                                                      │
│  ┌── Consumer Objects (user-selected sources) ──┐  ┌── App Objects ──────────────┐  │
│  │ SNOWFLAKE.TELEMETRY.EVENTS (default ET)      │  │ app_public (versioned)      │  │
│  │ consumer_db.schema.custom_et_view            │  │   main (Streamlit)          │  │
│  │   (CHANGE_TRACKING = TRUE required)          │  │   register_single_callback  │  │
│  │ SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY (AU)    │  │   collector SPs             │  │
│  │ consumer_db.schema.custom_au_view            │  │                             │  │
│  └───────────────────────────────────────────────┘  │ _internal                   │  │
│         ↓                                            │   config (KV settings)      │  │
│    SELECT via REFERENCE(...) using                   │   export_watermarks         │  │
│    CHANGES() for Event Tables,                       │     (unified high-water mark│  │
│    watermark+overlap+QUALIFY for ACCOUNT_USAGE       │      per source)            │  │
│                                                      │   scheduled tasks (per src) │  │
│  ┌── Manifest References ──────────────────────┐    │                             │  │
│  │ CONSUMER_EVENT_TABLE → bound to ET/view      │    │ _metrics                    │  │
│  │ SPLUNK_EAI → bound to EAI                    │    │   pipeline_health           │  │
│  │ PEM Secret ref → bound to Secret (optional)  │    │                             │  │
│  └──────────────────────────────────────────────┘    └─────────────────────────────┘  │
│                                                                   │                    │
│                                                        ┌──────────┴──────────┐         │
│                                                        │ EAI + Network Rules │         │
│                                                        │  (OTLP egress)      │         │
│                                                        └──────────┬──────────┘         │
└───────────────────────────────────────────────────────────────────┼─────────────────────┘
                                                                    │ gRPC/TLS
                                                          ┌─────────┴─────────┐
                                                          │  Remote OTel      │
                                                          │  Collector        │
                                                          │  (Splunk dist.)   │
                                                          └────────┬──────────┘
                                                     ┌─────────────┼─────────────┐
                                                     ↓             ↓             ↓
                                              Splunk O11y    Splunk Cloud   Splunk Ent.
                                              (traces/metrics)  (logs)      (logs)
```

Note: no `_staging` schema and no Snowflake streams are used — the app relies on the `CHANGES` clause for Event Tables and a self-managed watermark table (`_internal.export_watermarks`) for both pipelines.

### Data Flow

**Event Table Pipeline (scheduled `CHANGES` + self-managed watermark):**

```
User-selected source (default SNOWFLAKE.TELEMETRY.EVENTS or
                     consumer-owned view with CHANGE_TRACKING = TRUE)
  → Independent scheduled task (default 1 min cadence)
    → event_table_collector SP:
      1. session.sql_simplifier_enabled = True
      2. load_config(session) → otlp_endpoint, event_table.* tuning
      3. watermark  = read_watermark(session, source)
         batch_end = CURRENT_TIMESTAMP()       # captured once per run
      4. Per-signal Snowpark SELECTs, each using:
         SELECT ... FROM <source>
           CHANGES(INFORMATION => APPEND_ONLY)
             AT(TIMESTAMP => :watermark)
             END(TIMESTAMP => :batch_end)
         WHERE RECORD_TYPE IN (...)            # SPAN / SPAN_EVENT / LOG / METRIC
           AND <entity discrimination filter>  # snow.executable.type etc.
         On "Time travel data is not available" → record WATERMARK_EXPIRED,
         reset watermark to batch_end - event_table.watermark_reset_buffer_seconds,
         return WATERMARK_RESET (skip this run).
      5. to_pandas_batches() → span_mapper / log_mapper / metric_mapper
         → module-level OTLP exporters (.export(...))
      6. If all signal exports succeed (ExportOutcome = SUCCESS) →
         MERGE INTO _internal.export_watermarks SET watermark = :batch_end
         Else → hold watermark unchanged (exact retry next scheduled run).
      7. record_run_metrics()  # rows_*, export_latency_ms, watermark_value,
                               # source_lag_seconds, error_code (raw gRPC name)
```

**ACCOUNT_USAGE Pipeline (scheduled watermark + overlap + QUALIFY):**

```
User-selected source (AU view or default)
  → Independent scheduled task (per source, source-specific interval)
    → account_usage_collector SP:
      1. session.sql_simplifier_enabled = True
      2. load_config(session) → otlp_endpoint, source settings, overlap_minutes
      3. watermark  = read_watermark(session, source)
         batch_end = CURRENT_TIMESTAMP()
      4. Snowpark DataFrame (no CHANGES — unsupported on ACCOUNT_USAGE):
         a. Overlap window:  WHERE timestamp_col >  :watermark - INTERVAL overlap_minutes
         b. Batch bound:     AND   timestamp_col <= :batch_end
         c. Dedup:           QUALIFY ROW_NUMBER() OVER
                               (PARTITION BY <natural_key>
                                ORDER BY timestamp_col DESC) = 1
         d. Batch limit:     LIMIT batch_size
      5. to_pandas_batches() → account_usage_mapper → module-level OTLP exporter
      6. If export SUCCESS → MERGE INTO _internal.export_watermarks SET watermark = :batch_end
         Else → hold watermark unchanged.
      7. record_run_metrics()
```

Both pipelines write the same structured shape into `_metrics.pipeline_health` and use the same `_internal.export_watermarks` table, differing only in the incremental-read primitive (`CHANGES` vs `WHERE + QUALIFY`).

**Why overlap + dedup (corrected understanding):**

ACCOUNT_USAGE latency (e.g., "up to 45 minutes" for QUERY_HISTORY) is a **maximum**, not a fixed delay. Rows trickle in over a variable window — some appear in 5 minutes, others take the full documented maximum. The overlap window re-scans past the watermark to catch late-arriving rows; the dedup (`QUALIFY ROW_NUMBER()`) removes rows already exported in previous polls.

**Per-source overlap defaults (configurable via Telemetry Sources UI):**

| Source | Documented Max Latency | Default Overlap | Config Key | Natural Dedup Key |
|---|---|---|---|---|
| QUERY_HISTORY | Up to 45 min | **50 min** | `source.query_history.overlap_minutes` | `QUERY_ID` |
| TASK_HISTORY | Up to 45 min | **50 min** | `source.task_history.overlap_minutes` | `QUERY_ID` + `NAME` |
| COMPLETE_TASK_GRAPHS | Up to 45 min | **50 min** | `source.complete_task_graphs.overlap_minutes` | `ROOT_TASK_ID` + `GRAPH_RUN_GROUP_ID` |
| LOCK_WAIT_HISTORY | Up to 60 min | **66 min** | `source.lock_wait_history.overlap_minutes` | `QUERY_ID` + `LOCK_WAIT_STARTED` |

Defaults are set to `documented_max_latency × 1.1`. Admins can decrease to minimize re-scans (if they observe faster latency in their account) or increase as a safety margin. Dedup always runs regardless of overlap size.

**Post-MVP: Adaptive overlap** — track observed p95 latency per source and auto-tune `overlap_minutes` to `observed_p95 × 1.2`.

### Requirements to Structure Mapping

| FR Category | Primary Files | Supporting Files |
|---|---|---|
| **Installation & Setup** (FR1–3) | `app/manifest.yml`, `app/setup.sql` | `pages/getting_started.py`, `common/task_manager.py` |
| **Source Configuration** (FR4–11) | `pages/telemetry_sources.py`, `pages/splunk_settings.py` | `components/source_table.py`, `components/connection_card.py`, `common/config.py` |
| **Data Governance** (FR12–18) | `pages/data_governance.py` | `common/config.py` (source type: default vs custom) |
| **Telemetry Collection** (FR19–22) | `app/python/event_table_collector.py`, `app/python/account_usage_collector.py` | `app/python/watermark.py`, `app/python/config_reader.py`, `app/python/telemetry_constants.py` |
| **Telemetry Export** (FR23–26) | `app/python/otlp_export.py`, `app/python/span_mapper.py`, `app/python/log_mapper.py`, `app/python/metric_mapper.py`, `app/python/account_usage_mapper.py` | `app/python/export_result.py`, `app/python/secret_reader.py`, `app/python/endpoint_parse.py` |
| **Pipeline Operations** (FR27–34) | `pages/observability_health.py`, `app/python/pipeline_telemetry.py` | `components/health_cards.py`, `app/python/watermark.py` |
| **App Lifecycle** (FR35–39) | `app/setup.sql`, `app/manifest.yml`, `snowflake.yml` | `scripts/shared_content.sql` |

### Development Workflow

| Action | Command |
|---|---|
| Setup root env | `uv sync` (from project root) |
| Setup Streamlit preview | `cd app && uv sync` |
| Preview UI locally | `cd app && uv run streamlit run streamlit/main.py` |
| Deploy to dev | `snow app run -c dev` |
| Open in Snowsight | `snow app open -c dev` |
| Run tests | `pytest` (from root) |
| Lint + format | `ruff check --fix . && ruff format .` |
| Type check | `mypy .` |
| Pre-commit | `pre-commit run --all-files` |
| Create version | `snow app version create V1_0 --package <pkg>` |

## Architecture Validation

### Coherence

All 5 new decisions (D1–D5) and 14 vision decisions (V1–V14) are internally consistent. D1 (Config hybrid) feeds D2 (TLS) which feeds D3 (exporters). V1 (scheduled-task dual pipeline) and V4 (advance-on-success / hold-on-failure watermark with `WATERMARK_EXPIRED` self-heal) compose cleanly: both pipelines share `_internal.export_watermarks`, differing only in the incremental-read primitive (`CHANGES` for Event Tables, `WHERE + QUALIFY` for ACCOUNT_USAGE). The configurable ACCOUNT_USAGE overlap window and Event Table reset-buffer integrate cleanly with the unified watermark state and config table. Naming conventions, patterns, and structure are aligned throughout.

### Requirements Coverage

| Range | Count | Status |
|---|---|---|
| FR1–FR3 (Install & Setup) | 3 | ✅ `manifest.yml` v2, `setup.sql`, Permission SDK, Getting Started |
| FR4–FR11 (Source Config) | 8 | ✅ Config table, `st.data_editor`, Connection Card, EAI/Secrets |
| FR12–FR18 (Governance) | 7 | ✅ User-selected source model, governance page, per-source messages |
| FR19–FR22a (Collection) | 5 | ✅ Dual-pipeline (both scheduled-task-driven), entity discrimination, `CHANGES` for Event Tables, watermark+overlap+QUALIFY for ACCOUNT_USAGE |
| FR23–FR26 (Export) | 4 | ✅ OTLP/gRPC, OTel conventions, transport retry, terminal failure recording |
| FR27–FR34 (Ops & Health) | 8 | ✅ `_metrics.pipeline_health`, Native App events, health page, `WATERMARK_EXPIRED` self-heal, auto-suspend |
| FR35–FR39 (Lifecycle) | 5 | ✅ Versioned + stateful schemas, multi-package strategy, E2E testing |
| NFR1–5 (Performance) | 5 | ✅ Scheduled serverless tasks (1 min default), Snowpark pushdown, `to_pandas_batches()` |
| NFR6–12 (Security) | 7 | ✅ Snowflake Secrets, TLS gRPC, EAI scoping, Marketplace scan gate |
| NFR13–18 (Reliability) | 6 | ✅ Independent scheduled tasks, advance-on-success watermark, `WATERMARK_EXPIRED` reset-and-resume, upgrade continuity |
| NFR19–21 (Scalability) | 3 | ✅ Serverless compute, chunked processing |
| NFR22–24 (Integration) | 3 | ✅ OTel DB Client conventions, routing fields, error classification |
| **Total** | **64** | **All covered** |

### Implementation Readiness

| Check | Status |
|---|---|
| Critical decisions documented with live-verified versions | ✅ |
| Patterns comprehensive for AI agents (5 Cursor rules referenced) | ✅ |
| Project structure complete with FR-to-file mapping | ✅ |
| Component boundaries and data flow defined | ✅ |
| Config loading, health recording, and `WATERMARK_EXPIRED` self-heal examples provided | ✅ |

### Minor Observations (not blocking)

| # | Observation | Resolution |
|---|---|---|
| 1 | `st.image`, `st.pyplot`, `st.scatter_chart` Native App support ambiguous in docs | Verify at dev time; primary charting (Plotly) unaffected |
| 2 | 3 gRPC channels per Event Table collector sandbox not empirically tested | Verify during dev; fallback documented |
| 3 | OTel Python Logs signal is "development" status | SDK pinned; test at integration stage |

### Readiness Assessment

**Status:** READY FOR IMPLEMENTATION

**First Implementation Priority:**
1. `app/setup.sql` — DDL for `_internal.config`, `_internal.export_watermarks` (unified high-water mark per source), `_metrics.pipeline_health`
2. `app/python/config_reader.py` — `_internal.config` typed getters + manifest reference resolution
3. `app/python/watermark.py` — `read_watermark` / `update_watermark` / `reset_watermark` against `_internal.export_watermarks` (advance-on-success / hold-on-failure semantics)
4. `app/python/otlp_export.py` — module-level OTLP exporter singletons (Span / Metric / Log) with TLS enforcement
5. `app/python/event_table_collector.py` — `CHANGES(INFORMATION => APPEND_ONLY) AT/END` reader + per-signal mappers + `WATERMARK_EXPIRED` self-heal
6. `app/python/account_usage_collector.py` — watermark + overlap + `QUALIFY ROW_NUMBER()` reader + mapper
7. Scheduled-task DDL in `setup.sql` (default 1 min cadence per source) — independent tasks using `WAREHOUSE = REFERENCE('CONSUMER_WAREHOUSE')`
8. `app/streamlit/main.py` — `st.navigation()` router with sidebar structure
