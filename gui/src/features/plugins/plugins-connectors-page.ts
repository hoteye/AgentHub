import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { GuiRouteId } from "../../routes.ts";

import { BridgeClient, createMockBridgeClient } from "../../bridge/client.ts";
import "../../shared/components/operation-feedback-view.ts";
import { summarizeBridgeCollection } from "../../shared/state/health-summary.ts";
import {
  errorFeedback,
  feedbackFromBridgeResponse,
  neutralFeedback,
  type OperationFeedback,
  warningFeedback,
} from "../../shared/state/operation-feedback.ts";
import type { BridgeEvent, ConnectorSummary, PluginSummary } from "../../shared/types/bridge.ts";

type ConnectorFilter = "all" | "degraded" | "actionable" | "gateway";
const CONNECTOR_FILTERS = ["all", "degraded", "actionable", "gateway"] as const satisfies readonly ConnectorFilter[];

type PluginsAuthRouteContextDetail = {
  route: "auth";
  connectorKey?: string;
  connectorFilter?: "all" | "ingress" | "approval" | "gateway" | "plugin_app";
  source: "plugins-connectors";
};

type PluginsSettingsRouteContextDetail = {
  route: "settings";
  connectorKey?: string;
  connectorFilter?: "all" | "ingress" | "approval" | "gateway" | "plugin_app";
  source: "plugins-connectors";
};

type PluginsApprovalsRouteContextDetail = {
  route: "approvals";
  connectorKey?: string;
  source: "plugins-connectors";
};

@customElement("plugins-connectors-page")
export class PluginsConnectorsPage extends LitElement {
  private unsubscribeBridge: (() => void) | null = null;

  static styles = css`
    :host {
      display: block;
    }

    .grid {
      display: grid;
      grid-template-columns: 1fr 0.9fr;
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

    .item.active {
      border-color: rgba(111, 203, 193, 0.38);
      box-shadow: 0 0 0 1px rgba(111, 203, 193, 0.14) inset;
    }

    .summary-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }

    .summary-card {
      border-radius: 12px;
      border: 1px solid rgba(150, 186, 196, 0.16);
      background: rgba(8, 21, 30, 0.76);
      padding: 10px 12px;
      display: grid;
      gap: 4px;
    }

    .summary-card strong {
      font-size: 18px;
      color: #f1f7fa;
    }

    .summary-card span {
      font-size: 12px;
      color: #8ea7b4;
      text-transform: uppercase;
      letter-spacing: 0.08em;
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

    .pill {
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      background: rgba(234, 183, 94, 0.14);
      color: #ffd486;
    }

    .pill.ready {
      background: rgba(77, 192, 125, 0.18);
      color: #8ff0b0;
    }

    .pill.warning {
      background: rgba(234, 183, 94, 0.16);
      color: #ffd486;
    }

    .pill.error {
      background: rgba(229, 93, 93, 0.18);
      color: #ff9e9e;
    }

    .actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .stack {
      display: grid;
      gap: 10px;
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

    .meta-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    .meta-card {
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

    .meta-value {
      color: #e4f0f6;
      font-size: 14px;
      line-height: 1.5;
      word-break: break-word;
    }

    .empty {
      padding: 10px 0;
      color: #8da4b0;
      font-size: 13px;
    }

    .btn-secondary {
      background: linear-gradient(135deg, #3b5160, #2c4050);
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
  `;

  @property({ attribute: false }) bridgeClient: BridgeClient = createMockBridgeClient();
  @property({ type: String }) initialSelectedConnectorKey = "";
  @property({ type: String }) initialConnectorFilter: ConnectorFilter = "all";
  @property({ type: String }) initialContextSource = "";

  @state() private plugins: PluginSummary[] = [];
  @state() private connectors: ConnectorSummary[] = [];
  @state() private pluginFeedback: OperationFeedback = neutralFeedback("选择插件操作后会在这里显示结果。");
  @state() private connectorFeedback: OperationFeedback = neutralFeedback("正在同步连接器状态");
  @state() private selectedConnectorKey = "";
  @state() private connectorFilter: ConnectorFilter = "all";

  connectedCallback(): void {
    super.connectedCallback();
    void this.loadData();
    this.unsubscribeBridge = this.bridgeClient.subscribe((event) => {
      this.handleBridgeEvent(event);
    });
  }

  disconnectedCallback(): void {
    this.unsubscribeBridge?.();
    this.unsubscribeBridge = null;
    super.disconnectedCallback();
  }

