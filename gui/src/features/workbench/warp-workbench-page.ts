import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { BridgeClient, createMockBridgeClient } from "../../bridge/client.ts";
import "../../shared/components/operation-feedback-view.ts";
import "../../shared/components/warp-button.ts";
import "../../shared/components/warp-dialog.ts";
import "../../shared/components/warp-switch.ts";
import "../../shared/components/warp-tabs.ts";
import type {
  ApprovalSummary,
  BridgeEvent,
  BrowserStatusSummary,
  ConnectorSummary,
  ControlUiStateSnapshot,
  GatewayEventFrame,
  PluginSummary,
  SettingsSnapshot,
  ShellRunResult,
  StoredToolEvent,
  ThreadSummary,
  ThreadTurn,
} from "../../shared/types/bridge.ts";
import {
  summarizeCollectionHealth,
  type HealthSummary,
} from "../../shared/state/health-summary.ts";
import {
  errorFeedback,
  feedbackFromBridgeResponse,
  neutralFeedback,
  successFeedback,
  warningFeedback,
  type OperationFeedback,
} from "../../shared/state/operation-feedback.ts";

type CommandMode = "task" | "shell" | "files";
type InspectorTab = "files" | "health" | "settings";

type TranscriptKind = "user" | "assistant" | "commentary" | "tool" | "activity";

type TranscriptEntry = {
  id: string;
  kind: TranscriptKind;
  title: string;
  body: string;
  meta: string[];
  ok?: boolean;
};

type ArtifactKind = "file" | "directory" | "search" | "snapshot" | "tool";

type Artifact = {
  id: string;
  kind: ArtifactKind;
  title: string;
  subtitle: string;
  body: string;
  path: string;
  ok: boolean;
  payload: Record<string, unknown>;
  summary: string;
  toolName: string;
};

type WorkbenchRouteId = "chat" | "browser" | "approvals" | "sessions" | "plugins" | "settings";

const COMMAND_MODES: Array<{ id: CommandMode; label: string; detail: string }> = [
  {
    id: "task",
    label: "Task",
    detail: "agent task",
  },
  {
    id: "shell",
    label: "Shell",
    detail: "os command",
  },
  {
    id: "files",
    label: "Files",
    detail: "read / search",
  },
];

const INSPECTOR_TABS: Array<{ id: InspectorTab; label: string; detail: string }> = [
  {
    id: "files",
    label: "Files",
    detail: "artifacts",
  },
  {
    id: "health",
    label: "Health",
    detail: "status",
  },
  {
    id: "settings",
    label: "Settings",
    detail: "toggles",
  },
];

const FILE_TOOL_NAMES = new Set([
  "file_read",
  "read_file",
  "file_list",
  "list_dir",
  "file_search",
  "grep_files",
  "glob_files",
  "dir.list",
  "dir.search",
  "file.list",
  "file.search",
]);

