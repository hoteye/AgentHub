from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

_STANDARD_REASONING_EFFORTS = ("low", "medium", "high", "xhigh")
_ANTHROPIC_REASONING_EFFORTS = ("low", "medium", "high")


def resolve_model_migration(
    selector: str,
    toml_data: Mapping[str, Any],
) -> str:
    token = str(selector or "").strip()
    if not token:
        return ""
    notice_block = toml_data.get("notice")
    if not isinstance(notice_block, Mapping):
        return token
    migrations = notice_block.get("model_migrations")
    if not isinstance(migrations, Mapping):
        return token
    current = token
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        migrated = str(migrations.get(current) or "").strip()
        if not migrated or migrated == current:
            break
        current = migrated
    return current or token


def read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_toml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8-sig"))


def optional_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def infer_planner_kind(
    provider_name: str, model: str, base_url: str | None, provider_block: dict[str, Any]
) -> str:
    explicit = (
        str(provider_block.get("planner") or provider_block.get("planner_kind") or "")
        .strip()
        .lower()
    )
    fingerprint = " ".join(filter(None, (provider_name, model, base_url or ""))).lower()
    if explicit:
        if "deepseek" in fingerprint and explicit in {"deepseek_chat", "deepseek_reasoner"}:
            return (
                "deepseek_reasoner" if "reasoner" in str(model or "").lower() else "deepseek_chat"
            )
        return explicit
    if "anthropic" in fingerprint or "claude" in fingerprint:
        return "anthropic_messages"
    if "deepseek" in fingerprint:
        if "reasoner" in str(model or "").lower():
            return "deepseek_reasoner"
        return "deepseek_chat"
    return "openai_responses"


