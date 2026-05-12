from __future__ import annotations

from cli.agent_cli.models import ActivityEvent, PromptResponse, activity_code, activity_dedupe_key
from cli.agent_cli.ui import (
    transcript_browser_runtime,
    transcript_formatting_activity_runtime,
    transcript_formatting_helpers_runtime,
    transcript_formatting_runtime_helpers,
)


def format_transcript_block(
    content: str, *, first_prefix: str, continuation_prefix: str
) -> list[str]:
    return transcript_formatting_helpers_runtime.format_transcript_block_lines(
        content,
        first_prefix=first_prefix,
        continuation_prefix=continuation_prefix,
    )


format_plan_steps = transcript_formatting_activity_runtime.format_plan_steps


format_activity_detail_lines = transcript_formatting_helpers_runtime.format_activity_detail_lines


def format_web_activity_lines(
    event: ActivityEvent, *, max_search_results: int | None = None
) -> list[str]:
    if event.kind == "browser":
        return format_browser_activity_lines(event)
    summary = format_activity_summary(event)
    raw = str(event.detail or "").strip()
    if not summary:
        return format_activity_detail_lines(raw) if raw else []
    if event.status == "error" or not raw:
        lines = [summary]
        lines.extend(format_activity_detail_lines(raw) if raw else [])
        return lines
    code = activity_code(event)
    if code == "web.search":
        return _format_web_search_lines(event, summary, raw, max_results=max_search_results)
    if code in {"web.fetch", "web.open", "web.click"}:
        return _format_web_page_lines(event, summary, raw)
    if code == "web.find":
        return _format_web_find_lines(event, summary, raw)
    lines = [summary]
    lines.extend(format_activity_detail_lines(raw))
    return lines


def format_file_activity_lines(event: ActivityEvent) -> list[str]:
    summary = format_activity_summary(event)
    raw = str(event.detail or "").strip()
    if not summary:
        return format_activity_detail_lines(raw) if raw else []
    if event.status == "error" or not raw:
        lines = [summary]
        lines.extend(format_activity_detail_lines(raw) if raw else [])
        return lines
    code = activity_code(event)
    if code in {"file.list", "dir.list"}:
        return _format_file_list_lines(event, summary, raw)
    if code in {"file.search", "dir.search"}:
        return _format_file_search_lines(event, summary, raw)
    if code == "file.read":
        return _format_file_read_lines(event, summary, raw)
    if code == "image.view":
        return _format_view_image_lines(event, summary, raw)
    lines = [summary]
    lines.extend(format_activity_detail_lines(raw))
    return lines


def format_exploration_activity_lines(event: ActivityEvent) -> list[str] | None:
    if event.status == "error":
        return None
    detail = exploration_detail_item(event)
    return None if detail is None else render_exploration_entry_lines([detail], status=event.status)


def format_patch_activity_lines(event: ActivityEvent) -> list[str]:
    summary = format_activity_summary(event)
    raw = str(event.detail or "").strip()
    if not summary:
        return format_activity_detail_lines(raw) if raw else []
    if event.status == "error" or not raw:
        lines = [summary]
        lines.extend(format_activity_detail_lines(raw) if raw else [])
        return lines
    code = activity_code(event)
    if code == "patch.apply":
        return _format_apply_patch_lines(event, summary, raw)
    if code == "approval.request.patch":
        return _format_patch_approval_lines(event, summary, raw)
    if code == "approval.request.shell":
        return _format_shell_approval_lines(event, summary, raw)
    if code == "approval.request.action":
        return _format_action_approval_lines(event, summary, raw)
    if code == "approval.list":
        return _format_approval_list_lines(event, summary, raw)
    if code.startswith("approval.decision"):
        return _format_approval_decision_lines(event, summary, raw)
    lines = [summary]
    lines.extend(format_activity_detail_lines(raw))
    return lines


def _format_file_list_lines(event: ActivityEvent, summary: str, raw: str) -> list[str]:
    return transcript_formatting_runtime_helpers.format_file_list_lines(
        event,
        summary,
        raw,
        activity_param_text_fn=_activity_param_text,
    )


