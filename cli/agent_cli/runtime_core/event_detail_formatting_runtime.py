from __future__ import annotations

from typing import Any, Callable


def render_view_image_text(payload: dict[str, Any], *, separator: str) -> str:
    parts: list[str] = []
    path = str(payload.get("path") or "").strip()
    if path:
        parts.append(path)
    image_format = str(payload.get("format") or "").strip()
    if image_format:
        parts.append(f"format={image_format}")
    size_bytes = payload.get("size_bytes")
    if size_bytes is not None:
        parts.append(f"size={size_bytes}")
    return separator.join(parts)


def render_prepare_send_detail(payload: dict[str, Any], *, draft_limit: int) -> str:
    draft_text = str(payload.get("draft_text") or "").strip()
    parts = [draft_text[:draft_limit]] if draft_text else []
    if payload.get("approval_message"):
        parts.append(str(payload["approval_message"]))
    risk_guard = payload.get("risk_guard") or {}
    if risk_guard.get("summary"):
        parts.append(f"risk: {risk_guard['summary']}")
    suggestions = payload.get("recovery_suggestions") or []
    if suggestions:
        parts.append("suggestions: " + " | ".join(str(item) for item in suggestions[:3]))
    return "\n".join(part for part in parts if part)


def render_send_reply_detail(payload: dict[str, Any]) -> str:
    parts = [f"confirmed={bool(payload.get('confirmed'))}"]
    if payload.get("approval_message"):
        parts.append(str(payload["approval_message"]))
    risk_guard = payload.get("risk_guard") or {}
    if risk_guard.get("summary"):
        parts.append(f"risk: {risk_guard['summary']}")
    suggestions = payload.get("recovery_suggestions") or []
    if suggestions:
        parts.append("suggestions: " + " | ".join(str(item) for item in suggestions[:3]))
    return "\n".join(part for part in parts if part)


