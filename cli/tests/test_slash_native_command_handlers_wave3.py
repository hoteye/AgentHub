from __future__ import annotations

import json
from types import SimpleNamespace

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime_core import background_task_commands_runtime
from cli.agent_cli.runtime_core.command_handlers import handle_known_command
from cli.agent_cli.runtime_core.shell_command_handlers import handle_shell_command
from cli.agent_cli.runtime_core.thread_commands import handle_thread_and_agent_command
from cli.agent_cli.runtime_core.tool_call_context_runtime import active_provider_tool_call_id
from cli.agent_cli.slash_parser import parse_slash_invocation


def _int_option(value, default=None):
    if value in (None, ""):
        return default
    return int(value)


def _bool_option(value, default=False):
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean: {value}")


def _error_event(name, summary, **payload):
    return ToolEvent(name=name, ok=False, summary=summary, payload=payload)


def _error_result(event, arguments=None, tool_name=None):
    del arguments, tool_name
    return CommandExecutionResult(assistant_text=str(event.summary or ""), tool_events=[event], item_events=[])


def _text_only_result(text):
    return CommandExecutionResult(assistant_text=str(text), tool_events=[], item_events=[])


def _single_event_result(text, event, **kwargs):
    del kwargs
    return CommandExecutionResult(assistant_text=str(text), tool_events=[event], item_events=[])


def _approval_request_text(text, event):
    del event
    return text


def _parse_json_tool_arg(_arg_text: str):
    raise ValueError("not json")


def _decode_raw_text_arg(value: str) -> str:
    return str(value or "")


def _compact_arguments(arguments):
    return dict(arguments or {})


class _ShellRuntime:
    def __init__(self) -> None:
        self.start_calls: list[dict[str, object]] = []
        self.poll_calls: list[dict[str, object]] = []

    def _parse_args(self, arg_text: str):
        return [str(arg_text or "")], {}

    def patch_requires_approval(self) -> bool:
        return False

    def start_shell_session(self, command: str, **kwargs):
        self.start_calls.append({"command": command, **kwargs})
        return {
            "session_id": "session_1",
            "process_id": "process_1",
            "call_id": "call_1",
            "shell": kwargs.get("shell") or "/bin/bash",
        }

    def write_shell_stdin_result(self, session_id: str, chars: str, **kwargs):
        self.poll_calls.append({"session_id": session_id, "chars": chars, **kwargs})
        return CommandExecutionResult(
            assistant_text="Python 3.12\n",
            tool_events=[
                ToolEvent(
                    name="shell",
                    ok=True,
                    summary="shell rc=0",
                    payload={
                        "session_id": session_id,
                        "command": "python -V",
                        "stdout": "Python 3.12\n",
                        "returncode": 0,
                    },
                )
            ],
            item_events=[],
        )


def test_exec_command_slash_native_path_does_not_require_parse_args_or_arg_text() -> None:
    runtime = _ShellRuntime()
    result = handle_shell_command(
        runtime,
        name="exec_command",
        arg_text="",
        slash_invocation=parse_slash_invocation(
            "/exec_command python -V workdir cli shell /bin/zsh tty login false yield-time-ms 250"
        ),
        compact_arguments=_compact_arguments,
        int_option=_int_option,
        bool_option=_bool_option,
        error_event=_error_event,
        error_result=_error_result,
        text_only_result=_text_only_result,
        single_event_result=_single_event_result,
        approval_request_text=_approval_request_text,
    )

    assert isinstance(result, CommandExecutionResult)
    assert runtime.start_calls[0]["command"] == "python -V"
    assert runtime.start_calls[0]["cwd"] == "cli"
    assert runtime.start_calls[0]["shell"] == "/bin/zsh"
    assert runtime.start_calls[0]["tty"] is True
    assert runtime.start_calls[0]["login"] is False
    assert runtime.poll_calls[0]["yield_time_ms"] == 250
    assert result.tool_events[0].name == "exec_command"


