"""Read app-owned secrets (stored procedure handler)."""

from __future__ import annotations

from snowflake.snowpark import Session


def get_pem_secret(_session: Session) -> str:
    """Return the stored PEM certificate string, or empty string if none."""
    import _snowflake

    return _snowflake.get_generic_secret_string("otlp_pem_cert") or ""
