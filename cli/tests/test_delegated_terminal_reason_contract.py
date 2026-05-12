import shlex
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.models import AgentIntent
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_policy import RuntimePolicy


class _DelegateAgent:
    host_platform = current_host_platform()

    def __init__(self) -> None:
        self.delegate_overrides: dict[str, dict[str, str]] = {}

    @staticmethod
    def provider_status():
        return {
            "provider_ready": "true",
            "provider_name": "openai",
            "provider_model": "gpt-5.4",
            "provider_reasoning_effort": "high",
            "provider_planner": "openai_responses",
            "provider_source": "test",
            "provider_label": "openai | gpt-5.4 | tool-calls",
            "model_key": "gpt_54",
            "session_line": "openai-tools",
            "shell_kind": "bash",
        }

    def configure_delegate_selection(
        self,
        role_name,
        *,
        model=None,
        provider=None,
        reasoning_effort=None,
        timeout=None,
        clear=False,
    ):
        if clear:
            self.delegate_overrides.pop(str(role_name), None)
        else:
            self.delegate_overrides[str(role_name)] = {
                "model": str(model or ""),
                "provider": str(provider or ""),
                "reasoning_effort": str(reasoning_effort or ""),
                "timeout": str(timeout or ""),
            }
        return self.provider_status()

    @staticmethod
    def resolve_delegate_execution(
        role_name,
        *,
        model=None,
        provider=None,
        reasoning_effort=None,
        timeout=None,
    ):
        del model, provider, reasoning_effort, timeout
        assert role_name in {"subagent", "teammate"}
        return SimpleNamespace(
            config=ProviderConfig(
                model="glm-5",
                api_key="sk-glm",
                provider_name="glm",
                model_key="glm_5",
                planner_kind="openai_chat",
                wire_api="openai_chat",
                base_url="https://glm.example/v1",
                reasoning_effort="medium",
                raw_model={},
            ),
            timeout=18,
            source="delegation",
        )


