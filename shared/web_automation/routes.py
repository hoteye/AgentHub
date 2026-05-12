from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from shared.web_automation.client import BrowserClient
from shared.web_automation.request_policy import (
    normalize_browser_request_path,
    resolve_requested_browser_profile,
)


@dataclass(frozen=True)
class BrowserRouteResponse:
    status: int
    body: dict[str, Any]


class BrowserRouteDispatcher:
    def __init__(self, client: BrowserClient | None = None) -> None:
        self._client = client or BrowserClient()

    def dispatch(
        self,
        *,
        method: str = "GET",
        path: str = "/",
        query: Mapping[str, object] | None = None,
        body: object = None,
        profile: str | None = None,
    ) -> BrowserRouteResponse:
        normalized_method = str(method or "GET").strip().upper() or "GET"
        normalized_path = normalize_browser_request_path(path)
        normalized_query = dict(query or {})
        normalized_body = dict(body) if isinstance(body, Mapping) else {}
        resolved_profile = resolve_requested_browser_profile(
            query=normalized_query,
            body=normalized_body,
            profile=profile,
        )

        try:
            if normalized_method == "GET" and normalized_path == "/":
                return self._ok(
                    self._client.perform(action="status", profile=resolved_profile),
                )
            if normalized_method == "GET" and normalized_path == "/profiles":
                return self._ok(
                    self._client.perform(action="profiles"),
                )
            if normalized_method == "POST" and normalized_path == "/profiles/create":
                return self._ok(
                    self._client.perform(
                        action="create_profile",
                        name=_required_text(normalized_body, "name"),
                        color=_optional_text(normalized_body, "color"),
                        cdp_url=_optional_text(normalized_body, "cdpUrl"),
                        user_data_dir=_optional_text(normalized_body, "userDataDir"),
                        driver=_optional_text(normalized_body, "driver"),
                        headless=_optional_bool(normalized_body, "headless"),
                        attach_only=_optional_bool(normalized_body, "attachOnly"),
                    ),
                )
            if normalized_method == "DELETE" and normalized_path.startswith("/profiles/"):
                profile_name = normalized_path[len("/profiles/") :].strip()
                if not profile_name:
                    raise ValueError("profile name is required")
                return self._ok(
                    self._client.perform(action="delete_profile", name=profile_name),
                )
            if normalized_method == "POST" and normalized_path == "/reset-profile":
                return self._ok(
                    self._client.perform(action="reset_profile", profile=resolved_profile),
                )
            if normalized_method == "POST" and normalized_path == "/start":
                return self._ok(self._client.perform(action="start", profile=resolved_profile))
            if normalized_method == "POST" and normalized_path == "/stop":
                return self._ok(self._client.perform(action="stop", profile=resolved_profile))
            if normalized_method == "GET" and normalized_path == "/tabs":
                return self._ok(self._client.perform(action="tabs", profile=resolved_profile))
            if normalized_method == "POST" and normalized_path == "/tabs/open":
                return self._ok(
                    self._client.perform(
                        action="open",
                        profile=resolved_profile,
                        url=_required_text(normalized_body, "url"),
                    ),
                )
            if normalized_method == "POST" and normalized_path == "/tabs/focus":
                return self._ok(
                    self._client.perform(
                        action="focus",
                        profile=resolved_profile,
                        tab_id=_required_text(normalized_body, "targetId"),
                    ),
                )
            if normalized_method == "DELETE" and normalized_path.startswith("/tabs/"):
                target_id = normalized_path[len("/tabs/") :].strip()
                if not target_id:
                    raise ValueError("targetId is required")
                return self._ok(
                    self._client.perform(
                        action="close",
                        profile=resolved_profile,
                        tab_id=target_id,
                    ),
                )
            if normalized_method == "POST" and normalized_path == "/navigate":
                return self._ok(
                    self._client.perform(
                        action="navigate",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_body, "targetId"),
                        url=_required_text(normalized_body, "url"),
                    ),
                )
            if normalized_method == "GET" and normalized_path == "/snapshot":
                return self._ok(
                    self._client.perform(
                        action="snapshot",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_query, "targetId"),
                        max_chars=_optional_int(normalized_query, "maxChars"),
                        max_refs=_optional_int(normalized_query, "maxRefs"),
                    ),
                )
            if normalized_method == "GET" and normalized_path == "/console":
                return self._ok(
                    self._client.perform(
                        action="console",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_query, "targetId"),
                        level=_optional_text(normalized_query, "level"),
                        limit=_optional_int(normalized_query, "limit"),
                    ),
                )
            if normalized_method == "GET" and normalized_path == "/errors":
                return self._ok(
                    self._client.perform(
                        action="errors",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_query, "targetId"),
                        limit=_optional_int(normalized_query, "limit"),
                    ),
                )
            if normalized_method == "GET" and normalized_path == "/requests":
                return self._ok(
                    self._client.perform(
                        action="requests",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_query, "targetId"),
                        limit=_optional_int(normalized_query, "limit"),
                        method=_optional_text(normalized_query, "method"),
                        outcome=_optional_text(normalized_query, "outcome"),
                    ),
                )
            if normalized_method == "POST" and normalized_path == "/screenshot":
                return self._ok(
                    self._client.perform(
                        action="screenshot",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_body, "targetId"),
                        ref=_optional_text(normalized_body, "ref"),
                    ),
                )
            if normalized_method == "POST" and normalized_path == "/pdf":
                return self._ok(
                    self._client.perform(
                        action="pdf",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_body, "targetId"),
                    ),
                )
            if normalized_method == "POST" and normalized_path == "/download":
                return self._ok(
                    self._client.perform(
                        action="download",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_body, "targetId"),
                        ref=_required_text(normalized_body, "ref"),
                        path=_optional_text(normalized_body, "path"),
                    ),
                )
            if normalized_method == "POST" and normalized_path == "/wait-download":
                return self._ok(
                    self._client.perform(
                        action="wait_download",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_body, "targetId"),
                        path=_optional_text(normalized_body, "path"),
                        time_ms=_optional_int(normalized_body, "timeoutMs"),
                    ),
                )
            if normalized_method == "POST" and normalized_path == "/highlight":
                return self._ok(
                    self._client.perform(
                        action="highlight",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_body, "targetId"),
                        ref=_required_text(normalized_body, "ref"),
                        time_ms=_optional_int(normalized_body, "timeMs"),
                    ),
                )
            if normalized_method == "POST" and normalized_path == "/trace/start":
                return self._ok(
                    self._client.perform(
                        action="trace_start",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_body, "targetId"),
                    ),
                )
            if normalized_method == "POST" and normalized_path == "/trace/stop":
                return self._ok(
                    self._client.perform(
                        action="trace_stop",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_body, "targetId"),
                        path=_optional_text(normalized_body, "path"),
                    ),
                )
            if normalized_method == "GET" and normalized_path == "/cookies":
                return self._ok(
                    self._client.perform(
                        action="cookies",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_query, "targetId"),
                    ),
                )
            if normalized_method == "GET" and normalized_path == "/cookies/get":
                return self._ok(
                    self._client.perform(
                        action="cookies_get",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_query, "targetId"),
                    ),
                )
            if normalized_method == "POST" and normalized_path == "/cookies/set":
                return self._ok(
                    self._client.perform(
                        action="cookies_set",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_body, "targetId"),
                        cookies=_required_dict_list(normalized_body, "cookies"),
                    ),
                )
            if normalized_method == "POST" and normalized_path == "/cookies/clear":
                return self._ok(
                    self._client.perform(
                        action="cookies_clear",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_body, "targetId"),
                    ),
                )
            if normalized_method == "GET" and normalized_path == "/storage/state":
                return self._ok(
                    self._client.perform(
                        action="storage_state",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_query, "targetId"),
                    ),
                )
            if normalized_method == "GET" and normalized_path == "/storage/get":
                return self._ok(
                    self._client.perform(
                        action="storage_get",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_query, "targetId"),
                        storage_kind=_required_text(normalized_query, "storageKind"),
                    ),
                )
            if normalized_method == "POST" and normalized_path == "/storage/set":
                return self._ok(
                    self._client.perform(
                        action="storage_set",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_body, "targetId"),
                        storage_kind=_required_text(normalized_body, "storageKind"),
                        items=_required_dict(normalized_body, "items"),
                    ),
                )
            if normalized_method == "POST" and normalized_path == "/storage/clear":
                return self._ok(
                    self._client.perform(
                        action="storage_clear",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_body, "targetId"),
                        storage_kind=_required_text(normalized_body, "storageKind"),
                    ),
                )
            if normalized_method == "POST" and normalized_path == "/upload":
                return self._ok(
                    self._client.perform(
                        action="upload",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_body, "targetId"),
                        ref=_optional_text(normalized_body, "ref"),
                        input_ref=_optional_text(normalized_body, "inputRef"),
                        paths=_required_text_list(normalized_body, "paths"),
                        time_ms=_optional_int(normalized_body, "timeoutMs"),
                    ),
                )
            if normalized_method == "POST" and normalized_path == "/dialog":
                return self._ok(
                    self._client.perform(
                        action="dialog",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_body, "targetId"),
                        accept=_optional_bool(normalized_body, "accept"),
                        prompt_text=_optional_text(normalized_body, "promptText"),
                        time_ms=_optional_int(normalized_body, "timeoutMs"),
                    ),
                )
            if normalized_method == "POST" and normalized_path == "/act":
                return self._ok(
                    self._client.perform(
                        action="act",
                        profile=resolved_profile,
                        tab_id=_optional_text(normalized_body, "targetId"),
                        kind=_required_text(normalized_body, "kind"),
                        ref=_optional_text(normalized_body, "ref"),
                        start_ref=_optional_text(normalized_body, "startRef"),
                        end_ref=_optional_text(normalized_body, "endRef"),
                        text=_optional_text(normalized_body, "text"),
                        key=_optional_text(normalized_body, "key"),
                        values=_optional_list(normalized_body, "values"),
                        fields=_optional_dict_list(normalized_body, "fields"),
                        time_ms=_optional_int(normalized_body, "timeMs"),
                        width=_optional_int(normalized_body, "width"),
                        height=_optional_int(normalized_body, "height"),
                    ),
                )
        except ValueError as exc:
            return BrowserRouteResponse(status=400, body={"ok": False, "error": str(exc)})
        except Exception as exc:
            return BrowserRouteResponse(status=500, body={"ok": False, "error": str(exc)})

        return BrowserRouteResponse(
            status=404,
            body={"ok": False, "error": f"unknown browser route: {normalized_method} {normalized_path}"},
        )

    @staticmethod
    def _ok(payload: dict[str, Any]) -> BrowserRouteResponse:
        return BrowserRouteResponse(status=200, body=dict(payload))


