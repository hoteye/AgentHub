#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import sys
import threading
import time
from pathlib import Path

THREADS: dict[str, dict[str, object]] = {}
ACTIVE_TURNS: dict[str, dict[str, object]] = {}
NEXT_THREAD_SERIAL = 1
WRITE_LOCK = threading.Lock()


def _write(payload: dict[str, object]) -> None:
    with WRITE_LOCK:
        sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
        sys.stdout.flush()


def _result(request_id: object, result: dict[str, object]) -> None:
    _write({"id": request_id, "result": result})


def _server_request(
    request_id: object,
    method: str,
    params: dict[str, object],
) -> dict[str, object] | None:
    _write({"id": request_id, "method": method, "params": params})
    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            message = json.loads(stripped)
        except json.JSONDecodeError:
            print(f"invalid json: {stripped}", file=sys.stderr)
            continue
        if not isinstance(message, dict):
            continue
        if message.get("id") == request_id and (
            "response" in message or "result" in message or "error" in message
        ):
            response = (
                message.get("response")
                if "response" in message
                else (
                    message.get("result")
                    if "result" in message
                    else {"error": message.get("error")}
                )
            )
            return dict(response) if isinstance(response, dict) else {}
        _handle(message)
    return None


def _error(request_id: object, message: str) -> None:
    _write({"id": request_id, "error": {"code": -32000, "message": message}})


def _state_path() -> Path | None:
    raw = str(os.environ.get("FAKE_CODEX_SIDECAR_STATE") or "").strip()
    return Path(raw) if raw else None


def _load_state() -> None:
    global NEXT_THREAD_SERIAL
    path = _state_path()
    if path is None or not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    raw_threads = payload.get("threads") if isinstance(payload, dict) else None
    if isinstance(raw_threads, dict):
        THREADS.clear()
        THREADS.update(raw_threads)
    try:
        NEXT_THREAD_SERIAL = max(1, int(payload.get("next_thread_serial")))
    except (AttributeError, TypeError, ValueError):
        NEXT_THREAD_SERIAL = 1


def _save_state() -> None:
    path = _state_path()
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "threads": THREADS,
                    "next_thread_serial": NEXT_THREAD_SERIAL,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        return


def _turn(turn_id: str, status: str = "inProgress") -> dict[str, object]:
    return {
        "id": turn_id,
        "items": [],
        "status": status,
        "error": None,
        "startedAt": 1,
        "completedAt": 2 if status != "inProgress" else None,
        "durationMs": 1000 if status != "inProgress" else None,
    }


def _turn_key(thread_id: str, turn_id: str) -> str:
    return f"{thread_id}:{turn_id}"


def _next_turn_id(thread_id: str) -> str:
    thread_state = THREADS.get(thread_id)
    turns = list(thread_state.get("turns") or []) if isinstance(thread_state, dict) else []
    return f"turn-{len(turns) + 1}"


def _next_thread_id() -> str:
    global NEXT_THREAD_SERIAL
    thread_id = f"thread-{NEXT_THREAD_SERIAL}"
    NEXT_THREAD_SERIAL += 1
    return thread_id


def _thread(
    thread_id: str,
    *,
    name: str | None = None,
    cwd: object = "",
    forked_from_id: str | None = None,
    turns: list[dict[str, object]] | None = None,
    archived: bool = False,
    git_info: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "id": thread_id,
        "name": name or "Fake Thread",
        "preview": "",
        "ephemeral": False,
        "modelProvider": "fake-provider",
        "createdAt": 1,
        "updatedAt": 2,
        "status": {"type": "idle"},
        "path": f"/tmp/fake-codex-rollouts/{thread_id}.jsonl",
        "cwd": cwd or "",
        "forkedFromId": forked_from_id,
        "archived": archived,
        "archivedAt": 3 if archived else None,
        "gitInfo": dict(git_info or {}) or None,
        "turns": list(turns or []),
    }


def _copy_dynamic_tools(raw: object) -> list[dict[str, object]]:
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _dynamic_tools_for_thread(thread_id: str) -> list[dict[str, object]]:
    state = THREADS.get(thread_id)
    if not isinstance(state, dict):
        return []
    return _copy_dynamic_tools(state.get("dynamicTools"))


