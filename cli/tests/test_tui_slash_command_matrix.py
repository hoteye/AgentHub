from __future__ import annotations

import re
import unittest

from cli.agent_cli.app import AgentCliApp, PromptComposer
from cli.agent_cli.models import PromptAttachment
from cli.agent_cli.slash_commands import slash_command_help_text, slash_command_specs
from cli.agent_cli.slash_commands_pure_helpers_runtime import SLASH_COMMAND_SPECS
from cli.agent_cli.slash_parser import parse_slash_invocation
from cli.agent_cli.ui.presentation import SUPPORTED_LOCALES
from cli.agent_cli.ui.presentation_messages_slash import (
    _SLASH_COMMAND_FR_DESCRIPTIONS,
    _SLASH_COMMAND_JA_DESCRIPTIONS,
    _SLASH_COMMAND_ZH_CN_DESCRIPTIONS,
    SLASH_MESSAGES,
)
from cli.agent_cli.ui.slash_completion_projection_helpers_runtime import _LOCALIZED_DESCRIPTIONS
from cli.agent_cli.ui.theme import builtin_theme_ids


class _CatalogRuntime:
    class _Agent:
        @staticmethod
        def provider_status() -> dict[str, str]:
            return {
                "provider_name": "openai",
                "provider_model": "gpt_54",
                "provider_ready": "true",
            }

    def __init__(self) -> None:
        self.agent = self._Agent()
        self.activity_callback = None
        self.turn_event_callback = None

    def slash_command_catalog(self) -> list[dict[str, str]]:
        return [
            {
                "name": spec.name,
                "usage": spec.usage,
                "description": spec.description,
            }
            for spec in slash_command_specs()
        ]

    def interrupt_active_run(self) -> dict[str, object]:
        return {"ok": False, "interrupted": False}


_EXPLICIT_SAMPLES: dict[str, str] = {
    "apply_patch": "/apply_patch demo_patch_payload",
    "agent_workflow": "/agent_workflow agent_1 steps 3",
    "approval_inbox": "/approval_inbox",
    "approve": "/approve approval_1 note ok",
    "auth": "/auth status provider openai",
    "background_benchmark": "/background_benchmark timeout-seconds 30 smoke",
    "background_smoke": "/background_smoke multi_llm timeout-seconds 30 smoke",
    "background_task_apply": "/background_task_apply task_1",
    "background_task_cancel": "/background_task_cancel task_1",
    "background_task_reject": "/background_task_reject task_1",
    "background_task_retry": "/background_task_retry task_1",
    "background_task_status": "/background_task_status task_1",
    "background_tasks": "/background_tasks limit 5",
    "background_teammate": "/background_teammate summarize provider openai model gpt_54 timeout-seconds 30",
    "background_worker_run_once": "/background_worker_run_once max-jobs 1 stale-after-seconds 30",
    "background_worker_start": "/background_worker_start max-jobs 1 poll-interval 1 stale-after-seconds 30",
    "background_worker_status": "/background_worker_status",
    "background_worker_stop": "/background_worker_stop force",
    "chat": "/chat",
    "browser": "/browser status",
    "close": "/close",
    "close_agent": "/close_agent agent_1",
    "click": "/click page_1 1",
    "compact": "/compact keep recent file edits and test failures",
    "connect": "/connect provider demo model demo-model user",
    "codex_compact": "/codex_compact",
    "codex_rollback": "/codex_rollback turns 1",
    "codex_thread": "/codex_thread thread_1",
    "codex_threads": "/codex_threads limit 5",
    "demo_ping": "/demo_ping hello",
    "exit": "/exit",
    "expert_review": '/expert_review \'{"task":"review slash command alignment"}\'',
    "find": "/find page_1 needle",
    "file_list": "/file_list src limit 5",
    "file_read": "/file_read README.md offset 1 limit 5",
    "file_search": "/file_search hello path src limit 5",
    "fork": "/fork",
    "fork_child": "/fork_child",
    "github_approval_approve": "/github_approval_approve approval-id 1 decided-by tester",
    "github_approval_list": "/github_approval_list status pending",
    "github_approval_reject": "/github_approval_reject approval-id 1 decided-by tester",
    "github_issue_add_labels": "/github_issue_add_labels repo demo/repo issue-number 1 labels bug",
    "github_issue_close": "/github_issue_close repo demo/repo issue-number 1",
    "github_issue_comment": "/github_issue_comment repo demo/repo issue-number 1 body smoke",
    "github_issue_create": "/github_issue_create repo demo/repo title smoke",
    "github_workflow_dispatch": "/github_workflow_dispatch repo demo/repo workflow-id ci.yml ref main",
    "glob_files": "/glob_files '**/*.md' path docs limit 5",
    "grep_files": "/grep_files hello path src limit 5",
    "help": "/help",
    "init": "/init yes",
    "lang": "/lang en",
    "llm": "/llm summarize slash coverage",
    "list_dir": "/list_dir src limit 5 depth 1",
    "mcp": "/mcp list",
    "mcp_auth": "/mcp_auth atlas token123",
    "mcp_auth_callback": "/mcp_auth_callback atlas token123",
    "mcp_auth_clear": "/mcp_auth_clear atlas",
    "mcp_disable": "/mcp_disable atlas",
    "mcp_enable": "/mcp_enable atlas",
    "mcp_inspect": "/mcp_inspect atlas",
    "mcp_reconnect": "/mcp_reconnect atlas",
    "memory": "/memory list",
    "master": "/master",
    "model": "/model gpt_54 high user",
    "models": "/models openai",
    "office_run": "/office_run read_docx_markdown demo.docx",
    "office_skills": "/office_skills",
    "open": "/open https://example.com line 1",
    "orchestrate": "/orchestrate align slash commands across handlers",
    "orchestrate_apply": "/orchestrate_apply run_1 card_1",
    "orchestrate_confirm": "/orchestrate_confirm align slash commands",
    "orchestrate_continue": "/orchestrate_continue run_1 max-passes 2 dispatch-ready true",
    "orchestrate_dispatch": "/orchestrate_dispatch run_1",
    "orchestrate_progress": "/orchestrate_progress run_1",
    "orchestrate_reject": "/orchestrate_reject run_1 card_1",
    "plan": "/plan",
    "plugin_disable": "/plugin_disable all",
    "plugin_enable": "/plugin_enable demo",
    "plugin_install": "/plugin_install /tmp/demo.zip replace scope project",
    "plugin_marketplace": "/plugin_marketplace list",
    "plugin_remove": "/plugin_remove demo",
    "plugin_reload": "/plugin_reload",
    "plugins": "/plugins",
    "preview": "/preview toggle",
    "providers": "/providers probe",
    "provider": "/provider openai",
    "read_file": "/read_file README.md offset 1 limit 5",
    "reasoner": "/reasoner",
    "recover_agent": "/recover_agent agent_1 action retry_step",
    "reject": "/reject approval_1 note no",
    "request_user_input": "/request_user_input smoke",
    "setup": "/setup",
    "resume": "/resume thread_1",
    "resume_agent": "/resume_agent agent_1",
    "resume_last": "/resume_last",
    "resume_path": "/resume_path /tmp/thread.jsonl",
    "runtime_config": "/runtime_config approval-policy never sandbox-mode read-only",
    "runtime_status": "/runtime_status",
    "send_input": "/send_input agent_1 hello interrupt",
    "shell": "/shell echo hi",
    "spawn_agent": '/spawn_agent \'{"task":"inspect slash handlers","role":"teammate","async":true}\'',
    "status": "/status",
    "tab_new": "/tab_new agenthub_python",
    "tab_rename": "/tab_rename Phase 11",
    "theme": f"/theme {builtin_theme_ids()[0]}",
    "threads": "/threads limit 5",
    "tools": "/tools",
    "update": "/update status",
    "update_plan": "/update_plan smoke",
    "view_image": "/view_image demo.png",
    "wait_agent": "/wait_agent agent_1 timeout-ms 250",
    "web_fetch": "/web_fetch https://example.com max-chars 1000",
    "web_search": "/web_search OpenAI docs limit 3",
    "workflows": "/workflows limit 5",
    "approvals": "/approvals status pending limit 5",
    "quit": "/quit",
}