  protected willUpdate(changedProperties: Map<PropertyKey, unknown>): void {
    if (changedProperties.has("initialConnectorFilter")) {
      this.connectorFilter = this.normalizeConnectorFilter(this.initialConnectorFilter);
    }
    if (changedProperties.has("initialSelectedConnectorKey")) {
      this.selectedConnectorKey = this.initialSelectedConnectorKey.trim();
    }
  }

  render() {
    const filteredConnectors = this.filteredConnectors();
    const selectedConnector = this.selectedConnector(filteredConnectors);
    return html`
      <section class="grid">
        <article class="panel">
          <div>
            <h2>插件</h2>
            <p class="hint">展示 plugin lifecycle、启停动作和健康度，优先给 operator visibility。</p>
          </div>
          <section class="summary-grid" data-testid="plugin-summary">
            <article class="summary-card">
              <span>Plugins</span>
              <strong>${this.plugins.length}</strong>
            </article>
            <article class="summary-card">
              <span>Enabled</span>
              <strong>${this.plugins.filter((item) => item.enabled).length}</strong>
            </article>
            <article class="summary-card">
              <span>Degraded</span>
              <strong>${this.plugins.filter((item) => item.health !== "ready").length}</strong>
            </article>
          </section>
          <operation-feedback-view
            data-testid="plugin-feedback"
            variant="stack"
            .surface=${true}
            .feedback=${this.pluginFeedback}
          ></operation-feedback-view>
          ${this.plugins.map(
            (plugin) => html`
              <section class="item">
                <div class="row">
                  <strong>${plugin.title}</strong>
                  <span class="pill ${plugin.health}">${plugin.health}</span>
                </div>
                <span class="hint">${plugin.plugin_id}</span>
                <span class="hint">lifecycle: ${plugin.enabled ? "enabled" : "disabled"}</span>
                <div class="actions">
                  <button type="button" data-testid="plugin-toggle" @click=${() => this.togglePlugin(plugin)}>
                    ${plugin.enabled ? "禁用" : "启用"}
                  </button>
                  <button
                    type="button"
                    class="btn-secondary"
                    data-testid="plugin-reload"
                    @click=${() => this.reloadPlugin(plugin)}
                  >
                    重载
                  </button>
                </div>
              </section>
            `,
          )}
        </article>
        <article class="panel">
          <div>
            <h2>连接器</h2>
            <p class="hint">展示 connector registry、状态和错误摘要，并补 operator 侧的能力/来源/risk drill-down。</p>
            ${this.initialContextSource
              ? html`
                  <p class="hint" data-testid="connector-context-banner">
                    handoff=${this.initialContextSource} · filter=${this.connectorFilter} · connector=${this.selectedConnectorKey || "-"}
                  </p>
                `
              : null}
          </div>
          <section class="summary-grid" data-testid="connector-summary">
            <article class="summary-card">
              <span>Connectors</span>
              <strong>${this.connectors.length}</strong>
            </article>
            <article class="summary-card">
              <span>Enabled</span>
              <strong>${this.connectors.filter((item) => item.enabled).length}</strong>
            </article>
            <article class="summary-card">
              <span>Error</span>
              <strong>${this.connectors.filter((item) => item.health === "error").length}</strong>
            </article>
          </section>
          <operation-feedback-view
            data-testid="connector-feedback"
            variant="stack"
            .surface=${true}
            .feedback=${this.connectorFeedback}
          ></operation-feedback-view>
          <div class="filter-row" data-testid="connector-filter-row">
            ${this.renderFilterChip("all", `全部 ${this.connectors.length}`)}
            ${this.renderFilterChip("degraded", `异常 ${this.connectors.filter((item) => item.health !== "ready").length}`)}
            ${this.renderFilterChip("actionable", `可写 ${this.connectors.filter((item) => item.supports_actions).length}`)}
            ${this.renderFilterChip("gateway", `Gateway ${this.connectors.filter((item) => item.source_kind === "gateway").length}`)}
          </div>
          <div class="meta-grid" data-testid="connector-channel-inventory">
            <div class="meta-card">
              <span class="meta-label">Webhook Ingress</span>
              <span class="meta-value">${String(this.connectorIngressCount("webhook"))}</span>
            </div>
            <div class="meta-card">
              <span class="meta-label">Polling Ingress</span>
              <span class="meta-value">${String(this.connectorIngressCount("polling"))}</span>
            </div>
            <div class="meta-card">
              <span class="meta-label">Action Paths</span>
              <span class="meta-value">${String(this.connectors.filter((item) => item.supports_actions).length)}</span>
            </div>
            <div class="meta-card">
              <span class="meta-label">Approval Required</span>
              <span class="meta-value">${String(this.connectors.filter((item) => item.approval_required).length)}</span>
            </div>
            <div class="meta-card">
              <span class="meta-label">Source Split</span>
              <span class="meta-value">${this.connectorSourceSummary()}</span>
            </div>
            <div class="meta-card">
              <span class="meta-label">Operator Note</span>
              <span class="meta-value">这一块承接 auth handoff，先表达 ingress/source/action 风险，不发明独立 channels contract。</span>
            </div>
          </div>
          <div class="stack">
            ${filteredConnectors.length === 0
              ? html`<div class="empty">当前筛选条件下没有连接器。</div>`
              : filteredConnectors.map(
            (connector) => html`
              <section
                class="item ${selectedConnector?.connector_key === connector.connector_key ? "active" : ""}"
                data-testid=${`connector-item-${connector.connector_key}`}
              >
                <div class="row">
                  <strong>${connector.display_name}</strong>
                  <span class="pill ${connector.health}">${connector.health}</span>
                </div>
                <span class="hint">${connector.connector_key} · ${connector.connector_kind}</span>
                <span class="hint">plugin=${connector.plugin_name}</span>
                <span class="hint">
                  source=${connector.source_kind ?? "plugin"} · lifecycle=${connector.enabled ? "enabled" : "disabled"}
                </span>
                <span class="hint">
                  capabilities:
                  ${[
                    connector.supports_webhook ? "webhook" : "",
                    connector.supports_polling ? "polling" : "",
                    connector.supports_actions ? "actions" : "",
                  ]
                    .filter(Boolean)
                    .join(", ") || "none"}
                </span>
                ${connector.event_types?.length
                  ? html`<span class="hint">event types: ${connector.event_types.join(", ")}</span>`
                  : null}
                ${connector.action_types?.length
                  ? html`<span class="hint">action types: ${connector.action_types.join(", ")}</span>`
                  : null}
                <div class="actions">
                  <button
                    type="button"
                    class="btn-secondary"
                    data-testid=${`connector-select-${connector.connector_key}`}
                    @click=${() => this.selectConnector(connector.connector_key)}
                  >
                    查看 Operator Detail
                  </button>
                </div>
              </section>
            `,
          )}
          </div>
          <section class="item" data-testid="connector-detail-panel">
            ${selectedConnector
              ? html`
                  <div class="row">
                    <strong>${selectedConnector.display_name}</strong>
                    <span class="pill ${selectedConnector.health}">${selectedConnector.health}</span>
                  </div>
                  <span class="hint">
                    ${selectedConnector.connector_key} · ${selectedConnector.plugin_name} · ${selectedConnector.connector_kind}
                  </span>
                  <div class="meta-grid">
                    <div class="meta-card">
                      <span class="meta-label">Source</span>
                      <span class="meta-value">${selectedConnector.source_kind ?? "plugin"}</span>
                    </div>
                    <div class="meta-card">
                      <span class="meta-label">Lifecycle</span>
                      <span class="meta-value">${selectedConnector.enabled ? "enabled" : "disabled"}</span>
                    </div>
                    <div class="meta-card">
                      <span class="meta-label">Event Types</span>
                      <span class="meta-value">${String(selectedConnector.event_types?.length ?? 0)}</span>
                    </div>
                    <div class="meta-card">
                      <span class="meta-label">Action Types</span>
                      <span class="meta-value">${String(selectedConnector.action_types?.length ?? 0)}</span>
                    </div>
                    <div class="meta-card">
                      <span class="meta-label">Approval</span>
                      <span class="meta-value">${selectedConnector.approval_required ? "required" : "direct"}</span>
                    </div>
                    <div class="meta-card">
                      <span class="meta-label">Ingress</span>
                      <span class="meta-value">${this.connectorIngressSummary(selectedConnector)}</span>
                    </div>
                  </div>
                  <span class="hint" data-testid="connector-detail-capabilities">
                    capabilities:
                    ${[
                      selectedConnector.supports_webhook ? "webhook" : "",
                      selectedConnector.supports_polling ? "polling" : "",
                      selectedConnector.supports_actions ? "actions" : "",
                    ]
                      .filter(Boolean)
                      .join(", ") || "none"}
                  </span>
                  <span class="hint" data-testid="connector-detail-operator-note">
                    ${this.connectorOperatorNote(selectedConnector)}
                  </span>
                  <div class="actions">
                    <button
                      type="button"
                      class="btn-secondary"
                      data-testid="connector-open-auth-surface"
                      @click=${() => this.navigateToAuthConnectorContext({
                        route: "auth",
                        connectorKey: selectedConnector.connector_key,
                        connectorFilter: this.authRouteFilterForConnector(selectedConnector),
                        source: "plugins-connectors",
                      })}
                    >
                      打开 Auth / Scope
                    </button>
                    <button
                      type="button"
                      class="btn-secondary"
                      data-testid="connector-open-settings-surface"
                      @click=${() => this.navigateToSettingsConnectorContext({
                        route: "settings",
                        connectorKey: selectedConnector.connector_key,
                        connectorFilter: this.authRouteFilterForConnector(selectedConnector),
                        source: "plugins-connectors",
                      })}
                    >
                      打开设置
                    </button>
                    ${selectedConnector.approval_required
                      ? html`
                          <button
                            type="button"
                            class="btn-secondary"
                            data-testid="connector-open-approvals-surface"
                            @click=${() => this.navigateToApprovalsConnectorContext({
                              route: "approvals",
                              connectorKey: selectedConnector.connector_key,
                              source: "plugins-connectors",
                            })}
                          >
                            打开审批与审计
                          </button>
                        `
                      : null}
                  </div>
                `
              : html`<span class="hint">选择一个连接器后在这里查看 operator detail。</span>`}
          </section>
        </article>
      </section>
    `;
  }

