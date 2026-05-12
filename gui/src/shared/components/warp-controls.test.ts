import { afterEach, describe, expect, it } from "vitest";

import "./warp-button.ts";
import "./warp-dialog.ts";
import "./warp-switch.ts";
import "./warp-tabs.ts";

async function flushElement(element: { updateComplete?: Promise<unknown> }) {
  await Promise.resolve();
  await element.updateComplete;
  await Promise.resolve();
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("warp controls", () => {
  it("shows button tooltip content and busy state", async () => {
    const element = document.createElement("warp-button") as HTMLElement & {
      label: string;
      tooltip: string;
      busy: boolean;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.label = "Run";
    element.tooltip = "Run command";
    document.body.appendChild(element);
    await flushElement(element);

    const button = element.shadowRoot.querySelector("button") as HTMLButtonElement;
    button.dispatchEvent(new Event("mouseenter", { bubbles: false, composed: true }));
    await flushElement(element);

    const tooltip = element.shadowRoot.querySelector("warp-tooltip") as HTMLElement & {
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    expect(tooltip).toBeTruthy();
    await flushElement(tooltip);
    expect(tooltip.shadowRoot.textContent).toContain("Run command");

    element.busy = true;
    await flushElement(element);
    expect(element.shadowRoot.textContent).toContain("⋯");
  });

  it("toggles switch state with click and keyboard", async () => {
    const element = document.createElement("warp-switch") as HTMLElement & {
      checked: boolean;
      label: string;
      description: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    const changes: boolean[] = [];
    element.label = "Browser headless";
    element.description = "Persist browser execution mode";
    element.addEventListener("change", (event) => {
      changes.push((event as CustomEvent<{ checked: boolean }>).detail.checked);
    });
    document.body.appendChild(element);
    await flushElement(element);

    const button = element.shadowRoot.querySelector("button") as HTMLButtonElement;
    button.click();
    await flushElement(element);
    expect(element.checked).toBe(true);

    button.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, composed: true }));
    await flushElement(element);
    expect(element.checked).toBe(false);
    expect(changes).toEqual([true, false]);
  });

  it("moves selection with tab keyboard shortcuts", async () => {
    const element = document.createElement("warp-tabs") as HTMLElement & {
      items: Array<{ id: string; label: string; detail?: string }>;
      value: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    const changes: string[] = [];
    element.items = [
      { id: "task", label: "Task" },
      { id: "shell", label: "Shell" },
      { id: "files", label: "Files" },
    ];
    element.value = "task";
    element.addEventListener("change", (event) => {
      changes.push((event as CustomEvent<{ value: string }>).detail.value);
    });
    document.body.appendChild(element);
    await flushElement(element);

    const buttons = element.shadowRoot.querySelectorAll("button");
    (buttons[0] as HTMLButtonElement).dispatchEvent(
      new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true, composed: true }),
    );
    await flushElement(element);

    expect(element.value).toBe("shell");
    expect(changes).toEqual(["shell"]);
    expect((buttons[1] as HTMLButtonElement).getAttribute("aria-selected")).toBe("true");
    expect((buttons[1] as HTMLButtonElement).getAttribute("tabindex")).toBe("0");
  });

  it("dismisses dialog on Escape", async () => {
    const element = document.createElement("warp-dialog") as HTMLElement & {
      open: boolean;
      title: string;
      subtitle: string;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.open = true;
    element.title = "Artifact";
    element.subtitle = "tool output";
    element.innerHTML = "<div>payload</div>";
    document.body.appendChild(element);
    await flushElement(element);

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, composed: true }));
    await flushElement(element);

    expect(element.open).toBe(false);
  });
});
