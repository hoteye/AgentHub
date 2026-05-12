from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.main import main
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli import provider as provider_module
from cli.agent_cli.providers.openai_client import build_openai_client
from cli.agent_cli.providers.tool_specs import responses_provider_tool_specs
from cli.agent_cli.thread_store import ThreadStore

@unittest.skipUnless(
    os.environ.get("RUN_LIVE_RESPONSES_TOOL_CONTRACT") == "1",
    "set RUN_LIVE_RESPONSES_TOOL_CONTRACT=1 to enable live Responses tool-contract validation",
)
class OpenAIResponsesToolContractLiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cwd = ROOT / "cli"
        snapshot = provider_module.load_provider_management_snapshot(cwd=cls.cwd)
        cls.config = getattr(snapshot, "selected_config", None)
        if cls.config is None:
            raise unittest.SkipTest("provider config not found")
        if str(cls.config.planner_kind or "").strip().lower() != "openai_responses":
            raise unittest.SkipTest("active provider is not using the Responses planner")
        cls.client = build_openai_client(cls.config)

    def _call(self, *, tools=None) -> str:
        kwargs = {
            "model": self.config.model,
            "instructions": "Respond briefly in Chinese.",
            "input": [{"role": "user", "content": "你好"}],
            "store": False,
            "stream": False,
        }
        if tools is not None:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
            kwargs["parallel_tool_calls"] = False
        response = self.client.responses.create(**kwargs)
        return str(getattr(response, "output_text", "") or "").strip()

    def test_no_tools_and_minimal_flat_tool_succeed(self) -> None:
        baseline_text = self._call()
        self.assertTrue(baseline_text)

        minimal_tool_text = self._call(
            tools=[
                {
                    "type": "function",
                    "name": "echo_tool",
                    "description": "Echo one string.",
                    "parameters": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"],
                        "additionalProperties": False,
                    },
                }
            ]
        )
        self.assertTrue(minimal_tool_text)

    def test_builtin_exec_command_tool_succeeds(self) -> None:
        specs = responses_provider_tool_specs(self.config, current_host_platform())
        exec_command_tool = next(item for item in specs if item.get("type") == "function" and item.get("name") == "exec_command")

        response_text = self._call(tools=[exec_command_tool])
        self.assertTrue(response_text)

    def test_full_builtin_toolset_succeeds(self) -> None:
        specs = responses_provider_tool_specs(self.config, current_host_platform())

        response_text = self._call(tools=specs)
        self.assertTrue(response_text)

    def test_runtime_two_turn_conversation_stays_ready(self) -> None:
        runtime = AgentCliRuntime()

        first = runtime.handle_prompt("你好")
        second = runtime.handle_prompt("再说一遍你好")

        self.assertTrue(str(first.assistant_text or "").strip())
        self.assertTrue(str(second.assistant_text or "").strip())
        self.assertEqual(runtime.agent.provider_status().get("provider_runtime_state"), "ready")

    def test_headless_persistent_two_turn_conversation_stays_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))

            runtime1 = AgentCliRuntime(thread_store=store)
            runtime1.start_thread(name="openai headless live")
            stdout1 = io.StringIO()
            code1 = main(
                ["--headless", "--prompt", "你好", "--json", "--approval-policy", "never"],
                runtime=runtime1,
                stdout=stdout1,
                stderr=io.StringIO(),
            )
            payload1 = json.loads(stdout1.getvalue())

            runtime2 = AgentCliRuntime(thread_store=store)
            active_thread_id = store.get_active_thread_id()
            if active_thread_id:
                runtime2.resume_thread(active_thread_id)
            stdout2 = io.StringIO()
            code2 = main(
                ["--headless", "--prompt", "再说一遍你好", "--json", "--approval-policy", "never"],
                runtime=runtime2,
                stdout=stdout2,
                stderr=io.StringIO(),
            )
            payload2 = json.loads(stdout2.getvalue())

        self.assertEqual(code1, 0)
        self.assertEqual(code2, 0)
        self.assertTrue(str(payload1.get("assistant_text") or "").strip())
        self.assertTrue(str(payload2.get("assistant_text") or "").strip())
        self.assertEqual(payload1["status"]["provider_runtime_state"], "ready")
        self.assertEqual(payload2["status"]["provider_runtime_state"], "ready")
        self.assertNotIn("当前没有可用的 LLM provider", str(payload2.get("assistant_text") or ""))
