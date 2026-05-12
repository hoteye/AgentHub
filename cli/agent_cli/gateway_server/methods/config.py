from __future__ import annotations

from . import build_family


CONFIG_FAMILY = build_family(
    family_name="config",
    method_summaries={
        "config.validate": "Validate a control-plane config draft and return machine-readable apply/restart posture.",
        "config.apply": "Apply a validated control-plane config subset and return post-apply state plus restart posture.",
        "config.restart.report": "Report restart impact for a control-plane config draft without performing a restart.",
    },
)

config_handlers = CONFIG_FAMILY.handlers
