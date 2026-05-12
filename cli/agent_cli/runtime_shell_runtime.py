from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli.approval_continuation_projection_runtime import continuation_status_from_metadata
from cli.agent_cli.runtime_services import command_policy_runtime


def _policy_requirement_name(policy_state: dict[str, Any]) -> str:
    action_policy = policy_state.get("action_policy_payload")
    if isinstance(action_policy, dict):
        requirement_name = str(action_policy.get("requirement") or "").strip().lower()
        if requirement_name:
            return requirement_name
    payload = policy_state.get("payload")
    if isinstance(payload, dict):
        requirement_payload = payload.get("exec_approval_requirement")
        if isinstance(requirement_payload, dict):
            requirement_name = str(requirement_payload.get("requirement") or "").strip().lower()
            if requirement_name:
                return requirement_name
    return ""


def approval_list_event(
    *,
    rows: list[dict[str, Any]],
    status: str | None,
    tool_event_factory: Callable[..., Any],
) -> Any:
    return tool_event_factory(
        name="approval_list",
        ok=True,
        summary=f"approvals={len(rows)}",
        payload={"ok": True, "count": len(rows), "status": status, "approvals": rows},
    )


def approval_list_rows(
    *,
    tickets: list[Any],
    get_action_request_fn: Callable[[str], Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ticket in tickets:
        action_request = get_action_request_fn(ticket.action_id)
        row = {
            "approval_id": ticket.approval_id,
            "status": ticket.status,
            "summary": ticket.summary,
            "reason": ticket.reason,
            "action_type": action_request.action_type if action_request is not None else None,
            "connector_key": action_request.connector_key if action_request is not None else None,
        }
        continuation = continuation_status_from_metadata(ticket=ticket, action_request=action_request)
        if continuation:
            row["continuation"] = continuation
            row["continuation_status"] = continuation.get("continuation_status")
            row["continuation_stale"] = bool(continuation.get("continuation_stale"))
        rows.append(row)
    return rows


def shell_approval_response(
    *,
    command: str,
    requested_by: str,
    timeout_sec: int,
    exec_mode: str,
    cwd: str | None,
    login: bool,
    tty: bool,
    shell: str | None,
    max_output_chars: int,
    metadata: dict[str, Any] | None,
    policy_payload: dict[str, Any] | None,
    normalize_shell_exec_mode_fn: Callable[[str | None], str],
    request_shell_approval_fn: Callable[..., Any],
    shell_command_text_fn: Callable[[str, str], str],
    activity_event_factory: Callable[..., Any],
    prompt_response_factory: Callable[..., Any],
) -> Any:
    normalized_exec_mode = normalize_shell_exec_mode_fn(exec_mode)
    event = request_shell_approval_fn(
        command,
        requested_by=requested_by,
        timeout_sec=timeout_sec,
        exec_mode=normalized_exec_mode,
        cwd=cwd,
        login=login,
        tty=tty,
        shell=shell,
        max_output_chars=max_output_chars,
        metadata=metadata,
        policy_payload=policy_payload,
    )
    activity_events: list[Any] = []
    approval_id = str((event.payload or {}).get("approval_id") or "").strip()
    if approval_id:
        activity_events.append(
            activity_event_factory(
                title="Requested shell approval",
                status="info",
                detail=approval_id,
                kind="command",
                code="approval.request.shell",
                params={"approval_id": approval_id},
            )
        )
    return prompt_response_factory(
        user_text=shell_command_text_fn(command, normalized_exec_mode),
        assistant_text="",
        commentary_text="",
        tool_events=[event],
        activity_events=activity_events,
        handled_as_command=True,
    )


def begin_shell_request(
    *,
    command: str,
    requested_by: str,
    exec_mode: str,
    timeout_sec: int,
    cwd: str | None,
    login: bool,
    tty: bool,
    shell: str | None,
    max_output_chars: int,
    metadata: dict[str, Any] | None,
    on_activity: Callable[[dict[str, Any]], None] | None,
    cancel_event: Any,
    evaluate_exec_command_runtime_policy_fn: Callable[[str, str | None], dict[str, Any]],
    shell_approval_is_cached_fn: Callable[..., bool],
    normalize_shell_exec_mode_fn: Callable[[str | None], str],
    shell_approval_response_fn: Callable[..., Any],
    start_shell_session_fn: Callable[..., dict[str, Any]],
    tool_event_factory: Callable[..., Any],
    shell_result_from_event_fn: Callable[[str, Any, str | None], Any],
    shell_start_event_from_session_fn: Callable[[dict[str, Any], str, str], Any],
    run_shell_command_result_fn: Callable[..., Any],
) -> dict[str, Any]:
    normalized_command = str(command or "").strip()
    normalized_exec_mode = normalize_shell_exec_mode_fn(exec_mode)
    command_policy_decision = command_policy_runtime.evaluate_command_policy(normalized_command)
    if not command_policy_decision.allowed:
        event_name = "shell_start" if normalized_exec_mode == "session_start" else "shell"
        denied_event = command_policy_runtime.policy_denied_tool_event(
            tool_name=event_name,
            decision=command_policy_decision,
        )
        event = tool_event_factory(
            name=event_name,
            ok=bool(denied_event.ok),
            summary=str(denied_event.summary or "shell command denied by policy"),
            payload={
                **dict(denied_event.payload or {}),
                "command": normalized_command,
                "exec_mode": normalized_exec_mode,
            },
        )
        return {
            "status": "error",
            "tool_event": event,
            "session": None,
            "command_result": shell_result_from_event_fn(
                str(command_policy_decision.error_message or "shell command denied by policy"),
                event,
                normalized_command,
            ),
        }
    policy_state = evaluate_exec_command_runtime_policy_fn(normalized_command, cwd)
    policy_payload = dict(policy_state.get("payload") or {})
    requirement_name = _policy_requirement_name(policy_state)
    request_permission_enabled = requirement_name == "needs_approval"
    if requirement_name == "forbidden":
        event_name = "shell_start" if normalized_exec_mode == "session_start" else "shell"
        denied_summary = (
            "shell session denied by runtime policy"
            if normalized_exec_mode == "session_start"
            else "shell command denied by runtime policy"
        )
        event = tool_event_factory(
            name=event_name,
            ok=False,
            summary=denied_summary,
            payload={
                "command": normalized_command,
                "exec_mode": normalized_exec_mode,
                "status": "policy_denied",
                **policy_payload,
            },
        )
        return {
            "status": "error",
            "tool_event": event,
            "session": None,
            "command_result": shell_result_from_event_fn(
                str(policy_payload.get("reason_text") or "shell command denied by runtime policy"),
                event,
                normalized_command,
            ),
        }
    approval_cached = request_permission_enabled and shell_approval_is_cached_fn(
        command=normalized_command,
        cwd=cwd,
        exec_mode=normalized_exec_mode,
        login=login,
        tty=tty,
        shell=shell,
    )
    if request_permission_enabled and not approval_cached:
        response = shell_approval_response_fn(
            normalized_command,
            requested_by=requested_by,
            timeout_sec=timeout_sec,
            exec_mode=normalized_exec_mode,
            cwd=cwd,
            login=login,
            tty=tty,
            shell=shell,
            max_output_chars=max_output_chars,
            metadata=metadata,
            policy_payload=policy_payload or None,
        )
        return {
            "status": "approval_required",
            "response": response,
            "tool_event": response.tool_events[0] if response.tool_events else None,
        }
    if normalized_exec_mode == "session_start":
        try:
            session = start_shell_session_fn(
                normalized_command,
                cwd=cwd,
                login=login,
                tty=tty,
                shell=shell,
                max_output_chars=max_output_chars,
                on_activity=on_activity,
            )
        except Exception as exc:
            denied_payload = {}
            denied_status = "start_failed"
            assistant_text = "Start shell session."
            if isinstance(exc, command_policy_runtime.CommandPolicyError):
                denied_payload = dict(exc.payload or {})
                denied_status = str(denied_payload.get("status") or "policy_denied").strip() or "policy_denied"
                assistant_text = str(exc) or "command denied by policy"
            event = tool_event_factory(
                name="shell_start",
                ok=False,
                summary="shell session denied by policy" if denied_status == "policy_denied" else "shell session start failed",
                payload={
                    "command": normalized_command,
                    "exec_mode": normalized_exec_mode,
                    "error": str(exc),
                    "status": denied_status,
                    **denied_payload,
                },
            )
            return {
                "status": "error",
                "tool_event": event,
                "session": None,
                "command_result": shell_result_from_event_fn(
                    assistant_text,
                    event,
                    normalized_command,
                ),
            }
        event = shell_start_event_from_session_fn(session, normalized_command, normalized_exec_mode)
        return {
            "status": "started",
            "tool_event": event,
            "session": session,
            "command_result": shell_result_from_event_fn(
                "Start shell session.",
                event,
                normalized_command,
            ),
        }
    command_result = run_shell_command_result_fn(
        normalized_command,
        cwd=cwd,
        timeout_sec=timeout_sec,
        login=login,
        tty=tty,
        shell=shell,
        max_output_chars=max_output_chars,
        on_activity=on_activity,
        cancel_event=cancel_event,
    )
    tool_event = command_result.tool_events[0] if command_result.tool_events else None
    return {"status": "completed", "tool_event": tool_event, "command_result": command_result}


def decide_approval(
    *,
    approval_id: str,
    approved: bool | None = None,
    decision: Any = None,
    decided_by: str,
    decision_note: str,
    get_approval_ticket_fn: Callable[[str], Any],
    get_action_request_fn: Callable[[str], Any],
    decide_patch_approval_fn: Callable[..., dict[str, Any]],
    decide_shell_approval_fn: Callable[..., dict[str, Any]],
    decide_background_teammate_approval_fn: Callable[..., dict[str, Any]],
    decide_gateway_approval_fn: Callable[..., dict[str, Any]],
    local_approval_connector_key: str,
    local_approval_plugin_name: str,
) -> dict[str, Any]:
    ticket = get_approval_ticket_fn(approval_id)
    if ticket is None:
        raise ValueError(f"unknown approval_id: {approval_id}")
    action_request = get_action_request_fn(ticket.action_id)
    if action_request is None:
        raise ValueError(f"missing action_request for approval_id: {approval_id}")
    resolved_decision = decision
    if resolved_decision is None:
        resolved_decision = (
            approval_contract_runtime.APPROVAL_DECISION_ACCEPT
            if bool(approved)
            else approval_contract_runtime.APPROVAL_DECISION_DECLINE
        )
    if (
        action_request.action_type == "apply_patch"
        and action_request.connector_key == local_approval_connector_key
        and action_request.plugin_name == local_approval_plugin_name
    ):
        return decide_patch_approval_fn(
            approval_id,
            decision=resolved_decision,
            decided_by=decided_by,
            decision_note=decision_note,
        )
    if (
        action_request.action_type == "shell_command"
        and action_request.connector_key == local_approval_connector_key
        and action_request.plugin_name == local_approval_plugin_name
    ):
        return decide_shell_approval_fn(
            approval_id,
            decision=resolved_decision,
            decided_by=decided_by,
            decision_note=decision_note,
        )
    if (
        action_request.action_type == "background_teammate"
        and action_request.connector_key == local_approval_connector_key
        and action_request.plugin_name == local_approval_plugin_name
    ):
        return decide_background_teammate_approval_fn(
            approval_id,
            decision=resolved_decision,
            decided_by=decided_by,
            decision_note=decision_note,
        )
    return decide_gateway_approval_fn(
        approval_id,
        decision=resolved_decision,
        decided_by=decided_by,
        decision_note=decision_note,
    )
