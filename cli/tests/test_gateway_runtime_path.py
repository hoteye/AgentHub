from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from cli.agent_cli.gateway_core import JsonlGatewayStateStore, TriggerRegistration, create_gateway_event, create_workflow_run
from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.tools import ToolRegistry
from workers.actions import ActionResult

class _GatewayFakeAgent:
    @staticmethod
    def provider_status() -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "deepseek",
            "provider_model": "test-model",
        }

    @staticmethod
    def plan(text, history=None, *, tool_executor=None, attachments=None):
        raise AssertionError("LLM planner should not be used in gateway runtime path tests")

class _GatewayFakeActionWorker:
    @staticmethod
    def execute(request):
        return ActionResult(
            ok=True,
            action=str(request.get("action") or ""),
            summary="fake action executed",
            output={"artifact_refs": ["demo://artifact/1"]},
        )

def test_runtime_dispatch_gateway_event_routes_through_plugin_manager_registrations() -> None:
    source = ROOT / "plugins" / "demo_plugin"

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_root = Path(tmpdir)
        source_root = temp_root / "source"
        plugins_root = temp_root / "plugins_target"
        state_path = temp_root / "plugin_state.json"
        source_root.mkdir(parents=True, exist_ok=True)
        copied = source_root / "demo_plugin"
        shutil.copytree(source, copied)
        (copied / "runtime.py").write_text(
            "\n".join(
                [
                    "from cli.agent_cli.host.plugin_hooks import RuntimeHooks",
                    "",
                    "def runtime_hooks():",
                    "    return RuntimeHooks(",
                    "        build_connector_registrations=lambda plugin_name='demo_plugin': [",
                    "            {",
                    "                'connector_key': 'demo_webhook',",
                    "                'plugin_name': plugin_name,",
                    "                'display_name': 'Demo Webhook',",
                    "                'version': '1',",
                    "                'connector_kind': 'inbound',",
                    "                'supports_webhook': True,",
                    "                'supports_polling': False,",
                    "                'supports_actions': False,",
                    "                'event_types': ['demo.event'],",
                    "                'action_types': [],",
                    "            }",
                    "        ],",
                    "        build_trigger_registrations=lambda: [",
                    "            {",
                    "                'trigger_key': 'demo_trigger',",
                    "                'plugin_name': 'demo_plugin',",
                    "                'trigger_kind': 'event',",
                    "                'connector_key': 'demo_webhook',",
                    "                'event_types': ['demo.event'],",
                    "                'workflow_name': 'handle_demo_event',",
                    "                'priority': 10,",
                    "            }",
                    "        ],",
                    "    )",
                ]
            ),
            encoding="utf-8",
        )

        manager = PluginManager(plugin_root=plugins_root, state_path=state_path)
        installed = manager.install_plugin(str(copied))
        assert installed["ok"] is True

        tools = ToolRegistry()
        tools._plugin_manager = manager
        runtime = AgentCliRuntime(tools=tools, agent=_GatewayFakeAgent())
        event = create_gateway_event(
            event_type="demo.event",
            source_kind="webhook",
            source_id="demo:webhook",
            connector_key="demo_webhook",
            payload={"ticket": "T-1"},
        )

        result = runtime.dispatch_gateway_event(event)

        decision = result["decision"]
        workflow_run = result["workflow_run"]
        audit_records = result["audit_records"]

        assert decision.target_kind == "plugin_workflow"
        assert decision.plugin_name == "demo_plugin"
        assert decision.workflow_name == "handle_demo_event"
        assert workflow_run is not None
        assert workflow_run.plugin_name == "demo_plugin"
        assert workflow_run.event_id == event.event_id
        assert [item.stage for item in audit_records] == ["ingress", "route"]
        assert audit_records[1].workflow_run_id == workflow_run.workflow_run_id

