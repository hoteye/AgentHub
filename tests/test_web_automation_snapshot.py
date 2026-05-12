from __future__ import annotations

from shared.web_automation.snapshot import build_snapshot, ensure_tab_snapshot_seed
from shared.web_automation.types import BrowserPageRef, BrowserTab


def test_build_snapshot_truncates_text_and_limits_refs() -> None:
    tab = BrowserTab(
        tab_id="tab-1",
        url="https://example.com/app",
        title="Example App",
        profile="openclaw",
        text="A" * 260,
        refs=[
            BrowserPageRef(ref="e1", role="button", name="Save"),
            BrowserPageRef(ref="e2", role="textbox", name="Username"),
            BrowserPageRef(ref="e3", role="link", name="Docs"),
        ],
    )

    snapshot = build_snapshot(tab, max_chars=220, max_refs=1)

    assert snapshot.truncated
    assert snapshot.target_id == "tab-1"
    assert len(snapshot.refs) == 1
    assert snapshot.refs[0].ref == "e1"
    assert snapshot.text.endswith("...[truncated]")


def test_ensure_tab_snapshot_seed_populates_defaults() -> None:
    tab = BrowserTab(
        tab_id="tab-2",
        url="https://example.com/docs/start",
        title="",
        profile="openclaw",
        text="",
        refs=[],
    )

    ensure_tab_snapshot_seed(tab)

    assert tab.title == "example.com/docs/start"
    assert "Synthetic browser snapshot" in tab.text
    assert len(tab.refs) == 1
    assert tab.refs[0].ref == "r1"
    assert tab.refs[0].url == "https://example.com/docs/start"
