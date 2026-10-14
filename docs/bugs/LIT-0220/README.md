# DeepSeek Anthropic Messages: an inline `tool_definition` block is refused by the provider

## Symptom

A client surfacing a deferred tool mid-session can inline the declaration as a `tool_definition` block instead of
listing the tool in `tools[]`. DeepSeek's Anthropic-compatible Messages route has no such content variant, so the
provider rejects the body at its wire-format layer; the baseline forwards it unchanged and a retry fails the same way:

```
messages[N].content: unknown variant `tool_definition`, expected `tool_reference`
```

## Fix

`litellm/llms/deepseek/messages/transformation.py` adds a downgrade step that runs only on this route. It converts
the documented mid-conversation shape, a `tool_addition` whose `tool` is `{type: "tool_definition", definition:
{...}}`: the `definition` is hoisted into `tools[]` once and the `tool` becomes `{type: "tool_reference", name:
...}`, leaving the wrapper, the message and the block order where they were. A request with nothing to convert keeps
its message content and order unmodified.

What it cannot convert safely it refuses with a client 400 naming the position: a `tool_definition` outside a
`tool_addition`; a `tool_addition` outside a root system message's own `content`; a declaration whose `definition` is
missing, unnamed, gives a non-object `input_schema`, or names a server tool `type`; a conflicting redeclaration; a
content block in `tools[]`; a non-list `tools`; and nesting past the walk depth.

## Validation

`pytest tests/test_litellm/llms/deepseek/` -> 93 passed; the Anthropic messages pass-through suite -> 265 passed;
`ruff check` and `git diff --check` -> clean.

Against the real provider through a proxy: the canonical inline body answers 422 before the change and 200 after it,
returning a real `get_weather` call whose `tool_use_id` and full assistant content, thinking included, round-trip as
a `tool_result` and are consumed at 200; the same turn streams over SSE with the correct aggregated tool name,
arguments and `stop_reason`. Seven other illegal bodies come back 400 from the transform.

## Limits

* Only the canonical shape converts. A flat or differently nested declaration, or a server tool type, is refused,
  and a declaration inlined in another block's `content` field is forwarded untouched to the provider's own rejection.
* The 400s are this transform's contract for bodies it will not convert; a `tools` value that is not a list fails
  earlier in the HTTP router, on the baseline image too, a separate defect left unfixed.
* Dynamic redefinition, `defer_loading` and prompt-cache equivalence are not promised: a `tools[]` entry has no
  position, so a mid-conversation redefinition cannot be expressed.
* The originating report is not reproduced from a real client, which used the provider successfully but never
  emitted an inline block, so the refusals rest on direct probes against the live provider.
* Repo-wide `scripts/type_check_gate.py` was not run, so the repository type and Python CI budgets are unmeasured.
  Nothing is merged or deployed.

## Reference

* Anthropic tool use: https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview
* DeepSeek Anthropic API: https://api-docs.deepseek.com/guides/anthropic_api
