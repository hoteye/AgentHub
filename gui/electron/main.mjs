import { app, BrowserWindow } from "electron";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { ensureGuiBridge, guiBridgeBaseUrl } from "./bridge.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const GUI_ROOT = resolve(__dirname, "..");

let bridgeHandle = null;

app.disableHardwareAcceleration();
app.commandLine.appendSwitch("disable-gpu");
app.commandLine.appendSwitch("disable-software-rasterizer");

function withBridgeQuery(rawUrl) {
  const url = new URL(rawUrl);
  url.searchParams.set("bridge", "http");
  url.searchParams.set("baseUrl", guiBridgeBaseUrl());
  return url.toString();
}

function resolveGuiUrl() {
  const devUrl = process.env.AGENTHUB_GUI_DEV_URL;
  if (devUrl) {
    return withBridgeQuery(devUrl);
  }
  const builtIndex = resolve(GUI_ROOT, "dist", "index.html");
  if (!existsSync(builtIndex)) {
    throw new Error(
      `missing GUI build output: ${builtIndex}. Run the Vite build first or set AGENTHUB_GUI_DEV_URL.`,
    );
  }
  return withBridgeQuery(pathToFileURL(builtIndex).toString());
}

async function createMainWindow() {
  bridgeHandle = await ensureGuiBridge();

  const window = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1180,
    minHeight: 760,
    backgroundColor: "#08131b",
    autoHideMenuBar: true,
    webPreferences: {
      preload: resolve(__dirname, "preload.mjs"),
      contextIsolation: true,
      sandbox: false,
    },
  });

  await window.loadURL(resolveGuiUrl());
  return window;
}

app.whenReady().then(async () => {
  await createMainWindow();
  app.on("activate", async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      await createMainWindow();
    }
  });
});

app.on("before-quit", async () => {
  if (bridgeHandle?.dispose) {
    await bridgeHandle.dispose();
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
