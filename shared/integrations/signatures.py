from __future__ import annotations

import hashlib
import hmac


def _to_bytes(value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        return value
    return str(value or "").encode("utf-8")


def compute_sha256_hex(payload: str | bytes) -> str:
    return hashlib.sha256(_to_bytes(payload)).hexdigest()


def compute_hmac_sha256_hex(secret: str | bytes, payload: str | bytes) -> str:
    return hmac.new(_to_bytes(secret), _to_bytes(payload), hashlib.sha256).hexdigest()


def verify_hmac_sha256_hex(
    secret: str | bytes,
    payload: str | bytes,
    provided_signature: str,
    *,
    prefix: str = "sha256=",
) -> bool:
    candidate = str(provided_signature or "").strip()
    if not candidate:
        return False
    if prefix and candidate.startswith(prefix):
        candidate = candidate[len(prefix):]
    expected = compute_hmac_sha256_hex(secret, payload)
    return hmac.compare_digest(expected, candidate)
