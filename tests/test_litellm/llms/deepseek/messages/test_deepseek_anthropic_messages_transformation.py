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


# --- LIT-0220: inline tool_definition blocks must be converted WITHOUT silent loss ---
import pytest

_TOOL = "mcp__example__deferred_batch"


def _messages_with(block, *, second_block=None):
    content = [
        {"type": "tool_result", "tool_use_id": "toolu_01", "content": [{"type": "text", "text": "done"}]},
        block,
    ]
    if second_block is not None:
        content.append(second_block)
    return [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
        {"role": "user", "content": content},
    ]


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


def _valid_def(block_extra=None, spelling="name", schema=None):
    block = {"type": "tool_definition", spelling: _TOOL, "description": "batch docs"}
    if schema is not None:
        block["input_schema"] = schema
    elif spelling == "name":
        block["input_schema"] = {"type": "object", "properties": {}}
    if block_extra:
        block.update(block_extra)
    return block


def test_inline_valid_named_definition_is_hoisted_and_referenced():
    request = _transform(_messages_with(_valid_def()))
    # block converted, not dropped
    types = [b["type"] for b in request["messages"][2]["content"]]
    assert types == ["tool_result", "tool_reference"]
    assert request["messages"][2]["content"][1] == {"type": "tool_reference", "tool_name": _TOOL}
    # declaration hoisted into tools[]
    assert any(t.get("name") == _TOOL for t in request["tools"])


def test_inline_valid_definition_accepts_tool_name_spelling():
    request = _transform(_messages_with(_valid_def(spelling="tool_name",
                                                   schema={"type": "object", "properties": {}})))
    assert request["messages"][2]["content"][1] == {"type": "tool_reference", "tool_name": _TOOL}


def test_inline_definition_already_declared_is_referenced_without_duplicate():
    request = _transform(_messages_with(_valid_def()),
                         tools=[{"name": _TOOL, "description": "pre", "input_schema": {"type": "object", "properties": {}}}])
    assert request["messages"][2]["content"][1] == {"type": "tool_reference", "tool_name": _TOOL}
    assert sum(1 for t in request["tools"] if t.get("name") == _TOOL) == 1


def test_nameless_inline_definition_fails_closed_not_silently_dropped():
    with pytest.raises(litellm.BadRequestError):
        _transform(_messages_with({"type": "tool_definition", "description": "no name", "input_schema": {"type": "object"}}))


def test_inline_definition_without_valid_schema_and_undeclared_fails_closed():
    with pytest.raises(litellm.BadRequestError):
        _transform(_messages_with({"type": "tool_definition", "name": _TOOL, "input_schema": "not-a-dict"}))


def test_inline_definition_only_content_fails_closed_without_empty_message():
    # claim: a message whose only part is an unconvertible block must NOT become empty silently
    messages = [{"role": "user", "content": [{"type": "tool_definition", "input_schema": "bad"}]}]
    with pytest.raises(litellm.BadRequestError):
        _transform(messages)


def test_duplicate_conflicting_inline_definitions_fail_closed():
    a = _valid_def(schema={"type": "object", "properties": {"a": {"type": "string"}}})
    b = _valid_def(schema={"type": "object", "properties": {"b": {"type": "integer"}}})
    with pytest.raises(litellm.BadRequestError):
        _transform(_messages_with(a, second_block=b))


def test_duplicate_identical_inline_definitions_dedupe():
    a = _valid_def()
    b = _valid_def()
    request = _transform(_messages_with(a, second_block=b))
    assert sum(1 for t in request["tools"] if t.get("name") == _TOOL) == 1
    types = [p["type"] for p in request["messages"][2]["content"]]
    assert types == ["tool_result", "tool_reference", "tool_reference"]


def test_plain_text_and_tool_messages_byte_identical():
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_01", "name": "x", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_01", "content": "ok"}]},
    ]
    request = _transform(messages, tools=None)
    assert request["messages"] == messages
    assert "tools" not in request


def test_tool_reference_control_unchanged():
    messages = [{"role": "user", "content": [
        {"type": "tool_reference", "tool_name": _TOOL}]}]
    request = _transform(messages)
    assert request["messages"] == messages


def test_inline_block_after_tool_result_preserves_order():
    request = _transform(_messages_with(_valid_def()))
    assert [b["type"] for b in request["messages"][2]["content"]] == ["tool_result", "tool_reference"]


def test_streaming_and_non_streaming_behave_identically():
    non_stream = _transform(_messages_with(_valid_def()))
    stream = _transform(_messages_with(_valid_def()), stream=True)
    assert non_stream["messages"] == stream["messages"]
    assert non_stream["tools"] == stream["tools"]


