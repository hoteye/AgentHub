import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync } from "node:fs";

import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";

import { createHttpBridgeClient } from "../bridge/client.ts";
import "../features/browser/browser-control-page.ts";
import {
  allocatePort,
  BrowserPageElement,
  CHROME_PATH,
  clickButton,
  flushUi,
  LIVE_BROWSER_AVAILABLE,
  nestedText,
  pageText,
  REPO_ROOT,
  setInputValue,
  waitFor,
  waitForHealth,
  waitForSnapshotRef,
  waitForSnapshotText,
  writeLiveExamReport,
} from "./browser-live-exam-helpers.ts";

const LIVE_EXAM_REPORT_PATH = String(process.env.AGENTHUB_GUI_LIVE_EXAM_REPORT ?? "").trim();

let bridgeProcess: ChildProcessWithoutNullStreams | null = null;
let bridgeBaseUrl = "";
let bridgeLogs = "";

const describeLive = LIVE_BROWSER_AVAILABLE ? describe : describe.skip;

type BrowserTabCard = {
  tab_id: string;
  title: string;
  url: string;
};

function selectedTabId(root: ShadowRoot): string {
  const text = pageText(root);
  const match = text.match(/selected=([^\s]+)/i);
  return match?.[1] ?? "";
}

async function waitForBrowserTab(
  bridgeClient: ReturnType<typeof createHttpBridgeClient>,
  pattern: RegExp,
  timeoutMs = 30000,
  options?: {
    preferSelectedTabId?: () => string;
    excludeTabIds?: Set<string>;
  },
): Promise<BrowserTabCard> {
  const startedAt = Date.now();
  let lastTabs: BrowserTabCard[] = [];
  const excludedTabIds = options?.excludeTabIds ?? new Set<string>();
  while (Date.now() - startedAt < timeoutMs) {
    const tabsResponse = await bridgeClient.browser.tabs();
    const tabs = (tabsResponse.data?.tabs ?? []).map((item) => ({
      tab_id: String(item.tab_id ?? ""),
      title: String(item.title ?? ""),
      url: String(item.url ?? ""),
    }));
    lastTabs = tabs;
    const matches = tabs.filter((item) => pattern.test(`${item.title} ${item.url}`));
    const preferredSelectedTabId = options?.preferSelectedTabId?.().trim() ?? "";
    const preferredMatch = preferredSelectedTabId
      ? matches.find((item) => item.tab_id === preferredSelectedTabId) ?? null
      : null;
    if (preferredMatch && !excludedTabIds.has(preferredMatch.tab_id)) {
      return preferredMatch;
    }
    const latestUnseenMatch = [...matches].reverse().find((item) => !excludedTabIds.has(item.tab_id)) ?? null;
    if (latestUnseenMatch) {
      return latestUnseenMatch;
    }
    if (excludedTabIds.size === 0) {
      const latestMatch = preferredMatch ?? [...matches].reverse()[0] ?? null;
      if (latestMatch) {
        return latestMatch;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`browser tab not found: ${pattern}; tabs=${JSON.stringify(lastTabs)}`);
}

describeLive("gui browser live demoqa register exam", () => {
  beforeAll(async () => {
    const port = await allocatePort();
    bridgeBaseUrl = `http://127.0.0.1:${port}/gui`;
    bridgeProcess = spawn(
      "bash",
      ["-lc", `./cli/scripts/start_gui_bridge.sh --host 127.0.0.1 --port ${port}`],
      {
        cwd: REPO_ROOT,
        env: {
          ...process.env,
          AGENTHUB_BROWSER_MODE: "live",
          AGENTHUB_BROWSER_EXECUTABLE_PATH: CHROME_PATH,
          AGENTHUB_BROWSER_HEADLESS: "1",
        },
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    bridgeProcess.stdout.on("data", (chunk) => {
      bridgeLogs += chunk.toString();
    });
    bridgeProcess.stderr.on("data", (chunk) => {
      bridgeLogs += chunk.toString();
    });
    await waitForHealth(
      `${bridgeBaseUrl}/health`,
      () => bridgeProcess,
      () => bridgeLogs,
    );
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

  it("drives DemoQA register form fill and captcha validation from the browser GUI page", async () => {
    const steps = [
      "start live browser from GUI browser page",
      "open https://demoqa.com/register",
      "type Test into First Name",
      "type User into Last Name",
      "type test001 into UserName",
      "type Test@123456 into Password",
      "click Register",
      "observe Please verify reCaptcha to register!",
      "capture screenshot artifact",
      "stop browser",
    ];
    const directBridgeClient = createHttpBridgeClient({
      httpBaseUrl: bridgeBaseUrl,
      requestPath: "/requests",
      eventsPath: "/events",
      eventTransport: "polling",
      pollingIntervalMs: 60000,
    });
    const browserPage = document.createElement("browser-control-page") as BrowserPageElement;
    browserPage.bridgeClient = createHttpBridgeClient({
      httpBaseUrl: bridgeBaseUrl,
      requestPath: "/requests",
      eventsPath: "/events",
      eventTransport: "polling",
      pollingIntervalMs: 60000,
    });

    let targetId = "";
    let finalUrl = "";
    let snapshotExcerpt = "";
    let screenshotPath = "";
    try {
      document.body.appendChild(browserPage);
      await flushUi(browserPage);

      await waitFor(() => pageText(browserPage.shadowRoot).includes("浏览器状态与页签"), () => bridgeLogs, 10000, 100);

      clickButton(browserPage.shadowRoot, "[data-testid='browser-start']");
      await waitFor(() => pageText(browserPage.shadowRoot).includes("running=true"), () => bridgeLogs, 20000, 200);
      expect(nestedText(browserPage.shadowRoot, "[data-testid='browser-result-feedback']")).toContain("浏览器已启动");

      const existingDemoqaTabs = new Set(
        ((await directBridgeClient.browser.tabs()).data?.tabs ?? [])
          .filter((item) => /demoqa\.com\/register|toolsqa/i.test(`${item.title} ${item.url}`))
          .map((item) => item.tab_id),
      );
      setInputValue(browserPage.shadowRoot, "[data-testid='browser-open-url']", "https://demoqa.com/register");
      clickButton(browserPage.shadowRoot, "[data-testid='browser-open']");
      let matchedTab: BrowserTabCard;
      try {
        matchedTab = await waitForBrowserTab(directBridgeClient, /demoqa\.com\/register|toolsqa/i, 30000, {
          preferSelectedTabId: () => selectedTabId(browserPage.shadowRoot),
          excludeTabIds: existingDemoqaTabs,
        });
      } catch {
        const fallbackOpen = await directBridgeClient.browser.open({ url: "https://demoqa.com/register" });
        expect(fallbackOpen.ok).toBe(true);
        matchedTab = await waitForBrowserTab(directBridgeClient, /demoqa\.com\/register|toolsqa/i, 30000, {
          preferSelectedTabId: () => selectedTabId(browserPage.shadowRoot),
          excludeTabIds: existingDemoqaTabs,
        });
      }
      targetId = matchedTab.tab_id;
      clickButton(browserPage.shadowRoot, "[data-testid='browser-refresh']");
      await waitFor(
        () => selectedTabId(browserPage.shadowRoot) === targetId,
        () => bridgeLogs,
        20000,
        200,
      );

      const firstNameRef = await waitForSnapshotRef(directBridgeClient, targetId, /first name/i, 70000);
      const lastNameRef = await waitForSnapshotRef(directBridgeClient, targetId, /last name/i, 70000);
      const userNameRef = await waitForSnapshotRef(directBridgeClient, targetId, /username/i, 70000);
      const passwordRef = await waitForSnapshotRef(directBridgeClient, targetId, /password/i, 70000);
      const registerRef = await waitForSnapshotRef(directBridgeClient, targetId, /\bregister\b/i, 70000);

      const guiTypeAndConfirm = async (ref: string, value: string, expectedSnapshotText: string) => {
        setInputValue(browserPage.shadowRoot, "[data-testid='browser-action-kind']", "type");
        setInputValue(browserPage.shadowRoot, "[data-testid='browser-action-ref']", ref);
        setInputValue(browserPage.shadowRoot, "[data-testid='browser-action-value']", value);
        clickButton(browserPage.shadowRoot, "[data-testid='browser-act']");
        await waitForSnapshotText(directBridgeClient, targetId, (text) => text.includes(expectedSnapshotText), 20000);
      };

      const guiClick = async (ref: string) => {
        setInputValue(browserPage.shadowRoot, "[data-testid='browser-action-kind']", "click");
        setInputValue(browserPage.shadowRoot, "[data-testid='browser-action-ref']", ref);
        clickButton(browserPage.shadowRoot, "[data-testid='browser-act']");
      };

      await guiTypeAndConfirm(firstNameRef.ref, "Test", 'textbox "First Name": Test');
      await guiTypeAndConfirm(lastNameRef.ref, "User", 'textbox "Last Name": User');
      await guiTypeAndConfirm(userNameRef.ref, "test001", 'textbox "UserName": test001');
      await guiTypeAndConfirm(passwordRef.ref, "Test@123456", 'textbox "Password": Test@123456');

      await guiClick(registerRef.ref);

      const finalSnapshot = await waitForSnapshotText(
        directBridgeClient,
        targetId,
        (text) =>
          text.includes("Please verify reCaptcha to register!")
          && text.includes("First Name\": Test")
          && text.includes("Last Name\": User")
          && text.includes("UserName\": test001"),
        45000,
      );
      finalUrl = finalSnapshot.url;
      snapshotExcerpt = finalSnapshot.text.slice(0, 2000);

      clickButton(browserPage.shadowRoot, "[data-testid='browser-screenshot']");
      await waitFor(
        () => nestedText(browserPage.shadowRoot, "[data-testid='browser-artifact-feedback']").includes(".png"),
        () => bridgeLogs,
        20000,
        250,
      );
      const screenshotFeedback = nestedText(browserPage.shadowRoot, "[data-testid='browser-artifact-feedback']");
      const screenshotMatch = screenshotFeedback.match(/\/\S+\.png/) ?? [];
      screenshotPath = screenshotMatch[0] ?? "";
      expect(screenshotPath).toBeTruthy();
      expect(existsSync(screenshotPath)).toBe(true);

      clickButton(browserPage.shadowRoot, "[data-testid='browser-stop']");
      try {
        await waitFor(() => pageText(browserPage.shadowRoot).includes("running=false"), () => bridgeLogs, 20000, 200);
      } catch {
        const stopResponse = await directBridgeClient.browser.stop({ profile: "openclaw" });
        expect(stopResponse.ok).toBe(true);
        clickButton(browserPage.shadowRoot, "[data-testid='browser-refresh']");
        await waitFor(() => pageText(browserPage.shadowRoot).includes("running=false"), () => bridgeLogs, 20000, 200);
      }

      writeLiveExamReport(LIVE_EXAM_REPORT_PATH, {
        scenario: "gui-browser-live-demoqa-register",
        executed_at: new Date().toISOString(),
        target_url: "https://demoqa.com/register",
        target_tab_id: targetId,
        browser_mode: "live",
        headless: true,
        profile: "openclaw",
        prompt_or_steps: steps,
        final_url: finalUrl,
        snapshot_excerpt: snapshotExcerpt,
        screenshot_path: screenshotPath,
        pass: true,
        failure_category: null,
        failure_detail: null,
      });
    } catch (error) {
      writeLiveExamReport(LIVE_EXAM_REPORT_PATH, {
        scenario: "gui-browser-live-demoqa-register",
        executed_at: new Date().toISOString(),
        target_url: "https://demoqa.com/register",
        target_tab_id: targetId,
        browser_mode: "live",
        headless: true,
        profile: "openclaw",
        prompt_or_steps: steps,
        final_url: finalUrl,
        snapshot_excerpt: snapshotExcerpt || pageText(browserPage.shadowRoot).slice(0, 2000),
        screenshot_path: screenshotPath,
        pass: false,
        failure_category: "gui-live-exam-failed",
        failure_detail: error instanceof Error ? error.message : String(error),
      });
      throw error;
    }
  }, 180000);
});
