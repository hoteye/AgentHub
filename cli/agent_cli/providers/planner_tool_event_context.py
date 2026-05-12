from __future__ import annotations

from typing import Any, Dict, List, Sequence

from cli.agent_cli.models import ToolEvent, tool_event_is_soft_failure


def _trim_text(value: Any, *, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _excerpt_lines(payload: Dict[str, Any], *, limit: int = 8, line_text_limit: int = 240) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for item in list(payload.get("excerpt_lines") or [])[:limit]:
        if not isinstance(item, dict):
            continue
        text = _trim_text(item.get("text"), limit=line_text_limit)
        if not text:
            continue
        results.append(
            {
                "line": int(item.get("line") or 0),
                "text": text,
            }
        )
    return results


def _trim_json_like(value: Any, *, text_limit: int = 240, list_limit: int = 8, dict_limit: int = 12) -> Any:
    if isinstance(value, str):
        return _trim_text(value, limit=text_limit)
    if isinstance(value, list):
        return [
            _trim_json_like(item, text_limit=text_limit, list_limit=list_limit, dict_limit=dict_limit)
            for item in value[:list_limit]
        ]
    if isinstance(value, dict):
        trimmed: Dict[str, Any] = {}
        for key in list(value.keys())[:dict_limit]:
            trimmed[str(key)] = _trim_json_like(
                value.get(key),
                text_limit=text_limit,
                list_limit=list_limit,
                dict_limit=dict_limit,
            )
        return trimmed
    return value


def generic_tool_event_context_blocks(events: Sequence[ToolEvent]) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    for event in list(events or [])[-8:]:
        payload = event.payload or {}
        soft_failure = tool_event_is_soft_failure(event)
        block: Dict[str, Any] = {
            "name": event.name,
            "ok": bool(event.ok),
            "result_success": False if soft_failure else bool(event.ok),
            "summary": str(event.summary or "").strip(),
        }
        if not event.ok and not soft_failure:
            error = _trim_text(payload.get("error") or event.summary, limit=600)
            if error:
                block["error"] = error
            blocks.append(block)
            continue

        if event.name == "web_search":
            block["query"] = str(payload.get("query") or "").strip()
            block["results"] = [
                {
                    "rank": int(item.get("rank") or 0),
                    "title": _trim_text(item.get("title"), limit=180),
                    "url": str(item.get("url") or "").strip(),
                    "snippet": _trim_text(item.get("snippet"), limit=220),
                    "source_domain": str(item.get("source_domain") or "").strip(),
                }
                for item in list(payload.get("results") or [])[:5]
                if isinstance(item, dict)
            ]
            blocks.append(block)
            continue

        if event.name == "web_fetch":
            block.update(
                {
                    "url": str(payload.get("final_url") or payload.get("url") or "").strip(),
                    "title": str(payload.get("title") or "").strip(),
                    "source_domain": str(payload.get("source_domain") or "").strip(),
                    "text": _trim_text(payload.get("text"), limit=4000),
                    "line_count": int(payload.get("line_count") or 0),
                    "link_count": int(payload.get("link_count") or 0),
                    "source_scope": str(payload.get("source_scope") or "").strip(),
                }
            )
            blocks.append(block)
            continue

        if event.name == "grep_files":
            block.update(
                {
                    "pattern": str(payload.get("pattern") or "").strip(),
                    "path": str(payload.get("path") or "").strip(),
                    "include": str(payload.get("include") or "").strip(),
                    "count": int(payload.get("count") or 0),
                    "paths": [str(item).strip() for item in list(payload.get("paths") or [])[:20] if str(item).strip()],
                    "text": _trim_text(payload.get("text"), limit=1200),
                }
            )
            blocks.append(block)
            continue

        if event.name == "read_file":
            block.update(
                {
                    "path": str(payload.get("file_path") or payload.get("path") or "").strip(),
                    "text": _trim_text(payload.get("text"), limit=4000),
                    "line_count": int(payload.get("line_count") or 0),
                    "returned_line_count": int(payload.get("returned_line_count") or 0),
                    "offset": int(payload.get("offset") or 0),
                    "limit": int(payload.get("limit") or 0),
                    "mode": str(payload.get("mode") or "").strip(),
                    "truncated": bool(payload.get("truncated")),
                    "excerpt_lines": _excerpt_lines(payload),
                }
            )
            blocks.append(block)
            continue

        if event.name == "list_dir":
            block.update(
                {
                    "path": str(payload.get("dir_path") or payload.get("path") or "").strip(),
                    "offset": int(payload.get("offset") or 0),
                    "limit": int(payload.get("limit") or 0),
                    "depth": int(payload.get("depth") or 0),
                    "count": int(payload.get("count") or 0),
                    "text": _trim_text(payload.get("text"), limit=1200),
                    "entries": [
                        {
                            "index": int(item.get("index") or 0),
                            "kind": str(item.get("kind") or "").strip(),
                            "path": str(item.get("path") or "").strip(),
                        }
                        for item in list(payload.get("entries") or [])[:20]
                        if isinstance(item, dict)
                    ],
                }
            )
            blocks.append(block)
            continue

        if event.name in {"open", "click"}:
            block.update(
                {
                    "ref_id": str(payload.get("ref_id") or "").strip(),
                    "url": str(payload.get("final_url") or payload.get("url") or "").strip(),
                    "title": str(payload.get("title") or "").strip(),
                    "source_domain": str(payload.get("source_domain") or "").strip(),
                    "source_scope": str(payload.get("source_scope") or "").strip(),
                    "excerpt_lines": _excerpt_lines(payload),
                    "links": [
                        {
                            "id": int(item.get("id") or 0),
                            "text": _trim_text(item.get("text"), limit=120),
                            "url": str(item.get("url") or "").strip(),
                        }
                        for item in list(payload.get("links") or [])[:8]
                        if isinstance(item, dict)
                    ],
                }
            )
            clicked_link_text = str(payload.get("clicked_link_text") or "").strip()
            if clicked_link_text:
                block["clicked_link_text"] = clicked_link_text
            blocks.append(block)
            continue

        if event.name == "find":
            block.update(
                {
                    "ref_id": str(payload.get("ref_id") or "").strip(),
                    "pattern": str(payload.get("pattern") or "").strip(),
                    "matches": [
                        {
                            "line": int(item.get("line") or 0),
                            "text": _trim_text(item.get("text"), limit=220),
                        }
                        for item in list(payload.get("matches") or [])[:10]
                        if isinstance(item, dict)
                    ],
                }
            )
            blocks.append(block)
            continue

        if event.name == "file_read":
            block.update(
                {
                    "path": str(payload.get("path") or "").strip(),
                    "text": _trim_text(payload.get("text"), limit=4000),
                    "line_count": int(payload.get("line_count") or 0),
                    "truncated": bool(payload.get("truncated")),
                }
            )
            blocks.append(block)
            continue

        if event.name == "file_search":
            block.update(
                {
                    "query": str(payload.get("query") or "").strip(),
                    "path": str(payload.get("path") or "").strip(),
                    "matches": [
                        {
                            "path": str(item.get("path") or "").strip(),
                            "line": int(item.get("line") or 0),
                            "text": _trim_text(item.get("text"), limit=220),
                        }
                        for item in list(payload.get("matches") or [])[:12]
                        if isinstance(item, dict)
                    ],
                }
            )
            blocks.append(block)
            continue

        if event.name == "file_list":
            block.update(
                {
                    "path": str(payload.get("path") or "").strip(),
                    "files": [
                        {
                            "path": str(item.get("path") or "").strip(),
                            "size": int(item.get("size") or 0),
                        }
                        for item in list(payload.get("files") or [])[:20]
                        if isinstance(item, dict)
                    ],
                }
            )
            blocks.append(block)
            continue

        if event.name == "shell":
            stdout = _trim_text(payload.get("stdout"), limit=1600)
            stderr = _trim_text(payload.get("stderr"), limit=1000)
            command = str(payload.get("command") or "").strip()
            if command:
                block["command"] = command
            if stdout:
                block["stdout"] = stdout
            if stderr:
                block["stderr"] = stderr
            blocks.append(block)
            continue

        for key in ("summary_text", "draft_text", "draft_reply", "reason", "stdout", "stderr"):
            value = _trim_text(payload.get(key), limit=800)
            if value:
                block[key] = value
        blocks.append(block)
    return blocks


def executed_item_event_context_blocks(events: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    for raw_event in list(events or [])[-24:]:
        if not isinstance(raw_event, dict):
            continue
        event_type = str(raw_event.get("type") or "").strip()
        if not event_type:
            continue
        block: Dict[str, Any] = {"event_type": event_type}
        item = raw_event.get("item")
        if not isinstance(item, dict):
            blocks.append(block)
            continue
        item_type = str(item.get("type") or "").strip()
        if item_type:
            block["item_type"] = item_type
        item_id = str(item.get("id") or "").strip()
        if item_id:
            block["id"] = item_id
        status = str(item.get("status") or "").strip()
        if status:
            block["status"] = status
        for key in ("tool", "server", "command", "call_id", "ref_id"):
            value = str(item.get(key) or "").strip()
            if value:
                block[key] = value
        if item.get("exit_code") is not None:
            try:
                block["exit_code"] = int(item.get("exit_code"))
            except (TypeError, ValueError):
                pass
        if item.get("arguments") is not None:
            block["arguments"] = _trim_json_like(item.get("arguments"))
        text_value = _trim_text(item.get("text"), limit=400)
        if text_value:
            block["text"] = text_value
        aggregated_output = _trim_text(item.get("aggregated_output"), limit=600)
        if aggregated_output:
            block["aggregated_output"] = aggregated_output
        result = item.get("result")
        if isinstance(result, dict):
            result_block: Dict[str, Any] = {}
            content = result.get("content")
            if isinstance(content, list):
                text_parts: List[str] = []
                for entry in content[:8]:
                    if not isinstance(entry, dict):
                        continue
                    if str(entry.get("type") or "").strip() != "text":
                        continue
                    entry_text = _trim_text(entry.get("text"), limit=240)
                    if entry_text:
                        text_parts.append(entry_text)
                if text_parts:
                    result_block["content_text"] = "\n".join(text_parts)
            if result.get("structured_content") is not None:
                result_block["structured_content"] = _trim_json_like(result.get("structured_content"))
            if result_block:
                block["result"] = result_block
        error = item.get("error")
        if isinstance(error, dict):
            message = _trim_text(error.get("message"), limit=400)
            if message:
                block["error"] = {"message": message}
        blocks.append(block)
    return blocks
