import { afterEach, describe, expect, it, vi } from "vitest";

import { BridgeClient } from "../../bridge/client.ts";
import { MockHostAdapter } from "../../shared/api/mock-host.ts";
import type { HostAdapter } from "../../shared/api/mock-host.ts";
import { createBridgeFailure, createBridgeSuccess, type BridgeEvent, type BridgeRequest } from "../../shared/types/bridge.ts";
import "./settings-page.ts";

async function flushUi(element: { updateComplete?: Promise<unknown> }) {
  await Promise.resolve();
  await Promise.resolve();
  await element.updateComplete;
  await Promise.resolve();
  await element.updateComplete;
}

async function feedbackText(root: ShadowRoot): Promise<string> {
  const element = root.querySelector("[data-testid='settings-feedback']") as HTMLElement & {
    shadowRoot?: ShadowRoot;
    updateComplete?: Promise<unknown>;
  };
  await element?.updateComplete;
  return element?.shadowRoot?.textContent ?? "";
}

class FailingSettingsAdapter implements HostAdapter {
  async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (
      request.action === "settings.get" ||
      request.action === "settings.update" ||
      request.action === "config.validate" ||
      request.action === "config.apply" ||
      request.action === "config.restart.report"
    ) {
      return createBridgeFailure(request, {
        code: `${request.action}.failed`,
        message: "settings backend unavailable",
        retryable: false,
      });
    }
    return createBridgeSuccess(request, {} as TData);
  }

  subscribe(_listener: (event: BridgeEvent<Record<string, unknown>>) => void) {
    return () => {};
  }
}

class DiagnosticsSettingsAdapter extends MockHostAdapter {
  controlUiStateCalls = 0;
  healthProbeCalls = 0;
  logTailCalls = 0;

  override async getControlUiState(limit?: number) {
    this.controlUiStateCalls += 1;
    return super.getControlUiState(limit);
  }

  override async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "health.probes") {
      this.healthProbeCalls += 1;
    }
    if (request.action === "logs.tail") {
      this.logTailCalls += 1;
    }
    return super.request<TData>(request);
  }
}

class DelayedFirstLogTailAdapter extends MockHostAdapter {
  logTailSources: string[] = [];
  private holdNextLogTail = false;
  private heldLogTailRelease: (() => void) | null = null;
  private heldLogTailPending: Promise<void> | null = null;

  pauseNextLogTail() {
    this.holdNextLogTail = true;
  }

  releaseHeldLogTail() {
    this.heldLogTailRelease?.();
    this.heldLogTailRelease = null;
    this.heldLogTailPending = null;
  }

  override async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "logs.tail") {
      const payload = (request.payload as { source?: string } | undefined) ?? {};
      this.logTailSources.push(String(payload.source ?? "").trim() || "default");
      if (this.holdNextLogTail) {
        this.holdNextLogTail = false;
        this.heldLogTailPending =
          this.heldLogTailPending ??
          new Promise<void>((resolve) => {
            this.heldLogTailRelease = resolve;
          });
        await this.heldLogTailPending;
      }
    }
    return super.request<TData>(request);
  }
}

class NestedRolloutLogAdapter extends MockHostAdapter {
  override async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "logs.tail") {
      const payload = (request.payload as { source?: string } | undefined) ?? {};
      if (String(payload.source ?? "").trim() === "thread.active_rollout") {
        const response = await super.request<Record<string, unknown>>(request);
        const line = JSON.stringify({
          type: "turn",
          thread_id: "thread_live_nested",
          timestamp: "2026-03-30T07:45:00Z",
          turn: {
            timestamp: "2026-03-30T07:45:00Z",
            user_text: "检查 workflow 细节",
            assistant_text: "workflow 已进入等待审批状态",
            runtime_state: {
              trace_id: "trace_live_nested",
              workflow_run_id: "run_live_nested",
            },
          },
        });
        const base = response.ok && response.data ? response.data : {};
        return createBridgeSuccess(request, {
          ...base,
          source: "thread.active_rollout",
          label: "Active Thread Rollout",
          lines: [line],
          text: line,
          lineCount: 1,
          truncated: false,
        } as TData);
      }
    }
    return super.request<TData>(request);
  }
}

class DegradedProbeSettingsAdapter extends MockHostAdapter {
  override async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "health.probes") {
      return createBridgeSuccess(request, {
        status: "degraded",
        probes: {
          runtime: { ok: true },
          gatewayStateStore: { ok: true, workflowRuns: 1, events: 1 },
          browserControl: { ok: false, running: false, tabCount: 0 },
        },
      } as TData);
    }
    return super.request<TData>(request);
  }
}

class GatewayProviderFallbackAdapter extends MockHostAdapter {
  override async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "settings.get" || request.action === "health.get" || request.action === "control_ui.bootstrap") {
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
    const response = await super.request<TData>(request);
    if (request.action === "connect.capabilities" && response.ok && response.data) {
      const payload = { ...(response.data as Record<string, unknown>) };
      delete payload.providerLabel;
      return createBridgeSuccess(request, payload as TData);
    }
    return response;
  }
}

class FailingGatewayConnectAdapter extends MockHostAdapter {
  override async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (
      request.action === "connect.initialize" ||
      request.action === "connect.capabilities" ||
      request.action === "connect.ping"
    ) {
      return createBridgeFailure(request, {
        code: `${request.action}.failed`,
        message: `${request.action} unavailable`,
        retryable: true,
      });
    }
    return super.request<TData>(request);
  }
}

class PartialPingFailureAdapter extends MockHostAdapter {
  override async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "connect.ping") {
      return createBridgeFailure(request, {
        code: "connect.ping.failed",
        message: "connect.ping unavailable",
        retryable: true,
      });
    }
    return super.request<TData>(request);
  }
}

class RecoveringGatewayCapabilitiesAdapter extends MockHostAdapter {
  private capabilitiesCalls = 0;

  override async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "connect.capabilities") {
      this.capabilitiesCalls += 1;
      if (this.capabilitiesCalls === 1) {
        return createBridgeFailure(request, {
          code: "connect.capabilities.failed",
          message: "connect.capabilities unavailable",
          retryable: true,
        });
      }
    }
    return super.request<TData>(request);
  }
}

class AccessPosturePendingRefsAdapter extends MockHostAdapter {
  override async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "access.posture.get") {
      const response = await super.request<Record<string, unknown>>(request);
      if (!response.ok || !response.data) {
        return super.request<TData>(request);
      }
      const payload = response.data as Record<string, unknown>;
      const pairing = (payload.pairing as Record<string, unknown>) ?? {};
      return createBridgeSuccess(request, {
        ...payload,
        pairing: {
          ...pairing,
          pendingRequestCount: 2,
          pendingRefs: [
            {
              approvalId: "approval_demo_001",
              traceId: "trace_demo_001",
              title: "Remote device pairing request",
              actionType: "pairing.request",
              requestedAt: "2026-03-30T09:10:00Z",
            },
            {
              approvalId: "approval_route_only",
              title: "Approval-only pairing ref",
              actionType: "pairing.request",
            },
          ],
        },
      } as TData);
    }
    return super.request<TData>(request);
  }
}

class CapturingSettingsUpdateAdapter extends MockHostAdapter {
  lastConfigApplyPayload: Record<string, unknown> | null = null;
  lastConfigValidatePayload: Record<string, unknown> | null = null;
  lastConfigRestartReportPayload: Record<string, unknown> | null = null;
  private settingsSnapshot: Record<string, unknown> = {
    model: "gpt-5.4",
    browserHeadless: false,
    pluginAutoLoad: true,
    workspaceRoot: "/home/lyc/project/AgentHub",
    runtimePolicy: {
      approval_policy: "on-request",
      sandbox_mode: "workspace-write",
      web_search_mode: "live",
      network_access: "enabled",
    },
  };