def _format_file_search_lines(event: ActivityEvent, summary: str, raw: str) -> list[str]:
    return transcript_formatting_runtime_helpers.format_file_search_lines(
        event,
        summary,
        raw,
        activity_param_text_fn=_activity_param_text,
    )


def _format_file_read_lines(event: ActivityEvent, summary: str, raw: str) -> list[str]:
    return transcript_formatting_runtime_helpers.format_file_read_lines(
        event,
        summary,
        raw,
        read_subject_for_event_fn=_read_subject_for_event,
    )


def _format_view_image_lines(event: ActivityEvent, summary: str, raw: str) -> list[str]:
    return transcript_formatting_runtime_helpers.format_view_image_lines(
        event,
        summary,
        raw,
        activity_param_text_fn=_activity_param_text,
    )


_compact_web_domains = transcript_formatting_helpers_runtime.compact_web_domains


def _format_web_search_lines(
    event: ActivityEvent, summary: str, raw: str, *, max_results: int | None = None
) -> list[str]:
    return transcript_formatting_runtime_helpers.format_web_search_lines(
        event,
        summary,
        raw,
        max_results=max_results,
        activity_param_text_fn=_activity_param_text,
        format_ranked_result_fn=_format_ranked_web_result,
    )


_format_ranked_web_result = transcript_formatting_helpers_runtime.format_ranked_web_result


def _format_web_page_lines(event: ActivityEvent, summary: str, raw: str) -> list[str]:
    return transcript_formatting_runtime_helpers.format_web_page_lines(
        event,
        summary,
        raw,
        activity_param_text_fn=_activity_param_text,
    )


def _format_web_find_lines(event: ActivityEvent, summary: str, raw: str) -> list[str]:
    return transcript_formatting_runtime_helpers.format_web_find_lines(
        event,
        summary,
        raw,
        activity_param_only_text_fn=_activity_param_only_text,
    )


_browser_detail_segments = transcript_browser_runtime.browser_detail_segments


_browser_detail_map = transcript_browser_runtime.browser_detail_map


_append_browser_segments = transcript_browser_runtime.append_browser_segments


_take_browser_values = transcript_browser_runtime.take_browser_values


_format_browser_snapshot_lines = transcript_browser_runtime.format_browser_snapshot_lines


_format_browser_artifact_lines = transcript_browser_runtime.format_browser_artifact_lines


_format_browser_console_lines = transcript_browser_runtime.format_browser_console_lines


_format_browser_error_lines = transcript_browser_runtime.format_browser_error_lines


_format_browser_request_lines = transcript_browser_runtime.format_browser_request_lines


def format_browser_activity_lines(event: ActivityEvent) -> list[str]:
    summary = format_activity_summary(event)
    raw = str(event.detail or "").strip()
    if not summary:
        return format_activity_detail_lines(raw) if raw else []
    if not raw:
        return [summary]
    code = activity_code(event)
    return transcript_browser_runtime.format_browser_activity_lines(
        summary=summary,
        raw=raw,
        code=code,
    )


def _format_apply_patch_lines(event: ActivityEvent, summary: str, raw: str) -> list[str]:
    return transcript_formatting_runtime_helpers.format_apply_patch_lines(
        event,
        summary,
        raw,
        activity_param_text_fn=_activity_param_text,
    )


def _format_patch_approval_lines(event: ActivityEvent, summary: str, raw: str) -> list[str]:
    return transcript_formatting_runtime_helpers.format_patch_approval_lines(
        event,
        summary,
        raw,
        activity_param_text_fn=_activity_param_text,
    )


def _format_shell_approval_lines(event: ActivityEvent, summary: str, raw: str) -> list[str]:
    return transcript_formatting_runtime_helpers.format_shell_approval_lines(
        event,
        summary,
        raw,
        activity_param_text_fn=_activity_param_text,
    )


def _format_action_approval_lines(event: ActivityEvent, summary: str, raw: str) -> list[str]:
    return transcript_formatting_runtime_helpers.format_action_approval_lines(
        event,
        summary,
        raw,
        activity_param_text_fn=_activity_param_text,
    )


