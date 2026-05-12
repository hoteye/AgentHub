from __future__ import annotations

import os
import uuid
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from cli.agent_cli.providers.config_catalog import ProviderConfig, optional_bool

_CODEX_OPENAI_PROFILE = "codex_openai"
_CLAUDE_CODE_PROFILE = "claude_code"
_PROMPTS_ROOT = Path(__file__).resolve().parent.parent / "prompts" / "reference_parity"
_REFERENCE_BASE_PROMPT_CANDIDATES = (
    _PROMPTS_ROOT / "base_instructions" / "default.md",
    Path("/tmp/reference_install_capture/base_instructions.txt"),
)
_CLAUDE_CODE_BASE_PROMPT_CANDIDATES = (
    _PROMPTS_ROOT / "claude_code_prompts" / "core_instructions.md",
)
_REFERENCE_APPLY_PATCH_GRAMMAR_CANDIDATES = (
    _PROMPTS_ROOT / "tools" / "handlers" / "tool_apply_patch.lark",
)
#
# Frozen snapshot from codex_ref `codex debug models` on 2026-04-25.
# Keep runtime deterministic; refresh explicitly when codex_ref updates.
# Slugs absent from the snapshot must follow codex_ref unknown-model fallback
# metadata rather than being guessed into the table.
_DEFAULT_REFERENCE_INPUT_MODALITIES: tuple[str, ...] = ("text", "image")
_CODEX_REFERENCE_MODEL_CAPABILITIES: tuple[
    tuple[str, str | None, tuple[str, ...], bool, str | None], ...
] = (
    ("gpt-5.5", "freeform", ("text", "image"), True, "low"),
    ("gpt-5.4", "freeform", ("text", "image"), True, "low"),
    ("gpt-5.4-mini", "freeform", ("text", "image"), True, "medium"),
    ("gpt-5.3-codex", "freeform", ("text", "image"), True, "low"),
    ("gpt-5.2-codex", "freeform", ("text", "image"), False, None),
    ("gpt-5.1-codex-max", "freeform", ("text", "image"), False, None),
    ("gpt-5.1-codex", "freeform", ("text", "image"), False, None),
    ("gpt-5.2", "freeform", ("text", "image"), False, None),
    ("gpt-5.1", "freeform", ("text", "image"), False, None),
    ("gpt-5-codex", "freeform", ("text", "image"), False, None),
    ("gpt-5", None, ("text", "image"), False, None),
    ("gpt-oss-120b", "freeform", ("text",), False, None),
    ("gpt-oss-20b", "freeform", ("text",), False, None),
    ("gpt-5.1-codex-mini", "freeform", ("text", "image"), False, None),
    ("gpt-5-codex-mini", "freeform", ("text", "image"), False, None),
)
_VALID_REFERENCE_VERBOSITY = {"low", "medium", "high"}
_CODEX_INSTALLATION_ID_CLIENT_METADATA_KEY = "x-codex-installation-id"


def _explicit_bool(mapping: Mapping[str, Any], key: str) -> bool | None:
    if key not in mapping:
        return None
    return optional_bool(mapping.get(key), False)


def _explicit_text(mapping: Mapping[str, Any], key: str) -> str | None:
    if key not in mapping:
        return None
    value = str(mapping.get(key) or "").strip()
    return value if value else ""


def _raw_mappings(config: ProviderConfig) -> tuple[dict[str, Any], dict[str, Any]]:
    return dict(config.raw_model or {}), dict(config.raw_provider or {})


def _reference_model_slug_candidates(model_slug: str) -> tuple[str, ...]:
    normalized = str(model_slug or "").strip().lower()
    if not normalized:
        return ()
    candidates = [normalized]
    if "/" in normalized:
        suffix = normalized.rsplit("/", 1)[-1].strip()
        if suffix and suffix != normalized:
            candidates.append(suffix)
    return tuple(candidates)


def _matches_reference_model_prefix(candidate: str, prefix: str) -> bool:
    if candidate == prefix:
        return True
    for separator in ("-", "."):
        if candidate.startswith(prefix + separator):
            return True
    return False


def _normalized_input_modalities(value: Any) -> tuple[str, ...] | None:
    raw_values: list[str]
    if isinstance(value, str):
        raw_values = [part.strip().lower() for part in value.replace(",", " ").split()]
    elif isinstance(value, list | tuple | set):
        raw_values = [str(part or "").strip().lower() for part in value]
    else:
        return None
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        if item not in {"text", "image"} or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return tuple(normalized)


