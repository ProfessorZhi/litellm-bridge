"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { channelAvailability, groupByModel } from "./channelMonitorGroups";
import { useChannelMonitor, WINDOW_OPTIONS } from "./useChannelMonitor";

const NORMAL = 90; // ≥90% 绿
const WARN = 50; // 50-90% 黄

function healthColor(pct: number | null): string {
  if (pct == null) return "bg-muted"; // 无数据
  if (pct >= NORMAL) return "bg-emerald-500";
  if (pct >= WARN) return "bg-amber-500";
  return "bg-red-600";
}
function ringColor(pct: number): string {
  if (pct >= NORMAL) return "#10b981";
  if (pct >= WARN) return "#f59e0b";
  return "#dc2626";
}
function fmtPct(p: number | null): string {
  return p == null ? "-" : p.toFixed(1) + "%";
}
function fmtSec(ms: number | null): string {
  if (ms == null) return "-";
  return ms >= 1000 ? (ms / 1000).toFixed(1) + "s" : Math.round(ms) + "ms";
}

function Donut({ pct }: { pct: number | null }) {
  const r = 30;
  const c = 2 * Math.PI * r;
  const val = pct ?? 0;
  const dash = (val / 100) * c;
  return (
    <div className="relative h-20 w-20 shrink-0">
      <svg viewBox="0 0 80 80" className="h-20 w-20 -rotate-90">
        <circle cx="40" cy="40" r={r} fill="none" strokeWidth="8" className="stroke-muted" />
        <circle
          cx="40" cy="40" r={r} fill="none" strokeWidth="8"
          stroke={ringColor(val)} strokeLinecap="round"
          strokeDasharray={`${dash} ${c}`}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center text-sm font-bold">
        {pct == null ? "暂无" : fmtPct(pct)}
      </div>
    </div>
  );
}

