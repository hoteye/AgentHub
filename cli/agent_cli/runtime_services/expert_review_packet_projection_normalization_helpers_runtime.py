from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cli.agent_cli.models import ResponseInputItem, ToolEvent
from cli.agent_cli.runtime_services.expert_review_packet_projection_pure_helpers_runtime import (
    MAX_ARTIFACT_PATHS,
    _dedupe_strings,
)


_PATHISH_KEYS = {
    "path",
    "paths",
    "file",
    "files",
    "filepath",
    "file_path",
    "directory",
    "directories",
    "dir",
    "cwd",
    "workdir",
    "workspace_root",
    "root",
    "root_path",
    "target",
    "target_path",
    "target_file",
    "source_path",
    "source_file",
    "source_files",
    "artifact_path",
    "artifact_paths",
    "changed_file",
    "changed_files",
}


def _response_items_from_turn(turn: dict[str, Any]) -> list[ResponseInputItem]:
    items: list[ResponseInputItem] = []
    for item in list(turn.get("response_items") or []):
        if isinstance(item, ResponseInputItem):
            items.append(item)
            continue
        if isinstance(item, Mapping):
            items.append(ResponseInputItem.from_dict(dict(item)))
    return items


def _normalize_tool_output(item: Any) -> dict[str, Any]:
    if isinstance(item, ToolEvent):
        return item.to_dict()
    if isinstance(item, Mapping):
        return dict(item)
    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return dict(payload)
    return {}


def _normalized_path(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/").rstrip("/")


def _extract_paths(value: Any, *, depth: int = 0, path_hint: bool = False) -> list[str]:
    if depth > 4:
        return []
    collected: list[str] = []

    def append(candidate: Any) -> None:
        text = str(candidate or "").strip()
        if not text:
            return
        if "\n" in text or "://" in text:
            return
        if text not in collected:
            collected.append(text)

    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized_key = str(key or "").strip().lower()
            nested_hint = path_hint or normalized_key in _PATHISH_KEYS
            if nested_hint and isinstance(nested, (list, tuple, set)):
                for item in list(nested):
                    append(item)
            elif nested_hint and not isinstance(nested, Mapping):
                append(nested)
            for item in _extract_paths(nested, depth=depth + 1, path_hint=nested_hint):
                if item not in collected:
                    collected.append(item)
        return collected
    if isinstance(value, (list, tuple, set)):
        for nested in list(value):
            for item in _extract_paths(nested, depth=depth + 1, path_hint=path_hint):
                if item not in collected:
                    collected.append(item)
        return collected
    if path_hint:
        append(value)
    return collected


def _matches_selected_path(candidate: str, selected_paths: list[str]) -> bool:
    normalized_candidate = _normalized_path(candidate)
    if not normalized_candidate:
        return False
    for selected in selected_paths:
        normalized_selected = _normalized_path(selected)
        if not normalized_selected:
            continue
        if normalized_candidate == normalized_selected:
            return True
        if normalized_candidate.endswith(f"/{normalized_selected}"):
            return True
        if normalized_selected.endswith(f"/{normalized_candidate}"):
            return True
    return False


def _matches_selected_path_set(paths: Any, selected_paths: list[str]) -> bool:
    if not selected_paths:
        return True
    for candidate in list(paths or []):
        if _matches_selected_path(str(candidate or ""), selected_paths):
            return True
    return False


def _turn_artifact_paths(turn: dict[str, Any]) -> list[str]:
    collected = _extract_paths(turn.get("attachments"))
    for item in list(turn.get("reference_context_items") or []):
        collected.extend(_extract_paths(item))
    for event in list(turn.get("turn_events") or []):
        collected.extend(_extract_paths(event))
    for tool_event in list(turn.get("tool_events") or []):
        collected.extend(_extract_paths(tool_event))
    return _dedupe_strings(collected, limit=MAX_ARTIFACT_PATHS)


def _turn_matches_artifact_paths(turn: dict[str, Any], artifact_paths: list[str]) -> bool:
    if not artifact_paths:
        return False
    for candidate in _turn_artifact_paths(turn):
        if _matches_selected_path(candidate, artifact_paths):
            return True
    return False


def _contains_reasoning_payload(value: Any, *, depth: int = 0) -> bool:
    if depth > 4:
        return False
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized_key = str(key or "").strip().lower()
            if normalized_key in {"reasoning", "reasoning_content", "encrypted_content"} and nested not in (None, ""):
                return True
            if _contains_reasoning_payload(nested, depth=depth + 1):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_reasoning_payload(item, depth=depth + 1) for item in value)
    return False


__all__ = [
    "_PATHISH_KEYS",
    "_contains_reasoning_payload",
    "_extract_paths",
    "_matches_selected_path",
    "_matches_selected_path_set",
    "_normalized_path",
    "_normalize_tool_output",
    "_response_items_from_turn",
    "_turn_artifact_paths",
    "_turn_matches_artifact_paths",
]
