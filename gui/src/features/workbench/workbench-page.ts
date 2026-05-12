import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { BridgeClient, createMockBridgeClient } from "../../bridge/client.ts";
import "../../shared/components/operation-feedback-view.ts";
import type {
  ApprovalSummary,
  BridgeEvent,
  ConnectorSummary,
  ControlUiStateSnapshot,
  GatewayEventFrame,
  PluginSummary,
  SystemStatusSummary,
  ThreadSummary,
} from "../../shared/types/bridge.ts";
import { summarizeBridgeCollection } from "../../shared/state/health-summary.ts";
import {
  feedbackFromBridgeResponse,
  neutralFeedback,
  type OperationFeedback,
} from "../../shared/state/operation-feedback.ts";

type RecentTask = {
  taskId: string;
  title: string;
  status: "running" | "completed" | "pending_approval";
  updatedAt: string;
  subtitle: string;
};

type AttentionLevel = "high" | "medium" | "low";

type AttentionItem = {
  id: string;
  title: string;
  detail: string;
  level: AttentionLevel;
  route: "chat" | "browser" | "approvals" | "sessions" | "plugins" | "settings";
  traceId?: string;
  approvalId?: string;
  timelineScope?: "all" | "workflowRuns" | "actionRequests" | "approvalTickets" | "auditRecords";
  actionLabel: string;
};

type ActivityItem = {
  id: string;
  title: string;
  detail: string;
  kind: string;
  route: "approvals" | "sessions";
  traceId: string;
  approvalId?: string;
  timelineScope?: "all" | "workflowRuns" | "actionRequests" | "approvalTickets" | "auditRecords";
  actionLabel: string;
};

type ActivityGroup = {
  key: string;
  label: string;
  items: ActivityItem[];
};

type WorkbenchRouteId = "chat" | "browser" | "approvals" | "sessions" | "plugins" | "settings";

type WorkbenchControlContextDetail = {
  route: "approvals" | "sessions";
  traceId: string;
  approvalId?: string;
  timelineScope?: "all" | "workflowRuns" | "actionRequests" | "approvalTickets" | "auditRecords";
  source: "workbench";
};

type OperatorCardDescriptor = {
  id: string;
  title: string;
  value: number;
  detail: string;
  route: WorkbenchRouteId;
};

type ActionCardDescriptor = {
  id: string;
  title: string;
  value: string;
  detail: string;
  route: WorkbenchRouteId;
};

type OverviewSummary = {
  pendingApprovals: number;
  pendingApprovalsDetail: string;
  gatewayEvents: number;
  gatewayEventsDetail: string;
  recentTasks: number;
  recentTasksDetail: string;
  connectors: number;
  connectorsDetail: string;
};

@customElement("workbench-page")
export class WorkbenchPage extends LitElement {
  private unsubscribe: (() => void) | null = null;
  private gatewayPollTimer: ReturnType<typeof setTimeout> | null = null;
  private gatewayEventCursor = 0;
  private gatewayPolling = false;

