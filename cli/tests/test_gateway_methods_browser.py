from __future__ import annotations

from cli.agent_cli.gateway_server.methods.browser import BROWSER_FAMILY, browser_handlers

def test_browser_family_freezes_openclaw_aligned_method_names() -> None:
    assert BROWSER_FAMILY.methods == (
        "browser.proxy",
        "browser.workflow.run",
        "browser.playbook.run",
    )
    assert set(browser_handlers) == set(BROWSER_FAMILY.methods)

def test_browser_stub_handler_preserves_method_and_payload_shape() -> None:
    result = browser_handlers["browser.proxy"](params={"path": "/profiles", "method": "GET"})

    assert result["family"] == "browser"
    assert result["method"] == "browser.proxy"
    assert result["params"] == {"path": "/profiles", "method": "GET"}