@customElement("warp-workbench-page")
export class WarpWorkbenchPage extends LitElement {
  static styles = css`
    :host {
      display: block;
      min-height: 100%;
      color: #d6e3ea;
      background: #0a1016;
    }

    .surface {
      display: grid;
      grid-template-columns: minmax(260px, 300px) minmax(0, 1fr) minmax(290px, 340px);
      min-height: calc(100vh - 0px);
      background:
        linear-gradient(180deg, rgba(9, 15, 21, 0.98), rgba(9, 15, 21, 0.98)),
        #0a1016;
    }

    .rail,
    .workspace {
      min-width: 0;
    }

    .rail {
      display: grid;
      gap: 14px;
      align-content: start;
      padding: 18px 16px;
      background: rgba(7, 12, 17, 0.96);
      border-right: 1px solid rgba(143, 163, 176, 0.12);
    }

    .rail.right {
      border-right: 0;
      border-left: 1px solid rgba(143, 163, 176, 0.12);
      background: rgba(8, 13, 18, 0.94);
    }

    .workspace {
      display: grid;
      grid-template-rows: auto auto 1fr;
      gap: 14px;
      padding: 18px 16px;
      min-width: 0;
      background:
        linear-gradient(180deg, rgba(11, 16, 22, 0.8), rgba(10, 15, 21, 0.98)),
        #0a1016;
    }

    .brand {
      display: grid;
      gap: 6px;
      padding: 4px 2px 6px;
    }

    .brand-title {
      color: #f5fbff;
      font-size: 22px;
      font-weight: 700;
      line-height: 1.1;
    }

    .brand-copy,
    .helper,
    .meta {
      color: #8fa6b4;
      font-size: 12px;
      line-height: 1.5;
    }

    .chip-row,
    .button-row,
    .route-row,
    .quick-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .chip {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      border-radius: 8px;
      padding: 0 10px;
      border: 1px solid rgba(143, 163, 176, 0.16);
      background: rgba(13, 20, 27, 0.92);
      color: #d9e7ef;
      font-size: 12px;
      white-space: nowrap;
    }

    .rail-card,
    .panel,
    .composer-card,
    .transcript-card {
      display: grid;
      gap: 12px;
      border: 1px solid rgba(143, 163, 176, 0.14);
      border-radius: 8px;
      background: rgba(10, 16, 22, 0.92);
      padding: 14px;
      min-width: 0;
    }

    .panel {
      padding: 12px;
    }

    .panel-header,
    .section-header,
    .composer-header,
    .transcript-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      min-width: 0;
    }

    .panel-title,
    .section-title {
      min-width: 0;
      color: #f5fbff;
      font-size: 14px;
      font-weight: 700;
      line-height: 1.35;
    }

    .panel-detail,
    .section-detail {
      min-width: 0;
      color: #8ea6b3;
      font-size: 12px;
      line-height: 1.45;
    }

    .thread-list {
      display: grid;
      gap: 8px;
      max-height: 32vh;
      overflow: auto;
      padding-right: 2px;
    }

    .thread-item {
      display: grid;
      gap: 3px;
      width: 100%;
      border: 1px solid transparent;
      border-radius: 8px;
      padding: 10px 11px;
      background: rgba(13, 19, 26, 0.92);
      color: #d5e3eb;
      font: inherit;
      text-align: left;
      cursor: pointer;
      transition:
        background 120ms ease,
        border-color 120ms ease,
        transform 120ms ease;
    }

    .thread-item:hover,
    .thread-item:focus-visible {
      outline: none;
      border-color: rgba(166, 191, 203, 0.24);
      background: rgba(17, 25, 33, 0.98);
      transform: translateY(-1px);
    }

    .thread-item[aria-current="true"] {
      border-color: rgba(120, 196, 224, 0.3);
      background: linear-gradient(135deg, rgba(20, 44, 58, 0.95), rgba(12, 23, 31, 0.98));
    }

    .thread-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      min-width: 0;
      color: #f4fbff;
      font-size: 13px;
      font-weight: 600;
    }

    .thread-title span:first-child {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .thread-meta,
    .entry-meta {
      color: #93a9b6;
      font-size: 12px;
      line-height: 1.45;
    }

    .thread-preview {
      color: #8ea6b3;
      font-size: 12px;
      line-height: 1.45;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .workspace-head {
      display: grid;
      gap: 12px;
    }

    .workspace-title {
      display: grid;
      gap: 6px;
      min-width: 0;
    }

    .workspace-title h1 {
      margin: 0;
      color: #f5fbff;
      font-size: 24px;
      font-weight: 700;
      line-height: 1.1;
    }

    .workspace-title p {
      margin: 0;
      color: #8fa6b4;
      font-size: 13px;
      line-height: 1.55;
    }

    .workspace-stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }

    .stat-card {
      display: grid;
      gap: 6px;
      border: 1px solid rgba(143, 163, 176, 0.14);
      border-radius: 8px;
      padding: 10px 12px;
      background: rgba(10, 16, 22, 0.9);
    }

    .stat-label {
      color: #8ea6b3;
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }

    .stat-value {
      color: #f5fbff;
      font-size: 15px;
      font-weight: 700;
      line-height: 1.2;
    }

    .stat-detail {
      color: #9cb0bc;
      font-size: 12px;
      line-height: 1.4;
    }

    .composer-card {
      gap: 14px;
    }

    textarea {
      width: 100%;
      min-height: 144px;
      border: 1px solid rgba(143, 163, 176, 0.16);
      border-radius: 8px;
      padding: 12px 13px;
      color: #eff7fb;
      background: rgba(8, 13, 18, 0.98);
      font: inherit;
      font-size: 13px;
      line-height: 1.55;
      resize: vertical;
    }

    textarea:focus-visible {
      outline: none;
      border-color: rgba(120, 196, 224, 0.34);
      box-shadow: 0 0 0 2px rgba(120, 196, 224, 0.12);
    }

    textarea::placeholder {
      color: #6f8794;
    }

    .mode-row {
      display: grid;
      gap: 10px;
    }

    .mode-help {
      color: #8ea6b3;
      font-size: 12px;
      line-height: 1.45;
    }

    .composer-actions {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
    }

    .composer-actions .button-row {
      flex: 1 1 260px;
    }

    .composer-actions .button-row warp-button {
      flex: none;
    }

    .transcript-card {
      min-height: 0;
      grid-template-rows: auto 1fr;
    }

    .transcript-list {
      display: grid;
      gap: 10px;
      min-height: 0;
      overflow: auto;
      padding-right: 2px;
    }

    .transcript-list.compact {
      gap: 6px;
    }

    .entry {
      display: grid;
      gap: 6px;
      border: 1px solid rgba(143, 163, 176, 0.12);
      border-radius: 8px;
      padding: 11px 12px;
      background: rgba(11, 17, 23, 0.94);
    }

    .entry.user {
      background: rgba(15, 32, 41, 0.94);
      border-color: rgba(120, 196, 224, 0.12);
    }

    .entry.assistant {
      background: rgba(16, 22, 30, 0.96);
    }

    .entry.commentary {
      background: rgba(18, 20, 26, 0.96);
    }

    .entry.tool {
      background: rgba(17, 28, 19, 0.96);
      border-color: rgba(125, 198, 148, 0.12);
    }

    .entry.activity {
      background: rgba(22, 23, 28, 0.96);
      border-color: rgba(202, 182, 114, 0.12);
    }

    .entry.compact {
      gap: 4px;
      padding: 8px 10px;
    }

    .entry.compact .entry-body {
      font-size: 12px;
      line-height: 1.45;
    }

    .entry-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      min-width: 0;
      color: #f5fbff;
      font-size: 13px;
      font-weight: 600;
      line-height: 1.35;
    }

    .entry-title span:first-child {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .entry-body {
      color: #c5d2db;
      font-size: 13px;
      line-height: 1.55;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }

    .entry-body.muted {
      color: #93a9b6;
    }

    .badge {
      flex: none;
      min-height: 20px;
      border-radius: 8px;
      padding: 0 7px;
      background: rgba(255, 255, 255, 0.06);
      color: #c3d5df;
      font-size: 11px;
      line-height: 20px;
      white-space: nowrap;
    }

    .badge.ready {
      background: rgba(76, 175, 139, 0.16);
      color: #8ae0ba;
    }

    .badge.warning {
      background: rgba(234, 183, 94, 0.14);
      color: #ffd486;
    }

    .badge.error {
      background: rgba(218, 97, 97, 0.14);
      color: #ff9d9d;
    }

    .artifact-list {
      display: grid;
      gap: 8px;
      max-height: 28vh;
      overflow: auto;
      padding-right: 2px;
    }

    .artifact-item {
      display: grid;
      gap: 4px;
      width: 100%;
      border: 1px solid rgba(143, 163, 176, 0.14);
      border-radius: 8px;
      padding: 10px 11px;
      background: rgba(11, 17, 23, 0.94);
      color: #dce8ef;
      font: inherit;
      text-align: left;
      cursor: pointer;
    }

    .artifact-item:hover,
    .artifact-item:focus-visible {
      outline: none;
      border-color: rgba(120, 196, 224, 0.28);
      background: rgba(16, 24, 32, 0.98);
    }

    .artifact-item[aria-current="true"] {
      border-color: rgba(120, 196, 224, 0.34);
      background: rgba(18, 34, 45, 0.98);
    }

    .artifact-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      min-width: 0;
      color: #f5fbff;
      font-size: 13px;
      font-weight: 600;
    }

    .artifact-title span:first-child {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .artifact-preview {
      display: grid;
      gap: 8px;
      min-width: 0;
    }

    .preview-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      min-width: 0;
    }

    .preview-path {
      min-width: 0;
      overflow: hidden;
      color: #f4fbff;
      font-size: 13px;
      font-weight: 600;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .preview-card {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      gap: 10px;
      max-height: 36vh;
      overflow: auto;
      border: 1px solid rgba(143, 163, 176, 0.14);
      border-radius: 8px;
      padding: 10px 12px;
      background: rgba(7, 12, 17, 0.96);
    }

    .preview-lines {
      display: grid;
      gap: 0;
      color: #6f8794;
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      font-size: 12px;
      line-height: 1.55;
      text-align: right;
      user-select: none;
    }

    .preview-body {
      display: grid;
      gap: 0;
      min-width: 0;
      color: #eaf3f8;
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      font-size: 12px;
      line-height: 1.55;
      white-space: pre;
      overflow-wrap: normal;
    }

    .settings-stack,
    .health-stack {
      display: grid;
      gap: 10px;
    }

    .health-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }

    .health-card {
      display: grid;
      gap: 4px;
      border: 1px solid rgba(143, 163, 176, 0.14);
      border-radius: 8px;
      padding: 10px;
      background: rgba(11, 17, 23, 0.94);
    }

    .health-card strong {
      color: #f5fbff;
      font-size: 13px;
      font-weight: 600;
    }

    .health-card span {
      color: #8ea6b3;
      font-size: 12px;
      line-height: 1.45;
    }

    .empty {
      color: #7c93a1;
      font-size: 12px;
      line-height: 1.5;
    }

    .compact-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .command-link-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    warp-button {
      flex: none;
    }

    warp-switch {
      min-width: 0;
    }

    .dialog-preview {
      display: grid;
      gap: 12px;
    }

    .dialog-payload {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      gap: 10px;
      max-height: 44vh;
      overflow: auto;
      border: 1px solid rgba(143, 163, 176, 0.14);
      border-radius: 8px;
      padding: 12px;
      background: rgba(6, 10, 14, 0.96);
    }

    .dialog-lines {
      display: grid;
      gap: 0;
      color: #708594;
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      font-size: 12px;
      line-height: 1.55;
      text-align: right;
      user-select: none;
    }

    .dialog-body {
      display: grid;
      gap: 0;
      min-width: 0;
      color: #eaf3f8;
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      font-size: 12px;
      line-height: 1.55;
      white-space: pre;
    }

    @media (max-width: 1280px) {
      .surface {
        grid-template-columns: minmax(240px, 280px) minmax(0, 1fr);
      }

      .rail.right {
        grid-column: 1 / -1;
        border-left: 0;
        border-top: 1px solid rgba(143, 163, 176, 0.12);
      }
    }

    @media (max-width: 960px) {
      .surface {
        grid-template-columns: 1fr;
      }

      .rail,
      .workspace {
        padding: 14px;
      }

      .workspace-stats {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .health-grid {
        grid-template-columns: 1fr;
      }
    }
  `;

