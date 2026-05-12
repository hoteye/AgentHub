from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from .fingerprint import request_fingerprint
from .schema import (
    ReplayCassette,
    ReplayManifest,
    ReplayRound,
    ReplaySessionMetadata,
    ReplayToolCall,
)


_XML_TAG_PATTERN = re.compile(r"<(?P<name>[a-z_]+)>(?P<value>.*?)</(?P=name)>", re.DOTALL)
_ENVIRONMENT_CONTEXT_PATTERN = re.compile(
    r"<environment_context>(?P<body>.*?)</environment_context>",
    re.DOTALL,
)
_WORKSPACE_HEADER_PATTERN = re.compile(r"^# (?:AENGTHUB|AGENTS)\.md instructions for (?P<path>.+)$", re.MULTILINE)
_SKILL_PATTERN = re.compile(r"^- (?P<name>[a-zA-Z0-9_-]+):", re.MULTILINE)


@dataclass(frozen=True)
class ReferenceBaselineTurnLog:
    stdout_path: Path
    stderr_path: Path


def _read_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _find_stage(records: Sequence[Dict[str, Any]], stage: str) -> Dict[str, Any]:
    for record in list(records or []):
        if str(record.get("stage") or "").strip() == stage:
            payload = record.get("payload")
            if isinstance(payload, dict):
                return payload
    raise ValueError(f"missing stage {stage}")


def _message_text(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    parts: List[str] = []
    for entry in content:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _item_inventory(items: Any) -> List[str]:
    return [
        str(item.get("type") or "").strip()
        for item in list(items or [])
        if isinstance(item, dict) and str(item.get("type") or "").strip()
    ]


def _parse_environment_context(request: Dict[str, Any]) -> Dict[str, Any]:
    for item in list(request.get("input") or []):
        if not isinstance(item, dict):
            continue
        content_text = _message_text(item.get("content"))
        block_match = _ENVIRONMENT_CONTEXT_PATTERN.search(content_text)
        if block_match is None:
            continue
        block_text = str(block_match.group("body") or "")
        values: Dict[str, Any] = {}
        for match in _XML_TAG_PATTERN.finditer(block_text):
            name = str(match.group("name") or "").strip()
            value = str(match.group("value") or "").strip()
            if name in {"cwd", "shell", "current_date", "timezone"} and value:
                values[name] = value
        if values:
            return values
    return {}


def _workspace_prompt_text(request: Dict[str, Any]) -> str:
    for item in list(request.get("input") or []):
        if not isinstance(item, dict):
            continue
        for entry in list(item.get("content") or []):
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("text") or "")
            if (
                "# AENGTHUB.md instructions for " in text
                or "# AGENTS.md instructions for " in text
                or "REFERENCE_CONTEXT_BASELINE:" in text
            ):
                return text.strip()
    return ""


def _derive_workspace_snapshot(request: Dict[str, Any], environment: Dict[str, Any]) -> Dict[str, Any]:
    workspace_text = _workspace_prompt_text(request)
    doc_paths: List[str] = []
    skill_names: List[str] = []
    for item in list(request.get("input") or []):
        if not isinstance(item, dict):
            continue
        text = _message_text(item.get("content"))
        if not text:
            continue
        doc_paths.extend(match.group("path").strip() for match in _WORKSPACE_HEADER_PATTERN.finditer(text))
        skill_names.extend(match.group("name").strip() for match in _SKILL_PATTERN.finditer(text))
    digest = hashlib.sha1(workspace_text.encode("utf-8")).hexdigest() if workspace_text else ""
    return {
        "cwd": str(environment.get("cwd") or "").strip(),
        "trust_level": "unknown",
        "instructions_text": workspace_text,
        "instructions_digest": digest,
        "docs": sorted({item for item in doc_paths if item}),
        "skills": sorted({item for item in skill_names if item}),
    }


