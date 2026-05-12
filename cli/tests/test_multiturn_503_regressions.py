from __future__ import annotations

import json
import tempfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from cli.agent_cli.environment_context import (
    build_environment_context_snapshot,
    extract_environment_contract_from_input_items,
)
from cli.agent_cli.models import AgentIntent, PromptResponse, ResponseInputItem, default_response_items
from cli.agent_cli.providers.adapters.openai_responses import OpenAIResponsesSession
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.thread_store import ThreadStore

class _RecordingAgent:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.cwd: Path | None = None

    def provider_status(self):
        return {
            "provider_ready": "true",
            "provider_name": "openai",
            "model_key": "gpt_54",
            "provider_planner": "openai_responses",
            "provider_model": "gpt-5.4",
            "provider_tools": "tool-calls",
            "session_line": "openai-tools",
            "provider_label": "openai | gpt-5.4 | tool-calls",
            "provider_base_url": "https://relay05.relay.example/reference/v1",
            "provider_source": "test",
            "provider_config_path": "/tmp/config.toml",
            "provider_auth_path": "/tmp/auth.json",
            "platform_family": "unix",
            "platform_os": "linux",
            "shell_kind": "bash",
        }

    def plan(self, text, history=None, *, tool_executor=None, attachments=None, input_items=None):
        self.calls.append(
            {
                "text": text,
                "history": list(history or []),
                "input_items": list(input_items or []),
            }
        )
        return AgentIntent(assistant_text=f"echo: {text}")

    def switch_model(self, model_key):
        del model_key

    def switch_provider(self, provider_name):
        del provider_name

    def switch_provider_line(self, line):
        del line

    def set_cwd(self, cwd):
        self.cwd = Path(cwd).resolve()
        return self.cwd

class _FakeResponses:
    def __init__(self, response) -> None:
        self.response = response
        self.requests: list[dict] = []

    def create(self, **kwargs):
        self.requests.append(dict(kwargs))
        return self.response

class _FakeClient:
    def __init__(self, response) -> None:
        self.responses = _FakeResponses(response)

def _response(*items, response_id: str = "resp_1"):
    return SimpleNamespace(
        id=response_id,
        output=list(items),
        output_text="ok",
    )

def _typed_user_message(text: str) -> dict:
    return {
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": text}],
    }

def _message_texts(items: list[dict]) -> list[str]:
    texts: list[str] = []
    for item in list(items or []):
        if str(item.get("type") or "").strip() != "message":
            continue
        for block in list(item.get("content") or []):
            if not isinstance(block, dict):
                continue
            text = str(block.get("text") or "").strip()
            if text:
                texts.append(text)
    return texts

def _content_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    texts: list[str] = []
    for block in list(content or []):
        if not isinstance(block, dict):
            continue
        text = str(block.get("text") or "").strip()
        if text:
            texts.append(text)
    return "\n".join(texts).strip()

def _is_environment_context_message(item: dict) -> bool:
    if str(item.get("type") or "").strip() != "message":
        return False
    if str(item.get("role") or "").strip().lower() != "user":
        return False
    return "<environment_context>" in _content_text(item.get("content"))

def _responses_multiturn_503_risk_reasons(items: list[dict]) -> list[str]:
    reasons: list[str] = []

    if not any(_is_environment_context_message(item) for item in list(items or [])):
        reasons.append("missing_environment_context_message")

    for index, item in enumerate(list(items or [])):
        if not isinstance(item, dict):
            continue
        if "role" not in item or "content" not in item:
            continue
        item_type = str(item.get("type") or "").strip()
        if item_type != "message":
            role = str(item.get("role") or "").strip().lower() or "unknown"
            reasons.append(f"message_missing_type:{role}@{index}")

    return reasons

def _simulate_provider_503_for_malformed_multiturn_request(request: dict) -> dict:
    reasons = _responses_multiturn_503_risk_reasons(list(request.get("input") or []))
    if reasons:
        raise RuntimeError(
            "InternalServerError: Error code: 503 - "
            + str(
                {
                    "error": {
                        "type": "proxy_unavailable",
                        "message": f"malformed multiturn request: {', '.join(reasons)}",
                    }
                }
            )
        )
    return request

