import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { BridgeClient, createMockBridgeClient } from "../../bridge/client.ts";
import type {
  ApprovalSummary,
  ConnectorSummary,
  PluginSummary,
  SettingsSnapshot,
  ThreadSummary,
} from "../../shared/types/bridge.ts";

type ConversationMessage = {
  role: "user" | "assistant";
  text: string;
};

type SidebarAction = {
  label: string;
  icon: string;
  action?: () => void;
  active?: boolean;
};

@customElement("codex-agent-page")
export class CodexAgentPage extends LitElement {
  static styles = css`
    :host {
      display: block;
      min-height: 100vh;
      color: #ececec;
      background: #151515;
      font-family: "Aptos", "Segoe UI", sans-serif;
    }

    .desktop {
      display: grid;
      grid-template-columns: 298px minmax(0, 1fr);
      min-height: 100vh;
      background:
        linear-gradient(90deg, #241f23 0, #281d20 298px, #151515 298px),
        #151515;
    }

    .sidebar {
      display: grid;
      grid-template-rows: auto auto 1fr auto;
      min-height: 100vh;
      padding: 12px 8px 14px;
      color: #d7d4d2;
      background:
        radial-gradient(circle at 92% 72%, rgba(94, 31, 25, 0.34), transparent 35%),
        linear-gradient(180deg, #232024 0%, #251e22 48%, #291b1d 100%);
      border-right: 1px solid rgba(255, 255, 255, 0.08);
    }

    .window-strip {
      display: flex;
      align-items: center;
      gap: 14px;
      min-height: 28px;
      padding: 0 8px 10px;
      color: #b6b1af;
    }

    .window-icon {
      width: 14px;
      height: 14px;
      border: 1.5px solid currentColor;
      border-radius: 4px;
      opacity: 0.8;
    }

    .menu-labels {
      display: flex;
      gap: 22px;
      font-size: 13px;
      color: #a6a09e;
    }

    .nav-block,
    .thread-list {
      display: grid;
      gap: 4px;
    }

    .nav-item,
    .thread-item,
    .settings-button {
      display: flex;
      align-items: center;
      gap: 10px;
      min-height: 34px;
      width: 100%;
      border: 0;
      border-radius: 8px;
      padding: 0 9px;
      color: #e4e1df;
      background: transparent;
      font: inherit;
      font-size: 14px;
      text-align: left;
      cursor: pointer;
    }

    .nav-item:hover,
    .thread-item:hover,
    .settings-button:hover {
      background: rgba(255, 255, 255, 0.07);
    }

    .nav-item[aria-current="true"] {
      background: rgba(255, 255, 255, 0.1);
    }

    .nav-icon {
      width: 18px;
      color: #d4d0ce;
      text-align: center;
      font-size: 16px;
    }

    .section-label {
      margin: 20px 6px 8px;
      color: #9d9693;
      font-size: 13px;
    }

    .thread-item {
      justify-content: space-between;
      min-height: 31px;
      padding-inline: 9px 8px;
      color: #d8d4d1;
    }

    .thread-item[aria-current="true"] {
      background: rgba(255, 255, 255, 0.11);
    }

    .thread-title {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-weight: 600;
    }

    .thread-time {
      flex: none;
      color: #aaa39f;
      font-size: 13px;
    }

    .settings-button {
      margin-top: 16px;
    }

    .project-panel {
      display: grid;
      gap: 8px;
      margin: 8px 2px 4px;
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 14px;
      padding: 8px;
      background: rgba(22, 21, 21, 0.92);
      box-shadow: 0 18px 36px rgba(0, 0, 0, 0.22);
    }

    .project-menu-title {
      padding: 5px 6px 2px;
      color: #9d9693;
      font-size: 12px;
    }

    .project-option {
      display: grid;
      grid-template-columns: 18px minmax(0, 1fr);
      gap: 8px;
      width: 100%;
      border: 0;
      border-radius: 9px;
      padding: 8px 7px;
      color: #e7e3e0;
      background: transparent;
      font: inherit;
      text-align: left;
      cursor: pointer;
    }

    .project-option:hover,
    .project-option[aria-current="true"] {
      background: rgba(255, 255, 255, 0.08);
    }

    .project-check {
      color: #f0b38c;
      text-align: center;
    }

    .project-option > span:last-child {
      min-width: 0;
    }

    .project-name {
      display: block;
      overflow: hidden;
      color: #f0eeec;
      font-size: 13px;
      font-weight: 700;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .project-path {
      display: block;
      overflow-wrap: anywhere;
      color: #aaa39f;
      font-size: 12px;
      line-height: 1.45;
    }

    .project-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 0 6px;
    }

    .project-pill {
      border-radius: 999px;
      padding: 4px 8px;
      color: #dcd6d3;
      background: rgba(255, 255, 255, 0.07);
      font-size: 11px;
    }

    .project-input {
      box-sizing: border-box;
      width: 100%;
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 9px;
      padding: 8px 9px;
      color: #f1efed;
      background: rgba(255, 255, 255, 0.05);
      font: inherit;
      font-size: 12px;
      outline: 0;
    }

    .project-input:focus {
      border-color: rgba(255, 139, 84, 0.55);
    }

    .project-actions {
      display: flex;
      gap: 8px;
    }

    .project-button {
      flex: 1;
      min-height: 30px;
      border: 0;
      border-radius: 8px;
      color: #1d1d1d;
      background: #d6d0ca;
      font: inherit;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
    }

    .project-button.secondary {
      color: #e1ddda;
      background: rgba(255, 255, 255, 0.08);
    }

    .project-status {
      min-height: 16px;
      padding: 0 2px;
      color: #c9c2be;
      font-size: 12px;
      line-height: 1.35;
    }

    .thread-pane {
      display: grid;
      grid-template-rows: auto minmax(0, 1fr) auto;
      min-height: 100vh;
      background: #151515;
    }

    .thread-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      min-height: 66px;
      padding: 0 20px 0 16px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }

    .thread-titlebar {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
    }

    .ghost-icon {
      display: inline-grid;
      place-items: center;
      width: 30px;
      height: 30px;
      border: 0;
      border-radius: 8px;
      color: #bdb8b6;
      background: transparent;
      cursor: pointer;
      font: inherit;
    }

    .ghost-icon:hover {
      background: rgba(255, 255, 255, 0.08);
    }

    h1 {
      margin: 0;
      color: #f1f1f0;
      font-size: 15px;
      font-weight: 700;
    }

    .header-actions {
      display: flex;
      gap: 12px;
      color: #b7b2af;
    }

    .messages {
      display: grid;
      align-content: start;
      gap: 26px;
      min-height: 0;
      overflow: auto;
      padding: 34px clamp(28px, 10vw, 124px) 28px;
    }

    .assistant-turn,
    .history-divider {
      width: min(736px, 100%);
      justify-self: center;
    }

    .assistant-turn {
      display: grid;
      gap: 12px;
    }

    .assistant-text {
      color: #f0efed;
      font-size: 14px;
      line-height: 1.75;
      white-space: pre-wrap;
    }

    .assistant-actions {
      display: flex;
      gap: 14px;
      color: #aaa5a2;
      font-size: 13px;
    }

    .history-divider {
      display: grid;
      grid-template-columns: auto 1fr;
      align-items: center;
      gap: 12px;
      color: #918c88;
      font-size: 14px;
    }

    .history-divider::after {
      content: "";
      height: 1px;
      background: rgba(255, 255, 255, 0.08);
    }

    .user-turn {
      justify-self: end;
      max-width: min(520px, 72%);
      border-radius: 15px;
      padding: 9px 15px;
      color: #f2f2f1;
      background: #2d2d2d;
      font-size: 14px;
      line-height: 1.55;
      white-space: pre-wrap;
    }

    .empty-state {
      display: grid;
      justify-items: center;
      align-content: center;
      min-height: 42vh;
      color: #efefec;
      text-align: center;
    }

    .empty-state strong {
      font-size: 15px;
    }

    .composer-wrap {
      display: flex;
      justify-content: center;
      padding: 0 clamp(24px, 10vw, 120px) 16px;
    }

    .composer {
      width: min(736px, 100%);
      border-radius: 17px;
      background: #2b2b2b;
      box-shadow: 0 16px 44px rgba(0, 0, 0, 0.28);
      overflow: hidden;
    }

    textarea {
      box-sizing: border-box;
      width: 100%;
      min-height: 68px;
      max-height: 180px;
      padding: 16px 17px 8px;
      resize: vertical;
      border: 0;
      outline: 0;
      color: #f3f2f0;
      background: transparent;
      font: inherit;
      line-height: 1.5;
    }

    textarea::placeholder {
      color: #8b8784;
    }

    .composer-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 8px 12px 10px;
    }

    .composer-left,
    .composer-right {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
    }

    .round-control,
    .send-button {
      display: inline-grid;
      place-items: center;
      border: 0;
      border-radius: 999px;
      font: inherit;
      cursor: pointer;
    }

    .round-control {
      width: 30px;
      height: 30px;
      color: #d5d1cf;
      background: transparent;
      font-size: 22px;
    }

    .mode-chip,
    .model-chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: 30px;
      border-radius: 999px;
      padding: 0 10px;
      color: #ded9d7;
      background: rgba(255, 255, 255, 0.05);
      font-size: 12px;
      white-space: nowrap;
    }

    .mode-chip {
      color: #ff8b54;
      font-weight: 700;
    }

    .send-button {
      width: 32px;
      height: 32px;
      color: #1d1d1d;
      background: #bdbab6;
      font-size: 17px;
    }

    .send-button:disabled {
      opacity: 0.55;
      cursor: default;
    }

    @media (max-width: 860px) {
      .desktop {
        grid-template-columns: 1fr;
      }

      .sidebar {
        display: none;
      }

      .messages,
      .composer-wrap {
        padding-inline: 16px;
      }
    }
  `;

