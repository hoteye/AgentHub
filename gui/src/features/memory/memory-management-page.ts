import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";

export type MemoryScope = "project" | "user";
export type MemoryType = "project" | "user" | "reference" | "feedback";
export type MemoryStatus = "active" | "archived" | "deleted";
export type MemoryAction = "list" | "show" | "filter" | "preview" | "apply" | "save" | "delete" | "archive" | "debug";

export type MemoryListFilter = {
  scope: "all" | MemoryScope;
  type: "all" | MemoryType;
  status: "all" | MemoryStatus;
  tag: string;
  limit: number;
};

export type MemoryListItem = {
  memory_id: string;
  scope?: MemoryScope;
  memory_type: string;
  status: string;
  title: string;
  summary?: string;
  tags?: string[];
  paths?: string[];
};

export type MemoryDetail = MemoryListItem & {
  hit_count?: number;
  last_used_at?: string;
  body?: string;
};

export type MemoryPreview = {
  memory_type: string;
  title: string;
  summary: string;
  tags: string[];
  paths: string[];
  reasons: string[];
  blocked_sensitive: boolean;
  blocked_reason: string;
};

export type MemoryRankingExplainability = {
  rank: number;
  memory_id: string;
  memory_type: string;
  score: number | null;
  selected: boolean;
  reasons: string[];
};

export type MemoryAuditSummary = {
  who: string;
  when: string;
  action: MemoryAction;
  target: string;
  result: "ok" | "blocked" | "error";
  reason: string;
  command: string;
};

export type MemoryCommandRequest = {
  action: Exclude<MemoryAction, "filter">;
  command: string;
  params: Record<string, unknown>;
};

export type MemoryCommandResult = {
  ok: boolean;
  text: string;
  error?: string | null;
  audit?: Partial<Omit<MemoryAuditSummary, "action" | "command">> | null;
};

export interface MemoryManagementBridge {
  runMemoryCommand(request: MemoryCommandRequest): Promise<MemoryCommandResult>;
}

export function createMockMemoryManagementBridge(): MemoryManagementBridge {
  return {
    async runMemoryCommand(request) {
      return {
        ok: false,
        text: `${request.command}\nnot implemented`,
        error: "memory bridge is not wired",
      };
    },
  };
}

export type MemoryManagementState = {
  filters: MemoryListFilter;
  allItems: MemoryListItem[];
  visibleItems: MemoryListItem[];
  selected: MemoryDetail | null;
  preview: MemoryPreview | null;
  blockedReason: string;
  explainability: MemoryRankingExplainability[];
  auditSummary: MemoryAuditSummary[];
  lastRequest: MemoryCommandRequest | null;
  pendingAction: MemoryAction | null;
  error: string;
};

const DEFAULT_FILTERS: MemoryListFilter = {
  scope: "all",
  type: "all",
  status: "all",
  tag: "",
  limit: 20,
};

function initialState(): MemoryManagementState {
  return {
    filters: { ...DEFAULT_FILTERS },
    allItems: [],
    visibleItems: [],
    selected: null,
    preview: null,
    blockedReason: "",
    explainability: [],
    auditSummary: [],
    lastRequest: null,
    pendingAction: null,
    error: "",
  };
}

export class MemoryManagementModel {
  private state: MemoryManagementState = initialState();

  constructor(
    private readonly bridge: MemoryManagementBridge = createMockMemoryManagementBridge(),
    private readonly now: () => string = () => new Date().toISOString(),
    private readonly actor: string = "gui.operator",
  ) {}

  snapshot(): MemoryManagementState {
    return {
      ...this.state,
      filters: { ...this.state.filters },
      allItems: [...this.state.allItems],
      visibleItems: [...this.state.visibleItems],
      selected: this.state.selected ? { ...this.state.selected } : null,
      preview: this.state.preview ? { ...this.state.preview } : null,
      explainability: this.state.explainability.map((item) => ({ ...item, reasons: [...item.reasons] })),
      auditSummary: this.state.auditSummary.map((item) => ({ ...item })),
      lastRequest: this.state.lastRequest ? { ...this.state.lastRequest, params: { ...this.state.lastRequest.params } } : null,
    };
  }

