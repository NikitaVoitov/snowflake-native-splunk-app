#!/usr/bin/env python3
"""Deterministically reproduce the OTLP exporter hot-swap race.

This harness exercises the real `otlp_export.init_exporters()` and
`otlp_export.export_spans()` logic while replacing only the exporter
constructors with controllable test doubles. It proves whether a concurrent
re-init can call `shutdown()` on an exporter that is still being used by an
in-flight export call.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opentelemetry.sdk.metrics.export import MetricExportResult
from opentelemetry.sdk.trace.export import SpanExportResult


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PYTHON = PROJECT_ROOT / "app" / "python"
if str(APP_PYTHON) not in sys.path:
    sys.path.insert(0, str(APP_PYTHON))

import otlp_export  # noqa: E402


@dataclass
class RaceOutcome:
    iteration: int
    reproduced: bool
    generation_before: int
    generation_after: int
    old_span_shutdown_called: bool
    old_span_shutdown_during_export: bool
    export_result: bool | None
    export_error: str | None
    reinit_error: str | None
    old_span_exporter_id: int | None
    new_span_exporter_id: int | None


class ControlledSpanExporter:
    """A fake span exporter that lets us pause export mid-flight."""

    def __init__(
        self,
        export_started: threading.Event,
        allow_export_finish: threading.Event,
    ) -> None:
        self._export_started = export_started
        self._allow_export_finish = allow_export_finish
        self.shutdown_called = False
        self.shutdown_during_export = False
        self.export_in_progress = False

    def export(self, _batch: Any) -> SpanExportResult:
        self.export_in_progress = True
        self._export_started.set()
        self._allow_export_finish.wait(timeout=5.0)
        self.export_in_progress = False
        if self.shutdown_called:
            raise RuntimeError("shutdown observed during export")
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        self.shutdown_called = True
        if self.export_in_progress:
            self.shutdown_during_export = True


class PassiveExporter:
    """A minimal fake exporter for metrics/logs."""

    def __init__(self) -> None:
        self.shutdown_called = False

    def export(self, _batch: Any) -> MetricExportResult:
        return MetricExportResult.SUCCESS

    def shutdown(self) -> None:
        self.shutdown_called = True


def _reset_module() -> None:
    otlp_export.close_exporters()
    otlp_export._generation = 0
    otlp_export._last_used = 0.0


def run_iteration(iteration: int) -> RaceOutcome:
    """Run one deterministic reproduction attempt."""
    _reset_module()

    export_started = threading.Event()
    allow_export_finish = threading.Event()
    span_exporters: list[ControlledSpanExporter] = []

    original_build_credentials = otlp_export._build_credentials
    original_build_span_exporter = otlp_export._build_span_exporter
    original_build_metric_exporter = otlp_export._build_metric_exporter
    original_build_log_exporter = otlp_export._build_log_exporter

    def fake_build_credentials(_pem_cert: str | None) -> object:
        return object()

    def fake_build_span_exporter(_target: str, _creds: object) -> ControlledSpanExporter:
        exporter = ControlledSpanExporter(export_started, allow_export_finish)
        span_exporters.append(exporter)
        return exporter

    def fake_build_metric_exporter(_target: str, _creds: object) -> PassiveExporter:
        return PassiveExporter()

    def fake_build_log_exporter(_target: str, _creds: object) -> PassiveExporter:
        return PassiveExporter()

    otlp_export._build_credentials = fake_build_credentials
    otlp_export._build_span_exporter = fake_build_span_exporter
    otlp_export._build_metric_exporter = fake_build_metric_exporter
    otlp_export._build_log_exporter = fake_build_log_exporter

    export_result: bool | None = None
    export_error: str | None = None
    reinit_error: str | None = None

    try:
        otlp_export.init_exporters("https://collector.example.com:4317")
        generation_before = otlp_export.debug_snapshot()["generation"]
        old_span_exporter = span_exporters[0]
        generation_after = generation_before
        new_span_exporter = old_span_exporter

        def do_export() -> None:
            nonlocal export_result, export_error
            try:
                export_result = otlp_export.export_spans([object()])
            except Exception as exc:  # pragma: no cover - defensive
                export_error = str(exc)

        def do_reinit() -> None:
            nonlocal generation_after, new_span_exporter, reinit_error
            try:
                otlp_export.init_exporters("https://collector2.example.com:4317")
                generation_after = otlp_export.debug_snapshot()["generation"]
                new_span_exporter = span_exporters[-1]
            except Exception as exc:  # pragma: no cover - defensive
                reinit_error = str(exc)

        export_thread = threading.Thread(target=do_export, name="race-export-thread")
        export_thread.start()

        started = export_started.wait(timeout=5.0)
        if not started:
            raise RuntimeError("Timed out waiting for export to start")

        reinit_thread = threading.Thread(target=do_reinit, name="race-reinit-thread")
        reinit_thread.start()

        threading.Event().wait(0.05)
        allow_export_finish.set()
        export_thread.join(timeout=5.0)
        if export_thread.is_alive():
            raise RuntimeError("Export thread did not finish")
        reinit_thread.join(timeout=5.0)
        if reinit_thread.is_alive():
            raise RuntimeError("Reinit thread did not finish")

        reproduced = (
            old_span_exporter.shutdown_called
            and old_span_exporter.shutdown_during_export
            and export_result is False
            and generation_after == generation_before + 1
        )
        return RaceOutcome(
            iteration=iteration,
            reproduced=reproduced,
            generation_before=generation_before,
            generation_after=generation_after,
            old_span_shutdown_called=old_span_exporter.shutdown_called,
            old_span_shutdown_during_export=old_span_exporter.shutdown_during_export,
            export_result=export_result,
            export_error=export_error,
            reinit_error=reinit_error,
            old_span_exporter_id=id(old_span_exporter),
            new_span_exporter_id=id(new_span_exporter),
        )
    finally:
        allow_export_finish.set()
        otlp_export._build_credentials = original_build_credentials
        otlp_export._build_span_exporter = original_build_span_exporter
        otlp_export._build_metric_exporter = original_build_metric_exporter
        otlp_export._build_log_exporter = original_build_log_exporter
        otlp_export.close_exporters()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministically reproduce the OTLP exporter concurrency race.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=5,
        help="How many reproduction attempts to run.",
    )
    parser.add_argument(
        "--expect",
        choices=("reproduced", "not-reproduced"),
        default="reproduced",
        help="Whether the current implementation is expected to reproduce the race.",
    )
    args = parser.parse_args()

    outcomes = [run_iteration(i + 1) for i in range(args.iterations)]
    reproduced_count = sum(1 for outcome in outcomes if outcome.reproduced)
    expectation_met = (
        reproduced_count == args.iterations
        if args.expect == "reproduced"
        else reproduced_count == 0
    )

    print(
        json.dumps(
            {
                "expect": args.expect,
                "expectation_met": expectation_met,
                "iterations": args.iterations,
                "reproduced_count": reproduced_count,
                "all_reproduced": reproduced_count == args.iterations,
                "outcomes": [outcome.__dict__ for outcome in outcomes],
            },
            indent=2,
            sort_keys=True,
        ),
    )
    return 0 if expectation_met else 1


if __name__ == "__main__":
    raise SystemExit(main())
