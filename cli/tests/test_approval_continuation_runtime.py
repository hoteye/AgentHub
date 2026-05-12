from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cli.agent_cli.core.provider_session import ProviderSessionResult, ProviderToolCall
from cli.agent_cli.core.turn_engine import TurnEngine
from cli.agent_cli.gateway_core import (
    InMemoryGatewayStateStore,
    create_action_request,
    create_approval_ticket,
)
from cli.agent_cli.models import AgentIntent, ToolEvent
from cli.agent_cli.providers.anthropic_claude import AnthropicMessagesSession
from cli.agent_cli.runtime_core.command_dispatch import run_command_text_result
from cli.agent_cli.runtime_services import (
    approval_continuation_runtime,
    approval_resolution_runtime,
    gateway_diagnostics_runtime,
)


class _FakeSession:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def send(
        self,
        *,
        input_items: list[dict[str, Any]],
        allow_tools: bool,
        previous_response_id: str | None = None,
        prompt_cache_key: str | None = None,
        turn_event_callback: Any = None,
    ) -> ProviderSessionResult:
        self.calls.append(
            {
                "input_items": input_items,
                "allow_tools": allow_tools,
                "previous_response_id": previous_response_id,
                "prompt_cache_key": prompt_cache_key,
                "turn_event_callback": turn_event_callback,
            }
        )
        return ProviderSessionResult(
            output_text="",
            response_id="resp_approval",
            tool_calls=[
                ProviderToolCall(
                    call_id="call_shell_1",
                    name="exec_command",
                    arguments={"cmd": "echo hi"},
                    item_type="local_shell_call",
                    raw_item={"type": "local_shell_call"},
                )
            ],
            continuation_input_items=[{"type": "function_call", "call_id": "call_shell_1"}],
        )


@dataclass
class _RuntimeOwner:
    gateway_state_store: InMemoryGatewayStateStore

    def save_gateway_action_request(self, item: Any) -> Any:
        return self.gateway_state_store.save_action_request(item)

    def save_gateway_approval_ticket(self, item: Any) -> Any:
        return self.gateway_state_store.save_approval_ticket(item)


class _ToolExecutor:
    def __init__(self, runtime_owner: _RuntimeOwner, approval_id: str) -> None:
        self.runtime_owner = runtime_owner
        self.approval_id = approval_id

    def __call__(self, _command_text: str) -> tuple[str, list[ToolEvent]]:
        return "approval required", [
            ToolEvent(
                name="shell_approval_requested",
                ok=True,
                summary="shell approval requested",
                payload={
                    "approval_id": self.approval_id,
                    "provider_call_id": "call_shell_1",
                    "function_call_name": "exec_command",
                    "function_call_arguments": {"cmd": "echo hi"},
                    "provider_tool_type": "local_shell_call",
                    "provider_raw_item": {"type": "local_shell_call"},
                },
            )
        ]


class _AnthropicReplaySession:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def send(
        self,
        *,
        input_items: list[dict[str, Any]],
        allow_tools: bool,
        previous_response_id: str | None = None,
        prompt_cache_key: str | None = None,
        turn_event_callback: Any = None,
    ) -> ProviderSessionResult:
        self.calls.append(
            {
                "input_items": input_items,
                "allow_tools": allow_tools,
                "previous_response_id": previous_response_id,
                "prompt_cache_key": prompt_cache_key,
                "turn_event_callback": turn_event_callback,
            }
        )
        if len(self.calls) == 1:
            return ProviderSessionResult(
                output_text="",
                response_id="msg_agent",
                tool_calls=[
                    ProviderToolCall(
                        call_id="tooluse_agent_1",
                        name="Agent",
                        arguments={"prompt": "inspect project"},
                        item_type="tool_use",
                        raw_item={
                            "type": "tool_use",
                            "id": "tooluse_agent_1",
                            "name": "Agent",
                            "input": {"prompt": "inspect project"},
                        },
                    )
                ],
                continuation_input_items=[],
            )
        return ProviderSessionResult(
            output_text="",
            response_id="msg_bash",
            tool_calls=[
                ProviderToolCall(
                    call_id="tooluse_bash_1",
                    name="Bash",
                    arguments={"command": "ls providers"},
                    item_type="tool_use",
                    raw_item={
                        "type": "tool_use",
                        "id": "tooluse_bash_1",
                        "name": "Bash",
                        "input": {"command": "ls providers"},
                    },
                )
            ],
            continuation_input_items=[],
        )


class _AnthropicReplayToolExecutor:
    def __init__(self, runtime_owner: _RuntimeOwner, approval_id: str) -> None:
        self.runtime_owner = runtime_owner
        self.approval_id = approval_id

    def __call__(self, command_text: str) -> tuple[str, list[ToolEvent]]:
        if '"name": "Agent"' in command_text:
            return "agent explored", [
                ToolEvent(
                    name="Agent",
                    ok=True,
                    summary="agent completed",
                    payload={
                        "function_call_output": "project summary",
                        "function_call_output_model_visible": True,
                    },
                )
            ]
        return "approval required", [
            ToolEvent(
                name="shell_approval_requested",
                ok=True,
                summary="shell approval requested",
                payload={
                    "approval_id": self.approval_id,
                    "provider_call_id": "tooluse_bash_1",
                    "function_call_name": "Bash",
                    "function_call_arguments": {"command": "ls providers"},
                    "provider_tool_type": "tool_use",
                    "provider_raw_item": {
                        "type": "tool_use",
                        "id": "tooluse_bash_1",
                        "name": "Bash",
                        "input": {"command": "ls providers"},
                    },
                },
            )
        ]


class _PatchDecisionTools:
    def __init__(self, function_call_output: str) -> None:
        self.function_call_output = function_call_output
        self.calls: list[str] = []

    def apply_patch(self, patch_text: str) -> ToolEvent:
        self.calls.append(patch_text)
        return ToolEvent(
            name="apply_patch",
            ok=True,
            summary="apply_patch files=1",
            payload={
                "file_count": 1,
                "function_call_output": self.function_call_output,
                "function_call_output_model_visible": True,
            },
        )


class _PatchDecisionRuntime(_RuntimeOwner):
    def __init__(
        self, gateway_state_store: InMemoryGatewayStateStore, tools: _PatchDecisionTools
    ) -> None:
        super().__init__(gateway_state_store=gateway_state_store)
        self.tools = tools
        self.audit_records: list[Any] = []

    def append_gateway_audit_record(self, item: Any) -> None:
        self.audit_records.append(item)


