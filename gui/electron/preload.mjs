import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("agenthubDesktop", {
  runtime: "electron",
  bridgeMode: "http",
});
