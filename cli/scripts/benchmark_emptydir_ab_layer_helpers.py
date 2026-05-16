from __future__ import annotations

from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from cli.scripts.benchmark_emptydir_ab_layer_request_helpers import (
        _build_request_raw_layer,
        _build_tool_schema_layer,
        _normalize_tool_entries,
        _request_raw_candidates,
        _select_request_raw_candidate,
    )
    from cli.scripts.benchmark_emptydir_ab_model_io_helpers import (
        CommandResult,
        _preview_text,
        _read_json,
        _read_jsonl,
        _workspace_file_inventory,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    import benchmark_emptydir_ab_layer_request_helpers as _request_helpers  # type: ignore[no-redef]

    _build_request_raw_layer = _request_helpers._build_request_raw_layer
    _build_tool_schema_layer = _request_helpers._build_tool_schema_layer
    _normalize_tool_entries = _request_helpers._normalize_tool_entries
    _request_raw_candidates = _request_helpers._request_raw_candidates
    _select_request_raw_candidate = _request_helpers._select_request_raw_candidate
    from benchmark_emptydir_ab_model_io_helpers import (  # type: ignore[no-redef]
        CommandResult,
        _preview_text,
        _read_json,
        _read_jsonl,
        _workspace_file_inventory,
    )


def _build_agenthub_tool_chain(detail_path: Path) -> dict[str, Any]:
    detail = _read_json(detail_path)
    tool_events = [
        dict(item) for item in list(detail.get("tool_events") or []) if isinstance(item, dict)
    ]
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
                "arguments_preview": _preview_text(
                    raw_item.get("arguments") or payload.get("interaction_input") or ""
                ),
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
                    "tool_name": str(
                        tool_call.get("tool_name") or response_item.get("name") or ""
                    ).strip(),
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
                "result_preview": _preview_text(
                    response_input_item.get("preview") or response_input_item.get("output") or ""
                ),
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
    codex_chain = _build_codex_tool_chain(
        turn_actions_path=codex_turn_actions_path, detail_path=codex_detail_path
    )
    agenthub_sequence = list(agenthub_chain.get("tool_name_sequence") or [])
    codex_sequence = list(codex_chain.get("tool_name_sequence") or [])
    common_prefix_len = 0
    for left, right in zip(agenthub_sequence, codex_sequence, strict=False):
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


def _inventory_signature(
    entries: list[dict[str, Any]], *, visible_only: bool
) -> list[tuple[str, str]]:
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
            "agenthub_only_all_paths": sorted(
                set(path for path, _ in agenthub_all) - set(path for path, _ in codex_all)
            ),
            "codex_only_all_paths": sorted(
                set(path for path, _ in codex_all) - set(path for path, _ in agenthub_all)
            ),
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
            "agenthub_only_all_paths": sorted(
                set(path for path, _ in agenthub_all) - set(path for path, _ in codex_all)
            ),
            "codex_only_all_paths": sorted(
                set(path for path, _ in codex_all) - set(path for path, _ in agenthub_all)
            ),
        },
    }
