import { LitElement, type PropertyValues, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { BridgeClient, createMockBridgeClient } from "../../bridge/client.ts";
import "../../shared/components/operation-feedback-view.ts";
import {
  errorFeedback,
  feedbackFromBridgeResponse,
  neutralFeedback,
  successFeedback,
  warningFeedback,
  type OperationFeedback,
} from "../../shared/state/operation-feedback.ts";
import type { ApprovalSummary, BridgeEvent } from "../../shared/types/bridge.ts";

type AuditRecord = {
  audit_id?: string | null;
  trace_id: string;
  summary: string;
  stage?: string;
  status?: string;
  action_id?: string | null;
  approval_id?: string | null;
};

type ApprovalDetailResponse = {
  approvalTicket?: ApprovalSummary;
  actionRequest?: Record<string, unknown> | null;
  auditRecords?: AuditRecord[];
};

type TraceTimelineEntry = {
  kind: string;
  item: Record<string, unknown>;
};

type WorkflowContext = {
  workflowRunId: string;
  workflowName: string;
  pluginName: string;
  status: string;
  currentStep: string;
  summary: string;
  resumeEligible: boolean;
};

type SessionsNavigationDetail = {
  route: "sessions";
  traceId: string;
  workflowRunId?: string;
  timelineScope?: "all" | "workflowRuns" | "actionRequests" | "approvalTickets" | "auditRecords";
  source: "approvals-context";
};

type ConnectorNavigationDetail = {
  route: "auth" | "plugins" | "settings";
  connectorKey?: string;
  source: "approvals-context";
};

@customElement("approvals-audit-page")
export class ApprovalsAuditPage extends LitElement {
  private unsubscribeBridge: (() => void) | null = null;

  static styles = css`
    :host {
      display: block;
    }

    .grid {
      display: grid;
      grid-template-columns: 0.95fr 1.05fr;
      gap: 16px;
    }

    .panel {
      border-radius: 18px;
      border: 1px solid rgba(150, 186, 196, 0.12);
      background: rgba(10, 22, 31, 0.86);
      padding: 18px;
      display: grid;
      gap: 14px;
    }

    .item {
      border-radius: 14px;
      background: rgba(17, 32, 43, 0.74);
      padding: 12px 14px;
      display: grid;
      gap: 8px;
      border: 1px solid transparent;
    }

    h2, p {
      margin: 0;
    }

    h2 {
      font-size: 18px;
      color: #eef6fa;
    }

    .hint {
      color: #98afbb;
      font-size: 14px;
      line-height: 1.55;
    }

    .row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }

    .meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .risk {
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      background: rgba(218, 97, 97, 0.14);
      color: #ffb1b1;
    }

    .selected {
      border-color: rgba(111, 203, 193, 0.38);
      box-shadow: 0 0 0 1px rgba(111, 203, 193, 0.14) inset;
    }

    .status {
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      letter-spacing: 0.04em;
      background: rgba(80, 124, 151, 0.18);
      color: #c0d4df;
      text-transform: uppercase;
    }

    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }

    button {
      border: 0;
      border-radius: 999px;
      padding: 9px 14px;
      background: linear-gradient(135deg, #2c7a73, #1f5d73);
      color: #fff;
      font: inherit;
      cursor: pointer;
    }

    .ghost {
      background: rgba(21, 44, 57, 0.9);
      color: #dceaf0;
    }

    input {
      width: 100%;
      border-radius: 12px;
      border: 1px solid rgba(150, 186, 196, 0.18);
      background: rgba(6, 16, 22, 0.92);
      color: #eef5f8;
      padding: 10px 12px;
      font: inherit;
    }

  `;

  @property({ attribute: false }) bridgeClient: BridgeClient = createMockBridgeClient();
  @property({ attribute: false }) initialTraceFilter = "";
  @property({ attribute: false }) initialApprovalId = "";
  @property({ attribute: false }) initialActionId = "";
  @property({ attribute: false }) initialAuditId = "";
  @property({ attribute: false }) initialConnectorKey = "";
  @property({ attribute: false }) initialContextSource = "";

  @state() private approvals: ApprovalSummary[] = [];
  @state() private records: AuditRecord[] = [];
  @state() private selectedApprovalId = "";
  @state() private traceFilter = "";
  @state() private actionRequest: Record<string, unknown> | null = null;
  @state() private traceTimeline: TraceTimelineEntry[] = [];
  @state() private detailLoading = false;
  @state() private lastDecision: OperationFeedback = neutralFeedback("尚未处理审批");
  @state() private focusedActionId = "";
  @state() private focusedAuditId = "";
  @state() private workflowContext: WorkflowContext | null = null;
  @state() private workflowLoading = false;
  private lastAppliedRouteContextKey = "";

  connectedCallback(): void {
    super.connectedCallback();
    this.applyRouteContext();
    void this.load();
    this.unsubscribeBridge = this.bridgeClient.subscribe((event) => {
      this.handleBridgeEvent(event);
    });
  }

  protected updated(changedProperties: PropertyValues<this>): void {
    if (
      changedProperties.has("initialTraceFilter") ||
      changedProperties.has("initialApprovalId") ||
      changedProperties.has("initialActionId") ||
      changedProperties.has("initialAuditId")
    ) {
      if (this.applyRouteContext() && this.isConnected) {
        void this.load();
      }
    }
  }

  disconnectedCallback(): void {
    this.unsubscribeBridge?.();
    this.unsubscribeBridge = null;
    super.disconnectedCallback();
  }

  render() {
    const selectedApproval = this.selectedApproval;
    return html`
      <section class="grid">
        <article class="panel">
          <div>
            <h2>待审批</h2>
            <p class="hint">统一承接受控动作的批准、拒绝和审批上下文查看。</p>
            ${this.initialContextSource || this.initialConnectorKey
              ? html`
                  <div class="actions">
                    <p class="hint" data-testid="approvals-context-banner">
                      handoff=${this.initialContextSource || "unknown"} · connector=${this.initialConnectorKey || "-"}
                    </p>
                    <p class="hint" data-testid="approvals-context-limitation">
                      当前 approvals 仍按 trace / pending approval 展示，不按 connector 做独立过滤；这里先表达 operator landing context。
                    </p>
                    ${this.initialConnectorKey
                      ? html`
                          <button
                            class="ghost"
                            type="button"
                            data-testid="approvals-open-auth"
                            @click=${() => this.navigateToConnectorSurface("auth")}
                          >
                            打开 Auth / Scope
                          </button>
                          <button
                            class="ghost"
                            type="button"
                            data-testid="approvals-open-plugins"
                            @click=${() => this.navigateToConnectorSurface("plugins")}
                          >
                            打开插件与连接器
                          </button>
                          <button
                            class="ghost"
                            type="button"
                            data-testid="approvals-open-settings"
                            @click=${() => this.navigateToConnectorSurface("settings")}
                          >
                            打开设置
                          </button>
                        `
                      : null}
                  </div>
                `
              : null}
          </div>
          ${this.approvals.length === 0
            ? html`<span class="hint">当前没有待审批项。</span>`
            : this.approvals.map(
            (approval) => html`
              <section class="item ${this.selectedApprovalId === approval.approval_id ? "selected" : ""}">
                <div class="row">
                  <strong>${approval.title}</strong>
                  <span class="risk">${approval.risk}</span>
                </div>
                <span class="hint">${approval.trace_id}</span>
                <span class="hint">${approval.summary ?? approval.reason ?? "等待操作员确认。"}</span>
                <div class="actions">
                  <button
                    class="ghost"
                    type="button"
                    @click=${() => this.selectApproval(approval.approval_id)}
                  >
                    查看详情
                  </button>
                  <button type="button" @click=${() => this.resolveApproval(approval.approval_id, "approved")}>
                    批准
                  </button>
                  <button type="button" @click=${() => this.resolveApproval(approval.approval_id, "rejected")}>
                    拒绝
                  </button>
                </div>
              </section>
            `,
          )}
          <operation-feedback-view
            data-testid="operation-feedback"
            variant="stack"
            .surface=${true}
            .feedback=${this.lastDecision}
          ></operation-feedback-view>
        </article>
        <article class="panel">
          <div>
            <h2>审批详情与审计链</h2>
            <p class="hint">围绕 trace 查看审批上下文、操作理由和审计记录。</p>
          </div>
          <label>
            <span class="hint">Trace 过滤</span>
            <input
              data-testid="trace-filter"
              type="text"
              .value=${this.traceFilter}
              @input=${this.handleTraceInput}
              placeholder="输入 trace_id 过滤审计记录"
            />
          </label>
          ${selectedApproval
            ? html`
                <section class="item selected" data-testid="approval-detail">
                  <div class="row">
                    <strong>${selectedApproval.title}</strong>
                    <span class="status">${selectedApproval.status}</span>
                  </div>
                  <div class="meta">
                    <span class="hint">trace: ${selectedApproval.trace_id}</span>
                    <span class="hint">requested by: ${selectedApproval.requested_by ?? "-"}</span>
                    <span class="hint">requested at: ${selectedApproval.requested_at ?? "-"}</span>
                  </div>
                  <span class="hint">${selectedApproval.reason ?? selectedApproval.summary ?? "无补充理由"}</span>
                </section>
              `
            : html`<span class="hint" data-testid="approval-detail">请选择一个审批项。</span>`}
          <section class="item ${this.workflowContext ? "selected" : ""}" data-testid="workflow-context-detail">
            <div class="row">
              <strong>Related Workflow</strong>
              <span class="status">
                ${this.workflowLoading
                  ? "loading"
                  : this.workflowContext
                    ? this.workflowContext.status
                    : "none"}
              </span>
            </div>
            ${this.workflowLoading
              ? html`<span class="hint">正在加载 workflow 上下文...</span>`
              : this.workflowContext
                ? html`
                    <span class="hint">
                      ${this.workflowContext.workflowName} / ${this.workflowContext.pluginName}
                    </span>
                    <span class="hint">run: ${this.workflowContext.workflowRunId}</span>
                    <span class="hint">step: ${this.workflowContext.currentStep || "-"}</span>
                    <span class="hint">${this.workflowContext.summary || "暂无 workflow 摘要"}</span>
                    <div class="actions">
                      <button
                        class="ghost"
                        type="button"
                        @click=${this.refreshWorkflowContext}
                        ?disabled=${this.workflowLoading}
                        data-testid="refresh-workflow-context"
                      >
                        刷新 Workflow
                      </button>
                      <button
                        class="ghost"
                        type="button"
                        @click=${this.resumeWorkflow}
                        ?disabled=${!this.workflowContext.resumeEligible || this.workflowLoading}
                        data-testid="resume-workflow-context"
                      >
                        请求 Resume
                      </button>
                      <button
                        class="ghost"
                        type="button"
                        @click=${() => this.navigateToSessionsContext("workflowRuns")}
                        ?disabled=${!this.workflowContext?.workflowRunId}
                        data-testid="open-workflow-in-sessions"
                      >
                        打开 Workflow Detail
                      </button>
                    </div>
                  `
                : html`<span class="hint">当前 trace 未识别到关联 workflow run。</span>`}
          </section>
          <section
            class="item ${this.isFocusedActionRequest() ? "selected" : ""}"
            data-testid="action-request-detail"
          >
            <div class="row">
              <strong>Action Request</strong>
              <span class="status">
                ${this.actionRequest ? (this.isFocusedActionRequest() ? "focused" : "linked") : "none"}
              </span>
            </div>
            ${this.detailLoading
              ? html`<span class="hint">正在加载 causality 详情...</span>`
              : this.actionRequest
                ? html`
                    <span class="hint">action_id: ${this.valueText(this.actionRequest, "action_id", "actionId")}</span>
                    <span class="hint">status: ${this.valueText(this.actionRequest, "status", "state")}</span>
                    <span class="hint">type: ${this.valueText(this.actionRequest, "action_type", "actionType")}</span>
                    <span class="hint">summary: ${this.valueText(this.actionRequest, "summary", "reason", "title")}</span>
                    <div class="actions">
                      <button
                        class="ghost"
                        type="button"
                        @click=${() => this.navigateToSessionsContext("actionRequests")}
                        data-testid="open-action-in-sessions"
                      >
                        打开 Sessions Trace
                      </button>
                    </div>
                  `
                : html`<span class="hint">当前审批未关联 action request。</span>`}
          </section>
          ${this.records.map(
            (record) => html`
              <section
                class="item ${this.isFocusedAuditRecord(record) ? "selected" : ""}"
                data-testid="audit-record"
              >
                <div class="row">
                  <strong>${record.trace_id}</strong>
                  <span class="status">
                    ${this.isFocusedAuditRecord(record) ? "focused" : record.stage ?? record.status ?? "audit"}
                  </span>
                </div>
                <span class="hint">${record.summary}</span>
                <div class="actions">
                  <button
                    class="ghost"
                    type="button"
                    @click=${() => this.navigateToSessionsContext("auditRecords")}
                    data-testid="open-audit-in-sessions"
                  >
                    打开 Sessions Trace
                  </button>
                </div>
              </section>
            `,
          )}
          ${this.records.length === 0 ? html`<span class="hint">当前 trace 下暂无审计记录。</span>` : null}
          <section class="item" data-testid="trace-timeline">
            <div class="row">
              <strong>Trace Timeline</strong>
              <span class="status">${this.traceTimeline.length}</span>
            </div>
            ${this.traceTimeline.length === 0
              ? html`<span class="hint">当前 trace 下暂无 timeline 项。</span>`
              : this.traceTimeline.map(
                  (entry) => html`
                    <section class="item" data-testid="trace-timeline-item">
                      <div class="row">
                        <strong>${entry.kind}</strong>
                        <span class="status">${this.timelineItemStatus(entry.item)}</span>
                      </div>
                      <span class="hint">${this.timelineItemSummary(entry.item)}</span>
                      <div class="actions">
                        <button
                          class="ghost"
                          type="button"
                          @click=${() => this.inspectTimelineEntry(entry)}
                          data-testid="inspect-trace-timeline-item"
                        >
                          聚焦上下文
                        </button>
                      </div>
                    </section>
                  `,
                )}
          </section>
        </article>
      </section>
    `;
  }

  private async load() {
    const approvals = await this.loadApprovals();
    const traceId = this.traceFilter.trim();
    const records = await this.bridgeClient.audit.list(traceId ? { trace_id: traceId } : {});
    if (records.ok) {
      this.records = records.data?.records ?? [];
    } else {
      this.records = [];
    }
    if (!this.selectedApprovalId || !this.approvals.some((item) => item.approval_id === this.selectedApprovalId)) {
      this.selectedApprovalId =
        this.approvals.find((item) => item.trace_id === traceId)?.approval_id ?? this.approvals[0]?.approval_id ?? "";
    }
    if (!approvals.ok && !records.ok) {
      this.lastDecision = errorFeedback("审批与审计刷新失败");
      return;
    }
    if (!approvals.ok) {
      this.lastDecision = errorFeedback(approvals.error?.message ?? "审批列表刷新失败");
      return;
    }
    if (!records.ok) {
      this.lastDecision = errorFeedback(records.error?.message ?? "审计记录刷新失败");
    }
    const selectedTraceId =
      traceId || this.approvals.find((item) => item.approval_id === this.selectedApprovalId)?.trace_id || "";
    await this.loadWorkflowContext(selectedTraceId);
    await this.loadCausalityForSelected();
  }

  private async resolveApproval(approvalId: string, decision: "approved" | "rejected") {
    const response = await this.resolveWithFallback(approvalId, decision);
    this.lastDecision = feedbackFromBridgeResponse(response, {
      successMessage: `${approvalId} 已${decision === "approved" ? "批准" : "拒绝"}`,
      errorMessage: `${approvalId} 处理失败`,
    });
    if (response.ok) {
      this.approvals = this.approvals.filter((item) => item.approval_id !== approvalId);
      if (this.selectedApprovalId === approvalId) {
        this.selectedApprovalId = this.approvals[0]?.approval_id ?? "";
      }
      await this.load();
    }
  }

  private readonly handleTraceInput = (event: Event) => {
    this.traceFilter = (event.target as HTMLInputElement).value;
    void this.load();
  };

  private readonly handleBridgeEvent = (event: BridgeEvent<Record<string, unknown>>) => {
    if (!["approval_requested", "approval_resolved", "audit_written"].includes(event.kind)) {
      return;
    }
    const payload = event.payload ?? {};
    const approvalId = typeof payload.approval_id === "string" ? payload.approval_id : "";
    const status = typeof payload.status === "string" ? payload.status : "";
    if (approvalId && status) {
      this.lastDecision = this.feedbackForApprovalStatus(approvalId, status);
    }
    void this.load();
  };

  private selectApproval(approvalId: string) {
    this.selectedApprovalId = approvalId;
    this.focusedAuditId = "";
    const approval = this.selectedApproval;
    if (approval) {
      this.traceFilter = approval.trace_id;
      this.focusedActionId = String(approval.action_id ?? this.initialActionId).trim();
      void this.loadWorkflowContext(approval.trace_id);
      void this.loadCausalityForSelected();
    }
  }

  private get selectedApproval(): ApprovalSummary | null {
    return this.approvals.find((item) => item.approval_id === this.selectedApprovalId) ?? this.approvals[0] ?? null;
  }

  private feedbackForApprovalStatus(approvalId: string, status: string): OperationFeedback {
    if (status === "approved") {
      return successFeedback(`${approvalId} 已批准`);
    }
    if (status === "rejected") {
      return warningFeedback(`${approvalId} 已拒绝`);
    }
    return neutralFeedback(`${approvalId} 状态更新为 ${status}`);
  }

  private async loadApprovals() {
    const modern = await this.bridgeClient.approvals.list({ status: "pending" });
    if (modern.ok) {
      this.approvals = (modern.data?.approvalTickets ?? []) as ApprovalSummary[];
      return modern;
    }
    const legacy = await this.bridgeClient.approval.list();
    if (legacy.ok) {
      this.approvals = legacy.data?.approvals ?? [];
    } else {
      this.approvals = [];
    }
    return legacy;
  }

  private async resolveWithFallback(approvalId: string, decision: "approved" | "rejected") {
    const modern = await this.bridgeClient.approvals.resolve({
      approvalId: approvalId,
      decision: decision === "approved" ? "approve" : "reject",
    });
    if (modern.ok) {
      return modern;
    }
    return this.bridgeClient.approval.resolve({
      approval_id: approvalId,
      decision,
    });
  }

  private async loadCausalityForSelected() {
    const approval = this.selectedApproval;
    this.actionRequest = null;
    this.traceTimeline = [];
    if (!approval) {
      return;
    }
    this.detailLoading = true;
    const [detailResp, timelineResp] = await Promise.all([
      this.bridgeClient.approvals.get({ approvalId: approval.approval_id }),
      this.bridgeClient.gateway.state.traceTimeline({ traceId: approval.trace_id }),
    ]);
    if (detailResp.ok) {
      const data = (detailResp.data ?? {}) as ApprovalDetailResponse;
      this.actionRequest = data.actionRequest ?? null;
      this.records = Array.isArray(data.auditRecords) ? data.auditRecords : this.records;
    }
    if (timelineResp.ok) {
      const timeline = (timelineResp.data?.timeline ?? []) as TraceTimelineEntry[];
      this.traceTimeline = timeline.filter((item) => typeof item?.kind === "string");
    }
    this.detailLoading = false;
  }

  private readonly refreshWorkflowContext = async () => {
    const traceId = this.traceFilter.trim() || this.selectedApproval?.trace_id || "";
    await this.loadWorkflowContext(traceId);
  };

  private readonly resumeWorkflow = async () => {
    if (!this.workflowContext?.workflowRunId) {
      return;
    }
    this.workflowLoading = true;
    const response = await this.bridgeClient.gateway.workflows.resume({
      workflowRunId: this.workflowContext.workflowRunId,
      decidedBy: "gui.operator",
    });
    this.workflowLoading = false;
    this.lastDecision = feedbackFromBridgeResponse(response, {
      successMessage: `workflow ${this.workflowContext.workflowRunId} 已发起 resume 请求`,
      errorMessage: `workflow ${this.workflowContext.workflowRunId} resume 失败`,
    });
    if (!response.ok) {
      return;
    }
    this.workflowContext = this.normalizeWorkflowContext(response.data ?? {}, this.workflowContext.workflowRunId);
    const responseTraceId = String(response.data?.traceId ?? this.traceFilter).trim();
    if (responseTraceId) {
      this.traceFilter = responseTraceId;
    }
    const timeline = (response.data?.timeline ?? []) as TraceTimelineEntry[];
    this.traceTimeline = timeline.filter((item) => typeof item?.kind === "string");
    this.records = Array.isArray(response.data?.auditRecords) ? (response.data?.auditRecords as AuditRecord[]) : this.records;
  };

  private valueText(source: Record<string, unknown>, ...keys: string[]): string {
    for (const key of keys) {
      const value = source[key];
      if (value === undefined || value === null) {
        continue;
      }
      const text = String(value).trim();
      if (text) {
        return text;
      }
    }
    return "-";
  }

  private timelineItemStatus(item: Record<string, unknown>): string {
    return this.valueText(item, "status", "stage", "event_type");
  }

  private timelineItemSummary(item: Record<string, unknown>): string {
    return this.valueText(item, "summary", "title", "event_type", "trace_id", "traceId");
  }

  private inspectTimelineEntry(entry: TraceTimelineEntry) {
    const item = entry.item ?? {};
    const kind = String(entry.kind ?? "");
    if (kind === "approvalTickets") {
      const approvalId = this.valueText(item, "approval_id");
      if (approvalId !== "-") {
        this.selectApproval(approvalId);
      }
      return;
    }
    if (kind === "actionRequests") {
      this.focusedActionId = this.valueText(item, "action_id", "actionId");
      return;
    }
    if (kind === "auditRecords") {
      this.focusedAuditId = this.valueText(item, "audit_id");
      return;
    }
    if (kind === "workflowRuns") {
      const traceId = this.valueText(item, "trace_id", "traceId");
      if (traceId !== "-") {
        void this.loadWorkflowContext(traceId);
      }
    }
  }

  private applyRouteContext(): boolean {
    const traceId = this.initialTraceFilter.trim();
    const approvalId = this.initialApprovalId.trim();
    const actionId = this.initialActionId.trim();
    const auditId = this.initialAuditId.trim();
    const routeContextKey = `${traceId}::${approvalId}::${actionId}::${auditId}`;
    if (routeContextKey === this.lastAppliedRouteContextKey) {
      return false;
    }
    this.lastAppliedRouteContextKey = routeContextKey;
    let changed = false;
    if (traceId && this.traceFilter !== traceId) {
      this.traceFilter = traceId;
      changed = true;
    }
    if (approvalId && this.selectedApprovalId !== approvalId) {
      this.selectedApprovalId = approvalId;
      changed = true;
    }
    if (this.focusedActionId !== actionId) {
      this.focusedActionId = actionId;
      changed = true;
    }
    if (this.focusedAuditId !== auditId) {
      this.focusedAuditId = auditId;
      changed = true;
    }
    return changed;
  }

  private async loadWorkflowContext(traceId: string) {
    const normalizedTraceId = String(traceId || "").trim();
    this.workflowContext = null;
    if (!normalizedTraceId) {
      return;
    }
    this.workflowLoading = true;
    const response = await this.bridgeClient.gateway.workflows.list({ limit: 5, traceId: normalizedTraceId });
    this.workflowLoading = false;
    if (!response.ok) {
      return;
    }
    const runs = Array.isArray(response.data?.workflowRuns) ? response.data.workflowRuns : [];
    const matched = runs.find((item) => String((item as Record<string, unknown>).trace_id ?? "").trim() === normalizedTraceId);
    if (!matched) {
      return;
    }
    this.workflowContext = this.normalizeWorkflowContext(
      {
        workflowRun: matched,
        traceId: normalizedTraceId,
        resumeEligible: String((matched as Record<string, unknown>).status ?? "").toLowerCase() === "paused",
      },
      String((matched as Record<string, unknown>).workflow_run_id ?? ""),
    );
  }

  private normalizeWorkflowContext(payload: Record<string, unknown>, fallbackRunId: string): WorkflowContext {
    const workflowRun = (payload.workflowRun as Record<string, unknown> | undefined) ?? payload;
    return {
      workflowRunId: String(workflowRun.workflow_run_id ?? fallbackRunId),
      workflowName: String(workflowRun.workflow_name ?? "workflow"),
      pluginName: String(workflowRun.plugin_name ?? "unknown_plugin"),
      status: String(workflowRun.status ?? "unknown"),
      currentStep: String(workflowRun.current_step ?? workflowRun.currentStep ?? ""),
      summary: String(workflowRun.result_summary ?? workflowRun.summary ?? ""),
      resumeEligible: Boolean(payload.resumeEligible ?? String(workflowRun.status ?? "").toLowerCase() === "paused"),
    };
  }

  private navigateToSessionsContext(
    timelineScope: "workflowRuns" | "actionRequests" | "approvalTickets" | "auditRecords",
  ) {
    const traceId = String(this.traceFilter || this.selectedApproval?.trace_id || "").trim();
    if (!traceId) {
      return;
    }
    this.dispatchEvent(
      new CustomEvent<SessionsNavigationDetail>("navigate-control-context", {
        bubbles: true,
        composed: true,
        detail: {
          route: "sessions",
          traceId,
          workflowRunId: this.workflowContext?.workflowRunId || undefined,
          timelineScope,
          source: "approvals-context",
        },
      }),
    );
  }

  private navigateToConnectorSurface(route: ConnectorNavigationDetail["route"]) {
    if (!this.initialConnectorKey.trim()) {
      return;
    }
    this.dispatchEvent(
      new CustomEvent<ConnectorNavigationDetail>("navigate-control-context", {
        bubbles: true,
        composed: true,
        detail: {
          route,
          connectorKey: this.initialConnectorKey.trim(),
          source: "approvals-context",
        },
      }),
    );
  }

  private isFocusedActionRequest(): boolean {
    if (!this.actionRequest || !this.focusedActionId) {
      return false;
    }
    return this.valueText(this.actionRequest, "action_id", "actionId") === this.focusedActionId;
  }

  private isFocusedAuditRecord(record: AuditRecord): boolean {
    return Boolean(this.focusedAuditId) && String(record.audit_id ?? "").trim() === this.focusedAuditId;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "approvals-audit-page": ApprovalsAuditPage;
  }
}
