from __future__ import annotations

import re
from urllib.parse import urlparse

from shared.web_automation.types import BrowserProfileSpec


HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _normalize_profile_driver(driver: object) -> str:
    normalized = str(driver or "").strip().lower()
    if normalized in {"", "openclaw", "clawd", "synthetic", "live"}:
        return "openclaw"
    if normalized == "existing-session":
        return "existing-session"
    raise ValueError(f'unsupported profile driver "{normalized}"; use "openclaw", "clawd", or "existing-session"')


def _serialize_profile_override(spec: BrowserProfileSpec) -> dict[str, object]:
    return {
        "color": spec.color,
        "driver": spec.driver,
        "attach_only": spec.attach_only,
        "executable_path": spec.executable_path,
        "user_data_dir": spec.user_data_dir,
        "cdp_url": spec.cdp_url,
        "headless": spec.headless,
    }


def _is_remote_profile(spec: BrowserProfileSpec) -> bool:
    raw_url = str(spec.cdp_url or "").strip()
    if not raw_url:
        return False
    parsed = urlparse(raw_url)
    hostname = str(parsed.hostname or "").strip().lower()
    return hostname not in {"", "localhost", "127.0.0.1", "::1"}


def _supports_profile_reset(spec: BrowserProfileSpec) -> bool:
    driver = str(spec.driver or "").strip().lower()
    return driver != "existing-session" and not _is_remote_profile(spec)


def _profile_has_cdp_channel(spec: BrowserProfileSpec | None) -> bool:
    if spec is None:
        return False
    driver = str(spec.driver or "").strip().lower()
    return driver == "existing-session" or bool(str(spec.cdp_url or "").strip())

