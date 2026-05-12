from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:  # pragma: no cover - import availability depends on runtime env
    AESGCM = None  # type: ignore[assignment]


ENV_ENCRYPTION_MODE = "AGENTHUB_AUTH_TOKEN_ENCRYPTION"
ENV_ROTATE_DAYS = "AGENTHUB_AUTH_TOKEN_ROTATE_DAYS"
ENV_KEYRING_PATH = "AGENTHUB_AUTH_TOKEN_KEYRING_PATH"

_KEYRING_VERSION = 1
_ENCRYPTED_PAYLOAD_VERSION = 1
_DEFAULT_ROTATE_DAYS = 30
_AAD = b"agenthub.auth.session.v1"


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def token_encryption_supported() -> bool:
    return AESGCM is not None


def token_encryption_mode() -> str:
    mode = _as_str(os.environ.get(ENV_ENCRYPTION_MODE)).lower()
    if mode in {"on", "off", "auto"}:
        return mode
    return "auto"


def token_encryption_enabled() -> bool:
    mode = token_encryption_mode()
    if mode == "off":
        return False
    if mode == "on":
        return True
    return token_encryption_supported()


def token_keyring_path_for_store(*, store_path: Path) -> Path:
    override = _as_str(os.environ.get(ENV_KEYRING_PATH))
    if override:
        return Path(override)
    return store_path.with_name("auth.keys.json")


def _b64_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    text = _as_str(value)
    if not text:
        return b""
    padding = "=" * ((4 - (len(text) % 4)) % 4)
    return base64.urlsafe_b64decode((text + padding).encode("ascii"))


def _default_keyring_state() -> dict[str, Any]:
    return {"version": _KEYRING_VERSION, "active_key_id": "", "keys": {}}


def _read_keyring_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _default_keyring_state()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_keyring_state()
    if not isinstance(raw, Mapping):
        return _default_keyring_state()
    keys_raw = raw.get("keys")
    keys: dict[str, dict[str, Any]] = {}
    if isinstance(keys_raw, Mapping):
        for key_id, item in keys_raw.items():
            if not isinstance(key_id, str) or not isinstance(item, Mapping):
                continue
            keys[key_id] = dict(item)
    return {
        "version": _KEYRING_VERSION,
        "active_key_id": _as_str(raw.get("active_key_id")),
        "keys": keys,
    }


def _write_keyring_state(path: Path, state: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)
    try:
        path.chmod(0o600)
    except Exception:
        pass


def _generate_key_material() -> bytes:
    return os.urandom(32)


def _new_key_id(*, now_ts: float) -> str:
    return f"k{int(now_ts)}"


def _rotate_days() -> int:
    return max(1, _safe_int(os.environ.get(ENV_ROTATE_DAYS), _DEFAULT_ROTATE_DAYS))


def _ensure_keyring_with_active_key(*, path: Path) -> tuple[dict[str, Any], str, bytes]:
    state = _read_keyring_state(path)
    keys = dict(state.get("keys") or {})
    active_key_id = _as_str(state.get("active_key_id"))
    now_ts = float(time.time())
    rotate_after_seconds = _rotate_days() * 24 * 60 * 60

    def _active_record() -> dict[str, Any]:
        candidate = keys.get(active_key_id)
        if isinstance(candidate, Mapping):
            return dict(candidate)
        return {}

    needs_new = False
    if not active_key_id or active_key_id not in keys:
        needs_new = True
    else:
        created_at = float(_active_record().get("created_at") or 0.0)
        if created_at <= 0 or (now_ts - created_at) >= rotate_after_seconds:
            needs_new = True

    if needs_new:
        candidate = _new_key_id(now_ts=now_ts)
        while candidate in keys:
            candidate = f"{candidate}_r"
        active_key_id = candidate
        keys[active_key_id] = {
            "created_at": now_ts,
            "material_b64": _b64_encode(_generate_key_material()),
        }
        state = {"version": _KEYRING_VERSION, "active_key_id": active_key_id, "keys": keys}
        _write_keyring_state(path, state)
    else:
        state = {"version": _KEYRING_VERSION, "active_key_id": active_key_id, "keys": keys}

    record = dict(keys.get(active_key_id) or {})
    material = _b64_decode(_as_str(record.get("material_b64")))
    if len(material) != 32:
        material = _generate_key_material()
        record["material_b64"] = _b64_encode(material)
        record["created_at"] = float(record.get("created_at") or now_ts)
        keys[active_key_id] = record
        state = {"version": _KEYRING_VERSION, "active_key_id": active_key_id, "keys": keys}
        _write_keyring_state(path, state)
    return state, active_key_id, material


