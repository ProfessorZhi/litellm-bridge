#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVIDENCE="${LIT0226_REAL_EVIDENCE:?LIT0226_REAL_EVIDENCE is required}"
WORKTREE="${LIT0226_REAL_WORKTREE:?LIT0226_REAL_WORKTREE is required}"
GATEWAY="http://127.0.0.1:26547"
UPSTREAM="https://api.deepseek.com/anthropic/v1/messages"
VAULT="${DEEPSEEK_ENV_FILE:?DEEPSEEK_ENV_FILE is required}"
COMPOSE=(docker compose -p lit-0226-real23 -f "$HERE/docker-compose.yml")

mkdir -p "$EVIDENCE"/{raw,models,wire,logs}
rm -f "$EVIDENCE"/raw/* "$EVIDENCE"/models/* "$EVIDENCE"/wire/* "$EVIDENCE"/logs/*

MASTER_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
export LITELLM_MASTER_KEY="$MASTER_KEY"

set -a
# shellcheck disable=SC1090
source "$VAULT"
set +a
export DEEPSEEK_API_KEY="$DEEPSEEK_TEST_KEY"
unset DEEPSEEK_TEST_KEY

cleanup() {
  rm -f "${ACL_KEY_FILE:-}"
  if [[ "${LIT0226_REAL_KEEP_RUNNING:-0}" != "1" ]]; then
    "${COMPOSE[@]}" down
  fi
}
trap cleanup EXIT

"${COMPOSE[@]}" up -d
for _ in $(seq 1 90); do
  if curl -fsS "$GATEWAY/health/liveliness" >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS "$GATEWAY/health/liveliness" >/dev/null

request_headers() {
  local file="$1" auth_header="$2"
  {
    echo "method: POST"
    echo "auth: <redacted>"
    echo "content-type: application/json"
    echo "anthropic-version: 2023-06-01"
    echo "auth_header: $auth_header"
  } > "$file"
}

response_headers() {
  local raw="$1" clean="$2"
  grep -viE '^(authorization|x-api-key|set-cookie|cookie):' "$raw" > "$clean" || true
  rm -f "$raw"
}

create_model() {
  local name="$1" body="$2" status
  printf '%s' "$body" > "$EVIDENCE/models/$name.request.json"
  status="$(curl -sS --max-time 60 -o "$EVIDENCE/models/$name.response.json" -w '%{http_code}' \
    -X POST "$GATEWAY/model/new" \
    -H "Authorization: Bearer $MASTER_KEY" \
    -H "content-type: application/json" \
    --data-binary "$body")"
  printf '%s' "$status" > "$EVIDENCE/models/$name.status"
  echo "$name model create: HTTP $status" | tee -a "$EVIDENCE/logs/run.log"
  if [[ "$status" != "200" && "$status" != "201" ]]; then
    cat "$EVIDENCE/models/$name.response.json" | tee -a "$EVIDENCE/logs/run.log"
    exit 1
  fi
}

post_proxy() {
  local name="$1" url="$2" body="$3" key="$4" status
  printf '%s' "$body" > "$EVIDENCE/raw/$name.request.json"
  request_headers "$EVIDENCE/raw/$name.request.headers.txt" "Authorization"
  status="$(curl -sS --max-time 120 -o "$EVIDENCE/raw/$name.response.body" \
    -D "$EVIDENCE/raw/$name.response.headers.raw" -w '%{http_code}' \
    -X POST "$url" \
    -H "Authorization: Bearer $key" \
    -H "content-type: application/json" \
    -H "anthropic-version: 2023-06-01" \
    --data-binary "$body")"
  printf '%s' "$status" > "$EVIDENCE/raw/$name.status"
  response_headers "$EVIDENCE/raw/$name.response.headers.raw" "$EVIDENCE/raw/$name.response.headers.txt"
  echo "$name: HTTP $status" | tee -a "$EVIDENCE/logs/run.log"
}

COMPAT_MODEL_BODY='{"model_name":"v4pro-compat","litellm_params":{"model":"anthropic/deepseek-flash","api_base":"https://api.deepseek.com/anthropic","api_key":"os.environ/DEEPSEEK_API_KEY"},"model_info":{"anthropic_messages_compatibility":"deepseek"}}'
PLAIN_MODEL_BODY='{"model_name":"v4pro-plain","litellm_params":{"model":"anthropic/deepseek-flash","api_base":"https://api.deepseek.com/anthropic","api_key":"os.environ/DEEPSEEK_API_KEY"}}'

create_model v4pro-compat "$COMPAT_MODEL_BODY"
create_model v4pro-plain "$PLAIN_MODEL_BODY"
curl -sS --max-time 60 -o "$EVIDENCE/models/model-info.json" \
  -H "Authorization: Bearer $MASTER_KEY" "$GATEWAY/model/info" || true

DIRECT_BODY='{"model":"deepseek-flash","max_tokens":8,"messages":[{"role":"user","content":"Reply with the single word OK."}]}'
printf '%s' "$DIRECT_BODY" > "$EVIDENCE/raw/direct.request.json"
request_headers "$EVIDENCE/raw/direct.request.headers.txt" "x-api-key"
DIRECT_STATUS="$(curl -sS --max-time 120 -o "$EVIDENCE/raw/direct.response.body" \
  -D "$EVIDENCE/raw/direct.response.headers.raw" -w '%{http_code}' \
  -X POST "$UPSTREAM" \
  -H "x-api-key: $DEEPSEEK_API_KEY" \
  -H "content-type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  --data-binary "$DIRECT_BODY")"
printf '%s' "$DIRECT_STATUS" > "$EVIDENCE/raw/direct.status"
response_headers "$EVIDENCE/raw/direct.response.headers.raw" "$EVIDENCE/raw/direct.response.headers.txt"
echo "direct upstream probe: HTTP $DIRECT_STATUS" | tee -a "$EVIDENCE/logs/run.log"
if [[ "$DIRECT_STATUS" != "200" ]]; then
  echo "live E2E blocked at the direct probe; no proxy upstream call was made" | tee -a "$EVIDENCE/logs/run.log"
  exit 1
fi

COMPAT_BODY='{"model":"v4pro-compat","max_tokens":64,"tools":[{"name":"old_tool","description":"withdrawn","input_schema":{"type":"object"}},{"name":"existing_tool","description":"referenced","input_schema":{"type":"object"}}],"messages":[{"role":"system","content":[{"type":"text","text":"tool policy"},{"type":"tool_addition","tool":{"type":"tool_definition","definition":{"name":"dynamic_tool","description":"inline","input_schema":{"type":"object","properties":{"q":{"type":"string"}}}}}},{"type":"tool_addition","tool":{"type":"tool_reference","name":"existing_tool"}},{"type":"tool_removal","tool":{"type":"tool_reference","name":"old_tool"}}]},{"role":"user","content":"Reply with the single word OK. Do not call a tool."}]}'
PLAIN_BODY='{"model":"v4pro-plain","max_tokens":64,"tools":[{"name":"old_tool","description":"withdrawn","input_schema":{"type":"object"}},{"name":"existing_tool","description":"referenced","input_schema":{"type":"object"}}],"messages":[{"role":"system","content":[{"type":"text","text":"tool policy"},{"type":"tool_addition","tool":{"type":"tool_definition","definition":{"name":"dynamic_tool","description":"inline","input_schema":{"type":"object","properties":{"q":{"type":"string"}}}}}},{"type":"tool_addition","tool":{"type":"tool_reference","name":"existing_tool"}},{"type":"tool_removal","tool":{"type":"tool_reference","name":"old_tool"}}]},{"role":"user","content":"Reply with the single word OK. Do not call a tool."}]}'
STREAM_BODY='{"model":"v4pro-compat","max_tokens":32,"stream":true,"messages":[{"role":"system","content":[{"type":"tool_addition","tool":{"type":"tool_definition","definition":{"name":"stream_tool","input_schema":{"type":"object"}}}}]},{"role":"user","content":"Reply with the single word OK. Do not call a tool."}]}'

post_proxy compat "$GATEWAY/v1/messages" "$COMPAT_BODY" "$MASTER_KEY"
post_proxy plain "$GATEWAY/v1/messages" "$PLAIN_BODY" "$MASTER_KEY"
post_proxy compat-beta "$GATEWAY/v1/messages?beta=true" "$COMPAT_BODY" "$MASTER_KEY"
post_proxy plain-beta "$GATEWAY/v1/messages?beta=true" "$PLAIN_BODY" "$MASTER_KEY"
post_proxy compat-stream "$GATEWAY/v1/messages" "$STREAM_BODY" "$MASTER_KEY"

ACL_KEY_FILE="$(mktemp)"
chmod 600 "$ACL_KEY_FILE"
curl -fsS -X POST "$GATEWAY/key/generate" \
  -H "Authorization: Bearer $MASTER_KEY" \
  -H "content-type: application/json" \
  -d '{"models":["v4pro-compat"],"metadata":{"allowed_tools":["allowed_tool"]}}' \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["key"])' > "$ACL_KEY_FILE"
ACL_KEY="$(cat "$ACL_KEY_FILE")"
echo "restricted key generated" | tee -a "$EVIDENCE/logs/run.log"

ACL_DEFINITION='{"model":"v4pro-compat","max_tokens":32,"messages":[{"role":"system","content":[{"type":"tool_addition","tool":{"type":"tool_definition","definition":{"name":"secret_definition_live","input_schema":{"type":"object"}}}}]},{"role":"user","content":"case-acl-definition-live"}]}'
ACL_REFERENCE='{"model":"v4pro-compat","max_tokens":32,"tools":[{"name":"allowed_tool","input_schema":{"type":"object"}}],"messages":[{"role":"system","content":[{"type":"tool_addition","tool":{"type":"tool_reference","name":"secret_reference_live"}}]},{"role":"user","content":"case-acl-reference-live"}]}'
ACL_REMOVAL='{"model":"v4pro-compat","max_tokens":32,"tools":[{"name":"allowed_tool","input_schema":{"type":"object"}},{"name":"secret_removed_live","input_schema":{"type":"object"}}],"messages":[{"role":"system","content":[{"type":"tool_removal","tool":{"type":"tool_reference","name":"secret_removed_live"}}]},{"role":"user","content":"case-acl-removal-live"}]}'

post_proxy acl-definition "$GATEWAY/v1/messages" "$ACL_DEFINITION" "$ACL_KEY"
post_proxy acl-reference "$GATEWAY/v1/messages" "$ACL_REFERENCE" "$ACL_KEY"
post_proxy acl-removal "$GATEWAY/v1/messages" "$ACL_REMOVAL" "$ACL_KEY"

PYTHONPATH="$WORKTREE" LIT0226_REAL_EVIDENCE="$EVIDENCE" \
  "${PYTHON:-python3}" "$HERE/replay_transform.py" \
  > "$EVIDENCE/logs/replay.log" 2>&1 || true

"${COMPOSE[@]}" logs --no-color proxy-live 2>&1 \
  | LITELLM_MASTER_KEY="$MASTER_KEY" DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" \
    "${PYTHON:-python3}" -I "$HERE/sanitize_log.py" > "$EVIDENCE/logs/proxy-live.log"

LIT0226_REAL_EVIDENCE="$EVIDENCE" DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" \
  "${PYTHON:-python3}" -I "$HERE/summarize.py"
