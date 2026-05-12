from __future__ import annotations

from typing import Any


class StatusControllerApprovalStateRuntimeMixin:
    def _tab_pending_interaction_summary(self) -> list[dict[str, Any]]:
        mgr = getattr(self, "_tab_manager", None)
        tabs = getattr(mgr, "_tabs", None)
        order = list(getattr(mgr, "_tab_order", []) or [])
        if not isinstance(tabs, dict):
            return []
        if not order:
            order = list(tabs.keys())
        result: list[dict[str, Any]] = []
        for tab_id in order:
            session = tabs.get(tab_id)
            if session is None:
                continue
            approval_ids = [
                str(item or "").strip()
                for item in list(getattr(session, "pending_approvals", []) or [])
                if str(item or "").strip()
            ]
            has_request_user_input = bool(
                getattr(session, "pending_request_user_input", None) is not None
            )
            total = len(approval_ids) + (1 if has_request_user_input else 0)
            if total <= 0:
                continue
            label = str(
                getattr(session, "thread_name", "")
                or getattr(session, "top_title_text", "")
                or tab_id
            ).strip()
            result.append(
                {
                    "tab_id": str(tab_id),
                    "label": label or str(tab_id),
                    "approvals": len(approval_ids),
                    "request_user_input": 1 if has_request_user_input else 0,
                    "total": total,
                    "is_active": str(tab_id)
                    == str(getattr(mgr, "active_tab_id", "") or "").strip(),
                }
            )
        return result

    def _approval_ticket_for_id(self, approval_id: str) -> Any | None:
        normalized_id = str(approval_id or "").strip()
        if not normalized_id:
            return None
        runtime_for_ticket = self._runtime_for_pending_approval(normalized_id)
        state_store = getattr(runtime_for_ticket, "gateway_state_store", None)
        getter = getattr(state_store, "get_approval_ticket", None)
        if callable(getter):
            try:
                return getter(normalized_id)
            except Exception:
                return None
        return None

    def _tab_approval_inbox_rows(self) -> list[dict[str, Any]]:
        self._prune_resolved_tab_pending_approvals()
        mgr = getattr(self, "_tab_manager", None)
        tabs = getattr(mgr, "_tabs", None)
        order = list(getattr(mgr, "_tab_order", []) or [])
        if not isinstance(tabs, dict):
            return []
        if not order:
            order = list(tabs.keys())
        active_tab_id = str(getattr(mgr, "active_tab_id", "") or "").strip()
        rows: list[dict[str, Any]] = []
        for tab_id in order:
            session = tabs.get(tab_id)
            if session is None:
                continue
            approvals: list[dict[str, str]] = []
            for approval_id in [
                str(item or "").strip()
                for item in list(getattr(session, "pending_approvals", []) or [])
                if str(item or "").strip()
            ]:
                status = self._approval_ticket_status(approval_id)
                if status and status != "pending":
                    continue
                ticket = self._approval_ticket_for_id(approval_id)
                summary = ""
                action_id = ""
                if ticket is not None:
                    summary = str(
                        getattr(ticket, "summary", "") or getattr(ticket, "reason", "") or ""
                    ).strip()
                    action_id = str(getattr(ticket, "action_id", "") or "").strip()
                approvals.append(
                    {
                        "approval_id": approval_id,
                        "status": status or "pending",
                        "summary": summary,
                        "action_id": action_id,
                    }
                )
            if not approvals:
                continue
            label = str(
                getattr(session, "custom_label", "")
                or getattr(session, "thread_name", "")
                or getattr(session, "top_title_text", "")
                or tab_id
            ).strip()
            rows.append(
                {
                    "tab_id": str(tab_id),
                    "label": label or str(tab_id),
                    "is_active": str(tab_id) == active_tab_id,
                    "approvals": approvals,
                    "total": len(approvals),
                }
            )
        return rows

    def _refresh_tab_pending_markers(self) -> None:
        refresh_top_title = getattr(self, "_refresh_top_title_bar", None)
        if callable(refresh_top_title):
            refresh_top_title()

    def _refresh_tab_pending_interaction_indicators(self) -> None:
        self._refresh_tab_pending_markers()
        try:
            self._update_bottom_dock(max(1, int(getattr(self, "size", None).width)))
        except Exception:
            return

    def _tab_session_for_pending_surface(self, tab_id: str | None = None) -> Any | None:
        mgr = getattr(self, "_tab_manager", None)
        if mgr is None:
            return None
        getter = getattr(mgr, "get", None)
        if not callable(getter):
            return None
        resolved_tab_id = str(tab_id or getattr(mgr, "active_tab_id", "") or "").strip()
        if not resolved_tab_id:
            return None
        return getter(resolved_tab_id)

    def _all_tab_pending_approval_ids(self) -> set[str]:
        mgr = getattr(self, "_tab_manager", None)
        tabs = getattr(mgr, "_tabs", None)
        if not isinstance(tabs, dict):
            return set()
        result: set[str] = set()
        for session in tabs.values():
            for approval_id in list(getattr(session, "pending_approvals", []) or []):
                normalized_id = str(approval_id or "").strip()
                if normalized_id:
                    result.add(normalized_id)
        return result

    def _active_tab_pending_approval_ids(self) -> set[str]:
        return set(self._active_tab_pending_approval_order())

    def _active_tab_pending_approval_order(self) -> list[str]:
        session = self._tab_session_for_pending_surface()
        if session is None:
            return []
        return [
            str(approval_id or "").strip()
            for approval_id in list(getattr(session, "pending_approvals", []) or [])
            if str(approval_id or "").strip()
        ]

    def _set_tab_pending_approval(
        self,
        approval_id: str,
        *,
        pending: bool,
        tab_id: str | None = None,
    ) -> None:
        normalized_id = str(approval_id or "").strip()
        if not normalized_id:
            return
        session = self._tab_session_for_pending_surface(tab_id)
        if session is None:
            return
        current = [
            str(item or "").strip()
            for item in list(getattr(session, "pending_approvals", []) or [])
            if str(item or "").strip()
        ]
        if pending:
            if normalized_id not in current:
                current.append(normalized_id)
        else:
            current = [item for item in current if item != normalized_id]
        session.pending_approvals = current
        self._refresh_tab_pending_markers()

    def _prune_resolved_tab_pending_approvals(self) -> None:
        mgr = getattr(self, "_tab_manager", None)
        tabs = getattr(mgr, "_tabs", None)
        if not isinstance(tabs, dict):
            return
        changed = False
        for session in tabs.values():
            current = [
                str(item or "").strip()
                for item in list(getattr(session, "pending_approvals", []) or [])
                if str(item or "").strip()
            ]
            if not current:
                continue
            kept: list[str] = []
            for approval_id in current:
                status = self._approval_ticket_status(approval_id)
                if status and status != "pending":
                    changed = True
                    continue
                kept.append(approval_id)
            if kept != current:
                session.pending_approvals = kept
                changed = True
        if changed:
            self._refresh_tab_pending_markers()

    def _clear_pending_approval_surface_state(self) -> None:
        self._pending_approval_surface_id = ""
        self._pending_approval_surface_commands = []

    def _runtime_pending_approval_tickets(self) -> list[Any]:
        list_approval_tickets = getattr(
            getattr(self, "runtime", None), "list_approval_tickets", None
        )
        if not callable(list_approval_tickets):
            return []
        try:
            return list(list_approval_tickets(limit=20, status="pending") or [])
        except Exception:
            return []

    def _pending_approval_tickets(self) -> list[Any]:
        tickets = self._runtime_pending_approval_tickets()
        if getattr(self, "_tab_manager", None) is None:
            return tickets
        active_order = self._active_tab_pending_approval_order()
        if not active_order:
            return []
        tickets_by_id = {
            str(getattr(ticket, "approval_id", "") or "").strip(): ticket for ticket in tickets
        }
        return [
            tickets_by_id[approval_id]
            for approval_id in active_order
            if approval_id in tickets_by_id
        ]

    def _approval_ticket_status(self, approval_id: str) -> str:
        normalized_id = str(approval_id or "").strip()
        if not normalized_id:
            return ""
        runtime_for_ticket = self._runtime_for_pending_approval(normalized_id)
        state_store = getattr(runtime_for_ticket, "gateway_state_store", None)
        getter = getattr(state_store, "get_approval_ticket", None)
        if not callable(getter):
            return ""
        try:
            ticket = getter(normalized_id)
        except Exception:
            return ""
        if ticket is None:
            if normalized_id in self._all_tab_pending_approval_ids():
                return "pending"
            return ""
        return str(getattr(ticket, "status", "") or "").strip().lower()

    def _tab_id_for_pending_approval(self, approval_id: str) -> str:
        normalized_id = str(approval_id or "").strip()
        if not normalized_id:
            return ""
        mgr = getattr(self, "_tab_manager", None)
        tabs = getattr(mgr, "_tabs", None)
        if not isinstance(tabs, dict):
            return ""
        for tab_id, session in tabs.items():
            if normalized_id in {
                str(item or "").strip()
                for item in list(getattr(session, "pending_approvals", []) or [])
            }:
                return str(tab_id)
        return ""

    def _runtime_for_pending_approval(self, approval_id: str) -> Any:
        fallback_runtime = getattr(self, "runtime", None)
        tab_id = self._tab_id_for_pending_approval(approval_id)
        if not tab_id:
            return fallback_runtime
        mgr = getattr(self, "_tab_manager", None)
        getter = getattr(mgr, "get", None)
        if not callable(getter):
            return fallback_runtime
        session = getter(tab_id)
        runtime = getattr(session, "runtime", None) if session is not None else None
        return runtime if runtime is not None else fallback_runtime
