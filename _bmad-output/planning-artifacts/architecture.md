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
| Data Governance & Privacy (FR12–FR18) | Custom/default source selection, governance disclosure, policy-respecting export | User-selected source model, stream creation on views or tables, NULL-tolerant pipelines |
| Telemetry Collection (FR19–FR22) | Incremental export, entity scoping, independent schedules, per-source settings | Dual-pipeline (stream-triggered + scheduled), entity discrimination filter, watermark state |
| Telemetry Export (FR23–FR26) | OTLP delivery, Splunk-compatible spans, convention transparency, retry/failure | OTLP/gRPC client, OTel convention mapping, transport-level retry |
| Pipeline Operations & Health (FR27–FR34) | Health summary, source inspection, operational events, auto-recovery, auto-suspend | Internal metrics table, Native App event definitions, stale stream detection/recovery |
| App Lifecycle (FR35–FR39) | Upgrades, config preservation, submission readiness | Versioned schemas, stateful object preservation, multi-package publish pipeline |

**Non-Functional Requirements (24 NFRs across 5 domains):**

| Domain | Key Targets | Architectural Driver |
|---|---|---|
| Performance | Event Table ≤60s e2e, AU ≤1 poll cycle, page render ≤5s, batch ≤30s | Triggered tasks (30s min interval), Snowpark pushdown, chunked processing |
| Security | Secrets in Snowflake Secrets only, TLS-only OTLP, no governance bypass, security scan pass | EAI + Network Rules, secret references (not values) in config, policy-transparent reads |
| Reliability | 99.9% per-source availability, 99.5% batch success, stale stream recovery ≤10min, fault isolation | Independent tasks, auto-retry per task, auto-suspend, stream staleness detection/recreation |
| Scalability | 1M Event Table rows per triggered run, 10 concurrent AU sources, 1.7× throughput scaling | Serverless compute, to_pandas_batches() chunking, independent task architecture |
| Integration | Splunk APM interop, mandatory routing fields, deterministic error handling | OTel DB Client conventions, resource attribute enrichment, retryable vs terminal classification |

**Scale & Complexity:**

- Primary domain: Cloud Infrastructure / Observability — Snowflake Native App (Marketplace-distributed)
- Complexity level: **High**
- Architectural component count: ~15 major components (2 pipelines, 2 collector SPs, OTLP export layer, config/watermark/metrics state, stream management, task lifecycle, Streamlit UI with 5+ pages, EAI/networking, secret management, operational logging, governance layer, upgrade machinery, Marketplace packaging)

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
| ACCOUNT_USAGE views don't support Streams | Snowflake platform | Poll-based pipeline with watermark state required for AU sources |
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
| **Error handling & data gaps** | Both pipelines | Transport-level retry (MVP); failure logging; data gap recording; pipeline advancement on failure |
| **Secret management** | OTLP endpoint, certificates | Snowflake Secrets only; reference names in config table, never values; rotatable without restart |
| **Platform constraints** | SP environment, Native App sandbox | SimpleSpanProcessor, module-level init, independent tasks, NULL-tolerant policy handling |

### Key Architectural Decisions Already Made (from Vision)

The vision document pre-establishes 14 major architectural decisions that the architecture document will formalize, validate, and structure:

1. Dual-pipeline design (event-driven + poll-based)
2. User-selected sources (no app-created governed views)
3. Independent serverless scheduled tasks per ACCOUNT_USAGE source
4. Zero-row INSERT stream offset advancement
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
│   ├── setup.sql                    # Idempotent DDL (app_public, _internal, _staging, _metrics)
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

**Pre-Established Decisions (from Vision — validated and formalized):**

