from __future__ import annotations

import json
import shutil
import time
from urllib.error import HTTPError, URLError

from shared.web_automation.navigation_guard import assert_browser_endpoint_allowed

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
except ImportError:  # pragma: no cover
    PlaywrightError = Exception
    PlaywrightTimeoutError = TimeoutError


def _live_driver_module():
    from shared.web_automation import live_driver as live_driver_module

    return live_driver_module


def start_profile(self, profile_state) -> bool:
    profile_name = profile_state.spec.name
    context = self._contexts.get(profile_name)
    if context is not None:
        return True
    live_driver_module = _live_driver_module()
    if live_driver_module.sync_playwright is None:
        raise RuntimeError("Playwright is not installed")
    if self._playwright is None:
        self._playwright = live_driver_module.sync_playwright().start()
    cdp_url = self._resolve_cdp_url(profile_state)
    if cdp_url:
        browser = self._playwright.chromium.connect_over_cdp(
            cdp_url,
            timeout=int(self._config.launch_timeout_ms),
        )
        context = browser.contexts[0] if browser.contexts else browser.new_context(ignore_https_errors=True)
        self._browsers[profile_name] = browser
        self._contexts[profile_name] = context
        return True
    if profile_state.spec.attach_only:
        raise RuntimeError("attach_only profile requires cdp_url and will not launch a local browser")
    executable_path = self._resolve_executable_path(profile_state)
    if not executable_path:
        raise RuntimeError("No Chromium-compatible browser executable found")
    headless = self._resolve_headless(profile_state)
    user_data_dir = str(profile_state.spec.user_data_dir or "").strip()
    if user_data_dir:
        context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            executable_path=executable_path,
            headless=headless,
            timeout=int(self._config.launch_timeout_ms),
            ignore_https_errors=True,
            args=["--disable-dev-shm-usage"],
        )
        self._contexts[profile_name] = context
        self._persistent_profiles.add(profile_name)
        return True
    browser = self._playwright.chromium.launch(
        executable_path=executable_path,
        headless=headless,
        timeout=int(self._config.launch_timeout_ms),
        args=["--disable-dev-shm-usage"],
    )
    context = browser.new_context(ignore_https_errors=True)
    self._browsers[profile_name] = browser
    self._contexts[profile_name] = context
    return True


def _resolve_cdp_url(self, profile_state) -> str:
    cdp_url = str(profile_state.spec.cdp_url or "").strip()
    if cdp_url:
        assert_browser_endpoint_allowed(cdp_url, policy=self._navigation_policy)
        return cdp_url
    driver = str(profile_state.spec.driver or "").strip().lower()
    if driver != "existing-session":
        return ""
    return self._discover_existing_session_cdp_url()


def _discover_existing_session_cdp_url(self) -> str:
    live_driver_module = _live_driver_module()
    timeout_s = max(0.25, min(float(self._config.launch_timeout_ms) / 1000.0, 1.5))
    discovery_path = str(self._config.existing_session_discovery_path or "/json/version").strip() or "/json/version"
    discovery_bases = self._existing_session_discovery_bases()
    attempted_urls: list[str] = []
    for raw_base_url in discovery_bases:
        base_url = str(raw_base_url or "").strip().rstrip("/")
        if not base_url:
            continue
        assert_browser_endpoint_allowed(base_url, policy=self._navigation_policy)
        version_url = f"{base_url}{discovery_path}"
        attempted_urls.append(version_url)
        try:
            request = live_driver_module.Request(version_url, headers={"Accept": "application/json"})
            with live_driver_module.urlopen(request, timeout=timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        ws_url = str(payload.get("webSocketDebuggerUrl") or "").strip()
        browser_name = str(payload.get("Browser") or "").strip()
        if ws_url or browser_name:
            return base_url.rstrip("/")
    attempted_text = ", ".join(attempted_urls) if attempted_urls else "<none>"
    raise RuntimeError(
        "existing-session profile could not find a Chrome DevTools endpoint. "
        f"Attempted discovery URLs: {attempted_text}. "
        "Start Chrome/Edge/Brave/Chromium with --remote-debugging-port=9222, "
        "or configure existing_session.discovery_bases / discovery_path."
    )


def _existing_session_discovery_bases(self) -> tuple[str, ...]:
    configured = [
        str(item or "").strip()
        for item in self._config.existing_session_discovery_bases
        if str(item or "").strip()
    ]
    if configured:
        return tuple(configured)
    return self._existing_session_discovery_bases_default


def stop_profile(self, profile_state) -> bool:
    profile_name = profile_state.spec.name
    context = self._contexts.pop(profile_name, None)
    for tab in list(profile_state.tabs):
        self._pages.pop(tab.tab_id, None)
        self._ref_cache_by_tab.pop(tab.tab_id, None)
    browser = self._browsers.pop(profile_name, None)
    is_persistent = profile_name in self._persistent_profiles
    self._persistent_profiles.discard(profile_name)
    if browser is not None:
        browser.close()
    elif context is not None and is_persistent:
        context.close()
    elif context is not None:
        context.close()
    if not self._contexts:
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
    return True


def _resolve_executable_path(self, profile_state=None) -> str:
    candidate = str((profile_state.spec.executable_path if profile_state else "") or "").strip()
    if candidate:
        return candidate
    candidate = str(self._config.executable_path or "").strip()
    if candidate:
        return candidate
    for name in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return ""


def _resolve_headless(self, profile_state=None) -> bool:
    if profile_state is not None and profile_state.spec.headless is not None:
        return bool(profile_state.spec.headless)
    return bool(self._config.headless)


def _navigation_timeout_ms(self) -> int:
    return max(1000, min(120000, int(self._config.navigation_timeout_ms)))


def _interaction_timeout_ms(self) -> int:
    return max(500, min(60000, int(self._config.navigation_timeout_ms)))


def _is_timeout_error(self, error) -> bool:
    if isinstance(error, PlaywrightTimeoutError):
        return True
    return "timeout" in str(error).lower()


def _is_retryable_navigation_error(self, error) -> bool:
    message = str(error).lower()
    return (
        "frame has been detached" in message
        or "target page, context or browser has been closed" in message
    )


def _to_ai_friendly_error(self, error, selector: str) -> Exception:
    del self
    message = str(error)
    lowered = message.lower()
    if "strict mode violation" in lowered:
        return ValueError(
            f'Selector "{selector}" matched multiple elements. Run "/browser snapshot" to refresh refs.'
        )
    if (
        "timeout" in lowered or "waiting for" in lowered
    ) and ("to be visible" in lowered or "not visible" in lowered):
        return ValueError(
            f'Element "{selector}" not found or not visible. Run "/browser snapshot" to inspect the page again.'
        )
    if (
        "intercepts pointer events" in lowered
        or "not visible" in lowered
        or "not receive pointer events" in lowered
    ):
        return ValueError(
            f'Element "{selector}" is not interactable. Close overlays or run "/browser snapshot" again.'
        )
    if isinstance(error, PlaywrightError):
        return RuntimeError(message)
    if isinstance(error, Exception):
        return error
    return RuntimeError(message)


def bind_live_driver_profile_ops(cls) -> None:
    for fn in (
        start_profile,
        _resolve_cdp_url,
        _discover_existing_session_cdp_url,
        _existing_session_discovery_bases,
        stop_profile,
        _resolve_executable_path,
        _resolve_headless,
        _navigation_timeout_ms,
        _interaction_timeout_ms,
        _is_timeout_error,
        _is_retryable_navigation_error,
        _to_ai_friendly_error,
    ):
        setattr(cls, fn.__name__, fn)
