from __future__ import annotations

from . import build_family


WORKFLOWS_FAMILY = build_family(
    family_name="workflows",
    method_summaries={
        "workflows.list": "List gateway workflow runs visible to operators.",
        "workflows.get": "Return one workflow run with operator diagnostics context.",
        "workflows.resume": "Resume a paused gateway workflow execution.",
    },
)

workflows_handlers = WORKFLOWS_FAMILY.handlers
