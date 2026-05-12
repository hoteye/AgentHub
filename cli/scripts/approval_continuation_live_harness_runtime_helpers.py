from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from cli.scripts.approval_continuation_live_harness_analysis_helpers import (
        _case_verdict,
        _extract_approval_id,
        _extract_continuation,
        _request_log_summary,
        _response_payload,
        _summarize_continuation,
        _tool_events,
    )
    from cli.scripts.approval_continuation_live_harness_model_helpers import (
        DEFAULT_TIMEOUT_SECONDS,
        LiveCase,
        _default_out_root,
        _now_iso,
        _selected_cases,
        _write_json,
    )
    from cli.scripts.approval_continuation_live_harness_prompt_helpers import (
        _prompt_for_case_provider,
    )
    from cli.scripts.approval_continuation_live_harness_stream_helpers import _wait_for_json_line
    from cli.scripts.script_runtime_helpers import (
        ScriptProviderSelectionOverride,
        apply_script_provider_materialization_env,
        ensure_script_import_paths,
        materialize_script_provider_fixture,
    )
except ModuleNotFoundError:  # pragma: no cover - direct helper import
    from approval_continuation_live_harness_analysis_helpers import (  # type: ignore[no-redef]
        _case_verdict,
        _extract_approval_id,
        _extract_continuation,
        _request_log_summary,
        _response_payload,
        _summarize_continuation,
        _tool_events,
    )
    from approval_continuation_live_harness_model_helpers import (  # type: ignore[no-redef]
        DEFAULT_TIMEOUT_SECONDS,
        LiveCase,
        _default_out_root,
        _now_iso,
        _selected_cases,
        _write_json,
    )
    from approval_continuation_live_harness_prompt_helpers import (
        _prompt_for_case_provider,  # type: ignore[no-redef]
    )
    from approval_continuation_live_harness_stream_helpers import (
        _wait_for_json_line,  # type: ignore[no-redef]
    )
    from script_runtime_helpers import (  # type: ignore[no-redef]
        ScriptProviderSelectionOverride,
        apply_script_provider_materialization_env,
        ensure_script_import_paths,
        materialize_script_provider_fixture,
    )


_SCRIPT_PATHS = ensure_script_import_paths(__file__)
CLI_ROOT = _SCRIPT_PATHS.cli_root
AGENTHUB_MAIN = CLI_ROOT / "agent_cli" / "__main__.py"


def _prepare_case_workspace(workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    git_dir = workspace / ".git"
    if git_dir.exists():
        return
    git_dir.mkdir(parents=True, exist_ok=True)
    (git_dir / "refs" / "heads").mkdir(parents=True, exist_ok=True)
    (git_dir / "refs" / "tags").mkdir(parents=True, exist_ok=True)
    (git_dir / "objects").mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git_dir / "config").write_text(
        "[core]\n"
        "\trepositoryformatversion = 0\n"
        "\tfilemode = true\n"
        "\tbare = false\n"
        "\tlogallrefupdates = true\n",
        encoding="utf-8",
    )


