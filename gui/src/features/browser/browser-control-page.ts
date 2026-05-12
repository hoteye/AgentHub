import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { BridgeClient, createMockBridgeClient } from "../../bridge/client.ts";
import "../../shared/components/operation-feedback-view.ts";
import type { BridgeEvent } from "../../shared/types/bridge.ts";
import {
  feedbackFromBridgeResponse,
  neutralFeedback,
  successFeedback,
  warningFeedback,
  type OperationFeedback,
} from "../../shared/state/operation-feedback.ts";

type BrowserTabItem = {
  tab_id: string;
  title: string;
  url: string;
};

type BrowserRefItem = {
  ref: string;
  role: string;
  text?: string;
  name?: string;
  url?: string;
};

type ConsoleEntry = {
  level: string;
  text?: string;
  message?: string;
};

type RequestEntry = {
  method?: string;
  status?: string | number;
  url?: string;
  resource_type?: string;
  outcome?: string;
  message?: string;
};

type ErrorEntry = {
  level?: string;
  message?: string;
  text?: string;
  source?: string;
  url?: string;
};

type CausalityRecord = {
  trace_id?: string;
  stage?: string;
  status?: string;
  summary?: string;
  approval_id?: string;
  action_id?: string;
};

@customElement("browser-control-page")
export class BrowserControlPage extends LitElement {
  private unsubscribeBridge: (() => void) | null = null;

  static styles = css`
    :host {
      display: block;
    }

    .grid {
      display: grid;
      grid-template-columns: 0.95fr 1.1fr 0.95fr;
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

    h2,
    h3 {
      color: #eef6fa;
    }

    h2 {
      font-size: 18px;
    }

    h3 {
      font-size: 15px;
    }

    .hint,
    .status,
    .meta {
      color: #a6bcc7;
      font-size: 14px;
      line-height: 1.55;
    }

    .status {
      display: grid;
      gap: 8px;
    }

    .stack {
      display: grid;
      gap: 12px;
    }

    .field {
      display: grid;
      gap: 8px;
    }

    .field.inline {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }

    .tab,
    .ref,
    .console,
    .diag,
    .causality-item,
    .result {
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(17, 32, 43, 0.74);
      color: #c7d6df;
      font-size: 13px;
      line-height: 1.55;
      border: 1px solid transparent;
    }

    .tab.active,
    .ref.active,
    .result.active {
      border-color: rgba(111, 203, 193, 0.36);
      box-shadow: 0 0 0 1px rgba(111, 203, 193, 0.14) inset;
    }

    .result.success {
      border-color: rgba(76, 175, 139, 0.26);
    }

    .result.warning {
      border-color: rgba(234, 183, 94, 0.26);
    }

    .result.error {
      border-color: rgba(218, 97, 97, 0.26);
    }

    .row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
    }

    input,
    select,
    textarea {
      width: 100%;
      border-radius: 12px;
      border: 1px solid rgba(150, 186, 196, 0.18);
      background: rgba(6, 16, 22, 0.92);
      color: #eef5f8;
      padding: 10px 12px;
      font: inherit;
      box-sizing: border-box;
    }

    textarea {
      min-height: 88px;
      resize: vertical;
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
      background: rgba(26, 50, 63, 0.95);
      color: #d8e8ee;
    }

    .pill {
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      background: rgba(234, 183, 94, 0.14);
      color: #ffd486;
    }

    .checkbox {
      display: flex;
      align-items: center;
      gap: 10px;
      color: #d7e6ec;
    }

    .checkbox input {
      width: auto;
      margin: 0;
    }

    .metrics {
      display: grid;
      gap: 8px;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    }

    .metric {
      border-radius: 14px;
      border: 1px solid rgba(150, 186, 196, 0.14);
      background: rgba(13, 27, 36, 0.9);
      padding: 10px 12px;
      display: grid;
      gap: 6px;
      font-size: 13px;
    }

    .metric strong {
      color: #f1f7fa;
      font-size: 18px;
      letter-spacing: 0.03em;
    }

    .diag strong,
    .causality-item strong {
      color: #f2f8fb;
      font-size: 13px;
    }

    .causality-input {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: center;
    }

    @media (max-width: 1160px) {
      .grid {
        grid-template-columns: 1fr;
      }
    }
  `;

  @property({ attribute: false }) bridgeClient: BridgeClient = createMockBridgeClient();

  @state() private running = false;
  @state() private activeProfile = "-";
  @state() private tabs: BrowserTabItem[] = [];
  @state() private selectedTabId = "";
  @state() private lastKnownTabId = "";
  @state() private refs: BrowserRefItem[] = [];
  @state() private consoleEntries: ConsoleEntry[] = [];
  @state() private requestEntries: RequestEntry[] = [];
  @state() private errorEntries: ErrorEntry[] = [];
  @state() private traceId = "";
  @state() private approvalItems: Array<{ approval_id: string; title: string; trace_id: string; status: string }> = [];
  @state() private causalityRecords: CausalityRecord[] = [];
  @state() private transportHint = "bridge-http";
  @state() private profileHint = "-";
  @state() private proxyHint = "unknown";
  @state() private openUrl = "https://example.test/dashboard";
  @state() private navigateUrl = "https://example.test/approvals";
  @state() private actionKind = "click";
  @state() private actionRef = "";
  @state() private actionValue = "";
  @state() private actionAuxValue = "";
  @state() private lastResult: OperationFeedback = neutralFeedback("尚未执行浏览器动作");
  @state() private artifactFeedback: OperationFeedback = neutralFeedback("尚未生成 artifact");
  @state() private syncFeedback: OperationFeedback = neutralFeedback("尚未同步浏览器状态");
  @state() private causalityFeedback: OperationFeedback = neutralFeedback("尚未加载审批因果链");
  @state() private downloadPath = "/tmp/browser_download.txt";
  @state() private uploadPaths = "/tmp/demo_upload.txt";
  @state() private dialogPrompt = "confirmed by gui";
  @state() private dialogAccept = true;

