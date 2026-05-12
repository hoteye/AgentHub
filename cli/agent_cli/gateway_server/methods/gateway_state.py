from __future__ import annotations

from . import build_family


GATEWAY_STATE_FAMILY = build_family(
    family_name="gateway_state",
    method_summaries={
        "gateway.state.get": "Return the current gateway state snapshot for operators.",
        "gateway.events.list": "List persisted gateway ingress events.",
        "gateway.workflows.list": "List persisted workflow runs from the gateway state store.",
        "gateway.trace.timeline": "Return a trace-oriented timeline across workflow, approval, and audit records.",
    },
)

gateway_state_handlers = GATEWAY_STATE_FAMILY.handlers
