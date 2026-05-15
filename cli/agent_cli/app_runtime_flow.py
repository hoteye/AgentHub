from __future__ import annotations

import os
from typing import Any

from cli.agent_cli import (
    app_runtime_flow_normalization_helpers_runtime as normalization_helpers_runtime,
)
from cli.agent_cli import app_runtime_flow_projection_helpers_runtime as projection_helpers_runtime
from cli.agent_cli import app_runtime_flow_pure_helpers_runtime as pure_helpers_runtime
from cli.agent_cli import (
    app_runtime_flow_request_user_input_flow_helpers_runtime as request_user_input_flow_helpers_runtime,
)
from cli.agent_cli import app_runtime_flow_transcript_helpers_runtime as transcript_helpers_runtime
from cli.agent_cli import app_runtime_support_runtime
from cli.agent_cli.app_runtime_flow_request_user_input_helpers import (
    _PendingRequestUserInput,
)
from cli.agent_cli.models import PromptAttachment
from cli.agent_cli.slash_parser import parse_slash_invocation
from cli.agent_cli.ui import (
    enqueue_runtime_request,
    request_worker_loop,
    transcript_preview_pane,
    wait_for_runtime_idle,
)


class AppRuntimeFlowMixin:
    def _activate_transcript_search_mode(self) -> None:
        transcript_helpers_runtime.activate_transcript_search_mode(self)

    def _deactivate_transcript_search_mode(self) -> None:
        transcript_helpers_runtime.deactivate_transcript_search_mode(self)

    def _is_transcript_search_mode_active(self) -> bool:
        return bool(getattr(self, "_transcript_search_mode_active_flag", False))

    def _get_transcript_search_query_buffer(self) -> str:
        return str(getattr(self, "_transcript_search_query_buffer_value", "") or "")

    def _set_transcript_search_query_buffer(self, value: str) -> None:
        self._transcript_search_query_buffer_value = str(value or "")

    def _apply_transcript_search_query(self, query: str) -> None:
        transcript_helpers_runtime.apply_transcript_search_query(self, query)

    def _move_transcript_search_match(self, *, forward: bool) -> bool:
        return transcript_helpers_runtime.move_transcript_search_match(self, forward=forward)

    def _handle_transcript_search_key(self, key: str) -> bool:
        normalized_key = normalization_helpers_runtime.normalize_transcript_search_key(key)
        search_mode_active = self._is_transcript_search_mode_active()
        action = pure_helpers_runtime.transcript_search_key_action(
            normalized_key,
            search_mode_active=search_mode_active,
        )
        if action == "activate":
            self._activate_transcript_search_mode()
            return True
        if action == "deactivate":
            self._deactivate_transcript_search_mode()
            return True
        if action == "backspace":
            buffer = self._get_transcript_search_query_buffer()
            self._set_transcript_search_query_buffer(
                pure_helpers_runtime.transcript_search_buffer_backspace(buffer)
            )
            self._apply_transcript_search_query(self._get_transcript_search_query_buffer())
            return True
        if action == "submit":
            self._apply_transcript_search_query(self._get_transcript_search_query_buffer())
            self._deactivate_transcript_search_mode()
            return True
        if search_mode_active:
            inline_text = pure_helpers_runtime.transcript_search_inline_text(key)
            if inline_text:
                self._set_transcript_search_query_buffer(
                    pure_helpers_runtime.transcript_search_buffer_append(
                        self._get_transcript_search_query_buffer(),
                        inline_text,
                    )
                )
                self._apply_transcript_search_query(self._get_transcript_search_query_buffer())
                return True
            return False
        if action == "next_match":
            return self._move_transcript_search_match(forward=True)
        if action == "prev_match":
            return self._move_transcript_search_match(forward=False)
        return False

    def _handle_transcript_search_text_input(self, text: str) -> bool:
        if not self._is_transcript_search_mode_active():
            return False
        value = normalization_helpers_runtime.normalize_transcript_search_text(text)
        if not value:
            return False
        self._set_transcript_search_query_buffer(
            pure_helpers_runtime.transcript_search_buffer_append(
                self._get_transcript_search_query_buffer(),
                value,
            )
        )
        self._apply_transcript_search_query(self._get_transcript_search_query_buffer())
        return True

    def _on_runtime_request_start(self, text: str) -> None:
        normalized = normalization_helpers_runtime.normalize_runtime_request_text(text)
        self._active_runtime_request_text = normalized
        self._active_runtime_request_is_slash = pure_helpers_runtime.is_slash_command_text(
            normalized
        )
        self._set_top_title_from_prompt(normalized)

    def _request_user_input_notice_text(
        self,
        *,
        key: str,
        legacy_en: str,
        **kwargs: object,
    ) -> str:
        if self._presentation_cli_language is None:
            return pure_helpers_runtime.format_legacy_notice_text(legacy_en, **kwargs)
        return self._t(key, **kwargs)

    def _begin_shutdown(self) -> None:
        self._close_preview_pane_on_shutdown()
        if self._shutdown_initiated:
            return
        self._shutdown_initiated = True
        interrupt_active_run = getattr(getattr(self, "runtime", None), "interrupt_active_run", None)
        if callable(interrupt_active_run):
            try:
                interrupt_active_run()
            except Exception:
                pass
        self._cancel_pending_request_user_input("shutdown")
        self._restore_request_user_input_handler()
        for timer_name in ("_dynamic_hint_timer", "_prompt_burst_timer"):
            timer = getattr(self, timer_name, None)
            app_runtime_support_runtime.stop_optional_timer(timer)
            setattr(self, timer_name, None)

    def _close_preview_pane_on_shutdown(self) -> None:
        if bool(getattr(self, "_preview_pane_close_attempted", False)):
            return
        self._preview_pane_close_attempted = True
        if str(os.environ.get("AGENTHUB_TMUX_LAYOUT_OWNS_PREVIEW") or "").strip() != "1":
            return
        try:
            transcript_preview_pane.close_preview_pane()
        except Exception:
            pass

    def _populate_exit_request_from_runtime(self) -> None:
        try:
            from cli.agent_cli.runtime_core import thread_commands_text_runtime

            payload = thread_commands_text_runtime.exit_payload(self.runtime)
        except Exception:
            payload = projection_helpers_runtime.fallback_exit_payload(self.runtime)
        exit_projection = projection_helpers_runtime.exit_request_projection(payload)
        self._exit_requested = True
        self._exit_thread_id = exit_projection.thread_id
        self._exit_resume_command = exit_projection.resume_command
        self._exit_summary_requires_post_run_print = True

    def _set_screen_mode(self, screen_mode: str) -> None:
        transcript_helpers_runtime.set_screen_mode(self, screen_mode)

    def _handle_transcript_navigation_key(self, key: str) -> bool:
        return transcript_helpers_runtime.handle_transcript_navigation_key(self, key)

    def _install_local_request_user_input_handler(self) -> None:
        request_user_input_flow_helpers_runtime.install_local_request_user_input_handler(self)

    def _restore_request_user_input_handler(self) -> None:
        request_user_input_flow_helpers_runtime.restore_request_user_input_handler(self)

    def _handle_request_user_input_from_runtime(
        self, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        mgr = getattr(self, "_tab_manager", None)
        tab_id = str(getattr(mgr, "active_tab_id", "") or "").strip() or None
        return self._handle_request_user_input_from_runtime_for_tab(tab_id, payload)

    def _handle_request_user_input_from_runtime_for_tab(
        self, tab_id: str | None, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        return request_user_input_flow_helpers_runtime.handle_request_user_input_from_runtime(
            self,
            payload,
            tab_id=tab_id,
        )

    def _dispatch_request_user_input_prompt(self, pending: _PendingRequestUserInput) -> None:
        request_user_input_flow_helpers_runtime.dispatch_request_user_input_prompt(self, pending)

    def _present_request_user_input_modal(self, payload: dict[str, Any]) -> bool:
        return request_user_input_flow_helpers_runtime.present_request_user_input_modal(
            self,
            payload,
        )

    def _cancel_request_user_input_on_escape(self) -> bool:
        return request_user_input_flow_helpers_runtime.cancel_request_user_input_on_escape(self)

    def _cancel_pending_request_user_input(self, reason: str) -> None:
        request_user_input_flow_helpers_runtime.cancel_pending_request_user_input(self, reason)

    def _request_user_input_cancel_reason_label(self, reason: str) -> str:
        return request_user_input_flow_helpers_runtime.request_user_input_cancel_reason_label(
            self,
            reason,
        )

    def _on_request_user_input_submit(self, response: dict[str, Any]) -> None:
        request_user_input_flow_helpers_runtime.on_request_user_input_submit(self, response)

    def _on_request_user_input_cancel(self) -> None:
        request_user_input_flow_helpers_runtime.on_request_user_input_cancel(self)

    def _resolve_pending_request_user_input(
        self,
        *,
        response: dict[str, Any] | None,
        cancelled: bool,
    ) -> None:
        request_user_input_flow_helpers_runtime.resolve_pending_request_user_input(
            self,
            response=response,
            cancelled=cancelled,
        )

    def _has_pending_runtime_work(self) -> bool:
        return app_runtime_support_runtime.has_pending_runtime_work(
            busy=self._busy,
            runtime=self.runtime,
            queue_size=self._request_queue.qsize(),
        )

    def _slash_commands_blocked_by_pending_runtime_work(self) -> bool:
        if not self._has_pending_runtime_work():
            return False
        return not bool(getattr(self, "_live_turn_interrupt_requested", False))

    def _runtime_has_active_run(self) -> bool:
        return app_runtime_support_runtime.runtime_has_active_run(getattr(self, "runtime", None))

    def _has_interruptible_run(self) -> bool:
        return app_runtime_support_runtime.has_interruptible_run(
            busy=self._busy,
            runtime=getattr(self, "runtime", None),
        )

    async def _enqueue_runtime_request(
        self,
        text: str,
        attachments: list[PromptAttachment],
        *,
        display_text: str | None = None,
        display_attachments: list[PromptAttachment] | None = None,
        priority: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        normalized_text = str(text or "").strip()
        if self._approval_command_targets_inactive_tab(normalized_text):
            return
        if not pure_helpers_runtime.is_slash_command_text(normalized_text):
            self._queued_run_labels.append(normalized_text)
        await enqueue_runtime_request(
            self._request_queue,
            text,
            attachments,
            display_text=display_text,
            display_attachments=display_attachments,
            priority=priority,
            metadata=metadata,
        )

    def _approval_command_targets_inactive_tab(self, text: str) -> bool:
        normalized_text = str(text or "").strip()
        if not pure_helpers_runtime.is_slash_command_text(normalized_text):
            return False
        try:
            invocation = parse_slash_invocation(normalized_text, source="tui")
        except ValueError:
            return False
        if invocation.command_name not in {"approve", "reject"}:
            return False
        approval_id = next(
            (
                str(item or "").strip()
                for item in tuple(getattr(invocation, "positionals", ()) or ())
                if str(item or "").strip()
            ),
            "",
        )
        if not approval_id:
            return False
        owner_lookup = getattr(self, "_tab_id_for_pending_approval", None)
        if not callable(owner_lookup):
            return False
        owner_tab_id = str(owner_lookup(approval_id) or "").strip()
        if not owner_tab_id:
            return False
        active_tab_id = str(
            getattr(getattr(self, "_tab_manager", None), "active_tab_id", "") or ""
        ).strip()
        if not active_tab_id or owner_tab_id == active_tab_id:
            return False
        try:
            self._write_system_notice(
                self._t(
                    "system.approval_wrong_tab",
                    approval_id=approval_id,
                    tab_id=owner_tab_id,
                )
            )
        except Exception:
            pass
        try:
            self._refresh_tab_pending_interaction_indicators()
        except Exception:
            pass
        try:
            self._focus_input()
        except Exception:
            pass
        return True

    async def _request_worker_loop(self) -> None:
        await request_worker_loop(
            queue=self._request_queue,
            runtime=self.runtime,
            set_busy=self._set_busy,
            on_request_start=self._on_runtime_request_start,
            on_request_echo=self._write_user_prompt,
            begin_activity_capture=self._begin_activity_capture,
            render_response=self._render_response,
            handle_response=self._handle_runtime_response,
            write_assistant_reply=self._write_assistant_reply,
            on_idle=self._focus_input,
        )

    async def _wait_for_runtime_idle(self) -> None:
        await wait_for_runtime_idle(self._request_queue)

    def _handle_runtime_response(self, response: object) -> None:
        payload = self._exit_request_payload(response)
        if payload is not None:
            exit_projection = projection_helpers_runtime.exit_request_projection(payload)
            self._exit_requested = True
            self._exit_thread_id = exit_projection.thread_id
            self._exit_resume_command = exit_projection.resume_command
            self._exit_summary_requires_post_run_print = True
            self.call_after_refresh(self._exit_after_command)
            return
        if pure_helpers_runtime.close_tab_request_payload(response) is not None:
            if self._tab_manager is not None and len(self._tab_manager._tabs) > 1:
                self.call_after_refresh(self.action_close_tab)
            else:
                self.call_after_refresh(self._exit_after_command)
            return
        preview_payload = pure_helpers_runtime.preview_control_request_payload(response)
        if preview_payload is not None:
            self.call_after_refresh(
                self._handle_preview_control_request,
                str(preview_payload.get("action") or "toggle"),
            )
            return

    @staticmethod
    def _exit_request_payload(response: object) -> dict[str, object] | None:
        return pure_helpers_runtime.exit_request_payload(response)

    def action_split_open(self) -> None:
        self._handle_preview_control_request("open")
        self._refresh_split_toggle_button()

    def action_split_close(self) -> None:
        self._handle_preview_control_request("close")
        self._refresh_split_toggle_button()

    def _handle_preview_control_request(self, action: str) -> None:
        normalized = str(action or "toggle").strip().lower() or "toggle"
        if normalized == "status":
            self._write_system_notice(self._preview_control_status_text())
            self._focus_input()
            return
        if normalized == "toggle":
            normalized = "open" if self._preview_pane_disabled_or_missing() else "close"
        if normalized == "close":
            transcript_preview_pane.set_preview_pane_user_disabled(True)
            closed = transcript_preview_pane.close_preview_pane()
            key = "system.preview_pane.closed" if closed else "system.preview_pane.already_closed"
            self._write_system_notice(self._t(key))
            self._focus_input()
            return
        if normalized == "open":
            transcript_preview_pane.set_preview_pane_user_disabled(False)
            pane = transcript_preview_pane.open_preview_pane()
            key = "system.preview_pane.opened" if pane else "system.preview_pane.unavailable"
            self._write_system_notice(self._t(key))
            self._focus_input()
            return
        self._write_system_notice(self._t("system.preview_pane.usage"))
        self._focus_input()

    def _preview_pane_disabled_or_missing(self) -> bool:
        if transcript_preview_pane.preview_pane_user_disabled():
            return True
        pane = str(os.environ.get("AGENTHUB_PREVIEW_PANE") or "").strip()
        if not pane:
            return True
        return not transcript_preview_pane.preview_pane_exists(pane)

    def _refresh_split_toggle_button(self) -> None:
        try:
            from textual.widgets import Static

            btn = self.query_one("#split_toggle_btn", Static)
            is_open = not self._preview_pane_disabled_or_missing()
            compact = int(getattr(getattr(btn, "size", None), "width", 0) or 2) < 2
            if compact:
                icon = "<" if is_open else ">"
            else:
                icon = "<<" if is_open else ">>"
            btn.update(icon)
        except Exception:
            pass

    def _preview_control_status_text(self) -> str:
        if transcript_preview_pane.preview_pane_user_disabled():
            return self._t("system.preview_pane.disabled")
        pane = str(os.environ.get("AGENTHUB_PREVIEW_PANE") or "").strip()
        if pane and transcript_preview_pane.preview_pane_exists(pane):
            return self._t("system.preview_pane.open_status", pane=pane)
        return self._t("system.preview_pane.closed_status")

    def _exit_after_command(self) -> None:
        if self._shutdown_initiated:
            return
        self._begin_shutdown()
        self.exit()
