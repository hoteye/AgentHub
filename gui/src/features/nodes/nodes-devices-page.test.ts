import { describe, expect, it } from "vitest";

import { BridgeClient } from "../../bridge/client.ts";
import type { HostAdapter } from "../../shared/api/mock-host.ts";
import {
  createBridgeFailure,
  createBridgeSuccess,
  type BridgeEvent,
  type BridgeRequest,
} from "../../shared/types/bridge.ts";
import "./nodes-devices-page.ts";

async function flushUi(element: { updateComplete?: Promise<unknown> }) {
  await Promise.resolve();
  await Promise.resolve();
  await element.updateComplete;
  await Promise.resolve();
  await element.updateComplete;
}

async function feedbackText(root: ShadowRoot): Promise<string> {
  const element = root.querySelector("[data-testid='nodes-feedback']") as HTMLElement & {
    shadowRoot?: ShadowRoot;
    updateComplete?: Promise<unknown>;
  };
  await element?.updateComplete;
  return element?.shadowRoot?.textContent ?? "";
}

class NodesAdapter implements HostAdapter {
  constructor(private readonly failNodesList = false) {}

  async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (String(request.action) === "nodes.list") {
      if (this.failNodesList) {
        return createBridgeFailure(request, {
          code: "nodes.list.failed",
          message: "nodes list unavailable",
          retryable: true,
        });
      }
      return createBridgeSuccess(request, {
        nodes: [
          {
            node_id: "node_local_1",
            name: "Local Runtime",
            kind: "local",
            status: "ready",
            is_local: true,
            is_remote: false,
            trustLevel: "trusted",
            pairing: {
              pendingRequestCount: 0,
              pendingApprovalCount: 0,
              hasNativeContract: false,
              source: "heuristic",
            },
            capabilities: {
              browser: "ready",
              workflows: "ready",
              approvals: "warning",
              connectors: "ready",
            },
          },
          {
            node_id: "device_remote_1",
            name: "Remote Device iPad",
            kind: "device",
            status: "warning",
            is_local: false,
            is_remote: true,
            trustLevel: "untrusted",
            pairing: {
              pendingRequestCount: 2,
              pendingApprovalCount: 1,
              hasNativeContract: false,
              source: "approvals-heuristic",
              summary: "pending from approvals",
              pendingRefs: [
                {
                  approvalId: "approval_demo_007",
                  traceId: "trace_demo_007",
                  title: "Remote device pairing request",
                  actionType: "pairing.request",
                  requestedAt: "2026-03-30T09:10:00Z",
                },
                {
                  approvalId: "approval_route_only",
                  title: "Approval-only pairing ref",
                  actionType: "pairing.request",
                },
              ],
            },
            capabilities: {
              browser: "warning",
              workflows: "ready",
              approvals: "ready",
              connectors: "warning",
            },
          },
        ],
        summary: {
          source: "nodes_registry_v1",
        },
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

describe("nodes-devices-page", () => {
  it("renders nodes/devices inventory and summary cards from nodes.list", async () => {
    const element = document.createElement("nodes-devices-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(new NodesAdapter());
    document.body.appendChild(element);
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("Nodes / Devices Inventory");
    expect(element.shadowRoot.textContent).toContain("Local Runtime");
    expect(element.shadowRoot.textContent).toContain("Remote Device iPad");

    const total = element.shadowRoot.querySelector("[data-testid='nodes-summary-total']") as HTMLElement;
    const local = element.shadowRoot.querySelector("[data-testid='nodes-summary-local']") as HTMLElement;
    const remote = element.shadowRoot.querySelector("[data-testid='nodes-summary-remote']") as HTMLElement;
    const pairing = element.shadowRoot.querySelector("[data-testid='nodes-summary-pairing']") as HTMLElement;
    expect(total.textContent).toContain("2");
    expect(local.textContent).toContain("1");
    expect(remote.textContent).toContain("1");
    expect(pairing.textContent).toContain("2");
  });

  it("updates remote/pairing/capability detail when selecting remote node", async () => {
    const element = document.createElement("nodes-devices-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(new NodesAdapter());
    document.body.appendChild(element);
    await flushUi(element);

    const remoteCard = element.shadowRoot.querySelector(
      "[data-testid='nodes-card-device_remote_1']",
    ) as HTMLElement;
    remoteCard.click();
    await flushUi(element);

    const remotePosture = element.shadowRoot.querySelector("[data-testid='nodes-remote-posture']") as HTMLElement;
    const pairing = element.shadowRoot.querySelector("[data-testid='nodes-pairing-summary']") as HTMLElement;
    const capability = element.shadowRoot.querySelector("[data-testid='nodes-capability-summary']") as HTMLElement;
    expect(remotePosture.textContent).toContain("remote=on");
    expect(pairing.textContent).toContain("pendingPairing=2");
    expect(pairing.textContent).toContain("pendingRefs=2");
    expect(pairing.textContent).toContain("heuristic-only");
    expect(capability.textContent).toContain("browser=warning");
    expect(capability.textContent).toContain("approvals=ready");
    const pendingRefs = element.shadowRoot.querySelector("[data-testid='nodes-pairing-pending-refs']") as HTMLElement;
    expect(pendingRefs.textContent).toContain("Remote device pairing request");
    expect(pendingRefs.textContent).toContain("action=pairing.request");
  });

  it("emits route-change next-hop events", async () => {
    const element = document.createElement("nodes-devices-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(new NodesAdapter());
    document.body.appendChild(element);
    await flushUi(element);

    const routes: string[] = [];
    element.addEventListener("route-change", ((event: Event) => {
      routes.push((event as CustomEvent<string>).detail);
    }) as EventListener);

    const settingsButton = element.shadowRoot.querySelector("[data-testid='nodes-open-settings']") as HTMLButtonElement;
    const authButton = element.shadowRoot.querySelector("[data-testid='nodes-open-auth']") as HTMLButtonElement;
    const channelsButton = element.shadowRoot.querySelector("[data-testid='nodes-open-channels']") as HTMLButtonElement;
    const approvalsButton = element.shadowRoot.querySelector("[data-testid='nodes-open-approvals']") as HTMLButtonElement;
    settingsButton.click();
    authButton.click();
    channelsButton.click();
    approvalsButton.click();

    expect(routes).toEqual(["settings", "auth", "channels", "approvals"]);
  });

  it("prefers navigate-control-context for pairing refs with trace metadata", async () => {
    const element = document.createElement("nodes-devices-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(new NodesAdapter());
    document.body.appendChild(element);
    await flushUi(element);

    const remoteCard = element.shadowRoot.querySelector(
      "[data-testid='nodes-card-device_remote_1']",
    ) as HTMLElement;
    remoteCard.click();
    await flushUi(element);

    const contexts: Array<Record<string, unknown>> = [];
    const routes: string[] = [];
    element.addEventListener("navigate-control-context", ((event: Event) => {
      contexts.push((event as CustomEvent<Record<string, unknown>>).detail);
    }) as EventListener);
    element.addEventListener("route-change", ((event: Event) => {
      routes.push((event as CustomEvent<string>).detail);
    }) as EventListener);

    const openRef = element.shadowRoot.querySelector(
      "[data-testid='nodes-pairing-open-approvals-approval_demo_007']",
    ) as HTMLButtonElement;
    openRef.click();

    expect(contexts).toEqual([
      {
        route: "approvals",
        traceId: "trace_demo_007",
        approvalId: "approval_demo_007",
        source: "nodes-pairing",
      },
    ]);
    expect(routes).toEqual([]);
  });

  it("opens sessions drill-down from pairing refs", async () => {
    const element = document.createElement("nodes-devices-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(new NodesAdapter());
    document.body.appendChild(element);
    await flushUi(element);

    const remoteCard = element.shadowRoot.querySelector(
      "[data-testid='nodes-card-device_remote_1']",
    ) as HTMLElement;
    remoteCard.click();
    await flushUi(element);

    const contexts: Array<Record<string, unknown>> = [];
    element.addEventListener("navigate-control-context", ((event: Event) => {
      contexts.push((event as CustomEvent<Record<string, unknown>>).detail);
    }) as EventListener);

    const openRef = element.shadowRoot.querySelector(
      "[data-testid='nodes-pairing-open-sessions-approval_demo_007']",
    ) as HTMLButtonElement;
    openRef.click();

    expect(contexts).toEqual([
      {
        route: "sessions",
        traceId: "trace_demo_007",
        timelineScope: "approvalTickets",
        source: "nodes-pairing",
      },
    ]);
  });

  it("falls back to route-change when pairing ref has no trace metadata", async () => {
    const element = document.createElement("nodes-devices-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(new NodesAdapter());
    document.body.appendChild(element);
    await flushUi(element);

    const remoteCard = element.shadowRoot.querySelector(
      "[data-testid='nodes-card-device_remote_1']",
    ) as HTMLElement;
    remoteCard.click();
    await flushUi(element);

    const contexts: Array<Record<string, unknown>> = [];
    const routes: string[] = [];
    element.addEventListener("navigate-control-context", ((event: Event) => {
      contexts.push((event as CustomEvent<Record<string, unknown>>).detail);
    }) as EventListener);
    element.addEventListener("route-change", ((event: Event) => {
      routes.push((event as CustomEvent<string>).detail);
    }) as EventListener);

    const openRef = element.shadowRoot.querySelector(
      "[data-testid='nodes-pairing-open-sessions-approval_route_only']",
    ) as HTMLButtonElement;
    openRef.click();

    expect(contexts).toEqual([]);
    expect(routes).toEqual(["sessions"]);
  });

  it("shows failure feedback and empty inventory when nodes.list fails", async () => {
    const element = document.createElement("nodes-devices-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(new NodesAdapter(true));
    document.body.appendChild(element);
    await flushUi(element);

    const empty = element.shadowRoot.querySelector("[data-testid='nodes-empty']") as HTMLElement;
    expect(empty.textContent).toContain("暂无 nodes inventory");
    await expect(feedbackText(element.shadowRoot)).resolves.toContain("nodes list unavailable");
  });
});
