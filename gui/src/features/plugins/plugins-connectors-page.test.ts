import { afterEach, describe, expect, it } from "vitest";

import { BridgeClient } from "../../bridge/client.ts";
import type { HostAdapter } from "../../shared/api/mock-host.ts";
import {
  createBridgeFailure,
  createBridgeSuccess,
  normalizeBridgeEvent,
  type BrowserProxyResponse,
  type BridgeEvent,
  type BridgeRequest,
  type ControlUiBootstrap,
  type ControlUiStateSnapshot,
  type GatewayEventPollResult,
} from "../../shared/types/bridge.ts";
import "./plugins-connectors-page.ts";

async function flushUi(element: { updateComplete?: Promise<unknown> }) {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  await element.updateComplete;
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  await element.updateComplete;
}

async function feedbackText(root: ShadowRoot, selector: string): Promise<string> {
  const element = root.querySelector(selector) as HTMLElement & {
    shadowRoot?: ShadowRoot;
    updateComplete?: Promise<unknown>;
  };
  await element?.updateComplete;
  return element?.shadowRoot?.textContent ?? "";
}

class PluginFailureAdapter implements HostAdapter {
  async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "plugin.list") {
      return createBridgeSuccess(request, {
        plugins: [
          {
            plugin_id: "psbc_policy",
            title: "邮储制度合规插件",
            enabled: true,
            health: "ready",
          },
        ],
      } as TData);
    }
    if (request.action === "connector.list") {
      return createBridgeSuccess(request, {
        connectors: [
          {
            connector_key: "github_webhook",
            plugin_name: "psbc_policy",
            display_name: "GitHub Webhook",
            connector_kind: "webhook",
            supports_webhook: true,
            supports_polling: false,
            supports_actions: true,
            approval_required: true,
            enabled: true,
            health: "ready",
          },
        ],
      } as TData);
    }
    if (request.action === "plugin.disable") {
      return createBridgeFailure(request, {
        code: "plugin.disable.failed",
        message: "插件禁用失败",
        retryable: false,
      });
    }
    return createBridgeSuccess(request, {} as TData);
  }

  subscribe(_listener: (event: BridgeEvent<Record<string, unknown>>) => void) {
    return () => {};
  }
}

class EventfulPluginAdapter implements HostAdapter {
  plugins = [
    {
      plugin_id: "psbc_policy",
      title: "邮储制度合规插件",
      enabled: true,
      health: "ready",
    },
  ];
  connectors = [
    {
      connector_key: "github_webhook",
      plugin_name: "psbc_policy",
      display_name: "GitHub Webhook",
      connector_kind: "webhook",
      supports_webhook: true,
      supports_polling: false,
      supports_actions: true,
      approval_required: true,
      enabled: true,
      health: "ready",
      source_kind: "gateway" as const,
      event_types: ["github.issue.created"],
      action_types: ["github.issue.close"],
    },
  ];
  private readonly listeners = new Set<(event: BridgeEvent<Record<string, unknown>>) => void>();

