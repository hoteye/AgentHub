from __future__ import annotations

import importlib.util
import io
import json
import stat
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "prepare_codex_sidecar_runtime.py"
SPEC = importlib.util.spec_from_file_location("prepare_codex_sidecar_runtime", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PrepareCodexSidecarRuntimeTest(unittest.TestCase):
    def test_release_version_prefers_rust_tag_semver(self) -> None:
        self.assertEqual(MODULE.release_version({"tag_name": "rust-v0.129.0"}), "0.129.0")

    def test_select_assets_for_linux_x86_64(self) -> None:
        payload = _release_payload(
            tag="rust-v0.129.0",
            asset_names=[
                "codex-app-server-x86_64-unknown-linux-musl.tar.gz",
                "codex-npm-linux-x64-0.129.0.tgz",
                "bwrap-x86_64-unknown-linux-musl.tar.gz",
            ],
        )

        selected = MODULE.select_assets(payload, MODULE.PLATFORM_SPECS["linux-x86_64"])

        self.assertEqual(
            selected.app_server.name,
            "codex-app-server-x86_64-unknown-linux-musl.tar.gz",
        )
        self.assertEqual(selected.npm_platform.name, "codex-npm-linux-x64-0.129.0.tgz")
        self.assertIsNotNone(selected.bwrap)
        assert selected.bwrap is not None
        self.assertEqual(selected.bwrap.name, "bwrap-x86_64-unknown-linux-musl.tar.gz")

    def test_install_runtime_bundle_extracts_app_server_rg_bwrap_and_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app_server_archive = root / "codex-app-server-x86_64-unknown-linux-musl.tar.gz"
            npm_archive = root / "codex-npm-linux-x64-0.129.0.tgz"
            bwrap_archive = root / "bwrap-x86_64-unknown-linux-musl.tar.gz"
            _tar_with_files(
                app_server_archive,
                {"codex-app-server-x86_64-unknown-linux-musl": b"#!/bin/sh\n"},
            )
            _tar_with_files(
                npm_archive,
                {"package/vendor/x86_64-unknown-linux-musl/path/rg": b"#!/bin/sh\n"},
            )
            _tar_with_files(
                bwrap_archive,
                {"bwrap-x86_64-unknown-linux-musl": b"#!/bin/sh\n"},
            )
            runtime_root = root / "runtime" / "codex"
            payload = _release_payload(
                tag="rust-v0.129.0",
                asset_names=[
                    app_server_archive.name,
                    npm_archive.name,
                    bwrap_archive.name,
                ],
            )

            bundle_root = MODULE.install_runtime_bundle(
                runtime_root=runtime_root,
                platform_spec=MODULE.PLATFORM_SPECS["linux-x86_64"],
                runtime_version="rust-v0.129.0",
                release_payload=payload,
                app_server_archive=app_server_archive,
                npm_platform_archive=npm_archive,
                bwrap_archive=bwrap_archive,
            )

            app_server = bundle_root / "codex-app-server"
            rg = bundle_root / "path" / "rg"
            bwrap = bundle_root / "codex-resources" / "bwrap"
            self.assertTrue(app_server.exists())
            self.assertTrue(rg.exists())
            self.assertTrue(bwrap.exists())
            self.assertTrue(app_server.stat().st_mode & stat.S_IXUSR)
            self.assertTrue(rg.stat().st_mode & stat.S_IXUSR)
            self.assertTrue(bwrap.stat().st_mode & stat.S_IXUSR)

            manifest = json.loads((bundle_root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["sourceRepo"], "openai/codex")
            self.assertEqual(manifest["entrypoint"], "codex-app-server")
            self.assertEqual(manifest["args"], ["--listen", "stdio://"])
            self.assertEqual(manifest["pathEntries"], ["path"])
            self.assertEqual(manifest["resources"]["bwrap"], "codex-resources/bwrap")
            self.assertNotIn("runtimeRoot", manifest)

            root_manifest = json.loads((runtime_root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(root_manifest["defaultVersion"], "rust-v0.129.0")
            self.assertEqual(
                root_manifest["platforms"]["linux-x86_64"]["binary"],
                "linux-x86_64/rust-v0.129.0/codex-app-server",
            )

    def test_copy_archive_member_rejects_missing_member(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "empty.tar.gz"
            _tar_with_files(archive, {"other": b"data"})

            with self.assertRaises(FileNotFoundError):
                MODULE.copy_archive_member(
                    archive,
                    root / "out",
                    matcher=lambda name: name.endswith("/missing"),
                )

    def test_download_asset_retries_and_reuses_cached_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            calls = {"count": 0}

            def opener(request, *, timeout=0):
                calls["count"] += 1
                if calls["count"] == 1:
                    raise OSError("temporary network failure")
                return _FakeResponse(b"downloaded")

            original_urlopen = MODULE.urllib.request.urlopen
            original_sleep = MODULE.time.sleep
            MODULE.urllib.request.urlopen = opener
            MODULE.time.sleep = lambda _seconds: None
            try:
                asset = MODULE.download_asset(
                    MODULE.ReleaseAsset(name="asset.tgz", url="https://example.invalid/asset.tgz"),
                    download_dir=root,
                    retries=1,
                )
                cached = MODULE.download_asset(
                    MODULE.ReleaseAsset(name="asset.tgz", url="https://example.invalid/asset.tgz"),
                    download_dir=root,
                    retries=1,
                )
            finally:
                MODULE.urllib.request.urlopen = original_urlopen
                MODULE.time.sleep = original_sleep

            self.assertEqual(calls["count"], 2)
            self.assertEqual(asset.size, len(b"downloaded"))
            self.assertEqual(cached.size, len(b"downloaded"))
            self.assertEqual((root / "asset.tgz").read_bytes(), b"downloaded")


def _release_payload(*, tag: str, asset_names: list[str]) -> dict[str, object]:
    return {
        "tag_name": tag,
        "assets": [
            {
                "name": name,
                "browser_download_url": f"https://example.invalid/{name}",
                "size": 10,
            }
            for name in asset_names
        ],
    }


def _tar_with_files(path: Path, files: dict[str, bytes]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            info.mode = 0o755
            archive.addfile(info, io.BytesIO(content))


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def __enter__(self) -> io.BytesIO:
        return io.BytesIO(self._data)

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


if __name__ == "__main__":
    unittest.main()