def test_exec_command_slash_native_path_extended_flags_do_not_pollute_command() -> None:
    runtime = _ShellRuntime()
    result = handle_shell_command(
        runtime,
        name="exec_command",
        arg_text="",
        slash_invocation=parse_slash_invocation(
            "/exec_command 'ls -la' workdir cli shell /bin/zsh timeout-ms 30000 "
            "yield-time-ms 250 max-output-tokens 4000 "
            "sandbox-permissions use_default justification inspect prefix-rule git,pull"
        ),
        compact_arguments=_compact_arguments,
        int_option=_int_option,
        bool_option=_bool_option,
        error_event=_error_event,
        error_result=_error_result,
        text_only_result=_text_only_result,
        single_event_result=_single_event_result,
        approval_request_text=_approval_request_text,
    )

    assert isinstance(result, CommandExecutionResult)
    assert runtime.start_calls[0]["command"] == "ls -la"
    assert runtime.start_calls[0]["cwd"] == "cli"
    assert runtime.start_calls[0]["shell"] == "/bin/zsh"
    assert runtime.poll_calls[0]["yield_time_ms"] == 250
    assert result.tool_events[0].name == "exec_command"
    assert result.tool_events[0].payload["command"] == "ls -la"


def test_exec_command_slash_native_path_preserves_additional_permissions_payload() -> None:
    runtime = _ShellRuntime()
    result = handle_shell_command(
        runtime,
        name="exec_command",
        arg_text="",
        slash_invocation=parse_slash_invocation(
            "/exec_command 'ls -la' workdir cli shell /bin/zsh "
            "additional-permissions-json '{\"file_system\":{\"write\":[\"/tmp/out\"]}}'"
        ),
        compact_arguments=_compact_arguments,
        int_option=_int_option,
        bool_option=_bool_option,
        error_event=_error_event,
        error_result=_error_result,
        text_only_result=_text_only_result,
        single_event_result=_single_event_result,
        approval_request_text=_approval_request_text,
    )

    assert isinstance(result, CommandExecutionResult)
    assert runtime.start_calls[0]["command"] == "ls -la"
    assert "additional_permissions" not in runtime.start_calls[0]
    assert result.tool_events[0].payload["additional_permissions"] == {
        "file_system": {"write": ["/tmp/out"]}
    }
    assert result.tool_events[0].payload["function_call_arguments"]["additional_permissions"] == {
        "file_system": {"write": ["/tmp/out"]}
    }


def test_exec_command_respects_explicit_user_ban_without_starting_shell() -> None:
    runtime = _ShellRuntime()
    runtime._active_run_text = (
        "Use the apply_patch tool, and do not use exec_command, to create note.txt."
    )

    with active_provider_tool_call_id("call_exec_blocked_1"):
        result = handle_shell_command(
            runtime,
            name="exec_command",
            arg_text="",
            slash_invocation=parse_slash_invocation(
                "/exec_command apply_patch <<'PATCH'\n*** Begin Patch\n*** Add File: note.txt\n+hello\n*** End Patch\nPATCH"
            ),
            compact_arguments=_compact_arguments,
            int_option=_int_option,
            bool_option=_bool_option,
            error_event=_error_event,
            error_result=_error_result,
            text_only_result=_text_only_result,
            single_event_result=_single_event_result,
            approval_request_text=_approval_request_text,
        )

    assert isinstance(result, CommandExecutionResult)
    assert runtime.start_calls == []
    assert runtime.poll_calls == []
    assert result.tool_events == []
    assert "explicitly told me not to use it" in result.assistant_text
    assert len(result.item_events) == 1
    item_event = result.item_events[0]
    assert item_event["type"] == "item.completed"
    assert item_event["item"]["id"] == "item_0"
    assert item_event["item"]["type"] == "function_call_output"
    assert item_event["item"]["call_id"] == "call_exec_blocked_1"
    assert item_event["item"]["success"] is False


