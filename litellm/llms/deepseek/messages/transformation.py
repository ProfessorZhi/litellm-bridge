"""
DeepSeek Anthropic-compatible messages transformation config.
"""

from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass, field
from typing import Any, Final, NoReturn

import litellm
from litellm.litellm_core_utils.litellm_logging import verbose_logger
from litellm.llms.anthropic.pass_through.messages.transformation import (
    AnthropicMessagesConfig,
)
from litellm.secret_managers.main import get_secret_str
from litellm.types.router import GenericLiteLLMParams

INLINE_TOOL_DEFINITION_BLOCK: Final = "tool_definition"
TOOL_ADDITION_BLOCK: Final = "tool_addition"
TOOL_REMOVAL_BLOCK: Final = "tool_removal"
TOOL_REFERENCE_BLOCK: Final = "tool_reference"
TOOL_RESULT_BLOCK: Final = "tool_result"

# A `tools[]` entry is a declaration, so a content-block discriminator never belongs in it.
PROTOCOL_BLOCK_TYPES: Final = (INLINE_TOOL_DEFINITION_BLOCK, TOOL_ADDITION_BLOCK, TOOL_REMOVAL_BLOCK)

# How deep the block walk descends before it refuses. Bounded so a body nested past this is
# reported as uninspectable rather than walked until Python's own stack ends.
_MAX_PROTOCOL_DEPTH: Final = 8

# Returned by the walk for a block that has no provider wire form and was folded into state.
_DROP: Final = object()


@dataclass(slots=True)
class _ToolLedger:
    index: dict[str, Any]
    withdrawn: frozenset[str] = frozenset()
    hoisted: dict[str, Any] = field(default_factory=dict)
    removed: set[str] = field(default_factory=set)

    @classmethod
    def over(cls, tools: Sequence[Any], withdrawn: frozenset[str] = frozenset()) -> "_ToolLedger":
        return cls(
            index={
                tool["name"]: tool
                for tool in tools
                if isinstance(tool, Mapping) and isinstance(tool.get("name"), str) and tool["name"]
            },
            withdrawn=withdrawn,
        )


def _refuse(model: str, reason: str) -> NoReturn:
    """Every refusal from this transform is one and the same client error contract."""
    raise litellm.BadRequestError(message=reason, model=model, llm_provider="deepseek")


