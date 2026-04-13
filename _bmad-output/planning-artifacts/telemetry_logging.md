# Native App telemetry logging and provider sharing

> Audience: engineers working on the Snowflake Native App telemetry/export path.
>
> Status: updated 2026-04-10 from live Snowflake SQL probes in `LFB71918` and cross-checked against Snowflake docs via Firecrawl.
>
> Scope: our app's own telemetry emission, event-table behavior, `DESC APPLICATION` nuances, provider sharing, upgrade behavior, and practical verification commands.

**Related docs:** `telemetry_preparation_for_export.md`, `../implementation-artifacts/4-3-deterministic-otlp-retry-and-terminal-failure-handling.md`

---

## 1. Executive summary

Our current Native App telemetry posture is:

- App-level telemetry in `app/manifest.yml` is enabled at `log_level: INFO`, `trace_level: ALWAYS`, `metric_level: ALL`.
- Current event definitions are:
  - `ERRORS_AND_WARNINGS` as `MANDATORY`
  - `DEBUG_LOGS` as `OPTIONAL`
- In the dev install, both definitions are enabled, so `DESC APPLICATION` shows:
  - `log_level = INFO`
  - `effective_log_level = TRACE`
  - `trace_level = ALWAYS`
  - `metric_level = ALL`
  - `log_event_level = OFF`
  - `effective_log_event_level = OFF`
- Provider sharing is currently enabled in dev, but the provider-visible surface is still incomplete:
  - shared now: error/warn/fatal logs, plus debug logs because `DEBUG_LOGS` is enabled
  - not shared now: INFO logs, spans, span events, metrics, and `EVENT` rows

The main corrections to the earlier Cortex write-up are:

- Event definitions are not only provider-side filters. Enabled definitions can also widen the app's **effective** log/trace levels so Snowflake can collect shareable data.
- New event definitions are **not auto-enabled on upgrade**, even when they are mandatory.
- Our dev event table contains `EVENT` rows for app lifecycle even though `effective_log_event_level` is `OFF`, so we should document that as an observed platform behavior rather than assuming `OFF` means zero `EVENT` rows.

---

## 2. Current app configuration

### 2.1 Source of truth in source control

Current `app/manifest.yml` telemetry block:

```yaml
configuration:
  log_level: INFO
  trace_level: ALWAYS
  metric_level: ALL
  telemetry_event_definitions:
    - type: ERRORS_AND_WARNINGS
      sharing: MANDATORY
    - type: DEBUG_LOGS
      sharing: OPTIONAL
```

Important nuance:

- Snowflake's provider-side Native App docs explicitly show app-level manifest support for `log_level`, `trace_level`, and `metric_level`.
- Those docs do **not** show an equivalent app-level manifest property for `log_event_level`.
- `DESC APPLICATION` exposes `log_event_level`, but until we validate a provider-controlled configuration path for it, we should treat it as an observed application property, not as a knob we have proven we can publish via manifest.

### 2.2 Live `DESC APPLICATION` values

From `DESC APPLICATION SPLUNK_OBSERVABILITY_DEV_APP` on 2026-04-10:

| Property | Value | Notes |
|---|---|---|
| `share_events_with_provider` | `TRUE` | All currently defined event definitions are enabled in dev |
| `authorize_telemetry_event_sharing` | `TRUE` | Required sharing is authorized |
| `log_level` | `INFO` | Provider-declared app log threshold |
| `log_event_level` | `OFF` | Current app property for `RECORD_TYPE='EVENT'` capture |
| `trace_level` | `ALWAYS` | Provider-declared app trace threshold |
| `metric_level` | `ALL` | Provider-declared app metric threshold |
| `effective_log_level` | `TRACE` | Widened beyond manifest because `DEBUG_LOGS` is enabled |
| `effective_log_event_level` | `OFF` | Still off |
| `effective_trace_level` | `ALWAYS` | Same as app-level config |
| `effective_metric_level` | `ALL` | Same as app-level config |

### 2.3 Active event table

From `SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT`:

