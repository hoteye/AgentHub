from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cli.agent_cli.runtime_services.expert_review_packet_projection_helpers_runtime import (
    MAX_ARGUMENT_CHARS,
    MAX_ARTIFACT_PATHS,
    MAX_CHANGED_FILES,
    MAX_CONSTRAINT_TEXT_CHARS,
    MAX_DIFF_SUMMARY_CHARS,
    MAX_EVIDENCE_TEXT_CHARS,
    MAX_MESSAGE_CHARS,
    MAX_MESSAGE_ENTRIES,
    MAX_SCOPE_TURNS,
    MAX_SUMMARY_CHARS,
    MAX_TEST_EVIDENCE,
    MAX_TOOL_ACTIVITY_ITEMS,
    MAX_TOOL_RESULT_CHARS,
    clip_text,
    normalized_string_list,
    _assistant_text_from_turn,
    _contains_reasoning_payload,
    _dedupe_strings,
    _dedupe_tool_activity,
    _matches_selected_path,
    _matches_selected_path_set,
    _response_items_from_turn,
    _test_evidence_projection,
    _tool_activity_from_tool_output,
    _tool_activity_from_turn,
    _turn_matches_artifact_paths,
)


def selected_turns(
    *,
    turns: list[dict[str, Any]],
    scope: str,
    artifact_paths: list[str],
) -> tuple[list[dict[str, Any]], bool]:
    if not turns:
        return [], False
    if scope == "latest_turn":
        return [dict(turns[-1])], False
    if scope == "current_task":
        return [dict(turn) for turn in turns[-MAX_SCOPE_TURNS:]], len(turns) > MAX_SCOPE_TURNS

    selected: list[dict[str, Any]] = []
    if artifact_paths:
        for turn in turns:
            if _turn_matches_artifact_paths(turn, artifact_paths):
                selected.append(dict(turn))
    if turns[-1] not in selected:
        selected.append(dict(turns[-1]))
    if len(selected) > MAX_SCOPE_TURNS:
        return selected[-MAX_SCOPE_TURNS:], True
    return selected, False