  connectedCallback(): void {
    super.connectedCallback();
    void this.load();
    this.unsubscribeBridge = this.bridgeClient.subscribe((event) => {
      this.handleBridgeEvent(event);
    });
  }

  disconnectedCallback(): void {
    this.unsubscribeBridge?.();
    this.unsubscribeBridge = null;
    super.disconnectedCallback();
  }

  render() {
    const selectedTab = this.tabs.find((item) => item.tab_id === this.selectedTabId) ?? null;
    return html`
      <section class="grid">
        <article class="panel">
          <h2>浏览器状态与页签</h2>
          <div class="metrics">
            <article class="metric" data-testid="browser-metric-running">
              <span>runtime</span>
              <strong>${this.running ? "running" : "stopped"}</strong>
              <span>${this.transportHint}</span>
            </article>
            <article class="metric" data-testid="browser-metric-profile">
              <span>profile</span>
              <strong>${this.activeProfile}</strong>
              <span>hint=${this.profileHint}</span>
            </article>
            <article class="metric" data-testid="browser-metric-proxy">
              <span>proxy</span>
              <strong>${this.proxyHint}</strong>
              <span>tabs=${this.tabs.length}</span>
            </article>
          </div>
          <div class="status">
            <div>running=${String(this.running)}</div>
            <div>profile=${this.activeProfile}</div>
            <div>tabs=${this.tabs.length}</div>
            <div>selected=${this.selectedTabId || "-"}</div>
            <operation-feedback-view
              data-testid="browser-sync-feedback"
              .feedback=${this.syncFeedback}
            ></operation-feedback-view>
          </div>
          <div class="actions">
            <button data-testid="browser-start" type="button" @click=${this.startBrowser}>启动</button>
            <button data-testid="browser-stop" class="secondary" type="button" @click=${this.stopBrowser}>
              停止
            </button>
            <button data-testid="browser-refresh" class="secondary" type="button" @click=${this.load}>
              刷新状态
            </button>
          </div>
          <div class="stack">
            ${this.tabs.map(
              (tab) => html`
                <section class="tab ${this.selectedTabId === tab.tab_id ? "active" : ""}">
                  <div class="row">
                    <strong>${tab.title}</strong>
                    <span class="pill">${tab.tab_id}</span>
                  </div>
                  <div>${tab.url}</div>
                  <div class="actions">
                    <button class="secondary" type="button" @click=${() => this.focusTab(tab.tab_id)}>切换</button>
                    <button class="secondary" type="button" @click=${() => this.closeTab(tab.tab_id)}>关闭</button>
                  </div>
                </section>
              `,
            )}
          </div>
        </article>

        <article class="panel">
          <h2>导航与动作</h2>
          <div class="stack">
            <label class="field">
              <span class="hint">打开新页签</span>
              <input data-testid="browser-open-url" .value=${this.openUrl} @input=${this.handleOpenUrlInput} />
            </label>
            <div class="actions">
              <button data-testid="browser-open" type="button" @click=${this.openTab}>打开</button>
            </div>
            <label class="field">
              <span class="hint">导航当前页签</span>
              <input
                data-testid="browser-navigate-url"
                .value=${this.navigateUrl}
                @input=${this.handleNavigateUrlInput}
              />
            </label>
            <div class="actions">
              <button data-testid="browser-navigate" type="button" @click=${this.navigateTab}>导航</button>
              <button data-testid="browser-snapshot" class="secondary" type="button" @click=${this.refreshSnapshot}>
                刷新快照
              </button>
            </div>
            <div class="field">
              <span class="hint">基础动作</span>
              <select data-testid="browser-action-kind" .value=${this.actionKind} @change=${this.handleActionKindChange}>
                <option value="click">click</option>
                <option value="double_click">double_click</option>
                <option value="type">type</option>
                <option value="fill">fill</option>
                <option value="press">press</option>
                <option value="hover">hover</option>
                <option value="focus">focus</option>
                <option value="clear">clear</option>
                <option value="check">check</option>
                <option value="uncheck">uncheck</option>
                <option value="wait">wait</option>
                <option value="scroll_into_view">scroll_into_view</option>
                <option value="drag">drag</option>
                <option value="resize">resize</option>
                <option value="select">select</option>
              </select>
            </div>
            <label class="field">
              <span class="hint">${this.primaryActionLabel}</span>
              <input data-testid="browser-action-ref" .value=${this.actionRef} @input=${this.handleActionRefInput} />
            </label>
            <label class="field">
              <span class="hint">${this.primaryValueLabel}</span>
              ${this.actionKind === "fill"
                ? html`
                    <textarea
                      data-testid="browser-action-value"
                      .value=${this.actionValue}
                      @input=${this.handleActionValueInput}
                    ></textarea>
                  `
                : html`
                    <input
                      data-testid="browser-action-value"
                      .value=${this.actionValue}
                      @input=${this.handleActionValueInput}
                    />
                  `}
            </label>
            ${this.secondaryValueLabel
              ? html`
                  <label class="field">
                    <span class="hint">${this.secondaryValueLabel}</span>
                    <input
                      data-testid="browser-action-aux"
                      .value=${this.actionAuxValue}
                      @input=${this.handleActionAuxInput}
                    />
                  </label>
                `
              : null}
            <div class="actions">
              <button data-testid="browser-act" type="button" @click=${this.performAction}>执行动作</button>
              <button data-testid="browser-screenshot" class="secondary" type="button" @click=${this.takeScreenshot}>
                截图
              </button>
              <button data-testid="browser-pdf" class="secondary" type="button" @click=${this.exportPdf}>导出 PDF</button>
            </div>
            <h3>高级动作与 Artifact</h3>
            <label class="field">
              <span class="hint">下载输出路径</span>
              <input data-testid="browser-download-path" .value=${this.downloadPath} @input=${this.handleDownloadPathInput} />
            </label>
            <div class="actions">
              <button data-testid="browser-download" class="secondary" type="button" @click=${this.downloadByRef}>
                下载
              </button>
              <button
                data-testid="browser-wait-download"
                class="secondary"
                type="button"
                @click=${this.waitForDownload}
              >
                等待下载
              </button>
            </div>
            <label class="field">
              <span class="hint">上传文件路径，逗号分隔</span>
              <input data-testid="browser-upload-paths" .value=${this.uploadPaths} @input=${this.handleUploadPathsInput} />
            </label>
            <div class="actions">
              <button data-testid="browser-upload" class="secondary" type="button" @click=${this.uploadFiles}>
                上传
              </button>
            </div>
            <label class="field">
              <span class="hint">Dialog prompt 文本</span>
              <input data-testid="browser-dialog-prompt" .value=${this.dialogPrompt} @input=${this.handleDialogPromptInput} />
            </label>
            <label class="checkbox">
              <input
                data-testid="browser-dialog-accept"
                type="checkbox"
                .checked=${this.dialogAccept}
                @change=${this.handleDialogAcceptChange}
              />
              <span>接受对话框</span>
            </label>
            <div class="actions">
              <button data-testid="browser-dialog" class="secondary" type="button" @click=${this.respondDialog}>
                处理对话框
              </button>
            </div>
          </div>
          <section class="result active ${this.lastResult.level}" data-testid="browser-result">
            <operation-feedback-view
              data-testid="browser-result-feedback"
              title="执行回显"
              variant="stack"
              .feedback=${this.lastResult}
            ></operation-feedback-view>
          </section>
          <section class="result ${this.artifactFeedback.level}" data-testid="browser-artifact">
            <operation-feedback-view
              data-testid="browser-artifact-feedback"
              title="Artifact"
              variant="stack"
              .feedback=${this.artifactFeedback}
            ></operation-feedback-view>
          </section>
        </article>

        <aside class="panel">
          <h2>页面快照与控制台</h2>
          ${selectedTab
            ? html`<p class="hint">当前页签：${selectedTab.title} · ${selectedTab.url}</p>`
            : html`<p class="hint">当前没有可操作页签。</p>`}
          <div class="stack">
            ${this.refs.map(
              (ref) => html`
                <section
                  class="ref ${this.actionRef === ref.ref ? "active" : ""}"
                  data-testid="browser-ref-card"
                  data-ref=${ref.ref}
                >
                  <div class="row">
                    <strong>${ref.ref}</strong>
                    <span class="pill">${ref.role}</span>
                  </div>
                  <div>${ref.text ?? ref.name ?? ref.url ?? "-"}</div>
                  <div class="actions">
                    <button
                      class="secondary"
                      data-testid="browser-ref-pick"
                      type="button"
                      @click=${() => this.pickRef(ref.ref)}
                    >
                      选中 ref
                    </button>
                    <button
                      class="secondary"
                      data-testid="browser-ref-quick-click"
                      type="button"
                      @click=${() => this.quickClick(ref.ref)}
                    >
                      点击
                    </button>
                  </div>
                </section>
              `,
            )}
          </div>
          <h3>Console</h3>
          <div class="stack">
            ${this.consoleEntries.map(
              (entry) => html`
                <section class="console">
                  <strong>${entry.level}</strong>
                  <div>${entry.text ?? entry.message ?? "-"}</div>
                </section>
              `,
            )}
          </div>
          <h3>Requests</h3>
          <div class="stack">
            ${this.requestEntries.length
              ? this.requestEntries.map(
                  (entry) => html`
                    <section class="diag" data-testid="browser-request-card">
                      <strong>${entry.method ?? "-"} ${String(entry.status ?? "-")}</strong>
                      <div>${entry.url ?? "-"}</div>
                      <div class="meta">resource=${entry.resource_type ?? "-"} · outcome=${entry.outcome ?? "-"}</div>
                    </section>
                  `,
                )
              : html`<section class="diag" data-testid="browser-request-empty">当前没有 requests 诊断数据。</section>`}
          </div>
          <h3>Errors</h3>
          <div class="stack">
            ${this.errorEntries.length
              ? this.errorEntries.map(
                  (entry) => html`
                    <section class="diag" data-testid="browser-error-card">
                      <strong>${entry.level ?? "error"} · ${entry.source ?? "runtime"}</strong>
                      <div>${entry.message ?? entry.text ?? "-"}</div>
                      <div class="meta">${entry.url ?? "-"}</div>
                    </section>
                  `,
                )
              : html`<section class="diag" data-testid="browser-error-empty">当前没有 errors 诊断数据。</section>`}
          </div>
          <h3>Causality</h3>
          <div class="causality-input">
            <input
              data-testid="browser-trace-id"
              .value=${this.traceId}
              @input=${this.handleTraceIdInput}
              placeholder="trace_id"
            />
            <button data-testid="browser-causality-refresh" class="secondary" type="button" @click=${this.refreshCausality}>
              刷新因果链
            </button>
          </div>
          <operation-feedback-view
            data-testid="browser-causality-feedback"
            title="审批与审计"
            variant="stack"
            .feedback=${this.causalityFeedback}
          ></operation-feedback-view>
          <div class="stack">
            ${this.approvalItems.length
              ? this.approvalItems.map(
                  (item) => html`
                    <section class="causality-item" data-testid="browser-approval-card">
                      <strong>${item.title}</strong>
                      <div class="meta">approval=${item.approval_id} · status=${item.status}</div>
                      <div class="meta">trace=${item.trace_id}</div>
                      <div class="actions">
                        <button
                          data-testid="browser-pick-trace"
                          class="secondary"
                          type="button"
                          @click=${() => this.pickTrace(item.trace_id)}
                        >
                          使用 trace
                        </button>
                      </div>
                    </section>
                  `,
                )
              : html`<section class="causality-item">当前没有待处理审批。</section>`}
            ${this.causalityRecords.map(
              (item) => html`
                <section class="causality-item" data-testid="browser-causality-card">
                  <strong>${item.stage ?? "audit"} · ${item.status ?? "-"}</strong>
                  <div>${item.summary ?? "-"}</div>
                  <div class="meta">approval=${item.approval_id ?? "-"} · action=${item.action_id ?? "-"}</div>
                </section>
              `,
            )}
          </div>
        </aside>
      </section>
    `;
  }

