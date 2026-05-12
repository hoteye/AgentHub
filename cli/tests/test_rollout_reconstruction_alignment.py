import json
import tempfile
import unittest
from pathlib import Path

from cli.agent_cli.models import (
    ReferenceContextItem,
    RolloutItem,
    ResponseInputItem,
    ThreadHistoryTurn,
    TurnContextInputItem,
    TurnContextRollout,
)
from cli.agent_cli.thread_store import ThreadStore

def _workspace_context(path: str, digest: str) -> ReferenceContextItem:
    return ReferenceContextItem(
        item_type="workspace_context",
        source="test",
        label="workspace",
        path=path,
        description="workspace",
        metadata={"instructions_digest": digest},
    )

def _turn_line(
    thread_id: str,
    *,
    timestamp: str,
    user_text: str = "",
    assistant_text: str = "",
    runtime_state: dict | None = None,
    context_items: list[ReferenceContextItem] | None = None,
) -> dict:
    turn = ThreadHistoryTurn(
        turn_id=f"turn-{timestamp}",
        timestamp=timestamp,
        user_text=user_text,
        assistant_text=assistant_text,
        assistant_history_text=assistant_text,
        runtime_state=dict(runtime_state or {}),
        reference_context_items=list(context_items or []),
    )
    return RolloutItem(
        item_type="turn",
        thread_id=thread_id,
        timestamp=timestamp,
        turn=turn,
    ).to_dict()

