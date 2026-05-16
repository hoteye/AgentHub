#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    from cli.scripts.benchmark_two_turn_multi_provider_worker_runtime import (
        common_worker_command as _common_worker_command_impl,
    )
    from cli.scripts.benchmark_two_turn_multi_provider_worker_runtime import (
        provider_home_report_fields as _provider_home_report_fields_impl,
    )
    from cli.scripts.benchmark_two_turn_multi_provider_worker_runtime import (
        run_case_subprocess as _run_case_subprocess_impl,
    )
    from cli.scripts.benchmark_two_turn_multi_provider_worker_runtime import (
        run_worker as _run_worker_impl,
    )
    from cli.scripts.benchmark_two_turn_output_helpers import (
        print_table as _print_table,
    )
    from cli.scripts.benchmark_two_turn_output_helpers import (
        summary_for_results as _summary_for_results,
    )
    from cli.scripts.benchmark_two_turn_worker_helpers import (
        BenchmarkCase,
    )
    from cli.scripts.benchmark_two_turn_worker_helpers import (
        default_cases as _default_cases,
    )
    from cli.scripts.benchmark_two_turn_worker_helpers import (
        parse_case as _parse_case,
    )
    from cli.scripts.script_runtime_helpers import resolve_effective_script_provider_home_dir
except ModuleNotFoundError:
    from benchmark_two_turn_multi_provider_worker_runtime import (  # type: ignore[no-redef]
        common_worker_command as _common_worker_command_impl,
    )
    from benchmark_two_turn_multi_provider_worker_runtime import (
        provider_home_report_fields as _provider_home_report_fields_impl,
    )
    from benchmark_two_turn_multi_provider_worker_runtime import (
        run_case_subprocess as _run_case_subprocess_impl,
    )
    from benchmark_two_turn_multi_provider_worker_runtime import (
        run_worker as _run_worker_impl,
    )
    from benchmark_two_turn_output_helpers import (  # type: ignore[no-redef]
        print_table as _print_table,
    )
    from benchmark_two_turn_output_helpers import (
        summary_for_results as _summary_for_results,
    )
    from benchmark_two_turn_worker_helpers import (  # type: ignore[no-redef]
        BenchmarkCase,
    )
    from benchmark_two_turn_worker_helpers import (
        default_cases as _default_cases,
    )
    from benchmark_two_turn_worker_helpers import (
        parse_case as _parse_case,
    )
    from script_runtime_helpers import (
        resolve_effective_script_provider_home_dir,  # type: ignore[no-redef]
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
        first_prompt=first_prompt,
        second_prompt=second_prompt,
        timezone_name=timezone_name,
        current_datetime=current_datetime,
        provider_home=provider_home,
        script_path=Path(__file__).resolve(),
    )


def _provider_home_report_fields(provider_home: str) -> dict[str, str]:
    return _provider_home_report_fields_impl(
        provider_home,
        cwd=CLI_ROOT,
        resolve_provider_home_dir=resolve_effective_script_provider_home_dir,
    )


def _run_worker(args: argparse.Namespace) -> int:
    return _run_worker_impl(args, provider_home_reporter=_provider_home_report_fields)


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
    return _run_case_subprocess_impl(
        case,
        first_prompt=first_prompt,
        second_prompt=second_prompt,
        timezone_name=timezone_name,
        current_datetime=current_datetime,
        timeout_seconds=timeout_seconds,
        provider_home=provider_home,
        cwd=CLI_ROOT,
        run_command=subprocess.run,
        script_path=Path(__file__).resolve(),
    )


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
        Path(args.out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
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
