from __future__ import annotations

import json
import os
import tomllib
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cli.agent_cli.agent import RuleBasedAgent
from cli.agent_cli.models import AgentIntent
from cli.agent_cli import provider as provider_module
from cli.agent_cli.provider import save_user_model_selection
from cli.agent_cli.providers.config.paths import AGENTHUB_PROVIDER_HOME_ENV
from cli.agent_cli.runtime import AgentCliRuntime

class _PlannerFromConfig:
    def __init__(self, config) -> None:
        self._config = config

    def public_summary(self):
        return self._config.public_summary()

    def plan(self, text, history, *, tool_executor=None, attachments=None, input_items=None):
        del text, history, tool_executor, attachments, input_items
        return AgentIntent(assistant_text="ok")

def test_save_user_model_selection_writes_root_keys_before_existing_sections() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        user_config = root / ".agent_cli" / "config.toml"
        user_config.parent.mkdir(parents=True, exist_ok=True)
        user_config.write_text('[cli]\nlang = "zh-CN"\n', encoding="utf-8")

        with patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", user_config):
            save_user_model_selection(provider_name="glm", model="glm_5")

        saved_text = user_config.read_text(encoding="utf-8")
        payload = tomllib.loads(saved_text)

        assert payload["model_provider"] == "glm"
        assert payload["model"] == "glm_5"
        assert payload["cli"]["lang"] == "zh-CN"
        assert saved_text.index('model_provider = "glm"') < saved_text.index("[cli]")
        assert saved_text.index('model = "glm_5"') < saved_text.index("[cli]")

