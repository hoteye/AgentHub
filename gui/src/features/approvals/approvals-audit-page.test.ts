import { describe, expect, it } from "vitest";

import { BridgeClient } from "../../bridge/client.ts";
import type { HostAdapter } from "../../shared/api/mock-host.ts";
import {
  createBridgeFailure,
  createBridgeSuccess,
  normalizeBridgeEvent,
  type ApprovalSummary,
  type BridgeEvent,
  type BridgeError,
  type BridgeRequest,
  type BridgeResponse,
} from "../../shared/types/bridge.ts";
import "./approvals-audit-page.ts";

type AuditRecord = {
  audit_id?: string | null;
  trace_id: string;
  summary: string;
  stage?: string;
  status?: string;
  action_id?: string | null;
  approval_id?: string | null;
};

class MutableApprovalHostAdapter implements HostAdapter {
  approvals: ApprovalSummary[] = [];
  records: AuditRecord[] = [];
  actionRequests: Array<Record<string, unknown>> = [];
  workflowRuns: Array<Record<string, unknown>> = [];
  failResolve: BridgeError | null = null;
  failAuditList: BridgeError | null = null;
  failApprovalsApi = false;
  failTimelineApi = false;
  private readonly listeners = new Set<(event: BridgeEvent<Record<string, unknown>>) => void>();

