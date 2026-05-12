from __future__ import annotations

from typing import Any, Dict, Optional

from cli.agent_cli.models import ToolEvent


def tool_event_provider_type(tool_event: ToolEvent | None) -> str:
    if tool_event is None:
        return ""
    payload = dict(tool_event.payload or {})
    return str(payload.get("provider_tool_type") or "").strip().lower()


def shell_exit_code(tool_event: ToolEvent | None) -> int | None:
    if tool_event is None:
        return None
    payload = dict(tool_event.payload or {})
    candidate = payload.get("exit_code", payload.get("returncode"))
    if candidate is None:
        return None
    try:
        return int(candidate)
    except (TypeError, ValueError):
        return None


def shell_exit_code_from_payload(payload: Dict[str, Any]) -> int | None:
    candidate = payload.get("exit_code", payload.get("returncode"))
    if candidate is None:
        return None
    try:
        return int(candidate)
    except (TypeError, ValueError):
        return None


def tool_event_is_shell_like(tool_event: ToolEvent | None) -> bool:
    if tool_event is None:
        return False
    payload = dict(tool_event.payload or {})
    provider_type = tool_event_provider_type(tool_event)
    if provider_type in {"shell_call", "local_shell_call"}:
        return True
    normalized_name = str(getattr(tool_event, "name", "") or "").strip().lower()
    if normalized_name in {"shell", "shell_start", "exec_command", "write_stdin", "bash", "powershell"}:
        return True
    return any(
        key in payload
        for key in (
            "stdout",
            "stderr",
            "aggregated_output",
            "session_id",
            "process_id",
            "exit_code",
            "returncode",
            "timed_out",
            "interrupted",
        )
    )


def shell_stdout_text(payload: Dict[str, Any]) -> str:
    stdout = payload.get("stdout")
    stderr = payload.get("stderr")
    aggregated_output = payload.get("aggregated_output")
    if stdout is None and stderr is None and aggregated_output is not None:
        stdout = aggregated_output
    return str(stdout or "").lstrip("\n").rstrip()


def shell_stderr_text(payload: Dict[str, Any]) -> str:
    return str(payload.get("stderr") or "").strip()


def tool_result_projection_policy(policy: str) -> str:
    return str(policy or "").strip().lower()


def shell_running_status(payload: Dict[str, Any]) -> bool:
    if payload.get("timed_out") or payload.get("interrupted"):
        return False
    if shell_exit_code_from_payload(payload) is not None:
        return False
    status = str(payload.get("status") or "").strip().lower()
    if status in {
        "completed",
        "ok",
        "error",
        "timeout",
        "timed_out",
        "interrupted",
        "missing",
        "spawn_failed",
        "start_failed",
        "stdin_unavailable",
        "unsupported",
        "invalid",
    }:
        return False
    return bool(str(payload.get("session_id") or "").strip())


def shell_failure_line(
    *,
    tool_event: ToolEvent,
    payload: Dict[str, Any],
) -> str:
    if payload.get("interrupted"):
        return "<error>Command was aborted before completion</error>"
    if payload.get("timed_out"):
        return "<error>Command timed out before completion</error>"
    exit_code = shell_exit_code(tool_event)
    if exit_code not in (None, 0):
        return f"<error>Command exited with code {exit_code}</error>"
    if bool(tool_event.ok):
        return ""
    error_text = str(payload.get("error") or "").strip()
    if error_text:
        return f"<error>{error_text}</error>"
    summary = str(tool_event.summary or "").strip()
    if summary:
        return f"<error>{summary}</error>"
    return "<error>Command failed</error>"


def shell_summary_text(tool_event: ToolEvent | None) -> str:
    if tool_event is None:
        return ""
    summary = str(tool_event.summary or "").strip()
    if not summary:
        return ""
    normalized = summary.lower()
    generic_prefixes = ("exec_command", "write_stdin", "shell", "bash", "powershell")
    generic_keywords = ("exited", "running", "completed", "failed", "interrupted", "timeout", "timed out", "rc=")
    if any(normalized.startswith(prefix) for prefix in generic_prefixes) and any(
        keyword in normalized for keyword in generic_keywords
    ):
        return ""
    return summary


