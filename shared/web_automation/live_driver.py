from __future__ import annotations

from typing import Any
from urllib.request import Request, urlopen

from shared.web_automation.config import BrowserAutomationConfig
from shared.web_automation.navigation_guard import navigation_policy_from_config

try:
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright
except ImportError:  # pragma: no cover - exercised by availability checks
    Browser = BrowserContext = Page = Playwright = None
    sync_playwright = None

_INTERACTIVE_SELECTOR = ",".join(
    [
        "a[href]",
        "button",
        "input",
        "textarea",
        "select",
        "[role='button']",
        "[role='link']",
        "[role='textbox']",
        "[role='checkbox']",
        "[role='radio']",
        "[role='combobox']",
        "[contenteditable='true']",
        "[contenteditable='']",
    ]
)

_DEFAULT_EXISTING_SESSION_DISCOVERY_BASES = (
    "http://127.0.0.1:9222",
    "http://localhost:9222",
)

_SNAPSHOT_SCRIPT = """
(input) => {
  const knownRefs = input && typeof input === 'object' && input.knownRefs ? input.knownRefs : {};
  const visible = (el) => {
    if (!(el instanceof HTMLElement)) return false;
    const style = window.getComputedStyle(el);
    if (!style || style.visibility === 'hidden' || style.display === 'none') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
  document.querySelectorAll('[data-agenthub-ref]').forEach((node) => node.removeAttribute('data-agenthub-ref'));
  const elements = [];
  const seen = new Set();
  const signatureCounts = new Map();
  const assignedRefs = new Set();
  let nextRefIndex = 1;
  for (const el of document.querySelectorAll(%s)) {
    if (!(el instanceof HTMLElement)) continue;
    if (seen.has(el) || !visible(el)) continue;
    seen.add(el);
    const role =
      (el.getAttribute('role') || '').trim() ||
      (el.tagName || '').toLowerCase() ||
      'element';
    const textBits = [
      el.getAttribute('aria-label') || '',
      el.getAttribute('placeholder') || '',
      el.innerText || '',
      el.textContent || '',
      'value' in el && typeof el.value === 'string' ? el.value : '',
      el.getAttribute('title') || '',
      el.getAttribute('name') || '',
    ];
    const name = normalize(textBits.join(' ')).slice(0, 180);
    const href = el instanceof HTMLAnchorElement ? el.href : '';
    const tag = (el.tagName || '').toLowerCase();
    const key = [tag, role, name, href || ''].join('|');
    const seenCount = (signatureCounts.get(key) || 0) + 1;
    signatureCounts.set(key, seenCount);
    const signature = `${key}|${seenCount}`;
    let ref = normalize(knownRefs[signature]);
    if (ref && assignedRefs.has(ref)) {
      ref = '';
    }
    if (!ref) {
      while (assignedRefs.has(`e${nextRefIndex}`)) {
        nextRefIndex += 1;
      }
      ref = `e${nextRefIndex}`;
      nextRefIndex += 1;
    }
    assignedRefs.add(ref);
    el.setAttribute('data-agenthub-ref', ref);
    elements.push({
      ref,
      role,
      name,
      url: href || undefined,
      signature,
      selector: `[data-agenthub-ref="${ref}"]`,
      tag,
    });
  }
  return {
    title: document.title || '',
    url: location.href,
    elements,
  };
}
""" % repr(_INTERACTIVE_SELECTOR)


class LiveBrowserDriver:
    def __init__(self, config: BrowserAutomationConfig) -> None:
        self._config = config
        self._navigation_policy = navigation_policy_from_config(config)
        self._playwright: Playwright | None = None
        self._browsers: dict[str, Browser] = {}
        self._contexts: dict[str, BrowserContext] = {}
        self._persistent_profiles: set[str] = set()
        self._pages: dict[str, Page] = {}
        self._ref_cache_by_tab: dict[str, dict[str, str]] = {}
        self._snapshot_script = _SNAPSHOT_SCRIPT
        self._existing_session_discovery_bases_default = _DEFAULT_EXISTING_SESSION_DISCOVERY_BASES


from shared.web_automation.live_driver_interaction_ops import bind_live_driver_interaction_ops
from shared.web_automation.live_driver_page_ops import bind_live_driver_page_ops
from shared.web_automation.live_driver_profile_ops import bind_live_driver_profile_ops
from shared.web_automation.live_driver_tab_ops import bind_live_driver_tab_ops

bind_live_driver_profile_ops(LiveBrowserDriver)
bind_live_driver_page_ops(LiveBrowserDriver)
bind_live_driver_tab_ops(LiveBrowserDriver)
bind_live_driver_interaction_ops(LiveBrowserDriver)
