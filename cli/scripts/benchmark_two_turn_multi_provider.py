#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    from cli.scripts.benchmark_two_turn_output_helpers import (
        health_for_case as _health_for_case,
        print_table as _print_table,
        summary_for_results as _summary_for_results,
        turn_payload as _turn_payload,
    )
    from cli.scripts.benchmark_two_turn_worker_helpers import (
        BenchmarkCase,
        common_worker_command as _common_worker_command_impl,
        default_cases as _default_cases,
        decode_worker_payload as _decode_worker_payload,
        parse_case as _parse_case,
    )
except ModuleNotFoundError:
    from benchmark_two_turn_output_helpers import (  # type: ignore[no-redef]
        health_for_case as _health_for_case,
        print_table as _print_table,
        summary_for_results as _summary_for_results,
        turn_payload as _turn_payload,
    )
    from benchmark_two_turn_worker_helpers import (  # type: ignore[no-redef]
        BenchmarkCase,
        common_worker_command as _common_worker_command_impl,
        default_cases as _default_cases,
        decode_worker_payload as _decode_worker_payload,
        parse_case as _parse_case,
    )


CLI_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CLI_ROOT.parent
DEFAULT_TIMEOUT_SECONDS = 90.0
DEFAULT_MAX_WORKERS = 4
DEFAULT_FIRST_PROMPT = "今天几号？"
DEFAULT_SECOND_PROMPT = "明天呢？"
DEFAULT_TIMEZONE = "Asia/Shanghai"
def _ensure_import_paths() -> None:
    for candidate in (str(REPO_ROOT), str(CLI_ROOT)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)


_ensure_import_paths()

from cli.scripts.script_runtime_helpers import (
    normalize_optional_provider_home_override,
    resolve_effective_script_provider_home_dir,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/benchmark_two_turn_multi_provider.py",
        description="Run a concurrent two-turn benchmark across multiple provider:model pairs.",
    )
    parser.add_argument(
        "--case",
        action="append",
        type=_parse_case,
        dest="cases",
        help="Benchmark case in provider:model form. Repeat to override defaults.",
    )
    parser.add_argument(
        "--first-prompt",
        default=DEFAULT_FIRST_PROMPT,
        help=f"First-turn prompt. Defaults to {DEFAULT_FIRST_PROMPT!r}.",
    )
    parser.add_argument(
        "--second-prompt",
        default=DEFAULT_SECOND_PROMPT,
        help=f"Second-turn prompt. Defaults to {DEFAULT_SECOND_PROMPT!r}.",
    )
    parser.add_argument(
        "--timezone",
        default=DEFAULT_TIMEZONE,
        help=f"Timezone used for expected date checks. Defaults to {DEFAULT_TIMEZONE}.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-case timeout in seconds. Defaults to {DEFAULT_TIMEOUT_SECONDS:g}.",
    )
    parser.add_argument(
        "--provider-home",
        default="",
        help=(
            "Optional provider runtime home override passed via AGENTHUB_PROVIDER_HOME. "
            "Defaults to runtime-managed provider home resolution."
        ),
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help=f"Max concurrent worker subprocesses. Defaults to {DEFAULT_MAX_WORKERS}.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the default table summary.",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Optional path to write the full JSON report.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the worker commands without executing requests.",
    )
    parser.add_argument(
        "--worker",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--provider",
        default="",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--model",
        default="",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--current-datetime",
        default="",
        help=argparse.SUPPRESS,
    )
    return parser


def _common_worker_command(
    case: BenchmarkCase,
    *,
    first_prompt: str,
    second_prompt: str,
    timezone_name: str,
    current_datetime: str,
    provider_home: str,
) -> list[str]:
    return _common_worker_command_impl(
        case,
        script_path=Path(__file__).resolve(),
        first_prompt=first_prompt,
        second_prompt=second_prompt,
        timezone_name=timezone_name,
        current_datetime=current_datetime,
        provider_home=provider_home,
    )


