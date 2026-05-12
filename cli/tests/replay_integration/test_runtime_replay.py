from __future__ import annotations

import io
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from cli.agent_cli.app_server import main as app_server_main
from cli.agent_cli.app_server_shell_protocol import _shell_protocol_fields
from cli.agent_cli.runtime_policy import RuntimePolicy
from cli.replay_integration.real_cases import load_real_case_cassette
from cli.replay_integration.reference_baseline_logs import (
    ReferenceBaselineTurnLog,
    build_cassette_from_reference_baseline_turn_logs,
)
from cli.replay_integration.runtime_replay import (
    RuntimeReplayMismatchError,
    build_runtime_for_replay,
)
from cli.tests.replay_integration.formal_cases import (
    build_planner_case_cassette,
    formal_planner_cases,
    make_openai_planner,
)

ROOT = Path(__file__).resolve().parents[3]


def _resolved_log_root() -> Path:
    base = ROOT / "docs" / "ab_acceptance"
    preferred = base / "reference_logs"
    if preferred.exists():
        return preferred
    candidates = sorted(
        path for path in base.iterdir() if path.is_dir() and path.name.endswith("_logs")
    )
    if candidates:
        return candidates[0]
    return preferred


LOG_ROOT = _resolved_log_root()

FORMAL_CASES = {case.case_id: case for case in formal_planner_cases()}


class _NdjsonInput(io.StringIO):
    def isatty(self) -> bool:
        return False


def _run_app_server_requests(runtime: object, requests: list[dict]) -> list[dict]:
    lines = "\n".join(json.dumps(item) for item in requests) + "\n"
    stdin = _NdjsonInput(lines)
    stdout = io.StringIO()
    code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)
    assert code == 0
    return [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]


def _assert_policy_snapshot_schema(snapshot: dict[str, object] | None) -> None:
    normalized = dict(snapshot or {})
    expected_keys = {
        "approvalPolicy",
        "sandboxMode",
        "networkAccessEnabled",
        "requestPermissionEnabled",
    }
    assert set(normalized.keys()) == expected_keys
    assert normalized.get("approvalPolicy") is None or isinstance(
        normalized.get("approvalPolicy"), str
    )
    assert normalized.get("sandboxMode") is None or isinstance(normalized.get("sandboxMode"), str)
    assert normalized.get("networkAccessEnabled") is None or isinstance(
        normalized.get("networkAccessEnabled"), bool
    )
    assert normalized.get("requestPermissionEnabled") is None or isinstance(
        normalized.get("requestPermissionEnabled"),
        bool,
    )


def _assert_policy_triplet(decision: str, reason: str, snapshot: dict[str, object] | None) -> None:
    normalized_decision = str(decision or "").strip()
    normalized_reason = str(reason or "").strip()
    if normalized_decision == "allowed":
        assert normalized_reason == "policy_allowed"
    elif normalized_decision == "requires_approval":
        assert normalized_reason == "approval_required"
    elif normalized_decision == "blocked":
        assert normalized_reason.startswith("policy_denied")
    else:
        raise AssertionError(f"unexpected policy decision: {normalized_decision}")
    _assert_policy_snapshot_schema(snapshot)


def _policy_triplet_from_command_result(
    result_payload: dict[str, object] | None,
) -> tuple[str, str, dict[str, object]]:
    result = dict(result_payload or {})
    decision = str(result.get("policyDecision") or "").strip()
    reason = str(result.get("policyDecisionReason") or "").strip()
    snapshot = dict(result.get("policySnapshot") or {})
    if decision and reason and snapshot:
        return decision, reason, snapshot
    response = dict(result.get("response") or {})
    tool_events = list(response.get("tool_events") or [])
    event_payload = dict((tool_events[-1].get("payload") if tool_events else {}) or {})
    fields = _shell_protocol_fields(event_payload)
    if not decision:
        decision = str(fields.get("policyDecision") or "").strip()
    if not reason:
        reason = str(fields.get("policyDecisionReason") or "").strip()
    if not snapshot:
        snapshot = dict(fields.get("policySnapshot") or {})
    return decision, reason, snapshot


