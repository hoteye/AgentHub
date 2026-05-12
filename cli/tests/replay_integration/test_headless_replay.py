from __future__ import annotations

import io
import json

from cli.agent_cli.main import main as agenthub_main
from cli.replay_integration.headless_replay import main as headless_replay_main
from cli.replay_integration.headless_replay import run_headless_replay_case
from cli.replay_integration.real_cases import list_real_case_ids, load_real_case_cassette
from cli.replay_integration.runtime_replay import build_runtime_for_replay


def test_run_headless_replay_case_replays_real_pwd_followup_in_json_mode() -> None:
    results = run_headless_replay_case(
        load_real_case_cassette("tool_followup_pwd_memory"),
        output_format="json",
    )

    assert [item.turn_index for item in results] == [1, 2]
    assert [item.exit_code for item in results] == [0, 0]
    assert [item.json_payload["assistant_text"] for item in results] == [
        "当前目录是 `/home/lyc/project/AgentHub/cli`。",
        "`/home/lyc/project/AgentHub/cli`",
    ]
    assert [item.get("type") for item in results[0].json_payload["response_items"]] == [
        "reasoning",
        "message",
        "function_call",
        "function_call",
        "function_call_output",
        "message",
    ]
    assert [
        item.json_payload["protocol_diagnostics"]["protocol_path"]["kind"] for item in results
    ] == [
        "provider_replay_loop",
        "provider_replay_loop",
    ]
    assert results[0].json_payload["tool_events"][0]["name"] == "exec_command"
    assert results[0].json_payload["tool_events"][0]["ok"] is True
    assert results[1].json_payload["tool_events"] == []


def test_run_headless_replay_case_can_return_late_turn_after_internal_priming() -> None:
    results = run_headless_replay_case(
        load_real_case_cassette("memory_5turn_profile"),
        output_format="json",
        turn_indices=[5],
    )

    assert len(results) == 1
    assert results[0].turn_index == 5
    assert results[0].exit_code == 0
    assert (
        results[0].json_payload["assistant_text"]
        == "你叫王敏，在上海，是测试工程师，你的项目代号是天枢。"
    )


def test_run_headless_replay_case_replays_jsonl_with_stable_thread_id() -> None:
    results = run_headless_replay_case(
        load_real_case_cassette("tool_followup_pwd_memory"),
        output_format="jsonl",
    )

    assert len(results) == 2
    first_events = results[0].jsonl_events
    second_events = results[1].jsonl_events
    assert first_events[0]["type"] == "thread.started"
    assert second_events[0]["type"] == "thread.started"
    assert first_events[0]["thread_id"] == "019d4310-cac1-7a61-8ce6-dce8d23750f6"
    assert second_events[0]["thread_id"] == first_events[0]["thread_id"]
    assert any(
        event["type"] == "item.started" and event["item"]["type"] == "command_execution"
        for event in first_events
    )
    assert any(
        event["type"] == "item.completed"
        and event["item"]["type"] == "agent_message"
        and "/home/lyc/project/AgentHub/cli" in str(event["item"]["text"])
        for event in second_events
    )


def test_headless_replay_cli_lists_supported_cases() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = headless_replay_main(["--list-cases"], stdout=stdout, stderr=stderr)

    assert code == 0
    assert stderr.getvalue() == ""
    assert stdout.getvalue().strip().splitlines() == list_real_case_ids()


def test_headless_replay_cli_runs_real_case_in_json_mode() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = headless_replay_main(
        ["--case", "reference_path_followup", "--format", "json"],
        stdout=stdout,
        stderr=stderr,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert stderr.getvalue() == ""
    assert len(payload) == 2
    assert payload[0]["assistant_text"] == "记住了"
    assert payload[1]["assistant_text"] == "/srv/app"


def test_run_headless_replay_case_exposes_provider_native_response_items() -> None:
    results = run_headless_replay_case(
        load_real_case_cassette("simple_date_time_3turn"),
        output_format="json",
        turn_indices=[3],
    )

    assert len(results) == 1
    payload = results[0].to_dict()
    assert payload["assistant_text"] == "现在北京时间是 `2026年3月31日 22:27:38`。"
    assert [item.get("type") for item in payload["response_items"]] == [
        "reasoning",
        "web_search_call",
        "reasoning",
        "message",
    ]
    assert payload["response_items"][1]["action"]["query"] == 'time: {"utc_offset":"+08:00"}'


def test_headless_runtime_keeps_runtime_replay_planner_override() -> None:
    runtime = build_runtime_for_replay(load_real_case_cassette("tool_followup_pwd_memory"))
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = agenthub_main(
        [
            "--headless",
            "--prompt",
            "先执行 pwd，再告诉我当前目录。",
            "--approval-policy",
            "never",
            "--json",
        ],
        runtime=runtime,
        stdout=stdout,
        stderr=stderr,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert stderr.getvalue() == ""
    assert payload["protocol_diagnostics"]["protocol_path"]["kind"] == "provider_replay_loop"
    assert [item.get("type") for item in payload["response_items"]] == [
        "reasoning",
        "message",
        "function_call",
        "function_call",
        "function_call_output",
        "message",
    ]
    assert type(runtime.agent._planner).__name__ == "RuntimeReplayPlanner"
    assert runtime.agent._planner.public_summary()["planner_kind"] == "runtime_replay"
