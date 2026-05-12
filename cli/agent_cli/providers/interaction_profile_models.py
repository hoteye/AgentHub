from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from cli.agent_cli.providers import tool_family_mapping_runtime as mapping_runtime


class InteractionProfileLoadError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class InteractionToolFamilySpec:
    name: str
    exposure: str
    projection: str
    fallback_backend: str = ""
    canonical_family: str = ""
    projection_surface_family: str = ""
    projected_primary_tools: tuple[str, ...] = field(default_factory=tuple)
    projected_continuation_tools: tuple[str, ...] = field(default_factory=tuple)
    compatibility_aliases: tuple[str, ...] = field(default_factory=tuple)
    event_projection_name: str = ""


@dataclass(frozen=True, slots=True)
class InteractionProfileSpec:
    schema_version: int
    profile: str
    display_name: str
    base_prompt_profile: str
    tool_surface_profile: str
    context_prelude_policy: str
    tool_result_projection_policy: str
    continuation_policy: str
    turn_protocol_policy: str
    required_capabilities: dict[str, bool] = field(default_factory=dict)
    optional_capabilities: dict[str, bool] = field(default_factory=dict)
    tool_families: dict[str, InteractionToolFamilySpec] = field(default_factory=dict)
    fallback_profile: str = ""
    selection_hints: dict[str, Any] = field(default_factory=dict)
    plugin_exposure_policy: dict[str, Any] = field(default_factory=dict)


_REQUIRED_TEXT_FIELDS: tuple[str, ...] = (
    "profile",
    "display_name",
    "base_prompt_profile",
    "tool_surface_profile",
    "context_prelude_policy",
    "tool_result_projection_policy",
    "continuation_policy",
    "turn_protocol_policy",
    "fallback_profile",
)

_ALLOWED_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "schema_version",
        *list(_REQUIRED_TEXT_FIELDS),
        "required_capabilities",
        "optional_capabilities",
        "tool_families",
        "selection_hints",
        "plugin_exposure_policy",
    }
)


