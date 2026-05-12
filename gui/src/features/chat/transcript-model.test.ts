import { describe, expect, it } from "vitest";

import { buildTranscriptEntries, formatActivitySummary } from "./transcript-model.ts";

describe("transcript-model", () => {
  it("builds layered transcript entries from turns", () => {
    const entries = buildTranscriptEntries([
      {
        timestamp: "2026-03-28T08:00:00Z",
        user_text: "检查 GitHub workflow",
        commentary_text: "我先读取当前线程上下文。",
        assistant_text: "已定位最近一次 workflow run。",
        activity_events: [
          {
            title: "Browser snapshot",
            status: "success",
            detail: "target=tab_1 | url=https://example.test/dashboard | refs=2",
            kind: "browser",
          },
        ],
      },
    ]);

    expect(entries.map((item) => item.layer)).toEqual(["user", "commentary", "commentary", "final"]);
    expect(entries[2]?.lines.join("\n")).toContain("Browser snapshot");
    expect(entries[2]?.lines.join("\n")).toContain("target=tab_1");
  });

  it("formats activity summaries like the CLI transcript model", () => {
    expect(
      formatActivitySummary({
        title: "Running rg --files",
        status: "running",
        detail: "",
        kind: "command",
      }),
    ).toBe("• Running rg --files");

    expect(
      formatActivitySummary({
        title: "Browser snapshot",
        status: "success",
        detail: "",
        kind: "browser",
      }),
    ).toBe("• Browser snapshot");
  });
});
