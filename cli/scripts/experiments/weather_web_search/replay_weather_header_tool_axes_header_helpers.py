from __future__ import annotations

import copy
import json
import uuid
from typing import Any

from cli.scripts.experiments.weather_web_search.replay_weather_header_tool_axes_model_helpers import DROP_REQUEST_HEADERS


def _normalize_header_name(name: str) -> str:
    lower = str(name or "").strip().lower()
    if lower == "user-agent":
        return "User-Agent"
    if lower == "content-type":
        return "Content-Type"
    if lower == "accept":
        return "Accept"
    if lower == "originator":
        return "originator"
    if lower == "authorization":
        return "Authorization"
    if lower.startswith("x-"):
        return "-".join(part.capitalize() if part else part for part in lower.split("-"))
    return name


def _generate_codex_session_headers() -> dict[str, str]:
    session_id = str(uuid.uuid4())
    turn_id = str(uuid.uuid4())
    metadata = json.dumps(
        {
            "session_id": session_id,
            "turn_id": turn_id,
            "sandbox": "seccomp",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return {
        "session_id": session_id,
        "x-client-request-id": session_id,
        "x-codex-window-id": f"{session_id}:0",
        "x-codex-turn-metadata": metadata,
    }


def _build_header_family(
    *,
    family: str,
    agenthub_headers: dict[str, str],
    codex_headers: dict[str, str],
    api_key: str,
) -> dict[str, str]:
    captured = agenthub_headers if family == "agenthub" else codex_headers
    normalized: dict[str, str] = {}
    for raw_key, value in captured.items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        lower = key.lower()
        if lower in DROP_REQUEST_HEADERS:
            continue
        normalized[_normalize_header_name(key)] = str(value)
    normalized["Authorization"] = f"Bearer {api_key}"
    normalized["Content-Type"] = "application/json"
    if family == "codex":
        generated = _generate_codex_session_headers()
        for key, value in generated.items():
            normalized[_normalize_header_name(key)] = value
    return normalized


def _swap_tools(request: dict[str, Any], tools: list[dict[str, Any]]) -> dict[str, Any]:
    updated = copy.deepcopy(request)
    updated["tools"] = copy.deepcopy(tools)
    return updated