  @property({ attribute: false }) bridgeClient: BridgeClient = createMockBridgeClient();

  @state() private draft = "";
  @state() private loading = true;
  @state() private threads: ThreadSummary[] = [];
  @state() private selectedThreadId = "";
  @state() private selectedMessages: ConversationMessage[] = [];
  @state() private settings: SettingsSnapshot | null = null;
  @state() private approvals: ApprovalSummary[] = [];
  @state() private plugins: PluginSummary[] = [];
  @state() private connectors: ConnectorSummary[] = [];
  @state() private projectMenuOpen = false;
  @state() private projectDraft = "";
  @state() private projectStatus = "";
  @state() private recentWorkspaceRoots: string[] = [];

  connectedCallback(): void {
    super.connectedCallback();
    void this.load();
  }

  render() {
    return html`
      <section class="desktop" data-testid="codex-agent-page">
        ${this.renderSidebar()}
        <main class="thread-pane">
          ${this.renderHeader()}
          ${this.renderMessages()}
          ${this.renderComposer()}
        </main>
      </section>
    `;
  }

  private renderSidebar() {
    const actions: SidebarAction[] = [
      { label: "新对话", icon: "✎", action: () => this.startNewThread() },
      { label: "搜索", icon: "⌕" },
      { label: "插件", icon: "⌘" },
      { label: "自动化", icon: "◷" },
      { label: "项目", icon: "⊞", action: () => this.toggleProjectMenu(), active: this.projectMenuOpen },
    ];
    return html`
      <aside class="sidebar">
        <div class="window-strip">
          <span class="window-icon" aria-hidden="true"></span>
          <div class="menu-labels" aria-label="window menu">
            <span>文件</span><span>编辑</span><span>查看</span><span>窗口</span><span>帮助</span>
          </div>
        </div>
        <nav class="nav-block" aria-label="Codex navigation">
          ${actions.map(
            (item) => html`
              <button
                class="nav-item"
                type="button"
                aria-current=${item.active ? "true" : "false"}
                @click=${item.action ?? (() => {})}
              >
                <span class="nav-icon" aria-hidden="true">${item.icon}</span>
                <span>${item.label}</span>
              </button>
            `,
          )}
        </nav>
        ${this.projectMenuOpen ? this.renderProjectPanel() : null}
        <section>
          <div class="section-label">对话 · ${this.projectName()}</div>
          <div class="thread-list">
            ${this.threads.length
              ? this.threads.map((thread) => this.renderThread(thread))
              : html`<span class="section-label">当前项目暂无会话</span>`}
          </div>
        </section>
        <button class="settings-button" type="button" @click=${this.openSettings}>
          <span class="nav-icon" aria-hidden="true">⚙</span>
          <span>设置</span>
        </button>
      </aside>
    `;
  }

