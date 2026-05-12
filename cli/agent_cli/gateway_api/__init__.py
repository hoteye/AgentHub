from .approvals_api import approval_ticket_to_response
from .auth import GatewayAuthContext
from .webhook_api import (
    build_webhook_event,
    find_header_value,
    parse_webhook_body,
    sanitize_webhook_headers,
    verify_webhook_signature,
)


def dispatch_gui_bridge_action(*args, **kwargs):
    from .gui_bridge_api import dispatch_gui_bridge_action as _dispatch_gui_bridge_action

    return _dispatch_gui_bridge_action(*args, **kwargs)


def run_gui_bridge_server(*args, **kwargs):
    from .gui_http_server import run_gui_bridge_server as _run_gui_bridge_server

    return _run_gui_bridge_server(*args, **kwargs)


def run_github_webhook_server(*args, **kwargs):
    from .github_http_server import run_github_webhook_server as _run_github_webhook_server

    return _run_github_webhook_server(*args, **kwargs)


def process_github_webhook(*args, **kwargs):
    from .github_http_server import process_github_webhook as _process_github_webhook

    return _process_github_webhook(*args, **kwargs)


def gateway_ws_capabilities():
    from .gateway_ws import gateway_ws_capabilities as _gateway_ws_capabilities

    return _gateway_ws_capabilities()


def GuiBridgeEventBus(*args, **kwargs):
    from .gui_http_server import GuiBridgeEventBus as _GuiBridgeEventBus

    return _GuiBridgeEventBus(*args, **kwargs)


__all__ = [
    "GatewayAuthContext",
    "GuiBridgeEventBus",
    "approval_ticket_to_response",
    "build_webhook_event",
    "dispatch_gui_bridge_action",
    "find_header_value",
    "gateway_ws_capabilities",
    "parse_webhook_body",
    "process_github_webhook",
    "run_github_webhook_server",
    "run_gui_bridge_server",
    "sanitize_webhook_headers",
    "verify_webhook_signature",
]
