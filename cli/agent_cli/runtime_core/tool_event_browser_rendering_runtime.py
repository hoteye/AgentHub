from __future__ import annotations

from cli.agent_cli.models import ToolEvent


def browser_activity_repr(event: ToolEvent) -> tuple[str, str, str]:
    payload = event.payload or {}
    kind = "browser"
    if event.name == "browser_status":
        title = "Browser status" if event.ok else "Browser status failed"
        return title, _browser_status_detail(payload), kind
    if event.name == "browser_snapshot":
        title = "Browser snapshot" if event.ok else "Browser snapshot failed"
        return title, _browser_snapshot_detail(payload), kind
    if event.name == "browser_action":
        title = "Browser action" if event.ok else "Browser action failed"
        return title, _browser_action_detail(payload), kind
    if event.name == "browser_screenshot":
        title = "Browser screenshot" if event.ok else "Browser screenshot failed"
        return title, _browser_artifact_detail(payload), kind
    if event.name == "browser_pdf":
        title = "Browser pdf" if event.ok else "Browser pdf failed"
        return title, _browser_artifact_detail(payload), kind
    if event.name == "browser_download":
        title = "Browser download" if event.ok else "Browser download failed"
        return title, _browser_artifact_detail(payload), kind
    if event.name == "browser_console":
        surface = _browser_debug_surface(payload)
        if surface == "errors":
            title = "Browser errors" if event.ok else "Browser errors failed"
            return title, _browser_errors_detail(payload), kind
        if surface == "requests":
            title = "Browser requests" if event.ok else "Browser requests failed"
            return title, _browser_requests_detail(payload), kind
        title = "Browser console" if event.ok else "Browser console failed"
        return title, _browser_console_detail(payload), kind
    return event.name, str(payload), kind


def browser_activity_detail(
    event: ToolEvent,
    *,
    browser_activity_repr_fn,
    append_elapsed_detail_fn,
) -> str:
    payload = event.payload or {}
    return append_elapsed_detail_fn(browser_activity_repr_fn(event)[1], payload)


