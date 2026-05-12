from __future__ import annotations

from typing import Any

from cli.agent_cli import runtime_runtime
from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime_kernels.codex_sidecar import approval as codex_approval


class CodexSidecarRuntimeGatewayMixin:
    """Gateway / approval helpers extracted from CodexSidecarRuntimeAdapter."""

    def save_gateway_action_request(self, item: Any) -> Any:
        return self.gateway_state_store.save_action_request(item)

    def save_gateway_approval_ticket(self, item: Any) -> Any:
        return self.gateway_state_store.save_approval_ticket(item)

    def append_gateway_audit_record(self, item: Any) -> Any:
        return self.gateway_state_store.append_audit_record(item)

    def list_approval_tickets(
        self,
        *,
        limit: int = 50,
        status: str | None = None,
    ) -> list[Any]:
        return self.gateway_state_store.list_approval_tickets(limit=limit, status=status)

    def approvals_event(self, *, limit: int = 20, status: str | None = None) -> Any:
        tickets = self.list_approval_tickets(limit=limit, status=status)
        rows = runtime_runtime.approval_list_rows(
            tickets=tickets,
            get_action_request_fn=self.gateway_state_store.get_action_request,
        )
        return runtime_runtime.approval_list_event(
            rows=rows,
            status=status,
            tool_event_factory=ToolEvent,
        )

    def decide_approval(
        self,
        approval_id: str,
        *,
        approved: bool | None = None,
        decision: Any = None,
        decided_by: str,
        decision_note: str = "",
    ) -> dict[str, Any]:
        resolved_decision = decision
        if resolved_decision is None:
            resolved_decision = "accept" if bool(approved) else "decline"
        result = codex_approval.decide_approval(
            self,
            approval_id,
            decision=resolved_decision,
            decided_by=decided_by,
            decision_note=decision_note,
        )
        request = None
        with self._pending_sidecar_approval_lock:
            request = self._pending_sidecar_approval_requests.pop(
                str(approval_id or "").strip(),
                None,
            )
        if request is not None:
            self.kernel.client.respond_to_server_request(
                request,
                dict(result.get("codex_sidecar_response") or {}),
            )
            request_id = getattr(request, "request_id", "")
            if request_id:
                self._server_request_registry.resolve(request_id, status="responded")
        return result
