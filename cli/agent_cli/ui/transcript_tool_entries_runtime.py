from __future__ import annotations

import json
from pathlib import Path

from cli.agent_cli import models_mapping_runtime as models_mapping_runtime_service
from cli.agent_cli.command_execution_summary_runtime import command_display_text_from_mapping
from cli.agent_cli.image_transport_runtime import (
    IMAGE_TRANSPORT_FAMILY_TO_STATE,
    image_transport_family_from_output_item,
)
from cli.agent_cli.media_content_runtime import normalized_image_detail
from cli.agent_cli.models import ToolEvent
from cli.agent_cli.ui.text_utils import short


def is_exploration_mcp_tool(item: dict[str, object]) -> bool:
    return str(item.get("tool") or "").strip() in {
        "list_dir",
        "grep_files",
        "read_file",
        "file_list",
        "file_search",
        "file_read",
    }


def format_mcp_invocation_text(item: dict[str, object]) -> str:
    server = str(item.get("server") or "local").strip() or "local"
    tool = str(item.get("tool") or "").strip() or "tool"
    arguments = item.get("arguments")
    if arguments in (None, ""):
        args_text = ""
    else:
        try:
            args_text = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
        except TypeError:
            args_text = str(arguments)
    return f"{server}.{tool}({args_text})"


def turn_tool_item_payload(item: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {}
    arguments = item.get("arguments")
    if isinstance(arguments, dict):
        payload.update(arguments)
    result = item.get("result")
    if isinstance(result, dict):
        structured_content = result.get("structured_content")
        if isinstance(structured_content, dict):
            payload.update(structured_content)
            structured_payload = structured_content.get("structured_payload")
            if isinstance(structured_payload, dict):
                payload.update(structured_payload)
    return payload


def image_artifact_details(item: dict[str, object]) -> tuple[str, int]:
    payload = turn_tool_item_payload(item)
    raw_artifacts = payload.get("image_artifacts")
    if not isinstance(raw_artifacts, list):
        return "", 0
    artifacts = [entry for entry in raw_artifacts if isinstance(entry, dict)]
    if not artifacts:
        return "", 0
    first_artifact = artifacts[0]
    artifact_path = str(
        first_artifact.get("path")
        or payload.get("path")
        or payload.get("requested_path")
        or ""
    ).strip()
    display_name = Path(artifact_path).name or artifact_path
    return display_name, len(artifacts)


def input_image_output_details(item: dict[str, object]) -> tuple[str, int]:
    display_name, image_count, _, _ = input_image_output_transport_details(item)
    return display_name, image_count


def input_image_output_transport_details(item: dict[str, object]) -> tuple[str, int, str, str]:
    images = _input_images_from_output(item.get("output"))
    if not images:
        return "", 0, "", ""
    transport_family = _image_transport_family(item, images)
    state = IMAGE_TRANSPORT_FAMILY_TO_STATE.get(transport_family, "image_injected")
    subject = str(item.get("image_transport_subject") or "").strip()
    if subject:
        if subject.lower().startswith("attachment:"):
            subject = subject.split(":", 1)[1].strip()
        display_name = Path(subject).name or subject
        return display_name, len(images), transport_family, state
    first_detail = str(images[0].get("detail") or "").strip()
    display_name = ""
    if first_detail and not normalized_image_detail(first_detail):
        display_name = Path(first_detail).name or first_detail
    return display_name, len(images), transport_family, state


def view_document_extraction_details(item: dict[str, object]) -> tuple[str, str, str]:
    if str(item.get("tool") or "").strip() != "view_document":
        return "", "", ""
    result = item.get("result")
    if not isinstance(result, dict):
        return "", "", ""
    payload = models_mapping_runtime_service.view_document_payload_from_output(result.get("structured_content"))
    if payload is None or not bool(payload.get("ok")):
        return "", "", ""
    subject = models_mapping_runtime_service.view_document_projection_subject(payload)
    display_name = Path(subject).name or subject
    extraction_state = str(payload.get("extraction_state") or "").strip().lower()
    if extraction_state == "text_slice_ready":
        return display_name, "text_slice", "document_extracted_text"
    if extraction_state == "structured_content_ready":
        return display_name, "structured_content", "document_extracted_structured"
    return display_name, "", ""


def document_output_projection_details(item: dict[str, object]) -> tuple[str, str, str]:
    projection_mode = str(item.get("document_projection_mode") or "").strip()
    projection_state = str(item.get("document_projection_state") or "").strip()
    projection_subject = str(item.get("document_projection_subject") or "").strip()
    if not (projection_mode and projection_state):
        projection = models_mapping_runtime_service.view_document_output_projection(item.get("output"))
        if projection is None or not bool(projection.get("model_visible")):
            return "", "", ""
        projection_mode = str(projection.get("projection_mode") or "").strip()
        projection_state = str(projection.get("projection_state") or "").strip()
        projection_subject = str(projection.get("subject") or "").strip()
    display_name = Path(projection_subject).name or projection_subject
    return display_name, projection_mode, projection_state


def _input_images_from_output(output: object) -> list[dict[str, object]]:
    if isinstance(output, str):
        try:
            output = json.loads(output)
        except json.JSONDecodeError:
            output = []
    if not isinstance(output, list):
        return []
    images = [
        entry
        for entry in output
        if isinstance(entry, dict) and str(entry.get("type") or "").strip() == "input_image"
    ]
    return [dict(entry) for entry in images]


def _image_transport_family(item: dict[str, object], images: list[dict[str, object]]) -> str:
    return image_transport_family_from_output_item(item, images)


def is_local_exec_like_mcp_tool(item: dict[str, object]) -> bool:
    server = str(item.get("server") or "local").strip() or "local"
    tool = str(item.get("tool") or "").strip().lower()
    return server == "local" and tool in {"exec_command", "shell"}


def is_shell_approval_payload(payload: dict[str, object]) -> bool:
    approval_id = str(payload.get("approval_id") or "").strip()
    if not approval_id:
        return False
    status = str(payload.get("status") or "").strip().lower()
    summary = str(payload.get("summary") or "").strip().lower()
    reason = str(payload.get("reason") or "").strip().lower()
    return status in {"pending", "approval_required"} or "approval" in summary or "approval" in reason


def turn_event_result_text(result: object) -> str:
    if not isinstance(result, dict):
        return ""
    content = result.get("content")
    if not isinstance(content, list):
        return ""
    text_segments = [
        str(entry.get("text") or "").strip()
        for entry in content
        if isinstance(entry, dict) and str(entry.get("type") or "").strip() == "text"
    ]
    return "\n".join(segment for segment in text_segments if segment)


def turn_event_running_tool_detail(item: dict[str, object]) -> str:
    arguments = item.get("arguments")
    if not isinstance(arguments, dict):
        return ""
    parts: list[str] = []
    for key in ("path", "file_path", "dir_path", "query", "pattern", "ref_id", "url"):
        value = arguments.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        parts.append(f"{key}={text}")
    return "\n".join(parts[:3])


def turn_event_command_text(item: dict[str, object]) -> str:
    command_text = command_display_text_from_mapping(item, single_line=True) or str(item.get("command") or "").strip()
    if not command_text:
        return "command"
    return short(command_text, 120)


def turn_event_command_detail(item: dict[str, object]) -> str:
    aggregated_output = str(item.get("aggregated_output") or "").strip()
    exit_code = item.get("exit_code")
    status_text = str(item.get("status") or "").strip().lower()
    if status_text == "completed" and exit_code in {0, "0", None}:
        return ""
    if aggregated_output:
        lines = [line.strip() for line in aggregated_output.splitlines() if line.strip()]
        if lines:
            return lines[-1]
    if exit_code not in {None, ""}:
        return f"exit_code={exit_code}"
    return ""


def _web_search_error_text(payload: dict[str, object]) -> str:
    for key in ("display_message", "error", "issue"):
        text = str(payload.get(key) or "").strip()
        if text:
            return text
    errors = payload.get("errors")
    if isinstance(errors, list):
        for entry in errors:
            text = str(entry or "").strip()
            if text:
                return text
    fallback_reason = str(payload.get("fallback_reason") or "").strip()
    error_code = str(payload.get("error_code") or "").strip()
    if fallback_reason and error_code:
        return f"{error_code} | fallback_reason={fallback_reason}"
    if error_code:
        return error_code
    if fallback_reason:
        return f"fallback_reason={fallback_reason}"
    return ""


def tool_event_from_turn_tool_item(item: dict[str, object]) -> ToolEvent | None:
    tool_name = str(item.get("tool") or "").strip()
    if not tool_name:
        return None
    status_text = str(item.get("status") or "").strip().lower()
    payload = turn_tool_item_payload(item)
    arguments = item.get("arguments")
    if isinstance(arguments, dict):
        payload["arguments"] = dict(arguments)
    result = item.get("result")
    if isinstance(result, dict):
        result_text = turn_event_result_text(result)
        if result_text and not any(
            str(payload.get(key) or "").strip()
            for key in ("text", "output_text", "stdout", "summary_text")
        ):
            payload["text"] = result_text
    else:
        result_text = ""
    error = item.get("error")
    error_message = ""
    if isinstance(error, dict):
        error_message = str(error.get("message") or "").strip()
        if error_message:
            payload["error"] = error_message
    if tool_name == "web_search" and not error_message:
        error_message = _web_search_error_text(payload)
        if error_message and not str(payload.get("error") or "").strip():
            payload["error"] = error_message
    if is_local_exec_like_mcp_tool(item) and is_shell_approval_payload(payload):
        tool_name = "shell_approval_requested"
    ok = status_text == "completed"
    if tool_name == "web_search":
        explicit_ok = payload.get("ok")
        if isinstance(explicit_ok, bool):
            ok = ok and explicit_ok
        elif error_message:
            ok = False
    summary = result_text or error_message or tool_name
    return ToolEvent(
        name=tool_name,
        ok=ok,
        summary=summary,
        payload=payload,
    )
