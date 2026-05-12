from __future__ import annotations

import shlex
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

try:
    from cli.scripts.command_execution_wave03_ab_model_helpers import CommandResult, _workspace_file_inventory
    from cli.scripts.command_execution_wave03_ab_runtime_helpers import (
        _parse_agenthub_output,
        _parse_codex_output,
        _run_command,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from command_execution_wave03_ab_model_helpers import CommandResult, _workspace_file_inventory  # type: ignore[no-redef]
    from command_execution_wave03_ab_runtime_helpers import (  # type: ignore[no-redef]
        _parse_agenthub_output,
        _parse_codex_output,
        _run_command,
    )

RunCommand = Callable[..., CommandResult]
ParseOutput = Callable[[Path], dict[str, Any]]
WorkspaceInventory = Callable[[Path], list[dict[str, Any]]]


def _system_payload(
    *,
    system_name: str,
    command: list[str],
    cwd: Path,
    workspace: Path,
    env: dict[str, str],
    out_dir: Path,
    timeout_seconds: int,
    dry_run: bool,
    run_command: RunCommand | None = None,
    parse_agenthub_output: ParseOutput | None = None,
    parse_codex_output: ParseOutput | None = None,
    workspace_file_inventory: WorkspaceInventory | None = None,
) -> dict[str, Any]:
    stdout_path = out_dir / f"{system_name}.stdout.log"
    stderr_path = out_dir / f"{system_name}.stderr.log"
    runner = run_command or _run_command
    run = runner(
        name=system_name,
        command=command,
        cwd=cwd,
        env=env,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        timeout_seconds=timeout_seconds,
        dry_run=dry_run,
    )
    if system_name == "agenthub":
        parsed = (parse_agenthub_output or _parse_agenthub_output)(stdout_path)
    else:
        parsed = (parse_codex_output or _parse_codex_output)(stdout_path)
    workspace_files = (workspace_file_inventory or _workspace_file_inventory)(workspace)
    return {
        "workspace": str(workspace),
        "run": asdict(run),
        "parsed_output": parsed,
        "workspace_files": workspace_files,
        "workspace_file_count": len(workspace_files),
    }


def _build_log_manifest(out_dir: Path) -> dict[str, str]:
    return {
        "agenthub_stdout": str(out_dir / "agenthub.stdout.log"),
        "agenthub_stderr": str(out_dir / "agenthub.stderr.log"),
        "codex_stdout": str(out_dir / "codex.stdout.log"),
        "codex_stderr": str(out_dir / "codex.stderr.log"),
        "agenthub_invocation": str(out_dir / "agenthub.invocation.json"),
        "codex_invocation": str(out_dir / "codex.invocation.json"),
        "agenthub_config_snapshot": str(out_dir / "agenthub.config.snapshot.json"),
        "codex_config_snapshot": str(out_dir / "codex.config.snapshot.json"),
        "agenthub_auth_snapshot": str(out_dir / "agenthub.auth.snapshot.json"),
        "codex_auth_snapshot": str(out_dir / "codex.auth.snapshot.json"),
        "agenthub_workspace_files": str(out_dir / "agenthub.workspace.files.json"),
        "codex_workspace_files": str(out_dir / "codex.workspace.files.json"),
        "commands": str(out_dir / "commands.txt"),
        "summary_json": str(out_dir / "summary.json"),
        "report_json": str(out_dir / "report.json"),
        "summary_md": str(out_dir / "summary.md"),
    }


def _summary_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Command Execution Wave 03 A/B",
        "",
        f"- started_at: {report['started_at']}",
        f"- ended_at: {report['ended_at']}",
        f"- prompt_preview: {report['prompt_preview']}",
        f"- dry_run: {'yes' if report['dry_run'] else 'no'}",
        f"- out_dir: `{report['out_dir']}`",
        "",
    ]
    for system_name in ("agenthub", "codex"):
        system = report["systems"][system_name]
        run = system["run"]
        parsed = system["parsed_output"]
        lines.extend(
            [
                f"## {system_name}",
                "",
                f"- exit_code: {run['exit_code']}",
                f"- timed_out: {'yes' if run['timed_out'] else 'no'}",
                f"- elapsed_seconds: {run['elapsed_seconds']}",
                f"- workspace_file_count: {system['workspace_file_count']}",
                f"- assistant_preview: {str(parsed.get('assistant_text') or '').replace(chr(10), ' ')[:240] or '-'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _commands_text(
    *,
    agenthub_command: list[str],
    codex_command: list[str],
    agenthub_config_mode: str,
    agenthub_config_path: Path,
    agenthub_auth_path: Path,
    agenthub_interaction_profile: str,
    codex_config_mode: str,
    codex_provider_id: str,
    codex_config_path: Path,
    codex_auth_path: Path,
    summary_json: str,
    report_json: str,
) -> str:
    return (
        "\n".join(
            [
                "agenthub:",
                shlex.join(agenthub_command),
                "",
                "codex:",
                shlex.join(codex_command),
                "",
                f"agenthub_config_mode={agenthub_config_mode}",
                f"agenthub_config_path={agenthub_config_path}",
                f"agenthub_auth_path={agenthub_auth_path}",
                f"agenthub_interaction_profile={agenthub_interaction_profile or '-'}",
                "",
                f"codex_config_mode={codex_config_mode}",
                f"codex_provider_id={codex_provider_id}",
                f"codex_config_path={codex_config_path}",
                f"codex_auth_path={codex_auth_path}",
                "",
                f"summary_json={summary_json}",
                f"report_json={report_json}",
            ]
        )
        + "\n"
    )