  private async load() {
    const status = await this.bridgeClient.browser.status();
    const statusProfile = (status.data as { activeProfile?: string; profile?: string } | null)?.activeProfile
      ?? (status.data as { activeProfile?: string; profile?: string } | null)?.profile
      ?? "";
    const [tabs, consoleData, profiles] = await Promise.all([
      this.bridgeClient.browser.tabs(),
      this.bridgeClient.browser.console({ limit: 8 }),
      this.bridgeClient.browser.proxy({ method: "GET", path: "/profiles" }),
    ]);
    const failures = [status, tabs, consoleData, profiles]
      .filter((response) => !response.ok)
      .map((response) => response.error?.message)
      .filter((item): item is string => Boolean(item));
    this.running = Boolean(status.data?.running);
    this.activeProfile = (status.data as { activeProfile?: string; profile?: string } | null)?.activeProfile
      ?? (status.data as { activeProfile?: string; profile?: string } | null)?.profile
      ?? "-";
    this.profileHint = this.activeProfile === "-" ? "no-active-profile" : "active-profile";
    let resolvedTabs = tabs.data?.tabs ?? [];
    const resolvedProfile = String(statusProfile).trim();
    if (resolvedProfile && resolvedTabs.length === 0) {
      const profileTabs = await this.bridgeClient.browser.proxy({
        method: "GET",
        path: "/tabs",
        query: { profile: resolvedProfile },
      });
      const parsedTabs = this.parseProxyTabs(profileTabs.data?.result ?? {});
      if (parsedTabs.length > 0) {
        resolvedTabs = parsedTabs;
      }
    }
    this.tabs = resolvedTabs;
    this.consoleEntries = consoleData.data?.entries ?? [];
    this.proxyHint = profiles.ok && profiles.data?.status === 200 ? "proxy-ready" : "proxy-limited";
    this.transportHint = profiles.ok ? "gateway-browser-proxy" : "bridge-fallback";
    const selectedExists = this.selectedTabId && this.tabs.some((item) => item.tab_id === this.selectedTabId);
    if (selectedExists) {
      this.lastKnownTabId = this.selectedTabId;
    } else if (this.tabs[0]?.tab_id) {
      this.selectedTabId = this.tabs[0].tab_id;
      this.lastKnownTabId = this.selectedTabId;
    } else if (!this.running) {
      this.selectedTabId = "";
      this.lastKnownTabId = "";
    }
    this.syncFeedback = failures.length
      ? warningFeedback(`状态同步不完整: ${failures.join("；")}`)
      : successFeedback(`浏览器状态已同步: ${this.tabs.length} tabs`);
    await this.loadSnapshot();
    await this.loadProxyDiagnostics();
    await this.loadCausality();
  }