class RolloutReconstructionAlignmentTest(unittest.TestCase):
    def _append_line(self, root: Path, thread_id: str, payload: dict) -> None:
        rollout_path = root / "rollouts" / f"{thread_id}.jsonl"
        with rollout_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def test_resume_thread_rollback_drops_latest_user_turn_and_following_turns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ThreadStore(root)
            thread = store.start_thread(name="rollback thread")
            first_context = _workspace_context("/repo", "digest-1")
            second_context = _workspace_context("/repo", "digest-2")

            self._append_line(
                root,
                thread.thread_id,
                _turn_line(
                    thread.thread_id,
                    timestamp="2026-03-28T01:00:00+00:00",
                    user_text="turn 1 user",
                    assistant_text="turn 1 assistant",
                    runtime_state={"provider_name": "openai", "workspace_context_snapshot": {"instructions_digest": "digest-1"}},
                    context_items=[first_context],
                ),
            )
            self._append_line(
                root,
                thread.thread_id,
                _turn_line(
                    thread.thread_id,
                    timestamp="2026-03-28T01:01:00+00:00",
                    user_text="turn 2 user",
                    assistant_text="turn 2 assistant",
                    runtime_state={"provider_name": "openai", "workspace_context_snapshot": {"instructions_digest": "digest-2"}},
                    context_items=[second_context],
                ),
            )
            self._append_line(
                root,
                thread.thread_id,
                _turn_line(
                    thread.thread_id,
                    timestamp="2026-03-28T01:02:00+00:00",
                    assistant_text="standalone assistant",
                    runtime_state={"provider_name": "openai", "workspace_context_snapshot": {"instructions_digest": "digest-standalone"}},
                ),
            )
            self._append_line(
                root,
                thread.thread_id,
                {"type": "thread_rolled_back", "thread_id": thread.thread_id, "timestamp": "2026-03-28T01:03:00+00:00", "num_turns": 1},
            )

            resumed = store.resume_thread(thread.thread_id)

            self.assertEqual(
                resumed["history"],
                [
                    {"role": "user", "content": "turn 1 user"},
                    {"role": "assistant", "content": "turn 1 assistant"},
                ],
            )
            self.assertEqual(len(resumed["turns"]), 1)
            self.assertEqual(
                resumed["state"]["workspace_context_snapshot"]["instructions_digest"],
                "digest-1",
            )
            self.assertEqual(len(resumed["context_items"]), 1)
            self.assertEqual(resumed["context_items"][0]["metadata"]["instructions_digest"], "digest-1")

    def test_resume_thread_rollback_exceeding_user_turns_clears_history_context_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ThreadStore(root)
            thread = store.start_thread(name="rollback clear thread")
            self._append_line(
                root,
                thread.thread_id,
                _turn_line(
                    thread.thread_id,
                    timestamp="2026-03-28T02:00:00+00:00",
                    user_text="only user",
                    assistant_text="only assistant",
                    runtime_state={"provider_name": "openai"},
                    context_items=[_workspace_context("/repo", "digest-only")],
                ),
            )
            self._append_line(
                root,
                thread.thread_id,
                {"type": "thread_rolled_back", "thread_id": thread.thread_id, "timestamp": "2026-03-28T02:01:00+00:00", "num_turns": 99},
            )

            resumed = store.resume_thread(thread.thread_id)

            self.assertEqual(resumed["history"], [])
            self.assertEqual(resumed["turns"], [])
            self.assertEqual(resumed["context_items"], [])
            self.assertEqual(resumed["state"], {})

    def test_resume_thread_compaction_without_replacement_clears_reference_context_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ThreadStore(root)
            thread = store.start_thread(name="compaction clear thread")
            self._append_line(
                root,
                thread.thread_id,
                _turn_line(
                    thread.thread_id,
                    timestamp="2026-03-28T03:00:00+00:00",
                    user_text="before compact",
                    assistant_text="before compact reply",
                    runtime_state={"provider_name": "openai", "workspace_context_snapshot": {"instructions_digest": "digest-before"}},
                    context_items=[_workspace_context("/repo", "digest-before")],
                ),
            )
            self._append_line(
                root,
                thread.thread_id,
                {"type": "compacted", "thread_id": thread.thread_id, "timestamp": "2026-03-28T03:01:00+00:00"},
            )

            resumed = store.resume_thread(thread.thread_id)

            self.assertEqual(resumed["history"], [])
            self.assertEqual(resumed["turns"], [])
            self.assertEqual(resumed["context_items"], [])
            self.assertEqual(resumed["state"], {})

    def test_resume_thread_turn_after_compaction_reestablishes_context_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ThreadStore(root)
            thread = store.start_thread(name="compaction reestablish thread")
            self._append_line(
                root,
                thread.thread_id,
                _turn_line(
                    thread.thread_id,
                    timestamp="2026-03-28T04:00:00+00:00",
                    user_text="before compact",
                    assistant_text="before compact reply",
                    runtime_state={"provider_name": "openai", "workspace_context_snapshot": {"instructions_digest": "digest-before"}},
                    context_items=[_workspace_context("/repo", "digest-before")],
                ),
            )
            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "compacted",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T04:01:00+00:00",
                    "replacement_history": [{"role": "assistant", "content": "summary only"}],
                },
            )
            self._append_line(
                root,
                thread.thread_id,
                _turn_line(
                    thread.thread_id,
                    timestamp="2026-03-28T04:02:00+00:00",
                    user_text="after compact",
                    assistant_text="after compact reply",
                    runtime_state={"provider_name": "openai", "workspace_context_snapshot": {"instructions_digest": "digest-after"}},
                    context_items=[_workspace_context("/repo", "digest-after")],
                ),
            )

            resumed = store.resume_thread(thread.thread_id)

            self.assertEqual(
                resumed["history"],
                [
                    {"role": "assistant", "content": "summary only"},
                    {"role": "user", "content": "after compact"},
                    {"role": "assistant", "content": "after compact reply"},
                ],
            )
            self.assertEqual(len(resumed["turns"]), 1)
            self.assertEqual(resumed["context_items"][0]["metadata"]["instructions_digest"], "digest-after")
            self.assertEqual(
                resumed["state"]["workspace_context_snapshot"]["instructions_digest"],
                "digest-after",
            )

    def test_resume_thread_compaction_keeps_trigger_metadata_in_rollout_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ThreadStore(root)
            thread = store.start_thread(name="compaction metadata thread")
            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "compacted",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T04:30:00+00:00",
                    "reason": "provider_context_overflow_retry",
                    "trigger_error_type": "RuntimeError",
                    "trigger_error_text": "prompt is too long for the context window",
                    "replacement_history": [
                        {
                            "role": "assistant",
                            "content": "Previous conversation summary:\n1. user: before compact",
                        }
                    ],
                },
            )

            resumed = store.resume_thread(thread.thread_id)

            self.assertEqual(
                resumed["history"],
                [
                    {
                        "role": "assistant",
                        "content": "Previous conversation summary:\n1. user: before compact",
                    }
                ],
            )
            compacted_items = [item for item in resumed["rollout_items"] if item.get("type") == "compacted"]
            self.assertEqual(len(compacted_items), 1)
            self.assertEqual(compacted_items[0]["reason"], "provider_context_overflow_retry")
            self.assertEqual(compacted_items[0]["trigger_error_type"], "RuntimeError")
            self.assertEqual(
                compacted_items[0]["trigger_error_text"],
                "prompt is too long for the context window",
            )

    def test_resume_thread_keeps_turn_context_scoped_rollout_items_out_of_base_history_and_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ThreadStore(root)
            thread = store.start_thread(name="turn context scope thread")
            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "response_item",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T05:00:00+00:00",
                    "scope": "turn_context",
                    "item": {"role": "user", "content": "REFERENCE_CONTEXT_BASELINE: hidden"},
                },
            )
            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "reference_context_item",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T05:00:01+00:00",
                    "scope": "turn_context",
                    "item": _workspace_context("/repo", "digest-hidden").to_dict(),
                },
            )
            self._append_line(
                root,
                thread.thread_id,
                {
                    "type": "state_snapshot",
                    "thread_id": thread.thread_id,
                    "timestamp": "2026-03-28T05:00:02+00:00",
                    "scope": "turn_context",
                    "state": {"workspace_context_snapshot": {"instructions_digest": "digest-hidden"}},
                },
            )

            resumed = store.resume_thread(thread.thread_id)

            self.assertEqual(resumed["history"], [])
            self.assertEqual(resumed["context_items"], [])
            self.assertEqual(
                resumed["state"]["workspace_context_snapshot"]["instructions_digest"],
                "digest-hidden",
            )
            self.assertEqual(
                resumed["state"]["context_update_history"],
                [{"role": "user", "content": "REFERENCE_CONTEXT_BASELINE: hidden"}],
            )
            self.assertEqual(len(resumed["rollout_items"]), 4)

    def test_turn_context_rollout_round_trips_with_typed_items_and_metadata(self) -> None:
        payload = RolloutItem(
            item_type="turn_context",
            thread_id="thread-1",
            timestamp="2026-03-28T06:00:00+00:00",
            payload={"scope": "turn_context"},
            turn_context=TurnContextRollout(
                cwd="/repo",
                shell="bash",
                current_date="2026-03-28",
                timezone="Asia/Shanghai",
                approval_policy="on-request",
                sandbox_mode="workspace-write",
                model="gpt-5.4",
                network_access_enabled=True,
                items=[
                    TurnContextInputItem(
                        source="workspace_context",
                        item=ResponseInputItem.from_dict(
                            {
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": "REFERENCE_CONTEXT_BASELINE: typed"}],
                            }
                        ),
                    )
                ],
                reference_context_items=[_workspace_context("/repo", "digest-typed")],
                state={"workspace_context_snapshot": {"instructions_digest": "digest-typed"}},
            ),
        ).to_dict()

        restored = RolloutItem.from_dict(payload)

        self.assertIsNotNone(restored.turn_context)
        self.assertEqual(restored.turn_context.cwd, "/repo")
        self.assertEqual(restored.turn_context.model, "gpt-5.4")
        self.assertEqual(restored.turn_context.approval_policy, "on-request")
        self.assertEqual(restored.turn_context.sandbox_mode, "workspace-write")
        self.assertTrue(restored.turn_context.network_access_enabled)
        self.assertEqual(restored.turn_context.items[0].source, "workspace_context")
        self.assertEqual(restored.turn_context.items[0].item.item_type, "message")
        self.assertEqual(
            restored.turn_context.items[0].item.content[0]["text"],
            "REFERENCE_CONTEXT_BASELINE: typed",
        )
        self.assertEqual(
            restored.turn_context.reference_context_items[0].metadata["instructions_digest"],
            "digest-typed",
        )

    def test_resume_thread_keeps_compound_turn_context_items_out_of_base_history_and_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ThreadStore(root)
            thread = store.start_thread(name="compound turn context scope thread")
            self._append_line(
                root,
                thread.thread_id,
                RolloutItem(
                    item_type="turn_context",
                    thread_id=thread.thread_id,
                    timestamp="2026-03-28T06:10:00+00:00",
                    payload={"scope": "turn_context"},
                    turn_context=TurnContextRollout(
                        cwd="/repo",
                        approval_policy="on-request",
                        sandbox_mode="workspace-write",
                        model="gpt-5.4",
                        items=[
                            TurnContextInputItem(
                                source="workspace_context",
                                item=ResponseInputItem.from_dict(
                                    {
                                        "type": "message",
                                        "role": "user",
                                        "content": [{"type": "input_text", "text": "REFERENCE_CONTEXT_BASELINE: hidden typed"}],
                                    }
                                ),
                            )
                        ],
                        reference_context_items=[_workspace_context("/repo", "digest-hidden-typed")],
                        state={"workspace_context_snapshot": {"instructions_digest": "digest-hidden-typed"}},
                    ),
                ).to_dict(),
            )

            resumed = store.resume_thread(thread.thread_id)

            self.assertEqual(resumed["history"], [])
            self.assertEqual(resumed["context_items"], [])
            self.assertEqual(
                resumed["state"]["workspace_context_snapshot"]["instructions_digest"],
                "digest-hidden-typed",
            )
            self.assertEqual(
                resumed["state"]["context_update_history"],
                [{"role": "user", "content": "REFERENCE_CONTEXT_BASELINE: hidden typed"}],
            )

    def test_turn_context_rollout_round_trips_as_typed_carrier(self) -> None:
        rollout = RolloutItem(
            item_type="turn_context",
            thread_id="thread-1",
            timestamp="2026-03-28T06:00:00+00:00",
            payload={"scope": "turn_context"},
            turn_context=TurnContextRollout(
                cwd="/repo",
                approval_policy="on-request",
                sandbox_mode="workspace-write",
                model="gpt-5.4",
                items=[
                    TurnContextInputItem(
                        source="environment_context",
                        item=ResponseInputItem.from_dict(
                            {
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": "<environment_context>env</environment_context>"}],
                            }
                        ),
                    ),
                    TurnContextInputItem(
                        source="workspace_context",
                        item=ResponseInputItem.from_dict(
                            {
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": "REFERENCE_CONTEXT_BASELINE: workspace"}],
                            }
                        ),
                    ),
                ],
                reference_context_items=[_workspace_context("/repo", "digest-roundtrip")],
                state={"workspace_context_snapshot": {"instructions_digest": "digest-roundtrip"}},
            ),
        )

        restored = RolloutItem.from_dict(rollout.to_dict())

        self.assertEqual(restored.item_type, "turn_context")
        self.assertIsNotNone(restored.turn_context)
        self.assertEqual(restored.payload["scope"], "turn_context")
        self.assertEqual(restored.turn_context.cwd, "/repo")
        self.assertEqual(restored.turn_context.model, "gpt-5.4")
        self.assertEqual(restored.turn_context.items[0].item.role, "user")
        self.assertEqual(
            restored.turn_context.items[1].item.content[0]["text"],
            "REFERENCE_CONTEXT_BASELINE: workspace",
        )
        self.assertEqual(
            restored.turn_context.reference_context_items[0].metadata["instructions_digest"],
            "digest-roundtrip",
        )
        self.assertEqual(
            restored.turn_context.state["workspace_context_snapshot"]["instructions_digest"],
            "digest-roundtrip",
        )

    def test_turn_context_response_item_round_trips_tool_output_shape(self) -> None:
        payload = RolloutItem(
            item_type="turn_context",
            thread_id="thread-tool",
            timestamp="2026-03-28T06:20:00+00:00",
            payload={"scope": "turn_context"},
            turn_context=TurnContextRollout(
                items=[
                    TurnContextInputItem(
                        source="workspace_context",
                        item=ResponseInputItem.from_dict(
                            {
                                "type": "function_call_output",
                                "call_id": "call-1",
                                "output": "{\"status\":\"ok\"}",
                            }
                        ),
                    )
                ]
            ),
        ).to_dict()

        restored = RolloutItem.from_dict(payload)

        self.assertEqual(restored.turn_context.items[0].item.item_type, "function_call_output")
        self.assertEqual(restored.turn_context.items[0].item.extra["call_id"], "call-1")
        self.assertEqual(restored.turn_context.items[0].item.extra["output"], "{\"status\":\"ok\"}")
