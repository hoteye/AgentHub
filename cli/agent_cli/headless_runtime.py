from __future__ import annotations

import argparse
from typing import Any, Callable, TextIO

from cli.agent_cli.models import PromptResponse, ToolEvent


def validate_headless_args(args: argparse.Namespace) -> str | None:
    resume_flags = (
        int(bool(str(getattr(args, "resume", "") or "").strip()))
        + int(bool(str(getattr(args, "resume_path", "") or "").strip()))
        + int(bool(getattr(args, "resume_last", False)))
    )
    if resume_flags > 1:
        return "choose only one of --resume, --resume-path, or --resume-last"
    if args.json and args.jsonl:
        return "--json cannot be combined with --jsonl"
    if args.provider_status and args.prompt is not None:
        return "--provider-status cannot be combined with --prompt"
    if args.prompt is not None and args.stdin:
        return "--prompt cannot be combined with --stdin"
    if args.serve and args.prompt is not None:
        return "--serve cannot be combined with --prompt"
    if args.serve and args.provider_status:
        return "--serve cannot be combined with --provider-status"
    if args.serve and args.stdin:
        return "--serve cannot be combined with --stdin"
    if args.serve and args.json:
        return "--serve cannot be combined with --json"
    if args.serve and args.jsonl:
        return "--serve cannot be combined with --jsonl"
    return None


def has_piped_input(stream: TextIO) -> bool:
    isatty = getattr(stream, "isatty", None)
    if not callable(isatty):
        return False
    try:
        return not bool(isatty())
    except Exception:
        return False


def resolve_prompt(
    args: argparse.Namespace,
    input_stream: TextIO,
    *,
    has_piped_input_fn: Callable[[TextIO], bool],
) -> str | None:
    if args.provider_status:
        return "/provider verbose"
    if args.prompt is not None:
        return args.prompt
    if args.stdin:
        return input_stream.read()
    if has_piped_input_fn(input_stream):
        return input_stream.read()
    return None


def render_text_output(
    response: PromptResponse,
    *,
    response_items_to_text_fn: Callable[[list[Any]], str],
    tool_result_fallback_text_fn: Callable[[list[ToolEvent]], str],
) -> str:
    if response.response_items:
        rendered = response_items_to_text_fn(list(response.response_items or [])).strip()
        if rendered:
            return rendered
    commentary_text = str(response.commentary_text or "").strip()
    assistant_text = str(response.assistant_text or "").strip()
    if commentary_text and assistant_text:
        return commentary_text + "\n\n" + assistant_text
    if commentary_text:
        return commentary_text
    if assistant_text:
        return assistant_text
    if response.tool_events:
        fallback_text = tool_result_fallback_text_fn(list(response.tool_events or []))
        if fallback_text:
            return fallback_text
        return str(response.tool_events[-1].summary or "").strip()
    return ""


def _response_uses_codex_noninteractive_exit_semantics(response: PromptResponse) -> bool:
    diagnostics = dict(getattr(response, "protocol_diagnostics", {}) or {})
    headless_contract = dict(diagnostics.get("headless_contract") or {})
    return bool(headless_contract.get("codex_noninteractive"))


def _response_has_completed_answer(response: PromptResponse) -> bool:
    if str(getattr(response, "assistant_text", "") or "").strip():
        return True
    if str(getattr(response, "commentary_text", "") or "").strip():
        return True
    return bool(list(getattr(response, "response_items", []) or []))


def _is_pending_approval_event(event: ToolEvent) -> bool:
    return str(getattr(event, "name", "") or "").strip().lower().endswith("_approval_requested")


def _response_terminal_state(response: PromptResponse) -> str:
    status = dict(getattr(response, "status", {}) or {})
    return str(status.get("terminal_state") or "").strip().lower()


def exit_code_for_response(
    response: PromptResponse,
    *,
    tool_event_is_soft_failure_fn: Callable[[ToolEvent], bool],
) -> int:
    if _response_terminal_state(response) == "failed":
        return 2
    if not response.tool_events:
        return 0
    last_event = response.tool_events[-1]
    if last_event.ok or tool_event_is_soft_failure_fn(last_event):
        return 0
    if (
        _response_uses_codex_noninteractive_exit_semantics(response)
        and not _is_pending_approval_event(last_event)
        and _response_has_completed_answer(response)
    ):
        return 0
    return 2


def requires_persistent_runtime(
    *,
    persistent: bool,
    resume_thread_id: str | None = None,
    resume_rollout_path: str | None = None,
    resume_last: bool = False,
    has_explicit_resume_request_fn: Callable[..., bool],
) -> bool:
    explicit_resume = has_explicit_resume_request_fn(
        thread_id=resume_thread_id,
        rollout_path=resume_rollout_path,
        resume_last=resume_last,
    )
    return bool(persistent or explicit_resume)
