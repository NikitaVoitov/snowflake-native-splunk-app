"""Shared Snowpark session accessor for Streamlit pages.

In SiS warehouse runtime ``get_active_session()`` returns the session that
the Streamlit host injected.  Wrapping it with ``@st.cache_resource`` ensures
the same Python object is reused across reruns within a single user session,
avoiding redundant lookups.

Outside SiS (local development) the import or call will raise; callers should
use :func:`get_session` which returns ``None`` in that case so pages can
degrade gracefully.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st

if TYPE_CHECKING:
    from snowflake.snowpark import Session


@st.cache_resource
def _active_session() -> Session:
    from snowflake.snowpark.context import get_active_session

    return get_active_session()


def get_session() -> Session | None:
    """Return the cached Snowpark session, or ``None`` outside SiS."""
    try:
        return _active_session()
    except Exception:  # noqa: BLE001 — unavailable outside SiS
        return None