  static styles = css`
    :host {
      display: block;
      color: #d9e4ec;
    }

    .grid {
      display: grid;
      gap: 12px;
    }

    .console-grid {
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    }

    .secondary-grid {
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    }

    .hero-card {
      position: relative;
      overflow: hidden;
      min-height: clamp(500px, 72vh, 760px);
      padding: clamp(28px, 4vw, 42px);
      border-radius: 32px;
      border: 1px solid rgba(150, 198, 255, 0.12);
      background: linear-gradient(180deg, rgba(4, 11, 19, 0.28), rgba(4, 11, 19, 0.08));
      box-shadow:
        inset 0 1px 0 rgba(220, 238, 255, 0.06),
        0 24px 80px rgba(2, 8, 14, 0.22);
      backdrop-filter: blur(8px);
    }

    .hero-card::before {
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(120deg, rgba(255, 255, 255, 0.04), transparent 26%),
        radial-gradient(circle at 80% 22%, rgba(125, 174, 255, 0.08), transparent 26%);
      pointer-events: none;
    }

    .hero-grid {
      position: relative;
      z-index: 1;
      display: grid;
      grid-template-columns: minmax(0, 1.24fr) minmax(280px, 0.72fr);
      gap: 30px;
      min-height: calc(clamp(500px, 72vh, 760px) - 2 * clamp(28px, 4vw, 42px));
      align-items: center;
    }

    .hero-copy {
      display: grid;
      gap: 18px;
      max-width: 62ch;
      align-content: center;
    }

    .hero-title {
      margin: 0;
      max-width: 10ch;
      font-size: clamp(52px, 7.4vw, 92px);
      line-height: 0.88;
      letter-spacing: -0.065em;
      color: #f8fbff;
    }

    .hero-title-accent {
      display: block;
      background: linear-gradient(135deg, #f7f9ff 0%, #ffe88e 22%, #fb9ce5 44%, #8dd0ff 78%, #e8fbff 100%);
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
    }

    .hero-lead {
      font-size: 18px;
      line-height: 1.6;
      color: #d3e1ec;
      max-width: 56ch;
    }

    .hero-note {
      font-size: 11px;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      color: #9ed2ff;
    }

    .hero-pill-row,
    .hero-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }

    .hero-pill-row {
      margin-top: 4px;
    }

    .hero-pill {
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid rgba(151, 198, 255, 0.14);
      background: rgba(6, 18, 30, 0.38);
      color: #c8d8e4;
      font-size: 12px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      backdrop-filter: blur(12px);
    }

    .hero-actions {
      margin-top: 4px;
    }

    .hero-button {
      min-width: 144px;
      min-height: 46px;
      padding-inline: 18px;
      background: rgba(7, 22, 34, 0.42);
      border: 1px solid rgba(160, 206, 255, 0.16);
      backdrop-filter: blur(12px);
    }

    .hero-button.hero-button-primary {
      color: #f4fbff;
      background: linear-gradient(135deg, rgba(18, 78, 202, 0.96), rgba(71, 151, 255, 0.74));
      border-color: rgba(155, 206, 255, 0.3);
    }

    .hero-stat-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 14px;
      align-self: center;
    }

    .hero-stat {
      display: grid;
      align-content: start;
      gap: 10px;
      padding: 18px 18px 20px;
      border-radius: 20px;
      border: 1px solid rgba(150, 198, 255, 0.16);
      background: linear-gradient(180deg, rgba(7, 18, 29, 0.52), rgba(5, 13, 22, 0.24));
      backdrop-filter: blur(14px);
      box-shadow: inset 0 1px 0 rgba(220, 238, 255, 0.04);
    }

    .hero-stat-label {
      font-size: 11px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: #96c4e4;
    }

    .hero-stat-value {
      font-size: 34px;
      line-height: 1;
      color: #f8fbff;
      text-transform: uppercase;
    }

    .hero-stat-detail {
      font-size: 13px;
      line-height: 1.5;
      color: #bdd0dc;
    }

    .card {
      border-radius: 18px;
      border: 1px solid rgba(150, 186, 196, 0.14);
      background: rgba(10, 23, 31, 0.88);
      padding: 18px;
      display: grid;
      gap: 12px;
    }

    .card-console {
      min-height: 360px;
    }

    .card.wide {
      grid-column: span 2;
    }

    .card.full {
      grid-column: 1 / -1;
    }

    .card.narrow {
      min-height: 140px;
    }

    h2 {
      font-size: 18px;
      color: #f0f6fa;
      margin: 0;
    }

    h3 {
      font-size: 16px;
      margin: 0;
      color: #f0f6fa;
    }

    p {
      color: #8ea6b2;
      line-height: 1.55;
      font-size: 14px;
      margin: 0;
    }

    .lead {
      font-size: 13px;
      color: #9fb3c8;
    }

    .console-header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
    }

    .eyebrow {
      font-size: 11px;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      color: #7dd9ff;
      margin: 0;
    }

    textarea {
      width: 100%;
      min-height: 112px;
      border: 1px solid rgba(150, 186, 196, 0.18);
      border-radius: 14px;
      background: rgba(6, 16, 22, 0.92);
      color: #eef5f8;
      padding: 12px 14px;
      resize: vertical;
      font: inherit;
    }

    .operator-card-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 10px;
    }

    .operator-card {
      border-radius: 14px;
      border: 1px solid rgba(150, 186, 196, 0.25);
      background: rgba(6, 16, 22, 0.95);
      padding: 12px 14px;
      display: grid;
      gap: 6px;
      min-height: 100px;
      text-align: left;
      cursor: pointer;
      transition: transform 120ms ease, border-color 120ms ease;
      color: inherit;
    }

    .operator-card strong {
      font-size: 22px;
      letter-spacing: 0.08em;
    }

    .operator-card .caption {
      font-size: 11px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .operator-card:hover,
    .operator-card:focus-visible {
      transform: translateY(-2px);
      border-color: rgba(205, 232, 255, 0.6);
      background: rgba(10, 18, 28, 0.96);
      outline: none;
    }

    .operator-commands {
      display: grid;
      gap: 10px;
      margin-top: 6px;
    }

    .operator-commands__header {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
    }

    .operator-commands__toolbar {
      display: grid;
      gap: 10px;
    }

    .operator-commands__actions {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }

    .operator-commands__actions .quick-links {
      flex: 1 1 220px;
    }

    .operator-commands__run button {
      min-width: 140px;
    }

    .actions {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
    }

    .quick-links {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .quick-links a,
    .quick-links button {
      text-decoration: none;
      border-radius: 999px;
      padding: 6px 10px;
      border: 1px solid rgba(150, 186, 196, 0.22);
      color: #c3d5df;
      font-size: 12px;
      letter-spacing: 0.03em;
      background: rgba(15, 33, 42, 0.72);
      font: inherit;
    }

    .quick-links a:hover,
    .quick-links button:hover {
      border-color: rgba(163, 214, 234, 0.46);
      color: #e8f1f6;
    }

    button {
      border: 0;
      border-radius: 999px;
      padding: 10px 16px;
      font: inherit;
      cursor: pointer;
    }

    button.primary {
      background: linear-gradient(135deg, #2f8f7f, #285f86);
      color: #fff;
    }

    button.secondary {
      background: rgba(37, 58, 66, 0.72);
      color: #dbe7ee;
    }

    button:disabled {
      cursor: not-allowed;
      opacity: 0.45;
    }

    ul {
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 10px;
    }

    li {
      border-radius: 14px;
      padding: 12px 14px;
      background: rgba(14, 31, 40, 0.76);
      display: grid;
      gap: 6px;
    }

    .row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }

    .row.start {
      align-items: start;
    }

    .pill {
      padding: 3px 8px;
      border-radius: 999px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .running {
      background: rgba(234, 183, 94, 0.14);
      color: #ffd486;
    }

    .completed {
      background: rgba(76, 175, 139, 0.16);
      color: #8ae0ba;
    }

    .pending_approval {
      background: rgba(218, 97, 97, 0.14);
      color: #ff9d9d;
    }

    .attention-high {
      background: rgba(218, 97, 97, 0.14);
      color: #ff9d9d;
    }

    .attention-medium {
      background: rgba(234, 183, 94, 0.14);
      color: #ffd486;
    }

    .attention-low {
      background: rgba(76, 175, 139, 0.16);
      color: #8ae0ba;
    }

    .metric-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 12px;
    }

    .metric {
      border-radius: 14px;
      background: rgba(14, 31, 40, 0.76);
      padding: 12px 14px;
      display: grid;
      gap: 4px;
    }

    .metric strong {
      font-size: 22px;
      color: #f0f6fa;
      text-transform: uppercase;
    }

    .metric .level-ready {
      color: #8ae0ba;
    }

    .metric .level-warning {
      color: #ffd486;
    }

    .metric .level-error {
      color: #ff9d9d;
    }

    .activity-list li,
    .attention-list li {
      gap: 8px;
    }

    .activity-groups {
      display: grid;
      gap: 12px;
    }

    .activity-group {
      display: grid;
      gap: 8px;
    }

    .activity-group-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }

    .empty {
      color: #84a0af;
      font-size: 13px;
    }

    .caption {
      color: #84a0af;
      font-size: 13px;
    }

    @media (max-width: 960px) {
      .hero-card {
        min-height: 520px;
        padding: 20px;
      }

      .hero-grid {
        grid-template-columns: 1fr;
        min-height: unset;
        align-items: start;
      }

      .hero-stat-grid {
        grid-template-columns: 1fr;
      }

      .hero-title {
        max-width: 12ch;
      }

      .console-grid,
      .secondary-grid {
        grid-template-columns: 1fr;
      }

      .card.wide,
      .card.full {
        grid-column: span 1;
      }
    }
  `;