  private renderProjectPanel() {
    const activeRoot = this.projectRoot();
    const roots = this.projectMenuRoots();
    return html`
      <section class="project-panel" data-testid="codex-project-panel">
        <div class="project-menu-title">项目</div>
        ${roots.map((root) => this.renderProjectOption(root, root === activeRoot))}
        <div class="project-meta">
          <span class="project-pill">${this.settings?.workspaceTrust ?? "unknown"}</span>
          <span class="project-pill">${this.threads.length} 会话</span>
          <span class="project-pill">${this.settings?.runtimePolicy?.sandbox_mode ?? "sandbox"}</span>
        </div>
        <input
          class="project-input"
          data-testid="codex-project-root-input"
          .value=${this.projectDraft}
          @input=${this.handleProjectDraftInput}
          @keydown=${this.handleProjectDraftKeydown}
          placeholder="输入项目路径"
        />
        <div class="project-actions">
          <button class="project-button" type="button" @click=${() => this.applyProjectRoot()}>切换项目</button>
          <button class="project-button secondary" type="button" @click=${this.refreshProjectThreads}>刷新</button>
        </div>
        <div class="project-status">${this.projectStatus}</div>
      </section>
    `;
  }

  private renderProjectOption(root: string, active: boolean) {
    return html`
      <button
        class="project-option"
        type="button"
        aria-current=${active ? "true" : "false"}
        data-testid="codex-project-option"
        @click=${() => this.applyProjectRoot(root)}
      >
        <span class="project-check" aria-hidden="true">${active ? "✓" : ""}</span>
        <span>
          <span class="project-name">${this.projectNameForRoot(root)}</span>
          <span class="project-path">${root}</span>
        </span>
      </button>
    `;
  }

