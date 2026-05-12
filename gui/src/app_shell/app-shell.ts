import { LitElement, css, html } from "lit";
import { customElement, state } from "lit/decorators.js";

import { createDefaultBridgeClient } from "../bridge/client.ts";
import "../features/browser/browser-control-page.ts";
import "../features/channels/channels-operator-page.ts";
import "../features/chat/chat-task-page.ts";
import "../features/codex/codex-native-webview-page.ts";
import "../features/logs/logs-operator-page.ts";
import "../features/nodes/nodes-devices-page.ts";
import "../features/plugins/plugins-connectors-page.ts";
import "../features/approvals/approvals-audit-page.ts";
import "../features/sessions/sessions-runs-trace-page.ts";
import "../features/settings/settings-page.ts";
import "../features/workbench/workbench-home-hero-wave.ts";
import "../features/workbench/warp-workbench-page.ts";
import {
  type StatusSummary,
  statusSummaryFixture,
} from "../shared/layout/global-status-bar.ts";
import "../shared/layout/global-status-bar.ts";
import "../shared/layout/sidebar-nav.ts";
import { summarizeBridgeCollection } from "../shared/state/health-summary.ts";
import {
  GUI_ROUTE_GROUPS,
  routeFromPath,
  type GuiRouteId,
  type GuiRouteGroupId,
} from "../routes.ts";

type RouteSummary = {
  group: GuiRouteGroupId;
  title: string;
  description: string;
};

type OperatorRouteContext = {
  route: "approvals";
  traceId?: string;
  approvalId?: string;
  actionId?: string;
  auditId?: string;
  connectorKey?: string;
  source?: string;
};

type SessionTimelineScope = "all" | "workflowRuns" | "actionRequests" | "approvalTickets" | "auditRecords";

type SessionsRouteContext = {
  route: "sessions";
  traceId: string;
  workflowRunId?: string;
  timelineScope?: SessionTimelineScope;
  source?: string;
};

type PluginsConnectorFilter = "all" | "degraded" | "actionable" | "gateway";

type PluginsRouteContext = {
  route: "plugins";
  connectorKey?: string;
  connectorFilter?: PluginsConnectorFilter;
  source?: string;
};

type AuthConnectorFilter = "all" | "ingress" | "approval" | "gateway" | "plugin_app";

type AuthRouteContext = {
  route: "auth";
  connectorKey?: string;
  connectorFilter?: AuthConnectorFilter;
  source?: string;
};

type SettingsRouteContext = {
  route: "settings";
  connectorKey?: string;
  connectorFilter?: AuthConnectorFilter;
  source?: string;
};

type LogsRouteContext = {
  route: "logs";
  source?: string;
};

type ControlRouteContext =
  | OperatorRouteContext
  | SessionsRouteContext
  | PluginsRouteContext
  | AuthRouteContext
  | SettingsRouteContext
  | LogsRouteContext;

const ROUTE_SUMMARIES: Record<GuiRouteId, RouteSummary> = {
  workbench: {
    group: "chat",
    title: "工作台",
    description: "Warp 风格命令台、线程历史、文件预览和运行状态会在这里汇总展示。",
  },
  chat: {
    group: "chat",
    title: "对话与任务",
    description: "这里会承接 transcript、时间线、输入区和任务控制。",
  },
  codex: {
    group: "agent",
    title: "Codex UI",
    description: "借鉴 Codex 桌面 webview 的三栏 Agent 工作区，保留 AgentHub bridge 与工具面。",
  },
  browser: {
    group: "control",
    title: "浏览器控制",
    description: "这里会挂浏览器状态、标签页、快照、动作和 artifacts 面板。",
  },
  logs: {
    group: "settings",
    title: "Logs",
    description: "这里聚焦日志源切换、structured records、trace hotspots 与 raw tail operator flow。",
  },
  channels: {
    group: "control",
    title: "Channels",
    description: "这里聚焦 ingress / actions / approval posture 与 connector-level next-hop。",
  },
  nodes: {
    group: "control",
    title: "Nodes / Devices",
    description: "这里聚焦 local node、remote posture、pairing heuristic 与 capability next-hop。",
  },
  approvals: {
    group: "control",
    title: "审批与审计",
    description: "这里会放待审批列表、审批详情和 trace 审计链查询。",
  },
  sessions: {
    group: "control",
    title: "Sessions / Runs",
    description: "这里会承接会话列表、历史恢复和 trace timeline 挂点。",
  },
  plugins: {
    group: "control",
    title: "插件与连接器",
    description: "这里会管理插件启停、连接器健康和错误摘要。",
  },
  auth: {
    group: "settings",
    title: "Auth / Scope",
    description: "这里聚焦 gateway connect、scope、write-budget 与 origin 降级语义。",
  },
  config: {
    group: "settings",
    title: "Config",
    description: "这里聚焦 runtime config、policy draft、validate/apply/restart operator flow。",
  },
  debug: {
    group: "settings",
    title: "Debug",
    description: "这里聚焦 diagnostics、snapshots、trace hotspots 与 control-plane debug drill-down。",
  },
  settings: {
    group: "settings",
    title: "设置",
    description: "这里会管理 runtime policy、模型提供方和系统配置。",
  },
};

