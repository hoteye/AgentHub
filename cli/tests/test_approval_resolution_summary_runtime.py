from __future__ import annotations

from cli.agent_cli.runtime_services import approval_resolution_runtime
from cli.agent_cli.runtime_services import approval_resolution_summary_runtime


def test_background_teammate_summary_text_includes_workspace_write_markers_and_commands() -> None:
    text = approval_resolution_runtime.background_teammate_summary_text(
        title="background teammate submitted",
        approval_id="approval_1",
        task_id="bg_1",
        status="queued",
        task="inspect repository and summarize changed files" * 4,
        provider="glm",
        model="glm-5",
        reasoning_effort="medium",
        cwd="/repo",
        approval_policy="never",
        sandbox_mode="workspace-write",
        allowed_paths=["src"],
        blocked_paths=[".git"],
        timeout_seconds=30,
        queue_provider="rq",
        include_approval_commands=True,
    )

    assert "staged_run=true" in text
    assert "final_apply_required=true" in text
    assert "/approve approval_1" in text
    assert "/reject approval_1" in text
    assert "task=" in text


def test_background_teammate_submit_payload_preserves_shape_for_failure() -> None:
    payload = approval_resolution_summary_runtime.background_teammate_submit_payload(
        payload={
            "task": "inspect",
            "provider": "glm",
            "model": "glm-5",
            "reasoning_effort": "medium",
            "cwd": "/repo",
            "approval_policy": "never",
            "sandbox_mode": "workspace-write",
            "allowed_paths": ["src"],
            "blocked_paths": [".git"],
            "timeout_seconds": 30,
        },
        status="failed",
        ok=False,
        error="queue unavailable",
    )

    assert payload["ok"] is False
    assert payload["task_type"] == "teammate"
    assert payload["status"] == "failed"
    assert payload["provider"] == "glm"
    assert payload["allowed_paths"] == ["src"]
    assert payload["blocked_paths"] == [".git"]
    assert payload["error"] == "queue unavailable"
