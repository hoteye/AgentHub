import {
  type AccessPostureSummary,
  createBridgeFailure,
  createBridgeSuccess,
  normalizeBridgeEvent,
  type ApprovalSummary,
  type BridgeAction,
  type ConnectorSummary,
  type BridgeEvent,
  type BridgeRequest,
  type BridgeResponse,
  type BrowserStatusSummary,
  type BrowserProxyRequest,
  type BrowserProxyResponse,
  type ControlUiBootstrap,
  type ControlUiStateSnapshot,
  type GatewayEventPollResult,
  type GatewayLogTailSnapshot,
  type GatewayMethodMetadata,
  type NodesInventorySnapshot,
  type PluginSummary,
  type SettingsSnapshot,
  type ThreadHistoryEntry,
  type ThreadSummary,
  type ThreadTurn,
} from "../types/bridge.ts";

type EventListener = (event: BridgeEvent<Record<string, unknown>>) => void;

export interface HostAdapter {
  request<TData = unknown>(request: BridgeRequest<unknown>): Promise<BridgeResponse<TData>>;
  subscribe(listener: EventListener): () => void;
  getControlUiBootstrap(): Promise<ControlUiBootstrap>;
  getControlUiState(limit?: number): Promise<ControlUiStateSnapshot>;
  pollGatewayEvents(cursor?: number, streams?: string[]): Promise<GatewayEventPollResult>;
  browserProxy(request: BrowserProxyRequest): Promise<BrowserProxyResponse>;
}

const SETTINGS_SNAPSHOT: SettingsSnapshot = {
  model: "gpt-5.4",
  browserHeadless: false,
  pluginAutoLoad: true,
  workspaceRoot: "/home/lyc/project/AgentHub",
};

const MOCK_GATEWAY_METHODS: GatewayMethodMetadata[] = [
  {
    method: "connect.initialize",
    family: "connect",
    auth_required: false,
    required_scopes: [],
    control_plane_write: false,
    emits_events: false,
  },
  {
    method: "connect.capabilities",
    family: "connect",
    auth_required: false,
    required_scopes: [],
    control_plane_write: false,
    emits_events: false,
  },
  {
    method: "connect.ping",
    family: "connect",
    auth_required: false,
    required_scopes: [],
    control_plane_write: false,
    emits_events: false,
  },
  {
    method: "access.posture.get",
    family: "access",
    auth_required: false,
    required_scopes: [],
    control_plane_write: false,
    emits_events: false,
  },
  {
    method: "nodes.list",
    family: "nodes",
    auth_required: true,
    required_scopes: ["gateway.read"],
    control_plane_write: false,
    emits_events: false,
  },
  {
    method: "config.validate",
    family: "config",
    auth_required: true,
    required_scopes: ["config.read"],
    control_plane_write: false,
    emits_events: false,
  },
  {
    method: "config.apply",
    family: "config",
    auth_required: true,
    required_scopes: ["config.write"],
    control_plane_write: true,
    emits_events: true,
  },
  {
    method: "config.restart.report",
    family: "config",
    auth_required: true,
    required_scopes: ["config.read"],
    control_plane_write: false,
    emits_events: false,
  },
  {
    method: "health.probes",
    family: "health",
    auth_required: true,
    required_scopes: ["gateway.read"],
    control_plane_write: false,
    emits_events: false,
  },
  {
    method: "logs.tail",
    family: "logs",
    auth_required: true,
    required_scopes: ["gateway.read"],
    control_plane_write: false,
    emits_events: false,
  },
  {
    method: "workflows.resume",
    family: "workflows",
    auth_required: true,
    required_scopes: ["gateway.write"],
    control_plane_write: true,
    emits_events: true,
  },
  {
    method: "approvals.resolve",
    family: "approvals",
    auth_required: true,
    required_scopes: ["approvals.resolve"],
    control_plane_write: true,
    emits_events: true,
  },
  {
    method: "browser.proxy",
    family: "browser",
    auth_required: true,
    required_scopes: ["browser.write"],
    control_plane_write: true,
    emits_events: true,
    metadata: {
      transport: "proxy",
    },
  },
  {
    method: "plugin.list",
    family: "plugins",
    auth_required: true,
    required_scopes: ["plugins.read"],
    control_plane_write: false,
    emits_events: false,
  },
];

const APPROVALS: ApprovalSummary[] = [
  {
    approval_id: "approval_demo_001",
    action_id: "action_demo_001",
    title: "GitHub issue close",
    risk: "high",
    trace_id: "trace_demo_001",
    status: "pending",
    summary: "Close GitHub issue after approval",
    requested_at: "2026-03-28T08:00:00Z",
    requested_by: "demo-operator",
    reason: "Issue close mutates external system state",
  },
  {
    approval_id: "approval_demo_002",
    action_id: "action_demo_002",
    title: "Browser form submit",
    risk: "medium",
    trace_id: "trace_demo_002",
    status: "pending",
    summary: "Submit external browser form",
    requested_at: "2026-03-28T08:05:00Z",
    requested_by: "demo-operator",
    reason: "Form submit may write remote data",
  },
];

const AUDIT_RECORDS = [
  {
    audit_id: "audit_demo_001",
    trace_id: "trace_demo_001",
    workflow_run_id: "run_1",
    stage: "approval",
    status: "pending",
    summary: "GitHub issue close approved",
    approval_id: "approval_demo_001",
    action_id: "action_demo_001",
  },
  {
    audit_id: "audit_demo_002",
    trace_id: "trace_demo_002",
    workflow_run_id: "run_2",
    stage: "approval",
    status: "pending",
    summary: "Browser submit rejected",
    approval_id: "approval_demo_002",
    action_id: "action_demo_002",
  },
  {
    audit_id: "audit_demo_003",
    trace_id: "trace_demo_002",
    workflow_run_id: "run_2",
    stage: "execution",
    status: "running",
    summary: "browser proxy command started",
    action_id: "action_demo_002",
  },
];

const WORKFLOW_RUNS = [
  {
    workflow_run_id: "run_1",
    trace_id: "trace_demo_001",
    plugin_name: "github_phase1",
    workflow_name: "handle_github_issue_opened",
    status: "paused",
    current_step: "paused_for_operator_review",
    result_summary: "workflow recommends issue triage follow-up",
    started_at: "2026-03-28T08:00:00Z",
    updated_at: "2026-03-28T08:01:30Z",
  },
  {
    workflow_run_id: "run_2",
    trace_id: "trace_demo_002",
    plugin_name: "browser_phase1",
    workflow_name: "browser_mutate_after_approval",
    status: "running",
    current_step: "browser_action_executing",
    result_summary: "browser mutate workflow in progress",
    started_at: "2026-03-28T08:05:00Z",
    updated_at: "2026-03-28T08:06:00Z",
  },
] as Array<Record<string, unknown>>;

const ACTION_REQUESTS = [
  {
    action_id: "action_demo_001",
    action_type: "github.issue.comment",
    trace_id: "trace_demo_001",
    workflow_run_id: "run_1",
    requested_at: "2026-03-28T08:00:30Z",
    requested_by: "workflow.github",
    status: "pending",
  },
  {
    action_id: "action_demo_002",
    action_type: "browser.click",
    trace_id: "trace_demo_002",
    workflow_run_id: "run_2",
    requested_at: "2026-03-28T08:05:20Z",
    requested_by: "workflow.browser",
    status: "running",
  },
] as Array<Record<string, unknown>>;

const PLUGINS: PluginSummary[] = [
  {
    plugin_id: "psbc_policy",
    title: "邮储制度合规插件",
    enabled: true,
    health: "ready",
  },
  {
    plugin_id: "demo_plugin",
    title: "Demo Plugin",
    enabled: false,
    health: "warning",
  },
];

