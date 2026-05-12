from __future__ import annotations

import json
import locale as _locale
import os
import re
import tomllib
from pathlib import Path
from typing import Any, Mapping


def normalize_locale_id(value: str | None, *, auto_locale: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.lower() == auto_locale:
        return auto_locale
    normalized = raw.replace("_", "-").strip()
    lowered = normalized.lower()
    if lowered.startswith("zh"):
        return "zh-CN"
    if lowered.startswith("ja"):
        return "ja"
    if lowered.startswith("fr"):
        return "fr"
    if lowered.startswith("en"):
        return "en"
    return None


def detect_system_locale(*, env: Mapping[str, str] | None, auto_locale: str, default_locale: str) -> str:
    mapping = dict(env or os.environ)
    for key in ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG"):
        value = str(mapping.get(key) or "").strip()
        if not value:
            continue
        candidate = normalize_locale_id(value.split(":", 1)[0].split(".", 1)[0], auto_locale=auto_locale)
        if candidate and candidate != auto_locale:
            return candidate
    try:
        system_locale = _locale.getlocale()[0]
    except Exception:
        system_locale = None
    candidate = normalize_locale_id(system_locale, auto_locale=auto_locale)
    if candidate and candidate != auto_locale:
        return candidate
    return default_locale


def format_large_paste_placeholder(char_count: int, index: int, messages: Any) -> str:
    if index <= 1:
        return messages.text("paste.placeholder.base", char_count=char_count)
    return messages.text("paste.placeholder.suffixed", char_count=char_count, index=index)


def read_toml_mapping(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def presentation_project_paths(
    cwd: str | Path | None,
    *,
    project_local_data_dir_candidates: tuple[str, ...] | list[str],
) -> list[Path]:
    if cwd is None:
        return []
    try:
        resolved_cwd = Path(cwd).expanduser().resolve()
    except OSError:
        resolved_cwd = Path(cwd).expanduser()
    search_dirs = list(reversed(list(resolved_cwd.parents))) + [resolved_cwd]
    paths: list[Path] = []
    seen: set[Path] = set()
    for directory in search_dirs:
        candidate_roots = [directory]
        cli_subproject = directory / "cli"
        if cli_subproject.exists():
            candidate_roots.append(cli_subproject)
        for root in candidate_roots:
            for dirname in project_local_data_dir_candidates:
                candidate = root / dirname / "config.toml"
                if candidate.exists() and candidate not in seen:
                    paths.append(candidate)
                    seen.add(candidate)
                    break
    return paths


def configured_cli_lang(config: Mapping[str, object], *, auto_locale: str) -> str | None:
    cli_config = config.get("cli") if isinstance(config.get("cli"), dict) else {}
    return normalize_locale_id(cli_config.get("lang"), auto_locale=auto_locale) if cli_config else None


def configured_cli_theme(config: Mapping[str, object]) -> str:
    cli_config = config.get("cli") if isinstance(config.get("cli"), dict) else {}
    theme_block = cli_config.get("theme") if isinstance(cli_config.get("theme"), dict) else {}
    return str(theme_block.get("id") or "").strip() if theme_block else ""


def configured_cli_idle_cat(config: Mapping[str, object]) -> bool:
    cli_config = config.get("cli") if isinstance(config.get("cli"), dict) else {}
    value = cli_config.get("idle_cat") if cli_config else None
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return False


def quoted_toml_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def upsert_toml_string_key(
    existing: str,
    *,
    dotted_key: str,
    section_header: str,
    key: str,
    value: str,
) -> str:
    rendered_value = quoted_toml_string(value)
    dotted_pattern = re.compile(rf"(?m)^{re.escape(dotted_key)}\s*=.*$")
    if dotted_pattern.search(existing):
        return dotted_pattern.sub(f"{dotted_key} = {rendered_value}", existing, count=1)

    section_pattern = re.compile(
        rf"(?ms)^(?P<header>{re.escape(section_header)}[ \t]*\n)(?P<body>.*?)(?=^\[|\Z)"
    )
    replacement_line = f"{key} = {rendered_value}\n"
    match = section_pattern.search(existing)
    if match is None:
        prefix = existing.rstrip()
        if prefix:
            prefix += "\n\n"
        return prefix + section_header + "\n" + replacement_line

    body = match.group("body")
    key_pattern = re.compile(rf"(?m)^{re.escape(key)}\s*=.*$")
    if key_pattern.search(body):
        body = key_pattern.sub(replacement_line.rstrip(), body, count=1)
        body = body.rstrip() + "\n"
    else:
        body = body.rstrip()
        body = (body + "\n" if body else "") + replacement_line
    return existing[: match.start()] + match.group("header") + body + existing[match.end() :]


def save_user_presentation_preferences(
    *,
    path: Path,
    lang: str | None = None,
    theme_id: str | None = None,
) -> Path:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    updated = existing
    if lang is not None:
        updated = upsert_toml_string_key(
            updated,
            dotted_key="cli.lang",
            section_header="[cli]",
            key="lang",
            value=lang,
        )
    if theme_id is not None:
        updated = upsert_toml_string_key(
            updated,
            dotted_key="cli.theme.id",
            section_header="[cli.theme]",
            key="id",
            value=theme_id,
        )
    if updated and not updated.endswith("\n"):
        updated += "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")
    return path


def project_presentation_override_path(
    *,
    cwd: str | Path | None,
    setting: str,
    presentation_project_paths_fn: Any,
    read_toml_mapping_fn: Any,
    configured_cli_lang_fn: Any,
    configured_cli_theme_fn: Any,
) -> Path | None:
    override_path: Path | None = None
    for candidate in presentation_project_paths_fn(cwd):
        config = read_toml_mapping_fn(candidate)
        if setting == "lang":
            if configured_cli_lang_fn(config) is not None:
                override_path = candidate
        elif setting == "theme":
            if configured_cli_theme_fn(config):
                override_path = candidate
    return override_path


def resolve_presentation_settings(
    *,
    cwd: str | Path | None = None,
    lang: str | None = None,
    theme_id: str | None = None,
    auto_locale: str,
    default_locale: str,
    supported_locales: tuple[str, ...],
    presentation_config_fn: Any,
    configured_cli_lang_fn: Any,
    configured_cli_theme_fn: Any,
    configured_cli_idle_cat_fn: Any,
    normalize_locale_id_fn: Any,
    detect_system_locale_fn: Any,
    resolve_cli_theme_fn: Any,
    message_catalog_type: type,
    presentation_settings_type: type,
    default_theme_id: str,
) -> Any:
    config = presentation_config_fn(cwd)
    configured_lang = configured_cli_lang_fn(config)
    configured_theme = configured_cli_theme_fn(config)
    configured_idle_cat = configured_cli_idle_cat_fn(config)

    requested_locale = normalize_locale_id_fn(lang) or configured_lang or auto_locale
    if requested_locale == auto_locale:
        requested_locale = detect_system_locale_fn()
    final_locale = requested_locale or default_locale
    if final_locale not in supported_locales:
        final_locale = default_locale

    final_theme = resolve_cli_theme_fn(theme_id or configured_theme or default_theme_id)
    return presentation_settings_type(
        locale=final_locale,
        theme_id=final_theme.id,
        theme=final_theme,
        messages=message_catalog_type(final_locale),
        idle_cat_enabled=configured_idle_cat,
    )
