from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_core.orchestration_commands_helpers_runtime_text import (
    _orchestration_preview_full,
    _orchestration_preview_summary,
    _truncate_prompt_text,
)


def _single_answer(response: dict[str, Any], question_id: str) -> str:
    answers = dict((response or {}).get("answers") or {})
    payload = dict(answers.get(question_id) or {})
    values = [str(item).strip() for item in list(payload.get("answers") or []) if str(item).strip()]
    return values[0] if values else ""


def _planning_scope_update(answer: str) -> str | None:
    normalized = str(answer or "").strip().lower()
    if not normalized or normalized in {"keep current scope", "keep scope"}:
        return None
    if normalized == "tighten scope":
        return "tighten_scope"
    if normalized == "expand scope":
        return "expand_scope"
    return str(answer or "").strip() or None


def _planning_workspace_update(answer: str) -> str | None:
    normalized = str(answer or "").strip().lower()
    if not normalized or normalized == "keep current execution guard":
        return None
    if normalized == "require approval before live workspace writes":
        return "approval_before_live_workspace_writes"
    if normalized == "disallow background code changes":
        return "no_background_code_changes"
    if normalized == "prefer local execution only":
        return "local_only"
    return str(answer or "").strip() or None


def _planning_parallelism_update(answer: str) -> int | str | None:
    normalized = str(answer or "").strip().lower()
    if not normalized or normalized == "keep current parallelism":
        return None
    digits = ""
    for char in str(answer or ""):
        if char.isdigit():
            digits += char
        elif digits:
            break
    if digits:
        try:
            return max(1, int(digits))
        except ValueError:
            return None
    return str(answer or "").strip() or None


def _planning_extra_update(answer: str) -> str | None:
    text = str(answer or "").strip()
    if not text or text.lower() in {"no extra requirements", "no extra requirements (recommended)"}:
        return None
    return text


def _merge_planning_adjustments(current: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current or {})
    for key, value in dict(updates or {}).items():
        if value is None or (isinstance(value, str) and not value.strip()):
            merged.pop(str(key), None)
            continue
        merged[str(key)] = value
    return merged


def _orchestration_action_questions(
    preview: dict[str, Any],
    *,
    full_view: bool,
    taskbook_action_id: str,
    taskbook_action_confirm: str,
    taskbook_action_adjust: str,
    taskbook_action_view: str,
    taskbook_action_back: str,
    taskbook_action_cancel: str,
) -> list[dict[str, Any]]:
    question_text = _orchestration_preview_full(preview) if full_view else _orchestration_preview_summary(preview)
    if full_view:
        options = [
            {"label": taskbook_action_confirm, "description": "Create the orchestration run from this preview."},
            {"label": taskbook_action_adjust, "description": "Change constraints and regenerate the preview."},
            {"label": taskbook_action_back, "description": "Return to the compact summary view."},
            {"label": taskbook_action_cancel, "description": "Cancel without creating a run."},
        ]
        header = "Taskbook Full"
    else:
        options = [
            {"label": taskbook_action_confirm, "description": "Create the orchestration run from this preview."},
            {"label": taskbook_action_adjust, "description": "Change constraints and regenerate the preview."},
            {"label": taskbook_action_view, "description": "Inspect the full taskbook and card detail."},
            {"label": taskbook_action_cancel, "description": "Cancel without creating a run."},
        ]
        header = "Taskbook"
    return [
        {
            "id": taskbook_action_id,
            "header": header,
            "question": _truncate_prompt_text(question_text),
            "options": options,
        }
    ]
