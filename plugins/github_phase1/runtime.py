from __future__ import annotations

from cli.agent_cli.host.plugin_hooks import RuntimeHooks
from plugins.github_phase1.connectors import build_connectors
from plugins.github_phase1.policies import build_policies
from plugins.github_phase1.triggers import build_triggers
from plugins.github_phase1.workflow_handlers import build_workflow_handlers


def runtime_hooks() -> RuntimeHooks:
    return RuntimeHooks(
        build_connector_registrations=build_connectors,
        build_trigger_registrations=build_triggers,
        build_policy_registrations=build_policies,
        build_workflow_handlers=build_workflow_handlers,
    )