| # | Decision | Choice | Source |
|---|---|---|---|
| V1 | Pipeline architecture | Dual-pipeline: event-driven (streams + triggered tasks) + poll-based (scheduled tasks + watermarks) | Vision §3, §6 |
| V2 | Data governance model | User-selected sources only — no app-created governed views | Vision §7A, PRD §2.2 |
| V3 | ACCOUNT_USAGE task architecture | Independent serverless scheduled tasks — one per enabled source with source-specific schedule | Vision §7.6 |
| V4 | Stream offset advancement | Zero-row INSERT pattern within explicit transaction — `INSERT INTO _staging.stream_offset_log(_OFFSET_CONSUMED_AT) SELECT CURRENT_TIMESTAMP() FROM <stream> WHERE 0 = 1` | Vision §8.0 |
| V5 | OTLP transport | Single OTLP/gRPC endpoint — remote collector handles routing to Splunk backends | Vision §7.9, PRD §4.1 |
| V6 | Data processing philosophy | Snowpark pushdown-first — all relational work (filter, project, dedup) pushed to Snowflake engine; Python only serializes | Vision §7.11, §7.12 |
| V7 | Memory management | `to_pandas_batches()` for chunked processing — bounded memory, no global `collect()` | Vision §7.11 |
| V8 | OTel span processor | `SimpleSpanProcessor` (synchronous) — `BatchSpanProcessor` daemon thread incompatible with SP lifecycle | Vision §Technical Prerequisites |
| V9 | Network client lifecycle | Module-level OTLP exporter initialization — gRPC channel persists across task invocations via Snowflake module caching | Vision §7.12 BP-2, BP-3 |
| V10 | Event Table entity filtering | Positive include-list on `RESOURCE_ATTRIBUTES:"snow.executable.type"` — values: `procedure`, `function`, `query`, `sql` | Vision §7B, Entity Discrimination Strategy |
| V11 | OTel semantic conventions | Layered: `db.*` (Database Client, stable) + `snowflake.*` (custom namespace) + convention-transparent relay of original attributes | Vision §7B, OTel Conventions Research |
| V12 | Failure handling (MVP) | Transport-level retry only (OTel SDK built-in gRPC retry ~6 attempts over ~63s); on exhaustion: log failure + advance pipeline | Vision §7.2 |
| V13 | Operational logging | Native App event definitions — structured logs to consumer's account-level event table; queryable via Snowsight | Vision §3.5, PRD §3.5 |
| V14 | RBAC model | Single role: `app_admin` — KISS principle; admin shares dashboards via Splunk, not in-app viewer roles | Vision §1, PRD §1.2 |

### Data Architecture

**Configuration Storage (D1 — Hybrid):**

| Setting Category | Storage | Resolution |
|---|---|---|
| Event Table reference | Manifest reference (`CONSUMER_EVENT_TABLE`) | `REFERENCE('CONSUMER_EVENT_TABLE')` in SQL |
| EAI reference | Manifest reference (`SPLUNK_EAI`) | `REFERENCE('SPLUNK_EAI')` in SQL |
| PEM cert Secret reference | Manifest reference (optional, `required_at_setup: false`) | Resolve Secret content via reference at runtime |
| OTLP endpoint URL | `_internal.config` (key: `otlp.endpoint`) | Query config table at pipeline startup |
| Per-source custom view FQNs | `_internal.config` (key: `source.<name>.view_fqn`) | Query config table; used in stream/task DDL |
| Pack enablement flags | `_internal.config` (key: `pack_enabled.<pack_name>`) | Query config table; drives task create/drop |
| Per-source batch size and interval | `_internal.config` (keys: `source.<name>.batch_size`, `source.<name>.poll_interval_seconds`) | Query config table; per-source operational settings for MVP |
| Per-source overlap window | `_internal.config` (key: `source.<name>.overlap_minutes`) | Configurable overlap for AU watermark dedup; default = documented max latency × 1.1 |
| Watermark state | `_internal.export_watermarks` (dedicated table) | Per-source watermark tracking |
| Pipeline health metrics | `_metrics.pipeline_health` (dedicated table) | Per-run operational metrics |

**Schema Topology:**

