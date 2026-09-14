import datetime
import time

import pytest

from litellm.cost_calculator import completion_cost, cost_per_token
from litellm.litellm_core_utils.llm_cost_calc.utils import get_token_type_cost_breakdown
from litellm.litellm_core_utils.litellm_logging import Logging
from litellm.llms.deepseek.cost_calculator import cost_per_token as deepseek_cost_per_token
from litellm.llms.deepseek.dynamic_pricing import (
    deepseek_billing_model,
    deepseek_pricing_for_request,
    deepseek_serves_request,
    deepseek_tier_at,
    request_instant_utc,
)
from litellm.types.utils import CostBreakdown, ModelResponse, PromptTokensDetailsWrapper, Usage

UTC = datetime.timezone.utc
DEEPSEEK_BASE = "https://api.deepseek.com"
DEEPSEEK_BASE_V1 = "https://api.deepseek.com/v1"

FLASH_OFF_PEAK_MISS = 0.15 / 1_000_000
FLASH_OFF_PEAK_HIT = 0.003 / 1_000_000
FLASH_OFF_PEAK_OUTPUT = 0.6 / 1_000_000

# 2026-09-14 is a Monday, 2026-09-18 a Friday, 2026-09-19 a Saturday, 2026-09-20 a Sunday.
MONDAY = datetime.datetime(2026, 9, 14, tzinfo=UTC)
FRIDAY = datetime.datetime(2026, 9, 18, tzinfo=UTC)
SATURDAY = datetime.datetime(2026, 9, 19, tzinfo=UTC)
SUNDAY = datetime.datetime(2026, 9, 20, tzinfo=UTC)

# The forensic sample: 2026-09-13 00:00:00 +08:00 is 2026-09-12 16:00 UTC, a Saturday.
FORENSIC_INSTANT = datetime.datetime(2026, 9, 12, 16, 0, tzinfo=UTC)


def at(day: datetime.datetime, hour: int, minute: int = 0, second: int = 0) -> datetime.datetime:
    return day.replace(hour=hour, minute=minute, second=second)


def usage(prompt_tokens: int, cached_tokens: int, completion_tokens: int) -> Usage:
    return Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        prompt_tokens_details=PromptTokensDetailsWrapper(cached_tokens=cached_tokens),
    )


@pytest.mark.parametrize(
    "instant, expected",
    [
        (at(MONDAY, 0, 59, 59), "off_peak"),
        (at(MONDAY, 1, 0, 0), "peak"),
        (at(MONDAY, 3, 59, 59), "peak"),
        (at(MONDAY, 4, 0, 0), "off_peak"),
        (at(MONDAY, 5, 59, 59), "off_peak"),
        (at(MONDAY, 6, 0, 0), "peak"),
        (at(MONDAY, 9, 59, 59), "peak"),
        (at(MONDAY, 10, 0, 0), "off_peak"),
    ],
)
def test_peak_window_boundaries(instant, expected):
    assert deepseek_tier_at(instant) == expected


def test_weekday_peak_and_weekend_off_peak_at_the_same_clock_time():
    assert deepseek_tier_at(at(FRIDAY, 2)) == "peak"
    assert deepseek_tier_at(at(SATURDAY, 2)) == "off_peak"


def test_sunday_is_off_peak_inside_the_weekday_peak_window():
    assert deepseek_tier_at(at(SUNDAY, 2)) == "off_peak"
    assert deepseek_tier_at(at(SUNDAY, 8)) == "off_peak"


def test_tier_does_not_depend_on_the_offset_the_instant_is_expressed_in():
    utc = at(MONDAY, 2)
    assert deepseek_tier_at(utc) == "peak"
    assert deepseek_tier_at(utc.astimezone(datetime.timezone(datetime.timedelta(hours=8)))) == "peak"


def test_tier_rejects_a_naive_timestamp():
    with pytest.raises(ValueError):
        deepseek_tier_at(datetime.datetime(2026, 9, 14, 2))


def test_request_instant_normalizes_naive_local_and_aware_timestamps_to_utc():
    assert request_instant_utc(datetime.datetime(2026, 9, 14, 2, tzinfo=UTC)) == datetime.datetime(2026, 9, 14, 2, tzinfo=UTC)

    naive = datetime.datetime(2026, 9, 14, 2)
    normalized = request_instant_utc(naive)
    assert normalized is not None
    assert normalized.tzinfo is not None
    # A naive value is wall-clock local, so it must land on the UTC instant local
    # time 02:00 corresponds to, not be relabelled as 02:00 UTC.
    assert normalized == naive.astimezone().astimezone(UTC)