  private renderHeader() {
    return html`
      <header class="thread-header">
        <div class="thread-titlebar">
          <button class="ghost-icon" type="button" aria-label="Back">‹</button>
          <button class="ghost-icon" type="button" aria-label="Forward">›</button>
          <h1>${this.threadTitle()}</h1>
          <button class="ghost-icon" type="button" aria-label="Thread actions">···</button>
        </div>
        <div class="header-actions" aria-label="Thread controls">
          <button class="ghost-icon" type="button" title="Toggle terminal">▣</button>
          <button class="ghost-icon" type="button" title="Toggle side panel">▢</button>
        </div>
      </header>
    `;
  }

  private renderMessages() {
    if (!this.selectedMessages.length) {
      return html`
        <section class="messages" data-testid="codex-conversation">
          <div class="empty-state">
            <strong>你好！我在这儿。今天想一起弄点什么？</strong>
          </div>
        </section>
      `;
    }
    const hiddenCount = Math.max(0, this.selectedMessages.length - 3);
    const visibleMessages = hiddenCount ? this.selectedMessages.slice(-3) : this.selectedMessages;
    return html`
      <section class="messages" data-testid="codex-conversation">
        ${hiddenCount ? html`<div class="history-divider">上 ${hiddenCount} 条消息 ›</div>` : null}
        ${visibleMessages.map((message) => this.renderMessage(message))}
      </section>
    `;
  }

  private renderMessage(message: ConversationMessage) {
    if (message.role === "user") {
      return html`<div class="user-turn">${message.text}</div>`;
    }
    return html`
      <article class="assistant-turn">
        <div class="assistant-text">${message.text}</div>
        <div class="assistant-actions" aria-label="Message actions">
          <span>⧉</span>
          <span>⌘</span>
        </div>
      </article>
    `;
  }

  private renderComposer() {
    return html`
      <div class="composer-wrap">
        <section class="composer">
          <textarea
            data-testid="codex-composer"
            .value=${this.draft}
            @input=${this.handleDraftInput}
            placeholder="要求后续变更"
          ></textarea>
          <div class="composer-footer">
            <div class="composer-left">
              <button class="round-control" type="button" aria-label="Attach">＋</button>
              <span class="mode-chip">${this.permissionLabel()}⌄</span>
            </div>
            <div class="composer-right">
              <span class="model-chip">${this.modelShortLabel()}⌄</span>
              <span class="model-chip">${this.loading ? "同步" : "就绪"}</span>
              <button
                class="send-button"
                type="button"
                aria-label="Send"
                ?disabled=${!this.draft.trim()}
                @click=${this.sendDraft}
              >
                ↑
              </button>
            </div>
          </div>
        </section>
      </div>
    `;
  }