# --- LIT-0220 phase 3: real Claude Code 2.1.296 emits a NESTED definition ---
# Binary evidence (2.1.296): block = {type:"tool_definition", definition:<toolDef>};
# accessor reads `e.definition.name`. The wrapper key `definition` must never reach tools[].


def _nested_def(*, name=_TOOL, schema={"type": "object", "properties": {}}, extra=None):
    definition = {"name": name, "description": "batch docs", "input_schema": schema}
    if extra:
        definition.update(extra)
    return {"type": "tool_definition", "definition": definition}


def test_nested_valid_definition_hoisted_without_wrapper_key():
    request = _transform(_messages_with(_nested_def()))
    assert request["messages"][2]["content"][1] == {"type": "tool_reference", "tool_name": _TOOL}
    entry = next(t for t in request["tools"] if t.get("name") == _TOOL)
    assert entry.get("input_schema") == {"type": "object", "properties": {}}
    assert entry.get("description") == "batch docs"
    # the wrapper key must NOT leak into tools[]
    assert "definition" not in entry
    assert all("definition" not in t for t in request["tools"])


def test_nested_nameless_fails_closed():
    with pytest.raises(litellm.BadRequestError):
        _transform(_messages_with({"type": "tool_definition",
                                   "definition": {"description": "x", "input_schema": {"type": "object"}}}))


def test_nested_without_schema_and_undeclared_fails_closed():
    with pytest.raises(litellm.BadRequestError):
        _transform(_messages_with({"type": "tool_definition",
                                   "definition": {"name": _TOOL, "description": "x"}}))


def test_nested_conflicting_duplicates_fail_closed():
    a = _nested_def(schema={"type": "object", "properties": {"a": {"type": "string"}}})
    b = _nested_def(schema={"type": "object", "properties": {"b": {"type": "integer"}}})
    with pytest.raises(litellm.BadRequestError):
        _transform(_messages_with(a, second_block=b))


def test_nested_identical_duplicates_dedupe():
    request = _transform(_messages_with(_nested_def(), second_block=_nested_def()))
    assert sum(1 for t in request["tools"] if t.get("name") == _TOOL) == 1
    assert [p["type"] for p in request["messages"][2]["content"]] == \
        ["tool_result", "tool_reference", "tool_reference"]


def test_nested_and_flat_both_supported():
    flat = _transform(_messages_with(_valid_def()))
    nested = _transform(_messages_with(_nested_def()))
    assert flat["messages"][2]["content"][1] == nested["messages"][2]["content"][1] == \
        {"type": "tool_reference", "tool_name": _TOOL}
    assert flat["tools"] == nested["tools"]


# --- LIT-0220 phase 5: semantic boundaries (roles, deep nesting, reference-in-tool_result) ---
def test_two_level_nesting_is_not_resolvable_and_fails_closed():
    block = {"type": "tool_definition",
             "definition": {"definition": {"name": _TOOL, "input_schema": {"type": "object"}}}}
    with pytest.raises(litellm.BadRequestError):
        _transform(_messages_with(block))


def test_inline_block_in_assistant_and_system_positions_convert():
    for role in ("assistant", "system", "user"):
        messages = [{"role": role, "content": [
            {"type": "tool_result", "tool_use_id": "t", "content": [{"type": "text", "text": "x"}]},
            _nested_def()]}]
        req = _transform(messages)
        assert req["messages"][0]["content"][1] == {"type": "tool_reference", "tool_name": _TOOL}, role


