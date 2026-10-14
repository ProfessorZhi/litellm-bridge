import pytest

import litellm
from litellm.llms.anthropic.experimental_pass_through.messages.transformation import (
    AnthropicMessagesConfig,
)
from litellm.llms.deepseek.messages.transformation import (
    DeepSeekAnthropicMessagesConfig,
)
from litellm.types.router import GenericLiteLLMParams
from litellm.utils import ProviderConfigManager


def test_deepseek_provider_uses_anthropic_messages_config():
    config = ProviderConfigManager.get_provider_anthropic_messages_config(
        model="deepseek-v4-pro",
        provider=litellm.LlmProviders.DEEPSEEK,
    )

    assert isinstance(config, DeepSeekAnthropicMessagesConfig)
    assert config.custom_llm_provider == "deepseek"


def test_deepseek_anthropic_messages_config_defaults():
    config = DeepSeekAnthropicMessagesConfig()

    assert config.custom_llm_provider == "deepseek"
    assert config.get_api_base() == "https://api.deepseek.com/anthropic"


def test_anthropic_provider_keeps_default_config_for_deepseek_named_model():
    config = ProviderConfigManager.get_provider_anthropic_messages_config(
        model="deepseek-v4-pro",
        provider=litellm.LlmProviders.ANTHROPIC,
    )

    assert isinstance(config, AnthropicMessagesConfig)
    assert not isinstance(config, DeepSeekAnthropicMessagesConfig)


def test_deepseek_anthropic_messages_url_defaults_to_anthropic_endpoint():
    config = DeepSeekAnthropicMessagesConfig()

    assert (
        config.get_complete_url(
            api_base=None,
            api_key=None,
            model="deepseek-v4-pro",
            optional_params={},
            litellm_params={},
        )
        == "https://api.deepseek.com/anthropic/v1/messages"
    )
    assert (
        config.get_complete_url(
            api_base="https://api.deepseek.com/anthropic/v1",
            api_key=None,
            model="deepseek-v4-pro",
            optional_params={},
            litellm_params={},
        )
        == "https://api.deepseek.com/anthropic/v1/messages"
    )
    assert (
        config.get_complete_url(
            api_base="https://api.deepseek.com/anthropic",
            api_key=None,
            model="deepseek-v4-pro",
            optional_params={},
            litellm_params={},
        )
        == "https://api.deepseek.com/anthropic/v1/messages"
    )
    assert (
        config.get_complete_url(
            api_base="https://api.deepseek.com",
            api_key=None,
            model="deepseek-v4-pro",
            optional_params={},
            litellm_params={},
        )
        == "https://api.deepseek.com/anthropic/v1/messages"
    )
    assert (
        config.get_complete_url(
            api_base="https://api.deepseek.com/v1",
            api_key=None,
            model="deepseek-v4-pro",
            optional_params={},
            litellm_params={},
        )
        == "https://api.deepseek.com/anthropic/v1/messages"
    )
    assert (
        config.get_complete_url(
            api_base="https://api.deepseek.com/v1/messages",
            api_key=None,
            model="deepseek-v4-pro",
            optional_params={},
            litellm_params={},
        )
        == "https://api.deepseek.com/anthropic/v1/messages"
    )


def test_deepseek_anthropic_messages_headers_use_deepseek_key():
    config = DeepSeekAnthropicMessagesConfig()

    headers, api_base = config.validate_anthropic_messages_environment(
        headers={},
        model="deepseek-v4-pro",
        messages=[],
        optional_params={},
        litellm_params={},
        api_key="sk-deepseek",
        api_base="https://example.test/anthropic",
    )

    assert api_base == "https://example.test/anthropic"
    assert headers["x-api-key"] == "sk-deepseek"
    assert headers["anthropic-version"] == "2023-06-01"
    assert headers["content-type"] == "application/json"