def _real_cassette(prefix: str, turn_count: int, *, name: str):
    resolved_prefix = prefix
    first_probe = LOG_ROOT / f"{prefix}_turn1.stdout.jsonl"
    if not first_probe.exists():
        wildcard = str(prefix or "").replace("reference", "*")
        if wildcard != prefix:
            for stdout_path in sorted(LOG_ROOT.glob(f"{wildcard}_turn1.stdout.jsonl")):
                candidate = stdout_path.name[: -len("_turn1.stdout.jsonl")]
                if all(
                    (LOG_ROOT / f"{candidate}_turn{i}.stdout.jsonl").exists()
                    for i in range(1, turn_count + 1)
                ):
                    resolved_prefix = candidate
                    break

    turn_logs = []
    for turn_index in range(1, turn_count + 1):
        turn_logs.append(
            ReferenceBaselineTurnLog(
                stdout_path=LOG_ROOT / f"{resolved_prefix}_turn{turn_index}.stdout.jsonl",
                stderr_path=LOG_ROOT / f"{resolved_prefix}_turn{turn_index}.stderr.jsonl",
            )
        )

    return build_cassette_from_reference_baseline_turn_logs(
        turn_logs,
        name=name,
    )


def _real_pwd_followup_cassette():
    return _real_cassette("20260331_real_pwd_followup", 2, name="real-pwd-followup")


def _real_error_recovery_cassette():
    return _real_cassette("20260331_real_error_recovery", 2, name="real-error-recovery")


def _real_memory_2turn_name_cassette():
    return _real_cassette("20260331_real_memory_2turn_name", 2, name="real-memory-2turn-name")


def _real_reference_person_pronoun_cassette():
    return _real_cassette(
        "20260331_real_reference_person_pronoun", 2, name="real-reference-person-pronoun"
    )


def _real_history_compression_summary_cassette():
    return _real_cassette(
        "20260331_real_history_compression_summary", 3, name="real-history-compression-summary"
    )


def _real_reference_path_followup_cassette():
    return _real_cassette(
        "20260331_real_reference_path_followup", 2, name="real-reference-path-followup"
    )


def _real_reference_variable_value_cassette():
    return _real_cassette(
        "20260331_real_reference_variable_value", 2, name="real-reference-variable-value"
    )


def _real_memory_3turn_facts_cassette():
    return _real_cassette("20260331_real_memory_3turn_facts", 3, name="real-memory-3turn-facts")


def _real_memory_5turn_profile_cassette():
    return _real_cassette("20260331_real_memory_5turn_profile", 5, name="real-memory-5turn-profile")


def _real_simple_date_time_3turn_cassette():
    return _real_cassette(
        "20260331_real_simple_date_time_3turn", 3, name="real-simple-date-time-3turn"
    )


def _formal_case_cassette(case_id: str):
    return build_planner_case_cassette(
        make_openai_planner(),
        FORMAL_CASES[case_id],
    )


def test_runtime_replay_can_drive_real_pwd_followup_behavior() -> None:
    cassette = _real_pwd_followup_cassette()
    runtime = build_runtime_for_replay(cassette)

    response1 = runtime.handle_prompt("先执行 pwd，再告诉我当前目录。")
    assert response1.assistant_text == "当前目录是 `/home/lyc/project/AgentHub/cli`。"
    assert len(response1.tool_events) == 1
    assert response1.tool_events[0].name == "exec_command"
    assert response1.tool_events[0].ok is True
    assert (
        response1.tool_events[0].payload["function_call_output"]
        == "/home/lyc/project/AgentHub/cli\n"
    )
    assert any(
        str(event.get("item", {}).get("type") or "").strip() == "command_execution"
        for event in response1.turn_events
    )

    response2 = runtime.handle_prompt("刚才目录是什么？只回复路径。")
    assert response2.assistant_text == "`/home/lyc/project/AgentHub/cli`"
    assert not response2.tool_events
    assert runtime.history[-1]["content"] == "`/home/lyc/project/AgentHub/cli`"


