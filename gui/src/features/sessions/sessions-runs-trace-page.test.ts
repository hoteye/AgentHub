import { describe, expect, it } from "vitest";

import { BridgeClient } from "../../bridge/client.ts";
import type { HostAdapter } from "../../shared/api/mock-host.ts";
import {
  createBridgeFailure,
  createBridgeSuccess,
  type BridgeEvent,
  type BridgeRequest,
  type ControlUiBootstrap,
  type ControlUiStateSnapshot,
  type GatewayEventPollResult,
  type BrowserProxyRequest,
  type BrowserProxyResponse,
} from "../../shared/types/bridge.ts";
import "./sessions-runs-trace-page.ts";

async function flushUi(element: { updateComplete?: Promise<unknown> }) {
  await Promise.resolve();
  await Promise.resolve();
  await element.updateComplete;
}

function feedbackText(root: ShadowRoot): string {
  const element = root.querySelector("[data-testid='sessions-feedback']") as
    | (HTMLElement & { shadowRoot?: ShadowRoot })
    | null;
  return element?.shadowRoot?.textContent ?? "";
}

class SessionsHostAdapter implements HostAdapter {
  resumedThreadIds: string[] = [];
  resumedWorkflowIds: string[] = [];
  gatewayTraceOk = true;

  async getControlUiBootstrap(): Promise<ControlUiBootstrap> {
    return {
      basePath: "/gui",
      assistantName: "AgentHub",
      assistantAvatar: "",
      assistantAgentId: "agenthub",
      serverVersion: "0.1.0",
      providerLabel: "openai | gpt-5.4",
      gateway: {
        methods: ["gateway.trace.timeline", "workflows.list", "workflows.get", "workflows.resume"],
        streams: ["gateway_events", "workflow_runs", "approvals", "audit"],
      },
    };
  }

  async getControlUiState(): Promise<ControlUiStateSnapshot> {
    return {
      health: { status: "ok" },
      runtimePolicy: {},
      approvalStatus: {},
      events: [
        {
          event_id: "evt_1",
          event_type: "demo.event",
          source_kind: "mock",
          trace_id: "trace_1",
        },
      ],
      workflowRuns: [
        {
          workflow_run_id: "run_1",
          trace_id: "trace_1",
          status: "running",
          result_summary: "workflow running",
        },
      ],
      actionRequests: [],
      approvalTickets: [
        {
          approval_id: "approval_1",
          trace_id: "trace_1",
          status: "pending",
          summary: "awaiting approval",
        },
      ],
      auditRecords: [
        {
          audit_id: "audit_1",
          trace_id: "trace_1",
          stage: "approval",
          status: "pending",
          summary: "audit pending",
        },
      ],
      diagnostics: {},
      connectors: [],
    };
  }

  async pollGatewayEvents(): Promise<GatewayEventPollResult> {
    return {
      cursor: 0,
      events: [],
    };
  }

  async browserProxy(_request: BrowserProxyRequest): Promise<BrowserProxyResponse> {
    return {
      status: 200,
      result: { ok: true },
    };
  }

