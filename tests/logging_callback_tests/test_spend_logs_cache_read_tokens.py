from datetime import datetime, timezone

import litellm

from litellm.models.spend_logs import LiteLLM_SpendLogs
from litellm.proxy.spend_tracking.spend_tracking_utils import get_logging_payload


def _payload_for_usage(usage: litellm.Usage):
    now = datetime.now(timezone.utc)
    return get_logging_payload(
        kwargs={
            "model": "test-model",
            "call_type": "acompletion",
            "litellm_call_id": "cache-read-test",
            "litellm_params": {},
        },
        response_obj=litellm.ModelResponse(
            id="cache-read-test",
            model="test-model",
            choices=[],
            usage=usage,
        ),
        start_time=now,
        end_time=now,
    )


def test_spend_log_payload_extracts_anthropic_cache_read_tokens():
    payload = _payload_for_usage(
        litellm.Usage(
            prompt_tokens=100,
            completion_tokens=10,
            total_tokens=110,
            cache_read_input_tokens=41,
        )
    )

    assert payload["cache_read_input_tokens"] == 41


def test_spend_log_payload_extracts_openai_compatible_cached_tokens():
    payload = _payload_for_usage(
        litellm.Usage(
            prompt_tokens=100,
            completion_tokens=10,
            total_tokens=110,
            prompt_tokens_details={"cached_tokens": 37},
        )
    )

    assert payload["cache_read_input_tokens"] == 37


def test_spend_log_model_exposes_cache_read_tokens():
    row = LiteLLM_SpendLogs(
        request_id="req-1",
        api_key="hashed-key",
        model="test-model",
        call_type="acompletion",
        startTime="2026-09-07T00:00:00Z",
        endTime="2026-09-07T00:00:01Z",
        messages={},
        response={},
        cache_read_input_tokens=23,
    )

    assert row.cache_read_input_tokens == 23
