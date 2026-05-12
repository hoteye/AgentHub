from __future__ import annotations

import json
import shlex

from cli.agent_cli.host_platform import current_host_platform, detect_host_platform
from cli.agent_cli.models import ToolEvent
from cli.agent_cli.providers.anthropic_claude_runtime import (
    command_for_tool_call as anthropic_command_for_tool_call,
)
from cli.agent_cli.providers.tool_calls import command_for_tool_call, tool_result_payload


def _decode_apply_patch_payload(command: str) -> dict:
    argv = shlex.split(command)
    assert argv[0] == "/apply_patch"
    assert len(argv) == 2
    return json.loads(argv[1])


def test_tool_result_payload_preserves_deep_file_read_text() -> None:
    marker = "TARGET_MARKER_AT_DEEP_OFFSET"
    deep_text = ("a" * 9000) + marker
    payload = tool_result_payload(
        "/file_read cli/agent_cli/runtime_core/command_handlers.py --max-chars 12000",
        "Read workspace file.",
        [
            ToolEvent(
                name="file_read",
                ok=True,
                summary="file loaded",
                payload={
                    "path": "cli/agent_cli/runtime_core/command_handlers.py",
                    "char_count": len(deep_text),
                    "line_count": 250,
                    "truncated": False,
                    "text": deep_text,
                },
            )
        ],
    )

    text = payload["events"][0]["payload"]["text"]
    assert marker in text
    assert len(text) == len(deep_text)


def test_tool_result_payload_keeps_generic_payload_trimming() -> None:
    long_text = "b" * 3000
    payload = tool_result_payload(
        "/file_search provider",
        "Search workspace files.",
        [
            ToolEvent(
                name="file_search",
                ok=True,
                summary="file matches=1",
                payload={"text": long_text},
            )
        ],
    )

    text = payload["events"][0]["payload"]["text"]
    assert len(text) == 1200


