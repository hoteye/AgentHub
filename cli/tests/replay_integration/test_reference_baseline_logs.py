from __future__ import annotations

import hashlib
from pathlib import Path

from cli.replay_integration.reference_baseline_logs import (
    ReferenceBaselineTurnLog,
    build_cassette_from_reference_baseline_turn_logs,
)

ROOT = Path(__file__).resolve().parents[3]


def _resolved_log_root() -> Path:
    base = ROOT / "docs" / "ab_acceptance"
    preferred = base / "reference_logs"
    if preferred.exists():
        return preferred
    candidates = sorted(path for path in base.iterdir() if path.is_dir() and path.name.endswith("_logs"))
    if candidates:
        return candidates[0]
    return preferred


LOG_ROOT = _resolved_log_root()


def _resolve_prefix(prefix: str, turn_count: int) -> str:
    probe = LOG_ROOT / f"{prefix}_turn1.stdout.jsonl"
    if probe.exists():
        return prefix
    wildcard = str(prefix or "").replace("reference", "*")
    if wildcard == prefix:
        return prefix
    for stdout_path in sorted(LOG_ROOT.glob(f"{wildcard}_turn1.stdout.jsonl")):
        candidate = stdout_path.name[: -len("_turn1.stdout.jsonl")]
        if all((LOG_ROOT / f"{candidate}_turn{i}.stdout.jsonl").exists() for i in range(1, turn_count + 1)):
            return candidate
    return prefix

def _turn_logs(prefix: str, turn_count: int) -> list[ReferenceBaselineTurnLog]:
    resolved_prefix = _resolve_prefix(prefix, turn_count)
    return [
        ReferenceBaselineTurnLog(
            stdout_path=LOG_ROOT / f"{resolved_prefix}_turn{turn_index}.stdout.jsonl",
            stderr_path=LOG_ROOT / f"{resolved_prefix}_turn{turn_index}.stderr.jsonl",
        )
        for turn_index in range(1, turn_count + 1)
    ]

def _state_probe_turn_logs() -> list[ReferenceBaselineTurnLog]:
    return _turn_logs("20260331_multiturn_state_probe", 3)

def _real_pwd_followup_turn_logs() -> list[ReferenceBaselineTurnLog]:
    return _turn_logs("20260331_real_pwd_followup", 2)

def _real_error_recovery_turn_logs() -> list[ReferenceBaselineTurnLog]:
    return _turn_logs("20260331_real_error_recovery", 2)

def _real_memory_2turn_name_turn_logs() -> list[ReferenceBaselineTurnLog]:
    return _turn_logs("20260331_real_memory_2turn_name", 2)

def _real_reference_person_pronoun_turn_logs() -> list[ReferenceBaselineTurnLog]:
    return _turn_logs("20260331_real_reference_person_pronoun", 2)

def _real_history_compression_summary_turn_logs() -> list[ReferenceBaselineTurnLog]:
    return _turn_logs("20260331_real_history_compression_summary", 3)

def _real_reference_path_followup_turn_logs() -> list[ReferenceBaselineTurnLog]:
    return _turn_logs("20260331_real_reference_path_followup", 2)

def _real_reference_variable_value_turn_logs() -> list[ReferenceBaselineTurnLog]:
    return _turn_logs("20260331_real_reference_variable_value", 2)

def _real_memory_3turn_facts_turn_logs() -> list[ReferenceBaselineTurnLog]:
    return _turn_logs("20260331_real_memory_3turn_facts", 3)

def _real_memory_5turn_profile_turn_logs() -> list[ReferenceBaselineTurnLog]:
    return _turn_logs("20260331_real_memory_5turn_profile", 5)

def _real_simple_date_time_3turn_turn_logs() -> list[ReferenceBaselineTurnLog]:
    return _turn_logs("20260331_real_simple_date_time_3turn", 3)

