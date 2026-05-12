from __future__ import annotations

from typing import Any


def browser_event_name(action: str) -> str:
    normalized = str(action or "").strip().lower()
    mapping = {
        "status": "browser_status",
        "snapshot": "browser_snapshot",
        "screenshot": "browser_screenshot",
        "pdf": "browser_pdf",
        "download": "browser_download",
        "wait_download": "browser_download",
        "console": "browser_console",
        "errors": "browser_console",
        "requests": "browser_console",
    }
    return mapping.get(normalized, "browser_action")


def normalize_browser_fallback_payload(
    normalized: dict[str, Any],
    *,
    action: str,
    requested_target: str | None,
    requested_url: str | None,
    requested_ref: str | None,
    requested_paths: list[str] | None,
    requested_input_ref: str | None,
    requested_accept: bool | None,
    requested_prompt_text: str | None,
    browser_text_fn: Any,
) -> dict[str, Any]:
    if requested_ref and not browser_text_fn(normalized.get("ref")):
        normalized["ref"] = requested_ref
    if requested_input_ref and not browser_text_fn(normalized.get("input_ref")):
        normalized["input_ref"] = requested_input_ref
    if requested_target and not browser_text_fn(normalized.get("target_id")):
        normalized["target_id"] = requested_target
    if requested_url and not browser_text_fn(normalized.get("url")):
        normalized["url"] = requested_url
    if requested_paths and normalized.get("count") is None and action == "upload":
        normalized["count"] = len(requested_paths)
    if requested_accept is not None and "accept" not in normalized and action == "dialog":
        normalized["accept"] = bool(requested_accept)
    if requested_prompt_text and not browser_text_fn(normalized.get("prompt_text")):
        normalized["prompt_text"] = requested_prompt_text
    artifact = normalized.get("artifact")
    if isinstance(artifact, dict):
        path = browser_text_fn(artifact.get("path"))
        if path and not browser_text_fn(normalized.get("path")):
            normalized["path"] = path
        content_type = browser_text_fn(artifact.get("content_type"))
        if content_type and not browser_text_fn(normalized.get("content_type")):
            normalized["content_type"] = content_type
        created_at = artifact.get("created_at")
        if created_at is not None and normalized.get("created_at") is None:
            normalized["created_at"] = created_at
        suggested_filename = browser_text_fn(artifact.get("suggested_filename"))
        if suggested_filename and not browser_text_fn(normalized.get("suggested_filename")):
            normalized["suggested_filename"] = suggested_filename
        size_bytes = artifact.get("size_bytes")
        if size_bytes is not None and normalized.get("size") is None:
            normalized["size"] = int(size_bytes)
        kind = browser_text_fn(artifact.get("kind"))
        if kind and not browser_text_fn(normalized.get("format")):
            normalized["format"] = "png" if kind == "screenshot" else ("zip" if kind == "trace" else kind)
    return normalized


def browser_request_error(
    *,
    action: str,
    kind: str | None,
    ref: str | None,
    start_ref: str | None,
    end_ref: str | None,
    width: int | None,
    height: int | None,
    normalize_browser_act_kind_fn: Any,
    browser_text_fn: Any,
) -> str | None:
    if action != "act":
        return None
    normalized_kind = normalize_browser_act_kind_fn(kind)
    if normalized_kind == "scroll_into_view" and not browser_text_fn(ref):
        return "action requires ref"
    if normalized_kind == "drag" and (not browser_text_fn(start_ref) or not browser_text_fn(end_ref)):
        return "action requires ref"
    if normalized_kind == "resize":
        if width is None or height is None or int(width) <= 0 or int(height) <= 0:
            return "resize requires width and height"
    return None