def _response_from_completed_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    items = [
        dict(item)
        for item in list(payload.get("items_added") or [])
        if isinstance(item, dict)
    ]
    output_text = ""
    for item in items:
        if str(item.get("type") or "").strip() != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        parts = [
            str(entry.get("text") or "").strip()
            for entry in content
            if isinstance(entry, dict) and str(entry.get("text") or "").strip()
        ]
        if parts:
            output_text = "\n\n".join(parts).strip()
    return {
        "id": str(payload.get("response_id") or "").strip(),
        "output": items,
        "output_text": output_text,
        "usage": dict(payload.get("token_usage") or {}),
    }


def _final_agent_message_text(stdout_records: Sequence[Dict[str, Any]]) -> str:
    final_text = ""
    for record in list(stdout_records or []):
        item = record.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "agent_message":
            continue
        text = str(item.get("text") or "").strip()
        if text:
            final_text = text
    return final_text


def _response_from_turn_logs(
    stdout_records: Sequence[Dict[str, Any]],
    response_completed_payload: Dict[str, Any],
) -> Dict[str, Any]:
    response = _response_from_completed_payload(response_completed_payload)
    final_text = _final_agent_message_text(stdout_records)
    if final_text:
        output_items = [
            dict(item)
            for item in list(response.get("output") or [])
            if isinstance(item, dict)
        ]
        has_matching_final_message = False
        for item in output_items:
            if str(item.get("type") or "").strip() != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            parts = [
                str(entry.get("text") or "").strip()
                for entry in content
                if isinstance(entry, dict) and str(entry.get("text") or "").strip()
            ]
            if "\n\n".join(parts).strip() == final_text:
                has_matching_final_message = True
                break
        if not has_matching_final_message:
            output_items.append(
                {
                    "type": "message",
                    "role": "assistant",
                    "phase": "final_answer",
                    "content": [{"type": "output_text", "text": final_text}],
                }
            )
            response["output"] = output_items
        response["output_text"] = final_text
    return response


def _thread_id(stdout_records: Sequence[Dict[str, Any]]) -> str:
    for record in list(stdout_records or []):
        if str(record.get("type") or "").strip() != "thread.started":
            continue
        return str(record.get("thread_id") or "").strip()
    return ""


def _stdout_command_events(stdout_records: Sequence[Dict[str, Any]]) -> List[ReplayToolCall]:
    started_by_id: Dict[str, Dict[str, Any]] = {}
    completed_items: List[Dict[str, Any]] = []
    for record in list(stdout_records or []):
        item = record.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "command_execution":
            continue
        item_id = str(item.get("id") or "").strip()
        event_type = str(record.get("type") or "").strip()
        if event_type == "item.started" and item_id:
            started_by_id[item_id] = dict(record)
        if event_type == "item.completed":
            completed_items.append(dict(record))

    tool_calls: List[ReplayToolCall] = []
    for index, completed in enumerate(completed_items, start=1):
        item = dict(completed.get("item") or {})
        item_id = str(item.get("id") or "").strip()
        events: List[Dict[str, Any]] = []
        if item_id and item_id in started_by_id:
            events.append(dict(started_by_id[item_id]))
        events.append(dict(completed))
        output = str(item.get("aggregated_output") or "")
        tool_calls.append(
            ReplayToolCall(
                index=index,
                tool_name="exec_command",
                call_id=item_id or f"stdout_tool_{index}",
                command_text=str(item.get("command") or "").strip(),
                arguments={"command": str(item.get("command") or "").strip()},
                output_items=[
                    {
                        "type": "function_call_output",
                        "call_id": item_id or f"stdout_tool_{index}",
                        "output": output,
                        "success": int(item.get("exit_code") or 0) == 0,
                    }
                ],
                tool_events=events,
            )
        )
    return tool_calls