def _normalized_string_list(value: Any) -> tuple[str, ...] | None:
    raw_values: list[str]
    if isinstance(value, str):
        raw_values = [part.strip().lower() for part in value.replace(",", " ").split()]
    elif isinstance(value, list | tuple | set):
        raw_values = [str(part or "").strip().lower() for part in value]
    else:
        return None
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return tuple(normalized)


def _reference_model_capability_for_model(
    model_slug: str,
) -> tuple[str, str | None, tuple[str, ...], bool, str | None] | None:
    for candidate in _reference_model_slug_candidates(model_slug):
        for (
            prefix,
            tool_type,
            input_modalities,
            supports_original_detail,
            default_verbosity,
        ) in _CODEX_REFERENCE_MODEL_CAPABILITIES:
            if _matches_reference_model_prefix(candidate, prefix):
                return (
                    prefix,
                    tool_type,
                    input_modalities,
                    supports_original_detail,
                    default_verbosity,
                )
    return None


def reference_parity_enabled(config: ProviderConfig) -> bool:
    raw_model, raw_provider = _raw_mappings(config)
    for mapping in (raw_model, raw_provider):
        explicit = _explicit_bool(mapping, "reference_parity")
        if explicit is not None:
            return explicit
    return False


def _first_existing_text(paths: tuple[Path, ...]) -> str:
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if text.strip():
            return text
    raise FileNotFoundError(f"missing Reference parity reference file in: {paths}")


@lru_cache(maxsize=1)
def load_reference_base_prompt() -> str:
    return _first_existing_text(_REFERENCE_BASE_PROMPT_CANDIDATES)


@lru_cache(maxsize=1)
def load_claude_code_base_prompt() -> str:
    return _first_existing_text(_CLAUDE_CODE_BASE_PROMPT_CANDIDATES)


@lru_cache(maxsize=1)
def load_reference_apply_patch_grammar() -> str:
    return _first_existing_text(_REFERENCE_APPLY_PATCH_GRAMMAR_CANDIDATES)


def _resolved_tool_surface_profile(config: ProviderConfig) -> str:
    try:
        from cli.agent_cli.providers.interaction_profile_compat_runtime import (
            resolved_tool_surface_profile_for_config,
        )

        return str(resolved_tool_surface_profile_for_config(config) or "").strip().lower()
    except Exception:
        return ""


def _configured_or_resolved_tool_surface_profile(config: ProviderConfig) -> str:
    try:
        from cli.agent_cli.providers.interaction_profile_compat_runtime import (
            configured_interaction_profile_for_config,
        )

        configured_profile, _ = configured_interaction_profile_for_config(config)
        if configured_profile:
            return str(configured_profile or "").strip().lower()
    except Exception:
        pass
    return _resolved_tool_surface_profile(config)


def reference_default_mode_request_user_input(config: ProviderConfig) -> bool:
    raw_model, raw_provider = _raw_mappings(config)
    for mapping in (raw_model, raw_provider):
        for key in ("default_mode_request_user_input", "reference_default_mode_request_user_input"):
            explicit = _explicit_bool(mapping, key)
            if explicit is not None:
                return explicit
    if _configured_or_resolved_tool_surface_profile(config) == _CLAUDE_CODE_PROFILE:
        return True
    return False


def reference_collab_tools_enabled(config: ProviderConfig) -> bool:
    raw_model, raw_provider = _raw_mappings(config)
    for mapping in (raw_model, raw_provider):
        for key in ("collab_tools", "reference_collab_tools"):
            explicit = _explicit_bool(mapping, key)
            if explicit is not None:
                return explicit
    if _configured_or_resolved_tool_surface_profile(config) == _CODEX_OPENAI_PROFILE:
        return True
    return False


def reference_request_permission_enabled(config: ProviderConfig) -> bool:
    raw_model, raw_provider = _raw_mappings(config)
    for mapping in (raw_model, raw_provider):
        for key in (
            "request_permission_enabled",
            "request_permissions_enabled",
            "reference_request_permission_enabled",
        ):
            explicit = _explicit_bool(mapping, key)
            if explicit is not None:
                return explicit
    return False


