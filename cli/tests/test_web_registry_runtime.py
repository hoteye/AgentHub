from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.tools import ToolRegistry
from cli.agent_cli.tools_core import web_registry_runtime

class WebRegistryRuntimeTest(unittest.TestCase):
    def test_get_web_search_tools_builds_and_caches_project_tool(self) -> None:
        constructed: list[str] = []

        class _WebSearchTools:
            def __init__(self, *, policy_path: str) -> None:
                constructed.append(policy_path)
                self.policy_path = policy_path

        module = SimpleNamespace(WebSearchTools=_WebSearchTools)
        result = web_registry_runtime.get_web_search_tools(
            cached_tools=None,
            load_project_tool_module=lambda name: module,
            project_root=Path("/tmp/project"),
        )

        self.assertIsInstance(result, _WebSearchTools)
        self.assertEqual(constructed, ["/tmp/project/config/web_tools.toml"])

        cached = object()
        self.assertIs(
            web_registry_runtime.get_web_search_tools(
                cached_tools=cached,
                load_project_tool_module=lambda name: module,
                project_root=Path("/tmp/project"),
            ),
            cached,
        )

    def test_tool_registry_web_helpers_delegate_through_web_registry_runtime(self) -> None:
        registry = object.__new__(ToolRegistry)
        registry._web_search_tools = None

        with patch.object(web_registry_runtime, "get_web_search_tools", return_value="web-tools") as get_tools:
            self.assertEqual(ToolRegistry._get_web_search_tools(registry), "web-tools")
        get_tools.assert_called_once()
        self.assertEqual(get_tools.call_args.kwargs["cached_tools"], None)

        with patch.object(web_registry_runtime, "get_browser_client", return_value="browser-client") as get_client:
            self.assertEqual(ToolRegistry._get_browser_client(registry), "browser-client")
        get_client.assert_called_once_with(registry)

        with patch.object(web_registry_runtime, "profile_prefers_local_browser", return_value=True) as prefers_local:
            self.assertTrue(ToolRegistry._profile_prefers_local_browser(registry, profile="review"))
        prefers_local.assert_called_once_with(registry, profile="review")

        with patch.object(web_registry_runtime, "get_browser_executor", return_value="browser-executor") as get_executor:
            self.assertEqual(
                ToolRegistry._get_browser_executor(registry, profile="review", transport="proxy"),
                "browser-executor",
            )
        get_executor.assert_called_once_with(registry, profile="review", transport="proxy")
