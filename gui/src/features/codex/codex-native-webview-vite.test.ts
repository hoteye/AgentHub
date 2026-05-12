import { describe, expect, it } from "vitest";

import {
  agentHubCodexWebviewConfigScript,
  injectAgentHubCodexBridgeShim,
  resolveAgentHubWorkspaceRoot,
  resolveCodexNativeWebviewDir,
} from "../../../vite.config.ts";

describe("codex native webview vite helpers", () => {
  it("injects the AgentHub bridge shim before the Codex module entry", () => {
    const html = [
      "<html><head>",
      '<script type="module" crossorigin src="./assets/index.js"></script>',
      "</head><body></body></html>",
    ].join("");

    const transformed = injectAgentHubCodexBridgeShim(
      html,
      '<script>window.__AGENTHUB_CODEX_WEBVIEW_CONFIG__={"workspaceRoot":"/workspace/demo"};</script>',
    );

    expect(transformed).toContain("__AGENTHUB_CODEX_WEBVIEW_CONFIG__");
    expect(transformed).toContain('<script src="/agenthub-codex-bridge-shim.js"></script>');
    expect(transformed.indexOf("__AGENTHUB_CODEX_WEBVIEW_CONFIG__")).toBeLessThan(
      transformed.indexOf("agenthub-codex-bridge-shim.js"),
    );
    expect(transformed.indexOf("agenthub-codex-bridge-shim.js")).toBeLessThan(
      transformed.indexOf("./assets/index.js"),
    );
    expect(injectAgentHubCodexBridgeShim(transformed)).toBe(transformed);
  });

  it("allows overriding the extracted Codex webview directory", () => {
    expect(resolveCodexNativeWebviewDir({ AGENTHUB_CODEX_WEBVIEW_DIR: "/tmp/codex-webview" })).toBe(
      "/tmp/codex-webview",
    );
  });

  it("resolves the AgentHub workspace root outside the gui package by default", () => {
    expect(resolveAgentHubWorkspaceRoot({}, "/workspace/AgentHub/gui")).toBe("/workspace/AgentHub");
    expect(resolveAgentHubWorkspaceRoot({ AGENTHUB_WORKSPACE_ROOT: "/workspace/custom" }, "/workspace/AgentHub/gui"))
      .toBe("/workspace/custom");
  });

  it("serializes the Codex bridge runtime config", () => {
    expect(agentHubCodexWebviewConfigScript({}, "/workspace/AgentHub/gui")).toContain(
      '"workspaceRoot":"/workspace/AgentHub"',
    );
  });
});