def test_deepseek_anthropic_messages_preserves_thinking_and_sanitizes_custom_tools():
    config = DeepSeekAnthropicMessagesConfig()
    messages = [
        {
            "role": "user",
            "content": "Use the tool.",
        },
        {
            "role": "assistant",
            "content": [
                {
                    "type": "thinking",
                    "thinking": "I should call the tool.",
                    "signature": "sig",
                },
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "get_weather",
                    "input": {"city": "Sao Paulo"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_123",
                    "content": "Sunny",
                }
            ],
        },
    ]

    request = config.transform_anthropic_messages_request(
        model="deepseek-v4-pro",
        messages=messages,
        anthropic_messages_optional_request_params={
            "max_tokens": 100,
            "thinking": {"type": "enabled", "budget_tokens": 1024},
            "tools": [
                {
                    "type": "custom",
                    "name": "get_weather",
                    "description": "Get weather",
                    "input_schema": {"type": "object"},
                },
                {
                    "type": "web_search_20260209",
                    "name": "web_search",
                    "max_uses": 1,
                },
            ],
        },
        litellm_params=GenericLiteLLMParams(),
        headers={},
    )

    assert request["messages"] == messages
    assert request["thinking"] == {"type": "enabled", "budget_tokens": 1024}
    assert request["tools"][0] == {
        "name": "get_weather",
        "description": "Get weather",
        "input_schema": {"type": "object"},
    }
    assert request["tools"][1]["type"] == "web_search_20260209"


# DeepSeek's Anthropic layer accepts `tool_reference` but has no `tool_definition`
# variant, so a client that inlines a deferred tool's definition gets a 422 it cannot
# act on. These tests pin the downgrade and, just as much, what it refuses to guess at.

_TOOL = "mcp__example__deferred_batch"
_SCHEMA = {"type": "object", "properties": {}}
_SHAPES = ("flat", "nested", "official")


def _body(**overrides):
    body = {"name": _TOOL, "description": "batch docs", "input_schema": _SCHEMA}
    body.update(overrides)
    return body


def _declaration_message(body, shape):
    """One message whose last content block declares the tool, in the requested shape.

    `flat` puts the definition fields straight on the block, `nested` wraps them in
    `definition`, and `official` is the documented mid-conversation form: a
    `tool_addition` in a system message whose `tool` is the `tool_definition`.
    """
    if shape == "flat":
        return {"role": "user", "content": [{"type": "tool_definition", **body}]}
    if shape == "nested":
        return {"role": "user", "content": [{"type": "tool_definition", "definition": body}]}
    return {
        "role": "system",
        "content": [{"type": "tool_addition", "tool": {"type": "tool_definition", "definition": body}}],
    }


def _messages(*bodies, shape="nested"):
    return [_declaration_message(body, shape) for body in bodies]


def _transform(messages, tools=None, *, stream=False):
    config = DeepSeekAnthropicMessagesConfig()
    params = {"max_tokens": 100}
    if tools is not None:
        params["tools"] = tools
    if stream:
        params["stream"] = True
    return config.transform_anthropic_messages_request(
        model="deepseek-v4-pro",
        messages=messages,
        anthropic_messages_optional_request_params=params,
        litellm_params=GenericLiteLLMParams(),
        headers={},
    )


def _converted(request, index=0):
    """The block the declaration at `index` became: the reference, unwrapped if official."""
    part = request["messages"][index]["content"][-1]
    return part["tool"] if part["type"] == "tool_addition" else part


def _reference(shape, name=_TOOL):
    """The reference spelling of the dialect that carried the definition.

    Anthropic's own `tool_addition.tool` names a tool with `name`; the tool-result and
    flat dialects use `tool_name`. Each position keeps the spelling it arrived with.
    """
    key = "name" if shape == "official" else "tool_name"
    return {"type": "tool_reference", key: name}


# --- requests with nothing to convert are passed through untouched ---


