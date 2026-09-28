"""Behavior of /monitor/channel-summary against a real Postgres.

Every defect this endpoint shipped lived in the SQL text, so these assertions
run the real query against real tables. A mocked query_raw would assert the
mock, which is exactly where the bugs were invisible.

Fixtures are inserted under a per-test model name and deleted afterwards, so
the read-world seeded by `world` is never mutated.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, Final, List, Optional

import pytest
import pytest_asyncio

from .actors import Actor

pytestmark: Final = pytest.mark.asyncio(loop_scope="session")

BUCKET_SECONDS: Final = 300
WINDOW_START: Final = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
WINDOW_END: Final = datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc)

# 08:04 Beijing time, so the 300s bucket boundary it floors to is unambiguous,
# and far enough from the window edges that a whole-hour shift cannot hide.
REQUEST_AT: Final = datetime(2026, 1, 1, 0, 4)
EXPECTED_BUCKET: Final = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class _Spend:
    request_id: str
    status: Optional[str]
    error_class: Optional[str] = None
    llm_provider: Optional[str] = None
    error_code: Optional[str] = None
    duration_ms: int = 1000
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


# One row of each shape the classifier branches on, all inside one bucket.
SCENARIO: Final = (
    _Spend("ok-1", "success", duration_ms=1000, total_tokens=30, prompt_tokens=10, completion_tokens=20),
    _Spend("ok-2", "success", duration_ms=3000, total_tokens=50, prompt_tokens=20, completion_tokens=30),
    _Spend("net-1", "failure", error_class="ReadError", llm_provider="openai"),
    _Spend("cli-1", "failure", error_code="401", llm_provider="litellm_proxy"),
    _Spend("unk-1", "failure", error_class="SomethingUnmapped", llm_provider="litellm_proxy"),
    _Spend("oth-1", None),
)

# Scenario ids are unique per run, not per row shape, so the fan-out row needs
# its own name: reusing SCENARIO[0] would insert one id under two model groups.
FANOUT_SPEND: Final = _Spend("fanout-1", "success")


@dataclass(frozen=True)
class Monitor:
    tag: str
    key: str
    fanout_model: str
    classify_model: str
    idle_model: str

    async def summary(self, client: Any, model: str) -> List[Dict[str, Any]]:
        resp = await client.get(
            "/monitor/channel-summary",
            headers={"Authorization": f"Bearer {self.key}"},
            params={
                "start_time": WINDOW_START.isoformat(),
                "end_time": WINDOW_END.isoformat(),
                "model": model,
                "bucket_seconds": BUCKET_SECONDS,
            },
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    async def only_bucket(self, client: Any, model: str) -> Dict[str, Any]:
        rows = await self.summary(client, model)
        assert len(rows) == 1, f"expected one bucket for {model}, got {rows}"
        return rows[0]


async def _insert_deployment(prisma: Any, model_name: str) -> None:
    """Add one deployment row. Model id is fresh, so two calls share a name only."""
    await prisma.db.execute_raw(
        """
        INSERT INTO "LiteLLM_ProxyModelTable"
            (model_id, model_name, litellm_params, created_by, updated_by)
        VALUES ($1, $2, '{}'::jsonb, 'monitor-summary-test', 'monitor-summary-test')
        """,
        f"monitor-test-{uuid.uuid4().hex}",
        model_name,
    )


async def _insert_spend(prisma: Any, model_group: str, spend: _Spend, run_tag: str) -> None:
    """Insert one spend row. Request ids are namespaced per test run.

    They are the primary key, and every test in this file seeds the same
    scenario shapes, so a literal id would collide on the second test.
    """
    error_information: Dict[str, Optional[str]] = {
        key: value
        for key, value in (
            ("error_class", spend.error_class),
            ("llm_provider", spend.llm_provider),
            ("error_code", spend.error_code),
        )
        if value is not None
    }
    metadata = {"error_information": error_information} if error_information else {}
    await prisma.db.execute_raw(
        """
        INSERT INTO "LiteLLM_SpendLogs"
            (request_id, call_type, "startTime", "endTime", model, model_group, status,
             request_duration_ms, total_tokens, prompt_tokens, completion_tokens, metadata)
        VALUES ($1, 'acompletion', $2::timestamp, $3::timestamp, $4, $4, $5,
                $6, $7, $8, $9, $10::jsonb)
        """,
        f"{run_tag}-{spend.request_id}",
        REQUEST_AT,
        REQUEST_AT,
        model_group,
        spend.status,
        spend.duration_ms,
        spend.total_tokens,
        spend.prompt_tokens,
        spend.completion_tokens,
        json.dumps(metadata),
    )


@pytest_asyncio.fixture
async def monitor(prisma, proxy_client, world) -> AsyncIterator[Monitor]:
    tag = uuid.uuid4().hex[:8]
    scenario = Monitor(
        tag=tag,
        key=world.keys[Actor.PROXY_ADMIN].cleartext,
        fanout_model=f"scratch-mon-fanout-{tag}",
        classify_model=f"scratch-mon-classify-{tag}",
        idle_model=f"scratch-mon-idle-{tag}",
    )
    try:
        # Two deployments of one model name is the fan-out condition. One
        # spend row under it means any multiplication is unambiguous.
        await _insert_deployment(prisma, scenario.fanout_model)
        await _insert_deployment(prisma, scenario.fanout_model)
        await _insert_spend(prisma, scenario.fanout_model, FANOUT_SPEND, tag)

        await _insert_deployment(prisma, scenario.classify_model)
        for spend in SCENARIO:
            await _insert_spend(prisma, scenario.classify_model, spend, tag)

        # Configured but silent: must still be listed, with a null bucket.
        await _insert_deployment(prisma, scenario.idle_model)
        yield scenario
    finally:
        for model in (scenario.fanout_model, scenario.classify_model, scenario.idle_model):
            await prisma.db.execute_raw(
                'DELETE FROM "LiteLLM_SpendLogs" WHERE model_group = $1', model
            )
            await prisma.db.execute_raw(
                'DELETE FROM "LiteLLM_ProxyModelTable" WHERE model_name = $1', model
            )


async def test_deployment_rows_do_not_multiply_the_counts(monitor: Monitor, proxy_client):
    """One spend row under two deployment rows stays one request."""
    bucket = await monitor.only_bucket(proxy_client, monitor.fanout_model)
    assert bucket["total_requests"] == 1
    assert bucket["success_requests"] == 1


async def test_bucket_lands_in_the_requested_window(monitor: Monitor, proxy_client):
    """The bucket is the instant the request fell in, not eight hours later.

    A whole-hour shift would put every bucket past WINDOW_END, which is the
    blank-panel symptom this endpoint was fixed for.
    """
    bucket = await monitor.only_bucket(proxy_client, monitor.classify_model)
    observed = datetime.fromisoformat(bucket["bucket"]).astimezone(timezone.utc)
    assert observed == EXPECTED_BUCKET
    assert WINDOW_START <= observed < WINDOW_END


async def test_outbound_transport_error_counts_as_channel(monitor: Monitor, proxy_client):
    """A ReadError raised while reading the upstream stream is channel side."""
    bucket = await monitor.only_bucket(proxy_client, monitor.classify_model)
    assert bucket["transport_failures"] == 1
    assert bucket["upstream_failures"] == 0


async def test_platform_side_failure_is_client_caused_and_still_counted(
    monitor: Monitor, proxy_client
):
    """A 401 with no upstream attribution is caller-caused, and stays visible.

    The pre-fix query dropped these rows in the join predicate, so they left
    the request total entirely instead of being shown as exempt.
    """
    bucket = await monitor.only_bucket(proxy_client, monitor.classify_model)
    assert bucket["client_failures"] == 1
    assert bucket["failed_requests"] == 3


async def test_unprovable_failure_defaults_to_channel(monitor: Monitor, proxy_client):
    """Anything that cannot be shown to be the caller's fault counts against the channel."""
    bucket = await monitor.only_bucket(proxy_client, monitor.classify_model)
    assert bucket["unclassified_failures"] == 1
    assert bucket["channel_failures"] == 2
    assert bucket["client_failures"] + bucket["channel_failures"] == bucket["failed_requests"]


