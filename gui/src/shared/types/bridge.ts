export const PROTOCOL_VERSION = "v1" as const;

export const BRIDGE_ACTIONS = [
  "control_ui.bootstrap",
  "control_ui.state",
  "gateway.events.poll",
  "task.run",
  "shell.run",
  "task.stop",
  "chat.send",
  "thread.list",
  "thread.resume",
  "connect.initialize",
  "connect.capabilities",
  "connect.ping",
  "access.posture.get",
  "nodes.list",
  "config.validate",
  "config.apply",
  "config.restart.report",
  "health.get",
  "health.probes",
  "logs.tail",
  "gateway.state.get",
  "gateway.events.list",
  "gateway.workflows.list",
  "gateway.trace.timeline",
  "workflows.list",
  "workflows.get",
  "workflows.resume",
  "approvals.list",
  "approvals.get",
  "approvals.resolve",
  "browser.status",
  "browser.proxy",
  "browser.start",
  "browser.stop",
  "browser.tabs",
  "browser.open",
  "browser.focus",
  "browser.close",
  "browser.navigate",
  "browser.snapshot",
  "browser.console",
  "browser.screenshot",
  "browser.pdf",
  "browser.download",
  "browser.wait_download",
  "browser.upload",
  "browser.dialog",
  "browser.act",
  "approval.list",
  "approval.resolve",
  "audit.list",
  "plugin.list",
  "connector.list",
  "plugin.enable",
  "plugin.disable",
  "plugin.reload",
  "settings.get",
  "settings.update",
] as const;

export type BridgeAction = (typeof BRIDGE_ACTIONS)[number];

export const BRIDGE_EVENT_KINDS = [
  "task_started",
  "task_progress",
  "task_completed",
  "task_failed",
  "tool_event",
  "approval_requested",
  "approval_resolved",
  "audit_written",
  "browser_state_changed",
  "plugin_state_changed",
  "settings_changed",
] as const;

export type BridgeEventKind = (typeof BRIDGE_EVENT_KINDS)[number];
export type BridgeStatus = "accepted" | "ok" | "warning" | "error";

export type BridgeClientIdentity = {
  name: string;
  version: string;
};

export type BrowserStatusSummary = {
  running: boolean;
  activeProfile: string | null;
  tabCount: number;
};

export type GatewayMethodMetadata = {
  method: string;
  family: string;
  description?: string;
  auth_required?: boolean;
  required_scopes?: string[];
  control_plane_write?: boolean;
  emits_events?: boolean;
  idempotent?: boolean;
  metadata?: Record<string, unknown>;
};

export type PairingPendingRef = {
  approvalId: string;
  traceId: string;
  title: string;
  actionType: string;
  requestedAt?: string;
};

export type AccessPostureSummary = {
  access: {
    posture: "local-only" | "local+remote" | "remote-only" | "unknown" | string;
    local: {
      enabled: boolean;
      channel?: string;
      origin?: string;
    };
    remote: {
      enabled: boolean;
      channel?: string;
      origin?: string | null;
    };
  };
  auth: {
    mode: "trusted_local" | "remote_authenticated" | "authenticated" | "anonymous" | string;
    origin: "local" | "remote" | "unknown" | string;
    authenticated: boolean;
    authSource?: string;
    trustLevel?: string;
    actorId?: string;
    clientType?: string;
    roles: string[];
    scopes: string[];
  };
  pairing: {
    pendingRequestCount: number;
    pendingApprovalCount: number;
    source: string;
    hasNativeContract: boolean;
    summary?: string;
    pendingRefs?: PairingPendingRef[];
  };
  summary: {
    pendingPairingRequestCount: number;
    pendingApprovalCount: number;
    accessPosture: string;
    authMode: string;
    authOrigin: string;
  };
};

