from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cli.agent_cli.models import AgentIntent
from cli.agent_cli.runtime_core import execute_agent_intent_result, run_command_text_result
from cli.agent_cli.slash_commands import slash_command_help_text


class _InitPlannerAgent:
    def __init__(self, behavior: Callable[..., AgentIntent]) -> None:
        self._behavior = behavior
        self.prompt_texts: list[str] = []
        self.plan_kwargs: list[dict[str, Any]] = []

    def plan(
        self,
        text: str,
        history=None,
        *,
        tool_executor=None,
        attachments=None,
        input_items=None,
        prompt_cache_key=None,
        turn_event_callback=None,
        current_dt=None,
        environment_snapshot=None,
    ) -> AgentIntent:
        self.prompt_texts.append(text)
        self.plan_kwargs.append(
            {
                "history": history,
                "tool_executor": tool_executor,
                "attachments": attachments,
                "input_items": input_items,
                "prompt_cache_key": prompt_cache_key,
                "turn_event_callback": turn_event_callback,
                "current_dt": current_dt,
                "environment_snapshot": environment_snapshot,
            }
        )
        return self._behavior(
            text=text,
            history=history,
            tool_executor=tool_executor,
            attachments=attachments,
            input_items=input_items,
            prompt_cache_key=prompt_cache_key,
            turn_event_callback=turn_event_callback,
            current_dt=current_dt,
            environment_snapshot=environment_snapshot,
        )


class _InitRuntimeStub:
    def __init__(
        self,
        root: Path,
        *,
        interactive: bool,
        planner_behavior: Callable[..., AgentIntent],
    ) -> None:
        self.cwd = Path(root)
        self.history: list[dict[str, Any]] = []
        self.collaboration_mode = "default"
        self.default_mode_request_user_input = False
        self.request_payloads: list[dict[str, Any]] = []
        self._request_responses: list[Any] = []
        self.request_user_input_handler = self._request_user_input_handler if interactive else None
        self.turn_events: list[dict[str, Any]] = []
        self.turn_event_callback = self.turn_events.append
        self.agent = _InitPlannerAgent(planner_behavior)

    def _run_command_text_result(self, text: str):
        return run_command_text_result(self, text)

    def _execute_agent_intent_result(self, intent: AgentIntent):
        return execute_agent_intent_result(self, intent)

    def _is_interrupt_requested(self) -> bool:
        return False

    def _interrupt_tuple(self) -> tuple[str, list[Any]]:
        return ("interrupted", [])

    def queue_request_response(self, response: Any) -> None:
        self._request_responses.append(response)

    def _request_user_input_handler(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        self.request_payloads.append(dict(payload or {}))
        if not self._request_responses:
            return None
        next_response = self._request_responses.pop(0)
        if callable(next_response):
            return next_response(payload)
        return dict(next_response or {}) if isinstance(next_response, dict) else None


def test_init_command_is_listed_in_help() -> None:
    help_text = slash_command_help_text()
    assert "/init [yes]" in help_text


def test_init_command_default_prompt_does_not_use_request_user_input() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".git").write_text("", encoding="utf-8")
        (root / "README.md").write_text("# Demo\n", encoding="utf-8")
        (root / "AGENTS.md").write_text("Legacy guidance", encoding="utf-8")
        (root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
        skill_dir = root / ".agents" / "skills" / "verify"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: verify\ndescription: run checks\n---\n# verify\n",
            encoding="utf-8",
        )

        def _behavior(**kwargs: Any) -> AgentIntent:
            return AgentIntent(
                assistant_text="llm init flow finished",
                tool_events=[],
            )

        runtime = _InitRuntimeStub(root, interactive=True, planner_behavior=_behavior)

        result = run_command_text_result(runtime, "/init")

        prompt_text = runtime.agent.prompt_texts[-1]
        assert result.assistant_text == "llm init flow finished"
        assert result.tool_events == []
        assert runtime.request_payloads == []
        assert "Generate a file named AENGTHUB.md" in prompt_text
        assert "200-400 words is optimal" in prompt_text
        assert "Do not call `request_user_input`." in prompt_text
        assert "Do not create skills, hooks, `.agenthub/rules/`" in prompt_text
        assert "Project Structure & Module Organization" in prompt_text
        assert "README.md" in prompt_text
        assert "pyproject.toml" in prompt_text
        assert runtime.default_mode_request_user_input is False


def test_init_command_skips_when_project_doc_exists() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".git").write_text("", encoding="utf-8")
        (root / "AENGTHUB.md").write_text("# Existing\n", encoding="utf-8")

        runtime = _InitRuntimeStub(
            root,
            interactive=True,
            planner_behavior=lambda **_kwargs: AgentIntent(assistant_text="should not run"),
        )

        result = run_command_text_result(runtime, "/init")

        assert result.assistant_text == (
            "AENGTHUB.md already exists here. Skipping /init to avoid overwriting it."
        )
        assert result.command_display_text == result.assistant_text
        assert runtime.agent.prompt_texts == []


