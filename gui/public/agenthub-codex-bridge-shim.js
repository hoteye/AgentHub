(function () {
  const BRIDGE_EVENT_SOURCE = "agenthub-codex-bridge-shim";
  const SESSION_ID = `agenthub-${Date.now().toString(36)}`;
  const runtimeConfig = window.__AGENTHUB_CODEX_WEBVIEW_CONFIG__ || {};
  const WORKSPACE_ROOT = normalizePath(runtimeConfig.workspaceRoot || "/workspace");
  const HOME_DIR = normalizePath(runtimeConfig.homeDir || guessHomeDir(WORKSPACE_ROOT));
  const CODEX_HOME = normalizePath(runtimeConfig.codexHome || `${HOME_DIR}/.codex`);
  const WORKSPACE_LABEL = String(runtimeConfig.workspaceLabel || basename(WORKSPACE_ROOT) || "Workspace");
  const THREAD_STORAGE_KEY = "agenthub.codex.nativeWebview.threads.v1";
  const messages = [];
  const nativeFetch = window.fetch.bind(window);
  const sharedObjects = {
    active_workspace_roots: [WORKSPACE_ROOT],
    composer_prefill: null,
    host_config: { id: "local", display_name: "Local", kind: "local" },
    remote_connections: [],
    remote_control_connections: [],
  };
  const defaultConfig = {
    model: null,
    review_model: null,
    model_context_window: null,
    model_auto_compact_token_limit: null,
    model_provider: null,
    approval_policy: null,
    approvals_reviewer: null,
    sandbox_mode: null,
    sandbox_workspace_write: null,
    forced_chatgpt_workspace_id: null,
    forced_login_method: null,
    web_search: null,
    tools: null,
    profile: null,
    profiles: {},
    instructions: null,
    developer_instructions: null,
    compact_prompt: null,
    model_reasoning_effort: null,
    model_reasoning_summary: null,
    service_tier: null,
    model_verbosity: null,
    analytics: null,
    features: {
      remote_connections: false,
    },
    "features.remote_connections": false,
    mcp_servers: {},
    apps: {
      _default: {
        enabled: true,
        destructive_enabled: false,
        open_world_enabled: false,
        default_tools_approval_mode: null,
        default_tools_enabled: null,
        tools: null,
      },
    },
  };

  function defaultConfigResult() {
    return {
      config: currentCodexConfig(),
      origins: {},
      layers: null,
    };
  }
  const workerSubscribers = new Map();
  let systemThemeVariant = "dark";
  const threadState = loadThreadState();
  const providerSelectorState = {
    currentProvider: "",
    currentStatus: "",
    currentModel: "",
    currentReasoningEffort: "",
    providers: [],
    loading: false,
    switchingProvider: "",
  };
  let providerSelectorEnsureScheduled = false;

  installSentryIpcFetchShim();
  installProviderSelector();

  function record(direction, message) {
    const entry = { at: Date.now(), direction, message };
    messages.push(entry);
    if (messages.length > 500) {
      messages.shift();
    }
    window.__AGENTHUB_CODEX_BRIDGE_MESSAGES__ = messages;
    if (window.parent && window.parent !== window) {
      window.parent.postMessage({ source: BRIDGE_EVENT_SOURCE, direction, message }, "*");
    }
    if (message && message.type !== "log-message") {
      console.debug("[AgentHub Codex bridge]", direction, message);
    }
  }

  function sendToView(message) {
    record("to-view", message);
    if (message.type === "shared-object-updated") {
      if (message.value === undefined) {
        delete sharedObjects[message.key];
      } else {
        sharedObjects[message.key] = message.value;
      }
    }
    window.dispatchEvent(
      new MessageEvent("message", {
        data: message,
        origin: window.location.origin,
        source: window,
      }),
    );
  }

  function successFetchResponse(requestId, body, status) {
    sendToView({
      type: "fetch-response",
      requestId,
      responseType: "success",
      status: status || 200,
      headers: { "content-type": "application/json" },
      bodyJsonString: JSON.stringify(body),
    });
  }

  function errorFetchResponse(requestId, error, status) {
    sendToView({
      type: "fetch-response",
      requestId,
      responseType: "error",
      status: status || 500,
      error: error instanceof Error ? error.message : String(error),
    });
  }

  function parseBody(body) {
    if (typeof body !== "string" || body.trim() === "") {
      return null;
    }
    try {
      return JSON.parse(body);
    } catch {
      return body;
    }
  }

  function installSentryIpcFetchShim() {
    window.fetch = async (input, init) => {
      const requestUrl = urlFromFetchInput(input);
      if (requestUrl.startsWith("sentry-ipc://")) {
        record("sentry-ipc-fetch", {
          url: requestUrl,
          method: methodFromFetchInput(input, init),
        });
        return new Response("", {
          status: 200,
          statusText: "OK",
          headers: { "content-type": "text/plain; charset=utf-8" },
        });
      }
      return nativeFetch(input, init);
    };
  }

  function urlFromFetchInput(input) {
    if (typeof input === "string") {
      return input;
    }
    if (input instanceof URL) {
      return input.href;
    }
    return typeof input?.url === "string" ? input.url : "";
  }

  function methodFromFetchInput(input, init) {
    return String(init?.method || input?.method || "GET").toUpperCase();
  }

  function installProviderSelector() {
    injectProviderSelectorStyles();
    window.setTimeout(() => {
      void refreshProviderSelectorState();
    }, 0);
    window.setTimeout(scheduleProviderSelectorEnsure, 500);
    window.setInterval(scheduleProviderSelectorEnsure, 1500);
    const observer = new MutationObserver(scheduleProviderSelectorEnsure);
    observer.observe(document.documentElement, { childList: true, subtree: true });
    document.addEventListener("click", (event) => {
      const target = event.target;
      if (target instanceof Element && target.closest("[data-agenthub-provider-selector]")) {
        return;
      }
      closeProviderSelectorMenu();
    });
  }

  function scheduleProviderSelectorEnsure() {
    if (providerSelectorEnsureScheduled) {
      return;
    }
    providerSelectorEnsureScheduled = true;
    window.setTimeout(() => {
      providerSelectorEnsureScheduled = false;
      ensureProviderSelectorMounted();
    }, 100);
  }

  function injectProviderSelectorStyles() {
    if (document.getElementById("agenthub-provider-selector-style")) {
      return;
    }
    const style = document.createElement("style");
    style.id = "agenthub-provider-selector-style";
    style.textContent = `
      [data-agenthub-provider-menu] {
        background: var(--token-dropdown-background, rgb(41 41 41));
        border: 1px solid var(--token-border, rgb(64 64 64));
        border-radius: 12px;
        box-shadow: 0 12px 36px rgb(0 0 0 / 0.34);
        color: var(--token-foreground, #f5f5f5);
        min-width: 224px;
        overflow: hidden;
        padding: 6px;
        position: fixed;
        z-index: 2147483647;
      }
      [data-agenthub-provider-menu-title] {
        color: var(--token-description-foreground, #a3a3a3);
        font-size: 11px;
        padding: 6px 8px 8px;
      }
      [data-agenthub-provider-menu-item] {
        align-items: center;
        background: transparent;
        border: 0;
        border-radius: 9px;
        color: inherit;
        cursor: pointer;
        display: flex;
        gap: 10px;
        min-height: 38px;
        padding: 7px 8px;
        text-align: left;
        width: 100%;
      }
      [data-agenthub-provider-menu-item]:hover {
        background: var(--token-list-hover-background, rgb(54 54 54));
      }
      [data-agenthub-provider-menu-item][aria-disabled="true"] {
        cursor: default;
        opacity: 0.58;
      }
      [data-agenthub-provider-menu-item][aria-disabled="true"]:hover {
        background: transparent;
      }
      [data-agenthub-provider-name] {
        color: var(--token-foreground, #f5f5f5);
        display: block;
        font-size: 13px;
        line-height: 18px;
      }
      [data-agenthub-provider-meta] {
        color: var(--token-description-foreground, #a3a3a3);
        display: block;
        font-size: 11px;
        line-height: 15px;
      }
      [data-agenthub-provider-check] {
        color: var(--token-text-link-foreground, #8ab4ff);
        flex: 0 0 auto;
        width: 14px;
      }
      [data-agenthub-provider-selector] .agenthub-provider-secondary {
        max-width: 74px;
        overflow: hidden;
        text-overflow: ellipsis;
      }
    `;
    document.head.appendChild(style);
  }

  async function refreshProviderSelectorState() {
    providerSelectorState.loading = true;
    renderProviderSelectorButton();
    try {
      const settings = await callAgentHubBridgeAction("settings.get", {});
      applyProviderSelectorSettings(settings || {});
    } catch (error) {
      record("provider-selector-settings-error", { error: error instanceof Error ? error.message : String(error) });
    } finally {
      providerSelectorState.loading = false;
      renderProviderSelectorButton();
    }
  }

  function applyProviderSelectorSettings(settings) {
    const providerLabel = String(settings.providerLabel || "");
    const parsedCurrent = providerLabel.split("|")[0]?.trim() || "";
    providerSelectorState.currentProvider = String(settings.providerName || parsedCurrent || "").trim();
    providerSelectorState.currentModel = String(settings.model || providerLabel.split("|")[1]?.trim() || "").trim();
    providerSelectorState.currentReasoningEffort = String(settings.reasoningEffort || "").trim();
    providerSelectorState.currentStatus = String(settings.providerStatusState || "").trim();
    providerSelectorState.providers = normalizedProviderSelectorEntries(settings.availableProviders, providerSelectorState.currentProvider);
    if (providerSelectorState.currentProvider && !providerSelectorState.providers.some((item) => item.providerName === providerSelectorState.currentProvider)) {
      providerSelectorState.providers.unshift({
        providerName: providerSelectorState.currentProvider,
        displayName: providerSelectorState.currentProvider,
        defaultModel: providerSelectorState.currentModel,
        statusState: providerSelectorState.currentStatus,
        statusReason: "",
        authReady: true,
        current: true,
      });
    }
    syncNativeModelSelectorLabel();
  }

  function normalizedProviderSelectorEntries(rawProviders, currentProvider) {
    if (!Array.isArray(rawProviders)) {
      return [];
    }
    return rawProviders
      .map((item) => {
        const providerName = String(item?.providerName || item?.provider_name || item?.displayName || "").trim();
        if (!providerName) {
          return null;
        }
        return {
          providerName,
          displayName: String(item.displayName || item.display_name || providerName),
          defaultModel: String(item.defaultModel || item.default_model || ""),
          plannerKind: String(item.plannerKind || item.planner_kind || ""),
          wireApi: String(item.wireApi || item.wire_api || ""),
          statusState: String(item.statusState || item.provider_status_state || ""),
          statusReason: String(item.statusReason || item.provider_status_reason || item.authReason || ""),
          authReady: item.authReady !== false,
          availabilityStatus: String(item.availabilityStatus || ""),
          current: item.current === true || providerName === currentProvider,
        };
      })
      .filter(Boolean);
  }

  async function callAgentHubBridgeAction(action, payload) {
    const config = bridgeTransportConfig();
    if (!config || config.mode !== "http" || !config.httpBaseUrl) {
      return null;
    }
    const requestPath = config.requestPath || "/requests";
    const response = await fetchFromHostPage(`${String(config.httpBaseUrl).replace(/\/$/, "")}${requestPath}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        protocol_version: "v1",
        request_id: randomId("req"),
        action,
        payload: payload || {},
        client: { name: "agenthub-codex-provider-selector", version: "0.1.0" },
      }),
    });
    const result = await response.json();
    if (!response.ok || result.ok !== true) {
      throw new Error(result?.error?.message || `GUI bridge ${action} failed`);
    }
    return result.data || null;
  }

  function ensureProviderSelectorMounted() {
    const modelMount = findModelSelectorMount();
    if (!modelMount || !modelMount.parentElement) {
      return;
    }
    let host = document.querySelector("[data-agenthub-provider-selector]");
    const wasMissing = !host;
    if (!host) {
      host = document.createElement("span");
      host.setAttribute("data-agenthub-provider-selector", "true");
    }
    if (host.parentElement !== modelMount.parentElement || host.nextSibling !== modelMount) {
      modelMount.parentElement.insertBefore(host, modelMount);
    }
    if (wasMissing || !host.querySelector("button")) {
      renderProviderSelectorButton();
    }
    syncNativeModelSelectorLabel();
  }

  function findModelSelectorMount() {
    const buttons = Array.from(document.querySelectorAll("button"));
    const candidates = buttons
      .map((button) => ({ button, rect: button.getBoundingClientRect(), text: button.innerText || "" }))
      .filter((item) => (
        !item.button.closest("[data-agenthub-provider-selector]") &&
        item.rect.width > 80
        && item.rect.height > 20
        && item.rect.y > window.innerHeight * 0.35
        && item.rect.x > window.innerWidth * 0.45
        && /codex|gpt|claude|sonnet|gemini|qwen|deepseek|glm|minimax|model|medium|high|low/i.test(item.text)
      ))
      .sort((left, right) => left.rect.x - right.rect.x);
    const modelButton = candidates[0]?.button || null;
    if (!modelButton) {
      return null;
    }
    return modelButton.parentElement?.tagName === "SPAN" ? modelButton.parentElement : modelButton;
  }

  function renderProviderSelectorButton() {
    const host = document.querySelector("[data-agenthub-provider-selector]");
    if (!host) {
      return;
    }
    const modelButton = findModelSelectorMount()?.querySelector?.("button") || findModelSelectorMount();
    const buttonClass = modelButton?.className || "border-token-border user-select-none no-drag cursor-interaction flex items-center gap-1 border whitespace-nowrap focus:outline-none disabled:cursor-not-allowed disabled:opacity-40 rounded-full text-token-description-foreground enabled:hover:bg-token-list-hover-background border-transparent h-token-button-composer px-2 py-0 text-sm leading-[18px] outline-hidden cursor-interaction min-w-0";
    const label = providerSelectorState.currentProvider || (providerSelectorState.loading ? "provider" : "provider");
    const secondary = providerSelectorSecondaryLabel();
    host.innerHTML = `
      <button type="button" class="${escapeHtml(String(buttonClass))}" aria-label="Select AgentHub provider" aria-haspopup="menu" aria-expanded="false">
        <span class="flex min-w-0 items-center gap-1.5">
          <span class="flex min-w-0 items-center gap-1 tabular-nums">
            <span class="truncate whitespace-nowrap text-token-foreground">${escapeHtml(label)}</span>
          </span>
          <span class="agenthub-provider-secondary shrink-0 text-token-description-foreground">${escapeHtml(secondary)}</span>
        </span>
        ${chevronSvg()}
      </button>
    `;
    const button = host.querySelector("button");
    button?.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      void refreshProviderSelectorState().then(() => {
        const currentButton = host.querySelector("button") || button;
        toggleProviderSelectorMenu(currentButton);
      });
    });
  }

  function providerSelectorSecondaryLabel() {
    if (providerSelectorState.switchingProvider) {
      return "switching";
    }
    if (providerSelectorState.loading && !providerSelectorState.currentStatus) {
      return "loading";
    }
    const state = providerSelectorState.currentStatus;
    if (state === "ready") {
      return "ready";
    }
    if (state === "auth_blocked") {
      return "auth";
    }
    return state || "session";
  }

  function toggleProviderSelectorMenu(anchor) {
    const existing = document.querySelector("[data-agenthub-provider-menu]");
    if (existing) {
      closeProviderSelectorMenu();
      return;
    }
    openProviderSelectorMenu(anchor);
  }

  function openProviderSelectorMenu(anchor) {
    closeProviderSelectorMenu();
    const menu = document.createElement("div");
    menu.setAttribute("data-agenthub-provider-menu", "true");
    menu.innerHTML = providerSelectorMenuHtml();
    document.body.appendChild(menu);
    const rect = anchor.getBoundingClientRect();
    const menuRect = menu.getBoundingClientRect();
    const centeredLeft = rect.left + rect.width / 2 - menuRect.width / 2;
    const left = Math.max(8, Math.min(centeredLeft, window.innerWidth - menuRect.width - 8));
    const aboveTop = rect.top - menuRect.height - 8;
    const top = aboveTop >= 8 ? aboveTop : Math.min(rect.bottom + 8, window.innerHeight - menuRect.height - 8);
    menu.style.left = `${left}px`;
    menu.style.top = `${Math.max(8, top)}px`;
    menu.querySelectorAll("[data-provider-name]").forEach((item) => {
      item.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const providerName = item.getAttribute("data-provider-name") || "";
        void switchAgentHubProvider(providerName);
      });
    });
  }

  function closeProviderSelectorMenu() {
    document.querySelector("[data-agenthub-provider-menu]")?.remove();
  }

  function providerSelectorMenuHtml() {
    const providers = providerSelectorState.providers.length
      ? providerSelectorState.providers
      : [{ providerName: providerSelectorState.currentProvider || "provider", displayName: providerSelectorState.currentProvider || "provider", current: true }];
    return `
      <div data-agenthub-provider-menu-title>AgentHub provider</div>
      ${providers.map((provider) => providerSelectorMenuItemHtml(provider)).join("")}
    `;
  }

  function providerSelectorMenuItemHtml(provider) {
    const current = provider.current || provider.providerName === providerSelectorState.currentProvider;
    const meta = [
      provider.statusState || (provider.authReady ? "ready" : "auth"),
      provider.defaultModel,
    ].filter(Boolean).join(" . ");
    return `
      <button type="button" data-agenthub-provider-menu-item data-provider-name="${escapeHtml(provider.providerName)}">
        <span data-agenthub-provider-check>${current ? "✓" : ""}</span>
        <span>
          <span data-agenthub-provider-name>${escapeHtml(provider.displayName || provider.providerName)}</span>
          <span data-agenthub-provider-meta>${escapeHtml(meta || provider.statusReason || "session provider")}</span>
        </span>
      </button>
    `;
  }

  async function switchAgentHubProvider(providerName) {
    if (!providerName || providerName === providerSelectorState.currentProvider) {
      closeProviderSelectorMenu();
      return;
    }
    providerSelectorState.switchingProvider = providerName;
    renderProviderSelectorButton();
    closeProviderSelectorMenu();
    try {
      const settings = await callAgentHubBridgeAction("settings.update", {
        provider: providerName,
        providerWriteScope: "session",
      });
      applyProviderSelectorSettings(settings || {});
      syncNativeModelSelectorLabel();
    } catch (error) {
      record("provider-selector-switch-error", { providerName, error: error instanceof Error ? error.message : String(error) });
    } finally {
      providerSelectorState.switchingProvider = "";
      renderProviderSelectorButton();
      syncNativeModelSelectorLabel();
    }
  }

  function currentProviderEntry() {
    return providerSelectorState.providers.find((item) => item.providerName === providerSelectorState.currentProvider) || null;
  }

  function currentModelId() {
    return providerSelectorState.currentModel || currentProviderEntry()?.defaultModel || "gpt-5.3-codex";
  }

  function currentProviderName() {
    return providerSelectorState.currentProvider || currentProviderEntry()?.providerName || "agenthub_gui";
  }

  function currentReasoningEffort() {
    return providerSelectorState.currentReasoningEffort || "medium";
  }

  function currentCodexConfig() {
    const model = currentModelId();
    return {
      ...defaultConfig,
      model,
      model_provider: currentProviderName(),
      model_reasoning_effort: currentReasoningEffort(),
    };
  }

  function modelDisplayName(model, providerName) {
    const value = String(model || "").trim();
    const provider = String(providerName || "").trim().toLowerCase();
    if (!value) {
      return "Model";
    }
    const known = {
      "claude-sonnet-4-6": "Claude Sonnet 4.6",
      "deepseek-chat": "DeepSeek Chat",
      "glm-5": "GLM 5",
      "gpt-5.5": "GPT-5.5",
      "gpt-5.4": "GPT-5.4",
      "gpt-5.3-codex": "5.3 Codex",
      "qwen-plus": "Qwen Plus",
      "MiniMax-M2.5": "MiniMax M2.5",
    };
    if (known[value]) {
      return known[value];
    }
    if (provider === "openai" && /^gpt-/i.test(value)) {
      return value.replace(/^gpt/i, "GPT").replace(/-codex$/i, " Codex");
    }
    return value
      .replace(/[_-]+/g, " ")
      .replace(/\b[a-z]/g, (char) => char.toUpperCase());
  }

  function reasoningDisplayName(reasoningEffort) {
    const value = String(reasoningEffort || "").trim().toLowerCase();
    const known = {
      minimal: "Minimal",
      low: "Low",
      medium: "Medium",
      high: "High",
      xhigh: "Extra High",
    };
    return known[value] || (value ? modelDisplayName(value, "") : "Medium");
  }

  function syncNativeModelSelectorLabel() {
    const modelMount = findModelSelectorMount();
    const button = modelMount?.querySelector?.("button") || modelMount;
    if (!(button instanceof HTMLButtonElement)) {
      return;
    }
    const label = modelDisplayName(currentModelId(), currentProviderName());
    const effort = reasoningDisplayName(currentReasoningEffort());
    const primary = button.querySelector(".truncate.whitespace-nowrap.text-token-foreground");
    const secondary = Array.from(button.querySelectorAll(".text-token-description-foreground"))
      .find((item) => !item.classList.contains("agenthub-provider-secondary"));
    if (primary) {
      primary.textContent = label;
    }
    if (secondary) {
      secondary.textContent = effort;
    }
  }

  function chevronSvg() {
    return '<svg width="20" height="21" viewBox="0 0 20 21" fill="none" xmlns="http://www.w3.org/2000/svg" class="icon-2xs text-token-input-placeholder-foreground"><path d="M15.2793 7.71101C15.539 7.45131 15.961 7.45131 16.2207 7.71101C16.4804 7.97071 16.4804 8.39272 16.2207 8.65242L10.4707 14.4024C10.211 14.6621 9.78902 14.6621 9.52932 14.4024L3.77932 8.65242L3.69436 8.54792C3.52385 8.28979 3.55205 7.93828 3.77932 7.71101C4.00659 7.48374 4.3581 7.45554 4.61623 7.62605L4.72073 7.71101L10 12.9903L15.2793 7.71101Z" fill="currentColor" stroke="currentColor" stroke-width="0.6"></path></svg>';
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function normalizePath(value) {
    const normalized = String(value || "").replace(/\\/g, "/").replace(/\/+$/, "");
    return normalized || "/";
  }

  function basename(value) {
    const normalized = normalizePath(value);
    if (normalized === "/") {
      return "/";
    }
    return normalized.slice(normalized.lastIndexOf("/") + 1);
  }

  function guessHomeDir(workspaceRoot) {
    const normalized = normalizePath(workspaceRoot);
    const match = normalized.match(/^(\/home\/[^/]+)\b/);
    return match ? match[1] : "/";
  }

  function codexMethodFromUrl(url) {
    if (typeof url !== "string") {
      return "";
    }
    try {
      const parsed = new URL(url);
      if (parsed.protocol === "vscode:" && parsed.hostname === "codex") {
        return parsed.pathname.replace(/^\/+/, "");
      }
    } catch {
      return "";
    }
    return "";
  }

  function randomId(prefix) {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return `${prefix}_${window.crypto.randomUUID().replace(/-/g, "")}`;
    }
    return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
  }

  function nowSeconds() {
    return Math.floor(Date.now() / 1000);
  }

  function textFromInputItems(input) {
    return (Array.isArray(input) ? input : [])
      .map((item) => {
        if (!item || typeof item !== "object") {
          return "";
        }
        if (item.type === "text") {
          return String(item.text || "");
        }
        return "";
      })
      .join("")
      .trim();
  }

  function inputItemsFromPrompt(prompt) {
    return [{ type: "text", text: String(prompt || ""), text_elements: [] }];
  }

  function loadThreadState() {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(THREAD_STORAGE_KEY) || "{}");
      const threads = Array.isArray(parsed.threads) ? parsed.threads : [];
      return {
        activeThreadId: typeof parsed.activeThreadId === "string" ? parsed.activeThreadId : null,
        threads: threads.filter((thread) => thread && typeof thread.id === "string"),
      };
    } catch {
      return { activeThreadId: null, threads: [] };
    }
  }

  function saveThreadState() {
    try {
      window.localStorage.setItem(THREAD_STORAGE_KEY, JSON.stringify(threadState));
    } catch {
      // Ignore storage failures; the bridge still works for the current page lifetime.
    }
  }

  function getThread(threadId) {
    return threadState.threads.find((thread) => thread.id === threadId) || null;
  }

  function upsertThread(thread) {
    const index = threadState.threads.findIndex((item) => item.id === thread.id);
    if (index >= 0) {
      threadState.threads[index] = thread;
    } else {
      threadState.threads.unshift(thread);
    }
    threadState.activeThreadId = thread.id;
    saveThreadState();
  }

  function threadPayload(thread, options) {
    const includeTurns = options?.includeTurns === true;
    return {
      id: thread.id,
      thread_id: thread.id,
      preview: thread.preview || "",
      ephemeral: false,
      modelProvider: thread.modelProvider || "agenthub_gui",
      model_provider: thread.modelProvider || "agenthub_gui",
      createdAt: thread.createdAt,
      created_at: thread.createdAt,
      updatedAt: thread.updatedAt,
      updated_at: thread.updatedAt,
      status: thread.status || "idle",
      path: thread.path || null,
      cwd: thread.cwd || WORKSPACE_ROOT,
      cliVersion: "agenthub-gui-shim",
      cli_version: "agenthub-gui-shim",
      source: "appServer",
      agentNickname: null,
      agentRole: null,
      gitInfo: null,
      name: thread.name || null,
      turns: includeTurns ? (thread.turns || []).map(turnPayload) : [],
    };
  }

  function turnPayload(turn) {
    return {
      id: turn.id,
      status: turn.status || "completed",
      items: turn.items || [],
      error: turn.error || null,
    };
  }

  function turnRuntimePayload(turnId, status) {
    return {
      id: turnId,
      status,
      items: [],
      error: null,
    };
  }

  function modelListResult() {
    const providerName = currentProviderName();
    const model = currentModelId();
    const provider = currentProviderEntry();
    return {
      data: [
        {
          id: model,
          model,
          name: model,
          displayName: modelDisplayName(model, providerName),
          description: `AgentHub ${providerName} current model`,
          hidden: false,
          provider: providerName,
          providerName,
          modelKey: model,
          wireApi: provider?.wireApi || "responses",
          plannerKind: provider?.plannerKind || "agenthub_gui",
          isDefault: true,
          isCurrent: true,
          supportedReasoningEfforts: ["minimal", "low", "medium", "high", "xhigh"],
          defaultReasoningEffort: currentReasoningEffort(),
          inputModalities: ["text"],
          supportsPersonality: false,
        },
      ],
      nextCursor: null,
    };
  }

  function createThread(params) {
    const timestamp = nowSeconds();
    const cwd = String(params.cwd || WORKSPACE_ROOT);
    const id = randomId("thread");
    const thread = {
      id,
      cwd,
      createdAt: timestamp,
      updatedAt: timestamp,
      model: String(params.model || currentModelId()),
      modelProvider: String(params.modelProvider || currentProviderName()),
      reasoningEffort: String(params.reasoningEffort || params.effort || currentReasoningEffort()),
      preview: "",
      name: null,
      path: null,
      status: "idle",
      turns: [],
    };
    upsertThread(thread);
    window.setTimeout(() => {
      emitMcpNotification("thread/started", { thread: threadPayload(thread) });
    }, 0);
    return {
      thread: threadPayload(thread),
      model: thread.model,
      modelProvider: thread.modelProvider,
      cwd,
      approvalPolicy: params.approvalPolicy || "on-request",
      sandbox: params.sandbox || "workspace-write",
      reasoningEffort: thread.reasoningEffort,
      serviceTier: params.serviceTier || null,
    };
  }

  function updateThreadTitle(thread, prompt) {
    const title = String(prompt || "").replace(/\s+/g, " ").trim().slice(0, 60);
    if (!title) {
      return;
    }
    thread.preview = title;
    if (!thread.name) {
      thread.name = title;
      emitMcpNotification("thread/name/updated", {
        threadId: thread.id,
        threadName: title,
      });
    }
  }

  function startTurn(params) {
    const threadId = String(params.threadId || params.thread_id || "");
    const thread = getThread(threadId);
    if (!thread) {
      throw new Error(`Unknown threadId: ${threadId}`);
    }
    const input = Array.isArray(params.input) ? params.input : [];
    const prompt = textFromInputItems(input);
    const turnId = randomId("turn");
    const turn = {
      id: turnId,
      status: "inProgress",
      error: null,
      input,
      items: [],
    };
    thread.turns.push(turn);
    thread.updatedAt = nowSeconds();
    thread.status = { type: "active", activeFlags: ["running"] };
    updateThreadTitle(thread, prompt);
    upsertThread(thread);
    window.setTimeout(() => {
      void completeLocalTurn({ params, prompt, threadId, turnId });
    }, 20);
    return { turn: turnRuntimePayload(turnId, "inProgress") };
  }

  async function completeLocalTurn({ params, prompt, threadId, turnId }) {
    const thread = getThread(threadId);
    if (!thread) {
      return;
    }
    emitMcpNotification("turn/started", {
      threadId,
      turn: turnRuntimePayload(turnId, "inProgress"),
    });

    const userItem = {
      id: randomId("user"),
      type: "userMessage",
      content: Array.isArray(params.input) && params.input.length ? params.input : inputItemsFromPrompt(prompt),
      attachments: params.attachments || [],
      commentAttachments: [],
    };
    emitMcpNotification("item/started", { threadId, turnId, item: userItem });
    emitMcpNotification("item/completed", { threadId, turnId, item: userItem });

    const assistantItemId = randomId("agent");
    emitMcpNotification("item/started", {
      threadId,
      turnId,
      item: { id: assistantItemId, type: "agentMessage", text: "", phase: null },
    });
    const progressPulse = startAssistantProgressPulse({ threadId, turnId, itemId: assistantItemId });
    const assistantText = await resolveAssistantText({ params, prompt, thread });
    progressPulse.stop();
    emitMcpNotification("item/agentMessage/delta", {
      threadId,
      turnId,
      itemId: assistantItemId,
      delta: assistantText,
    });
    emitMcpNotification("item/completed", {
      threadId,
      turnId,
      item: { id: assistantItemId, type: "agentMessage", text: assistantText, phase: null },
    });
    emitMcpNotification("turn/completed", {
      threadId,
      turn: turnRuntimePayload(turnId, "completed"),
    });

    const latestThread = getThread(threadId);
    if (!latestThread) {
      return;
    }
    const turn = (latestThread.turns || []).find((item) => item.id === turnId);
    if (turn) {
      turn.status = "completed";
      turn.items = [userItem, { id: assistantItemId, type: "agentMessage", text: assistantText, phase: null }];
    }
    latestThread.status = "idle";
    latestThread.updatedAt = nowSeconds();
    upsertThread(latestThread);
  }

  function startAssistantProgressPulse({ threadId, turnId, itemId }) {
    let stopped = false;
    let timer = null;
    let progressIndex = 0;
    const progressMessages = [
      "正在连接 AgentHub provider...\n",
      "仍在等待 provider 响应...\n",
    ];

    const emitProgress = () => {
      if (stopped) {
        return;
      }
      const delta = progressMessages[Math.min(progressIndex, progressMessages.length - 1)];
      progressIndex += 1;
      emitMcpNotification("item/agentMessage/delta", {
        threadId,
        turnId,
        itemId,
        delta,
      });
      timer = window.setTimeout(emitProgress, 8000);
    };

    timer = window.setTimeout(emitProgress, 1200);
    return {
      stop() {
        stopped = true;
        if (timer !== null) {
          window.clearTimeout(timer);
          timer = null;
        }
      },
    };
  }

  async function resolveAssistantText({ params, prompt, thread }) {
    const bridgeResult = await callAgentHubChatSend({ params, prompt, thread });
    if (bridgeResult && typeof bridgeResult.assistant_text === "string" && bridgeResult.assistant_text.trim()) {
      return bridgeResult.assistant_text;
    }
    if (bridgeResult && bridgeResult.accepted === true) {
      return "AgentHub 已接受这次请求，后续结果会在 AgentHub 会话中更新。";
    }
    return `AgentHub Codex bridge 已收到请求：${prompt || "(empty prompt)"}`;
  }

  async function callAgentHubChatSend({ params, prompt, thread }) {
    const config = bridgeTransportConfig();
    if (!config || config.mode !== "http" || !config.httpBaseUrl) {
      return null;
    }
    try {
      const requestPath = config.requestPath || "/requests";
      const request = {
        protocol_version: "v1",
        request_id: randomId("req"),
        action: "chat.send",
        payload: {
          text: prompt,
          cwd: params.cwd || thread.cwd || WORKSPACE_ROOT,
          workspaceRoots: [params.cwd || thread.cwd || WORKSPACE_ROOT],
          thread_id: thread.agentHubThreadId || undefined,
          new_thread: !thread.agentHubThreadId,
        },
        client: { name: "agenthub-codex-native-webview", version: "0.1.0" },
      };
      const response = await fetchFromHostPage(`${String(config.httpBaseUrl).replace(/\/$/, "")}${requestPath}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(request),
      });
      const payload = await response.json();
      if (!response.ok || payload.ok !== true) {
        return null;
      }
      if (payload.data && typeof payload.data.thread_id === "string") {
        thread.agentHubThreadId = payload.data.thread_id;
        saveThreadState();
      }
      return payload.data || null;
    } catch (error) {
      record("agenthub-chat-send-error", { error: error instanceof Error ? error.message : String(error) });
      return null;
    }
  }

  function bridgeTransportConfig() {
    try {
      return window.parent && window.parent !== window
        ? window.parent.__AGENTHUB_GUI_BRIDGE__
        : window.__AGENTHUB_GUI_BRIDGE__;
    } catch {
      return window.__AGENTHUB_GUI_BRIDGE__;
    }
  }

  function fetchFromHostPage(url, init) {
    try {
      if (window.parent && window.parent !== window && typeof window.parent.fetch === "function") {
        return window.parent.fetch(url, init);
      }
    } catch {
      // Cross-origin parents are not expected in AgentHub, but fall through safely.
    }
    return window.fetch(url, init);
  }

  function emitMcpNotification(method, params) {
    sendToView({
      type: "mcp-notification",
      hostId: "local",
      method,
      params,
    });
  }

  async function fetchWorkspaceDirectoryEntries(params) {
    const response = await window.fetch("/__agenthub_codex/workspace-directory-entries", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        workspaceRoot: params.workspaceRoot || WORKSPACE_ROOT,
        directoryPath: params.directoryPath || null,
        includeHidden: params.includeHidden === true,
      }),
    });
    if (!response.ok) {
      throw new Error(`workspace-directory-entries failed: ${response.status}`);
    }
    return response.json();
  }

  async function resolveCodexApi(method, params) {
    switch (method) {
      case "get-global-state":
        return { value: null };
      case "set-global-state":
        return { ok: true };
      case "os-info":
        return {
          platform: "linux",
          arch: "x64",
          hasWsl: false,
          homedir: HOME_DIR,
        };
      case "mcp-codex-config":
        return { config: {} };
      case "developer-instructions":
        return { instructions: "" };
      case "open-in-targets":
        return {
          preferredTarget: null,
          targets: [],
          availableTargets: [],
          mode: "none",
        };
      case "thread-search":
        return { items: [], nextCursor: null };
      case "codex-agents-md":
        return { contents: "", sources: [] };
      case "feature-flags":
      case "experimentalFeature/list":
        return { data: [], nextCursor: null };
      case "config":
      case "mcp-config":
      case "configuration":
        return { ...defaultConfigResult(), codexHome: CODEX_HOME };
      case "set-default-model-config-for-host":
      case "set-model-and-reasoning-for-next-turn": {
        const model = String(params?.model || "").trim();
        const reasoningEffort = String(params?.reasoningEffort || params?.reasoning_effort || "").trim();
        if (model || reasoningEffort) {
          const settings = await callAgentHubBridgeAction("settings.update", {
            ...(model ? { model } : {}),
            ...(reasoningEffort ? { reasoningEffort } : {}),
            writeScope: "session",
          });
          applyProviderSelectorSettings(settings || {});
          renderProviderSelectorButton();
          syncNativeModelSelectorLabel();
        }
        return {};
      }
      case "workspace-roots":
      case "active-workspace-roots":
        return { roots: [WORKSPACE_ROOT], activeRoot: WORKSPACE_ROOT };
      case "workspace-root-options":
        return { roots: [WORKSPACE_ROOT], labels: { [WORKSPACE_ROOT]: WORKSPACE_LABEL } };
      case "paths-exist":
        return {
          existingPaths: (Array.isArray(params?.paths) ? params.paths : [])
            .map((item) => String(item || ""))
            .filter((item) => item === WORKSPACE_ROOT || item.startsWith(`${WORKSPACE_ROOT}/`)),
        };
      case "git-origins":
        return { origins: [] };
      case "codex-home":
        return { codexHome: CODEX_HOME, worktreesSegment: ".codex/worktrees" };
      case "list-automations":
        return { items: [] };
      case "list-pending-automation-run-threads":
        return { threadIds: [] };
      case "workspace-directory-entries":
        return fetchWorkspaceDirectoryEntries(params || {});
      case "ambient-suggestions":
        return { file: { generatedAtMs: null, currentSuggestionIds: [], suggestions: [] } };
      default:
        return fallbackCodexApiResponse(method, params);
    }
  }

  function fallbackCodexApiResponse(method, params) {
    if (method.includes("model")) {
      return modelListResult();
    }
    if (method.includes("git")) {
      return {};
    }
    return {};
  }

  async function handleFetch(message) {
    try {
      const method = codexMethodFromUrl(message.url);
      successFetchResponse(message.requestId, await resolveCodexApi(method, parseBody(message.body)));
    } catch (error) {
      errorFetchResponse(message.requestId, error);
    }
  }

  function handleFetchStream(message) {
    const requestId = message.requestId;
    window.setTimeout(() => {
      sendToView({ type: "fetch-stream-complete", requestId });
    }, 0);
  }

  function resolveMcpRequest(request) {
    const method = String(request && request.method ? request.method : "");
    const params = request && request.params ? request.params : {};
    switch (method) {
      case "thread/list":
        return {
          data: [...threadState.threads]
            .sort((left, right) => Number(right.updatedAt || 0) - Number(left.updatedAt || 0))
            .map((thread) => threadPayload(thread)),
          nextCursor: null,
        };
      case "thread/start":
        return createThread(params);
      case "turn/start":
        return startTurn(params);
      case "thread/read":
        return {
          thread: threadPayload(getThread(String(params.threadId || params.thread_id || "")) || createThread(params).thread, {
            includeTurns: params.includeTurns === true || params.include_turns === true,
          }),
        };
      case "account/read":
        return {
          account: { type: "apikey" },
          requiresOpenaiAuth: false,
        };
      case "account/logout":
        return {};
      case "experimentalFeature/list":
        return { data: [], nextCursor: null };
      case "model/list":
        return modelListResult();
      case "collaborationMode/list":
        return { data: [], nextCursor: null };
      case "config/read":
      case "read-config":
      case "read-config-for-host":
        return defaultConfigResult();
      default:
        return fallbackCodexApiResponse(method, params);
    }
  }

  function handleMcpRequest(message) {
    const request = message.request || {};
    sendToView({
      type: "mcp-response",
      hostId: message.hostId || "local",
      message: {
        id: request.id,
        result: resolveMcpRequest(request),
      },
    });
  }

  async function sendMessageFromView(message) {
    record("from-view", message);
    switch (message && message.type) {
      case "shared-object-set":
        if (message.value === undefined) {
          delete sharedObjects[message.key];
        } else {
          sharedObjects[message.key] = message.value;
        }
        sendToView({ type: "shared-object-updated", key: message.key, value: message.value });
        break;
      case "shared-object-subscribe":
        sendToView({ type: "shared-object-updated", key: message.key, value: sharedObjects[message.key] });
        break;
      case "persisted-atom-sync-request":
        sendToView({ type: "persisted-atom-sync", state: {} });
        break;
      case "persisted-atom-update":
        sendToView({
          type: "persisted-atom-updated",
          key: message.key,
          value: message.value,
          deleted: message.deleted === true,
        });
        break;
      case "fetch":
        handleFetch(message);
        break;
      case "fetch-stream":
        handleFetchStream(message);
        break;
      case "cancel-fetch":
      case "cancel-fetch-stream":
        break;
      case "mcp-request":
      case "thread-prewarm-start":
        handleMcpRequest(message);
        break;
      default:
        break;
    }
  }

  const electronBridge = {
    windowType: "electron",
    sendMessageFromView,
    getPathForFile(file) {
      return file && typeof file.path === "string" ? file.path : null;
    },
    async sendWorkerMessageFromView(workerId, message) {
      record("worker-from-view", { workerId, message });
    },
    subscribeToWorkerMessages(workerId, listener) {
      const listeners = workerSubscribers.get(workerId) || new Set();
      listeners.add(listener);
      workerSubscribers.set(workerId, listeners);
      return () => {
        listeners.delete(listener);
        if (listeners.size === 0) {
          workerSubscribers.delete(workerId);
        }
      };
    },
    async showContextMenu(menu) {
      record("context-menu", menu);
      return null;
    },
    async showApplicationMenu(menuId, x, y) {
      record("application-menu", { menuId, x, y });
      return null;
    },
    async getFastModeRolloutMetrics() {
      return null;
    },
    getSharedObjectSnapshotValue(key) {
      return sharedObjects[key];
    },
    getSystemThemeVariant() {
      return systemThemeVariant;
    },
    subscribeToSystemThemeVariant(listener) {
      const callback = () => listener(systemThemeVariant);
      window.addEventListener("agenthub-codex-theme", callback);
      return () => window.removeEventListener("agenthub-codex-theme", callback);
    },
    async triggerSentryTestError() {},
    getSentryInitOptions() {
      return {
        appVersion: "1.0.0",
        buildFlavor: "dev",
        buildNumber: "agenthub-dev",
        codexAppSessionId: SESSION_ID,
        dsn: null,
        environment: "agenthub-dev-shim",
      };
    },
    getAppSessionId() {
      return SESSION_ID;
    },
    getBuildFlavor() {
      return "agenthub-dev-shim";
    },
  };

  Object.defineProperty(window, "codexWindowType", {
    configurable: true,
    value: "electron",
  });
  Object.defineProperty(window, "electronBridge", {
    configurable: true,
    value: electronBridge,
  });
  window.__AGENTHUB_CODEX_BRIDGE_MESSAGES__ = messages;
  window.__AGENTHUB_CODEX_BRIDGE_SET_SHARED_OBJECT__ = (key, value) => {
    sharedObjects[key] = value;
    sendToView({ type: "shared-object-updated", key, value });
  };
})();
