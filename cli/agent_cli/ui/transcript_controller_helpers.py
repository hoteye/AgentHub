from __future__ import annotations

from cli.agent_cli.models import (
    PromptResponse,
    ResponseInputItem,
    response_item_text,
)
from cli.agent_cli.ui import (
    live_turn_controller_projection_helpers as live_turn_projection_helpers,
)
from cli.agent_cli.ui.transcript_controller_helpers_operator_projection import (  # noqa: F401
    _TRANSCRIPT_OPERATOR_COMMANDS,
    _apply_operator_transcript_projection,
    _operator_background_task_detail_lines,
    _operator_pipe_segments,
    _operator_segment_map,
    _operator_transcript_detail_lines,
    _operator_transcript_text,
    _operator_workflow_detail_lines,
    _project_operator_response_items,
    _project_operator_turn_events,
    _single_operator_detail_line,
)

_REQUEST_USER_INPUT_TRANSCRIPT_DEFAULTS = {
    "transcript.request_user_input.cancelled": "User input request was cancelled.",
    "transcript.request_user_input.answer": "User input {question_id} -> {answers}",
}


def _restore_transcript_from_runtime_history(controller) -> None:
    turns = [
        dict(item)
        for item in list(getattr(getattr(controller, "runtime", None), "history_turns", []) or [])
        if isinstance(item, dict)
    ]
    if not turns or getattr(controller, "_transcript_entries", None):
        return
    restored_prompt_count = 0
    for turn in turns:
        if str(turn.get("user_text") or "").strip():
            restored_prompt_count += 1
        _restore_transcript_turn(controller, turn)
    controller._restored_transcript_from_history = True
    if restored_prompt_count > int(getattr(controller, "prompt_count", 0) or 0):
        controller.prompt_count = restored_prompt_count


def _restore_transcript_turn(controller, turn: dict[str, object]) -> None:
    controller._begin_activity_capture()
    user_text = str(turn.get("user_text") or "").strip()
    assistant_text = (
        str(turn.get("command_display_text") or "").strip()
        if bool(turn.get("handled_as_command"))
        else ""
    ) or str(turn.get("assistant_text") or "").strip()
    if user_text:
        controller._write_user_prompt(user_text)
    if assistant_text and not _turn_has_app_exit_request(turn):
        controller._write_assistant_reply(assistant_text)


def render_response(controller, response: PromptResponse) -> None:
    if _response_has_app_exit_request(response):
        _update_response_status(controller, response)
        return
    _apply_command_display_text(response)
    controller._apply_operator_transcript_projection(response)
    canonical_turn_events = controller._prompt_response_turn_events(response)
    if not list(getattr(response, "turn_events", []) or []) and list(
        getattr(response, "response_items", []) or []
    ):
        canonical_turn_events = [
            event
            for event in canonical_turn_events
            if not (
                isinstance(event, dict)
                and isinstance(event.get("item"), dict)
                and str(event["item"].get("type") or "").strip() == "reasoning"
            )
        ]
    if canonical_turn_events:
        controller._render_canonical_turn_event_backfill(canonical_turn_events)
    else:
        for activity in list(getattr(response, "activity_events", []) or []):
            signature = controller._activity_signature(activity)
            if signature in controller._live_activity_signatures:
                continue
            controller._live_activity_signatures.add(signature)
            controller._note_work_activity_from_activity(activity)
            controller._write_activity_event(activity)
        if response.response_items:
            for item in list(response.response_items or []):
                item_type = str(getattr(item, "item_type", "") or "").strip().lower()
                content = getattr(item, "content", None)
                content_types = (
                    {
                        str(entry.get("type") or "").strip().lower()
                        for entry in list(content or [])
                        if isinstance(entry, dict)
                    }
                    if isinstance(content, list)
                    else set()
                )
                is_reasoning = item_type == "reasoning" or "reasoning" in content_types
                text = response_item_text(item)
                if not text:
                    continue
                if text.strip() == str(
                    response.assistant_text or ""
                ).strip() and not controller._should_render_assistant_reply(response):
                    continue
                if is_reasoning:
                    continue
                if text in controller._live_streamed_texts:
                    continue
                phase = str(item.extra.get("phase") or "").strip().lower()
                if phase == "commentary":
                    controller._write_commentary_reply(text)
                else:
                    controller._write_assistant_reply(text)
        else:
            if str(response.commentary_text or "").strip():
                if response.commentary_text not in controller._live_streamed_texts:
                    controller._write_commentary_reply(response.commentary_text)
            if controller._should_render_assistant_reply(response):
                if str(response.assistant_text or "") not in controller._live_streamed_texts:
                    controller._write_assistant_reply(response.assistant_text)
    _update_response_status(controller, response)


def _update_response_status(controller, response: PromptResponse) -> None:
    _write_request_user_input_summary(controller, response)
    status = controller._status_from_response(response)
    status["prompt_count"] = str(controller.prompt_count)
    controller._update_status(status)
    sync_top_title_from_thread_name = getattr(controller, "_sync_top_title_from_thread_name", None)
    if callable(sync_top_title_from_thread_name):
        try:
            sync_top_title_from_thread_name(refresh_from_store=True)
        except Exception:
            pass
    controller._focus_input()


def _response_has_app_exit_request(response: PromptResponse) -> bool:
    for event in list(getattr(response, "tool_events", []) or []):
        if str(getattr(event, "name", "") or "").strip() == "app_exit_requested":
            return True
    return False


