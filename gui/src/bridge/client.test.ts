import { describe, expect, it } from "vitest";

import { createDefaultBridgeClient, createHttpBridgeClient, createMockBridgeClient } from "./client.ts";

describe("bridge client", () => {
  it("serves namespaced requests through the mock adapter", async () => {
    const client = createMockBridgeClient();
    const response = await client.settings.get();

    expect(response.ok).toBe(true);
    expect(response.data?.model).toBe("gpt-5.4");
  });

  it("emits normalized events for task requests", async () => {
    const client = createMockBridgeClient();
    const events: string[] = [];
    const unsubscribe = client.subscribe((event) => {
      events.push(event.kind);
    });

    await client.task.run({ text: "run validation" });
    unsubscribe();

    expect(events).toEqual(["task_started", "task_progress", "task_completed"]);
  });

  it("runs shell bridge requests through the mock adapter", async () => {
    const client = createMockBridgeClient();
    const events: string[] = [];
    const unsubscribe = client.subscribe((event) => {
      events.push(event.kind);
    });

    const response = await client.shell.run({ command: "pwd", cwd: "/home/lyc/project/AgentHub" });
    unsubscribe();

    expect(response.ok).toBe(true);
    expect(response.data?.stdout).toBe("/home/lyc/project/AgentHub");
    expect(response.data?.exit_code).toBe(0);
    expect(events).toEqual(["task_started", "tool_event", "task_completed"]);
  });

  it("exposes thread list and resume through the mock adapter", async () => {
    const client = createMockBridgeClient();
    const listed = await client.thread.list({ limit: 5 });
    const firstThreadId = listed.data?.threads[0]?.thread_id ?? "";
    const resumed = await client.thread.resume({ thread_id: firstThreadId });

    expect(listed.ok).toBe(true);
    expect(firstThreadId).not.toBe("");
    expect(resumed.ok).toBe(true);
    expect(resumed.data?.history.length).toBeGreaterThan(0);
    expect(resumed.data?.turns?.length).toBeGreaterThan(0);
  });

  it("exposes connector list through the mock adapter", async () => {
    const client = createMockBridgeClient();
    const response = await client.connector.list();

    expect(response.ok).toBe(true);
    expect(response.data?.connectors[0]?.connector_key).toBe("github_webhook");
  });

  it("builds a default client from window runtime config", () => {
    window.__AGENTHUB_GUI_BRIDGE__ = {
      mode: "http",
      httpBaseUrl: "http://127.0.0.1:8787/gui",
    };

    const client = createDefaultBridgeClient();

    expect(client).toBeInstanceOf(Object);
    delete window.__AGENTHUB_GUI_BRIDGE__;
  });

  it("exposes control-ui bootstrap/state through adapter-backed helpers", async () => {
    const client = createMockBridgeClient();
    const bootstrap = await client.controlUi.bootstrap();
    const state = await client.controlUi.state({ limit: 5 });

    expect(bootstrap.ok).toBe(true);
    expect(bootstrap.data?.gateway.streams).toContain("gateway_events");
    expect(state.ok).toBe(true);
    expect(state.data?.health.status).toBe("ok");
  });

  it("exposes gateway poll and browser proxy through adapter-backed helpers", async () => {
    const client = createMockBridgeClient();
    const polled = await client.gateway.events.poll({ cursor: 0, streams: ["approvals"] });
    const proxy = await client.browser.proxy({ method: "GET", path: "/profiles" });
    const logs = await client.gateway.logs.tail({ source: "gateway.audit_records", lines: 2 });
    const workflows = await client.gateway.workflows.list({ limit: 5 });
    const workflowDetail = await client.gateway.workflows.get({ workflowRunId: "run_1" });

    expect(polled.ok).toBe(true);
    expect(polled.data?.events[0]?.stream).toBe("approvals");
    expect(proxy.ok).toBe(true);
    expect(proxy.data?.status).toBe(200);
    expect(logs.ok).toBe(true);
    expect(logs.data?.source).toBe("gateway.audit_records");
    expect(logs.data?.lines.length).toBe(2);
    expect(workflows.ok).toBe(true);
    expect((workflows.data?.workflowRuns as Array<{ workflow_run_id?: string }> | undefined)?.[0]?.workflow_run_id).toBe("run_1");
    expect(workflowDetail.ok).toBe(true);
    expect((workflowDetail.data?.workflowRun as { workflow_name?: string } | undefined)?.workflow_name).toBe("handle_github_issue_opened");
  });

  it("constructs http clients when requested", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        protocol_version: "v1",
        request_id: "req_1",
        action: "settings.get",
        ok: true,
        data: { model: "gpt-5.4", browserHeadless: false, pluginAutoLoad: true, workspaceRoot: "/tmp" },
        error: null,
        meta: { server_time: "2026-03-28T00:00:00Z" },
      }),
    })) as typeof fetch;
    const client = createHttpBridgeClient(
      {
        httpBaseUrl: "http://127.0.0.1:8787/gui",
        requestPath: "/requests",
        websocketUrl: "ws://127.0.0.1:8787/events",
      },
      undefined,
      {
        fetchImpl,
        webSocketFactory: () =>
          ({
            addEventListener() {},
            removeEventListener() {},
            close() {},
          }) as WebSocket,
      },
    );

    const response = await client.settings.get();

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(response.data?.workspaceRoot).toBe("/tmp");
  });

  it("surfaces access posture from connect capabilities", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        protocol_version: "v1",
        request_id: "req_access",
        action: "connect.capabilities",
        ok: true,
        data: {
          methods: [],
          legacyMethods: [],
          accessPosture: {
            access: {
              posture: "local-only",
              local: { enabled: true, channel: "local-app-server", origin: "localhost" },
              remote: { enabled: false, channel: "gateway", origin: null },
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
              pendingRequestCount: 0,
              pendingApprovalCount: 1,
              source: "approvals.pending_heuristic",
              hasNativeContract: false,
            },
            summary: {
              pendingPairingRequestCount: 0,
              pendingApprovalCount: 1,
              accessPosture: "local-only",
              authMode: "trusted_local",
              authOrigin: "local",
            },
          },
        },
        error: null,
        meta: { server_time: "2026-03-29T00:00:00Z" },
      }),
    })) as typeof fetch;
    const client = createHttpBridgeClient(
      {
        httpBaseUrl: "http://127.0.0.1:8787/gui",
        requestPath: "/requests",
      },
      undefined,
      {
        fetchImpl,
      },
    );
    const response = await client.gateway.connect.capabilities();

    expect(response.ok).toBe(true);
    expect(response.data?.accessPosture?.access.posture).toBe("local-only");
    expect(response.data?.accessPosture?.summary.pendingPairingRequestCount).toBe(0);
  });

  it("requests access posture through the dedicated gateway helper", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        protocol_version: "v1",
        request_id: "req_access_posture",
        action: "access.posture.get",
        ok: true,
        data: {
          access: {
            posture: "local+remote",
            local: { enabled: true, channel: "local-app-server", origin: "localhost" },
            remote: { enabled: true, channel: "gateway", origin: "network" },
          },
          auth: {
            mode: "remote_authenticated",
            origin: "remote",
            authenticated: true,
            authSource: "shared-secret",
            trustLevel: "unknown",
            actorId: "remote-operator-1",
            clientType: "gateway",
            roles: ["operator"],
            scopes: ["gateway.read"],
          },
          pairing: {
            pendingRequestCount: 1,
            pendingApprovalCount: 1,
            source: "approvals.pending_heuristic",
            hasNativeContract: false,
          },
          summary: {
            pendingPairingRequestCount: 1,
            pendingApprovalCount: 1,
            accessPosture: "local+remote",
            authMode: "remote_authenticated",
            authOrigin: "remote",
          },
        },
        error: null,
        meta: { server_time: "2026-03-29T00:00:00Z" },
      }),
    })) as typeof fetch;
    const client = createHttpBridgeClient(
      {
        httpBaseUrl: "http://127.0.0.1:8787/gui",
        requestPath: "/requests",
      },
      undefined,
      {
        fetchImpl,
      },
    );
    const response = await client.gateway.access.posture();

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(response.ok).toBe(true);
    expect(response.data?.auth.mode).toBe("remote_authenticated");
    expect(response.data?.pairing.pendingRequestCount).toBe(1);
  });

  it("requests nodes inventory through the dedicated gateway helper", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        protocol_version: "v1",
        request_id: "req_nodes",
        action: "nodes.list",
        ok: true,
        data: {
          nodes: [
            {
              nodeId: "node.local.app_server",
              deviceId: "local-app-server",
              kind: "local",
              label: "Local App Server",
              status: "online",
              access: { enabled: true, channel: "local-app-server", origin: "localhost", posture: "local-only" },
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
                pendingRequestCount: 0,
                pendingApprovalCount: 1,
                source: "approvals.pending_heuristic",
                hasNativeContract: false,
                writeSupported: false,
              },
              activity: {
                eventCount: 1,
                workflowCount: 2,
                approvalCount: 1,
                lastSeenAt: "2026-03-29T00:00:00Z",
              },
              runtime: {
                workspaceTrust: "trusted",
                toolCount: 12,
                mcpServerCount: 1,
                appConnectorCount: 2,
              },
            },
          ],
          devices: [],
          accessPosture: {
            access: {
              posture: "local-only",
              local: { enabled: true, channel: "local-app-server", origin: "localhost" },
              remote: { enabled: false, channel: "gateway", origin: null },
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
              pendingRequestCount: 0,
              pendingApprovalCount: 1,
              source: "approvals.pending_heuristic",
              hasNativeContract: false,
            },
            summary: {
              pendingPairingRequestCount: 0,
              pendingApprovalCount: 1,
              accessPosture: "local-only",
              authMode: "trusted_local",
              authOrigin: "local",
            },
          },
          pairing: {
            pendingRequestCount: 0,
            pendingApprovalCount: 1,
            source: "approvals.pending_heuristic",
            hasNativeContract: false,
          },
          summary: {
            totalNodes: 1,
            localNodes: 1,
            remoteNodes: 0,
            pendingPairingRequestCount: 0,
            pendingApprovalCount: 1,
            recentEvents: 1,
            recentWorkflowRuns: 2,
            recentApprovalTickets: 1,
            mcpServerCount: 1,
            appConnectorCount: 2,
            lastSeenAt: "2026-03-29T00:00:00Z",
            limit: 20,
          },
          capabilities: {
            readOnly: true,
            pairingWriteSupported: false,
          },
          runtimeRegistry: {
            workspaceTrust: "trusted",
            mcpServers: [],
            appConnectors: [],
            toolCount: 12,
            source: "tools.capabilities",
          },
          source: {
            contract: "nodes.list.v1",
            derivedFrom: ["access.posture.get"],
          },
        },
        error: null,
        meta: { server_time: "2026-03-29T00:00:00Z" },
      }),
    })) as typeof fetch;
    const client = createHttpBridgeClient(
      {
        httpBaseUrl: "http://127.0.0.1:8787/gui",
        requestPath: "/requests",
      },
      undefined,
      {
        fetchImpl,
      },
    );
    const response = await client.gateway.nodes.list();

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(response.ok).toBe(true);
    expect(response.data?.summary.totalNodes).toBe(1);
    expect(response.data?.nodes[0]?.runtime.workspaceTrust).toBe("trusted");
    expect(response.data?.source.contract).toBe("nodes.list.v1");
  });
});