export type NodeInventoryItem = {
  nodeId: string;
  deviceId: string;
  kind: "local" | "remote" | "device" | string;
  label: string;
  status: "online" | "offline" | "pending_pairing" | "unknown" | string;
  access: {
    enabled: boolean;
    channel?: string;
    origin?: string | null;
    posture?: string;
  };
  auth: AccessPostureSummary["auth"];
  pairing: AccessPostureSummary["pairing"] & {
    writeSupported?: boolean;
  };
  activity: {
    eventCount: number;
    workflowCount: number;
    approvalCount: number;
    lastSeenAt?: string | null;
  };
  runtime: {
    workspaceTrust: string;
    toolCount: number;
    mcpServerCount: number;
    appConnectorCount: number;
  };
};

export type NodesInventorySnapshot = {
  nodes: NodeInventoryItem[];
  devices: Array<{
    deviceId: string;
    nodeId: string;
    kind: string;
    status: string;
    label: string;
  }>;
  accessPosture: AccessPostureSummary;
  pairing: AccessPostureSummary["pairing"];
  summary: {
    totalNodes: number;
    localNodes: number;
    remoteNodes: number;
    pendingPairingRequestCount: number;
    pendingApprovalCount: number;
    recentEvents: number;
    recentWorkflowRuns: number;
    recentApprovalTickets: number;
    mcpServerCount: number;
    appConnectorCount: number;
    lastSeenAt?: string | null;
    limit: number;
  };
  capabilities: {
    readOnly: boolean;
    pairingWriteSupported: boolean;
    pairingWriteReason?: string;
  };
  runtimeRegistry: {
    workspaceTrust: string;
    mcpServers: Array<Record<string, unknown>>;
    appConnectors: Array<Record<string, unknown>>;
    toolCount: number;
    source: string;
  };
  source: {
    contract: string;
    derivedFrom: string[];
  };
};

export type ControlUiBootstrap = {
  basePath: string;
  assistantName: string;
  assistantAvatar: string;
  assistantAgentId: string;
  serverVersion: string;
  providerLabel?: string;
  gateway: {
    methods: string[];
    streams: string[];
  };
};

export type ControlUiStateSnapshot = {
  health: {
    status: string;
    provider?: Record<string, unknown>;
  };
  runtimePolicy: Record<string, unknown>;
  approvalStatus: Record<string, unknown>;
  events: Array<Record<string, unknown>>;
  workflowRuns: Array<Record<string, unknown>>;
  actionRequests: Array<Record<string, unknown>>;
  approvalTickets: Array<Record<string, unknown>>;
  auditRecords: Array<Record<string, unknown>>;
  diagnostics: Record<string, unknown>;
  accessPosture?: AccessPostureSummary;
  connectors: Array<Record<string, unknown>>;
};

export type GatewayEventFrame = {
  cursor: number;
  stream: string;
  event: string;
  payload: Record<string, unknown>;
  emittedAt?: string;
};

export type GatewayEventPollResult = {
  cursor: number;
  events: GatewayEventFrame[];
};

export type GatewayLogSourceInfo = {
  key: string;
  label: string;
  path?: string | null;
};

export type GatewayLogTailSnapshot = {
  source: string;
  label: string;
  path?: string | null;
  lines: string[];
  text: string;
  lineCount: number;
  truncated: boolean;
  availableSources: GatewayLogSourceInfo[];
};

export type BrowserProxyRequest = {
  method: "GET" | "POST" | "DELETE";
  path: string;
  query?: Record<string, string | number | boolean>;
  body?: Record<string, unknown>;
};

export type BrowserProxyResponse = {
  status: number;
  result: Record<string, unknown>;
  files?: Array<Record<string, unknown>>;
};

export type ThreadSummary = {
  thread_id: string;
  name: string;
  updated_at: string;
  turn_count: number;
  cwd?: string;
  last_user_text?: string;
  last_assistant_text?: string;
};

export type ThreadHistoryEntry = {
  role: "user" | "assistant";
  content: string;
};

export type StoredToolEvent = {
  name: string;
  ok: boolean;
  summary: string;
  payload: Record<string, unknown>;
};

