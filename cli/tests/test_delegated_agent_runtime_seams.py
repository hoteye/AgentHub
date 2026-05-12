from __future__ import annotations

import inspect
import json
import threading
import unittest
from types import SimpleNamespace

from cli.agent_cli import builtin_agent_profiles_runtime  # noqa: E402
from cli.agent_cli.models import CommandExecutionResult, ToolEvent  # noqa: E402
from cli.agent_cli.runtime_services import (
    delegated_agent_adoption_runtime,  # noqa: E402
    delegated_agent_event_forwarding_runtime,  # noqa: E402
    delegated_agent_input_runtime,  # noqa: E402
    delegated_agent_session_operations_runtime,  # noqa: E402
    delegated_agent_session_runtime,  # noqa: E402
    delegated_agent_spawn_runtime,  # noqa: E402
    delegated_agent_turn_runtime_helpers,  # noqa: E402
)


class DelegatedAgentRuntimeSeamTests(unittest.TestCase):
    def test_delegated_queue_item_runtime_preserves_input_items(self):
        payload = delegated_agent_session_runtime.delegated_queue_item(
            "continue child",
            interrupt=True,
            step_id="step_1",
            input_items=[{"type": "text", "text": "follow up"}],
        )

        self.assertEqual(
            payload,
            {
                "message": "continue child",
                "interrupt": True,
                "step_id": "step_1",
                "input_items": [{"type": "text", "text": "follow up"}],
            },
        )

    def test_delegated_plan_kwargs_include_turn_event_callback_for_streaming_providers(self):
        session = SimpleNamespace(
            agent_id="agent_stream",
            seed_history=[{"role": "user", "content": "seed"}],
            replay_history=[{"role": "assistant", "content": "replay"}],
            seed_input_items=[{"type": "message", "role": "user", "content": "seed"}],
            replay_input_items=[{"type": "message", "role": "assistant", "content": "replay"}],
            turn_count=2,
        )

        class _Planner:
            @staticmethod
            def plan(
                _text,
                *,
                history,
                tool_executor,
                attachments,
                input_items,
                prompt_cache_key,
                subagent_type,
                turn_event_callback,
            ):
                del (
                    _text,
                    history,
                    tool_executor,
                    attachments,
                    input_items,
                    prompt_cache_key,
                    subagent_type,
                    turn_event_callback,
                )
                return None

        class _Runtime:
            thread_id = "thread_main"
            _structured_tool_executor = object()

            @staticmethod
            def _filter_handler_kwargs(handler, kwargs):
                accepted = set(inspect.signature(handler).parameters)
                return {key: value for key, value in kwargs.items() if key in accepted}

        plan_kwargs = delegated_agent_turn_runtime_helpers.delegated_plan_kwargs_impl(
            _Runtime,
            _Planner,
            session=session,
        )

        self.assertEqual(plan_kwargs["history"], [])
        self.assertEqual(plan_kwargs["prompt_cache_key"], "thread_main:delegate:agent_stream:3")
        self.assertTrue(callable(plan_kwargs["turn_event_callback"]))
        self.assertIsNone(plan_kwargs["turn_event_callback"]({"type": "item.started"}))

    def test_delegated_sync_spawn_plan_kwargs_include_turn_event_callback_for_streaming_providers(
        self,
    ):
        class _Planner:
            @staticmethod
            def plan(
                _text,
                *,
                history,
                tool_executor,
                attachments,
                input_items,
                prompt_cache_key,
                subagent_type,
                turn_event_callback,
            ):
                del (
                    _text,
                    history,
                    tool_executor,
                    attachments,
                    input_items,
                    prompt_cache_key,
                    subagent_type,
                    turn_event_callback,
                )
                return None

        class _Runtime:
            thread_id = "thread_main"
            _structured_tool_executor = object()

            @staticmethod
            def _delegated_planner_input_items():
                return [{"type": "message", "role": "user", "content": "seed"}]

            @staticmethod
            def _planner_history():
                return [{"role": "user", "content": "seed"}]

            @staticmethod
            def _planner_history_with_context_updates(*, planner_history):
                return list(planner_history or [])

            @staticmethod
            def _filter_handler_kwargs(handler, kwargs):
                accepted = set(inspect.signature(handler).parameters)
                return {key: value for key, value in kwargs.items() if key in accepted}

        plan_kwargs = delegated_agent_spawn_runtime.delegated_sync_plan_kwargs(
            _Runtime,
            _Planner,
            role="subagent",
            input_items=[{"type": "text", "text": "ping"}],
            fork_context=False,
        )

        self.assertEqual(plan_kwargs["history"], [])
        self.assertEqual(plan_kwargs["prompt_cache_key"], "thread_main:delegate:subagent")
        self.assertEqual(plan_kwargs["input_items"], [{"type": "text", "text": "ping"}])
        self.assertTrue(callable(plan_kwargs["turn_event_callback"]))
        self.assertIsNone(plan_kwargs["turn_event_callback"]({"type": "item.started"}))

    def test_delegated_sync_spawn_plan_kwargs_forwards_child_progress_events(self):
        emitted: list[dict[str, object]] = []

        class _Planner:
            @staticmethod
            def plan(
                _text,
                *,
                history,
                tool_executor,
                attachments,
                input_items,
                prompt_cache_key,
                subagent_type,
                turn_event_callback,
            ):
                del (
                    _text,
                    history,
                    tool_executor,
                    attachments,
                    input_items,
                    prompt_cache_key,
                    subagent_type,
                    turn_event_callback,
                )
                return None

        class _Runtime:
            thread_id = "thread_main"
            _structured_tool_executor = object()

            @staticmethod
            def _delegated_planner_input_items():
                return []

            @staticmethod
            def _planner_history():
                return []

            @staticmethod
            def _planner_history_with_context_updates(*, planner_history):
                return list(planner_history or [])

            @staticmethod
            def _filter_handler_kwargs(handler, kwargs):
                accepted = set(inspect.signature(handler).parameters)
                return {key: value for key, value in kwargs.items() if key in accepted}

            @staticmethod
            def _emit_turn_event(event):
                emitted.append(dict(event))

        plan_kwargs = delegated_agent_spawn_runtime.delegated_sync_plan_kwargs(
            _Runtime,
            _Planner,
            role="subagent",
            task_text="inspect project",
            description="Quick codebase overview",
        )

        callback = plan_kwargs["turn_event_callback"]
        self.assertTrue(callable(callback))
        self.assertEqual(emitted[0]["type"], "system")
        self.assertEqual(emitted[0]["subtype"], "task_started")
        self.assertEqual(emitted[0]["description"], "Quick codebase overview")
        task_id = str(emitted[0]["task_id"])

        callback({"type": "turn.started"})
        callback(
            {
                "type": "item.started",
                "item": {
                    "id": "item_0",
                    "type": "command_execution",
                    "command": "ls -la",
                    "status": "in_progress",
                },
            }
        )

        self.assertEqual([event["type"] for event in emitted], ["system", "system", "item.started"])
        self.assertEqual(emitted[1]["subtype"], "task_progress")
        self.assertEqual(emitted[1]["description"], "Running ls -la")
        forwarded_item = emitted[2]["item"]
        self.assertEqual(forwarded_item["id"], f"{task_id}:item_0")
        self.assertEqual(forwarded_item["delegated_agent"]["task_id"], task_id)

    def test_delegated_child_event_forwarder_disambiguates_reused_item_ids(self):
        emitted: list[dict[str, object]] = []
        runtime = SimpleNamespace(_emit_turn_event=lambda event: emitted.append(dict(event)))
        callback = delegated_agent_event_forwarding_runtime.delegated_child_turn_event_callback(
            runtime,
            task_id="delegate_test",
            task_text="inspect",
            role="subagent",
            subagent_type="Explore",
        )

        callback(
            {
                "type": "item.started",
                "item": {
                    "id": "item_8",
                    "type": "command_execution",
                    "command": "ls providers",
                },
            }
        )
        callback(
            {
                "type": "item.started",
                "item": {
                    "id": "item_8",
                    "type": "command_execution",
                    "command": "ls plugins",
                },
            }
        )

        item_ids = [event["item"]["id"] for event in emitted if event.get("type") == "item.started"]
        self.assertEqual(item_ids, ["delegate_test:item_8", "delegate_test:item_8:2"])

    def test_delegated_child_event_forwarder_keeps_completed_id_for_enriched_arguments(self):
        emitted: list[dict[str, object]] = []
        runtime = SimpleNamespace(_emit_turn_event=lambda event: emitted.append(dict(event)))
        callback = delegated_agent_event_forwarding_runtime.delegated_child_turn_event_callback(
            runtime,
            task_id="delegate_test",
            task_text="inspect",
            role="subagent",
            subagent_type="Explore",
        )

        callback(
            {
                "type": "item.started",
                "item": {
                    "id": "item_2",
                    "type": "mcp_tool_call",
                    "tool": "glob_files",
                    "arguments": {"pattern": "**/*.md", "path": "/repo"},
                },
            }
        )
        callback(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_2",
                    "type": "mcp_tool_call",
                    "tool": "glob_files",
                    "arguments": {"pattern": "**/*.md", "path": "/repo", "limit": 100},
                    "status": "completed",
                },
            }
        )

        item_ids = [
            event["item"]["id"]
            for event in emitted
            if event.get("type") in {"item.started", "item.completed"}
        ]
        self.assertEqual(item_ids, ["delegate_test:item_2", "delegate_test:item_2"])

    def test_delegated_sync_spawn_plan_kwargs_apply_explore_profile(self):
        class _Planner:
            @staticmethod
            def plan(
                _text,
                *,
                history,
                tool_executor,
                attachments,
                input_items,
                prompt_cache_key,
                subagent_type,
                turn_event_callback,
            ):
                del (
                    _text,
                    history,
                    tool_executor,
                    attachments,
                    input_items,
                    prompt_cache_key,
                    subagent_type,
                    turn_event_callback,
                )
                return None

        class _Runtime:
            thread_id = "thread_main"
            _structured_tool_executor = object()

            @staticmethod
            def _delegated_planner_input_items():
                return [{"type": "message", "role": "user", "content": "seed"}]

            @staticmethod
            def _planner_history():
                return [{"role": "user", "content": "seed"}]

            @staticmethod
            def _environment_context_turn_update():
                return (
                    [
                        {
                            "role": "user",
                            "content": "<environment_context>\n  <cwd>/repo</cwd>\n</environment_context>",
                        }
                    ],
                    {},
                )

            @staticmethod
            def _planner_message_history_input_items(history):
                return [
                    {
                        "type": "message",
                        "role": item["role"],
                        "content": item["content"],
                    }
                    for item in history
                ]

            @staticmethod
            def _filter_handler_kwargs(handler, kwargs):
                accepted = set(inspect.signature(handler).parameters)
                return {key: value for key, value in kwargs.items() if key in accepted}

        plan_kwargs = delegated_agent_spawn_runtime.delegated_sync_plan_kwargs(
            _Runtime,
            _Planner,
            role="subagent",
            input_items=[{"type": "text", "text": "ping"}],
            subagent_type="Explore",
        )

        self.assertEqual(plan_kwargs["history"], [])
        self.assertEqual(plan_kwargs["subagent_type"], "Explore")
        self.assertEqual(plan_kwargs["input_items"][0]["role"], "system")
        self.assertIn("READ-ONLY", plan_kwargs["input_items"][0]["content"][0]["text"])
        self.assertIn("<environment_context>", plan_kwargs["input_items"][1]["content"])
        self.assertEqual(plan_kwargs["input_items"][-1], {"type": "text", "text": "ping"})
        self.assertNotIn(
            {"type": "message", "role": "user", "content": "seed"},
            plan_kwargs["input_items"],
        )
        denial = plan_kwargs["tool_executor"].run_structured("/apply_patch '*** Begin Patch'")
        self.assertFalse(denial.tool_events[0].ok)
        self.assertEqual(denial.tool_events[0].payload["reason_code"], "explore_read_only_denied")

    def test_wait_agent_result_marks_ready_result_adopted(self):
        session = SimpleNamespace(
            agent_id="agent_1",
            status="completed",
            terminal_reason="",
            queued_inputs=[],
            adopted=False,
            adopted_at="",
            updated_at="",
            current_step_id="step_3",
            condition=threading.Condition(),
        )
        payload = {"status": "completed", "adopted": False}
        checkpoints: list[dict[str, str]] = []
        background_syncs: list[str] = []

        class _Runtime:
            @staticmethod
            def _delegated_session(agent_id):
                self.assertEqual(agent_id, "agent_1")
                return session

            @staticmethod
            def _delegated_result_ready(_session):
                return True

            @staticmethod
            def _delegated_result_adoptable(_session):
                return True

            @staticmethod
            def _mark_delegated_result_adopted(_session):
                delegated_agent_adoption_runtime.mark_delegated_result_adopted(
                    _Runtime,
                    _session,
                    now_iso_fn=lambda: "2026-04-05T00:00:00+00:00",
                )

            @staticmethod
            def _delegated_agent_payload(_session):
                return dict(payload, adopted=_session.adopted, adopted_at=_session.adopted_at)

            @staticmethod
            def _sync_delegated_background_task(_session):
                background_syncs.append(_session.agent_id)

            @staticmethod
            def _delegated_agent_summary_text(_session):
                return "delegated summary"

            @staticmethod
            def _record_delegated_checkpoint(_session, **kwargs):
                checkpoints.append(dict(kwargs))

        result = delegated_agent_adoption_runtime.wait_agent_result(
            _Runtime,
            "agent_1",
            timeout_ms=10,
        )

        self.assertTrue(session.adopted)
        self.assertEqual(session.adopted_at, "2026-04-05T00:00:00+00:00")
        self.assertEqual(result.tool_events[0].payload["wait_decision"], "blocking_join")
        self.assertTrue(result.tool_events[0].payload["adopted"])
        self.assertEqual(len(checkpoints), 1)
        self.assertEqual(checkpoints[0]["kind"], "result_adopted")
        self.assertEqual(background_syncs, ["agent_1"])

    def test_wait_agent_result_does_not_re_adopt_already_adopted_result(self):
        session = SimpleNamespace(
            agent_id="agent_1",
            status="completed",
            terminal_reason="completed",
            queued_inputs=[],
            adopted=True,
            adopted_at="2026-04-05T00:00:00+00:00",
            updated_at="2026-04-05T00:00:00+00:00",
            current_step_id="step_3",
            condition=threading.Condition(),
        )
        payload = {"status": "completed", "adopted": True}
        checkpoints: list[dict[str, str]] = []
        background_syncs: list[str] = []

        class _Runtime:
            @staticmethod
            def _delegated_session(agent_id):
                self.assertEqual(agent_id, "agent_1")
                return session

            @staticmethod
            def _delegated_result_ready(_session):
                return True

            @staticmethod
            def _delegated_result_adoptable(_session):
                return True

            @staticmethod
            def _mark_delegated_result_adopted(_session):
                delegated_agent_adoption_runtime.mark_delegated_result_adopted(
                    _Runtime,
                    _session,
                    now_iso_fn=lambda: "2026-04-06T00:00:00+00:00",
                )

            @staticmethod
            def _delegated_agent_payload(_session):
                return dict(payload, adopted=_session.adopted, adopted_at=_session.adopted_at)

            @staticmethod
            def _sync_delegated_background_task(_session):
                background_syncs.append(_session.agent_id)

            @staticmethod
            def _delegated_agent_summary_text(_session):
                return "delegated summary"

            @staticmethod
            def _record_delegated_checkpoint(_session, **kwargs):
                checkpoints.append(dict(kwargs))

        result = delegated_agent_adoption_runtime.wait_agent_result(
            _Runtime,
            "agent_1",
            timeout_ms=10,
        )

        self.assertTrue(session.adopted)
        self.assertEqual(session.adopted_at, "2026-04-05T00:00:00+00:00")
        self.assertEqual(result.tool_events[0].payload["adopted_at"], "2026-04-05T00:00:00+00:00")
        self.assertEqual(checkpoints, [])
        self.assertEqual(background_syncs, ["agent_1"])

    def test_enqueue_delegated_input_interrupt_reorders_queue_and_requests_cancel(self):
        session = SimpleNamespace(
            agent_id="agent_2",
            queued_inputs=[{"message": "older", "interrupt": False, "step_id": "step_old"}],
            status="running",
            active_input={"message": "in flight", "interrupt": False, "step_id": "step_active"},
            cancel_event=threading.Event(),
            scheduler_reason="scheduled",
            adopted=True,
            adopted_at="yesterday",
            terminal_reason="completed",
            updated_at="",
        )
        refreshed: list[str] = []

        class _Runtime:
            @staticmethod
            def _queue_delegated_step(_session, *, user_text, source):
                self.assertIs(_session, session)
                self.assertEqual(user_text, "newest")
                self.assertEqual(source, "interrupt_input")
                return "step_new"

            @staticmethod
            def _delegated_queue_item(message, *, interrupt=False, step_id="", input_items=None):
                del input_items
                return {
                    "message": message,
                    "interrupt": interrupt,
                    "step_id": step_id,
                }

            @staticmethod
            def _refresh_delegated_current_step_id(_session):
                refreshed.append(_session.agent_id)

        queued = delegated_agent_input_runtime.enqueue_delegated_input(
            _Runtime,
            session,
            message_text="newest",
            interrupt=True,
            input_items=None,
            now_iso_fn=lambda: "2026-04-05T00:00:00+00:00",
        )

        self.assertEqual(queued["step_id"], "step_new")
        self.assertEqual(queued["pending_count"], 3)
        self.assertEqual(session.queued_inputs[0]["message"], "newest")
        self.assertEqual(session.queued_inputs[1]["message"], "older")
        self.assertTrue(session.cancel_event.is_set())
        self.assertEqual(session.scheduler_reason, "")
        self.assertFalse(session.adopted)
        self.assertEqual(session.adopted_at, "")
        self.assertEqual(session.terminal_reason, "")
        self.assertEqual(session.updated_at, "2026-04-05T00:00:00+00:00")
        self.assertEqual(refreshed, ["agent_2"])

    def test_send_input_result_codex_style_returns_submission_id_output(self):
        session = SimpleNamespace(
            agent_id="agent_codex_send",
            queued_inputs=[],
            status="idle",
            active_input=None,
            cancel_event=threading.Event(),
            scheduler_reason="",
            adopted=False,
            adopted_at="",
            terminal_reason="",
            updated_at="",
            close_requested=False,
            closed=False,
            condition=threading.Condition(),
        )
        started: list[str] = []
        synced: list[str] = []

        class _Runtime:
            @staticmethod
            def _delegated_session(agent_id):
                self.assertEqual(agent_id, "agent_codex_send")
                return session

            @staticmethod
            def _queue_delegated_step(_session, *, user_text, source):
                self.assertIs(_session, session)
                self.assertEqual(user_text, "continue")
                self.assertEqual(source, "followup_input")
                return "step_submit_1"

            @staticmethod
            def _delegated_queue_item(message, *, interrupt=False, step_id="", input_items=None):
                return {
                    "message": message,
                    "interrupt": interrupt,
                    "step_id": step_id,
                    "input_items": list(input_items or []),
                }

            @staticmethod
            def _refresh_delegated_current_step_id(_session):
                del _session

            @staticmethod
            def _start_delegated_agent_worker(_session):
                started.append(_session.agent_id)

            @staticmethod
            def _notify_delegated_scheduler():
                started.append("scheduler")

            @staticmethod
            def _sync_delegated_background_task(_session):
                synced.append(_session.agent_id)

            @staticmethod
            def _delegated_agent_payload(_session):
                return {
                    "agent_id": _session.agent_id,
                    "status": _session.status,
                }

        result = delegated_agent_input_runtime.send_input_result(
            _Runtime,
            "agent_codex_send",
            message="continue",
            codex_style=True,
            now_iso_fn=lambda: "2026-04-05T00:00:00+00:00",
        )

        payload = result.tool_events[0].payload
        self.assertEqual(
            json.loads(str(payload["function_call_output"])),
            {"submission_id": "step_submit_1"},
        )
        self.assertTrue(payload["function_call_output_model_visible"])
        self.assertEqual(result.item_events, [])
        self.assertEqual(started, ["agent_codex_send", "scheduler"])
        self.assertEqual(synced, ["agent_codex_send"])

    def test_spawn_agent_result_codex_collab_message_payload_forces_async_and_thin_output(self):
        session = SimpleNamespace(agent_id="agent_spawned")
        created: list[dict[str, object]] = []
        synced: list[str] = []
        runtime = SimpleNamespace(
            agent=SimpleNamespace(
                resolve_delegate_execution=lambda *args, **kwargs: SimpleNamespace(
                    config=object(),
                    timeout=30,
                    source="test",
                )
            ),
            _sync_delegated_background_task=lambda _session: synced.append(_session.agent_id),
            _delegated_agent_payload=lambda _session: {
                "agent_id": _session.agent_id,
                "status": "queued",
            },
        )

        def _create_session(*args, **kwargs):
            del args
            created.append(dict(kwargs))
            return session

        result = delegated_agent_session_operations_runtime.spawn_agent_result(
            runtime,
            session_class=object,
            task="Reply with exactly ONE and nothing else.",
            role="subagent",
            codex_collab_payload=True,
            infer_spawn_agent_metadata_fn=lambda payload, async_mode=None, role=None: {},
            resolve_spawn_agent_async_mode_fn=lambda payload, async_mode=None, role=None: bool(
                payload.get("codex_collab_payload")
            ),
            resolved_delegation_metadata_fn=lambda metadata, role, effective_async_mode: dict(
                metadata
            ),
            create_delegated_agent_session_fn=_create_session,
            now_iso_fn=lambda: "2026-04-05T00:00:00+00:00",
            tool_event_factory=ToolEvent,
            command_result_factory=CommandExecutionResult,
            generic_tool_call_item_events_fn=lambda **kwargs: [],
        )

        payload = result.tool_events[0].payload
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["task_text"], "Reply with exactly ONE and nothing else.")
        self.assertEqual(
            json.loads(str(payload["function_call_output"])),
            {"agent_id": "agent_spawned", "nickname": None},
        )
        self.assertTrue(payload["function_call_output_model_visible"])
        self.assertEqual(result.item_events, [])
        self.assertEqual(synced, ["agent_spawned"])

    def test_spawn_agent_result_explore_profile_defaults_to_haiku_model(self):
        session = SimpleNamespace(agent_id="agent_explore")
        resolve_calls: list[dict[str, object]] = []
        created: list[dict[str, object]] = []

        def _resolve_delegate_execution(role, **kwargs):
            resolve_calls.append({"role": role, **kwargs})
            return SimpleNamespace(config=object(), timeout=30, source="test")

        runtime = SimpleNamespace(
            agent=SimpleNamespace(resolve_delegate_execution=_resolve_delegate_execution),
            _sync_delegated_background_task=lambda _session: None,
            _delegated_agent_payload=lambda _session: {
                "agent_id": _session.agent_id,
                "status": "queued",
            },
        )

        def _create_session(*args, **kwargs):
            del args
            created.append(dict(kwargs))
            return session

        delegated_agent_session_operations_runtime.spawn_agent_result(
            runtime,
            session_class=object,
            task="Explore project capabilities",
            role="subagent",
            subagent_type="Explore",
            async_mode=True,
            infer_spawn_agent_metadata_fn=lambda payload, async_mode=None, role=None: {
                "subagent_type": payload.get("subagent_type")
            },
            resolve_spawn_agent_async_mode_fn=lambda payload, async_mode=None, role=None: bool(
                async_mode
            ),
            resolved_delegation_metadata_fn=lambda metadata, role, effective_async_mode: dict(
                metadata
            ),
            create_delegated_agent_session_fn=_create_session,
            now_iso_fn=lambda: "2026-04-05T00:00:00+00:00",
            tool_event_factory=ToolEvent,
            command_result_factory=CommandExecutionResult,
            generic_tool_call_item_events_fn=lambda **kwargs: [],
        )

        self.assertEqual(resolve_calls[0]["model"], "claude_haiku_45")
        self.assertEqual(created[0]["metadata"]["subagent_type"], "Explore")

    def test_explore_read_only_shell_allows_claude_style_read_pipelines(self):
        allowed_commands = (
            "/exec_command 'pwd && ls -la /tmp' --shell bash",
            "/exec_command 'find /tmp -name \"*.py\" | head -20' --shell bash",
            "/exec_command 'grep -r \"def.*tool\\|class.*Tool\" /tmp | head -10' --shell bash",
            "/exec_command 'ls -la /tmp/missing 2>/dev/null | head -40' --shell bash",
        )
        for command in allowed_commands:
            self.assertEqual(
                builtin_agent_profiles_runtime.read_only_profile_denial(command),
                "",
                command,
            )

        self.assertIn(
            "redirection",
            builtin_agent_profiles_runtime.read_only_profile_denial(
                "/exec_command 'cat README.md > /tmp/out' --shell bash"
            ),
        )
        self.assertIn(
            "rm is not allowed",
            builtin_agent_profiles_runtime.read_only_profile_denial(
                "/exec_command 'find /tmp -maxdepth 1 | rm -rf /tmp/x' --shell bash"
            ),
        )

    def test_resume_and_close_result_codex_style_return_codex_status_wire_shapes(self):
        resume_session = SimpleNamespace(
            agent_id="agent_resume",
            queued_inputs=[{"message": "resume me"}],
            closed=True,
            close_requested=True,
            cancel_event=threading.Event(),
            scheduler_reason="",
            resume_source="",
            terminal_reason="close_requested",
            status="closed",
            current_step_id="step_resume",
            updated_at="",
            assistant_text="",
            condition=threading.Condition(),
        )
        close_session = SimpleNamespace(
            agent_id="agent_close",
            queued_inputs=[],
            closed=False,
            close_requested=False,
            cancel_event=threading.Event(),
            scheduler_reason="",
            resume_source="",
            terminal_reason="",
            status="running",
            current_step_id="step_close",
            updated_at="",
            assistant_text="working",
            active_input={"message": "in flight"},
            worker=SimpleNamespace(is_alive=lambda: True),
            condition=threading.Condition(),
        )
        checkpoints: list[dict[str, str]] = []
        started: list[str] = []
        synced: list[str] = []
        notified: list[str] = []

        class _Runtime:
            @staticmethod
            def _delegated_session(agent_id):
                if agent_id == "agent_resume":
                    return resume_session
                self.assertEqual(agent_id, "agent_close")
                return close_session

            @staticmethod
            def _refresh_delegated_current_step_id(_session):
                del _session

            @staticmethod
            def _record_delegated_checkpoint(_session, **kwargs):
                checkpoints.append(dict(kwargs))

            @staticmethod
            def _delegated_agent_payload(_session):
                return {"status": _session.status}

            @staticmethod
            def _start_delegated_agent_worker(_session):
                started.append(_session.agent_id)

            @staticmethod
            def _notify_delegated_scheduler():
                notified.append("scheduler")

            @staticmethod
            def _sync_delegated_background_task(_session):
                synced.append(_session.agent_id)

        resume_result = delegated_agent_session_operations_runtime.resume_agent_result(
            _Runtime,
            "agent_resume",
            codex_style=True,
            now_iso_fn=lambda: "2026-04-06T00:00:00+00:00",
            sync_delegated_run_record_fn=lambda *args, **kwargs: None,
            tool_event_factory=ToolEvent,
            command_result_factory=CommandExecutionResult,
            generic_tool_call_item_events_fn=lambda **kwargs: [],
        )
        close_result = delegated_agent_session_operations_runtime.close_agent_result(
            _Runtime,
            "agent_close",
            codex_style=True,
            now_iso_fn=lambda: "2026-04-06T00:00:00+00:00",
            sync_delegated_run_record_fn=lambda *args, **kwargs: None,
            tool_event_factory=ToolEvent,
            command_result_factory=CommandExecutionResult,
            generic_tool_call_item_events_fn=lambda **kwargs: [],
        )

        self.assertEqual(
            json.loads(str(resume_result.tool_events[0].payload["function_call_output"])),
            {"status": "pending_init"},
        )
        self.assertEqual(
            json.loads(str(close_result.tool_events[0].payload["function_call_output"])),
            {"status": "running"},
        )
        self.assertEqual(started, ["agent_resume"])
        self.assertEqual(synced, ["agent_resume", "agent_close"])
        self.assertEqual(notified, ["scheduler", "scheduler"])
        self.assertEqual(checkpoints[0]["kind"], "session_resumed")
        self.assertEqual(checkpoints[1]["kind"], "session_close_requested")