def test_build_cassette_from_reference_baseline_turn_logs_extracts_multiturn_session() -> None:
    cassette = build_cassette_from_reference_baseline_turn_logs(
        _state_probe_turn_logs(),
        name="reference-ref-state-probe",
    )

    assert cassette.manifest.name == "reference-ref-state-probe"
    assert cassette.manifest.session.provider == "openai"
    assert cassette.manifest.session.model == "gpt-5.4"
    assert cassette.manifest.session.thread_id == "019d4137-a2a5-7060-8279-aa38319ac9f6"
    assert cassette.manifest.environment_snapshot["cwd"] == "/home/lyc/project/AgentHub/cli"
    assert cassette.manifest.workspace_snapshot["instructions_digest"]
    assert len(cassette.rounds) == 3
    assert cassette.rounds[0].response["output_text"] == "记住了"
    assert cassette.rounds[1].response["output_text"] == "张三"
    assert cassette.rounds[2].response["output_text"] == "你告诉我你叫张三，我回复“记住了”。"
    assert cassette.rounds[0].request_fingerprint
    assert not cassette.tool_calls

    first_prompt = cassette.rounds[0].request["input"][-1]["content"][0]["text"]
    second_prompt = cassette.rounds[1].request["input"][-1]["content"][0]["text"]
    third_prompt = cassette.rounds[2].request["input"][-1]["content"][0]["text"]
    assert first_prompt == "我叫张三。请只回复“记住了”。"
    assert second_prompt == "我刚才说我叫什么？只回复名字。"
    assert third_prompt == "把我们前两轮对话压缩成一句话。"

def test_build_cassette_from_real_pwd_followup_logs_extracts_tool_history() -> None:
    cassette = build_cassette_from_reference_baseline_turn_logs(
        _real_pwd_followup_turn_logs(),
        name="real-pwd-followup",
        case_id="tool_followup_pwd_memory",
        parity_targets=("behavioral_parity_required", "protocol_path_parity_required"),
        coverage_tags=("shell_tool_followup", "tool_loop"),
    )

    assert cassette.manifest.name == "real-pwd-followup"
    assert cassette.manifest.case_id == "tool_followup_pwd_memory"
    assert cassette.manifest.parity_targets == ["behavioral_parity_required", "protocol_path_parity_required"]
    assert cassette.manifest.coverage_tags == ["shell_tool_followup", "tool_loop"]
    assert cassette.manifest.session.thread_id == "019d4310-cac1-7a61-8ce6-dce8d23750f6"
    assert cassette.manifest.environment_snapshot["cwd"] == "/home/lyc/project/AgentHub/cli"
    assert len(cassette.rounds) == 2
    assert len(cassette.tool_calls) == 1
    assert cassette.rounds[0].request_item_inventory == ["message", "message", "message"]
    assert cassette.rounds[0].response_item_inventory == ["reasoning", "message", "function_call", "message"]

    tool_call = cassette.tool_calls[0]
    assert tool_call.round_index == 1
    assert tool_call.command_text == "/bin/bash -lc pwd"
    assert tool_call.output_items[0]["success"] is True
    assert tool_call.output_items[0]["output"] == "/home/lyc/project/AgentHub/cli\n"
    assert cassette.rounds[0].response["output_text"] == "当前目录是 `/home/lyc/project/AgentHub/cli`。"
    assert cassette.rounds[1].response["output_text"] == "`/home/lyc/project/AgentHub/cli`"

    second_round_input = cassette.rounds[1].request["input"]
    first_prompt = cassette.rounds[0].request["input"][-1]["content"][0]["text"]
    second_prompt = second_round_input[-1]["content"][0]["text"]
    function_call = next(item for item in second_round_input if item.get("type") == "function_call")
    function_output = next(item for item in second_round_input if item.get("type") == "function_call_output")

    assert first_prompt == "先执行 pwd，再告诉我当前目录。"
    assert second_prompt == "刚才目录是什么？只回复路径。"
    assert function_call["name"] == "exec_command"
    assert function_call["arguments"] == '{"cmd":"pwd","yield_time_ms":1000,"max_output_tokens":200}'
    assert "Process exited with code 0" in str(function_output["output"])
    assert "/home/lyc/project/AgentHub/cli" in str(function_output["output"])