def test_runtime_replay_can_drive_real_error_recovery_behavior() -> None:
    cassette = _real_error_recovery_cassette()
    runtime = build_runtime_for_replay(cassette)

    response1 = runtime.handle_prompt("先执行 ls /missing，再告诉我结果。")
    assert (
        response1.assistant_text
        == "结果如下：\n\n- 命令：`ls /missing`\n- 退出码：`2`\n- 输出：`ls: cannot access '/missing': No such file or directory`\n\n也就是说，系统里没有 `/missing` 这个路径。"
    )
    assert len(response1.tool_events) == 1
    assert response1.tool_events[0].name == "exec_command"
    assert response1.tool_events[0].ok is False
    assert "No such file or directory" in str(
        response1.tool_events[0].payload["function_call_output"]
    )
    assert any(
        item.role == "assistant"
        and any(
            "系统里没有 `/missing` 这个路径" in str(part.get("text") or "")
            for part in list(item.content or [])
        )
        for item in response1.response_items
    )
    assert any(
        str(event.get("item", {}).get("status") or "").strip() == "failed"
        for event in response1.turn_events
    )

    response2 = runtime.handle_prompt("上一轮失败的原因是什么？只回复一句话。")
    assert (
        response2.assistant_text
        == "因为系统中不存在 `/missing` 这个路径，所以 `ls /missing` 以 “No such file or directory” 失败了。"
    )
    assert not response2.tool_events
    assert runtime.history[-1]["content"] == response2.assistant_text


def test_runtime_replay_policy_block_contract_is_observable_via_app_server_command_exec() -> None:
    cassette = _formal_case_cassette("tool_followup_pwd_memory")
    runtime = build_runtime_for_replay(
        cassette,
        runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
    )
    with patch.dict(
        os.environ,
        {
            "AGENT_CLI_COMMAND_POLICY_MODE": "background_teammate",
            "AGENT_CLI_TEST_POLICY": "scoped_only",
        },
        clear=False,
    ):
        lines = _run_app_server_requests(
            runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {
                    "id": "cmd-exec",
                    "method": "command/exec",
                    "params": {"command": "pytest -q", "stream": False},
                },
            ],
        )
    result = next(line for line in lines if line.get("id") == "cmd-exec")
    contract = dict(result.get("result") or {})
    assert contract.get("policyDecision") == "blocked"
    assert str(contract.get("policyDecisionReason") or "").startswith("policy_denied")
    snapshot = dict(contract.get("policySnapshot") or {})
    assert set(snapshot.keys()) == {
        "approvalPolicy",
        "sandboxMode",
        "networkAccessEnabled",
        "requestPermissionEnabled",
    }
    response = dict(contract.get("response") or {})
    tool_events = list(response.get("tool_events") or [])
    assert tool_events
    tool_payload = dict(tool_events[-1].get("payload") or {})
    assert tool_payload.get("status") == "policy_denied"
    assert tool_payload.get("error_code") == "test_scope_required"


