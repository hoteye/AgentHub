from __future__ import annotations

import unittest
from typing import Any, Dict, List, Optional

from cli.agent_cli.core.provider_session import ProviderSession, ProviderSessionResult, ProviderToolCall
from cli.agent_cli.core.turn_engine import TurnEngine
from cli.agent_cli.models import AgentIntent, ToolEvent, response_message_item

class _FakeSession(ProviderSession):
    def __init__(self, scripted: List[ProviderSessionResult]):
        self.scripted = list(scripted)
        self.calls: List[Dict[str, Any]] = []

    def send(
        self,
        *,
        input_items: List[Dict[str, Any]],
        allow_tools: bool,
        previous_response_id: Optional[str] = None,
        prompt_cache_key: Optional[str] = None,
        turn_event_callback: Any = None,
    ) -> ProviderSessionResult:
        self.calls.append(
            {
                "input": input_items,
                "allow_tools": allow_tools,
                "previous_response_id": previous_response_id,
                "prompt_cache_key": prompt_cache_key,
                "turn_event_callback": turn_event_callback,
            }
        )
        if not self.scripted:
            raise RuntimeError("no scripted response")
        return self.scripted.pop(0)

class TurnEngineNoHardcodedRoundLimitTests(unittest.TestCase):
    def test_default_turn_engine_continues_past_six_rounds_until_model_answers(self) -> None:
        scripted: List[ProviderSessionResult] = []
        for index in range(6):
            call_id = f"call_{index + 1}"
            scripted.append(
                ProviderSessionResult(
                    output_text="",
                    tool_calls=[ProviderToolCall(call_id=call_id, name="read_file", arguments={"file_path": f"doc_{index + 1}.md"})],
                    response_id=f"resp_{index + 1}",
                )
            )
        scripted.append(
            ProviderSessionResult(
                output_text="final answer",
                tool_calls=[],
                response_items=[response_message_item("assistant", "final answer", phase="final_answer")],
                response_id="resp_7",
            )
        )
        session = _FakeSession(scripted)

        def tool_executor(command_text: str):
            return "read ok", [
                ToolEvent(
                    name="read_file",
                    ok=True,
                    summary="file loaded",
                    payload={"command": command_text},
                )
            ]

        engine = TurnEngine(session, tool_executor=tool_executor)
        intent: AgentIntent = engine.run(
            user_text="keep going until done",
            initial_input=[{"role": "user", "content": "continue"}],
        )

        self.assertEqual(intent.assistant_text, "final answer")
        self.assertEqual(len(session.calls), 7)
        self.assertEqual(session.calls[-1]["previous_response_id"], "resp_6")