  @property({ attribute: false }) bridgeClient: BridgeClient = createMockBridgeClient();

  @state() private loading = true;
  @state() private settings: SettingsSnapshot | null = null;
  @state() private browser: BrowserStatusSummary | null = null;
  @state() private approvals: ApprovalSummary[] = [];
  @state() private plugins: PluginSummary[] = [];
  @state() private connectors: ConnectorSummary[] = [];
  @state() private controlUiState: ControlUiStateSnapshot | null = null;
  @state() private threads: ThreadSummary[] = [];
  @state() private selectedThreadId = "";
  @state() private selectedThreadTitle = "";
  @state() private transcript: TranscriptEntry[] = [];
  @state() private artifacts: Artifact[] = [];
  @state() private selectedArtifactId = "";
  @state() private commandDraft = "";
  @state() private commandMode: CommandMode = "task";
  @state() private inspectorTab: InspectorTab = "files";
  @state() private showPayloads = true;
  @state() private compactTranscript = false;
  @state() private runFeedback: OperationFeedback = neutralFeedback("等待命令。");
  @state() private activeTaskId = "";
  @state() private gatewayEvents: GatewayEventFrame[] = [];
  @state() private gatewayCursor = 0;
  @state() private fileDialogOpen = false;
  @state() private dialogArtifact: Artifact | null = null;

  private bridgeUnsubscribe: (() => void) | null = null;
  private gatewayPollTimer: ReturnType<typeof setInterval> | null = null;

  connectedCallback(): void {
    super.connectedCallback();
    this.bridgeUnsubscribe = this.bridgeClient.subscribe(this.handleBridgeEvent);
    void this.load();
    this.gatewayPollTimer = window.setInterval(() => {
      void this.pollGatewayEvents();
    }, 4000);
  }

  disconnectedCallback(): void {
    this.bridgeUnsubscribe?.();
    this.bridgeUnsubscribe = null;
    if (this.gatewayPollTimer !== null) {
      clearInterval(this.gatewayPollTimer);
      this.gatewayPollTimer = null;
    }
    super.disconnectedCallback();
  }