def test_runtime_replay_policy_contract_matrix_for_command_exec_paths() -> None:
    cassette = _formal_case_cassette("tool_followup_pwd_memory")
    snapshot_keys = {
        "approvalPolicy",
        "sandboxMode",
        "networkAccessEnabled",
        "requestPermissionEnabled",
    }

    allowed_runtime = build_runtime_for_replay(
        cassette,
        runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
    )
    allowed_lines = _run_app_server_requests(
        allowed_runtime,
        [
            {"id": "init", "method": "initialize", "params": {}},
            {"method": "initialized", "params": {}},
            {
                "id": "cmd-exec",
                "method": "command/exec",
                "params": {"command": "echo stable", "stream": False},
            },
        ],
    )
    allowed_contract = dict(
        next(line for line in allowed_lines if line.get("id") == "cmd-exec").get("result") or {}
    )
    assert allowed_contract.get("policyDecision") == "allowed"
    assert allowed_contract.get("policyDecisionReason") == "policy_allowed"
    assert set(dict(allowed_contract.get("policySnapshot") or {}).keys()) == snapshot_keys

    approval_runtime = build_runtime_for_replay(
        cassette,
        runtime_policy=RuntimePolicy.normalized(approval_policy="on-request"),
    )
    approval_lines = _run_app_server_requests(
        approval_runtime,
        [
            {"id": "init", "method": "initialize", "params": {}},
            {"method": "initialized", "params": {}},
            {
                "id": "cmd-exec",
                "method": "command/exec",
                "params": {"command": "touch approve.txt", "stream": False},
            },
        ],
    )
    approval_contract = dict(
        next(line for line in approval_lines if line.get("id") == "cmd-exec").get("result") or {}
    )
    assert approval_contract.get("policyDecision") == "requires_approval"
    assert approval_contract.get("policyDecisionReason") == "approval_required"
    assert set(dict(approval_contract.get("policySnapshot") or {}).keys()) == snapshot_keys

    blocked_runtime = build_runtime_for_replay(
        cassette,
        runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
    )
    with patch.dict(
        os.environ,
        {
            "AGENT_CLI_COMMAND_POLICY_MODE": "background_teammate",
            "AGENT_CLI_TEST_POLICY": "scoped_only",
        },
        clear=False,
    ):
        blocked_lines = _run_app_server_requests(
            blocked_runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {
                    "id": "cmd-exec",
                    "method": "command/exec",
                    "params": {"command": "pytest -q", "stream": False},
                },
            ],
        )
    blocked_contract = dict(
        next(line for line in blocked_lines if line.get("id") == "cmd-exec").get("result") or {}
    )
    assert blocked_contract.get("policyDecision") == "blocked"
    assert str(blocked_contract.get("policyDecisionReason") or "").startswith("policy_denied")
    assert set(dict(blocked_contract.get("policySnapshot") or {}).keys()) == snapshot_keys


def test_runtime_replay_background_teammate_policy_contract_includes_decision() -> None:
    cassette = _formal_case_cassette("tool_followup_pwd_memory")
    runtime = build_runtime_for_replay(
        cassette,
        runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
    )
    with patch.dict(
        os.environ,
        {
            "AGENT_CLI_COMMAND_POLICY_MODE": "background_teammate",
            "AGENT_CLI_TEST_POLICY": "scoped_only",
        },
        clear=False,
    ):
        blocked_lines = _run_app_server_requests(
            runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {
                    "id": "cmd-exec",
                    "method": "command/exec",
                    "params": {"command": "pytest -q", "stream": False},
                },
            ],
        )
    contract = dict(
        next(line for line in blocked_lines if line.get("id") == "cmd-exec").get("result") or {}
    )
    assert contract.get("policyDecision") == "blocked"
    assert str(contract.get("policyDecisionReason") or "").startswith("policy_denied")
    assert (
        contract.get("outputText")
        == "background teammate test commands must target explicit test files or node ids"
    )
    assert set(dict(contract.get("policySnapshot") or {}).keys()) == {
        "approvalPolicy",
        "sandboxMode",
        "networkAccessEnabled",
        "requestPermissionEnabled",
    }
    response = dict(contract.get("response") or {})
    tool_events = list(response.get("tool_events") or [])
    assert tool_events
    tool_payload = dict(tool_events[-1].get("payload") or {})
    assert tool_payload.get("status") == "policy_denied"
    assert tool_payload.get("policy_mode") == "background_teammate"
    assert tool_payload.get("error_code") == "test_scope_required"
    assert tool_payload.get("is_test_command") is True


