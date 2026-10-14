"""
DeepSeek Anthropic-compatible messages transformation config.
"""

from collections.abc import Mapping
from dataclasses import dataclass
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

# A `tools[]` entry is a declaration, so a content-block discriminator never belongs in
# it. These are the two block types this transform converts, and either of them sitting
# in the declarations array is a block in the wrong place: the 422 this fix exists for.
PROTOCOL_BLOCK_TYPES: Final = (INLINE_TOOL_DEFINITION_BLOCK, TOOL_ADDITION_BLOCK)

# Declaration fields that are transport directives rather than part of the tool's
# contract: `type` is Anthropic's custom-tool discriminator, which this transform strips
# before sending, and `cache_control` only tells the provider how to cache the prefix.
# Two declarations of one name that agree on everything else describe the same tool and
# may be deduplicated; any other difference is a conflict not worth guessing at.
_DECLARATION_ANNOTATIONS: Final = frozenset(("type", "cache_control"))


def _refuse(model: str, reason: str) -> NoReturn:
    """Every refusal from this transform is one and the same client error contract."""
    raise litellm.BadRequestError(message=reason, model=model, llm_provider="deepseek")


@dataclass(frozen=True, slots=True)
class _InlineDeclaration:
    """A content block that declares a tool inline, resolved exactly once."""

    # the `tool_addition` wrapper to keep in place for the official form, None when the
    # definition block sits directly in `content[]`
    wrapper: Mapping[str, Any] | None
    name: str | None
    # the `tools[]` entry to hoist, or None when the block carries no schema to declare
    declaration: dict[str, Any] | None

    def reference(self, name: str) -> dict[str, Any]:
        """The block that replaces this position, pointing at the hoisted declaration.

        The name key mirrors the dialect that carried the definition: the official
        `tool_reference` uses `name`, the flat shape uses `tool_name`.
        """
        if self.wrapper is not None:
            return {**self.wrapper, "tool": {"type": TOOL_REFERENCE_BLOCK, "name": name}}
        return {"type": TOOL_REFERENCE_BLOCK, "tool_name": name}


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
    def _tool_name_of(body: Mapping[str, Any]) -> str | None:
        """The declared tool's name, in either spelling.

        `name` is the field Anthropic's own `tool_definition` and `tool_reference` blocks
        use, and the one the client's accessor reads, so it wins over the flat shape's
        `tool_name` when a block carries both.
        """
        for key in ("name", "tool_name"):
            value = body.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    @staticmethod
    def _tool_declaration(body: Mapping[str, Any], tool_name: str | None) -> dict[str, Any] | None:
        """The `tools[]` entry this block declares, or None when it cannot declare one.

        The wrapper key `definition` is never carried into `tools[]`, and every other
        field is copied rather than rebuilt from a whitelist, so a hoist cannot quietly
        drop one. DeepSeek's Anthropic layer validates `input_schema` as a JSON Schema
        object: a block without one has nothing to declare, and a reference to it would
        point at a tool the provider does not have.
        """
        if tool_name is None:
            return None
        declaration: Final = {
            key: value for key, value in body.items() if key not in ("type", "tool_name", "definition")
        }
        if not isinstance(declaration.get("input_schema"), dict):
            return None
        return {**declaration, "name": tool_name}

    @classmethod
    def _normalize_inline(cls, part: Any) -> _InlineDeclaration | None:
        """Resolve a content block that declares a tool inline, or None for any other block.

        Both accepted shapes converge here. The official mid-conversation form is a
        `tool_addition` wrapping a `tool_definition`, whose wrapper stays in place so only
        its `tool` has to be replaced; a `tool_definition` sitting directly in `content[]`
        is replaced whole. The declaration fields are read from one place in each, the
        sub-definition when there is one and the block itself otherwise, which is what
        keeps the two shapes interchangeable.
        """
        if not isinstance(part, Mapping):
            return None
        block: Final[Mapping[str, Any]]
        wrapper: Final[Mapping[str, Any] | None]
        if part.get("type") == INLINE_TOOL_DEFINITION_BLOCK:
            wrapper, block = None, part
        elif part.get("type") == TOOL_ADDITION_BLOCK:
            tool: Final = part.get("tool")
            if not (isinstance(tool, Mapping) and tool.get("type") == INLINE_TOOL_DEFINITION_BLOCK):
                return None
            wrapper, block = part, tool
        else:
            return None
        definition: Final = block.get("definition")
        body: Final = definition if isinstance(definition, Mapping) else block
        tool_name: Final = cls._tool_name_of(body)
        return _InlineDeclaration(
            wrapper=wrapper, name=tool_name, declaration=cls._tool_declaration(body, tool_name)
        )

    @staticmethod
    def _declaration_contract(declaration: Mapping[str, Any]) -> dict[str, Any]:
        """The part of a declaration that says which tool it is."""
        return {
            key: value for key, value in declaration.items() if key not in _DECLARATION_ANNOTATIONS
        }

    @classmethod
    def _declarations_differ(cls, existing: Mapping[str, Any], candidate: Mapping[str, Any]) -> bool:
        return cls._declaration_contract(existing) != cls._declaration_contract(candidate)

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

    # Only these positions can carry a content block. Anything else that happens
    # to contain a "type": "tool_definition" pair is user data (e.g. inside
    # `tool_use.input` or a JSON Schema property), which the provider never
    # parses as a block — so it is neither scanned nor rejected.
    _PROTOCOL_WRAPPER_TYPES: Final = ("tool_result", "tool_addition")
    _MAX_PROTOCOL_DEPTH: Final = 8
    _DEPTH_LIMIT_MARKER: Final = "!depth-limit!"

    @classmethod
    def _scan_protocol_blocks(cls, node: Any, path: str, depth: int, out: list[str]) -> None:
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
    def _find_tool_definitions(cls, messages: Any) -> list[str]:
        """Illegal `tool_definition` blocks, and uninspectable nesting, left in protocol positions."""
        out: Final[list[str]] = []
        cls._scan_protocol_blocks(messages, "messages", 0, out)
        return out

    @classmethod
    def _refuse_leftover(cls, leftover: list[str], model: str) -> None:
        """Refuse a body that still holds, or could not be fully inspected for, an illegal block."""
        first: Final = leftover[0]
        if first.startswith(cls._DEPTH_LIMIT_MARKER):
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
    def _first_invalid_declaration(cls, tools: Any) -> str | None:
        """The first ``tools[]`` entry that is a protocol block rather than a declaration.

        A declaration is identified by its own ``type`` field, and we look at that field
        only: the entry's ``input_schema`` is never walked, so a property or description
        that happens to contain the text ``tool_definition`` is legal user data.
        """
        if not isinstance(tools, list):
            return None
        for i, tool in enumerate(tools):
            if isinstance(tool, Mapping) and tool.get("type") in PROTOCOL_BLOCK_TYPES:
                return "tools[%d]" % i
        return None

    @classmethod
    def _downgrade_inline_tool_definitions(
        cls, messages: list[dict], tools: list[Any], model: str = "deepseek"
    ) -> tuple[list[dict], list[Any]]:
        """Move inline tool definitions into tools[] and reference them by name.

        DeepSeek's Anthropic layer accepts ``tool_reference`` but has no
        ``tool_definition`` variant, so a client that inlines a deferred tool's
        definition in messages[] gets a 422 it cannot act on.

        Fail-closed: a block that cannot be *safely* converted (no resolvable name,
        no object ``input_schema`` to declare, or a declaration of a name that
        tools[] already declares differently) raises a client ``BadRequestError``
        instead of being dropped silently. No content block and no message is ever
        discarded without a word, and nothing the provider would reject is forwarded.
        """
        cls._tools_or_raise(tools, model)
        bad_declaration: Final = cls._first_invalid_declaration(tools)
        if bad_declaration is not None:
            _refuse(
                model,
                "DeepSeek /v1/messages cannot forward the entry at %s: tools[] is a declaration "
                "container, and a content block (tool_definition/tool_addition) is not a valid "
                "declaration there. Refusing rather than sending an illegal block downstream."
                % bad_declaration,
            )

        # every convertible position is resolved here, once, and the rewrite below reads
        # those records rather than re-parsing the same block a second time
        inline: Final[dict[tuple[int, int], _InlineDeclaration]] = {}
        for mi, message in enumerate(messages):
            content: Final = message.get("content") if isinstance(message, Mapping) else None
            if not isinstance(content, list):
                continue
            for ci, part in enumerate(content):
                resolved: Final = cls._normalize_inline(part)
                if resolved is not None:
                    inline[(mi, ci)] = resolved

        if not inline:
            # no convertible top-level shape, but a tool_definition may still be
            # hiding deeper (e.g. inside tool_result.content[]); never forward it
            unconverted: Final = cls._find_tool_definitions(messages)
            if unconverted:
                cls._refuse_leftover(unconverted, model)
            return messages, tools

        declared: Final[dict[str, Mapping[str, Any]]] = {
            tool["name"]: tool
            for tool in tools
            if isinstance(tool, Mapping) and isinstance(tool.get("name"), str)
        }
        hoisted: Final[list[Any]] = []
        references: Final[dict[tuple[int, int], dict[str, Any]]] = {}
        for (mi, ci), block in inline.items():
            where: Final = f"messages[{mi}].content[{ci}]"
            tool_name: Final = block.name
            if tool_name is None:
                _refuse(
                    model,
                    f"DeepSeek /v1/messages cannot convert the tool_definition block at {where}: "
                    "no resolvable tool name ('name' or 'tool_name' expected). Refusing to drop it silently.",
                )
            references[(mi, ci)] = block.reference(tool_name)
            existing: Final = declared.get(tool_name)
            if existing is not None:
                if block.declaration is not None and cls._declarations_differ(existing, block.declaration):
                    _refuse(
                        model,
                        f"DeepSeek /v1/messages found conflicting declarations for the tool '{tool_name}' "
                        f"at {where}: tools[] already declares that name, and the two do not describe the "
                        "same tool. Refusing to guess which declaration the model should see.",
                    )
                continue
            if block.declaration is None:
                _refuse(
                    model,
                    f"DeepSeek /v1/messages cannot convert the tool_definition block for '{tool_name}' at "
                    f"{where}: it carries no valid 'input_schema' to declare and the tool is not already in "
                    "tools[]. Refusing to drop it silently.",
                )
            hoisted.append(block.declaration)
            declared[tool_name] = block.declaration

        downgraded: Final[list[dict]] = []
        for mi, message in enumerate(messages):
            content: Final = message.get("content") if isinstance(message, Mapping) else None
            if not isinstance(content, list):
                downgraded.append(message)
                continue
            downgraded.append(
                {
                    **message,
                    "content": [
                        references[(mi, ci)] if (mi, ci) in references else part
                        for ci, part in enumerate(content)
                    ],
                }
            )

        leftover: Final = cls._find_tool_definitions(downgraded)
        if leftover:
            cls._refuse_leftover(leftover, model)
        verbose_logger.debug(
            "DeepSeek /v1/messages: downgraded %s inline tool_definition block(s) to tool_reference, "
            "hoisted %s declaration(s) into tools[].",
            len(inline),
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
        converted_messages, converted_tools = self._downgrade_inline_tool_definitions(
            anthropic_messages_request["messages"],
            anthropic_messages_request.get("tools") or [],
            model,
        )
        anthropic_messages_request["messages"] = converted_messages
        if converted_tools or "tools" in anthropic_messages_request:
            anthropic_messages_request["tools"] = self._sanitize_tools_for_deepseek(converted_tools)
        return anthropic_messages_request
