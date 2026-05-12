from __future__ import annotations

from cli.agent_cli.command_execution_summary_runtime import command_display_text_from_mapping
from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime_core.event_rendering import activity_events_for_tool_event


RAW_BANNER_COMMAND = (
    "printf '--- top-level dirs ---\\n' && find . -maxdepth 1 -type d | sed 's#^./##' | sort "
    "&& printf '\\n--- source-like dirs ---\\n' && find . \\( -path '*/.git' -o -path '*/.venv' "
    "-o -path '*/venv' -o -path '*/node_modules' -o -path '*/dist' -o -path '*/build' -o -path "
    "'*/__pycache__' -o -path '*/artifacts' -o -path '*/logs' -o -path '*/.pytest_cache' \\) "
    "-prune -o -type d | sed 's#^./##' | sort | rg '^(cli|plugins|shared|gui|workers|tools|document_tools|config)(/|$)' "
    "| head -300"
)


def test_command_display_text_from_mapping_keeps_failure_prefix_for_banner_command() -> None:
    display = command_display_text_from_mapping(
        {"command": RAW_BANNER_COMMAND, "returncode": 2},
        single_line=True,
        max_chars=400,
    )

    assert display.startswith("printf '--- top-level dirs ---\\n' && find . -maxdepth 1 -type d | sed")
    assert "'|' sed" not in display


def test_command_display_text_from_mapping_keeps_compact_success_display_for_banner_command() -> None:
    display = command_display_text_from_mapping(
        {"command": RAW_BANNER_COMMAND, "returncode": 0},
        single_line=True,
        max_chars=400,
    )

    assert display.startswith("find . -maxdepth 1 -type d")
    assert "printf '--- top-level dirs ---\\n'" not in display
    assert "'|' sed" in display


def test_activity_events_for_failed_shell_event_preserve_raw_command_prefix() -> None:
    event = ToolEvent(
        name="shell",
        ok=False,
        summary="shell failed",
        payload={
            "command": RAW_BANNER_COMMAND,
            "returncode": 2,
            "duration_ms": 5,
        },
    )

    activities = activity_events_for_tool_event(event)

    assert activities[0].title.startswith("Command failed: printf '--- top-level dirs ---\\n'")
    assert activities[0].params.get("command_display", "").startswith("printf '--- top-level dirs ---\\n'")
