from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cli.agent_cli.tools_core.file_tools_bridge import (
    file_list,
    file_list_result,
    file_read,
    file_read_result,
    file_search,
    file_search_result,
    glob_files,
    glob_files_result,
    grep_files,
    grep_files_result,
    list_dir,
    list_dir_result,
    read_file,
    read_file_result,
)
from cli.agent_cli.models import ToolEvent, tool_event_is_soft_failure
from cli.agent_cli.runtime_core.event_rendering import activity_events_for_tool_event

class FileToolsBridgeTest(unittest.TestCase):
    def test_glob_files_returns_structured_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docs").mkdir()
            alpha = root / "docs" / "alpha.md"
            beta = root / "docs" / "beta.md"
            alpha.write_text("alpha\n", encoding="utf-8")
            beta.write_text("beta\n", encoding="utf-8")
            os.utime(alpha, (1_700_000_000, 1_700_000_000))
            os.utime(beta, (1_700_000_100, 1_700_000_100))

            event = glob_files(workspace_root=root, pattern="*.md", path="docs", limit=10)

            self.assertTrue(event.ok)
            self.assertEqual(event.payload["count"], 2)
            self.assertEqual(event.payload["paths"], ["docs/alpha.md", "docs/beta.md"])
            self.assertEqual(event.payload["text"], "docs/alpha.md\ndocs/beta.md")
            self.assertIn(event.payload["engine"], {"rg", "python"})

    def test_glob_files_empty_result_is_soft_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docs").mkdir()
            (root / "docs" / "notes.txt").write_text("hello\n", encoding="utf-8")

            event = glob_files(workspace_root=root, pattern="*.md", path="docs", limit=5)

            self.assertFalse(event.ok)
            self.assertTrue(tool_event_is_soft_failure(event))
            self.assertEqual(event.payload["count"], 0)
            self.assertEqual(event.payload["paths"], [])
            self.assertEqual(event.payload["text"], "No files found.")
            self.assertEqual(event.summary, "No files found.")

    def test_glob_files_rejects_workspace_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            event = glob_files(workspace_root=root, pattern="*.md", path="../outside", limit=5)

            self.assertFalse(event.ok)
            self.assertIn("path escapes workspace root", str(event.payload.get("error") or ""))

    def test_glob_files_defaults_to_cwd_when_project_root_is_broader(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cwd = root / "cli"
            docs = root / "docs"
            cwd.mkdir()
            docs.mkdir()
            (docs / "design.md").write_text("hello\n", encoding="utf-8")

            event = glob_files(workspace_root=root, cwd_root=cwd, pattern="**/*.md", limit=10)

            self.assertFalse(event.ok)
            self.assertEqual(event.payload["requested_path"], ".")
            self.assertEqual(event.payload["path"], ".")
            self.assertEqual(event.payload["paths"], [])

    def test_glob_files_allows_explicit_project_root_path_from_nested_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cwd = root / "cli"
            docs = root / "docs"
            cwd.mkdir()
            docs.mkdir()
            target = docs / "design.md"
            target.write_text("hello\n", encoding="utf-8")

            event = glob_files(
                workspace_root=root,
                cwd_root=cwd,
                pattern="**/design.md",
                path=str(root),
                limit=10,
            )

            self.assertTrue(event.ok)
            self.assertEqual(event.payload["path"], str(root.resolve()))
            self.assertEqual(event.payload["paths"], [str(target.resolve())])

    def test_grep_files_returns_path_only_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            alpha = root / "src" / "alpha.py"
            beta = root / "src" / "beta.py"
            alpha.write_text("needle\n", encoding="utf-8")
            beta.write_text("prefix needle suffix\n", encoding="utf-8")
            (root / "src" / "gamma.txt").write_text("needle\n", encoding="utf-8")
            os.utime(alpha, (1_700_000_000, 1_700_000_000))
            os.utime(beta, (1_700_000_100, 1_700_000_100))

            with patch("cli.agent_cli.tools_core.file_tools_bridge.shutil.which", return_value=None):
                event = grep_files(workspace_root=root, pattern="needle", include="*.py", path="src", limit=10)

            self.assertTrue(event.ok)
            self.assertEqual(event.payload["count"], 2)
            self.assertEqual(event.payload["paths"], ["src/beta.py", "src/alpha.py"])
            self.assertEqual(event.payload["text"], "src/beta.py\nsrc/alpha.py")
            self.assertEqual(
                event.payload["function_call_output"],
                f"{(root / 'src' / 'beta.py').resolve()}\n{(root / 'src' / 'alpha.py').resolve()}",
            )
            self.assertTrue(event.payload["function_call_output_model_visible"])
            self.assertEqual(event.payload["engine"], "python")

    def test_grep_files_prefers_rg_output_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            with patch("cli.agent_cli.tools_core.file_tools_bridge.shutil.which", return_value="/usr/bin/rg"):
                with patch("cli.agent_cli.tools_core.file_tools_bridge.subprocess.run") as run_mock:
                    run_mock.return_value.returncode = 0
                    run_mock.return_value.stdout = "src/beta.py\nsrc/alpha.py\n"

                    event = grep_files(workspace_root=root, pattern="needle", include="*.py", path="src", limit=10)

            self.assertTrue(event.ok)
            self.assertEqual(event.payload["engine"], "rg")
            self.assertEqual(event.payload["paths"], ["src/beta.py", "src/alpha.py"])
            self.assertEqual(event.payload["text"], "src/beta.py\nsrc/alpha.py")
            self.assertEqual(
                event.payload["function_call_output"],
                f"{(root / 'src' / 'beta.py').resolve()}\n{(root / 'src' / 'alpha.py').resolve()}",
            )
            self.assertTrue(event.payload["function_call_output_model_visible"])

    def test_grep_files_empty_result_uses_reference_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "logs").mkdir()
            (root / "logs" / "output.txt").write_text("no hits here\n", encoding="utf-8")

            event = grep_files(workspace_root=root, pattern="needle", path="logs", limit=5)

            self.assertFalse(event.ok)
            self.assertTrue(tool_event_is_soft_failure(event))
            self.assertEqual(event.payload["count"], 0)
            self.assertEqual(event.payload["paths"], [])
            self.assertEqual(event.payload["text"], "No matches found.")
            self.assertNotIn("function_call_output", event.payload)
            self.assertEqual(event.summary, "No matches found.")

    def test_grep_files_allows_explicit_project_root_path_from_nested_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cwd = root / "cli"
            docs = root / "docs"
            cwd.mkdir()
            docs.mkdir()
            target = docs / "design.md"
            target.write_text("needle\n", encoding="utf-8")

            with patch("cli.agent_cli.tools_core.file_tools_bridge.shutil.which", return_value=None):
                event = grep_files(
                    workspace_root=root,
                    cwd_root=cwd,
                    pattern="needle",
                    path=str(root),
                    limit=10,
                )

            self.assertTrue(event.ok)
            self.assertEqual(event.payload["path"], str(root.resolve()))
            self.assertEqual(event.payload["paths"], [str(target.resolve())])

    def test_list_dir_returns_reference_style_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base = root / "sample_dir"
            base.mkdir()
            (base / "alpha.txt").write_text("first file\n", encoding="utf-8")
            (base / "nested").mkdir()

            event = list_dir(workspace_root=root, dir_path=str(base.resolve()), offset=1, limit=2, depth=1)

            self.assertTrue(event.ok)
            self.assertEqual(event.payload["count"], 2)
            self.assertEqual(event.payload["text"], "E1: [file] alpha.txt\nE2: [dir] nested")
            self.assertEqual(
                event.payload["entries"],
                [
                    {"index": 1, "kind": "file", "path": "alpha.txt"},
                    {"index": 2, "kind": "dir", "path": "nested"},
                ],
            )
            self.assertEqual(
                event.payload["function_call_output"],
                f"Absolute path: {base.resolve()}\nalpha.txt\nnested/",
            )
            self.assertTrue(event.payload["function_call_output_model_visible"])

    def test_list_dir_depth_two_includes_children_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base = root / "depth_two"
            base.mkdir()
            (base / "alpha.txt").write_text("alpha\n", encoding="utf-8")
            nested = base / "nested"
            nested.mkdir()
            (nested / "beta.txt").write_text("beta\n", encoding="utf-8")
            deeper = nested / "grand"
            deeper.mkdir()
            (deeper / "gamma.txt").write_text("gamma\n", encoding="utf-8")

            event = list_dir(workspace_root=root, dir_path=str(base.resolve()), offset=1, limit=10, depth=2)

            self.assertTrue(event.ok)
            self.assertEqual(
                event.payload["text"],
                "E1: [file] alpha.txt\nE2: [dir] nested\nE3: [file] nested/beta.txt\nE4: [dir] nested/grand",
            )
            self.assertEqual(
                event.payload["function_call_output"],
                f"Absolute path: {base.resolve()}\nalpha.txt\nnested/\n  beta.txt\n  grand/",
            )

    def test_list_dir_rejects_relative_dir_path_and_surfaces_error_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base = root / "sample_dir"
            base.mkdir()

            event = list_dir(workspace_root=root, dir_path="sample_dir", offset=1, limit=2, depth=1)

            self.assertFalse(event.ok)
            self.assertEqual(event.payload["error"], "dir_path must be an absolute path")
            self.assertEqual(event.payload["function_call_output"], "dir_path must be an absolute path")
            self.assertTrue(event.payload["function_call_output_model_visible"])

    def test_file_search_is_legacy_alias_of_grep_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "src" / "alpha.py").write_text("needle\n", encoding="utf-8")
            (root / "src" / "beta.py").write_text("needle\n", encoding="utf-8")

            event = file_search(workspace_root=root, query="needle", path="src", limit=10)

            self.assertTrue(event.ok)
            self.assertEqual(event.payload["compatibility_alias"], "grep_files")
            self.assertEqual(event.payload["engine"], "compat:grep_files")
            self.assertEqual(event.payload["matches"], [{"path": "src/alpha.py"}, {"path": "src/beta.py"}])
            self.assertEqual(event.payload["text"], "src/alpha.py\nsrc/beta.py")

    def test_file_search_empty_result_is_soft_failure_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "src" / "alpha.py").write_text("hello\n", encoding="utf-8")

            event = file_search(workspace_root=root, query="needle", path="src", limit=10)

            self.assertFalse(event.ok)
            self.assertTrue(tool_event_is_soft_failure(event))
            self.assertEqual(event.payload["compatibility_alias"], "grep_files")
            self.assertEqual(event.payload["text"], "No matches found.")

    def test_file_list_is_legacy_alias_of_list_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.txt").write_text("alpha\n", encoding="utf-8")
            nested = root / "docs"
            nested.mkdir()
            (nested / "b.md").write_text("beta\n", encoding="utf-8")

            event = file_list(workspace_root=root, limit=10)

            self.assertTrue(event.ok)
            self.assertEqual(event.payload["compatibility_alias"], "list_dir")
            self.assertEqual(event.payload["engine"], "compat:list_dir")
            self.assertEqual([item["path"] for item in event.payload["files"]], ["a.txt", "docs/b.md"])

    def test_file_read_returns_line_slice_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "demo.py"
            target.write_text("print('a')\nprint('b')\nprint('c')\n", encoding="utf-8")

            event = file_read(workspace_root=root, path="demo.py", offset=2, limit=2)

            self.assertTrue(event.ok)
            self.assertFalse(event.payload["truncated"])
            self.assertEqual(event.payload["mode"], "slice")
            self.assertEqual(event.payload["path"], "demo.py")
            self.assertEqual(event.payload["offset"], 2)
            self.assertEqual(event.payload["limit"], 2)
            self.assertEqual(event.payload["returned_line_count"], 2)
            self.assertEqual(event.payload["excerpt_lines"][0]["line"], 2)
            self.assertEqual(event.payload["text"], "L2: print('b')\nL3: print('c')")

    def test_file_read_keeps_legacy_max_chars_mode_for_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "demo.py"
            target.write_text("print('a')\nprint('b')\n", encoding="utf-8")

            event = file_read(workspace_root=root, path="demo.py", max_chars=8)

            self.assertTrue(event.ok)
            self.assertTrue(event.payload["truncated"])
            self.assertEqual(event.payload["mode"], "chars")
            self.assertEqual(event.payload["path"], "demo.py")
            self.assertEqual(event.payload["excerpt_lines"][0]["line"], 1)

    def test_read_file_uses_canonical_name_and_line_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "sample.txt"
            target.write_text("first\nsecond\nthird\nfourth\n", encoding="utf-8")

            event = read_file(workspace_root=root, file_path=str(target.resolve()), offset=2, limit=2)

            self.assertTrue(event.ok)
            self.assertEqual(event.name, "read_file")
            self.assertEqual(event.payload["file_path"], str(target.resolve()))
            self.assertEqual(event.payload["text"], "L2: second\nL3: third")

    def test_read_file_rejects_relative_file_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "sample.txt"
            target.write_text("first\nsecond\n", encoding="utf-8")

            event = read_file(workspace_root=root, file_path="sample.txt", offset=1, limit=2)

            self.assertFalse(event.ok)
            self.assertEqual(event.payload["error"], "file_path must be an absolute path")
            self.assertEqual(event.payload["file_path"], "sample.txt")
            self.assertEqual(event.payload["function_call_output"], "file_path must be an absolute path")
            self.assertTrue(event.payload["function_call_output_model_visible"])

    def test_read_file_allows_explicit_project_root_file_from_nested_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cwd = root / "cli"
            docs = root / "docs"
            cwd.mkdir()
            docs.mkdir()
            target = docs / "sample.txt"
            target.write_text("first\nsecond\n", encoding="utf-8")

            event = read_file(
                workspace_root=root,
                cwd_root=cwd,
                file_path=str(target),
                offset=1,
                limit=2,
            )

            self.assertTrue(event.ok)
            self.assertEqual(event.payload["file_path"], str(target.resolve()))
            self.assertEqual(event.payload["text"], "L1: first\nL2: second")

    def test_read_file_indentation_mode_captures_block(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "sample.rs"
            target.write_text(
                "fn outer() {\n"
                "    if cond {\n"
                "        inner();\n"
                "    }\n"
                "    tail();\n"
                "}\n",
                encoding="utf-8",
            )

            event = read_file(
                workspace_root=root,
                file_path=str(target.resolve()),
                offset=3,
                limit=10,
                mode="indentation",
                indentation={
                    "anchor_line": 3,
                    "include_siblings": False,
                    "max_levels": 1,
                },
            )

            self.assertTrue(event.ok)
            self.assertEqual(event.payload["mode"], "indentation")
            self.assertEqual(
                event.payload["text"],
                "L2:     if cond {\nL3:         inner();\nL4:     }",
            )

    def test_read_file_indentation_mode_can_include_siblings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "sample.py"
            target.write_text(
                "class Foo:\n"
                "    def __init__(self, size):\n"
                "        self.size = size\n"
                "    def double(self, value):\n"
                "        if value is None:\n"
                "            return 0\n"
                "        result = value * self.size\n"
                "        return result\n"
                "class Bar:\n"
                "    def compute(self):\n"
                "        helper = Foo(2)\n"
                "        return helper.double(5)\n",
                encoding="utf-8",
            )

            event = read_file(
                workspace_root=root,
                file_path=str(target.resolve()),
                offset=1,
                limit=200,
                mode="indentation",
                indentation={
                    "anchor_line": 7,
                    "include_siblings": True,
                    "max_levels": 1,
                },
            )

            self.assertTrue(event.ok)
            self.assertEqual(
                event.payload["text"],
                "L2:     def __init__(self, size):\n"
                "L3:         self.size = size\n"
                "L4:     def double(self, value):\n"
                "L5:         if value is None:\n"
                "L6:             return 0\n"
                "L7:         result = value * self.size\n"
                "L8:         return result",
            )

    def test_file_read_rejects_workspace_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            event = file_read(workspace_root=root, path="../escape.txt")

            self.assertFalse(event.ok)
            self.assertIn("path escapes workspace root", str(event.payload.get("error") or ""))

    def test_grep_files_result_emits_structured_item_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "one.txt").write_text("hello world\n", encoding="utf-8")

            result = grep_files_result(workspace_root=root, pattern="hello", limit=5)

            expected_output = str((root / "one.txt").resolve())
            self.assertEqual(result.assistant_text, expected_output)
            self.assertEqual([item["type"] for item in result.item_events], ["item.started", "item.completed"])
            self.assertEqual(result.item_events[-1]["item"]["tool"], "grep_files")
            self.assertEqual(
                result.item_events[-1]["item"]["result"]["content"][0]["text"],
                expected_output,
            )

    def test_glob_files_result_emits_structured_item_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docs").mkdir()
            (root / "docs" / "one.txt").write_text("hello world\n", encoding="utf-8")

            result = glob_files_result(workspace_root=root, pattern="*.txt", path="docs", limit=5)

            self.assertEqual(result.assistant_text, "docs/one.txt")
            self.assertEqual([item["type"] for item in result.item_events], ["item.started", "item.completed"])
            self.assertEqual(result.item_events[-1]["item"]["tool"], "glob_files")

    def test_grep_files_empty_result_emits_completed_item_with_result_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "one.txt").write_text("hello world\n", encoding="utf-8")

            result = grep_files_result(workspace_root=root, pattern="needle", limit=5)

            completed = result.item_events[-1]["item"]
            self.assertEqual(completed["tool"], "grep_files")
            self.assertEqual(completed["status"], "completed")
            self.assertIsNone(completed["error"])
            self.assertEqual(completed["result"]["content"][0]["text"], "No matches found.")

    def test_file_search_activity_rendering_uses_paths_for_compat_alias(self) -> None:
        event = ToolEvent(
            name="file_search",
            ok=True,
            summary="file matches=2",
            payload={
                "count": 2,
                "query": "needle",
                "path": "src",
                "matches": [{"path": "src/alpha.py"}, {"path": "src/beta.py"}],
                "compatibility_alias": "grep_files",
            },
        )

        rendered = activity_events_for_tool_event(event)[0]
        self.assertEqual(rendered.title, "Searched files")
        self.assertIn("legacy_alias=file_search", rendered.detail)
        self.assertIn("src/alpha.py", rendered.detail)
        self.assertIn("src/beta.py", rendered.detail)
        self.assertNotIn("None", rendered.detail)

    def test_glob_files_activity_rendering_uses_structured_fields(self) -> None:
        event = ToolEvent(
            name="glob_files",
            ok=True,
            summary="files=2",
            payload={
                "count": 2,
                "pattern": "**/*.md",
                "path": "docs",
                "paths": ["docs/a.md", "docs/b.md"],
            },
        )

        rendered = activity_events_for_tool_event(event)[0]
        self.assertEqual(rendered.title, "Matched files")
        self.assertIn("pattern=**/*.md", rendered.detail)
        self.assertIn("path=docs", rendered.detail)
        self.assertIn("docs/a.md", rendered.detail)

    def test_list_dir_result_emits_structured_item_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.txt").write_text("alpha\n", encoding="utf-8")

            result = list_dir_result(workspace_root=root, dir_path=str(root.resolve()), limit=5, depth=2)

            self.assertEqual(result.assistant_text, f"Absolute path: {root.resolve()}\na.txt")
            self.assertEqual([item["type"] for item in result.item_events], ["item.started", "item.completed"])
            self.assertEqual(result.item_events[-1]["item"]["tool"], "list_dir")

    def test_list_dir_result_surfaces_error_text_to_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.txt").write_text("alpha\n", encoding="utf-8")

            result = list_dir_result(workspace_root=root, dir_path=".", limit=5, depth=2)

            self.assertEqual(result.assistant_text, "dir_path must be an absolute path")
            self.assertEqual([item["type"] for item in result.item_events], ["item.started", "item.completed"])
            self.assertEqual(
                result.item_events[-1]["item"]["error"]["message"],
                "dir_path must be an absolute path",
            )

    def test_file_list_result_emits_structured_item_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.txt").write_text("alpha\n", encoding="utf-8")

            result = file_list_result(workspace_root=root, path=".", limit=5)

            self.assertEqual(result.assistant_text, "files=1")
            self.assertEqual(len(result.tool_events), 1)
            self.assertEqual([item["type"] for item in result.item_events], ["item.started", "item.completed"])
            completed_item = dict(result.item_events[-1]["item"])
            self.assertEqual(completed_item["type"], "mcp_tool_call")
            self.assertEqual(completed_item["tool"], "file_list")
            self.assertEqual(completed_item["status"], "completed")

    def test_file_search_and_read_results_emit_structured_item_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "one.txt").write_text("hello world\n", encoding="utf-8")

            search = file_search_result(workspace_root=root, query="hello", limit=5)
            legacy_read = file_read_result(workspace_root=root, path="one.txt", offset=1, limit=1)
            canonical_read = read_file_result(
                workspace_root=root,
                file_path=str((root / "one.txt").resolve()),
                offset=1,
                limit=1,
            )

            self.assertEqual([item["type"] for item in search.item_events], ["item.started", "item.completed"])
            self.assertEqual(search.item_events[-1]["item"]["tool"], "file_search")
            self.assertEqual([item["type"] for item in legacy_read.item_events], ["item.started", "item.completed"])
            self.assertEqual(legacy_read.item_events[-1]["item"]["tool"], "file_read")
            self.assertEqual([item["type"] for item in canonical_read.item_events], ["item.started", "item.completed"])
            self.assertEqual(canonical_read.item_events[-1]["item"]["tool"], "read_file")

    def test_read_file_result_surfaces_error_text_to_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "one.txt").write_text("hello world\n", encoding="utf-8")

            canonical_read = read_file_result(workspace_root=root, file_path="one.txt", offset=1, limit=1)

            self.assertEqual(canonical_read.assistant_text, "file_path must be an absolute path")
            self.assertEqual([item["type"] for item in canonical_read.item_events], ["item.started", "item.completed"])
            self.assertEqual(
                canonical_read.item_events[-1]["item"]["error"]["message"],
                "file_path must be an absolute path",
            )