  @property({ attribute: false }) bridgeClient: BridgeClient = createMockBridgeClient();

  @state() private composeText = "";
  @state() private pendingApprovals: ApprovalSummary[] = [];
  @state() private plugins: PluginSummary[] = [];
  @state() private connectors: ConnectorSummary[] = [];
  @state() private threads: ThreadSummary[] = [];
  @state() private system: SystemStatusSummary = {
    model: "ready",
    browser: "warning",
    plugins: "warning",
    connectors: "warning",
  };
  @state() private systemDetail = {
    model: "模型待同步",
    browser: "浏览器待同步",
    plugins: "插件待同步",
    connectors: "连接器待同步",
  };
  @state() private controlUiState: ControlUiStateSnapshot | null = null;
  @state() private attentionItems: AttentionItem[] = [];
  @state() private recentActivities: ActivityItem[] = [];
  @state() private loading = true;
  @state() private runFeedback: OperationFeedback = neutralFeedback("真实 bridge 就绪，可直接发起任务。");

  connectedCallback(): void {
    super.connectedCallback();
    this.unsubscribe = this.bridgeClient.subscribe((event) => {
      this.handleBridgeEvent(event);
    });
    void this.refreshData();
    this.scheduleGatewayPoll(1200);
  }

  disconnectedCallback(): void {
    this.unsubscribe?.();
    this.unsubscribe = null;
    if (this.gatewayPollTimer !== null) {
      clearTimeout(this.gatewayPollTimer);
      this.gatewayPollTimer = null;
    }
    super.disconnectedCallback();
  }

