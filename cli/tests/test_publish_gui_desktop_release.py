from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "publish_gui_desktop_release.py"
SPEC = importlib.util.spec_from_file_location("publish_gui_desktop_release", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PublishGuiDesktopReleaseScriptTest(unittest.TestCase):
    def test_stable_artifact_name_strips_version_segment(self) -> None:
        self.assertEqual(
            MODULE.stable_artifact_name(
                "agenthub-gui-desktop-1.2.3-linux-x86_64.tar.gz",
                "gui-v1.2.3",
            ),
            "agenthub-gui-desktop-linux-x86_64.tar.gz",
        )

    def test_build_artifact_plan_emits_versioned_and_stable_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_path = Path(temp_dir) / "agenthub-gui-desktop-1.2.3-linux-x86_64.tar.gz"
            artifact_path.write_bytes(b"demo-bundle")

            plan = MODULE.build_artifact_plan(
                local_path=artifact_path,
                version="1.2.3",
                root_prefix="downloads",
                versioned_subdir="gui",
                include_stable_alias=True,
            )

            self.assertEqual(
                plan.versioned_remote_path,
                "downloads/gui/v1.2.3/agenthub-gui-desktop-1.2.3-linux-x86_64.tar.gz",
            )
            self.assertEqual(
                plan.versioned_checksum_path,
                "downloads/gui/v1.2.3/agenthub-gui-desktop-1.2.3-linux-x86_64.tar.gz.sha256",
            )
            self.assertEqual(
                plan.stable_remote_path, "downloads/agenthub-gui-desktop-linux-x86_64.tar.gz"
            )
            self.assertEqual(
                plan.stable_checksum_path,
                "downloads/agenthub-gui-desktop-linux-x86_64.tar.gz.sha256",
            )
            self.assertEqual(plan.size_bytes, len(b"demo-bundle"))

    def test_build_release_manifest_payload_records_public_and_source_urls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_path = Path(temp_dir) / "agenthub-gui-desktop-1.2.3-windows-x86_64.zip"
            artifact_path.write_bytes(b"zip-demo")

            plan = MODULE.build_artifact_plan(
                local_path=artifact_path,
                version="v1.2.3",
                root_prefix="downloads",
                versioned_subdir="gui",
                include_stable_alias=True,
            )
            payload = MODULE.build_release_manifest_payload(
                version="v1.2.3",
                artifact_plans=[plan],
                root_prefix="downloads",
                versioned_subdir="gui",
                source_base_url="https://dl.pressget.cn:8443",
                public_base_url="https://pressget.cn",
                manifest_name="release-manifest.json",
            )

            self.assertEqual(payload["version"], "1.2.3")
            self.assertEqual(
                payload["release_manifest"]["latest_public_url"],
                "https://pressget.cn/downloads/gui/latest/release-manifest.json",
            )
            artifact = payload["artifacts"][0]
            self.assertEqual(
                artifact["versioned"]["artifact_public_url"],
                "https://pressget.cn/downloads/gui/v1.2.3/agenthub-gui-desktop-1.2.3-windows-x86_64.zip",
            )
            self.assertEqual(
                artifact["stable"]["artifact_public_url"],
                "https://pressget.cn/downloads/agenthub-gui-desktop-windows-x86_64.zip",
            )

    def test_discover_artifacts_filters_sha256_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_dir = Path(temp_dir)
            expected = artifact_dir / "agenthub-gui-desktop-1.2.3-linux-x86_64.tar.gz"
            expected.write_bytes(b"linux")
            (artifact_dir / "agenthub-gui-desktop-1.2.3-linux-x86_64.tar.gz.sha256").write_text(
                "ignore\n", encoding="utf-8"
            )
            (artifact_dir / "agenthub-gui-desktop-1.2.3-windows-x86_64.zip").write_bytes(b"windows")

            discovered = MODULE.discover_artifacts(artifact_dir, "1.2.3")

            self.assertEqual(
                [path.name for path in discovered],
                sorted([expected.name, "agenthub-gui-desktop-1.2.3-windows-x86_64.zip"]),
            )

    def test_manifest_bytes_is_json_with_trailing_newline(self) -> None:
        payload = {"version": "1.2.3", "artifacts": []}
        encoded = MODULE.manifest_bytes(payload)
        self.assertTrue(encoded.endswith(b"\n"))
        self.assertEqual(json.loads(encoded.decode("utf-8")), payload)
