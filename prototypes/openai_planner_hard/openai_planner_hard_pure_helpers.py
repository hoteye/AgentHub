from __future__ import annotations

import json
import re
import shlex
from collections.abc import Callable
from re import Pattern
from typing import Any

from cli.agent_cli.models import AgentIntent, default_response_items
from cli.agent_cli.providers.planner_postprocessing import sanitize_final_answer_text


def message_input_item(role: str, content: str) -> dict[str, Any]:
    return {
        "role": str(role or "user").strip() or "user",
        "content": str(content or ""),
    }


def extract_json_payload(raw_text: str) -> dict[str, Any] | None:
    text = str(raw_text or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else None


def quote_arg(value: Any) -> str:
    return shlex.quote(str(value))


def optional_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def normalize_command_text(
    command_text: str | None,
    *,
    followup_command_pattern: Pattern[str],
    host_platform: Any,
) -> str | None:
    if command_text is None:
        return None
    compact = " ".join(str(command_text).strip().split())
    if not compact:
        return None
    followup_match = followup_command_pattern.search(compact)
    if followup_match:
        compact = compact[: followup_match.start()].strip()
    if not compact:
        return None
    if compact.lower().startswith("/shell "):
        shell_command = host_platform.normalize_shell_command(compact[len("/shell ") :])
        return f"/shell {shell_command}" if shell_command else None
    return compact if compact.startswith("/") else None


def extract_command_text(
    raw_text: str,
    *,
    command_pattern: Pattern[str],
    normalize_command_text_fn: Callable[[str | None], str | None],
) -> str | None:
    match = command_pattern.search(str(raw_text or ""))
    if not match:
        return None
    return normalize_command_text_fn(match.group(1))


def intent_from_raw_text(
    raw_text: str,
    *,
    extract_json_payload_fn: Callable[[str], dict[str, Any] | None],
    normalize_command_text_fn: Callable[[str | None], str | None],
    extract_command_text_fn: Callable[[str], str | None],
    command_pattern: Pattern[str],
    allow_command_pattern_fallback: bool = True,
) -> AgentIntent:
    payload = extract_json_payload_fn(raw_text)
    if payload is not None:
        command_text = normalize_command_text_fn(payload.get("command_text"))
        assistant_text = sanitize_final_answer_text(
            str(payload.get("assistant_text") or "").strip()
        )
        if not assistant_text and not command_text:
            assistant_text = "模型未返回内容。"
        status_hint = (
            str(payload.get("status_hint") or ("tool" if command_text else "llm")).strip() or "llm"
        )
        return AgentIntent(
            assistant_text=assistant_text,
            response_items=default_response_items(assistant_text=assistant_text),
            command_text=command_text,
            status_hint=status_hint,
        )

    assistant_text = sanitize_final_answer_text(str(raw_text or "").strip())
    if not allow_command_pattern_fallback:
        return AgentIntent(
            assistant_text=assistant_text or "模型未返回内容。",
            response_items=default_response_items(
                assistant_text=assistant_text or "模型未返回内容。"
            ),
            command_text=None,
            status_hint="llm",
        )
    command_text = extract_command_text_fn(raw_text)
    if command_text:
        assistant_text = command_pattern.sub("", assistant_text).strip(" \r\n\t:：")
        return AgentIntent(
            assistant_text=assistant_text,
            response_items=default_response_items(assistant_text=assistant_text),
            command_text=command_text,
            status_hint="tool",
        )
    return AgentIntent(
        assistant_text=assistant_text or "模型未返回内容。",
        response_items=default_response_items(assistant_text=assistant_text or "模型未返回内容。"),
        command_text=None,
        status_hint="llm",
    )
