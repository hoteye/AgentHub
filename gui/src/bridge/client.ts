import {
  HttpHostAdapter,
  resolveBridgeTransportConfig,
  type BridgeTransportConfig,
} from "../shared/api/http-host.ts";
import { MockHostAdapter, type HostAdapter } from "../shared/api/mock-host.ts";
import {
  createBridgeFailure,
  createBridgeRequest,
  createBridgeSuccess,
  toBridgeError,
  type AccessPostureSummary,
  type ApprovalSummary,
  type BrowserProxyRequest,
  type BrowserProxyResponse,
  type BrowserStatusSummary,
  type BridgeClientIdentity,
  type BridgeEvent,
  type BridgeResponse,
  type ConfigApplyResult,
  type ConfigRestartReport,
  type ConfigValidationResult,
  type ControlUiBootstrap,
  type ControlUiStateSnapshot,
  type ConnectorSummary,
  type GatewayEventPollResult,
  type GatewayLogTailSnapshot,
  type GatewayMethodMetadata,
  type PluginSummary,
  type SettingsSnapshot,
  type ShellRunPayload,
  type ShellRunResult,
  type NodesInventorySnapshot,
  type StoredActivityEvent,
  type StoredToolEvent,
  type ThreadTurn,
  type ThreadHistoryEntry,
  type ThreadSummary,
} from "../shared/types/bridge.ts";

type EventListener = (event: BridgeEvent<Record<string, unknown>>) => void;

export class BridgeClient {
  constructor(
    private readonly adapter: HostAdapter = new MockHostAdapter(),
    private readonly clientIdentity?: BridgeClientIdentity,
  ) {}

  readonly task = {
    run: (payload: { text: string }) =>
      this.request<{ accepted: boolean; task_id?: string; thread_id?: string; assistant_text?: string; tool_event_count?: number }>("task.run", payload),
    stop: (payload: { task_id?: string } = {}) =>
      this.request<{ accepted: boolean; task_id?: string; interrupted?: boolean }>("task.stop", payload),
  };

  readonly shell = {
    run: (payload: ShellRunPayload) => this.request<ShellRunResult>("shell.run", payload),
  };

  readonly chat = {
    send: (payload: {
      text: string;
      thread_id?: string;
      cwd?: string;
      workspaceRoots?: string[];
      new_thread?: boolean;
    }) =>
      this.request<{
        accepted: boolean;
        message_id?: string;
        thread_id?: string;
        assistant_text?: string;
        user_text?: string;
        cwd?: string;
        workspaceRoots?: string[];
      }>("chat.send", payload),
  };

  readonly thread = {
    list: (payload: { limit?: number; cwd?: string } = {}) =>
      this.request<{ threads: ThreadSummary[]; active_thread_id?: string | null }>("thread.list", payload),
    resume: (payload: { thread_id: string }) =>
      this.request<{
        thread: ThreadSummary;
        history: ThreadHistoryEntry[];
        turns?: ThreadTurn[];
        state?: Record<string, unknown>;
      }>("thread.resume", payload),
  };

  readonly controlUi = {
    bootstrap: () =>
      this.adapterCall<ControlUiBootstrap, "control_ui.bootstrap">(
        "control_ui.bootstrap",
        {},
        () => this.adapter.getControlUiBootstrap(),
      ),
    state: (payload: { limit?: number } = {}) =>
      this.adapterCall<ControlUiStateSnapshot, "control_ui.state">(
        "control_ui.state",
        payload,
        () => this.adapter.getControlUiState(payload.limit),
      ),
  };

  readonly gateway = {
    connect: {
      initialize: () =>
        this.request<{
          protocolVersion: string;
          serverInfo: { name: string; version: string };
          accessPosture?: AccessPostureSummary;
          methods: GatewayMethodMetadata[];
          legacyMethods: string[];
        }>("connect.initialize", {}),
      capabilities: () =>
        this.request<{
          accessPosture?: AccessPostureSummary;
          methods: GatewayMethodMetadata[];
          legacyMethods: string[];
          providerLabel?: string;
        }>("connect.capabilities", {}),
      ping: () => this.request<{ ok: boolean; protocolVersion: string }>("connect.ping", {}),
    },
    access: {
      posture: () => this.request<AccessPostureSummary>("access.posture.get", {}),
    },
    nodes: {
      list: () => this.request<NodesInventorySnapshot>("nodes.list", {}),
    },
    health: {
      get: () => this.request<Record<string, unknown>>("health.get", {}),
      probes: () => this.request<Record<string, unknown>>("health.probes", {}),
    },
    logs: {
      tail: (payload: { source?: string; lines?: number } = {}) =>
        this.request<GatewayLogTailSnapshot>("logs.tail", payload),
    },
    state: {
      get: (payload: { limit?: number } = {}) =>
        this.request<Record<string, unknown>>("gateway.state.get", payload),
      events: (payload: { limit?: number } = {}) =>
        this.request<Record<string, unknown>>("gateway.events.list", payload),
      workflows: (payload: { limit?: number } = {}) =>
        this.request<Record<string, unknown>>("gateway.workflows.list", payload),
      traceTimeline: (payload: { traceId: string }) =>
        this.request<Record<string, unknown>>("gateway.trace.timeline", payload),
    },
    workflows: {
      list: (payload: { limit?: number; status?: string; pluginName?: string; traceId?: string } = {}) =>
        this.request<Record<string, unknown>>("workflows.list", payload),
      get: (payload: { workflowRunId: string }) =>
        this.request<Record<string, unknown>>("workflows.get", payload),
      resume: (payload: { workflowRunId: string; decidedBy?: string; note?: string } ) =>
        this.request<Record<string, unknown>>("workflows.resume", payload),
    },
    events: {
      poll: (payload: { cursor?: number; streams?: string[] } = {}) =>
        this.adapterCall<GatewayEventPollResult, "gateway.events.poll">(
          "gateway.events.poll",
          payload,
          () => this.adapter.pollGatewayEvents(payload.cursor, payload.streams),
        ),
    },
  };