def _format_approval_list_lines(event: ActivityEvent, summary: str, raw: str) -> list[str]:
    return transcript_formatting_runtime_helpers.format_approval_list_lines(
        event,
        summary,
        raw,
        activity_param_text_fn=_activity_param_text,
    )


def _format_approval_decision_lines(event: ActivityEvent, summary: str, raw: str) -> list[str]:
    return transcript_formatting_runtime_helpers.format_approval_decision_lines(
        event,
        summary,
        raw,
        activity_param_text_fn=_activity_param_text,
    )


strip_activity_prefix = transcript_formatting_helpers_runtime.strip_activity_prefix


_detail_lookup = transcript_formatting_helpers_runtime.detail_lookup


def _activity_params(event: ActivityEvent) -> dict[str, object]:
    return dict(getattr(event, "params", None) or {})


def _activity_param_text(event: ActivityEvent, *keys: str) -> str:
    return transcript_formatting_helpers_runtime.activity_param_text(
        _activity_params(event), str(event.detail or ""), *keys
    )


def _activity_param_only_text(event: ActivityEvent, *keys: str) -> str:
    return transcript_formatting_helpers_runtime.activity_param_only_text(
        _activity_params(event), *keys
    )


_search_subject = transcript_formatting_helpers_runtime.search_subject_from_detail


def _search_subject_for_event(event: ActivityEvent) -> str:
    return transcript_formatting_helpers_runtime.search_subject(
        _activity_param_text(event, "query", "pattern"),
        _activity_param_text(event, "path", "dir_path"),
    )


_read_subject = transcript_formatting_helpers_runtime.read_subject


def _read_subject_for_event(event: ActivityEvent) -> str:
    detail_subject = _activity_param_text(event, "file_path", "path")
    return detail_subject or _read_subject(str(event.detail or ""))


def exploration_detail_item(event: ActivityEvent) -> tuple[str, str] | None:
    return transcript_formatting_activity_runtime.exploration_detail_item(
        event,
        activity_code_fn=activity_code,
        activity_param_text_fn=_activity_param_text,
        search_subject_for_event_fn=_search_subject_for_event,
        search_subject_fn=_search_subject,
        read_subject_for_event_fn=_read_subject_for_event,
    )


format_exploration_detail_item = (
    transcript_formatting_helpers_runtime.format_exploration_detail_item
)


parse_exploration_detail_item = transcript_formatting_helpers_runtime.parse_exploration_detail_item


merge_exploration_detail_items = (
    transcript_formatting_helpers_runtime.merge_exploration_detail_items
)


render_exploration_entry_lines = (
    transcript_formatting_helpers_runtime.render_exploration_entry_lines
)


def format_activity_summary(event: ActivityEvent) -> str:
    return transcript_formatting_activity_runtime.format_activity_summary(
        event,
        activity_code_fn=activity_code,
        activity_param_text_fn=_activity_param_text,
        strip_activity_prefix_fn=strip_activity_prefix,
    )


activity_signature = activity_dedupe_key


def should_render_assistant_reply(response: PromptResponse) -> bool:
    text = str(response.assistant_text or "").strip()
    if not text:
        return False
    if _response_has_approval_request(
        response
    ) and transcript_formatting_helpers_runtime.is_approval_request_fallback_text(text):
        return False
    if any(
        str(getattr(event, "name", "") or "").strip() == "app_exit_requested"
        for event in list(response.tool_events or [])
    ):
        return False
    if response.handled_as_command and [event.name for event in response.tool_events] == ["shell"]:
        return any(bool((event.payload or {}).get("interrupted")) for event in response.tool_events)
    return True


def _response_has_approval_request(response: PromptResponse) -> bool:
    request_names = {
        "patch_approval_requested",
        "shell_approval_requested",
        "background_teammate_approval_requested",
    }
    return any(
        str(getattr(event, "name", "") or "").strip() in request_names
        for event in list(response.tool_events or [])
    )