  render() {
    const workspaceRoot = this.settings?.workspaceRoot?.trim() || "workspace";
    const activeThread = this.threads.find((thread) => thread.thread_id === this.selectedThreadId) ?? null;
    const pendingApprovals = this.approvals.filter((item) => item.status === "pending").length;
    const connectorSummary = summarizeCollectionHealth(this.connectors.map((item) => item.health), {
      label: "连接器",
      emptyDetail: "暂无连接器",
    });
    const pluginSummary = summarizeCollectionHealth(this.plugins.map((item) => item.health), {
      label: "插件",
      emptyDetail: "暂无插件",
    });
    const dialogText = this.dialogArtifact ? this.artifactPreviewText(this.dialogArtifact) : "";
    return html`
      <section class="surface" data-testid="warp-workbench-page">
        <aside class="rail">
          <div class="brand">
            <div class="brand-title">AgentHub</div>
            <div class="brand-copy">
              Warp-style workspace for tasks, shell commands, and file inspection.
            </div>
          </div>

          <div class="rail-card">
            <div class="panel-header">
              <div>
                <div class="panel-title">Workspace</div>
                <div class="panel-detail">${workspaceRoot}</div>
              </div>
              <span class="badge">${this.commandMode.toUpperCase()}</span>
            </div>
            <div class="chip-row">
              <span class="chip">thread=${activeThread?.turn_count ?? 0}</span>
              <span class="chip">pending=${pendingApprovals}</span>
              <span class="chip">artifacts=${this.artifacts.length}</span>
            </div>
            <div class="button-row">
              <warp-button
                variant="primary"
                icon="↑"
                label="Run"
                shortcut="Enter"
                tooltip="Run the current draft"
                ?busy=${Boolean(this.activeTaskId)}
                @click=${this.submitDraft}
              ></warp-button>
              <warp-button
                variant="secondary"
                icon="⏹"
                label="Stop"
                shortcut="Esc"
                tooltip="Stop the active task"
                ?disabled=${!this.activeTaskId}
                @click=${this.stopTask}
              ></warp-button>
            </div>
            <div class="button-row">
              <warp-button
                variant="ghost"
                icon="＋"
                label="New"
                tooltip="Start a fresh thread"
                @click=${this.startFreshThread}
              ></warp-button>
              <warp-button
                variant="ghost"
                icon="↻"
                label="Refresh"
                tooltip="Refresh threads and status"
                ?busy=${this.loading}
                @click=${this.refreshAll}
              ></warp-button>
            </div>
          </div>

          <div class="rail-card">
            <div class="section-header">
              <div>
                <div class="section-title">Routes</div>
                <div class="section-detail">Jump to the control surfaces.</div>
              </div>
            </div>
            <div class="route-row">
              <warp-button variant="naked" label="Chat" icon="⌁" @click=${() => this.navigateToRoute("chat")}></warp-button>
              <warp-button
                variant="naked"
                label="Approvals"
                icon="✓"
                @click=${() => this.navigateToRoute("approvals")}
              ></warp-button>
              <warp-button
                variant="naked"
                label="Browser"
                icon="▣"
                @click=${() => this.navigateToRoute("browser")}
              ></warp-button>
              <warp-button
                variant="naked"
                label="Sessions"
                icon="↔"
                @click=${() => this.navigateToRoute("sessions")}
              ></warp-button>
              <warp-button
                variant="naked"
                label="Plugins"
                icon="⌘"
                @click=${() => this.navigateToRoute("plugins")}
              ></warp-button>
              <warp-button
                variant="naked"
                label="Settings"
                icon="⚙"
                @click=${() => this.navigateToRoute("settings")}
              ></warp-button>
            </div>
          </div>

          <div class="rail-card">
            <div class="section-header">
              <div>
                <div class="section-title">Threads</div>
                <div class="section-detail">Recent workspace conversations.</div>
              </div>
            </div>
            <div class="thread-list">
              ${this.threads.length
                ? this.threads.map((thread) => this.renderThread(thread))
                : html`<div class="empty">No threads yet.</div>`}
            </div>
          </div>
        </aside>

        <main class="workspace">
          <section class="workspace-head">
            <div class="workspace-title">
              <h1>Command Surface</h1>
              <p>
                Enter tasks, shell commands, and file operations in one surface. Transcript, files, and
                status stay visible together.
              </p>
            </div>

            <div class="workspace-stats">
              ${this.renderStat("Model", this.settings?.model || "unset", this.settings?.providerLabel || "provider pending")}
              ${this.renderStat(
                "Browser",
                this.browser?.running ? "running" : "idle",
                this.browser ? `${this.browser.tabCount} tabs` : "no browser data",
              )}
              ${this.renderStat("Approvals", `${pendingApprovals}`, pendingApprovals > 0 ? "waiting" : "clear")}
              ${this.renderStat("Gateway", this.controlUiState?.health?.status || "unknown", this.gatewayEvents.length ? "live events" : "quiet")}
            </div>
          </section>

          <section class="composer-card">
            <div class="composer-header">
              <div>
                <div class="section-title">Composer</div>
                <div class="section-detail">Enter to run, Shift+Enter for a newline.</div>
              </div>
              <span class="badge">${this.selectedThreadId ? this.selectedThreadTitle || "thread" : "new"}</span>
            </div>

            <div class="mode-row">
              <warp-tabs
                ariaLabel="Command mode"
                .items=${COMMAND_MODES}
                .value=${this.commandMode}
                @change=${this.handleCommandModeChange}
              ></warp-tabs>
              <div class="mode-help">${this.modeHelpText()}</div>
            </div>

            <textarea
              data-testid="warp-command-composer"
              .value=${this.commandDraft}
              placeholder=${this.commandPlaceholder()}
              @input=${this.handleComposerInput}
              @keydown=${this.handleComposerKeydown}
            ></textarea>

            <div class="quick-row">
              ${this.quickTemplateButtons().map(
                (item) => html`
                  <warp-button
                    variant="ghost"
                    size="small"
                    icon=${item.icon}
                    label=${item.label}
                    tooltip=${item.tooltip}
                    @click=${() => this.insertTemplate(item.template)}
                  ></warp-button>
                `,
              )}
            </div>

            <div class="composer-actions">
              <div class="button-row">
                <warp-button
                  variant="primary"
                  icon="↑"
                  label=${this.runButtonLabel()}
                  shortcut="Enter"
                  tooltip=${this.runButtonTooltip()}
                  @click=${this.submitDraft}
                ></warp-button>
                <warp-button
                  variant="secondary"
                  icon="⏹"
                  label="Stop"
                  shortcut="Esc"
                  tooltip="Interrupt the active task"
                  ?disabled=${!this.activeTaskId}
                  @click=${this.stopTask}
                ></warp-button>
                <warp-button
                  variant="ghost"
                  icon="↺"
                  label="Clear"
                  tooltip="Clear the current draft"
                  @click=${this.clearDraft}
                ></warp-button>
              </div>
              <div class="button-row">
                <warp-button
                  variant="naked"
                  label="Open settings"
                  icon="⚙"
                  @click=${() => this.navigateToRoute("settings")}
                ></warp-button>
              </div>
            </div>

            <operation-feedback-view
              data-testid="workbench-feedback"
              .feedback=${this.runFeedback}
            ></operation-feedback-view>
          </section>

          <section class="transcript-card">
            <div class="transcript-header">
              <div>
                <div class="section-title">Transcript</div>
                <div class="section-detail">${this.transcript.length} entries for the selected thread</div>
              </div>
              <div class="compact-row">
                <warp-button
                  variant="ghost"
                  size="small"
                  icon="⟳"
                  label="Reload"
                  tooltip="Reload the selected thread"
                  ?disabled=${!this.selectedThreadId}
                  @click=${this.reloadSelectedThread}
                ></warp-button>
              </div>
            </div>

            <div
              class=${this.compactTranscript ? "transcript-list compact" : "transcript-list"}
              data-testid="warp-transcript-list"
            >
              ${this.transcript.length
                ? this.transcript.map((entry) => this.renderTranscriptEntry(entry))
                : html`<div class="empty">Select a thread or run a command to populate the transcript.</div>`}
            </div>
          </section>
        </main>

        <aside class="rail right">
          <div class="rail-card">
            <div class="section-header">
              <div>
                <div class="section-title">Inspector</div>
                <div class="section-detail">Files, health, and runtime toggles.</div>
              </div>
            </div>
            <warp-tabs
              ariaLabel="Inspector tabs"
              .items=${INSPECTOR_TABS}
              .value=${this.inspectorTab}
              @change=${this.handleInspectorChange}
            ></warp-tabs>
          </div>

          ${this.inspectorTab === "files"
            ? this.renderFileInspector()
            : this.inspectorTab === "health"
              ? this.renderHealthInspector(connectorSummary, pluginSummary, pendingApprovals)
              : this.renderSettingsInspector()}
        </aside>

        <warp-dialog
          .open=${this.fileDialogOpen}
          .title=${this.dialogArtifact?.title ?? "Artifact"}
          .subtitle=${this.dialogArtifact ? this.dialogSubtitle(this.dialogArtifact) : ""}
          @dismiss=${this.closeArtifactDialog}
        >
          ${this.dialogArtifact
            ? html`
                <div class="dialog-preview">
                  <div class="meta">${this.dialogArtifact.summary || this.dialogArtifact.subtitle}</div>
                  <div class="dialog-payload">
                    <div class="dialog-lines">
                      ${this.renderLineNumbers(dialogText)}
                    </div>
                    <div class="dialog-body">${dialogText}</div>
                  </div>
                </div>
                <warp-button
                  slot="footer"
                  variant="secondary"
                  icon="↗"
                  label="Close"
                  @click=${this.closeArtifactDialog}
                ></warp-button>
              `
            : nothing}
        </warp-dialog>
      </section>
    `;
  }

