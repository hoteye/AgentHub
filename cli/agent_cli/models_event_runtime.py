from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


def tool_event_is_soft_failure(tool_event: Any) -> bool:
    payload = dict(getattr(tool_event, "payload", {}) or {})
    return (
        (not bool(getattr(tool_event, "ok", False)))
        and (payload.get("result_success") is False)
        and (not str(payload.get("error") or "").strip())
    )


def tool_event_is_interrupt(tool_event: Any) -> bool:
    payload = dict(getattr(tool_event, "payload", {}) or {})
    reason = str(payload.get("reason") or "").strip().lower()
    status = str(payload.get("status") or "").strip().lower()
    return (
        str(getattr(tool_event, "name", "") or "").strip() == "interrupted"
        or reason == "user_interrupt"
        or bool(payload.get("interrupted"))
        or status == "interrupted"
        or bool(payload.get("interrupt_requested"))
    )


def tool_events_include_interrupt(events: list[Any]) -> bool:
    return any(tool_event_is_interrupt(event) for event in list(events or []))


def tool_event_is_approval_request(tool_event: Any) -> bool:
    return (
        str(getattr(tool_event, "name", "") or "").strip().lower().endswith("_approval_requested")
    )


def tool_events_include_approval_requests(events: list[Any]) -> bool:
    return any(tool_event_is_approval_request(event) for event in list(events or []))


def is_user_interrupt_assistant_text(text: str, interrupted_text: str) -> bool:
    normalized = str(text or "").strip()
    return normalized in {
        "Execution interrupted.",
        str(interrupted_text or "").strip(),
    }


def shell_command_assistant_text(default_text: str, event: Any | None) -> str:
    if event is None:
        return str(default_text or "")
    payload = dict(getattr(event, "payload", {}) or {})
    reason = str(payload.get("reason") or "").strip().lower()
    if str(getattr(event, "name", "") or "").strip() == "interrupted" or reason == "user_interrupt":
        return "Execution interrupted."
    return str(default_text or "")


def model_visible_function_call_output_text(payload: dict[str, Any]) -> str:
    if not bool(payload.get("function_call_output_model_visible")):
        return ""
    output = payload.get("function_call_output")
    if output is None:
        return ""
    if isinstance(output, str):
        return output.strip()
    if isinstance(output, list):
        text_lines: list[str] = []
        for entry in output:
            if not isinstance(entry, dict):
                continue
            entry_type = str(entry.get("type") or entry.get("item_type") or "").strip().lower()
            if entry_type not in {"input_text", "output_text", "text"}:
                continue
            text = str(entry.get("text") or "").strip()
            if text:
                text_lines.append(text)
        if text_lines:
            return "\n".join(text_lines)
    try:
        return json.dumps(output, ensure_ascii=False).strip()
    except TypeError:
        return str(output).strip()