  render() {
    const recentTasks = this.threads.map((thread) => this.toRecentTask(thread));
    const summary = this.buildOverviewSummary();
    const activityGroups = this.groupRecentActivities();
    const operatorCards = this.buildOperatorCards(summary);
    const commandCards = this.buildOperatorCommandCards();
    const heroPills = [
      "Local-first render",
      "Approvals + Runs + Browser",
      this.loading ? "Bridge syncing" : "Bridge ready",
    ];
    const heroStats = [
      {
        label: "Pending approvals",
        value: String(summary.pendingApprovals),
        detail: summary.pendingApprovalsDetail,
      },
      {
        label: "Recent tasks",
        value: String(summary.recentTasks),
        detail: summary.recentTasksDetail,
      },
      {
        label: "Gateway events",
        value: String(summary.gatewayEvents),
        detail: summary.gatewayEventsDetail,
      },
      {
        label: "Bridge health",
        value: this.loading ? "syncing" : this.system.model,
        detail: this.loading ? "同步 control plane 状态中" : this.systemDetail.model,
      },
    ];

    return html`
      <section class="hero-card" data-testid="workbench-home-hero">
        <div class="hero-grid">
          <div class="hero-copy">
            <p class="eyebrow">AI-native operator surface</p>
            <h2 class="hero-title">
              Keep Every Run
              <span class="hero-title-accent">In Flow.</span>
            </h2>
            <p class="hero-lead">
              把对话、审批、浏览器控制和 Sessions 追踪收进同一张首页。首屏光影、轮廓流线和氛围层全部本地渲染，不依赖外网资源。
            </p>
            <p class="hero-note">SVG rails + moving radial gradients + flowing contour lines</p>
            <div class="hero-pill-row">
              ${heroPills.map((item) => html`<span class="hero-pill">${item}</span>`)}
            </div>
            <div class="hero-actions">
              <button
                class="secondary hero-button hero-button-primary"
                type="button"
                @click=${() => this.navigateToRoute("chat")}
              >
                Start With Chat
              </button>
              <button class="secondary hero-button" type="button" @click=${() => this.navigateToRoute("approvals")}>
                Review Approvals
              </button>
              <button class="secondary hero-button" type="button" @click=${() => this.navigateToRoute("sessions")}>
                Open Sessions
              </button>
            </div>
          </div>
          <div class="hero-stat-grid">
            ${heroStats.map(
              (item) => html`
                <article class="hero-stat">
                  <span class="hero-stat-label">${item.label}</span>
                  <strong class="hero-stat-value">${item.value}</strong>
                  <span class="hero-stat-detail">${item.detail}</span>
                </article>
              `,
            )}
          </div>
        </div>
      </section>

      <section class="grid console-grid">
        <article class="card card-console">
          <div class="console-header">
            <div>
              <p class="eyebrow">Control console</p>
              <h2>Operator Pulse</h2>
              <p class="lead">Bridge health snapshot that keeps urgent control decisions within reach.</p>
            </div>
            <div class="operator-card-grid">
              ${operatorCards.map(
                (card) => html`
                  <button
                    class="operator-card"
                    type="button"
                    @click=${() => this.navigateToRoute(card.route)}
                  >
                    <span class="caption">${card.title}</span>
                    <strong>${card.value}</strong>
                    <span class="lead">${card.detail}</span>
                  </button>
                `,
              )}
            </div>
          </div>
          <div class="metric-grid">
            <section class="metric">
              <span class="caption">Pending approvals</span>
              <strong>${summary.pendingApprovals}</strong>
              <span class="caption">${summary.pendingApprovalsDetail}</span>
            </section>
            <section class="metric">
              <span class="caption">Recent tasks</span>
              <strong>${summary.recentTasks}</strong>
              <span class="caption">${summary.recentTasksDetail}</span>
            </section>
            <section class="metric">
              <span class="caption">Gateway events</span>
              <strong>${summary.gatewayEvents}</strong>
              <span class="caption">${summary.gatewayEventsDetail}</span>
            </section>
            <section class="metric">
              <span class="caption">Connectors</span>
              <strong>${summary.connectors}</strong>
              <span class="caption">${summary.connectorsDetail}</span>
            </section>
          </div>
        </article>

        <article class="card card-console">
          <div class="console-header">
            <div>
              <p class="eyebrow">Operator Actions</p>
              <h2>Dispatch console</h2>
              <p class="lead">Type intent, dispatch it, and keep quick controls surfaced beside the chat.</p>
            </div>
            <div class="operator-commands__header">
              <span class="caption">${this.loading ? "同步中" : "Control plane snapshot 已同步"}</span>
              <button class="secondary" type="button" @click=${this.refreshData}>刷新</button>
            </div>
          </div>
          <div class="operator-commands">
            <textarea
              .value=${this.composeText}
              placeholder="例如：暂停 workflow_001 并打开 trace 详情。"
              @input=${this.handleInput}
            ></textarea>
            <operation-feedback-view
              data-testid="workbench-feedback"
              .feedback=${this.runFeedback}
            ></operation-feedback-view>
            <div class="operator-commands__actions">
              <div class="quick-links" data-testid="workbench-quick-links">
                <button class="secondary" type="button" @click=${() => this.navigateToRoute("chat")}>对话</button>
                <button class="secondary" type="button" @click=${() => this.navigateToRoute("approvals")}>审批</button>
                <button class="secondary" type="button" @click=${() => this.navigateToRoute("browser")}>浏览器</button>
                <button class="secondary" type="button" @click=${() => this.navigateToRoute("sessions")}>Sessions</button>
                <button class="secondary" type="button" @click=${() => this.navigateToRoute("plugins")}>连接器</button>
              </div>
              <div class="operator-commands__run">
                <button class="primary" type="button" ?disabled=${!this.composeText.trim()} @click=${this.handleRun}>
                  发起任务
                </button>
              </div>
            </div>
            <div class="operator-commands__toolbar">
              <div class="operator-card-grid">
                ${commandCards.map(
                  (card) => html`
                    <button
                      class="operator-card"
                      type="button"
                      @click=${() => this.navigateToRoute(card.route)}
                    >
                      <span class="caption">${card.title}</span>
                      <strong>${card.value}</strong>
                      <span class="lead">${card.detail}</span>
                    </button>
                  `,
                )}
              </div>
            </div>
          </div>
        </article>
      </section>

      <section class="grid secondary-grid">
        <article class="card attention-card">
          <div class="row">
            <h2>Attention</h2>
            <button class="secondary" type="button" @click=${this.refreshData}>刷新</button>
          </div>
          <ul class="attention-list">
            ${this.attentionItems.length === 0
              ? html`<li><span class="empty">暂无 attention 项。</span></li>`
              : this.attentionItems.map(
                  (item) => html`
                    <li>
                      <div class="row start">
                        <strong>${item.title}</strong>
                        <span class="pill attention-${item.level}">${item.level}</span>
                      </div>
                      <span class="caption">${item.detail}</span>
                      <button
                        class="secondary"
                        type="button"
                        @click=${() => this.handleAttentionNavigation(item)}
                        data-testid="workbench-attention-open"
                      >
                        ${item.actionLabel}
                      </button>
                    </li>
                  `,
                )}
          </ul>
        </article>

        <article class="card wide">
          <div class="row">
            <h2>Recent Activity</h2>
            <span class="caption">${this.recentActivities.length} 项</span>
          </div>
          ${activityGroups.length === 0
            ? html`<ul class="activity-list"><li><span class="empty">暂无 recent activity。</span></li></ul>`
            : html`
                <div class="activity-groups" data-testid="workbench-activity-groups">
                  ${activityGroups.map(
                    (group) => html`
                      <section class="activity-group" data-testid="workbench-activity-group">
                        <div class="activity-group-header">
                          <strong>${group.label}</strong>
                          <span class="caption">${group.items.length} 项</span>
                        </div>
                        <ul class="activity-list">
                          ${group.items.map(
                            (item) => html`
                              <li>
                                <div class="row">
                                  <strong>${item.title}</strong>
                                  <span class="caption">${item.kind}</span>
                                </div>
                                <span class="caption">${item.detail}</span>
                                <button
                                  class="secondary"
                                  type="button"
                                  @click=${() => this.handleActivityNavigation(item)}
                                  data-testid="workbench-activity-open"
                                >
                                  ${item.actionLabel}
                                </button>
                              </li>
                            `,
                          )}
                        </ul>
                      </section>
                    `,
                  )}
                </div>
              `}
        </article>
      </section>

      <section class="grid secondary-grid">
        <article class="card narrow">
          <div class="row">
            <h2>Recent Approvals</h2>
            <span class="caption">${this.pendingApprovals.length} pending</span>
          </div>
          <ul>
            ${this.pendingApprovals.length === 0
              ? html`<li><span class="empty">暂无待审批项。</span></li>`
              : this.pendingApprovals.slice(0, 4).map(
                  (approval) => html`
                    <li>
                      <div class="row">
                        <strong>${approval.title}</strong>
                        <span class="pill pending_approval">${approval.risk}</span>
                      </div>
                      <span class="caption">${approval.trace_id}</span>
                      <span class="caption">${approval.summary ?? approval.reason ?? "等待审批决策"}</span>
                      <button
                        class="secondary"
                        type="button"
                        @click=${() =>
                          this.navigateToControlContext({
                            route: "approvals",
                            traceId: approval.trace_id,
                            approvalId: approval.approval_id,
                            source: "workbench",
                          })}
                        data-testid="workbench-approval-open"
                      >
                        打开审批上下文
                      </button>
                    </li>
                  `,
                )}
          </ul>
        </article>

        <article class="card narrow">
          <div class="row">
            <h2>Recent Tasks</h2>
            <span class="caption">${recentTasks.length} 条</span>
          </div>
          <ul>
            ${recentTasks.length === 0
              ? html`<li><span class="empty">当前还没有线程记录。</span></li>`
              : recentTasks.map(
                  (task) => html`
                    <li>
                      <div class="row">
                        <strong>${task.title}</strong>
                        <span class="pill ${task.status}">${task.status}</span>
                      </div>
                      <span class="caption">${task.updatedAt}</span>
                      <span class="caption">${task.subtitle}</span>
                      <button
                        class="secondary"
                        type="button"
                        @click=${() => this.navigateToRoute("sessions")}
                        data-testid="workbench-task-open"
                      >
                        打开 Sessions
                      </button>
                    </li>
                  `,
                )}
          </ul>
        </article>
      </section>

      <section class="grid console-grid">
        <article class="card wide">
          <div class="row">
            <h2>System Health</h2>
            <span class="caption">${this.loading ? "加载中" : "已同步 bridge 与 control UI 状态"}</span>
          </div>
          <div class="metric-grid">
            ${this.renderMetric("浏览器", this.system.browser, this.systemDetail.browser)}
            ${this.renderMetric("插件", this.system.plugins, this.systemDetail.plugins)}
            ${this.renderMetric("模型", this.system.model, this.systemDetail.model)}
            ${this.renderMetric("连接器", this.system.connectors, this.systemDetail.connectors)}
          </div>
        </article>
      </section>
    `;
  }

