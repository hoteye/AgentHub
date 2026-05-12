from __future__ import annotations

from time import monotonic

from textual.css.query import NoMatches

from cli.agent_cli.ui.status_controller_models import (
    REQUEST_USER_INPUT_WAITING_LABEL,
    REQUEST_USER_INPUT_WAITING_STATUS_KEY,
    STATUS_FALSE,
    STATUS_TRUE,
)


class StatusControllerBusyRuntimeMixin:
    def _set_request_user_input_waiting(self, waiting: bool) -> None:
        self.status_data[REQUEST_USER_INPUT_WAITING_STATUS_KEY] = (
            STATUS_TRUE if waiting else STATUS_FALSE
        )
        if waiting:
            self._busy_status_label = REQUEST_USER_INPUT_WAITING_LABEL
        elif str(self._busy_status_label or "").strip().lower() == REQUEST_USER_INPUT_WAITING_LABEL:
            self._busy_status_label = ""
        self._refresh_dynamic_hint()

    def _update_status(self, status: dict[str, str]) -> None:
        self.status_data.update({str(k): str(v) for k, v in status.items() if v is not None})
        self._sync_pending_approval_surface_state()
        width = max(1, self.size.width)
        try:
            self._update_bottom_dock(width)
        except NoMatches:
            return

    def _refresh_dynamic_hint(self) -> None:
        if self._shutdown_initiated or not self.is_running:
            return
        if self._quit_shortcut_expires_at is not None and not self._quit_shortcut_active():
            self._quit_shortcut_expires_at = None
        if not self._busy and self._quit_shortcut_expires_at is None:
            pending_approvals = self._pending_approval_count()
            approval_policy = str(self.status_data.get("approval_policy", "") or "").strip().lower()
            if pending_approvals > 0 and approval_policy != "never":
                return
        try:
            self._update_bottom_dock(max(1, self.size.width))
        except NoMatches:
            return

    def _quit_shortcut_active(self) -> bool:
        return (
            self._quit_shortcut_expires_at is not None
            and monotonic() <= self._quit_shortcut_expires_at
        )

    def _arm_quit_shortcut(self) -> None:
        self._quit_shortcut_expires_at = monotonic() + self.QUIT_SHORTCUT_TIMEOUT_SECONDS
        self._update_bottom_dock(max(1, self.size.width))

    def _clear_quit_shortcut(self) -> None:
        if self._quit_shortcut_expires_at is None:
            return
        self._quit_shortcut_expires_at = None
        try:
            self._update_bottom_dock(max(1, self.size.width))
        except NoMatches:
            return

    def _set_busy(self, busy: bool) -> None:
        was_busy = self._busy
        self._busy = busy
        if busy and not was_busy:
            self._busy_started_at = monotonic()
            queued_label = self._queued_run_labels.popleft() if self._queued_run_labels else ""
            self._busy_status_label = self._busy_label_for_queued_request(queued_label)
            self._busy_status_hidden = False
            self._pending_status_indicator_restore = False
        elif not busy and was_busy:
            self._busy_started_at = None
            self._busy_status_label = ""
            self._assistant_message_streaming_active = False
            self._busy_status_hidden = False
            self._pending_status_indicator_restore = False
            self.status_data[REQUEST_USER_INPUT_WAITING_STATUS_KEY] = STATUS_FALSE
        self.sub_title = self._subtitle_text(busy)
        self.status_data["busy"] = STATUS_TRUE if busy else STATUS_FALSE
        try:
            self._update_status({})
        except NoMatches:
            return
        refresh_top_title = getattr(self, "_refresh_top_title_bar", None)
        if callable(refresh_top_title):
            refresh_top_title()
