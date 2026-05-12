import {
  normalizeBridgeEvent,
  toBridgeError,
  type BrowserProxyRequest,
  type BrowserProxyResponse,
  type BridgeClientIdentity,
  type BridgeEvent,
  type BridgeRequest,
  type BridgeResponse,
  type ControlUiBootstrap,
  type ControlUiStateSnapshot,
  type GatewayEventPollResult,
} from "../types/bridge.ts";
import type { HostAdapter } from "./mock-host.ts";

type EventListener = (event: BridgeEvent<Record<string, unknown>>) => void;

export type BridgeRuntimeMode = "mock" | "http";
export type BridgeEventTransport = "websocket" | "polling";

export type BridgeTransportConfig = {
  mode: BridgeRuntimeMode;
  httpBaseUrl?: string;
  requestPath?: string;
  websocketUrl?: string;
  eventsPath?: string;
  controlUiConfigPath?: string;
  controlUiStatePath?: string;
  gatewayEventsPath?: string;
  browserProxyPath?: string;
  eventTransport?: BridgeEventTransport;
  pollingIntervalMs?: number;
  client?: BridgeClientIdentity;
};

export type WebSocketLike = {
  addEventListener(type: string, listener: EventListenerObject | ((event: MessageEvent<string>) => void)): void;
  removeEventListener(type: string, listener: EventListenerObject | ((event: MessageEvent<string>) => void)): void;
  close(): void;
};

type FetchLike = typeof fetch;
type WebSocketFactory = (url: string) => WebSocketLike;
type IntervalHandle = ReturnType<typeof setInterval>;

declare global {
  interface Window {
    __AGENTHUB_GUI_BRIDGE__?: Partial<BridgeTransportConfig>;
  }
}

