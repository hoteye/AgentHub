import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { BridgeClient, createMockBridgeClient } from "../../bridge/client.ts";
import type { NodesInventorySnapshot, PairingPendingRef } from "../../shared/types/bridge.ts";
import "../../shared/components/operation-feedback-view.ts";
import {
  feedbackFromBridgeResponse,
  neutralFeedback,
  warningFeedback,
  type OperationFeedback,
} from "../../shared/state/operation-feedback.ts";

type RouteTarget = "settings" | "auth" | "channels" | "approvals" | "sessions";

type NodesControlContextDetail = {
  route: "approvals" | "sessions";
  traceId: string;
  approvalId?: string;
  timelineScope?: "approvalTickets";
  source: "nodes-pairing";
};

type CapabilityLevel = "ready" | "warning" | "unknown";

type NodeCapabilitySummary = {
  browser: CapabilityLevel;
  workflows: CapabilityLevel;
  approvals: CapabilityLevel;
  connectors: CapabilityLevel;
};

type NodePairingSummary = {
  pendingPairing: number;
  pendingApprovals: number;
  hasNativeContract: boolean;
  source: string;
  summary: string;
  pendingRefs: PairingPendingRef[];
};

type NodeEntry = {
  id: string;
  name: string;
  status: string;
  localEnabled: boolean;
  remoteEnabled: boolean;
  trustLevel: string;
  kind: string;
  capability: NodeCapabilitySummary;
  pairing: NodePairingSummary;
  raw: Record<string, unknown>;
};

type NodesListResponseData = {
  nodes?: unknown[];
  devices?: unknown[];
  summary?: Record<string, unknown>;
  source?: Record<string, unknown>;
};

@customElement("nodes-devices-page")
export class NodesDevicesPage extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .grid {
      display: grid;
      grid-template-columns: 1.05fr 0.95fr;
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

