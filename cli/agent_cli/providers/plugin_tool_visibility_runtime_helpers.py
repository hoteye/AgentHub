from __future__ import annotations

from typing import Any, Dict, List, Mapping

from cli.agent_cli.providers import interaction_contract_runtime as interaction_contract_runtime_helpers

_PROFILE_ALL = frozenset({"*", "all", "any"})
_ALLOWED_MEDIA_KINDS = frozenset({"image", "document", "audio", "video", "binary"})
_ALLOWED_MEDIA_INGEST_SEMANTICS = frozenset({"shared_media_ingest_v1"})
_ALLOWED_MEDIA_SOURCE_MODES = frozenset({"tool_path", "user_attachment", "hybrid"})
_ALLOWED_MEDIA_PROJECTION_MODES = frozenset(
    {
        "tool_native_continuation",
        "tool_result_content_block",
        "message_native_attachment",
    }
)
_FUNCTION_RESULT_POLICIES = frozenset({"codex_like", "claude_like", "generic", "generic_function_tool_result"})
_FUNCTION_CONTINUATION_POLICIES = frozenset(
    {
        "responses_native_preferred",
        "anthropic_native_preferred",
        "client_managed_history",
        "generic",
    }
)
_LOCAL_RUNTIME_BINDINGS = frozenset({"local_runtime", "plugin_runtime", "plugin_mcp_server"})
_MESSAGE_NATIVE_RESULT_POLICIES = frozenset({"codex_like", "claude_like"})


def normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_default_visibility(value: Any) -> str:
    text = normalized_text(value)
    if text in {"model_visible", "host_only", "operator_only", "disabled"}:
        return text
    return ""


def normalize_supported_profiles(value: Any) -> List[str]:
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [normalized_text(item) for item in value]
    elif isinstance(value, str):
        items = [normalized_text(item) for item in value.split(",")]
    else:
        items = []
    return [item for item in items if item]


def profile_supported_for_surface(
    *,
    resolved_profile: str,
    supported_profiles: List[str],
) -> bool:
    if any(item in _PROFILE_ALL for item in supported_profiles):
        return True
    if resolved_profile in supported_profiles:
        return True
    if resolved_profile == "claude_code" and "generic_chat" in supported_profiles:
        return True
    return False


def normalize_text_list(value: Any) -> List[str] | None:
    if isinstance(value, (list, tuple, set, frozenset)):
        return [normalized_text(item) for item in value if normalized_text(item)]
    if isinstance(value, str):
        text = normalized_text(value)
        return [text] if text else []
    return None


def media_capability_from_declaration(declaration: Mapping[str, Any]) -> Dict[str, Any]:
    media_capability = declaration.get("media_capability")
    if isinstance(media_capability, dict):
        return dict(media_capability)
    media_capability = declaration.get("mediaCapability")
    if isinstance(media_capability, dict):
        return dict(media_capability)
    return {}


def media_capability_shape_supported(media_capability: Mapping[str, Any]) -> bool:
    media_kind = normalized_text(
        media_capability.get("media_kind")
        or media_capability.get("mediaKind")
        or ""
    )
    if media_kind not in _ALLOWED_MEDIA_KINDS:
        return False

    ingest_semantics = normalized_text(
        media_capability.get("ingest_semantics")
        or media_capability.get("ingestSemantics")
        or "shared_media_ingest_v1"
    )
    if ingest_semantics not in _ALLOWED_MEDIA_INGEST_SEMANTICS:
        return False

    source_modes = normalize_text_list(
        media_capability.get("source_modes")
        if "source_modes" in media_capability
        else media_capability.get("sourceModes")
    )
    if not source_modes or any(item not in _ALLOWED_MEDIA_SOURCE_MODES for item in source_modes):
        return False

    projection_modes = normalize_text_list(
        media_capability.get("projection_modes")
        if "projection_modes" in media_capability
        else media_capability.get("projectionModes")
    )
    if not projection_modes or any(item not in _ALLOWED_MEDIA_PROJECTION_MODES for item in projection_modes):
        return False

    mime_types = normalize_text_list(
        media_capability.get("mime_types")
        if "mime_types" in media_capability
        else media_capability.get("mimeTypes")
    )
    if mime_types is None:
        return False
    if any("/" not in item for item in mime_types):
        return False

    max_size = media_capability.get("max_size_bytes")
    if max_size is None:
        max_size = media_capability.get("maxSizeBytes")
    if max_size not in (None, ""):
        try:
            if int(max_size) <= 0:
                return False
        except (TypeError, ValueError):
            return False
    return True


def media_capability_visible_for_profile(
    *,
    media_capability: Mapping[str, Any],
    tool_surface_profile: str,
    tool_result_projection_policy: str = "",
    continuation_policy: str = "",
    turn_protocol_policy: str = "",
) -> bool:
    if not media_capability:
        return True
    if not media_capability_shape_supported(media_capability):
        return False
    supported_sources = contract_media_source_modes(tool_surface_profile=tool_surface_profile)
    supported_projections = contract_media_projection_modes(
        tool_result_projection_policy=tool_result_projection_policy,
        continuation_policy=continuation_policy,
        turn_protocol_policy=turn_protocol_policy,
    )
    if not supported_sources or not supported_projections:
        return False
    source_modes = normalize_text_list(
        media_capability.get("source_modes")
        if "source_modes" in media_capability
        else media_capability.get("sourceModes")
    ) or []
    projection_modes = normalize_text_list(
        media_capability.get("projection_modes")
        if "projection_modes" in media_capability
        else media_capability.get("projectionModes")
    ) or []
    return any(item in supported_sources for item in source_modes) and any(
        item in supported_projections for item in projection_modes
    )


