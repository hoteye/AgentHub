from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


DEFAULT_UPSTREAM_BASE_URL = "https://api.anthropic.com"


@dataclass(frozen=True)
class ProxyConfig:
    upstream_base_url: str
    out_dir: Path
    response_preview_bytes: int = 8192
    upstream_timeout_seconds: float = 300.0


@dataclass(frozen=True)
class ClaudeHomeConfig:
    api_key: str
    base_url: str
    settings_path: Path
    config_path: Path
    state_path: Path
    settings_payload: dict[str, Any]
    config_payload: dict[str, Any]
    state_payload: dict[str, Any]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(encoded, encoding="utf-8")
    tmp_path.replace(path)


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def load_claude_home_config(
    *,
    home_dir: Path | None = None,
    env_mapping: Mapping[str, str] | None = None,
) -> ClaudeHomeConfig | None:
    home = Path(home_dir).expanduser() if home_dir is not None else Path.home()
    env = dict(env_mapping or os.environ)
    settings_path = home / ".claude" / "settings.json"
    config_path = home / ".claude" / "config.json"
    state_path = home / ".claude.json"
    settings_payload = _read_json_file(settings_path)
    config_payload = _read_json_file(config_path)
    state_payload = _read_json_file(state_path)
    settings_env = settings_payload.get("env")
    settings_env_mapping = dict(settings_env) if isinstance(settings_env, dict) else {}

    api_key = _first_text(
        env.get("ANTHROPIC_API_KEY"),
        settings_env_mapping.get("ANTHROPIC_API_KEY"),
        settings_env_mapping.get("_ANTHROPIC_API_KEY"),
        config_payload.get("primaryApiKey"),
        config_payload.get("apiKey"),
        config_payload.get("anthropicApiKey"),
        config_payload.get("api_key"),
    )
    base_url = _first_text(
        env.get("ANTHROPIC_BASE_URL"),
        settings_env_mapping.get("ANTHROPIC_BASE_URL"),
        config_payload.get("baseURL"),
        config_payload.get("baseUrl"),
    )
    if not api_key and not base_url:
        return None
    return ClaudeHomeConfig(
        api_key=api_key,
        base_url=base_url,
        settings_path=settings_path,
        config_path=config_path,
        state_path=state_path,
        settings_payload=settings_payload,
        config_payload=config_payload,
        state_payload=state_payload,
    )


def resolve_upstream_base_url(
    *,
    explicit_upstream_base_url: str,
    home_dir: Path | None = None,
    env_mapping: Mapping[str, str] | None = None,
) -> tuple[str, str, ClaudeHomeConfig | None]:
    explicit = str(explicit_upstream_base_url or "").strip()
    current = load_claude_home_config(home_dir=home_dir, env_mapping=env_mapping)
    if explicit:
        return explicit, "flag", current
    if current is not None and str(current.base_url or "").strip():
        return str(current.base_url).strip(), "claude_home", current
    return DEFAULT_UPSTREAM_BASE_URL, "default", current


def write_claude_proxy_settings(
    *,
    output_path: Path,
    proxy_base_url: str,
    home_dir: Path | None = None,
    env_mapping: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    current = load_claude_home_config(home_dir=home_dir, env_mapping=env_mapping)
    payload = dict(current.settings_payload) if current is not None else {}
    env = dict(payload.get("env") or {})
    if current is not None and str(current.api_key or "").strip():
        env["ANTHROPIC_API_KEY"] = str(current.api_key).strip()
    env["ANTHROPIC_BASE_URL"] = str(proxy_base_url).strip()
    payload["env"] = env
    _write_json(output_path, payload)
    return {
        "settings_file": str(output_path),
        "proxy_base_url": str(proxy_base_url).strip(),
        "resolved_source_base_url": str(current.base_url or "").strip() if current is not None else "",
        "settings_path": str(current.settings_path) if current is not None else "",
        "config_path": str(current.config_path) if current is not None else "",
    }
