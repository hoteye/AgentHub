from __future__ import annotations

import shlex
from collections.abc import Callable
from typing import Any

from cli.agent_cli import runtime_policy as runtime_policy_service
from cli.agent_cli.runtime_core.shell_command_handlers_output_text_runtime import (
    chunk_id as _chunk_id,
)
from cli.agent_cli.runtime_core.shell_command_handlers_output_text_runtime import (
    exec_output_text as _exec_output_text,
)
from cli.agent_cli.runtime_core.shell_command_handlers_output_text_runtime import (
    formatted_exec_output as _formatted_exec_output,
)
from cli.agent_cli.runtime_core.shell_command_handlers_output_text_runtime import (
    max_output_chars_for_tokens,
)

__all__ = [
    "canonical_command_tool_event",
    "canonical_exec_output_text",
    "exec_command_arguments",
    "exec_command_poll_payload",
    "max_output_chars_for_tokens",
    "normalize_shell_option",
    "parse_shell_action",
    "preview_text",
    "tool_event_trace_payload",
]


def normalize_shell_option(runtime: Any, shell: Any) -> str | None:
    raw = str(shell or "").strip()
    if not raw:
        return None
    normalizer = getattr(runtime, "_normalize_shell_override", None)
    if callable(normalizer):
        try:
            normalized = normalizer(raw)
        except TypeError:
            normalized = None
        if isinstance(normalized, str) and normalized.strip():
            return normalized.strip()
    return raw


def preview_text(value: Any, *, max_chars: int = 240) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}..."


def canonical_exec_output_text(payload: dict[str, Any]) -> str:
    normalized = dict(payload or {})
    sections: list[str] = []
    output_text = _exec_output_text(normalized)
    chunk_id = _chunk_id(normalized, output_text)
    if chunk_id:
        sections.append(f"Chunk ID: {chunk_id}")
    duration_ms = normalized.get("duration_ms")
    if duration_ms is not None:
        try:
            sections.append(f"Wall time: {float(duration_ms) / 1000:.4f} seconds")
        except (TypeError, ValueError):
            pass
    exit_code = normalized.get("exit_code", normalized.get("returncode"))
    if exit_code is not None:
        sections.append(f"Process exited with code {exit_code}")
    elif str(normalized.get("session_id") or "").strip():
        sections.append(f"Process running with session ID {normalized['session_id']}")
        task_id = str(normalized.get("task_id") or "").strip()
        if task_id:
            sections.append(f"Background task ID {task_id}")
        artifact_path = str(normalized.get("background_artifact_path") or "").strip()
        if artifact_path:
            sections.append(f"Background artifact: {artifact_path}")
        if task_id:
            sections.append(f"Use write_stdin {task_id} to poll for completion or send input")
    formatted_output, computed_original_token_count = _formatted_exec_output(
        normalized, output_text
    )
    original_token_count = normalized.get("original_token_count", computed_original_token_count)
    if original_token_count is not None:
        sections.append(f"Original token count: {original_token_count}")
    sections.append("Output:")
    sections.append(formatted_output)
    return "\n".join(sections)


def parse_shell_action(arg_text: str) -> tuple[str, list[str]]:
    tokens = shlex.split(str(arg_text or "").strip(), posix=True)
    if not tokens:
        return "exec", []
    action = str(tokens[0] or "").strip().lower()
    if action in {"start", "write", "terminate", "stop"}:
        return action, tokens[1:]
    return "exec", tokens


