"""Telemetry source discovery and related UI helpers.

Discovers Event Tables and validated MVP ACCOUNT_USAGE views from Snowflake
metadata. Relies on IMPORTED PRIVILEGES ON SNOWFLAKE DB (OBJECT_VIEWER,
GOVERNANCE_VIEWER roles).

All SQL uses parameterized queries via ``session.sql(params=[...])`` where
parameters are needed.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from snowflake.snowpark import Session

# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------

ACCOUNT_USAGE_MVP_VIEWS: tuple[str, ...] = (
    "QUERY_HISTORY",
    "TASK_HISTORY",
    "COMPLETE_TASK_GRAPHS",
    "LOCK_WAIT_HISTORY",
)

# ---------------------------------------------------------------------------
# Per-source operational defaults
# ---------------------------------------------------------------------------

SOURCE_DEFAULTS: dict[str, dict[str, int]] = {
    "QUERY_HISTORY": {"interval_seconds": 900, "overlap_minutes": 50},
    "TASK_HISTORY": {"interval_seconds": 900, "overlap_minutes": 50},
    "COMPLETE_TASK_GRAPHS": {"interval_seconds": 900, "overlap_minutes": 50},
    "LOCK_WAIT_HISTORY": {"interval_seconds": 900, "overlap_minutes": 66},
}

EVENT_TABLE_DEFAULT_INTERVAL_SECONDS = 60

MIN_INTERVAL_SECONDS = 60
MAX_INTERVAL_SECONDS = 86400
MIN_OVERLAP_MINUTES = 1
MAX_OVERLAP_MINUTES = 1440


class CategoryDef(NamedTuple):
    key: str
    name: str
    description: str
    source_family: str  # "event_table" | "account_usage"


CATEGORIES: tuple[CategoryDef, ...] = (
    CategoryDef(
        key="distributed_tracing",
        name="Distributed Tracing",
        description=(
            "Capture and correlate execution events from functions, "
            "procedures, tasks, and custom services."
        ),
        source_family="event_table",
    ),
    CategoryDef(
        key="query_performance",
        name="Query Performance & Execution",
        description=(
            "Understand workload patterns and query behavior "
            "via ACCOUNT_USAGE views."
        ),
        source_family="account_usage",
    ),
)


# ---------------------------------------------------------------------------
# Discovered-source data model
# ---------------------------------------------------------------------------

class DiscoveredSource(NamedTuple):
    view_name: str
    fqn: str
    category: str
    is_custom: bool
    telemetry_types: str
    telemetry_sources: str
    parent_account_usage_view: str | None = None


# ---------------------------------------------------------------------------
# Discovery SQL (validated against LFB71918 on 2026-03-26)
# ---------------------------------------------------------------------------

_EVENT_TABLE_SQL = (
    "SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME "
    "FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES "
    "WHERE TABLE_TYPE = 'EVENT TABLE' "
    "AND DELETED IS NULL "
    "ORDER BY TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME"
)

_ACCOUNT_USAGE_VALIDATION_SQL = (
    "SELECT TABLE_NAME "
    "FROM SNOWFLAKE.INFORMATION_SCHEMA.TABLES "
    "WHERE TABLE_SCHEMA = 'ACCOUNT_USAGE' "
    "AND TABLE_TYPE = 'VIEW' "
    "AND TABLE_NAME IN ({placeholders}) "
    "ORDER BY TABLE_NAME"
)

_CUSTOM_VIEW_SQL = (
    "SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, VIEW_DEFINITION "
    "FROM SNOWFLAKE.ACCOUNT_USAGE.VIEWS "
    "WHERE DELETED IS NULL "
    "AND TABLE_CATALOG != 'SNOWFLAKE' "
    "AND VIEW_DEFINITION IS NOT NULL "
    "ORDER BY TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME"
)


# ---------------------------------------------------------------------------
# Source/config helpers
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

PACK_ENABLED_CONFIG_KEYS: tuple[str, ...] = tuple(
    f"pack_enabled.{category.key}" for category in CATEGORIES
)

_ACCOUNT_USAGE_MATCH_TOKENS: tuple[str, ...] = tuple(
    sorted(
        {
            view_name
            for name in ACCOUNT_USAGE_MVP_VIEWS
            for view_name in (
                f"ACCOUNT_USAGE.{name}",
                f"SNOWFLAKE.ACCOUNT_USAGE.{name}",
            )
        },
        key=len,
        reverse=True,
    )
)


def source_slug(fqn: str) -> str:
    """Return a stable config-key-safe slug for a source FQN."""
    return _NON_ALNUM_RE.sub("_", fqn.strip().lower()).strip("_")


def normalize_view_definition(view_definition: str | None) -> str:
    """Normalize a SQL view definition for substring matching."""
    if not view_definition:
        return ""
    normalized = view_definition.upper().replace('"', "").replace("`", "")
    return _WHITESPACE_RE.sub(" ", normalized)


def build_event_table_match_tokens(
    event_tables: Iterable[DiscoveredSource],
) -> tuple[str, ...]:
    """Return match tokens for discovered event tables.

    We match on the full FQN and the schema-qualified name to recognize custom
    views built on both default and account-specific event tables.
    """
    tokens: set[str] = set()
    for source in event_tables:
        parts = source.fqn.upper().split(".")
        if len(parts) != 3:
            continue
        catalog, schema, table = parts
        tokens.add(f"{catalog}.{schema}.{table}")
        tokens.add(f"{schema}.{table}")
    return tuple(sorted(tokens, key=len, reverse=True))


def resolve_saved_poll_states(
    sources: list[DiscoveredSource],
    saved_source_polls: dict[str, bool],
) -> list[bool]:
    """Resolve persisted poll values for currently discovered sources.

    Poll state is independent of the category toggle — the toggle acts as a
    master enable/disable switch while checkboxes represent user selection
    intent.  Unknown sources default to ``False`` (explicit opt-in).
    """
    return [saved_source_polls.get(source.fqn, False) for source in sources]


def _extract_au_view_name(fqn: str) -> str | None:
    """Extract the bare ACCOUNT_USAGE view name from an FQN like
    ``SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY``."""
    parts = fqn.upper().split(".")
    if len(parts) == 3 and parts[1] == "ACCOUNT_USAGE":
        return parts[2]
    return None


def _extract_parent_account_usage_view(
    view_definition: str | None,
) -> str | None:
    """Return the referenced MVP ACCOUNT_USAGE view when it is unambiguous."""
    normalized = normalize_view_definition(view_definition)
    if not normalized:
        return None

    matches = {
        view_name
        for view_name in ACCOUNT_USAGE_MVP_VIEWS
        if f"ACCOUNT_USAGE.{view_name}" in normalized
    }
    if len(matches) == 1:
        return next(iter(matches))
    return None


def get_source_defaults(source: DiscoveredSource) -> dict[str, int | None]:
    """Return default operational settings for a discovered source.

    Returns ``{"interval_seconds": int, "overlap_minutes": int | None}``.
    For ACCOUNT_USAGE sources, overlap is looked up from ``SOURCE_DEFAULTS``
    by the bare view name.  For Event Table sources, overlap is ``None``.
    """
    if source.category == "distributed_tracing":
        return {
            "interval_seconds": EVENT_TABLE_DEFAULT_INTERVAL_SECONDS,
            "overlap_minutes": None,
        }

    view_name = source.parent_account_usage_view or _extract_au_view_name(source.fqn)
    if view_name and view_name in SOURCE_DEFAULTS:
        defaults = SOURCE_DEFAULTS[view_name]
        return {
            "interval_seconds": defaults["interval_seconds"],
            "overlap_minutes": defaults["overlap_minutes"],
        }

    if source.is_custom:
        return {
            "interval_seconds": 900,
            "overlap_minutes": 50,
        }

    return {
        "interval_seconds": 900,
        "overlap_minutes": 50,
    }


# ---------------------------------------------------------------------------
# Custom view category assignment
# ---------------------------------------------------------------------------

def classify_custom_view(
    view_definition: str | None,
    event_table_tokens: Iterable[str] | None = None,
) -> str | None:
    """Return category key for a custom view, or ``None`` if unrecognised."""
    normalized = normalize_view_definition(view_definition)
    if not normalized:
        return None

    for token in event_table_tokens or ():
        if token and token in normalized:
            return "distributed_tracing"

    for token in _ACCOUNT_USAGE_MATCH_TOKENS:
        if token in normalized:
            return "query_performance"

    return None


# ---------------------------------------------------------------------------
# Discovery orchestration
# ---------------------------------------------------------------------------

def discover_event_tables(
    session: Session,
) -> list[DiscoveredSource]:
    """Discover all event tables via ``SNOWFLAKE.ACCOUNT_USAGE.TABLES``.

    Requires ``IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE`` (requested in
    ``manifest.yml``).  New event tables appear in ACCOUNT_USAGE with up to
    ~45 min latency — acceptable because consumers typically create event
    tables during onboarding, not continuously at runtime.

    Note: RCR (Restricted Caller's Rights) procedures were evaluated but
    cannot work from Streamlit warehouse runtime — the session always runs
    as the app owner, so the "caller" in an RCR procedure is the app owner
    role which lacks visibility into consumer objects.  RCR would only work
    with container-runtime Streamlit (Preview, not available for Native Apps).
    """
    rows = session.sql(_EVENT_TABLE_SQL).collect()
    return [
        DiscoveredSource(
            view_name=f"{row[0]}.{row[1]}.{row[2]}",
            fqn=f"{row[0]}.{row[1]}.{row[2]}",
            category="distributed_tracing",
            is_custom=False,
            telemetry_types="",
            telemetry_sources="",
        )
        for row in rows
    ]


def discover_account_usage_views(
    session: Session,
) -> list[DiscoveredSource]:
    """Validate and return the MVP ACCOUNT_USAGE views."""
    placeholders = ", ".join(["?"] * len(ACCOUNT_USAGE_MVP_VIEWS))
    sql = _ACCOUNT_USAGE_VALIDATION_SQL.format(placeholders=placeholders)
    rows = session.sql(sql, params=list(ACCOUNT_USAGE_MVP_VIEWS)).collect()
    results: list[DiscoveredSource] = []
    for row in rows:
        name = str(row[0])
        fqn = f"SNOWFLAKE.ACCOUNT_USAGE.{name}"
        results.append(
            DiscoveredSource(
                view_name=fqn,
                fqn=fqn,
                category="query_performance",
                is_custom=False,
                telemetry_types="",
                telemetry_sources="",
            )
        )
    return results


def discover_custom_views(
    session: Session,
    event_tables: list[DiscoveredSource] | None = None,
) -> list[DiscoveredSource]:
    """Discover custom views built on supported ACCOUNT_USAGE or event tables."""
    rows = session.sql(_CUSTOM_VIEW_SQL).collect()
    event_table_tokens = build_event_table_match_tokens(event_tables or [])
    results: list[DiscoveredSource] = []

    for row in rows:
        catalog = str(row[0])
        schema = str(row[1])
        name = str(row[2])
        definition = str(row[3]) if row[3] else ""
        fqn = f"{catalog}.{schema}.{name}"
        category = classify_custom_view(definition, event_table_tokens)
        if category is None:
            continue
        parent_account_usage_view = (
            _extract_parent_account_usage_view(definition)
            if category == "query_performance"
            else None
        )
        results.append(
            DiscoveredSource(
                view_name=fqn,
                fqn=fqn,
                category=category,
                is_custom=True,
                telemetry_types="",
                telemetry_sources="",
                parent_account_usage_view=parent_account_usage_view,
            )
        )
    return results


def discover_all_sources(
    session: Session,
) -> dict[str, list[DiscoveredSource]]:
    """Run all discovery queries and return sources grouped by category key."""
    grouped: dict[str, list[DiscoveredSource]] = {cat.key: [] for cat in CATEGORIES}

    event_table_sources = discover_event_tables(session)
    for source in event_table_sources:
        grouped[source.category].append(source)

    account_usage_sources = discover_account_usage_views(session)
    for source in account_usage_sources:
        grouped[source.category].append(source)

    custom_sources = discover_custom_views(session, event_table_sources)
    for source in custom_sources:
        if source.category in grouped:
            grouped[source.category].append(source)

    return grouped