def selected_messages(turns: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    entries: list[dict[str, Any]] = []
    for index, turn in enumerate(turns):
        turn_id = str(turn.get("turn_id") or f"turn_{index + 1}")
        user_text = str(turn.get("user_text") or "").strip()
        if user_text:
            clipped_text, truncated = clip_text(user_text, max_chars=MAX_MESSAGE_CHARS)
            entries.append(
                {
                    "turn_id": turn_id,
                    "role": "user",
                    "text": clipped_text,
                    "truncated": truncated,
                }
            )
        assistant_text = _assistant_text_from_turn(turn)
        if assistant_text:
            clipped_text, truncated = clip_text(assistant_text, max_chars=MAX_MESSAGE_CHARS)
            entries.append(
                {
                    "turn_id": turn_id,
                    "role": "assistant",
                    "text": clipped_text,
                    "truncated": truncated,
                }
            )
    return entries[:MAX_MESSAGE_ENTRIES], len(entries) > MAX_MESSAGE_ENTRIES


def user_goal_summary(
    *,
    selected_turns: list[dict[str, Any]],
    runtime_state: dict[str, Any],
) -> str:
    runtime_summary = str(runtime_state.get("user_goal_summary") or "").strip()
    if runtime_summary:
        return clip_text(runtime_summary, max_chars=MAX_SUMMARY_CHARS)[0]
    for turn in reversed(selected_turns):
        user_text = str(turn.get("user_text") or "").strip()
        if user_text:
            return clip_text(user_text, max_chars=MAX_SUMMARY_CHARS)[0]
    return ""


def candidate_summary(
    *,
    selected_turns: list[dict[str, Any]],
    runtime_state: dict[str, Any],
) -> str:
    runtime_summary = str(runtime_state.get("candidate_summary") or "").strip()
    if runtime_summary:
        return clip_text(runtime_summary, max_chars=MAX_SUMMARY_CHARS)[0]
    for turn in reversed(selected_turns):
        assistant_text = _assistant_text_from_turn(turn)
        if assistant_text:
            return clip_text(assistant_text, max_chars=MAX_SUMMARY_CHARS)[0]
    return ""


def selected_tool_activity(
    *,
    turns: list[dict[str, Any]],
    tool_outputs: list[dict[str, Any]],
    artifact_paths: list[str],
    scope: str,
) -> tuple[list[dict[str, Any]], bool]:
    entries: list[dict[str, Any]] = []
    for index, turn in enumerate(turns):
        turn_id = str(turn.get("turn_id") or f"turn_{index + 1}")
        entries.extend(_tool_activity_from_turn(turn, turn_id=turn_id))
    for item in tool_outputs:
        projected = _tool_activity_from_tool_output(item)
        if projected is not None:
            entries.append(projected)
    if scope == "selected_artifacts" and artifact_paths:
        entries = [
            entry
            for entry in entries
            if _matches_selected_path_set(entry.get("artifact_paths"), artifact_paths)
        ]
    deduped = _dedupe_tool_activity(entries)
    return deduped[:MAX_TOOL_ACTIVITY_ITEMS], len(deduped) > MAX_TOOL_ACTIVITY_ITEMS


def artifacts_projection(
    *,
    runtime_state: dict[str, Any],
    artifact_paths: list[str],
    scope: str,
) -> dict[str, Any]:
    changed_files = [
        str(item or "").strip()
        for item in list(runtime_state.get("changed_files") or runtime_state.get("changed_file_paths") or [])
        if str(item or "").strip()
    ]
    if scope == "selected_artifacts" and artifact_paths:
        changed_files = [
            item for item in changed_files if _matches_selected_path(item, artifact_paths)
        ]
    diff_summary, diff_summary_truncated = clip_text(
        runtime_state.get("diff_summary"),
        max_chars=MAX_DIFF_SUMMARY_CHARS,
    )
    test_evidence, test_evidence_truncated = _test_evidence_projection(runtime_state)
    return {
        "requested_paths": artifact_paths,
        "changed_files": changed_files[:MAX_CHANGED_FILES],
        "changed_files_truncated": len(changed_files) > MAX_CHANGED_FILES,
        "diff_summary": diff_summary,
        "diff_summary_truncated": diff_summary_truncated,
        "test_evidence": test_evidence,
        "test_evidence_truncated": test_evidence_truncated,
    }


def runtime_constraints_projection(runtime_state: dict[str, Any]) -> dict[str, Any]:
    projection: dict[str, Any] = {}
    nested = runtime_state.get("runtime_constraints")
    if isinstance(nested, Mapping):
        merged_state = {**dict(nested), **runtime_state}
    else:
        merged_state = dict(runtime_state)
    for key in (
        "approval_policy",
        "sandbox_mode",
        "workspace_write_access",
        "network_access_enabled",
        "read_only_review",
    ):
        if key not in merged_state:
            continue
        value = merged_state.get(key)
        if isinstance(value, bool):
            projection[key] = value
            continue
        text = str(value or "").strip()
        if text:
            projection[key] = clip_text(text, max_chars=MAX_CONSTRAINT_TEXT_CHARS)[0]
    for key in ("policy_constraints", "safety_constraints"):
        value = merged_state.get(key)
        if isinstance(value, list):
            projection[key] = [
                clip_text(item, max_chars=MAX_CONSTRAINT_TEXT_CHARS)[0]
                for item in value
                if str(item or "").strip()
            ][:8]
        elif str(value or "").strip():
            projection[key] = [clip_text(value, max_chars=MAX_CONSTRAINT_TEXT_CHARS)[0]]
    return projection


def excluded_sources(
    *,
    turns: list[dict[str, Any]],
    tool_outputs: list[dict[str, Any]],
) -> list[str]:
    excluded: list[str] = []
    for turn in turns:
        if str(turn.get("commentary_text") or "").strip():
            excluded.append("commentary_text")
        for response_item in _response_items_from_turn(turn):
            item_type = str(getattr(response_item, "item_type", "") or "").strip().lower()
            if item_type == "reasoning":
                excluded.append("response_items.reasoning")
                break
            content = getattr(response_item, "content", None)
            if isinstance(content, list) and any(
                isinstance(entry, Mapping) and str(entry.get("type") or "").strip().lower() == "reasoning"
                for entry in content
            ):
                excluded.append("response_items.reasoning")
                break
        for event in list(turn.get("turn_events") or []):
            if not isinstance(event, Mapping):
                continue
            item = event.get("item")
            if not isinstance(item, Mapping):
                continue
            item_type = str(item.get("type") or "").strip().lower()
            if item_type == "reasoning":
                excluded.append("turn_events.reasoning")
            if item.get("encrypted_content") not in (None, ""):
                excluded.append("turn_events.encrypted_content")
    for tool_output in tool_outputs:
        payload = tool_output.get("payload")
        if _contains_reasoning_payload(payload):
            excluded.append("tool_outputs.reasoning_payload")
    return _dedupe_strings(excluded, limit=8)