  override async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "settings.get") {
      return createBridgeSuccess(request, { ...this.settingsSnapshot } as TData);
    }
    if (request.action === "config.validate") {
      this.lastConfigValidatePayload = (request.payload as Record<string, unknown>) ?? null;
      const nextPayload = (request.payload as Record<string, unknown>) ?? {};
      const changedFields: string[] = [];
      const applyableFields: string[] = [];
      const blocked = [];
      const applyPath: Array<{ field: string; handler: string }> = [];
      if (String(nextPayload.model ?? this.settingsSnapshot.model) !== String(this.settingsSnapshot.model)) {
        changedFields.push("model");
        blocked.push({
          field: "model",
          code: "unsupported",
          reason: "provider/model 变更尚未接入真实 config.apply contract。",
        });
      }
      if (Boolean(nextPayload.pluginAutoLoad) !== Boolean(this.settingsSnapshot.pluginAutoLoad)) {
        changedFields.push("pluginAutoLoad");
        applyableFields.push("pluginAutoLoad");
        applyPath.push({ field: "pluginAutoLoad", handler: "gui.runtime_flags" });
      }
      return createBridgeSuccess(request, {
        changedFields,
        applyableFields,
        blocked,
        blockedFields: blocked.map((item) => item.field),
        warnings: blocked.map((item) => item.reason),
        applyPath,
        restart: {
          required: applyableFields.includes("pluginAutoLoad"),
          reasons: applyableFields.includes("pluginAutoLoad") ? ["pluginAutoLoad 变更"] : [],
          allowed: false,
          mode: "manual",
          blockedReason: applyableFields.includes("pluginAutoLoad")
            ? "runtime restart 仍需 operator 在相关运行面手动执行；当前 contract 只返回 restart report。"
            : null,
        },
      } as TData);
    }
    if (request.action === "config.restart.report") {
      this.lastConfigRestartReportPayload = (request.payload as Record<string, unknown>) ?? null;
    }
    if (request.action === "config.apply") {
      this.lastConfigApplyPayload = (request.payload as Record<string, unknown>) ?? null;
      const nextPayload = (request.payload as Record<string, unknown>) ?? {};
      const runtimePolicy =
        "runtimePolicy" in nextPayload && typeof nextPayload.runtimePolicy === "object" && nextPayload.runtimePolicy
          ? {
              ...(this.settingsSnapshot.runtimePolicy as Record<string, unknown>),
              ...(nextPayload.runtimePolicy as Record<string, unknown>),
            }
          : (this.settingsSnapshot.runtimePolicy as Record<string, unknown>);
      this.settingsSnapshot = {
        ...this.settingsSnapshot,
        ...nextPayload,
        runtimePolicy,
      };
      return createBridgeSuccess(request, {
        applied: true,
        status: "partial",
        appliedFields: ["pluginAutoLoad"],
        blockedFields: ["model"],
        validation: {
          changedFields: ["model", "pluginAutoLoad"],
          applyableFields: ["pluginAutoLoad"],
          blocked: [
            {
              field: "model",
              code: "unsupported",
              reason: "provider/model 变更尚未接入真实 config.apply contract。",
            },
          ],
          blockedFields: ["model"],
          warnings: ["provider/model 变更尚未接入真实 config.apply contract。"],
          applyPath: [{ field: "pluginAutoLoad", handler: "gui.runtime_flags" }],
          restart: {
            required: true,
            reasons: ["pluginAutoLoad 变更"],
            allowed: false,
            mode: "manual",
            blockedReason: "runtime restart 仍需 operator 在相关运行面手动执行；当前 contract 只返回 restart report。",
          },
        },
        restart: {
          required: true,
          reasons: ["pluginAutoLoad 变更"],
          allowed: false,
          mode: "manual",
          blockedReason: "runtime restart 仍需 operator 在相关运行面手动执行；当前 contract 只返回 restart report。",
        },
        settings: { ...this.settingsSnapshot },
      } as TData);
    }
    return super.request<TData>(request);
  }
}

afterEach(() => {
  document.body.innerHTML = "";
  delete window.__AGENTHUB_GUI_BRIDGE__;
  vi.useRealTimers();
});

