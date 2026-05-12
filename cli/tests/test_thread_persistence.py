import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.background_tasks import (
    BackgroundTasksConfig,
    HueyConfig,
    build_background_task_adapter,
)
from cli.agent_cli.models import (
    AgentIntent,
    CommandExecutionResult,
    PromptAttachment,
    PromptResponse,
    ReferenceContextItem,
    ResponseInputItem,
    ToolEvent,
    default_response_items,
    prompt_response_turn_events,
)
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_core.thread_fork import (
    fork_source_inputs,
    fork_thread_record,
    resume_payload_preserving_active_thread,
)
from cli.agent_cli.thread_store import ThreadStore
from cli.agent_cli.workspace_context import (
    build_workspace_reference_context_item,
    build_workspace_reference_snapshot,
)
from cli.tests.provider_boundary_test_support import provider_status_path_fields


class _RecordingAgent:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.switch_calls: list[tuple[str, str]] = []
        self.route_override_calls: list[dict[str, dict]] = []
        self.route_overrides: dict[str, dict] = {}
        self.delegate_override_calls: list[dict[str, dict]] = []
        self.delegate_overrides: dict[str, dict] = {}
        self.cwd: Path | None = None

    def provider_status(self):
        return {
            "provider_ready": "true",
            "provider_name": "deepseek",
            "model_key": "deepseek_reasoner",
            "provider_planner": "deepseek_reasoner",
            "provider_model": "deepseek-reasoner",
            "provider_tools": "tool-calls",
            "session_line": "reasoner",
            "provider_label": "deepseek | deepseek-reasoner | tool-calls",
            "provider_base_url": "https://api.deepseek.com",
            "provider_source": "test",
            **provider_status_path_fields(),
            "platform_family": "windows",
            "platform_os": "windows",
            "shell_kind": "powershell",
        }

    def plan(self, text, history=None, *, tool_executor=None, attachments=None, input_items=None):
        self.calls.append(
            {
                "text": text,
                "history": list(history or []),
                "input_items": list(input_items or []),
            }
        )
        return AgentIntent(assistant_text=f"echo: {text}")

    def switch_model(self, model_key):
        self.switch_calls.append(("model", model_key))

    def switch_provider(self, provider_name):
        self.switch_calls.append(("provider", provider_name))

    def switch_provider_line(self, line):
        self.switch_calls.append(("line", line))

    def configure_route_selection(
        self,
        route_name,
        *,
        model=None,
        provider=None,
        reasoning_effort=None,
        timeout=None,
        clear=False,
    ):
        if clear:
            self.route_overrides.pop(str(route_name), None)
            return self.provider_status()
        payload: dict[str, object] = {"source": "session_override"}
        if model is not None:
            payload["model"] = str(model)
        if provider is not None:
            payload["provider"] = str(provider)
        if reasoning_effort is not None:
            payload["reasoning_effort"] = str(reasoning_effort)
        if timeout is not None:
            payload["timeout"] = int(timeout)
        self.route_overrides[str(route_name)] = payload
        return self.provider_status()

    def session_route_overrides(self):
        return {route_name: dict(payload) for route_name, payload in self.route_overrides.items()}

    def set_session_route_overrides(self, overrides):
        self.route_overrides = {
            str(route_name): dict(payload)
            for route_name, payload in dict(overrides or {}).items()
            if isinstance(payload, dict)
        }
        self.route_override_calls.append(self.session_route_overrides())
        return self.session_route_overrides()

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
            return self.provider_status()
        payload: dict[str, object] = {"source": "session_override"}
        if model is not None:
            payload["model"] = str(model)
        if provider is not None:
            payload["provider"] = str(provider)
        if reasoning_effort is not None:
            payload["reasoning_effort"] = str(reasoning_effort)
        if timeout is not None:
            payload["timeout"] = int(timeout)
        self.delegate_overrides[str(role_name)] = payload
        return self.provider_status()

    def session_delegate_overrides(self):
        return {role_name: dict(payload) for role_name, payload in self.delegate_overrides.items()}

    def set_session_delegate_overrides(self, overrides):
        self.delegate_overrides = {
            str(role_name): dict(payload)
            for role_name, payload in dict(overrides or {}).items()
            if isinstance(payload, dict)
        }
        self.delegate_override_calls.append(self.session_delegate_overrides())
        return self.session_delegate_overrides()

    def set_cwd(self, cwd):
        self.cwd = Path(cwd).resolve()
        return self.cwd


class _LegacyHistoryAgent:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def provider_status(self):
        return _RecordingAgent().provider_status()

    def plan(self, text, history=None, *, tool_executor=None, attachments=None):
        self.calls.append(
            {
                "text": text,
                "history": list(history or []),
            }
        )
        return AgentIntent(assistant_text=f"echo: {text}")


class _DelegatingRecordingAgent(_RecordingAgent):
    def resolve_delegate_execution(
        self,
        role_name,
        *,
        model=None,
        provider=None,
        reasoning_effort=None,
        timeout=None,
    ):
        del role_name
        model_key = str(model or "glm_5").strip() or "glm_5"
        normalized_timeout = None
        if timeout not in (None, ""):
            normalized_timeout = int(timeout)
        return SimpleNamespace(
            config=ProviderConfig(
                model="glm-5" if model_key == "glm_5" else model_key,
                api_key="test-key",
                provider_name=str(provider or "glm").strip() or "glm",
                model_key=model_key,
                planner_kind="openai_responses",
                wire_api="responses",
                base_url="https://open.bigmodel.cn/api/paas/v4",
                reasoning_effort=str(reasoning_effort or "medium").strip() or None,
                source="test",
            ),
            timeout=normalized_timeout,
            source="delegation",
        )


class _WorkspaceTools:
    def __init__(self, root: Path) -> None:
        self.PROJECT_ROOT = str(root)

    def set_workspace_root(self, path) -> Path:
        resolved = Path(path).resolve()
        self.PROJECT_ROOT = str(resolved)
        return resolved


