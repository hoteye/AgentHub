import { describe, expect, it } from "vitest";

import { errorFeedback, successFeedback } from "../state/operation-feedback.ts";
import "./operation-feedback-view.ts";

describe("operation-feedback-view", () => {
  it("renders inline feedback with level and message", async () => {
    const element = document.createElement("operation-feedback-view") as HTMLElement & {
      feedback: { level: string; message: string };
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.feedback = successFeedback("已保存");
    document.body.appendChild(element);
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("success");
    expect(element.shadowRoot.textContent).toContain("已保存");
  });

  it("renders stacked titled feedback with surface styling", async () => {
    const element = document.createElement("operation-feedback-view") as HTMLElement & {
      feedback: { level: string; message: string };
      title: string;
      variant: string;
      surface: boolean;
      shadowRoot: ShadowRoot;
      updateComplete?: Promise<unknown>;
    };
    element.feedback = errorFeedback("bridge 不可用");
    element.title = "执行回显";
    element.variant = "stack";
    element.surface = true;
    document.body.appendChild(element);
    await element.updateComplete;

    const wrapper = element.shadowRoot.querySelector(".wrapper") as HTMLElement;
    expect(wrapper.className).toContain("stack");
    expect(wrapper.className).toContain("surface");
    expect(element.shadowRoot.textContent).toContain("执行回显");
    expect(element.shadowRoot.textContent).toContain("bridge 不可用");
  });
});
