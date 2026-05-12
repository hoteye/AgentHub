from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.ui import slash_controller_popup_helpers
from cli.agent_cli.ui.presentation import (
    AUTO_LOCALE,
    SUPPORTED_LOCALES,
    resolve_presentation_settings,
)
from cli.agent_cli.ui.slash_controller import _SlashCompletionContext


class SlashControllerTest(unittest.TestCase):
    def test_local_slash_catalog_includes_lang_theme_setup_and_plan(self) -> None:
        names = [item["name"] for item in AgentCliApp._local_slash_command_specs()]

        self.assertEqual(
            names,
            [
                "lang",
                "theme",
                "setup",
                "plan",
                "tab_rename",
                "tab_new",
                "approval_inbox",
                "preview",
                "fork",
                "master",
                "fork_child",
                "close",
            ],
        )

    def test_local_slash_catalog_uses_requested_locale(self) -> None:
        specs = AgentCliApp._local_slash_command_specs(locale="zh-CN")
        descriptions = {item["name"]: item["description"] for item in specs}

        self.assertEqual(descriptions["lang"], "切换当前交互 TUI 的显示语言")
        self.assertEqual(descriptions["theme"], "切换当前交互 TUI 的主题")
        self.assertEqual(
            descriptions["approval_inbox"],
            "查看所有 TUI tab 的待处理审批，或跳转到指定 tab 处理",
        )
        self.assertEqual(
            descriptions["preview"],
            "打开、关闭、切换或查看固定分屏预览窗格状态",
        )
        self.assertEqual(descriptions["master"], "将当前 tab 标记为可见 master tab")
        self.assertEqual(descriptions["fork_child"], "从当前 master tab fork 一个可见 child tab")

    def test_complete_local_slash_command_adds_trailing_space_for_exact_match(self) -> None:
        self.assertEqual(AgentCliApp._complete_local_slash_command("lang"), "/lang ")
        self.assertEqual(AgentCliApp._complete_local_slash_command("/th"), "/theme ")

    def test_slash_argument_matches_offer_local_language_candidates(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app._current_prompt_text = lambda: "/lang z"  # type: ignore[method-assign]
        context = _SlashCompletionContext(
            mode="slash_arg",
            query="z",
            line_prefix="/lang z",
            line_end="/lang z",
            replace_start=6,
            replace_end=7,
            command_name="lang",
            arg_tokens=("z",),
            current_token="z",
            ends_with_space=False,
        )

        matches = app._slash_argument_matches(context)

        self.assertEqual(
            matches,
            [
                {
                    "name": "lang:zh-CN",
                    "usage": "zh-CN",
                    "description": "apply and save language",
                    "insert_text": "/lang zh-CN ",
                    "cursor_pos": "12",
                    "completion_mode": "slash_arg",
                    "submit_after_apply": "true",
                }
            ],
        )

    def test_slash_argument_matches_use_current_locale(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime(), language="zh-CN")
        app._current_prompt_text = lambda: "/lang z"  # type: ignore[method-assign]
        context = _SlashCompletionContext(
            mode="slash_arg",
            query="z",
            line_prefix="/lang z",
            line_end="/lang z",
            replace_start=6,
            replace_end=7,
            command_name="lang",
            arg_tokens=("z",),
            current_token="z",
            ends_with_space=False,
        )

        matches = app._slash_argument_matches(context)

        self.assertEqual(matches[0]["description"], "应用并保存语言")

    def test_handle_local_lang_command_without_value_reports_status(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        notices: list[str] = []
        app._write_system_notice = notices.append  # type: ignore[method-assign]

        app._handle_local_lang_command("")

        supported = ", ".join([*SUPPORTED_LOCALES, AUTO_LOCALE])
        self.assertEqual(
            notices,
            [app._t("system.lang_status", current=app._presentation.locale, supported=supported)],
        )

    def test_handle_local_theme_command_rejects_invalid_value(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        notices: list[str] = []
        app._write_system_notice = notices.append  # type: ignore[method-assign]

        app._handle_local_theme_command("not-a-theme")

        self.assertEqual(len(notices), 1)
        self.assertIn("not-a-theme", notices[0])

    def test_handle_local_theme_command_persists_and_applies_new_theme(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        notices: list[str] = []
        saved_path = Path("/tmp/user-config.toml")
        new_presentation = resolve_presentation_settings(cwd=app._workspace_root, theme_id="light")

        app._write_system_notice = notices.append  # type: ignore[method-assign]
        app._resolve_effective_presentation = lambda: new_presentation  # type: ignore[method-assign]
        app._theme_override_source = lambda value: None  # type: ignore[method-assign]

        def _apply(presentation) -> None:
            app._presentation = presentation

        app._apply_presentation = _apply  # type: ignore[method-assign]

        with patch(
            "cli.agent_cli.ui.slash_controller.save_user_presentation_preferences",
            return_value=saved_path,
        ):
            app._handle_local_theme_command("light")

        self.assertEqual(app._presentation.theme_id, "light")
        self.assertEqual(
            notices,
            [app._t("system.theme_saved", current="light", path=str(saved_path))],
        )

    def test_handle_local_setup_command_returns_false_when_args_are_present(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        self.assertFalse(app._handle_local_setup_command("status"))

    def test_handle_local_setup_command_opens_overlay_when_no_args(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        with patch(
            "cli.agent_cli.ui.setup_modal.present_setup_overlay",
            return_value=True,
        ) as present_overlay:
            self.assertTrue(app._handle_local_setup_command(""))

        present_overlay.assert_called_once()

    def test_handle_local_setup_command_submits_minimal_runtime_setup(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        notices: list[str] = []
        scheduled: list[str] = []

        async def _enqueue(text: str, attachments, **kwargs) -> None:
            del attachments, kwargs
            scheduled.append(text)

        class _FakeTask:
            def done(self) -> bool:
                return False

        def _fake_create_task(coro, *args, **kwargs):
            del args, kwargs
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(coro)
            finally:
                loop.close()
            return _FakeTask()

        def _present_overlay(*, on_submit, **kwargs):
            del kwargs
            on_submit(
                {
                    "provider": "openai",
                    "base_url": "https://example.test/v1",
                    "api_key": "sk-openai",
                }
            )
            return True

        app._write_system_notice = notices.append  # type: ignore[method-assign]
        app._enqueue_runtime_request = _enqueue  # type: ignore[method-assign]

        with (
            patch(
                "cli.agent_cli.ui.setup_modal.present_setup_overlay",
                side_effect=_present_overlay,
            ),
            patch.object(asyncio, "create_task", side_effect=_fake_create_task),
        ):
            self.assertTrue(app._handle_local_setup_command(""))

        self.assertEqual(notices, ["Running setup..."])
        self.assertEqual(
            scheduled,
            ["/setup provider openai api-key sk-openai user base-url https://example.test/v1"],
        )

    def test_handle_local_plan_command_switches_runtime_mode(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        notices: list[str] = []
        app._write_system_notice = notices.append  # type: ignore[method-assign]

        self.assertTrue(app._handle_local_plan_command(""))

        self.assertEqual(app.runtime.collaboration_mode, "plan")
        self.assertEqual(notices, ["switched to Plan mode"])

    def test_handle_local_tab_rename_command_updates_active_tab_label(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        notices: list[str] = []
        app._write_system_notice = notices.append  # type: ignore[method-assign]

        self.assertTrue(app._handle_local_tab_rename_command("  Phase 11   Rename  "))

        self.assertEqual(app._tab_manager.active_session.custom_label, "Phase 11 Rename")
        self.assertEqual(app._tab_manager.tab_labels()[0][1], "Phase 11 Rename")
        self.assertEqual(
            notices,
            [app._t("system.tab_rename_saved", label="Phase 11 Rename")],
        )

    def test_handle_local_tab_rename_command_clears_custom_label(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        notices: list[str] = []
        app._write_system_notice = notices.append  # type: ignore[method-assign]
        app._tab_manager.rename_tab("main", "Custom")

        self.assertTrue(app._handle_local_tab_rename_command(""))

        self.assertEqual(app._tab_manager.active_session.custom_label, "")
        self.assertEqual(
            notices,
            [app._t("system.tab_rename_cleared", label="")],
        )

    def test_handle_local_tab_new_command_creates_python_tab(self) -> None:
        from cli.agent_cli.runtime_factory import build_persistent_runtime

        async def _run() -> None:
            app = AgentCliApp(runtime=build_persistent_runtime(resume_active_thread=False))
            notices: list[str] = []
            app._write_system_notice = notices.append  # type: ignore[method-assign]

            async with app.run_test() as pilot:
                await pilot.pause()
                self.assertTrue(app._handle_local_tab_new_command("python"))
                await pilot.pause()

            self.assertEqual(app._tab_manager.active_tab_id, "tab-1")
            self.assertEqual(app._tab_manager.active_session.engine, "agenthub_python")
            self.assertEqual(
                notices,
                [
                    app._t(
                        "system.tab_new_created",
                        tab_id="tab-1",
                        engine="agenthub_python",
                    )
                ],
            )

        asyncio.run(_run())

    def test_handle_local_tab_new_command_creates_codex_sidecar_tab(self) -> None:
        from cli.agent_cli.runtime_kernels.codex_sidecar import CodexSidecarKernel

        async def _run() -> None:
            app = AgentCliApp(runtime=AgentCliRuntime())
            kernel = CodexSidecarKernel(
                codex_bin=Path(__file__).parent / "fixtures" / "fake_codex_sidecar.py",
                request_timeout=3,
            )
            app._codex_sidecar_kernel = kernel
            notices: list[str] = []
            app._write_system_notice = notices.append  # type: ignore[method-assign]
            try:
                async with app.run_test() as pilot:
                    await pilot.pause()
                    self.assertTrue(app._handle_local_tab_new_command("openai"))
                    await pilot.pause()

                self.assertEqual(app._tab_manager.active_tab_id, "tab-1")
                self.assertEqual(app._tab_manager.active_session.engine, "codex_sidecar")
                self.assertEqual(app._tab_manager.active_session.runtime.thread_id, "thread-1")
                self.assertEqual(
                    notices,
                    [
                        app._t(
                            "system.tab_new_created",
                            tab_id="tab-1",
                            engine="codex_sidecar",
                        )
                    ],
                )
            finally:
                await kernel.aclose()

        asyncio.run(_run())

    def test_handle_local_tab_new_command_accepts_openai_codex_alias(self) -> None:
        from cli.agent_cli.runtime_kernels.codex_sidecar import CodexSidecarKernel

        async def _run() -> None:
            app = AgentCliApp(runtime=AgentCliRuntime())
            kernel = CodexSidecarKernel(
                codex_bin=Path(__file__).parent / "fixtures" / "fake_codex_sidecar.py",
                request_timeout=3,
            )
            app._codex_sidecar_kernel = kernel
            try:
                async with app.run_test() as pilot:
                    await pilot.pause()
                    self.assertTrue(app._handle_local_tab_new_command("openai_codex"))
                    await pilot.pause()

                self.assertEqual(app._tab_manager.active_session.engine, "codex_sidecar")
                self.assertEqual(app._tab_manager.active_session.runtime.thread_id, "thread-1")
            finally:
                await kernel.aclose()

        asyncio.run(_run())

    def test_handle_local_tab_new_command_reports_invalid_engine(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        notices: list[str] = []
        app._write_system_notice = notices.append  # type: ignore[method-assign]

        self.assertTrue(app._handle_local_tab_new_command("missing"))

        self.assertEqual(notices, [app._t("system.tab_new_usage")])

    def test_handle_local_master_command_marks_active_tab(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        notices: list[str] = []
        app._write_system_notice = notices.append  # type: ignore[method-assign]

        self.assertTrue(app._handle_local_master_command(""))

        self.assertEqual(app._tab_manager.active_session.role, "master")
        self.assertEqual(app._tab_manager.tab_labels()[0][1], "[M] AgentHub")
        self.assertEqual(notices, [app._t("system.master_marked", tab_id="1")])

    def test_handle_local_fork_child_command_creates_visible_child(self) -> None:
        from cli.agent_cli.runtime_factory import build_persistent_runtime

        async def _run() -> None:
            app = AgentCliApp(runtime=build_persistent_runtime(resume_active_thread=False))
            notices: list[str] = []
            app._write_system_notice = notices.append  # type: ignore[method-assign]

            async with app.run_test() as pilot:
                await pilot.pause()
                self.assertTrue(app._handle_local_fork_child_command(""))
                await pilot.pause()

            self.assertEqual(app._tab_manager.get("main").role, "master")
            child = app._tab_manager.active_session
            self.assertEqual(child.tab_id, "tab-1")
            self.assertEqual(child.role, "child")
            self.assertEqual(child.parent_tab_id, "main")
            self.assertEqual(app._tab_manager.child_tab_ids("main"), ["tab-1"])
            self.assertEqual(
                notices,
                [
                    app._t(
                        "system.fork_child_created",
                        child_tab_id="2",
                        parent_tab_id="1",
                    )
                ],
            )

        asyncio.run(_run())

    def test_handle_local_approval_inbox_command_reports_empty(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        notices: list[str] = []
        app._write_system_notice = notices.append  # type: ignore[method-assign]

        self.assertTrue(app._handle_local_approval_inbox_command(""))

        self.assertEqual(notices, [app._t("system.approval_inbox_empty")])

    def test_handle_local_approval_inbox_command_lists_pending_tabs(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        notices: list[str] = []
        app._write_system_notice = notices.append  # type: ignore[method-assign]
        app._tab_manager.active_session.thread_name = "Main pending approvals"
        app._tab_manager.active_session.pending_approvals = ["appr_main_1", "appr_main_2"]

        self.assertTrue(app._handle_local_approval_inbox_command(""))

        self.assertEqual(len(notices), 1)
        self.assertIn(app._t("system.approval_inbox_heading", count=2), notices[0])
        self.assertIn("main * [Main pending approvals]", notices[0])
        self.assertIn("appr_main_1, appr_main_2", notices[0])
        self.assertIn("/approval_inbox go <tab_id>", notices[0])

    def test_handle_local_approval_inbox_go_switches_tab(self) -> None:
        from cli.agent_cli.runtime_factory import build_persistent_runtime

        app = AgentCliApp(runtime=build_persistent_runtime(resume_active_thread=False))
        notices: list[str] = []
        app._write_system_notice = notices.append  # type: ignore[method-assign]
        app._tab_manager._start_worker_task = lambda tab_id: None  # type: ignore[method-assign]
        tab_id = app._tab_manager.create_tab()
        self.assertEqual(tab_id, "tab-1")
        self.assertEqual(app._tab_manager.active_tab_id, "tab-1")

        self.assertTrue(app._handle_local_approval_inbox_command("go main"))

        self.assertEqual(app._tab_manager.active_tab_id, "main")
        self.assertEqual(
            notices,
            [app._t("system.approval_inbox_switched", tab_id="main")],
        )

    def test_handle_local_approval_inbox_go_reports_missing_tab(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        notices: list[str] = []
        app._write_system_notice = notices.append  # type: ignore[method-assign]

        self.assertTrue(app._handle_local_approval_inbox_command("go missing"))

        self.assertEqual(
            notices,
            [app._t("system.approval_inbox_tab_not_found", tab_id="missing")],
        )

    def test_handle_local_plan_command_with_args_queues_prompt_in_plan_mode(self) -> None:
        async def _scenario() -> tuple[str, list[str], list[tuple[str, list, dict]]]:
            app = AgentCliApp(runtime=AgentCliRuntime())
            notices: list[str] = []
            scheduled: list[tuple[str, list, dict]] = []

            async def _enqueue(text: str, attachments, **kwargs) -> None:
                scheduled.append((text, list(attachments or []), dict(kwargs)))

            app._write_system_notice = notices.append  # type: ignore[method-assign]
            app._enqueue_runtime_request = _enqueue  # type: ignore[method-assign]

            self.assertTrue(app._handle_local_plan_command("inspect this"))
            await asyncio.sleep(0)
            return app.runtime.collaboration_mode, notices, scheduled

        mode, notices, scheduled = asyncio.run(_scenario())

        self.assertEqual(mode, "plan")
        self.assertEqual(notices, [])
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0][0], "inspect this")
        self.assertEqual(scheduled[0][2].get("priority"), "next")

    def test_slash_argument_matches_offer_provider_candidates_as_submit_actions(self) -> None:
        class _Agent:
            @staticmethod
            def provider_status() -> dict[str, str]:
                return {"provider_name": "openai", "provider_public_name": "openai"}

            @staticmethod
            def available_providers() -> list[dict[str, str]]:
                return [{"provider_name": "openai"}, {"provider_name": "anthropic"}]

        runtime = AgentCliRuntime(agent=_Agent())
        app = AgentCliApp(runtime=runtime)
        app._current_prompt_text = lambda: "/provider ant"  # type: ignore[method-assign]
        context = _SlashCompletionContext(
            mode="slash_arg",
            query="ant",
            line_prefix="/provider ant",
            line_end="/provider ant",
            replace_start=10,
            replace_end=13,
            command_name="provider",
            arg_tokens=("ant",),
            current_token="ant",
            ends_with_space=False,
        )

        matches = app._slash_argument_matches(context)

        self.assertEqual(
            matches,
            [
                {
                    "name": "provider:anthropic",
                    "usage": "anthropic",
                    "description": "switch provider and save as user default",
                    "insert_text": "/provider anthropic ",
                    "cursor_pos": "20",
                    "completion_mode": "slash_arg",
                    "submit_after_apply": "true",
                },
            ],
        )

    def test_slash_argument_matches_only_show_provider_names_for_blank_provider_query(self) -> None:
        class _Agent:
            @staticmethod
            def provider_status() -> dict[str, str]:
                return {"provider_name": "openai", "provider_public_name": "openai"}

            @staticmethod
            def available_providers() -> list[dict[str, str]]:
                return [
                    {"provider_name": "openai"},
                    {"config_provider_name": "deepseek"},
                    {"provider_name": "anthropic"},
                ]

        runtime = AgentCliRuntime(agent=_Agent())
        app = AgentCliApp(runtime=runtime)
        app._current_prompt_text = lambda: "/provider "  # type: ignore[method-assign]
        context = _SlashCompletionContext(
            mode="slash_arg",
            query="",
            line_prefix="/provider ",
            line_end="/provider ",
            replace_start=10,
            replace_end=10,
            command_name="provider",
            arg_tokens=(),
            current_token="",
            ends_with_space=True,
        )

        matches = app._slash_argument_matches(context)

        self.assertEqual([item["usage"] for item in matches], ["openai", "deepseek", "anthropic"])
        self.assertTrue(all(item["name"].startswith("provider:") for item in matches))
        self.assertTrue(all(item.get("submit_after_apply") == "true" for item in matches))

    def test_slash_popup_ranks_current_provider_first_for_blank_query(self) -> None:
        class _Agent:
            @staticmethod
            def provider_status() -> dict[str, str]:
                return {"provider_name": "openai", "provider_public_name": "openai"}

            @staticmethod
            def available_providers() -> list[dict[str, str]]:
                return [
                    {"provider_name": "deepseek"},
                    {"provider_name": "openai"},
                    {"provider_name": "anthropic"},
                ]

        runtime = AgentCliRuntime(agent=_Agent())
        app = AgentCliApp(runtime=runtime)
        app._current_prompt_text = lambda: "/provider "  # type: ignore[method-assign]
        context = _SlashCompletionContext(
            mode="slash_arg",
            query="",
            line_prefix="/provider ",
            line_end="/provider ",
            replace_start=10,
            replace_end=10,
            command_name="provider",
            arg_tokens=(),
            current_token="",
            ends_with_space=True,
        )

        matches = app._slash_argument_matches(context)
        selected_index = slash_controller_popup_helpers._selected_index_for_slash_update(
            app,
            context,
            matches,
            [],
        )

        self.assertEqual([item["usage"] for item in matches], ["openai", "deepseek", "anthropic"])
        self.assertEqual(selected_index, 0)

    def test_slash_popup_selection_resets_when_argument_context_changes(self) -> None:
        class _Controller:
            _slash_selected_index = 2

        controller = _Controller()
        provider_context = _SlashCompletionContext(
            mode="slash_arg",
            query="",
            line_prefix="/provider ",
            line_end="/provider ",
            replace_start=10,
            replace_end=10,
            command_name="provider",
            arg_tokens=(),
            current_token="",
            ends_with_space=True,
        )
        model_context = _SlashCompletionContext(
            mode="slash_arg",
            query="",
            line_prefix="/model ",
            line_end="/model ",
            replace_start=7,
            replace_end=7,
            command_name="model",
            arg_tokens=(),
            current_token="",
            ends_with_space=True,
        )

        first_index = slash_controller_popup_helpers._selected_index_for_slash_update(
            controller,
            provider_context,
            [{"name": "provider:openai", "usage": "openai"}],
            [],
        )
        controller._slash_selected_index = 1
        same_index = slash_controller_popup_helpers._selected_index_for_slash_update(
            controller,
            provider_context,
            [{"name": "provider:openai", "usage": "openai"}],
            [],
        )
        reset_index = slash_controller_popup_helpers._selected_index_for_slash_update(
            controller,
            model_context,
            [{"name": "model:gpt_54", "usage": "gpt_54"}],
            [],
        )

        self.assertEqual(first_index, 0)
        self.assertEqual(same_index, 1)
        self.assertEqual(reset_index, 0)

    def test_slash_argument_matches_offer_model_candidates_as_submit_actions(self) -> None:
        class _Agent:
            @staticmethod
            def provider_status() -> dict[str, str]:
                return {"provider_name": "openai", "provider_public_name": "openai"}

            @staticmethod
            def available_models(provider_name=None) -> list[dict[str, str]]:
                del provider_name
                return [
                    {
                        "model_key": "gpt_54",
                        "display_name": "gpt-5.4",
                        "model_id": "gpt-5.4",
                        "provider_name": "openai",
                        "config_provider_name": "openai",
                    },
                    {
                        "model_key": "gpt_54_mini",
                        "display_name": "gpt-5.4-mini",
                        "model_id": "gpt-5.4-mini",
                        "provider_name": "openai",
                        "config_provider_name": "openai",
                    },
                ]

        runtime = AgentCliRuntime(agent=_Agent())
        app = AgentCliApp(runtime=runtime)
        app._current_prompt_text = lambda: "/model gpt_54_m"  # type: ignore[method-assign]
        context = _SlashCompletionContext(
            mode="slash_arg",
            query="gpt_54_m",
            line_prefix="/model gpt_54_m",
            line_end="/model gpt_54_m",
            replace_start=7,
            replace_end=15,
            command_name="model",
            arg_tokens=("gpt_54_m",),
            current_token="gpt_54_m",
            ends_with_space=False,
        )

        matches = app._slash_argument_matches(context)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["name"], "model:gpt_54_mini")
        self.assertEqual(matches[0]["usage"], "gpt_54_mini")
        self.assertIn("switch model and save as user default", matches[0]["description"])
        self.assertEqual(matches[0]["insert_text"], "/model gpt_54_mini ")
        self.assertEqual(matches[0]["cursor_pos"], "19")
        self.assertEqual(matches[0]["completion_mode"], "slash_arg")
        self.assertEqual(matches[0]["continue_completion"], "true")
        self.assertNotIn("submit_after_apply", matches[0])

    def test_slash_popup_ranks_current_model_first_for_blank_query(self) -> None:
        class _Agent:
            @staticmethod
            def provider_status() -> dict[str, str]:
                return {
                    "provider_name": "openai",
                    "provider_public_name": "openai",
                    "provider_model": "gpt-5.4-mini",
                }

            @staticmethod
            def available_models(provider_name=None) -> list[dict[str, str]]:
                del provider_name
                return [
                    {
                        "model_key": "gpt_54",
                        "display_name": "gpt-5.4",
                        "model_id": "gpt-5.4",
                        "provider_name": "openai",
                        "config_provider_name": "openai",
                    },
                    {
                        "model_key": "gpt_54_mini",
                        "display_name": "gpt-5.4-mini",
                        "model_id": "gpt-5.4-mini",
                        "provider_name": "openai",
                        "config_provider_name": "openai",
                    },
                ]

        runtime = AgentCliRuntime(agent=_Agent())
        app = AgentCliApp(runtime=runtime)
        app._current_prompt_text = lambda: "/model "  # type: ignore[method-assign]
        context = _SlashCompletionContext(
            mode="slash_arg",
            query="",
            line_prefix="/model ",
            line_end="/model ",
            replace_start=7,
            replace_end=7,
            command_name="model",
            arg_tokens=(),
            current_token="",
            ends_with_space=True,
        )

        matches = app._slash_argument_matches(context)
        selected_index = slash_controller_popup_helpers._selected_index_for_slash_update(
            app,
            context,
            matches,
            [],
        )

        self.assertEqual([item["usage"] for item in matches[:2]], ["gpt_54_mini", "gpt_54"])
        self.assertEqual(selected_index, 0)