export type StoredActivityEvent = {
  title: string;
  status: string;
  detail: string;
  kind: string;
};

export type ShellRunPayload = {
  command: string;
  text?: string;
  cwd?: string;
  workdir?: string;
  timeout_ms?: number;
  timeoutMs?: number;
  timeout_sec?: number;
  login?: boolean;
  tty?: boolean;
  shell?: string;
  max_output_chars?: number;
};

export type ShellRunResult = {
  accepted: boolean;
  approval_required?: boolean;
  command: string;
  cwd?: string | null;
  ok?: boolean;
  status?: string;
  exit_code?: number | null;
  stdout?: string;
  stderr?: string;
  duration_ms?: number | null;
  thread_id?: string | null;
  assistant_text?: string;
  user_text?: string;
  command_display_text?: string;
  commentary_text?: string;
  response_items?: Array<Record<string, unknown>>;
  tool_events?: StoredToolEvent[];
  activity_events?: StoredActivityEvent[];
  turn_events?: Array<Record<string, unknown>>;
  tool_event_count?: number;
};

export type ThreadTurn = {
  timestamp: string;
  user_text: string;
  commentary_text?: string;
  assistant_text?: string;
  assistant_history_text?: string;
  handled_as_command?: boolean;
  status?: Record<string, unknown>;
  runtime_state?: Record<string, unknown>;
  tool_events?: StoredToolEvent[];
  activity_events?: StoredActivityEvent[];
};

export type ApprovalSummary = {
  approval_id: string;
  action_id?: string;
  title: string;
  risk: "low" | "medium" | "high";
  trace_id: string;
  status: "pending" | "approved" | "rejected";
  summary?: string;
  requested_at?: string;
  requested_by?: string;
  reason?: string;
};

export type PluginSummary = {
  plugin_id: string;
  title: string;
  enabled: boolean;
  health: "ready" | "warning" | "error";
};

export type ConnectorSummary = {
  connector_key: string;
  plugin_name: string;
  display_name: string;
  connector_kind: string;
  supports_webhook: boolean;
  supports_polling: boolean;
  supports_actions: boolean;
  approval_required?: boolean;
  enabled: boolean;
  health: "ready" | "warning" | "error";
  event_types?: string[];
  action_types?: string[];
  source_kind?: "gateway" | "plugin_app" | string;
};

export type SettingsSnapshot = {
  model: string;
  browserHeadless: boolean;
  pluginAutoLoad: boolean;
  workspaceRoot: string;
  workspaceTrust?: "trusted" | "untrusted" | "unknown" | string;
  providerLabel?: string;
  runtimePolicy?: {
    approval_policy?: string;
    sandbox_mode?: string;
    web_search_mode?: string;
    network_access?: string;
  };
  mcpServers?: Array<{
    name: string;
    source: "user" | "plugin" | string;
    config: Record<string, unknown>;
  }>;
  appConnectors?: Array<{
    connector_id: string;
    plugin_name: string;
  }>;
};

export type ConfigBlockedField = {
  field: string;
  code: string;
  reason: string;
};

export type ConfigApplyPathEntry = {
  field: string;
  handler: string;
};

export type ConfigRestartReport = {
  required: boolean;
  reasons: string[];
  allowed: boolean;
  mode: string;
  blockedReason?: string | null;
};

export type ConfigValidationResult = {
  changedFields: string[];
  applyableFields: string[];
  blocked: ConfigBlockedField[];
  blockedFields: string[];
  warnings: string[];
  applyPath: ConfigApplyPathEntry[];
  restart: ConfigRestartReport;
};

export type ConfigApplyResult = {
  applied: boolean;
  status: "applied" | "partial" | "blocked";
  appliedFields: string[];
  blockedFields: string[];
  validation: ConfigValidationResult;
  restart: ConfigRestartReport;
  settings: SettingsSnapshot;
};

export type SystemStatusSummary = {
  model: "ready" | "warning" | "error";
  browser: "ready" | "warning" | "error";
  plugins: "ready" | "warning" | "error";
  connectors: "ready" | "warning" | "error";
};

