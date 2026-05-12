from __future__ import annotations

import json
from typing import Any

from .schema import ReplayCassette, ReplayManifest, ReplayRound, ReplaySessionMetadata, ReplayToolCall


def _fixture_request(prompt: str) -> dict[str, Any]:
    return {
        "model": "gpt-5.4",
        "parallel_tool_calls": False,
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": str(prompt or "").strip()}],
            }
        ],
    }


def _message_output_item(text: str, *, phase: str = "final_answer") -> dict[str, Any]:
    return {
        "type": "message",
        "phase": phase,
        "role": "assistant",
        "content": [{"type": "output_text", "text": str(text or "").strip()}],
    }


def _function_call_item(call_id: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function_call",
        "call_id": call_id,
        "name": tool_name,
        "arguments": json.dumps(arguments or {}, ensure_ascii=False, separators=(",", ":")),
    }


def _function_call_output_item(call_id: str, output: str, *, success: bool = True) -> dict[str, Any]:
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": str(output or ""),
        "success": bool(success),
    }


def _fixture_command_text(tool_name: str, arguments: dict[str, Any]) -> str:
    normalized_tool = str(tool_name or "").strip()
    normalized_arguments = dict(arguments or {})
    if normalized_tool == "exec_command":
        return str(normalized_arguments.get("cmd") or "").strip() or normalized_tool
    if normalized_tool == "web_search":
        return f"/web_search {str(normalized_arguments.get('query') or '').strip()}".strip()
    return f"{normalized_tool} {json.dumps(normalized_arguments, ensure_ascii=False, sort_keys=True)}".strip()


def _build_fixture_single_turn_case(
    *,
    case_id: str,
    notes: str,
    coverage_tags: tuple[str, ...],
    prompt: str,
    commentary_text: str,
    tool_name: str,
    tool_arguments: dict[str, Any],
    tool_output: str,
    assistant_text: str,
    tool_success: bool = True,
) -> ReplayCassette:
    call_id = f"{case_id}_call_1"
    response_items: list[dict[str, Any]] = []
    if str(commentary_text or "").strip():
        response_items.append(_message_output_item(commentary_text, phase="commentary"))
    response_items.extend(
        [
            _function_call_item(call_id, tool_name, tool_arguments),
            _function_call_output_item(call_id, tool_output, success=tool_success),
            _message_output_item(assistant_text),
        ]
    )
    return ReplayCassette(
        manifest=ReplayManifest(
            name=f"fixture-{case_id}",
            case_id=case_id,
            notes=notes,
            parity_targets=["behavioral_parity_required", "protocol_path_parity_required"],
            coverage_tags=list(coverage_tags),
            session=ReplaySessionMetadata(
                provider="fixture_live",
                model="gpt-5.4",
                transport_kind="responses_http",
            ),
            environment_snapshot={
                "cwd": "/home/lyc/project/AgentHub/cli",
                "shell": "bash",
                "current_date": "2026-03-31",
                "timezone": "Asia/Shanghai",
            },
            workspace_snapshot={
                "cwd": "/home/lyc/project/AgentHub/cli",
                "instructions_digest": f"fixture:{case_id}",
            },
        ),
        rounds=[
            ReplayRound(
                index=1,
                request=_fixture_request(prompt),
                response={
                    "id": f"resp_{case_id}_1",
                    "output": response_items,
                    "output_text": str(assistant_text or "").strip(),
                },
            )
        ],
        tool_calls=[
            ReplayToolCall(
                index=1,
                round_index=1,
                tool_name=tool_name,
                call_id=call_id,
                command_text=_fixture_command_text(tool_name, tool_arguments),
                arguments=dict(tool_arguments or {}),
                output_items=[_function_call_output_item(call_id, tool_output, success=tool_success)],
            )
        ],
    )


def _shell_pwd_fixture_cassette() -> ReplayCassette:
    return _build_fixture_single_turn_case(
        case_id="shell_pwd",
        notes="Operator/live shell surface fixture aligned to benchmark acceptance.",
        coverage_tags=("operator_live_surface", "shell", "benchmark_case_pack"),
        prompt="执行 pwd，然后只回复当前目录路径。",
        commentary_text="我先执行 `pwd`，然后只返回路径。",
        tool_name="exec_command",
        tool_arguments={"cmd": "pwd"},
        tool_output="/home/lyc/project/AgentHub/cli\n",
        assistant_text="/home/lyc/project/AgentHub/cli",
    )


def _write_readme_fixture_cassette() -> ReplayCassette:
    patch_text = "*** Begin Patch\n*** Add File: README.md\n+hello\n*** End Patch"
    return _build_fixture_single_turn_case(
        case_id="write_readme",
        notes="Operator/live write surface fixture aligned to benchmark acceptance.",
        coverage_tags=("operator_live_surface", "write", "benchmark_case_pack"),
        prompt="创建 README.md，内容只包含 hello，然后只回复 README.md。",
        commentary_text="我会先写入文件，然后只返回文件名。",
        tool_name="apply_patch",
        tool_arguments={"patch": patch_text},
        tool_output="README.md",
        assistant_text="README.md",
    )


def _edit_settings_fixture_cassette() -> ReplayCassette:
    patch_text = (
        "*** Begin Patch\n"
        "*** Update File: settings.toml\n"
        "@@\n"
        "-mode = \"dev\"\n"
        "+mode = \"prod\"\n"
        "*** End Patch"
    )
    return _build_fixture_single_turn_case(
        case_id="edit_settings",
        notes="Operator/live edit surface fixture aligned to benchmark acceptance.",
        coverage_tags=("operator_live_surface", "edit", "benchmark_case_pack"),
        prompt="把 settings.toml 里的 mode 改成 prod，然后只回复 settings.toml。",
        commentary_text="我会先改文件，然后只返回文件名。",
        tool_name="apply_patch",
        tool_arguments={"patch": patch_text},
        tool_output="settings.toml",
        assistant_text="settings.toml",
    )


def _search_weather_fixture_cassette() -> ReplayCassette:
    return _build_fixture_single_turn_case(
        case_id="search_weather",
        notes="Operator/live search surface fixture aligned to benchmark acceptance.",
        coverage_tags=("operator_live_surface", "search", "benchmark_case_pack"),
        prompt="搜索 Shanghai weather，然后只回复 Shanghai。",
        commentary_text="我先查一下，再只返回地点。",
        tool_name="web_search",
        tool_arguments={"query": "Shanghai weather"},
        tool_output="Shanghai weather: cloudy",
        assistant_text="Shanghai",
    )


def _delegate_probe_fixture_cassette() -> ReplayCassette:
    return _build_fixture_single_turn_case(
        case_id="delegate_probe",
        notes="Operator/live delegation surface fixture aligned to benchmark acceptance.",
        coverage_tags=("operator_live_surface", "agent_delegation", "benchmark_case_pack"),
        prompt="启动一个 explorer agent 做仓库摘要，然后只回复 worker summary。",
        commentary_text="我先启动一个 explorer agent，再只返回摘要结果。",
        tool_name="spawn_agent",
        tool_arguments={
            "agent_type": "explorer",
            "message": "Summarize the repository in one short paragraph.",
        },
        tool_output="worker summary",
        assistant_text="worker summary",
    )
