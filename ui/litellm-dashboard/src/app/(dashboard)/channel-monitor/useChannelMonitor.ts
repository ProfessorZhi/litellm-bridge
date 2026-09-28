"use client";

import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import { useCallback, useEffect, useRef, useState } from "react";

export interface ChannelBucket {
  /** 桶起点；已配置但窗口内无请求的模型为 null */
  bucket: string | null;
  model_group: string;
  total_requests: number;
  success_requests: number;
  failed_requests: number;
  /** status 既非 success 也非 failure 的请求（防御未来新增状态） */
  other_requests: number;
  /** 能证明是调用方责任的失败 */
  client_failures: number;
  /** 其余全部失败，含未分类 */
  channel_failures: number;
  /** channel_failures 中能明确归因 provider 的子集 */
  upstream_failures: number;
  transport_failures: number;
  unclassified_failures: number;
  avg_latency_ms: number | null;
  avg_ttft_ms: number | null;
  p50_ms: number | null;
  p95_ms: number | null;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  /** 渠道可用率 = success / (success + channel_failures)，分母不是 total */
  health: number;
}

export interface WindowOpt {
  label: string;
  windowSec: number;
  bucketSec: number;
}

// 每个时间窗对应的聚合粒度，保证状态条段数适中
export const WINDOW_OPTIONS: WindowOpt[] = [
  { label: "最近1小时", windowSec: 3600, bucketSec: 300 },   // 12段
  { label: "最近1天", windowSec: 86400, bucketSec: 3600 },   // 24段
  { label: "最近7天", windowSec: 604800, bucketSec: 21600 }, // 28段
];

export function useChannelMonitor() {
  const { accessToken, isAuthorized } = useAuthorized();
  const [buckets, setBuckets] = useState<ChannelBucket[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [windowSec, setWindowSec] = useState(WINDOW_OPTIONS[0].windowSec);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [bucketSec, setBucketSec] = useState(WINDOW_OPTIONS[0].bucketSec);

  const stateRef = useRef({ accessToken, isAuthorized, windowSec, bucketSec });
  stateRef.current = { accessToken, isAuthorized, windowSec, bucketSec };

  const load = useCallback(async () => {
    const { accessToken, isAuthorized, windowSec, bucketSec } = stateRef.current;
    if (!isAuthorized) return;
    setLoading(true);
    setError(null);
    const now = new Date();
    const start = new Date(now.getTime() - windowSec * 1000);
    const qs = new URLSearchParams({
      start_time: start.toISOString(),
      end_time: now.toISOString(),
      bucket_seconds: String(bucketSec),
    });
    try {
      const resp = await fetch(`/monitor/channel-summary?${qs.toString()}`, {
        headers: { Authorization: `Bearer ${accessToken ?? ""}` },
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const json = await resp.json();
      setBuckets(Array.isArray(json) ? json : []);
      setLastUpdated(new Date().toLocaleTimeString("zh-CN", { hour12: false }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const changeWindow = useCallback((opt: WindowOpt) => {
    setWindowSec(opt.windowSec);
    setBucketSec(opt.bucketSec);
  }, []);

  useEffect(() => {
    load();
  }, [load, isAuthorized, windowSec, bucketSec]);

  return { buckets, loading, error, refresh: load, windowSec, changeWindow, lastUpdated };
}
