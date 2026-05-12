from __future__ import annotations

from . import build_family


CONNECT_FAMILY = build_family(
    family_name="connect",
    method_summaries={
        "connect.initialize": "Initialize a gateway session and return protocol bootstrap details.",
        "connect.capabilities": "Return gateway method and capability metadata for the connected client.",
        "connect.ping": "Round-trip ping for gateway transports and control-plane health checks.",
    },
)

connect_handlers = CONNECT_FAMILY.handlers
