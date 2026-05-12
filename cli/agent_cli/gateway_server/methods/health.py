from __future__ import annotations

from . import build_family


HEALTH_FAMILY = build_family(
    family_name="health",
    method_summaries={
        "health.get": "Return gateway liveness and readiness summary.",
        "health.probes": "Return detailed health probes for runtime, plugins, and browser control.",
    },
)

health_handlers = HEALTH_FAMILY.handlers
