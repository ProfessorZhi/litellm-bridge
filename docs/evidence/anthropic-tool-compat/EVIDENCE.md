# Real upstream A/B evidence · Anthropic Messages tool compatibility

Runtime under test: `825c92e0bf9499c72c8f56e878de0a8341779589`

Run time: `2026-10-30T11:32:43+08:00`

Image: `litellm:v1.106.2-fix-all-4170175b1a`
(`sha256:5cc2514c984445f0fe0413af1d56eba7971bca5236e65a66d270dfde4f0707a2`)

## Method

The run used one isolated proxy and one isolated Postgres. No production database,
deployment, or gateway was touched. Two DB deployments were created through the
proxy in the isolated database:

- `v4pro-compat`: upstream `anthropic/deepseek-flash` at
  `https://api.deepseek.com/anthropic`, with
  `model_info.anthropic_messages_compatibility=deepseek`
- `v4pro-plain`: the same upstream and endpoint without the opt-in marker

The same request body was sent to both deployments. The body carries `tools[]`
with a withdrawn tool and a referenced tool, plus inline `tool_addition` with
`tool_definition`, `tool_addition` with `tool_reference`, and `tool_removal`.

The run also exercised `POST /v1/messages?beta=true`, a streaming request, and a
restricted virtual key with `allowed_tools` against inline definition, inline
reference, and removal requests.

The transform replay reads the captured compat request and runs the real
`DeepSeekAnthropicMessagesConfig.rewrite_deepseek_tool_blocks` without network.
It records the before and after protocol under `evidence/wire/`.

## Results

| Case | Result |
|---|---|
| Direct official upstream probe | 200 |
| Compat deployment, inline tools | 200 |
| Plain control, same body | 422 |
| Plain error names `unknown variant 'tool_definition'` and `expected 'tool_reference'` | PASS |
| Compat deployment, `?beta=true` | 200 |
| Plain control, `?beta=true` | 422 |
| Compat streaming | 200, SSE reached `message_stop` |
| Restricted key, inline definition | 403 |
| Restricted key, inline reference | 403 |
| Restricted key, removal | 403 |
| DB deployments visible through `/model/info` | PASS |
| Compat DB deployment carries the opt-in marker | PASS |
| Transform drops `tool_definition` from the wire | PASS |
| Transform uses `tool_reference` on the wire | PASS |
| Wire final tools keep `dynamic_tool` and `existing_tool`, drop `old_tool` | PASS |
| Credential-shaped values in the evidence | none |

Assertion summary: `evidence/assertions.json`
Human summary: `evidence/summary.md`

Paid model calls: 4 (direct probe, compat, compat beta, compat stream). The plain
control and the ACL requests fail before inference. No retry loop was used.

## Security and privacy

- The request and response headers are stored with the authorization value
  redacted; no API key, cookie, or session value is present.
- The model-creation requests store `os.environ/DEEPSEEK_API_KEY`, not a key.
- `evidence/assertions.json` includes a scan for the runtime key value and for
  credential-shaped strings; it reports none.
- No user content, production data, or production credential was read or written.

## Caveats

- The official Anthropic-compatible model used here is `deepseek-flash` behind the
  client-facing DB aliases `v4pro-compat` and `v4pro-plain`. This mirrors the
  production deployment shape, but it is not a byte-for-byte copy of the production
  server. A production version and local-patch diff is still required before any
  release decision.
- The A/B/C guardrail boundary fixes have RED and GREEN tests in the unit suite
  (8 failed before the fix, 51 passed after the focused run). The full
  Anthropic-plus-guardrails run is `7471 passed, 6 skipped, 1 xfailed`; that run is evidence of
  regression coverage, not a substitute for an independent security review.
- The independent review after the A/B/C fixes is still pending. The PR remains
  Draft.
- CI baseline failures are attributed in `CI-ATTRIBUTION.md`; they are not claimed
  as fixed by this evidence.

## Reproduction

```bash
export LIT0226_REAL_WORKTREE="<repository root>"
export LIT0226_REAL_EVIDENCE="<empty evidence directory>"
export DEEPSEEK_ENV_FILE="<authorized test environment file>"
export PYTHON="<python with the repository dependencies>"
bash docs/evidence/anthropic-tool-compat/run_live_e2e.sh
```

The script starts an isolated Postgres and proxy, creates the two DB deployments,
runs the A/B, beta, stream, and ACL cases, writes the sanitized evidence, and
tears the containers down. It requires an authorized test key and must not be run
against production.