def contract_media_source_modes(*, tool_surface_profile: str) -> frozenset[str]:
    profile = normalized_text(tool_surface_profile)
    if profile in {"codex_openai", "claude_code"}:
        return frozenset({"tool_path", "user_attachment", "hybrid"})
    if profile == "generic_chat":
        return frozenset({"tool_path"})
    return frozenset()


def contract_media_projection_modes(
    *,
    tool_result_projection_policy: str,
    continuation_policy: str,
    turn_protocol_policy: str,
) -> frozenset[str]:
    result_policy = normalized_text(tool_result_projection_policy)
    continuation = normalized_text(continuation_policy)
    turn_policy = normalized_text(turn_protocol_policy)
    supported: set[str] = set()
    if result_policy in _FUNCTION_RESULT_POLICIES:
        supported.add("tool_result_content_block")
    if result_policy in _MESSAGE_NATIVE_RESULT_POLICIES:
        supported.add("message_native_attachment")
    if continuation == "responses_native_preferred" and turn_policy.startswith("openai_responses"):
        supported.add("tool_native_continuation")
    return frozenset(supported)


def contract_supports_function_tool_surface(
    *,
    tool_surface_profile: str,
    tool_result_projection_policy: str,
    continuation_policy: str,
    turn_protocol_policy: str,
) -> bool:
    profile = normalized_text(tool_surface_profile)
    result_policy = normalized_text(tool_result_projection_policy)
    continuation = normalized_text(continuation_policy)
    turn_policy = normalized_text(turn_protocol_policy)
    if not profile or result_policy not in _FUNCTION_RESULT_POLICIES:
        return False
    if continuation not in _FUNCTION_CONTINUATION_POLICIES:
        return False
    return bool(
        turn_policy in {"generic", "generic_chat_turn"}
        or turn_policy.startswith("openai_responses")
        or turn_policy.startswith("anthropic_messages")
    )


def builtin_family_projection_category(family_metadata: Mapping[str, Any]) -> str:
    projection = normalized_text(family_metadata.get("projection"))
    if projection in {"canonical", "function", "capability_driven", "claude_shell_split"}:
        return "function_tool"
    if projection == "native_if_available":
        return "native_preferred"
    return ""


def provider_native_plugin_fallback_visible_as_function_tool(
    *,
    resolved_profile: str,
    supported_profiles: List[str],
    family_metadata: Mapping[str, Any],
    result_policy: str,
    continuation_policy: str,
    turn_protocol_policy: str,
) -> bool:
    if resolved_profile != "claude_code":
        return False
    if "generic_chat" not in supported_profiles:
        return False
    if normalized_text(family_metadata.get("fallback_backend")) != "local":
        return False
    return contract_supports_function_tool_surface(
        tool_surface_profile=resolved_profile,
        tool_result_projection_policy=result_policy,
        continuation_policy=continuation_policy,
        turn_protocol_policy=turn_protocol_policy,
    )


def declaration_from_extension(spec: Any) -> Dict[str, Any]:
    if not isinstance(spec, dict):
        return {}
    for key in ("x_agenthub_plugin_capability", "x_plugin_capability"):
        item = spec.get(key)
        if isinstance(item, dict):
            return dict(item)
    return {}


def declaration_items_from_manager(manager: Any) -> List[Dict[str, Any]]:
    if manager is None:
        return []
    for getter_name in (
        "provider_tool_capability_declarations",
        "plugin_tool_capability_declarations",
        "tool_capability_declarations",
        "provider_capability_declarations",
        "plugin_capability_declarations",
    ):
        getter = getattr(manager, getter_name, None)
        if not callable(getter):
            continue
        try:
            payload = getter()
        except Exception:
            continue
        if isinstance(payload, dict):
            items = payload.get("items")
            if isinstance(items, list):
                return [dict(item) for item in items if isinstance(item, dict)]
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, dict)]
    return []


def declaration_contract_metadata(declaration: Mapping[str, Any]) -> Dict[str, Any]:
    return interaction_contract_runtime_helpers.plugin_declaration_contract_metadata(declaration)


def tool_surface_contract_metadata(tool_surface_profile: str) -> Dict[str, Any]:
    return interaction_contract_runtime_helpers.interaction_contract_metadata_for_tool_surface_profile(
        tool_surface_profile
    )


def tool_family_metadata(*, tool_surface_profile: str, canonical_family: str) -> Dict[str, Any]:
    return interaction_contract_runtime_helpers.interaction_contract_tool_family_metadata(
        tool_surface_profile=tool_surface_profile,
        canonical_family=canonical_family,
    )
