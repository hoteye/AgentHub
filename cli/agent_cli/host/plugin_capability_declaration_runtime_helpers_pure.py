from __future__ import annotations

import re
from typing import Any

_ALLOWED_KINDS: tuple[str, ...] = (
    "provider_tool",
    "mcp_server",
    "skill",
    "app_connector",
)
_ALLOWED_DEFAULT_VISIBILITY: tuple[str, ...] = (
    "model_visible",
    "host_only",
    "operator_only",
    "disabled",
)
_ALLOWED_PROFILE_IDS: tuple[str, ...] = (
    "codex_openai",
    "claude_code",
    "generic_chat",
)
_ALLOWED_MEDIA_KINDS: tuple[str, ...] = (
    "image",
    "document",
    "audio",
    "video",
    "binary",
)
_ALLOWED_MEDIA_INGEST_SEMANTICS: tuple[str, ...] = ("shared_media_ingest_v1",)
_ALLOWED_MEDIA_SOURCE_MODES: tuple[str, ...] = (
    "tool_path",
    "user_attachment",
    "hybrid",
)
_ALLOWED_MEDIA_PROJECTION_MODES: tuple[str, ...] = (
    "tool_native_continuation",
    "tool_result_content_block",
    "message_native_attachment",
)
_ALLOWED_TOOL_CAPABILITY_KINDS: tuple[str, ...] = (
    "local_runtime_tool",
    "provider_native_tool",
    "message_native_capability",
    "ui_only_capability",
)
_ALLOWED_TOOL_RUNTIME_BINDINGS: tuple[str, ...] = (
    "local_runtime",
    "provider_native",
    "shared_media_ingest",
    "plugin_runtime",
    "plugin_mcp_server",
    "plugin_app_connector",
)
_CANONICAL_FAMILY_PATTERN = re.compile(r"^[a-z0-9_][a-z0-9_.-]*$")


def declaration_runtime():
    from cli.agent_cli.host import plugin_capability_declaration as runtime

    return runtime


def value_with_aliases(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def normalize_required_text(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"missing required field `{field_name}`")
    return text


def normalize_optional_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_kind(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in _ALLOWED_KINDS:
        allowed = ", ".join(_ALLOWED_KINDS)
        raise ValueError(f"invalid `kind` {value!r}; expected one of: {allowed}")
    return normalized


def normalize_default_visibility(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in _ALLOWED_DEFAULT_VISIBILITY:
        allowed = ", ".join(_ALLOWED_DEFAULT_VISIBILITY)
        raise ValueError(f"invalid `default_visibility` {value!r}; expected one of: {allowed}")
    return normalized


def normalize_tool_capability_kind(value: Any, *, required: bool) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        if required:
            raise ValueError("missing required field `tool_capability_kind`")
        return ""
    if normalized not in _ALLOWED_TOOL_CAPABILITY_KINDS:
        allowed = ", ".join(_ALLOWED_TOOL_CAPABILITY_KINDS)
        raise ValueError(f"invalid `tool_capability_kind` {value!r}; expected one of: {allowed}")
    return normalized


def normalize_tool_runtime_binding(value: Any, *, required: bool) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        if required:
            raise ValueError("missing required field `tool_runtime_binding`")
        return ""
    if normalized not in _ALLOWED_TOOL_RUNTIME_BINDINGS:
        allowed = ", ".join(_ALLOWED_TOOL_RUNTIME_BINDINGS)
        raise ValueError(f"invalid `tool_runtime_binding` {value!r}; expected one of: {allowed}")
    return normalized


def normalize_supported_profiles(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("`supported_profiles` must be a list")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        profile = str(item or "").strip().lower()
        if not profile:
            continue
        if profile not in _ALLOWED_PROFILE_IDS:
            allowed = ", ".join(_ALLOWED_PROFILE_IDS)
            raise ValueError(f"unsupported profile {profile!r}; allowed: {allowed}")
        if profile in seen:
            continue
        seen.add(profile)
        normalized.append(profile)
    if not normalized:
        raise ValueError("`supported_profiles` cannot be empty")
    return tuple(normalized)


def normalize_media_kind(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in _ALLOWED_MEDIA_KINDS:
        allowed = ", ".join(_ALLOWED_MEDIA_KINDS)
        raise ValueError(f"invalid `media_kind` {value!r}; expected one of: {allowed}")
    return normalized


def normalize_media_ingest_semantics(value: Any) -> str:
    normalized = str(value or "shared_media_ingest_v1").strip().lower()
    if normalized not in _ALLOWED_MEDIA_INGEST_SEMANTICS:
        allowed = ", ".join(_ALLOWED_MEDIA_INGEST_SEMANTICS)
        raise ValueError(f"invalid `ingest_semantics` {value!r}; expected one of: {allowed}")
    return normalized


def normalize_media_mode_list(
    value: Any,
    *,
    field_name: str,
    allowed_values: tuple[str, ...],
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"`{field_name}` must be a list")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        mode = str(item or "").strip().lower()
        if not mode:
            continue
        if mode not in allowed_values:
            allowed = ", ".join(allowed_values)
            raise ValueError(f"invalid `{field_name}` item {item!r}; expected one of: {allowed}")
        if mode in seen:
            continue
        seen.add(mode)
        normalized.append(mode)
    return tuple(normalized)


def normalize_mime_types(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("`mime_types` must be a list")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        mime_text = str(item or "").strip().lower()
        if not mime_text:
            continue
        if mime_text in seen:
            continue
        seen.add(mime_text)
        normalized.append(mime_text)
    return tuple(normalized)


def normalize_max_size_bytes(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError("`max_size_bytes` must be an integer") from None
    if parsed <= 0:
        raise ValueError("`max_size_bytes` must be greater than 0")
    return parsed


def normalize_canonical_family_name(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        raise ValueError("missing required field `canonical_family`")
    if not _CANONICAL_FAMILY_PATTERN.match(normalized):
        raise ValueError(
            f"invalid `canonical_family` {value!r}; expected lowercase slug-like text without spaces"
        )
    return normalized