def test_tool_definition_nested_inside_tool_result_is_fail_closed():
    """SUPERSEDED (RUN-0015): the old expectation was "left untouched"; the
    transformer now refuses this deep nesting with a client 400 rather than
    forwarding an illegal block. Silently forwarding was the RUN-0007 gap."""
    inner = _nested_def()
    messages = [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t", "content": [{"type": "text", "text": "d"}, inner]}]}]
    with pytest.raises(litellm.BadRequestError):
        _transform(messages)

def _official(name="db_query", schema={"type": "object", "properties": {"q": {"type": "string"}}}):
    return {"role": "system", "content": [{"type": "tool_addition", "tool": {
        "type": "tool_definition", "definition": {"name": name, "description": "d", "input_schema": schema}}}]}


def test_official_tool_addition_hoists_definition_and_keeps_outer_in_place():
    req = _transform([{"role": "user", "content": "hi"}, _official(), {"role": "user", "content": "go"}])
    msgs = req["messages"]
    # the system message and its position are preserved
    assert msgs[1]["role"] == "system"
    part = msgs[1]["content"][0]
    assert part["type"] == "tool_addition"                       # outer kept
    assert part["tool"] == {"type": "tool_reference", "name": "db_query"}
    entry = next(t for t in req["tools"] if t.get("name") == "db_query")
    assert entry["input_schema"] == {"type": "object", "properties": {"q": {"type": "string"}}}
    assert "definition" not in entry and "tool" not in entry


def test_official_tool_addition_duplicate_is_deduped():
    req = _transform([_official(), _official()])
    assert sum(1 for t in req["tools"] if t.get("name") == "db_query") == 1
    assert all(m["content"][0]["tool"]["type"] == "tool_reference"
               for m in req["messages"] if m["role"] == "system")


def test_official_tool_addition_conflict_fails_closed():
    a = _official(schema={"type": "object", "properties": {"a": {"type": "string"}}})
    b = _official(schema={"type": "object", "properties": {"b": {"type": "integer"}}})
    with pytest.raises(litellm.BadRequestError):
        _transform([a, b])


def test_official_tool_addition_without_schema_fails_closed():
    blk = {"role": "system", "content": [{"type": "tool_addition", "tool": {
        "type": "tool_definition", "definition": {"name": "db_query"}}}]}
    with pytest.raises(litellm.BadRequestError):
        _transform([blk])


# --- LIT-0220 RUN-0015: deep-nested negative control + production-size shapes ---
def test_deep_definition_inside_tool_result_is_fail_closed():
    """A tool_definition nested inside tool_result.content[] must NOT be forwarded."""
    deep = {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1",
            "content": [{"type": "text", "text": "d"},
                        {"type": "tool_definition", "definition": {"name": "x", "input_schema": {}}}]}]}
    with pytest.raises(litellm.BadRequestError):
        _transform([deep])


def test_double_wrapped_tool_addition_is_fail_closed():
    blk = {"role": "system", "content": [{"type": "tool_addition", "tool": {
        "type": "tool_addition", "tool": {"type": "tool_definition",
                                          "definition": {"name": "x", "input_schema": {"type": "object"}}}}}]}
    with pytest.raises(litellm.BadRequestError):
        _transform([blk])


def test_same_name_identical_definitions_are_idempotent():
    req = _transform([_official(), _official()])
    assert sum(1 for t in req["tools"] if t.get("name") == "db_query") == 1


def test_large_multi_system_tool_addition_round_trips():
    pad = "A" * (64 * 1024)
    msgs = [{"role": "user", "content": "hi"}, _official(),
            {"role": "user", "content": [{"type": "text", "text": pad}]}]
    req = _transform(msgs)
    assert any(t.get("name") == "db_query" for t in req["tools"])
    assert req["messages"][2]["content"][0]["text"] == pad


# --- LIT-0220 RUN-0019: tools[] container validation + protocol-scoped guard ---
# A `tools[]` entry is a *declaration container*, identified by its own `type`
# field. A content block sitting there is not a declaration and must be refused.
# The guard walks only protocol block positions, so legal user data that merely
# mentions `tool_definition` is never rejected.


def test_tool_definition_entry_in_tools_is_rejected():
    # RED before the tools[] container check: the block was forwarded downstream.
    tools = [{"type": "tool_definition",
              "definition": {"name": "x", "input_schema": {"type": "object", "properties": {}}}}]
    with pytest.raises(litellm.BadRequestError):
        _transform([{"role": "user", "content": "hi"}], tools=tools)


def test_tool_addition_entry_in_tools_is_rejected():
    tools = [{"type": "tool_addition",
              "tool": {"type": "tool_definition",
                       "definition": {"name": "x", "input_schema": {"type": "object", "properties": {}}}}}]
    with pytest.raises(litellm.BadRequestError):
        _transform([{"role": "user", "content": "hi"}], tools=tools)


def test_schema_property_named_tool_definition_is_allowed():
    # a schema *property* called tool_definition is legal user data, not a block
    tools = [{"name": "t", "description": "d",
              "input_schema": {"type": "object",
                               "properties": {"tool_definition": {"type": "string"},
                                              "tool_reference": {"type": "string"}}}}]
    req = _transform([{"role": "user", "content": "hi"}], tools=tools)
    assert any(t.get("name") == "t" for t in req["tools"])


def test_custom_typed_tool_declaration_with_that_property_is_allowed():
    tools = [{"type": "custom", "name": "t", "description": "d",
              "input_schema": {"type": "object",
                               "properties": {"tool_definition": {"type": "string"}}}}]
    req = _transform([{"role": "user", "content": "hi"}], tools=tools)
    assert req["tools"][0].get("name") == "t"