  setFilter(next: Partial<MemoryListFilter>): MemoryManagementState {
    const normalized: MemoryListFilter = {
      ...this.state.filters,
      ...next,
      tag: String(next.tag ?? this.state.filters.tag ?? "").trim(),
      limit: Number.isFinite(Number(next.limit)) ? Math.max(1, Number(next.limit)) : this.state.filters.limit,
    };
    this.state.filters = normalized;
    this.state.visibleItems = this.applyFilter(this.state.allItems, normalized);
    this.state.pendingAction = "filter";
    return this.snapshot();
  }

  async listMemories(): Promise<MemoryManagementState> {
    const request = buildListRequest(this.state.filters);
    const response = await this.run(request);
    if (response.ok) {
      const items = parseMemoryList(response.text);
      this.state.allItems = items;
      this.state.visibleItems = this.applyFilter(items, this.state.filters);
      this.state.error = "";
    } else {
      this.state.error = response.error || parseReason(response.text) || "memory list failed";
    }
    this.recordAudit("list", "memory:*", request, response);
    this.state.pendingAction = null;
    return this.snapshot();
  }

  async showMemory(memoryId: string): Promise<MemoryManagementState> {
    const request = buildShowRequest(memoryId, this.state.filters.scope === "all" ? undefined : this.state.filters.scope);
    const response = await this.run(request);
    if (response.ok) {
      const detail = parseMemoryDetail(response.text);
      this.state.selected = detail;
      this.state.error = "";
    } else {
      this.state.error = response.error || parseReason(response.text) || "memory show failed";
    }
    this.recordAudit("show", memoryId, request, response);
    this.state.pendingAction = null;
    return this.snapshot();
  }

  async previewFromLastTurn(options: { type?: MemoryType } = {}): Promise<MemoryManagementState> {
    const type = options.type || (this.state.filters.type !== "all" ? this.state.filters.type : "project");
    const request = buildPreviewRequest(type);
    const response = await this.run(request);
    if (response.ok) {
      const preview = parseMemoryPreview(response.text);
      this.state.preview = preview;
      this.state.blockedReason = preview.blocked_reason;
      this.state.error = "";
    } else {
      this.state.error = response.error || parseReason(response.text) || "memory preview failed";
    }
    this.recordAudit("preview", "latest-turn", request, response);
    this.state.pendingAction = null;
    return this.snapshot();
  }

  async applyPreview(): Promise<MemoryManagementState> {
    const preview = this.state.preview;
    if (preview?.blocked_reason) {
      this.state.blockedReason = preview.blocked_reason;
      this.appendAudit({
        who: this.actor,
        when: this.now(),
        action: "apply",
        target: "latest-turn",
        result: "blocked",
        reason: preview.blocked_reason,
        command: "/memory save --from-last-turn",
      });
      return this.snapshot();
    }
    const scope = this.state.filters.scope === "all" ? "project" : this.state.filters.scope;
    const memoryType = (preview?.memory_type || (this.state.filters.type !== "all" ? this.state.filters.type : "project")) as MemoryType;
    const request = buildSaveRequest(scope, memoryType);
    const response = await this.run({
      ...request,
      action: "apply",
    });
    if (response.ok) {
      const detail = parseMemoryDetail(response.text);
      if (detail.memory_id && detail.memory_id !== "-") {
        const existingIndex = this.state.allItems.findIndex((item) => item.memory_id === detail.memory_id);
        const item: MemoryListItem = {
          memory_id: detail.memory_id,
          scope: (detail.scope as MemoryScope | undefined) ?? scope,
          memory_type: detail.memory_type || memoryType,
          status: detail.status || "active",
          title: detail.title || "-",
          summary: detail.summary,
          tags: detail.tags,
          paths: detail.paths,
        };
        if (existingIndex >= 0) {
          this.state.allItems.splice(existingIndex, 1, item);
        } else {
          this.state.allItems.unshift(item);
        }
        this.state.visibleItems = this.applyFilter(this.state.allItems, this.state.filters);
      }
      this.state.error = "";
    } else {
      this.state.error = response.error || parseReason(response.text) || "memory apply failed";
    }
    this.recordAudit("apply", "latest-turn", request, response);
    this.state.pendingAction = null;
    return this.snapshot();
  }

