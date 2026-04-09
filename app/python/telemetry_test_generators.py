"""Telemetry signal generators for integration testing.

Provides stored procedure and UDF handlers that produce controlled,
verifiable telemetry signals (SPANs, SPAN_EVENTs, LOGs, exceptions)
in the Snowflake Event Table.  Each handler accepts a ``test_id``
parameter so that downstream integration tests can correlate the
generated rows with their extraction and mapping assertions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from snowflake.snowpark import Session

log = logging.getLogger(__name__)


def generate_test_spans(session: Session, test_id: str) -> str:
    """SP handler: produce SPAN + SPAN_EVENT rows tagged with *test_id*.

    1. Tags the auto-instrumented procedure span via ``set_span_attribute``.
    2. Adds a non-exception event with custom attributes.
    3. Executes a trivial SQL query to produce an inner SQL-traced span.
    """
    telemetry = _get_telemetry()
    telemetry.set_span_attribute("test.id", test_id)
    telemetry.add_event(
        "test_event_with_attrs",
        {"test.key1": "value1", "test.key2": "value2"},
    )
    session.sql("SELECT 1 AS test_column").collect()
    return f"ok:{test_id}"


def generate_test_logs(session: Session, test_id: str) -> str:  # noqa: ARG001
    """SP handler: produce instrumented LOG rows at INFO and ERROR levels."""
    telemetry = _get_telemetry()
    telemetry.set_span_attribute("test.id", test_id)

    log.info("test log %s", test_id)
    log.error("test error log %s", test_id)
    return f"ok:{test_id}"


def generate_test_exception(session: Session, test_id: str) -> str:  # noqa: ARG001
    """SP handler: raise an exception to produce dual-capture signals.

    Generates both a SPAN_EVENT (exception type) and a LOG (exception)
    row.  The caller should wrap the invocation in TRY/CATCH or expect
    the procedure to fail.
    """
    telemetry = _get_telemetry()
    telemetry.set_span_attribute("test.id", test_id)
    raise RuntimeError(f"deliberate_test_exception_{test_id}")


def generate_test_udf_telemetry(x: int, test_id: str) -> int:
    """UDF handler: produce FUNCTION-type spans and events."""
    telemetry = _get_telemetry()
    telemetry.set_span_attribute("test.id", test_id)
    telemetry.add_event("udf_event", {"input_value": str(x)})
    return x * 2


def _get_telemetry():
    """Import the telemetry API at call time (only available in Snowflake runtime)."""
    from snowflake import telemetry  # type: ignore[attr-defined]

    return telemetry