def reference_apply_patch_tool_type(config: ProviderConfig) -> str | None:
    raw_model, raw_provider = _raw_mappings(config)
    for mapping in (raw_model, raw_provider):
        for key in ("apply_patch_tool_type", "reference_apply_patch_tool_type"):
            explicit = _explicit_text(mapping, key)
            if explicit is None:
                continue
            normalized = explicit.strip().lower()
            if normalized in {"freeform", "function"}:
                return normalized
            if normalized in {"", "none", "null", "disabled", "false", "off"}:
                return None
    for mapping in (raw_model, raw_provider):
        for key in (
            "include_apply_patch_tool",
            "experimental_use_freeform_apply_patch",
            "apply_patch_freeform",
            "reference_apply_patch",
        ):
            explicit = _explicit_bool(mapping, key)
            if explicit is not None:
                return "freeform" if explicit else None
    tool_surface_profile = _resolved_tool_surface_profile(config)
    model_slug = str(getattr(config, "model", "") or "").strip().lower()
    if tool_surface_profile == _CODEX_OPENAI_PROFILE:
        capability = _reference_model_capability_for_model(model_slug)
        if capability is not None:
            return capability[1]
    return None


def reference_view_image_input_capable(config: ProviderConfig) -> bool:
    raw_model, raw_provider = _raw_mappings(config)
    for mapping in (raw_model, raw_provider):
        for key in ("view_image_input_capable", "reference_view_image_input_capable"):
            explicit = _explicit_bool(mapping, key)
            if explicit is not None:
                return explicit
        for key in ("input_modalities", "reference_input_modalities"):
            modalities = _normalized_input_modalities(mapping.get(key)) if key in mapping else None
            if modalities is not None:
                return "image" in modalities
    if _resolved_tool_surface_profile(config) == _CODEX_OPENAI_PROFILE:
        model_slug = str(getattr(config, "model", "") or "").strip().lower()
        capability = _reference_model_capability_for_model(model_slug)
        if capability is not None:
            return "image" in capability[2]
        return "image" in _DEFAULT_REFERENCE_INPUT_MODALITIES
    return True


def reference_view_image_detail(config: ProviderConfig) -> str | None:
    raw_model, raw_provider = _raw_mappings(config)
    for mapping in (raw_model, raw_provider):
        for key in ("view_image_detail", "reference_view_image_detail"):
            explicit = _explicit_text(mapping, key)
            if explicit is None:
                continue
            normalized = str(explicit or "").strip().lower()
            return "original" if normalized == "original" else None
        for key in ("supports_image_detail_original", "reference_supports_image_detail_original"):
            explicit = _explicit_bool(mapping, key)
            if explicit is not None:
                return (
                    "original" if explicit and reference_view_image_input_capable(config) else None
                )
    if not reference_view_image_input_capable(config):
        return None
    if _resolved_tool_surface_profile(config) == _CODEX_OPENAI_PROFILE:
        model_slug = str(getattr(config, "model", "") or "").strip().lower()
        capability = _reference_model_capability_for_model(model_slug)
        if capability is not None and capability[3]:
            return "original"
    return None


def reference_default_text_verbosity_for_model(model_slug: str) -> str | None:
    capability = _reference_model_capability_for_model(model_slug)
    if capability is None:
        return None
    verbosity = str(capability[4] or "").strip().lower()
    return verbosity if verbosity in _VALID_REFERENCE_VERBOSITY else None


def reference_text_verbosity(config: ProviderConfig) -> str | None:
    raw_model, raw_provider = _raw_mappings(config)
    for mapping in (raw_model, raw_provider):
        for key in (
            "model_verbosity",
            "text_verbosity",
            "verbosity",
            "reference_model_verbosity",
            "reference_text_verbosity",
        ):
            explicit = _explicit_text(mapping, key)
            if explicit is None:
                continue
            normalized = explicit.strip().lower()
            return normalized if normalized in _VALID_REFERENCE_VERBOSITY else None
    if _resolved_tool_surface_profile(config) == _CODEX_OPENAI_PROFILE:
        return reference_default_text_verbosity_for_model(str(getattr(config, "model", "") or ""))
    return None


