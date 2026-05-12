from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from cli.agent_cli.runtime_services.expert_review_execution_helpers_runtime import (
    _candidate_model_display,
    _candidate_model_selector,
    _candidate_provider_display,
    _candidate_provider_selector,
    _candidate_reviewer_capability_policy,
    _candidate_reviewer_capability_source,
    _candidate_reviewer_reasoning_effort,
    _candidate_reviewer_reasoning_mode,
    _candidate_reviewer_reasoning_strategy,
    _resolved_reviewer_model,
    _resolved_reviewer_provider,
)


@dataclass(slots=True, frozen=True)
class ReviewerExecutionMetadata:
    provider_selector: str | None
    model_selector: str | None
    reviewer_provider: str
    reviewer_model: str
    reviewer_reasoning_strategy: str
    reviewer_reasoning_effort: str | None
    reviewer_reasoning_mode: str
    reviewer_capability_policy: str
    reviewer_capability_source: str
    cross_provider: bool
    cross_vendor: bool
    selection_reason: str

    def delegate_resolution_kwargs(self) -> dict[str, Any]:
        return {
            "provider": self.provider_selector,
            "model": self.model_selector,
            "reasoning_effort": self.reviewer_reasoning_effort,
            "timeout": None,
        }

    def prompt_policy(self) -> dict[str, Any]:
        return {
            "reviewer_capability_policy": self.reviewer_capability_policy,
            "reviewer_capability_source": self.reviewer_capability_source,
            "reviewer_reasoning_strategy": self.reviewer_reasoning_strategy,
            "reviewer_reasoning_effort": self.reviewer_reasoning_effort or "",
            "reviewer_reasoning_mode": self.reviewer_reasoning_mode,
        }

    def spawn_request_kwargs(
        self,
        *,
        task: str,
        role: str,
        reason: str,
        mode: str,
        task_shape: str,
    ) -> dict[str, Any]:
        return {
            "task": task,
            "role": role,
            "model": self.model_selector,
            "provider": self.provider_selector,
            "reasoning_effort": self.reviewer_reasoning_effort,
            "timeout": None,
            "async_mode": True,
            "reason": reason,
            "mode": mode,
            "wait_required": False,
            "task_shape": task_shape,
        }

    def failure_result_kwargs(self) -> dict[str, Any]:
        return {
            "reviewer_provider": self.reviewer_provider,
            "reviewer_model": self.reviewer_model,
            "reviewer_reasoning_strategy": self.reviewer_reasoning_strategy,
            "reviewer_reasoning_effort": self.reviewer_reasoning_effort,
            "reviewer_reasoning_mode": self.reviewer_reasoning_mode,
            "reviewer_capability_policy": self.reviewer_capability_policy,
            "reviewer_capability_source": self.reviewer_capability_source,
        }

    def event_kwargs(self) -> dict[str, Any]:
        return {
            **self.failure_result_kwargs(),
            "cross_provider": self.cross_provider,
            "cross_vendor": self.cross_vendor,
            "selection_reason": self.selection_reason,
        }

    def parse_result_kwargs(
        self,
        *,
        scope: str,
        focus: Sequence[str],
        strictness: str,
        review_elapsed_ms: int,
    ) -> dict[str, Any]:
        return {
            **self.failure_result_kwargs(),
            "cross_provider": self.cross_provider,
            "cross_vendor": self.cross_vendor,
            "reviewer_reasoning_effort": self.reviewer_reasoning_effort or "",
            "scope": scope,
            "focus": list(focus),
            "strictness": strictness,
            "review_elapsed_ms": review_elapsed_ms,
        }


def _selected_candidate(selection: Mapping[str, Any]) -> dict[str, Any]:
    return dict(selection.get("selected_candidate") or {})


def selected_reviewer_execution_metadata(
    selection: Mapping[str, Any],
) -> ReviewerExecutionMetadata:
    selected_candidate = _selected_candidate(selection)
    return ReviewerExecutionMetadata(
        provider_selector=_candidate_provider_selector(selected_candidate),
        model_selector=_candidate_model_selector(selected_candidate),
        reviewer_provider=_candidate_provider_display(selected_candidate),
        reviewer_model=_candidate_model_display(selected_candidate),
        reviewer_reasoning_strategy=_candidate_reviewer_reasoning_strategy(selected_candidate),
        reviewer_reasoning_effort=_candidate_reviewer_reasoning_effort(selected_candidate),
        reviewer_reasoning_mode=_candidate_reviewer_reasoning_mode(selected_candidate),
        reviewer_capability_policy=_candidate_reviewer_capability_policy(selected_candidate),
        reviewer_capability_source=_candidate_reviewer_capability_source(selected_candidate),
        cross_provider=True,
        cross_vendor=bool(selected_candidate.get("cross_vendor")),
        selection_reason=str(selection.get("selection_reason") or ""),
    )


def resolved_reviewer_execution_metadata(
    selection: Mapping[str, Any],
    resolution: Any,
) -> ReviewerExecutionMetadata:
    selected_candidate = _selected_candidate(selection)
    selected_metadata = selected_reviewer_execution_metadata(selection)
    return ReviewerExecutionMetadata(
        provider_selector=selected_metadata.provider_selector,
        model_selector=selected_metadata.model_selector,
        reviewer_provider=_resolved_reviewer_provider(selected_candidate, resolution),
        reviewer_model=_resolved_reviewer_model(selected_candidate, resolution),
        reviewer_reasoning_strategy=selected_metadata.reviewer_reasoning_strategy,
        reviewer_reasoning_effort=selected_metadata.reviewer_reasoning_effort,
        reviewer_reasoning_mode=selected_metadata.reviewer_reasoning_mode,
        reviewer_capability_policy=selected_metadata.reviewer_capability_policy,
        reviewer_capability_source=selected_metadata.reviewer_capability_source,
        cross_provider=selected_metadata.cross_provider,
        cross_vendor=selected_metadata.cross_vendor,
        selection_reason=selected_metadata.selection_reason,
    )


__all__ = [
    "ReviewerExecutionMetadata",
    "resolved_reviewer_execution_metadata",
    "selected_reviewer_execution_metadata",
]
