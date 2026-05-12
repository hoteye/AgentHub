from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Protocol

from cli.agent_cli.providers.auth_token_encryption_runtime import (
    decrypt_session_payload,
    encrypt_session_payload,
)
from cli.agent_cli.providers.auth_session_runtime import AuthSession


def token_store_key(provider_name: str, token_ref: str) -> str:
    provider = str(provider_name or "").strip()
    ref = str(token_ref or "").strip()
    return f"{provider}::{ref}"


class AuthTokenStore(Protocol):
    def get(self, provider_name: str, token_ref: str) -> AuthSession | None:
        ...

    def put(self, session: AuthSession) -> None:
        ...

    def delete(self, provider_name: str, token_ref: str) -> bool:
        ...


@dataclass
class FileAuthTokenStore:
    store_path: Path

    def get(self, provider_name: str, token_ref: str) -> AuthSession | None:
        state = _read_store_state(self.store_path)
        sessions = _sessions_map(state)
        payload = sessions.get(token_store_key(provider_name, token_ref))
        if not isinstance(payload, Mapping):
            return None
        session_payload = decrypt_session_payload(payload, store_path=self.store_path)
        if not isinstance(session_payload, Mapping):
            return None
        session = AuthSession.from_mapping(session_payload)
        if not session.provider_name or not session.token_ref:
            return None
        return session

    def put(self, session: AuthSession) -> None:
        if not session.provider_name or not session.token_ref:
            raise ValueError("provider_name and token_ref are required")
        state = _read_store_state(self.store_path)
        sessions = _sessions_map(state)
        sessions[token_store_key(session.provider_name, session.token_ref)] = encrypt_session_payload(
            session.to_dict(),
            store_path=self.store_path,
        )
        _write_store_state(self.store_path, state)

    def delete(self, provider_name: str, token_ref: str) -> bool:
        state = _read_store_state(self.store_path)
        sessions = _sessions_map(state)
        removed = sessions.pop(token_store_key(provider_name, token_ref), None)
        if removed is None:
            return False
        _write_store_state(self.store_path, state)
        return True


def _sessions_map(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    raw = state.get("sessions")
    if isinstance(raw, dict):
        sessions: Dict[str, Dict[str, Any]] = {}
        for key, value in raw.items():
            if isinstance(key, str) and isinstance(value, dict):
                sessions[key] = dict(value)
        state["sessions"] = sessions
        return sessions
    state["sessions"] = {}
    return state["sessions"]


def _read_store_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"version": 1, "sessions": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "sessions": {}}
    if not isinstance(raw, dict):
        return {"version": 1, "sessions": {}}
    state = dict(raw)
    if not isinstance(state.get("version"), int):
        state["version"] = 1
    _sessions_map(state)
    return state


def _write_store_state(path: Path, state: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)