def test_exec_command_intercepts_inline_apply_patch_without_starting_shell(tmp_path, monkeypatch) -> None:
    runtime = _ShellRuntime()
    monkeypatch.chdir(tmp_path)

    with active_provider_tool_call_id("call_exec_patch_1"):
        result = handle_shell_command(
            runtime,
            name="exec_command",
            arg_text=(
                "apply_patch <<'PATCH'\n"
                "*** Begin Patch\n"
                "*** Add File: note.txt\n"
                "+hello\n"
                "*** End Patch\n"
                "PATCH"
            ),
            slash_invocation=None,
            compact_arguments=_compact_arguments,
            int_option=_int_option,
            bool_option=_bool_option,
            error_event=_error_event,
            error_result=_error_result,
            text_only_result=_text_only_result,
            single_event_result=_single_event_result,
            approval_request_text=_approval_request_text,
        )

    assert isinstance(result, CommandExecutionResult)
    assert runtime.start_calls == []
    assert runtime.poll_calls == []
    assert (tmp_path / "note.txt").read_text(encoding="utf-8") == "hello\n"
    assert [event.name for event in result.tool_events] == ["exec_command"]
    assert result.tool_events[0].payload["provider_call_id"] == "call_exec_patch_1"
    assert result.tool_events[0].payload["function_call_output_model_visible"] is True
    assert result.tool_events[0].payload["inline_apply_patch_intercepted"] is True
    assert result.tool_events[0].payload["function_call_output"].startswith("Exit code: 0\nWall time: ")
    assert "Success. Updated the following files:\nA note.txt" in result.tool_events[0].payload["function_call_output"]
    assert [event["type"] for event in result.item_events] == ["item.started", "item.completed"]
    completed_item = result.item_events[-1]["item"]
    assert completed_item["type"] == "mcp_tool_call"
    assert completed_item["tool"] == "apply_patch"
    assert completed_item["call_id"] == "call_exec_patch_1"
    assert completed_item["status"] == "completed"


def test_write_stdin_slash_native_path_does_not_require_parse_args_or_arg_text() -> None:
    runtime = _ShellRuntime()
    result = handle_shell_command(
        runtime,
        name="write_stdin",
        arg_text="",
        slash_invocation=parse_slash_invocation("/write_stdin session_1 ping yield-time-ms 300"),
        compact_arguments=_compact_arguments,
        int_option=_int_option,
        bool_option=_bool_option,
        error_event=_error_event,
        error_result=_error_result,
        text_only_result=_text_only_result,
        single_event_result=_single_event_result,
        approval_request_text=_approval_request_text,
    )

    assert isinstance(result, CommandExecutionResult)
    assert runtime.poll_calls[0]["session_id"] == "session_1"
    assert runtime.poll_calls[0]["chars"] == "ping"
    assert runtime.poll_calls[0]["yield_time_ms"] == 300
    assert result.tool_events[0].name == "write_stdin"


def test_write_stdin_slash_native_path_preserves_quoted_newline_chars() -> None:
    runtime = _ShellRuntime()
    result = handle_shell_command(
        runtime,
        name="write_stdin",
        arg_text="",
        slash_invocation=parse_slash_invocation("/write_stdin session_1 'stop\n' --yield-time-ms 300"),
        compact_arguments=_compact_arguments,
        int_option=_int_option,
        bool_option=_bool_option,
        error_event=_error_event,
        error_result=_error_result,
        text_only_result=_text_only_result,
        single_event_result=_single_event_result,
        approval_request_text=_approval_request_text,
    )

    assert isinstance(result, CommandExecutionResult)
    assert runtime.poll_calls[0]["session_id"] == "session_1"
    assert runtime.poll_calls[0]["chars"] == "stop\n"
    assert runtime.poll_calls[0]["yield_time_ms"] == 300
    assert result.tool_events[0].name == "write_stdin"


class _ApprovalsRuntime:
    def __init__(self) -> None:
        self.tools = SimpleNamespace(_plugin_manager=None)
        self.approval_queries: list[tuple[int, str | None]] = []
        self.approval_decisions: list[tuple[str, str, str]] = []

    def _is_interrupt_requested(self) -> bool:
        return False

    def approvals_event(self, *, limit=20, status=None):
        self.approval_queries.append((limit, status))
        return ToolEvent(name="approvals", ok=True, summary="approvals=1", payload={"limit": limit, "status": status})

    def decide_approval(self, approval_id, *, approved=None, decision=None, decided_by, decision_note=""):
        assert decided_by == "cli"
        resolved_decision = str(decision or ("accept" if approved else "decline"))
        approved = resolved_decision in {"accept", "accept_for_session", "accept_with_execpolicy_amendment"}
        self.approval_decisions.append((approval_id, resolved_decision, decision_note))
        return {
            "tool_events": [
                ToolEvent(
                    name="approval_decision",
                    ok=True,
                    summary="decision recorded",
                    payload={
                        "approval_id": approval_id,
                        "status": "approved" if approved else "rejected",
                        "decision_note": decision_note,
                    },
                )
            ]
        }