const CONNECTORS: ConnectorSummary[] = [
  {
    connector_key: "github_webhook",
    plugin_name: "github_phase1",
    display_name: "GitHub Webhook",
    connector_kind: "webhook",
    supports_webhook: true,
    supports_polling: false,
    supports_actions: true,
    approval_required: true,
    enabled: true,
    health: "ready",
    event_types: ["github.issue.created", "github.issue_comment.created"],
    action_types: ["github.issue.close", "github.workflow.dispatch"],
    source_kind: "gateway",
  },
  {
    connector_key: "github_dispatch",
    plugin_name: "github_phase1",
    display_name: "GitHub Dispatch",
    connector_kind: "api",
    supports_webhook: false,
    supports_polling: false,
    supports_actions: true,
    approval_required: true,
    enabled: true,
    health: "ready",
    event_types: [],
    action_types: ["github.workflow.dispatch"],
    source_kind: "plugin_app",
  },
];

const ACCESS_POSTURE_SUMMARY: AccessPostureSummary = {
  access: {
    posture: "local-only",
    local: {
      enabled: true,
      channel: "local-app-server",
      origin: "localhost",
    },
    remote: {
      enabled: false,
      channel: "gateway",
      origin: null,
    },
  },
  auth: {
    mode: "trusted_local",
    origin: "local",
    authenticated: true,
    authSource: "local-app-server",
    trustLevel: "trusted",
    actorId: "gui.operator",
    clientType: "gui",
    roles: ["operator"],
    scopes: ["gateway.read"],
  },
  pairing: {
    pendingRequestCount: 1,
    pendingApprovalCount: APPROVALS.filter((item) => item.status === "pending").length,
    source: "approvals.pending_heuristic",
    hasNativeContract: false,
    summary: "derived from pending approval tickets via pairing/device keywords",
    pendingRefs: [
      {
        approvalId: "approval_demo_001",
        traceId: "trace_demo_001",
        title: "Remote device pairing request",
        actionType: "pairing.request",
        requestedAt: "2026-03-28T08:00:00Z",
      },
    ],
  },
  summary: {
    pendingPairingRequestCount: 1,
    pendingApprovalCount: APPROVALS.filter((item) => item.status === "pending").length,
    accessPosture: "local-only",
    authMode: "trusted_local",
    authOrigin: "local",
  },
};

const NODES_INVENTORY_SNAPSHOT: NodesInventorySnapshot = {
  nodes: [
    {
      nodeId: "node.local.app_server",
      deviceId: "local-app-server",
      kind: "local",
      label: "Local App Server",
      status: "online",
      access: {
        enabled: true,
        channel: "local-app-server",
        origin: "localhost",
        posture: "local-only",
      },
      auth: ACCESS_POSTURE_SUMMARY.auth,
      pairing: {
        ...ACCESS_POSTURE_SUMMARY.pairing,
        writeSupported: false,
      },
      activity: {
        eventCount: 1,
        workflowCount: WORKFLOW_RUNS.length,
        approvalCount: APPROVALS.length,
        lastSeenAt: "2026-03-28T08:05:00Z",
      },
      runtime: {
        workspaceTrust: "trusted",
        toolCount: 13,
        mcpServerCount: 1,
        appConnectorCount: 2,
      },
    },
    {
      nodeId: "node.remote.gateway",
      deviceId: "remote-gateway",
      kind: "remote",
      label: "Remote Gateway Client",
      status: "pending_pairing",
      access: {
        enabled: false,
        channel: "gateway",
        origin: null,
        posture: "local-only",
      },
      auth: ACCESS_POSTURE_SUMMARY.auth,
      pairing: {
        ...ACCESS_POSTURE_SUMMARY.pairing,
        writeSupported: false,
      },
      activity: {
        eventCount: 1,
        workflowCount: WORKFLOW_RUNS.length,
        approvalCount: APPROVALS.length,
        lastSeenAt: "2026-03-28T08:05:00Z",
      },
      runtime: {
        workspaceTrust: "trusted",
        toolCount: 13,
        mcpServerCount: 1,
        appConnectorCount: 2,
      },
    },
  ],
  devices: [
    {
      deviceId: "local-app-server",
      nodeId: "node.local.app_server",
      kind: "local",
      status: "online",
      label: "Local App Server",
    },
    {
      deviceId: "remote-gateway",
      nodeId: "node.remote.gateway",
      kind: "remote",
      status: "pending_pairing",
      label: "Remote Gateway Client",
    },
  ],
  accessPosture: ACCESS_POSTURE_SUMMARY,
  pairing: ACCESS_POSTURE_SUMMARY.pairing,
  summary: {
    totalNodes: 2,
    localNodes: 1,
    remoteNodes: 1,
    pendingPairingRequestCount: 1,
    pendingApprovalCount: APPROVALS.filter((item) => item.status === "pending").length,
    recentEvents: 1,
    recentWorkflowRuns: WORKFLOW_RUNS.length,
    recentApprovalTickets: APPROVALS.length,
    mcpServerCount: 1,
    appConnectorCount: 2,
    lastSeenAt: "2026-03-28T08:05:00Z",
    limit: 20,
  },
  capabilities: {
    readOnly: true,
    pairingWriteSupported: false,
    pairingWriteReason: "nodes.list only provides read-only inventory; pairing decisions stay in approval flows.",
  },
  runtimeRegistry: {
    workspaceTrust: "trusted",
    mcpServers: [{ name: "docs", source: "plugin" }],
    appConnectors: CONNECTORS.map((item) => ({ connector_id: item.connector_key, plugin_name: item.plugin_name })),
    toolCount: 13,
    source: "tools.capabilities",
  },
  source: {
    contract: "nodes.list.v1",
    derivedFrom: ["access.posture.get", "runtimeRegistry", "gateway_state_snapshot"],
  },
};

const BROWSER_STATUS: BrowserStatusSummary = {
  running: true,
  activeProfile: "default",
  tabCount: 2,
};

const DEFAULT_BROWSER_TABS = [
  { tab_id: "tab_1", title: "Dashboard", url: "https://example.test/dashboard" },
  { tab_id: "tab_2", title: "Approvals", url: "https://example.test/approvals" },
];

const DEFAULT_BROWSER_REFS: Record<string, Array<{ ref: string; role: string; text: string }>> = {
  tab_1: [
    { ref: "a1", role: "button", text: "Run" },
    { ref: "b2", role: "textbox", text: "Search" },
  ],
  tab_2: [
    { ref: "c3", role: "button", text: "Approve" },
    { ref: "d4", role: "textbox", text: "Comment" },
  ],
};

const DEFAULT_BROWSER_CONSOLE = [
  { level: "info", text: "browser ready" },
  { level: "warning", text: "slow resource" },
];

const MOCK_LOG_SOURCES = [
  {
    key: "gateway.audit_records",
    label: "Gateway Audit Records",
    path: "/home/lyc/project/AgentHub/.config/gateway/audit_records.jsonl",
  },
  {
    key: "gateway.action_requests",
    label: "Gateway Action Requests",
    path: "/home/lyc/project/AgentHub/.config/gateway/action_requests.jsonl",
  },
  {
    key: "gateway.approval_tickets",
    label: "Gateway Approval Tickets",
    path: "/home/lyc/project/AgentHub/.config/gateway/approval_tickets.jsonl",
  },
  {
    key: "gateway.workflow_runs",
    label: "Gateway Workflow Runs",
    path: "/home/lyc/project/AgentHub/.config/gateway/workflow_runs.jsonl",
  },
  {
    key: "gateway.events",
    label: "Gateway Events",
    path: "/home/lyc/project/AgentHub/.config/gateway/events.jsonl",
  },
  {
    key: "thread.active_rollout",
    label: "Active Thread Rollout",
    path: "/home/lyc/project/AgentHub/.config/threads/rollouts/demo-thread.jsonl",
  },
] as const;

