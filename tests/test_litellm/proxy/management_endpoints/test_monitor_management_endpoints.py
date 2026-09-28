"""
Tests for /monitor/channel-summary in monitor_management_endpoints.py

The SQL aggregation itself is verified against a live proxy; these tests pin the
response-mapping rules, which are where the reported bugs lived.
"""

from datetime import datetime

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from litellm.proxy.management_endpoints.monitor_management_endpoints import (
    ChannelBucket,
    _bucket_from_row,
    _parse_dt,
)


def _row(**overrides) -> dict:
    row = {
        "model_group": "glm-5.3",
        "bucket": datetime(2026, 9, 28, 13, 40),
        "total_requests": 0,
        "success_requests": 0,
        "failed_requests": 0,
        "other_requests": 0,
        "client_failures": 0,
        "channel_failures": 0,
        "upstream_failures": 0,
        "transport_failures": 0,
        "unclassified_failures": 0,
        "avg_latency": None,
        "avg_ttft": None,
        "p50": None,
        "p95": None,
        "total_tokens": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }
    row.update(overrides)
    return row


class TestHealthDenominator:
    """Channel availability = success / (success + channel_failures). Not success / total."""

    def test_denominator_is_success_plus_channel_failures_not_total(self):
        bucket = _bucket_from_row(
            _row(
                total_requests=1000,
                success_requests=900,
                failed_requests=50,
                other_requests=50,
                client_failures=40,
                channel_failures=10,
            )
        )
        assert bucket.health == pytest.approx(900 / 910, abs=1e-4)
        assert bucket.health != pytest.approx(900 / 1000, abs=1e-4)

    def test_caller_caused_failures_leave_channel_fully_available(self):
        bucket = _bucket_from_row(
            _row(total_requests=100, success_requests=90, failed_requests=10, client_failures=10)
        )
        assert bucket.health == 1.0

    def test_unclassified_failures_count_against_availability(self):
        bucket = _bucket_from_row(
            _row(
                total_requests=100,
                success_requests=95,
                failed_requests=5,
                channel_failures=5,
                unclassified_failures=5,
            )
        )
        assert bucket.health == pytest.approx(0.95)

    def test_no_traffic_scores_zero_rather_than_erroring(self):
        bucket = _bucket_from_row(_row())
        assert bucket.health == 0.0


class TestRowMapping:
    """The four request counts and the failure breakdown pass through unchanged."""

    def test_failure_breakdown_is_read_not_derived(self):
        bucket = _bucket_from_row(
            _row(
                total_requests=162,
                success_requests=0,
                failed_requests=100,
                client_failures=60,
                channel_failures=95,
                upstream_failures=19,
                transport_failures=65,
                unclassified_failures=11,
            )
        )
        assert bucket.channel_failures == 95
        assert bucket.channel_failures != bucket.failed_requests - bucket.client_failures

    def test_other_requests_are_carried_through(self):
        bucket = _bucket_from_row(
            _row(total_requests=100, success_requests=90, failed_requests=8, other_requests=2)
        )
        assert bucket.total_requests == 100
        assert bucket.success_requests + bucket.failed_requests + bucket.other_requests == 100

    def test_upstream_and_transport_are_kept_apart(self):
        bucket = _bucket_from_row(
            _row(failed_requests=84, channel_failures=84, upstream_failures=19, transport_failures=65)
        )
        assert (bucket.upstream_failures, bucket.transport_failures) == (19, 65)

    def test_null_bucket_is_accepted_for_a_model_with_no_traffic(self):
        # LEFT JOIN over configured models yields a row with no aggregate at all
        bucket = _bucket_from_row(
            _row(
                model_group="resident-smoke-model",
                bucket=None,
                avg_latency=None,
                avg_ttft=None,
                p50=None,
                p95=None,
            )
        )
        assert bucket.bucket is None
        assert bucket.model_group == "resident-smoke-model"
        assert bucket.total_requests == 0
        assert bucket.avg_latency_ms is None

    def test_literal_none_bucket_is_rejected_so_it_can_never_reach_the_ui(self):
        # The pre-fix endpoint str()-ed a NULL bucket into "None"; the UI then read
        # new Date("None") as NaN and wrote into a NaN segment index
        with pytest.raises(ValidationError):
            _bucket_from_row(_row(bucket="None"))

    def test_latency_and_percentiles_pass_through(self):
        bucket = _bucket_from_row(
            _row(
                success_requests=10,
                total_requests=10,
                avg_latency=4281.42,
                avg_ttft=1.88,
                p50=2028.0,
                p95=14486.2,
            )
        )
        assert bucket.avg_latency_ms == 4281.42
        assert bucket.avg_ttft_ms == 1.88
        assert (bucket.p50_ms, bucket.p95_ms) == (2028.0, 14486.2)

    def test_token_columns_are_independent_of_latency(self):
        bucket = _bucket_from_row(
            _row(total_tokens=67499, prompt_tokens=50000, completion_tokens=17499)
        )
        assert bucket.total_tokens == 67499
        assert bucket.prompt_tokens == 50000
        assert bucket.completion_tokens == 17499


class TestParseDt:
    def test_accepts_zulu_and_offset_forms(self):
        assert _parse_dt("2026-09-21T00:00:00Z") == _parse_dt("2026-09-21T00:00:00+00:00")

    def test_preserves_utc_offset(self):
        assert _parse_dt("2026-09-21T08:00:00+08:00").utcoffset().total_seconds() == 8 * 3600

    @pytest.mark.parametrize("value", ["", "not-a-time", "2026-13-45T99:99:99Z"])
    def test_rejects_bad_input_with_400(self, value):
        with pytest.raises(HTTPException) as excinfo:
            _parse_dt(value)
        assert excinfo.value.status_code == 400


def test_response_model_defaults_are_defined():
    """Every count defaults to 0 so a partial row can never render as blank."""
    bucket = ChannelBucket(model_group="glm-5.3")
    assert bucket.total_requests == 0
    assert bucket.channel_failures == 0
    assert bucket.bucket is None
