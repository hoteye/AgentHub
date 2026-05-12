import { spawnSync } from "node:child_process";

function hasElectronBinary() {
  const result = spawnSync("pnpm", ["exec", "electron", "--version"], {
    stdio: "pipe",
    env: process.env,
    encoding: "utf-8",
  });
  return result.status === 0;
}

function rebuildElectron() {
  const result = spawnSync("pnpm", ["rebuild", "electron"], {
    stdio: "inherit",
    env: {
      ...process.env,
      ELECTRON_MIRROR: process.env.ELECTRON_MIRROR || "https://npmmirror.com/mirrors/electron/",
      ELECTRON_CUSTOM_DIR: process.env.ELECTRON_CUSTOM_DIR || "37.10.3",
    },
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

if (!hasElectronBinary()) {
  console.log("[electron] binary missing, rebuilding electron package");
  rebuildElectron();
}
