from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli import runtime_action_policy_runtime
from cli.agent_cli.runtime_services import approval_browser_runtime, approval_resolution_runtime
from cli.agent_cli.runtime_services import approval_runtime_helpers
from cli.agent_cli.runtime_services import approval_runtime_payload_helpers_runtime as payload_helpers
from cli.agent_cli.models import ToolEvent
from cli.agent_cli.tools_core.apply_patch_bridge import preview_apply_patch

approval_decision_turn_events = approval_resolution_runtime.approval_decision_turn_events
background_teammate_summary_text = approval_resolution_runtime.background_teammate_summary_text
decide_background_teammate_approval = approval_resolution_runtime.decide_background_teammate_approval
decide_gateway_approval = approval_resolution_runtime.decide_gateway_approval
decide_patch_approval = approval_resolution_runtime.decide_patch_approval
decide_shell_approval = approval_resolution_runtime.decide_shell_approval
execute_gateway_action_now = approval_resolution_runtime.execute_gateway_action_now
gateway_item_payload = approval_resolution_runtime.gateway_item_payload
record_gateway_action_denied = approval_resolution_runtime.record_gateway_action_denied

browser_profile_prefers_local_execution = approval_browser_runtime.browser_profile_prefers_local_execution
default_browser_action_executor = approval_browser_runtime.default_browser_action_executor
normalize_action_result = approval_browser_runtime.normalize_action_result


def request_patch_approval(
    runtime: Any,
    patch_text: str,
    *,
    requested_by: str,
    connector_key: str,
    plugin_name: str,
    approval_reason: str,
) -> ToolEvent:
    normalized_patch = str(patch_text or "").strip()
    workspace_root = Path(str(getattr(runtime, "cwd", "") or ".")).resolve()
    preview_error: str | None = None
    try:
        preview = preview_apply_patch(
            patch_text=normalized_patch,
            workspace_root=workspace_root,
        )
    except Exception as exc:
        preview_error = str(exc)
        preview = {"preview_ok": False, "preview_error": preview_error}
    policy_state = runtime_action_policy_runtime.evaluate_apply_patch_action_policy(
        runtime,
        patch_text=normalized_patch,
        workspace_root=workspace_root,
    )
    action_policy_payload = dict(policy_state.get("action_policy_payload") or {})
    session_contract = approval_contract_runtime.patch_session_contract(
        preview=preview,
        workspace_root=workspace_root,
    )
    available_decisions = approval_contract_runtime.patch_available_decisions(
        grant_root=str(session_contract.get("grant_root") or "").strip() or None,
    )
    requested = request_gateway_action(
        runtime,
        action_type="apply_patch",
        connector_key=connector_key,
        plugin_name=plugin_name,
        request_payload={
            "patch_text": normalized_patch,
            "preview": preview,
        },
        requested_by=requested_by,
        trace_id=f"patch_{uuid4().hex[:12]}",
        approval_required=True,
        approval_summary="Approve workspace patch",
        approval_reason=approval_reason,
        metadata={
            "source": "cli_apply_patch",
            **({"action_policy": action_policy_payload} if action_policy_payload else {}),
            **({"preview_error": preview_error} if preview_error else {}),
        },
        available_decisions=available_decisions,
        session_cache_keys=list(session_contract.get("session_cache_keys") or []),
        grant_root=str(session_contract.get("grant_root") or "").strip() or None,
    )
    approval_ticket = requested["approval_ticket"]
    payload = payload_helpers.patch_approval_payload(
        approval_ticket=approval_ticket,
        preview=preview,
        approval_reason=approval_reason,
        available_decisions=available_decisions,
        session_contract=session_contract,
        action_policy_payload=action_policy_payload,
    )
    return payload_helpers.patch_approval_event(payload)


