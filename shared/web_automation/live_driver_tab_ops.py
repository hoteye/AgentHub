from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path

from shared.web_automation.artifacts import (
    create_artifact_path,
    record_artifact,
    resolve_artifact_output_path,
    sanitize_artifact_filename,
)
from shared.web_automation.observe import append_console_entry
from shared.web_automation.types import BrowserSnapshot, BrowserTab


def open_tab(self, profile_state, url: str) -> BrowserTab:
    context = self._contexts.get(profile_state.spec.name)
    if context is None:
        raise RuntimeError(f"profile is not running: {profile_state.spec.name}")
    page = context.new_page()
    tab = BrowserTab(
        tab_id=uuid.uuid4().hex,
        url=str(url or "").strip(),
        title=str(url or "").strip(),
        profile=profile_state.spec.name,
    )
    self._pages[tab.tab_id] = page
    self._attach_page(tab, page)
    self._goto(page, url)
    self._sync_tab(tab, page)
    append_console_entry(
        tab,
        message_type="info",
        text=f"Opened live tab for {tab.url}",
        location={"url": tab.url},
    )
    return tab


def focus_tab(self, tab: BrowserTab) -> bool:
    page = self._pages.get(tab.tab_id)
    if page is None:
        return False
    page.bring_to_front()
    self._sync_tab(tab, page)
    return True


def close_tab(self, tab: BrowserTab) -> bool:
    page = self._pages.pop(tab.tab_id, None)
    if page is None:
        return False
    page.close()
    self._ref_cache_by_tab.pop(tab.tab_id, None)
    return True


def navigate(self, tab: BrowserTab, url: str) -> BrowserTab:
    page = self._require_page(tab)
    self._goto(page, url)
    self._sync_tab(tab, page)
    append_console_entry(
        tab,
        message_type="info",
        text=f"Navigated live tab to {tab.url}",
        location={"url": tab.url},
    )
    return tab


def snapshot_tab(self, tab: BrowserTab, *, max_chars: int, max_refs: int) -> BrowserSnapshot:
    page = self._require_page(tab)
    self._settle_page(page)
    payload = self._capture_ref_payload(page, tab)
    outline = self._capture_outline(page)
    title = str((payload or {}).get("title") or page.title() or tab.title).strip() or tab.title
    url = str((payload or {}).get("url") or page.url or tab.url).strip() or tab.url
    refs = self._apply_ref_payload(tab, payload)
    lines = [
        f"Page: {title}",
        f"URL: {url}",
    ]
    if outline:
        lines.extend(["", "Page content:", outline.rstrip()])
    lines.extend(["", "Interactive elements:"])
    bounded_refs = max(1, int(max_refs))
    for item in refs[:bounded_refs]:
        if item.name:
            lines.append(f'- {item.role} "{item.name}" [ref={item.ref}]')
        else:
            lines.append(f"- {item.role} [ref={item.ref}]")
    if not refs:
        lines.append("(no interactive elements)")
    text = "\n".join(lines).strip()
    truncated = len(refs) > bounded_refs
    bounded_chars = max(200, int(max_chars))
    if len(text) > bounded_chars:
        text = f"{text[:bounded_chars].rstrip()}\n...[truncated]"
        truncated = True
    tab.title = title
    tab.url = url
    tab.text = text
    tab.refs = refs
    return BrowserSnapshot(
        target_id=tab.tab_id,
        url=url,
        title=title,
        text=text,
        refs=refs,
        truncated=truncated,
    )


def screenshot_tab(self, tab: BrowserTab, *, ref: str | None = None):
    page = self._require_page(tab)
    out_path = create_artifact_path("screenshots", f"{tab.tab_id}-{uuid.uuid4().hex[:12]}.png")
    if str(ref or "").strip():
        locator = self._locator_for_ref(tab, str(ref))
        locator.screenshot(path=str(out_path))
    else:
        page.screenshot(path=str(out_path), full_page=True)
    self._sync_tab(tab, page)
    return record_artifact(
        tab,
        kind="screenshot",
        path=out_path,
        content_type="image/png",
        size_bytes=out_path.stat().st_size,
        ref=str(ref).strip() or None,
    )


def pdf_tab(self, tab: BrowserTab):
    page = self._require_page(tab)
    out_path = create_artifact_path("pdf", f"{tab.tab_id}-{uuid.uuid4().hex[:12]}.pdf")
    page.pdf(path=str(out_path), print_background=True)
    self._sync_tab(tab, page)
    return record_artifact(
        tab,
        kind="pdf",
        path=out_path,
        content_type="application/pdf",
        size_bytes=out_path.stat().st_size,
    )


def download_ref(self, tab: BrowserTab, *, ref: str, requested_path: str | None = None):
    page = self._require_page(tab)
    locator = self._locator_for_ref(tab, ref)
    timeout_ms = self._interaction_timeout_ms()
    with page.expect_download(timeout=timeout_ms) as download_info:
        locator.click(timeout=timeout_ms)
    download = download_info.value
    suggested_filename = sanitize_artifact_filename(
        getattr(download, "suggested_filename", None) or "download.bin",
        default="download.bin",
    )
    out_path = self._download_output_path(tab, suggested_filename=suggested_filename, requested_path=requested_path)
    download.save_as(str(out_path))
    self._settle_page(page, timeout_ms=1500)
    self._sync_tab(tab, page)
    content_type = mimetypes.guess_type(suggested_filename)[0] or "application/octet-stream"
    download_url = str(getattr(download, "url", "") or tab.url)
    return record_artifact(
        tab,
        kind="download",
        path=out_path,
        content_type=content_type,
        size_bytes=out_path.stat().st_size,
        ref=ref,
        url=download_url,
        title=tab.title,
        suggested_filename=suggested_filename,
    )


