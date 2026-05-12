import unittest

from cli.agent_cli.host import plugin_manager, plugin_types  # noqa: E402

class PluginTypesCompatibilityTest(unittest.TestCase):
    def test_plugin_manager_reexports_extracted_types(self):
        self.assertIs(plugin_manager.PluginId, plugin_types.PluginId)
        self.assertIs(plugin_manager.PluginStoreError, plugin_types.PluginStoreError)
        self.assertIs(plugin_manager.RegisteredCommand, plugin_types.RegisteredCommand)
        self.assertIs(plugin_manager.RegisteredTool, plugin_types.RegisteredTool)
        self.assertIs(plugin_manager.RegisteredWorkflowHandler, plugin_types.RegisteredWorkflowHandler)
        self.assertIs(plugin_manager.LoadedPlugin, plugin_types.LoadedPlugin)
        self.assertIs(plugin_manager.PluginCommandRegistry, plugin_types.PluginCommandRegistry)
        self.assertIs(plugin_manager.PluginToolRegistry, plugin_types.PluginToolRegistry)

    def test_plugin_id_parse_still_available_from_plugin_manager(self):
        plugin_id = plugin_manager.PluginId.parse("demo@debug")

        self.assertEqual(plugin_id.plugin_name, "demo")
        self.assertEqual(plugin_id.marketplace_name, "debug")
        self.assertEqual(plugin_id.as_key(), "demo@debug")