def tool_event_trace_payload(
    event: Any,
    *,
    compact_arguments: Callable[[dict[str, Any]], dict[str, Any]],
    preview_text_fn: Callable[[Any], str],
) -> dict[str, Any]:
    payload = dict(event.payload or {})
    return compact_arguments(
        {
            "event_name": str(event.name or ""),
            "ok": bool(event.ok),
            "summary": str(event.summary or ""),
            "status": payload.get("status"),
            "command": payload.get("command"),
            "session_id": payload.get("session_id"),
            "process_id": payload.get("process_id"),
            "call_id": payload.get("call_id"),
            "workdir": payload.get("workdir") or payload.get("cwd"),
            "shell": payload.get("shell"),
            "shell_override": payload.get("shell_override"),
            "resolved_shell": payload.get("resolved_shell"),
            "tty": payload.get("tty"),
            "login": payload.get("login"),
            "yield_time_ms": payload.get("yield_time_ms"),
            "timeout_ms": payload.get("timeout_ms"),
            "exit_code": payload.get("exit_code", payload.get("returncode")),
            "error": str(payload.get("error") or "").strip() or None,
            "output_preview": preview_text_fn(
                payload.get("aggregated_output")
                or payload.get("stdout")
                or payload.get("stderr")
                or payload.get("function_call_output")
                or ""
            )
            or None,
        }
    )


def canonical_command_tool_event(
    name: str,
    payload: dict[str, Any],
    *,
    command: str,
    tool_event_cls: type[Any],
    canonical_exec_output_text_fn: Callable[[dict[str, Any]], str],
) -> Any:
    normalized = dict(payload or {})
    normalized["command"] = str(command or normalized.get("command") or "").strip()
    resolved_shell = str(normalized.get("resolved_shell") or normalized.get("shell") or "").strip()
    if resolved_shell:
        normalized.setdefault("resolved_shell", resolved_shell)
    policy_contract = runtime_policy_service.shell_policy_contract_from_payload(normalized)
    normalized.setdefault("policy_decision", str(policy_contract.get("decision") or ""))
    normalized.setdefault("policy_decision_reason", str(policy_contract.get("reason") or ""))
    if policy_contract.get("approval_policy") is not None:
        normalized.setdefault("approval_policy", policy_contract["approval_policy"])
    if policy_contract.get("sandbox_mode") is not None:
        normalized.setdefault("sandbox_mode", policy_contract["sandbox_mode"])
    if policy_contract.get("network_access_enabled") is not None:
        normalized.setdefault(
            "network_access_enabled", bool(policy_contract["network_access_enabled"])
        )
    if policy_contract.get("request_permission_enabled") is not None:
        normalized.setdefault(
            "request_permission_enabled", bool(policy_contract["request_permission_enabled"])
        )
    has_exec_like_output = any(
        key in normalized
        for key in (
            "aggregated_output",
            "stdout",
            "stderr",
            "exit_code",
            "returncode",
            "session_id",
            "chunk_id",
        )
    )
    if has_exec_like_output:
        output_text = _exec_output_text(normalized)
        normalized.setdefault("chunk_id", _chunk_id(normalized, output_text))
        _, original_token_count = _formatted_exec_output(normalized, output_text)
        if original_token_count is not None:
            normalized.setdefault("original_token_count", original_token_count)
    if "function_call_output" not in normalized:
        if has_exec_like_output:
            normalized["function_call_output"] = canonical_exec_output_text_fn(normalized)
    summary = (
        f"{name} exited"
        if normalized.get("exit_code", normalized.get("returncode")) is not None
        else (
            f"{name} running {normalized.get('session_id')}"
            if str(normalized.get("session_id") or "").strip()
            else f"{name} completed"
        )
    )
    return tool_event_cls(
        name=name,
        ok=bool(normalized.get("ok", True)),
        summary=summary,
        payload=normalized,
    )


