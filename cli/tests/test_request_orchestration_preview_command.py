from __future__ import annotations

import json
import shlex

from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_core import run_command_text_result
from cli.agent_cli.runtime_core.orchestration_commands import handle_orchestration_command


class _PreviewRuntimeStub:
    def __init__(self, *, interactive: bool = False) -> None:
        self.preview_calls: list[dict[str, object]] = []
        self.create_calls: list[dict[str, object]] = []
        self.dispatch_calls: list[str] = []
        self.request_payloads: list[dict[str, object]] = []
        self._request_responses: list[dict[str, object] | None] = []
        self.request_user_input_handler = self._request_user_input_handler if interactive else None

    def queue_request_response(self, response: dict[str, object] | None) -> None:
        self._request_responses.append(response)

    def _request_user_input_handler(self, payload: dict[str, object]) -> dict[str, object] | None:
        self.request_payloads.append(dict(payload or {}))
        if not self._request_responses:
            return None
        return self._request_responses.pop(0)

    def preview_orchestration_run(
        self,
        source_text: str,
        *,
        planning_adjustments: dict[str, object] | None = None,
        relaxed_taskbook: bool = False,
    ) -> dict[str, object]:
        del relaxed_taskbook
        normalized_adjustments = dict(planning_adjustments or {})
        self.preview_calls.append(
            {
                "source_text": source_text,
                "planning_adjustments": normalized_adjustments,
            }
        )
        adjustment_lines = [
            f"{key}={value}" for key, value in normalized_adjustments.items() if str(key).strip()
        ]
        return {
            "preview_id": "preview_run_001",
            "objective": "拆分编排入口",
            "routing_mode": "orchestrated",
            "taskbook_version": 1,
            "card_count": 2,
            "ready_card_ids": ["CARD-001"],
            "blocked_card_ids": ["CARD-002"],
            "planning_adjustment_lines": adjustment_lines,
        }

    def create_orchestration_run(
        self,
        source_text: str,
        *,
        planning_adjustments: dict[str, object] | None = None,
        relaxed_taskbook: bool = False,
    ) -> dict[str, object]:
        del relaxed_taskbook
        normalized_adjustments = dict(planning_adjustments or {})
        self.create_calls.append(
            {
                "source_text": source_text,
                "planning_adjustments": normalized_adjustments,
            }
        )
        return {
            "run_id": "run_request_orchestration_001",
            "mode": "interactive",
            "routing_mode": "orchestrated",
            "status": "created",
            "current_phase": "created",
            "taskbook_source": "preview",
            "taskbook_version": 1,
            "card_count": 2,
            "ready_card_ids": ["CARD-001"],
            "blocked_card_ids": ["CARD-002"],
            "running_card_ids": [],
            "completed_card_ids": [],
            "run_path": "/tmp/run_request_orchestration_001",
            "projection_path": "/tmp/run_request_orchestration_001/projection.md",
        }

    def dispatch_orchestration_run(self, run_id: str) -> dict[str, object]:
        self.dispatch_calls.append(str(run_id))
        return {
            "run_id": str(run_id),
            "status": "running",
            "current_phase": "cards_dispatched",
            "selected_card_ids": ["CARD-001"],
            "dispatched_card_ids": ["CARD-001"],
            "dispatch_refs": ["visible_child_tab:tab-1"],
            "ready_card_ids": [],
            "blocked_card_ids": ["CARD-002"],
            "running_card_ids": ["CARD-001"],
            "completed_card_ids": [],
        }


def test_internal_request_orchestration_command_returns_preview_without_create() -> None:
    runtime = _PreviewRuntimeStub()
    arg_text = json.dumps(
        {
            "source_text": "把大文件拆成模块并补回归测试",
            "goal": "完成编排入口改造",
            "reason": "多阶段任务",
            "needs_confirmation": True,
            "planning_adjustments": {"max_parallel_cards": 2},
        },
        ensure_ascii=True,
    )

    text, events = handle_orchestration_command(
        runtime,
        name="__request_orchestration",
        arg_text=arg_text,
    ) or ("", [])

    assert events == []
    assert "orchestration preview ready" in text
    assert "status=preview_ready" in text
    assert "confirmation_required=true" in text
    assert "next_action=show_preview_confirm_ui" in text
    assert "preview_id=preview_run_001" in text
    assert "card_count=2" in text
    assert runtime.preview_calls == [
        {
            "source_text": "把大文件拆成模块并补回归测试",
            "planning_adjustments": {"max_parallel_cards": 2},
        }
    ]
    assert runtime.create_calls == []
    assert runtime.request_payloads == []


