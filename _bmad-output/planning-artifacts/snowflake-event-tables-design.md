# Snowflake Event Tables List Design


## Decision

We will represent each selected Snowflake event table in the UI with three dedicated columns:

- **Collection**
- **Telemetry types**
- **Telemetry sources**

This replaces the earlier idea of a single overloaded `source type` field and makes the list easier to scan, compare, and filter.

## Context

Snowflake event tables use a predefined schema, so the main differences between one event table and another are not structural. Instead, the meaningful distinctions come from:

- where the event table is associated for collection, such as account or database scope
- which telemetry record types are present in the table
- which Snowflake objects or executables generated those records, as indicated by resource attributes

Snowflake documents row-level telemetry kinds through `RECORD_TYPE`, including `LOG`, `SPAN`, `SPAN_EVENT`, `METRIC`, and `EVENT`.
Snowflake also documents `RESOURCE_ATTRIBUTES` as attributes that describe the source of an event in terms of Snowflake objects and execution context.

## Why this design

Using three dedicated columns is clearer than combining everything into one field because it separates three different user questions:

- **Collection** answers: where is this event table collecting from?
- **Telemetry types** answers: what kinds of telemetry are inside?
- **Telemetry sources** answers: what generated that telemetry?

This matches Snowflake’s model more closely than a single label because collection scope, record type, and source attributes are distinct concepts in the underlying telemetry data.

## Column definitions

### Collection

**Purpose:** Show where the event table is associated for telemetry collection.

**Display format:**
- `Account_name`
- `Database_name`

**Rationale:** Snowflake supports associating an event table with either the account or a database, and database association takes precedence for objects in that database.

**Notes:**
- We use the label **Collection** instead of `Scope` to avoid confusion with Snowflake’s `SCOPE` column, which is a different field used for log code namespace and not the collection boundary.

### Telemetry types

**Purpose:** Show the distinct kinds of telemetry present in the event table.

**Source:** Derived from unique observed `RECORD_TYPE` values.

**UI normalization rules:**
- `LOG` -> `Logs`
- `SPAN` -> `Traces`
- `SPAN_EVENT` -> `Traces`
- `METRIC` -> `Metrics`
- `EVENT` -> `Events`

**Rationale:** Although `SPAN` and `SPAN_EVENT` are separate record types in Snowflake, users will usually understand both as trace telemetry, so we normalize them into one UI label.

**Display examples:**
- `Logs`
- `Logs, Traces`
- `Logs, Traces, Metrics`
- `Events`

### Telemetry sources

**Purpose:** Show which kinds of Snowflake sources generated telemetry in the event table.

**Source:** Derived from selected `RESOURCE_ATTRIBUTES` values, especially stable identifiers such as executable type, executable name, and app-related attributes.

**Why we chose this name:**  
We prefer **Telemetry sources** over **Resources** because it communicates the actual user question more clearly: *what generated telemetry in this table?* Snowflake describes `RESOURCE_ATTRIBUTES` as describing the source of an event, so this label aligns well with both the product UX and the underlying metadata.

**Examples of displayed source categories:**
- `StoredProc`
- `Function`
- `StreamlitApp`
- `SnowServices`
- `NativeApp`

**Notes:**
- This column should show normalized source categories, not raw JSON and not every distinct attribute value.
- We should derive it from a controlled subset of `RESOURCE_ATTRIBUTES` keys so the UI stays stable and readable.

## Normalization rules

### Collection

Map the event table association into one of:
- `Account`
- `Database: <db_name>`

### Telemetry types

Collect distinct `RECORD_TYPE` values from polled rows and normalize them as follows:

| Raw value | UI value |
|---|---|
| `LOG` | `Logs` |
| `SPAN` | `Traces` |
| `SPAN_EVENT` | `Traces` |
| `METRIC` | `Metrics` |
| `EVENT` | `Events` |

If both `SPAN` and `SPAN_EVENT` exist, show only one `Traces` label.

### Telemetry sources

Derive source categories from prioritized `RESOURCE_ATTRIBUTES` keys. 

Recommended priority order:
1. `snow.executable.type` 
2. `snow.executable.name` 
3. Native App-related attributes
4. Database and schema attributes for supplemental labeling only

Recommended output behavior:
- show a short normalized list of source categories
- deduplicate values
- sort consistently
- avoid low-value noisy fields such as session-like or highly granular identifiers unless used in drill-down views

The most important source discriminator for our Telemetry sources column is snow.executable.type, and across Snowflake docs the following source families are clearly confirmed.

