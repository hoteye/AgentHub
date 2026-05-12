from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cli.agent_cli.tools_core.apply_patch_bridge import (
    execute_apply_patch,
    execute_apply_patch_result,
    evaluate_apply_patch_requirement,
    preview_apply_patch,
)


def _assert_success_output(testcase: unittest.TestCase, text: str, *expected_lines: str) -> None:
    testcase.assertTrue(text.startswith("Exit code: 0\nWall time: "))
    testcase.assertIn("\nOutput:\n", text)
    for line in expected_lines:
        testcase.assertIn(line, text)


class ApplyPatchBridgeTest(unittest.TestCase):
    def test_apply_patch_adds_and_updates_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "demo.txt"
            source.write_text("hello\n", encoding="utf-8")

            patch = """*** Begin Patch
*** Add File: notes.txt
+first line
*** Update File: demo.txt
@@
-hello
+hello world
*** End Patch"""

            event = execute_apply_patch(patch_text=patch, workspace_root=root)

            self.assertTrue(event.ok)
            self.assertEqual(event.name, "apply_patch")
            self.assertEqual(source.read_text(encoding="utf-8"), "hello world\n")
            self.assertEqual((root / "notes.txt").read_text(encoding="utf-8"), "first line\n")
            self.assertEqual(event.payload["file_count"], 2)
            self.assertEqual(event.payload["added_count"], 1)
            self.assertEqual(event.payload["updated_count"], 1)
            _assert_success_output(
                self,
                event.payload["function_call_output"],
                "Success. Updated the following files:",
                "A notes.txt",
                "M demo.txt",
            )
            self.assertTrue(event.payload["function_call_output_model_visible"])

    def test_apply_patch_supports_move(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "before.txt"
            source.write_text("alpha\n", encoding="utf-8")

            patch = """*** Begin Patch
*** Update File: before.txt
*** Move to: after.txt
@@
-alpha
+beta
*** End Patch"""

            event = execute_apply_patch(patch_text=patch, workspace_root=root)

            self.assertTrue(event.ok)
            self.assertFalse(source.exists())
            self.assertEqual((root / "after.txt").read_text(encoding="utf-8"), "beta\n")
            self.assertEqual(event.payload["moved_count"], 1)

    def test_apply_patch_rejects_workspace_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            patch = """*** Begin Patch
*** Add File: ../escape.txt
+oops
*** End Patch"""

            event = execute_apply_patch(patch_text=patch, workspace_root=root)

            self.assertFalse(event.ok)
            self.assertIn("path escapes workspace root", str(event.payload.get("error") or ""))
            self.assertEqual(event.payload["function_call_output"], event.payload["error"])
            self.assertTrue(event.payload["function_call_output_model_visible"])

    def test_apply_patch_keeps_legacy_malformed_add_file_error_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            event = execute_apply_patch(
                patch_text="""*** Begin Patch
*** Add File: notes.txt
first line
*** End Patch""",
                workspace_root=root,
            )

            self.assertFalse(event.ok)
            self.assertIn("invalid add-file line", str(event.payload.get("error") or ""))

    def test_preview_apply_patch_returns_change_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "demo.txt").write_text("hello\n", encoding="utf-8")

            preview = preview_apply_patch(
                patch_text="""*** Begin Patch
*** Add File: notes.txt
+first line
*** Update File: demo.txt
@@
-hello
+hello world
*** End Patch""",
                workspace_root=root,
            )

            self.assertEqual(preview["file_count"], 2)
            self.assertEqual(preview["added_count"], 1)
            self.assertEqual(preview["updated_count"], 1)
            self.assertEqual(preview["changes"][0]["path"], "notes.txt")
            self.assertEqual(preview["request_kind"], "raw_patch")
            self.assertEqual(preview["function_call_name"], "apply_patch")
            self.assertEqual(
                preview["function_call_arguments"],
                {
                    "patch": """*** Begin Patch
*** Add File: notes.txt
+first line
*** Update File: demo.txt
@@
-hello
+hello world
*** End Patch"""
                },
            )

    def test_apply_patch_requirement_is_skip_when_policy_is_never(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            patch = """*** Begin Patch
*** Add File: notes.txt
+first line
*** End Patch"""

            requirement = evaluate_apply_patch_requirement(
                patch_text=patch,
                workspace_root=root,
                approval_policy="never",
                sandbox_mode="workspace-write",
            )

            self.assertEqual(requirement["requirement"], "skip")
            self.assertEqual(requirement["reason_code"], "apply_patch_allowed")
            self.assertEqual(requirement["matched_rules"][0]["source"], "policy_axis")
            self.assertIsNone(requirement["proposed_rule"])
            self.assertEqual(requirement["normalized_segments"], ["notes.txt"])
            self.assertEqual(requirement["evidence"]["function_call_arguments"], {"patch": patch})
            self.assertTrue(requirement["evidence"]["preview_ok"])
            self.assertEqual(requirement["evidence"]["changes"][0]["path"], "notes.txt")

    def test_apply_patch_requirement_requests_approval_when_policy_demands_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "demo.txt").write_text("hello\n", encoding="utf-8")
            patch = """*** Begin Patch
*** Update File: demo.txt
@@
-hello
+hello world
*** End Patch"""

            requirement = evaluate_apply_patch_requirement(
                patch_text=patch,
                workspace_root=root,
                approval_policy="on-request",
                sandbox_mode="danger-full-access",
            )

            self.assertEqual(requirement["requirement"], "needs_approval")
            self.assertEqual(requirement["reason_code"], "apply_patch_approval_required")
            self.assertEqual(requirement["matched_rules"][0]["source"], "policy_axis")
            self.assertEqual(requirement["normalized_segments"], ["demo.txt"])
            self.assertTrue(requirement["evidence"]["preview_ok"])
            self.assertEqual(requirement["evidence"]["changes"][0]["path"], "demo.txt")

    def test_apply_patch_requirement_is_forbidden_when_sandbox_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "demo.txt").write_text("hello\n", encoding="utf-8")
            patch = """*** Begin Patch
*** Update File: demo.txt
@@
-hello
+hello world
*** End Patch"""

            requirement = evaluate_apply_patch_requirement(
                patch_text=patch,
                workspace_root=root,
                approval_policy="never",
                sandbox_mode="read-only",
            )

            self.assertEqual(requirement["requirement"], "forbidden")
            self.assertEqual(requirement["reason_code"], "apply_patch_sandbox_read_only")
            self.assertEqual(requirement["matched_rules"][0]["source"], "sandbox_requirement")
            self.assertTrue(requirement["evidence"]["preview_ok"])
            self.assertEqual(requirement["evidence"]["changes"][0]["path"], "demo.txt")

    def test_apply_patch_requirement_preserves_preview_error_and_replay_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            patch = """*** Begin Patch
*** Add File: ../escape.txt
+oops
*** End Patch"""

            requirement = evaluate_apply_patch_requirement(
                patch_text=patch,
                workspace_root=root,
                approval_policy="on-request",
                sandbox_mode="workspace-write",
            )

            self.assertEqual(requirement["requirement"], "forbidden")
            self.assertEqual(requirement["reason_code"], "apply_patch_preview_invalid")
            self.assertEqual(requirement["matched_rules"][0]["source"], "preview_validation")
            self.assertEqual(requirement["normalized_segments"], ["raw_patch"])
            self.assertFalse(requirement["evidence"]["preview_ok"])
            self.assertEqual(requirement["evidence"]["function_call_arguments"], {"patch": patch})
            self.assertIn("path escapes workspace root", requirement["evidence"]["preview_error"])

    def test_apply_patch_requirement_preserves_structured_write_projection_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload = json.dumps(
                {
                    "operation": "file_write",
                    "file_path": "src/hello.py",
                    "content": "print('hello')\n",
                    "source_tool_name": "Write",
                    "guard_profile": "claude_write",
                }
            )

            requirement = evaluate_apply_patch_requirement(
                patch_text=payload,
                workspace_root=root,
                approval_policy="unless-trusted",
                sandbox_mode="workspace-write",
            )

            self.assertEqual(requirement["requirement"], "needs_approval")
            self.assertEqual(requirement["normalized_segments"], ["src/hello.py"])
            self.assertTrue(requirement["evidence"]["preview_ok"])
            self.assertEqual(requirement["evidence"]["request_kind"], "structured_write")
            self.assertEqual(requirement["evidence"]["function_call_name"], "Write")
            self.assertEqual(requirement["evidence"]["source_tool_name"], "Write")
            self.assertEqual(requirement["evidence"]["guard_profile"], "claude_write")
            self.assertEqual(
                requirement["evidence"]["function_call_arguments"],
                {
                    "file_path": "src/hello.py",
                    "content": "print('hello')\n",
                },
            )

    def test_execute_apply_patch_result_emits_structured_item_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "demo.txt").write_text("hello\n", encoding="utf-8")

            patch = """*** Begin Patch
*** Update File: demo.txt
@@
-hello
+hello world
*** End Patch"""

            result = execute_apply_patch_result(patch_text=patch, workspace_root=root)

            self.assertEqual(result.assistant_text, "Apply workspace patch.")
            self.assertEqual(len(result.tool_events), 1)
            self.assertEqual([item["type"] for item in result.item_events], ["item.started", "item.completed"])
            completed_item = dict(result.item_events[-1]["item"])
            self.assertEqual(completed_item["type"], "mcp_tool_call")
            self.assertEqual(completed_item["tool"], "apply_patch")
            self.assertEqual(completed_item["status"], "completed")
            result_text = completed_item["result"]["content"][0]["text"]
            _assert_success_output(
                self,
                result_text,
                "Success. Updated the following files:",
                "M demo.txt",
            )
            _assert_success_output(
                self,
                result.tool_events[0].payload["function_call_output"],
                "Success. Updated the following files:",
                "M demo.txt",
            )

    def test_apply_patch_supports_structured_file_write_in_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            event = execute_apply_patch(
                patch_text=json.dumps(
                    {
                        "operation": "file_write",
                        "file_path": "src/ranges.py",
                        "content": "def normalize_ranges():\n    return []\n",
                    }
                ),
                workspace_root=root,
            )

            self.assertTrue(event.ok)
            self.assertEqual((root / "src" / "ranges.py").read_text(encoding="utf-8"), "def normalize_ranges():\n    return []\n")
            self.assertEqual(event.payload["request_kind"], "structured_write")
            self.assertEqual(event.payload["changes"][0]["change_type"], "add")
            self.assertEqual(event.payload["function_call_name"], "apply_patch")
            self.assertEqual(
                event.payload["function_call_arguments"],
                {
                    "file_path": "src/ranges.py",
                    "content": "def normalize_ranges():\n    return []\n",
                },
            )

    def test_apply_patch_rejects_mixed_structured_write_and_edit_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            event = execute_apply_patch(
                patch_text=json.dumps(
                    {
                        "operation": "file_write",
                        "file_path": "src/ranges.py",
                        "content": "def normalize_ranges():\n    return []\n",
                        "old_string": "TODO",
                        "new_string": "DONE",
                    }
                ),
                workspace_root=root,
            )

            self.assertFalse(event.ok)
            self.assertIn(
                "structured file_write cannot mix content with old_string/new_string",
                str(event.payload.get("error") or ""),
            )

    def test_apply_patch_preserves_write_projection_metadata_for_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            event = execute_apply_patch(
                patch_text=json.dumps(
                    {
                        "operation": "file_write",
                        "file_path": "src/hello.py",
                        "content": "print('hello')\n",
                        "source_tool_name": "Write",
                        "guard_profile": "claude_write",
                    }
                ),
                workspace_root=root,
            )

            self.assertTrue(event.ok)
            self.assertEqual(event.payload["function_call_name"], "Write")
            self.assertEqual(event.payload["source_tool_name"], "Write")
            self.assertEqual(event.payload["guard_profile"], "claude_write")
            self.assertEqual(
                event.payload["function_call_arguments"],
                {
                    "file_path": "src/hello.py",
                    "content": "print('hello')\n",
                },
            )

    def test_apply_patch_supports_structured_unique_edit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "README.md"
            target.write_text("Status: TODO\n", encoding="utf-8")

            event = execute_apply_patch(
                patch_text=json.dumps(
                    {
                        "operation": "file_edit",
                        "file_path": "README.md",
                        "old_string": "TODO",
                        "new_string": "DONE",
                    }
                ),
                workspace_root=root,
            )

            self.assertTrue(event.ok)
            self.assertEqual(target.read_text(encoding="utf-8"), "Status: DONE\n")
            self.assertEqual(event.payload["request_kind"], "structured_edit")
            self.assertEqual(event.payload["changes"][0]["match_count"], 1)

    def test_apply_patch_preserves_edit_projection_metadata_for_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "README.md"
            target.write_text("Status: TODO\n", encoding="utf-8")

            event = execute_apply_patch(
                patch_text=json.dumps(
                    {
                        "operation": "file_edit",
                        "file_path": "README.md",
                        "old_string": "TODO",
                        "new_string": "DONE",
                        "source_tool_name": "Edit",
                        "guard_profile": "claude_edit",
                    }
                ),
                workspace_root=root,
            )

            self.assertTrue(event.ok)
            self.assertEqual(event.payload["function_call_name"], "Edit")
            self.assertEqual(event.payload["source_tool_name"], "Edit")
            self.assertEqual(event.payload["guard_profile"], "claude_edit")
            self.assertEqual(
                event.payload["function_call_arguments"],
                {
                    "file_path": "README.md",
                    "old_string": "TODO",
                    "new_string": "DONE",
                },
            )

    def test_apply_patch_structured_edit_rejects_ambiguous_match_without_replace_all(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text("TODO\nTODO\n", encoding="utf-8")

            event = execute_apply_patch(
                patch_text=json.dumps(
                    {
                        "operation": "file_edit",
                        "file_path": "README.md",
                        "old_string": "TODO",
                        "new_string": "DONE",
                    }
                ),
                workspace_root=root,
            )

            self.assertFalse(event.ok)
            self.assertIn("must appear exactly once", str(event.payload.get("error") or ""))

    def test_apply_patch_structured_edit_replace_all_updates_all_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "README.md"
            target.write_text("TODO\nTODO\n", encoding="utf-8")

            event = execute_apply_patch(
                patch_text=json.dumps(
                    {
                        "operation": "file_edit",
                        "file_path": "README.md",
                        "old_string": "TODO",
                        "new_string": "DONE",
                        "replace_all": True,
                    }
                ),
                workspace_root=root,
            )

            self.assertTrue(event.ok)
            self.assertEqual(target.read_text(encoding="utf-8"), "DONE\nDONE\n")
            self.assertTrue(event.payload["changes"][0]["replace_all"])
            self.assertEqual(event.payload["changes"][0]["match_count"], 2)

    def test_apply_patch_preserves_raw_patch_request_metadata_for_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "demo.txt").write_text("hello\n", encoding="utf-8")

            patch = """*** Begin Patch
*** Update File: demo.txt
@@
-hello
+hello world
*** End Patch"""

            event = execute_apply_patch(patch_text=patch, workspace_root=root)

            self.assertTrue(event.ok)
            self.assertEqual(event.payload["request_kind"], "raw_patch")
            self.assertEqual(event.payload["function_call_name"], "apply_patch")
            self.assertEqual(event.payload["function_call_arguments"], {"patch": patch})

    def test_apply_patch_failure_preserves_raw_patch_request_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            patch = """*** Begin Patch
*** Add File: notes.txt
+hello"""

            event = execute_apply_patch(patch_text=patch, workspace_root=root)

            self.assertFalse(event.ok)
            self.assertEqual(event.payload["request_kind"], "raw_patch")
            self.assertEqual(event.payload["function_call_name"], "apply_patch")
            self.assertEqual(event.payload["function_call_arguments"], {"patch": patch})
            self.assertIn("the last line of the patch must be", str(event.payload.get("error") or ""))
