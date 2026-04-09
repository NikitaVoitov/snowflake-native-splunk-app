"""Shared fixtures for integration tests against real Snowflake + OTel collector."""

from __future__ import annotations

import base64
import contextlib
import json
import os
import re
import shlex
import ssl
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest


ACCOUNT_NAME = "LFB71918"
APP_NAME = "SPLUNK_OBSERVABILITY_DEV_APP"
DEFAULT_COLLECTOR_SSH_HOST = "otelcol"
DEFAULT_COLLECTOR_JOURNAL_UNIT = "splunk-otel-collector"
DEFAULT_COLLECTOR_JOURNAL_SINCE = "15 minutes ago"
DEFAULT_COLLECTOR_JOURNAL_CONTEXT = "20"
DEFAULT_SPLUNK_EXPORT_URL = (
    "https://eda.israelcentral.cloudapp.azure.com:8089/services/search/jobs/export"
)
DEFAULT_O11Y_RAW_MTS_RESOLUTION_MS = 1000
DEFAULT_O11Y_RAW_MTS_BUFFER_MS = 60_000

_GENERATION_SQL = """
ALTER SESSION SET TRACE_LEVEL = 'ALWAYS';
ALTER SESSION SET LOG_LEVEL = 'DEBUG';
ALTER SESSION SET METRIC_LEVEL = 'ALL';
ALTER SESSION SET ENABLE_UNHANDLED_EXCEPTIONS_REPORTING = TRUE;

CALL {app}.APP_PUBLIC.generate_test_spans('{test_id}');
CALL {app}.APP_PUBLIC.generate_test_logs('{test_id}');

EXECUTE IMMEDIATE $$
BEGIN
    CALL {app}.APP_PUBLIC.generate_test_exception('{test_id}');
EXCEPTION
    WHEN STATEMENT_ERROR THEN
        RETURN 'ignored expected integration-test exception';
END;
$$;

SELECT {app}.APP_PUBLIC.generate_test_udf_telemetry(42, '{test_id}');
"""

_RICH_GENERATION_SQL = """
ALTER SESSION SET TRACE_LEVEL = 'ALWAYS';
ALTER SESSION SET LOG_LEVEL = 'DEBUG';
ALTER SESSION SET METRIC_LEVEL = 'ALL';
ALTER SESSION SET ENABLE_UNHANDLED_EXCEPTIONS_REPORTING = TRUE;

EXECUTE IMMEDIATE $$
DECLARE
    udf_result NUMBER;
    direct_count NUMBER;
BEGIN
    SELECT 1 INTO :direct_count;
    SELECT COUNT(*) INTO :direct_count FROM TABLE(GENERATOR(ROWCOUNT => 5));

    CALL {app}.APP_PUBLIC.generate_test_logs('{test_id}');
    CALL {app}.APP_PUBLIC.generate_test_spans('{test_id}');
    SELECT {app}.APP_PUBLIC.generate_test_udf_telemetry(42, '{test_id}')
      INTO :udf_result;

    BEGIN
        CALL {app}.APP_PUBLIC.generate_test_exception('{test_id}');
    EXCEPTION
        WHEN STATEMENT_ERROR THEN
            NULL;
    END;

    RETURN TO_VARCHAR(COALESCE(udf_result, 0) + COALESCE(direct_count, 0));
END;
$$;
"""

_TARGET_TRACES_CTE = """
WITH target_traces AS (
    SELECT DISTINCT TRACE:"trace_id"::STRING AS trace_id
    FROM SNOWFLAKE.TELEMETRY.EVENTS
    WHERE RECORD_TYPE = 'SPAN'
      AND RESOURCE_ATTRIBUTES:"snow.application.name"::STRING = '{app}'
      AND TIMESTAMP >= DATEADD('minute', -{minutes_back}, CURRENT_TIMESTAMP())
      AND RECORD_ATTRIBUTES:"test.id"::STRING = '{test_id}'
)
"""

_TARGET_SESSIONS_CTE = """
WITH target_sessions AS (
    SELECT DISTINCT RESOURCE_ATTRIBUTES:"snow.session.id"::NUMBER AS session_id
    FROM SNOWFLAKE.TELEMETRY.EVENTS
    WHERE RECORD_TYPE = 'SPAN'
      AND RESOURCE_ATTRIBUTES:"snow.application.name"::STRING = '{app}'
      AND TIMESTAMP >= DATEADD('minute', -{minutes_back}, CURRENT_TIMESTAMP())
      AND RECORD_ATTRIBUTES:"test.id"::STRING = '{test_id}'
)
"""

