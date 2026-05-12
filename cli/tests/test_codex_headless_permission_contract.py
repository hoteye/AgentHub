from __future__ import annotations

import io
import tempfile
from pathlib import Path
from types import SimpleNamespace

from cli.agent_cli.headless import run_headless
from cli.agent_cli.models import PromptResponse, ToolEvent
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    approval_request_text,
    bool_option,
    compact_arguments,
    error_event,
    error_result,
    int_option,
    text_only_result,
)
from cli.agent_cli.runtime_core.shell_command_handlers_exec_helpers_runtime import (
    handle_exec_command,
)
from cli.agent_cli.runtime_exec_policy_runtime import (
    evaluate_apply_patch_runtime_policy,
    evaluate_exec_command_runtime_policy,
    runtime_policy_axes,
)
from cli.agent_cli.runtime_policy import RuntimePolicy
from cli.agent_cli.runtime_policy_gateway_bindings_facade_runtime import (
    runtime_policy_status as projected_runtime_policy_status,
)

_READ_ONLY_REJECTED_TEXT = (
    "writing is blocked by read-only sandbox; rejected by user approval settings"
)


class _HeadlessRuntimeStub:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.runtime_policy_updates: list[dict[str, object]] = []

    def handle_prompt(self, prompt: str) -> PromptResponse:
        self.prompts.append(prompt)
        return PromptResponse(
            user_text=prompt,
            assistant_text="ok",
            status={"approval_policy": "never"},
        )

    def configure_runtime_policy(
        self,
        *,
        approval_policy=None,
        sandbox_mode=None,
        web_search_mode=None,
        network_access_enabled=None,
    ) -> dict[str, str]:
        self.runtime_policy_updates.append(
            {
                "approval_policy": approval_policy,
                "sandbox_mode": sandbox_mode,
                "web_search_mode": web_search_mode,
                "network_access_enabled": network_access_enabled,
            }
        )
        return {
            "approval_policy": str(approval_policy or ""),
            "sandbox_mode": str(sandbox_mode or ""),
            "web_search_mode": str(web_search_mode or ""),
            "network_access": "enabled" if network_access_enabled else "disabled",
        }


def _codex_provider_config() -> ProviderConfig:
    return ProviderConfig(
        model="gpt-5.4",
        api_key="test",
        provider_name="gac",
        model_key="gpt-5.4",
        interaction_profile="codex_openai",
        interaction_profile_source="test",
    )


def _claude_provider_config() -> ProviderConfig:
    return ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="test",
        provider_name="anthropic",
        model_key="claude-sonnet-4-6",
        interaction_profile="claude_code",
        interaction_profile_source="test",
    )


def _codex_headless_runtime(
    *,
    approval_policy: str = "on-request",
    sandbox_mode: str = "read-only",
    network_access_enabled: bool = True,
):
    planner = SimpleNamespace(config=_codex_provider_config())
    state = {"shell_approvals": 0, "shell_starts": 0}

    def _request_shell_approval(*args, **kwargs) -> ToolEvent:
        del args, kwargs
        state["shell_approvals"] += 1
        return ToolEvent(
            name="shell_approval_requested",
            ok=True,
            summary="approval requested",
            payload={"approval_id": "approval_test"},
        )

    def _start_shell_session(*args, **kwargs):
        del args, kwargs
        state["shell_starts"] += 1
        raise AssertionError(
            "start_shell_session should not run for codex headless read-only denial"
        )

    runtime = SimpleNamespace(
        _agenthub_headless_mode="prompt",
        agent=SimpleNamespace(_planner=planner),
        runtime_policy=SimpleNamespace(
            approval_policy=approval_policy,
            sandbox_mode=sandbox_mode,
            network_access_enabled=network_access_enabled,
        ),
        runtime_policy_status=lambda: {
            "approval_policy": approval_policy,
            "sandbox_mode": sandbox_mode,
            "network_access": "enabled" if network_access_enabled else "disabled",
        },
        _parse_args=lambda arg_text: ([str(arg_text or "").strip()], {}),
        request_shell_approval=_request_shell_approval,
        start_shell_session=_start_shell_session,
    )
    return runtime, state


