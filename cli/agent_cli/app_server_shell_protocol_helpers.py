from __future__ import annotations

from typing import Any


def shell_process_id(payload: dict[str, Any] | None, *, session_id: str | None = None) -> str | None:
    process_id = str((payload or {}).get("process_id") or "").strip()
    if process_id:
        return process_id
    normalized_session_id = str(session_id or "").strip()
    return normalized_session_id or None


def shell_command_text(payload: dict[str, Any] | None) -> str | None:
    text = str((payload or {}).get("command") or "").strip()
    return text or None


def shell_cwd(payload: dict[str, Any] | None) -> str | None:
    text = str((payload or {}).get("cwd") or "").strip()
    return text or None


def shell_stdin(payload: dict[str, Any] | None) -> str | None:
    raw = dict(payload or {})
    value = raw.get("stdin")
    if value is None:
        value = raw.get("interaction_input")
    if value is None:
        return None
    return str(value)


def shell_interaction_input(payload: dict[str, Any] | None, *, shell_phase_fn, shell_stdin_fn) -> str | None:
    if shell_phase_fn(payload) != "input":
        return None
    return shell_stdin_fn(payload) or str((payload or {}).get("chars") or "")


def shell_output_text(payload: dict[str, Any] | None, *, shell_phase_fn) -> str | None:
    if shell_phase_fn(payload) != "output":
        return None
    raw = dict(payload or {})
    text = raw.get("text")
    if text is None:
        text = raw.get("output_text")
    if text is None:
        return None
    return str(text)


def shell_stdout(payload: dict[str, Any] | None) -> str | None:
    text = (payload or {}).get("stdout")
    if text is None:
        return None
    return str(text)


def shell_stderr(payload: dict[str, Any] | None) -> str | None:
    text = (payload or {}).get("stderr")
    if text is None:
        return None
    return str(text)


def shell_aggregated_output(payload: dict[str, Any] | None, *, shell_stdout_fn, shell_stderr_fn) -> str | None:
    aggregated = (payload or {}).get("aggregated_output")
    if aggregated is not None:
        return str(aggregated)
    if payload is not None and ("stdout" in payload or "stderr" in payload):
        return f"{shell_stdout_fn(payload) or ''}{shell_stderr_fn(payload) or ''}"
    stdout = shell_stdout_fn(payload) or ""
    stderr = shell_stderr_fn(payload) or ""
    combined = f"{stdout}{stderr}"
    return combined or None


def shell_event_source(payload: dict[str, Any] | None, *, shell_phase_fn) -> str | None:
    phase = shell_phase_fn(payload)
    if not phase:
        return None
    if phase == "input":
        return "unified_exec_interaction"
    return "unified_exec_startup"


def shell_io_mode(payload: dict[str, Any] | None) -> str | None:
    raw = dict(payload or {})
    mode = str(raw.get("io_mode") or "").strip().lower()
    if mode in {"pty", "pipes"}:
        return mode
    tty = raw.get("tty")
    if isinstance(tty, bool):
        return "pty" if tty else "pipes"
    return None


def is_shell_execution_payload(payload: dict[str, Any] | None) -> bool:
    raw = dict(payload or {})
    if raw.get("lifecycle"):
        return True
    return any(
        raw.get(key) is not None
        for key in (
            "call_id",
            "session_id",
            "process_id",
            "command",
            "io_mode",
            "returncode",
            "exit_code",
            "stdout",
            "stderr",
            "interrupted",
            "timed_out",
        )
    )


def first_text(params: dict[str, Any], *names: str) -> str:
    for name in names:
        value = params.get(name)
        if value is None:
            continue
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()
    return ""


def optional_bool_param(params: dict[str, Any], *names: str) -> bool | None:
    for name in names:
        value = params.get(name)
        if value is None:
            continue
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    return None


def optional_int_param(params: dict[str, Any], *names: str) -> int | None:
    for name in names:
        value = params.get(name)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None
