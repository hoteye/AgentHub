from __future__ import annotations

from re import Pattern
from typing import Any, Callable

from cli.agent_cli import app_pure_helpers_runtime as pure_helpers
from cli.agent_cli.ui import top_title_summary_runtime
from cli.agent_cli.ui.transcript_task_hint_runtime import resolve_transcript_task_hint


def resolve_transcript_task_hint_text(
    *,
    runtime: Any,
    top_title_text: str,
    base_title: str,
) -> str:
    return resolve_transcript_task_hint(
        runtime_thread_name=str(getattr(runtime, "thread_name", "") or "").strip(),
        top_title_text=str(top_title_text or "").strip(),
        base_title=base_title,
    )


def resolve_thread_title_from_runtime(
    *,
    runtime: Any,
    refresh_from_store: bool,
    default_thread_name_re: Pattern[str],
) -> str:
    thread_name = str(getattr(runtime, "thread_name", "") or "").strip()
    if refresh_from_store:
        thread_id = str(getattr(runtime, "thread_id", "") or "").strip()
        thread_store = getattr(runtime, "thread_store", None)
        get_thread = getattr(thread_store, "get_thread", None)
        if thread_id and callable(get_thread):
            try:
                record = get_thread(thread_id)
            except Exception:
                record = None
            if isinstance(record, dict):
                latest_name = str(record.get("name") or "").strip()
                if latest_name:
                    thread_name = latest_name
                    try:
                        runtime.thread_name = latest_name
                    except Exception:
                        pass
    return pure_helpers.normalize_thread_title_candidate(
        thread_name,
        default_thread_name_re=default_thread_name_re,
    )


def top_title_text_from_prompt(
    *,
    prompt: str,
    base_title: str,
    width: int,
    crop_one_line_fn: Callable[[str, int], str],
) -> str:
    return top_title_summary_runtime.top_title_text_for_prompt(
        prompt,
        base_title=base_title,
        width=width,
        crop_one_line_fn=crop_one_line_fn,
    )
