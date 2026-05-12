import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { BridgeClient, createMockBridgeClient } from "../../bridge/client.ts";
import "../../shared/components/operation-feedback-view.ts";
import type { BridgeEvent, ThreadSummary, ThreadTurn } from "../../shared/types/bridge.ts";
import {
  errorFeedback,
  feedbackFromBridgeResponse,
  neutralFeedback,
  successFeedback,
  warningFeedback,
  type OperationFeedback,
} from "../../shared/state/operation-feedback.ts";
import { buildTranscriptEntries, type TranscriptRenderEntry } from "./transcript-model.ts";

type TaskUiState = "idle" | "in_flight" | "abort_requested";

type LiveEventCard = {
  id: string;
  kind: BridgeEvent<Record<string, unknown>>["kind"];
  status: BridgeEvent<Record<string, unknown>>["status"];
  title: string;
  summary: string;
  detail: string;
  timestamp: string;
};

type ThreadRuntimeContext = {
  threadId: string;
  threadName: string;
  updatedAt: string;
  turnCount: number;
  threadStatus: string;
  runtimeState: Record<string, unknown> | null;
};

@customElement("chat-task-page")
export class ChatTaskPage extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .grid {
      display: grid;
      grid-template-columns: 0.7fr 1.4fr 0.8fr;
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

    h2 {
      margin: 0;
      font-size: 18px;
      color: #eef6fa;
    }

    .transcript,
    .timeline,
    .live-cards {
      display: grid;
      gap: 10px;
    }

    .bubble {
      border-radius: 14px;
      padding: 12px 14px;
      line-height: 1.55;
      font-size: 14px;
      white-space: pre-wrap;
    }

    .user {
      background: rgba(24, 77, 86, 0.36);
      color: #eff9fb;
    }

    .assistant {
      background: rgba(20, 34, 46, 0.8);
      color: #bcd0dc;
    }

    .commentary {
      background: rgba(32, 52, 68, 0.84);
      color: #d5e5ee;
    }

    .activity {
      background: rgba(15, 28, 38, 0.9);
      color: #9db3be;
      border-left: 2px solid rgba(111, 203, 193, 0.36);
    }

    .event {
      border-left: 2px solid rgba(130, 183, 171, 0.35);
      padding-left: 10px;
      color: #97afbb;
      font-size: 13px;
    }

