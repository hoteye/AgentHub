from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cli.agent_cli.runtime_services.expert_review_execution_helpers_runtime import (
    _normalized_choice,
    _normalized_max_findings,
    _normalized_scope,
    _normalized_string_list,
)


def parse_expert_review_request_payload(
    payload: Mapping[str, Any] | None,
    *,
    default_strictness: str,
    focus_areas: tuple[str, ...],
    strictness_levels: tuple[str, ...],
) -> dict[str, Any]:
    mapping = dict(payload or {})
    task = str(mapping.get("task") or "").strip()
    if not task:
        raise ValueError("failed to parse function arguments: expected non-empty task")
    return {
        "task": task,
        "scope": _normalized_scope(mapping.get("scope")),
        "focus": _normalized_string_list(mapping.get("focus"), allowed=focus_areas),
        "artifact_paths": _normalized_string_list(mapping.get("artifact_paths")),
        "max_findings": _normalized_max_findings(mapping.get("max_findings")),
        "strictness": _normalized_choice(
            mapping.get("strictness"),
            allowed=strictness_levels,
            default=default_strictness,
        ),
    }


__all__ = ["parse_expert_review_request_payload"]
