"""Resolve the tool names a request can make the provider act on.

Authorization must see every tool a request declares, including one added inline in a
system message. A mid-conversation ``tool_removal`` is not subtracted: the
chat-completions and Responses bridges drop the removal block but still forward
``tools[]``, so trusting the removal would hide a tool the provider can still call.
A removal-only request therefore still has to satisfy the allowlist.
"""

import json
from collections.abc import Iterable, Iterator, Mapping, Sequence, Set
from itertools import chain
from typing import Final

from pydantic import TypeAdapter, ValidationError

from litellm.llms.base_llm.guardrail_translation.utils import anthropic_tool_names
from litellm.types.llms.openai import ChatCompletionToolParam, ChatCompletionToolParamFunctionChunk

_ANTHROPIC_MESSAGES_CALL_TYPES: Final = frozenset({"anthropic_messages", "aanthropic_messages"})

_OBJECT_MAPPING: Final = TypeAdapter(Mapping[str, object])
_OBJECT_LIST: Final = TypeAdapter(list[object])


def object_mapping(value: object) -> Mapping[str, object] | None:
    """A JSON object as a typed read-only mapping, or None when ``value`` is not one."""
    if not isinstance(value, Mapping):
        return None
    try:
        return _OBJECT_MAPPING.validate_python(value)
    except ValidationError:
        return None


def object_list(value: object) -> tuple[object, ...]:
    """A JSON array as a tuple, or an empty tuple when ``value`` is not one."""
    if not isinstance(value, list):
        return ()
    try:
        return tuple(_OBJECT_LIST.validate_python(value))
    except ValidationError:
        return ()


def _dedupe(names: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(names))


def _definition_name(tool: Mapping[str, object]) -> str | None:
    definition: Final = object_mapping(tool.get("definition"))
    if definition is None:
        return None
    name: Final = definition.get("name")
    return name if isinstance(name, str) and name else None


def _reference_name(tool: Mapping[str, object]) -> str | None:
    name: Final = tool.get("name")
    return name if isinstance(name, str) and name else None


def inline_tool_addition_name(block: object) -> str | None:
    """The name an inline ``tool_addition`` declares, or None when ``block`` is not one."""
    fields: Final = object_mapping(block)
    if fields is None or fields.get("type") != "tool_addition":
        return None
    tool: Final = object_mapping(fields.get("tool"))
    if tool is None:
        return None
    tool_type: Final = tool.get("type")
    if tool_type == "tool_definition":
        return _definition_name(tool)
    if tool_type == "tool_reference":
        return _reference_name(tool)
    return None


def _system_content_blocks(messages: object) -> Iterator[object]:
    for raw_message in object_list(messages):
        message = object_mapping(raw_message)
        if message is None or message.get("role") != "system":
            continue
        yield from object_list(message.get("content"))


def _iter_added_names(messages: object) -> Iterator[str]:
    for block in _system_content_blocks(messages):
        name = inline_tool_addition_name(block)
        if name is not None:
            yield name


def _definition_from_addition(block: object) -> Iterator[Mapping[str, object]]:
    fields: Final = object_mapping(block)
    if fields is None or fields.get("type") != "tool_addition":
        return
    tool: Final = object_mapping(fields.get("tool"))
    if tool is None or tool.get("type") != "tool_definition":
        return
    definition: Final = object_mapping(tool.get("definition"))
    if definition is not None and _definition_name(tool) is not None:
        yield definition


