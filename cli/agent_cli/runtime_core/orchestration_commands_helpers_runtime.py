from __future__ import annotations

from typing import Any

from cli.agent_cli.orchestration import taskbook_runtime as taskbook_runtime_service
from cli.agent_cli.runtime_core import orchestration_commands_helpers_runtime_helpers as _helpers
from cli.agent_cli.runtime_core.request_user_input_contract_runtime import (
    normalize_request_user_input_questions,
    normalize_request_user_input_response,
)

_TASKBOOK_ACTION_ID = "taskbook_action"
_TASKBOOK_ACTION_CONFIRM = "Confirm and start"
_TASKBOOK_ACTION_ADJUST = "Adjust planning"
_TASKBOOK_ACTION_VIEW = "View full taskbook and cards"
_TASKBOOK_ACTION_BACK = "Back to summary"
_TASKBOOK_ACTION_CANCEL = "Cancel"

_TASKBOOK_SCOPE_ID = "scope_preference"
_TASKBOOK_WORKSPACE_ID = "workspace_policy"
_TASKBOOK_PARALLELISM_ID = "max_parallel_cards"
_TASKBOOK_EXTRA_ID = "extra_requirements"


def _preview_request_orchestration(runtime: Any, request: dict[str, Any]) -> dict[str, Any]:
    preview = _preview_orchestration_run(
        runtime,
        str(request.get("source_text") or ""),
        planning_adjustments=dict(request.get("planning_adjustments") or {}),
        relaxed_taskbook=True,
    )
    return {
        "status": "preview_ready",
        "confirmation_required": bool(request.get("confirmation_required", True)),
        "next_action": "show_preview_confirm_ui",
        "preview": dict(preview),
    }