def _dynamic_tool_for_request(thread_id: str, preferred_name: str) -> dict[str, object] | None:
    tools = _dynamic_tools_for_thread(thread_id)
    if not tools:
        return None
    for tool in tools:
        if str(tool.get("name") or "").strip() == preferred_name:
            return tool
    return tools[0]


def _thread_payload(thread_id: str, *, include_turns: bool = True) -> dict[str, object]:
    state = THREADS.get(thread_id)
    if not isinstance(state, dict):
        return _thread(thread_id)
    raw_thread = dict(state.get("thread") or {})
    raw_thread["name"] = raw_thread.get("name") or "Fake Thread"
    raw_thread["modelProvider"] = state.get("modelProvider") or "fake-provider"
    raw_thread["cwd"] = state.get("cwd") or raw_thread.get("cwd") or ""
    raw_thread["archived"] = bool(state.get("archived"))
    raw_thread["archivedAt"] = 3 if bool(state.get("archived")) else None
    raw_thread["gitInfo"] = state.get("gitInfo") if isinstance(state.get("gitInfo"), dict) else None
    raw_thread["turns"] = list(state.get("turns") or []) if include_turns else []
    return raw_thread


def _thread_result(
    *,
    thread_id: str,
    params: dict[str, object],
    name: str | None = None,
    forked_from_id: str | None = None,
    turns: list[dict[str, object]] | None = None,
    dynamic_tools: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    stored_dynamic_tools = (
        [dict(item) for item in dynamic_tools]
        if dynamic_tools is not None
        else _copy_dynamic_tools(params.get("dynamicTools"))
    )
    thread = _thread(
        thread_id,
        name=name,
        cwd=params.get("cwd") or "",
        forked_from_id=forked_from_id,
        turns=turns,
    )
    THREADS[thread_id] = {
        "thread": thread,
        "turns": list(turns or []),
        "model": params.get("model") or "fake-model",
        "modelProvider": params.get("modelProvider") or "fake-provider",
        "cwd": params.get("cwd") or "",
        "archived": False,
        "gitInfo": None,
        "dynamicTools": stored_dynamic_tools,
    }
    _save_state()
    return {
        "thread": thread,
        "model": params.get("model") or "fake-model",
        "modelProvider": params.get("modelProvider") or "fake-provider",
        "cwd": params.get("cwd") or "",
        "approvalPolicy": params.get("approvalPolicy") or "",
        "sandbox": params.get("sandbox") or "",
    }


def _dynamic_tool_arguments(tool_name: str) -> dict[str, object]:
    if tool_name == "spawn_child_tab":
        return {
            "task": "Inspect README from inherited dynamic tool",
            "task_name": "dynamic_child",
            "metadata": {"run_id": "fake_dynamic_run"},
        }
    if tool_name == "send_child_tab":
        return {
            "target": "latest",
            "message": "Continue from inherited dynamic tool",
            "interrupt": False,
        }
    if tool_name == "wait_child_tasks":
        return {"targets": ["latest"], "timeout_ms": 0}
    return {}


def _dynamic_tool_response_text(response: dict[str, object] | None) -> str:
    if not isinstance(response, dict):
        return "no_response"
    status = "success" if bool(response.get("success")) else "failed"
    content_items = response.get("contentItems")
    text = ""
    if isinstance(content_items, list):
        for item in content_items:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "") == "inputText":
                text = str(item.get("text") or "").strip()
                break
    if not text:
        return status
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    return f"{status}: {' | '.join(lines[:5])}"


def _call_dynamic_tool(
    *,
    thread_id: str,
    turn_id: str,
    preferred_name: str,
    arguments: dict[str, object],
    item_id: str,
) -> str:
    tool = _dynamic_tool_for_request(thread_id, preferred_name)
    if tool is None:
        return f"no_dynamic_tool:{preferred_name}"
    tool_name = str(tool.get("name") or "").strip()
    response = _server_request(
        f"dynamic-tool-request-{turn_id}-{item_id}",
        "item/tool/call",
        {
            "threadId": thread_id,
            "turnId": turn_id,
            "itemId": item_id,
            "namespace": str(tool.get("namespace") or ""),
            "tool": tool_name,
            "arguments": dict(arguments),
        },
    )
    return _dynamic_tool_response_text(response)