def test_tool_use_input_mentioning_tool_definition_is_allowed():
    # tool_use.input is user JSON, not a protocol position: must not be rejected
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_1", "name": "t",
             "input": {"note": "the block is called tool_definition",
                       "shape": {"type": "tool_definition"}}}]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_1",
             "content": [{"type": "text", "text": "tool_definition is expected here"}]}]},
    ]
    req = _transform(messages)
    assert req["messages"] == messages


def test_tool_result_text_mentioning_tool_definition_is_allowed():
    messages = [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t",
         "content": [{"type": "text", "text": "unknown variant `tool_definition`"}]}]}]
    req = _transform(messages)
    assert req["messages"] == messages


def test_deep_wrapping_still_fails_closed():
    # the bounded protocol walk must still catch a triple-wrapped definition
    blk = {"role": "system", "content": [{"type": "tool_addition", "tool": {
        "type": "tool_addition", "tool": {"type": "tool_addition", "tool": {
            "type": "tool_definition", "definition": {"name": "x", "input_schema": {}}}}}}]}
    with pytest.raises(litellm.BadRequestError):
        _transform([blk])


_MAX_WRAPPERS = 7  # the innermost block still lands at depth <= _MAX_PROTOCOL_DEPTH


def _wrap_tool_result(inner, layers):
    node = inner
    for _ in range(layers):
        node = {"type": "tool_result", "tool_use_id": "toolu_wrap", "content": [node]}
    return node


def _wrap_tool_addition(inner, layers):
    node = inner
    for _ in range(layers):
        node = {"type": "tool_addition", "tool": node}
    return node


def _unconvertible_definition():
    return {"type": "tool_definition", "definition": {"name": "deep_tool", "input_schema": {"type": "object"}}}


@pytest.mark.parametrize("layers", [_MAX_WRAPPERS, _MAX_WRAPPERS + 1, _MAX_WRAPPERS + 5])
@pytest.mark.parametrize("wrapper", [_wrap_tool_result, _wrap_tool_addition], ids=["tool_result", "tool_addition"])
def test_definition_wrapped_past_supported_depth_fails_closed(wrapper, layers):
    # RED before the depth guard: past the limit the walk gave up silently, the block was
    # treated as absent, and the illegal definition was forwarded to DeepSeek untouched.
    block = wrapper(_unconvertible_definition(), layers)
    with pytest.raises(litellm.BadRequestError):
        _transform([{"role": "user", "content": [block]}])


@pytest.mark.parametrize("wrapper", [_wrap_tool_result, _wrap_tool_addition], ids=["tool_result", "tool_addition"])
def test_depth_refusal_reports_a_path_and_no_payload(wrapper):
    block = wrapper(_unconvertible_definition(), _MAX_WRAPPERS + 1)
    with pytest.raises(litellm.BadRequestError) as excinfo:
        _transform([{"role": "user", "content": [block]}])
    assert "messages[0].content[0]" in str(excinfo.value)


@pytest.mark.parametrize("tools", [{"name": "x"}, "not-a-list", 42], ids=["dict", "str", "int"])
def test_non_list_tools_fail_closed_instead_of_being_iterated(tools):
    # RED before the guard: a dict yielded its keys, a str its characters, an int a TypeError
    with pytest.raises(litellm.BadRequestError):
        _transform(_messages_with(_valid_def()), tools=tools)


def test_non_list_tools_fail_closed_even_without_inline_definitions():
    with pytest.raises(litellm.BadRequestError):
        _transform([{"role": "user", "content": "hi"}], tools={"name": "x"})


@pytest.mark.parametrize("existing", [{"name": _TOOL, "description": "pre"}, {"name": _TOOL, "input_schema": "oops"}],
                         ids=["no_schema_key", "non_dict_schema"])
def test_existing_declaration_without_usable_schema_does_not_swallow_inline_schema(existing):
    # RED before the guard: the inline schema was discarded without a word
    with pytest.raises(litellm.BadRequestError):
        _transform(_messages_with(_valid_def()), tools=[existing])


def test_schemaless_existing_and_schemaless_inline_is_still_referenced():
    # nothing is dropped when neither side carries a schema, so referencing stays legal
    request = _transform(
        _messages_with({"type": "tool_definition", "definition": {"name": _TOOL}}),
        tools=[{"name": _TOOL, "description": "pre"}],
    )
    assert request["messages"][2]["content"][1] == {"type": "tool_reference", "tool_name": _TOOL}
    assert sum(1 for t in request["tools"] if t.get("name") == _TOOL) == 1
