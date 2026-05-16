from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from cli.scripts.benchmark_two_turn_output_helpers import (
        health_for_case as _health_for_case,
    )
    from cli.scripts.benchmark_two_turn_output_helpers import (
        turn_payload as _turn_payload,
    )
    from cli.scripts.benchmark_two_turn_worker_helpers import (
        BenchmarkCase,
    )
    from cli.scripts.benchmark_two_turn_worker_helpers import (
        common_worker_command as _common_worker_command_impl,
    )
    from cli.scripts.benchmark_two_turn_worker_helpers import (
        decode_worker_payload as _decode_worker_payload,
    )
    from cli.scripts.script_runtime_helpers import (
        normalize_optional_provider_home_override,
        resolve_effective_script_provider_home_dir,
    )
except ModuleNotFoundError:
    from benchmark_two_turn_output_helpers import (  # type: ignore[no-redef]
        health_for_case as _health_for_case,
    )
    from benchmark_two_turn_output_helpers import (
        turn_payload as _turn_payload,
    )
    from benchmark_two_turn_worker_helpers import (  # type: ignore[no-redef]
        BenchmarkCase,
    )
    from benchmark_two_turn_worker_helpers import (
        common_worker_command as _common_worker_command_impl,
    )
    from benchmark_two_turn_worker_helpers import (
        decode_worker_payload as _decode_worker_payload,
    )
    from script_runtime_helpers import (  # type: ignore[no-redef]
        normalize_optional_provider_home_override,
        resolve_effective_script_provider_home_dir,
    )


CLI_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CLI_ROOT.parent
MAIN_SCRIPT_PATH = Path(__file__).resolve().with_name("benchmark_two_turn_multi_provider.py")


def ensure_import_paths() -> None:
    for candidate in (str(REPO_ROOT), str(CLI_ROOT)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)


def common_worker_command(
    case: BenchmarkCase,
    *,
    first_prompt: str,
    second_prompt: str,
    timezone_name: str,
    current_datetime: str,
    provider_home: str,
    script_path: Path = MAIN_SCRIPT_PATH,
) -> list[str]:
    return _common_worker_command_impl(
        case,
        script_path=script_path,
        first_prompt=first_prompt,
        second_prompt=second_prompt,
        timezone_name=timezone_name,
        current_datetime=current_datetime,
        provider_home=provider_home,
    )


def provider_home_report_fields(
    provider_home: str,
    *,
    cwd: Path = CLI_ROOT,
    resolve_provider_home_dir: Callable[..., Path] = resolve_effective_script_provider_home_dir,
) -> dict[str, str]:
    normalized_provider_home = normalize_optional_provider_home_override(provider_home)
    return {
        "provider_home": str(
            resolve_provider_home_dir(
                cwd=cwd,
                provider_home=normalized_provider_home,
            )
        ),
        "provider_home_override": normalized_provider_home,
        "provider_home_source": (
            "explicit_override" if normalized_provider_home else "runtime_default"
        ),
    }


def run_worker(
    args: Any,
    *,
    provider_home_reporter: Callable[[str], dict[str, str]] = provider_home_report_fields,
) -> int:
    ensure_import_paths()
    from cli.agent_cli.runtime import AgentCliRuntime
    from cli.agent_cli.runtime_policy import RuntimePolicy

    case = BenchmarkCase(provider=str(args.provider).strip(), model=str(args.model).strip())
    if not case.provider or not case.model:
        raise SystemExit("worker requires --provider and --model")

    provider_home_override = normalize_optional_provider_home_override(args.provider_home)
    for name, value in case.env_overrides(provider_home=provider_home_override).items():
        os.environ[name] = value

    fixed_now = datetime.fromisoformat(str(args.current_datetime).strip())
    timezone_name = str(args.timezone or "").strip()
    expected_today = fixed_now
    expected_tomorrow = fixed_now + timedelta(days=1)
    started = time.perf_counter()
    payload: dict[str, Any] = {
        "provider": case.provider,
        "model": case.model,
        "timezone": timezone_name,
        "current_datetime": fixed_now.isoformat(),
        **provider_home_reporter(str(args.provider_home or "")),
    }
    try:
        runtime = AgentCliRuntime(
            runtime_policy=RuntimePolicy.normalized(
                approval_policy="never",
                sandbox_mode="workspace-write",
                web_search_mode="live",
                network_access_enabled=True,
            ),
            current_dt_provider=lambda: fixed_now,
        )
        first_response = runtime.handle_prompt(str(args.first_prompt))
        second_response = runtime.handle_prompt(str(args.second_prompt))
        provider_status = dict(runtime.agent.provider_status() or {})
        payload.update(
            {
                "provider_ready": provider_status.get("provider_ready"),
                "provider_name": provider_status.get("provider_name"),
                "provider_model": provider_status.get("provider_model"),
                "provider_runtime_state": provider_status.get("provider_runtime_state"),
                "provider_label": provider_status.get("provider_label"),
                "turns": [
                    _turn_payload(
                        prompt=str(args.first_prompt),
                        response=first_response,
                        expected_date=expected_today,
                    ),
                    _turn_payload(
                        prompt=str(args.second_prompt),
                        response=second_response,
                        expected_date=expected_tomorrow,
                    ),
                ],
            }
        )
        payload["health"] = _health_for_case(payload)
        payload["wall_ms"] = int((time.perf_counter() - started) * 1000)
    except Exception as exc:
        payload["health"] = "error"
        payload["exception"] = f"{type(exc).__name__}: {exc}"
        payload["wall_ms"] = int((time.perf_counter() - started) * 1000)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def run_case_subprocess(
    case: BenchmarkCase,
    *,
    first_prompt: str,
    second_prompt: str,
    timezone_name: str,
    current_datetime: str,
    timeout_seconds: float,
    provider_home: str,
    cwd: Path = CLI_ROOT,
    run_command: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    script_path: Path = MAIN_SCRIPT_PATH,
) -> dict[str, Any]:
    command = common_worker_command(
        case,
        first_prompt=first_prompt,
        second_prompt=second_prompt,
        timezone_name=timezone_name,
        current_datetime=current_datetime,
        provider_home=provider_home,
        script_path=script_path,
    )
    env = dict(os.environ)
    env.update(case.env_overrides(provider_home=provider_home))
    started = time.perf_counter()
    result: dict[str, Any] = {
        "provider": case.provider,
        "model": case.model,
        "command": command,
    }
    try:
        completed = run_command(
            command,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        result["timeout"] = True
        result["health"] = "error"
        result["wall_ms"] = int((time.perf_counter() - started) * 1000)
        result["stdout_preview"] = str(exc.stdout or "").strip()[:400]
        result["stderr"] = str(exc.stderr or "").strip()[:400]
        return result

    result["exit_code"] = int(completed.returncode)
    result["wall_ms"] = int((time.perf_counter() - started) * 1000)
    result["stderr"] = completed.stderr.strip()[:400]
    try:
        payload = _decode_worker_payload(completed.stdout)
    except json.JSONDecodeError as exc:
        result["health"] = "error"
        result["parse_error"] = f"{type(exc).__name__}: {exc}"
        result["stdout_preview"] = completed.stdout.strip()[:400]
        return result

    payload.setdefault("command", command)
    payload["worker_wall_ms"] = payload.get("wall_ms")
    payload["orchestrator_wall_ms"] = result["wall_ms"]
    return payload
