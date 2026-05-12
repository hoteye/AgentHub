from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .models import BackgroundTaskStatus, TaskResult
from .tasks_execution_runtime import teammate_running_snapshot_path
from .tasks_stream_helpers_runtime import (
    resolve_dispatch_runner_pid,
    resolve_running_log_path,
    running_snapshot_process_info,
)
from .tasks_stream_runtime_helpers import (
    consume_teammate_stdout_line,
    ensure_teammate_running_snapshot,
    worker_heartbeat_callback,
    _resolve_dispatch_runner_pid,
    _resolve_running_log_path,
)

_COMMAND_POLICY_MODE_ENV = "AGENT_CLI_COMMAND_POLICY_MODE"
_TEST_POLICY_ENV = "AGENT_CLI_TEST_POLICY"
_TEST_LOCK_PATH_ENV = "AGENT_CLI_TEST_LOCK_PATH"
_BACKGROUND_TEAMMATE_COMMAND_POLICY_MODE = "background_teammate"
_BACKGROUND_TEAMMATE_TEST_POLICY = "scoped_only"
_TEST_LOCK_PATH = Path.home() / ".agent_cli" / "locks" / "test_commands.lock"


def build_teammate_subprocess_request(
    *,
    cli_root: Path,
    payload: dict[str, Any],
    sandbox_mode: str,
    task_text: str,
    provider: str,
    model: str,
    reasoning_effort: str,
    response_sidecar_path: Path,
    os_environ: dict[str, str],
    python_executable: str,
    response_path_env_name: str,
) -> dict[str, Any]:
    command = [
        python_executable,
        str(cli_root / "agent_cli" / "__main__.py"),
        "--headless",
        "--jsonl",
        "--approval-policy",
        str(payload.get("approval_policy") or "never"),
        "--sandbox-mode",
        sandbox_mode,
        "--prompt",
        task_text,
    ]
    env = dict(os_environ)
    if provider:
        env["AGENT_CLI_PROVIDER"] = provider
    if model:
        env["AGENT_CLI_MODEL"] = model
    if reasoning_effort:
        env["AGENT_CLI_REASONING_EFFORT"] = reasoning_effort
    env[response_path_env_name] = str(response_sidecar_path)
    env[_COMMAND_POLICY_MODE_ENV] = _BACKGROUND_TEAMMATE_COMMAND_POLICY_MODE
    env[_TEST_POLICY_ENV] = _BACKGROUND_TEAMMATE_TEST_POLICY
    env[_TEST_LOCK_PATH_ENV] = str(_TEST_LOCK_PATH)
    return {
        "command": command,
        "env": env,
    }


def load_headless_response_payload(
    *,
    response_sidecar_path: Path,
    stdout_text: str,
    stream_state: dict[str, Any],
    decode_json_text_fn: Callable[[str], dict[str, Any] | None],
    synthetic_response_payload_fn: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    if response_sidecar_path.exists():
        try:
            payload = json.loads(response_sidecar_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict):
            return payload
    parsed_stdout = decode_json_text_fn(stdout_text)
    if isinstance(parsed_stdout, dict):
        return parsed_stdout
    return synthetic_response_payload_fn(stream_state)
