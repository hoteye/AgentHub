from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "release_artifact_smoke.py"
SPEC = importlib.util.spec_from_file_location("release_artifact_smoke", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReleaseArtifactSmokeTest(unittest.TestCase):
    def test_executable_path_prefers_existing_binary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_root = Path(temp_dir)
            binary = bundle_root / "agenthub-cli"
            binary.write_text("", encoding="utf-8")

            self.assertEqual(MODULE.executable_path(bundle_root), binary)

    def test_run_smoke_command_rejects_missing_asset_output(self) -> None:
        completed = SimpleNamespace(
            returncode=0, stdout="provider_source=[Errno 2] No such file or directory", stderr=""
        )
        with patch.object(MODULE.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "missing runtime asset"):
                MODULE.run_smoke_command(Path("/tmp/agenthub-cli"), "--provider-status")

    def test_run_smoke_command_sets_utf8_and_timeout(self) -> None:
        captured: dict[str, object] = {}

        def _fake_run(command, **kwargs):  # noqa: ANN001, ANN003
            captured["command"] = command
            captured.update(kwargs)
            return SimpleNamespace(returncode=0, stdout="ok", stderr="")

        with patch.object(MODULE.subprocess, "run", side_effect=_fake_run):
            MODULE.run_smoke_command(Path("agenthub-cli"), "--help")

        self.assertEqual(captured["command"], ["agenthub-cli", "--help"])
        self.assertEqual(captured["timeout"], MODULE.SMOKE_COMMAND_TIMEOUT_SECONDS)
        self.assertEqual(captured["env"]["PYTHONUTF8"], "1")

    def test_require_output_checks_expected_tokens(self) -> None:
        result = SimpleNamespace(
            stdout="provider status\nprovider_name=openai\nprovider_ready=true\n"
        )
        MODULE.require_output(result, "provider status", "provider_name=", "provider_ready=")

    def test_require_output_accepts_wrapped_help_text(self) -> None:
        result = SimpleNamespace(
            stdout="Reference-like CLI for AgentHub local automation and provider-backed\nworkflows.\n"
        )
        MODULE.require_output(
            result,
            "Reference-like CLI for AgentHub local automation and provider-backed workflows.",
        )

    def test_release_smoke_checks_version_command(self) -> None:
        calls: list[tuple[Path, tuple[str, ...]]] = []

        def _fake_run_smoke_command(executable: Path, *args: str):  # noqa: ANN001
            calls.append((executable, args))
            if args == ("--version",):
                return SimpleNamespace(stdout="agenthub-cli 1.2.3\n", stderr="", returncode=0)
            return SimpleNamespace(
                stdout=(
                    "Reference-like CLI for AgentHub local automation and "
                    "provider-backed workflows.\nprovider status\nprovider_name=openai\n"
                    "provider_ready=true\nprovider_model=gpt-5.5\nmodel_key=gpt_55\n"
                    "provider_base_url=https://codexcs.ysaikeji.cn/v1\n"
                ),
                stderr="",
                returncode=0,
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_root = Path(temp_dir) / "bundle"
            bundle_root.mkdir()
            executable = bundle_root / "agenthub-cli"
            executable.write_text("", encoding="utf-8")
            with patch.object(MODULE, "artifact_root", return_value=bundle_root):
                with patch.object(MODULE.build_release, "cli_version", return_value="1.2.3"):
                    with patch.object(
                        MODULE, "run_smoke_command", side_effect=_fake_run_smoke_command
                    ):
                        self.assertEqual(MODULE.main([]), 0)

        self.assertIn((executable, ("--version",)), calls)
        self.assertIn((executable, ("--provider-status",)), calls)

    def test_artifact_root_uses_version_and_platform_tag(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            target = (
                repo_root / "cli" / "artifacts" / "releases" / "agenthub-cli-1.2.3-windows-x86_64"
            )
            target.mkdir(parents=True)
            with patch.object(MODULE, "ROOT", repo_root):
                with patch.object(MODULE.build_release, "cli_version", return_value="1.2.3"):
                    with patch.object(
                        MODULE.build_release, "detect_platform_tag", return_value="windows-x86_64"
                    ):
                        self.assertEqual(MODULE.artifact_root(), target)

    def test_windows_unc_bundle_root_is_staged_locally(self) -> None:
        with patch.object(MODULE.os, "name", "nt"):
            self.assertTrue(
                MODULE._needs_windows_local_stage(Path(r"\\wsl.localhost\Ubuntu\bundle"))
            )
            self.assertFalse(MODULE._needs_windows_local_stage(Path(r"C:\agenthub\bundle")))

        with patch.object(MODULE.os, "name", "posix"):
            self.assertFalse(
                MODULE._needs_windows_local_stage(Path(r"\\wsl.localhost\Ubuntu\bundle"))
            )

    def test_smoke_bundle_root_copies_and_cleans_local_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "agenthub-cli-0.1.3-windows-x86_64"
            source.mkdir()
            (source / "agenthub-cli.exe").write_text("stub", encoding="utf-8")

            with patch.object(MODULE, "_needs_windows_local_stage", return_value=True):
                with MODULE.smoke_bundle_root(source) as staged:
                    staged_parent = staged.parent
                    self.assertNotEqual(staged, source)
                    self.assertEqual(staged.name, source.name)
                    self.assertEqual(
                        (staged / "agenthub-cli.exe").read_text(encoding="utf-8"),
                        "stub",
                    )

            self.assertFalse(staged_parent.exists())

    def test_clean_provider_status_requires_bundled_default_catalog_tokens(self) -> None:
        result = SimpleNamespace(
            stdout=(
                "provider status\n"
                "provider_name=openai\n"
                "provider_model=gpt-5.5\n"
                "model_key=gpt_55\n"
                "provider_base_url=https://codexcs.ysaikeji.cn/v1\n"
                "provider_ready=false\n"
            )
        )

        MODULE.require_output(
            result,
            "provider_name=openai",
            "provider_model=gpt-5.5",
            "model_key=gpt_55",
            "provider_base_url=https://codexcs.ysaikeji.cn/v1",
        )
