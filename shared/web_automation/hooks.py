from __future__ import annotations

from pathlib import Path

from shared.web_automation.observe import append_console_entry
from shared.web_automation.snapshot import ensure_tab_snapshot_seed, render_tab_text
from shared.web_automation.types import BrowserDialogHook, BrowserTab, BrowserUploadHook


def arm_upload_hook(
    tab: BrowserTab,
    *,
    paths: list[str],
    ref: str | None = None,
    input_ref: str | None = None,
    timeout_ms: int | None = None,
) -> dict[str, object]:
    ensure_tab_snapshot_seed(tab)
    normalized_paths = _normalize_upload_paths(paths)
    if not normalized_paths:
        raise ValueError("upload requires at least one file path")
    normalized_ref = _normalize_optional_ref(ref)
    normalized_input_ref = _normalize_optional_ref(input_ref)
    if normalized_ref:
        _require_ref(tab, normalized_ref)
    if normalized_input_ref:
        _require_ref(tab, normalized_input_ref)
    tab.armed_upload = BrowserUploadHook(
        paths=normalized_paths,
        ref=normalized_ref,
        input_ref=normalized_input_ref,
        timeout_ms=(int(timeout_ms) if timeout_ms is not None else None),
    )
    _refresh_tab_text(tab)
    target_ref = normalized_input_ref or normalized_ref
    message = (
        f"Armed upload hook for ref {target_ref} with {len(normalized_paths)} file(s)"
        if target_ref
        else f"Armed upload hook with {len(normalized_paths)} file(s)"
    )
    append_console_entry(
        tab,
        message_type="info",
        text=message,
        location={"url": tab.url},
    )
    payload: dict[str, object] = {
        "ok": True,
        "action": "upload",
        "operation": "hook",
        "target_id": tab.tab_id,
        "url": tab.url,
        "count": len(normalized_paths),
        "paths": list(normalized_paths),
        "message": message,
    }
    if normalized_ref:
        payload["ref"] = normalized_ref
    if normalized_input_ref:
        payload["input_ref"] = normalized_input_ref
    if timeout_ms is not None:
        payload["timeout_ms"] = int(timeout_ms)
    return payload


def arm_dialog_hook(
    tab: BrowserTab,
    *,
    accept: bool = True,
    prompt_text: str | None = None,
    timeout_ms: int | None = None,
) -> dict[str, object]:
    ensure_tab_snapshot_seed(tab)
    normalized_prompt = str(prompt_text or "").strip() or None
    tab.armed_dialog = BrowserDialogHook(
        accept=bool(accept),
        prompt_text=normalized_prompt,
        timeout_ms=(int(timeout_ms) if timeout_ms is not None else None),
    )
    _refresh_tab_text(tab)
    decision = "accept" if tab.armed_dialog.accept else "dismiss"
    message = f"Armed dialog hook to {decision}"
    if normalized_prompt:
        message += " with prompt text"
    append_console_entry(
        tab,
        message_type="info",
        text=message,
        location={"url": tab.url},
    )
    payload: dict[str, object] = {
        "ok": True,
        "action": "dialog",
        "operation": "hook",
        "target_id": tab.tab_id,
        "url": tab.url,
        "accept": bool(accept),
        "message": message,
    }
    if normalized_prompt:
        payload["prompt_text"] = normalized_prompt
    if timeout_ms is not None:
        payload["timeout_ms"] = int(timeout_ms)
    return payload


def consume_click_hooks(tab: BrowserTab, *, clicked_ref: str) -> list[str]:
    messages: list[str] = []
    if tab.armed_upload and _upload_targets_ref(tab.armed_upload, clicked_ref):
        files = list(tab.armed_upload.paths)
        tab.uploaded_files[clicked_ref] = files
        tab.armed_upload = None
        messages.append(f"Applied armed upload to ref {clicked_ref} ({len(files)} file(s))")
    if tab.armed_dialog is not None:
        decision = "accepted" if tab.armed_dialog.accept else "dismissed"
        prompt_note = " with prompt text" if tab.armed_dialog.prompt_text else ""
        tab.last_dialog = f"{decision}{prompt_note}"
        tab.armed_dialog = None
        messages.append(f"Handled armed dialog: {decision}")
    if messages:
        _refresh_tab_text(tab)
        for message in messages:
            append_console_entry(
                tab,
                message_type="info",
                text=message,
                location={"url": tab.url},
            )
    return messages


def _upload_targets_ref(hook: BrowserUploadHook, clicked_ref: str) -> bool:
    target_ref = hook.input_ref or hook.ref
    if not target_ref:
        return True
    return target_ref == clicked_ref


def _normalize_optional_ref(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _normalize_upload_paths(paths: list[str]) -> list[str]:
    normalized: list[str] = []
    for item in paths:
        raw = str(item or "").strip()
        if not raw:
            continue
        candidate = Path(raw).expanduser()
        if not candidate.is_file():
            raise ValueError(f"upload path not found: {raw}")
        normalized.append(str(candidate.resolve()))
    return normalized


def _require_ref(tab: BrowserTab, ref: str) -> None:
    for item in tab.refs:
        if item.ref == ref:
            return
    raise ValueError(f"unknown ref: {ref}")


def _refresh_tab_text(tab: BrowserTab) -> None:
    tab.text = render_tab_text(tab)