  async saveFromLastTurn(options: { scope?: MemoryScope; type?: MemoryType } = {}): Promise<MemoryManagementState> {
    const scope = options.scope || (this.state.filters.scope === "all" ? "project" : this.state.filters.scope);
    const type = options.type || (this.state.filters.type === "all" ? "project" : this.state.filters.type);
    const request = buildSaveRequest(scope, type);
    const response = await this.run(request);
    if (!response.ok) {
      this.state.error = response.error || parseReason(response.text) || "memory save failed";
    } else {
      this.state.error = "";
    }
    this.recordAudit("save", "latest-turn", request, response);
    this.state.pendingAction = null;
    return this.snapshot();
  }

  async deleteMemory(memoryId: string): Promise<MemoryManagementState> {
    const request = buildDeleteRequest(memoryId);
    const response = await this.run(request);
    if (response.ok) {
      this.state.allItems = this.state.allItems.map((item) =>
        item.memory_id === memoryId
          ? {
              ...item,
              status: "deleted",
            }
          : item,
      );
      this.state.visibleItems = this.applyFilter(this.state.allItems, this.state.filters);
      if (this.state.selected?.memory_id === memoryId) {
        this.state.selected = {
          ...this.state.selected,
          status: "deleted",
        };
      }
      this.state.error = "";
    } else {
      this.state.error = response.error || parseReason(response.text) || "memory delete failed";
    }
    this.recordAudit("delete", memoryId, request, response);
    this.state.pendingAction = null;
    return this.snapshot();
  }

  async archiveMemory(memoryId: string, reason = "operator_archive"): Promise<MemoryManagementState> {
    const request = buildArchiveRequest(memoryId, reason);
    const response = await this.run(request);
    if (response.ok) {
      this.state.allItems = this.state.allItems.map((item) =>
        item.memory_id === memoryId
          ? {
              ...item,
              status: "archived",
            }
          : item,
      );
      this.state.visibleItems = this.applyFilter(this.state.allItems, this.state.filters);
      if (this.state.selected?.memory_id === memoryId) {
        this.state.selected = {
          ...this.state.selected,
          status: "archived",
        };
      }
      this.state.error = "";
    } else {
      this.state.blockedReason = response.error || parseReason(response.text) || "memory archive failed";
      this.state.error = this.state.blockedReason;
    }
    this.recordAudit("archive", memoryId, request, response);
    this.state.pendingAction = null;
    return this.snapshot();
  }

  async refreshDebug(limit = 20): Promise<MemoryManagementState> {
    const request = buildDebugRequest(limit);
    const response = await this.run(request);
    if (response.ok) {
      const debug = parseMemoryDebug(response.text);
      this.state.blockedReason = debug.blockedReason;
      this.state.explainability = debug.explainability;
      this.state.error = "";
    } else {
      this.state.error = response.error || parseReason(response.text) || "memory debug failed";
    }
    this.recordAudit("debug", "memory-context", request, response);
    this.state.pendingAction = null;
    return this.snapshot();
  }

  private async run(request: MemoryCommandRequest): Promise<MemoryCommandResult> {
    this.state.pendingAction = request.action;
    this.state.lastRequest = request;
    return this.bridge.runMemoryCommand(request);
  }

