import { beforeEach, describe, expect, it } from "vitest";

import "./app-shell.ts";

async function flushShell(element: { updateComplete?: Promise<unknown> }) {
  await Promise.resolve();
  await Promise.resolve();
  await element.updateComplete;
  await Promise.resolve();
  await element.updateComplete;
}

describe("agenthub-app", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/");
    document.body.innerHTML = "";
  });

  it("renders all top-level routes", async () => {
    window.history.pushState({}, "", "/");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const nav = element.shadowRoot.querySelector("sidebar-nav") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    expect(nav).toBeTruthy();
    await nav.updateComplete;

    const buttons = nav.shadowRoot.querySelectorAll("button[data-route]");
    expect(buttons.length).toBe(14);
    expect(nav.shadowRoot.textContent).toContain("Chat");
    expect(nav.shadowRoot.textContent).toContain("Control");
    expect(nav.shadowRoot.textContent).toContain("Agent");
    expect(nav.shadowRoot.textContent).toContain("Settings");
    expect(nav.shadowRoot.textContent).toContain("工作台");
    expect(nav.shadowRoot.textContent).toContain("Codex UI");
    expect(nav.shadowRoot.textContent).toContain("浏览器控制");
    expect(nav.shadowRoot.textContent).toContain("Logs");
    expect(nav.shadowRoot.textContent).toContain("Config");
    expect(nav.shadowRoot.textContent).toContain("Debug");
    expect(nav.shadowRoot.textContent).toContain("Channels");
    expect(nav.shadowRoot.textContent).toContain("Nodes / Devices");
    expect(nav.shadowRoot.textContent).toContain("插件与连接器");
    expect(nav.shadowRoot.textContent).toContain("Sessions / Runs");
    expect(nav.shadowRoot.textContent).toContain("Auth / Scope");
  });

  it("switches route when sidebar emits route-change", async () => {
    window.history.pushState({}, "", "/");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const nav = element.shadowRoot.querySelector("sidebar-nav");
    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "settings",
        bubbles: true,
        composed: true,
      }),
    );
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("settings");
    expect(element.shadowRoot.textContent).toContain("设置");
  });

  it("renders channels route through routed shell", async () => {
    window.history.pushState({}, "", "/channels");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("channels");
    expect(element.shadowRoot.textContent).toContain("Channels");
    expect(element.shadowRoot.querySelector("channels-operator-page")).toBeTruthy();
  });

  it("renders codex route as a fullscreen Codex surface", async () => {
    window.history.pushState({}, "", "/codex");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("codex");
    expect(element.shadowRoot.querySelector("sidebar-nav")).toBeFalsy();
    expect(element.shadowRoot.querySelector("codex-native-webview-page")).toBeTruthy();
  });

  it("renders logs route through routed shell", async () => {
    window.history.pushState({}, "", "/logs");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("logs");
    expect(element.shadowRoot.textContent).toContain("Logs");
    expect(element.shadowRoot.querySelector("logs-operator-page")).toBeTruthy();
  });

  it("renders config route through routed shell", async () => {
    window.history.pushState({}, "", "/config");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("config");
    expect(element.shadowRoot.textContent).toContain("Config");
    const settingsPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      surfaceMode?: string;
    };
    expect(settingsPage.surfaceMode).toBe("config");
  });

  it("renders debug route through routed shell", async () => {
    window.history.pushState({}, "", "/debug");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("debug");
    expect(element.shadowRoot.textContent).toContain("Debug");
    const settingsPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      surfaceMode?: string;
    };
    expect(settingsPage.surfaceMode).toBe("debug");
  });

  it("renders nodes route through routed shell", async () => {
    window.history.pushState({}, "", "/nodes");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("nodes");
    expect(element.shadowRoot.textContent).toContain("Nodes / Devices");
    expect(element.shadowRoot.querySelector("nodes-devices-page")).toBeTruthy();
  });

  it("renders auth route through routed shell", async () => {
    window.history.pushState({}, "", "/");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const nav = element.shadowRoot.querySelector("sidebar-nav");
    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "auth",
        bubbles: true,
        composed: true,
      }),
    );
    await Promise.resolve();
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("auth");
    expect(element.shadowRoot.textContent).toContain("Auth / Scope");
    const settingsPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      surfaceMode?: string;
    };
    expect(settingsPage.surfaceMode).toBe("auth");
  });

  it("routes auth surface quick links into operator pages", async () => {
    window.history.pushState({}, "", "/auth");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const settingsPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await flushShell(settingsPage);

    const openBrowser = settingsPage.shadowRoot.querySelector(
      "[data-testid='gateway-route-open-browser']",
    ) as HTMLButtonElement;
    openBrowser.click();
    await Promise.resolve();
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("browser");
    expect(element.shadowRoot.querySelector("browser-control-page")).toBeTruthy();
  });

  it("routes auth connector handoff into plugins context", async () => {
    window.history.pushState({}, "", "/auth");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const settingsPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await flushShell(settingsPage);

    const openPlugins = settingsPage.shadowRoot.querySelector(
      "[data-testid='gateway-auth-connector-open-plugins']",
    ) as HTMLButtonElement;
    openPlugins.click();
    await Promise.resolve();
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("plugins");
    const pluginsPage = element.shadowRoot.querySelector("plugins-connectors-page") as HTMLElement & {
      initialSelectedConnectorKey?: string;
      initialConnectorFilter?: string;
      initialContextSource?: string;
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    expect(pluginsPage.initialSelectedConnectorKey).toBe("github_webhook");
    expect(pluginsPage.initialConnectorFilter).toBe("gateway");
    expect(pluginsPage.initialContextSource).toBe("settings-auth-connectors");
    await flushShell(pluginsPage);
    expect(pluginsPage.shadowRoot.textContent).toContain("github_webhook");
  });

  it("routes auth connector handoff into settings context", async () => {
    window.history.pushState({}, "", "/auth");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const settingsPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await flushShell(settingsPage);

    const openSettings = settingsPage.shadowRoot.querySelector(
      "[data-testid='gateway-auth-connector-open-settings']",
    ) as HTMLButtonElement;
    openSettings.click();
    await Promise.resolve();
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("settings");
    const fullSettingsPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      initialAuthConnectorKey?: string;
      initialAuthConnectorFilter?: string;
      initialContextSource?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    expect(fullSettingsPage.initialAuthConnectorKey).toBe("github_webhook");
    expect(fullSettingsPage.initialAuthConnectorFilter).toBe("gateway");
    expect(fullSettingsPage.initialContextSource).toBe("settings-auth-connectors");
    await flushShell(fullSettingsPage);
    expect(fullSettingsPage.shadowRoot.textContent).toContain("GitHub Webhook");
  });

  it("routes settings log handoff into logs context", async () => {
    window.history.pushState({}, "", "/settings");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const settingsPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await flushShell(settingsPage);

    const openLogs = settingsPage.shadowRoot.querySelector(
      "[data-testid='settings-log-route-open-logs']",
    ) as HTMLButtonElement;
    openLogs.click();
    await Promise.resolve();
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("logs");
    const logsPage = element.shadowRoot.querySelector("logs-operator-page") as HTMLElement & {
      initialSelectedSource?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    expect(logsPage.initialSelectedSource).toBe("gateway.audit_records");
    await flushShell(logsPage);
    expect(logsPage.shadowRoot.textContent).toContain("Gateway Audit Records");
  });

  it("routes auth connector handoff into approvals landing context", async () => {
    window.history.pushState({}, "", "/auth");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const settingsPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await flushShell(settingsPage);

    const openApprovals = settingsPage.shadowRoot.querySelector(
      "[data-testid='gateway-auth-connector-open-approvals']",
    ) as HTMLButtonElement;
    openApprovals.click();
    await Promise.resolve();
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("approvals");
    const approvalsPage = element.shadowRoot.querySelector("approvals-audit-page") as HTMLElement & {
      initialConnectorKey?: string;
      initialContextSource?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    expect(approvalsPage.initialConnectorKey).toBe("github_webhook");
    expect(approvalsPage.initialContextSource).toBe("settings-auth-connectors");
    await flushShell(approvalsPage);
    expect(approvalsPage.shadowRoot.textContent).toContain("connector=github_webhook");
  });

  it("routes plugins connector handoff back into auth context", async () => {
    window.history.pushState({}, "", "/plugins");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const pluginsPage = element.shadowRoot.querySelector("plugins-connectors-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await flushShell(pluginsPage);

    const selectDispatch = pluginsPage.shadowRoot.querySelector(
      "[data-testid='connector-select-github_dispatch']",
    ) as HTMLButtonElement;
    selectDispatch.click();
    await flushShell(pluginsPage);

    const openAuth = pluginsPage.shadowRoot.querySelector(
      "[data-testid='connector-open-auth-surface']",
    ) as HTMLButtonElement;
    openAuth.click();
    await Promise.resolve();
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("auth");
    const settingsPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      initialAuthConnectorKey?: string;
      initialAuthConnectorFilter?: string;
      initialContextSource?: string;
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    expect(settingsPage.initialAuthConnectorKey).toBe("github_dispatch");
    expect(settingsPage.initialAuthConnectorFilter).toBe("approval");
    expect(settingsPage.initialContextSource).toBe("plugins-connectors");
    await flushShell(settingsPage);
    expect(settingsPage.shadowRoot.textContent).toContain("GitHub Dispatch");
  });

  it("routes plugins connector detail into settings surface", async () => {
    window.history.pushState({}, "", "/plugins");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const pluginsPage = element.shadowRoot.querySelector("plugins-connectors-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await flushShell(pluginsPage);

    const openSettings = pluginsPage.shadowRoot.querySelector(
      "[data-testid='connector-open-settings-surface']",
    ) as HTMLButtonElement;
    openSettings.click();
    await Promise.resolve();
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("settings");
    const settingsPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      initialAuthConnectorKey?: string;
      initialAuthConnectorFilter?: string;
      initialContextSource?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    expect(settingsPage).toBeTruthy();
    expect(settingsPage.initialAuthConnectorKey).toBe("github_webhook");
    expect(settingsPage.initialAuthConnectorFilter).toBe("gateway");
    expect(settingsPage.initialContextSource).toBe("plugins-connectors");
    await flushShell(settingsPage);
    expect(settingsPage.shadowRoot.textContent).toContain("GitHub Webhook");
  });

  it("routes plugins connector detail into approvals landing context", async () => {
    window.history.pushState({}, "", "/plugins");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const pluginsPage = element.shadowRoot.querySelector("plugins-connectors-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await flushShell(pluginsPage);

    const openApprovals = pluginsPage.shadowRoot.querySelector(
      "[data-testid='connector-open-approvals-surface']",
    ) as HTMLButtonElement;
    openApprovals.click();
    await Promise.resolve();
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("approvals");
    const approvalsPage = element.shadowRoot.querySelector("approvals-audit-page") as HTMLElement & {
      initialConnectorKey?: string;
      initialContextSource?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    expect(approvalsPage.initialConnectorKey).toBe("github_webhook");
    expect(approvalsPage.initialContextSource).toBe("plugins-connectors");
    await flushShell(approvalsPage);
    expect(approvalsPage.shadowRoot.textContent).toContain("connector=github_webhook");
  });

  it("routes approvals connector landing back into auth context", async () => {
    window.history.pushState({}, "", "/approvals");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const approvalsPage = element.shadowRoot.querySelector("approvals-audit-page") as HTMLElement & {
      initialConnectorKey?: string;
      initialContextSource?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    approvalsPage.initialConnectorKey = "github_webhook";
    approvalsPage.initialContextSource = "plugins-connectors";
    await flushShell(approvalsPage);

    const openAuth = approvalsPage.shadowRoot.querySelector(
      "[data-testid='approvals-open-auth']",
    ) as HTMLButtonElement;
    openAuth.click();
    await Promise.resolve();
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("auth");
    const settingsPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      initialAuthConnectorKey?: string;
      initialContextSource?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    expect(settingsPage.initialAuthConnectorKey).toBe("github_webhook");
    expect(settingsPage.initialContextSource).toBe("approvals-context");
  });

  it("navigates to chat when warp workbench routes to chat", async () => {
    window.history.pushState({}, "", "/");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const workbench = element.shadowRoot.querySelector("warp-workbench-page");
    workbench?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "chat",
        bubbles: true,
        composed: true,
      }),
    );
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("chat");
    expect(element.shadowRoot.textContent).toContain("对话与任务");
  });

  it("routes warp workbench route changes into approvals", async () => {
    window.history.pushState({}, "", "/");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const workbench = element.shadowRoot.querySelector("warp-workbench-page");
    workbench?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "approvals",
        bubbles: true,
        composed: true,
      }),
    );
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("approvals");
    expect(element.shadowRoot.querySelector("approvals-audit-page")).toBeTruthy();
  });

  it("routes nodes control navigation into sessions context", async () => {
    window.history.pushState({}, "", "/nodes");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const nodesPage = element.shadowRoot.querySelector("nodes-devices-page");
    nodesPage?.dispatchEvent(
      new CustomEvent("navigate-control-context", {
        detail: {
          route: "sessions",
          traceId: "trace_pair_1",
          source: "nodes-pairing",
        },
        bubbles: true,
        composed: true,
      }),
    );
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("sessions");
    const sessionsPage = element.shadowRoot.querySelector("sessions-runs-trace-page") as HTMLElement & {
      initialTraceId?: string;
    };
    expect(sessionsPage.initialTraceId).toBe("trace_pair_1");
  });

  it("renders approvals and plugins pages through routed shell", async () => {
    window.history.pushState({}, "", "/");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const nav = element.shadowRoot.querySelector("sidebar-nav");
    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "approvals",
        bubbles: true,
        composed: true,
      }),
    );
    await Promise.resolve();
    await element.updateComplete;
    expect(element.shadowRoot.textContent).toContain("审批与审计");
    expect(element.shadowRoot.querySelector("approvals-audit-page")).toBeTruthy();

    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "plugins",
        bubbles: true,
        composed: true,
      }),
    );
    await Promise.resolve();
    await element.updateComplete;
    expect(element.shadowRoot.textContent).toContain("插件与连接器");
    expect(element.shadowRoot.querySelector("plugins-connectors-page")).toBeTruthy();
  });

  it("renders sessions page through routed shell", async () => {
    window.history.pushState({}, "", "/");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const nav = element.shadowRoot.querySelector("sidebar-nav");
    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "sessions",
        bubbles: true,
        composed: true,
      }),
    );
    await Promise.resolve();
    await element.updateComplete;
    expect(element.shadowRoot.textContent).toContain("Sessions / Runs");
    expect(element.shadowRoot.querySelector("sessions-runs-trace-page")).toBeTruthy();
  });

  it("returns to chat when sessions page emits session-resumed", async () => {
    window.history.pushState({}, "", "/sessions");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const sessionsPage = element.shadowRoot.querySelector("sessions-runs-trace-page");
    sessionsPage?.dispatchEvent(
      new CustomEvent("session-resumed", {
        detail: { threadId: "thread_demo_001", historyCount: 2 },
        bubbles: true,
        composed: true,
      }),
    );
    await Promise.resolve();
    await element.updateComplete;
    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("chat");
  });

  it("routes workflow approval drill-down into approvals page context", async () => {
    window.history.pushState({}, "", "/sessions");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const sessionsPage = element.shadowRoot.querySelector("sessions-runs-trace-page");
    sessionsPage?.dispatchEvent(
      new CustomEvent("navigate-control-context", {
        detail: {
          route: "approvals",
          traceId: "trace_1",
          approvalId: "approval_1",
          source: "workflow-detail",
        },
        bubbles: true,
        composed: true,
      }),
    );
    await Promise.resolve();
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("approvals");

    const approvalsPage = element.shadowRoot.querySelector("approvals-audit-page") as HTMLElement & {
      initialTraceFilter?: string;
      initialApprovalId?: string;
    };
    expect(approvalsPage).toBeTruthy();
    expect(approvalsPage.initialTraceFilter).toBe("trace_1");
    expect(approvalsPage.initialApprovalId).toBe("approval_1");
  });

  it("routes workflow action and audit drill-down into operator context", async () => {
    window.history.pushState({}, "", "/sessions");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const sessionsPage = element.shadowRoot.querySelector("sessions-runs-trace-page");
    sessionsPage?.dispatchEvent(
      new CustomEvent("navigate-control-context", {
        detail: {
          route: "approvals",
          traceId: "trace_2",
          actionId: "action_2",
          auditId: "audit_2",
          source: "workflow-detail",
        },
        bubbles: true,
        composed: true,
      }),
    );
    await Promise.resolve();
    await element.updateComplete;

    const approvalsPage = element.shadowRoot.querySelector("approvals-audit-page") as HTMLElement & {
      initialTraceFilter?: string;
      initialActionId?: string;
      initialAuditId?: string;
    };
    expect(approvalsPage).toBeTruthy();
    expect(approvalsPage.initialTraceFilter).toBe("trace_2");
    expect(approvalsPage.initialActionId).toBe("action_2");
    expect(approvalsPage.initialAuditId).toBe("audit_2");
  });

  it("routes approvals context back into sessions workflow detail", async () => {
    window.history.pushState({}, "", "/approvals");
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const approvalsPage = element.shadowRoot.querySelector("approvals-audit-page");
    approvalsPage?.dispatchEvent(
      new CustomEvent("navigate-control-context", {
        detail: {
          route: "sessions",
          traceId: "trace_3",
          workflowRunId: "run_3",
          timelineScope: "workflowRuns",
          source: "approvals-context",
        },
        bubbles: true,
        composed: true,
      }),
    );
    await Promise.resolve();
    await element.updateComplete;

    const panel = element.shadowRoot.querySelector("[data-route-panel]");
    expect(panel?.getAttribute("data-route-panel")).toBe("sessions");

    const sessionsPage = element.shadowRoot.querySelector("sessions-runs-trace-page") as HTMLElement & {
      initialTraceId?: string;
      initialWorkflowRunId?: string;
      initialTimelineScope?: string;
    };
    expect(sessionsPage).toBeTruthy();
    expect(sessionsPage.initialTraceId).toBe("trace_3");
    expect(sessionsPage.initialWorkflowRunId).toBe("run_3");
    expect(sessionsPage.initialTimelineScope).toBe("workflowRuns");
  });
});
