from __future__ import annotations

from typing import Any, Callable


def command_policy_projection_from_tool_events(
    tool_events: Any,
    *,
    normalized_optional_text_fn: Callable[[Any], str],
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    denied_count = 0
    rewrite_count = 0
    checked_count = 0
    for event in list(tool_events or []):
        payload = getattr(event, "payload", None)
        if not isinstance(payload, dict):
            continue
        command = normalized_optional_text_fn(payload.get("command"))
        effective_command = normalized_optional_text_fn(payload.get("effective_command"))
        status = normalized_optional_text_fn(payload.get("status"))
        policy_mapping = payload.get("command_policy")
        policy = dict(policy_mapping) if isinstance(policy_mapping, dict) else {}
        policy_allowed = policy.get("allowed")
        denied = status.lower() == "policy_denied" or policy_allowed is False
        rewritten = bool(command and effective_command and effective_command != command) and not denied
        checked = bool(command or effective_command) and not denied and not rewritten
        if denied:
            denied_count += 1
        elif rewritten:
            rewrite_count += 1
        elif checked:
            checked_count += 1
        if not (command or effective_command or status or denied or rewritten):
            continue
        error_code = normalized_optional_text_fn(payload.get("error_code") or policy.get("error_code"))
        dedupe_key = (command, effective_command, status, error_code)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        entries.append(
            {
                "command": command,
                "effective_command": effective_command,
                "status": status,
                "policy_denied": denied,
                "policy_rewrite": rewritten,
                "error_code": error_code,
                "command_policy": policy,
            }
        )
    if not entries:
        return {}
    return {
        "command_policies": entries,
        "command_policies_count": len(entries),
        "command_policy_denied_count": denied_count,
        "command_policy_rewrite_count": rewrite_count,
        "command_policy_checked_count": checked_count,
        "command_policy_surface": f"denied:{denied_count},rewrite:{rewrite_count},checked:{checked_count}",
    }


def apply_optional_payload_fields(
    payload: dict[str, Any],
    *,
    active_input: dict[str, Any] | None,
    assistant_text: str,
    error: str,
) -> dict[str, Any]:
    if active_input is not None:
        payload["active_input_text"] = str(active_input.get("message") or "")
    if assistant_text:
        payload["text"] = assistant_text
    if error:
        payload["error"] = error
    return payload


def build_delegated_workflow_payload(
    payload: dict[str, Any],
    *,
    progress_payload: dict[str, Any],
    steps_limit: int,
    checkpoints_limit: int,
) -> dict[str, Any]:
    steps = [dict(item) for item in list(progress_payload.get("steps") or []) if isinstance(item, dict)]
    checkpoints = [dict(item) for item in list(progress_payload.get("checkpoints") or []) if isinstance(item, dict)]
    bounded_steps = max(1, int(steps_limit))
    bounded_checkpoints = max(1, int(checkpoints_limit))
    payload["steps"] = steps[-bounded_steps:]
    payload["checkpoints"] = checkpoints[-bounded_checkpoints:]
    payload["steps_truncated"] = len(steps) > bounded_steps
    payload["checkpoints_truncated"] = len(checkpoints) > bounded_checkpoints
    return payload
