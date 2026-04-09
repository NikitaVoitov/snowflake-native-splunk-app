"""Unit tests for metric_mapper — Event Table METRIC → OTel MetricsData."""

from __future__ import annotations

import logging

import pandas as pd
from metric_mapper import map_metric_chunk
from opentelemetry.sdk.metrics.export import AggregationTemporality, Gauge, Sum
from telemetry_constants import (
    DB_NAMESPACE,
    DB_SYSTEM_NAME,
    SERVICE_NAME,
    SNOWFLAKE_ACCOUNT_NAME,
    SNOWFLAKE_RECORD_TYPE,
)


ACCOUNT = "LFB71918"


def _metric_row(**overrides):
    """Build a realistic METRIC row dict."""
    base = {
        "metric_time": pd.Timestamp("2026-04-06 12:00:01.000000000"),
        "metric_start_time": pd.Timestamp("2026-04-06 12:00:00.000000000"),
        "metric_name": "snow.process.memory.usage.max",
        "metric_description": "Peak memory usage",
        "metric_unit": "By",
        "metric_type": "gauge",
        "value_type": "DOUBLE",
        "aggregation_temporality": None,
        "is_monotonic": None,
        "metric_value": 1048576.0,
        "RECORD_ATTRIBUTES": {},
        "RESOURCE_ATTRIBUTES": {
            "snow.executable.type": "PROCEDURE",
            "snow.executable.name": "GENERATE_TEST_SPANS",
            "snow.warehouse.name": "SPLUNK_APP_DEV_WH",
            "snow.database.name": "SPLUNK_OBSERVABILITY_DEV_APP",
            "snow.schema.name": "APP_PUBLIC",
        },
    }
    base.update(overrides)
    return base


class TestGaugeMetricMapping:
    def test_gauge_metric_name_and_value(self):
        df = pd.DataFrame([_metric_row()])
        result = map_metric_chunk(df, ACCOUNT)
        assert len(result.resource_metrics) == 1
        rm = result.resource_metrics[0]
        assert len(rm.scope_metrics) == 1
        sm = rm.scope_metrics[0]
        assert len(sm.metrics) == 1

        m = sm.metrics[0]
        assert m.name == "snow.process.memory.usage.max"
        assert m.unit == "By"
        assert isinstance(m.data, Gauge)
        assert len(m.data.data_points) == 1
        assert m.data.data_points[0].value == 1048576.0

    def test_gauge_data_point_attributes(self):
        df = pd.DataFrame([_metric_row()])
        result = map_metric_chunk(df, ACCOUNT)
        dp = result.resource_metrics[0].scope_metrics[0].metrics[0].data.data_points[0]
        assert dp.attributes[DB_SYSTEM_NAME] == "snowflake"
        assert dp.attributes[DB_NAMESPACE] == "SPLUNK_OBSERVABILITY_DEV_APP|APP_PUBLIC"
        assert dp.attributes[SNOWFLAKE_ACCOUNT_NAME] == ACCOUNT
        assert dp.attributes[SNOWFLAKE_RECORD_TYPE] == "METRIC"

    def test_no_redundant_snowflake_aliases(self):
        """Raw snow.* attributes should NOT be duplicated as snowflake.* aliases."""
        df = pd.DataFrame([_metric_row()])
        result = map_metric_chunk(df, ACCOUNT)
        dp = result.resource_metrics[0].scope_metrics[0].metrics[0].data.data_points[0]
        res = result.resource_metrics[0].resource

        assert "snowflake.database.name" not in dp.attributes
        assert "snowflake.schema.name" not in dp.attributes
        assert "snowflake.warehouse.name" not in dp.attributes
        assert "snowflake.query.id" not in dp.attributes

        assert "snowflake.database.name" not in res.attributes
        assert "snowflake.schema.name" not in res.attributes
        assert "snowflake.warehouse.name" not in res.attributes
        assert "snowflake.query.id" not in res.attributes

    def test_gauge_timestamps(self):
        df = pd.DataFrame([_metric_row()])
        result = map_metric_chunk(df, ACCOUNT)
        dp = result.resource_metrics[0].scope_metrics[0].metrics[0].data.data_points[0]
        assert dp.time_unix_nano > 0
        assert dp.start_time_unix_nano > 0