export type BridgeRequest<TPayload = unknown> = {
  protocol_version: typeof PROTOCOL_VERSION;
  request_id: string;
  action: BridgeAction;
  payload: TPayload;
  client: BridgeClientIdentity;
};

export type BridgeError = {
  code: string;
  message: string;
  detail?: Record<string, unknown>;
  retryable: boolean;
};

export type BridgeResponse<TData = unknown> = {
  protocol_version: typeof PROTOCOL_VERSION;
  request_id: string;
  action: BridgeAction;
  ok: boolean;
  data: TData | null;
  error: BridgeError | null;
  meta: {
    server_time: string;
  };
};

export type BridgeEvent<TPayload = unknown> = {
  protocol_version: typeof PROTOCOL_VERSION;
  event_id: string;
  request_id: string;
  kind: BridgeEventKind;
  name: string;
  status: BridgeStatus;
  summary: string;
  payload: TPayload;
  ts: string;
};

export type NormalizedBridgeEvent = BridgeEvent<Record<string, unknown>>;

export type RequestOptions = {
  requestId?: string;
  client?: BridgeClientIdentity;
};

export const DEFAULT_CLIENT: BridgeClientIdentity = {
  name: "easyclaw-gui",
  version: "0.1.0",
};

export function createBridgeRequest<TPayload>(
  action: BridgeAction,
  payload: TPayload,
  options: RequestOptions = {},
): BridgeRequest<TPayload> {
  return {
    protocol_version: PROTOCOL_VERSION,
    request_id: options.requestId ?? generateId("req"),
    action,
    payload,
    client: options.client ?? DEFAULT_CLIENT,
  };
}

export function createBridgeSuccess<TData>(
  request: BridgeRequest<unknown>,
  data: TData,
): BridgeResponse<TData> {
  return {
    protocol_version: PROTOCOL_VERSION,
    request_id: request.request_id,
    action: request.action,
    ok: true,
    data,
    error: null,
    meta: {
      server_time: new Date().toISOString(),
    },
  };
}

export function createBridgeFailure(
  request: BridgeRequest<unknown>,
  error: BridgeError,
): BridgeResponse<null> {
  return {
    protocol_version: PROTOCOL_VERSION,
    request_id: request.request_id,
    action: request.action,
    ok: false,
    data: null,
    error,
    meta: {
      server_time: new Date().toISOString(),
    },
  };
}

export function normalizeBridgeEvent(
  event: Partial<BridgeEvent<Record<string, unknown>>> &
    Pick<BridgeEvent<Record<string, unknown>>, "request_id" | "kind" | "name">,
): NormalizedBridgeEvent {
  return {
    protocol_version: PROTOCOL_VERSION,
    event_id: event.event_id ?? generateId("evt"),
    request_id: event.request_id,
    kind: event.kind,
    name: event.name,
    status: event.status ?? "ok",
    summary: event.summary ?? event.name,
    payload: event.payload ?? {},
    ts: event.ts ?? new Date().toISOString(),
  };
}

export function toBridgeError(error: unknown, fallbackCode = "bridge.unknown"): BridgeError {
  if (typeof error === "object" && error !== null) {
    const candidate = error as Partial<BridgeError>;
    if (typeof candidate.code === "string" && typeof candidate.message === "string") {
      return {
        code: candidate.code,
        message: candidate.message,
        detail: candidate.detail,
        retryable: candidate.retryable ?? false,
      };
    }
  }
  if (error instanceof Error) {
    return {
      code: fallbackCode,
      message: error.message,
      retryable: false,
    };
  }
  return {
    code: fallbackCode,
    message: String(error ?? "unknown error"),
    retryable: false,
  };
}

export function generateId(prefix: string): string {
  const random = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID().replace(/-/g, "").slice(0, 12)
    : Math.random().toString(16).slice(2, 14);
  return `${prefix}_${random}`;
}
