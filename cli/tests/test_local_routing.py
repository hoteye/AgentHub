from __future__ import annotations

import shlex

from cli.agent_cli.agent_plan_runtime import live_web_fallback_intent
from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime_core.local_routing import extract_first_url


def test_extract_first_url_stops_at_cjk_sentence_suffix() -> None:
    text = "请阅读这个公开页面：https://platform.openai.com/docs/models。如果用户已经给出具体 URL，优先直接读取。"

    assert extract_first_url(text) == "https://platform.openai.com/docs/models"


def test_extract_first_url_preserves_query_before_cjk_punctuation() -> None:
    text = "看这个 https://example.com/docs?a=1&b=2。然后总结。"

    assert extract_first_url(text) == "https://example.com/docs?a=1&b=2"


def test_live_web_fallback_intent_uses_clean_explicit_url_for_web_fetch() -> None:
    commands: list[str] = []

    def tool_executor(command: str):
        commands.append(command)
        return (
            "fetched",
            [
                ToolEvent(
                    name="web_fetch",
                    ok=True,
                    summary="web page loaded",
                    payload={"ok": True, "url": "https://platform.openai.com/docs/models"},
                )
            ],
        )

    intent = live_web_fallback_intent(
        "请阅读这个公开页面并总结其中与 GPT-5.4 相关的关键信息：https://platform.openai.com/docs/models。如果用户已经给出具体 URL，优先直接读取而不是先泛搜。",
        tool_executor=tool_executor,
        summarize_live_web_result=lambda query, event: f"{query}:{event.summary}",
    )

    assert intent is not None
    assert intent.commentary_text == "这是实时信息查询，我先读取网页。"
    assert len(commands) == 1
    assert shlex.split(commands[0]) == ["/web_fetch", "https://platform.openai.com/docs/models"]
    assert [event.name for event in intent.tool_events] == ["web_fetch"]