| Parameter | Value |
|---|---|
| `EVENT_TABLE` | `snowflake.telemetry.events` |

That means our app's telemetry is currently landing in `SNOWFLAKE.TELEMETRY.EVENTS`.

### 2.4 Current event definition status

From `SHOW TELEMETRY EVENT DEFINITIONS IN APPLICATION SPLUNK_OBSERVABILITY_DEV_APP`:

| Name | Type | Sharing | Status |
|---|---|---|---|
| `SNOWFLAKE$ERRORS_AND_WARNINGS` | `ERRORS_AND_WARNINGS` | `MANDATORY` | `ENABLED` |
| `SNOWFLAKE$DEBUG_LOGS` | `DEBUG_LOGS` | `OPTIONAL` | `ENABLED` |

---

## 3. What our app actually emits today

### 3.1 Record types observed in the consumer event table

From `SNOWFLAKE.TELEMETRY.EVENTS` over the last 7 days for `RESOURCE_ATTRIBUTES:"snow.application.name" = 'SPLUNK_OBSERVABILITY_DEV_APP'`:

| Record type | Rows | What it represents in our app |
|---|---:|---|
| `LOG` | 1204 | Python logging emitted by app code and supporting runtime entries |
| `METRIC` | 784 | Snowflake-generated metrics because `metric_level = ALL` |
| `SPAN` | 190 | Trace spans because `trace_level = ALWAYS` |
| `SPAN_EVENT` | 98 | Trace child events, including exception events |
| `EVENT` | 10 | App lifecycle/system events such as `application.state_change` |

### 3.2 Log severities observed in the consumer event table

Last 7 days, `RECORD_TYPE = 'LOG'`:

| Severity | Rows |
|---|---:|
| `DEBUG` | 629 |
| `INFO` | 494 |
| `ERROR` | 40 |
| `FATAL` | 34 |
| `WARN` | 7 |

Observations:

- We are definitely producing INFO and DEBUG application logs, not just warnings/errors.
- The presence of `DEBUG` rows is consistent with `effective_log_level = TRACE`.
- This means optional `DEBUG_LOGS` has a real effect on capture, not just on provider replication.

### 3.3 `EVENT` rows observed even with `effective_log_event_level = OFF`

This is the most important live-data nuance to preserve.

Recent `EVENT` rows include:

- `application.state_change`
- `application.auto_grant_change`

These rows are present in the consumer event table even though `DESC APPLICATION` reports:

- `log_event_level = OFF`
- `effective_log_event_level = OFF`

Practical conclusion:

- The docs still describe `LOG_EVENT_LEVEL` as the control for `RECORD_TYPE='EVENT'`.
- Our live data shows at least some **Native App lifecycle/platform events** still appear in the event table even when that effective level is off.
- We should treat this as **observed platform behavior**, not as a guaranteed or fully documented contract for our troubleshooting design.
- We should **not** assume those `EVENT` rows are provider-shared today, because we do not declare `ALL_EVENTS` in the manifest.

---

## 4. Capture vs sharing: the mental model

### 4.1 Consumer event-table capture

These settings determine what the app emits into the **consumer** event table:

- `log_level`
- `trace_level`
- `metric_level`
- object-level overrides on schemas, procedures, or functions
- effective-level widening caused by enabled event definitions

Key doc-backed nuance:

- Snowflake Native App docs explicitly state that the app's effective log/trace levels can change based on which event definitions the consumer enables.
- Example from docs: an app published with `log_level = OFF` can still end up with `effective_log_level = WARN` if the consumer enables `ERRORS_AND_WARNINGS`.

So the strong form of "event definitions only affect provider sharing" is incorrect.

### 4.2 Provider-side sharing

Event definitions then determine which subset of the consumer-captured telemetry is eligible to be copied into the **provider** event table.

Supported event definitions relevant to our app:

| Type | Snowflake name | Filter |
|---|---|---|
| All | `SNOWFLAKE$ALL` | `*` |
| All events | `SNOWFLAKE$ALL_EVENTS` | `RECORD_TYPE='EVENT'` |
| Errors and warnings | `SNOWFLAKE$ERRORS_AND_WARNINGS` | `RECORD_TYPE='LOG' AND RECORD:severity_text in ('FATAL','ERROR','WARN')` |
| Usage logs | `SNOWFLAKE$USAGE_LOGS` | `RECORD_TYPE='LOG' AND RECORD:severity_text='INFO'` |
| Debug logs | `SNOWFLAKE$DEBUG_LOGS` | `RECORD_TYPE='LOG' AND RECORD:severity_text in ('DEBUG','TRACE')` |
| Traces | `SNOWFLAKE$TRACES` | `RECORD_TYPE in ('SPAN','SPAN_EVENT')` |
| Metrics | `SNOWFLAKE$METRICS` | `RECORD_TYPE='METRIC'` |

### 4.3 Current behavior in one sentence

Today, our app captures a broader telemetry set than it shares with the provider.

---

## 5. `LOG_LEVEL` vs `LOG_EVENT_LEVEL` vs `effective_*`

### 5.1 `LOG_LEVEL`

- Controls log messages emitted through logging APIs, such as Python logging from our stored procedures.
- Our manifest sets `log_level: INFO`.
- Because `DEBUG_LOGS` is enabled in dev, Snowflake widens the effective level and `DESC APPLICATION` shows `effective_log_level = TRACE`.

That widening is reflected in live data because our event table contains many DEBUG rows.

### 5.2 `LOG_EVENT_LEVEL`

- Snowflake documentation defines this as the threshold for `RECORD_TYPE='EVENT'`.
- Examples of `EVENT` telemetry in docs include Snowpipe, tasks, dynamic tables, SPCS compute pools, and data governance tag activity.
- Our app shows `log_event_level = OFF` and `effective_log_event_level = OFF`.

But our live event table still contains app lifecycle `EVENT` rows, so the practical interpretation is:

- `LOG_EVENT_LEVEL = OFF` does **not** mean "there will be zero `EVENT` rows in all cases".
- It does mean we should be cautious about assuming full `EVENT` capture or provider sharing without explicit `ALL_EVENTS` support.

### 5.3 Why Snowsight shows "Log event level: No logs"

That UI is consistent with `effective_log_event_level = OFF`, but it is easy to misread.

What it **does** mean:

- the app is not configured to broadly capture `RECORD_TYPE='EVENT'` data for diagnostics

What it does **not** safely mean:

- that the event table contains no `EVENT` rows whatsoever

---

## 6. Current provider-sharing matrix

Given the current manifest and current dev enablement state:

| Data category | Captured in consumer event table? | Shared with provider today? | Why |
|---|---|---|---|
| `LOG` at `FATAL` / `ERROR` / `WARN` | Yes | Yes | Covered by `ERRORS_AND_WARNINGS` |
| `LOG` at `INFO` | Yes | No | No `USAGE_LOGS` definition |
| `LOG` at `DEBUG` / `TRACE` | Yes | Yes in dev | `DEBUG_LOGS` is enabled |
| `SPAN` / `SPAN_EVENT` | Yes | No | No `TRACES` definition |
| `METRIC` | Yes | No | No `METRICS` definition |
| `EVENT` | Observed yes | No | No `ALL_EVENTS` definition |

This is the cleanest summary of our current gap:

- consumer-side observability is reasonably rich
- provider-side observability is still mostly "errors and debug logs", not a full support/troubleshooting picture

---

## 7. Installation, upgrades, and provider-sharing behavior

### 7.1 Install-time behavior

Per Snowflake docs:

- Required event definitions are enabled automatically when the app is installed.
- If the consumer does not already have an active event table, events emitted by the app are discarded.
- With required event definitions present, event sharing for those required definitions is effectively enabled during install and cannot later be turned off.

### 7.2 Upgrade behavior

This is where the earlier Cortex analysis needed correction.

For upgrades:

- unchanged definitions retain their existing enabled/disabled status
- **new** event definitions are **not enabled automatically**
- this is true for both required and optional definitions
- if a definition changes between required and optional, it still retains its prior status