def _claude_headless_runtime(
    *,
    approval_policy: str = "on-request",
    sandbox_mode: str = "workspace-write",
    network_access_enabled: bool = True,
):
    planner = SimpleNamespace(config=_claude_provider_config())
    state = {"shell_approvals": 0, "shell_starts": 0}

    def _request_shell_approval(*args, **kwargs) -> ToolEvent:
        del args, kwargs
        state["shell_approvals"] += 1
        return ToolEvent(
            name="shell_approval_requested",
            ok=True,
            summary="approval requested",
            payload={"approval_id": "approval_test"},
        )

    def _start_shell_session(*args, **kwargs):
        del args, kwargs
        state["shell_starts"] += 1
        raise AssertionError(
            "start_shell_session should not run for claude headless approval denial"
        )

    runtime = SimpleNamespace(
        _agenthub_headless_mode="prompt",
        agent=SimpleNamespace(_planner=planner),
        runtime_policy=SimpleNamespace(
            approval_policy=approval_policy,
            sandbox_mode=sandbox_mode,
            network_access_enabled=network_access_enabled,
        ),
        runtime_policy_status=lambda: {
            "approval_policy": approval_policy,
            "sandbox_mode": sandbox_mode,
            "network_access": "enabled" if network_access_enabled else "disabled",
        },
        _parse_args=lambda arg_text: ([str(arg_text or "").strip()], {}),
        request_shell_approval=_request_shell_approval,
        start_shell_session=_start_shell_session,
    )
    return runtime, state


def test_run_headless_marks_prompt_runtime_as_headless_prompt_mode() -> None:
    runtime = _HeadlessRuntimeStub()
    args = SimpleNamespace(
        headless=True,
        prompt="hello",
        stdin=False,
        output_format=None,
        json=False,
        jsonl=False,
        serve=False,
        provider_status=False,
        resume=None,
        resume_path=None,
        resume_last=False,
        permission_mode=None,
        approval_policy="never",
        sandbox_mode="read-only",
        web_search_mode="disabled",
        network_access="disabled",
    )

    exit_code = run_headless(args, runtime=runtime, stdout=io.StringIO(), stderr=io.StringIO())

    assert exit_code == 0
    assert runtime.prompts == ["hello"]
    assert getattr(runtime, "_agenthub_headless_mode", "") == "prompt"


def test_runtime_policy_axes_preserve_requested_policy_for_codex_headless_prompt() -> None:
    runtime, _state = _codex_headless_runtime()

    axes = runtime_policy_axes(runtime)

    assert axes["approval_policy"] == "on-request"
    assert axes["sandbox_mode"] == "read-only"
    assert axes["codex_noninteractive_headless"] is True


def test_runtime_policy_axes_marks_claude_headless_prompt_contract() -> None:
    runtime, _state = _claude_headless_runtime()

    axes = runtime_policy_axes(runtime)

    assert axes["approval_policy"] == "on-request"
    assert axes["sandbox_mode"] == "workspace-write"
    assert axes["codex_noninteractive_headless"] is False
    assert axes["claude_noninteractive_headless"] is True


def test_runtime_policy_status_preserves_requested_policy_for_codex_headless_prompt() -> None:
    runtime, _state = _codex_headless_runtime()
    runtime.runtime_policy = RuntimePolicy.normalized(
        approval_policy="on-request",
        sandbox_mode="read-only",
        web_search_mode="live",
        network_access_enabled=True,
    )

    status = projected_runtime_policy_status(runtime)

    assert status["approval_policy"] == "on-request"
    assert status["sandbox_mode"] == "read-only"
    assert status["web_search_mode"] == "live"
    assert status["network_access"] == "enabled"


def test_exec_command_policy_requests_approval_for_codex_headless_read_only_write() -> None:
    runtime, _state = _codex_headless_runtime()

    policy_state = evaluate_exec_command_runtime_policy(runtime, "printf 'hello' > note.txt")

    assert policy_state["approval_policy"] == "on-request"
    assert policy_state["requirement_payload"]["requirement"] == "needs_approval"
    assert policy_state["payload"]["reason_code"] == "exec.read_only.requires_approval"
    assert policy_state["payload"]["reason_text"] == (
        "Command writes to the filesystem and needs approval to leave the read-only sandbox."
    )
    assert "stderr" not in policy_state["payload"]
    assert "function_call_output" not in policy_state["payload"]


def test_handle_exec_command_requests_approval_for_codex_headless_read_only_write() -> None:
    runtime, state = _codex_headless_runtime()

    result = handle_exec_command(
        runtime,
        arg_text="printf 'hello' > note.txt",
        slash_invocation=None,
        compact_arguments=compact_arguments,
        int_option=int_option,
        bool_option=bool_option,
        error_event=error_event,
        error_result=error_result,
        text_only_result=text_only_result,
        approval_request_text=approval_request_text,
    )

    assert state["shell_approvals"] == 1
    assert state["shell_starts"] == 0
    assert result.tool_events[0].name == "shell_approval_requested"
    assert result.tool_events[0].payload["approval_policy"] == "on-request"
    assert result.tool_events[0].payload["reason_code"] == "exec.read_only.requires_approval"
    assert result.tool_events[0].payload["policy_decision"] == "requires_approval"
    assert result.item_events[-1]["item"]["type"] == "mcp_tool_call"
    assert result.item_events[-1]["item"]["tool"] == "exec_command"


