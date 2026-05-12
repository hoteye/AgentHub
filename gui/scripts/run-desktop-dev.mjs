import { spawn } from "node:child_process";

if (
  process.platform !== "win32"
  && !process.env.DISPLAY
  && !process.env.WAYLAND_DISPLAY
  && !process.env.AGENTHUB_ELECTRON_ALLOW_HEADLESS
) {
  console.error(
    "[electron] desktop:dev requires a graphical session. Set DISPLAY/WAYLAND_DISPLAY, or override with AGENTHUB_ELECTRON_ALLOW_HEADLESS=1 if you know the host can run Electron headlessly.",
  );
  process.exit(1);
}

function waitForLog(child, pattern, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const startedAt = Date.now();
    const onData = (chunk) => {
      const text = String(chunk);
      process.stdout.write(text);
      const match = text.match(pattern);
      if (match) {
        cleanup();
        resolve(match);
      }
      if (Date.now() - startedAt > timeoutMs) {
        cleanup();
        reject(new Error(`Timed out waiting for ${pattern}`));
      }
    };
    const onError = (chunk) => {
      process.stderr.write(String(chunk));
    };
    const onExit = (code) => {
      cleanup();
      reject(new Error(`Process exited before readiness with code ${code}`));
    };
    const cleanup = () => {
      child.stdout?.off("data", onData);
      child.stderr?.off("data", onError);
      child.off("exit", onExit);
    };
    child.stdout?.on("data", onData);
    child.stderr?.on("data", onError);
    child.on("exit", onExit);
  });
}

const preferredPort = process.env.AGENTHUB_GUI_DEV_PORT || "4173";
const vite = spawn("pnpm", ["vite", "--host", "127.0.0.1", "--port", preferredPort], {
  cwd: process.cwd(),
  env: process.env,
  stdio: ["inherit", "pipe", "pipe"],
});

try {
  const match = await waitForLog(vite, /http:\/\/127\.0\.0\.1:(\d+)\//);
  const port = String(match?.[1] || preferredPort);
  const electron = spawn(
    "pnpm",
    ["exec", "electron", "./electron/main.mjs"],
    {
      cwd: process.cwd(),
      env: {
        ...process.env,
        AGENTHUB_GUI_DEV_URL: `http://127.0.0.1:${port}/?bridge=http&baseUrl=http://127.0.0.1:8787/gui`,
      },
      stdio: "inherit",
    },
  );
  electron.on("exit", (code) => {
    if (!vite.killed) {
      vite.kill("SIGTERM");
    }
    process.exit(code ?? 0);
  });
} catch (error) {
  if (!vite.killed) {
    vite.kill("SIGTERM");
  }
  throw error;
}
