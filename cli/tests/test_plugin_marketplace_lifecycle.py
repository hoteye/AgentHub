from __future__ import annotations

from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.tools import ToolRegistry
from cli.tests.provider_boundary_test_support import provider_status_path_fields


ROOT = Path(__file__).resolve().parents[2]


class _PluginFakeAgent:
    def provider_status(self):
        return {
            "provider_ready": "true",
            "provider_name": "deepseek",
            "provider_planner": "deepseek_chat",
            "provider_model": "test-model",
            "provider_tools": "tool-calls",
            "provider_label": "deepseek | test-model | tool-calls",
            "provider_base_url": "http://test",
            "provider_source": "test",
            **provider_status_path_fields(),
        }

    def plan(self, text, history=None, *, tool_executor=None, attachments=None):
        raise AssertionError("LLM planner should not be used in plugin marketplace lifecycle tests")


class PluginMarketplaceLifecycleTest(unittest.TestCase):
    @staticmethod
    def _copy_demo_plugin(dst_root: Path) -> Path:
        source = ROOT / "plugins" / "demo_plugin"
        dst = dst_root / "demo_plugin"
        shutil.copytree(source, dst)
        return dst

    def test_runtime_plugin_marketplace_lifecycle(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "source"
            source_root.mkdir(parents=True, exist_ok=True)
            source_dir = self._copy_demo_plugin(source_root)
            reference_home = root / ".agent_cli"
            tools = ToolRegistry()
            tools._plugin_manager = PluginManager(
                plugin_root=root / "plugins_target",
                state_path=root / "plugin_state.json",
                reference_home=reference_home,
                config_path=reference_home / "config.toml",
            )
            runtime = AgentCliRuntime(tools=tools, agent=_PluginFakeAgent())

            add = runtime.handle_prompt(f'/plugin_marketplace add demo_plugin@test "{source_dir}" scope project')
            self.assertTrue(add.tool_events[0].ok)
            self.assertEqual(add.tool_events[0].name, "plugin_marketplace_add")
            add_entry = dict(add.tool_events[0].payload.get("entry") or {})
            source_metadata = dict(add_entry.get("source_metadata") or {})
            self.assertEqual(source_metadata.get("source_type"), "directory")
            self.assertEqual(source_metadata.get("cache_path"), str(source_dir.resolve()))
            self.assertTrue(str(source_metadata.get("last_checked") or "").strip())

            listed = runtime.handle_prompt("/plugin_marketplace list")
            self.assertIn("demo_plugin@test", listed.assistant_text)

            install = runtime.handle_prompt("/plugin_marketplace install demo_plugin@test")
            self.assertTrue(install.tool_events[0].ok)
            self.assertEqual(install.tool_events[0].name, "plugin_marketplace_install")
            self.assertEqual(install.tool_events[0].payload.get("scope"), "project")

            ping = runtime.handle_prompt("/demo_ping hello")
            self.assertTrue(ping.tool_events and ping.tool_events[0].ok)

            disable = runtime.handle_prompt("/plugin_marketplace disable demo_plugin")
            self.assertTrue(disable.tool_events[0].ok)

            ping_after_disable = runtime.handle_prompt("/demo_ping hello")
            self.assertEqual(ping_after_disable.tool_events, [])

            enable = runtime.handle_prompt("/plugin_marketplace enable demo_plugin")
            self.assertTrue(enable.tool_events[0].ok)

            ping_after_enable = runtime.handle_prompt("/demo_ping hello")
            self.assertTrue(ping_after_enable.tool_events and ping_after_enable.tool_events[0].ok)

            uninstall = runtime.handle_prompt("/plugin_marketplace uninstall demo_plugin")
            self.assertTrue(uninstall.tool_events[0].ok)

            remove_entry = runtime.handle_prompt("/plugin_marketplace remove demo_plugin@test")
            self.assertTrue(remove_entry.tool_events[0].ok)
            self.assertEqual(remove_entry.tool_events[0].name, "plugin_marketplace_remove")

    def test_runtime_plugin_marketplace_policy_blocks_add_with_diagnostics(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "source"
            source_root.mkdir(parents=True, exist_ok=True)
            source_dir = self._copy_demo_plugin(source_root)
            reference_home = root / ".agent_cli"
            tools = ToolRegistry()
            tools._plugin_manager = PluginManager(
                plugin_root=root / "plugins_target",
                state_path=root / "plugin_state.json",
                reference_home=reference_home,
                config_path=reference_home / "config.toml",
            )
            runtime = AgentCliRuntime(tools=tools, agent=_PluginFakeAgent())
            runtime.plugin_marketplace_policy_hook = lambda **_kwargs: {
                "allow": False,
                "reason": "blocked by test policy",
                "code": "policy.blocklist",
                "details": {"rule_id": "demo_plugin_block"},
            }

            blocked = runtime.handle_prompt(f'/plugin_marketplace add demo_plugin@test "{source_dir}" scope project')
            self.assertFalse(blocked.tool_events[0].ok)
            self.assertEqual(blocked.tool_events[0].name, "plugin_marketplace_add")
            self.assertIn("blocked by policy", blocked.assistant_text.lower())
            self.assertEqual(blocked.tool_events[0].payload.get("policy_code"), "policy.blocklist")
            self.assertIn("plugin_marketplace_policy_hook", str(blocked.tool_events[0].payload.get("policy_hook") or ""))
            self.assertEqual(
                dict(blocked.tool_events[0].payload.get("policy_details") or {}).get("rule_id"),
                "demo_plugin_block",
            )

    def test_runtime_plugin_marketplace_policy_blocks_update_with_diagnostics(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "source"
            source_root.mkdir(parents=True, exist_ok=True)
            source_dir = self._copy_demo_plugin(source_root)
            reference_home = root / ".agent_cli"
            tools = ToolRegistry()
            tools._plugin_manager = PluginManager(
                plugin_root=root / "plugins_target",
                state_path=root / "plugin_state.json",
                reference_home=reference_home,
                config_path=reference_home / "config.toml",
            )
            runtime = AgentCliRuntime(tools=tools, agent=_PluginFakeAgent())
            runtime.plugin_marketplace_policy_hook = lambda **_kwargs: True

            add = runtime.handle_prompt(f'/plugin_marketplace add demo_plugin@test "{source_dir}" scope project')
            self.assertTrue(add.tool_events[0].ok)

            runtime.plugin_marketplace_policy_hook = lambda **kwargs: {
                "allow": kwargs.get("action") != "update",
                "reason": "blocked update by test policy",
                "code": "policy.update_block",
                "details": {"rule_id": "demo_plugin_update_block"},
            }
            blocked_update = runtime.handle_prompt("/plugin_marketplace update demo_plugin@test scope user")
            self.assertFalse(blocked_update.tool_events[0].ok)
            self.assertEqual(blocked_update.tool_events[0].name, "plugin_marketplace_update")
            self.assertEqual(blocked_update.tool_events[0].payload.get("policy_code"), "policy.update_block")
            self.assertEqual(
                dict(blocked_update.tool_events[0].payload.get("policy_details") or {}).get("rule_id"),
                "demo_plugin_update_block",
            )