def test_handle_exec_command_denies_codex_headless_read_only_write_without_approval_path() -> None:
    runtime, state = _codex_headless_runtime(approval_policy="never")

    result = handle_exec_command(
        runtime,
        arg_text="printf 'hello' > note.txt",
        slash_invocation=None,
        compact_arguments=compact_arguments,
        int_option=int_option,
        bool_option=bool_option,
        error_event=error_event,
        error_result=error_result,
        text_only_result=text_only_result,
        approval_request_text=approval_request_text,
    )

    assert state["shell_approvals"] == 0
    assert state["shell_starts"] == 0
    assert "Process exited with code 1" in result.assistant_text
    assert "Permission denied" in result.assistant_text
    assert result.tool_events[0].payload["approval_policy"] == "never"
    assert (
        result.tool_events[0].payload["stderr"] == "/bin/bash: line 1: note.txt: Permission denied"
    )
    assert result.tool_events[0].payload["function_call_output_model_visible"] is True
    assert result.item_events[-1]["item"]["type"] == "command_execution"
    assert (
        result.item_events[-1]["item"]["aggregated_output"]
        == "/bin/bash: line 1: note.txt: Permission denied"
    )
    assert result.item_events[-1]["item"]["status"] == "failed"


def test_handle_exec_command_requests_approval_for_codex_headless_workspace_write() -> None:
    runtime, state = _codex_headless_runtime(sandbox_mode="workspace-write")

    result = handle_exec_command(
        runtime,
        arg_text="touch note.txt",
        slash_invocation=None,
        compact_arguments=compact_arguments,
        int_option=int_option,
        bool_option=bool_option,
        error_event=error_event,
        error_result=error_result,
        text_only_result=text_only_result,
        approval_request_text=approval_request_text,
    )

    assert state["shell_approvals"] == 1
    assert state["shell_starts"] == 0
    assert result.tool_events[0].name == "shell_approval_requested"
    assert result.tool_events[0].payload["approval_policy"] == "on-request"
    assert result.tool_events[0].payload["policy_decision"] == "requires_approval"
    assert result.tool_events[0].payload["codex_noninteractive_headless"] is True


def test_exec_command_policy_requests_approval_for_codex_headless_pure_network() -> None:
    runtime, _state = _codex_headless_runtime(sandbox_mode="workspace-write")

    policy_state = evaluate_exec_command_runtime_policy(runtime, "curl -I https://example.com")

    assert policy_state["approval_policy"] == "on-request"
    assert policy_state["requirement_payload"]["requirement"] == "needs_approval"
    assert policy_state["payload"]["reason_code"] == "exec.network.requires_approval"
    assert policy_state["payload"]["network_access_enabled"] is True


def test_handle_exec_command_requests_approval_for_codex_headless_pure_network() -> None:
    runtime, state = _codex_headless_runtime(sandbox_mode="workspace-write")

    result = handle_exec_command(
        runtime,
        arg_text="curl -I https://example.com",
        slash_invocation=None,
        compact_arguments=compact_arguments,
        int_option=int_option,
        bool_option=bool_option,
        error_event=error_event,
        error_result=error_result,
        text_only_result=text_only_result,
        approval_request_text=approval_request_text,
    )

    assert state["shell_approvals"] == 1
    assert state["shell_starts"] == 0
    assert result.tool_events[0].name == "shell_approval_requested"
    assert result.tool_events[0].payload["approval_policy"] == "on-request"
    assert result.tool_events[0].payload["reason_code"] == "exec.network.requires_approval"
    assert result.tool_events[0].payload["policy_decision"] == "requires_approval"


def test_apply_patch_policy_emits_model_visible_denial_for_codex_headless_read_only() -> None:
    runtime, _state = _codex_headless_runtime()
    patch_text = """*** Begin Patch
*** Add File: note.txt
+hello
*** End Patch"""

    with tempfile.TemporaryDirectory() as temp_dir:
        policy_state = evaluate_apply_patch_runtime_policy(
            runtime,
            patch_text=patch_text,
            workspace_root=Path(temp_dir),
        )

    assert policy_state["approval_policy"] == "on-request"
    assert policy_state["requirement_payload"]["requirement"] == "forbidden"
    assert policy_state["payload"]["reason_text"] == _READ_ONLY_REJECTED_TEXT
    assert policy_state["payload"]["function_call_output"] == _READ_ONLY_REJECTED_TEXT
    assert policy_state["payload"]["function_call_output_model_visible"] is True


def test_exec_command_policy_denies_claude_headless_approval_request_without_pending_ticket() -> (
    None
):
    runtime, _state = _claude_headless_runtime(sandbox_mode="workspace-write")

    policy_state = evaluate_exec_command_runtime_policy(runtime, "curl -I https://example.com")

    assert policy_state["approval_policy"] == "on-request"
    assert policy_state["requirement_payload"]["requirement"] == "forbidden"
    assert policy_state["payload"]["claude_noninteractive_headless"] is True
    assert policy_state["payload"]["policy_decision"] == "blocked"
    assert policy_state["payload"]["reason_code"] == "exec.network.requires_approval"
    assert policy_state["payload"]["function_call_output_model_visible"] is True


def test_handle_exec_command_denies_claude_headless_approval_request_without_pending_ticket() -> (
    None
):
    runtime, state = _claude_headless_runtime(sandbox_mode="workspace-write")

    result = handle_exec_command(
        runtime,
        arg_text="curl -I https://example.com",
        slash_invocation=None,
        compact_arguments=compact_arguments,
        int_option=int_option,
        bool_option=bool_option,
        error_event=error_event,
        error_result=error_result,
        text_only_result=text_only_result,
        approval_request_text=approval_request_text,
    )

    assert state["shell_approvals"] == 0
    assert state["shell_starts"] == 0
    assert result.tool_events[0].name == "exec_command"
    assert result.tool_events[0].ok is False
    assert result.tool_events[0].payload["claude_noninteractive_headless"] is True
    assert result.tool_events[0].payload["policy_decision"] == "blocked"
    assert result.tool_events[0].payload["function_call_output_model_visible"] is True


def test_apply_patch_policy_denies_claude_headless_approval_request_without_pending_ticket() -> (
    None
):
    runtime, _state = _claude_headless_runtime(sandbox_mode="workspace-write")
    patch_text = """*** Begin Patch
*** Add File: note.txt
+hello
*** End Patch"""

    with tempfile.TemporaryDirectory() as temp_dir:
        policy_state = evaluate_apply_patch_runtime_policy(
            runtime,
            patch_text=patch_text,
            workspace_root=Path(temp_dir),
        )

    assert policy_state["approval_policy"] == "on-request"
    assert policy_state["requirement_payload"]["requirement"] == "forbidden"
    assert policy_state["payload"]["claude_noninteractive_headless"] is True
    assert policy_state["payload"]["policy_decision"] == "blocked"
    assert policy_state["payload"]["reason_code"] == "apply_patch_approval_required"
    assert policy_state["payload"]["function_call_output_model_visible"] is True


def test_handle_exec_command_requests_approval_for_codex_headless_read_only_rm() -> None:
    runtime, state = _codex_headless_runtime()

    result = handle_exec_command(
        runtime,
        arg_text="rm sentinel.txt",
        slash_invocation=None,
        compact_arguments=compact_arguments,
        int_option=int_option,
        bool_option=bool_option,
        error_event=error_event,
        error_result=error_result,
        text_only_result=text_only_result,
        approval_request_text=approval_request_text,
    )

    assert state["shell_approvals"] == 1
    assert state["shell_starts"] == 0
    assert result.tool_events[0].name == "shell_approval_requested"
    assert result.tool_events[0].payload["approval_policy"] == "on-request"
    assert result.tool_events[0].payload["reason_code"] == "exec.dangerous.requires_approval"


def test_handle_exec_command_keeps_policy_denial_for_codex_headless_read_only_rm_without_approval_path() -> (
    None
):
    runtime, state = _codex_headless_runtime(approval_policy="never")

    result = handle_exec_command(
        runtime,
        arg_text="rm sentinel.txt",
        slash_invocation=None,
        compact_arguments=compact_arguments,
        int_option=int_option,
        bool_option=bool_option,
        error_event=error_event,
        error_result=error_result,
        text_only_result=text_only_result,
        approval_request_text=approval_request_text,
    )

    assert state["shell_approvals"] == 0
    assert state["shell_starts"] == 0
    assert result.assistant_text == "blocked by policy"
    assert result.tool_events[0].payload["approval_policy"] == "never"
    assert result.tool_events[0].payload["reason_code"] == "exec.dangerous.forbidden.no_approval"