def render_file_activity(
    event: Any,
    payload: dict[str, Any],
    *,
    is_soft_failure: bool,
    append_elapsed_detail_fn: Callable[[str, dict[str, Any]], str],
) -> str:
    if event.name == "glob_files":
        if not event.ok and not is_soft_failure:
            return str(payload.get("error") or "glob files failed").strip()
        parts = [f"count={int(payload.get('count') or 0)}"]
        pattern_text = str(payload.get("pattern") or "").strip()
        if pattern_text:
            parts.append(f"pattern={pattern_text}")
        path_text = str(payload.get("path") or ".").strip()
        if path_text:
            parts.append(f"path={path_text}")
        parts.extend(str(item).strip() for item in (payload.get("paths") or [])[:6] if str(item).strip())
        if not payload.get("paths"):
            parts.append(str(payload.get("text") or "No files found.").strip())
        return append_elapsed_detail_fn("\n".join(parts), payload)
    if event.name == "file_list":
        if not event.ok and not is_soft_failure:
            return str(payload.get("error") or "file list failed").strip()
        parts = ["legacy_alias=file_list", f"count={int(payload.get('count') or 0)}"]
        path_text = str(payload.get("path") or "").strip()
        if path_text:
            parts.append(f"path={path_text}")
        parts.extend(
            str(item.get("path") or "").strip()
            for item in (payload.get("files") or [])[:6]
            if str(item.get("path") or "").strip()
        )
        return append_elapsed_detail_fn("\n".join(parts), payload)
    if event.name == "list_dir":
        if not event.ok and not is_soft_failure:
            return str(payload.get("error") or "list dir failed").strip()
        parts = [f"count={int(payload.get('count') or 0)}"]
        dir_path = str(payload.get("dir_path") or ".").strip()
        if dir_path:
            parts.append(f"dir_path={dir_path}")
        text = str(payload.get("text") or "").strip()
        if text:
            parts.append(text)
        return append_elapsed_detail_fn("\n".join(parts), payload)
    if event.name == "file_search":
        if not event.ok and not is_soft_failure:
            return str(payload.get("error") or "file search failed").strip()
        parts = ["legacy_alias=file_search", f"count={int(payload.get('count') or 0)}"]
        query_text = str(payload.get("query") or "").strip()
        if query_text:
            parts.append(f"query={query_text}")
        path_text = str(payload.get("path") or "").strip()
        if path_text:
            parts.append(f"path={path_text}")
        for item in (payload.get("matches") or [])[:4]:
            if not isinstance(item, dict):
                continue
            match_path = str(item.get("path") or "").strip()
            line_value = item.get("line")
            match_text = str(item.get("text") or "").strip()
            if match_path and line_value not in (None, "") and match_text:
                parts.append(f"{match_path}:{line_value} | {match_text}")
            elif match_path:
                parts.append(match_path)
        return append_elapsed_detail_fn("\n".join(parts), payload)
    if event.name == "grep_files":
        if not event.ok and not is_soft_failure:
            return str(payload.get("error") or "grep files failed").strip()
        parts = [f"count={int(payload.get('count') or 0)}"]
        pattern_text = str(payload.get("pattern") or "").strip()
        if pattern_text:
            parts.append(f"pattern={pattern_text}")
        path_text = str(payload.get("path") or ".").strip()
        if path_text:
            parts.append(f"path={path_text}")
        parts.extend(str(item).strip() for item in (payload.get("paths") or [])[:6] if str(item).strip())
        if not payload.get("paths"):
            parts.append(str(payload.get("text") or "No matches found.").strip())
        return append_elapsed_detail_fn("\n".join(parts), payload)
    if event.name == "file_read":
        if not event.ok and not is_soft_failure:
            return str(payload.get("error") or "file read failed").strip()
        parts = [str(payload.get("path") or "-")]
        if payload.get("truncated"):
            parts.append("truncated")
        line_count = payload.get("line_count")
        if line_count is not None:
            parts.append(f"lines={int(line_count)}")
        return append_elapsed_detail_fn(" | ".join(parts), payload)
    if event.name == "read_file":
        if not event.ok and not is_soft_failure:
            return str(payload.get("error") or "read file failed").strip()
        parts = [str(payload.get("file_path") or payload.get("path") or "-")]
        if payload.get("truncated"):
            parts.append("truncated")
        line_count = payload.get("line_count")
        if line_count is not None:
            parts.append(f"lines={int(line_count)}")
        text = str(payload.get("text") or "").strip()
        if text:
            return append_elapsed_detail_fn("\n".join([" | ".join(parts), text]), payload)
        return append_elapsed_detail_fn(" | ".join(parts), payload)
    return ""


def render_web_activity(
    event: Any,
    payload: dict[str, Any],
    *,
    append_elapsed_detail_fn: Callable[[str, dict[str, Any]], str],
    first_excerpt_text_fn: Callable[[dict[str, Any]], str],
) -> str:
    if event.name == "web_search":
        results = payload.get("results") or []
        lines: list[str] = []
        query = str(payload.get("query") or "").strip()
        if query:
            lines.append(f"query={query}")
        lines.append(f"count={int(payload.get('count') or 0)}")
        lines.extend(
            f"{item.get('rank')}. {item.get('source_domain')} | {item.get('credibility_label')} | {item.get('title')}"
            for item in results[:10]
        )
        return append_elapsed_detail_fn("\n".join(lines), payload)
    if event.name in {"web_fetch", "open", "click"}:
        if event.name == "web_fetch":
            pieces = [part for part in [str(payload.get("ref_id") or "").strip(), str(payload.get("source_domain") or "").strip(), str(payload.get("title") or "").strip()] if part]
            default_text = "page loaded"
        elif event.name == "open":
            pieces = [item for item in [str(payload.get("ref_id") or "").strip(), str(payload.get("source_domain") or "").strip(), str(payload.get("title") or "").strip()] if item]
            default_text = "page opened"
        else:
            pieces = [item for item in [str(payload.get("ref_id") or "").strip(), str(payload.get("title") or "").strip()] if item]
            default_text = "link opened"
        scope = str(payload.get("source_scope") or "").strip()
        link_count = payload.get("link_count")
        if scope:
            pieces.append(f"scope={scope}")
        if link_count is not None:
            pieces.append(f"links={int(link_count)}")
        preview = first_excerpt_text_fn(payload)
        if preview:
            pieces.append(f"preview={preview}")
        return append_elapsed_detail_fn(" | ".join(pieces) if pieces else default_text, payload)
    if event.name == "find":
        parts = [f"count={int(payload.get('count') or 0)}"]
        ref_id = str(payload.get("ref_id") or "").strip()
        if ref_id:
            parts.append(ref_id)
        scope = str(payload.get("source_scope") or "").strip()
        if scope:
            parts.append(f"scope={scope}")
        return append_elapsed_detail_fn(" | ".join(parts), payload)
    return ""


