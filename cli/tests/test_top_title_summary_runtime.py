from __future__ import annotations

import unittest

from rich.cells import cell_len

from cli.agent_cli.ui.text_utils import crop_one_line
from cli.agent_cli.ui.top_title_summary_runtime import (
    condensed_prompt_intent,
    is_slash_command_prompt,
    normalized_prompt_text,
    should_update_title_from_prompt,
    strip_leading_prompt_prefix,
    top_title_text_for_prompt,
)


class TopTitleSummaryRuntimeTest(unittest.TestCase):
    def test_normalized_prompt_text_flattens_whitespace(self) -> None:
        self.assertEqual(normalized_prompt_text("  a\n b\t c  "), "a b c")

    def test_is_slash_command_prompt_detects_slash_commands(self) -> None:
        self.assertTrue(is_slash_command_prompt("/provider"))
        self.assertTrue(is_slash_command_prompt("   /tools   "))
        self.assertFalse(is_slash_command_prompt("请帮我看看 provider 状态"))

    def test_should_update_title_from_prompt_skips_empty_and_slash(self) -> None:
        self.assertFalse(should_update_title_from_prompt(""))
        self.assertFalse(should_update_title_from_prompt("   "))
        self.assertFalse(should_update_title_from_prompt("/model gpt_54"))
        self.assertTrue(should_update_title_from_prompt("请帮我梳理回滚步骤"))

    def test_strip_leading_prompt_prefix_removes_common_polite_prefix(self) -> None:
        self.assertEqual(
            strip_leading_prompt_prefix("请帮我  修复登录失败并补测试"),
            "修复登录失败并补测试",
        )
        self.assertEqual(
            strip_leading_prompt_prefix("麻烦你：整理今天的发布事项"),
            "整理今天的发布事项",
        )

    def test_condensed_prompt_intent_keeps_first_sentence(self) -> None:
        self.assertEqual(
            condensed_prompt_intent("请帮我修复支付回调超时，并补测试。然后给我一份变更说明"),
            "修复支付回调超时，并补测试",
        )
        self.assertEqual(
            condensed_prompt_intent("我想把接口改成幂等；并补一个回归用例"),
            "把接口改成幂等",
        )

    def test_top_title_text_for_prompt_crops_and_falls_back_to_base_title(self) -> None:
        cropped = top_title_text_for_prompt(
            "请帮我修复登录问题并补充回归测试，顺便更新文档",
            base_title="AgentHub",
            width=10,
            crop_one_line_fn=crop_one_line,
        )
        self.assertTrue(cropped.startswith("修复"))
        self.assertTrue(cropped.endswith("..."))
        self.assertLessEqual(cell_len(cropped), 10)
        self.assertEqual(
            top_title_text_for_prompt(
                "",
                base_title="AgentHub",
                width=10,
                crop_one_line_fn=crop_one_line,
            ),
            "AgentHub",
        )


