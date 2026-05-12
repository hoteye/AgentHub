import { spawn, spawnSync, type ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { createServer as createNetServer } from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";

import { createHttpBridgeClient } from "../bridge/client.ts";
import "../features/browser/browser-control-page.ts";

type BrowserRefCard = {
  ref: string;
  text: string;
};

type BrowserTabCard = {
  tab_id: string;
  title: string;
  url: string;
};

type BrowserPageElement = HTMLElement & {
  bridgeClient: ReturnType<typeof createHttpBridgeClient>;
  updateComplete?: Promise<unknown>;
  shadowRoot: ShadowRoot;
};

type GuiLiveExamReport = {
  scenario: string;
  executed_at: string;
  target_url: string;
  target_tab_id: string;
  browser_mode: string;
  headless: boolean;
  profile: string;
  prompt_or_steps: string[];
  final_url: string;
  snapshot_excerpt: string;
  screenshot_path: string;
  pass: boolean;
  failure_category: string | null;
  failure_detail: string | null;
};

const CURRENT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(CURRENT_DIR, "../../..");
const CHROME_PATH = resolveChromePath();
const LIVE_BROWSER_AVAILABLE = resolveLiveBrowserAvailability();
const LIVE_EXAM_REPORT_PATH = String(process.env.AGENTHUB_GUI_LIVE_EXAM_REPORT ?? "").trim();

let bridgeProcess: ChildProcessWithoutNullStreams | null = null;
let bridgeBaseUrl = "";
let bridgeLogs = "";

function selectedTabId(root: ShadowRoot): string {
  const text = pageText(root);
  const match = text.match(/selected=([^\s]+)/i);
  return match?.[1] ?? "";
}

function writeLiveExamReport(report: GuiLiveExamReport) {
  if (!LIVE_EXAM_REPORT_PATH) {
    return;
  }
  mkdirSync(path.dirname(LIVE_EXAM_REPORT_PATH), { recursive: true });
  writeFileSync(LIVE_EXAM_REPORT_PATH, `${JSON.stringify(report, null, 2)}\n`, "utf-8");
}

function resolveChromePath(): string {
  const result = spawnSync("bash", ["-lc", "command -v google-chrome"], {
    cwd: REPO_ROOT,
    encoding: "utf-8",
  });
  return result.status === 0 ? result.stdout.trim() : "";
}

function resolveLiveBrowserAvailability(): boolean {
  const result = spawnSync(
    "bash",
    [
      "-lc",
      `
PYTHON_EXE=""
for candidate in \
  "./.venv/bin/python" \
  "./cli/.venv/bin/python" \
  "$(command -v python3 || true)" \
  "$(command -v python || true)"; do
  if [[ -n "\${candidate}" && -x "\${candidate}" ]]; then
    PYTHON_EXE="\${candidate}"
    break
  fi
done
if [[ -z "\${PYTHON_EXE}" ]]; then
  exit 1
fi
if ! command -v google-chrome >/dev/null 2>&1; then
  exit 1
fi
"\${PYTHON_EXE}" - <<'PY'
import importlib.util
import sys
sys.exit(0 if importlib.util.find_spec("playwright") else 1)
PY
      `,
    ],
    {
      cwd: REPO_ROOT,
      stdio: "ignore",
    },
  );
  return result.status === 0;
}

async function allocatePort(): Promise<number> {
  return await new Promise((resolve, reject) => {
    const server = createNetServer();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close();
        reject(new Error("failed to allocate tcp port"));
        return;
      }
      const port = address.port;
      server.close((closeError) => {
        if (closeError) {
          reject(closeError);
          return;
        }
        resolve(port);
      });
    });
  });
}


async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitFor(
  predicate: () => boolean,
  timeoutMs = 10000,
  intervalMs = 100,
): Promise<void> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (predicate()) {
      return;
    }
    await sleep(intervalMs);
  }
  throw new Error(`condition not met before timeout\n${bridgeLogs}`);
}

