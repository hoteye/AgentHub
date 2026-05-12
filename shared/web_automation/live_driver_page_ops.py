from __future__ import annotations

import time
from typing import Any

from shared.web_automation.navigation_guard import (
    assert_browser_navigation_allowed,
    assert_browser_navigation_result_allowed,
)
from shared.web_automation.observe import append_console_entry
from shared.web_automation.types import BrowserPageRef


def _require_page(self, tab):
    page = self._pages.get(tab.tab_id)
    if page is None:
        raise RuntimeError(f"tab not found: {tab.tab_id}")
    return page


def _locator_for_ref(self, tab, ref: str):
    normalized = str(ref or "").strip()
    if not normalized:
        raise ValueError("ref is required")
    for item in tab.refs:
        if item.ref == normalized and item.selector:
            return self._require_page(tab).locator(item.selector).first
    self._refresh_refs_for_tab(tab)
    for item in tab.refs:
        if item.ref == normalized and item.selector:
            return self._require_page(tab).locator(item.selector).first
    raise ValueError(f'unknown ref: {normalized}. Run "/browser snapshot" to refresh page refs.')


def _goto(self, page, url: str) -> None:
    normalized_url = str(url or "").strip()
    if not normalized_url:
        raise ValueError("url is required")
    assert_browser_navigation_allowed(normalized_url, policy=self._navigation_policy)
    last_error: Exception | None = None
    timeout_ms = self._navigation_timeout_ms()
    for wait_until in ("domcontentloaded", "load", "commit"):
        try:
            page.goto(
                normalized_url,
                wait_until=wait_until,
                timeout=timeout_ms,
            )
            assert_browser_navigation_result_allowed(str(page.url or ""), policy=self._navigation_policy)
            self._settle_page(page)
            return
        except Exception as exc:
            last_error = exc if isinstance(exc, Exception) else RuntimeError(str(exc))
            if wait_until == "commit" and self._page_has_document(page):
                assert_browser_navigation_result_allowed(str(page.url or ""), policy=self._navigation_policy)
                self._settle_page(page, timeout_ms=1500)
                return
            if self._is_retryable_navigation_error(exc):
                time.sleep(0.15)
                continue
            if not self._is_timeout_error(exc):
                continue
    if self._page_has_document(page):
        assert_browser_navigation_result_allowed(str(page.url or ""), policy=self._navigation_policy)
        self._settle_page(page, timeout_ms=1500)
        return
    raise self._to_ai_friendly_error(last_error or RuntimeError("navigation failed"), normalized_url)


def _sync_tab(self, tab, page) -> None:
    tab.url = str(page.url or tab.url)
    try:
        title = page.title()
    except Exception:
        title = tab.title
    tab.title = str(title or tab.title)


def _attach_page(self, tab, page) -> None:
    page.on("console", lambda message, bound_tab=tab: self._handle_console(bound_tab, message))
    page.on("pageerror", lambda error, bound_tab=tab: self._handle_page_error(bound_tab, error))
    page.on("response", lambda response, bound_tab=tab: self._handle_response(bound_tab, response))
    page.on("requestfailed", lambda request, bound_tab=tab: self._handle_request_failed(bound_tab, request))
    page.on("dialog", lambda dialog, bound_tab=tab: self._handle_dialog(bound_tab, dialog))
    page.on("filechooser", lambda chooser, bound_tab=tab: self._handle_filechooser(bound_tab, chooser))


def _handle_console(self, tab, message: Any) -> None:
    try:
        text = message.text()
    except Exception:
        text = str(message)
    message_type = "info"
    try:
        message_type = str(message.type() or "info").lower()
    except Exception:
        pass
    append_console_entry(
        tab,
        message_type=message_type,
        text=str(text or "").strip(),
        location={"url": tab.url},
    )


def _handle_page_error(self, tab, error: Any) -> None:
    append_console_entry(
        tab,
        message_type="error",
        text=str(error or "").strip() or "Unhandled page error",
        location={"url": tab.url, "severity": "error"},
    )