class DeepSeekAnthropicMessagesConfig(AnthropicMessagesConfig):
    """
    DeepSeek exposes an Anthropic-compatible Messages API at
    https://api.deepseek.com/anthropic.

    It accepts the native Anthropic Messages conversation shape, including
    thinking blocks in assistant history, but rejects Anthropic's explicit
    custom-tool discriminator (`{"type": "custom"}`).
    """

    @property
    def custom_llm_provider(self) -> str | None:
        return "deepseek"

    def should_strip_billing_metadata(self) -> bool:
        return True

    @staticmethod
    def get_api_key(api_key: str | None = None) -> str | None:
        return api_key or get_secret_str("DEEPSEEK_API_KEY") or litellm.api_key

    @staticmethod
    def get_api_base(api_base: str | None = None) -> str:
        return (
            api_base
            or get_secret_str("DEEPSEEK_ANTHROPIC_API_BASE")
            or get_secret_str("DEEPSEEK_API_BASE")
            or "https://api.deepseek.com/anthropic"
        )

    def validate_anthropic_messages_environment(
        self,
        headers: dict,
        model: str,
        messages: list[Any],
        optional_params: dict,
        litellm_params: dict,
        api_key: str | None = None,
        api_base: str | None = None,
    ) -> tuple[dict, str | None]:
        dynamic_api_key: Final = self.get_api_key(api_key=api_key)

        if "x-api-key" not in headers and "authorization" not in headers and dynamic_api_key is not None:
            headers["x-api-key"] = dynamic_api_key

        if "anthropic-version" not in headers:
            headers["anthropic-version"] = "2023-06-01"
        if "content-type" not in headers:
            headers["content-type"] = "application/json"

        headers = self._update_headers_with_anthropic_beta(
            headers=headers,
            optional_params=optional_params,
            custom_llm_provider=self.custom_llm_provider or "deepseek",
            messages=messages,
        )

        return headers, api_base

    def get_complete_url(
        self,
        api_base: str | None,
        api_key: str | None,
        model: str,
        optional_params: dict,
        litellm_params: dict,
        stream: bool | None = None,
    ) -> str:
        base_url = self.get_api_base(api_base=api_base).rstrip("/")

        if base_url.endswith("/v1/messages") and "/anthropic/" in base_url:
            return base_url
        base_url = base_url.removesuffix("/v1/messages")
        base_url = base_url.removesuffix("/v1")
        base_url = base_url.removesuffix("/beta")

        if not base_url.endswith("/anthropic") and "/anthropic/" not in base_url:
            base_url = f"{base_url}/anthropic"

        return f"{base_url}/v1/messages"

    @staticmethod
    def _sanitize_tools_for_deepseek(tools: Any) -> object:
        if not isinstance(tools, list):
            return tools

        sanitized_tools: Final = []
        for tool in tools:
            if isinstance(tool, dict) and tool.get("type") == "custom":
                sanitized_tool = dict(tool)
                sanitized_tool.pop("type", None)
                sanitized_tools.append(sanitized_tool)
            else:
                sanitized_tools.append(tool)
        return sanitized_tools

    @staticmethod
    def _replace(node: Mapping[str, Any], key: str, value: Any) -> Mapping[str, Any]:
        """Copy-on-write: a subtree that did not change keeps the identity it arrived with."""
        return node if node[key] is value else {**node, key: value}

    @staticmethod
    def _tools_or_raise(tools: Any, model: str) -> None:
        """Reject a ``tools`` value that is neither absent nor a list of declarations.

        Checked before ``super()`` too: the parent walks ``tools`` for the advisor tool type,
        so a non-iterable one raises there first.
        """
        if tools is None or isinstance(tools, list):
            return
        _refuse(
            model,
            f"DeepSeek /v1/messages expects tools to be a list of declarations, received {type(tools).__name__}.",
        )

    @staticmethod
    def _contract(declaration: Mapping[str, Any]) -> dict[str, Any]:
        """The part of a declaration that says which tool it is.

        `cache_control` is a cache hint, not the tool. Anthropic's `custom` discriminator and no
        discriminator at all both mean an ordinary client tool; a versioned server tool type is
        what that tool is.
        """
        contract: Final = {key: value for key, value in declaration.items() if key != "cache_control"}
        if contract.get("type") == "custom":
            contract.pop("type")
        return contract

    @classmethod
    def _reference_for(
        cls,
        tool: Mapping[str, Any],
        path: str,
        model: str,
        ledger: _ToolLedger,
    ) -> Mapping[str, Any]:
        """Hoist this declaration into ``tools[]`` and return the reference that stands for it.

        Fields are copied rather than rebuilt from a whitelist, so a hoist cannot drop one.
        """
        definition: Final = tool.get("definition")
        if not isinstance(definition, Mapping):
            _refuse(
                model,
                "DeepSeek /v1/messages cannot convert %s: a tool_definition carries the tool under a "
                "'definition' object, and this one does not. Refusing rather than guessing at its fields." % path,
            )
        declared_type: Final = definition.get("type")
        if declared_type is not None and declared_type != "custom":
            _refuse(
                model,
                "DeepSeek /v1/messages cannot convert %s: this transform converts client tools, and the "
                "inline definition carries type '%s'. A server tool belongs in tools[] under its own type. "
                "Refusing rather than hoisting it as an ordinary client tool." % (path, declared_type),
            )
        name: Final = definition.get("name")
        if not isinstance(name, str) or not name:
            _refuse(
                model,
                "DeepSeek /v1/messages cannot convert %s: 'definition.name' is not a non-empty string, so "
                "the reference this declaration becomes could not name anything." % path,
            )
        declaration: Final = dict(definition)
        if not isinstance(declaration.get("input_schema"), dict):
            _refuse(
                model,
                "DeepSeek /v1/messages cannot convert %s: 'definition.input_schema' is not an object, and "
                "this compatibility transform requires an object input_schema. Refusing rather than "
                "narrowing the tool." % path,
            )
        existing: Final = ledger.index.get(name)
        if existing is None:
            ledger.hoisted[name] = declaration
            ledger.index[name] = declaration
        elif name in ledger.removed:
            # A withdrawal has a position; the redefinition that follows it can replace the entry
            # because the final tools[] is the set that is available at the end of the conversation.
            ledger.hoisted[name] = declaration
            ledger.index[name] = declaration
        elif cls._contract(existing) != cls._contract(declaration):
            _refuse(
                model,
                "DeepSeek /v1/messages found two declarations of '%s' that do not describe the same tool, "
                "the block at %s and the one already in tools[]. Anthropic lets a client redefine a tool "
                "mid-conversation, but a redefinition has a position and one tools[] entry does not, so "
                "this transform cannot express both. Refusing rather than picking one." % (name, path),
            )
        ledger.removed.discard(name)
        return {"type": TOOL_REFERENCE_BLOCK, "name": name}

    @classmethod
    def _rewrite_nodes(
        cls,
        node: object,
        path: str,
        depth: int,
        model: str,
        ledger: _ToolLedger,
        *,
        declares: bool,
    ) -> object:
        """Rewrite a copy of this subtree, converting the declaration it is allowed to carry.

        Two positions are walked: a root message's own ``content`` list, where ``declares`` says
        whether the provider reads a ``tool_addition``, and a ``tool_result``'s ``content``. A
        ``content`` field on any other block, and a ``role`` field below the message it belongs to,
        is user data and is left exactly as it arrived.
        """
        if isinstance(node, list):
            if depth > _MAX_PROTOCOL_DEPTH:
                _refuse(
                    model,
                    "DeepSeek /v1/messages cannot inspect %s: it is nested deeper than the %d levels this "
                    "transform walks, so an illegal tool_definition could be hiding there. Refusing rather "
                    "than forwarding a block that may be illegal downstream." % (path, _MAX_PROTOCOL_DEPTH),
                )
            rewritten: Final = [
                cls._rewrite_nodes(v, f"{path}[{i}]", depth, model, ledger, declares=declares)
                for i, v in enumerate(node)
            ]
            if not any(value is _DROP for value in rewritten):
                return node if all(old is new for old, new in zip(node, rewritten)) else rewritten
            return [value for value in rewritten if value is not _DROP]  # mutable-ok: message content is a JSON array
        if not isinstance(node, Mapping):
            return node
        kind: Final = node.get("type")
        if kind == INLINE_TOOL_DEFINITION_BLOCK:
            _refuse(
                model,
                "DeepSeek /v1/messages cannot convert the tool_definition at %s: the provider reads a "
                "declaration only under a tool_addition, and refuses a reference at this position as well. "
                "Refusing rather than forwarding a block that cannot reach the model." % path,
            )
        if kind == TOOL_REMOVAL_BLOCK:
            return cls._withdraw(node, path, model, ledger, declares=declares)
        if kind == TOOL_ADDITION_BLOCK:
            if not declares:
                _refuse(
                    model,
                    "DeepSeek /v1/messages cannot convert the tool_addition at %s: only a root system "
                    "message's own content declares a tool. Refusing rather than forwarding it." % path,
                )
            tool: Final = node.get("tool")
            if isinstance(tool, Mapping) and tool.get("type") == INLINE_TOOL_DEFINITION_BLOCK:
                reference: Final = cls._reference_for(tool, path + ".tool", model, ledger)
                if reference.get("name") in ledger.withdrawn:
                    return _DROP
                return cls._replace(node, "tool", reference)
            if isinstance(tool, Mapping) and tool.get("type") == TOOL_REFERENCE_BLOCK:
                reference_name: Final = tool.get("name")
                if isinstance(reference_name, str) and reference_name in ledger.withdrawn:
                    return _DROP
                return cls._re_added(node, tool, ledger.removed)
            _refuse(
                model,
                "DeepSeek /v1/messages cannot convert the tool_addition at %s: its 'tool' is neither a "
                "tool_definition nor a tool_reference. Refusing rather than forwarding an illegal block." % path,
            )
        if kind == TOOL_RESULT_BLOCK:
            content: Final = node.get("content")
            if isinstance(content, list):
                return cls._replace(
                    node,
                    "content",
                    cls._rewrite_nodes(content, path + ".content", depth + 1, model, ledger, declares=False),
                )
        return node

    @staticmethod
    def _withdraw(node: Mapping[str, Any], path: str, model: str, ledger: _ToolLedger, *, declares: bool) -> object:
        if not declares:
            _refuse(
                model,
                f"DeepSeek /v1/messages cannot convert the tool_removal at {path}: only a root system "
                "message's own content withdraws a tool. Refusing rather than forwarding it.",
            )
        removal_tool: Final = node.get("tool")
        if not (isinstance(removal_tool, Mapping) and removal_tool.get("type") == TOOL_REFERENCE_BLOCK):
            _refuse(
                model,
                f"DeepSeek /v1/messages cannot convert the tool_removal at {path}: its 'tool' must be a "
                "tool_reference. A withdrawal names a tool; it does not carry a definition, and this "
                "transform cannot resolve an MCP reference to a name. Refusing rather than guessing.",
            )
        name: Final = removal_tool.get("name")
        if not isinstance(name, str) or not name:
            _refuse(
                model,
                f"DeepSeek /v1/messages cannot convert the tool_removal at {path}: 'tool.name' is not a "
                "non-empty string, so the withdrawal names nothing.",
            )
        if name not in ledger.index:
            _refuse(
                model,
                f"DeepSeek /v1/messages cannot convert the tool_removal at {path}: '{name}' is not declared in "
                "tools[] or added earlier in this request. Refusing rather than forwarding an "
                "unresolved withdrawal.",
            )
        ledger.removed.add(name)
        return _DROP

    @staticmethod
    def _re_added(node: Mapping[str, Any], tool: Mapping[str, Any], removed: set[str]) -> Mapping[str, Any]:
        """A reference re-offers the tool it names, undoing an earlier withdrawal of that name."""
        name: Final = tool.get("name")
        if isinstance(name, str) and name:
            removed.discard(name)
        return node

    @staticmethod
    def _tool_name(tool: object) -> str | None:
        if isinstance(tool, Mapping):
            name: Final = tool.get("name")
            if isinstance(name, str) and name:
                return name
        return None

    @classmethod
    def _is_removed(cls, tool: object, removed: Set[str]) -> bool:
        name: Final = cls._tool_name(tool)
        return isinstance(name, str) and name in removed

    @classmethod
    def _kept_tool(cls, tool: object, hoisted: Mapping[str, object]) -> object:
        name: Final = cls._tool_name(tool)
        return hoisted[name] if isinstance(name, str) and name in hoisted else tool

    @classmethod
    def _rewrite_message(
        cls,
        message: object,
        position: int,
        model: str,
        ledger: _ToolLedger,
    ) -> object | None:
        if not isinstance(message, Mapping):
            return message
        content: Final = message.get("content")
        if not isinstance(content, list):
            return message
        rewritten: Final = cls._rewrite_nodes(
            content,
            f"messages[{position}].content",
            0,
            model,
            ledger,
            declares=message.get("role") == "system",
        )
        if content and isinstance(rewritten, list) and not rewritten:
            return None
        return cls._replace(message, "content", rewritten)

    @classmethod
    def _final_tools(
        cls,
        tools: Sequence[Any],
        ledger: _ToolLedger,
    ) -> list[object]:  # mutable-ok: tools[] is a JSON array on the wire
        original_names: Final = frozenset(name for tool in tools if (name := cls._tool_name(tool)) is not None)
        kept_originals: Final = [
            cls._kept_tool(tool, ledger.hoisted) for tool in tools if not cls._is_removed(tool, ledger.removed)
        ]
        appended: Final = [
            declaration
            for name, declaration in ledger.hoisted.items()
            if name not in original_names and name not in ledger.removed
        ]
        return [*kept_originals, *appended]  # mutable-ok: tools[] is a JSON array on the wire

    @classmethod
    def _downgrade_inline_tool_definitions(
        cls, messages: list[dict], tools: list[Any], model: str = "deepseek"
    ) -> tuple[list[object], list[object]]:
        """Move inline tool definitions into tools[] and reference them by name.

        DeepSeek accepts ``tool_reference`` but has no ``tool_definition`` variant, so an inlined
        definition reaches it as a 422 the client cannot act on. A block that cannot be converted
        safely is refused rather than dropped without a word.
        """
        cls._tools_or_raise(tools, model)
        misplaced: Final = next(
            (
                i
                for i, tool in enumerate(tools)
                if isinstance(tool, Mapping) and tool.get("type") in PROTOCOL_BLOCK_TYPES
            ),
            None,
        )
        if misplaced is not None:
            _refuse(
                model,
                "DeepSeek /v1/messages cannot forward the content block at tools[%d]: tools[] is a "
                "declaration container. Refusing rather than sending an illegal block downstream." % misplaced,
            )
        # First pass: the final set of names still withdrawn. Additions for these names cannot
        # stay as references, because the provider resolves every reference against the final
        # tools[], where the name is deliberately absent.
        analysis: Final = _ToolLedger.over(tools)
        for i, message in enumerate(messages):
            cls._rewrite_message(message, i, model, analysis)

        # Second pass: rewrite for the provider, dropping the historical additions of names that
        # are still withdrawn at the end while keeping the ledger that validates every removal.
        ledger: Final = _ToolLedger.over(tools, frozenset(analysis.removed))
        converted: Final = [
            rewritten
            for i, message in enumerate(messages)
            if (rewritten := cls._rewrite_message(message, i, model, ledger)) is not None
        ]
        if messages and not converted:
            _refuse(
                model,
                "DeepSeek /v1/messages cannot forward a request whose messages were all tool_removal "
                "blocks: no message would remain. Refusing rather than sending an empty conversation.",
            )
        if ledger.hoisted or ledger.removed:
            verbose_logger.debug(
                "DeepSeek /v1/messages: converted inline tool_definition blocks to tool_reference and "
                "applied tool_removal withdrawals, hoisting %d declaration(s) and withdrawing %d name(s).",
                len(ledger.hoisted),
                len(ledger.removed),
            )
        return converted, cls._final_tools(tools, ledger)

    @classmethod
    def _rewrite_deepseek_tool_blocks(cls, request: dict, model: str) -> dict:
        """One DeepSeek wire conversion shared by native DeepSeek and opt-in Anthropic routing."""
        converted_messages, converted_tools = cls._downgrade_inline_tool_definitions(
            request["messages"], request.get("tools") or [], model
        )
        request["messages"] = converted_messages
        if converted_tools or "tools" in request:
            request["tools"] = cls._sanitize_tools_for_deepseek(converted_tools)
        return request

    def transform_anthropic_messages_request(
        self,
        model: str,
        messages: list[dict],
        anthropic_messages_optional_request_params: dict,
        litellm_params: GenericLiteLLMParams,
        headers: dict,
    ) -> dict:
        self._tools_or_raise(anthropic_messages_optional_request_params.get("tools"), model)
        anthropic_messages_request: Final = super().transform_anthropic_messages_request(
            model=model,
            messages=messages,
            anthropic_messages_optional_request_params=anthropic_messages_optional_request_params,
            litellm_params=litellm_params,
            headers=headers,
        )
        return self._rewrite_deepseek_tool_blocks(anthropic_messages_request, model)


class DeepSeekCompatAnthropicMessagesConfig(AnthropicMessagesConfig):
    """Use DeepSeek's tool-block wire compatibility without changing Anthropic routing or auth."""

    def transform_anthropic_messages_request(
        self,
        model: str,
        messages: list[dict],
        anthropic_messages_optional_request_params: dict,
        litellm_params: GenericLiteLLMParams,
        headers: dict,
    ) -> dict:
        request: Final = super().transform_anthropic_messages_request(
            model=model,
            messages=messages,
            anthropic_messages_optional_request_params=anthropic_messages_optional_request_params,
            litellm_params=litellm_params,
            headers=headers,
        )
        return DeepSeekAnthropicMessagesConfig._rewrite_deepseek_tool_blocks(request, model)
