from __future__ import annotations

import unittest

from cli.agent_cli.send_guard import recovery_suggestions

class SendGuardTest(unittest.TestCase):
    def test_recovery_suggestions_use_product_neutral_language(self) -> None:
        suggestions = recovery_suggestions(
            "prepare_send",
            {"reason": "conversation_select_failed", "ok": False},
        )

        self.assertTrue(suggestions)
        self.assertIn("目标对象", suggestions[0])
        self.assertIn("可见状态", suggestions[0])

    def test_default_failure_suggestion_is_generic(self) -> None:
        suggestions = recovery_suggestions(
            "unknown",
            {"reason": "other_failure", "ok": False},
        )

        self.assertEqual(
            suggestions,
            ["检查当前应用是否在前台且处于标准输入界面后重试。"],
        )
