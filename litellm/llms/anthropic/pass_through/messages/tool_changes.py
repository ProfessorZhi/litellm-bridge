"""Resolve mid-conversation tool changes into the tool set a request can actually use.

Authorization and tool-permission guardrails must see a tool a request adds inline,
otherwise a key restricted from that tool can still get the model to call it. The
resolver is name-only on purpose: the provider transform keeps the validating
ledger, while auth needs the same add/remove/re-add outcome without raising on
schema details it does not own.
"""

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from functools import reduce
from typing import Final

from litellm.llms.base_llm.guardrail_translation.utils import anthropic_tool_names


@dataclass(frozen=True, slots=True)
class AnthropicToolChanges:
    effective: tuple[str, ...]
    added: tuple[str, ...]
    removed: frozenset[str]


@dataclass(frozen=True, slots=True)
class _ToolChangeState:
    added: tuple[str, ...] = ()
    removed: frozenset[str] = frozenset()


def _dedupe(names: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(names))


def _definition_name(block: Mapping[str, object]) -> str | None:
    for key in ("name", "tool_name"):
        value: Final = block.get(key)
        if isinstance(value, str) and value:
            return value
    definition: Final = block.get("definition")
    if isinstance(definition, Mapping):
        for key in ("name", "tool_name"):
            value: Final = definition.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _reference_name(tool: Mapping[str, object]) -> str | None:
    for key in ("name", "tool_name"):
        value: Final = tool.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _event(role: object, block: Mapping[str, object]) -> tuple[str, str] | None:
    kind: Final = block.get("type")
    if kind == "tool_addition" and role == "system":
        tool: Final = block.get("tool")
        if not isinstance(tool, Mapping):
            return None
        name: Final = (
            _definition_name(tool)
            if tool.get("type") == "tool_definition"
            else _reference_name(tool)
            if tool.get("type") == "tool_reference"
            else None
        )
        return ("add", name) if name is not None else None
    if kind == "tool_removal" and role == "system":
        tool: Final = block.get("tool")
        if not isinstance(tool, Mapping) or tool.get("type") != "tool_reference":
            return None
        name: Final = _reference_name(tool)
        return ("remove", name) if name is not None else None
    if kind == "tool_definition":
        name: Final = _definition_name(block)
        return ("add", name) if name is not None else None
    return None


def _iter_events(messages: object) -> Iterator[tuple[str, str]]:
    if not isinstance(messages, list):
        return
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        content: Final = message.get("content")
        if not isinstance(content, list):
            continue
        role: Final = message.get("role")
        for block in content:
            if isinstance(block, Mapping):
                event: Final = _event(role, block)
                if event is not None:
                    yield event


def _apply_event(state: _ToolChangeState, event: tuple[str, str]) -> _ToolChangeState:
    kind, name = event
    if kind == "add":
        return _ToolChangeState(added=(*state.added, name), removed=state.removed - {name})
    return _ToolChangeState(added=state.added, removed=state.removed | {name})


def resolve_anthropic_tool_changes(data: Mapping[str, object]) -> AnthropicToolChanges:
    """The effective tool set after inline additions, removals and re-adds.

    Only protocol positions are read: a message's own ``content`` list. A
    ``tool_definition`` inside ``tool_use.input`` or a schema property is user data
    and is never treated as a declaration.
    """
    tools: Final = data.get("tools")
    base: Final = (
        _dedupe(name for tool in tools for name in anthropic_tool_names(tool)) if isinstance(tools, list) else ()
    )
    state: Final = reduce(_apply_event, _iter_events(data.get("messages")), _ToolChangeState())
    added: Final = _dedupe(state.added)
    effective: Final = _dedupe(name for name in (*base, *added) if name not in state.removed)
    return AnthropicToolChanges(effective=effective, added=added, removed=state.removed)