def render_file_detail(event: Any, payload: dict[str, Any], *, is_soft_failure: bool) -> str:
    if event.name == "glob_files":
        if not event.ok and not is_soft_failure:
            return str(payload.get("error") or "glob files failed").strip()
        parts = [
            f"pattern={payload.get('pattern') or ''}",
            f"path={payload.get('path') or '.'}",
            f"count={int(payload.get('count') or 0)}",
        ]
        if payload.get("truncated"):
            parts.append("truncated=true")
        for item in (payload.get("paths") or [])[:20]:
            parts.append(str(item))
        if not payload.get("paths"):
            parts.append(str(payload.get("text") or "No files found.").strip())
        return "\n".join(parts)
    if event.name == "file_list":
        if not event.ok:
            return str(payload.get("error") or "file list failed").strip()
        parts = [f"path={payload.get('path') or '.'}", f"count={int(payload.get('count') or 0)}"]
        for item in (payload.get("files") or [])[:20]:
            parts.append(f"{item.get('path')} | size={int(item.get('size') or 0)}")
        return "\n".join(parts)
    if event.name == "list_dir":
        if not event.ok and not is_soft_failure:
            return str(payload.get("error") or "list dir failed").strip()
        parts = [
            f"dir_path={payload.get('dir_path') or '.'}",
            f"offset={int(payload.get('offset') or 1)}",
            f"limit={int(payload.get('limit') or 0)}",
            f"depth={int(payload.get('depth') or 0)}",
            f"count={int(payload.get('count') or 0)}",
        ]
        text = str(payload.get("text") or "").strip()
        if text:
            parts.append(text)
        return "\n".join(parts)
    if event.name == "file_search":
        if not event.ok and not is_soft_failure:
            return str(payload.get("error") or "file search failed").strip()
        parts = [
            f"query={payload.get('query') or ''}",
            f"path={payload.get('path') or '.'}",
            f"count={int(payload.get('count') or 0)}",
            f"file_count={int(payload.get('file_count') or 0)}",
        ]
        for item in (payload.get("matches") or [])[:20]:
            if not isinstance(item, dict):
                continue
            match_path = str(item.get("path") or "").strip()
            line_value = item.get("line")
            match_text = str(item.get("text") or "").strip()
            if match_path and line_value not in (None, "") and match_text:
                parts.append(f"{match_path}:{line_value} | {match_text}")
            elif match_path:
                parts.append(match_path)
        return "\n".join(parts)
    if event.name == "grep_files":
        if not event.ok and not is_soft_failure:
            return str(payload.get("error") or "grep files failed").strip()
        parts = [
            f"pattern={payload.get('pattern') or ''}",
            f"path={payload.get('path') or '.'}",
            f"count={int(payload.get('count') or 0)}",
        ]
        for item in (payload.get("paths") or [])[:20]:
            parts.append(str(item))
        if not payload.get("paths"):
            parts.append(str(payload.get("text") or "No matches found.").strip())
        return "\n".join(parts)
    if event.name == "file_read":
        if not event.ok and not is_soft_failure:
            return str(payload.get("error") or "file read failed").strip()
        parts = [
            f"path={payload.get('path') or '-'}",
            f"char_count={int(payload.get('char_count') or 0)}",
            f"line_count={int(payload.get('line_count') or 0)}",
        ]
        if payload.get("truncated"):
            parts.append("truncated=true")
        excerpt_lines = payload.get("excerpt_lines") or []
        parts.extend(f"{item.get('line')} | {item.get('text')}" for item in excerpt_lines[:8])
        return "\n".join(parts)
    if event.name == "read_file":
        if not event.ok:
            return str(payload.get("error") or "read file failed").strip()
        parts = [
            f"file_path={payload.get('file_path') or payload.get('path') or '-'}",
            f"line_count={int(payload.get('line_count') or 0)}",
        ]
        if payload.get("offset") is not None:
            parts.append(f"offset={int(payload.get('offset') or 0)}")
        if payload.get("limit") is not None:
            parts.append(f"limit={int(payload.get('limit') or 0)}")
        text = str(payload.get("text") or "").strip()
        if text:
            parts.append(text)
        return "\n".join(parts)
    return ""


