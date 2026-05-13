from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import struct
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "build_release.py"
SPEC = importlib.util.spec_from_file_location("build_release", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _collect_add_data_values(command: list[str]) -> list[str]:
    values: list[str] = []
    for index, token in enumerate(command):
        if token == "--add-data" and index + 1 < len(command):
            values.append(command[index + 1])
    return values


class BuildReleaseScriptTest(unittest.TestCase):
    def test_runtime_data_mappings_include_local_prompt_assets_without_reference_baseline_dependency(
        self,
    ) -> None:
        cli_root = ROOT / "cli"
        mappings = dict(MODULE.runtime_data_mappings(root=ROOT, cli=cli_root))

        self.assertEqual(
            mappings[cli_root / "agent_cli" / "prompts"],
            "cli/agent_cli/prompts",
        )
        self.assertEqual(
            mappings[cli_root / "agent_cli" / "providers" / "interaction_profiles"],
            "cli/agent_cli/providers/interaction_profiles",
        )
        self.assertEqual(mappings[ROOT / "LICENSE"], ".")
        self.assertTrue(
            (
                cli_root
                / "agent_cli"
                / "prompts"
                / "reference_parity"
                / "base_instructions"
                / "default.md"
            ).exists()
        )
        self.assertTrue(
            (
                cli_root
                / "agent_cli"
                / "providers"
                / "interaction_profiles"
                / "schema"
                / "interaction_profile.schema.json"
            ).exists()
        )
        self.assertFalse(
            any(
                "reference_baseline" in str(source) or "reference_baseline" in dest
                for source, dest in mappings.items()
            )
        )
        self.assertFalse(any("psbc_policy" in source.parts for source in mappings))
        self.assertFalse(any(".venv" in source.parts for source in mappings))
        self.assertFalse(any("chroma_db" in source.parts for source in mappings))
        self.assertFalse(any("_corpus_cache" in source.parts for source in mappings))
        self.assertFalse(any(source.name == "source_bundle.json" for source in mappings))

    def test_pyinstaller_command_keeps_runtime_data_in_onefile_mode(self) -> None:
        command = MODULE.pyinstaller_command(
            bundle_name="agenthub-cli",
            mode="onefile",
            dist_dir=Path("/tmp/dist"),
            build_dir=Path("/tmp/build"),
            spec_dir=Path("/tmp/spec"),
        )
        separator = ";" if MODULE.os.name == "nt" else ":"
        add_data_values = _collect_add_data_values(command)

        self.assertIn(f"{ROOT / 'config'}{separator}config", add_data_values)
        self.assertIn(f"{ROOT / 'LICENSE'}{separator}.", add_data_values)
        self.assertIn(
            f"{ROOT / 'cli' / 'agent_cli' / 'prompts'}{separator}cli/agent_cli/prompts",
            add_data_values,
        )
        self.assertIn(
            f"{ROOT / 'cli' / 'agent_cli' / 'providers' / 'interaction_profiles'}{separator}cli/agent_cli/providers/interaction_profiles",
            add_data_values,
        )
        self.assertFalse(any("reference_baseline" in token for token in add_data_values))
        self.assertFalse(any("psbc_policy" in token for token in add_data_values))
        self.assertFalse(any(".venv" in token for token in add_data_values))
        self.assertFalse(any("chroma_db" in token for token in add_data_values))
        self.assertFalse(any("_corpus_cache" in token for token in add_data_values))
        self.assertFalse(any("source_bundle.json" in token for token in add_data_values))

    def test_pyinstaller_command_collects_canonical_cli_package(self) -> None:
        command = MODULE.pyinstaller_command(
            bundle_name="agenthub-cli",
            mode="onedir",
            dist_dir=Path("/tmp/dist"),
            build_dir=Path("/tmp/build"),
            spec_dir=Path("/tmp/spec"),
        )

        collect_pairs = [
            command[index + 1]
            for index, token in enumerate(command)
            if token == "--collect-submodules" and index + 1 < len(command)
        ]

        self.assertIn("cli.agent_cli", collect_pairs)

    def test_pyinstaller_command_hidden_imports_dynamic_canonical_cli_modules(self) -> None:
        command = MODULE.pyinstaller_command(
            bundle_name="agenthub-cli",
            mode="onedir",
            dist_dir=Path("/tmp/dist"),
            build_dir=Path("/tmp/build"),
            spec_dir=Path("/tmp/spec"),
        )

        hidden_imports = [
            command[index + 1]
            for index, token in enumerate(command)
            if token == "--hidden-import" and index + 1 < len(command)
        ]

        self.assertIn("cli.agent_cli.headless", hidden_imports)
        self.assertIn("cli.agent_cli.headless_helpers", hidden_imports)
        self.assertIn("cli.agent_cli.headless_entry_runtime", hidden_imports)

    def test_pyinstaller_command_uses_agenthub_icon_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spec_dir = Path(temp_dir) / "spec"
            with patch.object(MODULE.platform, "system", return_value="Windows"):
                command = MODULE.pyinstaller_command(
                    bundle_name="agenthub-cli",
                    mode="onefile",
                    dist_dir=Path(temp_dir) / "dist",
                    build_dir=Path(temp_dir) / "build",
                    spec_dir=spec_dir,
                )

            icon_path = spec_dir / "agenthub.ico"
            self.assertIn("--icon", command)
            self.assertIn(str(icon_path), command)
            self.assertTrue(icon_path.exists())
            icon_bytes = icon_path.read_bytes()
            self.assertEqual(icon_bytes[:4], b"\x00\x00\x01\x00")
            self.assertGreater(icon_path.stat().st_size, 1024)
            first_payload_offset = struct.unpack_from("<I", icon_bytes, 6 + 12)[0]
            self.assertEqual(struct.unpack_from("<I", icon_bytes, first_payload_offset)[0], 40)
            self.assertNotIn(b"\x89PNG", icon_bytes)

    def test_pyinstaller_command_excludes_optional_heavy_modules(self) -> None:
        command = MODULE.pyinstaller_command(
            bundle_name="agenthub-cli",
            mode="onefile",
            dist_dir=Path("/tmp/dist"),
            build_dir=Path("/tmp/build"),
            spec_dir=Path("/tmp/spec"),
        )

        excluded_modules = [
            command[index + 1]
            for index, token in enumerate(command)
            if token == "--exclude-module" and index + 1 < len(command)
        ]

        for module_name in MODULE.PYINSTALLER_OPTIONAL_HEAVY_EXCLUDES:
            self.assertIn(module_name, excluded_modules)

    def test_codex_platform_key_matches_prepared_macos_runtime_key(self) -> None:
        with (
            patch.object(MODULE.packaging_helpers.platform, "system", return_value="Darwin"),
            patch.object(MODULE.packaging_helpers.platform, "machine", return_value="arm64"),
        ):
            self.assertEqual(MODULE.codex_platform_key(), "macos-arm64")

    def test_install_script_cleanup_trap_survives_successful_install(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            version = "9.9.9"
            platform_tag = "linux-x86_64"
            archive_name = f"agenthub-cli-{version}-{platform_tag}.tar.gz"
            bundle_root = root / f"agenthub-cli-{version}-{platform_tag}"
            bundle_root.mkdir()
            executable = bundle_root / "agenthub-cli"
            executable.write_text(
                "#!/usr/bin/env bash\nprintf 'AgentHub test\\n'\n", encoding="utf-8"
            )
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

            archive_path = root / archive_name
            with tarfile.open(archive_path, "w:gz") as archive:
                archive.add(bundle_root, arcname=bundle_root.name)
            digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            checksum_path = root / f"{archive_name}.sha256"
            checksum_path.write_text(f"{digest}  {archive_name}\n", encoding="utf-8")

            bin_dir = root / "bin"
            install_dir = root / "install"
            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            curl = fake_bin / "curl"
            curl.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "set -euo pipefail",
                        "out=''",
                        'args=("$@")',
                        "for ((i=0; i<${#args[@]}; i++)); do",
                        "  if [[ \"${args[$i]}\" == '-o' ]]; then",
                        '    out="${args[$((i + 1))]}"',
                        "  fi",
                        "done",
                        'url="${args[$((${#args[@]} - 1))]}"',
                        '[[ -n "$out" ]] || exit 2',
                        'case "$url" in',
                        '  *.sha256) cp "$FAKE_CHECKSUM" "$out" ;;',
                        '  *) cp "$FAKE_ARCHIVE" "$out" ;;',
                        "esac",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            curl.chmod(curl.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{fake_bin}{os.pathsep}{env.get('PATH', '')}",
                    "FAKE_ARCHIVE": str(archive_path),
                    "FAKE_CHECKSUM": str(checksum_path),
                    "AGENTHUB_INSTALL_REPO": "example/AgentHub",
                    "AGENTHUB_INSTALL_VERSION": f"cli-v{version}",
                    "AGENTHUB_INSTALL_DIR": str(install_dir),
                    "AGENTHUB_BIN_DIR": str(bin_dir),
                    "AGENTHUB_COMMAND_NAME": "agenthub-test",
                }
            )

            result = subprocess.run(
                ["bash", str(ROOT / "scripts" / "install_agenthub_cli.sh")],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((bin_dir / "agenthub-test").exists())
            self.assertNotIn("unbound variable", result.stdout + result.stderr)

    def test_package_output_onefile_replaces_stale_onedir_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dist_dir = root / "dist"
            artifact_dir = root / "artifacts"
            dist_dir.mkdir()
            artifact_dir.mkdir()
            executable = dist_dir / "agenthub-cli.exe"
            executable.write_text("exe", encoding="utf-8")
            packaged_root = artifact_dir / "agenthub-cli-9.9.9-windows-x86_64"
            stale_dir = packaged_root / "_internal"
            stale_dir.mkdir(parents=True)
            (stale_dir / "old.dll").write_text("stale", encoding="utf-8")

            with (
                patch.object(MODULE, "cli_version", return_value="9.9.9"),
                patch.object(
                    MODULE,
                    "detect_platform_tag",
                    return_value="windows-x86_64",
                ),
                patch.object(MODULE.platform, "system", return_value="Windows"),
            ):
                archive_path = MODULE.package_output(
                    bundle_name="agenthub-cli",
                    mode="onefile",
                    artifact_dir=artifact_dir,
                    dist_dir=dist_dir,
                )

            self.assertTrue((packaged_root / "agenthub-cli.exe").exists())
            self.assertFalse(stale_dir.exists())
            with zipfile.ZipFile(archive_path) as archive:
                self.assertEqual(
                    archive.namelist(),
                    ["agenthub-cli-9.9.9-windows-x86_64/agenthub-cli.exe"],
                )

    def test_bundle_codex_sidecar_runtime_writes_binary_and_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source-codex"
            source.write_text("#!/bin/sh\necho codex 1.2.3\n", encoding="utf-8")
            source.chmod(source.stat().st_mode | stat.S_IXUSR)
            packaged_root = root / "agenthub-cli-1.0-linux-x86_64"
            packaged_root.mkdir()

            with patch.object(MODULE, "probe_codex_version", return_value="codex 1.2.3"):
                target = MODULE.bundle_codex_sidecar_runtime(
                    packaged_root,
                    codex_sidecar_bin=source,
                    runtime_version="2026.05.07 codex/ref",
                    source_revision="abc123",
                    platform_key="linux-x86_64",
                )

            self.assertIsNotNone(target)
            assert target is not None
            self.assertEqual(
                target,
                packaged_root
                / "runtime"
                / "codex"
                / "linux-x86_64"
                / "2026.05.07-codex-ref"
                / "codex-app-server",
            )
            self.assertTrue(target.exists())
            runtime_manifest = json.loads(
                (packaged_root / "runtime" / "codex" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(runtime_manifest["defaultVersion"], "2026.05.07-codex-ref")
            self.assertEqual(
                runtime_manifest["platforms"]["linux-x86_64"]["binary"],
                "linux-x86_64/2026.05.07-codex-ref/codex-app-server",
            )
            bundle_manifest = json.loads(
                (target.parent / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(bundle_manifest["sourceRevision"], "abc123")
            self.assertEqual(bundle_manifest["binaryVersion"], "codex 1.2.3")
            self.assertEqual(bundle_manifest["args"], ["--listen", "stdio://"])

    def test_probe_codex_version_returns_empty_when_version_flag_is_unsupported(self) -> None:
        completed = SimpleNamespace(
            returncode=2,
            stdout="",
            stderr="error: unexpected argument '--version' found\n",
        )
        with patch.object(MODULE.subprocess, "run", return_value=completed):
            self.assertEqual(MODULE.probe_codex_version(Path("/tmp/codex-app-server")), "")

    def test_bundle_codex_sidecar_runtime_can_be_resolved_from_packaged_root(self) -> None:
        from cli.agent_cli.runtime_kernels.codex_sidecar import (
            CodexSidecarArtifactConfig,
            resolve_codex_sidecar_artifact,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source-codex"
            source.write_text("#!/bin/sh\necho codex 1.2.3\n", encoding="utf-8")
            source.chmod(source.stat().st_mode | stat.S_IXUSR)
            packaged_root = root / "agenthub-cli-1.0-linux-x86_64"
            packaged_root.mkdir()
            with patch.object(MODULE, "probe_codex_version", return_value="codex 1.2.3"):
                target = MODULE.bundle_codex_sidecar_runtime(
                    packaged_root,
                    codex_sidecar_bin=source,
                    runtime_version="v-test",
                    platform_key="linux-x86_64",
                )

            artifact = resolve_codex_sidecar_artifact(
                CodexSidecarArtifactConfig(
                    install_root=packaged_root,
                    allow_path_lookup=False,
                ),
                env={},
                platform_key="linux-x86_64",
                which=lambda _name: None,
                version_runner=lambda path: f"version:{path.name}",
            )

        self.assertEqual(artifact.path, target.resolve(strict=False))
        self.assertEqual(artifact.source, "bundled")
        self.assertEqual(artifact.version, "v-test")

    def test_bundle_codex_sidecar_runtime_root_copies_supporting_resources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime_root = root / "runtime" / "codex"
            bundle_root = runtime_root / "linux-x86_64" / "rust-v0.129.0"
            (bundle_root / "path").mkdir(parents=True)
            (bundle_root / "codex-resources").mkdir()
            for relative in ("codex-app-server", "path/rg", "codex-resources/bwrap"):
                path = bundle_root / relative
                path.write_text("#!/bin/sh\n", encoding="utf-8")
                path.chmod(path.stat().st_mode | stat.S_IXUSR)
            (bundle_root / "manifest.json").write_text(
                json.dumps(
                    {
                        "version": "rust-v0.129.0",
                        "binary": "codex-app-server",
                        "pathEntries": ["path"],
                        "resources": {
                            "path": "path/rg",
                            "bwrap": "codex-resources/bwrap",
                        },
                        "files": {
                            "appServer": "codex-app-server",
                            "rg": "path/rg",
                            "bwrap": "codex-resources/bwrap",
                        },
                    }
                ),
                encoding="utf-8",
            )
            (runtime_root / "manifest.json").write_text(
                json.dumps(
                    {
                        "defaultVersion": "rust-v0.129.0",
                        "platforms": {"linux-x86_64": {"defaultVersion": "rust-v0.129.0"}},
                    }
                ),
                encoding="utf-8",
            )
            packaged_root = root / "agenthub-cli-1.0-linux-x86_64"
            packaged_root.mkdir()

            target = MODULE.bundle_codex_sidecar_runtime_root(
                packaged_root,
                runtime_root=runtime_root,
                platform_key="linux-x86_64",
            )

            assert target is not None
            target_bundle = target.parent
            self.assertTrue((target_bundle / "codex-app-server").exists())
            self.assertTrue((target_bundle / "path" / "rg").exists())
            self.assertTrue((target_bundle / "codex-resources" / "bwrap").exists())
            root_manifest = json.loads(
                (packaged_root / "runtime" / "codex" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(root_manifest["defaultVersion"], "rust-v0.129.0")