def _run_orchestration_confirmation(
    runtime: Any,
    source_text: str,
    *,
    initial_planning_adjustments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    planning_adjustments: dict[str, Any] = dict(initial_planning_adjustments or {})
    preview = _preview_orchestration_run(
        runtime,
        source_text,
        planning_adjustments=planning_adjustments,
        relaxed_taskbook=True,
    )
    handler = getattr(runtime, "request_user_input_handler", None)
    if not callable(handler):
        return {
            "status": "interactive_unavailable",
            "preview": preview,
            "planning_adjustment_lines": list(preview.get("planning_adjustment_lines") or []),
        }

    full_view = False
    while True:
        action_response = _request_user_input_response(
            runtime,
            _orchestration_action_questions(preview, full_view=full_view),
        )
        action = _single_answer(action_response, _TASKBOOK_ACTION_ID)
        if action in {"", _TASKBOOK_ACTION_CANCEL}:
            return {
                "status": "cancelled",
                "preview": preview,
                "planning_adjustment_lines": list(preview.get("planning_adjustment_lines") or []),
            }
        if action == _TASKBOOK_ACTION_VIEW:
            full_view = True
            continue
        if action == _TASKBOOK_ACTION_BACK:
            full_view = False
            continue
        if action == _TASKBOOK_ACTION_ADJUST:
            adjustment_updates = _collect_planning_adjustment_updates(runtime)
            if adjustment_updates is None:
                return {
                    "status": "cancelled",
                    "preview": preview,
                    "planning_adjustment_lines": list(
                        preview.get("planning_adjustment_lines") or []
                    ),
                }
            planning_adjustments = _merge_planning_adjustments(
                planning_adjustments, adjustment_updates
            )
            preview = _preview_orchestration_run(
                runtime,
                source_text,
                planning_adjustments=planning_adjustments,
                relaxed_taskbook=True,
            )
            full_view = False
            continue
        if action == _TASKBOOK_ACTION_CONFIRM:
            created_run = _create_orchestration_run(
                runtime,
                source_text,
                planning_adjustments=planning_adjustments,
                relaxed_taskbook=True,
            )
            dispatch_run = _dispatch_created_orchestration_run(runtime, created_run)
            return {
                "status": "confirmed",
                "preview": preview,
                "created_run": created_run,
                "dispatch_run": dispatch_run,
                "planning_adjustment_lines": list(preview.get("planning_adjustment_lines") or []),
            }
        return {
            "status": "cancelled",
            "preview": preview,
            "planning_adjustment_lines": list(preview.get("planning_adjustment_lines") or []),
        }


def _preview_orchestration_run(
    runtime: Any,
    source_text: str,
    *,
    planning_adjustments: dict[str, Any] | None = None,
    relaxed_taskbook: bool = False,
) -> dict[str, Any]:
    normalized_adjustments = dict(planning_adjustments or {})
    preview_runner = getattr(runtime, "preview_orchestration_run", None)
    if callable(preview_runner):
        preview = preview_runner(
            source_text,
            planning_adjustments=normalized_adjustments,
            relaxed_taskbook=relaxed_taskbook,
        )
    else:
        preview = taskbook_runtime_service.preview_orchestration_run(
            runtime,
            source_text,
            planning_adjustments=normalized_adjustments,
            relaxed_taskbook=relaxed_taskbook,
        )
    if not isinstance(preview, dict):
        raise ValueError("preview_orchestration_run returned invalid payload")
    return dict(preview)


def _create_orchestration_run(
    runtime: Any,
    source_text: str,
    *,
    planning_adjustments: dict[str, Any] | None = None,
    relaxed_taskbook: bool = False,
) -> dict[str, Any]:
    normalized_adjustments = dict(planning_adjustments or {})
    create_runner = getattr(runtime, "create_orchestration_run", None)
    if callable(create_runner):
        created_run = create_runner(
            source_text,
            planning_adjustments=normalized_adjustments,
            relaxed_taskbook=relaxed_taskbook,
        )
    else:
        created_run = taskbook_runtime_service.create_orchestration_run(
            runtime,
            source_text,
            planning_adjustments=normalized_adjustments,
            relaxed_taskbook=relaxed_taskbook,
        )
    if not isinstance(created_run, dict):
        raise ValueError("create_orchestration_run returned invalid payload")
    return dict(created_run)


def _dispatch_created_orchestration_run(
    runtime: Any,
    created_run: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(created_run.get("run_id") or "").strip()
    if not run_id:
        return {}
    dispatch_runner = getattr(runtime, "dispatch_orchestration_run", None)
    if not callable(dispatch_runner):
        return {}
    try:
        dispatched = dispatch_runner(run_id)
    except Exception as exc:
        return {
            "run_id": run_id,
            "dispatch_error": f"{type(exc).__name__}: {exc}",
        }
    return dict(dispatched) if isinstance(dispatched, dict) else {}


def _request_user_input_response(runtime: Any, questions: list[dict[str, Any]]) -> dict[str, Any]:
    handler = getattr(runtime, "request_user_input_handler", None)
    if not callable(handler):
        return {}
    normalized_questions = normalize_request_user_input_questions(questions)
    response = handler({"questions": normalized_questions})
    if not isinstance(response, dict):
        return {}
    return normalize_request_user_input_response(
        response,
        question_ids={str(item.get("id") or "").strip() for item in normalized_questions},
    )


_single_answer = _helpers._single_answer


def _collect_planning_adjustment_updates(runtime: Any) -> dict[str, Any] | None:
    structured_response = _request_user_input_response(
        runtime,
        [
            {
                "id": _TASKBOOK_SCOPE_ID,
                "header": "Scope",
                "question": "How should the taskbook scope be adjusted?",
                "options": [
                    {
                        "label": "Keep current scope",
                        "description": "Leave the current scope unchanged.",
                    },
                    {
                        "label": "Tighten scope",
                        "description": "Reduce risk and stay closer to owned files.",
                    },
                    {
                        "label": "Expand scope",
                        "description": "Allow adjacent supporting cleanup when needed.",
                    },
                ],
            },
            {
                "id": _TASKBOOK_WORKSPACE_ID,
                "header": "Execution",
                "question": "How should code-changing work be executed?",
                "options": [
                    {
                        "label": "Keep current execution guard",
                        "description": "Preserve the current execution plan.",
                    },
                    {
                        "label": "Require approval before live workspace writes",
                        "description": "Keep review gates before live workspace changes.",
                    },
                    {
                        "label": "Disallow background code changes",
                        "description": "Avoid background code-changing execution paths.",
                    },
                    {
                        "label": "Prefer local execution only",
                        "description": "Keep all cards on the local runtime path.",
                    },
                ],
            },
            {
                "id": _TASKBOOK_PARALLELISM_ID,
                "header": "Parallelism",
                "question": "What parallelism cap should this run prefer?",
                "options": [
                    {
                        "label": "Keep current parallelism",
                        "description": "Leave the scheduler parallelism unchanged.",
                    },
                    {"label": "1 parallel slot", "description": "Favor one-at-a-time execution."},
                    {"label": "2 parallel slots", "description": "Allow limited parallel work."},
                    {"label": "4 parallel slots", "description": "Allow broader parallel work."},
                    {"label": "6 parallel slots", "description": "Allow aggressive parallel work."},
                ],
            },
        ],
    )
    if not structured_response:
        return None

    extra_response = _request_user_input_response(
        runtime,
        [
            {
                "id": _TASKBOOK_EXTRA_ID,
                "header": "Extra",
                "question": "Any additional requirement for this taskbook revision?",
                "options": [
                    {
                        "label": "No extra requirements",
                        "description": "Proceed without additional notes.",
                    },
                ],
            }
        ],
    )
    if not extra_response:
        return None

    return {
        _TASKBOOK_SCOPE_ID: _planning_scope_update(
            _single_answer(structured_response, _TASKBOOK_SCOPE_ID)
        ),
        _TASKBOOK_WORKSPACE_ID: _planning_workspace_update(
            _single_answer(structured_response, _TASKBOOK_WORKSPACE_ID)
        ),
        _TASKBOOK_PARALLELISM_ID: _planning_parallelism_update(
            _single_answer(structured_response, _TASKBOOK_PARALLELISM_ID)
        ),
        _TASKBOOK_EXTRA_ID: _planning_extra_update(
            _single_answer(extra_response, _TASKBOOK_EXTRA_ID)
        ),
    }


_planning_scope_update = _helpers._planning_scope_update
_planning_workspace_update = _helpers._planning_workspace_update
_planning_parallelism_update = _helpers._planning_parallelism_update
_planning_extra_update = _helpers._planning_extra_update
_merge_planning_adjustments = _helpers._merge_planning_adjustments


def _orchestration_action_questions(
    preview: dict[str, Any], *, full_view: bool
) -> list[dict[str, Any]]:
    return _helpers._orchestration_action_questions(
        preview,
        full_view=full_view,
        taskbook_action_id=_TASKBOOK_ACTION_ID,
        taskbook_action_confirm=_TASKBOOK_ACTION_CONFIRM,
        taskbook_action_adjust=_TASKBOOK_ACTION_ADJUST,
        taskbook_action_view=_TASKBOOK_ACTION_VIEW,
        taskbook_action_back=_TASKBOOK_ACTION_BACK,
        taskbook_action_cancel=_TASKBOOK_ACTION_CANCEL,
    )
