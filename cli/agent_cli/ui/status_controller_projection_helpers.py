from __future__ import annotations

from typing import Any

from cli.agent_cli.ui import crop_one_line, flag_label, short, status_controller_runtime, tool_label
from cli.agent_cli.ui.status_indicator import build_status_indicator_text


class StatusControllerProjectionHelpersMixin:
    @staticmethod
    def _short(value: str, limit: int) -> str:
        return short(value, limit)

    @staticmethod
    def _crop_one_line(value: str, width: int) -> str:
        return crop_one_line(value, width)

    @staticmethod
    def _status_text(value: Any) -> str:
        return status_controller_runtime.status_text(value)

    @staticmethod
    def _boolish_status(value: Any) -> bool | None:
        return status_controller_runtime.boolish_status(value)

    def _status_from_response(self, response: Any) -> dict[str, str]:
        return status_controller_runtime.status_from_response(
            response,
            operator_status_from_response_fn=self._operator_status_from_response,
        )

    def _operator_status_from_response(self, response: Any) -> dict[str, str]:
        return status_controller_runtime.operator_status_from_response(
            response,
            operator_command_name_fn=self._operator_command_name,
            key_value_lines_fn=self._key_value_lines,
            operator_status_from_mapping_fn=self._operator_status_from_mapping,
            operator_status_from_text_fn=self._operator_status_from_text,
            operator_hint_from_command_fn=lambda command_name, key_values, assistant_text: self._operator_hint_from_command(
                command_name,
                key_values=key_values,
                assistant_text=assistant_text,
            ),
        )

    @staticmethod
    def _operator_status_from_mapping(payload: dict[str, Any]) -> dict[str, str]:
        return status_controller_runtime.operator_status_from_mapping(payload)

    @staticmethod
    def _operator_command_name(user_text: Any) -> str:
        return status_controller_runtime.operator_command_name(user_text)

    @staticmethod
    def _key_value_lines(text: Any) -> dict[str, str]:
        return status_controller_runtime.key_value_lines(text)

    @staticmethod
    def _operator_status_from_text(key_values: dict[str, str]) -> dict[str, str]:
        return status_controller_runtime.operator_status_from_text(key_values)

    @staticmethod
    def _normalized_count(value: Any) -> str:
        return status_controller_runtime.normalized_count(value)

    @staticmethod
    def _operator_hint_title(assistant_text: Any) -> str:
        return status_controller_runtime.operator_hint_title(assistant_text)

    def _operator_hint_from_command(
        self,
        command_name: str,
        *,
        key_values: dict[str, str],
        assistant_text: Any,
    ) -> str:
        return status_controller_runtime.operator_hint_from_command(
            command_name,
            key_values=key_values,
            assistant_text=assistant_text,
            normalized_count_fn=self._normalized_count,
            tool_label_fn=tool_label,
            flag_label_fn=flag_label,
        )

    @staticmethod
    def _format_elapsed_compact(total_seconds: int) -> str:
        return status_controller_runtime.format_elapsed_compact(total_seconds)

    def _build_busy_hint(self, width: int) -> str:
        label = str(self._busy_status_label or self._t("status.working")).strip() or self._t(
            "status.working"
        )
        return build_status_indicator_text(
            label,
            width=width,
            started_at=self._busy_started_at,
            theme=self._theme,
            messages=self._messages,
            enhanced=True,
            show_interrupt_hint=True,
        )

    def _maybe_restore_busy_status_indicator(self) -> None:
        if (
            not self._pending_status_indicator_restore
            or not self._busy
            or self._assistant_message_streaming_active
        ):
            return
        self._pending_status_indicator_restore = False
        self._refresh_dynamic_hint()

    def _pending_approval_count(self) -> int:
        tickets = self._pending_approval_tickets()
        status_count = status_controller_runtime.pending_approval_count(self.status_data)
        active_ids_fn = getattr(self, "_active_tab_pending_approval_ids", None)
        all_ids_fn = getattr(self, "_all_tab_pending_approval_ids", None)
        if callable(active_ids_fn) and callable(all_ids_fn):
            active_ids = set(active_ids_fn() or set())
            all_ids = set(all_ids_fn() or set())
            if all_ids and not active_ids:
                status_count = 0
        approval_id = str(self.status_data.get("latest_pending_approval_id") or "").strip()
        ticket_status_fn = getattr(self, "_approval_ticket_status", None)
        if callable(ticket_status_fn) and approval_id not in {"", "-"}:
            ticket_status = str(ticket_status_fn(approval_id) or "").strip().lower()
            if ticket_status and ticket_status != "pending":
                status_count = 0
        return max(status_count, len(tickets))

    def _build_pending_approval_hint(self, width: int, pending_approvals: int) -> str:
        key = (
            "status.pending_approval.one"
            if pending_approvals == 1
            else "status.pending_approval.other"
        )
        return self._crop_one_line(f"• {self._t(key, count=pending_approvals)}", width)

    def _build_tab_pending_interaction_hint(self, width: int) -> str:
        summary_fn = getattr(self, "_tab_pending_interaction_summary", None)
        if not callable(summary_fn):
            return ""
        try:
            summary = list(summary_fn() or [])
        except Exception:
            return ""
        inactive = [
            item for item in summary if isinstance(item, dict) and not bool(item.get("is_active"))
        ]
        if not inactive:
            return ""
        parts: list[str] = []
        total = 0
        for item in inactive:
            try:
                count = max(0, int(item.get("total") or 0))
            except (TypeError, ValueError):
                count = 0
            if count <= 0:
                continue
            total += count
            label = str(item.get("label") or item.get("tab_id") or "").strip()
            if not label:
                continue
            parts.append(f"{self._short(label, 18)}:{count}")
        if total <= 0 or not parts:
            return ""
        key = (
            "status.tab_pending_interactions.one"
            if total == 1
            else "status.tab_pending_interactions.other"
        )
        return self._crop_one_line(
            f"• {self._t(key, count=total, tabs=', '.join(parts))}",
            width,
        )

    def _build_pending_approval_footer_hint(self, width: int) -> str:
        self._sync_pending_approval_surface_state()
        commands = [
            str(item).strip()
            for item in list(getattr(self, "_pending_approval_surface_commands", []) or [])
            if str(item).strip()
        ]
        if not commands:
            return ""
        return self._crop_one_line("  ".join(commands), width)

    def _build_operator_surface_hint(self, width: int) -> str:
        return status_controller_runtime.build_operator_surface_hint(
            self.status_data,
            width=width,
            short_fn=self._short,
            crop_one_line_fn=self._crop_one_line,
            tool_label_fn=tool_label,
            boolish_status_fn=self._boolish_status,
        )

    def _passive_status_summary_enabled(self) -> bool:
        if not bool(getattr(self, "_restored_transcript_from_history", False)):
            return False
        thread_name = str(self.status_data.get("thread_name", "") or "").strip()
        thread_id = str(self.status_data.get("thread_id", "") or "").strip()
        return thread_name not in {"", "-"} or thread_id not in {"", "-"}

    def _build_passive_status_summary(self, width: int) -> str:
        if not self._passive_status_summary_enabled():
            return ""
        return self._crop_one_line(
            status_controller_runtime.build_status_summary_text(
                status_data=self.status_data,
                cwd=str(getattr(self, "_workspace_root", "") or ""),
            ),
            width,
        )

    def _busy_label_for_queued_request(self, text: str) -> str:
        return status_controller_runtime.busy_label_for_queued_request(
            text,
            queued_request_busy_label_keys=self._QUEUED_REQUEST_BUSY_LABEL_KEYS,
            translate_fn=self._t,
        )
