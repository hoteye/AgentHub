from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from cli.scripts.anthropic_tool_smoke_case_helpers import CaseDefinition
    from cli.scripts.anthropic_tool_smoke_payload_helpers import (
        _assistant_text,
        _canonical_tool_names,
        _projected_tool_names,
        _response_tool_names,
        _turn_item_types,
        _validation_result,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from anthropic_tool_smoke_case_helpers import CaseDefinition  # type: ignore[no-redef]
    from anthropic_tool_smoke_payload_helpers import (  # type: ignore[no-redef]
        _assistant_text,
        _canonical_tool_names,
        _projected_tool_names,
        _response_tool_names,
        _turn_item_types,
        _validation_result,
    )


_SCRIPT_PATH = Path(__file__).resolve()
CLI_ROOT = _SCRIPT_PATH.parents[1]
REPO_ROOT = _SCRIPT_PATH.parents[2]
DEFAULT_OUT_ROOT = Path("/tmp/agenthub_anthropic_tool_smoke")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _utc_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _launcher_prefix() -> list[str]:
    if os.name == "nt":
        launcher = CLI_ROOT / "scripts" / "start_agent_cli.ps1"
        return ["pwsh", "-NoLogo", "-NoProfile", "-File", str(launcher)]
    launcher = CLI_ROOT / "scripts" / "start_agent_cli.sh"
    return [str(launcher)]


def _parse_single_json(stdout: str) -> dict[str, Any]:
    text = str(stdout or "").strip()
    if not text:
        raise ValueError("stdout was empty; expected one JSON object")
    return dict(json.loads(text))


def _parse_serve_jsonl(stdout: str) -> dict[str, dict[str, Any]]:
    responses: dict[str, dict[str, Any]] = {}
    for raw in str(stdout or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        row = dict(json.loads(line))
        if str(row.get("type") or "").strip() != "response":
            continue
        response_id = str(row.get("id") or "").strip()
        if not response_id:
            continue
        responses[response_id] = {
            "envelope": row,
            "payload": dict(row.get("response") or {}),
            "exit_code": row.get("exit_code"),
        }
    return responses


def _run_single_case(
    case: CaseDefinition,
    *,
    case_dir: Path,
    args: argparse.Namespace,
    temp_workspace: Path,
) -> dict[str, Any]:
    workdir = temp_workspace if case.workspace == "temp" else REPO_ROOT
    command = [
        *_launcher_prefix(),
        "--",
        "--headless",
        "--json",
        "--approval-policy",
        str(args.approval_policy),
        "--sandbox-mode",
        str(args.sandbox_mode),
        "--web-search-mode",
        str(args.web_search_mode),
        "--network-access",
        str(args.network_access),
        "--prompt",
        str(case.prompt),
    ]
    started = time.monotonic()
    proc = subprocess.run(
        command,
        cwd=str(workdir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=args.timeout_seconds,
        check=False,
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    stdout_path = case_dir / "stdout.json"
    stderr_path = case_dir / "stderr.log"
    _write_text(stdout_path, proc.stdout or "")
    _write_text(stderr_path, proc.stderr or "")
    payload = _parse_single_json(proc.stdout)
    _write_json(case_dir / "response.pretty.json", payload)
    run = {
        "case_id": case.case_id,
        "mode": case.mode,
        "cwd": str(workdir),
        "workspace": str(temp_workspace),
        "payload": payload,
        "command": command,
        "duration_ms": duration_ms,
        "returncode": proc.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }
    validation = case.validator(run) if case.validator is not None else _validation_result("failed", "missing validator", [])
    return {
        **run,
        "validation": validation,
    }


def _run_serve_case(
    case: CaseDefinition,
    *,
    case_dir: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    workdir = REPO_ROOT
    command = [
        *_launcher_prefix(),
        "--",
        "--serve",
        "--approval-policy",
        str(args.approval_policy),
        "--sandbox-mode",
        str(args.sandbox_mode),
        "--web-search-mode",
        str(args.web_search_mode),
        "--network-access",
        str(args.network_access),
    ]
    requests = [
        {"id": f"turn{index + 1}", "prompt": prompt}
        for index, prompt in enumerate(case.prompts)
    ]
    stdin_text = "\n".join(json.dumps(request, ensure_ascii=False) for request in requests) + "\n"
    started = time.monotonic()
    proc = subprocess.run(
        command,
        cwd=str(workdir),
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=args.timeout_seconds,
        check=False,
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    stdout_path = case_dir / "stdout.jsonl"
    stderr_path = case_dir / "stderr.log"
    stdin_path = case_dir / "stdin.jsonl"
    _write_text(stdin_path, stdin_text)
    _write_text(stdout_path, proc.stdout or "")
    _write_text(stderr_path, proc.stderr or "")
    turns = _parse_serve_jsonl(proc.stdout)
    for turn_id, turn in turns.items():
        _write_json(case_dir / f"{turn_id}.response.json", turn.get("payload") or {})
    run = {
        "case_id": case.case_id,
        "mode": case.mode,
        "cwd": str(workdir),
        "workspace": "",
        "turns": turns,
        "command": command,
        "duration_ms": duration_ms,
        "returncode": proc.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stdin_path": str(stdin_path),
    }
    validation = case.validator(run) if case.validator is not None else _validation_result("failed", "missing validator", [])
    return {
        **run,
        "validation": validation,
    }


def _case_report(case: CaseDefinition, run: dict[str, Any]) -> dict[str, Any]:
    validation = dict(run.get("validation") or {})
    payload = dict(run.get("payload") or {})
    turn_payloads = {
        turn_id: dict(turn.get("payload") or {})
        for turn_id, turn in dict(run.get("turns") or {}).items()
    }
    primary_payload = payload or dict(next(iter(turn_payloads.values()), {}))
    details = dict(validation.get("details") or {})
    if payload:
        details.setdefault("canonical_tools", _canonical_tool_names(payload))
        details.setdefault("projected_tools", _projected_tool_names(payload))
        details.setdefault("response_tools", _response_tool_names(payload))
        details.setdefault("turn_item_types", _turn_item_types(payload))
    if turn_payloads:
        details.setdefault(
            "turn_tools",
            {
                turn_id: {
                    "canonical": _canonical_tool_names(turn_payload),
                    "projected": _projected_tool_names(turn_payload),
                }
                for turn_id, turn_payload in turn_payloads.items()
            },
        )
    return {
        "case_id": case.case_id,
        "title": case.title,
        "mode": case.mode,
        "cwd": str(run.get("cwd") or ""),
        "workspace": str(run.get("workspace") or ""),
        "duration_ms": int(run.get("duration_ms") or 0),
        "returncode": run.get("returncode"),
        "status": str(validation.get("status") or "failed"),
        "summary": str(validation.get("summary") or ""),
        "notes": list(validation.get("notes") or []),
        "assistant_text": _assistant_text(primary_payload),
        "provider_name": str(((primary_payload.get("status") or {}).get("provider_name") or "")),
        "provider_model": str(((primary_payload.get("status") or {}).get("provider_model") or "")),
        "canonical_tools": _canonical_tool_names(primary_payload),
        "projected_tools": _projected_tool_names(primary_payload),
        "response_tools": _response_tool_names(primary_payload),
        "turn_item_types": _turn_item_types(primary_payload),
        "stdout_path": str(run.get("stdout_path") or ""),
        "stderr_path": str(run.get("stderr_path") or ""),
        "stdin_path": str(run.get("stdin_path") or ""),
        "details": details,
    }


def _markdown_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Anthropic Tool Smoke Report\n")
    lines.append(f"- generated_at: `{report.get('generated_at')}`\n")
    lines.append(f"- overall_status: `{report.get('overall_status')}`\n")
    lines.append(f"- passed: `{report.get('passed_count')}`\n")
    lines.append(f"- expected_blocked: `{report.get('expected_blocked_count')}`\n")
    lines.append(f"- failed: `{report.get('failed_count')}`\n")
    lines.append(f"- out_dir: `{report.get('out_dir')}`\n")
    lines.append("\n## Cases\n")
    lines.append("| Case | Status | Summary |\n")
    lines.append("| --- | --- | --- |\n")
    for case in list(report.get("cases") or []):
        lines.append(
            f"| `{case.get('case_id')}` | `{case.get('status')}` | {str(case.get('summary') or '').replace('|', '/')} |\n"
        )
    lines.append("\n## Details\n")
    for case in list(report.get("cases") or []):
        lines.append(f"### `{case.get('case_id')}`\n")
        lines.append(f"- title: {case.get('title')}\n")
        lines.append(f"- status: `{case.get('status')}`\n")
        lines.append(f"- duration_ms: `{case.get('duration_ms')}`\n")
        if case.get("canonical_tools"):
            lines.append(f"- canonical_tools: `{', '.join(case.get('canonical_tools') or [])}`\n")
        if case.get("projected_tools"):
            lines.append(f"- projected_tools: `{', '.join(case.get('projected_tools') or [])}`\n")
        if case.get("notes"):
            for note in list(case.get("notes") or []):
                lines.append(f"- note: {note}\n")
        if case.get("stdout_path"):
            lines.append(f"- stdout_path: `{case.get('stdout_path')}`\n")
        if case.get("stderr_path"):
            lines.append(f"- stderr_path: `{case.get('stderr_path')}`\n")
        lines.append("\n")
    return "".join(lines)
