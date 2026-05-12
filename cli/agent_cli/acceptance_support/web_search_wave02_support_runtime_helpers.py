from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from cli.agent_cli.acceptance_support.web_search_wave02_support_pure_helpers import (
    CommandResult,
    _action_rows,
    _clean_strings,
    _to_int,
)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _run_command(
    *,
    system: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: int,
) -> CommandResult:
    start = time.perf_counter()
    stdout_text = ""
    stderr_text = ""
    exit_code: int | None = None
    timed_out = False
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        exit_code = int(proc.returncode)
        stdout_text = proc.stdout
        stderr_text = proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = 124
        stdout_text = exc.stdout or ""
        stderr_text = exc.stderr or ""
    elapsed = round(time.perf_counter() - start, 3)
    _write_text(stdout_path, stdout_text)
    _write_text(stderr_path, stderr_text)
    return CommandResult(
        system=system,
        exit_code=exit_code,
        elapsed_seconds=elapsed,
        timed_out=timed_out,
        command=list(command),
        cwd=str(cwd),
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )


def _skipped_command(
    *,
    system: str,
    command: list[str],
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    reason: str,
) -> CommandResult:
    _write_text(stdout_path, "")
    _write_text(stderr_path, f"skipped: {reason}\n")
    return CommandResult(
        system=system,
        exit_code=None,
        elapsed_seconds=None,
        timed_out=False,
        command=list(command),
        cwd=str(cwd),
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        skipped=True,
        skip_reason=str(reason),
    )


def _agenthub_detail(stdout_path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "assistant_text": "",
        "tool_event_count": 0,
        "turn_event_count": 0,
        "response_item_count": 0,
        "status": {},
        "protocol_diagnostics": {},
        "protocol_path": {},
        "request_contract": {},
        "tool_names": [],
        "turn_item_types": [],
        "response_item_types": [],
        "web_search_actions": [],
        "web_search_routes": [],
        "has_final_message": False,
        "provider_name": "",
        "provider_public_name": "",
        "provider_planner": "",
        "provider_runtime_state": "",
        "availability_status": "",
    }
    raw = _read_json(stdout_path)
    if raw is None:
        return payload
    tool_events = [dict(item) for item in list(raw.get("tool_events") or []) if isinstance(item, dict)]
    turn_events = [dict(item) for item in list(raw.get("turn_events") or []) if isinstance(item, dict)]
    response_items = [dict(item) for item in list(raw.get("response_items") or []) if isinstance(item, dict)]
    payload["assistant_text"] = str(raw.get("assistant_text") or "").strip()
    payload["tool_event_count"] = len(tool_events)
    payload["turn_event_count"] = len(turn_events)
    payload["response_item_count"] = len(response_items)
    payload["status"] = dict(raw.get("status") or {})
    payload["protocol_diagnostics"] = dict(raw.get("protocol_diagnostics") or {})
    payload["protocol_path"] = dict(payload["protocol_diagnostics"].get("protocol_path") or {})
    payload["request_contract"] = dict(payload["protocol_diagnostics"].get("request_contract") or {})
    payload["tool_names"] = [str(item.get("name") or "").strip() for item in tool_events if str(item.get("name") or "").strip()]
    payload["turn_item_types"] = [
        str((item.get("item") or {}).get("type") or "").strip()
        for item in turn_events
        if isinstance(item.get("item"), dict) and str((item.get("item") or {}).get("type") or "").strip()
    ]
    payload["response_item_types"] = [
        str(item.get("type") or "").strip() for item in response_items if str(item.get("type") or "").strip()
    ]
    payload["web_search_actions"] = _action_rows(response_items) or _action_rows(
        [dict(item.get("item") or {}) for item in turn_events if isinstance(item.get("item"), dict)]
    )
    payload["web_search_routes"] = [
        dict((item.get("payload") or {}).get("web_search_route") or {})
        for item in tool_events
        if isinstance(item.get("payload"), dict) and isinstance((item.get("payload") or {}).get("web_search_route"), dict)
    ]
    payload["has_final_message"] = any(
        str(item.get("type") or "").strip() == "message" and str(item.get("phase") or "").strip() == "final_answer"
        for item in response_items
    ) or any(
        isinstance(item.get("item"), dict)
        and str((item.get("item") or {}).get("type") or "").strip() == "agent_message"
        and str((item.get("item") or {}).get("phase") or "").strip() == "final_answer"
        for item in turn_events
    )
    status = dict(payload["status"] or {})
    payload["provider_name"] = str(status.get("provider_name") or "").strip()
    payload["provider_public_name"] = str(status.get("provider_public_name") or status.get("provider_name") or "").strip()
    payload["provider_planner"] = str(status.get("provider_planner") or "").strip()
    payload["provider_runtime_state"] = str(status.get("provider_runtime_state") or "").strip()
    payload["availability_status"] = str(status.get("availability_status") or "").strip()
    return payload