def test_an_epoch_request_timestamp_is_read_as_the_instant_it_denotes():
    # `litellm_logging.start_time` holds whatever the caller passed, and the files
    # handlers pass `time.time()`. An epoch value is already unambiguous UTC.
    assert request_instant_utc(0) == datetime.datetime(1970, 1, 1, tzinfo=UTC)
    assert request_instant_utc(FORENSIC_INSTANT.timestamp()) == FORENSIC_INSTANT


@pytest.mark.parametrize("start_time", [None, True, "2026-09-12T16:00:00Z", object()])
def test_a_request_timestamp_that_carries_no_instant_resolves_to_none(start_time):
    assert request_instant_utc(start_time) is None


def test_a_non_deepseek_request_never_reads_the_request_timestamp():
    """
    The files handlers pass `time.time()` as `start_time`, so a request DeepSeek does
    not serve must cost the same whether that timestamp is a datetime or a float. It
    used to be read for every request, which turned the float into an AttributeError
    that the surrounding handler swallowed by reporting no cost at all.
    """
    logging_obj = Logging(
        model="gpt-4o",
        messages=[],
        stream=False,
        call_type="completion",
        start_time=time.time(),
        litellm_call_id="lit0104-float-start-time",
        function_id="fn-lit0104",
    )
    logging_obj.update_environment_variables(
        model="gpt-4o",
        user="",
        optional_params={},
        litellm_params={"api_base": "", "custom_llm_provider": "openai"},
    )
    assert isinstance(logging_obj.model_call_details["start_time"], float)

    cost = completion_cost(
        completion_response=ModelResponse(
            model="gpt-4o",
            usage=Usage(prompt_tokens=1000, completion_tokens=100, total_tokens=1100),
        ),
        model="gpt-4o",
        custom_llm_provider="openai",
        litellm_logging_obj=logging_obj,
    )
    assert cost == pytest.approx(0.0025 + 0.001)
    assert logging_obj.cost_breakdown is not None
    assert logging_obj.cost_breakdown["pricing_tier"] is None
    assert logging_obj.cost_breakdown["billing_model"] is None


@pytest.mark.parametrize(
    "model, billing_model",
    [
        ("deepseek-flash", "deepseek-flash"),
        ("deepseek-v4-flash", "deepseek-flash"),
        ("deepseek-v4-flash-vision-exp", "deepseek-flash"),
        ("deepseek/deepseek-v4-flash", "deepseek-flash"),
        ("deepseek-v4-pro", "deepseek-v4-pro"),
    ],
)
def test_billing_model_covers_the_retired_flash_aliases(model, billing_model):
    assert deepseek_billing_model(model) == billing_model


def test_unknown_model_is_not_claimed_by_deepseek():
    assert deepseek_billing_model("gpt-4o") is None
    assert not deepseek_serves_request("deepseek-chat", "deepseek", None)