    .summary-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }

    .summary-card,
    .item,
    .meta-card {
      border-radius: 14px;
      background: rgba(17, 32, 43, 0.74);
      border: 1px solid rgba(150, 186, 196, 0.1);
      padding: 12px 14px;
      display: grid;
      gap: 6px;
    }

    .item.active {
      border-color: rgba(111, 203, 193, 0.42);
      box-shadow: 0 0 0 1px rgba(111, 203, 193, 0.14) inset;
    }

    .meta-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
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
    .caption,
    .meta-value {
      color: #9db3be;
      font-size: 13px;
      line-height: 1.55;
    }

    .meta-label {
      color: #8ea6b3;
      font-size: 11px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .summary-card strong {
      color: #f1f6fa;
      font-size: 20px;
    }

    .row,
    .pill-row,
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }

    .row {
      justify-content: space-between;
    }

    .stack {
      display: grid;
      gap: 10px;
    }

    .pill {
      border-radius: 999px;
      padding: 4px 9px;
      font-size: 12px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      background: rgba(234, 183, 94, 0.14);
      color: #ffd486;
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
      color: #ffbaba;
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

  @state() private nodes: NodeEntry[] = [];
  @state() private selectedNodeId = "";
  @state() private summarySource = "";
  @state() private feedback: OperationFeedback = neutralFeedback("正在同步 nodes / devices surface。");

  connectedCallback(): void {
    super.connectedCallback();
    void this.load();
  }

  render() {
    const selected = this.selectedNode();
    return html`
      <section class="grid">
        <article class="panel">
          <h2>Nodes / Devices Inventory</h2>
          <p class="hint">
            当前只消费 nodes.list 只读 contract，不发明 node control 写接口；用于可视化 local node、remote posture、
            pairing heuristic 和 capability 摘要。
          </p>
          <operation-feedback-view
            data-testid="nodes-feedback"
            .feedback=${this.feedback}
          ></operation-feedback-view>
          <section class="summary-grid">
            ${this.renderSummaryCard("nodes", this.nodes.length, "visible inventory", "total")}
            ${this.renderSummaryCard("local", this.localNodeCount(), "local runtime", "local")}
            ${this.renderSummaryCard("remote", this.remoteNodeCount(), "remote or device", "remote")}
            ${this.renderSummaryCard("pairing", this.pendingPairingTotal(), "pending heuristic", "pairing")}
          </section>
          <div class="stack">
            ${this.nodes.map(
              (node) => html`
                <section
                  class="item ${selected?.id === node.id ? "active" : ""}"
                  data-testid=${`nodes-card-${this.testIdPart(node.id)}`}
                  @click=${() => this.selectNode(node.id)}
                >
                  <div class="row">
                    <strong>${node.name}</strong>
                    <span class="pill ${this.statusPillClass(node.status)}">${node.status || "unknown"}</span>
                  </div>
                  <div class="caption">${node.id} · kind=${node.kind || "unknown"} · trust=${node.trustLevel || "unknown"}</div>
                  <div class="pill-row">
                    <span class="pill ${node.localEnabled ? "ready" : "warning"}">${node.localEnabled ? "local on" : "local off"}</span>
                    <span class="pill ${node.remoteEnabled ? "warning" : "ready"}">${node.remoteEnabled ? "remote on" : "remote off"}</span>
                    <span class="pill warning">pairing ${node.pairing.pendingPairing}</span>
                    <span class="pill ${node.pairing.hasNativeContract ? "ready" : "warning"}">
                      ${node.pairing.hasNativeContract ? "native" : "heuristic"}
                    </span>
                  </div>
                </section>
              `,
            )}
            ${this.nodes.length === 0
              ? html`
                  <div class="caption" data-testid="nodes-empty">
                    暂无 nodes inventory；可回 settings/auth 检查 access posture 与 gateway contract。
                  </div>
                `
              : null}
          </div>
        </article>

        <aside class="panel">
          <h2>Node Operator Detail</h2>
          ${selected
            ? html`
                <div class="stack">
                  <section class="meta-grid" data-testid="nodes-local-summary">
                    ${this.renderMetaCard("Node", selected.name)}
                    ${this.renderMetaCard("ID", selected.id)}
                    ${this.renderMetaCard("Local runtime", selected.localEnabled ? "enabled" : "disabled")}
                    ${this.renderMetaCard("Summary source", this.summarySource || "nodes.list")}
                  </section>

                  <section class="item" data-testid="nodes-remote-posture">
                    <h3>Remote / Device Posture</h3>
                    <p class="hint">
                      remote=${selected.remoteEnabled ? "on" : "off"} · local=${selected.localEnabled ? "on" : "off"} ·
                      trust=${selected.trustLevel || "unknown"} · status=${selected.status || "unknown"}
                    </p>
                  </section>

                  <section class="item" data-testid="nodes-pairing-summary">
                    <h3>Pairing Heuristic</h3>
                    <p class="hint">
                      pendingPairing=${selected.pairing.pendingPairing} · pendingApprovals=${selected.pairing.pendingApprovals}
                      · pendingRefs=${selected.pairing.pendingRefs.length} · ${selected.pairing.hasNativeContract
                        ? "native-contract"
                        : "heuristic-only"}
                    </p>
                    <p class="caption">
                      source=${selected.pairing.source || "nodes.list"}${selected.pairing.summary ? ` · ${selected.pairing.summary}` : ""}
                    </p>
                    <div class="stack" data-testid="nodes-pairing-pending-refs">
                      ${this.renderNodePairingPendingRefs(selected.pairing.pendingRefs)}
                    </div>
                  </section>

                  <section class="item" data-testid="nodes-capability-summary">
                    <h3>Capability Summary</h3>
                    <p class="hint">
                      browser=${selected.capability.browser} · workflows=${selected.capability.workflows}
                      · approvals=${selected.capability.approvals} · connectors=${selected.capability.connectors}
                    </p>
                  </section>

                  <section class="item">
                    <h3>Next Hop</h3>
                    <div class="actions">
                      <button
                        type="button"
                        data-testid="nodes-open-settings"
                        @click=${() => this.emitRouteChange("settings")}
                      >
                        打开 Settings
                      </button>
                      <button
                        type="button"
                        class="secondary"
                        data-testid="nodes-open-auth"
                        @click=${() => this.emitRouteChange("auth")}
                      >
                        打开 Auth
                      </button>
                      <button
                        type="button"
                        class="secondary"
                        data-testid="nodes-open-channels"
                        @click=${() => this.emitRouteChange("channels")}
                      >
                        打开 Channels
                      </button>
                      <button
                        type="button"
                        class="secondary"
                        data-testid="nodes-open-approvals"
                        @click=${() => this.emitRouteChange("approvals")}
                      >
                        打开 Approvals
                      </button>
                    </div>
                  </section>
                </div>
              `
            : html`<p class="hint">选择一个 node 后查看 local/remote/pairing/capability 与 next-hop。</p>`}
        </aside>
      </section>
    `;
  }

  private renderSummaryCard(label: string, value: number, detail: string, key: string) {
    return html`
      <section class="summary-card" data-testid=${`nodes-summary-${key}`}>
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
    const response = await this.bridgeClient.gateway.nodes.list() as {
      ok: boolean;
      data: NodesInventorySnapshot | null;
      error: { message: string } | null;
    };
    if (!response.ok) {
      this.feedback = feedbackFromBridgeResponse(response as never, {
        successMessage: "nodes.list 已加载",
        errorMessage: "nodes.list 加载失败",
      });
      this.nodes = [];
      this.selectedNodeId = "";
      this.summarySource = "nodes.list";
      return;
    }
    const data = (response.data ?? {}) as unknown as NodesListResponseData;
    const rawItems = this.normalizeNodesArray(data);
    this.nodes = rawItems.map((item, index) => this.normalizeNode(item, index)).filter((item) => item.id.trim());
    this.summarySource =
      textOf((asRecord(data.source) ?? {})["contract"])
      || textOf((asRecord(data.summary) ?? {})["source"])
      || "nodes.list";
    if (!this.nodes.length) {
      this.feedback = warningFeedback("nodes.list 响应为空，当前只能展示空 inventory。");
      this.selectedNodeId = "";
      return;
    }
    const selectedStillExists = this.nodes.some((item) => item.id === this.selectedNodeId);
    if (!selectedStillExists) {
      this.selectedNodeId = this.nodes[0].id;
    }
    this.feedback = neutralFeedback(`nodes inventory 已同步：${this.nodes.length} nodes/devices`);
  }

  private normalizeNodesArray(data: NodesListResponseData): Record<string, unknown>[] {
    const nodes = toRecordArray(data.nodes);
    if (nodes.length) {
      return nodes;
    }
    return toRecordArray(data.devices);
  }

  private normalizeNode(raw: Record<string, unknown>, index: number): NodeEntry {
    const accessRecord = asRecord(raw.access) ?? {};
    const pairingRecord = asRecord(raw.pairing) ?? {};
    const capabilityRecord = asRecord(raw.capabilities) ?? {};
    const authRecord = asRecord(raw.auth) ?? {};
    const activityRecord = asRecord(raw.activity) ?? {};
    const runtimeRecord = asRecord(raw.runtime) ?? {};
    const id = textFirst(raw.node_id, raw.nodeId, raw.device_id, raw.deviceId, raw.id, `node_${index + 1}`);
    const name = textFirst(raw.name, raw.label, raw.hostname, raw.title, id);
    const status = textFirst(raw.status, raw.health, raw.lifecycle, "unknown");
    const rawKind = textFirst(raw.kind, raw.node_kind, raw.device_kind, "unknown");
    const localEnabled = boolFirst(
      raw.is_local,
      raw.localEnabled,
      rawKind === "local",
      accessRecord.enabled && rawKind === "local",
      false,
    );
    const remoteEnabled = boolFirst(
      raw.is_remote,
      raw.remoteEnabled,
      rawKind === "remote" || rawKind === "device",
      accessRecord.enabled && (rawKind === "remote" || rawKind === "device"),
      false,
    );
    const trustLevel = textFirst(raw.trustLevel, raw.trust, authRecord.trustLevel, runtimeRecord.workspaceTrust, "unknown");
    const kind = rawKind || (localEnabled ? "local" : "remote");
    const pairing: NodePairingSummary = {
      pendingPairing: numberFirst(
        pairingRecord.pendingRequestCount,
        pairingRecord.pendingPairingRequestCount,
        raw.pending_pairing,
        raw.pendingPairingCount,
        0,
      ),
      pendingApprovals: numberFirst(
        pairingRecord.pendingApprovalCount,
        pairingRecord.pending_approvals,
        raw.pending_approvals,
        raw.pendingApprovalCount,
        0,
      ),
      hasNativeContract: boolFirst(pairingRecord.hasNativeContract, raw.hasNativePairingContract, false),
      source: textFirst(pairingRecord.source, raw.pairing_source, "nodes.list"),
      summary: textFirst(pairingRecord.summary, raw.pairing_summary, ""),
      pendingRefs: this.normalizePairingPendingRefs(
        pairingRecord.pendingRefs,
        pairingRecord.pending_refs,
        raw.pendingRefs,
        raw.pending_refs,
      ),
    };
    const capability: NodeCapabilitySummary = {
      browser: capabilityLevel(
        capabilityRecord.browser,
        raw.browser,
        raw.browser_status,
        numberFirst(runtimeRecord.toolCount, 0) > 0 ? "ready" : "unknown",
      ),
      workflows: capabilityLevel(
        capabilityRecord.workflows,
        raw.workflows,
        raw.workflow_status,
        numberFirst(activityRecord.workflowCount, 0) > 0 ? "ready" : "unknown",
      ),
      approvals: capabilityLevel(
        capabilityRecord.approvals,
        raw.approvals,
        raw.approval_status,
        numberFirst(activityRecord.approvalCount, 0) > 0 ? "ready" : "unknown",
      ),
      connectors: capabilityLevel(
        capabilityRecord.connectors,
        raw.connectors,
        raw.connector_status,
        numberFirst(runtimeRecord.appConnectorCount, 0) > 0 ? "ready" : "unknown",
      ),
    };
    return {
      id,
      name,
      status,
      localEnabled,
      remoteEnabled,
      trustLevel,
      kind,
      capability,
      pairing,
      raw,
    };
  }

  private selectedNode(): NodeEntry | null {
    if (!this.nodes.length) {
      return null;
    }
    return this.nodes.find((item) => item.id === this.selectedNodeId) ?? this.nodes[0];
  }

  private localNodeCount(): number {
    return this.nodes.filter((item) => item.localEnabled).length;
  }

  private remoteNodeCount(): number {
    return this.nodes.filter((item) => item.remoteEnabled).length;
  }

  private pendingPairingTotal(): number {
    return this.nodes.reduce((sum, item) => sum + item.pairing.pendingPairing, 0);
  }

  private statusPillClass(status: string): string {
    const normalized = status.trim().toLowerCase();
    if (["ready", "ok", "healthy", "running", "online"].includes(normalized)) {
      return "ready";
    }
    if (["error", "failed", "unhealthy", "offline"].includes(normalized)) {
      return "error";
    }
    return "warning";
  }

  private selectNode(nodeId: string) {
    this.selectedNodeId = nodeId;
  }

  private emitRouteChange(route: RouteTarget) {
    this.dispatchEvent(
      new CustomEvent<RouteTarget>("route-change", {
        detail: route,
        bubbles: true,
        composed: true,
      }),
    );
  }

  private emitControlContext(detail: NodesControlContextDetail) {
    if (!detail.traceId.trim()) {
      return;
    }
    this.dispatchEvent(
      new CustomEvent<NodesControlContextDetail>("navigate-control-context", {
        detail,
        bubbles: true,
        composed: true,
      }),
    );
  }

  private normalizePairingPendingRefs(...values: unknown[]): PairingPendingRef[] {
    const pickText = (...candidates: unknown[]) => {
      for (const candidate of candidates) {
        if (typeof candidate === "string" && candidate.trim()) {
          return candidate.trim();
        }
      }
      return "";
    };
    for (const value of values) {
      if (!Array.isArray(value)) {
        continue;
      }
      const normalized: PairingPendingRef[] = [];
      for (const entry of value) {
        if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
          continue;
        }
        const record = entry as Record<string, unknown>;
        const approvalId = pickText(record.approvalId, record.approval_id);
        const traceId = pickText(record.traceId, record.trace_id);
        const title = pickText(record.title, record.summary, record.reason);
        const actionType = pickText(record.actionType, record.action_type);
        if ((!approvalId && !traceId) || !title || !actionType) {
          continue;
        }
        const normalizedRef: PairingPendingRef = {
          approvalId,
          traceId,
          title,
          actionType,
        };
        const requestedAt = pickText(record.requestedAt, record.requested_at, record.createdAt, record.created_at);
        if (requestedAt) {
          normalizedRef.requestedAt = requestedAt;
        }
        normalized.push(normalizedRef);
      }
      return normalized;
    }
    return [];
  }

  private pairingPendingRefKey(ref: PairingPendingRef): string {
    return ref.approvalId || ref.traceId || ref.actionType || ref.title || "pairing-ref";
  }

  private openNodePairingApproval(ref: PairingPendingRef) {
    const traceId = String(ref.traceId ?? "").trim();
    if (traceId) {
      this.emitControlContext({
        route: "approvals",
        traceId,
        approvalId: String(ref.approvalId ?? "").trim() || undefined,
        source: "nodes-pairing",
      });
      return;
    }
    this.emitRouteChange("approvals");
  }

  private openNodePairingTrace(ref: PairingPendingRef) {
    const traceId = String(ref.traceId ?? "").trim();
    if (traceId) {
      this.emitControlContext({
        route: "sessions",
        traceId,
        timelineScope: "approvalTickets",
        source: "nodes-pairing",
      });
      return;
    }
    this.emitRouteChange("sessions");
  }

  private renderNodePairingPendingRefs(refs: PairingPendingRef[]) {
    if (!refs.length) {
      return html`<p class="caption">当前无 pending pairing refs。</p>`;
    }
    return refs.map((entry) => {
      const key = this.testIdPart(this.pairingPendingRefKey(entry));
      return html`
        <section class="item" data-testid=${`nodes-pairing-ref-${key}`}>
          <strong>${entry.title}</strong>
          <div class="caption">action=${entry.actionType}</div>
          <div class="hint">approval=${entry.approvalId || "-"} · trace=${entry.traceId || "-"}</div>
          <div class="caption">${entry.requestedAt ? `requestedAt=${entry.requestedAt}` : "requestedAt=-"}</div>
          <div class="actions inline">
            <button
              type="button"
              class="secondary"
              data-testid=${`nodes-pairing-open-approvals-${key}`}
              @click=${() => this.openNodePairingApproval(entry)}
            >
              打开审批上下文
            </button>
            <button
              type="button"
              class="secondary"
              data-testid=${`nodes-pairing-open-sessions-${key}`}
              @click=${() => this.openNodePairingTrace(entry)}
            >
              打开 Trace
            </button>
          </div>
        </section>
      `;
    });
  }

  private testIdPart(value: string): string {
    return value
      .toLowerCase()
      .replace(/[^a-z0-9_-]+/g, "-")
      .replace(/^-+|-+$/g, "")
      || "node";
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "nodes-devices-page": NodesDevicesPage;
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function toRecordArray(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => asRecord(item)).filter((item): item is Record<string, unknown> => Boolean(item));
}

function textOf(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function textFirst(...values: unknown[]): string {
  for (const value of values) {
    const text = textOf(value);
    if (text) {
      return text;
    }
  }
  return "";
}

function boolFirst(...values: unknown[]): boolean {
  for (const value of values) {
    if (typeof value === "boolean") {
      return value;
    }
    if (typeof value === "number") {
      return value !== 0;
    }
    if (typeof value === "string") {
      const normalized = value.trim().toLowerCase();
      if (["true", "1", "yes", "on", "enabled", "ready"].includes(normalized)) {
        return true;
      }
      if (["false", "0", "no", "off", "disabled"].includes(normalized)) {
        return false;
      }
    }
  }
  return false;
}

function numberFirst(...values: unknown[]): number {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value)) {
      return Math.max(0, Math.trunc(value));
    }
    if (typeof value === "string") {
      const parsed = Number.parseInt(value, 10);
      if (Number.isFinite(parsed)) {
        return Math.max(0, parsed);
      }
    }
  }
  return 0;
}

function capabilityLevel(...values: unknown[]): CapabilityLevel {
  for (const value of values) {
    if (typeof value === "boolean") {
      return value ? "ready" : "warning";
    }
    if (typeof value === "string") {
      const normalized = value.trim().toLowerCase();
      if (!normalized) {
        continue;
      }
      if (["ready", "ok", "healthy", "enabled", "available", "running"].includes(normalized)) {
        return "ready";
      }
      if (["warning", "degraded", "error", "failed", "disabled", "offline", "unavailable"].includes(normalized)) {
        return "warning";
      }
    }
    if (value && typeof value === "object") {
      const record = value as Record<string, unknown>;
      if ("ok" in record) {
        return capabilityLevel(record.ok);
      }
      if ("status" in record) {
        return capabilityLevel(record.status);
      }
      if ("enabled" in record) {
        return capabilityLevel(record.enabled);
      }
      if ("running" in record) {
        return capabilityLevel(record.running);
      }
    }
  }
  return "unknown";
}
