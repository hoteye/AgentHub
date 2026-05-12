import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { GuiRouteId } from "../../routes.ts";

import { BridgeClient, createMockBridgeClient } from "../../bridge/client.ts";
import { resolveBridgeTransportConfig } from "../../shared/api/http-host.ts";
import "../../shared/components/operation-feedback-view.ts";
import type {
  AccessPostureSummary,
  ConfigApplyResult,
  ConfigRestartReport,
  ConfigValidationResult,
  ControlUiStateSnapshot,
  ConnectorSummary,
  GatewayLogTailSnapshot,
  GatewayMethodMetadata,
  PairingPendingRef,
  SettingsSnapshot,
} from "../../shared/types/bridge.ts";
import {
  errorFeedback,
  feedbackFromBridgeResponse,
  neutralFeedback,
  warningFeedback,
  type OperationFeedback,
} from "../../shared/state/operation-feedback.ts";

type RuntimePolicyForm = {
  approval_policy: string;
  sandbox_mode: string;
  web_search_mode: string;
  network_access: string;
};

type RuntimeEnvironment = {
  providerLabel: string;
  platformFamily: string;
  platformOs: string;
  shellKind: string;
  workspaceTrust: string;
  mcpServerCount: number;
  appConnectorCount: number;
};

type GatewayConnectSummary = {
  protocolVersion: string;
  pingOk: boolean;
  serverName: string;
  serverVersion: string;
  providerLabel: string;
  handshakeStatus: "ready" | "partial" | "degraded";
  methodSource: string;
  methodCount: number;
  legacyMethodCount: number;
  writeMethodCount: number;
  publicMethodCount: number;
  eventMethodCount: number;
  scopes: string[];
  methods: GatewayMethodMetadata[];
  legacyMethods: string[];
  errors: string[];
};

type AuthMethodFilter = "all" | "protected" | "write" | "events" | "public";
type AuthConnectorFilter =
  | "all"
  | "ingress"
  | "webhook"
  | "polling"
  | "actions"
  | "approval"
  | "gateway"
  | "plugin_app";

type GatewayScopeEntry = {
  scope: string;
  methods: GatewayMethodMetadata[];
  writeCount: number;
  publicCount: number;
  eventCount: number;
};

type SettingsSurfaceMode = "full" | "auth" | "config" | "debug";

type SettingsDraftValidation = {
  level: "ok" | "warning" | "error";
  changedFields: string[];
  applyableFields: string[];
  blockedFields: string[];
  restartRequired: boolean;
  restartReasons: string[];
  messages: string[];
  applyContractSummary: string;
  validateContractSummary: string;
  restartContractSummary: string;
};

type SettingsControlContextDetail = {
  route: "approvals" | "sessions";
  traceId: string;
  workflowRunId?: string;
  approvalId?: string;
  actionId?: string;
  auditId?: string;
  timelineScope?: "all" | "workflowRuns" | "actionRequests" | "approvalTickets" | "auditRecords";
  source: "settings-diagnostics" | "settings-access-posture";
};

type SettingsPluginsRouteContextDetail = {
  route: "plugins";
  connectorKey?: string;
  connectorFilter?: "all" | "degraded" | "actionable" | "gateway";
  source: "settings-auth-connectors" | "settings-diagnostics";
};

type SettingsRouteContextDetail = {
  route: "settings";
  connectorKey?: string;
  connectorFilter?: AuthConnectorFilter;
  source: "settings-auth-connectors";
};

type AuthOperatorCue = {
  id: string;
  title: string;
  detail: string;
  route: GuiRouteId | null;
  actionLabel?: string;
};

type LogSourceRouteCue = {
  route: GuiRouteId | null;
  label: string;
  note: string;
  actionLabel?: string;
};

type SettingsDiagnosticsCue = {
  id: string;
  title: string;
  detail: string;
  actionKind: "route" | "refresh" | "none";
  route?: GuiRouteId | null;
  actionLabel?: string;
};

type ParsedLogRecord = {
  id: string;
  title: string;
  detail: string;
  raw: string;
  route: GuiRouteId | null;
  actionLabel?: string;
  context?: SettingsControlContextDetail | null;
};

type ProbeInventoryEntry = {
  key: string;
  ok: boolean;
  detail: string;
  note: string;
  route: GuiRouteId | null;
  actionLabel?: string;
};

type SnapshotInventoryEntry = {
  key: string;
  count: number;
  detail: string;
  route: GuiRouteId | null;
  actionLabel?: string;
  actionKind?: "route" | "control" | "plugins";
};

type TraceHotspotEntry = {
  traceId: string;
  workflowRunId?: string;
  workflowName?: string;
  pluginName?: string;
  workflowStatus?: string;
  approvalId?: string;
  approvalCount: number;
  pendingApprovalCount: number;
  actionCount: number;
  auditCount: number;
  eventCount: number;
  priority: number;
};

type AuthRouteMapping = {
  family: string;
  route: GuiRouteId | null;
  label: string;
  note: string;
};

const EMPTY_LOG_TAIL: GatewayLogTailSnapshot = {
  source: "",
  label: "",
  path: null,
  lines: [],
  text: "",
  lineCount: 0,
  truncated: false,
  availableSources: [],
};

const EMPTY_GATEWAY_CONNECT: GatewayConnectSummary = {
  protocolVersion: "-",
  pingOk: false,
  serverName: "-",
  serverVersion: "-",
  providerLabel: "-",
  handshakeStatus: "degraded",
  methodSource: "none",
  methodCount: 0,
  legacyMethodCount: 0,
  writeMethodCount: 0,
  publicMethodCount: 0,
  eventMethodCount: 0,
  scopes: [],
  methods: [],
  legacyMethods: [],
  errors: [],
};

const APPROVAL_POLICY_OPTIONS = ["never", "on-request", "on-failure", "untrusted"] as const;
const SANDBOX_MODE_OPTIONS = ["read-only", "workspace-write", "danger-full-access"] as const;
const WEB_SEARCH_MODE_OPTIONS = ["disabled", "cached", "live"] as const;
const NETWORK_ACCESS_OPTIONS = ["enabled", "disabled"] as const;

