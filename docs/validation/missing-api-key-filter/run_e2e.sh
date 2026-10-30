#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"

MODE="${CONFIG_FILE:?set CONFIG_FILE to baseline or filtered}"
KIND="${E2E_KIND:-matrix}"
OUT="${EVIDENCE_DIR:-$PWD/evidence}"
TMP="$OUT/tmp-$MODE-$KIND"
mkdir -p "$TMP" "$OUT"
: > "$TMP/requests.jsonl"
SUMMARY="$OUT/summary-$MODE-$KIND.txt"
FAILED=0

BASE_URL="${BASE_URL:-http://127.0.0.1:4000}"
PROXY_CONTAINER="${PROXY_CONTAINER:-litellm-authfilter-proxy}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-litellm-authfilter-postgres}"
REDIS_CONTAINER="${REDIS_CONTAINER:-litellm-authfilter-redis}"

spend() { docker exec "$POSTGRES_CONTAINER" psql -U litellm -d litellm -t -A -c 'SELECT count(*) FROM "LiteLLM_SpendLogs";'; }
redis_total() { docker exec "$REDIS_CONTAINER" redis-cli -a "$REDIS_PASSWORD" --no-auth-warning GET litellm:auth:missing_api_key:total 2>/dev/null || true; }
prom_missing() { curl -sL -H "Authorization: Bearer $LITELLM_MASTER_KEY" "$BASE_URL/metrics/" | grep '^litellm_missing_api_key_requests_total' | awk '{print $2}' | head -1; }
console_missing() { docker logs "$PROXY_CONTAINER" 2>&1 | grep -c 'user_api_key_auth(): Exception occured - No api key passed in' || true; }
callback_count() { if [[ -f "$OUT/callback-probe-runtime.jsonl" ]]; then wc -l < "$OUT/callback-probe-runtime.jsonl" | tr -d ' '; else echo 0; fi; }

num() { python3 -c 'import sys; v=(sys.argv[1] or "0").strip(); print(int(float(v)))' "$1" 2>/dev/null || echo 0; }

assert_eq() {
  local name="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    echo "PASS $name expected=$expected actual=$actual" | tee -a "$SUMMARY"
  else
    echo "FAIL $name expected=$expected actual=$actual" | tee -a "$SUMMARY"
    FAILED=$((FAILED + 1))
  fi
}

req() {
  local name="$1" method="$2" auth_value="$3" path="$4" body="$5"
  local auth_kind="none"
  local -a headers=(-H 'Content-Type: application/json')
  if [[ -n "$auth_value" ]]; then
    auth_kind="present"
    headers+=(-H "Authorization: $auth_value")
  fi
  local status
  if [[ "$method" == "GET" ]]; then
    status=$(curl -s -o "$TMP/$name.json" -w '%{http_code}' -X GET "$BASE_URL$path" "${headers[@]}") || status=000
  else
    status=$(curl -s -o "$TMP/$name.json" -w '%{http_code}' -X POST "$BASE_URL$path" "${headers[@]}" -d "$body") || status=000
  fi
  python3 - "$TMP/$name.json" "$name" "$method" "$path" "$auth_kind" "$status" >> "$TMP/requests.jsonl" <<'PY'
import json, sys
body_path, name, method, path, auth_kind, status = sys.argv[1:7]
try:
    body = json.load(open(body_path))
except Exception:
    body = open(body_path, errors="replace").read()
print(json.dumps({"name": name, "method": method, "path": path, "auth": auth_kind, "status": int(status), "body": body}, ensure_ascii=False))
PY
  echo "$status"
}

snapshot() {
  echo "[$1] spendlogs=$(spend) redis=$(redis_total) prom=$(prom_missing) console_missing=$(console_missing) callback=$(callback_count)" | tee -a "$SUMMARY"
}

: > "$SUMMARY"
echo "mode=$MODE kind=$KIND" | tee -a "$SUMMARY"

if [[ "$KIND" == "rewrite" ]]; then
  status=$(req rewrite_no_key POST "" "/v1/chat/completions" '{"model":"mock-chat","messages":[{"role":"user","content":"hi"}]}')
  if [[ "$MODE" == "baseline" ]]; then assert_eq rewrite_status 403 "$status"; else assert_eq rewrite_status 401 "$status"; fi
  exit "$FAILED"
fi

if [[ "$KIND" == "dual" ]]; then
  S0=$(num "$(spend)"); R0=$(num "$(redis_total)"); C0=$(num "$(console_missing)"); B0=$(num "$(callback_count)")
  for i in 1 2 3 4 5 6; do
    req "dual_no_key_$i" POST "" "/v1/chat/completions" '{"model":"mock-chat","messages":[{"role":"user","content":"hi"}]}' > /dev/null
  done
  sleep 30
  S1=$(num "$(spend)"); R1=$(num "$(redis_total)"); C1=$(num "$(console_missing)"); B1=$(num "$(callback_count)")
  assert_eq dual_spendlogs_delta 0 "$((S1 - S0))"
  assert_eq dual_redis_delta 6 "$((R1 - R0))"
  assert_eq dual_console_delta 0 "$((C1 - C0))"
  assert_eq dual_callback_delta 0 "$((B1 - B0))"
  snapshot after
  exit "$FAILED"