  private async load() {
    this.loading = true;
    const [settings, approvals, plugins, connectors] = await Promise.all([
      this.bridgeClient.settings.get(),
      this.bridgeClient.approval.list(),
      this.bridgeClient.plugin.list(),
      this.bridgeClient.connector.list(),
    ]);
    this.settings = settings.data ?? null;
    this.projectDraft = this.projectRoot();
    this.recordWorkspaceRoot(this.projectRoot());
    this.approvals = approvals.data?.approvals ?? [];
    this.plugins = plugins.data?.plugins ?? [];
    this.connectors = connectors.data?.connectors ?? [];
    await this.refreshProjectThreads();
    this.loading = false;
  }

  private async refreshProjectThreads() {
    const workspaceRoot = this.projectRoot();
    this.recordWorkspaceRoot(workspaceRoot);
    const threads = await this.bridgeClient.thread.list({
      limit: 8,
      cwd: workspaceRoot || undefined,
    });
    this.threads = threads.data?.threads ?? [];
    const activeThreadId = threads.data?.active_thread_id || this.threads[0]?.thread_id || "";
    if (activeThreadId) {
      await this.selectThread(activeThreadId);
    } else {
      this.startNewThread();
    }
    this.projectStatus = workspaceRoot ? `已加载 ${this.projectName()} 的会话。` : "未设置项目路径。";
  }

  private renderThread(thread: ThreadSummary) {
    return html`
      <button
        class="thread-item"
        type="button"
        aria-current=${thread.thread_id === this.selectedThreadId ? "true" : "false"}
        @click=${() => this.selectThread(thread.thread_id)}
      >
        <span class="thread-title">${thread.name || thread.thread_id}</span>
        <span class="thread-time">${thread.updated_at}</span>
      </button>
    `;
  }

  private async selectThread(threadId: string) {
    const response = await this.bridgeClient.thread.resume({ thread_id: threadId });
    if (!response.ok) {
      return;
    }
    this.selectedThreadId = threadId;
    const turns = response.data?.turns ?? [];
    const history = response.data?.history ?? [];
    if (turns.length) {
      this.selectedMessages = turns.flatMap((turn) => [
        ...(turn.user_text ? [{ role: "user" as const, text: turn.user_text }] : []),
        ...(turn.assistant_text ? [{ role: "assistant" as const, text: turn.assistant_text }] : []),
      ]);
      return;
    }
    this.selectedMessages = history.map((item) => ({
      role: item.role,
      text: item.content,
    }));
  }

  private startNewThread() {
    this.selectedThreadId = "";
    this.selectedMessages = [];
    this.draft = "";
    this.projectMenuOpen = false;
    this.requestUpdate();
    void this.focusComposer();
  }

  private toggleProjectMenu() {
    this.projectMenuOpen = !this.projectMenuOpen;
    this.projectDraft = this.projectRoot();
    if (!this.projectStatus) {
      this.projectStatus = "项目会话按 workspaceRoot/cwd 过滤。";
    }
  }

  private handleDraftInput(event: Event) {
    this.draft = (event.target as HTMLTextAreaElement).value;
  }

  private handleProjectDraftInput(event: Event) {
    this.projectDraft = (event.target as HTMLInputElement).value;
  }

