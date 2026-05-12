from __future__ import annotations

import io
import json
import unittest

from cli.agent_cli.main import main
from cli.agent_cli.models import PromptResponse


class _CompatRuntime:
    class _Agent:
        @staticmethod
        def provider_status() -> dict[str, str]:
            return {
                "provider_ready": "true",
                "provider_name": "compat",
                "provider_model": "compat-model",
            }

    def __init__(self) -> None:
        self.agent = self._Agent()
        self.turn_event_callback = None
        self.thread_id = "thread_compat"

    def configure_runtime_policy(
        self,
        *,
        approval_policy=None,
        sandbox_mode=None,
        web_search_mode=None,
        network_access_enabled=None,
    ) -> None:
        del approval_policy, sandbox_mode, web_search_mode, network_access_enabled

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        streamed_events = [
            {"type": "turn.started"},
            {
                "type": "item.started",
                "item": {
                    "id": "tool_1",
                    "type": "mcp_tool_call",
                    "tool": "list_dir",
                    "status": "in_progress",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "tool_1",
                    "type": "mcp_tool_call",
                    "tool": "list_dir",
                    "status": "completed",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "msg_1",
                    "type": "agent_message",
                    "text": f"echo: {text}",
                },
            },
            {"type": "turn.completed"},
        ]
        callback = getattr(self, "turn_event_callback", None)
        if callable(callback):
            for event in streamed_events:
                callback(dict(event))
        return PromptResponse(
            user_text=text,
            assistant_text=f"echo: {text}",
            command_display_text=f"display: {text}",
            status=self.agent.provider_status(),
            turn_events=[dict(event) for event in streamed_events],
        )


class _CodexFunctionCallRuntime(_CompatRuntime):
    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del text, attachments
        call_id = "call_shell_1"
        streamed_events = [
            {"type": "turn.started"},
            {
                "type": "item.started",
                "item": {
                    "id": call_id,
                    "type": "function_call",
                    "call_id": call_id,
                    "name": "Bash",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": call_id,
                    "type": "function_call",
                    "call_id": call_id,
                    "name": "Bash",
                    "arguments": '{"command":"pwd -P"}',
                },
            },
            {
                "type": "item.completed",
                "item": {"id": "msg_1", "type": "agent_message", "text": "checking"},
            },
            {
                "type": "item.started",
                "item": {
                    "id": call_id,
                    "type": "command_execution",
                    "call_id": call_id,
                    "command": "/bin/bash -lc 'pwd -P'",
                    "aggregated_output": "",
                    "exit_code": None,
                    "status": "in_progress",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": call_id,
                    "type": "command_execution",
                    "call_id": call_id,
                    "command": "/bin/bash -lc 'pwd -P'",
                    "aggregated_output": "/repo",
                    "exit_code": 0,
                    "status": "completed",
                },
            },
            {"type": "turn.completed"},
        ]
        callback = getattr(self, "turn_event_callback", None)
        if callable(callback):
            for event in streamed_events:
                callback(dict(event))
        return PromptResponse(
            user_text="pwd",
            assistant_text="checking",
            status=self.agent.provider_status(),
            turn_events=[dict(event) for event in streamed_events],
        )


class _TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