  async refreshData() {
    this.loading = true;
    const [approvals, plugins, browser, threads, connectors, controlUiState] = await Promise.all([
      this.bridgeClient.approval.list(),
      this.bridgeClient.plugin.list(),
      this.bridgeClient.browser.status(),
      this.bridgeClient.thread.list({ limit: 6 }),
      this.bridgeClient.connector.list(),
      this.bridgeClient.controlUi.state({ limit: 12 }),
    ]);
    const pluginHealth = summarizeBridgeCollection(
      plugins,
      plugins.data?.plugins ?? [],
      (item) => item.health,
      {
        label: "插件",
        emptyDetail: "当前没有已加载插件",
      },
    );
    const connectorHealth = summarizeBridgeCollection(
      connectors,
      connectors.data?.connectors ?? [],
      (item) => item.health,
      {
        label: "连接器",
        emptyDetail: "当前没有注册连接器",
      },
    );
    this.pendingApprovals = approvals.data?.approvals ?? [];
    this.plugins = plugins.data?.plugins ?? [];
    this.threads = threads.data?.threads ?? [];
    this.connectors = connectors.data?.connectors ?? [];
    this.controlUiState = controlUiState.ok ? controlUiState.data ?? null : null;
    this.system = {
      model: this.controlUiState?.health?.status === "ok" ? "ready" : "warning",
      browser: browser.ok ? (browser.data?.running ? "ready" : "warning") : "error",
      plugins: pluginHealth.level,
      connectors: connectorHealth.level,
    };
    this.systemDetail = {
      model: this.controlUiState?.health?.status === "ok" ? "Gateway health 已就绪" : "Gateway health 未确认",
      browser: browser.ok
        ? browser.data?.running
          ? `运行中 · ${browser.data?.tabCount ?? 0} tabs`
          : "浏览器未启动"
        : browser.error?.message ?? "浏览器状态获取失败",
      plugins: pluginHealth.detail,
      connectors: connectorHealth.detail,
    };
    this.attentionItems = this.buildAttentionItems();
    this.recentActivities = this.buildRecentActivities();
    this.loading = false;
  }

  private renderMetric(label: string, level: string, detail: string) {
    return html`
      <section class="metric">
        <span class="caption">${label}</span>
        <strong class="level-${level}">${level}</strong>
        <span class="caption">${detail}</span>
      </section>
    `;
  }