  readonly browser = {
    proxy: (payload: BrowserProxyRequest) =>
      this.adapterCall<BrowserProxyResponse, "browser.proxy">(
        "browser.proxy",
        payload,
        () => this.adapter.browserProxy(payload),
      ),
    status: () => this.request<BrowserStatusSummary>("browser.status", {}),
    start: (payload: { profile?: string }) => this.request("browser.start", payload),
    stop: (payload: { profile?: string } = {}) => this.request("browser.stop", payload),
    tabs: () => this.request<{ tabs: Array<{ tab_id: string; title: string; url: string }> }>("browser.tabs", {}),
    open: (payload: { url: string }) => this.request("browser.open", payload),
    focus: (payload: { target_id: string }) => this.request("browser.focus", payload),
    close: (payload: { target_id: string }) => this.request("browser.close", payload),
    navigate: (payload: { tab_id: string; url: string }) => this.request("browser.navigate", payload),
    snapshot: (payload: { target_id: string }) =>
      this.request<{
        target_id: string;
        title: string;
        refs: Array<{ ref: string; role: string; text?: string; name?: string; url?: string }>;
      }>("browser.snapshot", payload),
    console: (payload: { limit?: number }) =>
      this.request<{ entries: Array<{ level: string; text?: string; message?: string }> }>("browser.console", payload),
    screenshot: (payload: { target_id: string }) => this.request("browser.screenshot", payload),
    pdf: (payload: { target_id: string }) => this.request("browser.pdf", payload),
    download: (payload: { target_id: string; ref: string; path?: string }) => this.request("browser.download", payload),
    waitDownload: (payload: { target_id: string; time_ms?: number; path?: string }) =>
      this.request("browser.wait_download", payload),
    upload: (payload: { target_id: string; ref?: string; input_ref?: string; paths: string[]; time_ms?: number }) =>
      this.request("browser.upload", payload),
    dialog: (payload: { target_id: string; accept?: boolean; prompt_text?: string; time_ms?: number }) =>
      this.request("browser.dialog", payload),
    act: (payload: {
      target_id: string;
      action: string;
      ref?: string;
      value?: string;
      fields?: Array<{ ref: string; value: string }>;
      key?: string;
      values?: string[];
      time_ms?: number;
      width?: number;
      height?: number;
      path?: string;
      paths?: string[];
      input_ref?: string;
      accept?: boolean;
      prompt_text?: string;
      start_ref?: string;
      end_ref?: string;
    }) =>
      this.request("browser.act", payload),
  };

  readonly approval = {
    list: () => this.request<{ approvals: ApprovalSummary[] }>("approval.list", {}),
    resolve: (payload: { approval_id: string; decision: "approved" | "rejected" }) =>
      this.request("approval.resolve", payload),
  };

  readonly approvals = {
    list: (payload: { limit?: number; status?: string } = {}) =>
      this.request<{ approvalTickets: ApprovalSummary[]; approvalDiagnostics?: Array<Record<string, unknown>> }>(
        "approvals.list",
        payload,
      ),
    get: (payload: { approvalId: string }) =>
      this.request<Record<string, unknown>>("approvals.get", payload),
    resolve: (payload: { approvalId: string; decision: "approve" | "reject"; decidedBy?: string; decisionNote?: string }) =>
      this.request<Record<string, unknown>>("approvals.resolve", payload),
  };

  readonly audit = {
    list: (payload: { trace_id?: string } = {}) =>
      this.request<{ records: Array<{ trace_id: string; summary: string }> }>("audit.list", payload),
  };

  readonly plugin = {
    list: () => this.request<{ plugins: PluginSummary[] }>("plugin.list", {}),
    enable: (payload: { plugin_id: string }) => this.request("plugin.enable", payload),
    disable: (payload: { plugin_id: string }) => this.request("plugin.disable", payload),
    reload: (payload: { plugin_id: string }) => this.request("plugin.reload", payload),
  };

  readonly connector = {
    list: () => this.request<{ connectors: ConnectorSummary[] }>("connector.list", {}),
  };

  readonly settings = {
    get: () => this.request<SettingsSnapshot>("settings.get", {}),
    update: (payload: Partial<SettingsSnapshot>) => this.request<SettingsSnapshot>("settings.update", payload),
  };

