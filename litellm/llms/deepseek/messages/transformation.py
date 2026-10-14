"""
DeepSeek Anthropic-compatible messages transformation config.
"""

from collections.abc import Mapping
from typing import Any, Final, NoReturn

import litellm
from litellm.litellm_core_utils.litellm_logging import verbose_logger
from litellm.llms.anthropic.experimental_pass_through.messages.transformation import (
    AnthropicMessagesConfig,
)
from litellm.secret_managers.main import get_secret_str
from litellm.types.router import GenericLiteLLMParams

INLINE_TOOL_DEFINITION_BLOCK: Final = "tool_definition"
TOOL_ADDITION_BLOCK: Final = "tool_addition"
TOOL_REFERENCE_BLOCK: Final = "tool_reference"

# A `tools[]` entry is a declaration, so a content-block discriminator never belongs in it.
PROTOCOL_BLOCK_TYPES: Final = (INLINE_TOOL_DEFINITION_BLOCK, TOOL_ADDITION_BLOCK)

# How deep the block walk descends before it refuses. Bounded so a body nested past this is
# reported as uninspectable rather than walked until Python's own stack ends.
_MAX_PROTOCOL_DEPTH: Final = 8


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
    def _sanitize_tools_for_deepseek(tools: Any) -> Any:
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
            "DeepSeek /v1/messages expects tools to be a list of declarations, received %s."
            % type(tools).__name__,
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
        index: dict[str, Any],
        hoisted: list[Any],
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
                "DeepSeek takes no boolean or omitted schema. Refusing rather than narrowing the tool." % path,
            )
        existing: Final = index.get(name)
        if existing is None:
            hoisted.append(declaration)
            index[name] = declaration
        elif cls._contract(existing) != cls._contract(declaration):
            _refuse(
                model,
                "DeepSeek /v1/messages found two declarations of '%s' that do not describe the same tool, "
                "the block at %s and the one already in tools[]. Anthropic lets a client redefine a tool "
                "mid-conversation, but a redefinition has a position and one tools[] entry does not, so "
                "this transform cannot express both. Refusing rather than picking one." % (name, path),
            )
        return {"type": TOOL_REFERENCE_BLOCK, "name": name}

    @classmethod
    def _rewrite_nodes(
        cls,
        node: Any,
        path: str,
        depth: int,
        model: str,
        index: dict[str, Any],
        hoisted: list[Any],
    ) -> Any:
        """Rewrite a copy of this subtree, converting every declaration it carries.

        Only the positions the provider reads as content blocks are walked, and only
        ``tool_addition.tool`` can declare a tool. A ``tool_definition`` anywhere else is refused
        rather than forwarded: the provider rejects the block there, and it rejects the reference it
        would become there too, so there is no conversion to invent for it.
        """
        if depth > _MAX_PROTOCOL_DEPTH:
            _refuse(
                model,
                "DeepSeek /v1/messages cannot inspect %s: it is nested deeper than the %d levels this "
                "transform walks, so an illegal tool_definition could be hiding there. Refusing rather "
                "than forwarding a block that may be illegal downstream." % (path, _MAX_PROTOCOL_DEPTH),
            )
        if isinstance(node, list):
            rewritten: Final = [
                cls._rewrite_nodes(v, "%s[%d]" % (path, i), depth, model, index, hoisted)
                for i, v in enumerate(node)
            ]
            return node if all(old is new for old, new in zip(node, rewritten)) else rewritten
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
        if kind == TOOL_ADDITION_BLOCK:
            tool: Final = node.get("tool")
            if isinstance(tool, Mapping) and tool.get("type") == INLINE_TOOL_DEFINITION_BLOCK:
                return cls._replace(node, "tool", cls._reference_for(tool, path + ".tool", model, index, hoisted))
            if isinstance(tool, Mapping) and tool.get("type") == TOOL_REFERENCE_BLOCK:
                return node
            _refuse(
                model,
                "DeepSeek /v1/messages cannot convert the tool_addition at %s: its 'tool' is neither a "
                "tool_definition nor a tool_reference. Refusing rather than forwarding an illegal block." % path,
            )
        content: Final = node.get("content")
        if isinstance(content, list):
            converted: Final = cls._rewrite_nodes(content, path + ".content", depth + 1, model, index, hoisted)
            return cls._replace(node, "content", converted)
        return node

    @classmethod
    def _downgrade_inline_tool_definitions(
        cls, messages: list[dict], tools: list[Any], model: str = "deepseek"
    ) -> tuple[list[dict], list[Any]]:
        """Move inline tool definitions into tools[] and reference them by name.

        DeepSeek accepts ``tool_reference`` but has no ``tool_definition`` variant, so an inlined
        definition reaches it as a 422 the client cannot act on. A block that cannot be converted
        safely is refused rather than dropped without a word.
        """
        cls._tools_or_raise(tools, model)
        misplaced: Final = next(
            (
                i for i, tool in enumerate(tools)
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
        # one index over the declarations already in tools[] and every one hoisted from here on
        index: Final[dict[str, Any]] = {
            tool["name"]: tool
            for tool in tools
            if isinstance(tool, Mapping) and isinstance(tool.get("name"), str) and tool["name"]
        }
        hoisted: Final[list[Any]] = []
        converted: Final[list[dict]] = cls._rewrite_nodes(messages, "messages", 0, model, index, hoisted)
        if hoisted:
            verbose_logger.debug(
                "DeepSeek /v1/messages: converted inline tool_definition blocks to tool_reference, "
                "hoisting %d declaration(s) into tools[].",
                len(hoisted),
            )
        return converted, [*tools, *hoisted]

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
        converted_messages, converted_tools = self._downgrade_inline_tool_definitions(
            anthropic_messages_request["messages"],
            anthropic_messages_request.get("tools") or [],
            model,
        )
        anthropic_messages_request["messages"] = converted_messages
        if converted_tools or "tools" in anthropic_messages_request:
            anthropic_messages_request["tools"] = self._sanitize_tools_for_deepseek(converted_tools)
        return anthropic_messages_request