def test_every_registered_slash_command_has_explicit_sample_and_parser_accepts_it() -> None:
    specs = slash_command_specs()
    missing = [spec.name for spec in specs if spec.name not in _EXPLICIT_SAMPLES]

    assert missing == []

    for spec in specs:
        sample = _EXPLICIT_SAMPLES[spec.name]
        invocation = parse_slash_invocation(sample, source="test")
        assert invocation.command_name == spec.name


def test_orchestration_slash_commands_are_visible_in_default_catalog_and_parse() -> None:
    specs = slash_command_specs()
    names = {spec.name for spec in specs}

    assert "orchestrate" in names
    assert "orchestrate_confirm" in names
    assert "orchestrate_progress" in names
    assert "orchestrate_continue" in names
    assert (
        parse_slash_invocation(
            "/orchestrate_confirm align slash commands",
            source="test",
        ).command_name
        == "orchestrate_confirm"
    )


def test_all_builtin_slash_commands_have_multilingual_description_overrides() -> None:
    expected = {spec.name for spec in SLASH_COMMAND_SPECS}

    assert set(_SLASH_COMMAND_ZH_CN_DESCRIPTIONS) == expected
    assert set(_SLASH_COMMAND_JA_DESCRIPTIONS) == expected
    assert set(_SLASH_COMMAND_FR_DESCRIPTIONS) == expected


def test_slash_i18n_catalog_has_complete_non_english_locale_values() -> None:
    localized_locales = tuple(locale for locale in SUPPORTED_LOCALES if locale != "en")
    bad = [
        (key, locale)
        for key, values in SLASH_MESSAGES.items()
        for locale in localized_locales
        if not str(values.get(locale) or "").strip()
    ]

    assert bad == []


def test_slash_argument_i18n_catalog_has_complete_locale_values() -> None:
    bad = [
        (key, locale)
        for key, values in _LOCALIZED_DESCRIPTIONS.items()
        for locale in SUPPORTED_LOCALES
        if not str(values.get(locale) or "").strip()
    ]

    assert bad == []


def test_slash_command_descriptions_do_not_render_empty_catalog_keys() -> None:
    for locale in (None, "en", "zh-CN", "ja", "fr"):
        bad = [
            spec.name
            for spec in slash_command_specs(locale=locale)
            if not spec.description or spec.description.startswith("slash.command.")
        ]

        assert bad == []


def test_slash_command_descriptions_are_localized_for_supported_locales() -> None:
    help_by_locale = {
        locale: next(
            spec.description for spec in slash_command_specs(locale=locale) if spec.name == "help"
        )
        for locale in ("en", "zh-CN", "ja", "fr")
    }

    assert help_by_locale["en"] == "show available slash commands"
    assert help_by_locale["zh-CN"] == "显示可用斜杠命令"
    assert help_by_locale["ja"] == "利用可能なスラッシュコマンドを表示"
    assert help_by_locale["fr"] == "afficher les commandes slash disponibles"


def test_english_slash_catalog_and_help_are_cjk_free() -> None:
    cjk = re.compile(r"[\u3400-\u9fff\u3040-\u30ff]")
    values: list[str] = []
    for locale in (None, "en", "en-US"):
        values.append(slash_command_help_text(locale=locale, include_advanced=True))
        for spec in slash_command_specs(locale=locale, discoverable_only=False):
            values.extend([spec.usage, spec.description])
    for mapping in _LOCALIZED_DESCRIPTIONS.values():
        values.append(str(mapping.get("en") or ""))

    bad = [value for value in values if cjk.search(value)]

    assert bad == []


