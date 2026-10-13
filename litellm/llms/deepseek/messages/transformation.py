"""
DeepSeek Anthropic-compatible messages transformation config.
"""

from collections.abc import Mapping
from typing import Any, Final

import litellm
from litellm.litellm_core_utils.litellm_logging import verbose_logger
from litellm.llms.anthropic.experimental_pass_through.messages.transformation import (
    AnthropicMessagesConfig,
)
from litellm.secret_managers.main import get_secret_str
from litellm.types.router import GenericLiteLLMParams

INLINE_TOOL_DEFINITION_BLOCK: Final = "tool_definition"
TOOL_REFERENCE_BLOCK: Final = "tool_reference"


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
    def _inline_tool_name(block: Mapping[str, Any]) -> str | None:
        """Resolve the tool name from either the flat or the nested block shape.

        Claude Code 2.1.296 emits ``{type: "tool_definition", definition: {name, ...}}``
        (the binary accessor reads ``e.definition.name``), while the synthetic flat
        fixtures carry ``name``/``tool_name`` at the top level. Both are accepted.
        """
        for key in ("tool_name", "name"):
            value = block.get(key)
            if isinstance(value, str) and value:
                return value
        definition = block.get("definition")
        if isinstance(definition, Mapping):
            for key in ("name", "tool_name"):
                value = definition.get(key)
                if isinstance(value, str) and value:
                    return value
        return None

    @classmethod
    def _inline_tool_declaration(cls, block: Mapping[str, Any], tool_name: str) -> dict[str, Any] | None:
        """Build the ``tools[]`` entry from the block.

        For the nested shape the **sub-definition** is used and the wrapper key
        ``definition`` is never carried into ``tools[]``.
        """
        definition = block.get("definition")
        source: Final = definition if isinstance(definition, Mapping) else block
        declaration: Final = {
            key: value for key, value in source.items() if key not in ("type", "tool_name", "definition")
        }
        declaration["name"] = tool_name
        if not isinstance(declaration.get("input_schema"), dict):
            return None
        return declaration

    @staticmethod
    def _declarations_conflict(existing: Any, candidate: Mapping[str, Any]) -> bool:
        if not isinstance(existing, Mapping):
            return False
        a = existing.get("input_schema")
        b = candidate.get("input_schema")
        return isinstance(a, dict) and isinstance(b, dict) and a != b

    # ---- official mid-conversation system-message form -----------------------
    # {"role":"system","content":[{"type":"tool_addition",
    #    "tool":{"type":"tool_definition","definition":{name,description,input_schema}}}]}
    # must become the same message with the inner tool referenced by name, and the
    # definition hoisted into tools[]. The outer `tool_addition` stays in place.
    @staticmethod
    def _official_tool_addition(part: Any) -> Mapping[str, Any] | None:
        if isinstance(part, Mapping) and part.get("type") == "tool_addition":
            tool = part.get("tool")
            if isinstance(tool, Mapping) and tool.get("type") == INLINE_TOOL_DEFINITION_BLOCK:
                return tool
        return None

    @classmethod
    def _is_inline_definition(cls, part: Any) -> bool:
        return (isinstance(part, Mapping)
                and (part.get("type") == INLINE_TOOL_DEFINITION_BLOCK
                     or cls._official_tool_addition(part) is not None))

    @classmethod
    def _inline_name_of(cls, part: Mapping[str, Any]) -> str | None:
        tool = cls._official_tool_addition(part)
        if tool is not None:
            definition = tool.get("definition")
            if isinstance(definition, Mapping):
                for key in ("name", "tool_name"):
                    v = definition.get(key)
                    if isinstance(v, str) and v:
                        return v
            return cls._inline_tool_name(tool)
        return cls._inline_tool_name(part)

    @classmethod
    def _inline_declaration_of(cls, part: Mapping[str, Any], tool_name: str):
        tool = cls._official_tool_addition(part)
        if tool is not None:
            definition = tool.get("definition")
            if not isinstance(definition, Mapping):
                return None
            return cls._inline_tool_declaration(definition, tool_name)
        return cls._inline_tool_declaration(part, tool_name)

    @classmethod
    def _to_reference(cls, part: Mapping[str, Any], tool_name: str) -> dict:
        if cls._official_tool_addition(part) is not None:
            return {**part, "tool": {"type": TOOL_REFERENCE_BLOCK, "name": tool_name}}
        return {"type": TOOL_REFERENCE_BLOCK, "tool_name": tool_name}

    @staticmethod
    def _find_tool_definitions(node: Any, path: str = "", out=None):
        """Recursively locate any remaining `tool_definition` block, with its path.

        Used as a final guard: after the supported shapes have been converted, any
        `tool_definition` still present (e.g. nested inside ``tool_result.content[]``
        or under a double ``tool_addition``) must NOT be forwarded to the provider —
        that would be an unhandled illegal block. We fail closed with a client 400
        that names the exact path instead, so nothing is dropped silently and the
        provider never sees a shape we did not understand.
        """
        if out is None:
            out = []
        if isinstance(node, Mapping):
            if node.get("type") == INLINE_TOOL_DEFINITION_BLOCK:
                out.append(path or "$")
            for key, value in node.items():
                if key in ("tools",):
                    continue
                DeepSeekAnthropicMessagesConfig._find_tool_definitions(
                    value, "%s.%s" % (path, key), out)
        elif isinstance(node, list):
            for i, value in enumerate(node):
                DeepSeekAnthropicMessagesConfig._find_tool_definitions(
                    value, "%s[%d]" % (path, i), out)
        return out

    @classmethod
    def _downgrade_inline_tool_definitions(
        cls, messages: list[dict], tools: list[Any], model: str = "deepseek"
    ) -> tuple[list[dict], list[Any]]:
        """Move inline tool definitions into tools[] and reference them by name.

        DeepSeek's Anthropic layer accepts ``tool_reference`` but has no
        ``tool_definition`` variant, so a client that inlines a deferred tool's
        definition inline in messages[] gets a 422 it cannot act on.

        Fail-closed: a block that cannot be *safely* converted (no resolvable
        name, no valid ``input_schema`` to declare, or a conflicting duplicate
        declaration) raises a client ``BadRequestError`` instead of being
        silently dropped. No content block and no message is ever discarded
        silently.
        """
        located: Final = [
            (mi, ci, part)
            for mi, message in enumerate(messages)
            if isinstance(message, Mapping) and isinstance(message.get("content"), list)
            for ci, part in enumerate(message["content"])
            if cls._is_inline_definition(part)
        ]
        if not located:
            # no convertible top-level shape, but a tool_definition may still be
            # hiding deeper (e.g. inside tool_result.content[]); never forward it.
            leftover0: Final = cls._find_tool_definitions(messages, "messages")
            if leftover0:
                raise litellm.BadRequestError(
                    message=(
                        "DeepSeek /v1/messages cannot convert the tool_definition block at %s: this "
                        "nesting is not a shape this transform can hoist losslessly, and forwarding it "
                        "would send an illegal block downstream. Refusing rather than dropping it "
                        "silently." % leftover0[0]
                    ),
                    model=model,
                    llm_provider="deepseek",
                )
            return messages, tools

        declared: Final = {
            tool["name"]: tool for tool in tools if isinstance(tool, Mapping) and isinstance(tool.get("name"), str)
        }
        hoisted: Final = []
        for mi, ci, block in located:
            where: Final = f"messages[{mi}].content[{ci}]"
            tool_name: Final = cls._inline_name_of(block)
            if tool_name is None:
                raise litellm.BadRequestError(
                    message=(
                        f"DeepSeek /v1/messages cannot convert the tool_definition block at {where}: "
                        "no resolvable tool name ('tool_name' or 'name' expected). Refusing to drop it silently."
                    ),
                    model=model,
                    llm_provider="deepseek",
                )
            declaration: Final = cls._inline_declaration_of(block, tool_name)
            if tool_name in declared:
                if declaration is not None and cls._declarations_conflict(declared[tool_name], declaration):
                    raise litellm.BadRequestError(
                        message=(
                            f"DeepSeek /v1/messages found conflicting tool_definition declarations for "
                            f"'{tool_name}' at {where}. Refusing to guess which schema to use."
                        ),
                        model=model,
                        llm_provider="deepseek",
                    )
                continue
            if declaration is None:
                raise litellm.BadRequestError(
                    message=(
                        f"DeepSeek /v1/messages cannot convert the tool_definition block for '{tool_name}' at "
                        f"{where}: it carries no valid 'input_schema' to declare and the tool is not already in "
                        "tools[]. Refusing to drop it silently."
                    ),
                    model=model,
                    llm_provider="deepseek",
                )
            hoisted.append(declaration)
            declared[tool_name] = declaration

        downgraded: Final = []
        for message in messages:
            content: Final = message.get("content") if isinstance(message, Mapping) else None
            if not isinstance(content, list):
                downgraded.append(message)
                continue
            kept: Final = []
            for part in content:
                if not cls._is_inline_definition(part):
                    kept.append(part)
                    continue
                tool_name: Final = cls._inline_name_of(part)  # validated non-None above
                kept.append(cls._to_reference(part, tool_name))
            downgraded.append({**message, "content": kept})

        leftover: Final = cls._find_tool_definitions(downgraded, "messages")
        if leftover:
            raise litellm.BadRequestError(
                message=(
                    "DeepSeek /v1/messages cannot convert the tool_definition block at %s: this nesting "
                    "is not a shape this transform can hoist losslessly, and forwarding it would send an "
                    "illegal block downstream. Refusing rather than dropping it silently." % leftover[0]
                ),
                model=model,
                llm_provider="deepseek",
            )
        verbose_logger.debug(
            "DeepSeek /v1/messages: downgraded %s inline tool_definition block(s) to tool_reference, "
            "hoisted %s declaration(s) into tools[].",
            len(located),
            len(hoisted),
        )
        return downgraded, [*tools, *hoisted]

    def transform_anthropic_messages_request(
        self,
        model: str,
        messages: list[dict],
        anthropic_messages_optional_request_params: dict,
        litellm_params: GenericLiteLLMParams,
        headers: dict,
    ) -> dict:
        anthropic_messages_request: Final = super().transform_anthropic_messages_request(
            model=model,
            messages=messages,
            anthropic_messages_optional_request_params=anthropic_messages_optional_request_params,
            litellm_params=litellm_params,
            headers=headers,
        )
        messages, tools = self._downgrade_inline_tool_definitions(
            anthropic_messages_request["messages"],
            anthropic_messages_request.get("tools") or [],
            model,
        )
        anthropic_messages_request["messages"] = messages
        if tools or "tools" in anthropic_messages_request:
            anthropic_messages_request["tools"] = self._sanitize_tools_for_deepseek(tools)
        return anthropic_messages_request
