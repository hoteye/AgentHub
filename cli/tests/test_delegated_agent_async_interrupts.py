import json
import shlex
import sys
import threading
import time
import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.models import ActivityEvent, AgentIntent
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_policy import RuntimePolicy


class _DelegateAgent:
    host_platform = current_host_platform()

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
        assert role_name == "subagent"
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


class DelegatedAgentAsyncInterruptsTest(unittest.TestCase):
    def test_interrupt_preempts_active_turn_without_replaying_partial_history(self):
        class _InterruptibleDelegatedPlanner:
            calls: list[dict] = []
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
                del attachments
                self.__class__.calls.append(
                    {
                        "user_text": user_text,
                        "history": list(history or []),
                        "input_items": list(input_items or []),
                        "prompt_cache_key": prompt_cache_key,
                    }
                )
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
        _InterruptibleDelegatedPlanner.calls = []
        _InterruptibleDelegatedPlanner.slow_turn_started = threading.Event()
        with patch("cli.agent_cli.runtime.build_planner", side_effect=lambda *args, **kwargs: _InterruptibleDelegatedPlanner()):
            spawned = runtime.spawn_agent_result(task="slow turn", role="subagent", async_mode=True)
            agent_id = spawned.tool_events[0].payload["agent_id"]

            self.assertTrue(_InterruptibleDelegatedPlanner.slow_turn_started.wait(timeout=3))
            queued = runtime.send_input_result(agent_id, message="fast turn", interrupt=True)
            self.assertTrue(queued.tool_events[0].payload["interrupt_requested"])
            self.assertEqual(queued.tool_events[0].payload["resume_source"], "send_input")
            self.assertEqual(
                queued.tool_events[0].payload["child_identity"],
                {
                    "agent_id": agent_id,
                    "run_id": f"delegated:{agent_id}",
                    "parent_run_id": "",
                    "thread_id": "",
                },
            )

            completed = runtime.wait_agent_result(agent_id, timeout_ms=6000)
            self.assertEqual(completed.tool_events[0].payload["status"], "completed")
            self.assertEqual(completed.assistant_text, "answer:fast turn")
            self.assertEqual(completed.tool_events[0].payload["resume_source"], "send_input")
            self.assertEqual(
                completed.tool_events[0].payload["child_identity"],
                {
                    "agent_id": agent_id,
                    "run_id": f"delegated:{agent_id}",
                    "parent_run_id": "",
                    "thread_id": "",
                },
            )

            session = runtime._delegated_agents[agent_id]
            self.assertEqual(session.turn_count, 1)
            self.assertEqual([item["user_text"] for item in _InterruptibleDelegatedPlanner.calls], ["slow turn", "fast turn"])
            second_call = _InterruptibleDelegatedPlanner.calls[1]
            self.assertEqual(second_call["history"], [])
            self.assertFalse(any("slow turn" in json.dumps(item, ensure_ascii=False) for item in second_call["input_items"]))
            self.assertFalse(
                any("Conversation interrupted" in json.dumps(item, ensure_ascii=False) for item in second_call["input_items"])
            )

    def test_close_interrupts_active_turn(self):
        class _CloseInterruptPlanner:
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
                del user_text, history, attachments, input_items, prompt_cache_key
                self.__class__.slow_turn_started.set()
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
        _CloseInterruptPlanner.slow_turn_started = threading.Event()
        with patch("cli.agent_cli.runtime.build_planner", side_effect=lambda *args, **kwargs: _CloseInterruptPlanner()):
            spawned = runtime.spawn_agent_result(task="slow turn", role="subagent", async_mode=True)
            agent_id = spawned.tool_events[0].payload["agent_id"]

            self.assertTrue(_CloseInterruptPlanner.slow_turn_started.wait(timeout=3))
            close_result = runtime.close_agent_result(agent_id)
            self.assertIn(close_result.tool_events[0].payload["status"], {"closing", "closed"})
            self.assertEqual(close_result.tool_events[0].payload["terminal_state"], "closed_by_request")
            self.assertEqual(close_result.tool_events[0].payload["terminal_reason"], "close_requested")

            waited = runtime.wait_agent_result(agent_id, timeout_ms=6000)
            self.assertEqual(waited.tool_events[0].payload["status"], "closed")
            self.assertEqual(waited.tool_events[0].payload["pending_input_count"], 0)
            self.assertEqual(waited.tool_events[0].payload["terminal_state"], "closed_by_request")
            self.assertEqual(waited.tool_events[0].payload["terminal_reason"], "close_requested")
            self.assertEqual(waited.tool_events[0].payload["result_contract"]["status"], "closed")
            self.assertEqual(waited.tool_events[0].payload["result_contract"]["artifact"]["kind"], "empty")
            self.assertEqual(waited.tool_events[0].payload["result_contract"]["confidence"], "low")

            session = runtime._delegated_agents[agent_id]
            self.assertTrue(session.closed)
            self.assertEqual(session.status, "closed")
            self.assertEqual(session.turn_count, 0)

    def test_background_shell_activity_isolated_from_foreground_callback(self):
        class _ShellDelegatedPlanner:
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
                command = (
                    f"{shlex.quote(sys.executable)} -u -c "
                    + shlex.quote("print('delegated-background-output')")
                )
                result = tool_executor.run_structured(
                    f"/exec_command --cmd {shlex.quote(command)} --yield-time-ms 250"
                )
                return AgentIntent(
                    assistant_text=f"answer:{user_text}",
                    tool_events=list(result.tool_events or []),
                    turn_events=list(result.turn_events or []),
                )

        activity_events: list[ActivityEvent] = []
        with TemporaryDirectory() as temp_dir:
            runtime = AgentCliRuntime(
                agent=_DelegateAgent(),
                activity_callback=activity_events.append,
                runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
            )
            runtime.set_cwd(temp_dir)
            foreground_command = (
                f"{shlex.quote(sys.executable)} -u -c "
                + shlex.quote("print('foreground-visible-output')")
            )
            runtime._run_command_text_result(
                f"/exec_command --cmd {shlex.quote(foreground_command)} --yield-time-ms 250"
            )
            self.assertTrue(any(event.code == "command.output" for event in activity_events))

            with patch("cli.agent_cli.runtime.build_planner", side_effect=lambda *args, **kwargs: _ShellDelegatedPlanner()):
                spawned = runtime.spawn_agent_result(
                    task="background shell task",
                    role="subagent",
                    async_mode=True,
                    mode="background",
                    wait_required=False,
                    task_shape="long_running",
                )
                after_spawn_activity_count = len(activity_events)
                agent_id = spawned.tool_events[0].payload["agent_id"]

                snapshot = None
                for _ in range(20):
                    snapshot = runtime.wait_agent_result(agent_id, timeout_ms=250, wait_required=False)
                    if snapshot.tool_events[0].payload["status"] == "completed":
                        break
                    time.sleep(0.05)
                assert snapshot is not None
                self.assertEqual(snapshot.tool_events[0].payload["status"], "completed")
                self.assertFalse(snapshot.tool_events[0].payload["adopted"])
                self.assertEqual(len(activity_events), after_spawn_activity_count)

                completed = runtime.wait_agent_result(agent_id, timeout_ms=4000)
                self.assertEqual(completed.tool_events[0].payload["status"], "completed")
                self.assertIn("delegated-background-output", completed.assistant_text)
                self.assertTrue(completed.tool_events[0].payload["adopted"])
                self.assertFalse(any("delegated-background-output" in (event.title or "") for event in activity_events))

            followup_command = (
                f"{shlex.quote(sys.executable)} -u -c "
                + shlex.quote("print('foreground-visible-output-2')")
            )
            runtime._run_command_text_result(
                f"/exec_command --cmd {shlex.quote(followup_command)} --yield-time-ms 250"
            )
            self.assertGreater(len(activity_events), after_spawn_activity_count)
