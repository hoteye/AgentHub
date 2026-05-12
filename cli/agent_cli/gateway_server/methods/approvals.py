from __future__ import annotations

from . import build_family


APPROVALS_FAMILY = build_family(
    family_name="approvals",
    method_summaries={
        "approvals.list": "List pending or historical approval tickets.",
        "approvals.get": "Return one approval ticket together with causality context.",
        "approvals.resolve": "Approve or reject a pending gateway approval ticket.",
    },
)

approvals_handlers = APPROVALS_FAMILY.handlers