  private buildOperatorCards(summary: OverviewSummary): OperatorCardDescriptor[] {
    return [
      {
        id: "operator-approvals",
        title: "Approvals",
        value: summary.pendingApprovals,
        detail: summary.pendingApprovalsDetail,
        route: "approvals",
      },
      {
        id: "operator-tasks",
        title: "Recent tasks",
        value: summary.recentTasks,
        detail: summary.recentTasksDetail,
        route: "sessions",
      },
      {
        id: "operator-events",
        title: "Gateway events",
        value: summary.gatewayEvents,
        detail: summary.gatewayEventsDetail,
        route: "sessions",
      },
      {
        id: "operator-connectors",
        title: "Connectors",
        value: summary.connectors,
        detail: summary.connectorsDetail,
        route: "plugins",
      },
    ];
  }

  private buildOperatorCommandCards(): ActionCardDescriptor[] {
    const latestTrace = this.recentActivities[0]?.traceId || "live trace";
    return [
      {
        id: "command-trace",
        title: "Trace drill-down",
        value: latestTrace,
        detail: "进入最新 Sessions trace",
        route: "sessions",
      },
      {
        id: "command-approvals",
        title: "Approval control",
        value: `${this.pendingApprovals.length} pending`,
        detail: "快速整理待审批项",
        route: "approvals",
      },
      {
        id: "command-connectors",
        title: "Connector health",
        value: `${this.connectors.length} registered`,
        detail: "打开连接器工作台",
        route: "plugins",
      },
    ];
  }

  private buildOverviewSummary(): OverviewSummary {
    const pendingApprovals = this.pendingApprovals.length;
    const gatewayEvents = this.controlUiState?.events?.length ?? 0;
    const recentTasks = this.threads.length;
    const connectors = this.connectors.length;
    return {
      pendingApprovals,
      pendingApprovalsDetail: pendingApprovals > 0 ? "需要 operator 处理" : "暂无待审批",
      gatewayEvents,
      gatewayEventsDetail: gatewayEvents > 0 ? "最近有新的 gateway events" : "暂无新 gateway events",
      recentTasks,
      recentTasksDetail: recentTasks > 0 ? "可在 Sessions/Runs 继续追踪" : "暂无任务",
      connectors,
      connectorsDetail: connectors > 0 ? "连接器已注册" : "暂无连接器",
    };
  }

  private buildAttentionItems(): AttentionItem[] {
    const items: AttentionItem[] = [];
    if (this.pendingApprovals.length > 0) {
      items.push({
        id: "approval-pending",
        title: "待审批项需要处理",
        detail: `${this.pendingApprovals.length} 条待审批动作仍在 pending`,
        level: "high",
        route: "approvals",
        traceId: this.pendingApprovals[0]?.trace_id,
        approvalId: this.pendingApprovals[0]?.approval_id,
        actionLabel: "打开审批上下文",
      });
    }
    if (this.system.browser !== "ready") {
      items.push({
        id: "browser-state",
        title: "浏览器状态降级",
        detail: this.systemDetail.browser,
        level: "medium",
        route: "browser",
        actionLabel: "打开浏览器控制",
      });
    }
    if (this.system.connectors === "error" || this.system.connectors === "warning") {
      items.push({
        id: "connector-state",
        title: "连接器状态需要关注",
        detail: this.systemDetail.connectors,
        level: this.system.connectors === "error" ? "high" : "medium",
        route: "plugins",
        actionLabel: "打开连接器",
      });
    }
    const recentTrace = this.controlUiState?.events?.[0]?.trace_id;
    if (typeof recentTrace === "string" && recentTrace) {
      items.push({
        id: "trace-follow",
        title: "近期 trace 可继续跟踪",
        detail: `trace: ${recentTrace}`,
        level: "low",
        route: "sessions",
        traceId: recentTrace,
        timelineScope: "all",
        actionLabel: "打开 Trace",
      });
    }
    return items.slice(0, 5);
  }

  private buildRecentActivities(): ActivityItem[] {
    const activities: ActivityItem[] = [];
    for (const item of this.controlUiState?.events ?? []) {
      activities.push({
        id: String(item.event_id ?? item.trace_id ?? `event-${activities.length}`),
        title: String(item.event_type ?? "gateway.event"),
        detail: String(item.trace_id ?? item.source_kind ?? "gateway event"),
        kind: "event",
        route: "sessions",
        traceId: String(item.trace_id ?? ""),
        timelineScope: "all",
        actionLabel: "打开 Sessions Trace",
      });
    }
    for (const item of this.controlUiState?.workflowRuns ?? []) {
      activities.push({
        id: String(item.workflow_run_id ?? item.trace_id ?? `workflow-${activities.length}`),
        title: String(item.workflow_name ?? item.workflow_run_id ?? "workflow run"),
        detail: String(item.trace_id ?? item.status ?? "trace unavailable"),
        kind: "workflow",
        route: "sessions",
        traceId: String(item.trace_id ?? ""),
        timelineScope: "workflowRuns",
        actionLabel: "打开 Workflow Detail",
      });
    }
    for (const item of this.controlUiState?.auditRecords ?? []) {
      activities.push({
        id: String(item.audit_id ?? item.trace_id ?? `audit-${activities.length}`),
        title: String(item.summary ?? item.stage ?? "audit record"),
        detail: String(item.trace_id ?? "trace unavailable"),
        kind: "audit",
        route: "sessions",
        traceId: String(item.trace_id ?? ""),
        timelineScope: "auditRecords",
        actionLabel: "打开审计 Trace",
      });
    }
    for (const item of this.pendingApprovals) {
      activities.push({
        id: item.approval_id,
        title: item.title,
        detail: item.summary ?? item.reason ?? item.trace_id,
        kind: "approval",
        route: "approvals",
        traceId: item.trace_id,
        approvalId: item.approval_id,
        actionLabel: "打开审批上下文",
      });
    }
    return activities.slice(0, 8);
  }

