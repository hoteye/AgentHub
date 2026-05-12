import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { BridgeClient, createMockBridgeClient } from "../../bridge/client.ts";
import "../../shared/components/operation-feedback-view.ts";
import {
  feedbackFromBridgeResponse,
  neutralFeedback,
  warningFeedback,
  type OperationFeedback,
} from "../../shared/state/operation-feedback.ts";
import type { ConnectorSummary, GatewayMethodMetadata, SettingsSnapshot } from "../../shared/types/bridge.ts";

type ChannelFilter = "all" | "webhook" | "polling" | "actions" | "approval" | "gateway" | "plugin_app";

type ChannelsRouteContextDetail =
  | {
      route: "auth";
      connectorKey?: string;
      connectorFilter?: "all" | "ingress" | "webhook" | "polling" | "actions" | "approval" | "gateway" | "plugin_app";
      source: "channels";
    }
  | {
      route: "plugins";
      connectorKey?: string;
      connectorFilter?: "all" | "degraded" | "actionable" | "gateway";
      source: "channels";
    }
  | {
      route: "settings";
      connectorKey?: string;
      connectorFilter?: "all" | "ingress" | "webhook" | "polling" | "actions" | "approval" | "gateway" | "plugin_app";
      source: "channels";
    }
  | {
      route: "approvals";
      connectorKey?: string;
      source: "channels";
    };

const CHANNEL_FILTERS = [
  "all",
  "webhook",
  "polling",
  "actions",
  "approval",
  "gateway",
  "plugin_app",
] as const satisfies readonly ChannelFilter[];

@customElement("channels-operator-page")
export class ChannelsOperatorPage extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .grid {
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
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

    .summary-grid,
    .meta-grid {
      display: grid;
      gap: 10px;
    }

    .summary-grid {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }

    .meta-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .summary-card,
    .meta-card,
    .item {
      border-radius: 14px;
      background: rgba(17, 32, 43, 0.74);
      border: 1px solid rgba(150, 186, 196, 0.1);
      padding: 12px 14px;
      display: grid;
      gap: 6px;
    }

    .item.active {
      border-color: rgba(111, 203, 193, 0.38);
      box-shadow: 0 0 0 1px rgba(111, 203, 193, 0.14) inset;
    }

    h2,
    h3,
    p {
      margin: 0;
    }

    h2 {
      color: #eef6fa;
      font-size: 18px;
    }

    h3 {
      color: #eef6fa;
      font-size: 15px;
    }

    .hint,
    .meta-value,
    .caption {
      color: #9bb1bc;
      font-size: 13px;
      line-height: 1.55;
    }

    .meta-label {
      color: #90a6b4;
      font-size: 11px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .summary-card strong {
      color: #f0f6fa;
      font-size: 20px;
    }

    .row,
    .actions,
    .filter-row,
    .pill-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }

    .row {
      justify-content: space-between;
    }

    .stack {
      display: grid;
      gap: 10px;
    }

    .pill,
    .filter-chip {
      border-radius: 999px;
      padding: 4px 9px;
      font-size: 12px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }

    .pill {
      background: rgba(234, 183, 94, 0.14);
      color: #ffd486;
      border: 1px solid transparent;
    }

    .pill.ready {
      background: rgba(76, 175, 139, 0.18);
      color: #9df0bc;
    }

    .pill.warning {
      background: rgba(234, 183, 94, 0.18);
      color: #ffd486;
    }

    .pill.error {
      background: rgba(218, 97, 97, 0.18);
      color: #ffabab;
    }

    .filter-chip {
      border: 1px solid rgba(150, 186, 196, 0.18);
      background: rgba(15, 31, 39, 0.82);
      color: #d7e6ee;
      cursor: pointer;
    }