| Schema | Type | Purpose | Upgrade Behavior |
|---|---|---|---|
| `app_public` | Versioned (`CREATE OR ALTER VERSIONED SCHEMA`) | Procedures, Streamlit, grants | Recreated on upgrade |
| `_internal` | Stateful (`CREATE SCHEMA IF NOT EXISTS`) | Config, watermarks, collector SPs | Persists across upgrades |
| `_staging` | Stateful | `stream_offset_log` (permanently empty) | Persists across upgrades |
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

**Stream DDL by Source Type:**

| User Selection | Stream Creation DDL | Syntax Variant |
|---|---|---|
| Default Event Table (`SNOWFLAKE.TELEMETRY.EVENTS`) | `CREATE STREAM IF NOT EXISTS <ns>_stream ON EVENT TABLE <ref> APPEND_ONLY = TRUE` | Event Table syntax (no AT/BEFORE, no SHOW_INITIAL_ROWS) |
| Consumer's custom view over Event Table | `CREATE STREAM IF NOT EXISTS <ns>_stream ON VIEW <user_view_fqn> APPEND_ONLY = TRUE` | View syntax (change tracking auto-enabled on first stream) |
| Default ACCOUNT_USAGE view | No stream — poll-based with watermark | N/A |
| Consumer's custom view over ACCOUNT_USAGE | No stream — poll-based with watermark | N/A |

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
| **(b) Integration** | pytest + `snow sql` against dev schema | SP execution, watermarks, stream behavior, task lifecycle | CI — pre-merge against dev account |
| **(c) E2E — Snowflake side** | Cursor agent + Playwright CLI | `snow app run` → Snowsight UI automation: install, configure, activate, verify health page | Pre-release — fully automated via Cursor |
| **(c) E2E — Splunk side** | Cursor agent + SSH to OTel collector | Connect to collector instance, query logs, verify exported telemetry format, OTel conventions, attribute completeness | Pre-release — fully automated via Cursor |

E2E is fully automated — Cursor agents drive Playwright CLI (minimizing token usage) for Snowsight browser automation and SSH into the OTel collector to verify exported telemetry end-to-end.

### Decision Impact Analysis

**Implementation Sequence:**

1. **D1 (Config storage)** → First: config table schema + reference callbacks must exist before any pipeline code
2. **Stream DDL** → Second: stream creation logic depends on D1 (where user-selected source FQNs are stored)
3. **D3 (Exporter topology)** → Third: OTLP export module with 3 exporters, TLS setup from D2
4. **V4, V6, V7, V8** → Fourth: collector SPs using Snowpark pushdown + to_pandas_batches + SimpleSpanProcessor
5. **D4 (Streamlit state)** → Fifth: UI reads config via session_state pattern
6. **D5 (Testing)** → Ongoing: unit tests from day 1, integration tests as SPs land, E2E at feature-complete

**Cross-Component Dependencies:**

| Decision | Depends On | Affects |
|---|---|---|
| D1 (Config hybrid) | Manifest reference definitions | All pipelines (read config at startup), Streamlit UI (read/write config) |
| D2 (TLS only) | D1 (PEM secret reference) | OTLP exporter initialization (D3) |
| D3 (3 exporters) | D2 (TLS credentials) | Event Table collector, ACCOUNT_USAGE collector |
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
| `_internal` | Stateful | `CREATE SCHEMA IF NOT EXISTS` | Config, watermarks, collector SPs — persists across upgrades |
| `_staging` | Stateful | `CREATE SCHEMA IF NOT EXISTS` | `stream_offset_log` (permanently empty) — persists across upgrades |
| `_metrics` | Stateful | `CREATE SCHEMA IF NOT EXISTS` | `pipeline_health` operational metrics — persists across upgrades |

### Naming Patterns

**Snowflake Object Naming:**

