import sys
import unittest

from cli.agent_cli.host import ProviderHooks, RuntimeHooks
from plugins.demo_plugin.provider import provider_hooks
from plugins.demo_plugin.runtime import runtime_hooks

class PluginContractsTest(unittest.TestCase):
    def test_demo_plugin_provider_hooks_use_contract_type(self):
        hooks = provider_hooks()
        self.assertIsInstance(hooks, ProviderHooks)
        self.assertTrue(any(item.get("name") == "demo_echo" for item in hooks.tool_specs))
        self.assertTrue(hooks.system_prompt_fragments)
        self.assertTrue(hooks.routing_hints)

    def test_demo_plugin_runtime_hooks_use_contract_type(self):
        hooks = runtime_hooks()
        self.assertIsInstance(hooks, RuntimeHooks)
        self.assertIsNone(hooks.pre_route)
        self.assertIsNone(hooks.enrich_local_plan)
        self.assertIsNone(hooks.build_activity_events)
        self.assertIsNone(hooks.build_connector_registrations)
        self.assertIsNone(hooks.build_trigger_registrations)
        self.assertIsNone(hooks.build_policy_registrations)
