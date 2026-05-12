from __future__ import annotations

from typing import Any

from cli.agent_cli.ui import approval_surface_runtime
from cli.agent_cli.ui.status_controller_approval_overlay_runtime import (
    StatusControllerApprovalOverlayRuntimeMixin,
)
from cli.agent_cli.ui.status_controller_approval_state_runtime import (
    StatusControllerApprovalStateRuntimeMixin,
)
from cli.agent_cli.ui.status_controller_models import (
    LATEST_PENDING_APPROVAL_ID_STATUS_KEY,
    PENDING_APPROVALS_STATUS_KEY,
)


class StatusControllerApprovalRuntimeMixin(
    StatusControllerApprovalOverlayRuntimeMixin,
    StatusControllerApprovalStateRuntimeMixin,
):
    def _sync_pending_approval_surface_state(self) -> None:
        self._prune_resolved_tab_pending_approvals()
        if getattr(self, "_tab_manager", None) is not None:
            active_order = self._active_tab_pending_approval_order()
            if not active_order and not self._all_tab_pending_approval_ids():
                session = self._tab_session_for_pending_surface()
                allow_legacy_hydration = bool(
                    getattr(session, "allow_legacy_approval_hydration", False)
                )
                if allow_legacy_hydration:
                    for ticket in self._runtime_pending_approval_tickets():
                        legacy_id = str(getattr(ticket, "approval_id", "") or "").strip()
                        if legacy_id:
                            self._set_tab_pending_approval(legacy_id, pending=True)
                    if session is not None:
                        session.allow_legacy_approval_hydration = False
                    active_order = self._active_tab_pending_approval_order()
            tickets = self._pending_approval_tickets()
            tickets_by_id = {
                str(getattr(ticket, "approval_id", "") or "").strip(): ticket for ticket in tickets
            }
            if not active_order:
                self.status_data[PENDING_APPROVALS_STATUS_KEY] = "0"
                self.status_data[LATEST_PENDING_APPROVAL_ID_STATUS_KEY] = "-"
                self._clear_pending_approval_surface_state()
                self._approval_overlay_queue = []
                self._dismiss_approval_overlay()
                return
            approval_id = active_order[0]
            self.status_data[PENDING_APPROVALS_STATUS_KEY] = str(len(active_order))
            self.status_data[LATEST_PENDING_APPROVAL_ID_STATUS_KEY] = approval_id
            if approval_id == str(
                getattr(self, "_pending_approval_surface_id", "") or ""
            ).strip() and list(getattr(self, "_pending_approval_surface_commands", []) or []):
                self._drain_approval_overlay_queue()
                return
            commands: list[str] = []
            ticket = tickets_by_id.get(approval_id)
            if ticket is not None:
                commands = approval_surface_runtime.approval_commands(
                    approval_id=approval_id,
                    available_decisions=getattr(ticket, "available_decisions", None),
                    allow_generic_fallback=True,
                )
            if not commands:
                commands = approval_surface_runtime.approval_commands(
                    approval_id=approval_id,
                    allow_generic_fallback=True,
                )
            self._pending_approval_surface_id = approval_id
            self._pending_approval_surface_commands = commands
            self._enqueue_pending_approval_overlay(approval_id)
            return
        tickets = self._pending_approval_tickets()
        latest_ticket = tickets[0] if tickets else None
        if latest_ticket is not None:
            self.status_data[PENDING_APPROVALS_STATUS_KEY] = str(len(tickets))
            self.status_data[LATEST_PENDING_APPROVAL_ID_STATUS_KEY] = str(
                getattr(latest_ticket, "approval_id", "") or "-"
            )
        else:
            approval_id = str(
                self.status_data.get(LATEST_PENDING_APPROVAL_ID_STATUS_KEY) or ""
            ).strip()
            if approval_id not in {"", "-"} and self._approval_ticket_status(approval_id) not in {
                "",
                "pending",
            }:
                self.status_data[PENDING_APPROVALS_STATUS_KEY] = "0"
                self.status_data[LATEST_PENDING_APPROVAL_ID_STATUS_KEY] = "-"
        pending_approvals = self._pending_approval_count()
        if pending_approvals <= 0:
            self._clear_pending_approval_surface_state()
            self._approval_overlay_queue = []
            self._approval_overlay_suppressed_state().clear()
            self._dismiss_approval_overlay()
            return
        approval_id = str(self.status_data.get(LATEST_PENDING_APPROVAL_ID_STATUS_KEY) or "").strip()
        if approval_id in {"", "-"} and tickets:
            approval_id = str(getattr(tickets[0], "approval_id", "") or "").strip()
        if approval_id in {"", "-"}:
            self._clear_pending_approval_surface_state()
            self._drain_approval_overlay_queue()
            return
        if approval_id == str(
            getattr(self, "_pending_approval_surface_id", "") or ""
        ).strip() and list(getattr(self, "_pending_approval_surface_commands", []) or []):
            self._drain_approval_overlay_queue()
            return
        commands: list[str] = []
        ticket = next(
            (
                item
                for item in tickets
                if str(getattr(item, "approval_id", "") or "").strip() == approval_id
            ),
            None,
        )
        if ticket is not None:
            commands = approval_surface_runtime.approval_commands(
                approval_id=approval_id,
                available_decisions=getattr(ticket, "available_decisions", None),
                allow_generic_fallback=True,
            )
        if not commands:
            commands = approval_surface_runtime.approval_commands(
                approval_id=approval_id,
                allow_generic_fallback=True,
            )
        self._pending_approval_surface_id = approval_id
        self._pending_approval_surface_commands = commands
        self._enqueue_pending_approval_overlay(approval_id)

    def _note_pending_approval_activity(self, event: Any, tab_id: str | None = None) -> None:
        if event is None:
            return
        mgr = getattr(self, "_tab_manager", None)
        active_tab_id = str(getattr(mgr, "active_tab_id", "") or "").strip()
        target_tab_id = str(tab_id or active_tab_id or "").strip()
        is_active_tab = not target_tab_id or not active_tab_id or target_tab_id == active_tab_id
        code = str(getattr(event, "code", "") or "").strip().lower()
        raw = str(getattr(event, "detail", "") or "")
        params = dict(getattr(event, "params", {}) or {})
        approval_id = str(
            params.get("approval_id") or ""
        ).strip() or approval_surface_runtime.approval_id_from_detail(raw)
        if code.startswith("approval.request."):
            if not approval_id:
                return
            self._set_tab_pending_approval(approval_id, pending=True, tab_id=target_tab_id)
            if not is_active_tab:
                self._refresh_tab_pending_interaction_indicators()
                return
            active_order = self._active_tab_pending_approval_order()
            if active_order:
                self.status_data[PENDING_APPROVALS_STATUS_KEY] = str(len(active_order))
                self.status_data[LATEST_PENDING_APPROVAL_ID_STATUS_KEY] = active_order[0]
            active_overlay_id = str(getattr(self, "_approval_overlay_active_id", "") or "").strip()
            if active_overlay_id and active_overlay_id != approval_id:
                self._enqueue_pending_approval_overlay(approval_id)
                return
            self._pending_approval_surface_id = approval_id
            self._pending_approval_surface_commands = approval_surface_runtime.approval_commands(
                approval_id=approval_id,
                available_decisions=params.get("available_decisions"),
                raw=raw,
                allow_generic_fallback=True,
            )
            self._enqueue_pending_approval_overlay(approval_id)
            return
        if code.startswith("approval.decision") and approval_id:
            self._set_tab_pending_approval(approval_id, pending=False, tab_id=target_tab_id)
            if not is_active_tab:
                self._refresh_tab_pending_interaction_indicators()
                return
            cached_id = str(getattr(self, "_pending_approval_surface_id", "") or "").strip()
            if cached_id == approval_id:
                self._clear_pending_approval_surface_state()
            self._resolve_pending_approval_overlay(approval_id)