  async request<TData = unknown>(request: BridgeRequest<unknown>): Promise<BridgeResponse<TData>> {
    if (request.action === "approval.list") {
      return createBridgeSuccess(request, {
        approvals: this.approvals.filter((item) => item.status === "pending"),
      } as TData);
    }
    if (request.action === "approvals.list") {
      if (this.failApprovalsApi) {
        return createBridgeFailure(request, {
          code: "approvals.list.failed",
          message: "approvals api unavailable",
          retryable: true,
        }) as BridgeResponse<TData>;
      }
      return createBridgeSuccess(request, {
        approvalTickets: this.approvals.filter((item) => item.status === "pending"),
      } as TData);
    }
    if (request.action === "audit.list") {
      if (this.failAuditList) {
        return createBridgeFailure(request, this.failAuditList) as BridgeResponse<TData>;
      }
      const traceId = String((request.payload as { trace_id?: string })?.trace_id ?? "");
      return createBridgeSuccess(request, {
        records: this.records.filter((item) => (traceId ? item.trace_id === traceId : true)),
      } as TData);
    }
    if (request.action === "approvals.get") {
      if (this.failApprovalsApi) {
        return createBridgeFailure(request, {
          code: "approvals.get.failed",
          message: "approvals api unavailable",
          retryable: true,
        }) as BridgeResponse<TData>;
      }
      const payload = request.payload as { approvalId?: string };
      const approval = this.approvals.find((item) => item.approval_id === payload.approvalId);
      const actionRequest = this.actionRequests.find((item) => {
        return String(item.action_id ?? "") === String(approval?.action_id ?? "");
      });
      return createBridgeSuccess(request, {
        approvalTicket: approval ?? null,
        actionRequest: actionRequest ?? null,
        auditRecords: this.records.filter((item) => item.trace_id === String(approval?.trace_id ?? "")),
      } as TData);
    }
    if (request.action === "gateway.trace.timeline") {
      if (this.failTimelineApi) {
        return createBridgeFailure(request, {
          code: "gateway.trace.timeline.failed",
          message: "timeline api unavailable",
          retryable: true,
        }) as BridgeResponse<TData>;
      }
      const payload = request.payload as { traceId?: string };
      const traceId = String(payload.traceId ?? "");
      const approval = this.approvals.find((item) => item.trace_id === traceId);
      const actionRequest = this.actionRequests.find((item) => {
        return String(item.action_id ?? "") === String(approval?.action_id ?? "");
      });
      const workflowRun = this.workflowRuns.find((item) => String(item.trace_id ?? "") === traceId);
      return createBridgeSuccess(request, {
        traceId,
        timeline: [
          { kind: "workflowRuns", item: workflowRun ?? {} },
          { kind: "approvalTickets", item: approval ?? {} },
          { kind: "actionRequests", item: actionRequest ?? {} },
          ...(this.records
            .filter((item) => item.trace_id === traceId)
            .map((record) => ({ kind: "auditRecords", item: record }))),
        ],
      } as TData);
    }
    if (request.action === "workflows.list") {
      const payload = request.payload as { traceId?: string };
      const traceId = String(payload.traceId ?? "");
      return createBridgeSuccess(request, {
        workflowRuns: this.workflowRuns.filter((item) => (traceId ? String(item.trace_id ?? "") === traceId : true)),
      } as TData);
    }
    if (request.action === "workflows.resume") {
      const payload = request.payload as { workflowRunId?: string };
      const workflowRun = this.workflowRuns.find((item) => String(item.workflow_run_id ?? "") === String(payload.workflowRunId ?? ""));
      if (!workflowRun) {
        return createBridgeFailure(request, {
          code: "workflows.resume.failed",
          message: "unknown workflow",
          retryable: false,
        }) as BridgeResponse<TData>;
      }
      workflowRun.status = "running";
      workflowRun.current_step = "manual_resume_requested";
      workflowRun.result_summary = "resume requested by gui.operator";
      const traceId = String(workflowRun.trace_id ?? "");
      this.records.unshift({
        audit_id: "audit_resume",
        trace_id: traceId,
        summary: "workflow resume requested",
        stage: "workflow_resume",
        status: "requested",
      });
      return createBridgeSuccess(request, {
        workflowRun,
        traceId,
        auditRecords: this.records.filter((item) => item.trace_id === traceId),
        timeline: [
          { kind: "workflowRuns", item: workflowRun },
          ...this.records
            .filter((item) => item.trace_id === traceId)
            .map((record) => ({ kind: "auditRecords", item: record })),
        ],
        resumeEligible: false,
      } as TData);
    }
    if (request.action === "approval.resolve") {
      if (this.failResolve) {
        return createBridgeFailure(request, this.failResolve) as BridgeResponse<TData>;
      }
      const payload = request.payload as { approval_id?: string; decision?: "approved" | "rejected" };
      const approval = this.approvals.find((item) => item.approval_id === payload.approval_id);
      if (approval) {
        approval.status = payload.decision ?? "approved";
        this.records.unshift({
          trace_id: approval.trace_id,
          summary: `${approval.title} ${approval.status}`,
          stage: "approval",
          status: approval.status,
          approval_id: approval.approval_id,
          action_id: approval.action_id ?? null,
        });
      }
      this.emit(
        normalizeBridgeEvent({
          request_id: request.request_id,
          kind: "approval_resolved",
          name: "approval_resolved",
          summary: "Approval resolved",
          payload: {
            approval_id: payload.approval_id ?? "",
            status: payload.decision ?? "approved",
          },
        }),
      );
      return createBridgeSuccess(request, {
        accepted: true,
        approval_id: payload.approval_id ?? "",
        status: payload.decision ?? "approved",
      } as TData);
    }
    if (request.action === "approvals.resolve") {
      if (this.failResolve) {
        return createBridgeFailure(request, this.failResolve) as BridgeResponse<TData>;
      }
      const payload = request.payload as { approvalId?: string; decision?: "approve" | "reject" };
      const decision = payload.decision === "reject" ? "rejected" : "approved";
      return this.request({
        ...request,
        action: "approval.resolve",
        payload: {
          approval_id: payload.approvalId ?? "",
          decision,
        },
      } as BridgeRequest<unknown>);
    }
    throw new Error(`unsupported action ${request.action}`);
  }

