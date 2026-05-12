from __future__ import annotations

import json
from pathlib import Path

from cli.agent_cli.background_tasks import tasks_support_runtime, tasks_teammate_runtime


def _projection(response_payload: dict[str, object], *, cwd: Path) -> dict[str, object]:
    return tasks_teammate_runtime.teammate_response_projection(
        response_payload=response_payload,
        live_cwd=cwd,
        response_status_mapping_fn=tasks_support_runtime.response_status_mapping,
        mapping_dict_fn=tasks_support_runtime.mapping_dict,
        route_report_from_status_fn=tasks_support_runtime.route_report_from_status,
        teammate_commands_fn=tasks_support_runtime.teammate_commands,
        teammate_test_commands_fn=tasks_support_runtime.teammate_test_commands,
        teammate_modified_files_fn=tasks_support_runtime.teammate_modified_files,
    )


def test_running_projection_keeps_effective_command_from_jsonl(tmp_path: Path) -> None:
    state = tasks_teammate_runtime.new_headless_jsonl_state()
    raw_event = {
        "type": "item.completed",
        "item": {
            "id": "item_1",
            "type": "command_execution",
            "command": "pytest -q tests/test_demo.py",
            "effective_command": "python /tmp/test_lock_runner.py -- pytest -q tests/test_demo.py",
            "aggregated_output": "1 passed",
            "exit_code": 0,
            "status": "completed",
            "command_policy": {
                "allowed": True,
                "test_policy": "scoped_only",
            },
        },
    }
    tasks_teammate_runtime.consume_headless_jsonl_line(state, json.dumps(raw_event, ensure_ascii=False))

    synthetic_payload = tasks_teammate_runtime.synthetic_response_payload_from_jsonl_state(state)
    tool_events = list(synthetic_payload.get("tool_events") or [])
    assert len(tool_events) == 1
    payload = dict(tool_events[0].get("payload") or {})
    assert payload["command"] == "pytest -q tests/test_demo.py"
    assert payload["effective_command"] == "python /tmp/test_lock_runner.py -- pytest -q tests/test_demo.py"
    assert dict(payload.get("command_policy") or {}).get("allowed") is True

    projection = _projection(synthetic_payload, cwd=tmp_path)
    commands = list(projection["commands"] or [])
    assert "pytest -q tests/test_demo.py" in commands
    assert "python /tmp/test_lock_runner.py -- pytest -q tests/test_demo.py" in commands
    assert "pytest -q tests/test_demo.py" in list(projection["test_commands"] or [])
    assert any(
        str(item.get("effective_command") or "").startswith("python /tmp/test_lock_runner.py")
        for item in list(projection.get("command_policies") or [])
    )


def test_policy_denied_is_visible_in_running_and_terminal_projection(tmp_path: Path) -> None:
    state = tasks_teammate_runtime.new_headless_jsonl_state()
    raw_event = {
        "type": "item.completed",
        "item": {
            "id": "item_2",
            "type": "command_execution",
            "command": "pytest",
            "aggregated_output": "",
            "exit_code": 1,
            "status": "policy_denied",
            "error_code": "test_scope_required",
        },
    }
    tasks_teammate_runtime.consume_headless_jsonl_line(state, json.dumps(raw_event, ensure_ascii=False))
    synthetic_payload = tasks_teammate_runtime.synthetic_response_payload_from_jsonl_state(state)
    running_projection = _projection(synthetic_payload, cwd=tmp_path)
    running_commands = list(running_projection["commands"] or [])
    assert "pytest" in running_commands
    assert "policy_denied: pytest" in running_commands
    running_policies = list(running_projection.get("command_policies") or [])
    assert running_policies
    assert running_policies[0]["policy_denied"] is True
    assert running_policies[0]["error_code"] == "test_scope_required"

    response_payload = {
        "tool_events": [
            {
                "name": "exec_command",
                "payload": {
                    "command": "pytest tests/test_scope.py",
                    "status": "policy_denied",
                    "command_policy": {
                        "allowed": False,
                        "error_code": "test_scope_required",
                    },
                },
            }
        ]
    }
    terminal_projection = _projection(response_payload, cwd=tmp_path)
    terminal_commands = list(terminal_projection["commands"] or [])
    assert "pytest tests/test_scope.py" in terminal_commands
    assert "policy_denied: pytest tests/test_scope.py" in terminal_commands
    terminal_policies = list(terminal_projection.get("command_policies") or [])
    assert terminal_policies
    assert terminal_policies[0]["policy_denied"] is True
    assert terminal_policies[0]["error_code"] == "test_scope_required"


def test_commands_and_test_commands_compatibility_without_policy_fields() -> None:
    response_payload = {
        "tool_events": [
            {
                "name": "exec_command",
                "payload": {
                    "command": "pytest -q tests/test_demo.py",
                },
            }
        ]
    }
    commands = tasks_support_runtime.teammate_commands(response_payload)
    test_commands = tasks_support_runtime.teammate_test_commands(commands)
    assert commands == ["pytest -q tests/test_demo.py"]
    assert test_commands == ["pytest -q tests/test_demo.py"]
    assert tasks_support_runtime.teammate_command_policy_summary(response_payload)[0]["policy_denied"] is False
