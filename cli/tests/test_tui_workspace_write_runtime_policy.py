from __future__ import annotations

import unittest

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_policy import RuntimePolicy


class TuiWorkspaceWriteRuntimePolicyTest(unittest.IsolatedAsyncioTestCase):
    async def test_tui_runs_with_workspace_write_runtime_policy(self) -> None:
        runtime = AgentCliRuntime(
            runtime_policy=RuntimePolicy.normalized(
                approval_policy="on-request",
                sandbox_mode="workspace-write",
            )
        )
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            status = app.runtime.runtime_policy_status()

        self.assertEqual(status["approval_policy"], "on-request")
        self.assertEqual(status["sandbox_mode"], "workspace-write")
        self.assertEqual(status["web_search_mode"], "cached")
