import { describe, expect, it } from "vitest";

import { BridgeClient } from "../../bridge/client.ts";
import type { HostAdapter } from "../../shared/api/mock-host.ts";
import {
  createBridgeFailure,
  createBridgeSuccess,
  type BridgeEvent,
  type BridgeRequest,
  normalizeBridgeEvent,
} from "../../shared/types/bridge.ts";
import "./chat-task-page.ts";

async function flushUi(element: { updateComplete?: Promise<unknown> }) {
  await Promise.resolve();
  await Promise.resolve();
  await element.updateComplete;
  await Promise.resolve();
  await element.updateComplete;
}

async function feedbackText(root: ShadowRoot): Promise<string> {
  const element = root.querySelector("[data-testid='chat-feedback']") as HTMLElement & {
    shadowRoot?: ShadowRoot;
    updateComplete?: Promise<unknown>;
  };
  await element?.updateComplete;
  return element?.shadowRoot?.textContent ?? "";
}

function textByTestId(root: ShadowRoot, testId: string): string {
  return (root.querySelector(`[data-testid='${testId}']`) as HTMLElement | null)?.textContent ?? "";
}

class ThreadAdapter implements HostAdapter {
  async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "thread.list") {
      return createBridgeSuccess(request, {
        threads: [
          {
            thread_id: "thread_demo",
            name: "浏览器排查",
            updated_at: "刚刚",
            turn_count: 2,
            last_user_text: "打开浏览器并检查页面",
            last_assistant_text: "页面已打开",
          },
        ],
        active_thread_id: "thread_demo",
      } as TData);
    }
    if (request.action === "thread.resume") {
      return createBridgeSuccess(request, {
        thread: {
          thread_id: "thread_demo",
          name: "浏览器排查",
          updated_at: "刚刚",
          turn_count: 2,
        },
        history: [
          { role: "user", content: "打开浏览器并检查页面" },
          { role: "assistant", content: "页面已打开" },
        ],
        state: {},
      } as TData);
    }
    if (request.action === "chat.send") {
      return createBridgeSuccess(request, {
        accepted: true,
        message_id: "msg_demo",
        thread_id: "thread_demo",
        user_text: "打开浏览器并检查页面",
        assistant_text: "页面已重新检查",
      } as TData);
    }
    if (request.action === "task.stop") {
      return createBridgeSuccess(request, {
        accepted: true,
        interrupted: true,
      } as TData);
    }
    return createBridgeSuccess(request, {} as TData);
  }

  subscribe(_listener: (event: BridgeEvent<Record<string, unknown>>) => void) {
    return () => {};
  }
}

class RuntimeContextAdapter extends ThreadAdapter {
  override async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "thread.resume") {
      return createBridgeSuccess(request, {
        thread: {
          thread_id: "thread_demo",
          name: "浏览器排查",
          updated_at: "刚刚",
          turn_count: 3,
        },
        turns: [
          {
            timestamp: "2026-03-29T09:00:00Z",
            user_text: "打开浏览器并检查页面",
            commentary_text: "正在分析页面结构",
            assistant_text: "继续处理中",
            status: { status: "running" },
            runtime_state: { phase: "planning", active_tool: "browser.snapshot" },
          },
        ],
        state: {
          status: "running",
          runtime_state: { phase: "planning", active_tool: "browser.snapshot" },
        },
        history: [],
      } as TData);
    }
    return super.request<TData>(request);
  }
}

class EventfulThreadAdapter extends ThreadAdapter {
  private listener: ((event: BridgeEvent<Record<string, unknown>>) => void) | null = null;

  override subscribe(listener: (event: BridgeEvent<Record<string, unknown>>) => void) {
    this.listener = listener;
    return () => {
      if (this.listener === listener) {
        this.listener = null;
      }
    };
  }