def test_approvals_and_approve_slash_native_paths_do_not_require_parse_args() -> None:
    runtime = _ApprovalsRuntime()

    approvals_result = handle_known_command(
        runtime,
        name="approvals",
        arg_text="",
        text="/approvals status pending limit 5",
        slash_invocation=parse_slash_invocation("/approvals status pending limit 5"),
    )
    approve_result = handle_known_command(
        runtime,
        name="approve",
        arg_text="",
        text="/approve approval_1 mode session note looks_good",
        slash_invocation=parse_slash_invocation("/approve approval_1 mode session note looks_good"),
    )
    reject_result = handle_known_command(
        runtime,
        name="reject",
        arg_text="",
        text="/reject approval_2 mode cancel note not_now",
        slash_invocation=parse_slash_invocation("/reject approval_2 mode cancel note not_now"),
    )

    assert isinstance(approvals_result, CommandExecutionResult)
    assert isinstance(approve_result, CommandExecutionResult)
    assert isinstance(reject_result, CommandExecutionResult)
    assert runtime.approval_queries == [(5, "pending")]
    assert runtime.approval_decisions == [
        ("approval_1", "accept_for_session", "looks_good"),
        ("approval_2", "cancel", "not_now"),
    ]
    assert approve_result.tool_events[0].payload["decision_note"] == "looks_good"
    assert approve_result.tool_events[0].payload["status"] == "approved"
    assert reject_result.tool_events[0].payload["status"] == "rejected"


class _ThreadRuntime:
    def __init__(self) -> None:
        self.thread_store = SimpleNamespace(get_active_thread_id=lambda: "thread_current")
        self.thread_id = "thread_current"
        self.send_calls: list[dict[str, object]] = []
        self.wait_calls: list[dict[str, object]] = []
        self.wait_many_calls: list[dict[str, object]] = []

    def list_threads(self, *, limit: int):
        return [{"thread_id": "thread_current", "name": f"main-{limit}", "path": "/tmp/thread_current.jsonl"}]

    def describe_thread(self, item, *, status, turns):
        del turns
        described = dict(item)
        described["status"] = status
        return described

    def wait_agent_result(self, target: str, **kwargs):
        self.wait_calls.append({"target": target, **kwargs})
        return CommandExecutionResult(
            assistant_text="wait_agent completed",
            tool_events=[ToolEvent(name="wait_agent", ok=True, summary="wait_agent completed", payload={"target": target, **kwargs})],
            item_events=[],
        )

    def wait_agents_result(
        self,
        targets: list[str],
        *,
        timeout_ms=None,
        reason=None,
        wait_required=None,
        codex_style: bool = False,
        **kwargs,
    ):
        self.wait_many_calls.append(
            {
                "targets": list(targets),
                "timeout_ms": timeout_ms,
                "reason": reason,
                "wait_required": wait_required,
                "codex_style": codex_style,
                **kwargs,
            }
        )
        return CommandExecutionResult(
            assistant_text="wait_agents completed",
            tool_events=[
                ToolEvent(
                    name="wait_agent",
                    ok=True,
                    summary="wait_agents completed",
                    payload={
                        "ids": list(targets),
                        "timeout_ms": timeout_ms,
                        "reason": reason,
                        "wait_required": wait_required,
                        "codex_style": codex_style,
                        **kwargs,
                    },
                )
            ],
            item_events=[],
        )

    def send_input_result(
        self,
        target: str,
        *,
        message: str,
        interrupt: bool = False,
        input_items=None,
        codex_style: bool = False,
    ):
        self.send_calls.append(
            {
                "target": target,
                "message": message,
                "interrupt": interrupt,
                "input_items": [dict(item) for item in list(input_items or [])] if input_items is not None else None,
                "codex_style": codex_style,
            }
        )
        return CommandExecutionResult(
            assistant_text="send_input completed",
            tool_events=[
                ToolEvent(
                    name="send_input",
                    ok=True,
                    summary="send_input completed",
                    payload={
                        "target": target,
                        "message": message,
                        "interrupt": interrupt,
                        "input_items": [dict(item) for item in list(input_items or [])] if input_items is not None else None,
                        "codex_style": codex_style,
                    },
                )
            ],
            item_events=[],
        )


