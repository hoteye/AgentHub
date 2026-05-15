from __future__ import annotations

import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    from cli.scripts.claude_request_capture_proxy import write_claude_proxy_settings
    from cli.scripts.file_write_alignment_ab_case_helpers import CLAUDE_BIN, CaseSpec
    from cli.scripts.file_write_alignment_ab_io_helpers import (
        _collect_expected_file_results,
        _copy_workspace_files,
        _write_json,
        _write_text,
    )
    from cli.scripts.file_write_alignment_ab_parser_helpers import _parse_claude_stream
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from claude_request_capture_proxy import write_claude_proxy_settings  # type: ignore[no-redef]
    from file_write_alignment_ab_case_helpers import CLAUDE_BIN, CaseSpec  # type: ignore[no-redef]
    from file_write_alignment_ab_io_helpers import (  # type: ignore[no-redef]
        _collect_expected_file_results,
        _copy_workspace_files,
        _write_json,
        _write_text,
    )
    from file_write_alignment_ab_parser_helpers import (
        _parse_claude_stream,  # type: ignore[no-redef]
    )


__all__ = (
    "_claude_command",
    "_claude_env",
    "_resolved_claude_settings_file",
    "_run_claude_case",
)


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