def test_no_inline_request_is_returned_unchanged():
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_01", "name": "x", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_01", "content": "ok"}]},
    ]

    request = _transform(messages)

    assert request["messages"] == messages
    assert "tools" not in request


def test_existing_tool_reference_block_is_untouched():
    messages = [{"role": "user", "content": [{"type": "tool_reference", "tool_name": _TOOL}]}]

    assert _transform(messages)["messages"] == messages


def test_streaming_and_non_streaming_agree():
    non_stream = _transform(_messages(_body()), stream=False)
    stream = _transform(_messages(_body()), stream=True)

    assert non_stream["messages"] == stream["messages"]
    assert non_stream["tools"] == stream["tools"]


# --- the accepted shapes convert and hoist ---


@pytest.mark.parametrize("shape", _SHAPES)
def test_declaration_converts_to_a_reference_and_hoists_its_entry(shape):
    request = _transform(_messages(_body(), shape=shape), tools=[])

    assert _converted(request) == _reference(shape)
    assert request["tools"] == [{"name": _TOOL, "description": "batch docs", "input_schema": _SCHEMA}]


def test_official_addition_keeps_its_system_message_and_position():
    messages = [
        {"role": "user", "content": "hi"},
        _declaration_message(_body(), "official"),
        {"role": "user", "content": "go"},
    ]

    request = _transform(messages, tools=[])

    assert [m["role"] for m in request["messages"]] == ["user", "system", "user"]
    assert request["messages"][1]["content"][0] == {
        "type": "tool_addition",
        "tool": {"type": "tool_reference", "name": _TOOL},
    }


@pytest.mark.parametrize("role", ["user", "assistant", "system"])
def test_a_declaration_may_be_carried_by_any_message_role(role):
    message = _declaration_message(_body(), "nested")
    message["role"] = role

    request = _transform([message], tools=[])

    assert _converted(request) == {"type": "tool_reference", "tool_name": _TOOL}


def test_a_declaration_carried_flat_on_the_wrapped_tool_is_hoisted():
    # the wrapper is official, but the definition fields sit on its `tool` instead of
    # under a `definition` key; the name and the schema must still be read from there
    part = {"type": "tool_addition", "tool": {"type": "tool_definition", **_body()}}

    request = _transform([{"role": "system", "content": [part]}], tools=[])

    assert _converted(request) == {"type": "tool_reference", "name": _TOOL}
    assert [t["name"] for t in request["tools"]] == [_TOOL]


# --- how the declared name is resolved ---


@pytest.mark.parametrize("shape", _SHAPES)
@pytest.mark.parametrize("spelling", ["name", "tool_name"])
def test_the_name_may_be_spelled_either_way(shape, spelling):
    body = {"description": "batch docs", "input_schema": _SCHEMA, spelling: _TOOL}

    request = _transform(_messages(body, shape=shape), tools=[])

    assert _converted(request) == _reference(shape)
    assert [t["name"] for t in request["tools"]] == [_TOOL]


def test_a_block_that_repeats_the_name_identically_is_accepted():
    request = _transform(_messages(_body(tool_name=_TOOL)), tools=[])

    assert _converted(request) == _reference("nested")


def test_a_block_that_spells_the_name_two_disagreeing_ways_is_refused():
    # RED: `name` used to win silently, so one block could resolve to two tools
    with pytest.raises(litellm.BadRequestError):
        _transform(_messages(_body(tool_name="a_different_tool")))


# --- what makes two declarations of one name the same tool ---


@pytest.mark.parametrize("shape", _SHAPES)
def test_repeated_declarations_convert_in_place_and_hoist_one_entry(shape):
    request = _transform(_messages(_body(), _body(), _body(), shape=shape), tools=[_body()])

    assert [_converted(request, i) for i in range(3)] == [_reference(shape)] * 3
    assert [t["name"] for t in request["tools"]] == [_TOOL]