| Object Type | Convention | Example | Anti-Pattern |
|---|---|---|---|
| Schemas (app-internal) | `_lowercase` prefix | `_internal`, `_staging`, `_metrics` | `Internal`, `INTERNAL` |
| Schemas (consumer-facing) | `snake_case` | `app_public` | `AppPublic` |
| Tables | `snake_case` | `pipeline_health`, `export_watermarks` | `PipelineHealth` |
| Columns | `UPPER_CASE` (Snowflake convention) | `CONFIG_KEY`, `METRIC_VALUE` | `config_key` in DDL |
| Stored procedures | `snake_case` | `event_table_collector` | `EventTableCollector` |
| Streams | `_splunk_obs_stream_<source_name>` | `_splunk_obs_stream_telemetry_events` | `stream_1` |
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
| Source overlap window | `source.<source_name>.overlap_minutes` | `source.query_history.overlap_minutes` (default: 50) |
| Source view FQNs | `source.<source_name>.view_fqn` | `source.query_history.view_fqn` |
| Source type | `source.<source_name>.source_type` | Value: `default` or `custom` |

This dotted format is the canonical config-key convention for the project. Older mixed examples such as `otlp_endpoint`, `source:<name>:view_fqn`, `pack_enabled:<pack_name>`, or `export_batch_size` are deprecated planning-era artifacts and must not be used in new stories or implementation code.

**OTel Attribute Naming:**

| Layer | Namespace | Convention | Example |
|---|---|---|---|
| OTel standard (DB) | `db.*` | Stable, lowercase dot-separated | `db.system.name`, `db.namespace` |
| Snowflake custom | `snowflake.*` | Lowercase dot-separated | `snowflake.warehouse.name`, `snowflake.query.id` |
| OTLP resource | `service.*`, `cloud.*` | OTel resource conventions | `service.name`, `cloud.provider` |
| Original pass-through | `snow.*` | Preserved as-is from Event Table | `snow.executable.type` |

### Structure Patterns

**Python Module Organization:**

```
app/python/
├── collectors/
│   ├── __init__.py
│   ├── event_table_collector.py
│   └── account_usage_collector.py
├── exporters/
│   ├── __init__.py
│   └── otlp_grpc.py
├── transforms/
│   ├── __init__.py
│   ├── span_mapper.py
│   ├── log_mapper.py
│   ├── metric_mapper.py
│   └── account_usage_mapper.py
├── common/
│   ├── __init__.py
│   ├── config.py
│   ├── health.py
│   ├── stream_manager.py
│   └── task_manager.py
└── constants.py
```

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
│   ├── test_span_mapper.py
│   ├── test_log_mapper.py
│   ├── test_config.py
│   └── test_health.py
├── integration/
│   ├── test_event_table_collector.py
│   ├── test_watermark_logic.py
│   └── test_stream_lifecycle.py
└── e2e/
    ├── test_install_configure.py       # Playwright MCP scripts
    └── test_export_verification.py     # SSH to collector verification
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
| `source_lag_seconds` | NUMBER | Latest available minus latest exported |
| `stream_stale_after` | TIMESTAMP_LTZ | From `DESCRIBE STREAM` |

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
| `error_code` | string | On error | Machine-readable error classification |
| `error_message` | string | On error | Human-readable error detail |

**Error Code Taxonomy:**

| Code | Category | Example |
|---|---|---|
| `OTLP_CONNECT_FAILED` | Transport | gRPC connection refused |
| `OTLP_TIMEOUT` | Transport | gRPC deadline exceeded after all retries |
| `OTLP_TLS_FAILED` | Transport | TLS handshake failure |
| `STREAM_STALE` | Pipeline | Stream became stale; auto-recovery triggered |
| `STREAM_BROKEN` | Pipeline | Stream on view broken (view recreated) |
| `SOURCE_UNAVAILABLE` | Pipeline | ACCOUNT_USAGE view query failed |
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

**Stream Staleness Recovery:**