def test_runtime_dispatch_gateway_event_executes_registered_workflow_handler() -> None:
    source = ROOT / "plugins" / "demo_plugin"

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_root = Path(tmpdir)
        source_root = temp_root / "source"
        plugins_root = temp_root / "plugins_target"
        state_path = temp_root / "plugin_state.json"
        source_root.mkdir(parents=True, exist_ok=True)
        copied = source_root / "demo_plugin"
        shutil.copytree(source, copied)
        (copied / "runtime.py").write_text(
            "\n".join(
                [
                    "from cli.agent_cli.host.plugin_hooks import RuntimeHooks",
                    "",
                    "def _handle_demo_event(*, event, decision, workflow_run, runtime=None):",
                    "    return {",
                    "        'status': 'ok',",
                    "        'reasoning_summary': f\"handled {event.event_type} for {decision.plugin_name}\",",
                    "        'evidence_refs': ['demo://ticket/T-1'],",
                    "        'action_requests': [],",
                    "    }",
                    "",
                    "def runtime_hooks():",
                    "    return RuntimeHooks(",
                    "        build_connector_registrations=lambda plugin_name='demo_plugin': [",
                    "            {",
                    "                'connector_key': 'demo_webhook',",
                    "                'plugin_name': plugin_name,",
                    "                'display_name': 'Demo Webhook',",
                    "                'version': '1',",
                    "                'connector_kind': 'inbound',",
                    "                'supports_webhook': True,",
                    "                'supports_polling': False,",
                    "                'supports_actions': False,",
                    "                'event_types': ['demo.event'],",
                    "                'action_types': [],",
                    "            }",
                    "        ],",
                    "        build_trigger_registrations=lambda: [",
                    "            {",
                    "                'trigger_key': 'demo_trigger',",
                    "                'plugin_name': 'demo_plugin',",
                    "                'trigger_kind': 'event',",
                    "                'connector_key': 'demo_webhook',",
                    "                'event_types': ['demo.event'],",
                    "                'workflow_name': 'handle_demo_event',",
                    "                'priority': 10,",
                    "            }",
                    "        ],",
                    "        build_workflow_handlers=lambda plugin_name='demo_plugin': [",
                    "            {",
                    "                'workflow_name': 'handle_demo_event',",
                    "                'plugin_name': plugin_name,",
                    "                'handler': _handle_demo_event,",
                    "            }",
                    "        ],",
                    "    )",
                ]
            ),
            encoding="utf-8",
        )

        manager = PluginManager(plugin_root=plugins_root, state_path=state_path)
        installed = manager.install_plugin(str(copied))
        assert installed["ok"] is True

        tools = ToolRegistry()
        tools._plugin_manager = manager
        runtime = AgentCliRuntime(tools=tools, agent=_GatewayFakeAgent())
        event = create_gateway_event(
            event_type="demo.event",
            source_kind="webhook",
            source_id="demo:webhook",
            connector_key="demo_webhook",
            payload={"ticket": "T-1"},
        )

        result = runtime.dispatch_gateway_event(event)

        workflow_run = result["workflow_run"]
        workflow_result = result["workflow_result"]
        audit_records = result["audit_records"]

        assert workflow_run is not None
        assert workflow_result is not None
        assert workflow_result["reasoning_summary"] == "handled demo.event for demo_plugin"
        assert workflow_run.status == "ok"
        assert workflow_run.current_step == "workflow_executed"
        assert workflow_run.result_summary == "handled demo.event for demo_plugin"
        assert workflow_run.context["workflow_result"]["action_request_count"] == 0
        assert [item.stage for item in audit_records] == ["ingress", "route", "workflow"]
        assert audit_records[2].details["evidence_refs"] == ["demo://ticket/T-1"]

def test_runtime_dispatch_gateway_event_keeps_unrouted_status_when_no_trigger_matches() -> None:
    runtime = AgentCliRuntime(agent=_GatewayFakeAgent())
    event = create_gateway_event(
        event_type="demo.event",
        source_kind="manual",
        source_id="cli",
    )

    result = runtime.dispatch_gateway_event(event)

    assert result["decision"].target_kind == "unrouted"
    assert result["workflow_run"] is None
    assert result["audit_records"][1].status == "unrouted"

