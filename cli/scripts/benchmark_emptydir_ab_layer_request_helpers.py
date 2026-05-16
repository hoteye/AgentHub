from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from cli.scripts.benchmark_emptydir_ab_model_io_helpers import (
        _id_shape,
        _payload_sha256,
        _read_jsonl,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from benchmark_emptydir_ab_model_io_helpers import (  # type: ignore[no-redef]
        _id_shape,
        _payload_sha256,
        _read_jsonl,
    )


def _request_raw_candidates(
    log_path: Path, *, stage: str, request_field: str | None
) -> list[dict[str, Any]]:
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


def _build_request_raw_layer(
    *, agenthub_llm_io_path: Path, codex_llm_io_path: Path
) -> dict[str, Any]:
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
        "instructions_equal": agenthub_request.get("instructions")
        == codex_request.get("instructions"),
        "input_equal": agenthub_request.get("input") == codex_request.get("input"),
        "tools_equal": agenthub_request.get("tools") == codex_request.get("tools"),
        "model_equal": agenthub_request.get("model") == codex_request.get("model"),
        "reasoning_equal": agenthub_request.get("reasoning") == codex_request.get("reasoning"),
        "include_equal": agenthub_request.get("include") == codex_request.get("include"),
        "prompt_cache_key_present_equal": bool(
            str(agenthub_request.get("prompt_cache_key") or "").strip()
        )
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
        for tool in list(
            dict(request_raw_layer.get("agenthub") or {}).get("request", {}).get("tools") or []
        )
        if isinstance(tool, dict)
    ]
    codex_tools = [
        dict(tool)
        for tool in list(
            dict(request_raw_layer.get("codex") or {}).get("request", {}).get("tools") or []
        )
        if isinstance(tool, dict)
    ]
    agenthub_entries = _normalize_tool_entries(agenthub_tools)
    codex_entries = _normalize_tool_entries(codex_tools)
    agenthub_map = {entry["key"]: entry for entry in agenthub_entries}
    codex_map = {entry["key"]: entry for entry in codex_entries}
    shared_keys = sorted(set(agenthub_map) & set(codex_map))
    shared_same = [
        key for key in shared_keys if agenthub_map[key]["tool"] == codex_map[key]["tool"]
    ]
    shared_different = [
        key for key in shared_keys if agenthub_map[key]["tool"] != codex_map[key]["tool"]
    ]
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