def exec_command_arguments(
    *,
    command: str,
    workdir: str | None,
    shell: str | None,
    shell_override: str | None,
    resolved_shell: str | None,
    tty: bool,
    login: bool,
    yield_time_ms: int | None,
    timeout_ms: int | None,
    max_output_tokens: int | None,
    sandbox_permissions: str | None,
    justification: str | None,
    prefix_rule: tuple[str, ...] | None,
    additional_permissions: dict[str, Any] | None,
    compact_arguments: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    return compact_arguments(
        {
            "cmd": command,
            "workdir": workdir,
            "shell": shell,
            "shell_override": shell_override,
            "resolved_shell": resolved_shell,
            "tty": tty,
            "login": login,
            "yield_time_ms": yield_time_ms,
            "timeout_ms": timeout_ms,
            "max_output_tokens": max_output_tokens,
            "sandbox_permissions": sandbox_permissions,
            "justification": justification,
            "prefix_rule": list(prefix_rule) if prefix_rule is not None else None,
            "additional_permissions": (
                dict(additional_permissions) if additional_permissions is not None else None
            ),
        }
    )


def exec_command_poll_payload(
    *,
    poll_payload: dict[str, Any],
    command: str,
    session_id: str,
    call_id: Any,
    process_id: Any,
    workdir: str | None,
    shell: str | None,
    shell_override: str | None,
    resolved_shell: str | None,
    tty: bool,
    login: bool,
    yield_time_ms: int | None,
    timeout_ms: int | None,
    max_output_tokens: int | None,
    sandbox_permissions: str | None,
    justification: str | None,
    prefix_rule: tuple[str, ...] | None,
    additional_permissions: dict[str, Any] | None,
    function_call_arguments: dict[str, Any],
) -> dict[str, Any]:
    payload = dict(poll_payload or {})
    if _exec_payload_is_terminal(payload):
        if process_id is not None:
            payload.setdefault("command_execution_process_id", process_id)
        payload.pop("session_id", None)
        payload.pop("process_id", None)
        payload.pop("task_id", None)
        payload.pop("background_artifact_path", None)
        payload.pop("completion_notification_available", None)
        payload.pop("completion_notification_status", None)
        payload.pop("completion_poll_tool", None)
    else:
        payload.setdefault("session_id", session_id or None)
        payload.setdefault("process_id", process_id)
    payload.setdefault("command", command)
    payload.setdefault("call_id", call_id)
    payload.setdefault("workdir", workdir)
    payload.setdefault("shell", shell)
    payload.setdefault("resolved_shell", resolved_shell or shell)
    if shell_override:
        payload.setdefault("shell_override", shell_override)
    payload.setdefault("tty", tty)
    payload.setdefault("login", login)
    payload.setdefault("yield_time_ms", yield_time_ms)
    payload.setdefault("timeout_ms", timeout_ms)
    payload.setdefault("max_output_tokens", max_output_tokens)
    payload.setdefault("sandbox_permissions", sandbox_permissions)
    payload.setdefault("justification", justification)
    if prefix_rule is not None:
        payload.setdefault("prefix_rule", list(prefix_rule))
    if additional_permissions is not None:
        payload.setdefault("additional_permissions", dict(additional_permissions))
    payload.setdefault("function_call_arguments", function_call_arguments)
    policy_contract = runtime_policy_service.shell_policy_contract_from_payload(payload)
    payload.setdefault("policy_decision", str(policy_contract.get("decision") or ""))
    payload.setdefault("policy_decision_reason", str(policy_contract.get("reason") or ""))
    if policy_contract.get("approval_policy") is not None:
        payload.setdefault("approval_policy", policy_contract["approval_policy"])
    if policy_contract.get("sandbox_mode") is not None:
        payload.setdefault("sandbox_mode", policy_contract["sandbox_mode"])
    if policy_contract.get("network_access_enabled") is not None:
        payload.setdefault(
            "network_access_enabled", bool(policy_contract["network_access_enabled"])
        )
    if policy_contract.get("request_permission_enabled") is not None:
        payload.setdefault(
            "request_permission_enabled", bool(policy_contract["request_permission_enabled"])
        )
    payload["suppress_output_update"] = True
    return payload


def _exec_payload_is_terminal(payload: dict[str, Any]) -> bool:
    exit_code = payload.get("exit_code", payload.get("returncode"))
    if exit_code is not None:
        return True
    phase = str(payload.get("phase") or "").strip().lower()
    if phase == "completed":
        return True
    lifecycle = payload.get("lifecycle")
    if isinstance(lifecycle, dict):
        lifecycle_phase = str(lifecycle.get("phase") or "").strip().lower()
        if lifecycle_phase == "completed":
            return True
    status = str(payload.get("status") or "").strip().lower()
    return status in {
        "ok",
        "error",
        "completed",
        "timeout",
        "interrupted",
        "pruned",
    }