def shell_background_line(payload: Dict[str, Any]) -> str:
    session_id = str(payload.get("session_id") or "").strip()
    task_id = str(payload.get("task_id") or session_id).strip()
    if not session_id and not task_id:
        return "Command is still running in the background."
    parts = ["Command is still running in the background."]
    if task_id:
        parts.append(f"task_id: {task_id}.")
    if session_id:
        parts.append(f"Use write_stdin with session_id {session_id} to wait for more output or send input.")
    else:
        parts.append("Use write_stdin to wait for more output or send input.")
    return " ".join(parts)


def shell_codex_background_line(payload: Dict[str, Any]) -> str:
    del payload
    return "Command is still running in the background."


def shell_codex_normalized_explicit_output(
    *,
    explicit_output: str,
    payload: Dict[str, Any],
) -> str:
    lines = [str(line) for line in str(explicit_output or "").splitlines()]
    filtered = [
        line
        for line in lines
        if not (
            line.startswith("Background task ID ")
            or line.startswith("Background artifact: ")
            or line.startswith("Use write_stdin ")
        )
    ]
    if filtered and not any(str(line).startswith("Wall time: ") for line in filtered):
        duration_ms = payload.get("duration_ms")
        if duration_ms is not None:
            try:
                wall_time_line = f"Wall time: {float(duration_ms) / 1000:.4f} seconds"
            except (TypeError, ValueError):
                wall_time_line = ""
            if wall_time_line:
                insert_at = 1 if filtered and str(filtered[0]).startswith("Chunk ID: ") else 0
                filtered.insert(insert_at, wall_time_line)
    return "\n".join(filtered).strip()


def shell_codex_status_line(
    *,
    tool_event: ToolEvent | None,
    payload: Dict[str, Any],
    stderr_text: str = "",
) -> str:
    if payload.get("interrupted"):
        return "Command interrupted."
    if payload.get("timed_out"):
        return "Command timed out."
    error_text = str(payload.get("error") or "").strip()
    if error_text and not stderr_text:
        return error_text
    exit_code = shell_exit_code(tool_event)
    if exit_code not in (None, 0) and not stderr_text:
        return f"Command exited with code {exit_code}."
    if tool_event is not None and not bool(tool_event.ok) and not stderr_text:
        summary = shell_summary_text(tool_event)
        if summary:
            return summary
        return "Command failed."
    return ""


def shell_codex_fallback_line(
    *,
    tool_event: ToolEvent | None,
    payload: Dict[str, Any],
) -> str:
    error_text = str(payload.get("error") or "").strip()
    if error_text:
        return error_text
    summary = shell_summary_text(tool_event)
    if summary:
        return summary
    status_line = shell_codex_status_line(tool_event=tool_event, payload=payload)
    if status_line:
        return status_line
    return "Command completed with no output."


def shell_explicit_fallback_text(
    *,
    command_text: Optional[str],
    assistant_text: str,
    tool_event: ToolEvent | None,
    payload: Dict[str, Any],
    projection_policy: str,
) -> str:
    normalized_policy = tool_result_projection_policy(projection_policy)
    if normalized_policy == "codex_like":
        return shell_codex_fallback_line(tool_event=tool_event, payload=payload)
    error_text = str(payload.get("error") or "").strip()
    if error_text:
        return error_text
    summary = shell_summary_text(tool_event)
    if summary:
        return summary
    if tool_event is not None and bool(tool_event.ok):
        return "Command completed with no output."
    fallback = str(assistant_text or "").strip()
    if fallback:
        return fallback
    fallback = str(command_text or "").strip()
    if fallback:
        return fallback
    return "Command failed."