def _handle_response(self, tab, response: Any) -> None:
    try:
        request = response.request
    except Exception:
        request = None
    method = ""
    resource_type = ""
    try:
        method = str(request.method or "").strip().upper() if request is not None else ""
    except Exception:
        method = ""
    try:
        resource_type = str(request.resource_type or "").strip() if request is not None else ""
    except Exception:
        resource_type = ""
    try:
        status = int(response.status)
    except Exception:
        status = None
    try:
        url = str(response.url or "").strip()
    except Exception:
        url = tab.url
    outcome = "failed" if status is not None and status >= 400 else "ok"
    message = f"{method or 'REQUEST'} {url or tab.url}"
    append_console_entry(
        tab,
        message_type="request",
        text=message,
        location={
            "url": url or tab.url,
            "method": method,
            "status": status if status is not None else "",
            "resource_type": resource_type,
            "outcome": outcome,
        },
    )


def _handle_request_failed(self, tab, request: Any) -> None:
    try:
        url = str(request.url or "").strip()
    except Exception:
        url = tab.url
    try:
        method = str(request.method or "").strip().upper()
    except Exception:
        method = ""
    try:
        resource_type = str(request.resource_type or "").strip()
    except Exception:
        resource_type = ""
    failure_text = ""
    try:
        failure = request.failure
        failure_text = str((failure or {}).get("errorText") or "").strip() if isinstance(failure, dict) else ""
    except Exception:
        failure_text = ""
    message = f"{method or 'REQUEST'} {url or tab.url}"
    if failure_text:
        message = f"{message} ({failure_text})"
    append_console_entry(
        tab,
        message_type="request",
        text=message,
        location={
            "url": url or tab.url,
            "method": method,
            "resource_type": resource_type,
            "outcome": "failed",
            "severity": "error",
        },
    )


def _handle_dialog(self, tab, dialog) -> None:
    hook = tab.armed_dialog
    try:
        if hook is None:
            dialog.dismiss()
            append_console_entry(
                tab,
                message_type="warning",
                text=f"Dismissed unexpected dialog: {dialog.message}",
                location={"url": tab.url},
            )
            return
        if hook.accept:
            dialog.accept(prompt_text=hook.prompt_text)
            tab.last_dialog = "accepted with prompt text" if hook.prompt_text else "accepted"
            append_console_entry(
                tab,
                message_type="info",
                text="Handled armed dialog: accepted",
                location={"url": tab.url},
            )
        else:
            dialog.dismiss()
            tab.last_dialog = "dismissed with prompt text" if hook.prompt_text else "dismissed"
            append_console_entry(
                tab,
                message_type="info",
                text="Handled armed dialog: dismissed",
                location={"url": tab.url},
            )
        tab.armed_dialog = None
    except Exception as exc:
        append_console_entry(
            tab,
            message_type="error",
            text=f"Dialog handling failed: {exc}",
            location={"url": tab.url},
        )


def _handle_filechooser(self, tab, chooser) -> None:
    hook = tab.armed_upload
    if hook is None:
        append_console_entry(
            tab,
            message_type="warning",
            text="Observed unexpected file chooser",
            location={"url": tab.url},
        )
        return
    try:
        chooser.set_files(hook.paths)
        target_ref = hook.input_ref or hook.ref or "filechooser"
        tab.uploaded_files[target_ref] = list(hook.paths)
        tab.armed_upload = None
        append_console_entry(
            tab,
            message_type="info",
            text=f"Applied armed upload to ref {target_ref} ({len(hook.paths)} file(s))",
            location={"url": tab.url},
        )
    except Exception as exc:
        append_console_entry(
            tab,
            message_type="error",
            text=f"File chooser handling failed: {exc}",
            location={"url": tab.url},
        )


def _capture_outline(self, page) -> str:
    del self
    try:
        outline = page.locator(":root").aria_snapshot()
    except Exception:
        return ""
    return str(outline or "").strip()


