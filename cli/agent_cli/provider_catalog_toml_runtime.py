from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, Sequence


def quoted_toml_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def upsert_root_toml_string_key(existing: str, *, key: str, value: str) -> str:
    rendered_value = quoted_toml_string(value)
    pattern = re.compile(rf"(?m)^{re.escape(key)}\s*=.*$")
    replacement = f"{key} = {rendered_value}"
    if pattern.search(existing):
        return pattern.sub(replacement, existing, count=1)
    first_section = re.search(r"(?m)^\[", existing)
    if first_section is not None:
        prefix = existing[: first_section.start()].rstrip()
        suffix = existing[first_section.start() :].lstrip("\n")
        parts = [part for part in (prefix, replacement, suffix) if part]
        return "\n\n".join(parts) + "\n"
    prefix = existing.rstrip()
    if prefix:
        prefix += "\n"
    return prefix + replacement + "\n"


def clear_root_toml_key(existing: str, *, key: str) -> str:
    pattern = re.compile(rf"(?m)^{re.escape(key)}\s*=.*(?:\n)?")
    updated = pattern.sub("", existing, count=1)
    updated = re.sub(r"(?m)\A\n+", "", updated)
    updated = re.sub(r"\n{3,}", "\n\n", updated)
    return updated


def _upsert_section_lines(existing: str, *, section: str, lines: Sequence[str]) -> str:
    pattern = re.compile(rf"(?ms)^\[{re.escape(section)}\]\s*\n(.*?)(?=^\[|\Z)")
    match = pattern.search(existing)
    if match is None:
        rendered_lines = "\n".join(str(line).rstrip() for line in lines if str(line).strip())
        block = f"[{section}]\n{rendered_lines}\n" if rendered_lines else f"[{section}]\n"
        prefix = existing.rstrip()
        if prefix:
            prefix += "\n\n"
        return prefix + block
    body = match.group(1)
    updated_body = body
    for line in lines:
        normalized = str(line).strip()
        if not normalized:
            continue
        key = normalized.split("=", 1)[0].strip()
        key_pattern = re.compile(rf"(?m)^{re.escape(key)}\s*=.*$")
        if key_pattern.search(updated_body):
            updated_body = key_pattern.sub(normalized, updated_body, count=1)
        else:
            updated_body = updated_body.rstrip("\n")
            if updated_body:
                updated_body += "\n"
            updated_body += normalized + "\n"
    start, end = match.span(1)
    return existing[:start] + updated_body + existing[end:]


def upsert_provider_auth_schema(
    existing: str,
    *,
    provider_name: str,
    auth_mode: str,
    auth: Dict[str, Any] | None = None,
) -> str:
    normalized_provider = str(provider_name or "").strip()
    if not normalized_provider:
        return existing
    normalized_mode = str(auth_mode or "").strip().lower() or "api_key"
    updated = _upsert_section_lines(
        existing,
        section=f"model_providers.{normalized_provider}",
        lines=[f"auth_mode = {quoted_toml_string(normalized_mode)}"],
    )
    auth_payload = dict(auth or {})
    if normalized_mode == "api_key":
        env_var = str(auth_payload.get("env_var") or "").strip()
        if env_var:
            updated = _upsert_section_lines(
                updated,
                section=f"model_providers.{normalized_provider}",
                lines=[f"api_key_env = {quoted_toml_string(env_var)}"],
            )
            updated = _upsert_section_lines(
                updated,
                section=f"model_providers.{normalized_provider}.auth",
                lines=[f"env_var = {quoted_toml_string(env_var)}"],
            )
        value_ref = str(auth_payload.get("value_ref") or "").strip()
        if value_ref:
            updated = _upsert_section_lines(
                updated,
                section=f"model_providers.{normalized_provider}.auth",
                lines=[f"value_ref = {quoted_toml_string(value_ref)}"],
            )
        return updated
    if normalized_mode == "oauth":
        oauth_lines: list[str] = []
        client_id = str(auth_payload.get("client_id") or "").strip()
        token_endpoint = str(auth_payload.get("token_endpoint") or "").strip()
        scopes = [str(item).strip() for item in list(auth_payload.get("scopes") or []) if str(item).strip()]
        if client_id:
            oauth_lines.append(f"client_id = {quoted_toml_string(client_id)}")
        if token_endpoint:
            oauth_lines.append(f"token_endpoint = {quoted_toml_string(token_endpoint)}")
        if scopes:
            oauth_lines.append(f"scopes = {json.dumps(scopes, ensure_ascii=False)}")
        if oauth_lines:
            updated = _upsert_section_lines(
                updated,
                section=f"model_providers.{normalized_provider}.auth",
                lines=oauth_lines,
            )
        return updated
    if normalized_mode == "wellknown":
        wk_lines: list[str] = []
        issuer = str(auth_payload.get("issuer") or "").strip()
        metadata_url = str(auth_payload.get("metadata_url") or "").strip()
        if issuer:
            wk_lines.append(f"issuer = {quoted_toml_string(issuer)}")
        if metadata_url:
            wk_lines.append(f"metadata_url = {quoted_toml_string(metadata_url)}")
        if wk_lines:
            updated = _upsert_section_lines(
                updated,
                section=f"model_providers.{normalized_provider}.auth",
                lines=wk_lines,
            )
    return updated


