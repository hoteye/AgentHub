from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    from cli.scripts.run_multiturn_coding_ab_model_io_helpers import _write_text
    from cli.scripts.script_runtime_helpers import normalize_script_validation_command
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from run_multiturn_coding_ab_model_io_helpers import _write_text  # type: ignore[no-redef]
    from script_runtime_helpers import normalize_script_validation_command  # type: ignore[no-redef]


def _looks_like_provider_unavailable(text: str) -> bool:
    normalized = str(text or "").lower()
    needles = (
        "proxy_unavailable",
        "all accounts are currently unavailable",
        "当前 provider 调用失败",
        "provider failure",
        "provider 暂不可用",
    )
    return any(needle in normalized for needle in needles)


def _agenthub_turn_summary(payload: dict[str, Any]) -> dict[str, Any]:
    tool_events = list(payload.get("tool_events") or [])
    response_items = [
        item for item in list(payload.get("response_items") or []) if isinstance(item, dict)
    ]
    return {
        "assistant_text": str(payload.get("assistant_text") or ""),
        "commentary_text": str(payload.get("commentary_text") or ""),
        "tool_event_count": len(tool_events),
        "tool_names": [
            str(item.get("name") or "") for item in tool_events if isinstance(item, dict)
        ],
        "response_item_types": [str(item.get("type") or "") for item in response_items],
        "turn_event_count": len(list(payload.get("turn_events") or [])),
        "status": dict(payload.get("status") or {}),
        "protocol_diagnostics": dict(payload.get("protocol_diagnostics") or {}),
    }


def _parse_codex_stdout(stdout_text: str, last_message_path: Path) -> dict[str, Any]:
    event_types: list[str] = []
    item_counts: dict[str, int] = {}
    completed_item_counts: dict[str, int] = {}
    errors: list[str] = []
    agent_messages: list[str] = []
    thread_id = ""
    turn_completed = 0
    for raw_line in stdout_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue
        event_type = str(event.get("type") or "")
        if event_type:
            event_types.append(event_type)
        if event_type == "thread.started":
            thread_id = str(event.get("thread_id") or thread_id)
        elif event_type == "turn.completed":
            turn_completed += 1
        elif event_type == "error":
            message = str(event.get("message") or "").strip()
            if message:
                errors.append(message)
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "")
        if item_type:
            item_counts[item_type] = item_counts.get(item_type, 0) + 1
            if event_type == "item.completed":
                completed_item_counts[item_type] = completed_item_counts.get(item_type, 0) + 1
        if item_type == "agent_message":
            text = str(item.get("text") or "").strip()
            if text:
                agent_messages.append(text)
        elif item_type == "error":
            message = str(item.get("message") or "").strip()
            if message:
                errors.append(message)
    assistant_text = ""
    if last_message_path.exists():
        assistant_text = last_message_path.read_text(encoding="utf-8").strip()
    if not assistant_text and agent_messages:
        assistant_text = agent_messages[-1]
    return {
        "assistant_text": assistant_text,
        "thread_id": thread_id,
        "event_types": event_types,
        "item_counts": item_counts,
        "completed_item_counts": completed_item_counts,
        "agent_message_count": len(agent_messages),
        "turn_completed": turn_completed,
        "errors": errors,
    }


def _run_validation(workspace: Path, out_dir: Path) -> list[dict[str, Any]]:
    checks = (
        ("human_output", ["python3", "task_stats.py", "sample_tasks.txt"]),
        ("json_output", ["python3", "task_stats.py", "sample_tasks.txt", "--json"]),
        ("pytest", ["pytest", "-q"]),
    )
    results: list[dict[str, Any]] = []
    for name, command in checks:
        effective_command = normalize_script_validation_command(command)
        started = time.time()
        proc = subprocess.run(
            effective_command,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        elapsed = round(time.time() - started, 3)
        stdout_path = out_dir / f"{name}.stdout.txt"
        stderr_path = out_dir / f"{name}.stderr.txt"
        _write_text(stdout_path, proc.stdout)
        _write_text(stderr_path, proc.stderr)
        results.append(
            {
                "name": name,
                "cmd": command,
                "effective_cmd": effective_command,
                "returncode": int(proc.returncode),
                "elapsed_s": elapsed,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
            }
        )
    return results


def _attempt_success(system_result: dict[str, Any], expected_turns: int) -> bool:
    turns = list(system_result.get("turns") or [])
    if len(turns) != expected_turns:
        return False
    if bool(system_result.get("provider_failure")):
        return False
    for turn in turns:
        if int(turn.get("returncode") or 0) != 0:
            return False
    return True


def _render_markdown(report: dict[str, Any]) -> str:
    attempts_used = report.get("attempts_used")
    if attempts_used is None:
        attempts_used = report.get("attempt_index", "-")
    lines = [
        f"# {report['case_name']}",
        "",
        f"- started_at: {report['started_at']}",
        f"- ended_at: {report['ended_at']}",
        f"- attempts_used: {attempts_used}",
        f"- reasoning_effort: {report['reasoning_effort']}",
        f"- out_root: `{report['root']}`",
        "",
    ]
    for system_name in ("agenthub", "codex"):
        system = report["systems"][system_name]
        lines.extend(
            [
                f"## {system_name}",
                "",
                f"- workspace: `{system['workspace']}`",
                f"- provider_failure: {'yes' if system['provider_failure'] else 'no'}",
            ]
        )
        if system.get("provider_failure_reason"):
            lines.append(f"- provider_failure_reason: `{system['provider_failure_reason'][:240]}`")
        lines.append("")
        lines.append("### Turns")
        lines.append("")
        for turn in system.get("turns", []):
            parsed = dict(turn.get("parsed") or {})
            excerpt = str(parsed.get("assistant_text") or "").replace("\n", " ").strip()
            if len(excerpt) > 220:
                excerpt = excerpt[:217] + "..."
            lines.extend(
                [
                    f"- turn {turn['turn']}: elapsed={turn['elapsed_s']}s",
                    f"  assistant: {excerpt or '-'}",
                ]
            )
            if system_name == "agenthub":
                lines.append(f"  tools: {parsed.get('tool_names') or []}")
            else:
                lines.append(f"  completed_items: {parsed.get('completed_item_counts') or {}}")
        lines.extend(["", "### Validation", ""])
        for item in system.get("validation", []):
            lines.append(
                f"- {item['name']}: rc={item['returncode']} elapsed={item['elapsed_s']}s stdout=`{item['stdout_path']}` stderr=`{item['stderr_path']}`"
            )
        lines.extend(["", "### Final Files", ""])
        final_files = [entry["path"] for entry in system.get("final_files", [])]
        if final_files:
            for path_text in final_files:
                lines.append(f"- {path_text}")
        else:
            lines.append("- none")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
