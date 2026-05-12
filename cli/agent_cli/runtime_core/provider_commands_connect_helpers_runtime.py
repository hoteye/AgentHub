from __future__ import annotations

import re
from typing import Callable, Mapping
from urllib.parse import urlparse


def slugify_model_key(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", str(value or "").strip()).strip("_").lower()
    return text or "model"


def provider_profile_name(provider_name: str, *, base_url: str = "") -> str:
    provider_slug = slugify_model_key(provider_name)
    normalized_base_url = str(base_url or "").strip()
    endpoint = ""
    if normalized_base_url:
        parsed = urlparse(normalized_base_url)
        endpoint = "/".join(
            part
            for part in (
                str(parsed.netloc or "").strip(),
                str(parsed.path or "").strip().strip("/"),
            )
            if part
        )
    endpoint_slug = re.sub(r"[^a-zA-Z0-9]+", "_", endpoint).strip("_").lower()
    if endpoint_slug:
        return f"{provider_slug}_{endpoint_slug}"
    return f"{provider_slug}_main"


def upsert_provider_base_url(
    existing: str,
    *,
    provider_name: str,
    base_url: str,
    quoted_toml_string_fn: Callable[[str], str],
) -> str:
    normalized_provider = str(provider_name or "").strip()
    normalized_url = str(base_url or "").strip()
    if not normalized_provider or not normalized_url:
        return existing
    section_pattern = re.compile(rf"(?ms)^\[model_providers\.{re.escape(normalized_provider)}\]\s*\n(.*?)(?=^\[|\Z)")
    line = f"base_url = {quoted_toml_string_fn(normalized_url)}"
    match = section_pattern.search(existing)
    if match is None:
        block = f"[model_providers.{normalized_provider}]\n{line}\n"
        prefix = existing.rstrip()
        if prefix:
            prefix += "\n\n"
        return prefix + block
    body = match.group(1)
    body_pattern = re.compile(r"(?m)^base_url\s*=.*$")
    if body_pattern.search(body):
        updated_body = body_pattern.sub(line, body, count=1)
    else:
        updated_body = body.rstrip("\n")
        if updated_body:
            updated_body += "\n"
        updated_body += f"{line}\n"
    start, end = match.span(1)
    return existing[:start] + updated_body + existing[end:]


def clear_provider_fields(
    existing: str,
    *,
    provider_name: str,
    keys: tuple[str, ...] | list[str],
) -> str:
    normalized_provider = str(provider_name or "").strip()
    normalized_keys = [str(key or "").strip() for key in list(keys or ()) if str(key or "").strip()]
    if not normalized_provider or not normalized_keys:
        return existing
    section_pattern = re.compile(rf"(?ms)^\[model_providers\.{re.escape(normalized_provider)}\]\s*\n(.*?)(?=^\[|\Z)")
    match = section_pattern.search(existing)
    if match is None:
        return existing
    body = match.group(1)
    updated_body = body
    for key in normalized_keys:
        key_pattern = re.compile(rf"(?m)^{re.escape(key)}\s*=.*(?:\n)?")
        updated_body = key_pattern.sub("", updated_body)
    updated_body = re.sub(r"(?m)\A\n+", "", updated_body)
    updated_body = re.sub(r"\n{3,}", "\n\n", updated_body)
    start, end = match.span(1)
    return existing[:start] + updated_body + existing[end:]


def upsert_provider_auth_fields(
    existing: str,
    *,
    provider_name: str,
    auth_mode: str,
    api_key_env: str,
    quoted_toml_string_fn: Callable[[str], str],
) -> str:
    normalized_provider = str(provider_name or "").strip()
    normalized_mode = str(auth_mode or "").strip().lower()
    if not normalized_provider or not normalized_mode:
        return existing
    section_pattern = re.compile(rf"(?ms)^\[model_providers\.{re.escape(normalized_provider)}\]\s*\n(.*?)(?=^\[|\Z)")
    lines = [f"auth_mode = {quoted_toml_string_fn(normalized_mode)}"]
    if normalized_mode == "api_key" and str(api_key_env or "").strip():
        lines.append(f"api_key_env = {quoted_toml_string_fn(str(api_key_env).strip())}")
    match = section_pattern.search(existing)
    if match is None:
        block = f"[model_providers.{normalized_provider}]\n" + "\n".join(lines) + "\n"
        prefix = existing.rstrip()
        if prefix:
            prefix += "\n\n"
        return prefix + block
    body = match.group(1)
    updated_body = body
    for line in lines:
        key = line.split("=", 1)[0].strip()
        key_pattern = re.compile(rf"(?m)^{re.escape(key)}\s*=.*$")
        if key_pattern.search(updated_body):
            updated_body = key_pattern.sub(line, updated_body, count=1)
        else:
            updated_body = updated_body.rstrip("\n")
            if updated_body:
                updated_body += "\n"
            updated_body += line + "\n"
    start, end = match.span(1)
    return existing[:start] + updated_body + existing[end:]


def upsert_model_entry(
    existing: str,
    *,
    provider_name: str,
    model_selector: str,
    quoted_toml_string_fn: Callable[[str], str],
) -> str:
    model_key = slugify_model_key(model_selector)
    section_pattern = re.compile(rf"(?ms)^\[models\.{re.escape(model_key)}\]\s*\n(.*?)(?=^\[|\Z)")
    lines = [
        f"provider = {quoted_toml_string_fn(provider_name)}",
        f"model_id = {quoted_toml_string_fn(model_selector)}",
    ]
    match = section_pattern.search(existing)
    if match is None:
        block = f"[models.{model_key}]\n" + "\n".join(lines) + "\n"
        prefix = existing.rstrip()
        if prefix:
            prefix += "\n\n"
        return prefix + block
    body = match.group(1)
    updated_body = body
    for line in lines:
        key = line.split("=", 1)[0].strip()
        key_pattern = re.compile(rf"(?m)^{re.escape(key)}\s*=.*$")
        if key_pattern.search(updated_body):
            updated_body = key_pattern.sub(line, updated_body, count=1)
        else:
            updated_body = updated_body.rstrip("\n")
            if updated_body:
                updated_body += "\n"
            updated_body += line + "\n"
    start, end = match.span(1)
    return existing[:start] + updated_body + existing[end:]


def connect_provider_defaults(
    provider_name: str,
    *,
    official_provider_defaults: Mapping[str, Mapping[str, str]],
) -> dict[str, str]:
    normalized = str(provider_name or "").strip().lower()
    defaults = official_provider_defaults.get(normalized)
    return dict(defaults or {})


def resolved_connect_auth_mode(
    *,
    provider_name: str,
    auth_mode: str,
    official_provider_defaults: Mapping[str, Mapping[str, str]],
) -> str:
    normalized = str(auth_mode or "").strip().lower()
    if normalized:
        return normalized
    return connect_provider_defaults(
        provider_name,
        official_provider_defaults=official_provider_defaults,
    ).get("auth_mode", "")


def resolved_connect_api_key_env(
    *,
    provider_name: str,
    auth_mode: str,
    api_key_env: str,
    official_provider_defaults: Mapping[str, Mapping[str, str]],
) -> str:
    normalized = str(api_key_env or "").strip()
    if normalized:
        return normalized
    if str(auth_mode or "").strip().lower() != "api_key":
        return ""
    return connect_provider_defaults(
        provider_name,
        official_provider_defaults=official_provider_defaults,
    ).get("api_key_env", "")


def connect_requires_base_url(
    provider_name: str,
    *,
    official_provider_defaults: Mapping[str, Mapping[str, str]],
) -> bool:
    return not bool(
        connect_provider_defaults(
            provider_name,
            official_provider_defaults=official_provider_defaults,
        )
    )


def connect_next_action_hint(
    *,
    provider_name: str,
    model_selector: str,
    base_url: str,
    auth_mode: str,
    api_key_env: str,
    write_scope: str,
    official_provider_defaults: Mapping[str, Mapping[str, str]],
) -> str:
    parts = ["/connect"]
    parts.append(f"provider {provider_name or '<name>'}")
    parts.append(f"model {model_selector or '<selector>'}")
    has_defaults = bool(
        connect_provider_defaults(
            provider_name,
            official_provider_defaults=official_provider_defaults,
        )
    )
    explicit_auth_mode = str(auth_mode or "").strip().lower()
    explicit_api_key_env = str(api_key_env or "").strip()
    resolved_auth_mode_value = resolved_connect_auth_mode(
        provider_name=provider_name,
        auth_mode=explicit_auth_mode,
        official_provider_defaults=official_provider_defaults,
    )
    resolved_api_key_env_value = resolved_connect_api_key_env(
        provider_name=provider_name,
        auth_mode=resolved_auth_mode_value,
        api_key_env=explicit_api_key_env,
        official_provider_defaults=official_provider_defaults,
    )

    if base_url or connect_requires_base_url(
        provider_name,
        official_provider_defaults=official_provider_defaults,
    ):
        parts.append(f"base-url {base_url or '<url>'}")
    if explicit_auth_mode:
        parts.append(f"auth-mode {explicit_auth_mode}")
    elif not has_defaults:
        parts.append("auth-mode <mode>")

    if explicit_api_key_env:
        parts.append(f"api-key-env {explicit_api_key_env}")
    elif explicit_auth_mode == "api_key":
        parts.append(f"api-key-env {resolved_api_key_env_value or '<ENV>'}")
    elif not explicit_auth_mode and not has_defaults:
        parts.append("api-key-env <ENV>")

    parts.append(str(write_scope))
    return " ".join(parts)


__all__ = [
    "clear_provider_fields",
    "connect_next_action_hint",
    "connect_provider_defaults",
    "connect_requires_base_url",
    "provider_profile_name",
    "resolved_connect_api_key_env",
    "resolved_connect_auth_mode",
    "slugify_model_key",
    "upsert_model_entry",
    "upsert_provider_auth_fields",
    "upsert_provider_base_url",
]
