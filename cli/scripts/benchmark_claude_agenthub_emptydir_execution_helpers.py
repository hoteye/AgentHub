from __future__ import annotations

import argparse
import shlex
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

try:
    from cli.scripts.benchmark_claude_agenthub_emptydir_config_helpers import (
        BenchmarkTask,
    )
    from cli.scripts.benchmark_claude_agenthub_emptydir_reporting_helpers import (
        _DIAGNOSTIC_FIELD_DEFAULTS,
        _artifact_quality_notes,
        _diagnostic_defaults,
        _dry_run_system_report,
        _flatten_diagnostics,
        _parse_agenthub_output,
        _parse_claude_output,
        _prompt_preview,
        _report_task_entry,
    )
    from cli.scripts.benchmark_claude_agenthub_emptydir_runtime_helpers import (
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
        _write_workspace_tree,
    )
    from cli.scripts.benchmark_claude_agenthub_emptydir_preflight_helpers import _planned_agenthub_env
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from benchmark_claude_agenthub_emptydir_config_helpers import (  # type: ignore[no-redef]
        BenchmarkTask,
    )
    from benchmark_claude_agenthub_emptydir_reporting_helpers import (  # type: ignore[no-redef]
        _DIAGNOSTIC_FIELD_DEFAULTS,
        _artifact_quality_notes,
        _diagnostic_defaults,
        _dry_run_system_report,
        _flatten_diagnostics,
        _parse_agenthub_output,
        _parse_claude_output,
        _prompt_preview,
        _report_task_entry,
    )
    from benchmark_claude_agenthub_emptydir_runtime_helpers import (  # type: ignore[no-redef]
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
        _write_workspace_tree,
    )
    from benchmark_claude_agenthub_emptydir_preflight_helpers import _planned_agenthub_env  # type: ignore[no-redef]


def _execute_system(
    *,
    system_name: str,
    task: BenchmarkTask,
    workspace: Path,
    system_root: Path,
    run_command: list[str],
    env: dict[str, str],
    timeout_seconds: int,
    validation_timeout_seconds: int,
    logger: TimelineLogger | None = None,
) -> dict[str, Any]:
    if logger is not None:
        logger.emit(
            "system.started",
            task_id=task.task_id,
            system=system_name,
            cwd=str(workspace),
            run_command=list(run_command),
            run_command_shell=shlex.join(run_command),
            timeout_seconds=int(timeout_seconds),
            validation_timeout_seconds=int(validation_timeout_seconds),
        )
    stdout_name = "stdout.json" if system_name == "agenthub" else "stdout.json"
    run_result = _run_command(
        name=system_name,
        command=run_command,
        cwd=workspace,
        env=env,
        stdout_path=system_root / stdout_name,
        stderr_path=system_root / "stderr.log",
        timeout_seconds=timeout_seconds,
        logger=logger,
        event_context={"task_id": task.task_id, "system": system_name, "phase": "run"},
    )
    validation_results = [
        _run_validation(
            validation=item,
            cwd=workspace,
            env=env,
            out_dir=system_root / "validation",
            timeout_seconds=validation_timeout_seconds,
            logger=logger,
            event_context={"task_id": task.task_id, "system": system_name, "phase": "validation"},
        )
        for item in task.validations
    ]
    workspace_files = _write_workspace_tree(workspace, system_root / "workspace_tree.txt")
    parsed = (
        _parse_agenthub_output(Path(run_result.stdout_path))
        if system_name == "agenthub"
        else _parse_claude_output(Path(run_result.stdout_path))
    )
    validation_payload = []
    for spec, result in zip(task.validations, validation_results):
        payload = asdict(result)
        payload["command_text"] = spec.command
        validation_payload.append(payload)
    missing_expected_files = _missing_expected_files(task, workspace_files)
    validation_passed = _validation_passed(validation_payload)
    run_succeeded = int(run_result.exit_code) == 0 and not run_result.timed_out
    diagnostics = _diagnostic_defaults(
        **{
            key: parsed.get(key)
            for key in _DIAGNOSTIC_FIELD_DEFAULTS
            if key in parsed
        }
    )
    diagnostics["created_files"] = list(workspace_files)
    diagnostics["validation_passed"] = bool(validation_passed)
    diagnostics["artifact_quality_notes"] = _artifact_quality_notes(
        run_succeeded=run_succeeded,
        validation_passed=validation_passed,
        missing_expected_files=missing_expected_files,
        workspace_files=workspace_files,
    )
    _flatten_diagnostics(parsed, diagnostics)
    payload = {
        "system": system_name,
        "workspace": str(workspace),
        "run": asdict(run_result),
        "assistant_text": str(parsed.get("assistant_text") or ""),
        "assistant_preview": _prompt_preview(str(parsed.get("assistant_text") or ""), limit=160),
        "parsed_output": parsed,
        "workspace_files": workspace_files,
        "workspace_file_count": len(workspace_files),
        "missing_expected_files": missing_expected_files,
        "validation": validation_payload,
        "validation_passed": validation_passed,
        "run_succeeded": run_succeeded,
        "workspace_tree_path": str(system_root / "workspace_tree.txt"),
    }
    _flatten_diagnostics(payload, diagnostics)
    if logger is not None:
        logger.emit(
            "system.first_event",
            task_id=task.task_id,
            system=system_name,
            relative_ms=payload.get("time_to_first_event_ms"),
            source="parsed_output",
            detected=payload.get("time_to_first_event_ms") is not None,
        )
        logger.emit(
            "system.first_tool_event",
            task_id=task.task_id,
            system=system_name,
            relative_ms=payload.get("time_to_first_tool_ms"),
            source="parsed_output",
            detected=payload.get("time_to_first_tool_ms") is not None,
            tool_call_sequence=list(payload.get("tool_call_sequence") or []),
        )
        logger.emit(
            "system.completed",
            task_id=task.task_id,
            system=system_name,
            exit_code=int(run_result.exit_code),
            timed_out=bool(run_result.timed_out),
            elapsed_seconds=float(run_result.elapsed_seconds),
            validation_passed=bool(payload["validation_passed"]),
            run_succeeded=bool(payload["run_succeeded"]),
            workspace_file_count=int(payload["workspace_file_count"]),
            missing_expected_files=list(payload["missing_expected_files"]),
            assistant_preview=str(payload["assistant_preview"]),
            workspace_tree_path=str(payload["workspace_tree_path"]),
        )
    return payload


