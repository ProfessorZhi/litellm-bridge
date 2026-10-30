"""
Tests for tool allowlist enforcement (key/team metadata.allowed_tools).

Covers:
- check_tools_allowlist: allowed, disallowed, no allowlist, non-tool routes
- extract_request_tool_names: OpenAI chat, responses, Anthropic, generate_content, MCP
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from litellm.proxy._types import ProxyErrorTypes, ProxyException, UserAPIKeyAuth
from litellm.proxy.auth.auth_checks import check_tools_allowlist
from litellm.proxy.guardrails.tool_name_extraction import (
    TOOL_CAPABLE_CALL_TYPES,
    extract_request_tool_names,
)


def _token(metadata=None, team_metadata=None):
    return UserAPIKeyAuth(
        api_key="test-key",
        user_id="user",
        team_id="team",
        org_id=None,
        models=["*"],
        metadata=metadata or {},
        team_metadata=team_metadata or {},
    )


class TestExtractRequestToolNames:
    """Test tool name extraction per API format."""

    def test_openai_chat_tools(self):
        data = {
            "tools": [
                {"type": "function", "function": {"name": "get_weather"}},
                {"type": "function", "function": {"name": "run_sql"}},
            ]
        }
        assert extract_request_tool_names("/v1/chat/completions", data) == [
            "get_weather",
            "run_sql",
        ]

    def test_openai_chat_functions_legacy(self):
        data = {"functions": [{"name": "get_weather"}, {"name": "run_sql"}]}
        assert extract_request_tool_names("/v1/chat/completions", data) == [
            "get_weather",
            "run_sql",
        ]

    def test_openai_responses_function_tools(self):
        data = {
            "tools": [
                {"type": "function", "name": "get_current_weather", "description": "x"},
            ]
        }
        assert extract_request_tool_names("/v1/responses", data) == [
            "get_current_weather"
        ]

    def test_openai_responses_mcp_tools(self):
        data = {
            "tools": [
                {"type": "mcp", "server_label": "dmcp", "server_url": "http://x"},
            ]
        }
        assert extract_request_tool_names("/v1/responses", data) == ["dmcp"]

    def test_openai_responses_custom_tools(self):
        """Custom tools become callable function tools on the Chat Completions
        bridge, so their names must be extracted for allowlist enforcement;
        otherwise a restricted key could invoke a disallowed tool by declaring
        it with type "custom" (VERIA finding on PR #32258)."""
        data = {
            "tools": [
                {"type": "custom", "name": "apply_patch", "description": "x"},
                {"type": "function", "name": "get_current_weather"},
            ]
        }
        assert extract_request_tool_names("/v1/responses", data) == [
            "apply_patch",
            "get_current_weather",
        ]

    def test_anthropic_tools(self):
        data = {"tools": [{"name": "get_weather"}, {"name": "run_sql"}]}
        assert extract_request_tool_names("/v1/messages", data) == [
            "get_weather",
            "run_sql",
        ]

    def test_anthropic_openai_format_tools_forwarded_by_bridge(self):
        data = {
            "tools": [
                {"type": "function", "function": {"name": "get_weather"}},
                {"name": "run_sql"},
                {"googleSearch": {}},
            ]
        }
        assert extract_request_tool_names("/v1/messages", data) == [
            "get_weather",
            "run_sql",
        ]

    def test_anthropic_hybrid_tool_yields_every_name(self):
        data = {
            "tools": [
                {"type": "function", "name": "decoy", "function": {"name": "blocked_fn"}},
                {"type": "function", "name": "", "function": {"name": "hidden_fn"}},
            ]
        }
        assert extract_request_tool_names("/v1/messages", data) == [
            "decoy",
            "blocked_fn",
            "hidden_fn",
        ]

    def test_generate_content_tools(self):
        data = {
            "tools": [
                {
                    "functionDeclarations": [
                        {"name": "schedule_meeting", "description": "x"},
                    ]
                },
            ]
        }
        assert extract_request_tool_names("/generate_content", data) == [
            "schedule_meeting"
        ]

    def test_mcp_call_tool_name(self):
        data = {"name": "my_tool", "arguments": {}}
        assert extract_request_tool_names("/mcp/call_tool", data) == ["my_tool"]

    def test_mcp_call_tool_mcp_tool_name(self):
        data = {"mcp_tool_name": "other_tool"}
        assert extract_request_tool_names("/mcp/call_tool", data) == ["other_tool"]

    def test_non_tool_route_returns_empty(self):
        data = {"tools": [{"type": "function", "function": {"name": "x"}}]}
        assert extract_request_tool_names("/v1/embeddings", data) == []


class TestCheckToolsAllowlist:
    """Test allowlist enforcement in auth (no DB in hot path)."""

    @pytest.mark.asyncio
    async def test_no_allowlist_passes(self):
        token = _token(metadata={}, team_metadata={})
        body = {"tools": [{"type": "function", "function": {"name": "get_weather"}}]}
        await check_tools_allowlist(
            request_body=body,
            valid_token=token,
            team_object=None,
            route="/v1/chat/completions",
        )

    @pytest.mark.asyncio
    async def test_allowed_tool_passes(self):
        token = _token(metadata={"allowed_tools": ["get_weather"]})
        body = {"tools": [{"type": "function", "function": {"name": "get_weather"}}]}
        await check_tools_allowlist(
            request_body=body,
            valid_token=token,
            team_object=None,
            route="/v1/chat/completions",
        )

    @pytest.mark.asyncio
    async def test_disallowed_tool_raises(self):
        token = _token(metadata={"allowed_tools": ["other_tool"]})
        body = {"tools": [{"type": "function", "function": {"name": "get_weather"}}]}
        with pytest.raises(ProxyException) as exc_info:
            await check_tools_allowlist(
                request_body=body,
                valid_token=token,
                team_object=None,
                route="/v1/chat/completions",
            )
        assert exc_info.value.type == ProxyErrorTypes.tool_access_denied
        assert "get_weather" in str(exc_info.value.message)

    @pytest.mark.asyncio
    async def test_disallowed_openai_format_tool_raises_on_messages_route(self):
        token = _token(metadata={"allowed_tools": ["other_tool"]})
        body = {"tools": [{"type": "function", "function": {"name": "get_weather"}}]}
        with pytest.raises(ProxyException) as exc_info:
            await check_tools_allowlist(
                request_body=body,
                valid_token=token,
                team_object=None,
                route="/v1/messages",
            )
        assert exc_info.value.type == ProxyErrorTypes.tool_access_denied
        assert "get_weather" in str(exc_info.value.message)

    @pytest.mark.asyncio
    async def test_hybrid_tool_with_decoy_name_raises_on_messages_route(self):
        token = _token(metadata={"allowed_tools": ["decoy"]})
        body = {"tools": [{"type": "function", "name": "decoy", "function": {"name": "run_sql"}}]}
        with pytest.raises(ProxyException) as exc_info:
            await check_tools_allowlist(
                request_body=body,
                valid_token=token,
                team_object=None,
                route="/v1/messages",
            )
        assert exc_info.value.type == ProxyErrorTypes.tool_access_denied
        assert "run_sql" in str(exc_info.value.message)

    @pytest.mark.asyncio
    async def test_disallowed_custom_tool_raises_on_responses_route(self):
        token = _token(metadata={"allowed_tools": ["other_tool"]})
        body = {"tools": [{"type": "custom", "name": "restricted_tool"}]}
        with pytest.raises(ProxyException) as exc_info:
            await check_tools_allowlist(
                request_body=body,
                valid_token=token,
                team_object=None,
                route="/v1/responses",
            )
        assert exc_info.value.type == ProxyErrorTypes.tool_access_denied
        assert "restricted_tool" in str(exc_info.value.message)

    @pytest.mark.asyncio
    async def test_team_allowlist_used_when_key_empty(self):
        token = _token(
            metadata={},
            team_metadata={"allowed_tools": ["get_weather"]},
        )
        body = {"tools": [{"type": "function", "function": {"name": "get_weather"}}]}
        await check_tools_allowlist(
            request_body=body,
            valid_token=token,
            team_object=None,
            route="/v1/chat/completions",
        )

    @pytest.mark.asyncio
    async def test_key_allowlist_overrides_team(self):
        token = _token(
            metadata={"allowed_tools": ["get_weather"]},
            team_metadata={"allowed_tools": ["other_tool"]},
        )
        body = {"tools": [{"type": "function", "function": {"name": "get_weather"}}]}
        await check_tools_allowlist(
            request_body=body,
            valid_token=token,
            team_object=None,
            route="/v1/chat/completions",
        )

    @pytest.mark.asyncio
    async def test_valid_token_none_skips(self):
        await check_tools_allowlist(
            request_body={"tools": [{"type": "function", "function": {"name": "x"}}]},
            valid_token=None,
            team_object=None,
            route="/v1/chat/completions",
        )

    @pytest.mark.asyncio
    async def test_no_tools_in_body_passes(self):
        token = _token(metadata={"allowed_tools": ["get_weather"]})
        await check_tools_allowlist(
            request_body={"messages": []},
            valid_token=token,
            team_object=None,
            route="/v1/chat/completions",
        )


class TestAnthropicInlineToolChanges:
    """Mid-conversation tool additions must be visible to authorization.

    A tool a request adds inline is usable by the model, so it must be checked
    against the key/team allowlist exactly like a tools[] entry. A removal is not
    subtracted: the chat-completions and Responses bridges drop the removal block
    but keep forwarding tools[], so only the additions can be trusted.
    """

    def test_inline_tool_addition_is_visible(self):
        body = {
            "tools": [{"name": "static_tool"}],
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {"type": "text", "text": "A new tool is available."},
                        {
                            "type": "tool_addition",
                            "tool": {
                                "type": "tool_definition",
                                "definition": {
                                    "name": "dynamic_tool",
                                    "input_schema": {"type": "object"},
                                },
                            },
                        },
                    ],
                }
            ],
        }
        assert extract_request_tool_names("/v1/messages", body) == [
            "static_tool",
            "dynamic_tool",
        ]

    @pytest.mark.asyncio
    async def test_inline_tool_addition_not_in_allowlist_is_denied(self):
        token = _token(metadata={"allowed_tools": ["static_tool"]})
        body = {
            "tools": [{"name": "static_tool"}],
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "tool_addition",
                            "tool": {
                                "type": "tool_definition",
                                "definition": {
                                    "name": "dynamic_tool",
                                    "input_schema": {"type": "object"},
                                },
                            },
                        }
                    ],
                }
            ],
        }
        with pytest.raises(ProxyException) as exc_info:
            await check_tools_allowlist(
                request_body=body,
                valid_token=token,
                team_object=None,
                route="/v1/messages",
            )
        assert exc_info.value.type == ProxyErrorTypes.tool_access_denied
        assert "dynamic_tool" in str(exc_info.value.message)

    def test_bare_tool_definition_is_user_data(self):
        body = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_definition",
                            "definition": {
                                "name": "bare_tool",
                                "input_schema": {"type": "object"},
                            },
                        }
                    ],
                }
            ]
        }
        assert extract_request_tool_names("/v1/messages", body) == []

    def test_bare_tool_definition_in_a_system_message_is_still_user_data(self):
        body = {
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "tool_definition",
                            "definition": {
                                "name": "bare_tool",
                                "input_schema": {"type": "object"},
                            },
                        }
                    ],
                }
            ]
        }
        assert extract_request_tool_names("/v1/messages", body) == []

    def test_tool_definition_uses_definition_name_only(self):
        body = {
            "tools": [{"name": "allowed_tool"}],
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "tool_addition",
                            "tool": {
                                "type": "tool_definition",
                                "name": "allowed_tool",
                                "definition": {
                                    "name": "secret_tool",
                                    "input_schema": {"type": "object"},
                                },
                            },
                        }
                    ],
                }
            ],
        }
        assert extract_request_tool_names("/v1/messages", body) == [
            "allowed_tool",
            "secret_tool",
        ]

    @pytest.mark.asyncio
    async def test_a_decoy_flat_name_cannot_smuggle_definition_name_past_allowlist(self):
        token = _token(metadata={"allowed_tools": ["allowed_tool"]})
        body = {
            "tools": [{"name": "allowed_tool"}],
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "tool_addition",
                            "tool": {
                                "type": "tool_definition",
                                "name": "allowed_tool",
                                "definition": {
                                    "name": "secret_tool",
                                    "input_schema": {"type": "object"},
                                },
                            },
                        }
                    ],
                }
            ],
        }
        with pytest.raises(ProxyException) as exc_info:
            await check_tools_allowlist(
                request_body=body,
                valid_token=token,
                team_object=None,
                route="/v1/messages",
            )
        assert exc_info.value.type == ProxyErrorTypes.tool_access_denied
        assert "secret_tool" in str(exc_info.value.message)

    def test_tool_reference_uses_the_wire_name_only(self):
        body = {
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "tool_addition",
                            "tool": {
                                "type": "tool_reference",
                                "name": "wire_name",
                                "tool_name": "decoy_name",
                            },
                        },
                        {
                            "type": "tool_addition",
                            "tool": {
                                "type": "tool_reference",
                                "tool_name": "legacy_only",
                            },
                        },
                    ],
                }
            ]
        }
        assert extract_request_tool_names("/v1/messages", body) == ["wire_name"]

    def test_removal_does_not_hide_a_tool_from_allowlist(self):
        body = {
            "tools": [{"name": "allowed_tool"}, {"name": "secret_tool"}],
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "tool_removal",
                            "tool": {"type": "tool_reference", "name": "secret_tool"},
                        }
                    ],
                }
            ],
        }
        assert extract_request_tool_names("/v1/messages", body) == [
            "allowed_tool",
            "secret_tool",
        ]

    @pytest.mark.asyncio
    async def test_removal_only_request_still_requires_the_removed_tool(self):
        token = _token(metadata={"allowed_tools": ["allowed_tool"]})
        body = {
            "tools": [{"name": "allowed_tool"}, {"name": "secret_tool"}],
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "tool_removal",
                            "tool": {"type": "tool_reference", "name": "secret_tool"},
                        }
                    ],
                }
            ],
        }
        with pytest.raises(ProxyException) as exc_info:
            await check_tools_allowlist(
                request_body=body,
                valid_token=token,
                team_object=None,
                route="/v1/messages",
            )
        assert exc_info.value.type == ProxyErrorTypes.tool_access_denied
        assert "secret_tool" in str(exc_info.value.message)

    def test_re_added_reference_is_visible(self):
        body = {
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "tool_addition",
                            "tool": {"type": "tool_reference", "name": "old_tool"},
                        }
                    ],
                }
            ]
        }
        assert extract_request_tool_names("/v1/messages", body) == ["old_tool"]

    def test_removed_then_re_added_is_visible(self):
        body = {
            "tools": [{"name": "old_tool"}],
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "tool_removal",
                            "tool": {"type": "tool_reference", "name": "old_tool"},
                        },
                        {
                            "type": "tool_addition",
                            "tool": {"type": "tool_reference", "name": "old_tool"},
                        },
                    ],
                }
            ],
        }
        assert extract_request_tool_names("/v1/messages", body) == ["old_tool"]

    def test_tool_definition_inside_tool_use_input_is_user_data(self):
        body = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_01",
                            "name": "caller",
                            "input": {
                                "type": "tool_definition",
                                "name": "hidden_tool",
                            },
                        }
                    ],
                }
            ]
        }
        assert extract_request_tool_names("/v1/messages", body) == []
