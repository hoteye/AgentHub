from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from cli.agent_cli.runtime import AgentCliRuntime

@unittest.skipUnless(os.environ.get("RUN_LIVE_DEEPSEEK_E2E") == "1", "set RUN_LIVE_DEEPSEEK_E2E=1 to enable live DeepSeek validation")
class DeepSeekReasonerLiveTest(unittest.TestCase):
    def test_reasoner_executes_multi_step_tool_loop(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AGENT_CLI_PROVIDER": "deepseek",
                "AGENT_CLI_MODEL": "deepseek-reasoner",
            },
            clear=False,
        ):
            runtime = AgentCliRuntime()
            status = runtime.agent.provider_status()
            self.assertEqual(status["provider_ready"], "true")
            self.assertEqual(status["provider_planner"], "deepseek_reasoner")
            self.assertEqual(status["provider_model"], "deepseek-reasoner")

            response = runtime.handle_prompt(
                "Use tools to run python --version. "
                "If the output starts with Python 3.11, then use tools to run pwd. "
                "Finally answer briefly in Chinese."
            )

        self.assertGreaterEqual(len(response.tool_events), 2)
        self.assertEqual(response.tool_events[0].name, "shell")
        self.assertEqual(response.tool_events[1].name, "shell")
        self.assertIn("Python 3.11", str(response.tool_events[0].payload.get("stdout") or ""))
        self.assertTrue(str(response.tool_events[1].payload.get("stdout") or "").strip())
        self.assertTrue(str(response.assistant_text or "").strip())
