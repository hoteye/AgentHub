from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

try:
    from cli.scripts.request_user_input_bridged_openai_ab_provider_helpers import (
        _agenthub_command,
        _agenthub_config,
        _agenthub_env,
        _codex_command,
        _codex_config,
        _codex_env,
    )
    from cli.scripts.request_user_input_bridged_openai_ab_runtime_helpers import (
        ProbeResult,
        _read_post_answer_until_completed,
        _read_until,
        _send,
        _terminate_process,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from request_user_input_bridged_openai_ab_provider_helpers import (  # type: ignore[no-redef]
        _agenthub_command,
        _agenthub_config,
        _agenthub_env,
        _codex_command,
        _codex_config,
        _codex_env,
    )
    from request_user_input_bridged_openai_ab_runtime_helpers import (  # type: ignore[no-redef]
        ProbeResult,
        _read_post_answer_until_completed,
        _read_until,
        _send,
        _terminate_process,
    )


def run_agenthub_probe(
    *,
    out_dir: Path,
    repo_root: Path,
    auth_src: Path,
    prompt: str,
    answer: str,
    base_url: str,
    model: str,
    effort: str,
    completion_timeout: float,
) -> ProbeResult:
    tmp_root = Path(tempfile.mkdtemp(prefix="agenthub_req_input_live_", dir=str(out_dir)))
    provider_home = tmp_root / "provider_home"
    provider_home.mkdir()
    launch_cwd = tmp_root / "launch"
    launch_cwd.mkdir()
    shutil.copy2(auth_src, provider_home / "auth.json")
    (provider_home / "config.toml").write_text(_agenthub_config(base_url, model, effort), encoding="utf-8")

    transcript_path = out_dir / "agenthub.transcript.jsonl"
    stderr_path = out_dir / "agenthub.app_server.stderr.log"
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        _agenthub_command(repo_root),
        cwd=str(launch_cwd),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr_handle,
        text=True,
        bufsize=1,
        env=_agenthub_env(provider_home),
    )
    assert process.stdin and process.stdout
    transcript: list[dict[str, Any]] = []
    try:
        _send(
            process.stdin,
            {
                "id": "init",
                "method": "initialize",
                "params": {"clientInfo": {"name": "bridged-ab", "version": "1"}},
            },
        )
        init_message = _read_until(
            process=process,
            stdout=process.stdout,
            transcript=transcript,
            transcript_path=transcript_path,
            predicate=lambda msg: msg.get("id") == "init",
            timeout=15,
        )
        _send(process.stdin, {"method": "initialized", "params": {}})
        _send(
            process.stdin,
            {
                "id": "thread-start",
                "method": "thread/start",
                "params": {"cwd": str(repo_root)},
            },
        )
        thread_response = _read_until(
            process=process,
            stdout=process.stdout,
            transcript=transcript,
            transcript_path=transcript_path,
            predicate=lambda msg: msg.get("id") == "thread-start",
            timeout=15,
        )
        thread_id = str(thread_response["result"]["thread"]["thread_id"])
        _send(
            process.stdin,
            {
                "id": "turn1",
                "method": "turn/start",
                "params": {"threadId": thread_id, "input": [{"type": "text", "text": prompt}]},
            },
        )
        turn_start_response = _read_until(
            process=process,
            stdout=process.stdout,
            transcript=transcript,
            transcript_path=transcript_path,
            predicate=lambda msg: msg.get("id") == "turn1",
            timeout=30,
        )
        request_user_input_message = _read_until(
            process=process,
            stdout=process.stdout,
            transcript=transcript,
            transcript_path=transcript_path,
            predicate=lambda msg: msg.get("method") == "item/tool/requestUserInput",
            timeout=180,
        )
        _send(
            process.stdin,
            {
                "id": request_user_input_message["id"],
                "result": {"answers": {"preference": {"answers": [answer]}}},
            },
        )
        resolved_message, final_answer_message, completed_message = _read_post_answer_until_completed(
            process=process,
            stdout=process.stdout,
            transcript=transcript,
            transcript_path=transcript_path,
            timeout=completion_timeout,
        )
        return ProbeResult(
            name="agenthub",
            transcript_path=transcript_path,
            stderr_path=stderr_path,
            tmp_root=tmp_root,
            transcript=transcript,
            init_message=init_message,
            thread_response=thread_response,
            turn_start_response=turn_start_response,
            request_user_input_message=request_user_input_message,
            resolved_message=resolved_message,
            final_answer_message=final_answer_message,
            completed_message=completed_message,
        )
    finally:
        _terminate_process(process, stderr_handle)


