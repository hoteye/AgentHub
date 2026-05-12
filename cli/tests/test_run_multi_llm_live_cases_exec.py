from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "run_multi_llm_live_cases_exec.py"
SPEC = importlib.util.spec_from_file_location("run_multi_llm_live_cases_exec", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class _DummyChatPlanner:
    def __init__(self) -> None:
        self.config = SimpleNamespace(
            provider_name="deepseek",
            model="deepseek-chat",
            planner_kind="deepseek_chat",
            wire_api="openai_chat",
            base_url="https://api.deepseek.com",
        )
        self.route_config = SimpleNamespace(
            provider_name="glm",
            model="glm-5",
            planner_kind="openai_chat",
            wire_api="openai_chat",
            base_url="https://open.bigmodel.cn/api/coding/paas/v4",
        )
        self.model_timeout = 30
        self.route_client_calls: list[tuple[str, str]] = []
        self.chat_request: dict[str, object] = {}

    def _resolve_route(self, route_name: str):
        return SimpleNamespace(
            config=self.route_config, source="route", timeout=28, route_name=route_name
        )

    def _effective_route_resolution(self, _route_name: str, resolution):
        return resolution

    def _synthesis_messages(
        self, *, user_text: str, executed_events, executed_item_events=None, attachments=None
    ):
        del executed_events, executed_item_events, attachments
        return [
            {"role": "system", "content": "system"},
            {"role": "user", "content": user_text},
        ]

    def _route_client(self, route_name: str, route_config):
        self.route_client_calls.append((route_name, str(route_config.model)))
        return object()

    def _chat_completion_create(self, **kwargs):
        self.chat_request = dict(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=" /tmp/demo/workspace "))]
        )

    @staticmethod
    def _message_content_text(content):
        return str(content or "")

    @staticmethod
    def _sanitize_final_answer_text(value):
        return str(value or "").strip()


class _DummyAnthropicPlanner:
    def __init__(self) -> None:
        self.config = SimpleNamespace(
            provider_name="anthropic",
            model="claude-sonnet-4-6",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
            base_url="https://gaccode.com/claudecode",
        )
        self.route_config = self.config
        self.system_prompt = "system"
        self.max_tokens = 4096
        self.supports_tools = True
        self.cwd = "/tmp/demo"
        self.resolved_interaction_contract = SimpleNamespace(
            tool_result_projection_policy="claude_like"
        )

    def _resolve_route(self, route_name: str):
        return SimpleNamespace(
            config=self.route_config, source="main", timeout=40, route_name=route_name
        )

    def _effective_route_resolution(self, _route_name: str, resolution):
        return resolution

    @staticmethod
    def _tool_specs():
        return []


class RunMultiLlmLiveCasesExecTest(unittest.TestCase):
    def test_route_view_surfaces_followup_and_synthesis_routes(self) -> None:
        result = MODULE._route_view(
            {
                "routes": {
                    "tool_followup": {
                        "provider_name": "glm",
                        "model": "glm-5",
                        "wire_api": "openai_chat",
                        "reasoning_effort": "high",
                        "timeout": 30,
                        "source": "route",
                    },
                    "final_synthesis": {
                        "provider_name": "glm",
                        "model": "glm-5",
                        "wire_api": "openai_chat",
                        "reasoning_effort": "high",
                        "timeout": 30,
                        "source": "route",
                    },
                }
            }
        )
        self.assertEqual(result["tool_followup"]["provider_name"], "glm")
        self.assertEqual(result["final_synthesis"]["model"], "glm-5")

    def test_planner_case_intent_uses_chat_completion_route_when_fresh_followup_missing(
        self,
    ) -> None:
        planner = _DummyChatPlanner()

        intent = MODULE._planner_case_intent(
            planner,
            route_name="tool_followup",
            user_text="根据工具结果直接回答当前目录。",
            executed_events=[],
            tool_executor=SimpleNamespace(),
        )

        self.assertEqual(intent.assistant_text, "/tmp/demo/workspace")
        self.assertEqual(planner.route_client_calls, [("tool_followup", "glm-5")])
        self.assertEqual(
            planner.chat_request["trace_stage"], "chat_completions.route_tool_followup"
        )
        self.assertEqual(planner.chat_request["trace_payload"]["provider_name"], "glm")
        self.assertEqual(planner.chat_request["model"], "glm-5")

    def test_planner_case_intent_uses_anthropic_route_when_fresh_synthesis_missing(self) -> None:
        planner = _DummyAnthropicPlanner()
        captured_init: dict[str, object] = {}
        captured_send: dict[str, object] = {}

        class _DummyAnthropicSession:
            def __init__(self, **kwargs) -> None:
                captured_init.update(kwargs)

            def send(
                self,
                *,
                input_items,
                allow_tools=False,
                previous_response_id=None,
                prompt_cache_key=None,
                turn_event_callback=None,
            ):
                del previous_response_id, prompt_cache_key, turn_event_callback
                captured_send["input_items"] = input_items
                captured_send["allow_tools"] = allow_tools
                return SimpleNamespace(output_text=" 当前目录是 /tmp/demo ", response_items=[])

        with (
            patch.object(MODULE, "build_anthropic_client", return_value=object()),
            patch.object(MODULE, "AnthropicMessagesSession", _DummyAnthropicSession),
        ):
            intent = MODULE._planner_case_intent(
                planner,
                route_name="final_synthesis",
                user_text="根据工具结果直接总结。",
                executed_events=[],
            )

        self.assertEqual(intent.assistant_text, "当前目录是 /tmp/demo")
        self.assertEqual(captured_init["model"], "claude-sonnet-4-6")
        self.assertIs(captured_send["allow_tools"], False)
        self.assertTrue(captured_send["input_items"])

    def test_extract_llm_trace_infers_provider_and_response_only_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir)
            (log_dir / "llm_io.jsonl").write_text(
                "\n".join(
                    [
                        '{"stage":"anthropic_messages.request_raw","payload":{"request":{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":"hi"}]}}}',
                        '{"stage":"chat_completions.route_final_synthesis.response_raw","payload":{"route_name":"final_synthesis","provider_name":"glm","base_url":"https://open.bigmodel.cn/api/coding/paas/v4","response":{"model":"glm-5"}}}',
                    ]
                ),
                encoding="utf-8",
            )

            trace = MODULE._extract_llm_trace(log_dir)

        self.assertEqual(trace["requests"][0]["provider_name"], "anthropic")
        self.assertEqual(trace["requests"][0]["model"], "claude-sonnet-4-6")
        self.assertEqual(trace["requests"][1]["provider_name"], "glm")
        self.assertEqual(trace["requests"][1]["model"], "glm-5")
        self.assertEqual(trace["requests"][1]["route_name"], "final_synthesis")