def _coerce_bool(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise InteractionProfileLoadError(f"invalid boolean for `{field_name}`: {value!r}")


def _require_mapping(payload: Any, *, field_name: str, source: str) -> Mapping[str, Any]:
    if isinstance(payload, Mapping):
        return payload
    raise InteractionProfileLoadError(f"`{field_name}` must be a mapping in {source}")


def _required_text(mapping: Mapping[str, Any], key: str, *, source: str) -> str:
    value = str(mapping.get(key) or "").strip()
    if not value:
        raise InteractionProfileLoadError(f"missing `{key}` in {source}")
    return value


def _normalized_bool_mapping(payload: Any, *, field_name: str, source: str) -> dict[str, bool]:
    mapping = _require_mapping(payload or {}, field_name=field_name, source=source)
    normalized: dict[str, bool] = {}
    for raw_key, raw_value in mapping.items():
        key = str(raw_key or "").strip()
        if not key:
            raise InteractionProfileLoadError(f"empty key in `{field_name}` for {source}")
        normalized[key] = _coerce_bool(raw_value, field_name=f"{field_name}.{key}")
    return normalized


def _normalized_tool_names(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return tuple()
    return tuple(str(item or "").strip() for item in value if str(item or "").strip())


def _derived_tool_family_contract(*, profile: str, name: str) -> dict[str, Any]:
    canonical_family = name
    projection_surface_family = "identity"
    projected_primary_tools = (name,)
    projected_continuation_tools: tuple[str, ...] = tuple()
    compatibility_aliases: tuple[str, ...] = tuple()
    event_projection_name = ""

    if name == "exec_command":
        canonical_family = mapping_runtime.COMMAND_EXECUTION_CANONICAL_FAMILY
        compatibility_aliases = mapping_runtime.COMMAND_EXECUTION_TOOL_COMPAT_ALIASES
        event_projection_name = mapping_runtime.COMMAND_EXECUTION_EVENT_PROJECTION_NAME
        if profile == "claude_code":
            projection_surface_family = "claude_shell_split"
            projected_primary_tools = ("Bash", "PowerShell")
        else:
            projection_surface_family = "canonical_exec_pair"
            projected_primary_tools = mapping_runtime.COMMAND_EXECUTION_PRIMARY_TOOLS
        projected_continuation_tools = mapping_runtime.COMMAND_EXECUTION_CONTINUATION_TOOLS
    elif name == "request_user_input" and profile == "claude_code":
        projection_surface_family = "claude_ask_user_question"
        projected_primary_tools = ("AskUserQuestion",)

    return {
        "canonical_family": canonical_family,
        "projection_surface_family": projection_surface_family,
        "projected_primary_tools": projected_primary_tools,
        "projected_continuation_tools": projected_continuation_tools,
        "compatibility_aliases": compatibility_aliases,
        "event_projection_name": event_projection_name,
    }


def _normalized_tool_families(payload: Any, *, profile: str, source: str) -> dict[str, InteractionToolFamilySpec]:
    mapping = _require_mapping(payload or {}, field_name="tool_families", source=source)
    normalized: dict[str, InteractionToolFamilySpec] = {}
    for raw_name, raw_item in mapping.items():
        name = str(raw_name or "").strip()
        if not name:
            raise InteractionProfileLoadError(f"empty tool family name in {source}")
        if name in set(mapping_runtime.COMMAND_EXECUTION_TOOL_COMPAT_ALIASES):
            raise InteractionProfileLoadError(
                f"`tool_families.{name}` is a compatibility alias in {source}; declare `exec_command` instead"
            )
        if name == mapping_runtime.COMMAND_EXECUTION_EVENT_PROJECTION_NAME:
            raise InteractionProfileLoadError(
                f"`tool_families.{name}` is an event projection in {source}; it must not be declared as a tool family"
            )
        item = _require_mapping(raw_item, field_name=f"tool_families.{name}", source=source)
        exposure = str(item.get("exposure") or "").strip()
        projection = str(item.get("projection") or "").strip()
        if not exposure:
            raise InteractionProfileLoadError(f"missing `exposure` for `tool_families.{name}` in {source}")
        if not projection:
            raise InteractionProfileLoadError(f"missing `projection` for `tool_families.{name}` in {source}")
        fallback_backend = str(item.get("fallback_backend") or "").strip()
        if projection == "native_if_available" and not fallback_backend:
            raise InteractionProfileLoadError(
                f"`tool_families.{name}` with `projection = native_if_available` requires `fallback_backend` in {source}"
            )
        derived = _derived_tool_family_contract(profile=profile, name=name)
        normalized[name] = InteractionToolFamilySpec(
            name=name,
            exposure=exposure,
            projection=projection,
            fallback_backend=fallback_backend,
            canonical_family=str(derived["canonical_family"] or name),
            projection_surface_family=str(derived["projection_surface_family"] or "identity"),
            projected_primary_tools=_normalized_tool_names(derived["projected_primary_tools"]),
            projected_continuation_tools=_normalized_tool_names(derived["projected_continuation_tools"]),
            compatibility_aliases=_normalized_tool_names(derived["compatibility_aliases"]),
            event_projection_name=str(derived["event_projection_name"] or "").strip(),
        )
    if not normalized:
        raise InteractionProfileLoadError(f"`tool_families` must not be empty in {source}")
    return normalized


def interaction_profile_spec_from_mapping(payload: Mapping[str, Any], *, source: str = "<memory>") -> InteractionProfileSpec:
    mapping = _require_mapping(payload, field_name="interaction_profile", source=source)
    unknown_keys = sorted(set(mapping.keys()) - _ALLOWED_TOP_LEVEL_KEYS)
    if unknown_keys:
        raise InteractionProfileLoadError(f"unknown top-level keys in {source}: {', '.join(unknown_keys)}")

    raw_schema_version = mapping.get("schema_version", 0)
    try:
        schema_version = int(raw_schema_version)
    except (TypeError, ValueError) as exc:
        raise InteractionProfileLoadError(f"invalid `schema_version` in {source}: {raw_schema_version!r}") from exc
    if schema_version < 1:
        raise InteractionProfileLoadError(f"`schema_version` must be >= 1 in {source}")

    text_fields = {key: _required_text(mapping, key, source=source) for key in _REQUIRED_TEXT_FIELDS}
    profile = text_fields["profile"]
    fallback_profile = text_fields["fallback_profile"]
    if fallback_profile == profile:
        raise InteractionProfileLoadError(f"`fallback_profile` must not equal `profile` in {source}")

    required_capabilities = _normalized_bool_mapping(
        mapping.get("required_capabilities"),
        field_name="required_capabilities",
        source=source,
    )
    optional_capabilities = _normalized_bool_mapping(
        mapping.get("optional_capabilities"),
        field_name="optional_capabilities",
        source=source,
    )
    tool_families = _normalized_tool_families(
        mapping.get("tool_families"),
        profile=profile,
        source=source,
    )

    selection_hints_raw = mapping.get("selection_hints") or {}
    selection_hints = dict(_require_mapping(selection_hints_raw, field_name="selection_hints", source=source))

    plugin_policy_raw = mapping.get("plugin_exposure_policy") or {}
    plugin_exposure_policy = dict(
        _require_mapping(plugin_policy_raw, field_name="plugin_exposure_policy", source=source)
    )

    return InteractionProfileSpec(
        schema_version=schema_version,
        profile=profile,
        display_name=text_fields["display_name"],
        base_prompt_profile=text_fields["base_prompt_profile"],
        tool_surface_profile=text_fields["tool_surface_profile"],
        context_prelude_policy=text_fields["context_prelude_policy"],
        tool_result_projection_policy=text_fields["tool_result_projection_policy"],
        continuation_policy=text_fields["continuation_policy"],
        turn_protocol_policy=text_fields["turn_protocol_policy"],
        required_capabilities=required_capabilities,
        optional_capabilities=optional_capabilities,
        tool_families=tool_families,
        fallback_profile=fallback_profile,
        selection_hints=selection_hints,
        plugin_exposure_policy=plugin_exposure_policy,
    )
