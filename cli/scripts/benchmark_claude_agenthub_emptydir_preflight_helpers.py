from __future__ import annotations

import argparse
import shlex
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

try:
    from cli.scripts.benchmark_claude_agenthub_emptydir_config_helpers import (
        CLI_ROOT,
        REPO_ROOT,
        DEFAULT_PREFLIGHT_PROMPT,
    )
    from cli.scripts.benchmark_claude_agenthub_emptydir_reporting_helpers import (
        _agenthub_preflight_checks,
        _checks_passed,
        _claude_preflight_checks,
        _parse_agenthub_output,
        _parse_claude_output,
        _preflight_system_report,
    )
    from cli.scripts.benchmark_claude_agenthub_emptydir_runtime_helpers import (
        TimelineLogger,
        _build_agenthub_command,
        _build_agenthub_env,
        _build_claude_command,
        _build_claude_env,
        _run_command,
    )
    from cli.scripts.script_runtime_helpers import apply_provider_home_override_env
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from benchmark_claude_agenthub_emptydir_config_helpers import (  # type: ignore[no-redef]
        CLI_ROOT,
        REPO_ROOT,
        DEFAULT_PREFLIGHT_PROMPT,
    )
    from benchmark_claude_agenthub_emptydir_reporting_helpers import (  # type: ignore[no-redef]
        _agenthub_preflight_checks,
        _checks_passed,
        _claude_preflight_checks,
        _parse_agenthub_output,
        _parse_claude_output,
        _preflight_system_report,
    )
    from benchmark_claude_agenthub_emptydir_runtime_helpers import (  # type: ignore[no-redef]
        TimelineLogger,
        _build_agenthub_command,
        _build_agenthub_env,
        _build_claude_command,
        _build_claude_env,
        _run_command,
    )
    from script_runtime_helpers import apply_provider_home_override_env  # type: ignore[no-redef]


def _planned_agenthub_env(args: argparse.Namespace) -> dict[str, str]:
    env = {
        "AGENT_CLI_PROVIDER": str(args.agenthub_provider),
        "AGENT_CLI_MODEL": str(args.agenthub_model),
    }
    return apply_provider_home_override_env(env, provider_home=args.agenthub_provider_home)


def _execute_preflight_system(
    *,
    system_name: str,
    command: list[str],
    env: dict[str, str],
    cwd: Path,
    system_root: Path,
    timeout_seconds: int,
    logger: TimelineLogger | None = None,
) -> dict[str, Any]:
    if logger is not None:
        logger.emit(
            "preflight.system.started",
            system=system_name,
            cwd=str(cwd),
            run_command=list(command),
            run_command_shell=shlex.join(command),
            timeout_seconds=int(timeout_seconds),
        )
    run_result = _run_command(
        name=f"preflight.{system_name}",
        command=command,
        cwd=cwd,
        env=env,
        stdout_path=system_root / "stdout.json",
        stderr_path=system_root / "stderr.log",
        timeout_seconds=timeout_seconds,
        logger=logger,
        event_context={"phase": "preflight", "system": system_name},
    )
    parsed = (
        _parse_agenthub_output(Path(run_result.stdout_path))
        if system_name == "agenthub"
        else _parse_claude_output(Path(run_result.stdout_path))
    )
    checks = _agenthub_preflight_checks(parsed) if system_name == "agenthub" else _claude_preflight_checks(parsed)
    payload = {
        "system": system_name,
        "cwd": str(cwd),
        "run": asdict(run_result),
        "assistant_text": str(parsed.get("assistant_text") or ""),
        "parsed_output": parsed,
        "checks": checks,
        "passed": int(run_result.exit_code) == 0 and not run_result.timed_out and _checks_passed(checks),
    }
    if logger is not None:
        logger.emit(
            "preflight.system.completed",
            system=system_name,
            exit_code=int(run_result.exit_code),
            timed_out=bool(run_result.timed_out),
            elapsed_seconds=float(run_result.elapsed_seconds),
            passed=bool(payload["passed"]),
            checks=checks,
            assistant_text=str(payload["assistant_text"]),
        )
    return payload


def _run_preflight(
    args: argparse.Namespace,
    *,
    out_dir: Path,
    logger: TimelineLogger | None = None,
    execute_preflight_system_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    preflight_root = out_dir / "preflight"
    agenthub_command = _build_agenthub_command(prompt=DEFAULT_PREFLIGHT_PROMPT, args=args)
    claude_command = _build_claude_command(prompt=DEFAULT_PREFLIGHT_PROMPT, args=args)
    if logger is not None:
        logger.emit(
            "preflight.started",
            prompt=DEFAULT_PREFLIGHT_PROMPT,
            out_dir=str(preflight_root),
        )
    if args.dry_run:
        payload = {
            "executed": False,
            "passed": None,
            "prompt": DEFAULT_PREFLIGHT_PROMPT,
            "systems": {
                "agenthub": _preflight_system_report(
                    system_name="agenthub",
                    command=agenthub_command,
                    env_overrides=_planned_agenthub_env(args),
                    cwd=CLI_ROOT,
                ),
                "claude": _preflight_system_report(
                    system_name="claude",
                    command=claude_command,
                    env_overrides={},
                    cwd=REPO_ROOT,
                ),
            },
        }
        if logger is not None:
            logger.emit(
                "preflight.planned",
                prompt=DEFAULT_PREFLIGHT_PROMPT,
                systems=list((payload.get("systems") or {}).keys()),
            )
        return payload

    jobs = [
        {
            "system_name": "agenthub",
            "command": agenthub_command,
            "env": _build_agenthub_env(args),
            "cwd": CLI_ROOT,
            "system_root": preflight_root / "agenthub",
            "timeout_seconds": int(args.timeout_seconds),
            "logger": logger,
        },
        {
            "system_name": "claude",
            "command": claude_command,
            "env": _build_claude_env(),
            "cwd": REPO_ROOT,
            "system_root": preflight_root / "claude",
            "timeout_seconds": int(args.timeout_seconds),
            "logger": logger,
        },
    ]
    systems: dict[str, dict[str, Any]] = {}
    runner = execute_preflight_system_fn or _execute_preflight_system
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                runner,
                system_name=str(job["system_name"]),
                command=list(job["command"]),
                env=dict(job["env"]),
                cwd=job["cwd"],
                system_root=job["system_root"],
                timeout_seconds=int(job["timeout_seconds"]),
                logger=job.get("logger"),
            )
            for job in jobs
        ]
        for future in futures:
            payload = future.result()
            systems[str(payload["system"])] = payload
    payload = {
        "executed": True,
        "passed": bool(systems.get("agenthub", {}).get("passed")) and bool(systems.get("claude", {}).get("passed")),
        "prompt": DEFAULT_PREFLIGHT_PROMPT,
        "systems": systems,
    }
    if logger is not None:
        logger.emit(
            "preflight.completed",
            passed=bool(payload["passed"]),
            systems={key: bool((value or {}).get("passed")) for key, value in systems.items()},
        )
    return payload
