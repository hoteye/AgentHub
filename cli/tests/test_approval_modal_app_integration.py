from __future__ import annotations

import asyncio
import unittest
from dataclasses import replace

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.gateway_core import ActionRequest, ApprovalTicket, InMemoryGatewayStateStore
from cli.agent_cli.models import ActivityEvent, PromptResponse, ToolEvent
from cli.agent_cli.ui.approval_modal import ApprovalOverlay
from cli.agent_cli.ui.tab_bar import TabBar


class _ApprovalRuntime:
    class _Agent:
        @staticmethod
        def provider_status() -> dict[str, str]:
            return {
                "provider_name": "test",
                "provider_model": "test-model",
                "provider_ready": "true",
            }

    def __init__(self) -> None:
        self.agent = self._Agent()
        self.activity_callback = None
        self.turn_event_callback = None
        self.gateway_state_store = InMemoryGatewayStateStore()
        self.prompts: list[str] = []
        self.decisions: list[dict[str, str]] = []

    @staticmethod
    def slash_command_matches(query: str) -> list[dict[str, str]]:
        del query
        return []

    @staticmethod
    def slash_command_completion(query: str) -> str | None:
        del query
        return None

    @staticmethod
    def interrupt_active_run() -> dict[str, object]:
        return {"ok": False, "interrupted": False}

    def list_approval_tickets(
        self, *, limit: int = 20, status: str | None = None
    ) -> list[ApprovalTicket]:
        return self.gateway_state_store.list_approval_tickets(limit=limit, status=status)

    def decide_approval(
        self,
        approval_id: str,
        *,
        decision,
        decided_by: str,
        decision_note: str = "",
    ) -> dict[str, object]:
        normalized = approval_contract_runtime.normalize_approval_decision(decision)
        decision_type = str(normalized.get("type") or "")
        ticket = self.gateway_state_store.get_approval_ticket(approval_id)
        if ticket is None:
            raise ValueError(f"unknown approval_id: {approval_id}")
        status = (
            "approved"
            if approval_contract_runtime.is_approval_accepting(normalized)
            else "rejected"
        )
        self.gateway_state_store.save_approval_ticket(
            replace(
                ticket,
                status=status,
                decision_by=decided_by,
                decision_note=decision_note,
                decision_type=decision_type,
                decision_payload=normalized,
            )
        )
        self.decisions.append(
            {
                "approval_id": approval_id,
                "decision": decision_type,
                "decided_by": decided_by,
            }
        )
        return {
            "tool_events": [
                ToolEvent(
                    name="approval_decision",
                    ok=True,
                    summary=f"{status} {approval_id}",
                    payload={
                        "approval_id": approval_id,
                        "status": status,
                        "decision_type": decision_type,
                    },
                )
            ]
        }

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        self.prompts.append(text)
        return PromptResponse(
            user_text=text,
            assistant_text=f"handled {text}",
            status=self.agent.provider_status(),
            handled_as_command=text.startswith("/"),
        )


def _seed_shell_approval(
    runtime: _ApprovalRuntime,
    *,
    approval_id: str,
    action_id: str,
    trace_id: str,
    requested_at: str,
    command: str,
    reason: str = "need filesystem access",
    additional_permissions: dict[str, object] | None = None,
) -> None:
    action_request = ActionRequest(
        action_id=action_id,
        action_type="shell_command",
        connector_key="cli",
        plugin_name="agent_cli",
        trace_id=trace_id,
        requested_at=requested_at,
        requested_by="assistant",
        approval_required=True,
        payload={
            "command": command,
            "additional_permissions": dict(additional_permissions or {}),
        },
        metadata={},
    )
    approval_ticket = ApprovalTicket(
        approval_id=approval_id,
        action_id=action_id,
        trace_id=trace_id,
        status="pending",
        requested_at=requested_at,
        requested_by="assistant",
        reason=reason,
        summary="Approve shell command",
        available_decisions=approval_contract_runtime.shell_available_decisions(
            {"command_tokens": command.split()}
        ),
    )
    runtime.gateway_state_store.save_action_request(action_request)
    runtime.gateway_state_store.save_approval_ticket(approval_ticket)


