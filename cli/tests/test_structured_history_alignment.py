import json
import tempfile
import unittest
from pathlib import Path

from cli.agent_cli.models import AgentIntent
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.thread_store import ThreadStore


class _RecordingAgent:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def provider_status(self):
        return {
            "provider_ready": "true",
            "provider_name": "openai",
            "model_key": "gpt_54",
            "provider_planner": "openai_responses",
            "provider_model": "gpt-5.4",
            "provider_tools": "tool-calls",
            "session_line": "openai-tools",
            "provider_label": "openai | gpt-5.4 | tool-calls",
            "provider_base_url": "https://relay05.relay.example/reference/v1",
            "provider_source": "test",
            "provider_config_path": "/tmp/config.toml",
            "provider_auth_path": "/tmp/auth.json",
            "platform_family": "unix",
            "platform_os": "linux",
            "shell_kind": "bash",
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


class _WorkspaceTools:
    def __init__(self, root: Path) -> None:
        self.PROJECT_ROOT = str(root)

    def set_workspace_root(self, path) -> Path:
        resolved = Path(path).resolve()
        self.PROJECT_ROOT = str(resolved)
        return resolved


class StructuredHistoryAlignmentTest(unittest.TestCase):
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
    def _input_item_texts(items: list[dict]) -> list[str]:
        texts: list[str] = []
        for item in list(items or []):
            content = item.get("content")
            if isinstance(content, str):
                if content.strip():
                    texts.append(content.strip())
                continue
            if not isinstance(content, list):
                continue
            parts = [
                str(entry.get("text") or "").strip()
                for entry in content
                if isinstance(entry, dict) and str(entry.get("text") or "").strip()
            ]
            if parts:
                texts.append("\n".join(parts))
        return texts

    @staticmethod
    def _input_item_types(items: list[dict]) -> list[str]:
        return [str(item.get("type") or "") for item in list(items or []) if isinstance(item, dict)]

    def _append_line(self, root: Path, thread_id: str, payload: dict) -> None:
        rollout_path = root / "state" / "rollouts" / f"{thread_id}.jsonl"
        with rollout_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def test_resume_thread_supports_structured_response_items_context_items_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / ".git").write_text("", encoding="utf-8")
            store = ThreadStore(root / "state")
            thread = store.start_thread(name="structured resume", cwd=str(workspace.resolve()))

            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "response_item",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T05:00:00+00:00",
                    "role": "user",
                    "content": "seed user",
                },
            )
            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "response_item",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T05:00:01+00:00",
                    "role": "assistant",
                    "content": "seed assistant",
                },
            )
            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "reference_context_item",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T05:00:02+00:00",
                    "item": {
                        "item_type": "workspace_context",
                        "source": "test",
                        "label": "workspace",
                        "path": str(workspace.resolve()),
                        "description": "workspace",
                        "metadata": {
                            "instructions_digest": "digest-1",
                            "docs": [],
                            "skills": [],
                            "trust_level": "trusted",
                        },
                    },
                },
            )
            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "state_snapshot",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T05:00:03+00:00",
                    "state": {
                        "workspace_context_snapshot": {
                            "cwd": str(workspace.resolve()).replace("\\", "/"),
                            "instructions_digest": "digest-1",
                            "docs": [],
                            "skills": [],
                        },
                        "provider_name": "openai",
                    },
                },
            )

            resumed = store.resume_thread(thread.thread_id)

            self.assertEqual(
                resumed["history"],
                [
                    {"role": "user", "content": "seed user"},
                    {"role": "assistant", "content": "seed assistant"},
                ],
            )
            self.assertEqual(len(resumed["context_items"]), 1)
            self.assertEqual(resumed["context_items"][0]["item_type"], "workspace_context")
            self.assertEqual(
                resumed["state"]["workspace_context_snapshot"]["instructions_digest"],
                "digest-1",
            )

    def test_runtime_resume_uses_structured_history_for_next_planner_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / ".git").write_text("", encoding="utf-8")
            store = ThreadStore(root / "state")
            thread = store.start_thread(name="structured runtime", cwd=str(workspace.resolve()))

            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "response_item",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T06:00:00+00:00",
                    "role": "user",
                    "content": "previous user",
                },
            )
            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "response_item",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T06:00:01+00:00",
                    "role": "assistant",
                    "content": "previous assistant",
                },
            )

            agent = _RecordingAgent()
            runtime = AgentCliRuntime(
                agent=agent, tools=_WorkspaceTools(workspace), thread_store=store
            )
            runtime.resume_thread(thread.thread_id)
            runtime.handle_prompt("follow up")

            self.assertEqual(agent.calls[0]["text"], "follow up")
            self.assertEqual(agent.calls[0]["history"], [])
            self.assertTrue(
                self._input_items_contain_text(agent.calls[0]["input_items"], "previous user")
            )
            self.assertTrue(
                self._input_items_contain_text(agent.calls[0]["input_items"], "previous assistant")
            )

    def test_compaction_clears_structured_history_and_context_until_reestablished(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / ".git").write_text("", encoding="utf-8")
            store = ThreadStore(root / "state")
            thread = store.start_thread(name="structured compaction", cwd=str(workspace.resolve()))

            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "response_item",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T07:00:00+00:00",
                    "role": "user",
                    "content": "old user",
                },
            )
            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "reference_context_item",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T07:00:01+00:00",
                    "item": {
                        "item_type": "workspace_context",
                        "source": "test",
                        "label": "old",
                        "path": str(workspace.resolve()),
                        "metadata": {"instructions_digest": "digest-old"},
                    },
                },
            )
            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "compacted",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T07:00:02+00:00",
                },
            )
            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "response_item",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T07:00:03+00:00",
                    "role": "assistant",
                    "content": "summary",
                },
            )
            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "reference_context_item",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T07:00:04+00:00",
                    "item": {
                        "item_type": "workspace_context",
                        "source": "test",
                        "label": "new",
                        "path": str(workspace.resolve()),
                        "metadata": {"instructions_digest": "digest-new"},
                    },
                },
            )
            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "state_snapshot",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T07:00:05+00:00",
                    "state": {"workspace_context_snapshot": {"instructions_digest": "digest-new"}},
                },
            )

            resumed = store.resume_thread(thread.thread_id)

            self.assertEqual(resumed["history"], [{"role": "assistant", "content": "summary"}])
            self.assertEqual(len(resumed["context_items"]), 1)
            self.assertEqual(
                resumed["context_items"][0]["metadata"]["instructions_digest"], "digest-new"
            )
            self.assertEqual(
                resumed["state"]["workspace_context_snapshot"]["instructions_digest"],
                "digest-new",
            )

    def test_runtime_resume_keeps_compaction_base_history_before_later_turns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / ".git").write_text("", encoding="utf-8")
            store = ThreadStore(root / "state")
            thread = store.start_thread(
                name="compaction base history", cwd=str(workspace.resolve())
            )

            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "compacted",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T08:00:00+00:00",
                    "replacement_history": [{"role": "assistant", "content": "summary only"}],
                },
            )
            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "response_item",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T08:00:01+00:00",
                    "role": "user",
                    "content": "follow-up user",
                },
            )
            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "response_item",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T08:00:02+00:00",
                    "role": "assistant",
                    "content": "follow-up assistant",
                },
            )

            agent = _RecordingAgent()
            runtime = AgentCliRuntime(
                agent=agent, tools=_WorkspaceTools(workspace), thread_store=store
            )
            runtime.resume_thread(thread.thread_id)
            runtime.handle_prompt("next turn")

            self.assertTrue(
                self._input_items_contain_text(agent.calls[0]["input_items"], "summary only")
            )
            self.assertTrue(
                self._input_items_contain_text(agent.calls[0]["input_items"], "follow-up user")
            )
            self.assertTrue(
                self._input_items_contain_text(agent.calls[0]["input_items"], "follow-up assistant")
            )

    def test_resume_thread_turn_context_history_replays_before_next_planner_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / ".git").write_text("", encoding="utf-8")
            store = ThreadStore(root / "state")
            thread = store.start_thread(
                name="structured turn context", cwd=str(workspace.resolve())
            )

            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "response_item",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T08:00:00+00:00",
                    "scope": "turn_context",
                    "source": "workspace_context",
                    "item": {
                        "role": "user",
                        "content": "REFERENCE_CONTEXT_BASELINE: restored scoped workspace marker",
                    },
                },
            )
            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "response_item",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T08:00:01+00:00",
                    "scope": "turn_context",
                    "source": "environment_context",
                    "item": {
                        "role": "user",
                        "content": "<environment_context>restored scoped env marker</environment_context>",
                    },
                },
            )

            agent = _RecordingAgent()
            runtime = AgentCliRuntime(
                agent=agent, tools=_WorkspaceTools(workspace), thread_store=store
            )
            runtime.resume_thread(thread.thread_id)
            runtime.handle_prompt("next question")

            self.assertEqual(agent.calls[0]["text"], "next question")
            input_items = agent.calls[0]["input_items"]
            input_texts = self._input_item_texts(agent.calls[0]["input_items"])
            self.assertTrue(
                any(item.get("type") == "reference_context_item" for item in input_items)
            )
            self.assertIn(
                {
                    "role": "user",
                    "content": "REFERENCE_CONTEXT_BASELINE: restored scoped workspace marker",
                },
                runtime._context_update_history,
            )
            self.assertIn(
                "<environment_context>restored scoped env marker</environment_context>", input_texts
            )
            self.assertTrue(
                any(
                    item.get("type") == "response_item" and item.get("scope") == "turn_context"
                    for item in runtime.rollout_items
                )
            )

    def test_resume_thread_turn_context_history_replays_for_legacy_planner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / ".git").write_text("", encoding="utf-8")
            store = ThreadStore(root / "state")
            thread = store.start_thread(
                name="structured turn context legacy", cwd=str(workspace.resolve())
            )

            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "response_item",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T09:00:00+00:00",
                    "scope": "turn_context",
                    "source": "workspace_context",
                    "item": {
                        "role": "user",
                        "content": "REFERENCE_CONTEXT_BASELINE: restored scoped workspace marker",
                    },
                },
            )
            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "response_item",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T09:00:01+00:00",
                    "scope": "turn_context",
                    "source": "environment_context",
                    "item": {
                        "role": "user",
                        "content": "<environment_context>restored scoped env marker</environment_context>",
                    },
                },
            )

            agent = _LegacyHistoryAgent()
            runtime = AgentCliRuntime(
                agent=agent, tools=_WorkspaceTools(workspace), thread_store=store
            )
            runtime.resume_thread(thread.thread_id)
            runtime.handle_prompt("next question")

            self.assertEqual(agent.calls[0]["text"], "next question")
            self.assertTrue(
                self._history_contains_text(
                    agent.calls[0]["history"],
                    "REFERENCE_CONTEXT_BASELINE: restored scoped workspace marker",
                )
            )
            self.assertTrue(
                self._history_contains_text(
                    agent.calls[0]["history"],
                    "<environment_context>restored scoped env marker</environment_context>",
                )
            )

    def test_resume_thread_replays_reference_style_structured_turn_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / ".git").write_text("", encoding="utf-8")
            store = ThreadStore(root / "state")
            thread = store.start_thread(name="reference style replay", cwd=str(workspace.resolve()))

            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "turn_context",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T10:00:00+00:00",
                    "approval_policy": "never",
                    "sandbox_mode": "read-only",
                    "network_access_enabled": False,
                    "items": [
                        {
                            "source": "environment_context",
                            "item": {
                                "type": "message",
                                "role": "user",
                                "content": [
                                    {
                                        "type": "input_text",
                                        "text": "<environment_context>\n  <cwd>/repo</cwd>\n</environment_context>",
                                    }
                                ],
                            },
                        }
                    ],
                    "reference_context_items": [
                        {
                            "item_type": "workspace_context",
                            "source": "test",
                            "label": "workspace_context_baseline",
                            "path": str(workspace.resolve()),
                            "metadata": {
                                "trust_level": "trusted",
                                "instructions_digest": "digest-1",
                                "instructions_excerpt": "workspace baseline",
                                "is_initial": True,
                                "docs": [],
                                "skills": [],
                            },
                        }
                    ],
                },
            )
            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "turn",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T10:00:01+00:00",
                    "turn": {
                        "turn_id": "turn-1",
                        "timestamp": "2026-03-28T10:00:01+00:00",
                        "user_text": "previous user",
                        "assistant_text": "final answer",
                        "assistant_history_text": "final answer",
                        "commentary_text": "",
                        "handled_as_command": False,
                        "status": {},
                        "runtime_state": {},
                        "attachments": [],
                        "tool_events": [],
                        "activity_events": [],
                        "reference_context_items": [],
                        "response_items": [],
                        "turn_events": [
                            {"type": "turn.started"},
                            {
                                "type": "item.completed",
                                "item": {
                                    "id": "item_0",
                                    "type": "reasoning",
                                    "text": "reasoning summary",
                                    "encrypted_content": "enc-1",
                                },
                            },
                            {
                                "type": "item.completed",
                                "item": {
                                    "id": "item_1",
                                    "type": "agent_message",
                                    "text": "pre-tool commentary",
                                },
                            },
                            {
                                "type": "item.started",
                                "item": {
                                    "id": "item_2",
                                    "type": "command_execution",
                                    "command": '/bin/bash -lc "find . -maxdepth 1"',
                                    "aggregated_output": "",
                                    "exit_code": None,
                                    "status": "in_progress",
                                },
                            },
                            {
                                "type": "item.completed",
                                "item": {
                                    "id": "item_2",
                                    "type": "command_execution",
                                    "command": '/bin/bash -lc "find . -maxdepth 1"',
                                    "aggregated_output": "README.md\nsrc\n",
                                    "exit_code": 0,
                                    "status": "completed",
                                },
                            },
                            {
                                "type": "item.completed",
                                "item": {
                                    "id": "item_3",
                                    "type": "agent_message",
                                    "text": "final answer",
                                },
                            },
                            {
                                "type": "turn.completed",
                                "usage": {
                                    "input_tokens": 0,
                                    "cached_input_tokens": 0,
                                    "output_tokens": 0,
                                },
                            },
                        ],
                    },
                },
            )

            resumed = store.resume_thread(thread.thread_id)
            resumed_types = self._input_item_types(resumed["planner_input_items"])
            self.assertIn("reasoning", resumed_types)
            self.assertIn("function_call", resumed_types)
            self.assertIn("function_call_output", resumed_types)

            agent = _RecordingAgent()
            runtime = AgentCliRuntime(
                agent=agent, tools=_WorkspaceTools(workspace), thread_store=store
            )
            runtime.resume_thread(thread.thread_id)
            runtime.handle_prompt("follow up")

            input_items = agent.calls[0]["input_items"]
            input_texts = self._input_item_texts(input_items)
            input_types = self._input_item_types(input_items)

            self.assertEqual(input_items[0]["role"], "developer")
            self.assertTrue(
                any("Approval policy is currently never." in text for text in input_texts)
            )
            self.assertIn(
                "<environment_context>\n  <cwd>/repo</cwd>\n</environment_context>", input_texts
            )
            self.assertTrue(any("REFERENCE_CONTEXT_BASELINE:" in text for text in input_texts))
            self.assertIn("previous user", input_texts)
            self.assertIn("reasoning summary", input_texts)
            self.assertIn("pre-tool commentary", input_texts)
            self.assertIn("final answer", input_texts)
            self.assertIn("reasoning", input_types)
            self.assertIn("function_call", input_types)
            self.assertIn("function_call_output", input_types)
