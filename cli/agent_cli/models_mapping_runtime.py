from __future__ import annotations

import json
from pathlib import Path, PureWindowsPath
from typing import Any

from cli.agent_cli.media_file_types import is_supported_image_path_candidate


PROMPT_ATTACHMENT_SOURCE_FILE_REFERENCE = "file_reference"
PROMPT_ATTACHMENT_SOURCE_USER_LOCAL_IMAGE_ATTACHMENT = "user_local_image_attachment"
PROMPT_ATTACHMENT_SOURCE_TOOL_LOCAL_IMAGE_READ = "tool_local_image_read"


def _is_tool_image_source(source: str) -> bool:
    normalized = str(source or "").strip().lower()
    if not normalized:
        return False
    return normalized.startswith("tool:") or normalized in {"view_image", "tool_view_image"}


def _normalized_prompt_attachment_source(*, source: str, image_candidate_ok: bool) -> str:
    normalized_source = str(source or PROMPT_ATTACHMENT_SOURCE_FILE_REFERENCE).strip()
    if not image_candidate_ok:
        return normalized_source or PROMPT_ATTACHMENT_SOURCE_FILE_REFERENCE
    if _is_tool_image_source(normalized_source):
        return PROMPT_ATTACHMENT_SOURCE_TOOL_LOCAL_IMAGE_READ
    return PROMPT_ATTACHMENT_SOURCE_USER_LOCAL_IMAGE_ATTACHMENT


def prompt_attachment_source_kind(source: str) -> str:
    normalized = str(source or "").strip()
    if normalized == PROMPT_ATTACHMENT_SOURCE_USER_LOCAL_IMAGE_ATTACHMENT:
        return "user_local_image_attachment"
    if normalized == PROMPT_ATTACHMENT_SOURCE_TOOL_LOCAL_IMAGE_READ:
        return "tool_local_image_read"
    if _is_tool_image_source(normalized):
        return "tool_local_image_read"
    return "local_file_attachment"


def tool_event_from_dict_data(payload: dict[str, Any]) -> dict[str, Any]:
    item = dict(payload or {})
    return {
        "name": str(item.get("name") or ""),
        "ok": bool(item.get("ok")),
        "summary": str(item.get("summary") or ""),
        "payload": dict(item.get("payload") or {}),
    }


def tool_event_to_dict_data(*, name: str, ok: bool, summary: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "ok": ok,
        "summary": summary,
        "payload": dict(payload or {}),
    }


def activity_event_from_dict_data(payload: dict[str, Any]) -> dict[str, Any]:
    item = dict(payload or {})
    raw_params = item.get("params")
    return {
        "title": str(item.get("title") or ""),
        "status": str(item.get("status") or "info"),
        "detail": str(item.get("detail") or ""),
        "kind": str(item.get("kind") or "activity"),
        "code": str(item.get("code") or ""),
        "params": dict(raw_params) if isinstance(raw_params, dict) else {},
    }


