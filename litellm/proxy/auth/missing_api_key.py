import asyncio
from typing import Final


class MissingAPIKeyError(Exception):
    status_code: Final[int] = 401


MISSING_API_KEY_TOTAL_COUNTER_KEY: Final = "litellm:auth:missing_api_key:total"
MISSING_API_KEY_TOTAL_COUNTER_TTL_SECONDS: Final = 30 * 24 * 60 * 60


def _flag_enabled(flag_name: str) -> bool:
    from litellm.proxy.proxy_server import general_settings

    return general_settings.get(flag_name) is True


def should_suppress_missing_api_key_logs() -> bool:
    return _flag_enabled("suppress_missing_api_key_logs")


def should_count_missing_api_key_requests() -> bool:
    return _flag_enabled("count_missing_api_key_requests")


def _increment_prometheus_counter() -> None:
    from litellm.integrations.prometheus import PrometheusLogger

    prometheus_logger: Final = PrometheusLogger.get_instance()
    if prometheus_logger is not None:
        prometheus_logger.litellm_missing_api_key_requests_metric.inc()


async def _increment_redis_counter() -> None:
    from litellm.proxy.proxy_server import redis_usage_cache

    if redis_usage_cache is None:
        return
    await asyncio.to_thread(
        redis_usage_cache.increment_cache,
        MISSING_API_KEY_TOTAL_COUNTER_KEY,
        1,
        MISSING_API_KEY_TOTAL_COUNTER_TTL_SECONDS,
    )


async def record_missing_api_key_request() -> None:
    try:
        _increment_prometheus_counter()
    except Exception:  # noqa: BLE001  # counting must never affect the auth rejection
        pass
    try:
        await _increment_redis_counter()
    except Exception:  # noqa: BLE001  # counting must never affect the auth rejection
        pass