def test_runtime_replay_policy_contract_matrix_for_command_start_paths() -> None:
    cassette = _formal_case_cassette("tool_followup_pwd_memory")
    snapshot_keys = {
        "approvalPolicy",
        "sandboxMode",
        "networkAccessEnabled",
        "requestPermissionEnabled",
    }

    allowed_runtime = build_runtime_for_replay(
        cassette,
        runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
    )
    allowed_lines = _run_app_server_requests(
        allowed_runtime,
        [
            {"id": "init", "method": "initialize", "params": {}},
            {"method": "initialized", "params": {}},
            {
                "id": "cmd-start",
                "method": "command/start",
                "params": {"command": "python -i", "stream": True, "cwd": str(ROOT)},
            },
        ],
    )
    allowed_contract = dict(
        next(line for line in allowed_lines if line.get("id") == "cmd-start").get("result") or {}
    )
    assert allowed_contract.get("accepted") is True
    assert allowed_contract.get("policyDecision") == "allowed"
    assert allowed_contract.get("policyDecisionReason") == "policy_allowed"
    assert set(dict(allowed_contract.get("policySnapshot") or {}).keys()) == snapshot_keys

    approval_runtime = build_runtime_for_replay(
        cassette,
        runtime_policy=RuntimePolicy.normalized(approval_policy="on-request"),
    )
    approval_lines = _run_app_server_requests(
        approval_runtime,
        [
            {"id": "init", "method": "initialize", "params": {}},
            {"method": "initialized", "params": {}},
            {
                "id": "cmd-start",
                "method": "command/start",
                "params": {"command": "python -i", "stream": True, "cwd": str(ROOT)},
            },
        ],
    )
    approval_contract = dict(
        next(line for line in approval_lines if line.get("id") == "cmd-start").get("result") or {}
    )
    assert approval_contract.get("accepted") is False
    assert approval_contract.get("approvalRequired") is True
    approval_payload = dict(
        list(dict(approval_contract.get("response") or {}).get("tool_events") or [])[-1].get(
            "payload"
        )
        or {}
    )
    approval_fields = _shell_protocol_fields(approval_payload)
    assert approval_fields.get("policyDecision") == "requires_approval"
    assert approval_fields.get("policyDecisionReason") == "approval_required"
    assert set(dict(approval_fields.get("policySnapshot") or {}).keys()) == snapshot_keys

    blocked_runtime = build_runtime_for_replay(
        cassette,
        runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
    )
    with patch.dict(
        os.environ,
        {
            "AGENT_CLI_COMMAND_POLICY_MODE": "background_teammate",
            "AGENT_CLI_TEST_POLICY": "scoped_only",
        },
        clear=False,
    ):
        blocked_lines = _run_app_server_requests(
            blocked_runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {
                    "id": "cmd-start",
                    "method": "command/start",
                    "params": {"command": "pytest -q", "stream": True, "cwd": str(ROOT)},
                },
            ],
        )
    blocked_contract = dict(
        next(line for line in blocked_lines if line.get("id") == "cmd-start").get("result") or {}
    )
    assert blocked_contract.get("accepted") is False
    blocked_payload = dict(
        list(dict(blocked_contract.get("response") or {}).get("tool_events") or [])[-1].get(
            "payload"
        )
        or {}
    )
    blocked_fields = _shell_protocol_fields(blocked_payload)
    assert blocked_fields.get("policyDecision") == "blocked"
    assert str(blocked_fields.get("policyDecisionReason") or "").startswith("policy_denied")
    assert set(dict(blocked_fields.get("policySnapshot") or {}).keys()) == snapshot_keys