_SPAN_EXTRACTION_SQL = """
{target_traces_cte}
SELECT
    TRACE:"trace_id"::STRING              AS trace_id,
    TRACE:"span_id"::STRING               AS span_id,
    RECORD:"name"::STRING                 AS span_name,
    RECORD:"kind"::STRING                 AS span_kind,
    RECORD:"parent_span_id"::STRING       AS parent_span_id,
    RECORD:"status":"code"::STRING        AS status_code,
    RECORD:"status":"message"::STRING     AS status_message,
    TIMESTAMP                             AS end_time,
    START_TIMESTAMP                       AS start_time,
    RESOURCE_ATTRIBUTES:"db.user"::STRING AS db_user,
    RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING AS exec_type,
    RESOURCE_ATTRIBUTES:"snow.executable.name"::STRING AS exec_name,
    RESOURCE_ATTRIBUTES:"snow.query.id"::STRING AS query_id,
    RESOURCE_ATTRIBUTES:"snow.warehouse.name"::STRING AS warehouse_name,
    RESOURCE_ATTRIBUTES:"snow.database.name"::STRING AS database_name,
    RESOURCE_ATTRIBUTES:"snow.schema.name"::STRING AS schema_name,
    RESOURCE_ATTRIBUTES:"telemetry.sdk.language"::STRING AS sdk_language,
    RECORD_ATTRIBUTES,
    RESOURCE_ATTRIBUTES
FROM SNOWFLAKE.TELEMETRY.EVENTS
WHERE RECORD_TYPE = 'SPAN'
  AND TIMESTAMP >= DATEADD('minute', -{minutes_back}, CURRENT_TIMESTAMP())
  AND TRACE:"trace_id"::STRING IN (SELECT trace_id FROM target_traces)
ORDER BY TIMESTAMP DESC
LIMIT 200
"""

_SPAN_EVENT_EXTRACTION_SQL = """
{target_traces_cte}
SELECT
    TRACE:"trace_id"::STRING              AS trace_id,
    TRACE:"span_id"::STRING               AS span_id,
    RECORD:"name"::STRING                 AS event_name,
    TIMESTAMP                             AS event_time,
    RECORD_ATTRIBUTES:"exception.message"::STRING    AS exception_message,
    RECORD_ATTRIBUTES:"exception.type"::STRING       AS exception_type,
    RECORD_ATTRIBUTES:"exception.stacktrace"::STRING AS exception_stacktrace,
    RECORD_ATTRIBUTES:"exception.escaped"::BOOLEAN   AS exception_escaped,
    RECORD_ATTRIBUTES,
    RESOURCE_ATTRIBUTES
FROM SNOWFLAKE.TELEMETRY.EVENTS
WHERE RECORD_TYPE = 'SPAN_EVENT'
  AND TIMESTAMP >= DATEADD('minute', -{minutes_back}, CURRENT_TIMESTAMP())
  AND TRACE:"trace_id"::STRING IN (SELECT trace_id FROM target_traces)
ORDER BY TIMESTAMP DESC
LIMIT 200
"""

_LOG_EXTRACTION_SQL = """
SELECT
    TIMESTAMP                             AS log_time,
    VALUE::STRING                         AS message,
    RECORD:"severity_text"::STRING        AS severity_text,
    RECORD:"severity_number"::NUMBER      AS severity_number,
    SCOPE:"name"::STRING                  AS scope_name,
    RECORD_ATTRIBUTES:"log.iostream"::STRING       AS log_iostream,
    RECORD_ATTRIBUTES:"code.filepath"::STRING      AS code_filepath,
    RECORD_ATTRIBUTES:"code.function"::STRING      AS code_function,
    RECORD_ATTRIBUTES:"code.lineno"::NUMBER        AS code_lineno,
    RECORD_ATTRIBUTES:"code.namespace"::STRING     AS code_namespace,
    RECORD_ATTRIBUTES:"thread.id"::NUMBER          AS thread_id,
    RECORD_ATTRIBUTES:"thread.name"::STRING        AS thread_name,
    RECORD_ATTRIBUTES:"exception.message"::STRING  AS exception_message,
    RECORD_ATTRIBUTES:"exception.type"::STRING     AS exception_type,
    RECORD_ATTRIBUTES:"exception.stacktrace"::STRING AS exception_stacktrace,
    RECORD_ATTRIBUTES:"exception.escaped"::BOOLEAN AS exception_escaped,
    RECORD_ATTRIBUTES,
    RESOURCE_ATTRIBUTES
FROM SNOWFLAKE.TELEMETRY.EVENTS
WHERE RECORD_TYPE = 'LOG'
  AND RESOURCE_ATTRIBUTES:"snow.application.name"::STRING = '{app}'
  AND TIMESTAMP >= DATEADD('minute', -{minutes_back}, CURRENT_TIMESTAMP())
  AND (
      VALUE::STRING ILIKE '%{test_id}%'
      OR RECORD_ATTRIBUTES:"exception.message"::STRING ILIKE '%{test_id}%'
  )
  AND UPPER(RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING)
      IN ('PROCEDURE', 'FUNCTION', 'QUERY', 'SQL', 'STATEMENT')
ORDER BY TIMESTAMP DESC
LIMIT 200
"""

