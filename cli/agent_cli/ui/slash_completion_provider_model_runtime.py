from __future__ import annotations

import re
from typing import Any

from cli.agent_cli.providers import availability_projection as provider_availability_projection


def current_provider_name(runtime: Any) -> str | None:
    tokens = current_provider_tokens(runtime)
    return next(iter(tokens), None)


def current_provider_tokens(runtime: Any) -> tuple[str, ...]:
    status_getter = getattr(getattr(runtime, "agent", None), "provider_status", None)
    if not callable(status_getter):
        return ()
    try:
        status = dict(status_getter() or {})
    except Exception:
        return ()
    candidates = (
        status.get("effective_provider_name"),
        status.get("provider_public_name"),
        status.get("provider_name"),
        status.get("provider_route_name"),
    )
    return _ordered_non_empty_tokens(candidates)


def current_model_tokens(runtime: Any) -> tuple[str, ...]:
    status_getter = getattr(getattr(runtime, "agent", None), "provider_status", None)
    if not callable(status_getter):
        return ()
    try:
        status = dict(status_getter() or {})
    except Exception:
        return ()
    candidates = (
        status.get("effective_model_key"),
        status.get("model_key"),
        status.get("effective_model"),
        status.get("provider_model"),
    )
    return _ordered_non_empty_tokens(candidates)


def model_name_matches_current(runtime: Any, model_name: str) -> bool:
    return _candidate_matches_current((model_name,), current_model_tokens(runtime))


def current_reasoning_effort_tokens(runtime: Any) -> tuple[str, ...]:
    status_getter = getattr(getattr(runtime, "agent", None), "provider_status", None)
    if not callable(status_getter):
        return ()
    try:
        status = dict(status_getter() or {})
    except Exception:
        return ()
    candidates = (
        status.get("effective_reasoning_effort"),
        status.get("current_reasoning_effort"),
        status.get("provider_reasoning_effort"),
        status.get("reasoning_effort"),
    )
    return _ordered_non_empty_tokens(candidates)


def _ordered_non_empty_tokens(values: Any) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text == "-":
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(text)
    return tuple(ordered)


def _normalized_token_set(tokens: tuple[str, ...]) -> set[str]:
    normalized: set[str] = set()
    for token in tokens:
        text = str(token or "").strip().lower()
        if not text:
            continue
        normalized.update(_token_variants(text))
    return normalized


def _candidate_matches_current(candidate_values: Any, current_tokens: tuple[str, ...]) -> bool:
    current = _normalized_token_set(current_tokens)
    if not current:
        return False
    for value in candidate_values:
        text = str(value or "").strip().lower()
        if not text:
            continue
        if _token_variants(text) & current:
            return True
    return False


def _token_variants(text: str) -> set[str]:
    value = str(text or "").strip().lower()
    if not value:
        return set()
    return {
        value,
        value.replace("_", "-"),
        re.sub(r"[^a-z0-9]+", "_", value).strip("_"),
        re.sub(r"[^a-z0-9]+", "", value),
    }


def available_provider_names(runtime: Any) -> list[str]:
    getter = getattr(getattr(runtime, "agent", None), "available_providers", None)
    if not callable(getter):
        return []
    try:
        items = list(getter() or [])
    except Exception:
        return []
    names: list[str] = []
    seen: set[str] = set()
    current_tokens = current_provider_tokens(runtime)
    provider_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        candidate = str(
            item.get("provider_name")
            or item.get("display_name")
            or item.get("config_provider_name")
            or ""
        ).strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        provider_items.append({**dict(item), "_candidate_name": candidate})
    provider_items.sort(
        key=lambda item: (
            0
            if _candidate_matches_current(
                (
                    item.get("provider_name"),
                    item.get("display_name"),
                    item.get("config_provider_name"),
                    item.get("_candidate_name"),
                ),
                current_tokens,
            )
            else 1
        )
    )
    for item in provider_items:
        names.append(str(item.get("_candidate_name") or "").strip())
    return names


def available_model_names(runtime: Any, provider_name: str | None = None) -> list[str]:
    items = available_model_items(runtime, provider_name=provider_name)
    names: list[str] = []
    seen: set[str] = set()
    for item in items:
        candidate = str(
            item.get("model_key") or item.get("display_name") or item.get("model_id") or ""
        ).strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        names.append(candidate)
    return names


