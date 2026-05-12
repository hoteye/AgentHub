from __future__ import annotations

import base64
import json
from typing import Any

from cli.agent_cli.command_execution_summary_runtime import (
    command_activity_params,
    command_display_text_from_mapping,
)
from cli.agent_cli.models import ActivityEvent
from cli.agent_cli import runtime_policy as runtime_policy_service


def shell_lifecycle_dict(
    payload: dict[str, Any] | None,
    *,
    infer_shell_phase_fn: Any,
    lifecycle_kind_by_phase: dict[str, str],
) -> dict[str, Any]:
    lifecycle = dict((payload or {}).get("lifecycle") or {})
    phase = infer_shell_phase_fn(payload, lifecycle=lifecycle)
    if phase:
        lifecycle["phase"] = phase
    call_id = str((payload or {}).get("call_id") or lifecycle.get("call_id") or "").strip()
    if call_id:
        lifecycle["call_id"] = call_id
    session_id = str((payload or {}).get("session_id") or lifecycle.get("session_id") or "").strip()
    if session_id:
        lifecycle["session_id"] = session_id
    process_id = str((payload or {}).get("process_id") or lifecycle.get("process_id") or "").strip()
    if process_id:
        lifecycle["process_id"] = process_id
    status = str((payload or {}).get("status") or lifecycle.get("status") or "").strip()
    if status:
        lifecycle["status"] = status
    if not lifecycle.get("kind") and phase:
        kind = lifecycle_kind_by_phase.get(phase)
        if kind:
            lifecycle["kind"] = kind
    return lifecycle


def shell_protocol_fields(
    payload: dict[str, Any] | None,
    *,
    session_id: str | None,
    command: str | None,
    include_raw: bool,
    shell_output_chunk_fn: Any,
    shell_lifecycle_dict_fn: Any,
    shell_phase_fn: Any,
    shell_event_kind_fn: Any,
    shell_call_id_fn: Any,
    shell_process_id_fn: Any,
    shell_command_text_fn: Any,
    shell_cwd_fn: Any,
    shell_event_source_fn: Any,
    shell_status_fn: Any,
    shell_io_mode_fn: Any,
    shell_stdin_fn: Any,
    shell_interaction_input_fn: Any,
    shell_output_text_fn: Any,
) -> dict[str, Any]:
    output_chunk = shell_output_chunk_fn(payload)
    lifecycle = shell_lifecycle_dict_fn(payload)
    policy_contract = runtime_policy_service.shell_policy_contract_from_payload(dict(payload or {}))
    data = {
        "sessionId": str((payload or {}).get("session_id") or session_id or "").strip() or None,
        "callId": shell_call_id_fn(payload) or None,
        "processId": shell_process_id_fn(payload, session_id=session_id),
        "lifecycle": lifecycle,
        "phase": shell_phase_fn(payload) or None,
        "eventKind": shell_event_kind_fn(payload),
        "lifecyclePhase": str(lifecycle.get("phase") or "").strip() or None,
        "lifecycleKind": str(lifecycle.get("kind") or "").strip() or None,
        "lifecycleStatus": str(lifecycle.get("status") or "").strip() or None,
        "lifecycleSource": str(lifecycle.get("source") or "").strip() or None,
        "command": shell_command_text_fn(payload) or (str(command).strip() if command is not None and str(command).strip() else None),
        "cwd": shell_cwd_fn(payload),
        "source": shell_event_source_fn(payload),
        "status": shell_status_fn(payload),
        "ioMode": shell_io_mode_fn(payload),
        "stream": str((payload or {}).get("stream") or lifecycle.get("stream") or "").strip() or None,
        "stdin": shell_stdin_fn(payload),
        "interactionInput": shell_interaction_input_fn(payload),
        "outputText": shell_output_text_fn(payload),
        "outputChunk": output_chunk,
        "outputChunkEncoding": "base64" if output_chunk else None,
        "policyDecision": str(policy_contract.get("decision") or ""),
        "policyDecisionReason": str(policy_contract.get("reason") or ""),
        "policySnapshot": {
            "approvalPolicy": policy_contract.get("approval_policy"),
            "sandboxMode": policy_contract.get("sandbox_mode"),
            "networkAccessEnabled": policy_contract.get("network_access_enabled"),
            "requestPermissionEnabled": policy_contract.get("request_permission_enabled"),
        },
    }
    if include_raw:
        data["raw"] = dict(payload or {})
    return data


def shell_activity_to_event(payload: dict[str, Any], *, shell_phase_fn: Any) -> ActivityEvent | None:
    phase = shell_phase_fn(payload)
    command = str(payload.get("command") or "").strip()
    if phase == "started":
        params = command_activity_params({"command": command})
        display_command = command_display_text_from_mapping(params, single_line=True) or command
        title = f"Running {display_command}" if display_command else "Running shell command"
        return ActivityEvent(
            title=title,
            status="running",
            kind="command",
            code="command.run",
            params=params,
        )
    if phase == "input":
        text = str(payload.get("stdin") or payload.get("chars") or "").rstrip("\r\n")
        return ActivityEvent(
            title="Shell input",
            status="running",
            detail=text,
            kind="command",
            code="command.input",
            params={"text": text},
        )
    if phase == "output":
        text = str(payload.get("text") or "").strip()
        if not text:
            return None
        return ActivityEvent(
            title="Shell output",
            status="running",
            detail=text,
            kind="command",
            code="command.output",
            params={"text": text},
        )
    if phase == "completed":
        interrupted = bool(payload.get("interrupted"))
        timed_out = bool(payload.get("timed_out"))
        ok = bool(payload.get("ok"))
        if interrupted:
            status = "error"
            title = "Shell command interrupted"
        elif timed_out:
            status = "error"
            title = "Shell command timed out"
        elif ok:
            status = "ok"
            title = "Shell command completed"
        else:
            status = "error"
            title = "Shell command failed"
        return ActivityEvent(
            title=title,
            status=status,
            detail=f"returncode={payload.get('returncode')}",
            kind="command",
            code="command.run",
            params=command_activity_params(
                {"command": command, **dict(payload or {})},
                extra_params={
                    "returncode": payload.get("returncode"),
                    "interrupted": interrupted,
                    "timed_out": timed_out,
                },
            ),
        )
    return None