def _wait_for_serve_response(
    stream: Any,
    *,
    timeout_seconds: int,
    tee_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    lines: list[dict[str, Any]] = []
    for _ in range(100):
        line = _wait_for_json_line(
            stream,
            timeout_seconds=timeout_seconds,
            tee_path=tee_path,
        )
        lines.append(line)
        line_type = str(line.get("type") or "").strip()
        if line_type in {"response", "error"}:
            return line, lines
    raise RuntimeError("serve emitted too many non-response lines")


def _control_request_tool_use_id(lines: list[dict[str, Any]], approval_id: str) -> str:
    normalized_id = str(approval_id or "").strip()
    for line in lines:
        if str(line.get("type") or "").strip() != "control_request":
            continue
        if str(line.get("request_id") or "").strip() != normalized_id:
            continue
        request = dict(line.get("request") or {})
        tool_use_id = str(request.get("tool_use_id") or "").strip()
        if tool_use_id:
            return tool_use_id
    return ""


def _control_response_request_for_case(
    *,
    case: LiveCase,
    approval_id: str,
    first_lines: list[dict[str, Any]],
) -> dict[str, Any]:
    tool_use_id = _control_request_tool_use_id(first_lines, approval_id)
    if case.decision == "approve":
        response: dict[str, Any] = {
            "behavior": "allow",
            "updatedInput": {},
            "decisionClassification": "user_temporary",
        }
    else:
        response = {
            "behavior": "deny",
            "message": "Rejected by approval continuation harness.",
            "decisionClassification": "user_reject",
        }
    if tool_use_id:
        response["toolUseID"] = tool_use_id
    return {
        "type": "control_response",
        "response": {
            "subtype": "success",
            "request_id": approval_id,
            "response": response,
        },
    }


def _decision_request_for_case(
    *,
    case: LiveCase,
    approval_id: str,
    first_lines: list[dict[str, Any]],
    approval_transport: str,
) -> dict[str, Any]:
    normalized_id = str(approval_id or "").strip() or "missing_approval_id"
    if str(approval_transport or "").strip() == "control":
        return _control_response_request_for_case(
            case=case,
            approval_id=normalized_id,
            first_lines=first_lines,
        )
    decision_prompt = f"/{case.decision} {normalized_id}"
    return {"id": f"{case.name}:decision", "prompt": decision_prompt}


def _run_case(
    *,
    case: LiveCase,
    root: Path,
    provider: str,
    model: str,
    reasoning_effort: str,
    timeout_seconds: int,
    approval_transport: str,
) -> dict[str, Any]:
    case_model = ""
    workspace = root / "workspace"
    log_dir = root / "logs"
    home = root / "provider_fixture"
    stdout_path = log_dir / "serve.stdout.jsonl"
    stderr_path = log_dir / "serve.stderr.txt"
    _prepare_case_workspace(workspace)
    log_dir.mkdir(parents=True, exist_ok=True)
    provider_fixture = materialize_script_provider_fixture(
        cwd=CLI_ROOT,
        target_root=home,
        selection_override=ScriptProviderSelectionOverride(
            provider_name=provider,
            model=case_model or model,
            reasoning_effort=reasoning_effort,
        ),
    )
    env = os.environ.copy()
    apply_script_provider_materialization_env(env, fixture=provider_fixture)
    if provider:
        env["AGENT_CLI_PROVIDER"] = provider
    if model:
        env["AGENT_CLI_MODEL"] = case_model or model
    if reasoning_effort:
        env["AGENT_CLI_REASONING_EFFORT"] = reasoning_effort
    env["AGENTHUB_DEBUG_LOG_DIR"] = str(log_dir)
    env["AGENTHUB_DEBUG_RESPONSES_TIMELINE"] = str(log_dir / "serve.timeline.jsonl")

    command = [
        sys.executable,
        str(AGENTHUB_MAIN),
        "--headless",
        "--serve",
        "--approval-policy",
        "on-request",
        "--sandbox-mode",
        "workspace-write",
        "--network-access",
        "enabled",
    ]
    stderr_file = stderr_path.open("w", encoding="utf-8")
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
    returncode: int | None = None
    try:
        if proc.stdin is None:
            raise RuntimeError("serve stdin pipe is unavailable")
        first_request = {
            "id": f"{case.name}:request",
            "prompt": _prompt_for_case_provider(case, provider=provider),
        }
        proc.stdin.write(json.dumps(first_request, ensure_ascii=False) + "\n")
        proc.stdin.flush()
        first_line, first_lines = _wait_for_serve_response(
            proc.stdout, timeout_seconds=timeout_seconds, tee_path=stdout_path
        )
        first_response = _response_payload(first_line)
        approval_id = _extract_approval_id(first_response)
        turns.append({"request": first_request, "line": first_line, "lines": first_lines})

        decision_request = _decision_request_for_case(
            case=case,
            approval_id=approval_id,
            first_lines=first_lines,
            approval_transport=approval_transport,
        )
        proc.stdin.write(json.dumps(decision_request, ensure_ascii=False) + "\n")
        proc.stdin.flush()
        decision_line, decision_lines = _wait_for_serve_response(
            proc.stdout, timeout_seconds=timeout_seconds, tee_path=stdout_path
        )
        decision_response = _response_payload(decision_line)
        turns.append({"request": decision_request, "line": decision_line, "lines": decision_lines})
    finally:
        if proc.stdin is not None and not proc.stdin.closed:
            proc.stdin.close()
        try:
            returncode = proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            returncode = proc.wait(timeout=10)
        stderr_file.close()

    first_response = _response_payload(turns[0]["line"]) if turns else {}
    decision_response = _response_payload(turns[1]["line"]) if len(turns) > 1 else {}
    continuation = _extract_continuation(decision_response)
    continuation_summary = _summarize_continuation(continuation)
    verdict, reasons = _case_verdict(
        case=case,
        first_response=first_response,
        decision_response=decision_response,
        continuation=continuation,
        workspace=workspace,
    )
    return {
        "case": case.name,
        "tool_name": case.tool_name,
        "decision": case.decision,
        "verdict": verdict,
        "reasons": reasons,
        "workspace": str(workspace),
        "target_file": str(workspace / case.target_file),
        "provider_fixture": {
            "config_path": str(provider_fixture.config_path),
            "auth_path": str(provider_fixture.auth_path),
            "agent_cli_home": str(provider_fixture.agent_cli_home),
            "provider_home": (
                str(provider_fixture.provider_home)
                if provider_fixture.provider_home is not None
                else ""
            ),
            "source_scope": str(provider_fixture.source_scope),
            "case_model_override": case_model,
        },
        "serve_command": command,
        "returncode": returncode,
        "approval_transport": approval_transport,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "log_dir": str(log_dir),
        "approval_id": _extract_approval_id(first_response),
        "control_requests": (
            [
                dict(line)
                for line in list(turns[0].get("lines") or [])
                if isinstance(line, dict) and str(line.get("type") or "") == "control_request"
            ]
            if turns
            else []
        ),
        "first_turn": {
            "assistant_text": str(first_response.get("assistant_text") or ""),
            "tool_event_names": [
                str(event.get("name") or "") for event in _tool_events(first_response)
            ],
            "exit_code": turns[0]["line"].get("exit_code") if turns else None,
        },
        "decision_turn": {
            "assistant_text": str(decision_response.get("assistant_text") or ""),
            "tool_event_names": [
                str(event.get("name") or "") for event in _tool_events(decision_response)
            ],
            "exit_code": turns[1]["line"].get("exit_code") if len(turns) > 1 else None,
            "continuation": continuation_summary,
        },
        "request_log": _request_log_summary(log_dir),
    }


def run_approval_continuation_harness(args: argparse.Namespace) -> dict[str, Any]:
    out_root = (
        Path(str(args.out_root or "")).expanduser().resolve()
        if str(args.out_root or "").strip()
        else _default_out_root()
    )
    out_root.mkdir(parents=True, exist_ok=True)
    cases = _selected_cases([str(item) for item in list(args.case or [])])
    results = [
        _run_case(
            case=case,
            root=out_root / case.name,
            provider=str(args.provider or "").strip(),
            model=str(args.model or "").strip(),
            reasoning_effort=str(args.reasoning_effort or "").strip(),
            timeout_seconds=int(args.timeout_seconds or DEFAULT_TIMEOUT_SECONDS),
            approval_transport=str(getattr(args, "approval_transport", "slash") or "slash"),
        )
        for case in cases
    ]
    summary = {
        "created_at": _now_iso(),
        "out_root": str(out_root),
        "provider": str(args.provider or "").strip(),
        "model": str(args.model or "").strip(),
        "reasoning_effort": str(args.reasoning_effort or "").strip(),
        "approval_transport": str(getattr(args, "approval_transport", "slash") or "slash"),
        "case_count": len(results),
        "pass_count": sum(1 for item in results if item.get("verdict") == "pass"),
        "fail_count": sum(1 for item in results if item.get("verdict") != "pass"),
        "results": results,
    }
    summary["verdict"] = "pass" if summary["fail_count"] == 0 else "fail"
    _write_json(out_root / "report.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary
