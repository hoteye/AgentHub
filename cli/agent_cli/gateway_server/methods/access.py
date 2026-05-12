from __future__ import annotations

from . import build_family


ACCESS_FAMILY = build_family(
    family_name="access",
    method_summaries={
        "access.posture.get": "Return control UI access/auth posture and pairing pending summary.",
    },
)

access_handlers = ACCESS_FAMILY.handlers

