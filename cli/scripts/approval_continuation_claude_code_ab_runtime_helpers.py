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
    from cli.scripts.approval_continuation_claude_code_ab_claude_helpers import (
        _run_claude_code_case,
    )
    from cli.scripts.approval_continuation_codex_ref_ab_case_helpers import AbCase
    from cli.scripts.approval_continuation_codex_ref_ab_model_helpers import (
        CommandResult,
        _file_state,
        _write_text,
    )
    from cli.scripts.script_runtime_helpers import ensure_script_import_paths
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from approval_continuation_claude_code_ab_claude_helpers import (  # type: ignore[no-redef]
        _run_claude_code_case,
    )
    from approval_continuation_codex_ref_ab_case_helpers import AbCase  # type: ignore[no-redef]
    from approval_continuation_codex_ref_ab_model_helpers import (  # type: ignore[no-redef]
        CommandResult,
        _file_state,
        _write_text,
    )
    from script_runtime_helpers import ensure_script_import_paths  # type: ignore[no-redef]


_SCRIPT_PATHS = ensure_script_import_paths(__file__)
CLI_ROOT = _SCRIPT_PATHS.cli_root
LIVE_HARNESS = CLI_ROOT / "scripts" / "approval_continuation_live_harness.py"


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
    if not path.exists():
        return {}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(report, dict):
        return {}
    results = list(report.get("results") or [])
    return dict(results[0]) if results and isinstance(results[0], dict) else {}


def _case_verdict(
    *,
    case: AbCase,
    agenthub_case: dict[str, Any],
    agenthub_file: dict[str, Any],
    claude_code: dict[str, Any],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if str(agenthub_case.get("verdict") or "") != "pass":
        reasons.append("agenthub_case_failed")
    claude_run = dict(claude_code.get("run") or {})
    if int(claude_run.get("exit_code") or 0) != 0:
        reasons.append("claude_code_nonzero_exit")
    if bool(claude_run.get("timed_out")):
        reasons.append("claude_code_timed_out")
    summary = dict(claude_code.get("summary") or {})
    requests = [dict(item) for item in list(summary.get("control_requests") or [])]
    expected_tool_names = {"Bash"} if case.tool_kind == "command" else {"Write", "Edit"}
    if not any(str(item.get("tool_name") or "") in expected_tool_names for item in requests):
        reasons.append("claude_code_missing_expected_permission_request")
    decision_tools = {
        str(item.get("tool_name") or "")
        for item in list(summary.get("decisions") or [])
        if str(item.get("decision") or "") == case.decision
    }
    if not decision_tools.intersection(expected_tool_names):
        reasons.append("claude_code_missing_decision")
    if not bool(summary.get("completed_turn")):
        reasons.append("claude_code_turn_not_completed")
    claude_file = dict(claude_code.get("file") or {})
    if case.decision == "approve":
        if not bool(agenthub_file.get("exists")):
            reasons.append("agenthub_file_missing")
        if str(agenthub_file.get("content") or "") != case.expected_content:
            reasons.append("agenthub_file_content_mismatch")
        if not bool(claude_file.get("exists")):
            reasons.append("claude_code_file_missing")
        if str(claude_file.get("content") or "") != case.expected_content:
            reasons.append("claude_code_file_content_mismatch")
    else:
        if bool(agenthub_file.get("exists")):
            reasons.append("agenthub_rejected_file_should_not_exist")
        if bool(claude_file.get("exists")):
            reasons.append("claude_code_rejected_file_should_not_exist")
    return ("pass" if not reasons else "fail", reasons)


def _run_case(
    *,
    case: AbCase,
    case_root: Path,
    agenthub_provider: str,
    agenthub_model: str,
    agenthub_reasoning_effort: str,
    claude_bin: str,
    claude_model: str,
    timeout_seconds: int,
    dry_run: bool,
) -> dict[str, Any]:
    agenthub_root = case_root / "agenthub"
    claude_root = case_root / "claude_code"
    env = os.environ.copy()
    agenthub_command = [
        sys.executable,
        str(LIVE_HARNESS),
        "--out-root",
        str(agenthub_root),
        "--provider",
        agenthub_provider,
        "--model",
        agenthub_model,
        "--reasoning-effort",
        agenthub_reasoning_effort,
        "--approval-transport",
        "control",
        "--timeout-seconds",
        str(timeout_seconds),
        "--case",
        case.live_case,
    ]
    agenthub_result = _run_command(
        command=agenthub_command,
        cwd=CLI_ROOT,
        env=env,
        stdout_path=case_root / "agenthub.runner.stdout.log",
        stderr_path=case_root / "agenthub.runner.stderr.log",
        timeout_seconds=timeout_seconds + 60,
        dry_run=dry_run,
    )
    agenthub_case = _agenthub_report_for_case(agenthub_root / "report.json") if not dry_run else {}
    agenthub_workspace = Path(
        str(agenthub_case.get("workspace") or agenthub_root / case.live_case / "workspace")
    )
    agenthub_file = _file_state(agenthub_workspace, case.target_file)
    claude_code = _run_claude_code_case(
        case=case,
        case_root=claude_root,
        claude_bin=claude_bin,
        claude_model=claude_model,
        timeout_seconds=timeout_seconds,
        dry_run=dry_run,
    )
    verdict, reasons = (
        ("dry_run", [])
        if dry_run
        else _case_verdict(
            case=case,
            agenthub_case=agenthub_case,
            agenthub_file=agenthub_file,
            claude_code=claude_code,
        )
    )
    return {
        "case": case.name,
        "verdict": verdict,
        "reasons": reasons,
        "agenthub": {
            "run": asdict(agenthub_result),
            "report_path": str(agenthub_root / "report.json"),
            "case": agenthub_case,
            "workspace": str(agenthub_workspace),
            "file": agenthub_file,
        },
        "claude_code": claude_code,
    }
