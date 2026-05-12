from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from cli.agent_cli.runtime_core.event_rendering import activity_events_for_tool_event
from cli.agent_cli.tools import ToolRegistry


DEFAULT_OUT_ROOT_PREFIX = "agenthub_apply_patch_wave01_"


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    family: str
    description: str
    execute: Callable[[Path], dict[str, Any]]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _normalized_file_content(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\n")


def _registry(workspace_root: Path) -> ToolRegistry:
    registry = ToolRegistry()
    registry.set_workspace_root(workspace_root)
    return registry


def _compact_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    source = dict(payload or {})
    keys = (
        "ok",
        "request_kind",
        "structured_request_kind",
        "function_call_name",
        "function_call_arguments",
        "source_tool_name",
        "guard_profile",
        "guard_failure",
        "file_count",
        "added_count",
        "updated_count",
        "deleted_count",
        "moved_count",
        "error",
    )
    compact: dict[str, Any] = {}
    for key in keys:
        value = source.get(key)
        if value in (None, "", {}, []):
            continue
        compact[key] = value
    return compact


def _completed_item_rows(item_events: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in list(item_events or []):
        if not isinstance(event, dict) or str(event.get("type") or "") != "item.completed":
            continue
        item = dict(event.get("item") or {})
        item_type = str(item.get("type") or "").strip()
        name = ""
        if item_type == "mcp_tool_call":
            name = str(item.get("tool") or "").strip()
        else:
            name = str(item.get("name") or item.get("call_id") or "").strip()
        rows.append(
            {
                "type": item_type,
                "name": name,
                "status": str(item.get("status") or "").strip(),
            }
        )
    return rows


def _step_report(step_name: str, result: Any) -> dict[str, Any]:
    tool_events = list(getattr(result, "tool_events", []) or [])
    activity_titles = [
        activity.title
        for event in tool_events
        for activity in activity_events_for_tool_event(event)
        if str(activity.title or "").strip()
    ]
    return {
        "step": step_name,
        "assistant_text": str(getattr(result, "assistant_text", "") or ""),
        "tool_event_names": [str(event.name or "") for event in tool_events],
        "completed_items": _completed_item_rows(list(getattr(result, "item_events", []) or [])),
        "activity_titles": activity_titles,
        "event_payloads": [_compact_payload(dict(event.payload or {})) for event in tool_events],
        "ok": bool(tool_events[-1].ok) if tool_events else False,
    }


def _file_expectation_rows(
    workspace_root: Path,
    *,
    expected_files: dict[str, str] | None = None,
    absent_files: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rel_path, expected in dict(expected_files or {}).items():
        path = workspace_root / rel_path
        exists = path.exists()
        actual = _normalized_file_content(path) if exists else ""
        rows.append(
            {
                "path": rel_path,
                "exists": exists,
                "expected": expected,
                "actual": actual,
                "ok": exists and actual == expected,
            }
        )
    for rel_path in absent_files:
        path = workspace_root / rel_path
        rows.append(
            {
                "path": rel_path,
                "exists": path.exists(),
                "expected": "<absent>",
                "actual": "<present>" if path.exists() else "<absent>",
                "ok": not path.exists(),
            }
        )
    return rows


def _case_report(
    *,
    case: CaseSpec,
    workspace_root: Path,
    steps: list[dict[str, Any]],
    expected_ok: bool,
    expected_error_substring: str = "",
    expected_files: dict[str, str] | None = None,
    absent_files: tuple[str, ...] = (),
) -> dict[str, Any]:
    last_step = steps[-1]
    actual_ok = bool(last_step.get("ok"))
    last_payload = dict((last_step.get("event_payloads") or [{}])[-1] or {})
    error_text = str(last_payload.get("error") or "")
    file_results = _file_expectation_rows(
        workspace_root,
        expected_files=expected_files,
        absent_files=absent_files,
    )
    passed = actual_ok == expected_ok and all(bool(item.get("ok")) for item in file_results)
    if expected_error_substring:
        passed = passed and expected_error_substring in error_text
    return {
        "case_id": case.case_id,
        "family": case.family,
        "description": case.description,
        "expected_ok": expected_ok,
        "actual_ok": actual_ok,
        "expected_error_substring": expected_error_substring,
        "error": error_text,
        "steps": steps,
        "file_results": file_results,
        "passed": passed,
    }