    .status-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      color: #a8bec9;
      font-size: 13px;
    }

    .status-chip {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      line-height: 1;
    }

    .status-chip.idle {
      background: rgba(94, 133, 149, 0.25);
      color: #c0d6e2;
    }

    .status-chip.in_flight {
      background: rgba(64, 147, 134, 0.32);
      color: #dbf6f0;
    }

    .status-chip.abort_requested {
      background: rgba(164, 131, 61, 0.3);
      color: #f7e9cb;
    }

    .section-label {
      margin: 0;
      font-size: 13px;
      color: #b8cbd6;
    }

    .partial-output {
      border-radius: 12px;
      padding: 10px 12px;
      border: 1px solid rgba(138, 176, 188, 0.18);
      background: rgba(9, 19, 27, 0.78);
      color: #dceaf2;
      white-space: pre-wrap;
      font-size: 13px;
      line-height: 1.45;
      min-height: 40px;
    }

    .live-card {
      border-radius: 12px;
      border: 1px solid rgba(122, 167, 185, 0.24);
      background: rgba(12, 25, 34, 0.88);
      padding: 10px 12px;
      display: grid;
      gap: 6px;
    }

    .live-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      font-size: 13px;
      color: #d8e8ef;
    }

    .live-kind {
      color: #89afbe;
      font-size: 12px;
    }

    .runtime-box {
      border-radius: 12px;
      border: 1px solid rgba(132, 170, 184, 0.2);
      background: rgba(9, 20, 28, 0.86);
      padding: 10px 12px;
      display: grid;
      gap: 8px;
    }

    .runtime-pre {
      margin: 0;
      white-space: pre-wrap;
      color: #bcd1dc;
      font-size: 12px;
      line-height: 1.5;
    }

    textarea {
      width: 100%;
      min-height: 96px;
      resize: vertical;
      border-radius: 14px;
      border: 1px solid rgba(150, 186, 196, 0.14);
      background: rgba(9, 20, 28, 0.92);
      color: #eff6fa;
      padding: 12px;
      font: inherit;
    }

    .actions {
      display: flex;
      justify-content: flex-end;
      gap: 10px;
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

    button[disabled] {
      opacity: 0.6;
      cursor: default;
    }

    .thread {
      border-radius: 14px;
      padding: 12px 14px;
      background: rgba(20, 34, 46, 0.8);
      display: grid;
      gap: 6px;
      cursor: pointer;
    }

    .thread.active {
      outline: 1px solid rgba(84, 172, 153, 0.55);
      background: rgba(24, 52, 66, 0.92);
    }

    .caption {
      color: #97afbb;
      font-size: 12px;
      line-height: 1.45;
    }
  `;

  private unsubscribe: (() => void) | null = null;

  @property({ attribute: false }) bridgeClient: BridgeClient = createMockBridgeClient();

  @state() private draft = "";
  @state() private sending = false;
  @state() private stopping = false;
  @state() private activeThreadId = "";
  @state() private threads: ThreadSummary[] = [];
  @state() private turns: ThreadTurn[] = [];
  @state() private transcript: TranscriptRenderEntry[] = [];
  @state() private timeline: BridgeEvent<Record<string, unknown>>[] = [];
  @state() private liveCards: LiveEventCard[] = [];
  @state() private partialOutput = "";
  @state() private taskState: TaskUiState = "idle";
  @state() private runtimeContext: ThreadRuntimeContext | null = null;
  @state() private feedback: OperationFeedback = neutralFeedback("等待选择线程或发送消息。");

  connectedCallback(): void {
    super.connectedCallback();
    this.unsubscribe = this.bridgeClient.subscribe((event) => {
      this.handleBridgeEvent(event);
    });
    void this.loadThreads();
  }

  disconnectedCallback(): void {
    this.unsubscribe?.();
    super.disconnectedCallback();
  }

  render() {
    return html`
      <section class="grid">
        <aside class="panel">
          <h2>最近会话</h2>
          ${this.threads.map(
            (thread) => html`
              <div
                class="thread ${thread.thread_id === this.activeThreadId ? "active" : ""}"
                @click=${() => this.handleResumeThread(thread.thread_id)}
              >
                <strong>${thread.name}</strong>
                <div class="caption">${thread.updated_at}</div>
                <div class="caption">${thread.last_user_text ?? thread.last_assistant_text ?? ""}</div>
              </div>
            `,
          )}
        </aside>
        <article class="panel">
          <h2>对话流</h2>
          <operation-feedback-view
            data-testid="chat-feedback"
            .feedback=${this.feedback}
          ></operation-feedback-view>
          <div class="status-row">
            <span
              class="status-chip ${this.taskState}"
              data-testid="chat-task-state"
            >
              ${this.taskStateLabel(this.taskState)}
            </span>
            <span class="caption">${this.activeThreadId ? `线程 ${this.activeThreadId}` : "未绑定线程"}</span>
          </div>
          <div class="transcript">
            ${this.transcript.length === 0
              ? html`<div class="bubble assistant">这里会承接真实线程历史、即时回复和事件流。</div>`
              : this.transcript.map(
                  (item) => html`<div class="bubble ${this.bubbleClass(item)}">${item.lines.join("\n")}</div>`,
                )}
          </div>
          <h3 class="section-label">实时输出（partial）</h3>
          <div class="partial-output" data-testid="chat-partial-output">
            ${this.partialOutput || "等待 bridge event 增量输出..."}
          </div>
          <label>
            <textarea
              .value=${this.draft}
              @input=${this.handleInput}
              placeholder="输入任务或问题"
            ></textarea>
          </label>
          <div class="actions">
            <button
              type="button"
              ?disabled=${this.stopping}
              @click=${this.handleStop}
            >
              停止
            </button>
            <button
              type="button"
              ?disabled=${this.sending || !this.draft.trim()}
              @click=${this.handleSend}
            >
              发送
            </button>
          </div>
        </article>
        <aside class="panel">
          <h2>线程上下文</h2>
          <div class="runtime-box" data-testid="chat-runtime-context">
            ${this.runtimeContext
              ? html`
                  <strong>${this.runtimeContext.threadName}</strong>
                  <div class="caption">thread_id: ${this.runtimeContext.threadId}</div>
                  <div class="caption">status: ${this.runtimeContext.threadStatus || "unknown"}</div>
                  <div class="caption">turns: ${this.runtimeContext.turnCount}</div>
                  <div class="caption">${this.runtimeContext.updatedAt}</div>
                  <pre class="runtime-pre">${this.formatRuntimeState(this.runtimeContext.runtimeState)}</pre>
                `
              : html`<div class="caption">恢复线程后显示 runtime / status 快照。</div>`}
          </div>
          <h2>实时事件卡</h2>
          <div class="live-cards" data-testid="chat-live-cards">
            ${this.liveCards.length === 0
              ? html`<div class="caption">等待 task/tool 事件。</div>`
              : this.liveCards.map(
                  (card) => html`
                    <div class="live-card">
                      <div class="live-head">
                        <strong>${card.title}</strong>
                        <span class="status-chip ${this.statusChipClass(card.status)}">${card.status}</span>
                      </div>
                      <div>${card.summary}</div>
                      ${card.detail ? html`<div class="caption">${card.detail}</div>` : ""}
                      <div class="live-kind">${card.kind} · ${card.timestamp}</div>
                    </div>
                  `,
                )}
          </div>
          <h2>任务时间线</h2>
          <div class="timeline">
            ${this.timeline.map(
              (event) => html`
                <div class="event">
                  <strong>${event.kind}</strong>
                  <div>${event.summary}</div>
                </div>
              `,
            )}
          </div>
        </aside>
      </section>
    `;
  }

  private handleInput(event: Event) {
    this.draft = (event.target as HTMLTextAreaElement).value;
  }

  private async handleSend() {
    const text = this.draft.trim();
    if (!text) {
      return;
    }
    this.taskState = "in_flight";
    this.partialOutput = "";
    this.feedback = neutralFeedback("消息已提交，等待任务事件回流。");
    this.sending = true;
    const response = await this.bridgeClient.chat.send({
      text,
      thread_id: this.activeThreadId || undefined,
    });
    if (response.ok) {
      this.activeThreadId = response.data?.thread_id ?? this.activeThreadId;
      this.feedback = successFeedback(response.data?.assistant_text ?? "消息已进入任务流。等待任务完成事件。");
      this.draft = "";
      if (this.activeThreadId) {
        await this.handleResumeThread(this.activeThreadId);
      } else {
        await this.loadThreads();
      }
    } else {
      this.taskState = "idle";
      this.feedback = feedbackFromBridgeResponse(response, {
        successMessage: "消息已进入任务流。",
        errorMessage: "消息发送失败",
      });
    }
    this.sending = false;
  }

  private async loadThreads() {
    const response = await this.bridgeClient.thread.list({ limit: 8 });
    if (!response.ok) {
      this.feedback = feedbackFromBridgeResponse(response, {
        successMessage: "线程列表已加载",
        errorMessage: "线程列表加载失败",
      });
      return;
    }
    this.threads = response.data?.threads ?? [];
    const nextActiveThreadId = response.data?.active_thread_id ?? this.activeThreadId;
    const shouldResume = nextActiveThreadId && nextActiveThreadId !== this.activeThreadId;
    this.activeThreadId = nextActiveThreadId;
    if (!nextActiveThreadId) {
      this.feedback = neutralFeedback(this.threads.length ? "请选择一个线程继续。" : "暂无线程，发送消息即可开始。");
    }
    if (shouldResume) {
      await this.handleResumeThread(nextActiveThreadId);
    }
  }

  private async handleResumeThread(threadId: string) {
    const response = await this.bridgeClient.thread.resume({ thread_id: threadId });
    if (!response.ok) {
      this.feedback = feedbackFromBridgeResponse(response, {
        successMessage: `已切换到线程 ${threadId}`,
        errorMessage: `线程 ${threadId} 恢复失败`,
      });
      return;
    }
    this.activeThreadId = threadId;
    this.turns = response.data?.turns ?? [];
    this.transcript = this.turns.length
      ? buildTranscriptEntries(this.turns)
      : (response.data?.history ?? []).map((item) => ({
          kind: item.role === "user" ? "user" : "assistant",
          layer: item.role === "user" ? "user" : "final",
          lines: [item.content],
        }));
    this.runtimeContext = this.buildThreadRuntimeContext(response.data, threadId);
    this.syncTaskStateFromContext(this.runtimeContext);
    this.feedback = successFeedback(`已切换到线程 ${threadId}`);
  }

  private async handleStop() {
    const previousState = this.taskState;
    this.taskState = "abort_requested";
    this.feedback = warningFeedback("已请求中断，等待任务停止确认。");
    this.stopping = true;
    const response = await this.bridgeClient.task.stop({});
    if (response.ok) {
      if (response.data?.interrupted) {
        this.taskState = "idle";
      }
      this.feedback = feedbackFromBridgeResponse(response, {
        successMessage: response.data?.interrupted ? "任务已中断" : "已发送停止请求",
        errorMessage: "停止失败",
      });
    } else {
      this.taskState = previousState;
      this.feedback = feedbackFromBridgeResponse(response, {
        successMessage: "已发送停止请求",
        errorMessage: "停止失败",
      });
    }
    this.stopping = false;
  }

  private handleBridgeEvent(event: BridgeEvent<Record<string, unknown>>) {
    this.timeline = [event, ...this.timeline].slice(0, 40);
    if (this.shouldRenderLiveCard(event)) {
      this.liveCards = [this.toLiveCard(event), ...this.liveCards].slice(0, 24);
    }
    this.partialOutput = mergePartialOutput(this.partialOutput, this.partialTextFromEvent(event));
    this.advanceTaskStateFromEvent(event);
    this.feedback = this.feedbackFromEvent(event);
    if (event.kind === "task_completed" || event.kind === "task_failed") {
      const payload = event.payload ?? {};
      const threadId = typeof payload.thread_id === "string" ? payload.thread_id : "";
      if (threadId && threadId === this.activeThreadId) {
        void this.handleResumeThread(threadId);
      }
    }
  }

  private bubbleClass(item: TranscriptRenderEntry): string {
    if (item.layer === "user") {
      return "user";
    }
    if (item.layer === "commentary") {
      return "commentary";
    }
    if (item.kind === "activity") {
      return "activity";
    }
    return "assistant";
  }

  private feedbackFromEvent(event: BridgeEvent<Record<string, unknown>>): OperationFeedback {
    const message = event.summary || this.feedback.message;
    if (event.status === "error") {
      return errorFeedback(message);
    }
    if (event.status === "warning") {
      return warningFeedback(message);
    }
    if (event.status === "accepted" || event.status === "ok") {
      return successFeedback(message);
    }
    return neutralFeedback(message);
  }

  private shouldRenderLiveCard(event: BridgeEvent<Record<string, unknown>>): boolean {
    return (
      event.kind === "task_started" ||
      event.kind === "task_progress" ||
      event.kind === "task_completed" ||
      event.kind === "task_failed" ||
      event.kind === "tool_event"
    );
  }

  private toLiveCard(event: BridgeEvent<Record<string, unknown>>): LiveEventCard {
    return {
      id: event.event_id,
      kind: event.kind,
      status: event.status,
      title: this.liveTitle(event),
      summary: event.summary,
      detail: this.eventDetail(event.payload ?? {}),
      timestamp: this.shortTimestamp(event.ts),
    };
  }

  private liveTitle(event: BridgeEvent<Record<string, unknown>>): string {
    if (event.kind === "tool_event") {
      return `Tool · ${event.name}`;
    }
    if (event.kind === "task_progress") {
      return `Task Progress · ${event.name}`;
    }
    if (event.kind === "task_started") {
      return "Task Started";
    }
    if (event.kind === "task_completed") {
      return "Task Completed";
    }
    if (event.kind === "task_failed") {
      return "Task Failed";
    }
    return event.name || event.kind;
  }

  private eventDetail(payload: Record<string, unknown>): string {
    const details: string[] = [];
    const threadId = asNonEmptyText(payload.thread_id);
    const phase = asNonEmptyText(payload.phase);
    const taskId = asNonEmptyText(payload.task_id);
    const targetId = asNonEmptyText(payload.target_id);
    if (threadId) {
      details.push(`thread=${threadId}`);
    }
    if (taskId) {
      details.push(`task=${taskId}`);
    }
    if (phase) {
      details.push(`phase=${phase}`);
    }
    if (targetId) {
      details.push(`target=${targetId}`);
    }
    if (details.length) {
      return details.join(" · ");
    }
    return compactJson(payload);
  }

  private partialTextFromEvent(event: BridgeEvent<Record<string, unknown>>): string {
    if (event.kind !== "task_progress" && event.kind !== "tool_event") {
      return "";
    }
    return partialTextFromPayload(event.payload ?? {});
  }

  private advanceTaskStateFromEvent(event: BridgeEvent<Record<string, unknown>>) {
    if (event.kind === "task_completed" || event.kind === "task_failed") {
      this.taskState = "idle";
      return;
    }
    if (event.kind === "task_started" || event.kind === "task_progress" || event.kind === "tool_event") {
      if (this.taskState !== "abort_requested") {
        this.taskState = "in_flight";
      }
    }
  }

  private statusChipClass(status: BridgeEvent<Record<string, unknown>>["status"]): string {
    if (status === "accepted" || status === "ok") {
      return "in_flight";
    }
    if (status === "warning") {
      return "abort_requested";
    }
    return "idle";
  }

  private taskStateLabel(state: TaskUiState): string {
    if (state === "in_flight") {
      return "执行中";
    }
    if (state === "abort_requested") {
      return "中断请求中";
    }
    return "空闲";
  }

  private buildThreadRuntimeContext(
    data: {
      thread?: ThreadSummary;
      turns?: ThreadTurn[];
      state?: Record<string, unknown>;
    } | null,
    fallbackThreadId: string,
  ): ThreadRuntimeContext | null {
    if (!data?.thread) {
      return null;
    }
    const latestTurn = (data.turns ?? []).at(-1);
    const threadStatus =
      asNonEmptyText(latestTurn?.status?.status) ||
      asNonEmptyText(latestTurn?.status?.phase) ||
      asNonEmptyText(data.state?.status) ||
      asNonEmptyText(data.state?.phase) ||
      "";
    const runtimeState = asRecord(latestTurn?.runtime_state) ?? asRecord(data.state?.runtime_state) ?? asRecord(data.state) ?? null;
    return {
      threadId: data.thread.thread_id || fallbackThreadId,
      threadName: data.thread.name || fallbackThreadId,
      updatedAt: data.thread.updated_at,
      turnCount: data.thread.turn_count ?? data.turns?.length ?? 0,
      threadStatus,
      runtimeState,
    };
  }

  private syncTaskStateFromContext(context: ThreadRuntimeContext | null) {
    if (!context?.threadStatus) {
      return;
    }
    const normalized = context.threadStatus.toLowerCase();
    if (["running", "in_progress", "queued", "processing", "streaming"].includes(normalized)) {
      if (this.taskState !== "abort_requested") {
        this.taskState = "in_flight";
      }
      return;
    }
    if (["completed", "done", "failed", "error", "interrupted", "cancelled", "stopped", "idle"].includes(normalized)) {
      this.taskState = "idle";
    }
  }

  private shortTimestamp(value: string): string {
    const text = String(value || "").trim();
    if (!text) {
      return "";
    }
    const date = new Date(text);
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      });
    }
    return text;
  }

  private formatRuntimeState(value: Record<string, unknown> | null): string {
    if (!value || Object.keys(value).length === 0) {
      return "{}";
    }
    return compactJson(value);
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "chat-task-page": ChatTaskPage;
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function asNonEmptyText(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function compactJson(value: unknown): string {
  if (!value || typeof value !== "object") {
    return "";
  }
  try {
    const json = JSON.stringify(value);
    return json.length > 220 ? `${json.slice(0, 220)}...` : json;
  } catch {
    return "";
  }
}

function partialTextFromPayload(payload: Record<string, unknown>): string {
  const directKeys = [
    "partial_output",
    "partial_text",
    "assistant_partial",
    "assistant_text_delta",
    "text_delta",
    "delta",
    "chunk",
    "token",
    "text",
    "message",
    "assistant_text",
  ] as const;
  for (const key of directKeys) {
    const text = partialTextFromValue(payload[key]);
    if (text) {
      return text;
    }
  }
  const nested = [payload.delta, payload.message, payload.result, payload.output];
  for (const item of nested) {
    const text = partialTextFromValue(item);
    if (text) {
      return text;
    }
  }
  return "";
}

function partialTextFromValue(value: unknown): string {
  if (typeof value === "string") {
    return value.trim();
  }
  if (Array.isArray(value)) {
    const merged = value.map((item) => partialTextFromValue(item)).filter(Boolean).join("");
    return merged.trim();
  }
  if (!value || typeof value !== "object") {
    return "";
  }
  const record = value as Record<string, unknown>;
  const nestedKeys = ["text", "content", "delta", "message", "assistant_text"];
  for (const key of nestedKeys) {
    const text = partialTextFromValue(record[key]);
    if (text) {
      return text;
    }
  }
  return "";
}

function mergePartialOutput(current: string, incoming: string): string {
  const next = incoming.trim();
  if (!next) {
    return current;
  }
  if (!current) {
    return next;
  }
  if (next.startsWith(current)) {
    return next;
  }
  if (current.endsWith(next)) {
    return current;
  }
  return `${current}${next}`;
}