class HeadlessOutputFormatCompatTest(unittest.TestCase):
    def test_output_format_json_emits_structured_payload(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = main(
            ["--headless", "--prompt", "hello", "--output-format", "json"],
            runtime=_CompatRuntime(),
            stdout=stdout,
            stderr=stderr,
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(payload["assistant_text"], "echo: hello")
        self.assertEqual(payload["command_display_text"], "display: hello")
        self.assertEqual(payload["status"]["provider_name"], "compat")

    def test_json_alias_keeps_compatibility(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = main(
            ["--headless", "--prompt", "hello", "--json"],
            runtime=_CompatRuntime(),
            stdout=stdout,
            stderr=stderr,
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(payload["assistant_text"], "echo: hello")

    def test_output_format_stream_json_emits_stable_event_type_fields(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = main(
            ["--headless", "--prompt", "hello", "--output-format", "stream-json"],
            runtime=_CompatRuntime(),
            stdout=stdout,
            stderr=stderr,
        )

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(lines[0]["type"], "thread.started")
        self.assertEqual(lines[0]["event_type"], "session")
        self.assertIn("tool", {line.get("event_type") for line in lines})
        self.assertIn("turn", {line.get("event_type") for line in lines})

    def test_jsonl_alias_keeps_stream_compatibility(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = main(
            ["--headless", "--prompt", "hello", "--jsonl"],
            runtime=_CompatRuntime(),
            stdout=stdout,
            stderr=stderr,
        )

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(lines[0]["type"], "thread.started")
        self.assertEqual(lines[0]["event_type"], "session")

    def test_output_format_codex_jsonl_omits_agenthub_extension_fields(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = main(
            ["--headless", "--prompt", "hello", "--output-format", "codex-jsonl"],
            runtime=_CompatRuntime(),
            stdout=stdout,
            stderr=stderr,
        )

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(lines[0], {"type": "thread.started", "thread_id": "thread_compat"})
        self.assertFalse(any("event_type" in line for line in lines))
        self.assertFalse(any("id" in line and line.get("type") != "item.started" for line in lines))

    def test_output_format_codex_jsonl_suppresses_shadowed_provider_function_call(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = main(
            ["--headless", "--prompt", "pwd", "--output-format", "codex-jsonl"],
            runtime=_CodexFunctionCallRuntime(),
            stdout=stdout,
            stderr=stderr,
        )

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        item_types = [line["item"]["type"] for line in lines if isinstance(line.get("item"), dict)]
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertNotIn("function_call", item_types)
        self.assertEqual(
            item_types,
            ["agent_message", "command_execution", "command_execution"],
        )
        command_events = [
            line["item"]
            for line in lines
            if isinstance(line.get("item"), dict) and line["item"]["type"] == "command_execution"
        ]
        self.assertEqual(command_events[0]["id"], command_events[1]["id"])
        self.assertEqual(command_events[0]["id"], "item_1")
        self.assertEqual(
            sorted(command_events[0].keys()),
            ["aggregated_output", "command", "exit_code", "id", "status", "type"],
        )
        self.assertEqual(
            sorted(command_events[1].keys()),
            ["aggregated_output", "command", "exit_code", "id", "status", "type"],
        )

    def test_output_format_conflicts_with_legacy_aliases(self) -> None:
        stderr_json = io.StringIO()
        code_json = main(
            ["--headless", "--prompt", "hello", "--output-format", "text", "--json"],
            runtime=_CompatRuntime(),
            stdout=io.StringIO(),
            stderr=stderr_json,
        )
        self.assertEqual(code_json, 1)
        self.assertIn("--output-format=text cannot be combined with --json", stderr_json.getvalue())

        stderr_jsonl = io.StringIO()
        code_jsonl = main(
            ["--headless", "--prompt", "hello", "--output-format", "json", "--jsonl"],
            runtime=_CompatRuntime(),
            stdout=io.StringIO(),
            stderr=stderr_jsonl,
        )
        self.assertEqual(code_jsonl, 1)
        self.assertIn(
            "--output-format=json cannot be combined with --jsonl", stderr_jsonl.getvalue()
        )

    def test_serve_conflicts_with_output_format(self) -> None:
        stderr = io.StringIO()

        code = main(
            ["--headless", "--serve", "--output-format", "json"],
            runtime=_CompatRuntime(),
            stdin=io.StringIO(),
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(code, 1)
        self.assertIn("--serve cannot be combined with --output-format", stderr.getvalue())

    def test_output_format_without_headless_still_routes_headless_path(self) -> None:
        stderr = io.StringIO()

        code = main(
            ["--output-format", "json"],
            runtime=_CompatRuntime(),
            stdin=_TtyStringIO(""),
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(code, 1)
        self.assertIn("provide --prompt, --provider-status, or --stdin", stderr.getvalue())
