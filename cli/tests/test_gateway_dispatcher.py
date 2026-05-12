from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from unittest.mock import patch

from cli.agent_cli.gateway_api.gateway_ws import gateway_ws_capabilities
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.tools import ToolRegistry
from cli.agent_cli.models import AgentIntent, ToolEvent
from cli.agent_cli.gateway_server.dispatcher import (
    dispatch_gateway_method,
    gateway_dispatcher_methods,
    gateway_dispatcher_supports_method,
)
from cli.agent_cli.gateway_server.write_budget import __testing

@dataclass
class _Item:
    payload: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return dict(self.payload)

    def __getattr__(self, name: str):
        try:
            return self.payload[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

class _Agent:
    def __init__(self) -> None:
        self.delegate_overrides: dict[str, dict[str, object]] = {}

    def provider_status(self) -> dict[str, str]:
        delegate_subagent = "test-provider | inherit | source=inherit_main"
        delegate_teammate = "test-provider | inherit | source=inherit_main"
        teammate_override = self.delegate_overrides.get("teammate")
        if isinstance(teammate_override, dict):
            model_text = str(teammate_override.get("model") or "").strip().lower()
            resolved_model = "inherit" if model_text in {"default", "auto", "inherit"} else str(teammate_override.get("model") or "")
            delegate_teammate = (
                f"{str(teammate_override.get('provider') or 'test-provider')} | {resolved_model} | "
                f"reasoning={str(teammate_override.get('reasoning_effort') or 'high')} | "
                f"timeout={str(teammate_override.get('timeout') or '30')} | "
                "source=session_override"
            )
        return {
            "provider_label": "test-provider",
            "platform_family": "linux",
            "platform_os": "linux",
            "shell_kind": "bash",
            "delegate_subagent": delegate_subagent,
            "delegate_teammate": delegate_teammate,
        }

    @staticmethod
    def available_models():
        return [
            {"model_key": "gpt_54", "model_id": "gpt-5.4"},
            {"model_key": "glm_5", "model_id": "glm-5"},
        ]

    def session_delegate_overrides(self):
        return {
            role_name: dict(payload)
            for role_name, payload in self.delegate_overrides.items()
        }

    def configure_delegate_selection(self, role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None, clear=False):
        if clear:
            self.delegate_overrides.pop(str(role_name), None)
            return self.provider_status()
        payload: dict[str, object] = {"source": "session_override"}
        if model is not None:
            payload["model"] = str(model)
        if provider is not None:
            payload["provider"] = str(provider)
        if reasoning_effort is not None:
            payload["reasoning_effort"] = str(reasoning_effort)
        if timeout is not None:
            payload["timeout"] = int(timeout)
        self.delegate_overrides[str(role_name)] = payload
        return self.provider_status()


def _browser_action_policy_payload() -> dict[str, object]:
    return {
        "action_kind": "browser",
        "decision": "requires_approval",
        "requirement": "needs_approval",
        "reason_code": "browser.external_side_effecting.approval_required",
        "reason_text": "Browser actions with external side effects require approval.",
        "approval_policy": "always",
        "sandbox_mode": "",
        "approval_required": True,
        "blocked": False,
        "matched_rules": [
            {
                "source": "browser_classification",
                "rule_id": "browser.external_side_effecting",
                "decision": "requires_approval",
                "evidence": {
                    "command": "act",
                    "action_kind": "click",
                    "action_class": "external_side_effecting",
                    "audit_stage": "browser_external_effect",
                },
            }
        ],
        "proposed_rule": None,
        "normalized_targets": ["act", "click"],
        "metadata": {
            "action_family": "browser",
            "action_class": "external_side_effecting",
            "audit_stage": "browser_external_effect",
            "command": "act",
            "action_kind": "click",
        },
    }


def _browser_action_request_payload() -> dict[str, object]:
    return {
        "action_id": "action_1",
        "action_type": "browser.act",
        "connector_key": "browser_proxy",
        "plugin_name": "easyclaw",
        "trace_id": "trace_1",
        "workflow_run_id": "wf_1",
        "requested_at": "2026-03-30T09:12:00Z",
        "requested_by": "workflow.browser",
        "approval_required": True,
        "action_family": "browser",
        "action_class": "external_side_effecting",
        "approval_policy": "always",
        "audit_stage": "browser_external_effect",
        "payload": {"kind": "click", "ref": "e4"},
        "metadata": {
            "browser": {
                "command": "act",
                "action_kind": "click",
                "action_class": "external_side_effecting",
            },
            "action_policy": _browser_action_policy_payload(),
        },
    }


def _browser_approval_ticket_payload() -> dict[str, object]:
    return {
        "approval_id": "approval_1",
        "action_id": "action_1",
        "trace_id": "trace_1",
        "status": "pending",
        "requested_at": "2026-03-30T09:12:05Z",
        "requested_by": "workflow.browser",
        "summary": "Approve browser click",
        "reason": "Browser external effect requires approval.",
        "metadata": {
            "source_action_type": "browser.act",
            "source_action_family": "browser",
            "source_action_class": "external_side_effecting",
            "source_approval_policy": "always",
            "source_audit_stage": "browser_external_effect",
            "browser": {
                "command": "act",
                "action_kind": "click",
                "action_class": "external_side_effecting",
            },
            "action_policy": _browser_action_policy_payload(),
        },
    }

class _StateStore:
    def __init__(self) -> None:
        self.workflow_runs = {
            "wf_1": _Item(
                {
                    "workflow_run_id": "wf_1",
                    "trace_id": "trace_1",
                    "plugin_name": "github_phase1",
                    "workflow_name": "handle_github_issue_opened",
                    "status": "paused",
                    "current_step": "paused_for_operator_review",
                    "result_summary": "awaiting operator review",
                    "event_id": "evt_1",
                    "started_at": "2026-03-30T09:11:00Z",
                    "updated_at": "2026-03-30T09:12:30Z",
                }
            )
        }
        self.audit_records = [
            _Item(
                {
                    "audit_id": "audit_1",
                    "trace_id": "trace_1",
                    "workflow_run_id": "wf_1",
                    "created_at": "2026-03-30T09:12:06Z",
                }
            ),
            _Item({"audit_id": "audit_2", "trace_id": "trace_2"}),
        ]

    def get_approval_ticket(self, approval_id: str):
        if approval_id != "approval_1":
            return None
        return _Item(_browser_approval_ticket_payload())

    def get_action_request(self, action_id: str):
        if action_id != "action_1":
            return None
        return _Item(_browser_action_request_payload())

    def list_audit_records(self, limit: int = 200):
        return self.audit_records[:limit]

    def get_workflow_run(self, workflow_run_id: str):
        return self.workflow_runs.get(workflow_run_id)

class _Runtime:
    def __init__(self) -> None:
        self.agent = _Agent()
        self.gateway_state_store = _StateStore()
        self.cwd = Path("/tmp/agenthub-gateway-config")
        self.runtime_policy_payload = {
            "approval_policy": "on-request",
            "sandbox_mode": "workspace-write",
            "web_search_mode": "live",
            "network_access": "enabled",
        }
        self._gui_browser_headless = False
        self._gui_plugin_auto_load = True
        self.tools = type(
            "Tools",
            (),
            {
                "capabilities": staticmethod(
                    lambda: {
                        "ok": True,
                        "count": 11,
                        "workspace_trust": "trusted",
                        "mcp_servers": {"docs": {"url": "https://docs.example/mcp"}},
                        "app_connectors": [{"connector_id": "demo_app", "plugin_name": "demo"}],
                    }
                )
            },
        )()

    def runtime_policy_status(self) -> dict[str, str]:
        return dict(self.runtime_policy_payload)

    def configure_runtime_policy(
        self,
        *,
        approval_policy: str | None = None,
        sandbox_mode: str | None = None,
        web_search_mode: str | None = None,
        network_access_enabled: str | bool | None = None,
    ) -> dict[str, str]:
        if approval_policy is not None:
            self.runtime_policy_payload["approval_policy"] = str(approval_policy)
        if sandbox_mode is not None:
            self.runtime_policy_payload["sandbox_mode"] = str(sandbox_mode)
        if web_search_mode is not None:
            self.runtime_policy_payload["web_search_mode"] = str(web_search_mode)
        if network_access_enabled is not None:
            value = str(network_access_enabled).strip().lower()
            self.runtime_policy_payload["network_access"] = "disabled" if value in {"false", "disabled", "0"} else "enabled"
        return self.runtime_policy_status()

    def set_cwd(self, cwd: str | Path) -> Path:
        self.cwd = Path(cwd).resolve()
        return self.cwd

    def configure_delegate_selection(
        self,
        role_name: str,
        *,
        model: str | None = None,
        provider: str | None = None,
        reasoning_effort: str | None = None,
        timeout: object = None,
        clear: bool = False,
    ) -> dict[str, str]:
        return self.agent.configure_delegate_selection(
            role_name,
            model=model,
            provider=provider,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            clear=clear,
        )

    @staticmethod
    def gateway_state_snapshot(*, limit: int = 20) -> dict[str, object]:
        return {
            "events": [
                _Item(
                    {
                        "event_id": "evt_1",
                        "trace_id": "trace_1",
                        "received_at": "2026-03-30T09:10:59Z",
                    }
                )
            ],
            "workflow_runs": [
                _Item(
                    {
                        "workflow_run_id": "wf_1",
                        "trace_id": "trace_1",
                        "plugin_name": "github_phase1",
                        "workflow_name": "handle_github_issue_opened",
                        "status": "paused",
                        "current_step": "paused_for_operator_review",
                        "result_summary": "awaiting operator review",
                        "event_id": "evt_1",
                        "started_at": "2026-03-30T09:11:00Z",
                        "updated_at": "2026-03-30T09:12:30Z",
                    }
                )
            ],
            "action_requests": [_Item(_browser_action_request_payload())],
            "approval_tickets": [_Item(_browser_approval_ticket_payload())],
            "audit_records": [
                _Item(
                    {
                        "audit_id": "audit_1",
                        "trace_id": "trace_1",
                        "workflow_run_id": "wf_1",
                        "created_at": "2026-03-30T09:12:06Z",
                    }
                )
            ],
            "diagnostics": {
                "workflow_diagnostics": [
                    {
                        "trace_id": "trace_1",
                        "workflow_run_id": "wf_1",
                        "workflow_status": "paused",
                        "workflow_name": "handle_github_issue_opened",
                        "plugin_name": "github_phase1",
                        "reasoning": {"summary": "awaiting operator review"},
                        "recommendation": {"count": 1},
                        "approval": {"status": "pending"},
                        "execution": {"status": "not_executed"},
                    }
                ],
                "approval_diagnostics": [{"approval_id": "approval_1", "trace_id": "trace_1"}],
            },
        }

    @staticmethod
    def list_approval_tickets(*, limit: int = 20, status: str | None = None):
        payload = _browser_approval_ticket_payload()
        payload["status"] = status or "pending"
        return [_Item(payload)]

    @staticmethod
    def list_approval_diagnostics(*, limit: int = 20, status: str | None = None):
        return [{"approval_id": "approval_1", "status": status or "pending"}]

    def save_gateway_action_request(self, item):
        return self.gateway_state_store.save_action_request(item)

    def save_gateway_approval_ticket(self, item):
        return self.gateway_state_store.save_approval_ticket(item)

    @staticmethod
    def decide_approval(
        approval_id: str,
        *,
        approved: bool | None = None,
        decision: str | None = None,
        decided_by: str,
        decision_note: str = "",
    ) -> dict[str, object]:
        resolved_decision = str(decision or ("accept" if approved else "decline"))
        approved = resolved_decision in {"accept", "accept_for_session", "accept_with_execpolicy_amendment"}
        return {
            "approval_ticket": _Item(
                {
                    "approval_id": approval_id,
                    "status": "approved" if approved else "rejected",
                    "decision_type": resolved_decision,
                }
            ),
            "action_request": _Item({"action_id": "action_1"}),
            "action_result": _Item({"result_id": "result_1"}),
            "audit_records": [_Item({"audit_id": "audit_1"})],
        }

    @staticmethod
    def request_gateway_action(**kwargs):
        return {
            "action_request": _Item({"action_id": "action_1", "action_type": kwargs.get("action_type")}),
            "approval_ticket": _Item({"approval_id": "approval_1", "status": "pending"}),
            "audit_records": [_Item({"audit_id": "audit_1"})],
        }

    def update_workflow_run_state(
        self,
        workflow_run_id: str,
        *,
        status: str | None = None,
        current_step: str | None = None,
        result_summary: str | None = None,
        context_updates: dict[str, object] | None = None,
        finished: bool = False,
    ):
        current = self.gateway_state_store.get_workflow_run(workflow_run_id)
        payload = dict(current.payload if current is not None else {})
        payload["workflow_run_id"] = workflow_run_id
        if status is not None:
            payload["status"] = status
        if current_step is not None:
            payload["current_step"] = current_step
        if result_summary is not None:
            payload["result_summary"] = result_summary
        if context_updates is not None:
            payload["context"] = dict(context_updates)
        if finished:
            payload["finished_at"] = "2026-03-28T00:00:00Z"
        updated = _Item(payload)
        self.gateway_state_store.workflow_runs[workflow_run_id] = updated
        return updated

    def append_gateway_audit_record(self, item):
        self.gateway_state_store.audit_records.append(item)
        return item

    @staticmethod
    def dispatch_gateway_event(event):
        return {
            "event": event,
            "decision": type(
                "Decision",
                (),
                {
                    "target_kind": "workflow",
                    "plugin_name": "github_phase1",
                    "workflow_name": "handle_github_issue_opened",
                    "reason": "matched trigger",
                },
            )(),
            "workflow_run": _Item({"workflow_run_id": "wf_1", "trace_id": getattr(event, "trace_id", "trace_1")}),
            "audit_records": [_Item({"audit_id": "audit_1", "trace_id": getattr(event, "trace_id", "trace_1")})],
        }

def test_gateway_dispatcher_methods_cover_protocol_and_legacy_surface() -> None:
    methods = set(gateway_dispatcher_methods())

    assert "gateway/state" in methods
    assert "approval/list" in methods
    assert "browser/proxy" in methods
    assert "connect.initialize" in methods
    assert "access.posture.get" in methods
    assert "nodes.list" in methods
    assert "config.apply" in methods
    assert "gateway.state.get" in methods
    assert "github.actions.dispatch" in methods
    assert gateway_dispatcher_supports_method("health.get") is True
    assert gateway_dispatcher_supports_method("missing.method") is False

def test_gateway_dispatcher_returns_protocol_capabilities_payload() -> None:
    outcome = dispatch_gateway_method(
        method="connect.initialize",
        params={},
        runtime=_Runtime(),
    )

    assert outcome.ok is True
    assert outcome.result["protocolVersion"] == "v1"
    assert outcome.result["runtimeRegistry"]["workspaceTrust"] == "trusted"
    assert outcome.result["runtimeRegistry"]["toolCount"] == 11
    assert outcome.result["runtimeRegistry"]["source"] == "tools.capabilities"
    assert outcome.result["accessPosture"]["access"]["posture"] == "local-only"
    assert outcome.result["accessPosture"]["auth"]["mode"] == "trusted_local"
    assert outcome.result["accessPosture"]["summary"]["pendingPairingRequestCount"] == 0
    assert any(item["method"] == "gateway.state.get" for item in outcome.result["methods"])
    assert any(item["method"] == "access.posture.get" for item in outcome.result["methods"])
    assert any(item["method"] == "nodes.list" for item in outcome.result["methods"])
    assert any(item["method"] == "config.validate" for item in outcome.result["methods"])
    assert "gateway/dispatch" in outcome.result["legacyMethods"]

def test_gateway_dispatcher_exposes_access_posture_and_pairing_summary() -> None:
    runtime = _Runtime()
    runtime.list_approval_tickets = lambda limit=20, status=None: [  # type: ignore[method-assign]
        _Item(
            {
                "approval_id": "approval_pair_1",
                "trace_id": "trace_pair_1",
                "status": "pending",
                "title": "Device pairing request",
                "action_type": "pairing.request",
                "requested_at": "2026-03-30T09:10:00Z",
            }
        )
    ]
    outcome = dispatch_gateway_method(
        method="access.posture.get",
        params={},
        runtime=runtime,
        client_info={
            "auth": {
                "actorId": "remote-operator-1",
                "role": "operator",
                "authenticated": True,
                "authSource": "shared-secret",
                "clientType": "gateway",
                "scopes": ["gateway.read"],
            }
        },
    )

    assert outcome.ok is True
    assert outcome.result["access"]["posture"] == "local+remote"
    assert outcome.result["auth"]["origin"] == "remote"
    assert outcome.result["auth"]["mode"] == "remote_authenticated"
    assert outcome.result["pairing"]["pendingRequestCount"] == 1
    assert outcome.result["pairing"]["pendingApprovalCount"] == 1
    assert outcome.result["pairing"]["hasNativeContract"] is False
    assert outcome.result["pairing"]["pendingRefs"] == [
        {
            "approvalId": "approval_pair_1",
            "traceId": "trace_pair_1",
            "title": "Device pairing request",
            "actionType": "pairing.request",
            "requestedAt": "2026-03-30T09:10:00Z",
        }
    ]
    assert outcome.result["summary"]["pendingPairingRequestCount"] == 1

def test_gateway_dispatcher_exposes_nodes_inventory_contract() -> None:
    runtime = _Runtime()
    runtime.list_approval_tickets = lambda limit=20, status=None: [  # type: ignore[method-assign]
        _Item(
            {
                "approval_id": "approval_pair_1",
                "trace_id": "trace_pair_1",
                "status": "pending",
                "title": "Device pairing request",
                "action_type": "pairing.request",
                "requested_at": "2026-03-30T09:10:00Z",
            }
        )
    ]
    outcome = dispatch_gateway_method(
        method="nodes.list",
        params={"limit": 10},
        runtime=runtime,
        client_info={
            "auth": {
                "actorId": "remote-operator-1",
                "role": "operator",
                "authenticated": True,
                "authSource": "shared-secret",
                "clientType": "gateway",
                "scopes": ["gateway.read"],
            }
        },
    )

    assert outcome.ok is True
    assert outcome.result["summary"]["totalNodes"] >= 1
    assert outcome.result["summary"]["pendingPairingRequestCount"] == 1
    assert outcome.result["capabilities"]["readOnly"] is True
    assert outcome.result["capabilities"]["pairingWriteSupported"] is False
    assert outcome.result["source"]["contract"] == "nodes.list.v1"
    assert outcome.result["accessPosture"]["summary"]["pendingPairingRequestCount"] == 1
    assert outcome.result["accessPosture"]["pairing"]["pendingRefs"] == [
        {
            "approvalId": "approval_pair_1",
            "traceId": "trace_pair_1",
            "title": "Device pairing request",
            "actionType": "pairing.request",
            "requestedAt": "2026-03-30T09:10:00Z",
        }
    ]
    assert outcome.result["runtimeRegistry"]["toolCount"] == 11
    assert any(item["kind"] == "local" for item in outcome.result["nodes"])
    assert all(
        item["pairing"]["pendingRefs"] == [
            {
                "approvalId": "approval_pair_1",
                "traceId": "trace_pair_1",
                "title": "Device pairing request",
                "actionType": "pairing.request",
                "requestedAt": "2026-03-30T09:10:00Z",
            }
        ]
        for item in outcome.result["nodes"]
    )

def test_gateway_dispatcher_validates_and_applies_config_contract() -> None:
    runtime = _Runtime()
    runtime.cwd.mkdir(parents=True, exist_ok=True)
    next_workspace = runtime.cwd / "next"
    next_workspace.mkdir(parents=True, exist_ok=True)

    validation = dispatch_gateway_method(
        method="config.validate",
        params={
            "workspaceRoot": str(next_workspace),
            "browserHeadless": True,
            "runtimePolicy": {
                "approval_policy": "never",
                "network_access": "disabled",
            },
        },
        runtime=runtime,
    )

    assert validation.ok is True
    assert sorted(validation.result["applyableFields"]) == [
        "approval_policy",
        "browserHeadless",
        "network_access",
        "workspaceRoot",
    ]
    assert validation.result["restart"]["required"] is True
    assert validation.result["restart"]["allowed"] is False

    applied = dispatch_gateway_method(
        method="config.apply",
        params={
            "workspaceRoot": str(next_workspace),
            "browserHeadless": True,
            "runtimePolicy": {
                "approval_policy": "never",
                "network_access": "disabled",
            },
        },
        runtime=runtime,
    )

    assert applied.ok is True
    assert applied.result["status"] == "applied"
    assert "workspaceRoot" in applied.result["appliedFields"]
    assert "delegationModels" in applied.result["settings"]
    assert applied.result["settings"]["browserHeadless"] is True
    assert applied.result["settings"]["workspaceRoot"] == str(next_workspace.resolve())
    assert applied.result["settings"]["runtimePolicy"]["approval_policy"] == "never"
    assert applied.result["settings"]["runtimePolicy"]["network_access"] == "restricted"

def test_gateway_dispatcher_validates_and_applies_delegation_model_contract() -> None:
    runtime = _Runtime()

    validation = dispatch_gateway_method(
        method="config.validate",
        params={
            "delegationModels": {
                "teammate": {
                    "model": "inherit",
                    "timeout": 20,
                }
            }
        },
        runtime=runtime,
    )

    assert validation.ok is True
    assert "delegationModels.teammate" in validation.result["applyableFields"]

    applied = dispatch_gateway_method(
        method="config.apply",
        params={
            "delegationModels": {
                "teammate": {
                    "model": "inherit",
                    "timeout": 20,
                }
            }
        },
        runtime=runtime,
    )

    assert applied.ok is True
    assert applied.result["status"] == "applied"
    assert "delegationModels.teammate" in applied.result["appliedFields"]
    teammate = applied.result["settings"]["delegationModels"]["teammate"]
    assert teammate["overrideActive"] is True
    assert teammate["model"] == "inherit"
    assert teammate["timeout"] == 20

def test_gateway_dispatcher_reports_blocked_config_fields() -> None:
    runtime = _Runtime()

    outcome = dispatch_gateway_method(
        method="config.validate",
        params={
            "model": "unknown-model",
            "workspaceRoot": "/definitely/missing/workspace",
        },
        runtime=runtime,
    )

    assert outcome.ok is True
    assert outcome.result["applyableFields"] == []
    assert outcome.result["blockedFields"] == ["model", "workspaceRoot"]
    reasons = {item["field"]: item["reason"] for item in outcome.result["blocked"]}
    assert "未知 model selector" in reasons["model"]
    assert "不存在" in reasons["workspaceRoot"]

def test_gateway_dispatcher_routes_github_family_handlers_for_registered_methods() -> None:
    __testing.reset_control_plane_write_budget_state()
    with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test"}, clear=False):
        outcome = dispatch_gateway_method(
            method="github.issues.create",
            params={"repo": "hoteye/simulate-app", "title": "Need review"},
            runtime=_Runtime(),
            client_info={"role": "operator", "actorId": "operator-1"},
        )

    assert outcome.ok is True
    assert outcome.result["status"] == "approval_required"
    assert outcome.result["method"] == "github.issues.create"
    assert outcome.result["approvalTicket"]["approval_id"] == "approval_1"
    assert outcome.result["actionRequest"]["action_id"] == "action_1"

def test_gateway_dispatcher_builds_trace_timeline_from_runtime_snapshot() -> None:
    outcome = dispatch_gateway_method(
        method="gateway.trace.timeline",
        params={"traceId": "trace_1"},
        runtime=_Runtime(),
        client_info={"role": "operator", "actorId": "operator-1"},
    )

    assert outcome.ok is True
    assert outcome.result["traceId"] == "trace_1"
    action_entry = next(item for item in outcome.result["timeline"] if item["kind"] == "actionRequests")
    approval_entry = next(item for item in outcome.result["timeline"] if item["kind"] == "approvalTickets")
    assert action_entry["item"]["approval_required"] is True
    assert action_entry["item"]["action_class"] == "external_side_effecting"
    assert action_entry["item"]["approval_policy"] == "always"
    assert action_entry["item"]["audit_stage"] == "browser_external_effect"
    assert action_entry["item"]["metadata"]["action_policy"]["matched_rules"][0]["rule_id"] == (
        "browser.external_side_effecting"
    )
    assert approval_entry["item"]["metadata"]["action_policy"]["decision"] == "requires_approval"

def test_gateway_dispatcher_health_probes_reports_gateway_state_counts() -> None:
    outcome = dispatch_gateway_method(
        method="health.probes",
        params={},
        runtime=_Runtime(),
        client_info={"role": "operator", "actorId": "operator-1"},
    )

    assert outcome.ok is True
    assert outcome.result["status"] == "ok"
    assert outcome.result["probes"]["gatewayStateStore"] == {
        "ok": True,
        "events": 1,
        "workflowRuns": 1,
        "approvalTickets": 1,
    }

def test_gateway_dispatcher_returns_bounded_log_tail(tmp_path: Path) -> None:
    runtime = _Runtime()
    runtime.gateway_state_store.base_dir = tmp_path
    (tmp_path / "audit_records.jsonl").write_text("line-1\nline-2\nline-3\n", encoding="utf-8")

    outcome = dispatch_gateway_method(
        method="logs.tail",
        params={"source": "gateway.audit_records", "lines": 2},
        runtime=runtime,
        client_info={"role": "operator", "actorId": "operator-1"},
    )

    assert outcome.ok is True
    assert outcome.result["source"] == "gateway.audit_records"
    assert outcome.result["lines"] == ["line-2", "line-3"]
    assert outcome.result["truncated"] is True

def test_gateway_dispatcher_lists_workflows_with_diagnostics() -> None:
    outcome = dispatch_gateway_method(
        method="workflows.list",
        params={"limit": 5},
        runtime=_Runtime(),
        client_info={"role": "operator", "actorId": "operator-1"},
    )

    assert outcome.ok is True
    assert outcome.result["workflowRuns"][0]["workflow_run_id"] == "wf_1"
    assert outcome.result["workflowDiagnostics"][0]["workflow_run_id"] == "wf_1"

def test_gateway_dispatcher_returns_workflow_detail_bundle() -> None:
    outcome = dispatch_gateway_method(
        method="workflows.get",
        params={"workflowRunId": "wf_1"},
        runtime=_Runtime(),
        client_info={"role": "operator", "actorId": "operator-1"},
    )

    assert outcome.ok is True
    assert outcome.result["workflowRun"]["workflow_name"] == "handle_github_issue_opened"
    assert outcome.result["workflowDiagnostic"]["approval"]["status"] == "pending"
    assert outcome.result["actionRequests"][0]["approval_required"] is True
    assert outcome.result["actionRequests"][0]["action_class"] == "external_side_effecting"
    assert outcome.result["actionRequests"][0]["approval_policy"] == "always"
    assert outcome.result["actionRequests"][0]["audit_stage"] == "browser_external_effect"
    assert outcome.result["actionRequests"][0]["metadata"]["action_policy"]["decision"] == "requires_approval"
    assert outcome.result["approvalTickets"][0]["metadata"]["action_policy"]["metadata"]["action_class"] == (
        "external_side_effecting"
    )
    assert outcome.result["timeline"][0]["kind"] == "events"

def test_gateway_dispatcher_returns_approval_list_with_action_policy_snapshot() -> None:
    outcome = dispatch_gateway_method(
        method="approvals.list",
        params={"limit": 5},
        runtime=_Runtime(),
        client_info={"role": "operator", "actorId": "operator-1"},
    )

    assert outcome.ok is True
    approval = outcome.result["approvalTickets"][0]
    assert approval["approval_id"] == "approval_1"
    assert approval["status"] == "pending"
    assert approval["metadata"]["action_policy"]["action_kind"] == "browser"
    assert approval["metadata"]["action_policy"]["decision"] == "requires_approval"
    assert outcome.result["approvalDiagnostics"][0]["approval_id"] == "approval_1"

def test_gateway_dispatcher_resume_updates_workflow_state_and_audit() -> None:
    runtime = _Runtime()
    outcome = dispatch_gateway_method(
        method="workflows.resume",
        params={"workflowRunId": "wf_1", "decidedBy": "operator-1"},
        runtime=runtime,
        client_info={"role": "operator", "actorId": "operator-1"},
    )

    assert outcome.ok is True
    assert outcome.result["resumeRequested"] is True
    assert outcome.result["workflowRun"]["status"] == "running"
    assert outcome.result["auditRecord"]["workflow_run_id"] == "wf_1"

def test_gateway_dispatcher_returns_approval_bundle_for_approvals_get() -> None:
    outcome = dispatch_gateway_method(
        method="approvals.get",
        params={"approvalId": "approval_1"},
        runtime=_Runtime(),
        client_info={"role": "operator", "actorId": "operator-1"},
    )

    assert outcome.ok is True
    assert outcome.result["approvalTicket"]["approval_id"] == "approval_1"
    assert outcome.result["actionRequest"]["action_type"] == "browser.act"
    assert outcome.result["actionRequest"]["approval_required"] is True
    assert outcome.result["actionRequest"]["action_class"] == "external_side_effecting"
    assert outcome.result["actionRequest"]["approval_policy"] == "always"
    assert outcome.result["actionRequest"]["audit_stage"] == "browser_external_effect"
    assert outcome.result["actionRequest"]["metadata"]["action_policy"]["matched_rules"][0]["rule_id"] == (
        "browser.external_side_effecting"
    )
    assert outcome.result["approvalTicket"]["metadata"]["action_policy"]["metadata"]["action_kind"] == "click"
    assert [item["audit_id"] for item in outcome.result["auditRecords"]] == ["audit_1"]

def test_gateway_dispatcher_rejects_invalid_approval_resolution_decision() -> None:
    outcome = dispatch_gateway_method(
        method="approvals.resolve",
        params={"approvalId": "approval_1", "decision": "later"},
        runtime=_Runtime(),
        client_info={"role": "operator", "actorId": "operator-1"},
    )

    assert outcome.ok is False
    assert outcome.error_code == -32602
    assert outcome.error_data["detail"] == "params.decision is unsupported"

def test_gateway_dispatcher_approval_resolution_synthesizes_tool_events_when_runtime_omits_them() -> None:
    __testing.reset_control_plane_write_budget_state()
    outcome = dispatch_gateway_method(
        method="approvals.resolve",
        params={"approvalId": "approval_1", "decision": "approve"},
        runtime=_Runtime(),
        client_info={"role": "operator", "actorId": "operator-1"},
    )

    assert outcome.ok is True
    assert outcome.result["approvalTicket"]["approval_id"] == "approval_1"
    assert outcome.result["toolEvents"][0]["name"] == "approval_decision"
    assert outcome.result["toolEvents"][0]["payload"]["approval_id"] == "approval_1"

def test_gateway_dispatcher_approval_resolution_surfaces_continuation_fields() -> None:
    class _ContinuationRuntime(_Runtime):
        @staticmethod
        def decide_approval(
            approval_id: str,
            *,
            approved: bool | None = None,
            decision: str | None = None,
            decided_by: str,
            decision_note: str = "",
        ) -> dict[str, object]:
            del approved, decision, decided_by, decision_note
            continuation = {
                "continuation_attempted": True,
                "continuation_status": "completed",
                "approval_id": approval_id,
                "action_id": "action_1",
                "provider_session_kind": "codex_openai",
                "provider_call_id": "call_shell_1",
                "function_call_name": "exec_command",
                "provider_tool_type": "local_shell_call",
                "tool_output_items": [{"type": "local_shell_call_output"}],
            }
            return {
                "approval_ticket": _Item(
                    {
                        "approval_id": approval_id,
                        "status": "approved",
                        "decision_type": "accept",
                    }
                ),
                "action_request": _Item({"action_id": "action_1"}),
                "action_result": _Item({"result_id": "result_1"}),
                "audit_records": [],
                "tool_events": [
                    ToolEvent(
                        name="approval_decision",
                        ok=True,
                        summary=f"approved {approval_id}",
                        payload={
                            "approval_id": approval_id,
                            "status": "approved",
                            "continuation": dict(continuation),
                        },
                    )
                ],
                "continuation": continuation,
    }

    __testing.reset_control_plane_write_budget_state()
    with patch(
        "cli.agent_cli.gateway_server.dispatcher_direct_handlers_methods.approval_continuation_runtime.persist_continuation_result",
        return_value=True,
    ):
        outcome = dispatch_gateway_method(
            method="approvals.resolve",
            params={"approvalId": "approval_1", "decision": "approve"},
            runtime=_ContinuationRuntime(),
            client_info={"role": "operator", "actorId": "operator-1"},
        )

    assert outcome.ok is True
    assert outcome.result["continuationAttempted"] is True
    assert outcome.result["continuationStatus"] == "completed"
    assert outcome.result["continuation"]["providerCallId"] == "call_shell_1"
    assert outcome.result["toolEvents"][0]["payload"]["continuation"]["provider_call_id"] == "call_shell_1"

def test_gateway_dispatcher_approval_resolution_resumes_pending_continuation() -> None:
    class _PendingContinuationRuntime(_Runtime):
        @staticmethod
        def decide_approval(
            approval_id: str,
            *,
            approved: bool | None = None,
            decision: str | None = None,
            decided_by: str,
            decision_note: str = "",
        ) -> dict[str, object]:
            del approved, decision, decided_by, decision_note
            continuation = {
                "continuation_attempted": False,
                "continuation_status": "tool_result_built",
                "approval_id": approval_id,
                "action_id": "action_1",
                "provider_session_kind": "codex_openai",
                "provider_call_id": "call_shell_1",
                "function_call_name": "exec_command",
                "provider_tool_type": "local_shell_call",
                "tool_output_items": [{"type": "local_shell_call_output"}],
            }
            return {
                "approval_ticket": _Item(
                    {
                        "approval_id": approval_id,
                        "status": "approved",
                        "decision_type": "accept",
                    }
                ),
                "action_request": _Item({"action_id": "action_1"}),
                "action_result": _Item({"result_id": "result_1"}),
                "audit_records": [],
                "tool_events": [
                    ToolEvent(
                        name="approval_decision",
                        ok=True,
                        summary=f"approved {approval_id}",
                        payload={
                            "approval_id": approval_id,
                            "status": "approved",
                            "continuation": dict(continuation),
                        },
                    )
                ],
                "continuation": continuation,
            }

    def _resume(_runtime, *, continuation_result):
        continuation_result["continuation_attempted"] = True
        continuation_result["continuation_status"] = "completed"
        continuation_result["assistant_text"] = "continued by rpc"
        return AgentIntent(assistant_text="continued by rpc")

    __testing.reset_control_plane_write_budget_state()
    with patch(
        "cli.agent_cli.gateway_server.dispatcher_direct_handlers_methods.approval_continuation_runtime.resume_after_approval",
        side_effect=_resume,
    ) as resume_mock, patch(
        "cli.agent_cli.gateway_server.dispatcher_direct_handlers_methods.approval_continuation_runtime.persist_continuation_result",
        return_value=True,
    ) as persist_mock:
        outcome = dispatch_gateway_method(
            method="approvals.resolve",
            params={"approvalId": "approval_1", "decision": "approve"},
            runtime=_PendingContinuationRuntime(),
            client_info={"role": "operator", "actorId": "operator-1"},
        )

    assert outcome.ok is True
    resume_mock.assert_called_once()
    persist_mock.assert_called_once()
    assert outcome.result["continuationAttempted"] is True
    assert outcome.result["continuationStatus"] == "completed"
    assert outcome.result["continuation"]["providerCallId"] == "call_shell_1"
    assert outcome.result["toolEvents"][0]["payload"]["continuation"]["continuation_status"] == "completed"
    assert outcome.transport_context["approval_decision_result"]["continuation"]["assistant_text"] == "continued by rpc"

def test_gateway_ws_capabilities_expose_dispatcher_methods() -> None:
    payload = gateway_ws_capabilities()

    assert payload["protocolVersions"] == ["v1"]
    assert "connect.initialize" in payload["methods"]
    assert "gateway.state.get" in payload["methods"]

def test_gateway_dispatcher_rejects_unauthenticated_protected_method() -> None:
    outcome = dispatch_gateway_method(
        method="gateway.state.get",
        params={"limit": 5},
        runtime=_Runtime(),
        client_info={"authenticated": False, "role": "operator", "actorId": "operator-1"},
    )

    assert outcome.ok is False
    assert outcome.error_code == -32041
    assert outcome.error_data["gatewayCode"] == "UNAUTHORIZED"

def test_gateway_dispatcher_applies_control_plane_write_budget_to_write_methods() -> None:
    __testing.reset_control_plane_write_budget_state()
    kwargs = {
        "method": "github.issues.create",
        "params": {"repo": "hoteye/simulate-app", "title": "Need review"},
        "runtime": _Runtime(),
        "client_info": {"role": "operator", "actorId": "operator-1", "clientIp": "203.0.113.7"},
    }

    with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test"}, clear=False):
        first = dispatch_gateway_method(**kwargs)
        second = dispatch_gateway_method(**kwargs)
        third = dispatch_gateway_method(**kwargs)
        blocked = dispatch_gateway_method(**kwargs)

    assert [item.ok for item in (first, second, third)] == [True, True, True]
    assert blocked.ok is False
    assert blocked.error_code == -32029
    assert blocked.error_data["gatewayCode"] == "UNAVAILABLE"
    assert blocked.error_data["retryable"] is True

def test_gateway_dispatcher_routes_github_webhook_ingest_through_family_handler() -> None:
    outcome = dispatch_gateway_method(
        method="github.webhook.ingest",
        params={
            "headers": {"X-GitHub-Event": "issues", "X-GitHub-Delivery": "delivery-1"},
            "rawBody": '{"action":"opened","repository":{"full_name":"acme/platform"},"issue":{"number":1}}',
        },
        runtime=_Runtime(),
        client_info={"role": "webhook", "actorId": "github-webhook", "scopes": ["github.read"]},
    )

    assert outcome.ok is True
    assert outcome.result["method"] == "github.webhook.ingest"
    assert outcome.result["status"] == "accepted"
    assert outcome.result["decision"]["pluginName"] == "github_phase1"

def test_gateway_dispatcher_rejects_webhook_signature_verification_without_raw_body() -> None:
    outcome = dispatch_gateway_method(
        method="gateway/webhook",
        params={
            "connectorKey": "demo_webhook",
            "eventType": "demo.event",
            "payload": {"ticket": "T-1"},
            "verifySignature": {"secret": "super-secret"},
        },
        runtime=_Runtime(),
        client_info={"role": "operator", "actorId": "operator-1"},
    )

    assert outcome.ok is False
    assert outcome.error_code == -32602
    assert outcome.error_data["detail"] == "params.rawBody is required when verifySignature is provided"

def test_gateway_dispatcher_rejects_browser_proxy_without_path() -> None:
    outcome = dispatch_gateway_method(
        method="browser.proxy",
        params={"method": "GET"},
        runtime=_Runtime(),
        client_info={"role": "operator", "actorId": "operator-1"},
    )

    assert outcome.ok is False
    assert outcome.error_code == -32602
    assert outcome.error_data["detail"] == "params.path must be a non-empty string"

def test_gateway_dispatcher_surfaces_browser_proxy_backend_failure() -> None:
    with patch("cli.agent_cli.gateway_server.dispatcher.run_browser_proxy_command", side_effect=RuntimeError("proxy down")):
        outcome = dispatch_gateway_method(
            method="browser.proxy",
            params={"path": "/profiles", "method": "GET"},
            runtime=_Runtime(),
            client_info={"role": "operator", "actorId": "operator-1"},
        )

    assert outcome.ok is False
    assert outcome.error_code == -32032
    assert outcome.error_data["detail"] == "proxy down"
