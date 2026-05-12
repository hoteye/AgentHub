from __future__ import annotations

from . import build_family


BROWSER_FAMILY = build_family(
    family_name="browser",
    method_summaries={
        "browser.proxy": "Route a structured browser control request through the gateway-owned browser surface.",
        "browser.workflow.run": "Start a gateway-owned browser workflow execution.",
        "browser.playbook.run": "Start a named browser playbook under gateway supervision.",
    },
)

browser_handlers = BROWSER_FAMILY.handlers
