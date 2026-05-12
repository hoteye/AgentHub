from __future__ import annotations

from cli.agent_cli.host_platform import detect_host_platform
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.openai_planner import OpenAIPlanner
from cli.replay_integration.replay_client import ReplayOpenAIClient
from cli.replay_integration.schema import (
    ReplayCassette,
    ReplayManifest,
    ReplayRound,
    ReplaySessionMetadata,
    ReplayToolCall,
)
from cli.replay_integration.tool_replay import ReplayToolExecutor


def test_openai_planner_can_finish_tool_loop_against_replay_client_and_tool_executor() -> None:
    host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
    planner = OpenAIPlanner(
        ProviderConfig(model="gpt-5.4", api_key="sk-test"),
        host_platform=host_platform,
    )

    tool_specs = planner._tool_specs()
    instructions = planner.native_tool_system_prompt
    cassette = ReplayCassette(
        manifest=ReplayManifest(
            name="synthetic-tool-loop",
            session=ReplaySessionMetadata(
                provider="replay",
                model="gpt-5.4",
                transport_kind="responses_http",
            ),
            environment_snapshot={"cwd": "/tmp/demo", "shell": "bash"},
            workspace_snapshot={"cwd": "/tmp/demo", "instructions_digest": "digest-1"},
        ),
        rounds=[
            ReplayRound(
                index=1,
                request={
                    "model": "gpt-5.4",
                    "instructions": instructions,
                    "input": [
                        {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "列出当前目录"}],
                        }
                    ],
                    "store": False,
                    "stream": False,
                    "tools": tool_specs,
                    "tool_choice": "auto",
                    "parallel_tool_calls": False,
                },
                response={
                    "id": "resp_1",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call_1",
                            "name": "exec_command",
                            "arguments": '{"cmd":"pwd"}',
                        }
                    ],
                    "output_text": "",
                },
            ),
            ReplayRound(
                index=2,
                request={
                    "model": "gpt-5.4",
                    "instructions": instructions,
                    "input": [
                        {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "列出当前目录"}],
                        },
                        {
                            "type": "function_call",
                            "call_id": "call_1",
                            "name": "exec_command",
                            "arguments": '{"cmd":"pwd"}',
                        },
                        {
                            "type": "function_call_output",
                            "call_id": "call_1",
                            "output": "/tmp/demo",
                        },
                    ],
                    "store": False,
                    "stream": False,
                    "tools": tool_specs,
                    "tool_choice": "auto",
                    "parallel_tool_calls": False,
                },
                response={
                    "id": "resp_2",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "phase": "final_answer",
                            "content": [{"type": "output_text", "text": "目录是 /tmp/demo"}],
                        }
                    ],
                    "output_text": "",
                },
            ),
        ],
        tool_calls=[
            ReplayToolCall(
                index=1,
                round_index=1,
                tool_name="exec_command",
                call_id="call_1",
                command_text="/exec_command pwd",
                arguments={"cmd": "pwd"},
                output_items=[
                    {
                        "type": "function_call_output",
                        "call_id": "call_1",
                        "output": "/tmp/demo",
                        "success": True,
                    }
                ],
            )
        ],
    )

    replay_client = ReplayOpenAIClient(cassette)
    planner.client = replay_client
    tool_executor = ReplayToolExecutor(cassette)

    intent = planner.plan("列出当前目录", [], tool_executor=tool_executor)

    assert intent.assistant_text == "目录是 /tmp/demo"
    assert len(replay_client.responses.requests) == 2
    assert replay_client.responses.requests[1]["input"][2] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": "/tmp/demo",
    }


def test_replay_tool_executor_accepts_exec_command_equivalent_to_shell_wrapped_command() -> None:
    cassette = ReplayCassette(
        manifest=ReplayManifest(
            name="shell-equivalence",
            session=ReplaySessionMetadata(provider="replay", model="gpt-5.4"),
        ),
        tool_calls=[
            ReplayToolCall(
                index=1,
                round_index=1,
                tool_name="exec_command",
                call_id="call_pwd_1",
                command_text="/bin/bash -lc pwd",
                output_items=[
                    {
                        "type": "function_call_output",
                        "call_id": "call_pwd_1",
                        "output": "/tmp/demo\n",
                        "success": True,
                    }
                ],
            )
        ],
    )

    executor = ReplayToolExecutor(cassette)

    result = executor.run_structured(
        "/exec_command pwd --workdir /tmp/demo --yield-time-ms 1000 --max-output-tokens 200"
    )

    assert result.assistant_text == "/tmp/demo\n"
    assert result.tool_events[0].name == "exec_command"
    assert result.tool_events[0].ok is True


