import tempfile
import unittest
from pathlib import Path

from cli.replay_integration.cassette import load_replay_cassette, save_replay_cassette
from cli.replay_integration.schema import (
    ReplayCassette,
    ReplayManifest,
    ReplayRound,
    ReplaySessionMetadata,
    ReplayToolCall,
)

class ReplayCassetteTest(unittest.TestCase):
    def test_save_and_load_roundtrip(self) -> None:
        cassette = ReplayCassette(
            manifest=ReplayManifest(
                name="smoke",
                drift_policy="strict",
                session=ReplaySessionMetadata(
                    provider="openai",
                    model="gpt-5.4",
                    thread_id="thread_1",
                    cwd="/tmp/workspace",
                ),
                environment_snapshot={"cwd": "/tmp/workspace", "shell": "bash"},
                workspace_snapshot={"cwd": "/tmp/workspace", "instructions_digest": "digest-1"},
            ),
            rounds=[
                ReplayRound(
                    index=1,
                    request_headers={"session_id": "thread_1"},
                    request={"model": "gpt-5.4", "input": [{"role": "user", "content": "hello"}]},
                    response_events=[{"type": "response.completed"}],
                    response={"id": "resp_1"},
                )
            ],
            tool_calls=[
                ReplayToolCall(
                    index=1,
                    tool_name="exec_command",
                    call_id="call_1",
                    arguments={"cmd": "pwd"},
                    output_items=[{"type": "function_call_output", "call_id": "call_1", "output": "/tmp"}],
                )
            ],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "case"
            save_replay_cassette(root, cassette)
            loaded = load_replay_cassette(root)

        self.assertEqual(loaded.manifest.name, "smoke")
        self.assertEqual(loaded.manifest.drift_policy, "strict")
        self.assertEqual(loaded.rounds[0].request_headers["session_id"], "thread_1")
        self.assertEqual(loaded.tool_calls[0].tool_name, "exec_command")