  emit(
    event: Partial<BridgeEvent<Record<string, unknown>>> &
      Pick<BridgeEvent<Record<string, unknown>>, "request_id" | "kind" | "name">,
  ) {
    this.listener?.(normalizeBridgeEvent(event));
  }
}

class StopPendingAdapter extends ThreadAdapter {
  override async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "task.stop") {
      return createBridgeSuccess(request, {
        accepted: true,
        interrupted: false,
      } as TData);
    }
    return super.request<TData>(request);
  }
}

class StopFailureAdapter extends ThreadAdapter {
  override async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "task.stop") {
      return createBridgeFailure(request, {
        code: "task_stop_failed",
        message: "停止任务失败：当前没有活动任务",
        retryable: false,
      });
    }
    return super.request<TData>(request);
  }
}

class ChatSendFailureAdapter extends ThreadAdapter {
  override async request<TData = unknown>(request: BridgeRequest<unknown>) {
    if (request.action === "chat.send") {
      return createBridgeFailure(request, {
        code: "chat_send_failed",
        message: "消息发送失败：bridge 暂不可用",
        retryable: true,
      });
    }
    return super.request<TData>(request);
  }
}

describe("chat-task-page", () => {
  it("renders transcript shell", async () => {
    const element = document.createElement("chat-task-page") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    document.body.appendChild(element);
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("对话流");
    expect(element.shadowRoot.textContent).toContain("任务时间线");
  });

  it("submits a draft and appends transcript entries", async () => {
    const element = document.createElement("chat-task-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(new ThreadAdapter());
    document.body.appendChild(element);
    await flushUi(element);

    const textarea = element.shadowRoot.querySelector("textarea") as HTMLTextAreaElement;
    textarea.value = "打开浏览器并检查页面";
    textarea.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    await flushUi(element);

    const button = Array.from(element.shadowRoot.querySelectorAll("button")).find(
      (item) => item.textContent?.includes("发送"),
    ) as HTMLButtonElement;
    button.dispatchEvent(new MouseEvent("click", { bubbles: true, composed: true }));
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("打开浏览器并检查页面");
    await expect(feedbackText(element.shadowRoot)).resolves.toContain("success");
    await expect(feedbackText(element.shadowRoot)).resolves.toContain("已切换到线程 thread_demo");
  });

  it("loads and resumes a recent thread", async () => {
    const element = document.createElement("chat-task-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(new ThreadAdapter());
    document.body.appendChild(element);
    await flushUi(element);

    const thread = Array.from(element.shadowRoot.querySelectorAll(".thread"))[0] as HTMLDivElement;
    thread.click();
    await flushUi(element);

    expect(element.shadowRoot.textContent).toContain("浏览器排查");
    expect(element.shadowRoot.textContent).toContain("页面已打开");
  });

  it("can request stop for the active task", async () => {
    const element = document.createElement("chat-task-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(new ThreadAdapter());
    document.body.appendChild(element);
    await flushUi(element);

    const stopButton = Array.from(element.shadowRoot.querySelectorAll("button")).find(
      (item) => item.textContent?.includes("停止"),
    ) as HTMLButtonElement;
    stopButton.click();
    await flushUi(element);

    await expect(feedbackText(element.shadowRoot)).resolves.toContain("任务已中断");
  });

  it("shows error feedback when stop fails", async () => {
    const element = document.createElement("chat-task-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(new StopFailureAdapter());
    document.body.appendChild(element);
    await flushUi(element);
    await flushUi(element);

    const stopButton = Array.from(element.shadowRoot.querySelectorAll("button")).find(
      (item) => item.textContent?.includes("停止"),
    ) as HTMLButtonElement;
    stopButton.click();
    await flushUi(element);

    await expect(feedbackText(element.shadowRoot)).resolves.toContain("error");
    await expect(feedbackText(element.shadowRoot)).resolves.toContain("停止任务失败：当前没有活动任务");
  });

  it("shows error feedback when chat send fails", async () => {
    const element = document.createElement("chat-task-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(new ChatSendFailureAdapter());
    document.body.appendChild(element);
    await flushUi(element);

    const textarea = element.shadowRoot.querySelector("textarea") as HTMLTextAreaElement;
    textarea.value = "打开浏览器并检查页面";
    textarea.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    await flushUi(element);

    const button = Array.from(element.shadowRoot.querySelectorAll("button")).find(
      (item) => item.textContent?.includes("发送"),
    ) as HTMLButtonElement;
    button.dispatchEvent(new MouseEvent("click", { bubbles: true, composed: true }));
    await flushUi(element);

    await expect(feedbackText(element.shadowRoot)).resolves.toContain("error");
    await expect(feedbackText(element.shadowRoot)).resolves.toContain("消息发送失败：bridge 暂不可用");
  });

  it("shows in-flight status after send until terminal event arrives", async () => {
    const element = document.createElement("chat-task-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(new ThreadAdapter());
    document.body.appendChild(element);
    await flushUi(element);

    const textarea = element.shadowRoot.querySelector("textarea") as HTMLTextAreaElement;
    textarea.value = "继续巡检";
    textarea.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    await flushUi(element);

    const button = Array.from(element.shadowRoot.querySelectorAll("button")).find(
      (item) => item.textContent?.includes("发送"),
    ) as HTMLButtonElement;
    button.dispatchEvent(new MouseEvent("click", { bubbles: true, composed: true }));
    await flushUi(element);

    expect(textByTestId(element.shadowRoot, "chat-task-state")).toContain("执行中");
  });

  it("keeps abort-requested state when stop is accepted but not yet interrupted", async () => {
    const element = document.createElement("chat-task-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(new StopPendingAdapter());
    document.body.appendChild(element);
    await flushUi(element);

    const stopButton = Array.from(element.shadowRoot.querySelectorAll("button")).find(
      (item) => item.textContent?.includes("停止"),
    ) as HTMLButtonElement;
    stopButton.click();
    await flushUi(element);

    expect(textByTestId(element.shadowRoot, "chat-task-state")).toContain("中断请求中");
    await expect(feedbackText(element.shadowRoot)).resolves.toContain("已发送停止请求");
  });

  it("renders live event cards and partial output from bridge events", async () => {
    const adapter = new EventfulThreadAdapter();
    const element = document.createElement("chat-task-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(adapter);
    document.body.appendChild(element);
    await flushUi(element);

    adapter.emit({
      request_id: "req_partial",
      kind: "task_progress",
      name: "assistant_delta",
      summary: "Assistant streaming",
      payload: {
        thread_id: "thread_demo",
        partial_text: "正在读取页面元素",
      },
      status: "ok",
    });
    adapter.emit({
      request_id: "req_tool",
      kind: "tool_event",
      name: "browser.snapshot",
      summary: "Snapshot captured",
      payload: {
        thread_id: "thread_demo",
        target_id: "tab_1",
      },
      status: "ok",
    });
    await flushUi(element);

    expect(textByTestId(element.shadowRoot, "chat-partial-output")).toContain("正在读取页面元素");
    const cards = textByTestId(element.shadowRoot, "chat-live-cards");
    expect(cards).toContain("Task Progress");
    expect(cards).toContain("Tool");
    expect(cards).toContain("browser.snapshot");
  });

  it("shows thread/runtime context details from resume payload", async () => {
    const element = document.createElement("chat-task-page") as HTMLElement & {
      bridgeClient: BridgeClient;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.bridgeClient = new BridgeClient(new RuntimeContextAdapter());
    document.body.appendChild(element);
    await flushUi(element);
    await flushUi(element);

    const context = textByTestId(element.shadowRoot, "chat-runtime-context");
    expect(context).toContain("thread_demo");
    expect(context).toContain("status: running");
    expect(context).toContain("planning");
  });
});
