from __future__ import annotations

import io
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from cli.agent_cli.host_platform import detect_host_platform
from cli.agent_cli.models import PromptResponse, ToolEvent
from cli.agent_cli.provider import extract_current_turn_prelude_contract
from cli.agent_cli.ui import status_controller_operator_runtime as operator_runtime
from cli.replay_integration.headless_replay import run_headless_replay_case
from cli.replay_integration.live_headless_ab import main as live_headless_ab_main
from cli.replay_integration.live_headless_ab import _payload_response_item_signatures
from cli.replay_integration.live_headless_ab import _timeline_metrics_from_path
from cli.replay_integration.live_headless_ab import run_live_headless_ab_case
from cli.replay_integration.real_cases import (
    get_real_case_pack_spec,
    get_real_case_spec,
    list_operator_live_case_ids,
    load_real_case_cassette,
)
from cli.replay_integration.runtime_replay import recorded_user_prompt
from cli.replay_integration.workspace_snapshot import capture_environment_snapshot, capture_workspace_snapshot

_ENVIRONMENT_CONTRACT = {
    "cwd": "/home/lyc/project/AgentHub/cli",
    "current_date": "2026-03-31",
    "timezone": "Asia/Shanghai",
}
_WORKSPACE_CONTRACT = {
    "cwd": "/home/lyc/project/AgentHub/cli",
    "trust_level": "unknown",
    "instructions_digest": "e5e7cb696f1b91f1742428707f20ce87ceafdbe7",
    "docs": [],
    "skills": [],
    "workspace_digest": "ed1d010033b5e8cc5f7e568f9ab5f9a9bffcb700",
}
_PRELUDE_BASELINE = {
    "item_count": 2,
    "section_order": ["developer", "workspace_context", "environment_context"],
}
_PRELUDE_UPDATE = {
    "item_count": 2,
    "section_order": ["developer", "environment_context"],
}


def _operator_surface_snapshot(response: PromptResponse) -> dict[str, str]:
    return operator_runtime.status_from_response(
        response,
        operator_status_from_response_fn=lambda item: operator_runtime.operator_status_from_response(
            item,
            operator_command_name_fn=operator_runtime.operator_command_name,
            key_value_lines_fn=operator_runtime.key_value_lines,
            operator_status_from_mapping_fn=operator_runtime.operator_status_from_mapping,
            operator_status_from_text_fn=operator_runtime.operator_status_from_text,
            operator_hint_from_command_fn=lambda command_name, key_values, assistant_text: "",
        ),
    )


def _operator_benchmark_fixture(response: PromptResponse) -> dict[str, str]:
    snapshot = _operator_surface_snapshot(response)
    normalized: dict[str, str] = {}
    for key in operator_runtime.OPERATOR_EVIDENCE_KEYS:
        value = str(snapshot.get(key) or "").strip()
        normalized[key] = "" if value == "-" else value
    return normalized


def _protocol_diagnostics(
    *,
    prelude: dict[str, object],
    path_kind: str = "provider_loop",
    source: str = "provider",
    provider_used: bool = True,
    parity_evaluable: bool = True,
    reason: str = "planner_execution",
) -> dict[str, object]:
    return {
        "protocol_path": {
            "kind": path_kind,
            "source": source,
            "provider_used": provider_used,
            "parity_evaluable": parity_evaluable,
            "reason": reason,
        },
        "request_contract": {
            "environment": dict(_ENVIRONMENT_CONTRACT),
            "workspace": dict(_WORKSPACE_CONTRACT),
            "prelude": dict(prelude),
        },
    }

def _write_fake_timeline() -> None:
    timeline_path = str(os.environ.get("AGENTHUB_DEBUG_RESPONSES_TIMELINE") or "").strip()
    if not timeline_path:
        return
    Path(timeline_path).write_text('{"stage":"fake.timeline"}\n', encoding="utf-8")


def _write_fake_timeline_records(*records: dict[str, object], path: Path | None = None) -> Path | None:
    if path is None:
        timeline_text = str(os.environ.get("AGENTHUB_DEBUG_RESPONSES_TIMELINE") or "").strip()
        if not timeline_text:
            return None
        timeline_path = Path(timeline_text)
    else:
        timeline_path = path
    if not str(timeline_path):
        return None
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    Path(timeline_path).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return Path(timeline_path)

