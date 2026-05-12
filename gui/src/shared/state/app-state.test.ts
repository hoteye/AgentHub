import { describe, expect, it } from "vitest";

import { createMockBridgeClient } from "../../bridge/client.ts";
import { AppStateStore } from "./app-state.ts";

describe("app state store", () => {
  it("tracks running task lifecycle from bridge events", async () => {
    const client = createMockBridgeClient();
    const store = new AppStateStore();
    const unsubscribe = store.bindClient(client);

    await client.task.run({ text: "audit task" });
    unsubscribe();

    expect(store.getSnapshot().runningTaskCount).toBe(0);
    expect(store.getSnapshot().lastEvent?.kind).toBe("task_completed");
  });

  it("marks browser health ready after browser events", async () => {
    const client = createMockBridgeClient();
    const store = new AppStateStore();
    const unsubscribe = store.bindClient(client);

    await client.browser.snapshot({ target_id: "tab_1" });
    unsubscribe();

    expect(store.getSnapshot().lastEvent?.kind).toBe("tool_event");
    expect(store.getSnapshot().system.browser).toBe("warning");

    store.applyEvent({
      protocol_version: "v1",
      event_id: "evt_browser_ready",
      request_id: "req_browser_ready",
      kind: "browser_state_changed",
      name: "browser_snapshot",
      status: "ok",
      summary: "Browser updated",
      payload: {},
      ts: new Date().toISOString(),
    });

    expect(store.getSnapshot().system.browser).toBe("ready");
  });
});