def test_runtime_replay_policy_triplet_parity_between_command_exec_and_start_paths() -> None:
    cassette = _formal_case_cassette("tool_followup_pwd_memory")

    allowed_exec_runtime = build_runtime_for_replay(
        cassette,
        runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
    )
    allowed_exec_lines = _run_app_server_requests(
        allowed_exec_runtime,
        [
            {"id": "init", "method": "initialize", "params": {}},
            {"method": "initialized", "params": {}},
            {
                "id": "cmd-exec",
                "method": "command/exec",
                "params": {"command": 'python -c "print(1)"', "stream": False},
            },
        ],
    )
    allowed_exec_result = dict(
        next(line for line in allowed_exec_lines if line.get("id") == "cmd-exec").get("result")
        or {}
    )
    allowed_exec_triplet = _policy_triplet_from_command_result(allowed_exec_result)
    _assert_policy_triplet(*allowed_exec_triplet)

    allowed_start_runtime = build_runtime_for_replay(
        cassette,
        runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
    )
    allowed_start_lines = _run_app_server_requests(
        allowed_start_runtime,
        [
            {"id": "init", "method": "initialize", "params": {}},
            {"method": "initialized", "params": {}},
            {
                "id": "cmd-start",
                "method": "command/start",
                "params": {"command": "python -i", "stream": True, "cwd": str(ROOT)},
            },
        ],
    )
    allowed_start_result = dict(
        next(line for line in allowed_start_lines if line.get("id") == "cmd-start").get("result")
        or {}
    )
    allowed_start_triplet = _policy_triplet_from_command_result(allowed_start_result)
    _assert_policy_triplet(*allowed_start_triplet)
    assert allowed_start_triplet == allowed_exec_triplet

    approval_exec_runtime = build_runtime_for_replay(
        cassette,
        runtime_policy=RuntimePolicy.normalized(approval_policy="on-request"),
    )
    approval_exec_lines = _run_app_server_requests(
        approval_exec_runtime,
        [
            {"id": "init", "method": "initialize", "params": {}},
            {"method": "initialized", "params": {}},
            {
                "id": "cmd-exec",
                "method": "command/exec",
                "params": {"command": 'python -c "print(1)"', "stream": False},
            },
        ],
    )
    approval_exec_result = dict(
        next(line for line in approval_exec_lines if line.get("id") == "cmd-exec").get("result")
        or {}
    )
    approval_exec_triplet = _policy_triplet_from_command_result(approval_exec_result)
    _assert_policy_triplet(*approval_exec_triplet)

    approval_start_runtime = build_runtime_for_replay(
        cassette,
        runtime_policy=RuntimePolicy.normalized(approval_policy="on-request"),
    )
    approval_start_lines = _run_app_server_requests(
        approval_start_runtime,
        [
            {"id": "init", "method": "initialize", "params": {}},
            {"method": "initialized", "params": {}},
            {
                "id": "cmd-start",
                "method": "command/start",
                "params": {"command": "python -i", "stream": True, "cwd": str(ROOT)},
            },
        ],
    )
    approval_start_result = dict(
        next(line for line in approval_start_lines if line.get("id") == "cmd-start").get("result")
        or {}
    )
    approval_start_triplet = _policy_triplet_from_command_result(approval_start_result)
    _assert_policy_triplet(*approval_start_triplet)
    assert approval_start_triplet == approval_exec_triplet

    blocked_exec_runtime = build_runtime_for_replay(
        cassette,
        runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
    )
    blocked_start_runtime = build_runtime_for_replay(
        cassette,
        runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
    )
    with patch.dict(
        os.environ,
        {
            "AGENT_CLI_COMMAND_POLICY_MODE": "background_teammate",
            "AGENT_CLI_TEST_POLICY": "scoped_only",
        },
        clear=False,
    ):
        blocked_exec_lines = _run_app_server_requests(
            blocked_exec_runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {
                    "id": "cmd-exec",
                    "method": "command/exec",
                    "params": {"command": "pytest -q", "stream": False},
                },
            ],
        )
        blocked_start_lines = _run_app_server_requests(
            blocked_start_runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {
                    "id": "cmd-start",
                    "method": "command/start",
                    "params": {"command": "pytest -q", "stream": True, "cwd": str(ROOT)},
                },
            ],
        )
    blocked_exec_result = dict(
        next(line for line in blocked_exec_lines if line.get("id") == "cmd-exec").get("result")
        or {}
    )
    blocked_exec_triplet = _policy_triplet_from_command_result(blocked_exec_result)
    _assert_policy_triplet(*blocked_exec_triplet)

    blocked_start_result = dict(
        next(line for line in blocked_start_lines if line.get("id") == "cmd-start").get("result")
        or {}
    )
    blocked_start_triplet = _policy_triplet_from_command_result(blocked_start_result)
    _assert_policy_triplet(*blocked_start_triplet)
    assert blocked_start_triplet == blocked_exec_triplet


