from __future__ import annotations

import json
from typing import Any

from cli.agent_cli.ui.transcript_history import TranscriptEntry


def transcript_entries_to_export_records(
    entries: list[TranscriptEntry],
    *,
    include_reasoning: bool = False,
    include_tool_details: bool = True,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, entry in enumerate(list(entries or [])):
        if entry.kind == "blank":
            continue
        if entry.kind == "reasoning" and not include_reasoning:
            continue
        record = _entry_base_record(entry, index=index)
        payload = entry.structured if isinstance(entry.structured, dict) else None
        if payload is not None:
            record["structured"] = _export_payload(
                payload, include_tool_details=include_tool_details
            )
            text = _payload_text(payload)
            if text:
                record["text"] = text
        else:
            record["lines"] = [str(line) for line in list(entry.lines or [])]
            text = "\n".join(str(line) for line in list(entry.lines or [])).strip()
            if text:
                record["text"] = text
        if entry.expanded_lines:
            record["expanded_lines"] = [str(line) for line in entry.expanded_lines]
        if entry.child_entry_ids:
            record["child_entry_ids"] = [str(value) for value in entry.child_entry_ids]
        records.append(record)
    return records


def transcript_entries_to_json(
    entries: list[TranscriptEntry],
    *,
    include_reasoning: bool = False,
    include_tool_details: bool = True,
) -> str:
    records = transcript_entries_to_export_records(
        entries,
        include_reasoning=include_reasoning,
        include_tool_details=include_tool_details,
    )
    return json.dumps(records, ensure_ascii=False, indent=2)


def transcript_entries_to_markdown(
    entries: list[TranscriptEntry],
    *,
    include_reasoning: bool = False,
    include_tool_details: bool = True,
) -> str:
    records = transcript_entries_to_export_records(
        entries,
        include_reasoning=include_reasoning,
        include_tool_details=include_tool_details,
    )
    sections: list[str] = []
    for record in records:
        title = _markdown_record_title(record)
        body_lines = _markdown_record_body(record, include_tool_details=include_tool_details)
        sections.append("\n".join([f"## {title}", *body_lines]).rstrip())
    return "\n\n".join(section for section in sections if section).strip()


def _entry_base_record(entry: TranscriptEntry, *, index: int) -> dict[str, Any]:
    record: dict[str, Any] = {
        "index": int(index),
        "kind": str(entry.kind or ""),
        "layer": str(entry.layer or ""),
        "status": str(entry.status or ""),
        "render_mode": str(entry.render_mode or ""),
        "expanded": bool(entry.expanded),
    }
    for key, value in {
        "entry_id": entry.entry_id,
        "activity_key": entry.activity_key,
        "group_key": entry.group_key,
    }.items():
        text = str(value or "").strip()
        if text:
            record[key] = text
    if entry.created_at:
        record["created_at"] = float(entry.created_at)
    return record


def _export_payload(payload: dict[str, Any], *, include_tool_details: bool) -> dict[str, Any]:
    exported = dict(payload)
    if include_tool_details:
        return exported
    for key in ("input", "output", "metadata", "artifacts"):
        exported.pop(key, None)
    return exported


def _payload_text(payload: dict[str, Any]) -> str:
    for key in ("text", "output", "summary", "title"):
        value = payload.get(key)
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _markdown_record_title(record: dict[str, Any]) -> str:
    structured = record.get("structured")
    if isinstance(structured, dict):
        payload_type = str(structured.get("type") or "").strip()
        name = str(structured.get("name") or "").strip()
        state = str(structured.get("state") or record.get("status") or "").strip()
        parts = [part for part in (payload_type, name, state) if part]
        if parts:
            return " / ".join(parts)
    kind = str(record.get("kind") or "entry").strip() or "entry"
    status = str(record.get("status") or "").strip()
    return f"{kind} / {status}" if status else kind


def _markdown_record_body(
    record: dict[str, Any],
    *,
    include_tool_details: bool,
) -> list[str]:
    structured = record.get("structured")
    if isinstance(structured, dict):
        return _markdown_structured_body(structured, include_tool_details=include_tool_details)
    lines = [str(line) for line in list(record.get("lines") or []) if str(line).strip()]
    return lines or ["(empty)"]


def _markdown_structured_body(
    payload: dict[str, Any],
    *,
    include_tool_details: bool,
) -> list[str]:
    lines: list[str] = []
    text = str(payload.get("text") or "").strip()
    if text:
        lines.extend(text.splitlines())
    title = str(payload.get("title") or "").strip()
    if title and not lines:
        lines.append(title)
    if not include_tool_details:
        return lines or ["(details hidden)"]
    for label, value in (
        ("input", payload.get("input")),
        ("output", payload.get("output")),
        ("metadata", payload.get("metadata")),
        ("error", payload.get("error")),
        ("artifacts", payload.get("artifacts")),
    ):
        if value is None or value == "" or value == [] or value == {}:
            continue
        lines.append(f"- {label}: {_markdown_value(value)}")
    return lines or ["(empty)"]


def _markdown_value(value: Any) -> str:
    if isinstance(value, dict | list | tuple):
        return "`" + json.dumps(value, ensure_ascii=False, sort_keys=True) + "`"
    text = str(value)
    if "\n" in text:
        return "\n\n```text\n" + text.rstrip() + "\n```"
    return text