def _seed_background_approval(
    runtime: _ApprovalRuntime,
    *,
    approval_id: str,
    action_id: str,
    trace_id: str,
    requested_at: str,
    task: str,
    provider: str = "openai",
    model: str = "gpt-5.4",
) -> None:
    action_request = ActionRequest(
        action_id=action_id,
        action_type="background_teammate",
        connector_key="cli",
        plugin_name="agent_cli",
        trace_id=trace_id,
        requested_at=requested_at,
        requested_by="assistant",
        approval_required=True,
        payload={
            "task": task,
            "provider": provider,
            "model": model,
            "sandbox_mode": "workspace-write",
            "allowed_paths": ["src", "tests"],
            "blocked_paths": ["README.md"],
            "timeout_seconds": 30.0,
        },
        metadata={},
    )
    approval_ticket = ApprovalTicket(
        approval_id=approval_id,
        action_id=action_id,
        trace_id=trace_id,
        status="pending",
        requested_at=requested_at,
        requested_by="assistant",
        reason="needs a long-running workspace task",
        summary="Approve background teammate live workspace run",
        available_decisions=approval_contract_runtime.generic_available_decisions(),
    )
    runtime.gateway_state_store.save_action_request(action_request)
    runtime.gateway_state_store.save_approval_ticket(approval_ticket)


def _seed_browser_approval(
    runtime: _ApprovalRuntime,
    *,
    approval_id: str,
    action_id: str,
    trace_id: str,
    requested_at: str,
    url: str,
    reason: str = "Browser state-mutating actions require approval.",
) -> None:
    action_request = ActionRequest(
        action_id=action_id,
        action_type="browser.navigate",
        connector_key="browser_gateway",
        plugin_name="browser_phase1",
        trace_id=trace_id,
        requested_at=requested_at,
        requested_by="workflow.browser",
        approval_required=True,
        action_family="browser",
        action_class="state_mutating",
        approval_policy="always",
        audit_stage="browser_state_change",
        payload={
            "browser_request": {
                "action": "navigate",
                "url": url,
                "transport": "client",
            }
        },
        metadata={
            "browser": {
                "command": "navigate",
                "action_class": "state_mutating",
                "approval_policy": "always",
                "audit_stage": "browser_state_change",
                "host": "example.com",
            }
        },
    )
    approval_ticket = ApprovalTicket(
        approval_id=approval_id,
        action_id=action_id,
        trace_id=trace_id,
        status="pending",
        requested_at=requested_at,
        requested_by="workflow.browser",
        reason=reason,
        summary="Approve browser navigation",
        available_decisions=approval_contract_runtime.browser_available_decisions(
            allow_for_session=True
        ),
        session_cache_keys=approval_contract_runtime.browser_session_cache_keys(host="example.com"),
    )
    runtime.gateway_state_store.save_action_request(action_request)
    runtime.gateway_state_store.save_approval_ticket(approval_ticket)


class ApprovalOverlayAppIntegrationTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _capture_queued_commands(app: AgentCliApp) -> list[str]:
        queued: list[str] = []

        async def capture(
            text: str,
            attachments,
            *,
            display_text: str | None = None,
            display_attachments=None,
            priority: str | None = None,
        ) -> None:
            del attachments, display_text, display_attachments, priority
            queued.append(text)

        app._enqueue_runtime_request = capture  # type: ignore[method-assign]
        return queued

    async def _wait_overlay_without_forcing_focus(
        self,
        app: AgentCliApp,
        pilot,
        *,
        timeout: float = 5.0,
    ) -> ApprovalOverlay:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            try:
                overlay = app.query_one(f"#{ApprovalOverlay.ROOT_ID}", ApprovalOverlay)
            except Exception:
                overlay = None
            if isinstance(overlay, ApprovalOverlay) and overlay.is_active:
                await pilot.pause()
                return overlay
            if asyncio.get_running_loop().time() >= deadline:
                self.fail("approval overlay did not become active")
            await pilot.pause()

    async def _wait_overlay(
        self, app: AgentCliApp, pilot, *, timeout: float = 5.0
    ) -> ApprovalOverlay:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            try:
                overlay = app.query_one(f"#{ApprovalOverlay.ROOT_ID}", ApprovalOverlay)
            except Exception:
                overlay = None
            if isinstance(overlay, ApprovalOverlay) and overlay.is_active:
                overlay.focus()
                await pilot.pause()
                return overlay
            if asyncio.get_running_loop().time() >= deadline:
                self.fail("approval overlay did not become active")
            await pilot.pause()

    async def _wait_prompt(
        self, runtime: _ApprovalRuntime, expected: str, *, timeout: float = 5.0
    ) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            if expected in runtime.prompts:
                return
            if asyncio.get_running_loop().time() >= deadline:
                self.fail(f"prompt not observed: {expected}")
            await asyncio.sleep(0.05)

    async def _wait_decision(
        self,
        runtime: _ApprovalRuntime,
        *,
        approval_id: str,
        decision: str,
        timeout: float = 5.0,
    ) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            if any(
                item.get("approval_id") == approval_id and item.get("decision") == decision
                for item in runtime.decisions
            ):
                return
            if asyncio.get_running_loop().time() >= deadline:
                self.fail(f"decision not observed: {approval_id} {decision}")
            await asyncio.sleep(0.05)

    async def test_shell_approval_overlay_submit_shortcut_uses_structured_decision(self) -> None:
        runtime = _ApprovalRuntime()
        _seed_shell_approval(
            runtime,
            approval_id="appr_shell",
            action_id="act_shell",
            trace_id="trace_shell",
            requested_at="2026-04-24T10:00:00Z",
            command="cat /tmp/readme.txt",
            additional_permissions={
                "network": {"enabled": True},
                "file_system": {
                    "read": ["/tmp/readme.txt"],
                    "write": ["/tmp/out.txt"],
                },
            },
        )
        app = AgentCliApp(runtime=runtime)
        queued = self._capture_queued_commands(app)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._write_live_activity_event(
                ActivityEvent(
                    title="Requested shell approval",
                    status="info",
                    detail="appr_shell",
                    code="approval.request.shell",
                    params={
                        "approval_id": "appr_shell",
                        "command": "cat /tmp/readme.txt",
                    },
                )
            )
            overlay = await self._wait_overlay(app, pilot)
            self.assertIn(
                "Permission rule: network; read `/tmp/readme.txt`; write `/tmp/out.txt`",
                overlay.render().plain,
            )

            await pilot.press("a")
            await self._wait_decision(
                runtime,
                approval_id="appr_shell",
                decision="accept_for_session",
            )
            self.assertEqual(queued, [])

            self.assertFalse(overlay.is_active)

    async def test_approval_decision_clears_tab_pending_indicator(self) -> None:
        runtime = _ApprovalRuntime()
        _seed_shell_approval(
            runtime,
            approval_id="appr_clear",
            action_id="act_clear",
            trace_id="trace_clear",
            requested_at="2026-04-24T10:00:00Z",
            command="cat /tmp/clear.txt",
        )
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._write_live_activity_event(
                ActivityEvent(
                    title="Requested shell approval",
                    status="info",
                    detail="appr_clear",
                    code="approval.request.shell",
                    params={
                        "approval_id": "appr_clear",
                        "command": "cat /tmp/clear.txt",
                    },
                )
            )
            overlay = await self._wait_overlay(app, pilot)
            session = app._tab_manager.active_session
            self.assertEqual(session.pending_approvals, ["appr_clear"])
            self.assertIn("!", app.query_one("#tab_bar", TabBar).render().plain)

            await pilot.press("a")
            await self._wait_decision(
                runtime,
                approval_id="appr_clear",
                decision="accept_for_session",
            )
            await pilot.pause()

            self.assertFalse(overlay.is_active)
            self.assertEqual(session.pending_approvals, [])
            self.assertNotIn("!", app.query_one("#tab_bar", TabBar).render().plain)

    async def test_resolved_ticket_status_prunes_tab_pending_indicator(self) -> None:
        runtime = _ApprovalRuntime()
        _seed_shell_approval(
            runtime,
            approval_id="appr_external",
            action_id="act_external",
            trace_id="trace_external",
            requested_at="2026-04-24T10:00:00Z",
            command="cat /tmp/external.txt",
        )
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._write_live_activity_event(
                ActivityEvent(
                    title="Requested shell approval",
                    status="info",
                    detail="appr_external",
                    code="approval.request.shell",
                    params={"approval_id": "appr_external"},
                )
            )
            await self._wait_overlay(app, pilot)
            session = app._tab_manager.active_session
            self.assertEqual(session.pending_approvals, ["appr_external"])

            runtime.decide_approval(
                "appr_external",
                decision=approval_contract_runtime.APPROVAL_DECISION_DECLINE,
                decided_by="external",
            )
            app._sync_pending_approval_surface_state()
            await pilot.pause()

            self.assertEqual(session.pending_approvals, [])
            self.assertNotIn("!", app.query_one("#tab_bar", TabBar).render().plain)

    async def test_multiple_pending_approvals_advance_in_tab_order(self) -> None:
        runtime = _ApprovalRuntime()
        _seed_shell_approval(
            runtime,
            approval_id="appr_first_order",
            action_id="act_first_order",
            trace_id="trace_first_order",
            requested_at="2026-04-24T10:00:00Z",
            command="echo first",
        )
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._write_live_activity_event(
                ActivityEvent(
                    title="Requested shell approval",
                    status="info",
                    detail="appr_first_order",
                    code="approval.request.shell",
                    params={"approval_id": "appr_first_order", "command": "echo first"},
                )
            )
            first_overlay = await self._wait_overlay(app, pilot)
            _seed_shell_approval(
                runtime,
                approval_id="appr_second_order",
                action_id="act_second_order",
                trace_id="trace_second_order",
                requested_at="2026-04-24T10:00:01Z",
                command="echo second",
            )
            app._write_live_activity_event(
                ActivityEvent(
                    title="Requested shell approval",
                    status="info",
                    detail="appr_second_order",
                    code="approval.request.shell",
                    params={"approval_id": "appr_second_order", "command": "echo second"},
                )
            )
            session = app._tab_manager.active_session
            self.assertEqual(
                session.pending_approvals,
                ["appr_first_order", "appr_second_order"],
            )
            self.assertEqual(first_overlay.approval_id, "appr_first_order")

            await pilot.press("a")
            await self._wait_decision(
                runtime,
                approval_id="appr_first_order",
                decision="accept_for_session",
            )
            second_overlay = await self._wait_overlay(app, pilot)
            self.assertEqual(session.pending_approvals, ["appr_second_order"])
            self.assertEqual(second_overlay.approval_id, "appr_second_order")

            await pilot.press("a")
            await self._wait_decision(
                runtime,
                approval_id="appr_second_order",
                decision="accept_for_session",
            )
            await pilot.pause()
            self.assertEqual(session.pending_approvals, [])
            self.assertNotIn("!", app.query_one("#tab_bar", TabBar).render().plain)

    async def test_failed_approval_decision_restores_retry_overlay(self) -> None:
        runtime = _ApprovalRuntime()
        _seed_shell_approval(
            runtime,
            approval_id="appr_retry",
            action_id="act_retry",
            trace_id="trace_retry",
            requested_at="2026-04-24T10:00:00Z",
            command="cat /tmp/retry.txt",
        )
        original_decide_approval = runtime.decide_approval
        attempts = {"count": 0}

        def _flaky_decide_approval(*args, **kwargs):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise ValueError("temporary decision failure")
            return original_decide_approval(*args, **kwargs)

        runtime.decide_approval = _flaky_decide_approval  # type: ignore[method-assign]
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._write_live_activity_event(
                ActivityEvent(
                    title="Requested shell approval",
                    status="info",
                    detail="appr_retry",
                    code="approval.request.shell",
                    params={"approval_id": "appr_retry", "command": "cat /tmp/retry.txt"},
                )
            )
            first_overlay = await self._wait_overlay(app, pilot)
            self.assertEqual(first_overlay.approval_id, "appr_retry")

            await pilot.press("a")
            retry_overlay = await self._wait_overlay(app, pilot)
            session = app._tab_manager.active_session
            self.assertEqual(retry_overlay.approval_id, "appr_retry")
            self.assertEqual(session.pending_approvals, ["appr_retry"])
            self.assertIn("!", app.query_one("#tab_bar", TabBar).render().plain)

            await pilot.press("a")
            await self._wait_decision(
                runtime,
                approval_id="appr_retry",
                decision="accept_for_session",
            )
            await pilot.pause()
            self.assertEqual(attempts["count"], 2)
            self.assertEqual(session.pending_approvals, [])
            self.assertNotIn("!", app.query_one("#tab_bar", TabBar).render().plain)

    async def test_startup_pending_approval_keeps_overlay_focused_and_accepts_shortcuts(
        self,
    ) -> None:
        runtime = _ApprovalRuntime()
        _seed_shell_approval(
            runtime,
            approval_id="appr_startup",
            action_id="act_startup",
            trace_id="trace_startup",
            requested_at="2026-04-24T10:00:00Z",
            command="cat /tmp/startup.txt",
        )
        app = AgentCliApp(runtime=runtime)
        queued = self._capture_queued_commands(app)

        async with app.run_test() as pilot:
            await pilot.pause()
            overlay = await self._wait_overlay_without_forcing_focus(app, pilot)

            self.assertIs(app.focused, overlay)

            await pilot.press("a")
            await self._wait_decision(
                runtime,
                approval_id="appr_startup",
                decision="accept_for_session",
            )
            self.assertEqual(queued, [])

    async def test_escape_submits_cancel_and_advances_to_next_pending_approval(self) -> None:
        runtime = _ApprovalRuntime()
        _seed_shell_approval(
            runtime,
            approval_id="appr_first",
            action_id="act_first",
            trace_id="trace_first",
            requested_at="2026-04-24T10:00:00Z",
            command="echo first",
        )
        _seed_shell_approval(
            runtime,
            approval_id="appr_second",
            action_id="act_second",
            trace_id="trace_second",
            requested_at="2026-04-24T10:00:01Z",
            command="echo second",
        )
        runtime.gateway_state_store.approval_tickets.pop("appr_second", None)
        runtime.gateway_state_store.action_requests.pop("act_second", None)
        app = AgentCliApp(runtime=runtime)
        queued = self._capture_queued_commands(app)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._write_live_activity_event(
                ActivityEvent(
                    title="Requested shell approval",
                    status="info",
                    detail="appr_first",
                    code="approval.request.shell",
                    params={"approval_id": "appr_first", "command": "echo first"},
                )
            )
            first_overlay = await self._wait_overlay(app, pilot)
            self.assertEqual(first_overlay.approval_id, "appr_first")

            _seed_shell_approval(
                runtime,
                approval_id="appr_second",
                action_id="act_second",
                trace_id="trace_second",
                requested_at="2026-04-24T10:00:01Z",
                command="echo second",
            )
            app._write_live_activity_event(
                ActivityEvent(
                    title="Requested shell approval",
                    status="info",
                    detail="appr_second",
                    code="approval.request.shell",
                    params={"approval_id": "appr_second", "command": "echo second"},
                )
            )
            await pilot.pause()
            self.assertTrue(app._cancel_approval_overlay_on_escape())
            await self._wait_decision(
                runtime,
                approval_id="appr_first",
                decision="cancel",
            )

            self.assertEqual(queued, [])
            second_overlay = await self._wait_overlay(app, pilot)
            self.assertEqual(second_overlay.approval_id, "appr_second")

    async def test_background_action_approval_overlay_submit_shortcut_uses_structured_decision(
        self,
    ) -> None:
        runtime = _ApprovalRuntime()
        _seed_background_approval(
            runtime,
            approval_id="appr_bg",
            action_id="act_bg",
            trace_id="trace_bg",
            requested_at="2026-04-24T10:00:00Z",
            task="Summarize the repo entrypoints",
        )
        app = AgentCliApp(runtime=runtime)
        queued = self._capture_queued_commands(app)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._write_live_activity_event(
                ActivityEvent(
                    title="Requested background teammate approval",
                    status="info",
                    detail="appr_bg",
                    code="approval.request.action",
                    params={
                        "approval_id": "appr_bg",
                        "task": "Summarize the repo entrypoints",
                        "summary": "Approve background teammate live workspace run",
                    },
                )
            )
            overlay = await self._wait_overlay(app, pilot)
            rendered = overlay.render().plain
            self.assertIn("Task: Summarize the repo entrypoints", rendered)
            self.assertIn("Sandbox: workspace-write", rendered)
            self.assertIn("Allowed paths: src, tests", rendered)
            self.assertIn("Blocked paths: README.md", rendered)

            await pilot.press("y")
            await self._wait_decision(
                runtime,
                approval_id="appr_bg",
                decision="accept",
            )
            self.assertEqual(queued, [])

    async def test_browser_host_approval_overlay_uses_session_shortcut_contract(self) -> None:
        runtime = _ApprovalRuntime()
        _seed_browser_approval(
            runtime,
            approval_id="appr_browser",
            action_id="act_browser",
            trace_id="trace_browser",
            requested_at="2026-04-24T10:00:00Z",
            url="https://example.com/settings",
        )
        app = AgentCliApp(runtime=runtime)
        queued = self._capture_queued_commands(app)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._write_live_activity_event(
                ActivityEvent(
                    title="Requested browser approval",
                    status="info",
                    detail="appr_browser",
                    code="approval.request.action",
                    params={"approval_id": "appr_browser"},
                )
            )
            overlay = await self._wait_overlay(app, pilot)
            rendered = overlay.render().plain
            self.assertIn('Do you want to approve browser access to "example.com"?', rendered)
            self.assertIn("Host: example.com", rendered)
            self.assertIn("URL: https://example.com/settings", rendered)
            self.assertIn("Yes, and allow this host for this conversation", rendered)

            overlay._submit_option(overlay._options[1])
            await self._wait_decision(
                runtime,
                approval_id="appr_browser",
                decision="accept_for_session",
            )
            self.assertEqual(queued, [])
