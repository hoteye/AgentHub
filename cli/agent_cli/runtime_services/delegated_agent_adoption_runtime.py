from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.models import CommandExecutionResult, ToolEvent, generic_tool_call_item_events
from cli.agent_cli.providers.delegation_policy import normalize_wait_agent_metadata
from cli.agent_cli.runtime_services import delegated_agent_adoption_projection_helpers_runtime
from cli.agent_cli.runtime_services import delegated_agent_adoption_pure_helpers_runtime
from cli.agent_cli.runtime_services import delegated_agent_adoption_runtime_helpers
from cli.agent_cli.runtime_services import delegated_agent_adoption_validation_helpers_runtime

_ACTIVE_WAIT_STATUSES = {"queued", "starting", "running", "closing"}
_TERMINAL_WAIT_STATUSES = {"completed", "failed", "closed"}
MIN_WAIT_TIMEOUT_MS = 10_000
DEFAULT_WAIT_TIMEOUT_MS = 30_000
MAX_WAIT_TIMEOUT_MS = 3600 * 1000


def delegated_result_adoptable(session: Any) -> bool:
    return delegated_agent_adoption_pure_helpers_runtime.delegated_result_adoptable(session)


def _runtime_now_iso() -> str:
    return delegated_agent_adoption_pure_helpers_runtime.runtime_now_iso()


def _normalized_wait_timeout_ms(timeout_ms: Any) -> int:
    return delegated_agent_adoption_validation_helpers_runtime.normalized_wait_timeout_ms(
        timeout_ms,
        default_timeout_ms=DEFAULT_WAIT_TIMEOUT_MS,
        min_timeout_ms=MIN_WAIT_TIMEOUT_MS,
        max_timeout_ms=MAX_WAIT_TIMEOUT_MS,
    )


def _wait_timeout_seconds(timeout_ms: Any) -> float | None:
    return delegated_agent_adoption_validation_helpers_runtime.wait_timeout_seconds(timeout_ms)


def _sync_delegated_run_record(
    runtime: Any,
    session: Any,
    *,
    forced_status: str | None = None,
    forced_summary: str | None = None,
) -> None:
    delegated_agent_adoption_runtime_helpers.sync_delegated_run_record(
        runtime,
        session,
        forced_status=forced_status,
        forced_summary=forced_summary,
    )


def _terminal_wait_status_hint(session: Any) -> str:
    return delegated_agent_adoption_projection_helpers_runtime.terminal_wait_status_hint(
        session,
        terminal_wait_statuses=_TERMINAL_WAIT_STATUSES,
    )


def _promote_terminal_wait_status(session: Any) -> bool:
    return delegated_agent_adoption_projection_helpers_runtime.promote_terminal_wait_status(
        session,
        terminal_wait_status_hint_fn=_terminal_wait_status_hint,
        now_iso_fn=_runtime_now_iso,
    )


def _delegated_session_if_present(runtime: Any, agent_id: str) -> Any | None:
    return delegated_agent_adoption_pure_helpers_runtime.delegated_session_if_present(runtime, agent_id)


def _codex_wait_status_wire(session: Any) -> Any | None:
    return delegated_agent_adoption_projection_helpers_runtime.codex_wait_status_wire(
        session,
        terminal_wait_status_hint_fn=_terminal_wait_status_hint,
    )


def _codex_wait_result(
    *,
    agent_ids: list[str],
    statuses: dict[str, Any],
    timed_out: bool,
    timeout_ms: int,
) -> CommandExecutionResult:
    return delegated_agent_adoption_projection_helpers_runtime.codex_wait_result(
        agent_ids=agent_ids,
        statuses=statuses,
        timed_out=timed_out,
        timeout_ms=timeout_ms,
        tool_event_factory=ToolEvent,
        command_result_factory=CommandExecutionResult,
        generic_tool_call_item_events_fn=generic_tool_call_item_events,
    )


def _codex_wait_status_snapshot(
    runtime: Any,
    agent_ids: list[str],
) -> tuple[dict[str, Any], list[tuple[str, Any]]]:
    return delegated_agent_adoption_projection_helpers_runtime.codex_wait_status_snapshot(
        runtime,
        agent_ids,
        delegated_session_if_present_fn=_delegated_session_if_present,
        promote_terminal_wait_status_fn=_promote_terminal_wait_status,
        codex_wait_status_wire_fn=_codex_wait_status_wire,
    )


def mark_delegated_result_adopted(
    runtime: Any,
    session: Any,
    *,
    now_iso_fn: Callable[[], str],
) -> bool:
    return delegated_agent_adoption_runtime_helpers.mark_delegated_result_adopted_impl(
        runtime,
        session,
        now_iso_fn=now_iso_fn,
        sync_delegated_run_record_fn=_sync_delegated_run_record,
    )


def wait_agent_result(
    runtime: Any,
    agent_id: str,
    *,
    timeout_ms: Any = 30000,
    reason: str | None = None,
    wait_required: Any = None,
) -> CommandExecutionResult:
    return delegated_agent_adoption_runtime_helpers.wait_agent_result_impl(
        runtime,
        agent_id,
        timeout_ms=timeout_ms,
        reason=reason,
        wait_required=wait_required,
        normalize_wait_agent_metadata_fn=normalize_wait_agent_metadata,
        wait_timeout_seconds_fn=_wait_timeout_seconds,
        promote_terminal_wait_status_fn=_promote_terminal_wait_status,
        runtime_now_iso_fn=_runtime_now_iso,
        sync_delegated_run_record_fn=_sync_delegated_run_record,
        tool_event_factory=ToolEvent,
        command_result_factory=CommandExecutionResult,
        generic_tool_call_item_events_fn=generic_tool_call_item_events,
        active_wait_statuses=_ACTIVE_WAIT_STATUSES,
    )


def wait_agents_result(
    runtime: Any,
    agent_ids: list[str],
    *,
    timeout_ms: Any = 30000,
    reason: str | None = None,
    wait_required: Any = None,
    codex_style: bool = False,
    wait_agent_result_fn: Callable[..., CommandExecutionResult],
) -> CommandExecutionResult:
    return delegated_agent_adoption_runtime_helpers.wait_agents_result_impl(
        runtime,
        agent_ids,
        timeout_ms=timeout_ms,
        reason=reason,
        wait_required=wait_required,
        codex_style=codex_style,
        wait_agent_result_fn=wait_agent_result_fn,
        normalized_wait_agent_ids_fn=delegated_agent_adoption_validation_helpers_runtime.normalized_wait_agent_ids,
        normalize_wait_agent_metadata_fn=normalize_wait_agent_metadata,
        normalized_wait_timeout_ms_fn=_normalized_wait_timeout_ms,
        wait_timeout_seconds_fn=_wait_timeout_seconds,
        codex_wait_status_snapshot_fn=_codex_wait_status_snapshot,
        codex_wait_status_wire_fn=_codex_wait_status_wire,
        codex_wait_result_fn=_codex_wait_result,
        promote_terminal_wait_status_fn=_promote_terminal_wait_status,
        active_wait_statuses=_ACTIVE_WAIT_STATUSES,
    )
