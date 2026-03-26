"""Shared onboarding task definitions and completion helpers.

Both ``main.py`` (sidebar badge, conditional page inclusion) and
``getting_started.py`` (tile rendering, progress bar) import from here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from snowflake.snowpark.exceptions import SnowparkSQLException

from utils.config import load_config, load_config_like

if TYPE_CHECKING:
    from snowflake.snowpark import Session


class OnboardingTask(NamedTuple):
    step: int
    title: str
    description: str
    config_key: str
    page_path: str | None


ONBOARDING_TASKS: list[OnboardingTask] = [
    OnboardingTask(
        step=1,
        title="Configure Splunk Settings",
        description=(
            "Set up your OTLP endpoint and configure the connection "
            "to your remote OpenTelemetry collector."
        ),
        config_key="otlp.endpoint",
        page_path="pages/splunk_settings.py",
    ),
    OnboardingTask(
        step=2,
        title="Select Telemetry Sources",
        description=(
            "Choose monitoring packs and configure data sources "
            "from Event Tables and ACCOUNT_USAGE views."
        ),
        config_key="pack_enabled.",
        page_path="pages/telemetry_sources.py",
    ),
    OnboardingTask(
        step=3,
        title="Review Data Governance",
        description=(
            "Verify that data governance policies and masking rules "
            "are properly configured for exported telemetry."
        ),
        config_key="governance.acknowledged",
        page_path="pages/data_governance.py",
    ),
    OnboardingTask(
        step=4,
        title="Activate Export",
        description=(
            "Enable auto-export to start sending telemetry data "
            "to your Splunk Observability platform."
        ),
        config_key="activation.completed",
        page_path=None,
    ),
]


def load_task_completion(session: Session | None) -> dict[int, bool]:
    """Query ``_internal.config`` and return ``{step: completed}`` for each task.

    Always re-queries (no caching) because task state can change mid-session.
    Returns all-False when *session* is ``None`` or the table is missing.
    """
    result: dict[int, bool] = {t.step: False for t in ONBOARDING_TASKS}
    if session is None:
        return result

    try:
        for task in ONBOARDING_TASKS:
            if task.step == 1:
                val = load_config(session, task.config_key)
                result[task.step] = bool(val)
            elif task.step == 2:
                packs = load_config_like(session, task.config_key)
                result[task.step] = any(v == "true" for v in packs.values())
            else:
                val = load_config(session, task.config_key)
                result[task.step] = val == "true"
    except SnowparkSQLException:
        pass

    return result


def get_completed_count(completion: dict[int, bool]) -> int:
    """Count completed tasks."""
    return sum(1 for v in completion.values() if v)
