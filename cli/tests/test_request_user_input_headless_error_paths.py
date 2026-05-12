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
            }
        ]
    }


def _request_prompt() -> str:
    return "/request_user_input '" + json.dumps(_request_payload(), ensure_ascii=False) + "'"


def _force_default_mode_request_user_input(runtime: AgentCliRuntime, enabled: bool) -> None:
    def _sync_for_test() -> bool:
        runtime.default_mode_request_user_input = bool(enabled)
        return bool(enabled)

    runtime._sync_request_user_input_mode_from_provider = _sync_for_test  # type: ignore[method-assign]
    planner = getattr(runtime.agent, "_planner", None)
    config = getattr(planner, "config", None)
    if config is None:
        return
    raw_model = getattr(config, "raw_model", None)
    if isinstance(raw_model, dict):
        raw_model["default_mode_request_user_input"] = bool(enabled)
    raw_provider = getattr(config, "raw_provider", None)
    if isinstance(raw_provider, dict):
        raw_provider.pop("default_mode_request_user_input", None)
        raw_provider.pop("reference_default_mode_request_user_input", None)


class _HeadlessErrorAgent(RuleBasedAgent):
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


def _last_failed_item(turn_events: list[dict[str, object]]) -> dict[str, object]:
    completed = [
        event
        for event in list(turn_events or [])
        if isinstance(event, dict)
        and event.get("type") == "item.completed"
        and isinstance(event.get("item"), dict)
        and (event.get("item") or {}).get("tool") == "request_user_input"
    ]
    assert completed, "expected request_user_input item.completed event"
    return dict(completed[-1]["item"])  # type: ignore[index]


def test_headless_request_user_input_handler_none_or_non_dict_cancelled_and_runtime_remains_usable() -> (
    None
):
    for bad_response in (None, []):
        runtime = AgentCliRuntime(agent=_HeadlessErrorAgent(), tools=_NoopTools())
        runtime.collaboration_mode = "plan"
        runtime.request_user_input_handler = lambda _payload, _bad=bad_response: _bad  # type: ignore[assignment]
        stdout = io.StringIO()

        code = main(
            ["--headless", "--prompt", _request_prompt(), "--json"],
            runtime=runtime,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        assert code == 2
        assert payload["tool_events"][-1]["name"] == "request_user_input"
        assert payload["tool_events"][-1]["ok"] is False
        assert payload["tool_events"][-1]["summary"] == "request_user_input cancelled"
        assert (
            payload["tool_events"][-1]["payload"]["error"]
            == "request_user_input was cancelled before receiving a response"
        )
        failed_item = _last_failed_item(payload["turn_events"])
        assert failed_item["status"] == "failed"
        assert (
            failed_item["error"]["message"]
            == "request_user_input was cancelled before receiving a response"
        )

        runtime.request_user_input_handler = lambda _payload: {"answers": {"confirm_path": "yes"}}
        followup_stdout = io.StringIO()
        followup_code = main(
            ["--headless", "--prompt", _request_prompt(), "--json"],
            runtime=runtime,
            stdout=followup_stdout,
            stderr=io.StringIO(),
        )
        followup_payload = json.loads(followup_stdout.getvalue())
        assert followup_code == 0
        assert followup_payload["tool_events"][-1]["ok"] is True
        assert json.loads(followup_payload["assistant_text"])["answers"]["confirm_path"][
            "answers"
        ] == ["yes"]


def test_headless_request_user_input_default_mode_disabled_emits_unavailable_error_item() -> None:
    runtime = AgentCliRuntime(agent=_HeadlessErrorAgent(), tools=_NoopTools())
    runtime.collaboration_mode = "default"
    runtime.default_mode_request_user_input = False
    _force_default_mode_request_user_input(runtime, False)
    runtime.request_user_input_handler = lambda _payload: {"answers": {"confirm_path": "yes"}}
    stdout = io.StringIO()

    code = main(
        ["--headless", "--prompt", _request_prompt(), "--json"],
        runtime=runtime,
        stdout=stdout,
        stderr=io.StringIO(),
    )

    payload = json.loads(stdout.getvalue())
    assert code == 2
    assert payload["tool_events"][-1]["name"] == "request_user_input"
    assert payload["tool_events"][-1]["ok"] is False
    assert payload["tool_events"][-1]["summary"] == "request_user_input unavailable"
    assert "unavailable in Default mode" in payload["assistant_text"]
    failed_item = _last_failed_item(payload["turn_events"])
    assert failed_item["status"] == "failed"
    assert "unavailable in Default mode" in failed_item["error"]["message"]


def test_app_server_session_run_request_user_input_non_dict_result_is_cancelled_with_failed_item() -> (
    None
):
    runtime = AgentCliRuntime(agent=_HeadlessErrorAgent(), tools=_NoopTools())
    runtime.collaboration_mode = "plan"
    runtime.request_user_input_handler = lambda _payload: []  # type: ignore[assignment]
    stdout = io.StringIO()
    stdin = io.StringIO(
        "\n".join(
            [
                json.dumps({"id": "init", "method": "initialize", "params": {}}),
                json.dumps({"method": "initialized", "params": {}}),
                json.dumps(
                    {
                        "id": "run-request-user-input-error",
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
    run_result = next(line for line in lines if line.get("id") == "run-request-user-input-error")
    response = run_result["result"]["response"]
    assert response["tool_events"][-1]["name"] == "request_user_input"
    assert response["tool_events"][-1]["ok"] is False
    assert (
        response["assistant_text"] == "request_user_input was cancelled before receiving a response"
    )
    failed_item = _last_failed_item(response["turn_events"])
    assert failed_item["status"] == "failed"
    assert (
        failed_item["error"]["message"]
        == "request_user_input was cancelled before receiving a response"
    )
    assert not any(
        line.get("method") == "item/tool/requestUserInput"
        for line in lines
        if isinstance(line, dict)
    )