  private applyFilter(items: MemoryListItem[], filters: MemoryListFilter): MemoryListItem[] {
    return items.filter((item) => {
      if (filters.scope !== "all" && item.scope && item.scope !== filters.scope) {
        return false;
      }
      if (filters.type !== "all" && item.memory_type !== filters.type) {
        return false;
      }
      if (filters.status !== "all" && item.status !== filters.status) {
        return false;
      }
      if (filters.tag) {
        const tags = (item.tags || []).map((tag) => String(tag).trim().toLowerCase());
        if (!tags.includes(filters.tag.toLowerCase())) {
          return false;
        }
      }
      return true;
    });
  }

  private recordAudit(action: Exclude<MemoryAction, "filter">, target: string, request: MemoryCommandRequest, response: MemoryCommandResult): void {
    const reason = parseReason(response.text) || response.error || "";
    const result: MemoryAuditSummary["result"] = response.ok ? (reason ? "blocked" : "ok") : "error";
    this.appendAudit({
      who: String(response.audit?.who || this.actor),
      when: String(response.audit?.when || this.now()),
      action,
      target: String(response.audit?.target || target),
      result,
      reason: String(response.audit?.reason || reason),
      command: request.command,
    });
  }

  private appendAudit(entry: MemoryAuditSummary): void {
    this.state.auditSummary = [entry, ...this.state.auditSummary].slice(0, 20);
  }
}

export function buildListRequest(filters: MemoryListFilter): MemoryCommandRequest {
  const args = [`--limit ${filters.limit}`];
  if (filters.scope !== "all") {
    args.push(`--scope ${filters.scope}`);
  }
  if (filters.type !== "all") {
    args.push(`--type ${filters.type}`);
  }
  if (filters.status !== "all") {
    args.push(`--status ${filters.status}`);
  }
  return {
    action: "list",
    command: `/memory list ${args.join(" ")}`.trim(),
    params: {
      limit: filters.limit,
      scope: filters.scope,
      type: filters.type,
      status: filters.status,
      tag: filters.tag,
    },
  };
}

export function buildShowRequest(memoryId: string, scope?: MemoryScope): MemoryCommandRequest {
  const args = [`/memory show ${memoryId}`];
  if (scope) {
    args.push(`--scope ${scope}`);
  }
  return {
    action: "show",
    command: args.join(" ").trim(),
    params: {
      memory_id: memoryId,
      scope: scope ?? "project",
    },
  };
}

export function buildPreviewRequest(type: MemoryType): MemoryCommandRequest {
  return {
    action: "preview",
    command: `/memory preview --from-last-turn --type ${type}`,
    params: {
      from_last_turn: true,
      type,
    },
  };
}

export function buildSaveRequest(scope: MemoryScope, type: MemoryType): MemoryCommandRequest {
  return {
    action: "save",
    command: `/memory save --from-last-turn --scope ${scope} --type ${type}`,
    params: {
      from_last_turn: true,
      scope,
      type,
    },
  };
}

export function buildDeleteRequest(memoryId: string): MemoryCommandRequest {
  return {
    action: "delete",
    command: `/memory delete ${memoryId}`,
    params: {
      memory_id: memoryId,
    },
  };
}

export function buildArchiveRequest(memoryId: string, reason: string): MemoryCommandRequest {
  return {
    action: "archive",
    command: `/memory archive ${memoryId} --reason ${reason}`,
    params: {
      memory_id: memoryId,
      reason,
    },
  };
}

export function buildDebugRequest(limit: number): MemoryCommandRequest {
  return {
    action: "debug",
    command: `/memory debug --limit ${Math.max(1, Number(limit) || 20)}`,
    params: {
      limit: Math.max(1, Number(limit) || 20),
    },
  };
}