  private renderThread(thread: ThreadSummary) {
    const active = thread.thread_id === this.selectedThreadId;
    return html`
      <button
        class="thread-item"
        type="button"
        aria-current=${active ? "true" : "false"}
        @click=${() => this.selectThread(thread.thread_id)}
      >
        <div class="thread-title">
          <span>${thread.name || thread.thread_id}</span>
          <span class="badge">${thread.turn_count}</span>
        </div>
        <div class="thread-meta">${thread.updated_at}${thread.cwd ? ` · ${thread.cwd}` : ""}</div>
        <div class="thread-preview">${thread.last_user_text || thread.last_assistant_text || "No preview yet."}</div>
      </button>
    `;
  }

  private renderStat(label: string, value: string, detail: string) {
    return html`
      <div class="stat-card">
        <div class="stat-label">${label}</div>
        <div class="stat-value">${value}</div>
        <div class="stat-detail">${detail}</div>
      </div>
    `;
  }

  private renderTranscriptEntry(entry: TranscriptEntry) {
    const compactClass = this.compactTranscript ? " compact" : "";
    return html`
      <article class=${`entry ${entry.kind}${compactClass}`}>
        <div class="entry-title">
          <span>${entry.title}</span>
          <span class="badge">${entry.kind}</span>
        </div>
        ${entry.meta.length
          ? html`<div class="entry-meta">${entry.meta.join(" · ")}</div>`
          : null}
        <div class=${`entry-body ${entry.kind === "commentary" ? "muted" : ""}`}>${entry.body}</div>
      </article>
    `;
  }

  private renderFileInspector() {
    const selected = this.artifacts.find((artifact) => artifact.id === this.selectedArtifactId) ?? this.artifacts[0] ?? null;
    const previewText = selected ? this.artifactPreviewText(selected) : "";
    return html`
      <div class="rail-card">
        <div class="section-header">
          <div>
            <div class="section-title">Artifacts</div>
            <div class="section-detail">Files and tool outputs from the selected thread.</div>
          </div>
        </div>
        <div class="artifact-list">
          ${this.artifacts.length
            ? this.artifacts.map((artifact) => this.renderArtifactItem(artifact, artifact.id === selected?.id))
            : html`<div class="empty">No file-like tool output yet.</div>`}
        </div>
      </div>

      <div class="rail-card">
        <div class="preview-header">
          <div class="preview-path">${selected ? this.previewTitle(selected) : "No artifact selected"}</div>
          ${selected
            ? html`
                <warp-button
                  variant="ghost"
                  size="small"
                  icon="↗"
                  label="Open"
                  tooltip="Open the artifact in a dialog"
                  @click=${() => this.openArtifactDialog(selected)}
                ></warp-button>
              `
            : null}
        </div>
        ${selected
          ? html`
              <div class="artifact-preview">
                <div class="meta">${selected.subtitle}</div>
                <div class="preview-card">
                  <div class="preview-lines">${this.renderLineNumbers(previewText)}</div>
                  <div class="preview-body">${previewText}</div>
                </div>
              </div>
            `
          : html`<div class="empty">Pick a file or search artifact to inspect its contents here.</div>`}
      </div>
    `;
  }

  private renderHealthInspector(
    connectorSummary: HealthSummary,
    pluginSummary: HealthSummary,
    pendingApprovals: number,
  ) {
    return html`
      <div class="rail-card">
        <div class="section-header">
          <div>
            <div class="section-title">Health</div>
            <div class="section-detail">Runtime status and control plane summary.</div>
          </div>
        </div>
        <div class="health-grid">
          ${this.renderHealthCard("Model", this.settings?.model ? "ready" : "warning", this.settings?.providerLabel || "provider pending")}
          ${this.renderHealthCard(
            "Browser",
            this.browser?.running ? "ready" : "warning",
            this.browser ? `${this.browser.tabCount} tabs` : "unavailable",
          )}
          ${this.renderHealthCard("Plugins", pluginSummary.level, pluginSummary.detail)}
          ${this.renderHealthCard("Connectors", connectorSummary.level, connectorSummary.detail)}
          ${this.renderHealthCard("Approvals", pendingApprovals > 0 ? "warning" : "ready", `${pendingApprovals} pending`)}
          ${this.renderHealthCard(
            "Gateway",
            this.controlUiState?.health?.status === "ok" ? "ready" : "warning",
            this.controlUiState?.health?.status || "unknown",
          )}
        </div>
      </div>

      <div class="rail-card">
        <div class="section-header">
          <div>
            <div class="section-title">Gateway events</div>
            <div class="section-detail">Last polled frames.</div>
          </div>
        </div>
        <div class="settings-stack">
          ${this.gatewayEvents.length
            ? this.gatewayEvents.slice(0, 4).map(
                (event) => html`
                  <div class="health-card">
                    <strong>${event.event}</strong>
                    <span>${event.stream}${event.emittedAt ? ` · ${event.emittedAt}` : ""}</span>
                  </div>
                `,
              )
            : html`<div class="empty">No gateway events yet.</div>`}
        </div>
      </div>
    `;
  }

  private renderSettingsInspector() {
    return html`
      <div class="rail-card">
        <div class="section-header">
          <div>
            <div class="section-title">Runtime toggles</div>
            <div class="section-detail">Persisted settings and local inspector state.</div>
          </div>
        </div>
        <div class="settings-stack">
          <warp-switch
            label="Browser headless"
            description="Persist browser execution mode"
            .checked=${this.settings?.browserHeadless ?? false}
            @change=${this.handleBrowserHeadlessToggle}
          ></warp-switch>
          <warp-switch
            label="Plugin auto-load"
            description="Load plugins when the workspace opens"
            .checked=${this.settings?.pluginAutoLoad ?? false}
            @change=${this.handlePluginAutoLoadToggle}
          ></warp-switch>
          <warp-switch
            label="Show payloads"
            description="Show raw tool payloads in transcript and previews"
            .checked=${this.showPayloads}
            @change=${this.handleShowPayloadsToggle}
          ></warp-switch>
          <warp-switch
            label="Compact transcript"
            description="Tighter entry spacing for scanning"
            .checked=${this.compactTranscript}
            @change=${this.handleCompactTranscriptToggle}
          ></warp-switch>
        </div>
      </div>

      <div class="rail-card">
        <div class="section-header">
          <div>
            <div class="section-title">Actions</div>
            <div class="section-detail">Route to higher-level surfaces.</div>
          </div>
        </div>
        <div class="command-link-row">
          <warp-button variant="ghost" size="small" label="Chat" icon="⌁" @click=${() => this.navigateToRoute("chat")}></warp-button>
          <warp-button variant="ghost" size="small" label="Settings" icon="⚙" @click=${() => this.navigateToRoute("settings")}></warp-button>
          <warp-button variant="ghost" size="small" label="Sessions" icon="↔" @click=${() => this.navigateToRoute("sessions")}></warp-button>
        </div>
      </div>
    `;
  }

  private renderHealthCard(label: string, level: string, detail: string) {
    return html`
      <div class="health-card">
        <strong>${label}</strong>
        <span class="badge ${level}">${level}</span>
        <span>${detail}</span>
      </div>
    `;
  }