class TestSumMetricMapping:
    def test_sum_metric_with_cumulative_temporality(self):
        df = pd.DataFrame(
            [
                _metric_row(
                    metric_name="snow.process.cpu.utilization",
                    metric_type="sum",
                    metric_value=0.75,
                    aggregation_temporality="CUMULATIVE",
                    is_monotonic=True,
                )
            ]
        )
        result = map_metric_chunk(df, ACCOUNT)
        m = result.resource_metrics[0].scope_metrics[0].metrics[0]
        assert isinstance(m.data, Sum)
        assert m.data.aggregation_temporality == AggregationTemporality.CUMULATIVE
        assert m.data.is_monotonic is True
        assert m.data.data_points[0].value == 0.75

    def test_sum_metric_with_delta_temporality(self):
        df = pd.DataFrame(
            [
                _metric_row(
                    metric_name="request_count",
                    metric_type="sum",
                    metric_value=42.0,
                    aggregation_temporality="DELTA",
                    is_monotonic=False,
                )
            ]
        )
        result = map_metric_chunk(df, ACCOUNT)
        m = result.resource_metrics[0].scope_metrics[0].metrics[0]
        assert isinstance(m.data, Sum)
        assert m.data.aggregation_temporality == AggregationTemporality.DELTA
        assert m.data.is_monotonic is False


class TestResourceGrouping:
    def test_metrics_grouped_by_resource(self):
        row1 = _metric_row(metric_name="metric_a")
        row2 = _metric_row(metric_name="metric_b")
        df = pd.DataFrame([row1, row2])
        result = map_metric_chunk(df, ACCOUNT)
        assert len(result.resource_metrics) == 1
        assert len(result.resource_metrics[0].scope_metrics[0].metrics) == 2

    def test_different_resources_separate_groups(self):
        row1 = _metric_row(
            metric_name="metric_a",
            RESOURCE_ATTRIBUTES={"snow.database.name": "DB1"},
        )
        row2 = _metric_row(
            metric_name="metric_b",
            RESOURCE_ATTRIBUTES={"snow.database.name": "DB2"},
        )
        df = pd.DataFrame([row1, row2])
        result = map_metric_chunk(df, ACCOUNT)
        assert len(result.resource_metrics) == 2

    def test_same_metric_identity_is_grouped_into_one_metric(self):
        row1 = _metric_row(metric_name="metric_a", metric_value=1.0)
        row2 = _metric_row(
            metric_name="metric_a",
            metric_value=2.0,
            metric_time=pd.Timestamp("2026-04-06 12:00:02.000000000"),
        )
        df = pd.DataFrame([row1, row2])
        result = map_metric_chunk(df, ACCOUNT)

        metrics = result.resource_metrics[0].scope_metrics[0].metrics
        assert len(metrics) == 1
        assert isinstance(metrics[0].data, Gauge)
        assert [dp.value for dp in metrics[0].data.data_points] == [1.0, 2.0]


class TestResourceEnrichment:
    def test_resource_attributes(self):
        df = pd.DataFrame([_metric_row()])
        result = map_metric_chunk(df, ACCOUNT)
        res = result.resource_metrics[0].resource
        assert res.attributes[DB_SYSTEM_NAME] == "snowflake"
        assert res.attributes[SNOWFLAKE_ACCOUNT_NAME] == ACCOUNT
        assert res.attributes[SERVICE_NAME] == "GENERATE_TEST_SPANS"