export function parseMemoryList(text: string): MemoryListItem[] {
  const rows: MemoryListItem[] = [];
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("- ")) {
      continue;
    }
    const cells = trimmed.slice(2).split("|").map((part) => part.trim());
    const memoryId = cells[0] || "";
    const item: MemoryListItem = {
      memory_id: memoryId,
      memory_type: "-",
      status: "-",
      title: "-",
    };
    for (const cell of cells.slice(1)) {
      const [key, ...rest] = cell.split("=");
      const value = rest.join("=").trim();
      if (key === "type") {
        item.memory_type = value || "-";
      } else if (key === "status") {
        item.status = value || "-";
      } else if (key === "title") {
        item.title = value || "-";
      } else if (key === "scope" && (value === "project" || value === "user")) {
        item.scope = value;
      }
    }
    rows.push(item);
  }
  return rows;
}

export function parseMemoryDetail(text: string): MemoryDetail {
  const map = parseKeyValueMap(text);
  return {
    memory_id: map.memory_id || "",
    scope: map.scope === "user" ? "user" : map.scope === "project" ? "project" : undefined,
    memory_type: map.type || "-",
    status: map.status || "-",
    title: map.title || "-",
    summary: map.summary || "",
    body: map.body || "",
    tags: splitListField(map.tags),
    paths: splitListField(map.paths),
    hit_count: numericOrUndefined(map.hit_count),
    last_used_at: map.last_used_at || "",
  };
}

export function parseMemoryPreview(text: string): MemoryPreview {
  const map = parseKeyValueMap(text);
  return {
    memory_type: map.type || "-",
    title: map.title || "-",
    summary: map.summary || "",
    tags: splitListField(map.tags),
    paths: splitListField(map.paths),
    reasons: splitListField(map.reasons),
    blocked_sensitive: map.blocked_sensitive === "true",
    blocked_reason: map.blocked_reason === "-" ? "" : (map.blocked_reason || ""),
  };
}

export function parseMemoryDebug(text: string): { blockedReason: string; explainability: MemoryRankingExplainability[] } {
  const blockedMatch = text.match(/snapshot_blocked_reason=([^\n\r]*)/);
  const blockedReason = (blockedMatch?.[1] || "-").trim();
  const explainability: MemoryRankingExplainability[] = [];
  const rankPattern = /^# rank=(\d+) \| memory_id=([^|]+)\| type=([^|]+)\| score=([^|]+)\| selected=(true|false)\| reasons=(.*)$/;
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line.startsWith("# rank=")) {
      continue;
    }
    const normalized = line
      .replace(" | type=", "| type=")
      .replace(" | score=", "| score=")
      .replace(" | selected=", "| selected=")
      .replace(" | reasons=", "| reasons=");
    const match = normalized.match(rankPattern);
    if (!match) {
      continue;
    }
    explainability.push({
      rank: Number(match[1]) || 0,
      memory_id: match[2].trim(),
      memory_type: match[3].trim(),
      score: match[4].trim() === "-" ? null : Number(match[4]),
      selected: match[5] === "true",
      reasons: splitListField(match[6].trim()),
    });
  }
  return {
    blockedReason: blockedReason === "-" ? "" : blockedReason,
    explainability,
  };
}

function parseKeyValueMap(text: string): Record<string, string> {
  const result: Record<string, string> = {};
  for (const line of text.split(/\r?\n/)) {
    const index = line.indexOf("=");
    if (index <= 0) {
      continue;
    }
    const key = line.slice(0, index).trim();
    const value = line.slice(index + 1).trim();
    if (key) {
      result[key] = value;
    }
  }
  return result;
}

function splitListField(value: string | undefined): string[] {
  const text = String(value || "").trim();
  if (!text || text === "-") {
    return [];
  }
  return text.split(",").map((item) => item.trim()).filter(Boolean);
}

