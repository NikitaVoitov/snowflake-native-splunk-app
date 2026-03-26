"""Durable config CRUD helpers for _internal.config.

All SQL uses positional ``?`` bind parameters via ``session.sql(params=[...])``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from snowflake.snowpark import Session

_MERGE_SQL = (
    "MERGE INTO _internal.config AS t "
    "USING (SELECT ? AS k, ? AS v) AS s "
    "ON t.CONFIG_KEY = s.k "
    "WHEN MATCHED THEN UPDATE SET CONFIG_VALUE = s.v, UPDATED_AT = CURRENT_TIMESTAMP() "
    "WHEN NOT MATCHED THEN INSERT (CONFIG_KEY, CONFIG_VALUE) VALUES (s.k, s.v)"
)

_SELECT_ONE_SQL = (
    "SELECT CONFIG_VALUE FROM _internal.config WHERE CONFIG_KEY = ?"
)

_SELECT_ALL_SQL = "SELECT CONFIG_KEY, CONFIG_VALUE FROM _internal.config"


def save_config(session: Session, key: str, value: str) -> None:
    """Upsert a single key/value pair into ``_internal.config``."""
    session.sql(_MERGE_SQL, params=[key, value]).collect()


def load_config(session: Session, key: str) -> str | None:
    """Return the value for *key*, or ``None`` if the row does not exist."""
    rows = session.sql(_SELECT_ONE_SQL, params=[key]).collect()
    if rows and rows[0][0] is not None:
        return str(rows[0][0]).strip()
    return None


def load_all_config(session: Session) -> dict[str, str]:
    """Return every key/value pair as a ``{key: value}`` dict."""
    rows = session.sql(_SELECT_ALL_SQL).collect()
    return {
        str(r[0]): str(r[1]).strip()
        for r in rows
        if r[0] is not None and r[1] is not None
    }


def load_config_like(session: Session, prefix: str) -> dict[str, str]:
    """Return all rows whose key matches ``prefix%``."""
    rows = session.sql(
        "SELECT CONFIG_KEY, CONFIG_VALUE FROM _internal.config WHERE CONFIG_KEY LIKE ?",
        params=[f"{prefix}%"],
    ).collect()
    return {str(r[0]): str(r[1]) for r in rows if r[0] is not None}
