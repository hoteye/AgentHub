from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import Any

from . import tasks_execution_runtime
from .models import TaskEnvelope
from .storage import BackgroundTaskStorage


_SMOKE_PROFILE_PRESETS: dict[str, dict[str, Any]] = {
    "multi_llm_regression": {
        "kind": "multi_llm_live_cases",
        "argv": [
            "--profile",
            "orchestration_smoke",
            "--strict",
            "--provider",
            "openai",
            "--model",
            "gpt_54",
            "--reasoning-effort",
            "high",
        ],
    },
    "policy_helper_regression": {
        "kind": "policy_helper_live_cases",
        "argv": [
            "--provider",
            "glm",
            "--model",
            "glm_5",
            "--policy-helper-provider",
            "deepseek",
            "--policy-helper-model",
            "deepseek_chat",
            "--policy-helper-reasoning-effort",
            "low",
            "--policy-helper-timeout",
            "20",
        ],
    },
}


def resolve_smoke_profile_payload(
    payload: dict[str, Any],
    *,
    normalize_argv_fn: Any,
) -> tuple[dict[str, Any], str]:
    raw_payload = dict(payload or {})
    requested = str(raw_payload.get("profile") or raw_payload.get("preset") or "").strip().lower()
    raw_kind = str(raw_payload.get("kind") or raw_payload.get("suite") or "").strip().lower()
    if not requested and raw_kind in _SMOKE_PROFILE_PRESETS:
        requested = raw_kind
    preset = _SMOKE_PROFILE_PRESETS.get(requested)
    if not isinstance(preset, dict):
        return raw_payload, ""
    merged = dict(raw_payload)
    merged["kind"] = str(preset.get("kind") or "").strip() or str(raw_payload.get("kind") or "")
    preset_argv = normalize_argv_fn(preset.get("argv"))
    user_argv = normalize_argv_fn(raw_payload.get("argv"))
    merged["argv"] = [*preset_argv, *user_argv]
    merged["profile"] = requested
    return merged, requested


def run_benchmark_subprocess(
    envelope: TaskEnvelope,
    *,
    report_path: Path,
    cli_root: Path,
    benchmark_script_path: Path,
    cwd: Path | None = None,
    storage: BackgroundTaskStorage | None = None,
    runner_token: str = "",
    normalize_argv_fn: Any,
    task_timeout_seconds_fn: Any,
    worker_heartbeat_callback_fn: Any,
) -> Any:
    from .tasks import _run_logged_subprocess, BenchmarkRunResult

    payload = dict(envelope.payload or {})
    run_request = tasks_execution_runtime.build_benchmark_run_request(
        payload=payload,
        benchmark_script_path=benchmark_script_path,
        report_path=report_path,
        python_executable=sys.executable,
        normalize_argv_fn=normalize_argv_fn,
        task_timeout_seconds_fn=task_timeout_seconds_fn,
    )
    run = _run_logged_subprocess(
        envelope,
        command=run_request["command"],
        cwd=cwd or cli_root,
        storage=storage,
        runner_token=runner_token,
        log_prefix="benchmark",
        timeout_seconds=run_request["timeout_seconds"],
        heartbeat_callback=worker_heartbeat_callback_fn(storage=storage, envelope=envelope) if storage is not None else None,
    )
    return BenchmarkRunResult(
        returncode=int(run.returncode),
        command=list(run.command or []),
        report_path=report_path,
        stdout=str(run.stdout or ""),
        stderr=str(run.stderr or ""),
        cancelled=bool(run.cancelled),
        timed_out=bool(run.timed_out),
        timeout_seconds=run.timeout_seconds,
        cwd=str(run.cwd or ""),
        stdout_path=run.stdout_path,
        stderr_path=run.stderr_path,
    )


def invoke_benchmark_runner(
    envelope: TaskEnvelope,
    *,
    report_path: Path,
    storage: BackgroundTaskStorage,
    runner_token: str,
    cli_root: Path,
    benchmark_script_path: Path,
) -> Any:
    from . import tasks as tasks_module

    runner = tasks_module.run_benchmark_subprocess
    kwargs: dict[str, Any] = {"report_path": report_path}
    try:
        parameters = inspect.signature(runner).parameters
    except (TypeError, ValueError):
        parameters = {}
    if "cli_root" in parameters:
        kwargs["cli_root"] = cli_root
    if "benchmark_script_path" in parameters:
        kwargs["benchmark_script_path"] = benchmark_script_path
    if "cwd" in parameters:
        kwargs["cwd"] = None
    if "storage" in parameters:
        kwargs["storage"] = storage
    if "runner_token" in parameters:
        kwargs["runner_token"] = runner_token
    return runner(envelope, **kwargs)
