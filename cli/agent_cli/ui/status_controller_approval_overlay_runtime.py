from __future__ import annotations

import asyncio
import threading
from typing import Any

from cli.agent_cli import approval_control_protocol_runtime
from cli.agent_cli.models import CommandExecutionResult, PromptResponse
from cli.agent_cli.runtime_core.command_handlers_approval_helpers_runtime import (
    execute_approval_control_response,
)
from cli.agent_cli.ui import approval_modal
from cli.agent_cli.ui.approval_modal_payload_helpers import build_approval_overlay_payload


class StatusControllerApprovalOverlayRuntimeMixin:
    async def _run_approval_decision_in_daemon_thread(
        self,
        runtime: Any,
        control_response: dict[str, Any],
    ) -> CommandExecutionResult:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[CommandExecutionResult] = loop.create_future()

        def _publish_result(result: CommandExecutionResult) -> None:
            if not future.done():
                future.set_result(result)

        def _publish_exception(error: BaseException) -> None:
            if not future.done():
                future.set_exception(error)

        def _worker() -> None:
            try:
                result = execute_approval_control_response(
                    runtime,
                    control_response,
                    decided_by="tui",
                    no_resume=bool(control_response.get("no_resume")),
                    resume_only=bool(control_response.get("resume_only")),
                )
            except BaseException as exc:
                try:
                    loop.call_soon_threadsafe(_publish_exception, exc)
                except RuntimeError:
                    pass
            else:
                try:
                    loop.call_soon_threadsafe(_publish_result, result)
                except RuntimeError:
                    pass

        threading.Thread(
            target=_worker,
            name="agenthub-approval-decision",
            daemon=True,
        ).start()
        return await future

    def _approval_overlay_queue_state(self) -> list[str]:
        queue = getattr(self, "_approval_overlay_queue", None)
        if isinstance(queue, list):
            return queue
        queue = []
        self._approval_overlay_queue = queue
        return queue

    def _approval_overlay_suppressed_state(self) -> set[str]:
        suppressed = getattr(self, "_approval_overlay_suppressed_ids", None)
        if isinstance(suppressed, set):
            return suppressed
        suppressed = set()
        self._approval_overlay_suppressed_ids = suppressed
        return suppressed

    def _approval_overlay_widget(self) -> approval_modal.ApprovalOverlay | None:
        overlay = getattr(self, "_approval_overlay", None)
        if isinstance(overlay, approval_modal.ApprovalOverlay):
            return overlay
        try:
            overlay = self.query_one(
                f"#{approval_modal.ApprovalOverlay.ROOT_ID}", approval_modal.ApprovalOverlay
            )
        except Exception:
            return None
        self._approval_overlay = overlay
        return overlay

    def _dismiss_approval_overlay(self, approval_id: str | None = None) -> None:
        normalized_id = str(approval_id or "").strip()
        overlay = self._approval_overlay_widget()
        if overlay is not None and overlay.is_active:
            if not normalized_id or overlay.approval_id == normalized_id:
                overlay.deactivate()
        active_id = str(getattr(self, "_approval_overlay_active_id", "") or "").strip()
        if not normalized_id or active_id == normalized_id:
            self._approval_overlay_active_id = ""

    def _approval_overlay_payload(self, approval_id: str) -> dict[str, Any] | None:
        normalized_id = str(approval_id or "").strip()
        if not normalized_id:
            return None
        runtime_for_ticket = self._runtime_for_pending_approval(normalized_id)
        state_store = getattr(runtime_for_ticket, "gateway_state_store", None)
        ticket = None
        getter = getattr(state_store, "get_approval_ticket", None)
        if callable(getter):
            try:
                ticket = getter(normalized_id)
            except Exception:
                ticket = None
        if ticket is None:
            ticket = next(
                (
                    item
                    for item in self._pending_approval_tickets()
                    if str(getattr(item, "approval_id", "") or "").strip() == normalized_id
                ),
                None,
            )
        if ticket is None:
            return None
        if str(getattr(ticket, "status", "") or "").strip().lower() != "pending":
            return None
        action_request = None
        get_action_request = getattr(state_store, "get_action_request", None)
        if callable(get_action_request):
            action_id = str(getattr(ticket, "action_id", "") or "").strip()
            if action_id:
                try:
                    action_request = get_action_request(action_id)
                except Exception:
                    action_request = None
        try:
            payload = build_approval_overlay_payload(
                approval_ticket=ticket,
                action_request=action_request,
            )
        except Exception:
            return None
        if not str(payload.get("approval_id") or "").strip():
            return None
        return payload

    def _present_approval_overlay(self, payload: dict[str, Any]) -> bool:
        presenter = getattr(self, "_approval_modal_presenter", None)
        if callable(presenter):
            try:
                accepted = bool(
                    presenter(
                        payload=dict(payload or {}),
                        on_submit=self._on_approval_overlay_submit,
                    )
                )
            except Exception:
                accepted = False
            if accepted:
                return True
        try:
            return bool(
                approval_modal.present_approval_overlay(
                    app=self,
                    payload=dict(payload or {}),
                    on_submit=self._on_approval_overlay_submit,
                )
            )
        except Exception:
            return False

    def _drain_approval_overlay_queue(self) -> None:
        active_id = str(getattr(self, "_approval_overlay_active_id", "") or "").strip()
        if active_id:
            payload = self._approval_overlay_payload(active_id)
            if payload is not None:
                return
            self._dismiss_approval_overlay(active_id)
        queue = self._approval_overlay_queue_state()
        if getattr(self, "_tab_manager", None) is not None:
            active_ids = set(self._active_tab_pending_approval_order())
            queue[:] = [item for item in queue if str(item or "").strip() in active_ids]
        suppressed = self._approval_overlay_suppressed_state()
        if not queue:
            for ticket in self._pending_approval_tickets():
                candidate = str(getattr(ticket, "approval_id", "") or "").strip()
                if not candidate or candidate in suppressed or candidate in queue:
                    continue
                queue.append(candidate)
        while queue:
            candidate = str(queue.pop(0) or "").strip()
            if not candidate or candidate in suppressed:
                continue
            payload = self._approval_overlay_payload(candidate)
            if payload is None:
                continue
            if self._present_approval_overlay(payload):
                self._approval_overlay_active_id = candidate
                return

    def _enqueue_pending_approval_overlay(self, approval_id: str) -> None:
        normalized_id = str(approval_id or "").strip()
        if not normalized_id:
            return
        if normalized_id in self._approval_overlay_suppressed_state():
            return
        if normalized_id == str(getattr(self, "_approval_overlay_active_id", "") or "").strip():
            return
        queue = self._approval_overlay_queue_state()
        if normalized_id in queue:
            return
        queue.append(normalized_id)
        self._drain_approval_overlay_queue()

    def _resolve_pending_approval_overlay(self, approval_id: str) -> None:
        normalized_id = str(approval_id or "").strip()
        if not normalized_id:
            return
        tab_id = self._tab_id_for_pending_approval(normalized_id)
        self._set_tab_pending_approval(normalized_id, pending=False, tab_id=tab_id or None)
        self._approval_overlay_suppressed_state().discard(normalized_id)
        queue = self._approval_overlay_queue_state()
        self._approval_overlay_queue = [
            item for item in queue if str(item or "").strip() != normalized_id
        ]
        if str(getattr(self, "_approval_overlay_active_id", "") or "").strip() == normalized_id:
            self._dismiss_approval_overlay(normalized_id)
        self._drain_approval_overlay_queue()

    @staticmethod
    def _approval_decision_prompt_response(result: CommandExecutionResult) -> PromptResponse:
        return PromptResponse(
            user_text="",
            assistant_text=str(result.assistant_text or ""),
            tool_events=list(result.tool_events or []),
            handled_as_command=True,
            turn_events=[
                dict(item) for item in list(result.turn_events or []) if isinstance(item, dict)
            ],
            command_display_text=str(result.command_display_text or ""),
        )

    async def _run_approval_overlay_control_response(
        self,
        control_response: dict[str, Any],
    ) -> None:
        approval_id = (
            approval_control_protocol_runtime.request_id_from_control_response(control_response)
            or ""
        )
        tab_id = self._tab_id_for_pending_approval(approval_id)
        active_tab_id = str(
            getattr(getattr(self, "_tab_manager", None), "active_tab_id", "") or ""
        ).strip()
        if tab_id and active_tab_id and tab_id != active_tab_id:
            self._refresh_tab_pending_interaction_indicators()
            return
        decision_runtime = self._runtime_for_pending_approval(approval_id)
        decision_failed = False
        try:
            self._set_busy(True)
        except Exception:
            pass
        try:
            self._begin_activity_capture()
        except Exception:
            pass
        try:
            result = await self._run_approval_decision_in_daemon_thread(
                decision_runtime,
                control_response,
            )
        except Exception as exc:
            decision_failed = True
            try:
                self._write_assistant_reply(f"Approval decision failed: {exc}")
            except Exception:
                pass
        else:
            response = self._approval_decision_prompt_response(result)
            try:
                if tab_id:
                    self._render_response_for_tab(tab_id, response)
                    self._handle_response_for_tab(tab_id, response)
                else:
                    self._render_response(response)
                    self._handle_runtime_response(response)
            except Exception as exc:
                try:
                    self._write_assistant_reply(f"Approval decision render failed: {exc}")
                except Exception:
                    pass
        finally:
            try:
                self._set_busy(False)
            except Exception:
                pass
            if decision_failed and approval_id:
                self._approval_overlay_suppressed_state().discard(approval_id)
            self._focus_input()
            self._drain_approval_overlay_queue()

    def _on_approval_overlay_submit(self, command: str, payload: dict[str, Any]) -> None:
        approval_id = str((payload or {}).get("approval_id") or "").strip()
        if approval_id:
            self._approval_overlay_suppressed_state().add(approval_id)
        self._dismiss_approval_overlay(approval_id or None)
        decision_type = str((payload or {}).get("decision_type") or "").strip()
        if approval_id and decision_type:
            control_response = approval_control_protocol_runtime.control_response_for_decision(
                approval_id=approval_id,
                decision=decision_type,
                request_id=approval_id,
            )
            control_response["no_resume"] = True
            try:
                asyncio.get_running_loop().create_task(
                    self._run_approval_overlay_control_response(control_response)
                )
            except RuntimeError:
                pass
        elif command:
            try:
                asyncio.get_running_loop().create_task(
                    self._enqueue_runtime_request(command, [], priority="later")
                )
            except RuntimeError:
                pass
        self._focus_input()
        self._drain_approval_overlay_queue()

    def _cancel_approval_overlay_on_escape(self) -> bool:
        overlay = self._approval_overlay_widget()
        if overlay is None or not overlay.is_active:
            return False
        return bool(overlay.submit_escape())
