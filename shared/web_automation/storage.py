from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STATE_DIR = Path(".web_automation_state")
STATE_FILE = STATE_DIR / "state.json"
PROFILE_OVERRIDES_KEY = "profile_overrides"


def load_state() -> dict[str, Any]:
    try:
        with STATE_FILE.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(data: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with STATE_FILE.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def load_profile_overrides() -> dict[str, dict[str, Any]]:
    state = load_state()
    raw = state.get(PROFILE_OVERRIDES_KEY) if isinstance(state, dict) else None
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for name, spec in raw.items():
        profile_name = str(name or "").strip()
        if not profile_name or not isinstance(spec, dict):
            continue
        normalized[profile_name] = dict(spec)
    return normalized


def save_profile_overrides(overrides: dict[str, dict[str, Any]]) -> None:
    state = load_state()
    next_state = dict(state) if isinstance(state, dict) else {}
    normalized = {
        str(name).strip(): dict(spec)
        for name, spec in overrides.items()
        if str(name).strip() and isinstance(spec, dict)
    }
    if normalized:
        next_state[PROFILE_OVERRIDES_KEY] = normalized
    else:
        next_state.pop(PROFILE_OVERRIDES_KEY, None)
    save_state(next_state)