def tool_event_payload_result_text(payload: dict[str, Any], *, summary: str = "") -> str:
    explicit_output = model_visible_function_call_output_text(payload)
    if explicit_output:
        return explicit_output
    for key in ("text", "output_text", "stdout", "summary_text"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return str(summary or "").strip()


def tool_event_result_text(tool_event: Any) -> str:
    payload = dict(getattr(tool_event, "payload", {}) or {})
    return tool_event_payload_result_text(
        payload, summary=str(getattr(tool_event, "summary", "") or "")
    )


def reference_wrapped_shell_command(payload: dict[str, Any], fallback: str) -> str:
    command = str(fallback or "").strip()
    if not command:
        return ""
    lowered = command.lower()
    if (
        lowered.startswith("/bin/bash -lc ")
        or lowered.startswith("bash -lc ")
        or lowered.startswith("/bin/sh -lc ")
    ):
        return command
    shell = str(payload.get("shell") or payload.get("resolved_shell") or "").strip()
    login = payload.get("login")
    if login is False or not shell:
        return command
    normalized_shell = shell.replace("\\", "/").rstrip("/")
    shell_name = normalized_shell.rsplit("/", 1)[-1].lower()
    if shell_name.endswith(".exe"):
        shell_name = shell_name[:-4]
    if shell_name not in {"bash", "sh", "zsh"}:
        return command
    return _reference_shlex_join([shell, "-lc", command])


def _reference_shlex_join(words: list[str]) -> str:
    return " ".join(_reference_shlex_quote(word) for word in list(words or []))


def _reference_shlex_quote(word: str) -> str:
    text = str(word or "")
    if text == "":
        return "''"
    quoted_parts: list[str] = []
    remaining = text
    while remaining:
        chunk, strategy = _reference_shlex_quoting_strategy(remaining)
        if strategy == "unquoted":
            quoted_parts.append(chunk)
        elif strategy == "single":
            quoted_parts.append(f"'{chunk}'")
        else:
            quoted_parts.append('"' + _reference_double_quote_escape(chunk) + '"')
        remaining = remaining[len(chunk) :]
    return "".join(quoted_parts)


def _reference_shlex_quoting_strategy(text: str) -> tuple[str, str]:
    previous = {"unquoted", "single", "double"}
    index = 0
    if text.startswith("^"):
        previous = {"single"}
        index = 1
    while index < len(text):
        current = set(previous)
        char = text[index]
        if not _reference_unquoted_ok(char):
            current.discard("unquoted")
        if not _reference_single_quoted_ok(char):
            current.discard("single")
        if not _reference_double_quoted_ok(char):
            current.discard("double")
        if not current:
            break
        previous = current
        index += 1
    if "unquoted" in previous:
        strategy = "unquoted"
    elif "single" in previous:
        strategy = "single"
    else:
        strategy = "double"
    return text[: max(index, 1)], strategy


def _reference_unquoted_ok(char: str) -> bool:
    if len(char) != 1:
        return False
    codepoint = ord(char)
    if codepoint >= 0x80:
        return False
    return char.isascii() and char.isalnum() or char in {"+", "-", ".", "/", ":", "@", "]", "_"}


def _reference_single_quoted_ok(char: str) -> bool:
    return char not in {"'", "\\", "^"}


def _reference_double_quoted_ok(char: str) -> bool:
    return char not in {"`", "$", "!", "^"}


def _reference_double_quote_escape(text: str) -> str:
    return "".join(f"\\{char}" if char in {"$", "`", '"', "\\"} else char for char in text)


def function_call_output_content_items_to_text(content_items: list[Any]) -> str | None:
    text_segments = [
        str(getattr(item, "text", "") or "")
        for item in list(content_items or [])
        if str(getattr(item, "item_type", "") or "") == "input_text"
        and str(getattr(item, "text", "") or "").strip()
    ]
    if not text_segments:
        return None
    return "\n".join(text_segments)


def function_output_content_items_from_text_segments(
    text_segments: list[Any],
    *,
    item_from_text: Callable[[str], Any],
) -> list[Any]:
    items: list[Any] = []
    for segment in list(text_segments or []):
        text = str(segment or "").strip()
        if text:
            items.append(item_from_text(text))
    return items


def build_function_call_output_body(
    output: Any,
    *,
    item_from_dict: Callable[[dict[str, Any]], Any],
    item_from_text: Callable[[str], Any],
) -> str | list[Any]:
    if isinstance(output, list):
        items: list[Any] = []
        for entry in output:
            if isinstance(entry, dict):
                items.append(item_from_dict(entry))
            elif isinstance(entry, str) and entry.strip():
                items.append(item_from_text(entry))
        return items
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        return json.dumps(output, ensure_ascii=False)
    if output is None:
        return ""
    return str(output)


def wire_value_from_function_output_body(
    body: str | list[Any],
    *,
    item_to_dict: Callable[[Any], dict[str, Any]],
) -> Any:
    if isinstance(body, list):
        return [item_to_dict(item) for item in body]
    return str(body or "")


def text_from_function_output_body(body: str | list[Any]) -> str | None:
    if isinstance(body, list):
        return function_call_output_content_items_to_text(body)
    text = str(body or "")
    return text if text else None