_METRIC_EXTRACTION_SQL = """
{target_sessions_cte}
SELECT
    TIMESTAMP                             AS metric_time,
    START_TIMESTAMP                       AS metric_start_time,
    RECORD:"metric":"name"::STRING        AS metric_name,
    RECORD:"metric":"description"::STRING AS metric_description,
    RECORD:"metric":"unit"::STRING        AS metric_unit,
    RECORD:"metric_type"::STRING          AS metric_type,
    RECORD:"value_type"::STRING           AS value_type,
    RECORD:"aggregation_temporality"::STRING AS aggregation_temporality,
    RECORD:"is_monotonic"::BOOLEAN        AS is_monotonic,
    VALUE                                 AS metric_value,
    RECORD_ATTRIBUTES,
    RESOURCE_ATTRIBUTES
FROM SNOWFLAKE.TELEMETRY.EVENTS
WHERE RECORD_TYPE = 'METRIC'
  AND RESOURCE_ATTRIBUTES:"snow.application.name"::STRING = '{app}'
  AND TIMESTAMP >= DATEADD('minute', -{minutes_back}, CURRENT_TIMESTAMP())
  AND RESOURCE_ATTRIBUTES:"snow.session.id"::NUMBER IN (
      SELECT session_id FROM target_sessions
  )
  AND UPPER(RESOURCE_ATTRIBUTES:"snow.executable.type"::STRING)
      IN ('PROCEDURE', 'FUNCTION', 'QUERY', 'SQL', 'STATEMENT')
ORDER BY TIMESTAMP DESC
LIMIT 200
"""

_WAIT_FOR_DATA_SQL = """
WITH target_sessions AS (
    SELECT DISTINCT RESOURCE_ATTRIBUTES:"snow.session.id"::NUMBER AS session_id
    FROM SNOWFLAKE.TELEMETRY.EVENTS
    WHERE RECORD_TYPE = 'SPAN'
      AND RESOURCE_ATTRIBUTES:"snow.application.name"::STRING = '{app}'
      AND TIMESTAMP >= DATEADD('minute', -{minutes_back}, CURRENT_TIMESTAMP())
      AND RECORD_ATTRIBUTES:"test.id"::STRING = '{test_id}'
)
SELECT
    COUNT_IF(
        RECORD_TYPE = 'SPAN'
        AND RECORD_ATTRIBUTES:"test.id"::STRING = '{test_id}'
    ) AS span_rows,
    COUNT_IF(
        RECORD_TYPE = 'LOG'
        AND (
            VALUE::STRING ILIKE '%{test_id}%'
            OR RECORD_ATTRIBUTES:"exception.message"::STRING ILIKE '%{test_id}%'
        )
    ) AS log_rows,
    COUNT_IF(
        RECORD_TYPE = 'METRIC'
        AND RESOURCE_ATTRIBUTES:"snow.session.id"::NUMBER IN (
            SELECT session_id FROM target_sessions
        )
    ) AS metric_rows
FROM SNOWFLAKE.TELEMETRY.EVENTS
WHERE RESOURCE_ATTRIBUTES:"snow.application.name"::STRING = '{app}'
  AND TIMESTAMP >= DATEADD('minute', -{minutes_back}, CURRENT_TIMESTAMP())
"""


def _snow_sql(
    *,
    query: str | None = None,
    filename: str | None = None,
    fmt: str = "JSON_EXT",
) -> str:
    """Execute SQL via ``snow sql -c dev`` and return raw output."""
    if (query is None) == (filename is None):
        raise ValueError("Provide exactly one of query or filename")

    passphrase = os.environ.get("PRIVATE_KEY_PASSPHRASE", "qwerty123")
    cmd = [
        "snow",
        "sql",
        "--connection",
        "dev",
        "--format",
        fmt,
    ]
    if query is not None:
        cmd.extend(["--query", query])
    else:
        cmd.extend(["--filename", filename])
    result = subprocess.run(  # noqa: S603
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "PRIVATE_KEY_PASSPHRASE": passphrase},
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"snow sql failed: {result.stderr}\n{result.stdout}")
    return result.stdout