const ROUTE_GROUP_LOOKUP = new Map(
  GUI_ROUTE_GROUPS.map((group) => [group.id, group]),
);

@customElement("agenthub-app")
export class AgentHubApp extends LitElement {
  private readonly bridgeClient = createDefaultBridgeClient();
  private unsubscribeBridgeEvents: (() => void) | null = null;
  private refreshTimer: ReturnType<typeof setTimeout> | null = null;

  static styles = css`
    :host {
      display: block;
      min-height: 100vh;
      color: #d9e4ec;
    }

    .shell {
      display: grid;
      grid-template-columns: 248px 1fr;
      min-height: 100vh;
    }

    .codex-fullscreen {
      min-height: 100vh;
      background: #151515;
    }

    .main {
      display: grid;
      grid-template-rows: auto 1fr auto;
      min-width: 0;
      padding: 24px;
      gap: 18px;
      position: relative;
      overflow: hidden;
      isolation: isolate;
    }

    .main-background {
      position: absolute;
      inset: 0;
      pointer-events: none;
      overflow: hidden;
      z-index: 0;
    }

    .main-background-wave {
      position: absolute;
      inset: -10% -14% 8% -10%;
      opacity: 0.94;
    }

    .main-background-wash {
      position: absolute;
      inset: 0;
      background:
        radial-gradient(circle at 52% 15%, rgba(255, 232, 142, 0.08), transparent 18%),
        radial-gradient(circle at 46% 12%, rgba(251, 156, 229, 0.14), transparent 24%),
        radial-gradient(circle at 54% 18%, rgba(9, 111, 255, 0.18), transparent 30%),
        linear-gradient(180deg, rgba(2, 8, 14, 0.1), rgba(2, 8, 14, 0.18) 36%, rgba(2, 8, 14, 0.34) 100%);
    }

    .main-background-vignette {
      position: absolute;
      inset: 0;
      background:
        radial-gradient(circle at 50% 28%, transparent 18%, rgba(3, 10, 18, 0.08) 52%, rgba(3, 10, 18, 0.54) 100%),
        linear-gradient(180deg, rgba(3, 10, 18, 0.24), rgba(3, 10, 18, 0) 24%, rgba(3, 10, 18, 0.08) 64%, rgba(3, 10, 18, 0.5) 100%);
    }

    .main-workbench {
      padding-top: 18px;
    }

    .console-header {
      display: grid;
      gap: 12px;
      padding: 16px 18px;
      border-radius: 18px;
      background: linear-gradient(135deg, rgba(15, 29, 38, 0.96), rgba(8, 19, 26, 0.94));
      border: 1px solid rgba(150, 186, 196, 0.14);
      box-shadow: 0 12px 34px rgba(2, 9, 15, 0.24);
      position: relative;
      z-index: 1;
    }

    .console-header.workbench-header {
      padding: 14px 18px;
      background: linear-gradient(180deg, rgba(6, 16, 26, 0.62), rgba(6, 16, 26, 0.28));
      border-color: rgba(150, 198, 255, 0.14);
      box-shadow: 0 12px 34px rgba(2, 9, 15, 0.18);
      backdrop-filter: blur(18px);
    }

    .console-meta {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }

    .eyebrow {
      font-size: 12px;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: #8fb5a1;
    }

    .console-chip-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .console-chip {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      color: #dce9ef;
      background: rgba(21, 45, 56, 0.84);
      border: 1px solid rgba(150, 186, 196, 0.12);
    }

    h1 {
      margin: 0;
      font-size: 24px;
      line-height: 1.05;
      color: #f0f6fa;
    }

    p {
      margin: 0;
      max-width: 88ch;
      line-height: 1.5;
      color: #a7bac6;
    }

    .placeholder {
      border-radius: 22px;
      border: 1px solid rgba(150, 186, 196, 0.12);
      background: rgba(7, 19, 28, 0.84);
      min-height: 360px;
      padding: 24px 28px;
      display: grid;
      align-content: start;
      gap: 16px;
      position: relative;
      z-index: 1;
    }

    .placeholder.workbench-panel {
      min-height: unset;
      padding: 0 0 8px;
      border: 0;
      border-radius: 0;
      background: transparent;
      overflow: visible;
    }

    global-status-bar {
      position: relative;
      z-index: 1;
    }

    .placeholder-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
    }

    .card {
      min-height: 112px;
      border-radius: 18px;
      border: 1px solid rgba(150, 186, 196, 0.12);
      background: rgba(15, 33, 42, 0.72);
      padding: 16px;
      display: grid;
      align-content: start;
      gap: 8px;
    }

    .card strong {
      font-size: 15px;
      color: #e8f1f6;
    }

    .card span {
      font-size: 13px;
      line-height: 1.5;
      color: #8da4b2;
    }

    @media (max-width: 960px) {
      .shell {
        grid-template-columns: 1fr;
      }

      .main {
        padding: 16px;
      }

      .main-workbench {
        padding-top: 12px;
      }

      .main-background-wave {
        inset: -8% -42% 30% -26%;
      }
    }
  `;