class _PatchFakeSession:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def send(
        self,
        *,
        input_items: list[dict[str, Any]],
        allow_tools: bool,
        previous_response_id: str | None = None,
        prompt_cache_key: str | None = None,
        turn_event_callback: Any = None,
    ) -> ProviderSessionResult:
        self.calls.append(
            {
                "input_items": input_items,
                "allow_tools": allow_tools,
                "previous_response_id": previous_response_id,
                "prompt_cache_key": prompt_cache_key,
                "turn_event_callback": turn_event_callback,
            }
        )
        return ProviderSessionResult(
            output_text="",
            response_id="resp_patch_approval",
            tool_calls=[
                ProviderToolCall(
                    call_id="call_patch_1",
                    name="apply_patch",
                    arguments={
                        "patch": "*** Begin Patch\n*** Add File: hello.txt\n+hi\n*** End Patch"
                    },
                    item_type="function_call",
                    raw_item={"type": "function_call", "name": "apply_patch"},
                )
            ],
            continuation_input_items=[
                {"type": "function_call", "call_id": "call_patch_1", "name": "apply_patch"}
            ],
        )


class _PatchToolExecutor:
    def __init__(self, runtime_owner: _RuntimeOwner, approval_id: str) -> None:
        self.runtime_owner = runtime_owner
        self.approval_id = approval_id

    def __call__(self, _command_text: str) -> tuple[str, list[ToolEvent]]:
        return "patch approval required", [
            ToolEvent(
                name="patch_approval_requested",
                ok=True,
                summary="patch approval requested",
                payload={
                    "approval_id": self.approval_id,
                    "provider_call_id": "call_patch_1",
                    "function_call_name": "apply_patch",
                    "function_call_arguments": {
                        "patch": "*** Begin Patch\n*** Add File: hello.txt\n+hi\n*** End Patch"
                    },
                    "provider_tool_type": "function_call",
                    "provider_raw_item": {"type": "function_call", "name": "apply_patch"},
                },
            )
        ]


def test_turn_engine_stores_pending_tool_continuation_for_shell_approval() -> None:
    store = InMemoryGatewayStateStore()
    action = create_action_request(
        action_type="shell_command",
        connector_key="local",
        plugin_name="builtin",
        trace_id="trace_approval_continuation",
        requested_by="test",
        payload={"command": "echo hi"},
        metadata={},
        approval_required=True,
    )
    store.save_action_request(action)
    ticket = create_approval_ticket(action, requested_by="test", reason="needs approval")
    store.save_approval_ticket(ticket)
    runtime_owner = _RuntimeOwner(gateway_state_store=store)

    engine = TurnEngine(
        _FakeSession(),
        tool_executor=_ToolExecutor(runtime_owner, ticket.approval_id),
    )

    intent = engine.run(
        user_text="run echo",
        initial_input=[{"role": "user", "content": "run echo"}],
    )

    assert "approval" in intent.assistant_text.lower()
    updated_action = store.get_action_request(action.action_id)
    updated_ticket = store.get_approval_ticket(ticket.approval_id)
    assert updated_action is not None
    assert updated_ticket is not None
    continuation = updated_action.metadata["pending_tool_continuation"]
    assert updated_ticket.metadata["pending_tool_continuation"] == continuation
    assert continuation["schema_version"] == 1
    assert continuation["approval_id"] == ticket.approval_id
    assert continuation["action_id"] == action.action_id
    assert continuation["previous_response_id"] == "resp_approval"
    assert continuation["provider_call_id"] == "call_shell_1"
    assert continuation["function_call_name"] == "exec_command"
    assert continuation["function_call_arguments"] == {"cmd": "echo hi"}
    assert continuation["provider_tool_type"] == "local_shell_call"
    assert continuation["replay_input_items"] == [{"role": "user", "content": "run echo"}]
    assert continuation["status"] == "pending"


