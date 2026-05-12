import { LitElement, type PropertyValues, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { BridgeClient, createMockBridgeClient } from "../../bridge/client.ts";
import "../../shared/components/operation-feedback-view.ts";
import {
  feedbackFromBridgeResponse,
  neutralFeedback,
  warningFeedback,
  type OperationFeedback,
} from "../../shared/state/operation-feedback.ts";
import type { ControlUiStateSnapshot, ThreadSummary } from "../../shared/types/bridge.ts";

type RunSummary = {
  runId: string;
  traceId: string;
  status: string;
  summary: string;
  workflowName: string;
  pluginName: string;
  currentStep: string;
  resumeEligible: boolean;
};

type TimelineEntry = {
  kind: string;
  title: string;
  detail: string;
  item: Record<string, unknown>;
};

type TraceCandidate = {
  traceId: string;
  source: string;
};

type WorkflowDetail = {
  runId: string;
  traceId: string;
  workflowName: string;
  pluginName: string;
  status: string;
  currentStep: string;
  summary: string;
  reasoningSummary: string;
  recommendationCount: number;
  approvalStatus: string;
  executionStatus: string;
  resumeEligible: boolean;
  actionCount: number;
  approvalCount: number;
  auditCount: number;
};

type WorkflowRelatedItem = {
  id: string;
  title: string;
  status: string;
  detail: string;
};

type TimelineScope = "all" | "workflowRuns" | "actionRequests" | "approvalTickets" | "auditRecords";

type ControlContextNavigationDetail = {
  route: "approvals";
  traceId: string;
  approvalId?: string;
  actionId?: string;
  auditId?: string;
  source: "workflow-detail";
};

type SessionTimelineScope = TimelineScope;

@customElement("sessions-runs-trace-page")
export class SessionsRunsTracePage extends LitElement {
  static styles = css`
    :host {
      display: block;
      color: #d9e4ec;
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

    h2,
    h3,
    p {
      margin: 0;
    }

    h2 {
      font-size: 18px;
      color: #eef6fa;
    }

    h3 {
      font-size: 15px;
      color: #d8e7ef;
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
      gap: 10px;
      flex-wrap: wrap;
    }

    .item {
      border-radius: 14px;
      background: rgba(17, 32, 43, 0.74);
      padding: 12px 14px;
      display: grid;
      gap: 8px;
      border: 1px solid transparent;
    }

    .item.active {
      border-color: rgba(111, 203, 193, 0.38);
      box-shadow: 0 0 0 1px rgba(111, 203, 193, 0.14) inset;
    }

    .pill {
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 11px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #d3e4ed;
      background: rgba(80, 124, 151, 0.2);
    }

    .list {
      display: grid;
      gap: 10px;
    }

    .meta-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    .meta-cell {
      border-radius: 12px;
      background: rgba(14, 28, 37, 0.84);
      padding: 10px 12px;
      display: grid;
      gap: 4px;
    }

    .detail-section {
      display: grid;
      gap: 8px;
      padding-top: 4px;
    }

    .scope-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .scope-chip {
      border: 1px solid rgba(150, 186, 196, 0.18);
      border-radius: 999px;
      padding: 6px 10px;
      background: rgba(15, 31, 39, 0.82);
      color: #d7e6ee;
      cursor: pointer;
      font-size: 12px;
    }

    .scope-chip.active {
      border-color: rgba(111, 203, 193, 0.42);
      background: rgba(31, 80, 77, 0.88);
    }

    .mini-list {
      display: grid;
      gap: 8px;
    }

    .mini-item {
      border-radius: 12px;
      background: rgba(12, 24, 33, 0.84);
      border: 1px solid rgba(150, 186, 196, 0.08);
      padding: 10px 12px;
      display: grid;
      gap: 4px;
    }

    .meta-label {
      color: #93aab7;
      font-size: 11px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .trace-control {
      display: grid;
      gap: 8px;
    }

    select,
    button {
      font: inherit;
    }

    select {
      width: 100%;
      border-radius: 12px;
      border: 1px solid rgba(150, 186, 196, 0.18);
      background: rgba(6, 16, 22, 0.92);
      color: #eef5f8;
      padding: 9px 12px;
    }

    button {
      border: 0;
      border-radius: 999px;
      padding: 9px 13px;
      background: linear-gradient(135deg, #2c7a73, #1f5d73);
      color: #fff;
      cursor: pointer;
    }

    button.ghost {
      background: rgba(21, 44, 57, 0.9);
      color: #dceaf0;
    }

    .empty {
      padding: 10px 0;
      color: #8da4b0;
      font-size: 13px;
    }

    @media (max-width: 960px) {
      .grid {
        grid-template-columns: 1fr;
      }

      .meta-grid {
        grid-template-columns: 1fr;
      }
    }
  `;

  @property({ attribute: false }) bridgeClient: BridgeClient = createMockBridgeClient();
  @property({ attribute: false }) initialTraceId = "";
  @property({ attribute: false }) initialWorkflowRunId = "";
  @property({ attribute: false }) initialTimelineScope: SessionTimelineScope = "all";

  @state() private loading = true;
  @state() private threads: ThreadSummary[] = [];
  @state() private activeThreadId = "";
  @state() private runs: RunSummary[] = [];
  @state() private traceCandidates: TraceCandidate[] = [];
  @state() private selectedTraceId = "";
  @state() private selectedWorkflowRunId = "";
  @state() private workflowDetail: WorkflowDetail | null = null;
  @state() private workflowDetailLoading = false;
  @state() private workflowActions: WorkflowRelatedItem[] = [];
  @state() private workflowApprovals: WorkflowRelatedItem[] = [];
  @state() private workflowAudits: WorkflowRelatedItem[] = [];
  @state() private timelineScope: TimelineScope = "all";
  @state() private timelineSource: TimelineEntry[] = [];
  @state() private timeline: TimelineEntry[] = [];
  @state() private feedback: OperationFeedback = neutralFeedback("可查看会话、运行与 trace。");
  @state() private snapshot: ControlUiStateSnapshot | null = null;
  private lastAppliedRouteContextKey = "";

  connectedCallback(): void {
    super.connectedCallback();
    this.applyRouteContext();
    void this.refresh();
  }

  protected updated(changedProperties: PropertyValues<this>): void {
    if (
      changedProperties.has("initialTraceId") ||
      changedProperties.has("initialWorkflowRunId") ||
      changedProperties.has("initialTimelineScope")
    ) {
      if (this.applyRouteContext() && this.isConnected) {
        void this.refresh();
      }
    }
  }

  render() {
    return html`
      <section class="grid">
        <article class="panel">
          <div>
            <h2>Sessions</h2>
            <p class="hint">复用现有 thread/session 能力，支持会话列表和恢复操作。</p>
          </div>
          <div class="list" data-testid="thread-list">
            ${this.threads.length === 0
              ? html`<span class="empty">当前没有会话记录。</span>`
              : this.threads.map(
                  (thread) => html`
                    <section
                      class="item ${thread.thread_id === this.activeThreadId ? "active" : ""}"
                      data-testid="thread-item"
                    >
                      <div class="row">
                        <strong>${thread.name || thread.thread_id}</strong>
                        <span class="pill">${thread.turn_count} turns</span>
                      </div>
                      <span class="hint">${thread.updated_at}</span>
                      <span class="hint">${thread.last_user_text || thread.last_assistant_text || "暂无最近消息"}</span>
                      <div class="row">
                        <button
                          class="ghost"
                          type="button"
                          @click=${() => this.resumeThread(thread.thread_id)}
                          data-testid="resume-thread"
                        >
                          恢复会话
                        </button>
                        ${thread.thread_id === this.activeThreadId
                          ? html`<span class="pill">active</span>`
                          : null}
                      </div>
                    </section>
                  `,
                )}
          </div>
        </article>

        <article class="panel">
          <div>
            <h2>Runs / Trace</h2>
            <p class="hint">优先使用当前 control UI state，后续平滑切到 gateway-native sessions/runs families。</p>
          </div>
          <div class="list" data-testid="runs-list">
            ${this.runs.length === 0
              ? html`<span class="empty">当前没有运行记录。</span>`
              : this.runs.map(
                  (run) => html`
                    <section
                      class="item ${run.runId === this.selectedWorkflowRunId ? "active" : ""}"
                      data-testid="run-item"
                    >
                      <div class="row">
                        <h3>${run.workflowName || run.runId}</h3>
                        <span class="pill">${run.status}</span>
                      </div>
                      <span class="hint">${run.pluginName || "unknown plugin"} / ${run.runId}</span>
                      <span class="hint">trace: ${run.traceId}</span>
                      <span class="hint">${run.summary}${run.currentStep ? ` | step=${run.currentStep}` : ""}</span>
                      <div class="row">
                        <button
                          class="ghost"
                          type="button"
                          @click=${() => this.selectWorkflowRun(run.runId)}
                          data-testid="select-run"
                        >
                          查看 Workflow Detail
                        </button>
                        ${run.resumeEligible
                          ? html`<span class="pill">resumable</span>`
                          : null}
                      </div>
                    </section>
                  `,
                )}
          </div>

          <section class="item" data-testid="workflow-detail">
            <div class="row">
              <h3>Workflow Detail</h3>
              ${this.workflowDetailLoading ? html`<span class="pill">loading</span>` : null}
            </div>
            ${this.workflowDetail === null
              ? html`<span class="empty">选择一个 workflow run 查看 reasoning、approval、execution 和 trace drill-down。</span>`
              : html`
                  <div class="meta-grid">
                    <div class="meta-cell">
                      <span class="meta-label">Workflow</span>
                      <strong>${this.workflowDetail.workflowName}</strong>
                      <span class="hint">${this.workflowDetail.pluginName} / ${this.workflowDetail.runId}</span>
                    </div>
                    <div class="meta-cell">
                      <span class="meta-label">Status</span>
                      <strong>${this.workflowDetail.status}</strong>
                      <span class="hint">${this.workflowDetail.currentStep || "no current step"}</span>
                    </div>
                    <div class="meta-cell">
                      <span class="meta-label">Reasoning</span>
                      <strong>${this.workflowDetail.reasoningSummary || this.workflowDetail.summary}</strong>
                      <span class="hint">trace=${this.workflowDetail.traceId}</span>
                    </div>
                    <div class="meta-cell">
                      <span class="meta-label">Operator Hooks</span>
                      <strong>approval=${this.workflowDetail.approvalStatus}, execution=${this.workflowDetail.executionStatus}</strong>
                      <span class="hint">
                        actions=${this.workflowDetail.actionCount}, approvals=${this.workflowDetail.approvalCount}, audits=${this.workflowDetail.auditCount}, recommendations=${this.workflowDetail.recommendationCount}
                      </span>
                    </div>
                  </div>
                  <div class="row">
                    <button
                      class="ghost"
                      type="button"
                      @click=${() => this.loadWorkflowDetail(this.selectedWorkflowRunId)}
                      ?disabled=${!this.selectedWorkflowRunId || this.workflowDetailLoading}
                      data-testid="refresh-workflow-detail"
                    >
                      刷新 Workflow Detail
                    </button>
                    <button
                      class="ghost"
                      type="button"
                      @click=${this.resumeWorkflow}
                      ?disabled=${!this.workflowDetail.resumeEligible || this.workflowDetailLoading}
                      data-testid="resume-workflow"
                    >
                      请求 Resume
                    </button>
                  </div>

                  <div class="detail-section">
                    <h3>Operator Drill-Down</h3>
                    <div class="scope-row" data-testid="timeline-scope-row">
                      ${this.renderTimelineScopeChip("all", "全部")}
                      ${this.renderTimelineScopeChip("workflowRuns", "Workflow")}
                      ${this.renderTimelineScopeChip("actionRequests", "Actions")}
                      ${this.renderTimelineScopeChip("approvalTickets", "Approvals")}
                      ${this.renderTimelineScopeChip("auditRecords", "Audits")}
                    </div>
                  </div>

                  <div class="meta-grid">
                    <section class="detail-section">
                      <h3>Action Requests</h3>
                      <div class="mini-list" data-testid="workflow-actions-list">
                        ${this.renderWorkflowMiniList(this.workflowActions, "当前没有关联 action request。", {
                          scope: "actionRequests",
                          opensOperatorContext: "action",
                        })}
                      </div>
                    </section>
                    <section class="detail-section">
                      <h3>Approval Chain</h3>
                      <div class="mini-list" data-testid="workflow-approvals-list">
                        ${this.renderWorkflowMiniList(this.workflowApprovals, "当前没有关联 approval。", {
                          scope: "approvalTickets",
                          opensOperatorContext: "approval",
                        })}
                      </div>
                    </section>
                  </div>

                  <section class="detail-section">
                    <h3>Audit Trail</h3>
                    <div class="mini-list" data-testid="workflow-audits-list">
                      ${this.renderWorkflowMiniList(this.workflowAudits, "当前没有关联 audit record。", {
                        scope: "auditRecords",
                        opensOperatorContext: "audit",
                      })}
                    </div>
                  </section>
                `}
          </section>

          <div class="trace-control">
            <label class="hint" for="trace-select">Trace Timeline</label>
            <select
              id="trace-select"
              .value=${this.selectedTraceId}
              @change=${this.handleTraceSelect}
              data-testid="trace-select"
            >
              ${this.traceCandidates.length === 0
                ? html`<option value="">暂无 trace</option>`
                : this.traceCandidates.map(
                    (item) => html`
                      <option value=${item.traceId}>
                        ${item.traceId} (${item.source})
                      </option>
                    `,
                  )}
            </select>
            <div class="row">
              <button
                class="ghost"
                type="button"
                @click=${this.loadTraceFromGateway}
                ?disabled=${!this.selectedTraceId}
                data-testid="load-trace-gateway"
              >
                从 Gateway 刷新 Timeline
              </button>
              <button class="ghost" type="button" @click=${this.refresh} ?disabled=${this.loading}>
                刷新
              </button>
            </div>
          </div>

          <div class="list" data-testid="trace-timeline">
            ${this.timeline.length === 0
              ? html`<span class="empty">当前 trace 下暂无 timeline 记录。</span>`
              : this.timeline.map(
                  (item) => html`
                    <section class="item" data-testid="trace-item">
                      <div class="row">
                        <strong>${item.title}</strong>
                        <span class="pill">${this.normalizeTimelineKind(item.kind)}</span>
                      </div>
                      <span class="hint">${item.detail}</span>
                      ${this.renderTraceTimelineActions(item)}
                    </section>
                  `,
                )}
          </div>
          <operation-feedback-view
            data-testid="sessions-feedback"
            variant="stack"
            .surface=${true}
            .feedback=${this.feedback}
          ></operation-feedback-view>
        </article>
      </section>
    `;
  }

  private readonly refresh = async () => {
    this.loading = true;
    const [threadList, stateResponse, workflowsResponse] = await Promise.all([
      this.bridgeClient.thread.list({ limit: 30 }),
      this.bridgeClient.controlUi.state({ limit: 40 }),
      this.bridgeClient.gateway.workflows.list({ limit: 20 }),
    ]);

    this.threads = threadList.ok ? threadList.data?.threads ?? [] : [];
    this.activeThreadId =
      (threadList.ok ? threadList.data?.active_thread_id ?? this.activeThreadId : this.activeThreadId) || "";

    const stateSnapshot = stateResponse.ok ? stateResponse.data : null;
    this.snapshot = stateSnapshot;
    this.runs =
      workflowsResponse.ok && Array.isArray(workflowsResponse.data?.workflowRuns)
        ? this.extractRunsFromGateway(workflowsResponse.data)
        : this.extractRuns(stateSnapshot);
    this.traceCandidates = this.extractTraceCandidates(stateSnapshot);
    this.applyRouteContext();
    if (!this.selectedTraceId || !this.traceCandidates.some((item) => item.traceId === this.selectedTraceId)) {
      this.selectedTraceId = this.traceCandidates[0]?.traceId ?? "";
    }
    if (!this.selectedWorkflowRunId || !this.runs.some((item) => item.runId === this.selectedWorkflowRunId)) {
      this.selectedWorkflowRunId = this.runs[0]?.runId ?? "";
    }
    this.timelineSource = this.buildTimelineFromState(stateSnapshot, this.selectedTraceId);
    this.timeline = this.filterTimeline(this.timelineSource, this.timelineScope);
    if (this.selectedWorkflowRunId) {
      await this.loadWorkflowDetail(this.selectedWorkflowRunId, true);
    } else {
      this.workflowDetail = null;
      this.workflowActions = [];
      this.workflowApprovals = [];
      this.workflowAudits = [];
    }
    if (!threadList.ok || !stateResponse.ok || !workflowsResponse.ok) {
      this.feedback = warningFeedback("会话或 control UI 状态刷新存在部分失败。");
    }
    this.loading = false;
  };

  private readonly resumeThread = async (threadId: string) => {
    const response = await this.bridgeClient.thread.resume({ thread_id: threadId });
    this.feedback = feedbackFromBridgeResponse(response, {
      successMessage: `已恢复会话 ${threadId}`,
      errorMessage: `恢复会话 ${threadId} 失败`,
    });
    if (response.ok) {
      this.activeThreadId = threadId;
      this.dispatchEvent(
        new CustomEvent("session-resumed", {
          bubbles: true,
          composed: true,
          detail: {
            threadId,
            historyCount: response.data?.history?.length ?? 0,
          },
        }),
      );
    }
  };

  private readonly handleTraceSelect = (event: Event) => {
    const nextTraceId = (event.target as HTMLSelectElement).value;
    this.selectedTraceId = nextTraceId;
    this.timelineSource = this.buildTimelineFromState(this.snapshot, nextTraceId);
    this.timeline = this.filterTimeline(this.timelineSource, this.timelineScope);
  };

  private readonly selectWorkflowRun = async (workflowRunId: string) => {
    this.selectedWorkflowRunId = workflowRunId;
    const run = this.runs.find((item) => item.runId === workflowRunId);
    if (run) {
      this.selectedTraceId = run.traceId;
      this.timelineSource = this.buildTimelineFromState(this.snapshot, run.traceId);
      this.timeline = this.filterTimeline(this.timelineSource, this.timelineScope);
    }
    await this.loadWorkflowDetail(workflowRunId);
  };

  private readonly loadTraceFromGateway = async () => {
    if (!this.selectedTraceId) {
      return;
    }
    const response = await this.bridgeClient.gateway.state.traceTimeline({
      traceId: this.selectedTraceId,
    });
    if (!response.ok) {
      this.feedback = warningFeedback(
        response.error?.message ?? "gateway.trace.timeline 暂不可用，已回退本地 timeline。",
      );
      return;
    }
    const rows = Array.isArray(response.data?.timeline) ? response.data.timeline : [];
    this.timelineSource = rows.map((entry) => {
      const item = (entry as { item?: Record<string, unknown> }).item ?? {};
      const kind = String((entry as { kind?: unknown }).kind ?? "trace");
      return {
        kind,
        title: this.timelineTitle(item, kind),
        detail: this.describeTimelineDetail(item),
        item,
      };
    });
    this.timeline = this.filterTimeline(this.timelineSource, this.timelineScope);
    this.feedback = neutralFeedback(`trace ${this.selectedTraceId} 已通过 gateway 刷新。`);
  };

  private async loadWorkflowDetail(workflowRunId: string, silent = false) {
    if (!workflowRunId) {
      this.workflowDetail = null;
      return;
    }
    this.workflowDetailLoading = true;
    const response = await this.bridgeClient.gateway.workflows.get({ workflowRunId });
    if (!response.ok) {
      if (!silent) {
        this.feedback = warningFeedback(response.error?.message ?? `workflow ${workflowRunId} detail 加载失败。`);
      }
      this.workflowDetailLoading = false;
      return;
    }
    this.workflowDetail = this.normalizeWorkflowDetail(response.data ?? {}, workflowRunId);
    this.workflowActions = this.normalizeActionItems(response.data ?? {});
    this.workflowApprovals = this.normalizeApprovalItems(response.data ?? {});
    this.workflowAudits = this.normalizeAuditItems(response.data ?? {});
    const traceId = String(response.data?.traceId ?? this.workflowDetail.traceId ?? "").trim();
    if (traceId) {
      this.selectedTraceId = traceId;
    }
    this.timelineSource =
      this.buildTimelineFromWorkflowDetail(response.data ?? {}) || this.buildTimelineFromState(this.snapshot, traceId);
    this.timeline = this.filterTimeline(this.timelineSource, this.timelineScope);
    if (!silent) {
      this.feedback = neutralFeedback(`workflow ${workflowRunId} detail 已刷新。`);
    }
    this.workflowDetailLoading = false;
  }

  private readonly resumeWorkflow = async () => {
    if (!this.selectedWorkflowRunId) {
      return;
    }
    const response = await this.bridgeClient.gateway.workflows.resume({
      workflowRunId: this.selectedWorkflowRunId,
      decidedBy: "gui.operator",
    });
    if (!response.ok) {
      this.feedback = warningFeedback(response.error?.message ?? `workflow ${this.selectedWorkflowRunId} resume 失败。`);
      return;
    }
    this.workflowDetail = this.normalizeWorkflowDetail(response.data ?? {}, this.selectedWorkflowRunId);
    this.workflowActions = this.normalizeActionItems(response.data ?? {});
    this.workflowApprovals = this.normalizeApprovalItems(response.data ?? {});
    this.workflowAudits = this.normalizeAuditItems(response.data ?? {});
    const traceId = String(response.data?.traceId ?? this.workflowDetail.traceId ?? "").trim();
    this.selectedTraceId = traceId;
    this.timelineSource =
      this.buildTimelineFromWorkflowDetail(response.data ?? {}) || this.buildTimelineFromState(this.snapshot, traceId);
    this.timeline = this.filterTimeline(this.timelineSource, this.timelineScope);
    this.runs = this.runs.map((item) =>
      item.runId === this.selectedWorkflowRunId
        ? {
            ...item,
            status: this.workflowDetail?.status ?? item.status,
            summary: this.workflowDetail?.summary ?? item.summary,
            currentStep: this.workflowDetail?.currentStep ?? item.currentStep,
            resumeEligible: this.workflowDetail?.resumeEligible ?? item.resumeEligible,
          }
        : item,
    );
    this.feedback = neutralFeedback(`workflow ${this.selectedWorkflowRunId} 已发起 resume 请求。`);
  };

  private readonly setTimelineScope = (scope: TimelineScope) => {
    this.timelineScope = scope;
    this.timeline = this.filterTimeline(this.timelineSource, scope);
  };

  private extractRuns(snapshot: ControlUiStateSnapshot | null): RunSummary[] {
    if (!snapshot) {
      return [];
    }
    const rows = Array.isArray(snapshot.workflowRuns) ? snapshot.workflowRuns : [];
    return rows.slice(0, 12).map((item, index) => ({
      runId: String(item.workflow_run_id || item.run_id || `run_${index + 1}`),
      traceId: String(item.trace_id || item.traceId || "trace_unknown"),
      status: String(item.status || "unknown"),
      summary: String(item.result_summary || item.summary || "暂无结果摘要"),
      workflowName: String(item.workflow_name || item.name || item.workflow_run_id || `workflow_${index + 1}`),
      pluginName: String(item.plugin_name || "unknown_plugin"),
      currentStep: String(item.current_step || item.currentStep || ""),
      resumeEligible: false,
    }));
  }

  private extractRunsFromGateway(payload: Record<string, unknown>): RunSummary[] {
    const diagnostics = Array.isArray(payload.workflowDiagnostics) ? payload.workflowDiagnostics : [];
    const diagnosticsByRunId = new Map(
      diagnostics.map((item) => [String((item as Record<string, unknown>).workflow_run_id || ""), item as Record<string, unknown>]),
    );
    const rows = Array.isArray(payload.workflowRuns) ? payload.workflowRuns : [];
    return rows.slice(0, 12).map((item, index) => {
      const record = item as Record<string, unknown>;
      const diagnostic = diagnosticsByRunId.get(String(record.workflow_run_id || ""));
      return {
        runId: String(record.workflow_run_id || record.run_id || `run_${index + 1}`),
        traceId: String(record.trace_id || record.traceId || "trace_unknown"),
        status: String(record.status || "unknown"),
        summary: String(
          (diagnostic?.reasoning as Record<string, unknown> | undefined)?.summary ||
            record.result_summary ||
            record.summary ||
            "暂无结果摘要",
        ),
        workflowName: String(record.workflow_name || record.name || record.workflow_run_id || `workflow_${index + 1}`),
        pluginName: String(record.plugin_name || diagnostic?.plugin_name || "unknown_plugin"),
        currentStep: String(record.current_step || record.currentStep || ""),
        resumeEligible: String(record.status || "").toLowerCase() === "paused",
      };
    });
  }

  private extractTraceCandidates(snapshot: ControlUiStateSnapshot | null): TraceCandidate[] {
    if (!snapshot) {
      return [];
    }
    const seen = new Set<string>();
    const output: TraceCandidate[] = [];
    const push = (value: unknown, source: string) => {
      const traceId = String(value || "").trim();
      if (!traceId || seen.has(traceId)) {
        return;
      }
      seen.add(traceId);
      output.push({ traceId, source });
    };

    for (const item of snapshot.workflowRuns ?? []) {
      push(item.trace_id || item.traceId, "workflow");
    }
    for (const item of snapshot.approvalTickets ?? []) {
      push(item.trace_id || item.traceId, "approval");
    }
    for (const item of snapshot.auditRecords ?? []) {
      push(item.trace_id || item.traceId, "audit");
    }
    for (const item of snapshot.events ?? []) {
      push(item.trace_id || item.traceId, "event");
    }
    return output.slice(0, 24);
  }

  private buildTimelineFromState(
    snapshot: ControlUiStateSnapshot | null,
    traceId: string,
  ): TimelineEntry[] {
    if (!snapshot || !traceId) {
      return [];
    }
    const rows: TimelineEntry[] = [];
    const push = (kind: string, item: Record<string, unknown>) => {
      const itemTraceId = String(item.trace_id || item.traceId || "").trim();
      if (itemTraceId !== traceId) {
        return;
      }
      rows.push({
        kind,
        title: String(
          item.summary ||
            item.event_type ||
            item.workflow_run_id ||
            item.approval_id ||
            item.audit_id ||
            kind,
        ),
        detail: this.describeTimelineDetail(item),
        item,
      });
    };

    for (const item of snapshot.events ?? []) {
      push("event", item as Record<string, unknown>);
    }
    for (const item of snapshot.workflowRuns ?? []) {
      push("run", item as Record<string, unknown>);
    }
    for (const item of snapshot.actionRequests ?? []) {
      push("action", item as Record<string, unknown>);
    }
    for (const item of snapshot.approvalTickets ?? []) {
      push("approval", item as Record<string, unknown>);
    }
    for (const item of snapshot.auditRecords ?? []) {
      push("audit", item as Record<string, unknown>);
    }
    return rows;
  }

  private buildTimelineFromWorkflowDetail(payload: Record<string, unknown>): TimelineEntry[] {
    const rows = Array.isArray(payload.timeline) ? payload.timeline : [];
    return rows.map((entry) => {
      const record = entry as { kind?: unknown; item?: Record<string, unknown> };
      return {
        kind: String(record.kind || "trace"),
        title: this.timelineTitle(record.item ?? {}, String(record.kind || "trace")),
        detail: this.describeTimelineDetail(record.item ?? {}),
        item: record.item ?? {},
      };
    });
  }

  private normalizeWorkflowDetail(payload: Record<string, unknown>, workflowRunId: string): WorkflowDetail {
    const workflowRun = (payload.workflowRun as Record<string, unknown> | undefined) ?? {};
    const workflowDiagnostic = (payload.workflowDiagnostic as Record<string, unknown> | undefined) ?? {};
    const reasoning = (workflowDiagnostic.reasoning as Record<string, unknown> | undefined) ?? {};
    const recommendation = (workflowDiagnostic.recommendation as Record<string, unknown> | undefined) ?? {};
    const approval = (workflowDiagnostic.approval as Record<string, unknown> | undefined) ?? {};
    const execution = (workflowDiagnostic.execution as Record<string, unknown> | undefined) ?? {};
    const actionRequests = Array.isArray(payload.actionRequests) ? payload.actionRequests : [];
    const approvalTickets = Array.isArray(payload.approvalTickets) ? payload.approvalTickets : [];
    const auditRecords = Array.isArray(payload.auditRecords) ? payload.auditRecords : [];
    return {
      runId: String(workflowRun.workflow_run_id || workflowRunId),
      traceId: String(payload.traceId || workflowRun.trace_id || ""),
      workflowName: String(workflowRun.workflow_name || "workflow"),
      pluginName: String(workflowRun.plugin_name || "unknown_plugin"),
      status: String(workflowRun.status || workflowDiagnostic.workflow_status || "unknown"),
      currentStep: String(workflowRun.current_step || workflowRun.currentStep || ""),
      summary: String(workflowRun.result_summary || workflowRun.summary || ""),
      reasoningSummary: String(reasoning.summary || ""),
      recommendationCount: Number(recommendation.count || 0),
      approvalStatus: String(approval.status || "not_requested"),
      executionStatus: String(execution.status || "not_executed"),
      resumeEligible: Boolean(payload.resumeEligible),
      actionCount: actionRequests.length,
      approvalCount: approvalTickets.length,
      auditCount: auditRecords.length,
    };
  }

  private timelineTitle(item: Record<string, unknown>, kind: string): string {
    return String(
      item.summary ||
        item.event_type ||
        item.workflow_name ||
        item.workflow_run_id ||
        item.approval_id ||
        item.audit_id ||
        kind,
    );
  }

  private describeTimelineDetail(item: Record<string, unknown>): string {
    const parts: string[] = [];
    const status = String(item.status || "").trim();
    if (status) {
      parts.push(`status=${status}`);
    }
    const stage = String(item.stage || "").trim();
    if (stage) {
      parts.push(`stage=${stage}`);
    }
    const source = String(item.source_kind || "").trim();
    if (source) {
      parts.push(`source=${source}`);
    }
    const trace = String(item.trace_id || item.traceId || "").trim();
    if (trace) {
      parts.push(`trace=${trace}`);
    }
    const step = String(item.current_step || item.currentStep || "").trim();
    if (step) {
      parts.push(`step=${step}`);
    }
    return parts.join(" | ") || "无更多详情";
  }

  private normalizeActionItems(payload: Record<string, unknown>): WorkflowRelatedItem[] {
    const rows = Array.isArray(payload.actionRequests) ? payload.actionRequests : [];
    return rows.map((item) => {
      const record = item as Record<string, unknown>;
      return {
        id: String(record.action_id || ""),
        title: String(record.action_type || record.action_id || "action"),
        status: String(record.status || (record.approval_required ? "pending" : "ready")),
        detail: this.describeTimelineDetail(record),
      };
    });
  }

  private normalizeApprovalItems(payload: Record<string, unknown>): WorkflowRelatedItem[] {
    const tickets = Array.isArray(payload.approvalTickets) ? payload.approvalTickets : [];
    const diagnostics = Array.isArray(payload.approvalDiagnostics) ? payload.approvalDiagnostics : [];
    const diagnosticById = new Map(
      diagnostics.map((item) => [String((item as Record<string, unknown>).approval_id || ""), item as Record<string, unknown>]),
    );
    return tickets.map((item) => {
      const record = item as Record<string, unknown>;
      const diagnostic = diagnosticById.get(String(record.approval_id || ""));
      return {
        id: String(record.approval_id || ""),
        title: String(record.summary || record.approval_id || "approval"),
        status: String(record.status || "pending"),
        detail: [
          this.describeTimelineDetail(record),
          diagnostic ? this.describeTimelineDetail(diagnostic) : "",
        ].filter(Boolean).join(" | "),
      };
    });
  }

  private normalizeAuditItems(payload: Record<string, unknown>): WorkflowRelatedItem[] {
    const rows = Array.isArray(payload.auditRecords) ? payload.auditRecords : [];
    return rows.map((item) => {
      const record = item as Record<string, unknown>;
      return {
        id: String(record.audit_id || ""),
        title: String(record.summary || record.audit_id || "audit"),
        status: String(record.status || "unknown"),
        detail: this.describeTimelineDetail(record),
      };
    });
  }

  private renderTimelineScopeChip(scope: TimelineScope, label: string) {
    return html`
      <button
        type="button"
        class="scope-chip ${this.timelineScope === scope ? "active" : ""}"
        @click=${() => this.setTimelineScope(scope)}
        data-testid=${`timeline-scope-${scope}`}
      >
        ${label}
      </button>
    `;
  }

  private renderWorkflowMiniList(
    items: WorkflowRelatedItem[],
    emptyText: string,
    options: {
      scope: TimelineScope;
      opensOperatorContext?: "approval" | "action" | "audit";
    },
  ) {
    if (items.length === 0) {
      return html`<span class="empty">${emptyText}</span>`;
    }
    return items.map(
      (item) => html`
        <section class="mini-item" data-testid="workflow-related-item">
          <div class="row">
            <strong>${item.title}</strong>
            <span class="pill">${item.status}</span>
          </div>
          <span class="hint">${item.id}</span>
          <span class="hint">${item.detail || "无更多详情"}</span>
          <div class="row">
            <button
              class="ghost"
              type="button"
              @click=${() => this.setTimelineScope(options.scope)}
              data-testid=${`focus-${options.scope}`}
            >
              聚焦 Timeline
            </button>
            ${options.opensOperatorContext
              ? html`
                  <button
                    class="ghost"
                    type="button"
                    @click=${() => this.navigateToOperatorContext(options.opensOperatorContext ?? "approval", item.id)}
                    data-testid=${`open-${options.opensOperatorContext}-context`}
                  >
                    打开 Operator Context
                  </button>
                `
              : null}
          </div>
        </section>
      `,
    );
  }

  private renderTraceTimelineActions(entry: TimelineEntry) {
    const normalizedKind = this.normalizeTimelineKind(entry.kind);
    if (normalizedKind === "workflowRuns") {
      return html`
        <div class="row">
          <button
            class="ghost"
            type="button"
            @click=${() => this.inspectTimelineEntry(entry)}
            data-testid="inspect-trace-workflow"
          >
            打开 Workflow Detail
          </button>
        </div>
      `;
    }
    if (normalizedKind === "actionRequests" || normalizedKind === "approvalTickets" || normalizedKind === "auditRecords") {
      return html`
        <div class="row">
          <button
            class="ghost"
            type="button"
            @click=${() => this.inspectTimelineEntry(entry)}
            data-testid=${`inspect-trace-${normalizedKind}`}
          >
            打开 Operator Context
          </button>
        </div>
      `;
    }
    return null;
  }

  private filterTimeline(entries: TimelineEntry[], scope: TimelineScope): TimelineEntry[] {
    if (scope === "all") {
      return [...entries];
    }
    return entries.filter((item) => this.normalizeTimelineKind(item.kind) === scope);
  }

  private applyRouteContext(): boolean {
    const traceId = this.initialTraceId.trim();
    const workflowRunId = this.initialWorkflowRunId.trim();
    const timelineScope = this.initialTimelineScope;
    const routeContextKey = `${traceId}::${workflowRunId}::${timelineScope}`;
    if (routeContextKey === this.lastAppliedRouteContextKey) {
      return false;
    }
    this.lastAppliedRouteContextKey = routeContextKey;
    let changed = false;
    if (traceId && this.selectedTraceId !== traceId) {
      this.selectedTraceId = traceId;
      changed = true;
    }
    if (workflowRunId && this.selectedWorkflowRunId !== workflowRunId) {
      this.selectedWorkflowRunId = workflowRunId;
      changed = true;
    }
    if (this.timelineScope !== timelineScope) {
      this.timelineScope = timelineScope;
      changed = true;
    }
    return changed;
  }

  private navigateToOperatorContext(kind: "approval" | "action" | "audit", itemId: string) {
    const traceId = String(this.workflowDetail?.traceId || this.selectedTraceId || "").trim();
    if (!traceId) {
      return;
    }
    const detail: ControlContextNavigationDetail = {
      route: "approvals",
      traceId,
      source: "workflow-detail",
    };
    if (kind === "approval") {
      detail.approvalId = itemId;
    } else if (kind === "action") {
      detail.actionId = itemId;
    } else {
      detail.auditId = itemId;
    }
    this.dispatchEvent(
      new CustomEvent<ControlContextNavigationDetail>("navigate-control-context", {
        bubbles: true,
        composed: true,
        detail,
      }),
    );
  }

  private inspectTimelineEntry(entry: TimelineEntry) {
    const normalizedKind = this.normalizeTimelineKind(entry.kind);
    const item = entry.item ?? {};
    if (normalizedKind === "workflowRuns") {
      const workflowRunId = String(item.workflow_run_id ?? item.run_id ?? "").trim();
      this.setTimelineScope("workflowRuns");
      if (workflowRunId) {
        void this.selectWorkflowRun(workflowRunId);
      }
      return;
    }
    if (normalizedKind === "actionRequests") {
      const actionId = String(item.action_id ?? "").trim();
      this.setTimelineScope("actionRequests");
      if (actionId) {
        this.navigateToOperatorContext("action", actionId);
      }
      return;
    }
    if (normalizedKind === "approvalTickets") {
      const approvalId = String(item.approval_id ?? "").trim();
      this.setTimelineScope("approvalTickets");
      if (approvalId) {
        this.navigateToOperatorContext("approval", approvalId);
      }
      return;
    }
    if (normalizedKind === "auditRecords") {
      const auditId = String(item.audit_id ?? "").trim();
      this.setTimelineScope("auditRecords");
      if (auditId) {
        this.navigateToOperatorContext("audit", auditId);
      }
    }
  }

  private normalizeTimelineKind(kind: string): string {
    if (kind === "run") {
      return "workflowRuns";
    }
    if (kind === "action") {
      return "actionRequests";
    }
    if (kind === "approval") {
      return "approvalTickets";
    }
    if (kind === "audit") {
      return "auditRecords";
    }
    if (kind === "event") {
      return "events";
    }
    return kind;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "sessions-runs-trace-page": SessionsRunsTracePage;
  }
}
