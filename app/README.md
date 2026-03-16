# Splunk Observability for Snowflake

Export Snowflake-native telemetry to Splunk via OTLP/gRPC for unified observability.

## What This App Does

- **Distributed Tracing Pack**: Exports Event Table spans, metrics, and logs to Splunk Observability Cloud via OTLP/gRPC.
- **Performance Pack**: Exports QUERY_HISTORY, TASK_HISTORY, COMPLETE_TASK_GRAPHS, and LOCK_WAIT_HISTORY via OTLP/gRPC.

All telemetry is sent to a remote OpenTelemetry Collector (Splunk distribution), which handles routing to Splunk Observability Cloud, Splunk Cloud, or Splunk Enterprise.

## Setup

1. Install the app from Snowflake Marketplace.
2. Grant requested privileges when prompted.
3. Open the Streamlit UI to configure Splunk connection settings and enable monitoring packs.
4. The app automatically provisions streams, tasks, and begins exporting telemetry.

## Required Privileges

| Privilege | Purpose |
|---|---|
| `IMPORTED PRIVILEGES ON SNOWFLAKE DB` | Read ACCOUNT_USAGE views for cost, performance, and security monitoring |
| `EXECUTE TASK` | Run scheduled and triggered tasks |
| `EXECUTE MANAGED TASK` | Provision serverless compute for tasks |
| `CREATE EXTERNAL ACCESS INTEGRATION` | OTLP gRPC egress to Splunk endpoints |

## Required References

| Reference | Type | Purpose |
|---|---|---|
| `CONSUMER_EVENT_TABLE` | TABLE | Event Table for reading telemetry data |
| `SPLUNK_OTLP_SECRET` | SECRET | Splunk Observability access token for OTLP gRPC export |
| `SPLUNK_EAI` | EXTERNAL_ACCESS_INTEGRATION | Allows OTLP gRPC egress from the app to Splunk |