def test_turn_engine_preserves_anthropic_full_replay_before_later_approval() -> None:
    store = InMemoryGatewayStateStore()
    action = create_action_request(
        action_type="shell_command",
        connector_key="local",
        plugin_name="builtin",
        trace_id="trace_anthropic_replay_continuation",
        requested_by="test",
        payload={"command": "ls providers"},
        metadata={},
        approval_required=True,
    )
    store.save_action_request(action)
    ticket = create_approval_ticket(action, requested_by="test", reason="needs approval")
    store.save_approval_ticket(ticket)
    runtime_owner = _RuntimeOwner(gateway_state_store=store)

    engine = TurnEngine(
        _AnthropicReplaySession(),
        tool_executor=_AnthropicReplayToolExecutor(runtime_owner, ticket.approval_id),
        max_rounds=3,
    )

    intent = engine.run(
        user_text="inspect project",
        initial_input=[{"role": "user", "content": "inspect project"}],
    )

    assert "approval" in intent.assistant_text.lower()
    updated_action = store.get_action_request(action.action_id)
    assert updated_action is not None
    continuation = updated_action.metadata["pending_tool_continuation"]
    assert continuation["provider_call_id"] == "tooluse_bash_1"
    replay_items = continuation["replay_input_items"]
    assert replay_items[0] == {"role": "user", "content": "inspect project"}
    assert any(
        item.get("type") == "function_call" and item.get("call_id") == "tooluse_agent_1"
        for item in replay_items
    )
    assert any(
        item.get("type") == "function_call_output" and item.get("call_id") == "tooluse_agent_1"
        for item in replay_items
    )
    assert not any(item.get("call_id") == "tooluse_bash_1" for item in replay_items)

    ticket.status = "approved"
    store.save_approval_ticket(ticket)
    result = approval_continuation_runtime.prepare_resume_after_approval(
        runtime_owner,
        approval_id=ticket.approval_id,
        decision_response={
            "approval_ticket": ticket,
            "action_request": updated_action,
            "action_result": {
                "ok": True,
                "action": "shell_command_start",
                "summary": "shell completed",
                "output": {"stdout": "providers\n", "exit_code": 0},
            },
        },
    )

    _, messages = AnthropicMessagesSession._normalize_messages(
        [
            *result["replay_input_items"],
            *result["tool_call_replay_items"],
            *result["tool_output_items"],
        ]
    )
    assert [message["role"] for message in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert messages[0]["content"][0]["text"] == "inspect project"
    assert messages[-2]["content"][0]["id"] == "tooluse_bash_1"
    assert messages[-1]["content"][0]["tool_use_id"] == "tooluse_bash_1"


def test_turn_engine_stores_pending_tool_continuation_for_apply_patch_approval() -> None:
    store = InMemoryGatewayStateStore()
    action = create_action_request(
        action_type="apply_patch",
        connector_key="local",
        plugin_name="builtin",
        trace_id="trace_patch_continuation",
        requested_by="test",
        payload={"patch_text": "*** Begin Patch\n*** Add File: hello.txt\n+hi\n*** End Patch"},
        metadata={},
        approval_required=True,
    )
    store.save_action_request(action)
    ticket = create_approval_ticket(action, requested_by="test", reason="needs patch approval")
    store.save_approval_ticket(ticket)
    runtime_owner = _RuntimeOwner(gateway_state_store=store)

    engine = TurnEngine(
        _PatchFakeSession(),
        tool_executor=_PatchToolExecutor(runtime_owner, ticket.approval_id),
    )

    intent = engine.run(
        user_text="create hello.txt",
        initial_input=[{"role": "user", "content": "create hello.txt"}],
    )

    assert "approval" in intent.assistant_text.lower()
    updated_action = store.get_action_request(action.action_id)
    updated_ticket = store.get_approval_ticket(ticket.approval_id)
    assert updated_action is not None
    assert updated_ticket is not None
    continuation = updated_action.metadata["pending_tool_continuation"]
    assert updated_ticket.metadata["pending_tool_continuation"] == continuation
    assert continuation["approval_id"] == ticket.approval_id
    assert continuation["action_id"] == action.action_id
    assert continuation["previous_response_id"] == "resp_patch_approval"
    assert continuation["provider_call_id"] == "call_patch_1"
    assert continuation["function_call_name"] == "apply_patch"
    assert continuation["function_call_arguments"]["patch"].startswith("*** Begin Patch")
    assert continuation["provider_tool_type"] == "function_call"
    assert continuation["continuation_input_items"] == [
        {"type": "function_call", "call_id": "call_patch_1", "name": "apply_patch"}
    ]
    assert continuation["replay_input_items"] == [{"role": "user", "content": "create hello.txt"}]
    assert continuation["status"] == "pending"


def test_prepare_resume_after_approval_builds_local_shell_output_item() -> None:
    store = InMemoryGatewayStateStore()
    runtime_owner = _RuntimeOwner(gateway_state_store=store)
    action = create_action_request(
        action_type="shell_command",
        connector_key="local",
        plugin_name="builtin",
        trace_id="trace_approval_continuation_build",
        requested_by="test",
        payload={"command": "echo hi"},
        metadata={
            "pending_tool_continuation": {
                "schema_version": 1,
                "approval_id": "approval_pending",
                "action_id": "action_pending",
                "previous_response_id": "resp_approval",
                "provider_call_id": "call_shell_1",
                "function_call_name": "exec_command",
                "function_call_arguments": {"cmd": "echo hi"},
                "provider_tool_type": "local_shell_call",
                "provider_raw_item": {"type": "local_shell_call"},
                "replay_input_items": [{"role": "user", "content": "run echo"}],
                "status": "pending",
            }
        },
        approval_required=True,
    )
    action.metadata["pending_tool_continuation"]["action_id"] = action.action_id
    store.save_action_request(action)
    ticket = create_approval_ticket(action, requested_by="test", reason="needs approval")
    ticket.status = "approved"
    ticket.metadata["pending_tool_continuation"] = dict(
        action.metadata["pending_tool_continuation"]
    )
    ticket.metadata["pending_tool_continuation"]["approval_id"] = ticket.approval_id
    store.save_approval_ticket(ticket)
    decision_response = {
        "approval_ticket": ticket,
        "action_request": action,
        "action_result": {
            "ok": True,
            "action": "shell_command_start",
            "summary": "shell completed",
            "output": {"stdout": "hi\n", "exit_code": 0},
        },
    }

    result = approval_continuation_runtime.prepare_resume_after_approval(
        runtime_owner,
        approval_id=ticket.approval_id,
        decision_response=decision_response,
    )

    assert result["continuation_status"] == "tool_result_built"
    assert result["previous_response_id"] == "resp_approval"
    assert result["tool_output_items"] == [
        {
            "type": "local_shell_call_output",
            "call_id": "call_shell_1",
            "output": [
                {"stdout": "hi\n", "stderr": "", "outcome": {"type": "exit", "exit_code": 0}}
            ],
            "status": "completed",
        }
    ]


def test_prepare_resume_after_reject_builds_failed_model_visible_output() -> None:
    store = InMemoryGatewayStateStore()
    runtime_owner = _RuntimeOwner(gateway_state_store=store)
    action = create_action_request(
        action_type="shell_command",
        connector_key="local",
        plugin_name="builtin",
        trace_id="trace_approval_continuation_reject",
        requested_by="test",
        payload={"command": "echo hi"},
        metadata={
            "pending_tool_continuation": {
                "schema_version": 1,
                "approval_id": "approval_pending",
                "action_id": "action_pending",
                "previous_response_id": "resp_approval",
                "provider_call_id": "call_shell_1",
                "function_call_name": "exec_command",
                "function_call_arguments": {"cmd": "echo hi"},
                "provider_tool_type": "function_call",
                "provider_raw_item": {"type": "function_call"},
                "replay_input_items": [{"role": "user", "content": "run echo"}],
                "status": "pending",
            }
        },
        approval_required=True,
    )
    action.metadata["pending_tool_continuation"]["action_id"] = action.action_id
    store.save_action_request(action)
    ticket = create_approval_ticket(action, requested_by="test", reason="needs approval")
    ticket.status = "rejected"
    ticket.metadata["pending_tool_continuation"] = dict(
        action.metadata["pending_tool_continuation"]
    )
    ticket.metadata["pending_tool_continuation"]["approval_id"] = ticket.approval_id
    store.save_approval_ticket(ticket)
    decision_response = {
        "approval_ticket": ticket,
        "action_request": action,
        "action_result": None,
    }

    result = approval_continuation_runtime.prepare_resume_after_approval(
        runtime_owner,
        approval_id=ticket.approval_id,
        decision_response=decision_response,
    )

    assert result["continuation_status"] == "tool_result_built"
    output_item = result["tool_output_items"][0]
    assert output_item["type"] == "function_call_output"
    assert output_item["call_id"] == "call_shell_1"
    assert output_item["success"] is False
    assert "User rejected approval" in str(output_item["output"])


def test_prepare_resume_after_apply_patch_approval_preserves_function_call_output() -> None:
    store = InMemoryGatewayStateStore()
    runtime_owner = _RuntimeOwner(gateway_state_store=store)
    action = create_action_request(
        action_type="apply_patch",
        connector_key="local",
        plugin_name="builtin",
        trace_id="trace_patch_continuation_build",
        requested_by="test",
        payload={"patch_text": "*** Begin Patch\n*** Add File: hello.txt\n+hi\n*** End Patch"},
        metadata={
            "pending_tool_continuation": {
                "schema_version": 1,
                "approval_id": "approval_pending",
                "action_id": "action_pending",
                "previous_response_id": "resp_patch_approval",
                "provider_call_id": "call_patch_1",
                "function_call_name": "apply_patch",
                "function_call_arguments": {
                    "patch": "*** Begin Patch\n*** Add File: hello.txt\n+hi\n*** End Patch"
                },
                "provider_tool_type": "function_call",
                "provider_raw_item": {"type": "function_call", "name": "apply_patch"},
                "continuation_input_items": [
                    {"type": "function_call", "call_id": "call_patch_1", "name": "apply_patch"}
                ],
                "replay_input_items": [{"role": "user", "content": "create hello.txt"}],
                "status": "pending",
            }
        },
        approval_required=True,
    )
    action.metadata["pending_tool_continuation"]["action_id"] = action.action_id
    store.save_action_request(action)
    ticket = create_approval_ticket(action, requested_by="test", reason="needs patch approval")
    ticket.status = "approved"
    ticket.metadata["pending_tool_continuation"] = dict(
        action.metadata["pending_tool_continuation"]
    )
    ticket.metadata["pending_tool_continuation"]["approval_id"] = ticket.approval_id
    store.save_approval_ticket(ticket)
    function_call_output = (
        "Exit code: 0\n"
        "Wall time: 0 seconds\n"
        "Output:\n"
        "Success. Updated the following files:\n"
        "A hello.txt"
    )
    decision_response = {
        "approval_ticket": ticket,
        "action_request": action,
        "action_result": {
            "ok": True,
            "action": "apply_patch",
            "summary": "apply_patch files=1",
            "output": {
                "function_call_output": function_call_output,
                "function_call_output_model_visible": True,
                "file_count": 1,
            },
        },
    }

    result = approval_continuation_runtime.prepare_resume_after_approval(
        runtime_owner,
        approval_id=ticket.approval_id,
        decision_response=decision_response,
    )

    assert result["continuation_status"] == "tool_result_built"
    output_item = result["tool_output_items"][0]
    assert output_item["type"] == "function_call_output"
    assert output_item["call_id"] == "call_patch_1"
    assert output_item["success"] is True
    assert output_item["output"] == function_call_output


def test_prepare_resume_after_apply_patch_reject_builds_failed_model_visible_output() -> None:
    store = InMemoryGatewayStateStore()
    runtime_owner = _RuntimeOwner(gateway_state_store=store)
    action = create_action_request(
        action_type="apply_patch",
        connector_key="local",
        plugin_name="builtin",
        trace_id="trace_patch_continuation_reject",
        requested_by="test",
        payload={"patch_text": "*** Begin Patch\n*** Add File: hello.txt\n+hi\n*** End Patch"},
        metadata={
            "pending_tool_continuation": {
                "schema_version": 1,
                "approval_id": "approval_pending",
                "action_id": "action_pending",
                "previous_response_id": "resp_patch_approval",
                "provider_call_id": "call_patch_1",
                "function_call_name": "apply_patch",
                "function_call_arguments": {
                    "patch": "*** Begin Patch\n*** Add File: hello.txt\n+hi\n*** End Patch"
                },
                "provider_tool_type": "function_call",
                "provider_raw_item": {"type": "function_call", "name": "apply_patch"},
                "continuation_input_items": [
                    {"type": "function_call", "call_id": "call_patch_1", "name": "apply_patch"}
                ],
                "replay_input_items": [{"role": "user", "content": "create hello.txt"}],
                "status": "pending",
            }
        },
        approval_required=True,
    )
    action.metadata["pending_tool_continuation"]["action_id"] = action.action_id
    store.save_action_request(action)
    ticket = create_approval_ticket(action, requested_by="test", reason="needs patch approval")
    ticket.status = "rejected"
    ticket.metadata["pending_tool_continuation"] = dict(
        action.metadata["pending_tool_continuation"]
    )
    ticket.metadata["pending_tool_continuation"]["approval_id"] = ticket.approval_id
    store.save_approval_ticket(ticket)

    result = approval_continuation_runtime.prepare_resume_after_approval(
        runtime_owner,
        approval_id=ticket.approval_id,
        decision_response={
            "approval_ticket": ticket,
            "action_request": action,
            "action_result": None,
        },
    )

    assert result["continuation_status"] == "tool_result_built"
    output_item = result["tool_output_items"][0]
    assert output_item["type"] == "function_call_output"
    assert output_item["call_id"] == "call_patch_1"
    assert output_item["success"] is False
    assert "User rejected approval" in str(output_item["output"])


def test_decide_patch_approval_prepares_continuation_and_projects_to_tool_events() -> None:
    store = InMemoryGatewayStateStore()
    patch_text = "*** Begin Patch\n*** Add File: hello.txt\n+hi\n*** End Patch"
    action = create_action_request(
        action_type="apply_patch",
        connector_key="local",
        plugin_name="builtin",
        trace_id="trace_patch_decision_continuation",
        requested_by="test",
        payload={"patch_text": patch_text},
        metadata={
            "pending_tool_continuation": {
                "schema_version": 1,
                "approval_id": "approval_pending",
                "action_id": "action_pending",
                "previous_response_id": "resp_patch_approval",
                "provider_call_id": "call_patch_1",
                "function_call_name": "apply_patch",
                "function_call_arguments": {"patch": patch_text},
                "provider_tool_type": "function_call",
                "provider_raw_item": {"type": "function_call", "name": "apply_patch"},
                "continuation_input_items": [
                    {"type": "function_call", "call_id": "call_patch_1", "name": "apply_patch"}
                ],
                "replay_input_items": [{"role": "user", "content": "create hello.txt"}],
                "status": "pending",
            }
        },
        approval_required=True,
    )
    action.metadata["pending_tool_continuation"]["action_id"] = action.action_id
    store.save_action_request(action)
    ticket = create_approval_ticket(action, requested_by="test", reason="needs patch approval")
    action.metadata["pending_tool_continuation"]["approval_id"] = ticket.approval_id
    store.save_action_request(action)
    ticket.metadata["pending_tool_continuation"] = dict(
        action.metadata["pending_tool_continuation"]
    )
    store.save_approval_ticket(ticket)
    function_call_output = (
        "Exit code: 0\n"
        "Wall time: 0 seconds\n"
        "Output:\n"
        "Success. Updated the following files:\n"
        "A hello.txt"
    )
    tools = _PatchDecisionTools(function_call_output)
    runtime = _PatchDecisionRuntime(store, tools)

    result = approval_resolution_runtime.decide_patch_approval(
        runtime,
        ticket.approval_id,
        approved=True,
        decided_by="test",
    )

    assert tools.calls == [patch_text]
    continuation = result["continuation"]
    assert continuation["continuation_status"] == "tool_result_built"
    assert continuation["previous_response_id"] == "resp_patch_approval"
    assert continuation["tool_output_items"][0] == {
        "type": "function_call_output",
        "call_id": "call_patch_1",
        "output": function_call_output,
        "success": True,
    }
    tool_events = list(result["tool_events"])
    assert [event.name for event in tool_events] == ["approval_decision", "apply_patch"]
    assert tool_events[0].payload["continuation"]["continuation_status"] == "tool_result_built"
    assert (
        tool_events[1].payload["continuation"]["tool_output_items"][0]["call_id"] == "call_patch_1"
    )


class _CommandRuntime(_RuntimeOwner):
    def __init__(self, gateway_state_store: InMemoryGatewayStateStore) -> None:
        super().__init__(gateway_state_store=gateway_state_store)
        self.history: list[dict[str, str]] = []
        self.thread_id = "thread_1"
        self._structured_tool_executor = object()
        self.agent = self
        self.plan_calls: list[dict[str, Any]] = []
        self.decide_calls = 0

    @staticmethod
    def _parse_args(arg_text: str):
        from cli.agent_cli.runtime_core import parse_args

        return parse_args(arg_text)

    @staticmethod
    def _is_interrupt_requested() -> bool:
        return False

    @staticmethod
    def _interrupt_tuple() -> tuple[str, list[ToolEvent]]:
        return "interrupted", []

    def decide_approval(
        self, approval_id: str, *, decision: Any, decided_by: str, decision_note: str = ""
    ):
        self.decide_calls += 1
        ticket = self.gateway_state_store.get_approval_ticket(approval_id)
        assert ticket is not None
        if str(ticket.status or "").strip().lower() != "pending":
            raise ValueError(f"approval already decided: {ticket.approval_id}")
        ticket.status = "approved"
        ticket.decision_by = decided_by
        ticket.decision_note = decision_note
        ticket.decision_type = str(decision)
        self.save_gateway_approval_ticket(ticket)
        action = self.gateway_state_store.get_action_request(ticket.action_id)
        assert action is not None
        event = ToolEvent(
            name="approval_decision",
            ok=True,
            summary=f"approved {approval_id}",
            payload={"approval_id": approval_id, "status": "approved"},
        )
        return {
            "approval_ticket": ticket,
            "action_request": action,
            "action_result": {
                "ok": True,
                "action": "shell_command_start",
                "summary": "shell completed",
                "output": {"stdout": "hi\n", "exit_code": 0},
            },
            "tool_events": [event],
            "item_events": [],
            "turn_events": [],
            "continuation": approval_continuation_runtime.prepare_resume_after_approval(
                self,
                approval_id=approval_id,
                decision_response={
                    "approval_ticket": ticket,
                    "action_request": action,
                    "action_result": {
                        "ok": True,
                        "action": "shell_command_start",
                        "summary": "shell completed",
                        "output": {"stdout": "hi\n", "exit_code": 0},
                    },
                },
            ),
        }

    def plan(self, user_text: str, history: list[dict[str, str]], **kwargs: Any) -> AgentIntent:
        del history
        self.plan_calls.append({"user_text": user_text, **kwargs})
        return AgentIntent(
            assistant_text="continued after approval",
            turn_events=[{"type": "turn.completed"}],
        )

    def approvals_event(self, *, limit: int = 20, status: str | None = None) -> ToolEvent:
        from cli.agent_cli import runtime_runtime

        tickets = self.gateway_state_store.list_approval_tickets(limit=limit, status=status)
        rows = runtime_runtime.approval_list_rows(
            tickets=tickets,
            get_action_request_fn=self.gateway_state_store.get_action_request,
        )
        return runtime_runtime.approval_list_event(
            rows=rows,
            status=status,
            tool_event_factory=ToolEvent,
        )

    def list_approval_diagnostics(self, *, limit: int = 20, status: str | None = None):
        return gateway_diagnostics_runtime.list_approval_diagnostics(
            self,
            limit=limit,
            status=status,
        )


class _RetryingCommandRuntime(_CommandRuntime):
    def plan(self, user_text: str, history: list[dict[str, str]], **kwargs: Any) -> AgentIntent:
        del history
        self.plan_calls.append({"user_text": user_text, **kwargs})
        if len(self.plan_calls) == 1:
            return AgentIntent(
                assistant_text="当前 provider 调用失败: Unsupported parameter: previous_response_id",
                status_hint="degraded",
                protocol_diagnostics={
                    "provider_runtime_error": "BadRequestError: Unsupported parameter: previous_response_id",
                    "protocol_path": {
                        "kind": "provider_degraded_fallback",
                        "source": "host",
                    },
                },
            )
        return AgentIntent(
            assistant_text="continued after replay retry",
            turn_events=[{"type": "turn.completed"}],
        )


class _FilteredPlannerRuntime(_CommandRuntime):
    @staticmethod
    def _filter_callable_kwargs(fn: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
        del fn
        return {
            key: value
            for key, value in dict(kwargs).items()
            if key
            not in {"initial_previous_response_id", "prompt_cache_key", "turn_event_callback"}
        }

    def plan(
        self,
        user_text: str,
        history: list[dict[str, str]],
        *,
        tool_executor: Any = None,
        input_items: list[dict[str, Any]] | None = None,
    ) -> AgentIntent:
        del history, tool_executor
        self.plan_calls.append({"user_text": user_text, "input_items": list(input_items or [])})
        return AgentIntent(
            assistant_text="continued with filtered planner kwargs",
            turn_events=[{"type": "turn.completed"}],
        )


class _GenericChatRuntime(_CommandRuntime):
    def provider_status(self) -> dict[str, str]:
        return {
            "provider_name": "deepseek",
            "provider_planner": "deepseek_chat",
            "wire_api": "openai_chat",
        }


def _store_shell_continuation_ticket(
    trace_id: str,
    *,
    previous_response_id: str = "resp_approval",
) -> tuple[InMemoryGatewayStateStore, Any]:
    store = InMemoryGatewayStateStore()
    action = create_action_request(
        action_type="shell_command",
        connector_key="local",
        plugin_name="builtin",
        trace_id=trace_id,
        requested_by="test",
        payload={"command": "echo hi"},
        metadata={
            "pending_tool_continuation": {
                "schema_version": 1,
                "approval_id": "approval_pending",
                "action_id": "action_pending",
                "previous_response_id": previous_response_id,
                "provider_call_id": "call_shell_1",
                "function_call_name": "exec_command",
                "function_call_arguments": {"cmd": "echo hi"},
                "provider_tool_type": "local_shell_call",
                "provider_raw_item": {"type": "local_shell_call"},
                "continuation_input_items": [
                    {"type": "local_shell_call", "call_id": "call_shell_1"}
                ],
                "replay_input_items": [{"role": "user", "content": "run echo"}],
                "status": "pending",
            }
        },
        approval_required=True,
    )
    action.metadata["pending_tool_continuation"]["action_id"] = action.action_id
    store.save_action_request(action)
    ticket = create_approval_ticket(action, requested_by="test", reason="needs approval")
    action.metadata["pending_tool_continuation"]["approval_id"] = ticket.approval_id
    store.save_action_request(action)
    ticket.metadata["pending_tool_continuation"] = dict(
        action.metadata["pending_tool_continuation"]
    )
    store.save_approval_ticket(ticket)
    return store, ticket


def test_approve_command_resumes_with_previous_response_and_tool_output() -> None:
    store, ticket = _store_shell_continuation_ticket("trace_approval_command_resume")
    runtime = _CommandRuntime(store)

    result = run_command_text_result(runtime, f"/approve {ticket.approval_id}")

    assert result.assistant_text == "continued after approval"
    assert len(runtime.plan_calls) == 1
    call = runtime.plan_calls[0]
    assert call["initial_previous_response_id"] == "resp_approval"
    assert call["input_items"][-1]["type"] == "local_shell_call_output"
    assert call["input_items"][-1]["call_id"] == "call_shell_1"
    assert result.tool_events[0].payload["continuation"]["continuation_status"] == "completed"


def test_resume_only_uses_persisted_continuation_without_reexecuting_approval() -> None:
    store, ticket = _store_shell_continuation_ticket("trace_resume_only")
    runtime = _CommandRuntime(store)

    first = run_command_text_result(runtime, f"/approve {ticket.approval_id} --no-resume")
    second = run_command_text_result(runtime, f"/approve {ticket.approval_id} --resume-only")

    assert (
        first.tool_events[0].payload["continuation"]["continuation_status"] == "tool_result_built"
    )
    assert first.assistant_text == ""
    assert first.command_display_text == ""
    assert runtime.decide_calls == 1
    assert len(runtime.plan_calls) == 1
    assert second.assistant_text == "continued after approval"
    assert second.tool_events[0].payload["status"] == "resume_only"
    assert second.tool_events[0].payload["continuation"]["continuation_status"] == "completed"


def test_resume_only_retries_after_failed_continuation_without_reexecuting_approval() -> None:
    store, ticket = _store_shell_continuation_ticket("trace_resume_only_failed_retry")
    runtime = _RetryingCommandRuntime(store)

    first = run_command_text_result(runtime, f"/approve {ticket.approval_id} --no-resume")
    stored = store.get_approval_ticket(ticket.approval_id).metadata["approval_continuation_result"]
    stored["continuation_attempted"] = True
    stored["continuation_status"] = "failed"
    stored["error"] = "temporary provider failure"
    store.get_approval_ticket(ticket.approval_id).metadata["approval_continuation_result"] = stored
    second = run_command_text_result(runtime, f"/approve {ticket.approval_id} --resume-only")

    assert (
        first.tool_events[0].payload["continuation"]["continuation_status"] == "tool_result_built"
    )
    assert runtime.decide_calls == 1
    assert len(runtime.plan_calls) == 2
    assert second.assistant_text == "continued after replay retry"
    assert second.tool_events[0].payload["continuation"]["resume_only_from_status"] == "failed"
    assert second.tool_events[0].payload["continuation"]["continuation_status"] == "completed"


def test_already_decided_approval_does_not_reexecute_without_resume_only() -> None:
    store = InMemoryGatewayStateStore()
    action = create_action_request(
        action_type="shell_command",
        connector_key="local",
        plugin_name="builtin",
        trace_id="trace_already_decided",
        requested_by="test",
        payload={"command": "echo hi"},
        metadata={},
        approval_required=True,
    )
    store.save_action_request(action)
    ticket = create_approval_ticket(action, requested_by="test", reason="needs approval")
    ticket.status = "approved"
    store.save_approval_ticket(ticket)
    runtime = _CommandRuntime(store)

    result = run_command_text_result(runtime, f"/approve {ticket.approval_id}")

    assert runtime.decide_calls == 1
    assert not runtime.plan_calls
    assert result.tool_events[0].ok is False
    assert "approval already decided" in result.tool_events[0].payload["error"]


def test_approvals_event_surfaces_stale_pending_continuation() -> None:
    store, ticket = _store_shell_continuation_ticket("trace_approvals_stale_pending")
    ticket.status = "approved"
    store.save_approval_ticket(ticket)
    runtime = _CommandRuntime(store)

    event = runtime.approvals_event(limit=5, status=None)
    row = event.payload["approvals"][0]

    assert row["continuation_status"] == "stale_pending"
    assert row["continuation_stale"] is True
    assert row["continuation"]["provider_call_id"] == "call_shell_1"


def test_approvals_event_surfaces_persisted_continuation_result() -> None:
    store, ticket = _store_shell_continuation_ticket("trace_approvals_completed_result")
    runtime = _CommandRuntime(store)
    result = run_command_text_result(runtime, f"/approve {ticket.approval_id}")

    event = runtime.approvals_event(limit=5, status=None)
    row = event.payload["approvals"][0]

    assert result.tool_events[0].payload["continuation"]["continuation_status"] == "completed"
    assert row["continuation_status"] == "completed"
    assert row["continuation_stale"] is False


def test_approval_diagnostics_surface_continuation_status() -> None:
    store, ticket = _store_shell_continuation_ticket("trace_approval_diagnostics_completed")
    runtime = _CommandRuntime(store)
    run_command_text_result(runtime, f"/approve {ticket.approval_id}")

    diagnostics = runtime.list_approval_diagnostics(limit=5)

    assert diagnostics[0]["continuation"]["continuation_status"] == "completed"
    assert diagnostics[0]["continuation"]["continuation_stale"] is False


def test_resume_after_approval_retries_replay_when_previous_response_id_is_unsupported() -> None:
    runtime = _RetryingCommandRuntime(InMemoryGatewayStateStore())
    continuation = {
        "continuation_status": "tool_result_built",
        "previous_response_id": "resp_approval",
        "continuation_input_items": [{"type": "local_shell_call", "call_id": "call_shell_1"}],
        "replay_input_items": [{"role": "user", "content": "run echo"}],
        "tool_output_items": [
            {
                "type": "local_shell_call_output",
                "call_id": "call_shell_1",
                "output": [
                    {"stdout": "hi\n", "stderr": "", "outcome": {"type": "exit", "exit_code": 0}}
                ],
                "status": "completed",
            }
        ],
    }

    intent = approval_continuation_runtime.resume_after_approval(
        runtime,
        continuation_result=continuation,
    )

    assert intent is not None
    assert intent.assistant_text == "continued after replay retry"
    assert continuation["continuation_status"] == "completed"
    assert continuation["retry_without_previous_response_id"] is True
    assert len(runtime.plan_calls) == 2
    assert runtime.plan_calls[0]["initial_previous_response_id"] == "resp_approval"
    assert runtime.plan_calls[1]["initial_previous_response_id"] is None
    assert runtime.plan_calls[1]["input_items"][-1]["call_id"] == "call_shell_1"


def test_resume_after_approval_filters_unsupported_planner_kwargs_for_anthropic_like_planners() -> (
    None
):
    runtime = _FilteredPlannerRuntime(InMemoryGatewayStateStore())
    continuation = {
        "continuation_status": "tool_result_built",
        "previous_response_id": "anthropic-msg-1",
        "continuation_input_items": [
            {"type": "function_call", "call_id": "toolu_1", "name": "file_read"}
        ],
        "replay_input_items": [{"role": "user", "content": "read file"}],
        "tool_output_items": [
            {
                "type": "function_call_output",
                "call_id": "toolu_1",
                "output": "file contents",
                "success": True,
            }
        ],
    }

    intent = approval_continuation_runtime.resume_after_approval(
        runtime,
        continuation_result=continuation,
    )

    assert intent is not None
    assert intent.assistant_text == "continued with filtered planner kwargs"
    assert continuation["continuation_status"] == "completed"
    assert runtime.plan_calls[0]["input_items"][-1]["call_id"] == "toolu_1"


def test_resume_after_approval_degrades_generic_chat_without_calling_planner() -> None:
    runtime = _GenericChatRuntime(InMemoryGatewayStateStore())
    continuation = {
        "continuation_status": "tool_result_built",
        "previous_response_id": "chatcmpl-1",
        "provider_session_kind": "deepseek_chat",
        "continuation_input_items": [],
        "tool_call_replay_items": [
            {
                "type": "function_call",
                "call_id": "call_shell_1",
                "name": "exec_command",
                "arguments": '{"cmd": "echo hi"}',
            }
        ],
        "replay_input_items": [{"role": "user", "content": "run echo"}],
        "tool_output_items": [
            {
                "type": "function_call_output",
                "call_id": "call_shell_1",
                "output": "hi\n",
                "success": True,
            }
        ],
    }

    intent = approval_continuation_runtime.resume_after_approval(
        runtime,
        continuation_result=continuation,
    )

    assert intent is not None
    assert intent.status_hint == "degraded"
    assert "generic chat-completions" in intent.assistant_text
    assert "hi" in intent.assistant_text
    assert continuation["continuation_attempted"] is True
    assert continuation["continuation_status"] == "degraded"
    assert continuation["degraded_reason"] == "generic_chat_continuation_not_native"
    assert runtime.plan_calls == []


def test_resume_after_approval_strips_orphan_replay_tool_outputs() -> None:
    runtime = _CommandRuntime(InMemoryGatewayStateStore())
    continuation = {
        "continuation_status": "tool_result_built",
        "previous_response_id": "anthropic-msg-1",
        "continuation_input_items": [],
        "replay_input_items": [
            {"type": "message", "role": "user", "content": "inspect project"},
            {
                "type": "function_call_output",
                "call_id": "toolu_orphan",
                "output": "stale output without matching tool use",
                "success": True,
            },
        ],
        "tool_call_replay_items": [
            {
                "type": "function_call",
                "call_id": "toolu_current",
                "name": "Bash",
                "arguments": '{"command": "ls"}',
            }
        ],
        "tool_output_items": [
            {
                "type": "function_call_output",
                "call_id": "toolu_current",
                "output": "README.md",
                "success": True,
            }
        ],
    }

    intent = approval_continuation_runtime.resume_after_approval(
        runtime,
        continuation_result=continuation,
    )

    assert intent is not None
    assert continuation["continuation_status"] == "completed"
    assert continuation["stripped_orphan_replay_tool_outputs"] == ["toolu_orphan"]
    input_items = runtime.plan_calls[0]["input_items"]
    assert not any(item.get("call_id") == "toolu_orphan" for item in input_items)
    assert [item.get("call_id") for item in input_items if item.get("call_id")] == [
        "toolu_current",
        "toolu_current",
    ]

    _, messages = AnthropicMessagesSession._normalize_messages(input_items)
    assert [message["role"] for message in messages] == ["user", "assistant", "user"]
    assert messages[1]["content"][0]["id"] == "toolu_current"
    assert messages[2]["content"][0]["tool_use_id"] == "toolu_current"


def test_prepare_resume_rebuilds_tool_call_replay_items_from_approval_turn_events() -> None:
    store = InMemoryGatewayStateStore()
    runtime_owner = _RuntimeOwner(gateway_state_store=store)
    patch_text = "*** Begin Patch\n*** Add File: hello.txt\n+hi\n*** End Patch"
    action = create_action_request(
        action_type="apply_patch",
        connector_key="local",
        plugin_name="builtin",
        trace_id="trace_patch_replay_rebuild",
        requested_by="test",
        payload={"patch_text": patch_text},
        metadata={
            "pending_tool_continuation": {
                "schema_version": 1,
                "approval_id": "approval_pending",
                "action_id": "action_pending",
                "previous_response_id": "anthropic-msg-1",
                "provider_call_id": "toolu_patch_1",
                "function_call_name": "apply_patch",
                "function_call_arguments": {"patch": patch_text},
                "provider_tool_type": "custom_tool_call",
                "provider_raw_item": {
                    "type": "tool_use",
                    "id": "toolu_patch_1",
                    "name": "apply_patch",
                },
                "continuation_input_items": [],
                "replay_input_items": [{"role": "user", "content": "create hello.txt"}],
                "executed_item_events_before_approval": [
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "toolu_patch_1",
                            "type": "custom_tool_call",
                            "call_id": "toolu_patch_1",
                            "name": "apply_patch",
                            "input": patch_text,
                        },
                    }
                ],
                "status": "pending",
            }
        },
        approval_required=True,
    )
    action.metadata["pending_tool_continuation"]["action_id"] = action.action_id
    store.save_action_request(action)
    ticket = create_approval_ticket(action, requested_by="test", reason="needs patch approval")
    ticket.status = "approved"
    action.metadata["pending_tool_continuation"]["approval_id"] = ticket.approval_id
    store.save_action_request(action)
    ticket.metadata["pending_tool_continuation"] = dict(
        action.metadata["pending_tool_continuation"]
    )
    store.save_approval_ticket(ticket)

    result = approval_continuation_runtime.prepare_resume_after_approval(
        runtime_owner,
        approval_id=ticket.approval_id,
        decision_response={
            "approval_ticket": ticket,
            "action_request": action,
            "action_result": {
                "ok": True,
                "action": "apply_patch",
                "summary": "apply_patch files=1",
                "output": {"function_call_output": "patch applied"},
            },
        },
    )

    assert result["continuation_status"] == "tool_result_built"
    assert len(result["tool_call_replay_items"]) == 1
    replay_item = result["tool_call_replay_items"][0]
    assert replay_item["type"] == "custom_tool_call"
    assert replay_item["call_id"] == "toolu_patch_1"
    assert replay_item["name"] == "apply_patch"
    assert replay_item["input"] == patch_text

    _, messages = AnthropicMessagesSession._normalize_messages(
        [
            *result["replay_input_items"],
            *result["tool_call_replay_items"],
            *result["tool_output_items"],
        ]
    )
    assert messages[-2] == {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_patch_1",
                "name": "apply_patch",
                "input": {"patch": patch_text},
            }
        ],
    }
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"][0]["type"] == "tool_result"
    assert messages[-1]["content"][0]["tool_use_id"] == "toolu_patch_1"
    assert messages[-1]["content"][0]["content"][0]["text"] == "patch applied"


