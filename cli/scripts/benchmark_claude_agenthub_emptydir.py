#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from cli.scripts.benchmark_claude_agenthub_emptydir_config_helpers import (
        CLI_ROOT,
        REPO_ROOT,
        DEFAULT_PREFLIGHT_PROMPT,
        BenchmarkTask,
        ValidationSpec,
        _agenthub_provider_home_report_fields,
        _default_tasks,
        _print_task_list,
        _resolve_tasks,
        build_parser,
    )
    from cli.scripts.benchmark_claude_agenthub_emptydir_preflight_helpers import (
        _execute_preflight_system,
        _planned_agenthub_env,
        _run_preflight as _run_preflight_impl,
    )
    from cli.scripts.benchmark_claude_agenthub_emptydir_execution_helpers import (
        _execute_system,
        _execute_system_job,
        _run_task as _run_task_impl,
    )
    from cli.scripts.benchmark_claude_agenthub_emptydir_reporting_helpers import (
        _DIAGNOSTIC_FIELD_DEFAULTS,
        _agenthub_output_defaults,
        _agenthub_preflight_checks,
        _artifact_quality_notes,
        _checks_passed,
        _claude_output_defaults,
        _claude_preflight_checks,
        _diagnostic_defaults,
        _dry_run_system_report,
        _flatten_diagnostics,
        _parse_agenthub_output,
        _parse_claude_output,
        _preflight_system_report,
        _prompt_preview,
        _render_console_summary,
        _report_task_entry,
        _scoreboard_rows,
        _short_reply_ok,
        _write_summary_markdown,
    )
    from cli.scripts.benchmark_claude_agenthub_emptydir_runtime_helpers import (
        CommandResult,
        TimelineLogger,
        _build_agenthub_command,
        _build_agenthub_env,
        _build_claude_command,
        _build_claude_env,
        _ensure_task_layout,
        _missing_expected_files,
        _run_command,
        _run_validation,
        _validation_passed,
        _write_text,
        _write_workspace_tree,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from benchmark_claude_agenthub_emptydir_config_helpers import (  # type: ignore[no-redef]
        CLI_ROOT,
        REPO_ROOT,
        DEFAULT_PREFLIGHT_PROMPT,
        BenchmarkTask,
        ValidationSpec,
        _agenthub_provider_home_report_fields,
        _default_tasks,
        _print_task_list,
        _resolve_tasks,
        build_parser,
    )
    from benchmark_claude_agenthub_emptydir_preflight_helpers import (  # type: ignore[no-redef]
        _execute_preflight_system,
        _planned_agenthub_env,
        _run_preflight as _run_preflight_impl,
    )
    from benchmark_claude_agenthub_emptydir_execution_helpers import (  # type: ignore[no-redef]
        _execute_system,
        _execute_system_job,
        _run_task as _run_task_impl,
    )
    from benchmark_claude_agenthub_emptydir_reporting_helpers import (  # type: ignore[no-redef]
        _DIAGNOSTIC_FIELD_DEFAULTS,
        _agenthub_output_defaults,
        _agenthub_preflight_checks,
        _artifact_quality_notes,
        _checks_passed,
        _claude_output_defaults,
        _claude_preflight_checks,
        _diagnostic_defaults,
        _dry_run_system_report,
        _flatten_diagnostics,
        _parse_agenthub_output,
        _parse_claude_output,
        _preflight_system_report,
        _prompt_preview,
        _render_console_summary,
        _report_task_entry,
        _scoreboard_rows,
        _short_reply_ok,
        _write_summary_markdown,
    )
    from benchmark_claude_agenthub_emptydir_runtime_helpers import (  # type: ignore[no-redef]
        CommandResult,
        TimelineLogger,
        _build_agenthub_command,
        _build_agenthub_env,
        _build_claude_command,
        _build_claude_env,
        _ensure_task_layout,
        _missing_expected_files,
        _run_command,
        _run_validation,
        _validation_passed,
        _write_text,
        _write_workspace_tree,
    )


def _run_preflight(args: argparse.Namespace, *, out_dir: Path, logger: TimelineLogger | None = None) -> dict[str, Any]:
    return _run_preflight_impl(
        args,
        out_dir=out_dir,
        logger=logger,
        execute_preflight_system_fn=_execute_preflight_system,
    )


def _run_task(
    task: BenchmarkTask,
    *,
    root: Path,
    args: argparse.Namespace,
    logger: TimelineLogger | None = None,
) -> dict[str, Any]:
    return _run_task_impl(
        task,
        root=root,
        args=args,
        logger=logger,
        execute_system_fn=_execute_system,
    )

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if int(args.timeout_seconds) <= 0:
        parser.error("--timeout-seconds must be greater than zero")
    if int(args.validation_timeout_seconds) <= 0:
        parser.error("--validation-timeout-seconds must be greater than zero")
    if int(args.task_workers) <= 0:
        parser.error("--task-workers must be greater than zero")
    try:
        tasks = _resolve_tasks(args.tasks)
    except ValueError as exc:
        parser.error(str(exc))
    if args.list_tasks:
        _print_task_list(tasks if args.tasks else _default_tasks())
        return 0

    out_dir = (
        Path(args.out_dir).resolve()
        if str(args.out_dir or "").strip()
        else Path(tempfile.mkdtemp(prefix="claude_agenthub_emptydir_", dir="/tmp")).resolve()
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    timeline_path = out_dir / "timeline.jsonl"
    logger = TimelineLogger(timeline_path)
    logger.emit(
        "benchmark.started",
        out_dir=str(out_dir),
        dry_run=bool(args.dry_run),
        task_workers=int(args.task_workers),
        tasks=[task.task_id for task in tasks],
    )

    preflight = _run_preflight(args, out_dir=out_dir, logger=logger)
    if preflight.get("executed") and not preflight.get("passed"):
        task_reports: list[dict[str, Any]] = []
    elif args.dry_run or int(args.task_workers) == 1:
        task_reports = [_run_task(task, root=out_dir, args=args, logger=logger) for task in tasks]
    else:
        indexed_reports: dict[int, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=int(args.task_workers)) as executor:
            futures = {
                executor.submit(_run_task, task, root=out_dir, args=args, logger=logger): index
                for index, task in enumerate(tasks)
            }
            for future, index in futures.items():
                indexed_reports[index] = future.result()
        task_reports = [indexed_reports[index] for index in range(len(tasks))]
    report = {
        "schema_version": "anthropic_coding_benchmark_v1",
        "generated_at": datetime.now().astimezone().isoformat(),
        "repo_root": str(REPO_ROOT),
        "out_dir": str(out_dir),
        "timeline_path": str(timeline_path),
        "dry_run": bool(args.dry_run),
        "preflight": preflight,
        "system_execution_mode": "parallel",
        "task_workers": int(args.task_workers),
        "agenthub_provider": str(args.agenthub_provider),
        "agenthub_model": str(args.agenthub_model),
        "agenthub_main": str(Path(args.agenthub_main).resolve()),
        **_agenthub_provider_home_report_fields(str(args.agenthub_provider_home or "")),
        "claude_bin": str(args.claude_bin),
        "claude_model": str(args.claude_model),
        "claude_permission_mode": str(args.claude_permission_mode),
        "timeout_seconds": int(args.timeout_seconds),
        "validation_timeout_seconds": int(args.validation_timeout_seconds),
        "tasks": task_reports,
    }
    report["scoreboard"] = _scoreboard_rows(task_reports)
    report_path = out_dir / "report.json"
    summary_md_path = out_dir / "summary.md"
    report["report_path"] = str(report_path)
    report["summary_md_path"] = str(summary_md_path)

    _write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    _write_summary_markdown(report, summary_md_path)
    logger.emit(
        "benchmark.completed",
        out_dir=str(out_dir),
        preflight_executed=bool(preflight.get("executed")),
        preflight_passed=preflight.get("passed"),
        scoreboard=report["scoreboard"],
        report_path=str(report_path),
        summary_md_path=str(summary_md_path),
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _render_console_summary(report)
    if preflight.get("executed") and not preflight.get("passed"):
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