def _capture_date_followup_request(*, current_dt: datetime | None = None) -> tuple[dict, list[dict]]:
    fixed_dt = current_dt or datetime(2026, 4, 1, 10, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    def _setup_history(store: ThreadStore, thread_id: str, workspace: Path) -> None:
        snapshot = build_environment_context_snapshot(
            cwd=str(workspace.resolve()),
            shell="bash",
            network_access=True,
            current_dt=fixed_dt,
        )
        store.append_turn(
            thread_id,
            PromptResponse(
                user_text="今天几号？",
                assistant_text="今天是 2026 年 4 月 1 日。",
                protocol_diagnostics={
                    "protocol_path": {
                        "kind": "provider_loop",
                        "source": "provider",
                        "provider_used": True,
                    }
                },
                response_items=default_response_items(assistant_text="今天是 2026 年 4 月 1 日。"),
            ),
            runtime_state={"environment_context_snapshot": snapshot},
        )

    return _capture_followup_request(
        setup_history=_setup_history,
        followup_prompt="明天呢？",
        current_dt=fixed_dt,
    )

def _remove_environment_context_item(request: dict) -> dict:
    mutated = deepcopy(request)
    mutated["input"] = [
        item for item in list(mutated.get("input") or []) if not _is_environment_context_message(item)
    ]
    return mutated

def _drop_message_type(request: dict, *, role: str, text: str) -> dict:
    mutated = deepcopy(request)
    for item in list(mutated.get("input") or []):
        if str(item.get("role") or "").strip().lower() != role.lower():
            continue
        if text not in _content_text(item.get("content")):
            continue
        item.pop("type", None)
        return mutated
    raise AssertionError(f"message not found for role={role!r} text={text!r}")

def _capture_followup_request(
    *,
    setup_history,
    followup_prompt: str = "继续",
    current_dt: datetime | None = None,
) -> tuple[dict, list[dict]]:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        workspace = root / "workspace"
        workspace.mkdir()
        store = ThreadStore(root / "state")
        thread = store.start_thread(name="503 regression", cwd=str(workspace.resolve()))

        setup_history(store, thread.thread_id, workspace)

        agent = _RecordingAgent()
        runtime = AgentCliRuntime(agent=agent, thread_store=store)
        runtime.resume_thread(thread.thread_id)
        if current_dt is not None:
            runtime._current_dt_provider = lambda: current_dt
        runtime.handle_prompt(followup_prompt)

        planner_input_items = list(agent.calls[0]["input_items"])
        client = _FakeClient(_response())
        session = OpenAIResponsesSession(
            client=client,
            model="gpt-5.4",
            instructions="system",
            tool_specs=[],
        )
        session.send(
            input_items=[*planner_input_items, _typed_user_message(followup_prompt)],
            allow_tools=False,
        )
        return client.responses.requests[0], planner_input_items


def _append_rollout_line(root: Path, thread_id: str, payload: dict) -> None:
    rollout_path = root / "state" / "rollouts" / f"{thread_id}.jsonl"
    with rollout_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _capture_followup_request_from_rollout_items(
    *,
    rollout_items: list[dict],
    followup_prompt: str = "继续",
    current_dt: datetime | None = None,
) -> tuple[dict, list[dict]]:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        workspace = root / "workspace"
        workspace.mkdir()
        store = ThreadStore(root / "state")
        thread = store.start_thread(name="503 rollout regression", cwd=str(workspace.resolve()))
        for index, raw_payload in enumerate(list(rollout_items or []), start=1):
            payload = {
                "thread_id": thread.thread_id,
                "timestamp": f"2026-04-01T00:00:{index:02d}+00:00",
                **dict(raw_payload),
            }
            _append_rollout_line(root, thread.thread_id, payload)

        agent = _RecordingAgent()
        runtime = AgentCliRuntime(agent=agent, thread_store=store)
        runtime.resume_thread(thread.thread_id)
        if current_dt is not None:
            runtime._current_dt_provider = lambda: current_dt
        runtime.handle_prompt(followup_prompt)

        planner_input_items = list(agent.calls[0]["input_items"])
        client = _FakeClient(_response())
        session = OpenAIResponsesSession(
            client=client,
            model="gpt-5.4",
            instructions="system",
            tool_specs=[],
        )
        session.send(
            input_items=[*planner_input_items, _typed_user_message(followup_prompt)],
            allow_tools=False,
        )
        return client.responses.requests[0], planner_input_items

def test_503_regression_date_followup_request_has_full_resume_shape() -> None:
    fixed_dt = datetime(2026, 4, 1, 10, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    request, _ = _capture_date_followup_request(current_dt=fixed_dt)
    request_input = list(request["input"])

    assert _responses_multiturn_503_risk_reasons(request_input) == []
    _simulate_provider_503_for_malformed_multiturn_request(request)

    assert request_input[0]["role"] == "user"
    assert _content_text(request_input[0]["content"]) == "今天几号？"
    assert request_input[1]["role"] == "assistant"
    assert _content_text(request_input[1]["content"]) == "今天是 2026 年 4 月 1 日。"
    assert any(str(item.get("role") or "").strip().lower() == "developer" for item in request_input)
    assert sum(_is_environment_context_message(item) for item in request_input) == 1
    assert request_input[-1]["role"] == "user"
    assert _content_text(request_input[-1]["content"]) == "明天呢？"
    assert extract_environment_contract_from_input_items(request_input) == {
        "cwd": request_input[-2]["content"][0]["text"].split("<cwd>")[1].split("</cwd>")[0],
        "current_date": "2026-04-01",
        "timezone": "Asia/Shanghai",
    }

@pytest.mark.parametrize(
    ("case_id", "mutate_request", "expected_reason"),
    [
        (
            "missing_environment_context_message",
            _remove_environment_context_item,
            "missing_environment_context_message",
        ),
        (
            "previous_user_message_missing_type",
            lambda request: _drop_message_type(request, role="user", text="今天几号？"),
            "message_missing_type:user@0",
        ),
        (
            "previous_assistant_message_missing_type",
            lambda request: _drop_message_type(request, role="assistant", text="今天是 2026 年 4 月 1 日。"),
            "message_missing_type:assistant@1",
        ),
        (
            "developer_message_missing_type",
            lambda request: _drop_message_type(request, role="developer", text="<permissions instructions>"),
            "message_missing_type:developer@2",
        ),
        (
            "current_user_message_missing_type",
            lambda request: _drop_message_type(request, role="user", text="明天呢？"),
            "message_missing_type:user@5",
        ),
    ],
)
def test_503_regression_date_followup_request_missing_one_required_element_is_503_risk(
    case_id: str,
    mutate_request,
    expected_reason: str,
) -> None:
    del case_id
    request, _ = _capture_date_followup_request()
    malformed_request = mutate_request(request)

    reasons = _responses_multiturn_503_risk_reasons(list(malformed_request["input"]))
    assert reasons == [expected_reason]

    with pytest.raises(RuntimeError, match="Error code: 503") as excinfo:
        _simulate_provider_503_for_malformed_multiturn_request(malformed_request)
    assert expected_reason in str(excinfo.value)

def test_503_regression_followup_request_repeats_full_environment_context_when_snapshot_is_unchanged() -> None:
    fixed_dt = datetime(2026, 4, 1, 10, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    def _setup_history(store: ThreadStore, thread_id: str, workspace: Path) -> None:
        snapshot = build_environment_context_snapshot(
            cwd=str(workspace.resolve()),
            shell="bash",
            network_access=True,
            current_dt=fixed_dt,
        )
        store.append_turn(
            thread_id,
            PromptResponse(
                user_text="今天几号？",
                assistant_text="今天是 2026 年 4 月 1 日。",
                protocol_diagnostics={
                    "protocol_path": {
                        "kind": "provider_loop",
                        "source": "provider",
                        "provider_used": True,
                    }
                },
                response_items=default_response_items(assistant_text="今天是 2026 年 4 月 1 日。"),
            ),
            runtime_state={"environment_context_snapshot": snapshot},
        )

    request, planner_input_items = _capture_followup_request(
        setup_history=_setup_history,
        followup_prompt="明天呢？",
        current_dt=fixed_dt,
    )

    request_input = list(request["input"])
    env_contract = extract_environment_contract_from_input_items(request_input)
    assert env_contract == {
        "cwd": planner_input_items[-1]["content"][0]["text"].split("<cwd>")[1].split("</cwd>")[0],
        "current_date": "2026-04-01",
        "timezone": "Asia/Shanghai",
    }
    assert sum("<environment_context>" in text for text in _message_texts(request_input)) == 1
    assert all(str(item.get("type") or "").strip() for item in request_input)
    assert all(
        str(block.get("type") or "").strip()
        for item in request_input
        if str(item.get("type") or "").strip() == "message"
        for block in list(item.get("content") or [])
        if isinstance(block, dict)
    )

def test_503_regression_followup_request_strips_provider_rejected_reasoning_fields() -> None:
    def _setup_history(store: ThreadStore, thread_id: str, workspace: Path) -> None:
        del workspace
        store.append_turn(
            thread_id,
            PromptResponse(
                user_text="现在北京时间几点？",
                assistant_text="北京时间 10:00。",
                protocol_diagnostics={
                    "protocol_path": {
                        "kind": "provider_loop",
                        "source": "provider",
                        "provider_used": True,
                    }
                },
                response_items=[
                    ResponseInputItem.from_dict(
                        {
                            "type": "reasoning",
                            "id": "rs_1",
                            "status": "completed",
                            "summary": [{"type": "summary_text", "text": "先查询北京时间"}],
                            "encrypted_content": "enc-1",
                            "content": [{"type": "reasoning", "text": "先查询北京时间"}],
                        }
                    ),
                    ResponseInputItem.from_dict(
                        {
                            "type": "web_search_call",
                            "id": "ws_1",
                            "action": {"query": 'time: {"utc_offset":"+08:00"}'},
                        }
                    ),
                    ResponseInputItem.from_dict(
                        {
                            "type": "message",
                            "role": "assistant",
                            "phase": "final_answer",
                            "content": [{"type": "output_text", "text": "北京时间 10:00。"}],
                        }
                    ),
                ],
            ),
        )

    request, _ = _capture_followup_request(
        setup_history=_setup_history,
        followup_prompt="继续",
    )

    reasoning_items = [item for item in list(request["input"]) if str(item.get("type") or "").strip() == "reasoning"]
    assert len(reasoning_items) == 1
    assert reasoning_items[0]["encrypted_content"] == "enc-1"
    assert reasoning_items[0]["summary"][0]["text"] == "先查询北京时间"
    assert "id" not in reasoning_items[0]
    assert "status" not in reasoning_items[0]


def test_503_regression_followup_request_backfills_empty_reasoning_summary() -> None:
    def _setup_history(store: ThreadStore, thread_id: str, workspace: Path) -> None:
        del workspace
        store.append_turn(
            thread_id,
            PromptResponse(
                user_text="继续刚才的推理",
                assistant_text="继续处理中。",
                protocol_diagnostics={
                    "protocol_path": {
                        "kind": "provider_loop",
                        "source": "provider",
                        "provider_used": True,
                    }
                },
                response_items=[
                    ResponseInputItem.from_dict(
                        {
                            "type": "reasoning",
                            "id": "rs_missing_summary_1",
                            "status": "completed",
                            "encrypted_content": "enc-missing-summary",
                            "content": None,
                        }
                    ),
                    ResponseInputItem.from_dict(
                        {
                            "type": "message",
                            "role": "assistant",
                            "phase": "final_answer",
                            "content": [{"type": "output_text", "text": "继续处理中。"}],
                        }
                    ),
                ],
            ),
        )

    request, _ = _capture_followup_request(
        setup_history=_setup_history,
        followup_prompt="继续",
    )

    reasoning_items = [item for item in list(request["input"]) if str(item.get("type") or "").strip() == "reasoning"]
    assert len(reasoning_items) == 1
    assert reasoning_items[0] == {
        "type": "reasoning",
        "encrypted_content": "enc-missing-summary",
        "summary": [],
        "content": None,
    }


def test_503_regression_followup_request_fail_closed_strips_turn_event_reasoning_without_encrypted_content() -> None:
    def _setup_history(store: ThreadStore, thread_id: str, workspace: Path) -> None:
        del workspace
        store.append_turn(
            thread_id,
            PromptResponse(
                user_text="现在北京时间几点？",
                assistant_text="北京时间 10:00。",
                protocol_diagnostics={
                    "protocol_path": {
                        "kind": "provider_loop",
                        "source": "provider",
                        "provider_used": True,
                    }
                },
                turn_events=[
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_reasoning_1",
                            "type": "reasoning",
                            "text": "先查询北京时间",
                            "summary": [{"type": "summary_text", "text": "先查询北京时间"}],
                        },
                    },
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "call_exec_1",
                            "type": "command_execution",
                            "call_id": "call_exec_1",
                            "command": "date",
                            "aggregated_output": "10:00\n",
                            "exit_code": 0,
                            "status": "completed",
                        },
                    },
                    {
                        "type": "item.completed",
                        "item": {"id": "item_2", "type": "agent_message", "text": "北京时间 10:00。"},
                    },
                ],
            ),
        )

    request, _ = _capture_followup_request(
        setup_history=_setup_history,
        followup_prompt="继续",
    )

    reasoning_items = [item for item in list(request["input"]) if str(item.get("type") or "").strip() == "reasoning"]
    assert reasoning_items == []
    assert _responses_multiturn_503_risk_reasons(list(request["input"])) == []


