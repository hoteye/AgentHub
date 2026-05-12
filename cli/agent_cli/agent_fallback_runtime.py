from __future__ import annotations

import ast
import json
import re
from collections.abc import Mapping
from typing import Any

from cli.agent_cli.providers.responses_503_diagnostics import format_responses_request_503_risks

_EXCEPTION_PREFIX_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*:\s*")
_ERROR_CODE_PREFIX_RE = re.compile(r"^Error code:\s*\d+\s*-\s*", re.IGNORECASE)
_MESSAGE_FIELD_RE = re.compile(
    r"""['"]message['"]\s*:\s*(['"])(?P<message>.*?)(?<!\\)\1""",
    re.DOTALL,
)
_REQUEST_ID_SUFFIX_RE = re.compile(r"\s*\(request id:\s*[^)]*\)\s*$", re.IGNORECASE)


def planner_runtime_error_diagnostic_lines(
    runtime_error_diagnostics: Mapping[str, Any] | None
) -> list[str]:
    return format_responses_request_503_risks(runtime_error_diagnostics)


def _strip_noise(text: str) -> str:
    return _REQUEST_ID_SUFFIX_RE.sub("", str(text or "").strip()).strip()


def _find_message_field(value: Any) -> str:
    if isinstance(value, str):
        return ""
    if isinstance(value, Mapping):
        for key in ("message", "detail", "error_description", "error"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return _strip_noise(candidate)
        for candidate in value.values():
            message = _find_message_field(candidate)
            if message:
                return message
    if isinstance(value, list):
        for candidate in value:
            message = _find_message_field(candidate)
            if message:
                return message
    return ""


def _structured_message_from_error(raw: str) -> str:
    payload_start = raw.find("{")
    if payload_start < 0:
        return ""
    payload_text = raw[payload_start:].strip()
    for parser in (ast.literal_eval, json.loads):
        try:
            parsed = parser(payload_text)
        except Exception:
            continue
        message = _find_message_field(parsed)
        if message:
            return message
    match = _MESSAGE_FIELD_RE.search(payload_text)
    if match:
        return _strip_noise(match.group("message"))
    return ""


def provider_runtime_error_message(error_text: str) -> str:
    raw = str(error_text or "").strip()
    if not raw:
        return "provider 调用失败。"
    structured = _structured_message_from_error(raw)
    if structured:
        return structured
    text = _EXCEPTION_PREFIX_RE.sub("", raw, count=1)
    text = _ERROR_CODE_PREFIX_RE.sub("", text, count=1)
    return _strip_noise(text) or raw


def provider_runtime_error_hints(
    error_text: str, *, has_request_diagnostics: bool = False
) -> list[str]:
    del has_request_diagnostics
    message = provider_runtime_error_message(error_text)
    return [message] if message else []


def planner_fallback_text(
    *,
    planner_runtime_error: str | None,
    planner_error: str | None,
    provider_status: Mapping[str, Any],
    planner_runtime_error_diagnostics: Mapping[str, Any] | None,
    planner_runtime_fallback_text: str,
    planner_unavailable_fallback_text: str,
) -> str:
    lines: list[str]
    if planner_runtime_error:
        del provider_status, planner_runtime_error_diagnostics
        return f"{planner_runtime_fallback_text}{provider_runtime_error_message(planner_runtime_error)}"
    lines = [planner_unavailable_fallback_text]
    if planner_error:
        lines.append(f"provider 初始化失败: {planner_error}")
    return "\n".join(lines)