def _snow_sql_script(sql_script: str, *, fmt: str = "TABLE") -> str:
    """Execute a multi-statement SQL script in a single Snowflake session."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".sql",
        encoding="utf-8",
        delete=False,
    ) as handle:
        handle.write(sql_script)
        path = handle.name

    try:
        return _snow_sql(filename=path, fmt=fmt)
    finally:
        with contextlib.suppress(FileNotFoundError):
            Path(path).unlink()


_KEEP_UPPER = {"RECORD_ATTRIBUTES", "RESOURCE_ATTRIBUTES"}


def _snow_sql_json(query: str) -> list[dict[str, Any]]:
    """Execute SQL and return parsed JSON rows with normalised keys.

    ``snow sql --format JSON_EXT`` emits a pretty-printed JSON array to
    stdout.  Snowflake uppercases unquoted aliases, so we normalise all
    keys to lowercase **except** VARIANT columns that the mapper constants
    reference in uppercase (``RECORD_ATTRIBUTES``, ``RESOURCE_ATTRIBUTES``).
    """
    raw = _snow_sql(query=query).strip()
    if not raw:
        return []
    parsed = json.loads(raw)
    if isinstance(parsed, dict):
        parsed = [parsed]
    return [
        {(k if k in _KEEP_UPPER else k.lower()): v for k, v in row.items()}
        for row in parsed
    ]


def _poll_until_result(
    fetch: Callable[[], Any],
    *,
    timeout_s: int,
    description: str,
) -> Any:
    """Poll until ``fetch`` returns a truthy value or times out."""
    deadline = time.monotonic() + timeout_s
    sleep_s = 2
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            value = fetch()
        except Exception as exc:  # pragma: no cover - exercised in live env only
            last_error = exc
        else:
            if value:
                return value

        time.sleep(sleep_s)
        sleep_s = min(sleep_s * 2, 10)

    if last_error is not None:
        raise AssertionError(
            f"Timed out waiting for {description}: {last_error}",
        ) from last_error
    raise AssertionError(f"Timed out waiting for {description}")


def _collector_journal_excerpt(test_id: str) -> str | None:
    """Return journal lines mentioning the current ``test_id``."""
    host = os.environ.get("OTELCOL_VERIFY_SSH_HOST", DEFAULT_COLLECTOR_SSH_HOST)
    unit = os.environ.get(
        "OTELCOL_VERIFY_JOURNAL_UNIT", DEFAULT_COLLECTOR_JOURNAL_UNIT
    )
    since = os.environ.get(
        "OTELCOL_VERIFY_JOURNAL_SINCE", DEFAULT_COLLECTOR_JOURNAL_SINCE
    )
    context_lines = os.environ.get(
        "OTELCOL_VERIFY_JOURNAL_CONTEXT", DEFAULT_COLLECTOR_JOURNAL_CONTEXT
    )
    remote_cmd = (
        f"sudo journalctl -u {shlex.quote(unit)} "
        f"--since {shlex.quote(since)} --no-pager | "
        f"grep -F -C {shlex.quote(context_lines)} -- {shlex.quote(test_id)}"
    )
    result = subprocess.run(  # noqa: S603
        ["/usr/bin/ssh", host, remote_cmd],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=os.environ.copy(),
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    if result.returncode == 1 and not result.stdout.strip():
        return None
    raise RuntimeError(
        "collector journal lookup failed: "
        f"{result.stderr.strip() or result.stdout.strip()}"
    )


def _splunk_ssl_context() -> ssl.SSLContext:
    """Build the SSL context for Splunk Enterprise REST verification."""
    ca_path = os.environ.get("SPLUNK_ENTERPRISE_CA_CERT_PATH")
    if ca_path:
        return ssl.create_default_context(cafile=ca_path)
    if os.environ.get("SPLUNK_ENTERPRISE_VERIFY_TLS") == "1":
        return ssl.create_default_context()
    # Dev Splunk Enterprise currently serves a self-signed chain.
    return ssl._create_unverified_context()  # noqa: S323


def _splunk_search_results(
    test_id: str,
    *,
    username: str,
    password: str,
) -> list[dict[str, Any]]:
    """Query Splunk Enterprise and return any result rows for ``test_id``."""
    export_url = os.environ.get("SPLUNK_ENTERPRISE_EXPORT_URL", DEFAULT_SPLUNK_EXPORT_URL)
    earliest = os.environ.get("SPLUNK_ENTERPRISE_EARLIEST", "-30m")
    search = (
        f'search index=otelcol "{test_id}" earliest={earliest} '
        "| head 20 | table _time _raw"
    )
    payload = urllib.parse.urlencode(
        {"search": search, "output_mode": "json"},
    ).encode("utf-8")
    basic_auth = base64.b64encode(f"{username}:{password}".encode()).decode(
        "ascii"
    )
    request = urllib.request.Request(  # noqa: S310
        export_url,
        data=payload,
        headers={"Authorization": f"Basic {basic_auth}"},
        method="POST",
    )
    with urllib.request.urlopen(  # noqa: S310
        request,
        context=_splunk_ssl_context(),
        timeout=30,
    ) as response:
        body = response.read().decode("utf-8")

    results: list[dict[str, Any]] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        row = json.loads(stripped)
        result = row.get("result")
        if isinstance(result, dict):
            results.append(result)
    return results


def _o11y_request_json(
    path: str,
    *,
    query: dict[str, str] | None = None,
) -> Any:
    """Call the realm-scoped Splunk Observability REST API and decode JSON."""
    realm = os.environ.get("SPLUNK_REALM")
    token = os.environ.get("SPLUNK_ACCESS_TOKEN")
    if not realm or not token:
        raise RuntimeError(
            "Set SPLUNK_REALM and SPLUNK_ACCESS_TOKEN to enable Splunk O11y checks",
        )

    api_path = path if path.startswith("/") else f"/{path}"
    url = f"https://api.{realm}.observability.splunkcloud.com{api_path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"

    request = urllib.request.Request(url, headers={"X-SF-Token": token})  # noqa: S310
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        body = response.read().decode("utf-8")

    return json.loads(body) if body else None


def _o11y_metric_metadata(metric_name: str) -> dict[str, Any] | None:
    """Retrieve metric metadata for a single metric name."""
    try:
        result = _o11y_request_json(
            f"/v2/metric/{urllib.parse.quote(metric_name, safe='')}",
        )
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise

    return result if isinstance(result, dict) else None


def _o11y_raw_mts(
    metric_name: str,
    *,
    start_ms: int,
    end_ms: int,
    resolution_ms: int = DEFAULT_O11Y_RAW_MTS_RESOLUTION_MS,
) -> dict[str, Any]:
    """Retrieve raw metric time series for one metric name."""
    result = _o11y_request_json(
        "/v1/timeserieswindow",
        query={
            "query": f"sf_metric:{metric_name}",
            "startMS": str(start_ms),
            "endMS": str(end_ms),
            "resolution": str(resolution_ms),
        },
    )
    return result if isinstance(result, dict) else {}


def _o11y_trace_segments(trace_id: str) -> list[int]:
    """List available APM trace segments for a trace ID."""
    result = _o11y_request_json(
        f"/v2/apm/trace/{urllib.parse.quote(trace_id, safe='')}/segments",
    )
    if not isinstance(result, list):
        return []
    return [int(item) for item in result]


def _o11y_trace_segment(
    trace_id: str,
    *,
    segment_timestamp_ms: int,
) -> list[dict[str, Any]]:
    """Download one explicit APM trace segment by trace ID and segment timestamp."""
    result = _o11y_request_json(
        (
            f"/v2/apm/trace/{urllib.parse.quote(trace_id, safe='')}"
            f"/{segment_timestamp_ms}"
        ),
    )
    return result if isinstance(result, list) else []


def _collector_span_blocks(journal_excerpt: str) -> list[list[str]]:
    """Split a collector excerpt into individual span blocks."""
    blocks: list[list[str]] = []
    current: list[str] | None = None

    for line in journal_excerpt.splitlines():
        if "]: Span #" in line:
            if current:
                blocks.append(current)
            current = [line]
            continue

        if current is not None:
            if "]: ResourceSpans #" in line:
                blocks.append(current)
                current = None
                continue
            current.append(line)

    if current:
        blocks.append(current)
    return blocks


def _parse_collector_attr_value(rendered: str) -> Any:
    """Convert collector debug-exporter attr renderings into Python values."""
    if rendered.startswith("Int(") and rendered.endswith(")"):
        with contextlib.suppress(ValueError):
            return int(rendered[4:-1])
    if rendered.startswith("Bool(") and rendered.endswith(")"):
        return rendered[5:-1].strip().lower() == "true"
    if rendered.startswith("Str(") and rendered.endswith(")"):
        return rendered[4:-1]
    return rendered


def _parse_collector_start_time_ms(start_time: str) -> int:
    parsed = datetime.strptime(
        start_time,
        "%Y-%m-%d %H:%M:%S.%f +0000 UTC",
    ).replace(tzinfo=UTC)
    return int(parsed.timestamp() * 1000)


def _maybe_assign_collector_span_field(
    parsed: dict[str, Any],
    content: str,
) -> bool:
    """Populate parsed collector span metadata from one rendered content line."""
    prefix_map = {
        "Trace ID": "trace_id",
        "Parent ID": "parent_span_id",
        "Name": "name",
        "End time": "end_time",
    }
    for prefix, field_name in prefix_map.items():
        if content.startswith(prefix):
            parsed[field_name] = content.split(":", 1)[1].strip()
            return True

    if re.match(r"^ID\s+:", content):
        parsed["span_id"] = content.split(":", 1)[1].strip()
        return True

    if content.startswith("Start time"):
        start_time = content.split(":", 1)[1].strip()
        parsed["start_time"] = start_time
        parsed["segment_timestamp_ms"] = _parse_collector_start_time_ms(start_time)
        return True

    return False


def _extract_collector_attribute_span(
    journal_excerpt: str,
) -> dict[str, Any] | None:
    """Parse the collector span block that carries Snowflake row-count attrs."""
    for block_lines in _collector_span_blocks(journal_excerpt):
        block_text = "\n".join(block_lines)
        if "snow.input.rows" not in block_text or "snow.output.rows" not in block_text:
            continue

        parsed: dict[str, Any] = {
            "attributes": {},
            "raw_block": block_text,
        }
        in_attr_section = False
        for line in block_lines:
            content = line.split("]:", 1)[1].strip() if "]:" in line else line.strip()
            if _maybe_assign_collector_span_field(parsed, content):
                continue
            if content.startswith("Attributes:"):
                in_attr_section = True
                continue
            if content.startswith("Events:"):
                in_attr_section = False
                continue
            if in_attr_section and content.startswith("-> "):
                if ": " not in content[3:]:
                    continue
                attr_key, attr_value = content[3:].split(": ", 1)
                parsed["attributes"][attr_key] = _parse_collector_attr_value(
                    attr_value,
                )

        if parsed.get("trace_id") and parsed.get("span_id"):
            return parsed
    return None


def _collector_trace_excerpt(trace_id: str) -> str | None:
    """Return collector journal lines mentioning a specific trace ID."""
    host = os.environ.get("OTELCOL_VERIFY_SSH_HOST", DEFAULT_COLLECTOR_SSH_HOST)
    unit = os.environ.get(
        "OTELCOL_VERIFY_JOURNAL_UNIT", DEFAULT_COLLECTOR_JOURNAL_UNIT
    )
    since = os.environ.get(
        "OTELCOL_VERIFY_JOURNAL_SINCE", DEFAULT_COLLECTOR_JOURNAL_SINCE
    )
    remote_cmd = (
        f"sudo journalctl -u {shlex.quote(unit)} "
        f"--since {shlex.quote(since)} --no-pager | "
        f"grep -F -C 80 -- {shlex.quote(trace_id)}"
    )
    result = subprocess.run(  # noqa: S603
        ["/usr/bin/ssh", host, remote_cmd],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=os.environ.copy(),
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    if result.returncode == 1 and not result.stdout.strip():
        return None
    raise RuntimeError(
        "collector trace lookup failed: "
        f"{result.stderr.strip() or result.stdout.strip()}"
    )


def _parse_collector_trace_spans(
    journal_excerpt: str,
    *,
    trace_id: str,
) -> list[dict[str, Any]]:
    """Parse all collector span blocks belonging to one trace."""
    parsed_spans: list[dict[str, Any]] = []
    for block_lines in _collector_span_blocks(journal_excerpt):
        parsed: dict[str, Any] = {"attributes": {}}
        in_attr_section = False
        for line in block_lines:
            content = line.split("]:", 1)[1].strip() if "]:" in line else line.strip()
            if _maybe_assign_collector_span_field(parsed, content):
                continue
            if content.startswith("Attributes:"):
                in_attr_section = True
                continue
            if content.startswith("Events:"):
                in_attr_section = False
                continue
            if in_attr_section and content.startswith("-> "):
                if ": " not in content[3:]:
                    continue
                attr_key, attr_value = content[3:].split(": ", 1)
                parsed["attributes"][attr_key] = _parse_collector_attr_value(
                    attr_value,
                )
        if parsed.get("trace_id") == trace_id and parsed.get("span_id"):
            parsed_spans.append(parsed)

    return sorted(
        parsed_spans,
        key=lambda item: (item.get("start_time") or "", item.get("span_id") or ""),
    )


def _normalize_hex_id(value: str | None) -> str:
    """Normalize hex IDs so leading-zero render differences compare cleanly."""
    if value is None:
        return ""
    text = str(value).strip().lower()
    if not text:
        return ""
    return format(int(text, 16), "x")


def _o11y_trace_spans(trace_id: str) -> list[dict[str, Any]]:
    """Return all deduplicated O11y spans for a trace across its segments."""
    segment_timestamps = _o11y_trace_segments(trace_id)
    if not segment_timestamps:
        return []

    seen: set[tuple[Any, ...]] = set()
    spans: list[dict[str, Any]] = []
    for segment_timestamp_ms in segment_timestamps:
        for span in _o11y_trace_segment(
            trace_id,
            segment_timestamp_ms=segment_timestamp_ms,
        ):
            key = (
                span.get("traceId"),
                span.get("spanId"),
                span.get("startTime"),
            )
            if key in seen:
                continue
            seen.add(key)
            spans.append(span)

    return sorted(
        spans,
        key=lambda item: (item.get("startTime", ""), item.get("spanId", "")),
    )


def _wait_for_event_table_rows(test_id: str, *, timeout_s: int) -> str:
    """Poll until a test run has SPAN, LOG, and METRIC rows available."""
    deadline = time.monotonic() + timeout_s
    sleep_s = 2

    while time.monotonic() < deadline:
        rows = _snow_sql_json(
            _WAIT_FOR_DATA_SQL.format(
                app=APP_NAME,
                minutes_back=30,
                test_id=test_id,
            )
        )
        counts = rows[0] if rows else {}
        span_rows = int(counts.get("span_rows") or 0)
        log_rows = int(counts.get("log_rows") or 0)
        metric_rows = int(counts.get("metric_rows") or 0)
        if span_rows > 0 and log_rows > 0 and metric_rows > 0:
            return test_id
        time.sleep(sleep_s)
        sleep_s = min(sleep_s * 2, 10)

    raise AssertionError(
        f"Timed out waiting for Event Table rows for test_id={test_id}",
    )


@pytest.fixture(scope="module")
def unique_test_id() -> str:
    return f"integ_{int(time.time())}_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def run_telemetry_generation(unique_test_id: str) -> str:
    """Generate telemetry in one Snowflake session."""
    _snow_sql_script(
        _GENERATION_SQL.format(app=APP_NAME, test_id=unique_test_id),
        fmt="TABLE",
    )
    return unique_test_id


@pytest.fixture(scope="module")
def wait_for_event_table(run_telemetry_generation: str) -> str:
    """Poll until the current test run's rows appear in the Event Table."""
    return _wait_for_event_table_rows(run_telemetry_generation, timeout_s=90)


