"""
Time-of-day pricing for DeepSeek models.

DeepSeek publishes two rate cards per model and picks between them from the wall
clock at which the request was served: peak is 01:00-04:00 and 06:00-10:00 UTC,
Monday through Friday, and every other instant is off-peak at exactly half the
peak rate.

Rates are declared below in the unit DeepSeek publishes them in (USD per 1M
tokens) and converted to per-token once, at resolution time, so the published
numbers stay copy-pasteable from the vendor pricing page.
"""

import datetime
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, Mapping
from urllib.parse import urlparse

DEEPSEEK_PRICING_SOURCE: Final = "deepseek_dynamic"

# DeepSeek serves OpenAI-format traffic from this host as well as the `deepseek`
# provider, so the endpoint, not the provider label, is what identifies a request
# that must be billed with DeepSeek's rate card.
DEEPSEEK_API_HOSTS: Final[frozenset[str]] = frozenset({"api.deepseek.com"})

PEAK_WINDOWS_UTC: Final[tuple[tuple[int, int], ...]] = ((1, 4), (6, 10))
WEEKEND_WEEKDAYS: Final[frozenset[int]] = frozenset({5, 6})

PricingTier = Literal["peak", "off_peak"]


@dataclass(frozen=True, slots=True)
class TokenRatesPerMillion:
    cache_hit: float
    cache_miss: float
    output: float


@dataclass(frozen=True, slots=True)
class DeepSeekPricing:
    """The rate card a single request is billed against."""

    billing_model: str
    tier: PricingTier
    input_price: float
    cache_read_price: float
    output_price: float
    source: str = DEEPSEEK_PRICING_SOURCE


_RATES: Final[Mapping[str, Mapping[PricingTier, TokenRatesPerMillion]]] = MappingProxyType(
    {
        "deepseek-flash": MappingProxyType(
            {
                "off_peak": TokenRatesPerMillion(cache_hit=0.003, cache_miss=0.15, output=0.6),
                "peak": TokenRatesPerMillion(cache_hit=0.006, cache_miss=0.30, output=1.2),
            }
        ),
        "deepseek-v4-pro": MappingProxyType(
            {
                "off_peak": TokenRatesPerMillion(cache_hit=0.022, cache_miss=0.66, output=1.98),
                "peak": TokenRatesPerMillion(cache_hit=0.044, cache_miss=1.32, output=3.96),
            }
        ),
    }
)

# Request names DeepSeek accepts, mapped to the model that actually serves and
# bills them. The legacy names are retired aliases: DeepSeek still accepts them,
# serves them with the current Flash model, and bills them at the Flash price.
_BILLING_MODEL_BY_REQUEST_NAME: Final[Mapping[str, str]] = MappingProxyType(
    {
        "deepseek-flash": "deepseek-flash",
        "deepseek-v4-flash": "deepseek-flash",
        "deepseek-v4-flash-vision-exp": "deepseek-flash",
        "deepseek-v4-pro": "deepseek-v4-pro",
    }
)


def _request_model_name(model: str) -> str:
    """Drop a single leading provider segment, e.g. ``deepseek/deepseek-v4-pro``."""
    prefix, separator, remainder = model.partition("/")
    return remainder if separator else prefix


def deepseek_billing_model(model: str) -> str | None:
    """The model DeepSeek bills for ``model``, or None when DeepSeek does not serve it."""
    return _BILLING_MODEL_BY_REQUEST_NAME.get(_request_model_name(model))


def is_deepseek_endpoint(api_base: str | None) -> bool:
    """Whether ``api_base`` points at a DeepSeek-served endpoint."""
    if not api_base:
        return False
    candidate: Final = api_base if "//" in api_base else f"//{api_base}"
    try:
        hostname: Final = urlparse(candidate).hostname
    except ValueError:
        return False
    return hostname is not None and hostname.lower() in DEEPSEEK_API_HOSTS


def deepseek_tier_at(instant: datetime.datetime) -> PricingTier:
    """
    The tier DeepSeek bills a request served at ``instant`` against.

    ``instant`` must be timezone-aware. A naive value is rejected rather than
    assumed to be UTC, because silently reading a local wall clock as UTC shifts
    the tier by the host's offset.
    """
    if instant.tzinfo is None:
        raise ValueError("DeepSeek tier resolution requires a timezone-aware request timestamp")
    utc: Final = instant.astimezone(datetime.timezone.utc)
    if utc.weekday() in WEEKEND_WEEKDAYS:
        return "off_peak"
    return "peak" if any(start <= utc.hour < end for start, end in PEAK_WINDOWS_UTC) else "off_peak"


def request_instant_utc(start_time: datetime.datetime | float | int) -> datetime.datetime | None:
    """
    Normalize a ``litellm_logging`` request timestamp to an aware UTC instant, or
    None when it does not carry one.

    ``LitellmLoggingObject.start_time`` holds whichever shape the caller passed to
    it: the completion path passes ``datetime.now()``, which is wall-clock local and
    therefore naive, while the files handlers pass a ``time.time()`` float. Neither
    is UTC by default. A naive value is resolved against the local zone it was read
    from rather than relabelled as UTC, and an epoch value is already an unambiguous
    instant.
    """
    if isinstance(start_time, datetime.datetime):
        if start_time.tzinfo is not None:
            return start_time.astimezone(datetime.timezone.utc)
        return start_time.astimezone().astimezone(datetime.timezone.utc)
    if isinstance(start_time, bool) or not isinstance(start_time, (int, float)):
        return None
    return datetime.datetime.fromtimestamp(start_time, tz=datetime.timezone.utc)


def _provider_is_deepseek(custom_llm_provider: str | None, api_base: str | None) -> bool:
    if custom_llm_provider == "deepseek":
        return True
    return custom_llm_provider == "openai" and is_deepseek_endpoint(api_base)


def deepseek_serves_request(model: str, custom_llm_provider: str | None, api_base: str | None) -> bool:
    """
    Whether DeepSeek serves, and therefore bills, this request.

    True when the provider is ``deepseek``, or when it is ``openai`` pointed at a
    DeepSeek host, and in both cases the model is one DeepSeek serves. Nothing is
    inferred from the model name beyond membership in that table.
    """
    return deepseek_billing_model(model) is not None and _provider_is_deepseek(custom_llm_provider, api_base)


def deepseek_pricing_for_request(
    model: str,
    instant: datetime.datetime,
    custom_llm_provider: str | None = None,
    api_base: str | None = None,
) -> DeepSeekPricing | None:
    """Resolve the DeepSeek rate card for a request, or None when the request is not DeepSeek's to bill."""
    billing_model: Final = deepseek_billing_model(model)
    if billing_model is None or not _provider_is_deepseek(custom_llm_provider, api_base):
        return None

    tier: Final = deepseek_tier_at(instant)
    rates: Final = _RATES[billing_model][tier]
    return DeepSeekPricing(
        billing_model=billing_model,
        tier=tier,
        input_price=rates.cache_miss / 1_000_000,
        cache_read_price=rates.cache_hit / 1_000_000,
        output_price=rates.output / 1_000_000,
    )