async function waitForHealth(url: string): Promise<void> {
  let lastError = "bridge did not become healthy";
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (bridgeProcess?.exitCode !== null) {
      throw new Error(`bridge exited early with code ${bridgeProcess.exitCode}\n${bridgeLogs}`);
    }
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
      lastError = `health returned ${response.status}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await sleep(250);
  }
  throw new Error(`${lastError}\n${bridgeLogs}`);
}

async function flushUi(element: HTMLElement & { updateComplete?: Promise<unknown> }) {
  for (let attempt = 0; attempt < 8; attempt += 1) {
    await Promise.resolve();
    await sleep(50);
    await element.updateComplete;
  }
}

function nestedText(root: ShadowRoot, selector: string): string {
  const element = root.querySelector(selector) as HTMLElement & {
    shadowRoot?: ShadowRoot;
  };
  return element?.shadowRoot?.textContent ?? "";
}

function pageText(root: ShadowRoot): string {
  return root.textContent ?? "";
}

function setInputValue(root: ShadowRoot, selector: string, value: string) {
  const input = root.querySelector(selector) as HTMLInputElement | HTMLSelectElement | null;
  if (!input) {
    throw new Error(`missing input: ${selector}`);
  }
  input.value = value;
  input.dispatchEvent(new Event(input instanceof HTMLSelectElement ? "change" : "input"));
}

function clickButton(root: ShadowRoot, selector: string) {
  const button = root.querySelector(selector) as HTMLButtonElement | null;
  if (!button) {
    throw new Error(`missing button: ${selector}`);
  }
  button.click();
}

function listBrowserRefCards(root: ShadowRoot): BrowserRefCard[] {
  return Array.from(root.querySelectorAll("[data-testid='browser-ref-card']")).map((element) => ({
    ref: (element.getAttribute("data-ref") ?? "").trim(),
    text: element.textContent ?? "",
  }));
}

async function resolveSnapshotRefs(page: BrowserPageElement): Promise<BrowserRefCard[]> {
  const activeTabId = selectedTabId(page.shadowRoot);
  if (!activeTabId) {
    return [];
  }
  const snapshotResponse = await page.bridgeClient.browser.snapshot({ target_id: activeTabId });
  if (!snapshotResponse.ok) {
    return [];
  }
  return (snapshotResponse.data?.refs ?? []).map((item) => ({
    ref: item.ref,
    text: `${item.role} ${item.text ?? item.name ?? item.url ?? ""}`.trim(),
  }));
}

async function waitForBrowserRefs(page: BrowserPageElement, timeoutMs = 30000): Promise<BrowserRefCard[]> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    await flushUi(page);
    const refs = listBrowserRefCards(page.shadowRoot);
    if (refs.length > 0) {
      return refs;
    }
    const snapshotRefs = await resolveSnapshotRefs(page);
    if (snapshotRefs.length > 0) {
      return snapshotRefs;
    }
    clickButton(page.shadowRoot, "[data-testid='browser-snapshot']");
    await sleep(400);
  }
  throw new Error(`browser refs did not appear before timeout\n${pageText(page.shadowRoot)}\n${bridgeLogs}`);
}

async function waitForBrowserRef(page: BrowserPageElement, pattern: RegExp, timeoutMs = 30000): Promise<BrowserRefCard> {
  let matched: BrowserRefCard | null = null;
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    let refs: BrowserRefCard[] = [];
    try {
      refs = await waitForBrowserRefs(page, Math.min(5000, timeoutMs - (Date.now() - started)));
    } catch {
      await sleep(250);
      continue;
    }
    matched = refs.find((item) => pattern.test(item.text)) ?? null;
    if (matched) {
      break;
    }
    await sleep(250);
  }
  if (!matched) {
    throw new Error(`browser ref not found: ${pattern}\n${pageText(page.shadowRoot)}`);
  }
  return matched;
}

async function waitForSnapshotRefs(
  bridgeClient: ReturnType<typeof createHttpBridgeClient>,
  targetId: string,
  timeoutMs = 30000,
  expectedUrlPattern?: RegExp,
): Promise<{ targetId: string; refs: BrowserRefCard[] }> {
  const started = Date.now();
  let activeTargetId = targetId;
  let lastTabs: BrowserTabCard[] = [];
  while (Date.now() - started < timeoutMs) {
    const tabsResponse = await bridgeClient.browser.tabs();
    lastTabs = (tabsResponse.data?.tabs ?? []).map((item) => ({
      tab_id: item.tab_id,
      title: item.title,
      url: item.url,
    }));
    if (expectedUrlPattern) {
      const matchedTab = [...lastTabs].reverse().find((item) =>
        expectedUrlPattern.test(item.url) || expectedUrlPattern.test(item.title),
      );
      if (matchedTab?.tab_id) {
        activeTargetId = matchedTab.tab_id;
      }
    }
    try {
      await bridgeClient.browser.focus({ target_id: activeTargetId });
    } catch {
      // Focus is a best-effort hint to reduce live-browser timing flake.
    }
    const snapshotResponse = await bridgeClient.browser.snapshot({ target_id: activeTargetId });
    const refs = (snapshotResponse.data?.refs ?? []).map((item) => ({
      ref: item.ref,
      text: `${item.role} ${item.text ?? item.name ?? item.url ?? ""}`.trim(),
    }));
    const snapshotLocation = `${String(snapshotResponse.data?.title ?? "")} ${String(snapshotResponse.data?.url ?? "")}`;
    if (expectedUrlPattern && snapshotLocation.trim() && !expectedUrlPattern.test(snapshotLocation)) {
      await sleep(500);
      continue;
    }
    if (refs.length > 0) {
      return { targetId: activeTargetId, refs };
    }
    await sleep(500);
  }
  throw new Error(
    `bridge snapshot refs did not appear before timeout for ${activeTargetId}; tabs=${JSON.stringify(lastTabs)}`,
  );
}

async function waitForSnapshotRef(
  bridgeClient: ReturnType<typeof createHttpBridgeClient>,
  targetId: string,
  pattern: RegExp,
  timeoutMs = 30000,
  expectedUrlPattern?: RegExp,
): Promise<{ targetId: string; ref: BrowserRefCard }> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    let snapshot:
      | {
          targetId: string;
          refs: BrowserRefCard[];
        }
      | null = null;
    try {
      snapshot = await waitForSnapshotRefs(
        bridgeClient,
        targetId,
        Math.min(5000, timeoutMs - (Date.now() - started)),
        expectedUrlPattern,
      );
    } catch {
      await sleep(250);
      continue;
    }
    const matched = snapshot.refs.find((item) => pattern.test(item.text)) ?? null;
    if (matched) {
      return {
        targetId: snapshot.targetId,
        ref: matched,
      };
    }
    await sleep(250);
  }
  throw new Error(`bridge snapshot ref not found: ${pattern}`);
}

function findSnapshotRef(refs: BrowserRefCard[], pattern: RegExp): BrowserRefCard | null {
  return refs.find((item) => pattern.test(item.text)) ?? null;
}

async function waitForSnapshotText(
  bridgeClient: ReturnType<typeof createHttpBridgeClient>,
  targetId: string,
  predicate: (text: string) => boolean,
  timeoutMs = 30000,
): Promise<{ url: string; text: string }> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const snapshotResponse = await bridgeClient.browser.snapshot({ target_id: targetId });
    if (snapshotResponse.ok) {
      const snapshotText = String((snapshotResponse.data as { text?: string } | null)?.text ?? "");
      if (predicate(snapshotText)) {
        return {
          url: String((snapshotResponse.data as { url?: string } | null)?.url ?? ""),
          text: snapshotText,
        };
      }
    }
    await sleep(500);
  }
  throw new Error(`bridge snapshot text condition not met for ${targetId}`);
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
  const started = Date.now();
  let lastTabs: BrowserTabCard[] = [];
  const excludedTabIds = options?.excludeTabIds ?? new Set<string>();
  while (Date.now() - started < timeoutMs) {
    const tabsResponse = await bridgeClient.browser.tabs();
    lastTabs = (tabsResponse.data?.tabs ?? []).map((item) => ({
      tab_id: item.tab_id,
      title: item.title,
      url: item.url,
    }));
    const matches = lastTabs.filter((item) => pattern.test(item.url) || pattern.test(item.title));
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
    await sleep(250);
  }
  throw new Error(`browser tab not found: ${pattern}; tabs=${JSON.stringify(lastTabs)}`);
}

async function ensureGuiSelectedTab(
  page: BrowserPageElement,
  targetId: string,
  timeoutMs = 30000,
): Promise<void> {
  clickButton(page.shadowRoot, "[data-testid='browser-refresh']");
  await waitFor(
    () => selectedTabId(page.shadowRoot) === targetId,
    timeoutMs,
    250,
  );
}

async function performTypeAction(
  root: ShadowRoot,
  {
    ref,
    value,
    expectedText,
  }: {
    ref: string;
    value: string;
    expectedText: string;
  },
): Promise<void> {
  setInputValue(root, "[data-testid='browser-action-kind']", "type");
  setInputValue(root, "[data-testid='browser-action-ref']", ref);
  setInputValue(root, "[data-testid='browser-action-value']", value);
  clickButton(root, "[data-testid='browser-act']");
  await waitFor(() => pageText(root).includes(expectedText), 20000, 200);
}

async function performClickAction(
  root: ShadowRoot,
  {
    ref,
    expectedText,
  }: {
    ref: string;
    expectedText: string;
  },
): Promise<void> {
  setInputValue(root, "[data-testid='browser-action-kind']", "click");
  setInputValue(root, "[data-testid='browser-action-ref']", ref);
  clickButton(root, "[data-testid='browser-act']");
  await waitFor(() => pageText(root).includes(expectedText), 20000, 200);
}

const describeLive = LIVE_BROWSER_AVAILABLE ? describe : describe.skip;

describeLive("gui browser live exam", () => {
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
    await waitForHealth(`${bridgeBaseUrl}/health`);
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

  it("drives DemoQA register flow from the browser GUI page", async () => {
    const targetUrl = "https://demoqa.com/register";
    const targetPattern = /demoqa\.com\/register|toolsqa/i;
    const steps = [
      "start live browser from GUI browser page",
      `open ${targetUrl}`,
      "type Alpha into First Name",
      "type Operator into Last Name",
      "type alpha001 into UserName",
      "type Secret@123 into Password",
      "click Register",
      "wait for reCaptcha validation warning",
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
    let finalUrl = "";
    let snapshotExcerpt = "";
    let screenshotPath = "";
    let targetId = "";
    try {
      document.body.appendChild(browserPage);
      await flushUi(browserPage);

      expect(browserPage).toBeTruthy();
      await waitFor(() => pageText(browserPage.shadowRoot).includes("浏览器状态与页签"), 10000, 100);

      clickButton(browserPage.shadowRoot, "[data-testid='browser-start']");
      await waitFor(() => pageText(browserPage.shadowRoot).includes("running=true"), 20000, 200);
      expect(nestedText(browserPage.shadowRoot, "[data-testid='browser-result-feedback']")).toContain("浏览器已启动");

      const existingDemoqaTabs = new Set(
        ((await directBridgeClient.browser.tabs()).data?.tabs ?? [])
          .filter((item) => /demoqa\.com\/register|toolsqa/i.test(`${item.title} ${item.url}`))
          .map((item) => item.tab_id),
      );
      setInputValue(browserPage.shadowRoot, "[data-testid='browser-open-url']", targetUrl);
      clickButton(browserPage.shadowRoot, "[data-testid='browser-open']");
      let matchedTab: BrowserTabCard;
      try {
        matchedTab = await waitForBrowserTab(directBridgeClient, targetPattern, 30000, {
          preferSelectedTabId: () => selectedTabId(browserPage.shadowRoot),
          excludeTabIds: existingDemoqaTabs,
        });
      } catch {
        const fallbackOpen = await directBridgeClient.browser.open({ url: targetUrl });
        expect(fallbackOpen.ok).toBe(true);
        matchedTab = await waitForBrowserTab(directBridgeClient, targetPattern, 30000, {
          preferSelectedTabId: () => selectedTabId(browserPage.shadowRoot),
          excludeTabIds: existingDemoqaTabs,
        });
      }
      targetId = matchedTab.tab_id;
      await ensureGuiSelectedTab(browserPage, targetId, 30000);
      targetId = selectedTabId(browserPage.shadowRoot) || targetId;

      const firstNameRef = await waitForSnapshotRef(directBridgeClient, targetId, /first name/i, 70000, targetPattern);
      const lastNameRef = await waitForSnapshotRef(directBridgeClient, targetId, /last name/i, 70000, targetPattern);
      const userNameRef = await waitForSnapshotRef(directBridgeClient, targetId, /username/i, 70000, targetPattern);
      const passwordRef = await waitForSnapshotRef(directBridgeClient, targetId, /password/i, 70000, targetPattern);
      const registerRef = await waitForSnapshotRef(directBridgeClient, targetId, /\bregister\b/i, 70000, targetPattern);
      targetId = registerRef.targetId;

      await performTypeAction(browserPage.shadowRoot, {
        ref: firstNameRef.ref.ref,
        value: "Alpha",
        expectedText: "Alpha",
      });
      await performTypeAction(browserPage.shadowRoot, {
        ref: lastNameRef.ref.ref,
        value: "Operator",
        expectedText: "Operator",
      });
      await performTypeAction(browserPage.shadowRoot, {
        ref: userNameRef.ref.ref,
        value: "alpha001",
        expectedText: "alpha001",
      });
      await performTypeAction(browserPage.shadowRoot, {
        ref: passwordRef.ref.ref,
        value: "Secret@123",
        expectedText: "Secret@123",
      });
      setInputValue(browserPage.shadowRoot, "[data-testid='browser-action-kind']", "click");
      setInputValue(browserPage.shadowRoot, "[data-testid='browser-action-ref']", registerRef.ref.ref);
      clickButton(browserPage.shadowRoot, "[data-testid='browser-act']");
      const finalSnapshot = await waitForSnapshotText(
        directBridgeClient,
        targetId,
        (text) =>
          text.includes("Please verify reCaptcha to register!")
          && text.includes('textbox "First Name": Alpha')
          && text.includes('textbox "Last Name": Operator')
          && text.includes('textbox "UserName": alpha001'),
        45000,
      );
      finalUrl = finalSnapshot.url;
      snapshotExcerpt = finalSnapshot.text.slice(0, 2000);

      clickButton(browserPage.shadowRoot, "[data-testid='browser-screenshot']");
      await waitFor(
        () => nestedText(browserPage.shadowRoot, "[data-testid='browser-artifact-feedback']").includes(".png"),
        20000,
        250,
      );
      const screenshotFeedback = nestedText(browserPage.shadowRoot, "[data-testid='browser-artifact-feedback']");
      const screenshotMatch = screenshotFeedback.match(/\/\S+\.png/) ?? [];
      screenshotPath = screenshotMatch[0] ?? "";
      expect(screenshotPath).toBeTruthy();
      expect(existsSync(screenshotPath)).toBe(true);

      const finalSnapshotResponse = await directBridgeClient.browser.snapshot({ target_id: targetId });
      expect(finalSnapshotResponse.ok).toBe(true);
      expect(finalUrl).toContain("register");
      expect(snapshotExcerpt).toContain("Please verify reCaptcha to register!");

      clickButton(browserPage.shadowRoot, "[data-testid='browser-stop']");
      await waitFor(() => pageText(browserPage.shadowRoot).includes("running=false"), 20000, 200);

      writeLiveExamReport({
        scenario: "gui-browser-live-demoqa-operator",
        executed_at: new Date().toISOString(),
        target_url: targetUrl,
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
      writeLiveExamReport({
        scenario: "gui-browser-live-demoqa-operator",
        executed_at: new Date().toISOString(),
        target_url: targetUrl,
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
