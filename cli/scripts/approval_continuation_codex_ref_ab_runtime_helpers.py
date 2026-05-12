from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

try:
    from cli.scripts.approval_continuation_codex_ref_ab_case_helpers import AbCase, _prompt_for_case
    from cli.scripts.approval_continuation_codex_ref_ab_config_helpers import (
        CLI_ROOT,
        LIVE_HARNESS,
        _build_codex_home,
    )
    from cli.scripts.approval_continuation_codex_ref_ab_model_helpers import (
        CommandResult,
        _file_state,
        _read_json,
        _write_text,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from approval_continuation_codex_ref_ab_case_helpers import (  # type: ignore[no-redef]
        AbCase,
        _prompt_for_case,
    )
    from approval_continuation_codex_ref_ab_config_helpers import (  # type: ignore[no-redef]
        CLI_ROOT,
        LIVE_HARNESS,
        _build_codex_home,
    )
    from approval_continuation_codex_ref_ab_model_helpers import (  # type: ignore[no-redef]
        CommandResult,
        _file_state,
        _read_json,
        _write_text,
    )


def _coerce_process_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def _run_command(
    *,
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: int,
    dry_run: bool,
) -> CommandResult:
    started = time.perf_counter()
    timed_out = False
    exit_code = 0
    stdout_text = ""
    stderr_text = ""
    if dry_run:
        stdout_text = json.dumps({"dry_run": True, "command": command}, ensure_ascii=False) + "\n"
    else:
        try:
            proc = subprocess.run(
                command,
                cwd=str(cwd),
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            exit_code = int(proc.returncode)
            stdout_text = proc.stdout
            stderr_text = proc.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = 124
            stdout_text = _coerce_process_text(exc.stdout)
            stderr_text = _coerce_process_text(exc.stderr)
    elapsed = time.perf_counter() - started
    _write_text(stdout_path, stdout_text)
    _write_text(stderr_path, stderr_text)
    return CommandResult(
        command=list(command),
        cwd=str(cwd),
        exit_code=exit_code,
        elapsed_seconds=round(elapsed, 3),
        timed_out=timed_out,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )


def _agenthub_report_for_case(path: Path) -> dict[str, Any]:
    report = _read_json(path)
    if not isinstance(report, dict):
        return {}
    results = list(report.get("results") or [])
    return dict(results[0]) if results and isinstance(results[0], dict) else {}


def _parse_codex_stdout(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    command_decision_lines = [
        line for line in text.splitlines() if "commandExecution decision" in line
    ]
    file_change_decision_lines = [
        line for line in text.splitlines() if "fileChange decision" in line
    ]
    approval_markers = {
        "command": "commandExecution approval requested" in text,
        "file_change": "fileChange approval requested" in text,
    }
    decision_markers = {
        "command_accept": any("Accept" in line for line in command_decision_lines),
        "command_decline": any("Decline" in line for line in command_decision_lines),
        "file_change_accept": any("Accept" in line for line in file_change_decision_lines),
        "file_change_decline": any("Decline" in line for line in file_change_decision_lines),
    }
    completed_turn = "turn/completed notification: Completed" in text
    item_completed = "item completed:" in text
    command_completed = "ThreadItem::CommandExecution" in text and "Completed" in text
    file_completed = "ThreadItem::FileChange" in text or "fileChange" in text
    return {
        "approval_markers": approval_markers,
        "decision_markers": decision_markers,
        "completed_turn": completed_turn,
        "item_completed": item_completed,
        "command_completed": command_completed,
        "file_completed": file_completed,
        "stdout_preview": text[-3000:],
    }


def _case_verdict(
    *,
    case: AbCase,
    agenthub_case: dict[str, Any],
    codex_summary: dict[str, Any],
    agenthub_file: dict[str, Any],
    codex_file: dict[str, Any],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if str(agenthub_case.get("verdict") or "") != "pass":
        reasons.append("agenthub_case_failed")
    marker_name = case.tool_kind
    if not bool(dict(codex_summary.get("approval_markers") or {}).get(marker_name)):
        reasons.append("codex_missing_approval_marker")
    decision_marker = f"{marker_name}_{'accept' if case.decision == 'approve' else 'decline'}"
    if not bool(dict(codex_summary.get("decision_markers") or {}).get(decision_marker)):
        reasons.append(f"codex_missing_{decision_marker}_marker")
    if not bool(codex_summary.get("completed_turn")):
        reasons.append("codex_turn_not_completed")
    if case.decision == "approve":
        if not bool(agenthub_file.get("exists")):
            reasons.append("agenthub_file_missing")
        if not bool(codex_file.get("exists")):
            reasons.append("codex_file_missing")
        if str(agenthub_file.get("content") or "") != case.expected_content:
            reasons.append("agenthub_file_content_mismatch")
        if str(codex_file.get("content") or "") != case.expected_content:
            reasons.append("codex_file_content_mismatch")
    else:
        if bool(agenthub_file.get("exists")):
            reasons.append("agenthub_rejected_file_should_not_exist")
        if bool(codex_file.get("exists")):
            reasons.append("codex_rejected_file_should_not_exist")
    return ("pass" if not reasons else "fail", reasons)


def _run_case(
    *,
    case: AbCase,
    case_root: Path,
    provider: str,
    agenthub_model: str,
    codex_model: str,
    reasoning_effort: str,
    base_url: str,
    api_key: str,
    codex_provider_id: str,
    codex_bin: Path,
    codex_app_server_test_client: Path,
    timeout_seconds: int,
    dry_run: bool,
) -> dict[str, Any]:
    agenthub_root = case_root / "agenthub"
    codex_root = case_root / "codex"
    codex_workspace = codex_root / "workspace"
    codex_home = codex_root / "codex_home"
    codex_workspace.mkdir(parents=True, exist_ok=True)
    codex_config_path, codex_auth_path = _build_codex_home(
        codex_home=codex_home,
        api_key=api_key,
        provider_id=codex_provider_id,
        model=codex_model,
        reasoning_effort=reasoning_effort,
        base_url=base_url,
        workspace=codex_workspace,
    )
    agenthub_command = [
        sys.executable,
        str(LIVE_HARNESS),
        "--out-root",
        str(agenthub_root),
        "--provider",
        provider,
        "--model",
        agenthub_model,
        "--reasoning-effort",
        reasoning_effort,
        "--timeout-seconds",
        str(timeout_seconds),
        "--case",
        case.live_case,
    ]
    codex_command = [
        str(codex_app_server_test_client),
        "--codex-bin",
        str(codex_bin),
        "-c",
        f'model_provider="{codex_provider_id}"',
        "-c",
        f'model="{codex_model}"',
    ]
    if reasoning_effort:
        codex_command.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
    codex_command.extend([case.codex_command, _prompt_for_case(case)])
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = api_key
    env["CODEX_HOME"] = str(codex_home)
    env["CODEX_DEBUG_LOG_DIR"] = str(codex_root / "logs")
    agenthub_result = _run_command(
        command=agenthub_command,
        cwd=CLI_ROOT,
        env=env,
        stdout_path=case_root / "agenthub.runner.stdout.log",
        stderr_path=case_root / "agenthub.runner.stderr.log",
        timeout_seconds=timeout_seconds + 60,
        dry_run=dry_run,
    )
    codex_result = _run_command(
        command=codex_command,
        cwd=codex_workspace,
        env=env,
        stdout_path=case_root / "codex.stdout.log",
        stderr_path=case_root / "codex.stderr.log",
        timeout_seconds=timeout_seconds + 60,
        dry_run=dry_run,
    )
    agenthub_case = _agenthub_report_for_case(agenthub_root / "report.json") if not dry_run else {}
    codex_summary = _parse_codex_stdout(Path(codex_result.stdout_path))
    agenthub_workspace = Path(
        str(agenthub_case.get("workspace") or agenthub_root / case.live_case / "workspace")
    )
    agenthub_file = _file_state(agenthub_workspace, case.target_file)
    codex_file = _file_state(codex_workspace, case.target_file)
    verdict, reasons = (
        ("dry_run", [])
        if dry_run
        else _case_verdict(
            case=case,
            agenthub_case=agenthub_case,
            codex_summary=codex_summary,
            agenthub_file=agenthub_file,
            codex_file=codex_file,
        )
    )
    return {
        "case": case.name,
        "verdict": verdict,
        "reasons": reasons,
        "prompt": _prompt_for_case(case),
        "agenthub": {
            "run": asdict(agenthub_result),
            "report_path": str(agenthub_root / "report.json"),
            "case": agenthub_case,
            "workspace": str(agenthub_workspace),
            "file": agenthub_file,
        },
        "codex_ref": {
            "run": asdict(codex_result),
            "workspace": str(codex_workspace),
            "codex_home": str(codex_home),
            "config_path": str(codex_config_path),
            "auth_path": str(codex_auth_path),
            "summary": codex_summary,
            "file": codex_file,
        },
    }