So if we add `USAGE_LOGS`, `TRACES`, `METRICS`, or `ALL_EVENTS` in a future patch:

- existing consumer installs will need an explicit review/enable step
- we cannot assume new mandatory definitions silently turn on during upgrade

### 7.3 Other sharing constraints that matter

- event sharing is same-region only
- historical events are not shared retroactively
- consumers pay ingest/storage cost for their event table
- once a consumer has shared events, they cannot revoke provider access to already shared historical copies

---

## 8. Recommendations for our app

### 8.1 Minimum recommendation

If we want provider-side troubleshooting to include normal operational success/failure context, add:

```yaml
- type: USAGE_LOGS
  sharing: MANDATORY
```

Reason:

- our app emits substantial INFO logs
- INFO logs usually carry success-path and state-transition context that is missing from errors-only sharing

### 8.2 Stronger recommendation for observability completeness

Consider evolving to:

```yaml
telemetry_event_definitions:
  - type: ERRORS_AND_WARNINGS
    sharing: MANDATORY
  - type: USAGE_LOGS
    sharing: MANDATORY
  - type: TRACES
    sharing: MANDATORY
  - type: METRICS
    sharing: MANDATORY
  - type: DEBUG_LOGS
    sharing: OPTIONAL
```

Rationale:

- `USAGE_LOGS` fills the INFO gap
- `TRACES` allows provider-side correlation and span-level troubleshooting
- `METRICS` gives provider-side health visibility
- `DEBUG_LOGS` remains optional so consumers can opt out of verbose diagnostics

### 8.3 `ALL_EVENTS` decision

`ALL_EVENTS` is optional from a support perspective.

Add it only if we decide provider access to app lifecycle/platform `EVENT` rows is operationally valuable enough to justify broader sharing.

Today:

- we observe lifecycle `EVENT` rows in the consumer event table
- they are not provider-shared
- we do not yet depend on them for the OTLP export troubleshooting path

### 8.4 Container-app caveat

Snowflake docs say Native Apps **with Snowpark Container Services** currently support only the `ALL` event definition.

Our current app is not in that category, which is consistent with the fact that named definitions like `ERRORS_AND_WARNINGS` and `DEBUG_LOGS` are working live in dev.

---

## 9. Verification commands

### 9.1 Inspect current app telemetry settings

```bash
PRIVATE_KEY_PASSPHRASE=qwerty123 snow sql -c dev --query "DESC APPLICATION SPLUNK_OBSERVABILITY_DEV_APP"
```

### 9.2 Inspect current event definitions

```bash
PRIVATE_KEY_PASSPHRASE=qwerty123 snow sql -c dev --query "SHOW TELEMETRY EVENT DEFINITIONS IN APPLICATION SPLUNK_OBSERVABILITY_DEV_APP"
```

### 9.3 Confirm active event table

```bash
PRIVATE_KEY_PASSPHRASE=qwerty123 snow sql -c dev --query "SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT"
```

### 9.4 Count app telemetry by record type

```sql
SELECT
  RECORD_TYPE,
  COUNT(*) AS row_count
FROM SNOWFLAKE.TELEMETRY.EVENTS
WHERE RESOURCE_ATTRIBUTES:"snow.application.name"::STRING = 'SPLUNK_OBSERVABILITY_DEV_APP'
  AND TIMESTAMP >= DATEADD('day', -7, CURRENT_TIMESTAMP())
GROUP BY 1
ORDER BY 1;
```

### 9.5 Inspect app logs

```sql
SELECT
  TIMESTAMP,
  RECORD:"severity_text"::STRING AS severity,
  SCOPE:"name"::STRING AS scope_name,
  VALUE::STRING AS message
FROM SNOWFLAKE.TELEMETRY.EVENTS
WHERE RESOURCE_ATTRIBUTES:"snow.application.name"::STRING = 'SPLUNK_OBSERVABILITY_DEV_APP'
  AND RECORD_TYPE = 'LOG'
  AND TIMESTAMP >= DATEADD('hour', -24, CURRENT_TIMESTAMP())
ORDER BY TIMESTAMP DESC;
```

