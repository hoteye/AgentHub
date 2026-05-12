from __future__ import annotations

from typing import Any, Dict, Tuple

from cli.agent_cli.providers import tool_family_metadata_base_specs_core_helpers_runtime as core_helpers_runtime
from cli.agent_cli.providers import tool_family_metadata_base_specs_helpers_runtime as base_specs_helpers_runtime
from cli.agent_cli.providers import tool_family_metadata_base_specs_surface_helpers_runtime as surface_helpers_runtime
from cli.agent_cli.providers import tool_family_mapping_runtime as mapping_runtime
from cli.agent_cli.slash_surface import surface_usage_text


def _command_execution_contract_metadata(
    *,
    tool_name: str,
    tool_role: str,
    compatibility_alias_for: str = "",
    model_default_exposure: str = "",
) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {
        "canonical_family": mapping_runtime.COMMAND_EXECUTION_CANONICAL_FAMILY,
        "command_execution_role": tool_role,
        "command_execution_primary_tools": mapping_runtime.COMMAND_EXECUTION_PRIMARY_TOOLS,
        "command_execution_continuation_tools": mapping_runtime.COMMAND_EXECUTION_CONTINUATION_TOOLS,
        "command_execution_event_projection": mapping_runtime.COMMAND_EXECUTION_EVENT_PROJECTION_NAME,
        "command_execution_event_projection_scopes": mapping_runtime.COMMAND_EXECUTION_EVENT_PROJECTION_SCOPES,
        "command_execution_compatibility_aliases": mapping_runtime.COMMAND_EXECUTION_TOOL_COMPAT_ALIASES,
        "command_execution_session_semantics": "persistent_session",
        "command_execution_observable_activity": True,
        "event_projection_is_model_tool": False,
    }
    if model_default_exposure:
        metadata["model_default_exposure"] = model_default_exposure
    if compatibility_alias_for:
        metadata["compatibility_alias_for"] = compatibility_alias_for
    else:
        metadata["canonical_tool_name"] = tool_name
    return metadata


def _apply_patch_contract_metadata() -> Dict[str, Any]:
    return {
        "canonical_family": mapping_runtime.APPLY_PATCH_CANONICAL_FAMILY,
        "canonical_tool_name": "apply_patch",
        "editing_domain": mapping_runtime.EDITING_DOMAIN_NAME,
        "editing_domain_canonical_operations": mapping_runtime.EDITING_DOMAIN_CANONICAL_OPERATIONS,
        "codex_model_primary_tools": mapping_runtime.APPLY_PATCH_CODEX_PRIMARY_TOOLS,
        "claude_model_primary_tools": mapping_runtime.APPLY_PATCH_CLAUDE_PRIMARY_TOOLS,
        "projection_variants": mapping_runtime.APPLY_PATCH_PROJECTION_VARIANTS,
        "model_default_exposure": "profile_declared",
        "event_projection_is_model_tool": False,
    }


def _expert_review_contract_metadata() -> Dict[str, Any]:
    return {
        "canonical_family": mapping_runtime.EXPERT_REVIEW_CANONICAL_FAMILY,
        "canonical_tool_name": "expert_review",
        "expert_review_runtime_binding": mapping_runtime.EXPERT_REVIEW_RUNTIME_BINDING,
        "model_default_exposure": "conditional_gate",
        "event_projection_is_model_tool": False,
    }


def build_base_capability_tool_specs(
    *,
    browser_runtime_actions: Tuple[str, ...],
    browser_provider_actions: Tuple[str, ...],
) -> Tuple[Dict[str, Any], ...]:
    return (
        *core_helpers_runtime.runtime_and_delegation_tool_specs(
            surface_usage_text_fn=surface_usage_text,
            command_execution_contract_metadata=_command_execution_contract_metadata,
            apply_patch_contract_metadata=_apply_patch_contract_metadata,
        ),
        *surface_helpers_runtime.workspace_and_remote_tool_specs(
            surface_usage_text_fn=surface_usage_text,
            browser_runtime_actions=browser_runtime_actions,
            browser_provider_actions=browser_provider_actions,
            expert_review_contract_metadata=_expert_review_contract_metadata,
        ),
        *base_specs_helpers_runtime.navigation_and_policy_tool_specs(),
    )