  async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "plugin.list") {
      return createBridgeSuccess(request, { plugins: this.plugins } as TData);
    }
    if (request.action === "connector.list") {
      return createBridgeSuccess(request, { connectors: this.connectors } as TData);
    }
    return createBridgeSuccess(request, {} as TData);
  }

  subscribe(listener: (event: BridgeEvent<Record<string, unknown>>) => void) {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  async getControlUiBootstrap(): Promise<ControlUiBootstrap> {
    return {
      basePath: "/gui",
      assistantName: "AgentHub",
      assistantAvatar: "",
      assistantAgentId: "agenthub",
      serverVersion: "0.1.0",
      gateway: {
        methods: [],
        streams: [],
      },
    };
  }

  async getControlUiState(): Promise<ControlUiStateSnapshot> {
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

  async pollGatewayEvents(): Promise<GatewayEventPollResult> {
    return { cursor: 0, events: [] };
  }

  async browserProxy(): Promise<BrowserProxyResponse> {
    return { status: 200, result: {} };
  }

  emitPluginStateChanged(summary = "plugin state changed") {
    for (const listener of this.listeners) {
      listener(
        normalizeBridgeEvent({
          request_id: "req_plugin_event",
          kind: "plugin_state_changed",
          name: "plugin_state_changed",
          summary,
          payload: { plugin_id: this.plugins[0]?.plugin_id ?? "" },
        }),
      );
    }
  }
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("plugins-connectors-page", () => {
  it("loads plugin list and connector status", async () => {
    const element = document.createElement("plugins-connectors-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("插件");
    expect(element.shadowRoot.textContent).toContain("邮储制度合规插件");
    expect(element.shadowRoot.textContent).toContain("连接器");
    expect(element.shadowRoot.textContent).toContain("GitHub Webhook");
    expect(element.shadowRoot.querySelector('[data-testid="plugin-summary"]')?.textContent).toContain("Plugins");
    expect(element.shadowRoot.querySelector('[data-testid="connector-summary"]')?.textContent).toContain("Connectors");
    expect(element.shadowRoot.querySelector('[data-testid="connector-channel-inventory"]')?.textContent).toContain(
      "Webhook Ingress",
    );
    expect(element.shadowRoot.querySelector('[data-testid="connector-channel-inventory"]')?.textContent).toContain(
      "gateway=1, app=1",
    );
    await expect(feedbackText(element.shadowRoot, '[data-testid="connector-feedback"]')).resolves.toContain(
      "2/2 连接器就绪",
    );
    expect(element.shadowRoot.querySelector('[data-testid="connector-detail-panel"]')?.textContent).toContain(
      "GitHub Webhook",
    );
  });

  it("toggles plugin enabled state", async () => {
    const element = document.createElement("plugins-connectors-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const button = element.shadowRoot.querySelector('[data-testid="plugin-toggle"]') as HTMLButtonElement;
    expect(button.textContent).toContain("禁用");
    button.click();
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("启用");
  });

  it("keeps reload action visible for plugin lifecycle", async () => {
    const element = document.createElement("plugins-connectors-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const reloadButton = element.shadowRoot.querySelector('[data-testid="plugin-reload"]') as HTMLButtonElement;
    expect(reloadButton).toBeTruthy();
    expect(reloadButton.textContent).toContain("重载");
  });

  it("renders unified operation feedback when plugin disable fails", async () => {
    const element = document.createElement("plugins-connectors-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(new PluginFailureAdapter());
    document.body.appendChild(element);
    await flushUi(element);

    const button = element.shadowRoot.querySelector('[data-testid="plugin-toggle"]') as HTMLButtonElement;
    button.click();
    await flushUi(element);

    const feedback = element.shadowRoot.querySelector('[data-testid="plugin-feedback"]') as HTMLElement & {
      shadowRoot?: ShadowRoot;
    };
    await expect(feedbackText(element.shadowRoot, '[data-testid="plugin-feedback"]')).resolves.toContain(
      "插件禁用失败",
    );
    expect(feedback.shadowRoot?.querySelector(".wrapper")?.className).toContain("error");
    expect(button.textContent).toContain("禁用");
  });

  it("updates connector detail when selecting another connector", async () => {
    const element = document.createElement("plugins-connectors-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const button = element.shadowRoot.querySelector(
      '[data-testid="connector-select-github_dispatch"]',
    ) as HTMLButtonElement;
    button.click();
    await flushUi(element);

    const detail = element.shadowRoot.querySelector('[data-testid="connector-detail-panel"]') as HTMLElement;
    expect(detail.textContent).toContain("github_dispatch");
    expect(detail.textContent).toContain("Action Types");
    const operatorNote = element.shadowRoot.querySelector(
      '[data-testid="connector-detail-operator-note"]',
    ) as HTMLElement;
    expect(operatorNote.textContent).toContain("external auth / channel inventory");
  });

  it("shows plugin-app connector detail as channel inventory handoff", async () => {
    const element = document.createElement("plugins-connectors-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const selectButton = element.shadowRoot.querySelector(
      '[data-testid="connector-select-github_dispatch"]',
    ) as HTMLButtonElement;
    selectButton.click();
    await flushUi(element);

    const detail = element.shadowRoot.querySelector('[data-testid="connector-detail-panel"]') as HTMLElement;
    expect(detail.textContent).toContain("plugin_app");
    expect(detail.textContent).toContain("required");
    expect(detail.textContent).toContain("no ingress");
    expect(detail.textContent).toContain("external auth / channel inventory");
  });

  it("honors initial connector route context", async () => {
    const element = document.createElement("plugins-connectors-page") as HTMLElement & {
      initialSelectedConnectorKey?: string;
      initialConnectorFilter?: string;
      initialContextSource?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.initialSelectedConnectorKey = "github_webhook";
    element.initialConnectorFilter = "gateway";
    element.initialContextSource = "settings-auth-connectors";
    document.body.appendChild(element);
    await flushUi(element);

    const inventory = element.shadowRoot.querySelector('[data-testid="connector-channel-inventory"]') as HTMLElement;
    expect(inventory.textContent).toContain("gateway=1, app=1");
    const banner = element.shadowRoot.querySelector('[data-testid="connector-context-banner"]') as HTMLElement;
    expect(banner.textContent).toContain("handoff=settings-auth-connectors");
    const detail = element.shadowRoot.querySelector('[data-testid="connector-detail-panel"]') as HTMLElement;
    expect(detail.textContent).toContain("github_webhook");
    const gatewayFilter = element.shadowRoot.querySelector(
      '[data-testid="connector-filter-gateway"]',
    ) as HTMLButtonElement;
    expect(gatewayFilter.className).toContain("active");
  });

  it("dispatches auth connector context from connector detail", async () => {
    const routes: Array<Record<string, string>> = [];
    const element = document.createElement("plugins-connectors-page") as HTMLElement & {
      initialSelectedConnectorKey?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.initialSelectedConnectorKey = "github_dispatch";
    element.addEventListener("navigate-control-context", ((event: CustomEvent<Record<string, string>>) => {
      routes.push(event.detail);
    }) as EventListener);
    document.body.appendChild(element);
    await flushUi(element);

    const openAuth = element.shadowRoot.querySelector(
      '[data-testid="connector-open-auth-surface"]',
    ) as HTMLButtonElement;
    openAuth.click();

    expect(routes).toEqual([
      {
        route: "auth",
        connectorKey: "github_dispatch",
        connectorFilter: "approval",
        source: "plugins-connectors",
      },
    ]);
  });

  it("dispatches settings route from connector detail", async () => {
    const routes: Array<Record<string, string>> = [];
    const element = document.createElement("plugins-connectors-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.addEventListener("navigate-control-context", ((event: CustomEvent<Record<string, string>>) => {
      routes.push(event.detail);
    }) as EventListener);
    document.body.appendChild(element);
    await flushUi(element);

    const openSettings = element.shadowRoot.querySelector(
      '[data-testid="connector-open-settings-surface"]',
    ) as HTMLButtonElement;
    openSettings.click();

    expect(routes).toEqual([
      {
        route: "settings",
        connectorKey: "github_webhook",
        connectorFilter: "gateway",
        source: "plugins-connectors",
      },
    ]);
  });

  it("dispatches approvals landing context from connector detail", async () => {
    const routes: Array<Record<string, string>> = [];
    const element = document.createElement("plugins-connectors-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.addEventListener("navigate-control-context", ((event: CustomEvent<Record<string, string>>) => {
      routes.push(event.detail);
    }) as EventListener);
    document.body.appendChild(element);
    await flushUi(element);

    const openApprovals = element.shadowRoot.querySelector(
      '[data-testid="connector-open-approvals-surface"]',
    ) as HTMLButtonElement;
    openApprovals.click();

    expect(routes).toEqual([
      {
        route: "approvals",
        connectorKey: "github_webhook",
        source: "plugins-connectors",
      },
    ]);
  });

  it("refreshes registry when plugin state bridge event arrives", async () => {
    const adapter = new EventfulPluginAdapter();
    const element = document.createElement("plugins-connectors-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(adapter);
    document.body.appendChild(element);
    await flushUi(element);

    adapter.plugins = [
      {
        plugin_id: "psbc_policy",
        title: "邮储制度合规插件",
        enabled: false,
        health: "warning",
      },
    ];
    adapter.emitPluginStateChanged("插件状态已变化");
    await flushUi(element);

    const toggleButton = element.shadowRoot.querySelector('[data-testid="plugin-toggle"]') as HTMLButtonElement;
    expect(toggleButton.textContent).toContain("启用");
    await expect(feedbackText(element.shadowRoot, '[data-testid="plugin-feedback"]')).resolves.toContain(
      "插件状态已变化",
    );
  });
});