  @state() private currentRoute: GuiRouteId = routeFromPath(window.location.pathname);
  @state() private statusSummary: StatusSummary = statusSummaryFixture();
  @state() private pendingApprovals = 0;
  @state() private operatorRouteContext: OperatorRouteContext | null = null;
  @state() private sessionsRouteContext: SessionsRouteContext | null = null;
  @state() private pluginsRouteContext: PluginsRouteContext | null = null;
  @state() private authRouteContext: AuthRouteContext | null = null;
  @state() private settingsRouteContext: SettingsRouteContext | null = null;
  @state() private logsRouteContext: LogsRouteContext | null = null;

  connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener("popstate", this.handlePopState);
    this.unsubscribeBridgeEvents = this.bridgeClient.subscribe(this.handleBridgeEvent);
    void this.bootstrap();
  }

  disconnectedCallback(): void {
    window.removeEventListener("popstate", this.handlePopState);
    this.unsubscribeBridgeEvents?.();
    this.unsubscribeBridgeEvents = null;
    if (this.refreshTimer !== null) {
      clearTimeout(this.refreshTimer);
      this.refreshTimer = null;
    }
    super.disconnectedCallback();
  }

  render() {
    const summary = ROUTE_SUMMARIES[this.currentRoute];
    const routeGroup = ROUTE_GROUP_LOOKUP.get(summary.group);
    const isWorkbench = this.currentRoute === "workbench";
    if (this.currentRoute === "codex") {
      return html`
        <section class="codex-fullscreen" data-route-panel="codex">
          <codex-native-webview-page></codex-native-webview-page>
        </section>
      `;
    }
    return html`
      <div class="shell">
        <sidebar-nav
          .currentRoute=${this.currentRoute}
          .pendingApprovals=${this.pendingApprovals}
          @route-change=${this.handleRouteChange}
        ></sidebar-nav>
        <section class=${isWorkbench ? "main main-workbench" : "main"}>
          ${isWorkbench
            ? html`
                <div class="main-background" aria-hidden="true">
                  <workbench-home-hero-wave class="main-background-wave"></workbench-home-hero-wave>
                  <div class="main-background-wash"></div>
                  <div class="main-background-vignette"></div>
                </div>
              `
            : null}
          <section class=${isWorkbench ? "console-header workbench-header" : "console-header"}>
            <div class="console-meta">
              <div class="eyebrow">
                ${routeGroup?.label ?? "Control"} / ${routeGroup?.description ?? "Operator Surface"} / Control Console
              </div>
              <div class="console-chip-row">
                <span class="console-chip">pending=${this.pendingApprovals}</span>
                <span class="console-chip">
                  gateway=${this.statusSummary.gateway.connected ? "online" : "degraded"}
                </span>
                <span class="console-chip">${this.statusSummary.model.detail}</span>
              </div>
            </div>
            <h1>${summary.title}</h1>
            <p>${summary.description}</p>
          </section>
          <section class=${isWorkbench ? "placeholder workbench-panel" : "placeholder"} data-route-panel=${this.currentRoute}>
            ${this.renderCurrentPage()}
          </section>
          <global-status-bar .summary=${this.statusSummary}></global-status-bar>
        </section>
      </div>
    `;
  }

  private renderCurrentPage() {
    switch (this.currentRoute) {
      case "workbench":
        return html`
          <warp-workbench-page
            .bridgeClient=${this.bridgeClient}
            @route-change=${this.handleRouteChange}
          ></warp-workbench-page>
        `;
      case "chat":
        return html`<chat-task-page .bridgeClient=${this.bridgeClient}></chat-task-page>`;
      case "codex":
        return html`
          <codex-native-webview-page></codex-native-webview-page>
        `;
      case "browser":
        return html`<browser-control-page .bridgeClient=${this.bridgeClient}></browser-control-page>`;
      case "logs":
        return html`
          <logs-operator-page
            .bridgeClient=${this.bridgeClient}
            .initialSelectedSource=${this.logsRouteContext?.source ?? ""}
            @route-change=${this.handleRouteChange}
            @navigate-control-context=${this.handleControlContextNavigation}
          ></logs-operator-page>
        `;
      case "channels":
        return html`
          <channels-operator-page
            .bridgeClient=${this.bridgeClient}
            @navigate-control-context=${this.handleControlContextNavigation}
          ></channels-operator-page>
        `;
      case "nodes":
        return html`
          <nodes-devices-page
            .bridgeClient=${this.bridgeClient}
            @route-change=${this.handleRouteChange}
            @navigate-control-context=${this.handleControlContextNavigation}
          ></nodes-devices-page>
        `;
      case "approvals":
        return html`
          <approvals-audit-page
            .bridgeClient=${this.bridgeClient}
            .initialTraceFilter=${this.operatorRouteContext?.traceId ?? ""}
            .initialApprovalId=${this.operatorRouteContext?.approvalId ?? ""}
            .initialActionId=${this.operatorRouteContext?.actionId ?? ""}
            .initialAuditId=${this.operatorRouteContext?.auditId ?? ""}
            .initialConnectorKey=${this.operatorRouteContext?.connectorKey ?? ""}
            .initialContextSource=${this.operatorRouteContext?.source ?? ""}
            @navigate-control-context=${this.handleControlContextNavigation}
          ></approvals-audit-page>
        `;
      case "sessions":
        return html`
          <sessions-runs-trace-page
            .bridgeClient=${this.bridgeClient}
            .initialTraceId=${this.sessionsRouteContext?.traceId ?? ""}
            .initialWorkflowRunId=${this.sessionsRouteContext?.workflowRunId ?? ""}
            .initialTimelineScope=${this.sessionsRouteContext?.timelineScope ?? "all"}
            @session-resumed=${this.handleSessionResumed}
            @navigate-control-context=${this.handleControlContextNavigation}
          ></sessions-runs-trace-page>
        `;
      case "plugins":
        return html`
          <plugins-connectors-page
            .bridgeClient=${this.bridgeClient}
            .initialSelectedConnectorKey=${this.pluginsRouteContext?.connectorKey ?? ""}
            .initialConnectorFilter=${this.pluginsRouteContext?.connectorFilter ?? "all"}
            .initialContextSource=${this.pluginsRouteContext?.source ?? ""}
            @route-change=${this.handleRouteChange}
            @navigate-control-context=${this.handleControlContextNavigation}
          ></plugins-connectors-page>
        `;
      case "auth":
        return html`
          <settings-page
            .bridgeClient=${this.bridgeClient}
            .surfaceMode=${"auth"}
            .initialAuthConnectorKey=${this.authRouteContext?.connectorKey ?? ""}
            .initialAuthConnectorFilter=${this.authRouteContext?.connectorFilter ?? "all"}
            .initialContextSource=${this.authRouteContext?.source ?? ""}
            @route-change=${this.handleRouteChange}
            @navigate-control-context=${this.handleControlContextNavigation}
          ></settings-page>
        `;
      case "config":
        return html`
          <settings-page
            .bridgeClient=${this.bridgeClient}
            .surfaceMode=${"config"}
            @route-change=${this.handleRouteChange}
            @navigate-control-context=${this.handleControlContextNavigation}
          ></settings-page>
        `;
      case "debug":
        return html`
          <settings-page
            .bridgeClient=${this.bridgeClient}
            .surfaceMode=${"debug"}
            @route-change=${this.handleRouteChange}
            @navigate-control-context=${this.handleControlContextNavigation}
          ></settings-page>
        `;
      case "settings":
        return html`
          <settings-page
            .bridgeClient=${this.bridgeClient}
            .initialAuthConnectorKey=${this.settingsRouteContext?.connectorKey ?? ""}
            .initialAuthConnectorFilter=${this.settingsRouteContext?.connectorFilter ?? "all"}
            .initialContextSource=${this.settingsRouteContext?.source ?? ""}
            @route-change=${this.handleRouteChange}
            @navigate-control-context=${this.handleControlContextNavigation}
          ></settings-page>
        `;
      default:
        return html`
          <div class="placeholder-grid">
            ${this.renderPlaceholderCards()}
          </div>
        `;
    }
  }

  private renderPlaceholderCards() {
    return [
      ["宿主桥接", "等待 gui/bridge 接入真实请求、事件流和错误模型。"],
      ["页面功能", "Wave 1 会在这里分别接入工作台、任务页、浏览器页等组件。"],
      ["联调状态", "当前壳层已可启动、可切页、可渲染全局状态栏。"],
    ].map(
      ([title, description]) => html`
        <article class="card">
          <strong>${title}</strong>
          <span>${description}</span>
        </article>
      `,
    );
  }

  private readonly handlePopState = () => {
    this.currentRoute = routeFromPath(window.location.pathname);
  };

  private readonly handleRouteChange = (event: CustomEvent<GuiRouteId>) => {
    this.navigateToRoute(event.detail);
  };

  private readonly handleWorkbenchRun = () => {
    this.navigateToRoute("chat");
  };

  private readonly handleSessionResumed = () => {
    this.navigateToRoute("chat");
  };

  private readonly handleControlContextNavigation = (event: CustomEvent<ControlRouteContext>) => {
    const route = event.detail?.route;
    if (route === "auth") {
      this.navigateToRoute("auth", {
        authRouteContext: {
          route,
          connectorKey: String(event.detail?.connectorKey ?? "").trim() || undefined,
          connectorFilter:
            (String(event.detail?.connectorFilter ?? "").trim() as AuthConnectorFilter) || undefined,
          source: String(event.detail?.source ?? "").trim() || undefined,
        },
      });
      return;
    }
    if (route === "logs") {
      this.navigateToRoute("logs", {
        logsRouteContext: {
          route,
          source: String(event.detail?.source ?? "").trim() || undefined,
        },
      });
      return;
    }
    if (route === "settings") {
      this.navigateToRoute("settings", {
        settingsRouteContext: {
          route,
          connectorKey: String(event.detail?.connectorKey ?? "").trim() || undefined,
          connectorFilter:
            (String(event.detail?.connectorFilter ?? "").trim() as AuthConnectorFilter) || undefined,
          source: String(event.detail?.source ?? "").trim() || undefined,
        },
      });
      return;
    }
    if (route === "plugins") {
      this.navigateToRoute("plugins", {
        pluginsRouteContext: {
          route,
          connectorKey: String(event.detail?.connectorKey ?? "").trim() || undefined,
          connectorFilter:
            (String(event.detail?.connectorFilter ?? "").trim() as PluginsConnectorFilter) || undefined,
          source: String(event.detail?.source ?? "").trim() || undefined,
        },
      });
      return;
    }
    if (route === "approvals") {
      const traceId = String(event.detail?.traceId ?? "").trim();
      const connectorKey = String(event.detail?.connectorKey ?? "").trim();
      if (!traceId && !connectorKey) {
        return;
      }
      this.navigateToRoute("approvals", {
        approvalRouteContext: {
          route,
          traceId: traceId || undefined,
          approvalId: String(event.detail?.approvalId ?? "").trim() || undefined,
          actionId: String(event.detail?.actionId ?? "").trim() || undefined,
          auditId: String(event.detail?.auditId ?? "").trim() || undefined,
          connectorKey: connectorKey || undefined,
          source: String(event.detail?.source ?? "").trim() || undefined,
        },
      });
      return;
    }
    const traceId = String(event.detail?.traceId ?? "").trim();
    if (!traceId) {
      return;
    }
    if (route === "sessions") {
      this.navigateToRoute("sessions", {
        sessionsRouteContext: {
          route,
          traceId,
          workflowRunId: String(event.detail?.workflowRunId ?? "").trim() || undefined,
          timelineScope:
            (String(event.detail?.timelineScope ?? "").trim() as SessionTimelineScope) || undefined,
          source: String(event.detail?.source ?? "").trim() || undefined,
        },
      });
    }
  };

  private readonly handleBridgeEvent = (event: { kind?: string }) => {
    const kind = String(event.kind ?? "");
    if (
      kind === "approval_requested" ||
      kind === "approval_resolved" ||
      kind === "browser_state_changed" ||
      kind === "plugin_state_changed" ||
      kind === "settings_changed" ||
      kind === "task_completed" ||
      kind === "task_failed"
    ) {
      this.scheduleRefresh();
    }
  };

  private scheduleRefresh() {
    if (this.refreshTimer !== null) {
      clearTimeout(this.refreshTimer);
    }
    this.refreshTimer = setTimeout(() => {
      this.refreshTimer = null;
      void this.bootstrap();
    }, 200);
  }

  private async bootstrap() {
    const bootstrapState = await this.loadControlUiState();
    const [browserStatus, pluginList, approvalList, connectorList, settings] = await Promise.all([
      this.bridgeClient.browser.status(),
      this.bridgeClient.plugin.list(),
      this.bridgeClient.approval.list(),
      this.bridgeClient.connector.list(),
      this.bridgeClient.settings.get(),
    ]);
    const connectorHealth = summarizeBridgeCollection(
      connectorList,
      connectorList.data?.connectors ?? [],
      (item) => item.health,
      {
        label: "连接器",
        emptyDetail: "当前没有注册连接器",
      },
    );
    const pluginHealth = summarizeBridgeCollection(
      pluginList,
      pluginList.data?.plugins ?? [],
      (item) => item.health,
      {
        label: "插件",
        emptyDetail: "当前没有已加载插件",
      },
    );
    this.pendingApprovals = approvalList.data?.approvals?.length ?? 0;
    const providerLabel = bootstrapState.bootstrap?.providerLabel?.trim() || "";
    const healthStatus = String(bootstrapState.state?.health?.status || "").trim().toLowerCase();
    const healthDetail = healthStatus === "ok" ? "gateway health: ok" : "gateway health degraded";
    const pendingApprovalsFromControlUi = Number(
      bootstrapState.state?.approvalStatus?.pending_approvals ?? bootstrapState.state?.approvalStatus?.pendingApprovals ?? 0,
    );
    const approvalSummaryCount = Number.isFinite(pendingApprovalsFromControlUi)
      ? pendingApprovalsFromControlUi
      : this.pendingApprovals;
    const runtimeProviderLabel =
      providerLabel ||
      (bootstrapState.state?.health?.provider &&
      typeof bootstrapState.state.health.provider.provider_label === "string"
        ? bootstrapState.state.health.provider.provider_label
        : "");
    this.statusSummary = {
      ...this.statusSummary,
      model: settings.ok
        ? {
            level: settings.data?.model ? "ready" : "warning",
            detail: settings.data?.model
              ? `当前模型 ${settings.data.model}${runtimeProviderLabel ? ` · ${runtimeProviderLabel}` : ""}`
              : runtimeProviderLabel || "当前未配置模型",
          }
        : {
            level: "error",
            detail: settings.error?.message ?? "模型状态获取失败",
          },
      browser: browserStatus.ok
        ? {
            level: browserStatus.data?.running ? "ready" : "warning",
            detail: browserStatus.data?.running
              ? `运行中 · ${browserStatus.data?.tabCount ?? 0} tabs`
              : "浏览器未启动",
          }
        : {
            level: "error",
            detail: browserStatus.error?.message ?? "浏览器状态获取失败",
          },
      plugins: {
        level: pluginHealth.level,
        detail: pluginHealth.detail,
      },
      connectors: {
        level: connectorHealth.level,
        detail:
          approvalSummaryCount > 0
            ? `${connectorHealth.detail} · 待审批 ${approvalSummaryCount}`
            : connectorHealth.detail,
      },
      gateway: {
        connected: bootstrapState.connected,
        detail: bootstrapState.connected
          ? `${healthDetail}${bootstrapState.bootstrap?.serverVersion ? ` · v${bootstrapState.bootstrap.serverVersion}` : ""}`
          : "control UI bootstrap/state 未连通，当前使用兼容回退数据",
      },
      approvals: {
        pending: approvalSummaryCount,
        detail: approvalSummaryCount > 0 ? `${approvalSummaryCount} pending approvals` : "暂无待审批项",
      },
    };
  }

  private navigateToRoute(
    route: GuiRouteId,
    options: {
      approvalRouteContext?: OperatorRouteContext | null;
      sessionsRouteContext?: SessionsRouteContext | null;
      pluginsRouteContext?: PluginsRouteContext | null;
      authRouteContext?: AuthRouteContext | null;
      settingsRouteContext?: SettingsRouteContext | null;
      logsRouteContext?: LogsRouteContext | null;
    } = {},
  ) {
    const path = route === "workbench" ? "/" : `/${route}`;
    window.history.pushState({}, "", path);
    this.currentRoute = route;
    this.operatorRouteContext = route === "approvals" ? options.approvalRouteContext ?? null : null;
    this.sessionsRouteContext = route === "sessions" ? options.sessionsRouteContext ?? null : null;
    this.pluginsRouteContext = route === "plugins" ? options.pluginsRouteContext ?? null : null;
    this.authRouteContext = route === "auth" ? options.authRouteContext ?? null : null;
    this.settingsRouteContext = route === "settings" ? options.settingsRouteContext ?? null : null;
    this.logsRouteContext = route === "logs" ? options.logsRouteContext ?? null : null;
  }

  private async loadControlUiState(): Promise<{
    connected: boolean;
    bootstrap: Record<string, unknown> | null;
    state: Record<string, unknown> | null;
  }> {
    const [bootstrap, state] = await Promise.all([
      this.bridgeClient.controlUi.bootstrap(),
      this.bridgeClient.controlUi.state({ limit: 20 }),
    ]);
    if (!bootstrap.ok || !state.ok) {
      return {
        connected: false,
        bootstrap: null,
        state: null,
      };
    }
    return {
      connected: true,
      bootstrap: (bootstrap.data ?? null) as Record<string, unknown> | null,
      state: (state.data ?? null) as Record<string, unknown> | null,
    };
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "agenthub-app": AgentHubApp;
  }
}