@customElement("settings-page")
export class SettingsPage extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .panel {
      border-radius: 18px;
      border: 1px solid rgba(150, 186, 196, 0.12);
      background: rgba(10, 22, 31, 0.86);
      padding: 18px;
      display: grid;
      gap: 16px;
    }

    .panel-header {
      display: grid;
      gap: 8px;
    }

    h2,
    h3,
    p,
    label {
      margin: 0;
    }

    h2 {
      color: #eef6fa;
      font-size: 18px;
    }

    h3 {
      color: #d7e8f1;
      font-size: 16px;
    }

    p,
    label,
    .hint {
      color: #97adba;
      font-size: 14px;
      line-height: 1.55;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }

    .grid.three {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    .field {
      display: grid;
      gap: 8px;
      padding: 14px;
      border-radius: 14px;
      background: rgba(15, 31, 39, 0.76);
    }

    input[type="text"],
    select {
      width: 100%;
      border-radius: 12px;
      border: 1px solid rgba(150, 186, 196, 0.18);
      background: rgba(6, 16, 22, 0.92);
      color: #eef5f8;
      padding: 10px 12px;
      font: inherit;
    }

    .checkbox {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .readonly-value {
      color: #e4f0f6;
      font-size: 14px;
      line-height: 1.5;
      word-break: break-word;
    }

    .meta-block {
      display: grid;
      gap: 10px;
      border-radius: 14px;
      border: 1px solid rgba(150, 186, 196, 0.12);
      background: rgba(12, 25, 33, 0.64);
      padding: 14px;
    }

    .meta-line {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      color: #c8dae4;
      font-size: 13px;
      border-bottom: 1px solid rgba(150, 186, 196, 0.08);
      padding-bottom: 8px;
    }

    .meta-line:last-child {
      border-bottom: none;
      padding-bottom: 0;
    }

    .meta-line span:first-child {
      color: #96adba;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      font-size: 12px;
    }

    .actions {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }

    .actions.wrap {
      align-items: flex-start;
      flex-wrap: wrap;
    }

    .actions.inline {
      justify-content: flex-end;
    }

    .chip-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .chip-button {
      border: 1px solid rgba(150, 186, 196, 0.18);
      border-radius: 999px;
      padding: 7px 11px;
      background: rgba(15, 31, 39, 0.82);
      color: #d7e6ee;
      cursor: pointer;
      font-size: 12px;
    }

    .chip-button.active {
      border-color: rgba(111, 203, 193, 0.42);
      background: rgba(31, 80, 77, 0.88);
    }

    button {
      border: 0;
      border-radius: 999px;
      padding: 10px 16px;
      background: linear-gradient(135deg, #2c7a73, #1f5d73);
      color: white;
      cursor: pointer;
      font: inherit;
    }

    button.secondary {
      background: rgba(34, 58, 69, 0.92);
      border: 1px solid rgba(150, 186, 196, 0.16);
      color: #d8e8f0;
    }

    .log-view {
      margin: 0;
      border-radius: 14px;
      border: 1px solid rgba(150, 186, 196, 0.12);
      background: rgba(6, 16, 22, 0.96);
      color: #d7ecef;
      padding: 14px;
      font-size: 12px;
      line-height: 1.6;
      overflow-x: auto;
      white-space: pre-wrap;
      word-break: break-word;
      min-height: 160px;
    }

    .diag-list {
      display: grid;
      gap: 10px;
    }

    .diag-item {
      border-radius: 12px;
      background: rgba(12, 24, 33, 0.84);
      border: 1px solid rgba(150, 186, 196, 0.08);
      padding: 12px;
      display: grid;
      gap: 8px;
    }

    .diag-title {
      color: #e4f0f6;
      font-size: 14px;
      line-height: 1.5;
      word-break: break-word;
    }

    .diag-meta {
      color: #93aab7;
      font-size: 12px;
      line-height: 1.5;
      word-break: break-word;
    }

    .diag-status-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .diag-chip {
      border-radius: 999px;
      padding: 4px 8px;
      background: rgba(31, 80, 77, 0.32);
      color: #d8e8f0;
      font-size: 11px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }

    .diag-chip.warn {
      background: rgba(119, 84, 30, 0.3);
      color: #f6d39f;
    }

    .diag-chip.error {
      background: rgba(122, 49, 49, 0.3);
      color: #ffbdbd;
    }

    .filter-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .filter-chip {
      border: 1px solid rgba(150, 186, 196, 0.18);
      border-radius: 999px;
      padding: 7px 11px;
      background: rgba(15, 31, 39, 0.82);
      color: #d7e6ee;
      cursor: pointer;
      font-size: 12px;
    }

    .filter-chip.active {
      border-color: rgba(111, 203, 193, 0.42);
      background: rgba(31, 80, 77, 0.88);
    }

    @media (max-width: 960px) {
      .grid {
        grid-template-columns: 1fr;
      }
    }
  `;

  @property({ attribute: false }) bridgeClient: BridgeClient = createMockBridgeClient();
  @property({ type: String }) surfaceMode: SettingsSurfaceMode = "full";
  @property({ type: String }) initialAuthConnectorKey = "";
  @property({ type: String }) initialAuthConnectorFilter: AuthConnectorFilter = "all";
  @property({ type: String }) initialContextSource = "";

  @state() private snapshot: SettingsSnapshot = {
    model: "",
    browserHeadless: false,
    pluginAutoLoad: false,
    workspaceRoot: "",
  };
  @state() private feedback: OperationFeedback = neutralFeedback("尚未保存");
  @state() private runtimePolicy: RuntimePolicyForm = {
    approval_policy: "on-request",
    sandbox_mode: "workspace-write",
    web_search_mode: "live",
    network_access: "enabled",
  };
  @state() private lastAppliedSettings: SettingsSnapshot | null = null;
  @state() private configContractSummaryOverride: SettingsDraftValidation | null = null;
  @state() private environment: RuntimeEnvironment = {
    providerLabel: "",
    platformFamily: "-",
    platformOs: "-",
    shellKind: "-",
    workspaceTrust: "unknown",
    mcpServerCount: 0,
    appConnectorCount: 0,
  };
  @state() private controlUiState: ControlUiStateSnapshot | null = null;
  @state() private gatewayConnect: GatewayConnectSummary = EMPTY_GATEWAY_CONNECT;
  @state() private accessPosture: AccessPostureSummary | null = null;
  @state() private healthProbes: Record<string, unknown> = {};
  @state() private logTail: GatewayLogTailSnapshot = EMPTY_LOG_TAIL;
  @state() private diagnosticsStatus = "正在加载诊断...";
  @state() private diagnosticsLoading = false;
  @state() private autoRefreshEnabled = true;
  @state() private lastDiagnosticsRefreshLabel = "尚未刷新";
  private pendingDiagnosticsSource: string | null = null;
  @state() private lastRemoteValidation: ConfigValidationResult | null = null;
  @state() private lastRestartReport: ConfigRestartReport | null = null;
  @state() private authMethodFilter: AuthMethodFilter = "all";
  @state() private selectedAuthMethod = "";
  @state() private selectedAuthScope = "";
  @state() private authConnectors: ConnectorSummary[] = [];
  @state() private authConnectorFilter: AuthConnectorFilter = "all";
  @state() private selectedAuthConnectorKey = "";
  private diagnosticsRefreshTimer: ReturnType<typeof setTimeout> | null = null;

  connectedCallback(): void {
    super.connectedCallback();
    void this.loadSettings();
    void this.loadGatewayConnection();
    void this.loadAuthConnectors();
    void this.loadDiagnostics();
  }

  protected willUpdate(changedProperties: Map<PropertyKey, unknown>): void {
    if (changedProperties.has("initialAuthConnectorFilter")) {
      this.authConnectorFilter = this.normalizeAuthConnectorFilter(this.initialAuthConnectorFilter);
    }
    if (changedProperties.has("initialAuthConnectorKey")) {
      this.selectedAuthConnectorKey = this.initialAuthConnectorKey.trim();
    }
  }

  disconnectedCallback(): void {
    this.clearDiagnosticsRefreshTimer();
    super.disconnectedCallback();
  }

  render() {
    const liveDraftValidation = this.validateDraft();
    const draftValidation = this.configContractSummaryOverride ?? liveDraftValidation;
    const scopeEntries = this.gatewayScopeEntries();
    const selectedAuthScope = this.selectedGatewayScope(scopeEntries);
    const filteredAuthMethods = this.filteredGatewayMethods();
    const selectedAuthMethod = this.selectedGatewayMethod(filteredAuthMethods);
    const filteredAuthConnectors = this.filteredAuthConnectors();
    const selectedAuthConnector = this.selectedAuthConnector(filteredAuthConnectors);
    if (this.surfaceMode === "auth") {
      return html`
        <section class="panel">
          <div class="panel-header">
            <h2>Gateway Auth / Scope / Connect</h2>
            <p>该页面聚焦 gateway connect、method family、scope、write-budget 与 origin 降级语义，不额外发明新 auth contract。</p>
            ${this.initialContextSource
              ? html`
                  <p class="hint" data-testid="settings-context-banner">
                    handoff=${this.initialContextSource} · filter=${this.authConnectorFilter} · connector=${this.selectedAuthConnectorKey || "-"}
                  </p>
                `
              : null}
          </div>
          ${this.renderGatewayAuthSurface(
            scopeEntries,
            selectedAuthScope,
            filteredAuthMethods,
            selectedAuthMethod,
            filteredAuthConnectors,
            selectedAuthConnector,
          )}
          <div class="meta-block" data-testid="gateway-auth-diagnostics-summary">
            <div class="panel-header">
              <h3>Diagnostics Attention</h3>
              <p>当前只摘取 health.probes、control_ui.state.diagnostics 与 logs.tail 的紧凑摘要；详查仍回完整 settings diagnostics。</p>
            </div>
            <div class="grid">
              <section class="field">
                <span>Gateway Probes</span>
                <div class="readonly-value">${this.gatewayProbeHealthSummary()}</div>
              </section>
              <section class="field">
                <span>Workflow / Approval Attention</span>
                <div class="readonly-value">${this.controlUiDiagnosticsSummary()}</div>
              </section>
              <section class="field">
                <span>Log Tail Source</span>
                <div class="readonly-value">${this.logSourceSummary()}</div>
              </section>
            </div>
            <div class="actions inline">
              <button
                type="button"
                class="secondary"
                data-testid="gateway-auth-open-diagnostics"
                @click=${() => this.emitRouteChange("settings")}
              >
                打开完整设置诊断
              </button>
              <button
                type="button"
                class="secondary"
                data-testid="gateway-auth-open-sessions"
                @click=${() => this.emitRouteChange("sessions")}
              >
                打开 Sessions / Runs
              </button>
              <button
                type="button"
                class="secondary"
                data-testid="gateway-auth-open-approvals"
                @click=${() => this.emitRouteChange("approvals")}
              >
                打开审批与审计
              </button>
            </div>
          </div>
          <div class="actions wrap">
            <div class="hint" data-testid="auth-surface-refresh-meta">
              connect=${this.gatewayConnect.handshakeStatus} · ${this.lastDiagnosticsRefreshLabel}
            </div>
            <div class="actions inline">
              <button
                type="button"
                class="secondary"
                data-testid="settings-refresh-diagnostics"
                @click=${this.handleRefreshDiagnostics}
              >
                刷新 Gateway Connect
              </button>
            </div>
          </div>
        </section>
      `;
    }
    const isConfigSurface = this.surfaceMode === "config";
    const isDebugSurface = this.surfaceMode === "debug";
    const isFullSurface = this.surfaceMode === "full";
    const title = isConfigSurface
      ? "Config / Policy / Apply"
      : isDebugSurface
        ? "Debug / Diagnostics / Trace"
        : "Runtime / Provider / Model / Policy";
    const description = isConfigSurface
      ? "该页面聚焦 runtime config、policy draft、validate/apply/restart operator flow，不把 diagnostics 与 auth 混在一起。"
      : isDebugSurface
        ? "该页面聚焦 diagnostics、snapshots、trace hotspots、log drill-down 与 refresh posture。"
        : "该页面聚焦 operator runtime 面，展示当前执行环境、Provider/Model 状态和 Runtime Policy。";
    return html`
      <section class="panel">
        <div class="panel-header">
          <h2>${title}</h2>
          <p>${description}</p>
          ${this.initialContextSource
            ? html`
                <p class="hint" data-testid="settings-context-banner">
                  handoff=${this.initialContextSource} · filter=${this.authConnectorFilter} · connector=${this.selectedAuthConnectorKey || "-"}
                </p>
              `
            : null}
        </div>

        ${!isDebugSurface
          ? this.renderConfigSurface(
              draftValidation,
              liveDraftValidation,
              scopeEntries,
              selectedAuthScope,
              filteredAuthMethods,
              selectedAuthMethod,
              filteredAuthConnectors,
              selectedAuthConnector,
              isFullSurface,
            )
          : null}
        ${isConfigSurface ? this.renderConfigSurfaceConsole() : null}
        ${isDebugSurface ? this.renderDebugSurfaceConsole() : null}
        ${!isConfigSurface ? this.renderDiagnosticsSurface() : null}
      </section>
    `;
  }

  private renderConfigSurface(
    draftValidation: SettingsDraftValidation,
    liveDraftValidation: SettingsDraftValidation,
    scopeEntries: GatewayScopeEntry[],
    selectedAuthScope: GatewayScopeEntry | null,
    filteredAuthMethods: GatewayMethodMetadata[],
    selectedAuthMethod: GatewayMethodMetadata | null,
    filteredAuthConnectors: ConnectorSummary[],
    selectedAuthConnector: ConnectorSummary | null,
    includeGatewayAuth: boolean,
  ) {
    return html`
      <div class="meta-block" data-testid="runtime-environment-summary">
        <h3>环境与运行态摘要</h3>
        <div class="meta-line"><span>Provider</span><strong>${this.environment.providerLabel || "-"}</strong></div>
        <div class="meta-line"><span>Platform</span><strong>${this.environment.platformFamily} / ${this.environment.platformOs}</strong></div>
        <div class="meta-line"><span>Shell</span><strong>${this.environment.shellKind}</strong></div>
        <div class="meta-line"><span>Workspace Trust</span><strong>${this.environment.workspaceTrust}</strong></div>
        <div class="meta-line"><span>MCP Servers</span><strong>${String(this.environment.mcpServerCount)}</strong></div>
        <div class="meta-line"><span>App Connectors</span><strong>${String(this.environment.appConnectorCount)}</strong></div>
      </div>

      ${includeGatewayAuth
        ? this.renderGatewayAuthSurface(
            scopeEntries,
            selectedAuthScope,
            filteredAuthMethods,
            selectedAuthMethod,
            filteredAuthConnectors,
            selectedAuthConnector,
          )
        : null}

      <div class="grid">
        <label class="field">
          <span>当前模型 (operator view)</span>
          <div class="readonly-value" data-testid="runtime-model-readonly">
            ${this.snapshot.model || "-"}
          </div>
          <div class="hint">该值来自宿主运行态快照。</div>
        </label>
        <label class="field">
          <span>Provider Label</span>
          <div class="readonly-value" data-testid="runtime-provider-label">
            ${this.environment.providerLabel || this.snapshot.providerLabel || "-"}
          </div>
          <div class="hint">Provider/Model 的切换入口最终应对齐 gateway control-plane。</div>
        </label>
        <label class="field">
          <span>目标模型（更新入口）</span>
          <input type="text" .value=${this.snapshot.model} @input=${this.handleModelInput} />
          <div class="hint">当前 bridge 尚未把 provider/model 变更接入真正 apply contract，现阶段只做变更检测。</div>
        </label>
        <label class="field">
          <span>工作目录</span>
          <input type="text" .value=${this.snapshot.workspaceRoot} @input=${this.handleWorkspaceInput} />
          <div class="hint">当前 GUI 可显示 workspaceRoot，但未接入真实 apply/restart contract。</div>
        </label>
        <label class="field checkbox">
          <input
            type="checkbox"
            .checked=${this.snapshot.browserHeadless}
            @change=${this.handleBrowserHeadlessChange}
          />
          <span>浏览器无头模式</span>
        </label>
        <label class="field checkbox">
          <input
            type="checkbox"
            .checked=${this.snapshot.pluginAutoLoad}
            @change=${this.handlePluginAutoLoadChange}
          />
          <span>自动加载插件</span>
        </label>
      </div>

      <div class="grid three">
        <label class="field">
          <span>Approval Policy</span>
          <select
            .value=${this.runtimePolicy.approval_policy}
            @change=${this.handleRuntimePolicySelect("approval_policy")}
          >
            ${APPROVAL_POLICY_OPTIONS.map((item) => html`<option value=${item}>${item}</option>`)}
          </select>
        </label>
        <label class="field">
          <span>Sandbox Mode</span>
          <select
            .value=${this.runtimePolicy.sandbox_mode}
            @change=${this.handleRuntimePolicySelect("sandbox_mode")}
          >
            ${SANDBOX_MODE_OPTIONS.map((item) => html`<option value=${item}>${item}</option>`)}
          </select>
        </label>
        <label class="field">
          <span>Web Search Mode</span>
          <select
            .value=${this.runtimePolicy.web_search_mode}
            @change=${this.handleRuntimePolicySelect("web_search_mode")}
          >
            ${WEB_SEARCH_MODE_OPTIONS.map((item) => html`<option value=${item}>${item}</option>`)}
          </select>
        </label>
      </div>

      <div class="grid">
        <label class="field">
          <span>Network Access</span>
          <select
            .value=${this.runtimePolicy.network_access}
            @change=${this.handleRuntimePolicySelect("network_access")}
          >
            ${NETWORK_ACCESS_OPTIONS.map((item) => html`<option value=${item}>${item}</option>`)}
          </select>
          <div class="hint">该值会通过 settings.update -> runtimePolicy 写回宿主策略。</div>
        </label>
        <section class="field">
          <span>Runtime Policy 快照</span>
          <div class="readonly-value" data-testid="runtime-policy-summary">
            approval=${this.runtimePolicy.approval_policy},
            sandbox=${this.runtimePolicy.sandbox_mode},
            web=${this.runtimePolicy.web_search_mode},
            network=${this.runtimePolicy.network_access}
          </div>
        </section>
        <section class="field">
          <span>Gateway Scope / Write 面</span>
          <div class="readonly-value" data-testid="gateway-scope-summary">
            ${this.gatewayScopeSummary()}
          </div>
          <div class="hint">
            write=${this.gatewayConnect.writeMethodCount},
            events=${this.gatewayConnect.eventMethodCount},
            public=${this.gatewayConnect.publicMethodCount}
          </div>
        </section>
      </div>

      <div class="meta-block">
        <div class="panel-header">
          <h3>Config Apply / Preview</h3>
          <p data-testid="settings-apply-summary">${this.applySummaryText(draftValidation)}</p>
        </div>
        <div class="grid">
          <section class="field">
            <span>变更集</span>
            <div class="readonly-value" data-testid="settings-change-summary">
              ${draftValidation.changedFields.length ? draftValidation.changedFields.join(", ") : "当前没有待应用变更"}
            </div>
          </section>
          <section class="field">
            <span>Apply Path</span>
            <div class="readonly-value" data-testid="settings-apply-path-summary">
              ${draftValidation.applyContractSummary}
            </div>
          </section>
          <section class="field">
            <span>Blocked / Unsupported</span>
            <div class="readonly-value" data-testid="settings-blocked-summary">
              ${draftValidation.blockedFields.length
                ? draftValidation.blockedFields.join(", ")
                : "当前没有阻塞字段"}
            </div>
          </section>
          <section class="field">
            <span>Restart Impact</span>
            <div class="readonly-value" data-testid="settings-restart-summary">
              ${draftValidation.restartRequired
                ? `建议重启相关运行面：${draftValidation.restartReasons.join(", ")}`
                : "当前变更不要求额外 restart hint"}
            </div>
          </section>
          <section class="field">
            <span>Validate Contract</span>
            <div class="readonly-value" data-testid="settings-validate-contract-summary">
              ${draftValidation.validateContractSummary}
            </div>
          </section>
          <section class="field">
            <span>Restart Contract</span>
            <div class="readonly-value" data-testid="settings-restart-contract-summary">
              ${draftValidation.restartContractSummary}
            </div>
          </section>
        </div>
        <div class="diag-list" data-testid="settings-validation-messages">
          ${draftValidation.messages.map(
            (message) => html`
              <div class="diag-item">
                <span class="diag-meta">${message}</span>
              </div>
            `,
          )}
        </div>
        <div class="grid">
          <section class="field">
            <span>Remote Validate</span>
            <div class="readonly-value" data-testid="settings-remote-validate-summary">
              ${this.remoteValidationSummaryText()}
            </div>
          </section>
          <section class="field">
            <span>Restart Report</span>
            <div class="readonly-value" data-testid="settings-remote-restart-report-summary">
              ${this.remoteRestartReportSummaryText()}
            </div>
            <div class="hint">${this.remoteRestartReportHint()}</div>
          </section>
        </div>
      </div>

      <div class="actions">
        <operation-feedback-view
          data-testid="settings-feedback"
          .feedback=${this.feedback}
        ></operation-feedback-view>
        <button
          type="button"
          class="secondary"
          data-testid="settings-validate"
          @click=${this.handleValidateDraft}
        >
          仅验证草稿
        </button>
        <button
          type="button"
          class="secondary"
          data-testid="settings-restart-report"
          @click=${this.handleRestartReport}
        >
          刷新 Restart Report
        </button>
        <button
          type="button"
          data-testid="settings-save"
          ?disabled=${liveDraftValidation.applyableFields.length === 0}
          @click=${this.handleSave}
        >
          ${liveDraftValidation.blockedFields.length ? "应用支持字段" : "应用 Runtime 设置"}
        </button>
      </div>
    `;
  }

  private renderConfigSurfaceConsole() {
    return html`
      <div class="meta-block" data-testid="settings-config-console">
        <div class="panel-header">
          <h3>Config Surface Next Hop</h3>
          <p>Config 面只保留运行态编辑与 apply/validate/restart。Auth 和 diagnostics 进入独立 surface。</p>
        </div>
        <div class="grid">
          <section class="field">
            <span>Gateway Connect</span>
            <div class="readonly-value">${this.gatewayConnect.handshakeStatus}</div>
            <div class="hint">${this.gatewayConnectStatusSummary()}</div>
          </section>
          <section class="field">
            <span>Recent Validate</span>
            <div class="readonly-value">${this.remoteValidationSummaryText()}</div>
            <div class="hint">${this.remoteRestartReportSummaryText()}</div>
          </section>
          <section class="field">
            <span>Diagnostics Snapshot</span>
            <div class="readonly-value">${this.controlUiDiagnosticsSummary()}</div>
            <div class="hint">${this.logSourceSummary()}</div>
          </section>
        </div>
        <div class="actions inline">
          <button
            type="button"
            class="secondary"
            data-testid="settings-config-open-auth"
            @click=${() => this.emitRouteChange("auth")}
          >
            打开 Auth / Scope
          </button>
          <button
            type="button"
            class="secondary"
            data-testid="settings-config-open-debug"
            @click=${() => this.emitRouteChange("debug")}
          >
            打开 Debug
          </button>
          <button
            type="button"
            class="secondary"
            data-testid="settings-config-open-logs"
            @click=${this.navigateToLogsSurface}
          >
            打开 Logs
          </button>
        </div>
      </div>
    `;
  }

  private renderDebugSurfaceConsole() {
    return html`
      <div class="meta-block" data-testid="settings-debug-console">
        <div class="panel-header">
          <h3>Debug Entry Console</h3>
          <p>Debug 面只保留诊断、快照、trace 与日志 drill-down；配置写入动作回到 Config 面完成。</p>
        </div>
        <div class="grid">
          <section class="field">
            <span>Gateway Probes</span>
            <div class="readonly-value">${this.gatewayProbeSummary()}</div>
            <div class="hint">${this.gatewayProbeHealthSummary()}</div>
          </section>
          <section class="field">
            <span>Control UI</span>
            <div class="readonly-value">${this.controlUiSnapshotSummary()}</div>
            <div class="hint">${this.controlUiDiagnosticsSummary()}</div>
          </section>
          <section class="field">
            <span>Log Tail</span>
            <div class="readonly-value">${this.logSourceSummary()}</div>
            <div class="hint">${this.lastDiagnosticsRefreshLabel}</div>
          </section>
        </div>
        <div class="actions inline">
          <button
            type="button"
            class="secondary"
            data-testid="settings-debug-open-config"
            @click=${() => this.emitRouteChange("config")}
          >
            打开 Config
          </button>
          <button
            type="button"
            class="secondary"
            data-testid="settings-debug-open-auth"
            @click=${() => this.emitRouteChange("auth")}
          >
            打开 Auth / Scope
          </button>
          <button
            type="button"
            class="secondary"
            data-testid="settings-debug-open-logs"
            @click=${this.navigateToLogsSurface}
          >
            打开 Logs
          </button>
        </div>
      </div>
    `;
  }

  private renderDiagnosticsSurface() {
    return html`
      <div class="meta-block">
        <div class="panel-header">
          <div>
            <h3>Control-Plane Diagnostics</h3>
            <p data-testid="diagnostics-status">${this.diagnosticsStatus}</p>
          </div>
          <div class="actions inline">
            <button
              type="button"
              class="secondary"
              data-testid="settings-log-route-open-logs"
              @click=${() =>
                this.dispatchEvent(
                  new CustomEvent("navigate-control-context", {
                    detail: {
                      route: "logs",
                      source: this.logTail.source || undefined,
                    },
                    bubbles: true,
                    composed: true,
                  }),
                )}
            >
              打开 Logs 页面
            </button>
          </div>
        </div>

        <div class="grid">
          <section class="field">
            <span>Gateway Probes</span>
            <div class="readonly-value" data-testid="gateway-probes-summary">
              ${this.gatewayProbeSummary()}
            </div>
          </section>
          <section class="field">
            <span>Control UI Diagnostics</span>
            <div class="readonly-value" data-testid="control-ui-diagnostics-summary">
              ${this.controlUiDiagnosticsSummary()}
            </div>
          </section>
          <section class="field">
            <span>Operator Surface Snapshot</span>
            <div class="readonly-value" data-testid="control-ui-snapshot-summary">
              ${this.controlUiSnapshotSummary()}
            </div>
          </section>
          <section class="field">
            <span>Log Tail Source</span>
            <div class="readonly-value" data-testid="log-tail-source-summary">
              ${this.logSourceSummary()}
            </div>
          </section>
          <label class="field">
            <span>Log Source</span>
            <select data-testid="settings-log-source-select" .value=${this.logTail.source} @change=${this.handleLogSourceChange}>
              ${this.logTail.availableSources.map(
                (item) => html`<option value=${item.key}>${item.label}</option>`,
              )}
            </select>
            <div class="hint">${this.logTail.path || "暂无可用日志源"}</div>
          </label>
        </div>

        <div class="meta-block" data-testid="settings-log-route-cue">
          <div class="panel-header">
            <h3>Log Source Next Hop</h3>
            <p>当前只按已知 log source key 把 operator 引到最接近的现有页面，不发明 logs family 新协议。</p>
          </div>
          ${(() => {
            const cue = this.logSourceRouteCue();
            return html`
              <div class="readonly-value">route=${cue.label}</div>
              <div class="hint">${cue.note}</div>
              <div class="actions inline">
                <button
                  type="button"
                  class="secondary"
                  data-testid="settings-log-route-open-logs"
                  @click=${this.navigateToLogsSurface}
                >
                  打开 Logs 面
                </button>
                ${cue.route && cue.actionLabel
                  ? html`
                      <button
                        type="button"
                        class="secondary"
                        data-testid="settings-log-route-open"
                        @click=${() => this.emitRouteChange(cue.route!)}
                      >
                        ${cue.actionLabel}
                      </button>
                    `
                  : html`<span class="hint">当前日志源只保留文本可见性。</span>`}
              </div>
            `;
          })()}
        </div>

        <div class="meta-block" data-testid="settings-log-source-inventory">
          <div class="panel-header">
            <h3>Available Log Sources</h3>
            <p>当前直接复用 logs.tail.availableSources 做 source inventory 与 quick-hop，不新增 logs family 查询接口。</p>
          </div>
          <div class="diag-list">
            ${this.renderLogSourceInventory()}
          </div>
        </div>

        <div class="meta-block" data-testid="settings-diagnostics-cues">
          <div class="panel-header">
            <h3>Diagnostics Attention Cues</h3>
            <p>当前基于 probes、workflow diagnostics、approval diagnostics 与 log source 给出最小 next-hop，不引入新的 diagnostics contract。</p>
          </div>
          <div class="diag-list">
            ${this.settingsDiagnosticsCues().map(
              (cue) => html`
                <section class="diag-item" data-testid=${`settings-diagnostics-cue-${cue.id}`}>
                  <div class="diag-title">${cue.title}</div>
                  <div class="diag-meta">${cue.detail}</div>
                  <div class="actions inline">
                    ${cue.actionKind === "refresh"
                      ? html`
                          <button
                            type="button"
                            class="secondary"
                            data-testid=${`settings-diagnostics-cue-open-${cue.id}`}
                            @click=${this.handleRefreshDiagnostics}
                          >
                            ${cue.actionLabel || "刷新诊断 / 日志"}
                          </button>
                        `
                      : cue.actionKind === "route" && cue.route && cue.actionLabel
                        ? html`
                            <button
                              type="button"
                              class="secondary"
                              data-testid=${`settings-diagnostics-cue-open-${cue.id}`}
                              @click=${() => this.emitRouteChange(cue.route!)}
                            >
                              ${cue.actionLabel}
                            </button>
                          `
                        : html`<span class="hint">当前无需额外动作</span>`}
                  </div>
                </section>
              `,
            )}
          </div>
        </div>

        <div class="meta-block" data-testid="settings-probe-inventory">
          <div class="panel-header">
            <h3>Probe Inventory</h3>
            <p>当前直接展开 health.probes 返回的 probe map；只对能明确映射的 probe 给 quick-hop。</p>
          </div>
          <div class="diag-list">
            ${this.renderProbeInventory()}
          </div>
        </div>

        <div class="meta-block" data-testid="settings-snapshot-inventory">
          <div class="panel-header">
            <h3>Control UI Snapshot Inventory</h3>
            <p>当前直接展开 control_ui.state 快照里的核心集合计数，并给出对应 operator 面的 quick-hop。</p>
          </div>
          <div class="diag-list">
            ${this.renderSnapshotInventory()}
          </div>
        </div>

        <div class="meta-block" data-testid="settings-trace-hotspots">
          <div class="panel-header">
            <h3>Trace Hotspots</h3>
            <p>当前按 trace_id 聚合 workflowRuns / actionRequests / approvalTickets / auditRecords / events，并把 operator 直接送到已有 trace 上下文。</p>
          </div>
          <div class="diag-list">
            ${this.renderTraceHotspots()}
          </div>
        </div>

        <div class="meta-block" data-testid="settings-log-records">
          <div class="panel-header">
            <h3>Recent Log Records</h3>
            <p>当前只对现有 JSONL 行做前端安全解析；无法识别时仍回退到原始文本。</p>
          </div>
          <div class="diag-list">
            ${this.renderLogRecords()}
          </div>
        </div>

        <div class="actions wrap">
          <div class="hint" data-testid="diagnostics-refresh-meta">
            ${this.autoRefreshEnabled ? "自动刷新已开启" : "自动刷新已暂停"}
            · ${this.lastDiagnosticsRefreshLabel}
            · ${this.diagnosticsLoading ? "刷新中" : "空闲"}
          </div>
          <div class="actions inline">
            <button
              type="button"
              class="secondary"
              data-testid="settings-toggle-auto-refresh"
              @click=${this.handleToggleAutoRefresh}
            >
              ${this.autoRefreshEnabled ? "暂停自动刷新" : "开启自动刷新"}
            </button>
            <button
              type="button"
              class="secondary"
              data-testid="settings-refresh-diagnostics"
              @click=${this.handleRefreshDiagnostics}
            >
              刷新诊断 / 日志
            </button>
          </div>
        </div>

        <div class="grid">
          <section class="field">
            <span>Workflow Diagnostics Drill-down</span>
            <div class="diag-list" data-testid="workflow-diagnostics-list">
              ${this.renderWorkflowDiagnostics()}
            </div>
          </section>
          <section class="field">
            <span>Approval Diagnostics Drill-down</span>
            <div class="diag-list" data-testid="approval-diagnostics-list">
              ${this.renderApprovalDiagnostics()}
            </div>
          </section>
        </div>

        <pre class="log-view" data-testid="gateway-log-tail">${this.logTailText()}</pre>
      </div>
    `;
  }

  private renderGatewayAuthSurface(
    scopeEntries: GatewayScopeEntry[],
    selectedAuthScope: GatewayScopeEntry | null,
    filteredAuthMethods: GatewayMethodMetadata[],
    selectedAuthMethod: GatewayMethodMetadata | null,
    filteredAuthConnectors: ConnectorSummary[],
    selectedAuthConnector: ConnectorSummary | null,
  ) {
    return html`
      <div class="meta-block" data-testid="gateway-connect-summary">
        <h3>Gateway Connect / Auth Surface</h3>
        <div class="meta-line"><span>Handshake</span><strong>${this.gatewayConnect.handshakeStatus}</strong></div>
        <div class="meta-line"><span>Protocol</span><strong>${this.gatewayConnect.protocolVersion}</strong></div>
        <div class="meta-line"><span>Ping</span><strong>${this.gatewayConnect.pingOk ? "ok" : "degraded"}</strong></div>
        <div class="meta-line"><span>Server</span><strong>${this.gatewayConnect.serverName} / ${this.gatewayConnect.serverVersion}</strong></div>
        <div class="meta-line"><span>Provider</span><strong>${this.gatewayProviderLabelSummary()}</strong></div>
        <div class="meta-line"><span>Method Source</span><strong>${this.gatewayConnect.methodSource}</strong></div>
        <div class="meta-line"><span>Methods</span><strong>${String(this.gatewayConnect.methodCount)}</strong></div>
        <div class="meta-line"><span>Legacy</span><strong>${String(this.gatewayConnect.legacyMethodCount)}</strong></div>
        <div class="diag-list" data-testid="gateway-connect-errors">
          ${(this.gatewayConnect.errors.length ? this.gatewayConnect.errors : [this.gatewayConnectStatusSummary()]).map(
            (message) => html`
              <div class="diag-item">
                <span class="diag-meta">${message}</span>
              </div>
            `,
          )}
        </div>
        <div class="hint" data-testid="gateway-connect-recovery-hint">${this.gatewayConnectRecoveryHint()}</div>
      </div>

      <div class="meta-block" data-testid="gateway-auth-summary">
        <h3>Gateway Auth / Origin / Write Visibility</h3>
        <div class="meta-line"><span>Transport</span><strong>${this.transportModeSummary()}</strong></div>
        <div class="meta-line"><span>Origin</span><strong>${this.transportOriginSummary()}</strong></div>
        <div class="meta-line"><span>Auth Hint</span><strong>${this.authContextSummary()}</strong></div>
        <div class="meta-line"><span>Protected Methods</span><strong>${String(this.gatewayConnect.methodCount - this.gatewayConnect.publicMethodCount)}</strong></div>
        <div class="meta-line"><span>Write Budget</span><strong>${this.writeBudgetKeySummary()}</strong></div>
        <div class="hint" data-testid="gateway-origin-hint">${this.originDegradeHint()}</div>
      </div>

      <div class="meta-block" data-testid="gateway-access-posture-summary">
        <div class="panel-header">
          <h3>Access / Pairing Posture</h3>
          <p>当前优先消费 gateway 只读 posture contract；只表达 access、auth 与 pairing 摘要，不提前发明写接口。</p>
        </div>
        <div class="meta-line"><span>Access</span><strong>${this.accessPostureVisibilitySummary()}</strong></div>
        <div class="meta-line"><span>Auth Mode</span><strong>${this.accessPostureAuthSummary()}</strong></div>
        <div class="meta-line"><span>Roles / Scopes</span><strong>${this.accessPostureScopeSummary()}</strong></div>
        <div class="meta-line"><span>Pairing</span><strong>${this.accessPosturePairingSummary()}</strong></div>
        <div class="diag-list" data-testid="gateway-access-posture-pending-refs">
          ${this.renderAccessPosturePendingRefs()}
        </div>
        <div class="hint" data-testid="gateway-access-posture-hint">${this.accessPostureHint()}</div>
      </div>

      <div class="meta-block" data-testid="gateway-auth-operator-cues">
        <div class="panel-header">
          <h3>Operator Cues</h3>
          <p>当前只基于 connect / method metadata / connector visibility 给出下一跳建议，不发明额外 auth contract。</p>
        </div>
        <div class="diag-list">
          ${this.authOperatorCues().map(
            (cue) => html`
              <section class="diag-item" data-testid=${`gateway-auth-cue-${cue.id}`}>
                <div class="diag-title">${cue.title}</div>
                <div class="diag-meta">${cue.detail}</div>
                <div class="actions inline">
                  ${cue.route && cue.actionLabel
                    ? html`
                        <button
                          type="button"
                          class="secondary"
                          data-testid=${`gateway-auth-cue-open-${cue.id}`}
                          @click=${() => this.emitRouteChange(cue.route!)}
                        >
                          ${cue.actionLabel}
                        </button>
                      `
                    : html`<span class="hint">当前无需额外 route 跳转</span>`}
                </div>
              </section>
            `,
          )}
        </div>
      </div>

      <div class="meta-block" data-testid="gateway-transport-contract">
        <h3>Transport / Handshake Contract</h3>
        ${this.transportContractEntries().map(
          (entry) => html`<div class="meta-line"><span>${entry.label}</span><strong>${entry.value}</strong></div>`,
        )}
      </div>

      <div class="meta-block" data-testid="gateway-auth-methods">
        <div class="panel-header">
          <h3>Auth Method / Scope Drill-down</h3>
          <p>当前直接基于 connect.capabilities / connect.initialize 返回的 method metadata 展开，不额外发明 auth contract。</p>
        </div>
        <div class="grid">
          <section class="field">
            <span>Family Summary</span>
            <div class="readonly-value" data-testid="gateway-family-summary">${this.gatewayFamilySummary()}</div>
          </section>
          <section class="field">
            <span>Scope Inventory</span>
            <div class="readonly-value" data-testid="gateway-scope-inventory">${this.gatewayScopeInventory()}</div>
          </section>
          <section class="field">
            <span>Legacy Methods</span>
            <div class="readonly-value" data-testid="gateway-legacy-methods">
              ${this.gatewayConnect.legacyMethods.length ? this.gatewayConnect.legacyMethods.join(", ") : "当前没有 legacy methods"}
            </div>
          </section>
        </div>
        <div class="grid">
          <section class="field">
            <span>Scope -> Methods</span>
            <div class="chip-row" data-testid="gateway-scope-chip-row">
              ${scopeEntries.length === 0
                ? html`<span class="hint">暂无 scope inventory</span>`
                : scopeEntries.map(
                  (entry) => html`
                    <button
                      type="button"
                      class="chip-button ${selectedAuthScope?.scope === entry.scope ? "active" : ""}"
                      data-testid=${`gateway-scope-select-${this.testIdPart(entry.scope)}`}
                      @click=${() => this.selectAuthScope(entry.scope)}
                    >
                      ${entry.scope} ${entry.methods.length}
                    </button>
                  `,
                )}
            </div>
            <div class="hint">从 scope 反查当前 gateway connect surface 暴露了哪些 methods。</div>
          </section>
          <section class="field" data-testid="gateway-scope-detail">
            ${selectedAuthScope
              ? html`
                  <span>Scope Detail</span>
                  <div class="readonly-value">${selectedAuthScope.scope}</div>
                  <div class="readonly-value">
                    methods=${selectedAuthScope.methods.length},
                    write=${selectedAuthScope.writeCount},
                    events=${selectedAuthScope.eventCount},
                    public=${selectedAuthScope.publicCount}
                  </div>
                  <div class="diag-list" data-testid="gateway-scope-methods">
                    ${selectedAuthScope.methods.map(
                      (method) => html`
                        <section class="diag-item">
                          <div class="diag-title">${method.method}</div>
                          <div class="diag-meta">${method.description || "暂无 method 描述"}</div>
                          <div class="actions inline">
                            <button
                              type="button"
                              class="secondary"
                              data-testid=${`gateway-scope-open-${method.method}`}
                              @click=${() => this.inspectAuthMethod(method.method)}
                            >
                              查看 Method Detail
                            </button>
                          </div>
                        </section>
                      `,
                    )}
                  </div>
                `
              : html`<span class="hint">当前 connect surface 未返回 scope inventory。</span>`}
          </section>
        </div>
        <div class="meta-block" data-testid="gateway-route-mappings">
          <div class="panel-header">
            <h3>Family -> Route Mapping</h3>
            <p>当前只表达 GUI 现有 operator 面如何承接各 family，不发明新的 gateway contract。</p>
          </div>
          <div class="diag-list">
            ${this.gatewayFamilyRouteMappings().map(
              (entry) => html`
                <section class="diag-item" data-testid=${`gateway-route-mapping-${this.testIdPart(entry.family)}`}>
                  <div class="diag-title">${entry.family}</div>
                  <div class="diag-meta">route=${entry.label}</div>
                  <div class="diag-meta">${entry.note}</div>
                  <div class="actions inline">
                    ${entry.route
                      ? html`
                          <button
                            type="button"
                            class="secondary"
                            data-testid=${`gateway-route-open-${entry.family}`}
                            @click=${() => this.emitRouteChange(entry.route!)}
                          >
                            打开 ${entry.label}
                          </button>
                        `
                      : html`<span class="hint">当前没有 dedicated route</span>`}
                  </div>
                </section>
              `,
            )}
          </div>
        </div>
        <div class="meta-block" data-testid="gateway-auth-connectors">
          <div class="panel-header">
            <h3>External Auth / Ingress Visibility</h3>
            <p>当前直接复用 connector.list 返回的 connector metadata，先表达 ingress、外部动作和 approval 风险，不额外发明 channels.* / auth 管理协议。</p>
          </div>
          <div class="grid three" data-testid="gateway-auth-connector-summary">
            <section class="field">
              <span>Connectors</span>
              <div class="readonly-value">${String(this.authConnectors.length)}</div>
              <div class="hint">${this.authConnectorSourceSummary()}</div>
            </section>
            <section class="field">
              <span>Ingress</span>
              <div class="readonly-value">${String(this.ingressConnectorCount())}</div>
              <div class="hint">${this.authConnectorIngressSummary()}</div>
            </section>
            <section class="field">
              <span>Approval Risk</span>
              <div class="readonly-value">${String(this.approvalRequiredConnectorCount())}</div>
              <div class="hint">${this.authConnectorApprovalSummary()}</div>
            </section>
          </div>
          <div class="grid">
            <section class="field" data-testid="gateway-auth-channel-summary">
              <span>Channel Posture</span>
              <div class="readonly-value">
                webhook=${this.webhookConnectorCount()},
                polling=${this.pollingConnectorCount()},
                actions=${this.actionConnectorCount()}
              </div>
              <div class="hint">
                event types=${this.authConnectorEventTypeCount()},
                action types=${this.authConnectorActionTypeCount()}；当前作为 channels surface 的第一版真实入口。
              </div>
            </section>
          </div>
          <div class="chip-row" data-testid="gateway-auth-connector-filter-row">
            ${this.renderAuthConnectorFilterChip("all", `全部 ${this.authConnectors.length}`)}
            ${this.renderAuthConnectorFilterChip("ingress", `Ingress ${this.ingressConnectorCount()}`)}
            ${this.renderAuthConnectorFilterChip("webhook", `Webhook ${this.webhookConnectorCount()}`)}
            ${this.renderAuthConnectorFilterChip("polling", `Polling ${this.pollingConnectorCount()}`)}
            ${this.renderAuthConnectorFilterChip("actions", `Actions ${this.actionConnectorCount()}`)}
            ${this.renderAuthConnectorFilterChip("approval", `Approval ${this.approvalRequiredConnectorCount()}`)}
            ${this.renderAuthConnectorFilterChip("gateway", `Gateway ${this.authConnectors.filter((item) => item.source_kind === "gateway").length}`)}
            ${this.renderAuthConnectorFilterChip(
              "plugin_app",
              `App ${this.authConnectors.filter((item) => item.source_kind !== "gateway").length}`,
            )}
          </div>
          <div class="grid">
            <section class="field">
              <span>Connector Candidates</span>
              <div class="diag-list" data-testid="gateway-auth-connector-list">
                ${filteredAuthConnectors.length === 0
                  ? html`<div class="diag-item"><span class="diag-meta">当前筛选下没有 connector。</span></div>`
                  : filteredAuthConnectors.map(
                    (connector) => html`
                      <section class="diag-item">
                        <div class="diag-title">${connector.display_name}</div>
                        <div class="diag-status-row">
                          <span class="diag-chip">${connector.source_kind ?? "plugin"}</span>
                          <span class="diag-chip ${connector.supports_actions ? "warn" : ""}">
                            ${connector.supports_actions ? "actions" : "read"}
                          </span>
                          <span class="diag-chip ${connector.approval_required ? "warn" : ""}">
                            ${connector.approval_required ? "approval" : "direct"}
                          </span>
                        </div>
                        <div class="diag-meta">${this.authConnectorCapabilitySummary(connector)}</div>
                        <div class="actions inline">
                          <button
                            type="button"
                            class="secondary"
                            data-testid=${`gateway-auth-connector-select-${this.testIdPart(connector.connector_key)}`}
                            @click=${() => this.selectAuthConnector(connector.connector_key)}
                          >
                            查看 Connector Detail
                          </button>
                        </div>
                      </section>
                    `,
                  )}
              </div>
            </section>
            <section class="field" data-testid="gateway-auth-connector-detail">
              ${selectedAuthConnector
                ? html`
                    <span>Connector Detail</span>
                    <div class="readonly-value">${selectedAuthConnector.display_name}</div>
                    <div class="readonly-value">
                      ${selectedAuthConnector.connector_key} · ${selectedAuthConnector.plugin_name} · ${selectedAuthConnector.connector_kind}
                    </div>
                    <div class="readonly-value">
                      source=${selectedAuthConnector.source_kind ?? "plugin"},
                      lifecycle=${selectedAuthConnector.enabled ? "enabled" : "disabled"},
                      approval=${selectedAuthConnector.approval_required ? "required" : "direct"}
                    </div>
                    <div class="readonly-value">${this.authConnectorCapabilitySummary(selectedAuthConnector)}</div>
                    <div class="readonly-value">
                      events=${String(selectedAuthConnector.event_types?.length ?? 0)},
                      actions=${String(selectedAuthConnector.action_types?.length ?? 0)}
                    </div>
                    <div class="hint">${this.authConnectorOperatorNote(selectedAuthConnector)}</div>
                    <div class="actions inline">
                      ${selectedAuthConnector.approval_required
                        ? html`
                            <button
                              type="button"
                              class="secondary"
                              data-testid="gateway-auth-connector-open-approvals"
                              @click=${() => this.dispatchEvent(
                                new CustomEvent<{
                                  route: "approvals";
                                  connectorKey?: string;
                                  source: "settings-auth-connectors";
                                }>("navigate-control-context", {
                                  detail: {
                                    route: "approvals",
                                    connectorKey: selectedAuthConnector.connector_key,
                                    source: "settings-auth-connectors",
                                  },
                                  bubbles: true,
                                  composed: true,
                                }),
                              )}
                            >
                              打开审批与审计
                            </button>
                          `
                        : null}
                      <button
                        type="button"
                        class="secondary"
                        data-testid="gateway-auth-connector-open-settings"
                        @click=${() => this.navigateToSettingsConnectorContext({
                          route: "settings",
                          connectorKey: selectedAuthConnector.connector_key,
                          connectorFilter:
                            selectedAuthConnector.source_kind === "gateway" ? "gateway" : "approval",
                          source: "settings-auth-connectors",
                        })}
                      >
                        打开设置
                      </button>
                      <button
                        type="button"
                        class="secondary"
                        data-testid="gateway-auth-connector-open-plugins"
                        @click=${() => this.navigateToPluginsConnectorContext({
                          route: "plugins",
                          connectorKey: selectedAuthConnector.connector_key,
                          connectorFilter:
                            selectedAuthConnector.source_kind === "gateway" ? "gateway" : "actionable",
                          source: "settings-auth-connectors",
                        })}
                      >
                        打开插件与连接器
                      </button>
                    </div>
                  `
                : html`<span class="hint">选择一个 connector 后在这里查看 external auth / ingress detail。</span>`}
            </section>
          </div>
        </div>
        <div class="chip-row" data-testid="gateway-method-filter-row">
          ${this.renderAuthFilterChip("all", `全部 ${this.gatewayConnect.methods.length}`)}
          ${this.renderAuthFilterChip("protected", `受保护 ${Math.max(0, this.gatewayConnect.methodCount - this.gatewayConnect.publicMethodCount)}`)}
          ${this.renderAuthFilterChip("write", `写 ${this.gatewayConnect.writeMethodCount}`)}
          ${this.renderAuthFilterChip("events", `事件 ${this.gatewayConnect.eventMethodCount}`)}
          ${this.renderAuthFilterChip("public", `公开 ${this.gatewayConnect.publicMethodCount}`)}
        </div>
        <div class="grid">
          <section class="field">
            <span>Methods</span>
            <div class="diag-list" data-testid="gateway-method-list">
              ${filteredAuthMethods.length === 0
                ? html`<div class="diag-item"><span class="diag-meta">当前筛选下没有 method。</span></div>`
                : filteredAuthMethods.map(
                  (method) => html`
                    <section class="diag-item">
                      <div class="diag-title">${method.method}</div>
                      <div class="diag-status-row">
                        <span class="diag-chip">${method.family}</span>
                        <span class="diag-chip ${method.control_plane_write ? "warn" : ""}">
                          ${method.control_plane_write ? "write" : "read"}
                        </span>
                        <span class="diag-chip ${method.auth_required === false ? "" : "warn"}">
                          ${method.auth_required === false ? "public" : "protected"}
                        </span>
                      </div>
                      <div class="diag-meta">${this.gatewayMethodScopeSummary(method)}</div>
                      <div class="actions inline">
                        <button
                          type="button"
                          class="secondary"
                          data-testid=${`gateway-method-select-${method.method}`}
                          @click=${() => this.selectAuthMethod(method.method)}
                        >
                          查看 Method Detail
                        </button>
                      </div>
                    </section>
                  `,
                )}
            </div>
          </section>
          <section class="field" data-testid="gateway-method-detail">
            ${selectedAuthMethod
              ? html`
                  ${(() => {
                    const routeMapping = this.gatewayFamilyRouteMapping(selectedAuthMethod.family);
                    return html`
                  <span>Method Detail</span>
                  <div class="readonly-value">${selectedAuthMethod.method}</div>
                  <div class="readonly-value">${selectedAuthMethod.description || "暂无 method 描述"}</div>
                  <div class="readonly-value">family=${selectedAuthMethod.family}</div>
                  <div class="readonly-value">
                    auth=${selectedAuthMethod.auth_required === false ? "public" : "protected"},
                    write=${selectedAuthMethod.control_plane_write ? "yes" : "no"},
                    events=${selectedAuthMethod.emits_events ? "yes" : "no"},
                    idempotent=${selectedAuthMethod.idempotent === false ? "no" : "yes"}
                  </div>
                  <div class="readonly-value">scopes=${this.gatewayMethodScopeSummary(selectedAuthMethod)}</div>
                  <div class="readonly-value">
                    transport=${String(selectedAuthMethod.metadata?.transport ?? "default")}
                  </div>
                  <div class="hint">${this.gatewayMethodOperatorNote(selectedAuthMethod)}</div>
                  <div class="actions inline">
                    ${routeMapping.route
                      ? html`
                          <button
                            type="button"
                            class="secondary"
                            data-testid="gateway-method-open-route"
                            @click=${() => this.emitRouteChange(routeMapping.route!)}
                          >
                            打开 ${routeMapping.label}
                          </button>
                        `
                      : html`<span class="hint">当前 method family 尚无 dedicated route</span>`}
                  </div>
                `;
                  })()}
                `
              : html`<span class="hint">选择一个 method 后在这里查看 auth/write detail。</span>`}
          </section>
        </div>
      </div>
    `;
  }

  private async loadSettings() {
    const [settingsResponse, healthResponse, bootstrapResponse] = await Promise.all([
      this.bridgeClient.settings.get(),
      this.bridgeClient.gateway.health.get(),
      this.bridgeClient.controlUi.bootstrap(),
    ]);
    this.snapshot = settingsResponse.data ?? this.snapshot;
    this.runtimePolicy = this.normalizeRuntimePolicy(this.snapshot.runtimePolicy);
    this.lastAppliedSettings = this.composeDraftSettings(this.snapshot, this.runtimePolicy);
    const providerLabel =
      this.normalizeProviderLabel(this.snapshot.providerLabel) ||
      this.normalizeProviderLabel(bootstrapResponse.data?.providerLabel) ||
      this.normalizeProviderLabel(this.environment.providerLabel);
    this.environment = {
      providerLabel,
      platformFamily: String((healthResponse.data?.runtime as Record<string, unknown> | undefined)?.platformFamily || "-"),
      platformOs: String((healthResponse.data?.runtime as Record<string, unknown> | undefined)?.platformOs || "-"),
      shellKind: String((healthResponse.data?.runtime as Record<string, unknown> | undefined)?.shellKind || "-"),
      workspaceTrust: String(this.snapshot.workspaceTrust || "unknown"),
      mcpServerCount: this.snapshot.mcpServers?.length ?? 0,
      appConnectorCount: this.snapshot.appConnectors?.length ?? 0,
    };
    this.syncGatewayProviderLabel(providerLabel);
    this.feedback = feedbackFromBridgeResponse(settingsResponse, {
      successMessage: "已加载 runtime 设置快照",
      errorMessage: "runtime 设置加载失败",
    });
  }

  private async loadGatewayConnection() {
    const [initializeResponse, capabilitiesResponse, pingResponse, accessPostureResponse] = await Promise.all([
      this.bridgeClient.gateway.connect.initialize(),
      this.bridgeClient.gateway.connect.capabilities(),
      this.bridgeClient.gateway.connect.ping(),
      this.bridgeClient.gateway.access.posture(),
    ]);
    const initializeMethods = initializeResponse.ok ? initializeResponse.data?.methods : undefined;
    const capabilityMethods = capabilitiesResponse.ok ? capabilitiesResponse.data?.methods : undefined;
    const methods = this.gatewayMethods(
      capabilityMethods,
      initializeMethods,
    );
    const errors = [
      initializeResponse.ok ? null : `connect.initialize: ${initializeResponse.error?.message ?? "failed"}`,
      capabilitiesResponse.ok ? null : `connect.capabilities: ${capabilitiesResponse.error?.message ?? "failed"}`,
      pingResponse.ok ? null : `connect.ping: ${pingResponse.error?.message ?? "failed"}`,
    ].filter((message): message is string => Boolean(message));
    const scopes = Array.from(
      new Set(
        methods.flatMap((item) => (Array.isArray(item.required_scopes) ? item.required_scopes : []).filter(Boolean)),
      ),
    ).sort();
    const legacyMethods = Array.isArray(capabilitiesResponse.ok ? capabilitiesResponse.data?.legacyMethods : undefined)
      ? capabilitiesResponse.data?.legacyMethods
      : Array.isArray(initializeResponse.ok ? initializeResponse.data?.legacyMethods : undefined)
        ? initializeResponse.data?.legacyMethods
        : [];
    const providerLabel =
      this.normalizeProviderLabel(capabilitiesResponse.ok ? capabilitiesResponse.data?.providerLabel : undefined) ||
      this.normalizeProviderLabel(this.environment.providerLabel) ||
      this.normalizeProviderLabel(this.snapshot.providerLabel) ||
      "-";
    const methodSource = Array.isArray(capabilityMethods) && capabilityMethods.length
      ? "connect.capabilities"
      : Array.isArray(initializeMethods) && initializeMethods.length
        ? "connect.initialize fallback"
        : "none";
    const handshakeStatus = errors.length === 0 && Boolean(pingResponse.data?.ok)
      ? "ready"
      : methods.length || initializeResponse.ok || capabilitiesResponse.ok || pingResponse.ok
        ? "partial"
        : "degraded";
    this.accessPosture =
      this.normalizeAccessPostureSummary(accessPostureResponse.ok ? accessPostureResponse.data : null) ??
      this.normalizeAccessPostureSummary(capabilitiesResponse.ok ? capabilitiesResponse.data?.accessPosture : null) ??
      this.normalizeAccessPostureSummary(initializeResponse.ok ? initializeResponse.data?.accessPosture : null) ??
      this.normalizeAccessPostureSummary(this.controlUiState?.accessPosture) ??
      this.accessPosture;
    this.gatewayConnect = {
      protocolVersion:
        String(pingResponse.data?.protocolVersion ?? initializeResponse.data?.protocolVersion ?? "-") || "-",
      pingOk: Boolean(pingResponse.ok && pingResponse.data?.ok),
      serverName: String(initializeResponse.ok ? initializeResponse.data?.serverInfo?.name ?? "-" : "-") || "-",
      serverVersion: String(initializeResponse.ok ? initializeResponse.data?.serverInfo?.version ?? "-" : "-") || "-",
      providerLabel,
      handshakeStatus,
      methodSource,
      methodCount: methods.length,
      legacyMethodCount: legacyMethods.length,
      writeMethodCount: methods.filter((item) => item.control_plane_write).length,
      publicMethodCount: methods.filter((item) => item.auth_required === false).length,
      eventMethodCount: methods.filter((item) => item.emits_events).length,
      scopes,
      methods,
      legacyMethods,
      errors,
    };
    const selectedStillExists = methods.some((item) => item.method === this.selectedAuthMethod);
    if (!selectedStillExists) {
      this.selectedAuthMethod = methods[0]?.method ?? "";
    }
    const scopeEntries = this.gatewayScopeEntries(methods);
    const selectedScopeStillExists = scopeEntries.some((item) => item.scope === this.selectedAuthScope);
    if (!selectedScopeStillExists) {
      this.selectedAuthScope = scopeEntries[0]?.scope ?? "";
    }
  }

  private async loadAuthConnectors() {
    const response = await this.bridgeClient.connector.list();
    this.authConnectors = response.ok && Array.isArray(response.data?.connectors) ? response.data.connectors : [];
    const selectedStillExists = this.authConnectors.some((item) => item.connector_key === this.selectedAuthConnectorKey);
    if (!selectedStillExists) {
      this.selectedAuthConnectorKey = this.authConnectors[0]?.connector_key ?? "";
    }
  }

  private async loadDiagnostics(source = this.logTail.source) {
    const requestedSource = String(source || "").trim();
    if (this.diagnosticsLoading) {
      this.pendingDiagnosticsSource = requestedSource;
      return;
    }
    this.diagnosticsLoading = true;
    this.pendingDiagnosticsSource = null;
    this.clearDiagnosticsRefreshTimer();
    this.diagnosticsStatus = this.controlUiState ? "正在刷新诊断..." : "正在加载诊断...";

    const [stateResponse, probesResponse, logsResponse] = await Promise.all([
      this.bridgeClient.controlUi.state({ limit: 8 }),
      this.bridgeClient.gateway.health.probes(),
      this.bridgeClient.gateway.logs.tail(requestedSource ? { source: requestedSource, lines: 12 } : { lines: 12 }),
    ]);

    if (stateResponse.ok && stateResponse.data) {
      this.controlUiState = stateResponse.data;
      if (!this.accessPosture && stateResponse.data.accessPosture) {
        this.accessPosture = this.normalizeAccessPostureSummary(stateResponse.data.accessPosture);
      }
    }
    if (probesResponse.ok && probesResponse.data) {
      this.healthProbes = probesResponse.data;
    }
    if (logsResponse.ok && logsResponse.data) {
      this.logTail = {
        ...EMPTY_LOG_TAIL,
        ...logsResponse.data,
      };
    }

    const errors = [stateResponse, probesResponse, logsResponse]
      .map((response) => response.error?.message)
      .filter((message): message is string => Boolean(message));
    this.diagnosticsStatus = errors.length
      ? `部分诊断加载失败：${errors.join(" | ")}`
      : `gateway probes、control-ui diagnostics、logs tail 已刷新 (${this.gatewayProbeHealthSummary()})`;
    this.lastDiagnosticsRefreshLabel = `最近刷新 ${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`;
    this.diagnosticsLoading = false;
    const pendingSource = this.pendingDiagnosticsSource;
    this.pendingDiagnosticsSource = null;
    if (pendingSource && pendingSource !== String(this.logTail.source || "").trim()) {
      void this.loadDiagnostics(pendingSource);
      return;
    }
    this.scheduleDiagnosticsRefresh();
  }

  private readonly handleModelInput = (event: Event) => {
    this.clearConfigContractSummaryOverride();
    this.snapshot = {
      ...this.snapshot,
      model: (event.target as HTMLInputElement).value,
    };
  };

  private readonly handleWorkspaceInput = (event: Event) => {
    this.clearConfigContractSummaryOverride();
    this.snapshot = {
      ...this.snapshot,
      workspaceRoot: (event.target as HTMLInputElement).value,
    };
  };

  private readonly handleBrowserHeadlessChange = (event: Event) => {
    this.clearConfigContractSummaryOverride();
    this.snapshot = {
      ...this.snapshot,
      browserHeadless: (event.target as HTMLInputElement).checked,
    };
  };

  private readonly handlePluginAutoLoadChange = (event: Event) => {
    this.clearConfigContractSummaryOverride();
    this.snapshot = {
      ...this.snapshot,
      pluginAutoLoad: (event.target as HTMLInputElement).checked,
    };
  };

  private readonly handleRefreshDiagnostics = async () => {
    await Promise.all([
      this.loadGatewayConnection(),
      this.loadAuthConnectors(),
      this.loadDiagnostics(this.logTail.source),
    ]);
  };

  private readonly handleToggleAutoRefresh = async () => {
    this.autoRefreshEnabled = !this.autoRefreshEnabled;
    if (!this.autoRefreshEnabled) {
      this.clearDiagnosticsRefreshTimer();
      return;
    }
    await this.loadDiagnostics(this.logTail.source);
  };

  private readonly handleSave = async () => {
    try {
      const draft = this.composeDraftSettings();
      const validationResponse = await this.bridgeClient.config.validate(draft);
      if (!validationResponse.ok || !validationResponse.data) {
        this.feedback = errorFeedback(
          validationResponse.error?.message || "config.validate 失败，当前无法执行 apply。",
        );
        return;
      }
      const remoteValidation = validationResponse.data;
      this.lastRemoteValidation = remoteValidation;
      this.lastRestartReport = remoteValidation.restart;
      this.configContractSummaryOverride = this.remoteValidationToDraftValidation(remoteValidation);
      if (remoteValidation.applyableFields.length === 0) {
        this.feedback = errorFeedback(
          remoteValidation.warnings[0] || "当前设置草稿包含无法应用的字段，请先处理阻塞项。",
        );
        return;
      }
      const response = await this.bridgeClient.config.apply(draft);
      const applyResult = response.data;
      if (!response.ok || !applyResult) {
        this.feedback = errorFeedback(response.error?.message || "config.apply 失败");
        return;
      }
      const remoteApplyValidation = this.remoteApplyToDraftValidation(applyResult);
      this.configContractSummaryOverride = remoteApplyValidation;
      const appliedSnapshot = applyResult.settings ?? this.snapshot;
      const appliedRuntimePolicy = this.normalizeRuntimePolicy(appliedSnapshot.runtimePolicy);
      this.lastAppliedSettings = this.composeDraftSettings(appliedSnapshot, appliedRuntimePolicy);
      this.snapshot = this.mergeRetainedDraftSnapshot(
        appliedSnapshot,
        draft,
        remoteApplyValidation,
      );
      this.runtimePolicy = this.mergeRetainedDraftRuntimePolicy(
        appliedRuntimePolicy,
        draft,
        remoteApplyValidation,
      );
      this.environment = {
        ...this.environment,
        providerLabel: appliedSnapshot.providerLabel || this.environment.providerLabel,
        workspaceTrust: String(appliedSnapshot.workspaceTrust || this.environment.workspaceTrust),
        mcpServerCount: appliedSnapshot.mcpServers?.length ?? this.environment.mcpServerCount,
        appConnectorCount: appliedSnapshot.appConnectors?.length ?? this.environment.appConnectorCount,
      };
      this.syncGatewayProviderLabel(appliedSnapshot.providerLabel);
      if (applyResult.status === "partial" && applyResult.blockedFields.length) {
        this.feedback = warningFeedback(
          `已应用支持字段；以下字段仍未应用并保留在本地草稿：${applyResult.blockedFields.join("，")}。${
            applyResult.restart.required
              ? `${applyResult.restart.reasons.join("，")} 建议在相关运行面重启后确认。`
              : ""
          }`,
        );
        return;
      }
      if (applyResult.restart.required) {
        this.feedback = warningFeedback(
          `runtime 设置已保存；${applyResult.restart.reasons.join("，")} 建议在相关运行面重启后确认。`,
        );
        return;
      }
      this.feedback = feedbackFromBridgeResponse(response, {
        successMessage: "runtime 设置已保存",
        errorMessage: "runtime 设置保存失败",
      });
    } catch (error) {
      this.feedback = errorFeedback(error instanceof Error ? error.message : String(error));
    }
  };

  private readonly handleValidateDraft = async () => {
    try {
      const draft = this.composeDraftSettings();
      const response = await this.bridgeClient.config.validate(draft);
      if (!response.ok || !response.data) {
        this.feedback = errorFeedback(response.error?.message || "config.validate 失败");
        return;
      }
      this.lastRemoteValidation = response.data;
      this.lastRestartReport = response.data.restart;
      this.configContractSummaryOverride = this.remoteValidationToDraftValidation(response.data);
      this.feedback = neutralFeedback(
        `config.validate 已返回：changed=${response.data.changedFields.length} · applyable=${response.data.applyableFields.length} · blocked=${response.data.blockedFields.length}`,
      );
    } catch (error) {
      this.feedback = errorFeedback(error instanceof Error ? error.message : String(error));
    }
  };

  private readonly handleRestartReport = async () => {
    try {
      const draft = this.composeDraftSettings();
      const response = await this.bridgeClient.config.restartReport(draft);
      if (!response.ok || !response.data) {
        this.feedback = errorFeedback(response.error?.message || "config.restart.report 失败");
        return;
      }
      this.lastRestartReport = response.data;
      this.feedback = response.data.required
        ? warningFeedback(
            `config.restart.report: manual / ${response.data.reasons.join("，") || "restart required"}`,
          )
        : neutralFeedback("config.restart.report: 当前草稿无额外 restart requirement");
    } catch (error) {
      this.feedback = errorFeedback(error instanceof Error ? error.message : String(error));
    }
  };

  private readonly handleRuntimePolicySelect =
    (key: keyof RuntimePolicyForm) => (event: Event) => {
      this.clearConfigContractSummaryOverride();
      const next = (event.target as HTMLSelectElement).value;
      this.runtimePolicy = {
        ...this.runtimePolicy,
        [key]: next,
      };
    };

  private readonly handleLogSourceChange = async (event: Event) => {
    const next = (event.target as HTMLSelectElement).value;
    this.logTail = {
      ...this.logTail,
      source: next,
    };
    await this.loadDiagnostics(next);
  };

  private readonly handleLogSourceQuickSelect = async (source: string) => {
    this.logTail = {
      ...this.logTail,
      source,
    };
    await this.loadDiagnostics(source);
  };

  private gatewayProbeSummary(): string {
    const probes = (this.healthProbes.probes as Record<string, Record<string, unknown>> | undefined) ?? {};
    const parts = Object.entries(probes).map(([name, probe]) => `${name}=${probe.ok === false ? "down" : "ok"}`);
    return parts.length ? parts.join(", ") : "暂无 probe 数据";
  }

  private gatewayProbeHealthSummary(): string {
    const entries = this.gatewayProbeEntries();
    if (!entries.length) {
      return "暂无 probe 数据";
    }
    const downCount = entries.filter((probe) => probe.ok === false).length;
    return downCount > 0 ? `${downCount}/${entries.length} probes degraded` : `${entries.length}/${entries.length} probes ok`;
  }

  private gatewayProbeEntries(): Array<Record<string, unknown>> {
    const probes = (this.healthProbes.probes as Record<string, Record<string, unknown>> | undefined) ?? {};
    return Object.values(probes);
  }

  private degradedProbeCount(): number {
    return this.gatewayProbeEntries().filter((probe) => probe.ok === false).length;
  }

  private probeInventoryEntries(): ProbeInventoryEntry[] {
    const probes = (this.healthProbes.probes as Record<string, Record<string, unknown>> | undefined) ?? {};
    return Object.entries(probes)
      .map(([key, probe]) => {
        const details = Object.entries(probe)
          .filter(([field]) => field !== "ok")
          .map(([field, value]) => `${field}=${String(value)}`);
        const routeCue = this.probeRouteCue(key, probe);
        return {
          key,
          ok: probe.ok !== false,
          detail: details.length ? details.join(", ") : "no extra metrics",
          note: routeCue.note,
          route: routeCue.route,
          actionLabel: routeCue.actionLabel,
        };
      })
      .sort((left, right) => Number(left.ok) - Number(right.ok) || left.key.localeCompare(right.key));
  }

  private probeRouteCue(key: string, probe: Record<string, unknown>): { route: GuiRouteId | null; actionLabel?: string; note: string } {
    const normalizedKey = key.toLowerCase();
    if (normalizedKey.includes("browser") || "tabCount" in probe || "running" in probe) {
      return {
        route: "browser",
        actionLabel: "打开浏览器控制",
        note: probe.ok === false ? "该 probe degraded，优先回浏览器控制面确认 running/tab/ref 状态。" : "该 probe 直连浏览器运行面，适合继续看 browser control。",
      };
    }
    if ("workflowRuns" in probe || "events" in probe) {
      return {
        route: "sessions",
        actionLabel: "打开 Sessions / Runs",
        note: probe.ok === false ? "该 probe degraded，优先检查 workflow/trace 可见性。" : "该 probe 对应 workflow/trace 观察面，可继续到 Sessions / Runs。",
      };
    }
    if ("approvalTickets" in probe) {
      return {
        route: "approvals",
        actionLabel: "打开审批与审计",
        note: probe.ok === false ? "该 probe degraded，优先确认 approval chain 与 pending 状态。" : "该 probe 对应 approvals / audit，可继续检查审批链路。",
      };
    }
    return {
      route: null,
      note: probe.ok === false ? "该 probe degraded，但当前没有更明确的 operator surface。" : "当前 probe 只保留指标可见性。",
    };
  }

  private snapshotInventoryEntries(): SnapshotInventoryEntry[] {
    if (!this.controlUiState) {
      return [];
    }
    return [
      {
        key: "events",
        count: this.controlUiState.events.length,
        detail: "最近事件流与 operator activity snapshot。",
        route: "workbench",
        actionLabel: "打开工作台",
        actionKind: "route",
      },
      {
        key: "workflowRuns",
        count: this.controlUiState.workflowRuns.length,
        detail: "workflow runs 与 trace timeline 观察面。",
        route: "sessions",
        actionLabel: "打开 Sessions / Runs",
        actionKind: "control",
      },
      {
        key: "approvalTickets",
        count: this.controlUiState.approvalTickets.length,
        detail: "pending approvals 与 approval chain 观察面。",
        route: "approvals",
        actionLabel: "打开审批与审计",
        actionKind: "control",
      },
      {
        key: "connectors",
        count: this.controlUiState.connectors.length,
        detail: "connector / external integration 可见性面。",
        route: "plugins",
        actionLabel: "打开插件与连接器",
        actionKind: "plugins",
      },
    ];
  }

  private snapshotInventoryWorkflowContext(): SettingsControlContextDetail | null {
    const candidates = (this.controlUiState?.workflowRuns ?? []) as Array<Record<string, unknown>>;
    const selected =
      candidates.find((item) => String(item.status ?? item.workflow_status ?? "").trim().toLowerCase() === "paused") ??
      candidates[0];
    const traceId = String(selected?.trace_id ?? selected?.traceId ?? "").trim();
    if (!traceId) {
      return null;
    }
    const workflowRunId = String(selected?.workflow_run_id ?? selected?.run_id ?? "").trim();
    return {
      route: "sessions",
      traceId,
      workflowRunId: workflowRunId || undefined,
      timelineScope: "workflowRuns",
      source: "settings-diagnostics",
    };
  }

  private snapshotInventoryApprovalContext(): SettingsControlContextDetail | null {
    const candidates = (this.controlUiState?.approvalTickets ?? []) as Array<Record<string, unknown>>;
    const selected =
      candidates.find((item) => String(item.status ?? "").trim().toLowerCase() === "pending") ??
      candidates[0];
    const traceId = String(selected?.trace_id ?? selected?.traceId ?? "").trim();
    if (!traceId) {
      return null;
    }
    const approvalId = String(selected?.approval_id ?? "").trim();
    return {
      route: "approvals",
      traceId,
      approvalId: approvalId || undefined,
      source: "settings-diagnostics",
    };
  }

  private snapshotInventoryPluginsContext(): SettingsPluginsRouteContextDetail | null {
    const candidates = (this.controlUiState?.connectors ?? []) as Array<Record<string, unknown>>;
    const selected =
      candidates.find((item) => String(item.health ?? "").trim().toLowerCase() !== "ready") ??
      candidates[0];
    if (!selected) {
      return null;
    }
    const connectorKey = String(selected.connector_key ?? "").trim();
    const sourceKind = String(selected.source_kind ?? "").trim().toLowerCase();
    return {
      route: "plugins",
      connectorKey: connectorKey || undefined,
      connectorFilter: sourceKind === "gateway" ? "gateway" : "actionable",
      source: "settings-diagnostics",
    };
  }

  private traceHotspots(limit = 4): TraceHotspotEntry[] {
    if (!this.controlUiState) {
      return [];
    }
    const hotspots = new Map<string, TraceHotspotEntry>();
    const ensureEntry = (traceId: string): TraceHotspotEntry => {
      const existing = hotspots.get(traceId);
      if (existing) {
        return existing;
      }
      const created: TraceHotspotEntry = {
        traceId,
        approvalCount: 0,
        pendingApprovalCount: 0,
        actionCount: 0,
        auditCount: 0,
        eventCount: 0,
        priority: 0,
      };
      hotspots.set(traceId, created);
      return created;
    };
    const resolveTraceId = (item: Record<string, unknown>): string =>
      String(item.trace_id ?? item.traceId ?? "").trim();

    for (const item of this.controlUiState.workflowRuns ?? []) {
      const record = item as Record<string, unknown>;
      const traceId = resolveTraceId(record);
      if (!traceId) {
        continue;
      }
      const entry = ensureEntry(traceId);
      const workflowStatus = String(record.status ?? record.workflow_status ?? "").trim().toLowerCase();
      const currentRunId = String(record.workflow_run_id ?? record.run_id ?? "").trim();
      const currentPriority = workflowStatus === "paused" ? 2 : workflowStatus === "running" ? 1 : 0;
      const existingPriority =
        entry.workflowStatus === "paused" ? 2 : entry.workflowStatus === "running" ? 1 : entry.workflowRunId ? 0 : -1;
      if (currentPriority >= existingPriority) {
        entry.workflowRunId = currentRunId || entry.workflowRunId;
        entry.workflowName = String(record.workflow_name ?? record.name ?? currentRunId ?? "").trim() || entry.workflowName;
        entry.pluginName = String(record.plugin_name ?? "").trim() || entry.pluginName;
        entry.workflowStatus = workflowStatus || entry.workflowStatus;
      }
      entry.priority += currentPriority >= 2 ? 8 : currentPriority === 1 ? 4 : 2;
    }

    for (const item of this.controlUiState.actionRequests ?? []) {
      const record = item as Record<string, unknown>;
      const traceId = resolveTraceId(record);
      if (!traceId) {
        continue;
      }
      ensureEntry(traceId).actionCount += 1;
    }

    for (const item of this.controlUiState.approvalTickets ?? []) {
      const record = item as Record<string, unknown>;
      const traceId = resolveTraceId(record);
      if (!traceId) {
        continue;
      }
      const entry = ensureEntry(traceId);
      const approvalId = String(record.approval_id ?? "").trim();
      const status = String(record.status ?? "").trim().toLowerCase();
      entry.approvalCount += 1;
      if (status === "pending") {
        entry.pendingApprovalCount += 1;
      }
      if (!entry.approvalId || status === "pending") {
        entry.approvalId = approvalId || entry.approvalId;
      }
      entry.priority += status === "pending" ? 10 : 3;
    }

    for (const item of this.controlUiState.auditRecords ?? []) {
      const record = item as Record<string, unknown>;
      const traceId = resolveTraceId(record);
      if (!traceId) {
        continue;
      }
      const entry = ensureEntry(traceId);
      entry.auditCount += 1;
      entry.priority += 1;
    }

    for (const item of this.controlUiState.events ?? []) {
      const record = item as Record<string, unknown>;
      const traceId = resolveTraceId(record);
      if (!traceId) {
        continue;
      }
      const entry = ensureEntry(traceId);
      entry.eventCount += 1;
      entry.priority += 1;
    }

    return [...hotspots.values()]
      .sort((left, right) => right.priority - left.priority || left.traceId.localeCompare(right.traceId))
      .slice(0, limit);
  }

  private controlUiDiagnosticsSummary(): string {
    const workflowDiagnostics = this.workflowDiagnostics();
    const approvalDiagnostics = this.approvalDiagnostics();
    const pausedCount = workflowDiagnostics.filter((item) =>
      String(item.workflow_status ?? item.status ?? "").trim().toLowerCase() === "paused"
    ).length;
    const pendingApprovals = approvalDiagnostics.filter((item) =>
      String(item.status ?? "").trim().toLowerCase() === "pending"
    ).length;
    return `workflow=${workflowDiagnostics.length}, approval=${approvalDiagnostics.length}, paused=${pausedCount}, pending=${pendingApprovals}`;
  }

  private controlUiSnapshotSummary(): string {
    if (!this.controlUiState) {
      return "暂无 control-ui 快照";
    }
    return `events=${this.controlUiState.events.length}, approvals=${this.controlUiState.approvalTickets.length}, connectors=${this.controlUiState.connectors.length}`;
  }

  private logTailText(): string {
    if (this.logTail.text.trim()) {
      return this.logTail.text;
    }
    return "暂无日志输出";
  }

  private gatewayScopeSummary(): string {
    return this.gatewayConnect.scopes.length
      ? this.gatewayConnect.scopes.join(", ")
      : "当前 connect surface 未返回 scope 元数据";
  }

  private gatewayScopeKeys(method: GatewayMethodMetadata): string[] {
    const scopes = Array.isArray(method.required_scopes)
      ? method.required_scopes.map((item) => String(item).trim()).filter(Boolean)
      : [];
    if (scopes.length) {
      return scopes;
    }
    if (method.auth_required === false) {
      return ["public"];
    }
    return ["no extra scopes"];
  }

  private gatewayScopeEntries(methods = this.gatewayConnect.methods): GatewayScopeEntry[] {
    if (!methods.length) {
      return [];
    }
    const scopes = new Map<string, GatewayScopeEntry>();
    for (const method of methods) {
      for (const scope of this.gatewayScopeKeys(method)) {
        const entry = scopes.get(scope) ?? {
          scope,
          methods: [],
          writeCount: 0,
          publicCount: 0,
          eventCount: 0,
        };
        entry.methods.push(method);
        if (method.control_plane_write) {
          entry.writeCount += 1;
        }
        if (method.auth_required === false) {
          entry.publicCount += 1;
        }
        if (method.emits_events) {
          entry.eventCount += 1;
        }
        scopes.set(scope, entry);
      }
    }
    return Array.from(scopes.values()).sort((left, right) => {
      if (left.scope === "public") {
        return -1;
      }
      if (right.scope === "public") {
        return 1;
      }
      return left.scope.localeCompare(right.scope);
    });
  }

  private selectedGatewayScope(entries: GatewayScopeEntry[]): GatewayScopeEntry | null {
    if (!entries.length) {
      return null;
    }
    return entries.find((item) => item.scope === this.selectedAuthScope) ?? entries[0];
  }

  private normalizeProviderLabel(label: string | null | undefined): string {
    const value = String(label ?? "").trim();
    if (!value || value === "-") {
      return "";
    }
    return value;
  }

  private gatewayProviderLabelSummary(): string {
    return (
      this.normalizeProviderLabel(this.gatewayConnect.providerLabel) ||
      this.normalizeProviderLabel(this.environment.providerLabel) ||
      this.normalizeProviderLabel(this.snapshot.providerLabel) ||
      "-"
    );
  }

  private syncGatewayProviderLabel(providerLabel: string | null | undefined) {
    const normalized = this.normalizeProviderLabel(providerLabel);
    if (!normalized || this.normalizeProviderLabel(this.gatewayConnect.providerLabel)) {
      return;
    }
    this.gatewayConnect = {
      ...this.gatewayConnect,
      providerLabel: normalized,
    };
  }

  private gatewayFamilySummary(): string {
    if (!this.gatewayConnect.methods.length) {
      return "暂无 method family 数据";
    }
    const counts = new Map<string, number>();
    for (const method of this.gatewayConnect.methods) {
      counts.set(method.family, (counts.get(method.family) ?? 0) + 1);
    }
    return Array.from(counts.entries())
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([family, count]) => `${family}=${count}`)
      .join(", ");
  }

  private gatewayScopeInventory(): string {
    if (!this.gatewayConnect.methods.length) {
      return "暂无 scope inventory";
    }
    const counts = new Map<string, number>();
    for (const method of this.gatewayConnect.methods) {
      const scopes = this.gatewayScopeKeys(method);
      for (const scope of scopes) {
        counts.set(scope, (counts.get(scope) ?? 0) + 1);
      }
    }
    return Array.from(counts.entries())
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([scope, count]) => `${scope}=${count}`)
      .join(", ");
  }

  private transportModeSummary(): string {
    const config = resolveBridgeTransportConfig();
    if (config.mode === "http") {
      return `http / ${config.eventTransport ?? "polling"}`;
    }
    return "mock / local";
  }

  private transportContractEntries(): Array<{ label: string; value: string }> {
    const config = resolveBridgeTransportConfig();
    if (config.mode !== "http") {
      return [
        { label: "Mode", value: "mock / local only" },
        { label: "Requests", value: "not applicable" },
        { label: "Events", value: "local mock stream" },
        { label: "Control UI", value: "not applicable" },
        { label: "Browser Proxy", value: "not applicable" },
      ];
    }
    return [
      { label: "Base URL", value: config.httpBaseUrl ?? "-" },
      { label: "Requests", value: config.requestPath ?? "/requests" },
      { label: "Events", value: `${config.eventsPath ?? "/events"} (${config.eventTransport ?? "polling"})` },
      { label: "Control UI Config", value: config.controlUiConfigPath ?? "/__agenthub/control-ui-config.json" },
      { label: "Control UI State", value: config.controlUiStatePath ?? "/control-ui/state" },
      { label: "Gateway Events", value: config.gatewayEventsPath ?? "/gateway-events" },
      { label: "Browser Proxy", value: config.browserProxyPath ?? "/browser-proxy" },
      { label: "WebSocket", value: config.websocketUrl ?? "disabled" },
      { label: "Polling", value: `${config.pollingIntervalMs ?? 800}ms` },
      {
        label: "Client",
        value: config.client ? `${config.client.name}/${config.client.version}` : "not declared",
      },
    ];
  }

  private gatewayConnectStatusSummary(): string {
    if (this.gatewayConnect.handshakeStatus === "ready") {
      return "connect.initialize / connect.capabilities / connect.ping 已就绪。";
    }
    if (this.gatewayConnect.handshakeStatus === "partial") {
      return "connect surface 部分降级；当前 UI 会保留已有 metadata 和 transport contract。";
    }
    return "connect surface 当前不可用；UI 仅保留 transport contract 与本地 runtime 摘要。";
  }

  private gatewayConnectRecoveryHint(): string {
    if (this.gatewayConnect.handshakeStatus === "ready") {
      return "当前 connect surface 已 ready；若后续出现抖动，可通过“刷新诊断 / 日志”重新握手。";
    }
    if (this.gatewayConnect.methodSource === "connect.initialize fallback") {
      return "connect.capabilities 当前不可用；methods/legacyMethods 已回退到 connect.initialize，手动刷新可重试 capabilities。";
    }
    if (!this.gatewayConnect.pingOk && this.gatewayConnect.methodCount > 0) {
      return "connect.ping 当前降级；auth/method metadata 仍可用，手动刷新可重试 ping。";
    }
    if (this.gatewayConnect.errors.some((message) => message.startsWith("connect.initialize:")) && this.gatewayConnect.methodCount > 0) {
      return "connect.initialize 当前不可用；server identity 缺失，但 method metadata 仍保留，可手动刷新重试 initialize。";
    }
    return "connect surface 当前不可用；请先检查 bridge/gateway 可达性，再通过“刷新诊断 / 日志”触发恢复。";
  }

  private gatewayFamilyRouteMappings(): AuthRouteMapping[] {
    const families = new Set(this.gatewayConnect.methods.map((item) => item.family));
    families.add("settings");
    return Array.from(families)
      .sort((left, right) => left.localeCompare(right))
      .map((family) => this.gatewayFamilyRouteMapping(family));
  }

  private gatewayFamilyRouteMapping(family: string): AuthRouteMapping {
    if (family === "approvals") {
      return {
        family,
        route: "approvals",
        label: "审批与审计",
        note: "审批票、审计因果链和 workflow gate 由 approvals 面承接。",
      };
    }
    if (family === "browser") {
      return {
        family,
        route: "browser",
        label: "浏览器控制",
        note: "browser.write 与 proxy transport 相关方法由浏览器控制面承接。",
      };
    }
    if (family === "plugins" || family === "github") {
      return {
        family,
        route: "plugins",
        label: "插件与连接器",
        note: "插件、连接器与外部集成 family 目前统一由 plugins 面承接。",
      };
    }
    if (family === "workflows" || family === "gateway_state") {
      return {
        family,
        route: "sessions",
        label: "Sessions / Runs",
        note: "workflow run、timeline 与 gateway state 相关观察面由 sessions 承接。",
      };
    }
    if (family === "access" || family === "connect" || family === "health" || family === "logs" || family === "settings") {
      return {
        family,
        route: "settings",
        label: "设置",
        note: "connect / health / logs / runtime contract 目前仍主要由 settings operator 面承接。",
      };
    }
    return {
      family,
      route: null,
      label: "metadata only",
      note: "该 family 当前只有 metadata visibility，尚无 dedicated operator route。",
    };
  }

  private transportOriginSummary(): string {
    const config = resolveBridgeTransportConfig();
    if (config.mode === "http") {
      return config.httpBaseUrl || "http transport";
    }
    return "local mock bridge";
  }

  private authContextSummary(): string {
    const config = resolveBridgeTransportConfig();
    if (config.mode === "http") {
      return "HTTP bridge transport（认证状态仅按部署方式推断）";
    }
    return "mock-local transport（不代表真实认证结果）";
  }

  private originDegradeHint(): string {
    const config = resolveBridgeTransportConfig();
    if (config.mode === "mock") {
      return "当前处于 mock transport，auth / origin / scope 只用于本地演示，不代表真实 gateway 约束。";
    }
    if (config.eventTransport === "polling") {
      return "当前事件通道走 polling；这是 transport 降级模式，适合 bridge 过渡期但不等同于完整 websocket push。";
    }
    return "当前已接入真实 HTTP/WebSocket transport，可继续在 settings 内深化 auth/origin/write-budget，并在 contract 稳定后拆分独立 surface。";
  }

  private writeBudgetKeySummary(): string {
    return "device_id|clientIp，缺失时回退 connId";
  }

  private normalizeAccessPostureSummary(posture: AccessPostureSummary | null | undefined): AccessPostureSummary | null {
    if (!posture || typeof posture !== "object") {
      return null;
    }
    const candidate = posture as Partial<AccessPostureSummary> & Record<string, unknown>;
    if (!candidate.access || !candidate.auth || !candidate.pairing || !candidate.summary) {
      return null;
    }
    const pairingRecord = candidate.pairing as AccessPostureSummary["pairing"] & Record<string, unknown>;
    const pendingRefs = this.normalizePairingPendingRefs(pairingRecord.pendingRefs ?? pairingRecord.pending_refs);
    return {
      ...(candidate as AccessPostureSummary),
      pairing: {
        ...pairingRecord,
        pendingRefs,
      },
    };
  }

  private accessPostureVisibilitySummary(): string {
    if (!this.accessPosture) {
      return "未知";
    }
    return [
      this.accessPosture.access.posture,
      `local=${this.accessPosture.access.local.enabled ? "on" : "off"}`,
      `remote=${this.accessPosture.access.remote.enabled ? "on" : "off"}`,
    ].join(" · ");
  }

  private accessPostureAuthSummary(): string {
    if (!this.accessPosture) {
      return "当前未返回 access/auth posture";
    }
    return [
      this.accessPosture.auth.mode,
      this.accessPosture.auth.origin,
      this.accessPosture.auth.authenticated ? "authenticated" : "anonymous",
      this.accessPosture.auth.actorId || "actor=-",
    ].join(" · ");
  }

  private accessPostureScopeSummary(): string {
    if (!this.accessPosture) {
      return "当前未返回 role/scope inventory";
    }
    const roles = this.accessPosture.auth.roles.length ? this.accessPosture.auth.roles.join(", ") : "none";
    const scopes = this.accessPosture.auth.scopes.length ? this.accessPosture.auth.scopes.join(", ") : "none";
    return `roles=${roles} · scopes=${scopes}`;
  }

  private accessPosturePairingSummary(): string {
    if (!this.accessPosture) {
      return "当前未返回 pairing posture";
    }
    const pendingRefs = this.accessPosturePendingRefs();
    return [
      `pendingPairing=${this.accessPosture.pairing.pendingRequestCount}`,
      `pendingApprovals=${this.accessPosture.pairing.pendingApprovalCount}`,
      `pendingRefs=${pendingRefs.length}`,
      this.accessPosture.pairing.hasNativeContract ? "native-contract" : "heuristic-only",
    ].join(" · ");
  }

  private accessPostureHint(): string {
    if (!this.accessPosture) {
      return "access.posture.get 当前不可用；UI 会继续回退到 connect / diagnostics 摘要。";
    }
    if (this.accessPosture.pairing.pendingRequestCount > 0) {
      return `当前有 ${this.accessPosture.pairing.pendingRequestCount} 个 pairing pending，优先联动 approvals / sessions / trace 查看来源与风险。`;
    }
    const pendingRefs = this.accessPosturePendingRefs();
    if (pendingRefs.length > 0) {
      return `当前返回 ${pendingRefs.length} 条 pairing refs，可直接跳到 approvals / sessions 查看 trace 证据链。`;
    }
    if (this.accessPosture.access.remote.enabled) {
      return "当前 remote access 已暴露；应结合 origin、scope 与 write-budget 一起判断后续操作风险。";
    }
    if (this.accessPosture.pairing.hasNativeContract === false) {
      return "当前 pairing 仍通过 approvals pending 启发式汇总，适合作为只读 operator posture，不代表已具备配对写入口。";
    }
    return "当前 access posture 已稳定返回，可继续在 settings/auth 面做 origin、scope 与 pending pairing 观察。";
  }

  private accessPosturePendingRefs(): PairingPendingRef[] {
    if (!this.accessPosture) {
      return [];
    }
    return this.normalizePairingPendingRefs(this.accessPosture.pairing.pendingRefs);
  }

  private normalizePairingPendingRefs(value: unknown): PairingPendingRef[] {
    if (!Array.isArray(value)) {
      return [];
    }
    const normalized: PairingPendingRef[] = [];
    for (const entry of value) {
      if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
        continue;
      }
      const record = entry as Record<string, unknown>;
      const pick = (...values: unknown[]) => {
        for (const candidate of values) {
          if (typeof candidate === "string" && candidate.trim()) {
            return candidate.trim();
          }
        }
        return "";
      };
      const approvalId = pick(record.approvalId, record.approval_id);
      const traceId = pick(record.traceId, record.trace_id);
      const title = pick(record.title, record.summary, record.reason);
      const actionType = pick(record.actionType, record.action_type);
      if (!approvalId && !traceId) {
        continue;
      }
      if (!title || !actionType) {
        continue;
      }
      const normalizedRef: PairingPendingRef = {
        approvalId,
        traceId,
        title,
        actionType,
      };
      const requestedAt = pick(record.requestedAt, record.requested_at, record.createdAt, record.created_at);
      if (requestedAt) {
        normalizedRef.requestedAt = requestedAt;
      }
      normalized.push(normalizedRef);
    }
    return normalized;
  }

  private pairingPendingRefKey(ref: PairingPendingRef): string {
    return ref.approvalId || ref.traceId || ref.actionType || ref.title || "pairing-ref";
  }

  private openAccessPosturePendingApproval(ref: PairingPendingRef) {
    const traceId = String(ref.traceId ?? "").trim();
    if (traceId) {
      this.navigateToControlContext({
        route: "approvals",
        traceId,
        approvalId: String(ref.approvalId ?? "").trim() || undefined,
        source: "settings-access-posture",
      });
      return;
    }
    this.emitRouteChange("approvals");
  }

  private openAccessPosturePendingTrace(ref: PairingPendingRef) {
    const traceId = String(ref.traceId ?? "").trim();
    if (traceId) {
      this.navigateToControlContext({
        route: "sessions",
        traceId,
        timelineScope: "approvalTickets",
        source: "settings-access-posture",
      });
      return;
    }
    this.emitRouteChange("sessions");
  }

  private renderAccessPosturePendingRefs() {
    const refs = this.accessPosturePendingRefs();
    if (!refs.length) {
      return html`<section class="diag-item"><div class="diag-meta">当前无 pending pairing refs。</div></section>`;
    }
    return refs.map((entry) => {
      const key = this.testIdPart(this.pairingPendingRefKey(entry));
      return html`
        <section class="diag-item" data-testid=${`gateway-access-posture-ref-${key}`}>
          <div class="diag-title">${entry.title}</div>
          <div class="diag-meta">
            action=${entry.actionType} · approval=${entry.approvalId || "-"} · trace=${entry.traceId || "-"}
          </div>
          <div class="diag-meta">${entry.requestedAt ? `requestedAt=${entry.requestedAt}` : "requestedAt=-"}</div>
          <div class="actions inline">
            <button
              type="button"
              class="secondary"
              data-testid=${`gateway-access-posture-ref-open-approvals-${key}`}
              @click=${() => this.openAccessPosturePendingApproval(entry)}
            >
              打开审批上下文
            </button>
            <button
              type="button"
              class="secondary"
              ?disabled=${!entry.traceId}
              data-testid=${`gateway-access-posture-ref-open-sessions-${key}`}
              @click=${() => this.openAccessPosturePendingTrace(entry)}
            >
              打开 Trace
            </button>
          </div>
        </section>
      `;
    });
  }

  private filteredGatewayMethods(): GatewayMethodMetadata[] {
    if (this.authMethodFilter === "protected") {
      return this.gatewayConnect.methods.filter((item) => item.auth_required !== false);
    }
    if (this.authMethodFilter === "write") {
      return this.gatewayConnect.methods.filter((item) => item.control_plane_write);
    }
    if (this.authMethodFilter === "events") {
      return this.gatewayConnect.methods.filter((item) => item.emits_events);
    }
    if (this.authMethodFilter === "public") {
      return this.gatewayConnect.methods.filter((item) => item.auth_required === false);
    }
    return this.gatewayConnect.methods;
  }

  private selectedGatewayMethod(methods: GatewayMethodMetadata[]): GatewayMethodMetadata | null {
    if (!methods.length) {
      return null;
    }
    return methods.find((item) => item.method === this.selectedAuthMethod) ?? methods[0];
  }

  private renderAuthFilterChip(filter: AuthMethodFilter, label: string) {
    return html`
      <button
        type="button"
        class="chip-button ${this.authMethodFilter === filter ? "active" : ""}"
        data-testid=${`gateway-method-filter-${filter}`}
        @click=${() => this.applyAuthMethodFilter(filter)}
      >
        ${label}
      </button>
    `;
  }

  private renderAuthConnectorFilterChip(filter: AuthConnectorFilter, label: string) {
    return html`
      <button
        type="button"
        class="chip-button ${this.authConnectorFilter === filter ? "active" : ""}"
        data-testid=${`gateway-auth-connector-filter-${filter}`}
        @click=${() => this.applyAuthConnectorFilter(filter)}
      >
        ${label}
      </button>
    `;
  }

  private applyAuthMethodFilter(filter: AuthMethodFilter) {
    this.authMethodFilter = filter;
    const nextSelected = this.filteredGatewayMethods()[0];
    this.selectedAuthMethod = nextSelected?.method ?? "";
  }

  private applyAuthConnectorFilter(filter: AuthConnectorFilter) {
    this.authConnectorFilter = filter;
    const nextSelected = this.filteredAuthConnectors()[0];
    this.selectedAuthConnectorKey = nextSelected?.connector_key ?? "";
  }

  private selectAuthMethod(method: string) {
    this.selectedAuthMethod = method;
  }

  private selectAuthScope(scope: string) {
    this.selectedAuthScope = scope;
  }

  private selectAuthConnector(connectorKey: string) {
    this.selectedAuthConnectorKey = connectorKey;
  }

  private inspectAuthMethod(method: string) {
    this.authMethodFilter = "all";
    this.selectedAuthMethod = method;
  }

  private filteredAuthConnectors(): ConnectorSummary[] {
    if (this.authConnectorFilter === "ingress") {
      return this.authConnectors.filter((item) => item.supports_webhook || item.supports_polling);
    }
    if (this.authConnectorFilter === "webhook") {
      return this.authConnectors.filter((item) => item.supports_webhook);
    }
    if (this.authConnectorFilter === "polling") {
      return this.authConnectors.filter((item) => item.supports_polling);
    }
    if (this.authConnectorFilter === "actions") {
      return this.authConnectors.filter((item) => item.supports_actions);
    }
    if (this.authConnectorFilter === "approval") {
      return this.authConnectors.filter((item) => item.approval_required);
    }
    if (this.authConnectorFilter === "gateway") {
      return this.authConnectors.filter((item) => item.source_kind === "gateway");
    }
    if (this.authConnectorFilter === "plugin_app") {
      return this.authConnectors.filter((item) => item.source_kind !== "gateway");
    }
    return this.authConnectors;
  }

  private normalizeAuthConnectorFilter(filter: string): AuthConnectorFilter {
    return ["all", "ingress", "webhook", "polling", "actions", "approval", "gateway", "plugin_app"].includes(filter)
      ? (filter as AuthConnectorFilter)
      : "all";
  }

  private selectedAuthConnector(connectors: ConnectorSummary[]): ConnectorSummary | null {
    if (!connectors.length) {
      return null;
    }
    return connectors.find((item) => item.connector_key === this.selectedAuthConnectorKey) ?? connectors[0];
  }

  private emitRouteChange(route: GuiRouteId) {
    this.dispatchEvent(
      new CustomEvent<GuiRouteId>("route-change", {
        detail: route,
        bubbles: true,
        composed: true,
      }),
    );
  }

  private gatewayMethodScopeSummary(method: GatewayMethodMetadata): string {
    const scopes = this.gatewayScopeKeys(method).filter((item) => item !== "public");
    return scopes.length ? scopes.join(", ") : "no extra scopes";
  }

  private ingressConnectorCount(): number {
    return this.authConnectors.filter((item) => item.supports_webhook || item.supports_polling).length;
  }

  private approvalRequiredConnectorCount(): number {
    return this.authConnectors.filter((item) => item.approval_required).length;
  }

  private webhookConnectorCount(): number {
    return this.authConnectors.filter((item) => item.supports_webhook).length;
  }

  private pollingConnectorCount(): number {
    return this.authConnectors.filter((item) => item.supports_polling).length;
  }

  private actionConnectorCount(): number {
    return this.authConnectors.filter((item) => item.supports_actions).length;
  }

  private authConnectorEventTypeCount(): number {
    return this.authConnectors.reduce((count, connector) => count + (connector.event_types?.length ?? 0), 0);
  }

  private authConnectorActionTypeCount(): number {
    return this.authConnectors.reduce((count, connector) => count + (connector.action_types?.length ?? 0), 0);
  }

  private authConnectorSourceSummary(): string {
    const gatewayCount = this.authConnectors.filter((item) => item.source_kind === "gateway").length;
    const appCount = this.authConnectors.length - gatewayCount;
    return `gateway=${gatewayCount}, app=${appCount}`;
  }

  private authConnectorIngressSummary(): string {
    const webhookCount = this.authConnectors.filter((item) => item.supports_webhook).length;
    const pollingCount = this.authConnectors.filter((item) => item.supports_polling).length;
    return `webhook=${webhookCount}, polling=${pollingCount}`;
  }

  private authConnectorApprovalSummary(): string {
    const directCount = this.authConnectors.filter((item) => !item.approval_required).length;
    return `approval=${this.approvalRequiredConnectorCount()}, direct=${directCount}`;
  }

  private authConnectorCapabilitySummary(connector: ConnectorSummary): string {
    const capabilityText = [
      connector.supports_webhook ? "webhook" : "",
      connector.supports_polling ? "polling" : "",
      connector.supports_actions ? "actions" : "",
    ]
      .filter(Boolean)
      .join(", ") || "none";
    return `${connector.connector_key} · capabilities=${capabilityText}`;
  }

  private authConnectorOperatorNote(connector: ConnectorSummary): string {
    if (!connector.enabled) {
      return "该 connector 当前未启用，当前 auth surface 先做来源与 ingress 可见性，不假设已有独立 apply / pairing contract。";
    }
    if (connector.health === "error") {
      return "该 connector 处于 error，优先联动 plugins / audit / trace 检查上游认证、入口可达性和最近失败链路。";
    }
    if (connector.approval_required) {
      return "该 connector 会把外部动作带入 approval 链路；当前应与 approvals / sessions / trace 一起判断写风险。";
    }
    if (connector.supports_webhook || connector.supports_polling) {
      return "该 connector 当前主要表达 ingress / external auth 可见性，是 channels surface 的第一版真实入口。";
    }
    return "该 connector 当前更偏外部集成元数据；细粒度 auth / pairing contract 仍需等待后端成熟。";
  }

  private gatewayMethodOperatorNote(method: GatewayMethodMetadata): string {
    if (method.control_plane_write) {
      return "该 method 会消耗 control-plane write budget，operator 应结合 origin、scope 和 write-budget 语义判断执行风险。";
    }
    if (method.auth_required === false) {
      return "该 method 属于公开 bootstrap/connect 面，可在未认证前用于连接协商和能力探测。";
    }
    if (method.emits_events) {
      return "该 method 会推动事件流变化，适合与 approvals / sessions / workbench feed 一起观察。";
    }
    return "该 method 当前更偏只读可见性，适合作为 auth/scope 探针与健康基线。";
  }

  private authOperatorCues(): AuthOperatorCue[] {
    const cues: AuthOperatorCue[] = [];
    if (this.gatewayConnect.handshakeStatus !== "ready" || !this.gatewayConnect.pingOk) {
      cues.push({
        id: "connect",
        title: "Gateway connect degraded",
        detail: "当前 connect surface 未完全 ready，优先回到完整 settings / diagnostics 面确认 transport、handshake 与 refresh recovery。",
        route: "settings",
        actionLabel: "打开设置",
      });
    } else {
      cues.push({
        id: "connect",
        title: "Gateway connect ready",
        detail: "当前 connect / capabilities / ping 已 ready，可继续围绕 scope、connector 与 write risk 做 operator 判断。",
        route: null,
      });
    }
    if (this.approvalRequiredConnectorCount() > 0) {
      cues.push({
        id: "approvals",
        title: "Approval path present",
        detail: `当前有 ${this.approvalRequiredConnectorCount()} 个 connector 会把外部动作带入 approval 链路，优先到 approvals / audit 面确认 pending risk。`,
        route: "approvals",
        actionLabel: "打开审批与审计",
      });
    }
    if (this.ingressConnectorCount() > 0) {
      cues.push({
        id: "channels",
        title: "Ingress channels visible",
        detail: `当前有 ${this.ingressConnectorCount()} 个 ingress connector 已上屏，适合转到 plugins / connectors 面继续检查 channel inventory、health 与 operator note。`,
        route: "plugins",
        actionLabel: "打开插件与连接器",
      });
    }
    if (this.gatewayConnect.writeMethodCount > 0) {
      cues.push({
        id: "writes",
        title: "Control-plane writes exposed",
        detail: `当前 gateway 暴露 ${this.gatewayConnect.writeMethodCount} 个 write methods，应结合 scope、origin 和 write-budget 语义判断是否继续执行写操作。`,
        route: "settings",
        actionLabel: "查看完整设置面",
      });
    }
    return cues;
  }

  private settingsDiagnosticsCues(): SettingsDiagnosticsCue[] {
    const cues: SettingsDiagnosticsCue[] = [];
    const degradedProbes = this.degradedProbeCount();
    const workflowDiagnostics = this.workflowDiagnostics();
    const approvalDiagnostics = this.approvalDiagnostics();
    const pausedWorkflows = workflowDiagnostics.filter((item) =>
      String(item.workflow_status ?? item.status ?? "").trim().toLowerCase() === "paused"
    ).length;
    const pendingApprovals = approvalDiagnostics.filter((item) =>
      String(item.status ?? "").trim().toLowerCase() === "pending"
    ).length;
    if (degradedProbes > 0) {
      cues.push({
        id: "probes",
        title: "Gateway probes degraded",
        detail: `当前有 ${degradedProbes} 个 probes degraded，优先刷新诊断并确认 transport / runtime 可达性。`,
        actionKind: "refresh",
        actionLabel: "刷新诊断 / 日志",
      });
    }
    if (pausedWorkflows > 0) {
      cues.push({
        id: "workflows",
        title: "Paused workflows present",
        detail: `当前有 ${pausedWorkflows} 个 workflow 处于 paused，适合继续到 sessions / runs 面查看 workflow detail 与 trace timeline。`,
        actionKind: "route",
        route: "sessions",
        actionLabel: "打开 Sessions / Runs",
      });
    }
    if (pendingApprovals > 0) {
      cues.push({
        id: "approvals",
        title: "Pending approvals present",
        detail: `当前有 ${pendingApprovals} 个 approvals 仍处于 pending，适合继续到 approvals / audit 面处理。`,
        actionKind: "route",
        route: "approvals",
        actionLabel: "打开审批与审计",
      });
    }
    const logCue = this.logSourceRouteCue();
    cues.push({
      id: "logs",
      title: "Current log source",
      detail: `当前日志源建议落点到 ${logCue.label}；${logCue.note}`,
      actionKind: logCue.route && logCue.actionLabel ? "route" : "none",
      route: logCue.route,
      actionLabel: logCue.actionLabel,
    });
    return cues;
  }

  private parseLogRecords(limit = 3): ParsedLogRecord[] {
    const routeCue = this.logSourceRouteCue();
    return [...this.logTail.lines]
      .reverse()
      .slice(0, limit)
      .map((line, index) => this.parseLogRecord(line, index, routeCue));
  }

  private objectRecord(value: unknown): Record<string, unknown> | null {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      return null;
    }
    return value as Record<string, unknown>;
  }

  private firstText(...values: unknown[]): string {
    for (const value of values) {
      const text = String(value ?? "").trim();
      if (text) {
        return text;
      }
    }
    return "";
  }

  private parseLogRecord(line: string, index: number, routeCue: LogSourceRouteCue): ParsedLogRecord {
    const raw = String(line || "").trim();
    let payload: Record<string, unknown> | null = null;
    try {
      const parsed = JSON.parse(raw) as unknown;
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        payload = parsed as Record<string, unknown>;
      }
    } catch {
      payload = null;
    }
    const source = String(this.logTail.source || "").trim();
    if (source === "gateway.action_requests" && payload) {
      const actionId = String(payload.action_id ?? `action-${index + 1}`).trim();
      const actionType = String(payload.action_type ?? "unknown").trim();
      const requestedAt = String(payload.requested_at ?? "").trim();
      const summary = String(payload.summary ?? "").trim() || raw;
      const context = this.resolveActionRequestLogContext(payload, actionId);
      return {
        id: `${actionId}-${index}`,
        title: actionId || `action-${index + 1}`,
        detail: `type=${actionType} · ${requestedAt || "no timestamp"} · ${summary}`,
        raw,
        route: "approvals",
        actionLabel: context ? "打开动作上下文" : "打开审批与审计",
        context,
      };
    }
    if (source === "gateway.approval_tickets" && payload) {
      const approvalId = String(payload.approval_id ?? `approval-${index + 1}`).trim();
      const status = String(payload.status ?? "unknown").trim();
      const requestedAt = String(payload.requested_at ?? "").trim();
      const summary = String(payload.summary ?? payload.reason ?? "").trim() || raw;
      const context = this.resolveApprovalTicketLogContext(payload, approvalId);
      return {
        id: `${approvalId}-${index}`,
        title: approvalId || `approval-${index + 1}`,
        detail: `status=${status} · ${requestedAt || "no timestamp"} · ${summary}`,
        raw,
        route: "approvals",
        actionLabel: context ? "打开审批上下文" : "打开审批与审计",
        context,
      };
    }
    if (source === "gateway.audit_records" && payload) {
      const auditId = String(payload.audit_id ?? `audit-${index + 1}`).trim();
      const stage = String(payload.stage ?? "unknown").trim();
      const status = String(payload.status ?? "unknown").trim();
      const summary = String(payload.summary ?? "").trim() || raw;
      const context = this.resolveAuditLogContext(payload, auditId);
      return {
        id: `${auditId}-${index}`,
        title: auditId || `audit-${index + 1}`,
        detail: `stage=${stage} · status=${status} · ${summary}`,
        raw,
        route: "approvals",
        actionLabel: context ? "打开审批上下文" : "打开审批与审计",
        context,
      };
    }
    if (source === "gateway.events" && payload) {
      const metadata = this.objectRecord(payload.metadata);
      const causality = this.objectRecord(metadata?.causality);
      const eventPayload = this.objectRecord(payload.payload);
      const eventId = this.firstText(payload.event_id, `event-${index + 1}`);
      const eventType = this.firstText(payload.event_type, "unknown");
      const sourceKind = this.firstText(payload.source_kind, "unknown");
      const occurredAt = this.firstText(payload.occurred_at, payload.received_at);
      const summary =
        this.firstText(
          payload.summary,
          metadata?.summary,
          eventPayload?.summary,
          eventType,
        ) || raw;
      const context = this.resolveGatewayEventLogContext(payload, {
        metadata,
        causality,
        eventPayload,
      });
      return {
        id: `${eventId}-${index}`,
        title: eventType || eventId || `event-${index + 1}`,
        detail: `kind=${sourceKind} · ${occurredAt || "no timestamp"} · ${summary}`,
        raw,
        route: "sessions",
        actionLabel: context?.workflowRunId ? "打开 Workflow Detail" : "打开 Sessions / Runs",
        context,
      };
    }
    if (source === "gateway.workflow_runs" && payload) {
      const workflowRunId = String(payload.workflow_run_id ?? payload.run_id ?? `workflow-${index + 1}`).trim();
      const status = String(payload.status ?? "unknown").trim();
      const workflowName = String(payload.workflow_name ?? workflowRunId).trim();
      const summary = String(payload.summary ?? payload.result_summary ?? "").trim() || raw;
      const context = this.resolveWorkflowRunLogContext(payload, workflowRunId);
      return {
        id: `${workflowRunId}-${index}`,
        title: workflowName || workflowRunId || `workflow-${index + 1}`,
        detail: `status=${status}${context?.traceId ? ` · trace=${context.traceId}` : ""} · ${summary}`,
        raw,
        route: "sessions",
        actionLabel: context ? "打开 Workflow Detail" : "打开 Sessions / Runs",
        context,
      };
    }
    if (source === "thread.active_rollout" && payload) {
      const turn = this.objectRecord(payload.turn);
      const turnStatus = this.objectRecord(turn?.status);
      const turnRuntimeState = this.objectRecord(turn?.runtime_state);
      const metadata = this.objectRecord(payload.metadata);
      const causality = this.objectRecord(metadata?.causality);
      const type = this.firstText(payload.type, turn?.type, "record");
      const threadId = this.firstText(payload.thread_id, turn?.thread_id, "thread");
      const timestamp = this.firstText(payload.timestamp, turn?.timestamp);
      const summary =
        this.firstText(
          payload.user_text,
          payload.assistant_text,
          turn?.user_text,
          turn?.assistant_text,
          turn?.commentary_text,
        ) || raw;
      const traceId = this.firstText(
        payload.trace_id,
        payload.traceId,
        turn?.trace_id,
        turn?.traceId,
        turnStatus?.trace_id,
        turnStatus?.traceId,
        turnRuntimeState?.trace_id,
        turnRuntimeState?.traceId,
        causality?.trace_id,
        causality?.traceId,
      );
      const workflowRunId = this.firstText(
        payload.workflow_run_id,
        payload.workflowRunId,
        turn?.workflow_run_id,
        turn?.workflowRunId,
        turnStatus?.workflow_run_id,
        turnStatus?.workflowRunId,
        turnRuntimeState?.workflow_run_id,
        turnRuntimeState?.workflowRunId,
        causality?.workflow_run_id,
        causality?.workflowRunId,
      );
      const context = traceId
        ? {
            route: "sessions" as const,
            traceId,
            workflowRunId: workflowRunId || undefined,
            timelineScope: "workflowRuns" as const,
            source: "settings-diagnostics" as const,
          }
        : null;
      return {
        id: `${type}-${index}`,
        title: `${type} · ${threadId}`,
        detail: `${timestamp || "no timestamp"}${traceId ? ` · trace=${traceId}` : ""} · ${summary}`,
        raw,
        route: "sessions",
        actionLabel: context ? "打开 Workflow Detail" : "打开 Sessions / Runs",
        context,
      };
    }
    return {
      id: `raw-${index}`,
      title: `record ${index + 1}`,
      detail: raw || "empty log line",
      raw,
      route: routeCue.route,
      actionLabel: routeCue.actionLabel,
      context: null,
    };
  }

  private resolveActionRequestLogContext(
    payload: Record<string, unknown>,
    actionId: string,
  ): SettingsControlContextDetail | null {
    const traceIdFromPayload = String(payload.trace_id ?? payload.traceId ?? "").trim();
    const actionRequests = this.controlUiState?.actionRequests ?? [];
    const match = actionRequests.find((item) => {
      const record = item as Record<string, unknown>;
      return String(record.action_id ?? "").trim() === actionId;
    }) as Record<string, unknown> | undefined;
    const traceId = traceIdFromPayload || String(match?.trace_id ?? match?.traceId ?? "").trim();
    if (!traceId) {
      return null;
    }
    return {
      route: "approvals",
      traceId,
      actionId: actionId || String(match?.action_id ?? "").trim() || undefined,
      source: "settings-diagnostics",
    };
  }

  private resolveApprovalTicketLogContext(
    payload: Record<string, unknown>,
    approvalId: string,
  ): SettingsControlContextDetail | null {
    const traceIdFromPayload = String(payload.trace_id ?? payload.traceId ?? "").trim();
    const actionIdFromPayload = String(payload.action_id ?? "").trim();
    const approvalTickets = this.controlUiState?.approvalTickets ?? [];
    const match = approvalTickets.find((item) => {
      const record = item as Record<string, unknown>;
      return String(record.approval_id ?? "").trim() === approvalId;
    }) as Record<string, unknown> | undefined;
    const traceId = traceIdFromPayload || String(match?.trace_id ?? match?.traceId ?? "").trim();
    if (!traceId) {
      return null;
    }
    return {
      route: "approvals",
      traceId,
      approvalId: approvalId || String(match?.approval_id ?? "").trim() || undefined,
      actionId: actionIdFromPayload || String(match?.action_id ?? "").trim() || undefined,
      source: "settings-diagnostics",
    };
  }

  private resolveAuditLogContext(
    payload: Record<string, unknown>,
    auditId: string,
  ): SettingsControlContextDetail | null {
    const traceIdFromPayload = String(payload.trace_id ?? payload.traceId ?? "").trim();
    const approvalIdFromPayload = String(payload.approval_id ?? "").trim();
    const actionIdFromPayload = String(payload.action_id ?? "").trim();
    const auditRecords = this.controlUiState?.auditRecords ?? [];
    const match = auditRecords.find((item) => {
      const record = item as Record<string, unknown>;
      return String(record.audit_id ?? "").trim() === auditId;
    }) as Record<string, unknown> | undefined;
    const traceId = traceIdFromPayload || String(match?.trace_id ?? match?.traceId ?? "").trim();
    if (!traceId) {
      return null;
    }
    return {
      route: "approvals",
      traceId,
      approvalId: approvalIdFromPayload || String(match?.approval_id ?? "").trim() || undefined,
      actionId: actionIdFromPayload || String(match?.action_id ?? "").trim() || undefined,
      auditId: auditId || String(match?.audit_id ?? "").trim() || undefined,
      source: "settings-diagnostics",
    };
  }

  private resolveWorkflowRunLogContext(
    payload: Record<string, unknown>,
    workflowRunId: string,
  ): SettingsControlContextDetail | null {
    const traceIdFromPayload = String(payload.trace_id ?? payload.traceId ?? "").trim();
    const workflowRuns = this.controlUiState?.workflowRuns ?? [];
    const match = workflowRuns.find((item) => {
      const record = item as Record<string, unknown>;
      return String(record.workflow_run_id ?? record.run_id ?? "").trim() === workflowRunId;
    }) as Record<string, unknown> | undefined;
    const traceId = traceIdFromPayload || String(match?.trace_id ?? match?.traceId ?? "").trim();
    if (!traceId) {
      return null;
    }
    return {
      route: "sessions",
      traceId,
      workflowRunId: workflowRunId || String(match?.workflow_run_id ?? match?.run_id ?? "").trim() || undefined,
      timelineScope: "workflowRuns",
      source: "settings-diagnostics",
    };
  }

  private resolveGatewayEventLogContext(
    payload: Record<string, unknown>,
    nested?: {
      metadata?: Record<string, unknown> | null;
      causality?: Record<string, unknown> | null;
      eventPayload?: Record<string, unknown> | null;
    },
  ): SettingsControlContextDetail | null {
    const metadata = nested?.metadata ?? this.objectRecord(payload.metadata);
    const causality = nested?.causality ?? this.objectRecord(metadata?.causality);
    const eventPayload = nested?.eventPayload ?? this.objectRecord(payload.payload);
    const traceId = this.firstText(
      payload.trace_id,
      payload.traceId,
      causality?.trace_id,
      causality?.traceId,
      metadata?.trace_id,
      metadata?.traceId,
      eventPayload?.trace_id,
      eventPayload?.traceId,
    );
    if (!traceId) {
      return null;
    }
    const workflowRunIdFromPayload = this.firstText(
      payload.workflow_run_id,
      payload.workflowRunId,
      causality?.workflow_run_id,
      causality?.workflowRunId,
      metadata?.workflow_run_id,
      metadata?.workflowRunId,
      eventPayload?.workflow_run_id,
      eventPayload?.workflowRunId,
    );
    const workflowRuns = this.controlUiState?.workflowRuns ?? [];
    const match = workflowRuns.find((item) => {
      const record = item as Record<string, unknown>;
      return String(record.trace_id ?? record.traceId ?? "").trim() === traceId;
    }) as Record<string, unknown> | undefined;
    return {
      route: "sessions",
      traceId,
      workflowRunId:
        workflowRunIdFromPayload || this.firstText(match?.workflow_run_id, match?.run_id) || undefined,
      timelineScope: "workflowRuns",
      source: "settings-diagnostics",
    };
  }

  private renderLogRecords() {
    const records = this.parseLogRecords();
    if (!records.length) {
      return html`<div class="diag-item"><span class="diag-meta">暂无可解析日志记录。</span></div>`;
    }
    return records.map(
      (record, index) => html`
        <section class="diag-item" data-testid=${`settings-log-record-${index}`}>
          <div class="diag-title">${record.title}</div>
          <div class="diag-meta">${record.detail}</div>
          <div class="diag-meta">${record.raw}</div>
          <div class="actions inline">
            ${record.route && record.actionLabel
              ? html`
                  <button
                    type="button"
                    class="secondary"
                    data-testid=${`settings-log-record-open-${index}`}
                    @click=${() =>
                      record.context
                        ? this.navigateToControlContext(record.context)
                        : this.emitRouteChange(record.route!)}
                  >
                    ${record.actionLabel}
                  </button>
                `
              : html`<span class="hint">当前记录只保留文本可见性。</span>`}
          </div>
        </section>
      `,
    );
  }

  private renderLogSourceInventory() {
    const sources = this.logTail.availableSources;
    if (!sources.length) {
      return html`<div class="diag-item"><span class="diag-meta">暂无可用日志源。</span></div>`;
    }
    return sources.map((source) => {
      const isActive = source.key === this.logTail.source;
      const cue = this.logSourceRouteCueFor(source.key);
      return html`
        <section class="diag-item" data-testid=${`settings-log-source-item-${this.testIdPart(source.key)}`}>
          <div class="diag-title">${source.label}</div>
          <div class="diag-meta">${source.key}</div>
          <div class="diag-meta">${source.path || "暂无 path"}</div>
          <div class="diag-meta">
            ${isActive
              ? `当前选中 · ${this.logTail.lineCount} lines · ${this.logTail.truncated ? "truncated" : "full"}`
              : `next-hop=${cue.label}`}
          </div>
          <div class="actions inline">
            <button
              type="button"
              class="secondary"
              data-testid=${`settings-log-source-select-${this.testIdPart(source.key)}`}
              @click=${() => this.handleLogSourceQuickSelect(source.key)}
            >
              ${isActive ? "刷新当前日志源" : "切换并查看日志"}
            </button>
            <button
              type="button"
              class="secondary"
              data-testid=${`settings-log-source-open-logs-${this.testIdPart(source.key)}`}
              @click=${() => this.navigateToLogsSurfaceWithSource(source.key)}
            >
              打开 Logs 面
            </button>
            ${cue.route && cue.actionLabel
              ? html`
                  <button
                    type="button"
                    class="secondary"
                    data-testid=${`settings-log-source-open-${this.testIdPart(source.key)}`}
                    @click=${() => this.emitRouteChange(cue.route!)}
                  >
                    ${cue.actionLabel}
                  </button>
                `
              : null}
          </div>
        </section>
      `;
    });
  }

  private renderProbeInventory() {
    const entries = this.probeInventoryEntries();
    if (!entries.length) {
      return html`<div class="diag-item"><span class="diag-meta">暂无 probe inventory。</span></div>`;
    }
    return entries.map(
      (entry) => html`
        <section class="diag-item" data-testid=${`settings-probe-item-${this.testIdPart(entry.key)}`}>
          <div class="diag-title">${entry.key}</div>
          <div class="diag-status-row">
            <span class="diag-chip ${entry.ok ? "" : "error"}">${entry.ok ? "ok" : "degraded"}</span>
          </div>
          <div class="diag-meta">${entry.detail}</div>
          <div class="diag-meta">${entry.note}</div>
          <div class="actions inline">
            ${entry.route && entry.actionLabel
              ? html`
                  <button
                    type="button"
                    class="secondary"
                    data-testid=${`settings-probe-open-${this.testIdPart(entry.key)}`}
                    @click=${() => this.emitRouteChange(entry.route!)}
                  >
                    ${entry.actionLabel}
                  </button>
                `
              : html`<span class="hint">当前 probe 只保留指标可见性。</span>`}
          </div>
        </section>
      `,
    );
  }

  private renderSnapshotInventory() {
    const entries = this.snapshotInventoryEntries();
    if (!entries.length) {
      return html`<div class="diag-item"><span class="diag-meta">暂无 control-ui snapshot inventory。</span></div>`;
    }
    return entries.map(
      (entry) => html`
        <section class="diag-item" data-testid=${`settings-snapshot-item-${entry.key}`}>
          <div class="diag-title">${entry.key}</div>
          <div class="diag-meta">count=${entry.count}</div>
          <div class="diag-meta">${entry.detail}</div>
          <div class="actions inline">
            ${entry.route && entry.actionLabel
              ? html`
                  <button
                    type="button"
                    class="secondary"
                    data-testid=${`settings-snapshot-open-${entry.key}`}
                    @click=${() => {
                      if (entry.key === "workflowRuns") {
                        const context = this.snapshotInventoryWorkflowContext();
                        if (context) {
                          this.navigateToControlContext(context);
                          return;
                        }
                      }
                      if (entry.key === "approvalTickets") {
                        const context = this.snapshotInventoryApprovalContext();
                        if (context) {
                          this.navigateToControlContext(context);
                          return;
                        }
                      }
                      if (entry.key === "connectors") {
                        const context = this.snapshotInventoryPluginsContext();
                        if (context) {
                          this.navigateToPluginsConnectorContext(context);
                          return;
                        }
                      }
                      this.emitRouteChange(entry.route!);
                    }}
                  >
                    ${entry.actionLabel}
                  </button>
                `
              : html`<span class="hint">当前只保留快照可见性。</span>`}
          </div>
        </section>
      `,
    );
  }

  private renderTraceHotspots() {
    const hotspots = this.traceHotspots();
    if (!hotspots.length) {
      return html`<div class="diag-item"><span class="diag-meta">暂无 trace hotspots。</span></div>`;
    }
    return hotspots.map(
      (entry) => html`
        <section class="diag-item" data-testid=${`settings-trace-hotspot-${entry.traceId}`}>
          <div class="diag-title">${entry.traceId}</div>
          <div class="diag-status-row">
            ${entry.workflowStatus
              ? html`
                  <span class="diag-chip ${entry.workflowStatus === "paused" ? "warn" : ""}">
                    workflow=${entry.workflowStatus}
                  </span>
                `
              : null}
            ${entry.pendingApprovalCount > 0
              ? html`<span class="diag-chip warn">pending approvals=${entry.pendingApprovalCount}</span>`
              : entry.approvalCount > 0
                ? html`<span class="diag-chip">approvals=${entry.approvalCount}</span>`
                : null}
          </div>
          <div class="diag-meta">
            workflow=${entry.workflowName || entry.workflowRunId || "-"} · plugin=${entry.pluginName || "-"}
          </div>
          <div class="diag-meta">
            actions=${entry.actionCount} · approvals=${entry.approvalCount} · audits=${entry.auditCount} · events=${entry.eventCount}
          </div>
          <div class="diag-meta">
            ${entry.pendingApprovalCount > 0
              ? "该 trace 同时具备 workflow 与 approval 诊断语义，适合先看审批链路再回 workflow detail。"
              : "该 trace 已具备 workflow / trace detail 上下文，可直接落到 sessions 继续 drill-down。"}
          </div>
          <div class="actions inline">
            <button
              type="button"
              class="secondary"
              data-testid=${`settings-trace-hotspot-open-workflow-${entry.traceId}`}
              @click=${() => this.navigateToControlContext({
                route: "sessions",
                traceId: entry.traceId,
                workflowRunId: entry.workflowRunId,
                timelineScope: "workflowRuns",
                source: "settings-diagnostics",
              })}
            >
              打开 Workflow Detail
            </button>
            ${entry.approvalCount > 0
              ? html`
                  <button
                    type="button"
                    class="secondary"
                    data-testid=${`settings-trace-hotspot-open-approvals-${entry.traceId}`}
                    @click=${() => this.navigateToControlContext({
                      route: "approvals",
                      traceId: entry.traceId,
                      approvalId: entry.approvalId,
                      source: "settings-diagnostics",
                    })}
                  >
                    打开审批上下文
                  </button>
                `
              : null}
          </div>
        </section>
      `,
    );
  }

  private logSourceRouteCue(): LogSourceRouteCue {
    return this.logSourceRouteCueFor(this.logTail.source);
  }

  private logSourceRouteCueFor(sourceValue: string): LogSourceRouteCue {
    const source = String(sourceValue || "").trim();
    if (source === "gateway.action_requests") {
      return {
        route: "approvals",
        label: "审批与审计",
        note: "当前日志源是 gateway action requests，适合继续到 approvals / audit 面查看 action request 与审批链路。",
        actionLabel: "打开审批与审计",
      };
    }
    if (source === "gateway.approval_tickets") {
      return {
        route: "approvals",
        label: "审批与审计",
        note: "当前日志源是 gateway approval tickets，适合继续到 approvals / audit 面查看审批状态与因果链。",
        actionLabel: "打开审批与审计",
      };
    }
    if (source === "gateway.audit_records") {
      return {
        route: "approvals",
        label: "审批与审计",
        note: "当前日志源是 gateway audit records，适合继续到 approvals / audit 面结合审批链路与审计因果链查看。",
        actionLabel: "打开审批与审计",
      };
    }
    if (source === "gateway.events") {
      return {
        route: "sessions",
        label: "Sessions / Runs",
        note: "当前日志源是 gateway events，适合继续到 sessions / runs 面结合 trace timeline 与 workflow detail 查看。",
        actionLabel: "打开 Sessions / Runs",
      };
    }
    if (source === "gateway.workflow_runs") {
      return {
        route: "sessions",
        label: "Sessions / Runs",
        note: "当前日志源是 gateway workflow runs，适合继续到 sessions / runs 面查看 workflow detail 与 trace timeline。",
        actionLabel: "打开 Sessions / Runs",
      };
    }
    if (source === "thread.active_rollout") {
      return {
        route: "sessions",
        label: "Sessions / Runs",
        note: "当前日志源是 active rollout，适合继续到 sessions / runs 面结合 thread、trace 与 workflow detail 查看。",
        actionLabel: "打开 Sessions / Runs",
      };
    }
    return {
      route: "settings",
      label: "设置",
      note: "当前日志源没有更细的 route 语义，先保留在 settings diagnostics 内查看。",
      actionLabel: "留在设置面",
    };
  }

  private testIdPart(value: string): string {
    return value.replace(/[^a-zA-Z0-9_.-]+/g, "_");
  }

  private workflowDiagnostics(): Array<Record<string, unknown>> {
    const diagnostics = this.controlUiState?.diagnostics ?? {};
    const raw = (diagnostics as Record<string, unknown>).workflow_diagnostics;
    return Array.isArray(raw) ? (raw as Array<Record<string, unknown>>) : [];
  }

  private approvalDiagnostics(): Array<Record<string, unknown>> {
    const diagnostics = this.controlUiState?.diagnostics ?? {};
    const raw = (diagnostics as Record<string, unknown>).approval_diagnostics;
    return Array.isArray(raw) ? (raw as Array<Record<string, unknown>>) : [];
  }

  private logSourceSummary(): string {
    const label = this.logTail.label || "暂无日志源";
    const lineText = `${this.logTail.lineCount} lines`;
    const truncatedText = this.logTail.truncated ? "truncated" : "full";
    return `${label} · ${lineText} · ${truncatedText}`;
  }

  private renderWorkflowDiagnostics() {
    const diagnostics = this.workflowDiagnostics().slice(0, 3);
    if (!diagnostics.length) {
      return html`<div class="diag-item"><span class="diag-meta">暂无 workflow diagnostics。</span></div>`;
    }
    return diagnostics.map((item) => {
      const traceId = String(item.trace_id ?? "").trim();
      const workflowRunId = String(item.workflow_run_id ?? "").trim();
      const status = String(item.workflow_status ?? item.status ?? "unknown").trim() || "unknown";
      const reasoning = String((item.reasoning as Record<string, unknown> | undefined)?.summary ?? "").trim();
      return html`
        <section class="diag-item">
          <div class="diag-title">${String(item.workflow_name ?? workflowRunId ?? "workflow")}</div>
          <div class="diag-status-row">
            <span class="diag-chip ${status === "paused" ? "warn" : ""}">${status}</span>
            <span class="diag-chip">${String(item.plugin_name ?? "unknown-plugin")}</span>
          </div>
          <div class="diag-meta">${traceId || "-"}</div>
          <div class="diag-meta">${reasoning || String(item.result_summary ?? "暂无 reasoning summary")}</div>
          <div class="actions inline">
            <button
              type="button"
              class="secondary"
              data-testid=${`workflow-diagnostic-open-${workflowRunId || traceId}`}
              ?disabled=${!traceId}
              @click=${() => this.navigateToControlContext({
                route: "sessions",
                traceId,
                workflowRunId: workflowRunId || undefined,
                timelineScope: "workflowRuns",
                source: "settings-diagnostics",
              })}
            >
              打开 Workflow Detail
            </button>
          </div>
        </section>
      `;
    });
  }

  private renderApprovalDiagnostics() {
    const diagnostics = this.approvalDiagnostics().slice(0, 3);
    if (!diagnostics.length) {
      return html`<div class="diag-item"><span class="diag-meta">暂无 approval diagnostics。</span></div>`;
    }
    return diagnostics.map((item) => {
      const traceId = String(item.trace_id ?? "").trim();
      const approvalId = String(item.approval_id ?? "").trim();
      const status = String(item.status ?? "unknown").trim() || "unknown";
      return html`
        <section class="diag-item">
          <div class="diag-title">${approvalId || "approval diagnostic"}</div>
          <div class="diag-status-row">
            <span class="diag-chip ${status === "pending" ? "warn" : status === "rejected" ? "error" : ""}">
              ${status}
            </span>
            <span class="diag-chip">${traceId || "-"}</span>
          </div>
          <div class="diag-meta">审批链路已进入 operator surface，可直接跳转到 approvals / audit 上下文。</div>
          <div class="actions inline">
            <button
              type="button"
              class="secondary"
              data-testid=${`approval-diagnostic-open-${approvalId || traceId}`}
              ?disabled=${!traceId}
              @click=${() => this.navigateToControlContext({
                route: "approvals",
                traceId,
                approvalId: approvalId || undefined,
                source: "settings-diagnostics",
              })}
            >
              打开审批上下文
            </button>
          </div>
        </section>
      `;
    });
  }

  private scheduleDiagnosticsRefresh(delayMs = 5000) {
    if (!this.autoRefreshEnabled || !this.isConnected) {
      return;
    }
    this.clearDiagnosticsRefreshTimer();
    this.diagnosticsRefreshTimer = setTimeout(() => {
      this.diagnosticsRefreshTimer = null;
      void this.loadDiagnostics(this.logTail.source);
    }, delayMs);
  }

  private clearDiagnosticsRefreshTimer() {
    if (this.diagnosticsRefreshTimer !== null) {
      clearTimeout(this.diagnosticsRefreshTimer);
      this.diagnosticsRefreshTimer = null;
    }
  }

  private navigateToControlContext(detail: SettingsControlContextDetail) {
    if (!detail.traceId.trim()) {
      return;
    }
    this.dispatchEvent(
      new CustomEvent<SettingsControlContextDetail>("navigate-control-context", {
        detail,
        bubbles: true,
        composed: true,
      }),
    );
  }

  private readonly navigateToLogsSurface = () => {
    this.navigateToLogsSurfaceWithSource(this.logTail.source);
  };

  private navigateToLogsSurfaceWithSource(source: string) {
    this.dispatchEvent(
      new CustomEvent("navigate-control-context", {
        detail: {
          route: "logs",
          source: String(source || "").trim() || undefined,
        },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private navigateToPluginsConnectorContext(detail: SettingsPluginsRouteContextDetail) {
    this.dispatchEvent(
      new CustomEvent<SettingsPluginsRouteContextDetail>("navigate-control-context", {
        detail,
        bubbles: true,
        composed: true,
      }),
    );
  }

  private navigateToSettingsConnectorContext(detail: SettingsRouteContextDetail) {
    this.dispatchEvent(
      new CustomEvent<SettingsRouteContextDetail>("navigate-control-context", {
        detail,
        bubbles: true,
        composed: true,
      }),
    );
  }

  private composeDraftSettings(
    snapshot: SettingsSnapshot = this.snapshot,
    runtimePolicy: RuntimePolicyForm = this.runtimePolicy,
  ): SettingsSnapshot {
    return {
      ...snapshot,
      runtimePolicy: {
        ...runtimePolicy,
      },
    };
  }

  private buildApplyPayload(
    draft: SettingsSnapshot,
    validation: SettingsDraftValidation,
  ): Partial<SettingsSnapshot> {
    const payload: Partial<SettingsSnapshot> = {};
    const applyable = new Set(validation.applyableFields);
    const runtimePolicyPayload: Record<string, unknown> = {};
    if (applyable.has("approval_policy")) {
      runtimePolicyPayload.approval_policy = draft.runtimePolicy?.approval_policy;
    }
    if (applyable.has("sandbox_mode")) {
      runtimePolicyPayload.sandbox_mode = draft.runtimePolicy?.sandbox_mode;
    }
    if (applyable.has("web_search_mode")) {
      runtimePolicyPayload.web_search_mode = this.normalizeWebSearchModeToken(draft.runtimePolicy?.web_search_mode);
    }
    if (applyable.has("network_access")) {
      runtimePolicyPayload.network_access = draft.runtimePolicy?.network_access;
    }
    if (Object.keys(runtimePolicyPayload).length) {
      payload.runtimePolicy = runtimePolicyPayload;
    }
    if (applyable.has("browserHeadless")) {
      payload.browserHeadless = draft.browserHeadless;
    }
    if (applyable.has("pluginAutoLoad")) {
      payload.pluginAutoLoad = draft.pluginAutoLoad;
    }
    return payload;
  }

  private retainedDraftFields(validation: SettingsDraftValidation): string[] {
    const blocked = new Set(validation.blockedFields);
    return validation.changedFields.filter((field) => blocked.has(field));
  }

  private mergeRetainedDraftSnapshot(
    appliedSnapshot: SettingsSnapshot,
    draft: SettingsSnapshot,
    validation: SettingsDraftValidation,
  ): SettingsSnapshot {
    const retainedFields = new Set(this.retainedDraftFields(validation));
    return {
      ...appliedSnapshot,
      model: retainedFields.has("model") ? draft.model : appliedSnapshot.model,
      workspaceRoot: retainedFields.has("workspaceRoot") ? draft.workspaceRoot : appliedSnapshot.workspaceRoot,
    };
  }

  private mergeRetainedDraftRuntimePolicy(
    appliedRuntimePolicy: RuntimePolicyForm,
    draft: SettingsSnapshot,
    validation: SettingsDraftValidation,
  ): RuntimePolicyForm {
    const retainedFields = new Set(this.retainedDraftFields(validation));
    return {
      approval_policy: retainedFields.has("approval_policy")
        ? String(draft.runtimePolicy?.approval_policy ?? appliedRuntimePolicy.approval_policy)
        : appliedRuntimePolicy.approval_policy,
      sandbox_mode: retainedFields.has("sandbox_mode")
        ? String(draft.runtimePolicy?.sandbox_mode ?? appliedRuntimePolicy.sandbox_mode)
        : appliedRuntimePolicy.sandbox_mode,
      web_search_mode: retainedFields.has("web_search_mode")
        ? String(draft.runtimePolicy?.web_search_mode ?? appliedRuntimePolicy.web_search_mode)
        : appliedRuntimePolicy.web_search_mode,
      network_access: retainedFields.has("network_access")
        ? String(draft.runtimePolicy?.network_access ?? appliedRuntimePolicy.network_access)
        : appliedRuntimePolicy.network_access,
    };
  }

  private validateDraft(): SettingsDraftValidation {
    const baseline = this.lastAppliedSettings;
    const draft = this.composeDraftSettings();
    const changedFields: string[] = [];
    const applyableFields: string[] = [];
    const blockedFields: string[] = [];
    const restartReasons: string[] = [];
    const messages: string[] = [];
    const runtimePolicyFields = new Set(["approval_policy", "sandbox_mode", "web_search_mode", "network_access"]);
    const runtimeFlagFields = new Set(["browserHeadless", "pluginAutoLoad"]);

    const pushChanged = (field: string, changed: boolean) => {
      if (changed) {
        changedFields.push(field);
      }
    };
    const fieldChanged = (left: unknown, right: unknown) => String(left ?? "") !== String(right ?? "");
    pushChanged("model", fieldChanged(draft.model, baseline?.model));
    pushChanged("workspaceRoot", fieldChanged(draft.workspaceRoot, baseline?.workspaceRoot));
    pushChanged("browserHeadless", draft.browserHeadless !== Boolean(baseline?.browserHeadless));
    pushChanged("pluginAutoLoad", draft.pluginAutoLoad !== Boolean(baseline?.pluginAutoLoad));
    pushChanged(
      "approval_policy",
      fieldChanged(draft.runtimePolicy?.approval_policy, baseline?.runtimePolicy?.approval_policy),
    );
    pushChanged(
      "sandbox_mode",
      fieldChanged(draft.runtimePolicy?.sandbox_mode, baseline?.runtimePolicy?.sandbox_mode),
    );
    pushChanged(
      "web_search_mode",
      fieldChanged(
        this.normalizeWebSearchModeToken(draft.runtimePolicy?.web_search_mode),
        this.normalizeWebSearchModeToken(baseline?.runtimePolicy?.web_search_mode),
      ),
    );
    pushChanged(
      "network_access",
      fieldChanged(draft.runtimePolicy?.network_access, baseline?.runtimePolicy?.network_access),
    );

    const approvalPolicy = String(draft.runtimePolicy?.approval_policy ?? "");
    const sandboxMode = String(draft.runtimePolicy?.sandbox_mode ?? "");
    const webSearchMode = this.normalizeWebSearchModeToken(draft.runtimePolicy?.web_search_mode);
    const networkAccess = String(draft.runtimePolicy?.network_access ?? "");
    if (!APPROVAL_POLICY_OPTIONS.includes(approvalPolicy as (typeof APPROVAL_POLICY_OPTIONS)[number])) {
      blockedFields.push("approval_policy");
      messages.push(`approval_policy=${approvalPolicy || "-"} 不在当前 GUI 支持范围。`);
    }
    if (!SANDBOX_MODE_OPTIONS.includes(sandboxMode as (typeof SANDBOX_MODE_OPTIONS)[number])) {
      blockedFields.push("sandbox_mode");
      messages.push(`sandbox_mode=${sandboxMode || "-"} 不在当前 GUI 支持范围。`);
    }
    if (!WEB_SEARCH_MODE_OPTIONS.includes(webSearchMode as (typeof WEB_SEARCH_MODE_OPTIONS)[number])) {
      blockedFields.push("web_search_mode");
      messages.push(`web_search_mode=${webSearchMode || "-"} 不在当前 GUI 支持范围。`);
    }
    if (!NETWORK_ACCESS_OPTIONS.includes(networkAccess as (typeof NETWORK_ACCESS_OPTIONS)[number])) {
      blockedFields.push("network_access");
      messages.push(`network_access=${networkAccess || "-"} 不在当前 GUI 支持范围。`);
    }
    if (!String(draft.workspaceRoot || "").trim()) {
      blockedFields.push("workspaceRoot");
      messages.push("workspaceRoot 不能为空。");
    }
    if (changedFields.includes("model")) {
      blockedFields.push("model");
      messages.push("当前 bridge 尚未把 provider/model 变更接入 settings.update apply contract。");
    }
    if (changedFields.includes("workspaceRoot")) {
      blockedFields.push("workspaceRoot");
      messages.push("当前 bridge 尚未把 workspaceRoot 变更接入真实 apply/restart contract。");
    }

    for (const field of changedFields) {
      if (!blockedFields.includes(field)) {
        applyableFields.push(field);
      }
    }

    if (changedFields.includes("browserHeadless")) {
      restartReasons.push("browserHeadless 变更");
    }
    if (changedFields.includes("pluginAutoLoad")) {
      restartReasons.push("pluginAutoLoad 变更");
    }

    if (!changedFields.length) {
      messages.push("当前草稿与已应用快照一致。");
    } else if (applyableFields.length) {
      messages.push(`当前可通过 settings.update 应用 ${applyableFields.length} 个字段。`);
    }
    if (applyableFields.some((field) => runtimePolicyFields.has(field))) {
      messages.push("runtime policy 字段会通过 settings.update -> runtime.configure_runtime_policy 写回。");
    }
    if (applyableFields.some((field) => runtimeFlagFields.has(field))) {
      messages.push("browserHeadless / pluginAutoLoad 会通过 settings.update 写入 GUI runtime flags。");
    }
    messages.push("可使用显式 config.validate 动作拉取 machine-readable validation result。");
    if (restartReasons.length) {
      messages.push("可使用显式 config.restart.report 拉取 manual restart posture；GUI 不伪造 restart 动作。");
    }
    const applyContractParts: string[] = [];
    const appliedRuntimePolicyFields = applyableFields.filter((field) => runtimePolicyFields.has(field));
    const appliedRuntimeFlags = applyableFields.filter((field) => runtimeFlagFields.has(field));
    if (appliedRuntimePolicyFields.length) {
      applyContractParts.push(
        `settings.update -> runtime.configure_runtime_policy(${appliedRuntimePolicyFields.join(", ")})`,
      );
    }
    if (appliedRuntimeFlags.length) {
      applyContractParts.push(`settings.update -> GUI runtime flags(${appliedRuntimeFlags.join(", ")})`);
    }
    const uniqueBlocked = Array.from(new Set(blockedFields));
    const uniqueMessages = Array.from(new Set(messages));
    return {
      level: uniqueBlocked.length ? "error" : restartReasons.length ? "warning" : "ok",
      changedFields,
      applyableFields,
      blockedFields: uniqueBlocked,
      restartRequired: restartReasons.length > 0,
      restartReasons,
      messages: uniqueMessages,
      applyContractSummary: applyContractParts.length ? applyContractParts.join(" + ") : "当前没有可应用字段",
      validateContractSummary: uniqueBlocked.length
        ? `config.validate 可显式调用；当前 GUI 本地预检 blocked=${uniqueBlocked.join(", ")}`
        : "config.validate 可显式调用；当前预览为 GUI 本地枚举与 runtime policy normalize",
      restartContractSummary: restartReasons.length
        ? `config.restart.report 可显式调用；当前 restart impact=${restartReasons.join(", ")}`
        : "config.restart.report 可显式调用；当前没有 restart impact",
    };
  }

  private applySummaryText(validation: SettingsDraftValidation): string {
    if (validation.changedFields.length > 0 && validation.applyableFields.length > 0 && validation.blockedFields.length > 0) {
      return validation.restartRequired
        ? "当前草稿可部分应用，且包含 restart impact；支持字段会通过 settings.update 落盘，unsupported 字段保留为本地草稿。"
        : "当前草稿可部分应用；支持字段会通过 settings.update 落盘，unsupported 字段保留为本地草稿。";
    }
    if (validation.level === "error") {
      return "当前草稿包含无法真实 apply 的字段，需先消除阻塞项。";
    }
    if (validation.changedFields.length === 0) {
      return "当前没有待应用配置。";
    }
    if (validation.restartRequired) {
      return "当前草稿可应用，但包含 restart impact，GUI 只做提示不伪造 restart。";
    }
    return "当前草稿可通过 settings.update 直接应用。";
  }

  private gatewayMethods(
    primary: GatewayMethodMetadata[] | undefined,
    fallback: GatewayMethodMetadata[] | undefined,
  ): GatewayMethodMetadata[] {
    if (Array.isArray(primary) && primary.length) {
      return primary;
    }
    if (Array.isArray(fallback)) {
      return fallback;
    }
    return [];
  }

  private normalizeRuntimePolicy(
    runtimePolicy: SettingsSnapshot["runtimePolicy"],
  ): RuntimePolicyForm {
    const raw = runtimePolicy ?? {};
    const networkRaw = String(raw.network_access ?? "").trim().toLowerCase();
    const network_access = networkRaw === "disabled" ? "disabled" : "enabled";
    const web_search_mode = this.normalizeWebSearchModeToken(raw.web_search_mode);
    return {
      approval_policy: String(raw.approval_policy || "on-request"),
      sandbox_mode: String(raw.sandbox_mode || "workspace-write"),
      web_search_mode,
      network_access,
    };
  }

  private clearConfigContractSummaryOverride() {
    this.configContractSummaryOverride = null;
    this.lastRemoteValidation = null;
    this.lastRestartReport = null;
  }

  private remoteValidationToDraftValidation(validation: ConfigValidationResult): SettingsDraftValidation {
    const blockedFields = validation.blockedFields.length
      ? validation.blockedFields
      : validation.blocked.map((item) => item.field);
    return {
      level: blockedFields.length ? "error" : validation.restart.required ? "warning" : "ok",
      changedFields: validation.changedFields,
      applyableFields: validation.applyableFields,
      blockedFields,
      restartRequired: validation.restart.required,
      restartReasons: validation.restart.reasons,
      messages: validation.warnings.length
        ? validation.warnings
        : validation.blocked.map((item) => item.reason),
      applyContractSummary: validation.applyPath.length
        ? validation.applyPath.map((item) => `${item.field} -> ${item.handler}`).join(" + ")
        : "当前没有可应用字段",
      validateContractSummary: blockedFields.length
        ? `config.validate 已返回 machine-readable blocked=${blockedFields.join(", ")}`
        : "config.validate 已返回 machine-readable validation result",
      restartContractSummary: validation.restart.required
        ? `config.restart.report: manual / ${validation.restart.reasons.join(", ")}`
        : "config.restart.report: no restart required",
    };
  }

  private remoteApplyToDraftValidation(result: ConfigApplyResult): SettingsDraftValidation {
    return this.remoteValidationToDraftValidation(result.validation);
  }

  private remoteValidationSummaryText(): string {
    if (!this.lastRemoteValidation) {
      return "尚未执行显式 config.validate";
    }
    return [
      `changed=${this.lastRemoteValidation.changedFields.length}`,
      `applyable=${this.lastRemoteValidation.applyableFields.length}`,
      `blocked=${this.lastRemoteValidation.blockedFields.length}`,
    ].join(" · ");
  }

  private remoteRestartReportSummaryText(): string {
    if (!this.lastRestartReport) {
      return "尚未拉取 config.restart.report";
    }
    return [
      `required=${this.lastRestartReport.required ? "yes" : "no"}`,
      `allowed=${this.lastRestartReport.allowed ? "yes" : "no"}`,
      `mode=${this.lastRestartReport.mode || "-"}`,
      this.lastRestartReport.reasons.length ? `reasons=${this.lastRestartReport.reasons.join(", ")}` : "reasons=none",
    ].join(" · ");
  }

  private remoteRestartReportHint(): string {
    if (!this.lastRestartReport) {
      return "可显式拉取 config.restart.report，查看 manual restart posture。";
    }
    return this.lastRestartReport.blockedReason || "当前 restart report 未返回额外 blocked reason。";
  }

  private normalizeWebSearchModeToken(value: unknown): string {
    const token = String(value ?? "").trim().toLowerCase();
    if (token === "off") {
      return "disabled";
    }
    if (token === "on") {
      return "cached";
    }
    if (token === "strict") {
      return "live";
    }
    return token || "live";
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "settings-page": SettingsPage;
  }
}