  private groupRecentActivities(): ActivityGroup[] {
    const groups = new Map<string, ActivityGroup>();
    const labels: Record<string, string> = {
      workflow: "Workflow Runs",
      approval: "Approvals",
      audit: "Audit Trail",
      event: "Gateway Events",
    };
    for (const item of this.recentActivities) {
      const key = item.kind;
      const existing = groups.get(key);
      if (existing) {
        existing.items.push(item);
        continue;
      }
      groups.set(key, {
        key,
        label: labels[key] ?? key,
        items: [item],
      });
    }
    return Array.from(groups.values());
  }

  private readonly handleInput = (event: Event) => {
    this.composeText = (event.target as HTMLTextAreaElement).value;
  };

  private readonly handleRun = async () => {
    const text = this.composeText.trim();
    if (!text) {
      return;
    }
    const response = await this.bridgeClient.task.run({ text });
    this.runFeedback = feedbackFromBridgeResponse(response, {
      successMessage: String(response.data?.assistant_text ?? "任务已提交到真实线程"),
      errorMessage: "任务提交失败",
    });
    if (!response.ok) {
      return;
    }
    this.composeText = "";
    await this.refreshData();
    this.dispatchEvent(
      new CustomEvent("workbench-run", {
        detail: { text },
        bubbles: true,
        composed: true,
      }),
    );
  };

  private toRecentTask(thread: ThreadSummary): RecentTask {
    const hasPendingApproval = this.pendingApprovals.some((item) => item.trace_id === thread.thread_id);
    const status = hasPendingApproval
      ? "pending_approval"
      : thread.thread_id === this.threads[0]?.thread_id
        ? "running"
        : "completed";
    return {
      taskId: thread.thread_id,
      title: thread.name || thread.thread_id,
      status,
      updatedAt: thread.updated_at,
      subtitle: thread.last_user_text || thread.last_assistant_text || "暂无摘要",
    };
  }

  private readonly handleBridgeEvent = (event: BridgeEvent<Record<string, unknown>>) => {
    if (
      ![
        "task_started",
        "task_progress",
        "task_completed",
        "task_failed",
        "approval_requested",
        "approval_resolved",
        "audit_written",
      ].includes(event.kind)
    ) {
      return;
    }
    this.runFeedback = neutralFeedback(event.summary || this.runFeedback.message);
    this.applyIncrementalBridgeEvent(event);
  };

  private applyIncrementalBridgeEvent(event: BridgeEvent<Record<string, unknown>>) {
    const payload = event.payload ?? {};
    const traceId = String(payload.trace_id ?? payload.traceId ?? "").trim();
    const approvalId = String(payload.approval_id ?? "").trim();

    if (event.kind === "approval_requested" && approvalId && traceId) {
      if (!this.pendingApprovals.some((item) => item.approval_id === approvalId)) {
        this.pendingApprovals = [
          {
            approval_id: approvalId,
            action_id: String(payload.action_id ?? ""),
            title: String(payload.title ?? payload.summary ?? approvalId),
            risk: "high",
            trace_id: traceId,
            status: "pending",
            summary: String(payload.summary ?? event.summary ?? "待审批"),
          },
          ...this.pendingApprovals,
        ];
      }
    }

    if (event.kind === "approval_resolved" && approvalId) {
      this.pendingApprovals = this.pendingApprovals.filter((item) => item.approval_id !== approvalId);
    }

    const nextControlUiState = this.controlUiState
      ? {
          ...this.controlUiState,
          events: [...(this.controlUiState.events ?? [])],
          approvalTickets: [...(this.controlUiState.approvalTickets ?? [])],
          auditRecords: [...(this.controlUiState.auditRecords ?? [])],
        }
      : null;

    if (nextControlUiState) {
      if (traceId) {
        nextControlUiState.events.unshift({
          event_id: event.event_id,
          event_type: event.name || event.kind,
          trace_id: traceId,
          source_kind: "bridge",
          summary: event.summary,
        });
      }
      if (event.kind === "approval_requested" && approvalId && traceId) {
        nextControlUiState.approvalTickets.unshift({
          approval_id: approvalId,
          trace_id: traceId,
          status: "pending",
          summary: String(payload.summary ?? event.summary ?? "待审批"),
        });
      }
      if (event.kind === "approval_resolved" && approvalId) {
        nextControlUiState.approvalTickets = nextControlUiState.approvalTickets.filter(
          (item) => String(item.approval_id ?? "") !== approvalId,
        );
      }
      if (event.kind === "audit_written" && traceId) {
        nextControlUiState.auditRecords.unshift({
          audit_id: String(payload.audit_id ?? event.event_id),
          trace_id: traceId,
          summary: String(payload.summary ?? event.summary ?? "audit updated"),
          stage: String(payload.stage ?? "audit"),
          status: String(payload.status ?? "ok"),
        });
      }
      this.controlUiState = nextControlUiState;
    }

    const liveActivity = this.toActivityFromBridgeEvent(event);
    if (liveActivity) {
      this.recentActivities = [liveActivity, ...this.recentActivities.filter((item) => item.id !== liveActivity.id)].slice(0, 8);
    } else {
      this.recentActivities = this.buildRecentActivities();
    }
    this.attentionItems = this.buildAttentionItems();
  }

  private scheduleGatewayPoll(delayMs = 1200) {
    if (this.gatewayPollTimer !== null) {
      clearTimeout(this.gatewayPollTimer);
    }
    this.gatewayPollTimer = setTimeout(() => {
      this.gatewayPollTimer = null;
      void this.pollGatewayEventsOnce();
    }, delayMs);
  }

