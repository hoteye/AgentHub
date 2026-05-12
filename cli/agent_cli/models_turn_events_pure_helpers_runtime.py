from __future__ import annotations

import shlex
from typing import Any

from cli.agent_cli.web_search_argument_projection_runtime import (
    derived_web_search_arguments_from_payload as _derived_web_search_arguments_from_payload_shared,
)


def normalized_text(value: Any) -> str:
    return str(value or "").strip()


def normalized_slug(value: Any) -> str:
    return normalized_text(value).lower()


def mapping_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def compact_argument_map(arguments: dict[str, Any] | None) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in dict(arguments or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        compact[key] = value
    return compact


def derived_arguments_from_payload(tool_name: str, payload: dict[str, Any]) -> Any:
    normalized_name = normalized_text(tool_name).lower()
    if normalized_name == "web_search":
        return compact_argument_map(_derived_web_search_arguments_from_payload_shared(payload)) or None
    if normalized_name == "web_fetch":
        return compact_argument_map(
            {
                "url": normalized_text(payload.get("url")) or None,
                "max_chars": payload.get("max_chars"),
            }
        ) or None
    if normalized_name == "open":
        return compact_argument_map(
            {
                "ref": normalized_text(payload.get("ref") or payload.get("ref_id")) or None,
                "line": payload.get("requested_line"),
            }
        ) or None
    if normalized_name == "click":
        return compact_argument_map(
            {
                "ref_id": normalized_text(payload.get("source_ref_id") or payload.get("ref_id")) or None,
                "id": payload.get("clicked_link_id"),
            }
        ) or None
    if normalized_name == "find":
        return compact_argument_map(
            {
                "ref_id": normalized_text(payload.get("ref_id")) or None,
                "pattern": normalized_text(payload.get("pattern")) or None,
            }
        ) or None
    return None


def reasoning_summary_text_from_extra(extra: dict[str, Any]) -> str:
    summary = extra.get("summary")
    if isinstance(summary, list):
        parts: list[str] = []
        for entry in summary:
            if isinstance(entry, dict):
                text = normalized_text(entry.get("text"))
            else:
                text = normalized_text(entry)
            if text:
                parts.append(text)
        if parts:
            return "\n\n".join(parts).strip()
    if isinstance(summary, dict):
        return normalized_text(summary.get("text"))
    if isinstance(summary, str):
        return summary.strip()
    return normalized_text(extra.get("summary_text"))


def shell_command_text_from_action(action: Any) -> str:
    if not isinstance(action, dict):
        return ""
    command = action.get("command")
    if isinstance(command, (list, tuple)):
        parts = [normalized_text(item) for item in command if normalized_text(item)]
        if not parts:
            return ""
        try:
            return shlex.join(parts)
        except Exception:
            return " ".join(parts)
    return normalized_text(command)


def _shell_output_blocks(output: Any) -> list[dict[str, Any]]:
    if not isinstance(output, list):
        return []
    return [dict(entry) for entry in output if isinstance(entry, dict)]


def shell_output_aggregated_text(output: Any) -> str:
    chunks: list[str] = []
    for block in _shell_output_blocks(output):
        stdout = block.get("stdout")
        stderr = block.get("stderr")
        text = block.get("text")
        output_text = block.get("output_text")
        if stdout is not None:
            chunks.append(str(stdout))
        if stderr is not None:
            chunks.append(str(stderr))
        if stdout is None and stderr is None:
            if text not in (None, ""):
                chunks.append(str(text))
            elif output_text not in (None, ""):
                chunks.append(str(output_text))
    return "".join(chunks)


def shell_output_exit_code(output: Any) -> int | None:
    for block in reversed(_shell_output_blocks(output)):
        outcome = block.get("outcome")
        if not isinstance(outcome, dict):
            continue
        if normalized_slug(outcome.get("type")) != "exit":
            continue
        value = outcome.get("exit_code")
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def command_execution_metadata_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw = dict(payload or {})
    metadata: dict[str, Any] = {}
    cwd = normalized_text(raw.get("cwd"))
    if cwd:
        metadata["cwd"] = cwd
    process_id = normalized_text(raw.get("process_id") or raw.get("command_execution_process_id"))
    if process_id:
        metadata["process_id"] = process_id
    duration_ms = optional_int(raw.get("duration_ms"))
    if duration_ms is not None:
        metadata["duration_ms"] = duration_ms
    command_actions = raw.get("command_actions")
    if isinstance(command_actions, list):
        metadata["command_actions"] = [dict(item) if isinstance(item, dict) else item for item in command_actions]
    function_call_name = normalized_text(raw.get("function_call_name"))
    if function_call_name:
        metadata["function_call_name"] = function_call_name
    function_call_arguments = raw.get("function_call_arguments")
    if function_call_arguments is not None:
        metadata["function_call_arguments"] = function_call_arguments
    return metadata


__all__ = [
    "command_execution_metadata_from_payload",
    "compact_argument_map",
    "derived_arguments_from_payload",
    "mapping_dict",
    "normalized_slug",
    "normalized_text",
    "optional_int",
    "reasoning_summary_text_from_extra",
    "shell_command_text_from_action",
    "shell_output_aggregated_text",
    "shell_output_exit_code",
]
