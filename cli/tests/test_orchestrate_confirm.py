from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from cli.agent_cli.orchestration import taskbook_runtime as taskbook_runtime_service
from cli.agent_cli.runtime_core import run_command_text_result


TASKBOOK_MARKDOWN = """# Confirmed orchestration run

### CARD-001: Research workflow surface
- goal: research current workflow surface and summarize gaps
- owned_files: docs/research_notes.md
- acceptance_criteria: capture the workflow findings

### CARD-002: Update runtime wiring
- goal: patch runtime orchestration wiring after research completes
- owned_files: cli/agent_cli/runtime.py
- acceptance_criteria: runtime wiring updated
- depends_on: CARD-001
"""


class _RuntimeStub:
    class _Agent:
        @staticmethod
        def provider_status() -> dict[str, str]:
            return {
                "provider_name": "openai",
                "provider_model": "gpt-5.4",
                "provider_reasoning_effort": "high",
            }

    def __init__(self, root: Path) -> None:
        self.cwd = Path(root)
        self.thread_id = "thread_confirm_test"
        self.agent = self._Agent()
        self.request_payloads: list[dict[str, Any]] = []
        self._request_responses: list[Any] = []
        self.request_user_input_handler = self._request_user_input_handler
        self._orchestration_runtime_services_cache = None
        self._orchestration_runtime_services_cwd = ""

    def queue_request_response(self, response: Any) -> None:
        self._request_responses.append(response)

    def _request_user_input_handler(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        self.request_payloads.append(dict(payload or {}))
        if not self._request_responses:
            return None
        next_response = self._request_responses.pop(0)
        if callable(next_response):
            return next_response(payload)
        return dict(next_response or {}) if isinstance(next_response, dict) else None


def _line_value(text: str, key: str) -> str:
    prefix = f"{key}="
    for raw_line in str(text or "").splitlines():
        line = str(raw_line or "").strip()
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def test_orchestrate_confirm_creates_run_only_after_confirmation() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        runtime = _RuntimeStub(Path(tmpdir))
        runtime.queue_request_response(
            {"answers": {"taskbook_action": {"answers": ["Confirm and start"]}}}
        )

        result = run_command_text_result(runtime, f"/orchestrate_confirm {TASKBOOK_MARKDOWN}")

        assert "orchestration confirmation accepted" in result.assistant_text
        assert "orchestration run created" in result.assistant_text
        run_id = _line_value(result.assistant_text, "run_id")
        assert run_id.startswith("run_")

        services = taskbook_runtime_service.runtime_services(runtime)
        run = services.storage.read_run(run_id)
        assert run is not None
        assert run.objective == "Confirmed orchestration run"
        assert len(runtime.request_payloads) == 1
        question = runtime.request_payloads[0]["questions"][0]["question"]
        assert "Taskbook preview" in question
        assert "Cards: 2" in question


def test_orchestrate_confirm_cancel_does_not_create_run() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        runtime = _RuntimeStub(Path(tmpdir))
        runtime.queue_request_response(
            {"answers": {"taskbook_action": {"answers": ["Cancel"]}}}
        )

        result = run_command_text_result(runtime, f"/orchestrate_confirm {TASKBOOK_MARKDOWN}")

        assert "orchestration confirmation cancelled" in result.assistant_text
        assert "no orchestration run was created" in result.assistant_text
        workflows, count = taskbook_runtime_service.list_orchestration_workflows(runtime)
        assert workflows == []
        assert count == 0


def test_orchestrate_confirm_view_full_then_confirm() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        runtime = _RuntimeStub(Path(tmpdir))
        runtime.queue_request_response(
            {"answers": {"taskbook_action": {"answers": ["View full taskbook and cards"]}}}
        )
        runtime.queue_request_response(
            {"answers": {"taskbook_action": {"answers": ["Confirm and start"]}}}
        )

        result = run_command_text_result(runtime, f"/orchestrate_confirm {TASKBOOK_MARKDOWN}")

        assert "orchestration confirmation accepted" in result.assistant_text
        assert len(runtime.request_payloads) == 2
        first_question = runtime.request_payloads[0]["questions"][0]["question"]
        second_question = runtime.request_payloads[1]["questions"][0]["question"]
        assert "Taskbook preview" in first_question
        assert "Taskbook preview (full)" in second_question
        assert "### CARD-001: Research workflow surface" in second_question


def test_orchestrate_confirm_adjusts_constraints_before_creating_run() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        runtime = _RuntimeStub(Path(tmpdir))
        runtime.queue_request_response(
            {"answers": {"taskbook_action": {"answers": ["Adjust planning"]}}}
        )
        runtime.queue_request_response(
            {
                "answers": {
                    "scope_preference": {"answers": ["Tighten scope"]},
                    "workspace_policy": {"answers": ["Require approval before live workspace writes"]},
                    "max_parallel_cards": {"answers": ["1 parallel slot"]},
                }
            }
        )
        runtime.queue_request_response(
            {"answers": {"extra_requirements": {"answers": ["Focused patch only"]}}}
        )
        runtime.queue_request_response(
            {"answers": {"taskbook_action": {"answers": ["Confirm and start"]}}}
        )

        result = run_command_text_result(runtime, f"/orchestrate_confirm {TASKBOOK_MARKDOWN}")

        assert "orchestration confirmation accepted" in result.assistant_text
        assert "planning_adjustments=scope: tighten current scope" in result.assistant_text
        run_id = _line_value(result.assistant_text, "run_id")
        services = taskbook_runtime_service.runtime_services(runtime)
        run = services.storage.read_run(run_id)
        taskbook = services.storage.latest_taskbook(run_id)
        card = services.storage.read_card_spec(run_id, "CARD-002")

        assert run is not None
        assert taskbook is not None
        assert card is not None
        assert run.global_constraints["scope_preference"] == "tighten_scope"
        assert run.global_constraints["workspace_policy"] == "approval_before_live_workspace_writes"
        assert run.global_constraints["max_parallel_cards"] == 1
        assert run.global_constraints["extra_requirements"] == "Focused patch only"
        assert taskbook.global_rules["scope_preference"] == "tighten_scope"
        assert taskbook.global_rules["workspace_policy"] == "approval_before_live_workspace_writes"
        assert taskbook.global_rules["max_parallel_cards"] == 1
        assert "Focused patch only" in taskbook.assumptions
        assert card.can_run_in_parallel is False
        assert "operator approval" in " ".join(card.handoff_requirements).lower()

        regenerated_question = runtime.request_payloads[3]["questions"][0]["question"]
        assert "Current planning adjustments:" in regenerated_question
        assert "scope: tighten current scope" in regenerated_question
