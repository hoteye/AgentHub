from __future__ import annotations

import json
import os
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
    "CODEX_PROVIDER_OVERRIDE",
    "BENCH_MODEL",
    "BENCH_REASONING_EFFORT",
)

DEFAULT_PROMPT = (
    "当前目录是空的。请创建一个最小 Python 脚本 `ticker.py`，要求：\n"
    "- 启动后每隔 0.2 秒打印一行 `tick N`\n"
    "- 接收到 stdin 的 `stop` 后打印 `stopped` 并退出\n"
    "- 然后实际运行它，确认它开始输出，再停止它\n"
    "- 最后只汇报你创建了哪些文件，以及运行是否成功。\n"
    "请直接执行，不要只给方案。"
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


@dataclass(frozen=True)
class AgentHubConfigSelection:
    config_path: Path
    auth_path: Path
    agent_cli_home: Path | None
    provider_home: Path


@dataclass
class RunSummary:
    harness_root: str
    prompt_preview: str
    dry_run: bool
    openai_base_url: str
    model: str
    reasoning_effort: str
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
    agenthub_run: dict[str, Any]
    codex_run: dict[str, Any]
    log_manifest: dict[str, str]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _prompt_preview(prompt: str, limit: int = 240) -> str:
    normalized = " ".join(str(prompt or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3] + "..."


def _env_snapshot(env: dict[str, str]) -> dict[str, str]:
    payload: dict[str, str] = {}
    for key in SNAPSHOT_ENV_KEYS:
        value = str(env.get(key, "") or "").strip()
        if not value:
            continue
        payload[key] = "<redacted>" if key.endswith("_API_KEY") else value
    return payload


def _auth_snapshot(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {"path": str(path), "exists": path.exists()}
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
    payload: dict[str, Any] = {"path": str(path), "exists": path.exists()}
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
    for path in sorted(candidate for candidate in workspace.rglob("*") if candidate.is_file()):
        entries.append({"path": str(path.relative_to(workspace)), "size": path.stat().st_size})
    return entries


def _load_api_key(auth_json: Path, key_name: str) -> str:
    env_value = str(os.environ.get(key_name) or "").strip()
    if env_value:
        return env_value
    payload = json.loads(auth_json.read_text(encoding="utf-8"))
    value = str(payload.get(key_name) or "").strip()
    if value:
        return value
    raise SystemExit(f"missing API key `{key_name}` in env or {auth_json}")
