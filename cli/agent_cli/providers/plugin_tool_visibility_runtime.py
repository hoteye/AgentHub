from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping

from cli.agent_cli.providers import plugin_tool_visibility_runtime_helpers


FunctionNameFromSpec = Callable[[Any], str]


@dataclass(frozen=True)
class PluginToolProjectionDecision:
    function_name: str
    outcome: str
    reason: str
    tool_surface_profile: str = ""
    tool_result_projection_policy: str = ""
    continuation_policy: str = ""
    turn_protocol_policy: str = ""
    canonical_family: str = ""
    tool_capability_kind: str = ""
    tool_runtime_binding: str = ""
    builtin_family_projection: str = ""
    builtin_family_exposure: str = ""

    @property
    def include_in_tool_registry(self) -> bool:
        return self.outcome == "expose_tool"

_PROFILE_ALL = plugin_tool_visibility_runtime_helpers._PROFILE_ALL
_ALLOWED_MEDIA_KINDS = plugin_tool_visibility_runtime_helpers._ALLOWED_MEDIA_KINDS
_ALLOWED_MEDIA_INGEST_SEMANTICS = plugin_tool_visibility_runtime_helpers._ALLOWED_MEDIA_INGEST_SEMANTICS
_ALLOWED_MEDIA_SOURCE_MODES = plugin_tool_visibility_runtime_helpers._ALLOWED_MEDIA_SOURCE_MODES
_ALLOWED_MEDIA_PROJECTION_MODES = plugin_tool_visibility_runtime_helpers._ALLOWED_MEDIA_PROJECTION_MODES
_FUNCTION_RESULT_POLICIES = plugin_tool_visibility_runtime_helpers._FUNCTION_RESULT_POLICIES
_FUNCTION_CONTINUATION_POLICIES = plugin_tool_visibility_runtime_helpers._FUNCTION_CONTINUATION_POLICIES
_LOCAL_RUNTIME_BINDINGS = plugin_tool_visibility_runtime_helpers._LOCAL_RUNTIME_BINDINGS
_MESSAGE_NATIVE_RESULT_POLICIES = plugin_tool_visibility_runtime_helpers._MESSAGE_NATIVE_RESULT_POLICIES
_normalized_text = plugin_tool_visibility_runtime_helpers.normalized_text
_normalize_default_visibility = plugin_tool_visibility_runtime_helpers.normalize_default_visibility
_normalize_supported_profiles = plugin_tool_visibility_runtime_helpers.normalize_supported_profiles
_profile_supported_for_surface = plugin_tool_visibility_runtime_helpers.profile_supported_for_surface
_normalize_text_list = plugin_tool_visibility_runtime_helpers.normalize_text_list
_media_capability_from_declaration = plugin_tool_visibility_runtime_helpers.media_capability_from_declaration
_media_capability_shape_supported = plugin_tool_visibility_runtime_helpers.media_capability_shape_supported
_media_capability_visible_for_profile = plugin_tool_visibility_runtime_helpers.media_capability_visible_for_profile
_contract_media_source_modes = plugin_tool_visibility_runtime_helpers.contract_media_source_modes
_contract_media_projection_modes = plugin_tool_visibility_runtime_helpers.contract_media_projection_modes
_contract_supports_function_tool_surface = plugin_tool_visibility_runtime_helpers.contract_supports_function_tool_surface
_builtin_family_projection_category = plugin_tool_visibility_runtime_helpers.builtin_family_projection_category
_provider_native_plugin_fallback_visible_as_function_tool = (
    plugin_tool_visibility_runtime_helpers.provider_native_plugin_fallback_visible_as_function_tool
)
_declaration_from_extension = plugin_tool_visibility_runtime_helpers.declaration_from_extension
_declaration_items_from_manager = plugin_tool_visibility_runtime_helpers.declaration_items_from_manager