def _required_text(mapping: Mapping[str, object], key: str) -> str:
    value = _optional_text(mapping, key)
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _optional_text(mapping: Mapping[str, object], key: str) -> str | None:
    value = mapping.get(key)
    text = str(value or "").strip()
    return text or None


def _optional_int(mapping: Mapping[str, object], key: str) -> int | None:
    value = mapping.get(key)
    if value is None or value == "":
        return None
    return int(value)


def _optional_bool(mapping: Mapping[str, object], key: str) -> bool | None:
    value = mapping.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{key} must be a boolean")


def _optional_list(mapping: Mapping[str, object], key: str) -> list[str] | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return [str(item) for item in value]


def _optional_dict_list(mapping: Mapping[str, object], key: str) -> list[dict[str, object]] | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{key} must be a list of objects")
    return [dict(item) for item in value]


def _required_dict_list(mapping: Mapping[str, object], key: str) -> list[dict[str, object]]:
    value = _optional_dict_list(mapping, key)
    if value is None:
        raise ValueError(f"{key} is required")
    return value


def _required_text_list(mapping: Mapping[str, object], key: str) -> list[str]:
    value = _optional_list(mapping, key)
    if value is None:
        raise ValueError(f"{key} is required")
    return value


def _required_dict(mapping: Mapping[str, object], key: str) -> dict[str, object]:
    value = mapping.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return dict(value)
