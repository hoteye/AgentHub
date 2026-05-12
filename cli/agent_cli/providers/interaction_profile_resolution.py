from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from cli.agent_cli.providers.interaction_contract import ResolvedInteractionContract

DEFAULT_PROFILE = "generic_chat"

_EXPLICIT_PROFILE_SOURCES = {
    "explicit",
    "model_config",
    "provider_config",
    "model_explicit",
    "provider_explicit",
    "legacy_alias",
    "cli_override",
}

_DEFAULT_COMPATIBILITY: dict[str, tuple[set[str], set[str]]] = {
    "codex_openai": ({"openai_responses"}, {"responses", "openai_responses"}),
    "claude_code": ({"anthropic_messages"}, {"anthropic_messages"}),
    "generic_chat": ({"openai_chat", "deepseek_chat", "deepseek_reasoner"}, {"openai_chat"}),
}


class InteractionProfileResolutionError(ValueError):
    pass


class InteractionProfileCompatibilityError(InteractionProfileResolutionError):
    def __init__(self, message: str, *, conflict_reason: str) -> None:
        super().__init__(message)
        self.conflict_reason = conflict_reason


@dataclass(frozen=True, slots=True)
class _ProfileSpecView:
    profile: str
    base_prompt_profile: str
    tool_surface_profile: str
    context_prelude_policy: str
    tool_result_projection_policy: str
    continuation_policy: str
    turn_protocol_policy: str
    fallback_profile: str
    allowed_planner_kinds: tuple[str, ...]
    allowed_wire_apis: tuple[str, ...]


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalized_set(values: Any) -> tuple[str, ...]:
    if isinstance(values, (list, tuple, set)):
        return tuple(item for item in (_normalized(value) for value in values) if item)
    return tuple()


def _field_value(spec: Any, key: str) -> Any:
    if isinstance(spec, Mapping):
        return spec.get(key)
    return getattr(spec, key, None)


def _field_text(spec: Any, key: str, default: str = "") -> str:
    value = _field_value(spec, key)
    text = str(value or "").strip()
    return text or default


def _selection_hints(spec: Any) -> Mapping[str, Any]:
    hints = _field_value(spec, "selection_hints")
    if isinstance(hints, Mapping):
        return hints
    return {}


def _profile_spec_view(spec: Any, *, profile_name: str) -> _ProfileSpecView:
    profile = _field_text(spec, "profile", default=profile_name) or profile_name
    hints = _selection_hints(spec)
    fallback_profile = _field_text(spec, "fallback_profile", default=DEFAULT_PROFILE) or DEFAULT_PROFILE

    planner_values = _field_value(spec, "allowed_planner_kinds")
    if planner_values is None:
        planner_values = hints.get("allowed_planner_kinds") or hints.get("planner_kinds")
    wire_values = _field_value(spec, "allowed_wire_apis")
    if wire_values is None:
        wire_values = hints.get("allowed_wire_apis") or hints.get("wire_apis")

    if profile in _DEFAULT_COMPATIBILITY:
        default_planners, default_wires = _DEFAULT_COMPATIBILITY[profile]
    else:
        default_planners, default_wires = (set(), set())

    allowed_planner_kinds = _normalized_set(planner_values) or tuple(sorted(default_planners))
    allowed_wire_apis = _normalized_set(wire_values) or tuple(sorted(default_wires))

    return _ProfileSpecView(
        profile=profile,
        base_prompt_profile=_field_text(spec, "base_prompt_profile", default=profile),
        tool_surface_profile=_field_text(spec, "tool_surface_profile", default=profile),
        context_prelude_policy=_field_text(spec, "context_prelude_policy", default="generic"),
        tool_result_projection_policy=_field_text(spec, "tool_result_projection_policy", default="generic"),
        continuation_policy=_field_text(spec, "continuation_policy", default="generic"),
        turn_protocol_policy=_field_text(spec, "turn_protocol_policy", default="generic"),
        fallback_profile=fallback_profile,
        allowed_planner_kinds=allowed_planner_kinds,
        allowed_wire_apis=allowed_wire_apis,
    )