def test_build_cassette_from_real_error_recovery_logs_extracts_failed_tool_history() -> None:
    cassette = build_cassette_from_reference_baseline_turn_logs(
        _real_error_recovery_turn_logs(),
        name="real-error-recovery",
    )

    assert cassette.manifest.name == "real-error-recovery"
    assert cassette.manifest.session.thread_id == "019d4312-7ea2-7353-9fdf-17dd4ad1caf8"
    assert cassette.manifest.environment_snapshot["cwd"] == "/home/lyc/project/AgentHub/cli"
    assert len(cassette.rounds) == 2
    assert len(cassette.tool_calls) == 1

    tool_call = cassette.tool_calls[0]
    assert tool_call.round_index == 1
    assert tool_call.command_text == "/bin/bash -lc 'ls /missing'"
    assert tool_call.output_items[0]["success"] is False
    assert tool_call.output_items[0]["output"] == "ls: cannot access '/missing': No such file or directory\n"
    assert (
        cassette.rounds[0].response["output_text"]
        == "结果如下：\n\n- 命令：`ls /missing`\n- 退出码：`2`\n- 输出：`ls: cannot access '/missing': No such file or directory`\n\n也就是说，系统里没有 `/missing` 这个路径。"
    )
    assert (
        cassette.rounds[1].response["output_text"]
        == "因为系统中不存在 `/missing` 这个路径，所以 `ls /missing` 以 “No such file or directory” 失败了。"
    )

    second_round_input = cassette.rounds[1].request["input"]
    first_prompt = cassette.rounds[0].request["input"][-1]["content"][0]["text"]
    second_prompt = second_round_input[-1]["content"][0]["text"]
    function_call = next(item for item in second_round_input if item.get("type") == "function_call")
    function_output = next(item for item in second_round_input if item.get("type") == "function_call_output")

    assert first_prompt == "先执行 ls /missing，再告诉我结果。"
    assert second_prompt == "上一轮失败的原因是什么？只回复一句话。"
    assert function_call["name"] == "exec_command"
    assert (
        function_call["arguments"]
        == '{"cmd":"ls /missing","workdir":"/home/lyc/project/AgentHub/cli","yield_time_ms":1000,"max_output_tokens":300}'
    )
    assert "Process exited with code 2" in str(function_output["output"])
    assert "No such file or directory" in str(function_output["output"])

def test_build_cassette_from_real_memory_2turn_name_logs_extracts_multiturn_session() -> None:
    cassette = build_cassette_from_reference_baseline_turn_logs(
        _real_memory_2turn_name_turn_logs(),
        name="real-memory-2turn-name",
    )

    assert cassette.manifest.name == "real-memory-2turn-name"
    assert cassette.manifest.session.thread_id == "019d433d-80ef-7f83-8a85-258e8a9fe3d8"
    assert cassette.manifest.environment_snapshot["cwd"] == "/home/lyc/project/AgentHub/cli"
    assert len(cassette.rounds) == 2
    assert not cassette.tool_calls
    assert cassette.rounds[0].response["output_text"] == "记住了"
    assert cassette.rounds[1].response["output_text"] == "张三"
    assert cassette.rounds[0].request["input"][-1]["content"][0]["text"] == "我叫张三。请只回复“记住了”。"
    assert cassette.rounds[1].request["input"][-1]["content"][0]["text"] == "我刚才说我叫什么？只回复名字。"

def test_build_cassette_from_real_reference_person_pronoun_logs_extracts_multiturn_session() -> None:
    cassette = build_cassette_from_reference_baseline_turn_logs(
        _real_reference_person_pronoun_turn_logs(),
        name="real-reference-person-pronoun",
    )

    assert cassette.manifest.name == "real-reference-person-pronoun"
    assert cassette.manifest.session.thread_id == "019d433f-245e-70d3-a9fe-2187388f495f"
    assert cassette.manifest.environment_snapshot["cwd"] == "/home/lyc/project/AgentHub/cli"
    assert len(cassette.rounds) == 2
    assert not cassette.tool_calls
    assert cassette.rounds[0].response["output_text"] == "记住了"
    assert cassette.rounds[1].response["output_text"] == "李雷"
    assert cassette.rounds[0].request["input"][-1]["content"][0]["text"] == "新同事叫李雷。请只回复“记住了”。"
    assert cassette.rounds[1].request["input"][-1]["content"][0]["text"] == "他叫什么？只回复名字。"