def test_thread_commands_slash_native_paths_do_not_require_parse_args() -> None:
    runtime = _ThreadRuntime()

    threads_result = handle_thread_and_agent_command(
        runtime,
        name="threads",
        arg_text="",
        slash_invocation=parse_slash_invocation("/threads limit 7"),
        parse_json_tool_arg=_parse_json_tool_arg,
        int_option=_int_option,
        bool_option=_bool_option,
        decode_raw_text_arg=_decode_raw_text_arg,
        single_event_result=_single_event_result,
        text_only_result=_text_only_result,
        error_result=_error_result,
        error_event=_error_event,
    )
    wait_result = handle_thread_and_agent_command(
        runtime,
        name="wait_agent",
        arg_text="",
        slash_invocation=parse_slash_invocation("/wait_agent agent_1 timeout-ms 250 reason wait_for_child_result"),
        parse_json_tool_arg=_parse_json_tool_arg,
        int_option=_int_option,
        bool_option=_bool_option,
        decode_raw_text_arg=_decode_raw_text_arg,
        single_event_result=_single_event_result,
        text_only_result=_text_only_result,
        error_result=_error_result,
        error_event=_error_event,
    )

    assert threads_result == ("threads=1\nactive_thread_id=thread_current\nid=thread_current - name=main-7 - status=idle - path=/tmp/thread_current.jsonl", [])
    assert isinstance(wait_result, CommandExecutionResult)
    assert runtime.wait_calls == [{"target": "agent_1", "timeout_ms": "250", "reason": "wait_for_child_result", "wait_required": True}]


def test_thread_commands_json_send_input_items_and_wait_ids_paths() -> None:
    runtime = _ThreadRuntime()

    send_result = handle_thread_and_agent_command(
        runtime,
        name="send_input",
        arg_text='{"id":"agent_1","items":[{"type":"text","text":"继续检查"},{"type":"mention","name":"repo","path":"app://repo"}],"interrupt":true}',
        parse_json_tool_arg=json.loads,
        int_option=_int_option,
        bool_option=_bool_option,
        decode_raw_text_arg=_decode_raw_text_arg,
        single_event_result=_single_event_result,
        text_only_result=_text_only_result,
        error_result=_error_result,
        error_event=_error_event,
    )
    wait_result = handle_thread_and_agent_command(
        runtime,
        name="wait_agent",
        arg_text='{"ids":["agent_1","agent_2"],"timeout_ms":750}',
        parse_json_tool_arg=json.loads,
        int_option=_int_option,
        bool_option=_bool_option,
        decode_raw_text_arg=_decode_raw_text_arg,
        single_event_result=_single_event_result,
        text_only_result=_text_only_result,
        error_result=_error_result,
        error_event=_error_event,
    )

    assert isinstance(send_result, CommandExecutionResult)
    assert isinstance(wait_result, CommandExecutionResult)
    assert runtime.send_calls == [
        {
            "target": "agent_1",
            "message": "继续检查\n[mention:$repo](app://repo)",
            "interrupt": True,
            "input_items": [
                {"type": "text", "text": "继续检查"},
                {"type": "mention", "name": "repo", "path": "app://repo"},
            ],
            "codex_style": True,
        }
    ]
    assert runtime.wait_many_calls == [
        {
            "targets": ["agent_1", "agent_2"],
            "timeout_ms": "750",
            "reason": None,
            "wait_required": True,
            "codex_style": True,
        }
    ]