def test_init_command_does_not_skip_when_only_parent_project_doc_exists() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".git").write_text("", encoding="utf-8")
        (root / "AENGTHUB.md").write_text("# Root\n", encoding="utf-8")
        nested = root / "nested"
        nested.mkdir()

        runtime = _InitRuntimeStub(
            nested,
            interactive=True,
            planner_behavior=lambda **_kwargs: AgentIntent(assistant_text="init prompt ran"),
        )

        result = run_command_text_result(runtime, "/init")

        assert result.assistant_text == "init prompt ran"
        assert runtime.agent.prompt_texts


def test_init_command_refresh_is_local_noop_without_provider_call() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".git").write_text("", encoding="utf-8")
        (root / "AENGTHUB.md").write_text("# Existing\n", encoding="utf-8")

        runtime = _InitRuntimeStub(
            root,
            interactive=True,
            planner_behavior=lambda **_kwargs: AgentIntent(assistant_text="should not run"),
        )

        result = run_command_text_result(runtime, "/init --refresh")

        assert "refresh is not supported" in result.assistant_text
        assert result.command_display_text == result.assistant_text
        assert runtime.agent.prompt_texts == []


def test_init_command_passes_turn_event_callback_to_planner() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".git").write_text("", encoding="utf-8")

        def _behavior(**kwargs: Any) -> AgentIntent:
            callback = kwargs["turn_event_callback"]
            assert callable(callback)
            callback({"type": "item.updated", "item": {"type": "message", "text": "streaming"}})
            return AgentIntent(assistant_text="done")

        runtime = _InitRuntimeStub(root, interactive=True, planner_behavior=_behavior)

        result = run_command_text_result(runtime, "/init")

        assert result.assistant_text == "done"
        assert runtime.agent.plan_kwargs[-1]["turn_event_callback"] is runtime.turn_event_callback
        assert runtime.turn_events == [
            {"type": "item.updated", "item": {"type": "message", "text": "streaming"}}
        ]


def test_init_command_uses_noop_turn_event_callback_when_runtime_has_none() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".git").write_text("", encoding="utf-8")

        runtime = _InitRuntimeStub(
            root,
            interactive=False,
            planner_behavior=lambda **_kwargs: AgentIntent(assistant_text="done"),
        )
        runtime.turn_event_callback = None

        result = run_command_text_result(runtime, "/init")

        callback = runtime.agent.plan_kwargs[-1]["turn_event_callback"]
        assert result.assistant_text == "done"
        assert callable(callback)
        assert callback({"type": "noop"}) is None


def test_init_command_does_not_enable_request_user_input_tool() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".git").write_text("", encoding="utf-8")
        payload = {
            "questions": [
                {
                    "id": "confirm_write",
                    "header": "Confirm",
                    "question": "Write files?",
                    "options": [{"label": "Yes", "description": "Write."}],
                }
            ]
        }

        def _behavior(**kwargs: Any) -> AgentIntent:
            tool_executor = kwargs["tool_executor"]
            command_result = tool_executor.run_structured(
                "/request_user_input '" + json.dumps(payload, ensure_ascii=False) + "'"
            )
            assistant_text, events = command_result.assistant_text, command_result.tool_events
            assert "request_user_input is unavailable" in assistant_text
            return AgentIntent(assistant_text="done", tool_events=list(events or []))

        runtime = _InitRuntimeStub(root, interactive=True, planner_behavior=_behavior)

        result = run_command_text_result(runtime, "/init")

        assert result.assistant_text == "done"
        assert result.tool_events[-1].name == "request_user_input"
        assert result.tool_events[-1].ok is False
        assert runtime.request_payloads == []


def test_init_command_noninteractive_prompt_forbids_request_user_input_and_writes() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".git").write_text("", encoding="utf-8")
        (root / "README.md").write_text("# Demo\n", encoding="utf-8")
        (root / "package.json").write_text(
            '{"name":"demo","scripts":{"build":"vite build"}}', encoding="utf-8"
        )

        runtime = _InitRuntimeStub(
            root,
            interactive=False,
            planner_behavior=lambda **_kwargs: AgentIntent(assistant_text="proposal only"),
        )

        result = run_command_text_result(runtime, "/init")

        prompt_text = runtime.agent.prompt_texts[-1]
        assert result.assistant_text == "proposal only"
        assert "Interactive user input is unavailable." in prompt_text
        assert "Do not call `request_user_input`." in prompt_text
        assert "Do not write files." in prompt_text
        assert "package.json" in prompt_text


def test_init_command_yes_prompt_uses_safe_defaults_without_request_user_input() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".git").write_text("", encoding="utf-8")
        (root / "README.md").write_text("# Demo\n", encoding="utf-8")

        runtime = _InitRuntimeStub(
            root,
            interactive=False,
            planner_behavior=lambda **_kwargs: AgentIntent(assistant_text="auto apply path"),
        )

        result = run_command_text_result(runtime, "/init --yes")

        prompt_text = runtime.agent.prompt_texts[-1]
        assert result.assistant_text == "auto apply path"
        assert "This run was invoked with `/init yes`." in prompt_text
        assert "write AENGTHUB.md directly" in prompt_text
        assert "Do not call `request_user_input`." in prompt_text