class ThreadPersistenceTest(unittest.TestCase):
    @staticmethod
    def _input_items_contain_text(items: list[dict], expected: str) -> bool:
        needle = str(expected or "").strip()
        if not needle:
            return False
        for item in list(items or []):
            if needle in str(item.get("content") or ""):
                return True
            nested = item.get("item")
            if isinstance(nested, dict) and needle in str(nested.get("content") or ""):
                return True
        return False

    @staticmethod
    def _history_contains_text(items: list[dict], expected: str) -> bool:
        needle = str(expected or "").strip()
        if not needle:
            return False
        return any(needle in str(item.get("content") or "") for item in list(items or []))

    @staticmethod
    def _reference_context_inputs(items: list[dict]) -> list[dict]:
        return [
            dict(item.get("item") or {})
            for item in list(items or [])
            if str(item.get("type") or "").strip() == "reference_context_item"
            and isinstance(item.get("item"), dict)
        ]

    @staticmethod
    def _function_call_output_items(items: list[dict]) -> list[dict]:
        return [
            dict(item)
            for item in list(items or [])
            if isinstance(item, dict)
            and str(item.get("type") or "").strip() == "function_call_output"
        ]

    @staticmethod
    def _function_call_items(items: list[dict]) -> list[dict]:
        return [
            dict(item)
            for item in list(items or [])
            if isinstance(item, dict) and str(item.get("type") or "").strip() == "function_call"
        ]

    @staticmethod
    def _input_image_output_items(items: list[dict]) -> list[dict]:
        output_items: list[dict] = []
        for item in ThreadPersistenceTest._function_call_output_items(items):
            output = item.get("output")
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except json.JSONDecodeError:
                    continue
            if isinstance(output, dict):
                output = [output]
            if not isinstance(output, list):
                continue
            normalized = [
                dict(entry)
                for entry in output
                if isinstance(entry, dict) and str(entry.get("type") or "").strip() == "input_image"
            ]
            if normalized:
                output_items.extend(normalized)
        return output_items

    @staticmethod
    def _reasoning_items(items: list[dict]) -> list[dict]:
        return [
            dict(item)
            for item in list(items or [])
            if isinstance(item, dict) and str(item.get("type") or "").strip() == "reasoning"
        ]

    @staticmethod
    def _failed_exec_command_tool_event() -> ToolEvent:
        return ToolEvent(
            name="exec_command",
            ok=False,
            summary="exec_command exited",
            payload={
                "provider_call_id": "call_exec_1",
                "function_call_name": "exec_command",
                "function_call_arguments": {"cmd": "ls /missing"},
                "function_call_output": (
                    "Process exited with code 2\n"
                    "Output:\n"
                    "ls: cannot access '/missing': No such file or directory\n"
                ),
                "stderr": "ls: cannot access '/missing': No such file or directory\n",
                "aggregated_output": "ls: cannot access '/missing': No such file or directory\n",
                "exit_code": 2,
            },
        )

    @staticmethod
    def _successful_exec_command_tool_event() -> ToolEvent:
        return ToolEvent(
            name="exec_command",
            ok=True,
            summary="exec_command completed",
            payload={
                "provider_call_id": "call_exec_ok_1",
                "function_call_name": "exec_command",
                "function_call_arguments": {"cmd": "pwd"},
                "function_call_output": "/repo\n",
                "command": "pwd",
                "stdout": "/repo\n",
                "aggregated_output": "/repo\n",
                "exit_code": 0,
            },
        )

    def test_thread_start_records_runtime_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace-a"
            workspace.mkdir()
            store = ThreadStore(root / "state")
            runtime = AgentCliRuntime(
                agent=_RecordingAgent(), tools=_WorkspaceTools(root), thread_store=store
            )

            runtime.set_cwd(workspace)
            thread = runtime.start_thread(name="cwd thread")

            self.assertEqual(runtime.agent.cwd, workspace.resolve())
            self.assertEqual(thread["cwd"], str(workspace.resolve()))
            listed = store.get_thread(thread["thread_id"])
            self.assertIsNotNone(listed)
            self.assertEqual(listed["cwd"], str(workspace.resolve()))

    def test_start_thread_clears_cached_planner_input_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir) / "state")
            runtime = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)

            runtime._planner_input_items = [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "stale cached prompt"}],
                }
            ]

            runtime.start_thread(name="fresh thread")

            self.assertEqual(runtime._planner_input_items, [])

    def test_start_thread_persists_thread_metadata_snapshot_and_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ThreadStore(root / "state")
            runtime = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            runtime.configure_runtime_policy(
                approval_policy="never",
                sandbox_mode="read-only",
                web_search_mode="disabled",
                network_access_enabled=False,
            )

            thread = runtime.start_thread(name="metadata thread")
            described = runtime.describe_thread(thread, status="idle", turns=[])

            rollout_path = root / "state" / "rollouts" / f"{thread['thread_id']}.jsonl"
            lines = [
                json.loads(line)
                for line in rollout_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            meta = lines[0]

            self.assertEqual(meta["type"], "thread_meta")
            self.assertEqual(meta["path"], str(rollout_path))
            self.assertFalse(meta["ephemeral"])
            self.assertEqual(meta["source"], "agenthub_cli")
            self.assertEqual(meta["cli_version"], "0.1.0")
            self.assertEqual(meta["provider_status"]["provider_name"], "deepseek")
            self.assertEqual(meta["runtime_policy"]["approval_policy"], "never")
            self.assertEqual(meta["runtime_policy"]["sandbox_mode"], "read-only")
            self.assertEqual(meta["runtime_policy"]["web_search_mode"], "disabled")
            self.assertEqual(meta["runtime_policy"]["network_access"], "disabled")
            self.assertFalse(described["ephemeral"])
            self.assertEqual(described["status"], "idle")
            self.assertTrue(Path(described["path"]).is_absolute())
            self.assertEqual(described["metadata"]["provider_status"]["provider_name"], "deepseek")
            self.assertEqual(described["metadata"]["runtime_policy"]["network_access"], "disabled")

    def test_resume_thread_restores_runtime_cwd_and_tool_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace-b"
            workspace.mkdir()
            store = ThreadStore(root / "state")
            thread = store.start_thread(name="cwd restore thread", cwd=str(workspace.resolve()))

            runtime = AgentCliRuntime(
                agent=_RecordingAgent(), tools=_WorkspaceTools(root), thread_store=store
            )
            runtime.resume_thread(thread.thread_id)

            self.assertEqual(runtime.cwd, workspace.resolve())
            self.assertEqual(runtime.agent.cwd, workspace.resolve())
            self.assertEqual(Path(runtime.tools.PROJECT_ROOT), workspace.resolve())

    def test_thread_workspace_context_stays_in_sync_across_start_resume_cwd_and_policy_updates(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace_a = root / "workspace-a"
            workspace_b = root / "workspace-b"
            workspace_a.mkdir()
            workspace_b.mkdir()
            store = ThreadStore(root / "state")

            runtime1 = AgentCliRuntime(
                agent=_RecordingAgent(), tools=_WorkspaceTools(root), thread_store=store
            )
            runtime1.set_cwd(workspace_a)
            created = runtime1.start_thread(name="workspace context sync thread")

            context1 = runtime1.thread_workspace_context
            self.assertIsNotNone(context1)
            self.assertEqual(context1.thread_id, str(created["thread_id"]))
            self.assertEqual(context1.cwd, str(workspace_a.resolve()))
            self.assertEqual(context1.workspace_root, str(workspace_a.resolve()))

            runtime1.configure_runtime_policy(
                approval_policy="never",
                sandbox_mode="read-only",
                web_search_mode="disabled",
                network_access_enabled=False,
            )
            context2 = runtime1.thread_workspace_context
            self.assertIsNotNone(context2)
            self.assertEqual(context2.thread_id, str(created["thread_id"]))
            self.assertEqual(context2.approval_policy, "never")
            self.assertEqual(context2.sandbox_mode, "read-only")
            self.assertFalse(context2.network_access_enabled)
            self.assertEqual(context2.web_search_mode, "disabled")

            runtime1.handle_prompt("sync marker")
            rollout_types = {str(item.get("type") or "").strip() for item in runtime1.rollout_items}
            self.assertNotIn("thread_workspace_context", rollout_types)

            runtime2 = AgentCliRuntime(
                agent=_RecordingAgent(), tools=_WorkspaceTools(root), thread_store=store
            )
            runtime2.resume_thread(str(created["thread_id"]))
            resumed_context = runtime2.thread_workspace_context
            self.assertIsNotNone(resumed_context)
            self.assertEqual(resumed_context.thread_id, str(created["thread_id"]))
            self.assertEqual(resumed_context.cwd, str(workspace_a.resolve()))
            self.assertEqual(resumed_context.approval_policy, "never")
            self.assertEqual(resumed_context.sandbox_mode, "read-only")
            self.assertFalse(resumed_context.network_access_enabled)
            self.assertEqual(resumed_context.web_search_mode, "disabled")

            runtime2.set_cwd(workspace_b)
            moved_context = runtime2.thread_workspace_context
            self.assertIsNotNone(moved_context)
            self.assertEqual(moved_context.thread_id, str(created["thread_id"]))
            self.assertEqual(moved_context.cwd, str(workspace_b.resolve()))
            self.assertEqual(moved_context.workspace_root, str(workspace_b.resolve()))

    def test_thread_resume_restores_history_for_future_planning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            agent1 = _RecordingAgent()
            runtime1 = AgentCliRuntime(agent=agent1, thread_store=store)
            thread = runtime1.start_thread(name="demo thread")

            response1 = runtime1.handle_prompt("hello morning")
            self.assertEqual(response1.assistant_text, "echo: hello morning")

            agent2 = _RecordingAgent()
            runtime2 = AgentCliRuntime(agent=agent2, thread_store=store)
            resumed = runtime2.resume_thread(thread["thread_id"])

            self.assertEqual(resumed["thread"]["thread_id"], thread["thread_id"])
            self.assertEqual(
                resumed["history"],
                [
                    {"role": "user", "content": "hello morning"},
                    {"role": "assistant", "content": "echo: hello morning"},
                ],
            )

            runtime2.handle_prompt("hello afternoon")

            self.assertEqual(agent2.calls[0]["text"], "hello afternoon")
            self.assertEqual(agent2.calls[0]["history"], [])
            self.assertTrue(
                self._input_items_contain_text(agent2.calls[0]["input_items"], "hello morning")
            )
            self.assertTrue(
                self._input_items_contain_text(
                    agent2.calls[0]["input_items"], "echo: hello morning"
                )
            )
            self.assertTrue(
                any(
                    "<environment_context>" in str(item.get("content") or "")
                    for item in agent2.calls[0]["input_items"]
                )
            )
            self.assertTrue(
                any(
                    str(item.get("role") or "") == "developer"
                    for item in agent2.calls[0]["input_items"]
                )
            )

    def test_resume_thread_from_path_restores_rollout_after_sqlite_loss(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store1 = ThreadStore(root / "state")
            runtime1 = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store1)
            thread = runtime1.start_thread(name="path sourced thread")

            runtime1.handle_prompt("restore me from rollout path")

            rollout_path = root / "state" / "rollouts" / f"{thread['thread_id']}.jsonl"
            sqlite_path = root / "state" / "threads.sqlite3"
            sqlite_path.unlink()

            store2 = ThreadStore(root / "state")
            resumed = store2.resume_thread_from_path(rollout_path)

            self.assertEqual(resumed["resume_source"], "path")
            self.assertEqual(resumed["thread"]["thread_id"], thread["thread_id"])
            self.assertEqual(resumed["resume_path"], str(rollout_path.resolve()))
            self.assertTrue(
                self._history_contains_text(resumed["history"], "restore me from rollout path")
            )
            self.assertTrue(
                self._input_items_contain_text(
                    resumed["planner_input_items"], "restore me from rollout path"
                )
            )

    def test_resume_thread_from_path_materializes_metadata_for_later_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_dir = root / "state"
            store1 = ThreadStore(state_dir)
            runtime1 = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store1)
            thread = runtime1.start_thread(name="materialize after path resume")
            runtime1.handle_prompt("persist me across sqlite rebuild")

            rollout_path = Path(thread["rollout_path"])
            sqlite_path = state_dir / "threads.sqlite3"
            sqlite_path.unlink()

            store2 = ThreadStore(state_dir)
            runtime2 = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store2)
            resumed = runtime2.resume_thread(path=str(rollout_path))

            self.assertEqual(resumed["thread"]["thread_id"], thread["thread_id"])
            self.assertEqual(store2.get_active_thread_id(), thread["thread_id"])

            store3 = ThreadStore(state_dir)
            listed = store3.list_threads(limit=10)
            self.assertTrue(any(item.get("thread_id") == thread["thread_id"] for item in listed))
            materialized = store3.get_thread(thread["thread_id"])
            self.assertIsNotNone(materialized)
            self.assertEqual(materialized["rollout_path"], str(rollout_path))

            runtime3 = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store3)
            resumed_again = runtime3.resume_thread(thread["thread_id"])
            self.assertEqual(resumed_again["thread"]["thread_id"], thread["thread_id"])
            self.assertTrue(
                self._history_contains_text(
                    resumed_again["history"], "persist me across sqlite rebuild"
                )
            )

    def test_resume_thread_from_history_preserves_structured_seed_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ThreadStore(root / "state")

            resumed = store.resume_thread_from_history(
                [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "seed user prompt"}],
                    },
                    {
                        "type": "reasoning",
                        "summary": [{"type": "summary_text", "text": "seed reasoning"}],
                        "encrypted_content": "enc_seed",
                    },
                    {
                        "type": "function_call",
                        "call_id": "call_seed_1",
                        "name": "exec_command",
                        "arguments": '{"cmd":"pwd"}',
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "call_seed_1",
                        "output": '{"stdout":"/repo"}',
                    },
                ],
                cwd=str(root),
                provider_status=_RecordingAgent().provider_status(),
            )

            planner_input_items = list(resumed["planner_input_items"])
            planner_item_types = [str(item.get("type") or "") for item in planner_input_items]

            self.assertEqual(resumed["resume_source"], "history")
            self.assertEqual(resumed["thread"]["name"], "seed user prompt")
            self.assertEqual(resumed["history"], [{"role": "user", "content": "seed user prompt"}])
            self.assertEqual(
                planner_item_types,
                ["message", "reasoning", "function_call", "function_call_output"],
            )
            self.assertEqual(planner_input_items[1]["encrypted_content"], "enc_seed")
            self.assertEqual(planner_input_items[2]["call_id"], "call_seed_1")
            self.assertEqual(planner_input_items[3]["call_id"], "call_seed_1")

    def test_resume_thread_exposes_planner_history_preferring_structured_turns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="planner history source")
            store.append_rollout_items(
                thread.thread_id,
                [
                    {"type": "response_item", "role": "user", "content": "legacy user"},
                    {"type": "response_item", "role": "assistant", "content": "legacy assistant"},
                ],
            )
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="structured user",
                    assistant_text="structured assistant",
                ),
            )

            resumed = store.resume_thread(thread.thread_id)

            self.assertIn("planner_history", resumed)
            self.assertEqual(
                resumed["planner_history"],
                [
                    {"role": "user", "content": "structured user"},
                    {"role": "assistant", "content": "structured assistant"},
                ],
            )
            self.assertEqual(
                resumed["planner_input_items"],
                [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "structured user"}],
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "phase": "final_answer",
                        "content": [{"type": "output_text", "text": "structured assistant"}],
                    },
                ],
            )

    def test_runtime_resume_prefers_structured_turn_history_for_planner_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="structured preferred")
            store.append_rollout_items(
                thread.thread_id,
                [
                    {"type": "response_item", "role": "user", "content": "legacy user"},
                    {"type": "response_item", "role": "assistant", "content": "legacy assistant"},
                ],
            )
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="structured user",
                    assistant_text="structured assistant",
                ),
            )

            agent = _RecordingAgent()
            runtime = AgentCliRuntime(agent=agent, thread_store=store)
            runtime.resume_thread(thread.thread_id)
            runtime.handle_prompt("follow up")

            self.assertEqual(agent.calls[0]["history"], [])
            self.assertTrue(
                self._input_items_contain_text(agent.calls[0]["input_items"], "structured user")
            )
            self.assertTrue(
                self._input_items_contain_text(
                    agent.calls[0]["input_items"], "structured assistant"
                )
            )
            self.assertFalse(
                self._input_items_contain_text(agent.calls[0]["input_items"], "legacy user")
            )

    def test_runtime_planner_input_items_rebuild_from_history_turns_when_cached_items_are_empty(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="structured items rebuild")
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="structured user",
                    assistant_text="structured assistant",
                ),
            )

            agent = _RecordingAgent()
            runtime = AgentCliRuntime(agent=agent, thread_store=store)
            runtime.resume_thread(thread.thread_id)
            runtime._planner_input_items = []

            runtime.handle_prompt("follow up")

            self.assertEqual(agent.calls[0]["history"], [])
            self.assertTrue(
                self._input_items_contain_text(agent.calls[0]["input_items"], "structured user")
            )
            self.assertTrue(
                self._input_items_contain_text(
                    agent.calls[0]["input_items"], "structured assistant"
                )
            )

    def test_thread_resume_rebuilds_function_call_output_items_for_request_user_input_turn(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            runtime = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            thread = runtime.start_thread(name="request input persistence")
            runtime.collaboration_mode = "plan"
            runtime.request_user_input_handler = lambda payload: {
                "answers": {"confirm_path": {"answers": ["yes"]}},
                "questions": payload["questions"],
            }

            runtime.handle_prompt(
                '/request_user_input \'{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?","options":[{"label":"Yes (Recommended)","description":"Continue."},{"label":"No","description":"Stop."}]}]}\''  # noqa: E501
            )

            resumed = store.resume_thread(thread["thread_id"])
            function_outputs = self._function_call_output_items(resumed["planner_input_items"])

            self.assertEqual(len(function_outputs), 1)
            self.assertEqual(function_outputs[0]["call_id"], "item_0")
            self.assertTrue(function_outputs[0]["success"])
            output_payload = json.loads(function_outputs[0]["output"])
            self.assertEqual(
                output_payload["response"]["answers"]["confirm_path"]["answers"], ["yes"]
            )

    def test_runtime_follow_up_preserves_function_call_output_items_for_request_user_input_turn(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            runtime1 = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            thread = runtime1.start_thread(name="request input follow up")
            runtime1.collaboration_mode = "plan"
            runtime1.request_user_input_handler = lambda payload: {
                "answers": {"confirm_path": {"answers": ["yes"]}},
                "questions": payload["questions"],
            }

            runtime1.handle_prompt(
                '/request_user_input \'{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?","options":[{"label":"Yes (Recommended)","description":"Continue."},{"label":"No","description":"Stop."}]}]}\''  # noqa: E501
            )

            agent2 = _RecordingAgent()
            runtime2 = AgentCliRuntime(agent=agent2, thread_store=store)
            runtime2.resume_thread(thread["thread_id"])
            runtime2._planner_input_items = []

            runtime2.handle_prompt("follow up")

            function_outputs = self._function_call_output_items(agent2.calls[0]["input_items"])
            self.assertEqual(len(function_outputs), 1)
            self.assertEqual(function_outputs[0]["call_id"], "item_0")
            output_payload = json.loads(function_outputs[0]["output"])
            self.assertEqual(
                output_payload["response"]["answers"]["confirm_path"]["answers"], ["yes"]
            )

    def test_thread_resume_rebuilds_function_call_output_items_for_normalized_request_user_input_shape(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            runtime = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            thread = runtime.start_thread(name="request input shape normalize persistence")
            runtime.collaboration_mode = "plan"
            runtime.request_user_input_handler = lambda _payload: {
                "answers": {"confirm_path": "yes"},
            }

            runtime.handle_prompt(
                '/request_user_input \'{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?","options":[{"label":"Yes (Recommended)","description":"Continue."},{"label":"No","description":"Stop."}]}]}\''  # noqa: E501
            )

            resumed = store.resume_thread(thread["thread_id"])
            function_outputs = self._function_call_output_items(resumed["planner_input_items"])

            self.assertEqual(len(function_outputs), 1)
            self.assertEqual(function_outputs[0]["call_id"], "item_0")
            self.assertTrue(function_outputs[0]["success"])
            output_payload = json.loads(function_outputs[0]["output"])
            self.assertEqual(
                output_payload["response"]["answers"]["confirm_path"], {"answers": ["yes"]}
            )

    def test_thread_resume_rebuilds_function_call_output_items_for_cancelled_request_user_input_turn(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            runtime = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            thread = runtime.start_thread(name="request input cancelled persistence")
            runtime.collaboration_mode = "plan"
            runtime.request_user_input_handler = lambda _payload: []  # type: ignore[assignment]

            runtime.handle_prompt(
                '/request_user_input \'{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?","options":[{"label":"Yes (Recommended)","description":"Continue."},{"label":"No","description":"Stop."}]}]}\''  # noqa: E501
            )

            resumed = store.resume_thread(thread["thread_id"])
            function_outputs = self._function_call_output_items(resumed["planner_input_items"])

            self.assertEqual(len(function_outputs), 1)
            self.assertEqual(function_outputs[0]["call_id"], "item_0")
            self.assertFalse(function_outputs[0]["success"])
            self.assertIn(
                "request_user_input was cancelled before receiving a response",
                str(function_outputs[0]["output"]),
            )

    def test_thread_resume_rebuilds_function_call_items_and_outputs_for_update_plan_turn(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            runtime = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            thread = runtime.start_thread(name="update plan persistence")

            runtime.handle_prompt(
                '/update_plan \'{"explanation":"sync","plan":[{"step":"inspect","status":"completed"},{"step":"patch","status":"in_progress"}]}\''
            )

            resumed = store.resume_thread(thread["thread_id"])
            function_calls = self._function_call_items(resumed["planner_input_items"])
            function_outputs = self._function_call_output_items(resumed["planner_input_items"])

            self.assertEqual(len(function_calls), 1)
            self.assertEqual(function_calls[0]["name"], "update_plan")
            self.assertEqual(function_calls[0]["call_id"], "item_0")
            self.assertEqual(
                json.loads(function_calls[0]["arguments"]),
                {
                    "explanation": "sync",
                    "plan": [
                        {"step": "inspect", "status": "completed"},
                        {"step": "patch", "status": "in_progress"},
                    ],
                },
            )
            self.assertEqual(len(function_outputs), 1)
            self.assertEqual(function_outputs[0]["call_id"], "item_0")
            self.assertEqual(function_outputs[0]["output"], "Plan updated")
            self.assertTrue(function_outputs[0]["success"])

    def test_runtime_follow_up_preserves_update_plan_call_and_output_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            runtime1 = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            thread = runtime1.start_thread(name="update plan follow up")

            runtime1.handle_prompt(
                '/update_plan \'{"explanation":"sync","plan":[{"step":"inspect","status":"completed"},{"step":"patch","status":"in_progress"}]}\''
            )

            agent2 = _RecordingAgent()
            runtime2 = AgentCliRuntime(agent=agent2, thread_store=store)
            runtime2.resume_thread(thread["thread_id"])
            runtime2._planner_input_items = []

            runtime2.handle_prompt("上一轮计划是什么？")

            function_calls = self._function_call_items(agent2.calls[0]["input_items"])
            function_outputs = self._function_call_output_items(agent2.calls[0]["input_items"])
            self.assertEqual(len(function_calls), 1)
            self.assertEqual(function_calls[0]["name"], "update_plan")
            self.assertEqual(function_calls[0]["call_id"], "item_0")
            self.assertEqual(len(function_outputs), 1)
            self.assertEqual(function_outputs[0]["call_id"], "item_0")
            self.assertEqual(function_outputs[0]["output"], "Plan updated")
            self.assertTrue(function_outputs[0]["success"])

    def test_resume_thread_restores_latest_task_plan_from_most_recent_update_plan_turn(
        self,
    ) -> None:
        second_payload = {
            "explanation": "second",
            "plan": [
                {"step": "inspect", "status": "completed"},
                {"step": "patch", "status": "in_progress"},
                {"step": "test", "status": "pending"},
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            runtime1 = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            thread = runtime1.start_thread(name="update plan latest state")

            runtime1.handle_prompt(
                '/update_plan \'{"explanation":"first","plan":[{"step":"inspect","status":"in_progress"},{"step":"patch","status":"pending"}]}\''
            )
            runtime1.handle_prompt(
                '/update_plan \'{"explanation":"second","plan":[{"step":"inspect","status":"completed"},{"step":"patch","status":"in_progress"},{"step":"test","status":"pending"}]}\''
            )

            runtime2 = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            resumed = runtime2.resume_thread(thread["thread_id"])

            self.assertEqual(resumed["state"].get("latest_task_plan"), second_payload)
            self.assertEqual(runtime2.latest_task_plan, second_payload)
            function_calls = self._function_call_items(resumed["planner_input_items"])
            function_outputs = self._function_call_output_items(resumed["planner_input_items"])
            self.assertEqual(
                [item["name"] for item in function_calls], ["update_plan", "update_plan"]
            )
            self.assertEqual(len(function_outputs), 2)
            self.assertTrue(all(item["output"] == "Plan updated" for item in function_outputs))

    def test_resume_thread_derives_latest_task_plan_from_legacy_update_plan_turns_without_runtime_snapshot(
        self,
    ) -> None:
        second_payload = {
            "explanation": "second",
            "plan": [
                {"step": "inspect", "status": "completed"},
                {"step": "patch", "status": "in_progress"},
                {"step": "test", "status": "pending"},
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="legacy update plan state")
            for explanation, plan in [
                (
                    "first",
                    [
                        {"step": "inspect", "status": "in_progress"},
                        {"step": "patch", "status": "pending"},
                    ],
                ),
                ("second", second_payload["plan"]),
            ]:
                store.append_turn(
                    thread.thread_id,
                    PromptResponse(
                        user_text="/update_plan",
                        assistant_text="Plan updated",
                        response_items=default_response_items(assistant_text="Plan updated"),
                        tool_events=[
                            ToolEvent(
                                name="update_plan",
                                ok=True,
                                summary="Plan updated",
                                payload={"explanation": explanation, "plan": plan},
                            )
                        ],
                    ),
                    runtime_state={},
                )

            resumed = store.resume_thread(thread.thread_id)

            self.assertEqual(resumed["state"].get("latest_task_plan"), second_payload)

    def test_runtime_follow_up_after_multiple_update_plan_turns_keeps_history_and_latest_state(
        self,
    ) -> None:
        second_payload = {
            "explanation": "second",
            "plan": [
                {"step": "inspect", "status": "completed"},
                {"step": "patch", "status": "in_progress"},
                {"step": "test", "status": "pending"},
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            runtime1 = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            thread = runtime1.start_thread(name="update plan multi turn follow up")

            runtime1.handle_prompt(
                '/update_plan \'{"explanation":"first","plan":[{"step":"inspect","status":"in_progress"},{"step":"patch","status":"pending"}]}\''
            )
            runtime1.handle_prompt(
                '/update_plan \'{"explanation":"second","plan":[{"step":"inspect","status":"completed"},{"step":"patch","status":"in_progress"},{"step":"test","status":"pending"}]}\''
            )

            agent2 = _RecordingAgent()
            runtime2 = AgentCliRuntime(agent=agent2, thread_store=store)
            runtime2.resume_thread(thread["thread_id"])
            runtime2._planner_input_items = []

            runtime2.handle_prompt("基于当前计划，下一步做什么？")

            self.assertEqual(runtime2.latest_task_plan, second_payload)
            function_calls = self._function_call_items(agent2.calls[0]["input_items"])
            function_outputs = self._function_call_output_items(agent2.calls[0]["input_items"])
            self.assertEqual(
                [item["name"] for item in function_calls], ["update_plan", "update_plan"]
            )
            self.assertEqual(len(function_outputs), 2)
            self.assertTrue(all(item["output"] == "Plan updated" for item in function_outputs))
            self.assertTrue(all(item["success"] for item in function_outputs))

    def test_thread_resume_rebuilds_function_call_output_items_for_failed_tool_turn(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="failed tool turn persistence")
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="先执行 ls /missing，再告诉我结果。",
                    assistant_text="ls: cannot access '/missing': No such file or directory",
                    response_items=default_response_items(
                        assistant_text="结果是：ls: cannot access '/missing': No such file or directory（/missing 不存在）。"
                    ),
                    tool_events=[self._failed_exec_command_tool_event()],
                ),
            )

            resumed = store.resume_thread(thread.thread_id)
            function_outputs = self._function_call_output_items(resumed["planner_input_items"])

            self.assertEqual(len(function_outputs), 1)
            self.assertEqual(function_outputs[0]["call_id"], "call_exec_1")
            self.assertFalse(function_outputs[0]["success"])
            self.assertIn("No such file or directory", str(function_outputs[0]["output"]))

    def test_runtime_follow_up_preserves_function_call_output_items_for_failed_tool_turn(
        self,
    ) -> None:
        class _FailingToolAgent(_RecordingAgent):
            def plan(
                self, text, history=None, *, tool_executor=None, attachments=None, input_items=None
            ):
                self.calls.append(
                    {
                        "text": text,
                        "history": list(history or []),
                        "input_items": list(input_items or []),
                    }
                )
                if len(self.calls) == 1:
                    return AgentIntent(
                        assistant_text="结果是：ls: cannot access '/missing': No such file or directory（/missing 不存在）。",
                        response_items=default_response_items(
                            assistant_text="结果是：ls: cannot access '/missing': No such file or directory（/missing 不存在）。"
                        ),
                        tool_events=[ThreadPersistenceTest._failed_exec_command_tool_event()],
                        status_hint="tool",
                    )
                return AgentIntent(assistant_text="因为目录不存在。")

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            agent = _FailingToolAgent()
            runtime = AgentCliRuntime(agent=agent, thread_store=store)
            runtime.start_thread(name="failed tool follow up")

            response1 = runtime.handle_prompt("先执行 ls /missing，再告诉我结果。")
            self.assertEqual(
                response1.assistant_text,
                "结果是：ls: cannot access '/missing': No such file or directory（/missing 不存在）。",
            )

            runtime.handle_prompt("上一轮失败的原因是什么？只回复一句话。")

            function_outputs = self._function_call_output_items(agent.calls[1]["input_items"])
            self.assertEqual(len(function_outputs), 1)
            self.assertEqual(function_outputs[0]["call_id"], "call_exec_1")
            self.assertFalse(function_outputs[0]["success"])
            self.assertIn("No such file or directory", str(function_outputs[0]["output"]))

    def test_runtime_follow_up_preserves_function_call_items_for_successful_tool_turn(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="successful tool follow up")
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="执行 pwd 并告诉我结果。",
                    assistant_text="当前目录是 /repo。",
                    response_items=default_response_items(assistant_text="当前目录是 /repo。"),
                    tool_events=[self._successful_exec_command_tool_event()],
                ),
            )

            resumed = store.resume_thread(thread.thread_id)
            function_calls = self._function_call_items(resumed["planner_input_items"])
            function_outputs = self._function_call_output_items(resumed["planner_input_items"])

            self.assertEqual(len(function_calls), 1)
            self.assertEqual(function_calls[0]["call_id"], "call_exec_ok_1")
            self.assertEqual(len(function_outputs), 1)
            self.assertEqual(function_outputs[0]["call_id"], "call_exec_ok_1")
            self.assertTrue(function_outputs[0]["success"])

            agent = _RecordingAgent()
            runtime = AgentCliRuntime(agent=agent, thread_store=store)
            runtime.resume_thread(thread.thread_id)
            runtime.handle_prompt("刚才命令返回了什么？")

            function_calls = self._function_call_items(agent.calls[0]["input_items"])
            function_outputs = self._function_call_output_items(agent.calls[0]["input_items"])
            self.assertEqual(len(function_calls), 1)
            self.assertEqual(function_calls[0]["call_id"], "call_exec_ok_1")
            self.assertEqual(len(function_outputs), 1)
            self.assertEqual(function_outputs[0]["call_id"], "call_exec_ok_1")
            self.assertTrue(function_outputs[0]["success"])

    def test_thread_resume_keeps_image_ready_without_synthesizing_image_injected_output(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="image ready only")
            image_artifact = {
                "path": "/tmp/sample.png",
                "mime_type": "image/png",
                "size_bytes": 42,
                "width": 10,
                "height": 12,
                "image_url": "data:image/png;base64,AAA",
                "detail": "high",
            }
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="inspect image",
                    assistant_text="image ready",
                    response_items=default_response_items(assistant_text="image ready"),
                    tool_events=[
                        ToolEvent(
                            name="view_image",
                            ok=True,
                            summary="image ready",
                            payload={
                                "provider_call_id": "call_view_image_1",
                                "ok": True,
                                "path": "/tmp/sample.png",
                                "requested_path": "sample.png",
                                "image_artifacts": [image_artifact],
                            },
                        )
                    ],
                    turn_events=[
                        {"type": "turn.started"},
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "item_1",
                                "type": "mcp_tool_call",
                                "tool": "view_image",
                                "arguments": {"path": "/tmp/sample.png"},
                                "result": {
                                    "structured_content": {"image_artifacts": [image_artifact]}
                                },
                                "status": "completed",
                            },
                        },
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "item_2",
                                "type": "agent_message",
                                "text": "image ready",
                            },
                        },
                        {"type": "turn.completed"},
                    ],
                ),
            )

            resumed = store.resume_thread(thread.thread_id)
            function_calls = self._function_call_items(resumed["planner_input_items"])
            input_images = self._input_image_output_items(resumed["planner_input_items"])

            self.assertEqual(len(function_calls), 1)
            self.assertEqual(function_calls[0]["call_id"], "call_view_image_1")
            self.assertEqual(input_images, [])
            media_state = resumed["turns"][0]["runtime_state"]["media_artifacts"]
            self.assertEqual(media_state["schema"], "v1")
            self.assertEqual(len(media_state["ready_handles"]), 1)
            self.assertEqual(media_state["injected_handles"], [])

    def test_thread_resume_preserves_explicit_image_injected_output_and_media_handles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="image injected")
            image_artifact = {
                "path": "/tmp/sample.png",
                "mime_type": "image/png",
                "size_bytes": 42,
                "width": 10,
                "height": 12,
                "image_url": "data:image/png;base64,AAA",
                "detail": "high",
            }
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="inspect image",
                    assistant_text="image injected",
                    response_items=default_response_items(assistant_text="image injected"),
                    tool_events=[
                        ToolEvent(
                            name="view_image",
                            ok=True,
                            summary="image ready",
                            payload={
                                "provider_call_id": "call_view_image_1",
                                "ok": True,
                                "path": "/tmp/sample.png",
                                "requested_path": "sample.png",
                                "image_artifacts": [image_artifact],
                            },
                        )
                    ],
                    turn_events=[
                        {"type": "turn.started"},
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "item_1",
                                "type": "mcp_tool_call",
                                "tool": "view_image",
                                "arguments": {"path": "/tmp/sample.png"},
                                "result": {
                                    "structured_content": {"image_artifacts": [image_artifact]}
                                },
                                "status": "completed",
                            },
                        },
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "item_2",
                                "type": "function_call_output",
                                "call_id": "call_view_image_1",
                                "output": [
                                    {
                                        "type": "input_image",
                                        "image_url": "data:image/png;base64,AAA",
                                        "detail": "high",
                                    }
                                ],
                                "success": True,
                            },
                        },
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "item_3",
                                "type": "agent_message",
                                "text": "image injected",
                            },
                        },
                        {"type": "turn.completed"},
                    ],
                ),
            )

            resumed = store.resume_thread(thread.thread_id)
            function_outputs = self._function_call_output_items(resumed["planner_input_items"])
            input_images = self._input_image_output_items(resumed["planner_input_items"])

            self.assertEqual(len(function_outputs), 1)
            self.assertEqual(function_outputs[0]["call_id"], "call_view_image_1")
            self.assertEqual(len(input_images), 1)
            self.assertEqual(input_images[0]["image_url"], "data:image/png;base64,AAA")
            media_state = resumed["turns"][0]["runtime_state"]["media_artifacts"]
            self.assertEqual(media_state["schema"], "v1")
            self.assertEqual(len(media_state["ready_handles"]), 1)
            self.assertEqual(len(media_state["injected_handles"]), 1)

    def test_runtime_follow_up_preserves_provider_native_items_and_reasoning_extensions(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="provider native continuity")
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="现在北京时间几点？",
                    assistant_text="北京时间 10:00。",
                    response_items=[
                        ResponseInputItem.from_dict(
                            {
                                "type": "reasoning",
                                "id": "rs_1",
                                "status": "completed",
                                "summary": [{"type": "summary_text", "text": "先查询北京时间"}],
                                "encrypted_content": "enc-1",
                                "content": [{"type": "reasoning", "text": "先查询北京时间"}],
                            }
                        ),
                        ResponseInputItem.from_dict(
                            {
                                "type": "web_search_call",
                                "id": "ws_1",
                                "action": {"query": 'time: {"utc_offset":"+08:00"}'},
                            }
                        ),
                        ResponseInputItem.from_dict(
                            {
                                "type": "message",
                                "role": "assistant",
                                "phase": "final_answer",
                                "content": [{"type": "output_text", "text": "北京时间 10:00。"}],
                            }
                        ),
                    ],
                ),
            )

            resumed = store.resume_thread(thread.thread_id)
            resumed_reasoning = self._reasoning_items(resumed["planner_input_items"])
            resumed_web_search = [
                dict(item)
                for item in list(resumed["planner_input_items"] or [])
                if isinstance(item, dict)
                and str(item.get("type") or "").strip() == "web_search_call"
            ]
            reasoning_turn_items = [
                dict(event.get("item") or {})
                for event in list(resumed["turns"][0]["turn_events"] or [])
                if isinstance(event, dict)
                and str(event.get("type") or "").strip() == "item.completed"
                and isinstance(event.get("item"), dict)
                and str(event["item"].get("type") or "").strip() == "reasoning"
            ]
            self.assertEqual(len(resumed_reasoning), 1)
            self.assertEqual(resumed_reasoning[0]["encrypted_content"], "enc-1")
            self.assertEqual(resumed_reasoning[0]["summary"][0]["text"], "先查询北京时间")
            self.assertEqual(len(resumed_web_search), 1)
            self.assertEqual(
                resumed_web_search[0]["action"]["query"], 'time: {"utc_offset":"+08:00"}'
            )
            self.assertEqual(len(reasoning_turn_items), 1)
            self.assertEqual(reasoning_turn_items[0]["encrypted_content"], "enc-1")

            agent = _RecordingAgent()
            runtime = AgentCliRuntime(agent=agent, thread_store=store)
            runtime.resume_thread(thread.thread_id)
            runtime.handle_prompt("继续")

            reasoning_items = self._reasoning_items(agent.calls[0]["input_items"])
            web_search_items = [
                dict(item)
                for item in list(agent.calls[0]["input_items"] or [])
                if isinstance(item, dict)
                and str(item.get("type") or "").strip() == "web_search_call"
            ]
            self.assertEqual(len(reasoning_items), 1)
            self.assertEqual(reasoning_items[0]["encrypted_content"], "enc-1")
            self.assertEqual(reasoning_items[0]["summary"][0]["text"], "先查询北京时间")
            self.assertEqual(len(web_search_items), 1)
            self.assertEqual(
                web_search_items[0]["action"]["query"], 'time: {"utc_offset":"+08:00"}'
            )

    def test_runtime_follow_up_excludes_local_dialog_turns_from_provider_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="local dialog excluded")
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="你好",
                    assistant_text="你好！有什么我可以帮你处理的？",
                    protocol_diagnostics={
                        "protocol_path": {
                            "kind": "local_dialog",
                            "source": "runtime",
                            "provider_used": False,
                        }
                    },
                ),
            )
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="今天几号？",
                    assistant_text="今天是 2026 年 4 月 1 日。",
                    protocol_diagnostics={
                        "protocol_path": {
                            "kind": "provider_loop",
                            "source": "provider",
                            "provider_used": True,
                        }
                    },
                    response_items=default_response_items(
                        assistant_text="今天是 2026 年 4 月 1 日。"
                    ),
                ),
            )

            agent = _RecordingAgent()
            runtime = AgentCliRuntime(agent=agent, thread_store=store)
            runtime.resume_thread(thread.thread_id)
            runtime.handle_prompt("明天呢？")

            input_items = agent.calls[0]["input_items"]
            self.assertFalse(self._input_items_contain_text(input_items, "你好"))
            self.assertFalse(
                self._input_items_contain_text(input_items, "你好！有什么我可以帮你处理的？")
            )
            self.assertTrue(self._input_items_contain_text(input_items, "今天几号？"))
            self.assertTrue(
                self._input_items_contain_text(input_items, "今天是 2026 年 4 月 1 日。")
            )

    def test_runtime_resume_prefers_structured_turn_history_for_legacy_planner_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="legacy planner structured preferred")
            store.append_rollout_items(
                thread.thread_id,
                [
                    {"type": "response_item", "role": "user", "content": "legacy user"},
                    {"type": "response_item", "role": "assistant", "content": "legacy assistant"},
                ],
            )
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="structured user",
                    assistant_text="structured assistant",
                ),
            )

            agent = _LegacyHistoryAgent()
            runtime = AgentCliRuntime(agent=agent, thread_store=store)
            runtime.resume_thread(thread.thread_id)
            runtime.handle_prompt("follow up")

            self.assertEqual(agent.calls[0]["text"], "follow up")
            self.assertTrue(
                self._history_contains_text(agent.calls[0]["history"], "structured user")
            )
            self.assertTrue(
                self._history_contains_text(agent.calls[0]["history"], "structured assistant")
            )
            self.assertFalse(self._history_contains_text(agent.calls[0]["history"], "legacy user"))

    def test_thread_store_persists_phase_aware_response_items_on_turns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="phase aware")
            response = PromptResponse(
                user_text="hello",
                commentary_text="thinking",
                assistant_text="answer",
                response_items=default_response_items(
                    commentary_text="thinking",
                    assistant_text="answer",
                ),
            )
            response.turn_events = prompt_response_turn_events(response)
            store.append_turn(
                thread.thread_id,
                response,
            )

            resumed = store.resume_thread(thread.thread_id)

            self.assertEqual(resumed["planner_input_items"][0]["role"], "user")
            self.assertEqual(resumed["planner_input_items"][1]["phase"], "commentary")
            self.assertEqual(resumed["planner_input_items"][2]["phase"], "final_answer")
            self.assertEqual(resumed["turns"][0]["turn_events"][0]["type"], "turn.started")
            self.assertEqual(resumed["turns"][0]["turn_events"][-1]["type"], "turn.completed")

    def test_thread_store_persists_protocol_diagnostics_on_turns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="protocol diagnostics")
            response = PromptResponse(
                user_text="what drove this turn",
                commentary_text="checking protocol state",
                assistant_text="provider path answer",
                protocol_diagnostics={
                    "protocol_path": {
                        "kind": "provider_loop",
                        "source": "provider",
                        "provider_used": True,
                    },
                    "request_contract": {
                        "prelude": {
                            "section_order": [
                                "developer",
                                "workspace_context",
                                "environment_context",
                            ],
                        }
                    },
                },
                response_items=default_response_items(
                    commentary_text="checking protocol state",
                    assistant_text="provider path answer",
                ),
            )
            response.turn_events = prompt_response_turn_events(response)
            store.append_turn(thread.thread_id, response)

            resumed = store.resume_thread(thread.thread_id)

            self.assertEqual(
                resumed["turns"][0]["protocol_diagnostics"]["protocol_path"]["kind"],
                "provider_loop",
            )
            self.assertEqual(
                resumed["turns"][0]["protocol_diagnostics"]["request_contract"]["prelude"][
                    "section_order"
                ],
                ["developer", "workspace_context", "environment_context"],
            )

    def test_thread_store_fallback_turn_events_stay_message_only_without_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="message fallback")
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="hello",
                    commentary_text="thinking",
                    assistant_text="answer",
                    tool_events=[
                        ToolEvent(
                            name="shell",
                            ok=True,
                            summary="shell rc=0",
                            payload={"command": "echo hi", "returncode": 0},
                        )
                    ],
                ),
            )

            resumed = store.resume_thread(thread.thread_id)
            turn_events = list(resumed["turns"][0]["turn_events"])
            self.assertEqual(turn_events[0]["type"], "turn.started")
            self.assertEqual(turn_events[-1]["type"], "turn.completed")
            completed_items = [
                dict(event.get("item") or {})
                for event in turn_events
                if event.get("type") == "item.completed"
            ]
            self.assertTrue(completed_items)
            self.assertEqual(completed_items[-1]["type"], "agent_message")

    def test_thread_resume_history_prefers_response_items_when_turn_has_structured_tool_items(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="structured tool turn")
            response = PromptResponse(
                user_text="list files",
                commentary_text="",
                assistant_text="final from response item",
                response_items=default_response_items(assistant_text="final from response item"),
                tool_events=[
                    ToolEvent(
                        name="file_list",
                        ok=True,
                        summary="file_list ok: files=3",
                        payload={"path": "."},
                    )
                ],
            )
            response.turn_events = [
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_0",
                        "type": "command_execution",
                        "command": "/file_list .",
                        "aggregated_output": "files=3",
                        "exit_code": 0,
                        "status": "completed",
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_1",
                        "type": "agent_message",
                        "text": "final from response item",
                    },
                },
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
                },
            ]
            store.append_turn(thread.thread_id, response)

            resumed = store.resume_thread(thread.thread_id)
            self.assertEqual(
                resumed["history"],
                [
                    {"role": "user", "content": "list files"},
                    {"role": "assistant", "content": "final from response item"},
                ],
            )

    def test_thread_resume_history_prefers_canonical_turn_event_message_for_structured_tool_turn(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="structured tool canonical message")
            response = PromptResponse(
                user_text="list files",
                commentary_text="",
                assistant_text="legacy fallback",
                response_items=default_response_items(assistant_text="stale final"),
                tool_events=[
                    ToolEvent(
                        name="file_list",
                        ok=True,
                        summary="file_list ok: files=3",
                        payload={"path": "."},
                    )
                ],
            )
            response.turn_events = [
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_0",
                        "type": "command_execution",
                        "command": "/file_list .",
                        "aggregated_output": "files=3",
                        "exit_code": 0,
                        "status": "completed",
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_1",
                        "type": "agent_message",
                        "text": "canonical final",
                    },
                },
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
                },
            ]
            store.append_turn(thread.thread_id, response)

            resumed = store.resume_thread(thread.thread_id)
            self.assertEqual(
                resumed["history"],
                [
                    {"role": "user", "content": "list files"},
                    {"role": "assistant", "content": "canonical final"},
                ],
            )

    def test_thread_store_lists_latest_threads_and_active_thread(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            runtime = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            first = runtime.start_thread(name="first")
            runtime.handle_prompt("one")
            second = runtime.start_thread(name="second")
            runtime.handle_prompt("two")

            threads = runtime.list_threads(limit=10)

            self.assertEqual(
                [item["thread_id"] for item in threads[:2]],
                [second["thread_id"], first["thread_id"]],
            )
            self.assertEqual(store.get_active_thread_id(), second["thread_id"])
            self.assertTrue(Path(threads[0]["rollout_path"]).exists())
            self.assertTrue(Path(temp_dir, "threads.sqlite3").exists())

    def test_append_turn_can_skip_active_thread_update(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            first = store.start_thread(name="first")
            second = store.start_thread(name="second")
            self.assertEqual(store.get_active_thread_id(), second.thread_id)

            store.append_turn(
                first.thread_id,
                PromptResponse(user_text="background", assistant_text="done"),
                update_active=False,
            )

            self.assertEqual(store.get_active_thread_id(), second.thread_id)
            resumed = store.resume_thread(first.thread_id)
            self.assertEqual(resumed["history"][-1], {"role": "assistant", "content": "done"})

    def test_append_rollout_items_can_skip_active_thread_update(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            first = store.start_thread(name="first")
            second = store.start_thread(name="second")
            self.assertEqual(store.get_active_thread_id(), second.thread_id)

            store.append_rollout_items(
                first.thread_id,
                [
                    {
                        "item_type": "response_item",
                        "thread_id": first.thread_id,
                        "payload": {"type": "message", "role": "user", "content": "seed"},
                    }
                ],
                update_active=False,
            )

            self.assertEqual(store.get_active_thread_id(), second.thread_id)

    def test_append_compacted_can_skip_active_thread_update(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            first = store.start_thread(name="first")
            second = store.start_thread(name="second")
            self.assertEqual(store.get_active_thread_id(), second.thread_id)

            store.append_compacted(
                first.thread_id,
                replacement_history=[
                    {"role": "assistant", "content": "Previous conversation summary:\nseed"}
                ],
                metadata={"reason": "test"},
                update_active=False,
            )

            self.assertEqual(store.get_active_thread_id(), second.thread_id)

    def test_thread_store_filters_threads_by_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            first_workspace = Path(temp_dir) / "first"
            second_workspace = Path(temp_dir) / "second"
            first_workspace.mkdir()
            second_workspace.mkdir()
            store = ThreadStore(Path(temp_dir) / "state")
            runtime = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            first = runtime.start_thread(name="first", cwd=str(first_workspace))
            runtime.handle_prompt("one")
            runtime.start_thread(name="second", cwd=str(second_workspace))
            runtime.handle_prompt("two")

            threads = runtime.list_threads(limit=10, cwd=str(first_workspace))

            self.assertEqual([item["thread_id"] for item in threads], [first["thread_id"]])
            self.assertEqual(threads[0]["cwd"], str(first_workspace.resolve()))

    def test_resume_thread_does_not_override_ready_provider_with_stale_thread_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(
                name="stale openai thread",
                provider_status={
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                },
            )

            agent = _RecordingAgent()
            runtime = AgentCliRuntime(agent=agent, thread_store=store)
            resumed = runtime.resume_thread(thread.thread_id)

            self.assertEqual(resumed["thread"]["thread_id"], thread.thread_id)
            self.assertEqual(agent.switch_calls, [])
            self.assertEqual(runtime.agent.provider_status()["provider_name"], "deepseek")

    def test_resume_thread_restores_session_route_overrides_without_switching_ready_provider(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            runtime = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            thread = runtime.start_thread(name="route override thread")
            runtime.agent.configure_route_selection(
                "tool_followup",
                model="glm_5",
                provider="glm",
                reasoning_effort="high",
                timeout=30,
            )
            runtime.handle_prompt("hello route override")

            resumed_agent = _RecordingAgent()
            resumed_runtime = AgentCliRuntime(agent=resumed_agent, thread_store=store)
            resumed = resumed_runtime.resume_thread(thread["thread_id"])

            self.assertEqual(resumed["thread"]["thread_id"], thread["thread_id"])
            self.assertEqual(resumed_agent.switch_calls, [])
            self.assertEqual(
                resumed["state"]["session_route_overrides"]["tool_followup"]["model"],
                "glm_5",
            )
            self.assertEqual(
                resumed_agent.route_overrides["tool_followup"]["provider"],
                "glm",
            )
            self.assertEqual(
                resumed_agent.route_overrides["tool_followup"]["timeout"],
                30,
            )
            self.assertTrue(resumed_agent.route_override_calls)

    def test_resume_thread_restores_session_delegate_overrides_without_switching_ready_provider(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            runtime = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            thread = runtime.start_thread(name="delegate override thread")
            runtime.agent.configure_delegate_selection(
                "teammate",
                model="glm_5",
                provider="glm",
                reasoning_effort="medium",
                timeout=45,
            )
            runtime.handle_prompt("hello delegate override")

            resumed_agent = _RecordingAgent()
            resumed_runtime = AgentCliRuntime(agent=resumed_agent, thread_store=store)
            resumed = resumed_runtime.resume_thread(thread["thread_id"])

            self.assertEqual(resumed["thread"]["thread_id"], thread["thread_id"])
            self.assertEqual(resumed_agent.switch_calls, [])
            self.assertEqual(
                resumed["state"]["session_delegation_overrides"]["teammate"]["model"],
                "glm_5",
            )
            self.assertEqual(
                resumed_agent.delegate_overrides["teammate"]["provider"],
                "glm",
            )
            self.assertEqual(
                resumed_agent.delegate_overrides["teammate"]["timeout"],
                45,
            )
            self.assertTrue(resumed_agent.delegate_override_calls)

    def test_resume_thread_restores_delegated_agent_sessions_and_requeues_active_input(
        self,
    ) -> None:
        class _DelegatedPlanner:
            calls: list[dict] = []

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
                del history, tool_executor, attachments, prompt_cache_key
                self.__class__.calls.append(
                    {
                        "user_text": user_text,
                        "input_items": list(input_items or []),
                    }
                )
                return AgentIntent(assistant_text=f"answer:{user_text}")

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            runtime = AgentCliRuntime(agent=_DelegatingRecordingAgent(), thread_store=store)
            thread = runtime.start_thread(name="delegated session thread")

            _DelegatedPlanner.calls = []
            with patch(
                "cli.agent_cli.runtime.build_planner",
                side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
            ):
                spawned = runtime.spawn_agent_result(
                    task="first turn", role="subagent", async_mode=True
                )
                agent_id = spawned.tool_events[0].payload["agent_id"]

                first_wait = runtime.wait_agent_result(agent_id, timeout_ms=1000)
                self.assertEqual(first_wait.assistant_text, "answer:first turn")

                session = runtime._delegated_agents[agent_id]
                with session.condition:
                    session.protocol_run_id = "run_resume_1"
                    session.protocol_parent_run_id = "run_parent_resume_1"
                    session.protocol_thread_id = thread["thread_id"]
                    session.status = "running"
                    session.closed = False
                    session.close_requested = False
                    session.active_input = {"message": "second turn", "interrupt": False}
                    session.queued_inputs = []

                store.append_turn(
                    thread["thread_id"],
                    PromptResponse(
                        user_text="persist delegated state",
                        assistant_text="snapshot saved",
                    ),
                    runtime_state=runtime._snapshot_thread_state(),
                )

            resumed_runtime = AgentCliRuntime(agent=_DelegatingRecordingAgent(), thread_store=store)
            with patch(
                "cli.agent_cli.runtime.build_planner",
                side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
            ):
                resumed = resumed_runtime.resume_thread(thread["thread_id"])

                delegated_state = list(resumed["state"].get("delegated_agents") or [])
                self.assertEqual(len(delegated_state), 1)
                self.assertEqual(delegated_state[0]["agent_id"], agent_id)
                self.assertEqual(delegated_state[0]["active_input"]["message"], "second turn")
                self.assertEqual(delegated_state[0]["resume_source"], "spawn_agent")
                self.assertEqual(
                    delegated_state[0]["child_identity"],
                    {
                        "agent_id": agent_id,
                        "run_id": "run_resume_1",
                        "parent_run_id": "run_parent_resume_1",
                        "thread_id": thread["thread_id"],
                    },
                )
                self.assertEqual(
                    delegated_state[0]["base_url"],
                    "https://open.bigmodel.cn/api/paas/v4",
                )

                second_wait = resumed_runtime.wait_agent_result(agent_id, timeout_ms=1000)
                self.assertEqual(second_wait.assistant_text, "answer:second turn")
                self.assertEqual(second_wait.tool_events[0].payload["provider_name"], "glm")
                self.assertEqual(
                    second_wait.tool_events[0].payload["base_url"],
                    "https://open.bigmodel.cn/api/paas/v4",
                )
                self.assertEqual(
                    second_wait.tool_events[0].payload["resume_source"], "thread_resume_restore"
                )
                self.assertEqual(
                    second_wait.tool_events[0].payload["child_identity"],
                    {
                        "agent_id": agent_id,
                        "run_id": "run_resume_1",
                        "parent_run_id": "run_parent_resume_1",
                        "thread_id": thread["thread_id"],
                    },
                )

            second_call = next(
                item for item in _DelegatedPlanner.calls if item["user_text"] == "second turn"
            )
            self.assertTrue(
                any(
                    "answer:first turn" in json.dumps(item, ensure_ascii=False)
                    for item in second_call["input_items"]
                )
            )

    def test_resume_thread_does_not_requeue_close_requested_active_input(self) -> None:
        class _DelegatedPlanner:
            calls: list[dict] = []

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
                del history, tool_executor, attachments, prompt_cache_key
                self.__class__.calls.append(
                    {
                        "user_text": user_text,
                        "input_items": list(input_items or []),
                    }
                )
                return AgentIntent(assistant_text=f"answer:{user_text}")

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            runtime = AgentCliRuntime(agent=_DelegatingRecordingAgent(), thread_store=store)
            thread = runtime.start_thread(name="delegated close restore thread")

            _DelegatedPlanner.calls = []
            with patch(
                "cli.agent_cli.runtime.build_planner",
                side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
            ):
                spawned = runtime.spawn_agent_result(
                    task="first turn", role="subagent", async_mode=True
                )
                agent_id = spawned.tool_events[0].payload["agent_id"]

                first_wait = runtime.wait_agent_result(agent_id, timeout_ms=1000)
                self.assertEqual(first_wait.assistant_text, "answer:first turn")

                session = runtime._delegated_agents[agent_id]
                with session.condition:
                    session.status = "closing"
                    session.closed = False
                    session.close_requested = True
                    session.terminal_reason = "close_requested"
                    session.active_input = {"message": "should not replay", "interrupt": False}
                    session.queued_inputs = []

                store.append_turn(
                    thread["thread_id"],
                    PromptResponse(
                        user_text="persist closing delegated state",
                        assistant_text="snapshot saved",
                    ),
                    runtime_state=runtime._snapshot_thread_state(),
                )

            resumed_runtime = AgentCliRuntime(agent=_DelegatingRecordingAgent(), thread_store=store)
            with patch(
                "cli.agent_cli.runtime.build_planner",
                side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
            ):
                resumed = resumed_runtime.resume_thread(thread["thread_id"])

                self.assertEqual(resumed["thread"]["thread_id"], thread["thread_id"])
                restored_session = resumed_runtime._delegated_agents[agent_id]
                with restored_session.condition:
                    self.assertTrue(restored_session.closed)
                    self.assertTrue(restored_session.close_requested)
                    self.assertEqual(restored_session.status, "closed")
                    self.assertEqual(restored_session.terminal_reason, "close_requested")
                    self.assertIsNone(restored_session.active_input)
                    self.assertEqual(restored_session.queued_inputs, [])

                waited = resumed_runtime.wait_agent_result(agent_id, timeout_ms=50)
                self.assertEqual(waited.tool_events[0].payload["status"], "closed")
                self.assertEqual(waited.tool_events[0].payload["pending_input_count"], 0)
                self.assertEqual(
                    waited.tool_events[0].payload["terminal_reason"], "close_requested"
                )

            self.assertEqual(
                [item["user_text"] for item in _DelegatedPlanner.calls],
                ["first turn"],
            )

    def test_resume_thread_restores_delegated_agent_adoption_and_scheduler_fields(self) -> None:
        class _DelegatedPlanner:
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
                del history, tool_executor, attachments, input_items, prompt_cache_key
                return AgentIntent(assistant_text=f"answer:{user_text}")

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            runtime = AgentCliRuntime(agent=_DelegatingRecordingAgent(), thread_store=store)
            thread = runtime.start_thread(name="delegated adoption thread")

            with patch(
                "cli.agent_cli.runtime.build_planner",
                side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
            ):
                spawned = runtime.spawn_agent_result(
                    task="completed turn",
                    role="subagent",
                    async_mode=True,
                    task_shape="read_only",
                )
                agent_id = spawned.tool_events[0].payload["agent_id"]
                waited = runtime.wait_agent_result(agent_id, timeout_ms=1000)
                self.assertTrue(waited.tool_events[0].payload["adopted"])

                session = runtime._delegated_agents[agent_id]
                with session.condition:
                    session.parallel_group = "read_only"
                    session.scheduler_reason = "read_only_parallel_limit_reached"
                    session.adopted = True
                    session.adopted_at = "2026-01-02T03:04:05+00:00"
                    session.updated_at = session.adopted_at

                store.append_turn(
                    thread["thread_id"],
                    PromptResponse(
                        user_text="persist delegated adoption state",
                        assistant_text="snapshot saved",
                    ),
                    runtime_state=runtime._snapshot_thread_state(),
                )

            resumed_runtime = AgentCliRuntime(agent=_DelegatingRecordingAgent(), thread_store=store)
            resumed = resumed_runtime.resume_thread(thread["thread_id"])

            delegated_state = list(resumed["state"].get("delegated_agents") or [])
            self.assertEqual(len(delegated_state), 1)
            self.assertEqual(delegated_state[0]["agent_id"], agent_id)
            self.assertEqual(delegated_state[0]["parallel_group"], "read_only")
            self.assertEqual(
                delegated_state[0]["scheduler_reason"], "read_only_parallel_limit_reached"
            )
            self.assertTrue(delegated_state[0]["adopted"])
            self.assertEqual(delegated_state[0]["adopted_at"], "2026-01-02T03:04:05+00:00")
            self.assertEqual(delegated_state[0]["last_wait_decision"], "blocking_join")
            self.assertGreaterEqual(delegated_state[0]["last_wait_blocked_ms"], 0)
            self.assertFalse(delegated_state[0]["last_wait_timed_out"])

            restored_session = resumed_runtime._delegated_agents[agent_id]
            self.assertEqual(restored_session.parallel_group, "read_only")
            self.assertEqual(restored_session.scheduler_reason, "read_only_parallel_limit_reached")
            self.assertTrue(restored_session.adopted)
            self.assertEqual(restored_session.adopted_at, "2026-01-02T03:04:05+00:00")
            self.assertEqual(restored_session.last_wait_decision, "blocking_join")
            self.assertIsInstance(restored_session.last_wait_blocked_ms, int)
            self.assertFalse(restored_session.last_wait_timed_out)

    def test_resume_thread_records_orphaned_background_teammate_when_delegate_restore_fails(
        self,
    ) -> None:
        class _DelegatedPlanner:
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
                del history, tool_executor, attachments, input_items, prompt_cache_key
                return AgentIntent(assistant_text=f"answer:{user_text}")

        class _FailingDelegatingAgent(_DelegatingRecordingAgent):
            def resolve_delegate_execution(
                self,
                role_name,
                *,
                model=None,
                provider=None,
                reasoning_effort=None,
                timeout=None,
            ):
                if str(role_name or "").strip() == "teammate":
                    raise RuntimeError("teammate restore unavailable")
                return super().resolve_delegate_execution(
                    role_name,
                    model=model,
                    provider=provider,
                    reasoning_effort=reasoning_effort,
                    timeout=timeout,
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            store = ThreadStore(temp_path / "threads")
            runtime = AgentCliRuntime(agent=_DelegatingRecordingAgent(), thread_store=store)
            runtime.set_cwd(temp_path)
            thread = runtime.start_thread(name="teammate restore failure thread")
            adapter = build_background_task_adapter(
                config=BackgroundTasksConfig(
                    enabled=True,
                    provider="huey",
                    huey=HueyConfig(
                        backend="sqlite",
                        path=temp_path / "background_tasks.sqlite3",
                        results_dir=temp_path / "results",
                        worker_count=1,
                        immediate=True,
                    ),
                )
            )

            with patch("cli.agent_cli.runtime.build_background_task_adapter", return_value=adapter):
                with patch(
                    "cli.agent_cli.runtime.build_planner",
                    side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
                ):
                    spawned = runtime.spawn_agent_result(
                        task="persist teammate background",
                        role="teammate",
                        async_mode=True,
                        mode="background",
                        wait_required=False,
                    )
                    agent_id = spawned.tool_events[0].payload["agent_id"]

                    session = runtime._delegated_agents[agent_id]
                    with session.condition:
                        session.status = "running"
                        session.closed = False
                        session.close_requested = False
                        session.active_input = {"message": "followup teammate", "interrupt": False}
                        session.queued_inputs = []

                    store.append_turn(
                        thread["thread_id"],
                        PromptResponse(
                            user_text="persist teammate delegated state",
                            assistant_text="snapshot saved",
                        ),
                        runtime_state=runtime._snapshot_thread_state(),
                    )

                resumed_runtime = AgentCliRuntime(
                    agent=_FailingDelegatingAgent(), thread_store=store
                )
                resumed_runtime.set_cwd(temp_path)
                resumed = resumed_runtime.resume_thread(thread["thread_id"])

            self.assertEqual(resumed["thread"]["thread_id"], thread["thread_id"])
            self.assertEqual(list(resumed["state"].get("delegated_agents") or []), [])

            stored = None
            for _ in range(20):
                stored = adapter.storage.get_result(f"bg_delegate_{agent_id}")
                if (
                    stored is not None
                    and (stored.artifact or {}).get("terminal_reason")
                    == "restore_resolution_failed"
                ):
                    break
            self.assertIsNotNone(stored)
            assert stored is not None
            self.assertEqual(stored.status.value, "cancelled")
            self.assertEqual(stored.artifact["notification_state"], "orphaned")
            self.assertEqual(stored.artifact["terminal_reason"], "restore_resolution_failed")
            self.assertIn("teammate restore unavailable", stored.error)

    def test_start_thread_does_not_orphan_completed_teammate_background_session(self) -> None:
        class _DelegatedPlanner:
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
                del history, tool_executor, attachments, input_items, prompt_cache_key
                return AgentIntent(assistant_text=f"answer:{user_text}")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            store = ThreadStore(temp_path / "threads")
            runtime = AgentCliRuntime(agent=_DelegatingRecordingAgent(), thread_store=store)
            runtime.set_cwd(temp_path)
            runtime.start_thread(name="background terminal thread")
            adapter = build_background_task_adapter(
                config=BackgroundTasksConfig(
                    enabled=True,
                    provider="huey",
                    huey=HueyConfig(
                        backend="sqlite",
                        path=temp_path / "background_tasks.sqlite3",
                        results_dir=temp_path / "results",
                        worker_count=1,
                        immediate=True,
                    ),
                )
            )

            with patch("cli.agent_cli.runtime.build_background_task_adapter", return_value=adapter):
                with patch(
                    "cli.agent_cli.runtime.build_planner",
                    side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
                ):
                    spawned = runtime.spawn_agent_result(
                        task="persist completed teammate",
                        role="teammate",
                        async_mode=True,
                        mode="background",
                        wait_required=False,
                    )
                    agent_id = spawned.tool_events[0].payload["agent_id"]

                    snapshot = None
                    for _ in range(20):
                        snapshot = runtime.wait_agent_result(
                            agent_id, timeout_ms=250, wait_required=False
                        )
                        if snapshot.tool_events[0].payload["status"] == "completed":
                            break
                        time.sleep(0.05)
                    assert snapshot is not None
                    self.assertEqual(snapshot.tool_events[0].payload["status"], "completed")
                    self.assertFalse(snapshot.tool_events[0].payload["adopted"])

                    stored = None
                    for _ in range(20):
                        stored = adapter.storage.get_result(f"bg_delegate_{agent_id}")
                        if (
                            stored is not None
                            and (stored.artifact or {}).get("notification_state") == "ready"
                        ):
                            break
                        time.sleep(0.05)
                    self.assertIsNotNone(stored)
                    assert stored is not None
                    self.assertEqual(stored.status.value, "completed")
                    self.assertEqual(stored.artifact["notification_state"], "ready")
                    self.assertEqual(stored.artifact["terminal_state"], "completed")
                    self.assertEqual(stored.artifact["terminal_reason"], "completed")

                    runtime.start_thread(name="fresh thread after completed teammate")

            stored_after = adapter.storage.get_result(f"bg_delegate_{agent_id}")
            self.assertIsNotNone(stored_after)
            assert stored_after is not None
            self.assertEqual(stored_after.status.value, "completed")
            self.assertEqual(stored_after.artifact["notification_state"], "ready")
            self.assertEqual(stored_after.artifact["terminal_state"], "completed")
            self.assertEqual(stored_after.artifact["terminal_reason"], "completed")

    def test_resume_thread_restore_failure_does_not_rewrite_completed_teammate_background_result(
        self,
    ) -> None:
        class _DelegatedPlanner:
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
                del history, tool_executor, attachments, input_items, prompt_cache_key
                return AgentIntent(assistant_text=f"answer:{user_text}")

        class _FailingDelegatingAgent(_DelegatingRecordingAgent):
            def resolve_delegate_execution(
                self,
                role_name,
                *,
                model=None,
                provider=None,
                reasoning_effort=None,
                timeout=None,
            ):
                if str(role_name or "").strip() == "teammate":
                    raise RuntimeError("teammate restore unavailable")
                return super().resolve_delegate_execution(
                    role_name,
                    model=model,
                    provider=provider,
                    reasoning_effort=reasoning_effort,
                    timeout=timeout,
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            store = ThreadStore(temp_path / "threads")
            runtime = AgentCliRuntime(agent=_DelegatingRecordingAgent(), thread_store=store)
            runtime.set_cwd(temp_path)
            thread = runtime.start_thread(name="completed teammate restore thread")
            adapter = build_background_task_adapter(
                config=BackgroundTasksConfig(
                    enabled=True,
                    provider="huey",
                    huey=HueyConfig(
                        backend="sqlite",
                        path=temp_path / "background_tasks.sqlite3",
                        results_dir=temp_path / "results",
                        worker_count=1,
                        immediate=True,
                    ),
                )
            )

            with patch("cli.agent_cli.runtime.build_background_task_adapter", return_value=adapter):
                with patch(
                    "cli.agent_cli.runtime.build_planner",
                    side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
                ):
                    spawned = runtime.spawn_agent_result(
                        task="persist completed teammate",
                        role="teammate",
                        async_mode=True,
                        mode="background",
                        wait_required=False,
                    )
                    agent_id = spawned.tool_events[0].payload["agent_id"]

                    snapshot = None
                    for _ in range(20):
                        snapshot = runtime.wait_agent_result(
                            agent_id, timeout_ms=250, wait_required=False
                        )
                        if snapshot.tool_events[0].payload["status"] == "completed":
                            break
                        time.sleep(0.05)
                    assert snapshot is not None
                    self.assertEqual(snapshot.tool_events[0].payload["status"], "completed")
                    self.assertFalse(snapshot.tool_events[0].payload["adopted"])

                    store.append_turn(
                        thread["thread_id"],
                        PromptResponse(
                            user_text="persist completed teammate state",
                            assistant_text="snapshot saved",
                        ),
                        runtime_state=runtime._snapshot_thread_state(),
                    )

                resumed_runtime = AgentCliRuntime(
                    agent=_FailingDelegatingAgent(), thread_store=store
                )
                resumed_runtime.set_cwd(temp_path)
                resumed = resumed_runtime.resume_thread(thread["thread_id"])

            self.assertEqual(resumed["thread"]["thread_id"], thread["thread_id"])
            self.assertEqual(list(resumed["state"].get("delegated_agents") or []), [])

            stored = adapter.storage.get_result(f"bg_delegate_{agent_id}")
            self.assertIsNotNone(stored)
            assert stored is not None
            self.assertEqual(stored.status.value, "completed")
            self.assertEqual(stored.artifact["notification_state"], "ready")
            self.assertEqual(stored.artifact["terminal_state"], "completed")
            self.assertEqual(stored.artifact["terminal_reason"], "completed")
            self.assertFalse(stored.error)

    def test_thread_resume_replays_assistant_history_with_tool_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="tool thread")
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="list current directory",
                    commentary_text="Checking current workspace before execution.",
                    assistant_text="Recognized as a local directory query. Preparing shell execution.",
                    tool_events=[
                        ToolEvent(
                            name="shell",
                            ok=True,
                            summary="shell ok: Get-ChildItem -Force",
                            payload={"command": "Get-ChildItem -Force"},
                        )
                    ],
                ),
            )

            resumed = store.resume_thread(thread.thread_id)

            self.assertEqual(
                resumed["history"],
                [
                    {"role": "user", "content": "list current directory"},
                    {
                        "role": "assistant",
                        "content": "Checking current workspace before execution.\n\nRecognized as a local directory query. Preparing shell execution.\n\nshell ok: Get-ChildItem -Force",
                    },
                ],
            )

    def test_resume_thread_restores_runtime_policy_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            runtime1 = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            thread = runtime1.start_thread(name="policy thread")
            runtime1.configure_runtime_policy(
                approval_policy="never",
                sandbox_mode="read-only",
                web_search_mode="disabled",
                network_access_enabled=False,
            )
            runtime1.handle_prompt("hello policy")

            runtime2 = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            runtime2.resume_thread(thread["thread_id"])

            self.assertEqual(runtime2.runtime_policy_status()["approval_policy"], "never")
            self.assertEqual(runtime2.runtime_policy_status()["sandbox_mode"], "read-only")
            self.assertEqual(runtime2.runtime_policy_status()["web_search_mode"], "disabled")
            self.assertEqual(runtime2.runtime_policy_status()["network_access"], "disabled")

    def test_commentary_only_turn_retains_history_with_tool_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="commentary thread")
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="note workspace",
                    commentary_text="Documenting action before the run.",
                    assistant_text="",
                    tool_events=[
                        ToolEvent(
                            name="shell",
                            ok=True,
                            summary="shell ok: List directory",
                            payload={"command": "Get-ChildItem -Force"},
                        )
                    ],
                ),
            )

            resumed = store.resume_thread(thread.thread_id)
            self.assertEqual(
                resumed["history"],
                [
                    {"role": "user", "content": "note workspace"},
                    {
                        "role": "assistant",
                        "content": "Documenting action before the run.\n\nshell ok: List directory",
                    },
                ],
            )

    def test_thread_listing_normalizes_stale_rollout_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ThreadStore(root)
            thread = store.start_thread(name="stale path thread")

            stale_dir = root / "legacy"
            stale_dir.mkdir(parents=True, exist_ok=True)
            stale_rollout = stale_dir / f"{thread.thread_id}.jsonl"
            stale_rollout.write_text('{"type":"thread_meta"}\n', encoding="utf-8")

            with store._connection() as conn:
                conn.execute(
                    """
                    UPDATE threads
                    SET rollout_path = ?
                    WHERE thread_id = ?
                    """,
                    (str(stale_rollout), thread.thread_id),
                )
                conn.commit()

            listed = store.list_threads(limit=10)
            current = next(item for item in listed if item["thread_id"] == thread.thread_id)

            self.assertEqual(
                Path(current["rollout_path"]),
                Path(temp_dir) / "rollouts" / f"{thread.thread_id}.jsonl",
            )
            self.assertTrue(Path(current["rollout_path"]).exists())

    def test_append_turn_persists_structured_turn_and_reference_context_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            attachment_path = root / "notes.txt"
            attachment_path.write_text("hello", encoding="utf-8")
            store = ThreadStore(root)
            thread = store.start_thread(name="structured thread")
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="inspect the note",
                    assistant_text="Loaded the local note.",
                    attachments=[PromptAttachment.from_path(str(attachment_path))],
                    tool_events=[
                        ToolEvent(
                            name="file_read",
                            ok=True,
                            summary="file loaded",
                            payload={"path": str(attachment_path)},
                        ),
                        ToolEvent(
                            name="open",
                            ok=True,
                            summary="page opened",
                            payload={
                                "url": "https://example.com/docs",
                                "title": "Example Docs",
                                "ref": "ref_1",
                            },
                        ),
                    ],
                ),
            )

            rollout_path = root / "rollouts" / f"{thread.thread_id}.jsonl"
            lines = [
                json.loads(line)
                for line in rollout_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            turn_line = lines[-1]

            self.assertEqual(turn_line["type"], "turn")
            self.assertIn("turn", turn_line)
            self.assertEqual(turn_line["turn"]["user_text"], "inspect the note")
            self.assertEqual(turn_line["turn"]["assistant_text"], "Loaded the local note.")
            context_items = turn_line["turn"]["reference_context_items"]
            self.assertTrue(
                any(
                    item["item_type"] == "attachment" and item["path"] == str(attachment_path)
                    for item in context_items
                )
            )
            self.assertTrue(
                any(
                    item["item_type"] == "file" and item["path"] == str(attachment_path)
                    for item in context_items
                )
            )
            self.assertTrue(
                any(
                    item["item_type"] == "web_page" and item["uri"] == "https://example.com/docs"
                    for item in context_items
                )
            )

    def test_append_turn_persists_reference_context_for_canonical_read_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            attachment_path = root / "note.txt"
            attachment_path.write_text("hello", encoding="utf-8")
            store = ThreadStore(root)
            thread = store.start_thread(name="canonical read thread")
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="inspect canonical read",
                    assistant_text="Loaded the note.",
                    tool_events=[
                        ToolEvent(
                            name="read_file",
                            ok=True,
                            summary="file loaded",
                            payload={
                                "file_path": str(attachment_path),
                                "path": str(attachment_path),
                            },
                        )
                    ],
                ),
            )

            rollout_path = root / "rollouts" / f"{thread.thread_id}.jsonl"
            lines = [
                json.loads(line)
                for line in rollout_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            context_items = lines[-1]["turn"]["reference_context_items"]
            self.assertTrue(
                any(
                    item["item_type"] == "file" and item["path"] == str(attachment_path)
                    for item in context_items
                )
            )
            self.assertTrue(any(item["source"] == "tool:read_file" for item in context_items))

    def test_append_turn_persists_top_level_rollout_causality_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ThreadStore(root)
            thread = store.start_thread(name="causality thread")
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="resume the workflow",
                    assistant_text="workflow resume requested",
                    tool_events=[
                        ToolEvent(
                            name="gateway.workflow.resume",
                            ok=True,
                            summary="resume requested",
                            payload={
                                "metadata": {
                                    "causality": {
                                        "trace_id": "trace_rollout_1",
                                        "workflow_run_id": "wf_rollout_1",
                                    }
                                }
                            },
                        )
                    ],
                ),
            )

            rollout_path = root / "rollouts" / f"{thread.thread_id}.jsonl"
            lines = [
                json.loads(line)
                for line in rollout_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            turn_line = lines[-1]
            self.assertEqual(turn_line["type"], "turn")
            self.assertEqual(turn_line["trace_id"], "trace_rollout_1")
            self.assertEqual(turn_line["workflow_run_id"], "wf_rollout_1")
            self.assertIn("turn", turn_line)

    def test_resume_thread_returns_structured_turns_rollout_items_and_context_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            attachment_path = root / "draft.md"
            attachment_path.write_text("draft", encoding="utf-8")
            store = ThreadStore(root)
            thread = store.start_thread(name="resume structured thread")
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="review draft",
                    assistant_text="Draft loaded.",
                    attachments=[PromptAttachment.from_path(str(attachment_path))],
                    tool_events=[
                        ToolEvent(
                            name="file_read",
                            ok=True,
                            summary="file loaded",
                            payload={"path": str(attachment_path)},
                        )
                    ],
                ),
            )

            resumed = store.resume_thread(thread.thread_id)

            self.assertEqual(len(resumed["rollout_items"]), 2)
            self.assertEqual(resumed["rollout_items"][0]["type"], "thread_meta")
            self.assertEqual(resumed["rollout_items"][1]["type"], "turn")
            self.assertEqual(resumed["turns"][0]["user_text"], "review draft")
            self.assertTrue(resumed["turns"][0]["reference_context_items"])
            self.assertTrue(
                any(item["path"] == str(attachment_path) for item in resumed["context_items"])
            )

    def test_resume_thread_supports_legacy_turn_payload_without_structured_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ThreadStore(root)
            thread = store.start_thread(name="legacy structured thread")
            rollout_path = root / "rollouts" / f"{thread.thread_id}.jsonl"
            with rollout_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "type": "turn",
                            "thread_id": thread.thread_id,
                            "timestamp": "2026-03-28T12:00:00+00:00",
                            "user_text": "legacy hello",
                            "assistant_text": "legacy world",
                            "assistant_history_text": "legacy world",
                            "handled_as_command": False,
                            "status": {"provider_name": "deepseek"},
                            "runtime_state": {"provider_name": "deepseek"},
                            "tool_events": [],
                            "activity_events": [],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

            resumed = store.resume_thread(thread.thread_id)

            self.assertEqual(
                resumed["history"],
                [
                    {"role": "user", "content": "legacy hello"},
                    {"role": "assistant", "content": "legacy world"},
                ],
            )
            self.assertEqual(resumed["turns"][0]["assistant_text"], "legacy world")
            self.assertEqual(resumed["turns"][0]["reference_context_items"], [])

    def test_runtime_tracks_structured_turns_and_context_items_for_active_thread(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            attachment_path = root / "memo.txt"
            attachment_path.write_text("memo", encoding="utf-8")
            store = ThreadStore(root / "state")
            runtime = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            runtime.start_thread(name="runtime structured thread")

            runtime.handle_prompt(
                "summarize memo",
                attachments=[PromptAttachment.from_path(str(attachment_path))],
            )

            self.assertEqual(len(runtime.history_turns), 1)
            self.assertEqual(runtime.history_turns[0]["user_text"], "summarize memo")
            self.assertEqual(runtime.rollout_items[-1]["type"], "turn")
            self.assertTrue(
                any(
                    item["path"] == str(attachment_path) for item in runtime.reference_context_items
                )
            )

    def test_resume_thread_compaction_replacement_history_replaces_turn_history_and_clears_context_state(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ThreadStore(root)
            thread = store.start_thread(name="compacted thread")
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="first user",
                    assistant_text="first assistant",
                    reference_context_items=[
                        ReferenceContextItem(
                            item_type="workspace_context",
                            source="runtime",
                            label="workspace_context_baseline",
                            description="workspace_reference",
                            metadata={"instructions_digest": "digest-v1"},
                        )
                    ],
                ),
                runtime_state={
                    "provider_name": "openai",
                    "workspace_context_snapshot": {"instructions_digest": "digest-v1"},
                },
            )

            rollout_path = root / "rollouts" / f"{thread.thread_id}.jsonl"
            with rollout_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "type": "compacted",
                            "thread_id": thread.thread_id,
                            "timestamp": "2026-03-28T12:30:00+00:00",
                            "message": "",
                            "replacement_history": [
                                {"role": "user", "content": "compact summary user"},
                                {"role": "assistant", "content": "compact summary assistant"},
                            ],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

            resumed = store.resume_thread(thread.thread_id)

            self.assertEqual(
                resumed["history"],
                [
                    {"role": "user", "content": "compact summary user"},
                    {"role": "assistant", "content": "compact summary assistant"},
                ],
            )
            self.assertEqual(resumed["turns"], [])
            self.assertEqual(resumed["context_items"], [])
            self.assertEqual(resumed["state"], {})

    def test_resume_thread_legacy_compaction_keeps_user_history_and_clears_context_state(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ThreadStore(root)
            thread = store.start_thread(name="legacy compacted thread")
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="before compact",
                    assistant_text="assistant reply",
                    reference_context_items=[
                        ReferenceContextItem(
                            item_type="workspace_context",
                            source="runtime",
                            label="workspace_context_baseline",
                            description="workspace_reference",
                            metadata={"instructions_digest": "digest-v1"},
                        )
                    ],
                ),
                runtime_state={"workspace_context_snapshot": {"instructions_digest": "digest-v1"}},
            )

            rollout_path = root / "rollouts" / f"{thread.thread_id}.jsonl"
            with rollout_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "type": "compacted",
                            "thread_id": thread.thread_id,
                            "timestamp": "2026-03-28T12:40:00+00:00",
                            "message": "legacy summary",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

            resumed = store.resume_thread(thread.thread_id)

            self.assertEqual(
                resumed["history"],
                [
                    {"role": "user", "content": "before compact"},
                    {"role": "user", "content": "legacy summary"},
                ],
            )
            self.assertEqual(resumed["turns"], [])
            self.assertEqual(resumed["context_items"], [])
            self.assertEqual(resumed["state"], {})

    def test_append_compacted_persists_reactive_metadata_and_rollout_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ThreadStore(root)
            thread = store.start_thread(name="reactive compacted thread")

            payload = store.append_compacted(
                thread.thread_id,
                replacement_history=[
                    {
                        "role": "assistant",
                        "content": "Previous conversation summary:\n1. user: hello\n1. assistant: hi",
                    }
                ],
                metadata={
                    "reason": "provider_context_overflow_retry",
                    "trigger_error_type": "RuntimeError",
                    "trigger_error_text": "prompt is too long for the context window",
                },
            )

            self.assertEqual(
                payload["replacement_history"],
                [
                    {
                        "role": "assistant",
                        "content": "Previous conversation summary:\n1. user: hello\n1. assistant: hi",
                    }
                ],
            )
            self.assertEqual(payload["reason"], "provider_context_overflow_retry")
            self.assertEqual(payload["trigger_error_type"], "RuntimeError")
            self.assertEqual(
                payload["trigger_error_text"], "prompt is too long for the context window"
            )

            rollout_path = root / "rollouts" / f"{thread.thread_id}.jsonl"
            lines = [
                json.loads(line)
                for line in rollout_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(lines[-1], payload)

            resumed = store.resume_thread(thread.thread_id)
            compacted_items = [
                item for item in resumed["rollout_items"] if item.get("type") == "compacted"
            ]
            self.assertEqual(compacted_items, [payload])
            described = store.describe_thread(thread.thread_id)
            self.assertEqual(
                described["preview"],
                "Previous conversation summary:\n1. user: hello\n1. assistant: hi",
            )

    def test_append_compacted_rejects_invalid_replacement_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="invalid compacted replacement history")

            with self.assertRaisesRegex(ValueError, "invalid compacted replacement history"):
                store.append_compacted(
                    thread.thread_id,
                    replacement_history=[{"type": "function_call", "name": "exec_command"}],
                )

    def test_resume_thread_rollback_removes_last_user_turn_and_restores_prior_context_state(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ThreadStore(root)
            thread = store.start_thread(name="rollback thread")
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="turn one",
                    assistant_text="assistant one",
                    reference_context_items=[
                        ReferenceContextItem(
                            item_type="workspace_context",
                            source="runtime",
                            label="workspace_context_baseline",
                            description="workspace_reference",
                            metadata={"instructions_digest": "digest-v1"},
                        )
                    ],
                ),
                runtime_state={
                    "provider_name": "openai",
                    "workspace_context_snapshot": {"instructions_digest": "digest-v1"},
                },
            )
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="turn two",
                    assistant_text="assistant two",
                    reference_context_items=[
                        ReferenceContextItem(
                            item_type="workspace_context",
                            source="runtime",
                            label="workspace_context_update",
                            description="workspace_reference",
                            metadata={"instructions_digest": "digest-v2"},
                        )
                    ],
                ),
                runtime_state={
                    "provider_name": "glm",
                    "workspace_context_snapshot": {"instructions_digest": "digest-v2"},
                },
            )

            rollout_path = root / "rollouts" / f"{thread.thread_id}.jsonl"
            with rollout_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "type": "thread_rolled_back",
                            "thread_id": thread.thread_id,
                            "timestamp": "2026-03-28T12:50:00+00:00",
                            "num_turns": 1,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

            resumed = store.resume_thread(thread.thread_id)

            self.assertEqual(
                resumed["history"],
                [
                    {"role": "user", "content": "turn one"},
                    {"role": "assistant", "content": "assistant one"},
                ],
            )
            self.assertEqual(len(resumed["turns"]), 1)
            self.assertEqual(resumed["turns"][0]["user_text"], "turn one")
            self.assertEqual(
                resumed["context_items"][0]["metadata"]["instructions_digest"],
                "digest-v1",
            )
            self.assertEqual(
                resumed["state"]["workspace_context_snapshot"]["instructions_digest"],
                "digest-v1",
            )

    def test_resume_thread_rollback_beyond_available_user_turns_clears_history_and_state(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ThreadStore(root)
            thread = store.start_thread(name="rollback overflow thread")
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="only turn",
                    assistant_text="only assistant",
                    reference_context_items=[
                        ReferenceContextItem(
                            item_type="workspace_context",
                            source="runtime",
                            label="workspace_context_baseline",
                            description="workspace_reference",
                            metadata={"instructions_digest": "digest-v1"},
                        )
                    ],
                ),
                runtime_state={"workspace_context_snapshot": {"instructions_digest": "digest-v1"}},
            )

            rollout_path = root / "rollouts" / f"{thread.thread_id}.jsonl"
            with rollout_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "type": "thread_rolled_back",
                            "thread_id": thread.thread_id,
                            "timestamp": "2026-03-28T13:00:00+00:00",
                            "num_turns": 99,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

            resumed = store.resume_thread(thread.thread_id)

            self.assertEqual(resumed["history"], [])
            self.assertEqual(resumed["turns"], [])
            self.assertEqual(resumed["context_items"], [])
            self.assertEqual(resumed["state"], {})

    def test_runtime_injects_workspace_context_from_latest_snapshot_into_structured_input_items(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").write_text("", encoding="utf-8")
            workspace_doc_path = root / "AENGTHUB.md"
            workspace_doc_path.write_text("workspace baseline", encoding="utf-8")
            agent = _RecordingAgent()
            runtime = AgentCliRuntime(agent=agent, tools=_WorkspaceTools(root))
            runtime.set_cwd(root)

            runtime.handle_prompt("first prompt")
            first_context_items = self._reference_context_inputs(agent.calls[0]["input_items"])
            self.assertEqual(len(first_context_items), 1)
            self.assertEqual(first_context_items[0]["item_type"], "workspace_context")
            self.assertEqual(first_context_items[0]["label"], "workspace_context_baseline")
            self.assertEqual(
                first_context_items[0]["metadata"]["instructions_excerpt"], "workspace baseline"
            )

            runtime.handle_prompt("second prompt")
            second_context_items = self._reference_context_inputs(agent.calls[1]["input_items"])
            self.assertEqual(second_context_items, [])

            workspace_doc_path.write_text("workspace updated", encoding="utf-8")
            runtime.handle_prompt("third prompt")
            third_context_items = self._reference_context_inputs(agent.calls[2]["input_items"])
            self.assertEqual(len(third_context_items), 1)
            self.assertEqual(third_context_items[0]["label"], "workspace_context_update")
            self.assertEqual(
                third_context_items[0]["metadata"]["instructions_excerpt"], "workspace updated"
            )

    def test_resume_thread_restores_workspace_context_snapshot_from_reference_context_item(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "repo"
            workspace.mkdir()
            (workspace / ".git").write_text("", encoding="utf-8")
            (workspace / "AENGTHUB.md").write_text("restored baseline", encoding="utf-8")
            store = ThreadStore(root / "state")
            thread = store.start_thread(
                name="workspace snapshot restore", cwd=str(workspace.resolve())
            )
            snapshot = build_workspace_reference_snapshot(workspace)
            context_item = build_workspace_reference_context_item(None, snapshot)
            self.assertIsNotNone(context_item)
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="hello",
                    assistant_text="echo: hello",
                    reference_context_items=[ReferenceContextItem.from_dict(context_item or {})],
                ),
                runtime_state={},
            )

            runtime = AgentCliRuntime(
                agent=_RecordingAgent(), tools=_WorkspaceTools(root), thread_store=store
            )
            runtime.resume_thread(thread.thread_id)

            self.assertEqual(
                runtime._workspace_context_snapshot["cwd"],
                str(workspace.resolve()).replace("\\", "/"),
            )
            self.assertEqual(
                runtime._workspace_context_snapshot["instructions_digest"],
                snapshot["instructions_digest"],
            )
            self.assertEqual(runtime.reference_context_items[-1]["item_type"], "workspace_context")

    def test_resume_thread_restores_file_read_guard_state_for_claude_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            target = workspace / "demo.txt"
            target.write_text("before\n", encoding="utf-8")
            store = ThreadStore(root / "state")

            runtime = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            runtime.set_cwd(workspace)
            thread = runtime.start_thread(name="file read guard restore")

            read_result = runtime.tools.read_file_result("demo.txt", offset=1, limit=20)
            self.assertTrue(read_result.tool_events[-1].ok)
            self.assertTrue(runtime.tools._file_read_state)

            store.append_turn(
                thread["thread_id"],
                PromptResponse(
                    user_text="read demo",
                    assistant_text="loaded demo",
                    tool_events=list(read_result.tool_events),
                ),
                runtime_state=runtime._snapshot_thread_state(),
            )

            resumed_runtime = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            resumed = resumed_runtime.resume_thread(thread["thread_id"])
            restored_state = dict(getattr(resumed_runtime.tools, "_file_read_state", {}) or {})
            self.assertTrue(restored_state)
            self.assertEqual(resumed["state"]["file_read_guard_state"], restored_state)
            resumed_runtime.configure_runtime_policy(approval_policy="never")

            patch_text = json.dumps(
                {
                    "operation": "file_write",
                    "file_path": "demo.txt",
                    "content": "after\n",
                    "source_tool_name": "Write",
                    "guard_profile": "claude_write",
                }
            )

            result = resumed_runtime.tools.apply_patch_result(patch_text)
            self.assertTrue(result.tool_events[-1].ok)
            self.assertEqual(target.read_text(encoding="utf-8"), "after\n")

    def test_resume_thread_restores_file_read_guard_state_for_stale_after_read_rejection(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            target = workspace / "demo.txt"
            target.write_text("Status: TODO\n", encoding="utf-8")
            store = ThreadStore(root / "state")

            runtime = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            runtime.set_cwd(workspace)
            thread = runtime.start_thread(name="file read stale restore")

            read_result = runtime.tools.read_file_result("demo.txt", offset=1, limit=20)
            self.assertTrue(read_result.tool_events[-1].ok)

            store.append_turn(
                thread["thread_id"],
                PromptResponse(
                    user_text="read demo",
                    assistant_text="loaded demo",
                    tool_events=list(read_result.tool_events),
                ),
                runtime_state=runtime._snapshot_thread_state(),
            )
            target.write_text("Status: external\n", encoding="utf-8")

            resumed_runtime = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            resumed_runtime.resume_thread(thread["thread_id"])

            patch_text = json.dumps(
                {
                    "operation": "file_edit",
                    "file_path": "demo.txt",
                    "old_string": "TODO",
                    "new_string": "DONE",
                    "source_tool_name": "Edit",
                    "guard_profile": "claude_edit",
                }
            )

            blocked = resumed_runtime.tools.apply_patch_result(patch_text)
            self.assertFalse(blocked.tool_events[-1].ok)
            self.assertEqual(
                blocked.tool_events[-1].payload.get("guard_failure"),
                "stale_after_read",
            )
            self.assertIn(
                "changed since it was read",
                str(blocked.tool_events[-1].payload.get("error") or ""),
            )
            self.assertEqual(target.read_text(encoding="utf-8"), "Status: external\n")

    def test_workspace_context_baseline_and_diff_are_injected_and_restored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            (workspace / ".git").write_text("", encoding="utf-8")
            workspace_doc_path = workspace / "AENGTHUB.md"
            workspace_doc_path.write_text("workspace rule v1", encoding="utf-8")
            store = ThreadStore(root / "state")

            agent1 = _RecordingAgent()
            runtime1 = AgentCliRuntime(
                agent=agent1,
                tools=_WorkspaceTools(workspace),
                thread_store=store,
            )
            runtime1.set_cwd(workspace)
            thread = runtime1.start_thread(name="workspace context thread")

            runtime1.handle_prompt("first turn")
            baseline_items = self._reference_context_inputs(agent1.calls[0]["input_items"])
            self.assertEqual(len(baseline_items), 1)
            self.assertEqual(baseline_items[0]["label"], "workspace_context_baseline")
            self.assertEqual(
                baseline_items[0]["metadata"]["instructions_excerpt"], "workspace rule v1"
            )
            self.assertEqual(len(runtime1._context_update_history), 1)

            runtime1.handle_prompt("second turn")
            stable_items = self._reference_context_inputs(agent1.calls[1]["input_items"])
            self.assertEqual(stable_items, [])

            workspace_doc_path.write_text("workspace rule v2", encoding="utf-8")
            runtime1.handle_prompt("third turn")
            changed_items = self._reference_context_inputs(agent1.calls[2]["input_items"])
            self.assertEqual(len(changed_items), 1)
            self.assertEqual(changed_items[0]["label"], "workspace_context_update")
            self.assertEqual(
                changed_items[0]["metadata"]["instructions_excerpt"], "workspace rule v2"
            )
            self.assertTrue(
                any(
                    item.get("item_type") == "workspace_context"
                    for item in runtime1.reference_context_items
                )
            )

            runtime1.handle_prompt("fourth turn")
            stable_baseline_items = self._reference_context_inputs(agent1.calls[3]["input_items"])
            self.assertEqual(stable_baseline_items, [])

            runtime2 = AgentCliRuntime(
                agent=_RecordingAgent(),
                tools=_WorkspaceTools(workspace),
                thread_store=store,
            )
            resumed = runtime2.resume_thread(thread["thread_id"])
            self.assertTrue(
                any(
                    item.get("item_type") == "workspace_context"
                    for item in resumed["context_items"]
                )
            )
            self.assertEqual(
                runtime2._workspace_context_snapshot.get("instructions_digest"),
                runtime1._workspace_context_snapshot.get("instructions_digest"),
            )
            self.assertGreaterEqual(len(runtime2._context_update_history), 1)

            runtime2.handle_prompt("resumed steady turn")
            resumed_context_items = self._reference_context_inputs(
                runtime2.agent.calls[0]["input_items"]
            )
            self.assertEqual(resumed_context_items, [])

    def test_auto_compaction_clears_context_baseline_and_reinjects_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            (workspace / ".git").write_text("", encoding="utf-8")
            (workspace / "AENGTHUB.md").write_text("workspace compact rule", encoding="utf-8")
            store = ThreadStore(root / "state")
            agent = _RecordingAgent()
            runtime = AgentCliRuntime(
                agent=agent,
                tools=_WorkspaceTools(workspace),
                thread_store=store,
            )
            runtime.set_cwd(workspace)
            runtime._AUTO_COMPACT_TRIGGER_ITEMS = 1
            thread = runtime.start_thread(name="auto compact thread")

            runtime.handle_prompt("first turn")
            self.assertEqual(len(self._reference_context_inputs(agent.calls[0]["input_items"])), 1)

            runtime.handle_prompt("second turn")
            second_context_items = self._reference_context_inputs(agent.calls[1]["input_items"])
            self.assertEqual(len(second_context_items), 1)
            self.assertEqual(second_context_items[0]["label"], "workspace_context_baseline")
            self.assertTrue(
                any(
                    str(item.get("type") or "").strip() == "compacted"
                    for item in runtime.rollout_items
                )
            )
            self.assertTrue(runtime._base_history)

            runtime._AUTO_COMPACT_TRIGGER_ITEMS = 100
            runtime.handle_prompt("third turn")
            third_context_items = self._reference_context_inputs(agent.calls[2]["input_items"])
            self.assertEqual(third_context_items, [])

            resumed_runtime = AgentCliRuntime(
                agent=_RecordingAgent(),
                tools=_WorkspaceTools(workspace),
                thread_store=store,
            )
            resumed_runtime.resume_thread(thread["thread_id"])
            self.assertTrue(resumed_runtime._base_history)

    def test_manual_compact_command_replaces_history_and_records_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ThreadStore(root / "state")
            runtime = AgentCliRuntime(
                agent=_RecordingAgent(),
                tools=_WorkspaceTools(root),
                thread_store=store,
            )
            runtime.start_thread(name="manual compact thread")
            runtime.handle_prompt("first turn")

            result = runtime._run_command_text_result("/compact keep recent failures")

            self.assertIn("Context compacted.", result.assistant_text)
            self.assertEqual(runtime.history_turns, [])
            self.assertTrue(runtime._base_history)
            compacted = [
                item for item in runtime.rollout_items if str(item.get("type") or "") == "compacted"
            ]
            self.assertEqual(len(compacted), 1)
            self.assertEqual(compacted[0]["reason"], "manual_compact")
            self.assertEqual(compacted[0]["trigger"], "manual")
            self.assertEqual(compacted[0]["instructions"], "keep recent failures")
            self.assertEqual(
                compacted[0]["replacement_history"],
                [
                    {
                        "role": "assistant",
                        "content": "Previous conversation summary:\n1. user: first turn\n1. assistant: echo: first turn",
                    }
                ],
            )

    def test_manual_compact_command_noops_without_provider_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = AgentCliRuntime(
                agent=_RecordingAgent(),
                tools=_WorkspaceTools(root),
                thread_store=ThreadStore(root / "state"),
            )
            runtime.start_thread(name="manual compact empty thread")

            result = runtime._run_command_text_result("/compact")

            self.assertIn("Not enough provider conversation history", result.assistant_text)
            self.assertEqual(len(result.tool_events), 1)
            self.assertTrue(result.tool_events[0].ok)
            self.assertEqual(result.tool_events[0].payload.get("reason"), "not_enough_history")
            self.assertFalse(any(item.get("type") == "compacted" for item in runtime.rollout_items))

    def test_runtime_persists_turn_context_rollout_items_without_changing_resumed_history(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            (workspace / ".git").write_text("", encoding="utf-8")
            (workspace / "AENGTHUB.md").write_text("workspace rule v1", encoding="utf-8")
            store = ThreadStore(root / "state")

            agent1 = _RecordingAgent()
            runtime1 = AgentCliRuntime(
                agent=agent1,
                tools=_WorkspaceTools(workspace),
                thread_store=store,
            )
            runtime1.set_cwd(workspace)
            thread = runtime1.start_thread(name="turn context rollout thread")

            runtime1.handle_prompt("first turn")

            turn_context_items = [
                item for item in runtime1.rollout_items if item.get("type") == "turn_context"
            ]
            self.assertEqual(len(turn_context_items), 1)
            self.assertEqual(turn_context_items[0].get("scope"), "turn_context")
            self.assertEqual(turn_context_items[0].get("cwd"), str(workspace.resolve()))
            self.assertEqual(
                turn_context_items[0].get("approval_policy"),
                runtime1.runtime_policy.approval_policy,
            )
            self.assertEqual(
                turn_context_items[0].get("sandbox_mode"), runtime1.runtime_policy.sandbox_mode
            )
            self.assertEqual(turn_context_items[0].get("model"), "deepseek-reasoner")
            environment_items = [
                item
                for item in list(turn_context_items[0].get("items") or [])
                if str(item.get("source") or "").strip() == "environment_context"
            ]
            workspace_items = [
                item
                for item in list(turn_context_items[0].get("items") or [])
                if str(item.get("source") or "").strip() == "workspace_context"
            ]
            self.assertTrue(environment_items)
            self.assertEqual(workspace_items, [])
            self.assertTrue(turn_context_items[0].get("reference_context_items"))

            runtime2 = AgentCliRuntime(
                agent=_RecordingAgent(),
                tools=_WorkspaceTools(workspace),
                thread_store=store,
            )
            resumed = runtime2.resume_thread(thread["thread_id"])

            self.assertEqual(
                resumed["history"],
                [
                    {"role": "user", "content": "first turn"},
                    {"role": "assistant", "content": "echo: first turn"},
                ],
            )
            self.assertTrue(
                any(item.get("type") == "turn_context" for item in resumed["rollout_items"])
            )

    def test_runtime_command_path_prefers_item_events_when_turn_events_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            runtime = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            runtime.start_thread(name="command item events")

            def _fake_run_command_text_result(text: str) -> CommandExecutionResult:
                self.assertEqual(text, "/file_list .")
                return CommandExecutionResult(
                    assistant_text="listed files",
                    tool_events=[
                        ToolEvent(
                            name="file_list",
                            ok=True,
                            summary="files=1",
                            payload={"path": "."},
                        )
                    ],
                    item_events=[
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "item_0",
                                "type": "command_execution",
                                "command": "/file_list .",
                                "aggregated_output": "README.md",
                                "exit_code": 0,
                                "status": "completed",
                            },
                        }
                    ],
                    turn_events=[],
                )

            runtime._run_command_text_result = _fake_run_command_text_result  # type: ignore[assignment]
            response = runtime.handle_prompt("/file_list .")

            command_items = [
                dict(event.get("item") or {})
                for event in list(response.turn_events or [])
                if event.get("type") == "item.completed"
                and isinstance(event.get("item"), dict)
                and str(event["item"].get("type") or "").strip() == "command_execution"
            ]
            self.assertTrue(command_items)
            self.assertEqual(command_items[0]["command"], "/file_list .")

    def test_runtime_resume_planner_input_prefers_canonical_turn_event_message_for_structured_turn(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="runtime canonical planner input")
            response = PromptResponse(
                user_text="list files",
                commentary_text="",
                assistant_text="legacy fallback",
                response_items=default_response_items(assistant_text="stale final"),
                tool_events=[
                    ToolEvent(
                        name="file_list",
                        ok=True,
                        summary="file_list ok: files=3",
                        payload={"path": "."},
                    )
                ],
            )
            response.turn_events = [
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_0",
                        "type": "command_execution",
                        "command": "/file_list .",
                        "aggregated_output": "files=3",
                        "exit_code": 0,
                        "status": "completed",
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_1",
                        "type": "agent_message",
                        "text": "canonical final",
                    },
                },
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
                },
            ]
            store.append_turn(thread.thread_id, response)

            agent = _RecordingAgent()
            runtime = AgentCliRuntime(agent=agent, thread_store=store)
            runtime.resume_thread(thread.thread_id)
            runtime.handle_prompt("follow up")

            self.assertTrue(
                self._input_items_contain_text(agent.calls[0]["input_items"], "canonical final")
            )
            self.assertFalse(
                self._input_items_contain_text(agent.calls[0]["input_items"], "stale final")
            )

    def test_runtime_injects_environment_context_and_restores_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            (workspace / ".git").write_text("", encoding="utf-8")
            store = ThreadStore(root / "state")

            agent1 = _RecordingAgent()
            runtime1 = AgentCliRuntime(
                agent=agent1,
                tools=_WorkspaceTools(workspace),
                thread_store=store,
            )
            runtime1.set_cwd(workspace)
            thread = runtime1.start_thread(name="environment context thread")

            runtime1.handle_prompt("first env turn")
            env_messages = [
                str(item.get("content") or "")
                for item in agent1.calls[0]["input_items"]
                if "<environment_context>" in str(item.get("content") or "")
            ]
            self.assertEqual(len(env_messages), 1)
            self.assertIn(f"<cwd>{str(workspace.resolve())}</cwd>", env_messages[0])
            self.assertIn("<shell>", env_messages[0])
            self.assertIn("<current_date>", env_messages[0])
            self.assertIn("<timezone>", env_messages[0])

            runtime2 = AgentCliRuntime(
                agent=_RecordingAgent(),
                tools=_WorkspaceTools(workspace),
                thread_store=store,
            )
            resumed = runtime2.resume_thread(thread["thread_id"])
            self.assertIn("environment_context_snapshot", resumed["state"])
            self.assertIn("environment_context_history", resumed["state"])
            self.assertEqual(
                runtime2._environment_context_snapshot.get("cwd"),
                str(workspace.resolve()),
            )

    def test_resume_thread_restores_turn_context_histories_from_scoped_rollout_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            (workspace / ".git").write_text("", encoding="utf-8")
            store = ThreadStore(root / "state")
            thread = store.start_thread(name="scoped context restore", cwd=str(workspace.resolve()))
            store.append_rollout_items(
                thread.thread_id,
                [
                    {
                        "type": "response_item",
                        "scope": "turn_context",
                        "source": "environment_context",
                        "item": {
                            "role": "user",
                            "content": "<environment_context>\n<cwd>x</cwd>\n</environment_context>",
                        },
                    },
                    {
                        "type": "response_item",
                        "scope": "turn_context",
                        "source": "workspace_context",
                        "item": {
                            "role": "user",
                            "content": "REFERENCE_CONTEXT_BASELINE:\nworkspace baseline",
                        },
                    },
                    {
                        "type": "state_snapshot",
                        "scope": "turn_context",
                        "state": {
                            "environment_context_snapshot": {"cwd": str(workspace.resolve())},
                            "workspace_context_snapshot": {"instructions_digest": "digest-scoped"},
                        },
                    },
                ],
            )

            runtime = AgentCliRuntime(
                agent=_RecordingAgent(), tools=_WorkspaceTools(workspace), thread_store=store
            )
            runtime.resume_thread(thread.thread_id)

            self.assertEqual(len(runtime._environment_context_history), 1)
            self.assertIn(
                "<environment_context>", runtime._environment_context_history[0]["content"]
            )
            self.assertEqual(len(runtime._context_update_history), 1)
            self.assertIn(
                "REFERENCE_CONTEXT_BASELINE:", runtime._context_update_history[0]["content"]
            )
            self.assertEqual(
                runtime._workspace_context_snapshot["instructions_digest"], "digest-scoped"
            )

    def test_resume_thread_restores_turn_context_histories_from_compound_turn_context_rollout_item(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            (workspace / ".git").write_text("", encoding="utf-8")
            store = ThreadStore(root / "state")
            thread = store.start_thread(
                name="compound context restore", cwd=str(workspace.resolve())
            )
            store.append_rollout_items(
                thread.thread_id,
                [
                    {
                        "type": "turn_context",
                        "scope": "turn_context",
                        "cwd": str(workspace.resolve()),
                        "approval_policy": "on-request",
                        "sandbox_mode": "workspace-write",
                        "model": "gpt-5.4",
                        "items": [
                            {
                                "source": "environment_context",
                                "item": {
                                    "type": "message",
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "input_text",
                                            "text": "<environment_context>\n<cwd>x</cwd>\n</environment_context>",
                                        }
                                    ],
                                },
                            },
                            {
                                "source": "workspace_context",
                                "item": {
                                    "type": "message",
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "input_text",
                                            "text": "REFERENCE_CONTEXT_BASELINE:\nworkspace baseline",
                                        }
                                    ],
                                },
                            },
                        ],
                        "state": {
                            "environment_context_snapshot": {"cwd": str(workspace.resolve())},
                            "workspace_context_snapshot": {
                                "instructions_digest": "digest-turn-context"
                            },
                        },
                    }
                ],
            )

            runtime = AgentCliRuntime(
                agent=_RecordingAgent(), tools=_WorkspaceTools(workspace), thread_store=store
            )
            runtime.resume_thread(thread.thread_id)

            self.assertEqual(len(runtime._environment_context_history), 1)
            self.assertIn(
                "<environment_context>", runtime._environment_context_history[0]["content"]
            )
            self.assertEqual(len(runtime._context_update_history), 1)
            self.assertIn(
                "REFERENCE_CONTEXT_BASELINE:", runtime._context_update_history[0]["content"]
            )
            self.assertEqual(
                runtime._workspace_context_snapshot["instructions_digest"], "digest-turn-context"
            )

    def test_resume_thread_restores_workspace_snapshot_from_scoped_context_item_fallback(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            (workspace / ".git").write_text("", encoding="utf-8")
            store = ThreadStore(root / "state")
            thread = store.start_thread(
                name="scoped context item fallback", cwd=str(workspace.resolve())
            )
            snapshot = build_workspace_reference_snapshot(workspace)
            context_item = build_workspace_reference_context_item(None, snapshot)
            self.assertIsNotNone(context_item)
            store.append_rollout_items(
                thread.thread_id,
                [
                    {
                        "type": "reference_context_item",
                        "scope": "turn_context",
                        "item": context_item,
                    }
                ],
            )

            runtime = AgentCliRuntime(
                agent=_RecordingAgent(), tools=_WorkspaceTools(workspace), thread_store=store
            )
            runtime.resume_thread(thread.thread_id)

            self.assertEqual(
                runtime._workspace_context_snapshot["instructions_digest"],
                snapshot["instructions_digest"],
            )
            self.assertEqual(
                runtime._workspace_context_snapshot["cwd"],
                str(workspace.resolve()).replace("\\", "/"),
            )

    def test_runtime_without_thread_store_keeps_canonical_turn_history_for_structured_planner(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            (workspace / ".git").write_text("", encoding="utf-8")

            agent = _RecordingAgent()
            runtime = AgentCliRuntime(agent=agent, tools=_WorkspaceTools(workspace))
            runtime.set_cwd(workspace)

            runtime.handle_prompt("first local turn")
            self.assertEqual(len(runtime.history_turns), 1)

            runtime.history = []
            runtime.handle_prompt("second local turn")

            self.assertEqual(agent.calls[1]["history"], [])
            self.assertTrue(
                self._input_items_contain_text(agent.calls[1]["input_items"], "first local turn")
            )
            self.assertTrue(
                self._input_items_contain_text(
                    agent.calls[1]["input_items"], "echo: first local turn"
                )
            )

    def test_runtime_without_thread_store_keeps_canonical_turn_history_for_legacy_planner(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            (workspace / ".git").write_text("", encoding="utf-8")

            agent = _LegacyHistoryAgent()
            runtime = AgentCliRuntime(agent=agent, tools=_WorkspaceTools(workspace))
            runtime.set_cwd(workspace)

            runtime.handle_prompt("first local turn")
            self.assertEqual(len(runtime.history_turns), 1)

            runtime.history = []
            runtime.handle_prompt("second local turn")

            self.assertTrue(
                self._history_contains_text(agent.calls[1]["history"], "first local turn")
            )
            self.assertTrue(
                self._history_contains_text(agent.calls[1]["history"], "echo: first local turn")
            )

    def test_runtime_resume_compaction_keeps_later_structured_turn_continuation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="compaction structured continuation")
            store.append_compacted(
                thread.thread_id,
                replacement_history=[{"role": "assistant", "content": "summary only"}],
            )
            store.append_turn(
                thread.thread_id,
                PromptResponse(
                    user_text="执行 pwd 并告诉我结果。",
                    assistant_text="当前目录是 /repo。",
                    response_items=default_response_items(assistant_text="当前目录是 /repo。"),
                    tool_events=[self._successful_exec_command_tool_event()],
                ),
            )

            agent = _RecordingAgent()
            runtime = AgentCliRuntime(agent=agent, thread_store=store)
            runtime.resume_thread(thread.thread_id)
            runtime.handle_prompt("下一轮继续")

            self.assertTrue(
                self._input_items_contain_text(agent.calls[0]["input_items"], "summary only")
            )
            function_calls = self._function_call_items(agent.calls[0]["input_items"])
            function_outputs = self._function_call_output_items(agent.calls[0]["input_items"])
            self.assertEqual(len(function_calls), 1)
            self.assertEqual(function_calls[0]["call_id"], "call_exec_ok_1")
            self.assertEqual(len(function_outputs), 1)
            self.assertEqual(function_outputs[0]["call_id"], "call_exec_ok_1")

    def test_thread_store_assistant_history_text_excludes_reasoning_response_items(self) -> None:
        response = PromptResponse(
            user_text="read file",
            assistant_text="final answer",
            response_items=[
                ResponseInputItem.from_dict(
                    {
                        "type": "reasoning",
                        "content": [{"type": "reasoning", "text": "internal reasoning"}],
                    }
                ),
                ResponseInputItem.from_dict(
                    {
                        "type": "message",
                        "role": "assistant",
                        "phase": "final_answer",
                        "content": [{"type": "output_text", "text": "final answer"}],
                    }
                ),
            ],
        )

        self.assertEqual(ThreadStore._assistant_history_text(response), "final answer")

    def test_thread_fork_source_inputs_excludes_thread_meta_and_rewrites_source_thread(
        self,
    ) -> None:
        source_thread, rollout_items, history = fork_source_inputs(
            {
                "thread": {"thread_id": "source"},
                "rollout_items": [
                    {
                        "item_type": "thread_meta",
                        "thread_id": "source",
                        "metadata": {"provider_status": {"provider_name": "openai"}},
                    },
                    {
                        "item_type": "response_item",
                        "thread_id": "source",
                        "item": {"type": "message", "role": "user", "content": "hello"},
                    },
                ],
                "planner_input_items": [{"type": "message", "role": "user", "content": "fallback"}],
            }
        )

        self.assertEqual(source_thread["thread_id"], "source")
        self.assertEqual(len(rollout_items), 1)
        self.assertEqual(rollout_items[0]["item_type"], "response_item")
        self.assertEqual(rollout_items[0]["thread_id"], "")
        self.assertEqual(history, [{"type": "message", "role": "user", "content": "fallback"}])

    def test_thread_fork_source_inputs_falls_back_to_validated_history(self) -> None:
        _source_thread, rollout_items, history = fork_source_inputs(
            {
                "thread": {"thread_id": "source"},
                "history": [{"type": "message", "role": "user", "content": "seed"}],
            },
            validate_history=True,
        )

        self.assertEqual(rollout_items, [])
        self.assertEqual(history, [{"type": "message", "role": "user", "content": "seed"}])

    def test_thread_fork_source_inputs_rejects_invalid_history_fallback(self) -> None:
        with self.assertRaisesRegex(ValueError, "history\\[0\\]: type is required"):
            fork_source_inputs(
                {
                    "thread": {"thread_id": "source"},
                    "history": [{"role": "user", "content": "missing type"}],
                },
                validate_history=True,
            )

    def test_thread_fork_source_inputs_can_keep_legacy_bare_role_history(self) -> None:
        _source_thread, rollout_items, history = fork_source_inputs(
            {
                "thread": {"thread_id": "source"},
                "history": [{"role": "user", "content": "legacy seed"}],
            }
        )

        self.assertEqual(rollout_items, [])
        self.assertEqual(history, [{"role": "user", "content": "legacy seed"}])

    def test_resume_payload_preserving_active_thread_restores_previous_active(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            first = store.start_thread(name="first")
            second = store.start_thread(name="second")
            store.set_active_thread_id(first.thread_id)

            payload = resume_payload_preserving_active_thread(
                store,
                thread_id=second.thread_id,
            )

            self.assertEqual(payload["thread"]["thread_id"], second.thread_id)
            self.assertEqual(store.get_active_thread_id(), first.thread_id)

    def test_resume_payload_preserving_active_thread_restores_missing_active(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            thread = store.start_thread(name="only")
            with store._lock, store._connection() as conn:
                conn.execute("DELETE FROM settings WHERE key = 'active_thread_id'")
                conn.commit()

            resume_payload_preserving_active_thread(store, thread_id=thread.thread_id)

            self.assertIsNone(store.get_active_thread_id())

    def test_fork_thread_record_copies_rollout_items_and_rewrites_thread_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            source = store.start_thread(
                name="source",
                provider_status={"provider_name": "openai", "provider_model": "gpt-x"},
                runtime_policy_status={"approval_policy": "never"},
            )
            store.append_rollout_items(
                source.thread_id,
                [
                    {
                        "item_type": "response_item",
                        "item": {
                            "type": "message",
                            "role": "user",
                            "content": "hello fork",
                        },
                    }
                ],
            )
            store.set_active_thread_id(source.thread_id)

            result = fork_thread_record(
                thread_store=store,
                source_thread_id=source.thread_id,
                provider_status={"provider_name": "fallback"},
                runtime_policy_status={"approval_policy": "on-request"},
            )
            fork_thread_id = result["thread_id"]
            loaded = store.resume_thread(fork_thread_id)
            copied_items = [
                item for item in loaded["rollout_items"] if item.get("item_type") != "thread_meta"
            ]

            self.assertNotEqual(fork_thread_id, source.thread_id)
            self.assertEqual(result["created_from"], "rollout")
            self.assertTrue(copied_items)
            self.assertTrue(all(item["thread_id"] == fork_thread_id for item in copied_items))
            self.assertTrue(
                any("hello fork" in str(item.get("item") or {}) for item in copied_items)
            )

    def test_fork_thread_record_falls_back_to_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))

            result = fork_thread_record(
                thread_store=store,
                source_payload={
                    "thread": {
                        "thread_id": "virtual-source",
                        "cwd": str(Path(temp_dir)),
                        "metadata": {
                            "provider_status": {"provider_name": "source-provider"},
                            "runtime_policy": {"approval_policy": "never"},
                        },
                    },
                    "history": [
                        {"type": "message", "role": "user", "content": "history seed"},
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": "history answer",
                        },
                    ],
                },
            )
            runtime = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            runtime.resume_thread(result["thread_id"])

            self.assertEqual(result["created_from"], "history")
            self.assertEqual(
                [item.get("role") for item in runtime.history],
                ["user", "assistant"],
            )
            self.assertTrue(
                any("history seed" in str(item) for item in runtime._planner_input_items)
            )
            self.assertEqual(result["provider_status"]["provider_name"], "source-provider")

    def test_fork_thread_record_accepts_legacy_bare_role_history_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))

            result = fork_thread_record(
                thread_store=store,
                source_payload={
                    "thread": {"thread_id": "virtual-source"},
                    "history": [{"role": "user", "content": "legacy seed"}],
                },
            )
            runtime = AgentCliRuntime(agent=_RecordingAgent(), thread_store=store)
            runtime.resume_thread(result["thread_id"])

            self.assertEqual(result["created_from"], "history")
            self.assertEqual(runtime.history, [{"role": "user", "content": "legacy seed"}])

    def test_fork_thread_record_can_validate_history_fallback_for_app_server(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))

            with self.assertRaisesRegex(ValueError, "history\\[0\\]: type is required"):
                fork_thread_record(
                    thread_store=store,
                    source_payload={
                        "thread": {"thread_id": "virtual-source"},
                        "history": [{"role": "user", "content": "legacy seed"}],
                    },
                    validate_history=True,
                )

    def test_fork_thread_record_raises_when_source_has_no_material(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))

            with self.assertRaisesRegex(ValueError, "no rollout found"):
                fork_thread_record(
                    thread_store=store,
                    source_payload={"thread": {"thread_id": "empty-source"}},
                )