@pytest.fixture(scope="module")
def unique_rich_test_id() -> str:
    return f"integ_rich_{int(time.time())}_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def run_rich_telemetry_generation(unique_rich_test_id: str) -> str:
    """Generate a richer mixed SQL/procedure/function trace in one session."""
    _snow_sql_script(
        _RICH_GENERATION_SQL.format(app=APP_NAME, test_id=unique_rich_test_id),
        fmt="TABLE",
    )
    return unique_rich_test_id


@pytest.fixture(scope="module")
def wait_for_rich_event_table(run_rich_telemetry_generation: str) -> str:
    """Poll until the rich trace scenario has landed in the Event Table."""
    return _wait_for_event_table_rows(run_rich_telemetry_generation, timeout_s=150)


@pytest.fixture(scope="module")
def collector_journal_excerpt(
    wait_for_event_table: str,
    live_export_results: dict[str, bool | None],
) -> str:
    """Poll the live collector journal until the exported ``test_id`` appears."""
    assert live_export_results["span_export"] is True
    assert live_export_results["log_export"] is True
    return _poll_until_result(
        lambda: _collector_journal_excerpt(wait_for_event_table),
        timeout_s=90,
        description=f"collector journal evidence for test_id={wait_for_event_table}",
    )


@pytest.fixture(scope="module")
def collector_attribute_span(collector_journal_excerpt: str) -> dict[str, Any]:
    """Return the collector span block with row-count attributes."""
    parsed = _extract_collector_attribute_span(collector_journal_excerpt)
    if not parsed:
        raise AssertionError(
            "Collector journal did not contain a span with "
            "snow.input.rows + snow.output.rows",
        )
    return parsed


