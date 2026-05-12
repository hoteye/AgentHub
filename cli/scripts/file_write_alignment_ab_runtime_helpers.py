from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    from cli.scripts.claude_request_capture_proxy import write_claude_proxy_settings
    from cli.scripts.file_write_alignment_ab_case_helpers import (
        AGENTHUB_MAIN,
        CLAUDE_BIN,
        CLI_ROOT,
        CODEX_BIN,
        CaseSpec,
    )
    from cli.scripts.file_write_alignment_ab_io_helpers import (
        _collect_expected_file_results,
        _copy_workspace_files,
        _load_toml,
        _wait_for_json_line,
        _write_json,
        _write_text,
    )
    from cli.scripts.file_write_alignment_ab_parser_helpers import (
        _parse_agenthub_request_tool_names,
        _parse_agenthub_turn,
        _parse_claude_stream,
        _parse_codex_stdout,
    )
    from cli.scripts.script_runtime_helpers import (
        apply_script_provider_materialization_env,
        materialize_script_provider_fixture,
        resolve_codex_source_paths,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from claude_request_capture_proxy import write_claude_proxy_settings  # type: ignore[no-redef]
    from file_write_alignment_ab_case_helpers import (  # type: ignore[no-redef]
        AGENTHUB_MAIN,
        CLAUDE_BIN,
        CLI_ROOT,
        CODEX_BIN,
        CaseSpec,
    )
    from file_write_alignment_ab_io_helpers import (  # type: ignore[no-redef]
        _collect_expected_file_results,
        _copy_workspace_files,
        _load_toml,
        _wait_for_json_line,
        _write_json,
        _write_text,
    )
    from file_write_alignment_ab_parser_helpers import (  # type: ignore[no-redef]
        _parse_agenthub_request_tool_names,
        _parse_agenthub_turn,
        _parse_claude_stream,
        _parse_codex_stdout,
    )
    from script_runtime_helpers import (  # type: ignore[no-redef]
        apply_script_provider_materialization_env,
        materialize_script_provider_fixture,
        resolve_codex_source_paths,
    )


def _prepare_agenthub_home(target_home: Path) -> Any:
    return materialize_script_provider_fixture(cwd=CLI_ROOT, target_root=target_home)


def _run_agenthub_case(
    *,
    case: CaseSpec,
    root: Path,
    timeout_seconds: int,
    model: str,
    reasoning_effort: str,
) -> dict[str, Any]:
    home = root / "agenthub_home"
    workspace = root / "workspace"
    log_dir = root / "logs"
    provider_fixture = _prepare_agenthub_home(home)
    workspace.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    _copy_workspace_files(workspace, case.initial_files)

    env = os.environ.copy()
    apply_script_provider_materialization_env(env, fixture=provider_fixture)
    env["AGENT_CLI_PROVIDER"] = "anthropic"
    env["AGENT_CLI_MODEL"] = model
    env["AGENT_CLI_REASONING_EFFORT"] = reasoning_effort
    env["AGENTHUB_DEBUG_LOG_DIR"] = str(log_dir)
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
    stderr_path = root / "serve.stderr.txt"
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
    try:
        for index, prompt in enumerate(case.prompts, start=1):
            request = {"id": f"turn{index}", "prompt": prompt}
            if proc.stdin is None:
                raise RuntimeError("agenthub serve stdin unavailable")
            started = time.time()
            proc.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            response_line = _wait_for_json_line(proc.stdout, timeout_seconds)
            elapsed = round(time.time() - started, 3)
            payload = dict(response_line.get("response") or {})
            turn_summary = _parse_agenthub_turn(payload)
            turns.append(
                {
                    "turn": index,
                    "prompt": prompt,
                    "elapsed_s": elapsed,
                    **turn_summary,
                }
            )
    finally:
        if proc.stdin is not None and not proc.stdin.closed:
            proc.stdin.close()
        try:
            returncode = proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            returncode = proc.wait(timeout=10)
        stderr_file.close()
    file_results = _collect_expected_file_results(workspace, case.expected_files)
    return {
        "system": "agenthub",
        "workspace": str(workspace),
        "turns": turns,
        "returncode": int(returncode),
        "stderr_path": str(stderr_path),
        "request_tool_names": _parse_agenthub_request_tool_names(log_dir),
        "file_results": file_results,
        "success": returncode == 0 and all(item["ok"] for item in file_results),
    }


def _prepare_codex_home(target_home: Path, workspace: Path) -> None:
    target_home.mkdir(parents=True, exist_ok=True)
    source_paths = resolve_codex_source_paths()
    config_text = source_paths.config_path.read_text(encoding="utf-8")
    config_text += f'\n[projects."{workspace}"]\ntrust_level = "trusted"\n'
    _write_text(target_home / "config.toml", config_text)
    shutil.copy(source_paths.auth_path, target_home / "auth.json")
    if source_paths.skills_dir.exists() and not (target_home / "skills").exists():
        os.symlink(source_paths.skills_dir, target_home / "skills")


def _codex_exec_command(
    *,
    prompt: str,
    turn_dir: Path,
    reasoning_effort: str,
    resume: bool,
) -> list[str]:
    last_message_path = turn_dir / "last_message.txt"
    command = [str(CODEX_BIN), "exec"]
    if resume:
        command.extend(["resume", "--last"])
    command.extend(
        [
            "--dangerously-bypass-approvals-and-sandbox",
            "--json",
            "-o",
            str(last_message_path),
            "--skip-git-repo-check",
            "-c",
            f'model_reasoning_effort="{reasoning_effort}"',
            prompt,
        ]
    )
    return command


def _run_codex_case(
    *,
    case: CaseSpec,
    root: Path,
    timeout_seconds: int,
    reasoning_effort: str,
) -> dict[str, Any]:
    workspace = root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    _copy_workspace_files(workspace, case.initial_files)
    home = root / "codex_home"
    _prepare_codex_home(home, workspace)
    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    turns: list[dict[str, Any]] = []
    returncode = 0
    for index, prompt in enumerate(case.prompts, start=1):
        turn_dir = root / f"turn{index}"
        turn_dir.mkdir(parents=True, exist_ok=True)
        command = _codex_exec_command(
            prompt=prompt,
            turn_dir=turn_dir,
            reasoning_effort=reasoning_effort,
            resume=index > 1,
        )
        started = time.time()
        proc = subprocess.run(
            command,
            cwd=str(workspace),
            env=env,
            input="",
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        elapsed = round(time.time() - started, 3)
        returncode = int(proc.returncode)
        stdout_path = turn_dir / "stdout.jsonl"
        stderr_path = turn_dir / "stderr.txt"
        _write_text(stdout_path, proc.stdout)
        _write_text(stderr_path, proc.stderr)
        parsed = _parse_codex_stdout(proc.stdout, turn_dir / "last_message.txt")
        turns.append(
            {
                "turn": index,
                "prompt": prompt,
                "elapsed_s": elapsed,
                "assistant_text": parsed["assistant_text"],
                "tool_like_items": parsed["tool_like_items"],
                "returncode": returncode,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
            }
        )
        if returncode != 0:
            break
    file_results = _collect_expected_file_results(workspace, case.expected_files)
    config_data = _load_toml(home / "config.toml")
    return {
        "system": "codex",
        "workspace": str(workspace),
        "turns": turns,
        "returncode": returncode,
        "configured_model": str(config_data.get("model") or ""),
        "configured_provider": str(config_data.get("model_provider") or ""),
        "file_results": file_results,
        "success": returncode == 0 and all(item["ok"] for item in file_results),
    }


def _claude_env() -> dict[str, str]:
    return os.environ.copy()


def _resolved_claude_settings_file(
    *,
    root: Path,
    base_url: str,
    settings_file: str,
) -> str:
    explicit = str(settings_file or "").strip()
    if explicit:
        return str(Path(explicit).expanduser().resolve())
    requested_base_url = str(base_url or "").strip()
    if not requested_base_url:
        return ""
    generated_path = root / "claude_proxy_settings.json"
    write_claude_proxy_settings(
        output_path=generated_path,
        proxy_base_url=requested_base_url,
    )
    return str(generated_path)


def _claude_command(
    *,
    prompt: str,
    model: str,
    effort: str,
    session_id: str,
    settings_file: str,
    debug: str,
    debug_file: Path | None,
    include_hook_events: bool,
    include_partial_messages: bool,
) -> list[str]:
    command = [
        str(CLAUDE_BIN),
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "bypassPermissions",
        "--dangerously-skip-permissions",
        "--model",
        model,
        "--effort",
        effort,
    ]
    if str(settings_file or "").strip():
        command.extend(["--settings", str(settings_file).strip()])
    if include_hook_events:
        command.append("--include-hook-events")
    if include_partial_messages:
        command.append("--include-partial-messages")
    debug_value = str(debug or "").strip()
    if debug_value:
        command.append("--debug")
        if debug_value.lower() != "all":
            command.append(debug_value)
        if debug_file is not None:
            command.extend(["--debug-file", str(debug_file)])
    if session_id:
        command.extend(["--resume", session_id])
    command.append(prompt)
    return command


def _run_claude_case(
    *,
    case: CaseSpec,
    root: Path,
    timeout_seconds: int,
    model: str,
    effort: str,
    settings_file: str,
    base_url: str,
    debug: str,
    include_hook_events: bool,
    include_partial_messages: bool,
) -> dict[str, Any]:
    workspace = root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    _copy_workspace_files(workspace, case.initial_files)
    turns: list[dict[str, Any]] = []
    session_id = ""
    returncode = 0
    observed_tools: list[str] = []
    effective_settings_file = _resolved_claude_settings_file(
        root=root,
        base_url=base_url,
        settings_file=settings_file,
    )
    env = _claude_env()
    for index, prompt in enumerate(case.prompts, start=1):
        turn_dir = root / f"turn{index}"
        turn_dir.mkdir(parents=True, exist_ok=True)
        debug_path = turn_dir / "debug.log" if str(debug or "").strip() else None
        command = _claude_command(
            prompt=prompt,
            model=model,
            effort=effort,
            session_id=session_id,
            settings_file=effective_settings_file,
            debug=debug,
            debug_file=debug_path,
            include_hook_events=include_hook_events,
            include_partial_messages=include_partial_messages,
        )
        _write_text(turn_dir / "command.txt", shlex.join(command) + "\n")
        _write_json(
            turn_dir / "env.json",
            {
                "ANTHROPIC_BASE_URL": str(base_url or ""),
                "claude_settings_file": effective_settings_file,
                "claude_debug": str(debug or ""),
                "claude_include_hook_events": bool(include_hook_events),
                "claude_include_partial_messages": bool(include_partial_messages),
            },
        )
        started = time.time()
        proc = subprocess.run(
            command,
            cwd=str(workspace),
            env=env,
            input="",
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        elapsed = round(time.time() - started, 3)
        returncode = int(proc.returncode)
        stdout_path = turn_dir / "stdout.jsonl"
        stderr_path = turn_dir / "stderr.txt"
        _write_text(stdout_path, proc.stdout)
        _write_text(stderr_path, proc.stderr)
        parsed = _parse_claude_stream(proc.stdout)
        session_id = str(parsed.get("session_id") or session_id)
        if not observed_tools:
            observed_tools = list(parsed.get("system_tools") or [])
        turns.append(
            {
                "turn": index,
                "prompt": prompt,
                "elapsed_s": elapsed,
                "assistant_text": parsed["assistant_text"],
                "tool_use_names": parsed["tool_use_names"],
                "returncode": returncode,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "debug_path": str(debug_path) if debug_path is not None else "",
            }
        )
        if returncode != 0:
            break
    file_results = _collect_expected_file_results(workspace, case.expected_files)
    return {
        "system": "claude_code",
        "workspace": str(workspace),
        "turns": turns,
        "returncode": returncode,
        "session_id": session_id,
        "system_tools": observed_tools,
        "base_url": str(base_url or ""),
        "settings_file": effective_settings_file,
        "debug": str(debug or ""),
        "include_hook_events": bool(include_hook_events),
        "include_partial_messages": bool(include_partial_messages),
        "file_results": file_results,
        "success": returncode == 0 and all(item["ok"] for item in file_results),
    }
