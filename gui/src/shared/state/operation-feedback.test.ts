import { describe, expect, it } from "vitest";

import { createBridgeFailure, createBridgeRequest, createBridgeSuccess } from "../types/bridge.ts";
import {
  errorFeedback,
  feedbackFromBridgeResponse,
  neutralFeedback,
  successFeedback,
  warningFeedback,
} from "./operation-feedback.ts";

describe("operation-feedback", () => {
  it("builds manual feedback helpers", () => {
    expect(neutralFeedback("idle")).toEqual({ level: "neutral", message: "idle" });
    expect(successFeedback("ok")).toEqual({ level: "success", message: "ok" });
    expect(warningFeedback("warn")).toEqual({ level: "warning", message: "warn" });
    expect(errorFeedback("boom")).toEqual({ level: "error", message: "boom" });
  });

  it("maps bridge responses into success and error feedback", () => {
    const request = createBridgeRequest("settings.get", {});
    const success = createBridgeSuccess(request, { model: "gpt-5.4" });
    expect(
      feedbackFromBridgeResponse(success, {
        successMessage: "已加载设置",
        errorMessage: "加载失败",
      }),
    ).toEqual({
      level: "success",
      message: "已加载设置",
    });

    const failure = createBridgeFailure(request, {
      code: "settings.get.failed",
      message: "backend unavailable",
      retryable: false,
    });
    expect(
      feedbackFromBridgeResponse(failure, {
        successMessage: "已加载设置",
        errorMessage: "加载失败",
      }),
    ).toEqual({
      level: "error",
      message: "backend unavailable",
    });
  });
});