def reasoning_effort_names_for_model(
    runtime: Any,
    model_name: str,
    *,
    provider_name: str | None = None,
    fallback: tuple[str, ...] = (),
) -> list[str]:
    selected_model = str(model_name or "").strip()
    if not selected_model:
        return list(fallback)
    for item in available_model_items(runtime, provider_name=provider_name):
        if not _candidate_matches_current(
            (
                item.get("model_key"),
                item.get("display_name"),
                item.get("model_id"),
            ),
            (selected_model,),
        ):
            continue
        efforts = _ordered_non_empty_tokens(
            item.get("supported_reasoning_efforts") or item.get("supportedReasoningEfforts") or ()
        )
        if efforts:
            return list(efforts)
        default_effort = _ordered_non_empty_tokens(
            (
                item.get("default_reasoning_effort"),
                item.get("defaultReasoningEffort"),
            )
        )
        if default_effort:
            return list(default_effort)
        return list(fallback)
    return list(fallback)


def default_reasoning_effort_tokens_for_model(
    runtime: Any,
    model_name: str,
    *,
    provider_name: str | None = None,
) -> tuple[str, ...]:
    selected_model = str(model_name or "").strip()
    if not selected_model:
        return ()
    for item in available_model_items(runtime, provider_name=provider_name):
        if not _candidate_matches_current(
            (
                item.get("model_key"),
                item.get("display_name"),
                item.get("model_id"),
            ),
            (selected_model,),
        ):
            continue
        return _ordered_non_empty_tokens(
            (
                item.get("default_reasoning_effort"),
                item.get("defaultReasoningEffort"),
            )
        )
    return ()


def available_model_items(runtime: Any, provider_name: str | None = None) -> list[dict[str, Any]]:
    getter = getattr(getattr(runtime, "agent", None), "available_models", None)
    if not callable(getter):
        return []
    try:
        items = list(getter(provider_name=provider_name) or [])
    except TypeError:
        try:
            items = list(getter(provider_name) or [])
        except Exception:
            return []
    except Exception:
        return []
    normalized_items: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    current_tokens = current_model_tokens(runtime)
    for item in items:
        if not isinstance(item, dict):
            continue
        model_key = str(
            item.get("model_key") or item.get("display_name") or item.get("model_id") or ""
        ).strip()
        model_id = str(item.get("model_id") or "").strip()
        config_provider_name = str(
            item.get("config_provider_name") or item.get("provider_name") or ""
        ).strip()
        dedupe_key = (config_provider_name, model_key, model_id)
        if not model_key or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized_items.append(dict(item))
    normalized_items.sort(
        key=lambda item: (
            0
            if _candidate_matches_current(
                (
                    item.get("model_key"),
                    item.get("display_name"),
                    item.get("model_id"),
                ),
                current_tokens,
            )
            else 1
        )
    )
    return normalized_items


def current_slash_arg_selection_index(
    runtime: Any,
    *,
    command_name: str,
    matches: list[dict[str, str]],
    current_tokens: tuple[str, ...] | None = None,
) -> int:
    if current_tokens is None:
        normalized_command = str(command_name or "").strip().lower()
        if normalized_command == "provider":
            current_tokens = current_provider_tokens(runtime)
        elif normalized_command == "model":
            current_tokens = current_model_tokens(runtime)
        else:
            return 0
    if not current_tokens:
        return 0
    for index, item in enumerate(list(matches or [])):
        name = str(item.get("name") or "").strip()
        name_tail = name.split(":", 1)[1] if ":" in name else name
        if _candidate_matches_current(
            (
                item.get("usage"),
                item.get("replacement"),
                name_tail,
            ),
            current_tokens,
        ):
            return index
    return 0


def model_availability_hint(runtime: Any, model_item: dict[str, Any]) -> str:
    owner = getattr(runtime, "agent", None) or runtime
    registry = provider_availability_projection.get_availability_registry(owner)
    provider_name = str(
        model_item.get("config_provider_name")
        or model_item.get("provider_name")
        or current_provider_name(runtime)
        or ""
    ).strip()
    model = str(
        model_item.get("model_id")
        or model_item.get("model_key")
        or model_item.get("display_name")
        or ""
    ).strip()
    fields = provider_availability_projection.availability_surface_fields(
        registry,
        provider_name=provider_name,
        model=model,
    )
    status = str(fields.get("availability_status") or "unknown").strip().lower() or "unknown"
    if status == "available":
        latency_ms = fields.get("availability_avg_latency_ms")
        if latency_ms in (None, ""):
            latency_ms = fields.get("availability_last_latency_ms")
        if latency_ms not in (None, ""):
            return f"availability: available, avg {int(latency_ms)}ms"
        return "availability: available"
    if status == "unavailable":
        failure_code = str(fields.get("availability_failure_code") or "").strip().replace("_", " ")
        retry_after_seconds = fields.get("availability_retry_after_seconds")
        if retry_after_seconds not in (None, ""):
            return f"availability: unavailable, retry {int(retry_after_seconds)}s"
        if failure_code:
            return f"availability: unavailable, {failure_code}"
        return "availability: unavailable"
    return "availability: unknown"
