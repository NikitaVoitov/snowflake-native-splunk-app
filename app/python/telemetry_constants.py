"""OTel attribute name constants for the Snowflake telemetry contract.

Defines all attribute names as plain strings to avoid dependency on the stale
``opentelemetry-semantic-conventions`` package (Snowflake Anaconda channel
ships v0.44b0 which uses the old ``db.system`` instead of the stable
``db.system.name``).
"""

from __future__ import annotations

# ── OTel Stable Database Semantic Conventions ─────────────────────
DB_SYSTEM_NAME = "db.system.name"
DB_NAMESPACE = "db.namespace"
DB_OPERATION_NAME = "db.operation.name"
DB_COLLECTION_NAME = "db.collection.name"
DB_QUERY_TEXT = "db.query.text"
DB_QUERY_SUMMARY = "db.query.summary"

# ── Snowflake Custom Attributes ──────────────────────────────────
# Only attributes with no raw snow.* equivalent from the event table.
# Raw snow.database.name, snow.schema.name, snow.warehouse.name, and
# snow.query.id are passed through verbatim — no snowflake.* alias needed.
SNOWFLAKE_ACCOUNT_NAME = "snowflake.account.name"
SNOWFLAKE_HANDLER_NAME = "snowflake.handler.name"
SNOWFLAKE_RECORD_TYPE = "snowflake.record_type"

# ── OTel GenAI Semantic Conventions ──────────────────────────────
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_CONVERSATION_ID = "gen_ai.conversation.id"

# ── Resource & Mapper Scope Constants ────────────────────────────
SERVICE_NAME = "service.name"
MAPPER_SCOPE_NAME = "splunk.snowflake.native_app.telemetry_mapper"

# ── Exception Attribute Constants ────────────────────────────────
EXCEPTION_TYPE = "exception.type"
EXCEPTION_MESSAGE = "exception.message"
EXCEPTION_STACKTRACE = "exception.stacktrace"

# ── Project-Standard Fixed Values ────────────────────────────────
DB_SYSTEM_SNOWFLAKE = "snowflake"
GEN_AI_PROVIDER_SNOWFLAKE = "snowflake"
DEFAULT_SERVICE_NAME = "splunk-snowflake-native-app"

# ── Projected Column Name Constants (from §8 extraction templates) ─
COL_TRACE_ID = "trace_id"
COL_SPAN_ID = "span_id"
COL_PARENT_SPAN_ID = "parent_span_id"
COL_SPAN_NAME = "span_name"
COL_SPAN_KIND = "span_kind"
COL_STATUS_CODE = "status_code"
COL_STATUS_MESSAGE = "status_message"
COL_START_TIME = "start_time"
COL_END_TIME = "end_time"
COL_DB_USER = "db_user"
COL_EXEC_TYPE = "exec_type"
COL_EXEC_NAME = "exec_name"
COL_QUERY_ID = "query_id"
COL_WAREHOUSE_NAME = "warehouse_name"
COL_DATABASE_NAME = "database_name"
COL_SCHEMA_NAME = "schema_name"
COL_SDK_LANGUAGE = "sdk_language"
COL_RECORD_ATTRIBUTES = "RECORD_ATTRIBUTES"
COL_RESOURCE_ATTRIBUTES = "RESOURCE_ATTRIBUTES"

# SPAN_EVENT projected columns
COL_EVENT_NAME = "event_name"
COL_EVENT_TIME = "event_time"
COL_EXCEPTION_MESSAGE = "exception_message"
COL_EXCEPTION_TYPE = "exception_type"
COL_EXCEPTION_STACKTRACE = "exception_stacktrace"
COL_EXCEPTION_ESCAPED = "exception_escaped"

# LOG projected columns
COL_LOG_TIME = "log_time"
COL_MESSAGE = "message"
COL_SEVERITY_TEXT = "severity_text"
COL_SEVERITY_NUMBER = "severity_number"
COL_SCOPE_NAME = "scope_name"

# METRIC projected columns
COL_METRIC_TIME = "metric_time"
COL_METRIC_START_TIME = "metric_start_time"
COL_METRIC_NAME = "metric_name"
COL_METRIC_DESCRIPTION = "metric_description"
COL_METRIC_UNIT = "metric_unit"
COL_METRIC_TYPE = "metric_type"
COL_VALUE_TYPE = "value_type"
COL_AGGREGATION_TEMPORALITY = "aggregation_temporality"
COL_IS_MONOTONIC = "is_monotonic"
COL_METRIC_VALUE = "metric_value"

# AI Observability projected columns (§8.5 additions)
COL_SPAN_TYPE = "span_type"
COL_AGENT_NAME = "agent_name"
COL_OBJECT_TYPE = "object_type"
COL_RUN_NAME = "run_name"
COL_RECORD_ID = "record_id"

# ── AI Observability Fallback Keys (in RECORD_ATTRIBUTES) ────────
AI_OBS_COST_MODEL = "ai.observability.cost.model"
AI_OBS_COST_INPUT_TOKENS = "ai.observability.cost.num_prompt_tokens"
AI_OBS_COST_OUTPUT_TOKENS = "ai.observability.cost.num_completion_tokens"
AI_OBS_OBJECT_NAME = "snow.ai.observability.object.name"

# ── Span Kind Mapping ────────────────────────────────────────────
SPAN_KIND_MAP: dict[str, int] = {
    "SPAN_KIND_INTERNAL": 0,
    "SPAN_KIND_SERVER": 1,
    "SPAN_KIND_CLIENT": 2,
    "SPAN_KIND_PRODUCER": 3,
    "SPAN_KIND_CONSUMER": 4,
}

# ── Status Code Mapping ─────────────────────────────────────────
STATUS_CODE_MAP: dict[str, int] = {
    "STATUS_CODE_UNSET": 0,
    "STATUS_CODE_OK": 1,
    "STATUS_CODE_ERROR": 2,
}