  private renderArtifactItem(artifact: Artifact, active: boolean) {
    return html`
      <button
        class="artifact-item"
        type="button"
        aria-current=${active ? "true" : "false"}
        @click=${() => this.selectArtifact(artifact.id)}
        @dblclick=${() => this.openArtifactDialog(artifact)}
      >
        <div class="artifact-title">
          <span>${artifact.title}</span>
          <span class="badge ${artifact.ok ? "ready" : "error"}">${artifact.kind}</span>
        </div>
        <div class="thread-meta">${artifact.subtitle || artifact.toolName}</div>
      </button>
    `;
  }

  private async load() {
    this.loading = true;
    try {
      const [settings, browser, approvals, plugins, connectors, controlUiState, threads] = await Promise.all([
        this.bridgeClient.settings.get(),
        this.bridgeClient.browser.status(),
        this.bridgeClient.approval.list(),
        this.bridgeClient.plugin.list(),
        this.bridgeClient.connector.list(),
        this.bridgeClient.controlUi.state({ limit: 12 }),
        this.bridgeClient.thread.list({ limit: 12 }),
      ]);
      this.settings = settings.data ?? this.settings;
      this.browser = browser.ok ? browser.data ?? null : null;
      this.approvals = approvals.data?.approvals ?? [];
      this.plugins = plugins.data?.plugins ?? [];
      this.connectors = connectors.data?.connectors ?? [];
      this.controlUiState = controlUiState.ok ? controlUiState.data ?? null : null;
      this.threads = threads.data?.threads ?? [];
      this.selectedThreadId = threads.data?.active_thread_id || this.threads[0]?.thread_id || "";
      await this.loadSelectedThread();
      await this.pollGatewayEvents();
    } catch (error) {
      this.runFeedback = errorFeedback(error instanceof Error ? error.message : "workspace load failed");
    } finally {
      this.loading = false;
    }
  }

  private async refreshAll() {
    await this.load();
  }

  private async loadSelectedThread() {
    if (!this.selectedThreadId) {
      this.selectedThreadTitle = "new thread";
      this.transcript = [];
      this.artifacts = [];
      this.selectedArtifactId = "";
      return;
    }
    const response = await this.bridgeClient.thread.resume({ thread_id: this.selectedThreadId });
    if (!response.ok) {
      this.runFeedback = errorFeedback(response.error?.message ?? "failed to load thread");
      this.selectedThreadTitle = this.selectedThreadId || "thread";
      this.transcript = [];
      this.artifacts = [];
      this.selectedArtifactId = "";
      return;
    }
    const thread = response.data?.thread;
    this.selectedThreadTitle = thread?.name || thread?.thread_id || "thread";
    this.transcript = this.buildTranscript(response.data?.turns ?? [], response.data?.history ?? []);
    this.artifacts = this.buildArtifacts(response.data?.turns ?? [], response.data?.history ?? []);
    this.selectedArtifactId = this.artifacts[0]?.id ?? "";
  }

  private buildTranscript(turns: ThreadTurn[], history: ThreadHistoryEntry[]): TranscriptEntry[] {
    const entries: TranscriptEntry[] = [];
    turns.forEach((turn, turnIndex) => {
      if (turn.user_text?.trim()) {
        entries.push({
          id: `turn-${turnIndex}-user`,
          kind: "user",
          title: "User",
          body: turn.user_text,
          meta: [turn.timestamp || "", this.selectedThreadTitle].filter(Boolean),
        });
      }
      if (turn.commentary_text?.trim()) {
        entries.push({
          id: `turn-${turnIndex}-commentary`,
          kind: "commentary",
          title: "Commentary",
          body: turn.commentary_text,
          meta: [turn.timestamp || "", "internal note"].filter(Boolean),
        });
      }
      if (turn.activity_events?.length) {
        turn.activity_events.forEach((event, eventIndex) => {
          entries.push({
            id: `turn-${turnIndex}-activity-${eventIndex}`,
            kind: "activity",
            title: event.title || "Activity",
            body: event.detail || event.status || "",
            meta: [event.kind || "activity", event.status || ""].filter(Boolean),
          });
        });
      }
      if (turn.tool_events?.length) {
        turn.tool_events.forEach((event, eventIndex) => {
          entries.push(this.transcriptToolEntry(turnIndex, eventIndex, event));
        });
      }
      if (turn.assistant_text?.trim()) {
        entries.push({
          id: `turn-${turnIndex}-assistant`,
          kind: "assistant",
          title: "Assistant",
          body: turn.assistant_text,
          meta: [turn.timestamp || "", turn.handled_as_command ? "command" : "reply"].filter(Boolean),
        });
      }
    });
    if (!entries.length) {
      return history.map((entry, index) => ({
        id: `history-${index}`,
        kind: entry.role,
        title: entry.role === "user" ? "User" : "Assistant",
        body: entry.content,
        meta: [this.selectedThreadTitle].filter(Boolean),
      }));
    }
    return entries;
  }

  private buildArtifacts(turns: ThreadTurn[], history: ThreadHistoryEntry[]): Artifact[] {
    const artifacts: Artifact[] = [];
    turns.forEach((turn, turnIndex) => {
      (turn.tool_events ?? []).forEach((event, eventIndex) => {
        const artifact = this.artifactFromToolEvent(event, turnIndex, eventIndex);
        if (artifact) {
          artifacts.push(artifact);
        }
      });
    });
    if (!artifacts.length && history.length) {
      const body = history.map((entry) => `${entry.role}: ${entry.content}`).join("\n");
      artifacts.push({
        id: "history-preview",
        kind: "tool",
        title: "Thread history",
        subtitle: "plain text fallback",
        body,
        path: "",
        ok: true,
        payload: { history },
        summary: "Thread history fallback",
        toolName: "thread.history",
      });
    }
    return artifacts;
  }

  private transcriptToolEntry(turnIndex: number, eventIndex: number, event: StoredToolEvent): TranscriptEntry {
    const payloadText = this.showPayloads ? this.prettyJson(event.payload) : "";
    return {
      id: `turn-${turnIndex}-tool-${eventIndex}`,
      kind: "tool",
      title: event.summary || event.name || "Tool event",
      body: payloadText || event.summary || "Tool event completed.",
      meta: [event.name, event.ok ? "ok" : "error"].filter(Boolean),
      ok: event.ok,
    };
  }

  private artifactFromToolEvent(event: StoredToolEvent, turnIndex: number, eventIndex: number): Artifact | null {
    const toolName = String(event.name || "").trim();
    const payload = this.asRecord(event.payload);
    const path = this.extractPath(payload);
    const body = this.artifactBodyFromPayload(payload, event.summary);
    const kind = this.artifactKind(toolName);
    if (!kind && !body && !path) {
      return null;
    }
    return {
      id: `artifact-${turnIndex}-${eventIndex}-${toolName || "tool"}`,
      kind: kind || "tool",
      title: event.summary || this.prettyName(toolName),
      subtitle: path || toolName || "tool output",
      body,
      path,
      ok: event.ok,
      payload,
      summary: event.summary,
      toolName,
    };
  }