def render_web_detail(
    event: Any,
    payload: dict[str, Any],
    *,
    first_excerpt_text_fn: Callable[[dict[str, Any]], str],
) -> str:
    if event.name == "web_search":
        results = payload.get("results") or []
        return "\n".join(
            f"{item.get('rank')} | {item.get('source_domain')} | score={item.get('credibility_score')} | official={item.get('official_hint')} | {item.get('title')}"
            for item in results[:10]
        )
    if event.name == "view_image":
        if not event.ok:
            return str(payload.get("error") or "view image failed").strip()
        return render_view_image_text(payload, separator="\n")
    if event.name == "web_fetch":
        if not event.ok:
            return str(payload.get("error") or "web fetch failed").strip()
        title = str(payload.get("title") or "").strip()
        text = str(payload.get("text") or "").strip()
        final_url = str(payload.get("final_url") or payload.get("url") or "").strip()
        pieces = [item for item in [title, final_url, text[:1200]] if item]
        preview = first_excerpt_text_fn(payload)
        if preview:
            pieces.append(f"preview={preview}")
        return "\n".join(pieces)
    if event.name == "open":
        if not event.ok:
            return str(payload.get("error") or "open failed").strip()
        excerpt_lines = payload.get("excerpt_lines") or []
        links = payload.get("links") or []
        parts = [item for item in [str(payload.get("title") or "").strip(), str(payload.get("final_url") or payload.get("url") or "").strip()] if item]
        parts.extend(f"{item.get('line')} | {item.get('text')}" for item in excerpt_lines[:8])
        preview = first_excerpt_text_fn(payload)
        if preview:
            parts.append(f"preview={preview}")
        if links:
            parts.append("links:")
            parts.extend(f"{item.get('id')} | {item.get('text')} | {item.get('url')}" for item in links[:8])
        return "\n".join(parts)
    if event.name == "click":
        if not event.ok:
            return str(payload.get("error") or "click failed").strip()
        excerpt_lines = payload.get("excerpt_lines") or []
        parts = [item for item in [str(payload.get("clicked_link_text") or "").strip(), str(payload.get("final_url") or payload.get("url") or "").strip()] if item]
        parts.extend(f"{item.get('line')} | {item.get('text')}" for item in excerpt_lines[:8])
        preview = first_excerpt_text_fn(payload)
        if preview:
            parts.append(f"preview={preview}")
        return "\n".join(parts)
    if event.name == "find":
        if not event.ok:
            return str(payload.get("error") or "find failed").strip()
        matches = payload.get("matches") or []
        return "\n".join(f"{item.get('line')} | {item.get('text')}" for item in matches[:20])
    return ""