const MOCK_LOG_LINES: Record<string, string[]> = {
  "gateway.events": [
    '{"event_id":"evt_demo_001","event_type":"github.issue.opened","source_kind":"github","source_id":"issue_1","connector_key":"github","plugin_name":"github_phase1","occurred_at":"2026-03-28T08:00:00Z","received_at":"2026-03-28T08:00:02Z","trace_id":"trace_demo_001","payload":{"action":"opened"},"metadata":{"causality":{"workflow_run_id":"run_1"}}}',
    '{"event_id":"evt_demo_002","event_type":"browser.session.updated","source_kind":"browser","source_id":"session_1","connector_key":"browser","plugin_name":"browser_phase1","occurred_at":"2026-03-28T08:05:00Z","received_at":"2026-03-28T08:05:03Z","trace_id":"trace_demo_002","payload":{"tab_count":1,"workflow_run_id":"run_2"}}',
  ],
  "gateway.action_requests": [
    '{"action_id":"action_demo_001","action_type":"browser.proxy","trace_id":"trace_demo_001","workflow_run_id":"run_1","requested_at":"2026-03-28T08:01:00Z","requested_by":"operator","summary":"browser proxy action queued"}',
    '{"action_id":"action_demo_002","action_type":"shell_command","trace_id":"trace_demo_002","requested_at":"2026-03-28T08:08:00Z","requested_by":"operator","summary":"shell command action queued"}',
  ],
  "gateway.approval_tickets": [
    '{"approval_id":"approval_demo_001","action_id":"action_demo_001","trace_id":"trace_demo_001","status":"pending","requested_at":"2026-03-28T08:02:00Z","summary":"Approve browser proxy"}',
    '{"approval_id":"approval_demo_002","action_id":"action_demo_002","trace_id":"trace_demo_002","status":"approved","requested_at":"2026-03-28T08:09:00Z","summary":"Approve shell command"}',
  ],
  "gateway.audit_records": [
    '{"audit_id":"audit_demo_001","stage":"action_request","status":"pending","summary":"created action request shell_command"}',
    '{"audit_id":"audit_demo_002","stage":"approval","status":"pending","summary":"Approve shell command"}',
    '{"audit_id":"audit_demo_003","stage":"execution","status":"running","summary":"browser proxy command started"}',
  ],
  "gateway.workflow_runs": [
    '{"workflow_run_id":"run_1","trace_id":"trace_demo_001","workflow_name":"Demo Workflow","plugin_name":"demo-plugin","status":"paused","current_step":"awaiting_approval","summary":"workflow paused for approval"}',
    '{"workflow_run_id":"run_2","trace_id":"trace_demo_002","workflow_name":"Demo Follow-up","plugin_name":"demo-plugin","status":"running","current_step":"execute","summary":"workflow resumed execution"}',
  ],
  "thread.active_rollout": [
    '{"type":"thread_meta","thread_id":"thread_demo_001","timestamp":"2026-03-28T08:00:00Z","trace_id":"trace_demo_001","workflow_run_id":"run_1"}',
    '{"type":"turn","thread_id":"thread_demo_001","timestamp":"2026-03-28T08:05:00Z","trace_id":"trace_demo_001","workflow_run_id":"run_1","user_text":"检查 gateway 状态"}',
    '{"type":"turn","thread_id":"thread_demo_001","timestamp":"2026-03-28T08:05:03Z","trace_id":"trace_demo_001","workflow_run_id":"run_1","assistant_text":"gateway 状态已刷新"}',
  ],
};

const THREADS: ThreadSummary[] = [
  {
    thread_id: "thread_demo_001",
    name: "GitHub 验证",
    updated_at: "刚刚",
    turn_count: 4,
    cwd: "/home/lyc/project/AgentHub",
    last_user_text: "检查最近一次 GitHub Actions run",
    last_assistant_text: "已定位最近一次 run，并准备核对状态。",
  },
  {
    thread_id: "thread_demo_002",
    name: "浏览器快照",
    updated_at: "5 分钟前",
    turn_count: 3,
    cwd: "/home/lyc/project/AgentHub",
    last_user_text: "打开浏览器并刷新页面快照",
    last_assistant_text: "浏览器快照已刷新，可继续查看 refs。",
  },
];

const THREAD_HISTORY: Record<string, ThreadHistoryEntry[]> = {
  thread_demo_001: [
    { role: "user", content: "检查最近一次 GitHub Actions run" },
    { role: "assistant", content: "已定位最近一次 run，并准备核对状态。" },
  ],
  thread_demo_002: [
    { role: "user", content: "打开浏览器并刷新页面快照" },
    { role: "assistant", content: "浏览器快照已刷新，可继续查看 refs。" },
  ],
};

const THREAD_TURNS: Record<string, ThreadTurn[]> = {
  thread_demo_001: [
    {
      timestamp: "2026-03-28T08:00:00Z",
      user_text: THREAD_HISTORY["thread_demo_001"]?.[0]?.content ?? "",
      commentary_text: "我先读取当前线程上下文。",
      assistant_text: THREAD_HISTORY["thread_demo_001"]?.[1]?.content ?? "",
      activity_events: [
        {
          title: "Browser snapshot",
          status: "success",
          detail: "target=tab_1 | url=https://example.test/dashboard | refs=2",
          kind: "browser",
        },
      ],
      tool_events: [
        {
          name: "browser_snapshot",
          ok: true,
          summary: "Browser snapshot",
          payload: { target_id: "tab_1", ref_count: 2 },
        },
      ],
    },
  ],
  thread_demo_002: [],
};

export class MockHostAdapter implements HostAdapter {
  private readonly listeners = new Set<EventListener>();
  private readonly settingsSnapshot: SettingsSnapshot = {
    ...SETTINGS_SNAPSHOT,
    runtimePolicy: SETTINGS_SNAPSHOT.runtimePolicy ? { ...SETTINGS_SNAPSHOT.runtimePolicy } : undefined,
  };
  private activeThreadId = THREADS[0]?.thread_id ?? null;
  private readonly browserStatus: BrowserStatusSummary = { ...BROWSER_STATUS };
  private browserTabs = DEFAULT_BROWSER_TABS.map((item) => ({ ...item }));
  private readonly browserRefs = Object.fromEntries(
    Object.entries(DEFAULT_BROWSER_REFS).map(([tabId, refs]) => [tabId, refs.map((item) => ({ ...item }))]),
  ) as Record<string, Array<{ ref: string; role: string; text: string }>>;
  private browserConsoleEntries = DEFAULT_BROWSER_CONSOLE.map((item) => ({ ...item }));
  private activeBrowserTabId = DEFAULT_BROWSER_TABS[0]?.tab_id ?? "";
  private threadCounter = 3;
  private gatewayEventCursor = 2;

  async getControlUiBootstrap(): Promise<ControlUiBootstrap> {
    return {
      basePath: "/gui",
      assistantName: "AgentHub",
      assistantAvatar: "",
      assistantAgentId: "agenthub",
      serverVersion: "0.1.0",
      providerLabel: "openai | gpt-5.4",
      gateway: {
        methods: [
          "connect.initialize",
          "connect.capabilities",
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
          "gateway.trace.timeline",
          "workflows.list",
          "workflows.get",
          "workflows.resume",
          "approvals.list",
          "approvals.resolve",
          "browser.proxy",
        ],
        streams: ["gateway_events", "workflow_runs", "approvals", "audit"],
      },
    };
  }

