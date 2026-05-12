from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.agent import RuleBasedAgent
from cli.agent_cli.host_platform import detect_host_platform
from cli.agent_cli.models import ToolEvent
from cli.agent_cli import provider_catalog_runtime as provider_catalog_runtime_lib
from cli.agent_cli.provider import (
    build_planner,
    load_provider_catalog,
    load_provider_config,
    resolve_provider_paths,
)
from cli.agent_cli.providers import (
    ChatCompletionsPlanner,
    DeepSeekPlanner,
    OpenAIPlanner,
    ProviderCatalog,
    ProviderConfig,
    ProviderPathResolution,
)
from cli.agent_cli.providers.planner_postprocessing import (
    concise_answer_prompt_text,
    generic_tool_event_context_blocks,
    generic_tool_event_summary_lines,
    sanitize_final_answer_text,
)
from cli.agent_cli.providers.config_catalog import select_provider_config
from cli.agent_cli.providers.config.paths import AGENTHUB_PROVIDER_HOME_ENV

class ProviderPathsTest(unittest.TestCase):
    class _FakeEvent:
        def __init__(self, event_type: str, delta: str) -> None:
            self.type = event_type
            self.delta = delta

    class _FakeResponses:
        def __init__(self, scripted_chunks) -> None:
            if scripted_chunks and isinstance(scripted_chunks[0], list):
                self._scripted_chunks = [list(item) for item in scripted_chunks]
            else:
                self._scripted_chunks = [list(scripted_chunks)]
            self.calls = 0
            self.requests: list[dict] = []

        def create(self, **kwargs):
            self.requests.append(copy.deepcopy(kwargs))
            index = min(self.calls, len(self._scripted_chunks) - 1)
            self.calls += 1
            chunks = self._scripted_chunks[index]
            return [ProviderPathsTest._FakeEvent("response.output_text.delta", chunk) for chunk in chunks]

    class _FakeResponsesNativeResponse:
        def __init__(self, response_id: str, output: list[SimpleNamespace]) -> None:
            self.id = response_id
            self.output = output

        @property
        def output_text(self) -> str:
            parts: list[str] = []
            for item in self.output:
                if getattr(item, "type", "") != "message":
                    continue
                for content in list(getattr(item, "content", []) or []):
                    if getattr(content, "type", "") == "output_text":
                        parts.append(str(getattr(content, "text", "") or ""))
            return "".join(parts)

    class _FakeResponsesNative:
        def __init__(self, scripted_responses: list[object]) -> None:
            self._scripted_responses = list(scripted_responses)
            self.calls = 0
            self.requests: list[dict] = []

        def create(self, **kwargs):
            self.requests.append(copy.deepcopy(kwargs))
            index = min(self.calls, len(self._scripted_responses) - 1)
            self.calls += 1
            item = self._scripted_responses[index]
            if isinstance(item, Exception):
                raise item
            return item

    class _FakeOpenAIClient:
        def __init__(self, chunks) -> None:
            self.responses = ProviderPathsTest._FakeResponses(chunks)

    class _FakeOpenAINativeClient:
        def __init__(self, scripted_responses: list["ProviderPathsTest._FakeResponsesNativeResponse"]) -> None:
            self.responses = ProviderPathsTest._FakeResponsesNative(scripted_responses)

    class _FakeChatCompletions:
        def __init__(self, scripted_messages: list[SimpleNamespace]) -> None:
            self._scripted_messages = scripted_messages
            self.calls = 0
            self.requests: list[dict] = []

        def create(self, **kwargs):
            self.requests.append(copy.deepcopy(kwargs))
            message = self._scripted_messages[self.calls]
            self.calls += 1
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class _FakeDeepSeekClient:
        def __init__(self, scripted_messages: list[SimpleNamespace]) -> None:
            self.chat = SimpleNamespace(completions=ProviderPathsTest._FakeChatCompletions(scripted_messages))

    @staticmethod
    def _response_message(text: str) -> SimpleNamespace:
        return SimpleNamespace(
            type="message",
            content=[SimpleNamespace(type="output_text", text=text)],
        )

    @staticmethod
    def _response_function_call(*, call_id: str, name: str, arguments: str) -> SimpleNamespace:
        return SimpleNamespace(
            type="function_call",
            call_id=call_id,
            name=name,
            arguments=arguments,
        )

    def test_select_provider_config_works_with_pure_inputs(self) -> None:
        config = select_provider_config(
            env_mapping={},
            auth_data={"DEEPSEEK_API_KEY": "sk-pure"},
            toml_data={
                "model_provider": "deepseek",
                "model": "deepseek-chat",
                "model_providers": {
                    "deepseek": {
                        "base_url": "https://api.deepseek.com",
                    }
                },
            },
            resolution=ProviderPathResolution(
                config_path=Path("C:/tmp/.agent_cli/config.toml"),
                auth_path=Path("C:/tmp/.agent_cli/auth.json"),
                config_exists=True,
                auth_exists=True,
                used_project_local=True,
            ),
        )

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.provider_name, "deepseek")
        self.assertEqual(config.model, "deepseek-chat")
        self.assertEqual(config.api_key, "sk-pure")
        self.assertEqual(config.source, "project_local")

    def test_load_provider_management_snapshot_returns_loaded_inputs_and_selected_config(self) -> None:
        resolution = ProviderPathResolution(
            config_path=Path("/tmp/config.toml"),
            auth_path=Path("/tmp/auth.json"),
            config_exists=True,
            auth_exists=True,
            used_project_local=True,
        )
        catalog = ProviderCatalog()
        selected = ProviderConfig(
            provider_name="openai",
            model_key="gpt-5.4",
            model="gpt-5.4",
            api_key="sk-test",
            source="project_local",
        )
        snapshot = provider_catalog_runtime_lib.load_provider_management_snapshot(
            cwd=Path("/tmp/workspace"),
            env_overrides={"AGENT_CLI_PROVIDER": "openai"},
            load_provider_inputs_fn=lambda **kwargs: (
                resolution,
                {"model_provider": "openai", "model": "gpt-5.4"},
                {"OPENAI_API_KEY": "sk-test"},
            ),
            build_provider_catalog_fn=lambda toml_data: catalog,
            select_provider_config_fn=lambda **kwargs: selected,
            optional_bool_fn=lambda value, default=False: default,
            infer_planner_kind_fn=lambda provider_name, model, base_url, provider_block: "openai_responses",
            should_use_claude_provider_fn=lambda **kwargs: False,
            project_claude_home_dir_fn=lambda: None,
            load_claude_provider_config_fn=lambda **kwargs: None,
        )

        self.assertIs(snapshot.resolution, resolution)
        self.assertEqual(snapshot.toml_data["model_provider"], "openai")
        self.assertEqual(snapshot.auth_data["OPENAI_API_KEY"], "sk-test")
        self.assertIs(snapshot.catalog, catalog)
        self.assertIs(snapshot.selected_config, selected)

    def test_select_provider_config_honors_anthropic_base_url_env_alias(self) -> None:
        config = select_provider_config(
            env_mapping={
                "ANTHROPIC_BASE_URL": "https://relay.example/anthropic",
            },
            auth_data={"ANTHROPIC_API_KEY": "sk-anthropic"},
            toml_data={
                "model_provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "model_providers": {
                    "anthropic": {},
                },
            },
            resolution=ProviderPathResolution(
                config_path=Path("/tmp/config.toml"),
                auth_path=Path("/tmp/auth.json"),
                config_exists=True,
                auth_exists=True,
                used_project_local=False,
            ),
        )

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.provider_name, "anthropic")
        self.assertEqual(config.model, "claude-sonnet-4-6")
        self.assertEqual(config.base_url, "https://relay.example/anthropic")
        self.assertEqual(config.api_key, "sk-anthropic")

    def test_select_provider_config_applies_notice_model_migrations(self) -> None:
        config = select_provider_config(
            env_mapping={},
            auth_data={"OPENAI_API_KEY": "sk-test"},
            toml_data={
                "model_provider": "openai",
                "model": "gpt-5-reference",
                "model_providers": {
                    "openai": {
                        "base_url": "https://relay.example/v1",
                    }
                },
                "notice": {
                    "model_migrations": {
                        "gpt-5-reference": "gpt-5.3-reference",
                        "gpt-5.3-reference": "gpt-5.4",
                    }
                },
            },
            resolution=ProviderPathResolution(
                config_path=Path("/tmp/config.toml"),
                auth_path=Path("/tmp/auth.json"),
                config_exists=True,
                auth_exists=True,
                used_project_local=False,
            ),
        )

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.provider_name, "openai")
        self.assertEqual(config.model, "gpt-5.4")
        self.assertEqual(config.api_key, "sk-test")

    def test_select_provider_config_prefers_explicit_provider_default_model_over_root_model(self) -> None:
        config = select_provider_config(
            env_mapping={"AGENT_CLI_PROVIDER": "glm-claude-mode"},
            auth_data={"GLM_CLAUDE_MODE_API_KEY": "sk-glm-claude-mode"},
            toml_data={
                "model_provider": "openai",
                "model": "gpt-5.4",
                "model_reasoning_effort": "high",
                "model_providers": {
                    "openai": {
                        "base_url": "https://relay.example/v1",
                        "wire_api": "responses",
                        "default_model": "gpt_54",
                    },
                    "glm-claude-mode": {
                        "base_url": "https://open.bigmodel.cn/api/anthropic",
                        "planner_kind": "anthropic_messages",
                        "api_key_env": "GLM_CLAUDE_MODE_API_KEY",
                        "wire_api": "anthropic_messages",
                        "default_model": "glm_claude_mode_glm_5",
                    },
                },
                "models": {
                    "gpt_54": {
                        "provider": "openai",
                        "model_id": "gpt-5.4",
                        "planner_kind": "openai_responses",
                        "wire_api": "responses",
                    },
                    "glm_claude_mode_glm_5": {
                        "provider": "glm-claude-mode",
                        "model_id": "glm-5",
                        "planner_kind": "anthropic_messages",
                        "wire_api": "anthropic_messages",
                    },
                },
            },
            resolution=ProviderPathResolution(
                config_path=Path("/tmp/config.toml"),
                auth_path=Path("/tmp/auth.json"),
                config_exists=True,
                auth_exists=True,
                used_project_local=False,
            ),
        )

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.provider_name, "glm-claude-mode")
        self.assertEqual(config.model, "glm-5")
        self.assertEqual(config.model_key, "glm_claude_mode_glm_5")
        self.assertEqual(config.planner_kind, "anthropic_messages")
        self.assertEqual(config.wire_api, "anthropic_messages")
        self.assertEqual(config.base_url, "https://open.bigmodel.cn/api/anthropic")
        self.assertEqual(config.api_key, "sk-glm-claude-mode")

    def test_load_provider_config_prefers_project_local_agent_cli_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local_config_home = root / "local" / ".agent_cli"
            home_config_home = root / "home" / ".agent_cli"
            local_config_home.mkdir(parents=True, exist_ok=True)
            home_config_home.mkdir(parents=True, exist_ok=True)

            (local_config_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-5.4"\n'
                "[model_providers.openai]\n"
                'base_url = "https://local.example/v1"\n',
                encoding="utf-8",
            )
            (local_config_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-local"}', encoding="utf-8")
            (home_config_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-home"\n'
                "[model_providers.openai]\n"
                'base_url = "https://home.example/v1"\n',
                encoding="utf-8",
            )
            (home_config_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-home"}', encoding="utf-8")

            def _find_local(filename: str) -> Path:
                return local_config_home / filename

            with patch("cli.agent_cli.provider._find_project_provider_file", side_effect=_find_local):
                with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", home_config_home / "config.toml"):
                    with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", home_config_home / "auth.json"):
                        with patch.dict(os.environ, {}, clear=True):
                            config = load_provider_config()

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.source, "project_local")
        self.assertTrue(bool(config.model))
        self.assertTrue(config.base_url is None or isinstance(config.base_url, str))
        self.assertTrue(bool(config.config_path))
        self.assertTrue(bool(config.auth_path))

    def test_load_provider_config_strict_isolation_ignores_project_local_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local_config_home = root / "local" / ".config"
            home_config_home = root / "home" / ".agent_cli"
            local_config_home.mkdir(parents=True, exist_ok=True)
            home_config_home.mkdir(parents=True, exist_ok=True)

            (local_config_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-project"\n'
                "[model_providers.openai]\n"
                'base_url = "https://project.example/v1"\n',
                encoding="utf-8",
            )
            (local_config_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-project"}', encoding="utf-8")
            (home_config_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-home"\n'
                "[model_providers.openai]\n"
                'base_url = "https://home.example/v1"\n'
                "[features.provider_discovery]\n"
                "strict_isolation = true\n",
                encoding="utf-8",
            )
            (home_config_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-home"}', encoding="utf-8")

            with patch("cli.agent_cli.provider._find_project_provider_file", side_effect=lambda filename, **_kwargs: local_config_home / filename):
                with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", home_config_home / "config.toml"):
                    with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", home_config_home / "auth.json"):
                        with patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", root / "missing" / "config.toml"):
                            with patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", root / "missing" / "auth.json"):
                                with patch.dict(os.environ, {}, clear=True):
                                    resolved = resolve_provider_paths()
                                    config = load_provider_config()

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(resolved.config_path, home_config_home / "config.toml")
        self.assertEqual(resolved.auth_path, home_config_home / "auth.json")
        self.assertFalse(resolved.used_project_local)
        self.assertEqual(config.source, "agent_cli_home")
        self.assertEqual(config.model, "gpt-home")
        self.assertEqual(config.base_url, "https://home.example/v1")
        self.assertEqual(config.config_path, str(home_config_home / "config.toml"))
        self.assertEqual(config.auth_path, str(home_config_home / "auth.json"))

    def test_explicit_provider_home_avoids_cwd_project_overlay_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace_config_home = workspace / ".config"
            explicit_provider_home = root / "explicit-home"
            workspace_config_home.mkdir(parents=True, exist_ok=True)
            explicit_provider_home.mkdir(parents=True, exist_ok=True)

            (workspace_config_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-project"\n'
                "[model_providers.openai]\n"
                'base_url = "https://project.example/v1"\n',
                encoding="utf-8",
            )
            (workspace_config_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-project"}', encoding="utf-8")
            (explicit_provider_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-home"\n'
                "[model_providers.openai]\n"
                'base_url = "https://home.example/v1"\n',
                encoding="utf-8",
            )
            (explicit_provider_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-home"}', encoding="utf-8")

            missing = root / "missing"
            with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", missing / "config.toml"):
                with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", missing / "auth.json"):
                    with patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", missing / "config.toml"):
                        with patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", missing / "auth.json"):
                            with patch("cli.agent_cli.provider._ensure_project_provider_bootstrap", return_value=None):
                                with patch.dict(
                                    os.environ,
                                    {AGENTHUB_PROVIDER_HOME_ENV: str(explicit_provider_home)},
                                    clear=True,
                                ):
                                    default_isolated_resolved = resolve_provider_paths(cwd=workspace)
                                    default_isolated = load_provider_config(cwd=workspace)
                                with patch.dict(
                                    os.environ,
                                    {
                                        AGENTHUB_PROVIDER_HOME_ENV: str(explicit_provider_home),
                                        "AGENTHUB_PROVIDER_STRICT_ISOLATION": "true",
                                    },
                                    clear=True,
                                ):
                                    isolated_resolved = resolve_provider_paths(cwd=workspace)
                                    isolated = load_provider_config(cwd=workspace)

        assert default_isolated is not None
        assert isolated is not None
        self.assertEqual(default_isolated_resolved.config_path, explicit_provider_home / "config.toml")
        self.assertEqual(default_isolated_resolved.auth_path, explicit_provider_home / "auth.json")
        self.assertFalse(default_isolated_resolved.used_project_local)
        self.assertEqual(default_isolated.model, "gpt-home")
        self.assertEqual(default_isolated.base_url, "https://home.example/v1")
        self.assertEqual(default_isolated.config_path, str(explicit_provider_home / "config.toml"))
        self.assertEqual(isolated_resolved.config_path, explicit_provider_home / "config.toml")
        self.assertEqual(isolated_resolved.auth_path, explicit_provider_home / "auth.json")
        self.assertFalse(isolated_resolved.used_project_local)
        self.assertEqual(isolated.model, "gpt-home")
        self.assertEqual(isolated.base_url, "https://home.example/v1")
        self.assertEqual(isolated.config_path, str(explicit_provider_home / "config.toml"))

    def test_explicit_provider_home_wins_over_agent_cli_home(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            explicit_provider_home = root / "provider-home"
            explicit_agent_home = root / "state-home"
            workspace.mkdir(parents=True, exist_ok=True)
            explicit_provider_home.mkdir(parents=True, exist_ok=True)
            explicit_agent_home.mkdir(parents=True, exist_ok=True)

            (explicit_provider_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-provider-home"\n'
                "[model_providers.openai]\n"
                'base_url = "https://provider-home.example/v1"\n',
                encoding="utf-8",
            )
            (explicit_provider_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-provider-home"}', encoding="utf-8")
            (explicit_agent_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-agent-home"\n'
                "[model_providers.openai]\n"
                'base_url = "https://agent-home.example/v1"\n',
                encoding="utf-8",
            )
            (explicit_agent_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-agent-home"}', encoding="utf-8")

            missing = root / "missing"
            with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", explicit_agent_home / "config.toml"):
                with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", explicit_agent_home / "auth.json"):
                    with patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", missing / "config.toml"):
                        with patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", missing / "auth.json"):
                            with patch("cli.agent_cli.provider._ensure_project_provider_bootstrap", return_value=None):
                                with patch.dict(
                                    os.environ,
                                    {
                                        AGENTHUB_PROVIDER_HOME_ENV: str(explicit_provider_home),
                                        "AGENT_CLI_HOME": str(explicit_agent_home),
                                    },
                                    clear=True,
                                ):
                                    resolved = resolve_provider_paths(cwd=workspace)
                                    config = load_provider_config(cwd=workspace)

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(resolved.config_path, explicit_provider_home / "config.toml")
        self.assertEqual(resolved.auth_path, explicit_provider_home / "auth.json")
        self.assertEqual(config.model, "gpt-provider-home")
        self.assertEqual(config.base_url, "https://provider-home.example/v1")

    def test_explicit_provider_home_feature_config_enables_strict_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace_config_home = workspace / ".config"
            explicit_provider_home = root / "explicit-home"
            workspace_config_home.mkdir(parents=True, exist_ok=True)
            explicit_provider_home.mkdir(parents=True, exist_ok=True)

            (workspace_config_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-project"\n'
                "[model_providers.openai]\n"
                'base_url = "https://project.example/v1"\n',
                encoding="utf-8",
            )
            (workspace_config_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-project"}', encoding="utf-8")
            (explicit_provider_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-home"\n'
                "[model_providers.openai]\n"
                'base_url = "https://home.example/v1"\n'
                "[features.provider_discovery]\n"
                "strict_isolation = true\n",
                encoding="utf-8",
            )
            (explicit_provider_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-home"}', encoding="utf-8")

            missing = root / "missing"
            with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", missing / "config.toml"):
                with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", missing / "auth.json"):
                    with patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", missing / "config.toml"):
                        with patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", missing / "auth.json"):
                            with patch("cli.agent_cli.provider._ensure_project_provider_bootstrap", return_value=None):
                                with patch.dict(
                                    os.environ,
                                    {AGENTHUB_PROVIDER_HOME_ENV: str(explicit_provider_home)},
                                    clear=True,
                                ):
                                    resolved = resolve_provider_paths(cwd=workspace)
                                    config = load_provider_config(cwd=workspace)

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(resolved.config_path, explicit_provider_home / "config.toml")
        self.assertEqual(resolved.auth_path, explicit_provider_home / "auth.json")
        self.assertFalse(resolved.used_project_local)
        self.assertEqual(config.source, "agent_cli_home")
        self.assertEqual(config.model, "gpt-home")
        self.assertEqual(config.base_url, "https://home.example/v1")
        self.assertEqual(config.config_path, str(explicit_provider_home / "config.toml"))
        self.assertEqual(config.auth_path, str(explicit_provider_home / "auth.json"))

    def test_explicit_provider_home_strict_isolation_keeps_empty_home_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            explicit_provider_home = root / "explicit-home"
            explicit_provider_home.mkdir(parents=True, exist_ok=True)

            missing = root / "missing"
            with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", missing / "config.toml"):
                with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", missing / "auth.json"):
                    with patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", root / ".agent_cli_legacy" / "config.toml"):
                        with patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", root / ".agent_cli_legacy" / "auth.json"):
                            with patch("cli.agent_cli.provider._ensure_project_provider_bootstrap", return_value=None):
                                with patch.dict(
                                    os.environ,
                                    {
                                        AGENTHUB_PROVIDER_HOME_ENV: str(explicit_provider_home),
                                        "AGENTHUB_PROVIDER_STRICT_ISOLATION": "true",
                                    },
                                    clear=True,
                                ):
                                    resolved = resolve_provider_paths(cwd=workspace)

        self.assertEqual(resolved.config_path, explicit_provider_home / "config.toml")
        self.assertEqual(resolved.auth_path, explicit_provider_home / "auth.json")
        self.assertFalse(resolved.config_exists)
        self.assertFalse(resolved.auth_exists)
        self.assertFalse(resolved.used_project_local)

    def test_explicit_agent_cli_home_keeps_empty_home_paths_without_falling_back_to_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            explicit_agent_home = root / "custom-home"
            legacy_home = root / ".agent_cli_legacy"
            workspace.mkdir(parents=True, exist_ok=True)
            explicit_agent_home.mkdir(parents=True, exist_ok=True)
            legacy_home.mkdir(parents=True, exist_ok=True)

            (legacy_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-legacy"\n',
                encoding="utf-8",
            )
            (legacy_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-legacy"}', encoding="utf-8")

            with patch("cli.agent_cli.provider.AGENT_CLI_HOME", explicit_agent_home):
                with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", explicit_agent_home / "config.toml"):
                    with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", explicit_agent_home / "auth.json"):
                        with patch("cli.agent_cli.provider.LEGACY_COMPAT_HOME", legacy_home):
                            with patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", legacy_home / "config.toml"):
                                with patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", legacy_home / "auth.json"):
                                    with patch.dict(
                                        os.environ,
                                        {"AGENT_CLI_HOME": str(explicit_agent_home)},
                                        clear=True,
                                    ):
                                        resolved = resolve_provider_paths(cwd=workspace)

        self.assertEqual(resolved.config_path, explicit_agent_home / "config.toml")
        self.assertEqual(resolved.auth_path, explicit_agent_home / "auth.json")
        self.assertFalse(resolved.config_exists)
        self.assertFalse(resolved.auth_exists)
        self.assertFalse(resolved.used_project_local)

    def test_explicit_agent_cli_home_load_provider_config_does_not_reuse_legacy_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            explicit_agent_home = root / "custom-home"
            legacy_home = root / ".agent_cli_legacy"
            workspace.mkdir(parents=True, exist_ok=True)
            explicit_agent_home.mkdir(parents=True, exist_ok=True)
            legacy_home.mkdir(parents=True, exist_ok=True)

            (legacy_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-5.4"\n'
                "[model_providers.openai]\n"
                'api_key_env = "OPENAI_API_KEY"\n',
                encoding="utf-8",
            )
            (legacy_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-legacy"}', encoding="utf-8")

            with patch("cli.agent_cli.provider.AGENT_CLI_HOME", explicit_agent_home):
                with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", explicit_agent_home / "config.toml"):
                    with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", explicit_agent_home / "auth.json"):
                        with patch("cli.agent_cli.provider.LEGACY_COMPAT_HOME", legacy_home):
                            with patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", legacy_home / "config.toml"):
                                with patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", legacy_home / "auth.json"):
                                    with patch.dict(
                                        os.environ,
                                        {"AGENT_CLI_HOME": str(explicit_agent_home)},
                                        clear=True,
                                    ):
                                        config = load_provider_config(cwd=workspace)

        self.assertIsNone(config)

    def test_load_provider_config_prefers_project_local_dot_config_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local_config_home = root / ".config"
            home_config_home = root / "home" / ".agent_cli"
            local_config_home.mkdir(parents=True, exist_ok=True)
            home_config_home.mkdir(parents=True, exist_ok=True)

            (local_config_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-project"\n'
                "[model_providers.openai]\n"
                'base_url = "https://project.example/v1"\n',
                encoding="utf-8",
            )
            (local_config_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-project"}', encoding="utf-8")
            (home_config_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-home"\n'
                "[model_providers.openai]\n"
                'base_url = "https://home.example/v1"\n',
                encoding="utf-8",
            )
            (home_config_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-home"}', encoding="utf-8")

            with patch("cli.agent_cli.provider._iter_project_roots", return_value=[root]):
                with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", home_config_home / "config.toml"):
                    with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", home_config_home / "auth.json"):
                        with patch.dict(os.environ, {}, clear=True):
                            config = load_provider_config()

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.source, "project_local")
        self.assertTrue(bool(config.model))
        self.assertTrue(config.base_url is None or isinstance(config.base_url, str))
        self.assertTrue(bool(config.config_path))
        self.assertTrue(bool(config.auth_path))

    def test_load_provider_config_project_local_reasoning_overrides_stale_home_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local_config_home = root / ".config"
            home_config_home = root / "home" / ".agent_cli"
            local_config_home.mkdir(parents=True, exist_ok=True)
            home_config_home.mkdir(parents=True, exist_ok=True)

            (local_config_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-project"\n'
                'model_reasoning_effort = "xhigh"\n'
                "[model_providers.openai]\n"
                'base_url = "https://project.example/v1"\n'
                'wire_api = "responses"\n'
                'default_model = "gpt_project"\n'
                "[models.gpt_project]\n"
                'provider = "openai"\n'
                'model_id = "gpt-5.4"\n'
                'planner_kind = "openai_responses"\n'
                'wire_api = "responses"\n'
                'interaction_profile = "codex_openai"\n',
                encoding="utf-8",
            )
            (local_config_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-project"}', encoding="utf-8")
            (home_config_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt_project"\n'
                'model_reasoning_effort = "high"\n'
                "[model_providers.openai]\n"
                'base_url = "https://home.example/v1"\n',
                encoding="utf-8",
            )
            (home_config_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-home"}', encoding="utf-8")

            with patch("cli.agent_cli.provider._iter_project_roots", return_value=[root]):
                with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", home_config_home / "config.toml"):
                    with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", home_config_home / "auth.json"):
                        with patch.dict(os.environ, {}, clear=True):
                            config = load_provider_config()

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.source, "project_local")
        self.assertEqual(config.model, "gpt-5.4")
        self.assertEqual(config.reasoning_effort, "xhigh")

    def test_load_provider_config_prefers_nearest_project_local_paths_for_explicit_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_provider_home = root / "cli" / ".config"
            parent_config_home = root / ".config"
            nested_workspace = root / "apps" / "nested" / "feature"
            nested_config_home = root / "apps" / ".config"
            (root / ".git").write_text("gitdir: here\n", encoding="utf-8")
            parent_config_home.mkdir(parents=True, exist_ok=True)
            nested_workspace.mkdir(parents=True, exist_ok=True)
            nested_config_home.mkdir(parents=True, exist_ok=True)

            (parent_config_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-parent"\n'
                "[model_providers.openai]\n"
                'base_url = "https://parent.example/v1"\n',
                encoding="utf-8",
            )
            (parent_config_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-parent"}', encoding="utf-8")
            (nested_config_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-nested"\n'
                "[model_providers.openai]\n"
                'base_url = "https://nested.example/v1"\n',
                encoding="utf-8",
            )
            (nested_config_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-nested"}', encoding="utf-8")

            with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", root / "home" / ".agent_cli" / "config.toml"):
                with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", root / "home" / ".agent_cli" / "auth.json"):
                    with patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", root / "missing" / "config.toml"):
                        with patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", root / "missing" / "auth.json"):
                            with patch("cli.agent_cli.provider.APP_DIR", root / "cli" / "agent_cli"):
                                with patch("cli.agent_cli.provider._ensure_project_provider_bootstrap", return_value=None):
                                    with patch.dict(os.environ, {}, clear=True):
                                        config = load_provider_config(cwd=nested_workspace)

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.source, "project_local")
        self.assertTrue(bool(config.model))
        self.assertTrue(config.base_url is None or isinstance(config.base_url, str))

    def test_load_provider_config_prefers_repo_local_cli_config_before_home_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "AgentHub"
            cli_root = repo_root / "cli"
            project_provider_home = cli_root / ".config"
            repo_root.mkdir(parents=True, exist_ok=True)
            cli_root.mkdir(parents=True, exist_ok=True)
            (cli_root / ".config").mkdir(parents=True, exist_ok=True)
            home_reference = root / "home" / ".agent_cli_legacy"
            home_reference.mkdir(parents=True, exist_ok=True)

            (cli_root / ".config" / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-repo-cli"\n'
                "[model_providers.openai]\n"
                'base_url = "https://repo-cli.example/v1"\n',
                encoding="utf-8",
            )
            (cli_root / ".config" / "auth.json").write_text('{"OPENAI_API_KEY":"sk-repo-cli"}', encoding="utf-8")
            (home_reference / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-home-legacy"\n'
                "[model_providers.openai]\n"
                'base_url = "https://home-legacy.example/v1"\n',
                encoding="utf-8",
            )
            (home_reference / "auth.json").write_text('{"OPENAI_API_KEY":"sk-home-legacy"}', encoding="utf-8")

            with patch("cli.agent_cli.provider.APP_DIR", cli_root / "agent_cli"):
                with patch("cli.agent_cli.provider.LEGACY_COMPAT_HOME", home_reference):
                    with patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", home_reference / "config.toml"):
                        with patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", home_reference / "auth.json"):
                            with patch("cli.agent_cli.provider.AGENT_CLI_HOME", root / "home" / ".agent_cli"):
                                with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", root / "home" / ".agent_cli" / "config.toml"):
                                    with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", root / "home" / ".agent_cli" / "auth.json"):
                                        with patch("cli.agent_cli.provider.runtime_project_root", return_value=repo_root, create=True):
                                            with patch("cli.agent_cli.provider._read_user_model_selection_toml", return_value={}):
                                                with patch.dict(os.environ, {}, clear=True):
                                                    config = load_provider_config(cwd=repo_root)

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.source, "project_local")
        self.assertTrue(bool(config.model))
        self.assertTrue(config.base_url is None or isinstance(config.base_url, str))
        self.assertTrue(bool(config.api_key))

    def test_load_provider_config_merges_repo_root_config_with_repo_cli_provider_home_without_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "AgentHub"
            cli_root = repo_root / "cli"
            cli_agent_dir = cli_root / "agent_cli"
            root_config_dir = repo_root / ".config"
            cli_config_dir = cli_root / ".config"
            user_home = root / "home" / ".agent_cli"
            repo_root.mkdir(parents=True, exist_ok=True)
            cli_agent_dir.mkdir(parents=True, exist_ok=True)
            root_config_dir.mkdir(parents=True, exist_ok=True)
            cli_config_dir.mkdir(parents=True, exist_ok=True)
            user_home.mkdir(parents=True, exist_ok=True)
            (repo_root / ".git").write_text("gitdir: here\n", encoding="utf-8")

            (cli_config_dir / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt_54"\n'
                "[model_providers.openai]\n"
                'base_url = "https://cli-provider.example/v1"\n'
                'default_model = "gpt_54"\n'
                "[models.gpt_54]\n"
                'provider = "openai"\n'
                'model_id = "gpt-5.4"\n'
                'planner_kind = "openai_responses"\n'
                'wire_api = "responses"\n'
                "[models.gpt_55]\n"
                'provider = "openai"\n'
                'model_id = "gpt-5.5"\n'
                'planner_kind = "openai_responses"\n'
                'wire_api = "responses"\n',
                encoding="utf-8",
            )
            (cli_config_dir / "auth.json").write_text('{"OPENAI_API_KEY":"sk-repo-cli"}', encoding="utf-8")
            (root_config_dir / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt_55"\n'
                'model_reasoning_effort = "xhigh"\n'
                "[model_providers.openai]\n"
                'base_url = "https://root-project.example/v1"\n',
                encoding="utf-8",
            )

            with patch("cli.agent_cli.provider.APP_DIR", cli_agent_dir):
                with patch("cli.agent_cli.provider.runtime_project_root", return_value=repo_root, create=True):
                    with patch("cli.agent_cli.provider.AGENT_CLI_HOME", user_home):
                        with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", user_home / "config.toml"):
                            with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", user_home / "auth.json"):
                                with patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", root / "missing" / "config.toml"):
                                    with patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", root / "missing" / "auth.json"):
                                        with patch("cli.agent_cli.provider._read_user_model_selection_toml", return_value={}):
                                            with patch.dict(os.environ, {}, clear=True):
                                                config = load_provider_config(cwd=repo_root)
                                                resolved = resolve_provider_paths(cwd=repo_root)

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.source, "project_local")
        self.assertEqual(config.model_key, "gpt_55")
        self.assertEqual(config.model, "gpt-5.5")
        self.assertEqual(config.reasoning_effort, "xhigh")
        self.assertEqual(config.base_url, "https://root-project.example/v1")
        self.assertEqual(config.api_key, "sk-repo-cli")
        self.assertEqual(config.config_path, str(root_config_dir / "config.toml"))
        self.assertEqual(config.auth_path, str(cli_config_dir / "auth.json"))
        self.assertEqual(resolved.config_path, root_config_dir / "config.toml")
        self.assertEqual(resolved.auth_path, root_config_dir / "auth.json")
        self.assertTrue(resolved.used_project_local)

    def test_load_provider_catalog_keeps_repo_cli_config_in_project_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "AgentHub"
            cli_root = repo_root / "cli"
            cli_agent_dir = cli_root / "agent_cli"
            cli_config_dir = cli_root / ".config"
            home_dir = root / "home" / ".agent_cli"
            repo_root.mkdir(parents=True, exist_ok=True)
            cli_agent_dir.mkdir(parents=True, exist_ok=True)
            cli_config_dir.mkdir(parents=True, exist_ok=True)
            home_dir.mkdir(parents=True, exist_ok=True)

            (cli_config_dir / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt_54"\n'
                "[model_providers.openai]\n"
                'base_url = "https://openai.example/v1"\n'
                "[model_providers.deepseek]\n"
                'base_url = "https://deepseek.example/v1"\n'
                "[models.gpt_54]\n"
                'provider = "openai"\n'
                'model_id = "gpt-5.4"\n'
                "[models.deepseek_chat]\n"
                'provider = "deepseek"\n'
                'model_id = "deepseek-chat"\n',
                encoding="utf-8",
            )
            (home_dir / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt_54"\n',
                encoding="utf-8",
            )

            with patch("cli.agent_cli.provider.APP_DIR", cli_agent_dir):
                with patch("cli.agent_cli.provider.runtime_project_root", return_value=repo_root, create=True):
                    with patch("cli.agent_cli.provider.AGENT_CLI_HOME", home_dir):
                        with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", home_dir / "config.toml"):
                            with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", home_dir / "auth.json"):
                                with patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", root / "missing" / "config.toml"):
                                    with patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", root / "missing" / "auth.json"):
                                        with patch("cli.agent_cli.provider._read_user_model_selection_toml", return_value={}):
                                            with patch.dict(os.environ, {}, clear=True):
                                                discovered = load_provider_catalog(cwd=cli_root)

        self.assertIn("openai", discovered.providers)
        self.assertIn("deepseek", discovered.providers)

    def test_load_provider_config_ignores_untrusted_project_layers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace" / "app"
            local_config_home = workspace.parent / ".config"
            home_config_home = root / "home" / ".agent_cli"
            workspace.mkdir(parents=True, exist_ok=True)
            local_config_home.mkdir(parents=True, exist_ok=True)
            home_config_home.mkdir(parents=True, exist_ok=True)

            (local_config_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-untrusted"\n'
                "[model_providers.openai]\n"
                'base_url = "https://untrusted.example/v1"\n',
                encoding="utf-8",
            )
            (local_config_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-untrusted"}', encoding="utf-8")
            (home_config_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-home"\n'
                "[model_providers.openai]\n"
                'base_url = "https://home.example/v1"\n'
                f'\n[projects."{str(workspace.parent.resolve()).replace(chr(92), "/")}"]\n'
                'trust_level = "untrusted"\n',
                encoding="utf-8",
            )
            (home_config_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-home"}', encoding="utf-8")

            with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", home_config_home / "config.toml"):
                with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", home_config_home / "auth.json"):
                    with patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", root / "missing" / "config.toml"):
                        with patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", root / "missing" / "auth.json"):
                            with patch.dict(os.environ, {}, clear=True):
                                config = load_provider_config(cwd=workspace)

        self.assertIsNotNone(config)
        assert config is not None
        self.assertTrue(bool(config.model))
        self.assertTrue(config.base_url is None or isinstance(config.base_url, str))
        self.assertTrue(bool(config.api_key))
        self.assertTrue(bool(config.config_path))
        self.assertTrue(bool(config.auth_path))

    def test_load_provider_config_merges_project_layers_from_root_to_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_provider_home = root / "cli" / ".config"
            nested_workspace = root / "apps" / "nested" / "feature"
            root_config_home = root / ".config"
            nested_config_home = root / "apps" / ".config"
            (root / ".git").mkdir(parents=True, exist_ok=True)
            root_config_home.mkdir(parents=True, exist_ok=True)
            nested_config_home.mkdir(parents=True, exist_ok=True)
            nested_workspace.mkdir(parents=True, exist_ok=True)

            (root_config_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                "[model_providers.openai]\n"
                'base_url = "https://root.example/v1"\n',
                encoding="utf-8",
            )
            (root_config_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-root"}', encoding="utf-8")
            (nested_config_home / "config.toml").write_text(
                'model = "gpt-nested"\n',
                encoding="utf-8",
            )

            with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", root / "home" / ".agent_cli" / "config.toml"):
                with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", root / "home" / ".agent_cli" / "auth.json"):
                    with patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", root / "missing" / "config.toml"):
                        with patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", root / "missing" / "auth.json"):
                            with patch("cli.agent_cli.provider.APP_DIR", root / "cli" / "agent_cli"):
                                with patch("cli.agent_cli.provider._ensure_project_provider_bootstrap", return_value=None):
                                    with patch.dict(os.environ, {}, clear=True):
                                        config = load_provider_config(cwd=nested_workspace)

        self.assertIsNotNone(config)
        assert config is not None
        self.assertTrue(bool(config.provider_name))
        self.assertTrue(bool(config.model))
        self.assertTrue(config.base_url is None or isinstance(config.base_url, str))
        self.assertTrue(bool(config.api_key))
        self.assertTrue(bool(config.config_path))
        self.assertTrue(bool(config.auth_path))

    def test_load_provider_config_merges_project_layers_from_root_to_cwd_for_explicit_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_provider_home = root / "cli" / ".config"
            workspace = root / "apps" / "api"
            workspace.mkdir(parents=True, exist_ok=True)
            (root / ".git").write_text("gitdir: here\n", encoding="utf-8")
            (root / ".config").mkdir(parents=True, exist_ok=True)
            (workspace / ".config").mkdir(parents=True, exist_ok=True)

            (root / ".config" / "config.toml").write_text(
                'model_provider = "openai"\n'
                "[model_providers.openai]\n"
                'base_url = "https://root.example/v1"\n'
                'default_model = "gpt-root"\n',
                encoding="utf-8",
            )
            (root / ".config" / "auth.json").write_text('{"OPENAI_API_KEY":"sk-root"}', encoding="utf-8")
            (workspace / ".config" / "config.toml").write_text(
                'model = "gpt-child"\n'
                "[model_providers.openai]\n"
                'default_model = "gpt-child"\n',
                encoding="utf-8",
            )
            (workspace / ".config" / "auth.json").write_text('{"OPENAI_API_KEY":"sk-child"}', encoding="utf-8")

            with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", root / "home" / ".agent_cli" / "config.toml"):
                with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", root / "home" / ".agent_cli" / "auth.json"):
                    with patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", root / "missing" / "config.toml"):
                        with patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", root / "missing" / "auth.json"):
                            with patch("cli.agent_cli.provider.APP_DIR", root / "cli" / "agent_cli"):
                                with patch("cli.agent_cli.provider._ensure_project_provider_bootstrap", return_value=None):
                                    with patch.dict(os.environ, {}, clear=True):
                                        config = load_provider_config(cwd=workspace)

        self.assertIsNotNone(config)
        assert config is not None
        self.assertTrue(bool(config.model))
        self.assertTrue(config.base_url is None or isinstance(config.base_url, str))
        self.assertTrue(bool(config.config_path))
        self.assertTrue(bool(config.auth_path))

    def test_load_provider_config_falls_back_to_agent_cli_home_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_provider_home = root / "cli" / ".config"
            home_config_home = root / ".agent_cli"
            home_config_home.mkdir(parents=True, exist_ok=True)
            (home_config_home / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-home"\n'
                "[model_providers.openai]\n"
                'base_url = "https://home.example/v1"\n',
                encoding="utf-8",
            )
            (home_config_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-home"}', encoding="utf-8")

            with patch("cli.agent_cli.provider._find_project_provider_file", return_value=None):
                with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", home_config_home / "config.toml"):
                    with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", home_config_home / "auth.json"):
                        with patch("cli.agent_cli.provider.APP_DIR", root / "cli" / "agent_cli"):
                            with patch("cli.agent_cli.provider._ensure_project_provider_bootstrap", return_value=None):
                                with patch.dict(os.environ, {}, clear=True):
                                    config = load_provider_config()

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.source, "agent_cli_home")
        self.assertTrue(bool(config.model))
        self.assertTrue(config.base_url is None or isinstance(config.base_url, str))
        self.assertTrue(bool(config.config_path))
        self.assertTrue(bool(config.auth_path))

    def test_load_provider_config_falls_back_to_legacy_compat_home_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy_home = root / ".agent_cli_legacy"
            legacy_home.mkdir(parents=True, exist_ok=True)
            (legacy_home / "config.toml").write_text(
                'model_provider = "deepseek"\n'
                'model = "deepseek-chat"\n'
                "[model_providers.deepseek]\n"
                'base_url = "https://api.deepseek.com/v1"\n',
                encoding="utf-8",
            )
            (legacy_home / "auth.json").write_text('{"DEEPSEEK_API_KEY":"sk-deepseek"}', encoding="utf-8")

            with patch("cli.agent_cli.provider._find_project_provider_file", return_value=None):
                with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", root / ".agent_cli" / "config.toml"):
                    with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", root / ".agent_cli" / "auth.json"):
                        with patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", legacy_home / "config.toml"):
                            with patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", legacy_home / "auth.json"):
                                with patch.dict(os.environ, {}, clear=True):
                                    config = load_provider_config()

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.source, "project_local")
        self.assertTrue(bool(config.model))
        self.assertTrue(config.base_url is None or isinstance(config.base_url, str))
        self.assertTrue(bool(config.api_key))
        self.assertTrue(bool(config.planner_kind))
        self.assertTrue(bool(config.config_path))
        self.assertTrue(bool(config.auth_path))

    def test_load_provider_config_infers_reasoner_planner_kind(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local_config_home = root / ".agent_cli"
            local_config_home.mkdir(parents=True, exist_ok=True)
            (local_config_home / "config.toml").write_text(
                'model_provider = "deepseek"\n'
                'model = "deepseek-reasoner"\n'
                "[model_providers.deepseek]\n"
                'base_url = "https://api.deepseek.com"\n',
                encoding="utf-8",
            )
            (local_config_home / "auth.json").write_text('{"DEEPSEEK_API_KEY":"sk-reasoner"}', encoding="utf-8")

            def _find_local(filename: str) -> Path:
                return local_config_home / filename

            with patch("cli.agent_cli.provider._find_project_provider_file", side_effect=_find_local):
                with patch.dict(os.environ, {}, clear=True):
                    config = load_provider_config()

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.provider_name, "deepseek")
        self.assertEqual(config.model, "deepseek-reasoner")
        self.assertEqual(config.api_key, "sk-reasoner")
        self.assertEqual(config.planner_kind, "deepseek_reasoner")

    def test_rule_based_agent_keeps_provider_not_ready_when_provider_specific_api_key_is_missing(self) -> None:
        fake_paths = SimpleNamespace(
            config_path=Path("/tmp/config.toml"),
            auth_path=Path("/tmp/auth.json"),
        )
        missing_key_config = ProviderConfig(
            model="qwen-plus",
            api_key="",
            provider_name="qwen",
            planner_kind="openai_chat",
            auth_mode="api_key",
            raw_provider={"api_key_env": "DASHSCOPE_API_KEY"},
        )

        with patch("cli.agent_cli.agent.resolve_provider_paths", return_value=fake_paths):
            with patch("cli.agent_cli.agent.load_provider_config", return_value=missing_key_config):
                agent = RuleBasedAgent()

        status = agent.provider_status()
        self.assertEqual(status["provider_ready"], "false")
        self.assertIn("missing API credential", status["provider_source"])
        self.assertEqual(status["provider_name"], "-")

    def test_openai_planner_prompt_prefers_structured_file_tools(self) -> None:
        host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
        planner = OpenAIPlanner(
            ProviderConfig(
                model="gpt-5.4",
                api_key="sk-test",
                provider_name="openai",
                planner_kind="openai_responses",
                base_url="https://api.openai.com/v1",
            ),
            host_platform=host_platform,
        )

        self.assertIn("/grep_files", planner.system_prompt)
        self.assertIn("/read_file", planner.system_prompt)
        self.assertIn("/list_dir", planner.system_prompt)
        self.assertNotIn("/file_list", planner.system_prompt)
        self.assertNotIn("/file_search", planner.system_prompt)
        self.assertNotIn("/file_read", planner.system_prompt)
        self.assertIn("prefer grep_files, list_dir, and read_file", planner.system_prompt)

    def test_deepseek_planner_prompt_prefers_structured_file_tools(self) -> None:
        host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        self.assertIn("prefer grep_files, list_dir, and read_file", planner.system_prompt)
        self.assertNotIn("prefer file_list, file_search, and file_read", planner.system_prompt)

    def test_load_provider_config_resolves_model_registry_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local_config_home = root / ".agent_cli"
            local_config_home.mkdir(parents=True, exist_ok=True)
            (local_config_home / "config.toml").write_text(
                'model_provider = "deepseek"\n'
                'model = "deepseek_reasoner"\n'
                "[model_providers.deepseek]\n"
                'base_url = "https://api.deepseek.com"\n'
                'planner_kind = "deepseek_reasoner"\n'
                'default_model = "deepseek_reasoner"\n'
                "[models.deepseek_reasoner]\n"
                'provider = "deepseek"\n'
                'model_id = "deepseek-reasoner"\n'
                'planner_kind = "deepseek_reasoner"\n',
                encoding="utf-8",
            )
            (local_config_home / "auth.json").write_text('{"DEEPSEEK_API_KEY":"sk-alias"}', encoding="utf-8")

            def _find_local(filename: str) -> Path:
                return local_config_home / filename

            with patch("cli.agent_cli.provider._find_project_provider_file", side_effect=_find_local):
                with patch.dict(os.environ, {}, clear=True):
                    config = load_provider_config()

        self.assertIsNotNone(config)
        assert config is not None
        self.assertTrue(isinstance(config.model_key, str))
        self.assertTrue(bool(config.model))
        self.assertTrue(bool(config.provider_name))
        self.assertTrue(bool(config.planner_kind))

    def test_load_provider_config_env_model_alias_uses_registry_model_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local_config_home = root / ".agent_cli"
            local_config_home.mkdir(parents=True, exist_ok=True)
            (local_config_home / "config.toml").write_text(
                'model_provider = "qwen"\n'
                'model = "qwen_plus"\n'
                "[model_providers.qwen]\n"
                'base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"\n'
                'api_key_env = "DASHSCOPE_API_KEY"\n'
                'planner_kind = "openai_chat"\n'
                'default_model = "qwen_plus"\n'
                "[models.qwen_plus]\n"
                'provider = "qwen"\n'
                'model_id = "qwen-plus"\n'
                'planner_kind = "openai_chat"\n',
                encoding="utf-8",
            )
            (local_config_home / "auth.json").write_text('{"DASHSCOPE_API_KEY":"sk-qwen"}', encoding="utf-8")

            def _find_local(filename: str) -> Path:
                return local_config_home / filename

            with patch("cli.agent_cli.provider._find_project_provider_file", side_effect=_find_local):
                with patch.dict(
                    os.environ,
                    {
                        "AGENT_CLI_PROVIDER": "qwen",
                        "AGENT_CLI_MODEL": "qwen_plus",
                    },
                    clear=True,
                ):
                    config = load_provider_config()

        self.assertIsNotNone(config)
        assert config is not None
        self.assertTrue(isinstance(config.model_key, str))
        self.assertTrue(bool(config.model))
        self.assertTrue(bool(config.provider_name))
        self.assertTrue(bool(config.planner_kind))

    def test_provider_specific_api_key_env_does_not_fall_back_to_openai_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local_config_home = root / ".agent_cli"
            local_config_home.mkdir(parents=True, exist_ok=True)
            (local_config_home / "config.toml").write_text(
                'model_provider = "qwen"\n'
                'model = "qwen_plus"\n'
                "[model_providers.qwen]\n"
                'base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"\n'
                'api_key_env = "DASHSCOPE_API_KEY"\n'
                'planner_kind = "openai_chat"\n'
                'default_model = "qwen_plus"\n'
                "[models.qwen_plus]\n"
                'provider = "qwen"\n'
                'model_id = "qwen-plus"\n'
                'planner_kind = "openai_chat"\n',
                encoding="utf-8",
            )
            (local_config_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-openai-only"}', encoding="utf-8")

            def _find_local(filename: str) -> Path:
                return local_config_home / filename

            with patch("cli.agent_cli.provider._find_project_provider_file", side_effect=_find_local):
                with patch.dict(os.environ, {}, clear=True):
                    config = load_provider_config()

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.provider_name, "qwen")
        self.assertEqual(config.model, "qwen-plus")
        self.assertEqual(config.api_key, "")
        self.assertEqual(config.auth_mode, "api_key")
        self.assertEqual(config.auth_status, "missing")

    def test_rule_based_agent_can_switch_between_chat_and_reasoner_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_provider_home = root / "cli" / ".config"
            local_config_home = root / ".agent_cli"
            local_config_home.mkdir(parents=True, exist_ok=True)
            (local_config_home / "config.toml").write_text(
                'model_provider = "deepseek"\n'
                'model = "deepseek-reasoner"\n'
                "[model_providers.deepseek]\n"
                'base_url = "https://api.deepseek.com"\n'
                'planner_kind = "deepseek_reasoner"\n',
                encoding="utf-8",
            )
            (local_config_home / "auth.json").write_text('{"DEEPSEEK_API_KEY":"sk-switch"}', encoding="utf-8")

            def _fake_load_provider_config(*, cwd=None, env_overrides=None):
                del cwd
                overrides = dict(env_overrides or {})
                model = str(overrides.get("AGENT_CLI_MODEL") or "deepseek-reasoner").strip()
                planner_kind = "deepseek_chat" if model == "deepseek-chat" else "deepseek_reasoner"
                return ProviderConfig(
                    model=model,
                    api_key="sk-switch",
                    provider_name="deepseek",
                    model_key=model.replace("-", "_"),
                    planner_kind=planner_kind,
                    wire_api="openai_chat",
                    base_url="https://api.deepseek.com",
                    source="env" if overrides.get("AGENT_CLI_MODEL") else "project_local",
                    config_path=str(local_config_home / "config.toml"),
                    auth_path=str(local_config_home / "auth.json"),
                )

            host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
            with patch("cli.agent_cli.agent.load_provider_config", side_effect=_fake_load_provider_config):
                with patch("cli.agent_cli.agent.build_planner", side_effect=lambda config, **kwargs: config):
                    with patch("cli.agent_cli.agent.resolve_provider_paths", return_value=ProviderPathResolution(
                        config_path=local_config_home / "config.toml",
                        auth_path=local_config_home / "auth.json",
                        config_exists=True,
                        auth_exists=True,
                        used_project_local=True,
                    )):
                        with patch.dict(os.environ, {AGENTHUB_PROVIDER_HOME_ENV: str(project_provider_home)}, clear=True):
                            agent = RuleBasedAgent(host_platform=host_platform)
                            chat_status = agent.switch_provider_line("chat")
                            reasoner_status = agent.switch_provider_line("reasoner")

        self.assertEqual(chat_status["provider_name"], "deepseek")
        self.assertEqual(chat_status["provider_model"], "deepseek-chat")
        self.assertEqual(chat_status["provider_planner"], "deepseek_chat")
        self.assertEqual(chat_status["provider_source"], "session_override")
        self.assertEqual(chat_status["provider_source_raw"], "env")
        self.assertEqual(reasoner_status["provider_model"], "deepseek-reasoner")
        self.assertEqual(reasoner_status["provider_planner"], "deepseek_reasoner")
        self.assertEqual(reasoner_status["provider_source"], "session_override")
        self.assertEqual(reasoner_status["provider_source_raw"], "env")

    def test_env_reasoner_model_overrides_explicit_deepseek_chat_planner_kind(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local_config_home = root / ".agent_cli"
            local_config_home.mkdir(parents=True, exist_ok=True)
            (local_config_home / "config.toml").write_text(
                'model_provider = "deepseek"\n'
                'model = "deepseek-chat"\n'
                "[model_providers.deepseek]\n"
                'base_url = "https://api.deepseek.com"\n'
                'planner_kind = "deepseek_chat"\n',
                encoding="utf-8",
            )
            (local_config_home / "auth.json").write_text('{"DEEPSEEK_API_KEY":"sk-reasoner"}', encoding="utf-8")

            def _find_local(filename: str) -> Path:
                return local_config_home / filename

            with patch("cli.agent_cli.provider._find_project_provider_file", side_effect=_find_local):
                with patch.dict(os.environ, {"AGENT_CLI_MODEL": "deepseek-reasoner"}, clear=True):
                    config = load_provider_config()

        self.assertIsNotNone(config)
        assert config is not None
        self.assertTrue(bool(config.model))
        self.assertTrue(bool(config.planner_kind))

    def test_provider_status_includes_resolved_paths_when_not_configured(self) -> None:
        resolved = ProviderPathResolution(
            config_path=Path("C:/tmp/test_config.toml"),
            auth_path=Path("C:/tmp/test_auth.json"),
            config_exists=False,
            auth_exists=False,
            used_project_local=False,
        )
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        with patch("cli.agent_cli.agent.resolve_provider_paths", return_value=resolved):
            with patch("cli.agent_cli.agent.load_provider_config", return_value=None):
                agent = RuleBasedAgent(host_platform=host_platform)

        status = agent.provider_status()
        self.assertEqual(status["provider_ready"], "false")
        self.assertEqual(status["provider_config_path"], str(Path("C:/tmp/test_config.toml")))
        self.assertEqual(status["provider_auth_path"], str(Path("C:/tmp/test_auth.json")))
        self.assertEqual(status["platform_family"], "windows")
        self.assertEqual(status["platform_os"], "windows")
        self.assertEqual(status["shell_kind"], "powershell")

    def test_rule_based_agent_set_cwd_reloads_provider_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_provider_home = root / "cli" / ".config"
            workspace_a = root / "workspace-a"
            workspace_b = root / "workspace-b"
            config_a = workspace_a / ".config"
            config_b = workspace_b / ".config"
            config_a.mkdir(parents=True, exist_ok=True)
            config_b.mkdir(parents=True, exist_ok=True)

            (config_a / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-a"\n'
                "[model_providers.openai]\n"
                'base_url = "https://a.example/v1"\n',
                encoding="utf-8",
            )
            (config_a / "auth.json").write_text('{"OPENAI_API_KEY":"sk-a"}', encoding="utf-8")
            (config_b / "config.toml").write_text(
                'model_provider = "openai"\n'
                'model = "gpt-b"\n'
                "[model_providers.openai]\n"
                'base_url = "https://b.example/v1"\n',
                encoding="utf-8",
            )
            (config_b / "auth.json").write_text('{"OPENAI_API_KEY":"sk-b"}', encoding="utf-8")

            with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", root / "home" / ".agent_cli" / "config.toml"):
                with patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", root / "home" / ".agent_cli" / "auth.json"):
                    with patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", root / "missing" / "config.toml"):
                        with patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", root / "missing" / "auth.json"):
                            host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
                            with patch("cli.agent_cli.provider.APP_DIR", root / "cli" / "agent_cli"):
                                with patch("cli.agent_cli.provider._ensure_project_provider_bootstrap", return_value=None):
                                    with patch.dict(os.environ, {}, clear=True):
                                        agent = RuleBasedAgent(host_platform=host_platform)
                                        agent.set_cwd(workspace_a)
                                        status_a = agent.provider_status()
                                        agent.set_cwd(workspace_b)
                                        status_b = agent.provider_status()

        self.assertEqual(status_a["provider_ready"], "true")
        self.assertTrue(bool(status_a["provider_model"]))
        self.assertTrue(bool(status_a["provider_config_path"]))
        self.assertEqual(status_b["provider_ready"], "true")
        self.assertTrue(bool(status_b["provider_model"]))
        self.assertTrue(bool(status_b["provider_config_path"]))

    def test_rule_based_agent_maps_natural_language_list_dir_to_windows_file_list(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        with patch("cli.agent_cli.agent.load_provider_config", return_value=None):
            agent = RuleBasedAgent(host_platform=host_platform)

        intent = agent.plan("列出当前目录下的文件")

        self.assertEqual(intent.command_text, "/list_dir . --limit 50 --depth 1")
        self.assertEqual(intent.status_hint, "tool")

    def test_rule_based_agent_maps_natural_language_list_dir_to_linux_file_list(self) -> None:
        host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
        with patch("cli.agent_cli.agent.load_provider_config", return_value=None):
            agent = RuleBasedAgent(host_platform=host_platform)

        intent = agent.plan("list current directory")

        self.assertEqual(intent.command_text, "/list_dir . --limit 50 --depth 1")
        self.assertEqual(intent.status_hint, "tool")

    def test_rule_based_agent_prefers_planner_for_natural_language_when_available(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner_calls: list[str] = []

        class _FakePlanner:
            @staticmethod
            def public_summary() -> dict[str, str]:
                return {
                    "provider_name": "deepseek",
                    "model_key": "deepseek_reasoner",
                    "model": "deepseek-reasoner",
                    "planner_kind": "deepseek_reasoner",
                    "base_url": "https://api.deepseek.com",
                    "source": "test",
                    "config_path": "C:/test/.agent_cli/config.toml",
                    "auth_path": "C:/test/.agent_cli/auth.json",
                }

            def plan(self, text, history, *, tool_executor=None, attachments=None):
                planner_calls.append(text)
                return SimpleNamespace(
                    assistant_text="planner handled it",
                    command_text=None,
                    status_hint="llm",
                )

        with patch(
            "cli.agent_cli.agent.load_provider_config",
            return_value=ProviderConfig(model="deepseek-reasoner", api_key="sk-test"),
        ):
            with patch("cli.agent_cli.agent.build_planner", return_value=_FakePlanner()):
                agent = RuleBasedAgent(host_platform=host_platform)

        intent = agent.plan("list current directory")

        self.assertEqual(planner_calls, ["list current directory"])
        self.assertEqual(intent.command_text, "/list_dir . --limit 50 --depth 1")
        self.assertIn("列出当前工作区文件", intent.assistant_text)

    def test_openai_planner_extracts_and_normalizes_shell_suggestion_for_windows(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = OpenAIPlanner(ProviderConfig(model="gpt-5.4", api_key="sk-test"), host_platform=host_platform)
        planner.client = self._FakeOpenAIClient(["请直接执行 /shell ls -la"])

        intent = planner.plan("列出当前目录下的文件", [])

        self.assertEqual(intent.command_text, "/shell Get-ChildItem -Force")
        self.assertEqual(intent.status_hint, "tool")

    def test_openai_planner_extracts_and_normalizes_shell_suggestion_for_linux(self) -> None:
        host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
        planner = OpenAIPlanner(ProviderConfig(model="gpt-5.4", api_key="sk-test"), host_platform=host_platform)
        planner.client = self._FakeOpenAIClient(["Please run /shell Get-Location"])

        intent = planner.plan("show current directory", [])

        self.assertEqual(intent.command_text, "/shell pwd")
        self.assertEqual(intent.status_hint, "tool")

    def test_openai_planner_accepts_structured_json_intent(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = OpenAIPlanner(ProviderConfig(model="gpt-5.4", api_key="sk-test"), host_platform=host_platform)
        planner.client = self._FakeOpenAIClient(
            ['{"assistant_text":"识别为查看目录，准备执行。","command_text":"/shell pwd","status_hint":"tool"}']
        )

        intent = planner.plan("当前目录是什么", [])

        self.assertEqual(intent.command_text, "/shell Get-Location")
        self.assertEqual(intent.assistant_text, "识别为查看目录，准备执行。")

    def test_openai_planner_trims_followup_commands_from_single_command_text(self) -> None:
        host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
        planner = OpenAIPlanner(ProviderConfig(model="gpt-5.4", api_key="sk-test"), host_platform=host_platform)
        planner.client = self._FakeOpenAIClient(
            [
                ['{"assistant_text":"我先检查项目结构。","command_text":"/file_list . --limit 200 /file_read README.md","status_hint":"tool"}'],
            ]
        )

        intent = planner.plan("你看看当前项目是干什么的", [])

        self.assertEqual(intent.command_text, "/file_list . --limit 200")
        self.assertEqual(intent.assistant_text, "我先检查项目结构。")
        self.assertEqual(intent.status_hint, "tool")
        self.assertEqual(len(intent.tool_events), 0)

    def test_openai_planner_without_tool_executor_keeps_structured_intent(self) -> None:
        host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
        planner = OpenAIPlanner(ProviderConfig(model="gpt-5.4", api_key="sk-test"), host_platform=host_platform)
        planner.client = self._FakeOpenAIClient(
            [
                ['{"assistant_text":"我先检查项目结构和说明文件。","command_text":"/file_list . --limit 5","status_hint":"tool"}'],
            ]
        )

        intent = planner.plan("你看看当前项目是干什么的", [])

        self.assertEqual(intent.assistant_text, "我先检查项目结构和说明文件。")
        self.assertEqual(intent.command_text, "/file_list . --limit 5")
        self.assertEqual(intent.status_hint, "tool")
        self.assertEqual(len(intent.tool_events), 0)

    def test_openai_planner_uses_native_responses_function_tool_loop(self) -> None:
        host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
        planner = OpenAIPlanner(ProviderConfig(model="gpt-5.4", api_key="sk-test"), host_platform=host_platform)
        fake_client = self._FakeOpenAINativeClient(
            [
                self._FakeResponsesNativeResponse(
                    "resp_1",
                    [
                        self._response_function_call(
                            call_id="call_1",
                            name="file_list",
                            arguments='{"path":".","limit":5}',
                        )
                    ],
                ),
                self._FakeResponsesNativeResponse(
                    "resp_2",
                    [
                        self._response_message(
                            "这是一个 Agent CLI 项目，包含 CLI、GUI 桥接和插件机制。"
                        )
                    ],
                ),
            ]
        )
        planner.client = fake_client

        observed_commands: list[str] = []

        def _executor(command_text: str):
            observed_commands.append(command_text)
            return (
                "执行完成",
                [
                    ToolEvent(
                        name="file_list",
                        ok=True,
                        summary="files=2",
                        payload={
                            "path": ".",
                            "files": [
                                {"path": "README.md", "size": 100},
                                {"path": "cli/README.md", "size": 200},
                            ],
                        },
                    )
                ],
            )

        intent = planner.plan("你看看当前项目是干什么的", [], tool_executor=_executor)

        self.assertEqual(observed_commands, ["/list_dir . --limit 5"])
        self.assertEqual(intent.assistant_text, "这是一个 Agent CLI 项目，包含 CLI、GUI 桥接和插件机制。")
        self.assertEqual(intent.status_hint, "tool")
        self.assertEqual(len(intent.tool_events), 1)
        self.assertEqual(len(fake_client.responses.requests), 2)
        self.assertFalse(bool(fake_client.responses.requests[0].get("stream")))
        self.assertEqual(fake_client.responses.requests[0]["tool_choice"], "auto")
        self.assertEqual(fake_client.responses.requests[1]["previous_response_id"], "resp_1")
        self.assertEqual(
            [item.get("type") for item in fake_client.responses.requests[1]["input"]],
            ["function_call_output"],
        )
        self.assertEqual(fake_client.responses.requests[1]["input"][0]["type"], "function_call_output")

    def test_openai_planner_builds_reference_compatible_openai_headers(self) -> None:
        host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
        with patch("cli.agent_cli.providers.openai_client.OpenAI") as openai_cls:
            OpenAIPlanner(ProviderConfig(model="gpt-5.4", api_key="sk-test"), host_platform=host_platform)

        kwargs = openai_cls.call_args.kwargs
        self.assertEqual(kwargs["api_key"], "sk-test")
        self.assertIsNone(kwargs["base_url"])
        self.assertEqual(kwargs["default_headers"]["originator"], "reference_cli_rs")
        self.assertTrue(kwargs["default_headers"]["User-Agent"].startswith("reference_cli_rs/"))

    def test_openai_planner_builds_codex_style_headers_for_codex_openai_profile(self) -> None:
        host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
        with patch("cli.agent_cli.providers.openai_client.OpenAI") as openai_cls:
            OpenAIPlanner(
                ProviderConfig(
                    model="gpt-5.4",
                    api_key="sk-test",
                    interaction_profile="codex_openai",
                ),
                host_platform=host_platform,
            )

        kwargs = openai_cls.call_args.kwargs
        self.assertEqual(kwargs["default_headers"]["originator"], "codex_exec")
        self.assertTrue(kwargs["default_headers"]["User-Agent"].startswith("codex_exec/"))

    def test_chat_completions_planner_builds_reference_compatible_openai_headers(self) -> None:
        host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
        with patch("cli.agent_cli.providers.openai_client.OpenAI") as openai_cls:
            ChatCompletionsPlanner(
                ProviderConfig(model="glm-5", api_key="sk-test", base_url="https://open.bigmodel.cn/api/paas/v4"),
                host_platform=host_platform,
            )

        kwargs = openai_cls.call_args.kwargs
        self.assertEqual(kwargs["api_key"], "sk-test")
        self.assertEqual(kwargs["base_url"], "https://open.bigmodel.cn/api/paas/v4")
        self.assertEqual(kwargs["default_headers"]["originator"], "reference_cli_rs")
        self.assertTrue(kwargs["default_headers"]["User-Agent"].startswith("reference_cli_rs/"))

    def test_openai_planner_native_loop_returns_structured_tool_fallback_when_model_omits_final_text(self) -> None:
        host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
        planner = OpenAIPlanner(ProviderConfig(model="gpt-5.4", api_key="sk-test"), host_platform=host_platform)
        planner.client = self._FakeOpenAINativeClient(
            [
                self._FakeResponsesNativeResponse(
                    "resp_1",
                    [
                        self._response_function_call(
                            call_id="call_1",
                            name="file_read",
                            arguments='{"path":"README.md","max_chars":4000}',
                        )
                    ],
                ),
                self._FakeResponsesNativeResponse("resp_2", []),
            ]
        )

        def _executor(command_text: str):
            self.assertEqual(command_text, "/read_file README.md --max-chars 4000")
            return (
                "执行完成",
                [
                    ToolEvent(
                        name="file_read",
                        ok=True,
                        summary="file read ok",
                        payload={"path": "README.md", "text": "AgentHub project", "line_count": 3},
                    )
                ],
            )

        intent = planner.plan("读取 README", [], tool_executor=_executor)

        self.assertEqual(intent.assistant_text, "已读取文件：README.md")
        self.assertEqual(intent.status_hint, "tool")
        self.assertEqual(len(intent.tool_events), 1)

    def test_openai_planner_native_loop_parses_structured_final_json_without_tool_calls(self) -> None:
        host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
        planner = OpenAIPlanner(ProviderConfig(model="gpt-5.4", api_key="sk-test"), host_platform=host_platform)
        planner.client = self._FakeOpenAINativeClient(
            [
                self._FakeResponsesNativeResponse(
                    "resp_1",
                    [
                        self._response_message(
                            '{"assistant_text":"你好，有什么我可以帮你处理的？","command_text":null,"status_hint":"ready"}'
                        )
                    ],
                ),
            ]
        )

        intent = planner.plan("你好", [], tool_executor=lambda command_text: ("", []))

        self.assertEqual(
            intent.assistant_text,
            '{"assistant_text":"你好，有什么我可以帮你处理的？","command_text":null,"status_hint":"ready"}',
        )
        self.assertIsNone(intent.command_text)
        self.assertEqual(intent.status_hint, "llm")
        self.assertEqual(len(intent.tool_events), 0)

    def test_openai_planner_falls_back_to_fresh_followup_replanning_when_continuation_request_fails(self) -> None:
        host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
        planner = OpenAIPlanner(ProviderConfig(model="gpt-5.4", api_key="sk-test"), host_platform=host_platform)
        planner.client = self._FakeOpenAINativeClient(
            [
                self._FakeResponsesNativeResponse(
                    "resp_1",
                    [
                        self._response_function_call(
                            call_id="call_1",
                            name="file_list",
                            arguments='{"path":".","limit":5}',
                        )
                    ],
                ),
                RuntimeError("proxy_unavailable"),
                self._FakeResponsesNativeResponse(
                    "resp_2",
                    [
                        self._response_function_call(
                            call_id="call_2",
                            name="file_read",
                            arguments='{"path":"README.md","max_chars":4000}',
                        )
                    ],
                ),
                self._FakeResponsesNativeResponse(
                    "resp_3",
                    [
                        self._response_message(
                            "这是一个多模块 AgentHub 项目，包含 CLI、GUI 与自动化能力。"
                        )
                    ],
                ),
            ]
        )

        observed_commands: list[str] = []

        def _executor(command_text: str):
            observed_commands.append(command_text)
            if command_text == "/list_dir . --limit 5":
                return (
                    "执行完成",
                    [
                        ToolEvent(
                            name="file_list",
                            ok=True,
                            summary="files=3",
                            payload={"path": ".", "files": [{"path": "README.md"}, {"path": "cli"}, {"path": "gui"}]},
                        )
                    ],
                )
            self.assertEqual(command_text, "/read_file README.md --max-chars 4000")
            return (
                "读取完成",
                [
                    ToolEvent(
                        name="file_read",
                        ok=True,
                        summary="file read ok",
                        payload={"path": "README.md", "text": "AgentHub project overview"},
                    )
                ],
            )

        intent = planner.plan("你看看当前项目是干什么的", [], tool_executor=_executor)

        self.assertEqual(observed_commands, ["/list_dir . --limit 5", "/read_file README.md --max-chars 4000"])
        self.assertEqual(intent.assistant_text, "这是一个多模块 AgentHub 项目，包含 CLI、GUI 与自动化能力。")
        self.assertEqual(intent.status_hint, "tool")
        self.assertIsNone(intent.command_text)
        self.assertEqual(len(intent.tool_events), 2)
        self.assertEqual(len(planner.client.responses.requests), 4)
        self.assertEqual(planner.client.responses.requests[1]["previous_response_id"], "resp_1")
        self.assertEqual(planner.client.responses.requests[1]["input"][0]["type"], "function_call_output")
        self.assertEqual(planner.client.responses.requests[2]["previous_response_id"], "resp_1")
        self.assertEqual(planner.client.responses.requests[2]["input"][0]["type"], "function_call_output")
        self.assertEqual(planner.client.responses.requests[3]["previous_response_id"], "resp_2")
        self.assertEqual(planner.client.responses.requests[3]["input"][0]["type"], "function_call_output")

    def test_openai_planner_keeps_workspace_skills_out_of_system_prompt_but_injects_explicit_skill_body(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "repo"
            skill_dir = workspace / ".agents" / "skills" / "demo"
            skill_dir.mkdir(parents=True)
            skill_path = skill_dir / "SKILL.md"
            skill_path.write_text(
                "---\nname: demo\ndescription: inspect repo\n---\n\n# demo body\n",
                encoding="utf-8",
            )

            host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
            planner = OpenAIPlanner(
                ProviderConfig(model="gpt-5.4", api_key="sk-test"),
                host_platform=host_platform,
                cwd=str(workspace),
            )

            composed = planner._compose_user_text("please use $demo", None)

        self.assertNotIn("## Skills", planner.system_prompt)
        self.assertNotIn("- demo: inspect repo", planner.system_prompt)
        self.assertNotIn(str(skill_path.resolve()).replace("\\", "/"), planner.system_prompt)
        self.assertIn("SKILL_INSTRUCTIONS:", composed)
        self.assertIn("# demo body", composed)

    def test_openai_planner_does_not_inject_policy_hint_for_generic_requirement_prompt(self) -> None:
        host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
        planner = OpenAIPlanner(
            ProviderConfig(
                model="gpt-5.4",
                api_key="sk-test",
                provider_name="openai",
                planner_kind="openai_responses",
                interaction_profile="codex_openai",
            ),
            host_platform=host_platform,
            cwd="/tmp",
        )

        composed = planner._compose_user_text(
            "请创建一个最小 Python 脚本，要求：启动后每隔 0.2 秒打印 tick。",
            None,
        )

        self.assertNotIn("POLICY_QA_HINT", composed)
        self.assertNotIn("policy_doc_search", composed)
        self.assertNotIn("policy_doc_read", composed)

    def test_openai_planner_relevant_history_keeps_recent_items_for_generic_requirement_prompt(self) -> None:
        host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")
        planner = OpenAIPlanner(
            ProviderConfig(
                model="gpt-5.4",
                api_key="sk-test",
                provider_name="openai",
                planner_kind="openai_responses",
                interaction_profile="codex_openai",
            ),
            host_platform=host_platform,
            cwd="/tmp",
        )
        history = [
            {"role": "user", "content": "普通编码上下文 1"},
            {"role": "assistant", "content": "普通编码回复 1"},
            {"role": "user", "content": "普通编码上下文 2"},
            {"role": "assistant", "content": "普通编码回复 2"},
        ]

        relevant = planner._relevant_history(
            "请创建一个最小 Python 脚本，要求：启动后每隔 0.2 秒打印 tick。",
            history,
        )

        self.assertEqual(relevant, history)

    def test_openai_chat_uses_chat_completions_planner(self) -> None:
        planner = build_planner(
            ProviderConfig(
                model="glm-5",
                api_key="sk-test",
                provider_name="glm",
                planner_kind="openai_chat",
                base_url="https://open.bigmodel.cn/api/paas/v4",
            )
        )

        self.assertIsInstance(planner, ChatCompletionsPlanner)

    def test_chat_completions_planner_exports_remain_generic_with_legacy_alias(self) -> None:
        from cli.agent_cli.providers import ChatCompletionsPlanner as ExportedChatCompletionsPlanner
        from cli.agent_cli.providers.deepseek_planner import DeepSeekPlanner as LegacyDeepSeekPlanner

        self.assertIs(ExportedChatCompletionsPlanner, ChatCompletionsPlanner)
        self.assertIs(LegacyDeepSeekPlanner, ChatCompletionsPlanner)

    def test_planner_postprocessing_rules_are_shared(self) -> None:
        rule_text = concise_answer_prompt_text()
        self.assertIn("first sentence", rule_text)
        self.assertIn("tables", rule_text)

        sanitized = sanitize_final_answer_text("## Title\n\n正文")
        self.assertEqual(sanitized, "## Title\n\n正文")

        lines = generic_tool_event_summary_lines(
            [
                ToolEvent(
                    name="web_search",
                    ok=True,
                    summary="web results=2",
                    payload={
                        "query": "北京天气",
                        "results": [{"title": "北京天气预报", "url": "https://example.com/weather"}],
                    },
                )
            ]
        )
        self.assertEqual(lines, ["- web_search: ok | query=北京天气 | top_title=北京天气预报 | top_url=https://example.com/weather"])

        context_blocks = generic_tool_event_context_blocks(
            [
                ToolEvent(
                    name="web_fetch",
                    ok=True,
                    summary="web page loaded",
                    payload={
                        "url": "https://example.com/weather",
                        "final_url": "https://example.com/weather",
                        "title": "北京天气预报",
                        "text": "今天 多云 21/7℃ <3级",
                        "line_count": 12,
                        "link_count": 3,
                    },
                )
            ]
        )
        self.assertEqual(context_blocks[0]["name"], "web_fetch")
        self.assertIn("21/7℃", context_blocks[0]["text"])

    def test_deepseek_planner_executes_tool_calls_via_executor(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="shell", arguments='{"command":"ls -la"}'),
        )
        planner.client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="先查看目录。", tool_calls=[tool_call]),
                SimpleNamespace(content="目录已列出。", tool_calls=[]),
            ]
        )

        def _executor(command_text: str):
            self.assertEqual(command_text, "/exec_command 'Get-ChildItem -Force'")
            return (
                "执行完成",
                [SimpleNamespace(name="shell", ok=True, summary="shell rc=0", payload={})],
            )

        intent = planner.plan("列出当前目录下的文件", [], tool_executor=_executor)

        self.assertEqual(intent.assistant_text, "目录已列出。")
        self.assertEqual(intent.status_hint, "tool")
        self.assertEqual(len(intent.tool_events), 1)

    def test_deepseek_planner_synthesizes_final_answer_after_tool_calls_when_model_omits_final_text(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="shell", arguments='{"command":"ls -la"}'),
        )
        fake_client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="", tool_calls=[tool_call]),
                SimpleNamespace(content="", tool_calls=[]),
                SimpleNamespace(content="当前目录文件已经列出。", tool_calls=[]),
            ]
        )
        planner.client = fake_client

        def _executor(command_text: str):
            self.assertEqual(command_text, "/exec_command 'Get-ChildItem -Force'")
            return (
                "执行完成",
                [ToolEvent(name="shell", ok=True, summary="shell rc=0", payload={"stdout": "a.txt\nb.txt\n"})],
            )

        intent = planner.plan("列出当前目录下的文件", [], tool_executor=_executor)

        self.assertEqual(intent.assistant_text, "当前目录文件已经列出。")
        self.assertEqual(intent.status_hint, "tool")
        self.assertEqual(len(fake_client.chat.completions.requests), 3)

    def test_deepseek_planner_replans_after_continuation_failure(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="file_list", arguments='{"path":".","limit":5}'),
        )
        call_count = 0

        def fake_chat_completion_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[tool_call]))])
            if call_count == 2:
                raise RuntimeError("proxy_unavailable")
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="最终答案", tool_calls=[]))])

        planner._chat_completion_create = fake_chat_completion_create

        observed_commands: list[str] = []

        def _executor(command_text: str):
            observed_commands.append(command_text)
            return (
                "执行完成",
                [
                    ToolEvent(
                        name="file_list",
                        ok=True,
                        summary="files=1",
                        payload={"path": ".", "files": []},
                    )
                ],
            )

        intent = planner.plan("列出当前目录下的文件", [], tool_executor=_executor)

        self.assertEqual(observed_commands, ["/list_dir . --limit 5"])
        self.assertEqual(intent.assistant_text, "最终答案")
        self.assertEqual(intent.status_hint, "tool")
        self.assertEqual(len(intent.tool_events), 1)
        self.assertEqual(call_count, 3)
        self.assertEqual(intent.timings["planning_rounds"], 2)
        self.assertEqual(intent.timings["synthesis_rounds"], 0)

    def test_deepseek_planner_replans_after_continuation_failure(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="file_list", arguments='{"path":".","limit":5}'),
        )
        call_count = 0

        def fake_chat_completion_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[tool_call]))])
            if call_count == 2:
                raise RuntimeError("proxy_unavailable")
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="最终答案", tool_calls=[]))])

        planner._chat_completion_create = fake_chat_completion_create

        observed_commands: list[str] = []

        def _executor(command_text: str):
            observed_commands.append(command_text)
            return (
                "执行完成",
                [
                    ToolEvent(
                        name="file_list",
                        ok=True,
                        summary="files=1",
                        payload={"path": ".", "files": []},
                    )
                ],
            )

        intent = planner.plan("列出当前目录下的文件", [], tool_executor=_executor)

        self.assertEqual(observed_commands, ["/list_dir . --limit 5"])
        self.assertEqual(intent.assistant_text, "最终答案")
        self.assertEqual(intent.status_hint, "tool")
        self.assertEqual(len(intent.tool_events), 1)
        self.assertEqual(call_count, 3)
        self.assertEqual(intent.timings["planning_rounds"], 2)
        self.assertEqual(intent.timings["synthesis_rounds"], 0)

    def test_deepseek_planner_synthesis_context_keeps_web_fetch_text(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="web_fetch", arguments='{"url":"https://weather.example.com/beijing"}'),
        )
        fake_client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="", tool_calls=[tool_call]),
                SimpleNamespace(content="", tool_calls=[]),
                SimpleNamespace(content="北京今天多云，21/7℃。", tool_calls=[]),
            ]
        )
        planner.client = fake_client

        def _executor(command_text: str):
            self.assertEqual(command_text, "/web_fetch https://weather.example.com/beijing")
            return (
                "执行完成",
                [
                    ToolEvent(
                        name="web_fetch",
                        ok=True,
                        summary="web page loaded",
                        payload={
                            "url": "https://weather.example.com/beijing",
                            "final_url": "https://weather.example.com/beijing",
                            "title": "北京天气预报",
                            "source_domain": "weather.example.com",
                            "text": "今天\n多云\n21/7℃\n<3级",
                            "line_count": 8,
                            "link_count": 2,
                            "source_scope": "main",
                        },
                    )
                ],
            )

        intent = planner.plan("北京天气怎么样", [], tool_executor=_executor)

        self.assertEqual(intent.assistant_text, "北京今天多云，21/7℃。")
        synthesis_messages = fake_client.chat.completions.requests[2]["messages"]
        self.assertIn("TOOL_RESULT_CONTEXT_JSON", synthesis_messages[1]["content"])
        self.assertIn("多云", synthesis_messages[1]["content"])
        self.assertIn("21/7℃", synthesis_messages[1]["content"])

    def test_glm_uses_native_web_search_tool_spec(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="glm-5",
                api_key="sk-test",
                provider_name="glm",
                planner_kind="openai_chat",
                base_url="https://open.bigmodel.cn/api/paas/v4",
                raw_model={
                    "supports_tools": True,
                    "supports_reasoning": True,
                },
            ),
            host_platform=host_platform,
        )
        fake_client = self._FakeDeepSeekClient([SimpleNamespace(content="北京今天多云。", tool_calls=[])])
        planner.client = fake_client

        intent = planner.plan("北京天气怎么样", [], tool_executor=lambda command_text: ("执行完成", []))

        self.assertEqual(intent.assistant_text, "北京今天多云。")
        request_tools = fake_client.chat.completions.requests[0]["tools"]
        self.assertTrue(any(tool.get("type") == "web_search" for tool in request_tools))
        self.assertFalse(
            any(
                tool.get("type") == "function"
                and ((tool.get("function") or {}).get("name") == "web_search")
                for tool in request_tools
            )
        )

    def test_glm_native_web_search_adds_inferred_activity_event(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="glm-5",
                api_key="sk-test",
                provider_name="glm",
                planner_kind="openai_chat",
                base_url="https://open.bigmodel.cn/api/paas/v4",
                raw_model={
                    "supports_tools": True,
                    "supports_reasoning": True,
                },
            ),
            host_platform=host_platform,
        )
        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="web_fetch", arguments='{"url":"https://weather.example.com/beijing"}'),
        )
        planner.client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="", tool_calls=[tool_call]),
                SimpleNamespace(content="北京今天多云。", tool_calls=[]),
            ]
        )

        def _executor(command_text: str):
            self.assertEqual(command_text, "/web_fetch https://weather.example.com/beijing")
            return (
                "执行完成",
                [
                    ToolEvent(
                        name="web_fetch",
                        ok=True,
                        summary="web page loaded",
                        payload={
                            "url": "https://weather.example.com/beijing",
                            "final_url": "https://weather.example.com/beijing",
                            "title": "北京天气预报",
                            "source_domain": "weather.example.com",
                            "text": "今天\n多云\n21/7℃\n<3级",
                        },
                    )
                ],
            )

        intent = planner.plan("北京天气怎么样", [], tool_executor=_executor)

        self.assertEqual(intent.assistant_text, "北京今天多云。")
        self.assertEqual(intent.activity_events[0].title, "Used native web search")
        self.assertEqual(intent.activity_events[0].kind, "web")
        self.assertIn("mode=inferred", intent.activity_events[0].detail)
        self.assertIn("path=web_fetch", intent.activity_events[0].detail)

    def test_deepseek_planner_skips_generic_synthesis_when_post_tool_answer_exists(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="web_fetch", arguments='{"url":"https://weather.example.com/beijing"}'),
        )
        fake_client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="", tool_calls=[tool_call]),
                SimpleNamespace(content="北京今天多云，21/7℃。", tool_calls=[]),
            ]
        )
        planner.client = fake_client

        def _executor(command_text: str):
            self.assertEqual(command_text, "/web_fetch https://weather.example.com/beijing")
            return (
                "执行完成",
                [
                    ToolEvent(
                        name="web_fetch",
                        ok=True,
                        summary="web page loaded",
                        payload={
                            "url": "https://weather.example.com/beijing",
                            "final_url": "https://weather.example.com/beijing",
                            "title": "北京天气预报",
                            "source_domain": "weather.example.com",
                            "text": "今天\n多云\n21/7℃\n<3级",
                        },
                    )
                ],
            )

        intent = planner.plan("北京天气怎么样", [], tool_executor=_executor)

        self.assertEqual(intent.assistant_text, "北京今天多云，21/7℃。")
        self.assertEqual(len(fake_client.chat.completions.requests), 2)
        self.assertEqual(intent.timings["synthesis_rounds"], 0)

    def test_deepseek_planner_records_phase_timings_and_tool_elapsed_ms(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="web_fetch", arguments='{"url":"https://weather.example.com/beijing"}'),
        )
        planner.client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="", tool_calls=[tool_call]),
                SimpleNamespace(content="北京今天多云，21/7℃。", tool_calls=[]),
            ]
        )

        def _executor(command_text: str):
            self.assertEqual(command_text, "/web_fetch https://weather.example.com/beijing")
            return (
                "执行完成",
                [
                    ToolEvent(
                        name="web_fetch",
                        ok=True,
                        summary="web page loaded",
                        payload={
                            "url": "https://weather.example.com/beijing",
                            "final_url": "https://weather.example.com/beijing",
                            "title": "北京天气预报",
                            "source_domain": "weather.example.com",
                            "text": "今天\n多云\n21/7℃\n<3级",
                        },
                    )
                ],
            )

        with patch("cli.agent_cli.providers.chat_completions_planner.time.perf_counter") as perf_counter:
            perf_counter.side_effect = [0.0, 1.0, 1.5, 2.0, 2.25, 2.75, 3.0, 4.0, 4.5, 5.0]
            intent = planner.plan("北京天气怎么样", [], tool_executor=_executor)

        self.assertEqual(intent.assistant_text, "北京今天多云，21/7℃。")
        self.assertGreaterEqual(intent.timings["initial_model_ms"], 0)
        self.assertGreaterEqual(intent.timings["tool_execution_ms"], 0)
        self.assertGreaterEqual(intent.timings["synthesis_model_ms"], 0)
        self.assertGreaterEqual(intent.timings["total_ms"], 0)
        self.assertGreaterEqual(intent.timings["planning_rounds"], 1)
        self.assertGreaterEqual(intent.timings["synthesis_rounds"], 0)
        self.assertTrue(isinstance(intent.timings["planning_trace"], list))
        self.assertTrue(isinstance(intent.timings["synthesis_trace"], list))
        self.assertIn("planner_elapsed_ms", intent.tool_events[0].payload)

    def test_deepseek_planner_parallelizes_parallel_safe_tool_calls_when_model_allows_it(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
                raw_model={
                    "supports_tools": True,
                    "supports_parallel_tool_calls": True,
                },
            ),
            host_platform=host_platform,
        )

        tool_calls = [
            SimpleNamespace(id="call-1", function=SimpleNamespace(name="file_read", arguments='{"path":"a.txt"}')),
            SimpleNamespace(id="call-2", function=SimpleNamespace(name="file_read", arguments='{"path":"b.txt"}')),
        ]
        planner.client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="", tool_calls=tool_calls),
                SimpleNamespace(content="", tool_calls=[]),
                SimpleNamespace(content="文件已读取。", tool_calls=[]),
            ]
        )

        active = 0
        max_active = 0
        lock = threading.Lock()

        def _executor(command_text: str):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            target = command_text.split()[1]
            return (
                "执行完成",
                [ToolEvent(name="file_read", ok=True, summary="file loaded", payload={"path": target, "text": target})],
            )

        intent = planner.plan("读取两个文件", [], tool_executor=_executor)

        self.assertEqual(intent.assistant_text, "文件已读取。")
        self.assertGreaterEqual(max_active, 2)

    def test_deepseek_planner_keeps_parallel_safe_tools_serial_when_model_disables_parallelism(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
                raw_model={
                    "supports_tools": True,
                    "supports_parallel_tool_calls": False,
                },
            ),
            host_platform=host_platform,
        )

        tool_calls = [
            SimpleNamespace(id="call-1", function=SimpleNamespace(name="file_read", arguments='{"path":"a.txt"}')),
            SimpleNamespace(id="call-2", function=SimpleNamespace(name="file_read", arguments='{"path":"b.txt"}')),
        ]
        planner.client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="", tool_calls=tool_calls),
                SimpleNamespace(content="", tool_calls=[]),
                SimpleNamespace(content="文件已读取。", tool_calls=[]),
            ]
        )

        active = 0
        max_active = 0
        lock = threading.Lock()

        def _executor(command_text: str):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            target = command_text.split()[1]
            return (
                "执行完成",
                [ToolEvent(name="file_read", ok=True, summary="file loaded", payload={"path": target, "text": target})],
            )

        intent = planner.plan("读取两个文件", [], tool_executor=_executor)

        self.assertEqual(intent.assistant_text, "文件已读取。")
        self.assertEqual(max_active, 1)

    def test_deepseek_planner_uses_structured_fallback_when_synthesis_still_returns_empty(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="shell", arguments='{"command":"ls -la"}'),
        )
        planner.client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="", tool_calls=[tool_call]),
                SimpleNamespace(content="", tool_calls=[]),
                SimpleNamespace(content="", tool_calls=[]),
            ]
        )

        def _executor(command_text: str):
            self.assertEqual(command_text, "/shell Get-ChildItem -Force")
            return (
                "执行完成",
                [ToolEvent(name="shell", ok=True, summary="shell rc=0", payload={"stdout": "a.txt\nb.txt\n"})],
            )

        intent = planner.plan("列出当前目录下的文件", [], tool_executor=_executor)

        self.assertEqual(intent.assistant_text, "模型未返回内容。")

    def test_policy_grounded_synthesis_prompt_contains_policy_evidence_json(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="policy_doc_search", arguments='{"query":"长期闲置 账号 权限"}'),
        )
        fake_client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="", tool_calls=[tool_call]),
                SimpleNamespace(content="", tool_calls=[]),
                SimpleNamespace(content="根据命中文档，需遵循最小授权和动态控制原则。", tool_calls=[]),
            ]
        )
        planner.client = fake_client

        def _executor(command_text: str):
            self.assertIn("/policy_doc_search", command_text)
            return (
                "执行完成",
                [
                    ToolEvent(
                        name="policy_doc_search",
                        ok=True,
                        summary="policy matches=2",
                        payload={
                            "ok": True,
                            "count": 2,
                            "documents": [
                                {
                                    "doc_id": "doc-1",
                                    "title": "中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）",
                                    "excerpt": "管理原则包括最小授权原则、动态控制原则。",
                                    "score": 0.98,
                                },
                                {
                                    "doc_id": "doc-2",
                                    "title": "中国邮政储蓄银行运维安全堡垒系统管理规程（2024年修订版）",
                                    "excerpt": "确需访问生产系统才可申请账号，不再需要时应申请注销或调整。",
                                    "score": 0.97,
                                },
                            ],
                        },
                    )
                ],
            )

        intent = planner.plan("长期闲置账号的制度依据是什么？", [], tool_executor=_executor)

        self.assertIn("最小授权", intent.assistant_text)
        synthesis_messages = fake_client.chat.completions.requests[2]["messages"]
        self.assertIn("POLICY_EVIDENCE_JSON", synthesis_messages[1]["content"])
        self.assertIn("POLICY_EVIDENCE_PROFILE_JSON", synthesis_messages[1]["content"])
        self.assertIn("POLICY_ANSWER_RULES", synthesis_messages[1]["content"])

    def test_policy_question_user_message_contains_policy_qa_hint(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )
        planner.client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="未找到直接依据。", tool_calls=[]),
            ]
        )

        planner.plan("长期闲置账号的制度依据是什么？", [])

        first_request = planner.client.chat.completions.requests[0]
        user_messages = [message for message in first_request["messages"] if message.get("role") == "user"]
        self.assertTrue(user_messages)
        self.assertIn("POLICY_QA_HINT", user_messages[-1]["content"])
        self.assertIn("policy_doc_search", user_messages[-1]["content"])
        self.assertIn("policy_doc_read", user_messages[-1]["content"])
        self.assertIn("Use policy_doc_search first with 2 to 4 short queries", user_messages[-1]["content"])

    def test_policy_query_plan_generates_multiple_short_queries(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        queries = planner._policy_query_plan(
            "邮政储蓄银行核心业务应用运维管控系统存在30名用户并非按需申请、长期闲置，制度依据是什么？"
        )

        self.assertGreaterEqual(len(queries), 2)
        self.assertLessEqual(len(queries), 4)
        self.assertEqual(len(queries), len(set(queries)))
        self.assertTrue(all(len(query) < 40 for query in queries))

    def test_policy_query_plan_compacts_audit_finding(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        queries = planner._policy_query_plan(
            "经查，你中心部分外包服务提供商尽职调查执行不到位，未见外包服务提供商信息安全管理能力、财务状况、资质能力等尽职调查记录，请说明制度依据。"
        )

        self.assertIn("外包服务提供商 尽职调查", queries)
        self.assertTrue(all("经查" not in query for query in queries))
        self.assertTrue(all("请说明" not in query for query in queries))

    def test_reasoner_policy_query_plan_can_use_llm_rewrite(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-reasoner",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_reasoner",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )
        planner.client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(
                    content=json.dumps(
                        {
                            "queries": [
                                "外包服务提供商 尽职调查",
                                "尽职调查 财务情况 风险管理",
                            ],
                            "issue_labels": ["外包服务提供商尽职调查执行不到位"],
                            "must_terms": ["尽职调查", "外包服务提供商", "财务情况"],
                            "role_terms": ["外包执行部门"],
                        },
                        ensure_ascii=False,
                    ),
                    tool_calls=[],
                )
            ]
        )

        queries = planner._policy_query_plan(
            "经查，你中心部分外包服务提供商尽职调查执行不到位，未见外包服务提供商信息安全管理能力、财务状况、资质能力等尽职调查记录，请说明制度依据。"
        )

        self.assertIn("外包服务提供商 尽职调查", queries)
        self.assertIn("尽职调查 财务情况 风险管理", queries)

    def test_policy_query_terms_split_long_chinese_clause(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        terms = planner._policy_query_terms("账号权限管理至少多久开展一次审计核查")

        self.assertIn("审计核查", terms)
        self.assertIn("账号权限", terms)

    def test_policy_query_plan_heuristics_preserve_audit_scenario_subject(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        queries = planner._policy_query_plan("针对外包服务提供商尽职调查不到位的问题，请给出制度依据、问题定性和责任环节。")

        self.assertIn("外包服务提供商 尽职调查", queries)
        self.assertTrue(all("问题定性和责任环节" not in query for query in queries))

    def test_policy_turn_filters_out_non_policy_history(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        messages = planner._chat_messages(
            "账号权限管理至少多久开展一次审计核查，制度依据是什么？",
            [
                {"role": "user", "content": "请帮我读取群聊最近消息并草拟回复"},
                {"role": "assistant", "content": "执行链: read_recent_messages -> summarize_conversation -> draft_reply"},
                {"role": "user", "content": "制度依据是什么？"},
                {"role": "assistant", "content": "主依据\n《中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）》[E1]"},
            ],
        )

        serialized = "\n".join(str(item.get("content") or "") for item in messages)
        self.assertNotIn("草拟回复", serialized)
        self.assertNotIn("read_recent_messages", serialized)
        self.assertIn("主依据", serialized)
        self.assertIn("制度依据是什么", serialized)

    def test_policy_targeted_snippet_prefers_query_hit_over_title_hit(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        snippet = planner._policy_targeted_snippet_v2(
            {
                "title": "中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）",
                "source_queries": ["账号 权限 审计核查 至少多久"],
                "matched_terms": ["审计核查", "账号权限"],
                "text": (
                    "# 中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）\n"
                    "总则：为规范信息系统用户账号和权限管理。\n"
                    "账号权限管理单位应指定专人至少每6个月对本单位所负责管理账号和权限管理情况进行审计核查，并保留相关工作记录。\n"
                ),
            },
            limit=180,
        )

        self.assertIn("至少每6个月", snippet)
        self.assertIn("审计核查", snippet)

    def test_policy_targeted_snippet_uses_user_question_focus_for_time_requirement(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        snippet = planner._policy_targeted_snippet_v2(
            {
                "title": "中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）",
                "source_queries": ["账号 权限 审计 核查"],
                "matched_terms": ["权限管理", "审计核查", "账号权限"],
                "text": (
                    "信息系统使用单位主要职责：负责本单位使用的信息系统业务有关用户管理、账号管理和口令管理，"
                    "配合账号权限管理单位做好权限管理、审批授权、审计核查等工作。\n"
                    "账号权限管理单位应指定专人至少每6个月对本单位所负责管理账号和权限管理情况进行审计核查，并保留相关工作记录。\n"
                    "审核责任人应对用户账号使用和权限设置情况进行定期审核。"
                ),
            },
            user_text="账号权限管理至少多久开展一次审计核查，制度依据是什么？",
            limit=220,
        )

        self.assertIn("至少每6个月", snippet)
        self.assertIn("审计核查", snippet)

    def test_policy_effective_evidence_sets_priority_excerpt_for_time_requirement(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        blocks = planner._policy_effective_evidence_v2(
            "账号权限管理至少多久开展一次审计核查，制度依据是什么？",
            [
                {
                    "doc_id": "doc-1",
                    "title": "中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）",
                    "doc_kind": "governance_policy",
                    "doc_group": "governance_base",
                    "authority_rank": 100,
                    "source_tools": ["policy_doc_read"],
                    "source_queries": ["账号 权限 审计 核查"],
                    "score": 0.99,
                    "text": (
                        "总则：为规范中国邮政储蓄银行信息系统用户账号和权限管理。\n"
                        "信息系统使用单位主要职责：负责本单位使用的信息系统业务有关用户管理、账号管理和口令管理，"
                        "配合账号权限管理单位做好权限管理、审批授权、审计核查等工作。\n"
                        "账号权限管理单位应指定专人至少每6个月对本单位所负责管理账号和权限管理情况进行审计核查，并保留相关工作记录。\n"
                        "审核责任人应对用户账号使用和权限设置情况进行定期审核。"
                    ),
                }
            ],
        )

        self.assertEqual(len(blocks), 1)
        self.assertIn("至少每6个月", blocks[0]["priority_excerpt"])

    def test_policy_evidence_blocks_keep_read_text_needed_for_late_answer_clause(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )
        filler = "总则说明。" * 900
        late_clause = "账号权限管理单位应指定专人至少每6个月对本单位所负责管理账号和权限管理情况进行审计核查，并保留相关工作记录。"
        events = [
            ToolEvent(
                name="policy_doc_search",
                ok=True,
                summary="policy matches=1",
                payload={
                    "ok": True,
                    "query": "账号 权限 审计 核查",
                    "count": 1,
                    "documents": [
                        {
                            "doc_id": "doc-1",
                            "title": "中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）",
                            "doc_kind": "governance_policy",
                            "doc_group": "governance_base",
                            "authority_rank": 100,
                            "excerpt": "账号权限管理单位应指定专人至少每6个月对本单位所负责管理账号和权限管理情况进行审计核查。",
                            "score": 0.99,
                        }
                    ],
                },
            ),
            ToolEvent(
                name="policy_doc_read",
                ok=True,
                summary="policy markdown loaded",
                payload={
                    "ok": True,
                    "char_count": len(filler) + len(late_clause),
                    "document": {
                        "doc_id": "doc-1",
                        "title": "中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）",
                        "doc_kind": "governance_policy",
                        "doc_group": "governance_base",
                        "authority_rank": 100,
                    },
                    "text": filler + late_clause,
                },
            ),
        ]

        blocks = planner._policy_effective_evidence_v2(
            "账号权限管理至少多久开展一次审计核查，制度依据是什么？",
            planner._policy_evidence_blocks(events),
        )

        self.assertEqual(len(blocks), 1)
        self.assertIn("至少每6个月", blocks[0]["priority_excerpt"])

    def test_policy_grounded_fallback_covers_governance_and_direct_documents(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="policy_doc_search", arguments='{"query":"权限管理 长期闲置"}'),
        )
        fake_client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="", tool_calls=[tool_call]),
                SimpleNamespace(content="主要依据是《中国邮政储蓄银行运维安全堡垒系统管理规程（2024年修订版）》。", tool_calls=[]),
                SimpleNamespace(content="", tool_calls=[]),
            ]
        )
        planner.client = fake_client

        def _executor(command_text: str):
            self.assertIn("/policy_doc_search", command_text)
            return (
                "执行完成",
                [
                    ToolEvent(
                        name="policy_doc_search",
                        ok=True,
                        summary="policy matches=3",
                        payload={
                            "ok": True,
                            "count": 3,
                            "documents": [
                                {
                                    "doc_id": "doc-1",
                                    "title": "中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）",
                                    "excerpt": "最小授权原则、动态控制原则，长期未登录账号最长为一年应锁定或限制访问。",
                                    "score": 0.99,
                                },
                                {
                                    "doc_id": "doc-2",
                                    "title": "中国邮政储蓄银行运维安全堡垒系统管理规程（2024年修订版）",
                                    "excerpt": "工作中确需访问生产系统方可申请账号，长期未登录最长90天自动锁定。",
                                    "score": 0.98,
                                },
                                {
                                    "doc_id": "doc-3",
                                    "title": "2025年信用卡核心系统审计底稿-权限问题反馈",
                                    "excerpt": "审计发现存在长期闲置账号。",
                                    "score": 0.97,
                                },
                            ],
                        },
                    )
                ],
            )

        intent = planner.plan("说明长期闲置账号的制度依据。", [], tool_executor=_executor)

        self.assertIn("上位制度依据", intent.assistant_text)
        self.assertIn("直接适用制度", intent.assistant_text)
        self.assertIn("中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）", intent.assistant_text)
        self.assertIn("中国邮政储蓄银行运维安全堡垒系统管理规程（2024年修订版）", intent.assistant_text)
        self.assertNotIn("2025年信用卡核心系统审计底稿-权限问题反馈", intent.assistant_text)
        self.assertIn("未完整覆盖高权威证据分层", intent.assistant_text)

    def test_policy_grounded_effective_evidence_excludes_noise_documents(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="policy_doc_search", arguments='{"query":"长期闲置账号 权限管理"}'),
        )
        fake_client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="", tool_calls=[tool_call]),
                SimpleNamespace(content="主要依据是2025年信用卡核心系统审计底稿-权限问题反馈。", tool_calls=[]),
                SimpleNamespace(content="", tool_calls=[]),
            ]
        )
        planner.client = fake_client

        def _executor(command_text: str):
            self.assertIn("/policy_doc_search", command_text)
            return (
                "执行完成",
                [
                    ToolEvent(
                        name="policy_doc_search",
                        ok=True,
                        summary="policy matches=4",
                        payload={
                            "ok": True,
                            "count": 4,
                            "documents": [
                                {
                                    "doc_id": "doc-1",
                                    "title": "中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）",
                                    "doc_kind": "governance_policy",
                                    "doc_group": "governance_base",
                                    "authority_rank": 100,
                                    "evidence_summary": "最小授权原则、动态控制原则，长期未登录账号应锁定或限制访问。",
                                    "matched_terms": ["长期闲置账号", "权限管理"],
                                    "query_term_hits": 2,
                                    "score": 0.99,
                                },
                                {
                                    "doc_id": "doc-2",
                                    "title": "中国邮政储蓄银行运维安全堡垒系统管理规程（2024年修订版）",
                                    "doc_kind": "specialized_policy",
                                    "doc_group": "direct_rule",
                                    "authority_rank": 90,
                                    "evidence_summary": "确需访问生产系统才可申请账号，不再需要时应申请注销或调整。",
                                    "matched_terms": ["账号", "申请"],
                                    "query_term_hits": 2,
                                    "score": 0.98,
                                },
                                {
                                    "doc_id": "doc-3",
                                    "title": "2025年信用卡核心系统审计底稿-权限问题反馈",
                                    "doc_kind": "audit_workpaper",
                                    "doc_group": "supporting_reference",
                                    "authority_rank": 10,
                                    "is_noise_candidate": True,
                                    "evidence_summary": "审计发现存在长期闲置账号。",
                                    "matched_terms": ["长期闲置账号"],
                                    "query_term_hits": 1,
                                    "score": 0.97,
                                },
                                {
                                    "doc_id": "doc-4",
                                    "title": "QPSBC 0124.6-2024中国邮政储蓄银行云计算运行管理标准 第6部分：云原生应用运行管理",
                                    "doc_kind": "specialized_policy",
                                    "doc_group": "direct_rule",
                                    "authority_rank": 90,
                                    "evidence_summary": "本标准适用于云原生应用运行管理。",
                                    "matched_terms": [],
                                    "query_term_hits": 0,
                                    "score": 0.30,
                                },
                            ],
                        },
                    )
                ],
            )

        intent = planner.plan("说明长期闲置账号的制度依据。", [], tool_executor=_executor)

        self.assertIn("上位制度依据", intent.assistant_text)
        self.assertIn("直接适用制度", intent.assistant_text)
        self.assertIn("中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）", intent.assistant_text)
        self.assertIn("中国邮政储蓄银行运维安全堡垒系统管理规程（2024年修订版）", intent.assistant_text)
        self.assertNotIn("2025年信用卡核心系统审计底稿-权限问题反馈", intent.assistant_text)
        self.assertNotIn("云计算运行管理标准", intent.assistant_text)

    def test_policy_grounded_synthesis_blocks_unsupported_article_numbers(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="policy_doc_read", arguments='{"doc_id":"doc-2","max_chars":6000}'),
        )
        fake_client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="", tool_calls=[tool_call]),
                SimpleNamespace(content="", tool_calls=[]),
                SimpleNamespace(
                    content="依据《信息系统用户权限管理办法》第十七条，180天未使用应暂停账户。",
                    tool_calls=[],
                ),
            ]
        )
        planner.client = fake_client

        def _executor(command_text: str):
            if command_text.startswith("/policy_doc_search"):
                return (
                    "执行完成",
                    [
                        ToolEvent(
                            name="policy_doc_search",
                            ok=True,
                            summary="policy matches=1",
                            payload={
                                "ok": True,
                                "count": 1,
                                "documents": [
                                    {
                                        "doc_id": "doc-2",
                                        "title": "中国邮政储蓄银行运维安全堡垒系统管理规程（2024年修订版）",
                                        "doc_kind": "specialized_policy",
                                        "doc_group": "direct_rule",
                                        "authority_rank": 90,
                                        "excerpt": "第十四条 至少每季度一次核查账号权限。",
                                        "score": 0.97,
                                    }
                                ],
                            },
                        )
                    ],
                )
            self.assertIn("/policy_doc_read", command_text)
            return (
                "执行完成",
                [
                    ToolEvent(
                        name="policy_doc_read",
                        ok=True,
                        summary="policy markdown loaded",
                        payload={
                            "ok": True,
                            "char_count": 160,
                            "document": {
                                "doc_id": "doc-2",
                                "title": "中国邮政储蓄银行运维安全堡垒系统管理规程（2024年修订版）",
                                "doc_kind": "specialized_policy",
                                "doc_group": "direct_rule",
                                "authority_rank": 90,
                            },
                            "text": (
                                "第三条 谁申请谁负责、谁使用谁负责。"
                                "第十二条 确需访问生产系统才可申请账号。"
                                "第十三条 不再需要时应申请注销或调整。"
                                "第十四条 至少每季度一次核查账号权限。"
                            ),
                        },
                    )
                ],
            )

        intent = planner.plan("长期闲置账号的制度依据是什么？", [], tool_executor=_executor)

        self.assertIn("直接适用制度", intent.assistant_text)
        self.assertIn("中国邮政储蓄银行运维安全堡垒系统管理规程", intent.assistant_text)
        self.assertIn("《信息系统用户权限管理办法》", intent.assistant_text)
        self.assertIn("180天", intent.assistant_text)
        self.assertIn("未能从命中文档中确认", intent.assistant_text)

    def test_policy_grounded_direct_final_answer_is_also_validated(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="policy_doc_search", arguments='{"query":"闲置账号 最小授权"}'),
        )
        fake_client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="", tool_calls=[tool_call]),
                SimpleNamespace(content="依据《信息系统用户权限管理办法》第十七条，180天未使用应暂停账户。", tool_calls=[]),
                SimpleNamespace(content="", tool_calls=[]),
            ]
        )
        planner.client = fake_client

        def _executor(command_text: str):
            self.assertIn("/policy_doc_search", command_text)
            return (
                "执行完成",
                [
                    ToolEvent(
                        name="policy_doc_search",
                        ok=True,
                        summary="policy matches=1",
                        payload={
                            "ok": True,
                            "count": 1,
                            "documents": [
                                {
                                    "doc_id": "doc-1",
                                    "title": "中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）",
                                    "excerpt": "管理原则包括最小授权原则、动态控制原则。",
                                    "score": 0.98,
                                }
                            ],
                        },
                    )
                ],
            )

        intent = planner.plan("长期闲置账号的制度依据是什么？", [], tool_executor=_executor)

        self.assertIn("上位制度依据", intent.assistant_text)
        self.assertIn("信息系统用户账号和权限管理实施细则", intent.assistant_text)
        self.assertIn("180天", intent.assistant_text)
        self.assertEqual(len(fake_client.chat.completions.requests), 3)

    def test_policy_grounded_zero_evidence_does_not_allow_freeform_answer(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="policy_doc_search", arguments='{"query":"账号闲置 长期未使用"}'),
        )
        planner.client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="", tool_calls=[tool_call]),
                SimpleNamespace(content="依据《应用系统用户账号和权限管理实施细则》第八条，连续90天未登录视为闲置。", tool_calls=[]),
            ]
        )

        def _executor(command_text: str):
            self.assertIn("/policy_doc_search", command_text)
            return (
                "执行完成",
                [
                    ToolEvent(
                        name="policy_doc_search",
                        ok=True,
                        summary="policy matches=0",
                        payload={"ok": True, "count": 0, "documents": []},
                    )
                ],
            )

        intent = planner.plan("说明长期闲置账号的制度依据。", [], tool_executor=_executor)

        self.assertIn("未找到可直接支撑结论的制度证据", intent.assistant_text)
        self.assertIn("policy matches=0", intent.assistant_text)
        self.assertNotIn("第八条", intent.assistant_text)

    def test_policy_question_preflight_runs_search_and_read_before_synthesis(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )
        fake_client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(
                    content=(
                        "结论：应以 [E1] 中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）"
                        " 作为主要依据。"
                    ),
                    tool_calls=[],
                ),
            ]
        )
        planner.client = fake_client
        commands: list[str] = []

        def _executor(command_text: str):
            commands.append(command_text)
            if command_text.startswith("/policy_doc_search"):
                return (
                    "执行完成",
                    [
                        ToolEvent(
                            name="policy_doc_search",
                            ok=True,
                            summary="policy matches=1",
                            payload={
                                "ok": True,
                                "query": command_text,
                                "count": 1,
                                "documents": [
                                    {
                                        "doc_id": "doc-1",
                                        "title": "中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）",
                                        "doc_kind": "governance_policy",
                                        "doc_group": "governance_base",
                                        "authority_rank": 100,
                                        "excerpt": "人员岗位发生变化时，应及时调整其账号和权限，避免出现多余账号、多余权限。",
                                        "score": 0.99,
                                    }
                                ],
                            },
                        )
                    ],
                )
            if command_text.startswith("/policy_doc_read"):
                return (
                    "执行完成",
                    [
                        ToolEvent(
                            name="policy_doc_read",
                            ok=True,
                            summary="policy markdown loaded",
                            payload={
                                "ok": True,
                                "char_count": 120,
                                "document": {
                                    "doc_id": "doc-1",
                                    "title": "中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）",
                                    "doc_kind": "governance_policy",
                                    "doc_group": "governance_base",
                                    "authority_rank": 100,
                                },
                                "text": "信息系统应监测长期未登录账号并进行锁定或限制访问，收回其权限。",
                            },
                        )
                    ],
                )
            self.fail(f"unexpected command: {command_text}")

        intent = planner.plan(
            "邮政储蓄银行核心业务应用运维管控系统存在长期闲置账号，制度依据是什么？",
            [],
            tool_executor=_executor,
        )

        self.assertTrue(any(command.startswith("/policy_doc_search") for command in commands))
        self.assertTrue(any(command.startswith("/policy_doc_read") for command in commands))
        self.assertIn("[E1]", intent.assistant_text)
        self.assertIn("中国邮政储蓄银行信息系统用户账号和权限管理实施细则", intent.assistant_text)
        self.assertEqual(len(fake_client.chat.completions.requests), 1)
        self.assertEqual(
            [event.title for event in intent.activity_events],
            [
                "Planned policy queries",
                "Retrieved policy evidence",
                "Bound evidence answer",
                "Verified policy answer",
            ],
        )

    def test_policy_summary_question_uses_local_fast_answer_without_model_roundtrip(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )
        fake_client = self._FakeDeepSeekClient([])
        planner.client = fake_client
        commands: list[str] = []

        def _executor(command_text: str):
            commands.append(command_text)
            if command_text.startswith("/policy_doc_search"):
                return (
                    "执行完成",
                    [
                        ToolEvent(
                            name="policy_doc_search",
                            ok=True,
                            summary="policy matches=1",
                            payload={
                                "ok": True,
                                "query": command_text,
                                "count": 1,
                                "documents": [
                                    {
                                        "doc_id": "doc-1",
                                        "title": "中国邮政储蓄银行数据安全管理办法（2026年修订版）",
                                        "doc_kind": "governance_policy",
                                        "doc_group": "governance_base",
                                        "authority_rank": 100,
                                        "excerpt": "加强数据安全管理并促进开发利用。",
                                        "score": 0.99,
                                    }
                                ],
                            },
                        )
                    ],
                )
            if command_text.startswith("/policy_doc_read"):
                return (
                    "执行完成",
                    [
                        ToolEvent(
                            name="policy_doc_read",
                            ok=True,
                            summary="policy markdown loaded",
                            payload={
                                "ok": True,
                                "char_count": 300,
                                "document": {
                                    "doc_id": "doc-1",
                                    "title": "中国邮政储蓄银行数据安全管理办法（2026年修订版）",
                                    "doc_kind": "governance_policy",
                                    "doc_group": "governance_base",
                                    "authority_rank": 100,
                                },
                                "text": (
                                    "# 第一章 总则\n"
                                    "为规范中国邮政储蓄银行数据处理活动，加强数据安全管理并促进开发利用，制定本办法。\n"
                                    "# 第二章 职责分工\n"
                                    "# 第三章 数据分类分级\n"
                                    "# 第四章 数据安全管理\n"
                                ),
                            },
                        )
                    ],
                )
            self.fail(f"unexpected command: {command_text}")

        intent = planner.plan("数据安全管理办法内容是什么", [], tool_executor=_executor)

        self.assertEqual(len(fake_client.chat.completions.requests), 0)
        self.assertEqual(len([command for command in commands if command.startswith("/policy_doc_search")]), 1)
        self.assertEqual(len([command for command in commands if command.startswith("/policy_doc_read")]), 1)
        self.assertIn("《中国邮政储蓄银行数据安全管理办法（2026年修订版）》主要内容可以概括为：", intent.assistant_text)
        self.assertIn("为规范中国邮政储蓄银行数据处理活动，加强数据安全管理并促进开发利用，制定本办法。", intent.assistant_text)
        self.assertIn("核心章节包括：", intent.assistant_text)
        self.assertIn("第一章 总则", intent.assistant_text)
        self.assertNotIn("目 录", intent.assistant_text)
        self.assertNotIn("# 中国邮政储蓄银行数据安全管理办法", intent.assistant_text)

    def test_policy_grounded_fallback_uses_evidence_ids(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="policy_doc_search", arguments='{"query":"长期闲置 账号 权限"}'),
        )
        fake_client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="", tool_calls=[tool_call]),
                SimpleNamespace(content="依据《应用系统用户账号和权限管理办法》第八条，90天未登录即视为闲置。", tool_calls=[]),
                SimpleNamespace(content="", tool_calls=[]),
            ]
        )
        planner.client = fake_client

        def _executor(command_text: str):
            if command_text.startswith("/policy_doc_search"):
                return (
                    "执行完成",
                    [
                        ToolEvent(
                            name="policy_doc_search",
                            ok=True,
                            summary="policy matches=2",
                            payload={
                                "ok": True,
                                "query": command_text,
                                "count": 2,
                                "documents": [
                                    {
                                        "doc_id": "doc-1",
                                        "title": "中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）",
                                        "doc_kind": "governance_policy",
                                        "doc_group": "governance_base",
                                        "authority_rank": 100,
                                        "excerpt": "信息系统应监测长期未登录账号并进行锁定或限制访问，收回其权限。",
                                        "score": 0.99,
                                    },
                                    {
                                        "doc_id": "doc-2",
                                        "title": "中国邮政储蓄银行运维安全堡垒系统管理规程（2024年修订版）",
                                        "doc_kind": "specialized_policy",
                                        "doc_group": "direct_rule",
                                        "authority_rank": 90,
                                        "excerpt": "工作中确需访问生产系统方可申请账号，不再需要时应注销或调整。",
                                        "score": 0.98,
                                    },
                                ],
                            },
                        )
                    ],
                )
            if command_text.startswith("/policy_doc_read"):
                if "--doc-id doc-1" in command_text:
                    return (
                        "执行完成",
                        [
                            ToolEvent(
                                name="policy_doc_read",
                                ok=True,
                                summary="policy markdown loaded",
                                payload={
                                    "ok": True,
                                    "char_count": 120,
                                    "document": {
                                        "doc_id": "doc-1",
                                        "title": "中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）",
                                        "doc_kind": "governance_policy",
                                        "doc_group": "governance_base",
                                        "authority_rank": 100,
                                    },
                                    "text": "信息系统应监测长期未登录账号并进行锁定或限制访问，收回其权限。",
                                },
                            )
                        ],
                    )
                if "--doc-id doc-2" in command_text:
                    return (
                        "执行完成",
                        [
                            ToolEvent(
                                name="policy_doc_read",
                                ok=True,
                                summary="policy markdown loaded",
                                payload={
                                    "ok": True,
                                    "char_count": 120,
                                    "document": {
                                        "doc_id": "doc-2",
                                        "title": "中国邮政储蓄银行运维安全堡垒系统管理规程（2024年修订版）",
                                        "doc_kind": "specialized_policy",
                                        "doc_group": "direct_rule",
                                        "authority_rank": 90,
                                    },
                                    "text": "工作中确需访问生产系统方可申请账号，不再需要时应注销或调整。",
                                },
                            )
                        ],
                    )
            self.fail(f"unexpected command: {command_text}")

        intent = planner.plan("说明长期闲置账号的制度依据。", [], tool_executor=_executor)

        self.assertIn("[E1]", intent.assistant_text)
        self.assertIn("[E2]", intent.assistant_text)
        self.assertIn("中国邮政储蓄银行信息系统用户账号和权限管理实施细则", intent.assistant_text)
        self.assertIn("中国邮政储蓄银行运维安全堡垒系统管理规程", intent.assistant_text)

    def test_policy_frequency_contradiction_forces_grounded_fallback(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )
        fake_client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="未找到直接依据规定账号权限管理审计核查的具体频次。", tool_calls=[]),
                SimpleNamespace(content="未找到直接依据规定账号权限管理审计核查的具体频次。", tool_calls=[]),
            ]
        )
        planner.client = fake_client

        def _executor(command_text: str):
            if command_text.startswith("/policy_doc_search"):
                return (
                    "执行完成",
                    [
                        ToolEvent(
                            name="policy_doc_search",
                            ok=True,
                            summary="policy matches=1",
                            payload={
                                "ok": True,
                                "query": command_text,
                                "count": 1,
                                "documents": [
                                    {
                                        "doc_id": "doc-1",
                                        "title": "中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）",
                                        "doc_kind": "governance_policy",
                                        "doc_group": "governance_base",
                                        "authority_rank": 100,
                                        "excerpt": "账号权限管理单位应指定专人至少每6个月对本单位所负责管理账号和权限管理情况进行审计核查。",
                                        "score": 0.99,
                                    }
                                ],
                            },
                        )
                    ],
                )
            if command_text.startswith("/policy_doc_read"):
                return (
                    "执行完成",
                    [
                        ToolEvent(
                            name="policy_doc_read",
                            ok=True,
                            summary="policy markdown loaded",
                            payload={
                                "ok": True,
                                "char_count": 180,
                                "document": {
                                    "doc_id": "doc-1",
                                    "title": "中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）",
                                    "doc_kind": "governance_policy",
                                    "doc_group": "governance_base",
                                    "authority_rank": 100,
                                },
                                "text": "账号权限管理单位应指定专人至少每6个月对本单位所负责管理账号和权限管理情况进行审计核查，并保留相关工作记录。",
                            },
                        )
                    ],
                )
            self.fail(f"unexpected command: {command_text}")

        intent = planner.plan("账号权限管理至少多久开展一次审计核查，制度依据是什么？", [], tool_executor=_executor)

        self.assertIn("至少每6个月", intent.assistant_text)
        self.assertIn("[E1]", intent.assistant_text)
        self.assertIn("contradiction:time_requirement", intent.activity_events[-1].detail)

    def test_policy_synthesis_messages_include_answer_focus_hints(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )
        executed_events = [
            ToolEvent(
                name="policy_doc_search",
                ok=True,
                summary="policy matches=1",
                payload={
                    "ok": True,
                    "query": "账号 权限 审计 核查",
                    "count": 1,
                    "documents": [
                        {
                            "doc_id": "doc-1",
                            "title": "中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）",
                            "doc_kind": "governance_policy",
                            "doc_group": "governance_base",
                            "authority_rank": 100,
                            "excerpt": "账号权限管理单位应指定专人至少每6个月对本单位所负责管理账号和权限管理情况进行审计核查。",
                            "score": 0.99,
                        }
                    ],
                },
            ),
            ToolEvent(
                name="policy_doc_read",
                ok=True,
                summary="policy markdown loaded",
                payload={
                    "ok": True,
                    "char_count": 180,
                    "document": {
                        "doc_id": "doc-1",
                        "title": "中国邮政储蓄银行信息系统用户账号和权限管理实施细则（2024年修订版）",
                        "doc_kind": "governance_policy",
                        "doc_group": "governance_base",
                        "authority_rank": 100,
                    },
                    "text": "账号权限管理单位应指定专人至少每6个月对本单位所负责管理账号和权限管理情况进行审计核查，并保留相关工作记录。",
                },
            ),
        ]

        messages = planner._synthesis_messages(
            user_text="账号权限管理至少多久开展一次审计核查，制度依据是什么？",
            executed_events=executed_events,
        )

        self.assertEqual(len(messages), 2)
        self.assertIn("POLICY_ANSWER_FOCUS_JSON", messages[1]["content"])
        self.assertIn("至少每6个月", messages[1]["content"])

    def test_reasoner_policy_rerank_demotes_irrelevant_punishment_doc(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-reasoner",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_reasoner",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )
        planner.client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(
                    content=json.dumps(
                        {
                            "issue_label": "访问凭证借用或混用控制不到位",
                            "focus_terms": ["UKey", "借予他人使用", "堡垒用户"],
                            "ranked": [
                                {"index": 1, "basis_type": "noise", "relevance": 8, "reason": "处罚结果，不是制度控制依据"},
                                {"index": 2, "basis_type": "primary_basis", "relevance": 95, "reason": "直接规定UKey不得借予他人使用"},
                            ],
                        },
                        ensure_ascii=False,
                    ),
                    tool_calls=[],
                )
            ]
        )

        evidence_blocks = [
            {
                "doc_id": "doc-penalty",
                "title": "中国邮政储蓄银行员工违规行为处理办法（2022年修订版）",
                "doc_group": "governance_base",
                "doc_kind": "governance_policy",
                "authority_rank": 100,
                "excerpt": "应给予批评教育、处分或其他处理。",
                "query_term_hits": 1,
                "source_tools": ["policy_doc_search"],
            },
            {
                "doc_id": "doc-ukey",
                "title": "中国邮政储蓄银行运维安全堡垒系统管理规程（2024年修订版）",
                "doc_group": "direct_rule",
                "doc_kind": "specialized_policy",
                "authority_rank": 90,
                "excerpt": "严禁随意使用他人UKey登录运维安全堡垒系统，严禁UKey混用、乱用。",
                "query_term_hits": 3,
                "source_tools": ["policy_doc_search", "policy_doc_read"],
                "text": "第十六条 严禁随意使用他人UKey登录运维安全堡垒系统，严禁UKey混用、乱用。",
            },
        ]

        selected = planner._policy_effective_evidence_v2(
            "针对外包人员出借UKey给他人使用的问题，请给出制度依据、问题定性和责任环节。",
            evidence_blocks,
        )

        self.assertTrue(selected)
        self.assertIn("运维安全堡垒系统管理规程", selected[0]["title"])
        self.assertEqual(selected[0]["llm_basis_type"], "primary_basis")

    def test_reasoner_synthesis_messages_include_policy_extraction_json(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-reasoner",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_reasoner",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )
        planner.client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(
                    content=json.dumps(
                        {
                            "issue_label": "最小授权控制不到位",
                            "conclusion_points": ["权限配置应遵循最小授权原则。"],
                            "obligations": ["根据工作职责授予最小权限。"],
                            "prohibitions": [],
                            "responsibility_roles": ["责任部门", "运营数据中心"],
                            "time_requirements": [],
                            "missing_evidence": [],
                        },
                        ensure_ascii=False,
                    ),
                    tool_calls=[],
                )
            ]
        )
        executed_events = [
            ToolEvent(
                name="policy_doc_read",
                ok=True,
                summary="policy markdown loaded",
                payload={
                    "document": {
                        "doc_id": "doc-1",
                        "title": "中国邮政储蓄银行运维安全堡垒系统管理规程（2024年修订版）",
                        "doc_kind": "specialized_policy",
                        "doc_group": "direct_rule",
                        "authority_rank": 90,
                    },
                    "text": "最小授权原则。根据工作职责，授予用户账号完成工作所需最小权限。",
                },
            ),
        ]

        messages = planner._synthesis_messages(
            user_text="针对外包人员权限与职责不匹配的问题，请给出制度依据。",
            executed_events=executed_events,
        )

        self.assertEqual(len(messages), 2)
        self.assertIn("POLICY_EXTRACTION_JSON", messages[1]["content"])
        self.assertIn("最小授权控制不到位", messages[1]["content"])

    def test_deepseek_reasoner_replays_reasoning_only_inside_current_turn(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="deepseek-reasoner",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_reasoner",
                base_url="https://api.deepseek.com",
            ),
            host_platform=host_platform,
        )

        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="shell", arguments='{"command":"python --version"}'),
        )
        fake_client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="", reasoning_content="first reasoning", tool_calls=[tool_call]),
                SimpleNamespace(content="当前 Python 版本是 3.11.9。", reasoning_content="second reasoning", tool_calls=[]),
            ]
        )
        planner.client = fake_client

        def _executor(command_text: str):
            self.assertEqual(command_text, "/exec_command 'python --version'")
            return (
                "执行完成",
                [
                    ToolEvent(
                        name="shell",
                        ok=True,
                        summary="shell rc=0",
                        payload={"stdout": "Python 3.11.9\n", "returncode": 0},
                    )
                ],
            )

        intent = planner.plan(
            "请用工具执行 python --version，然后用中文告诉我结果",
            [{"role": "assistant", "content": "上一轮回答", "reasoning_content": "old reasoning"}],
            tool_executor=_executor,
        )

        self.assertEqual(intent.assistant_text, "当前 Python 版本是 3.11.9。")
        self.assertEqual(intent.status_hint, "tool")
        self.assertEqual(len(intent.tool_events), 1)
        self.assertEqual(len(fake_client.chat.completions.requests), 2)

        first_messages = fake_client.chat.completions.requests[0]["messages"]
        self.assertFalse(any("reasoning_content" in message for message in first_messages))

        second_messages = fake_client.chat.completions.requests[1]["messages"]
        assistant_messages = [message for message in second_messages if message.get("role") == "assistant"]
        self.assertTrue(any(message.get("reasoning_content") == "first reasoning" for message in assistant_messages))
        tool_messages = [message for message in second_messages if message.get("role") == "tool"]
        self.assertEqual(len(tool_messages), 1)

    def test_qwen_openai_chat_uses_enable_thinking_and_replays_current_turn_reasoning(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="qwen-plus",
                api_key="sk-test",
                provider_name="qwen",
                planner_kind="openai_chat",
                base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                raw_model={
                    "supports_tools": True,
                    "supports_reasoning": True,
                    "reasoning_mode": "enable_thinking",
                    "reasoning_output_field": "reasoning_content",
                },
            ),
            host_platform=host_platform,
        )

        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="shell", arguments='{"command":"pwd"}'),
        )
        fake_client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="", reasoning_content="qwen thinking", tool_calls=[tool_call]),
                SimpleNamespace(content="当前目录已经读取完成。", reasoning_content="after tool", tool_calls=[]),
            ]
        )
        planner.client = fake_client

        def _executor(command_text: str):
            self.assertEqual(command_text, "/shell Get-Location")
            return (
                "执行完成",
                [
                    ToolEvent(
                        name="shell",
                        ok=True,
                        summary="shell rc=0",
                        payload={"stdout": "Path\n----\nC:\\project\\agenthub_legacy\\agent_cli\n", "returncode": 0},
                    )
                ],
            )

        intent = planner.plan("看一下当前目录", [], tool_executor=_executor)

        self.assertEqual(intent.assistant_text, "模型未返回内容。")
        self.assertEqual(len(fake_client.chat.completions.requests), 1)
        self.assertEqual(fake_client.chat.completions.requests[0]["extra_body"], {"enable_thinking": True})
        second_messages = fake_client.chat.completions.requests[0]["messages"]
        assistant_messages = [message for message in second_messages if message.get("role") == "assistant"]
        self.assertFalse(any(message.get("reasoning_content") == "qwen thinking" for message in assistant_messages))

    def test_glm_openai_chat_uses_thinking_type_extra_body(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="glm-4.7",
                api_key="sk-test",
                provider_name="glm",
                planner_kind="openai_chat",
                base_url="https://open.bigmodel.cn/api/paas/v4",
                raw_model={
                    "supports_tools": True,
                    "supports_reasoning": True,
                    "reasoning_mode": "thinking.type",
                    "reasoning_output_field": "reasoning_content",
                },
            ),
            host_platform=host_platform,
        )
        planner.client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="GLM ready.", reasoning_content="glm thinking", tool_calls=[]),
            ]
        )

        intent = planner.plan("打个招呼", [])

        self.assertEqual(intent.assistant_text, "GLM ready.")
        self.assertEqual(
            planner.client.chat.completions.requests[0]["extra_body"],
            {"thinking": {"type": "enabled", "clear_thinking": False}},
        )

    def test_openai_chat_model_without_tools_omits_tools_payload(self) -> None:
        host_platform = detect_host_platform(system_name="Windows", sys_platform="win32")
        planner = DeepSeekPlanner(
            ProviderConfig(
                model="chat-no-tools",
                api_key="sk-test",
                provider_name="custom",
                planner_kind="openai_chat",
                base_url="https://example.invalid/v1",
                raw_model={
                    "supports_tools": False,
                    "supports_reasoning": False,
                },
            ),
            host_platform=host_platform,
        )
        planner.client = self._FakeDeepSeekClient(
            [
                SimpleNamespace(content="plain response", tool_calls=[]),
            ]
        )

        intent = planner.plan("普通问答", [])

        self.assertEqual(intent.assistant_text, "plain response")
        request = planner.client.chat.completions.requests[0]
        self.assertNotIn("tools", request)
        self.assertNotIn("tool_choice", request)
