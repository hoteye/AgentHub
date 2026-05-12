from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

from cli.agent_cli.host_platform import detect_host_platform
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.adapters.openai_responses import OpenAIResponsesSession
from cli.agent_cli.providers.openai_planner import OpenAIPlanner
from cli.replay_integration.schema import (
    ReplayCassette,
    ReplayManifest,
    ReplayRound,
    ReplaySessionMetadata,
    ReplayToolCall,
)


@dataclass(frozen=True)
class PlannerStepSpec:
    user_text: str
    assistant_text: str
    tool_name: str = ""
    tool_arguments: Dict[str, Any] = field(default_factory=dict)
    tool_output: str = ""
    tool_success: bool = True

    @property
    def uses_tool(self) -> bool:
        return bool(self.tool_name)


@dataclass(frozen=True)
class PlannerConversationCase:
    case_id: str
    category: str
    description: str
    steps: List[PlannerStepSpec]


def make_openai_planner() -> OpenAIPlanner:
    host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
    return OpenAIPlanner(
        ProviderConfig(model="gpt-5.4", api_key="sk-test"),
        host_platform=host_platform,
    )


def _assistant_response(response_id: str, text: str) -> Dict[str, Any]:
    return {
        "id": response_id,
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "phase": "final_answer",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
        "output_text": "",
    }


def _tool_call_response(
    response_id: str,
    *,
    call_id: str,
    tool_name: str,
    tool_arguments: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "id": response_id,
        "output": [
            {
                "type": "function_call",
                "call_id": call_id,
                "name": tool_name,
                "arguments": json.dumps(tool_arguments, ensure_ascii=False, separators=(",", ":")),
            }
        ],
        "output_text": "",
    }


def _planner_request(
    planner: OpenAIPlanner,
    *,
    input_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    normalized_input = OpenAIResponsesSession._normalize_input_items(
        input_items,
        reference_parity=planner.reference_parity_enabled,
    )
    return {
        "model": planner.config.model,
        "instructions": planner.native_tool_system_prompt,
        "input": normalized_input,
        "tools": planner._tool_specs(),
        "tool_choice": "auto",
        "parallel_tool_calls": False,
    }


def build_planner_case_cassette(
    planner: OpenAIPlanner,
    case: PlannerConversationCase,
) -> ReplayCassette:
    rounds: List[ReplayRound] = []
    tool_calls: List[ReplayToolCall] = []
    history: List[Dict[str, str]] = []
    round_index = 1

    for step_index, step in enumerate(list(case.steps or []), start=1):
        initial_input = planner._conversation_input_items(step.user_text, list(history))
        if not step.uses_tool:
            rounds.append(
                ReplayRound(
                    index=round_index,
                    request=_planner_request(planner, input_items=initial_input),
                    response=_assistant_response(f"resp_{round_index}", step.assistant_text),
                )
            )
            round_index += 1
        else:
            call_id = f"call_{step_index}"
            command_text = planner._command_for_function_call(step.tool_name, dict(step.tool_arguments or {}))
            if not command_text:
                raise ValueError(f"failed to build command_text for case {case.case_id}")

            rounds.append(
                ReplayRound(
                    index=round_index,
                    request=_planner_request(planner, input_items=initial_input),
                    response=_tool_call_response(
                        f"resp_{round_index}",
                        call_id=call_id,
                        tool_name=step.tool_name,
                        tool_arguments=dict(step.tool_arguments or {}),
                    ),
                )
            )
            tool_calls.append(
                ReplayToolCall(
                    index=len(tool_calls) + 1,
                    round_index=round_index,
                    tool_name=step.tool_name,
                    call_id=call_id,
                    command_text=command_text,
                    arguments=dict(step.tool_arguments or {}),
                    output_items=[
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": step.tool_output,
                            "success": bool(step.tool_success),
                        }
                    ],
                )
            )
            round_index += 1

            continuation_input = [
                *list(initial_input or []),
                {
                    "type": "function_call",
                    "call_id": call_id,
                    "name": step.tool_name,
                    "arguments": json.dumps(step.tool_arguments, ensure_ascii=False, separators=(",", ":")),
                },
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": step.tool_output,
                },
            ]
            rounds.append(
                ReplayRound(
                    index=round_index,
                    request=_planner_request(planner, input_items=continuation_input),
                    response=_assistant_response(f"resp_{round_index}", step.assistant_text),
                )
            )
            round_index += 1

        history.extend(
            [
                {"role": "user", "content": step.user_text},
                {"role": "assistant", "content": step.assistant_text},
            ]
        )

    return ReplayCassette(
        manifest=ReplayManifest(
            name=case.case_id,
            notes=case.description,
            session=ReplaySessionMetadata(
                provider="replay",
                model=planner.config.model,
                transport_kind="responses_http",
            ),
            environment_snapshot={"cwd": "/tmp/replay", "shell": "bash"},
            workspace_snapshot={"cwd": "/tmp/replay", "instructions_digest": f"digest:{case.case_id}"},
        ),
        rounds=rounds,
        tool_calls=tool_calls,
    )