  async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "thread.list") {
      return createBridgeSuccess(request, {
        threads: [
          {
            thread_id: "thread_1",
            name: "Thread One",
            updated_at: "刚刚",
            turn_count: 4,
            last_user_text: "first prompt",
            last_assistant_text: "first answer",
          },
          {
            thread_id: "thread_2",
            name: "Thread Two",
            updated_at: "1 分钟前",
            turn_count: 2,
            last_user_text: "second prompt",
            last_assistant_text: "second answer",
          },
        ],
        active_thread_id: "thread_1",
      } as TData);
    }
    if (request.action === "thread.resume") {
      const threadId = String((request.payload as { thread_id?: string })?.thread_id ?? "");
      this.resumedThreadIds.push(threadId);
      return createBridgeSuccess(request, {
        thread: { thread_id: threadId, name: threadId, updated_at: "now", turn_count: 1 },
        history: [{ role: "user", content: "hello" }],
      } as TData);
    }
    if (request.action === "gateway.trace.timeline") {
      if (!this.gatewayTraceOk) {
        return createBridgeFailure(request, {
          code: "gateway.trace.timeline.failed",
          message: "trace service unavailable",
          retryable: false,
        }) as ReturnType<typeof createBridgeSuccess<TData>>;
      }
      return createBridgeSuccess(request, {
        traceId: "trace_1",
        timeline: [
          {
            kind: "run",
            item: {
              workflow_run_id: "run_1",
              trace_id: "trace_1",
              status: "running",
              summary: "gateway timeline run",
            },
          },
        ],
      } as TData);
    }
    if (request.action === "workflows.list") {
      return createBridgeSuccess(request, {
        workflowRuns: [
          {
            workflow_run_id: "run_1",
            trace_id: "trace_1",
            plugin_name: "github_phase1",
            workflow_name: "handle_github_issue_opened",
            status: "paused",
            current_step: "paused_for_operator_review",
            result_summary: "workflow running",
          },
        ],
        workflowDiagnostics: [
          {
            workflow_run_id: "run_1",
            plugin_name: "github_phase1",
            workflow_name: "handle_github_issue_opened",
            workflow_status: "paused",
            reasoning: { summary: "workflow recommends operator review" },
          },
        ],
        counts: { workflowRuns: 1, running: 0, paused: 1 },
      } as TData);
    }
    if (request.action === "workflows.get") {
      return createBridgeSuccess(request, {
        workflowRun: {
          workflow_run_id: "run_1",
          trace_id: "trace_1",
          plugin_name: "github_phase1",
          workflow_name: "handle_github_issue_opened",
          status: "paused",
          current_step: "paused_for_operator_review",
          result_summary: "workflow running",
        },
        workflowDiagnostic: {
          workflow_run_id: "run_1",
          workflow_status: "paused",
          reasoning: { summary: "workflow recommends operator review" },
          recommendation: { count: 1 },
          approval: { status: "pending" },
          execution: { status: "not_executed" },
        },
        actionRequests: [{ action_id: "action_1", action_type: "github.issue.comment", status: "pending", trace_id: "trace_1" }],
        approvalTickets: [{ approval_id: "approval_1", summary: "awaiting approval", status: "pending", trace_id: "trace_1" }],
        approvalDiagnostics: [{ approval_id: "approval_1", status: "pending", trace_id: "trace_1" }],
        auditRecords: [{ audit_id: "audit_1", stage: "approval", status: "pending", trace_id: "trace_1" }],
        traceId: "trace_1",
        timeline: [
          {
            kind: "events",
            item: {
              event_id: "evt_1",
              trace_id: "trace_1",
              event_type: "demo.event",
            },
          },
          {
            kind: "workflowRuns",
            item: {
              workflow_run_id: "run_1",
              trace_id: "trace_1",
              status: "paused",
              workflow_name: "handle_github_issue_opened",
            },
          },
          {
            kind: "actionRequests",
            item: {
              action_id: "action_1",
              trace_id: "trace_1",
              action_type: "github.issue.comment",
              status: "pending",
            },
          },
          {
            kind: "approvalTickets",
            item: {
              approval_id: "approval_1",
              trace_id: "trace_1",
              status: "pending",
              summary: "awaiting approval",
            },
          },
          {
            kind: "auditRecords",
            item: {
              audit_id: "audit_1",
              trace_id: "trace_1",
              stage: "approval",
              status: "pending",
              summary: "audit pending",
            },
          },
        ],
        resumeEligible: true,
      } as TData);
    }
    if (request.action === "workflows.resume") {
      this.resumedWorkflowIds.push(String((request.payload as { workflowRunId?: string })?.workflowRunId ?? ""));
      return createBridgeSuccess(request, {
        workflowRun: {
          workflow_run_id: "run_1",
          trace_id: "trace_1",
          plugin_name: "github_phase1",
          workflow_name: "handle_github_issue_opened",
          status: "running",
          current_step: "manual_resume_requested",
          result_summary: "resume requested by gui.operator",
        },
        workflowDiagnostic: {
          workflow_run_id: "run_1",
          workflow_status: "running",
          reasoning: { summary: "workflow recommends operator review" },
          recommendation: { count: 1 },
          approval: { status: "pending" },
          execution: { status: "not_executed" },
        },
        actionRequests: [{ action_id: "action_1", action_type: "github.issue.comment", status: "pending", trace_id: "trace_1" }],
        approvalTickets: [{ approval_id: "approval_1", summary: "awaiting approval", status: "pending", trace_id: "trace_1" }],
        approvalDiagnostics: [{ approval_id: "approval_1", status: "pending", trace_id: "trace_1" }],
        auditRecords: [{ audit_id: "audit_1", stage: "approval", status: "pending", trace_id: "trace_1" }, { audit_id: "audit_2", stage: "workflow_resume", status: "requested", trace_id: "trace_1" }],
        traceId: "trace_1",
        timeline: [
          {
            kind: "events",
            item: {
              event_id: "evt_1",
              trace_id: "trace_1",
              event_type: "demo.event",
            },
          },
          {
            kind: "workflowRuns",
            item: {
              workflow_run_id: "run_1",
              trace_id: "trace_1",
              status: "running",
              workflow_name: "handle_github_issue_opened",
              current_step: "manual_resume_requested",
            },
          },
          {
            kind: "actionRequests",
            item: {
              action_id: "action_1",
              trace_id: "trace_1",
              action_type: "github.issue.comment",
              status: "pending",
            },
          },
          {
            kind: "approvalTickets",
            item: {
              approval_id: "approval_1",
              trace_id: "trace_1",
              status: "pending",
              summary: "awaiting approval",
            },
          },
          {
            kind: "auditRecords",
            item: {
              audit_id: "audit_2",
              trace_id: "trace_1",
              stage: "workflow_resume",
              status: "requested",
              summary: "resume requested",
            },
          },
        ],
        resumeEligible: false,
        resumeRequested: true,
      } as TData);
    }
    return createBridgeSuccess(request, {} as TData);
  }

  subscribe(_listener: (event: BridgeEvent<Record<string, unknown>>) => void) {
    return () => {};
  }
}