  private async pollGatewayEventsOnce() {
    if (!this.isConnected || this.gatewayPolling) {
      return;
    }
    this.gatewayPolling = true;
    const response = await this.bridgeClient.gateway.events.poll({
      cursor: this.gatewayEventCursor,
      streams: ["gateway_events", "workflow_runs", "approvals", "audit"],
    });
    this.gatewayPolling = false;
    if (response.ok) {
      this.gatewayEventCursor = Number(response.data?.cursor ?? this.gatewayEventCursor);
      const frames = Array.isArray(response.data?.events) ? response.data.events : [];
      this.applyGatewayFrames(frames as GatewayEventFrame[]);
    }
    if (this.isConnected) {
      this.scheduleGatewayPoll(1200);
    }
  }

  private applyGatewayFrames(frames: GatewayEventFrame[]) {
    if (frames.length === 0) {
      return;
    }
    let changed = false;
    const nextActivities = [...this.recentActivities];
    for (const frame of frames) {
      const activity = this.toActivityFromGatewayFrame(frame);
      if (!activity) {
        continue;
      }
      changed = true;
      const existingIndex = nextActivities.findIndex((item) => item.id === activity.id);
      if (existingIndex >= 0) {
        nextActivities.splice(existingIndex, 1);
      }
      nextActivities.unshift(activity);
    }
    if (changed) {
      this.recentActivities = nextActivities.slice(0, 8);
    }
  }

  private toActivityFromBridgeEvent(event: BridgeEvent<Record<string, unknown>>): ActivityItem | null {
    const payload = event.payload ?? {};
    const traceId = String(payload.trace_id ?? payload.traceId ?? "").trim();
    if (!traceId) {
      return null;
    }
    if (event.kind === "approval_requested" || event.kind === "approval_resolved") {
      return {
        id: String(payload.approval_id ?? event.event_id),
        title: event.summary || "approval update",
        detail: traceId,
        kind: "approval",
        route: "approvals",
        traceId,
        approvalId: String(payload.approval_id ?? "").trim() || undefined,
        actionLabel: "打开审批上下文",
      };
    }
    if (event.kind === "audit_written") {
      return {
        id: String(payload.audit_id ?? event.event_id),
        title: String(payload.summary ?? event.summary ?? "audit updated"),
        detail: traceId,
        kind: "audit",
        route: "sessions",
        traceId,
        timelineScope: "auditRecords",
        actionLabel: "打开审计 Trace",
      };
    }
    return {
      id: event.event_id,
      title: event.summary || event.name,
      detail: traceId,
      kind: "event",
      route: "sessions",
      traceId,
      timelineScope: "all",
      actionLabel: "打开 Sessions Trace",
    };
  }

  private toActivityFromGatewayFrame(frame: GatewayEventFrame): ActivityItem | null {
    const payload = frame.payload ?? {};
    const traceId = String(payload.trace_id ?? payload.traceId ?? "").trim();
    if (!traceId) {
      return null;
    }
    if (frame.stream === "workflow_runs") {
      return {
        id: String(payload.workflow_run_id ?? `${frame.stream}:${frame.cursor}`),
        title: String(payload.workflow_name ?? frame.event ?? "workflow run"),
        detail: traceId,
        kind: "workflow",
        route: "sessions",
        traceId,
        timelineScope: "workflowRuns",
        actionLabel: "打开 Workflow Detail",
      };
    }
    if (frame.stream === "approvals") {
      return {
        id: String(payload.approval_id ?? `${frame.stream}:${frame.cursor}`),
        title: String(payload.summary ?? frame.event ?? "approval update"),
        detail: traceId,
        kind: "approval",
        route: "approvals",
        traceId,
        approvalId: String(payload.approval_id ?? "").trim() || undefined,
        actionLabel: "打开审批上下文",
      };
    }
    if (frame.stream === "audit") {
      return {
        id: String(payload.audit_id ?? `${frame.stream}:${frame.cursor}`),
        title: String(payload.summary ?? frame.event ?? "audit update"),
        detail: traceId,
        kind: "audit",
        route: "sessions",
        traceId,
        timelineScope: "auditRecords",
        actionLabel: "打开审计 Trace",
      };
    }
    return {
      id: `${frame.stream}:${frame.cursor}`,
      title: frame.event || "gateway event",
      detail: traceId,
      kind: "event",
      route: "sessions",
      traceId,
      timelineScope: "all",
      actionLabel: "打开 Sessions Trace",
    };
  }

  private handleAttentionNavigation(item: AttentionItem) {
    if ((item.route === "approvals" || item.route === "sessions") && item.traceId) {
      this.navigateToControlContext({
        route: item.route,
        traceId: item.traceId,
        approvalId: item.approvalId,
        timelineScope: item.timelineScope,
        source: "workbench",
      });
      return;
    }
    this.navigateToRoute(item.route);
  }

  private handleActivityNavigation(item: ActivityItem) {
    this.navigateToControlContext({
      route: item.route,
      traceId: item.traceId,
      approvalId: item.approvalId,
      timelineScope: item.timelineScope,
      source: "workbench",
    });
  }

  private navigateToRoute(route: WorkbenchRouteId) {
    this.dispatchEvent(
      new CustomEvent<WorkbenchRouteId>("route-change", {
        detail: route,
        bubbles: true,
        composed: true,
      }),
    );
  }

  private navigateToControlContext(detail: WorkbenchControlContextDetail) {
    this.dispatchEvent(
      new CustomEvent<WorkbenchControlContextDetail>("navigate-control-context", {
        detail,
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "workbench-page": WorkbenchPage;
  }
}