export default function ChannelMonitorPage() {
  const { buckets, loading, error, refresh, windowSec, changeWindow, lastUpdated } = useChannelMonitor();
  const now = Date.now();
  const bucketSec = WINDOW_OPTIONS.find((o) => o.windowSec === windowSec)?.bucketSec ?? 300;
  const numSeg = Math.floor(windowSec / bucketSec);
  const groups = groupByModel(buckets, windowSec, bucketSec, now);

  // 桶落在窗口外说明后端时间与窗口对不上，格子会静默缺失
  if (process.env.NODE_ENV !== "production") {
    const dropped = groups.reduce((n, g) => n + g.droppedBuckets, 0);
    if (dropped > 0) console.warn(`channel-monitor: ${dropped} 个桶落在窗口外，未渲染`);
  }

  const Stat = ({ label, value, color }: { label: string; value: string | number; color?: string }) => (
    <div className="flex flex-col items-center rounded bg-muted/40 px-2 py-2">
      <span className={`text-sm font-semibold ${color ?? "text-foreground"}`}>{value}</span>
      <span className="text-[11px] text-muted-foreground">{label}</span>
    </div>
  );

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">模型健康监控</h1>
          <p className="text-sm text-muted-foreground">按模型查看渠道可用率、延迟与请求</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={windowSec}
            onChange={(e) => {
              const opt = WINDOW_OPTIONS.find((o) => o.windowSec === Number(e.target.value));
              if (opt) changeWindow(opt);
            }}
            className="rounded border bg-background px-3 py-1 pr-9 text-sm min-w-[9.5rem]"
          >
            {WINDOW_OPTIONS.map((o) => (
              <option key={o.windowSec} value={o.windowSec}>{o.label}</option>
            ))}
          </select>
          <span className="text-xs text-muted-foreground whitespace-nowrap">
            最后更新 {lastUpdated ?? "--:--:--"}
          </span>
          <Button onClick={() => refresh()} disabled={loading}>刷新</Button>
        </div>
      </div>

      {error && <p className="text-destructive">加载失败: {error}</p>}
      {loading && groups.length === 0 && <p className="text-muted-foreground">加载中…</p>}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {groups.map((g) => {
          // 分母是 成功+渠道失败，不是总请求：用户侧失败(401/402/403 等)不算渠道不可用
          const avail = channelAvailability(g);
          return (
            <Card key={g.model} className="overflow-hidden">
              {/* 顶部状态色条 */}
              <div className={`h-1 ${avail == null ? "bg-muted" : avail >= NORMAL ? "bg-emerald-500" : avail >= WARN ? "bg-amber-500" : "bg-red-600"}`} />
              <CardHeader className="border-b px-4 py-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">{g.model}</CardTitle>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                    avail == null ? "bg-muted text-muted-foreground" :
                    avail >= NORMAL ? "bg-emerald-100 text-emerald-700" :
                    avail >= WARN ? "bg-amber-100 text-amber-700" : "bg-red-100 text-red-700"
                  }`}>
                    {avail == null ? "暂无数据" : avail >= NORMAL ? "健康" : avail >= WARN ? "警告" : "异常"}
                  </span>
                </div>
              </CardHeader>
              <CardContent className="p-4">
                <div className="flex items-center gap-4">
                  <Donut pct={avail} />
                  <div className="grid flex-1 grid-cols-2 gap-2">
                    <Stat label="总请求" value={g.total} />
                    {/* 失败请求 = 全部 status='failure'；渠道失败 = 其中排除可证明属调用方责任的部分 */}
                    <Stat label="失败请求" value={g.failed} color={g.failed > 0 ? "text-red-600" : undefined} />
                    <Stat label="响应时间" value={fmtSec(g.latency)} />
                    <Stat label="首token" value={fmtSec(g.ttft)} />
                    <Stat label="总token" value={fmtToken(g.totalTokens)} />
                    <Stat label="渠道失败" value={g.channelFailed} color={g.channelFailed > 0 ? "text-red-600" : undefined} />
                  </div>
                </div>

                {/* 渠道可用率时间条 */}
                <div className="mt-4">
                  <div className="text-[11px] text-muted-foreground">
                    渠道可用率 {fmtPct(avail)}
                  </div>
                  <div className="mt-1 flex gap-[2px]">
                    {Array.from({ length: numSeg }).map((_, i) => {
                      const seg = g.slots[i];
                      const pct = seg && seg.health != null ? seg.health * 100 : null;
                      return (
                        <div
                          key={i}
                          title={seg ? `${new Date(seg.t).toLocaleTimeString()}: ${fmtPct(pct)}` : "无数据"}
                          className={`h-4 flex-1 rounded-sm ${healthColor(pct)}`}
                        />
                      );
                    })}
                  </div>
                  <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
                    <span>{fmtTime(now - windowSec * 1000)}</span>
                    <span>{fmtTime(now)}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* 图例 */}
      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1"><span className="h-3 w-3 rounded-sm bg-emerald-500" />正常 ≥{NORMAL}%</span>
        <span className="flex items-center gap-1"><span className="h-3 w-3 rounded-sm bg-amber-500" />警告 {WARN}-{NORMAL}%</span>
        <span className="flex items-center gap-1"><span className="h-3 w-3 rounded-sm bg-red-600" />异常 &lt;{WARN}%</span>
        <span className="flex items-center gap-1"><span className="h-3 w-3 rounded-sm bg-muted" />无数据</span>
      </div>
    </div>
  );
}

function fmtToken(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "k";
  return String(n);
}

function fmtTime(ts: number): string {
  const d = new Date(ts);
  const h = d.getHours().toString().padStart(2, "0");
  const m = d.getMinutes().toString().padStart(2, "0");
  const mo = (d.getMonth() + 1).toString().padStart(2, "0");
  const dd = d.getDate().toString().padStart(2, "0");
  return `${mo}-${dd} ${h}:${m}`;
}
