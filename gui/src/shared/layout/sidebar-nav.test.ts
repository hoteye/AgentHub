import { describe, expect, it } from "vitest";

import "./sidebar-nav.ts";

describe("sidebar-nav", () => {
  it("highlights current route and shows approval badge", async () => {
    const element = document.createElement("sidebar-nav") as HTMLElement & {
      currentRoute: string;
      pendingApprovals: number;
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    element.currentRoute = "approvals";
    element.pendingApprovals = 3;
    document.body.appendChild(element);
    await element.updateComplete;

    const current = element.shadowRoot.querySelector('button[aria-current="page"]');
    expect(current?.getAttribute("data-route")).toBe("approvals");
    expect(element.shadowRoot.textContent).toContain("3");
    expect(element.shadowRoot.textContent).toContain("Chat");
    expect(element.shadowRoot.textContent).toContain("Control");
    expect(element.shadowRoot.textContent).toContain("Agent");
    expect(element.shadowRoot.textContent).toContain("Settings");
    expect(element.shadowRoot.querySelector('[data-group="agent"] button[data-route="codex"]')).toBeTruthy();
    expect(element.shadowRoot.textContent).toContain("Codex UI");
  });
});
