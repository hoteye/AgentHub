from __future__ import annotations

import io
import json

from cli.agent_cli.agent import RuleBasedAgent
from cli.agent_cli.app_server import main as app_server_main
from cli.agent_cli.main import main
from cli.agent_cli.models import AgentIntent
from cli.agent_cli.runtime import AgentCliRuntime


def _request_payload() -> dict[str, object]:
    return {
        "questions": [
            {
                "id": "confirm_path",
                "header": "Confirm",
                "question": "Proceed?",
                "options": [
                    {"label": "Yes (Recommended)", "description": "Continue."},
                    {"label": "No", "description": "Stop."},
                ],
            },
            {
                "id": "delivery",
                "header": "Delivery",
                "question": "How should this be delivered?",
                "options": [
                    {"label": "Patch only", "description": "Return only patch."},
                    {"label": "Custom delivery path", "description": "Use a custom delivery path."},
                ],
            },
        ]
    }


def _request_prompt() -> str:
    return "/request_user_input '" + json.dumps(_request_payload(), ensure_ascii=False) + "'"


class _HeadlessRoundTripAgent(RuleBasedAgent):
    def provider_status(self) -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "test",
            "provider_model": "gpt-5.4",
        }

    def plan(self, text: str, history=None, *, tool_executor=None, attachments=None):
        del history, tool_executor, attachments
        return AgentIntent(assistant_text=f"echo: {text}")


class _NoopTools:
    def capabilities(self) -> dict[str, object]:
        return {"ok": True, "tools": []}


def test_headless_request_user_input_multi_question_response_is_canonical() -> None:
    runtime = AgentCliRuntime(agent=_HeadlessRoundTripAgent(), tools=_NoopTools())
    runtime.collaboration_mode = "plan"
    runtime.request_user_input_handler = lambda payload: {
        "answers": {
            "confirm_path": "yes",
            "delivery": "custom delivery",
        },
        "questions": payload["questions"],
    }
    stdout = io.StringIO()

    code = main(
        ["--headless", "--prompt", _request_prompt(), "--json"],
        runtime=runtime,
        stdout=stdout,
        stderr=io.StringIO(),
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["tool_events"][-1]["name"] == "request_user_input"
    normalized = json.loads(payload["assistant_text"])
    assert normalized["answers"]["confirm_path"]["answers"] == ["yes"]
    assert normalized["answers"]["delivery"]["answers"] == ["custom delivery"]
    assert payload["tool_events"][-1]["payload"]["response"]["answers"]["confirm_path"]["answers"] == ["yes"]
    assert payload["tool_events"][-1]["payload"]["response"]["answers"]["delivery"]["answers"] == ["custom delivery"]


def test_app_server_request_user_input_multi_question_other_answer_round_trip() -> None:
    runtime = AgentCliRuntime(agent=_HeadlessRoundTripAgent(), tools=_NoopTools())
    runtime.collaboration_mode = "plan"
    runtime.request_user_input_handler = lambda payload: {
        "answers": {
            "confirm_path": {"answers": ["yes"]},
            "delivery": "custom delivery",
        },
        "questions": payload["questions"],
    }
    stdout = io.StringIO()
    stdin = io.StringIO(
        "\n".join(
            [
                json.dumps({"id": "init", "method": "initialize", "params": {}}),
                json.dumps({"method": "initialized", "params": {}}),
                json.dumps(
                    {
                        "id": "run-request-user-input",
                        "method": "session/run",
                        "params": {
                            "prompt": _request_prompt(),
                            "stream": False,
                        },
                    }
                ),
            ]
        )
        + "\n"
    )

    code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)

    assert code == 0
    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    run_result = next(line for line in lines if line.get("id") == "run-request-user-input")
    response = run_result["result"]["response"]
    assert response["tool_events"][-1]["name"] == "request_user_input"
    normalized = json.loads(response["assistant_text"])
    assert normalized["answers"]["confirm_path"]["answers"] == ["yes"]
    assert normalized["answers"]["delivery"]["answers"] == ["custom delivery"]
    assert response["tool_events"][-1]["payload"]["response"]["answers"]["confirm_path"]["answers"] == ["yes"]
    assert response["tool_events"][-1]["payload"]["response"]["answers"]["delivery"]["answers"] == ["custom delivery"]