def _should_split_visible_child_tasks(normalized: str) -> bool:
    mentions_visible_child = any(
        marker in normalized
        for marker in (
            "visible child",
            "child tab",
            "child tabs",
            "子tab",
            "子 tab",
            "可见子",
        )
    )
    mentions_two = any(marker in normalized for marker in ("two", "2", "两个", "兩個"))
    mentions_split = any(marker in normalized for marker in ("split", "fork", "拆"))
    mentions_sources = "readme" in normalized and "docs" in normalized
    return mentions_visible_child and mentions_two and mentions_split and mentions_sources


def _should_wait_visible_child_results(normalized: str) -> bool:
    if "agenthub_visible_child_task_updates" in normalized:
        return False
    return any(
        marker in normalized
        for marker in (
            "taskrun",
            "task run",
            "structured result",
            "structured results",
            "结构化结果",
            "結構化結果",
            "wait child",
        )
    )


def _should_send_visible_child_followup(normalized: str) -> bool:
    mentions_followup = any(
        marker in normalized
        for marker in (
            "follow-up",
            "follow up",
            "追问",
            "追問",
            "注入",
            "新命令",
        )
    )
    mentions_child = any(marker in normalized for marker in ("child", "子tab", "子 tab"))
    return mentions_followup and mentions_child


def _maybe_call_dynamic_child_tool(
    *,
    thread_id: str,
    turn_id: str,
    input_text: str,
) -> str:
    normalized = str(input_text or "").lower()
    if "dynamic child tool" in normalized:
        return _call_dynamic_tool(
            thread_id=thread_id,
            turn_id=turn_id,
            preferred_name="spawn_child_tab",
            arguments=_dynamic_tool_arguments("spawn_child_tab"),
            item_id="dynamic-tool-1",
        )
    if _should_split_visible_child_tasks(normalized):
        responses = [
            _call_dynamic_tool(
                thread_id=thread_id,
                turn_id=turn_id,
                preferred_name="spawn_child_tab",
                arguments={
                    "task": "README child: inspect README and summarize project capability.",
                    "task_name": "README",
                    "metadata": {"run_id": "fake_nl_run"},
                },
                item_id="dynamic-tool-readme",
            ),
            _call_dynamic_tool(
                thread_id=thread_id,
                turn_id=turn_id,
                preferred_name="spawn_child_tab",
                arguments={
                    "task": "Docs child: inspect docs and summarize design status.",
                    "task_name": "DOCS",
                    "metadata": {"run_id": "fake_nl_run"},
                },
                item_id="dynamic-tool-docs",
            ),
        ]
        return " | ".join(response for response in responses if response)
    if _should_wait_visible_child_results(normalized):
        return _call_dynamic_tool(
            thread_id=thread_id,
            turn_id=turn_id,
            preferred_name="wait_child_tasks",
            arguments={"targets": [], "terminal_only": True, "timeout_ms": 0},
            item_id="dynamic-tool-wait",
        )
    if _should_send_visible_child_followup(normalized):
        return _call_dynamic_tool(
            thread_id=thread_id,
            turn_id=turn_id,
            preferred_name="send_child_tab",
            arguments={
                "target": "latest",
                "message": "Follow up: report one missing risk and the next action.",
                "interrupt": False,
                "metadata": {"run_id": "fake_nl_run", "card_id": "FOLLOWUP", "attempt": 1},
            },
            item_id="dynamic-tool-followup",
        )
    return ""