def slugify_model_key(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", str(value or "").strip()).strip("_").lower()
    return text or "model"


def aliased_mapping_value(mapping: Mapping[str, Any], snake_key: str, camel_key: str) -> Any:
    if snake_key in mapping:
        return mapping.get(snake_key)
    if camel_key in mapping:
        return mapping.get(camel_key)
    return None


def normalized_reasoning_effort(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("reasoning_effort") or value.get("reasoningEffort")
    effort = str(value or "").strip().lower()
    if effort in _STANDARD_REASONING_EFFORTS:
        return effort
    return ""


def explicit_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def normalized_reasoning_efforts(value: Any) -> tuple[str, ...]:
    raw_items = value if isinstance(value, list | tuple | set) else [value]
    normalized: list[str] = []
    for raw_item in raw_items:
        effort = normalized_reasoning_effort(raw_item)
        if not effort or effort in normalized:
            continue
        normalized.append(effort)
    return tuple(normalized)


def reasoning_efforts_declared(value: Any) -> tuple[bool, tuple[str, ...]]:
    if isinstance(value, list | tuple | set):
        return True, normalized_reasoning_efforts(value)
    return False, normalized_reasoning_efforts(value)


def default_supports_reasoning_for_model(
    *,
    provider_name: str,
    model_id: str,
    supports_reasoning: Any = None,
    reasoning_mode: str = "",
    reasoning_output_field: str = "",
    supported_reasoning_efforts: Any = None,
    default_reasoning_effort: Any = None,
) -> bool:
    _, explicit_supported_reasoning_efforts = reasoning_efforts_declared(
        supported_reasoning_efforts
    )
    if explicit_supported_reasoning_efforts:
        return True
    if normalized_reasoning_effort(default_reasoning_effort):
        return True
    explicit_supports_reasoning = explicit_optional_bool(supports_reasoning)
    if explicit_supports_reasoning is not None:
        return explicit_supports_reasoning
    if str(reasoning_mode or "").strip() or str(reasoning_output_field or "").strip():
        return True
    normalized_provider = str(provider_name or "").strip().lower()
    normalized_model = str(model_id or "").strip().lower()
    if not normalized_model:
        return False
    if "anthropic" in normalized_provider or normalized_model.startswith("claude"):
        return "haiku" not in normalized_model
    if normalized_model.startswith("gpt-") or normalized_model.startswith("gpt-oss-"):
        return True
    if "reasoner" in normalized_model:
        return True
    return False


def supported_reasoning_efforts_for_model(
    *,
    provider_name: str,
    model_id: str,
    supports_reasoning: Any = None,
    reasoning_mode: str = "",
    reasoning_output_field: str = "",
    supported_reasoning_efforts: Any = None,
    default_reasoning_effort: Any = None,
    default_supports_reasoning_for_model_fn: Callable[
        ..., bool
    ] = default_supports_reasoning_for_model,
) -> tuple[str, ...]:
    explicit_supported_reasoning_efforts_declared, explicit_supported_reasoning_efforts = (
        reasoning_efforts_declared(supported_reasoning_efforts)
    )
    if explicit_supported_reasoning_efforts_declared:
        return explicit_supported_reasoning_efforts
    if not default_supports_reasoning_for_model_fn(
        provider_name=provider_name,
        model_id=model_id,
        supports_reasoning=supports_reasoning,
        reasoning_mode=reasoning_mode,
        reasoning_output_field=reasoning_output_field,
        supported_reasoning_efforts=supported_reasoning_efforts,
        default_reasoning_effort=default_reasoning_effort,
    ):
        return ()
    normalized_provider = str(provider_name or "").strip().lower()
    normalized_model = str(model_id or "").strip().lower()
    if "anthropic" in normalized_provider or normalized_model.startswith("claude"):
        return _ANTHROPIC_REASONING_EFFORTS
    if normalized_model.startswith("gpt-") or normalized_model.startswith("gpt-oss-"):
        return _STANDARD_REASONING_EFFORTS
    return _STANDARD_REASONING_EFFORTS


def default_reasoning_effort_for_model(
    *,
    provider_name: str,
    model_id: str,
    interaction_profile: str = "",
    planner_kind: str = "",
    wire_api: str = "",
    supports_reasoning: Any = None,
    reasoning_mode: str = "",
    reasoning_output_field: str = "",
    supported_reasoning_efforts: Any = None,
    default_reasoning_effort: Any = None,
    supported_reasoning_efforts_for_model_fn: Callable[
        ..., tuple[str, ...]
    ] = supported_reasoning_efforts_for_model,
) -> str:
    supported_efforts = supported_reasoning_efforts_for_model_fn(
        provider_name=provider_name,
        model_id=model_id,
        supports_reasoning=supports_reasoning,
        reasoning_mode=reasoning_mode,
        reasoning_output_field=reasoning_output_field,
        supported_reasoning_efforts=supported_reasoning_efforts,
        default_reasoning_effort=default_reasoning_effort,
    )
    explicit_default_reasoning_effort = normalized_reasoning_effort(default_reasoning_effort)
    if explicit_default_reasoning_effort and explicit_default_reasoning_effort in supported_efforts:
        return explicit_default_reasoning_effort
    normalized_provider = str(provider_name or "").strip().lower()
    normalized_model = str(model_id or "").strip().lower()
    normalized_interaction_profile = str(interaction_profile or "").strip().lower()
    normalized_planner_kind = str(planner_kind or "").strip().lower()
    normalized_wire_api = str(wire_api or "").strip().lower()
    provider_is_openai_like = (
        not normalized_provider
        or normalized_provider in {"openai", "reference"}
        or "openai" in normalized_provider
        or "reference" in normalized_provider
    )
    if (
        provider_is_openai_like
        and normalized_interaction_profile == "codex_openai"
        and normalized_model == "gpt-5.4"
        and normalized_planner_kind in {"", "openai_responses"}
        and normalized_wire_api in {"", "responses", "openai_responses"}
        and "xhigh" in supported_efforts
    ):
        return "xhigh"
    return ""


def reasoning_effort_supported_for_model(
    reasoning_effort: str,
    *,
    provider_name: str,
    model_id: str,
    interaction_profile: str = "",
    planner_kind: str = "",
    wire_api: str = "",
    supports_reasoning: Any = None,
    reasoning_mode: str = "",
    reasoning_output_field: str = "",
    supported_reasoning_efforts: Any = None,
    default_reasoning_effort: Any = None,
    supported_reasoning_efforts_for_model_fn: Callable[
        ..., tuple[str, ...]
    ] = supported_reasoning_efforts_for_model,
) -> bool:
    del interaction_profile, planner_kind, wire_api
    normalized_effort = normalized_reasoning_effort(reasoning_effort)
    if not normalized_effort:
        return False
    return normalized_effort in supported_reasoning_efforts_for_model_fn(
        provider_name=provider_name,
        model_id=model_id,
        supports_reasoning=supports_reasoning,
        reasoning_mode=reasoning_mode,
        reasoning_output_field=reasoning_output_field,
        supported_reasoning_efforts=supported_reasoning_efforts,
        default_reasoning_effort=default_reasoning_effort,
    )