def test_openai_planner_can_finish_delegation_recovery_loop_against_replay_client_and_tool_executor() -> (
    None
):
    host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
    planner = OpenAIPlanner(
        ProviderConfig(model="gpt-5.4", api_key="sk-test"),
        host_platform=host_platform,
    )

    tool_specs = planner._tool_specs()
    instructions = planner.native_tool_system_prompt
    user_prompt = "先检查 agent_1 的 workflow；如果有失败步骤且可恢复，就直接在原子会话里重试。"
    workflow_output = "workflow snapshot: failed step=step_2; recovery_actions=[retry_step]"
    recover_output = "recovery accepted: retried step_2"
    cassette = ReplayCassette(
        manifest=ReplayManifest(
            name="synthetic-delegation-recovery-loop",
            session=ReplaySessionMetadata(
                provider="replay",
                model="gpt-5.4",
                transport_kind="responses_http",
            ),
            environment_snapshot={"cwd": "/tmp/demo", "shell": "bash"},
            workspace_snapshot={"cwd": "/tmp/demo", "instructions_digest": "digest-recovery-loop"},
        ),
        rounds=[
            ReplayRound(
                index=1,
                request={
                    "model": "gpt-5.4",
                    "instructions": instructions,
                    "input": [
                        {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": user_prompt}],
                        }
                    ],
                    "store": False,
                    "stream": False,
                    "tools": tool_specs,
                    "tool_choice": "auto",
                    "parallel_tool_calls": False,
                },
                response={
                    "id": "resp_1",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call_1",
                            "name": "agent_workflow",
                            "arguments": '{"target":"agent_1","steps":3,"checkpoints":2}',
                        }
                    ],
                    "output_text": "",
                },
            ),
            ReplayRound(
                index=2,
                request={
                    "model": "gpt-5.4",
                    "instructions": instructions,
                    "input": [
                        {
                            "type": "function_call_output",
                            "call_id": "call_1",
                            "output": workflow_output,
                        },
                    ],
                    "previous_response_id": "resp_1",
                    "store": False,
                    "stream": False,
                    "tools": tool_specs,
                    "tool_choice": "auto",
                    "parallel_tool_calls": False,
                },
                response={
                    "id": "resp_2",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call_2",
                            "name": "recover_agent",
                            "arguments": '{"target":"agent_1"}',
                        }
                    ],
                    "output_text": "",
                },
            ),
            ReplayRound(
                index=3,
                request={
                    "model": "gpt-5.4",
                    "instructions": instructions,
                    "input": [
                        {
                            "type": "function_call_output",
                            "call_id": "call_2",
                            "output": recover_output,
                        },
                    ],
                    "previous_response_id": "resp_2",
                    "store": False,
                    "stream": False,
                    "tools": tool_specs,
                    "tool_choice": "auto",
                    "parallel_tool_calls": False,
                },
                response={
                    "id": "resp_3",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "phase": "final_answer",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "已检查 workflow，并在原会话内重试失败步骤。",
                                }
                            ],
                        }
                    ],
                    "output_text": "",
                },
            ),
        ],
        tool_calls=[
            ReplayToolCall(
                index=1,
                round_index=1,
                tool_name="agent_workflow",
                call_id="call_1",
                command_text="/agent_workflow agent_1 --steps 3 --checkpoints 2",
                arguments={"target": "agent_1", "steps": 3, "checkpoints": 2},
                output_items=[
                    {
                        "type": "function_call_output",
                        "call_id": "call_1",
                        "output": workflow_output,
                        "success": True,
                    }
                ],
            ),
            ReplayToolCall(
                index=2,
                round_index=2,
                tool_name="recover_agent",
                call_id="call_2",
                command_text="/recover_agent agent_1 --action retry_step",
                arguments={"target": "agent_1"},
                output_items=[
                    {
                        "type": "function_call_output",
                        "call_id": "call_2",
                        "output": recover_output,
                        "success": True,
                    }
                ],
            ),
        ],
    )

    replay_client = ReplayOpenAIClient(cassette)
    planner.client = replay_client
    tool_executor = ReplayToolExecutor(cassette)

    intent = planner.plan(user_prompt, [], tool_executor=tool_executor)

    assert intent.assistant_text == "已检查 workflow，并在原会话内重试失败步骤。"
    assert len(replay_client.responses.requests) == 3
    assert replay_client.responses.requests[1]["previous_response_id"] == "resp_1"
    assert replay_client.responses.requests[1]["input"] == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": workflow_output,
        }
    ]
    assert replay_client.responses.requests[2]["previous_response_id"] == "resp_2"
    assert replay_client.responses.requests[2]["input"] == [
        {
            "type": "function_call_output",
            "call_id": "call_2",
            "output": recover_output,
        }
    ]
    assert list(tool_executor.remaining_tool_calls()) == []