def test_build_cassette_from_real_history_compression_summary_logs_extracts_multiturn_session() -> None:
    cassette = build_cassette_from_reference_baseline_turn_logs(
        _real_history_compression_summary_turn_logs(),
        name="real-history-compression-summary",
    )

    assert cassette.manifest.name == "real-history-compression-summary"
    assert cassette.manifest.session.thread_id == "019d4340-85d8-7a82-97fd-9215efd70f9c"
    assert cassette.manifest.environment_snapshot["cwd"] == "/home/lyc/project/AgentHub/cli"
    assert len(cassette.rounds) == 3
    assert not cassette.tool_calls
    assert cassette.rounds[0].response["output_text"] == "记住了"
    assert cassette.rounds[1].response["output_text"] == "记住了"
    assert cassette.rounds[2].response["output_text"] == "我叫张三，喜欢 Go。"
    assert cassette.rounds[0].request["input"][-1]["content"][0]["text"] == "我叫张三。请只回复“记住了”。"
    assert cassette.rounds[1].request["input"][-1]["content"][0]["text"] == "我喜欢 Go。请只回复“记住了”。"
    assert cassette.rounds[2].request["input"][-1]["content"][0]["text"] == "把前两轮压缩成一句话。只输出结果。"

def test_build_cassette_from_real_reference_path_followup_logs_extracts_multiturn_session() -> None:
    cassette = build_cassette_from_reference_baseline_turn_logs(
        _real_reference_path_followup_turn_logs(),
        name="real-reference-path-followup",
    )

    assert cassette.manifest.name == "real-reference-path-followup"
    assert cassette.manifest.session.thread_id == "019d4346-0032-70b2-a636-db61f44c5aad"
    assert cassette.manifest.environment_snapshot["cwd"] == "/home/lyc/project/AgentHub/cli"
    assert len(cassette.rounds) == 2
    assert not cassette.tool_calls
    assert cassette.rounds[0].response["output_text"] == "记住了"
    assert cassette.rounds[1].response["output_text"] == "/srv/app"
    assert (
        cassette.rounds[0].request["input"][-1]["content"][0]["text"]
        == "项目目录是 /srv/app。请记住这个路径，并只回复“记住了”。"
    )
    assert cassette.rounds[1].request["input"][-1]["content"][0]["text"] == "刚才那个目录是什么？只回复路径。"

def test_build_cassette_from_real_reference_variable_value_logs_extracts_multiturn_session() -> None:
    cassette = build_cassette_from_reference_baseline_turn_logs(
        _real_reference_variable_value_turn_logs(),
        name="real-reference-variable-value",
    )

    assert cassette.manifest.name == "real-reference-variable-value"
    assert cassette.manifest.session.thread_id == "019d4346-7a20-7f61-94a8-77eaf6de1b12"
    assert cassette.manifest.environment_snapshot["cwd"] == "/home/lyc/project/AgentHub/cli"
    assert len(cassette.rounds) == 2
    assert not cassette.tool_calls
    assert cassette.rounds[0].response["output_text"] == "记住了"
    assert cassette.rounds[1].response["output_text"] == "https://api.example.com/v1"
    assert (
        cassette.rounds[0].request["input"][-1]["content"][0]["text"]
        == "变量 API_BASE 的值是 https://api.example.com/v1 。请只回复“记住了”。"
    )
    assert cassette.rounds[1].request["input"][-1]["content"][0]["text"] == "API_BASE 是什么？只回复值。"

def test_build_cassette_from_real_memory_3turn_facts_logs_extracts_multiturn_session() -> None:
    cassette = build_cassette_from_reference_baseline_turn_logs(
        _real_memory_3turn_facts_turn_logs(),
        name="real-memory-3turn-facts",
    )

    assert cassette.manifest.name == "real-memory-3turn-facts"
    assert cassette.manifest.session.thread_id == "019d4346-efc1-7433-9ee5-fc363661e677"
    assert cassette.manifest.environment_snapshot["cwd"] == "/home/lyc/project/AgentHub/cli"
    assert len(cassette.rounds) == 3
    assert not cassette.tool_calls
    assert cassette.rounds[0].response["output_text"] == "记住了"
    assert cassette.rounds[1].response["output_text"] == "记住了"
    assert cassette.rounds[2].response["output_text"] == "你叫李雷，在杭州工作。"
    assert cassette.rounds[0].request["input"][-1]["content"][0]["text"] == "我叫李雷。请只回复“记住了”。"
    assert cassette.rounds[1].request["input"][-1]["content"][0]["text"] == "我在杭州工作。请只回复“记住了”。"
    assert cassette.rounds[2].request["input"][-1]["content"][0]["text"] == "我叫什么，在哪里工作？只用一句话回答。"