@pytest.fixture(scope="module")
def splunk_search_results_fixture(
    wait_for_event_table: str,
    live_export_results: dict[str, bool | None],
) -> list[dict[str, Any]]:
    """Poll Splunk Enterprise REST until exported logs are searchable."""
    assert live_export_results["log_export"] is True

    password = os.environ.get("SPLUNK_ENTERPRISE_PASSWORD")
    if not password:
        pytest.skip(
            "Set SPLUNK_ENTERPRISE_PASSWORD to enable Splunk REST verification",
        )
    username = os.environ.get("SPLUNK_ENTERPRISE_USERNAME", "admin")
    return _poll_until_result(
        lambda: _splunk_search_results(
            wait_for_event_table,
            username=username,
            password=password,
        ),
        timeout_s=90,
        description=f"Splunk Enterprise results for test_id={wait_for_event_table}",
    )


@pytest.fixture(scope="module")
def o11y_access() -> dict[str, str]:
    """Ensure the env has the credentials needed for Splunk O11y REST checks."""
    token = os.environ.get("SPLUNK_ACCESS_TOKEN")
    realm = os.environ.get("SPLUNK_REALM")
    if not token or not realm:
        pytest.skip(
            "Set SPLUNK_ACCESS_TOKEN and SPLUNK_REALM to enable Splunk O11y checks",
        )
    return {"token": token, "realm": realm}


