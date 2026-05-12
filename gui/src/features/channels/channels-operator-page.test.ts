import { describe, expect, it } from "vitest";

import { BridgeClient } from "../../bridge/client.ts";
import type { HostAdapter } from "../../shared/api/mock-host.ts";
import {
  createBridgeSuccess,
  type BridgeEvent,
  type BridgeRequest,
} from "../../shared/types/bridge.ts";
import "./channels-operator-page.ts";

async function flushUi(element: { updateComplete?: Promise<unknown> }) {
  await Promise.resolve();
  await Promise.resolve();
  await element.updateComplete;
  await Promise.resolve();
  await element.updateComplete;
}

class ChannelsAdapter implements HostAdapter {
  async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "connector.list") {
      return createBridgeSuccess(request, {
        connectors: [
          {
            connector_key: "github_webhook",
            plugin_name: "github_phase1",
            display_name: "GitHub Webhook",
            connector_kind: "webhook",
            supports_webhook: true,
            supports_polling: false,
            supports_actions: true,
            approval_required: true,
            enabled: true,
            health: "ready",
            event_types: ["github.issue.created"],
            action_types: ["github.issue.close", "github.workflow.dispatch"],
            source_kind: "gateway",
          },
          {
            connector_key: "slack_poller",
            plugin_name: "slack_phase1",
            display_name: "Slack Poller",
            connector_kind: "poller",
            supports_webhook: false,
            supports_polling: true,
            supports_actions: false,
            approval_required: false,
            enabled: true,
            health: "warning",
            event_types: ["slack.message"],
            action_types: [],
            source_kind: "plugin_app",
          },
        ],
      } as TData);
    }
    if (request.action === "settings.get") {
      return createBridgeSuccess(request, {
        model: "gpt-5.4",
        browserHeadless: false,
        pluginAutoLoad: true,
        workspaceRoot: "/workspace/demo",
        workspaceTrust: "trusted",
        providerLabel: "openai | gpt-5.4",
      } as TData);
    }
    if (request.action === "connect.capabilities") {
      return createBridgeSuccess(request, {
        methods: [
          { method: "connect.capabilities", family: "connect", auth_required: false, required_scopes: [] },
          { method: "connector.list", family: "connectors", auth_required: true, required_scopes: ["connectors.read"] },
          { method: "approvals.resolve", family: "approvals", auth_required: true, required_scopes: ["approvals.resolve"] },
        ],
        legacyMethods: [],
        providerLabel: "openai | gpt-5.4",
      } as TData);
    }
    return createBridgeSuccess(request, {} as TData);
  }

  subscribe(_listener: (event: BridgeEvent<Record<string, unknown>>) => void) {
    return () => {};
  }

  async getControlUiBootstrap() {
    throw new Error("not used");
  }

  async getControlUiState() {
    throw new Error("not used");
  }

  async pollGatewayEvents() {
    throw new Error("not used");
  }

  async browserProxy() {
    throw new Error("not used");
  }
}

describe("channels-operator-page", () => {
  it("renders channel inventory and posture summary", async () => {
    const element = document.createElement("channels-operator-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(new ChannelsAdapter());
    document.body.appendChild(element);
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("Channels Inventory");
    expect(element.shadowRoot.textContent).toContain("GitHub Webhook");
    expect(element.shadowRoot.textContent).toContain("Slack Poller");
    expect(element.shadowRoot.textContent).toContain("approval-gated");
  });

  it("filters connectors by channel mode", async () => {
    const element = document.createElement("channels-operator-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(new ChannelsAdapter());
    document.body.appendChild(element);
    await flushUi(element);

    const filter = element.shadowRoot.querySelector("[data-testid='channels-filter-polling']") as HTMLButtonElement;
    filter.click();
    await flushUi(element);

    const cards = Array.from(element.shadowRoot.querySelectorAll("[data-testid='channels-connector-card']"));
    expect(cards.length).toBe(1);
    expect(element.shadowRoot.textContent).toContain("Slack Poller");
    expect(element.shadowRoot.textContent).not.toContain("GitHub Webhook");
  });

  it("emits auth handoff from selected connector", async () => {
    const element = document.createElement("channels-operator-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(new ChannelsAdapter());
    document.body.appendChild(element);
    await flushUi(element);

    const events: Array<Record<string, unknown>> = [];
    element.addEventListener("navigate-control-context", ((event: Event) => {
      events.push((event as CustomEvent<Record<string, unknown>>).detail);
    }) as EventListener);

    const authButton = element.shadowRoot.querySelector("[data-testid='channels-open-auth']") as HTMLButtonElement;
    authButton.click();

    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({
      route: "auth",
      connectorKey: "github_webhook",
      source: "channels",
    });
  });
});
