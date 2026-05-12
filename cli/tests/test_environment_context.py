from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from cli.agent_cli.environment_context import (
    EnvironmentContext,
    NetworkContext,
    build_environment_context_snapshot,
    local_datetime_with_timezone,
    environment_contract,
    extract_environment_contract_from_input_items,
    render_environment_context_update_message,
)

class EnvironmentContextTest(unittest.TestCase):
    def test_serialize_environment_context_with_workspace_fields(self) -> None:
        context = EnvironmentContext(
            cwd="/repo",
            shell="bash",
            current_date="2026-03-28",
            timezone="Asia/Shanghai",
        )

        self.assertEqual(
            context.serialize_to_xml(),
            "<environment_context>\n"
            "  <cwd>/repo</cwd>\n"
            "  <shell>bash</shell>\n"
            "  <current_date>2026-03-28</current_date>\n"
            "  <timezone>Asia/Shanghai</timezone>\n"
            "</environment_context>",
        )

    def test_serialize_environment_context_with_network_and_subagents(self) -> None:
        context = EnvironmentContext(
            cwd="/repo",
            shell="bash",
            current_date="2026-03-28",
            timezone="Asia/Shanghai",
            network=NetworkContext(
                allowed_domains=["api.example.com", "*.openai.com"],
                denied_domains=["blocked.example.com"],
            ),
            subagents="worker-a\nworker-b",
        )

        xml = context.serialize_to_xml()
        self.assertIn('<network enabled="true">', xml)
        self.assertIn("<allowed>api.example.com</allowed>", xml)
        self.assertIn("<allowed>*.openai.com</allowed>", xml)
        self.assertIn("<denied>blocked.example.com</denied>", xml)
        self.assertIn("<subagents>", xml)
        self.assertIn("worker-a", xml)
        self.assertIn("worker-b", xml)

    def test_equals_except_shell_ignores_shell_but_compares_other_fields(self) -> None:
        left = EnvironmentContext(
            cwd="/repo",
            shell="bash",
            current_date="2026-03-28",
            timezone="Asia/Shanghai",
            network=NetworkContext(allowed_domains=["api.example.com"]),
            subagents="worker-a",
        )
        right = EnvironmentContext(
            cwd="/repo",
            shell="powershell",
            current_date="2026-03-28",
            timezone="Asia/Shanghai",
            network=NetworkContext(allowed_domains=["api.example.com"]),
            subagents="worker-a",
        )
        changed = EnvironmentContext(
            cwd="/other",
            shell="bash",
            current_date="2026-03-28",
            timezone="Asia/Shanghai",
            network=NetworkContext(allowed_domains=["api.example.com"]),
            subagents="worker-a",
        )

        self.assertTrue(left.equals_except_shell(right))
        self.assertFalse(left.equals_except_shell(changed))

    def test_diff_from_previous_only_emits_changed_cwd(self) -> None:
        previous = EnvironmentContext(
            cwd="/repo-a",
            shell="bash",
            current_date="2026-03-28",
            timezone="Asia/Shanghai",
            network=NetworkContext(allowed_domains=["api.example.com"]),
        )
        current = EnvironmentContext(
            cwd="/repo-b",
            shell="bash",
            current_date="2026-03-29",
            timezone="Asia/Shanghai",
            network=NetworkContext(allowed_domains=["api.example.com"]),
        )

        diff = current.diff(previous)

        self.assertEqual(diff.cwd, "/repo-b")
        self.assertEqual(diff.current_date, "2026-03-29")
        self.assertEqual(diff.timezone, "Asia/Shanghai")
        self.assertEqual(diff.network, previous.network)

    def test_render_environment_context_update_message_returns_full_context_when_unchanged(self) -> None:
        previous = {
            "cwd": "/repo",
            "shell": "bash",
            "current_date": "2026-04-01",
            "timezone": "Asia/Shanghai",
        }
        current = {
            "cwd": "/repo",
            "shell": "bash",
            "current_date": "2026-04-01",
            "timezone": "Asia/Shanghai",
        }

        self.assertEqual(
            render_environment_context_update_message(previous, current),
            "<environment_context>\n"
            "  <cwd>/repo</cwd>\n"
            "  <shell>bash</shell>\n"
            "  <current_date>2026-04-01</current_date>\n"
            "  <timezone>Asia/Shanghai</timezone>\n"
            "</environment_context>",
        )

    def test_environment_contract_ignores_shell_and_network(self) -> None:
        payload = {
            "cwd": "/repo",
            "shell": "bash",
            "current_date": "2026-03-31",
            "timezone": "Asia/Shanghai",
            "network": {"allowed_domains": ["api.openai.com"]},
        }

        self.assertEqual(
            environment_contract(payload),
            {
                "cwd": "/repo",
                "current_date": "2026-03-31",
                "timezone": "Asia/Shanghai",
            },
        )

    def test_extract_environment_contract_from_input_items_prefers_latest_context_block(self) -> None:
        items = [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "<environment_context>\n  <cwd>/repo-a</cwd>\n  <shell>bash</shell>\n  <current_date>2026-03-30</current_date>\n  <timezone>UTC</timezone>\n</environment_context>"}],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "<environment_context>\n  <cwd>/repo-b</cwd>\n  <shell>bash</shell>\n  <current_date>2026-03-31</current_date>\n  <timezone>Asia/Shanghai</timezone>\n</environment_context>"}],
            },
        ]

        self.assertEqual(
            extract_environment_contract_from_input_items(items),
            {
                "cwd": "/repo-b",
                "current_date": "2026-03-31",
                "timezone": "Asia/Shanghai",
            },
        )

    def test_local_datetime_with_timezone_uses_detected_iana_name(self) -> None:
        base = datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc)
        with patch(
            "cli.agent_cli.environment_context.detect_local_timezone_name",
            return_value="Asia/Shanghai",
        ):
            localized = local_datetime_with_timezone(base)

        self.assertEqual(str(localized.tzinfo), "Asia/Shanghai")

    def test_build_environment_context_snapshot_preserves_explicit_current_dt_timezone(self) -> None:
        snapshot = build_environment_context_snapshot(
            cwd="/repo",
            shell="bash",
            network_access=False,
            current_dt=datetime(2026, 4, 20, 4, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(snapshot["timezone"], "UTC")
