from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.host_platform import detect_host_platform
from cli.agent_cli.providers.config_catalog_types import ProviderConfig
from cli.agent_cli.runtime_tools_surface_runtime import runtime_tools_capabilities


class _Tools:
    def __init__(self) -> None:
        self._payload = {
            "ok": True,
            "tools": [
                {"name": "exec_command", "description": "Runs a command in a PTY."},
                {"name": "write_stdin", "description": "Writes stdin to an existing session."},
                {"name": "request_user_input", "description": "Request structured user input."},
                {"name": "apply_patch", "description": "Apply a workspace patch."},
                {"name": "shell", "description": "Compatibility shell alias."},
                {"name": "office_skills", "description": "Office skills."},
            ],
            "count": 6,
        }

    def capabilities(self) -> dict[str, object]:
        return dict(self._payload)


class RuntimeToolsSurfaceRuntimeTest(unittest.TestCase):
    def test_runtime_tools_capabilities_projects_claude_surface_names(self) -> None:
        runtime = SimpleNamespace(
            tools=_Tools(),
            agent=SimpleNamespace(
                _planner=SimpleNamespace(
                    config=ProviderConfig(
                        model="claude-sonnet-4-6",
                        api_key="test-key",
                        provider_name="anthropic",
                        planner_kind="anthropic_messages",
                        wire_api="anthropic_messages",
                        interaction_profile="claude_code",
                        interaction_profile_source="test",
                    )
                )
            ),
        )

        with patch(
            "cli.agent_cli.runtime_tools_surface_runtime.current_host_platform",
            return_value=detect_host_platform(system_name="Linux", sys_platform="linux"),
        ):
            payload = runtime_tools_capabilities(runtime)

        names = [item["name"] for item in payload["tools"]]
        self.assertEqual(
            names, ["Bash", "write_stdin", "AskUserQuestion", "Write", "Edit", "office_skills"]
        )
        self.assertNotIn("exec_command", names)
        self.assertNotIn("shell", names)
        self.assertNotIn("request_user_input", names)
        self.assertNotIn("apply_patch", names)
        description_by_name = {item["name"]: item.get("description") for item in payload["tools"]}
        self.assertTrue(description_by_name["Bash"])
        self.assertTrue(description_by_name["AskUserQuestion"])
        self.assertIn(
            "Use Read first before overwriting an existing file.", description_by_name["Write"]
        )
        self.assertIn("match exactly once unless replace_all=true", description_by_name["Edit"])
        self.assertNotIn("Reference-style structured patch", description_by_name["Write"])
        self.assertNotIn("Reference-style structured patch", description_by_name["Edit"])
        self.assertEqual(payload["count"], 6)

    def test_runtime_tools_capabilities_keeps_original_payload_without_provider_config(
        self,
    ) -> None:
        tools = _Tools()
        runtime = SimpleNamespace(
            tools=tools,
            agent=SimpleNamespace(),
        )

        payload = runtime_tools_capabilities(runtime)

        self.assertEqual(payload["tools"], tools.capabilities()["tools"])
        self.assertEqual(payload["count"], 6)
