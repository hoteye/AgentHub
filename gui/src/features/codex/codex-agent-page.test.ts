import { describe, expect, it } from "vitest";

import { BridgeClient } from "../../bridge/client.ts";
import type { HostAdapter } from "../../shared/api/mock-host.ts";
import {
  createBridgeSuccess,
  type BridgeEvent,
  type BridgeRequest,
} from "../../shared/types/bridge.ts";
import "./codex-agent-page.ts";

async function flushUi(element: { updateComplete?: Promise<unknown> }) {
  for (let index = 0; index < 6; index += 1) {
    await Promise.resolve();
    await element.updateComplete;
  }
}

class CodexPageAdapter implements HostAdapter {
  readonly requests: BridgeRequest<unknown>[] = [];
  private workspaceRoot = "/home/lyc/project/AgentHub";

  async request<TData = unknown>(request: BridgeRequest<unknown>) {
    this.requests.push(request);
    if (request.action === "thread.list") {
      const cwd = String((request.payload as { cwd?: string })?.cwd ?? "");
      return createBridgeSuccess(request, {
        threads:
          cwd === "/workspace/other"
            ? []
            : [
                {
                  thread_id: "thread_alpha",
                  name: "Provider parity",
                  updated_at: "刚刚",
                  turn_count: 2,
                  cwd: "/home/lyc/project/AgentHub",
                  last_user_text: "检查 Codex 工具面",
                },
              ],
        active_thread_id: cwd === "/workspace/other" ? null : "thread_alpha",
      } as TData);
    }
    if (request.action === "thread.resume") {
      return createBridgeSuccess(request, {
        thread: {
          thread_id: "thread_alpha",
          name: "Provider parity",
          updated_at: "刚刚",
          turn_count: 2,
        },
        turns: [
          {
            timestamp: "2026-04-27T09:00:00Z",
            user_text: "检查 Codex 工具面",
            assistant_text: "工具面已载入",
          },
        ],
        history: [],
        state: {},
      } as TData);
    }
    if (request.action === "settings.get") {
      return createBridgeSuccess(request, {
        model: "gpt-5.5",
        providerLabel: "openai | gpt-5.5 | responses",
        browserHeadless: true,
        pluginAutoLoad: true,
        workspaceRoot: this.workspaceRoot,
        workspaceTrust: "trusted",
        runtimePolicy: {
          approval_policy: "on-request",
          sandbox_mode: "workspace-write",
        },
      } as TData);
    }
    if (request.action === "approval.list") {
      return createBridgeSuccess(request, {
        approvals: [
          {
            approval_id: "approval_alpha",
            title: "Run shell command",
            risk: "medium",
            trace_id: "trace_alpha",
            status: "pending",
          },
        ],
      } as TData);
    }
    if (request.action === "plugin.list") {
      return createBridgeSuccess(request, {
        plugins: [
          {
            plugin_id: "local_tools",
            title: "Local tools",
            enabled: true,
            health: "ready",
          },
        ],
      } as TData);
    }
    if (request.action === "connector.list") {
      return createBridgeSuccess(request, {
        connectors: [
          {
            connector_key: "local_shell",
            plugin_name: "local",
            display_name: "Local shell",
            connector_kind: "tool",
            supports_webhook: false,
            supports_polling: false,
            supports_actions: true,
            enabled: true,
            health: "ready",
          },
        ],
      } as TData);
    }
    if (request.action === "chat.send") {
      return createBridgeSuccess(request, {
        accepted: true,
        message_id: "msg_alpha",
        thread_id: "thread_alpha",
        cwd: (request.payload as { cwd?: string }).cwd,
        workspaceRoots: (request.payload as { workspaceRoots?: string[] }).workspaceRoots ?? [],
        user_text: (request.payload as { text?: string }).text ?? "",
        assistant_text: "已创建任务。",
      } as TData);
    }
    if (request.action === "config.apply") {
      this.workspaceRoot = String((request.payload as { workspaceRoot?: string }).workspaceRoot ?? this.workspaceRoot);
      return createBridgeSuccess(request, {
        applied: true,
        status: "applied",
        appliedFields: ["workspaceRoot"],
        blockedFields: [],
        validation: {
          changedFields: ["workspaceRoot"],
          applyableFields: ["workspaceRoot"],
          blocked: [],
          blockedFields: [],
          warnings: [],
          applyPath: [{ field: "workspaceRoot", handler: "runtime.set_cwd" }],
          restart: {
            required: false,
            reasons: [],
            allowed: false,
            mode: "manual",
          },
        },
        restart: {
          required: false,
          reasons: [],
          allowed: false,
          mode: "manual",
        },
        settings: {
          model: "gpt-5.5",
          providerLabel: "openai | gpt-5.5 | responses",
          browserHeadless: true,
          pluginAutoLoad: true,
          workspaceRoot: this.workspaceRoot,
          workspaceTrust: "trusted",
          runtimePolicy: {
            approval_policy: "on-request",
            sandbox_mode: "workspace-write",
          },
        },
      } as TData);
    }
    return createBridgeSuccess(request, {} as TData);
  }

