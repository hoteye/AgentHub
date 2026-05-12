import { describe, expect, it, vi } from "vitest";

import { HttpHostAdapter, resolveBridgeTransportConfig } from "./http-host.ts";
import { createBridgeRequest } from "../types/bridge.ts";

class FakeSocket {
  listeners = new Map<string, Set<(event: MessageEvent<string>) => void>>();
  closed = false;

  addEventListener(type: string, listener: (event: MessageEvent<string>) => void) {
    const existing = this.listeners.get(type) ?? new Set();
    existing.add(listener);
    this.listeners.set(type, existing);
  }

  removeEventListener(type: string, listener: (event: MessageEvent<string>) => void) {
    this.listeners.get(type)?.delete(listener);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, data: string) {
    const event = new MessageEvent(type, { data });
    for (const listener of this.listeners.get(type) ?? []) {
      listener(event);
    }
  }
}

describe("http-host", () => {
  it("posts bridge requests to configured endpoint", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        protocol_version: "v1",
        request_id: "req_1",
        action: "settings.get",
        ok: true,
        data: { model: "gpt-5.4" },
        error: null,
        meta: { server_time: "2026-03-28T00:00:00Z" },
      }),
    })) as typeof fetch;
    const adapter = new HttpHostAdapter(
      {
        httpBaseUrl: "http://127.0.0.1:8787/gui",
        requestPath: "/requests",
        eventsPath: "/events",
        controlUiConfigPath: "/__agenthub/control-ui-config.json",
        controlUiStatePath: "/control-ui/state",
        gatewayEventsPath: "/gateway-events",
        browserProxyPath: "/browser-proxy",
        eventTransport: "websocket",
        pollingIntervalMs: 800,
        websocketUrl: "ws://127.0.0.1:8787/gui/events",
      },
      { fetchImpl },
    );
    const request = createBridgeRequest("settings.get", {}, { requestId: "req_1" });

    const response = await adapter.request(request);

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("http://127.0.0.1:8787/gui/requests");
    expect(response.data).toEqual({ model: "gpt-5.4" });
  });

  it("subscribes to websocket events and closes socket on unsubscribe", () => {
    const socket = new FakeSocket();
    const adapter = new HttpHostAdapter(
      {
        httpBaseUrl: "http://127.0.0.1:8787/gui",
        requestPath: "/requests",
        eventsPath: "/events",
        controlUiConfigPath: "/__agenthub/control-ui-config.json",
        controlUiStatePath: "/control-ui/state",
        gatewayEventsPath: "/gateway-events",
        browserProxyPath: "/browser-proxy",
        eventTransport: "websocket",
        pollingIntervalMs: 800,
        websocketUrl: "ws://127.0.0.1:8787/gui/events",
      },
      {
        webSocketFactory: () => socket,
      },
    );
    const received: string[] = [];

    const unsubscribe = adapter.subscribe((event) => {
      received.push(event.name);
    });
    socket.emit(
      "message",
      JSON.stringify({
        request_id: "req_1",
        kind: "tool_event",
        name: "browser_snapshot",
        summary: "Browser snapshot",
      }),
    );
    unsubscribe();

    expect(received).toEqual(["browser_snapshot"]);
    expect(socket.closed).toBe(true);
  });

  it("resolves runtime config from window bridge settings", () => {
    const config = resolveBridgeTransportConfig({
      location: window.location,
      __AGENTHUB_GUI_BRIDGE__: {
        mode: "http",
        httpBaseUrl: "http://127.0.0.1:8787/gui",
      },
    });

    expect(config.mode).toBe("http");
    expect(config.httpBaseUrl).toBe("http://127.0.0.1:8787/gui");
    expect(config.requestPath).toBe("/requests");
    expect(config.eventsPath).toBe("/events");
    expect(config.controlUiConfigPath).toBe("/__agenthub/control-ui-config.json");
    expect(config.controlUiStatePath).toBe("/control-ui/state");
    expect(config.gatewayEventsPath).toBe("/gateway-events");
    expect(config.browserProxyPath).toBe("/browser-proxy");
    expect(config.eventTransport).toBe("polling");
  });

  it("polls json events when configured for polling transport", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          events: [
            {
              request_id: "req_2",
              kind: "tool_event",
              name: "browser_snapshot",
              summary: "Browser snapshot",
            },
          ],
          next_cursor: 1,
        }),
      })
      .mockResolvedValue({
        ok: true,
        json: async () => ({ events: [], next_cursor: 1 }),
      }) as typeof fetch;
    let capturedInterval: (() => void) | null = null;
    const adapter = new HttpHostAdapter(
      {
        httpBaseUrl: "http://127.0.0.1:8787/gui",
        requestPath: "/requests",
        eventsPath: "/events",
        controlUiConfigPath: "/__agenthub/control-ui-config.json",
        controlUiStatePath: "/control-ui/state",
        gatewayEventsPath: "/gateway-events",
        browserProxyPath: "/browser-proxy",
        eventTransport: "polling",
        pollingIntervalMs: 800,
      },
      {
        fetchImpl,
        setIntervalImpl: ((callback: TimerHandler) => {
          capturedInterval = callback as () => void;
          return 1 as ReturnType<typeof setInterval>;
        }) as typeof setInterval,
        clearIntervalImpl: (() => {}) as typeof clearInterval,
      },
    );
    const received: string[] = [];

    const unsubscribe = adapter.subscribe((event) => {
      received.push(event.name);
    });
    await Promise.resolve();
    await Promise.resolve();
    capturedInterval?.();
    await Promise.resolve();
    unsubscribe();

    expect(fetchImpl.mock.calls[0]?.[0]).toBe("http://127.0.0.1:8787/gui/events?cursor=0");
    expect(received).toContain("browser_snapshot");
  });

  it("swallows transient polling fetch errors", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError("fetch failed")) as typeof fetch;
    let capturedInterval: (() => void) | null = null;
    const adapter = new HttpHostAdapter(
      {
        httpBaseUrl: "http://127.0.0.1:8787/gui",
        requestPath: "/requests",
        eventsPath: "/events",
        controlUiConfigPath: "/__agenthub/control-ui-config.json",
        controlUiStatePath: "/control-ui/state",
        gatewayEventsPath: "/gateway-events",
        browserProxyPath: "/browser-proxy",
        eventTransport: "polling",
        pollingIntervalMs: 800,
      },
      {
        fetchImpl,
        setIntervalImpl: ((callback: TimerHandler) => {
          capturedInterval = callback as () => void;
          return 1 as ReturnType<typeof setInterval>;
        }) as typeof setInterval,
        clearIntervalImpl: (() => {}) as typeof clearInterval,
      },
    );

    const unsubscribe = adapter.subscribe(() => {});
    await Promise.resolve();
    await Promise.resolve();
    capturedInterval?.();
    await Promise.resolve();
    await Promise.resolve();
    unsubscribe();
  });

  it("fetches control-ui bootstrap and state via dedicated endpoints", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          basePath: "/gui",
          assistantName: "AgentHub",
          assistantAvatar: "",
          assistantAgentId: "agenthub",
          serverVersion: "0.1.0",
          gateway: { methods: ["connect.initialize"], streams: ["gateway_events"] },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ok: true,
          data: {
            health: { status: "ok" },
            runtimePolicy: {},
            approvalStatus: {},
            events: [],
            workflowRuns: [],
            actionRequests: [],
            approvalTickets: [],
            auditRecords: [],
            diagnostics: {},
            connectors: [],
          },
        }),
      }) as typeof fetch;
    const adapter = new HttpHostAdapter(
      {
        httpBaseUrl: "http://127.0.0.1:8787/gui",
        requestPath: "/requests",
        eventsPath: "/events",
        controlUiConfigPath: "/__agenthub/control-ui-config.json",
        controlUiStatePath: "/control-ui/state",
        gatewayEventsPath: "/gateway-events",
        browserProxyPath: "/browser-proxy",
        eventTransport: "polling",
        pollingIntervalMs: 800,
      },
      { fetchImpl },
    );

    const bootstrap = await adapter.getControlUiBootstrap();
    const state = await adapter.getControlUiState(5);

    expect(bootstrap.basePath).toBe("/gui");
    expect(state.health.status).toBe("ok");
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("http://127.0.0.1:8787/gui/__agenthub/control-ui-config.json");
    expect(fetchImpl.mock.calls[1]?.[0]).toBe("http://127.0.0.1:8787/gui/control-ui/state?limit=5");
  });

  it("polls gateway events endpoint and dispatches browser-proxy calls", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ok: true,
          cursor: 12,
          events: [{ cursor: 12, stream: "approvals", event: "approval.updated", payload: { approval_id: "a1" } }],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          status: 200,
          result: { ok: true, running: true },
        }),
      }) as typeof fetch;
    const adapter = new HttpHostAdapter(
      {
        httpBaseUrl: "http://127.0.0.1:8787/gui",
        requestPath: "/requests",
        eventsPath: "/events",
        controlUiConfigPath: "/__agenthub/control-ui-config.json",
        controlUiStatePath: "/control-ui/state",
        gatewayEventsPath: "/gateway-events",
        browserProxyPath: "/browser-proxy",
        eventTransport: "polling",
        pollingIntervalMs: 800,
      },
      { fetchImpl },
    );

    const polled = await adapter.pollGatewayEvents(7, ["approvals"]);
    const proxy = await adapter.browserProxy({ method: "GET", path: "/", query: { profile: "openclaw" } });

    expect(polled.cursor).toBe(12);
    expect(polled.events[0]?.stream).toBe("approvals");
    expect(proxy.status).toBe(200);
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("http://127.0.0.1:8787/gui/gateway-events?cursor=7&streams=approvals");
    expect(fetchImpl.mock.calls[1]?.[0]).toBe("http://127.0.0.1:8787/gui/browser-proxy/?profile=openclaw");
  });
});
