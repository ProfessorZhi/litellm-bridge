# Test commands and results

## Focused RED and GREEN

The RED run reverted only the three runtime hunks from the fix commit, ran the
same selection, and restored them. The new tests failed before the fix and passed
after it.

```bash
python -m pytest \
  tests/unit/llms/anthropic/chat/guardrail_translation/test_anthropic_guardrail_handler.py::TestAnthropicMessagesHandlerInputProcessing \
  tests/unit/proxy/guardrails/guardrail_hooks/test_tool_permission.py::TestAnthropicInlineToolPermission \
  -q
```

- Before the fix: 8 failed
- After the fix: 51 passed

The RED selection covered a request with only an inline tool and no scannable
text, the same-name removal-then-redefinition schema, the guardrail drop and
rewrite fail-closed paths, and Chat/Responses system content preservation.

## Targeted regression

```bash
python -m pytest \
  tests/unit/llms/deepseek/messages/test_deepseek_anthropic_messages_transformation.py \
  tests/unit/llms/anthropic/chat/guardrail_translation \
  tests/unit/llms/anthropic/pass_through \
  tests/unit/proxy/test_tools_allowlist_enforcement.py \
  tests/unit/proxy/guardrails/guardrail_hooks/test_tool_permission.py \
  -q
```

- 1443 passed

## Full Anthropic and guardrails regression

```bash
python -m pytest tests/unit/llms/anthropic tests/unit/proxy/guardrails -q
```

- `7471 passed, 6 skipped, 1 xfailed`

## Machine-wide check

```bash
BASE_REF=origin/update/106-dev make check
```

- PASS

## Real upstream A/B

See `run_live_e2e.sh` and `EVIDENCE.md`. The run used four paid model calls and
no retry loop; all 17 assertions passed. The raw response bodies, redacted
headers, SSE stream, transform before/after, service log, and checksums are under
`evidence/`.