    .filter-chip.active {
      border-color: rgba(111, 203, 193, 0.42);
      background: rgba(31, 80, 77, 0.88);
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

    .secondary {
      background: linear-gradient(135deg, #3b5160, #2c4050);
    }

    @media (max-width: 1120px) {
      .grid {
        grid-template-columns: 1fr;
      }

      .summary-grid,
      .meta-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }
  `;

  @property({ attribute: false }) bridgeClient: BridgeClient = createMockBridgeClient();
  @property({ type: String }) initialSelectedConnectorKey = "";
  @property({ type: String }) initialChannelFilter: ChannelFilter = "all";

  @state() private connectors: ConnectorSummary[] = [];
  @state() private settings: SettingsSnapshot | null = null;
  @state() private methods: GatewayMethodMetadata[] = [];
  @state() private selectedConnectorKey = "";
  @state() private channelFilter: ChannelFilter = "all";
  @state() private feedback: OperationFeedback = neutralFeedback("正在同步 channels operator surface。");

  connectedCallback(): void {
    super.connectedCallback();
    void this.load();
  }

  protected willUpdate(changedProperties: Map<PropertyKey, unknown>): void {
    if (changedProperties.has("initialSelectedConnectorKey") && this.initialSelectedConnectorKey.trim()) {
      this.selectedConnectorKey = this.initialSelectedConnectorKey.trim();
    }
    if (changedProperties.has("initialChannelFilter")) {
      this.channelFilter = this.normalizeFilter(this.initialChannelFilter);
    }
  }

  render() {
    const visibleConnectors = this.filteredConnectors();
    const selectedConnector =
      visibleConnectors.find((item) => item.connector_key === this.selectedConnectorKey)
      ?? visibleConnectors[0]
      ?? null;
    return html`
      <section class="grid">
        <article class="panel">
          <h2>Channels Inventory</h2>
          <p class="hint">
            当前严格复用 connector.list / settings.get / connect.capabilities，先把 ingress、action、
            approval posture 和 source 可见性从 auth/settings 中提成独立 operator surface。
          </p>
          <operation-feedback-view
            data-testid="channels-feedback"
            .feedback=${this.feedback}
          ></operation-feedback-view>
          <section class="summary-grid">
            ${this.renderSummaryCard("connectors", this.connectors.length, "visible inventory")}
            ${this.renderSummaryCard("ingress", this.ingressReadyCount(), "webhook or polling")}
            ${this.renderSummaryCard("approval", this.approvalRequiredCount(), "approval-gated")}
            ${this.renderSummaryCard("actions", this.totalActionTypes(), "action types")}
          </section>
          <div class="filter-row">
            ${CHANNEL_FILTERS.map(
              (filter) => html`
                <button
                  class="filter-chip ${this.channelFilter === filter ? "active" : ""}"
                  type="button"
                  data-testid=${`channels-filter-${filter}`}
                  @click=${() => this.handleFilterChange(filter)}
                >
                  ${filter}
                </button>
              `,
            )}
          </div>
          <div class="stack">
            ${visibleConnectors.map(
              (connector) => html`
                <section
                  class="item ${selectedConnector?.connector_key === connector.connector_key ? "active" : ""}"
                  data-testid="channels-connector-card"
                  @click=${() => this.selectConnector(connector.connector_key)}
                >
                  <div class="row">
                    <strong>${connector.display_name}</strong>
                    <span class="pill ${connector.health}">${connector.health}</span>
                  </div>
                  <div class="caption">${connector.connector_key} · ${connector.plugin_name}</div>
                  <div class="pill-row">
                    ${connector.supports_webhook ? html`<span class="pill">webhook</span>` : null}
                    ${connector.supports_polling ? html`<span class="pill">polling</span>` : null}
                    ${connector.supports_actions ? html`<span class="pill">actions</span>` : null}
                    ${connector.approval_required ? html`<span class="pill warning">approval</span>` : null}
                    <span class="pill ${connector.enabled ? "ready" : "warning"}">
                      ${connector.enabled ? "enabled" : "disabled"}
                    </span>
                  </div>
                  <div class="caption">
                    source=${connector.source_kind ?? "unknown"} · events=${connector.event_types?.length ?? 0}
                    · action types=${connector.action_types?.length ?? 0}
                  </div>
                </section>
              `,
            )}
            ${visibleConnectors.length === 0
              ? html`<div class="caption" data-testid="channels-empty">当前 filter 下没有可见 connector。</div>`
              : null}
          </div>
        </article>
        <aside class="panel">
          <h2>Operator Detail</h2>
          ${selectedConnector
            ? html`
                <div class="stack">
                  <section class="meta-grid">
                    ${this.renderMetaCard("Connector", selectedConnector.connector_key)}
                    ${this.renderMetaCard("Source", selectedConnector.source_kind ?? "unknown")}
                    ${this.renderMetaCard("Plugin", selectedConnector.plugin_name)}
                    ${this.renderMetaCard("Approval", selectedConnector.approval_required ? "required" : "not required")}
                    ${this.renderMetaCard("Provider", this.settings?.providerLabel ?? "-")}
                    ${this.renderMetaCard("Workspace trust", this.settings?.workspaceTrust ?? "unknown")}
                  </section>
                  <section class="item">
                    <h3>Channel Posture</h3>
                    <p class="hint">${this.describeConnector(selectedConnector)}</p>
                    <div class="pill-row">
                      ${selectedConnector.supports_webhook ? html`<span class="pill">webhook ingress</span>` : null}
                      ${selectedConnector.supports_polling ? html`<span class="pill">polling ingress</span>` : null}
                      ${selectedConnector.supports_actions ? html`<span class="pill">action egress</span>` : null}
                      <span class="pill">${selectedConnector.connector_kind}</span>
                    </div>
                  </section>
                  <section class="item">
                    <h3>Methods Visible</h3>
                    <p class="hint">
                      gateway methods=${this.methods.length} · connector/write surfaces 仍主要经由 auth/settings/plugins 展开，
                      本页只负责 inventory 与 next-hop。
                    </p>
                  </section>
                  <section class="item">
                    <h3>Next Hop</h3>
                    <div class="actions">
                      <button
                        data-testid="channels-open-auth"
                        type="button"
                        @click=${() => this.navigateTo({
                          route: "auth",
                          connectorKey: selectedConnector.connector_key,
                          connectorFilter: this.authFilterForConnector(selectedConnector),
                          source: "channels",
                        })}
                      >
                        打开 Auth
                      </button>
                      <button
                        class="secondary"
                        data-testid="channels-open-plugins"
                        type="button"
                        @click=${() => this.navigateTo({
                          route: "plugins",
                          connectorKey: selectedConnector.connector_key,
                          connectorFilter: this.pluginsFilterForConnector(selectedConnector),
                          source: "channels",
                        })}
                      >
                        打开 Plugins
                      </button>
                      <button
                        class="secondary"
                        data-testid="channels-open-settings"
                        type="button"
                        @click=${() => this.navigateTo({
                          route: "settings",
                          connectorKey: selectedConnector.connector_key,
                          connectorFilter: this.authFilterForConnector(selectedConnector),
                          source: "channels",
                        })}
                      >
                        打开 Settings
                      </button>
                      <button
                        class="secondary"
                        data-testid="channels-open-approvals"
                        type="button"
                        @click=${() => this.navigateTo({
                          route: "approvals",
                          connectorKey: selectedConnector.connector_key,
                          source: "channels",
                        })}
                      >
                        打开 Approvals
                      </button>
                    </div>
                  </section>
                </div>
              `
            : html`<p class="hint">选择一个 connector 查看 channel posture 与 next-hop。</p>`}
        </aside>
      </section>
    `;
  }

  private renderSummaryCard(label: string, value: number, detail: string) {
    return html`
      <section class="summary-card">
        <span>${label}</span>
        <strong>${value}</strong>
        <div class="caption">${detail}</div>
      </section>
    `;
  }

  private renderMetaCard(label: string, value: string) {
    return html`
      <section class="meta-card">
        <span class="meta-label">${label}</span>
        <span class="meta-value">${value}</span>
      </section>
    `;
  }

  private async load() {
    const [connectors, settings, capabilities] = await Promise.all([
      this.bridgeClient.connector.list(),
      this.bridgeClient.settings.get(),
      this.bridgeClient.gateway.connect.capabilities(),
    ]);
    this.connectors = connectors.data?.connectors ?? [];
    this.settings = settings.ok ? settings.data ?? null : null;
    this.methods = capabilities.data?.methods ?? [];
    if (!this.selectedConnectorKey && this.connectors[0]?.connector_key) {
      this.selectedConnectorKey = this.connectors[0].connector_key;
    }
    const failures = [connectors, settings, capabilities]
      .filter((response) => !response.ok)
      .map((response) => response.error?.message)
      .filter((item): item is string => Boolean(item));
    this.feedback = failures.length
      ? warningFeedback(`channels surface 部分降级: ${failures.join("；")}`)
      : neutralFeedback(`channels inventory 已同步: ${this.connectors.length} connectors`);
  }

  private filteredConnectors(): ConnectorSummary[] {
    return this.connectors.filter((connector) => {
      switch (this.channelFilter) {
        case "webhook":
          return connector.supports_webhook;
        case "polling":
          return connector.supports_polling;
        case "actions":
          return connector.supports_actions;
        case "approval":
          return Boolean(connector.approval_required);
        case "gateway":
          return connector.source_kind === "gateway";
        case "plugin_app":
          return connector.source_kind === "plugin_app";
        case "all":
        default:
          return true;
      }
    });
  }

  private ingressReadyCount(): number {
    return this.connectors.filter((item) => item.supports_webhook || item.supports_polling).length;
  }

  private approvalRequiredCount(): number {
    return this.connectors.filter((item) => item.approval_required).length;
  }

  private totalActionTypes(): number {
    return this.connectors.reduce((sum, item) => sum + (item.action_types?.length ?? 0), 0);
  }

  private describeConnector(connector: ConnectorSummary): string {
    const ingress = [
      connector.supports_webhook ? "webhook" : "",
      connector.supports_polling ? "polling" : "",
    ].filter(Boolean);
    const egress = connector.supports_actions ? "actions enabled" : "read-mostly";
    const approval = connector.approval_required ? "approval-gated" : "direct";
    return `${connector.display_name} 当前以 ${ingress.join(" / ") || "no-ingress"} ingress 为主，${egress}，${approval}，source=${connector.source_kind ?? "unknown"}。`;
  }

  private authFilterForConnector(connector: ConnectorSummary): ChannelsRouteContextDetail["connectorFilter"] {
    if (connector.supports_webhook) {
      return "webhook";
    }
    if (connector.supports_polling) {
      return "polling";
    }
    if (connector.supports_actions) {
      return "actions";
    }
    if (connector.approval_required) {
      return "approval";
    }
    return connector.source_kind === "gateway" ? "gateway" : "plugin_app";
  }

  private pluginsFilterForConnector(connector: ConnectorSummary): "all" | "degraded" | "actionable" | "gateway" {
    if (connector.source_kind === "gateway") {
      return "gateway";
    }
    if (connector.supports_actions || connector.approval_required) {
      return "actionable";
    }
    return "all";
  }

  private normalizeFilter(value: string): ChannelFilter {
    return (CHANNEL_FILTERS as readonly string[]).includes(value) ? (value as ChannelFilter) : "all";
  }

  private handleFilterChange(filter: ChannelFilter) {
    this.channelFilter = filter;
  }

  private selectConnector(connectorKey: string) {
    this.selectedConnectorKey = connectorKey;
  }

  private navigateTo(detail: ChannelsRouteContextDetail) {
    this.dispatchEvent(
      new CustomEvent<ChannelsRouteContextDetail>("navigate-control-context", {
        detail,
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "channels-operator-page": ChannelsOperatorPage;
  }
}