def test_legacy_flash_alias_is_billed_at_the_flash_price():
    for model in ("deepseek-flash", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp"):
        pricing = deepseek_pricing_for_request(model, FORENSIC_INSTANT, custom_llm_provider="deepseek")
        assert pricing is not None
        assert pricing.billing_model == "deepseek-flash"
        assert pricing.tier == "off_peak"
        assert pricing.input_price == FLASH_OFF_PEAK_MISS
        assert pricing.cache_read_price == FLASH_OFF_PEAK_HIT
        assert pricing.output_price == FLASH_OFF_PEAK_OUTPUT


def test_openai_provider_reaches_deepseek_pricing_through_the_endpoint_only():
    assert deepseek_serves_request("deepseek-v4-flash", "openai", DEEPSEEK_BASE)
    assert deepseek_serves_request("deepseek-v4-flash", "openai", DEEPSEEK_BASE_V1)
    assert not deepseek_serves_request("deepseek-v4-flash", "openai", "https://api.openai.com/v1")
    assert not deepseek_serves_request("deepseek-v4-flash", "openai", None)
    assert not deepseek_serves_request("deepseek-v4-flash", "azure", DEEPSEEK_BASE)


FORENSIC_MODEL = "deepseek-v4-flash-vision-exp"
FORENSIC_PROMPT_TOKENS = 44870
FORENSIC_CACHED_TOKENS = 44544
FORENSIC_COMPLETION_TOKENS = 867
FORENSIC_REQUEST = {
    "model": FORENSIC_MODEL,
    "prompt_tokens": FORENSIC_PROMPT_TOKENS,
    "completion_tokens": FORENSIC_COMPLETION_TOKENS,
    "usage_object": usage(FORENSIC_PROMPT_TOKENS, FORENSIC_CACHED_TOKENS, FORENSIC_COMPLETION_TOKENS),
}

# The forensic SpendLog row: config declared 0.90 / 0.018 / 3.60 per 1M and billed
# 0.004216392 for these counts. DeepSeek's published off-peak rate card bills
# 0.000702732, which is exactly one sixth of it.
FORENSIC_OFF_PEAK_TOTAL = 0.000702732


def test_forensic_request_is_billed_at_the_published_off_peak_rate():
    for api_base in (DEEPSEEK_BASE, DEEPSEEK_BASE_V1):
        input_cost, output_cost = cost_per_token(
            custom_llm_provider="openai",
            api_base=api_base,
            request_at=FORENSIC_INSTANT,
            **FORENSIC_REQUEST,
        )
        assert input_cost + output_cost == pytest.approx(FORENSIC_OFF_PEAK_TOTAL, abs=1e-12)


def test_the_same_request_at_a_peak_instant_costs_exactly_twice_as_much():
    off_peak = sum(cost_per_token(custom_llm_provider="deepseek", request_at=FORENSIC_INSTANT, **FORENSIC_REQUEST))
    peak = sum(cost_per_token(custom_llm_provider="deepseek", request_at=at(MONDAY, 2), **FORENSIC_REQUEST))
    assert peak == pytest.approx(off_peak * 2, rel=1e-12)


def test_cached_tokens_are_not_charged_the_cache_miss_rate():
    prompt_tokens, cached_tokens, completion_tokens = 44870, 44544, 867
    input_cost, output_cost = cost_per_token(
        custom_llm_provider="deepseek",
        request_at=FORENSIC_INSTANT,
        **FORENSIC_REQUEST,
    )
    cache_miss_tokens = prompt_tokens - cached_tokens

    assert input_cost == pytest.approx(
        cache_miss_tokens * FLASH_OFF_PEAK_MISS + cached_tokens * FLASH_OFF_PEAK_HIT, abs=1e-15
    )
    assert output_cost == pytest.approx(completion_tokens * FLASH_OFF_PEAK_OUTPUT, abs=1e-15)

    charge_every_prompt_token_at_the_miss_rate = (
        prompt_tokens * FLASH_OFF_PEAK_MISS + cached_tokens * FLASH_OFF_PEAK_HIT + completion_tokens * FLASH_OFF_PEAK_OUTPUT
    )
    assert input_cost + output_cost < charge_every_prompt_token_at_the_miss_rate


def test_total_is_the_sum_of_its_parts_and_nothing_is_charged_twice():
    input_cost, output_cost = cost_per_token(
        custom_llm_provider="deepseek",
        request_at=FORENSIC_INSTANT,
        **FORENSIC_REQUEST,
    )
    directly = deepseek_cost_per_token(
        FORENSIC_MODEL,
        usage(FORENSIC_PROMPT_TOKENS, FORENSIC_CACHED_TOKENS, FORENSIC_COMPLETION_TOKENS),
        at=FORENSIC_INSTANT,
    )
    assert (input_cost, output_cost) == directly


def test_streamed_and_unstreamed_usage_with_the_same_counts_price_identically():
    streamed = Usage(
        prompt_tokens=44870,
        completion_tokens=867,
        total_tokens=45737,
        prompt_tokens_details=PromptTokensDetailsWrapper(cached_tokens=44544),
    )
    unstreamed = usage(44870, 44544, 867)
    assert streamed.model_dump() == unstreamed.model_dump()
    assert cost_per_token(custom_llm_provider="deepseek", request_at=FORENSIC_INSTANT, model="deepseek-v4-flash", usage_object=streamed) == cost_per_token(
        custom_llm_provider="deepseek", request_at=FORENSIC_INSTANT, model="deepseek-v4-flash", usage_object=unstreamed
    )


def test_a_usage_that_repeats_its_cache_hit_as_its_own_field_is_not_billed_twice():
    # The cache hit reported twice on one usage object: as the prompt detail it is, and
    # as the separate field the Anthropic Messages shape uses. The prompt already counts
    # it, so pricing the field again charges the cached tokens a second time.
    as_a_detail = usage(FORENSIC_PROMPT_TOKENS, FORENSIC_CACHED_TOKENS, FORENSIC_COMPLETION_TOKENS)
    also_as_its_own_field = Usage(
        prompt_tokens=FORENSIC_PROMPT_TOKENS,
        completion_tokens=FORENSIC_COMPLETION_TOKENS,
        total_tokens=FORENSIC_PROMPT_TOKENS + FORENSIC_COMPLETION_TOKENS,
        cache_read_input_tokens=FORENSIC_CACHED_TOKENS,
    )
    assert also_as_its_own_field.cache_read_input_tokens == FORENSIC_CACHED_TOKENS

    input_cost, output_cost = cost_per_token(
        custom_llm_provider="deepseek",
        request_at=FORENSIC_INSTANT,
        model=FORENSIC_MODEL,
        usage_object=also_as_its_own_field,
    )
    assert (input_cost, output_cost) == cost_per_token(
        custom_llm_provider="deepseek",
        request_at=FORENSIC_INSTANT,
        model=FORENSIC_MODEL,
        usage_object=as_a_detail,
    )
    assert input_cost == pytest.approx(
        (FORENSIC_PROMPT_TOKENS - FORENSIC_CACHED_TOKENS) * FLASH_OFF_PEAK_MISS
        + FORENSIC_CACHED_TOKENS * FLASH_OFF_PEAK_HIT,
        abs=1e-15,
    )


def test_a_prompt_that_does_not_cover_its_cache_hit_has_the_hit_added_to_it():
    # Anthropic-format usage counts only the tokens that were not cached.
    cache_miss_tokens, cached_tokens, completion_tokens = 176, 1920, 16
    anthropic_shaped = Usage(
        prompt_tokens=cache_miss_tokens,
        completion_tokens=completion_tokens,
        total_tokens=cache_miss_tokens + completion_tokens,
        cache_read_input_tokens=cached_tokens,
    )
    input_cost, output_cost = cost_per_token(
        custom_llm_provider="deepseek",
        request_at=FORENSIC_INSTANT,
        model=FORENSIC_MODEL,
        usage_object=anthropic_shaped,
    )
    assert input_cost == pytest.approx(
        cache_miss_tokens * FLASH_OFF_PEAK_MISS + cached_tokens * FLASH_OFF_PEAK_HIT, abs=1e-15
    )
    assert output_cost == pytest.approx(completion_tokens * FLASH_OFF_PEAK_OUTPUT, abs=1e-15)


def test_streaming_that_loses_cached_tokens_would_be_priced_differently():
    with_cache = deepseek_cost_per_token("deepseek-v4-flash", usage(44870, 44544, 867), at=FORENSIC_INSTANT)
    without_cache = deepseek_cost_per_token("deepseek-v4-flash", usage(44870, 0, 867), at=FORENSIC_INSTANT)
    assert with_cache[0] < without_cache[0]


def test_custom_pricing_still_takes_precedence_over_the_deepseek_rate_card():
    input_cost, output_cost = cost_per_token(
        custom_llm_provider="deepseek",
        request_at=FORENSIC_INSTANT,
        custom_cost_per_token={"input_cost_per_token": 1.0, "output_cost_per_token": 2.0},
        **FORENSIC_REQUEST,
    )
    assert (input_cost, output_cost) == (44870.0, 1734.0)


def test_a_missing_request_timestamp_raises_instead_of_guessing_a_tier():
    with pytest.raises(ValueError):
        cost_per_token(custom_llm_provider="deepseek", **FORENSIC_REQUEST)


def test_a_missing_request_timestamp_does_not_affect_models_deepseek_does_not_serve():
    input_cost, output_cost = cost_per_token(custom_llm_provider="openai", model="gpt-4o", usage_object=usage(1000, 0, 100))
    assert (input_cost, output_cost) == (0.0025, 0.001)


def test_cache_read_breakdown_uses_the_same_rate_as_the_total():
    breakdown = get_token_type_cost_breakdown(
        model="deepseek-v4-flash-vision-exp",
        custom_llm_provider="deepseek",
        usage=usage(44870, 44544, 867),
        request_at=FORENSIC_INSTANT,
    )
    assert breakdown.cache_read_cost == pytest.approx(44544 * FLASH_OFF_PEAK_HIT, abs=1e-15)
    assert breakdown.cache_creation_cost == 0.0


def test_cache_read_breakdown_runs_through_the_openai_provider_path():
    breakdown = get_token_type_cost_breakdown(
        model="deepseek-v4-flash-vision-exp",
        custom_llm_provider="openai",
        usage=usage(44870, 44544, 867),
        request_at=FORENSIC_INSTANT,
        api_base=DEEPSEEK_BASE_V1,
    )
    assert breakdown.cache_read_cost == pytest.approx(44544 * FLASH_OFF_PEAK_HIT, abs=1e-15)


def test_breakdown_is_unaffected_when_the_request_is_not_deepseeks():
    breakdown = get_token_type_cost_breakdown(
        model="gpt-4o",
        custom_llm_provider="openai",
        usage=usage(1000, 0, 100),
        request_at=FORENSIC_INSTANT,
    )
    assert breakdown.cache_read_cost == 0.0


def _cost_breakdown_for(logging_obj: Logging, **completion_kwargs) -> CostBreakdown:
    completion_cost(
        completion_response=ModelResponse(model="deepseek-v4-flash", usage=usage(44870, 44544, 867)),
        litellm_logging_obj=logging_obj,
        **completion_kwargs,
    )
    breakdown = logging_obj.cost_breakdown
    assert breakdown is not None
    return breakdown


def _deepseek_logging_obj(instant: datetime.datetime) -> Logging:
    logging_obj = Logging(
        model="deepseek-v4-flash",
        messages=[],
        stream=False,
        call_type="completion",
        start_time=instant,
        litellm_call_id="lit0104-pricing-basis",
        function_id="fn-lit0104",
    )
    logging_obj.update_environment_variables(
        model="deepseek-v4-flash",
        user="",
        optional_params={},
        litellm_params={"api_base": DEEPSEEK_BASE_V1, "custom_llm_provider": "openai"},
    )
    return logging_obj


def test_the_spend_log_records_which_rate_card_the_cost_was_priced_on():
    breakdown = _cost_breakdown_for(
        _deepseek_logging_obj(FORENSIC_INSTANT),
        model="deepseek-v4-flash-vision-exp",
        custom_llm_provider="openai",
        api_base=DEEPSEEK_BASE_V1,
    )
    assert breakdown["billing_model"] == "deepseek-flash"
    assert breakdown["pricing_tier"] == "off_peak"
    assert breakdown["pricing_source"] == "deepseek_dynamic"
    assert breakdown["effective_input_price"] == FLASH_OFF_PEAK_MISS
    assert breakdown["effective_cache_read_price"] == FLASH_OFF_PEAK_HIT
    assert breakdown["effective_output_price"] == FLASH_OFF_PEAK_OUTPUT


def test_the_recorded_rate_card_switches_with_the_request_instant():
    off_peak = _cost_breakdown_for(
        _deepseek_logging_obj(FORENSIC_INSTANT), model="deepseek-v4-flash", custom_llm_provider="deepseek"
    )
    peak = _cost_breakdown_for(
        _deepseek_logging_obj(at(MONDAY, 2)), model="deepseek-v4-flash", custom_llm_provider="deepseek"
    )
    assert off_peak["pricing_tier"] == "off_peak"
    assert peak["pricing_tier"] == "peak"
    assert peak["effective_input_price"] == pytest.approx(off_peak["effective_input_price"] * 2)
    assert peak["effective_cache_read_price"] == pytest.approx(off_peak["effective_cache_read_price"] * 2)
    assert peak["effective_output_price"] == pytest.approx(off_peak["effective_output_price"] * 2)


def test_the_recorded_rates_reproduce_the_recorded_cost():
    breakdown = _cost_breakdown_for(
        _deepseek_logging_obj(FORENSIC_INSTANT),
        model="deepseek-v4-flash-vision-exp",
        custom_llm_provider="openai",
        api_base=DEEPSEEK_BASE_V1,
    )
    recomputed = (
        (44870 - 44544) * breakdown["effective_input_price"]
        + 44544 * breakdown["effective_cache_read_price"]
        + 867 * breakdown["effective_output_price"]
    )
    assert recomputed == pytest.approx(breakdown["total_cost"], abs=1e-15)
