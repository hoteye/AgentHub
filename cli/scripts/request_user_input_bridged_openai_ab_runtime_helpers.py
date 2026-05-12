from __future__ import annotations

import json
import select
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class ProbeResult:
    name: str
    transcript_path: Path
    stderr_path: Path
    tmp_root: Path
    transcript: list[dict[str, Any]]
    init_message: dict[str, Any]
    thread_response: dict[str, Any]
    turn_start_response: dict[str, Any]
    request_user_input_message: dict[str, Any] | None
    resolved_message: dict[str, Any] | None
    final_answer_message: dict[str, Any] | None
    completed_message: dict[str, Any]


def _json_line(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _read_message(stdout: Any, timeout: float = 1.0) -> dict[str, Any] | None:
    ready, _, _ = select.select([stdout], [], [], timeout)
    if not ready:
        return None
    line = stdout.readline()
    if not line:
        return None
    return json.loads(line)


def _read_until(
    *,
    process: subprocess.Popen[str],
    stdout: Any,
    transcript: list[dict[str, Any]],
    transcript_path: Path,
    predicate: Callable[[dict[str, Any]], bool],
    timeout: float,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"process exited early with rc={process.returncode}")
        message = _read_message(stdout, timeout=0.5)
        if message is None:
            continue
        transcript.append(message)
        _json_line(transcript_path, message)
        if predicate(message):
            return message
    raise TimeoutError(f"timeout after {timeout}s")


def _read_post_answer_until_completed(
    *,
    process: subprocess.Popen[str],
    stdout: Any,
    transcript: list[dict[str, Any]],
    transcript_path: Path,
    timeout: float,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any]]:
    deadline = time.time() + timeout
    resolved_message: dict[str, Any] | None = None
    final_answer_message: dict[str, Any] | None = None
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"process exited early with rc={process.returncode}")
        message = _read_message(stdout, timeout=0.5)
        if message is None:
            continue
        transcript.append(message)
        _json_line(transcript_path, message)
        method = str(message.get("method") or "")
        if method == "serverRequest/resolved" and resolved_message is None:
            resolved_message = message
        if method == "rawResponseItem/completed":
            params = dict(message.get("params") or {})
            item = dict(params.get("item") or {})
            if str(item.get("phase") or "") == "final_answer":
                final_answer_message = message
        if method == "item/completed":
            params = dict(message.get("params") or {})
            item = dict(params.get("item") or {})
            if str(item.get("type") or "") == "agentMessage" and str(item.get("phase") or "") == "final_answer":
                final_answer_message = message
        if method == "turn/completed":
            return resolved_message, final_answer_message, message
    synthetic_message = {
        "method": "turn/completed_missing",
        "synthetic": True,
        "params": {
            "threadId": "",
            "turn": {
                "id": "",
                "status": "completed_missing_notification",
                "error": {
                    "message": f"timed out after {timeout}s waiting for turn/completed",
                },
                "items": [],
            },
        },
    }
    if isinstance(final_answer_message, dict):
        params = dict(final_answer_message.get("params") or {})
        synthetic_message["params"]["threadId"] = params.get("threadId") or ""
        synthetic_message["params"]["turn"]["id"] = params.get("turnId") or ""
        synthetic_message["params"]["turn"]["error"]["message"] = (
            f"final answer observed, but turn/completed was not emitted within {timeout}s"
        )
    elif isinstance(resolved_message, dict):
        params = dict(resolved_message.get("params") or {})
        synthetic_message["params"]["threadId"] = params.get("threadId") or ""
    return resolved_message, final_answer_message, synthetic_message


def _send(stdin: Any, payload: dict[str, Any]) -> None:
    stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
    stdin.flush()


def _terminate_process(process: subprocess.Popen[str], stderr_handle: Any) -> None:
    try:
        if process.stdin is not None:
            process.stdin.close()
    except Exception:
        pass
    try:
        process.terminate()
        process.wait(timeout=5)
    except Exception:
        try:
            process.kill()
            process.wait(timeout=5)
        except Exception:
            pass
    stderr_handle.close()