def _complete_turn(
    *,
    thread_id: str,
    turn_id: str,
    input_text: str,
    delay: float = 0.0,
) -> None:
    if delay > 0:
        time.sleep(delay)
    key = _turn_key(thread_id, turn_id)
    state = ACTIVE_TURNS.setdefault(
        key,
        {
            "thread_id": thread_id,
            "turn_id": turn_id,
            "input_text": input_text,
            "steers": [],
            "interrupted": False,
        },
    )
    if bool(state.get("interrupted")):
        _write(
            {
                "method": "turn/completed",
                "params": {"threadId": thread_id, "turn": _turn(turn_id, "interrupted")},
            }
        )
        ACTIVE_TURNS.pop(key, None)
        return

    steers = [
        str(item or "").strip()
        for item in list(state.get("steers") or [])
        if str(item or "").strip()
    ]
    steer_suffix = f" steer:{' | '.join(steers)}" if steers else ""
    dynamic_tool_text = _maybe_call_dynamic_child_tool(
        thread_id=thread_id,
        turn_id=turn_id,
        input_text=input_text,
    )
    dynamic_tool_suffix = f" dynamic:{dynamic_tool_text}" if dynamic_tool_text else ""
    reply_text = f"fake sidecar reply{steer_suffix}{dynamic_tool_suffix}"
    _write(
        {
            "method": "item/started",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "item": {
                    "type": "reasoning",
                    "id": "reasoning-1",
                    "summary": [],
                    "content": [],
                },
            },
        }
    )
    _write(
        {
            "method": "item/reasoning/summaryTextDelta",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "itemId": "reasoning-1",
                "delta": "检查请求",
                "summaryIndex": 0,
            },
        }
    )
    _write(
        {
            "method": "item/started",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "item": {
                    "type": "agentMessage",
                    "id": "msg-1",
                    "text": "",
                    "phase": "final_answer",
                },
            },
        }
    )
    _write(
        {
            "method": "item/agentMessage/delta",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "itemId": "msg-1",
                "delta": reply_text,
            },
        }
    )
    _write(
        {
            "method": "item/started",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "item": {
                    "type": "commandExecution",
                    "id": "cmd-1",
                    "command": "printf ok",
                    "cwd": "/tmp",
                    "processId": "proc-1",
                    "source": "agent",
                    "status": "inProgress",
                    "commandActions": [],
                    "aggregatedOutput": None,
                    "exitCode": None,
                    "durationMs": None,
                },
            },
        }
    )
    _write(
        {
            "method": "item/commandExecution/outputDelta",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "itemId": "cmd-1",
                "delta": "ok\n",
            },
        }
    )
    _write(
        {
            "method": "item/completed",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "item": {
                    "type": "commandExecution",
                    "id": "cmd-1",
                    "command": "printf ok",
                    "cwd": "/tmp",
                    "processId": "proc-1",
                    "source": "agent",
                    "status": "completed",
                    "commandActions": [],
                    "aggregatedOutput": "ok\n",
                    "exitCode": 0,
                    "durationMs": 12,
                },
            },
        }
    )
    _write(
        {
            "method": "item/completed",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "item": {
                    "type": "agentMessage",
                    "id": "msg-1",
                    "text": reply_text,
                    "phase": "final_answer",
                },
            },
        }
    )
    _write(
        {
            "method": "thread/tokenUsage/updated",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "tokenUsage": {
                    "last": {
                        "totalTokens": 10,
                        "inputTokens": 4,
                        "cachedInputTokens": 1,
                        "outputTokens": 6,
                        "reasoningOutputTokens": 2,
                    },
                    "total": {
                        "totalTokens": 10,
                        "inputTokens": 4,
                        "cachedInputTokens": 1,
                        "outputTokens": 6,
                        "reasoningOutputTokens": 2,
                    },
                    "modelContextWindow": 128000,
                },
            },
        }
    )
    _write(
        {
            "method": "turn/completed",
            "params": {"threadId": thread_id, "turn": _turn(turn_id, "completed")},
        }
    )
    thread_state = THREADS.setdefault(
        thread_id,
        {
            "thread": _thread(thread_id),
            "turns": [],
            "model": "fake-model",
            "modelProvider": "fake-provider",
            "cwd": "",
        },
    )
    turns = list(thread_state.get("turns") or [])
    turns.append(
        {
            "id": turn_id,
            "items": [
                {
                    "type": "userMessage",
                    "id": "user-1",
                    "text": input_text,
                },
                {
                    "type": "agentMessage",
                    "id": "msg-1",
                    "text": reply_text,
                    "phase": "final_answer",
                },
            ],
            "status": "completed",
        }
    )
    thread_state["turns"] = turns
    ACTIVE_TURNS.pop(key, None)
    _save_state()