def _profile_spec_map(bundled_profile_specs: Mapping[str, Any]) -> dict[str, _ProfileSpecView]:
    items: dict[str, _ProfileSpecView] = {}
    for key, value in dict(bundled_profile_specs or {}).items():
        profile_key = _normalized(key)
        if not profile_key:
            continue
        items[profile_key] = _profile_spec_view(value, profile_name=profile_key)
    return items


def _is_explicit_source(source: str) -> bool:
    normalized = _normalized(source)
    if normalized in _EXPLICIT_PROFILE_SOURCES or normalized.startswith("explicit_"):
        return True
    return normalized.startswith("model.") or normalized.startswith("provider.")


def _compatibility_conflict_reason(
    *,
    profile: str,
    planner_kind: str,
    wire_api: str,
    allowed_planner_kinds: tuple[str, ...],
    allowed_wire_apis: tuple[str, ...],
) -> str:
    parts: list[str] = []
    if planner_kind and allowed_planner_kinds and planner_kind not in allowed_planner_kinds:
        parts.append(
            f"planner_kind `{planner_kind}` not in {{{', '.join(allowed_planner_kinds)}}}"
        )
    if wire_api and allowed_wire_apis and wire_api not in allowed_wire_apis:
        parts.append(
            f"wire_api `{wire_api}` not in {{{', '.join(allowed_wire_apis)}}}"
        )
    if not parts:
        return ""
    return f"profile `{profile}` incompatible: " + "; ".join(parts)


def _build_contract(
    *,
    spec: _ProfileSpecView,
    source: str,
    conflict_reason: str = "",
) -> ResolvedInteractionContract:
    return ResolvedInteractionContract(
        profile=spec.profile,
        source=source,
        base_prompt_profile=spec.base_prompt_profile,
        tool_surface_profile=spec.tool_surface_profile,
        context_prelude_policy=spec.context_prelude_policy,
        tool_result_projection_policy=spec.tool_result_projection_policy,
        continuation_policy=spec.continuation_policy,
        turn_protocol_policy=spec.turn_protocol_policy,
        fallback_profile=spec.fallback_profile,
        conflict_reason=conflict_reason,
    )


def resolve_interaction_contract(
    *,
    configured_profile: str,
    profile_source: str,
    bundled_profile_specs: Mapping[str, Any],
    planner_kind: str,
    wire_api: str,
) -> ResolvedInteractionContract:
    profile = _normalized(configured_profile) or DEFAULT_PROFILE
    source = _normalized(profile_source) or "default"
    planner = _normalized(planner_kind)
    wire = _normalized(wire_api)

    specs = _profile_spec_map(bundled_profile_specs)
    if profile not in specs:
        conflict_reason = f"unknown interaction profile `{profile}`"
        if _is_explicit_source(source):
            raise InteractionProfileResolutionError(conflict_reason)
        profile = DEFAULT_PROFILE
        source = "fallback_generic_chat"

    selected = specs.get(profile)
    if selected is None:
        raise InteractionProfileResolutionError(
            f"missing bundled profile `{profile}` while resolving interaction contract"
        )

    conflict_reason = _compatibility_conflict_reason(
        profile=selected.profile,
        planner_kind=planner,
        wire_api=wire,
        allowed_planner_kinds=selected.allowed_planner_kinds,
        allowed_wire_apis=selected.allowed_wire_apis,
    )
    if not conflict_reason:
        return _build_contract(spec=selected, source=source)

    if _is_explicit_source(source):
        raise InteractionProfileCompatibilityError(
            f"explicit interaction profile conflict: {conflict_reason}",
            conflict_reason=conflict_reason,
        )

    fallback = specs.get(DEFAULT_PROFILE)
    if fallback is None:
        raise InteractionProfileResolutionError(
            f"fallback profile `{DEFAULT_PROFILE}` missing while handling conflict: {conflict_reason}"
        )
    return _build_contract(
        spec=fallback,
        source="fallback_generic_chat",
        conflict_reason=conflict_reason,
    )