  subscribe(_listener: (event: BridgeEvent<Record<string, unknown>>) => void) {
    return () => {};
  }

  async getControlUiBootstrap() {
    throw new Error("not used");
  }

  async getControlUiState() {
    throw new Error("not used");
  }

  async pollGatewayEvents() {
    throw new Error("not used");
  }

  async browserProxy() {
    throw new Error("not used");
  }
}

function createElementWithAdapter(adapter: CodexPageAdapter) {
  const element = document.createElement("codex-agent-page") as HTMLElement & {
    bridgeClient: BridgeClient;
    shadowRoot: ShadowRoot;
    updateComplete?: Promise<unknown>;
  };
  element.bridgeClient = new BridgeClient(adapter);
  document.body.appendChild(element);
  return element;
}

describe("codex-agent-page", () => {
  it("renders the Codex Desktop-style shell from bridge state", async () => {
    const adapter = new CodexPageAdapter();
    const element = createElementWithAdapter(adapter);
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("新对话");
    expect(element.shadowRoot.textContent).toContain("搜索");
    expect(element.shadowRoot.textContent).toContain("插件");
    expect(element.shadowRoot.textContent).toContain("自动化");
    expect(element.shadowRoot.textContent).toContain("项目");
    expect(element.shadowRoot.textContent).toContain("设置");
    expect(element.shadowRoot.textContent).toContain("对话 · AgentHub");
    expect(element.shadowRoot.textContent).toContain("Provider parity");
    expect(element.shadowRoot.textContent).toContain("gpt-5.5");
    expect(element.shadowRoot.textContent).toContain("待审批 1");
    const composer = element.shadowRoot.querySelector("[data-testid='codex-composer']") as HTMLTextAreaElement;
    expect(composer.placeholder).toBe("要求后续变更");
    expect(element.shadowRoot.textContent).toContain("工具面已载入");
    expect(adapter.requests.map((request) => request.action)).toEqual([
      "settings.get",
      "approval.list",
      "plugin.list",
      "connector.list",
      "thread.list",
      "thread.resume",
    ]);
    expect(adapter.requests.find((request) => request.action === "thread.list")?.payload).toEqual({
      limit: 8,
      cwd: "/home/lyc/project/AgentHub",
    });
  });

  it("opens a real project menu and switches workspaceRoot through config.apply", async () => {
    const adapter = new CodexPageAdapter();
    const element = createElementWithAdapter(adapter);
    await flushUi(element);

    const project = Array.from(element.shadowRoot.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("项目"),
    ) as HTMLButtonElement;
    project.click();
    await flushUi(element);

    expect(element.shadowRoot.querySelector("[data-testid='codex-project-panel']")).toBeTruthy();
    expect(element.shadowRoot.textContent).toContain("/home/lyc/project/AgentHub");
    expect(element.shadowRoot.textContent).toContain("已加载 AgentHub 的会话");
    expect(element.shadowRoot.querySelectorAll("[data-testid='codex-project-option']")).toHaveLength(1);

    const input = element.shadowRoot.querySelector("[data-testid='codex-project-root-input']") as HTMLInputElement;
    input.value = "/workspace/other";
    input.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    await flushUi(element);

    const switchProject = Array.from(element.shadowRoot.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("切换项目"),
    ) as HTMLButtonElement;
    switchProject.click();
    await flushUi(element);

    expect(adapter.requests.find((request) => request.action === "config.apply")?.payload).toEqual({
      workspaceRoot: "/workspace/other",
    });
    const threadRequests = adapter.requests.filter((request) => request.action === "thread.list");
    expect(threadRequests.at(-1)?.payload).toEqual({
      limit: 8,
      cwd: "/workspace/other",
    });
    expect(element.shadowRoot.textContent).toContain("对话 · other");
    expect(element.shadowRoot.textContent).toContain("当前项目暂无会话");
  });

  it("dispatches route-change from settings and can reset to a new chat", async () => {
    const adapter = new CodexPageAdapter();
    const element = createElementWithAdapter(adapter);
    const routes: string[] = [];
    element.addEventListener("route-change", ((event: CustomEvent<string>) => {
      routes.push(event.detail);
    }) as EventListener);
    await flushUi(element);

    const newChat = Array.from(element.shadowRoot.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("新对话"),
    ) as HTMLButtonElement;
    const settings = Array.from(element.shadowRoot.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("设置"),
    ) as HTMLButtonElement;
    newChat.click();
    await flushUi(element);
    settings.click();

    expect(element.shadowRoot.textContent).toContain("你好！我在这儿。今天想一起弄点什么？");
    expect(routes).toEqual(["settings"]);
  });

  it("sends composer text through chat.send and appends the assistant response", async () => {
    const adapter = new CodexPageAdapter();
    const element = createElementWithAdapter(adapter);
    await flushUi(element);

    const textarea = element.shadowRoot.querySelector("[data-testid='codex-composer']") as HTMLTextAreaElement;
    textarea.value = "创建一个 hello world";
    textarea.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    await flushUi(element);

    const send = element.shadowRoot.querySelector("button[aria-label='Send']") as HTMLButtonElement;
    send.click();
    await flushUi(element);

    const chatRequest = adapter.requests.find((request) => request.action === "chat.send");
    expect(chatRequest?.payload).toEqual({
      text: "创建一个 hello world",
      thread_id: "thread_alpha",
      cwd: "/home/lyc/project/AgentHub",
      workspaceRoots: ["/home/lyc/project/AgentHub"],
      new_thread: false,
    });
    expect(element.shadowRoot.textContent).toContain("创建一个 hello world");
    expect(element.shadowRoot.textContent).toContain("已创建任务。");
  });

  it("starts a project-scoped new chat with Codex-style cwd and workspaceRoots", async () => {
    const adapter = new CodexPageAdapter();
    const element = createElementWithAdapter(adapter);
    await flushUi(element);

    const newChat = Array.from(element.shadowRoot.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("新对话"),
    ) as HTMLButtonElement;
    newChat.click();
    await flushUi(element);

    const textarea = element.shadowRoot.querySelector("[data-testid='codex-composer']") as HTMLTextAreaElement;
    textarea.value = "从当前项目开始";
    textarea.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    await flushUi(element);

    const send = element.shadowRoot.querySelector("button[aria-label='Send']") as HTMLButtonElement;
    send.click();
    await flushUi(element);

    const chatRequest = adapter.requests.find((request) => request.action === "chat.send");
    expect(chatRequest?.payload).toEqual({
      text: "从当前项目开始",
      thread_id: undefined,
      cwd: "/home/lyc/project/AgentHub",
      workspaceRoots: ["/home/lyc/project/AgentHub"],
      new_thread: true,
    });
  });
});