def plugin_tool_declarations_by_name(
    *,
    manager: Any,
    plugin_specs: Iterable[Dict[str, Any]],
    function_name_from_spec: FunctionNameFromSpec,
) -> Dict[str, Dict[str, Any]]:
    by_name: Dict[str, Dict[str, Any]] = {}
    for item in _declaration_items_from_manager(manager):
        tool_name = str(item.get("tool_name") or item.get("name") or "").strip()
        if not tool_name:
            continue
        by_name[tool_name] = dict(item)
    for spec in list(plugin_specs or []):
        tool_name = function_name_from_spec(spec)
        if not tool_name or tool_name in by_name:
            continue
        extension_item = _declaration_from_extension(spec)
        if extension_item:
            by_name[tool_name] = extension_item
    return by_name


def plugin_tool_projection_decision(
    *,
    function_name: str,
    tool_surface_profile: str,
    declarations_by_name: Mapping[str, Dict[str, Any]],
) -> PluginToolProjectionDecision:
    name = str(function_name or "").strip()
    if not name:
        return PluginToolProjectionDecision(function_name="", outcome="hide", reason="empty_function_name")
    declaration = dict(declarations_by_name.get(name) or {})
    if not declaration:
        return PluginToolProjectionDecision(function_name=name, outcome="hide", reason="undeclared_tool")

    default_visibility = _normalize_default_visibility(declaration.get("default_visibility"))
    if default_visibility != "model_visible":
        return PluginToolProjectionDecision(
            function_name=name,
            outcome="hide",
            reason="default_visibility_not_model_visible",
        )

    contract_metadata = plugin_tool_visibility_runtime_helpers.tool_surface_contract_metadata(tool_surface_profile)
    resolved_profile = _normalized_text(
        contract_metadata.get("tool_surface_profile") or tool_surface_profile
    )
    if not resolved_profile:
        return PluginToolProjectionDecision(
            function_name=name,
            outcome="hide",
            reason="missing_tool_surface_profile",
        )

    supported_profiles = _normalize_supported_profiles(declaration.get("supported_profiles"))
    if not supported_profiles:
        return PluginToolProjectionDecision(
            function_name=name,
            outcome="hide",
            reason="missing_supported_profiles",
            tool_surface_profile=resolved_profile,
        )
    if not _profile_supported_for_surface(
        resolved_profile=resolved_profile,
        supported_profiles=supported_profiles,
    ):
        return PluginToolProjectionDecision(
            function_name=name,
            outcome="hide",
            reason="profile_not_supported",
            tool_surface_profile=resolved_profile,
        )

    declaration_metadata = plugin_tool_visibility_runtime_helpers.declaration_contract_metadata(declaration)
    canonical_family = _normalized_text(declaration_metadata.get("canonical_family"))
    tool_capability_kind = _normalized_text(declaration_metadata.get("tool_capability_kind"))
    tool_runtime_binding = _normalized_text(declaration_metadata.get("tool_runtime_binding"))
    result_policy = _normalized_text(contract_metadata.get("tool_result_projection_policy"))
    continuation_policy = _normalized_text(contract_metadata.get("continuation_policy"))
    turn_protocol_policy = _normalized_text(contract_metadata.get("turn_protocol_policy"))

    if not canonical_family or not tool_capability_kind or not tool_runtime_binding:
        return PluginToolProjectionDecision(
            function_name=name,
            outcome="hide",
            reason="canonical_alignment_required",
            tool_surface_profile=resolved_profile,
            tool_result_projection_policy=result_policy,
            continuation_policy=continuation_policy,
            turn_protocol_policy=turn_protocol_policy,
        )

    family_metadata = plugin_tool_visibility_runtime_helpers.tool_family_metadata(
        tool_surface_profile=resolved_profile,
        canonical_family=canonical_family,
    )
    family_projection = _normalized_text(family_metadata.get("projection"))
    family_exposure = _normalized_text(family_metadata.get("exposure"))
    if family_metadata and family_exposure and family_exposure != "enabled":
        return PluginToolProjectionDecision(
            function_name=name,
            outcome="hide",
            reason="builtin_family_disabled_for_profile",
            tool_surface_profile=resolved_profile,
            tool_result_projection_policy=result_policy,
            continuation_policy=continuation_policy,
            turn_protocol_policy=turn_protocol_policy,
            canonical_family=canonical_family,
            tool_capability_kind=tool_capability_kind,
            tool_runtime_binding=tool_runtime_binding,
            builtin_family_projection=family_projection,
            builtin_family_exposure=family_exposure,
        )

    builtin_projection_category = _builtin_family_projection_category(family_metadata)
    media_capability = _media_capability_from_declaration(declaration)

    if tool_capability_kind == "ui_only_capability":
        return PluginToolProjectionDecision(
            function_name=name,
            outcome="hide",
            reason="ui_only_capability_never_model_visible",
            tool_surface_profile=resolved_profile,
            tool_result_projection_policy=result_policy,
            continuation_policy=continuation_policy,
            turn_protocol_policy=turn_protocol_policy,
            canonical_family=canonical_family,
            tool_capability_kind=tool_capability_kind,
            tool_runtime_binding=tool_runtime_binding,
            builtin_family_projection=family_projection,
            builtin_family_exposure=family_exposure,
        )

    if tool_capability_kind == "provider_native_tool":
        if tool_runtime_binding != "provider_native":
            outcome = "hide"
            reason = "provider_native_binding_required"
        elif builtin_projection_category != "native_preferred":
            outcome = "hide"
            reason = "provider_native_profile_projection_mismatch"
        elif _provider_native_plugin_fallback_visible_as_function_tool(
            resolved_profile=resolved_profile,
            supported_profiles=supported_profiles,
            family_metadata=family_metadata,
            result_policy=result_policy,
            continuation_policy=continuation_policy,
            turn_protocol_policy=turn_protocol_policy,
        ):
            outcome = "expose_tool"
            reason = "provider_native_fallback_function_tool_supported"
        elif not bool(
            (contract_metadata.get("optional_capabilities") or {}).get("native_web_search_runtime")
        ):
            outcome = "hide"
            reason = "provider_native_runtime_unavailable"
        else:
            outcome = "native_only"
            reason = "provider_native_requires_adapter_projection"
        return PluginToolProjectionDecision(
            function_name=name,
            outcome=outcome,
            reason=reason,
            tool_surface_profile=resolved_profile,
            tool_result_projection_policy=result_policy,
            continuation_policy=continuation_policy,
            turn_protocol_policy=turn_protocol_policy,
            canonical_family=canonical_family,
            tool_capability_kind=tool_capability_kind,
            tool_runtime_binding=tool_runtime_binding,
            builtin_family_projection=family_projection,
            builtin_family_exposure=family_exposure,
        )

    if tool_capability_kind == "message_native_capability":
        visible = _media_capability_visible_for_profile(
            media_capability=media_capability,
            tool_surface_profile=resolved_profile,
            tool_result_projection_policy=result_policy,
            continuation_policy=continuation_policy,
            turn_protocol_policy=turn_protocol_policy,
        )
        return PluginToolProjectionDecision(
            function_name=name,
            outcome="message_only" if visible else "hide",
            reason="message_native_capability_only" if visible else "message_native_projection_unsupported",
            tool_surface_profile=resolved_profile,
            tool_result_projection_policy=result_policy,
            continuation_policy=continuation_policy,
            turn_protocol_policy=turn_protocol_policy,
            canonical_family=canonical_family,
            tool_capability_kind=tool_capability_kind,
            tool_runtime_binding=tool_runtime_binding,
            builtin_family_projection=family_projection,
            builtin_family_exposure=family_exposure,
        )

    if tool_capability_kind != "local_runtime_tool":
        return PluginToolProjectionDecision(
            function_name=name,
            outcome="hide",
            reason="unsupported_tool_capability_kind",
            tool_surface_profile=resolved_profile,
            tool_result_projection_policy=result_policy,
            continuation_policy=continuation_policy,
            turn_protocol_policy=turn_protocol_policy,
            canonical_family=canonical_family,
            tool_capability_kind=tool_capability_kind,
            tool_runtime_binding=tool_runtime_binding,
            builtin_family_projection=family_projection,
            builtin_family_exposure=family_exposure,
        )

    if builtin_projection_category == "native_preferred":
        return PluginToolProjectionDecision(
            function_name=name,
            outcome="hide",
            reason="builtin_family_requires_native_projection",
            tool_surface_profile=resolved_profile,
            tool_result_projection_policy=result_policy,
            continuation_policy=continuation_policy,
            turn_protocol_policy=turn_protocol_policy,
            canonical_family=canonical_family,
            tool_capability_kind=tool_capability_kind,
            tool_runtime_binding=tool_runtime_binding,
            builtin_family_projection=family_projection,
            builtin_family_exposure=family_exposure,
        )

    if not _contract_supports_function_tool_surface(
        tool_surface_profile=resolved_profile,
        tool_result_projection_policy=result_policy,
        continuation_policy=continuation_policy,
        turn_protocol_policy=turn_protocol_policy,
    ):
        return PluginToolProjectionDecision(
            function_name=name,
            outcome="hide",
            reason="interaction_contract_cannot_project_function_tools",
            tool_surface_profile=resolved_profile,
            tool_result_projection_policy=result_policy,
            continuation_policy=continuation_policy,
            turn_protocol_policy=turn_protocol_policy,
            canonical_family=canonical_family,
            tool_capability_kind=tool_capability_kind,
            tool_runtime_binding=tool_runtime_binding,
            builtin_family_projection=family_projection,
            builtin_family_exposure=family_exposure,
        )

    if tool_runtime_binding in _LOCAL_RUNTIME_BINDINGS:
        return PluginToolProjectionDecision(
            function_name=name,
            outcome="expose_tool",
            reason="local_runtime_tool_supported",
            tool_surface_profile=resolved_profile,
            tool_result_projection_policy=result_policy,
            continuation_policy=continuation_policy,
            turn_protocol_policy=turn_protocol_policy,
            canonical_family=canonical_family,
            tool_capability_kind=tool_capability_kind,
            tool_runtime_binding=tool_runtime_binding,
            builtin_family_projection=family_projection,
            builtin_family_exposure=family_exposure,
        )

    if tool_runtime_binding == "shared_media_ingest":
        visible = _media_capability_visible_for_profile(
            media_capability=media_capability,
            tool_surface_profile=resolved_profile,
            tool_result_projection_policy=result_policy,
            continuation_policy=continuation_policy,
            turn_protocol_policy=turn_protocol_policy,
        )
        return PluginToolProjectionDecision(
            function_name=name,
            outcome="expose_tool" if visible else "hide",
            reason="shared_media_ingest_supported" if visible else "shared_media_ingest_projection_unsupported",
            tool_surface_profile=resolved_profile,
            tool_result_projection_policy=result_policy,
            continuation_policy=continuation_policy,
            turn_protocol_policy=turn_protocol_policy,
            canonical_family=canonical_family,
            tool_capability_kind=tool_capability_kind,
            tool_runtime_binding=tool_runtime_binding,
            builtin_family_projection=family_projection,
            builtin_family_exposure=family_exposure,
        )

    return PluginToolProjectionDecision(
        function_name=name,
        outcome="hide",
        reason="runtime_binding_not_model_tool_projectable",
        tool_surface_profile=resolved_profile,
        tool_result_projection_policy=result_policy,
        continuation_policy=continuation_policy,
        turn_protocol_policy=turn_protocol_policy,
        canonical_family=canonical_family,
        tool_capability_kind=tool_capability_kind,
        tool_runtime_binding=tool_runtime_binding,
        builtin_family_projection=family_projection,
        builtin_family_exposure=family_exposure,
    )


def plugin_tool_visible_for_profile(
    *,
    function_name: str,
    tool_surface_profile: str,
    declarations_by_name: Mapping[str, Dict[str, Any]],
) -> bool:
    decision = plugin_tool_projection_decision(
        function_name=function_name,
        tool_surface_profile=tool_surface_profile,
        declarations_by_name=declarations_by_name,
    )
    return decision.include_in_tool_registry
