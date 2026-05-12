from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SNAPSHOT_ENV_KEYS = (
    "AGENT_CLI_HOME",
    "AGENT_CLI_PROVIDER",
    "AGENT_CLI_MODEL",
    "AGENT_CLI_REASONING_EFFORT",
    "AGENTHUB_PROVIDER_HOME",
    "AGENTHUB_PROVIDER_STRICT_ISOLATION",
    "AGENTHUB_STARTUP_CWD",
    "OPENAI_BASE_URL",
    "OPENAI_API_KEY",
    "CODEX_HOME",
    "BENCH_MODEL",
    "BENCH_REASONING_EFFORT",
)


@dataclass
class CommandResult:
    name: str
    command: list[str]
    cwd: str
    exit_code: int
    elapsed_seconds: float
    timed_out: bool
    started_at: str
    ended_at: str
    stdout_path: str
    stderr_path: str


@dataclass
class RunSummary:
    harness_root: str
    prompt_path: str
    prompt_preview: str
    provider: str
    model: str
    reasoning_effort: str
    openai_base_url: str
    agenthub_config_mode: str
    agenthub_config_path: str
    agenthub_auth_path: str
    agenthub_interaction_profile: str
    codex_config_mode: str
    codex_provider_id: str
    codex_config_path: str
    codex_auth_path: str
    agenthub_workspace: str
    codex_workspace: str
    codex_home: str
    codex_bin: str
    agenthub_run: dict[str, Any]
    codex_run: dict[str, Any]
    agenthub_validation: dict[str, Any] | None
    codex_validation: dict[str, Any] | None
    agenthub_assistant_text: str
    codex_assistant_text: str
    codex_thread_id: str
    codex_errors: list[str]
    layer_summary: dict[str, Any]
    log_manifest: dict[str, str]


def _read_prompt(prompt_path: Path) -> str:
    return prompt_path.read_text(encoding="utf-8").strip()


def _prompt_preview(prompt: str, limit: int = 200) -> str:
    normalized = " ".join(prompt.split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3] + "..."


def _load_api_key(auth_json: Path, key_name: str) -> str:
    env_value = os.environ.get(key_name, "").strip()
    if env_value:
        return env_value
    payload = json.loads(auth_json.read_text(encoding="utf-8"))
    value = str(payload.get(key_name, "")).strip()
    if value:
        return value
    raise SystemExit(f"missing API key `{key_name}` in env or {auth_json}")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _env_snapshot(env: dict[str, str]) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for key in SNAPSHOT_ENV_KEYS:
        value = str(env.get(key, "") or "")
        if not value:
            continue
        snapshot[key] = "<redacted>" if key.endswith("_API_KEY") else value
    return snapshot


def _auth_snapshot(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
    }
    if not path.exists():
        return payload
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - diagnostics only
        payload["error"] = f"{type(exc).__name__}: {exc}"
        return payload
    if isinstance(data, dict):
        payload["keys"] = sorted(str(key) for key in data.keys())
    else:
        payload["type"] = type(data).__name__
    return payload


def _text_file_snapshot(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
    }
    if not path.exists():
        return payload
    try:
        payload["text"] = path.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover - diagnostics only
        payload["error"] = f"{type(exc).__name__}: {exc}"
    return payload


def _workspace_file_inventory(workspace: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not workspace.exists():
        return entries
    for path in sorted(p for p in workspace.rglob("*") if p.is_file()):
        try:
            stat = path.stat()
            size = stat.st_size
        except OSError:
            size = -1
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            digest = ""
        entries.append(
            {
                "path": str(path.relative_to(workspace)),
                "size": size,
                "sha256": digest,
            }
        )
    return entries


def _agenthub_detail(stdout_path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "assistant_text": "",
        "commentary_text": "",
        "tool_event_count": 0,
        "turn_event_count": 0,
        "response_item_count": 0,
        "status": {},
        "protocol_diagnostics": {},
    }
    if not stdout_path.exists():
        return payload
    try:
        data = json.loads(stdout_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - diagnostics only
        payload["parse_error"] = f"{type(exc).__name__}: {exc}"
        return payload
    payload["assistant_text"] = str(data.get("assistant_text") or "")
    payload["commentary_text"] = str(data.get("commentary_text") or "")
    payload["tool_event_count"] = len(list(data.get("tool_events") or []))
    payload["turn_event_count"] = len(list(data.get("turn_events") or []))
    payload["response_item_count"] = len(list(data.get("response_items") or []))
    payload["status"] = dict(data.get("status") or {})
    payload["protocol_diagnostics"] = dict(data.get("protocol_diagnostics") or {})
    payload["response_items"] = list(data.get("response_items") or [])
    payload["tool_events"] = list(data.get("tool_events") or [])
    payload["turn_events"] = list(data.get("turn_events") or [])
    return payload


def _codex_detail(stdout_path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "thread_id": "",
        "turn_started": 0,
        "turn_completed": 0,
        "error_count": 0,
        "item_counts": {},
        "errors": [],
        "agent_messages": [],
        "events": [],
    }
    if not stdout_path.exists():
        return payload
    item_counts: dict[str, int] = {}
    for raw_line in stdout_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            payload.setdefault("non_json_lines", []).append(line)
            continue
        payload["events"].append(event)
        event_type = str(event.get("type") or "")
        if event_type == "thread.started":
            payload["thread_id"] = str(event.get("thread_id") or payload["thread_id"])
        elif event_type == "turn.started":
            payload["turn_started"] += 1
        elif event_type == "turn.completed":
            payload["turn_completed"] += 1
        elif event_type == "error":
            payload["error_count"] += 1
            message = str(event.get("message") or "").strip()
            if message:
                payload["errors"].append(message)
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "")
        if item_type:
            item_counts[item_type] = item_counts.get(item_type, 0) + 1
        if item_type == "agent_message":
            text = str(item.get("text") or "").strip()
            if text:
                payload["agent_messages"].append(text)
        elif item_type == "error":
            message = str(item.get("message") or "").strip()
            if message:
                payload["errors"].append(message)
    payload["item_counts"] = item_counts
    return payload


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _stable_json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _payload_sha256(payload: Any) -> str:
    return hashlib.sha256(_stable_json_text(payload).encode("utf-8")).hexdigest()


def _preview_text(value: Any, limit: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _id_shape(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "empty"
    if re.fullmatch(r"[0-9a-f]{32}", text, flags=re.IGNORECASE):
        return "hex32"
    if re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        text,
        flags=re.IGNORECASE,
    ):
        return "uuid"
    return "other"
