from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from .benchmark_acceptance_case_helpers import get_benchmark_case_spec, _evidence_pass_level


def _coerce_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _tool_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in list(payload.get("response_items") or []):
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip().lower()
        if item_type in {"function_call", "custom_tool_call", "shell_call", "local_shell_call", "command_execution"}:
            items.append(dict(item))
    return items


def _first_tool_event(payload: dict[str, Any]) -> dict[str, Any]:
    for event in list(payload.get("tool_events") or []):
        if isinstance(event, dict):
            return dict(event)
    return {}


def _tool_name_from_item(item: dict[str, Any]) -> str:
    item_type = str(item.get("type") or "").strip().lower()
    if item_type in {"shell_call", "local_shell_call", "command_execution"}:
        return "exec_command"
    return str(item.get("name") or item.get("tool") or "").strip()


def _tool_name_from_payload(payload: dict[str, Any], *, expected_tool_name: str = "") -> str:
    expected = str(expected_tool_name or "").strip()
    item_names = [_tool_name_from_item(item) for item in _tool_items(payload)]
    if expected and expected in item_names:
        return expected
    for name in item_names:
        if name:
            return name
    event_names = [
        str(event.get("name") or "").strip()
        for event in list(payload.get("tool_events") or [])
        if isinstance(event, dict)
    ]
    if expected and expected in event_names:
        return expected
    for name in event_names:
        if name:
            return name
    return ""


