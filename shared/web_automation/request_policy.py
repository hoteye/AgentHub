from __future__ import annotations

from typing import Mapping


def normalize_browser_request_path(value: str) -> str:
    trimmed = str(value or "").strip()
    if not trimmed:
        return trimmed
    with_leading_slash = trimmed if trimmed.startswith("/") else f"/{trimmed}"
    if len(with_leading_slash) <= 1:
        return with_leading_slash
    return with_leading_slash.rstrip("/")


def is_persistent_browser_profile_mutation(method: str, path: str) -> bool:
    normalized_method = str(method or "").strip().upper()
    normalized_path = normalize_browser_request_path(path)
    if normalized_method == "POST" and normalized_path in {"/profiles/create", "/reset-profile"}:
        return True
    if normalized_method == "DELETE":
        parts = [part for part in normalized_path.split("/") if part]
        return len(parts) == 2 and parts[0] == "profiles"
    return False


def resolve_requested_browser_profile(
    *,
    query: Mapping[str, object] | None = None,
    body: object = None,
    profile: str | None = None,
) -> str | None:
    query_profile = _resolve_profile_value((query or {}).get("profile"))
    if query_profile:
        return query_profile
    if isinstance(body, Mapping):
        body_profile = _resolve_profile_value(body.get("profile"))
        if body_profile:
            return body_profile
    explicit = _resolve_profile_value(profile)
    return explicit or None


def _resolve_profile_value(raw: object) -> str:
    text = str(raw or "").strip()
    return text