  async getControlUiState(limit = 20): Promise<ControlUiStateSnapshot> {
    const safeLimit = Math.max(1, Math.trunc(Number(limit) || 20));
    const approvalTickets = APPROVALS.slice(0, safeLimit);
    return {
      health: {
        status: "ok",
        provider: {
          provider_label: "openai | gpt-5.4",
          provider_model: "gpt-5.4",
        },
      },
      runtimePolicy: {
        approval_policy: "on-request",
        sandbox_mode: "workspace-write",
      },
      approvalStatus: {
        pending_approvals: String(approvalTickets.filter((item) => item.status === "pending").length),
      },
      events: [
        {
          event_id: "evt_demo_1",
          event_type: "demo.event",
          source_kind: "mock",
          trace_id: "trace_demo_001",
        },
      ],
      workflowRuns: WORKFLOW_RUNS.slice(0, safeLimit).map((item) => ({ ...item })),
      actionRequests: ACTION_REQUESTS.slice(0, safeLimit).map((item) => ({ ...item })),
      approvalTickets: approvalTickets.map((item) => ({ ...item })),
      auditRecords: AUDIT_RECORDS.slice(0, safeLimit).map((item) => ({ ...item })),
      diagnostics: {
        access_posture: { ...ACCESS_POSTURE_SUMMARY },
        pairing_summary: { ...ACCESS_POSTURE_SUMMARY.pairing },
        workflow_diagnostics: [
          {
            trace_id: "trace_demo_001",
            workflow_run_id: "run_1",
            workflow_status: "paused",
            status: "paused",
            workflow_name: "handle_github_issue_opened",
            plugin_name: "github_phase1",
            reasoning: {
              status: "approval_requested",
              summary: "workflow recommends issue triage follow-up",
              evidence_refs: [],
            },
            recommendation: {
              count: 1,
              items: [{ action_id: "action_demo_001", action_type: "github.issue.comment" }],
            },
            approval: {
              status: "pending",
              approval_id: "approval_demo_001",
            },
            execution: {
              status: "not_executed",
              summary: "",
              artifact_refs: [],
            },
          },
          {
            trace_id: "trace_demo_002",
            workflow_run_id: "run_2",
            workflow_status: "running",
            status: "running",
            workflow_name: "browser_mutate_after_approval",
            plugin_name: "browser_phase1",
          },
        ],
        approval_diagnostics: approvalTickets.map((item) => ({
          approval_id: item.approval_id,
          status: item.status,
          trace_id: item.trace_id,
        })),
      },
      accessPosture: { ...ACCESS_POSTURE_SUMMARY },
      connectors: CONNECTORS.slice(0, safeLimit).map((item) => ({ ...item })),
    };
  }

  async pollGatewayEvents(cursor = 0, streams?: string[]): Promise<GatewayEventPollResult> {
    const acceptedStreams = new Set((streams ?? []).map((item) => item.trim()).filter(Boolean));
    const nextCursor = this.gatewayEventCursor;
    const events = [
      {
        cursor: 1,
        stream: "approvals",
        event: "approval.updated",
        payload: { approval_id: APPROVALS[0]?.approval_id ?? "approval_demo_001" },
      },
      {
        cursor: 2,
        stream: "gateway_events",
        event: "gateway.event.created",
        payload: { event_id: "evt_demo_1" },
      },
    ].filter((item) => item.cursor > cursor && (!acceptedStreams.size || acceptedStreams.has(item.stream)));
    return {
      cursor: nextCursor,
      events,
    };
  }

  async browserProxy(request: BrowserProxyRequest): Promise<BrowserProxyResponse> {
    const method = String(request.method || "").toUpperCase();
    const path = String(request.path || "/").trim() || "/";
    if (method === "GET" && path === "/profiles") {
      return {
        status: 200,
        result: {
          ok: true,
          profiles: [
            {
              profile: "default",
              active: true,
            },
          ],
        },
      };
    }
    return {
      status: 200,
      result: {
        ok: true,
        method,
        path,
        query: { ...(request.query ?? {}) },
        body: { ...(request.body ?? {}) },
      },
    };
  }

  async request<TData = unknown>(request: BridgeRequest<unknown>): Promise<BridgeResponse<TData>> {
    try {
      const response = await this.handleRequest<TData>(request);
      return response;
    } catch (error) {
      return createBridgeFailure(request, {
        code: `${request.action}.failed`,
        message: error instanceof Error ? error.message : String(error),
        retryable: false,
      });
    }
  }

