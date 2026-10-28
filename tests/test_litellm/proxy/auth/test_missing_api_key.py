from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from litellm.proxy.auth.missing_api_key import (
    MISSING_API_KEY_TOTAL_COUNTER_KEY,
    MISSING_API_KEY_TOTAL_COUNTER_TTL_SECONDS,
    MissingAPIKeyError,
    record_missing_api_key_request,
    should_count_missing_api_key_requests,
    should_suppress_missing_api_key_logs,
)


def test_missing_api_key_error_is_a_401_client_error():
    error = MissingAPIKeyError("No api key passed in.")

    assert MissingAPIKeyError.status_code == 401
    assert str(error) == "No api key passed in."


@pytest.mark.parametrize(
    "configured, expected",
    [(True, True), (False, False), (None, False)],
)
def test_suppress_flag_requires_explicit_true(configured, expected):
    with patch(
        "litellm.proxy.proxy_server.general_settings",
        {"suppress_missing_api_key_logs": configured},
    ):
        assert should_suppress_missing_api_key_logs() is expected


@pytest.mark.parametrize(
    "configured, expected",
    [(True, True), (False, False), (None, False)],
)
def test_count_flag_requires_explicit_true(configured, expected):
    with patch(
        "litellm.proxy.proxy_server.general_settings",
        {"count_missing_api_key_requests": configured},
    ):
        assert should_count_missing_api_key_requests() is expected


@pytest.mark.asyncio
async def test_record_increments_prometheus_counter():
    metric = MagicMock()
    prometheus_logger = SimpleNamespace(litellm_missing_api_key_requests_metric=metric)

    with (
        patch(
            "litellm.integrations.prometheus.PrometheusLogger.get_instance",
            return_value=prometheus_logger,
        ),
        patch("litellm.proxy.proxy_server.redis_usage_cache", None),
    ):
        await record_missing_api_key_request()

    metric.inc.assert_called_once_with()


@pytest.mark.asyncio
async def test_record_increments_redis_total_counter():
    cache = MagicMock()
    cache.increment_cache = MagicMock(return_value=1)

    with (
        patch(
            "litellm.integrations.prometheus.PrometheusLogger.get_instance",
            return_value=None,
        ),
        patch("litellm.proxy.proxy_server.redis_usage_cache", cache),
    ):
        await record_missing_api_key_request()

    cache.increment_cache.assert_called_once_with(
        MISSING_API_KEY_TOTAL_COUNTER_KEY,
        1,
        MISSING_API_KEY_TOTAL_COUNTER_TTL_SECONDS,
    )


@pytest.mark.asyncio
async def test_record_swallows_counter_failures():
    cache = MagicMock()
    cache.increment_cache = MagicMock(side_effect=ConnectionError("redis down"))

    with (
        patch(
            "litellm.integrations.prometheus.PrometheusLogger.get_instance",
            side_effect=RuntimeError("prometheus broken"),
        ),
        patch("litellm.proxy.proxy_server.redis_usage_cache", cache),
    ):
        await record_missing_api_key_request()