```
detect → DESCRIBE STREAM → if stale:
    log STREAM_STALE warning
    DROP STREAM IF EXISTS
    CREATE STREAM ON <selected_source> APPEND_ONLY = TRUE
    record data_gap in pipeline_health
```

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

1. Never create Snowflake views — only streams on user-selected sources
2. Initialize OTLP exporters at module scope, never inside handler functions
3. Use `session.sql_simplifier_enabled = True` at the start of every SP handler
4. Use explicit `BEGIN`/`COMMIT` transactions for stream offset advancement
5. Resolve manifest references via `REFERENCE('ref_name')` in SQL, not hardcoded object names
6. Record pipeline health metrics at the end of every SP run (success or failure)
7. Use structured logging with mandatory fields (pipeline, source, run_id, duration_ms)
8. Use the config key naming convention (`otlp.*`, `pack_enabled.*`, `source.*.*`)
9. Follow the Getting Started → Observability health → Telemetry sources → Splunk settings → Data governance sidebar order
10. Use `st.navigation()` API for page routing (not `pages/` folder convention alone)

## Project Structure & Boundaries

*Complete directory structure documented in Starter Template section above. This section defines architectural boundaries, data flow, and requirement mapping.*

### Architectural Boundaries

```
┌─────────────────────────── Consumer's Snowflake Account ───────────────────────────┐
│                                                                                      │
│  ┌── Consumer Objects (user-selected sources) ──┐  ┌── App Objects ──────────────┐  │
│  │ SNOWFLAKE.TELEMETRY.EVENTS (default ET)      │  │ app_public (versioned)      │  │
│  │ consumer_db.schema.custom_view (custom)       │  │   main (Streamlit)          │  │
│  │ SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY (AU)    │  │   register_single_callback  │  │
│  │ consumer_db.schema.custom_au_view (custom)    │  │   collector SPs             │  │
│  └───────────────────────────────────────────────┘  │                             │  │
│            ↓ (SELECT via reference or FQN)           │ _internal                   │  │
│                                                      │   config (KV settings)      │  │
│  ┌── Manifest References ──────────────────────┐    │   export_watermarks          │  │
│  │ CONSUMER_EVENT_TABLE → bound to ET/view      │    │   collector SPs (stateful)  │  │
│  │ SPLUNK_EAI → bound to EAI                    │    │ _staging                    │  │
│  │ PEM Secret ref → bound to Secret (optional)  │    │   stream_offset_log         │  │
│  └──────────────────────────────────────────────┘    │ _metrics                    │  │
│                                                      │   pipeline_health           │  │
│                                                      └──────────────────────────────┘  │
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

### Data Flow

**Event Table Pipeline (event-driven):**

```
User-selected source (ET or view)
  → Stream (APPEND_ONLY)
    → Triggered task fires (SYSTEM$STREAM_HAS_DATA)
      → event_table_collector SP:
        1. session.sql_simplifier_enabled = True
        2. load_config(session) → otlp_endpoint, batch settings
        3. BEGIN TRANSACTION
        4. Snowpark DataFrame: filter RECORD_TYPE + entity discrimination
        5. Per-signal projection (span_mapper/log_mapper/metric_mapper)
        6. to_pandas_batches() → OTel protobuf → otlp_grpc.export()
        7. Zero-row INSERT into `_staging.stream_offset_log(_OFFSET_CONSUMED_AT)`
           using `SELECT CURRENT_TIMESTAMP() FROM <stream> WHERE 0 = 1`
           (stream consumed without coupling to stream column shape)
        8. COMMIT
        9. record_run_metrics()
