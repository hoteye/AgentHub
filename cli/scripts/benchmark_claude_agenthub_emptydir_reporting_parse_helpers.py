from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

try:
    from cli.scripts.benchmark_claude_agenthub_emptydir_config_helpers import (
        BenchmarkTask,
        EXPECTED_AGENTHUB_PROVIDER_NAME,
        EXPECTED_SHORT_REPLY,
        EXPECTED_SONNET_MODEL_KEY,
        ValidationSpec,
    )
    from cli.scripts.benchmark_claude_agenthub_emptydir_reporting_diagnostic_helpers import (
        _agenthub_diagnostics,
        _artifact_quality_notes,
        _diagnostic_defaults,
        _dict_list,
        _flatten_diagnostics,
        _safe_json_loads,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from benchmark_claude_agenthub_emptydir_config_helpers import (  # type: ignore[no-redef]
        BenchmarkTask,
        EXPECTED_AGENTHUB_PROVIDER_NAME,
        EXPECTED_SHORT_REPLY,
        EXPECTED_SONNET_MODEL_KEY,
        ValidationSpec,
    )
    from benchmark_claude_agenthub_emptydir_reporting_diagnostic_helpers import (  # type: ignore[no-redef]
        _agenthub_diagnostics,
        _artifact_quality_notes,
        _diagnostic_defaults,
        _dict_list,
        _flatten_diagnostics,
        _safe_json_loads,
    )


def _payload_thread_id(payload: dict[str, Any] | None) -> str:
    status = (payload or {}).get("status")
    if not isinstance(status, dict):
        return ""
    value = str(status.get("thread_id") or "").strip()
    if value in {"", "-", "None", "null"}:
        return ""
    return value


def _agenthub_output_defaults(*, raw_preview: str = "") -> dict[str, Any]:
    payload = {
        "assistant_text": "",
        "raw_preview": raw_preview,
        "status": {},
        "thread_id": "",
        "tool_events": [],
        "turn_events": [],
        "tool_event_count": 0,
        "turn_event_count": 0,
    }
    _flatten_diagnostics(payload, _diagnostic_defaults())
    return payload


def _claude_output_defaults(*, raw_preview: str = "") -> dict[str, Any]:
    payload = {
        "assistant_text": "",
        "raw_preview": raw_preview,
        "duration_ms": None,
        "duration_api_ms": None,
        "session_id": "",
        "total_cost_usd": None,
        "usage": {},
        "model_usage": {},
        "result_type": "",
        "result_subtype": "",
    }
    _flatten_diagnostics(payload, _diagnostic_defaults())
    return payload


def _parse_agenthub_output(stdout_path: Path) -> dict[str, Any]:
    if not stdout_path.exists():
        return _agenthub_output_defaults()
    text = stdout_path.read_text(encoding="utf-8").strip()
    if not text:
        return _agenthub_output_defaults()
    payload = _safe_json_loads(text)
    if payload is None:
        output = _agenthub_output_defaults(raw_preview=text[:400])
        output["assistant_text"] = text
        return output
    tool_events = _dict_list(payload.get("tool_events"))
    turn_events = _dict_list(payload.get("turn_events"))
    status = payload.get("status") if isinstance(payload.get("status"), dict) else {}
    output = {
        "assistant_text": str(payload.get("assistant_text") or "").strip(),
        "raw_preview": text[:400],
        "status": dict(status),
        "thread_id": _payload_thread_id(payload),
        "tool_events": tool_events,
        "turn_events": turn_events,
        "tool_event_count": len(tool_events),
        "turn_event_count": len(turn_events),
    }
    _flatten_diagnostics(
        output,
        _agenthub_diagnostics(status=dict(status), tool_events=tool_events, turn_events=turn_events),
    )
    return output


def _parse_claude_output(stdout_path: Path) -> dict[str, Any]:
    if not stdout_path.exists():
        return _claude_output_defaults()
    text = stdout_path.read_text(encoding="utf-8").strip()
    if not text:
        return _claude_output_defaults()
    payload = _safe_json_loads(text)
    if payload is None:
        output = _claude_output_defaults(raw_preview=text[:400])
        output["assistant_text"] = text
        return output
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    model_usage = payload.get("modelUsage") if isinstance(payload.get("modelUsage"), dict) else {}
    output = {
        "assistant_text": str(payload.get("result") or "").strip(),
        "raw_preview": text[:400],
        "duration_ms": payload.get("duration_ms"),
        "duration_api_ms": payload.get("duration_api_ms"),
        "session_id": str(payload.get("session_id") or "").strip(),
        "total_cost_usd": payload.get("total_cost_usd"),
        "usage": dict(usage),
        "model_usage": dict(model_usage),
        "result_type": str(payload.get("type") or "").strip(),
        "result_subtype": str(payload.get("subtype") or "").strip(),
    }
    _flatten_diagnostics(output, _diagnostic_defaults())
    return output


def _normalize_short_reply(text: Any) -> str:
    normalized = str(text or "").strip()
    while normalized and normalized[-1] in ".。!！?？":
        normalized = normalized[:-1].rstrip()
    return normalized.upper()


def _short_reply_ok(text: Any, *, expected: str = EXPECTED_SHORT_REPLY) -> bool:
    return _normalize_short_reply(text) == str(expected or "").strip().upper()


def _check_payload(*, name: str, passed: bool, expected: Any, actual: Any) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "expected": expected,
        "actual": actual,
    }


