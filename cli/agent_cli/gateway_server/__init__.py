from __future__ import annotations

from cli.agent_cli.gateway_server.methods import GatewayMethodFamily, merge_handler_maps
from cli.agent_cli.gateway_server.methods.access import ACCESS_FAMILY, access_handlers
from cli.agent_cli.gateway_server.methods.approvals import APPROVALS_FAMILY, approvals_handlers
from cli.agent_cli.gateway_server.methods.browser import BROWSER_FAMILY, browser_handlers
from cli.agent_cli.gateway_server.methods.config import CONFIG_FAMILY, config_handlers
from cli.agent_cli.gateway_server.methods.connect import CONNECT_FAMILY, connect_handlers
from cli.agent_cli.gateway_server.methods.gateway_state import GATEWAY_STATE_FAMILY, gateway_state_handlers
from cli.agent_cli.gateway_server.methods.github import GITHUB_FAMILY, github_handlers
from cli.agent_cli.gateway_server.methods.health import HEALTH_FAMILY, health_handlers
from cli.agent_cli.gateway_server.methods.logs import LOGS_FAMILY, logs_handlers
from cli.agent_cli.gateway_server.methods.nodes import NODES_FAMILY, nodes_handlers
from cli.agent_cli.gateway_server.event_broadcast import (
    GatewayBroadcastFrame,
    GatewayBroadcastSubscription,
    GatewayEventBroadcaster,
)
from cli.agent_cli.gateway_server.method_registry import GatewayMethodRegistration, GatewayServerMethodRegistry
from cli.agent_cli.gateway_server.methods.plugins import PLUGINS_FAMILY, plugins_handlers
from cli.agent_cli.gateway_server.request_scope import (
    GatewayRequestScope,
    gateway_request_scope,
    get_gateway_request_scope,
    with_gateway_plugin_scope,
    with_gateway_request_scope,
)
from cli.agent_cli.gateway_server.methods.workflows import WORKFLOWS_FAMILY, workflows_handlers


CONTROL_UI_BOOTSTRAP_CONFIG_PATH = "/__agenthub/control-ui-config.json"


def build_control_ui_bootstrap(*args, **kwargs):
    from cli.agent_cli.gateway_server.control_ui_contract import build_control_ui_bootstrap as _impl

    return _impl(*args, **kwargs)


def build_control_ui_state_snapshot(*args, **kwargs):
    from cli.agent_cli.gateway_server.control_ui_contract import build_control_ui_state_snapshot as _impl

    return _impl(*args, **kwargs)


gateway_method_families: tuple[GatewayMethodFamily, ...] = (
    CONNECT_FAMILY,
    CONFIG_FAMILY,
    ACCESS_FAMILY,
    NODES_FAMILY,
    HEALTH_FAMILY,
    GATEWAY_STATE_FAMILY,
    APPROVALS_FAMILY,
    BROWSER_FAMILY,
    GITHUB_FAMILY,
    PLUGINS_FAMILY,
    WORKFLOWS_FAMILY,
    LOGS_FAMILY,
)

gateway_method_handlers = merge_handler_maps(gateway_method_families)


__all__ = [
    "ACCESS_FAMILY",
    "APPROVALS_FAMILY",
    "BROWSER_FAMILY",
    "CONNECT_FAMILY",
    "CONFIG_FAMILY",
    "CONTROL_UI_BOOTSTRAP_CONFIG_PATH",
    "GATEWAY_STATE_FAMILY",
    "GITHUB_FAMILY",
    "GatewayBroadcastFrame",
    "GatewayBroadcastSubscription",
    "GatewayEventBroadcaster",
    "HEALTH_FAMILY",
    "GatewayMethodRegistration",
    "GatewayRequestScope",
    "GatewayServerMethodRegistry",
    "LOGS_FAMILY",
    "NODES_FAMILY",
    "PLUGINS_FAMILY",
    "WORKFLOWS_FAMILY",
    "approvals_handlers",
    "browser_handlers",
    "build_control_ui_bootstrap",
    "build_control_ui_state_snapshot",
    "connect_handlers",
    "config_handlers",
    "gateway_request_scope",
    "gateway_method_families",
    "gateway_method_handlers",
    "gateway_state_handlers",
    "get_gateway_request_scope",
    "github_handlers",
    "health_handlers",
    "logs_handlers",
    "nodes_handlers",
    "plugins_handlers",
    "with_gateway_plugin_scope",
    "with_gateway_request_scope",
    "workflows_handlers",
    "access_handlers",
]