def _codex_detail(stdout_path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "assistant_text": "",
        "thread_id": "",
        "item_counts": {},
        "item_types": [],
        "error_messages": [],
        "web_search_actions": [],
    }
    if not stdout_path.exists():
        return payload
    item_counts: dict[str, int] = {}
    assistant_messages: list[str] = []
    item_types: list[str] = []
    errors: list[str] = []
    web_search_items: list[dict[str, Any]] = []
    for raw_line in stdout_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(event.get("type") or "").strip() == "thread.started":
            payload["thread_id"] = str(event.get("thread_id") or "").strip()
        if str(event.get("type") or "").strip() == "error":
            message = str(event.get("message") or "").strip()
            if message:
                errors.append(message)
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip()
        if item_type:
            item_counts[item_type] = item_counts.get(item_type, 0) + 1
            item_types.append(item_type)
        if item_type in {"web_search", "web_search_call"}:
            web_search_items.append(dict(item))
        if item_type == "agent_message":
            text = str(item.get("text") or "").strip()
            if text:
                assistant_messages.append(text)
    payload["assistant_text"] = assistant_messages[-1] if assistant_messages else ""
    payload["item_counts"] = item_counts
    payload["item_types"] = item_types
    payload["error_messages"] = errors
    payload["web_search_actions"] = _action_rows(web_search_items)
    return payload


def _claude_detail(stdout_path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "assistant_text": "",
        "result_type": "",
        "result_subtype": "",
        "duration_ms": None,
        "duration_api_ms": None,
        "session_id": "",
        "usage": {},
        "model_usage": {},
        "response_block_types": [],
        "server_tool_uses": [],
        "web_search_requests": 0,
    }
    raw = _read_json(stdout_path)
    if raw is None:
        return payload
    payload["assistant_text"] = str(raw.get("result") or "").strip()
    payload["result_type"] = str(raw.get("type") or "").strip()
    payload["result_subtype"] = str(raw.get("subtype") or "").strip()
    payload["duration_ms"] = raw.get("duration_ms")
    payload["duration_api_ms"] = raw.get("duration_api_ms")
    payload["session_id"] = str(raw.get("session_id") or "").strip()
    payload["usage"] = dict(raw.get("usage") or {})
    payload["model_usage"] = dict(raw.get("modelUsage") or {})
    payload["response_block_types"] = _clean_strings(raw.get("response_block_types"))
    payload["server_tool_uses"] = _clean_strings(raw.get("server_tool_uses"))
    payload["web_search_requests"] = _to_int(
        (payload["usage"].get("server_tool_use") or {}).get("web_search_requests")
        if isinstance(payload["usage"], dict)
        else 0
    )
    return payload


__all__ = [
    "_agenthub_detail",
    "_claude_detail",
    "_codex_detail",
    "_read_json",
    "_run_command",
    "_skipped_command",
    "_write_json",
    "_write_text",
]
