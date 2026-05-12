from __future__ import annotations

import os
import re
from dataclasses import replace
from typing import Dict, Iterable

from shared.web_automation.config import BrowserAutomationConfig
from shared.web_automation.types import BrowserProfileSpec


PROFILE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PROFILE_COLORS = [
    "#FF4500",
    "#0066CC",
    "#00AA00",
    "#9933FF",
    "#FF6699",
    "#00CCCC",
    "#FF9900",
    "#6666FF",
    "#CC3366",
    "#339966",
]


def resolve_profiles(
    config: BrowserAutomationConfig,
    overrides: Dict[str, dict[str, object]] | None = None,
) -> Dict[str, BrowserProfileSpec]:
    profiles: Dict[str, BrowserProfileSpec] = {}
    merged_specs: Dict[str, dict[str, object]] = {
        name: dict(spec)
        for name, spec in config.profiles.items()
    }
    for name, spec in (overrides or {}).items():
        profile_name = str(name or "").strip()
        if not profile_name or not isinstance(spec, dict):
            continue
        merged_specs[profile_name] = dict(spec)
    for name, spec in merged_specs.items():
        profiles[name] = BrowserProfileSpec(
            name=name,
            color=str(spec.get("color") or "#CCCCCC"),
            driver=str(spec.get("driver") or config.mode or "synthetic"),
            default=(name == config.default_profile),
            attach_only=_resolve_profile_bool(spec.get("attach_only"), config.attach_only),
            executable_path=str(spec.get("executable_path") or config.executable_path or ""),
            user_data_dir=str(spec.get("user_data_dir") or config.user_data_dir or ""),
            cdp_url=str(spec.get("cdp_url") or config.cdp_url or ""),
            headless=_resolve_profile_optional_bool(spec.get("headless"), config.headless),
        )
    profiles = _ensure_builtin_user_profile(profiles, config)
    if config.default_profile not in profiles:
        profiles[config.default_profile] = BrowserProfileSpec(
            name=config.default_profile,
            color="#FF4500",
            driver=config.mode or "synthetic",
            default=True,
            attach_only=config.attach_only,
            executable_path=config.executable_path,
            user_data_dir=config.user_data_dir,
            cdp_url=config.cdp_url,
            headless=config.headless,
        )
    return profiles


def ensure_default_profile(profiles: Dict[str, BrowserProfileSpec], default: str) -> Dict[str, BrowserProfileSpec]:
    if default not in profiles:
        profiles[default] = BrowserProfileSpec(name=default, color="#FF4500", driver="synthetic", default=True)
    return {name: replace(spec, default=(name == default)) for name, spec in profiles.items()}


def is_valid_profile_name(name: str) -> bool:
    text = str(name or "").strip()
    if not text or len(text) > 64:
        return False
    return bool(PROFILE_NAME_RE.fullmatch(text))


def get_used_colors(profiles: Dict[str, BrowserProfileSpec]) -> set[str]:
    return {
        str(spec.color or "").strip().upper()
        for spec in profiles.values()
        if str(spec.color or "").strip()
    }


def allocate_profile_color(used_colors: Iterable[str]) -> str:
    used = {str(item or "").strip().upper() for item in used_colors if str(item or "").strip()}
    for color in PROFILE_COLORS:
        if color.upper() not in used:
            return color
    index = len(used) % len(PROFILE_COLORS)
    return PROFILE_COLORS[index]


def _resolve_profile_bool(raw: object, fallback: bool) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw is None or raw == "":
        return fallback
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return fallback


def _resolve_profile_optional_bool(raw: object, fallback: bool) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw is None or raw == "":
        return fallback
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return fallback


def _ensure_builtin_user_profile(
    profiles: Dict[str, BrowserProfileSpec],
    config: BrowserAutomationConfig,
) -> Dict[str, BrowserProfileSpec]:
    if str(config.mode or "").strip().lower() != "live":
        return profiles
    if "user" in profiles:
        return profiles
    profiles["user"] = BrowserProfileSpec(
        name="user",
        color="#00AA00",
        driver="existing-session",
        default=False,
        attach_only=True,
        executable_path=config.executable_path,
        user_data_dir=_default_existing_session_user_data_dir(),
        cdp_url="",
        headless=False,
    )
    return profiles


def _default_existing_session_user_data_dir() -> str:
    home = os.path.expanduser("~")
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        return os.path.join(local_app_data, "Google", "Chrome", "User Data")
    if os.uname().sysname == "Darwin":
        return os.path.join(home, "Library", "Application Support", "Google", "Chrome")
    return os.path.join(home, ".config", "google-chrome")
