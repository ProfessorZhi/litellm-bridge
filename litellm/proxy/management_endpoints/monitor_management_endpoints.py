"""
渠道可用性监控端点：按 model_group × 5min 桶聚合健康度/延迟/吞吐量。
数据源 PostgreSQL LiteLLM_SpendLogs（ASIA/Shanghai 分桶）。
"""
from datetime import datetime
from typing import Optional, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.spend_tracking.spend_management_endpoints import _is_admin_view_safe

router = APIRouter()


class ChannelBucket(BaseModel):
    bucket: str
    model_group: str
    total_requests: int = 0
    success_requests: int = 0
    upstream_failures: int = 0   # 仅上游/provider 失败(用户自己错误已剔除)
    avg_latency_ms: Optional[float] = None
    avg_ttft_ms: Optional[float] = None
    p50_ms: Optional[float] = None
    p95_ms: Optional[float] = None
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    health: float = 0.0   # success/total


def _parse_dt(s: str) -> datetime:
    if not s:
        raise HTTPException(status_code=400, detail="start_time/end_time required")
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid ISO8601 time")


async def _query_raw(prisma_client, sql_query: str, *args):
    return await prisma_client.db.query_raw(sql_query, *args)


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

    args: list = [start_dt, end_dt, model, bucket_seconds]

    # 渠道列表 = 实际配置的模型(LiteLLM_ProxyModelTable.model_name)；假/未知 model_group 不匹配则排除
    sql = f"""
        SELECT
            m.model_name AS model_group,
            to_timestamp(floor(extract(epoch FROM s."startTime" AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Shanghai')/ $4::int) * $4::int) AS bucket,
            COUNT(s.request_id) AS total_requests,
            COUNT(s.request_id) FILTER (WHERE s.status = 'success') AS success_requests,
            COUNT(s.request_id) FILTER (WHERE s.status = 'failure'
                -- 双保险:只有"真实上游"才算上游错误。用户侧(平台代理层)错误一律剔除。
                -- 判据1:llm_provider 是真实上游厂商(非 litellm_proxy / litellm / 空)
                AND s.metadata->'error_information'->>'llm_provider' IS NOT NULL AND s.metadata->'error_information'->>'llm_provider' <> '' AND s.metadata->'error_information'->>'llm_provider' NOT IN ('litellm_proxy','litellm')
                -- 判据2(双保险):error_class 不在"用户侧(平台层)"白名单内(权限/预算/平台认证/模型不存在/上下文超长等)
                -- 注意:AuthenticationError 是"上游 provider"认证失败(PROV-006,如 Anthropic 令牌过期),应计入上游,不放白名单。
                AND COALESCE(s.metadata->'error_information'->>'error_class','') NOT IN ('BudgetExceededError','KeyModelAccessDenied','KeyNotFoundError','ProxyException','ProxyModelNotFoundError','ContextWindowExceededError')
            ) AS upstream_failures,
            AVG(s.request_duration_ms) AS avg_latency,
            AVG(CASE WHEN s."completionStartTime" IS NOT NULL AND s."completionStartTime" < s."endTime"
                     THEN extract(epoch FROM (s."completionStartTime" - s."startTime"))*1000
                     ELSE NULL END) AS avg_ttft,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY s.request_duration_ms) AS p50,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY s.request_duration_ms) AS p95,
            COALESCE(SUM(s.total_tokens),0) AS total_tokens,
            COALESCE(SUM(s.prompt_tokens),0) AS prompt_tokens,
            COALESCE(SUM(s.completion_tokens),0) AS completion_tokens
        FROM "LiteLLM_ProxyModelTable" m
        LEFT JOIN "LiteLLM_SpendLogs" s
          ON COALESCE(NULLIF(s.model_group, ''), s.model) = m.model_name
         AND s."startTime" >= $1::timestamptz
         AND s."startTime" < $2::timestamptz
         -- 剔除用户自己的错误(平台代理层:401 无效key/402 超预算/403 key配错/模型不存在/上下文超长等)。
         -- 双保险:上游 = failure 且 llm_provider 是真实厂商 且 error_class 不在"用户侧白名单"。
         -- AuthenticationError(上游 provider 认证失败,PROV-006)不计入白名单,归上游显示。
         AND NOT (s.status = 'failure' AND (
                 (s.metadata->'error_information'->>'llm_provider' IS NULL OR s.metadata->'error_information'->>'llm_provider' = '' OR s.metadata->'error_information'->>'llm_provider' IN ('litellm_proxy','litellm'))
                 OR COALESCE(s.metadata->'error_information'->>'error_class','') IN ('BudgetExceededError','KeyModelAccessDenied','KeyNotFoundError','ProxyException','ProxyModelNotFoundError','ContextWindowExceededError')
             ))
        WHERE ($3::text IS NULL OR m.model_name = $3)
        GROUP BY m.model_name, bucket
        ORDER BY bucket ASC
    """

    rows = await _query_raw(prisma_client, sql, *args)

    result = []
    for r in rows:
        total = r.get("total_requests", 0) or 0
        success = r.get("success_requests", 0) or 0
        upstream_failures = r.get("upstream_failures", 0) or 0
        health = (success / total) if total else 0.0
        result.append(ChannelBucket(
            bucket=str(r.get("bucket", "")),
            model_group=str(r.get("model_group", "")),
            total_requests=total,
            success_requests=success,
            upstream_failures=upstream_failures,
            avg_latency_ms=r.get("avg_latency"),
            avg_ttft_ms=r.get("avg_ttft"),
            p50_ms=r.get("p50"),
            p95_ms=r.get("p95"),
            total_tokens=r.get("total_tokens", 0) or 0,
            prompt_tokens=r.get("prompt_tokens", 0) or 0,
            completion_tokens=r.get("completion_tokens", 0) or 0,
            health=round(health, 4),
        ))
    return result