def _browser_value(payload: dict, *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _browser_int(payload: dict, *keys: str) -> int | None:
    for key in keys:
        value = payload.get(key)
        if value is None or value == "":
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _append_browser_error(parts: list[str], payload: dict) -> None:
    error = _browser_value(payload, "error", "reason")
    if error:
        parts.append(f"error={error}")


def _compact_browser_text(value: str, *, limit: int = 140) -> str:
    compact = " ".join(str(value or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _browser_debug_surface(payload: dict) -> str:
    for key in ("action", "surface", "view"):
        value = str(payload.get(key) or "").strip().lower()
        if value in {"errors", "requests", "console"}:
            return value
    return "console"


def _browser_status_detail(payload: dict) -> str:
    parts = []
    _append_browser_error(parts, payload)
    profile = str(payload.get("profile") or "").strip()
    if profile:
        parts.append(f"profile={profile}")
    running = payload.get("running")
    if isinstance(running, bool):
        parts.append(f"running={running}")
    tabs = payload.get("tabs")
    if tabs is not None:
        parts.append(f"tabs={tabs}")
    return " | ".join(parts)


def _browser_snapshot_detail(payload: dict) -> str:
    parts = []
    _append_browser_error(parts, payload)
    ref = _browser_value(payload, "ref", "snapshot_ref", "snapshot_id")
    if ref:
        parts.append(f"ref={ref}")
    target = _browser_value(payload, "target_id", "tab_id", "target")
    if target:
        parts.append(f"target={target}")
    ref = _browser_value(payload, "ref")
    if ref:
        parts.append(f"ref={ref}")
    url = _browser_value(payload, "url", "page_url")
    if url:
        parts.append(f"url={url}")
    title = _browser_value(payload, "title", "page_title")
    if title:
        parts.append(f"title={title}")
    element_count = _browser_int(payload, "element_count", "node_count", "count")
    if element_count is not None:
        parts.append(f"elements={element_count}")
    ref_count = _browser_int(payload, "ref_count", "element_ref_count")
    if ref_count is not None:
        parts.append(f"refs={ref_count}")
    if payload.get("truncated"):
        parts.append("truncated=true")
    preview = _browser_value(payload, "preview", "summary", "text")
    if preview:
        parts.append(f"preview={_compact_browser_text(preview)}")
    return " | ".join(parts)


def _browser_action_detail(payload: dict) -> str:
    parts = []
    _append_browser_error(parts, payload)
    action = str(payload.get("action") or "").strip()
    if action:
        parts.append(f"action={action}")
    operation = str(payload.get("operation") or "").strip()
    if operation:
        parts.append(f"op={operation}")
    profile = str(payload.get("profile") or "").strip()
    if profile:
        parts.append(f"profile={profile}")
    target = str(payload.get("target_id") or "").strip()
    if target:
        parts.append(f"target={target}")
    ref = str(payload.get("ref") or "").strip()
    if not ref:
        ref = str(payload.get("input_ref") or "").strip()
    if ref:
        parts.append(f"ref={ref}")
    storage_kind = str(payload.get("storage_kind") or "").strip()
    if storage_kind:
        parts.append(f"storage={storage_kind}")
    url = str(payload.get("url") or "").strip()
    if url:
        parts.append(f"url={url}")
    path = _browser_value(payload, "path")
    if path:
        parts.append(f"path={path}")
    fmt = _browser_value(payload, "format")
    if fmt:
        parts.append(f"format={fmt}")
    count = payload.get("count")
    if count is not None:
        parts.append(f"count={count}")
    capture_mode = _browser_value(payload, "capture_mode", "highlight_mode")
    if capture_mode:
        parts.append(f"mode={capture_mode}")
    trace_id = _browser_value(payload, "trace_id")
    if trace_id:
        parts.append(f"trace_id={trace_id}")
    duration_ms = _browser_int(payload, "duration_ms")
    if duration_ms is not None:
        parts.append(f"duration_ms={duration_ms}")
    message = _browser_value(payload, "message")
    if message:
        parts.append(f"msg={_compact_browser_text(message)}")
    if "accept" in payload:
        parts.append(f"accept={bool(payload.get('accept'))}")
    return " | ".join(parts)


def _browser_artifact_detail(payload: dict) -> str:
    parts = []
    _append_browser_error(parts, payload)
    path = _browser_value(payload, "path", "artifact", "file_path", "output_path")
    if path:
        parts.append(f"path={path}")
    target = _browser_value(payload, "target_id", "tab_id", "target")
    if target:
        parts.append(f"target={target}")
    ref = _browser_value(payload, "ref")
    if ref:
        parts.append(f"ref={ref}")
    url = _browser_value(payload, "url", "page_url")
    if url:
        parts.append(f"url={url}")
    fmt = _browser_value(payload, "format", "artifact_type")
    if fmt:
        parts.append(f"format={fmt}")
    width = _browser_int(payload, "width")
    height = _browser_int(payload, "height")
    if width is not None and height is not None:
        parts.append(f"viewport={width}x{height}")
    pages = _browser_int(payload, "page_count", "pages")
    if pages is not None:
        parts.append(f"pages={pages}")
    size = payload.get("size")
    if size is not None:
        parts.append(f"size={size}")
    suggested_filename = _browser_value(payload, "suggested_filename")
    if suggested_filename:
        parts.append(f"file={suggested_filename}")
    return " | ".join(parts)


def _browser_console_detail(payload: dict) -> str:
    parts = []
    _append_browser_error(parts, payload)
    target = _browser_value(payload, "target_id", "tab_id", "target")
    if target:
        parts.append(f"target={target}")
    url = _browser_value(payload, "url", "page_url")
    if url:
        parts.append(f"url={url}")
    entries = payload.get("entries") or payload.get("messages") or []
    count = _browser_int(payload, "count")
    if count is None and isinstance(entries, list):
        count = len(entries)
    if count is not None:
        parts.append(f"count={count}")
    level = _browser_value(payload, "level")
    message = _browser_value(payload, "message")
    if not level and isinstance(entries, list) and entries:
        first = entries[0] or {}
        if isinstance(first, dict):
            level = _browser_value(first, "level")
            message = message or _browser_value(first, "message", "text")
    if level:
        parts.append(f"level={level}")
    if message:
        parts.append(f"msg={_compact_browser_text(message)}")
    levels = payload.get("levels")
    if isinstance(levels, dict) and levels:
        ordered = ",".join(
            f"{name}:{levels[name]}"
            for name in sorted(levels)
            if str(name).strip()
        )
        if ordered:
            parts.append(f"levels={ordered}")
    return " | ".join(parts)


def _browser_errors_detail(payload: dict) -> str:
    parts = []
    _append_browser_error(parts, payload)
    target = _browser_value(payload, "target_id", "tab_id", "target")
    if target:
        parts.append(f"target={target}")
    url = _browser_value(payload, "url", "page_url")
    if url:
        parts.append(f"url={url}")
    entries = payload.get("entries") or payload.get("errors") or []
    count = _browser_int(payload, "count")
    if count is None and isinstance(entries, list):
        count = len(entries)
    if count is not None:
        parts.append(f"count={count}")
    first_level = _browser_value(payload, "level")
    first_message = _browser_value(payload, "message")
    if isinstance(entries, list) and entries:
        first = entries[0]
        if isinstance(first, dict):
            if not first_level:
                first_level = _browser_value(first, "level", "type")
            if not first_message:
                first_message = _browser_value(first, "message", "text", "error")
    if first_level:
        parts.append(f"level={first_level}")
    if first_message:
        parts.append(f"msg={_compact_browser_text(first_message)}")
    levels = payload.get("levels") or payload.get("errors_by_level")
    if isinstance(levels, dict) and levels:
        ordered = ",".join(
            f"{name}:{levels[name]}"
            for name in sorted(levels)
            if str(name).strip()
        )
        if ordered:
            parts.append(f"levels={ordered}")
    return " | ".join(parts)


def _browser_requests_detail(payload: dict) -> str:
    parts = []
    _append_browser_error(parts, payload)
    target = _browser_value(payload, "target_id", "tab_id", "target")
    if target:
        parts.append(f"target={target}")
    entries = payload.get("entries") or payload.get("requests") or []
    count = _browser_int(payload, "count")
    if count is None and isinstance(entries, list):
        count = len(entries)
    if count is not None:
        parts.append(f"count={count}")
    first_method = _browser_value(payload, "method")
    first_status = _browser_value(payload, "status")
    first_resource = _browser_value(payload, "resource_type", "resource")
    first_url = _browser_value(payload, "url", "request_url", "page_url")
    first_outcome = _browser_value(payload, "outcome")
    first_message = _browser_value(payload, "message")
    if isinstance(entries, list) and entries:
        first = entries[0]
        if isinstance(first, dict):
            if not first_method:
                first_method = _browser_value(first, "method")
            if not first_status:
                first_status = _browser_value(first, "status")
            if not first_resource:
                first_resource = _browser_value(first, "resource_type", "resource")
            if not first_url:
                first_url = _browser_value(first, "url", "request_url")
            if not first_outcome:
                first_outcome = _browser_value(first, "outcome")
            if not first_message:
                first_message = _browser_value(first, "message", "text")
    if first_method:
        parts.append(f"method={first_method}")
    if first_status:
        parts.append(f"status={first_status}")
    if first_resource:
        parts.append(f"resource={first_resource}")
    if first_url:
        parts.append(f"url={first_url}")
    if first_outcome:
        parts.append(f"outcome={first_outcome}")
    if first_message:
        parts.append(f"msg={_compact_browser_text(first_message)}")
    outcomes = payload.get("outcomes")
    if isinstance(outcomes, dict) and outcomes:
        ordered = ",".join(
            f"{name}:{outcomes[name]}"
            for name in sorted(outcomes)
            if str(name).strip()
        )
        if ordered:
            parts.append(f"outcomes={ordered}")
    return " | ".join(parts)
