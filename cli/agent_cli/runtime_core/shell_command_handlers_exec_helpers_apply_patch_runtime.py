from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli.models import CommandExecutionResult, ToolEvent, generic_tool_call_item_events
from cli.agent_cli.runtime_action_policy_runtime import evaluate_apply_patch_action_policy
from cli.agent_cli.runtime_core import shell_command_handlers_pure_helpers_runtime
from cli.agent_cli.runtime_core.tool_call_context_runtime import current_provider_tool_call_id
from cli.agent_cli.tools_core import apply_patch_bridge as apply_patch_bridge_module
from cli.agent_cli.tools_core import apply_patch_runtime


def command_looks_like_inline_apply_patch(command_text: str) -> bool:
    normalized = str(command_text or "").strip()
    if not normalized:
        return False
    if "apply_patch" not in normalized and "applypatch" not in normalized:
        return False
    return (
        apply_patch_runtime.BEGIN_PATCH_MARKER in normalized
        and apply_patch_runtime.END_PATCH_MARKER in normalized
    )


def inline_apply_patch_text(command_text: str) -> str:
    normalized = str(command_text or "").strip()
    if not command_looks_like_inline_apply_patch(normalized):
        return ""
    begin_index = normalized.find(apply_patch_runtime.BEGIN_PATCH_MARKER)
    if begin_index < 0:
        return ""
    end_index = normalized.find(apply_patch_runtime.END_PATCH_MARKER, begin_index)
    if end_index < 0:
        return ""
    return normalized[begin_index : end_index + len(apply_patch_runtime.END_PATCH_MARKER)].strip()


def inline_apply_patch_workspace_root(runtime: Any, *, workdir: str | None) -> Path:
    if str(workdir or "").strip():
        return Path(str(workdir)).resolve()
    tools = getattr(runtime, "tools", None)
    if tools is not None:
        getter = getattr(tools, "workspace_root", None)
        if callable(getter):
            try:
                value = getter()
            except TypeError:
                value = None
            if value:
                return Path(str(value)).resolve()
        for attr_name in ("WORKSPACE_ROOT", "PROJECT_ROOT"):
            value = getattr(tools, attr_name, None)
            if value:
                return Path(str(value)).resolve()
    return Path.cwd().resolve()


def codex_apply_patch_exec_output(success_text: str) -> str:
    return str(success_text or "").strip()


