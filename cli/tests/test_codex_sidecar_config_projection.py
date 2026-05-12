from __future__ import annotations

import asyncio
import json
import os
import tempfile
import tomllib
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

from cli.agent_cli.providers.config.catalog import (
    ModelCatalogEntry,
    ProviderCatalog,
    ProviderCatalogEntry,
    ProviderPathResolution,
)
from cli.agent_cli.runtime_kernels.base import KernelSession
from cli.agent_cli.runtime_kernels.codex_sidecar import (
    CodexSidecarKernel,
    CodexSidecarRuntimeAgent,
    CodexSidecarSupervisor,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.config_projection import (
    CODEX_API_KEY_ENV,
    CODEX_HOME_ENV,
    CodexSidecarProjectedConfig,
    prepare_codex_sidecar_projected_config,
    project_codex_config_from_catalog,
    render_codex_config_toml,
)

FAKE_CODEX_BIN = Path(__file__).parent / "fixtures" / "fake_codex_sidecar.py"


@dataclass
class FakeProviderSnapshot:
    catalog: ProviderCatalog
    toml_data: dict[str, Any]
    resolution: ProviderPathResolution
    auth_data: dict[str, Any] | None = None
    selected_config: Any | None = None


def _provider_snapshot(
    tmp_path: Path, *, auth_data: dict[str, Any] | None = None
) -> FakeProviderSnapshot:
    return FakeProviderSnapshot(
        catalog=ProviderCatalog(
            providers={
                "openai": ProviderCatalogEntry(
                    provider_name="openai",
                    display_name="OpenAI",
                    base_url="https://relay.example/v1",
                    api_key_env="OPENAI_API_KEY",
                    wire_api="responses",
                    default_model="gpt_55",
                    raw_provider={
                        "name": "OpenAI",
                        "base_url": "https://relay.example/v1",
                        "api_key_env": "OPENAI_API_KEY",
                        "wire_api": "responses",
                        "requires_openai_auth": True,
                    },
                )
            },
            models={
                "gpt_55": ModelCatalogEntry(
                    key="gpt_55",
                    provider_name="openai",
                    model_id="gpt-5.5",
                    planner_kind="openai_responses",
                    wire_api="responses",
                    interaction_profile="codex_openai",
                    supports_reasoning=True,
                )
            },
        ),
        toml_data={"model_provider": "openai", "model": "gpt_55"},
        auth_data={"OPENAI_API_KEY": "sk-from-auth-store"} if auth_data is None else auth_data,
        resolution=ProviderPathResolution(
            config_path=tmp_path / "config.toml",
            auth_path=tmp_path / "auth.json",
            config_exists=True,
            auth_exists=False,
            used_project_local=False,
        ),
    )


class CodexSidecarConfigProjectionTest(unittest.TestCase):
    def test_project_codex_config_reads_key_from_agenthub_auth_store_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = _provider_snapshot(Path(temp_dir))
            projection = project_codex_config_from_catalog(
                catalog=snapshot.catalog,
                toml_data=snapshot.toml_data,
                auth_data=snapshot.auth_data,
                env={"OPENAI_API_KEY": "sk-from-shell"},
                source_config_path=str(snapshot.resolution.config_path),
                source_auth_path=str(snapshot.resolution.auth_path),
            )

        assert projection is not None
        self.assertEqual(projection["model"], "gpt-5.5")
        self.assertEqual(projection["model_provider"], "agenthub-openai")
        self.assertEqual(projection["auth_json"], {"OPENAI_API_KEY": "sk-from-auth-store"})
        self.assertEqual(projection["source_config_path"], str(snapshot.resolution.config_path))
        self.assertEqual(projection["source_auth_path"], str(snapshot.resolution.auth_path))
        self.assertNotIn("env_key", projection["provider"])

    def test_project_codex_config_uses_openai_key_when_auth_required_without_env_key(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = _provider_snapshot(Path(temp_dir))
            provider = snapshot.catalog.providers["openai"]
            provider.api_key_env = ""
            provider.raw_provider.pop("api_key_env", None)
            provider.raw_provider["requires_openai_auth"] = True
            projection = project_codex_config_from_catalog(
                catalog=snapshot.catalog,
                toml_data=snapshot.toml_data,
                auth_data={"OPENAI_API_KEY": "sk-from-auth-store"},
                env={"OPENAI_API_KEY": "sk-from-shell"},
                source_config_path=str(snapshot.resolution.config_path),
                source_auth_path=str(snapshot.resolution.auth_path),
            )

        assert projection is not None
        self.assertEqual(projection["model_provider"], "agenthub-openai")
        self.assertEqual(projection["auth_json"], {"OPENAI_API_KEY": "sk-from-auth-store"})
        self.assertEqual(projection["provider"]["requires_openai_auth"], True)

    def test_render_codex_config_uses_codex_wire_shape_without_key(self) -> None:
        rendered = render_codex_config_toml(
            {
                "model": "gpt-5.5",
                "model_provider": "agenthub-openai",
                "provider": {
                    "name": "OpenAI",
                    "base_url": "https://relay.example/v1",
                    "wire_api": "responses",
                    "requires_openai_auth": True,
                },
            }
        )
        payload = tomllib.loads(rendered)

        self.assertEqual(payload["model"], "gpt-5.5")
        provider = payload["model_providers"]["agenthub-openai"]
        self.assertEqual(provider["base_url"], "https://relay.example/v1")
        self.assertEqual(provider["wire_api"], "responses")
        self.assertEqual(provider["requires_openai_auth"], True)
        self.assertNotIn("env_key", provider)
        self.assertNotIn("api_key", provider)

    def test_project_codex_config_does_not_forward_env_header_or_token_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = _provider_snapshot(Path(temp_dir))
            provider = snapshot.catalog.providers["openai"]
            provider.raw_provider.update(
                {
                    "experimental_bearer_token": "sk-inline-token",
                    "env_http_headers": {"Authorization": "OPENAI_API_KEY"},
                    "http_headers": {"X-AgentHub": "1"},
                }
            )
            projection = project_codex_config_from_catalog(
                catalog=snapshot.catalog,
                toml_data=snapshot.toml_data,
                auth_data=snapshot.auth_data,
                source_config_path=str(snapshot.resolution.config_path),
            )

        assert projection is not None
        provider_block = projection["provider"]
        self.assertNotIn("experimental_bearer_token", provider_block)
        self.assertNotIn("env_http_headers", provider_block)
        self.assertEqual(provider_block["http_headers"], {"X-AgentHub": "1"})

    def test_project_codex_config_does_not_reuse_other_provider_generic_api_key(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = _provider_snapshot(
                Path(temp_dir),
                auth_data={
                    "providers": {
                        "anthropic": {
                            "auth": {
                                "api_key": "sk-claude-should-not-be-used",
                            },
                        },
                    },
                },
            )
            projection = project_codex_config_from_catalog(
                catalog=snapshot.catalog,
                toml_data=snapshot.toml_data,
                auth_data=snapshot.auth_data,
            )

        assert projection is not None
        self.assertEqual(projection["auth_json"], {})

    def test_prepare_projected_config_writes_under_agenthub_home_and_ignores_shell_key(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot = _provider_snapshot(root)
            projected = prepare_codex_sidecar_projected_config(
                env={"OPENAI_API_KEY": "sk-from-shell", CODEX_API_KEY_ENV: "sk-codex-shell"},
                provider_home=root,
                snapshot_loader=lambda **_kwargs: snapshot,
            )

            assert projected is not None
            self.assertTrue(projected.generated)
            self.assertEqual(projected.codex_home, root / "codex_sidecar" / "codex_home")
            self.assertEqual(projected.env[CODEX_HOME_ENV], str(projected.codex_home))
            self.assertNotIn("OPENAI_API_KEY", projected.env)
            self.assertEqual(projected.auth_key_names, ("OPENAI_API_KEY",))
            self.assertEqual(projected.source_config_path, str(snapshot.resolution.config_path))
            self.assertEqual(projected.source_auth_path, str(snapshot.resolution.auth_path))
            self.assertEqual(projected.scrubbed_env_keys, (CODEX_API_KEY_ENV, "OPENAI_API_KEY"))
            assert projected.auth_path is not None
            auth_payload = json.loads(projected.auth_path.read_text(encoding="utf-8"))
            self.assertEqual(auth_payload["OPENAI_API_KEY"], "sk-from-auth-store")

    def test_runtime_agent_status_uses_agenthub_source_config_and_auth_paths(self) -> None:
        projected = CodexSidecarProjectedConfig(
            codex_home=Path("/tmp/codex-home"),
            config_path=Path("/tmp/codex-home/config.toml"),
            auth_path=Path("/tmp/codex-home/auth.json"),
            provider_name="openai",
            codex_provider_id="agenthub-openai",
            source_config_path="/tmp/agenthub/config.toml",
            source_auth_path="/tmp/agenthub/auth.json",
            generated=True,
        )
        agent = CodexSidecarRuntimeAgent(
            session=KernelSession(
                engine="codex_sidecar",
                session_id="session-1",
                thread_id="thread-1",
                model="gpt-5.5",
                model_provider="agenthub-openai",
            ),
            artifact_metadata={"projected_config": projected.status_fields()},
        )

        status = agent.provider_status()

        self.assertEqual(status["provider_name"], "openai")
        self.assertEqual(status["provider_public_name"], "openai")
        self.assertEqual(status["provider_label"], "openai | gpt-5.5 | codex-sidecar")
        self.assertNotIn("codex_sidecar_model_provider", status)
        self.assertEqual(status["provider_config_path"], "/tmp/agenthub/config.toml")
        self.assertEqual(status["provider_auth_path"], "/tmp/agenthub/auth.json")
        self.assertEqual(status["codex_sidecar_config_path"], "/tmp/codex-home/config.toml")
        self.assertEqual(status["codex_sidecar_auth_path"], "/tmp/codex-home/auth.json")
        self.assertEqual(status["codex_sidecar_source_config_path"], "/tmp/agenthub/config.toml")
        self.assertEqual(status["codex_sidecar_source_auth_path"], "/tmp/agenthub/auth.json")

    def test_prepare_projected_config_does_not_fall_back_to_shell_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot = _provider_snapshot(root, auth_data={})
            projected = prepare_codex_sidecar_projected_config(
                env={"OPENAI_API_KEY": "sk-from-shell", CODEX_API_KEY_ENV: "sk-codex-shell"},
                provider_home=root,
                snapshot_loader=lambda **_kwargs: snapshot,
            )

            assert projected is not None
            self.assertEqual(projected.auth_key_names, ())
            self.assertIsNone(projected.auth_path)
            self.assertFalse((projected.codex_home / "auth.json").exists())
            self.assertEqual(projected.scrubbed_env_keys, (CODEX_API_KEY_ENV, "OPENAI_API_KEY"))

    def test_prepare_projected_config_ignores_external_codex_home_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            external_codex_home = root / "manual-codex-home"
            snapshot = _provider_snapshot(root)
            projected = prepare_codex_sidecar_projected_config(
                env={CODEX_HOME_ENV: str(external_codex_home)},
                provider_home=root / "provider-home",
                snapshot_loader=lambda **_kwargs: snapshot,
            )

        assert projected is not None
        self.assertTrue(projected.generated)
        self.assertNotEqual(projected.codex_home, external_codex_home)
        self.assertEqual(
            projected.codex_home,
            (root / "provider-home" / "codex_sidecar" / "codex_home").resolve(strict=False),
        )

    def test_prepare_projected_config_isolates_when_provider_snapshot_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            projected = prepare_codex_sidecar_projected_config(
                env={"OPENAI_API_KEY": "sk-from-shell", CODEX_HOME_ENV: str(root / "external")},
                provider_home=root,
                snapshot_loader=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
            )

            assert projected is not None
            self.assertTrue(projected.generated)
            self.assertEqual(projected.codex_home, root / "codex_sidecar" / "codex_home")
            self.assertEqual(projected.env[CODEX_HOME_ENV], str(projected.codex_home))
            self.assertEqual(projected.auth_key_names, ())
            self.assertEqual(projected.scrubbed_env_keys, (CODEX_API_KEY_ENV, "OPENAI_API_KEY"))
            self.assertTrue(projected.config_path.exists())
            self.assertFalse((projected.codex_home / "auth.json").exists())

    def test_supervisor_removes_parent_auth_env_before_applying_projected_env(self) -> None:
        supervisor = CodexSidecarSupervisor(
            codex_bin=FAKE_CODEX_BIN,
            extra_env={CODEX_HOME_ENV: "/tmp/projected-codex-home"},
            remove_env_keys=(CODEX_HOME_ENV, "OPENAI_API_KEY", CODEX_API_KEY_ENV),
        )

        with patch.dict(
            os.environ,
            {
                CODEX_HOME_ENV: "/tmp/shell-codex-home",
                "OPENAI_API_KEY": "sk-shell",
                CODEX_API_KEY_ENV: "sk-codex-shell",
                "PATH": "/usr/bin",
            },
            clear=True,
        ):
            env = supervisor._build_process_env()

        assert env is not None
        self.assertEqual(env[CODEX_HOME_ENV], "/tmp/projected-codex-home")
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn(CODEX_API_KEY_ENV, env)
        self.assertEqual(env["PATH"], "/usr/bin")

    def test_kernel_removes_parent_codex_home_but_keeps_projected_codex_home(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home = Path(temp_dir) / "projected-codex-home"
            projected = CodexSidecarProjectedConfig(
                codex_home=codex_home,
                config_path=codex_home / "config.toml",
                env={CODEX_HOME_ENV: str(codex_home)},
                generated=True,
            )
            from cli.agent_cli.runtime_kernels.codex_sidecar import kernel as kernel_module

            original_prepare = kernel_module.prepare_codex_sidecar_projected_config
            kernel_module.prepare_codex_sidecar_projected_config = lambda **_kwargs: projected
            try:
                kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
            finally:
                kernel_module.prepare_codex_sidecar_projected_config = original_prepare

        try:
            self.assertEqual(kernel.client.supervisor.extra_env[CODEX_HOME_ENV], str(codex_home))
            self.assertIn(CODEX_HOME_ENV, kernel.client.supervisor.remove_env_keys)
            with patch.dict(
                os.environ,
                {CODEX_HOME_ENV: "/tmp/shell-codex-home", "OPENAI_API_KEY": "sk-shell"},
                clear=True,
            ):
                env = kernel.client.supervisor._build_process_env()
            assert env is not None
            self.assertEqual(env[CODEX_HOME_ENV], str(codex_home))
            self.assertNotIn("OPENAI_API_KEY", env)
        finally:
            asyncio.run(kernel.aclose())


if __name__ == "__main__":
    unittest.main()
