from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime_action_policy_runtime import evaluate_apply_patch_action_policy
from cli.agent_cli.tools_core import apply_patch_bridge as apply_patch_bridge_runtime
from cli.agent_cli.tools_core import tool_library_runtime as _tool_library_runtime
from cli.agent_cli.tools_core import (
    tool_registry_file_guard_runtime,
    tools_helper_runtime,
)

tool_library_runtime = _tool_library_runtime


def apply_patch(self: Any, patch_text: str) -> ToolEvent:
    guard_event = _claude_structured_edit_guard_event(self, patch_text)
    if guard_event is not None:
        return guard_event
    return tools_helper_runtime.ApplyPatchBridgeCompat.execute_apply_patch(
        patch_text=patch_text,
        workspace_root=self.file_workspace_root(),
    )


def apply_patch_result(self: Any, patch_text: str) -> CommandExecutionResult:
    guard_event = _claude_structured_edit_guard_event(self, patch_text)
    if guard_event is not None:
        return self._result_from_event(
            "Edit workspace file.",
            guard_event,
            tool_name=str((guard_event.payload or {}).get("function_call_name") or "apply_patch"),
            arguments=dict((guard_event.payload or {}).get("function_call_arguments") or {}),
        )
    policy_result = _runtime_apply_patch_policy_result(self, patch_text)
    if policy_result is not None:
        return policy_result
    return tools_helper_runtime.ApplyPatchBridgeCompat.execute_apply_patch_result(
        patch_text=patch_text,
        workspace_root=self.file_workspace_root(),
        call_structured_helper=self._call_structured_helper,
        result_from_event=self._result_from_event,
        apply_patch_call=self.apply_patch,
    )


def _claude_structured_edit_guard_event(self: Any, patch_text: str) -> ToolEvent | None:
    return tool_registry_file_guard_runtime.claude_structured_edit_guard_event(self, patch_text)


def _claude_structured_edit_guard_failure_event(
    self: Any,
    *,
    request: Any,
    error: str,
    guard_failure: str = "",
) -> ToolEvent:
    return tool_registry_file_guard_runtime.claude_structured_edit_guard_failure_event(
        self,
        request=request,
        error=error,
        guard_failure=guard_failure,
    )


def _claude_structured_edit_arguments(request: Any) -> dict[str, Any]:
    return tool_registry_file_guard_runtime.claude_structured_edit_arguments(request)


def _runtime_apply_patch_policy_result(
    self: Any,
    patch_text: str,
) -> CommandExecutionResult | None:
    runtime_policy_status = _runtime_policy_status(self)
    if runtime_policy_status is None:
        return None
    policy_state = evaluate_apply_patch_action_policy(
        SimpleNamespace(
            runtime_policy_status=lambda: dict(runtime_policy_status),
            cwd=self.workspace_root(),
        ),
        patch_text=patch_text,
        workspace_root=self.file_workspace_root(),
    )
    requirement_payload = dict(policy_state.get("payload") or {})
    requirement_name = (
        str((policy_state.get("action_policy_payload") or {}).get("requirement") or "")
        .strip()
        .lower()
    )
    if requirement_name in {"", "skip"}:
        return None
    if requirement_name == "forbidden":
        error_text = (
            str(requirement_payload.get("reason_text") or "patch blocked").strip()
            or "patch blocked"
        )
        if str(requirement_payload.get("reason_code") or "") == "apply_patch_sandbox_read_only":
            error_text = "runtime sandbox is read-only"
        return _patch_error_result(
            self,
            patch_text=patch_text,
            summary="patch blocked",
            error_text=error_text,
            payload=requirement_payload,
        )
    if requirement_name == "needs_approval":
        request_patch_approval = getattr(self, "_request_patch_approval_fn", None)
        approval_runtime = (
            getattr(request_patch_approval, "__self__", None)
            if callable(request_patch_approval)
            else None
        )
        try:
            preview = apply_patch_bridge_runtime.preview_apply_patch(
                patch_text=patch_text,
                workspace_root=self.file_workspace_root(),
            )
            approval_cached = approval_contract_runtime.patch_approval_is_cached(
                approval_runtime if approval_runtime is not None else self,
                preview=preview,
                workspace_root=self.file_workspace_root(),
            )
        except Exception:
            approval_cached = False
        if approval_cached:
            return None
        if not callable(request_patch_approval):
            return _patch_error_result(
                self,
                patch_text=patch_text,
                summary="patch approval request failed",
                error_text="patch approval bridge unavailable",
                payload=requirement_payload,
            )
        try:
            event = request_patch_approval(patch_text)
        except Exception as exc:
            return _patch_error_result(
                self,
                patch_text=patch_text,
                summary="patch approval request failed",
                error_text=str(exc) or "patch approval request failed",
                payload=requirement_payload,
            )
        if isinstance(event.payload, dict):
            event.payload.update(requirement_payload)
        result = self._result_from_event(
            "Request patch approval.",
            event,
            tool_name="patch_approval_requested",
            arguments={"patch": patch_text},
        )
        result.assistant_text = _approval_request_text("Request patch approval.", event)
        return result
    return None


def _patch_error_result(
    self: Any,
    *,
    patch_text: str,
    summary: str,
    error_text: str,
    payload: dict[str, Any],
) -> CommandExecutionResult:
    event = ToolEvent(
        name="apply_patch",
        ok=False,
        summary=summary,
        payload={
            "ok": False,
            "error": str(error_text or summary or "apply_patch failed"),
            **dict(payload or {}),
        },
    )
    return self._result_from_event(
        "Patch blocked." if summary == "patch blocked" else "Patch approval request failed.",
        event,
        tool_name="apply_patch",
        arguments={"patch": patch_text},
    )


def _runtime_policy_status(self: Any) -> dict[str, Any] | None:
    getter = getattr(self, "_runtime_policy_status_getter", None)
    if not callable(getter):
        return None
    try:
        raw_status = getter()
    except Exception:
        return None
    if raw_status is None:
        return None
    if isinstance(raw_status, dict):
        return dict(raw_status)
    try:
        return dict(raw_status)
    except Exception:
        return None


def _approval_request_text(prefix: str, event: ToolEvent) -> str:
    try:
        from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
            approval_request_text as shared_approval_request_text,
        )

        return shared_approval_request_text(prefix, event)
    except Exception:
        payload = event.payload or {}
        approval_id = str(payload.get("approval_id") or "").strip()
        if not approval_id:
            return prefix
        return (
            f"{prefix}\n\n"
            f"approval_id={approval_id}\n"
            f"/approve {approval_id}\n"
            f"/reject {approval_id}"
        )


APPLY_PATCH_METHOD_BINDINGS = (
    ("apply_patch", apply_patch),
    ("apply_patch_result", apply_patch_result),
)