def request_shell_approval(
    runtime: Any,
    command: str,
    *,
    requested_by: str,
    timeout_sec: int,
    exec_mode: str,
    cwd: str | None,
    login: bool,
    tty: bool,
    shell: str | None,
    max_output_chars: int,
    metadata: Dict[str, Any] | None,
    sandbox_permissions: str | None = None,
    justification: str | None = None,
    prefix_rule: list[str] | tuple[str, ...] | None = None,
    additional_permissions: Dict[str, Any] | None = None,
    connector_key: str,
    plugin_name: str,
    approval_reason: str,
    policy_payload: Dict[str, Any] | None = None,
) -> ToolEvent:
    normalized_command = str(command or "").strip()
    if not normalized_command:
        return payload_helpers.approval_failure_event(
            name="shell_approval_requested",
            summary="shell approval request failed",
            error="shell command is empty",
        )
    normalized_exec_mode = runtime._normalize_shell_exec_mode(exec_mode)
    normalized_cwd = str(cwd or "").strip() or None
    normalized_shell = runtime._normalize_shell_override(shell)
    normalized_sandbox_permissions = str(sandbox_permissions or "").strip() or None
    normalized_justification = str(justification or "").strip() or None
    normalized_prefix_rule = [
        str(item or "").strip() for item in list(prefix_rule or []) if str(item or "").strip()
    ] or None
    normalized_additional_permissions = (
        dict(additional_permissions) if isinstance(additional_permissions, dict) else None
    )
    resolved_policy_payload = dict(policy_payload or {})
    if not resolved_policy_payload:
        try:
            resolved_policy_payload = dict(
                (
                    runtime_action_policy_runtime.evaluate_exec_command_action_policy(
                        runtime,
                        normalized_command,
                        workdir=normalized_cwd,
                        sandbox_permissions=normalized_sandbox_permissions,
                        additional_permissions=normalized_additional_permissions,
                    ).get("payload")
                    or {}
                )
            )
        except Exception:
            resolved_policy_payload = {}
    action_policy_payload = dict(resolved_policy_payload.get("action_policy") or {})
    proposed_rule = approval_contract_runtime.approval_execpolicy_amendment_rule(
        dict(resolved_policy_payload.get("proposed_rule") or {})
        if isinstance(resolved_policy_payload.get("proposed_rule"), dict)
        else None
    )
    available_decisions = approval_contract_runtime.shell_available_decisions(proposed_rule)
    session_cache_keys = approval_contract_runtime.shell_session_cache_keys(
        command=normalized_command,
        cwd=normalized_cwd,
        exec_mode=normalized_exec_mode,
        login=bool(login),
        tty=bool(tty),
        shell=normalized_shell,
        sandbox_permissions=normalized_sandbox_permissions,
        additional_permissions=normalized_additional_permissions,
    )
    approval_metadata = payload_helpers.shell_approval_metadata(
        exec_mode=normalized_exec_mode,
        cwd=normalized_cwd,
        login=bool(login),
        tty=bool(tty),
        shell=normalized_shell,
        max_output_chars=int(max_output_chars),
        metadata=metadata,
        sandbox_permissions=normalized_sandbox_permissions,
        justification=normalized_justification,
        prefix_rule=normalized_prefix_rule,
        additional_permissions=normalized_additional_permissions,
        action_policy_payload=action_policy_payload,
    )
    request_payload = payload_helpers.shell_request_payload(
        command=normalized_command,
        timeout_sec=int(timeout_sec),
        exec_mode=normalized_exec_mode,
        cwd=normalized_cwd,
        login=bool(login),
        tty=bool(tty),
        shell=normalized_shell,
        max_output_chars=int(max_output_chars),
        sandbox_permissions=normalized_sandbox_permissions,
        justification=normalized_justification,
        prefix_rule=normalized_prefix_rule,
        additional_permissions=normalized_additional_permissions,
    )
    requested = request_gateway_action(
        runtime,
        action_type="shell_command",
        connector_key=connector_key,
        plugin_name=plugin_name,
        request_payload=request_payload,
        requested_by=requested_by,
        trace_id=f"shell_{uuid4().hex[:12]}",
        approval_required=True,
        approval_summary=payload_helpers.shell_approval_summary(normalized_exec_mode),
        approval_reason=approval_reason,
        metadata=approval_metadata,
        available_decisions=available_decisions,
        session_cache_keys=session_cache_keys,
        proposed_rule=proposed_rule,
    )
    approval_ticket = requested["approval_ticket"]
    payload = payload_helpers.shell_approval_payload(
        approval_ticket=approval_ticket,
        approval_reason=approval_reason,
        command=normalized_command,
        timeout_sec=int(timeout_sec),
        exec_mode=normalized_exec_mode,
        cwd=normalized_cwd,
        login=bool(login),
        tty=bool(tty),
        shell=normalized_shell,
        max_output_chars=int(max_output_chars),
        sandbox_permissions=normalized_sandbox_permissions,
        justification=normalized_justification,
        prefix_rule=normalized_prefix_rule,
        additional_permissions=normalized_additional_permissions,
        action_policy_payload=action_policy_payload,
        available_decisions=available_decisions,
        session_cache_keys=session_cache_keys,
        proposed_rule=proposed_rule,
        resolved_policy_payload=resolved_policy_payload,
    )
    return payload_helpers.shell_approval_event(payload)


