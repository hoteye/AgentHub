from __future__ import annotations

import json
from typing import Any

from cli.agent_cli.runtime_core.command_handlers_structured_runtime import decode_raw_text_arg


def parse_request_orchestration_payload(arg_text: str) -> dict[str, Any]:
    decoded_arg_text = decode_raw_text_arg(arg_text)
    try:
        payload = json.loads(str(decoded_arg_text or "").strip() or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"__request_orchestration expects JSON payload: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("__request_orchestration expects JSON object payload")
    source_text = str(
        payload.get("source_text")
        or payload.get("task")
        or payload.get("prompt")
        or payload.get("message")
        or ""
    ).strip()
    if not source_text:
        raise ValueError("__request_orchestration requires source_text")
    planning_adjustments = payload.get("planning_adjustments")
    return {
        "source_text": source_text,
        "confirmation_required": bool(payload.get("needs_confirmation", True)),
        "planning_adjustments": (
            dict(planning_adjustments) if isinstance(planning_adjustments, dict) else {}
        ),
    }


def parse_json_object_payload(arg_text: str, *, command_name: str) -> dict[str, Any]:
    decoded_arg_text = decode_raw_text_arg(arg_text)
    try:
        payload = json.loads(str(decoded_arg_text or "").strip() or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"{command_name} expects JSON payload: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{command_name} expects JSON object payload")
    return dict(payload)


def parse_orchestration_review_args(runtime: Any, arg_text: str) -> tuple[str, str]:
    parse_args = getattr(runtime, "_parse_args", None)
    if callable(parse_args):
        positionals, _options = parse_args(arg_text)
        run_id = str(positionals[0] if len(positionals) >= 1 else "").strip()
        card_id = str(positionals[1] if len(positionals) >= 2 else "").strip()
        return (run_id, card_id)
    parts = str(arg_text or "").split()
    run_id = str(parts[0] if len(parts) >= 1 else "").strip()
    card_id = str(parts[1] if len(parts) >= 2 else "").strip()
    return (run_id, card_id)


def parse_orchestration_continue_args(runtime: Any, arg_text: str) -> tuple[str, dict[str, Any]]:
    parse_args = getattr(runtime, "_parse_args", None)
    if not callable(parse_args):
        return ("", {})
    positionals, options = parse_args(arg_text)
    tokens = [
        str(item or "").strip() for item in list(positionals or []) if str(item or "").strip()
    ]
    normalized_options: dict[str, Any] = {
        str(key or "").strip(): value
        for key, value in dict(options or {}).items()
        if str(key or "").strip()
    }
    run_id = ""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("--"):
            if not run_id:
                run_id = token
            index += 1
            continue
        key = token[2:].strip()
        value: Any = True
        if index + 1 < len(tokens):
            next_token = tokens[index + 1]
            if not next_token.startswith("--"):
                value = next_token
                index += 1
        if key and key not in normalized_options:
            normalized_options[key] = value
        index += 1
    return (run_id, normalized_options)


def bool_option(value: Any, *, default: bool) -> bool:
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
