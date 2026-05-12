from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime_services.expert_review_packet_projection_runtime import (
    MAX_SUMMARY_CHARS as _MAX_SUMMARY_CHARS,
    artifacts_projection as _artifacts_projection,
    candidate_summary as _candidate_summary,
    clip_text as _clip_text,
    excluded_sources as _excluded_sources,
    normalized_string_list as _normalized_string_list,
    runtime_constraints_projection as _runtime_constraints_projection,
    selected_messages as _selected_messages,
    selected_tool_activity as _selected_tool_activity,
    selected_turns as _selected_turns,
    user_goal_summary as _user_goal_summary,
)


_PACKET_VERSION = "expert_review.v1"
_DEFAULT_SCOPE = "current_task"
_DEFAULT_STRICTNESS = "medium"
_DEFAULT_MAX_FINDINGS = 5


def build_expert_review_packet(
    *,
    task: Any,
    thread_turns: Sequence[Any] | None = None,
    runtime_state: Mapping[str, Any] | None = None,
    tool_outputs: Sequence[Any] | None = None,
    scope: Any = _DEFAULT_SCOPE,
    focus: Sequence[Any] | None = None,
    artifact_paths: Sequence[Any] | None = None,
    max_findings: Any = _DEFAULT_MAX_FINDINGS,
    strictness: Any = _DEFAULT_STRICTNESS,
) -> dict[str, Any]:
    normalized_turns = [
        normalized
        for normalized in (_normalize_turn(turn) for turn in list(thread_turns or []))
        if normalized
    ]
    normalized_runtime_state = _normalize_mapping(runtime_state)
    normalized_tool_outputs = [
        normalized
        for normalized in (_normalize_tool_output(item) for item in list(tool_outputs or []))
        if normalized
    ]
    normalized_scope = _normalize_scope(scope)
    normalized_focus = _normalized_string_list(focus, lower=True)
    normalized_artifact_paths = _normalized_string_list(artifact_paths)
    selected_turns, selected_turns_truncated = _selected_turns(
        turns=normalized_turns,
        scope=normalized_scope,
        artifact_paths=normalized_artifact_paths,
    )
    messages, messages_truncated = _selected_messages(selected_turns)
    tool_activity, tool_activity_truncated = _selected_tool_activity(
        turns=selected_turns,
        tool_outputs=normalized_tool_outputs,
        artifact_paths=normalized_artifact_paths,
        scope=normalized_scope,
    )
    artifacts = _artifacts_projection(
        runtime_state=normalized_runtime_state,
        artifact_paths=normalized_artifact_paths,
        scope=normalized_scope,
    )
    return {
        "packet_version": _PACKET_VERSION,
        "review_request": {
            "task": _clip_text(task, max_chars=_MAX_SUMMARY_CHARS)[0],
            "scope": normalized_scope,
            "focus": normalized_focus,
            "artifact_paths": normalized_artifact_paths,
            "max_findings": _normalize_max_findings(max_findings),
            "strictness": _normalize_strictness(strictness),
        },
        "selection": {
            "scope": normalized_scope,
            "total_turn_count": len(normalized_turns),
            "selected_turn_count": len(selected_turns),
            "selected_turn_ids": [
                str(turn.get("turn_id") or f"turn_{index + 1}")
                for index, turn in enumerate(selected_turns)
            ],
            "selected_turns_truncated": selected_turns_truncated,
        },
        "observable_context": {
            "user_goal_summary": _user_goal_summary(
                selected_turns=selected_turns,
                runtime_state=normalized_runtime_state,
            ),
            "candidate_summary": _candidate_summary(
                selected_turns=selected_turns,
                runtime_state=normalized_runtime_state,
            ),
            "messages": messages,
            "messages_truncated": messages_truncated,
            "tool_activity": tool_activity,
            "tool_activity_truncated": tool_activity_truncated,
            "artifacts": artifacts,
            "runtime_constraints": _runtime_constraints_projection(normalized_runtime_state),
        },
        "omissions": {
            "reasoning_traces_excluded": True,
            "excluded_sources": _excluded_sources(
                turns=selected_turns,
                tool_outputs=normalized_tool_outputs,
            ),
        },
    }


def _normalize_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return dict(value)


def _normalize_turn(turn: Any) -> dict[str, Any]:
    if isinstance(turn, Mapping):
        return dict(turn)
    to_dict = getattr(turn, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return dict(payload)
    return {}


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


def _normalize_scope(scope: Any) -> str:
    normalized = str(scope or "").strip().lower()
    if normalized in {"latest_turn", "current_task", "selected_artifacts"}:
        return normalized
    return _DEFAULT_SCOPE


def _normalize_strictness(strictness: Any) -> str:
    normalized = str(strictness or "").strip().lower()
    if normalized in {"low", "medium", "high"}:
        return normalized
    return _DEFAULT_STRICTNESS


def _normalize_max_findings(value: Any) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_FINDINGS
    return max(1, min(10, normalized))
