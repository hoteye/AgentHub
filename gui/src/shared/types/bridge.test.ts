import { describe, expect, it } from "vitest";

import { createBridgeRequest, normalizeBridgeEvent, toBridgeError } from "./bridge.ts";

describe("bridge types", () => {
  it("creates v1 requests with stable action metadata", () => {
    const request = createBridgeRequest("browser.snapshot", { target_id: "tab-1" }, { requestId: "req_fixed" });
    expect(request.protocol_version).toBe("v1");
    expect(request.request_id).toBe("req_fixed");
    expect(request.action).toBe("browser.snapshot");
  });

  it("normalizes partial events", () => {
    const event = normalizeBridgeEvent({
      request_id: "req_1",
      kind: "tool_event",
      name: "browser_snapshot",
    });
    expect(event.protocol_version).toBe("v1");
    expect(event.summary).toBe("browser_snapshot");
    expect(event.status).toBe("ok");
  });

  it("maps unknown errors into bridge errors", () => {
    const error = toBridgeError(new Error("boom"), "browser.snapshot.failed");
    expect(error.code).toBe("browser.snapshot.failed");
    expect(error.message).toBe("boom");
    expect(error.retryable).toBe(false);
  });
});
