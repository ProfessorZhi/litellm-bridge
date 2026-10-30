# Missing API key log filter validation

This directory reproduces the HTTP A/B validation for the missing-API-key log filter and counter. It runs a real LiteLLM proxy over HTTP against a controlled mock upstream, with PostgreSQL, Redis and Prometheus wired in. It does not call a real model provider.

## What is asserted

Baseline (both flags absent):

- `GET /v1/models`, `POST /v1/messages`, `POST /v1/chat/completions` without `Authorization` return `401` with the same body.
- Empty `Bearer`, bogus key, expired key, a valid master key and an invalid model keep their existing behavior.
- All eight requests produce SpendLogs rows; the three missing-key requests produce console errors and reach the failure callback.

Filtered (`suppress_missing_api_key_logs: true`, `count_missing_api_key_requests: true`):

- The three missing-key requests still return the same `401` body.
- They produce no SpendLogs row, no console error, and do not reach the failure callback.
- Redis and Prometheus each increment by three.
- The other five requests keep their previous logging and callback behavior.

Additional checks:

- A callback that rewrites the auth failure to `403` proves the hook-level boundary: baseline returns `403`, filtered returns the original `401` and the callback is not called.
- Two workers, six missing-key requests: Redis increases by six, SpendLogs and console stay unchanged.
- After a proxy restart: Redis keeps its value, Prometheus resets to zero and increments again on the next request, SpendLogs stays unchanged.

## Environment

- Proxy source commit under test: `e4980116d097f49fbb00a551f254049e2bf26968`
- Base commit: `649668502a5d2946d1ffe39c3ada088bff5b4250`
- Proxy image digest: `sha256:b6af60da88902d3abf71cbc3a32e0e81d8a98a133240e0b4fd6b505178101a80`
- PostgreSQL: `postgres:16-alpine`
- Redis: `redis:7-alpine`
- Mock upstream is the Python file in this directory and records only method, path, status, model and an auth hash.

## Required environment variables

```bash
export LITELLM_IMAGE=<image with the LiteLLM venv at /app/.venv>
export LITELLM_SOURCE=<LiteLLM checkout under test>
export LITELLM_MASTER_KEY=<local test master key>
export MOCK_UPSTREAM_KEY=<local test upstream key>
export POSTGRES_PASSWORD=<local test database password>
export REDIS_PASSWORD=<local test redis password>
export COMPOSE_PROJECT=litellm-authfilter
export PROXY_PORT=4000
export MOCK_PORT=8080
```

These are local test credentials. Do not reuse a production key.

## Start A or B

```bash
CONFIG_FILE=baseline docker compose up -d --force-recreate litellm
CONFIG_FILE=filtered docker compose up -d --force-recreate litellm
```

Wait for the proxy health check before running the matrix.

## Run the matrix

```bash
CONFIG_FILE=baseline E2E_KIND=matrix bash run_e2e.sh
CONFIG_FILE=filtered E2E_KIND=matrix bash run_e2e.sh
```

The script reads the proxy, Postgres, Redis and evidence paths from `PROXY_CONTAINER`, `POSTGRES_CONTAINER`, `REDIS_CONTAINER`, `BASE_URL` and `EVIDENCE_DIR`. Defaults match `docker-compose.yml`.

## Run the extra checks

```bash
CONFIG_FILE=baseline CALLBACK_PROBE_REWRITE=true docker compose up -d --force-recreate litellm
CONFIG_FILE=baseline E2E_KIND=rewrite bash run_e2e.sh

CONFIG_FILE=filtered CALLBACK_PROBE_REWRITE=true docker compose up -d --force-recreate litellm
CONFIG_FILE=filtered E2E_KIND=rewrite bash run_e2e.sh

CONFIG_FILE=filtered LITELLM_NUM_WORKERS=2 docker compose up -d --force-recreate litellm
CONFIG_FILE=filtered E2E_KIND=dual bash run_e2e.sh
```

For the restart check, read the Redis key and the Prometheus counter before and after `docker compose restart litellm`, then send one missing-key request.

## Evidence

`evidence-2026-10-30/` holds the sanitized output of the run:

- assertion summaries for baseline, filtered, rewrite and dual-worker runs
- redacted request/response records; the `auth` field says only `none` or `present`
- SpendLogs error rows and the Prometheus counter line
- server log lines containing only the missing-key error
- callback records with route and error class only
- restart comparison

`manifest.sha256` covers every evidence file. The evidence contains no API keys, prompts, IP addresses or production data.
