from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cli.agent_cli.gateway_core import JsonlGatewayStateStore, create_gateway_event
from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.providers.config.paths import project_provider_layout
from cli.agent_cli.runtime_paths import (
    PROJECT_ROOT_ENV,
    project_local_data_dir,
    runtime_project_root,
)
from cli.agent_cli.thread_store import ThreadStore
from cli.agent_cli.tools_core.project_loader import find_project_root


class RuntimePathsTest(unittest.TestCase):
    def test_runtime_project_root_prefers_env_override(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.dict(os.environ, {PROJECT_ROOT_ENV: temp_dir}, clear=False),
        ):
            self.assertEqual(runtime_project_root(), Path(temp_dir).resolve())

    def test_find_project_root_prefers_runtime_env_root(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.dict(os.environ, {PROJECT_ROOT_ENV: temp_dir}, clear=False),
        ):
            root = Path(temp_dir)
            (root / "plugins").mkdir()
            (root / "tools").mkdir()
            candidate = find_project_root(root / "nested" / "path")
            self.assertEqual(candidate, root.resolve())

    def test_project_local_data_dir_prefers_dot_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            preferred = root / ".config"
            preferred.mkdir()
            (root / ".agent_cli").mkdir()
            self.assertEqual(project_local_data_dir(root=root), preferred.resolve())

    def test_project_local_data_dir_falls_back_to_legacy_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy = root / ".agent_cli"
            legacy.mkdir()
            self.assertEqual(project_local_data_dir(root=root), legacy.resolve())

    def test_project_local_data_dir_defaults_to_dot_config_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.assertEqual(project_local_data_dir(root=root), (root / ".config").resolve())

    def test_default_runtime_stores_use_project_local_data_dir(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.dict(os.environ, {PROJECT_ROOT_ENV: temp_dir}, clear=False),
        ):
            root = Path(temp_dir)
            (root / "plugins").mkdir()

            store = ThreadStore.default()
            gateway = JsonlGatewayStateStore.default()
            manager = PluginManager(plugin_root=root / "plugins")

            self.assertEqual(store.base_dir, (root / ".config" / "threads").resolve())
            self.assertEqual(gateway.base_dir, (root / ".config" / "gateway").resolve())
            self.assertEqual(manager.state_path, (root / ".config" / "plugin_state.json").resolve())

    def test_frozen_project_local_data_dir_uses_agent_cli_home_not_install_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            install_dir = root / "agenthub-cli"
            state_home = root / "state-home"
            install_dir.mkdir()
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "executable", str(install_dir / "agenthub-cli")),
                patch.dict(
                    os.environ,
                    {
                        PROJECT_ROOT_ENV: str(install_dir),
                        "AGENT_CLI_HOME": str(state_home),
                    },
                    clear=False,
                ),
            ):
                self.assertEqual(runtime_project_root(), install_dir.resolve())
                self.assertEqual(project_local_data_dir(), state_home.resolve())

    def test_frozen_gateway_store_uses_agent_cli_home_not_install_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            install_dir = root / "agenthub-cli"
            state_home = root / "state-home"
            install_dir.mkdir()
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "executable", str(install_dir / "agenthub-cli")),
                patch.dict(
                    os.environ,
                    {
                        PROJECT_ROOT_ENV: str(install_dir),
                        "AGENT_CLI_HOME": str(state_home),
                    },
                    clear=False,
                ),
            ):
                gateway = JsonlGatewayStateStore.default()

            self.assertEqual(gateway.base_dir, (state_home / "gateway").resolve())
            self.assertFalse((install_dir / ".config").exists())

    def test_frozen_provider_layout_uses_agent_cli_home_not_install_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            install_dir = root / "agenthub-cli"
            state_home = root / "state-home"
            install_dir.mkdir()
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "executable", str(install_dir / "agenthub-cli")),
                patch.dict(
                    os.environ,
                    {
                        PROJECT_ROOT_ENV: str(install_dir),
                        "AGENT_CLI_HOME": str(state_home),
                    },
                    clear=False,
                ),
            ):
                layout = project_provider_layout()

            self.assertEqual(layout.home_dir, state_home.resolve())
            self.assertEqual(layout.config_toml, state_home.resolve() / "config.toml")
            self.assertFalse((install_dir / ".config").exists())

    def test_frozen_provider_layout_without_explicit_home_uses_default_agent_cli_home(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            install_dir = root / "agenthub-cli"
            home_dir = root / "home"
            install_dir.mkdir()
            home_dir.mkdir()
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "executable", str(install_dir / "agenthub-cli.exe")),
                patch.dict(os.environ, {"HOME": str(home_dir)}, clear=True),
            ):
                layout = project_provider_layout()

            self.assertEqual(layout.home_dir, (home_dir / ".agent_cli").resolve())
            self.assertEqual(
                layout.config_toml, (home_dir / ".agent_cli" / "config.toml").resolve()
            )
            self.assertFalse((install_dir / ".config").exists())

    def test_default_gateway_store_migrates_legacy_jsonl_into_dot_config(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.dict(os.environ, {PROJECT_ROOT_ENV: temp_dir}, clear=False),
        ):
            root = Path(temp_dir)
            legacy_root = root / ".agent_cli" / "gateway"
            legacy_store = JsonlGatewayStateStore(legacy_root)
            event = create_gateway_event(
                event_type="demo.event",
                source_kind="manual",
                source_id="runtime-path-test",
                payload={"ok": True},
            )
            legacy_store.save_event(event)

            migrated = JsonlGatewayStateStore.default()

            self.assertEqual(migrated.base_dir, (root / ".config" / "gateway").resolve())
            self.assertTrue((root / ".config" / "gateway" / "events.jsonl").exists())
            self.assertEqual(migrated.list_events(limit=5)[0].event_id, event.event_id)
