import { afterEach, describe, expect, it, vi } from "vitest";

import { BridgeClient } from "../../bridge/client.ts";
import type { HostAdapter } from "../../shared/api/mock-host.ts";
import {
  createBridgeFailure,
  createBridgeSuccess,
  normalizeBridgeEvent,
  type BridgeEvent,
  type BridgeRequest,
  type BrowserProxyRequest,
  type BrowserProxyResponse,
  type ControlUiBootstrap,
  type ControlUiStateSnapshot,
  type GatewayEventPollResult,
} from "../../shared/types/bridge.ts";
import "./workbench-page.ts";

async function flushUi(element: { updateComplete?: Promise<unknown> }) {
  await Promise.resolve();
  await Promise.resolve();
  await element.updateComplete;
}

async function feedbackText(root: ShadowRoot): Promise<string> {
  const element = root.querySelector("[data-testid='workbench-feedback']") as HTMLElement & {
    shadowRoot?: ShadowRoot;
    updateComplete?: Promise<unknown>;
  };
  await element?.updateComplete;
  return element?.shadowRoot?.textContent ?? "";
}

class ApprovalRefreshAdapter implements HostAdapter {
  approvalsCount = 1;
  failTaskRun = false;
  private readonly listeners = new Set<(event: BridgeEvent<Record<string, unknown>>) => void>();
  gatewayPollFrames: GatewayEventPollResult["events"] = [];
  gatewayCursor = 1;

  async getControlUiBootstrap(): Promise<ControlUiBootstrap> {
    return {
      basePath: "/gui",
      assistantName: "AgentHub",
      assistantAvatar: "",
      assistantAgentId: "agenthub",
      serverVersion: "0.1.0",
      providerLabel: "openai | gpt-5.4",
      gateway: {
        methods: ["gateway.state.get", "approvals.list"],
        streams: ["gateway_events", "approvals", "audit"],
      },
    };
  }

  async getControlUiState(): Promise<ControlUiStateSnapshot> {
    return {
      health: {
        status: "ok",
        provider: {
          provider_label: "openai | gpt-5.4",
        },
      },
      runtimePolicy: {},
      approvalStatus: { pending_approvals: String(this.approvalsCount) },
      events: [
        {
          event_id: "evt_1",
          event_type: "gateway.event.created",
          trace_id: "trace_1",
          source_kind: "gateway",
        },
      ],
      workflowRuns: [
        {
          workflow_run_id: "run_1",
          workflow_name: "handle_github_issue_opened",
          trace_id: "trace_1",
          status: "paused",
        },
      ],
      actionRequests: [],
      approvalTickets: [
        {
          approval_id: "approval_0",
          title: "Approval 0",
          risk: "medium",
          trace_id: "trace_0",
          status: "pending",
        },
      ],
      auditRecords: [
        {
          audit_id: "audit_1",
          summary: "approval pending",
          trace_id: "trace_1",
        },
      ],
      diagnostics: {},
      connectors: [],
    };
  }

  async pollGatewayEvents(): Promise<GatewayEventPollResult> {
    return {
      cursor: this.gatewayCursor++,
      events: this.gatewayPollFrames.splice(0),
    };
  }

  async browserProxy(request: BrowserProxyRequest): Promise<BrowserProxyResponse> {
    return {
      status: 200,
      result: {
        ok: true,
        method: request.method,
        path: request.path,
      },
    };
  }

  async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "approval.list") {
      return createBridgeSuccess(request, {
        approvals: Array.from({ length: this.approvalsCount }, (_, index) => ({
          approval_id: `approval_${index}`,
          title: `Approval ${index}`,
          risk: "medium",
          trace_id: `trace_${index}`,
          status: "pending",
        })),
      } as TData);
    }
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
    if (request.action === "browser.status") {
      return createBridgeSuccess(request, {
        running: true,
        activeProfile: "default",
        tabCount: 2,
      } as TData);
    }
    if (request.action === "task.run") {
      if (this.failTaskRun) {
        return createBridgeFailure(request, {
          code: "task.run.failed",
          message: "bridge task rejected",
          retryable: false,
        }) as ReturnType<typeof createBridgeSuccess<TData>>;
      }
      return createBridgeSuccess(request, {
        accepted: true,
        task_id: "task_test",
        thread_id: "thread_test",
      } as TData);
    }
    if (request.action === "thread.list") {
      return createBridgeSuccess(request, {
        threads: [
          {
            thread_id: "thread_test",
            name: "最近线程",
            updated_at: "刚刚",
            turn_count: 2,
            last_user_text: "检查结果",
            last_assistant_text: "已完成",
          },
        ],
        active_thread_id: "thread_test",
      } as TData);
    }
    return createBridgeSuccess(request, {} as TData);
  }

  subscribe(_listener: (event: BridgeEvent<Record<string, unknown>>) => void) {
    this.listeners.add(_listener);
    return () => {
      this.listeners.delete(_listener);
    };
  }

  emit(event: BridgeEvent<Record<string, unknown>>) {
    for (const listener of this.listeners) {
      listener(event);
    }
  }
}

