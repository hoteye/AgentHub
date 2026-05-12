from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    from cli.scripts import run_multiturn_planning_probe as planning_probe
    from cli.scripts.run_multiturn_planning_ab_projection_helpers import _parse_codex_stdout
    from cli.scripts.run_multiturn_planning_ab_runtime_helpers import (
        _codex_exec_command,
        _inventory,
        _prepare_codex_home,
        _write_json,
        _write_text,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    import run_multiturn_planning_probe as planning_probe  # type: ignore[no-redef]
    from run_multiturn_planning_ab_projection_helpers import _parse_codex_stdout  # type: ignore[no-redef]
    from run_multiturn_planning_ab_runtime_helpers import (  # type: ignore[no-redef]
        _codex_exec_command,
        _inventory,
        _prepare_codex_home,
        _write_json,
        _write_text,
    )


def _run_codex_case_once(
    *,
    attempt_root: Path,
    case: planning_probe.CaseSpec,
    timeout_seconds: int,
) -> dict[str, Any]:
    home = attempt_root / "codex_home"
    workspace = attempt_root / "workspace"
    log_dir = attempt_root / "codex"
    workspace.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    _prepare_codex_home(home, workspace)
    planning_probe._seed_workspace(workspace, case.seed_files)

    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)

    turns: list[dict[str, Any]] = []
    provider_failure = False
    provider_failure_reason = ""
    last_thread_id = ""
    for turn_index, prompt in enumerate(case.prompts, start=1):
        turn_dir = log_dir / f"turn{turn_index}"
        turn_dir.mkdir(parents=True, exist_ok=True)
        command = _codex_exec_command(
            prompt=prompt,
            turn_dir=turn_dir,
            resume=turn_index > 1,
        )
        stdout_path = turn_dir / "stdout.jsonl"
        stderr_path = turn_dir / "stderr.txt"
        started = time.time()
        proc = subprocess.run(
            command,
            cwd=str(workspace),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        elapsed = round(time.time() - started, 3)
        _write_text(stdout_path, proc.stdout)
        _write_text(stderr_path, proc.stderr)
        parsed = _parse_codex_stdout(proc.stdout, turn_dir / "last_message.txt")
        last_thread_id = str(parsed.get("thread_id") or last_thread_id)
        failure_text = "\n".join(
            piece
            for piece in (
                parsed.get("assistant_text") or "",
                "\n".join(parsed.get("errors") or []),
                proc.stderr,
            )
            if str(piece or "").strip()
        )
        if planning_probe._looks_like_provider_unavailable(failure_text):
            provider_failure = True
            provider_failure_reason = failure_text
        turns.append(
            {
                "turn": turn_index,
                "prompt": prompt,
                "cmd": command,
                "returncode": int(proc.returncode),
                "elapsed_s": elapsed,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "last_message_path": str(turn_dir / "last_message.txt"),
                "parsed": parsed,
                "files_after": _inventory(workspace),
            }
        )
        if proc.returncode != 0 or provider_failure:
            break

    validation_results = planning_probe._run_validation(
        workspace=workspace,
        out_dir=attempt_root / "validation",
        commands=case.validation_commands,
    )
    evaluation = _evaluate_system_case(
        case=case,
        turns=turns,
        validation_results=validation_results,
        provider_failure=provider_failure,
        provider_failure_reason=provider_failure_reason,
        planning_key="has_todo_list",
        signature_key="latest_todo_signature",
    )
    return {
        "case_name": case.name,
        "description": case.description,
        "home": str(home),
        "workspace": str(workspace),
        "thread_id": last_thread_id,
        "turns": turns,
        "evaluation": evaluation,
    }


def _run_agenthub_case_once(
    *,
    attempt_root: Path,
    case: planning_probe.CaseSpec,
    selection_override: planning_probe.ScriptProviderSelectionOverride,
    timeout_seconds: int,
) -> dict[str, Any]:
    home = attempt_root / "agenthub_home"
    workspace = attempt_root / "workspace"
    log_dir = attempt_root / "agenthub"
    provider_fixture = planning_probe._prepare_agenthub_home(home, selection_override=selection_override)
    workspace.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    planning_probe._seed_workspace(workspace, case.seed_files)

    stderr_path = log_dir / "serve.stderr.txt"
    serve_stdout_path = log_dir / "serve.stdout.jsonl"
    env = os.environ.copy()
    planning_probe.apply_script_provider_materialization_env(env, fixture=provider_fixture)
    env["AGENTHUB_DEBUG_LOG_DIR"] = str(log_dir)
    env["AGENTHUB_DEBUG_RESPONSES_TIMELINE"] = str(log_dir / "serve.timeline.jsonl")

    command = [
        sys.executable,
        str(planning_probe.AGENTHUB_MAIN),
        "--headless",
        "--serve",
        "--approval-policy",
        "never",
        "--sandbox-mode",
        "danger-full-access",
    ]
    stderr_file = open(stderr_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        command,
        cwd=str(workspace),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr_file,
        text=True,
        bufsize=1,
    )

    turns: list[dict[str, Any]] = []
    serve_lines: list[dict[str, Any]] = []
    provider_failure = False
    provider_failure_reason = ""
    shutdown: dict[str, Any] = {}
    try:
        for turn_index, prompt in enumerate(case.prompts, start=1):
            if proc.stdin is None:
                raise RuntimeError("missing serve stdin pipe")
            request = {"id": f"turn{turn_index}", "prompt": prompt}
            started = time.time()
            proc.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            response_line = planning_probe._wait_for_json_line(proc.stdout, timeout_seconds)
            elapsed = round(time.time() - started, 3)
            serve_lines.append(response_line)
            _write_text(
                serve_stdout_path,
                "\n".join(json.dumps(item, ensure_ascii=False) for item in serve_lines) + "\n",
            )
            if response_line.get("type") != "response" or response_line.get("id") != f"turn{turn_index}":
                raise RuntimeError(f"unexpected serve response: {response_line}")
            payload = dict(response_line.get("response") or {})
            turn_dir = log_dir / f"turn{turn_index}"
            turn_dir.mkdir(parents=True, exist_ok=True)
            response_path = turn_dir / "response.json"
            _write_json(response_path, payload)
            parsed = planning_probe._agenthub_turn_summary(payload)
            assistant_text = str(parsed.get("assistant_text") or "")
            if planning_probe._looks_like_provider_unavailable(assistant_text):
                provider_failure = True
                provider_failure_reason = assistant_text
            turns.append(
                {
                    "turn": turn_index,
                    "prompt": prompt,
                    "elapsed_s": elapsed,
                    "response_path": str(response_path),
                    "parsed": parsed,
                    "files_after": _inventory(workspace),
                }
            )
            if provider_failure:
                break
    finally:
        shutdown = planning_probe._shutdown_serve_process(
            proc,
            stderr_file=stderr_file,
            stdout_tail_path=log_dir / "serve.stdout.tail.txt",
        )
        returncode = int(shutdown.get("returncode") or 0)

    validation_results = planning_probe._run_validation(
        workspace=workspace,
        out_dir=attempt_root / "validation",
        commands=case.validation_commands,
    )
    evaluation = _evaluate_system_case(
        case=case,
        turns=turns,
        validation_results=validation_results,
        provider_failure=provider_failure,
        provider_failure_reason=provider_failure_reason,
        planning_key="has_todo_list",
        signature_key="latest_todo_signature",
    )
    return {
        "case_name": case.name,
        "description": case.description,
        "home": str(home),
        "workspace": str(workspace),
        "serve_cmd": command,
        "serve_returncode": int(returncode),
        "serve_shutdown": shutdown,
        "serve_stderr_path": str(stderr_path),
        "turns": turns,
        "evaluation": evaluation,
    }


def _evaluate_system_case(
    *,
    case: planning_probe.CaseSpec,
    turns: list[dict[str, Any]],
    validation_results: list[dict[str, Any]],
    provider_failure: bool,
    provider_failure_reason: str,
    planning_key: str,
    signature_key: str,
) -> dict[str, Any]:
    plan_turns = [int(turn.get("turn")) for turn in turns if turn.get("parsed", {}).get(planning_key)]
    signatures = [
        tuple(turn.get("parsed", {}).get(signature_key) or [])
        for turn in turns
        if turn.get("parsed", {}).get(signature_key)
    ]
    unique_signatures: list[tuple[str, ...]] = []
    for signature in signatures:
        if signature not in unique_signatures:
            unique_signatures.append(signature)
    last_inventory = {str(item.get("path") or "") for item in list((turns[-1] if turns else {}).get("files_after") or [])}
    issues: list[str] = []
    if provider_failure:
        issues.append(f"provider failure: {provider_failure_reason or 'unknown'}")
    if case.expect_no_plan:
        if plan_turns:
            issues.append(f"expected no planning, but planning appeared on turns {plan_turns}")
    else:
        if len(plan_turns) < int(case.min_plan_turns or 0):
            issues.append(f"expected at least {case.min_plan_turns} plan-bearing turns, got {len(plan_turns)}")
        if case.require_replan and len(unique_signatures) < 2:
            issues.append("expected a replan across turns, but plan signatures did not change")
    for turn in turns:
        parsed = dict(turn.get("parsed") or {})
        turn_id = int(turn.get("turn") or 0)
        if parsed.get(planning_key):
            if parsed.get("stale_open_todo"):
                issues.append(f"turn {turn_id}: todo_list remained open at turn end")
            if int(parsed.get("max_in_progress_count") or 0) > 1:
                issues.append(f"turn {turn_id}: more than one in_progress plan step observed")
            if not parsed.get("latest_todo_all_completed"):
                issues.append(f"turn {turn_id}: latest todo_list snapshot was not fully completed")
    for expected in list(case.expected_files or ()):
        if expected not in last_inventory:
            issues.append(f"missing expected file: {expected}")
    for forbidden in list(case.forbidden_files or ()):
        if forbidden in last_inventory:
            issues.append(f"unexpected leftover file: {forbidden}")
    for result in list(validation_results or []):
        if int(result.get("returncode") or 0) != 0:
            issues.append(f"validation failed: {result.get('name')} rc={result.get('returncode')}")
    return {
        "passed": not issues,
        "issues": issues,
        "plan_turns": plan_turns,
        "unique_plan_signatures": [list(signature) for signature in unique_signatures],
        "replan_detected": len(unique_signatures) >= 2,
        "validation_results": validation_results,
        "final_inventory": sorted(path for path in last_inventory if path),
        "provider_failure": provider_failure,
        "provider_failure_reason": provider_failure_reason,
    }


def _run_case_once(
    *,
    attempt_root: Path,
    case: planning_probe.CaseSpec,
    selection_override: planning_probe.ScriptProviderSelectionOverride,
    timeout_seconds: int,
) -> dict[str, Any]:
    systems = {
        "agenthub": _run_agenthub_case_once(
            attempt_root=attempt_root / "agenthub_system",
            case=case,
            selection_override=selection_override,
            timeout_seconds=timeout_seconds,
        ),
        "codex": _run_codex_case_once(
            attempt_root=attempt_root / "codex_system",
            case=case,
            timeout_seconds=timeout_seconds,
        ),
    }
    return {
        "case_name": case.name,
        "description": case.description,
        "attempt_root": str(attempt_root),
        "systems": systems,
    }