def _apply_command_display_text(response: PromptResponse) -> None:
    display_text = str(getattr(response, "command_display_text", "") or "").strip()
    if not display_text or not bool(getattr(response, "handled_as_command", False)):
        return
    response.response_items = [
        ResponseInputItem(
            item_type="message",
            role="assistant",
            content=[{"type": "output_text", "text": display_text}],
            content_present=True,
            extra={"phase": "final_answer"},
        )
    ]
    response.turn_events = []


def _turn_has_app_exit_request(turn: dict[str, object]) -> bool:
    for raw_event in list(turn.get("tool_events") or []):
        if (
            isinstance(raw_event, dict)
            and str(raw_event.get("name") or "").strip() == "app_exit_requested"
        ):
            return True
    for raw_event in list(turn.get("turn_events") or []):
        if not isinstance(raw_event, dict):
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("tool") or item.get("name") or "").strip() == "app_exit_requested":
            return True
    return False


def _write_request_user_input_summary(controller, response: PromptResponse) -> None:
    tool_events = list(getattr(response, "tool_events", []) or [])
    for event in tool_events:
        if str(getattr(event, "name", "") or "").strip() != "request_user_input":
            continue
        payload = dict(getattr(event, "payload", {}) or {})
        raw_response = payload.get("response")
        if not isinstance(raw_response, dict):
            controller._write_system_notice(
                _request_user_input_transcript_text(
                    controller,
                    "transcript.request_user_input.cancelled",
                )
            )
            continue
        answer_map = dict(raw_response.get("answers") or {})
        if not answer_map:
            controller._write_system_notice(
                _request_user_input_transcript_text(
                    controller,
                    "transcript.request_user_input.cancelled",
                )
            )
            continue
        for question_id, answer_payload in answer_map.items():
            values = _request_user_input_answer_values(answer_payload)
            if not values:
                continue
            controller._write_system_notice(
                _request_user_input_transcript_text(
                    controller,
                    "transcript.request_user_input.answer",
                    question_id=str(question_id),
                    answers=", ".join(values),
                )
            )


def _request_user_input_transcript_text(controller, key: str, **kwargs: object) -> str:
    template = str(_REQUEST_USER_INPUT_TRANSCRIPT_DEFAULTS.get(key) or "").strip()
    explicit_language = getattr(controller, "_presentation_cli_language", None)
    if explicit_language is None:
        return template.format(**kwargs) if kwargs else template
    translator = getattr(controller, "_t", None)
    if callable(translator):
        try:
            value = str(translator(key, **kwargs) or "").strip()
            if value:
                return value
        except Exception:
            pass
    return template.format(**kwargs) if kwargs else template


def _request_user_input_answer_values(value: object) -> list[str]:
    if isinstance(value, dict):
        answers = value.get("answers")
        if isinstance(answers, list):
            return [str(item).strip() for item in answers if str(item).strip()]
        if isinstance(answers, str):
            text = answers.strip()
            return [text] if text else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _render_canonical_turn_event_backfill(controller, events: list[dict[str, object]]) -> None:
    backfilled_counts: dict[str, int] = {}
    backfill_sequence = controller._live_turn_event_sequence
    for event in list(events or []):
        if not isinstance(event, dict):
            continue
        if controller._should_suppress_turn_event_after_interrupt(event):
            continue
        signature = controller._turn_event_backfill_signature(event)
        live_seen = controller._live_turn_backfill_counts.get(signature, 0)
        already_backfilled = backfilled_counts.get(signature, 0)
        if already_backfilled < live_seen:
            backfilled_counts[signature] = already_backfilled + 1
            continue
        event_type = str(event.get("type") or "").strip()
        if event_type in {"turn.completed", "turn.failed"}:
            controller._finalize_live_turn_items()
            backfilled_counts[signature] = already_backfilled + 1
            continue
        activity = controller._turn_event_activity(event)
        if activity is not None:
            activity_signature = controller._activity_signature(activity)
            if activity_signature in controller._live_activity_signatures:
                backfilled_counts[signature] = already_backfilled + 1
                continue
            controller._live_activity_signatures.add(activity_signature)
            controller._note_work_activity_from_activity(activity)
            controller._note_pending_approval_activity(activity)
        entry = controller._turn_event_entry(event, activity=activity)
        if entry is None:
            backfilled_counts[signature] = already_backfilled + 1
            continue
        item = event.get("item")
        if isinstance(item, dict):
            projection = live_turn_projection_helpers.project_live_turn_item(
                item=item,
                event_type=event_type,
                live_turn_event_sequence=backfill_sequence + 1,
                entry_activity_key=entry.activity_key,
            )
            if projection.tool_sequence is not None:
                controller._demote_last_agent_message_before_late_tool()
                controller._live_turn_last_tool_sequence = projection.tool_sequence
                controller._note_work_activity_from_turn_item(item)
        backfill_sequence += 1
        controller._append_transcript_entry(entry, leading_blank=not bool(entry.activity_key))
        if isinstance(item, dict) and event_type == "item.completed":
            item_type = str(item.get("type") or "").strip()
            if item_type in {
                "mcp_tool_call",
                "command_execution",
                "expert_review",
                "function_call",
                "custom_tool_call",
                "shell_call",
                "local_shell_call",
            }:
                controller._live_turn_last_tool_sequence = backfill_sequence
                controller._note_work_activity_from_turn_item(item)
            text = str(item.get("text") or "").strip()
            if text:
                controller._live_streamed_texts.add(text)
            if item_type == "agent_message":
                controller._live_turn_last_agent_message_key = entry.activity_key
                controller._live_turn_last_agent_message_sequence = backfill_sequence
        backfilled_counts[signature] = already_backfilled + 1
    controller._live_turn_event_sequence = max(
        controller._live_turn_event_sequence, backfill_sequence
    )