async def test_counts_partition_every_row(monitor: Monitor, proxy_client):
    """Total, failure and channel partitions each add up, with other non-zero."""
    bucket = await monitor.only_bucket(proxy_client, monitor.classify_model)
    assert bucket["total_requests"] == len(SCENARIO)
    assert (
        bucket["success_requests"] + bucket["failed_requests"] + bucket["other_requests"]
        == bucket["total_requests"]
    )
    assert bucket["other_requests"] == 1
    assert bucket["success_requests"] == 2
    assert (
        bucket["upstream_failures"]
        + bucket["transport_failures"]
        + bucket["unclassified_failures"]
        == bucket["channel_failures"]
    )


async def test_health_excludes_caller_caused_failures(monitor: Monitor, proxy_client):
    """Availability is success over success plus channel failures, not over total."""
    bucket = await monitor.only_bucket(proxy_client, monitor.classify_model)
    assert bucket["health"] == pytest.approx(2 / 4, abs=1e-4)


async def test_configured_model_without_traffic_is_listed_with_null_bucket(
    monitor: Monitor, proxy_client
):
    """A silent model still appears, and its bucket is null rather than "None"."""
    rows = await monitor.summary(proxy_client, monitor.idle_model)
    assert len(rows) == 1, rows
    assert rows[0]["model_group"] == monitor.idle_model
    assert rows[0]["bucket"] is None
    assert rows[0]["total_requests"] == 0
