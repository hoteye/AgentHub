from __future__ import annotations

from typing import Any, Mapping


LEGACY_CODEX_PROFILE = "codex_openai"


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def normalize_interaction_profile(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = text.replace("-", "_")
    return text


def _explicit_profile_from_mapping(mapping: Mapping[str, Any], *, layer: str) -> tuple[str, str]:
    if "interaction_profile" not in mapping:
        return "", ""
    return normalize_interaction_profile(mapping.get("interaction_profile")), f"{layer}.interaction_profile"


def _legacy_profile_alias_from_mapping(mapping: Mapping[str, Any], *, layer: str) -> tuple[str, str]:
    for key in ("codex_parity", "reference_parity"):
        if key not in mapping:
            continue
        parsed = _optional_bool(mapping.get(key))
        if parsed is None:
            continue
        if parsed:
            return LEGACY_CODEX_PROFILE, f"{layer}.{key}"
        return "", f"{layer}.{key}"
    return "", ""


def resolve_configured_interaction_profile(
    *,
    raw_model: Mapping[str, Any] | None,
    raw_provider: Mapping[str, Any] | None,
) -> tuple[str, str]:
    model_mapping = raw_model or {}
    provider_mapping = raw_provider or {}

    for mapping, layer in ((model_mapping, "model"), (provider_mapping, "provider")):
        explicit_profile, explicit_source = _explicit_profile_from_mapping(mapping, layer=layer)
        if explicit_source:
            return explicit_profile, explicit_source
        legacy_profile, legacy_source = _legacy_profile_alias_from_mapping(mapping, layer=layer)
        if legacy_source:
            return legacy_profile, legacy_source

    return "", ""
