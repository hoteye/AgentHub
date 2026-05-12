from __future__ import annotations

import json
import os
import select
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    from cli.scripts.run_multiturn_coding_ab_evaluation_helpers import (
        _agenthub_turn_summary,
        _attempt_success,
        _looks_like_provider_unavailable,
        _parse_codex_stdout,
        _render_markdown,
        _run_validation,
    )
    from cli.scripts.run_multiturn_coding_ab_model_io_helpers import (
        CaseSpec,
        _inventory,
        _now_iso,
        _write_json,
        _write_text,
    )
    from cli.scripts.script_runtime_helpers import (
        apply_script_provider_materialization_env,
        ensure_script_import_paths,
        materialize_script_provider_fixture,
        resolve_codex_source_paths,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from run_multiturn_coding_ab_evaluation_helpers import (  # type: ignore[no-redef]
        _agenthub_turn_summary,
        _attempt_success,
        _looks_like_provider_unavailable,
        _parse_codex_stdout,
        _render_markdown,
        _run_validation,
    )
    from run_multiturn_coding_ab_model_io_helpers import (  # type: ignore[no-redef]
        CaseSpec,
        _inventory,
        _now_iso,
        _write_json,
        _write_text,
    )
    from script_runtime_helpers import (  # type: ignore[no-redef]
        apply_script_provider_materialization_env,
        ensure_script_import_paths,
        materialize_script_provider_fixture,
        resolve_codex_source_paths,
    )

_SCRIPT_PATHS = ensure_script_import_paths(__file__)
CLI_ROOT = _SCRIPT_PATHS.cli_root
AGENTHUB_MAIN = CLI_ROOT / "agent_cli" / "__main__.py"
CODEX_REF_ROOT = Path("/home/lyc/project/AgentHubRef/codex_ref")
CODEX_BIN = CODEX_REF_ROOT / "codex-rs" / "target" / "debug" / "codex"


def _prepare_agenthub_home(target_home: Path) -> Any:
    return materialize_script_provider_fixture(cwd=CLI_ROOT, target_root=target_home)


def _prepare_codex_home(target_home: Path, workspace: Path) -> None:
    target_home.mkdir(parents=True, exist_ok=True)
    source_paths = resolve_codex_source_paths()
    config_text = source_paths.config_path.read_text(encoding="utf-8")
    config_text += f'\n[projects."{workspace}"]\ntrust_level = "trusted"\n'
    _write_text(target_home / "config.toml", config_text)
    shutil.copy(source_paths.auth_path, target_home / "auth.json")
    if source_paths.skills_dir.exists() and not (target_home / "skills").exists():
        os.symlink(source_paths.skills_dir, target_home / "skills")


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


def _run_agenthub_case(
    *,
    attempt_root: Path,
    case: CaseSpec,
    reasoning_effort: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    home = attempt_root / "agenthub_home"
    workspace = attempt_root / "agenthub_workspace"
    log_dir = attempt_root / "agenthub"
    provider_fixture = _prepare_agenthub_home(home)
    workspace.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    stderr_path = log_dir / "serve.stderr.txt"
    serve_stdout_path = log_dir / "serve.stdout.jsonl"
    env = os.environ.copy()
    apply_script_provider_materialization_env(env, fixture=provider_fixture)
    env["AGENT_CLI_REASONING_EFFORT"] = reasoning_effort
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
        if proc.stdin is not None and not proc.stdin.closed:
            proc.stdin.close()
        try:
            returncode = proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            returncode = proc.wait(timeout=10)
        stderr_file.close()

    return {
        "home": str(home),
        "workspace": str(workspace),
        "serve_cmd": command,
        "serve_returncode": int(returncode),
        "serve_stderr_path": str(stderr_path),
        "turns": turns,
        "provider_failure": provider_failure,
        "provider_failure_reason": provider_failure_reason,
    }


def _codex_exec_command(
    *,
    prompt: str,
    turn_dir: Path,
    workspace: Path,
    resume: bool,
) -> list[str]:
    last_message_path = turn_dir / "last_message.txt"
    base = [str(CODEX_BIN), "exec"]
    if resume:
        base.extend(["resume", "--last"])
    base.extend(
        [
            "--dangerously-bypass-approvals-and-sandbox",
            "--json",
            "-o",
            str(last_message_path),
            "--skip-git-repo-check",
            prompt,
        ]
    )
    return base


def _run_codex_case(
    *,
    attempt_root: Path,
    case: CaseSpec,
    timeout_seconds: int,
) -> dict[str, Any]:
    home = attempt_root / "codex_home"
    workspace = attempt_root / "codex_workspace"
    log_dir = attempt_root / "codex"
    workspace.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    _prepare_codex_home(home, workspace)

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
            workspace=workspace,
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
        if _looks_like_provider_unavailable(failure_text):
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

    return {
        "home": str(home),
        "workspace": str(workspace),
        "turns": turns,
        "provider_failure": provider_failure,
        "provider_failure_reason": provider_failure_reason,
        "thread_id": last_thread_id,
    }


def _run_attempt(
    *,
    root: Path,
    case: CaseSpec,
    reasoning_effort: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "root": str(root),
        "case_name": case.name,
        "started_at": _now_iso(),
        "reasoning_effort": reasoning_effort,
        "prompts": list(case.prompts),
        "systems": {},
    }
    report["systems"]["agenthub"] = _run_agenthub_case(
        attempt_root=root,
        case=case,
        reasoning_effort=reasoning_effort,
        timeout_seconds=timeout_seconds,
    )
    report["systems"]["codex"] = _run_codex_case(
        attempt_root=root,
        case=case,
        timeout_seconds=timeout_seconds,
    )
    for system_name in ("agenthub", "codex"):
        system = report["systems"][system_name]
        workspace = Path(system["workspace"])
        system["validation"] = _run_validation(workspace, root / system_name / "validation")
        system["final_files"] = _inventory(workspace)
    report["ended_at"] = _now_iso()
    report["success"] = all(
        _attempt_success(report["systems"][name], expected_turns=len(case.prompts))
        for name in ("agenthub", "codex")
    )
    _write_json(root / "report.json", report)
    _write_text(root / "summary.md", _render_markdown(report))
    return report
