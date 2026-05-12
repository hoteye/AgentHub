from __future__ import annotations

from urllib.parse import urlparse

from shared.web_automation.types import BrowserPageRef, BrowserSnapshot, BrowserTab

DEFAULT_SNAPSHOT_MAX_CHARS = 4000
DEFAULT_SNAPSHOT_MAX_REFS = 50


def ensure_tab_snapshot_seed(tab: BrowserTab) -> None:
    if not tab.title.strip():
        tab.title = _default_title(tab.url)
    if not tab.text.strip():
        tab.text = render_tab_text(tab)
    if not tab.refs:
        tab.refs = _default_refs(tab)


def build_snapshot(
    tab: BrowserTab,
    *,
    max_chars: int = DEFAULT_SNAPSHOT_MAX_CHARS,
    max_refs: int = DEFAULT_SNAPSHOT_MAX_REFS,
) -> BrowserSnapshot:
    ensure_tab_snapshot_seed(tab)
    bounded_chars = max(200, int(max_chars))
    bounded_refs = max(1, int(max_refs))
    text = _normalize_text(tab.text)
    truncated = len(text) > bounded_chars
    if truncated:
        text = f"{text[:bounded_chars].rstrip()}\n...[truncated]"
    refs = [_copy_ref(ref) for ref in tab.refs[:bounded_refs]]
    return BrowserSnapshot(
        target_id=tab.tab_id,
        url=tab.url,
        title=tab.title,
        text=text,
        refs=refs,
        truncated=truncated or len(tab.refs) > bounded_refs,
    )


def _copy_ref(ref: BrowserPageRef) -> BrowserPageRef:
    return BrowserPageRef(ref=ref.ref, role=ref.role, name=ref.name, url=ref.url)


def _normalize_text(text: str) -> str:
    normalized = "\n".join(part.rstrip() for part in str(text or "").replace("\r\n", "\n").split("\n"))
    return normalized.strip()


def _default_title(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return str(url or "").strip() or "Untitled tab"
    path = parsed.path.rstrip("/")
    if path and path != "/":
        return f"{parsed.netloc}{path}"
    return parsed.netloc


def _default_text(tab: BrowserTab) -> str:
    parsed = urlparse(str(tab.url or "").strip())
    lines = [
        "Synthetic browser snapshot",
        f"Target: {tab.tab_id}",
        f"Profile: {tab.profile}",
        f"URL: {tab.url or '(empty)'}",
        f"Title: {tab.title or _default_title(tab.url)}",
    ]
    if parsed.netloc:
        lines.append(f"Host: {parsed.netloc}")
    if parsed.path and parsed.path != "/":
        lines.append(f"Path: {parsed.path}")
    if parsed.query:
        lines.append(f"Query: {parsed.query}")
    lines.append("Mode: local-host in-memory state only")
    return "\n".join(lines)


def render_tab_text(tab: BrowserTab) -> str:
    lines = _default_text(tab).splitlines()
    if tab.input_state:
        lines.append("Form state:")
        for ref, value in sorted(tab.input_state.items()):
            lines.append(f"Field {ref}: {value}")
    if tab.uploaded_files:
        lines.append("Uploaded files:")
        for ref, paths in sorted(tab.uploaded_files.items()):
            joined = ", ".join(paths)
            lines.append(f"Upload {ref}: {joined}")
    if tab.armed_upload is not None:
        target_ref = tab.armed_upload.input_ref or tab.armed_upload.ref or "(next file chooser)"
        lines.append(f"Armed upload: {target_ref} ({len(tab.armed_upload.paths)} file(s))")
    if tab.armed_dialog is not None:
        decision = "accept" if tab.armed_dialog.accept else "dismiss"
        prompt_note = " with prompt text" if tab.armed_dialog.prompt_text else ""
        lines.append(f"Armed dialog: {decision}{prompt_note}")
    if tab.last_dialog:
        lines.append(f"Last dialog: {tab.last_dialog}")
    return "\n".join(lines)


def _default_refs(tab: BrowserTab) -> list[BrowserPageRef]:
    url = str(tab.url or "").strip()
    if not url:
        return []
    name = tab.title.strip() or _default_title(url)
    return [BrowserPageRef(ref="r1", role="link", name=name, url=url)]
