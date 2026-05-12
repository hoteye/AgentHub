from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
import cli.agent_cli.tools as tools_module
from cli.agent_cli.tools_core import tools_helper_runtime

class ToolsHelperRuntimeTest(unittest.TestCase):
    def test_apply_patch_bridge_compat_delegates_to_workspace_runtime(self) -> None:
        event = ToolEvent(name="apply_patch", ok=True, summary="patched", payload={"ok": True})
        result = CommandExecutionResult(assistant_text="patched")

        with patch.object(tools_helper_runtime.workspace_file_runtime, "apply_patch", return_value=event) as apply_mock:
            returned = tools_helper_runtime.ApplyPatchBridgeCompat.execute_apply_patch(
                patch_text="*** Begin Patch\n*** End Patch",
                workspace_root=Path("/tmp/workspace"),
            )

        self.assertIs(returned, event)
        apply_mock.assert_called_once_with(
            patch_text="*** Begin Patch\n*** End Patch",
            workspace_root=Path("/tmp/workspace"),
        )

        with patch.object(tools_helper_runtime.workspace_file_runtime, "apply_patch_result", return_value=result) as result_mock:
            returned_result = tools_helper_runtime.ApplyPatchBridgeCompat.execute_apply_patch_result(
                patch_text="*** Begin Patch\n*** End Patch",
                workspace_root=Path("/tmp/workspace"),
                call_structured_helper=lambda *args, **kwargs: None,
                result_from_event=lambda *args, **kwargs: CommandExecutionResult(assistant_text="fallback"),
                apply_patch_call=lambda patch_text: event,
            )

        self.assertIs(returned_result, result)
        result_mock.assert_called_once()

    def test_tool_registry_module_helpers_delegate_to_runtime_seam(self) -> None:
        with patch.object(tools_helper_runtime, "find_tools_project_root", return_value=Path("/tmp/root")) as find_mock:
            self.assertEqual(Path("/tmp/root"), tools_module._find_project_root())
        find_mock.assert_called_once()

        with patch.object(tools_helper_runtime, "json_safe_value", return_value={"ok": True}) as json_mock:
            self.assertEqual({"ok": True}, tools_module._json_safe({"raw": object()}))
        json_mock.assert_called_once()

        with patch.object(tools_helper_runtime, "load_project_tool", return_value=object()) as load_mock:
            returned = tools_module._load_project_tool_module("office_tools")
        self.assertIsNotNone(returned)
        load_mock.assert_called_once()
