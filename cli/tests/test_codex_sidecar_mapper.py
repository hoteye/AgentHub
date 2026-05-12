from __future__ import annotations

from cli.agent_cli.runtime_kernels.codex_sidecar.mapper import (
    CodexSidecarTurnEventMapper,
    map_thread_item,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.protocol import JsonRpcNotification


def _notification(method: str, params: dict[str, object]) -> JsonRpcNotification:
    return JsonRpcNotification(
        method=method,
        params=params,
        raw={"method": method, "params": params},
    )


def test_agent_message_delta_accumulates_canonical_updates() -> None:
    mapper = CodexSidecarTurnEventMapper()

    first = mapper.map_notification(
        _notification(
            "item/agentMessage/delta",
            {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "itemId": "msg-1",
                "delta": "hel",
            },
        )
    )
    second = mapper.map_notification(
        _notification(
            "item/agentMessage/delta",
            {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "itemId": "msg-1",
                "delta": "lo",
            },
        )
    )

    assert first == [
        {
            "type": "item.updated",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "item": {"id": "msg-1", "type": "agent_message", "text": "hel"},
        }
    ]
    assert second[-1]["item"]["text"] == "hello"


def test_reasoning_summary_delta_accumulates_text() -> None:
    mapper = CodexSidecarTurnEventMapper()

    mapper.map_notification(
        _notification(
            "item/reasoning/summaryTextDelta",
            {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "itemId": "reasoning-1",
                "summaryIndex": 0,
                "delta": "先",
            },
        )
    )
    events = mapper.map_notification(
        _notification(
            "item/reasoning/summaryTextDelta",
            {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "itemId": "reasoning-1",
                "summaryIndex": 0,
                "delta": "检查",
            },
        )
    )

    assert events[-1]["item"] == {
        "id": "reasoning-1",
        "type": "reasoning",
        "text": "先检查",
    }


def test_command_execution_output_delta_projects_canonical_item() -> None:
    mapper = CodexSidecarTurnEventMapper()
    mapper.map_notification(
        _notification(
            "item/started",
            {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "item": {
                    "type": "commandExecution",
                    "id": "cmd-1",
                    "command": "printf ok",
                    "cwd": "/tmp",
                    "status": "inProgress",
                    "commandActions": [],
                },
            },
        )
    )

    events = mapper.map_notification(
        _notification(
            "item/commandExecution/outputDelta",
            {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "itemId": "cmd-1",
                "delta": "ok\n",
            },
        )
    )

    assert events == [
        {
            "type": "item.updated",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "item": {
                "id": "cmd-1",
                "type": "command_execution",
                "command": "printf ok",
                "cwd": "/tmp",
                "status": "in_progress",
                "command_actions": [],
                "aggregated_output": "ok\n",
            },
        }
    ]


def test_usage_notification_is_attached_to_turn_completed() -> None:
    mapper = CodexSidecarTurnEventMapper()
    mapper.map_notification(
        _notification(
            "thread/tokenUsage/updated",
            {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "tokenUsage": {
                    "last": {
                        "totalTokens": 7,
                        "inputTokens": 3,
                        "cachedInputTokens": 1,
                        "outputTokens": 4,
                        "reasoningOutputTokens": 2,
                    },
                    "modelContextWindow": 128000,
                },
            },
        )
    )

    events = mapper.map_notification(
        _notification(
            "turn/completed",
            {
                "threadId": "thread-1",
                "turn": {"id": "turn-1", "status": "completed", "items": []},
            },
        )
    )

    assert events[-1]["type"] == "turn.completed"
    assert events[-1]["usage"] == {
        "input_tokens": 3,
        "cached_input_tokens": 1,
        "output_tokens": 4,
        "reasoning_output_tokens": 2,
        "total_tokens": 7,
    }
    assert mapper.status_updates["model_context_window"] == 128000


def test_failed_turn_projects_turn_failed() -> None:
    mapper = CodexSidecarTurnEventMapper()

    events = mapper.map_notification(
        _notification(
            "turn/completed",
            {
                "threadId": "thread-1",
                "turn": {
                    "id": "turn-1",
                    "status": "failed",
                    "items": [],
                    "error": {"message": "boom"},
                },
            },
        )
    )

    assert events == [
        {
            "type": "turn.failed",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "error": {"message": "boom"},
        }
    ]
    assert mapper.terminal_seen is True


def test_interrupted_turn_projects_turn_interrupted() -> None:
    mapper = CodexSidecarTurnEventMapper()

    events = mapper.map_notification(
        _notification(
            "turn/completed",
            {
                "threadId": "thread-1",
                "turn": {
                    "id": "turn-1",
                    "status": "interrupted",
                    "items": [],
                    "error": None,
                },
            },
        )
    )

    assert events == [
        {
            "type": "turn.interrupted",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "error": {"message": "interrupted"},
        }
    ]
    assert mapper.terminal_seen is True


def test_map_thread_item_supports_core_codex_item_types() -> None:
    assert map_thread_item(
        {"type": "agentMessage", "id": "msg-1", "text": "done", "phase": "final_answer"}
    ) == {
        "id": "msg-1",
        "type": "agent_message",
        "text": "done",
        "phase": "final_answer",
    }
    assert map_thread_item(
        {"type": "reasoning", "id": "r1", "summary": ["read"], "content": ["answer"]}
    ) == {
        "id": "r1",
        "type": "reasoning",
        "text": "read\n\nanswer",
        "summary": ["read"],
        "content": ["answer"],
    }
    assert (
        map_thread_item(
            {
                "type": "mcpToolCall",
                "id": "tool-1",
                "server": "local",
                "tool": "demo",
                "status": "completed",
                "arguments": {"x": 1},
                "result": {"content": [{"type": "text", "text": "ok"}]},
                "error": None,
            }
        )["type"]
        == "mcp_tool_call"
    )
    assert map_thread_item({"type": "webSearch", "id": "ws-1", "query": "q"}) == {
        "id": "ws-1",
        "type": "web_search_call",
        "query": "q",
        "action": None,
        "status": "completed",
        "search_phase": "search_results_received",
    }