function parseReason(text: string): string {
  const blockedMatch = text.match(/blocked_reason=([^\n\r]+)/);
  if (blockedMatch?.[1]) {
    const blocked = blockedMatch[1].trim();
    return blocked === "-" ? "" : blocked;
  }
  const saveBlocked = text.match(/memory save blocked:\s*([^\n\r]+)/);
  if (saveBlocked?.[1]) {
    return saveBlocked[1].trim();
  }
  const genericFailure = text.match(/(failed:[^\n\r]+)/);
  if (genericFailure?.[1]) {
    return genericFailure[1].trim();
  }
  return "";
}

function numericOrUndefined(text: string | undefined): number | undefined {
  if (text === undefined) {
    return undefined;
  }
  const value = Number(text);
  return Number.isFinite(value) ? value : undefined;
}

@customElement("memory-management-page")
export class MemoryManagementPage extends LitElement {
  static styles = css`
    :host {
      display: block;
    }
    .panel {
      border-radius: 14px;
      border: 1px solid rgba(150, 186, 196, 0.16);
      background: rgba(10, 22, 31, 0.9);
      padding: 14px;
      display: grid;
      gap: 10px;
      color: #d7e6ee;
    }
    .row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }
    .hint {
      margin: 0;
      color: #9bb1bc;
      font-size: 12px;
    }
    .item {
      border: 1px solid rgba(150, 186, 196, 0.14);
      border-radius: 10px;
      padding: 8px 10px;
      background: rgba(17, 32, 43, 0.7);
    }
    button {
      border: 0;
      border-radius: 999px;
      padding: 6px 10px;
      background: #2d7b74;
      color: white;
      cursor: pointer;
      font: inherit;
    }
  `;

  @property({ attribute: false }) model = new MemoryManagementModel();
  @state() private view = this.model.snapshot();

  connectedCallback(): void {
    super.connectedCallback();
    void this.refresh();
  }

  render() {
    return html`
      <section class="panel">
        <h3>Memory Management</h3>
        <p class="hint">
          CLI contract: list/show/filter + preview/apply/save/delete/archive。当前动作以 /memory ... 命令语义对齐。
        </p>
        <div class="row">
          <button type="button" data-testid="memory-list" @click=${() => void this.refresh()}>刷新列表</button>
          <button type="button" data-testid="memory-preview" @click=${() => void this.preview()}>Preview</button>
          <button type="button" data-testid="memory-apply" @click=${() => void this.apply()}>Apply</button>
          <button type="button" data-testid="memory-save" @click=${() => void this.save()}>Save</button>
          <button type="button" data-testid="memory-debug" @click=${() => void this.debug()}>Debug</button>
        </div>
        <div class="item" data-testid="memory-blocked-reason">blocked_reason: ${this.view.blockedReason || "-"}</div>
        <div class="item" data-testid="memory-explainability">
          explainability(${this.view.explainability.length}):
          ${this.view.explainability.map(
            (row) => html`<div>#${row.rank} ${row.memory_id} score=${row.score ?? "-"} reasons=${row.reasons.join(",") || "-"}</div>`,
          )}
        </div>
        <div class="item" data-testid="memory-audit-summary">
          audit summary(${this.view.auditSummary.length}):
          ${this.view.auditSummary.map(
            (row) =>
              html`<div>
                ${row.when} | ${row.who} | ${row.action} | ${row.target} | ${row.result} | ${row.reason || "-"}
              </div>`,
          )}
        </div>
      </section>
    `;
  }

  private async refresh() {
    await this.model.listMemories();
    this.view = this.model.snapshot();
  }

  private async preview() {
    await this.model.previewFromLastTurn();
    this.view = this.model.snapshot();
  }

  private async apply() {
    await this.model.applyPreview();
    this.view = this.model.snapshot();
  }

  private async save() {
    await this.model.saveFromLastTurn();
    this.view = this.model.snapshot();
  }

  private async debug() {
    await this.model.refreshDebug(20);
    this.view = this.model.snapshot();
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "memory-management-page": MemoryManagementPage;
  }
}