def formal_planner_cases() -> List[PlannerConversationCase]:
    return [
        PlannerConversationCase(
            case_id="memory_2turn_name",
            category="memory",
            description="2-turn memory retention for a single entity",
            steps=[
                PlannerStepSpec(
                    user_text="我叫张三。请只回复“记住了”。",
                    assistant_text="记住了",
                ),
                PlannerStepSpec(
                    user_text="我刚才说我叫什么？只回复名字。",
                    assistant_text="张三",
                ),
            ],
        ),
        PlannerConversationCase(
            case_id="memory_3turn_facts",
            category="memory",
            description="3-turn memory retention across two stored facts",
            steps=[
                PlannerStepSpec(
                    user_text="我叫李雷。请只回复“记住了”。",
                    assistant_text="记住了",
                ),
                PlannerStepSpec(
                    user_text="我在杭州工作。请只回复“记住了”。",
                    assistant_text="记住了",
                ),
                PlannerStepSpec(
                    user_text="我叫什么，在哪里工作？只用一句话回答。",
                    assistant_text="你叫李雷，在杭州工作。",
                ),
            ],
        ),
        PlannerConversationCase(
            case_id="memory_5turn_profile",
            category="memory",
            description="5-turn memory retention across four prior facts",
            steps=[
                PlannerStepSpec(
                    user_text="我叫王敏。请只回复“记住了”。",
                    assistant_text="记住了",
                ),
                PlannerStepSpec(
                    user_text="我在上海。请只回复“记住了”。",
                    assistant_text="记住了",
                ),
                PlannerStepSpec(
                    user_text="我是测试工程师。请只回复“记住了”。",
                    assistant_text="记住了",
                ),
                PlannerStepSpec(
                    user_text="我的项目代号是天枢。请只回复“记住了”。",
                    assistant_text="记住了",
                ),
                PlannerStepSpec(
                    user_text="把我前四轮说的信息合成一句话。",
                    assistant_text="你叫王敏，在上海，是测试工程师，项目代号是天枢。",
                ),
            ],
        ),
        PlannerConversationCase(
            case_id="reference_person_pronoun",
            category="reference",
            description="Resolve a pronoun back to a previously mentioned person",
            steps=[
                PlannerStepSpec(
                    user_text="新同事叫李雷。请只回复“记住了”。",
                    assistant_text="记住了",
                ),
                PlannerStepSpec(
                    user_text="他叫什么？只回复名字。",
                    assistant_text="李雷",
                ),
            ],
        ),
        PlannerConversationCase(
            case_id="reference_path_followup",
            category="reference",
            description="Resolve a previously mentioned absolute path",
            steps=[
                PlannerStepSpec(
                    user_text="项目目录是 /srv/app。请记住这个路径，并只回复“记住了”。",
                    assistant_text="记住了",
                ),
                PlannerStepSpec(
                    user_text="刚才那个目录是什么？只回复路径。",
                    assistant_text="/srv/app",
                ),
            ],
        ),
        PlannerConversationCase(
            case_id="reference_variable_value",
            category="reference",
            description="Resolve a previously mentioned variable value",
            steps=[
                PlannerStepSpec(
                    user_text="变量 API_BASE 的值是 https://api.example.com/v1 。请只回复“记住了”。",
                    assistant_text="记住了",
                ),
                PlannerStepSpec(
                    user_text="API_BASE 是什么？只回复值。",
                    assistant_text="https://api.example.com/v1",
                ),
            ],
        ),
        PlannerConversationCase(
            case_id="history_compression_summary",
            category="compression",
            description="Compress two prior turns into a single sentence",
            steps=[
                PlannerStepSpec(
                    user_text="我叫张三。请只回复“记住了”。",
                    assistant_text="记住了",
                ),
                PlannerStepSpec(
                    user_text="我喜欢 Go。请只回复“记住了”。",
                    assistant_text="记住了",
                ),
                PlannerStepSpec(
                    user_text="把前两轮压缩成一句话。只输出结果。",
                    assistant_text="你叫张三，喜欢 Go。",
                ),
            ],
        ),
        PlannerConversationCase(
            case_id="tool_followup_pwd_memory",
            category="tool_followup",
            description="Run pwd, answer from tool output, then answer a follow-up turn from memory",
            steps=[
                PlannerStepSpec(
                    user_text="先执行 pwd，再告诉我当前目录。",
                    assistant_text="当前目录是 /tmp/demo",
                    tool_name="exec_command",
                    tool_arguments={"cmd": "pwd"},
                    tool_output="/tmp/demo",
                    tool_success=True,
                ),
                PlannerStepSpec(
                    user_text="刚才目录是什么？只回复路径。",
                    assistant_text="/tmp/demo",
                ),
            ],
        ),
        PlannerConversationCase(
            case_id="error_recovery_after_tool_failure",
            category="error_recovery",
            description="Recover after a failing tool round and answer a follow-up question",
            steps=[
                PlannerStepSpec(
                    user_text="先执行 ls /missing，再告诉我结果。",
                    assistant_text="命令失败：目录 /missing 不存在。",
                    tool_name="exec_command",
                    tool_arguments={"cmd": "ls /missing"},
                    tool_output="ls: cannot access '/missing': No such file or directory",
                    tool_success=False,
                ),
                PlannerStepSpec(
                    user_text="上一轮失败的原因是什么？只回复一句话。",
                    assistant_text="因为目录 /missing 不存在。",
                ),
            ],
        ),
    ]
