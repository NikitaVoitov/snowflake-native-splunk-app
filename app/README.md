# Splunk Observability for Snowflake

Export Snowflake-native telemetry to Splunk via OTLP/gRPC for unified observability.

## What This App Does

- **Distributed Tracing Pack**: Exports Event Table spans, metrics, and logs to Splunk Observability Cloud via OTLP/gRPC.
- **Performance Pack**: Exports QUERY_HISTORY, TASK_HISTORY, COMPLETE_TASK_GRAPHS, and LOCK_WAIT_HISTORY via OTLP/gRPC.

All telemetry is sent to a remote OpenTelemetry Collector (Splunk distribution), which handles routing to Splunk Observability Cloud, Splunk Cloud, or Splunk Enterprise.

## Setup

1. Install the app from Snowflake Marketplace.
2. Grant requested privileges when prompted.
3. Open the Streamlit UI to configure OTLP collector endpoint settings and enable monitoring packs.
4. The app automatically provisions streams, tasks, and begins exporting telemetry.

## Required Privileges

- `IMPORTED PRIVILEGES ON SNOWFLAKE DB` - Read ACCOUNT_USAGE views for cost, performance, and security monitoring.
- `EXECUTE TASK` - Run scheduled and triggered tasks.
- `EXECUTE MANAGED TASK` - Provision serverless compute for tasks.
- `CREATE EXTERNAL ACCESS INTEGRATION` - Allow OTLP gRPC egress to the configured collector endpoint.

## Required References

- `CONSUMER_WAREHOUSE` (Warehouse) - USAGE, OPERATE privileges. Query execution for Streamlit UI, tasks, and stored procedures.
