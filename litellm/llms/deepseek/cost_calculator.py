"""
Cost calculator for DeepSeek Chat models.

Handles prompt caching scenario and DeepSeek's peak/off-peak rate cards.
"""

import datetime
from typing import Final

from litellm.litellm_core_utils.llm_cost_calc.utils import generic_cost_per_token
from litellm.llms.deepseek.dynamic_pricing import DeepSeekPricing, deepseek_pricing_for_request
from litellm.types.utils import Usage


def deepseek_cost_from_pricing(
    pricing: DeepSeekPricing,
    prompt_tokens: float,
    cached_tokens: float,
    completion_tokens: float,
) -> tuple[float, float]:
    """
    Cost of one DeepSeek request against an already-resolved rate card.

    ``prompt_tokens`` includes the cached tokens, matching how OpenAI-format
    usage is reported, so the cache-miss count is the remainder. The two input
    line items are priced separately and summed rather than charging every
    prompt token the cache-miss rate.
    """
    cache_miss_tokens: Final = prompt_tokens - cached_tokens
    input_cost: Final = cache_miss_tokens * pricing.input_price + cached_tokens * pricing.cache_read_price
    output_cost: Final = completion_tokens * pricing.output_price
    return input_cost, output_cost


def cost_per_token(
    model: str,
    usage: Usage,
    at: datetime.datetime | None = None,
    custom_llm_provider: str = "deepseek",
    api_base: str | None = None,
) -> tuple[float, float]:
    """
    Calculates the cost per token for a given model, prompt tokens, and completion tokens.

    Follows the same logic as Anthropic's cost per token calculation.

    When the request instant is known and DeepSeek serves the model, the
    peak/off-peak rate card in effect at ``at`` is used. Otherwise this keeps the
    model-cost-map behavior that precedes it.
    """
    pricing: Final = (
        None
        if at is None
        else deepseek_pricing_for_request(
            model,
            at,
            custom_llm_provider=custom_llm_provider,
            api_base=api_base,
        )
    )
    if pricing is None:
        return generic_cost_per_token(model=model, usage=usage, custom_llm_provider="deepseek")

    cached_tokens: Final = int(getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0)
    return deepseek_cost_from_pricing(
        pricing=pricing,
        prompt_tokens=float(usage.prompt_tokens or 0),
        cached_tokens=float(cached_tokens),
        completion_tokens=float(usage.completion_tokens or 0),
    )
