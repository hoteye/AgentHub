from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from cli.scripts.probe_native_web_search_cases import ProbeCase
from cli.scripts.script_runtime_helpers import normalize_optional_provider_home_override


def common_worker_command(
    case: ProbeCase,
    *,
    script_path: Path,
    query: str,
    timeout_seconds: float,
    provider_home: str,
) -> list[str]:
    command = [
        sys.executable,
        str(script_path),
        "--worker",
        "--provider",
        case.provider,
        "--model",
        case.model,
        "--query",
        query,
        "--timeout",
        str(timeout_seconds),
    ]
    normalized_provider_home = normalize_optional_provider_home_override(provider_home)
    if normalized_provider_home:
        command.extend(["--provider-home", normalized_provider_home])
    return command


def run_case_subprocess(
    case: ProbeCase,
    *,
    cli_root: Path,
    script_path: Path,
    query: str,
    timeout_seconds: float,
    provider_home: str,
    response_text_preview_fn: Callable[[Any], str],
) -> dict[str, Any]:
    command = common_worker_command(
        case,
        script_path=script_path,
        query=query,
        timeout_seconds=timeout_seconds,
        provider_home=provider_home,
    )
    env = dict(os.environ)
    env.update(case.env_overrides(provider_home=provider_home))
    started_at = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=cli_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=max(1.0, float(timeout_seconds) + 2.0),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "case": case.label,
            "provider": case.provider,
            "model": case.model,
            "status": "error",
            "confidence": "high",
            "issue": f"worker timed out after {float(timeout_seconds):g}s",
            "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
        }
    stdout_text = str(completed.stdout or "").strip()
    if completed.returncode != 0:
        return {
            "case": case.label,
            "provider": case.provider,
            "model": case.model,
            "status": "error",
            "confidence": "high",
            "issue": response_text_preview_fn(completed.stderr or stdout_text or f"worker exited {completed.returncode}"),
            "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
        }
    try:
        payload = json.loads(stdout_text.splitlines()[-1])
    except Exception as exc:
        return {
            "case": case.label,
            "provider": case.provider,
            "model": case.model,
            "status": "error",
            "confidence": "high",
            "issue": f"failed to parse worker JSON: {exc}",
            "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
            "stdout_preview": response_text_preview_fn(stdout_text),
        }
    if not isinstance(payload, dict):
        payload = {
            "case": case.label,
            "provider": case.provider,
            "model": case.model,
            "status": "error",
            "issue": "worker returned non-object JSON",
        }
    payload.setdefault("case", case.label)
    payload.setdefault("provider", case.provider)
    payload.setdefault("model", case.model)
    payload.setdefault("elapsed_ms", int((time.perf_counter() - started_at) * 1000))
    return payload