class TestNullAndEmptyHandling:
    def test_empty_dataframe_returns_empty_metrics_data(self):
        result = map_metric_chunk(pd.DataFrame(), ACCOUNT)
        assert result.resource_metrics == []

    def test_missing_metric_name_skipped(self):
        df = pd.DataFrame([_metric_row(metric_name=None)])
        result = map_metric_chunk(df, ACCOUNT)
        assert result.resource_metrics == []

    def test_unsupported_metric_type_skipped(self):
        df = pd.DataFrame([_metric_row(metric_type="histogram")])
        result = map_metric_chunk(df, ACCOUNT)
        assert result.resource_metrics == []

    def test_null_record_attributes(self):
        df = pd.DataFrame([_metric_row(RECORD_ATTRIBUTES=None)])
        result = map_metric_chunk(df, ACCOUNT)
        assert len(result.resource_metrics) == 1

    def test_null_resource_attributes(self):
        df = pd.DataFrame([_metric_row(RESOURCE_ATTRIBUTES=None)])
        result = map_metric_chunk(df, ACCOUNT)
        assert len(result.resource_metrics) == 1

    def test_nullish_resource_members_are_filtered_before_resource_creation(
        self, caplog
    ):
        df = pd.DataFrame(
            [
                _metric_row(
                    RESOURCE_ATTRIBUTES={
                        "snow.application.name": "SPLUNK_OBSERVABILITY_DEV_APP",
                        "nullish.attr": pd.NA,
                        "none.attr": None,
                    }
                )
            ]
        )
        with caplog.at_level(logging.WARNING, logger="opentelemetry.attributes"):
            result = map_metric_chunk(df, ACCOUNT)

        attrs = result.resource_metrics[0].resource.attributes
        assert attrs["snow.application.name"] == "SPLUNK_OBSERVABILITY_DEV_APP"
        assert "nullish.attr" not in attrs
        assert "none.attr" not in attrs
        assert not any("Invalid type" in record.message for record in caplog.records)

    def test_pandas_na_values_do_not_leak_into_metric_metadata_or_attrs(self):
        df = pd.DataFrame(
            [
                _metric_row(
                    metric_description=pd.NA,
                    metric_unit=pd.NA,
                    RECORD_ATTRIBUTES={"stable": "ok", "nullish.attr": pd.NA},
                )
            ]
        )
        result = map_metric_chunk(df, ACCOUNT)
        metric = result.resource_metrics[0].scope_metrics[0].metrics[0]
        attrs = metric.data.data_points[0].attributes

        assert metric.description == ""
        assert metric.unit == ""
        assert attrs["stable"] == "ok"
        assert "nullish.attr" not in attrs

    def test_integer_metric_value_keeps_integer_precision(self):
        exact_value = 2**63 + 7
        df = pd.DataFrame(
            [
                _metric_row(
                    metric_name="request_count",
                    metric_type="sum",
                    value_type="INT",
                    metric_value=exact_value,
                    aggregation_temporality="CUMULATIVE",
                    is_monotonic=True,
                )
            ]
        )
        result = map_metric_chunk(df, ACCOUNT)
        dp_value = result.resource_metrics[0].scope_metrics[0].metrics[0].data.data_points[
            0
        ].value

        assert isinstance(dp_value, int)
        assert dp_value == exact_value


class TestMandatoryRoutingFields:
    def test_all_routing_fields_on_resource_and_datapoint(self):
        df = pd.DataFrame([_metric_row()])
        result = map_metric_chunk(df, ACCOUNT)
        res = result.resource_metrics[0].resource
        dp = result.resource_metrics[0].scope_metrics[0].metrics[0].data.data_points[0]

        assert res.attributes[DB_SYSTEM_NAME] == "snowflake"
        assert res.attributes[SNOWFLAKE_ACCOUNT_NAME] == ACCOUNT
        assert res.attributes[SERVICE_NAME] is not None
        assert dp.attributes[SNOWFLAKE_RECORD_TYPE] == "METRIC"