def inline_tool_definitions(data: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    """Definitions carried by inline additions, for guardrails that inspect tool schemas."""
    return tuple(
        chain.from_iterable(_definition_from_addition(block) for block in _system_content_blocks(data.get("messages")))
    )


def strip_inline_tool_additions(message: object, names: Set[str]) -> object:
    """Drop the inline additions that declare one of ``names``; other blocks are untouched."""
    fields: Final = object_mapping(message)
    if fields is None or fields.get("role") != "system":
        return message
    content: Final = object_list(fields.get("content"))
    kept: Final = [block for block in content if inline_tool_addition_name(block) not in names]
    if len(kept) == len(content):
        return message
    return {**fields, "content": kept}


def resolve_anthropic_tool_names(data: Mapping[str, object]) -> tuple[str, ...]:
    """Every tool name authorization must check for this request."""
    tools: Final = object_list(data.get("tools"))
    base: Final = _dedupe(chain.from_iterable(anthropic_tool_names(tool) for tool in tools))
    return _dedupe((*base, *_iter_added_names(data.get("messages"))))


def is_anthropic_messages_call(call_type: object) -> bool:
    return getattr(call_type, "value", call_type) in _ANTHROPIC_MESSAGES_CALL_TYPES


def messages_without_inline_tools(messages: object, names: Set[str]) -> object:
    """``messages`` with the inline additions of ``names`` dropped; a non-list is returned as is."""
    if not isinstance(messages, list):
        return messages
    return [strip_inline_tool_additions(message, names) for message in object_list(messages)]  # pyright: ignore[reportUnknownArgumentType]  # messages was narrowed from an untyped JSON array


def _openai_tool_from_definition(definition: Mapping[str, object]) -> ChatCompletionToolParam | None:
    name: Final = definition.get("name")
    if not isinstance(name, str) or not name:
        return None
    description: Final = definition.get("description")
    parameters: Final = object_mapping(definition.get("input_schema"))
    function: Final[ChatCompletionToolParamFunctionChunk] = ChatCompletionToolParamFunctionChunk(name=name)
    if isinstance(description, str):
        function["description"] = description
    if parameters is not None:
        function["parameters"] = dict(parameters)
    return ChatCompletionToolParam(type="function", function=function)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _named_tools(tools: Sequence[ChatCompletionToolParam]) -> Iterator[tuple[str, ChatCompletionToolParam]]:
    for tool in tools:
        for name in anthropic_tool_names(tool):
            yield name, tool


def _tool_matches_definition(tool: object, definition: Mapping[str, object]) -> bool:
    fields: Final = object_mapping(tool)
    function: Final = object_mapping(fields.get("function")) if fields is not None else None
    if function is None or function.get("name") != definition.get("name"):
        return False
    if function.get("description") != definition.get("description"):
        return False
    return _canonical(function.get("parameters")) == _canonical(definition.get("input_schema"))


def inline_guardrail_tools(
    data: Mapping[str, object], scan_only: bool
) -> tuple[tuple[ChatCompletionToolParam, ...], Mapping[str, Mapping[str, object]]]:
    """Inline declarations a guardrail must scan, keyed by their final name.

    A same-name redefinition replaces the ``tools[]`` declaration in the scan, so the
    guardrail inspects the schema the provider will actually receive.
    """
    if scan_only:
        return (), {}
    definitions: Final = {
        name: definition
        for definition in inline_tool_definitions(data)
        if isinstance(name := definition.get("name"), str) and name
    }
    tools: Final = tuple(
        tool for definition in definitions.values() if (tool := _openai_tool_from_definition(definition)) is not None
    )
    return tools, definitions


def inline_tools_denied_by_guardrail(
    guardrailed_tools: Sequence[ChatCompletionToolParam],
    inline_definitions: Mapping[str, Mapping[str, object]],
) -> frozenset[str]:
    returned: Final = dict(_named_tools(guardrailed_tools))
    return frozenset(
        name
        for name, definition in inline_definitions.items()
        if name not in returned or not _tool_matches_definition(returned[name], definition)
    )


def declared_tools_only(
    guardrailed_tools: Sequence[ChatCompletionToolParam], inline_names: frozenset[str]
) -> tuple[ChatCompletionToolParam, ...]:
    """Drop inline-declared tools a guardrail returned; they live in messages, not in tools[]."""
    return tuple(tool for tool in guardrailed_tools if not inline_names.intersection(anthropic_tool_names(tool)))


def _inline_tool_removal_name(block: object) -> str | None:
    fields: Final = object_mapping(block)
    if fields is None or fields.get("type") != "tool_removal":
        return None
    tool: Final = object_mapping(fields.get("tool"))
    return _reference_name(tool) if tool is not None and tool.get("type") == "tool_reference" else None


def withdrawn_declarations(data: Mapping[str, object], inline_names: frozenset[str]) -> tuple[object, ...]:
    """tools[] entries an inline redefinition replaces and a ``tool_removal`` withdraws.

    The guardrail scans the redefinition instead of these, and they must stay in tools[] so
    the removal still resolves; being withdrawn, the provider cannot call them.
    """
    withdrawn: Final = inline_names.intersection(
        name for block in _system_content_blocks(data.get("messages")) if (name := _inline_tool_removal_name(block))
    )
    return tuple(tool for tool in object_list(data.get("tools")) if withdrawn.intersection(anthropic_tool_names(tool)))