def test_runtime_dispatch_gateway_event_persists_gateway_state_in_jsonl_store() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        store = JsonlGatewayStateStore(Path(tmpdir) / "gateway")
        runtime = AgentCliRuntime(agent=_GatewayFakeAgent(), gateway_state_store=store)
        event = create_gateway_event(
            event_type="demo.event",
            source_kind="manual",
            source_id="cli",
            payload={"hello": "world"},
        )

        result = runtime.dispatch_gateway_event(event)
        reloaded = JsonlGatewayStateStore(Path(tmpdir) / "gateway")

        assert result["event"].event_id == event.event_id
        assert reloaded.list_events(limit=5)[0].event_id == event.event_id
        assert len(reloaded.list_audit_records(limit=10, trace_id=event.trace_id)) == 2

def test_gateway_state_snapshot_exposes_diagnostics_by_reasoning_recommendation_approval_and_execution() -> None:
    runtime = AgentCliRuntime(agent=_GatewayFakeAgent(), action_worker=_GatewayFakeActionWorker())
    event = create_gateway_event(
        event_type="demo.event",
        source_kind="manual",
        source_id="cli",
        payload={"ticket": "T-9"},
    )
    trigger = TriggerRegistration(
        trigger_key="demo_trigger",
        plugin_name="demo_plugin",
        trigger_kind="event",
        connector_key="demo_webhook",
        event_types=["demo.event"],
        workflow_name="handle_demo_event",
    )
    workflow_run = create_workflow_run(
        trigger=trigger,
        event=event,
        status="approval_requested",
        current_step="workflow_executed",
        context={
            "workflow_result": {
                "status": "approval_requested",
                "reasoning_summary": "demo workflow recommended one follow-up action",
                "evidence_refs": ["demo://ticket/T-9"],
                "action_request_count": 1,
            }
        },
    )
    runtime.gateway_state_store.save_event(event)
    runtime.gateway_state_store.save_workflow_run(workflow_run)
    requested = runtime.request_gateway_action(
        action_type="demo.noop",
        connector_key="demo_webhook",
        plugin_name="demo_plugin",
        request_payload={"action": "noop", "parameters": {"ticket": "T-9"}},
        requested_by="workflow.demo",
        trace_id=event.trace_id,
        event_id=event.event_id,
        workflow_run_id=workflow_run.workflow_run_id,
        approval_required=True,
        approval_summary="Approve demo noop",
        approval_reason="phase2 diagnostics test",
        metadata={
            "workflow_name": workflow_run.workflow_name,
            "reasoning_summary": "demo workflow recommended one follow-up action",
            "evidence_refs": ["demo://ticket/T-9"],
        },
    )
    runtime.decide_gateway_approval(
        requested["approval_ticket"].approval_id,
        approved=True,
        decided_by="tester",
    )

    snapshot = runtime.gateway_state_snapshot(limit=10)
    workflow_diagnostic = snapshot["diagnostics"]["workflow_diagnostics"][0]
    approval_diagnostic = snapshot["diagnostics"]["approval_diagnostics"][0]

    assert workflow_diagnostic["reasoning"]["summary"] == "demo workflow recommended one follow-up action"
    assert workflow_diagnostic["recommendation"]["count"] == 1
    assert workflow_diagnostic["recommendation"]["items"][0]["action_type"] == "demo.noop"
    assert workflow_diagnostic["approval"]["status"] == "approved"
    assert workflow_diagnostic["execution"]["status"] == "ok"
    assert approval_diagnostic["reasoning"]["summary"] == "demo workflow recommended one follow-up action"
    assert approval_diagnostic["recommendation"]["action_type"] == "demo.noop"
    assert approval_diagnostic["approval"]["status"] == "approved"
    assert approval_diagnostic["execution"]["status"] == "ok"