def shell_turn_item(payload: dict[str, Any] | None, *, shell_call_id_fn: Any, shell_command_text_fn: Any) -> dict[str, Any]:
    raw = dict(payload or {})
    call_id = shell_call_id_fn(raw)
    session_id = str(raw.get("session_id") or "").strip()
    item_id = call_id or session_id or "item_shell"
    arguments_payload = {"command": shell_command_text_fn(raw) or ""}
    if session_id:
        arguments_payload["session_id"] = session_id
    return {
        "type": "function_call",
        "id": item_id,
        "call_id": call_id or None,
        "name": "shell",
        "arguments": json.dumps(arguments_payload, ensure_ascii=False),
    }


def shell_activity_to_turn_event(
    payload: dict[str, Any],
    *,
    shell_phase_fn: Any,
    shell_turn_item_fn: Any,
    shell_status_fn: Any,
    shell_interaction_input_fn: Any,
    shell_output_text_fn: Any,
    shell_stdout_fn: Any,
    shell_stderr_fn: Any,
) -> dict[str, Any] | None:
    phase = shell_phase_fn(payload)
    if phase not in {"started", "input", "output", "completed"}:
        return None
    item = shell_turn_item_fn(payload)
    if phase == "started":
        return {"type": "item.started", "item": item}
    if phase in {"input", "output"}:
        updated: dict[str, Any] = {"phase": phase}
        status = shell_status_fn(payload)
        if status:
            updated["status"] = status
        text = shell_interaction_input_fn(payload) if phase == "input" else shell_output_text_fn(payload)
        if text:
            updated["text"] = text
        return {"type": "item.updated", "item": item, "updated": updated}
    result: dict[str, Any] = {"status": shell_status_fn(payload) or ("ok" if payload.get("ok") else "error")}
    stdout = shell_stdout_fn(payload)
    stderr = shell_stderr_fn(payload)
    if stdout is not None:
        result["stdout"] = stdout
    if stderr is not None:
        result["stderr"] = stderr
    return {"type": "item.completed", "item": item, "result": result}


def shell_payload_item_events(payload: dict[str, Any] | None, *, shell_activity_to_turn_event_fn: Any) -> list[dict[str, Any]]:
    raw_history = (payload or {}).get("_event_history")
    if not isinstance(raw_history, list):
        return []
    item_events: list[dict[str, Any]] = []
    for raw_event in raw_history:
        if not isinstance(raw_event, dict):
            continue
        turn_event = shell_activity_to_turn_event_fn(raw_event)
        if isinstance(turn_event, dict):
            item_events.append(dict(turn_event))
    return item_events


def completed_shell_item_events(
    payload: dict[str, Any] | None,
    *,
    session_turn_events: list[dict[str, Any]] | None,
    shell_payload_item_events_fn: Any,
    shell_activity_to_turn_event_fn: Any,
) -> list[dict[str, Any]]:
    normalized_session_events = [
        dict(item)
        for item in list(session_turn_events or [])
        if isinstance(item, dict) and str(item.get("type") or "").strip().startswith("item.")
    ]
    if normalized_session_events:
        return normalized_session_events
    history_events = shell_payload_item_events_fn(payload)
    if history_events:
        return history_events
    single = shell_activity_to_turn_event_fn(dict(payload or {}))
    return [single] if isinstance(single, dict) else []


def shell_options_from_params(
    params: dict[str, Any],
    *,
    interactive: bool,
    first_text_fn: Any,
    optional_bool_param_fn: Any,
    optional_int_param_fn: Any,
) -> dict[str, Any]:
    options: dict[str, Any] = {}
    cwd = first_text_fn(params, "cwd")
    shell = first_text_fn(params, "shell")
    login = optional_bool_param_fn(params, "login")
    tty = optional_bool_param_fn(params, "tty")
    max_output_chars = optional_int_param_fn(params, "maxOutputChars", "max_output_chars")
    timeout_sec = optional_int_param_fn(params, "timeoutSec", "timeout_sec")
    if cwd:
        options["cwd"] = cwd
    if shell:
        options["shell"] = shell
    if login is not None:
        options["login"] = login
    if tty is not None:
        options["tty"] = tty
    if max_output_chars is not None:
        options["max_output_chars"] = max_output_chars
    if not interactive and timeout_sec is not None:
        options["timeout_sec"] = timeout_sec
    return options


def shell_output_chunk(payload: dict[str, Any] | None, *, shell_phase_fn: Any) -> str | None:
    if shell_phase_fn(payload) != "output":
        return None
    raw = dict(payload or {})
    chunk = raw.get("chunk")
    if chunk is None:
        chunk = raw.get("output_chunk")
    if chunk is not None:
        text = str(chunk).strip()
        return text or None
    text = raw.get("text")
    if text is None:
        text = raw.get("output_text")
    if text is None:
        return None
    return base64.b64encode(str(text).encode("utf-8", errors="replace")).decode("ascii")
