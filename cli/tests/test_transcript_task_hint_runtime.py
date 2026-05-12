from __future__ import annotations

from cli.agent_cli.ui.transcript_task_hint_runtime import resolve_transcript_task_hint


def test_resolve_transcript_task_hint_prefers_meaningful_thread_name() -> None:
    assert (
        resolve_transcript_task_hint("定位登录超时根因", "标题栏摘要", "AgentHub")
        == "定位登录超时根因"
    )


def test_resolve_transcript_task_hint_ignores_placeholder_thread_name() -> None:
    assert (
        resolve_transcript_task_hint("Thread 2026-04-10 10:00:00", "标题栏摘要", "AgentHub")
        == "标题栏摘要"
    )


def test_resolve_transcript_task_hint_falls_back_to_base_title() -> None:
    assert resolve_transcript_task_hint("", "", "AgentHub") == "AgentHub"
