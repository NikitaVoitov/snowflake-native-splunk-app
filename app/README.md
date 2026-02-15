# Splunk Observability for Snowflake

Export Snowflake-native telemetry to Splunk backends for unified observability.

## What This App Does

- **Distributed Tracing Pack**: Exports Event Table spans, metrics, and logs to Splunk Observability Cloud (OTLP/gRPC) and Splunk Enterprise/Cloud (HEC HTTP).
- **Performance Pack**: Exports QUERY_HISTORY, TASK_HISTORY, COMPLETE_TASK_GRAPHS, and LOCK_WAIT_HISTORY to Splunk Enterprise/Cloud (HEC HTTP).

## Setup

1. Install the app from Snowflake Marketplace.
2. Grant requested privileges when prompted.
3. Open the Streamlit UI to configure Splunk connection settings and enable monitoring packs.
4. The app automatically provisions streams, tasks, and begins exporting telemetry.

## Required Privileges

| Privilege | Purpose |
|---|---|
| `IMPORTED PRIVILEGES ON SNOWFLAKE DB` | Read ACCOUNT_USAGE views |
| `EXECUTE TASK` | Run scheduled and triggered tasks |
| `EXECUTE MANAGED TASK` | Provision serverless compute |
| `CREATE DATABASE` | Internal state storage |
| `CREATE EXTERNAL ACCESS INTEGRATION` | Egress to Splunk endpoints |

## Stored Procedures

```sql
-- Trigger Event Table export manually (normally runs automatically via triggered task)
CALL _internal.event_table_collector();

-- Estimate data volume for planning
CALL _internal.volume_estimator();
```