def reference_reasoning_summary(config: ProviderConfig) -> str | None:
    raw_model, raw_provider = _raw_mappings(config)
    for mapping in (raw_model, raw_provider):
        for key in (
            "reasoning_summary",
            "model_reasoning_summary",
            "reference_reasoning_summary",
        ):
            explicit = _explicit_text(mapping, key)
            if explicit is None:
                continue
            normalized = explicit.strip().lower()
            if normalized in {"", "none", "null", "disabled", "false", "off"}:
                return None
            if normalized in {"auto", "concise", "detailed"}:
                return normalized
    return None


def _codex_installation_id_path() -> Path:
    configured_home = str(os.environ.get("AGENT_CLI_HOME") or "").strip()
    home = Path(configured_home).expanduser() if configured_home else Path.home() / ".agent_cli"
    return home / "codex_installation_id"


def _read_or_create_codex_installation_id() -> str:
    path = _codex_installation_id_path()
    try:
        existing = path.read_text(encoding="utf-8").strip()
    except OSError:
        existing = ""
    if existing:
        return existing
    generated = uuid.uuid4().hex
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(generated + "\n", encoding="utf-8")
    except OSError:
        return generated
    return generated


def reference_codex_installation_id(config: ProviderConfig) -> str:
    raw_model, raw_provider = _raw_mappings(config)
    for mapping in (raw_model, raw_provider):
        for key in (
            "codex_installation_id",
            "reference_codex_installation_id",
            "installation_id",
        ):
            explicit = _explicit_text(mapping, key)
            if explicit is not None and explicit.strip():
                return explicit.strip()
    for key in ("AGENTHUB_CODEX_INSTALLATION_ID", "CODEX_INSTALLATION_ID"):
        value = str(os.environ.get(key) or "").strip()
        if value:
            return value
    return _read_or_create_codex_installation_id()


def reference_client_metadata(config: ProviderConfig) -> dict[str, str]:
    if _configured_or_resolved_tool_surface_profile(config) != _CODEX_OPENAI_PROFILE:
        return {}
    installation_id = reference_codex_installation_id(config)
    if not installation_id:
        return {}
    return {_CODEX_INSTALLATION_ID_CLIENT_METADATA_KEY: installation_id}


def reference_web_search_external_web_access(config: ProviderConfig) -> bool:
    raw_model, raw_provider = _raw_mappings(config)
    requested_mode: str | None = None
    for mapping in (raw_model, raw_provider):
        for key in (
            "reference_web_search_external_web_access",
            "web_search_external_web_access",
            "external_web_access",
            "reference_web_search_live",
            "web_search_live",
        ):
            explicit = _explicit_bool(mapping, key)
            if explicit is not None:
                requested_mode = "live" if explicit else "cached"
                break
        if requested_mode is not None:
            break
        for key in ("web_search_mode", "reference_web_search_mode"):
            explicit_mode = _explicit_text(mapping, key)
            if explicit_mode is None:
                continue
            normalized_mode = explicit_mode.strip().lower()
            if normalized_mode in {"live", "cached", "disabled"}:
                requested_mode = normalized_mode
                break
        if requested_mode is not None:
            break
    if requested_mode is None:
        return False
    sandbox_mode = ""
    for mapping in (raw_model, raw_provider):
        explicit_sandbox = _explicit_text(mapping, "sandbox_mode")
        if explicit_sandbox is None:
            continue
        normalized_sandbox = explicit_sandbox.strip().lower()
        if normalized_sandbox in {"read-only", "workspace-write", "danger-full-access"}:
            sandbox_mode = normalized_sandbox
            break
    effective_mode = requested_mode
    if sandbox_mode == "danger-full-access" and requested_mode != "disabled":
        effective_mode = "live"
    return effective_mode == "live"


def reference_experimental_supported_tools(config: ProviderConfig) -> tuple[str, ...]:
    raw_model, raw_provider = _raw_mappings(config)
    for mapping in (raw_model, raw_provider):
        for key in ("experimental_supported_tools", "reference_experimental_supported_tools"):
            if key not in mapping:
                continue
            normalized = _normalized_string_list(mapping.get(key))
            if normalized is not None:
                return normalized
    return ()


def reference_supports_experimental_tool(config: ProviderConfig, tool_name: str) -> bool:
    normalized_tool_name = str(tool_name or "").strip().lower()
    if not normalized_tool_name:
        return False
    return normalized_tool_name in set(reference_experimental_supported_tools(config))
