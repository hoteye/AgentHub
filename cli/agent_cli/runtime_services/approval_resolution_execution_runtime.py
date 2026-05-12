from __future__ import annotations

from typing import Any, Dict, Tuple

from cli.agent_cli.gateway_core import create_audit_record
from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime_services import command_policy_runtime


def execute_shell_approval_action(runtime: Any, payload: Dict[str, Any]) -> Tuple[ToolEvent, str]:
    normalized_exec_mode = runtime._normalize_shell_exec_mode(str(payload.get("exec_mode") or "exec_once"))
    if normalized_exec_mode == "session_start":
        try:
            session = runtime.start_shell_session(
                str(payload.get("command") or ""),
                cwd=str(payload.get("cwd") or "").strip() or None,
                login=bool(payload.get("login", True)),
                tty=bool(payload.get("tty")),
                shell=str(payload.get("shell") or "").strip() or None,
                max_output_chars=int(payload.get("max_output_chars") or 12000),
            )
            return (
                runtime._shell_start_event_from_session(
                    session,
                    command=str(payload.get("command") or ""),
                    exec_mode=normalized_exec_mode,
                ),
                normalized_exec_mode,
            )
        except Exception as exc:
            denied_payload = {}
            denied_status = "start_failed"
            if isinstance(exc, command_policy_runtime.CommandPolicyError):
                denied_payload = dict(exc.payload or {})
                denied_status = str(denied_payload.get("status") or "policy_denied").strip() or "policy_denied"
            return (
                ToolEvent(
                    name="shell_start",
                    ok=False,
                    summary="shell session denied by policy" if denied_status == "policy_denied" else "shell session start failed",
                    payload={
                        "command": str(payload.get("command") or ""),
                        "exec_mode": normalized_exec_mode,
                        "error": str(exc),
                        "status": denied_status,
                        **denied_payload,
                    },
                ),
                normalized_exec_mode,
            )
    return (
        # Phase 1 keeps additional_permissions as approval/replay contract data only.
        # Real execution-time sandbox enforcement is intentionally deferred.
        runtime.run_shell_command(
            str(payload.get("command") or ""),
            cwd=str(payload.get("cwd") or "").strip() or None,
            timeout_sec=int(payload.get("timeout_sec") or 60),
            login=bool(payload.get("login", True)),
            tty=bool(payload.get("tty")),
            shell=str(payload.get("shell") or "").strip() or None,
            max_output_chars=int(payload.get("max_output_chars") or 12000),
        ),
        normalized_exec_mode,
    )


def approved_gateway_execution_audit_record(
    approval_ticket: Any,
    action_request: Any,
    *,
    execution_status: str,
    execution_summary: str,
    execution_details: Dict[str, Any],
) -> Any:
    return create_audit_record(
        trace_id=approval_ticket.trace_id,
        stage="action_execute",
        status=execution_status,
        summary=execution_summary,
        event_id=action_request.event_id,
        workflow_run_id=action_request.workflow_run_id,
        action_id=action_request.action_id,
        approval_id=approval_ticket.approval_id,
        details=execution_details,
    )