def activity_event_to_dict_data(
    *,
    title: str,
    status: str,
    detail: str,
    kind: str,
    code: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    return {
        "title": title,
        "status": status,
        "detail": detail,
        "kind": kind,
        "code": code,
        "params": dict(params or {}),
    }


def shell_lifecycle_envelope_from_dict_data(payload: dict[str, Any]) -> dict[str, str]:
    item = dict(payload or {})
    return {
        "phase": str(item.get("phase") or ""),
        "kind": str(item.get("kind") or ""),
        "call_id": str(item.get("call_id") or item.get("callId") or ""),
        "session_id": str(item.get("session_id") or item.get("sessionId") or ""),
        "process_id": str(item.get("process_id") or item.get("processId") or ""),
        "source": str(item.get("source") or "shell_session_manager"),
        "stream": str(item.get("stream") or ""),
        "status": str(item.get("status") or ""),
    }


def shell_lifecycle_envelope_to_dict_data(
    *,
    phase: str,
    kind: str,
    call_id: str,
    session_id: str,
    process_id: str,
    source: str,
    stream: str,
    status: str,
) -> dict[str, str]:
    payload = {
        "phase": phase,
        "kind": kind,
        "call_id": call_id,
        "session_id": session_id,
        "process_id": process_id,
        "source": source,
    }
    if stream:
        payload["stream"] = stream
    if status:
        payload["status"] = status
    return payload


def prompt_attachment_from_path_data(
    path_text: str,
    *,
    source: str = PROMPT_ATTACHMENT_SOURCE_FILE_REFERENCE,
) -> dict[str, Any]:
    raw_path = str(path_text or "").strip()
    path = Path(raw_path)
    display_path = PureWindowsPath(raw_path) if "\\" in raw_path else path
    suffix = display_path.suffix.lower()
    try:
        exists = path.exists()
    except OSError:
        exists = False
    try:
        is_dir = path.is_dir()
    except OSError:
        is_dir = False
    normalized_source = _normalized_prompt_attachment_source(
        source=str(source or PROMPT_ATTACHMENT_SOURCE_FILE_REFERENCE),
        image_candidate_ok=exists and not is_dir and is_supported_image_path_candidate(raw_path),
    )
    return {
        "path": raw_path,
        "name": display_path.name or raw_path,
        "extension": suffix[1:] if suffix.startswith(".") else suffix,
        "exists": exists,
        "is_dir": is_dir,
        "source": normalized_source,
    }


def prompt_attachment_from_dict_data(payload: dict[str, Any]) -> dict[str, Any]:
    item = dict(payload or {})
    return {
        "path": str(item.get("path") or ""),
        "name": str(item.get("name") or ""),
        "extension": str(item.get("extension") or ""),
        "exists": bool(item.get("exists")),
        "is_dir": bool(item.get("is_dir")),
        "source": str(item.get("source") or PROMPT_ATTACHMENT_SOURCE_FILE_REFERENCE),
    }


def prompt_attachment_to_dict_data(
    *,
    path: str,
    name: str,
    extension: str,
    exists: bool,
    is_dir: bool,
    source: str,
) -> dict[str, Any]:
    return {
        "path": path,
        "name": name,
        "extension": extension,
        "exists": exists,
        "is_dir": is_dir,
        "source": source,
    }


def reference_context_item_from_attachment_data(attachment: Any) -> dict[str, Any]:
    label = attachment.name or attachment.path
    return {
        "item_type": "attachment",
        "source": str(attachment.source or "file_reference"),
        "label": label,
        "path": str(attachment.path or ""),
        "description": f"attachment:{attachment.extension}" if attachment.extension else "attachment",
        "metadata": {
            "name": attachment.name,
            "extension": attachment.extension,
            "exists": bool(attachment.exists),
            "is_dir": bool(attachment.is_dir),
        },
    }


def reference_context_item_from_dict_data(payload: dict[str, Any]) -> dict[str, Any]:
    item = dict(payload or {})
    return {
        "item_type": str(item.get("item_type") or item.get("type") or "reference"),
        "source": str(item.get("source") or ""),
        "label": str(item.get("label") or ""),
        "path": str(item.get("path") or ""),
        "uri": str(item.get("uri") or ""),
        "ref": str(item.get("ref") or ""),
        "description": str(item.get("description") or ""),
        "metadata": dict(item.get("metadata") or {}),
    }


def reference_context_item_to_dict_data(
    *,
    item_type: str,
    source: str,
    label: str,
    path: str,
    uri: str,
    ref: str,
    description: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "item_type": item_type,
        "source": source,
        "label": label,
        "path": path,
        "uri": uri,
        "ref": ref,
        "description": description,
        "metadata": dict(metadata or {}),
    }


def function_call_output_content_item_from_dict_data(payload: dict[str, Any]) -> dict[str, Any]:
    item = dict(payload or {})
    return {
        "item_type": str(item.get("type") or item.get("item_type") or "input_text"),
        "text": str(item.get("text") or ""),
        "image_url": str(item.get("image_url") or item.get("imageUrl") or ""),
        "detail": str(item.get("detail") or "") or None,
    }


def function_call_output_content_item_to_dict_data(
    *,
    item_type: str,
    text: str,
    image_url: str,
    detail: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": item_type}
    if item_type == "input_image":
        payload["image_url"] = image_url
        if detail:
            payload["detail"] = detail
        return payload
    payload["text"] = text
    return payload


def _mapping_from_output_value(output: Any) -> dict[str, Any] | None:
    if isinstance(output, dict):
        return dict(output)
    if not isinstance(output, str):
        return None
    text = output.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return dict(parsed) if isinstance(parsed, dict) else None


def view_document_payload_from_output(output: Any) -> dict[str, Any] | None:
    payload = _mapping_from_output_value(output)
    if payload is None:
        return None
    capability_baseline = str(payload.get("capability_baseline") or "").strip().lower()
    document_class = str(payload.get("document_class") or "").strip().lower()
    extraction_state = str(payload.get("extraction_state") or "").strip().lower()
    if capability_baseline != "extraction_only":
        return None
    if not document_class or not extraction_state:
        return None
    if "text_slice" not in payload and "structured_content" not in payload:
        return None
    return payload


def view_document_projection_subject(payload: dict[str, Any]) -> str:
    subject = str(payload.get("path") or payload.get("requested_path") or "").strip()
    return subject


def view_document_output_projection(output: Any) -> dict[str, Any] | None:
    payload = view_document_payload_from_output(output)
    if payload is None:
        return None
    projection: dict[str, Any] = {
        "recognized": True,
        "model_visible": False,
        "projection_mode": "",
        "projection_state": "",
        "subject": view_document_projection_subject(payload),
        "output": payload,
        "payload": payload,
    }
    if not bool(payload.get("ok")):
        return projection

    extraction_state = str(payload.get("extraction_state") or "").strip().lower()
    text_slice = payload.get("text_slice")
    if extraction_state == "text_slice_ready" and isinstance(text_slice, dict):
        projection["model_visible"] = True
        projection["projection_mode"] = "tool_result_content_block"
        projection["projection_state"] = "document_projected_text"
        projection["output"] = [{"type": "input_text", "text": str(text_slice.get("text") or "")}]
        return projection

    structured_content = payload.get("structured_content")
    if extraction_state == "structured_content_ready" and isinstance(structured_content, dict):
        format_name = str(structured_content.get("format") or "").strip().lower()
        data = structured_content.get("data")
        if format_name == "json" and data is not None:
            projection["model_visible"] = True
            projection["projection_mode"] = "tool_result_content_block"
            projection["projection_state"] = "document_projected_structured"
            projection["output"] = [{"type": "input_text", "text": json.dumps(data, ensure_ascii=False)}]
            return projection
    return projection