  private async loadData(pluginFeedbackOverride?: string) {
    const [plugins, connectors] = await Promise.all([
      this.bridgeClient.plugin.list(),
      this.bridgeClient.connector.list(),
    ]);
    this.plugins = plugins.data?.plugins ?? [];
    this.connectors = connectors.data?.connectors ?? [];
    const pluginSummary = summarizeBridgeCollection(
      plugins,
      this.plugins,
      (item) => item.health,
      {
        label: "插件",
        emptyDetail: "当前没有已加载插件",
      },
    );
    const connectorSummary = summarizeBridgeCollection(
      connectors,
      this.connectors,
      (item) => item.health,
      {
        label: "连接器",
        emptyDetail: "当前没有注册连接器",
      },
    );
    const nextPluginFeedback =
      pluginSummary.level === "error"
        ? errorFeedback(pluginSummary.detail)
        : pluginSummary.level === "warning"
          ? warningFeedback(pluginSummary.detail)
          : neutralFeedback(pluginSummary.detail);
    this.pluginFeedback = pluginFeedbackOverride
      ? neutralFeedback(`${pluginFeedbackOverride} · ${pluginSummary.detail}`)
      : nextPluginFeedback;
    this.connectorFeedback =
      connectorSummary.level === "error"
        ? errorFeedback(connectorSummary.detail)
        : connectorSummary.level === "warning"
          ? warningFeedback(connectorSummary.detail)
          : neutralFeedback(connectorSummary.detail);
    const selectedStillExists = this.connectors.some((item) => item.connector_key === this.selectedConnectorKey);
    if (!selectedStillExists) {
      this.selectedConnectorKey = this.connectors[0]?.connector_key ?? "";
    }
  }

