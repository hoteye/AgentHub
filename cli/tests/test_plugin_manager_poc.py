import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from cli.agent_cli.host.plugin_manager import PluginManager, RegisteredWorkflowHandler
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.tools import ToolRegistry
from cli.agent_cli.gateway_core.models import ConnectorRegistration, PolicyRegistration, TriggerRegistration
from cli.tests.provider_boundary_test_support import provider_status_path_fields

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
        raise AssertionError("LLM planner should not be used in plugin POC tests")

class PluginManagerPocTest(unittest.TestCase):
    @staticmethod
    def _demo_plugin_path() -> Path:
        return ROOT / "plugins" / "demo_plugin"

    def _copy_demo_plugin(self, dst_root: Path, *, folder_name: str = "demo_plugin") -> Path:
        source = self._demo_plugin_path()
        dst = dst_root / folder_name
        shutil.copytree(source, dst)
        return dst

    def test_demo_plugin_discovered_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PluginManager(state_path=Path(tmpdir) / "plugin_state.json")
            plugins = manager.list_plugins()
            self.assertTrue(any(item["name"] == "demo_plugin" and item["enabled"] for item in plugins))
            self.assertTrue(any(item["name"] == "demo_ping" for item in manager.command_specs()))
            self.assertTrue(any(item["name"] == "demo_echo" for item in manager.tool_specs()))

    def test_disable_plugin_hides_command_and_tool(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PluginManager(state_path=Path(tmpdir) / "plugin_state.json")
            disabled = manager.disable_plugin("demo_plugin")
            self.assertTrue(disabled["ok"])
            self.assertFalse(any(item["name"] == "demo_ping" for item in manager.command_specs()))
            self.assertFalse(any(item["name"] == "demo_echo" for item in manager.tool_specs()))
            plugins = manager.list_plugins()
            self.assertTrue(any(item["name"] == "demo_plugin" and not item["enabled"] for item in plugins))

    def test_install_from_directory_and_safe_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "source"
            plugins_root = root / "plugins_target"
            state_path = root / "plugin_state.json"
            source_root.mkdir(parents=True, exist_ok=True)
            source_dir = self._copy_demo_plugin(source_root)
            manager = PluginManager(plugin_root=plugins_root, state_path=state_path)

            installed = manager.install_plugin(str(source_dir))
            self.assertTrue(installed["ok"])
            self.assertEqual(installed["plugin_name"], "demo_plugin")
            self.assertTrue((plugins_root / "demo_plugin").exists())
            self.assertTrue(any(item["name"] == "demo_ping" for item in manager.command_specs()))

            blocked = manager.install_plugin(str(source_dir))
            self.assertFalse(blocked["ok"])
            self.assertEqual(blocked["reason"], "plugin_exists")

            replaced = manager.install_plugin(str(source_dir), replace=True)
            self.assertTrue(replaced["ok"])
            self.assertTrue(replaced["replaced"])

    def test_install_from_zip_and_remove(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "source"
            plugins_root = root / "plugins_target"
            state_path = root / "plugin_state.json"
            source_root.mkdir(parents=True, exist_ok=True)
            source_dir = self._copy_demo_plugin(source_root)
            zip_path = root / "demo_plugin.zip"
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for path in source_dir.rglob("*"):
                    if path.is_file():
                        zf.write(path, arcname=str(path.relative_to(source_root)))

            manager = PluginManager(plugin_root=plugins_root, state_path=state_path)
            installed = manager.install_plugin(str(zip_path))
            self.assertTrue(installed["ok"])
            self.assertEqual(installed["source_kind"], "zip")
            self.assertTrue((plugins_root / "demo_plugin").exists())

            removed = manager.remove_plugin("demo_plugin")
            self.assertTrue(removed["ok"])
            self.assertFalse((plugins_root / "demo_plugin").exists())
            self.assertFalse(any(item["name"] == "demo_ping" for item in manager.command_specs()))

    def test_reload_reflects_updated_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "source"
            plugins_root = root / "plugins_target"
            state_path = root / "plugin_state.json"
            source_root.mkdir(parents=True, exist_ok=True)
            source_dir = self._copy_demo_plugin(source_root)
            manager = PluginManager(plugin_root=plugins_root, state_path=state_path)
            installed = manager.install_plugin(str(source_dir))
            self.assertTrue(installed["ok"])

            manifest_path = plugins_root / "demo_plugin" / "manifest.py"
            text = manifest_path.read_text(encoding="utf-8")
            manifest_path.write_text(text.replace('version="0.1.0"', 'version="9.9.9"'), encoding="utf-8")
            manager.reload()
            plugins = manager.list_plugins()
            self.assertTrue(any(item["name"] == "demo_plugin" and item["version"] == "9.9.9" for item in plugins))

    def test_plugin_manager_normalizes_manifest_contract_fields_for_legacy_plugins(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "source"
            plugins_root = root / "plugins_target"
            state_path = root / "plugin_state.json"
            source_root.mkdir(parents=True, exist_ok=True)
            source_dir = self._copy_demo_plugin(source_root)
            manifest_path = source_dir / "manifest.py"
            manifest_path.write_text(
                "\n".join(
                    [
                        "from dataclasses import dataclass",
                        "",
                        "@dataclass(frozen=True)",
                        "class PluginManifest:",
                        "    name: str",
                        "    version: str",
                        "    description: str",
                        "    enabled_by_default: bool = True",
                        "    commercial: bool = False",
                        "    dependencies: tuple[str, ...] = ()",
                        "",
                        "def manifest() -> PluginManifest:",
                        "    return PluginManifest(",
                        "        name='demo_plugin',",
                        "        version='0.2.0',",
                        "        description='legacy manifest plugin',",
                        "        enabled_by_default=True,",
                        "        commercial=False,",
                        "        dependencies=(),",
                        "    )",
                    ]
                ),
                encoding="utf-8",
            )

            manager = PluginManager(plugin_root=plugins_root, state_path=state_path)
            installed = manager.install_plugin(str(source_dir))
            self.assertTrue(installed["ok"])

            plugins = manager.list_plugins()
            item = next(plugin for plugin in plugins if plugin["name"] == "demo_plugin")
            self.assertEqual(item["version"], "0.2.0")
            self.assertEqual(item["api_version"], "1")
            self.assertEqual(item["plugin_kind"], "generic")
            self.assertEqual(item["distribution"], "bundled")
            self.assertEqual(item["min_host_version"], "0.1.0")

    def test_runtime_executes_demo_plugin_command_and_respects_disable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tools = ToolRegistry()
            tools._plugin_manager = PluginManager(state_path=Path(tmpdir) / "plugin_state.json")
            runtime = AgentCliRuntime(tools=tools, agent=_PluginFakeAgent())

            response = runtime.handle_prompt("/demo_ping hello")
            self.assertEqual([event.name for event in response.tool_events], ["demo_echo"])
            self.assertIn("demo_plugin responded: hello", response.assistant_text)
            self.assertEqual(response.tool_events[0].payload["text"], "hello")

            disabled = runtime.handle_prompt("/plugin_disable demo_plugin")
            self.assertTrue(disabled.tool_events[0].ok)

            after_disable = runtime.handle_prompt("/demo_ping hello")
            self.assertEqual(after_disable.tool_events, [])
            self.assertIn("未知命令: /demo_ping", after_disable.assistant_text)

    def test_runtime_plugin_disable_all_turns_off_every_plugin(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tools = ToolRegistry()
            tools._plugin_manager = PluginManager(state_path=Path(tmpdir) / "plugin_state.json")
            runtime = AgentCliRuntime(tools=tools, agent=_PluginFakeAgent())

            ping_before = runtime.handle_prompt("/demo_ping hello")
            self.assertTrue(ping_before.tool_events and ping_before.tool_events[0].ok)

            disabled_all = runtime.handle_prompt("/plugin_disable --all")
            self.assertTrue(disabled_all.tool_events and disabled_all.tool_events[0].ok)
            payload = dict(disabled_all.tool_events[0].payload or {})
            self.assertGreaterEqual(int(payload.get("disabled_count") or 0), 1)
            self.assertEqual(disabled_all.tool_events[0].name, "plugin_disable")
            listed_plugins = list(payload.get("plugins") or [])
            self.assertTrue(listed_plugins)
            self.assertTrue(all(not bool(item.get("enabled")) for item in listed_plugins))

            ping_after = runtime.handle_prompt("/demo_ping hello")
            self.assertEqual(ping_after.tool_events, [])
            self.assertIn("未知命令: /demo_ping", ping_after.assistant_text)

    def test_runtime_plugin_install_reload_remove_commands(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "source"
            source_root.mkdir(parents=True, exist_ok=True)
            source_dir = self._copy_demo_plugin(source_root)
            tools = ToolRegistry()
            tools._plugin_manager = PluginManager(
                plugin_root=root / "plugins_target",
                state_path=root / "plugin_state.json",
            )
            runtime = AgentCliRuntime(tools=tools, agent=_PluginFakeAgent())

            install = runtime.handle_prompt(f"/plugin_install \"{source_dir}\"")
            self.assertTrue(install.tool_events[0].ok)
            self.assertEqual(install.tool_events[0].name, "plugin_install")

            reload_resp = runtime.handle_prompt("/plugin_reload")
            self.assertTrue(reload_resp.tool_events[0].ok)
            self.assertEqual(reload_resp.tool_events[0].name, "plugin_reload")

            ping = runtime.handle_prompt("/demo_ping live")
            self.assertTrue(ping.tool_events and ping.tool_events[0].ok)

            remove = runtime.handle_prompt("/plugin_remove demo_plugin")
            self.assertTrue(remove.tool_events[0].ok)
            self.assertEqual(remove.tool_events[0].name, "plugin_remove")

            ping_after = runtime.handle_prompt("/demo_ping live")
            self.assertEqual(ping_after.tool_events, [])

    def test_plugin_manager_collects_connector_and_trigger_registrations_from_runtime_hooks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "source"
            plugins_root = root / "plugins_target"
            state_path = root / "plugin_state.json"
            source_root.mkdir(parents=True, exist_ok=True)
            source_dir = self._copy_demo_plugin(source_root)
            runtime_path = source_dir / "runtime.py"
            runtime_path.write_text(
                "\n".join(
                    [
                        "from cli.agent_cli.host.plugin_hooks import RuntimeHooks",
                        "",
                        "def _connectors(plugin_name: str):",
                        "    return [",
                        "        {",
                        "            'connector_key': 'demo_webhook',",
                        "            'display_name': 'Demo Webhook',",
                        "            'version': '1',",
                        "            'connector_kind': 'inbound',",
                        "            'supports_webhook': True,",
                        "            'supports_polling': False,",
                        "            'supports_actions': False,",
                        "            'event_types': ['demo.event'],",
                        "            'action_types': [],",
                        "            'metadata': {'source': plugin_name},",
                        "        }",
                        "    ]",
                        "",
                        "def _triggers():",
                        "    return [",
                        "        TriggerRegistration(",
                        "            trigger_key='demo_trigger',",
                        "            plugin_name='demo_plugin',",
                        "            trigger_kind='event',",
                        "            connector_key='demo_webhook',",
                        "            event_types=['demo.event'],",
                        "            workflow_name='handle_demo_event',",
                        "            priority=10,",
                        "        )",
                        "    ]",
                        "",
                        "from cli.agent_cli.gateway_core.models import TriggerRegistration",
                        "",
                        "def runtime_hooks():",
                        "    return RuntimeHooks(",
                        "        build_connector_registrations=_connectors,",
                        "        build_trigger_registrations=_triggers,",
                        "    )",
                    ]
                ),
                encoding="utf-8",
            )

            manager = PluginManager(plugin_root=plugins_root, state_path=state_path)
            installed = manager.install_plugin(str(source_dir))
            self.assertTrue(installed["ok"])

            plugins = manager.list_plugins()
            self.assertTrue(any(item["name"] == "demo_plugin" and item["connector_count"] == 1 for item in plugins))
            self.assertTrue(any(item["name"] == "demo_plugin" and item["trigger_count"] == 1 for item in plugins))

            connectors = manager.connector_registrations()
            triggers = manager.trigger_registrations()
            self.assertEqual(len(connectors), 1)
            self.assertEqual(len(triggers), 1)
            self.assertIsInstance(connectors[0], ConnectorRegistration)
            self.assertIsInstance(triggers[0], TriggerRegistration)
            self.assertEqual(connectors[0].metadata["source"], "demo_plugin")
            self.assertEqual(triggers[0].workflow_name, "handle_demo_event")
            self.assertEqual(manager.connector_registrations_for_plugin("demo_plugin")[0].connector_key, "demo_webhook")
            self.assertEqual(manager.trigger_registrations_for_plugin("demo_plugin")[0].trigger_key, "demo_trigger")

    def test_plugin_manager_collects_policy_registrations_from_runtime_hooks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "source"
            plugins_root = root / "plugins_target"
            state_path = root / "plugin_state.json"
            source_root.mkdir(parents=True, exist_ok=True)
            source_dir = self._copy_demo_plugin(source_root)
            runtime_path = source_dir / "runtime.py"
            runtime_path.write_text(
                "\n".join(
                    [
                        "from cli.agent_cli.host.plugin_hooks import RuntimeHooks",
                        "",
                        "def _policies(plugin_name: str):",
                        "    return [",
                        "        {",
                        "            'policy_key': 'demo_policy',",
                        "            'display_name': 'Demo Approval Policy',",
                        "            'version': '1',",
                        "            'policy_kind': 'approval',",
                        "            'description': 'Guard outbound actions',",
                        "            'applies_to': ['action.request'],",
                        "            'metadata': {'owner': plugin_name},",
                        "        }",
                        "    ]",
                        "",
                        "def runtime_hooks():",
                        "    return RuntimeHooks(",
                        "        build_policy_registrations=_policies,",
                        "    )",
                    ]
                ),
                encoding="utf-8",
            )

            manager = PluginManager(plugin_root=plugins_root, state_path=state_path)
            installed = manager.install_plugin(str(source_dir))
            self.assertTrue(installed["ok"])

            plugins = manager.list_plugins()
            self.assertTrue(any(item["name"] == "demo_plugin" and item["policy_count"] == 1 for item in plugins))

            policies = manager.policy_registrations()
            self.assertEqual(len(policies), 1)
            self.assertIsInstance(policies[0], PolicyRegistration)
            self.assertEqual(policies[0].policy_key, "demo_policy")
            self.assertEqual(policies[0].metadata["owner"], "demo_plugin")
            self.assertEqual(manager.policy_registrations_for_plugin("demo_plugin")[0].policy_kind, "approval")

    def test_plugin_manager_rejects_duplicate_connector_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "source"
            plugins_root = root / "plugins_target"
            state_path = root / "plugin_state.json"
            source_root.mkdir(parents=True, exist_ok=True)
            source_dir = self._copy_demo_plugin(source_root)
            runtime_path = source_dir / "runtime.py"
            runtime_path.write_text(
                "\n".join(
                    [
                        "from cli.agent_cli.host.plugin_hooks import RuntimeHooks",
                        "",
                        "def runtime_hooks():",
                        "    return RuntimeHooks(",
                        "        build_connector_registrations=lambda plugin_name='demo_plugin': [",
                        "            {",
                        "                'connector_key': 'demo_webhook',",
                        "                'display_name': 'Demo Webhook A',",
                        "                'version': '1',",
                        "                'connector_kind': 'inbound',",
                        "                'event_types': ['demo.event'],",
                        "                'action_types': [],",
                        "            },",
                        "            {",
                        "                'connector_key': 'demo_webhook',",
                        "                'display_name': 'Demo Webhook B',",
                        "                'version': '1',",
                        "                'connector_kind': 'inbound',",
                        "                'event_types': ['demo.event'],",
                        "                'action_types': [],",
                        "            },",
                        "        ],",
                        "    )",
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, r"duplicate connector_key 'demo_webhook'.*demo_plugin"):
                manager = PluginManager(plugin_root=plugins_root, state_path=state_path)
                manager.install_plugin(str(source_dir))

    def test_plugin_manager_rejects_duplicate_trigger_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "source"
            plugins_root = root / "plugins_target"
            state_path = root / "plugin_state.json"
            source_root.mkdir(parents=True, exist_ok=True)
            source_dir = self._copy_demo_plugin(source_root)
            runtime_path = source_dir / "runtime.py"
            runtime_path.write_text(
                "\n".join(
                    [
                        "from cli.agent_cli.host.plugin_hooks import RuntimeHooks",
                        "",
                        "def runtime_hooks():",
                        "    return RuntimeHooks(",
                        "        build_trigger_registrations=lambda: [",
                        "            {",
                        "                'trigger_key': 'demo_trigger',",
                        "                'plugin_name': 'demo_plugin',",
                        "                'trigger_kind': 'event',",
                        "                'connector_key': 'demo_webhook',",
                        "                'event_types': ['demo.event'],",
                        "                'workflow_name': 'workflow_a',",
                        "            },",
                        "            {",
                        "                'trigger_key': 'demo_trigger',",
                        "                'plugin_name': 'demo_plugin',",
                        "                'trigger_kind': 'event',",
                        "                'connector_key': 'demo_webhook',",
                        "                'event_types': ['demo.event'],",
                        "                'workflow_name': 'workflow_b',",
                        "            },",
                        "        ],",
                        "    )",
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, r"duplicate trigger_key 'demo_trigger'.*demo_plugin"):
                manager = PluginManager(plugin_root=plugins_root, state_path=state_path)
                manager.install_plugin(str(source_dir))

    def test_plugin_manager_rejects_duplicate_policy_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "source"
            plugins_root = root / "plugins_target"
            state_path = root / "plugin_state.json"
            source_root.mkdir(parents=True, exist_ok=True)
            source_dir = self._copy_demo_plugin(source_root)
            runtime_path = source_dir / "runtime.py"
            runtime_path.write_text(
                "\n".join(
                    [
                        "from cli.agent_cli.host.plugin_hooks import RuntimeHooks",
                        "",
                        "def runtime_hooks():",
                        "    return RuntimeHooks(",
                        "        build_policy_registrations=lambda plugin_name='demo_plugin': [",
                        "            {",
                        "                'policy_key': 'demo_policy',",
                        "                'display_name': 'Policy A',",
                        "                'version': '1',",
                        "                'policy_kind': 'approval',",
                        "                'applies_to': ['action.request'],",
                        "            },",
                        "            {",
                        "                'policy_key': 'demo_policy',",
                        "                'display_name': 'Policy B',",
                        "                'version': '1',",
                        "                'policy_kind': 'approval',",
                        "                'applies_to': ['action.request'],",
                        "            },",
                        "        ],",
                        "    )",
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, r"duplicate policy_key 'demo_policy'.*demo_plugin"):
                manager = PluginManager(plugin_root=plugins_root, state_path=state_path)
                manager.install_plugin(str(source_dir))

    def test_plugin_manager_collects_workflow_handler_registrations_from_runtime_hooks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "source"
            plugins_root = root / "plugins_target"
            state_path = root / "plugin_state.json"
            source_root.mkdir(parents=True, exist_ok=True)
            source_dir = self._copy_demo_plugin(source_root)
            runtime_path = source_dir / "runtime.py"
            runtime_path.write_text(
                "\n".join(
                    [
                        "from cli.agent_cli.host.plugin_hooks import RuntimeHooks",
                        "",
                        "def _handle_demo_event(*, event, decision, workflow_run, runtime=None):",
                        "    return {'status': 'ok', 'reasoning_summary': 'demo workflow handled event'}",
                        "",
                        "def runtime_hooks():",
                        "    return RuntimeHooks(",
                        "        build_workflow_handlers=lambda plugin_name='demo_plugin': [",
                        "            {",
                        "                'workflow_name': 'handle_demo_event',",
                        "                'plugin_name': plugin_name,",
                        "                'description': 'Demo workflow handler',",
                        "                'handler': _handle_demo_event,",
                        "            },",
                        "        ],",
                        "    )",
                    ]
                ),
                encoding="utf-8",
            )

            manager = PluginManager(plugin_root=plugins_root, state_path=state_path)
            installed = manager.install_plugin(str(source_dir))
            self.assertTrue(installed["ok"])

            plugins = manager.list_plugins()
            self.assertTrue(any(item["name"] == "demo_plugin" and item["workflow_count"] == 1 for item in plugins))

            handlers = manager.workflow_handler_registrations()
            self.assertEqual(len(handlers), 1)
            self.assertIsInstance(handlers[0], RegisteredWorkflowHandler)
            self.assertEqual(handlers[0].workflow_name, "handle_demo_event")
            self.assertEqual(handlers[0].description, "Demo workflow handler")
            self.assertTrue(callable(handlers[0].handler))
            self.assertEqual(
                manager.workflow_handler_registrations_for_plugin("demo_plugin")[0].workflow_name,
                "handle_demo_event",
            )
            self.assertEqual(
                manager.get_workflow_handler(plugin_name="demo_plugin", workflow_name="handle_demo_event").workflow_name,
                "handle_demo_event",
            )

    def test_plugin_manager_rejects_duplicate_workflow_name_within_plugin(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "source"
            plugins_root = root / "plugins_target"
            state_path = root / "plugin_state.json"
            source_root.mkdir(parents=True, exist_ok=True)
            source_dir = self._copy_demo_plugin(source_root)
            runtime_path = source_dir / "runtime.py"
            runtime_path.write_text(
                "\n".join(
                    [
                        "from cli.agent_cli.host.plugin_hooks import RuntimeHooks",
                        "",
                        "def _handler_a():",
                        "    return {'status': 'ok'}",
                        "",
                        "def _handler_b():",
                        "    return {'status': 'ok'}",
                        "",
                        "def runtime_hooks():",
                        "    return RuntimeHooks(",
                        "        build_workflow_handlers=lambda plugin_name='demo_plugin': [",
                        "            {",
                        "                'workflow_name': 'handle_demo_event',",
                        "                'plugin_name': plugin_name,",
                        "                'handler': _handler_a,",
                        "            },",
                        "            {",
                        "                'workflow_name': 'handle_demo_event',",
                        "                'plugin_name': plugin_name,",
                        "                'handler': _handler_b,",
                        "            },",
                        "        ],",
                        "    )",
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, r"duplicate workflow_name 'handle_demo_event' for plugin 'demo_plugin'"):
                manager = PluginManager(plugin_root=plugins_root, state_path=state_path)
                manager.install_plugin(str(source_dir))
