from __future__ import annotations

import json
import os
import select
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

try:
    from cli.scripts.approval_continuation_codex_ref_ab_case_helpers import AbCase
    from cli.scripts.approval_continuation_codex_ref_ab_model_helpers import (
        CommandResult,
        _file_state,
        _write_text,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from approval_continuation_codex_ref_ab_case_helpers import AbCase  # type: ignore[no-redef]
    from approval_continuation_codex_ref_ab_model_helpers import (  # type: ignore[no-redef]
        CommandResult,
        _file_state,
        _write_text,
    )


def _claude_prompt_for_case(case: AbCase) -> str:
    if case.tool_kind == "file_change":
        write_args = {"file_path": case.target_file, "content": f"{case.expected_content}\n"}
        return (
            "Use the `Write` tool exactly once in the current workspace with this exact JSON input:\n"
            f"{json.dumps(write_args, ensure_ascii=False)}\n"
            "Do not use Bash, Edit, or any other file-writing tool. "
            "Do not answer before the tool returns. "
            "After the tool returns, briefly state whether the write result was approved and visible."
        )
    bash_args = {"command": f"printf '{case.expected_content}\\n' > {case.target_file}"}
    return (
        "Use the `Bash` tool exactly once in the current workspace with this exact JSON input:\n"
        f"{json.dumps(bash_args, ensure_ascii=False)}\n"
        "Do not use Write, Edit, or any other file-writing tool. "
        "Do not answer before the tool returns. "
        "After the tool returns, briefly state whether the command result was approved and visible."
    )


def _permission_response_for_case(
    *,
    case: AbCase,
    request_id: str,
    tool_use_id: str,
) -> dict[str, Any]:
    if case.decision == "approve":
        response = {
            "behavior": "allow",
            "updatedInput": {},
            "toolUseID": tool_use_id,
            "decisionClassification": "user_temporary",
        }
    else:
        response = {
            "behavior": "deny",
            "message": "User denied permission",
            "toolUseID": tool_use_id,
            "decisionClassification": "user_reject",
        }
    return {
        "type": "control_response",
        "response": {
            "subtype": "success",
            "request_id": request_id,
            "response": response,
        },
    }


def _summarize_claude_lines(
    lines: list[dict[str, Any]], decisions: list[dict[str, Any]]
) -> dict[str, Any]:
    control_requests = [
        dict(line)
        for line in lines
        if line.get("type") == "control_request"
        and dict(line.get("request") or {}).get("subtype") == "can_use_tool"
    ]
    assistant_tool_uses: list[dict[str, Any]] = []
    result: dict[str, Any] = {}
    for line in lines:
        if line.get("type") == "result":
            result = dict(line)
        if line.get("type") != "assistant":
            continue
        message = dict(line.get("message") or {})
        for content in list(message.get("content") or []):
            if not isinstance(content, dict) or content.get("type") != "tool_use":
                continue
            assistant_tool_uses.append(
                {
                    "name": str(content.get("name") or ""),
                    "input": dict(content.get("input") or {}),
                    "id": str(content.get("id") or ""),
                }
            )
    request_summaries = []
    for item in control_requests:
        request = dict(item.get("request") or {})
        request_summaries.append(
            {
                "request_id": str(item.get("request_id") or ""),
                "tool_name": str(request.get("tool_name") or ""),
                "tool_use_id": str(request.get("tool_use_id") or ""),
                "description": str(request.get("description") or ""),
                "input": dict(request.get("input") or {}),
            }
        )
    return {
        "control_request_count": len(control_requests),
        "control_requests": request_summaries,
        "decision_count": len(decisions),
        "decisions": decisions,
        "assistant_tool_uses": assistant_tool_uses,
        "completed_turn": bool(result) and str(result.get("subtype") or "") == "success",
        "terminal_reason": str(result.get("terminal_reason") or ""),
        "result_text": str(result.get("result") or ""),
        "permission_denials_count": len(list(result.get("permission_denials") or [])),
    }


def _run_claude_code_case(
    *,
    case: AbCase,
    case_root: Path,
    claude_bin: str,
    claude_model: str,
    timeout_seconds: int,
    dry_run: bool,
) -> dict[str, Any]:
    workspace = case_root / "workspace"
    log_dir = case_root / "logs"
    stdout_path = log_dir / "claude.stdout.jsonl"
    stderr_path = log_dir / "claude.stderr.log"
    stdin_path = log_dir / "claude.stdin.jsonl"
    workspace.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    command = [
        str(claude_bin),
        "-p",
        "--verbose",
        "--output-format",
        "stream-json",
        "--input-format",
        "stream-json",
        "--permission-prompt-tool",
        "stdio",
        "--model",
        str(claude_model),
        "--permission-mode",
        "default",
        "--tools",
        "Bash,Write" if case.tool_kind == "file_change" else "Bash",
    ]
    prompt = _claude_prompt_for_case(case)
    if dry_run:
        _write_text(
            stdout_path,
            json.dumps({"dry_run": True, "command": command}, ensure_ascii=False) + "\n",
        )
        _write_text(stderr_path, "")
        _write_text(stdin_path, "")
        return {
            "run": asdict(
                CommandResult(
                    command=command,
                    cwd=str(workspace),
                    exit_code=0,
                    elapsed_seconds=0.0,
                    timed_out=False,
                    stdout_path=str(stdout_path),
                    stderr_path=str(stderr_path),
                )
            ),
            "workspace": str(workspace),
            "summary": {},
            "file": _file_state(workspace, case.target_file),
            "prompt": prompt,
            "stdin_path": str(stdin_path),
        }

    started = time.perf_counter()
    timed_out = False
    parsed_lines: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    env = os.environ.copy()
    proc = subprocess.Popen(
        command,
        cwd=str(workspace),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None
    user_message = {
        "type": "user",
        "message": {"role": "user", "content": prompt},
        "parent_tool_use_id": None,
    }
    with (
        stdout_path.open("w", encoding="utf-8") as stdout_file,
        stdin_path.open("w", encoding="utf-8") as stdin_file,
    ):
        line = json.dumps(user_message, ensure_ascii=False)
        proc.stdin.write(line + "\n")
        proc.stdin.flush()
        stdin_file.write(line + "\n")
        stdin_file.flush()
        deadline = time.monotonic() + timeout_seconds
        while True:
            if time.monotonic() >= deadline:
                timed_out = True
                proc.kill()
                break
            if proc.poll() is not None:
                break
            ready, _, _ = select.select([proc.stdout], [], [], 0.2)
            if not ready:
                continue
            raw_line = proc.stdout.readline()
            if not raw_line:
                continue
            stdout_file.write(raw_line)
            stdout_file.flush()
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                parsed_lines.append(event)
            if event.get("type") == "control_request":
                request = dict(event.get("request") or {})
                if request.get("subtype") == "can_use_tool":
                    response = _permission_response_for_case(
                        case=case,
                        request_id=str(event.get("request_id") or ""),
                        tool_use_id=str(request.get("tool_use_id") or ""),
                    )
                    decision_record = {
                        "request_id": str(event.get("request_id") or ""),
                        "tool_name": str(request.get("tool_name") or ""),
                        "tool_use_id": str(request.get("tool_use_id") or ""),
                        "decision": case.decision,
                    }
                    decisions.append(decision_record)
                    response_line = json.dumps(response, ensure_ascii=False)
                    proc.stdin.write(response_line + "\n")
                    proc.stdin.flush()
                    stdin_file.write(response_line + "\n")
                    stdin_file.flush()
            if event.get("type") == "result":
                break
    if proc.stdin is not None and not proc.stdin.closed:
        proc.stdin.close()
    try:
        returncode = proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        returncode = proc.wait(timeout=10)
    stderr_text = proc.stderr.read() if proc.stderr is not None else ""
    _write_text(stderr_path, stderr_text)
    elapsed = round(time.perf_counter() - started, 3)
    return {
        "run": asdict(
            CommandResult(
                command=command,
                cwd=str(workspace),
                exit_code=int(returncode),
                elapsed_seconds=elapsed,
                timed_out=timed_out,
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
            )
        ),
        "workspace": str(workspace),
        "summary": _summarize_claude_lines(parsed_lines, decisions),
        "file": _file_state(workspace, case.target_file),
        "prompt": prompt,
        "stdin_path": str(stdin_path),
    }