def test_runtime_replay_rejects_prompt_drift() -> None:
    cassette = _real_pwd_followup_cassette()
    runtime = build_runtime_for_replay(cassette)

    with pytest.raises(RuntimeReplayMismatchError):
        runtime.agent._planner.plan(
            "不一样的请求",
            history=[],
            tool_executor=runtime._structured_tool_executor,
            prompt_cache_key=str(runtime.thread_id or ""),
        )


def test_runtime_replay_can_drive_real_simple_date_time_behavior() -> None:
    cassette = _real_simple_date_time_3turn_cassette()
    runtime = build_runtime_for_replay(cassette)

    prompts = ["你好", "你帮我看看今天周几", "现在北京时间几点"]
    expected_outputs = [
        "你好！我在这儿。要我帮你做什么？",
        "今天是星期二。  \n按你当前环境时间，今天是 `2026年3月31日`（Asia/Shanghai）。",
        "现在北京时间是 `2026年3月31日 22:27:38`。",
    ]

    observed = []
    for prompt, expected_output in zip(prompts, expected_outputs, strict=False):
        response = runtime.handle_prompt(prompt)
        observed.append(response.assistant_text)
        assert response.assistant_text == expected_output
        assert response.turn_events
        assert runtime.history[-1]["content"] == response.assistant_text
        if prompt == "现在北京时间几点":
            assert [item.item_type for item in list(response.response_items or [])] == [
                "reasoning",
                "web_search_call",
                "reasoning",
                "message",
            ]
            assert (
                response.response_items[1].extra["action"]["query"]
                == 'time: {"utc_offset":"+08:00"}'
            )

    assert observed == expected_outputs


@pytest.mark.parametrize(
    ("cassette_factory", "prompts", "expected_outputs"),
    [
        (
            _real_memory_2turn_name_cassette,
            ["我叫张三。请只回复“记住了”。", "我刚才说我叫什么？只回复名字。"],
            ["记住了", "张三"],
        ),
        (
            _real_reference_person_pronoun_cassette,
            ["新同事叫李雷。请只回复“记住了”。", "他叫什么？只回复名字。"],
            ["记住了", "李雷"],
        ),
        (
            _real_history_compression_summary_cassette,
            [
                "我叫张三。请只回复“记住了”。",
                "我喜欢 Go。请只回复“记住了”。",
                "把前两轮压缩成一句话。只输出结果。",
            ],
            ["记住了", "记住了", "我叫张三，喜欢 Go。"],
        ),
        (
            _real_reference_path_followup_cassette,
            [
                "项目目录是 /srv/app。请记住这个路径，并只回复“记住了”。",
                "刚才那个目录是什么？只回复路径。",
            ],
            ["记住了", "/srv/app"],
        ),
        (
            _real_reference_variable_value_cassette,
            [
                "变量 API_BASE 的值是 https://api.example.com/v1 。请只回复“记住了”。",
                "API_BASE 是什么？只回复值。",
            ],
            ["记住了", "https://api.example.com/v1"],
        ),
        (
            _real_memory_3turn_facts_cassette,
            [
                "我叫李雷。请只回复“记住了”。",
                "我在杭州工作。请只回复“记住了”。",
                "我叫什么，在哪里工作？只用一句话回答。",
            ],
            ["记住了", "记住了", "你叫李雷，在杭州工作。"],
        ),
        (
            _real_memory_5turn_profile_cassette,
            [
                "我叫王敏。请只回复“记住了”。",
                "我在上海。请只回复“记住了”。",
                "我是测试工程师。请只回复“记住了”。",
                "我的项目代号是天枢。请只回复“记住了”。",
                "把我前四轮说的信息合成一句话。",
            ],
            [
                "记住了",
                "记住了",
                "记住了",
                "记住了",
                "你叫王敏，在上海，是测试工程师，你的项目代号是天枢。",
            ],
        ),
    ],
)
def test_runtime_replay_can_drive_real_multiturn_memory_cases(
    cassette_factory,
    prompts: list[str],
    expected_outputs: list[str],
) -> None:
    cassette = cassette_factory()
    runtime = build_runtime_for_replay(cassette)

    observed = []
    for prompt, expected_output in zip(prompts, expected_outputs, strict=False):
        response = runtime.handle_prompt(prompt)
        observed.append(response.assistant_text)
        assert response.assistant_text == expected_output
        assert not response.tool_events
        assert response.turn_events
        assert runtime.history[-1]["content"] == response.assistant_text

    assert observed == expected_outputs


