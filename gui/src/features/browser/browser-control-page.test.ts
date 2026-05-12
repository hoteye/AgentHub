import { describe, expect, it } from "vitest";

import { BridgeClient } from "../../bridge/client.ts";
import type { HostAdapter } from "../../shared/api/mock-host.ts";
import { createBridgeFailure, createBridgeSuccess, type BridgeEvent, type BridgeRequest } from "../../shared/types/bridge.ts";
import "./browser-control-page.ts";

async function flushUi(element: { updateComplete?: Promise<unknown> }) {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  await element.updateComplete;
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  await element.updateComplete;
}

function componentText(root: ShadowRoot, selector: string): string {
  const element = root.querySelector(selector) as HTMLElement & { shadowRoot?: ShadowRoot };
  return element?.shadowRoot?.textContent ?? "";
}

class FailingOpenAdapter implements HostAdapter {
  async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "browser.status") {
      return createBridgeSuccess(request, {
        running: true,
        activeProfile: "default",
        tabCount: 1,
      } as TData);
    }
    if (request.action === "browser.tabs") {
      return createBridgeSuccess(request, {
        tabs: [{ tab_id: "tab_1", title: "Dashboard", url: "https://example.test/dashboard" }],
      } as TData);
    }
    if (request.action === "browser.console") {
      return createBridgeSuccess(request, {
        entries: [{ level: "info", text: "browser ready" }],
      } as TData);
    }
    if (request.action === "browser.snapshot") {
      return createBridgeSuccess(request, {
        target_id: "tab_1",
        title: "Dashboard",
        refs: [{ ref: "a1", role: "button", text: "Run" }],
      } as TData);
    }
    if (request.action === "browser.open") {
      return createBridgeFailure(request, {
        code: "browser.open.failed",
        message: "blocked by policy",
        retryable: false,
      });
    }
    return createBridgeSuccess(request, {} as TData);
  }

  subscribe(_listener: (event: BridgeEvent<Record<string, unknown>>) => void) {
    return () => {};
  }
}

class RecordingBrowserAdapter implements HostAdapter {
  public requests: BridgeRequest<unknown>[] = [];

  async request<TData = unknown>(request: BridgeRequest<unknown>) {
    this.requests.push(request);
    if (request.action === "browser.status") {
      return createBridgeSuccess(request, {
        running: true,
        activeProfile: "default",
        tabCount: 1,
      } as TData);
    }
    if (request.action === "browser.tabs") {
      return createBridgeSuccess(request, {
        tabs: [{ tab_id: "tab_1", title: "Dashboard", url: "https://example.test/dashboard" }],
      } as TData);
    }
    if (request.action === "browser.console") {
      return createBridgeSuccess(request, {
        entries: [{ level: "info", text: "browser ready" }],
      } as TData);
    }
    if (request.action === "browser.snapshot") {
      return createBridgeSuccess(request, {
        target_id: "tab_1",
        title: "Dashboard",
        refs: [{ ref: "a1", role: "button", text: "Run" }],
      } as TData);
    }
    return createBridgeSuccess(request, {
      accepted: true,
      message: "ok",
      result: {},
    } as TData);
  }

  subscribe(_listener: (event: BridgeEvent<Record<string, unknown>>) => void) {
    return () => {};
  }
}

class OpenAliasLagAdapter implements HostAdapter {
  public requests: BridgeRequest<unknown>[] = [];
  private openRequested = false;
  private tabsCallsAfterOpen = 0;

  async request<TData = unknown>(request: BridgeRequest<unknown>) {
    this.requests.push(request);
    if (request.action === "browser.status") {
      return createBridgeSuccess(request, {
        running: true,
        activeProfile: "openclaw",
        tabCount: this.openRequested ? 1 : 1,
      } as TData);
    }
    if (request.action === "browser.tabs") {
      if (!this.openRequested) {
        return createBridgeSuccess(request, {
          tabs: [{ tab_id: "seed_tab", title: "Seed", url: "https://example.test/seed" }],
        } as TData);
      }
      this.tabsCallsAfterOpen += 1;
      if (this.tabsCallsAfterOpen < 2) {
        return createBridgeSuccess(request, { tabs: [] } as TData);
      }
      return createBridgeSuccess(request, {
        tabs: [{ tab_id: "tab_open_1", title: "Swag Labs", url: "https://www.saucedemo.com/" }],
      } as TData);
    }
    if (request.action === "browser.console") {
      return createBridgeSuccess(request, {
        entries: [{ level: "info", text: "browser ready" }],
      } as TData);
    }
    if (request.action === "browser.open") {
      this.openRequested = true;
      return createBridgeSuccess(request, {
        accepted: true,
        tab_id: "tab_open_1",
        url: "https://www.saucedemo.com/",
      } as TData);
    }
    if (request.action === "browser.snapshot") {
      const targetId = String((request.payload as { target_id?: string } | null)?.target_id ?? "seed_tab");
      if (targetId === "tab_open_1") {
        return createBridgeSuccess(request, {
          target_id: "tab_open_1",
          title: "Swag Labs",
          refs: [{ ref: "username", role: "textbox", text: "Username" }],
        } as TData);
      }
      return createBridgeSuccess(request, {
        target_id: "seed_tab",
        title: "Seed",
        refs: [{ ref: "seed", role: "button", text: "Seed Action" }],
      } as TData);
    }
    return createBridgeSuccess(request, { accepted: true } as TData);
  }