  private async togglePlugin(plugin: PluginSummary) {
    const response = plugin.enabled
      ? await this.bridgeClient.plugin.disable({ plugin_id: plugin.plugin_id })
      : await this.bridgeClient.plugin.enable({ plugin_id: plugin.plugin_id });
    this.pluginFeedback = feedbackFromBridgeResponse(response, {
      successMessage: `${plugin.title}${plugin.enabled ? "已禁用" : "已启用"}`,
      errorMessage: `${plugin.title}${plugin.enabled ? "禁用失败" : "启用失败"}`,
    });
    if (!response.ok) {
      return;
    }
    this.plugins = this.plugins.map((item) =>
      item.plugin_id === plugin.plugin_id ? { ...item, enabled: !item.enabled } : item,
    );
    await this.loadData();
  }

  private async reloadPlugin(plugin: PluginSummary) {
    const response = await this.bridgeClient.plugin.reload({ plugin_id: plugin.plugin_id });
    this.pluginFeedback = feedbackFromBridgeResponse(response, {
      successMessage: `${plugin.title}已重载`,
      errorMessage: `${plugin.title}重载失败`,
    });
    if (!response.ok) {
      return;
    }
    await this.loadData();
  }

  private filteredConnectors(): ConnectorSummary[] {
    if (this.connectorFilter === "degraded") {
      return this.connectors.filter((item) => item.health !== "ready");
    }
    if (this.connectorFilter === "actionable") {
      return this.connectors.filter((item) => item.supports_actions);
    }
    if (this.connectorFilter === "gateway") {
      return this.connectors.filter((item) => item.source_kind === "gateway");
    }
    return this.connectors;
  }

