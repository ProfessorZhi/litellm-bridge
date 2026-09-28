import { describe, expect, it } from "vitest";

import { channelAvailability, groupByModel } from "./channelMonitorGroups";
import type { ChannelBucket } from "./useChannelMonitor";

const NOW = Date.parse("2026-09-28T05:42:00Z");
const WINDOW_SEC = 3600;
const BUCKET_SEC = 300;
const NUM_SEG = WINDOW_SEC / BUCKET_SEC;

function bucket(overrides: Partial<ChannelBucket> = {}): ChannelBucket {
  return {
    bucket: new Date(NOW - 300_000).toISOString(),
    model_group: "glm-5.3",
    total_requests: 0,
    success_requests: 0,
    failed_requests: 0,
    other_requests: 0,
    client_failures: 0,
    channel_failures: 0,
    upstream_failures: 0,
    transport_failures: 0,
    unclassified_failures: 0,
    avg_latency_ms: null,
    avg_ttft_ms: null,
    p50_ms: null,
    p95_ms: null,
    total_tokens: 0,
    prompt_tokens: 0,
    completion_tokens: 0,
    health: 0,
    ...overrides,
  };
}

function atOffset(ms: number): string {
  return new Date(NOW + ms).toISOString();
}

describe("groupByModel slot placement", () => {
  it("places the newest bucket at the last segment", () => {
    const groups = groupByModel([bucket({ bucket: atOffset(-60_000) })], WINDOW_SEC, BUCKET_SEC, NOW);
    expect(groups[0].slots).toHaveLength(NUM_SEG);
    expect(groups[0].slots[NUM_SEG - 1]?.t).toBe(Date.parse(atOffset(-60_000)));
    expect(groups[0].slots[0]).toBeNull();
  });

  it("drops a bucket 8 hours ahead of the window instead of filling a ghost segment", () => {
    const groups = groupByModel([bucket({ bucket: atOffset(8 * 3600_000) })], WINDOW_SEC, BUCKET_SEC, NOW);
    expect(groups[0].slots).toHaveLength(NUM_SEG);
    expect(groups[0].slots.every((slot) => slot === null)).toBe(true);
    expect(groups[0].droppedBuckets).toBe(1);
  });

  it("drops a bucket that falls before the window", () => {
    const groups = groupByModel([bucket({ bucket: atOffset(-3600_000 - 300_000) })], WINDOW_SEC, BUCKET_SEC, NOW);
    expect(groups[0].droppedBuckets).toBe(1);
  });

  it("ignores a null bucket without dropping or misplacing anything", () => {
    const groups = groupByModel(
      [bucket({ bucket: null, total_requests: 0 }), bucket({ bucket: atOffset(-60_000), total_requests: 5, success_requests: 5, health: 1 })],
      WINDOW_SEC,
      BUCKET_SEC,
      NOW,
    );
    expect(groups[0].slots).toHaveLength(NUM_SEG);
    expect(groups[0].droppedBuckets).toBe(0);
    expect(groups[0].slots[NUM_SEG - 1]?.health).toBe(1);
  });

  it("ignores the literal string None the backend used to emit for empty buckets", () => {
    const groups = groupByModel(
      [bucket({ bucket: "None" })],
      WINDOW_SEC,
      BUCKET_SEC,
      NOW,
    );
    expect(groups[0].slots).toHaveLength(NUM_SEG);
    expect(groups[0].slots.every((slot) => slot === null)).toBe(true);
    expect(groups[0].droppedBuckets).toBe(0);
    expect(Object.keys(groups[0].slots)).toHaveLength(NUM_SEG);
  });

  it("marks a bucket with no requests as no-data rather than healthy", () => {
    const groups = groupByModel(
      [bucket({ total_requests: 0, success_requests: 0, channel_failures: 0, health: 1 })],
      WINDOW_SEC,
      BUCKET_SEC,
      NOW,
    );
    expect(groups[0].slots[NUM_SEG - 1]?.health).toBeNull();
  });

  it("keys groups by model_group and keeps them separate", () => {
    const groups = groupByModel(
      [
        bucket({ model_group: "glm-5.3", total_requests: 3, success_requests: 3 }),
        bucket({ model_group: "gpt-5.6-luna", total_requests: 7, success_requests: 7 }),
      ],
      WINDOW_SEC,
      BUCKET_SEC,
      NOW,
    );
    expect(groups.map((g) => g.model).sort()).toEqual(["glm-5.3", "gpt-5.6-luna"]);
    expect(groups.find((g) => g.model === "glm-5.3")?.total).toBe(3);
  });
});