def _execute_system_job(
    job: dict[str, Any],
    *,
    execute_system_fn: Callable[..., dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any]]:
    runner = execute_system_fn or _execute_system
    return str(job["system_name"]), runner(
        system_name=str(job["system_name"]),
        task=job["task"],
        workspace=job["workspace"],
        system_root=job["system_root"],
        run_command=list(job["run_command"]),
        env=dict(job["env"]),
        timeout_seconds=int(job["timeout_seconds"]),
        validation_timeout_seconds=int(job["validation_timeout_seconds"]),
        logger=job.get("logger"),
    )


def _run_task(
    task: BenchmarkTask,
    *,
    root: Path,
    args: argparse.Namespace,
    logger: TimelineLogger | None = None,
    execute_system_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    paths = _ensure_task_layout(root, task)
    agenthub_command = _build_agenthub_command(prompt=task.prompt, args=args)
    claude_command = _build_claude_command(prompt=task.prompt, args=args)
    if logger is not None:
        logger.emit(
            "task.started",
            task_id=task.task_id,
            title=task.title,
            prompt_path=str(paths["prompt_path"]),
        )
    if args.dry_run:
        if logger is not None:
            logger.emit(
                "task.planned",
                task_id=task.task_id,
                systems=["agenthub", "claude"],
            )
        agenthub_payload = _dry_run_system_report(
            system_name="agenthub",
            task=task,
            workspace=paths["agenthub_workspace"],
            run_command=agenthub_command,
            validations=task.validations,
            env_overrides=_planned_agenthub_env(args),
        )
        claude_payload = _dry_run_system_report(
            system_name="claude",
            task=task,
            workspace=paths["claude_workspace"],
            run_command=claude_command,
            validations=task.validations,
            env_overrides={},
        )
        return _report_task_entry(
            task=task,
            paths=paths,
            agenthub_payload=agenthub_payload,
            claude_payload=claude_payload,
        )

    jobs = [
        {
            "system_name": "agenthub",
            "task": task,
            "workspace": paths["agenthub_workspace"],
            "system_root": paths["agenthub_root"],
            "run_command": agenthub_command,
            "env": _build_agenthub_env(args),
            "timeout_seconds": int(args.timeout_seconds),
            "validation_timeout_seconds": int(args.validation_timeout_seconds),
            "logger": logger,
        },
        {
            "system_name": "claude",
            "task": task,
            "workspace": paths["claude_workspace"],
            "system_root": paths["claude_root"],
            "run_command": claude_command,
            "env": _build_claude_env(),
            "timeout_seconds": int(args.timeout_seconds),
            "validation_timeout_seconds": int(args.validation_timeout_seconds),
            "logger": logger,
        },
    ]
    system_reports: dict[str, dict[str, Any]] = {}
    runner = execute_system_fn or _execute_system
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_execute_system_job, job, execute_system_fn=runner)
            for job in jobs
        ]
        for future in futures:
            system_name, payload = future.result()
            system_reports[system_name] = payload
    result = _report_task_entry(
        task=task,
        paths=paths,
        agenthub_payload=system_reports["agenthub"],
        claude_payload=system_reports["claude"],
    )
    if logger is not None:
        logger.emit(
            "task.completed",
            task_id=task.task_id,
            agenthub_validation_passed=bool(result["agenthub"]["validation_passed"]),
            claude_validation_passed=bool(result["claude"]["validation_passed"]),
            agenthub_run_succeeded=bool(result["agenthub"]["run_succeeded"]),
            claude_run_succeeded=bool(result["claude"]["run_succeeded"]),
        )
    return result