  private selectedConnector(connectors: ConnectorSummary[]): ConnectorSummary | null {
    if (!connectors.length) {
      return null;
    }
    return connectors.find((item) => item.connector_key === this.selectedConnectorKey) ?? connectors[0];
  }

  private renderFilterChip(filter: ConnectorFilter, label: string) {
    return html`
      <button
        type="button"
        class="filter-chip ${this.connectorFilter === filter ? "active" : ""}"
        data-testid=${`connector-filter-${filter}`}
        @click=${() => this.applyConnectorFilter(filter)}
      >
        ${label}
      </button>
    `;
  }

  private applyConnectorFilter(filter: ConnectorFilter) {
    this.connectorFilter = filter;
    const nextSelected = this.filteredConnectors()[0];
    this.selectedConnectorKey = nextSelected?.connector_key ?? "";
  }

  private selectConnector(connectorKey: string) {
    this.selectedConnectorKey = connectorKey;
  }

  private connectorOperatorNote(connector: ConnectorSummary): string {
    if (!connector.enabled) {
      return "该连接器当前未启用，operator 侧只能做可见性确认，后续需要补 auth / apply / restart contract。";
    }
    if (connector.health === "error") {
      return "该连接器处于 error，优先检查上游认证、source 侧可达性和最近 audit / workflow 失败链路。";
    }
    if (connector.source_kind === "plugin_app") {
      return "该连接器来自 plugin app source，当前更适合作为 external auth / channel inventory 入口，再与插件面联动确认配置与生命周期。";
    }
    if (connector.approval_required) {
      return "该连接器具备外部动作能力，且当前写路径会进入 approval 链路，应与 approvals / audit / trace 一起收口。";
    }
    if (connector.supports_actions) {
      return "该连接器具备外部动作能力，应与 approvals / audit / trace 语义统一收口。";
    }
    return "该连接器当前以事件可见性为主，后续可继续补 external auth、channels 和 node-level operator contract。";
  }

  private connectorIngressCount(kind: "webhook" | "polling"): number {
    if (kind === "webhook") {
      return this.connectors.filter((item) => item.supports_webhook).length;
    }
    return this.connectors.filter((item) => item.supports_polling).length;
  }

  private connectorSourceSummary(): string {
    const gatewayCount = this.connectors.filter((item) => item.source_kind === "gateway").length;
    const appCount = this.connectors.length - gatewayCount;
    return `gateway=${gatewayCount}, app=${appCount}`;
  }

  private connectorIngressSummary(connector: ConnectorSummary): string {
    return [
      connector.supports_webhook ? "webhook" : "",
      connector.supports_polling ? "polling" : "",
    ]
      .filter(Boolean)
      .join(", ") || "no ingress";
  }

  private authRouteFilterForConnector(connector: ConnectorSummary): PluginsAuthRouteContextDetail["connectorFilter"] {
    if (connector.source_kind === "gateway") {
      return "gateway";
    }
    if (connector.supports_webhook || connector.supports_polling) {
      return "ingress";
    }
    return "approval";
  }

  private normalizeConnectorFilter(filter: string): ConnectorFilter {
    return CONNECTOR_FILTERS.includes(filter as ConnectorFilter) ? (filter as ConnectorFilter) : "all";
  }

  private navigateToAuthConnectorContext(detail: PluginsAuthRouteContextDetail) {
    this.dispatchEvent(
      new CustomEvent<PluginsAuthRouteContextDetail>("navigate-control-context", {
        detail,
        bubbles: true,
        composed: true,
      }),
    );
  }

  private navigateToSettingsConnectorContext(detail: PluginsSettingsRouteContextDetail) {
    this.dispatchEvent(
      new CustomEvent<PluginsSettingsRouteContextDetail>("navigate-control-context", {
        detail,
        bubbles: true,
        composed: true,
      }),
    );
  }

  private navigateToApprovalsConnectorContext(detail: PluginsApprovalsRouteContextDetail) {
    this.dispatchEvent(
      new CustomEvent<PluginsApprovalsRouteContextDetail>("navigate-control-context", {
        detail,
        bubbles: true,
        composed: true,
      }),
    );
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

  private handleBridgeEvent(event: BridgeEvent<Record<string, unknown>>) {
    if (event.kind !== "plugin_state_changed") {
      return;
    }
    void this.loadData(event.summary || "插件状态已变化，正在刷新 registry。");
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "plugins-connectors-page": PluginsConnectorsPage;
  }
}