  private async loadSnapshot() {
    const targetId = this.resolveTargetId();
    if (!targetId) {
      this.refs = [];
      this.syncFeedback = warningFeedback("当前没有活动页签，无法刷新快照");
      return;
    }
    const snapshot = await this.bridgeClient.browser.snapshot({ target_id: targetId });
    this.refs = snapshot.data?.refs ?? [];
    const resolvedTarget = this.extractTargetId(snapshot);
    if (resolvedTarget) {
      this.selectedTabId = resolvedTarget;
      this.lastKnownTabId = resolvedTarget;
    }
    if (!snapshot.ok) {
      this.syncFeedback = warningFeedback(snapshot.error?.message ?? "快照刷新失败");
    }
    if (!this.actionRef && this.refs[0]?.ref) {
      this.actionRef = this.refs[0].ref;
    }
  }

  private readonly handleOpenUrlInput = (event: Event) => {
    this.openUrl = (event.target as HTMLInputElement).value;
  };

  private readonly handleNavigateUrlInput = (event: Event) => {
    this.navigateUrl = (event.target as HTMLInputElement).value;
  };

  private readonly handleActionKindChange = (event: Event) => {
    this.actionKind = (event.target as HTMLSelectElement).value;
  };

  private readonly handleActionRefInput = (event: Event) => {
    this.actionRef = (event.target as HTMLInputElement).value;
  };