@pytest.mark.parametrize(
    ("case_id", "prompts", "expected_outputs"),
    [
        (
            "memory_project_constraint_followup",
            [
                "项目目录是 /srv/app。请记住这个路径，并只回复“记住了”。",
                "刚才那个目录是什么？只回复路径。",
            ],
            ["记住了", "/srv/app"],
        ),
        (
            "memory_user_preference_followup",
            [
                "我叫张三。请只回复“记住了”。",
                "我刚才说我叫什么？只回复名字。",
            ],
            ["记住了", "张三"],
        ),
        (
            "memory_reference_link_followup",
            [
                "变量 API_BASE 的值是 https://api.example.com/v1 。请只回复“记住了”。",
                "API_BASE 是什么？只回复值。",
            ],
            ["记住了", "https://api.example.com/v1"],
        ),
    ],
)
def test_runtime_replay_can_drive_real_memory_followup_cases(
    case_id: str,
    prompts: list[str],
    expected_outputs: list[str],
) -> None:
    cassette = load_real_case_cassette(case_id)
    coverage_tags = set(cassette.manifest.coverage_tags or [])
    assert "phase2_memory_preview_apply_contract" in coverage_tags
    assert "phase2_memory_ranking_explainability_contract" in coverage_tags
    if case_id == "memory_user_preference_followup":
        assert "phase2_memory_user_scope_opt_in_contract" in coverage_tags
    runtime = build_runtime_for_replay(cassette)

    observed = []
    for prompt, expected_output in zip(prompts, expected_outputs, strict=False):
        response = runtime.handle_prompt(prompt)
        observed.append(response.assistant_text)
        assert response.assistant_text == expected_output
        assert response.turn_events
        assert runtime.history[-1]["content"] == response.assistant_text
    assert observed == expected_outputs


@pytest.mark.parametrize(
    ("case_id", "expected_outputs"),
    [
        ("memory_2turn_name", ["记住了", "张三"]),
        ("memory_3turn_facts", ["记住了", "记住了", "你叫李雷，在杭州工作。"]),
        (
            "memory_5turn_profile",
            [
                "记住了",
                "记住了",
                "记住了",
                "记住了",
                "你叫王敏，在上海，是测试工程师，项目代号是天枢。",
            ],
        ),
        ("reference_person_pronoun", ["记住了", "李雷"]),
        ("reference_path_followup", ["记住了", "/srv/app"]),
        ("reference_variable_value", ["记住了", "https://api.example.com/v1"]),
        ("history_compression_summary", ["记住了", "记住了", "你叫张三，喜欢 Go。"]),
    ],
)
def test_runtime_replay_can_drive_formal_multiturn_memory_cases(
    case_id: str,
    expected_outputs: list[str],
) -> None:
    cassette = _formal_case_cassette(case_id)
    runtime = build_runtime_for_replay(cassette)
    case = FORMAL_CASES[case_id]

    observed = []
    for step in case.steps:
        response = runtime.handle_prompt(step.user_text)
        observed.append(response.assistant_text)
        assert not response.tool_events
        assert response.turn_events
        assert runtime.history[-1]["content"] == response.assistant_text

    assert observed == expected_outputs
    assert len(runtime.history) == len(case.steps) * 2
