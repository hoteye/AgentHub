from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.prompt_history import PromptHistoryStore
from cli.agent_cli.runtime import AgentCliRuntime


class PromptHistoryIncludesSlashTest(unittest.TestCase):
    def test_browse_prompt_history_includes_persisted_slash_entries(self) -> None:
        with TemporaryDirectory() as tmpdir:
            history_home = Path(tmpdir)
            store = PromptHistoryStore(history_home)
            store.append("/provider")
            store.append("first prompt")
            store.append("/tools")
            store.append("second prompt")

            app = AgentCliApp(runtime=AgentCliRuntime(), prompt_history_home=history_home)
            composer = SimpleNamespace(text="", cursor_pos=0)
            applied: list[str] = []

            app.query_one = lambda *_args, **_kwargs: composer  # type: ignore[method-assign]

            def _apply(value: str) -> None:
                composer.text = value
                composer.cursor_pos = len(value)
                applied.append(value)

            app._apply_history_prompt = _apply  # type: ignore[method-assign]

            self.assertTrue(app.browse_prompt_history(-1))
            self.assertEqual(applied[-1], "second prompt")
            self.assertTrue(app.browse_prompt_history(-1))
            self.assertEqual(applied[-1], "/tools")
            self.assertTrue(app.browse_prompt_history(-1))
            self.assertEqual(applied[-1], "first prompt")
            self.assertTrue(app.browse_prompt_history(-1))
            self.assertEqual(applied[-1], "/provider")

            self.assertTrue(app.browse_prompt_history(1))
            self.assertEqual(applied[-1], "first prompt")
            self.assertTrue(app.browse_prompt_history(1))
            self.assertEqual(applied[-1], "/tools")
            self.assertTrue(app.browse_prompt_history(1))
            self.assertEqual(applied[-1], "second prompt")
            self.assertTrue(app.browse_prompt_history(1))
            self.assertEqual(applied[-1], "")