def _page_has_document(self, page) -> bool:
    del self
    try:
        if page.locator("body").count() > 0:
            return True
    except Exception:
        pass
    try:
        current_url = str(page.url or "").strip()
    except Exception:
        current_url = ""
    try:
        current_title = str(page.title() or "").strip()
    except Exception:
        current_title = ""
    return bool(current_url and current_url != "about:blank") or bool(current_title)


def _capture_ref_payload(self, page, tab) -> dict[str, object]:
    known_refs = dict(self._ref_cache_by_tab.get(tab.tab_id, {}))
    payload = page.evaluate(self._snapshot_script, {"knownRefs": known_refs})
    return payload if isinstance(payload, dict) else {}


def _apply_ref_payload(self, tab, payload: dict[str, object]) -> list[BrowserPageRef]:
    raw_elements = payload.get("elements")
    source = raw_elements if isinstance(raw_elements, list) else []
    refs: list[BrowserPageRef] = []
    ref_cache: dict[str, str] = {}
    for item in source:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("ref") or "").strip()
        role = str(item.get("role") or item.get("tag") or "element").strip()
        name = str(item.get("name") or "").strip() or None
        element_url = str(item.get("url") or "").strip() or None
        selector = str(item.get("selector") or "").strip() or None
        signature = str(item.get("signature") or "").strip()
        if not ref or not selector:
            continue
        refs.append(
            BrowserPageRef(
                ref=ref,
                role=role,
                name=name,
                url=element_url,
                selector=selector,
            )
        )
        if signature:
            ref_cache[signature] = ref
    tab.refs = refs
    self._ref_cache_by_tab[tab.tab_id] = ref_cache
    return refs


def _refresh_refs_for_tab(self, tab) -> None:
    page = self._require_page(tab)
    self._settle_page(page, timeout_ms=1000)
    payload = self._capture_ref_payload(page, tab)
    self._apply_ref_payload(tab, payload)


def _run_ref_action(self, tab, ref: str, action) -> None:
    try:
        action(self._locator_for_ref(tab, ref))
        return
    except Exception as exc:
        if not self._should_retry_ref_action(exc):
            raise self._to_ai_friendly_error(exc, ref)
    self._refresh_refs_for_tab(tab)
    try:
        action(self._locator_for_ref(tab, ref))
    except Exception as exc:
        raise self._to_ai_friendly_error(exc, ref)


def _should_retry_ref_action(self, error) -> bool:
    lowered = str(error).lower()
    return (
        "timeout" in lowered
        or "not visible" in lowered
        or "waiting for" in lowered
        or "element is not attached" in lowered
        or "element handle" in lowered
        or "could not resolve" in lowered
    )


def _settle_page(self, page, timeout_ms: int | None = None) -> None:
    budget = max(500, min(8000, int(timeout_ms or self._config.navigation_timeout_ms)))
    try:
        page.wait_for_function("document.readyState !== 'loading'", timeout=min(2500, budget))
    except Exception:
        pass
    try:
        page.locator("body").first.wait_for(state="attached", timeout=min(2500, budget))
    except Exception:
        pass
    for state in ("domcontentloaded", "load"):
        try:
            page.wait_for_load_state(state, timeout=min(2500, budget))
        except Exception:
            continue
    try:
        page.wait_for_timeout(150)
    except Exception:
        pass


def bind_live_driver_page_ops(cls) -> None:
    for fn in (
        _require_page,
        _locator_for_ref,
        _goto,
        _sync_tab,
        _attach_page,
        _handle_console,
        _handle_page_error,
        _handle_response,
        _handle_request_failed,
        _handle_dialog,
        _handle_filechooser,
        _capture_outline,
        _page_has_document,
        _capture_ref_payload,
        _apply_ref_payload,
        _refresh_refs_for_tab,
        _run_ref_action,
        _should_retry_ref_action,
        _settle_page,
    ):
        setattr(cls, fn.__name__, fn)