describe("settings-page", () => {
  it("loads settings snapshot from mock bridge", async () => {
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("Runtime / Provider / Model / Policy");
    await expect(feedbackText(element.shadowRoot)).resolves.toContain("已加载 runtime 设置快照");
    const modelReadonly = element.shadowRoot.querySelector(
      "[data-testid='runtime-model-readonly']",
    ) as HTMLElement;
    expect(modelReadonly.textContent).toContain("gpt-5.4");
    const providerLabel = element.shadowRoot.querySelector(
      "[data-testid='runtime-provider-label']",
    ) as HTMLElement;
    expect(providerLabel.textContent).toContain("openai");
    const environmentSummary = element.shadowRoot.querySelector(
      "[data-testid='runtime-environment-summary']",
    ) as HTMLElement;
    expect(environmentSummary.textContent).toContain("Workspace Trust");
    const gatewayConnectSummary = element.shadowRoot.querySelector(
      "[data-testid='gateway-connect-summary']",
    ) as HTMLElement;
    expect(gatewayConnectSummary.textContent).toContain("ready");
    expect(gatewayConnectSummary.textContent).toContain("v1");
    expect(gatewayConnectSummary.textContent).toContain("agenthub-gateway");
    expect(gatewayConnectSummary.textContent).toContain("connect.capabilities");
    const gatewayAuthSummary = element.shadowRoot.querySelector(
      "[data-testid='gateway-auth-summary']",
    ) as HTMLElement;
    expect(gatewayAuthSummary.textContent).toContain("mock / local");
    expect(gatewayAuthSummary.textContent).toContain("不代表真实认证结果");
    const gatewayOriginHint = element.shadowRoot.querySelector(
      "[data-testid='gateway-origin-hint']",
    ) as HTMLElement;
    expect(gatewayOriginHint.textContent).toContain("mock transport");
    const gatewayScopeSummary = element.shadowRoot.querySelector(
      "[data-testid='gateway-scope-summary']",
    ) as HTMLElement;
    expect(gatewayScopeSummary.textContent).toContain("gateway.read");
    const gatewayMethodList = element.shadowRoot.querySelector(
      "[data-testid='gateway-method-list']",
    ) as HTMLElement;
    expect(gatewayMethodList.textContent).toContain("browser.proxy");
    expect(gatewayMethodList.textContent).toContain("approvals.resolve");
    const gatewayFamilySummary = element.shadowRoot.querySelector(
      "[data-testid='gateway-family-summary']",
    ) as HTMLElement;
    expect(gatewayFamilySummary.textContent).toContain("browser=1");
    const gatewayLegacyMethods = element.shadowRoot.querySelector(
      "[data-testid='gateway-legacy-methods']",
    ) as HTMLElement;
    expect(gatewayLegacyMethods.textContent).toContain("gateway/dispatch");
    const gatewayTransportContract = element.shadowRoot.querySelector(
      "[data-testid='gateway-transport-contract']",
    ) as HTMLElement;
    expect(gatewayTransportContract.textContent).toContain("mock / local only");
    const gatewayConnectErrors = element.shadowRoot.querySelector(
      "[data-testid='gateway-connect-errors']",
    ) as HTMLElement;
    expect(gatewayConnectErrors.textContent).toContain("已就绪");
    const gatewayConnectRecoveryHint = element.shadowRoot.querySelector(
      "[data-testid='gateway-connect-recovery-hint']",
    ) as HTMLElement;
    expect(gatewayConnectRecoveryHint.textContent).toContain("已 ready");
    const gatewayMethodDetail = element.shadowRoot.querySelector(
      "[data-testid='gateway-method-detail']",
    ) as HTMLElement;
    expect(gatewayMethodDetail.textContent).toContain("connect.initialize");
    const gatewayAuthConnectorSummary = element.shadowRoot.querySelector(
      "[data-testid='gateway-auth-connector-summary']",
    ) as HTMLElement;
    expect(gatewayAuthConnectorSummary.textContent).toContain("gateway=1, app=1");
    expect(gatewayAuthConnectorSummary.textContent).toContain("webhook=1, polling=0");
    expect(gatewayAuthConnectorSummary.textContent).toContain("approval=2, direct=0");
    const applySummary = element.shadowRoot.querySelector(
      "[data-testid='settings-apply-summary']",
    ) as HTMLElement;
    expect(applySummary.textContent).toContain("当前没有待应用配置");
    const diagnosticsSummary = element.shadowRoot.querySelector(
      "[data-testid='control-ui-diagnostics-summary']",
    ) as HTMLElement;
    expect(diagnosticsSummary.textContent).toContain("workflow=2");
    expect(diagnosticsSummary.textContent).toContain("paused=1");
    const logSourceSummary = element.shadowRoot.querySelector(
      "[data-testid='log-tail-source-summary']",
    ) as HTMLElement;
    expect(logSourceSummary.textContent).toContain("Gateway Audit Records");
    const logRouteCue = element.shadowRoot.querySelector(
      "[data-testid='settings-log-route-cue']",
    ) as HTMLElement;
    expect(logRouteCue.textContent).toContain("route=审批与审计");
    expect(logRouteCue.textContent).toContain("gateway audit records");
    const diagnosticsCues = element.shadowRoot.querySelector(
      "[data-testid='settings-diagnostics-cues']",
    ) as HTMLElement;
    expect(diagnosticsCues.textContent).toContain("Paused workflows present");
    expect(diagnosticsCues.textContent).toContain("Pending approvals present");
    expect(diagnosticsCues.textContent).toContain("Current log source");
    const probeInventory = element.shadowRoot.querySelector(
      "[data-testid='settings-probe-inventory']",
    ) as HTMLElement;
    expect(probeInventory.textContent).toContain("runtime");
    expect(probeInventory.textContent).toContain("gatewayStateStore");
    expect(probeInventory.textContent).toContain("browserControl");
    expect(probeInventory.textContent).toContain("tabCount=2");
    const snapshotInventory = element.shadowRoot.querySelector(
      "[data-testid='settings-snapshot-inventory']",
    ) as HTMLElement;
    expect(snapshotInventory.textContent).toContain("events");
    expect(snapshotInventory.textContent).toContain("workflowRuns");
    expect(snapshotInventory.textContent).toContain("approvalTickets");
    expect(snapshotInventory.textContent).toContain("connectors");
    const traceHotspots = element.shadowRoot.querySelector(
      "[data-testid='settings-trace-hotspots']",
    ) as HTMLElement;
    expect(traceHotspots.textContent).toContain("trace_demo_001");
    expect(traceHotspots.textContent).toContain("workflow=paused");
    expect(traceHotspots.textContent).toContain("pending approvals=1");
    const logRecords = element.shadowRoot.querySelector(
      "[data-testid='settings-log-records']",
    ) as HTMLElement;
    expect(logRecords.textContent).toContain("audit_demo_003");
    expect(logRecords.textContent).toContain("stage=execution");
    const logInventory = element.shadowRoot.querySelector(
      "[data-testid='settings-log-source-inventory']",
    ) as HTMLElement;
    expect(logInventory.textContent).toContain("Gateway Action Requests");
    expect(logInventory.textContent).toContain("Gateway Approval Tickets");
    expect(logInventory.textContent).toContain("Gateway Audit Records");
    expect(logInventory.textContent).toContain("Gateway Events");
    expect(logInventory.textContent).toContain("Gateway Workflow Runs");
    expect(logInventory.textContent).toContain("Active Thread Rollout");
    const logTail = element.shadowRoot.querySelector("[data-testid='gateway-log-tail']") as HTMLElement;
    expect(logTail.textContent).toContain("audit_demo_002");
  });

  it("dispatches route-change from settings log source next-hop", async () => {
    const routes: string[] = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.addEventListener("route-change", ((event: CustomEvent<string>) => {
      routes.push(event.detail);
    }) as EventListener);
    document.body.appendChild(element);
    await flushUi(element);

    const logSource = element.shadowRoot.querySelector(
      "[data-testid='settings-log-source-select']",
    ) as HTMLSelectElement;
    logSource.value = "thread.active_rollout";
    logSource.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);

    const logRouteCue = element.shadowRoot.querySelector(
      "[data-testid='settings-log-route-cue']",
    ) as HTMLElement;
    expect(logRouteCue.textContent).toContain("route=Sessions / Runs");
    const logRecords = element.shadowRoot.querySelector(
      "[data-testid='settings-log-records']",
    ) as HTMLElement;
    expect(logRecords.textContent).toContain("turn · thread_demo_001");
    expect(logRecords.textContent).toContain("gateway 状态已刷新");

    const openRoute = element.shadowRoot.querySelector(
      "[data-testid='settings-log-route-open']",
    ) as HTMLButtonElement;
    openRoute.click();

    expect(routes).toEqual(["sessions"]);
  });

  it("switches to gateway action requests log source and exposes approvals next-hop", async () => {
    const routes: string[] = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.addEventListener("route-change", ((event: CustomEvent<string>) => {
      routes.push(event.detail);
    }) as EventListener);
    document.body.appendChild(element);
    await flushUi(element);

    const logSource = element.shadowRoot.querySelector(
      "[data-testid='settings-log-source-select']",
    ) as HTMLSelectElement;
    logSource.value = "gateway.action_requests";
    logSource.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);

    const logRouteCue = element.shadowRoot.querySelector(
      "[data-testid='settings-log-route-cue']",
    ) as HTMLElement;
    expect(logRouteCue.textContent).toContain("route=审批与审计");
    expect(logRouteCue.textContent).toContain("gateway action requests");
    const logRecords = element.shadowRoot.querySelector(
      "[data-testid='settings-log-records']",
    ) as HTMLElement;
    expect(logRecords.textContent).toContain("action_demo_002");
    expect(logRecords.textContent).toContain("shell command action queued");

    const openRoute = element.shadowRoot.querySelector(
      "[data-testid='settings-log-route-open']",
    ) as HTMLButtonElement;
    openRoute.click();

    expect(routes).toEqual(["approvals"]);
  });

  it("switches log source from inventory quick select", async () => {
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const switchSource = element.shadowRoot.querySelector(
      "[data-testid='settings-log-source-select-thread.active_rollout']",
    ) as HTMLButtonElement;
    switchSource.click();
    await flushUi(element);

    const logRouteCue = element.shadowRoot.querySelector(
      "[data-testid='settings-log-route-cue']",
    ) as HTMLElement;
    expect(logRouteCue.textContent).toContain("route=Sessions / Runs");
    const logTail = element.shadowRoot.querySelector("[data-testid='gateway-log-tail']") as HTMLElement;
    expect(logTail.textContent).toContain("assistant_text");
  });

  it("replays pending log source refresh after an in-flight diagnostics load finishes", async () => {
    const adapter = new DelayedFirstLogTailAdapter();
    const element = document.createElement("settings-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(adapter);
    document.body.appendChild(element);
    await flushUi(element);
    await vi.waitFor(() => {
      expect(adapter.logTailSources).toEqual(["default"]);
    });

    adapter.pauseNextLogTail();
    const refreshButton = element.shadowRoot.querySelector(
      "[data-testid='settings-refresh-diagnostics']",
    ) as HTMLButtonElement;
    refreshButton.click();
    await flushUi(element);

    const logSource = element.shadowRoot.querySelector(
      "[data-testid='settings-log-source-select']",
    ) as HTMLSelectElement;
    logSource.value = "thread.active_rollout";
    logSource.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);

    adapter.releaseHeldLogTail();
    await flushUi(element);

    await vi.waitFor(() => {
      expect(adapter.logTailSources).toEqual(["default", "gateway.audit_records", "thread.active_rollout"]);
    });
    const logRouteCue = element.shadowRoot.querySelector(
      "[data-testid='settings-log-route-cue']",
    ) as HTMLElement;
    await vi.waitFor(() => {
      expect(logRouteCue.textContent).toContain("route=Sessions / Runs");
    });
  });

  it("dispatches route-change from log source inventory quick hop", async () => {
    const routes: string[] = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.addEventListener("route-change", ((event: CustomEvent<string>) => {
      routes.push(event.detail);
    }) as EventListener);
    document.body.appendChild(element);
    await flushUi(element);

    const openApprovals = element.shadowRoot.querySelector(
      "[data-testid='settings-log-source-open-gateway.audit_records']",
    ) as HTMLButtonElement;
    openApprovals.click();

    expect(routes).toEqual(["approvals"]);
  });

  it("dispatches route-change from settings diagnostics cues", async () => {
    const routes: string[] = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.addEventListener("route-change", ((event: CustomEvent<string>) => {
      routes.push(event.detail);
    }) as EventListener);
    document.body.appendChild(element);
    await flushUi(element);

    const openApprovals = element.shadowRoot.querySelector(
      "[data-testid='settings-diagnostics-cue-open-approvals']",
    ) as HTMLButtonElement;
    openApprovals.click();

    expect(routes).toEqual(["approvals"]);
  });

  it("dispatches route-change from probe inventory quick hop", async () => {
    const routes: string[] = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.addEventListener("route-change", ((event: CustomEvent<string>) => {
      routes.push(event.detail);
    }) as EventListener);
    document.body.appendChild(element);
    await flushUi(element);

    const openBrowser = element.shadowRoot.querySelector(
      "[data-testid='settings-probe-open-browserControl']",
    ) as HTMLButtonElement;
    openBrowser.click();

    expect(routes).toEqual(["browser"]);
  });

  it("prioritizes degraded probes and renders operator next-hop note", async () => {
    const client = new BridgeClient(new DegradedProbeSettingsAdapter());
    const element = document.createElement("settings-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);

    const probeItems = Array.from(
      element.shadowRoot.querySelectorAll("[data-testid^='settings-probe-item-']"),
    ) as HTMLElement[];
    expect(probeItems[0]?.textContent).toContain("browserControl");
    expect(probeItems[0]?.textContent).toContain("degraded");
    expect(probeItems[0]?.textContent).toContain("优先回浏览器控制面");
  });

  it("dispatches workflow control context from snapshot inventory", async () => {
    const events: Array<Record<string, unknown>> = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.addEventListener(
      "navigate-control-context",
      ((event: CustomEvent<Record<string, unknown>>) => {
        events.push(event.detail);
      }) as EventListener,
    );
    document.body.appendChild(element);
    await flushUi(element);

    const openSessions = element.shadowRoot.querySelector(
      "[data-testid='settings-snapshot-open-workflowRuns']",
    ) as HTMLButtonElement;
    openSessions.click();

    expect(events).toEqual([
      {
        route: "sessions",
        traceId: "trace_demo_001",
        workflowRunId: "run_1",
        timelineScope: "workflowRuns",
        source: "settings-diagnostics",
      },
    ]);
  });

  it("dispatches approvals control context from snapshot inventory", async () => {
    const events: Array<Record<string, unknown>> = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.addEventListener(
      "navigate-control-context",
      ((event: CustomEvent<Record<string, unknown>>) => {
        events.push(event.detail);
      }) as EventListener,
    );
    document.body.appendChild(element);
    await flushUi(element);

    const openApprovals = element.shadowRoot.querySelector(
      "[data-testid='settings-snapshot-open-approvalTickets']",
    ) as HTMLButtonElement;
    openApprovals.click();

    expect(events).toEqual([
      {
        route: "approvals",
        traceId: "trace_demo_001",
        approvalId: "approval_demo_001",
        source: "settings-diagnostics",
      },
    ]);
  });

  it("dispatches plugins connector context from snapshot inventory", async () => {
    const events: Array<Record<string, unknown>> = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.addEventListener(
      "navigate-control-context",
      ((event: CustomEvent<Record<string, unknown>>) => {
        events.push(event.detail);
      }) as EventListener,
    );
    document.body.appendChild(element);
    await flushUi(element);

    const openPlugins = element.shadowRoot.querySelector(
      "[data-testid='settings-snapshot-open-connectors']",
    ) as HTMLButtonElement;
    openPlugins.click();

    expect(events).toEqual([
      {
        route: "plugins",
        connectorKey: "github_webhook",
        connectorFilter: "gateway",
        source: "settings-diagnostics",
      },
    ]);
  });

  it("dispatches control context from trace hotspots", async () => {
    const events: Array<Record<string, unknown>> = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.addEventListener(
      "navigate-control-context",
      ((event: CustomEvent<Record<string, unknown>>) => {
        events.push(event.detail);
      }) as EventListener,
    );
    document.body.appendChild(element);
    await flushUi(element);

    const openWorkflow = element.shadowRoot.querySelector(
      "[data-testid='settings-trace-hotspot-open-workflow-trace_demo_001']",
    ) as HTMLButtonElement;
    openWorkflow.click();
    const openApprovals = element.shadowRoot.querySelector(
      "[data-testid='settings-trace-hotspot-open-approvals-trace_demo_001']",
    ) as HTMLButtonElement;
    openApprovals.click();

    expect(events).toHaveLength(2);
    expect(events[0]).toMatchObject({
      route: "sessions",
      traceId: "trace_demo_001",
      workflowRunId: "run_1",
      timelineScope: "workflowRuns",
      source: "settings-diagnostics",
    });
    expect(events[1]).toMatchObject({
      route: "approvals",
      traceId: "trace_demo_001",
      approvalId: "approval_demo_001",
      source: "settings-diagnostics",
    });
  });

  it("dispatches approvals control context from parsed audit log records", async () => {
    const events: Array<Record<string, unknown>> = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.addEventListener(
      "navigate-control-context",
      ((event: CustomEvent<Record<string, unknown>>) => {
        events.push(event.detail);
      }) as EventListener,
    );
    document.body.appendChild(element);
    await flushUi(element);

    const openRecord = element.shadowRoot.querySelector(
      "[data-testid='settings-log-record-open-0']",
    ) as HTMLButtonElement;
    openRecord.click();

    expect(events).toEqual([
      {
        route: "approvals",
        traceId: "trace_demo_002",
        actionId: "action_demo_002",
        auditId: "audit_demo_003",
        source: "settings-diagnostics",
      },
    ]);
  });

  it("dispatches approvals control context from action request log records", async () => {
    const events: Array<Record<string, unknown>> = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.addEventListener(
      "navigate-control-context",
      ((event: CustomEvent<Record<string, unknown>>) => {
        events.push(event.detail);
      }) as EventListener,
    );
    document.body.appendChild(element);
    await flushUi(element);

    const logSource = element.shadowRoot.querySelector(
      "[data-testid='settings-log-source-select']",
    ) as HTMLSelectElement;
    logSource.value = "gateway.action_requests";
    logSource.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);

    const openRecord = element.shadowRoot.querySelector(
      "[data-testid='settings-log-record-open-0']",
    ) as HTMLButtonElement;
    openRecord.click();

    expect(events).toEqual([
      {
        route: "approvals",
        traceId: "trace_demo_002",
        actionId: "action_demo_002",
        source: "settings-diagnostics",
      },
    ]);
  });

  it("dispatches approvals control context from approval ticket log records", async () => {
    const events: Array<Record<string, unknown>> = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.addEventListener(
      "navigate-control-context",
      ((event: CustomEvent<Record<string, unknown>>) => {
        events.push(event.detail);
      }) as EventListener,
    );
    document.body.appendChild(element);
    await flushUi(element);

    const logSource = element.shadowRoot.querySelector(
      "[data-testid='settings-log-source-select']",
    ) as HTMLSelectElement;
    logSource.value = "gateway.approval_tickets";
    logSource.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);

    const openRecord = element.shadowRoot.querySelector(
      "[data-testid='settings-log-record-open-0']",
    ) as HTMLButtonElement;
    openRecord.click();

    expect(events).toEqual([
      {
        route: "approvals",
        traceId: "trace_demo_002",
        approvalId: "approval_demo_002",
        actionId: "action_demo_002",
        source: "settings-diagnostics",
      },
    ]);
  });

  it("dispatches sessions control context from rollout log records when trace metadata exists", async () => {
    const events: Array<Record<string, unknown>> = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.addEventListener(
      "navigate-control-context",
      ((event: CustomEvent<Record<string, unknown>>) => {
        events.push(event.detail);
      }) as EventListener,
    );
    document.body.appendChild(element);
    await flushUi(element);

    const logSource = element.shadowRoot.querySelector(
      "[data-testid='settings-log-source-select']",
    ) as HTMLSelectElement;
    logSource.value = "thread.active_rollout";
    logSource.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);

    const openRecord = element.shadowRoot.querySelector(
      "[data-testid='settings-log-record-open-0']",
    ) as HTMLButtonElement;
    openRecord.click();

    expect(events).toEqual([
      {
        route: "sessions",
        traceId: "trace_demo_001",
        workflowRunId: "run_1",
        timelineScope: "workflowRuns",
        source: "settings-diagnostics",
      },
    ]);
  });

  it("parses nested live rollout turn records into sessions control context", async () => {
    const events: Array<Record<string, unknown>> = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(new NestedRolloutLogAdapter());
    element.addEventListener(
      "navigate-control-context",
      ((event: CustomEvent<Record<string, unknown>>) => {
        events.push(event.detail);
      }) as EventListener,
    );
    document.body.appendChild(element);
    await flushUi(element);

    const logSource = element.shadowRoot.querySelector(
      "[data-testid='settings-log-source-select']",
    ) as HTMLSelectElement;
    logSource.value = "thread.active_rollout";
    logSource.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);

    const logRecords = element.shadowRoot.querySelector(
      "[data-testid='settings-log-records']",
    ) as HTMLElement;
    expect(logRecords.textContent).toContain("workflow 已进入等待审批状态");

    const openRecord = element.shadowRoot.querySelector(
      "[data-testid='settings-log-record-open-0']",
    ) as HTMLButtonElement;
    openRecord.click();

    expect(events).toEqual([
      {
        route: "sessions",
        traceId: "trace_live_nested",
        workflowRunId: "run_live_nested",
        timelineScope: "workflowRuns",
        source: "settings-diagnostics",
      },
    ]);
  });

  it("dispatches sessions control context from gateway event log records", async () => {
    const events: Array<Record<string, unknown>> = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.addEventListener(
      "navigate-control-context",
      ((event: CustomEvent<Record<string, unknown>>) => {
        events.push(event.detail);
      }) as EventListener,
    );
    document.body.appendChild(element);
    await flushUi(element);

    const logSource = element.shadowRoot.querySelector(
      "[data-testid='settings-log-source-select']",
    ) as HTMLSelectElement;
    logSource.value = "gateway.events";
    logSource.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);

    const logRouteCue = element.shadowRoot.querySelector(
      "[data-testid='settings-log-route-cue']",
    ) as HTMLElement;
    expect(logRouteCue.textContent).toContain("route=Sessions / Runs");

    const openRecord = element.shadowRoot.querySelector(
      "[data-testid='settings-log-record-open-0']",
    ) as HTMLButtonElement;
    openRecord.click();

    expect(events).toEqual([
      {
        route: "sessions",
        traceId: "trace_demo_002",
        workflowRunId: "run_2",
        timelineScope: "workflowRuns",
        source: "settings-diagnostics",
      },
    ]);
  });

  it("dispatches sessions control context from workflow run log records", async () => {
    const events: Array<Record<string, unknown>> = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.addEventListener(
      "navigate-control-context",
      ((event: CustomEvent<Record<string, unknown>>) => {
        events.push(event.detail);
      }) as EventListener,
    );
    document.body.appendChild(element);
    await flushUi(element);

    const logSource = element.shadowRoot.querySelector(
      "[data-testid='settings-log-source-select']",
    ) as HTMLSelectElement;
    logSource.value = "gateway.workflow_runs";
    logSource.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);

    const openRecord = element.shadowRoot.querySelector(
      "[data-testid='settings-log-record-open-0']",
    ) as HTMLButtonElement;
    openRecord.click();

    expect(events).toEqual([
      {
        route: "sessions",
        traceId: "trace_demo_002",
        workflowRunId: "run_2",
        timelineScope: "workflowRuns",
        source: "settings-diagnostics",
      },
    ]);
  });

  it("renders auth-only mode without config apply and diagnostics blocks", async () => {
    const element = document.createElement("settings-page") as HTMLElement & {
      surfaceMode?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.surfaceMode = "auth";
    document.body.appendChild(element);
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("Gateway Auth / Scope / Connect");
    expect(element.shadowRoot.querySelector("[data-testid='gateway-auth-methods']")).toBeTruthy();
    expect(element.shadowRoot.querySelector("[data-testid='settings-apply-summary']")).toBeNull();
    expect(element.shadowRoot.querySelector("[data-testid='control-ui-diagnostics-summary']")).toBeNull();
    const refreshMeta = element.shadowRoot.querySelector(
      "[data-testid='auth-surface-refresh-meta']",
    ) as HTMLElement;
    expect(refreshMeta.textContent).toContain("connect=");
    const refreshButton = element.shadowRoot.querySelector(
      "[data-testid='settings-refresh-diagnostics']",
    ) as HTMLButtonElement;
    expect(refreshButton).toBeTruthy();
    const routeMappings = element.shadowRoot.querySelector(
      "[data-testid='gateway-route-mappings']",
    ) as HTMLElement;
    expect(routeMappings.textContent).toContain("Family -> Route Mapping");
    expect(routeMappings.textContent).toContain("access");
    const connectorSummary = element.shadowRoot.querySelector(
      "[data-testid='gateway-auth-connector-summary']",
    ) as HTMLElement;
    expect(connectorSummary.textContent).toContain("gateway=1, app=1");
    const channelSummary = element.shadowRoot.querySelector(
      "[data-testid='gateway-auth-channel-summary']",
    ) as HTMLElement;
    expect(channelSummary.textContent).toContain("webhook=1");
    expect(channelSummary.textContent).toContain("polling=0");
    expect(channelSummary.textContent).toContain("actions=2");
    expect(channelSummary.textContent).toContain("event types=2");
    expect(channelSummary.textContent).toContain("action types=3");
    const accessPosture = element.shadowRoot.querySelector(
      "[data-testid='gateway-access-posture-summary']",
    ) as HTMLElement;
    expect(accessPosture.textContent).toContain("local-only");
    expect(accessPosture.textContent).toContain("trusted_local");
    expect(accessPosture.textContent).toContain("roles=operator");
    expect(accessPosture.textContent).toContain("pendingPairing=1");
    expect(accessPosture.textContent).toContain("pendingRefs=1");
    const connectorDetail = element.shadowRoot.querySelector(
      "[data-testid='gateway-auth-connector-detail']",
    ) as HTMLElement;
    expect(connectorDetail.textContent).toContain("GitHub Webhook");
    expect(connectorDetail.textContent).toContain("approval=required");
    const operatorCues = element.shadowRoot.querySelector(
      "[data-testid='gateway-auth-operator-cues']",
    ) as HTMLElement;
    expect(operatorCues.textContent).toContain("Gateway connect ready");
    expect(operatorCues.textContent).toContain("Approval path present");
    expect(operatorCues.textContent).toContain("Ingress channels visible");
    expect(operatorCues.textContent).toContain("Control-plane writes exposed");
    const diagnosticsSummary = element.shadowRoot.querySelector(
      "[data-testid='gateway-auth-diagnostics-summary']",
    ) as HTMLElement;
    expect(diagnosticsSummary.textContent).toContain("3/3 probes ok");
    expect(diagnosticsSummary.textContent).toContain("workflow=2");
    expect(diagnosticsSummary.textContent).toContain("pending=2");
    expect(diagnosticsSummary.textContent).toContain("Gateway Audit Records");
  });

  it("renders config-only mode without auth and diagnostics blocks", async () => {
    const element = document.createElement("settings-page") as HTMLElement & {
      surfaceMode?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.surfaceMode = "config";
    document.body.appendChild(element);
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("Config / Policy / Apply");
    expect(element.shadowRoot.querySelector("[data-testid='settings-apply-summary']")).toBeTruthy();
    expect(element.shadowRoot.querySelector("[data-testid='settings-config-console']")).toBeTruthy();
    expect(element.shadowRoot.querySelector("[data-testid='gateway-auth-methods']")).toBeNull();
    expect(element.shadowRoot.querySelector("[data-testid='control-ui-diagnostics-summary']")).toBeNull();
    expect(element.shadowRoot.querySelector("[data-testid='settings-log-source-inventory']")).toBeNull();
  });

  it("renders debug-only mode without config apply and auth blocks", async () => {
    const element = document.createElement("settings-page") as HTMLElement & {
      surfaceMode?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.surfaceMode = "debug";
    document.body.appendChild(element);
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("Debug / Diagnostics / Trace");
    expect(element.shadowRoot.querySelector("[data-testid='settings-debug-console']")).toBeTruthy();
    expect(element.shadowRoot.querySelector("[data-testid='control-ui-diagnostics-summary']")).toBeTruthy();
    expect(element.shadowRoot.querySelector("[data-testid='gateway-auth-methods']")).toBeNull();
    expect(element.shadowRoot.querySelector("[data-testid='settings-apply-summary']")).toBeNull();
    expect(element.shadowRoot.querySelector("[data-testid='runtime-environment-summary']")).toBeNull();
  });

  it("renders pairing pending refs from access posture contract in auth surface", async () => {
    const element = document.createElement("settings-page") as HTMLElement & {
      surfaceMode?: string;
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.surfaceMode = "auth";
    element.bridgeClient = new BridgeClient(new AccessPosturePendingRefsAdapter());
    document.body.appendChild(element);
    await flushUi(element);

    const refs = element.shadowRoot.querySelector(
      "[data-testid='gateway-access-posture-pending-refs']",
    ) as HTMLElement;
    expect(refs.textContent).toContain("Remote device pairing request");
    expect(refs.textContent).toContain("Approval-only pairing ref");
    expect(refs.textContent).toContain("action=pairing.request");
    expect(refs.textContent).toContain("approval=approval_demo_001");
    expect(refs.textContent).toContain("trace=trace_demo_001");
  });

  it("dispatches control context from access posture pairing refs with trace metadata", async () => {
    const contexts: Array<Record<string, unknown>> = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      surfaceMode?: string;
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.surfaceMode = "auth";
    element.bridgeClient = new BridgeClient(new AccessPosturePendingRefsAdapter());
    element.addEventListener("navigate-control-context", ((event: CustomEvent<Record<string, unknown>>) => {
      contexts.push(event.detail);
    }) as EventListener);
    document.body.appendChild(element);
    await flushUi(element);

    const openRef = element.shadowRoot.querySelector(
      "[data-testid='gateway-access-posture-ref-open-approvals-approval_demo_001']",
    ) as HTMLButtonElement;
    openRef.click();

    expect(contexts).toEqual([
      {
        route: "approvals",
        traceId: "trace_demo_001",
        approvalId: "approval_demo_001",
        source: "settings-access-posture",
      },
    ]);
  });

  it("dispatches sessions control context from access posture pairing refs", async () => {
    const contexts: Array<Record<string, unknown>> = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      surfaceMode?: string;
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.surfaceMode = "auth";
    element.bridgeClient = new BridgeClient(new AccessPosturePendingRefsAdapter());
    element.addEventListener("navigate-control-context", ((event: CustomEvent<Record<string, unknown>>) => {
      contexts.push(event.detail);
    }) as EventListener);
    document.body.appendChild(element);
    await flushUi(element);

    const openRef = element.shadowRoot.querySelector(
      "[data-testid='gateway-access-posture-ref-open-sessions-approval_demo_001']",
    ) as HTMLButtonElement;
    openRef.click();

    expect(contexts).toEqual([
      {
        route: "sessions",
        traceId: "trace_demo_001",
        timelineScope: "approvalTickets",
        source: "settings-access-posture",
      },
    ]);
  });

  it("falls back to route-change for access posture pairing refs without trace", async () => {
    const routes: string[] = [];
    const contexts: Array<Record<string, unknown>> = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      surfaceMode?: string;
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.surfaceMode = "auth";
    element.bridgeClient = new BridgeClient(new AccessPosturePendingRefsAdapter());
    element.addEventListener("route-change", ((event: CustomEvent<string>) => {
      routes.push(event.detail);
    }) as EventListener);
    element.addEventListener("navigate-control-context", ((event: CustomEvent<Record<string, unknown>>) => {
      contexts.push(event.detail);
    }) as EventListener);
    document.body.appendChild(element);
    await flushUi(element);

    const openRef = element.shadowRoot.querySelector(
      "[data-testid='gateway-access-posture-ref-open-approvals-approval_route_only']",
    ) as HTMLButtonElement;
    openRef.click();

    expect(routes).toEqual(["approvals"]);
    expect(contexts).toEqual([]);
  });

  it("dispatches route-change from auth route mappings", async () => {
    const routes: string[] = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      surfaceMode?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.surfaceMode = "auth";
    element.addEventListener("route-change", ((event: CustomEvent<string>) => {
      routes.push(event.detail);
    }) as EventListener);
    document.body.appendChild(element);
    await flushUi(element);

    const openBrowser = element.shadowRoot.querySelector(
      "[data-testid='gateway-route-open-browser']",
    ) as HTMLButtonElement;
    openBrowser.click();

    expect(routes).toEqual(["browser"]);
  });

  it("dispatches route-change from auth operator cues", async () => {
    const routes: string[] = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      surfaceMode?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.surfaceMode = "auth";
    element.addEventListener("route-change", ((event: CustomEvent<string>) => {
      routes.push(event.detail);
    }) as EventListener);
    document.body.appendChild(element);
    await flushUi(element);

    const openApprovals = element.shadowRoot.querySelector(
      "[data-testid='gateway-auth-cue-open-approvals']",
    ) as HTMLButtonElement;
    openApprovals.click();

    expect(routes).toEqual(["approvals"]);
  });

  it("dispatches route-change from auth diagnostics summary", async () => {
    const routes: string[] = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      surfaceMode?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.surfaceMode = "auth";
    element.addEventListener("route-change", ((event: CustomEvent<string>) => {
      routes.push(event.detail);
    }) as EventListener);
    document.body.appendChild(element);
    await flushUi(element);

    const openSessions = element.shadowRoot.querySelector(
      "[data-testid='gateway-auth-open-sessions']",
    ) as HTMLButtonElement;
    openSessions.click();

    expect(routes).toEqual(["sessions"]);
  });

  it("filters auth connectors and dispatches plugins control context from connector detail", async () => {
    const routes: Array<Record<string, string>> = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      surfaceMode?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.surfaceMode = "auth";
    element.addEventListener("navigate-control-context", ((event: CustomEvent<Record<string, string>>) => {
      routes.push(event.detail);
    }) as EventListener);
    document.body.appendChild(element);
    await flushUi(element);

    const ingressFilter = element.shadowRoot.querySelector(
      "[data-testid='gateway-auth-connector-filter-ingress']",
    ) as HTMLButtonElement;
    ingressFilter.click();
    await flushUi(element);

    const connectorList = element.shadowRoot.querySelector(
      "[data-testid='gateway-auth-connector-list']",
    ) as HTMLElement;
    expect(connectorList.textContent).toContain("GitHub Webhook");
    expect(connectorList.textContent).not.toContain("GitHub Dispatch");

    const openPlugins = element.shadowRoot.querySelector(
      "[data-testid='gateway-auth-connector-open-plugins']",
    ) as HTMLButtonElement;
    openPlugins.click();

    expect(routes).toEqual([
      {
        route: "plugins",
        connectorKey: "github_webhook",
        connectorFilter: "gateway",
        source: "settings-auth-connectors",
      },
    ]);
  });

  it("filters auth connectors by webhook channel posture", async () => {
    const element = document.createElement("settings-page") as HTMLElement & {
      surfaceMode?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.surfaceMode = "auth";
    document.body.appendChild(element);
    await flushUi(element);

    const webhookFilter = element.shadowRoot.querySelector(
      "[data-testid='gateway-auth-connector-filter-webhook']",
    ) as HTMLButtonElement;
    webhookFilter.click();
    await flushUi(element);

    const connectorList = element.shadowRoot.querySelector(
      "[data-testid='gateway-auth-connector-list']",
    ) as HTMLElement;
    expect(connectorList.textContent).toContain("GitHub Webhook");
    expect(connectorList.textContent).not.toContain("GitHub Dispatch");
    const connectorDetail = element.shadowRoot.querySelector(
      "[data-testid='gateway-auth-connector-detail']",
    ) as HTMLElement;
    expect(connectorDetail.textContent).toContain("GitHub Webhook");
  });

  it("dispatches settings control context from auth connector detail", async () => {
    const routes: Array<Record<string, string>> = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      surfaceMode?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.surfaceMode = "auth";
    element.addEventListener("navigate-control-context", ((event: CustomEvent<Record<string, string>>) => {
      routes.push(event.detail);
    }) as EventListener);
    document.body.appendChild(element);
    await flushUi(element);

    const openSettings = element.shadowRoot.querySelector(
      "[data-testid='gateway-auth-connector-open-settings']",
    ) as HTMLButtonElement;
    openSettings.click();

    expect(routes).toEqual([
      {
        route: "settings",
        connectorKey: "github_webhook",
        connectorFilter: "gateway",
        source: "settings-auth-connectors",
      },
    ]);
  });

  it("dispatches approvals landing context from auth connector detail", async () => {
    const routes: Array<Record<string, string>> = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      surfaceMode?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.surfaceMode = "auth";
    element.addEventListener("navigate-control-context", ((event: CustomEvent<Record<string, string>>) => {
      routes.push(event.detail);
    }) as EventListener);
    document.body.appendChild(element);
    await flushUi(element);

    const openApprovals = element.shadowRoot.querySelector(
      "[data-testid='gateway-auth-connector-open-approvals']",
    ) as HTMLButtonElement;
    openApprovals.click();

    expect(routes).toEqual([
      {
        route: "approvals",
        connectorKey: "github_webhook",
        source: "settings-auth-connectors",
      },
    ]);
  });

  it("honors auth connector route context from plugins surface", async () => {
    const element = document.createElement("settings-page") as HTMLElement & {
      surfaceMode?: string;
      initialAuthConnectorKey?: string;
      initialAuthConnectorFilter?: string;
      initialContextSource?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.surfaceMode = "auth";
    element.initialAuthConnectorKey = "github_dispatch";
    element.initialAuthConnectorFilter = "approval";
    element.initialContextSource = "plugins-connectors";
    document.body.appendChild(element);
    await flushUi(element);

    const approvalFilter = element.shadowRoot.querySelector(
      "[data-testid='gateway-auth-connector-filter-approval']",
    ) as HTMLButtonElement;
    expect(approvalFilter.className).toContain("active");
    const banner = element.shadowRoot.querySelector("[data-testid='settings-context-banner']") as HTMLElement;
    expect(banner.textContent).toContain("handoff=plugins-connectors");
    const connectorDetail = element.shadowRoot.querySelector(
      "[data-testid='gateway-auth-connector-detail']",
    ) as HTMLElement;
    expect(connectorDetail.textContent).toContain("GitHub Dispatch");
    expect(connectorDetail.textContent).toContain("approval=required");
  });

  it("updates and saves runtime settings", async () => {
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const approvalSelect = element.shadowRoot.querySelectorAll(
      "select",
    )[0] as HTMLSelectElement;
    approvalSelect.value = "never";
    approvalSelect.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    const pluginAutoLoadCheckbox = element.shadowRoot.querySelectorAll(
      'input[type="checkbox"]',
    )[1] as HTMLInputElement;
    pluginAutoLoadCheckbox.checked = false;
    pluginAutoLoadCheckbox.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);

    const applySummary = element.shadowRoot.querySelector(
      "[data-testid='settings-apply-summary']",
    ) as HTMLElement;
    expect(applySummary.textContent).toContain("restart impact");
    const restartSummary = element.shadowRoot.querySelector(
      "[data-testid='settings-restart-summary']",
    ) as HTMLElement;
    expect(restartSummary.textContent).toContain("pluginAutoLoad");
    const validateContractSummary = element.shadowRoot.querySelector(
      "[data-testid='settings-validate-contract-summary']",
    ) as HTMLElement;
    expect(validateContractSummary.textContent).toContain("config.validate 可显式调用");
    const restartContractSummary = element.shadowRoot.querySelector(
      "[data-testid='settings-restart-contract-summary']",
    ) as HTMLElement;
    expect(restartContractSummary.textContent).toContain("config.restart.report 可显式调用");
    const applyPathSummary = element.shadowRoot.querySelector(
      "[data-testid='settings-apply-path-summary']",
    ) as HTMLElement;
    expect(applyPathSummary.textContent).toContain("runtime.configure_runtime_policy");
    expect(applyPathSummary.textContent).toContain("GUI runtime flags");

    const saveButton = element.shadowRoot.querySelector("[data-testid='settings-save']") as HTMLButtonElement;
    expect(saveButton.disabled).toBe(false);
    saveButton.click();
    await flushUi(element);

    await vi.waitFor(async () => {
      expect(await feedbackText(element.shadowRoot)).toContain("建议在相关运行面重启后确认");
    });
    const policySummary = element.shadowRoot.querySelector(
      "[data-testid='runtime-policy-summary']",
    ) as HTMLElement;
    expect(policySummary.textContent).toContain("approval=never");
  });

  it("runs explicit config.validate and updates remote summaries", async () => {
    const adapter = new CapturingSettingsUpdateAdapter();
    const element = document.createElement("settings-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(adapter);
    document.body.appendChild(element);
    await flushUi(element);

    const pluginAutoLoadCheckbox = element.shadowRoot.querySelectorAll(
      'input[type="checkbox"]',
    )[1] as HTMLInputElement;
    pluginAutoLoadCheckbox.checked = false;
    pluginAutoLoadCheckbox.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);

    const validateButton = element.shadowRoot.querySelector("[data-testid='settings-validate']") as HTMLButtonElement;
    validateButton.click();
    await flushUi(element);

    expect(adapter.lastConfigValidatePayload).toMatchObject({
      pluginAutoLoad: false,
    });
    const remoteValidateSummary = element.shadowRoot.querySelector(
      "[data-testid='settings-remote-validate-summary']",
    ) as HTMLElement;
    expect(remoteValidateSummary.textContent).toContain("changed=1");
    expect(remoteValidateSummary.textContent).toContain("applyable=1");
    const remoteRestartSummary = element.shadowRoot.querySelector(
      "[data-testid='settings-remote-restart-report-summary']",
    ) as HTMLElement;
    expect(remoteRestartSummary.textContent).toContain("required=yes");
    expect(await feedbackText(element.shadowRoot)).toContain("config.validate 已返回");
  });

  it("runs explicit config.restart.report and shows manual restart posture", async () => {
    const adapter = new CapturingSettingsUpdateAdapter();
    const element = document.createElement("settings-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(adapter);
    document.body.appendChild(element);
    await flushUi(element);

    const pluginAutoLoadCheckbox = element.shadowRoot.querySelectorAll(
      'input[type="checkbox"]',
    )[1] as HTMLInputElement;
    pluginAutoLoadCheckbox.checked = false;
    pluginAutoLoadCheckbox.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);

    const restartReportButton = element.shadowRoot.querySelector(
      "[data-testid='settings-restart-report']",
    ) as HTMLButtonElement;
    restartReportButton.click();
    await flushUi(element);

    expect(adapter.lastConfigRestartReportPayload).toMatchObject({
      pluginAutoLoad: false,
    });
    const remoteRestartSummary = element.shadowRoot.querySelector(
      "[data-testid='settings-remote-restart-report-summary']",
    ) as HTMLElement;
    expect(remoteRestartSummary.textContent).toContain("required=yes");
    expect(remoteRestartSummary.textContent).toContain("mode=manual");
    await expect(feedbackText(element.shadowRoot)).resolves.toContain("config.restart.report: manual");
  });

  it("blocks unsupported config changes from apply", async () => {
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const modelInput = element.shadowRoot.querySelectorAll('input[type="text"]')[0] as HTMLInputElement;
    modelInput.value = "glm-5";
    modelInput.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    await flushUi(element);

    const blockedSummary = element.shadowRoot.querySelector(
      "[data-testid='settings-blocked-summary']",
    ) as HTMLElement;
    expect(blockedSummary.textContent).toContain("model");
    const validationMessages = element.shadowRoot.querySelector(
      "[data-testid='settings-validation-messages']",
    ) as HTMLElement;
    expect(validationMessages.textContent).toContain("provider/model");
    const saveButton = element.shadowRoot.querySelector("[data-testid='settings-save']") as HTMLButtonElement;
    expect(saveButton.disabled).toBe(true);
  });

  it("applies supported subset and retains unsupported draft fields", async () => {
    const adapter = new CapturingSettingsUpdateAdapter();
    const client = new BridgeClient(adapter);
    const element = document.createElement("settings-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);

    const modelInput = element.shadowRoot.querySelectorAll('input[type="text"]')[0] as HTMLInputElement;
    modelInput.value = "glm-5";
    modelInput.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    const pluginAutoLoadCheckbox = element.shadowRoot.querySelectorAll(
      'input[type="checkbox"]',
    )[1] as HTMLInputElement;
    pluginAutoLoadCheckbox.checked = false;
    pluginAutoLoadCheckbox.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);

    const applySummary = element.shadowRoot.querySelector(
      "[data-testid='settings-apply-summary']",
    ) as HTMLElement;
    expect(applySummary.textContent).toContain("部分应用");
    const saveButton = element.shadowRoot.querySelector("[data-testid='settings-save']") as HTMLButtonElement;
    expect(saveButton.disabled).toBe(false);
    expect(saveButton.textContent).toContain("应用支持字段");

    saveButton.click();
    await flushUi(element);

    expect(adapter.lastConfigApplyPayload).toMatchObject({
      model: "glm-5",
      pluginAutoLoad: false,
    });
    await expect(feedbackText(element.shadowRoot)).resolves.toContain("以下字段仍未应用并保留在本地草稿：model");
    await expect(feedbackText(element.shadowRoot)).resolves.toContain("pluginAutoLoad 变更");
    expect(modelInput.value).toBe("glm-5");
    expect(pluginAutoLoadCheckbox.checked).toBe(false);
    expect(saveButton.disabled).toBe(true);
  });

  it("renders error feedback when settings bridge fails", async () => {
    const client = new BridgeClient(new FailingSettingsAdapter());
    const element = document.createElement("settings-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);

    await expect(feedbackText(element.shadowRoot)).resolves.toContain("error");
    await expect(feedbackText(element.shadowRoot)).resolves.toContain("settings backend unavailable");

    const saveButton = element.shadowRoot.querySelector("[data-testid='settings-save']") as HTMLButtonElement;
    saveButton.click();
    await flushUi(element);

    await expect(feedbackText(element.shadowRoot)).resolves.toContain(
      "settings backend unavailable",
    );
  });

  it("degrades gateway connect surface when connect methods fail", async () => {
    const client = new BridgeClient(new FailingGatewayConnectAdapter());
    const element = document.createElement("settings-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);

    const gatewayConnectSummary = element.shadowRoot.querySelector(
      "[data-testid='gateway-connect-summary']",
    ) as HTMLElement;
    expect(gatewayConnectSummary.textContent).toContain("degraded");
    expect(gatewayConnectSummary.textContent).toContain("none");
    const gatewayConnectErrors = element.shadowRoot.querySelector(
      "[data-testid='gateway-connect-errors']",
    ) as HTMLElement;
    expect(gatewayConnectErrors.textContent).toContain("connect.initialize unavailable");
    expect(gatewayConnectErrors.textContent).toContain("connect.capabilities unavailable");
    expect(gatewayConnectErrors.textContent).toContain("connect.ping unavailable");
    const gatewayMethodList = element.shadowRoot.querySelector(
      "[data-testid='gateway-method-list']",
    ) as HTMLElement;
    expect(gatewayMethodList.textContent).toContain("当前筛选下没有 method");
    const gatewayTransportContract = element.shadowRoot.querySelector(
      "[data-testid='gateway-transport-contract']",
    ) as HTMLElement;
    expect(gatewayTransportContract.textContent).toContain("mock / local only");
    const gatewayConnectRecoveryHint = element.shadowRoot.querySelector(
      "[data-testid='gateway-connect-recovery-hint']",
    ) as HTMLElement;
    expect(gatewayConnectRecoveryHint.textContent).toContain("检查 bridge/gateway 可达性");
  });

  it("keeps method metadata visible when ping is degraded", async () => {
    const client = new BridgeClient(new PartialPingFailureAdapter());
    const element = document.createElement("settings-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);

    const gatewayConnectSummary = element.shadowRoot.querySelector(
      "[data-testid='gateway-connect-summary']",
    ) as HTMLElement;
    expect(gatewayConnectSummary.textContent).toContain("partial");
    expect(gatewayConnectSummary.textContent).toContain("degraded");
    expect(gatewayConnectSummary.textContent).toContain("connect.capabilities");
    const gatewayConnectErrors = element.shadowRoot.querySelector(
      "[data-testid='gateway-connect-errors']",
    ) as HTMLElement;
    expect(gatewayConnectErrors.textContent).toContain("connect.ping unavailable");
    const gatewayConnectRecoveryHint = element.shadowRoot.querySelector(
      "[data-testid='gateway-connect-recovery-hint']",
    ) as HTMLElement;
    expect(gatewayConnectRecoveryHint.textContent).toContain("auth/method metadata 仍可用");
    const gatewayMethodList = element.shadowRoot.querySelector(
      "[data-testid='gateway-method-list']",
    ) as HTMLElement;
    expect(gatewayMethodList.textContent).toContain("browser.proxy");
    expect(gatewayMethodList.textContent).toContain("approvals.resolve");
  });

  it("recovers from capabilities fallback after manual refresh", async () => {
    const client = new BridgeClient(new RecoveringGatewayCapabilitiesAdapter());
    const element = document.createElement("settings-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);

    const gatewayConnectSummary = element.shadowRoot.querySelector(
      "[data-testid='gateway-connect-summary']",
    ) as HTMLElement;
    expect(gatewayConnectSummary.textContent).toContain("partial");
    expect(gatewayConnectSummary.textContent).toContain("connect.initialize fallback");
    const gatewayConnectErrors = element.shadowRoot.querySelector(
      "[data-testid='gateway-connect-errors']",
    ) as HTMLElement;
    expect(gatewayConnectErrors.textContent).toContain("connect.capabilities unavailable");
    const gatewayConnectRecoveryHint = element.shadowRoot.querySelector(
      "[data-testid='gateway-connect-recovery-hint']",
    ) as HTMLElement;
    expect(gatewayConnectRecoveryHint.textContent).toContain("回退到 connect.initialize");

    const refreshButton = element.shadowRoot.querySelector(
      "[data-testid='settings-refresh-diagnostics']",
    ) as HTMLButtonElement;
    refreshButton.click();
    await flushUi(element);

    expect(gatewayConnectSummary.textContent).toContain("ready");
    expect(gatewayConnectSummary.textContent).toContain("connect.capabilities");
    expect(gatewayConnectErrors.textContent).toContain("已就绪");
    expect(gatewayConnectErrors.textContent).not.toContain("connect.capabilities unavailable");
    expect(gatewayConnectRecoveryHint.textContent).toContain("已 ready");
  });

  it("auto refreshes diagnostics while enabled", async () => {
    vi.useFakeTimers();
    const adapter = new DiagnosticsSettingsAdapter();
    const client = new BridgeClient(adapter);
    const element = document.createElement("settings-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);

    expect(adapter.controlUiStateCalls).toBe(1);
    expect(adapter.healthProbeCalls).toBe(1);
    expect(adapter.logTailCalls).toBe(1);

    await vi.advanceTimersByTimeAsync(5200);
    await flushUi(element);

    expect(adapter.controlUiStateCalls).toBeGreaterThanOrEqual(2);
    expect(adapter.healthProbeCalls).toBeGreaterThanOrEqual(2);
    expect(adapter.logTailCalls).toBeGreaterThanOrEqual(2);

    const refreshMeta = element.shadowRoot.querySelector(
      "[data-testid='diagnostics-refresh-meta']",
    ) as HTMLElement;
    expect(refreshMeta.textContent).toContain("自动刷新已开启");
  });

  it("stops diagnostics polling after auto refresh is disabled", async () => {
    vi.useFakeTimers();
    const adapter = new DiagnosticsSettingsAdapter();
    const client = new BridgeClient(adapter);
    const element = document.createElement("settings-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await flushUi(element);

    const toggleButton = element.shadowRoot.querySelector(
      "[data-testid='settings-toggle-auto-refresh']",
    ) as HTMLButtonElement;
    toggleButton.click();
    await flushUi(element);

    await vi.advanceTimersByTimeAsync(5200);
    await flushUi(element);

    expect(adapter.controlUiStateCalls).toBe(1);
    expect(adapter.healthProbeCalls).toBe(1);
    expect(adapter.logTailCalls).toBe(1);

    const refreshMeta = element.shadowRoot.querySelector(
      "[data-testid='diagnostics-refresh-meta']",
    ) as HTMLElement;
    expect(refreshMeta.textContent).toContain("自动刷新已暂停");
  });

  it("emits drill-down navigation from diagnostics cards", async () => {
    const events: Array<Record<string, unknown>> = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.addEventListener(
      "navigate-control-context",
      ((event: CustomEvent<Record<string, unknown>>) => {
        events.push(event.detail);
      }) as EventListener,
    );
    document.body.appendChild(element);
    await flushUi(element);

    const workflowButton = element.shadowRoot.querySelector(
      "[data-testid='workflow-diagnostic-open-run_1']",
    ) as HTMLButtonElement;
    workflowButton.click();
    const approvalButton = element.shadowRoot.querySelector(
      "[data-testid='approval-diagnostic-open-approval_demo_001']",
    ) as HTMLButtonElement;
    approvalButton.click();

    expect(events).toHaveLength(2);
    expect(events[0]).toMatchObject({
      route: "sessions",
      traceId: "trace_demo_001",
      workflowRunId: "run_1",
      timelineScope: "workflowRuns",
      source: "settings-diagnostics",
    });
    expect(events[1]).toMatchObject({
      route: "approvals",
      traceId: "trace_demo_001",
      approvalId: "approval_demo_001",
      source: "settings-diagnostics",
    });
  });

  it("filters and inspects auth methods", async () => {
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const writeFilter = element.shadowRoot.querySelector(
      "[data-testid='gateway-method-filter-write']",
    ) as HTMLButtonElement;
    writeFilter.click();
    await flushUi(element);

    const methodList = element.shadowRoot.querySelector(
      "[data-testid='gateway-method-list']",
    ) as HTMLElement;
    expect(methodList.textContent).toContain("browser.proxy");
    expect(methodList.textContent).toContain("approvals.resolve");
    expect(methodList.textContent).not.toContain("health.probes");

    const selectButton = element.shadowRoot.querySelector(
      "[data-testid='gateway-method-select-browser.proxy']",
    ) as HTMLButtonElement;
    selectButton.click();
    await flushUi(element);

    const detail = element.shadowRoot.querySelector(
      "[data-testid='gateway-method-detail']",
    ) as HTMLElement;
    expect(detail.textContent).toContain("browser.proxy");
    expect(detail.textContent).toContain("browser.write");
    expect(detail.textContent).toContain("transport=proxy");
    expect(detail.textContent).toContain("write budget");

    const publicFilter = element.shadowRoot.querySelector(
      "[data-testid='gateway-method-filter-public']",
    ) as HTMLButtonElement;
    publicFilter.click();
    await flushUi(element);

    expect(methodList.textContent).toContain("connect.initialize");
    expect(methodList.textContent).not.toContain("browser.proxy");
    expect(detail.textContent).toContain("connect.initialize");
  });

  it("reverses scope drill-down into method detail", async () => {
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const scopeButton = element.shadowRoot.querySelector(
      "[data-testid='gateway-scope-select-gateway.read']",
    ) as HTMLButtonElement;
    scopeButton.click();
    await flushUi(element);

    const scopeDetail = element.shadowRoot.querySelector(
      "[data-testid='gateway-scope-detail']",
    ) as HTMLElement;
    expect(scopeDetail.textContent).toContain("gateway.read");
    expect(scopeDetail.textContent).toContain("health.probes");
    expect(scopeDetail.textContent).toContain("logs.tail");

    const openMethodButton = element.shadowRoot.querySelector(
      "[data-testid='gateway-scope-open-logs.tail']",
    ) as HTMLButtonElement;
    openMethodButton.click();
    await flushUi(element);

    const methodDetail = element.shadowRoot.querySelector(
      "[data-testid='gateway-method-detail']",
    ) as HTMLElement;
    expect(methodDetail.textContent).toContain("logs.tail");
    expect(methodDetail.textContent).toContain("gateway.read");
    expect(methodDetail.textContent).toContain("打开 设置");
  });

  it("dispatches route-change from method detail next-hop", async () => {
    const routes: string[] = [];
    const element = document.createElement("settings-page") as HTMLElement & {
      surfaceMode?: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.surfaceMode = "auth";
    element.addEventListener("route-change", ((event: CustomEvent<string>) => {
      routes.push(event.detail);
    }) as EventListener);
    document.body.appendChild(element);
    await flushUi(element);

    const selectButton = element.shadowRoot.querySelector(
      "[data-testid='gateway-method-select-browser.proxy']",
    ) as HTMLButtonElement;
    selectButton.click();
    await flushUi(element);

    const openRoute = element.shadowRoot.querySelector(
      "[data-testid='gateway-method-open-route']",
    ) as HTMLButtonElement;
    openRoute.click();

    expect(routes).toEqual(["browser"]);
  });

  it("shows inferred http transport auth hint when bridge runtime config is present", async () => {
    window.__AGENTHUB_GUI_BRIDGE__ = {
      mode: "http",
      httpBaseUrl: "http://127.0.0.1:8787/gui",
      eventTransport: "polling",
      pollingIntervalMs: 1200,
      client: {
        name: "agenthub-gui",
        version: "0.1.0",
      },
    };
    const element = document.createElement("settings-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const gatewayAuthSummary = element.shadowRoot.querySelector(
      "[data-testid='gateway-auth-summary']",
    ) as HTMLElement;
    expect(gatewayAuthSummary.textContent).toContain("http / polling");
    expect(gatewayAuthSummary.textContent).toContain("认证状态仅按部署方式推断");
    const gatewayOriginHint = element.shadowRoot.querySelector(
      "[data-testid='gateway-origin-hint']",
    ) as HTMLElement;
    expect(gatewayOriginHint.textContent).toContain("polling");
    const gatewayTransportContract = element.shadowRoot.querySelector(
      "[data-testid='gateway-transport-contract']",
    ) as HTMLElement;
    expect(gatewayTransportContract.textContent).toContain("http://127.0.0.1:8787/gui");
    expect(gatewayTransportContract.textContent).toContain("/requests");
    expect(gatewayTransportContract.textContent).toContain("/control-ui/state");
    expect(gatewayTransportContract.textContent).toContain("/browser-proxy");
    expect(gatewayTransportContract.textContent).toContain("1200ms");
    expect(gatewayTransportContract.textContent).toContain("agenthub-gui/0.1.0");
  });

  it("falls back to runtime provider label when connect capabilities omit it", async () => {
    const client = new BridgeClient(new GatewayProviderFallbackAdapter());
    const element = document.createElement("settings-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = client;
    document.body.appendChild(element);
    await new Promise((resolve) => setTimeout(resolve, 25));
    await flushUi(element);

    const gatewayConnectSummary = element.shadowRoot.querySelector(
      "[data-testid='gateway-connect-summary']",
    ) as HTMLElement;
    expect(gatewayConnectSummary.textContent).toContain("openai | gpt-5.4");
  });
});
