# CI failure attribution for PR #23

Run: https://github.com/ProfessorZhi/litellm-bridge/actions/runs/40987394359

The base branch had no unit-test run before this PR head enabled the unit workflow
for `update/106-dev`. The failures below are therefore first observed here, but
none of them is in a file or behavior changed by this PR. The jobs that exercise
the changed areas pass: `llms-anthropic`, `guardrails-hooks`, `guardrails-tests`,
and `auth-checks`.

| Job | First observed failure | Category | Relation to this diff |
|---|---|---|---|
| docs | `tests/documentation_tests/test_env_keys.py` reports three undocumented environment variables | historical baseline / docs drift | no docs or env-var source changed |
| core-utils | `test_fallback_generalizations`, `test_get_model_cost_map`, `test_tool_call_cost_tracking`, then realtime streaming tests time out; job hits its 20 minute limit | baseline model/cost data plus timeout | no core-utils, cost-map, or realtime file changed |
| endpoints | OpenAPI response status enum mismatch (`queued` versus `requires_continuation`) and a realtime voice guardrail test hits the 120 second timeout | baseline contract plus timeout | no endpoints or realtime file changed |
| llms-vertex-ai | `test_vertex_realtime_text_in_text_out` hits the 120 second timeout | timeout / flaky | no Vertex file changed |
| proxy-auth | `test_over_first_window_raises` and `test_over_second_window_raises` assert `402 == 422` | historical budget contract | no auth or budget file changed |
| proxy-infra-root | tag-budget tests assert `'402' == '422'` | historical budget contract | no proxy request-processing file changed |
| responses-caching-types | WebSocket failure frames assert `500 == 400` | historical WebSocket contract | no responses or caching file changed |
| root | `pyproject.toml` version `1.106.2` is not an `X.Y.0` release; 42 `.disabled` files are present in the workflow directory; Bedrock and Claude model-info assertions fail | historical repository hygiene and model data | none of those files is changed |
| router-unit-tests | `test_router_prompt_caching_same_cacheable_prefix_routes_to_same_deployment` hits the 120 second timeout | timeout / flaky | no router file changed |

## Conclusion

No CI failure points at the five runtime files or four test files changed here. The
failures are baseline repository state, external model/docs data, or timeout/flaky
behavior. The PR does not delete tests, skip tests, or weaken assertions to hide
them. The unit workflow enablement for the base branch is what makes the baseline
visible; whether to accept that CI debt or split it into a separate change is a
merge decision, not a code change in this PR.

The PR stays Draft while the baseline CI question, the independent security review,
and the production-version diff check remain open.
