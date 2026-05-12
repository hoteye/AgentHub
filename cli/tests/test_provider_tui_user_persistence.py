from __future__ import annotations

import json
import os
import tomllib
import unittest
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.agent import RuleBasedAgent
from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.main import _build_tui_runtime
from cli.agent_cli.models import AgentIntent
from cli.agent_cli.providers.config.paths import AGENTHUB_PROVIDER_HOME_ENV
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.thread_store import ThreadStore
from cli.agent_cli.ui.widgets import SlashCommandPopup


class _PlannerFromConfig:
    def __init__(self, config) -> None:
        self._config = config

    def public_summary(self):
        return self._config.public_summary()

    def plan(self, text, history, *, tool_executor=None, attachments=None, input_items=None, turn_event_callback=None):
        del text, history, tool_executor, attachments, input_items, turn_event_callback
        return AgentIntent(assistant_text="ok")


class ProviderTuiUserPersistenceTest(unittest.IsolatedAsyncioTestCase):
    async def test_provider_popup_submit_persists_user_selection(self) -> None:
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
                stack.enter_context(
                    patch.dict(os.environ, {AGENTHUB_PROVIDER_HOME_ENV: str(project_home)}, clear=False)
                )
                stack.enter_context(patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", user_config))
                stack.enter_context(patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", missing / "auth.json"))
                stack.enter_context(
                    patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", missing / "config.toml")
                )
                stack.enter_context(
                    patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", missing / "auth.json")
                )
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
                app = AgentCliApp(runtime=runtime)

                async with app.run_test() as pilot:
                    await pilot.pause()
                    app._set_prompt_text("/provider gl")
                    await pilot.pause()

                    popup = app.query_one("#slash_popup", SlashCommandPopup)
                    self.assertIn("glm", popup.render().plain)

                    await pilot.press("enter")
                    await app._wait_for_runtime_idle()
                    await pilot.pause()

                persisted_payload = tomllib.loads(user_config.read_text(encoding="utf-8"))
                current_status = runtime.agent.provider_status()

            self.assertEqual(persisted_payload["model_provider"], "glm")
            self.assertEqual(persisted_payload["model"], "glm_5")
            self.assertEqual(current_status["provider_name"], "glm")
            self.assertEqual(current_status["provider_selection_scope"], "user_home")
            self.assertTrue(current_status["provider_selection_active"])

    async def test_tui_restart_restores_last_provider_selection_and_footer_summary(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_root = root / "project"
            cli_root = project_root / "cli"
            project_home = cli_root / ".config"
            project_config = project_home / "config.toml"
            project_auth = project_home / "auth.json"
            user_config = root / "home" / ".agent_cli" / "config.toml"
            missing = root / "missing"
            thread_store = ThreadStore(project_home / "threads-test")

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
                stack.enter_context(
                    patch.dict(
                        os.environ,
                        {
                            AGENTHUB_PROVIDER_HOME_ENV: str(project_home),
                            "AGENTHUB_PROJECT_ROOT": str(project_root),
                            "AGENTHUB_STARTUP_CWD": str(cli_root),
                        },
                        clear=False,
                    )
                )
                stack.enter_context(patch("cli.agent_cli.provider.AGENT_CLI_CONFIG_TOML", user_config))
                stack.enter_context(patch("cli.agent_cli.provider.AGENT_CLI_AUTH_JSON", missing / "auth.json"))
                stack.enter_context(
                    patch("cli.agent_cli.provider.LEGACY_COMPAT_CONFIG_TOML", missing / "config.toml")
                )
                stack.enter_context(
                    patch("cli.agent_cli.provider.LEGACY_COMPAT_AUTH_JSON", missing / "auth.json")
                )
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
                stack.enter_context(
                    patch("cli.agent_cli.runtime_factory.ThreadStore.default", return_value=thread_store)
                )
                stack.enter_context(patch("cli.agent_cli.runtime_factory.JsonlGatewayStateStore.default"))

                runtime = AgentCliRuntime(agent=RuleBasedAgent(), thread_store=thread_store)
                app = AgentCliApp(runtime=runtime)

                async with app.run_test() as pilot:
                    await pilot.pause()
                    app._set_prompt_text("/provider gl")
                    await pilot.pause()

                    popup = app.query_one("#slash_popup", SlashCommandPopup)
                    self.assertIn("glm", popup.render().plain)

                    await pilot.press("enter")
                    await app._wait_for_runtime_idle()
                    await pilot.pause()

                args = SimpleNamespace(
                    resume=None,
                    resume_path=None,
                    resume_last=False,
                    permission_mode=None,
                    approval_policy="never",
                    sandbox_mode="danger-full-access",
                    web_search_mode=None,
                    network_access=None,
                )
                restarted_runtime = _build_tui_runtime(args, None)
                restarted_status = restarted_runtime.agent.provider_status()

                self.assertEqual(restarted_status["provider_name"], "glm")
                self.assertEqual(restarted_status["provider_model"], "glm-5")
                self.assertEqual(restarted_status["provider_selection_scope"], "user_home")
                self.assertTrue(restarted_status["provider_selection_active"])

                restarted_app = AgentCliApp(runtime=restarted_runtime)
                async with restarted_app.run_test() as pilot:
                    await pilot.pause()
                    footer = str(restarted_app.query_one("#composer_footer").renderable)

                self.assertIn("glm", footer)
                self.assertIn("glm-5", footer)