def test_transport_metadata_is_not_a_conflict():
    # `cache_control` only directs caching, and a `custom` type is the ordinary client
    # tool this transform strips before sending, so neither may split one tool in two
    existing = {**_body(), "type": "custom", "cache_control": {"type": "ephemeral"}}

    request = _transform(_messages(_body()), tools=[existing])

    assert _converted(request) == _reference("nested")
    assert len(request["tools"]) == 1


def test_a_declaration_that_names_a_different_tool_type_is_a_conflict():
    # RED: `type` was dropped from the comparison, so a plain tool of the same name
    # silently merged with a versioned server tool. A server tool is not a custom tool
    existing = [_body(name="web_search", type="web_search_20260209")]

    with pytest.raises(litellm.BadRequestError):
        _transform(_messages(_body(name="web_search")), tools=existing)


@pytest.mark.parametrize(
    "existing",
    [_body(description="stale docs"), _body(input_schema={"type": "object", "properties": {"q": {}}})],
    ids=["description", "schema"],
)
def test_a_conflicting_declaration_of_a_known_name_is_refused(existing):
    # RED before the comparison: the inline declaration was discarded without a word and
    # the model saw the tools[] one instead
    with pytest.raises(litellm.BadRequestError):
        _transform(_messages(_body()), tools=[existing])


@pytest.mark.parametrize("shape", _SHAPES)
def test_hoisting_copies_every_field_and_drops_only_the_wrapper(shape):
    body = _body(title="Batch", strict=True)

    request = _transform(_messages(body, shape=shape), tools=[])

    entry = request["tools"][0]
    assert entry["title"] == "Batch"
    assert entry["strict"] is True
    assert "definition" not in entry
    assert "tool" not in entry


def test_hoisting_keeps_the_tool_type_the_declaration_carried():
    # a server tool's `type` is what makes it that tool; dropping it would silently
    # turn the declaration into an ordinary client tool
    body = _body(type="web_search_20260209")

    request = _transform(_messages(body, shape="nested"), tools=[])

    assert request["tools"][0]["type"] == "web_search_20260209"


# --- refusals: a declaration that cannot be converted losslessly ---

_DEFECTS = {
    "nameless": {"description": "batch docs", "input_schema": _SCHEMA},
    "no_schema_key": {"name": _TOOL, "description": "batch docs"},
    "string_schema": {"name": _TOOL, "input_schema": "oops"},
    "boolean_schema": {"name": _TOOL, "input_schema": True},
}


@pytest.mark.parametrize("defect", sorted(_DEFECTS))
@pytest.mark.parametrize("shape", _SHAPES)
def test_a_declaration_without_a_name_and_an_object_schema_is_refused(shape, defect):
    with pytest.raises(litellm.BadRequestError):
        _transform(_messages(_DEFECTS[defect], shape=shape))


def test_a_schemaless_declaration_is_refused_even_when_the_name_is_already_declared():
    # RED: the block was dropped silently and the request went on with the tools[] entry,
    # which is not evidence that the two describe the same tool
    body = {"name": _TOOL}

    with pytest.raises(litellm.BadRequestError):
        _transform(_messages(body), tools=[{"name": _TOOL, "description": "pre"}])


def test_a_two_level_wrapped_definition_is_refused():
    block = {"type": "tool_definition", "definition": {"definition": {"name": _TOOL, "input_schema": _SCHEMA}}}

    with pytest.raises(litellm.BadRequestError):
        _transform(_messages(block))


@pytest.mark.parametrize("layers", [1, 3])
def test_a_definition_under_a_tool_result_content_is_refused(layers):
    node = {"type": "tool_definition", "definition": _body()}
    for _ in range(layers):
        node = {"type": "tool_result", "tool_use_id": "t", "content": [node]}

    with pytest.raises(litellm.BadRequestError):
        _transform([{"role": "user", "content": [node]}])


