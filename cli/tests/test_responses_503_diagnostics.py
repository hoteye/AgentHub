from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.agent import RuleBasedAgent
from cli.agent_cli.providers.adapters.openai_responses import OpenAIResponsesSession
from cli.agent_cli.providers.responses_503_diagnostics import (
    diagnose_responses_request_503_risks,
    format_responses_request_503_risks,
)


def _bad_multiturn_request_items() -> list[dict]:
    return [
        {
            "type": "message",
            "role": "developer",
            "content": [
                {
                    "type": "input_text",
                    "text": "<permissions instructions>...</permissions instructions>",
                }
            ],
        },
        {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "<environment_context>\n  <cwd>/tmp</cwd>\n</environment_context>",
                }
            ],
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "今天几号？"}],
        },
        {
            "type": "reasoning",
            "content": [{"type": "reasoning", "text": "plain reasoning"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "今天是 2026 年 4 月 1 日。"}],
        },
        {
            "type": "function_call",
            "name": "exec_command",
            "call_id": "item_0",
            "arguments": '{"cmd":"pwd"}',
            "content": [],
        },
        {
            "type": "function_call_output",
            "call_id": "item_0",
            "output": '{"command":"pwd","aggregated_output":"/tmp","exit_code":0,"status":"completed"}',
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "明天呢？"}],
        },
    ]


class _Always503Responses:
    def __init__(self) -> None:
        self.requests: list[dict] = []

    def create(self, **kwargs):
        self.requests.append(dict(kwargs))
        raise RuntimeError(
            "InternalServerError: Error code: 503 - {'error': {'type': 'proxy_unavailable', 'message': 'All accounts are currently unavailable.'}}"
        )


class _Always503Client:
    def __init__(self) -> None:
        self.responses = _Always503Responses()


class Responses503DiagnosticsTest(unittest.TestCase):
    def test_diagnose_responses_request_503_risks_flags_gold_standard_bad_triplet(self) -> None:
        diagnostics = diagnose_responses_request_503_risks(
            {"input": _bad_multiturn_request_items()}
        )

        self.assertEqual(diagnostics["issue_count"], 3)
        self.assertEqual(
            [item["element"] for item in diagnostics["issues"]],
            [
                "previous_turn_reasoning",
                "previous_turn_function_call",
                "previous_turn_function_call_output",
            ],
        )
        rendered = format_responses_request_503_risks(diagnostics)
        self.assertIn("503 请求结构诊断:", rendered[0])
        self.assertTrue(any("input[3] previous_turn_reasoning" in line for line in rendered))
        self.assertTrue(
            any("input[6] previous_turn_function_call_output" in line for line in rendered)
        )

    def test_openai_responses_session_attaches_503_request_diagnostics(self) -> None:
        session = OpenAIResponsesSession(
            client=_Always503Client(),
            model="gpt-5.4",
            instructions="system",
            tool_specs=[],
        )

        with patch("cli.agent_cli.providers.openai_client.time.sleep", return_value=None):
            with self.assertRaises(RuntimeError) as excinfo:
                session.send(input_items=_bad_multiturn_request_items(), allow_tools=False)

        diagnostics = getattr(excinfo.exception, "agenthub_provider_diagnostics", None)
        self.assertIsInstance(diagnostics, dict)
        self.assertEqual(
            [item["element"] for item in diagnostics["issues"]],
            [
                "previous_turn_reasoning",
                "previous_turn_function_call",
                "previous_turn_function_call_output",
            ],
        )

    def test_rule_based_agent_fallback_keeps_503_diagnostics_out_of_user_text(self) -> None:
        class _FailingPlanner:
            @staticmethod
            def public_summary():
                return {
                    "provider_name": "openai",
                    "model_key": "gpt-5.4",
                    "planner_kind": "openai_responses",
                    "model": "gpt-5.4",
                    "base_url": "https://example.invalid/v1",
                    "source": "test",
                    "config_path": "/tmp/config.toml",
                    "auth_path": "/tmp/auth.json",
                }

            def plan(
                self,
                text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                **kwargs,
            ):
                del text, history, tool_executor, attachments, kwargs
                diagnostics = diagnose_responses_request_503_risks(
                    {"input": list(input_items or [])}
                )
                exc = RuntimeError(
                    "InternalServerError: Error code: 503 - {'error': {'type': 'proxy_unavailable', 'message': 'All accounts are currently unavailable.'}}"
                )
                exc.agenthub_provider_diagnostics = diagnostics
                raise exc

        fake_paths = SimpleNamespace(
            config_path=Path("/tmp/config.toml"),
            auth_path=Path("/tmp/auth.json"),
        )

        with patch("cli.agent_cli.agent.resolve_provider_paths", return_value=fake_paths):
            with patch("cli.agent_cli.agent.load_provider_config", return_value=object()):
                with patch("cli.agent_cli.agent.build_planner", return_value=_FailingPlanner()):
                    agent = RuleBasedAgent()
                    intent = agent.plan(
                        "继续", history=[], input_items=_bad_multiturn_request_items()
                    )

        self.assertEqual(intent.assistant_text, "无法继续：All accounts are currently unavailable.")
        self.assertNotIn("503 请求结构诊断:", intent.assistant_text)
        self.assertNotIn("provider 失败类型", intent.assistant_text)
        self.assertNotIn("最近一次 provider 异常", intent.assistant_text)