def _claude_preflight_checks(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    model_usage = parsed.get("model_usage") if isinstance(parsed.get("model_usage"), dict) else {}
    model_keys = sorted(str(key) for key in model_usage.keys())
    return [
        _check_payload(
            name="assistant_reply",
            passed=_short_reply_ok(parsed.get("assistant_text")),
            expected=EXPECTED_SHORT_REPLY,
            actual=str(parsed.get("assistant_text") or ""),
        ),
        _check_payload(
            name="result_subtype",
            passed=str(parsed.get("result_subtype") or "").strip() == "success",
            expected="success",
            actual=str(parsed.get("result_subtype") or "").strip(),
        ),
        _check_payload(
            name="resolved_model",
            passed=EXPECTED_SONNET_MODEL_KEY in model_keys,
            expected=EXPECTED_SONNET_MODEL_KEY,
            actual=model_keys,
        ),
    ]


def _agenthub_preflight_checks(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    status = parsed.get("status") if isinstance(parsed.get("status"), dict) else {}
    return [
        _check_payload(
            name="assistant_reply",
            passed=_short_reply_ok(parsed.get("assistant_text")),
            expected=EXPECTED_SHORT_REPLY,
            actual=str(parsed.get("assistant_text") or ""),
        ),
        _check_payload(
            name="provider_name",
            passed=str(status.get("provider_name") or "").strip() == EXPECTED_AGENTHUB_PROVIDER_NAME,
            expected=EXPECTED_AGENTHUB_PROVIDER_NAME,
            actual=str(status.get("provider_name") or "").strip(),
        ),
        _check_payload(
            name="model_key",
            passed=str(status.get("model_key") or "").strip() == EXPECTED_SONNET_MODEL_KEY,
            expected=EXPECTED_SONNET_MODEL_KEY,
            actual=str(status.get("model_key") or "").strip(),
        ),
    ]


def _checks_passed(checks: list[dict[str, Any]]) -> bool:
    return bool(checks) and all(bool(item.get("passed")) for item in checks)


def _dry_run_system_report(
    *,
    system_name: str,
    task: BenchmarkTask,
    workspace: Path,
    run_command: list[str],
    validations: tuple[ValidationSpec, ...],
    env_overrides: dict[str, str],
) -> dict[str, Any]:
    missing_expected_files = list(task.expected_files)
    parsed_output = _agenthub_output_defaults() if system_name == "agenthub" else _claude_output_defaults()
    diagnostics = _diagnostic_defaults(
        created_files=[],
        validation_passed=False,
        artifact_quality_notes=_artifact_quality_notes(
            run_succeeded=False,
            validation_passed=False,
            missing_expected_files=missing_expected_files,
            workspace_files=[],
        )
        + "; dry_run",
    )
    payload = {
        "system": system_name,
        "workspace": str(workspace),
        "planned_run_command": list(run_command),
        "planned_run_command_shell": shlex.join(run_command),
        "planned_validations": [
            {"name": item.name, "command": item.command}
            for item in validations
        ],
        "env_overrides": dict(env_overrides),
        "assistant_text": "",
        "assistant_preview": "",
        "parsed_output": parsed_output,
        "run": {
            "name": system_name,
            "command": list(run_command),
            "cwd": str(workspace),
            "exit_code": None,
            "elapsed_seconds": None,
            "timed_out": False,
            "stdout_path": "",
            "stderr_path": "",
        },
        "validation": [],
        "workspace_files": [],
        "workspace_file_count": 0,
        "missing_expected_files": missing_expected_files,
        "validation_passed": False,
        "run_succeeded": False,
        "workspace_tree_path": "",
    }
    _flatten_diagnostics(parsed_output, diagnostics)
    _flatten_diagnostics(payload, diagnostics)
    return payload
