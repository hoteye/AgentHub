from __future__ import annotations

from typing import Any

from cli.agent_cli import app_server_protocol_normalization_helpers_runtime as normalization_helpers
from cli.agent_cli import app_server_protocol_pure_helpers_runtime as pure_helpers
from cli.agent_cli.app_server_payloads import (
    prompt_attachment_for_turn_input,
    reference_turn_runtime_payload,
)
from cli.agent_cli.app_server_shell_protocol import (
    _first_text,
)


def unsupported_reference_method_error_data(
    method: str,
    *,
    replacements: dict[str, str],
    compatibility: str,
) -> dict[str, Any] | None:
    normalized = str(method or "").strip()
    replacement = str(replacements.get(normalized) or "").strip()
    if not replacement:
        return None
    return {
        "detail": normalized,
        "compatibility": compatibility,
        "replacement": replacement,
    }


def reference_sandbox_policy_payload(
    *,
    sandbox_mode: Any,
    cwd: str,
    network_access: Any,
) -> dict[str, Any]:
    normalized_mode = str(sandbox_mode or "").strip().lower()
    network_enabled = normalization_helpers.booleanish(network_access)
    if normalized_mode == "danger-full-access":
        return {"type": "dangerFullAccess"}
    if normalized_mode == "workspace-write":
        writable_roots = [cwd] if cwd else []
        return {
            "type": "workspaceWrite",
            "writableRoots": writable_roots,
            "readOnlyAccess": {"type": "fullAccess"},
            "networkAccess": network_enabled,
            "excludeTmpdirEnvVar": False,
            "excludeSlashTmp": False,
        }
    return {
        "type": "readOnly",
        "access": {"type": "fullAccess"},
        "networkAccess": network_enabled,
    }


def turn_prompt_from_input_items(
    params: dict[str, Any],
) -> tuple[str, list[Any]]:
    raw_input = params.get("input")
    if not isinstance(raw_input, list):
        raise ValueError("params.input must be an array")
    text_segments: list[str] = []
    attachments: list[Any] = []
    for raw_item in raw_input:
        if not isinstance(raw_item, dict):
            continue
        item_type = str(raw_item.get("type") or "").strip().lower()
        if item_type == "text":
            text = str(raw_item.get("text") or "").strip()
            if text:
                text_segments.append(text)
            continue
        if item_type == "image":
            url = _first_text(raw_item, "url", "imageUrl")
            if url:
                text_segments.append(url)
            continue
        if item_type in {"localimage", "local_image", "skill", "mention"}:
            path = _first_text(raw_item, "path")
            if path:
                attachments.append(prompt_attachment_for_turn_input(path))
            name = _first_text(raw_item, "name")
            if item_type == "mention" and name:
                text_segments.append(f"@{name}")
    prompt = "\n\n".join(segment for segment in text_segments if segment)
    if not prompt and not attachments:
        raise ValueError("params.input must include at least one supported item")
    return prompt, attachments


def completed_turn_payload_from_response(*, turn_id: str, response: Any) -> dict[str, Any]:
    payload = reference_turn_runtime_payload(
        turn_id=turn_id,
        status=pure_helpers.completed_turn_status(response),
    )
    error_message = pure_helpers.turn_error_message(response)
    if str(payload.get("status") or "").strip() == "failed" and error_message:
        payload["error"] = {"message": error_message}
    return payload


def failed_turn_payload(*, turn_id: str, message: str) -> dict[str, Any]:
    payload = reference_turn_runtime_payload(turn_id=turn_id, status="failed")
    payload["error"] = {"message": str(message or "turn failed")}
    return payload


def reference_turn_plan_payload(*, thread_id: str, turn_id: str, item: dict[str, Any]) -> dict[str, Any] | None:
    item_type = str(item.get("type") or "").strip().lower()
    if item_type not in {"todolist", "todo_list"}:
        return None
    plan_entries = item.get("plan")
    plan: list[dict[str, Any]] = []
    if isinstance(plan_entries, list):
        for entry in plan_entries:
            if not isinstance(entry, dict):
                continue
            step = str(entry.get("step") or "").strip()
            if not step:
                continue
            plan.append(
                {
                    "step": step,
                    "status": normalization_helpers.reference_turn_plan_step_status(entry.get("status")),
                }
            )
    if not plan:
        for entry in list(item.get("items") or []):
            if not isinstance(entry, dict):
                continue
            step = str(entry.get("text") or entry.get("step") or "").strip()
            if not step:
                continue
            plan.append(
                {
                    "step": step,
                    "status": "completed" if bool(entry.get("completed")) else "pending",
                }
            )
    if not plan:
        return None
    explanation = item.get("explanation")
    explanation_text = str(explanation or "").strip()
    payload: dict[str, Any] = {
        "threadId": thread_id,
        "turnId": turn_id,
        "plan": plan,
    }
    if explanation is not None:
        payload["explanation"] = explanation_text or None
    return payload