  subscribe(listener: EventListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private async handleRequest<TData>(
    request: BridgeRequest<unknown>,
  ): Promise<BridgeResponse<TData>> {
    switch (request.action) {
      case "task.run":
        this.appendThreadTurn(
          String((request.payload as { text?: string })?.text ?? "任务"),
          "任务已进入执行流。",
        );
        this.emitTaskLifecycle(request, String((request.payload as { text?: string })?.text ?? "任务"));
        return createBridgeSuccess(request, {
          accepted: true,
          task_id: "task_demo_001",
          thread_id: this.activeThreadId ?? "thread_demo_001",
          assistant_text: "任务已进入执行流。",
          tool_event_count: 2,
        } as TData);
      case "shell.run": {
        const payload = (request.payload as { command?: string; text?: string; cwd?: string } | undefined) ?? {};
        const command = String(payload.command ?? payload.text ?? "").trim();
        const cwd = String(payload.cwd ?? this.settingsSnapshot.workspaceRoot ?? "").trim();
        const stdout = this.mockShellStdout(command, cwd);
        const shellPayload = {
          command,
          cwd,
          stdout,
          stderr: "",
          exit_code: 0,
          returncode: 0,
          duration_ms: 18,
          ok: true,
          status: "ok",
        };
        const threadId = this.appendThreadTurn(command ? `/shell ${command}` : "/shell", "Run shell command.", {
          timestamp: new Date().toISOString(),
          user_text: command ? `/shell ${command}` : "/shell",
          assistant_text: "Run shell command.",
          handled_as_command: true,
          activity_events: [
            {
              title: "Shell command completed",
              status: "ok",
              detail: "shell rc=0",
              kind: "command",
            },
          ],
          tool_events: [
            {
              name: "shell",
              ok: true,
              summary: "shell rc=0",
              payload: shellPayload,
            },
          ],
        });
        this.emitShellLifecycle(request, command, shellPayload);
        return createBridgeSuccess(request, {
          accepted: true,
          approval_required: false,
          command,
          cwd,
          ok: true,
          status: "ok",
          exit_code: 0,
          stdout,
          stderr: "",
          duration_ms: 18,
          thread_id: threadId,
          assistant_text: "Run shell command.",
          user_text: command ? `/shell ${command}` : "/shell",
          tool_events: [
            {
              name: "shell",
              ok: true,
              summary: "shell rc=0",
              payload: shellPayload,
            },
          ],
          activity_events: [
            {
              title: "Shell command completed",
              status: "ok",
              detail: "shell rc=0",
              kind: "command",
            },
          ],
          turn_events: [],
          tool_event_count: 1,
        } as TData);
      }
      case "task.stop":
        this.emit(
          normalizeBridgeEvent({
            request_id: request.request_id,
            kind: "task_failed",
            name: "task_stop",
            summary: "Execution interrupted",
            payload: {
              interrupted: true,
              thread_id: this.activeThreadId ?? "",
            },
          }),
        );
        return createBridgeSuccess(request, {
          accepted: true,
          interrupted: true,
          task_id: (request.payload as { task_id?: string })?.task_id ?? "task_demo_001",
        } as TData);
      case "chat.send":
        this.appendThreadTurn(
          String((request.payload as { text?: string })?.text ?? ""),
          `已收到：${String((request.payload as { text?: string })?.text ?? "")}`,
        );
        this.emit(
          normalizeBridgeEvent({
            request_id: request.request_id,
            kind: "task_progress",
            name: "chat_send",
            summary: "Chat message queued",
            payload: {
              text: (request.payload as { text?: string })?.text ?? "",
              thread_id: this.activeThreadId ?? "",
            },
          }),
        );
        return createBridgeSuccess(request, {
          accepted: true,
          message_id: "msg_demo_001",
          thread_id: this.activeThreadId ?? "thread_demo_001",
          user_text: (request.payload as { text?: string })?.text ?? "",
          assistant_text: `已收到：${(request.payload as { text?: string })?.text ?? ""}`,
        } as TData);
      case "thread.list":
        {
          const cwd = String((request.payload as { cwd?: string })?.cwd ?? "").trim();
          const threads = cwd ? THREADS.filter((item) => String(item.cwd ?? "") === cwd) : THREADS;
          const activeThreadId = threads.some((item) => item.thread_id === this.activeThreadId)
            ? this.activeThreadId
            : threads[0]?.thread_id ?? null;
          return createBridgeSuccess(request, {
            threads,
            active_thread_id: activeThreadId,
          } as TData);
        }
      case "thread.resume": {
        const threadId = String((request.payload as { thread_id?: string })?.thread_id ?? "");
        const thread = THREADS.find((item) => item.thread_id === threadId) ?? THREADS[0];
        this.activeThreadId = thread?.thread_id ?? null;
          return createBridgeSuccess(request, {
            thread,
            history: thread ? (THREAD_HISTORY[thread.thread_id] ?? []) : [],
            turns: thread ? (THREAD_TURNS[thread.thread_id] ?? []) : [],
          state: {},
        } as TData);
      }
      case "connect.initialize":
        return createBridgeSuccess(request, {
          protocolVersion: "v1",
          serverInfo: { name: "agenthub-gateway", version: "0.1.0" },
          accessPosture: { ...ACCESS_POSTURE_SUMMARY },
          methods: MOCK_GATEWAY_METHODS.map((item) => ({ ...item })),
          legacyMethods: ["gateway/dispatch", "browser/proxy"],
        } as TData);
      case "connect.capabilities":
        return createBridgeSuccess(request, {
          accessPosture: { ...ACCESS_POSTURE_SUMMARY },
          methods: MOCK_GATEWAY_METHODS.map((item) => ({ ...item })),
          legacyMethods: ["gateway/dispatch", "browser/proxy"],
          providerLabel: "openai | gpt-5.4",
        } as TData);
      case "connect.ping":
        return createBridgeSuccess(request, {
          ok: true,
          protocolVersion: "v1",
        } as TData);
      case "access.posture.get":
        return createBridgeSuccess(request, { ...ACCESS_POSTURE_SUMMARY } as TData);
      case "nodes.list":
        return createBridgeSuccess(request, { ...NODES_INVENTORY_SNAPSHOT } as TData);
      case "health.get":
        return createBridgeSuccess(request, {
          status: "ok",
          runtime: {
            providerLabel: "openai | gpt-5.4",
            platformFamily: "unix",
            platformOs: "linux",
            shellKind: "bash",
          },
        } as TData);
      case "health.probes":
        return createBridgeSuccess(request, {
          status: "ok",
          probes: {
            runtime: { ok: true },
            gatewayStateStore: {
              ok: true,
              events: 1,
              workflowRuns: 0,
              approvalTickets: APPROVALS.length,
            },
            browserControl: {
              ok: true,
              running: this.browserStatus.running,
              tabCount: this.browserTabs.length,
            },
          },
        } as TData);
      case "logs.tail": {
        const payload = (request.payload as { source?: string; lines?: number } | undefined) ?? {};
        const requestedSource = String(payload.source ?? "").trim();
        const sourceMeta = MOCK_LOG_SOURCES.find((item) => item.key === requestedSource) ?? MOCK_LOG_SOURCES[0];
        const allLines = MOCK_LOG_LINES[sourceMeta.key] ?? [];
        const safeLines = Math.max(1, Math.trunc(Number(payload.lines) || 20));
        const lines = allLines.slice(-safeLines);
        const response: GatewayLogTailSnapshot = {
          source: sourceMeta.key,
          label: sourceMeta.label,
          path: sourceMeta.path,
          lines,
          text: lines.join("\n"),
          lineCount: lines.length,
          truncated: allLines.length > lines.length,
          availableSources: MOCK_LOG_SOURCES.map((item) => ({ ...item })),
        };
        return createBridgeSuccess(request, response as TData);
      }
      case "workflows.list": {
        const payload = (request.payload as { status?: string; traceId?: string; pluginName?: string } | undefined) ?? {};
        const status = String(payload.status ?? "").trim().toLowerCase();
        const traceId = String(payload.traceId ?? "").trim();
        const pluginName = String(payload.pluginName ?? "").trim();
        const workflowRuns = WORKFLOW_RUNS.filter((item) => {
          if (status && String(item.status ?? "").trim().toLowerCase() !== status) {
            return false;
          }
          if (traceId && String(item.trace_id ?? "").trim() !== traceId) {
            return false;
          }
          if (pluginName && String(item.plugin_name ?? "").trim() !== pluginName) {
            return false;
          }
          return true;
        });
        const runIds = new Set(workflowRuns.map((item) => String(item.workflow_run_id ?? "")));
        return createBridgeSuccess(request, {
          workflowRuns,
          workflowDiagnostics: (await this.getControlUiState(20)).diagnostics.workflow_diagnostics.filter((item) =>
            runIds.has(String((item as Record<string, unknown>).workflow_run_id ?? ""))
          ),
          counts: {
            workflowRuns: workflowRuns.length,
            running: workflowRuns.filter((item) => item.status === "running").length,
            paused: workflowRuns.filter((item) => item.status === "paused").length,
          },
        } as TData);
      }
      case "workflows.get": {
        const workflowRunId = String((request.payload as { workflowRunId?: string })?.workflowRunId ?? "");
        const workflowRun = WORKFLOW_RUNS.find((item) => item.workflow_run_id === workflowRunId);
        if (!workflowRun) {
          return createBridgeFailure(request, {
            code: "workflows.get.failed",
            message: `unknown workflow run: ${workflowRunId}`,
            retryable: false,
          }) as BridgeResponse<TData>;
        }
        const traceId = String(workflowRun.trace_id ?? "");
        const actionRequests = ACTION_REQUESTS.filter((item) => item.workflow_run_id === workflowRunId);
        const approvalTickets = APPROVALS.filter((item) => item.trace_id === traceId);
        const auditRecords = AUDIT_RECORDS.filter((item) => item.trace_id === traceId);
        const diagnostics = (await this.getControlUiState(20)).diagnostics;
        return createBridgeSuccess(request, {
          workflowRun: { ...workflowRun },
          workflowDiagnostic: (diagnostics.workflow_diagnostics as Array<Record<string, unknown>>).find(
            (item) => String(item.workflow_run_id ?? "") === workflowRunId,
          ) ?? null,
          approvalDiagnostics: (diagnostics.approval_diagnostics as Array<Record<string, unknown>>).filter(
            (item) => String(item.trace_id ?? "") === traceId,
          ),
          events: [
            {
              event_id: "evt_demo_1",
              event_type: "demo.event",
              source_kind: "mock",
              trace_id: traceId,
            },
          ],
          actionRequests,
          approvalTickets,
          auditRecords,
          traceId,
          timeline: [
            { kind: "events", item: { event_id: "evt_demo_1", event_type: "demo.event", trace_id: traceId } },
            { kind: "workflowRuns", item: { ...workflowRun } },
            ...actionRequests.map((item) => ({ kind: "actionRequests", item: { ...item } })),
            ...approvalTickets.map((item) => ({ kind: "approvalTickets", item: { ...item } })),
            ...auditRecords.map((item) => ({ kind: "auditRecords", item: { ...item } })),
          ],
          resumeEligible: workflowRun.status === "paused",
        } as TData);
      }
      case "workflows.resume": {
        const workflowRunId = String((request.payload as { workflowRunId?: string })?.workflowRunId ?? "");
        const workflowRun = WORKFLOW_RUNS.find((item) => item.workflow_run_id === workflowRunId);
        if (!workflowRun) {
          return createBridgeFailure(request, {
            code: "workflows.resume.failed",
            message: `unknown workflow run: ${workflowRunId}`,
            retryable: false,
          }) as BridgeResponse<TData>;
        }
        workflowRun.status = "running";
        workflowRun.current_step = "manual_resume_requested";
        workflowRun.result_summary = `resume requested by ${String((request.payload as { decidedBy?: string })?.decidedBy ?? "operator")}`;
        workflowRun.updated_at = "2026-03-28T08:07:00Z";
        AUDIT_RECORDS.push({
          trace_id: String(workflowRun.trace_id ?? ""),
          workflow_run_id: workflowRunId,
          stage: "workflow_resume",
          status: "requested",
          summary: `operator requested resume for ${workflowRunId}`,
        });
        return this.handleRequest<TData>({
          ...request,
          action: "workflows.get",
          payload: { workflowRunId },
        });
      }
      case "browser.status":
        this.browserStatus.tabCount = this.browserTabs.length;
        return createBridgeSuccess(request, {
          ...this.browserStatus,
          activeTab: this.activeBrowserTabId,
        } as TData);
      case "browser.tabs":
        return createBridgeSuccess(request, {
          tabs: this.browserTabs,
        } as TData);
      case "browser.snapshot": {
        const targetId = String((request.payload as { target_id?: string })?.target_id ?? this.activeBrowserTabId);
        const tab = this.browserTabs.find((item) => item.tab_id === targetId) ?? this.browserTabs[0];
        const refs = this.browserRefs[targetId] ?? [];
        this.emit(
          normalizeBridgeEvent({
            request_id: request.request_id,
            kind: "tool_event",
            name: "browser_snapshot",
            summary: "Browser snapshot",
            payload: {
              refs: refs.map((item) => item.ref),
              target_id: targetId,
            },
          }),
        );
        return createBridgeSuccess(request, {
          target_id: tab?.tab_id ?? targetId,
          title: tab?.title ?? "Demo page",
          refs,
        } as TData);
      }
      case "browser.console":
        return createBridgeSuccess(request, {
          entries: this.browserConsoleEntries,
        } as TData);
      case "browser.start":
        this.browserStatus.running = true;
        this.pushBrowserConsole("info", "Browser started");
        this.emitBrowserStateChanged(request, { action: request.action, running: true });
        return createBridgeSuccess(request, { accepted: true, running: true } as TData);
      case "browser.stop":
        this.browserStatus.running = false;
        this.pushBrowserConsole("info", "Browser stopped");
        this.emitBrowserStateChanged(request, { action: request.action, running: false });
        return createBridgeSuccess(request, { accepted: true, running: false } as TData);
      case "browser.open": {
        const url = String((request.payload as { url?: string })?.url ?? "https://example.test/new");
        const tabId = `tab_${this.browserTabs.length + 1}`;
        const title = this.deriveTabTitle(url);
        this.browserTabs = [...this.browserTabs, { tab_id: tabId, title, url }];
        this.browserRefs[tabId] = [
          { ref: "a1", role: "button", text: "Submit" },
          { ref: "b2", role: "textbox", text: "Search" },
        ];
        this.activeBrowserTabId = tabId;
        this.browserStatus.tabCount = this.browserTabs.length;
        this.pushBrowserConsole("info", `Opened ${url}`);
        this.emitBrowserStateChanged(request, { action: request.action, target_id: tabId, url });
        return createBridgeSuccess(request, {
          accepted: true,
          target_id: tabId,
          title,
          url,
        } as TData);
      }
      case "browser.focus": {
        const targetId = String((request.payload as { target_id?: string })?.target_id ?? "");
        if (targetId) {
          this.activeBrowserTabId = targetId;
        }
        this.emitBrowserStateChanged(request, { action: request.action, target_id: this.activeBrowserTabId });
        return createBridgeSuccess(request, {
          accepted: true,
          target_id: this.activeBrowserTabId,
        } as TData);
      }
      case "browser.close": {
        const targetId = String((request.payload as { target_id?: string })?.target_id ?? "");
        this.browserTabs = this.browserTabs.filter((item) => item.tab_id !== targetId);
        delete this.browserRefs[targetId];
        this.activeBrowserTabId = this.browserTabs[0]?.tab_id ?? "";
        this.browserStatus.tabCount = this.browserTabs.length;
        this.pushBrowserConsole("info", `Closed ${targetId}`);
        this.emitBrowserStateChanged(request, { action: request.action, target_id: targetId });
        return createBridgeSuccess(request, {
          accepted: true,
          target_id: targetId,
        } as TData);
      }
      case "browser.navigate": {
        const payload = request.payload as { url?: string; tab_id?: string };
        const targetId = String(payload.tab_id ?? this.activeBrowserTabId);
        const url = String(payload.url ?? "");
        const tab = this.browserTabs.find((item) => item.tab_id === targetId);
        if (tab) {
          tab.url = url;
          tab.title = this.deriveTabTitle(url);
          this.activeBrowserTabId = targetId;
        }
        this.pushBrowserConsole("info", `Navigated ${targetId} to ${url}`);
        this.emitBrowserStateChanged(request, { action: request.action, target_id: targetId, url });
        return createBridgeSuccess(request, {
          accepted: true,
          target_id: targetId,
          url,
          title: tab?.title ?? url,
        } as TData);
      }
      case "browser.screenshot":
      case "browser.pdf": {
        const targetId = String((request.payload as { target_id?: string })?.target_id ?? this.activeBrowserTabId);
        const kind = request.action === "browser.pdf" ? "pdf" : "screenshot";
        const extension = kind === "pdf" ? "pdf" : "png";
        const artifactPath = `/tmp/${targetId || "tab"}_${kind}.${extension}`;
        this.emitBrowserStateChanged(request, { action: request.action, target_id: targetId, path: artifactPath });
        return createBridgeSuccess(request, {
          accepted: true,
          artifact: {
            kind,
            path: artifactPath,
            target_id: targetId,
          },
        } as TData);
      }
      case "browser.download":
      case "browser.wait_download": {
        const payload = request.payload as { target_id?: string; ref?: string; path?: string };
        const targetId = String(payload.target_id ?? this.activeBrowserTabId);
        const kind = request.action === "browser.wait_download" ? "download" : "download";
        const artifactPath = String(payload.path ?? `/tmp/${targetId || "tab"}_download.txt`);
        this.pushBrowserConsole("info", `Download ready at ${artifactPath}`);
        this.emitBrowserStateChanged(request, {
          action: request.action,
          target_id: targetId,
          ref: payload.ref ?? "",
          path: artifactPath,
        });
        return createBridgeSuccess(request, {
          accepted: true,
          artifact: {
            kind,
            path: artifactPath,
            target_id: targetId,
            ref: payload.ref ?? null,
          },
        } as TData);
      }
      case "browser.upload": {
        const payload = request.payload as { target_id?: string; ref?: string; input_ref?: string; paths?: string[] };
        const targetId = String(payload.target_id ?? this.activeBrowserTabId);
        const paths = Array.isArray(payload.paths) ? payload.paths : [];
        const summary = `Uploaded ${paths.length} file(s) to ${payload.input_ref ?? payload.ref ?? "input"}`;
        this.pushBrowserConsole("info", summary);
        this.emitBrowserStateChanged(request, {
          action: request.action,
          target_id: targetId,
          ref: payload.ref ?? "",
          input_ref: payload.input_ref ?? "",
          paths,
        });
        return createBridgeSuccess(request, {
          accepted: true,
          target_id: targetId,
          paths,
          message: summary,
        } as TData);
      }
      case "browser.dialog": {
        const payload = request.payload as { target_id?: string; accept?: boolean; prompt_text?: string };
        const targetId = String(payload.target_id ?? this.activeBrowserTabId);
        const summary = `${payload.accept === false ? "Dismissed" : "Accepted"} dialog`;
        this.pushBrowserConsole("info", summary);
        this.emitBrowserStateChanged(request, {
          action: request.action,
          target_id: targetId,
          accept: payload.accept ?? true,
          prompt_text: payload.prompt_text ?? "",
        });
        return createBridgeSuccess(request, {
          accepted: true,
          target_id: targetId,
          message: summary,
        } as TData);
      }
      case "browser.act": {
        const payload = request.payload as {
          action?: string;
          ref?: string;
          value?: string;
          fields?: Array<{ ref?: string; value?: string }>;
          time_ms?: number;
          target_id?: string;
          width?: number;
          height?: number;
          start_ref?: string;
          end_ref?: string;
          values?: string[];
        };
        const kind = String(payload.action ?? "click");
        const targetId = String(payload.target_id ?? this.activeBrowserTabId);
        const summary = this.browserActionSummary(kind, payload);
        this.pushBrowserConsole("info", summary);
        this.emitBrowserStateChanged(request, { action: request.action, kind, target_id: targetId, ref: payload.ref ?? "" });
        return createBridgeSuccess(request, {
          accepted: true,
          kind,
          target_id: targetId,
          message: summary,
          result: {
            ref: payload.ref ?? "",
            value: payload.value ?? "",
            time_ms: payload.time_ms ?? 0,
            width: payload.width ?? 0,
            height: payload.height ?? 0,
            start_ref: payload.start_ref ?? "",
            end_ref: payload.end_ref ?? "",
            values: payload.values ?? [],
            fields: payload.fields ?? [],
          },
        } as TData);
      }
      case "approval.list":
        return createBridgeSuccess(request, {
          approvals: APPROVALS.filter((item) => {
            const status = String((request.payload as { status?: string })?.status ?? "pending");
            return status ? item.status === status : true;
          }),
        } as TData);
      case "approval.resolve": {
        const payload = request.payload as { approval_id?: string; decision?: "approved" | "rejected" };
        const approval = APPROVALS.find((item) => item.approval_id === payload.approval_id);
        if (approval) {
          approval.status = payload.decision ?? "approved";
          AUDIT_RECORDS.unshift({
            trace_id: approval.trace_id,
            stage: "approval",
            status: approval.status,
            summary: `${approval.title} ${approval.status === "approved" ? "approved" : "rejected"}`,
            approval_id: approval.approval_id,
            action_id: approval.action_id ?? null,
          });
        }
        this.emit(
          normalizeBridgeEvent({
            request_id: request.request_id,
            kind: "approval_resolved",
            name: "approval_resolved",
            summary: "Approval resolved",
            payload: {
              ...(request.payload as Record<string, unknown>),
              trace_id: approval?.trace_id ?? "",
              status: approval?.status ?? payload.decision ?? "approved",
            },
          }),
        );
        return createBridgeSuccess(request, {
          accepted: true,
          approval_id: approval?.approval_id ?? payload.approval_id ?? "",
          status: approval?.status ?? payload.decision ?? "approved",
        } as TData);
      }
      case "audit.list":
        return createBridgeSuccess(request, {
          records: AUDIT_RECORDS.filter((item) => {
            const traceId = String((request.payload as { trace_id?: string })?.trace_id ?? "");
            return traceId ? item.trace_id === traceId : true;
          }),
        } as TData);
      case "plugin.list":
        return createBridgeSuccess(request, { plugins: PLUGINS } as TData);
      case "connector.list":
        return createBridgeSuccess(request, { connectors: CONNECTORS } as TData);
      case "plugin.enable":
      case "plugin.disable":
      case "plugin.reload": {
        const payload = request.payload as { plugin_id?: string };
        if (request.action !== "plugin.reload") {
          const plugin = PLUGINS.find((item) => item.plugin_id === payload.plugin_id);
          if (plugin) {
            plugin.enabled = request.action === "plugin.enable";
            plugin.health = plugin.enabled ? "ready" : "warning";
          }
        }
        this.emit(
          normalizeBridgeEvent({
            request_id: request.request_id,
            kind: "plugin_state_changed",
            name: request.action.replace(".", "_"),
            summary: `Plugin action ${request.action}`,
            payload: request.payload as Record<string, unknown>,
          }),
        );
        const plugin = PLUGINS.find((item) => item.plugin_id === payload.plugin_id);
        return createBridgeSuccess(request, {
          accepted: true,
          plugin: plugin ?? null,
          plugins: PLUGINS,
        } as TData);
      }
      case "settings.get":
        return createBridgeSuccess(request, {
          ...this.settingsSnapshot,
          runtimePolicy: this.settingsSnapshot.runtimePolicy ? { ...this.settingsSnapshot.runtimePolicy } : undefined,
        } as TData);
      case "config.validate": {
        const payload = (request.payload as Record<string, unknown>) ?? {};
        const changedFields: string[] = [];
        const applyableFields: string[] = [];
        const blocked: Array<{ field: string; code: string; reason: string }> = [];
        const applyPath: Array<{ field: string; handler: string }> = [];
        const restartReasons: string[] = [];
        const runtimePolicy = typeof payload.runtimePolicy === "object" && payload.runtimePolicy
          ? (payload.runtimePolicy as Record<string, unknown>)
          : {};
        if ("model" in payload && String(payload.model ?? "") !== String(this.settingsSnapshot.model ?? "")) {
          changedFields.push("model");
          blocked.push({
            field: "model",
            code: "unsupported",
            reason: "provider/model 变更尚未接入真实 config.apply contract。",
          });
        }
        if ("workspaceRoot" in payload && String(payload.workspaceRoot ?? "") !== String(this.settingsSnapshot.workspaceRoot ?? "")) {
          changedFields.push("workspaceRoot");
          const workspaceRoot = String(payload.workspaceRoot ?? "").trim();
          if (!workspaceRoot) {
            blocked.push({ field: "workspaceRoot", code: "required", reason: "workspaceRoot 不能为空。" });
          } else {
            applyableFields.push("workspaceRoot");
            applyPath.push({ field: "workspaceRoot", handler: "runtime.set_cwd" });
          }
        }
        for (const field of ["browserHeadless", "pluginAutoLoad"] as const) {
          if (field in payload && Boolean(payload[field]) !== Boolean(this.settingsSnapshot[field])) {
            changedFields.push(field);
            applyableFields.push(field);
            applyPath.push({ field, handler: "gui.runtime_flags" });
            restartReasons.push(`${field} 变更`);
          }
        }
        for (const field of ["approval_policy", "sandbox_mode", "web_search_mode", "network_access"] as const) {
          if (field in runtimePolicy) {
            const next = String(runtimePolicy[field] ?? "");
            const current = String((this.settingsSnapshot.runtimePolicy as Record<string, unknown> | undefined)?.[field] ?? "");
            if (next !== current) {
              changedFields.push(field);
              applyableFields.push(field);
              applyPath.push({ field, handler: "runtime.configure_runtime_policy" });
            }
          }
        }
        return createBridgeSuccess(request, {
          changedFields,
          applyableFields,
          blocked,
          blockedFields: blocked.map((item) => item.field),
          warnings: blocked.map((item) => item.reason),
          applyPath,
          restart: {
            required: restartReasons.length > 0,
            reasons: restartReasons,
            allowed: false,
            mode: "manual",
            blockedReason: restartReasons.length
              ? "runtime restart 仍需 operator 在相关运行面手动执行；当前 contract 只返回 restart report。"
              : null,
          },
        } as TData);
      }
      case "config.apply": {
        const validation = await this.handleRequest<{
          changedFields: string[];
          applyableFields: string[];
          blocked: Array<{ field: string; code: string; reason: string }>;
          blockedFields: string[];
          warnings: string[];
          applyPath: Array<{ field: string; handler: string }>;
          restart: {
            required: boolean;
            reasons: string[];
            allowed: boolean;
            mode: string;
            blockedReason?: string | null;
          };
        }>({
          ...request,
          action: "config.validate",
        });
        const validationData = validation.data!;
        const payload = (request.payload as Record<string, unknown>) ?? {};
        const runtimePolicy = typeof payload.runtimePolicy === "object" && payload.runtimePolicy
          ? (payload.runtimePolicy as Record<string, unknown>)
          : {};
        if (validationData.applyableFields.includes("workspaceRoot")) {
          this.settingsSnapshot.workspaceRoot = String(payload.workspaceRoot ?? this.settingsSnapshot.workspaceRoot);
        }
        if (validationData.applyableFields.includes("browserHeadless")) {
          this.settingsSnapshot.browserHeadless = Boolean(payload.browserHeadless);
        }
        if (validationData.applyableFields.includes("pluginAutoLoad")) {
          this.settingsSnapshot.pluginAutoLoad = Boolean(payload.pluginAutoLoad);
        }
        if (Object.keys(runtimePolicy).length > 0) {
          this.settingsSnapshot.runtimePolicy = {
            ...(this.settingsSnapshot.runtimePolicy ?? {}),
            ...runtimePolicy,
          };
        }
        return createBridgeSuccess(request, {
          applied: validationData.applyableFields.length > 0,
          status: validationData.applyableFields.length && validationData.blockedFields.length
            ? "partial"
            : validationData.applyableFields.length
              ? "applied"
              : "blocked",
          appliedFields: validationData.applyableFields,
          blockedFields: validationData.blockedFields,
          validation: validationData,
          restart: validationData.restart,
          settings: {
            ...this.settingsSnapshot,
            runtimePolicy: this.settingsSnapshot.runtimePolicy ? { ...this.settingsSnapshot.runtimePolicy } : undefined,
          },
        } as TData);
      }
      case "config.restart.report": {
        const validation = await this.handleRequest<{
          restart: {
            required: boolean;
            reasons: string[];
            allowed: boolean;
            mode: string;
            blockedReason?: string | null;
          };
        }>({
          ...request,
          action: "config.validate",
        });
        return createBridgeSuccess(request, validation.data?.restart as TData);
      }
      case "settings.update":
        Object.assign(this.settingsSnapshot, request.payload as Record<string, unknown>);
        this.emit(
          normalizeBridgeEvent({
            request_id: request.request_id,
            kind: "settings_changed",
            name: "settings_changed",
            summary: "Settings updated",
            payload: request.payload as Record<string, unknown>,
          }),
        );
        return createBridgeSuccess(request, {
          ...this.settingsSnapshot,
          runtimePolicy: this.settingsSnapshot.runtimePolicy ? { ...this.settingsSnapshot.runtimePolicy } : undefined,
        } as TData);
      default:
        return createBridgeFailure(request, {
          code: `${request.action satisfies BridgeAction}.unsupported`,
          message: `unsupported action: ${request.action}`,
          retryable: false,
        }) as BridgeResponse<TData>;
    }
  }

  private emitTaskLifecycle(request: BridgeRequest<unknown>, text: string) {
    this.emit(
      normalizeBridgeEvent({
        request_id: request.request_id,
        kind: "task_started",
        name: "task_run",
        summary: "Task started",
        payload: { text, thread_id: this.activeThreadId ?? "" },
      }),
    );
    this.emit(
      normalizeBridgeEvent({
        request_id: request.request_id,
        kind: "task_progress",
        name: "tool_event",
        summary: "Planning and tool selection",
        payload: { phase: "planning", thread_id: this.activeThreadId ?? "" },
      }),
    );
    this.emit(
      normalizeBridgeEvent({
        request_id: request.request_id,
        kind: "task_completed",
        name: "task_run",
        summary: "Task completed",
        payload: { result: "accepted", thread_id: this.activeThreadId ?? "" },
      }),
    );
  }

  private emitShellLifecycle(
    request: BridgeRequest<unknown>,
    command: string,
    payload: Record<string, unknown>,
  ) {
    this.emit(
      normalizeBridgeEvent({
        request_id: request.request_id,
        kind: "task_started",
        name: "shell_run",
        summary: "Shell command started",
        payload: { command, thread_id: this.activeThreadId ?? "" },
      }),
    );
    this.emit(
      normalizeBridgeEvent({
        request_id: request.request_id,
        kind: "tool_event",
        name: "shell",
        summary: "shell rc=0",
        payload,
      }),
    );
    this.emit(
      normalizeBridgeEvent({
        request_id: request.request_id,
        kind: "task_completed",
        name: "shell_run",
        summary: "Shell command completed",
        payload: { ...payload, thread_id: this.activeThreadId ?? "" },
      }),
    );
  }

  private appendThreadTurn(userText: string, assistantText: string, turn?: ThreadTurn): string {
    const normalizedUser = String(userText).trim();
    const normalizedAssistant = String(assistantText).trim();
    if (!this.activeThreadId) {
      const threadId = `thread_demo_${String(this.threadCounter).padStart(3, "0")}`;
      this.threadCounter += 1;
      THREADS.unshift({
        thread_id: threadId,
        name: normalizedUser.slice(0, 18) || "新任务",
        updated_at: "刚刚",
        turn_count: 0,
        last_user_text: "",
        last_assistant_text: "",
      });
      THREAD_HISTORY[threadId] = [];
      THREAD_TURNS[threadId] = [];
      this.activeThreadId = threadId;
    }
    const threadId = this.activeThreadId ?? "";
    if (!threadId) {
      return "";
    }
    const history = THREAD_HISTORY[threadId] ?? [];
    if (normalizedUser) {
      history.push({ role: "user", content: normalizedUser });
    }
    if (normalizedAssistant) {
      history.push({ role: "assistant", content: normalizedAssistant });
    }
    THREAD_HISTORY[threadId] = history;
    if (turn) {
      const turns = THREAD_TURNS[threadId] ?? [];
      turns.push(turn);
      THREAD_TURNS[threadId] = turns;
    }
    const thread = THREADS.find((item) => item.thread_id === threadId);
    if (thread) {
      thread.updated_at = "刚刚";
      thread.turn_count = Math.max(history.length, THREAD_TURNS[threadId]?.length ?? 0);
      thread.last_user_text = normalizedUser || thread.last_user_text;
      thread.last_assistant_text = normalizedAssistant || thread.last_assistant_text;
      if (!thread.name || thread.name.startsWith("thread_")) {
        thread.name = (normalizedUser || "新任务").slice(0, 18);
      }
    }
    return threadId;
  }

  private mockShellStdout(command: string, cwd: string): string {
    const normalized = command.trim();
    if (normalized === "pwd") {
      return cwd || this.settingsSnapshot.workspaceRoot || "/home/lyc/project/AgentHub";
    }
    if (normalized === "git status --short") {
      return " M gui/src/features/workbench/warp-workbench-page.ts";
    }
    if (normalized.startsWith("rg ")) {
      return "gui/src/features/workbench/warp-workbench-page.ts:1808: shell.run";
    }
    return `mock shell output: ${normalized || "command"}`;
  }

  private emitBrowserStateChanged(request: BridgeRequest<unknown>, payload: Record<string, unknown>) {
    this.emit(
      normalizeBridgeEvent({
        request_id: request.request_id,
        kind: "browser_state_changed",
        name: request.action.replace(".", "_"),
        summary: `Handled ${request.action}`,
        payload,
      }),
    );
  }

  private deriveTabTitle(url: string): string {
    try {
      const parsed = new URL(url);
      const token = parsed.pathname.split("/").filter(Boolean).pop() ?? parsed.hostname;
      return token.charAt(0).toUpperCase() + token.slice(1);
    } catch {
      return url || "New Tab";
    }
  }

  private pushBrowserConsole(level: string, text: string) {
    this.browserConsoleEntries = [{ level, text }, ...this.browserConsoleEntries].slice(0, 8);
  }

  private browserActionSummary(
    kind: string,
    payload: {
      ref?: string;
      value?: string;
      key?: string;
      time_ms?: number;
      width?: number;
      height?: number;
      start_ref?: string;
      end_ref?: string;
      values?: string[];
      fields?: Array<{ ref?: string; value?: string }>;
    },
  ): string {
    if (kind === "type") {
      return `Typed into ${payload.ref ?? "ref"}: ${payload.value ?? ""}`.trim();
    }
    if (kind === "press") {
      return `Pressed ${payload.key ?? payload.value ?? "key"}`;
    }
    if (kind === "fill") {
      const count = payload.fields?.length ?? 0;
      return `Filled ${count} field(s)`;
    }
    if (kind === "wait") {
      return `Waited for ${payload.time_ms ?? 0}ms`;
    }
    if (kind === "drag") {
      return `Dragged ${payload.start_ref ?? payload.ref ?? "source"} to ${payload.end_ref ?? "target"}`;
    }
    if (kind === "resize") {
      return `Resized viewport to ${payload.width ?? 0}x${payload.height ?? 0}`;
    }
    if (kind === "scroll_into_view") {
      return `Scrolled ${payload.ref ?? "ref"} into view`;
    }
    if (kind === "select") {
      return `Selected ${(payload.values ?? []).join(", ") || "-"} on ${payload.ref ?? "ref"}`;
    }
    if (kind === "check") {
      return `Checked ${payload.ref ?? "ref"}`;
    }
    if (kind === "uncheck") {
      return `Unchecked ${payload.ref ?? "ref"}`;
    }
    if (kind === "focus") {
      return `Focused ${payload.ref ?? "ref"}`;
    }
    return `${kind} on ${payload.ref ?? "selected ref"}`;
  }

  private emit(event: BridgeEvent<Record<string, unknown>>) {
    for (const listener of this.listeners) {
      listener(event);
    }
  }
}
