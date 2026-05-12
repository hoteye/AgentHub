from __future__ import annotations

from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from cli.scripts.benchmark_emptydir_ab_model_io_helpers import (
        CommandResult,
        _id_shape,
        _payload_sha256,
        _preview_text,
        _read_json,
        _read_jsonl,
        _workspace_file_inventory,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from benchmark_emptydir_ab_model_io_helpers import (  # type: ignore[no-redef]
        CommandResult,
        _id_shape,
        _payload_sha256,
        _preview_text,
        _read_json,
        _read_jsonl,
        _workspace_file_inventory,
    )

def _request_raw_candidates(log_path: Path, *, stage: str, request_field: str | None) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, row in enumerate(_read_jsonl(log_path), start=1):
        if str(row.get("stage") or "").strip() != stage:
            continue
        payload = row.get("payload") or {}
        if request_field:
            request = dict(payload.get(request_field) or {})
        else:
            request = dict(payload or {})
        if request:
            candidates.append(
                {
                    "candidate_index": index,
                    "request": request,
                }
            )
    return candidates


def _select_request_raw_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not candidates:
        return {}
    for candidate in candidates:
        request = dict(candidate.get("request") or {})
        if list(request.get("tools") or []):
            return candidate
    return candidates[0]


def _build_request_raw_layer(*, agenthub_llm_io_path: Path, codex_llm_io_path: Path) -> dict[str, Any]:
    agenthub_candidates = _request_raw_candidates(
        agenthub_llm_io_path,
        stage="responses.send.request_raw",
        request_field="request",
    )
    codex_candidates = _request_raw_candidates(
        codex_llm_io_path,
        stage="stream_responses_api.request.raw",
        request_field=None,
    )
    agenthub_selected = _select_request_raw_candidate(agenthub_candidates)
    codex_selected = _select_request_raw_candidate(codex_candidates)
    agenthub_request = dict(agenthub_selected.get("request") or {})
    codex_request = dict(codex_selected.get("request") or {})
    comparison = {
        "agenthub_present": bool(agenthub_request),
        "codex_present": bool(codex_request),
        "instructions_equal": agenthub_request.get("instructions") == codex_request.get("instructions"),
        "input_equal": agenthub_request.get("input") == codex_request.get("input"),
        "tools_equal": agenthub_request.get("tools") == codex_request.get("tools"),
        "model_equal": agenthub_request.get("model") == codex_request.get("model"),
        "reasoning_equal": agenthub_request.get("reasoning") == codex_request.get("reasoning"),
        "include_equal": agenthub_request.get("include") == codex_request.get("include"),
        "prompt_cache_key_present_equal": bool(str(agenthub_request.get("prompt_cache_key") or "").strip())
        == bool(str(codex_request.get("prompt_cache_key") or "").strip()),
        "prompt_cache_key_shape_equal": _id_shape(agenthub_request.get("prompt_cache_key"))
        == _id_shape(codex_request.get("prompt_cache_key")),
        "instructions_sha256_equal": _payload_sha256(agenthub_request.get("instructions") or "")
        == _payload_sha256(codex_request.get("instructions") or ""),
    }
    return {
        "agenthub": {
            "path": str(agenthub_llm_io_path),
            "stage": "responses.send.request_raw",
            "request_present": bool(agenthub_request),
            "candidate_count": len(agenthub_candidates),
            "selected_candidate_index": int(agenthub_selected.get("candidate_index") or 0),
            "instructions_len": len(str(agenthub_request.get("instructions") or "")),
            "tools_count": len(list(agenthub_request.get("tools") or [])),
            "input_count": len(list(agenthub_request.get("input") or [])),
            "prompt_cache_key_shape": _id_shape(agenthub_request.get("prompt_cache_key")),
            "sha256": _payload_sha256(agenthub_request) if agenthub_request else "",
            "request": agenthub_request,
        },
        "codex": {
            "path": str(codex_llm_io_path),
            "stage": "stream_responses_api.request.raw",
            "request_present": bool(codex_request),
            "candidate_count": len(codex_candidates),
            "selected_candidate_index": int(codex_selected.get("candidate_index") or 0),
            "instructions_len": len(str(codex_request.get("instructions") or "")),
            "tools_count": len(list(codex_request.get("tools") or [])),
            "input_count": len(list(codex_request.get("input") or [])),
            "prompt_cache_key_shape": _id_shape(codex_request.get("prompt_cache_key")),
            "sha256": _payload_sha256(codex_request) if codex_request else "",
            "request": codex_request,
        },
        "comparison": comparison,
        "summary": {
            "instructions_equal": comparison["instructions_equal"],
            "input_equal": comparison["input_equal"],
            "tools_equal": comparison["tools_equal"],
            "model_equal": comparison["model_equal"],
            "reasoning_equal": comparison["reasoning_equal"],
            "include_equal": comparison["include_equal"],
            "prompt_cache_key_present_equal": comparison["prompt_cache_key_present_equal"],
            "prompt_cache_key_shape_equal": comparison["prompt_cache_key_shape_equal"],
            "agenthub_request_present": comparison["agenthub_present"],
            "codex_request_present": comparison["codex_present"],
        },
    }


def _normalize_tool_entries(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen_counts: dict[str, int] = {}
    for index, tool in enumerate(tools, start=1):
        name = str(tool.get("name") or "").strip()
        tool_type = str(tool.get("type") or "").strip()
        base_key = name or tool_type or f"unnamed_{index}"
        seen_counts[base_key] = seen_counts.get(base_key, 0) + 1
        key = base_key if seen_counts[base_key] == 1 else f"{base_key}#{seen_counts[base_key]}"
        entries.append(
            {
                "key": key,
                "name": name,
                "type": tool_type,
                "description": str(tool.get("description") or ""),
                "schema_sha256": _payload_sha256(tool),
                "tool": tool,
            }
        )
    return entries


def _build_tool_schema_layer(request_raw_layer: dict[str, Any]) -> dict[str, Any]:
    agenthub_tools = [
        dict(tool)
        for tool in list(dict(request_raw_layer.get("agenthub") or {}).get("request", {}).get("tools") or [])
        if isinstance(tool, dict)
    ]
    codex_tools = [
        dict(tool)
        for tool in list(dict(request_raw_layer.get("codex") or {}).get("request", {}).get("tools") or [])
        if isinstance(tool, dict)
    ]
    agenthub_entries = _normalize_tool_entries(agenthub_tools)
    codex_entries = _normalize_tool_entries(codex_tools)
    agenthub_map = {entry["key"]: entry for entry in agenthub_entries}
    codex_map = {entry["key"]: entry for entry in codex_entries}
    shared_keys = sorted(set(agenthub_map) & set(codex_map))
    shared_same = [key for key in shared_keys if agenthub_map[key]["tool"] == codex_map[key]["tool"]]
    shared_different = [key for key in shared_keys if agenthub_map[key]["tool"] != codex_map[key]["tool"]]
    return {
        "agenthub": {
            "tool_count": len(agenthub_entries),
            "tool_keys": [entry["key"] for entry in agenthub_entries],
            "tools": agenthub_entries,
        },
        "codex": {
            "tool_count": len(codex_entries),
            "tool_keys": [entry["key"] for entry in codex_entries],
            "tools": codex_entries,
        },
        "comparison": {
            "shared_tools": shared_keys,
            "shared_same_schema": shared_same,
            "shared_different_schema": shared_different,
            "agenthub_only": sorted(set(agenthub_map) - set(codex_map)),
            "codex_only": sorted(set(codex_map) - set(agenthub_map)),
            "all_shared_schema_equal": not shared_different,
        },
        "summary": {
            "agenthub_tool_count": len(agenthub_entries),
            "codex_tool_count": len(codex_entries),
            "agenthub_only": sorted(set(agenthub_map) - set(codex_map)),
            "codex_only": sorted(set(codex_map) - set(agenthub_map)),
            "shared_different_schema": shared_different,
            "all_shared_schema_equal": not shared_different,
        },
    }


def _build_agenthub_tool_chain(detail_path: Path) -> dict[str, Any]:
    detail = _read_json(detail_path)
    tool_events = [dict(item) for item in list(detail.get("tool_events") or []) if isinstance(item, dict)]
    entries: list[dict[str, Any]] = []
    for index, event in enumerate(tool_events, start=1):
        payload = dict(event.get("payload") or {})
        raw_item = dict(payload.get("provider_raw_item") or {})
        tool_name = (
            str(raw_item.get("name") or "").strip()
            or str(payload.get("function_call_name") or "").strip()
            or str(event.get("name") or "").strip()
        )
        entries.append(
            {
                "step": index,
                "tool_name": tool_name,
                "call_id": str(payload.get("call_id") or raw_item.get("call_id") or "").strip(),
                "function_call_name": str(payload.get("function_call_name") or "").strip(),
                "source_tool_name": str(payload.get("source_tool_name") or "").strip(),
                "ok": bool(event.get("ok")),
                "command_preview": _preview_text(payload.get("command") or ""),
                "arguments_preview": _preview_text(raw_item.get("arguments") or payload.get("interaction_input") or ""),
                "result_preview": _preview_text(
                    payload.get("output_text")
                    or payload.get("aggregated_output")
                    or payload.get("stdout")
                    or event.get("summary")
                    or ""
                ),
            }
        )
    return {
        "source": str(detail_path),
        "entries": entries,
        "tool_name_sequence": [entry["tool_name"] for entry in entries],
    }


def _build_codex_tool_chain(*, turn_actions_path: Path, detail_path: Path) -> dict[str, Any]:
    rows = _read_jsonl(turn_actions_path)
    calls: list[dict[str, Any]] = []
    results_by_call_id: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        stage = str(row.get("stage") or "").strip()
        payload = dict(row.get("payload") or {})
        if stage == "tool_loop.output_item.routed_tool_call":
            tool_call = dict(payload.get("tool_call") or {})
            response_item = dict(payload.get("response_item") or {})
            call_id = str(tool_call.get("call_id") or response_item.get("call_id") or "").strip()
            calls.append(
                {
                    "call_id": call_id,
                    "tool_name": str(tool_call.get("tool_name") or response_item.get("name") or "").strip(),
                    "arguments_preview": _preview_text(
                        tool_call.get("payload_preview")
                        or response_item.get("arguments_preview")
                        or response_item.get("arguments")
                        or ""
                    ),
                }
            )
            continue
        if stage != "tool_loop.in_flight.response_input":
            continue
        response_input_item = dict(payload.get("response_input_item") or {})
        call_id = str(response_input_item.get("call_id") or "").strip()
        if not call_id:
            continue
        results_by_call_id.setdefault(call_id, []).append(
            {
                "success": bool(response_input_item.get("success")),
                "result_preview": _preview_text(response_input_item.get("preview") or response_input_item.get("output") or ""),
            }
        )
    entries: list[dict[str, Any]] = []
    for index, call in enumerate(calls, start=1):
        first_result = (results_by_call_id.get(call["call_id"]) or [{}])[0]
        entries.append(
            {
                "step": index,
                "tool_name": call["tool_name"],
                "call_id": call["call_id"],
                "arguments_preview": call["arguments_preview"],
                "ok": bool(first_result.get("success")),
                "result_preview": str(first_result.get("result_preview") or ""),
            }
        )
    if not entries:
        detail = _read_json(detail_path)
        events = [dict(item) for item in list(detail.get("events") or []) if isinstance(item, dict)]
        fallback_types: list[str] = []
        for event in events:
            item = dict(event.get("item") or {})
            item_type = str(item.get("type") or "").strip()
            if item_type and item_type not in {"agent_message", "error"}:
                fallback_types.append(item_type)
        entries = [
            {
                "step": index,
                "tool_name": item_type,
                "call_id": "",
                "arguments_preview": "",
                "ok": True,
                "result_preview": "",
            }
            for index, item_type in enumerate(fallback_types, start=1)
        ]
    return {
        "source": str(turn_actions_path if turn_actions_path.exists() else detail_path),
        "entries": entries,
        "tool_name_sequence": [entry["tool_name"] for entry in entries],
    }


def _build_tool_call_chain_layer(
    *,
    agenthub_detail_path: Path,
    codex_detail_path: Path,
    codex_turn_actions_path: Path,
) -> dict[str, Any]:
    agenthub_chain = _build_agenthub_tool_chain(agenthub_detail_path)
    codex_chain = _build_codex_tool_chain(turn_actions_path=codex_turn_actions_path, detail_path=codex_detail_path)
    agenthub_sequence = list(agenthub_chain.get("tool_name_sequence") or [])
    codex_sequence = list(codex_chain.get("tool_name_sequence") or [])
    common_prefix_len = 0
    for left, right in zip(agenthub_sequence, codex_sequence):
        if left != right:
            break
        common_prefix_len += 1
    return {
        "agenthub": agenthub_chain,
        "codex": codex_chain,
        "comparison": {
            "tool_name_sequence_equal": agenthub_sequence == codex_sequence,
            "common_prefix_len": common_prefix_len,
            "agenthub_call_count": len(agenthub_sequence),
            "codex_call_count": len(codex_sequence),
            "agenthub_tool_names": agenthub_sequence,
            "codex_tool_names": codex_sequence,
        },
        "summary": {
            "tool_name_sequence_equal": agenthub_sequence == codex_sequence,
            "common_prefix_len": common_prefix_len,
            "agenthub_tool_names": agenthub_sequence,
            "codex_tool_names": codex_sequence,
        },
    }


def _inventory_signature(entries: list[dict[str, Any]], *, visible_only: bool) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for entry in entries:
        path_text = str(entry.get("path") or "").strip()
        if not path_text:
            continue
        if visible_only and any(part.startswith(".") for part in PurePosixPath(path_text).parts):
            continue
        items.append((path_text, str(entry.get("sha256") or "")))
    return items


def _build_workspace_side_effects_layer(
    *,
    agenthub_workspace: Path,
    codex_workspace: Path,
    agenthub_run: CommandResult,
    codex_run: CommandResult,
    agenthub_validation: CommandResult | None,
    codex_validation: CommandResult | None,
    agenthub_assistant_text: str,
    codex_assistant_text: str,
) -> dict[str, Any]:
    agenthub_inventory = _workspace_file_inventory(agenthub_workspace)
    codex_inventory = _workspace_file_inventory(codex_workspace)
    agenthub_all = _inventory_signature(agenthub_inventory, visible_only=False)
    codex_all = _inventory_signature(codex_inventory, visible_only=False)
    agenthub_visible = _inventory_signature(agenthub_inventory, visible_only=True)
    codex_visible = _inventory_signature(codex_inventory, visible_only=True)
    return {
        "agenthub": {
            "workspace": str(agenthub_workspace),
            "assistant_text": agenthub_assistant_text,
            "run": asdict(agenthub_run),
            "validation": asdict(agenthub_validation) if agenthub_validation else None,
            "files": agenthub_inventory,
            "visible_files": [path for path, _ in agenthub_visible],
        },
        "codex": {
            "workspace": str(codex_workspace),
            "assistant_text": codex_assistant_text,
            "run": asdict(codex_run),
            "validation": asdict(codex_validation) if codex_validation else None,
            "files": codex_inventory,
            "visible_files": [path for path, _ in codex_visible],
        },
        "comparison": {
            "all_files_equal": agenthub_all == codex_all,
            "visible_files_equal": agenthub_visible == codex_visible,
            "agenthub_only_all_paths": sorted(set(path for path, _ in agenthub_all) - set(path for path, _ in codex_all)),
            "codex_only_all_paths": sorted(set(path for path, _ in codex_all) - set(path for path, _ in agenthub_all)),
            "agenthub_only_visible_paths": sorted(
                set(path for path, _ in agenthub_visible) - set(path for path, _ in codex_visible)
            ),
            "codex_only_visible_paths": sorted(
                set(path for path, _ in codex_visible) - set(path for path, _ in agenthub_visible)
            ),
        },
        "summary": {
            "all_files_equal": agenthub_all == codex_all,
            "visible_files_equal": agenthub_visible == codex_visible,
            "agenthub_only_all_paths": sorted(set(path for path, _ in agenthub_all) - set(path for path, _ in codex_all)),
            "codex_only_all_paths": sorted(set(path for path, _ in codex_all) - set(path for path, _ in agenthub_all)),
        },
    }