def test_command_for_tool_call_uses_canonical_file_commands_for_reference_names() -> None:
    host = current_host_platform()
    glob_command = command_for_tool_call(
        "Glob",
        {"pattern": "**/*.py", "path": "cli"},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    grep_command = command_for_tool_call(
        "grep_files",
        {"pattern": "ProviderConfig", "include": "*.py", "path": "cli", "limit": 12},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    assert glob_command == "/glob_files '**/*.py' --path cli"
    assert grep_command == "/grep_files ProviderConfig --include '*.py' --path cli --limit 12"

    read_command = command_for_tool_call(
        "read_file",
        {"file_path": "cli/agent_cli/providers/tool_specs.py", "offset": 40, "limit": 30},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    assert read_command == "/read_file cli/agent_cli/providers/tool_specs.py --offset 40 --limit 30"

    list_command = command_for_tool_call(
        "list_dir",
        {"dir_path": "cli/agent_cli/providers", "offset": 1, "limit": 25, "depth": 2},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    assert list_command == "/list_dir cli/agent_cli/providers --offset 1 --limit 25 --depth 2"


def test_command_for_tool_call_keeps_native_list_dir_for_one_layer_snapshots() -> None:
    host = current_host_platform()
    list_command = command_for_tool_call(
        "list_dir",
        {"dir_path": ".", "limit": 50, "depth": 1},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert list_command == "/list_dir . --limit 50 --depth 1"


def test_command_for_tool_call_uses_canonical_exec_and_plan_commands() -> None:
    host = current_host_platform()
    exec_command = command_for_tool_call(
        "exec_command",
        {
            "cmd": "python -V",
            "workdir": "cli",
            "tty": True,
            "yield_time_ms": 1500,
            "max_output_tokens": 800,
            "login": False,
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    spawn_command = command_for_tool_call(
        "spawn_agent",
        {
            "task": "检查 provider 差异",
            "role": "teammate",
            "model": "inherit",
            "provider": "glm",
            "reasoning_effort": "high",
            "timeout": 25,
            "async": True,
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    send_command = command_for_tool_call(
        "send_input",
        {"target": "agent_1", "message": "继续检查", "interrupt": True},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    resume_command = command_for_tool_call(
        "resume_agent",
        {"target": "agent_1"},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    wait_command = command_for_tool_call(
        "wait_agent",
        {"target": "agent_1", "timeout_ms": 250},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    workflow_command = command_for_tool_call(
        "agent_workflow",
        {"target": "agent_1", "steps": 3, "checkpoints": 2},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    recover_command = command_for_tool_call(
        "recover_agent",
        {"target": "agent_1", "action": "retry_step", "step_id": "step_2"},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    close_command = command_for_tool_call(
        "close_agent",
        {"target": "agent_1"},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    write_command = command_for_tool_call(
        "write_stdin",
        {"session_id": 42, "chars": "ping\n", "yield_time_ms": 250},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    plan_command = command_for_tool_call(
        "update_plan",
        {"explanation": "sync", "plan": [{"step": "inspect", "status": "completed"}]},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    request_command = command_for_tool_call(
        "request_user_input",
        {
            "questions": [
                {
                    "id": "confirm_path",
                    "header": "Confirm",
                    "question": "Proceed?",
                    "options": [
                        {"label": "Yes (Recommended)", "description": "Continue."},
                        {"label": "No", "description": "Stop."},
                    ],
                }
            ]
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert (
        exec_command
        == "/exec_command 'python -V' --workdir cli --tty --login false --yield-time-ms 1500 --max-output-tokens 800"
    )
    assert (
        spawn_command
        == '/spawn_agent \'{"task": "\\u68c0\\u67e5 provider \\u5dee\\u5f02", "role": "teammate", "model": "inherit", "provider": "glm", "reasoning_effort": "high", "timeout": 25, "async": true}\''
    )
    assert send_command == "/send_input agent_1 '继续检查' --interrupt"
    assert resume_command == "/resume_agent agent_1"
    assert wait_command == "/wait_agent agent_1 --timeout-ms 250"
    assert workflow_command == "/agent_workflow agent_1 --steps 3 --checkpoints 2"
    assert recover_command == "/recover_agent agent_1 --action retry_step --step-id step_2"
    assert close_command == "/close_agent agent_1"
    assert write_command == "/write_stdin 42 'ping\n' --yield-time-ms 250"
    assert (
        plan_command
        == '/update_plan \'{"plan": [{"step": "inspect", "status": "completed"}], "explanation": "sync"}\''
    )
    assert (
        request_command
        == '/request_user_input \'{"questions": [{"id": "confirm_path", "header": "Confirm", "question": "Proceed?", "options": [{"label": "Yes (Recommended)", "description": "Continue."}, {"label": "No", "description": "Stop."}]}]}\''
    )


def test_command_for_tool_call_projects_codex_wait_to_ids_payload() -> None:
    host = current_host_platform()
    wait_command = command_for_tool_call(
        "wait",
        {"ids": ["agent_1", "agent_2"], "timeout_ms": 15000},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert wait_command == '/wait_agent \'{"ids": ["agent_1", "agent_2"], "timeout_ms": 15000}\''


def test_command_for_tool_call_projects_expert_review_to_runtime_command() -> None:
    host = detect_host_platform()
    command = command_for_tool_call(
        "expert_review",
        {
            "task": "Review latest answer",
            "scope": "current_task",
            "focus": ["correctness", "evidence"],
            "artifact_paths": ["src/app.py"],
            "max_findings": 3,
            "strictness": "high",
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert command is not None
    argv = shlex.split(command)
    assert argv[0] == "/expert_review"
    payload = json.loads(argv[1])
    assert payload == {
        "task": "Review latest answer",
        "scope": "current_task",
        "focus": ["correctness", "evidence"],
        "artifact_paths": ["src/app.py"],
        "max_findings": 3,
        "strictness": "high",
    }


def test_command_for_tool_call_projects_codex_collab_message_and_wait_surface() -> None:
    host = current_host_platform()
    spawn_command = command_for_tool_call(
        "spawn_agent",
        {
            "message": "检查 README 结构",
            "agent_type": "worker",
            "fork_context": True,
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    wait_command = command_for_tool_call(
        "wait",
        {"ids": ["agent_1", "agent_2"], "timeout_ms": 5000},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert (
        spawn_command
        == '/spawn_agent \'{"message": "\\u68c0\\u67e5 README \\u7ed3\\u6784", "agent_type": "worker", "fork_context": true}\''
    )
    assert wait_command == '/wait_agent \'{"ids": ["agent_1", "agent_2"], "timeout_ms": 5000}\''


def test_command_for_tool_call_projects_codex_collab_item_payloads() -> None:
    host = current_host_platform()
    send_command = command_for_tool_call(
        "send_input",
        {
            "id": "agent_1",
            "items": [
                {"type": "text", "text": "继续检查"},
                {"type": "mention", "name": "repo", "path": "app://repo"},
            ],
            "interrupt": True,
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    argv = shlex.split(send_command)
    assert argv[0] == "/send_input"
    assert json.loads(argv[1]) == {
        "id": "agent_1",
        "items": [
            {"type": "text", "text": "继续检查"},
            {"type": "mention", "name": "repo", "path": "app://repo"},
        ],
        "interrupt": True,
    }


def test_command_for_tool_call_request_user_input_requires_questions_array() -> None:
    host = current_host_platform()
    command = command_for_tool_call(
        "request_user_input",
        {"questions": "not-a-list"},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    assert command is None


def test_command_for_tool_call_request_orchestration_uses_internal_preview_command() -> None:
    host = current_host_platform()
    command = command_for_tool_call(
        "request_orchestration",
        {
            "source_text": "拆分 runtime_core/orchestration_commands.py 并补测试",
            "goal": "完成编排入口改造",
            "reason": "任务跨多个阶段且需要确认",
            "needs_confirmation": True,
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    assert command is not None
    assert command.startswith("/__request_orchestration ")
    assert (
        '"source_text": "\\u62c6\\u5206 runtime_core/orchestration_commands.py \\u5e76\\u8865\\u6d4b\\u8bd5"'
        in command
    )
    assert '"needs_confirmation": true' in command


def test_command_for_tool_call_visible_child_tools_use_internal_commands() -> None:
    host = current_host_platform()
    spawn_command = command_for_tool_call(
        "spawn_child_tab",
        {"task": "Inspect README", "task_name": "README", "metadata": {"run_id": "run_1"}},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    send_command = command_for_tool_call(
        "send_child_tab",
        {"target": "latest", "message": "Continue", "interrupt": True},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    wait_command = command_for_tool_call(
        "wait_child_tasks",
        {"targets": ["latest"], "timeout_ms": 250, "wait_for": "any", "terminal_only": True},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert spawn_command is not None
    assert spawn_command.startswith("/__spawn_child_tab ")
    assert '"task": "Inspect README"' in spawn_command
    assert '"task_name": "README"' in spawn_command
    assert send_command is not None
    assert send_command.startswith("/__send_child_tab ")
    assert '"target": "latest"' in send_command
    assert '"interrupt": true' in send_command
    assert wait_command is not None
    assert wait_command.startswith("/__wait_child_tasks ")
    assert '"targets": ["latest"]' in wait_command
    assert '"wait_for": "any"' in wait_command
    assert '"terminal_only": true' in wait_command


def test_command_for_tool_call_request_user_input_serializes_unicode_payload_as_ascii_json() -> (
    None
):
    host = current_host_platform()
    request_command = command_for_tool_call(
        "request_user_input",
        {
            "questions": [
                {
                    "id": "confirm_scope",
                    "header": "确认",
                    "question": "继续执行吗？",
                    "options": [
                        {"label": "是", "description": "继续"},
                        {"label": "否", "description": "停止"},
                    ],
                    "ignored_by_command": True,
                }
            ]
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert request_command is not None
    assert request_command.startswith("/request_user_input ")
    assert "\\u786e\\u8ba4" in request_command
    assert "\\u7ee7\\u7eed\\u6267\\u884c\\u5417\\uff1f" in request_command


def test_command_for_tool_call_ask_user_question_routes_to_canonical_request_user_input() -> None:
    host = current_host_platform()
    request_command = command_for_tool_call(
        "AskUserQuestion",
        {
            "questions": [
                {
                    "id": "confirm_scope",
                    "header": "Confirm",
                    "question": "Proceed?",
                    "options": [
                        {"label": "Yes (Recommended)", "description": "Continue."},
                        {"label": "No", "description": "Stop."},
                    ],
                }
            ]
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert (
        request_command
        == '/request_user_input \'{"questions": [{"id": "confirm_scope", "header": "Confirm", "question": "Proceed?", "options": [{"label": "Yes (Recommended)", "description": "Continue."}, {"label": "No", "description": "Stop."}]}]}\''
    )


def test_tool_result_payload_preserves_spawn_agent_text_body() -> None:
    marker = "DELEGATED_RESULT_MARKER"
    delegated_text = ("c" * 9000) + marker
    payload = tool_result_payload(
        '/spawn_agent \'{"task":"inspect"}\'',
        "delegated",
        [
            ToolEvent(
                name="spawn_agent",
                ok=True,
                summary="spawn_agent completed",
                payload={
                    "role": "subagent",
                    "task": "inspect",
                    "text": delegated_text,
                },
            )
        ],
    )

    text = payload["events"][0]["payload"]["text"]
    assert marker in text
    assert len(text) == len(delegated_text)


def test_tool_result_payload_preserves_wait_agent_text_body() -> None:
    marker = "WAIT_RESULT_MARKER"
    delegated_text = ("w" * 9000) + marker
    payload = tool_result_payload(
        "/wait_agent agent_1",
        "delegated",
        [
            ToolEvent(
                name="wait_agent",
                ok=True,
                summary="wait_agent completed",
                payload={
                    "target": "agent_1",
                    "status": "completed",
                    "text": delegated_text,
                },
            )
        ],
    )

    text = payload["events"][0]["payload"]["text"]
    assert marker in text
    assert len(text) == len(delegated_text)


def test_tool_result_payload_preserves_nested_result_contract_shape() -> None:
    payload = tool_result_payload(
        "/wait_agent agent_1",
        "delegated",
        [
            ToolEvent(
                name="wait_agent",
                ok=True,
                summary="wait_agent completed",
                payload={
                    "target": "agent_1",
                    "status": "completed",
                    "result_contract": {
                        "status": "completed",
                        "confidence": "high",
                        "touched_scope": ["/tmp/project/pkg/example.py"],
                        "artifact": {
                            "kind": "structured",
                            "format": "json",
                            "structured": {
                                "summary": "ok",
                                "files": ["pkg/example.py"],
                            },
                        },
                    },
                },
            )
        ],
    )

    event_payload = payload["events"][0]["payload"]
    assert event_payload["result_contract"]["artifact"]["kind"] == "structured"
    assert event_payload["result_contract"]["artifact"]["structured"]["summary"] == "ok"
    assert event_payload["result_contract"]["confidence"] == "high"
    assert event_payload["result_contract"]["touched_scope"] == ["/tmp/project/pkg/example.py"]


def test_command_for_tool_call_preserves_delegation_metadata() -> None:
    host = current_host_platform()
    spawn_command = command_for_tool_call(
        "spawn_agent",
        {
            "task": "并行验证 benchmark",
            "role": "subagent",
            "async": True,
            "reason": "verify_side_task",
            "mode": "background",
            "wait_required": False,
            "task_shape": "read_only",
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    wait_command = command_for_tool_call(
        "wait_agent",
        {
            "target": "agent_1",
            "timeout_ms": 250,
            "reason": "wait_for_child_result",
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert (
        spawn_command
        == '/spawn_agent \'{"task": "\\u5e76\\u884c\\u9a8c\\u8bc1 benchmark", "role": "subagent", "async": true, "reason": "verify_side_task", "mode": "background", "wait_required": false, "task_shape": "read_only"}\''
    )
    assert wait_command == "/wait_agent agent_1 --timeout-ms 250 --reason wait_for_child_result"


def test_claude_agent_explore_defaults_to_foreground_when_not_explicit() -> None:
    host = current_host_platform()
    command = anthropic_command_for_tool_call(
        "Agent",
        {
            "description": "scan repo",
            "prompt": "看看项目能力",
            "subagent_type": "Explore",
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        plugin_manager_factory=lambda: None,
    )

    assert (
        command
        == '/spawn_agent \'{"task": "\\u770b\\u770b\\u9879\\u76ee\\u80fd\\u529b", "role": "subagent", "reason": "research_side_task", "mode": "sync", "wait_required": false, "task_shape": "read_only", "subagent_type": "Explore"}\''
    )


def test_claude_agent_explore_preserves_explicit_foreground_hints() -> None:
    host = current_host_platform()
    foreground_command = anthropic_command_for_tool_call(
        "Agent",
        {
            "description": "scan repo",
            "prompt": "看看项目能力",
            "subagent_type": "Explore",
            "run_in_background": False,
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        plugin_manager_factory=lambda: None,
    )
    sync_command = anthropic_command_for_tool_call(
        "Agent",
        {
            "description": "scan repo",
            "prompt": "看看项目能力",
            "subagent_type": "Explore",
            "mode": "sync",
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        plugin_manager_factory=lambda: None,
    )

    assert (
        foreground_command
        == '/spawn_agent \'{"task": "\\u770b\\u770b\\u9879\\u76ee\\u80fd\\u529b", "role": "subagent", "async": false, "reason": "research_side_task", "mode": "sync", "wait_required": false, "task_shape": "read_only", "subagent_type": "Explore"}\''
    )
    assert (
        sync_command
        == '/spawn_agent \'{"task": "\\u770b\\u770b\\u9879\\u76ee\\u80fd\\u529b", "role": "subagent", "reason": "research_side_task", "mode": "sync", "wait_required": false, "task_shape": "read_only", "subagent_type": "Explore"}\''
    )


def test_command_for_tool_call_normalizes_legacy_file_aliases_to_canonical_commands() -> None:
    host = current_host_platform()
    legacy_search = command_for_tool_call(
        "file_search",
        {"query": "ProviderConfig", "path": "cli"},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    legacy_list = command_for_tool_call(
        "file_list",
        {"path": "cli", "limit": 5},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    legacy_read = command_for_tool_call(
        "file_read",
        {"path": "README.md", "offset": 3, "limit": 5},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert legacy_search == "/grep_files ProviderConfig --path cli"
    assert legacy_list == "/list_dir cli --limit 5"
    assert legacy_read == "/read_file README.md --offset 3 --limit 5"


def test_command_for_tool_call_routes_legacy_web_aliases_through_browser_entry() -> None:
    host = current_host_platform()
    open_command = command_for_tool_call(
        "open",
        {"url": "https://example.com/docs", "line": 2},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    click_command = command_for_tool_call(
        "click",
        {"ref_id": "page_1", "id": 1},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    find_command = command_for_tool_call(
        "find",
        {"ref_id": "page_1", "pattern": "Responses API"},
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert open_command == "/browser open_legacy --ref https://example.com/docs --line 2"
    assert click_command == "/browser click_legacy --ref page_1 --id 1"
    assert find_command == "/browser find_legacy --ref page_1 --text 'Responses API'"


def test_command_for_tool_call_normalizes_shell_alias_to_exec_command() -> None:
    host = current_host_platform()
    command = command_for_tool_call(
        "shell",
        {
            "command": "python -V",
            "workdir": "cli",
            "tty": True,
            "login": False,
            "yield_time_ms": 300,
            "max_output_tokens": 1200,
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    argv_command = command_for_tool_call(
        "shell",
        {
            "argv": ["python", "-c", "print('ok')"],
            "cwd": "cli/tests",
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert (
        command
        == "/exec_command 'python -V' --workdir cli --tty --login false --yield-time-ms 300 --max-output-tokens 1200"
    )
    assert argv_command is not None
    assert argv_command.startswith("/exec_command ")
    assert "--workdir cli/tests" in argv_command
    assert "python -c" in argv_command
    assert "/shell " not in argv_command


def test_command_for_bash_tool_call_uses_exec_command_with_explicit_shell_override() -> None:
    host = detect_host_platform(system_name="Windows", sys_platform="win32")
    command = command_for_tool_call(
        "Bash",
        {
            "command": "ls -la",
            "workdir": "cli",
            "timeout": 750,
            "run_in_background": True,
            "dangerouslyDisableSandbox": True,
            "description": "List workspace files",
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert command == (
        "/exec_command 'ls -la' --workdir cli --shell bash --yield-time-ms 250 --timeout-ms 750 "
        "--sandbox-permissions require_escalated --justification 'List workspace files'"
    )
    assert "Get-ChildItem" not in command


def test_command_for_powershell_tool_call_uses_exec_command_with_explicit_shell_override() -> None:
    host = detect_host_platform(system_name="Linux", sys_platform="linux")
    command = command_for_tool_call(
        "PowerShell",
        {
            "command": "Get-ChildItem -Force",
            "cwd": "cli",
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert (
        command
        == "/exec_command 'Get-ChildItem -Force' --workdir cli --shell powershell --yield-time-ms 15000"
    )
    assert "ls -la" not in command


def test_command_for_bash_tool_call_uses_short_initial_yield_when_background_requested() -> None:
    host = detect_host_platform(system_name="Linux", sys_platform="linux")
    command = command_for_tool_call(
        "Bash",
        {
            "command": "python -m http.server",
            "run_in_background": True,
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert command == "/exec_command 'python -m http.server' --shell bash --yield-time-ms 250"


def test_command_for_bash_tool_call_uses_claude_style_auto_background_threshold_by_default() -> (
    None
):
    host = detect_host_platform(system_name="Linux", sys_platform="linux")
    command = command_for_tool_call(
        "Bash",
        {
            "command": "pytest -q",
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert command == "/exec_command 'pytest -q' --shell bash --yield-time-ms 15000"


def test_command_for_bash_tool_call_preserves_explicit_timeout_budget() -> None:
    host = detect_host_platform(system_name="Linux", sys_platform="linux")
    command = command_for_tool_call(
        "Bash",
        {
            "command": "python -m http.server",
            "timeout": 30000,
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert (
        command
        == "/exec_command 'python -m http.server' --shell bash --yield-time-ms 15000 --timeout-ms 30000"
    )


def test_command_for_exec_command_keeps_timeout_and_yield_as_separate_flags() -> None:
    host = detect_host_platform(system_name="Linux", sys_platform="linux")
    command = command_for_tool_call(
        "exec_command",
        {
            "cmd": "python -m http.server",
            "shell": "bash",
            "yield_time_ms": 500,
            "timeout_ms": 30000,
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert (
        command
        == "/exec_command 'python -m http.server' --shell bash --yield-time-ms 500 --timeout-ms 30000"
    )


def test_command_for_exec_command_serializes_additional_permissions_json() -> None:
    host = detect_host_platform(system_name="Linux", sys_platform="linux")
    command = command_for_tool_call(
        "exec_command",
        {
            "cmd": "python -V",
            "additional_permissions": {
                "file_system": {
                    "read": ["/tmp/ref"],
                    "write": ["/tmp/out"],
                }
            },
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert command == (
        "/exec_command 'python -V' --sandbox-permissions with_additional_permissions "
        "--additional-permissions-json "
        '\'{"file_system": {"read": ["/tmp/ref"], "write": ["/tmp/out"]}}\''
    )


def test_command_for_tool_call_preserves_explicit_powershell_commands_on_unix_hosts() -> None:
    host = detect_host_platform(system_name="Linux", sys_platform="linux")
    command = command_for_tool_call(
        "exec_command",
        {
            "cmd": "Get-Location",
            "shell": "powershell",
            "yield_time_ms": 250,
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert command == "/exec_command Get-Location --shell powershell --yield-time-ms 250"
    assert "pwd" not in command


def test_tool_result_payload_marks_legacy_file_alias_usage() -> None:
    payload = tool_result_payload(
        "/file_search provider",
        "Search workspace files.",
        [
            ToolEvent(
                name="file_search",
                ok=True,
                summary="file matches=1",
                payload={"query": "provider"},
            )
        ],
    )

    assert payload["legacy_file_alias_used"] is True
    assert payload["legacy_file_alias_replacement"] == "grep_files + read_file/file_read"


def test_command_for_tool_call_apply_patch_supports_file_write_operation() -> None:
    host = current_host_platform()
    command = command_for_tool_call(
        "apply_patch",
        {
            "operation": "file_write",
            "file_path": "src/range_tools.py",
            "content": "def normalize_ranges():\n    return []\n",
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert command is not None
    payload = _decode_apply_patch_payload(command)
    assert payload == {
        "content": "def normalize_ranges():\n    return []\n",
        "file_path": "src/range_tools.py",
        "operation": "file_write",
    }


def test_command_for_tool_call_apply_patch_supports_file_edit_operation() -> None:
    host = current_host_platform()
    command = command_for_tool_call(
        "apply_patch",
        {
            "operation": "file_edit",
            "file_path": "README.md",
            "old_string": "TODO",
            "new_string": "DONE",
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert command is not None
    payload = _decode_apply_patch_payload(command)
    assert payload == {
        "file_path": "README.md",
        "new_string": "DONE",
        "old_string": "TODO",
        "operation": "file_edit",
    }


def test_command_for_tool_call_apply_patch_ignores_empty_legacy_patch_when_structured_file_write_present() -> (
    None
):
    host = current_host_platform()
    command = command_for_tool_call(
        "apply_patch",
        {
            "patch": "",
            "operation": "file_write",
            "file_path": "ticker.py",
            "content": "print('tick')\n",
            "old_string": "",
            "new_string": "",
            "replace_all": False,
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert command is not None
    payload = _decode_apply_patch_payload(command)
    assert payload == {
        "content": "print('tick')\n",
        "file_path": "ticker.py",
        "operation": "file_write",
    }


def test_command_for_tool_call_apply_patch_ignores_empty_legacy_patch_when_structured_file_edit_present() -> (
    None
):
    host = current_host_platform()
    command = command_for_tool_call(
        "apply_patch",
        {
            "patch": "",
            "operation": "file_edit",
            "file_path": "ticker.py",
            "old_string": "tick",
            "new_string": "tock",
            "replace_all": True,
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert command is not None
    payload = _decode_apply_patch_payload(command)
    assert payload == {
        "file_path": "ticker.py",
        "new_string": "tock",
        "old_string": "tick",
        "operation": "file_edit",
        "replace_all": True,
    }


def test_command_for_tool_call_file_write_name_routes_to_apply_patch() -> None:
    host = current_host_platform()
    command = command_for_tool_call(
        "file_write",
        {
            "file_path": "notes.txt",
            "content": "first line\n",
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert command is not None
    payload = _decode_apply_patch_payload(command)
    assert payload == {
        "content": "first line\n",
        "file_path": "notes.txt",
        "operation": "file_write",
    }


def test_command_for_tool_call_write_name_routes_to_apply_patch_with_guard_metadata() -> None:
    host = current_host_platform()
    command = command_for_tool_call(
        "Write",
        {
            "file_path": "notes.txt",
            "content": "fresh text\n",
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert command is not None
    payload = _decode_apply_patch_payload(command)
    assert payload == {
        "content": "fresh text\n",
        "file_path": "notes.txt",
        "guard_profile": "claude_write",
        "operation": "file_write",
        "source_tool_name": "Write",
    }


def test_command_for_tool_call_file_edit_replace_all_is_forwarded() -> None:
    host = current_host_platform()
    command = command_for_tool_call(
        "file_edit",
        {
            "file_path": "README.md",
            "old_string": "x",
            "new_string": "y",
            "replace_all": True,
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert command is not None
    payload = _decode_apply_patch_payload(command)
    assert payload == {
        "file_path": "README.md",
        "new_string": "y",
        "old_string": "x",
        "operation": "file_edit",
        "replace_all": True,
    }


def test_command_for_tool_call_edit_name_routes_to_apply_patch_with_guard_metadata() -> None:
    host = current_host_platform()
    command = command_for_tool_call(
        "Edit",
        {
            "file_path": "README.md",
            "old_string": "TODO",
            "new_string": "DONE",
            "replace_all": True,
        },
        host,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )

    assert command is not None
    payload = _decode_apply_patch_payload(command)
    assert payload == {
        "file_path": "README.md",
        "guard_profile": "claude_edit",
        "new_string": "DONE",
        "old_string": "TODO",
        "operation": "file_edit",
        "replace_all": True,
        "source_tool_name": "Edit",
    }