function normalizeBaseUrl(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

function joinUrl(base: string, path: string): string {
  const normalizedBase = normalizeBaseUrl(base);
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${normalizedBase}${normalizedPath}`;
}

function toWebSocketUrl(httpBaseUrl: string, eventsPath: string): string {
  const base = new URL(httpBaseUrl);
  base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
  base.pathname = eventsPath.startsWith("/") ? eventsPath : `/${eventsPath}`;
  return base.toString();
}

export function resolveBridgeTransportConfig(
  source: Pick<Window, "location"> & { __AGENTHUB_GUI_BRIDGE__?: Partial<BridgeTransportConfig> } = window,
): BridgeTransportConfig {
  const provided = source.__AGENTHUB_GUI_BRIDGE__ ?? {};
  if (provided.mode === "http" && provided.httpBaseUrl) {
    const requestPath = provided.requestPath ?? "/requests";
    const eventsPath = provided.eventsPath ?? "/events";
    return {
      mode: "http",
      httpBaseUrl: normalizeBaseUrl(provided.httpBaseUrl),
      requestPath,
      eventsPath,
      controlUiConfigPath: provided.controlUiConfigPath ?? "/__agenthub/control-ui-config.json",
      controlUiStatePath: provided.controlUiStatePath ?? "/control-ui/state",
      gatewayEventsPath: provided.gatewayEventsPath ?? "/gateway-events",
      browserProxyPath: provided.browserProxyPath ?? "/browser-proxy",
      websocketUrl: provided.websocketUrl,
      eventTransport: provided.eventTransport ?? (provided.websocketUrl ? "websocket" : "polling"),
      pollingIntervalMs: Math.max(250, Number(provided.pollingIntervalMs ?? 800)),
      client: provided.client,
    };
  }
  return {
    mode: "mock",
  };
}

export class HttpHostAdapter implements HostAdapter {
  private readonly listeners = new Set<EventListener>();
  private socket: WebSocketLike | null = null;
  private pollingHandle: IntervalHandle | null = null;
  private eventCursor = 0;
  private pollingInFlight = false;
  private boundOnMessage: ((event: MessageEvent<string>) => void) | null = null;
  private boundOnClose: (() => void) | null = null;

  constructor(
    private readonly config: Required<
      Pick<
        BridgeTransportConfig,
        | "httpBaseUrl"
        | "requestPath"
        | "eventsPath"
        | "controlUiConfigPath"
        | "controlUiStatePath"
        | "gatewayEventsPath"
        | "browserProxyPath"
        | "eventTransport"
        | "pollingIntervalMs"
      >
    > &
      Pick<BridgeTransportConfig, "websocketUrl">,
    private readonly deps: {
      fetchImpl?: FetchLike;
      webSocketFactory?: WebSocketFactory;
      setIntervalImpl?: typeof setInterval;
      clearIntervalImpl?: typeof clearInterval;
    } = {},
  ) {}

  async request<TData = unknown>(request: BridgeRequest<unknown>): Promise<BridgeResponse<TData>> {
    const fetchImpl = this.deps.fetchImpl ?? fetch;
    const response = await fetchImpl(joinUrl(this.config.httpBaseUrl, this.config.requestPath), {
      method: "POST",
      headers: {
        "content-type": "application/json",
      },
      body: JSON.stringify(request),
    });
    const payload = (await response.json()) as BridgeResponse<TData>;
    if (!response.ok) {
      throw toBridgeError(payload.error ?? `bridge request failed: ${response.status}`, `${request.action}.failed`);
    }
    return payload;
  }

  async getControlUiBootstrap(): Promise<ControlUiBootstrap> {
    return this.fetchJson<ControlUiBootstrap>(this.config.controlUiConfigPath);
  }

  async getControlUiState(limit = 20): Promise<ControlUiStateSnapshot> {
    const url = new URL(joinUrl(this.config.httpBaseUrl, this.config.controlUiStatePath));
    url.searchParams.set("limit", String(Math.max(1, Math.trunc(Number(limit) || 20))));
    const payload = await this.fetchJson<{ ok: boolean; data: ControlUiStateSnapshot }>(url.toString(), true);
    if (!payload.ok || !payload.data) {
      throw new Error("control_ui_state_unavailable");
    }
    return payload.data;
  }

  async pollGatewayEvents(cursor = 0, streams: string[] = []): Promise<GatewayEventPollResult> {
    const url = new URL(joinUrl(this.config.httpBaseUrl, this.config.gatewayEventsPath));
    url.searchParams.set("cursor", String(Math.max(0, Math.trunc(Number(cursor) || 0))));
    if (streams.length) {
      url.searchParams.set("streams", streams.join(","));
    }
    const payload = await this.fetchJson<{ ok: boolean; cursor?: number; events?: Array<Record<string, unknown>> }>(
      url.toString(),
      true,
    );
    return {
      cursor: Number(payload.cursor ?? cursor) || 0,
      events: (payload.events ?? []).map((item) => ({
        cursor: Number(item.cursor ?? 0),
        stream: String(item.stream ?? "gateway_events"),
        event: String(item.event ?? "gateway.event"),
        payload: (item.payload as Record<string, unknown>) ?? {},
        emittedAt: typeof item.emittedAt === "string" ? item.emittedAt : undefined,
      })),
    };
  }

  async browserProxy(request: BrowserProxyRequest): Promise<BrowserProxyResponse> {
    const method = String(request.method || "GET").toUpperCase();
    const proxyPath = normalizeProxyPath(this.config.browserProxyPath, request.path);
    const fetchImpl = this.deps.fetchImpl ?? fetch;
    const url = new URL(joinUrl(this.config.httpBaseUrl, proxyPath));
    for (const [key, value] of Object.entries(request.query ?? {})) {
      url.searchParams.set(key, String(value));
    }
    const response = await fetchImpl(url.toString(), {
      method,
      headers: {
        "content-type": "application/json",
      },
      body: method === "POST" || method === "DELETE" ? JSON.stringify(request.body ?? {}) : undefined,
    });
    const payload = (await response.json()) as BrowserProxyResponse;
    if (!response.ok) {
      throw new Error(`browser_proxy_failed:${response.status}`);
    }
    return payload;
  }

  subscribe(listener: EventListener): () => void {
    this.listeners.add(listener);
    this.ensureEventTransport();
    return () => {
      this.listeners.delete(listener);
      if (this.listeners.size === 0) {
        this.teardownEvents();
      }
    };
  }

  private ensureEventTransport() {
    if (this.config.eventTransport === "websocket") {
      this.ensureSocket();
      return;
    }
    this.ensurePolling();
  }

  private async fetchJson<TData>(pathOrUrl: string, absolute = false): Promise<TData> {
    const fetchImpl = this.deps.fetchImpl ?? fetch;
    const url = absolute ? pathOrUrl : joinUrl(this.config.httpBaseUrl, pathOrUrl);
    const response = await fetchImpl(url, {
      method: "GET",
      headers: {
        accept: "application/json",
      },
    });
    if (!response.ok) {
      throw new Error(`http_fetch_failed:${response.status}`);
    }
    return (await response.json()) as TData;
  }

  private ensureSocket() {
    if (this.socket) {
      return;
    }
    if (!this.config.websocketUrl) {
      throw new Error("websocketUrl is required for websocket event transport");
    }
    const factory = this.deps.webSocketFactory ?? ((url: string) => new WebSocket(url));
    this.socket = factory(this.config.websocketUrl);
    this.boundOnMessage = (event: MessageEvent<string>) => {
      const raw = typeof event.data === "string" ? JSON.parse(event.data) : event.data;
      const normalized = normalizeBridgeEvent(raw);
      for (const listener of this.listeners) {
        listener(normalized);
      }
    };
    this.boundOnClose = () => {
      this.teardownSocket(false);
    };
    this.socket.addEventListener("message", this.boundOnMessage);
    this.socket.addEventListener("close", this.boundOnClose);
  }

  private ensurePolling() {
    if (this.pollingHandle !== null) {
      return;
    }
    const setIntervalImpl = this.deps.setIntervalImpl ?? setInterval;
    void this.pollEvents();
    this.pollingHandle = setIntervalImpl(() => {
      void this.pollEvents();
    }, this.config.pollingIntervalMs);
  }

  private async pollEvents() {
    if (this.pollingInFlight || this.listeners.size === 0) {
      return;
    }
    this.pollingInFlight = true;
    try {
      const fetchImpl = this.deps.fetchImpl ?? fetch;
      const url = new URL(joinUrl(this.config.httpBaseUrl, this.config.eventsPath));
      url.searchParams.set("cursor", String(this.eventCursor));
      const response = await fetchImpl(url.toString(), {
        method: "GET",
        headers: {
          accept: "application/json",
        },
      });
      if (!response.ok) {
        return;
      }
      const payload = (await response.json()) as {
        events?: Array<Record<string, unknown>>;
        next_cursor?: number;
      };
      for (const item of payload.events ?? []) {
        const normalized = normalizeBridgeEvent({
          ...(item as Record<string, unknown>),
          request_id: String(item.request_id ?? "req_gui_event"),
          kind: item.kind as BridgeEvent<Record<string, unknown>>["kind"],
          name: String(item.name ?? "gui_event"),
        });
        for (const listener of this.listeners) {
          listener(normalized);
        }
      }
      if (typeof payload.next_cursor === "number" && Number.isFinite(payload.next_cursor)) {
        this.eventCursor = payload.next_cursor;
      }
    } catch {
      return;
    } finally {
      this.pollingInFlight = false;
    }
  }

  private teardownSocket(closeSocket = true) {
    if (!this.socket) {
      return;
    }
    if (this.boundOnMessage) {
      this.socket.removeEventListener("message", this.boundOnMessage);
    }
    if (this.boundOnClose) {
      this.socket.removeEventListener("close", this.boundOnClose);
    }
    if (closeSocket) {
      this.socket.close();
    }
    this.socket = null;
    this.boundOnMessage = null;
    this.boundOnClose = null;
  }

  private teardownEvents() {
    this.teardownSocket();
    if (this.pollingHandle !== null) {
      const clearIntervalImpl = this.deps.clearIntervalImpl ?? clearInterval;
      clearIntervalImpl(this.pollingHandle);
      this.pollingHandle = null;
    }
  }
}

function normalizeProxyPath(basePath: string, requestPath: string): string {
  const prefix = basePath.startsWith("/") ? basePath : `/${basePath}`;
  const suffix = requestPath.startsWith("/") ? requestPath : `/${requestPath}`;
  return `${prefix}${suffix}`.replace(/\/{2,}/g, "/");
}
