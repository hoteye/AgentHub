import { describe, expect, it } from "vitest";

import { createBridgeFailure, createBridgeRequest, createBridgeSuccess } from "../types/bridge.ts";
import { aggregateHealthLevels, summarizeBridgeCollection, summarizeCollectionHealth } from "./health-summary.ts";

describe("health-summary", () => {
  it("aggregates ready, warning, and error levels", () => {
    expect(aggregateHealthLevels(["ready", "ready"])).toBe("ready");
    expect(aggregateHealthLevels(["ready", "warning"])).toBe("warning");
    expect(aggregateHealthLevels(["ready", "error"])).toBe("error");
    expect(aggregateHealthLevels([])).toBe("warning");
  });

  it("summarizes collection health counts", () => {
    expect(
      summarizeCollectionHealth(["ready", "ready"], {
        label: "连接器",
        emptyDetail: "当前没有注册连接器",
      }),
    ).toMatchObject({
      level: "ready",
      detail: "2/2 连接器就绪",
    });

    expect(
      summarizeCollectionHealth(["ready", "warning"], {
        label: "插件",
        emptyDetail: "当前没有已加载插件",
      }),
    ).toMatchObject({
      level: "warning",
      detail: "1/2 插件就绪，1 降级",
    });
  });

  it("converts bridge failures into error summaries", () => {
    const request = createBridgeRequest("connector.list", {});
    const response = createBridgeFailure(request, {
      code: "connector.list.failed",
      message: "registry unavailable",
      retryable: false,
    });
    expect(
      summarizeBridgeCollection(
        response,
        [],
        (item: { health: string }) => item.health,
        {
          label: "连接器",
          emptyDetail: "当前没有注册连接器",
        },
      ),
    ).toMatchObject({
      level: "error",
      detail: "registry unavailable",
      failed: true,
    });
  });

  it("summarizes successful bridge collections", () => {
    const request = createBridgeRequest("plugin.list", {});
    const response = createBridgeSuccess(request, {
      plugins: [
        { plugin_id: "p1", title: "A", enabled: true, health: "ready" },
        { plugin_id: "p2", title: "B", enabled: false, health: "warning" },
      ],
    });
    expect(
      summarizeBridgeCollection(
        response,
        response.data?.plugins ?? [],
        (item) => item.health,
        {
          label: "插件",
          emptyDetail: "当前没有已加载插件",
        },
      ),
    ).toMatchObject({
      level: "warning",
      detail: "1/2 插件就绪，1 降级",
      failed: false,
    });
  });
});