def _handle(message: dict[str, object]) -> None:
    method = str(message.get("method") or "")
    request_id = message.get("id")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}

    if request_id is None:
        if method == "initialized":
            _write({"method": "server/initialized", "params": {"ok": True}})
        return

    if method == "initialize":
        _result(
            request_id,
            {
                "userAgent": "fake-codex-sidecar/0.1",
                "codexHome": "/tmp/fake-codex-home",
                "platformFamily": "unix",
                "platformOs": "linux",
            },
        )
        return

    if method == "thread/start":
        thread_id = _next_thread_id()
        _write({"method": "thread/status/changed", "params": {"status": "idle"}})
        _result(
            request_id,
            _thread_result(thread_id=thread_id, params=params),
        )
        return

    if method == "thread/resume":
        thread_id = str(params.get("threadId") or params.get("thread_id") or "")
        if not thread_id:
            _error(request_id, "thread id is required")
            return
        existing = THREADS.get(thread_id)
        turns = list(existing.get("turns") or []) if existing is not None else []
        dynamic_tools = (
            _copy_dynamic_tools(existing.get("dynamicTools")) if isinstance(existing, dict) else []
        )
        _result(
            request_id,
            _thread_result(
                thread_id=thread_id,
                params=params,
                name="Fake Thread",
                turns=turns,
                dynamic_tools=dynamic_tools,
            ),
        )
        return

    if method == "thread/fork":
        source_thread_id = str(params.get("threadId") or params.get("thread_id") or "")
        source = THREADS.get(source_thread_id)
        source_turns = list(source.get("turns") or []) if source is not None else []
        if not source_turns:
            _error(request_id, f"no rollout found for thread id {source_thread_id}")
            return
        source_dynamic_tools = (
            _copy_dynamic_tools(source.get("dynamicTools")) if isinstance(source, dict) else []
        )
        thread_id = _next_thread_id()
        _result(
            request_id,
            _thread_result(
                thread_id=thread_id,
                params=params,
                name="Forked Fake Thread",
                forked_from_id=source_thread_id,
                turns=source_turns,
                dynamic_tools=source_dynamic_tools,
            ),
        )
        return

    if method == "thread/read":
        thread_id = str(params.get("threadId") or params.get("thread_id") or "")
        if not thread_id:
            _error(request_id, "thread id is required")
            return
        _result(
            request_id,
            {
                "thread": _thread_payload(
                    thread_id,
                    include_turns=bool(params.get("includeTurns")),
                )
            },
        )
        return

    if method == "thread/list":
        archived_filter = params.get("archived")
        limit = params.get("limit")
        try:
            max_items = int(limit) if limit is not None else None
        except (TypeError, ValueError):
            max_items = None
        rows = []
        for thread_id in sorted(THREADS):
            state = THREADS[thread_id]
            is_archived = bool(state.get("archived")) if isinstance(state, dict) else False
            if archived_filter is True and not is_archived:
                continue
            if archived_filter in {False, None} and is_archived:
                continue
            rows.append(_thread_payload(thread_id, include_turns=False))
        if max_items is not None:
            rows = rows[: max(0, max_items)]
        _result(
            request_id,
            {
                "data": rows,
                "nextCursor": None,
                "backwardsCursor": None,
            },
        )
        return

    if method == "thread/loaded/list":
        rows = list(sorted(THREADS))
        limit = params.get("limit")
        try:
            max_items = int(limit) if limit is not None else None
        except (TypeError, ValueError):
            max_items = None
        if max_items is not None:
            rows = rows[: max(0, max_items)]
        _result(
            request_id,
            {
                "data": rows,
                "nextCursor": None,
                "backwardsCursor": None,
            },
        )
        return

    if method == "thread/archive":
        thread_id = str(params.get("threadId") or params.get("thread_id") or "")
        state = THREADS.get(thread_id)
        if not isinstance(state, dict):
            _error(request_id, "thread not found")
            return
        state["archived"] = True
        _save_state()
        _result(request_id, {})
        _write({"method": "thread/archived", "params": {"threadId": thread_id}})
        return

    if method == "thread/unarchive":
        thread_id = str(params.get("threadId") or params.get("thread_id") or "")
        state = THREADS.get(thread_id)
        if not isinstance(state, dict):
            _error(request_id, "thread not found")
            return
        state["archived"] = False
        _save_state()
        _result(request_id, {"thread": _thread_payload(thread_id, include_turns=False)})
        _write({"method": "thread/unarchived", "params": {"threadId": thread_id}})
        return

    if method == "thread/rollback":
        thread_id = str(params.get("threadId") or params.get("thread_id") or "")
        state = THREADS.get(thread_id)
        if not isinstance(state, dict):
            _error(request_id, "thread not found")
            return
        try:
            num_turns = int(params.get("numTurns") or 0)
        except (TypeError, ValueError):
            num_turns = 0
        if num_turns < 1:
            _error(request_id, "numTurns must be >= 1")
            return
        turns = list(state.get("turns") or [])
        state["turns"] = turns[:-num_turns] if num_turns < len(turns) else []
        _save_state()
        _result(request_id, {"thread": _thread_payload(thread_id, include_turns=True)})
        return

    if method == "thread/compact/start":
        thread_id = str(params.get("threadId") or params.get("thread_id") or "")
        if thread_id not in THREADS:
            _error(request_id, "thread not found")
            return
        turn_id = f"compact-{int(time.time() * 1000)}"
        _write(
            {
                "method": "turn/started",
                "params": {"threadId": thread_id, "turn": _turn(turn_id)},
            }
        )
        _result(request_id, {})
        _write(
            {
                "method": "item/started",
                "params": {
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "item": {"type": "contextCompaction", "id": "compact-1"},
                },
            }
        )
        _write(
            {
                "method": "item/completed",
                "params": {
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "item": {"type": "contextCompaction", "id": "compact-1"},
                },
            }
        )
        _write(
            {
                "method": "turn/completed",
                "params": {"threadId": thread_id, "turn": _turn(turn_id, "completed")},
            }
        )
        return

    if method == "thread/name/set":
        thread_id = str(params.get("threadId") or params.get("thread_id") or "")
        name = str(params.get("name") or "").strip()
        state = THREADS.get(thread_id)
        if not isinstance(state, dict):
            _error(request_id, "thread not found")
            return
        if not name:
            _error(request_id, "thread name must not be empty")
            return
        thread = dict(state.get("thread") or {})
        thread["name"] = name
        state["thread"] = thread
        _save_state()
        _result(request_id, {})
        _write(
            {
                "method": "thread/name/updated",
                "params": {"threadId": thread_id, "threadName": name},
            }
        )
        return

    if method == "thread/metadata/update":
        thread_id = str(params.get("threadId") or params.get("thread_id") or "")
        state = THREADS.get(thread_id)
        if not isinstance(state, dict):
            _error(request_id, "thread not found")
            return
        git_info = params.get("gitInfo")
        if isinstance(git_info, dict):
            existing = state.get("gitInfo") if isinstance(state.get("gitInfo"), dict) else {}
            merged = dict(existing)
            for key, value in git_info.items():
                if value is None:
                    merged.pop(str(key), None)
                else:
                    merged[str(key)] = value
            state["gitInfo"] = merged or None
        elif git_info is None and "gitInfo" in params:
            state["gitInfo"] = None
        _save_state()
        _result(request_id, {"thread": _thread_payload(thread_id, include_turns=False)})
        return

    if method == "model/list":
        include_hidden = bool(params.get("includeHidden"))
        models = [
            {
                "id": "gpt-fake-default",
                "model": "gpt-fake-default",
                "upgrade": None,
                "upgradeInfo": None,
                "availabilityNux": None,
                "displayName": "GPT Fake Default",
                "description": "Fake visible model",
                "hidden": False,
                "supportedReasoningEfforts": [
                    {"reasoningEffort": "medium", "description": "Balanced"}
                ],
                "defaultReasoningEffort": "medium",
                "inputModalities": ["text"],
                "supportsPersonality": False,
                "additionalSpeedTiers": [],
                "isDefault": True,
            },
            {
                "id": "gpt-fake-hidden",
                "model": "gpt-fake-hidden",
                "upgrade": None,
                "upgradeInfo": None,
                "availabilityNux": None,
                "displayName": "GPT Fake Hidden",
                "description": "Fake hidden model",
                "hidden": True,
                "supportedReasoningEfforts": [],
                "defaultReasoningEffort": "medium",
                "inputModalities": ["text"],
                "supportsPersonality": False,
                "additionalSpeedTiers": [],
                "isDefault": False,
            },
        ]
        if not include_hidden:
            models = [item for item in models if not bool(item.get("hidden"))]
        _result(request_id, {"data": models, "nextCursor": None})
        return

    if method == "modelProvider/capabilities/read":
        _result(
            request_id,
            {
                "namespaceTools": True,
                "imageGeneration": False,
                "webSearch": True,
            },
        )
        return

    if method == "fs/readFile":
        path = Path(str(params.get("path") or ""))
        if not path.is_absolute() or not path.is_file():
            _error(request_id, "file not found")
            return
        try:
            data = path.read_bytes()
        except OSError as exc:
            _error(request_id, str(exc))
            return
        _result(request_id, {"dataBase64": base64.b64encode(data).decode("ascii")})
        return

    if method == "fs/readDirectory":
        path = Path(str(params.get("path") or ""))
        if not path.is_absolute() or not path.is_dir():
            _error(request_id, "directory not found")
            return
        entries = []
        for child in sorted(path.iterdir(), key=lambda item: item.name):
            entries.append(
                {
                    "fileName": child.name,
                    "isDirectory": child.is_dir(),
                    "isFile": child.is_file(),
                }
            )
        _result(request_id, {"entries": entries})
        return

    if method == "fs/getMetadata":
        path = Path(str(params.get("path") or ""))
        if not path.is_absolute() or not path.exists():
            _error(request_id, "path not found")
            return
        try:
            stat = path.stat()
        except OSError as exc:
            _error(request_id, str(exc))
            return
        _result(
            request_id,
            {
                "isDirectory": path.is_dir(),
                "isFile": path.is_file(),
                "isSymlink": path.is_symlink(),
                "createdAtMs": int(stat.st_ctime * 1000),
                "modifiedAtMs": int(stat.st_mtime * 1000),
            },
        )
        return

    if method == "mcpServerStatus/list":
        _result(
            request_id,
            {
                "data": [
                    {
                        "name": "fake-mcp",
                        "tools": {
                            "echo": {
                                "name": "echo",
                                "description": "Echo arguments",
                                "inputSchema": {"type": "object"},
                            }
                        },
                        "resources": [],
                        "resourceTemplates": [],
                        "authStatus": {"type": "none"},
                    }
                ],
                "nextCursor": None,
            },
        )
        return

    if method == "mcpServer/resource/read":
        _result(
            request_id,
            {
                "contents": [
                    {
                        "uri": str(params.get("uri") or ""),
                        "mimeType": "text/plain",
                        "text": "fake resource",
                    }
                ]
            },
        )
        return

    if method == "mcpServer/tool/call":
        _result(
            request_id,
            {
                "content": [{"type": "text", "text": "fake tool result"}],
                "structuredContent": {"ok": True},
                "isError": False,
            },
        )
        return

    if method == "skills/list":
        cwds = list(params.get("cwds") or ["/tmp/fake-work"])
        _result(
            request_id,
            {
                "data": [
                    {
                        "cwd": str(cwds[0]),
                        "skills": [
                            {
                                "name": "fake-skill",
                                "description": "Fake skill",
                                "path": "/tmp/fake-skill/SKILL.md",
                                "scope": "project",
                                "enabled": True,
                            }
                        ],
                        "errors": [],
                    }
                ]
            },
        )
        return

    if method == "plugin/list":
        _result(
            request_id,
            {
                "marketplaces": [
                    {
                        "name": "fake-market",
                        "path": None,
                        "interface": None,
                        "plugins": [
                            {
                                "id": "fake-plugin@fake-market",
                                "name": "fake-plugin",
                                "source": "local",
                                "installed": True,
                                "enabled": True,
                                "installPolicy": "allowed",
                                "authPolicy": "none",
                                "availability": "AVAILABLE",
                                "interface": None,
                            }
                        ],
                    }
                ],
                "marketplaceLoadErrors": [],
                "featuredPluginIds": [],
            },
        )
        return

    if method == "plugin/read":
        plugin_name = str(params.get("pluginName") or "fake-plugin")
        _result(
            request_id,
            {
                "plugin": {
                    "marketplaceName": "fake-market",
                    "marketplacePath": None,
                    "summary": {
                        "id": f"{plugin_name}@fake-market",
                        "name": plugin_name,
                        "source": "local",
                        "installed": True,
                        "enabled": True,
                        "installPolicy": "allowed",
                        "authPolicy": "none",
                        "availability": "AVAILABLE",
                        "interface": None,
                    },
                    "description": "Fake plugin detail",
                    "skills": [],
                    "apps": [],
                    "mcpServers": ["fake-mcp"],
                }
            },
        )
        return

    if method == "turn/start":
        thread_id = str(params.get("threadId") or "thread-1")
        turn_id = _next_turn_id(thread_id)
        input_text = _turn_input_text(params.get("input"))
        key = _turn_key(thread_id, turn_id)
        ACTIVE_TURNS[key] = {
            "thread_id": thread_id,
            "turn_id": turn_id,
            "input_text": input_text,
            "steers": [],
            "interrupted": False,
        }
        _write(
            {
                "method": "turn/started",
                "params": {"threadId": thread_id, "turn": _turn(turn_id)},
            }
        )
        _result(request_id, {"turn": _turn(turn_id)})
        time.sleep(0.05)
        if "approval" in input_text.lower():
            approval_response = _server_request(
                "approval-request-1",
                "item/commandExecution/requestApproval",
                {
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "itemId": "cmd-approval-1",
                    "approvalId": "codex_fake_approval_1",
                    "reason": "fake approval requested",
                    "command": "printf approved",
                    "cwd": "/tmp",
                    "commandActions": [],
                    "availableDecisions": [
                        "accept",
                        "acceptForSession",
                        "decline",
                        "cancel",
                    ],
                },
            )
            decision = ""
            if isinstance(approval_response, dict):
                decision = str(approval_response.get("decision") or "")
            if decision in {"decline", "cancel"}:
                _write(
                    {
                        "method": "turn/completed",
                        "params": {
                            "threadId": thread_id,
                            "turn": _turn(turn_id, "completed"),
                        },
                    }
                )
                return
        delay = 0.45 if "slow" in input_text.lower() else 0.0
        if delay > 0:
            threading.Thread(
                target=_complete_turn,
                kwargs={
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                    "input_text": input_text,
                    "delay": delay,
                },
                daemon=True,
            ).start()
        else:
            _complete_turn(
                thread_id=thread_id,
                turn_id=turn_id,
                input_text=input_text,
            )
        return

    if method == "turn/interrupt":
        thread_id = str(params.get("threadId") or "")
        turn_id = str(params.get("turnId") or "")
        key = _turn_key(thread_id, turn_id)
        state = ACTIVE_TURNS.get(key)
        if state is None:
            _error(request_id, "no active turn")
            return
        state["interrupted"] = True
        _result(request_id, {})
        return

    if method == "turn/steer":
        thread_id = str(params.get("threadId") or "")
        turn_id = str(params.get("expectedTurnId") or "")
        key = _turn_key(thread_id, turn_id)
        state = ACTIVE_TURNS.get(key)
        if state is None:
            _error(request_id, "no active steerable turn")
            return
        steer_text = _turn_input_text(params.get("input"))
        if steer_text:
            steers = list(state.get("steers") or [])
            steers.append(steer_text)
            state["steers"] = steers
        _result(request_id, {"turnId": turn_id})
        return

    _error(request_id, f"unknown method: {method}")


def _turn_input_text(value: object) -> str:
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value:
        if isinstance(item, dict):
            text = str(item.get("text") or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts)


def main() -> int:
    if sys.argv[1:3] != ["--listen", "stdio://"]:
        print("expected --listen stdio://", file=sys.stderr)
        return 2
    _load_state()
    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            message = json.loads(stripped)
        except json.JSONDecodeError:
            print(f"invalid json: {stripped}", file=sys.stderr)
            continue
        if isinstance(message, dict):
            _handle(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
