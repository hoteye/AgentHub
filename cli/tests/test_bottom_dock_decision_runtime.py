from __future__ import annotations

import unittest

from cli.agent_cli.ui.bottom_dock_decision_runtime import decide_bottom_dock_content


class BottomDockDecisionRuntimeTest(unittest.TestCase):
    def test_transcript_mode_uses_transcript_footer_pair(self) -> None:
        decision = decide_bottom_dock_content(
            screen_mode="transcript",
            status_line="ignored",
            passive_summary_active=False,
            prompt_has_text=False,
            busy=False,
            queue_dominant_active=False,
            footer_context_text="context",
            footer_shortcuts_text="shortcuts",
            footer_queue_text="queue",
            transcript_prompt_view_text="prompt view",
            transcript_exit_text="esc back",
        )

        self.assertEqual(decision.status_line, "")
        self.assertEqual(decision.footer_left, "prompt view")
        self.assertEqual(decision.footer_right, "esc back")

    def test_passive_summary_hides_shortcuts_when_prompt_is_empty(self) -> None:
        decision = decide_bottom_dock_content(
            screen_mode="prompt",
            status_line="gpt-5.4 · resume current task · workspace",
            passive_summary_active=True,
            prompt_has_text=False,
            busy=False,
            queue_dominant_active=False,
            footer_context_text="100% context left",
            footer_shortcuts_text="? for shortcuts",
            footer_queue_text="Tab to view queue",
            transcript_prompt_view_text="prompt view",
            transcript_exit_text="esc back",
        )

        self.assertEqual(decision.footer_left, "")
        self.assertEqual(decision.footer_right, "100% context left")

    def test_busy_draft_keeps_queue_hint(self) -> None:
        decision = decide_bottom_dock_content(
            screen_mode="prompt",
            status_line="• Working (2s • esc to interrupt)",
            passive_summary_active=False,
            prompt_has_text=True,
            busy=True,
            queue_dominant_active=True,
            footer_context_text="100% context left",
            footer_shortcuts_text="? for shortcuts",
            footer_queue_text="Tab to view queue",
            transcript_prompt_view_text="prompt view",
            transcript_exit_text="esc back",
        )

        self.assertEqual(decision.status_line, "• Working (2s • esc to interrupt)")
        self.assertEqual(decision.footer_left, "Tab to view queue")
        self.assertEqual(decision.footer_right, "100% context left")

    def test_queue_dominant_beats_other_prompt_state_flags(self) -> None:
        decision = decide_bottom_dock_content(
            screen_mode="prompt",
            status_line="• Working (0s • esc to interrupt)",
            passive_summary_active=True,
            prompt_has_text=True,
            busy=False,
            queue_dominant_active=True,
            footer_context_text="82% left",
            footer_shortcuts_text="? for shortcuts",
            footer_queue_text="Tab to queue",
            transcript_prompt_view_text="prompt view",
            transcript_exit_text="esc back",
        )

        self.assertEqual(decision.status_line, "• Working (0s • esc to interrupt)")
        self.assertEqual(decision.footer_left, "Tab to queue")
        self.assertEqual(decision.footer_right, "82% left")

    def test_prompt_mode_current_contract_always_keeps_context_on_right(self) -> None:
        decision = decide_bottom_dock_content(
            screen_mode="prompt",
            status_line="passive summary",
            passive_summary_active=False,
            prompt_has_text=False,
            busy=False,
            queue_dominant_active=False,
            footer_context_text="100% context left",
            footer_shortcuts_text="? for shortcuts",
            footer_queue_text="Tab to queue",
            transcript_prompt_view_text="prompt view",
            transcript_exit_text="esc back",
        )

        self.assertEqual(decision.status_line, "passive summary")
        self.assertEqual(decision.footer_left, "")
        self.assertEqual(decision.footer_right, "100% context left")

    def test_idle_prompt_footer_keeps_context_only_when_status_line_owns_shortcuts(self) -> None:
        decision = decide_bottom_dock_content(
            screen_mode="prompt",
            status_line="• ? for shortcuts",
            passive_summary_active=False,
            prompt_has_text=False,
            busy=False,
            queue_dominant_active=False,
            footer_context_text="100% context left",
            footer_shortcuts_text="? for shortcuts",
            footer_queue_text="Tab to view queue",
            transcript_prompt_view_text="prompt view",
            transcript_exit_text="esc back",
        )

        self.assertEqual(decision.status_line, "• ? for shortcuts")
        self.assertEqual(decision.footer_left, "")
        self.assertEqual(decision.footer_right, "100% context left")

