"""Resolve the tool names a request can make the provider act on.

Authorization must see every tool a request declares, including one added inline in a
system message. A mid-conversation ``tool_removal`` is not subtracted: the
chat-completions and Responses bridges drop the removal block but still forward
``tools[]``, so trusting the removal would hide a tool the provider can still call.
A removal-only request therefore still has to satisfy the allowlist.
"""

from collections.abc import Iterable, Iterator, Mapping
from itertools import chain
from typing import Final

from pydantic import TypeAdapter, ValidationError

from litellm.llms.base_llm.guardrail_translation.utils import anthropic_tool_names

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


def strip_inline_tool_additions(message: object, names: frozenset[str]) -> object:
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
