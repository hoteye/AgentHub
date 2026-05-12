from __future__ import annotations

import unittest

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.runtime import AgentCliRuntime


class BusyShortcutPolicyTest(unittest.IsolatedAsyncioTestCase):
    async def test_action_refresh_state_blocks_when_busy_policy_disallows(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        notices: list[str] = []
        focus_calls: list[str] = []
        enqueued: list[tuple[str, list[object], dict[str, object]]] = []

        async def _enqueue(text: str, attachments: list[object], **kwargs: object) -> None:
            enqueued.append((text, attachments, dict(kwargs)))

        app._has_pending_runtime_work = lambda: True  # type: ignore[method-assign]
        app._slash_command_available_during_busy = lambda _text: False  # type: ignore[method-assign]
        app._write_system_notice = notices.append  # type: ignore[method-assign]
        app._focus_input = lambda: focus_calls.append("focus")  # type: ignore[method-assign]
        app._enqueue_runtime_request = _enqueue  # type: ignore[method-assign]

        await app.action_refresh_state()

        self.assertEqual(notices, [app._BUSY_SLASH_COMMAND_NOTICE])
        self.assertEqual(focus_calls, ["focus"])
        self.assertEqual(enqueued, [])

    async def test_action_show_tools_honors_busy_policy_and_queues_when_allowed(self) -> None:
        app = AgentCliApp(runtime=AgentCliRuntime())
        notices: list[str] = []
        enqueued: list[tuple[str, list[object], dict[str, object]]] = []

        async def _enqueue(text: str, attachments: list[object], **kwargs: object) -> None:
            enqueued.append((text, attachments, dict(kwargs)))

        app._has_pending_runtime_work = lambda: True  # type: ignore[method-assign]
        app._slash_command_available_during_busy = lambda _text: True  # type: ignore[method-assign]
        app._write_system_notice = notices.append  # type: ignore[method-assign]
        app._enqueue_runtime_request = _enqueue  # type: ignore[method-assign]
        app._t = lambda key, **_kwargs: key  # type: ignore[method-assign]

        await app.action_show_tools()

        self.assertEqual(notices, ["system.queued_tools"])
        self.assertEqual(enqueued, [("/tools", [], {"priority": "later"})])
