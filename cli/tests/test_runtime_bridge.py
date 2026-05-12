from __future__ import annotations

import unittest
from unittest.mock import patch

from cli.agent_cli.ui.runtime_bridge import resolve_runtime
from cli.agent_cli.runtime_policy import RuntimePolicy

class RuntimeBridgeTest(unittest.TestCase):
    def test_resolve_runtime_uses_fresh_persistent_runtime_for_tui(self) -> None:
        sentinel = object()

        with patch("cli.agent_cli.runtime_factory.build_persistent_runtime", return_value=sentinel) as build_runtime:
            resolved = resolve_runtime(None)

        self.assertIs(resolved, sentinel)
        build_runtime.assert_called_once_with(
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
            resume_active_thread=False,
        )
