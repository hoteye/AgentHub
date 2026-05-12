import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import http from "node:http";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "..", "..");
const DEFAULT_HOST = process.env.AGENTHUB_GUI_BRIDGE_HOST || "127.0.0.1";
const DEFAULT_PORT = Number.parseInt(process.env.AGENTHUB_GUI_BRIDGE_PORT || "8787", 10);
const DEFAULT_BASE_PATH = process.env.AGENTHUB_GUI_BRIDGE_BASE_PATH || "/gui";
const DEFAULT_HEALTH_URL = `http://${DEFAULT_HOST}:${DEFAULT_PORT}${DEFAULT_BASE_PATH}/health`;

function sleep(ms) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, ms));
}

function logPrefix(line) {
  return `[gui-bridge] ${line}`;
}

function healthCheck(url) {
  return new Promise((resolvePromise) => {
    const request = http.get(url, (response) => {
      const ok = response.statusCode && response.statusCode >= 200 && response.statusCode < 300;
      response.resume();
      resolvePromise(Boolean(ok));
    });
    request.on("error", () => resolvePromise(false));
    request.setTimeout(800, () => {
      request.destroy();
      resolvePromise(false);
    });
  });
}

async function waitForHealth(url, timeoutMs) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (await healthCheck(url)) {
      return true;
    }
    await sleep(350);
  }
  return false;
}

function resolveBridgeSpawnCommand() {
  const scriptBase = resolve(REPO_ROOT, "cli", "scripts");
  if (process.platform === "win32") {
    const powershellPath = process.env.AGENTHUB_POWERSHELL || "powershell.exe";
    const scriptPath = resolve(scriptBase, "start_gui_bridge.ps1");
    if (!existsSync(scriptPath)) {
      throw new Error(`missing bridge startup script: ${scriptPath}`);
    }
    return {
      command: powershellPath,
      args: [
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        scriptPath,
        "-Host",
        DEFAULT_HOST,
        "-Port",
        String(DEFAULT_PORT),
        "-BasePath",
        DEFAULT_BASE_PATH,
      ],
    };
  }
  const shellPath = process.env.AGENTHUB_GUI_BRIDGE_SHELL || "bash";
  const scriptPath = resolve(scriptBase, "start_gui_bridge.sh");
  if (!existsSync(scriptPath)) {
    throw new Error(`missing bridge startup script: ${scriptPath}`);
  }
  return {
    command: shellPath,
    args: [
      scriptPath,
      "--host",
      DEFAULT_HOST,
      "--port",
      String(DEFAULT_PORT),
      "--base-path",
      DEFAULT_BASE_PATH,
    ],
  };
}

export async function ensureGuiBridge(options = {}) {
  const healthUrl = options.healthUrl || DEFAULT_HEALTH_URL;
  const timeoutMs = Number.parseInt(String(options.timeoutMs || "15000"), 10);
  const inheritLogs = options.inheritLogs !== false;

  if (await healthCheck(healthUrl)) {
    return {
      owned: false,
      healthUrl,
      dispose: async () => {},
    };
  }

  const { command, args } = resolveBridgeSpawnCommand();
  const child = spawn(command, args, {
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      PYTHONUTF8: "1",
      PYTHONIOENCODING: "utf-8",
    },
    stdio: inheritLogs ? ["ignore", "pipe", "pipe"] : "ignore",
  });

  if (inheritLogs && child.stdout) {
    child.stdout.on("data", (chunk) => {
      process.stdout.write(logPrefix(String(chunk)));
    });
  }
  if (inheritLogs && child.stderr) {
    child.stderr.on("data", (chunk) => {
      process.stderr.write(logPrefix(String(chunk)));
    });
  }

  const ready = await waitForHealth(healthUrl, timeoutMs);
  if (!ready) {
    child.kill("SIGTERM");
    throw new Error(`GUI bridge failed to become healthy within ${timeoutMs}ms: ${healthUrl}`);
  }

  let disposed = false;
  return {
    owned: true,
    healthUrl,
    child,
    dispose: async () => {
      if (disposed) {
        return;
      }
      disposed = true;
      child.kill("SIGTERM");
      await sleep(300);
      if (!child.killed) {
        child.kill("SIGKILL");
      }
    },
  };
}

export function guiBridgeBaseUrl() {
  return `http://${DEFAULT_HOST}:${DEFAULT_PORT}${DEFAULT_BASE_PATH}`;
}