```

**ACCOUNT_USAGE Pipeline (poll-based with configurable overlap):**

```
User-selected source (AU view or default)
  → Independent scheduled task (per source, source-specific interval)
    → account_usage_collector SP:
      1. session.sql_simplifier_enabled = True
      2. load_config(session) → otlp_endpoint, source settings, overlap_minutes
      3. Read watermark from _internal.export_watermarks
      4. Snowpark DataFrame:
         a. Overlap window:  WHERE START_TIME > watermark - INTERVAL overlap_minutes
         b. Latency cutoff:  AND START_TIME <= NOW() - INTERVAL overlap_minutes
         c. Dedup:           QUALIFY ROW_NUMBER() OVER (PARTITION BY natural_key
                                ORDER BY timestamp_col DESC) = 1
         d. Batch limit:     LIMIT batch_size
      5. to_pandas_batches() → account_usage_mapper → otlp_grpc.export()
      6. Update watermark
      7. record_run_metrics()
```

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
| **Telemetry Collection** (FR19–22) | `collectors/event_table_collector.py`, `collectors/account_usage_collector.py` | `common/stream_manager.py`, `common/config.py`, `constants.py` |
| **Telemetry Export** (FR23–26) | `exporters/otlp_grpc.py`, `transforms/*.py` | `constants.py` (OTel attribute names) |
| **Pipeline Operations** (FR27–34) | `pages/observability_health.py`, `common/health.py` | `components/health_cards.py`, `common/stream_manager.py` |
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

All 5 new decisions (D1–D5) and 14 vision decisions (V1–V14) are internally consistent. D1 (Config hybrid) feeds D2 (TLS) which feeds D3 (exporters). The configurable overlap window integrates cleanly with watermark state and the config table. Naming conventions, patterns, and structure are aligned throughout.

### Requirements Coverage

| Range | Count | Status |
|---|---|---|
| FR1–FR3 (Install & Setup) | 3 | ✅ `manifest.yml` v2, `setup.sql`, Permission SDK, Getting Started |
| FR4–FR11 (Source Config) | 8 | ✅ Config table, `st.data_editor`, Connection Card, EAI/Secrets |
| FR12–FR18 (Governance) | 7 | ✅ User-selected source model, governance page, per-source messages |
| FR19–FR22a (Collection) | 5 | ✅ Dual-pipeline, entity discrimination, independent tasks, configurable overlap + dedup |
| FR23–FR26 (Export) | 4 | ✅ OTLP/gRPC, OTel conventions, transport retry, terminal failure recording |
| FR27–FR34 (Ops & Health) | 8 | ✅ `_metrics.pipeline_health`, Native App events, health page, auto-recovery, auto-suspend |
| FR35–FR39 (Lifecycle) | 5 | ✅ Versioned + stateful schemas, multi-package strategy, E2E testing |
| NFR1–5 (Performance) | 5 | ✅ Triggered tasks, Snowpark pushdown, `to_pandas_batches()` |
| NFR6–12 (Security) | 7 | ✅ Snowflake Secrets, TLS gRPC, EAI scoping, Marketplace scan gate |
| NFR13–18 (Reliability) | 6 | ✅ Independent tasks, auto-retry, stale stream recovery, upgrade continuity |
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
| Config loading, health recording, stream recovery examples provided | ✅ |

### Minor Observations (not blocking)

| # | Observation | Resolution |
|---|---|---|
| 1 | `st.image`, `st.pyplot`, `st.scatter_chart` Native App support ambiguous in docs | Verify at dev time; primary charting (Plotly) unaffected |
| 2 | 3 gRPC channels per Event Table collector sandbox not empirically tested | Verify during dev; fallback documented |
| 3 | OTel Python Logs signal is "development" status | SDK pinned; test at integration stage |

### Readiness Assessment

**Status:** READY FOR IMPLEMENTATION

**First Implementation Priority:**
1. `setup.sql` — DDL for `_internal.config`, `_internal.export_watermarks`, `_metrics.pipeline_health`, `_staging.stream_offset_log`
2. `app/python/common/config.py` — config table reader + manifest reference resolution
3. `app/python/exporters/otlp_grpc.py` — module-level OTLP exporter initialization
4. `app/streamlit/main.py` — `st.navigation()` router with sidebar structure
