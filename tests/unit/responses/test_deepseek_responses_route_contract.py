"""Keep the DeepSeek native Responses opt-in AND the Responses-to-Chat bridge usable.

These are mocked protocol-contract tests, not a substitute for DeepSeek live E2E.
Strict json_schema is only tested on the native Responses path; DeepSeek Chat does not
implement strict response_format.type=json_schema, so the bridge must not pretend to.
"""

import json

import httpx
import litellm
import pytest
import respx

from litellm.llms.openai_like.responses.transformation import OpenAILikeResponsesConfig
from litellm.responses.main import (
    _bridges_to_chat_completions,
    _resolve_responses_api_provider_config,
)
from litellm.types.llms.openai import ResponsesAPIResponse

BASE_URL = "https://api.deepseek.com"
RESPONSES_URL = f"{BASE_URL}/responses"
CHAT_URL = f"{BASE_URL}/chat/completions"
MODEL = "deepseek/deepseek-flash"
NATIVE = {"supported_endpoints": ["/v1/responses"]}
CHAT_ONLY = {"supported_endpoints": ["/v1/chat/completions"]}
SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}
NATIVE_BODY = {
    "id": "resp_deepseek_mock",
    "object": "response",
    "created_at": 1761609600,
    "status": "completed",
    "model": "deepseek-flash",
    "output": [
        {
            "type": "message",
            "id": "msg_1",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": '{"ok":true}', "annotations": []}],
        }
    ],
    "parallel_tool_calls": True,
    "usage": {"input_tokens": 8, "output_tokens": 4, "total_tokens": 12},
}
CHAT_BODY = {
    "id": "chatcmpl_deepseek_mock",
    "object": "chat.completion",
    "created": 1761609600,
    "model": "deepseek-flash",
    "choices": [
        {"index": 0, "message": {"role": "assistant", "content": '{"ok":true}'}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
}


@pytest.fixture(autouse=True)
def _mock_clean_litellm_clients(monkeypatch):
    monkeypatch.setattr(litellm, "num_retries", 0)
    monkeypatch.setattr(litellm, "disable_aiohttp_transport", True)
    litellm.in_memory_llm_clients_cache.flush_cache()
    yield
    litellm.in_memory_llm_clients_cache.flush_cache()


def test_deepseek_native_opt_in_does_not_remove_chat_bridge():
    native_config = _resolve_responses_api_provider_config(
        "deepseek-flash", "deepseek", NATIVE, BASE_URL
    )
    chat_config = _resolve_responses_api_provider_config(
        "deepseek-flash", "deepseek", CHAT_ONLY, BASE_URL
    )

    assert isinstance(native_config, OpenAILikeResponsesConfig)
    assert chat_config is None
    assert not _bridges_to_chat_completions(native_config, False)
    assert _bridges_to_chat_completions(native_config, True)
    assert _bridges_to_chat_completions(chat_config, False)


@respx.mock
async def test_deepseek_native_responses_preserves_json_schema():
    native_route = respx.post(RESPONSES_URL).mock(
        return_value=httpx.Response(200, json=NATIVE_BODY)
    )
    chat_route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=CHAT_BODY)
    )
    text_format = {
        "format": {"type": "json_schema", "name": "result", "schema": SCHEMA, "strict": True}
    }

    result = await litellm.aresponses(
        model=MODEL,
        input="Return the ok field",
        api_base=BASE_URL,
        api_key="mock-key",
        text=text_format,
        model_info=NATIVE,
    )

    assert native_route.call_count == 1
    assert chat_route.call_count == 0
    body = json.loads(native_route.calls.last.request.content)
    assert body["text"]["format"] == text_format["format"]
    assert isinstance(result, ResponsesAPIResponse)


@pytest.mark.parametrize(
    ("text_format", "expected_response_format"),
    [
        ({"format": {"type": "json_object"}}, {"type": "json_object"}),
        ({"format": {"type": "text"}}, None),
    ],
)
@respx.mock
async def test_deepseek_chat_bridge_keeps_supported_formats(text_format, expected_response_format):
    native_route = respx.post(RESPONSES_URL).mock(
        return_value=httpx.Response(200, json=NATIVE_BODY)
    )
    chat_route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=CHAT_BODY)
    )

    result = await litellm.aresponses(
        model=MODEL,
        input="Return JSON",
        api_base=BASE_URL,
        api_key="mock-key",
        text=text_format,
        model_info=CHAT_ONLY,
    )

    assert native_route.call_count == 0
    assert chat_route.call_count == 1
    body = json.loads(chat_route.calls.last.request.content)
    assert body.get("response_format") == expected_response_format
    assert isinstance(result, ResponsesAPIResponse)
    assert result.output[0].content[0].text == '{"ok":true}'


@respx.mock
async def test_deepseek_opted_in_native_responses_can_still_force_chat_bridge():
    native_route = respx.post(RESPONSES_URL).mock(
        return_value=httpx.Response(200, json=NATIVE_BODY)
    )
    chat_route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=CHAT_BODY)
    )

    result = await litellm.aresponses(
        model=MODEL,
        input="Return JSON",
        api_base=BASE_URL,
        api_key="mock-key",
        model_info=NATIVE,
        use_chat_completions_api=True,
        text={"format": {"type": "json_object"}},
    )

    assert native_route.call_count == 0
    assert chat_route.call_count == 1
    assert json.loads(chat_route.calls.last.request.content)["response_format"] == {
        "type": "json_object"
    }
    assert isinstance(result, ResponsesAPIResponse)