### 9.6 Inspect lifecycle `EVENT` rows

```sql
SELECT
  TIMESTAMP,
  RECORD:"name"::STRING AS event_name,
  RECORD:"severity_text"::STRING AS severity,
  VALUE
FROM SNOWFLAKE.TELEMETRY.EVENTS
WHERE RESOURCE_ATTRIBUTES:"snow.application.name"::STRING = 'SPLUNK_OBSERVABILITY_DEV_APP'
  AND RECORD_TYPE = 'EVENT'
ORDER BY TIMESTAMP DESC;
```

### 9.7 Inspect failure-path logs for OTLP export testing

```sql
SELECT
  TIMESTAMP,
  RECORD:"severity_text"::STRING AS severity,
  VALUE::STRING AS message,
  RECORD_ATTRIBUTES
FROM SNOWFLAKE.TELEMETRY.EVENTS
WHERE RESOURCE_ATTRIBUTES:"snow.application.name"::STRING = 'SPLUNK_OBSERVABILITY_DEV_APP'
  AND RECORD_TYPE = 'LOG'
  AND TIMESTAMP >= DATEADD('minute', -30, CURRENT_TIMESTAMP())
  AND (
    VALUE::STRING ILIKE '%otlp%'
    OR VALUE::STRING ILIKE '%export%'
    OR VALUE::STRING ILIKE '%retry%'
    OR VALUE::STRING ILIKE '%grpc%'
  )
ORDER BY TIMESTAMP DESC;
```

---

## 10. Notes for our retry/failure testing

For the gRPC failure-path test we are preparing:

- the authoritative consumer-side signals will be:
  - `SNOWFLAKE.TELEMETRY.EVENTS`
  - `SPLUNK_OBSERVABILITY_DEV_APP._METRICS.PIPELINE_HEALTH`
- we should primarily expect failure evidence in:
  - `LOG` rows emitted by our Python code
  - potentially `SPAN_EVENT` rows if exceptions surface through traced handlers
- we should **not** rely on provider sharing alone to validate the behavior because:
  - current manifest definitions do not cover INFO logs, traces, metrics, or events
  - provider sharing is a subset of the consumer event-table picture

That is why the live failure test should first validate the consumer event table and health table, then separately inform any manifest-sharing changes we decide to make.

---

## 11. What was corrected from the Cortex output

Use this as a quick "do not repeat the old mistake" checklist:

| Claim from Cortex | Corrected position |
|---|---|
| Event definitions only affect provider sharing, not consumer capture | Too strong and misleading. Enabled definitions can widen effective log/trace levels, which changes what is collected in the consumer event table |
| New mandatory definitions are auto-enabled on upgrade | Incorrect. New definitions are not auto-enabled on upgrade, regardless of whether they are mandatory or optional |
| `effective_log_event_level = OFF` means no `EVENT` rows | Not supported by our live data. We observe lifecycle `EVENT` rows anyway |

---

## 12. Sources used for this document

Snowflake docs validated via Firecrawl:

- `https://docs.snowflake.com/en/developer-guide/native-apps/ui-consumer-enable-logging`
- `https://docs.snowflake.com/en/developer-guide/native-apps/event-definition`
- `https://docs.snowflake.com/en/developer-guide/logging-tracing/telemetry-levels`
- `https://docs.snowflake.com/en/sql-reference/sql/desc-application`

Live SQL probes run on 2026-04-10:

- `DESC APPLICATION SPLUNK_OBSERVABILITY_DEV_APP`
- `SHOW TELEMETRY EVENT DEFINITIONS IN APPLICATION SPLUNK_OBSERVABILITY_DEV_APP`
- `SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT`
- targeted queries against `SNOWFLAKE.TELEMETRY.EVENTS`

---

## 13. Changelog

| Date | Change |
|---|---|
| 2026-04-10 | Rewrote the document around Native App-specific telemetry behavior, corrected Cortex upgrade/capture assumptions, added current live state, sharing matrix, and verification queries |
| 2026-04-07 | Initial account/session telemetry note |