  private readonly handleActionValueInput = (event: Event) => {
    this.actionValue = (event.target as HTMLInputElement).value;
  };

  private readonly handleActionAuxInput = (event: Event) => {
    this.actionAuxValue = (event.target as HTMLInputElement).value;
  };

  private readonly handleDownloadPathInput = (event: Event) => {
    this.downloadPath = (event.target as HTMLInputElement).value;
  };

  private readonly handleUploadPathsInput = (event: Event) => {
    this.uploadPaths = (event.target as HTMLInputElement).value;
  };

  private readonly handleDialogPromptInput = (event: Event) => {
    this.dialogPrompt = (event.target as HTMLInputElement).value;
  };

  private readonly handleDialogAcceptChange = (event: Event) => {
    this.dialogAccept = (event.target as HTMLInputElement).checked;
  };

  private readonly handleTraceIdInput = (event: Event) => {
    this.traceId = (event.target as HTMLInputElement).value.trim();
  };

  private readonly startBrowser = async () => {
    const profile = this.resolveProfileHint();
    const response = await this.bridgeClient.browser.start(profile ? { profile } : {});
    this.lastResult = feedbackFromBridgeResponse(response, {
      successMessage: "浏览器已启动",
      errorMessage: "浏览器启动失败",
    });
    await this.waitForRunningState(true);
    await this.load();
  };

  private readonly stopBrowser = async () => {
    const profile = this.resolveProfileHint();
    const response = await this.bridgeClient.browser.stop(profile ? { profile } : {});
    const stopped = await this.waitForRunningState(false, 15000);
    this.lastResult = feedbackFromBridgeResponse(response, {
      successMessage: "浏览器已停止",
      errorMessage: "浏览器停止失败",
    });
    if (response.ok && !stopped) {
      this.lastResult = warningFeedback("停止请求已发送，但运行态仍在同步中");
    }
    await this.load();
  };

  private readonly openTab = async () => {
    const url = this.openUrl.trim();
    if (!url) {
      this.lastResult = warningFeedback("请输入需要打开的 URL");
      return;
    }
    const profile = this.resolveProfileHint();
    const openPayload = profile
      ? ({ url, profile } as { url: string })
      : { url };
    const response = await this.bridgeClient.browser.open(openPayload);
    const resolvedTarget = this.extractTargetId(response);
    if (resolvedTarget) {
      this.selectedTabId = resolvedTarget;
      this.lastKnownTabId = resolvedTarget;
    }
    if (response.ok) {
      this.lastResult = successFeedback(`已请求打开 ${url}`);
    } else {
      this.lastResult = feedbackFromBridgeResponse(response, {
        successMessage: `已打开 ${url}`,
        errorMessage: "打开页签失败",
      });
      await this.load();
      return;
    }
    const synced = await this.waitForTabToAppear({ targetId: resolvedTarget, url, profile });
    this.lastResult = successFeedback(synced ? `已打开 ${url}` : `已请求打开 ${url}，页签同步中`);
    await this.load();
  };

  private readonly navigateTab = async () => {
    const targetId = this.resolveTargetId();
    if (!targetId) {
      this.lastResult = warningFeedback("当前没有可导航页签");
      return;
    }
    await this.bridgeClient.browser.focus({ target_id: targetId });
    const response = await this.bridgeClient.browser.navigate({ tab_id: targetId, url: this.navigateUrl });
    this.lastResult = feedbackFromBridgeResponse(response, {
      successMessage: `已导航到 ${this.navigateUrl}`,
      errorMessage: "导航失败",
    });
    await this.load();
  };

  private readonly refreshSnapshot = async () => {
    await this.loadSnapshot();
    const targetId = this.resolveTargetId();
    this.lastResult = targetId
      ? successFeedback(`已刷新 ${targetId} 快照`)
      : warningFeedback("当前没有活动页签");
  };

  private readonly focusTab = async (tabId: string) => {
    this.selectedTabId = tabId;
    this.lastKnownTabId = tabId;
    await this.bridgeClient.browser.focus({ target_id: tabId });
    this.lastResult = successFeedback(`已切换到 ${tabId}`);
    await this.load();
  };

  private readonly closeTab = async (tabId: string) => {
    const response = await this.bridgeClient.browser.close({ target_id: tabId });
    this.lastResult = feedbackFromBridgeResponse(response, {
      successMessage: `已关闭 ${tabId}`,
      errorMessage: "关闭页签失败",
    });
    if (this.selectedTabId === tabId) {
      this.selectedTabId = "";
    }
    if (this.lastKnownTabId === tabId) {
      this.lastKnownTabId = "";
    }
    await this.load();
  };