def run_codex_probe(
    *,
    out_dir: Path,
    repo_root: Path,
    codex_bin: Path,
    auth_src: Path,
    prompt: str,
    answer: str,
    base_url: str,
    model: str,
    effort: str,
    completion_timeout: float,
) -> ProbeResult:
    tmp_root = Path(tempfile.mkdtemp(prefix="codex_req_input_live_", dir=str(out_dir)))
    codex_home = tmp_root / "codex_home"
    codex_home.mkdir()
    launch_cwd = tmp_root / "launch"
    launch_cwd.mkdir()
    shutil.copy2(auth_src, codex_home / "auth.json")
    (codex_home / "config.toml").write_text(_codex_config(base_url, model, effort), encoding="utf-8")

    transcript_path = out_dir / "codex.transcript.jsonl"
    stderr_path = out_dir / "codex.app_server.stderr.log"
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        _codex_command(codex_bin),
        cwd=str(launch_cwd),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr_handle,
        text=True,
        bufsize=1,
        env=_codex_env(codex_home),
    )
    assert process.stdin and process.stdout
    transcript: list[dict[str, Any]] = []
    try:
        _send(
            process.stdin,
            {
                "jsonrpc": "2.0",
                "id": "init",
                "method": "initialize",
                "params": {"clientInfo": {"name": "bridged-ab", "version": "1"}, "capabilities": {}},
            },
        )
        init_message = _read_until(
            process=process,
            stdout=process.stdout,
            transcript=transcript,
            transcript_path=transcript_path,
            predicate=lambda msg: msg.get("id") == "init",
            timeout=15,
        )
        _send(process.stdin, {"jsonrpc": "2.0", "method": "initialized", "params": {}})
        _send(
            process.stdin,
            {
                "jsonrpc": "2.0",
                "id": "thread-start",
                "method": "thread/start",
                "params": {"cwd": str(repo_root)},
            },
        )
        thread_response = _read_until(
            process=process,
            stdout=process.stdout,
            transcript=transcript,
            transcript_path=transcript_path,
            predicate=lambda msg: msg.get("id") == "thread-start",
            timeout=30,
        )
        thread_id = str(thread_response["result"]["thread"]["id"])
        _send(
            process.stdin,
            {
                "jsonrpc": "2.0",
                "id": "turn1",
                "method": "turn/start",
                "params": {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": prompt, "textElements": []}],
                    "cwd": str(repo_root),
                    "model": model,
                    "effort": effort,
                },
            },
        )
        turn_start_response = _read_until(
            process=process,
            stdout=process.stdout,
            transcript=transcript,
            transcript_path=transcript_path,
            predicate=lambda msg: msg.get("id") == "turn1",
            timeout=30,
        )
        request_user_input_message = _read_until(
            process=process,
            stdout=process.stdout,
            transcript=transcript,
            transcript_path=transcript_path,
            predicate=lambda msg: msg.get("method") == "item/tool/requestUserInput",
            timeout=180,
        )
        _send(
            process.stdin,
            {
                "jsonrpc": "2.0",
                "id": request_user_input_message["id"],
                "result": {"answers": {"preference": {"answers": [answer]}}},
            },
        )
        resolved_message, final_answer_message, completed_message = _read_post_answer_until_completed(
            process=process,
            stdout=process.stdout,
            transcript=transcript,
            transcript_path=transcript_path,
            timeout=completion_timeout,
        )
        return ProbeResult(
            name="codex",
            transcript_path=transcript_path,
            stderr_path=stderr_path,
            tmp_root=tmp_root,
            transcript=transcript,
            init_message=init_message,
            thread_response=thread_response,
            turn_start_response=turn_start_response,
            request_user_input_message=request_user_input_message,
            resolved_message=resolved_message,
            final_answer_message=final_answer_message,
            completed_message=completed_message,
        )
    finally:
        _terminate_process(process, stderr_handle)