def _fake_live_headless_ok(argv, *, stdout=None, stderr=None, **kwargs):
    del kwargs
    args = list(argv)
    prompt = args[args.index("--prompt") + 1]
    resume_thread_id = args[args.index("--resume") + 1] if "--resume" in args else ""
    _write_fake_timeline()
    payload = None
    if prompt == "先执行 pwd，再告诉我当前目录。":
        assert resume_thread_id == ""
        payload = {
            "assistant_text": "当前目录是 `/home/lyc/project/AgentHub/cli`。",
            "commentary_text": "",
            "protocol_diagnostics": _protocol_diagnostics(prelude=_PRELUDE_BASELINE),
            "response_items": [
                {
                    "type": "reasoning",
                    "content": None,
                    "summary": [{"type": "summary_text", "text": "placeholder"}],
                    "encrypted_content": "enc-1",
                },
                {
                    "type": "message",
                    "phase": "commentary",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "我先跑一下 `pwd`，然后把结果直接告诉你。"}],
                },
                {
                    "type": "function_call",
                    "call_id": "call_host_1",
                    "name": "exec_command",
                    "arguments": "{\"cmd\":\"/bin/bash -lc pwd\"}",
                },
                {
                    "type": "function_call_output",
                    "call_id": "call_host_1",
                    "output": "/home/lyc/project/AgentHub/cli\n",
                    "success": True,
                },
                {
                    "type": "function_call",
                    "call_id": "call_fake_1",
                    "name": "exec_command",
                    "arguments": "{\"cmd\":\"pwd\",\"yield_time_ms\":1000,\"max_output_tokens\":200}",
                },
                {
                    "type": "message",
                    "phase": "final_answer",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "当前目录是 `/home/lyc/project/AgentHub/cli`。"}],
                },
            ],
            "status": {
                "thread_id": "live-thread-1",
                "provider_runtime_state": "ready",
            },
            "tool_events": [
                {
                    "name": "exec_command",
                    "ok": True,
                    "summary": "/home/lyc/project/AgentHub/cli\n",
                    "payload": {
                        "command": "/bin/bash -lc pwd",
                        "function_call_output": "/home/lyc/project/AgentHub/cli\n",
                        "stdout": "/home/lyc/project/AgentHub/cli\n",
                    },
                }
            ],
            "turn_events": [
                {"type": "turn.started"},
                {
                    "type": "item.started",
                    "item": {
                        "type": "command_execution",
                        "status": "in_progress",
                        "command": "/bin/bash -lc pwd",
                        "exit_code": None,
                        "aggregated_output": "",
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "type": "command_execution",
                        "status": "completed",
                        "command": "/bin/bash -lc pwd",
                        "exit_code": 0,
                        "aggregated_output": "/home/lyc/project/AgentHub/cli\n",
                    },
                },
                {"type": "turn.completed"},
            ],
        }
    elif prompt == "刚才目录是什么？只回复路径。":
        assert resume_thread_id == "live-thread-1"
        payload = {
            "assistant_text": "`/home/lyc/project/AgentHub/cli`",
            "commentary_text": "",
            "protocol_diagnostics": _protocol_diagnostics(prelude=_PRELUDE_UPDATE),
            "response_items": [
                {
                    "type": "reasoning",
                    "content": None,
                    "summary": [{"type": "summary_text", "text": "placeholder"}],
                    "encrypted_content": "enc-2",
                },
                {
                    "type": "message",
                    "phase": "final_answer",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "`/home/lyc/project/AgentHub/cli`"}],
                },
            ],
            "status": {
                "thread_id": "live-thread-1",
                "provider_runtime_state": "ready",
            },
            "tool_events": [],
            "turn_events": [
                {"type": "turn.started"},
                {"type": "item.completed", "item": {"type": "agent_message", "text": "`/home/lyc/project/AgentHub/cli`"}},
                {"type": "turn.completed"},
            ],
        }
    else:
        raise AssertionError(f"unexpected prompt: {prompt!r}")
    (stdout or io.StringIO()).write(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0

def _fake_live_headless_mismatch(argv, *, stdout=None, stderr=None, **kwargs):
    del stderr, kwargs
    args = list(argv)
    prompt = args[args.index("--prompt") + 1]
    resume_thread_id = args[args.index("--resume") + 1] if "--resume" in args else ""
    _write_fake_timeline()
    if prompt == "项目目录是 /srv/app。请记住这个路径，并只回复“记住了”。":
        payload = {
            "assistant_text": "记住了",
            "commentary_text": "",
            "protocol_diagnostics": _protocol_diagnostics(prelude=_PRELUDE_BASELINE),
            "response_items": [
                {
                    "type": "reasoning",
                    "content": None,
                    "summary": [],
                    "encrypted_content": "enc-3",
                },
                {
                    "type": "message",
                    "phase": "final_answer",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "记住了"}],
                },
            ],
            "status": {
                "thread_id": "live-thread-2",
                "provider_runtime_state": "ready",
            },
            "tool_events": [],
            "turn_events": [{"type": "turn.started"}, {"type": "turn.completed"}],
        }
    elif prompt == "刚才那个目录是什么？只回复路径。":
        assert resume_thread_id == "live-thread-2"
        payload = {
            "assistant_text": "/srv/other",
            "commentary_text": "",
            "protocol_diagnostics": _protocol_diagnostics(prelude=_PRELUDE_UPDATE),
            "response_items": [
                {
                    "type": "reasoning",
                    "content": None,
                    "summary": [],
                    "encrypted_content": "enc-4",
                },
                {
                    "type": "message",
                    "phase": "final_answer",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "/srv/other"}],
                },
            ],
            "status": {
                "thread_id": "live-thread-2",
                "provider_runtime_state": "ready",
            },
            "tool_events": [],
            "turn_events": [{"type": "turn.started"}, {"type": "turn.completed"}],
        }
    else:
        raise AssertionError(f"unexpected prompt: {prompt!r}")
    (stdout or io.StringIO()).write(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0

def _fake_live_headless_tool_process_mismatch(argv, *, stdout=None, stderr=None, **kwargs):
    del stderr, kwargs
    args = list(argv)
    prompt = args[args.index("--prompt") + 1]
    resume_thread_id = args[args.index("--resume") + 1] if "--resume" in args else ""
    _write_fake_timeline()
    if prompt == "先执行 pwd，再告诉我当前目录。":
        assert resume_thread_id == ""
        payload = {
            "assistant_text": "当前目录是 `/home/lyc/project/AgentHub/cli`。",
            "commentary_text": "",
            "protocol_diagnostics": _protocol_diagnostics(prelude=_PRELUDE_BASELINE),
            "response_items": [
                {
                    "type": "reasoning",
                    "content": None,
                    "summary": [{"type": "summary_text", "text": "placeholder"}],
                    "encrypted_content": "enc-5",
                },
                {
                    "type": "message",
                    "phase": "commentary",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "我先跑一下 `pwd`，然后把结果直接告诉你。"}],
                },
                {
                    "type": "function_call",
                    "call_id": "call_host_2",
                    "name": "exec_command",
                    "arguments": "{\"cmd\":\"/bin/bash -lc pwd\"}",
                },
                {
                    "type": "function_call_output",
                    "call_id": "call_host_2",
                    "output": "/home/lyc/project/AgentHub/cli\n",
                    "success": True,
                },
                {
                    "type": "function_call",
                    "call_id": "call_fake_2",
                    "name": "exec_command",
                    "arguments": "{\"cmd\":\"pwd\",\"yield_time_ms\":1000,\"max_output_tokens\":200}",
                },
                {
                    "type": "message",
                    "phase": "final_answer",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "当前目录是 `/home/lyc/project/AgentHub/cli`。"}],
                },
            ],
            "status": {
                "thread_id": "live-thread-3",
                "provider_runtime_state": "ready",
            },
            "tool_events": [
                {
                    "name": "exec_command",
                    "ok": True,
                    "summary": "/home/lyc/project/AgentHub/cli\n",
                    "payload": {
                        "command": "/bin/bash -lc 'pwd -P'",
                        "function_call_output": "/home/lyc/project/AgentHub/cli\n",
                        "stdout": "/home/lyc/project/AgentHub/cli\n",
                    },
                }
            ],
            "turn_events": [
                {"type": "turn.started"},
                {
                    "type": "item.started",
                    "item": {
                        "type": "command_execution",
                        "status": "in_progress",
                        "command": "/bin/bash -lc 'pwd -P'",
                        "exit_code": None,
                        "aggregated_output": "",
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "type": "command_execution",
                        "status": "completed",
                        "command": "/bin/bash -lc 'pwd -P'",
                        "exit_code": 0,
                        "aggregated_output": "/home/lyc/project/AgentHub/cli\n",
                    },
                },
                {"type": "turn.completed"},
            ],
        }
    elif prompt == "刚才目录是什么？只回复路径。":
        assert resume_thread_id == "live-thread-3"
        payload = {
            "assistant_text": "`/home/lyc/project/AgentHub/cli`",
            "commentary_text": "",
            "protocol_diagnostics": _protocol_diagnostics(prelude=_PRELUDE_UPDATE),
            "response_items": [
                {
                    "type": "reasoning",
                    "content": None,
                    "summary": [{"type": "summary_text", "text": "placeholder"}],
                    "encrypted_content": "enc-6",
                },
                {
                    "type": "message",
                    "phase": "final_answer",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "`/home/lyc/project/AgentHub/cli`"}],
                },
            ],
            "status": {
                "thread_id": "live-thread-3",
                "provider_runtime_state": "ready",
            },
            "tool_events": [],
            "turn_events": [
                {"type": "turn.started"},
                {"type": "item.completed", "item": {"type": "agent_message", "text": "`/home/lyc/project/AgentHub/cli`"}},
                {"type": "turn.completed"},
            ],
        }
    else:
        raise AssertionError(f"unexpected prompt: {prompt!r}")
    (stdout or io.StringIO()).write(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0

def _fake_live_headless_protocol_mismatch(argv, *, stdout=None, stderr=None, **kwargs):
    del stderr, kwargs
    args = list(argv)
    prompt = args[args.index("--prompt") + 1]
    resume_thread_id = args[args.index("--resume") + 1] if "--resume" in args else ""
    _write_fake_timeline()
    if prompt == "先执行 pwd，再告诉我当前目录。":
        assert resume_thread_id == ""
        payload = {
            "assistant_text": "当前目录是 `/home/lyc/project/AgentHub/cli`。",
            "commentary_text": "",
            "protocol_diagnostics": _protocol_diagnostics(prelude=_PRELUDE_BASELINE),
            "response_items": [
                {
                    "type": "message",
                    "phase": "final_answer",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "当前目录是 `/home/lyc/project/AgentHub/cli`。"}],
                }
            ],
            "status": {
                "thread_id": "live-thread-4",
                "provider_runtime_state": "ready",
            },
            "tool_events": [
                {
                    "name": "exec_command",
                    "ok": True,
                    "summary": "/home/lyc/project/AgentHub/cli\n",
                    "payload": {
                        "command": "/bin/bash -lc pwd",
                        "function_call_output": "/home/lyc/project/AgentHub/cli\n",
                        "stdout": "/home/lyc/project/AgentHub/cli\n",
                    },
                }
            ],
            "turn_events": [
                {"type": "turn.started"},
                {
                    "type": "item.started",
                    "item": {
                        "type": "command_execution",
                        "status": "in_progress",
                        "command": "/bin/bash -lc pwd",
                        "exit_code": None,
                        "aggregated_output": "",
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "type": "command_execution",
                        "status": "completed",
                        "command": "/bin/bash -lc pwd",
                        "exit_code": 0,
                        "aggregated_output": "/home/lyc/project/AgentHub/cli\n",
                    },
                },
                {"type": "turn.completed"},
            ],
        }
    elif prompt == "刚才目录是什么？只回复路径。":
        assert resume_thread_id == "live-thread-4"
        payload = {
            "assistant_text": "`/home/lyc/project/AgentHub/cli`",
            "commentary_text": "",
            "protocol_diagnostics": _protocol_diagnostics(prelude=_PRELUDE_UPDATE),
            "response_items": [
                {
                    "type": "message",
                    "phase": "final_answer",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "`/home/lyc/project/AgentHub/cli`"}],
                }
            ],
            "status": {
                "thread_id": "live-thread-4",
                "provider_runtime_state": "ready",
            },
            "tool_events": [],
            "turn_events": [
                {"type": "turn.started"},
                {"type": "item.completed", "item": {"type": "agent_message", "text": "`/home/lyc/project/AgentHub/cli`"}},
                {"type": "turn.completed"},
            ],
        }
    else:
        raise AssertionError(f"unexpected prompt: {prompt!r}")
    (stdout or io.StringIO()).write(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0

def _fake_live_headless_protocol_unverified(argv, *, stdout=None, stderr=None, **kwargs):
    del stderr, kwargs
    args = list(argv)
    prompt = args[args.index("--prompt") + 1]
    resume_thread_id = args[args.index("--resume") + 1] if "--resume" in args else ""
    _write_fake_timeline()
    if prompt == "先执行 pwd，再告诉我当前目录。":
        assert resume_thread_id == ""
        payload = {
            "assistant_text": "当前目录是 `/home/lyc/project/AgentHub/cli`。",
            "commentary_text": "",
            "protocol_diagnostics": _protocol_diagnostics(
                prelude=_PRELUDE_BASELINE,
                path_kind="host_short_circuit_legacy_fixture",
                source="host",
                provider_used=False,
                parity_evaluable=False,
                reason="legacy_test_fixture",
            ),
            "response_items": [
                {
                    "type": "reasoning",
                    "content": None,
                    "summary": [{"type": "summary_text", "text": "placeholder"}],
                    "encrypted_content": "enc-u1",
                },
                {
                    "type": "message",
                    "phase": "commentary",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "我先跑一下 `pwd`，然后把结果直接告诉你。"}],
                },
                {
                    "type": "function_call",
                    "call_id": "call_host_u1",
                    "name": "exec_command",
                    "arguments": "{\"cmd\":\"/bin/bash -lc pwd\"}",
                },
                {
                    "type": "function_call_output",
                    "call_id": "call_host_u1",
                    "output": "/home/lyc/project/AgentHub/cli\n",
                    "success": True,
                },
                {
                    "type": "function_call",
                    "call_id": "call_fake_u1",
                    "name": "exec_command",
                    "arguments": "{\"cmd\":\"pwd\",\"yield_time_ms\":1000,\"max_output_tokens\":200}",
                },
                {
                    "type": "message",
                    "phase": "final_answer",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "当前目录是 `/home/lyc/project/AgentHub/cli`。"}],
                },
            ],
            "status": {
                "thread_id": "live-thread-u1",
                "provider_runtime_state": "ready",
            },
            "tool_events": [
                {
                    "name": "exec_command",
                    "ok": True,
                    "summary": "/home/lyc/project/AgentHub/cli\n",
                    "payload": {
                        "command": "/bin/bash -lc pwd",
                        "function_call_output": "/home/lyc/project/AgentHub/cli\n",
                        "stdout": "/home/lyc/project/AgentHub/cli\n",
                    },
                }
            ],
            "turn_events": [
                {"type": "turn.started"},
                {
                    "type": "item.started",
                    "item": {
                        "type": "command_execution",
                        "status": "in_progress",
                        "command": "/bin/bash -lc pwd",
                        "exit_code": None,
                        "aggregated_output": "",
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "type": "command_execution",
                        "status": "completed",
                        "command": "/bin/bash -lc pwd",
                        "exit_code": 0,
                        "aggregated_output": "/home/lyc/project/AgentHub/cli\n",
                    },
                },
                {"type": "turn.completed"},
            ],
        }
    elif prompt == "刚才目录是什么？只回复路径。":
        assert resume_thread_id == "live-thread-u1"
        payload = {
            "assistant_text": "`/home/lyc/project/AgentHub/cli`",
            "commentary_text": "",
            "protocol_diagnostics": _protocol_diagnostics(
                prelude=_PRELUDE_UPDATE,
                path_kind="host_short_circuit_legacy_fixture",
                source="host",
                provider_used=False,
                parity_evaluable=False,
                reason="legacy_test_fixture",
            ),
            "response_items": [
                {
                    "type": "reasoning",
                    "content": None,
                    "summary": [{"type": "summary_text", "text": "placeholder"}],
                    "encrypted_content": "enc-u2",
                },
                {
                    "type": "message",
                    "phase": "final_answer",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "`/home/lyc/project/AgentHub/cli`"}],
                },
            ],
            "status": {
                "thread_id": "live-thread-u1",
                "provider_runtime_state": "ready",
            },
            "tool_events": [],
            "turn_events": [
                {"type": "turn.started"},
                {"type": "item.completed", "item": {"type": "agent_message", "text": "`/home/lyc/project/AgentHub/cli`"}},
                {"type": "turn.completed"},
            ],
        }
    else:
        raise AssertionError(f"unexpected prompt: {prompt!r}")
    (stdout or io.StringIO()).write(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0

def _make_fake_live_headless_simple_date_time(
    workspace: Path,
    *,
    host_shell: str,
) -> callable:
    cassette = load_real_case_cassette("simple_date_time_3turn")
    replay_results = run_headless_replay_case(
        cassette,
        output_format="json",
    )
    replay_by_prompt = {item.prompt: item.json_payload for item in replay_results}
    prompt_to_round = {
        result.prompt: round_item
        for result, round_item in zip(replay_results, cassette.rounds)
    }
    environment_snapshot = capture_environment_snapshot(
        cwd=str(workspace),
        shell=host_shell,
        network_access=True,
        current_dt=datetime(2026, 3, 31, 22, 27, 38, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    workspace_snapshot = capture_workspace_snapshot(str(workspace))

    def _fake(argv, *, stdout=None, stderr=None, **kwargs):
        del stderr, kwargs
        args = list(argv)
        prompt = args[args.index("--prompt") + 1]
        resume_thread_id = args[args.index("--resume") + 1] if "--resume" in args else ""
        _write_fake_timeline()
        if prompt != "你好":
            assert resume_thread_id == "portable-live-thread"
        payload = json.loads(json.dumps(replay_by_prompt[prompt], ensure_ascii=False))
        protocol_diagnostics = dict(payload.get("protocol_diagnostics") or {})
        request_contract = dict(protocol_diagnostics.get("request_contract") or {})
        round_item = prompt_to_round[prompt]
        request_contract["environment"] = environment_snapshot
        request_contract["workspace"] = workspace_snapshot
        request_contract["prelude"] = extract_current_turn_prelude_contract(list(round_item.request.get("input") or []))
        protocol_diagnostics["request_contract"] = request_contract
        payload["protocol_diagnostics"] = protocol_diagnostics
        payload["status"] = {
            **dict(payload.get("status") or {}),
            "thread_id": "portable-live-thread",
            "provider_runtime_state": "ready",
        }
        (stdout or io.StringIO()).write(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    return _fake


def _message_text_by_phase(response_items: list[dict[str, object]], *, phase: str) -> str:
    parts: list[str] = []
    for item in list(response_items or []):
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "message":
            continue
        if str(item.get("phase") or "").strip() != phase:
            continue
        for block in list(item.get("content") or []):
            if not isinstance(block, dict):
                continue
            text = str(block.get("text") or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def _fixture_tool_events(case_id: str, *, round_index: int) -> list[dict[str, object]]:
    cassette = load_real_case_cassette(case_id)
    events: list[dict[str, object]] = []
    for tool_call in list(cassette.tool_calls or []):
        if int(tool_call.round_index or 0) != int(round_index):
            continue
        output_item = dict((tool_call.output_items or [{}])[0])
        output_text = str(output_item.get("output") or "")
        payload = {
            "call_id": str(tool_call.call_id or ""),
            "command": str(tool_call.command_text or ""),
        }
        if output_text:
            payload["function_call_output"] = output_text
            payload["stdout"] = output_text
        events.append(
            {
                "name": str(tool_call.tool_name or ""),
                "ok": bool(output_item.get("success", True)),
                "summary": output_text or str(tool_call.command_text or ""),
                "payload": payload,
            }
        )
    return events


def _make_fake_live_headless_fixture_case(case_id: str):
    cassette = load_real_case_cassette(case_id)
    replay_results = run_headless_replay_case(
        cassette,
        output_format="json",
    )
    prompt_to_round = {recorded_user_prompt(round_item): round_item for round_item in list(cassette.rounds or [])}
    payload_by_prompt = {result.prompt: result.to_dict() for result in replay_results}

    def _fake(argv, *, stdout=None, stderr=None, **kwargs):
        del stderr, kwargs
        args = list(argv)
        prompt = args[args.index("--prompt") + 1]
        resume_thread_id = args[args.index("--resume") + 1] if "--resume" in args else ""
        assert resume_thread_id == ""
        round_item = prompt_to_round.get(prompt)
        if round_item is None:
            raise AssertionError(f"unexpected prompt for case {case_id!r}: {prompt!r}")
        replay_payload = payload_by_prompt.get(prompt)
        if replay_payload is None:
            raise AssertionError(f"missing replay payload for case {case_id!r}: {prompt!r}")
        payload = json.loads(json.dumps(replay_payload, ensure_ascii=False))
        working_cwd = str(Path.cwd().resolve())
        environment_snapshot = capture_environment_snapshot(
            cwd=working_cwd,
            shell=detect_host_platform().shell_kind,
            network_access=True,
            current_dt=None,
        )
        workspace_snapshot = capture_workspace_snapshot(working_cwd)
        protocol_diagnostics = _protocol_diagnostics(
            prelude=extract_current_turn_prelude_contract(list(round_item.request.get("input") or []))
        )
        request_contract = dict(protocol_diagnostics.get("request_contract") or {})
        request_contract["environment"] = environment_snapshot
        request_contract["workspace"] = workspace_snapshot
        protocol_diagnostics["request_contract"] = request_contract
        _write_fake_timeline()
        payload["protocol_diagnostics"] = protocol_diagnostics
        payload["status"] = {
            **dict(payload.get("status") or {}),
            "thread_id": f"{case_id}-live-thread",
            "provider_runtime_state": "ready",
        }
        (stdout or io.StringIO()).write(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    return _fake

def test_run_live_headless_ab_case_writes_artifacts_and_passes(tmp_path) -> None:
    report = run_live_headless_ab_case(
        "tool_followup_pwd_memory",
        out_dir=tmp_path,
        invoke_headless=_fake_live_headless_ok,
    )

    assert report.passed is True
    assert report.mismatch_count == 0
    assert Path(report.replay_path).exists()
    assert Path(report.live_results_path).exists()
    assert Path(report.diff_report_path).exists()
    assert Path(report.summary_path).exists()
    assert (tmp_path / "agenthub.live.turn1.stdout.json").exists()
    assert (tmp_path / "agenthub.live.turn1.stderr.txt").exists()
    assert (tmp_path / "agenthub.live.turn1.timeline.jsonl").exists()
    assert (tmp_path / "agenthub.live.turn2.stdout.json").exists()
    assert (tmp_path / "agenthub.live.turn2.timeline.jsonl").exists()
    assert (tmp_path / "agenthub.live.thread_id.txt").read_text(encoding="utf-8") == "live-thread-1"

    diff_payload = json.loads(Path(report.diff_report_path).read_text(encoding="utf-8"))
    assert diff_payload["passed"] is True
    assert diff_payload["mismatch_count"] == 0
    assert diff_payload["behavioral_passed"] is True
    assert diff_payload["protocol_path_passed"] is True
    assert len(diff_payload["turn_diffs"]) == 2
    assert diff_payload["turn_diffs"][0]["replay_response_item_inventory"] == [
        "reasoning",
        "message",
        "function_call",
        "function_call_output",
        "function_call",
        "message",
    ]

def test_run_live_headless_ab_case_reports_mismatch(tmp_path) -> None:
    report = run_live_headless_ab_case(
        "reference_path_followup",
        out_dir=tmp_path,
        invoke_headless=_fake_live_headless_mismatch,
    )

    assert report.passed is False
    assert report.mismatch_count >= 1
    assert len(report.turn_diffs) == 2
    assert any("assistant_text mismatch" in item for item in report.turn_diffs[1].mismatches)
    assert report.behavioral_passed is False
    assert report.protocol_path_passed is False

def test_run_live_headless_ab_case_detects_tool_process_mismatch(tmp_path) -> None:
    report = run_live_headless_ab_case(
        "tool_followup_pwd_memory",
        out_dir=tmp_path,
        invoke_headless=_fake_live_headless_tool_process_mismatch,
    )

    assert report.passed is False
    assert report.mismatch_count >= 1
    assert any("tool_events mismatch" in item for item in report.turn_diffs[0].mismatches)
    assert any("command_execution mismatch" in item for item in report.turn_diffs[0].mismatches)
    assert report.behavioral_passed is False
    assert report.protocol_path_passed is True

def test_run_live_headless_ab_case_reports_protocol_mismatch(tmp_path) -> None:
    report = run_live_headless_ab_case(
        "tool_followup_pwd_memory",
        out_dir=tmp_path,
        invoke_headless=_fake_live_headless_protocol_mismatch,
    )

    assert report.passed is False
    assert report.behavioral_passed is True
    assert report.protocol_path_passed is False
    assert report.protocol_mismatch_count >= 1
    assert any(
        "response_item_inventory mismatch" in item or "response_item_signatures mismatch" in item
        for item in report.turn_diffs[0].protocol_mismatches
    )

def test_run_live_headless_ab_case_reports_protocol_unverified_for_host_short_circuit(tmp_path) -> None:
    report = run_live_headless_ab_case(
        "tool_followup_pwd_memory",
        out_dir=tmp_path,
        invoke_headless=_fake_live_headless_protocol_unverified,
    )

    assert report.passed is False
    assert report.behavioral_passed is True
    assert report.protocol_path_passed is False
    assert report.protocol_path_verdict == "unverified"
    assert any(
        "protocol_path unverified" in item
        for item in report.turn_diffs[0].protocol_mismatches
    )

def test_run_live_headless_ab_case_supports_portable_current_workspace_cases(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "portable-workspace"
    workspace.mkdir()
    (workspace / "AENGTHUB.md").write_text("portable instructions", encoding="utf-8")
    monkeypatch.chdir(workspace)

    report = run_live_headless_ab_case(
        "simple_date_time_3turn",
        out_dir=tmp_path / "portable-out",
        invoke_headless=_make_fake_live_headless_simple_date_time(workspace, host_shell="powershell"),
        host_platform=detect_host_platform(system_name="Windows", sys_platform="win32"),
    )

    assert report.passed is True
    assert report.working_cwd == str(workspace.resolve())
    assert report.host_platform_os == "windows"
    assert report.expected_environment_contract["cwd"] == str(workspace.resolve())
    assert report.expected_environment_contract["current_date"] == "2026-03-31"
    assert report.expected_environment_contract["timezone"] == "Asia/Shanghai"
    assert report.expected_workspace_contract["cwd"] == str(workspace.resolve()).replace("\\", "/")
    assert report.turn_diffs[0].protocol_mismatches == []


def test_timeline_metrics_extract_anthropic_provider_and_tool_stages(tmp_path) -> None:
    timeline_path = tmp_path / "timeline.jsonl"
    _write_fake_timeline_records(
        {"t_rel_ms": 135, "stage": "anthropic_messages.response_raw"},
        {"t_rel_ms": 410, "stage": "turn_engine.tool.provisional_started.emit"},
        {"t_rel_ms": 450, "stage": "turn_engine.tool.execute.begin"},
        path=timeline_path,
    )

    assert _timeline_metrics_from_path(timeline_path) == {
        "time_to_first_event_ms": 135,
        "time_to_first_tool_ms": 410,
    }


def test_run_live_headless_ab_case_persists_timeline_metrics_into_live_payload(tmp_path) -> None:
    cassette = load_real_case_cassette("shell_pwd")
    replay_result = run_headless_replay_case(cassette, output_format="json")[0]
    replay_payload = replay_result.to_dict()
    replay_payload["protocol_diagnostics"] = dict((replay_result.json_payload or {}).get("protocol_diagnostics") or {})

    def _fake(argv, *, stdout=None, stderr=None, **kwargs):
        del argv, stderr, kwargs
        _write_fake_timeline_records(
            {"t_rel_ms": 123, "stage": "anthropic_messages.response_raw"},
            {"t_rel_ms": 456, "stage": "turn_engine.tool.provisional_started.emit"},
        )
        payload = json.loads(json.dumps(replay_payload, ensure_ascii=False))
        payload["status"] = {
            **dict(payload.get("status") or {}),
            "thread_id": "shell-timing-live",
            "provider_runtime_state": "ready",
        }
        (stdout or io.StringIO()).write(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    report = run_live_headless_ab_case(
        "shell_pwd",
        out_dir=tmp_path / "timing-case",
        invoke_headless=_fake,
    )

    live_payload = json.loads(Path(report.live_results_path).read_text(encoding="utf-8"))[0]
    assert report.behavioral_passed is True
    assert live_payload["status"]["time_to_first_event_ms"] == 123
    assert live_payload["status"]["time_to_first_tool_ms"] == 456


def test_operator_live_case_pack_registers_recorded_surfaces() -> None:
    case_ids = list_operator_live_case_ids()
    specs = [get_real_case_spec(case_id) for case_id in case_ids]
    pack = get_real_case_pack_spec("operator_live_surface_v1")

    assert case_ids == ["shell_pwd", "write_readme", "edit_settings", "search_weather", "delegate_probe"]
    assert [spec.surface_family for spec in specs] == ["shell", "write", "edit", "search", "agent_delegation"]
    assert {spec.source_kind for spec in specs} == {"recorded"}
    assert {spec.case_pack for spec in specs} == {"operator_live_surface_v1"}
    assert pack.current_state == "full_operator_live_pack"
    assert pack.target_state == "full_operator_live_pack"
    assert all(spec.cassette_dir for spec in specs)
    assert pack.upgrade_candidates == ()


def test_operator_live_shell_case_loads_recorded_cassette() -> None:
    shell_case = get_real_case_spec("shell_pwd")
    pack = get_real_case_pack_spec(shell_case.case_pack)
    cassette = load_real_case_cassette("shell_pwd")

    assert shell_case.source_kind == "recorded"
    assert cassette.manifest.session.provider == "anthropic"
    assert cassette.manifest.session.cwd == "/tmp/agenthub_operator_live/shell_pwd"
    assert pack.current_state == "full_operator_live_pack"


def test_run_live_headless_ab_case_supports_operator_surface_pack_cases(tmp_path) -> None:
    for case_id in list_operator_live_case_ids():
        report = run_live_headless_ab_case(
            case_id,
            out_dir=tmp_path / case_id,
            invoke_headless=_make_fake_live_headless_fixture_case(case_id),
        )

        spec = get_real_case_spec(case_id)
        assert report.passed is True
        assert report.mismatch_count == 0
        assert report.case_source_kind == spec.source_kind
        assert report.surface_family == spec.surface_family
        assert report.case_pack == spec.case_pack
        assert report.recording_prefix_used == str(Path(spec.cassette_dir).resolve())
        assert report.recording_variant_source == "recorded_cassette"
        assert Path(report.summary_path).exists()

def test_run_live_headless_ab_case_rejects_incompatible_host_for_platform_sensitive_case(tmp_path) -> None:
    try:
        run_live_headless_ab_case(
            "tool_followup_pwd_memory",
            out_dir=tmp_path,
            invoke_headless=_fake_live_headless_ok,
            host_platform=detect_host_platform(system_name="Windows", sys_platform="win32"),
        )
    except ValueError as exc:
        assert "not supported on host windows" in str(exc)
    else:
        raise AssertionError("expected incompatible host validation error")

def test_live_headless_ab_main_lists_current_host_compatible_cases() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = live_headless_ab_main(
        ["--list-live-compatible-cases"],
        stdout=stdout,
        stderr=stderr,
        invoke_headless=_fake_live_headless_ok,
    )

    assert code == 0
    assert stderr.getvalue() == ""
    assert "tool_followup_pwd_memory" in stdout.getvalue()

def test_live_headless_ab_main_returns_nonzero_on_mismatch(tmp_path) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = live_headless_ab_main(
        ["--case", "reference_path_followup", "--out-dir", str(tmp_path)],
        stdout=stdout,
        stderr=stderr,
        invoke_headless=_fake_live_headless_mismatch,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 3
    assert stderr.getvalue() == ""
    assert payload["passed"] is False
    assert payload["mismatch_count"] >= 1

def test_payload_response_item_signatures_compare_provider_native_payload_fields() -> None:
    baseline = {
        "response_items": [
            {
                "type": "web_search_call",
                "status": "completed",
                "action": {
                    "type": "search",
                    "query": 'time: {"utc_offset":"+08:00"}',
                    "queries": ['time: {"utc_offset":"+08:00"}'],
                },
            }
        ]
    }
    changed = {
        "response_items": [
            {
                "type": "web_search_call",
                "status": "completed",
                "action": {
                    "type": "search",
                    "query": 'time: {"utc_offset":"+09:00"}',
                    "queries": ['time: {"utc_offset":"+09:00"}'],
                },
            }
        ]
    }

    assert _payload_response_item_signatures(baseline) == [
        {
            "type": "web_search_call",
            "action": {
                "queries": ['time: {"utc_offset":"+08:00"}'],
                "query": 'time: {"utc_offset":"+08:00"}',
                "type": "search",
            },
            "status": "completed",
        }
    ]
    assert _payload_response_item_signatures(baseline) != _payload_response_item_signatures(changed)


def test_payload_response_item_signatures_ignore_message_status_and_output_text_metadata() -> None:
    baseline = {
        "response_items": [
            {
                "type": "message",
                "phase": "final_answer",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "记住了"}],
            }
        ]
    }
    expanded = {
        "response_items": [
            {
                "type": "message",
                "status": "completed",
                "phase": "final_answer",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "记住了",
                        "annotations": [],
                        "logprobs": [],
                    }
                ],
            }
        ]
    }

    assert _payload_response_item_signatures(baseline) == _payload_response_item_signatures(expanded)


def test_payload_response_item_signatures_treat_reasoning_null_content_as_empty() -> None:
    baseline = {
        "response_items": [
            {
                "type": "reasoning",
                "encrypted_content": "enc-1",
            }
        ]
    }
    expanded = {
        "response_items": [
            {
                "type": "reasoning",
                "content": None,
                "summary": [{"type": "summary_text", "text": "placeholder"}],
                "encrypted_content": "enc-1",
            }
        ]
    }

    assert _payload_response_item_signatures(baseline) == _payload_response_item_signatures(expanded)


def test_payload_response_item_signatures_treat_shell_output_envelope_as_plain_output_text() -> None:
    baseline = {
        "response_items": [
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": json.dumps(
                    {
                        "command": "/bin/bash -lc pwd",
                        "aggregated_output": "/home/lyc/project/AgentHub/cli\n",
                        "exit_code": 0,
                        "status": "completed",
                    },
                    ensure_ascii=False,
                ),
                "success": True,
            }
        ]
    }
    expanded = {
        "response_items": [
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": "/home/lyc/project/AgentHub/cli\n",
                "success": True,
            }
        ]
    }

    assert _payload_response_item_signatures(baseline) == _payload_response_item_signatures(expanded)


def test_operator_benchmark_fixture_prefers_structured_lifecycle_snapshot_over_free_text() -> None:
    cases = (
        (
            PromptResponse(
                user_text="/agent_workflow ag_fixture",
                assistant_text=(
                    "delegated workflow\n"
                    "agent_id=ag_fixture\n"
                    "status=completed\n"
                    "completion_state=adopted\n"
                    "adopted=true\n"
                ),
                tool_events=[
                    ToolEvent(
                        name="agent_workflow",
                        ok=True,
                        summary="workflow_state=completed",
                        payload={
                            "agent_id": "ag_fixture",
                            "role": "teammate",
                            "status": "completed",
                            "workflow_state": "completed",
                            "completion_state": "ready_to_adopt",
                            "adopted": False,
                        },
                    )
                ],
            ),
            {
                "operator_evidence_subject_kind": "agent",
                "operator_evidence_subject_id": "ag_fixture",
                "operator_evidence_lifecycle_state": "returned",
                "operator_evidence_review_state": "review_pending",
                "operator_evidence_state_source": "structured",
                "operator_evidence_subject_source": "structured",
            },
        ),
        (
            PromptResponse(
                user_text="/background_task_status bg_fixture",
                assistant_text=(
                    "background task status\n"
                    "task_id=bg_fixture\n"
                    "status=completed\n"
                    "result_state=pending_review\n"
                    "final_apply_state=pending\n"
                ),
                tool_events=[
                    ToolEvent(
                        name="background_task_status",
                        ok=True,
                        summary="status=completed",
                        payload={
                            "task_id": "bg_fixture",
                            "status": "completed",
                            "workflow_state": "completed",
                            "result_state": "pending_review",
                            "final_apply_state": "blocked",
                        },
                    )
                ],
            ),
            {
                "operator_evidence_subject_kind": "task",
                "operator_evidence_subject_id": "bg_fixture",
                "operator_evidence_lifecycle_state": "returned",
                "operator_evidence_review_state": "blocked",
                "operator_evidence_state_source": "structured",
                "operator_evidence_subject_source": "structured",
            },
        ),
        (
            PromptResponse(
                user_text="/background_task_status sh_fixture",
                assistant_text=(
                    "background task status\n"
                    "task_id=sh_fixture\n"
                    "status=completed\n"
                    "completion_state=ready_to_adopt\n"
                    "adopted=false\n"
                ),
                tool_events=[
                    ToolEvent(
                        name="background_task_status",
                        ok=True,
                        summary="status=completed",
                        payload={
                            "task_id": "sh_fixture",
                            "status": "completed",
                            "workflow_state": "completed",
                            "result_state": "adopted",
                        },
                    )
                ],
            ),
            {
                "operator_evidence_subject_kind": "task",
                "operator_evidence_subject_id": "sh_fixture",
                "operator_evidence_lifecycle_state": "adopted",
                "operator_evidence_review_state": "",
                "operator_evidence_state_source": "structured",
                "operator_evidence_subject_source": "structured",
            },
        ),
    )

    for response, expected in cases:
        fixture = _operator_benchmark_fixture(response)
        assert fixture == expected