  private artifactKind(toolName: string): ArtifactKind | "" {
    const normalized = toolName.trim().toLowerCase();
    if (!normalized) {
      return "";
    }
    if (normalized === "browser_snapshot") {
      return "snapshot";
    }
    if (normalized.includes("search") || normalized.includes("grep")) {
      return "search";
    }
    if (normalized.includes("list") || normalized.includes("dir")) {
      return "directory";
    }
    if (FILE_TOOL_NAMES.has(normalized)) {
      return "file";
    }
    return "tool";
  }

  private artifactBodyFromPayload(payload: Record<string, unknown>, summary: string): string {
    const preferredText = this.extractText(payload);
    if (preferredText.trim()) {
      return preferredText.trim();
    }
    if (summary.trim()) {
      return summary.trim();
    }
    return this.prettyJson(payload);
  }

  private artifactPreviewText(artifact: Artifact): string {
    return artifact.body || this.prettyJson(artifact.payload);
  }

  private extractText(value: unknown): string {
    if (typeof value === "string") {
      return value;
    }
    if (Array.isArray(value)) {
      return value.map((item) => this.extractText(item)).filter(Boolean).join("\n");
    }
    if (!value || typeof value !== "object") {
      return "";
    }
    const record = value as Record<string, unknown>;
    for (const key of [
      "content",
      "text",
      "body",
      "result",
      "output",
      "output_text",
      "stdout",
      "stderr",
      "aggregatedOutput",
      "aggregated_output",
      "markdown",
      "raw",
    ]) {
      const candidate = record[key];
      if (typeof candidate === "string" && candidate.trim()) {
        return candidate;
      }
    }
    if (Array.isArray(record.lines)) {
      return record.lines
        .map((line) => this.extractText(line))
        .filter(Boolean)
        .join("\n");
    }
    return "";
  }

  private extractPath(payload: Record<string, unknown>): string {
    for (const key of ["path", "file_path", "target_path", "dir_path", "url"]) {
      const value = payload[key];
      if (typeof value === "string" && value.trim()) {
        return value.trim();
      }
    }
    return "";
  }

  private asRecord(value: unknown): Record<string, unknown> {
    return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
  }

  private prettyJson(value: unknown): string {
    try {
      return JSON.stringify(value ?? {}, null, 2);
    } catch {
      return String(value ?? "");
    }
  }

  private prettyName(value: string): string {
    return value
      .replaceAll(/[_\-.]+/g, " ")
      .replaceAll(/\s+/g, " ")
      .trim()
      .replace(/^./, (match) => match.toUpperCase());
  }

  private modeHelpText(): string {
    switch (this.commandMode) {
      case "shell":
        return "Shell mode keeps the composer focused on OS commands. Use it for repository inspection and local actions.";
      case "files":
        return "File mode centers file reads and searches. The right inspector mirrors file-like tool output.";
      default:
        return "Task mode keeps the composer aligned with AgentHub task execution and chat handoff.";
    }
  }

  private commandPlaceholder(): string {
    switch (this.commandMode) {
      case "shell":
        return "Run an OS command, for example: rg -n TODO .";
      case "files":
        return "Read or search workspace files, for example: /read_file README.md";
      default:
        return "Describe a task, for example: inspect the latest approval flow";
    }
  }

  private runButtonLabel(): string {
    return this.commandMode === "shell" ? "Run shell" : this.commandMode === "files" ? "Run files" : "Run task";
  }

  private runButtonTooltip(): string {
    return this.commandMode === "shell"
      ? "Run the current shell command"
      : this.commandMode === "files"
        ? "Run the current file operation"
        : "Run the current task";
  }

  private quickTemplateButtons() {
    switch (this.commandMode) {
      case "shell":
        return [
          { label: "pwd", icon: "⌂", template: "pwd", tooltip: "Show the current working directory" },
          { label: "git status", icon: "⎇", template: "git status --short", tooltip: "Inspect repository status" },
          { label: "search", icon: "⌕", template: "rg -n TODO .", tooltip: "Search the workspace" },
        ];
      case "files":
        return [
          { label: "read README", icon: "▣", template: "/read_file README.md", tooltip: "Open README.md" },
          { label: "list root", icon: "≡", template: "/list_dir .", tooltip: "List the workspace root" },
          { label: "search files", icon: "⌕", template: "/file_search AgentHub", tooltip: "Search for files" },
        ];
      default:
        return [
          { label: "inspect", icon: "⌘", template: "inspect the selected thread", tooltip: "Build a task prompt" },
          { label: "compare", icon: "⇄", template: "compare the current and previous output", tooltip: "Compare outputs" },
          { label: "follow up", icon: "↩", template: "follow up on the latest file read", tooltip: "Continue the workflow" },
        ];
    }
  }

  private insertTemplate(template: string) {
    this.commandDraft = template;
    void this.focusComposer();
  }

  private async focusComposer() {
    await this.updateComplete;
    const composer = this.renderRoot.querySelector("[data-testid='warp-command-composer']") as HTMLTextAreaElement | null;
    composer?.focus();
  }

  private handleComposerInput = (event: Event) => {
    this.commandDraft = (event.target as HTMLTextAreaElement).value;
  };

