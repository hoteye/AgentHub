(function loadAgentHubGuiRuntimeConfig() {
  const params = new URLSearchParams(window.location.search);
  const bridgeMode = params.get("bridge");
  const baseUrl = params.get("baseUrl") || "http://127.0.0.1:8787/gui";

  if (bridgeMode === "http") {
    window.__AGENTHUB_GUI_BRIDGE__ = {
      mode: "http",
      httpBaseUrl: baseUrl,
      requestPath: "/requests",
      eventsPath: "/events",
      eventTransport: "polling",
      pollingIntervalMs: 800,
    };
    return;
  }

  window.__AGENTHUB_GUI_BRIDGE__ = window.__AGENTHUB_GUI_BRIDGE__ || {
    mode: "mock",
  };
})();