def test_prepare_resume_rebuilds_anthropic_tool_use_replay_item_from_provider_context() -> None:
    store = InMemoryGatewayStateStore()
    runtime_owner = _RuntimeOwner(gateway_state_store=store)
    action = create_action_request(
        action_type="apply_patch",
        connector_key="local",
        plugin_name="builtin",
        trace_id="trace_anthropic_write_replay",
        requested_by="test",
        payload={"patch_text": "write notes.txt"},
        metadata={
            "pending_tool_continuation": {
                "schema_version": 1,
                "approval_id": "approval_pending",
                "action_id": "action_pending",
                "previous_response_id": "anthropic-msg-1",
                "provider_call_id": "tooluse_write_1",
                "function_call_name": "Write",
                "function_call_arguments": {
                    "file_path": "notes.txt",
                    "content": "hello\n",
                },
                "provider_tool_type": "tool_use",
                "provider_raw_item": {
                    "type": "tool_use",
                    "id": "tooluse_write_1",
                    "name": "Write",
                    "input": {
                        "file_path": "notes.txt",
                        "content": "hello\n",
                    },
                },
                "continuation_input_items": [],
                "replay_input_items": [{"role": "user", "content": "write notes.txt"}],
                "executed_item_events_before_approval": [
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_1",
                            "type": "mcp_tool_call",
                            "tool": "patch_approval_requested",
                            "status": "completed",
                        },
                    }
                ],
                "status": "pending",
            }
        },
        approval_required=True,
    )
    action.metadata["pending_tool_continuation"]["action_id"] = action.action_id
    store.save_action_request(action)
    ticket = create_approval_ticket(action, requested_by="test", reason="needs write approval")
    ticket.status = "approved"
    action.metadata["pending_tool_continuation"]["approval_id"] = ticket.approval_id
    store.save_action_request(action)
    ticket.metadata["pending_tool_continuation"] = dict(
        action.metadata["pending_tool_continuation"]
    )
    store.save_approval_ticket(ticket)

    result = approval_continuation_runtime.prepare_resume_after_approval(
        runtime_owner,
        approval_id=ticket.approval_id,
        decision_response={
            "approval_ticket": ticket,
            "action_request": action,
            "action_result": {
                "ok": True,
                "action": "apply_patch",
                "summary": "apply_patch files=1",
                "output": {"function_call_output": "write applied"},
            },
        },
    )

    assert result["continuation_status"] == "tool_result_built"
    assert result["tool_call_replay_items"] == [
        {
            "type": "function_call",
            "call_id": "tooluse_write_1",
            "name": "Write",
            "arguments": '{"file_path": "notes.txt", "content": "hello\\n"}',
        }
    ]

    _, messages = AnthropicMessagesSession._normalize_messages(
        [
            *result["replay_input_items"],
            *result["tool_call_replay_items"],
            *result["tool_output_items"],
        ]
    )
    assert messages[-2] == {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "tooluse_write_1",
                "name": "Write",
                "input": {
                    "file_path": "notes.txt",
                    "content": "hello\n",
                },
            }
        ],
    }
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"][0]["type"] == "tool_result"
    assert messages[-1]["content"][0]["tool_use_id"] == "tooluse_write_1"
    assert messages[-1]["content"][0]["content"][0]["text"] == "write applied"