def wait_for_download(
    self,
    tab: BrowserTab,
    *,
    timeout_ms: int | None = None,
    requested_path: str | None = None,
):
    page = self._require_page(tab)
    bounded_timeout = max(250, int(timeout_ms or 5000))
    with page.expect_download(timeout=bounded_timeout) as download_info:
        page.wait_for_timeout(bounded_timeout)
    download = download_info.value
    suggested_filename = sanitize_artifact_filename(
        getattr(download, "suggested_filename", None) or "download.bin",
        default="download.bin",
    )
    out_path = self._download_output_path(tab, suggested_filename=suggested_filename, requested_path=requested_path)
    download.save_as(str(out_path))
    self._settle_page(page, timeout_ms=1500)
    self._sync_tab(tab, page)
    content_type = mimetypes.guess_type(suggested_filename)[0] or "application/octet-stream"
    download_url = str(getattr(download, "url", "") or tab.url)
    return record_artifact(
        tab,
        kind="download",
        path=out_path,
        content_type=content_type,
        size_bytes=out_path.stat().st_size,
        url=download_url,
        title=tab.title,
        suggested_filename=suggested_filename,
    )


def get_cookies(self, tab: BrowserTab) -> list[dict[str, object]]:
    context = self._contexts.get(tab.profile)
    if context is None:
        return []
    try:
        raw = context.cookies([tab.url] if str(tab.url or "").strip() else None)
    except Exception:
        raw = context.cookies()
    cookies: list[dict[str, object]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        payload: dict[str, object] = {
            "name": str(item.get("name") or ""),
            "value": str(item.get("value") or ""),
            "domain": str(item.get("domain") or ""),
            "path": str(item.get("path") or ""),
            "httpOnly": bool(item.get("httpOnly")),
            "secure": bool(item.get("secure")),
            "sameSite": str(item.get("sameSite") or ""),
        }
        if item.get("expires") is not None:
            payload["expires"] = item.get("expires")
        cookies.append(payload)
    return cookies


def set_cookies(self, tab: BrowserTab, cookies: list[dict[str, object]]) -> None:
    context = self._contexts.get(tab.profile)
    if context is None:
        raise ValueError(f"profile is not running: {tab.profile}")
    context.add_cookies([dict(item) for item in cookies])


def clear_cookies(self, tab: BrowserTab) -> int:
    existing = self.get_cookies(tab)
    context = self._contexts.get(tab.profile)
    if context is None:
        return 0
    context.clear_cookies()
    return len(existing)


def get_storage_state(self, tab: BrowserTab) -> dict[str, object]:
    page = self._pages.get(tab.tab_id)
    if page is None:
        return {"origins": []}
    payload = page.evaluate(
        """
        () => ({
          origins: [
            {
              origin: window.location.origin,
              localStorage: Object.entries(window.localStorage || {}).map(([name, value]) => ({ name, value })),
              sessionStorage: Object.entries(window.sessionStorage || {}).map(([name, value]) => ({ name, value })),
            }
          ],
        })
        """
    )
    return dict(payload or {"origins": []})


def get_storage(self, tab: BrowserTab, *, storage_kind: str) -> dict[str, str]:
    page = self._pages.get(tab.tab_id)
    if page is None:
        return {}
    payload = page.evaluate(
        """
        (kind) => {
          const storage = kind === "local" ? window.localStorage : window.sessionStorage;
          return Object.fromEntries(Object.entries(storage || {}).map(([name, value]) => [name, String(value)]));
        }
        """,
        storage_kind,
    )
    return {
        str(name): str(value)
        for name, value in dict(payload or {}).items()
        if str(name).strip()
    }


def set_storage(self, tab: BrowserTab, *, storage_kind: str, items: dict[str, str]) -> None:
    page = self._pages.get(tab.tab_id)
    if page is None:
        raise ValueError(f"tab is not attached to a live page: {tab.tab_id}")
    page.evaluate(
        """
        ({ kind, items }) => {
          const storage = kind === "local" ? window.localStorage : window.sessionStorage;
          for (const [name, value] of Object.entries(items || {})) {
            storage.setItem(name, String(value));
          }
        }
        """,
        {"kind": storage_kind, "items": dict(items)},
    )


def clear_storage(self, tab: BrowserTab, *, storage_kind: str) -> int:
    existing = self.get_storage(tab, storage_kind=storage_kind)
    page = self._pages.get(tab.tab_id)
    if page is None:
        return 0
    page.evaluate(
        """
        (kind) => {
          const storage = kind === "local" ? window.localStorage : window.sessionStorage;
          storage.clear();
        }
        """,
        storage_kind,
    )
    return len(existing)


def _download_output_path(self, tab: BrowserTab, *, suggested_filename: str, requested_path: str | None) -> Path:
    del self
    if str(requested_path or "").strip():
        out_path = resolve_artifact_output_path("downloads", str(requested_path))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        return out_path
    return create_artifact_path(
        "downloads",
        f"{tab.tab_id}-{uuid.uuid4().hex[:12]}-{suggested_filename}",
    )


def bind_live_driver_tab_ops(cls) -> None:
    for fn in (
        open_tab,
        focus_tab,
        close_tab,
        navigate,
        snapshot_tab,
        screenshot_tab,
        pdf_tab,
        download_ref,
        wait_for_download,
        get_cookies,
        set_cookies,
        clear_cookies,
        get_storage_state,
        get_storage,
        set_storage,
        clear_storage,
        _download_output_path,
    ):
        setattr(cls, fn.__name__, fn)
