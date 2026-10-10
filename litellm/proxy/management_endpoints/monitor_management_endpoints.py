"""
渠道可用性监控端点：按 model_group × 时间桶聚合健康度/延迟/吞吐量。
数据源 PostgreSQL LiteLLM_SpendLogs（startTime 为 naive UTC，桶按北京时间对齐）。
"""
from datetime import datetime
from typing import Final, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.spend_tracking.spend_management_endpoints import _is_admin_view_safe

router = APIRouter()

# startTime 存的是 naive UTC。桶按北京零点对齐，因为平台的额度日界与运营口径都是北京时间。
_BUCKET_TZ_OFFSET_SECONDS: Final = 8 * 3600


class ChannelBucket(BaseModel):
    bucket: Optional[datetime] = None
    model_group: str
    total_requests: int = 0
    success_requests: int = 0
    failed_requests: int = 0
    other_requests: int = 0
    client_failures: int = 0
    channel_failures: int = 0
    upstream_failures: int = 0
    transport_failures: int = 0
    unclassified_failures: int = 0
    avg_latency_ms: Optional[float] = None
    avg_ttft_ms: Optional[float] = None
    p50_ms: Optional[float] = None
    p95_ms: Optional[float] = None
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    health: float = 0.0


class _RawBucket(BaseModel):
    model_group: str
    bucket: Optional[datetime] = None
    total_requests: int = 0
    success_requests: int = 0
    failed_requests: int = 0
    other_requests: int = 0
    client_failures: int = 0
    channel_failures: int = 0
    upstream_failures: int = 0
    transport_failures: int = 0
    unclassified_failures: int = 0
    avg_latency: Optional[float] = None
    avg_ttft: Optional[float] = None
    p50: Optional[float] = None
    p95: Optional[float] = None
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


def _parse_dt(s: str) -> datetime:
    if not s:
        raise HTTPException(status_code=400, detail="start_time/end_time required")
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid ISO8601 time")


async def _query_raw(prisma_client, sql_query: str, *args):
    return await prisma_client.db.query_raw(sql_query, *args)


def _bucket_from_row(raw: _RawBucket) -> ChannelBucket:
    channel_failures = raw.channel_failures
    healthy = raw.success_requests + channel_failures
    return ChannelBucket(
        bucket=raw.bucket,
        model_group=raw.model_group,
        total_requests=raw.total_requests,
        success_requests=raw.success_requests,
        failed_requests=raw.failed_requests,
        other_requests=raw.other_requests,
        client_failures=raw.client_failures,
        channel_failures=channel_failures,
        upstream_failures=raw.upstream_failures,
        transport_failures=raw.transport_failures,
        unclassified_failures=raw.unclassified_failures,
        avg_latency_ms=raw.avg_latency,
        avg_ttft_ms=raw.avg_ttft,
        p50_ms=raw.p50,
        p95_ms=raw.p95,
        total_tokens=raw.total_tokens,
        prompt_tokens=raw.prompt_tokens,
        completion_tokens=raw.completion_tokens,
        health=round(raw.success_requests / healthy, 4) if healthy else 0.0,
    )


