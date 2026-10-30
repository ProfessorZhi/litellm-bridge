# Real DeepSeek Anthropic-compatible A/B evidence

All requests used an isolated proxy and an isolated Postgres; no production database or deployment was touched.
The upstream is the official DeepSeek Anthropic-compatible endpoint.

| Case | HTTP | Assertion |
|---|---:|---|
| direct-upstream-200 | HTTP 200 | PASS |
| compat-inline-tools-200 | HTTP 200 | PASS |
| plain-non-opt-in-422 | HTTP 422 | PASS |
| plain-error-is-tool-definition-discriminator | upstream 422 names the tool_definition discriminator | PASS |
| compat-beta-200 | HTTP 200 | PASS |
| plain-beta-422 | HTTP 422 | PASS |
| compat-stream-200 | HTTP 200 | PASS |
| compat-stream-message-stop | SSE reached message_stop | PASS |
| acl-inline-definition-403 | HTTP 403 | PASS |
| acl-inline-reference-403 | HTTP 403 | PASS |
| acl-removal-403 | HTTP 403 | PASS |
| db-deployments-present | isolated DB deployments are visible through /model/info | PASS |
| db-deployment-opt-in-marker | the compat DB deployment carries the opt-in marker | PASS |
| wire-drops-tool-definition | wire body has no tool_definition block | PASS |
| wire-uses-tool-reference | wire body uses tool_reference | PASS |
| wire-final-tools | after_tools=['existing_tool', 'dynamic_tool'] | PASS |
| no-credential-shaped-values | leaked=[] | PASS |

Paid model calls: 4 (direct probe, compat, compat beta, compat stream).
The plain control and the ACL requests are expected to fail before inference.

Failures: 0
