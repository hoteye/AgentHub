from __future__ import annotations

from cli.agent_cli.gateway_core import GatewayRegistry, TriggerRegistration, create_gateway_event, route_event

def test_route_event_selects_highest_priority_matching_trigger() -> None:
    registry = GatewayRegistry()
    registry.register_trigger(
        TriggerRegistration(
            trigger_key="default_trigger",
            plugin_name="demo_plugin",
            trigger_kind="event",
            connector_key=None,
            event_types=["demo.event"],
            workflow_name="default_workflow",
            priority=100,
        )
    )
    registry.register_trigger(
        TriggerRegistration(
            trigger_key="preferred_trigger",
            plugin_name="psbc_policy",
            trigger_kind="event",
            connector_key="psbc_webhook",
            event_types=["demo.event"],
            workflow_name="preferred_workflow",
            priority=5,
        )
    )

    event = create_gateway_event(
        event_type="demo.event",
        source_kind="webhook",
        source_id="webhook:psbc",
        connector_key="psbc_webhook",
    )

    decision = route_event(registry, event)

    assert decision.target_kind == "plugin_workflow"
    assert decision.plugin_name == "psbc_policy"
    assert decision.workflow_name == "preferred_workflow"
    assert decision.reason == "trigger_match"

def test_route_event_returns_unrouted_when_no_trigger_matches() -> None:
    registry = GatewayRegistry()
    event = create_gateway_event(event_type="demo.event", source_kind="manual", source_id="cli")

    decision = route_event(registry, event)

    assert decision.target_kind == "unrouted"
    assert decision.workflow_name is None
    assert decision.reason == "no_trigger_match"

def test_route_event_uses_trigger_filters_before_fallback_trigger() -> None:
    registry = GatewayRegistry()
    registry.register_trigger(
        TriggerRegistration(
            trigger_key="generic_issue",
            plugin_name="github_phase1",
            trigger_kind="event",
            connector_key="github_webhook",
            event_types=["github.issues.opened"],
            workflow_name="handle_github_issue_opened",
            priority=20,
        )
    )
    registry.register_trigger(
        TriggerRegistration(
            trigger_key="policy_issue",
            plugin_name="github_phase1",
            trigger_kind="event",
            connector_key="github_webhook",
            event_types=["github.issues.opened"],
            workflow_name="handle_github_compliance_issue_opened",
            priority=10,
            filters={
                "payload_contains_any": {
                    "paths": ["issue.title", "issue.body"],
                    "terms": ["compliance", "audit"],
                }
            },
        )
    )

    decision = route_event(
        registry,
        create_gateway_event(
            event_type="github.issues.opened",
            source_kind="webhook",
            source_id="github:acme/platform",
            connector_key="github_webhook",
            payload={"issue": {"title": "Compliance remediation", "body": "Need audit follow-up"}},
        ),
    )
    fallback_decision = route_event(
        registry,
        create_gateway_event(
            event_type="github.issues.opened",
            source_kind="webhook",
            source_id="github:acme/platform",
            connector_key="github_webhook",
            payload={"issue": {"title": "Refactor logs", "body": "no policy impact"}},
        ),
    )

    assert decision.workflow_name == "handle_github_compliance_issue_opened"
    assert fallback_decision.workflow_name == "handle_github_issue_opened"
