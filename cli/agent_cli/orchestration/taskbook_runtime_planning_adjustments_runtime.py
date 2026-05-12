from __future__ import annotations

import re
from typing import Any


def normalize_planning_adjustments(planning_adjustments: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(planning_adjustments or {})
    normalized: dict[str, Any] = {}

    scope_value = normalize_scope_adjustment(payload.get("scope_preference"))
    if scope_value is not None:
        normalized["scope_preference"] = scope_value

    workspace_value = normalize_workspace_policy(payload.get("workspace_policy"))
    if workspace_value is not None:
        normalized["workspace_policy"] = workspace_value

    parallel_value = normalize_parallelism(payload.get("max_parallel_cards"))
    if parallel_value is not None:
        normalized["max_parallel_cards"] = parallel_value

    extra_value = str(payload.get("extra_requirements") or "").strip()
    if extra_value and extra_value.lower() not in {"no extra requirements", "no extra requirements (recommended)"}:
        normalized["extra_requirements"] = extra_value

    return normalized


def normalize_scope_adjustment(value: Any) -> str | None:
    text = str(value or "").strip()
    normalized = text.lower()
    if not normalized or normalized in {"keep current scope", "keep scope"}:
        return None
    if normalized == "tighten scope":
        return "tighten_scope"
    if normalized == "expand scope":
        return "expand_scope"
    return text


def normalize_workspace_policy(value: Any) -> str | None:
    text = str(value or "").strip()
    normalized = text.lower()
    if not normalized or normalized == "keep current execution guard":
        return None
    if normalized == "require approval before live workspace writes":
        return "approval_before_live_workspace_writes"
    if normalized == "disallow background code changes":
        return "no_background_code_changes"
    if normalized == "prefer local execution only":
        return "local_only"
    return text


def normalize_parallelism(value: Any) -> int | str | None:
    text = str(value or "").strip()
    normalized = text.lower()
    if not normalized or normalized == "keep current parallelism":
        return None
    match = re.match(r"^(\d+)", text)
    if match:
        try:
            parsed = int(match.group(1))
        except ValueError:
            parsed = 0
        if parsed > 0:
            return parsed
    return text


def append_unique(target: list[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in target:
        target.append(text)


def apply_planning_adjustments(
    *,
    snapshot: Any,
    cards: list[Any],
    planning_adjustments: dict[str, Any],
) -> None:
    if not planning_adjustments:
        return

    scope_preference = planning_adjustments.get("scope_preference")
    if scope_preference:
        snapshot.global_rules["scope_preference"] = scope_preference
        if scope_preference == "tighten_scope":
            append_unique(snapshot.open_risks, "avoid adjacent edits outside owned_files unless explicitly required")
            for card in cards:
                append_unique(card.risk_hints, "Stay strictly inside owned_files unless the operator re-expands scope.")
        elif scope_preference == "expand_scope":
            append_unique(snapshot.assumptions, "Adjacent cleanup is allowed when it directly supports the objective.")
        else:
            append_unique(snapshot.assumptions, f"Scope guidance: {scope_preference}")

    workspace_policy = planning_adjustments.get("workspace_policy")
    if workspace_policy:
        snapshot.global_rules["workspace_policy"] = workspace_policy
        if workspace_policy == "approval_before_live_workspace_writes":
            for card in cards:
                if str(getattr(card.kind, "value", card.kind)) != "workspace_mutating":
                    continue
                append_unique(
                    card.handoff_requirements,
                    "Do not apply live-workspace writes before operator approval.",
                )
        elif workspace_policy == "no_background_code_changes":
            for card in cards:
                if str(getattr(card.kind, "value", card.kind)) != "workspace_mutating":
                    continue
                if str(getattr(card.execution_mode, "value", card.execution_mode)) in {
                    "background_teammate",
                    "background_task",
                }:
                    card.execution_mode = type(card.execution_mode).STAY_LOCAL
                append_unique(
                    card.handoff_requirements,
                    "Avoid background code changes; keep mutating work in the live runtime path.",
                )
        elif workspace_policy == "local_only":
            for card in cards:
                card.execution_mode = type(card.execution_mode).STAY_LOCAL
                append_unique(
                    card.handoff_requirements,
                    "Keep this card in the local runtime; do not dispatch to delegated/background executors.",
                )
        else:
            append_unique(snapshot.assumptions, f"Execution guard: {workspace_policy}")

    max_parallel_cards = planning_adjustments.get("max_parallel_cards")
    if max_parallel_cards is not None:
        snapshot.global_rules["max_parallel_cards"] = max_parallel_cards
        if isinstance(max_parallel_cards, int) and max_parallel_cards <= 1:
            for card in cards:
                card.can_run_in_parallel = False

    extra_requirements = str(planning_adjustments.get("extra_requirements") or "").strip()
    if extra_requirements:
        append_unique(snapshot.assumptions, extra_requirements)

    planner_summary = str(snapshot.planner_summary or "").strip()
    if planner_summary:
        snapshot.planner_summary = f"{planner_summary};operator_adjusted"
    else:
        snapshot.planner_summary = "operator_adjusted"


def planning_adjustment_lines(planning_adjustments: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    scope_preference = planning_adjustments.get("scope_preference")
    if scope_preference == "tighten_scope":
        lines.append("scope: tighten current scope")
    elif scope_preference == "expand_scope":
        lines.append("scope: allow adjacent supporting cleanup")
    elif scope_preference:
        lines.append(f"scope: {scope_preference}")

    workspace_policy = planning_adjustments.get("workspace_policy")
    if workspace_policy == "approval_before_live_workspace_writes":
        lines.append("execution: require approval before live workspace writes")
    elif workspace_policy == "no_background_code_changes":
        lines.append("execution: disallow background code changes")
    elif workspace_policy == "local_only":
        lines.append("execution: keep execution local only")
    elif workspace_policy:
        lines.append(f"execution: {workspace_policy}")

    max_parallel_cards = planning_adjustments.get("max_parallel_cards")
    if max_parallel_cards is not None:
        lines.append(f"parallelism: {max_parallel_cards}")

    extra_requirements = str(planning_adjustments.get("extra_requirements") or "").strip()
    if extra_requirements:
        lines.append(f"extra: {extra_requirements}")

    return lines