@pytest.mark.parametrize("layers", [2, 3])
def test_a_doubly_wrapped_tool_addition_is_refused(layers):
    node = {"type": "tool_definition", "definition": _body()}
    for _ in range(layers):
        node = {"type": "tool_addition", "tool": node}

    with pytest.raises(litellm.BadRequestError):
        _transform([{"role": "system", "content": [node]}])


def test_nesting_past_the_protocol_depth_limit_is_refused():
    # the walk is bounded, and giving up on a subtree must not read as "nothing illegal
    # in there"; without the bound this body comes back untouched
    node = {"type": "text", "text": "x"}
    for _ in range(12):
        node = {"type": "tool_result", "tool_use_id": "t", "content": [node]}

    with pytest.raises(litellm.BadRequestError):
        _transform([{"role": "user", "content": [node]}])


def test_a_refusal_names_the_position_it_refused():
    block = {"type": "tool_definition", "definition": {"name": _TOOL}}

    with pytest.raises(litellm.BadRequestError) as excinfo:
        _transform(_messages(block))

    assert "messages[0].content[0]" in str(excinfo.value)


@pytest.mark.parametrize(
    "tools",
    [{"type": "tool_definition", "definition": _body()}, {"type": "tool_addition", "tool": {"type": "tool_definition", "definition": _body()}}],
    ids=["tool_definition", "tool_addition"],
)
def test_a_tools_entry_that_is_a_content_block_is_refused(tools):
    # RED before the container check: the block was forwarded to the provider as a tool
    with pytest.raises(litellm.BadRequestError):
        _transform([{"role": "user", "content": "hi"}], tools=[tools])


@pytest.mark.parametrize("tools", [{"name": "x"}, "not-a-list", 42, ({"name": "x"},)], ids=["dict", "str", "int", "tuple"])
def test_a_non_list_tools_container_is_refused(tools):
    # RED before the guard: a dict yielded its keys, a str its characters, an int a TypeError
    with pytest.raises(litellm.BadRequestError):
        _transform(_messages(_body()), tools=tools)


def test_a_non_list_tools_container_is_refused_without_inline_definitions():
    with pytest.raises(litellm.BadRequestError):
        _transform([{"role": "user", "content": "hi"}], tools={"name": "x"})


# --- pinned boundaries: legal traffic the guard must leave alone ---


def test_a_tool_reference_entry_in_tools_is_forwarded():
    tools = [{"type": "tool_reference", "tool_name": _TOOL}]

    assert _transform([{"role": "user", "content": "hi"}], tools=tools)["tools"] == tools


def test_user_data_that_merely_mentions_a_block_type_is_untouched():
    # tool_use.input and tool_result content are user JSON, not protocol positions: the
    # provider never parses a block out of them, so neither is scanned nor rejected
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_1", "name": "t",
                                           "input": {"note": "the block is called tool_definition",
                                                     "shape": {"type": "tool_definition"}}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1",
                                      "content": [{"type": "text", "text": "unknown variant `tool_definition`"}]}]},
    ]

    assert _transform(messages)["messages"] == messages


@pytest.mark.parametrize("type_field", [{}, {"type": "custom"}], ids=["untyped", "custom"])
def test_a_schema_property_named_like_a_block_type_is_allowed(type_field):
    tools = [{**type_field, "name": "t", "description": "d",
              "input_schema": {"type": "object",
                               "properties": {"tool_definition": {"type": "string"},
                                              "tool_reference": {"type": "string"}}}}]

    request = _transform([{"role": "user", "content": "hi"}], tools=tools)

    assert request["tools"][0]["name"] == "t"


def test_a_large_payload_around_a_declaration_round_trips():
    pad = "A" * (64 * 1024)
    messages = [
        {"role": "user", "content": "hi"},
        _declaration_message(_body(), "official"),
        {"role": "user", "content": [{"type": "text", "text": pad}]},
    ]

    request = _transform(messages)

    assert any(t.get("name") == _TOOL for t in request["tools"])
    assert request["messages"][2]["content"][0]["text"] == pad