afterEach(() => {
  document.body.innerHTML = "";
  vi.useRealTimers();
});

describe("workbench-page", () => {
  it("renders dashboard sections with mock bridge data", async () => {
    const element = document.createElement("workbench-page") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("Operator Pulse");
    expect(element.shadowRoot.textContent).toContain("Operator Actions");
    expect(element.shadowRoot.textContent).toContain("Attention");
    expect(element.shadowRoot.textContent).toContain("Recent Activity");
    expect(element.shadowRoot.textContent).toContain("System Health");
  });

  it("dispatches workbench-run when quick start submits text", async () => {
    const element = document.createElement("workbench-page") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const receivedPromise = new Promise<string>((resolve) => {
      element.addEventListener("workbench-run", ((event: CustomEvent<{ text: string }>) => {
        resolve(event.detail.text);
      }) as EventListener, { once: true });
    });

    const textarea = element.shadowRoot.querySelector("textarea") as HTMLTextAreaElement;
    textarea.value = "检查 GitHub Actions 结果";
    textarea.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    await flushUi(element);

    const button = element.shadowRoot.querySelector("button.primary") as HTMLButtonElement;
    button.click();
    await flushUi(element);

    await expect(receivedPromise).resolves.toBe("检查 GitHub Actions 结果");
  });

  it("refreshes approval card content", async () => {
    const adapter = new ApprovalRefreshAdapter();
    const client = new BridgeClient(adapter);
    const element = document.createElement("workbench-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
      refreshData?: () => Promise<void>;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await element.refreshData?.();
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("Approval 0");
    expect(element.shadowRoot.textContent).toContain("gateway.event.created");

    adapter.approvalsCount = 3;
    await element.refreshData?.();
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("Approval 2");
    expect(element.shadowRoot.textContent).toContain("最近线程");
  });

  it("renders grouped recent activity including workflow runs", async () => {
    const adapter = new ApprovalRefreshAdapter();
    const client = new BridgeClient(adapter);
    const element = document.createElement("workbench-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);

    const groupsText = element.shadowRoot.querySelector("[data-testid='workbench-activity-groups']")?.textContent ?? "";
    expect(groupsText).toContain("Workflow Runs");
    expect(groupsText).toContain("handle_github_issue_opened");
    expect(groupsText).toContain("Approvals");
    expect(groupsText).toContain("Audit Trail");
  });

  it("renders quick links for operator jumps", async () => {
    const element = document.createElement("workbench-page") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const links = Array.from(
      element.shadowRoot.querySelectorAll("[data-testid='workbench-quick-links'] button"),
    ).map((item) => item.textContent?.trim());
    expect(links).toContain("对话");
    expect(links).toContain("审批");
    expect(links).toContain("Sessions");
  });

  it("dispatches route-change from quick links", async () => {
    const element = document.createElement("workbench-page") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const receivedPromise = new Promise<string>((resolve) => {
      element.addEventListener("route-change", ((event: CustomEvent<string>) => {
        resolve(event.detail);
      }) as EventListener, { once: true });
    });

    const buttons = Array.from(
      element.shadowRoot.querySelectorAll("[data-testid='workbench-quick-links'] button"),
    ) as HTMLButtonElement[];
    buttons[0]?.click();

    await expect(receivedPromise).resolves.toBe("chat");
  });

  it("dispatches operator context from attention and approval entries", async () => {
    const adapter = new ApprovalRefreshAdapter();
    const client = new BridgeClient(adapter);
    const element = document.createElement("workbench-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);

    const attentionPromise = new Promise<Record<string, unknown>>((resolve) => {
      element.addEventListener(
        "navigate-control-context",
        ((event: CustomEvent<Record<string, unknown>>) => resolve(event.detail)) as EventListener,
        { once: true },
      );
    });

    const attentionButton = element.shadowRoot.querySelector("[data-testid='workbench-attention-open']") as HTMLButtonElement;
    attentionButton.click();
    await expect(attentionPromise).resolves.toEqual({
      route: "approvals",
      traceId: "trace_0",
      approvalId: "approval_0",
      timelineScope: undefined,
      source: "workbench",
    });

    const approvalPromise = new Promise<Record<string, unknown>>((resolve) => {
      element.addEventListener(
        "navigate-control-context",
        ((event: CustomEvent<Record<string, unknown>>) => resolve(event.detail)) as EventListener,
        { once: true },
      );
    });

    const approvalButton = element.shadowRoot.querySelector("[data-testid='workbench-approval-open']") as HTMLButtonElement;
    approvalButton.click();
    await expect(approvalPromise).resolves.toEqual({
      route: "approvals",
      traceId: "trace_0",
      approvalId: "approval_0",
      source: "workbench",
    });
  });

  it("applies bridge events incrementally into live feed", async () => {
    const adapter = new ApprovalRefreshAdapter();
    const client = new BridgeClient(adapter);
    const element = document.createElement("workbench-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);

    adapter.emit(
      normalizeBridgeEvent({
        request_id: "req_approval",
        kind: "approval_requested",
        name: "approval_requested",
        summary: "New approval requested",
        payload: {
          approval_id: "approval_live",
          trace_id: "trace_live",
          summary: "live approval",
        },
      }),
    );
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("live approval");
    expect(element.shadowRoot.textContent).toContain("New approval requested");

    adapter.emit(
      normalizeBridgeEvent({
        request_id: "req_audit",
        kind: "audit_written",
        name: "audit_written",
        summary: "Audit stream updated",
        payload: {
          audit_id: "audit_live",
          trace_id: "trace_live",
          summary: "live audit",
          stage: "approval",
          status: "pending",
        },
      }),
    );
    await flushUi(element);

    const groupsText = element.shadowRoot.querySelector("[data-testid='workbench-activity-groups']")?.textContent ?? "";
    expect(groupsText).toContain("live audit");
    expect(groupsText).toContain("Audit Trail");
  });

  it("polls gateway events into live feed", async () => {
    vi.useFakeTimers();
    const adapter = new ApprovalRefreshAdapter();
    adapter.gatewayPollFrames = [
      {
        cursor: 1,
        stream: "workflow_runs",
        event: "workflow.updated",
        payload: {
          workflow_run_id: "run_live",
          workflow_name: "live_workflow",
          trace_id: "trace_live",
        },
      },
      {
        cursor: 2,
        stream: "audit",
        event: "audit.appended",
        payload: {
          audit_id: "audit_live_poll",
          summary: "polled audit",
          trace_id: "trace_live",
        },
      },
    ];
    const client = new BridgeClient(adapter);
    const element = document.createElement("workbench-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);

    await vi.advanceTimersByTimeAsync(1300);
    await flushUi(element);

    const groupsText = element.shadowRoot.querySelector("[data-testid='workbench-activity-groups']")?.textContent ?? "";
    expect(groupsText).toContain("live_workflow");
    expect(groupsText).toContain("polled audit");
  });

  it("renders operation feedback when task.run fails", async () => {
    const adapter = new ApprovalRefreshAdapter();
    adapter.failTaskRun = true;
    const client = new BridgeClient(adapter);
    const element = document.createElement("workbench-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);

    const textarea = element.shadowRoot.querySelector("textarea") as HTMLTextAreaElement;
    textarea.value = "执行失败任务";
    textarea.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    await flushUi(element);

    const button = element.shadowRoot.querySelector("button.primary") as HTMLButtonElement;
    button.click();
    await flushUi(element);

    const feedback = element.shadowRoot.querySelector("[data-testid='workbench-feedback']") as HTMLElement & {
      shadowRoot?: ShadowRoot;
    };
    await vi.waitFor(async () => {
      expect(await feedbackText(element.shadowRoot)).toContain("bridge task rejected");
    });
    expect(feedback.shadowRoot?.querySelector(".wrapper")?.className).toContain("error");
    expect(textarea.value).toBe("执行失败任务");
  });
});
