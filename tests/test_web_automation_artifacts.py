from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from shared.web_automation.artifacts import (
    MAX_ARTIFACTS_PER_TAB,
    create_artifact_path,
    emit_download_artifact,
    emit_waited_download_artifact,
    emit_pdf_artifact,
    emit_screenshot_artifact,
    record_artifact,
    resolve_existing_artifact_path,
    resolve_artifact_output_path,
    sanitize_artifact_filename,
)
from shared.web_automation.types import BrowserTab

class WebAutomationArtifactsTest(unittest.TestCase):
    def test_emit_artifacts_write_files_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                tab = BrowserTab(
                    tab_id="tab-1",
                    url="https://example.com/report",
                    title="Report",
                    profile="openclaw",
                    text="Report body",
                )

                screenshot = emit_screenshot_artifact(tab)
                pdf = emit_pdf_artifact(tab)

                screenshot_path = Path(screenshot.path)
                pdf_path = Path(pdf.path)
                self.assertTrue(screenshot_path.exists())
                self.assertTrue(pdf_path.exists())
                self.assertGreater(screenshot_path.stat().st_size, 0)
                self.assertGreater(pdf_path.stat().st_size, 0)
                self.assertEqual(screenshot.kind, "screenshot")
                self.assertEqual(pdf.kind, "pdf")
                self.assertEqual(len(tab.artifacts), 2)
            finally:
                os.chdir(old_cwd)

    def test_emit_download_artifact_writes_file_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                tab = BrowserTab(
                    tab_id="tab-dl",
                    url="https://example.com/report",
                    title="Report",
                    profile="openclaw",
                )

                download = emit_download_artifact(tab, ref="r1", suggested_filename="../quarterly report.csv")

                download_path = Path(download.path)
                self.assertTrue(download_path.exists())
                self.assertEqual(download.kind, "download")
                self.assertEqual(download.ref, "r1")
                self.assertEqual(download.suggested_filename, "quarterly-report.csv")
                self.assertTrue(download_path.name.endswith("quarterly-report.csv"))
            finally:
                os.chdir(old_cwd)

    def test_emit_waited_download_artifact_honors_safe_relative_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                tab = BrowserTab(
                    tab_id="tab-wait",
                    url="https://example.com/report",
                    title="Report",
                    profile="openclaw",
                )

                artifact = emit_waited_download_artifact(tab, requested_path="safe/reports/export.csv")

                artifact_path = Path(artifact.path)
                self.assertTrue(artifact_path.exists())
                self.assertTrue(artifact.path.endswith("safe/reports/export.csv"))
            finally:
                os.chdir(old_cwd)

    def test_record_artifact_caps_history_per_tab(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                tab = BrowserTab(
                    tab_id="tab-2",
                    url="https://example.com/app",
                    title="App",
                    profile="openclaw",
                )
                for index in range(MAX_ARTIFACTS_PER_TAB + 3):
                    artifact_path = create_artifact_path("screenshots", f"artifact-{index}.png")
                    artifact_path.write_bytes(b"x")
                    record_artifact(
                        tab,
                        kind="screenshot",
                        path=artifact_path,
                        content_type="image/png",
                        size_bytes=artifact_path.stat().st_size,
                    )

                self.assertEqual(len(tab.artifacts), MAX_ARTIFACTS_PER_TAB)
                self.assertTrue(tab.artifacts[-1].path.endswith(f"artifact-{MAX_ARTIFACTS_PER_TAB + 2}.png"))
            finally:
                os.chdir(old_cwd)

    def test_create_artifact_path_blocks_parent_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with self.assertRaises(ValueError):
                    create_artifact_path("screenshots", "../escape.png")
            finally:
                os.chdir(old_cwd)

    def test_sanitize_artifact_filename_strips_path_escape_and_unsafe_chars(self) -> None:
        self.assertEqual(sanitize_artifact_filename("../a/quarterly report?.csv"), "quarterly-report-.csv")
        self.assertEqual(sanitize_artifact_filename("CON.txt"), "file-CON.txt")

    def test_resolve_artifact_output_path_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with self.assertRaises(ValueError):
                    resolve_artifact_output_path("downloads", "../escape.csv")
            finally:
                os.chdir(old_cwd)

    def test_resolve_artifact_output_path_rejects_reserved_segment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with self.assertRaisesRegex(ValueError, "reserved file name"):
                    resolve_artifact_output_path("downloads", "safe/COM1.csv")
            finally:
                os.chdir(old_cwd)

    def test_resolve_existing_artifact_path_accepts_runtime_artifact_and_blocks_outside_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                artifact_path = create_artifact_path("screenshots", "allowed.png")
                artifact_path.write_bytes(b"png")
                outside_path = Path(temp_dir) / "outside.txt"
                outside_path.write_text("outside", encoding="utf-8")

                resolved = resolve_existing_artifact_path(str(artifact_path))

                self.assertEqual(resolved, artifact_path.resolve())
                with self.assertRaisesRegex(ValueError, "outside runtime artifacts directory"):
                    resolve_existing_artifact_path(str(outside_path))
            finally:
                os.chdir(old_cwd)

    @unittest.skipIf(os.name == "nt", "symlink escape test requires POSIX-style symlink support")
    def test_resolve_artifact_output_path_rejects_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                downloads_root = Path(".web_automation_state/artifacts/downloads")
                downloads_root.mkdir(parents=True, exist_ok=True)
                outside = Path(temp_dir) / "outside"
                outside.mkdir()
                symlink_dir = downloads_root / "link-out"
                symlink_dir.symlink_to(outside, target_is_directory=True)

                with self.assertRaises(ValueError):
                    resolve_artifact_output_path("downloads", "link-out/escape.csv")
            finally:
                os.chdir(old_cwd)