  subscribe(_listener: (event: BridgeEvent<Record<string, unknown>>) => void) {
    return () => {};
  }
}

class ProfileAwareStopAdapter implements HostAdapter {
  public requests: BridgeRequest<unknown>[] = [];
  private running = true;

  async request<TData = unknown>(request: BridgeRequest<unknown>) {
    this.requests.push(request);
    if (request.action === "browser.status") {
      return createBridgeSuccess(request, {
        running: this.running,
        activeProfile: "openclaw",
        tabCount: 1,
      } as TData);
    }
    if (request.action === "browser.tabs") {
      return createBridgeSuccess(request, {
        tabs: [{ tab_id: "tab_1", title: "Dashboard", url: "https://example.test/dashboard" }],
      } as TData);
    }
    if (request.action === "browser.console") {
      return createBridgeSuccess(request, {
        entries: [{ level: "info", text: "browser ready" }],
      } as TData);
    }
    if (request.action === "browser.snapshot") {
      return createBridgeSuccess(request, {
        target_id: "tab_1",
        title: "Dashboard",
        refs: [{ ref: "a1", role: "button", text: "Run" }],
      } as TData);
    }
    if (request.action === "browser.stop") {
      this.running = false;
      return createBridgeSuccess(request, { accepted: true, running: false } as TData);
    }
    return createBridgeSuccess(request, { accepted: true } as TData);
  }

  subscribe(_listener: (event: BridgeEvent<Record<string, unknown>>) => void) {
    return () => {};
  }
}

class ControlPlaneDiagnosticsAdapter implements HostAdapter {
  async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "browser.status") {
      return createBridgeSuccess(request, {
        running: true,
        activeProfile: "default",
        tabCount: 1,
      } as TData);
    }
    if (request.action === "browser.tabs") {
      return createBridgeSuccess(request, {
        tabs: [{ tab_id: "tab_1", title: "Control UI", url: "https://example.test/control" }],
      } as TData);
    }
    if (request.action === "browser.console") {
      return createBridgeSuccess(request, {
        entries: [{ level: "info", text: "browser ready" }],
      } as TData);
    }
    if (request.action === "browser.snapshot") {
      return createBridgeSuccess(request, {
        target_id: "tab_1",
        title: "Control UI",
        refs: [{ ref: "r1", role: "button", text: "Submit" }],
      } as TData);
    }
    if (request.action === "approval.list") {
      return createBridgeSuccess(request, {
        approvals: [
          {
            approval_id: "approval_1",
            title: "Browser submit",
            trace_id: "trace_1",
            status: "pending",
            risk: "medium",
          },
        ],
      } as TData);
    }
    if (request.action === "audit.list") {
      return createBridgeSuccess(request, {
        records: [
          {
            trace_id: "trace_1",
            stage: "approval",
            status: "pending",
            summary: "Awaiting approval",
            approval_id: "approval_1",
            action_id: "action_1",
          },
        ],
      } as TData);
    }
    return createBridgeSuccess(request, {} as TData);
  }

  async getControlUiBootstrap() {
    return {
      basePath: "/gui",
      assistantName: "AgentHub",
      assistantAvatar: "",
      assistantAgentId: "agenthub",
      serverVersion: "0.1.0",
      gateway: {
        methods: [],
        streams: ["gateway_events"],
      },
    };
  }

  async getControlUiState() {
    return {
      health: { status: "ok" },
      runtimePolicy: {},
      approvalStatus: {},
      events: [],
      workflowRuns: [],
      actionRequests: [],
      approvalTickets: [],
      auditRecords: [],
      diagnostics: {},
      connectors: [],
    };
  }

  async pollGatewayEvents() {
    return {
      cursor: 0,
      events: [],
    };
  }

  async browserProxy(request: { method: "GET" | "POST" | "DELETE"; path: string }) {
    if (request.path === "/profiles") {
      return {
        status: 200,
        result: {
          profiles: [{ profile: "default", active: true }],
        },
      };
    }
    if (request.path === "/requests") {
      return {
        status: 200,
        result: {
          entries: [
            {
              method: "POST",
              status: 202,
              url: "https://api.example.test/tasks",
              resource_type: "xhr",
              outcome: "accepted",
            },
          ],
        },
      };
    }
    if (request.path === "/errors") {
      return {
        status: 200,
        result: {
          entries: [
            {
              level: "error",
              source: "console",
              message: "Policy denied",
              url: "https://example.test/control",
            },
          ],
        },
      };
    }
    return {
      status: 200,
      result: {},
    };
  }

  subscribe(_listener: (event: BridgeEvent<Record<string, unknown>>) => void) {
    return () => {};
  }
}

