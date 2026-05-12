from __future__ import annotations

import pytest

from cli.agent_cli import memory_sync_runtime


def _scope() -> memory_sync_runtime.MemorySyncScope:
    return memory_sync_runtime.MemorySyncScope.from_values(
        tenant_id="tenant_alpha",
        user_id="user_1",
        project_id="project_a",
    )


def test_validate_record_scope_rejects_cross_tenant_payload() -> None:
    with pytest.raises(PermissionError):
        memory_sync_runtime.validate_record_scope(
            record={
                "memory_id": "mem_1",
                "tenant_id": "tenant_beta",
                "user_id": "user_1",
                "project_id": "project_a",
            },
            scope=_scope(),
        )


def test_validate_record_scope_rejects_cross_user_and_project_payload() -> None:
    with pytest.raises(PermissionError):
        memory_sync_runtime.validate_record_scope(
            record={
                "memory_id": "mem_1",
                "tenant_id": "tenant_alpha",
                "user_id": "user_2",
                "project_id": "project_a",
            },
            scope=_scope(),
        )

    with pytest.raises(PermissionError):
        memory_sync_runtime.validate_record_scope(
            record={
                "memory_id": "mem_1",
                "tenant_id": "tenant_alpha",
                "user_id": "user_1",
                "project_id": "project_b",
            },
            scope=_scope(),
        )


def test_push_request_rejects_mixed_multi_tenant_records() -> None:
    request = memory_sync_runtime.MemorySyncPushRequest(
        scope=_scope(),
        records=[
            {
                "memory_id": "mem_ok",
                "tenant_id": "tenant_alpha",
                "user_id": "user_1",
                "project_id": "project_a",
            },
            {
                "memory_id": "mem_cross_tenant",
                "tenant_id": "tenant_beta",
                "user_id": "user_1",
                "project_id": "project_a",
            },
        ],
    )

    with pytest.raises(PermissionError):
        memory_sync_runtime.NoopMemorySyncAdapter().push(request)


def test_pull_request_accepts_valid_scope_without_remote() -> None:
    request = memory_sync_runtime.MemorySyncPullRequest(scope=_scope(), since_cursor="c1", limit=10)
    result = memory_sync_runtime.NoopMemorySyncAdapter().pull(request)

    assert result.records == []
    assert result.next_cursor == "c1"
