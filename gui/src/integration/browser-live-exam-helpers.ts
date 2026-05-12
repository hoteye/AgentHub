import { spawnSync, type ChildProcessWithoutNullStreams } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { createHttpBridgeClient } from "../bridge/client.ts";

export type BrowserRefCard = {
  ref: string;
  text: string;
};

export type BrowserPageElement = HTMLElement & {
  bridgeClient: ReturnType<typeof createHttpBridgeClient>;
  updateComplete?: Promise<unknown>;
  shadowRoot: ShadowRoot;
};

export type GuiLiveExamReport = {
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
export const REPO_ROOT = path.resolve(CURRENT_DIR, "../../..");
export const CHROME_PATH = resolveChromePath();
export const LIVE_BROWSER_AVAILABLE = resolveLiveBrowserAvailability();

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

export async function allocatePort(): Promise<number> {
  return await new Promise((resolve, reject) => {
    const server = createServer();
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

export async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

export async function waitFor(
  predicate: () => boolean,
  getLogs: () => string,
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
  throw new Error(`condition not met before timeout\n${getLogs()}`);
}

export async function waitForHealth(
  url: string,
  getBridgeProcess: () => ChildProcessWithoutNullStreams | null,
  getLogs: () => string,
): Promise<void> {
  let lastError = "bridge did not become healthy";
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const bridgeProcess = getBridgeProcess();
    if (bridgeProcess?.exitCode !== null) {
      throw new Error(`bridge exited early with code ${bridgeProcess.exitCode}\n${getLogs()}`);
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
  throw new Error(`${lastError}\n${getLogs()}`);
}

export async function flushUi(element: HTMLElement & { updateComplete?: Promise<unknown> }) {
  for (let attempt = 0; attempt < 8; attempt += 1) {
    await Promise.resolve();
    await sleep(50);
    await element.updateComplete;
  }
}

export function nestedText(root: ShadowRoot, selector: string): string {
  const element = root.querySelector(selector) as HTMLElement & {
    shadowRoot?: ShadowRoot;
  };
  return element?.shadowRoot?.textContent ?? "";
}

export function pageText(root: ShadowRoot): string {
  return root.textContent ?? "";
}

export function setInputValue(root: ShadowRoot, selector: string, value: string) {
  const input = root.querySelector(selector) as HTMLInputElement | HTMLSelectElement | null;
  if (!input) {
    throw new Error(`missing input: ${selector}`);
  }
  input.value = value;
  input.dispatchEvent(new Event(input instanceof HTMLSelectElement ? "change" : "input"));
}

export function clickButton(root: ShadowRoot, selector: string) {
  const button = root.querySelector(selector) as HTMLButtonElement | null;
  if (!button) {
    throw new Error(`missing button: ${selector}`);
  }
  button.click();
}

export function selectedTabId(root: ShadowRoot): string {
  const text = pageText(root);
  const match = text.match(/selected=([^\s]+)/i);
  return match?.[1] ?? "";
}

export function writeLiveExamReport(reportPath: string, report: GuiLiveExamReport) {
  if (!reportPath) {
    return;
  }
  mkdirSync(path.dirname(reportPath), { recursive: true });
  writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf-8");
}

export async function resolveSnapshotRefs(
  bridgeClient: ReturnType<typeof createHttpBridgeClient>,
  targetId: string,
): Promise<BrowserRefCard[]> {
  const snapshotResponse = await bridgeClient.browser.snapshot({ target_id: targetId });
  if (!snapshotResponse.ok) {
    return [];
  }
  return (snapshotResponse.data?.refs ?? []).map((item) => ({
    ref: item.ref,
    text: `${item.role} ${item.text ?? item.name ?? item.url ?? ""}`.trim(),
  }));
}

export async function waitForSnapshotRefs(
  bridgeClient: ReturnType<typeof createHttpBridgeClient>,
  targetId: string,
  timeoutMs = 30000,
): Promise<BrowserRefCard[]> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const refs = await resolveSnapshotRefs(bridgeClient, targetId);
    if (refs.length > 0) {
      return refs;
    }
    await sleep(500);
  }
  throw new Error(`bridge snapshot refs did not appear before timeout for ${targetId}`);
}

export async function waitForSnapshotRef(
  bridgeClient: ReturnType<typeof createHttpBridgeClient>,
  targetId: string,
  pattern: RegExp,
  timeoutMs = 30000,
): Promise<BrowserRefCard> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    let refs: BrowserRefCard[] = [];
    try {
      refs = await waitForSnapshotRefs(bridgeClient, targetId, Math.min(5000, timeoutMs - (Date.now() - started)));
    } catch {
      await sleep(250);
      continue;
    }
    const matched = refs.find((item) => pattern.test(item.text)) ?? null;
    if (matched) {
      return matched;
    }
    await sleep(250);
  }
  throw new Error(`bridge snapshot ref not found: ${pattern}`);
}

export async function waitForSnapshotText(
  bridgeClient: ReturnType<typeof createHttpBridgeClient>,
  targetId: string,
  predicate: (text: string) => boolean,
  timeoutMs = 30000,
): Promise<{ url: string; text: string }> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const snapshotResponse = await bridgeClient.browser.snapshot({ target_id: targetId });
    if (snapshotResponse.ok) {
      const snapshotText = String(snapshotResponse.data?.text ?? "");
      if (predicate(snapshotText)) {
        return {
          url: String(snapshotResponse.data?.url ?? ""),
          text: snapshotText,
        };
      }
    }
    await sleep(500);
  }
  throw new Error(`bridge snapshot text condition not met for ${targetId}`);
}

export async function performTypeAction(
  root: ShadowRoot,
  getLogs: () => string,
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
  await waitFor(() => pageText(root).includes(expectedText), getLogs, 20000, 200);
}

export async function performClickAction(
  root: ShadowRoot,
  getLogs: () => string,
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
  await waitFor(() => pageText(root).includes(expectedText), getLogs, 20000, 200);
}
