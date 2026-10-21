# DeepSeek Anthropic Messages: `tool_removal` is an unknown variant

## Symptom

A client that changes its available tools mid-session can send a root system message whose
content is text plus one or more `tool_removal` blocks. DeepSeek's Anthropic-compatible Messages
route has no `tool_removal` variant, so its serde layer rejects the body with HTTP 422 before the
model runs:

```
messages[N].content: unknown variant `tool_removal`, expected one of `text`, ..., `tool_addition`
```

The baseline forwards the block unchanged, so a retry fails the same way.

## Fix

`litellm/llms/deepseek/messages/transformation.py` now walks root system content in message order
and keeps one effective tool set. A `tool_removal` whose `tool` is a `tool_reference` withdraws that
name from the final `tools[]` and the block itself is dropped, because DeepSeek has no wire form
for it. A later `tool_addition` by reference or by value re-offers the tool; a later definition
replaces the declaration after a withdrawal. The final `tools[]` is the set available at the end of
the conversation, which is what the provider reads for the next turn. Text, thinking, `tool_use`
and `tool_result` history are left untouched.

A tool that an earlier `tool_addition` declared and a later `tool_removal` still withdraws cannot
remain as a reference: DeepSeek resolves every `tool_addition.tool_reference` against the final
`tools[]`, where the name is deliberately absent. The transform therefore drops those historical
addition blocks, drops the system message if it becomes empty, and keeps the declaration in the
internal ledger only so the later removal still validates. Other content in the same message is
kept. This is the two-phase shape exercised by the full-length E2E.

What cannot be expressed safely is refused with a client 400 naming the position: a removal outside
a root system message's own content, a removal whose `tool` is not a `tool_reference` (including
`tool_definition`, `mcp_tool_reference` and `mcp_toolset_reference`), a removal without a name, a
removal of a name that was not declared or added earlier, and a removal inside `tools[]`. A
withdrawal only needs the name, so an unresolved name is never guessed at. A root system message
that contained only removals is dropped; if that would leave no message, the request is refused.

## Validation

- `pytest tests/test_litellm/llms/deepseek/` -> 119 passed
- `ruff check` and `ruff format --check` on the two changed files -> clean
- type-discipline count in the transformation file -> 46; this is not a whole-repo type-check pass
- Anthropic Messages pass-through suite -> 249 passed, 16 failed on both the candidate and the
  frozen baseline in the available ad-hoc venv, so the failures are environmental, not a regression
- Real A/B against `deepseek/deepseek-v4-pro`: the same synthetic request hash answers 422 on the
  frozen production image and 200 on the fixed image; ordinary text is 200 on both; the old
  `tool_definition` path still answers 200; a removal followed by a redefinition answers 200 and
  the model uses the revision-two definition; a streaming removal ends with `message_stop`
- RUN-0007 long synthetic negative test: A=422, B=400 because an old `tool_addition`
  referenced a finally removed tool. This failed Run is retained as regression evidence.
- RUN-0008 long synthetic streaming test: A=422, B=200, SSE `message_stop` (1,982,814 bytes,
  1,017 messages, 147 tools; `max_tokens=16`).
- RUN-0009 **real DeepSeek** A/B on two synthetic, original-control-aligned long fixtures:
  1,982,794 / 1,982,814 bytes, 1,017 messages, 147 tools, `stream=true`,
  `max_tokens=32000`; both A requests returned 422 at `messages[1016].content`, both B
  requests returned HTTP 200 with SSE `message_stop` / `end_turn` and no error events.
  Input is fully synthetic, not the original private request.
- RUN-0010 independent QA: functional E2E PASS, release gate HOLD (CI billing,
  two historical evidence locator SHA mismatches, records card not yet merged).
- Detailed evidence, limitations and delivery status: [PROJECT-REPORT.md](PROJECT-REPORT.md).

## Limits

- DeepSeek has no positional tool changes. The transform therefore sends one final `tools[]` for
  the whole conversation, not a per-message tool set. This is correct for the next generation and
  for history, but a removal changes the prefix and can cost a prompt cache hit
- A tool that is still withdrawn at the end has its historical `tool_addition` blocks dropped, so
  the history no longer shows the tool as declared even though the final tool set is correct. The
  full-length E2E accepted this shape
- Original archived requests were `stream=true` and `max_tokens=32000`; the latest
  full-length synthetic RUN-0009 matches those controls, but **not** the original private
  conversation bytes, exact parser column or complete historical tool-call distribution.
  LiteLLM also changes some upstream controls (Anthropic beta headers, adaptive thinking,
  output_config), which are not addressed by this provider-specific fix.
- `tool_removal` only accepts a `tool_reference` here. MCP reference kinds are refused rather than
  resolved
- The walk covers `messages[].content` and a `tool_result`'s `content`, the same positions as the
  existing inline-definition support. A `tool_removal` in the top-level `system` field is not
  converted
- A redefinition without an intervening withdrawal is still refused, matching the existing contract

## Rollback

Revert this commit. The change is stateless and confined to the DeepSeek Anthropic Messages
transform; there is no database, config or migration change. No production deployment is part of
this branch