@router.get(
    "/monitor/channel-summary",
    tags=["channel-monitor"],
    dependencies=[Depends(user_api_key_auth)],
    response_model=list[ChannelBucket],
)
async def channel_summary(
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
    start_time: str = Query(...),
    end_time: str = Query(...),
    model: Optional[str] = Query(None, description="按 model_group 过滤"),
    bucket_seconds: int = Query(300, ge=60, le=86400, description="聚合桶大小(秒)"),
):
    # 内部用户也能看渠道健康度（放给所有登录用户）
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Prisma client not initialized")

    start_dt = _parse_dt(start_time)
    end_dt = _parse_dt(end_time)

    args: list = [start_dt, end_dt, model, bucket_seconds, _BUCKET_TZ_OFFSET_SECONDS]

    # 渠道列表 = 实际配置的模型(LiteLLM_ProxyModelTable.model_name)。
    # DISTINCT 是必须的:同一 model_name 可以有多条部署记录,不 DISTINCT 会让每条部署各算一遍,
    # 把请求数放大到部署份数倍。
    sql = f"""
        WITH configured_models AS (
            SELECT DISTINCT model_name
            FROM "LiteLLM_ProxyModelTable"
            WHERE ($3::text IS NULL OR model_name = $3)
        ),
        classified_requests AS (
            SELECT
                COALESCE(NULLIF(s.model_group, ''), s.model) AS model_group,
                -- startTime 是 naive UTC: epoch 直接取用即可, 不能再做时区转换(转换会把桶整体平移到未来)。
                -- offset 只决定桶的相位, 净位移为零: 先加 offset 对齐到北京边界, 再减回去。
                to_timestamp(floor((extract(epoch FROM s."startTime") + $5::int) / $4::int) * $4::int - $5::int) AS bucket,
                s.status,
                s.request_duration_ms,
                s."completionStartTime",
                s."startTime",
                s."endTime",
                s.total_tokens,
                s.prompt_tokens,
                s.completion_tokens,
                -- 失败分类只在这里算一次, 下游聚合一律用 FILTER 引用它, 避免口径在多处漂移。
                -- 口径: 只豁免"能证明是调用方责任"的失败; 证明不了的一律算渠道失败(默认计入)。
                CASE
                    WHEN s.status IS DISTINCT FROM 'failure' THEN NULL
                    WHEN COALESCE(s.metadata->'error_information'->>'error_class', '') IN (
                        'BudgetExceededError', 'ContextWindowExceededError', 'KeyModelAccessDenied',
                        'KeyNotFoundError', 'ProxyMissingRequiredParamError', 'ProxyModelNotFoundError'
                    ) THEN 'client'
                    -- 未带鉴权头的请求: 认证层在记账前抛裸 Exception, 无 error_code、无 provider 归因,
                    -- 顶层 user_api_key 也不会写。四者同时为空才判调用方, 否则真实的渠道异常会被洗成 client。
                    WHEN COALESCE(s.metadata->'error_information'->>'error_class', '') = 'Exception'
                     AND s.metadata->>'user_api_key' IS NULL
                     AND COALESCE(s.metadata->'error_information'->>'error_code', '') = ''
                     AND COALESCE(s.metadata->'error_information'->>'llm_provider', '') IN ('', 'litellm_proxy', 'litellm')
                        THEN 'client'
                    -- 出站传输失败(如 httpx.ReadError 在上游流读取时抛出)属渠道侧。
                    WHEN COALESCE(s.metadata->'error_information'->>'error_class', '') IN (
                        'APIConnectionError', 'ConnectError', 'ConnectTimeout', 'LocalProtocolError',
                        'PoolTimeout', 'ReadError', 'ReadTimeout', 'RemoteProtocolError', 'Timeout',
                        'WriteError', 'WriteTimeout'
                    ) THEN 'transport'
                    -- 有真实厂商归因即算 provider。放在 error_code 判据之前, 因为带 provider 的
                    -- 403(如上游策略拒绝)是上游失败, 不是调用方鉴权失败。
                    WHEN COALESCE(s.metadata->'error_information'->>'llm_provider', '') NOT IN ('', 'litellm_proxy', 'litellm')
                        THEN 'provider'
                    -- 平台层直接拒绝: 401/402/403 且无上游归因, 且异常未带出站调用栈。带栈的是 pass-through
                    -- 上游自己返回的 401(pass_through_endpoints 记录 httpx.HTTPStatusError), 属渠道侧。
                    -- 只按 error_code 判定, 不按异常类名——ProxyException 太泛, 整类白名单化会漏算真实渠道失败。
                    WHEN COALESCE(s.metadata->'error_information'->>'error_code', '') IN ('401', '402', '403')
                     AND COALESCE(s.metadata->'error_information'->>'llm_provider', '') IN ('', 'litellm_proxy', 'litellm')
                     AND COALESCE(s.metadata->'error_information'->>'traceback', '') = ''
                        THEN 'client'
                    ELSE 'unclassified'
                END AS failure_category
            FROM "LiteLLM_SpendLogs" s
            -- 转成 naive UTC 再比较, 否则比较结果会随连接会话的 TimeZone 漂移, 窗口被静默平移。
            WHERE s."startTime" >= ($1::timestamptz AT TIME ZONE 'UTC')
              AND s."startTime" <  ($2::timestamptz AT TIME ZONE 'UTC')
        ),
        aggregated AS (
            SELECT
                model_group,
                bucket,
                COUNT(*) AS total_requests,
                COUNT(*) FILTER (WHERE status = 'success') AS success_requests,
                COUNT(*) FILTER (WHERE status = 'failure') AS failed_requests,
                COUNT(*) FILTER (WHERE status IS DISTINCT FROM 'success' AND status IS DISTINCT FROM 'failure') AS other_requests,
                COUNT(*) FILTER (WHERE failure_category = 'client') AS client_failures,
                COUNT(*) FILTER (WHERE failure_category IN ('provider', 'transport', 'unclassified')) AS channel_failures,
                COUNT(*) FILTER (WHERE failure_category = 'provider') AS upstream_failures,
                COUNT(*) FILTER (WHERE failure_category = 'transport') AS transport_failures,
                COUNT(*) FILTER (WHERE failure_category = 'unclassified') AS unclassified_failures,
                -- 延迟与吞吐统计在成功请求上: 失败请求大多毫秒级返回, 混进来会把响应时间压低。
                AVG(request_duration_ms) FILTER (WHERE status = 'success')::float8 AS avg_latency,
                AVG(CASE WHEN status = 'success' AND "completionStartTime" IS NOT NULL AND "completionStartTime" < "endTime"
                         THEN extract(epoch FROM ("completionStartTime" - "startTime")) * 1000
                         ELSE NULL END)::float8 AS avg_ttft,
                percentile_cont(0.5) WITHIN GROUP (ORDER BY request_duration_ms)
                    FILTER (WHERE status = 'success')::float8 AS p50,
                percentile_cont(0.95) WITHIN GROUP (ORDER BY request_duration_ms)
                    FILTER (WHERE status = 'success')::float8 AS p95,
                COALESCE(SUM(total_tokens) FILTER (WHERE status = 'success'), 0)::bigint AS total_tokens,
                COALESCE(SUM(prompt_tokens) FILTER (WHERE status = 'success'), 0)::bigint AS prompt_tokens,
                COALESCE(SUM(completion_tokens) FILTER (WHERE status = 'success'), 0)::bigint AS completion_tokens
            FROM classified_requests
            GROUP BY model_group, bucket
        )
        SELECT
            m.model_name AS model_group,
            a.bucket,
            COALESCE(a.total_requests, 0)::bigint AS total_requests,
            COALESCE(a.success_requests, 0)::bigint AS success_requests,
            COALESCE(a.failed_requests, 0)::bigint AS failed_requests,
            COALESCE(a.other_requests, 0)::bigint AS other_requests,
            COALESCE(a.client_failures, 0)::bigint AS client_failures,
            COALESCE(a.channel_failures, 0)::bigint AS channel_failures,
            COALESCE(a.upstream_failures, 0)::bigint AS upstream_failures,
            COALESCE(a.transport_failures, 0)::bigint AS transport_failures,
            COALESCE(a.unclassified_failures, 0)::bigint AS unclassified_failures,
            a.avg_latency, a.avg_ttft, a.p50, a.p95,
            COALESCE(a.total_tokens, 0)::bigint AS total_tokens,
            COALESCE(a.prompt_tokens, 0)::bigint AS prompt_tokens,
            COALESCE(a.completion_tokens, 0)::bigint AS completion_tokens
        FROM configured_models m
        LEFT JOIN aggregated a ON a.model_group = m.model_name
        ORDER BY m.model_name, a.bucket
    """

    rows = await _query_raw(prisma_client, sql, *args)

    return tuple(_bucket_from_row(_RawBucket.model_validate(dict(row))) for row in rows)
