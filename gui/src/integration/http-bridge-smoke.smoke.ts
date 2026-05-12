import { spawn, spawnSync, type ChildProcessWithoutNullStreams } from "node:child_process";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";

import "../app_shell/app-shell.ts";

const CURRENT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(CURRENT_DIR, "../../..");

let bridgeProcess: ChildProcessWithoutNullStreams | null = null;
let bridgeBaseUrl = "";
let bridgeLogs = "";
const SEEDED_ROLLOUT_TRACE_ID = "trace_gui_smoke_rollout";
const SEEDED_ROLLOUT_WORKFLOW_ID = "wf_gui_smoke_rollout";
const SEEDED_GATEWAY_EVENT_ID = "evt_gui_smoke_gateway_event";
const SEEDED_GATEWAY_WORKFLOW_TRACE_ID = "trace_gui_smoke_gateway_workflow";
const SEEDED_GATEWAY_WORKFLOW_ID = "wf_gui_smoke_gateway_workflow";

async function allocatePort(): Promise<number> {
  return await new Promise((resolve, reject) => {
    const server = createServer();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close();
        reject(new Error("failed to allocate tcp port"));
        return;
      }
      const port = address.port;
      server.close((closeError) => {
        if (closeError) {
          reject(closeError);
          return;
        }
        resolve(port);
      });
    });
  });
}

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForHealth(url: string): Promise<void> {
  let lastError = "bridge did not become healthy";
  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (bridgeProcess?.exitCode !== null) {
      throw new Error(`bridge exited early with code ${bridgeProcess.exitCode}\n${bridgeLogs}`);
    }
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
      lastError = `health returned ${response.status}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await sleep(250);
  }
  throw new Error(`${lastError}\n${bridgeLogs}`);
}

async function flushUi(element: HTMLElement & { updateComplete?: Promise<unknown> }) {
  for (let attempt = 0; attempt < 6; attempt += 1) {
    await Promise.resolve();
    await sleep(50);
    await element.updateComplete;
  }
}

function nestedText(root: ShadowRoot, selector: string): string {
  const element = root.querySelector(selector) as HTMLElement & {
    shadowRoot?: ShadowRoot;
    updateComplete?: Promise<unknown>;
  };
  return element?.shadowRoot?.textContent ?? "";
}

async function waitFor(
  predicate: () => boolean,
  timeoutMs = 5000,
  intervalMs = 50,
): Promise<void> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (predicate()) {
      return;
    }
    await sleep(intervalMs);
  }
  throw new Error("condition not met before timeout");
}

function seedActiveRolloutCausality() {
  const script = `
from cli.agent_cli.models import PromptResponse, ToolEvent
from cli.agent_cli.thread_store import ThreadStore

store = ThreadStore.default()
thread = store.start_thread(name="GUI Smoke Rollout")
store.append_turn(
    thread.thread_id,
    PromptResponse(
        user_text="seed thread.active_rollout workflow detail smoke",
        assistant_text="thread.active_rollout workflow detail ready",
        tool_events=[
            ToolEvent(
                name="gateway.workflow.resume",
                ok=True,
                summary="seed rollout causality",
                payload={
                    "metadata": {
                        "causality": {
                            "trace_id": "${SEEDED_ROLLOUT_TRACE_ID}",
                            "workflow_run_id": "${SEEDED_ROLLOUT_WORKFLOW_ID}",
                        }
                    }
                },
            )
        ],
    ),
)
print(thread.thread_id)
`;
  const result = spawnSync("python", ["-c", script], {
    cwd: REPO_ROOT,
    encoding: "utf-8",
  });
  if (result.status !== 0) {
    throw new Error(`failed to seed active rollout causality\\n${result.stderr || result.stdout}`);
  }
}

function seedGatewayWorkflowRunSource() {
  const script = `
from datetime import datetime, timezone

from cli.agent_cli.gateway_core.models import WorkflowRun
from cli.agent_cli.gateway_core.state_store import JsonlGatewayStateStore

now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
store = JsonlGatewayStateStore.default()
store.save_workflow_run(
    WorkflowRun(
        workflow_run_id="${SEEDED_GATEWAY_WORKFLOW_ID}",
        workflow_name="GUI Smoke Workflow",
        plugin_name="gui-smoke",
        trace_id="${SEEDED_GATEWAY_WORKFLOW_TRACE_ID}",
        status="paused",
        started_at=now,
        updated_at=now,
        current_step="awaiting_input",
        result_summary="seeded workflow run for gui smoke",
    )
)
print("${SEEDED_GATEWAY_WORKFLOW_ID}")
`;
  const result = spawnSync("python", ["-c", script], {
    cwd: REPO_ROOT,
    encoding: "utf-8",
  });
  if (result.status !== 0) {
    throw new Error(`failed to seed gateway workflow source\\n${result.stderr || result.stdout}`);
  }
}

function seedGatewayEventSource() {
  const script = `
from datetime import datetime, timezone

from cli.agent_cli.gateway_core.models import GatewayEvent
from cli.agent_cli.gateway_core.state_store import JsonlGatewayStateStore

now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
store = JsonlGatewayStateStore.default()
store.save_event(
    GatewayEvent(
        event_id="${SEEDED_GATEWAY_EVENT_ID}",
        event_type="gui.smoke.event",
        source_kind="gui_smoke",
        source_id="gui_smoke_source",
        connector_key="gui_smoke",
        plugin_name="gui_smoke",
        tenant_id=None,
        occurred_at=now,
        received_at=now,
        trace_id="${SEEDED_GATEWAY_WORKFLOW_TRACE_ID}",
        payload={"workflow_run_id": "${SEEDED_GATEWAY_WORKFLOW_ID}"},
        metadata={"causality": {"workflow_run_id": "${SEEDED_GATEWAY_WORKFLOW_ID}"}},
    )
)
print("${SEEDED_GATEWAY_EVENT_ID}")
`;
  const result = spawnSync("python", ["-c", script], {
    cwd: REPO_ROOT,
    encoding: "utf-8",
  });
  if (result.status !== 0) {
    throw new Error(`failed to seed gateway event source\\n${result.stderr || result.stdout}`);
  }
}

describe("http bridge smoke", () => {
  beforeAll(async () => {
    seedActiveRolloutCausality();
    seedGatewayWorkflowRunSource();
    seedGatewayEventSource();
    const port = await allocatePort();
    bridgeBaseUrl = `http://127.0.0.1:${port}/gui`;
    bridgeProcess = spawn(
      "bash",
      ["-lc", `./cli/scripts/start_gui_bridge.sh --host 127.0.0.1 --port ${port}`],
      {
        cwd: REPO_ROOT,
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    bridgeProcess.stdout.on("data", (chunk) => {
      bridgeLogs += chunk.toString();
    });
    bridgeProcess.stderr.on("data", (chunk) => {
      bridgeLogs += chunk.toString();
    });
    await waitForHealth(`${bridgeBaseUrl}/health`);
  }, 30000);

  afterAll(() => {
    delete window.__AGENTHUB_GUI_BRIDGE__;
    if (bridgeProcess && bridgeProcess.exitCode === null) {
      bridgeProcess.kill("SIGTERM");
    }
  });

  beforeEach(() => {
    window.history.pushState({}, "", "/");
    document.body.innerHTML = "";
    window.__AGENTHUB_GUI_BRIDGE__ = {
      mode: "http",
      httpBaseUrl: bridgeBaseUrl,
      requestPath: "/requests",
      eventsPath: "/events",
      eventTransport: "polling",
      pollingIntervalMs: 100,
    };
  });

  it("renders the app shell against the live http bridge", async () => {
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const statusBar = element.shadowRoot.querySelector("global-status-bar") as HTMLElement & {
      shadowRoot?: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await statusBar.updateComplete;
    await waitFor(() => {
      const text = statusBar.shadowRoot?.textContent ?? "";
      return text.includes("当前模型") || text.includes("当前未配置模型");
    });

    expect(element.shadowRoot.textContent).toContain("工作台");
    const statusText = statusBar.shadowRoot?.textContent ?? "";
    expect(statusText).toContain("模型");
    expect(statusText).toMatch(/当前模型|当前未配置模型/);
  }, 20000);

  it("loads settings/config/debug/auth/channels/nodes/sessions/approvals/plugins pages through the live http bridge", async () => {
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const nav = element.shadowRoot.querySelector("sidebar-nav");
    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "settings",
        bubbles: true,
        composed: true,
      }),
    );
    await flushUi(element);

    const settingsPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      shadowRoot?: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await settingsPage.updateComplete;
    await waitFor(() => {
      const inputs = settingsPage.shadowRoot?.querySelectorAll('input[type="text"]');
      return Boolean(inputs && inputs.length >= 2 && (inputs[1] as HTMLInputElement).value.length > 0);
    });
    const settingsInputs = settingsPage.shadowRoot?.querySelectorAll('input[type="text"]') ?? [];
    expect((settingsInputs[0] as HTMLInputElement).value.length).toBeGreaterThan(0);
    expect((settingsInputs[1] as HTMLInputElement).value).toBe(REPO_ROOT);
    expect(settingsPage.shadowRoot?.textContent).toContain("Config Apply / Preview");
    expect(settingsPage.shadowRoot?.querySelector("[data-testid='settings-apply-summary']")).toBeTruthy();
    expect(settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-source-select']")).toBeTruthy();
    expect(settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-route-cue']")).toBeTruthy();

    const validateButton = settingsPage.shadowRoot?.querySelector(
      "[data-testid='settings-validate']",
    ) as HTMLButtonElement;
    validateButton.click();
    await flushUi(element);
    await waitFor(() => {
      const summary = settingsPage.shadowRoot?.querySelector("[data-testid='settings-remote-validate-summary']");
      return (summary?.textContent ?? "").includes("changed=");
    });
    expect(settingsPage.shadowRoot?.querySelector("[data-testid='settings-remote-validate-summary']")?.textContent).toContain(
      "changed=",
    );

    const restartReportButton = settingsPage.shadowRoot?.querySelector(
      "[data-testid='settings-restart-report']",
    ) as HTMLButtonElement;
    restartReportButton.click();
    await flushUi(element);
    await waitFor(() => {
      const summary = settingsPage.shadowRoot?.querySelector("[data-testid='settings-remote-restart-report-summary']");
      return (summary?.textContent ?? "").includes("required=");
    });
    expect(
      settingsPage.shadowRoot?.querySelector("[data-testid='settings-remote-restart-report-summary']")?.textContent,
    ).toContain("required=");
    expect(nestedText(settingsPage.shadowRoot as ShadowRoot, "[data-testid='settings-feedback']")).toMatch(
      /config\.restart\.report|config\.validate/,
    );

    const settingsCheckboxes = settingsPage.shadowRoot?.querySelectorAll('input[type="checkbox"]') ?? [];
    const pluginAutoLoadCheckbox = settingsCheckboxes[1] as HTMLInputElement;
    const originalPluginAutoLoad = pluginAutoLoadCheckbox.checked;
    pluginAutoLoadCheckbox.checked = !originalPluginAutoLoad;
    pluginAutoLoadCheckbox.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);
    expect(settingsPage.shadowRoot?.querySelector("[data-testid='settings-apply-summary']")?.textContent).toContain(
      "当前草稿可应用，但包含 restart impact",
    );

    const saveButton = settingsPage.shadowRoot?.querySelector("[data-testid='settings-save']") as HTMLButtonElement;
    expect(saveButton.disabled).toBe(false);
    saveButton.click();
    await flushUi(element);
    await waitFor(() => {
      const feedback = nestedText(settingsPage.shadowRoot as ShadowRoot, "[data-testid='settings-feedback']");
      return feedback.includes("runtime 设置已保存") || feedback.includes("建议在相关运行面重启后确认");
    });
    expect(nestedText(settingsPage.shadowRoot as ShadowRoot, "[data-testid='settings-feedback']")).toMatch(
      /runtime 设置已保存|建议在相关运行面重启后确认/,
    );
    await waitFor(() => {
      const save = settingsPage.shadowRoot?.querySelector("[data-testid='settings-save']") as HTMLButtonElement | null;
      const checkboxes = settingsPage.shadowRoot?.querySelectorAll('input[type="checkbox"]') ?? [];
      const checkbox = checkboxes[1] as HTMLInputElement | undefined;
      return Boolean(
        save?.disabled &&
          checkbox &&
          checkbox.checked === !originalPluginAutoLoad,
      );
    });

    expect(settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-route-open']")).toBeTruthy();
    expect(settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-route-cue']")?.textContent).toMatch(
      /route=/,
    );

    const logSourceSelect = settingsPage.shadowRoot?.querySelector(
      "[data-testid='settings-log-source-select']",
    ) as HTMLSelectElement;
    logSourceSelect.value = "thread.active_rollout";
    logSourceSelect.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);
    await waitFor(() => {
      const cue = settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-route-cue']");
      return (cue?.textContent ?? "").includes("route=Sessions / Runs");
    });
    expect(settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-route-cue']")?.textContent).toContain(
      "route=Sessions / Runs",
    );
    expect(settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-route-open']")).toBeTruthy();

    logSourceSelect.value = "gateway.action_requests";
    logSourceSelect.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);
    await waitFor(() => {
      const cue = settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-route-cue']");
      return (cue?.textContent ?? "").includes("route=审批与审计");
    });
    expect(settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-route-cue']")?.textContent).toContain(
      "route=审批与审计",
    );
    const openLogRecord = settingsPage.shadowRoot?.querySelector(
      "[data-testid='settings-log-record-open-0']",
    ) as HTMLButtonElement;
    openLogRecord.click();
    await flushUi(element);
    await waitFor(() => {
      const panel = element.shadowRoot.querySelector("[data-route-panel]");
      return panel?.getAttribute("data-route-panel") === "approvals";
    });
    const approvalsHandoffPage = element.shadowRoot.querySelector("approvals-audit-page") as HTMLElement & {
      initialTraceFilter?: string;
      initialActionId?: string;
      updateComplete?: Promise<unknown>;
    };
    await approvalsHandoffPage.updateComplete;
    expect(approvalsHandoffPage.initialTraceFilter?.length ?? 0).toBeGreaterThan(0);
    expect(approvalsHandoffPage.initialActionId?.length ?? 0).toBeGreaterThan(0);

    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "settings",
        bubbles: true,
        composed: true,
      }),
    );
    await flushUi(element);
    const settingsLogsPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      shadowRoot?: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await settingsLogsPage.updateComplete;
    await waitFor(() => Boolean(settingsLogsPage.shadowRoot?.querySelector("[data-testid='settings-log-route-open-logs']")));
    const openLogsSurface = settingsLogsPage.shadowRoot?.querySelector(
      "[data-testid='settings-log-route-open-logs']",
    ) as HTMLButtonElement;
    openLogsSurface.click();
    await flushUi(element);
    await waitFor(() => {
      const panel = element.shadowRoot.querySelector("[data-route-panel]");
      return panel?.getAttribute("data-route-panel") === "logs";
    });
    const logsPage = element.shadowRoot.querySelector("logs-operator-page") as HTMLElement & {
      shadowRoot?: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await logsPage.updateComplete;
    await waitFor(() => (logsPage.shadowRoot?.textContent ?? "").includes("Logs Operator Surface"));
    expect(logsPage.shadowRoot?.textContent).toContain("Log Stream");
    expect(logsPage.shadowRoot?.textContent).toContain("Structured Drill-down");
    expect(logsPage.shadowRoot?.querySelector("[data-testid='logs-source-select']")).toBeTruthy();

    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "config",
        bubbles: true,
        composed: true,
      }),
    );
    await flushUi(element);
    const configPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      surfaceMode?: string;
      shadowRoot?: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await configPage.updateComplete;
    await waitFor(() => (configPage.shadowRoot?.textContent ?? "").includes("Config / Policy / Apply"));
    expect(configPage.surfaceMode).toBe("config");
    expect(configPage.shadowRoot?.querySelector("[data-testid='settings-config-console']")).toBeTruthy();

    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "debug",
        bubbles: true,
        composed: true,
      }),
    );
    await flushUi(element);
    const debugPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      surfaceMode?: string;
      shadowRoot?: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await debugPage.updateComplete;
    await waitFor(() => (debugPage.shadowRoot?.textContent ?? "").includes("Debug / Diagnostics / Trace"));
    expect(debugPage.surfaceMode).toBe("debug");
    expect(debugPage.shadowRoot?.querySelector("[data-testid='settings-debug-console']")).toBeTruthy();

    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "auth",
        bubbles: true,
        composed: true,
      }),
    );
    await flushUi(element);

    const authPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      shadowRoot?: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await authPage.updateComplete;
    await waitFor(() => (authPage.shadowRoot?.textContent ?? "").includes("Gateway Auth / Scope / Connect"));
    expect(authPage.shadowRoot?.textContent).toContain("Access / Pairing Posture");

    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "channels",
        bubbles: true,
        composed: true,
      }),
    );
    await flushUi(element);

    const channelsPage = element.shadowRoot.querySelector("channels-operator-page") as HTMLElement & {
      shadowRoot?: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await channelsPage.updateComplete;
    await waitFor(() => (channelsPage.shadowRoot?.textContent ?? "").includes("Channels Inventory"));
    expect(channelsPage.shadowRoot?.textContent).toContain("Operator Detail");

    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "nodes",
        bubbles: true,
        composed: true,
      }),
    );
    await flushUi(element);

    const nodesPage = element.shadowRoot.querySelector("nodes-devices-page") as HTMLElement & {
      shadowRoot?: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await nodesPage.updateComplete;
    await waitFor(() => (nodesPage.shadowRoot?.textContent ?? "").includes("Nodes / Devices Inventory"));
    expect(nodesPage.shadowRoot?.textContent).toContain("Node Operator Detail");

    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "sessions",
        bubbles: true,
        composed: true,
      }),
    );
    await flushUi(element);

    const sessionsPage = element.shadowRoot.querySelector("sessions-runs-trace-page") as HTMLElement & {
      shadowRoot?: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await sessionsPage.updateComplete;
    await waitFor(() => (sessionsPage.shadowRoot?.textContent ?? "").includes("Workflow Detail"));
    expect(sessionsPage.shadowRoot?.textContent).toContain("Trace Timeline");
    expect(sessionsPage.shadowRoot?.querySelector("[data-testid='trace-select']")).toBeTruthy();

    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "approvals",
        bubbles: true,
        composed: true,
      }),
    );
    await flushUi(element);

    const approvalsPage = element.shadowRoot.querySelector("approvals-audit-page") as HTMLElement & {
      shadowRoot?: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await approvalsPage.updateComplete;
    await waitFor(() => (approvalsPage.shadowRoot?.textContent ?? "").includes("审批详情与审计链"));
    expect(approvalsPage.shadowRoot?.textContent).toContain("Trace Timeline");
    expect(approvalsPage.shadowRoot?.querySelector("[data-testid='approval-detail']")).toBeTruthy();

    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "plugins",
        bubbles: true,
        composed: true,
      }),
    );
    await flushUi(element);

    const pluginsPage = element.shadowRoot.querySelector("plugins-connectors-page") as HTMLElement & {
      shadowRoot?: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await pluginsPage.updateComplete;
    await waitFor(() => nestedText(pluginsPage.shadowRoot as ShadowRoot, '[data-testid="connector-feedback"]').length > 0);

    expect(pluginsPage.shadowRoot?.textContent).toContain("插件");
    expect(pluginsPage.shadowRoot?.textContent).toContain("连接器");
    expect(nestedText(pluginsPage.shadowRoot as ShadowRoot, '[data-testid="connector-feedback"]')).not.toContain(
      "正在同步连接器状态",
    );
  }, 20000);

  it("smokes config.apply partial apply with blocked draft retain through the live http bridge", async () => {
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const nav = element.shadowRoot.querySelector("sidebar-nav");
    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "settings",
        bubbles: true,
        composed: true,
      }),
    );
    await flushUi(element);

    const settingsPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      shadowRoot?: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await settingsPage.updateComplete;
    await waitFor(() => {
      const textInputs = settingsPage.shadowRoot?.querySelectorAll('input[type="text"]') ?? [];
      const checkboxes = settingsPage.shadowRoot?.querySelectorAll('input[type="checkbox"]') ?? [];
      return textInputs.length >= 2 && checkboxes.length >= 2;
    });

    const textInputs = settingsPage.shadowRoot?.querySelectorAll('input[type="text"]') ?? [];
    const modelInput = textInputs[0] as HTMLInputElement;
    const checkboxes = settingsPage.shadowRoot?.querySelectorAll('input[type="checkbox"]') ?? [];
    const pluginAutoLoadCheckbox = checkboxes[1] as HTMLInputElement;

    modelInput.value = "__partial_apply_smoke__";
    modelInput.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    pluginAutoLoadCheckbox.checked = !pluginAutoLoadCheckbox.checked;
    pluginAutoLoadCheckbox.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);

    expect(settingsPage.shadowRoot?.querySelector("[data-testid='settings-apply-summary']")?.textContent).toContain(
      "当前草稿可部分应用",
    );

    const saveButton = settingsPage.shadowRoot?.querySelector("[data-testid='settings-save']") as HTMLButtonElement;
    expect(saveButton.disabled).toBe(false);
    expect(saveButton.textContent).toContain("应用支持字段");
    saveButton.click();
    await flushUi(element);

    await waitFor(() => {
      const feedback = nestedText(settingsPage.shadowRoot as ShadowRoot, "[data-testid='settings-feedback']");
      return feedback.includes("以下字段仍未应用并保留在本地草稿：model");
    });
    const feedback = nestedText(settingsPage.shadowRoot as ShadowRoot, "[data-testid='settings-feedback']");
    expect(feedback).toContain("以下字段仍未应用并保留在本地草稿：model");
    expect(feedback).toMatch(/建议在相关运行面重启后确认|pluginAutoLoad 变更/);
    expect(modelInput.value).toBe("__partial_apply_smoke__");
    expect(saveButton.disabled).toBe(true);
  }, 20000);

  it("smokes gateway.approval_tickets handoff into approvals context through the live http bridge", async () => {
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const nav = element.shadowRoot.querySelector("sidebar-nav");
    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "settings",
        bubbles: true,
        composed: true,
      }),
    );
    await flushUi(element);

    const settingsPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      shadowRoot?: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await settingsPage.updateComplete;
    await waitFor(() => {
      const select = settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-source-select']");
      const inventory = settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-source-inventory']");
      const refreshMeta = settingsPage.shadowRoot?.querySelector("[data-testid='diagnostics-refresh-meta']");
      return Boolean(
        select &&
          (inventory?.textContent ?? "").includes("Gateway Approval Tickets") &&
          (refreshMeta?.textContent ?? "").includes("空闲"),
      );
    });

    const logSourceSelect = settingsPage.shadowRoot?.querySelector(
      "[data-testid='settings-log-source-select']",
    ) as HTMLSelectElement;
    logSourceSelect.value = "gateway.approval_tickets";
    logSourceSelect.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);
    await waitFor(() => {
      const cue = settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-route-cue']");
      return (cue?.textContent ?? "").includes("route=审批与审计");
    });

    const openLogRecord = settingsPage.shadowRoot?.querySelector(
      "[data-testid='settings-log-record-open-0']",
    ) as HTMLButtonElement;
    openLogRecord.click();
    await flushUi(element);
    await waitFor(() => {
      const panel = element.shadowRoot.querySelector("[data-route-panel]");
      return panel?.getAttribute("data-route-panel") === "approvals";
    });

    const approvalsPage = element.shadowRoot.querySelector("approvals-audit-page") as HTMLElement & {
      initialTraceFilter?: string;
      initialApprovalId?: string;
      initialActionId?: string;
      updateComplete?: Promise<unknown>;
    };
    await approvalsPage.updateComplete;
    expect(approvalsPage.initialTraceFilter?.length ?? 0).toBeGreaterThan(0);
    expect(approvalsPage.initialApprovalId?.length ?? 0).toBeGreaterThan(0);
    expect(approvalsPage.initialActionId?.length ?? 0).toBeGreaterThan(0);
  }, 20000);

  it("smokes gateway.audit_records handoff into approvals context through the live http bridge", async () => {
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const nav = element.shadowRoot.querySelector("sidebar-nav");
    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "settings",
        bubbles: true,
        composed: true,
      }),
    );
    await flushUi(element);

    const settingsPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      shadowRoot?: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await settingsPage.updateComplete;
    await waitFor(() => {
      const select = settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-source-select']");
      const inventory = settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-source-inventory']");
      const refreshMeta = settingsPage.shadowRoot?.querySelector("[data-testid='diagnostics-refresh-meta']");
      return Boolean(
        select &&
          (inventory?.textContent ?? "").includes("Gateway Audit Records") &&
          (refreshMeta?.textContent ?? "").includes("空闲"),
      );
    });

    const logSourceSelect = settingsPage.shadowRoot?.querySelector(
      "[data-testid='settings-log-source-select']",
    ) as HTMLSelectElement;
    logSourceSelect.value = "gateway.audit_records";
    logSourceSelect.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);
    await waitFor(() => {
      const cue = settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-route-cue']");
      return (cue?.textContent ?? "").includes("route=审批与审计");
    });

    const openLogRecord = settingsPage.shadowRoot?.querySelector(
      "[data-testid='settings-log-record-open-0']",
    ) as HTMLButtonElement;
    openLogRecord.click();
    await flushUi(element);
    await waitFor(() => {
      const panel = element.shadowRoot.querySelector("[data-route-panel]");
      return panel?.getAttribute("data-route-panel") === "approvals";
    });

    const approvalsPage = element.shadowRoot.querySelector("approvals-audit-page") as HTMLElement & {
      initialTraceFilter?: string;
      initialActionId?: string;
      initialAuditId?: string;
      updateComplete?: Promise<unknown>;
    };
    await approvalsPage.updateComplete;
    expect(approvalsPage.initialTraceFilter?.length ?? 0).toBeGreaterThan(0);
    expect(approvalsPage.initialActionId?.length ?? 0).toBeGreaterThan(0);
    expect(approvalsPage.initialAuditId?.length ?? 0).toBeGreaterThan(0);
  }, 20000);

  it("smokes thread.active_rollout handoff into sessions workflow detail through the live http bridge", async () => {
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const nav = element.shadowRoot.querySelector("sidebar-nav");
    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "settings",
        bubbles: true,
        composed: true,
      }),
    );
    await flushUi(element);

    const settingsPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      shadowRoot?: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await settingsPage.updateComplete;
    await waitFor(() => {
      const select = settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-source-select']");
      const inventory = settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-source-inventory']");
      const refreshMeta = settingsPage.shadowRoot?.querySelector("[data-testid='diagnostics-refresh-meta']");
      return Boolean(
        select &&
          (inventory?.textContent ?? "").includes("Active Thread Rollout") &&
          (refreshMeta?.textContent ?? "").includes("空闲"),
      );
    });

    const logSourceSelect = settingsPage.shadowRoot?.querySelector(
      "[data-testid='settings-log-source-select']",
    ) as HTMLSelectElement;
    logSourceSelect.value = "thread.active_rollout";
    logSourceSelect.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);
    await waitFor(() => {
      const cue = settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-route-cue']");
      return (cue?.textContent ?? "").includes("route=Sessions / Runs");
    });

    const openLogRecord = settingsPage.shadowRoot?.querySelector(
      "[data-testid='settings-log-record-open-0']",
    ) as HTMLButtonElement;
    openLogRecord.click();
    await flushUi(element);
    await waitFor(() => {
      const panel = element.shadowRoot.querySelector("[data-route-panel]");
      return panel?.getAttribute("data-route-panel") === "sessions";
    });

    const sessionsPage = element.shadowRoot.querySelector("sessions-runs-trace-page") as HTMLElement & {
      initialTraceId?: string;
      initialWorkflowRunId?: string;
      initialTimelineScope?: string;
      updateComplete?: Promise<unknown>;
    };
    await sessionsPage.updateComplete;
    expect(sessionsPage.initialTraceId).toBe(SEEDED_ROLLOUT_TRACE_ID);
    expect(sessionsPage.initialWorkflowRunId).toBe(SEEDED_ROLLOUT_WORKFLOW_ID);
    expect(sessionsPage.initialTimelineScope).toBe("workflowRuns");
  }, 20000);

  it("smokes gateway.workflow_runs handoff into sessions workflow detail through the live http bridge", async () => {
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const nav = element.shadowRoot.querySelector("sidebar-nav");
    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "settings",
        bubbles: true,
        composed: true,
      }),
    );
    await flushUi(element);

    const settingsPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      shadowRoot?: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await settingsPage.updateComplete;
    await waitFor(() => {
      const select = settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-source-select']");
      const inventory = settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-source-inventory']");
      const refreshMeta = settingsPage.shadowRoot?.querySelector("[data-testid='diagnostics-refresh-meta']");
      return Boolean(
        select &&
          (inventory?.textContent ?? "").includes("Gateway Workflow Runs") &&
          (refreshMeta?.textContent ?? "").includes("空闲"),
      );
    });

    const logSourceSelect = settingsPage.shadowRoot?.querySelector(
      "[data-testid='settings-log-source-select']",
    ) as HTMLSelectElement;
    logSourceSelect.value = "gateway.workflow_runs";
    logSourceSelect.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);
    await waitFor(() => {
      const cue = settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-route-cue']");
      return (cue?.textContent ?? "").includes("route=Sessions / Runs");
    });

    const openLogRecord = settingsPage.shadowRoot?.querySelector(
      "[data-testid='settings-log-record-open-0']",
    ) as HTMLButtonElement;
    openLogRecord.click();
    await flushUi(element);
    await waitFor(() => {
      const panel = element.shadowRoot.querySelector("[data-route-panel]");
      return panel?.getAttribute("data-route-panel") === "sessions";
    });

    const sessionsPage = element.shadowRoot.querySelector("sessions-runs-trace-page") as HTMLElement & {
      initialTraceId?: string;
      initialWorkflowRunId?: string;
      initialTimelineScope?: string;
      updateComplete?: Promise<unknown>;
    };
    await sessionsPage.updateComplete;
    expect(sessionsPage.initialTraceId).toBe(SEEDED_GATEWAY_WORKFLOW_TRACE_ID);
    expect(sessionsPage.initialWorkflowRunId).toBe(SEEDED_GATEWAY_WORKFLOW_ID);
    expect(sessionsPage.initialTimelineScope).toBe("workflowRuns");
  }, 20000);

  it("smokes gateway.events handoff into sessions workflow detail through the live http bridge", async () => {
    const element = document.createElement("agenthub-app") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await flushUi(element);

    const nav = element.shadowRoot.querySelector("sidebar-nav");
    nav?.dispatchEvent(
      new CustomEvent("route-change", {
        detail: "settings",
        bubbles: true,
        composed: true,
      }),
    );
    await flushUi(element);

    const settingsPage = element.shadowRoot.querySelector("settings-page") as HTMLElement & {
      shadowRoot?: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await settingsPage.updateComplete;
    await waitFor(() => {
      const select = settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-source-select']");
      const inventory = settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-source-inventory']");
      const refreshMeta = settingsPage.shadowRoot?.querySelector("[data-testid='diagnostics-refresh-meta']");
      return Boolean(
        select &&
          (inventory?.textContent ?? "").includes("Gateway Events") &&
          (refreshMeta?.textContent ?? "").includes("空闲"),
      );
    });

    const logSourceSelect = settingsPage.shadowRoot?.querySelector(
      "[data-testid='settings-log-source-select']",
    ) as HTMLSelectElement;
    logSourceSelect.value = "gateway.events";
    logSourceSelect.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    await flushUi(element);
    await waitFor(() => {
      const cue = settingsPage.shadowRoot?.querySelector("[data-testid='settings-log-route-cue']");
      return (cue?.textContent ?? "").includes("route=Sessions / Runs");
    });

    const openLogRecord = settingsPage.shadowRoot?.querySelector(
      "[data-testid='settings-log-record-open-0']",
    ) as HTMLButtonElement;
    openLogRecord.click();
    await flushUi(element);
    await waitFor(() => {
      const panel = element.shadowRoot.querySelector("[data-route-panel]");
      return panel?.getAttribute("data-route-panel") === "sessions";
    });

    const sessionsPage = element.shadowRoot.querySelector("sessions-runs-trace-page") as HTMLElement & {
      initialTraceId?: string;
      initialWorkflowRunId?: string;
      initialTimelineScope?: string;
      updateComplete?: Promise<unknown>;
    };
    await sessionsPage.updateComplete;
    expect(sessionsPage.initialTraceId).toBe(SEEDED_GATEWAY_WORKFLOW_TRACE_ID);
    expect(sessionsPage.initialWorkflowRunId).toBe(SEEDED_GATEWAY_WORKFLOW_ID);
    expect(sessionsPage.initialTimelineScope).toBe("workflowRuns");
  }, 20000);
});
