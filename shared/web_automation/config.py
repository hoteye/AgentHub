from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "browser_automation.toml"


@dataclass
class BrowserAutomationConfig:
    enabled: bool = True
    mode: str = "synthetic"
    evaluate_enabled: bool = False
    default_profile: str = "openclaw"
    executable_path: str = ""
    user_data_dir: str = ""
    cdp_url: str = ""
    attach_only: bool = False
    headless: bool = True
    launch_timeout_ms: int = 20000
    navigation_timeout_ms: int = 20000
    allow_hosts: list[str] = field(default_factory=list)
    block_hosts: list[str] = field(default_factory=list)
    allow_private_network: bool = False
    existing_session_discovery_bases: list[str] = field(default_factory=list)
    existing_session_discovery_path: str = "/json/version"
    proxy_enabled: bool = True
    proxy_transport: str = "local"
    proxy_base_url: str = ""
    proxy_auth_token: str = ""
    proxy_auth_password: str = ""
    proxy_inject_loopback_auth: bool = True
    proxy_allow_profiles: list[str] = field(default_factory=list)
    proxy_max_file_bytes: int = 10 * 1024 * 1024
    profiles: Dict[str, Dict[str, Any]] = field(default_factory=dict)


def load_config(path: Path | None = None) -> BrowserAutomationConfig:
    candidate = Path(path or DEFAULT_CONFIG_PATH)
    if not candidate.exists():
        return BrowserAutomationConfig()
    with candidate.open("rb") as handle:
        payload = tomllib.load(handle)
    mode = str(os.environ.get("AGENTHUB_BROWSER_MODE") or payload.get("mode") or "synthetic").strip().lower()
    executable_path = str(
        os.environ.get("AGENTHUB_BROWSER_EXECUTABLE_PATH")
        or payload.get("executable_path")
        or ""
    ).strip()
    user_data_dir = str(
        os.environ.get("AGENTHUB_BROWSER_USER_DATA_DIR")
        or payload.get("user_data_dir")
        or ""
    ).strip()
    cdp_url = str(
        os.environ.get("AGENTHUB_BROWSER_CDP_URL")
        or payload.get("cdp_url")
        or ""
    ).strip()
    headless_raw = os.environ.get("AGENTHUB_BROWSER_HEADLESS")
    if headless_raw is None:
        headless = bool(payload.get("headless", True))
    else:
        headless = str(headless_raw).strip().lower() not in {"0", "false", "no", "off"}
    attach_only_raw = os.environ.get("AGENTHUB_BROWSER_ATTACH_ONLY")
    if attach_only_raw is None:
        attach_only = _normalize_bool(payload.get("attach_only", False))
    else:
        attach_only = _normalize_bool(attach_only_raw)
    evaluate_enabled_raw = os.environ.get("AGENTHUB_BROWSER_EVALUATE_ENABLED")
    if evaluate_enabled_raw is None:
        evaluate_enabled = _normalize_bool(payload.get("evaluate_enabled", False))
    else:
        evaluate_enabled = _normalize_bool(evaluate_enabled_raw)
    existing_session_payload = payload.get("existing_session") if isinstance(payload.get("existing_session"), dict) else {}
    proxy_payload = payload.get("proxy") if isinstance(payload.get("proxy"), dict) else {}
    return BrowserAutomationConfig(
        enabled=bool(payload.get("enabled", True)),
        mode=mode or "synthetic",
        evaluate_enabled=evaluate_enabled,
        default_profile=str(payload.get("default_profile") or "openclaw"),
        executable_path=executable_path,
        user_data_dir=user_data_dir,
        cdp_url=cdp_url,
        attach_only=attach_only,
        headless=headless,
        launch_timeout_ms=int(payload.get("launch_timeout_ms", 20000) or 20000),
        navigation_timeout_ms=int(payload.get("navigation_timeout_ms", 20000) or 20000),
        allow_hosts=_normalize_host_rules(payload.get("allow_hosts")),
        block_hosts=_normalize_host_rules(payload.get("block_hosts")),
        allow_private_network=_normalize_bool(payload.get("allow_private_network", False)),
        existing_session_discovery_bases=_normalize_host_rules(
            os.environ.get("AGENTHUB_BROWSER_EXISTING_SESSION_DISCOVERY_BASES")
            if os.environ.get("AGENTHUB_BROWSER_EXISTING_SESSION_DISCOVERY_BASES") is not None
            else existing_session_payload.get("discovery_bases")
        ),
        existing_session_discovery_path=_normalize_discovery_path(
            os.environ.get("AGENTHUB_BROWSER_EXISTING_SESSION_DISCOVERY_PATH")
            if os.environ.get("AGENTHUB_BROWSER_EXISTING_SESSION_DISCOVERY_PATH") is not None
            else existing_session_payload.get("discovery_path")
        ),
        proxy_enabled=_normalize_bool(proxy_payload.get("enabled", True)),
        proxy_transport=str(
            os.environ.get("AGENTHUB_BROWSER_PROXY_TRANSPORT") or proxy_payload.get("transport") or "local"
        ).strip().lower()
        or "local",
        proxy_base_url=str(
            os.environ.get("AGENTHUB_BROWSER_PROXY_BASE_URL") or proxy_payload.get("base_url") or ""
        ).strip(),
        proxy_auth_token=str(
            os.environ.get("AGENTHUB_BROWSER_PROXY_TOKEN") or proxy_payload.get("auth_token") or ""
        ).strip(),
        proxy_auth_password=str(
            os.environ.get("AGENTHUB_BROWSER_PROXY_PASSWORD") or proxy_payload.get("auth_password") or ""
        ).strip(),
        proxy_inject_loopback_auth=_normalize_bool(
            os.environ.get("AGENTHUB_BROWSER_PROXY_LOOPBACK_AUTH")
            if os.environ.get("AGENTHUB_BROWSER_PROXY_LOOPBACK_AUTH") is not None
            else proxy_payload.get("inject_loopback_auth", True)
        ),
        proxy_allow_profiles=_normalize_host_rules(proxy_payload.get("allow_profiles")),
        proxy_max_file_bytes=int(
            proxy_payload.get("max_file_bytes", 10 * 1024 * 1024)
        ),
        profiles=_normalize_profiles(payload.get("profiles")),
    )


def _normalize_host_rules(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        entries = [raw]
    elif isinstance(raw, (list, tuple)):
        entries = list(raw)
    else:
        return []
    normalized: list[str] = []
    for item in entries:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return normalized


def _normalize_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    text = str(raw or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def _normalize_profiles(raw: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    normalized: Dict[str, Dict[str, Any]] = {}
    for name, spec in raw.items():
        profile_name = str(name or "").strip()
        if not profile_name or not isinstance(spec, dict):
            continue
        normalized[profile_name] = {
            "color": str(spec.get("color") or "").strip(),
            "driver": str(spec.get("driver") or "").strip(),
            "attach_only": _normalize_optional_bool(spec.get("attach_only")),
            "executable_path": str(spec.get("executable_path") or "").strip(),
            "user_data_dir": str(spec.get("user_data_dir") or "").strip(),
            "cdp_url": str(spec.get("cdp_url") or "").strip(),
            "headless": _normalize_optional_bool(spec.get("headless")),
        }
    return normalized


def _normalize_optional_bool(raw: Any) -> bool | None:
    if raw is None or raw == "":
        return None
    return _normalize_bool(raw)


def _normalize_discovery_path(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return "/json/version"
    if not text.startswith("/"):
        return f"/{text}"
    return text