  readonly config = {
    validate: (payload: Partial<SettingsSnapshot>) => this.request<ConfigValidationResult>("config.validate", payload),
    apply: (payload: Partial<SettingsSnapshot>) => this.request<ConfigApplyResult>("config.apply", payload),
    restartReport: (payload: Partial<SettingsSnapshot>) =>
      this.request<ConfigRestartReport>("config.restart.report", payload),
  };

  subscribe(listener: EventListener): () => void {
    return this.adapter.subscribe(listener);
  }

  async request<TData = unknown>(
    action: Parameters<typeof createBridgeRequest>[0],
    payload: unknown,
  ): Promise<BridgeResponse<TData>> {
    const request = createBridgeRequest(action, payload, {
      client: this.clientIdentity,
    });
    try {
      return await this.adapter.request<TData>(request);
    } catch (error) {
      return {
        protocol_version: request.protocol_version,
        request_id: request.request_id,
        action,
        ok: false,
        data: null,
        error: toBridgeError(error, `${action}.failed`),
        meta: {
          server_time: new Date().toISOString(),
        },
      };
    }
  }

  private async adapterCall<TData, TAction extends Parameters<typeof createBridgeRequest>[0]>(
    action: TAction,
    payload: unknown,
    call: () => Promise<TData>,
  ): Promise<BridgeResponse<TData>> {
    const request = createBridgeRequest(action, payload, {
      client: this.clientIdentity,
    });
    try {
      const data = await call();
      return createBridgeSuccess(request, data);
    } catch (error) {
      return createBridgeFailure(request, toBridgeError(error, `${action}.failed`));
    }
  }
}

export function createMockBridgeClient(identity?: BridgeClientIdentity): BridgeClient {
  return new BridgeClient(new MockHostAdapter(), identity);
}

export function createHttpBridgeClient(
  config: Pick<BridgeTransportConfig, "httpBaseUrl"> &
    Partial<
      Pick<
        BridgeTransportConfig,
        | "requestPath"
        | "eventsPath"
        | "controlUiConfigPath"
        | "controlUiStatePath"
        | "gatewayEventsPath"
        | "browserProxyPath"
        | "eventTransport"
        | "pollingIntervalMs"
        | "websocketUrl"
      >
    >,
  identity?: BridgeClientIdentity,
  deps?: ConstructorParameters<typeof HttpHostAdapter>[1],
): BridgeClient {
  return new BridgeClient(
    new HttpHostAdapter(
      {
        httpBaseUrl: config.httpBaseUrl,
        requestPath: config.requestPath ?? "/requests",
        eventsPath: config.eventsPath ?? "/events",
        controlUiConfigPath: config.controlUiConfigPath ?? "/__agenthub/control-ui-config.json",
        controlUiStatePath: config.controlUiStatePath ?? "/control-ui/state",
        gatewayEventsPath: config.gatewayEventsPath ?? "/gateway-events",
        browserProxyPath: config.browserProxyPath ?? "/browser-proxy",
        eventTransport: config.eventTransport ?? "polling",
        pollingIntervalMs: config.pollingIntervalMs ?? 800,
        websocketUrl: config.websocketUrl,
      },
      deps,
    ),
    identity,
  );
}

export function createDefaultBridgeClient(identity?: BridgeClientIdentity): BridgeClient {
  const config = resolveBridgeTransportConfig();
  if (config.mode === "http" && config.httpBaseUrl && config.requestPath && config.websocketUrl) {
    return createHttpBridgeClient(
      {
        httpBaseUrl: config.httpBaseUrl,
        requestPath: config.requestPath,
        websocketUrl: config.websocketUrl,
        eventsPath: config.eventsPath ?? "/events",
        controlUiConfigPath: config.controlUiConfigPath ?? "/__agenthub/control-ui-config.json",
        controlUiStatePath: config.controlUiStatePath ?? "/control-ui/state",
        gatewayEventsPath: config.gatewayEventsPath ?? "/gateway-events",
        browserProxyPath: config.browserProxyPath ?? "/browser-proxy",
        eventTransport: config.eventTransport ?? "websocket",
        pollingIntervalMs: config.pollingIntervalMs ?? 800,
      },
      identity ?? config.client,
    );
  }
  if (config.mode === "http" && config.httpBaseUrl && config.requestPath) {
    return createHttpBridgeClient(
      {
        httpBaseUrl: config.httpBaseUrl,
        requestPath: config.requestPath,
        websocketUrl: config.websocketUrl,
        eventsPath: config.eventsPath ?? "/events",
        controlUiConfigPath: config.controlUiConfigPath ?? "/__agenthub/control-ui-config.json",
        controlUiStatePath: config.controlUiStatePath ?? "/control-ui/state",
        gatewayEventsPath: config.gatewayEventsPath ?? "/gateway-events",
        browserProxyPath: config.browserProxyPath ?? "/browser-proxy",
        eventTransport: config.eventTransport ?? "polling",
        pollingIntervalMs: config.pollingIntervalMs ?? 800,
      },
      identity ?? config.client,
    );
  }
  return createMockBridgeClient(identity);
}
