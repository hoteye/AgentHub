from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Dict

from cli.agent_cli.models import CommandExecutionResult, ToolEvent, generic_tool_call_item_events
from cli.agent_cli import runtime_exec_policy_apply_patch as apply_patch_policy_runtime
from cli.agent_cli.tools_core import apply_patch_runtime


ApplyPatchError = apply_patch_runtime.ApplyPatchError


def _request_metadata(patch_text: str) -> Dict[str, Any]:
    return dict(apply_patch_runtime.request_metadata(patch_text))


def _merge_request_metadata(payload: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
    if not metadata:
        return dict(payload)
    return {
        **dict(payload),
        **{key: value for key, value in metadata.items() if value not in ("", None, {})},
    }


def _display_change_path(path_value: Any, *, workspace_root: Path) -> str:
    raw_path = str(path_value or "").strip()
    if not raw_path:
        return ""
    path = Path(raw_path)
    if not path.is_absolute():
        return raw_path.replace("\\", "/")
    try:
        return str(path.resolve().relative_to(workspace_root.resolve())).replace("\\", "/")
    except ValueError:
        return raw_path.replace("\\", "/")


def _duration_seconds_text(elapsed_seconds: float) -> str:
    try:
        normalized = max(0.0, float(elapsed_seconds))
    except (TypeError, ValueError):
        normalized = 0.0
    rounded = round(normalized, 1)
    text = f"{rounded:.1f}".rstrip("0").rstrip(".")
    return text or "0"


def _apply_patch_change_summary(payload: Dict[str, Any], *, workspace_root: Path) -> str:
    changes = list(payload.get("changes") or [])
    if not changes:
        return ""
    lines = ["Success. Updated the following files:"]
    for change in changes:
        if not isinstance(change, dict):
            continue
        change_type = str(change.get("change_type") or "").strip().lower()
        status = "A" if change_type == "add" else "D" if change_type == "delete" else "M"
        display_path = _display_change_path(change.get("path"), workspace_root=workspace_root)
        if display_path:
            lines.append(f"{status} {display_path}")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def _apply_patch_function_call_output(
    payload: Dict[str, Any],
    *,
    workspace_root: Path,
    elapsed_seconds: float,
) -> str:
    summary = _apply_patch_change_summary(payload, workspace_root=workspace_root)
    if not summary:
        return ""
    return "\n".join(
        (
            "Exit code: 0",
            f"Wall time: {_duration_seconds_text(elapsed_seconds)} seconds",
            "Output:",
            summary,
        )
    )


def preview_apply_patch(*, patch_text: str, workspace_root: Path) -> Dict[str, Any]:
    return _merge_request_metadata(
        apply_patch_runtime.summarize_preview(
            patch_text=patch_text,
            workspace_root=workspace_root,
        ),
        _request_metadata(patch_text),
    )


def evaluate_apply_patch_requirement(
    *,
    patch_text: str,
    workspace_root: Path,
    approval_policy: str | None,
    sandbox_mode: str | None,
) -> Dict[str, Any]:
    preview_error: str | None = None
    try:
        evidence = dict(
            preview_apply_patch(
                patch_text=patch_text,
                workspace_root=workspace_root,
            )
        )
    except Exception as exc:
        preview_error = str(exc)
        evidence = _merge_request_metadata(
            {
                "preview_ok": False,
                "preview_error": preview_error,
            },
            _request_metadata(patch_text),
        )
    else:
        evidence.setdefault("preview_ok", True)
    return apply_patch_policy_runtime.evaluate_apply_patch_requirement(
        approval_policy=approval_policy,
        sandbox_mode=sandbox_mode,
        evidence=evidence,
        preview_error=preview_error,
    )


def execute_apply_patch(*, patch_text: str, workspace_root: Path) -> ToolEvent:
    root = workspace_root.resolve()
    request_metadata = _request_metadata(patch_text)
    started_at = time.perf_counter()
    try:
        payload = _merge_request_metadata(
            apply_patch_runtime.execute_patch(
                patch_text=patch_text,
                workspace_root=workspace_root,
            ),
            request_metadata,
        )
        elapsed_seconds = time.perf_counter() - started_at
        payload.setdefault("duration_ms", max(0, int(round(elapsed_seconds * 1000))))
        function_call_output = _apply_patch_function_call_output(
            payload,
            workspace_root=root,
            elapsed_seconds=elapsed_seconds,
        )
        if function_call_output:
            payload.setdefault("function_call_output", function_call_output)
            payload.setdefault("function_call_output_model_visible", True)
        file_count = int(payload.get("file_count") or 0)
        return ToolEvent(
            name="apply_patch",
            ok=True,
            summary=f"apply_patch files={file_count}",
            payload=payload,
        )
    except Exception as exc:
        error_text = str(exc)
        elapsed_seconds = time.perf_counter() - started_at
        return ToolEvent(
            name="apply_patch",
            ok=False,
            summary=f"apply_patch failed: {error_text}" if error_text else "apply_patch failed",
            payload=_merge_request_metadata(
                {
                    "ok": False,
                    "workspace_root": str(root),
                    "error": error_text,
                    "duration_ms": max(0, int(round(elapsed_seconds * 1000))),
                    "function_call_output": error_text,
                    "function_call_output_model_visible": True,
                },
                request_metadata,
            ),
        )


def execute_apply_patch_result(*, patch_text: str, workspace_root: Path) -> CommandExecutionResult:
    event = execute_apply_patch(
        patch_text=patch_text,
        workspace_root=workspace_root,
    )
    arguments = dict((event.payload or {}).get("function_call_arguments") or {})
    tool_name = str((event.payload or {}).get("function_call_name") or "apply_patch").strip() or "apply_patch"
    if not arguments:
        arguments = {"patch": str(patch_text or "").strip()}
    return CommandExecutionResult(
        assistant_text="Apply workspace patch.",
        tool_events=[event],
        item_events=generic_tool_call_item_events(
            tool_name=tool_name,
            arguments=arguments,
            ok=bool(event.ok),
            summary=str(event.summary or ""),
            structured_content=dict(event.payload or {}),
        ),
    )
