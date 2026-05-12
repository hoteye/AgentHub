from __future__ import annotations

from cli.agent_cli.tools_core.command_execution_acceptance_runtime import (
    run_command_execution_wave02_acceptance,
)


def test_wave02_command_execution_acceptance_suite_passes() -> None:
    report = run_command_execution_wave02_acceptance()

    assert report["suite"] == "command_execution_wave02_acceptance"
    assert report["passed"] is True
    assert [case["name"] for case in report["cases"]] == [
        "one_shot",
        "interactive_session",
        "empty_poll",
        "terminate",
    ]
    assert all(case["passed"] for case in report["cases"])
