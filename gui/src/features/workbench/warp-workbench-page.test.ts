import { afterEach, describe, expect, it } from "vitest";

import "./warp-workbench-page.ts";

async function flushElement(element: { updateComplete?: Promise<unknown> }) {
  await Promise.resolve();
  await Promise.resolve();
  await element.updateComplete;
  await Promise.resolve();
  await element.updateComplete;
}

async function waitFor(
  predicate: () => boolean,
  element: { updateComplete?: Promise<unknown> },
  timeoutMs = 3000,
) {
  const started = Date.now();
  while (!predicate()) {
    if (Date.now() - started > timeoutMs) {
      throw new Error("Timed out waiting for warp workbench state");
    }
    await flushElement(element);
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

async function waitForText(
  element: { shadowRoot: ShadowRoot },
  text: string,
  timeoutMs = 3000,
) {
  const started = Date.now();
  while (!(element.shadowRoot.textContent ?? "").includes(text)) {
    if (Date.now() - started > timeoutMs) {
      throw new Error(`Timed out waiting for ${text}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("warp-workbench-page", () => {
  it("renders transcript and file artifacts from the mock bridge", async () => {
    const element = document.createElement("warp-workbench-page") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await waitFor(() => (element.shadowRoot.querySelectorAll(".artifact-item").length ?? 0) > 0, element);

    expect(element.shadowRoot.textContent).toContain("Command Surface");
    expect(element.shadowRoot.textContent).toContain("Browser snapshot");
    expect(element.shadowRoot.textContent).toContain("tab_1");
    expect(element.shadowRoot.querySelectorAll(".artifact-item").length).toBeGreaterThan(0);
    expect(element.shadowRoot.querySelector("[data-testid='warp-transcript-list']")).toBeTruthy();
  });

  it("submits the composer with Enter and stops active work with Escape", async () => {
    const element = document.createElement("warp-workbench-page") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await waitFor(() => (element.shadowRoot.textContent ?? "").includes("Browser snapshot"), element);

    const composer = element.shadowRoot.querySelector("[data-testid='warp-command-composer']") as HTMLTextAreaElement;
    composer.value = "inspect the latest approval flow";
    composer.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    composer.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, composed: true }));
    const feedback = element.shadowRoot.querySelector("[data-testid='workbench-feedback']") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await waitForText(feedback, "Task submitted");

    expect(composer.value).toBe("");
    expect(feedback.shadowRoot.textContent).toContain("Task submitted");

    composer.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, composed: true }));
    await waitForText(feedback, "Task stopped");

    expect(feedback.shadowRoot.textContent).toContain("Task stopped");
  });

  it("runs shell mode commands through shell.run", async () => {
    const element = document.createElement("warp-workbench-page") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await waitFor(() => (element.shadowRoot.textContent ?? "").includes("Browser snapshot"), element);

    const commandTabs = element.shadowRoot.querySelector("warp-tabs") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    const modeButtons = commandTabs.shadowRoot.querySelectorAll("button");
    (modeButtons[1] as HTMLButtonElement).click();
    await flushElement(element);

    const composer = element.shadowRoot.querySelector("[data-testid='warp-command-composer']") as HTMLTextAreaElement;
    composer.value = "pwd";
    composer.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    composer.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, composed: true }));

    const feedback = element.shadowRoot.querySelector("[data-testid='workbench-feedback']") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    await waitForText(feedback, "Shell command completed");
    await waitFor(() => (element.shadowRoot.textContent ?? "").includes("/home/lyc/project/AgentHub"), element);

    expect(composer.value).toBe("");
    expect(feedback.shadowRoot.textContent).toContain("Shell command completed");
    expect(element.shadowRoot.textContent).toContain("/home/lyc/project/AgentHub");
  });

  it("switches inspector tabs and opens artifact dialogs", async () => {
    const element = document.createElement("warp-workbench-page") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await waitFor(() => (element.shadowRoot.querySelectorAll(".artifact-item").length ?? 0) > 0, element);

    const tabs = element.shadowRoot.querySelectorAll("warp-tabs");
    const inspectorTabs = tabs[1] as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };

    let inspectorButtons = inspectorTabs.shadowRoot.querySelectorAll("button");
    (inspectorButtons[1] as HTMLButtonElement).click();
    await flushElement(element);
    expect(element.shadowRoot.textContent).toContain("Gateway events");

    inspectorButtons = inspectorTabs.shadowRoot.querySelectorAll("button");
    (inspectorButtons[0] as HTMLButtonElement).click();
    await flushElement(element);

    const artifactItem = element.shadowRoot.querySelector(".artifact-item") as HTMLButtonElement;
    artifactItem.dispatchEvent(new MouseEvent("dblclick", { bubbles: true, composed: true }));
    await flushElement(element);

    const dialog = element.shadowRoot.querySelector("warp-dialog") as HTMLElement & {
      open: boolean;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    expect(dialog.open).toBe(true);
    await flushElement(dialog);
    expect(dialog.querySelector("warp-button")).toBeTruthy();

    (dialog.shadowRoot.querySelector("button.close") as HTMLButtonElement).click();
    await flushElement(element);
    expect(dialog.open).toBe(false);
  });
});
