from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.runtime_kernels.codex_sidecar import (
    CodexSidecarArtifactConfig,
    CodexSidecarKernel,
    resolve_codex_sidecar_artifact,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.artifact import (
    CODEX_SIDECAR_ALLOW_DEV_ENV,
    CODEX_SIDECAR_BIN_ENV,
    CODEX_SIDECAR_TEST_BIN_ENV,
    bundled_codex_binary_path,
    cached_codex_binary_path,
    codex_binary_name,
    current_platform_key,
    probe_codex_version,
    resolve_codex_sidecar_test_binary,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.errors import CodexSidecarProcessError
from cli.agent_cli.runtime_kernels.errors import RuntimeKernelSessionError


class CodexSidecarArtifactTest(unittest.TestCase):
    def test_resolver_uses_bundled_by_default_and_ignores_external_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_bin = _executable(root / "env-codex")
            config_bin = _executable(root / "config-codex")
            cache = _executable(
                cached_codex_binary_path(
                    root / "cache",
                    platform_key="linux-x86_64",
                    runtime_version="v1",
                )
            )
            path_bin = _executable(root / "path-codex-app-server")
            bundled = _executable(
                bundled_codex_binary_path(
                    root / "install",
                    platform_key="linux-x86_64",
                    runtime_version="v1",
                )
            )

            artifact = resolve_codex_sidecar_artifact(
                CodexSidecarArtifactConfig(
                    codex_bin=config_bin,
                    install_root=root / "install",
                    cache_root=root / "cache",
                    runtime_version="v1",
                    allow_path_lookup=True,
                ),
                env={CODEX_SIDECAR_BIN_ENV: str(env_bin)},
                platform_key="linux-x86_64",
                which=lambda name: str(path_bin) if name == "codex-app-server" else None,
                version_runner=lambda path: f"version:{path.name}",
            )
            self.assertTrue(bundled.exists())
            self.assertTrue(cache.exists())

        self.assertEqual(artifact.path, bundled.resolve(strict=False))
        self.assertEqual(artifact.source, "bundled")
        self.assertEqual(artifact.version, "version:codex-app-server")
        self.assertEqual(
            artifact.sha256,
            "01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b",
        )

    def test_resolver_uses_bundled_before_cache_and_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundled = _executable(
                bundled_codex_binary_path(
                    root / "install",
                    platform_key="linux-x86_64",
                    runtime_version="v2",
                )
            )
            cache = _executable(
                cached_codex_binary_path(
                    root / "cache",
                    platform_key="linux-x86_64",
                    runtime_version="v2",
                )
            )
            path_bin = _executable(root / "path-codex")

            artifact = resolve_codex_sidecar_artifact(
                CodexSidecarArtifactConfig(
                    install_root=root / "install",
                    cache_root=root / "cache",
                    runtime_version="v2",
                    allow_cache_lookup=True,
                    allow_path_lookup=True,
                ),
                env={CODEX_SIDECAR_ALLOW_DEV_ENV: "1"},
                platform_key="linux-x86_64",
                which=lambda name: str(path_bin) if name == "codex-app-server" else None,
                version_runner=lambda path: path.name,
            )
            self.assertTrue(cache.exists())

        self.assertEqual(artifact.path, bundled.resolve(strict=False))
        self.assertEqual(artifact.source, "bundled")

    def test_resolver_uses_cache_before_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = _executable(
                cached_codex_binary_path(
                    root / "cache",
                    platform_key="linux-x86_64",
                    runtime_version="v3",
                )
            )
            path_bin = _executable(root / "path-codex")

            artifact = resolve_codex_sidecar_artifact(
                CodexSidecarArtifactConfig(
                    cache_root=root / "cache",
                    runtime_version="v3",
                    allow_cache_lookup=True,
                    allow_path_lookup=True,
                ),
                env={CODEX_SIDECAR_ALLOW_DEV_ENV: "1"},
                platform_key="linux-x86_64",
                which=lambda name: str(path_bin) if name == "codex-app-server" else None,
                version_runner=lambda path: path.name,
            )

        self.assertEqual(artifact.path, cache.resolve(strict=False))
        self.assertEqual(artifact.source, "cache")

    def test_resolver_uses_env_and_config_only_when_dev_opt_in_is_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_bin = _executable(root / "env-codex")
            config_bin = _executable(root / "config-codex")
            config = CodexSidecarArtifactConfig(
                codex_bin=config_bin,
                install_root=root / "missing-install",
                cache_root=root / "missing-cache",
            )

            with self.assertRaises(CodexSidecarProcessError):
                resolve_codex_sidecar_artifact(
                    config,
                    env={CODEX_SIDECAR_BIN_ENV: str(env_bin)},
                    platform_key="linux-x86_64",
                    which=lambda _name: None,
                )

            artifact = resolve_codex_sidecar_artifact(
                config,
                env={
                    CODEX_SIDECAR_ALLOW_DEV_ENV: "1",
                    CODEX_SIDECAR_BIN_ENV: str(env_bin),
                },
                platform_key="linux-x86_64",
                which=lambda _name: None,
                version_runner=lambda path: f"version:{path.name}",
            )

        self.assertEqual(artifact.path, env_bin.resolve(strict=False))
        self.assertEqual(artifact.source, "env")
        self.assertEqual(artifact.version, "version:env-codex")

    def test_resolver_uses_config_before_path_when_dev_opt_in_is_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_bin = _executable(root / "config-codex")
            path_bin = _executable(root / "path-codex")

            artifact = resolve_codex_sidecar_artifact(
                CodexSidecarArtifactConfig(
                    codex_bin=config_bin,
                    install_root=root / "missing-install",
                    cache_root=root / "missing-cache",
                    allow_path_lookup=True,
                ),
                env={CODEX_SIDECAR_ALLOW_DEV_ENV: "1"},
                platform_key="linux-x86_64",
                which=lambda name: str(path_bin) if name == "codex-app-server" else None,
                version_runner=lambda path: path.name,
            )

        self.assertEqual(artifact.path, config_bin.resolve(strict=False))
        self.assertEqual(artifact.source, "config")

    def test_resolver_can_use_cache_without_dev_opt_in_when_explicitly_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = _executable(
                cached_codex_binary_path(
                    root / "cache",
                    platform_key="linux-x86_64",
                    runtime_version="v-cache",
                )
            )

            artifact = resolve_codex_sidecar_artifact(
                CodexSidecarArtifactConfig(
                    install_root=root / "missing-install",
                    cache_root=root / "cache",
                    runtime_version="v-cache",
                    allow_cache_lookup=True,
                ),
                env={},
                platform_key="linux-x86_64",
                which=lambda _name: None,
                version_runner=lambda path: path.name,
            )

        self.assertEqual(artifact.path, cache.resolve(strict=False))
        self.assertEqual(artifact.source, "cache")

    def test_path_lookup_requires_dev_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path_bin = _executable(root / "path-codex")
            config = CodexSidecarArtifactConfig(
                install_root=root / "missing-install",
                cache_root=root / "missing-cache",
                allow_path_lookup=True,
            )

            with self.assertRaises(CodexSidecarProcessError):
                resolve_codex_sidecar_artifact(
                    config,
                    env={},
                    platform_key="linux-x86_64",
                    which=lambda name: str(path_bin) if name == "codex-app-server" else None,
                )

            artifact = resolve_codex_sidecar_artifact(
                config,
                env={CODEX_SIDECAR_ALLOW_DEV_ENV: "1"},
                platform_key="linux-x86_64",
                which=lambda name: str(path_bin) if name == "codex-app-server" else None,
                version_runner=lambda path: path.name,
            )

        self.assertEqual(artifact.path, path_bin.resolve(strict=False))
        self.assertEqual(artifact.source, "path")

    def test_dev_overrides_are_disabled_in_frozen_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_bin = _executable(root / "env-codex")
            config_bin = _executable(root / "config-codex")
            dev_bin = _executable(root / "dev-codex")
            path_bin = _executable(root / "path-codex")
            config = CodexSidecarArtifactConfig(
                codex_bin=config_bin,
                install_root=root / "missing-install",
                cache_root=root / "missing-cache",
                allow_dev_fallback=True,
                allow_path_lookup=True,
                dev_codex_bin=dev_bin,
            )

            with (
                patch(
                    "cli.agent_cli.runtime_kernels.codex_sidecar.artifact.sys",
                    SimpleNamespace(frozen=True),
                ),
                self.assertRaises(CodexSidecarProcessError),
            ):
                resolve_codex_sidecar_artifact(
                    config,
                    env={
                        CODEX_SIDECAR_ALLOW_DEV_ENV: "1",
                        CODEX_SIDECAR_BIN_ENV: str(env_bin),
                    },
                    platform_key="linux-x86_64",
                    which=lambda name: str(path_bin) if name == "codex-app-server" else None,
                )

    def test_test_binary_env_is_internal_and_disabled_in_frozen_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            test_bin = _executable(root / "test-codex")

            resolved = resolve_codex_sidecar_test_binary(
                env={CODEX_SIDECAR_TEST_BIN_ENV: str(test_bin)}
            )

            with patch(
                "cli.agent_cli.runtime_kernels.codex_sidecar.artifact.sys",
                SimpleNamespace(frozen=True),
            ):
                frozen_resolved = resolve_codex_sidecar_test_binary(
                    env={CODEX_SIDECAR_TEST_BIN_ENV: str(test_bin)}
                )

        self.assertEqual(resolved, test_bin)
        self.assertIsNone(frozen_resolved)

    def test_dev_fallback_requires_explicit_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dev_bin = _executable(root / "dev-codex-app-server")
            config = CodexSidecarArtifactConfig(
                install_root=root / "missing-install",
                cache_root=root / "missing-cache",
                allow_path_lookup=False,
                dev_codex_bin=dev_bin,
            )

            with self.assertRaises(CodexSidecarProcessError):
                resolve_codex_sidecar_artifact(
                    config,
                    env={},
                    platform_key="linux-x86_64",
                    which=lambda _name: None,
                )

            artifact = resolve_codex_sidecar_artifact(
                config,
                env={CODEX_SIDECAR_ALLOW_DEV_ENV: "1"},
                platform_key="linux-x86_64",
                which=lambda _name: None,
                version_runner=lambda path: path.name,
            )

        self.assertEqual(artifact.source, "dev")
        self.assertEqual(artifact.path.name, "dev-codex-app-server")

    def test_platform_binary_name(self) -> None:
        self.assertEqual(codex_binary_name("windows-x86_64"), "codex-app-server.exe")
        self.assertEqual(codex_binary_name("linux-x86_64"), "codex-app-server")
        self.assertIn("-", current_platform_key())

    def test_probe_codex_version_returns_empty_when_version_flag_is_unsupported(self) -> None:
        completed = SimpleNamespace(
            returncode=2,
            stdout="",
            stderr="error: unexpected argument '--version' found\n",
        )
        with patch(
            "cli.agent_cli.runtime_kernels.codex_sidecar.artifact.subprocess.run",
            return_value=completed,
        ):
            self.assertEqual(probe_codex_version(Path("/tmp/codex-app-server")), "")

    def test_kernel_can_resolve_artifact_from_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_bin = _executable(Path(tmp) / "codex")
            kernel = CodexSidecarKernel(
                artifact_config=CodexSidecarArtifactConfig(
                    codex_bin=codex_bin,
                    allow_dev_fallback=True,
                ),
                request_timeout=3,
            )

        self.assertIsNotNone(kernel.artifact)
        self.assertEqual(kernel.artifact.source, "config")

    def test_kernel_rejects_direct_external_binary_in_frozen_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_bin = _executable(Path(tmp) / "codex")

            with (
                patch(
                    "cli.agent_cli.runtime_kernels.codex_sidecar.artifact.sys",
                    SimpleNamespace(frozen=True),
                ),
                self.assertRaises(RuntimeKernelSessionError),
            ):
                CodexSidecarKernel(codex_bin=codex_bin)

    def test_resolver_uses_runtime_root_manifest_for_current_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_root = root / "install" / "runtime" / "codex"
            codex_bin = _executable(
                runtime_root / "linux-x86_64" / "v-manifest" / "codex-app-server"
            )
            (runtime_root / "manifest.json").write_text(
                json.dumps(
                    {
                        "defaultVersion": "wrong-default",
                        "platforms": {
                            "linux-x86_64": {
                                "defaultVersion": "v-manifest",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            artifact = resolve_codex_sidecar_artifact(
                CodexSidecarArtifactConfig(
                    install_root=root / "install",
                    runtime_version="current",
                    allow_path_lookup=False,
                ),
                env={},
                platform_key="linux-x86_64",
                which=lambda _name: None,
                version_runner=lambda path: path.name,
            )

        self.assertEqual(artifact.path, codex_bin.resolve(strict=False))
        self.assertEqual(artifact.source, "bundled")

    def test_resolver_prefers_bundle_manifest_version_when_binary_has_no_version_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_bin = _executable(
                bundled_codex_binary_path(
                    root / "install",
                    platform_key="linux-x86_64",
                    runtime_version="rust-v0.129.0",
                )
            )
            (codex_bin.parent / "manifest.json").write_text(
                json.dumps(
                    {
                        "codexVersion": "0.129.0",
                        "sourceTag": "rust-v0.129.0",
                    }
                ),
                encoding="utf-8",
            )

            artifact = resolve_codex_sidecar_artifact(
                CodexSidecarArtifactConfig(
                    install_root=root / "install",
                    runtime_version="rust-v0.129.0",
                    allow_path_lookup=False,
                ),
                env={},
                platform_key="linux-x86_64",
                which=lambda _name: None,
                version_runner=lambda _path: "",
            )

        self.assertEqual(artifact.path, codex_bin.resolve(strict=False))
        self.assertEqual(artifact.version, "0.129.0")
        self.assertEqual(artifact.manifest["sourceTag"], "rust-v0.129.0")


def _executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


if __name__ == "__main__":
    unittest.main()
