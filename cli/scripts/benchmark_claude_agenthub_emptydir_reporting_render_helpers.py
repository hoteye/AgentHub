from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

try:
    from cli.scripts.benchmark_claude_agenthub_emptydir_config_helpers import (
        BenchmarkTask,
        EXPECTED_SHORT_REPLY,
        EXPECTED_SONNET_MODEL_KEY,
    )
    from cli.scripts.benchmark_claude_agenthub_emptydir_reporting_diagnostic_helpers import _prompt_preview
    from cli.scripts.benchmark_claude_agenthub_emptydir_runtime_helpers import _write_text
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from benchmark_claude_agenthub_emptydir_config_helpers import (  # type: ignore[no-redef]
        BenchmarkTask,
        EXPECTED_SHORT_REPLY,
        EXPECTED_SONNET_MODEL_KEY,
    )
    from benchmark_claude_agenthub_emptydir_reporting_diagnostic_helpers import _prompt_preview  # type: ignore[no-redef]
    from benchmark_claude_agenthub_emptydir_runtime_helpers import _write_text  # type: ignore[no-redef]


def _scoreboard_rows(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for system_name in ("agenthub", "claude"):
        systems = [item.get(system_name) or {} for item in tasks]
        completed_runs = [item for item in systems if item]
        wall_values = [
            float((item.get("run") or {}).get("elapsed_seconds"))
            for item in completed_runs
            if isinstance((item.get("run") or {}).get("elapsed_seconds"), (int, float))
        ]
        first_event_values = [
            int(item.get("time_to_first_event_ms"))
            for item in completed_runs
            if isinstance(item.get("time_to_first_event_ms"), int)
        ]
        first_tool_values = [
            int(item.get("time_to_first_tool_ms"))
            for item in completed_runs
            if isinstance(item.get("time_to_first_tool_ms"), int)
        ]
        rows.append(
            {
                "system": system_name,
                "tasks_total": len(tasks),
                "run_successes": sum(1 for item in completed_runs if item.get("run_succeeded")),
                "validation_successes": sum(1 for item in completed_runs if item.get("validation_passed")),
                "avg_wall_seconds": round(sum(wall_values) / len(wall_values), 3) if wall_values else None,
                "avg_time_to_first_event_ms": (
                    round(sum(first_event_values) / len(first_event_values), 1)
                    if first_event_values
                    else None
                ),
                "avg_time_to_first_tool_ms": (
                    round(sum(first_tool_values) / len(first_tool_values), 1)
                    if first_tool_values
                    else None
                ),
                "apply_patch_failures": sum(
                    int(item.get("apply_patch_failures") or 0)
                    for item in completed_runs
                ),
            }
        )
    return rows


def _md_escape(value: str) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def _md_join(values: Any, *, limit: int = 6) -> str:
    if not isinstance(values, list) or not values:
        return "-"
    text_values = [str(item) for item in values if str(item).strip()]
    if not text_values:
        return "-"
    visible = text_values[:limit]
    suffix = "" if len(text_values) <= limit else f", +{len(text_values) - limit} more"
    return _md_escape(", ".join(visible) + suffix)


def _md_value(value: Any) -> str:
    return "-" if value is None or value == "" else _md_escape(str(value))


def _write_summary_markdown(report: dict[str, Any], destination: Path) -> None:
    lines: list[str] = []
    lines.append("# Claude Code vs AgentHub Empty-Dir Benchmark\n")
    lines.append(f"- generated_at: {report.get('generated_at')}\n")
    lines.append(f"- out_dir: {report.get('out_dir')}\n")
    lines.append(f"- timeline_jsonl: {report.get('timeline_path')}\n")
    lines.append(f"- dry_run: {report.get('dry_run')}\n")
    lines.append(f"- system_execution_mode: {report.get('system_execution_mode')}\n")
    lines.append(f"- task_workers: {report.get('task_workers')}\n")
    lines.append(
        f"- agenthub: {report.get('agenthub_provider')} / {report.get('agenthub_model')}\n"
    )
    lines.append(f"- claude_code: {report.get('claude_model')}\n")
    preflight = report.get("preflight") if isinstance(report.get("preflight"), dict) else {}
    lines.append(
        "- preflight: "
        + (
            "planned"
            if not preflight.get("executed")
            else ("passed" if preflight.get("passed") else "failed")
        )
        + "\n"
    )
    lines.append("\n## Preflight\n")
    lines.append("| System | Status | Exit | Reply | Key Model / Route |\n")
    lines.append("| --- | --- | ---: | --- | --- |\n")
    for system_name in ("agenthub", "claude"):
        system = (preflight.get("systems") or {}).get(system_name) or {}
        run = system.get("run") or {}
        if not preflight.get("executed"):
            lines.append(
                f"| {system_name} | planned | - | {EXPECTED_SHORT_REPLY} | {EXPECTED_SONNET_MODEL_KEY} |\n"
            )
            continue
        parsed = system.get("parsed_output") if isinstance(system.get("parsed_output"), dict) else {}
        route_label = ""
        if system_name == "agenthub":
            status = parsed.get("status") if isinstance(parsed.get("status"), dict) else {}
            route_label = str(status.get("provider_label") or status.get("model_key") or "")
        else:
            model_usage = parsed.get("model_usage") if isinstance(parsed.get("model_usage"), dict) else {}
            route_label = ", ".join(sorted(str(key) for key in model_usage.keys()))
        lines.append(
            f"| {system_name} | {'passed' if system.get('passed') else 'failed'} | "
            f"{run.get('exit_code', '-')} | {_md_escape(str(system.get('assistant_text') or ''))} | {_md_escape(route_label)} |\n"
        )
    lines.append("\n## Scoreboard\n")
    lines.append(
        "| System | Tasks | Run OK | Validation OK | Avg Wall Seconds | Avg First Event ms | Avg First Tool ms | Patch Failures |\n"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n")
    for row in list(report.get("scoreboard") or []):
        avg_wall = row.get("avg_wall_seconds")
        avg_first_event = row.get("avg_time_to_first_event_ms")
        avg_first_tool = row.get("avg_time_to_first_tool_ms")
        lines.append(
            f"| {row.get('system')} | {row.get('tasks_total')} | {row.get('run_successes')} | "
            f"{row.get('validation_successes')} | {avg_wall if avg_wall is not None else '-'} | "
            f"{avg_first_event if avg_first_event is not None else '-'} | "
            f"{avg_first_tool if avg_first_tool is not None else '-'} | "
            f"{row.get('apply_patch_failures', 0)} |\n"
        )
    lines.append("\n## Task Results\n")
    lines.append("| Task | System | Exit | Validation | Wall Seconds | Files | Preview |\n")
    lines.append("| --- | --- | ---: | --- | ---: | ---: | --- |\n")
    for task in list(report.get("tasks") or []):
        for system_name in ("agenthub", "claude"):
            system = task.get(system_name) or {}
            run = system.get("run") or {}
            exit_code = run.get("exit_code", "-")
            wall = run.get("elapsed_seconds", "-")
            preview = _md_escape(str(system.get("assistant_preview") or ""))
            validation_value = "yes" if system.get("validation_passed") else "no"
            lines.append(
                f"| {task.get('task_id')} | {system_name} | {exit_code} | {validation_value} | "
                f"{wall} | {system.get('workspace_file_count', 0)} | {preview} |\n"
            )
    lines.append("\n## Diagnostics\n")
    lines.append(
        "| Task | Prompt | System | Tool Sequence | First Event ms | First Tool ms | Initial Model ms | Tool Exec ms | Patch Attempts | Patch Failures | Created Files | Validation | Artifact Notes |\n"
    )
    lines.append("| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |\n")
    for task in list(report.get("tasks") or []):
        prompt_preview = _md_escape(str(task.get("prompt_preview") or ""))
        for system_name in ("agenthub", "claude"):
            system = task.get(system_name) or {}
            lines.append(
                f"| {task.get('task_id')} | {prompt_preview} | {system_name} | "
                f"{_md_join(system.get('tool_call_sequence'))} | "
                f"{_md_value(system.get('time_to_first_event_ms'))} | "
                f"{_md_value(system.get('time_to_first_tool_ms'))} | "
                f"{_md_value(system.get('initial_model_ms'))} | "
                f"{_md_value(system.get('tool_execution_ms'))} | "
                f"{_md_value(system.get('apply_patch_attempts'))} | "
                f"{_md_value(system.get('apply_patch_failures'))} | "
                f"{_md_join(system.get('created_files'), limit=5)} | "
                f"{'yes' if system.get('validation_passed') else 'no'} | "
                f"{_md_escape(str(system.get('artifact_quality_notes') or ''))} |\n"
            )
    _write_text(destination, "".join(lines))


def _report_task_entry(
    *,
    task: BenchmarkTask,
    paths: dict[str, Path],
    agenthub_payload: dict[str, Any],
    claude_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "title": task.title,
        "prompt_path": str(paths["prompt_path"]),
        "prompt_preview": _prompt_preview(task.prompt),
        "expected_files": list(task.expected_files),
        "validations": [{"name": item.name, "command": item.command} for item in task.validations],
        "agenthub": agenthub_payload,
        "claude": claude_payload,
    }


def _preflight_system_report(
    *,
    system_name: str,
    command: list[str],
    env_overrides: dict[str, str],
    cwd: Path,
) -> dict[str, Any]:
    return {
        "system": system_name,
        "cwd": str(cwd),
        "planned_run_command": list(command),
        "planned_run_command_shell": shlex.join(command),
        "env_overrides": dict(env_overrides),
        "expected_reply": EXPECTED_SHORT_REPLY,
        "expected_model": EXPECTED_SONNET_MODEL_KEY,
    }


def _render_console_summary(report: dict[str, Any]) -> None:
    print(f"out_dir={report['out_dir']}")
    print(f"dry_run={report['dry_run']}")
    print(f"timeline_jsonl={report['timeline_path']}")
    preflight = report.get("preflight") or {}
    print(
        "preflight="
        + (
            "planned"
            if not preflight.get("executed")
            else ("passed" if preflight.get("passed") else "failed")
        )
    )
    for row in list(report.get("scoreboard") or []):
        avg_wall = row.get("avg_wall_seconds")
        avg_label = "-" if avg_wall is None else f"{avg_wall}s"
        print(
            f"{row['system']}: tasks={row['tasks_total']} "
            f"run_ok={row['run_successes']} validation_ok={row['validation_successes']} avg_wall={avg_label}"
        )
    print(f"report_json={report['report_path']}")
    print(f"summary_md={report['summary_md_path']}")