def test_provider_command_persists_user_selection_and_restores_it_on_restart() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        project_home = root / "cli" / ".config"
        project_config = project_home / "config.toml"
        project_auth = project_home / "auth.json"
        user_config = root / "home" / ".agent_cli" / "config.toml"
        missing = root / "missing"

        project_config.parent.mkdir(parents=True, exist_ok=True)
        user_config.parent.mkdir(parents=True, exist_ok=True)

        project_config.write_text(
            "\n".join(
                [
                    'model_provider = "openai"',
                    'model = "gpt_54"',
                    '[model_providers.openai]',
                    'api_key_env = "OPENAI_API_KEY"',
                    'base_url = "https://relay.example/v1"',
                    'wire_api = "responses"',
                    'default_model = "gpt_54"',
                    '[model_providers.glm]',
                    'api_key_env = "GLM_API_KEY"',
                    'base_url = "https://glm.example/v1"',
                    'planner_kind = "openai_chat"',
                    'wire_api = "openai_chat"',
                    'default_model = "glm_5"',
                    '[models.gpt_54]',
                    'provider = "openai"',
                    'model = "gpt-5.4"',
                    'planner_kind = "openai_responses"',
                    'wire_api = "responses"',
                    'supports_reasoning = true',
                    '[models.glm_5]',
                    'provider = "glm"',
                    'model = "glm-5"',
                    'planner_kind = "openai_chat"',
                    'wire_api = "openai_chat"',
                    'supports_reasoning = true',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        project_auth.write_text(
            json.dumps(
                {
                    "OPENAI_API_KEY": "sk-openai",
                    "GLM_API_KEY": "sk-glm",
                }
            ),
            encoding="utf-8",
        )
        user_config.write_text('[cli]\nlang = "zh-CN"\n', encoding="utf-8")

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {AGENTHUB_PROVIDER_HOME_ENV: str(project_home)}, clear=False))
            stack.enter_context(patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", user_config))
            stack.enter_context(patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", missing / "auth.json"))
            stack.enter_context(patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", missing / "config.toml"))
            stack.enter_context(patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", missing / "auth.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_SETTINGS_JSON", missing / "settings.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_CONFIG_JSON", missing / "config.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_STATE_JSON", missing / "state.json"))
            stack.enter_context(patch("cli.agent_cli.provider._ensure_project_provider_bootstrap", return_value=None))
            stack.enter_context(patch("cli.agent_cli.provider._find_project_provider_file", return_value=None))
            stack.enter_context(patch("cli.agent_cli.agent._project_claude_home_dir", return_value=None))
            stack.enter_context(
                patch(
                    "cli.agent_cli.agent.build_planner",
                    side_effect=lambda config, **kwargs: _PlannerFromConfig(config),
                )
            )

            runtime = AgentCliRuntime(agent=RuleBasedAgent())
            initial_status = runtime.agent.provider_status()
            response = runtime.handle_prompt("/provider glm")
            persisted_payload = tomllib.loads(user_config.read_text(encoding="utf-8"))
            project_payload = tomllib.loads(project_config.read_text(encoding="utf-8"))
            restored_status = RuleBasedAgent().provider_status()

        assert initial_status["provider_name"] == "openai"
        assert initial_status["provider_model"] == "gpt-5.4"
        assert "switched provider to glm" in response.assistant_text
        assert response.command_display_text == "switched provider to glm and saved as user default"
        assert "provider_model" in response.assistant_text
        assert "provider_model" not in response.command_display_text
        assert persisted_payload["model_provider"] == "glm"
        assert persisted_payload["model"] == "glm_5"
        assert persisted_payload["cli"]["lang"] == "zh-CN"
        assert project_payload["model_provider"] == "openai"
        assert project_payload["model"] == "gpt_54"
        assert restored_status["provider_name"] == "glm"
        assert restored_status["provider_model"] == "glm-5"


def test_provider_command_write_scope_session_does_not_persist_user_selection() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        project_home = root / "cli" / ".config"
        project_config = project_home / "config.toml"
        project_auth = project_home / "auth.json"
        user_config = root / "home" / ".agent_cli" / "config.toml"
        missing = root / "missing"

        project_config.parent.mkdir(parents=True, exist_ok=True)
        user_config.parent.mkdir(parents=True, exist_ok=True)

        project_config.write_text(
            "\n".join(
                [
                    'model_provider = "openai"',
                    'model = "gpt_54"',
                    '[model_providers.openai]',
                    'api_key_env = "OPENAI_API_KEY"',
                    'base_url = "https://relay.example/v1"',
                    'wire_api = "responses"',
                    'default_model = "gpt_54"',
                    '[model_providers.glm]',
                    'api_key_env = "GLM_API_KEY"',
                    'base_url = "https://glm.example/v1"',
                    'planner_kind = "openai_chat"',
                    'wire_api = "openai_chat"',
                    'default_model = "glm_5"',
                    '[models.gpt_54]',
                    'provider = "openai"',
                    'model = "gpt-5.4"',
                    'planner_kind = "openai_responses"',
                    'wire_api = "responses"',
                    'supports_reasoning = true',
                    '[models.glm_5]',
                    'provider = "glm"',
                    'model = "glm-5"',
                    'planner_kind = "openai_chat"',
                    'wire_api = "openai_chat"',
                    'supports_reasoning = true',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        project_auth.write_text(
            json.dumps({"OPENAI_API_KEY": "sk-openai", "GLM_API_KEY": "sk-glm"}),
            encoding="utf-8",
        )
        user_config.write_text('[cli]\nlang = "zh-CN"\n', encoding="utf-8")

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {AGENTHUB_PROVIDER_HOME_ENV: str(project_home)}, clear=False))
            stack.enter_context(patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", user_config))
            stack.enter_context(patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", missing / "auth.json"))
            stack.enter_context(patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", missing / "config.toml"))
            stack.enter_context(patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", missing / "auth.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_SETTINGS_JSON", missing / "settings.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_CONFIG_JSON", missing / "config.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_STATE_JSON", missing / "state.json"))
            stack.enter_context(patch("cli.agent_cli.provider._ensure_project_provider_bootstrap", return_value=None))
            stack.enter_context(patch("cli.agent_cli.provider._find_project_provider_file", return_value=None))
            stack.enter_context(patch("cli.agent_cli.agent._project_claude_home_dir", return_value=None))
            stack.enter_context(
                patch(
                    "cli.agent_cli.agent.build_planner",
                    side_effect=lambda config, **kwargs: _PlannerFromConfig(config),
                )
            )

            runtime = AgentCliRuntime(agent=RuleBasedAgent())
            response = runtime.handle_prompt("/provider glm --write session")
            persisted_payload = tomllib.loads(user_config.read_text(encoding="utf-8"))
            current_status = runtime.agent.provider_status()
            restored_status = RuleBasedAgent().provider_status()

        assert "switched provider for this session to glm" in response.assistant_text
        assert "write_scope=session" in response.assistant_text
        assert persisted_payload["cli"]["lang"] == "zh-CN"
        assert "model_provider" not in persisted_payload
        assert "model" not in persisted_payload
        assert current_status["provider_name"] == "glm"
        assert restored_status["provider_name"] == "openai"


def test_provider_command_persisted_selection_overrides_project_local_on_restart() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        project_home = root / "cli" / ".config"
        project_config = project_home / "config.toml"
        project_auth = project_home / "auth.json"
        user_config = root / "home" / ".agent_cli" / "config.toml"
        missing = root / "missing"

        project_config.parent.mkdir(parents=True, exist_ok=True)
        user_config.parent.mkdir(parents=True, exist_ok=True)

        project_config.write_text(
            "\n".join(
                [
                    'model_provider = "openai"',
                    'model = "gpt_54"',
                    '[model_providers.openai]',
                    'api_key_env = "OPENAI_API_KEY"',
                    'base_url = "https://relay.example/v1"',
                    'wire_api = "responses"',
                    'default_model = "gpt_54"',
                    '[model_providers.glm]',
                    'api_key_env = "GLM_API_KEY"',
                    'base_url = "https://glm.example/v1"',
                    'planner_kind = "openai_chat"',
                    'wire_api = "openai_chat"',
                    'default_model = "glm_5"',
                    '[models.gpt_54]',
                    'provider = "openai"',
                    'model = "gpt-5.4"',
                    'planner_kind = "openai_responses"',
                    'wire_api = "responses"',
                    'supports_reasoning = true',
                    '[models.glm_5]',
                    'provider = "glm"',
                    'model = "glm-5"',
                    'planner_kind = "openai_chat"',
                    'wire_api = "openai_chat"',
                    'supports_reasoning = true',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        project_auth.write_text(
            json.dumps(
                {
                    "OPENAI_API_KEY": "sk-openai",
                    "GLM_API_KEY": "sk-glm",
                }
            ),
            encoding="utf-8",
        )
        user_config.write_text('[cli]\nlang = "zh-CN"\n', encoding="utf-8")

        def _find_project_file(filename: str, *, cwd=None):
            del cwd
            if filename == "config.toml":
                return project_config
            if filename == "auth.json":
                return project_auth
            return None

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {AGENTHUB_PROVIDER_HOME_ENV: str(project_home)}, clear=False))
            stack.enter_context(patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", user_config))
            stack.enter_context(patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", missing / "auth.json"))
            stack.enter_context(patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", missing / "config.toml"))
            stack.enter_context(patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", missing / "auth.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_SETTINGS_JSON", missing / "settings.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_CONFIG_JSON", missing / "config.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_STATE_JSON", missing / "state.json"))
            stack.enter_context(patch("cli.agent_cli.provider._ensure_project_provider_bootstrap", return_value=None))
            stack.enter_context(patch("cli.agent_cli.provider._find_project_provider_file", side_effect=_find_project_file))
            stack.enter_context(patch("cli.agent_cli.agent._project_claude_home_dir", return_value=None))
            stack.enter_context(
                patch(
                    "cli.agent_cli.agent.build_planner",
                    side_effect=lambda config, **kwargs: _PlannerFromConfig(config),
                )
            )

            runtime = AgentCliRuntime(agent=RuleBasedAgent())
            initial_status = runtime.agent.provider_status()
            response = runtime.handle_prompt("/provider glm")
            persisted_payload = tomllib.loads(user_config.read_text(encoding="utf-8"))
            restored_status = RuleBasedAgent().provider_status()

        assert initial_status["provider_name"] == "openai"
        assert initial_status["provider_model"] == "gpt-5.4"
        assert initial_status["provider_source"] == "runtime_home"
        assert initial_status["provider_source_raw"] == "project_local"
        assert initial_status["provider_config_scope"] == "runtime_home"
        assert initial_status["provider_selection_scope"] == "none"
        assert initial_status["provider_selection_active"] is False
        assert initial_status["provider_runtime_home_active"] is True
        assert initial_status["provider_runtime_home_path"] == str(project_home)
        assert "switched provider to glm" in response.assistant_text
        assert persisted_payload["model_provider"] == "glm"
        assert persisted_payload["model"] == "glm_5"
        assert restored_status["provider_name"] == "glm"
        assert restored_status["provider_model"] == "glm-5"
        assert restored_status["provider_source"] == "runtime_home"
        assert restored_status["provider_source_raw"] == "project_local"
        assert restored_status["provider_config_scope"] == "runtime_home"
        assert restored_status["provider_selection_scope"] == "user_home"
        assert restored_status["provider_selection_active"] is True
        assert restored_status["provider_runtime_home_active"] is True
        assert restored_status["provider_runtime_home_path"] == str(project_home)
        assert restored_status["provider_config_path"] == str(project_config)
        assert restored_status["provider_selection_path"] == str(user_config)



def test_model_command_persists_user_selection_and_restores_it_on_restart() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        project_home = root / "cli" / ".config"
        project_config = project_home / "config.toml"
        project_auth = project_home / "auth.json"
        user_config = root / "home" / ".agent_cli" / "config.toml"
        missing = root / "missing"

        project_config.parent.mkdir(parents=True, exist_ok=True)
        user_config.parent.mkdir(parents=True, exist_ok=True)

        project_config.write_text(
            "\n".join(
                [
                    'model_provider = "openai"',
                    'model = "gpt_54"',
                    '[model_providers.openai]',
                    'api_key_env = "OPENAI_API_KEY"',
                    'base_url = "https://relay.example/v1"',
                    'wire_api = "responses"',
                    'default_model = "gpt_54"',
                    '[model_providers.glm]',
                    'api_key_env = "GLM_API_KEY"',
                    'base_url = "https://glm.example/v1"',
                    'planner_kind = "openai_chat"',
                    'wire_api = "openai_chat"',
                    'default_model = "glm_5"',
                    '[models.gpt_54]',
                    'provider = "openai"',
                    'model = "gpt-5.4"',
                    'planner_kind = "openai_responses"',
                    'wire_api = "responses"',
                    'supports_reasoning = true',
                    '[models.glm_5]',
                    'provider = "glm"',
                    'model = "glm-5"',
                    'planner_kind = "openai_chat"',
                    'wire_api = "openai_chat"',
                    'supports_reasoning = true',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        project_auth.write_text(
            json.dumps(
                {
                    "OPENAI_API_KEY": "sk-openai",
                    "GLM_API_KEY": "sk-glm",
                }
            ),
            encoding="utf-8",
        )
        user_config.write_text('[cli]\nlang = "zh-CN"\n', encoding="utf-8")

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {AGENTHUB_PROVIDER_HOME_ENV: str(project_home)}, clear=False))
            stack.enter_context(patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", user_config))
            stack.enter_context(patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", missing / "auth.json"))
            stack.enter_context(patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", missing / "config.toml"))
            stack.enter_context(patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", missing / "auth.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_SETTINGS_JSON", missing / "settings.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_CONFIG_JSON", missing / "config.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_STATE_JSON", missing / "state.json"))
            stack.enter_context(patch("cli.agent_cli.provider._ensure_project_provider_bootstrap", return_value=None))
            stack.enter_context(patch("cli.agent_cli.provider._find_project_provider_file", return_value=None))
            stack.enter_context(patch("cli.agent_cli.agent._project_claude_home_dir", return_value=None))
            stack.enter_context(
                patch(
                    "cli.agent_cli.agent.build_planner",
                    side_effect=lambda config, **kwargs: _PlannerFromConfig(config),
                )
            )

            runtime = AgentCliRuntime(agent=RuleBasedAgent())
            initial_status = runtime.agent.provider_status()
            response = runtime.handle_prompt("/model glm_5 --reasoning-effort xhigh")
            persisted_payload = tomllib.loads(user_config.read_text(encoding="utf-8"))
            project_payload = tomllib.loads(project_config.read_text(encoding="utf-8"))
            restored_status = RuleBasedAgent().provider_status()

        assert initial_status["provider_name"] == "openai"
        assert initial_status["provider_model"] == "gpt-5.4"
        assert "updated user default model=glm_5, reasoning_effort=xhigh" in response.assistant_text
        assert "provider_source=session_override" in response.assistant_text
        assert "provider_source=env" not in response.assistant_text
        assert persisted_payload["model_provider"] == "glm"
        assert persisted_payload["model"] == "glm_5"
        assert persisted_payload["model_reasoning_effort"] == "xhigh"
        assert persisted_payload["cli"]["lang"] == "zh-CN"
        assert project_payload["model_provider"] == "openai"
        assert project_payload["model"] == "gpt_54"
        assert restored_status["provider_name"] == "glm"
        assert restored_status["provider_model"] == "glm-5"
        assert restored_status["provider_reasoning_effort"] == "xhigh"


def test_model_command_write_scope_project_persists_workspace_selection() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        project_home = root / "cli" / ".config"
        project_config = project_home / "config.toml"
        project_auth = project_home / "auth.json"
        user_config = root / "home" / ".agent_cli" / "config.toml"
        missing = root / "missing"

        project_config.parent.mkdir(parents=True, exist_ok=True)
        user_config.parent.mkdir(parents=True, exist_ok=True)

        project_config.write_text(
            "\n".join(
                [
                    'model_provider = "openai"',
                    'model = "gpt_54"',
                    '[model_providers.openai]',
                    'api_key_env = "OPENAI_API_KEY"',
                    'base_url = "https://relay.example/v1"',
                    'wire_api = "responses"',
                    'default_model = "gpt_54"',
                    '[model_providers.glm]',
                    'api_key_env = "GLM_API_KEY"',
                    'base_url = "https://glm.example/v1"',
                    'planner_kind = "openai_chat"',
                    'wire_api = "openai_chat"',
                    'default_model = "glm_5"',
                    '[models.gpt_54]',
                    'provider = "openai"',
                    'model = "gpt-5.4"',
                    'planner_kind = "openai_responses"',
                    'wire_api = "responses"',
                    'supports_reasoning = true',
                    '[models.glm_5]',
                    'provider = "glm"',
                    'model = "glm-5"',
                    'planner_kind = "openai_chat"',
                    'wire_api = "openai_chat"',
                    'supports_reasoning = true',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        project_auth.write_text(
            json.dumps({"OPENAI_API_KEY": "sk-openai", "GLM_API_KEY": "sk-glm"}),
            encoding="utf-8",
        )
        user_config.write_text('[cli]\nlang = "zh-CN"\n', encoding="utf-8")

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {AGENTHUB_PROVIDER_HOME_ENV: str(project_home)}, clear=False))
            stack.enter_context(patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", user_config))
            stack.enter_context(patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", missing / "auth.json"))
            stack.enter_context(patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", missing / "config.toml"))
            stack.enter_context(patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", missing / "auth.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_SETTINGS_JSON", missing / "settings.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_CONFIG_JSON", missing / "config.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_STATE_JSON", missing / "state.json"))
            stack.enter_context(patch("cli.agent_cli.provider._ensure_project_provider_bootstrap", return_value=None))
            stack.enter_context(patch("cli.agent_cli.provider._find_project_provider_file", return_value=None))
            stack.enter_context(patch("cli.agent_cli.agent._project_claude_home_dir", return_value=None))
            stack.enter_context(
                patch(
                    "cli.agent_cli.agent.build_planner",
                    side_effect=lambda config, **kwargs: _PlannerFromConfig(config),
                )
            )

            runtime = AgentCliRuntime(agent=RuleBasedAgent())
            runtime.agent.cwd = root
            response = runtime.handle_prompt("/model glm_5 --reasoning-effort xhigh --write project")
            user_payload = tomllib.loads(user_config.read_text(encoding="utf-8"))
            project_payload = tomllib.loads((root / ".agent_cli" / "config.toml").read_text(encoding="utf-8"))

        assert "updated workspace default model=glm_5, reasoning_effort=xhigh" in response.assistant_text
        assert "write_scope=project" in response.assistant_text
        assert user_payload["cli"]["lang"] == "zh-CN"
        assert "model_provider" not in user_payload
        assert project_payload["model_provider"] == "glm"
        assert project_payload["model"] == "glm_5"
        assert project_payload["model_reasoning_effort"] == "xhigh"


def test_model_command_default_clears_persisted_user_selection_and_restores_project_default() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        project_home = root / "cli" / ".config"
        project_config = project_home / "config.toml"
        project_auth = project_home / "auth.json"
        user_config = root / "home" / ".agent_cli" / "config.toml"
        missing = root / "missing"

        project_config.parent.mkdir(parents=True, exist_ok=True)
        user_config.parent.mkdir(parents=True, exist_ok=True)

        project_config.write_text(
            "\n".join(
                [
                    'model_provider = "openai"',
                    'model = "gpt_54"',
                    '[model_providers.openai]',
                    'api_key_env = "OPENAI_API_KEY"',
                    'base_url = "https://relay.example/v1"',
                    'wire_api = "responses"',
                    'default_model = "gpt_54"',
                    '[model_providers.glm]',
                    'api_key_env = "GLM_API_KEY"',
                    'base_url = "https://glm.example/v1"',
                    'planner_kind = "openai_chat"',
                    'wire_api = "openai_chat"',
                    'default_model = "glm_5"',
                    '[models.gpt_54]',
                    'provider = "openai"',
                    'model = "gpt-5.4"',
                    'planner_kind = "openai_responses"',
                    'wire_api = "responses"',
                    'supports_reasoning = true',
                    '[models.glm_5]',
                    'provider = "glm"',
                    'model = "glm-5"',
                    'planner_kind = "openai_chat"',
                    'wire_api = "openai_chat"',
                    'supports_reasoning = true',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        project_auth.write_text(
            json.dumps(
                {
                    "OPENAI_API_KEY": "sk-openai",
                    "GLM_API_KEY": "sk-glm",
                }
            ),
            encoding="utf-8",
        )
        user_config.write_text(
            "\n".join(
                [
                    'model_provider = "glm"',
                    'model = "glm_5"',
                    'model_reasoning_effort = "xhigh"',
                    '',
                    '[cli]',
                    'lang = "zh-CN"',
                    '',
                ]
            ),
            encoding="utf-8",
        )

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {AGENTHUB_PROVIDER_HOME_ENV: str(project_home)}, clear=False))
            stack.enter_context(patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", user_config))
            stack.enter_context(patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", missing / "auth.json"))
            stack.enter_context(patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", missing / "config.toml"))
            stack.enter_context(patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", missing / "auth.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_SETTINGS_JSON", missing / "settings.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_CONFIG_JSON", missing / "config.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_STATE_JSON", missing / "state.json"))
            stack.enter_context(patch("cli.agent_cli.provider._ensure_project_provider_bootstrap", return_value=None))
            stack.enter_context(patch("cli.agent_cli.provider._find_project_provider_file", return_value=None))
            stack.enter_context(patch("cli.agent_cli.agent._project_claude_home_dir", return_value=None))
            stack.enter_context(
                patch(
                    "cli.agent_cli.agent.build_planner",
                    side_effect=lambda config, **kwargs: _PlannerFromConfig(config),
                )
            )

            runtime = AgentCliRuntime(agent=RuleBasedAgent())
            initial_snapshot = provider_module.load_provider_management_snapshot()
            response = runtime.handle_prompt("/model default --reasoning-effort default")
            persisted_payload = tomllib.loads(user_config.read_text(encoding="utf-8"))
            restored_snapshot = provider_module.load_provider_management_snapshot()

        assert initial_snapshot.selected_config is not None
        assert initial_snapshot.selected_config.provider_name == "glm"
        assert initial_snapshot.selected_config.model == "glm-5"
        assert initial_snapshot.selected_config.reasoning_effort == "xhigh"
        assert "updated user default model=default, reasoning_effort=default" in response.assistant_text
        assert "model_provider" not in persisted_payload
        assert "model" not in persisted_payload
        assert "model_reasoning_effort" not in persisted_payload
        assert persisted_payload["cli"]["lang"] == "zh-CN"
        assert restored_snapshot.selected_config is not None
        assert restored_snapshot.selected_config.provider_name == "openai"
        assert restored_snapshot.selected_config.model == "gpt-5.4"
        assert restored_snapshot.selected_config.reasoning_effort != "xhigh"


def test_model_command_project_write_uses_project_root_for_nested_workspace() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        workspace = root / "apps" / "api"
        project_home = root / "cli" / ".config"
        user_config = root / "home" / ".agent_cli" / "config.toml"
        missing = root / "missing"

        workspace.mkdir(parents=True, exist_ok=True)
        project_home.mkdir(parents=True, exist_ok=True)
        user_config.parent.mkdir(parents=True, exist_ok=True)
        (root / ".git").write_text("gitdir: here\n", encoding="utf-8")
        (project_home / "config.toml").write_text(
            "\n".join(
                [
                    'model_provider = "openai"',
                    'model = "gpt_54"',
                    '[model_providers.openai]',
                    'api_key_env = "OPENAI_API_KEY"',
                    'base_url = "https://relay.example/v1"',
                    'wire_api = "responses"',
                    'default_model = "gpt_54"',
                    '[model_providers.glm]',
                    'api_key_env = "GLM_API_KEY"',
                    'base_url = "https://glm.example/v1"',
                    'planner_kind = "openai_chat"',
                    'wire_api = "openai_chat"',
                    'default_model = "glm_5"',
                    '[models.gpt_54]',
                    'provider = "openai"',
                    'model = "gpt-5.4"',
                    'planner_kind = "openai_responses"',
                    'wire_api = "responses"',
                    'supports_reasoning = true',
                    '[models.glm_5]',
                    'provider = "glm"',
                    'model = "glm-5"',
                    'planner_kind = "openai_chat"',
                    'wire_api = "openai_chat"',
                    'supports_reasoning = true',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (project_home / "auth.json").write_text(
            json.dumps({"OPENAI_API_KEY": "sk-openai", "GLM_API_KEY": "sk-glm"}),
            encoding="utf-8",
        )
        user_config.write_text('[cli]\nlang = "zh-CN"\n', encoding="utf-8")

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {AGENTHUB_PROVIDER_HOME_ENV: str(project_home)}, clear=False))
            stack.enter_context(patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", user_config))
            stack.enter_context(patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", missing / "auth.json"))
            stack.enter_context(patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", missing / "config.toml"))
            stack.enter_context(patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", missing / "auth.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_SETTINGS_JSON", missing / "settings.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_CONFIG_JSON", missing / "config.json"))
            stack.enter_context(patch("cli.agent_cli.provider.CLAUDE_STATE_JSON", missing / "state.json"))
            stack.enter_context(patch("cli.agent_cli.provider._ensure_project_provider_bootstrap", return_value=None))
            stack.enter_context(patch("cli.agent_cli.provider._find_project_provider_file", return_value=None))
            stack.enter_context(patch("cli.agent_cli.agent._project_claude_home_dir", return_value=None))
            stack.enter_context(
                patch(
                    "cli.agent_cli.agent.build_planner",
                    side_effect=lambda config, **kwargs: _PlannerFromConfig(config),
                )
            )

            runtime = AgentCliRuntime(agent=RuleBasedAgent())
            runtime.agent.cwd = workspace
            response = runtime.handle_prompt("/model glm_5 --reasoning-effort xhigh --write project")

        project_payload = tomllib.loads((root / ".agent_cli" / "config.toml").read_text(encoding="utf-8"))
        assert "updated workspace default model=glm_5, reasoning_effort=xhigh" in response.assistant_text
        assert project_payload["model_provider"] == "glm"
        assert project_payload["model"] == "glm_5"
        assert project_payload["model_reasoning_effort"] == "xhigh"