  private handleComposerKeydown = (event: KeyboardEvent) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void this.submitDraft();
    }
    if (event.key === "Escape") {
      event.preventDefault();
      if (this.activeTaskId) {
        void this.stopTask();
      } else if (this.commandDraft.trim()) {
        this.clearDraft();
      }
    }
  };

  private handleCommandModeChange = (event: CustomEvent<{ value: CommandMode }>) => {
    this.commandMode = event.detail.value;
    this.commandDraft = this.commandDraft.trim();
    void this.focusComposer();
  };

  private handleInspectorChange = (event: CustomEvent<{ value: InspectorTab }>) => {
    this.inspectorTab = event.detail.value;
  };

  private handleBrowserHeadlessToggle = async (event: CustomEvent<{ checked: boolean }>) => {
    await this.updateSettings({ browserHeadless: event.detail.checked });
  };

  private handlePluginAutoLoadToggle = async (event: CustomEvent<{ checked: boolean }>) => {
    await this.updateSettings({ pluginAutoLoad: event.detail.checked });
  };

  private handleShowPayloadsToggle = (event: CustomEvent<{ checked: boolean }>) => {
    this.showPayloads = event.detail.checked;
  };

  private handleCompactTranscriptToggle = (event: CustomEvent<{ checked: boolean }>) => {
    this.compactTranscript = event.detail.checked;
  };

  private async updateSettings(partial: Partial<SettingsSnapshot>) {
    const response = await this.bridgeClient.settings.update(partial);
    if (!response.ok) {
      this.runFeedback = errorFeedback(response.error?.message ?? "settings update failed");
      return;
    }
    this.settings = response.data ?? this.settings;
    this.runFeedback = feedbackFromBridgeResponse(response, {
      successMessage: "Settings updated",
      errorMessage: "settings update failed",
    });
  }

  private clearDraft() {
    this.commandDraft = "";
    void this.focusComposer();
  }

  private async submitDraft() {
    const text = this.commandDraft.trim();
    if (!text) {
      this.runFeedback = neutralFeedback("Compose a command or task before running it.");
      return;
    }
    if (this.commandMode === "shell") {
      await this.submitShellDraft(text);
      return;
    }
    const response = await this.bridgeClient.task.run({ text });
    this.runFeedback = feedbackFromBridgeResponse(response, {
      successMessage: "Task submitted",
      errorMessage: "task submission failed",
    });
    if (!response.ok) {
      return;
    }
    this.activeTaskId = response.data?.task_id ?? "";
    this.commandDraft = "";
    if (response.data?.thread_id) {
      this.selectedThreadId = response.data.thread_id;
    }
    await this.refreshThreadList(response.data?.thread_id ?? undefined);
  }

  private async submitShellDraft(command: string) {
    const response = await this.bridgeClient.shell.run({
      command,
      cwd: this.settings?.workspaceRoot,
      timeout_ms: 60000,
    });
    if (!response.ok) {
      this.runFeedback = errorFeedback(response.error?.message ?? "shell command failed");
      return;
    }
    this.runFeedback =
      response.data?.ok === false
        ? warningFeedback(`Shell exited ${response.data.exit_code ?? "with error"}`)
        : successFeedback("Shell command completed");
    this.commandDraft = "";
    this.activeTaskId = "";
    if (response.data) {
      this.appendShellRunResult(command, response.data);
    }
    if (response.data?.thread_id) {
      this.selectedThreadId = response.data.thread_id;
    }
    await this.refreshThreadList(response.data?.thread_id ?? undefined);
  }

  private appendShellRunResult(command: string, result: ShellRunResult) {
    const timestamp = new Date().toISOString();
    const userText = result.user_text?.trim() || `/shell ${command}`;
    const toolEvents = result.tool_events?.length
      ? result.tool_events
      : [
          {
            name: "shell",
            ok: result.ok !== false,
            summary: result.status || `shell rc=${result.exit_code ?? 0}`,
            payload: {
              command,
              cwd: result.cwd ?? "",
              stdout: result.stdout ?? "",
              stderr: result.stderr ?? "",
              exit_code: result.exit_code ?? null,
              duration_ms: result.duration_ms ?? null,
              status: result.status ?? "",
            },
          },
        ];
    const shellEntries: TranscriptEntry[] = [
      {
        id: `shell-${timestamp}-user`,
        kind: "user",
        title: "User",
        body: userText,
        meta: [timestamp, "shell"].filter(Boolean),
      },
      ...toolEvents.map((event, index) => this.transcriptToolEntry(Date.now(), index, event)),
    ];
    this.transcript = [...this.transcript, ...shellEntries];
    const artifacts = toolEvents
      .map((event, index) => this.artifactFromToolEvent(event, Date.now(), index))
      .filter((artifact): artifact is Artifact => artifact !== null);
    if (artifacts.length) {
      this.artifacts = [...artifacts, ...this.artifacts];
      this.selectedArtifactId = artifacts[0]?.id ?? this.selectedArtifactId;
    }
    if (result.thread_id) {
      this.selectedThreadTitle = result.thread_id;
    }
  }

  private async stopTask() {
    if (!this.activeTaskId) {
      return;
    }
    const response = await this.bridgeClient.task.stop({ task_id: this.activeTaskId });
    this.runFeedback = feedbackFromBridgeResponse(response, {
      successMessage: "Task stopped",
      errorMessage: "task stop failed",
    });
    if (response.ok) {
      this.activeTaskId = "";
    }
  }

  private async refreshThreadList(preferThreadId?: string) {
    const response = await this.bridgeClient.thread.list({ limit: 12 });
    if (!response.ok) {
      return;
    }
    this.threads = response.data?.threads ?? [];
    const nextThreadId =
      preferThreadId && this.threads.some((thread) => thread.thread_id === preferThreadId)
        ? preferThreadId
        : response.data?.active_thread_id || this.threads[0]?.thread_id || "";
    if (nextThreadId) {
      this.selectedThreadId = nextThreadId;
      await this.loadSelectedThread();
    }
  }

  private async selectThread(threadId: string) {
    this.selectedThreadId = threadId;
    await this.loadSelectedThread();
  }

  private async reloadSelectedThread() {
    if (!this.selectedThreadId) {
      return;
    }
    await this.loadSelectedThread();
  }

  private startFreshThread() {
    this.selectedThreadId = "";
    this.selectedThreadTitle = "new thread";
    this.transcript = [];
    this.artifacts = [];
    this.selectedArtifactId = "";
    this.commandDraft = "";
    this.activeTaskId = "";
    this.runFeedback = neutralFeedback("Fresh thread ready.");
    void this.focusComposer();
  }

  private selectArtifact(artifactId: string) {
    this.selectedArtifactId = artifactId;
  }

  private openArtifactDialog(artifact: Artifact) {
    this.dialogArtifact = artifact;
    this.fileDialogOpen = true;
  }

  private closeArtifactDialog = () => {
    this.fileDialogOpen = false;
    this.dialogArtifact = null;
  };

  private navigateToRoute(route: WorkbenchRouteId) {
    this.dispatchEvent(
      new CustomEvent("route-change", {
        detail: route,
        bubbles: true,
        composed: true,
      }),
    );
  }

  private handleBridgeEvent = (event: BridgeEvent<Record<string, unknown>>) => {
    const kind = String(event.kind || "");
    if (kind === "task_completed" || kind === "task_failed" || kind === "settings_changed") {
      void this.refreshAll();
    }
  };

  private async pollGatewayEvents() {
    if (this.loading) {
      return;
    }
    const response = await this.bridgeClient.gateway.events.poll({
      cursor: this.gatewayCursor,
      streams: ["gateway_events", "approvals", "audit"],
    });
    if (!response.ok) {
      return;
    }
    this.gatewayCursor = response.data?.cursor ?? this.gatewayCursor;
    const nextEvents = response.data?.events ?? [];
    if (!nextEvents.length) {
      return;
    }
    this.gatewayEvents = [...nextEvents, ...this.gatewayEvents].slice(0, 12);
  }

  private previewTitle(artifact: Artifact): string {
    return artifact.path || artifact.title;
  }

  private renderLineNumbers(text: string) {
    const lines = this.linesFor(text);
    return lines.map((_, index) => html`<span>${index + 1}</span>`);
  }

  private linesFor(text: string) {
    return (text || this.prettyJson({})).split("\n");
  }

  private dialogSubtitle(artifact: Artifact): string {
    return [artifact.toolName, artifact.path].filter(Boolean).join(" · ");
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "warp-workbench-page": WarpWorkbenchPage;
  }
}
