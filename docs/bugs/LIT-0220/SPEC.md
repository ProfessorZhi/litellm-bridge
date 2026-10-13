# LIT-0220 — Claude Code inline tool_definition → DeepSeek Anthropic 422

Status: **IN PROGRESS (isolated research; no production change)**  
Owner: Vince (Tokyo Ubuntu / `vince`)  
Opened: 2026-10-13  
Baseline: LiteLLM `86e98cb8c1` (deployed gateway anchor), separate worktree `fix/lit-0220-deepseek-inline-tools-422`

## 1. Problem and impact

Claude Code 2.1.286+ may inline previously surfaced deferred MCP tools after an SDK process restart. A subsequent Anthropic Messages request contains a `tool_definition` block within `messages[].content`. DeepSeek's Anthropic-compatible endpoint refuses it with 422, reporting `unknown variant 'tool_definition', expected 'tool_reference'`. Claude Code 2.1.296 allegedly matches only Anthropic's `Input tag 'tool_definition'` phrasing for its inline-tool fallback and does not downgrade on DeepSeek's error phrasing. Repeated requests can strand a session. These causal details are **Yale's reported hypothesis** until independently reproduced.

Reference issue: https://github.com/deepseek-ai/DeepSeek-V3/issues/1701 (open as of 2026-10-13).
Adjacent LiteLLM: https://github.com/BerriAI/litellm/pull/45297, https://github.com/BerriAI/litellm/pull/45439 (header fixes, not a proven DeepSeek fix).
Adjacent LiteLLM ToolSearch/Responses: https://github.com/BerriAI/litellm/issues/36540 and https://github.com/BerriAI/litellm/pull/36557.

## 2. Evidence already obtained (do not confuse with this item's reproduction)

- Tokyo **shared** gateway `litellm-shared-litellm` (owned/managed under `ubuntu`, **do not modify**) logged relevant errors at 2026-10-13 05:20:51.648 and 05:20:52.247 UTC. Runtime LiteLLM 1.100.0, model group `v4.1flash`, downstream `deepseek`.
- Beijing FJ production (separate asset, **outside scope**) had 12 SpendLogs 422 occurrences with target error vocabulary: 2026-10-08 (2), 10-09 (4), 10-12 (6), route `deepseek-v4-pro-anthropic`; no persistent raw request body recovered. This is prior read-only evidence, NOT permission for any further production access.
- Yale's source text is privately retained under the per-Item Tokyo local evidence folder (no production credentials or raw internal session identifiers are committed to Git).

## 3. Hypotheses requiring separate experiments

H1 — Downstream: a *synthetic*, minimal Anthropic Messages request containing `tool_definition` receives the 422 above at the official DeepSeek endpoint. Distinguish direct provider refusal from proxy behavior.

H2 — Proxy: stock LiteLLM in the pinned baseline forwards rather than transforms the unsupported content in this particular route; identify the exact /v1/messages path and whether the request is passed through vs Anthropic-to-chat conversion.

H3 — Client: after ToolSearch surfaces deferred tools, a Claude Code 2.1.296 SDK process restart generates inline-tool definitions on the first resumed turn; **do not resume or write to Yale's original transcript**. Tokyo `vince` CLI is 2.1.272, so a second isolated 2.1.296 binary is needed for this lane.

H4 — Recovery: Claude Code's fallback detection is wording-sensitive; reproduce on a mock endpoint with deliberately different (otherwise equivalent) 422 error wording.

H5 — Fix: either safe protocol-aware downgrade/translation in LiteLLM for DeepSeek, a documented client switch to disable inline-tool generation, or upstream DeepSeek support; check that the chosen implementation does not silently corrupt tool semantics.

## 4. Acceptance criteria

- Repro R0: controlled 200 on ordinary text (or successful validation of safe fixture), and controlled 422 on `tool_definition` with HTTP code + sanitized discriminator and layer attribution. Reproducible with a single command and no customer transcript.
- R1: side-by-side direct DeepSeek vs **isolated** LiteLLM gateway, request headers/beta flags accounted for, request/response bodies kept private, evidence includes version, URL path, fixed fixture hash and request ID prefix only.
- R2: client restart/cold session comparison on Claude Code 2.1.296 (and legacy 2.1.272 as negative control where available); do not alter user's ~/.claude settings or reuse original sessions.
- Fix test: before RED / after GREEN for `tool_definition`, `tool_reference`, mixed content, repeated declarations, multistep tool use, both error wordings, streaming and non-streaming, unsupported beta handling.
- Negative controls: no token leaks; no impact to `container0-litellm`, `litellm-shared-litellm`, or FJ production. No regressions in existing LiteLLM fixture tests.
- Deliver `REPRO.md`, `ROOT_CAUSE.md`, `PATCH_PLAN.md`, `TEST_RESULTS.md`, `ROLLBACK.md` with evidence, commands, changed files and precise limitations.

## 5. Isolation and authorization

- **Only** Tokyo `VM-16-5-ubuntu` as Unix user `vince`, in `LIT-0220` worktree and `/data/home/vince/workspace/test-envs/litellm-bridge/LIT-0220`.
- The new gateway must use a unique compose project, loopback-only port, unique Docker names/network and isolated local configuration. No public binding, no shared production DB/Redis, no root/sudo, no Docker volume deletion, no key disclosure.
- Existing shared/container0 workloads and active Agents are strictly off-limits.
- Stopping old *research-only* gateway containers is permitted **only after independently establishing exact owner, purpose, dependencies, and lack of active use**; retain images, volumes, data, evidence and config. If ambiguous, leave them running and report why.
- Avoid real upstream requests until the necessary credentials can be reused by reference in the authorized local vault; never copy/decrypt/print secrets. Prefer mock and unit tests first; cap real requests to minimal fixture volume.
- Changes to production, shared gateway, authorization, or deleting any data require separate approval.

## 6. Work layout

- Source checkout: `/data/home/vince/workspace/worktrees/litellm-bridge/LIT-0220`.
- Runtime item: `/data/home/vince/workspace/test-envs/litellm-bridge/LIT-0220`.
- Evidence and Yale's verbatim report: `/data/home/vince/artifacts/work-items/litellm/LIT-0220` (private).
- Run all tests and new gateways as this independent Item; no change to `/data/home/vince/workspace/src/litellm-bridge` main worktree.

## Verification status (updated 2026-10-14, RUN-0013)
* **synthetic official-wire E2E: PASSED** — official `system.content.tool_addition.tool.tool_definition`
  returns **422** on the unpatched gateway and **200** on the patched one, in **both non-stream and
  `stream:true` (real `text/event-stream`, 6 SSE events)**; the `tool_addition`/system message keeps its
  position; `tool_use`→`tool_result` ids pair across turns; a definition missing `input_schema` is
  **400 (fail-closed)**.
* **real Claude Code 2.1.296 ToolSearch inline wire: NOT CAPTURED** — RUN-0011 reproduced the ToolSearch
  loop + `--resume`, but the client declared the surfaced tool in `tools[]`, never inline.
* **DeepSeek live: NOT VERIFIED** — no dedicated isolated test key; no paid call made.