def test_build_cassette_from_real_memory_5turn_profile_logs_extracts_multiturn_session() -> None:
    cassette = build_cassette_from_reference_baseline_turn_logs(
        _real_memory_5turn_profile_turn_logs(),
        name="real-memory-5turn-profile",
    )

    assert cassette.manifest.name == "real-memory-5turn-profile"
    assert cassette.manifest.session.thread_id == "019d4347-ccce-72a2-98fb-089be8d816a8"
    assert cassette.manifest.environment_snapshot["cwd"] == "/home/lyc/project/AgentHub/cli"
    assert len(cassette.rounds) == 5
    assert not cassette.tool_calls
    assert [round_.response["output_text"] for round_ in cassette.rounds] == [
        "记住了",
        "记住了",
        "记住了",
        "记住了",
        "你叫王敏，在上海，是测试工程师，你的项目代号是天枢。",
    ]
    assert cassette.rounds[0].request["input"][-1]["content"][0]["text"] == "我叫王敏。请只回复“记住了”。"
    assert cassette.rounds[1].request["input"][-1]["content"][0]["text"] == "我在上海。请只回复“记住了”。"
    assert cassette.rounds[2].request["input"][-1]["content"][0]["text"] == "我是测试工程师。请只回复“记住了”。"
    assert cassette.rounds[3].request["input"][-1]["content"][0]["text"] == "我的项目代号是天枢。请只回复“记住了”。"
    assert cassette.rounds[4].request["input"][-1]["content"][0]["text"] == "把我前四轮说的信息合成一句话。"

def test_build_cassette_from_real_simple_date_time_logs_preserves_provider_native_items() -> None:
    cassette = build_cassette_from_reference_baseline_turn_logs(
        _real_simple_date_time_3turn_turn_logs(),
        name="real-simple-date-time-3turn",
        case_id="simple_date_time_3turn",
        parity_targets=("behavioral_parity_required", "protocol_path_parity_required"),
        coverage_tags=("provider_native_search", "time_query", "environment_sensitive"),
    )

    assert cassette.manifest.name == "real-simple-date-time-3turn"
    assert cassette.manifest.case_id == "simple_date_time_3turn"
    assert cassette.manifest.parity_targets == ["behavioral_parity_required", "protocol_path_parity_required"]
    assert cassette.manifest.coverage_tags == ["provider_native_search", "time_query", "environment_sensitive"]
    assert cassette.manifest.session.thread_id == "019d4447-b0e2-7461-9af1-d14aa77a855c"
    assert len(cassette.rounds) == 3

    round3 = cassette.rounds[2]
    output_types = [str(item.get("type") or "") for item in list(round3.response.get("output") or [])]
    assert round3.request_item_inventory[-3:] == ["reasoning", "message", "message"]
    assert round3.response_item_inventory == ["reasoning", "web_search_call", "reasoning", "message"]
    assert output_types == ["reasoning", "web_search_call", "reasoning", "message"]
    assert round3.response["output"][1]["action"]["query"] == 'time: {"utc_offset":"+08:00"}'
    assert round3.response["output_text"] == "现在北京时间是 `2026年3月31日 22:27:38`。"

    response_event_items = [
        dict(event.get("item") or {})
        for event in list(round3.response_events or [])
        if isinstance(event, dict) and isinstance(event.get("item"), dict)
    ]
    web_search_event_types = [
        str(item.get("type") or "")
        for item in response_event_items
        if str(item.get("type") or "") == "web_search"
    ]
    assert web_search_event_types == ["web_search", "web_search"]
    workspace_text = str(cassette.manifest.workspace_snapshot.get("instructions_text") or "")
    assert workspace_text.startswith("# AGENTS.md instructions for /home/lyc/project/AgentHub/cli")
    assert cassette.manifest.workspace_snapshot["instructions_digest"] == hashlib.sha1(
        workspace_text.encode("utf-8")
    ).hexdigest()
    assert cassette.manifest.workspace_snapshot["instructions_digest"] != hashlib.sha1(
        str(cassette.rounds[0].request.get("instructions") or "").encode("utf-8")
    ).hexdigest()
