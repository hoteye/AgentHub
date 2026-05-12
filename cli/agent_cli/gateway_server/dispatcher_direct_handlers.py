from __future__ import annotations
from typing import Any, Callable

from cli.agent_cli.gateway_server.method_registry import GatewayServerMethodRegistry

from cli.agent_cli.gateway_server.dispatcher_direct_handlers_common import (
    GatewayDispatchResult,
    _failure,
    _success,
    build_direct_method_handlers,
)
from cli.agent_cli.gateway_server.dispatcher_direct_handlers_methods import (
    _DIRECT_HANDLERS,
    _LEGACY_METHOD_ALIASES,
    _LEGACY_ONLY_METHODS,
    _handle_gateway_state_get,
    build_workflow_trace_approval_handlers,
    configure_gateway_method_registry,
)
from cli.agent_cli.gateway_server.methods import merge_handler_maps
from cli.agent_cli.gateway_server.methods.access import ACCESS_FAMILY
from cli.agent_cli.gateway_server.methods.approvals import APPROVALS_FAMILY
from cli.agent_cli.gateway_server.methods.browser import BROWSER_FAMILY
from cli.agent_cli.gateway_server.methods.config import CONFIG_FAMILY
from cli.agent_cli.gateway_server.methods.connect import CONNECT_FAMILY
from cli.agent_cli.gateway_server.methods.gateway_state import GATEWAY_STATE_FAMILY
from cli.agent_cli.gateway_server.methods.health import HEALTH_FAMILY
from cli.agent_cli.gateway_server.methods.logs import LOGS_FAMILY
from cli.agent_cli.gateway_server.methods.nodes import NODES_FAMILY
from cli.agent_cli.gateway_server.methods.plugins import PLUGINS_FAMILY
from cli.agent_cli.gateway_server.methods.workflows import WORKFLOWS_FAMILY

gateway_method_families = (
    CONNECT_FAMILY,
    CONFIG_FAMILY,
    ACCESS_FAMILY,
    NODES_FAMILY,
    HEALTH_FAMILY,
    GATEWAY_STATE_FAMILY,
    APPROVALS_FAMILY,
    BROWSER_FAMILY,
    PLUGINS_FAMILY,
    WORKFLOWS_FAMILY,
    LOGS_FAMILY,
)
gateway_method_handlers = merge_handler_maps(gateway_method_families)
gateway_method_registry = GatewayServerMethodRegistry(handlers=gateway_method_handlers)
configure_gateway_method_registry(gateway_method_registry)
_WORKFLOW_TRACE_APPROVAL_HANDLERS = build_workflow_trace_approval_handlers()
_DIRECT_METHOD_HANDLERS = build_direct_method_handlers(
    _WORKFLOW_TRACE_APPROVAL_HANDLERS,
    _DIRECT_HANDLERS,
)


__all__ = [
    "GatewayDispatchResult",
    "_DIRECT_METHOD_HANDLERS",
    "_handle_gateway_state_get",
    "_success",
    "_failure",
    "gateway_method_registry",
    "_LEGACY_METHOD_ALIASES",
    "_LEGACY_ONLY_METHODS",
]
