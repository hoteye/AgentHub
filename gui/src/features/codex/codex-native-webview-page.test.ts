import { describe, expect, it } from "vitest";

import "./codex-native-webview-page.ts";

describe("codex-native-webview-page", () => {
  it("loads the Codex native webview mount", async () => {
    const element = document.createElement("codex-native-webview-page") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    const iframe = element.shadowRoot.querySelector("iframe");
    expect(iframe?.getAttribute("src")).toBe("/__codex_webview/index.html");
    expect(iframe?.getAttribute("data-testid")).toBe("codex-native-webview");
  });

  it("tracks bridge shim messages from the iframe", async () => {
    const element = document.createElement("codex-native-webview-page") as HTMLElement & {
      updateComplete?: Promise<unknown>;
      shadowRoot: ShadowRoot;
    };
    document.body.appendChild(element);
    await element.updateComplete;

    window.dispatchEvent(
      new MessageEvent("message", {
        data: {
          source: "agenthub-codex-bridge-shim",
          direction: "from-view",
          message: { type: "fetch" },
        },
      }),
    );
    await element.updateComplete;

    const iframe = element.shadowRoot.querySelector("iframe");
    expect(iframe?.getAttribute("data-bridge-message-count")).toBe("1");
  });
});