def test_503_regression_reasoning_retention_difference_is_replay_path_specific() -> None:
    legacy_request, _ = _capture_followup_request_from_rollout_items(
        rollout_items=[
            {
                "type": "response_item",
                "role": "user",
                "content": "现在北京时间几点？",
            },
            {
                "type": "response_item",
                "item": {
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": "先查询北京时间"}],
                    "encrypted_content": "enc-legacy",
                    "content": None,
                },
            },
            {
                "type": "response_item",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "北京时间 10:00。"}],
                },
            },
        ],
        followup_prompt="继续",
    )

    shared_request, _ = _capture_followup_request(
        setup_history=lambda store, thread_id, workspace: store.append_turn(
            thread_id,
            PromptResponse(
                user_text="现在北京时间几点？",
                assistant_text="北京时间 10:00。",
                protocol_diagnostics={
                    "protocol_path": {
                        "kind": "provider_loop",
                        "source": "provider",
                        "provider_used": True,
                    }
                },
                turn_events=[
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_reasoning_1",
                            "type": "reasoning",
                            "text": "先查询北京时间",
                            "summary": [{"type": "summary_text", "text": "先查询北京时间"}],
                        },
                    },
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "call_exec_1",
                            "type": "command_execution",
                            "call_id": "call_exec_1",
                            "command": "date",
                            "aggregated_output": "10:00\n",
                            "exit_code": 0,
                            "status": "completed",
                        },
                    },
                    {
                        "type": "item.completed",
                        "item": {"id": "item_2", "type": "agent_message", "text": "北京时间 10:00。"},
                    },
                ],
            ),
        ),
        followup_prompt="继续",
    )

    legacy_reasoning_items = [
        item for item in list(legacy_request["input"]) if str(item.get("type") or "").strip() == "reasoning"
    ]
    shared_reasoning_items = [
        item for item in list(shared_request["input"]) if str(item.get("type") or "").strip() == "reasoning"
    ]

    assert legacy_reasoning_items == [
        {
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": "先查询北京时间"}],
            "encrypted_content": "enc-legacy",
            "content": None,
        }
    ]
    assert shared_reasoning_items == []

