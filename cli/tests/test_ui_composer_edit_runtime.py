from __future__ import annotations

import unittest
from types import SimpleNamespace

from cli.agent_cli import app_event_helpers
from cli.agent_cli.ui import composer_runtime
from cli.agent_cli.ui.composer import PromptComposer


def _composer(text: str) -> PromptComposer:
    composer = PromptComposer(text)
    composer.refresh = lambda *args, **kwargs: None  # type: ignore[method-assign]
    return composer


class _EscapeFallbackComposer:
    ALT_ENTER_ESCAPE_FALLBACK_SECONDS = 0.08

    def __init__(self, text: str = "") -> None:
        self.text = text
        self._pending_alt_enter_escape_token = 0
        self._pending_alt_enter_escape_active_token = 0
        self.inserted: list[str] = []
        self.scheduled: list[object] = []
        self.escape_calls: list[str] = []
        self.app = SimpleNamespace(
            handle_escape_key=lambda: self.escape_calls.append("escape") or True,
        )

    def insert_text(self, text: str) -> None:
        self.inserted.append(text)
        self.text += text

    def set_timer(self, _delay: float, callback) -> object:
        self.scheduled.append(callback)
        return callback


class _FakeKeyEvent:
    def __init__(self, key: str, *, aliases: list[str] | None = None) -> None:
        self.key = key
        self.aliases = list(aliases or [])
        self.is_printable = False
        self.character = None
        self.stopped = False
        self.prevented = False

    def stop(self) -> None:
        self.stopped = True

    def prevent_default(self) -> None:
        self.prevented = True


def _handle_composer_key(composer: PromptComposer, key: str) -> _FakeKeyEvent:
    event = _FakeKeyEvent(key)
    handled = composer_runtime.handle_key_event(
        composer=composer,
        event=event,
        prehandled=False,
        app_ctrl_c_fn=lambda: None,
    )
    assert handled
    assert event.stopped
    assert event.prevented
    return event