class DelegatedTerminalReasonContractTest(unittest.TestCase):
    def test_role_override_changed_cleanup_marks_active_teammate_as_orphaned(self):
        class _SlowTeammatePlanner:
            started = threading.Event()

            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del user_text, history, attachments, input_items, prompt_cache_key
                self.__class__.started.set()
                command = (
                    f"{shlex.quote(sys.executable)} -u -c "
                    + shlex.quote("import sys,time; print('delegated-role-override'); sys.stdout.flush(); time.sleep(30)")
                )
                result = tool_executor.run_structured(
                    f"/exec_command --cmd {shlex.quote(command)} --yield-time-ms 5000"
                )
                if tool_executor.interrupt_requested():
                    interrupt_text, interrupt_events = tool_executor.interrupt_result()
                    return AgentIntent(
                        assistant_text=str(interrupt_text or result.assistant_text or ""),
                        tool_events=[*list(result.tool_events or []), *list(interrupt_events or [])],
                        turn_events=list(result.turn_events or []),
                    )
                return AgentIntent(
                    assistant_text=str(result.assistant_text or ""),
                    tool_events=list(result.tool_events or []),
                    turn_events=list(result.turn_events or []),
                )

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        _SlowTeammatePlanner.started = threading.Event()
        with patch("cli.agent_cli.runtime.build_planner", side_effect=lambda *args, **kwargs: _SlowTeammatePlanner()):
            spawned = runtime.spawn_agent_result(
                task="slow teammate task",
                role="teammate",
                async_mode=True,
                mode="background",
                wait_required=False,
            )
            agent_id = spawned.tool_events[0].payload["agent_id"]

            self.assertTrue(_SlowTeammatePlanner.started.wait(timeout=3))
            runtime.configure_delegate_selection(
                "teammate",
                model="glm_5",
                provider="glm",
                reasoning_effort="medium",
                timeout=30,
            )
            waited = runtime.wait_agent_result(agent_id, timeout_ms=6000)
            worker = runtime._delegated_agents[agent_id].worker
            if worker is not None:
                worker.join(timeout=1)

        payload = waited.tool_events[0].payload
        self.assertEqual(payload["status"], "closed")
        self.assertEqual(payload["terminal_reason"], "role_override_changed")
        self.assertEqual(payload["terminal_state"], "orphaned")
        self.assertEqual(payload["result_contract"]["status"], "closed")
        self.assertEqual(payload["result_contract"]["artifact"]["kind"], "empty")
        self.assertEqual(payload["result_contract"]["confidence"], "low")
        self.assertNotEqual(payload["terminal_state"], "closed_by_request")

    def test_close_interrupt_keeps_closed_empty_low_confidence_contract(self):
        class _CloseInterruptPlanner:
            started = threading.Event()

            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del user_text, history, attachments, input_items, prompt_cache_key
                self.__class__.started.set()
                command = (
                    f"{shlex.quote(sys.executable)} -u -c "
                    + shlex.quote("import sys,time; print('delegated-close'); sys.stdout.flush(); time.sleep(30)")
                )
                result = tool_executor.run_structured(
                    f"/exec_command --cmd {shlex.quote(command)} --yield-time-ms 5000"
                )
                if tool_executor.interrupt_requested():
                    interrupt_text, interrupt_events = tool_executor.interrupt_result()
                    return AgentIntent(
                        assistant_text=str(interrupt_text or result.assistant_text or ""),
                        tool_events=[*list(result.tool_events or []), *list(interrupt_events or [])],
                        turn_events=list(result.turn_events or []),
                    )
                return AgentIntent(
                    assistant_text=str(result.assistant_text or ""),
                    tool_events=list(result.tool_events or []),
                    turn_events=list(result.turn_events or []),
                )

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        _CloseInterruptPlanner.started = threading.Event()
        with patch("cli.agent_cli.runtime.build_planner", side_effect=lambda *args, **kwargs: _CloseInterruptPlanner()):
            spawned = runtime.spawn_agent_result(task="slow turn", role="subagent", async_mode=True)
            agent_id = spawned.tool_events[0].payload["agent_id"]

            self.assertTrue(_CloseInterruptPlanner.started.wait(timeout=3))
            close_result = runtime.close_agent_result(agent_id)
            self.assertIn(close_result.tool_events[0].payload["status"], {"closing", "closed"})

            waited = runtime.wait_agent_result(agent_id, timeout_ms=6000)

        payload = waited.tool_events[0].payload
        self.assertEqual(payload["status"], "closed")
        self.assertEqual(payload["terminal_reason"], "close_requested")
        self.assertEqual(payload["terminal_state"], "closed_by_request")
        self.assertEqual(payload["result_contract"]["status"], "closed")
        self.assertEqual(payload["result_contract"]["artifact"]["kind"], "empty")
        self.assertEqual(payload["result_contract"]["confidence"], "low")

    def test_interrupt_follow_up_counts_only_completed_turns(self):
        class _InterruptiblePlanner:
            calls: list[str] = []
            slow_turn_started = threading.Event()

            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, attachments, input_items, prompt_cache_key
                self.__class__.calls.append(str(user_text))
                if user_text == "slow turn":
                    self.__class__.slow_turn_started.set()
                    command = (
                        f"{shlex.quote(sys.executable)} -u -c "
                        + shlex.quote("import sys,time; print('delegated-ready'); sys.stdout.flush(); time.sleep(30)")
                    )
                    result = tool_executor.run_structured(
                        f"/exec_command --cmd {shlex.quote(command)} --yield-time-ms 5000"
                    )
                    if tool_executor.interrupt_requested():
                        interrupt_text, interrupt_events = tool_executor.interrupt_result()
                        return AgentIntent(
                            assistant_text=str(interrupt_text or result.assistant_text or ""),
                            tool_events=[*list(result.tool_events or []), *list(interrupt_events or [])],
                            turn_events=list(result.turn_events or []),
                        )
                    return AgentIntent(
                        assistant_text=str(result.assistant_text or ""),
                        tool_events=list(result.tool_events or []),
                        turn_events=list(result.turn_events or []),
                    )
                return AgentIntent(assistant_text=f"answer:{user_text}")

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        _InterruptiblePlanner.calls = []
        _InterruptiblePlanner.slow_turn_started = threading.Event()
        with patch("cli.agent_cli.runtime.build_planner", side_effect=lambda *args, **kwargs: _InterruptiblePlanner()):
            spawned = runtime.spawn_agent_result(task="slow turn", role="subagent", async_mode=True)
            agent_id = spawned.tool_events[0].payload["agent_id"]

            self.assertTrue(_InterruptiblePlanner.slow_turn_started.wait(timeout=3))
            queued = runtime.send_input_result(agent_id, message="fast turn", interrupt=True)
            self.assertTrue(queued.tool_events[0].payload["interrupt_requested"])

            completed = runtime.wait_agent_result(agent_id, timeout_ms=6000)
            self.assertEqual(completed.tool_events[0].payload["status"], "completed")
            self.assertEqual(completed.assistant_text, "answer:fast turn")

        session = runtime._delegated_agents[agent_id]
        self.assertEqual(session.turn_count, 1)
        self.assertEqual(_InterruptiblePlanner.calls, ["slow turn", "fast turn"])