def test_background_command_slash_native_paths_do_not_require_parse_args() -> None:
    invocation = parse_slash_invocation("/background_tasks limit 9")
    result = background_task_commands_runtime.handle_background_task_command(
        SimpleNamespace(),
        name="background_tasks",
        arg_text="",
        slash_invocation=invocation,
        int_option=_int_option,
        workflows_text_fn=lambda runtime, *, limit: f"workflows={limit}",
        background_tasks_text_fn=lambda runtime, *, limit: f"background_tasks={limit}",
        background_worker_status_text_fn=lambda runtime: "status",
        background_worker_start_text_fn=lambda runtime, *, raw_args: raw_args,
        background_worker_stop_text_fn=lambda runtime, *, raw_args: raw_args,
        background_worker_run_once_text_fn=lambda runtime, *, raw_args: raw_args,
        submit_background_benchmark_fn=lambda runtime, *, raw_args: raw_args,
        submit_background_smoke_fn=lambda runtime, *, raw_args: raw_args,
        handle_background_teammate_fn=lambda runtime, *, arg_text, slash_invocation=None: (arg_text, []),
        background_task_status_text_fn=lambda runtime, *, task_id: task_id,
        background_task_cancel_text_fn=lambda runtime, *, task_id: task_id,
        background_task_retry_text_fn=lambda runtime, *, task_id: task_id,
        background_task_apply_text_fn=lambda runtime, *, task_id: task_id,
        background_task_reject_text_fn=lambda runtime, *, task_id: task_id,
    )

    assert result == ("background_tasks=9", [])


def test_background_worker_start_slash_native_path_rebuilds_compat_args_from_invocation() -> None:
    invocation = parse_slash_invocation("/background_worker_start max-jobs 2 poll-interval 1 stale-after-seconds 30")
    result = background_task_commands_runtime.handle_background_task_command(
        SimpleNamespace(),
        name="background_worker_start",
        arg_text="",
        slash_invocation=invocation,
        int_option=_int_option,
        workflows_text_fn=lambda runtime, *, limit: f"workflows={limit}",
        background_tasks_text_fn=lambda runtime, *, limit: f"background_tasks={limit}",
        background_worker_status_text_fn=lambda runtime: "status",
        background_worker_start_text_fn=lambda runtime, *, raw_args: raw_args,
        background_worker_stop_text_fn=lambda runtime, *, raw_args: raw_args,
        background_worker_run_once_text_fn=lambda runtime, *, raw_args: raw_args,
        submit_background_benchmark_fn=lambda runtime, *, raw_args: raw_args,
        submit_background_smoke_fn=lambda runtime, *, raw_args: raw_args,
        handle_background_teammate_fn=lambda runtime, *, arg_text, slash_invocation=None: (arg_text, []),
        background_task_status_text_fn=lambda runtime, *, task_id: task_id,
        background_task_cancel_text_fn=lambda runtime, *, task_id: task_id,
        background_task_retry_text_fn=lambda runtime, *, task_id: task_id,
        background_task_apply_text_fn=lambda runtime, *, task_id: task_id,
        background_task_reject_text_fn=lambda runtime, *, task_id: task_id,
    )

    assert result == ("--max-jobs 2 --poll-interval 1 --stale-after-seconds 30", [])


def test_background_teammate_slash_native_path_does_not_call_legacy_option_parser() -> None:
    calls: list[str] = []

    def _fail_parse_option_tokens(*args, **kwargs):
        raise AssertionError("legacy option parsing should not run")

    def _submit_background_teammate(_runtime, *, raw_args: str) -> str:
        calls.append(raw_args)
        return "submitted"

    result = background_task_commands_runtime.handle_background_teammate_command(
        SimpleNamespace(cwd="/tmp/workspace"),
        arg_text="",
        parse_option_tokens_fn=_fail_parse_option_tokens,
        parse_csv_paths_fn=lambda value: [] if value in (None, "") else [str(value)],
        parse_positive_float_fn=lambda value, *, option_name: float(value),
        submit_background_teammate_fn=_submit_background_teammate,
        slash_invocation=parse_slash_invocation(
            "/background_teammate summarize provider openai model gpt_54 timeout-seconds 30"
        ),
    )

    assert result == ("submitted", [])
    assert calls == [""]
