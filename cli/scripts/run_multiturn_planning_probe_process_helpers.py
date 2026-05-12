from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

try:
    from cli.scripts.run_multiturn_planning_probe_case_helpers import CaseSpec
    from cli.scripts.run_multiturn_planning_probe_evaluation_helpers import (
        _agenthub_turn_summary,
        _evaluate_case,
        _looks_like_provider_unavailable,
    )
    from cli.scripts.run_multiturn_planning_probe_runtime_helpers import (
        AGENTHUB_MAIN,
        ScriptProviderSelectionOverride,
        _inventory,
        _now_iso,
        _prepare_agenthub_home,
        _run_validation,
        _seed_workspace,
        _write_json,
        _write_text,
        apply_script_provider_materialization_env,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from run_multiturn_planning_probe_case_helpers import CaseSpec  # type: ignore[no-redef]
    from run_multiturn_planning_probe_evaluation_helpers import (  # type: ignore[no-redef]
        _agenthub_turn_summary,
        _evaluate_case,
        _looks_like_provider_unavailable,
    )
    from run_multiturn_planning_probe_runtime_helpers import (  # type: ignore[no-redef]
        AGENTHUB_MAIN,
        ScriptProviderSelectionOverride,
        _inventory,
        _now_iso,
        _prepare_agenthub_home,
        _run_validation,
        _seed_workspace,
        _write_json,
        _write_text,
        apply_script_provider_materialization_env,
    )


def _wait_for_json_line(stream: Any, timeout_s: int) -> dict[str, Any]:
    if stream is None:
        raise RuntimeError("missing serve stdout pipe")
    deadline = time.time() + max(timeout_s, 1)
    buffer = ""
    while time.time() < deadline:
        remaining = max(deadline - time.time(), 0.1)
        ready, _, _ = select.select([stream], [], [], min(remaining, 1.0))
        if not ready:
            continue
        chunk = stream.readline()
        if not chunk:
            raise RuntimeError("serve stdout closed before response")
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            stripped = line.strip()
            if not stripped:
                continue
            return json.loads(stripped)
    raise TimeoutError(f"timed out waiting for serve response after {timeout_s}s")


def _write_optional_text(path: Path | None, text: str) -> str:
    if path is None:
        return ""
    _write_text(path, text)
    return str(path)


def _shutdown_serve_process(
    proc: subprocess.Popen[str],
    *,
    stderr_file: Any,
    stdout_tail_path: Path | None = None,
    wait_timeout_s: int = 30,
    terminate_timeout_s: int = 5,
    kill_timeout_s: int = 10,
) -> dict[str, Any]:
    stdout_tail_parts: list[str] = []
    stdout_drain_error = ""

    def _drain_stdout() -> None:
        nonlocal stdout_drain_error
        stream = proc.stdout
        if stream is None:
            return
        try:
            remainder = stream.read()
            if remainder:
                stdout_tail_parts.append(remainder)
        except Exception as exc:
            stdout_drain_error = f"{exc.__class__.__name__}: {exc}"
        finally:
            try:
                stream.close()
            except Exception:
                pass

    drain_thread: threading.Thread | None = None
    if proc.stdout is not None:
        drain_thread = threading.Thread(
            target=_drain_stdout,
            name="agenthub-serve-stdout-drain",
            daemon=True,
        )
        drain_thread.start()

    started = time.time()
    if proc.stdin is not None and not proc.stdin.closed:
        proc.stdin.close()

    terminated = False
    killed = False
    try:
        returncode = proc.wait(timeout=max(wait_timeout_s, 1))
    except subprocess.TimeoutExpired:
        terminated = True
        proc.terminate()
        try:
            returncode = proc.wait(timeout=max(terminate_timeout_s, 1))
        except subprocess.TimeoutExpired:
            killed = True
            proc.kill()
            returncode = proc.wait(timeout=max(kill_timeout_s, 1))
    finally:
        if drain_thread is not None:
            drain_thread.join(timeout=1.0)
        stderr_file.close()

    stdout_tail = "".join(stdout_tail_parts)
    stdout_tail_file = _write_optional_text(stdout_tail_path, stdout_tail) if stdout_tail else ""
    return {
        "returncode": int(returncode),
        "terminated": terminated,
        "killed": killed,
        "shutdown_elapsed_s": round(time.time() - started, 3),
        "stdout_tail_path": stdout_tail_file,
        "stdout_tail_bytes": len(stdout_tail.encode("utf-8")),
        "stdout_drain_error": stdout_drain_error,
        "stdout_drain_thread_alive": bool(drain_thread is not None and drain_thread.is_alive()),
    }


def _run_case_once(
    *,
    attempt_root: Path,
    case: CaseSpec,
    selection_override: ScriptProviderSelectionOverride,
    timeout_seconds: int,
) -> dict[str, Any]:
    home = attempt_root / "agenthub_home"
    workspace = attempt_root / "workspace"
    log_dir = attempt_root / "agenthub"
    provider_fixture = _prepare_agenthub_home(home, selection_override=selection_override)
    workspace.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    _seed_workspace(workspace, case.seed_files)

    stderr_path = log_dir / "serve.stderr.txt"
    serve_stdout_path = log_dir / "serve.stdout.jsonl"
    env = os.environ.copy()
    apply_script_provider_materialization_env(env, fixture=provider_fixture)
    env["AGENTHUB_DEBUG_LOG_DIR"] = str(log_dir)
    env["AGENTHUB_DEBUG_RESPONSES_TIMELINE"] = str(log_dir / "serve.timeline.jsonl")

    command = [
        sys.executable,
        str(AGENTHUB_MAIN),
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
            response_line = _wait_for_json_line(proc.stdout, timeout_seconds)
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
            parsed = _agenthub_turn_summary(payload)
            assistant_text = str(parsed.get("assistant_text") or "")
            if _looks_like_provider_unavailable(assistant_text):
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
        shutdown = _shutdown_serve_process(
            proc,
            stderr_file=stderr_file,
            stdout_tail_path=log_dir / "serve.stdout.tail.txt",
        )
        returncode = int(shutdown.get("returncode") or 0)

    validation_results = _run_validation(
        workspace=workspace,
        out_dir=attempt_root / "validation",
        commands=case.validation_commands,
    )
    evaluation = _evaluate_case(
        case=case,
        turns=turns,
        validation_results=validation_results,
        provider_failure=provider_failure,
        provider_failure_reason=provider_failure_reason,
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


def _run_case_with_retries(
    *,
    root_dir: Path,
    case: CaseSpec,
    selection_override: ScriptProviderSelectionOverride,
    timeout_seconds: int,
    retry_attempts: int,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for attempt_index in range(1, max(1, retry_attempts) + 1):
        attempt_root = root_dir / case.name / f"attempt_{attempt_index:02d}"
        started = _now_iso()
        result = _run_case_once(
            attempt_root=attempt_root,
            case=case,
            selection_override=selection_override,
            timeout_seconds=timeout_seconds,
        )
        finished = _now_iso()
        result["attempt_index"] = attempt_index
        result["attempt_root"] = str(attempt_root)
        result["started_at"] = started
        result["finished_at"] = finished
        attempts.append(result)
        if not result.get("evaluation", {}).get("provider_failure"):
            break
    chosen = dict(attempts[-1])
    chosen["attempts"] = attempts
    chosen["provider_failure_retried"] = len(attempts) > 1
    return chosen