describe("groupByModel totals", () => {
  it("sums the four request counts independently so other requests stay visible", () => {
    const groups = groupByModel(
      [
        bucket({ total_requests: 100, success_requests: 90, failed_requests: 8, other_requests: 2, client_failures: 5, channel_failures: 3 }),
        bucket({ total_requests: 50, success_requests: 45, failed_requests: 5, other_requests: 0, client_failures: 1, channel_failures: 4 }),
      ],
      WINDOW_SEC,
      BUCKET_SEC,
      NOW,
    );
    expect(groups[0].total).toBe(150);
    expect(groups[0].success).toBe(135);
    expect(groups[0].failed).toBe(13);
    expect(groups[0].clientFailed).toBe(6);
    expect(groups[0].channelFailed).toBe(7);
    expect(groups[0].totalTokens).toBe(0);
  });

  it("weights latency and ttft only by buckets that reported one", () => {
    const groups = groupByModel(
      [
        bucket({ avg_latency_ms: 1000, avg_ttft_ms: 100 }),
        bucket({ avg_latency_ms: null, avg_ttft_ms: null }),
        bucket({ avg_latency_ms: 2000, avg_ttft_ms: 300 }),
      ],
      WINDOW_SEC,
      BUCKET_SEC,
      NOW,
    );
    expect(groups[0].latency).toBe(1500);
    expect(groups[0].ttft).toBe(200);
  });

  it("reports no latency at all when no bucket reported one", () => {
    const groups = groupByModel([bucket(), bucket()], WINDOW_SEC, BUCKET_SEC, NOW);
    expect(groups[0].latency).toBeNull();
    expect(groups[0].ttft).toBeNull();
  });
});

describe("channelAvailability", () => {
  it("divides by success plus channel failures, not by total requests", () => {
    const groups = groupByModel(
      [bucket({ total_requests: 1000, success_requests: 900, failed_requests: 50, other_requests: 50, client_failures: 40, channel_failures: 10 })],
      WINDOW_SEC,
      BUCKET_SEC,
      NOW,
    );
    expect(channelAvailability(groups[0])).toBeCloseTo(98.9, 1);
    expect(channelAvailability(groups[0])).not.toBeCloseTo(90, 0);
  });

  it("is 100 percent when the only failures are provably caller-caused", () => {
    const groups = groupByModel(
      [bucket({ total_requests: 100, success_requests: 90, failed_requests: 10, client_failures: 10, channel_failures: 0 })],
      WINDOW_SEC,
      BUCKET_SEC,
      NOW,
    );
    expect(channelAvailability(groups[0])).toBe(100);
  });

  it("counts unclassified failures against availability by construction", () => {
    const groups = groupByModel(
      [bucket({ total_requests: 100, success_requests: 95, failed_requests: 5, client_failures: 0, channel_failures: 5, unclassified_failures: 5 })],
      WINDOW_SEC,
      BUCKET_SEC,
      NOW,
    );
    expect(channelAvailability(groups[0])).toBe(95);
  });

  it("is null rather than 100 percent when there is no traffic", () => {
    const groups = groupByModel([bucket()], WINDOW_SEC, BUCKET_SEC, NOW);
    expect(channelAvailability(groups[0])).toBeNull();
  });
});