def _resolve_key_material_for_decrypt(*, keyring_path: Path, key_id: str) -> bytes | None:
    state = _read_keyring_state(keyring_path)
    keys = dict(state.get("keys") or {})
    record = dict(keys.get(_as_str(key_id)) or {})
    material = _b64_decode(_as_str(record.get("material_b64")))
    if len(material) != 32:
        return None
    return material


def session_payload_is_encrypted(payload: Mapping[str, Any]) -> bool:
    encrypted = payload.get("_enc")
    return isinstance(encrypted, Mapping) and _safe_int(encrypted.get("v"), 0) == _ENCRYPTED_PAYLOAD_VERSION


def encrypt_session_payload(
    payload: Mapping[str, Any],
    *,
    store_path: Path,
) -> dict[str, Any]:
    if not token_encryption_enabled():
        return dict(payload)
    if AESGCM is None:
        raise RuntimeError("AGENTHUB auth token encryption requires 'cryptography' package")
    keyring_path = token_keyring_path_for_store(store_path=store_path)
    _, active_key_id, key_material = _ensure_keyring_with_active_key(path=keyring_path)
    plaintext = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    nonce = os.urandom(12)
    ciphertext = AESGCM(key_material).encrypt(nonce, plaintext, _AAD)
    return {
        "_enc": {
            "v": _ENCRYPTED_PAYLOAD_VERSION,
            "alg": "AESGCM",
            "kid": active_key_id,
            "nonce": _b64_encode(nonce),
            "ciphertext": _b64_encode(ciphertext),
        }
    }


def decrypt_session_payload(
    payload: Mapping[str, Any],
    *,
    store_path: Path,
) -> dict[str, Any] | None:
    if not session_payload_is_encrypted(payload):
        return dict(payload)
    encrypted = dict(payload.get("_enc") or {})
    key_id = _as_str(encrypted.get("kid"))
    nonce = _b64_decode(_as_str(encrypted.get("nonce")))
    ciphertext = _b64_decode(_as_str(encrypted.get("ciphertext")))
    if not key_id or len(nonce) != 12 or not ciphertext:
        return None
    if AESGCM is None:
        return None
    keyring_path = token_keyring_path_for_store(store_path=store_path)
    key_material = _resolve_key_material_for_decrypt(keyring_path=keyring_path, key_id=key_id)
    if key_material is None:
        return None
    try:
        plaintext = AESGCM(key_material).decrypt(nonce, ciphertext, _AAD)
    except Exception:
        return None
    try:
        decoded = json.loads(plaintext.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(decoded, Mapping):
        return None
    return dict(decoded)


def token_encryption_public_status(*, store_path: Path) -> dict[str, Any]:
    keyring_path = token_keyring_path_for_store(store_path=store_path)
    state = _read_keyring_state(keyring_path)
    keys = dict(state.get("keys") or {})
    return {
        "mode": token_encryption_mode(),
        "enabled": token_encryption_enabled(),
        "supported": token_encryption_supported(),
        "keyring_path": str(keyring_path),
        "active_key_id": _as_str(state.get("active_key_id")),
        "key_count": len(keys),
    }
