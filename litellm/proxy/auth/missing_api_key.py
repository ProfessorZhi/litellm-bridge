from collections.abc import Mapping
from typing import TYPE_CHECKING, Final

from litellm._logging import verbose_proxy_logger

if TYPE_CHECKING:
    from litellm.caching.redis_cache import RedisCache
    from litellm.integrations.prometheus import PrometheusLogger


class MissingAPIKeyError(Exception):
    status_code: Final[int] = 401


MISSING_API_KEY_TOTAL_COUNTER_KEY: Final = "litellm:auth:missing_api_key:total"
MISSING_API_KEY_TOTAL_COUNTER_TTL_SECONDS: Final = 30 * 24 * 60 * 60


def should_suppress_missing_api_key_logs(general_settings: Mapping[str, object]) -> bool:
    return general_settings.get("suppress_missing_api_key_logs") is True


def should_count_missing_api_key_requests(general_settings: Mapping[str, object]) -> bool:
    return general_settings.get("count_missing_api_key_requests") is True


async def record_missing_api_key_request(
    prometheus_logger: "PrometheusLogger | None", redis_cache: "RedisCache | None"
) -> None:
    try:
        if prometheus_logger is not None:
            prometheus_logger.litellm_missing_api_key_requests_metric.inc()
    except Exception:  # noqa: BLE001  # counting must never affect the auth rejection
        verbose_proxy_logger.debug("missing API key: prometheus counter failed", exc_info=True)
    try:
        if redis_cache is not None:
            await redis_cache.async_increment(
                MISSING_API_KEY_TOTAL_COUNTER_KEY, 1, ttl=MISSING_API_KEY_TOTAL_COUNTER_TTL_SECONDS
            )
    except Exception:  # noqa: BLE001  # counting must never affect the auth rejection
        verbose_proxy_logger.debug("missing API key: redis counter failed", exc_info=True)
