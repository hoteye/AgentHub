from __future__ import annotations

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime_core.event_rendering import activity_events_for_tool_event
from cli.agent_cli.ui.approval_modal import (
    ApprovalOverlay,
    approval_option_specs,
    approval_overlay_text,
    format_additional_permissions_rule,
)


def test_format_additional_permissions_rule_matches_codex_style() -> None:
    assert (
        format_additional_permissions_rule(
            {
                "network": {"enabled": True},
                "file_system": {
                    "read": ["/tmp/readme.txt"],
                    "write": ["/tmp/out.txt"],
                },
            }
        )
        == "network; read `/tmp/readme.txt`; write `/tmp/out.txt`"
    )


def test_shell_option_specs_match_codex_shortcuts_and_labels() -> None:
    payload = {
        "approval_id": "appr_shell",
        "action_type": "shell_command",
        "additional_permissions": {
            "network": {"enabled": True},
            "file_system": {
                "read": ["/tmp/readme.txt"],
                "write": ["/tmp/out.txt"],
            },
        },
        "available_decisions": approval_contract_runtime.shell_available_decisions(
            {"command_tokens": ["cat", "/tmp/readme.txt"]}
        ),
    }

    options = approval_option_specs(payload)

    assert [item.label for item in options] == [
        "Yes, proceed",
        "Yes, and allow these permissions for this session",
        "Yes, and don't ask again for commands that start with `cat /tmp/readme.txt`",
        "No, continue without running it",
        "No, and tell AgentHub what to do differently",
    ]
    assert [item.display_shortcut for item in options] == ["y", "a", "p", "d", "escape"]
    assert options[-1].extra_shortcuts == ("n",)


def test_shell_option_specs_render_prefix_pattern_without_python_list_repr() -> None:
    payload = {
        "approval_id": "appr_shell_rule",
        "action_type": "shell_command",
        "available_decisions": [
            {"type": approval_contract_runtime.APPROVAL_DECISION_ACCEPT},
            {
                "type": approval_contract_runtime.APPROVAL_DECISION_ACCEPT_WITH_EXECPOLICY_AMENDMENT,
                "proposed_rule": {"pattern": ["curl"]},
            },
        ],
    }

    options = approval_option_specs(payload)

    assert [item.label for item in options] == [
        "Yes, proceed",
        "Yes, and don't ask again for commands that start with `curl`",
    ]


def test_browser_host_overlay_matches_codex_style_labels() -> None:
    payload = {
        "approval_id": "appr_browser",
        "action_type": "browser.navigate",
        "summary": "Approve browser navigation",
        "reason": "Browser state-mutating actions require approval.",
        "browser_host": "example.com",
        "browser_url": "https://example.com/settings",
        "browser_command": "navigate",
        "browser_action_class": "state_mutating",
        "approval_policy": "always",
        "audit_stage": "browser_state_change",
        "available_decisions": approval_contract_runtime.browser_available_decisions(
            allow_for_session=True
        ),
    }

    options = approval_option_specs(payload)
    rendered = approval_overlay_text(payload).plain

    assert [item.label for item in options] == [
        "Yes, just this once",
        "Yes, and allow this host for this conversation",
        "No, continue without this browser action",
        "No, and tell AgentHub what to do differently",
    ]
    assert 'Do you want to approve browser access to "example.com"?' in rendered
    assert "Host: example.com" in rendered
    assert "URL: https://example.com/settings" in rendered
    assert "Risk class: state mutating" in rendered


def test_patch_overlay_text_includes_codex_like_prompt_and_options() -> None:
    payload = {
        "approval_id": "appr_patch",
        "action_type": "apply_patch",
        "summary": "Approve workspace patch",
        "reason": "need to update config",
        "file_count": 2,
        "changes": [
            {"change_type": "update", "path": "app.py"},
            {"change_type": "create", "path": "README.md"},
        ],
        "available_decisions": approval_contract_runtime.patch_available_decisions(
            grant_root="/workspace"
        ),
    }

    rendered = approval_overlay_text(payload).plain

    assert "Would you like to make the following edits?" in rendered
    assert "Reason: need to update config" in rendered
    assert "Files: 2" in rendered
    assert "Yes, proceed (y)" in rendered
    assert "Yes, and don't ask again for these files (a)" in rendered
    assert "No, and tell AgentHub what to do differently (esc)" in rendered


def test_overlay_submit_escape_uses_cancel_decision() -> None:
    submitted: list[tuple[str, dict[str, object]]] = []
    overlay = ApprovalOverlay(on_submit=lambda command, payload: submitted.append((command, payload)))
    payload = {
        "approval_id": "appr_escape",
        "action_type": "shell_command",
        "available_decisions": approval_contract_runtime.shell_available_decisions(
            {"command_tokens": ["echo", "hi"]}
        ),
    }

    overlay.activate(payload)

    assert overlay.submit_escape() is True
    assert submitted[0][0] == "/reject appr_escape mode cancel"


def test_background_teammate_approval_activity_uses_generic_action_code() -> None:
    event = ToolEvent(
        name="background_teammate_approval_requested",
        ok=True,
        summary="background teammate approval requested appr_bg",
        payload={
            "approval_id": "appr_bg",
            "summary": "Approve background teammate live workspace run",
            "task": "Summarize the repo entrypoints",
            "provider": "openai",
            "model": "gpt-5.4",
            "sandbox_mode": "workspace-write",
            "available_decisions": approval_contract_runtime.generic_available_decisions(),
        },
    )

    activities = activity_events_for_tool_event(event)

    assert activities[0].code == "approval.request.action"
    assert activities[0].title == "Requested background teammate approval"
    assert activities[0].params["approval_id"] == "appr_bg"