def upsert_provider_profile(
    existing: str,
    *,
    profile_name: str,
    provider_name: str,
    model: str | None = None,
    base_url: str | None = None,
    auth_mode: str | None = None,
    auth: Dict[str, Any] | None = None,
) -> str:
    normalized_profile = str(profile_name or "").strip()
    normalized_provider = str(provider_name or "").strip()
    if not normalized_profile or not normalized_provider:
        return existing
    updated = _upsert_section_lines(
        existing,
        section=f"provider_profiles.{normalized_profile}",
        lines=[f"provider = {quoted_toml_string(normalized_provider)}"],
    )
    normalized_model = str(model or "").strip()
    if normalized_model:
        updated = _upsert_section_lines(
            updated,
            section=f"provider_profiles.{normalized_profile}",
            lines=[f"model = {quoted_toml_string(normalized_model)}"],
        )
    normalized_base_url = str(base_url or "").strip()
    if normalized_base_url:
        updated = _upsert_section_lines(
            updated,
            section=f"provider_profiles.{normalized_profile}",
            lines=[f"base_url = {quoted_toml_string(normalized_base_url)}"],
        )
    normalized_auth_mode = str(auth_mode or "").strip().lower()
    if normalized_auth_mode:
        updated = _upsert_section_lines(
            updated,
            section=f"provider_profiles.{normalized_profile}",
            lines=[f"auth_mode = {quoted_toml_string(normalized_auth_mode)}"],
        )
    auth_payload = dict(auth or {})
    if normalized_auth_mode == "api_key":
        env_var = str(auth_payload.get("env_var") or "").strip()
        if env_var:
            updated = _upsert_section_lines(
                updated,
                section=f"provider_profiles.{normalized_profile}",
                lines=[f"api_key_env = {quoted_toml_string(env_var)}"],
            )
    return updated


def read_user_model_selection_toml(
    *,
    config_paths: Sequence[Path],
    read_toml_fn: Callable[[Path], Dict[str, Any]],
    selection_keys: Sequence[str],
) -> Dict[str, Any]:
    for path in config_paths:
        payload = read_toml_fn(path)
        if not payload:
            continue
        selection: Dict[str, Any] = {}
        for key in selection_keys:
            value = payload.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                selection[key] = text
        if selection:
            return selection
    return {}


def load_toml_document_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_toml_document_text(path: Path, text: str) -> Path:
    rendered = str(text or "")
    if rendered and not rendered.endswith("\n"):
        rendered += "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    return path


def save_user_model_selection(
    *,
    path: Path,
    provider_name: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    provider_profile: str | None = None,
    default_provider_profile: str | None = None,
    provider_base_url: str | None = None,
    provider_name_for_auth: str | None = None,
    auth_mode: str | None = None,
    auth: Dict[str, Any] | None = None,
) -> Path:
    existing = load_toml_document_text(path)
    updated = existing
    if provider_name is not None:
        provider_name_text = str(provider_name).strip()
        updated = (
            upsert_root_toml_string_key(updated, key="model_provider", value=provider_name_text)
            if provider_name_text
            else clear_root_toml_key(updated, key="model_provider")
        )
    if model is not None:
        model_text = str(model).strip()
        updated = (
            upsert_root_toml_string_key(updated, key="model", value=model_text)
            if model_text
            else clear_root_toml_key(updated, key="model")
        )
    if reasoning_effort is not None:
        reasoning_effort_text = str(reasoning_effort).strip()
        updated = (
            upsert_root_toml_string_key(updated, key="model_reasoning_effort", value=reasoning_effort_text)
            if reasoning_effort_text
            else clear_root_toml_key(updated, key="model_reasoning_effort")
        )
    if provider_profile is not None:
        provider_profile_text = str(provider_profile).strip()
        updated = (
            upsert_root_toml_string_key(updated, key="provider_profile", value=provider_profile_text)
            if provider_profile_text
            else clear_root_toml_key(updated, key="provider_profile")
        )
    if default_provider_profile is not None:
        default_provider_profile_text = str(default_provider_profile).strip()
        updated = (
            upsert_root_toml_string_key(
                updated,
                key="default_provider_profile",
                value=default_provider_profile_text,
            )
            if default_provider_profile_text
            else clear_root_toml_key(updated, key="default_provider_profile")
        )
    if provider_name is not None and provider_base_url is not None:
        updated = _upsert_section_lines(
            updated,
            section=f"model_providers.{str(provider_name).strip()}",
            lines=[f"base_url = {quoted_toml_string(str(provider_base_url).strip())}"],
        )
    if auth_mode is not None and provider_name_for_auth is not None:
        updated = upsert_provider_auth_schema(
            updated,
            provider_name=str(provider_name_for_auth).strip(),
            auth_mode=str(auth_mode).strip(),
            auth=dict(auth or {}),
        )
    return write_toml_document_text(path, updated)
