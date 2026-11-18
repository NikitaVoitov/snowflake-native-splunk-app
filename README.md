# Splunk Observability for Snowflake

Snowflake Native App that exports Snowflake telemetry to Splunk through an OTLP/gRPC path. Installation, source selection, destination setup, and pipeline health stay inside the consumer Snowflake account. A remote OpenTelemetry Collector (Splunk distribution) routes data to Splunk Observability Cloud, Splunk Cloud, or Splunk Enterprise.

## What it does

- **Distributed Tracing Pack** — Event Table spans, logs, and related telemetry for SQL and Snowpark compute.
- **Performance Pack** — Selected `ACCOUNT_USAGE` sources such as query, task, and lock history.
- **Snowflake-first setup** — Streamlit UI for OTLP destination, TLS, pack/source selection, and operational health.
- **Customer-owned governance** — Default Snowflake sources for speed, or custom views when masking, row access, or projection must apply before export.

The app does not host vendor infrastructure. Collection and export run as Native App objects (tasks, stored procedures, Streamlit) in the consumer account.

## How it fits together

```
Snowflake account                         Downstream
─────────────────                         ──────────
Event Tables / ACCOUNT_USAGE
        │
  Native App collectors
  (scheduled tasks + watermarks)
        │
  OTLP/gRPC export (TLS)
        │
        └──► OpenTelemetry Collector ──► Splunk Observability / Cloud / Enterprise
```

## Using the app

1. Install from Snowflake Marketplace (or a development application package).
2. Grant the requested privileges and bind a consumer warehouse.
3. Open the Streamlit UI, configure the OTLP collector endpoint, and enable the packs you need.
4. Confirm first telemetry in Splunk after the collectors start exporting.

### Privileges

| Privilege | Why |
| --- | --- |
| `IMPORTED PRIVILEGES ON SNOWFLAKE DB` | Read `ACCOUNT_USAGE` for performance sources |
| `EXECUTE TASK` / `EXECUTE MANAGED TASK` | Run scheduled collection |
| `CREATE EXTERNAL ACCESS INTEGRATION` | Allow OTLP/gRPC egress |

### References

- `CONSUMER_WAREHOUSE` — warehouse used by the Streamlit UI, tasks, and stored procedures (`USAGE`, `OPERATE`)

The in-app README (`app/README.md`) is the copy packaged with the Native App.

## Repository layout

| Path | Role |
| --- | --- |
| `app/` | Native App artifacts: `manifest.yml`, `setup.sql`, Streamlit UI, Python collectors and exporters |
| `scripts/` | Post-deploy / shared-content SQL |
| `tests/` | Unit and integration tests |
| `snowflake.yml` | Snowflake CLI project definition for local packages and apps |
| `grpc_test/` | Local OTLP/gRPC connectivity helpers |

## Local development

Runtime dependencies are resolved from the Snowflake Anaconda channel (`app/environment.yml`). The root `pyproject.toml` mirrors those packages for IDE support, linting, and tests.

```bash
uv sync --group dev
uv run pytest
uv run ruff check app tests
```

Deploy and iterate with Snowflake CLI using `snowflake.yml` (dev application package and app). Preview Streamlit layout locally from `app/` with `uv run streamlit run streamlit/main.py` — Snowflake stored procedure calls will not run in that preview.

## Status

MVP in active development: tracing and performance packs, OTLP export, and Marketplace-oriented packaging. Cost, security, pipeline, Openflow, and Cortex packs are out of scope for this release.

## License

See [LICENSE](LICENSE).
