from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cli.replay_integration.harness import ReplayIntegrationHarness
from cli.replay_integration.schema import ReplayCassette, ReplayManifest, ReplaySessionMetadata
from cli.replay_integration.tool_replay import ReplayToolExecutor
from cli.replay_integration.workspace_snapshot import capture_environment_snapshot, capture_workspace_snapshot
from cli.tests.replay_integration.formal_cases import (
    build_planner_case_cassette,
    formal_planner_cases,
    make_openai_planner,
)

def _strict_harness_for_workspace(cwd: str) -> ReplayIntegrationHarness:
    fixed_dt = datetime(2026, 3, 31, tzinfo=timezone.utc)
    cassette = ReplayCassette(
        manifest=ReplayManifest(
            name="drift-baseline",
            drift_policy="strict",
            session=ReplaySessionMetadata(
                provider="replay",
                model="gpt-5.4",
                transport_kind="responses_http",
                cwd=cwd,
                current_date="2026-03-31",
                timezone="UTC",
            ),
            environment_snapshot=capture_environment_snapshot(
                cwd=cwd,
                shell="bash",
                network_access=False,
                current_dt=fixed_dt,
            ),
            workspace_snapshot=capture_workspace_snapshot(cwd),
        )
    )
    return ReplayIntegrationHarness.from_cassette(cassette)

@pytest.mark.parametrize("case", formal_planner_cases(), ids=lambda case: case.case_id)
def test_formal_planner_replay_cases(case) -> None:
    planner = make_openai_planner()
    cassette = build_planner_case_cassette(planner, case)
    replay_client = ReplayIntegrationHarness.from_cassette(cassette).provider_client
    planner.client = replay_client
    tool_executor = ReplayToolExecutor(cassette)

    history = []
    observed = []
    for step in case.steps:
        intent = planner.plan(step.user_text, history, tool_executor=tool_executor)
        observed.append(intent.assistant_text)
        history.extend(
            [
                {"role": "user", "content": step.user_text},
                {"role": "assistant", "content": intent.assistant_text},
            ]
        )

    assert observed == [step.assistant_text for step in case.steps]
    assert len(replay_client.responses.requests) == len(cassette.rounds)
    assert not replay_client.responses.remaining_rounds()
    assert not tool_executor.remaining_tool_calls()

def test_formal_drift_case_blocks_on_cwd_change(tmp_path) -> None:
    workspace_a = tmp_path / "workspace-a"
    workspace_b = tmp_path / "workspace-b"
    workspace_a.mkdir()
    workspace_b.mkdir()
    (workspace_a / "AENGTHUB.md").write_text("repo instructions", encoding="utf-8")
    (workspace_b / "AENGTHUB.md").write_text("repo instructions", encoding="utf-8")

    harness = _strict_harness_for_workspace(str(workspace_a))
    report = harness.check_drift(
        cwd=str(workspace_b),
        shell="bash",
        network_access=False,
        current_dt=datetime(2026, 3, 31, tzinfo=timezone.utc),
    )

    changed_fields = {(issue.scope, issue.field) for issue in report.issues}
    assert report.blocking
    assert ("environment", "cwd") in changed_fields
    assert ("workspace", "cwd") in changed_fields

def test_formal_drift_case_blocks_on_agents_md_change(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    agents_doc = workspace / "AENGTHUB.md"
    agents_doc.write_text("version one", encoding="utf-8")

    harness = _strict_harness_for_workspace(str(workspace))
    agents_doc.write_text("version two", encoding="utf-8")
    report = harness.check_drift(
        cwd=str(workspace),
        shell="bash",
        network_access=False,
        current_dt=datetime(2026, 3, 31, tzinfo=timezone.utc),
    )

    changed_fields = {(issue.scope, issue.field) for issue in report.issues}
    assert report.blocking
    assert ("workspace", "instructions_digest") in changed_fields or ("workspace", "docs") in changed_fields