def build_cassette_from_reference_baseline_turn_logs(
    turn_logs: Sequence[ReferenceBaselineTurnLog],
    *,
    name: str,
    case_id: str = "",
    drift_policy: str = "warn",
    parity_targets: Sequence[str] | None = None,
    coverage_tags: Sequence[str] | None = None,
) -> ReplayCassette:
    if not turn_logs:
        raise ValueError("turn_logs must not be empty")

    rounds: List[ReplayRound] = []
    all_tool_calls: List[ReplayToolCall] = []
    first_request: Dict[str, Any] | None = None
    first_environment: Dict[str, Any] = {}
    thread_id = ""
    recorded_at = ""
    provider = ""
    model = ""
    prompt_cache_key = ""

    for index, turn_log in enumerate(list(turn_logs or []), start=1):
        stdout_records = _read_jsonl(turn_log.stdout_path)
        stderr_records = _read_jsonl(turn_log.stderr_path)
        request = _find_stage(stderr_records, "stream_responses_api.request.raw")
        response_completed = _find_stage(stderr_records, "stream_responses_api.response.completed.raw")
        request_body = dict(request)
        response = _response_from_turn_logs(stdout_records, response_completed)
        environment = _parse_environment_context(request_body)
        if first_request is None:
            first_request = request_body
            first_environment = environment
            thread_id = _thread_id(stdout_records)
            provider = str(_find_stage(stderr_records, "stream_responses_api.request").get("provider") or "").strip()
            model = str(request_body.get("model") or "").strip()
            prompt_cache_key = str(request_body.get("prompt_cache_key") or "").strip()
            ts_ms = _find_stage(stderr_records, "stream_responses_api.request").get("ts_ms")
            recorded_at = str(ts_ms or "").strip()

        request_headers: Dict[str, Any] = {}
        if prompt_cache_key:
            request_headers["session_id"] = prompt_cache_key

        rounds.append(
            ReplayRound(
                index=index,
                request_headers=request_headers,
                request_fingerprint=request_fingerprint(request_body, headers=request_headers),
                request_item_inventory=_item_inventory(request_body.get("input")),
                request=request_body,
                response_item_inventory=_item_inventory(response.get("output")),
                response_events=[dict(item) for item in list(stdout_records or []) if isinstance(item, dict)],
                response=response,
            )
        )

        for tool_index, tool_call in enumerate(_stdout_command_events(stdout_records), start=1):
            all_tool_calls.append(
                ReplayToolCall(
                    index=len(all_tool_calls) + 1,
                    round_index=index,
                    tool_name=tool_call.tool_name,
                    call_id=tool_call.call_id,
                    command_text=tool_call.command_text,
                    arguments=dict(tool_call.arguments or {}),
                    output_items=[dict(item) for item in list(tool_call.output_items or [])],
                    tool_events=[dict(item) for item in list(tool_call.tool_events or [])],
                )
            )

    if first_request is None:
        raise ValueError("failed to find any reference_baseline request records")

    workspace_snapshot = _derive_workspace_snapshot(first_request, first_environment)
    session = ReplaySessionMetadata(
        provider=provider,
        model=model,
        transport_kind="responses_http",
        thread_id=thread_id,
        prompt_cache_key=prompt_cache_key,
        recorded_at=recorded_at,
        cwd=str(first_environment.get("cwd") or "").strip(),
        timezone=str(first_environment.get("timezone") or "").strip(),
        current_date=str(first_environment.get("current_date") or "").strip(),
    )
    manifest = ReplayManifest(
        name=name,
        case_id=str(case_id or "").strip(),
        drift_policy=drift_policy,
        notes="converted from reference_baseline stderr/stdout turn logs",
        parity_targets=[str(item or "").strip() for item in list(parity_targets or []) if str(item or "").strip()],
        coverage_tags=[str(item or "").strip() for item in list(coverage_tags or []) if str(item or "").strip()],
        session=session,
        environment_snapshot=first_environment,
        workspace_snapshot=workspace_snapshot,
    )
    return ReplayCassette(
        manifest=manifest,
        rounds=rounds,
        tool_calls=all_tool_calls,
    )
