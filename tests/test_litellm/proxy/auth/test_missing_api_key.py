from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

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
    [(True, True), (False, False), (None, False), ("true", False)],
)
def test_suppress_flag_requires_explicit_true(configured, expected):
    assert should_suppress_missing_api_key_logs({"suppress_missing_api_key_logs": configured}) is expected
    assert should_suppress_missing_api_key_logs({"count_missing_api_key_requests": configured}) is False


@pytest.mark.parametrize(
    "configured, expected",
    [(True, True), (False, False), (None, False), ("true", False)],
)
def test_count_flag_requires_explicit_true(configured, expected):
    assert should_count_missing_api_key_requests({"count_missing_api_key_requests": configured}) is expected
    assert should_count_missing_api_key_requests({"suppress_missing_api_key_logs": configured}) is False


@pytest.mark.asyncio
async def test_record_increments_prometheus_counter():
    metric = MagicMock()

    await record_missing_api_key_request(SimpleNamespace(litellm_missing_api_key_requests_metric=metric), None)

    metric.inc.assert_called_once_with()


@pytest.mark.asyncio
async def test_record_increments_redis_total_counter():
    cache = MagicMock()
    cache.async_increment = AsyncMock(return_value=1)

    await record_missing_api_key_request(None, cache)

    cache.async_increment.assert_awaited_once_with(
        MISSING_API_KEY_TOTAL_COUNTER_KEY,
        1,
        ttl=MISSING_API_KEY_TOTAL_COUNTER_TTL_SECONDS,
    )


@pytest.mark.asyncio
async def test_record_swallows_counter_failures_and_still_tries_redis():
    metric = MagicMock()
    metric.inc.side_effect = RuntimeError("prometheus broken")
    cache = MagicMock()
    cache.async_increment = AsyncMock(side_effect=ConnectionError("redis down"))

    await record_missing_api_key_request(SimpleNamespace(litellm_missing_api_key_requests_metric=metric), cache)

    metric.inc.assert_called_once_with()
    cache.async_increment.assert_awaited_once()