describe("browser-control-page", () => {
  it("loads browser status, tabs, refs, and console", async () => {
    const element = document.createElement("browser-control-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("浏览器状态与页签");
    expect(element.shadowRoot.textContent).toContain("running=true");
    expect(element.shadowRoot.textContent).toContain("Dashboard");
    expect(element.shadowRoot.textContent).toContain("a1");
    expect(element.shadowRoot.textContent).toContain("browser ready");
  });

  it("opens and navigates tabs through browser controls", async () => {
    const element = document.createElement("browser-control-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const openInput = element.shadowRoot.querySelector("[data-testid='browser-open-url']") as HTMLInputElement;
    openInput.value = "https://example.test/reports";
    openInput.dispatchEvent(new Event("input"));
    const openButton = element.shadowRoot.querySelector("[data-testid='browser-open']") as HTMLButtonElement;
    openButton.click();
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("Reports");

    const navigateInput = element.shadowRoot.querySelector("[data-testid='browser-navigate-url']") as HTMLInputElement;
    navigateInput.value = "https://example.test/reports/daily";
    navigateInput.dispatchEvent(new Event("input"));
    const navigateButton = element.shadowRoot.querySelector("[data-testid='browser-navigate']") as HTMLButtonElement;
    navigateButton.click();
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("reports/daily");
    expect(componentText(element.shadowRoot, "[data-testid='browser-result-feedback']")).toContain("已导航到");
  });

  it("resolves tab_id aliases from open response and keeps open feedback stable while tabs sync", async () => {
    const adapter = new OpenAliasLagAdapter();
    const client = new BridgeClient(adapter);
    const element = document.createElement("browser-control-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);

    const openInput = element.shadowRoot.querySelector("[data-testid='browser-open-url']") as HTMLInputElement;
    openInput.value = "https://www.saucedemo.com/";
    openInput.dispatchEvent(new Event("input"));
    const openButton = element.shadowRoot.querySelector("[data-testid='browser-open']") as HTMLButtonElement;
    openButton.click();
    await new Promise((resolve) => setTimeout(resolve, 500));
    await flushUi(element);

    expect(componentText(element.shadowRoot, "[data-testid='browser-result-feedback']")).toContain("已打开 https://www.saucedemo.com/");
    expect(element.shadowRoot.textContent).toContain("Swag Labs");

    const snapshotButton = element.shadowRoot.querySelector("[data-testid='browser-snapshot']") as HTMLButtonElement;
    snapshotButton.click();
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("username");
    const snapshotRequest = adapter.requests
      .filter((item) => item.action === "browser.snapshot")
      .pop();
    expect((snapshotRequest?.payload as { target_id?: string } | undefined)?.target_id).toBe("tab_open_1");
  });

  it("executes browser actions and records artifact outputs", async () => {
    const element = document.createElement("browser-control-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const kindSelect = element.shadowRoot.querySelector("[data-testid='browser-action-kind']") as HTMLSelectElement;
    kindSelect.value = "type";
    kindSelect.dispatchEvent(new Event("change"));
    const refInput = element.shadowRoot.querySelector("[data-testid='browser-action-ref']") as HTMLInputElement;
    refInput.value = "b2";
    refInput.dispatchEvent(new Event("input"));
    const valueInput = element.shadowRoot.querySelector("[data-testid='browser-action-value']") as HTMLInputElement;
    valueInput.value = "agenthub";
    valueInput.dispatchEvent(new Event("input"));

    const actButton = element.shadowRoot.querySelector("[data-testid='browser-act']") as HTMLButtonElement;
    actButton.click();
    await flushUi(element);

    expect(componentText(element.shadowRoot, "[data-testid='browser-result-feedback']")).toContain("Typed into");

    const screenshotButton = element.shadowRoot.querySelector("[data-testid='browser-screenshot']") as HTMLButtonElement;
    screenshotButton.click();
    await flushUi(element);

    expect(componentText(element.shadowRoot, "[data-testid='browser-artifact-feedback']")).toContain("/tmp/");
  });

  it("supports advanced browser actions, download, upload, and dialog handling", async () => {
    const element = document.createElement("browser-control-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const kindSelect = element.shadowRoot.querySelector("[data-testid='browser-action-kind']") as HTMLSelectElement;
    kindSelect.value = "drag";
    kindSelect.dispatchEvent(new Event("change"));
    await flushUi(element);

    const refInput = element.shadowRoot.querySelector("[data-testid='browser-action-ref']") as HTMLInputElement;
    refInput.value = "a1";
    refInput.dispatchEvent(new Event("input"));
    const auxInput = element.shadowRoot.querySelector("[data-testid='browser-action-aux']") as HTMLInputElement;
    auxInput.value = "b2";
    auxInput.dispatchEvent(new Event("input"));
    const actButton = element.shadowRoot.querySelector("[data-testid='browser-act']") as HTMLButtonElement;
    actButton.click();
    await flushUi(element);

    expect(componentText(element.shadowRoot, "[data-testid='browser-result-feedback']")).toContain("Dragged");

    kindSelect.value = "fill";
    kindSelect.dispatchEvent(new Event("change"));
    await flushUi(element);
    const fillValue = element.shadowRoot.querySelector("[data-testid='browser-action-value']") as HTMLTextAreaElement;
    fillValue.value = '[{"ref":"b2","value":"agenthub"}]';
    fillValue.dispatchEvent(new Event("input"));
    actButton.click();
    await flushUi(element);

    expect(componentText(element.shadowRoot, "[data-testid='browser-result-feedback']")).toContain("Filled 1 field(s)");

    kindSelect.value = "press";
    kindSelect.dispatchEvent(new Event("change"));
    await flushUi(element);
    const keyValue = element.shadowRoot.querySelector("[data-testid='browser-action-value']") as HTMLInputElement;
    keyValue.value = "Enter";
    keyValue.dispatchEvent(new Event("input"));
    actButton.click();
    await flushUi(element);

    expect(componentText(element.shadowRoot, "[data-testid='browser-result-feedback']")).toContain("Pressed Enter");

    const downloadButton = element.shadowRoot.querySelector("[data-testid='browser-download']") as HTMLButtonElement;
    downloadButton.click();
    await flushUi(element);
    expect(componentText(element.shadowRoot, "[data-testid='browser-artifact-feedback']")).toContain("download");

    const uploadInput = element.shadowRoot.querySelector("[data-testid='browser-upload-paths']") as HTMLInputElement;
    uploadInput.value = "/tmp/a.txt,/tmp/b.txt";
    uploadInput.dispatchEvent(new Event("input"));
    const uploadButton = element.shadowRoot.querySelector("[data-testid='browser-upload']") as HTMLButtonElement;
    uploadButton.click();
    await flushUi(element);
    expect(componentText(element.shadowRoot, "[data-testid='browser-result-feedback']")).toContain("Uploaded 2 file(s)");

    const dialogToggle = element.shadowRoot.querySelector("[data-testid='browser-dialog-accept']") as HTMLInputElement;
    dialogToggle.checked = false;
    dialogToggle.dispatchEvent(new Event("change"));
    const dialogButton = element.shadowRoot.querySelector("[data-testid='browser-dialog']") as HTMLButtonElement;
    dialogButton.click();
    await flushUi(element);
    expect(componentText(element.shadowRoot, "[data-testid='browser-result-feedback']")).toContain("Dismissed dialog");
  });

  it("supports fill, press, and wait browser act variants", async () => {
    const element = document.createElement("browser-control-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const kindSelect = element.shadowRoot.querySelector("[data-testid='browser-action-kind']") as HTMLSelectElement;
    const refInput = element.shadowRoot.querySelector("[data-testid='browser-action-ref']") as HTMLInputElement;
    const actButton = element.shadowRoot.querySelector("[data-testid='browser-act']") as HTMLButtonElement;

    kindSelect.value = "fill";
    kindSelect.dispatchEvent(new Event("change"));
    await flushUi(element);
    const fillValue = element.shadowRoot.querySelector("[data-testid='browser-action-value']") as HTMLTextAreaElement;
    fillValue.value = "a1=alice@example.com;b2=123456";
    fillValue.dispatchEvent(new Event("input"));
    actButton.click();
    await flushUi(element);
    expect(componentText(element.shadowRoot, "[data-testid='browser-result-feedback']")).toContain("Filled 2 field(s)");

    kindSelect.value = "press";
    kindSelect.dispatchEvent(new Event("change"));
    await flushUi(element);
    refInput.value = "";
    refInput.dispatchEvent(new Event("input"));
    const pressValue = element.shadowRoot.querySelector("[data-testid='browser-action-value']") as HTMLInputElement;
    pressValue.value = "Enter";
    pressValue.dispatchEvent(new Event("input"));
    actButton.click();
    await flushUi(element);
    expect(componentText(element.shadowRoot, "[data-testid='browser-result-feedback']")).toContain("Pressed Enter");

    kindSelect.value = "wait";
    kindSelect.dispatchEvent(new Event("change"));
    await flushUi(element);
    const waitValue = element.shadowRoot.querySelector("[data-testid='browser-action-value']") as HTMLInputElement;
    waitValue.value = "250";
    waitValue.dispatchEvent(new Event("input"));
    actButton.click();
    await flushUi(element);
    expect(componentText(element.shadowRoot, "[data-testid='browser-result-feedback']")).toContain("Waited for 250ms");
  });

  it("exposes the extended browser action set and maps press to key payload", async () => {
    const adapter = new RecordingBrowserAdapter();
    const client = new BridgeClient(adapter);
    const element = document.createElement("browser-control-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);

    const kindSelect = element.shadowRoot.querySelector("[data-testid='browser-action-kind']") as HTMLSelectElement;
    const options = Array.from(kindSelect.options).map((item) => item.value);

    expect(options).toEqual(
      expect.arrayContaining(["double_click", "fill", "press", "focus", "check", "uncheck"]),
    );

    kindSelect.value = "press";
    kindSelect.dispatchEvent(new Event("change"));
    const refInput = element.shadowRoot.querySelector("[data-testid='browser-action-ref']") as HTMLInputElement;
    refInput.value = "a1";
    refInput.dispatchEvent(new Event("input"));
    const valueInput = element.shadowRoot.querySelector("[data-testid='browser-action-value']") as HTMLInputElement;
    valueInput.value = "Enter";
    valueInput.dispatchEvent(new Event("input"));

    const actButton = element.shadowRoot.querySelector("[data-testid='browser-act']") as HTMLButtonElement;
    actButton.click();
    await flushUi(element);

    const actRequests = adapter.requests.filter((item) => item.action === "browser.act");
    expect(actRequests).toHaveLength(1);
    expect(actRequests[0].payload).toMatchObject({
      action: "press",
      ref: "a1",
      key: "Enter",
    });
  });

  it("renders error feedback when browser action fails", async () => {
    const client = new BridgeClient(new FailingOpenAdapter());
    const element = document.createElement("browser-control-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);

    const openButton = element.shadowRoot.querySelector("[data-testid='browser-open']") as HTMLButtonElement;
    openButton.click();
    await flushUi(element);

    expect(componentText(element.shadowRoot, "[data-testid='browser-result-feedback']")).toContain("error");
    expect(componentText(element.shadowRoot, "[data-testid='browser-result-feedback']")).toContain("blocked by policy");
  });

  it("renders request/error diagnostics and causality hooks", async () => {
    const client = new BridgeClient(new ControlPlaneDiagnosticsAdapter());
    const element = document.createElement("browser-control-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("POST 202");
    expect(element.shadowRoot.textContent).toContain("Policy denied");
    expect(element.shadowRoot.textContent).toContain("Browser submit");
    expect(componentText(element.shadowRoot, "[data-testid='browser-causality-feedback']")).toContain("trace=trace_1");
  });

  it("uses active profile when issuing stop and converges to stopped runtime", async () => {
    const adapter = new ProfileAwareStopAdapter();
    const client = new BridgeClient(adapter);
    const element = document.createElement("browser-control-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);

    const stopButton = element.shadowRoot.querySelector("[data-testid='browser-stop']") as HTMLButtonElement;
    stopButton.click();
    await flushUi(element);

    const stopRequest = adapter.requests
      .filter((item) => item.action === "browser.stop")
      .pop();
    expect((stopRequest?.payload as { profile?: string } | undefined)?.profile).toBe("openclaw");
    expect(element.shadowRoot.textContent).toContain("running=false");
  });
});
