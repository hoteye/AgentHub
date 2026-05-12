from __future__ import annotations

from typing import Any, Dict, Optional

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.tools_core import apply_patch_runtime

from cli.agent_cli.core.provider_session_tool_results_shell_status_helpers_runtime import shell_exit_code

_APPLY_PATCH_WARNING_PREFIX = "Warning: apply_patch was requested via "
_APPLY_PATCH_WARNING_SUFFIX = ". Use the apply_patch tool instead of exec_command."


def inline_apply_patch_text(command_text: Optional[str]) -> str:
    normalized = str(command_text or "").strip()
    if not normalized:
        return ""
    if "apply_patch" not in normalized and "applypatch" not in normalized:
        return ""
    begin_marker = apply_patch_runtime.BEGIN_PATCH_MARKER
    end_marker = apply_patch_runtime.END_PATCH_MARKER
    begin_index = normalized.find(begin_marker)
    if begin_index < 0:
        return ""
    end_index = normalized.find(end_marker, begin_index)
    if end_index < 0:
        return ""
    return normalized[begin_index : end_index + len(end_marker)].strip()


def codex_apply_patch_explicit_output(
    *,
    explicit_output: str,
    payload: Dict[str, Any],
    tool_event: ToolEvent | None,
) -> str:
    text = str(explicit_output or "").strip()
    if not text:
        return ""
    if text.startswith("Exit code: "):
        return text
    if not text.startswith("Success. Updated the following files:"):
        return text
    exit_code = shell_exit_code(tool_event)
    if exit_code is None:
        exit_code = 0 if tool_event is None or bool(tool_event.ok) else 1
    sections = [f"Exit code: {exit_code}"]
    duration_ms = payload.get("duration_ms")
    try:
        duration_seconds = max(0.0, float(duration_ms) / 1000.0) if duration_ms is not None else 0.0
        duration_text = f"{round(duration_seconds, 1):.1f}".rstrip("0").rstrip(".") or "0"
    except (TypeError, ValueError):
        duration_text = "0"
    sections.append(f"Wall time: {duration_text} seconds")
    sections.append("Output:")
    sections.append(text)
    return "\n".join(sections)


def shell_codex_passthrough_explicit_output(
    *,
    command_text: Optional[str],
    payload: Dict[str, Any],
    explicit_output: str,
) -> bool:
    if not str(explicit_output or "").strip():
        return False
    if str(explicit_output).strip().startswith("Exit code: "):
        return True
    if bool(payload.get("inline_apply_patch_intercepted")):
        return False
    if not inline_apply_patch_text(command_text):
        return False
    return False


def codex_apply_patch_warning_item(
    *,
    command_text: Optional[str],
    tool_event: ToolEvent | None,
    tool_result_projection_policy: str,
) -> Dict[str, Any] | None:
    if tool_result_projection_policy and tool_result_projection_policy.strip().lower() != "codex_like":
        return None
    if tool_event is None:
        return None
    tool_name = str(getattr(tool_event, "name", "") or "").strip()
    if tool_name != "exec_command":
        return None
    payload = dict(tool_event.payload or {})
    patch_text = inline_apply_patch_text(command_text)
    if not patch_text:
        patch_text = inline_apply_patch_text(payload.get("command"))
    if not patch_text:
        return None
    metadata = apply_patch_runtime.request_metadata(patch_text)
    if str(metadata.get("function_call_name") or "").strip() != "apply_patch":
        return None
    return {
        "type": "message",
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": f"{_APPLY_PATCH_WARNING_PREFIX}{tool_name}{_APPLY_PATCH_WARNING_SUFFIX}",
            }
        ],
    }