def request_background_teammate_approval(
    runtime: Any,
    task: str,
    *,
    requested_by: str,
    provider: str,
    model: str,
    reasoning_effort: str,
    task_cwd: str | None,
    queue_cwd: str | None,
    approval_policy: str,
    sandbox_mode: str,
    allowed_paths: list[str] | None,
    blocked_paths: list[str] | None,
    timeout_seconds: float | None,
    connector_key: str,
    plugin_name: str,
    approval_reason: str,
) -> ToolEvent:
    normalized_task = str(task or "").strip()
    if not normalized_task:
        return payload_helpers.approval_failure_event(
            name="background_teammate_approval_requested",
            summary="background teammate approval request failed",
            error="background teammate task is empty",
        )
    normalized_provider = str(provider or "").strip()
    normalized_model = str(model or "").strip()
    normalized_reasoning_effort = str(reasoning_effort or "").strip()
    normalized_task_cwd = str(task_cwd or "").strip() or str(getattr(runtime, "cwd", "") or "").strip()
    normalized_queue_cwd = str(queue_cwd or "").strip() or str(getattr(runtime, "cwd", "") or "").strip()
    normalized_approval_policy = str(approval_policy or "never").strip() or "never"
    normalized_sandbox_mode = str(sandbox_mode or "read-only").strip() or "read-only"
    normalized_allowed_paths = [str(item or "").strip() for item in list(allowed_paths or []) if str(item or "").strip()]
    normalized_blocked_paths = [str(item or "").strip() for item in list(blocked_paths or []) if str(item or "").strip()]
    normalized_timeout_seconds = float(timeout_seconds) if timeout_seconds is not None and float(timeout_seconds) > 0 else None
    request_payload = payload_helpers.background_teammate_request_payload(
        task=normalized_task,
        provider=normalized_provider,
        model=normalized_model,
        reasoning_effort=normalized_reasoning_effort,
        task_cwd=normalized_task_cwd,
        queue_cwd=normalized_queue_cwd,
        approval_policy=normalized_approval_policy,
        sandbox_mode=normalized_sandbox_mode,
        allowed_paths=normalized_allowed_paths,
        blocked_paths=normalized_blocked_paths,
        timeout_seconds=normalized_timeout_seconds,
    )
    requested = request_gateway_action(
        runtime,
        action_type="background_teammate",
        connector_key=connector_key,
        plugin_name=plugin_name,
        request_payload=request_payload,
        requested_by=requested_by,
        trace_id=f"background_teammate_{uuid4().hex[:12]}",
        approval_required=True,
        approval_summary="Approve background teammate live workspace run",
        approval_reason=approval_reason,
        metadata=payload_helpers.background_teammate_metadata(**request_payload),
    )
    approval_ticket = requested["approval_ticket"]
    payload = payload_helpers.background_teammate_approval_payload(
        approval_ticket=approval_ticket,
        approval_reason=approval_reason,
        request_payload=request_payload,
        fallback_available_decisions_factory=approval_contract_runtime.generic_available_decisions,
        summary_text_factory=background_teammate_summary_text,
    )
    return payload_helpers.background_teammate_approval_event(payload)


def request_gateway_action(
    runtime: Any,
    *,
    action_type: str,
    connector_key: str,
    plugin_name: str,
    request_payload: Dict[str, Any],
    requested_by: str,
    trace_id: str,
    event_id: str | None = None,
    workflow_run_id: str | None = None,
    approval_required: bool | None = None,
    approval_summary: str = "",
    approval_reason: str = "",
    metadata: Dict[str, Any] | None = None,
    available_decisions: list[dict[str, Any]] | None = None,
    session_cache_keys: list[str] | None = None,
    proposed_rule: dict[str, Any] | None = None,
    grant_root: str | None = None,
) -> Dict[str, Any]:
    return approval_runtime_helpers.request_gateway_action(
        runtime,
        action_type=action_type,
        connector_key=connector_key,
        plugin_name=plugin_name,
        request_payload=request_payload,
        requested_by=requested_by,
        trace_id=trace_id,
        event_id=event_id,
        workflow_run_id=workflow_run_id,
        approval_required=approval_required,
        approval_summary=approval_summary,
        approval_reason=approval_reason,
        metadata=metadata,
        available_decisions=available_decisions,
        session_cache_keys=session_cache_keys,
        proposed_rule=proposed_rule,
        grant_root=grant_root,
    )
