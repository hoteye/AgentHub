from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.providers.config_catalog_types import ProviderConfig
from cli.agent_cli.providers.tool_specs import provider_tool_names
from cli.agent_cli.tools import ToolRegistry


RELEVANT_SURFACE_TOOLS = ("apply_patch", "Write", "Edit", "Bash", "write_stdin")
CODEX_REFERENCE_FILES = (
    "/home/lyc/project/AgentHubRef/codex_ref/codex-rs/core/tests/suite/apply_patch_cli.rs",
    "/home/lyc/project/AgentHubRef/codex_ref/codex-rs/core/tests/suite/unified_exec.rs",
)
CLAUDE_REFERENCE_FILES = (
    "/home/lyc/project/AgentHubRef/repo_ref/版本1-src/src/tools/FileWriteTool/FileWriteTool.ts",
    "/home/lyc/project/AgentHubRef/repo_ref/版本1-src/src/tools/FileEditTool/FileEditTool.ts",
    "/home/lyc/project/AgentHubRef/repo_ref/版本1-src/src/hooks/useTurnDiffs.ts",
)


def _surface_runtime(profile: str, *, model: str | None = None) -> Any:
    if profile == "claude_code":
        config = ProviderConfig(
            model=str(model or "claude-sonnet-4-6"),
            api_key="test-key",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
            interaction_profile="claude_code",
            interaction_profile_source="acceptance",
        )
    else:
        config = ProviderConfig(
            model=str(model or "gpt-5.4"),
            api_key="test-key",
            provider_name="openai",
            planner_kind="openai_responses",
            wire_api="openai_responses",
            interaction_profile="codex_openai",
            interaction_profile_source="acceptance",
        )
    return SimpleNamespace(
        tools=ToolRegistry(),
        agent=SimpleNamespace(_planner=SimpleNamespace(config=config)),
    )


def _surface_snapshot(profile: str, *, model: str | None = None) -> dict[str, Any]:
    runtime = _surface_runtime(profile, model=model)
    config = runtime.agent._planner.config
    names = provider_tool_names(config, current_host_platform())
    relevant_names = [name for name in names if name in RELEVANT_SURFACE_TOOLS]
    return {
        "label": f"{profile}:{config.model}",
        "profile": profile,
        "model": str(config.model or ""),
        "relevant_tool_names": relevant_names,
        "has_apply_patch": "apply_patch" in relevant_names,
        "has_write": "Write" in relevant_names,
        "has_edit": "Edit" in relevant_names,
    }


def _reference_snapshot() -> list[dict[str, Any]]:
    return [
        {
            "system": "codex_ref",
            "reference_files": list(CODEX_REFERENCE_FILES),
            "model_visible_tools": ["apply_patch"],
            "notes": [
                "Reference tests cover freeform, function, shell, and shell-via-heredoc apply_patch projections.",
                "Unified exec interception of apply_patch remains an external dependency for AgentHub command execution parity.",
            ],
        },
        {
            "system": "claude_code_ref",
            "reference_files": list(CLAUDE_REFERENCE_FILES),
            "model_visible_tools": ["Write", "Edit"],
            "notes": [
                "FileWriteTool returns type=create|update plus structuredPatch.",
                "FileEditTool returns structuredPatch and replaceAll metadata, and useTurnDiffs consumes structuredPatch.",
            ],
        },
    ]


def _regression_bundle() -> dict[str, Any]:
    return {
        "surface_contract": [
            "pytest -q cli/tests/test_reference_parity.py cli/tests/test_provider_tool_specs_shared.py cli/tests/test_builtin_provider_tool_specs.py cli/tests/test_runtime_tools_surface_runtime.py cli/tests/test_system_prompts.py cli/tests/test_responses_tool_specs_interaction_profile.py cli/tests/test_anthropic_structured_edit_tools.py -k 'apply_patch or Write or Edit'"
        ],
        "backend": [
            "pytest -q cli/tests/test_apply_patch_bridge.py -k 'apply_patch or Write or Edit'"
        ],
        "observable_projection": [
            "pytest -q cli/tests/test_turn_items_alignment.py cli/tests/test_app_server_protocol.py cli/tests/test_reference_transcript_baseline.py -k 'apply_patch or Write or Edit'"
        ],
        "task_d_closure": [
            "pytest -q cli/tests/test_apply_patch_bridge.py cli/tests/test_runtime_tools_surface_runtime.py cli/tests/test_responses_tool_specs_interaction_profile.py cli/tests/test_turn_items_alignment.py cli/tests/test_app_server_protocol.py cli/tests/test_reference_transcript_baseline.py -k 'apply_patch or Write or Edit'"
        ],
        "acceptance_harness": [
            "python cli/scripts/apply_patch_wave01_acceptance.py --json"
        ],
        "open_dependency": [
            "Codex-style exec_command heredoc interception now lands in the exec runtime itself; keep broader command-execution live coverage under the unified command-execution wave."
        ],
    }