def test_internal_request_orchestration_command_enters_confirmation_flow_when_interactive() -> None:
    runtime = _PreviewRuntimeStub(interactive=True)
    runtime.queue_request_response(
        {"answers": {"taskbook_action": {"answers": ["Confirm and start"]}}}
    )
    arg_text = json.dumps(
        {
            "source_text": "把大文件拆成模块并补回归测试",
            "goal": "完成编排入口改造",
            "reason": "多阶段任务",
            "needs_confirmation": True,
            "planning_adjustments": {"max_parallel_cards": 2},
        },
        ensure_ascii=True,
    )

    text, events = handle_orchestration_command(
        runtime,
        name="__request_orchestration",
        arg_text=arg_text,
    ) or ("", [])

    assert events == []
    assert "orchestration confirmation accepted" in text
    assert "run_id=run_request_orchestration_001" in text
    assert "orchestration dispatch submitted" in text
    assert "dispatched_cards=CARD-001" in text
    assert "planning_adjustments=max_parallel_cards=2" in text
    assert runtime.preview_calls == [
        {
            "source_text": "把大文件拆成模块并补回归测试",
            "planning_adjustments": {"max_parallel_cards": 2},
        }
    ]
    assert runtime.create_calls == [
        {
            "source_text": "把大文件拆成模块并补回归测试",
            "planning_adjustments": {"max_parallel_cards": 2},
        }
    ]
    assert runtime.dispatch_calls == ["run_request_orchestration_001"]
    assert len(runtime.request_payloads) == 1
    question = runtime.request_payloads[0]["questions"][0]["question"]
    assert "Taskbook preview" in question
    assert "max_parallel_cards=2" in question


def test_internal_request_orchestration_command_cancelled_in_interactive_flow_does_not_create() -> (
    None
):
    runtime = _PreviewRuntimeStub(interactive=True)
    runtime.queue_request_response({"answers": {"taskbook_action": {"answers": ["Cancel"]}}})
    arg_text = json.dumps(
        {
            "source_text": "把大文件拆成模块并补回归测试",
            "goal": "完成编排入口改造",
            "reason": "多阶段任务",
            "needs_confirmation": True,
        },
        ensure_ascii=True,
    )

    text, events = handle_orchestration_command(
        runtime,
        name="__request_orchestration",
        arg_text=arg_text,
    ) or ("", [])

    assert events == []
    assert "orchestration confirmation cancelled" in text
    assert "no orchestration run was created" in text
    assert runtime.create_calls == []
    assert len(runtime.request_payloads) == 1


def test_internal_request_orchestration_command_requires_source_text() -> None:
    runtime = _PreviewRuntimeStub()
    text, events = handle_orchestration_command(
        runtime,
        name="__request_orchestration",
        arg_text=json.dumps({"goal": "missing source"}),
    ) or ("", [])
    assert events == []
    assert "__request_orchestration requires source_text" in text
    assert runtime.preview_calls == []


def test_internal_request_orchestration_command_accepts_shell_quoted_json_payload() -> None:
    runtime = _PreviewRuntimeStub()
    raw_payload = json.dumps(
        {
            "source_text": "把大文件拆成模块并补回归测试",
            "goal": "完成编排入口改造",
            "reason": "多阶段任务",
            "needs_confirmation": True,
        },
        ensure_ascii=True,
    )

    text, events = handle_orchestration_command(
        runtime,
        name="__request_orchestration",
        arg_text=f"'{raw_payload}'",
    ) or ("", [])

    assert events == []
    assert "orchestration preview ready" in text
    assert runtime.preview_calls == [
        {
            "source_text": "把大文件拆成模块并补回归测试",
            "planning_adjustments": {},
        }
    ]


def test_internal_request_orchestration_command_relaxes_markdown_outline_into_preview() -> None:
    runtime = AgentCliRuntime()
    payload = json.dumps(
        {
            "source_text": (
                "## 复杂改造任务：Provider Availability 探测 + 编排入口接入 + 回归测试 + 文档整理\n\n"
                "### 阶段一：Provider Availability 探测\n"
                "- 补充 provider 可用性探测逻辑\n"
                "- 支持在编排前检测各 provider 是否可达\n\n"
                "### 阶段二：编排入口接入 host/TUI 确认流\n"
                "- 将编排入口与 host/TUI 确认流程对接\n"
                "- 用户在 TUI 中可确认/取消编排操作\n\n"
                "### 阶段三：补回归测试\n"
                "- 覆盖 provider 探测、编排确认流等核心路径\n\n"
                "### 阶段四：文档整理\n"
                "- 更新相关文档，说明新增能力和使用方式\n"
            ),
            "goal": "复杂改造任务编排预览",
            "reason": "多阶段任务需要先进入编排确认流",
            "needs_confirmation": True,
        },
        ensure_ascii=True,
    )

    result = run_command_text_result(
        runtime,
        f"/__request_orchestration {shlex.quote(payload)}",
    )

    assert result.tool_events == []
    assert "orchestration preview ready" in result.assistant_text
    assert "card_count=4" in result.assistant_text
    assert "ready_card_ids=CARD-001,CARD-002,CARD-003,CARD-004" in result.assistant_text
