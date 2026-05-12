from __future__ import annotations

from re import Pattern

from cli.agent_cli.ui import top_title_summary_runtime


def normalize_thread_title_candidate(value: str, *, default_thread_name_re: Pattern[str]) -> str:
    normalized = top_title_summary_runtime.normalized_prompt_text(value)
    if not normalized:
        return ""
    if default_thread_name_re.match(normalized):
        return ""
    if top_title_summary_runtime.is_slash_command_prompt(normalized):
        return ""
    return normalized


def can_toggle_shortcut_overlay(*, screen_mode: str, prompt_text: str) -> bool:
    normalized_screen_mode = str(screen_mode or "prompt").strip().lower()
    return normalized_screen_mode == "prompt" and not bool(prompt_text)