  subscribe(listener: (event: BridgeEvent<Record<string, unknown>>) => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  emit(event: BridgeEvent<Record<string, unknown>>) {
    for (const listener of this.listeners) {
      listener(event);
    }
  }
}

function createApproval(approvalId: string, title: string, traceId: string): ApprovalSummary {
  return {
    approval_id: approvalId,
    action_id: `action_${approvalId}`,
    title,
    risk: "high",
    trace_id: traceId,
    status: "pending",
    summary: `${title} summary`,
    requested_at: "2026-03-28T08:00:00Z",
    requested_by: "tester",
    reason: `${title} reason`,
  };
}

function createActionRequest(actionId: string, traceId: string): Record<string, unknown> {
  return {
    action_id: actionId,
    trace_id: traceId,
    action_type: "github.issue.close",
    status: "pending",
    summary: "Close GitHub issue after approval",
  };
}

function createWorkflowRun(runId: string, traceId: string, status = "paused"): Record<string, unknown> {
  return {
    workflow_run_id: runId,
    trace_id: traceId,
    workflow_name: "handle_github_issue_opened",
    plugin_name: "github_phase1",
    status,
    current_step: status === "paused" ? "paused_for_operator_review" : "manual_resume_requested",
    result_summary: status === "paused" ? "workflow waiting for operator" : "resume requested by gui.operator",
  };
}

async function flushUi(element: { updateComplete?: Promise<unknown> }) {
  for (let index = 0; index < 10; index += 1) {
    await Promise.resolve();
    await element.updateComplete;
  }
}

function feedbackText(root: ShadowRoot): string {
  const element = root.querySelector("[data-testid='operation-feedback']") as HTMLElement & { shadowRoot?: ShadowRoot };
  return element?.shadowRoot?.textContent ?? "";
}

describe("approvals-audit-page", () => {
  it("loads approval list, detail panel, and audit records", async () => {
    const element = document.createElement("approvals-audit-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("待审批");
    expect(element.shadowRoot.textContent).toContain("GitHub issue close");
    expect(element.shadowRoot.textContent).toContain("审批详情与审计链");
    expect(element.shadowRoot.textContent).toContain("Action Request");
    expect(element.shadowRoot.querySelector("[data-testid='approval-detail']")?.textContent).toContain("requested by");
    expect(element.shadowRoot.querySelectorAll("[data-testid='audit-record']").length).toBeGreaterThan(0);
  });

  it("shows connector landing banner when opened from plugins surface", async () => {
    const adapter = new MutableApprovalHostAdapter();
    adapter.approvals = [createApproval("approval_1", "Close issue", "trace_1")];

    const element = document.createElement("approvals-audit-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      initialConnectorKey?: string;
      initialContextSource?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(adapter);
    element.initialConnectorKey = "github_webhook";
    element.initialContextSource = "plugins-connectors";
    document.body.appendChild(element);
    await flushUi(element);

    const banner = element.shadowRoot.querySelector("[data-testid='approvals-context-banner']") as HTMLElement;
    expect(banner.textContent).toContain("handoff=plugins-connectors");
    expect(banner.textContent).toContain("connector=github_webhook");
    const limitation = element.shadowRoot.querySelector("[data-testid='approvals-context-limitation']") as HTMLElement;
    expect(limitation.textContent).toContain("不按 connector 做独立过滤");
  });

  it("emits connector surface navigation from landing banner", async () => {
    const adapter = new MutableApprovalHostAdapter();
    adapter.approvals = [createApproval("approval_1", "Close issue", "trace_1")];

    const element = document.createElement("approvals-audit-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      initialConnectorKey?: string;
      initialContextSource?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(adapter);
    element.initialConnectorKey = "github_webhook";
    element.initialContextSource = "plugins-connectors";
    document.body.appendChild(element);
    await flushUi(element);

    const navigation = new Promise<Record<string, unknown>>((resolve) => {
      element.addEventListener(
        "navigate-control-context",
        ((event: CustomEvent<Record<string, unknown>>) => resolve(event.detail)) as EventListener,
        { once: true },
      );
    });
    const openAuth = element.shadowRoot.querySelector("[data-testid='approvals-open-auth']") as HTMLButtonElement;
    openAuth.click();

    await expect(navigation).resolves.toEqual({
      route: "auth",
      connectorKey: "github_webhook",
      source: "approvals-context",
    });
  });

  it("renders causality panels with action request and trace timeline", async () => {
    const adapter = new MutableApprovalHostAdapter();
    adapter.approvals = [createApproval("approval_causal", "Causal action", "trace_causal")];
    adapter.workflowRuns = [createWorkflowRun("run_causal", "trace_causal")];
    adapter.records = [
      {
        audit_id: "audit_causal",
        trace_id: "trace_causal",
        summary: "Causal audit",
        stage: "approval",
        status: "pending",
      },
    ];
    adapter.actionRequests = [createActionRequest("action_approval_causal", "trace_causal")];

    const element = document.createElement("approvals-audit-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(adapter);
    document.body.appendChild(element);
    await flushUi(element);

    const actionRequestText = element.shadowRoot.querySelector("[data-testid='action-request-detail']")?.textContent ?? "";
    expect(actionRequestText).toContain("linked");
    expect(actionRequestText).toContain("action_approval_causal");

    const timelineItems = element.shadowRoot.querySelectorAll("[data-testid='trace-timeline-item']");
    expect(timelineItems.length).toBeGreaterThan(0);
    expect(element.shadowRoot.querySelector("[data-testid='workflow-context-detail']")?.textContent).toContain("run_causal");
  });

  it("applies routed trace and operator context on load and update", async () => {
    const adapter = new MutableApprovalHostAdapter();
    adapter.approvals = [
      createApproval("approval_alpha", "Alpha action", "trace_alpha"),
      createApproval("approval_beta", "Beta action", "trace_beta"),
    ];
    adapter.workflowRuns = [
      createWorkflowRun("run_alpha", "trace_alpha"),
      createWorkflowRun("run_beta", "trace_beta"),
    ];
    adapter.records = [
      { audit_id: "audit_alpha", trace_id: "trace_alpha", summary: "Alpha audit", stage: "approval", status: "pending" },
      { audit_id: "audit_beta", trace_id: "trace_beta", summary: "Beta audit", stage: "approval", status: "pending" },
    ];
    adapter.actionRequests = [
      createActionRequest("action_approval_alpha", "trace_alpha"),
      createActionRequest("action_approval_beta", "trace_beta"),
    ];

    const element = document.createElement("approvals-audit-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      initialTraceFilter: string;
      initialApprovalId: string;
      initialActionId: string;
      initialAuditId: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(adapter);
    element.initialTraceFilter = "trace_beta";
    element.initialApprovalId = "approval_beta";
    element.initialActionId = "action_approval_beta";
    element.initialAuditId = "audit_beta";
    document.body.appendChild(element);
    await flushUi(element);

    const traceInput = element.shadowRoot.querySelector("[data-testid='trace-filter']") as HTMLInputElement;
    expect(traceInput.value).toBe("trace_beta");
    expect(element.shadowRoot.querySelector("[data-testid='approval-detail']")?.textContent).toContain("Beta action");
    const actionDetail = element.shadowRoot.querySelector("[data-testid='action-request-detail']");
    expect(actionDetail?.textContent).toContain("action_approval_beta");
    expect(actionDetail?.className).toContain("selected");
    const records = element.shadowRoot.querySelectorAll("[data-testid='audit-record']");
    expect(records[0]?.textContent).toContain("Beta audit");
    expect(records[0]?.className).toContain("selected");

    element.initialTraceFilter = "trace_alpha";
    element.initialApprovalId = "approval_alpha";
    element.initialActionId = "action_approval_alpha";
    element.initialAuditId = "audit_alpha";
    await flushUi(element);

    expect(traceInput.value).toBe("trace_alpha");
    expect(element.shadowRoot.querySelector("[data-testid='approval-detail']")?.textContent).toContain("Alpha action");
    const refreshedActionDetail = element.shadowRoot.querySelector("[data-testid='action-request-detail']");
    expect(refreshedActionDetail?.textContent).toContain("action_approval_alpha");
    expect(refreshedActionDetail?.className).toContain("selected");
    const refreshedRecords = element.shadowRoot.querySelectorAll("[data-testid='audit-record']");
    expect(refreshedRecords[0]?.textContent).toContain("Alpha audit");
    expect(refreshedRecords[0]?.className).toContain("selected");
    expect(element.shadowRoot.querySelector("[data-testid='workflow-context-detail']")?.textContent).toContain("run_alpha");
  });

  it("supports workflow resume from operator context", async () => {
    const adapter = new MutableApprovalHostAdapter();
    adapter.approvals = [createApproval("approval_resume", "Resume action", "trace_resume")];
    adapter.workflowRuns = [createWorkflowRun("run_resume", "trace_resume", "paused")];
    adapter.records = [
      { audit_id: "audit_resume_0", trace_id: "trace_resume", summary: "pending audit", stage: "approval", status: "pending" },
    ];
    adapter.actionRequests = [createActionRequest("action_approval_resume", "trace_resume")];

    const element = document.createElement("approvals-audit-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(adapter);
    document.body.appendChild(element);
    await flushUi(element);

    const resumeButton = element.shadowRoot.querySelector("[data-testid='resume-workflow-context']") as HTMLButtonElement;
    expect(resumeButton.disabled).toBe(false);
    resumeButton.click();
    await flushUi(element);

    expect(element.shadowRoot.querySelector("[data-testid='workflow-context-detail']")?.textContent).toContain(
      "manual_resume_requested",
    );
    expect(feedbackText(element.shadowRoot)).toContain("workflow run_resume 已发起 resume 请求");
    expect(element.shadowRoot.textContent).toContain("workflow resume requested");
  });

  it("emits sessions navigation context from workflow and action drill-down", async () => {
    const adapter = new MutableApprovalHostAdapter();
    adapter.approvals = [createApproval("approval_nav", "Nav action", "trace_nav")];
    adapter.workflowRuns = [createWorkflowRun("run_nav", "trace_nav", "paused")];
    adapter.records = [
      { audit_id: "audit_nav", trace_id: "trace_nav", summary: "Nav audit", stage: "approval", status: "pending" },
    ];
    adapter.actionRequests = [createActionRequest("action_approval_nav", "trace_nav")];

    const element = document.createElement("approvals-audit-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(adapter);
    document.body.appendChild(element);
    await flushUi(element);

    const workflowEvent = new Promise<Record<string, unknown>>((resolve) => {
      element.addEventListener(
        "navigate-control-context",
        ((event: CustomEvent<Record<string, unknown>>) => resolve(event.detail)) as EventListener,
        { once: true },
      );
    });
    const workflowButton = element.shadowRoot.querySelector("[data-testid='open-workflow-in-sessions']") as HTMLButtonElement;
    workflowButton.click();
    await expect(workflowEvent).resolves.toEqual({
      route: "sessions",
      traceId: "trace_nav",
      workflowRunId: "run_nav",
      timelineScope: "workflowRuns",
      source: "approvals-context",
    });

    const actionEvent = new Promise<Record<string, unknown>>((resolve) => {
      element.addEventListener(
        "navigate-control-context",
        ((event: CustomEvent<Record<string, unknown>>) => resolve(event.detail)) as EventListener,
        { once: true },
      );
    });
    const actionButton = element.shadowRoot.querySelector("[data-testid='open-action-in-sessions']") as HTMLButtonElement;
    actionButton.click();
    await expect(actionEvent).resolves.toEqual({
      route: "sessions",
      traceId: "trace_nav",
      workflowRunId: "run_nav",
      timelineScope: "actionRequests",
      source: "approvals-context",
    });
  });

  it("inspects timeline items and focuses matched operator context", async () => {
    const adapter = new MutableApprovalHostAdapter();
    adapter.approvals = [createApproval("approval_focus", "Focus action", "trace_focus")];
    adapter.workflowRuns = [createWorkflowRun("run_focus", "trace_focus")];
    adapter.records = [
      { audit_id: "audit_focus", trace_id: "trace_focus", summary: "Focus audit", stage: "approval", status: "pending" },
    ];
    adapter.actionRequests = [createActionRequest("action_approval_focus", "trace_focus")];

    const element = document.createElement("approvals-audit-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(adapter);
    document.body.appendChild(element);
    await flushUi(element);

    const timelineItems = Array.from(
      element.shadowRoot.querySelectorAll("[data-testid='trace-timeline-item']"),
    ) as HTMLElement[];
    const inspectButtons = Array.from(
      element.shadowRoot.querySelectorAll("[data-testid='inspect-trace-timeline-item']"),
    ) as HTMLButtonElement[];
    const actionIndex = timelineItems.findIndex((item) => item.textContent?.includes("actionRequests"));
    inspectButtons[actionIndex]?.click();
    await flushUi(element);
    expect(element.shadowRoot.querySelector("[data-testid='action-request-detail']")?.className).toContain("selected");

    const auditIndex = timelineItems.findIndex((item) => item.textContent?.includes("auditRecords"));
    inspectButtons[auditIndex]?.click();
    await flushUi(element);
    const records = element.shadowRoot.querySelectorAll("[data-testid='audit-record']");
    expect(records[0]?.className).toContain("selected");
  });

  it("filters audit records by trace", async () => {
    const element = document.createElement("approvals-audit-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const input = element.shadowRoot.querySelector("[data-testid='trace-filter']") as HTMLInputElement;
    input.value = "trace_demo_002";
    input.dispatchEvent(new Event("input"));
    await flushUi(element);

    const records = Array.from(element.shadowRoot.querySelectorAll("[data-testid='audit-record']")).map(
      (item) => item.textContent ?? "",
    );
    expect(records).toHaveLength(2);
    expect(records.every((item) => item.includes("trace_demo_002"))).toBe(true);
  });

  it("resolves approval entries and keeps the decision banner", async () => {
    const element = document.createElement("approvals-audit-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const approveButton = element.shadowRoot.querySelector("button:not(.ghost)") as HTMLButtonElement;
    approveButton.click();
    await flushUi(element);

    const feedback = element.shadowRoot.querySelector("[data-testid='operation-feedback']") as HTMLElement & {
      shadowRoot?: ShadowRoot;
    };
    expect(feedbackText(element.shadowRoot)).toContain("approval_demo_001 已批准");
    expect(feedback.shadowRoot?.querySelector(".wrapper")?.className).toContain("success");
  });

  it("reloads from bridge events", async () => {
    const adapter = new MutableApprovalHostAdapter();
    adapter.approvals = [createApproval("approval_alpha", "Alpha action", "trace_alpha")];
    adapter.records = [{ trace_id: "trace_alpha", summary: "Alpha audit", stage: "approval", status: "pending" }];

    const element = document.createElement("approvals-audit-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(adapter);
    document.body.appendChild(element);
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("Alpha action");

    adapter.approvals.unshift(createApproval("approval_beta", "Beta action", "trace_beta"));
    adapter.records.unshift({ trace_id: "trace_beta", summary: "Beta audit", stage: "approval", status: "pending" });
    adapter.emit(
      normalizeBridgeEvent({
        request_id: "req_beta",
        kind: "approval_requested",
        name: "approval_requested",
        summary: "Beta action pending",
        payload: { approval_id: "approval_beta", trace_id: "trace_beta", status: "pending" },
      }),
    );
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("Beta action");
  });

  it("shows error feedback when approval resolution fails", async () => {
    const adapter = new MutableApprovalHostAdapter();
    adapter.approvals = [createApproval("approval_fail", "Fail action", "trace_fail")];
    adapter.records = [{ trace_id: "trace_fail", summary: "Fail audit", stage: "approval", status: "pending" }];
    adapter.failResolve = {
      code: "approval.resolve.failed",
      message: "审批处理失败，请稍后重试",
      retryable: true,
    };

    const element = document.createElement("approvals-audit-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(adapter);
    document.body.appendChild(element);
    await flushUi(element);

    const approveButton = element.shadowRoot.querySelector("button:not(.ghost)") as HTMLButtonElement;
    approveButton.click();
    await flushUi(element);

    const feedback = element.shadowRoot.querySelector("[data-testid='operation-feedback']") as HTMLElement & {
      shadowRoot?: ShadowRoot;
    };
    expect(feedbackText(element.shadowRoot)).toContain("审批处理失败，请稍后重试");
    expect(feedback.shadowRoot?.querySelector(".wrapper")?.className).toContain("error");
    expect(element.shadowRoot.textContent).toContain("Fail action");
  });

  it("shows error feedback when audit refresh fails", async () => {
    const adapter = new MutableApprovalHostAdapter();
    adapter.approvals = [createApproval("approval_alpha", "Alpha action", "trace_alpha")];
    adapter.records = [{ trace_id: "trace_alpha", summary: "Alpha audit", stage: "approval", status: "pending" }];

    const element = document.createElement("approvals-audit-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(adapter);
    document.body.appendChild(element);
    await flushUi(element);

    adapter.failAuditList = {
      code: "audit.list.failed",
      message: "审计记录刷新失败",
      retryable: true,
    };
    adapter.emit(
      normalizeBridgeEvent({
        request_id: "req_audit_fail",
        kind: "audit_written",
        name: "audit_written",
        summary: "Audit refresh requested",
        payload: { trace_id: "trace_alpha" },
      }),
    );
    await flushUi(element);

    const feedback = element.shadowRoot.querySelector("[data-testid='operation-feedback']") as HTMLElement & {
      shadowRoot?: ShadowRoot;
    };
    expect(feedbackText(element.shadowRoot)).toContain("审计记录刷新失败");
    expect(feedback.shadowRoot?.querySelector(".wrapper")?.className).toContain("error");
  });
});
