const { contextBridge } = require("electron");


contextBridge.exposeInMainWorld("agenthubDesktop", {
  desktop: true,
});