def inline_apply_patch_exec_result(
    runtime: Any,
    *,
    request: shell_command_handlers_pure_helpers_runtime.ExecCommandRequest,
    compact_arguments: Callable[[Dict[str, Any]], Dict[str, Any]],
    approval_request_text: Callable[[str, ToolEvent], str],
    canonical_command_tool_event: Callable[..., ToolEvent],
    tool_trace: Callable[..., None],
) -> CommandExecutionResult | None:
    patch_text = inline_apply_patch_text(request.command)
    if not patch_text:
        return None
    workspace_root = inline_apply_patch_workspace_root(runtime, workdir=request.workdir)
    policy_state = evaluate_apply_patch_action_policy(
        runtime,
        patch_text=patch_text,
        workspace_root=workspace_root,
    )
    policy_payload = dict(policy_state["payload"] or {})
    requirement_name = str((policy_state["action_policy_payload"] or {}).get("requirement") or "").strip()
    if requirement_name == "forbidden":
        error_text = str(policy_payload.get("reason_text") or "Patch blocked.")
        event = ToolEvent(
            name="apply_patch",
            ok=False,
            summary="patch blocked",
            payload={
                "ok": False,
                "error": error_text,
                "workspace_root": str(workspace_root),
                **policy_payload,
            },
        )
        return CommandExecutionResult(
            assistant_text=error_text,
            tool_events=[event],
            item_events=generic_tool_call_item_events(
                tool_name="apply_patch",
                arguments={"patch": patch_text},
                ok=False,
                summary=str(event.summary or ""),
                structured_content=dict(event.payload or {}),
                error_message=error_text,
            ),
        )
    if requirement_name == "needs_approval":
        try:
            preview = apply_patch_bridge_module.preview_apply_patch(
                patch_text=patch_text,
                workspace_root=workspace_root,
            )
            approval_cached = approval_contract_runtime.patch_approval_is_cached(
                runtime,
                preview=preview,
                workspace_root=workspace_root,
            )
        except Exception:
            approval_cached = False
        if not approval_cached:
            event = runtime.request_patch_approval(patch_text)
            event.payload.update(policy_payload)
            return CommandExecutionResult(
                assistant_text=approval_request_text("Request patch approval.", event),
                tool_events=[event],
                item_events=generic_tool_call_item_events(
                    tool_name="patch_approval_requested",
                    arguments={"patch": patch_text},
                    ok=bool(event.ok),
                    summary=str(event.summary or ""),
                    structured_content=dict(event.payload or {}),
                ),
            )
        policy_payload.update(
            {
                "approval_cache_hit": True,
                "policy_decision": "allowed",
                "policy_decision_reason": "approval_cached",
            }
        )
    apply_patch_event = apply_patch_bridge_module.execute_apply_patch(
        patch_text=patch_text,
        workspace_root=workspace_root,
    )
    provider_call_id = current_provider_tool_call_id()
    apply_patch_payload = dict(apply_patch_event.payload or {})
    apply_patch_payload.update(policy_payload)
    if provider_call_id:
        apply_patch_payload.setdefault("provider_call_id", provider_call_id)
    exec_payload = dict(apply_patch_payload)
    if provider_call_id:
        exec_payload.setdefault("provider_call_id", provider_call_id)
    exec_payload.update(
        {
            "command": request.command,
            "workdir": request.workdir,
            "tty": request.tty,
            "login": request.login,
            "yield_time_ms": request.yield_time_ms,
            "timeout_ms": request.timeout_ms,
            "max_output_tokens": request.max_output_tokens,
            "status": "completed" if apply_patch_event.ok else "failed",
            "duration_ms": apply_patch_payload.get("duration_ms", 0),
            "inline_apply_patch_intercepted": True,
        }
    )
    exec_payload = shell_command_handlers_pure_helpers_runtime.shell_contract_payload(
        exec_payload,
        shell_override=request.shell_override,
        resolved_shell=request.shell,
    )
    if apply_patch_event.ok:
        function_call_output = codex_apply_patch_exec_output(
            str(apply_patch_event.payload.get("function_call_output") or "")
        )
        if function_call_output:
            exec_payload["function_call_output"] = function_call_output
            exec_payload["function_call_output_model_visible"] = True
        exec_payload.setdefault("exit_code", 0)
        exec_payload.setdefault("returncode", 0)
    else:
        exec_payload["error"] = str(
            apply_patch_event.payload.get("error") or apply_patch_event.summary or "apply_patch failed"
        ).strip()
        exec_payload.setdefault("exit_code", 1)
        exec_payload.setdefault("returncode", 1)
    exec_event = canonical_command_tool_event(
        "exec_command",
        exec_payload,
        command=request.command,
    )
    arguments = dict(apply_patch_payload.get("function_call_arguments") or {})
    if not arguments:
        arguments = {"patch": patch_text}
    item_events = generic_tool_call_item_events(
        tool_name=str(apply_patch_payload.get("function_call_name") or "apply_patch").strip() or "apply_patch",
        arguments=arguments,
        ok=bool(apply_patch_event.ok),
        summary=str(apply_patch_event.summary or ""),
        structured_content=apply_patch_payload,
        error_message=str(apply_patch_payload.get("error") or ""),
    )
    tool_trace(
        "tool.exec_command.inline_apply_patch.intercepted",
        command=request.command,
        workdir=request.workdir,
        workspace_root=str(workspace_root),
        ok=bool(apply_patch_event.ok),
        file_count=apply_patch_payload.get("file_count"),
        preview_arguments=compact_arguments(arguments),
    )
    return CommandExecutionResult(
        assistant_text=str(apply_patch_event.payload.get("function_call_output") or apply_patch_event.summary or ""),
        tool_events=[exec_event],
        item_events=item_events,
    )