describe("sessions-runs-trace-page", () => {
  it("renders threads, runs and trace timeline from control ui state", async () => {
    const adapter = new SessionsHostAdapter();
    const client = new BridgeClient(adapter);
    const element = document.createElement("sessions-runs-trace-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("Thread One");
    expect(element.shadowRoot.textContent).toContain("run_1");
    expect(element.shadowRoot.textContent).toContain("trace_1");
    expect(element.shadowRoot.textContent).toContain("handle_github_issue_opened");
    expect(element.shadowRoot.textContent).toContain("workflow recommends operator review");
    expect(
      element.shadowRoot.querySelector("[data-testid='workflow-actions-list']")?.textContent ?? "",
    ).toContain("github.issue.comment");
    expect(
      element.shadowRoot.querySelector("[data-testid='workflow-approvals-list']")?.textContent ?? "",
    ).toContain("awaiting approval");
    expect(element.shadowRoot.querySelectorAll("[data-testid='trace-item']").length).toBeGreaterThan(0);
  });

  it("supports resume session action and updates active marker", async () => {
    const adapter = new SessionsHostAdapter();
    const client = new BridgeClient(adapter);
    const element = document.createElement("sessions-runs-trace-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);

    const resumedEvent = new Promise<string>((resolve) => {
      element.addEventListener("session-resumed", ((event: CustomEvent<{ threadId: string }>) => {
        resolve(event.detail.threadId);
      }) as EventListener, { once: true });
    });

    const buttons = Array.from(element.shadowRoot.querySelectorAll("[data-testid='resume-thread']")) as HTMLButtonElement[];
    buttons[1]?.click();
    await flushUi(element);

    await expect(resumedEvent).resolves.toBe("thread_2");
    expect(adapter.resumedThreadIds).toContain("thread_2");
    expect(feedbackText(element.shadowRoot)).toContain("已恢复会话 thread_2");
  });

  it("loads workflow detail and supports workflow resume action", async () => {
    const adapter = new SessionsHostAdapter();
    const client = new BridgeClient(adapter);
    const element = document.createElement("sessions-runs-trace-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);
    await flushUi(element);

    const resumeButton = element.shadowRoot.querySelector("[data-testid='resume-workflow']") as HTMLButtonElement;
    resumeButton.click();
    await flushUi(element);

    expect(adapter.resumedWorkflowIds).toContain("run_1");
    expect(element.shadowRoot.textContent).toContain("manual_resume_requested");
    expect(feedbackText(element.shadowRoot)).toContain("已发起 resume 请求");
  });

  it("applies routed workflow context and timeline scope on load", async () => {
    const adapter = new SessionsHostAdapter();
    const client = new BridgeClient(adapter);
    const element = document.createElement("sessions-runs-trace-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      initialTraceId: string;
      initialWorkflowRunId: string;
      initialTimelineScope: "all" | "workflowRuns" | "actionRequests" | "approvalTickets" | "auditRecords";
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    element.bridgeClient = client;
    element.initialTraceId = "trace_1";
    element.initialWorkflowRunId = "run_1";
    element.initialTimelineScope = "auditRecords";
    document.body.appendChild(element);
    await flushUi(element);
    await flushUi(element);

    const workflowDetailText = element.shadowRoot.querySelector("[data-testid='workflow-detail']")?.textContent ?? "";
    expect(workflowDetailText).toContain("run_1");
    expect(workflowDetailText).toContain("workflow recommends operator review");

    const traceText = element.shadowRoot.querySelector("[data-testid='trace-timeline']")?.textContent ?? "";
    expect(traceText).toContain("audit pending");
    expect(traceText).not.toContain("github.issue.comment");

    const scopeChip = element.shadowRoot.querySelector("[data-testid='timeline-scope-auditRecords']");
    expect(scopeChip?.className).toContain("active");
  });

  it("filters timeline by selected causality scope", async () => {
    const adapter = new SessionsHostAdapter();
    const client = new BridgeClient(adapter);
    const element = document.createElement("sessions-runs-trace-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);
    await flushUi(element);

    const approvalScope = element.shadowRoot.querySelector(
      "[data-testid='timeline-scope-approvalTickets']",
    ) as HTMLButtonElement;
    approvalScope.click();
    await flushUi(element);

    const traceText = element.shadowRoot.querySelector("[data-testid='trace-timeline']")?.textContent ?? "";
    expect(traceText).toContain("awaiting approval");
    expect(traceText).not.toContain("github.issue.comment");
  });

  it("opens workflow detail from trace timeline inspect", async () => {
    const adapter = new SessionsHostAdapter();
    const client = new BridgeClient(adapter);
    const element = document.createElement("sessions-runs-trace-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);
    await flushUi(element);

    const button = element.shadowRoot.querySelector("[data-testid='inspect-trace-workflow']") as HTMLButtonElement;
    button.click();
    await flushUi(element);

    const workflowDetailText = element.shadowRoot.querySelector("[data-testid='workflow-detail']")?.textContent ?? "";
    expect(workflowDetailText).toContain("handle_github_issue_opened");
    expect(workflowDetailText).toContain("run_1");
    const scopeChip = element.shadowRoot.querySelector("[data-testid='timeline-scope-workflowRuns']");
    expect(scopeChip?.className).toContain("active");
  });

  it("emits approval navigation context from trace timeline inspect", async () => {
    const adapter = new SessionsHostAdapter();
    const client = new BridgeClient(adapter);
    const element = document.createElement("sessions-runs-trace-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);
    await flushUi(element);

    const navigationEvent = new Promise<{
      route: string;
      traceId: string;
      approvalId?: string;
      source?: string;
    }>((resolve) => {
      element.addEventListener(
        "navigate-control-context",
        ((event: CustomEvent<{ route: string; traceId: string; approvalId?: string; source?: string }>) => {
          resolve(event.detail);
        }) as EventListener,
        { once: true },
      );
    });

    const button = element.shadowRoot.querySelector("[data-testid='inspect-trace-approvalTickets']") as HTMLButtonElement;
    button.click();
    await flushUi(element);

    await expect(navigationEvent).resolves.toEqual({
      route: "approvals",
      traceId: "trace_1",
      approvalId: "approval_1",
      source: "workflow-detail",
    });
  });

  it("emits approval navigation context from workflow approval chain", async () => {
    const adapter = new SessionsHostAdapter();
    const client = new BridgeClient(adapter);
    const element = document.createElement("sessions-runs-trace-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);
    await flushUi(element);

    const navigationEvent = new Promise<{
      route: string;
      traceId: string;
      approvalId?: string;
      source?: string;
    }>((resolve) => {
      element.addEventListener(
        "navigate-control-context",
        ((event: CustomEvent<{ route: string; traceId: string; approvalId?: string; source?: string }>) => {
          resolve(event.detail);
        }) as EventListener,
        { once: true },
      );
    });

    const button = element.shadowRoot.querySelector("[data-testid='open-approval-context']") as HTMLButtonElement;
    button.click();
    await flushUi(element);

    await expect(navigationEvent).resolves.toEqual({
      route: "approvals",
      traceId: "trace_1",
      approvalId: "approval_1",
      source: "workflow-detail",
    });
  });

  it("emits action navigation context from workflow action chain", async () => {
    const adapter = new SessionsHostAdapter();
    const client = new BridgeClient(adapter);
    const element = document.createElement("sessions-runs-trace-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);
    await flushUi(element);

    const navigationEvent = new Promise<{
      route: string;
      traceId: string;
      actionId?: string;
      source?: string;
    }>((resolve) => {
      element.addEventListener(
        "navigate-control-context",
        ((event: CustomEvent<{ route: string; traceId: string; actionId?: string; source?: string }>) => {
          resolve(event.detail);
        }) as EventListener,
        { once: true },
      );
    });

    const button = element.shadowRoot.querySelector("[data-testid='open-action-context']") as HTMLButtonElement;
    button.click();
    await flushUi(element);

    await expect(navigationEvent).resolves.toEqual({
      route: "approvals",
      traceId: "trace_1",
      actionId: "action_1",
      source: "workflow-detail",
    });
  });

  it("emits audit navigation context from workflow audit trail", async () => {
    const adapter = new SessionsHostAdapter();
    const client = new BridgeClient(adapter);
    const element = document.createElement("sessions-runs-trace-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);
    await flushUi(element);

    const navigationEvent = new Promise<{
      route: string;
      traceId: string;
      auditId?: string;
      source?: string;
    }>((resolve) => {
      element.addEventListener(
        "navigate-control-context",
        ((event: CustomEvent<{ route: string; traceId: string; auditId?: string; source?: string }>) => {
          resolve(event.detail);
        }) as EventListener,
        { once: true },
      );
    });

    const button = element.shadowRoot.querySelector("[data-testid='open-audit-context']") as HTMLButtonElement;
    button.click();
    await flushUi(element);

    await expect(navigationEvent).resolves.toEqual({
      route: "approvals",
      traceId: "trace_1",
      auditId: "audit_1",
      source: "workflow-detail",
    });
  });

  it("falls back to local timeline when gateway trace endpoint fails", async () => {
    const adapter = new SessionsHostAdapter();
    adapter.gatewayTraceOk = false;
    const client = new BridgeClient(adapter);
    const element = document.createElement("sessions-runs-trace-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);

    const button = element.shadowRoot.querySelector("[data-testid='load-trace-gateway']") as HTMLButtonElement;
    button.click();
    await flushUi(element);

    expect(feedbackText(element.shadowRoot)).toContain("trace service unavailable");
    expect(element.shadowRoot.querySelectorAll("[data-testid='trace-item']").length).toBeGreaterThan(0);
  });
});
