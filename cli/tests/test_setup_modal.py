from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from textual.widgets import Button, Input, Select, Static

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.providers.config.catalog import (
    ModelCatalogEntry,
    ProviderCatalog,
    ProviderCatalogEntry,
)
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.ui.presentation import resolve_presentation_settings
from cli.agent_cli.ui.setup_modal import (
    SetupOverlay,
    present_setup_overlay,
    setup_provider_details_for_app,
    setup_provider_options_for_app,
)


class SetupModalTest(unittest.IsolatedAsyncioTestCase):
    async def test_setup_overlay_shows_tab_focus_hint(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime(), language="en")

        async with app.run_test() as pilot:
            self.assertTrue(
                present_setup_overlay(
                    app=app,
                    payload={"provider": "openai"},
                    provider_options=["openai", "anthropic"],
                    on_submit=lambda payload: None,
                    on_cancel=lambda: None,
                )
            )
            await pilot.pause()

            overlay = app.query_one(f"#{SetupOverlay.ROOT_ID}", SetupOverlay)
            hint = overlay.query_one(f"#{SetupOverlay.FOCUS_HINT_ID}", Static)
            self.assertEqual(str(hint.renderable), "Use Tab to move between fields.")

    async def test_setup_overlay_uses_chinese_presentation(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime(), language="zh-CN")

        with patch(
            "cli.agent_cli.provider.load_provider_management_snapshot", side_effect=Exception
        ):
            async with app.run_test() as pilot:
                self.assertTrue(
                    present_setup_overlay(
                        app=app,
                        payload={"provider": "openai"},
                        provider_options=["openai", "anthropic"],
                        on_submit=lambda payload: None,
                        on_cancel=lambda: None,
                    )
                )
                await pilot.pause()

                overlay = app.query_one(f"#{SetupOverlay.ROOT_ID}", SetupOverlay)
                title = overlay.query_one(f"#{SetupOverlay.TITLE_ID}", Static)
                hint = overlay.query_one(f"#{SetupOverlay.FOCUS_HINT_ID}", Static)
                provider_label = overlay.query_one(f"#{SetupOverlay.PROVIDER_LABEL_ID}", Static)
                uri_label = overlay.query_one(f"#{SetupOverlay.BASE_URL_LABEL_ID}", Static)
                key_label = overlay.query_one(f"#{SetupOverlay.API_KEY_LABEL_ID}", Static)
                base_url = overlay.query_one(f"#{SetupOverlay.BASE_URL_INPUT_ID}", Input)
                save = overlay.query_one(f"#{SetupOverlay.SUBMIT_BUTTON_ID}", Button)

                self.assertEqual(str(title.renderable), "欢迎使用 AgentHub")
                self.assertEqual(str(hint.renderable), "使用 Tab 在字段之间切换。")
                self.assertEqual(str(provider_label.renderable), "provider")
                self.assertEqual(str(uri_label.renderable), "uri")
                self.assertEqual(str(key_label.renderable), "key")
                self.assertEqual(str(base_url.placeholder), "可选 API base URL")
                self.assertEqual(str(save.label), "保存")

                overlay.submit()
                notice = overlay.query_one(f"#{SetupOverlay.NOTICE_ID}", Static)
                self.assertEqual(str(notice.renderable), "缺少：API key")

    async def test_setup_overlay_updates_when_presentation_changes(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime(), language="en")

        async with app.run_test() as pilot:
            self.assertTrue(
                present_setup_overlay(
                    app=app,
                    payload={"provider": "openai"},
                    provider_options=["openai", "anthropic"],
                    on_submit=lambda payload: None,
                    on_cancel=lambda: None,
                )
            )
            await pilot.pause()

            overlay = app.query_one(f"#{SetupOverlay.ROOT_ID}", SetupOverlay)
            title = overlay.query_one(f"#{SetupOverlay.TITLE_ID}", Static)
            self.assertEqual(str(title.renderable), "Welcome to AgentHub")

            app._apply_presentation(
                resolve_presentation_settings(cwd=app._workspace_root, lang="zh-CN")
            )
            await pilot.pause()

            self.assertEqual(str(title.renderable), "欢迎使用 AgentHub")

    async def test_setup_provider_is_selected_from_options(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime(), language="en")
        submitted: list[dict[str, str]] = []

        async with app.run_test() as pilot:
            self.assertTrue(
                present_setup_overlay(
                    app=app,
                    payload={"provider": "anthropic", "base_url": "https://api.anthropic.com"},
                    provider_options=["openai", "anthropic"],
                    on_submit=submitted.append,
                    on_cancel=lambda: None,
                )
            )
            await pilot.pause()

            overlay = app.query_one(f"#{SetupOverlay.ROOT_ID}", SetupOverlay)
            provider_select = overlay.query_one(f"#{SetupOverlay.PROVIDER_SELECT_ID}", Select)
            self.assertEqual(provider_select.value, "anthropic")

            provider_select.value = "openai"
            overlay.query_one(f"#{SetupOverlay.BASE_URL_INPUT_ID}", Input).value = (
                "https://relay.example/v1"
            )
            overlay.query_one(f"#{SetupOverlay.API_KEY_INPUT_ID}", Input).value = "sk-openai"
            overlay.submit()

        self.assertEqual(
            submitted,
            [
                {
                    "provider": "openai",
                    "base_url": "https://relay.example/v1",
                    "api_key": "sk-openai",
                }
            ],
        )

    async def test_setup_overlay_prefills_configured_provider_details(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime(), language="en")

        with patch(
            "cli.agent_cli.provider.load_provider_management_snapshot",
            return_value=_provider_snapshot(),
        ):
            async with app.run_test() as pilot:
                self.assertTrue(
                    present_setup_overlay(
                        app=app,
                        payload={"provider": "openai"},
                        provider_options=["openai", "anthropic"],
                        on_submit=lambda payload: None,
                        on_cancel=lambda: None,
                    )
                )
                await pilot.pause()

                overlay = app.query_one(f"#{SetupOverlay.ROOT_ID}", SetupOverlay)
                provider_select = overlay.query_one(f"#{SetupOverlay.PROVIDER_SELECT_ID}", Select)
                base_url = overlay.query_one(f"#{SetupOverlay.BASE_URL_INPUT_ID}", Input)
                api_key = overlay.query_one(f"#{SetupOverlay.API_KEY_INPUT_ID}", Input)

                self.assertEqual(base_url.value, "https://api.openai.test/v1")
                self.assertEqual(api_key.value, "sk-openai")

                provider_select.value = "anthropic"
                await pilot.pause()

                self.assertEqual(base_url.value, "https://api.anthropic.test")
                self.assertEqual(api_key.value, "sk-anthropic")

    async def test_setup_overlay_mouse_click_focuses_inputs(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime(), language="en")

        with patch(
            "cli.agent_cli.provider.load_provider_management_snapshot", side_effect=Exception
        ):
            async with app.run_test(size=(100, 40)) as pilot:
                self.assertTrue(
                    present_setup_overlay(
                        app=app,
                        payload={"provider": "openai"},
                        provider_options=["openai", "anthropic"],
                        on_submit=lambda payload: None,
                        on_cancel=lambda: None,
                    )
                )
                await pilot.pause()

                overlay = app.query_one(f"#{SetupOverlay.ROOT_ID}", SetupOverlay)
                base_url = overlay.query_one(f"#{SetupOverlay.BASE_URL_INPUT_ID}", Input)
                api_key = overlay.query_one(f"#{SetupOverlay.API_KEY_INPUT_ID}", Input)

                await pilot.click(f"#{SetupOverlay.BASE_URL_INPUT_ID}", offset=(2, 1))
                await pilot.press("a", "b", "c")
                await pilot.pause()

                self.assertTrue(base_url.has_focus)
                self.assertEqual(base_url.value, "abc")

                await pilot.click(f"#{SetupOverlay.API_KEY_INPUT_ID}", offset=(2, 1))
                await pilot.press("x", "y", "z")
                await pilot.pause()

                self.assertTrue(api_key.has_focus)
                self.assertEqual(api_key.value, "xyz")

    def test_setup_provider_options_include_runtime_and_defaults(self) -> None:
        class _Agent:
            @staticmethod
            def provider_status() -> dict[str, str]:
                return {"provider_name": "deepseek"}

            @staticmethod
            def available_providers() -> list[dict[str, str]]:
                return [{"provider_name": "glm"}, {"provider_name": "anthropic"}]

        app = AgentCliApp(runtime=AgentCliRuntime(agent=_Agent()))

        self.assertEqual(
            setup_provider_options_for_app(app),
            ["deepseek", "glm", "anthropic", "openai"],
        )

    def test_setup_provider_details_include_configured_url_key_and_models(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        with patch(
            "cli.agent_cli.provider.load_provider_management_snapshot",
            return_value=_provider_snapshot(),
        ):
            details = setup_provider_details_for_app(app)

        self.assertEqual(details["openai"]["base_url"], "https://api.openai.test/v1")
        self.assertEqual(details["openai"]["api_key"], "sk-openai")
        self.assertEqual(
            details["openai"]["models"],
            ["gpt-5.5", "gpt-5.4"],
        )


def _provider_snapshot() -> SimpleNamespace:
    return SimpleNamespace(
        catalog=ProviderCatalog(
            providers={
                "openai": ProviderCatalogEntry(
                    provider_name="openai",
                    display_name="OpenAI",
                    base_url="https://api.openai.test/v1",
                    api_key_env="OPENAI_API_KEY",
                ),
                "anthropic": ProviderCatalogEntry(
                    provider_name="anthropic",
                    display_name="Anthropic",
                    base_url="https://api.anthropic.test",
                    api_key_env="ANTHROPIC_API_KEY",
                ),
            },
            models={
                "gpt_55": ModelCatalogEntry(
                    key="gpt_55",
                    provider_name="openai",
                    model_id="gpt-5.5",
                ),
                "gpt_54": ModelCatalogEntry(
                    key="gpt_54",
                    provider_name="openai",
                    model_id="gpt-5.4",
                ),
                "claude_sonnet_46": ModelCatalogEntry(
                    key="claude_sonnet_46",
                    provider_name="anthropic",
                    model_id="claude-sonnet-4-6",
                ),
            },
        ),
        auth_data={
            "OPENAI_API_KEY": "sk-openai",
            "ANTHROPIC_API_KEY": "sk-anthropic",
        },
        selected_config=None,
    )
