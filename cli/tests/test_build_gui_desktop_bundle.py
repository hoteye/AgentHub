from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "build_gui_desktop_bundle.py"
SPEC = importlib.util.spec_from_file_location("build_gui_desktop_bundle", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BuildGuiDesktopBundleScriptTest(unittest.TestCase):
    def test_bundle_directory_name_includes_normalized_version(self) -> None:
        self.assertEqual(
            MODULE.bundle_directory_name(
                base_name="agenthub-gui-desktop",
                version="gui-v1.2.3",
                platform_tag="windows-x86_64",
            ),
            "agenthub-gui-desktop-1.2.3-windows-x86_64",
        )

    def test_archive_suffix_is_platform_aware(self) -> None:
        self.assertEqual(MODULE.archive_suffix("Windows"), ".zip")
        self.assertEqual(MODULE.archive_suffix("Linux"), ".tar.gz")
        self.assertEqual(MODULE.archive_suffix("Darwin"), ".tar.gz")

    def test_write_launchers_emits_unix_and_windows_entrypoints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_root = Path(temp_dir)
            MODULE.write_launchers(bundle_root)

            self.assertTrue((bundle_root / "start_gui_desktop.sh").exists())
            self.assertTrue((bundle_root / "start_gui_desktop.cmd").exists())
            self.assertTrue((bundle_root / "start_gui_desktop.ps1").exists())

            unix_launcher = (bundle_root / "start_gui_desktop.sh").read_text(encoding="utf-8")
            cmd_launcher = (bundle_root / "start_gui_desktop.cmd").read_text(encoding="utf-8")

            self.assertIn("Electron.app/Contents/MacOS/Electron", unix_launcher)
            self.assertIn("electron.exe", cmd_launcher)

    def test_write_bundle_manifest_records_release_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_root = Path(temp_dir)
            with patch.object(MODULE.platform, "system", return_value="Windows"):
                MODULE.write_bundle_manifest(
                    bundle_root,
                    bundle_name="agenthub-gui-desktop",
                    version="v2.0.0",
                    platform_tag="windows-x86_64",
                    archive_name="agenthub-gui-desktop-2.0.0-windows-x86_64.zip",
                    obfuscation_level="minimal",
                    obfuscation_summary={"python_sources_removed": 12},
                )

            manifest = json.loads((bundle_root / "release-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["distribution_kind"], "portable_bundle")
            self.assertEqual(manifest["version"], "2.0.0")
            self.assertEqual(manifest["archive_format"], "zip")
            self.assertEqual(manifest["obfuscation_level"], "minimal")
            self.assertEqual(manifest["obfuscation_summary"]["python_sources_removed"], 12)
            self.assertIn("start_gui_desktop.cmd", manifest["launchers"])

    def test_package_bundle_creates_zip_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle_root = root / "agenthub-gui-desktop-1.2.3-windows-x86_64"
            artifact_dir = root / "artifacts"
            bundle_root.mkdir()
            artifact_dir.mkdir()
            (bundle_root / "hello.txt").write_text("hello\n", encoding="utf-8")

            with patch.object(MODULE.platform, "system", return_value="Windows"):
                archive_path = MODULE.package_bundle(bundle_root, artifact_dir)

            self.assertEqual(archive_path.name, "agenthub-gui-desktop-1.2.3-windows-x86_64.zip")
            with zipfile.ZipFile(archive_path, "r") as archive:
                self.assertIn(f"{bundle_root.name}/hello.txt", archive.namelist())

    def test_apply_minimal_obfuscation_compiles_selected_runtime_tree_to_sourceless_pyc(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_root = Path(temp_dir)
            module_root = bundle_root / "cli" / "agent_cli" / "gateway_api"
            module_root.mkdir(parents=True)
            (bundle_root / "cli" / "__init__.py").write_text("", encoding="utf-8")
            (bundle_root / "cli" / "agent_cli" / "__init__.py").write_text("", encoding="utf-8")
            (module_root / "__init__.py").write_text("", encoding="utf-8")
            (module_root / "gui_http_server.py").write_text("print('sourceless-ok')\n", encoding="utf-8")

            plugin_root = bundle_root / "plugins" / "demo_plugin"
            plugin_root.mkdir(parents=True)
            (plugin_root / "manifest.py").write_text("PLUGIN = 'demo'\n", encoding="utf-8")

            summary = MODULE.apply_minimal_obfuscation(bundle_root)

            self.assertGreater(summary["python_sources_removed"], 0)
            self.assertFalse((module_root / "gui_http_server.py").exists())
            self.assertTrue((module_root / "gui_http_server.pyc").exists())
            self.assertTrue((plugin_root / "manifest.py").exists())

            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import sys; "
                        f"sys.path.insert(0, {str(bundle_root)!r}); "
                        "import cli.agent_cli.gateway_api.gui_http_server"
                    ),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("sourceless-ok", completed.stdout)
