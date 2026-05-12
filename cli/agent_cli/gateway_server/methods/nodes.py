from __future__ import annotations

from . import build_family


NODES_FAMILY = build_family(
    family_name="nodes",
    method_summaries={
        "nodes.list": "List read-only nodes/devices inventory derived from access posture and gateway state.",
    },
)

nodes_handlers = NODES_FAMILY.handlers