  private handleProjectDraftKeydown(event: KeyboardEvent) {
    if (event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    void this.applyProjectRoot();
  }

  private async applyProjectRoot(nextRoot?: string) {
    const workspaceRoot = (nextRoot ?? this.projectDraft).trim();
    if (!workspaceRoot) {
      this.projectStatus = "workspaceRoot 不能为空。";
      return;
    }
    if (workspaceRoot === this.projectRoot()) {
      this.projectDraft = workspaceRoot;
      this.projectMenuOpen = false;
      this.projectStatus = `已选择 ${this.projectNameForRoot(workspaceRoot)}。`;
      return;
    }
    this.projectStatus = "正在切换项目...";
    const response = await this.bridgeClient.config.apply({ workspaceRoot });
    if (!response.ok) {
      this.projectStatus = response.error?.message ?? "项目切换失败。";
      return;
    }
    this.settings = response.data?.settings ?? this.settings;
    this.projectDraft = this.projectRoot();
    this.recordWorkspaceRoot(this.projectRoot());
    await this.refreshProjectThreads();
    this.projectMenuOpen = false;
  }

  private async sendDraft() {
    const text = this.draft.trim();
    if (!text) {
      return;
    }
    this.selectedMessages = [...this.selectedMessages, { role: "user", text }];
    this.draft = "";
    const response = await this.bridgeClient.chat.send({
      text,
      thread_id: this.selectedThreadId || undefined,
      cwd: this.projectRoot() || undefined,
      workspaceRoots: this.workspaceRootsPayload(),
      new_thread: !this.selectedThreadId,
    });
    if (response.ok) {
      this.selectedThreadId = response.data?.thread_id ?? this.selectedThreadId;
      this.selectedMessages = [
        ...this.selectedMessages,
        { role: "assistant", text: response.data?.assistant_text ?? "Task accepted." },
      ];
      return;
    }
    this.selectedMessages = [
      ...this.selectedMessages,
      { role: "assistant", text: response.error?.message ?? "Send failed." },
    ];
  }

  private openSettings() {
    this.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "settings",
        bubbles: true,
        composed: true,
      }),
    );
  }

  private threadTitle(): string {
    return this.threads.find((thread) => thread.thread_id === this.selectedThreadId)?.name || "新对话";
  }

  private projectRoot(): string {
    return String(this.settings?.workspaceRoot ?? "").trim();
  }

  private workspaceRootsPayload(): string[] {
    const root = this.projectRoot();
    return root ? [root] : [];
  }

  private projectMenuRoots(): string[] {
    const roots = [this.projectRoot(), ...this.recentWorkspaceRoots]
      .map((root) => root.trim())
      .filter(Boolean);
    return Array.from(new Set(roots));
  }

  private recordWorkspaceRoot(root: string) {
    const normalized = root.trim();
    if (!normalized) {
      return;
    }
    this.recentWorkspaceRoots = [normalized, ...this.recentWorkspaceRoots.filter((item) => item !== normalized)].slice(0, 6);
  }

  private projectName(): string {
    return this.projectNameForRoot(this.projectRoot());
  }

  private projectNameForRoot(root: string): string {
    if (!root) {
      return "未选择项目";
    }
    const normalized = root.replace(/\\/g, "/").replace(/\/+$/, "");
    const name = normalized.split("/").filter(Boolean).pop() ?? normalized;
    const tokens = name.trim().split(/\s+/).filter(Boolean);
    return tokens.length <= 3 ? name : tokens.slice(0, 3).join(" ");
  }

  private async focusComposer() {
    await this.updateComplete;
    const composer = this.shadowRoot?.querySelector("[data-testid='codex-composer']") as HTMLTextAreaElement | null;
    composer?.focus();
  }

  private permissionLabel(): string {
    const policy = this.settings?.runtimePolicy ?? {};
    if (policy.approval_policy === "never" || policy.sandbox_mode === "danger-full-access") {
      return "完全访问权限";
    }
    if (this.approvals.length) {
      return `待审批 ${this.approvals.length}`;
    }
    return "默认权限";
  }

  private modelShortLabel(): string {
    const raw = this.settings?.providerLabel ?? this.settings?.model ?? "model";
    const parts = raw.split("|").map((item) => item.trim()).filter(Boolean);
    const model = parts.length >= 2 ? parts[1] : parts[0] ?? raw;
    const readyTools = this.plugins.filter((item: PluginSummary) => item.enabled && item.health === "ready").length;
    const readyConnectors = this.connectors.filter(
      (item: ConnectorSummary) => item.enabled && item.health === "ready",
    ).length;
    const suffix = readyTools + readyConnectors > 0 ? ` · ${readyTools + readyConnectors}` : "";
    return `${model}${suffix}`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "codex-agent-page": CodexAgentPage;
  }
}
