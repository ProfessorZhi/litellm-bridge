import type { ChannelBucket } from "./useChannelMonitor";

export interface BucketSlot {
  t: number;
  health: number | null;
}

export interface Group {
  model: string;
  total: number;
  success: number;
  failed: number;
  clientFailed: number;
  channelFailed: number;
  latency: number | null;
  ttft: number | null;
  totalTokens: number;
  /** 定长 numSeg，空位为 null，下标越界的桶不落格 */
  slots: (BucketSlot | null)[];
  /** 落在窗口外的桶数；非 0 说明后端桶时间与窗口对不上 */
  droppedBuckets: number;
}

/** 渠道可用率 = success / (success + channel_failures)，分母不是 total */
export function channelAvailability(g: Pick<Group, "success" | "channelFailed">): number | null {
  const denominator = g.success + g.channelFailed;
  return denominator > 0 ? (g.success / denominator) * 100 : null;
}

interface Accumulator {
  model: string;
  total: number;
  success: number;
  failed: number;
  clientFailed: number;
  channelFailed: number;
  latencySum: number;
  latencyCount: number;
  ttftSum: number;
  ttftCount: number;
  totalTokens: number;
  slots: (BucketSlot | null)[];
  droppedBuckets: number;
}

export function groupByModel(
  buckets: ChannelBucket[],
  windowSec: number,
  bucketSec: number,
  now: number,
): Group[] {
  const numSeg = Math.floor(windowSec / bucketSec);
  const segMs = bucketSec * 1000;
  const byModel = new Map<string, Accumulator>();

  for (const b of buckets) {
    const model = b.model_group || "unk";
    let acc = byModel.get(model);
    if (!acc) {
      acc = {
        model,
        total: 0,
        success: 0,
        failed: 0,
        clientFailed: 0,
        channelFailed: 0,
        latencySum: 0,
        latencyCount: 0,
        ttftSum: 0,
        ttftCount: 0,
        totalTokens: 0,
        slots: Array<BucketSlot | null>(numSeg).fill(null),
        droppedBuckets: 0,
      };
      byModel.set(model, acc);
    }

    acc.total += b.total_requests;
    acc.success += b.success_requests;
    acc.failed += b.failed_requests;
    acc.clientFailed += b.client_failures;
    acc.channelFailed += b.channel_failures;
    acc.totalTokens += b.total_tokens;
    if (b.avg_latency_ms != null) {
      acc.latencySum += b.avg_latency_ms;
      acc.latencyCount += 1;
    }
    if (b.avg_ttft_ms != null) {
      acc.ttftSum += b.avg_ttft_ms;
      acc.ttftCount += 1;
    }

    if (!b.bucket) continue;
    const t = new Date(b.bucket).getTime();
    if (!Number.isFinite(t)) continue;
    const idx = numSeg - 1 - Math.floor((now - t) / segMs);
    if (idx < 0 || idx >= numSeg) {
      acc.droppedBuckets += 1;
      continue;
    }
    acc.slots[idx] = { t, health: b.total_requests > 0 ? b.health : null };
  }

  return Array.from(byModel.values(), (acc) => ({
    model: acc.model,
    total: acc.total,
    success: acc.success,
    failed: acc.failed,
    clientFailed: acc.clientFailed,
    channelFailed: acc.channelFailed,
    latency: acc.latencyCount > 0 ? acc.latencySum / acc.latencyCount : null,
    ttft: acc.ttftCount > 0 ? acc.ttftSum / acc.ttftCount : null,
    totalTokens: acc.totalTokens,
    slots: acc.slots,
    droppedBuckets: acc.droppedBuckets,
  }));
}