def test_503_regression_followup_request_excludes_pure_host_text_turns_from_resumed_history() -> None:
    def _setup_history(store: ThreadStore, thread_id: str, workspace: Path) -> None:
        del workspace
        store.append_turn(
            thread_id,
            PromptResponse(
                user_text="你好",
                assistant_text="你好！有什么我可以帮你处理的？",
                protocol_diagnostics={
                    "protocol_path": {
                        "kind": "host_short_circuit_legacy_fixture",
                        "source": "host",
                        "provider_used": False,
                    }
                },
            ),
        )
        store.append_turn(
            thread_id,
            PromptResponse(
                user_text="今天几号？",
                assistant_text="今天是 2026 年 4 月 1 日。",
                protocol_diagnostics={
                    "protocol_path": {
                        "kind": "provider_loop",
                        "source": "provider",
                        "provider_used": True,
                    }
                },
                response_items=default_response_items(assistant_text="今天是 2026 年 4 月 1 日。"),
            ),
        )

    request, _ = _capture_followup_request(
        setup_history=_setup_history,
        followup_prompt="明天呢？",
    )

    request_text = json.dumps(request["input"], ensure_ascii=False)
    assert "你好！有什么我可以帮你处理的？" not in request_text
    assert '"text": "你好"' not in request_text
    assert "今天几号？" in request_text
    assert "今天是 2026 年 4 月 1 日。" in request_text

def test_503_regression_followup_request_keeps_local_tool_outputs_needed_for_resume() -> None:
    def _setup_history(store: ThreadStore, thread_id: str, workspace: Path) -> None:
        runtime = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
        runtime.resume_thread(thread_id)
        runtime.collaboration_mode = "plan"
        runtime.request_user_input_handler = lambda payload: {
            "answers": {"confirm_path": {"answers": ["yes"]}},
            "questions": payload["questions"],
        }
        runtime.handle_prompt(
            '/request_user_input \'{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?","options":[{"label":"Yes (Recommended)","description":"Continue."},{"label":"No","description":"Stop."}]}]}\''  # noqa: E501
        )
        runtime.set_cwd(workspace.resolve())

    request, _ = _capture_followup_request(
        setup_history=_setup_history,
        followup_prompt="follow up",
    )

    function_outputs = [
        item
        for item in list(request["input"])
        if str(item.get("type") or "").strip() == "function_call_output"
    ]
    assert len(function_outputs) == 1
    assert function_outputs[0]["call_id"] == "item_0"
    output_payload = json.loads(function_outputs[0]["output"])
    assert output_payload["response"]["answers"]["confirm_path"]["answers"] == ["yes"]
