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
TOOL_REFERENCE_BLOCK: Final = "tool_reference"


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

    @staticmethod
    def _has_comparable_schema(existing: Any) -> bool:
        return isinstance(existing, Mapping) and isinstance(existing.get("input_schema"), dict)

    @staticmethod
    def _tools_or_raise(tools: Any, model: str) -> None:
        """Reject a ``tools`` value that is neither absent nor a list of declarations.

        Checked before ``super()`` as well: the parent walks ``tools`` to look for
        the advisor tool type, so a non-iterable one raises there first.
        """
        if tools is None or isinstance(tools, list):
            return
        _refuse(
            model,
            "DeepSeek /v1/messages expects tools to be a list of declarations, received %s. Refusing "
            "rather than reinterpreting or forwarding a malformed declaration container."
            % type(tools).__name__,
        )

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

    # Only these positions can carry a content block. Anything else that happens
    # to contain a "type": "tool_definition" pair is user data (e.g. inside
    # `tool_use.input` or a JSON Schema property), which the provider never
    # parses as a block — so it is neither scanned nor rejected.
    _PROTOCOL_WRAPPER_TYPES: Final = ("tool_result", "tool_addition")
    _MAX_PROTOCOL_DEPTH: Final = 8
    _DEPTH_LIMIT_MARKER: Final = "!depth-limit!"

    @classmethod
    def _scan_protocol_blocks(cls, node: Any, path: str, depth: int, out: list) -> None:
        """Walk only protocol block positions, collecting illegal `tool_definition`s.

        A full recursive walk of the request body would be both slower (it runs on
        the hot path of every request, inline block or not) and *wrong*: it would
        reject legal user content that merely contains the string ``tool_definition``
        — a schema property name, a ``tool_use.input`` value, a tool result payload.
        So we follow only the three positions where the provider expects a content
        block: ``messages[].content[]``, a ``tool_result``'s nested ``content[]``,
        and a ``tool_addition``'s ``tool``. Depth is bounded.
        """
        if depth > cls._MAX_PROTOCOL_DEPTH:
            # fail closed: "not inspected" must never read as "nothing illegal here"
            out.append(cls._DEPTH_LIMIT_MARKER + path)
            return
        if isinstance(node, list):
            for i, value in enumerate(node):
                cls._scan_protocol_blocks(value, "%s[%d]" % (path, i), depth, out)
            return
        if not isinstance(node, Mapping):
            return
        if node.get("type") == INLINE_TOOL_DEFINITION_BLOCK:
            out.append(path)
            return
        # a message envelope: messages[i] -> content[]
        if "role" in node and isinstance(node.get("content"), list):
            cls._scan_protocol_blocks(node["content"], path + ".content", depth + 1, out)
        if node.get("type") in cls._PROTOCOL_WRAPPER_TYPES:
            if isinstance(node.get("content"), list):
                cls._scan_protocol_blocks(node["content"], path + ".content", depth + 1, out)
            if isinstance(node.get("tool"), Mapping):
                cls._scan_protocol_blocks(node["tool"], path + ".tool", depth + 1, out)

    @classmethod
    def _find_tool_definitions(cls, messages: Any, path: str = "messages", out=None):
        """Illegal `tool_definition` blocks, and uninspectable nesting, left in protocol positions."""
        if out is None:
            out = []
        cls._scan_protocol_blocks(messages, path, 0, out)
        return out

    @classmethod
    def _refuse_leftover(cls, leftover: list, model: str) -> None:
        """Refuse a body that still holds, or could not be fully inspected for, an illegal block."""
        first: Final = leftover[0]
        if isinstance(first, str) and first.startswith(cls._DEPTH_LIMIT_MARKER):
            _refuse(
                model,
                "DeepSeek /v1/messages cannot inspect the block nesting at %s: it is deeper than the %d "
                "levels this transform walks, so an illegal tool_definition may be hiding there. Refusing "
                "rather than forwarding a block that may be illegal downstream."
                % (first[len(cls._DEPTH_LIMIT_MARKER):], cls._MAX_PROTOCOL_DEPTH),
            )
        _refuse(
            model,
            "DeepSeek /v1/messages cannot convert the tool_definition block at %s: this nesting is not a "
            "shape this transform can hoist losslessly, and forwarding it would send an illegal block "
            "downstream. Refusing rather than dropping it silently." % first,
        )

    @classmethod
    def _invalid_tool_declarations(cls, tools: Any) -> list:
        """Reject ``tools[]`` entries that are protocol blocks, not declarations.

        A ``tools[]`` entry is a *declaration container*: it is identified by its
        own ``type`` field. We look at that field only and never walk the entry's
        ``input_schema`` — a property or description that happens to contain the
        text ``tool_definition`` is legal user data and must not be rejected.
        """
        bad: Final = []
        if not isinstance(tools, list):
            return bad
        for i, tool in enumerate(tools):
            if isinstance(tool, Mapping) and tool.get("type") in (
                INLINE_TOOL_DEFINITION_BLOCK,
                "tool_addition",
            ):
                bad.append("tools[%d]" % i)
        return bad

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
        cls._tools_or_raise(tools, model)
        bad_declarations: Final = cls._invalid_tool_declarations(tools)
        if bad_declarations:
            _refuse(
                model,
                "DeepSeek /v1/messages cannot forward the entry at %s: tools[] is a declaration "
                "container, and a content block (tool_definition/tool_addition) is not a valid "
                "declaration there. Refusing rather than sending an illegal block downstream."
                % bad_declarations[0],
            )

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
                cls._refuse_leftover(leftover0, model)
            return messages, tools

        declared: Final = {
            tool["name"]: tool for tool in tools if isinstance(tool, Mapping) and isinstance(tool.get("name"), str)
        }
        hoisted: Final = []
        for mi, ci, block in located:
            where: Final = f"messages[{mi}].content[{ci}]"
            tool_name: Final = cls._inline_name_of(block)
            if tool_name is None:
                _refuse(
                    model,
                    f"DeepSeek /v1/messages cannot convert the tool_definition block at {where}: "
                    "no resolvable tool name ('tool_name' or 'name' expected). Refusing to drop it silently.",
                )
            declaration: Final = cls._inline_declaration_of(block, tool_name)
            if tool_name in declared:
                existing: Final = declared[tool_name]
                if declaration is not None and cls._declarations_conflict(existing, declaration):
                    _refuse(
                        model,
                        f"DeepSeek /v1/messages found conflicting tool_definition declarations for "
                        f"'{tool_name}' at {where}. Refusing to guess which schema to use.",
                    )
                if declaration is not None and not cls._has_comparable_schema(existing):
                    _refuse(
                        model,
                        f"DeepSeek /v1/messages cannot reconcile the tool_definition for '{tool_name}' at "
                        f"{where}: tools[] already declares that name without a usable input_schema, and "
                        "the inline definition carries one. Refusing rather than discarding the inline "
                        "schema silently.",
                    )
                continue
            if declaration is None:
                _refuse(
                    model,
                    f"DeepSeek /v1/messages cannot convert the tool_definition block for '{tool_name}' at "
                    f"{where}: it carries no valid 'input_schema' to declare and the tool is not already in "
                    "tools[]. Refusing to drop it silently.",
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
            cls._refuse_leftover(leftover, model)
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
        self._tools_or_raise(anthropic_messages_optional_request_params.get("tools"), model)
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
