from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from cli.agent_cli.providers.auth_refresh_scheduler_runtime import RefreshProviderContext

_STATE_VERSION = 1


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, Mapping):
        return {}
    return dict(data)


def daemon_state_path_for_store(*, store_path: Path) -> Path:
    return store_path.with_name("auth_refresh_daemon_state.json")


def daemon_contexts_path_for_store(*, store_path: Path) -> Path:
    return store_path.with_name("auth_refresh_daemon_contexts.json")


def _context_to_dict(context: RefreshProviderContext) -> dict[str, Any]:
    return {
        "provider_name": context.provider_name,
        "token_ref": context.token_ref,
        "token_endpoint": context.token_endpoint,
        "client_id": context.client_id,
        "client_secret": context.client_secret,
        "scope": context.scope,
    }


def _contexts_from_payload(payload: Any) -> list[RefreshProviderContext]:
    raw_items = payload if isinstance(payload, list) else []
    contexts: list[RefreshProviderContext] = []
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        provider_name = _as_str(item.get("provider_name"))
        token_ref = _as_str(item.get("token_ref"))
        token_endpoint = _as_str(item.get("token_endpoint"))
        client_id = _as_str(item.get("client_id"))
        if not provider_name or not token_ref or not token_endpoint or not client_id:
            continue
        contexts.append(
            RefreshProviderContext(
                provider_name=provider_name,
                token_ref=token_ref,
                token_endpoint=token_endpoint,
                client_id=client_id,
                client_secret=_as_str(item.get("client_secret")),
                scope=_as_str(item.get("scope")),
            )
        )
    return contexts


def _write_contexts_file(
    *, contexts_path: Path, contexts: Iterable[RefreshProviderContext]
) -> None:
    payload = {"version": _STATE_VERSION, "contexts": [_context_to_dict(item) for item in contexts]}
    _write_json_atomic(contexts_path, payload)


def _load_contexts_file(*, contexts_path: Path) -> list[RefreshProviderContext]:
    payload = _read_json_dict(contexts_path)
    return _contexts_from_payload(payload.get("contexts"))
