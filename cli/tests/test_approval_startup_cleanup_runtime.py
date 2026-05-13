from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from cli.agent_cli.gateway_core import (
    InMemoryGatewayStateStore,
    JsonlGatewayStateStore,
    LazyJsonlGatewayStateStore,
    create_action_request,
    create_approval_ticket,
)
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_factory import build_persistent_runtime
from cli.agent_cli.runtime_services import approval_startup_cleanup_runtime
from cli.agent_cli.thread_store import ThreadStore


class _Agent:
    @staticmethod
    def provider_status() -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "test",
            "provider_model": "test-model",
        }

    @staticmethod
    def plan(*args, **kwargs):
        raise AssertionError("planner should not run during approval startup cleanup")


class _Tools:
    def __init__(self) -> None:
        self.shell_calls: list[str] = []

    def shell(self, command: str, **kwargs):
        self.shell_calls.append(command)
        raise AssertionError("stale approval cleanup must not execute shell commands")

    def shell_start(self, command: str, **kwargs):
        self.shell_calls.append(command)
        raise AssertionError("stale approval cleanup must not start shell sessions")


def _pending_shell_ticket(
    store: InMemoryGatewayStateStore, *, requested_at: datetime, command: str
):
    action = create_action_request(
        action_type="shell_command",
        connector_key="local_cli",
        plugin_name="local_cli",
        trace_id=f"trace_{command.replace(' ', '_')}",
        requested_by="test",
        payload={"command": command, "exec_mode": "exec_once"},
        approval_required=True,
    )
    ticket = create_approval_ticket(
        action,
        requested_by="test",
        reason="needs approval",
        summary="Approve shell command",
    )
    ticket = replace(
        ticket,
        requested_at=requested_at.replace(microsecond=0).isoformat(),
    )
    store.save_action_request(action)
    store.save_approval_ticket(ticket)
    return ticket


def test_startup_cleanup_declines_only_stale_pending_approvals_without_execution() -> None:
    now = datetime(2026, 4, 25, 10, 30, tzinfo=UTC)
    store = InMemoryGatewayStateStore()
    stale = _pending_shell_ticket(
        store,
        requested_at=now - timedelta(minutes=31),
        command="echo stale",
    )
    fresh = _pending_shell_ticket(
        store,
        requested_at=now - timedelta(minutes=29),
        command="echo fresh",
    )
    tools = _Tools()
    runtime = AgentCliRuntime(agent=_Agent(), tools=tools, gateway_state_store=store)

    updated = approval_startup_cleanup_runtime.decline_stale_pending_approvals_on_startup(
        runtime,
        stale_after_seconds=30 * 60,
        now=now,
    )

    assert [ticket.approval_id for ticket in updated] == [stale.approval_id]
    assert store.get_approval_ticket(stale.approval_id).status == "rejected"
    assert store.get_approval_ticket(stale.approval_id).decision_type == "decline"
    assert store.get_approval_ticket(stale.approval_id).decision_by == "system_startup"
    assert store.get_approval_ticket(fresh.approval_id).status == "pending"
    assert tools.shell_calls == []
    audits = store.list_audit_records(limit=10, approval_id=stale.approval_id)
    assert len(audits) == 1
    assert audits[0].details["execution_skipped"] is True


def test_startup_cleanup_skips_pending_approval_with_unparseable_requested_at() -> None:
    store = InMemoryGatewayStateStore()
    ticket = _pending_shell_ticket(
        store,
        requested_at=datetime(2026, 4, 25, 10, 0, tzinfo=UTC),
        command="echo malformed",
    )
    store.save_approval_ticket(replace(ticket, requested_at="not-a-date"))
    runtime = AgentCliRuntime(agent=_Agent(), tools=_Tools(), gateway_state_store=store)

    updated = approval_startup_cleanup_runtime.decline_stale_pending_approvals_on_startup(
        runtime,
        stale_after_seconds=1,
        now=datetime(2026, 4, 25, 11, 0, tzinfo=UTC),
    )

    assert updated == []
    assert store.get_approval_ticket(ticket.approval_id).status == "pending"


def test_persistent_runtime_runs_stale_pending_cleanup_on_startup(tmp_path: Path) -> None:
    gateway_path = tmp_path / "gateway"
    gateway_store = JsonlGatewayStateStore(gateway_path)
    thread_store = ThreadStore(tmp_path / "threads")
    stale = _pending_shell_ticket(
        gateway_store,
        requested_at=datetime.now(UTC) - timedelta(hours=2),
        command="echo persistent stale",
    )

    with (
        patch("cli.agent_cli.runtime_factory.ThreadStore.default", return_value=thread_store),
        patch(
            "cli.agent_cli.gateway_core.state_store._default_gateway_base_dir",
            return_value=gateway_path,
        ),
    ):
        runtime = build_persistent_runtime(
            resume_active_thread=False,
            start_thread_if_unavailable=False,
            stale_pending_approval_seconds=30 * 60,
        )

    wait_until_loaded = getattr(runtime.gateway_state_store, "wait_until_loaded", None)
    if callable(wait_until_loaded):
        assert wait_until_loaded(timeout=2)
    cleanup_wait = getattr(runtime, "_approval_startup_cleanup_thread", None)
    if cleanup_wait is not None:
        cleanup_wait.join(timeout=2)
    assert isinstance(runtime.gateway_state_store, LazyJsonlGatewayStateStore)
    assert runtime.gateway_state_store.get_approval_ticket(stale.approval_id).status == "rejected"
    reloaded = JsonlGatewayStateStore(tmp_path / "gateway")
    assert reloaded.get_approval_ticket(stale.approval_id).status == "rejected"


def test_lazy_jsonl_gateway_state_store_loads_existing_state_in_background(
    tmp_path: Path,
) -> None:
    gateway_path = tmp_path / "gateway"
    eager_store = JsonlGatewayStateStore(gateway_path)
    ticket = _pending_shell_ticket(
        eager_store,
        requested_at=datetime(2026, 4, 25, 10, 0, tzinfo=UTC),
        command="echo lazy",
    )

    lazy_store = LazyJsonlGatewayStateStore(gateway_path)

    assert lazy_store.base_dir == gateway_path
    assert lazy_store.wait_until_loaded(timeout=2)
    assert lazy_store.get_approval_ticket(ticket.approval_id).approval_id == ticket.approval_id


def test_persistent_runtime_starts_stale_cleanup_in_background(tmp_path: Path) -> None:
    thread_store = ThreadStore(tmp_path / "threads")

    with (
        patch("cli.agent_cli.runtime_factory.ThreadStore.default", return_value=thread_store),
        patch(
            "cli.agent_cli.gateway_core.state_store._default_gateway_base_dir",
            return_value=tmp_path / "gateway",
        ),
        patch(
            "cli.agent_cli.runtime_factory.approval_startup_cleanup_runtime.decline_stale_pending_approvals_on_startup",
        ) as cleanup,
    ):
        runtime = build_persistent_runtime(
            resume_active_thread=False,
            start_thread_if_unavailable=False,
            stale_pending_approval_seconds=30 * 60,
        )

        assert isinstance(runtime.gateway_state_store, LazyJsonlGatewayStateStore)
        thread = getattr(runtime, "_approval_startup_cleanup_thread", None)
        assert thread is not None
        thread.join(timeout=2)
        cleanup.assert_called_once()
