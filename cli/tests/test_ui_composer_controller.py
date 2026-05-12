from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli import app_event_helpers
from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.models import PromptResponse, ToolEvent
from cli.agent_cli.runtime import AgentCliRuntime


class ComposerControllerAsyncTest(unittest.IsolatedAsyncioTestCase):
    async def test_action_submit_prompt_normalizes_bare_exit_to_exit_command(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        enqueued: list[tuple[str, list[str]]] = []

        async def _enqueue(text: str, attachments: list[str]) -> None:
            enqueued.append((text, attachments))

        app._clear_quit_shortcut = lambda: None  # type: ignore[method-assign]
        app._flush_prompt_composer_burst = lambda: None  # type: ignore[method-assign]
        app._current_prompt_text = lambda: "exit"  # type: ignore[method-assign]
        app._prepare_prompt_submission = lambda display_text: (display_text, [])  # type: ignore[method-assign]
        app._clear_prompt_text = lambda: None  # type: ignore[method-assign]
        app._refresh_prompt_composer = lambda: None  # type: ignore[method-assign]
        app._record_prompt_history = lambda _text: None  # type: ignore[method-assign]
        app._write_user_prompt = lambda _text, attachments=None: None  # type: ignore[method-assign]
        app._handle_local_slash_command = lambda text, attachments=None: False  # type: ignore[method-assign]
        app._enqueue_runtime_request = _enqueue  # type: ignore[method-assign]
        app._focus_input = lambda: None  # type: ignore[method-assign]

        await app.action_submit_prompt()

        self.assertEqual(enqueued, [("/exit", [])])

    async def test_action_submit_prompt_enqueues_runtime_request_for_normal_prompt(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        events: list[object] = []
        history: list[str] = []
        prompts: list[tuple[str, list[str]]] = []
        enqueued: list[tuple[str, list[str]]] = []

        async def _enqueue(text: str, attachments: list[str]) -> None:
            enqueued.append((text, attachments))

        app._clear_quit_shortcut = lambda: events.append("clear_quit")  # type: ignore[method-assign]
        app._flush_prompt_composer_burst = lambda: events.append("flush")  # type: ignore[method-assign]
        app._current_prompt_text = lambda: "hello world"  # type: ignore[method-assign]
        app._prepare_prompt_submission = lambda display_text: ("hello world", ["a.txt"])  # type: ignore[method-assign]
        app._clear_prompt_text = lambda: events.append("clear_prompt")  # type: ignore[method-assign]
        app._refresh_prompt_composer = lambda: events.append("refresh")  # type: ignore[method-assign]
        app._record_prompt_history = history.append  # type: ignore[method-assign]
        app._write_user_prompt = lambda text, attachments=None: prompts.append(
            (text, list(attachments or []))
        )  # type: ignore[method-assign]
        app._handle_local_slash_command = lambda text, attachments=None: False  # type: ignore[method-assign]
        app._enqueue_runtime_request = _enqueue  # type: ignore[method-assign]
        app._focus_input = lambda: events.append("focus")  # type: ignore[method-assign]

        await app.action_submit_prompt()

        self.assertEqual(app.prompt_count, 1)
        self.assertEqual(history, ["hello world"])
        self.assertEqual(prompts, [("hello world", ["a.txt"])])
        self.assertEqual(enqueued, [("hello world", ["a.txt"])])
        self.assertEqual(events, ["clear_quit", "flush", "clear_prompt", "refresh", "focus"])

    async def test_action_submit_prompt_handles_local_slash_without_runtime_request(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        calls: list[object] = []

        async def _enqueue(_text: str, _attachments: list[str]) -> None:
            raise AssertionError("runtime request should not be enqueued for local slash commands")

        app._clear_quit_shortcut = lambda: calls.append("clear_quit")  # type: ignore[method-assign]
        app._flush_prompt_composer_burst = lambda: calls.append("flush")  # type: ignore[method-assign]
        app._current_prompt_text = lambda: "/theme light"  # type: ignore[method-assign]
        app._prepare_prompt_submission = lambda display_text: (display_text, [])  # type: ignore[method-assign]
        app._clear_prompt_text = lambda: calls.append("clear_prompt")  # type: ignore[method-assign]
        app._refresh_prompt_composer = lambda: calls.append("refresh")  # type: ignore[method-assign]
        app._record_prompt_history = lambda text: calls.append(("history", text))  # type: ignore[method-assign]
        app._write_user_prompt = lambda text, attachments=None: calls.append(
            ("user", text, list(attachments or []))
        )  # type: ignore[method-assign]
        app._handle_local_slash_command = lambda text, attachments=None: calls.append(("local", text)) or True  # type: ignore[method-assign]
        app._enqueue_runtime_request = _enqueue  # type: ignore[method-assign]
        app._focus_input = lambda: calls.append("focus")  # type: ignore[method-assign]

        await app.action_submit_prompt()

        self.assertEqual(app.prompt_count, 1)
        self.assertIn(("local", "/theme light"), calls)
        self.assertEqual(calls[-1], "focus")

    async def test_action_submit_prompt_records_runtime_slash_in_history(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        events: list[object] = []
        prompts: list[tuple[str, list[str]]] = []
        enqueued: list[tuple[str, list[str]]] = []

        async def _enqueue(text: str, attachments: list[str]) -> None:
            enqueued.append((text, attachments))

        app._clear_quit_shortcut = lambda: events.append("clear_quit")  # type: ignore[method-assign]
        app._flush_prompt_composer_burst = lambda: events.append("flush")  # type: ignore[method-assign]
        app._current_prompt_text = lambda: "/help"  # type: ignore[method-assign]
        app._prepare_prompt_submission = lambda display_text: (display_text, [])  # type: ignore[method-assign]
        app._clear_prompt_text = lambda: events.append("clear_prompt")  # type: ignore[method-assign]
        app._refresh_prompt_composer = lambda: events.append("refresh")  # type: ignore[method-assign]
        app._write_user_prompt = lambda text, attachments=None: prompts.append(
            (text, list(attachments or []))
        )  # type: ignore[method-assign]
        app._handle_local_slash_command = lambda text, attachments=None: False  # type: ignore[method-assign]
        app._enqueue_runtime_request = _enqueue  # type: ignore[method-assign]
        app._focus_input = lambda: events.append("focus")  # type: ignore[method-assign]

        await app.action_submit_prompt()

        self.assertEqual(app.prompt_count, 1)
        self.assertEqual(app._prompt_history.local_history, ["/help"])
        self.assertEqual(prompts, [("/help", [])])
        self.assertEqual(enqueued, [("/help", [])])
        self.assertEqual(events, ["clear_quit", "flush", "clear_prompt", "refresh", "focus"])

    async def test_action_submit_prompt_blocks_runtime_slash_while_busy(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        notices: list[str] = []
        events: list[object] = []

        async def _enqueue(_text: str, _attachments: list[str]) -> None:
            raise AssertionError("runtime slash commands should not enqueue while busy")

        app._clear_quit_shortcut = lambda: events.append("clear_quit")  # type: ignore[method-assign]
        app._flush_prompt_composer_burst = lambda: events.append("flush")  # type: ignore[method-assign]
        app._current_prompt_text = lambda: "/theme light"  # type: ignore[method-assign]
        app._prepare_prompt_submission = lambda display_text: (display_text, [])  # type: ignore[method-assign]
        app._has_pending_runtime_work = lambda: True  # type: ignore[method-assign]
        app._write_system_notice = notices.append  # type: ignore[method-assign]
        app._clear_prompt_text = lambda: events.append("clear_prompt")  # type: ignore[method-assign]
        app._refresh_prompt_composer = lambda: events.append("refresh")  # type: ignore[method-assign]
        app._write_user_prompt = lambda _text, attachments=None: events.append(
            ("user", attachments)
        )  # type: ignore[method-assign]
        app._handle_local_slash_command = lambda text, attachments=None: events.append(("local", text)) or True  # type: ignore[method-assign]
        app._enqueue_runtime_request = _enqueue  # type: ignore[method-assign]
        app._focus_input = lambda: events.append("focus")  # type: ignore[method-assign]

        await app.action_submit_prompt()

        self.assertEqual(notices, [app._BUSY_SLASH_COMMAND_NOTICE])
        self.assertEqual(app.prompt_count, 0)
        self.assertEqual(events, ["clear_quit", "flush", "focus"])

    async def test_action_submit_prompt_allows_slash_after_interrupt_request(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        notices: list[str] = []
        events: list[object] = []

        async def _enqueue(_text: str, _attachments: list[str]) -> None:
            raise AssertionError("local slash command should run without enqueueing")

        app._clear_quit_shortcut = lambda: events.append("clear_quit")  # type: ignore[method-assign]
        app._flush_prompt_composer_burst = lambda: events.append("flush")  # type: ignore[method-assign]
        app._current_prompt_text = lambda: "/theme light"  # type: ignore[method-assign]
        app._prepare_prompt_submission = lambda display_text: (display_text, [])  # type: ignore[method-assign]
        app._has_pending_runtime_work = lambda: True  # type: ignore[method-assign]
        app._live_turn_interrupt_requested = True
        app._write_system_notice = notices.append  # type: ignore[method-assign]
        app._clear_prompt_text = lambda: events.append("clear_prompt")  # type: ignore[method-assign]
        app._refresh_prompt_composer = lambda: events.append("refresh")  # type: ignore[method-assign]
        app._record_prompt_history = lambda _text: None  # type: ignore[method-assign]
        app._write_user_prompt = lambda _text, attachments=None: events.append(
            ("user", attachments)
        )  # type: ignore[method-assign]
        app._handle_local_slash_command = (
            lambda text, attachments=None: events.append(("local", text, attachments)) or True
        )  # type: ignore[method-assign]
        app._enqueue_runtime_request = _enqueue  # type: ignore[method-assign]
        app._focus_input = lambda: events.append("focus")  # type: ignore[method-assign]

        await app.action_submit_prompt()

        self.assertEqual(notices, [])
        self.assertEqual(app.prompt_count, 1)
        self.assertEqual(
            events,
            [
                "clear_quit",
                "flush",
                "clear_prompt",
                "refresh",
                ("user", []),
                ("local", "/theme light", []),
                "focus",
            ],
        )

    async def test_action_submit_prompt_allows_busy_slash_when_policy_allows(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        notices: list[str] = []
        events: list[object] = []
        enqueued: list[tuple[str, list[str]]] = []

        async def _enqueue(text: str, attachments: list[str]) -> None:
            enqueued.append((text, attachments))

        app._clear_quit_shortcut = lambda: events.append("clear_quit")  # type: ignore[method-assign]
        app._flush_prompt_composer_burst = lambda: events.append("flush")  # type: ignore[method-assign]
        app._current_prompt_text = lambda: "/help"  # type: ignore[method-assign]
        app._prepare_prompt_submission = lambda display_text: (display_text, [])  # type: ignore[method-assign]
        app._has_pending_runtime_work = lambda: True  # type: ignore[method-assign]
        app._write_system_notice = notices.append  # type: ignore[method-assign]
        app._clear_prompt_text = lambda: events.append("clear_prompt")  # type: ignore[method-assign]
        app._refresh_prompt_composer = lambda: events.append("refresh")  # type: ignore[method-assign]
        app._write_user_prompt = lambda _text, attachments=None: events.append(
            ("user", attachments)
        )  # type: ignore[method-assign]
        app._handle_local_slash_command = lambda _text, attachments=None: False  # type: ignore[method-assign]
        app._enqueue_runtime_request = _enqueue  # type: ignore[method-assign]
        app._focus_input = lambda: events.append("focus")  # type: ignore[method-assign]

        await app.action_submit_prompt()

        self.assertEqual(notices, [])
        self.assertEqual(app.prompt_count, 1)
        self.assertEqual(enqueued, [("/help", [])])
        self.assertEqual(
            events, ["clear_quit", "flush", "clear_prompt", "refresh", ("user", []), "focus"]
        )

    async def test_action_submit_prompt_rejects_oversized_input(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app.MAX_USER_INPUT_TEXT_CHARS = 4
        notices: list[str] = []
        calls: list[str] = []

        app._clear_quit_shortcut = lambda: calls.append("clear_quit")  # type: ignore[method-assign]
        app._flush_prompt_composer_burst = lambda: calls.append("flush")  # type: ignore[method-assign]
        app._current_prompt_text = lambda: "hello"  # type: ignore[method-assign]
        app._prepare_prompt_submission = lambda display_text: ("hello", [])  # type: ignore[method-assign]
        app._write_system_notice = notices.append  # type: ignore[method-assign]
        app._focus_input = lambda: calls.append("focus")  # type: ignore[method-assign]
        app._clear_prompt_text = lambda: calls.append("clear_prompt")  # type: ignore[method-assign]
        app._refresh_prompt_composer = lambda: calls.append("refresh")  # type: ignore[method-assign]

        await app.action_submit_prompt()

        self.assertEqual(notices, [app._user_input_too_large_message(5)])
        self.assertEqual(app.prompt_count, 0)
        self.assertEqual(calls, ["clear_quit", "flush", "focus"])

    async def test_action_submit_prompt_queues_while_busy_non_slash_without_steer(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        events: list[object] = []
        prompts: list[tuple[str, list[str]]] = []
        enqueued: list[tuple[str, list[str], dict[str, object]]] = []

        async def _enqueue(text: str, attachments: list[str], **kwargs: object) -> None:
            enqueued.append((text, attachments, dict(kwargs)))

        def _raise_if_steer_called(_text: str, *, attachments=None):
            del attachments
            raise AssertionError("busy prompt submission should queue instead of steering")

        app._clear_quit_shortcut = lambda: events.append("clear_quit")  # type: ignore[method-assign]
        app._flush_prompt_composer_burst = lambda: events.append("flush")  # type: ignore[method-assign]
        app._current_prompt_text = lambda: "follow up"  # type: ignore[method-assign]
        app._prepare_prompt_submission = lambda display_text: (display_text, ["a.txt"])  # type: ignore[method-assign]
        app._has_pending_runtime_work = lambda: True  # type: ignore[method-assign]
        app._busy = True
        app.runtime.steer_active_run = _raise_if_steer_called  # type: ignore[method-assign]
        app._clear_prompt_text = lambda: events.append("clear_prompt")  # type: ignore[method-assign]
        app._refresh_prompt_composer = lambda: events.append("refresh")  # type: ignore[method-assign]
        app._record_prompt_history = lambda _text: None  # type: ignore[method-assign]
        app._write_user_prompt = lambda text, attachments=None: prompts.append(
            (text, list(attachments or []))
        )  # type: ignore[method-assign]
        app._handle_local_slash_command = lambda _text, attachments=None: False  # type: ignore[method-assign]
        app._enqueue_runtime_request = _enqueue  # type: ignore[method-assign]
        app._focus_input = lambda: events.append("focus")  # type: ignore[method-assign]

        await app.action_submit_prompt()

        self.assertEqual(
            enqueued,
            [
                (
                    "follow up",
                    ["a.txt"],
                    {
                        "display_text": "follow up",
                        "display_attachments": ["a.txt"],
                        "priority": "later",
                    },
                )
            ],
        )
        self.assertEqual(prompts, [])
        self.assertEqual(events, ["clear_quit", "flush", "clear_prompt", "refresh", "focus"])
        self.assertEqual(app.prompt_count, 1)

    async def test_action_submit_prompt_busy_queue_does_not_emit_steer_fallback_notice(
        self,
    ) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        notices: list[str] = []
        events: list[object] = []
        enqueued: list[tuple[str, list[str], dict[str, object]]] = []

        async def _enqueue(text: str, attachments: list[str], **kwargs: object) -> None:
            enqueued.append((text, attachments, dict(kwargs)))

        def _raise_if_steer_called(_text: str, *, attachments=None):
            del attachments
            raise AssertionError("busy prompt submission should queue instead of steering")

        app._clear_quit_shortcut = lambda: events.append("clear_quit")  # type: ignore[method-assign]
        app._flush_prompt_composer_burst = lambda: events.append("flush")  # type: ignore[method-assign]
        app._current_prompt_text = lambda: "fallback steer"  # type: ignore[method-assign]
        app._prepare_prompt_submission = lambda display_text: (display_text, [])  # type: ignore[method-assign]
        app._has_pending_runtime_work = lambda: True  # type: ignore[method-assign]
        app._busy = True
        app.runtime.steer_active_run = _raise_if_steer_called  # type: ignore[method-assign]
        app._write_system_notice = notices.append  # type: ignore[method-assign]
        app._clear_prompt_text = lambda: events.append("clear_prompt")  # type: ignore[method-assign]
        app._refresh_prompt_composer = lambda: events.append("refresh")  # type: ignore[method-assign]
        app._record_prompt_history = lambda _text: None  # type: ignore[method-assign]
        app._write_user_prompt = lambda _text, attachments=None: events.append(
            ("user", list(attachments or []))
        )  # type: ignore[method-assign]
        app._handle_local_slash_command = lambda _text, attachments=None: False  # type: ignore[method-assign]
        app._enqueue_runtime_request = _enqueue  # type: ignore[method-assign]
        app._focus_input = lambda: events.append("focus")  # type: ignore[method-assign]

        await app.action_submit_prompt()

        self.assertEqual(notices, [])
        self.assertEqual(
            enqueued,
            [
                (
                    "fallback steer",
                    [],
                    {
                        "display_text": "fallback steer",
                        "display_attachments": [],
                        "priority": "later",
                    },
                )
            ],
        )
        self.assertEqual(events, ["clear_quit", "flush", "clear_prompt", "refresh", "focus"])
        self.assertEqual(app.prompt_count, 1)

    async def test_action_submit_prompt_steers_when_runtime_supports_pending_steer(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        events: list[object] = []
        prompts: list[tuple[str, list[str]]] = []
        enqueued: list[tuple[str, list[str], dict[str, object]]] = []
        steers: list[tuple[str, list[str]]] = []

        async def _enqueue(text: str, attachments: list[str], **kwargs: object) -> None:
            enqueued.append((text, attachments, dict(kwargs)))

        def _steer(text: str, *, attachments=None):
            steers.append((text, list(attachments or [])))
            return {"accepted": True, "fallback_queue": False, "reason": "accepted"}

        app._clear_quit_shortcut = lambda: events.append("clear_quit")  # type: ignore[method-assign]
        app._flush_prompt_composer_burst = lambda: events.append("flush")  # type: ignore[method-assign]
        app._current_prompt_text = lambda: "same turn steer"  # type: ignore[method-assign]
        app._prepare_prompt_submission = lambda display_text: (display_text, ["a.txt"])  # type: ignore[method-assign]
        app._has_pending_runtime_work = lambda: True  # type: ignore[method-assign]
        app._busy = True
        app.runtime.pending_steer_supported = lambda: True  # type: ignore[method-assign]
        app.runtime.steer_active_run = _steer  # type: ignore[method-assign]
        app._clear_prompt_text = lambda: events.append("clear_prompt")  # type: ignore[method-assign]
        app._refresh_prompt_composer = lambda: events.append("refresh")  # type: ignore[method-assign]
        app._record_prompt_history = lambda text: events.append(("history", text))  # type: ignore[method-assign]
        app._write_user_prompt = lambda text, attachments=None: prompts.append(
            (text, list(attachments or []))
        )  # type: ignore[method-assign]
        app._handle_local_slash_command = lambda _text, attachments=None: False  # type: ignore[method-assign]
        app._enqueue_runtime_request = _enqueue  # type: ignore[method-assign]
        app._focus_input = lambda: events.append("focus")  # type: ignore[method-assign]

        await app.action_submit_prompt()

        self.assertEqual(steers, [("same turn steer", ["a.txt"])])
        self.assertEqual(prompts, [("same turn steer", ["a.txt"])])
        self.assertEqual(enqueued, [])
        self.assertEqual(app.prompt_count, 1)
        self.assertEqual(
            events,
            [
                "clear_quit",
                "flush",
                "clear_prompt",
                "refresh",
                ("history", "same turn steer"),
                "focus",
            ],
        )

    async def test_action_submit_prompt_queues_when_pending_steer_falls_back(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        events: list[object] = []
        enqueued: list[tuple[str, list[str], dict[str, object]]] = []

        async def _enqueue(text: str, attachments: list[str], **kwargs: object) -> None:
            enqueued.append((text, attachments, dict(kwargs)))

        app._clear_quit_shortcut = lambda: events.append("clear_quit")  # type: ignore[method-assign]
        app._flush_prompt_composer_burst = lambda: events.append("flush")  # type: ignore[method-assign]
        app._current_prompt_text = lambda: "fallback steer"  # type: ignore[method-assign]
        app._prepare_prompt_submission = lambda display_text: (display_text, [])  # type: ignore[method-assign]
        app._has_pending_runtime_work = lambda: True  # type: ignore[method-assign]
        app._busy = True
        app.runtime.pending_steer_supported = lambda: True  # type: ignore[method-assign]
        app.runtime.steer_active_run = lambda text, attachments=None: {  # type: ignore[method-assign]
            "accepted": False,
            "fallback_queue": True,
            "reason": "active_turn_not_steerable",
        }
        app._clear_prompt_text = lambda: events.append("clear_prompt")  # type: ignore[method-assign]
        app._refresh_prompt_composer = lambda: events.append("refresh")  # type: ignore[method-assign]
        app._record_prompt_history = lambda _text: None  # type: ignore[method-assign]
        app._write_user_prompt = lambda _text, attachments=None: events.append(
            ("user", list(attachments or []))
        )  # type: ignore[method-assign]
        app._handle_local_slash_command = lambda _text, attachments=None: False  # type: ignore[method-assign]
        app._enqueue_runtime_request = _enqueue  # type: ignore[method-assign]
        app._focus_input = lambda: events.append("focus")  # type: ignore[method-assign]

        await app.action_submit_prompt()

        self.assertEqual(
            enqueued,
            [
                (
                    "fallback steer",
                    [],
                    {
                        "display_text": "fallback steer",
                        "display_attachments": [],
                        "priority": "later",
                    },
                )
            ],
        )
        self.assertEqual(events, ["clear_quit", "flush", "clear_prompt", "refresh", "focus"])

    async def test_action_submit_prompt_after_interrupt_enqueues_without_steer_notice(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        notices: list[str] = []
        events: list[object] = []
        enqueued: list[tuple[str, list[str]]] = []

        async def _enqueue(text: str, attachments: list[str]) -> None:
            enqueued.append((text, attachments))

        def _raise_if_steer_called(_text: str, *, attachments=None):
            del attachments
            raise AssertionError("post-interrupt follow-up should not use busy steering")

        app._clear_quit_shortcut = lambda: events.append("clear_quit")  # type: ignore[method-assign]
        app._flush_prompt_composer_burst = lambda: events.append("flush")  # type: ignore[method-assign]
        app._current_prompt_text = lambda: "use gui directory under repo root"  # type: ignore[method-assign]
        app._prepare_prompt_submission = lambda display_text: (display_text, [])  # type: ignore[method-assign]
        app._has_pending_runtime_work = lambda: True  # type: ignore[method-assign]
        app._busy = False
        app._live_turn_interrupt_requested = True
        app.runtime.steer_active_run = _raise_if_steer_called  # type: ignore[method-assign]
        app._write_system_notice = notices.append  # type: ignore[method-assign]
        app._clear_prompt_text = lambda: events.append("clear_prompt")  # type: ignore[method-assign]
        app._refresh_prompt_composer = lambda: events.append("refresh")  # type: ignore[method-assign]
        app._record_prompt_history = lambda _text: None  # type: ignore[method-assign]
        app._write_user_prompt = lambda _text, attachments=None: events.append(
            ("user", list(attachments or []))
        )  # type: ignore[method-assign]
        app._handle_local_slash_command = lambda _text, attachments=None: False  # type: ignore[method-assign]
        app._enqueue_runtime_request = _enqueue  # type: ignore[method-assign]
        app._focus_input = lambda: events.append("focus")  # type: ignore[method-assign]

        await app.action_submit_prompt()

        self.assertEqual(notices, [])
        self.assertEqual(enqueued, [("use gui directory under repo root", [])])
        self.assertEqual(
            events, ["clear_quit", "flush", "clear_prompt", "refresh", ("user", []), "focus"]
        )
        self.assertEqual(app.prompt_count, 1)

    async def test_action_queue_prompt_enqueues_while_busy_without_steer(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        events: list[object] = []
        enqueued: list[tuple[str, list[str], dict[str, object]]] = []

        async def _enqueue(text: str, attachments: list[str], **kwargs: object) -> None:
            enqueued.append((text, attachments, dict(kwargs)))

        def _raise_if_steer_called(_text: str, *, attachments=None):
            del attachments
            raise AssertionError("queue mode should not call steer")

        app._clear_quit_shortcut = lambda: events.append("clear_quit")  # type: ignore[method-assign]
        app._flush_prompt_composer_burst = lambda: events.append("flush")  # type: ignore[method-assign]
        app._current_prompt_text = lambda: "queue only"  # type: ignore[method-assign]
        app._prepare_prompt_submission = lambda display_text: (display_text, [])  # type: ignore[method-assign]
        app._has_pending_runtime_work = lambda: True  # type: ignore[method-assign]
        app.runtime.steer_active_run = _raise_if_steer_called  # type: ignore[method-assign]
        app._clear_prompt_text = lambda: events.append("clear_prompt")  # type: ignore[method-assign]
        app._refresh_prompt_composer = lambda: events.append("refresh")  # type: ignore[method-assign]
        app._record_prompt_history = lambda _text: None  # type: ignore[method-assign]
        app._write_user_prompt = lambda _text, attachments=None: events.append(
            ("user", list(attachments or []))
        )  # type: ignore[method-assign]
        app._handle_local_slash_command = lambda _text, attachments=None: False  # type: ignore[method-assign]
        app._enqueue_runtime_request = _enqueue  # type: ignore[method-assign]
        app._focus_input = lambda: events.append("focus")  # type: ignore[method-assign]

        await app.action_queue_prompt()

        self.assertEqual(
            enqueued,
            [
                (
                    "queue only",
                    [],
                    {
                        "display_text": "queue only",
                        "display_attachments": [],
                        "priority": "later",
                    },
                )
            ],
        )
        self.assertEqual(events, ["clear_quit", "flush", "clear_prompt", "refresh", "focus"])
        self.assertEqual(app.prompt_count, 1)


class ComposerControllerTest(unittest.TestCase):
    def test_queue_prompt_actionable_respects_busy_slash_policy(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app._has_pending_runtime_work = lambda: True  # type: ignore[method-assign]

        self.assertTrue(app._queue_prompt_actionable("normal prompt"))
        self.assertTrue(app._queue_prompt_actionable("/help"))
        self.assertFalse(app._queue_prompt_actionable("/theme light"))
        self.assertFalse(app._queue_prompt_actionable(""))

    def test_restore_transcript_from_runtime_history_uses_stored_visible_text_fields(self) -> None:
        runtime = AgentCliRuntime()
        runtime.history_turns = [
            {
                "user_text": "resume me",
                "assistant_text": "done",
                "turn_events": [
                    {"type": "turn.started"},
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_1",
                            "type": "agent_message",
                            "text": "done",
                            "phase": "final_answer",
                        },
                    },
                    {"type": "turn.completed"},
                ],
            }
        ]
        app = AgentCliApp(runtime=runtime)
        calls: list[object] = []

        app._begin_activity_capture = lambda: calls.append("begin")  # type: ignore[method-assign]
        app._write_user_prompt = lambda text, attachments=None: calls.append(
            ("user", text, list(attachments or []))
        )  # type: ignore[method-assign]
        app._write_assistant_reply = lambda text: calls.append(("assistant", text))  # type: ignore[method-assign]

        app._restore_transcript_from_runtime_history()

        self.assertEqual(app.prompt_count, 1)
        self.assertEqual(
            calls,
            [
                "begin",
                ("user", "resume me", []),
                ("assistant", "done"),
            ],
        )

    def test_restore_transcript_from_runtime_history_falls_back_to_text_fields(self) -> None:
        runtime = AgentCliRuntime()
        runtime.history_turns = [
            {
                "user_text": "resume user",
                "assistant_text": "resume assistant",
                "turn_events": [],
            }
        ]
        app = AgentCliApp(runtime=runtime)
        calls: list[object] = []

        app._begin_activity_capture = lambda: calls.append("begin")  # type: ignore[method-assign]
        app._write_user_prompt = lambda text, attachments=None: calls.append(
            ("user", text, list(attachments or []))
        )  # type: ignore[method-assign]
        app._write_assistant_reply = lambda text: calls.append(("assistant", text))  # type: ignore[method-assign]

        app._restore_transcript_from_runtime_history()

        self.assertEqual(app.prompt_count, 1)
        self.assertEqual(
            calls,
            [
                "begin",
                ("user", "resume user", []),
                ("assistant", "resume assistant"),
            ],
        )

    def test_restore_transcript_from_runtime_history_hides_exit_internal_response(self) -> None:
        runtime = AgentCliRuntime()
        runtime.history_turns = [
            {
                "user_text": "/exit",
                "assistant_text": "exiting session\nthread_id=thread_exit_123",
                "turn_events": [
                    {"type": "turn.started"},
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_0",
                            "type": "mcp_tool_call",
                            "tool": "app_exit_requested",
                            "status": "completed",
                        },
                    },
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_1",
                            "type": "agent_message",
                            "text": "exiting session\nthread_id=thread_exit_123",
                            "phase": "final_answer",
                        },
                    },
                    {"type": "turn.completed"},
                ],
            }
        ]
        app = AgentCliApp(runtime=runtime)
        calls: list[object] = []

        app._begin_activity_capture = lambda: calls.append("begin")  # type: ignore[method-assign]
        app._render_canonical_turn_event_backfill = lambda events: calls.append(
            ("events", list(events))
        )  # type: ignore[method-assign]
        app._write_user_prompt = lambda text, attachments=None: calls.append(
            ("user", text, list(attachments or []))
        )  # type: ignore[method-assign]
        app._write_assistant_reply = lambda text: calls.append(("assistant", text))  # type: ignore[method-assign]

        app._restore_transcript_from_runtime_history()

        self.assertEqual(
            calls,
            [
                "begin",
                ("user", "/exit", []),
            ],
        )

    def test_render_response_hides_exit_internal_response(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        app.prompt_count = 1
        calls: list[object] = []
        response = PromptResponse(
            user_text="/exit",
            assistant_text=(
                "exiting session\n"
                "thread_id=thread_exit_123\n"
                "resume_command=agenthub resume thread_exit_123"
            ),
            tool_events=[
                ToolEvent(
                    name="app_exit_requested",
                    ok=True,
                    summary="exit requested",
                    payload={
                        "thread_id": "thread_exit_123",
                        "resume_command": "agenthub resume thread_exit_123",
                    },
                )
            ],
            turn_events=[
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_0",
                        "type": "mcp_tool_call",
                        "tool": "app_exit_requested",
                        "status": "completed",
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_1",
                        "type": "agent_message",
                        "text": "exiting session\nthread_id=thread_exit_123",
                        "phase": "final_answer",
                    },
                },
                {"type": "turn.completed"},
            ],
        )

        app._status_from_response = lambda _response: {"status": "idle"}  # type: ignore[method-assign]
        app._update_status = lambda status: calls.append(("status", dict(status)))  # type: ignore[method-assign]
        app._focus_input = lambda: calls.append("focus")  # type: ignore[method-assign]
        app._render_canonical_turn_event_backfill = lambda events: calls.append(
            ("events", list(events))
        )  # type: ignore[method-assign]
        app._write_assistant_reply = lambda text: calls.append(("assistant", text))  # type: ignore[method-assign]

        app._render_response(response)

        self.assertEqual(calls, [("status", {"status": "idle", "prompt_count": "1"}), "focus"])

    def test_on_mount_restores_runtime_history_automatically(self) -> None:
        runtime = AgentCliRuntime()
        runtime.history_turns = [
            {
                "user_text": "读取 README.md 的前3行",
                "assistant_text": "README.md 的前 3 行是：\n1. # AgentHub\n2. \n3. 示例",
                "commentary_text": "我先读取 README.md。",
                "turn_events": [
                    {"type": "turn.started"},
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "tool_1",
                            "type": "function_call",
                            "name": "file_read",
                            "arguments": {"path": "README.md", "limit": 3},
                        },
                    },
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "msg_1",
                            "type": "agent_message",
                            "text": "我先读取 README.md。",
                            "phase": "commentary",
                        },
                    },
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "msg_2",
                            "type": "agent_message",
                            "text": "README.md 的前 3 行是：\n1. # AgentHub\n2. \n3. 示例",
                            "phase": "final_answer",
                        },
                    },
                    {"type": "turn.completed"},
                ],
            }
        ]
        app = AgentCliApp(runtime=runtime)
        calls: list[object] = []

        class _FakeTask:
            def done(self) -> bool:
                return False

        def _fake_create_task(coro, *args, **kwargs):
            coro.close()
            return _FakeTask()

        app._install_local_request_user_input_handler = lambda: calls.append("install")  # type: ignore[method-assign]
        app._apply_layout_state = lambda width: calls.append(("layout", width))  # type: ignore[method-assign]
        app._write_user_prompt = lambda text, attachments=None: calls.append(
            ("user", text, list(attachments or []))
        )  # type: ignore[method-assign]
        app._write_assistant_reply = lambda text: calls.append(("assistant", text))  # type: ignore[method-assign]
        app._write_commentary_reply = lambda text: calls.append(("commentary", text))  # type: ignore[method-assign]
        app._render_canonical_turn_event_backfill = lambda events: calls.append(
            ("events", list(events))
        )  # type: ignore[method-assign]
        app._begin_activity_capture = lambda: calls.append("begin")  # type: ignore[method-assign]
        app._focus_input = lambda: calls.append("focus")  # type: ignore[method-assign]
        app.call_after_refresh = lambda callback: calls.append(("after_refresh", callback.__name__))  # type: ignore[method-assign]
        app.set_timer = lambda delay, callback: calls.append(("timer", delay, callback.__name__))  # type: ignore[method-assign]
        app.set_interval = (
            lambda delay, callback: calls.append(("interval", delay, callback.__name__))
            or SimpleNamespace()
        )  # type: ignore[method-assign]

        with patch.object(asyncio, "create_task", side_effect=_fake_create_task) as create_task:
            app.on_mount()

        create_task.assert_called_once()
        self.assertEqual(
            calls,
            [
                "install",
                ("interval", 2.0, "_capture_active_scroll"),
                ("layout", 80),
                "begin",
                ("user", "读取 README.md 的前3行", []),
                ("assistant", "README.md 的前 3 行是：\n1. # AgentHub\n2. \n3. 示例"),
                "focus",
                ("after_refresh", "_stabilize_initial_frame"),
                ("timer", 0.05, "_stabilize_initial_frame"),
                ("timer", 0.2, "_stabilize_initial_frame"),
                ("interval", 0.02, "_flush_prompt_composer_burst_if_due"),
                ("interval", 0.032, "_refresh_dynamic_hint"),
            ],
        )

    def test_on_mount_writes_setup_notice_when_provider_is_unconfigured(self) -> None:
        class _Agent:
            @staticmethod
            def provider_status() -> dict[str, str]:
                return {
                    "provider_ready": "false",
                    "provider_name": "-",
                    "provider_source": "not_configured",
                }

        app = AgentCliApp(runtime=AgentCliRuntime(agent=_Agent()))
        calls: list[object] = []

        class _FakeTask:
            def done(self) -> bool:
                return False

        def _fake_create_task(coro, *args, **kwargs):
            del args, kwargs
            coro.close()
            return _FakeTask()

        app._install_local_request_user_input_handler = lambda: calls.append("install")  # type: ignore[method-assign]
        app._apply_layout_state = lambda width: calls.append(("layout", width))  # type: ignore[method-assign]
        app._restore_transcript_from_runtime_history = lambda: calls.append("restore")  # type: ignore[method-assign]
        app._write_system_notice = lambda text: calls.append(("notice", text))  # type: ignore[method-assign]
        app._focus_input = lambda: calls.append("focus")  # type: ignore[method-assign]
        app.call_after_refresh = lambda callback: calls.append(("after_refresh", callback.__name__))  # type: ignore[method-assign]
        app.set_timer = lambda delay, callback: calls.append(("timer", delay, callback.__name__))  # type: ignore[method-assign]
        app.set_interval = (
            lambda delay, callback: calls.append(("interval", delay, callback.__name__))
            or SimpleNamespace()
        )  # type: ignore[method-assign]

        with patch.object(asyncio, "create_task", side_effect=_fake_create_task):
            app.on_mount()

        self.assertIn(
            ("notice", "No provider configured. Run /setup to add API key and optional base URL."),
            calls,
        )

    def test_on_mount_skips_setup_notice_for_fallback_runtime(self) -> None:
        class _Agent:
            @staticmethod
            def provider_status() -> dict[str, str]:
                return {
                    "provider_ready": "false",
                    "provider_name": "fallback",
                    "provider_source": "fallback",
                }

        app = AgentCliApp(runtime=AgentCliRuntime(agent=_Agent()))
        notices: list[str] = []

        class _FakeTask:
            def done(self) -> bool:
                return False

        def _fake_create_task(coro, *args, **kwargs):
            del args, kwargs
            coro.close()
            return _FakeTask()

        app._install_local_request_user_input_handler = lambda: None  # type: ignore[method-assign]
        app._apply_layout_state = lambda width: None  # type: ignore[method-assign]
        app._restore_transcript_from_runtime_history = lambda: None  # type: ignore[method-assign]
        app._write_system_notice = notices.append  # type: ignore[method-assign]
        app._focus_input = lambda: None  # type: ignore[method-assign]
        app.call_after_refresh = lambda callback: None  # type: ignore[method-assign]
        app.set_timer = lambda delay, callback: None  # type: ignore[method-assign]
        app.set_interval = lambda delay, callback: SimpleNamespace()  # type: ignore[method-assign]

        with patch.object(asyncio, "create_task", side_effect=_fake_create_task):
            app.on_mount()

        self.assertEqual(notices, [])

    def test_startup_setup_required_includes_auth_blocked_provider(self) -> None:
        self.assertTrue(
            app_event_helpers._startup_setup_required(
                {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_source": "user_home",
                    "provider_status_state": "auth_blocked",
                }
            )
        )
        self.assertFalse(
            app_event_helpers._startup_setup_required(
                {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_source": "user_home",
                    "provider_status_state": "ready",
                    "provider_auth_ready": "true",
                }
            )
        )

    def test_startup_setup_required_includes_hard_unavailable_provider(self) -> None:
        self.assertTrue(
            app_event_helpers._startup_setup_required(
                {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_source": "user_home",
                    "provider_auth_ready": "true",
                    "provider_status_state": "hard_unavailable",
                    "provider_status_reason": "http_402",
                }
            )
        )
        self.assertTrue(
            app_event_helpers._startup_setup_required(
                {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_source": "user_home",
                    "provider_auth_ready": "true",
                    "provider_hard_unavailable": "true",
                }
            )
        )

    def test_startup_setup_overlay_submits_runtime_setup_command(self) -> None:
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

        def _present_overlay(*, payload, on_submit, **kwargs):
            del kwargs
            self.assertEqual(payload["provider"], "openai")
            self.assertEqual(payload["base_url"], "https://example.test/v1")
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
            shown = app_event_helpers._present_startup_setup_overlay(
                app,
                {"provider": "openai", "base_url": "https://example.test/v1"},
            )

        self.assertTrue(shown)
        self.assertEqual(notices, ["Running setup..."])
        self.assertEqual(
            scheduled,
            ["/setup provider openai api-key sk-openai user base-url https://example.test/v1"],
        )

    def test_on_mount_writes_cached_update_notice_and_schedules_background_check(self) -> None:
        class _Agent:
            @staticmethod
            def provider_status() -> dict[str, str]:
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_source": "user_home",
                    "provider_auth_ready": "true",
                    "provider_status_state": "ready",
                }

        app = AgentCliApp(runtime=AgentCliRuntime(agent=_Agent()))
        notices: list[str] = []
        scheduled: list[str] = []

        class _FakeTask:
            def done(self) -> bool:
                return False

        def _fake_create_task(coro, *args, **kwargs):
            del args, kwargs
            coro.close()
            return _FakeTask()

        app._install_local_request_user_input_handler = lambda: None  # type: ignore[method-assign]
        app._apply_layout_state = lambda width: None  # type: ignore[method-assign]
        app._restore_transcript_from_runtime_history = lambda: None  # type: ignore[method-assign]
        app._write_system_notice = notices.append  # type: ignore[method-assign]
        app._focus_input = lambda: None  # type: ignore[method-assign]
        app.call_after_refresh = lambda callback: scheduled.append(callback.__name__)  # type: ignore[method-assign]
        app.set_timer = lambda delay, callback: None  # type: ignore[method-assign]
        app.set_interval = lambda delay, callback: SimpleNamespace()  # type: ignore[method-assign]

        with (
            patch.object(asyncio, "create_task", side_effect=_fake_create_task),
            patch(
                "cli.agent_cli.update_runtime.cached_update_notice",
                return_value="AgentHub update available: 0.1.0 -> 0.2.0. Run /update status.",
            ),
            patch(
                "cli.agent_cli.update_runtime.schedule_background_update_check",
                return_value=True,
            ) as schedule,
        ):
            app.on_mount()

        schedule.assert_called_once()
        self.assertEqual(
            notices,
            ["AgentHub update available: 0.1.0 -> 0.2.0. Run /update status."],
        )
        self.assertIn("_stabilize_initial_frame", scheduled)

    def test_workspace_files_starts_background_index_without_blocking(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        started: list[object] = []

        class _FakeThread:
            def __init__(self, *, target=None, name=None, daemon=None) -> None:
                started.append((target, name, daemon))

            def start(self) -> None:
                started.append("started")

        with patch(
            "cli.agent_cli.ui.app_transcript_coordination_runtime.threading.Thread", _FakeThread
        ):
            files = app._workspace_files()

        self.assertEqual(files, [])
        self.assertTrue(app._workspace_files_indexing)
        self.assertEqual(started[-1], "started")

    def test_normalize_pasted_path_text_keeps_slash_command_literal(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        normalized = app._normalize_pasted_path_text("/runtime_status")

        self.assertEqual(normalized, "/runtime_status")

    def test_normalize_pasted_path_text_keeps_bare_absolute_path_literal(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        normalized = app._normalize_pasted_path_text("/tmp/example.txt")

        self.assertEqual(normalized, "/tmp/example.txt")

    def test_paste_prompt_from_clipboard_reports_empty(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        notices: list[str] = []
        calls: list[str] = []

        app._read_clipboard_text = lambda: ""  # type: ignore[method-assign]
        app._write_system_notice = notices.append  # type: ignore[method-assign]
        app._focus_input = lambda: calls.append("focus")  # type: ignore[method-assign]

        result = app.paste_prompt_from_clipboard(report_empty=True)

        self.assertFalse(result)
        self.assertEqual(notices, [app._t("system.clipboard_empty")])
        self.assertEqual(calls, ["focus"])

    def test_paste_prompt_from_clipboard_inserts_text_and_refreshes(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        calls: list[object] = []

        app._read_clipboard_text = lambda: "hello"  # type: ignore[method-assign]
        app._insert_paste_text = lambda text: calls.append(("insert", text))  # type: ignore[method-assign]
        app._refresh_prompt_composer = lambda: calls.append("refresh")  # type: ignore[method-assign]
        app._focus_input = lambda: calls.append("focus")  # type: ignore[method-assign]

        result = app.paste_prompt_from_clipboard(report_empty=False)

        self.assertTrue(result)
        self.assertEqual(calls, [("insert", "hello"), "refresh", "focus"])

    def test_paste_prompt_from_clipboard_can_arm_native_paste_suppression(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        calls: list[object] = []

        app._read_clipboard_text = lambda: "hello"  # type: ignore[method-assign]
        app._arm_prompt_paste_suppression = lambda: calls.append("suppress")  # type: ignore[method-assign]
        app._insert_paste_text = lambda text: calls.append(("insert", text))  # type: ignore[method-assign]
        app._refresh_prompt_composer = lambda: calls.append("refresh")  # type: ignore[method-assign]
        app._focus_input = lambda: calls.append("focus")  # type: ignore[method-assign]

        result = app.paste_prompt_from_clipboard(
            report_empty=False,
            suppress_following_native_paste=True,
        )

        self.assertTrue(result)
        self.assertEqual(calls, ["suppress", ("insert", "hello"), "refresh", "focus"])

    def test_browse_prompt_history_applies_latest_entry(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        composer = SimpleNamespace(text="", cursor_pos=0)
        applied: list[str] = []

        app._prompt_history.record_local_submission("first")
        app._prompt_history.record_local_submission("second")
        app.query_one = lambda *_args, **_kwargs: composer  # type: ignore[method-assign]
        app._apply_history_prompt = applied.append  # type: ignore[method-assign]

        handled = app.browse_prompt_history(-1)

        self.assertTrue(handled)
        self.assertEqual(applied, ["second"])

    def test_record_prompt_history_includes_slash_commands(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())

        app._record_prompt_history("/help")
        app._record_prompt_history("  /theme light  ")
        app._record_prompt_history("normal prompt")

        self.assertEqual(
            app._prompt_history.local_history, ["/help", "/theme light", "normal prompt"]
        )

    def test_set_prompt_text_clears_pending_pastes(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        composer = SimpleNamespace(text="", set_text=lambda value: setattr(composer, "text", value))
        app._pending_pastes = [{"id": "paste-1"}]
        app.query_one = lambda *_args, **_kwargs: composer  # type: ignore[method-assign]

        app._set_prompt_text("updated")

        self.assertEqual(composer.text, "updated")
        self.assertEqual(app._pending_pastes, [])