  private readonly performAction = async () => {
    const targetId = this.resolveTargetId();
    if (!targetId) {
      this.lastResult = warningFeedback("当前没有可操作页签");
      return;
    }
    const payload: Parameters<BridgeClient["browser"]["act"]>[0] = {
      target_id: targetId,
      action: this.actionKind,
      ref: this.actionRef || undefined,
    };
    if (this.actionKind === "type") {
      payload.value = this.actionValue;
    } else if (this.actionKind === "fill") {
      payload.fields = this.parseFillFields();
    } else if (this.actionKind === "press") {
      payload.key = this.actionValue;
    } else if (this.actionKind === "wait") {
      payload.time_ms = Number.parseInt(this.actionValue || "500", 10);
    } else if (this.actionKind === "drag") {
      payload.start_ref = this.actionRef || undefined;
      payload.end_ref = this.actionAuxValue || undefined;
    } else if (this.actionKind === "resize") {
      payload.width = Number.parseInt(this.actionValue || "1280", 10);
      payload.height = Number.parseInt(this.actionAuxValue || "720", 10);
    } else if (this.actionKind === "select") {
      payload.values = this.actionValue
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    } else if (this.actionValue) {
      payload.value = this.actionValue;
    }
    const response = await this.bridgeClient.browser.act(payload);
    const resolvedTarget = this.extractTargetId(response);
    if (resolvedTarget) {
      this.selectedTabId = resolvedTarget;
      this.lastKnownTabId = resolvedTarget;
    }
    this.lastResult = response.ok
      ? successFeedback(String((response.data as { message?: string } | null)?.message ?? "浏览器动作已执行"))
      : feedbackFromBridgeResponse(response, {
          successMessage: "浏览器动作已执行",
          errorMessage: "浏览器动作失败",
        });
    await this.load();
  };