@pytest.fixture(scope="module")
def o11y_metric_window(
    metrics_df: pd.DataFrame,
    o11y_access: dict[str, str],
) -> dict[str, Any]:
    """Derive the exact metric window for the current integration test run."""
    del o11y_access
    if metrics_df.empty:
        pytest.skip("No METRIC rows extracted from Event Table")

    timestamps = pd.to_datetime(metrics_df["metric_time"], utc=True)
    exact_start_ms = int(timestamps.min().value // 1_000_000)
    exact_end_ms = int(timestamps.max().value // 1_000_000)
    metric_names = sorted(
        {
            str(name).strip()
            for name in metrics_df["metric_name"].dropna().tolist()
            if str(name).strip()
        },
    )
    return {
        "metric_names": metric_names,
        "exact_start_ms": exact_start_ms,
        "exact_end_ms": exact_end_ms,
        "query_start_ms": exact_start_ms - DEFAULT_O11Y_RAW_MTS_BUFFER_MS,
        "query_end_ms": exact_end_ms + DEFAULT_O11Y_RAW_MTS_BUFFER_MS,
        "resolution_ms": DEFAULT_O11Y_RAW_MTS_RESOLUTION_MS,
    }


@pytest.fixture(scope="module")
def o11y_metric_metadata_fixture(
    wait_for_event_table: str,
    o11y_metric_window: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Poll Splunk O11y until metric metadata exists for every emitted metric."""
    metric_names = o11y_metric_window["metric_names"]
    if not metric_names:
        pytest.skip("No metric names were extracted from the Event Table")

    def fetch() -> dict[str, dict[str, Any]] | None:
        metadata: dict[str, dict[str, Any]] = {}
        for metric_name in metric_names:
            item = _o11y_metric_metadata(metric_name)
            if not item or item.get("name") != metric_name:
                return None
            metadata[metric_name] = item
        return metadata

    return _poll_until_result(
        fetch,
        timeout_s=120,
        description=f"Splunk O11y metric metadata for test_id={wait_for_event_table}",
    )


@pytest.fixture(scope="module")
def o11y_raw_mts_results(
    wait_for_event_table: str,
    o11y_metric_window: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Poll Splunk O11y raw MTS until each metric has points in the exact run window."""
    metric_names = o11y_metric_window["metric_names"]
    if not metric_names:
        pytest.skip("No metric names were extracted from the Event Table")

    def fetch() -> dict[str, dict[str, Any]] | None:
        results: dict[str, dict[str, Any]] = {}
        for metric_name in metric_names:
            payload = _o11y_raw_mts(
                metric_name,
                start_ms=o11y_metric_window["query_start_ms"],
                end_ms=o11y_metric_window["query_end_ms"],
                resolution_ms=o11y_metric_window["resolution_ms"],
            )
            data = payload.get("data") or {}
            errors = payload.get("errors") or []
            points = [
                (mts_id, ts, value)
                for mts_id, mts_points in data.items()
                for ts, value in mts_points
            ]
            exact_points = [
                (mts_id, ts, value)
                for mts_id, ts, value in points
                if o11y_metric_window["exact_start_ms"]
                <= ts
                <= o11y_metric_window["exact_end_ms"]
            ]
            if not data or not exact_points:
                return None
            results[metric_name] = {
                "payload": payload,
                "errors": errors,
                "mts_count": len(data),
                "point_count": len(points),
                "points_in_exact_window": len(exact_points),
                "first_point_in_exact_window": exact_points[0],
            }
        return results

    return _poll_until_result(
        fetch,
        timeout_s=120,
        description=f"Splunk O11y raw MTS for test_id={wait_for_event_table}",
    )


@pytest.fixture(scope="module")
def o11y_trace_segment_fixture(
    collector_attribute_span: dict[str, Any],
    wait_for_event_table: str,
    o11y_access: dict[str, str],
) -> dict[str, Any]:
    """Poll Splunk O11y APM REST until the collector-derived trace segment is available."""
    del o11y_access

    def fetch() -> dict[str, Any] | None:
        spans = _o11y_trace_spans(collector_attribute_span["trace_id"])
        if not spans:
            return None

        target_span = next(
            (
                span
                for span in spans
                if span.get("spanId") == collector_attribute_span["span_id"]
            ),
            None,
        )
        if target_span is None:
            return None

        return {
            "spans": spans,
            "target_span": target_span,
        }

    return _poll_until_result(
        fetch,
        timeout_s=420,
        description=(
            "Splunk O11y trace segment for "
            f"test_id={wait_for_event_table} trace_id={collector_attribute_span['trace_id']}"
        ),
    )


@pytest.fixture(scope="module")
def spans_df(wait_for_event_table: str) -> pd.DataFrame:
    test_id = wait_for_event_table
    sql = _SPAN_EXTRACTION_SQL.format(
        target_traces_cte=_TARGET_TRACES_CTE.format(
            app=APP_NAME,
            minutes_back=30,
            test_id=test_id,
        ),
        minutes_back=30,
    )
    rows = _snow_sql_json(sql)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@pytest.fixture(scope="module")
def rich_spans_df(wait_for_rich_event_table: str) -> pd.DataFrame:
    test_id = wait_for_rich_event_table
    sql = _SPAN_EXTRACTION_SQL.format(
        target_traces_cte=_TARGET_TRACES_CTE.format(
            app=APP_NAME,
            minutes_back=30,
            test_id=test_id,
        ),
        minutes_back=30,
    )
    rows = _snow_sql_json(sql)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@pytest.fixture(scope="module")
def span_events_df(wait_for_event_table: str) -> pd.DataFrame:
    test_id = wait_for_event_table
    sql = _SPAN_EVENT_EXTRACTION_SQL.format(
        target_traces_cte=_TARGET_TRACES_CTE.format(
            app=APP_NAME,
            minutes_back=30,
            test_id=test_id,
        ),
        minutes_back=30,
    )
    rows = _snow_sql_json(sql)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@pytest.fixture(scope="module")
def rich_span_events_df(wait_for_rich_event_table: str) -> pd.DataFrame:
    test_id = wait_for_rich_event_table
    sql = _SPAN_EVENT_EXTRACTION_SQL.format(
        target_traces_cte=_TARGET_TRACES_CTE.format(
            app=APP_NAME,
            minutes_back=30,
            test_id=test_id,
        ),
        minutes_back=30,
    )
    rows = _snow_sql_json(sql)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@pytest.fixture(scope="module")
def logs_df(wait_for_event_table: str) -> pd.DataFrame:
    sql = _LOG_EXTRACTION_SQL.format(
        app=APP_NAME,
        minutes_back=30,
        test_id=wait_for_event_table,
    )
    rows = _snow_sql_json(sql)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@pytest.fixture(scope="module")
def rich_logs_df(wait_for_rich_event_table: str) -> pd.DataFrame:
    sql = _LOG_EXTRACTION_SQL.format(
        app=APP_NAME,
        minutes_back=30,
        test_id=wait_for_rich_event_table,
    )
    rows = _snow_sql_json(sql)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@pytest.fixture(scope="module")
def metrics_df(wait_for_event_table: str) -> pd.DataFrame:
    test_id = wait_for_event_table
    sql = _METRIC_EXTRACTION_SQL.format(
        target_sessions_cte=_TARGET_SESSIONS_CTE.format(
            app=APP_NAME,
            minutes_back=30,
            test_id=test_id,
        ),
        app=APP_NAME,
        minutes_back=30,
    )
    rows = _snow_sql_json(sql)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@pytest.fixture(scope="module")
def rich_metrics_df(wait_for_rich_event_table: str) -> pd.DataFrame:
    test_id = wait_for_rich_event_table
    sql = _METRIC_EXTRACTION_SQL.format(
        target_sessions_cte=_TARGET_SESSIONS_CTE.format(
            app=APP_NAME,
            minutes_back=30,
            test_id=test_id,
        ),
        app=APP_NAME,
        minutes_back=30,
    )
    rows = _snow_sql_json(sql)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@pytest.fixture(scope="module")
def rich_target_trace_df(rich_spans_df: pd.DataFrame) -> pd.DataFrame:
    """Return the richest trace tree from the rich generation scenario."""
    if rich_spans_df.empty:
        pytest.skip("No rich SPAN rows extracted from Event Table")
    _, trace_df = max(
        rich_spans_df.groupby("trace_id"),
        key=lambda item: len(item[1]),
    )
    return trace_df.sort_values(["start_time", "end_time"]).reset_index(drop=True)


@pytest.fixture(scope="module")
def rich_target_trace_id(rich_target_trace_df: pd.DataFrame) -> str:
    return str(rich_target_trace_df.iloc[0]["trace_id"])
