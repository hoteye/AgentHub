from __future__ import annotations

from unittest.mock import patch

import pytest

from cli.agent_cli import memory_store_runtime
from cli.agent_cli import memory_sync_runtime


def test_scope_requires_tenant_user_project_ids() -> None:
    with pytest.raises(memory_sync_runtime.MemorySyncContractError):
        memory_sync_runtime.MemorySyncScope.from_values(tenant_id="", user_id="u", project_id="p")
    with pytest.raises(memory_sync_runtime.MemorySyncContractError):
        memory_sync_runtime.MemorySyncScope.from_values(tenant_id="t", user_id="", project_id="p")
    with pytest.raises(memory_sync_runtime.MemorySyncContractError):
        memory_sync_runtime.MemorySyncScope.from_values(tenant_id="t", user_id="u", project_id="")


def test_noop_adapter_push_validates_and_accepts_memory_ids() -> None:
    scope = memory_sync_runtime.MemorySyncScope.from_values(
        tenant_id="tenant_a", user_id="user_a", project_id="proj_a"
    )
    request = memory_sync_runtime.MemorySyncPushRequest(
        scope=scope,
        records=[
            {
                "memory_id": "mem_1",
                "tenant_id": "tenant_a",
                "user_id": "user_a",
                "project_id": "proj_a",
            },
            {
                "memory_id": "mem_2",
                "tenant_id": "tenant_a",
                "user_id": "user_a",
                "project_id": "proj_a",
            },
        ],
    )

    result = memory_sync_runtime.NoopMemorySyncAdapter().push(request)
    assert result.accepted_ids == ["mem_1", "mem_2"]
    assert result.rejected_ids == []


def test_push_contract_rejects_scope_mismatch() -> None:
    scope = memory_sync_runtime.MemorySyncScope.from_values(
        tenant_id="tenant_a", user_id="user_a", project_id="proj_a"
    )
    request = memory_sync_runtime.MemorySyncPushRequest(
        scope=scope,
        records=[
            {
                "memory_id": "mem_bad",
                "tenant_id": "tenant_b",
                "user_id": "user_a",
                "project_id": "proj_a",
            }
        ],
    )

    with pytest.raises(PermissionError):
        memory_sync_runtime.validate_push_request(request)


def test_pull_contract_requires_positive_limit() -> None:
    scope = memory_sync_runtime.MemorySyncScope.from_values(
        tenant_id="tenant_a", user_id="user_a", project_id="proj_a"
    )
    with pytest.raises(memory_sync_runtime.MemorySyncContractError):
        memory_sync_runtime.validate_pull_request(
            memory_sync_runtime.MemorySyncPullRequest(scope=scope, limit=0)
        )


def test_conflict_resolution_prefers_last_write_wins() -> None:
    result = memory_sync_runtime.resolve_memory_conflict(
        local_record={"memory_id": "mem_1", "updated_at": "2026-04-09T10:00:00+00:00", "source": "local"},
        remote_record={"memory_id": "mem_1", "updated_at": "2026-04-09T11:00:00+00:00", "source": "remote"},
    )

    assert result["winner"]["source"] == "remote"
    assert result["reason"] == "last_write_wins_remote"


def test_conflict_resolution_uses_source_priority_when_timestamps_tie() -> None:
    result = memory_sync_runtime.resolve_memory_conflict(
        local_record={"memory_id": "mem_1", "updated_at": "2026-04-09T10:00:00+00:00", "source": "local"},
        remote_record={"memory_id": "mem_1", "updated_at": "2026-04-09T10:00:00+00:00", "source": "remote"},
        source_priority={"local": 50, "remote": 10},
    )

    assert result["winner"]["source"] == "local"
    assert result["reason"] == "source_priority_local"


def test_conflict_resolution_uses_tombstone_when_ties_remain() -> None:
    result = memory_sync_runtime.resolve_memory_conflict(
        local_record={"memory_id": "mem_1", "updated_at": "2026-04-09T10:00:00+00:00", "source": "local", "status": "active"},
        remote_record={
            "memory_id": "mem_1",
            "updated_at": "2026-04-09T10:00:00+00:00",
            "source": "remote",
            "tombstone": True,
            "status": "deleted",
        },
        source_priority={"local": 10, "remote": 10},
    )

    assert bool(result["winner"]["tombstone"]) is True
    assert result["reason"] == "tombstone_remote"


def test_memory_sync_opt_in_and_local_fallback_helpers() -> None:
    with patch.dict("os.environ", {memory_store_runtime.MEMORY_SYNC_OPT_IN_ENV: ""}, clear=False):
        assert memory_store_runtime.memory_sync_allowed() is False
        assert memory_store_runtime.prefer_local_store_fallback(sync_enabled=None, remote_available=True) is True

    with patch.dict("os.environ", {memory_store_runtime.MEMORY_SYNC_OPT_IN_ENV: "true"}, clear=False):
        assert memory_store_runtime.memory_sync_allowed() is True
        assert memory_store_runtime.prefer_local_store_fallback(sync_enabled=None, remote_available=True) is False
        assert memory_store_runtime.prefer_local_store_fallback(sync_enabled=None, remote_available=False) is True

    assert memory_sync_runtime.memory_sync_opt_in_enabled("enabled") is True