class ComposerEditRuntimeTest(unittest.TestCase):
    def test_backspace_removes_atomic_attachment_reference(self) -> None:
        composer = _composer('look @"/tmp/cat.png" now')
        composer._cursor_pos = len('look @"/tmp/cat.png"')

        composer.backspace()

        self.assertEqual(composer.text, "look  now")
        self.assertEqual(composer.cursor_pos, len("look "))

    def test_selection_bounds_expand_to_atomic_tokens(self) -> None:
        composer = _composer('a @"/tmp/cat.png" z')
        composer._selection_anchor = 3
        composer._cursor_pos = 6

        self.assertEqual(composer.selection_bounds, (2, 17))
        self.assertEqual(composer.selected_text, '@"/tmp/cat.png"')

    def test_undo_and_redo_restore_text_and_cursor(self) -> None:
        composer = _composer("hello")

        composer.insert_text(" world")
        composer.undo()

        self.assertEqual(composer.text, "hello")
        self.assertEqual(composer.cursor_pos, 5)

        composer.redo()

        self.assertEqual(composer.text, "hello world")
        self.assertEqual(composer.cursor_pos, 11)

    def test_word_navigation_treats_punctuation_as_separate_word_like_units(self) -> None:
        composer = _composer("alpha, beta")
        composer._cursor_pos = len(composer.text)

        composer.move_cursor_word_left()
        self.assertEqual(composer.cursor_pos, 7)

        composer.move_cursor_word_left()
        self.assertEqual(composer.cursor_pos, 5)

        composer.move_cursor_word_left()
        self.assertEqual(composer.cursor_pos, 0)

        composer.move_cursor_word_right()
        self.assertEqual(composer.cursor_pos, 5)

        composer.move_cursor_word_right()
        self.assertEqual(composer.cursor_pos, 6)

        composer.move_cursor_word_right()
        self.assertEqual(composer.cursor_pos, len(composer.text))

    def test_codex_style_word_delete_keys_delete_previous_and_next_word(self) -> None:
        composer = _composer("alpha beta gamma")
        composer._cursor_pos = len("alpha beta")

        _handle_composer_key(composer, "ctrl+w")

        self.assertEqual(composer.text, "alpha  gamma")
        self.assertEqual(composer.cursor_pos, len("alpha "))

        _handle_composer_key(composer, "alt+d")

        self.assertEqual(composer.text, "alpha ")
        self.assertEqual(composer.cursor_pos, len("alpha "))

    def test_codex_style_line_kill_keys_match_logical_line_semantics(self) -> None:
        composer = _composer("alpha beta\ngamma delta")
        composer._cursor_pos = len("alpha beta\ngamma")

        _handle_composer_key(composer, "ctrl+u")

        self.assertEqual(composer.text, "alpha beta\n delta")
        self.assertEqual(composer.cursor_pos, len("alpha beta\n"))

        _handle_composer_key(composer, "ctrl+k")

        self.assertEqual(composer.text, "alpha beta\n")
        self.assertEqual(composer.cursor_pos, len("alpha beta\n"))

    def test_ctrl_y_yanks_last_killed_text(self) -> None:
        composer = _composer("alpha beta")
        composer._cursor_pos = len("alpha beta")

        _handle_composer_key(composer, "ctrl+w")
        self.assertEqual(composer.text, "alpha ")

        _handle_composer_key(composer, "ctrl+y")

        self.assertEqual(composer.text, "alpha beta")
        self.assertEqual(composer.cursor_pos, len("alpha beta"))

    def test_ctrl_u_at_line_start_noops(self) -> None:
        composer = _composer("alpha\nbeta")
        composer._cursor_pos = len("alpha\n")

        _handle_composer_key(composer, "ctrl+u")

        self.assertEqual(composer.text, "alpha\nbeta")
        self.assertEqual(composer.cursor_pos, len("alpha\n"))

    def test_ctrl_e_moves_to_logical_line_end_and_next_line_when_repeated(self) -> None:
        composer = _composer("alpha\nbeta")
        composer._cursor_pos = 2

        _handle_composer_key(composer, "ctrl+e")
        self.assertEqual(composer.cursor_pos, len("alpha"))

        _handle_composer_key(composer, "ctrl+e")
        self.assertEqual(composer.cursor_pos, len("alpha\nbeta"))

    def test_ctrl_modified_navigation_keys_move_or_extend_selection(self) -> None:
        composer = _composer("alpha beta")

        _handle_composer_key(composer, "ctrl+left")
        self.assertEqual(composer.cursor_pos, len("alpha "))

        _handle_composer_key(composer, "ctrl+shift+right")
        self.assertEqual(composer.cursor_pos, len("alpha beta"))
        self.assertEqual(composer.selection_bounds, (len("alpha "), len("alpha beta")))

        _handle_composer_key(composer, "ctrl+home")
        self.assertEqual(composer.cursor_pos, 0)
        self.assertIsNone(composer.selection_bounds)

        _handle_composer_key(composer, "ctrl+shift+end")
        self.assertEqual(composer.cursor_pos, len("alpha beta"))
        self.assertEqual(composer.selection_bounds, (0, len("alpha beta")))

    def test_raw_terminal_home_and_end_sequences_move_prompt_cursor(self) -> None:
        for raw_home, raw_end in (
            ("\x1b[H", "\x1b[F"),
            ("\x1bOH", "\x1bOF"),
            ("\x1b[1~", "\x1b[4~"),
            ("\x1b[7~", "\x1b[8~"),
        ):
            composer = _composer("alpha")

            _handle_composer_key(composer, raw_home)
            self.assertEqual(composer.cursor_pos, 0, repr(raw_home))

            _handle_composer_key(composer, raw_end)
            self.assertEqual(composer.cursor_pos, len("alpha"), repr(raw_end))

    def test_textual_tmux_home_and_end_decoded_keys_move_prompt_cursor(self) -> None:
        composer = _composer("alpha")

        _handle_composer_key(composer, "\x01")
        self.assertEqual(composer.cursor_pos, 0)

        _handle_composer_key(composer, "\x04")
        self.assertEqual(composer.cursor_pos, len("alpha"))

    def test_raw_terminal_shift_home_and_end_sequences_extend_selection(self) -> None:
        composer = _composer("alpha")

        _handle_composer_key(composer, "\x1b[1;2H")
        self.assertEqual(composer.selection_bounds, (0, len("alpha")))

        _handle_composer_key(composer, "\x1b[1;2F")
        self.assertIsNone(composer.selection_bounds)
        self.assertEqual(composer.cursor_pos, len("alpha"))

    def test_codex_style_aliases_route_to_composer_when_input_is_not_focused(self) -> None:
        for key in (
            "alt+left",
            "alt+right",
            "ctrl+backspace",
            "ctrl+delete",
            "ctrl+end",
            "ctrl+home",
            "ctrl+k",
            "ctrl+left",
            "ctrl+right",
            "ctrl+shift+end",
            "ctrl+shift+home",
            "ctrl+shift+left",
            "ctrl+shift+right",
            "ctrl+w",
        ):
            event = SimpleNamespace(key=key, aliases=[], is_printable=False, character=None)
            self.assertTrue(app_event_helpers._is_prompt_composer_key_candidate(event), key)

    def test_raw_terminal_home_and_end_sequences_route_to_composer_when_input_is_not_focused(
        self,
    ) -> None:
        for key in (
            "\x1b[H",
            "\x1b[F",
            "\x1bOH",
            "\x1bOF",
            "\x1b[1~",
            "\x1b[4~",
            "\x01",
            "\x04",
        ):
            event = SimpleNamespace(key=key, aliases=[], is_printable=False, character=None)
            self.assertTrue(app_event_helpers._is_prompt_composer_key_candidate(event), repr(key))

    def test_alt_enter_inserts_newline(self) -> None:
        composer = _composer("line1")
        event = _FakeKeyEvent("alt+enter")

        handled = composer_runtime.handle_key_event(
            composer=composer,
            event=event,
            prehandled=False,
            app_ctrl_c_fn=lambda: None,
        )

        self.assertTrue(handled)
        self.assertEqual(composer.text, "line1\n")
        self.assertTrue(event.stopped)
        self.assertTrue(event.prevented)

    def test_escape_then_enter_falls_back_to_alt_enter_newline(self) -> None:
        composer = _EscapeFallbackComposer("line1")

        escape_event = _FakeKeyEvent("escape")
        enter_event = _FakeKeyEvent("enter")

        escape_handled = composer_runtime.handle_alt_enter_escape_fallback(
            composer=composer,
            event=escape_event,
        )
        enter_handled = composer_runtime.handle_alt_enter_escape_fallback(
            composer=composer,
            event=enter_event,
        )

        self.assertTrue(escape_handled)
        self.assertTrue(enter_handled)
        self.assertEqual(composer.text, "line1\n")
        self.assertEqual(composer.escape_calls, [])
        self.assertTrue(escape_event.stopped)
        self.assertTrue(escape_event.prevented)
        self.assertTrue(enter_event.stopped)
        self.assertTrue(enter_event.prevented)

    def test_escape_fallback_flushes_original_escape_when_sequence_does_not_continue(self) -> None:
        composer = _EscapeFallbackComposer("")

        escape_handled = composer_runtime.handle_alt_enter_escape_fallback(
            composer=composer,
            event=_FakeKeyEvent("escape"),
        )
        self.assertTrue(escape_handled)
        self.assertEqual(composer.escape_calls, [])
        self.assertEqual(len(composer.scheduled), 1)

        callback = composer.scheduled[0]
        assert callable(callback)
        callback()

        self.assertEqual(composer.escape_calls, ["escape"])