def _normalized_arguments_for_matching(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(arguments or {})
    if str(tool_name or "").strip() == "apply_patch":
        patch_text = str(normalized.get("patch") or normalized.get("input") or "").strip()
        if patch_text:
            normalized["patch"] = patch_text
            normalized["input"] = patch_text
    return normalized


def _arguments_from_tool_item(item: dict[str, Any], *, tool_name: str) -> dict[str, Any]:
    item_type = str(item.get("type") or "").strip().lower()
    if item_type == "custom_tool_call":
        raw_input = str(item.get("input") or "").strip()
        if str(tool_name or "").strip() == "apply_patch":
            if not raw_input:
                return {}
            return _normalized_arguments_for_matching(tool_name, {"patch": raw_input})
        return {"input": raw_input} if raw_input else {}
    if item_type == "function_call":
        return _normalized_arguments_for_matching(tool_name, _coerce_dict(item.get("arguments")))
    if item_type in {"shell_call", "local_shell_call", "command_execution"}:
        action = item.get("action")
        action_payload = dict(action) if isinstance(action, dict) else {}
        command = str(item.get("command") or action_payload.get("command") or action_payload.get("cmd") or "").strip()
        return {"cmd": command} if command else {}
    return {}


def _arguments_from_first_tool_event(payload: dict[str, Any], *, tool_name: str) -> dict[str, Any]:
    event = _first_tool_event(payload)
    return _arguments_from_tool_event(event, tool_name=tool_name)


def _arguments_from_tool_event(event: dict[str, Any], *, tool_name: str) -> dict[str, Any]:
    event_payload = event.get("payload")
    payload_map = dict(event_payload) if isinstance(event_payload, dict) else {}
    for key in ("function_call_arguments", "arguments"):
        arguments = _coerce_dict(payload_map.get(key))
        if arguments:
            return _normalized_arguments_for_matching(tool_name, arguments)
    if tool_name == "exec_command":
        command = str(payload_map.get("command") or payload_map.get("cmd") or "").strip()
        return {"cmd": command} if command else {}
    if tool_name == "apply_patch":
        patch_text = str(payload_map.get("patch") or payload_map.get("input") or payload_map.get("command") or "").strip()
        return _normalized_arguments_for_matching(tool_name, {"patch": patch_text}) if patch_text else {}
    if tool_name == "web_search":
        query = str(payload_map.get("query") or payload_map.get("search_query") or "").strip()
        return {"query": query} if query else {}
    return {}


def _arguments_from_function_call_outputs(
    payload: dict[str, Any],
    *,
    call_ids: set[str],
    tool_name: str,
) -> dict[str, Any]:
    if not call_ids:
        return {}
    for item in list(payload.get("response_items") or []):
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip().lower() != "function_call_output":
            continue
        call_id = str(item.get("call_id") or "").strip()
        if call_id not in call_ids:
            continue
        output_payload = _coerce_dict(item.get("output"))
        arguments = _coerce_dict(output_payload.get("function_call_arguments"))
        if arguments:
            return _normalized_arguments_for_matching(tool_name, arguments)
    return {}


def _tool_arguments_from_payload(payload: dict[str, Any], *, tool_name: str) -> dict[str, Any]:
    matching_call_ids: set[str] = set()
    for item in _tool_items(payload):
        item_name = _tool_name_from_item(item)
        if item_name != str(tool_name or "").strip():
            continue
        call_id = str(item.get("call_id") or "").strip()
        if call_id:
            matching_call_ids.add(call_id)
        arguments = _arguments_from_tool_item(item, tool_name=tool_name)
        if arguments:
            return arguments
    output_arguments = _arguments_from_function_call_outputs(
        payload,
        call_ids=matching_call_ids,
        tool_name=tool_name,
    )
    if output_arguments:
        return output_arguments
    for event in list(payload.get("tool_events") or []):
        if not isinstance(event, dict):
            continue
        if str(event.get("name") or "").strip() != str(tool_name or "").strip():
            continue
        arguments = _arguments_from_tool_event(event, tool_name=tool_name)
        if arguments:
            return arguments
    return _arguments_from_first_tool_event(payload, tool_name=tool_name)


def _value_matches(actual: Any, expected: Any) -> bool:
    if isinstance(expected, str):
        expected_text = expected.strip()
        actual_text = str(actual or "").strip()
        if not expected_text:
            return actual_text == ""
        return expected_text in actual_text
    return actual == expected


def _metric(payload: dict[str, Any], key: str) -> int | None:
    status = payload.get("status")
    if isinstance(status, dict) and isinstance(status.get(key), int):
        return int(status[key])
    for event in list(payload.get("tool_events") or []):
        if not isinstance(event, dict):
            continue
        event_payload = event.get("payload")
        if isinstance(event_payload, dict) and isinstance(event_payload.get(key), int):
            return int(event_payload[key])
    return None


def _result_text_candidates(payload: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    assistant_text = str(payload.get("assistant_text") or "").strip()
    if assistant_text:
        texts.append(assistant_text)
    for item in list(payload.get("response_items") or []):
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip().lower() != "function_call_output":
            continue
        output_text = str(item.get("output") or "").strip()
        if output_text:
            texts.append(output_text)
    for event in list(payload.get("tool_events") or []):
        if not isinstance(event, dict):
            continue
        summary = str(event.get("summary") or "").strip()
        if summary:
            texts.append(summary)
        event_payload = event.get("payload")
        if not isinstance(event_payload, dict):
            continue
        for key in ("function_call_output", "stdout", "aggregated_output", "output"):
            text = str(event_payload.get(key) or "").strip()
            if text:
                texts.append(text)
    return texts


def build_acceptance_row(case_id: str, payload: dict[str, Any], *, evidence_level: str = "synthetic") -> dict[str, Any]:
    case = get_benchmark_case_spec(case_id)
    tool_name_actual = _tool_name_from_payload(payload, expected_tool_name=case.expected_tool_name)
    actual_arguments = _tool_arguments_from_payload(payload, tool_name=tool_name_actual)
    arguments_correct = any(
        all(_value_matches(actual_arguments.get(key), value) for key, value in option.items())
        for option in case.expected_argument_options
    )
    result_usable = any(
        _value_matches(text, case.expected_result_fragment)
        for text in _result_text_candidates(payload)
    )
    time_to_first_event_ms = _metric(payload, "time_to_first_event_ms")
    time_to_first_tool_ms = _metric(payload, "time_to_first_tool_ms")
    return {
        "case_id": case.case_id,
        "surface": case.surface,
        "tool_name_expected": case.expected_tool_name,
        "tool_name_actual": tool_name_actual,
        "tool_name_correct": tool_name_actual == case.expected_tool_name,
        "arguments_correct": arguments_correct,
        "result_usable": result_usable,
        "time_to_first_event_ms": time_to_first_event_ms,
        "time_to_first_tool_ms": time_to_first_tool_ms,
        "evidence_level": evidence_level,
        "evidence_pass_level": _evidence_pass_level(evidence_level),
        "acceptance_passed": bool(
            tool_name_actual == case.expected_tool_name
            and arguments_correct
            and result_usable
            and isinstance(time_to_first_event_ms, int)
            and isinstance(time_to_first_tool_ms, int)
        ),
    }


def _coerce_live_results_items(live_results: Sequence[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [dict(item) for item in list(live_results or []) if isinstance(item, dict)]


def _load_live_results(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [dict(item) for item in list(data or []) if isinstance(item, dict)]


def _evidence_level_for_case_source_kind(case_source_kind: str) -> str:
    normalized = str(case_source_kind or "").strip().lower()
    if normalized == "fixture_live":
        return "fixture_live"
    if normalized in {"recorded", "operator_live"}:
        return "operator_live"
    return "synthetic"


def project_live_headless_ab_report_to_row(
    report: Any,
    *,
    live_results: Sequence[dict[str, Any]] | None = None,
    evidence_level: str | None = None,
) -> dict[str, Any]:
    report_payload = report.to_dict() if hasattr(report, "to_dict") else dict(report or {})
    case_id = str(report_payload.get("case_id") or "").strip()
    if not case_id:
        raise ValueError("live headless ab report is missing case_id")
    case_source_kind = str(report_payload.get("case_source_kind") or "").strip()
    live_items = _coerce_live_results_items(live_results)
    if not live_items:
        live_results_path = str(report_payload.get("live_results_path") or "").strip()
        if not live_results_path:
            raise ValueError("live headless ab report is missing live_results_path")
        live_items = _load_live_results(live_results_path)
    if not live_items:
        raise ValueError(f"live headless ab report has no live turn payloads for case {case_id!r}")
    row = build_acceptance_row(
        case_id,
        live_items[-1],
        evidence_level=evidence_level or _evidence_level_for_case_source_kind(case_source_kind),
    )
    row["case_source_kind"] = case_source_kind
    row["surface_family"] = str(report_payload.get("surface_family") or "").strip()
    row["case_pack"] = str(report_payload.get("case_pack") or "").strip()
    row["recording_variant_source"] = str(report_payload.get("recording_variant_source") or "").strip()
    row["behavioral_passed"] = bool(report_payload.get("behavioral_passed"))
    row["protocol_path_passed"] = bool(report_payload.get("protocol_path_passed"))
    row["mismatch_count"] = int(report_payload.get("mismatch_count") or 0)
    row["live_results_path"] = str(report_payload.get("live_results_path") or "").strip()
    row["diff_report_path"] = str(report_payload.get("diff_report_path") or "").strip()
    row["summary_path"] = str(report_payload.get("summary_path") or "").strip()
    return row