| UI source family                    | How to detect                                                                                                                                              | Notes                                                                                                                                                    |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Stored procedures       | snow.executable.type = 'PROCEDURE' is documented in Snowflake examples and translated docs snippets.                                              | Snowflake describes procedures as executable event sources in RESOURCE_ATTRIBUTES.                                                              |
| Functions / UDFs         | snow.executable.type = 'FUNCTION' is shown in Snowflake examples.                                                                              | The docs describe function executions as span sources and use function names in snow.executable.name.                                           |
| SQL queries                | snow.executable.type = 'QUERY' is explicitly called out in Snowflake tracing docs for traced SQL statements.                                     | This is useful if you want to distinguish SQL executed inside procedures or UDF contexts.                                                       |
| Streamlit apps          | Detect Streamlit through executable metadata; Snowflake explicitly lists Streamlit apps as executable sources and trace UI filters.            | Good user-facing label: Streamlit apps.                                                                                                       |
| SnowServices               | Detect through executable metadata; the event-table docs explicitly mention SnowService as an executable source category.                         | Good user-facing label: SnowServices.                                                                                                           |
| Dynamic tables data-flakes          | snow.executable.type = 'DYNAMIC_TABLE' is explicitly documented for dynamic-table events. data-flakes                                                      | These rows are EVENT records for refresh status monitoring. data-flakes                                                                                  |
| Iceberg automated refresh  | Special-case EVENT rows with Iceberg-specific resource attributes such as catalog integration, catalog table, database, schema, and table names.  | Snowflake says only a limited attribute set is populated for this source.                                                                       |
| Native Apps                | Detect via snow.app.consumer.*, snow.app.*, and listing/package attributes in RESOURCE_ATTRIBUTES.                                                | Native App context is documented through app attributes rather than a single clearly documented executable-type value on the event-table page.  |

I would not treat RESOURCE_ATTRIBUTES as a single exact enum of sources, because Snowflake documents both executable-centric sources and non-executable source context such as database, schema, table, warehouse, query, session, and app metadata. In practice, that means your UI should derive Telemetry sources from a prioritized subset, not from every distinct key-value pair present in the JSON.

For a stable product enum, I would normalize to these labels first: Stored procedures, Functions, SQL queries, Streamlit apps, SnowServices, Dynamic tables, Iceberg refresh, and Native Apps. Then derive them in this priority order: snow.executable.type first, Native App snow.app.* attributes second, and Iceberg-specific catalog/table fields as a special-case fallback when normal executable attributes are absent.

You can implement the Telemetry sources column with rules like these:

| Detection rule                                                                                        | Show in UI                  |
| ----------------------------------------------------------------------------------------------------- | --------------------------- |
| snow.executable.type = 'PROCEDURE'                                                           | Stored procedures  |
| snow.executable.type = 'FUNCTION'                                                        | Functions      |
| snow.executable.type = 'QUERY'                                                               | SQL queries        |
| Streamlit executable context present                                                    | Streamlit apps  |
| SnowService executable context present                                                       | SnowServices       |
| snow.executable.type = 'DYNAMIC_TABLE' data-flakes                                                    | Dynamic tables data-flakes  |
| Iceberg refresh-specific resource keys present and normal executable keys absent/irrelevant  | Iceberg refresh    |
| Any snow.app.* / consumer / listing / package attributes present                             | Native Apps        |

## UX principles

This design improves usability in several ways:

- It avoids overloading one column with multiple meanings.
- It makes filtering and sorting easier.
- It helps users distinguish event tables that share the same Snowflake schema but differ in scope, telemetry mix, or source categories.
- It keeps the main list readable while still allowing raw Snowflake values to be exposed in detail views if needed.

## Example rows

| Event table | Collection | Telemetry types | Telemetry sources |
|---|---|---|---|
| `OBSERVABILITY_EVENTS` | `Account` | `Logs, Traces, Metrics` | `Stored procedures, Functions` |
| `APP_TELEMETRY_EVENTS` | `Database: APP_DB` | `Logs, Metrics` | `Native Apps` |
| `STREAMLIT_EVENTS` | `Database: ANALYTICS` | `Logs, Traces` | `Streamlit apps` |
| `ICEBERG_EVENTS` | `Database: CATALOG_DB` | `Events` | `Iceberg operations` |

## Final schema

The final list view for selected Snowflake event tables will use these columns:

- **Collection**
- **Telemetry types**
- **Telemetry sources**

This is the approved representation for the event tables list in our Snowflake observability native app.