def _provider_home_report_fields(provider_home: str) -> dict[str, str]:
    normalized_provider_home = normalize_optional_provider_home_override(provider_home)
    return {
        "provider_home": str(
            resolve_effective_script_provider_home_dir(
                cwd=CLI_ROOT,
                provider_home=normalized_provider_home,
            )
        ),
        "provider_home_override": normalized_provider_home,
        "provider_home_source": "explicit_override" if normalized_provider_home else "runtime_default",
    }


def _run_worker(args: argparse.Namespace) -> int:
    _ensure_import_paths()
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
        **_provider_home_report_fields(str(args.provider_home or "")),
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


def _run_case_subprocess(
    case: BenchmarkCase,
    *,
    first_prompt: str,
    second_prompt: str,
    timezone_name: str,
    current_datetime: str,
    timeout_seconds: float,
    provider_home: str,
) -> dict[str, Any]:
    command = _common_worker_command(
        case,
        first_prompt=first_prompt,
        second_prompt=second_prompt,
        timezone_name=timezone_name,
        current_datetime=current_datetime,
        provider_home=provider_home,
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
        completed = subprocess.run(
            command,
            cwd=str(CLI_ROOT),
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


def _orchestrate(args: argparse.Namespace) -> int:
    if args.timeout <= 0:
        raise SystemExit("--timeout must be greater than zero")
    if args.max_workers <= 0:
        raise SystemExit("--max-workers must be greater than zero")

    try:
        zone = ZoneInfo(str(args.timezone))
    except ZoneInfoNotFoundError as exc:
        raise SystemExit(f"unknown timezone: {args.timezone}") from exc

    cases = list(args.cases or _default_cases())
    fixed_now = datetime.now(zone).replace(microsecond=0)
    current_datetime = fixed_now.isoformat()

    if args.dry_run:
        payload = {
            "cwd": str(CLI_ROOT),
            **_provider_home_report_fields(str(args.provider_home or "")),
            "timezone": str(args.timezone),
            "current_datetime": current_datetime,
            "first_prompt": args.first_prompt,
            "second_prompt": args.second_prompt,
            "max_workers": args.max_workers,
            "timeout_seconds": args.timeout,
            "cases": [
                {
                    "provider": case.provider,
                    "model": case.model,
                    "env": case.env_overrides(provider_home=str(args.provider_home)),
                    "command": _common_worker_command(
                        case,
                        first_prompt=args.first_prompt,
                        second_prompt=args.second_prompt,
                        timezone_name=str(args.timezone),
                        current_datetime=current_datetime,
                        provider_home=str(args.provider_home),
                    ),
                }
                for case in cases
            ],
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("Dry run")
            for item in payload["cases"]:
                print(f"- {item['provider']}:{item['model']}")
        return 0

    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(args.max_workers, len(cases))) as executor:
        future_map = {
            executor.submit(
                _run_case_subprocess,
                case,
                first_prompt=str(args.first_prompt),
                second_prompt=str(args.second_prompt),
                timezone_name=str(args.timezone),
                current_datetime=current_datetime,
                timeout_seconds=float(args.timeout),
                provider_home=str(args.provider_home),
            ): case
            for case in cases
        }
        for future in as_completed(future_map):
            case = future_map[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(
                    {
                        "provider": case.provider,
                        "model": case.model,
                        "health": "error",
                        "exception": f"{type(exc).__name__}: {exc}",
                    }
                )

    results.sort(key=lambda item: (str(item.get("provider") or ""), str(item.get("model") or "")))
    report = {
        **_provider_home_report_fields(str(args.provider_home or "")),
        "timezone": str(args.timezone),
        "current_datetime": current_datetime,
        "first_prompt": str(args.first_prompt),
        "second_prompt": str(args.second_prompt),
        "timeout_seconds": float(args.timeout),
        "max_workers": int(args.max_workers),
        "orchestrator_wall_ms": int((time.perf_counter() - started) * 1000),
        "cases": [{"provider": case.provider, "model": case.model} for case in cases],
        "results": results,
        "summary": _summary_for_results(results),
    }
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_table(results)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.worker:
        return _run_worker(args)
    return _orchestrate(args)


if __name__ == "__main__":
    raise SystemExit(main())