def test_locale_aliases_are_used_for_slash_descriptions() -> None:
    descriptions = {
        locale: next(
            spec.description for spec in slash_command_specs(locale=locale) if spec.name == "help"
        )
        for locale in ("zh", "ja-JP", "fr-FR")
    }

    assert descriptions == {
        "zh": "显示可用斜杠命令",
        "ja-JP": "利用可能なスラッシュコマンドを表示",
        "fr-FR": "afficher les commandes slash disponibles",
    }


def _sample_command_text(name: str, usage: str) -> str:
    explicit = _EXPLICIT_SAMPLES.get(name)
    if explicit:
        return explicit
    if "<" in usage or "..." in usage:
        return f"/{name} smoke"
    return f"/{name}"


class TuiSlashCommandMatrixTest(unittest.IsolatedAsyncioTestCase):
    async def test_every_registered_slash_command_submits_from_tui(self) -> None:
        specs = slash_command_specs()
        runtime = _CatalogRuntime()
        app = AgentCliApp(runtime=runtime)
        enqueued: list[str] = []
        local_calls: list[tuple[str, str]] = []

        async def _enqueue(text: str, attachments: list[PromptAttachment], **kwargs) -> None:
            del attachments, kwargs
            enqueued.append(text)

        def _record_local(name: str):
            def _handler(arg_text: str) -> None:
                local_calls.append((name, arg_text))

            return _handler

        app._enqueue_runtime_request = _enqueue  # type: ignore[method-assign]
        app._handle_local_lang_command = _record_local("lang")  # type: ignore[method-assign]
        app._handle_local_theme_command = _record_local("theme")  # type: ignore[method-assign]

        def _handle_setup(arg_text: str) -> bool:
            local_calls.append(("setup", arg_text))
            return True

        app._handle_local_setup_command = _handle_setup  # type: ignore[method-assign]

        def _handle_plan(arg_text: str) -> bool:
            local_calls.append(("plan", arg_text))
            return True

        app._handle_local_plan_command = _handle_plan  # type: ignore[method-assign]

        def _handle_preview(arg_text: str) -> bool:
            local_calls.append(("preview", arg_text))
            return True

        app._handle_local_preview_command = _handle_preview  # type: ignore[method-assign]

        async with app.run_test() as pilot:
            await pilot.pause()

            catalog = app._slash_command_catalog()
            self.assertEqual(
                {item["name"] for item in catalog},
                {spec.name for spec in specs},
            )

            for spec in specs:
                sample = _sample_command_text(spec.name, spec.usage)
                before_enqueued = len(enqueued)
                before_local = len(local_calls)
                with self.subTest(command=spec.name, sample=sample):
                    app._set_prompt_text(sample)
                    await pilot.pause()
                    await app.action_submit_prompt()
                    await pilot.pause()
                    self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "")
                    if spec.name in {
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
                    }:
                        self.assertEqual(len(enqueued), before_enqueued)
                        if spec.name in {
                            "tab_rename",
                            "tab_new",
                            "approval_inbox",
                            "fork",
                            "master",
                            "fork_child",
                        }:
                            self.assertEqual(len(local_calls), before_local)
                            if spec.name == "tab_rename":
                                self.assertEqual(
                                    app._tab_manager.active_session.custom_label,
                                    "Phase 11",
                                )
                        else:
                            self.assertEqual(len(local_calls), before_local + 1)
                            self.assertEqual(local_calls[-1][0], spec.name)
                    else:
                        self.assertEqual(len(local_calls), before_local)
                        self.assertEqual(len(enqueued), before_enqueued + 1)
                        self.assertEqual(enqueued[-1], sample)

            self.assertEqual(app.prompt_count, len(specs))
