from __future__ import annotations

from . import build_family


LOGS_FAMILY = build_family(
    family_name="logs",
    method_summaries={
        "logs.tail": "Read a bounded tail slice from gateway-visible logs.",
    },
)

logs_handlers = LOGS_FAMILY.handlers