  private parseFillFields(): Array<{ ref: string; value: string }> {
    const raw = this.actionValue.trim();
    if (!raw) {
      return this.actionRef ? [{ ref: this.actionRef, value: "" }] : [];
    }
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed
          .map((item) => {
            if (!item || typeof item !== "object") {
              return null;
            }
            return {
              ref: String((item as { ref?: unknown }).ref ?? "").trim(),
              value: String((item as { value?: unknown }).value ?? ""),
            };
          })
          .filter((item): item is { ref: string; value: string } => Boolean(item?.ref));
      }
    } catch {
      // Fall through to lightweight ref=value parsing for quick GUI input.
    }
    const pairs = raw
      .split(/\n|;/)
      .map((item) => item.trim())
      .filter(Boolean)
      .map((item) => {
        const [ref, ...rest] = item.split("=");
        return {
          ref: ref?.trim() ?? "",
          value: rest.join("=").trim(),
        };
      })
      .filter((item) => item.ref && item.value);
    if (pairs.length > 0) {
      return pairs;
    }
    if (this.actionRef) {
      return [{ ref: this.actionRef, value: raw }];
    }
    return [];
  }

  private readonly takeScreenshot = async () => {
    const targetId = this.resolveTargetId();
    if (!targetId) {
      this.artifactFeedback = warningFeedback("当前没有可截图页签");
      return;
    }
    const response = await this.bridgeClient.browser.screenshot({ target_id: targetId });
    const resolvedTarget = this.extractTargetId(response);
    if (resolvedTarget) {
      this.selectedTabId = resolvedTarget;
      this.lastKnownTabId = resolvedTarget;
    }
    this.artifactFeedback = this.describeArtifact(response);
    this.lastResult = feedbackFromBridgeResponse(response, {
      successMessage: "截图已生成",
      errorMessage: "截图失败",
    });
  };

  private readonly exportPdf = async () => {
    const targetId = this.resolveTargetId();
    if (!targetId) {
      this.artifactFeedback = warningFeedback("当前没有可导出页签");
      return;
    }
    const response = await this.bridgeClient.browser.pdf({ target_id: targetId });
    const resolvedTarget = this.extractTargetId(response);
    if (resolvedTarget) {
      this.selectedTabId = resolvedTarget;
      this.lastKnownTabId = resolvedTarget;
    }
    this.artifactFeedback = this.describeArtifact(response);
    this.lastResult = feedbackFromBridgeResponse(response, {
      successMessage: "PDF 已生成",
      errorMessage: "PDF 导出失败",
    });
  };

  private readonly downloadByRef = async () => {
    const targetId = this.resolveTargetId();
    if (!targetId || !this.actionRef) {
      this.lastResult = warningFeedback("下载需要选中页签和目标 ref");
      return;
    }
    const response = await this.bridgeClient.browser.download({
      target_id: targetId,
      ref: this.actionRef,
      path: this.downloadPath || undefined,
    });
    const resolvedTarget = this.extractTargetId(response);
    if (resolvedTarget) {
      this.selectedTabId = resolvedTarget;
      this.lastKnownTabId = resolvedTarget;
    }
    this.artifactFeedback = this.describeArtifact(response);
    this.lastResult = feedbackFromBridgeResponse(response, {
      successMessage: "下载任务已发起",
      errorMessage: "下载失败",
    });
  };

  private readonly waitForDownload = async () => {
    const targetId = this.resolveTargetId();
    if (!targetId) {
      this.lastResult = warningFeedback("当前没有可等待下载的页签");
      return;
    }
    const response = await this.bridgeClient.browser.waitDownload({
      target_id: targetId,
      time_ms: 1000,
      path: this.downloadPath || undefined,
    });
    const resolvedTarget = this.extractTargetId(response);
    if (resolvedTarget) {
      this.selectedTabId = resolvedTarget;
      this.lastKnownTabId = resolvedTarget;
    }
    this.artifactFeedback = this.describeArtifact(response);
    this.lastResult = feedbackFromBridgeResponse(response, {
      successMessage: "下载结果已就绪",
      errorMessage: "等待下载失败",
    });
  };

  private readonly uploadFiles = async () => {
    const targetId = this.resolveTargetId();
    if (!targetId) {
      this.lastResult = warningFeedback("当前没有可上传的页签");
      return;
    }
    const paths = this.uploadPaths
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const response = await this.bridgeClient.browser.upload({
      target_id: targetId,
      ref: this.actionRef || undefined,
      input_ref: this.actionRef || undefined,
      paths,
      time_ms: 1000,
    });
    const resolvedTarget = this.extractTargetId(response);
    if (resolvedTarget) {
      this.selectedTabId = resolvedTarget;
      this.lastKnownTabId = resolvedTarget;
    }
    this.lastResult = response.ok
      ? successFeedback(String((response.data as { message?: string } | null)?.message ?? "上传已完成"))
      : feedbackFromBridgeResponse(response, {
          successMessage: "上传已完成",
          errorMessage: "上传失败",
        });
    await this.load();
  };

  private readonly respondDialog = async () => {
    const targetId = this.resolveTargetId();
    if (!targetId) {
      this.lastResult = warningFeedback("当前没有可处理 dialog 的页签");
      return;
    }
    const response = await this.bridgeClient.browser.dialog({
      target_id: targetId,
      accept: this.dialogAccept,
      prompt_text: this.dialogPrompt || undefined,
      time_ms: 1000,
    });
    const resolvedTarget = this.extractTargetId(response);
    if (resolvedTarget) {
      this.selectedTabId = resolvedTarget;
      this.lastKnownTabId = resolvedTarget;
    }
    this.lastResult = response.ok
      ? successFeedback(String((response.data as { message?: string } | null)?.message ?? "dialog 已处理"))
      : feedbackFromBridgeResponse(response, {
          successMessage: "dialog 已处理",
          errorMessage: "dialog 处理失败",
        });
    await this.load();
  };

  private readonly refreshCausality = async () => {
    await this.loadCausality();
  };

  private readonly quickClick = async (ref: string) => {
    this.actionKind = "click";
    this.actionRef = ref;
    await this.performAction();
  };

  private readonly pickRef = (ref: string) => {
    this.actionRef = ref;
    this.lastResult = neutralFeedback(`已选中 ref ${ref}`);
  };

  private readonly pickTrace = async (traceId: string) => {
    this.traceId = traceId;
    await this.loadCausality();
  };

  private readonly handleBridgeEvent = (event: BridgeEvent<Record<string, unknown>>) => {
    if (event.kind !== "browser_state_changed") {
      return;
    }
    void this.load();
  };

  private describeArtifact(response: unknown): OperationFeedback {
    const artifact = (response as { data?: { artifact?: { kind?: string; path?: string } } } | null)?.data?.artifact
      ?? (response as { artifact?: { kind?: string; path?: string } } | null)?.artifact;
    if (!artifact) {
      return neutralFeedback("尚未生成 artifact");
    }
    return successFeedback(`${artifact.kind ?? "artifact"}: ${artifact.path ?? "-"}`);
  }

  private resolveProfileHint(): string | undefined {
    const profile = this.activeProfile.trim();
    return profile && profile !== "-" ? profile : undefined;
  }

  private resolveTargetId(): string {
    if (this.selectedTabId) {
      return this.selectedTabId;
    }
    if (this.lastKnownTabId) {
      return this.lastKnownTabId;
    }
    return this.tabs[0]?.tab_id ?? "";
  }

  private extractTargetId(response: { data?: Record<string, unknown> | null } | null | undefined): string {
    const data = response?.data;
    if (!data || typeof data !== "object") {
      return "";
    }
    const candidates = [
      data.target_id,
      data.tab_id,
      data.targetId,
      data.tabId,
      (data.artifact as { target_id?: unknown; targetId?: unknown } | undefined)?.target_id,
      (data.artifact as { target_id?: unknown; targetId?: unknown } | undefined)?.targetId,
    ];
    for (const candidate of candidates) {
      if (typeof candidate !== "string") {
        continue;
      }
      const normalized = candidate.trim();
      if (normalized) {
        return normalized;
      }
    }
    return "";
  }

  private async waitForRunningState(expected: boolean, timeoutMs = 5000): Promise<boolean> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const response = await this.bridgeClient.browser.status();
      if (Boolean(response.data?.running) === expected) {
        return true;
      }
      await this.sleep(150);
    }
    return false;
  }

  private async waitForTabToAppear(
    criteria: {
      targetId?: string;
      url?: string;
      profile?: string;
    },
    timeoutMs = 8000,
  ): Promise<boolean> {
    const expectedTabId = String(criteria.targetId ?? "").trim();
    const expectedUrl = String(criteria.url ?? "").trim();
    const expectedProfile = String(criteria.profile ?? "").trim();
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const tabsResponse = await this.bridgeClient.browser.tabs();
      let tabs = tabsResponse.data?.tabs ?? [];
      if (expectedProfile && tabs.length === 0) {
        const profileTabsResponse = await this.bridgeClient.browser.proxy({
          method: "GET",
          path: "/tabs",
          query: { profile: expectedProfile },
        });
        const parsedTabs = this.parseProxyTabs(profileTabsResponse.data?.result ?? {});
        if (parsedTabs.length > 0) {
          tabs = parsedTabs;
        }
      }
      const matchedById = expectedTabId ? tabs.find((item) => item.tab_id === expectedTabId) : undefined;
      const matchedByUrl = !matchedById && expectedUrl
        ? tabs.find((item) => item.url === expectedUrl || item.url.includes(expectedUrl))
        : undefined;
      const matched = matchedById ?? matchedByUrl;
      if (matched) {
        this.selectedTabId = matched.tab_id;
        this.lastKnownTabId = matched.tab_id;
        return true;
      }
      await this.sleep(200);
    }
    return false;
  }

  private async sleep(ms: number): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve, ms));
  }

  private async loadProxyDiagnostics() {
    const targetId = this.resolveTargetId();
    if (!targetId) {
      this.requestEntries = [];
      this.errorEntries = [];
      return;
    }
    const [requests, errors] = await Promise.all([
      this.bridgeClient.browser.proxy({
        method: "GET",
        path: "/requests",
        query: { targetId, limit: 8 },
      }),
      this.bridgeClient.browser.proxy({
        method: "GET",
        path: "/errors",
        query: { targetId, limit: 8 },
      }),
    ]);
    this.requestEntries = this.parseProxyRequestEntries(requests.data?.result ?? {});
    this.errorEntries = this.parseProxyErrorEntries(errors.data?.result ?? {});
  }

  private async loadCausality() {
    const approvals = await this.bridgeClient.approval.list();
    this.approvalItems = (approvals.data?.approvals ?? []).map((item) => ({
      approval_id: item.approval_id,
      title: item.title,
      trace_id: item.trace_id,
      status: item.status,
    }));
    if (!this.traceId && this.approvalItems[0]?.trace_id) {
      this.traceId = this.approvalItems[0].trace_id;
    }
    if (!this.traceId) {
      this.causalityRecords = [];
      this.causalityFeedback = warningFeedback("当前没有 trace_id，可先从审批卡片选择");
      return;
    }
    const audit = await this.bridgeClient.audit.list({ trace_id: this.traceId });
    const records = (audit.data?.records ?? []) as CausalityRecord[];
    this.causalityRecords = records;
    this.causalityFeedback = audit.ok
      ? successFeedback(`trace=${this.traceId} · records=${records.length}`)
      : warningFeedback(audit.error?.message ?? "审计链加载失败");
  }

  private parseProxyRequestEntries(result: Record<string, unknown>): RequestEntry[] {
    const candidates = [result.entries, result.requests, result.items];
    for (const value of candidates) {
      if (!Array.isArray(value)) {
        continue;
      }
      return value
        .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
        .map((item) => ({
          method: this.stringOrUndefined(item.method),
          status: this.numberOrString(item.status),
          url: this.stringOrUndefined(item.url),
          resource_type: this.stringOrUndefined(item.resource_type) ?? this.stringOrUndefined(item.resource),
          outcome: this.stringOrUndefined(item.outcome),
          message: this.stringOrUndefined(item.message),
        }));
    }
    return [];
  }

  private parseProxyTabs(result: Record<string, unknown>): BrowserTabItem[] {
    const candidates = [result.tabs, result.items];
    for (const value of candidates) {
      if (!Array.isArray(value)) {
        continue;
      }
      return value
        .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
        .map((item) => ({
          tab_id: this.stringOrUndefined(item.tab_id) ?? this.stringOrUndefined(item.target_id) ?? "",
          title: this.stringOrUndefined(item.title) ?? this.stringOrUndefined(item.url) ?? "-",
          url: this.stringOrUndefined(item.url) ?? "",
        }))
        .filter((item) => item.tab_id.length > 0);
    }
    return [];
  }

  private parseProxyErrorEntries(result: Record<string, unknown>): ErrorEntry[] {
    const candidates = [result.entries, result.errors, result.items];
    for (const value of candidates) {
      if (!Array.isArray(value)) {
        continue;
      }
      return value
        .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
        .map((item) => ({
          level: this.stringOrUndefined(item.level),
          message: this.stringOrUndefined(item.message),
          text: this.stringOrUndefined(item.text),
          source: this.stringOrUndefined(item.source) ?? this.stringOrUndefined(item.type),
          url: this.stringOrUndefined(item.url),
        }));
    }
    return [];
  }

  private stringOrUndefined(value: unknown): string | undefined {
    if (value === undefined || value === null) {
      return undefined;
    }
    const text = String(value).trim();
    return text || undefined;
  }

  private numberOrString(value: unknown): string | number | undefined {
    if (typeof value === "number") {
      return value;
    }
    const text = this.stringOrUndefined(value);
    return text;
  }

  private get primaryActionLabel(): string {
    if (this.actionKind === "drag") {
      return "起始 ref";
    }
    if (this.actionKind === "press" || this.actionKind === "wait") {
      return "目标 ref，可留空";
    }
    return "目标 ref";
  }

  private get primaryValueLabel(): string {
    if (this.actionKind === "press") {
      return "按键，如 Enter / Escape";
    }
    if (this.actionKind === "fill") {
      return "批量填写，支持 ref=value 或 JSON 数组";
    }
    if (this.actionKind === "wait") {
      return "等待毫秒";
    }
    if (this.actionKind === "resize") {
      return "宽度";
    }
    if (this.actionKind === "select") {
      return "选项值，逗号分隔";
    }
    return "文本值";
  }

  private get secondaryValueLabel(): string | null {
    if (this.actionKind === "drag") {
      return "目标 ref";
    }
    if (this.actionKind === "resize") {
      return "高度";
    }
    return null;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "browser-control-page": BrowserControlPage;
  }
}