fi

S0=$(num "$(spend)"); R0=$(num "$(redis_total)"); P0=$(num "$(prom_missing)"); C0=$(num "$(console_missing)"); B0=$(num "$(callback_count)")
snapshot before

req models_no_auth GET "" "/v1/models" "" > "$TMP/status_models"
req messages_no_auth POST "" "/v1/messages" '{"model":"mock-chat","max_tokens":16,"messages":[{"role":"user","content":"hi"}]}' > "$TMP/status_messages"
req chat_no_auth POST "" "/v1/chat/completions" '{"model":"mock-chat","messages":[{"role":"user","content":"hi"}]}' > "$TMP/status_chat"
req bearer_empty POST "Bearer " "/v1/chat/completions" '{"model":"mock-chat","messages":[{"role":"user","content":"hi"}]}' > "$TMP/status_bearer"
req bogus_key POST "Bearer sk-bogus-not-a-key" "/v1/chat/completions" '{"model":"mock-chat","messages":[{"role":"user","content":"hi"}]}' > "$TMP/status_bogus"
expired_response=$(curl -s -X POST "$BASE_URL/key/generate" -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H 'Content-Type: application/json' -d "{\"duration\":\"1s\",\"models\":[\"mock-chat\"],\"key_alias\":\"missing-key-e2e-$(date +%s)\"}")
expired_key=$(echo "$expired_response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["key"])')
sleep 3
req expired_key POST "Bearer $expired_key" "/v1/chat/completions" '{"model":"mock-chat","messages":[{"role":"user","content":"hi"}]}' > "$TMP/status_expired"
req valid_master POST "Bearer $LITELLM_MASTER_KEY" "/v1/chat/completions" '{"model":"mock-chat","messages":[{"role":"user","content":"hi"}]}' > "$TMP/status_valid"
req invalid_model POST "Bearer $LITELLM_MASTER_KEY" "/v1/chat/completions" '{"model":"nonexistent-model","messages":[{"role":"user","content":"hi"}]}' > "$TMP/status_invalid_model"

sleep 30
S1=$(num "$(spend)"); R1=$(num "$(redis_total)"); P1=$(num "$(prom_missing)"); C1=$(num "$(console_missing)"); B1=$(num "$(callback_count)")

if [[ "$MODE" == "baseline" ]]; then
  assert_eq spendlogs_delta 8 "$((S1 - S0))"
  assert_eq redis_delta 0 "$((R1 - R0))"
  assert_eq prom_delta 0 "$((P1 - P0))"
  assert_eq console_missing_delta 3 "$((C1 - C0))"
  assert_eq callback_delta 7 "$((B1 - B0))"
else
  assert_eq spendlogs_delta 5 "$((S1 - S0))"
  assert_eq redis_delta 3 "$((R1 - R0))"
  assert_eq prom_delta 3 "$((P1 - P0))"
  assert_eq console_missing_delta 0 "$((C1 - C0))"
  assert_eq callback_delta 4 "$((B1 - B0))"
fi

assert_eq models_status 401 "$(cat "$TMP/status_models")"
assert_eq messages_status 401 "$(cat "$TMP/status_messages")"
assert_eq chat_status 401 "$(cat "$TMP/status_chat")"
if cmp -s "$TMP/models_no_auth.json" "$TMP/messages_no_auth.json" && cmp -s "$TMP/models_no_auth.json" "$TMP/chat_no_auth.json"; then
  echo "PASS missing_key_bodies_identical" | tee -a "$SUMMARY"
else
  echo "FAIL missing_key_bodies_identical" | tee -a "$SUMMARY"; FAILED=$((FAILED + 1))
fi

snapshot after
docker logs --tail 200 "$PROXY_CONTAINER" 2>&1 | grep -E "user_api_key_auth\(\): Exception occured|No api key passed in" > "$OUT/server-$MODE-$KIND-keylines.log" || true
curl -sL -H "Authorization: Bearer $LITELLM_MASTER_KEY" "$BASE_URL/metrics/" | grep '^litellm_missing_api_key_requests_total' > "$OUT/metrics-$MODE-$KIND.txt" || true
docker exec "$POSTGRES_CONTAINER" psql -U litellm -d litellm -t -A -F '|' -c "SELECT left(coalesce(metadata->>'error_information',''),120) FROM \"LiteLLM_SpendLogs\" ORDER BY \"startTime\" DESC LIMIT 12;" > "$OUT/spendrows-$MODE-$KIND.txt" || true

echo "failures=$FAILED" | tee -a "$SUMMARY"
exit "$FAILED"
