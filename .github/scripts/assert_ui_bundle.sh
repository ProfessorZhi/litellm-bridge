#!/usr/bin/env bash
# Fails when the committed UI bundle cannot be served:
#   1. it carries unresolved git conflict markers (the served page then starts
#      with "<<<<<<< HEAD", which drops the browser into quirks mode), or
#   2. an entry HTML references a chunk that was never committed, so the page
#      cannot hydrate (no form, no data) even if the markers are stripped.
#
# litellm/proxy/_experimental/out is served directly by the proxy, so either
# defect breaks the dashboard while every API endpoint stays green.
set -euo pipefail

OUT="litellm/proxy/_experimental/out"
CHUNK_RE='/litellm-asset-prefix/_next/static/chunks/[A-Za-z0-9_.-]+\.(js|css)'
fail=0

if [ ! -d "$OUT" ]; then
  echo "::error::$OUT is missing"
  exit 1
fi

# grep exits 1 when nothing matches, which pipefail would turn into a failure.
markers=$( (grep -RIl '^<<<<<<< ' "$OUT" 2>/dev/null || true) | wc -l | tr -d ' ')
if [ "$markers" -ne 0 ]; then
  echo "::error::$markers file(s) under $OUT carry unresolved conflict markers"
  grep -RIl '^<<<<<<< ' "$OUT" | head -20
  fail=1
fi

checked=0
missing=0
while IFS= read -r f; do
  refs=$(grep -oE "$CHUNK_RE" "$f" | sort -u || true)
  if [ -z "$refs" ]; then
    continue
  fi
  checked=$((checked + 1))
  for r in $refs; do
    # $r is an absolute URL path; the file lives under $OUT on disk.
    if [ ! -f "$OUT${r#/litellm-asset-prefix}" ]; then
      echo "::error::missing chunk $r (referenced by $f)"
      missing=$((missing + 1))
    fi
  done
done < <(find "$OUT" -name 'index.html')
echo "checked $checked entry file(s); missing chunk references: $missing"

if [ "$missing" -ne 0 ]; then
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo "UI bundle check FAILED"
  exit 1
fi
echo "UI bundle OK"
