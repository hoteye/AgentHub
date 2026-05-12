from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict


def _browser_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_browser_console_level(value: Any) -> str:
    normalized = _browser_text(value).lower()
    if normalized == "warn":
        return "warning"
    return normalized or "info"


def _browser_preview_text(value: Any, *, limit: int = 220) -> str:
    compact = " ".join(_browser_text(value).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _normalize_browser_act_kind(value: Any) -> str:
    text = _browser_text(value).lower().replace("-", "_").replace(" ", "_")
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_")


class _BrowserProxyToolClient:
    def __init__(self, transport: Any) -> None:
        self._transport = transport

    def perform(self, **kwargs: Any) -> dict[str, Any]:
        request = _browser_proxy_request_from_action(kwargs)
        response = self._transport.run(**request)
        result = response.get("result")
        normalized = dict(result) if isinstance(result, dict) else {}
        files = response.get("files")
        if isinstance(files, list) and files and "files" not in normalized:
            normalized["files"] = [dict(item) for item in files if isinstance(item, dict)]
        return normalized

    def status(self):
        payload = self.perform(action="status")
        return SimpleNamespace(
            active_tab=payload.get("active_tab"),
            active_profile=payload.get("profile") or payload.get("active_profile"),
            running=bool(payload.get("running")),
            profile_count=int(payload.get("profile_count") or payload.get("count") or 0),
        )

    def tabs(self, profile: str | None = None):
        payload = self.perform(action="tabs", profile=profile)
        tabs = payload.get("tabs")
        if not isinstance(tabs, list):
            return []
        return [
            SimpleNamespace(
                tab_id=item.get("tab_id"),
                url=item.get("url"),
                title=item.get("title"),
                profile=item.get("profile"),
            )
            for item in tabs
            if isinstance(item, dict)
        ]


def _browser_proxy_request_from_action(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    action = str(kwargs.get("action") or "").strip().lower()
    profile = _browser_text(kwargs.get("profile")) or None
    tab_id = _browser_text(kwargs.get("tab_id")) or None
    query: Dict[str, object] = {}
    body: Dict[str, object] = {}

    def _add_body(name: str, value: object) -> None:
        if value is None or value == "":
            return
        body[name] = value

    def _add_query(name: str, value: object) -> None:
        if value is None or value == "":
            return
        query[name] = value

    if action == "status":
        _add_query("profile", profile)
        return {"method": "GET", "path": "/", "query": query}
    if action == "profiles":
        return {"method": "GET", "path": "/profiles"}
    if action == "start":
        _add_body("profile", profile)
        return {"method": "POST", "path": "/start", "body": body}
    if action == "stop":
        _add_body("profile", profile)
        return {"method": "POST", "path": "/stop", "body": body}
    if action == "tabs":
        _add_query("profile", profile)
        return {"method": "GET", "path": "/tabs", "query": query}
    if action == "open":
        _add_body("profile", profile)
        _add_body("url", kwargs.get("url"))
        return {"method": "POST", "path": "/tabs/open", "body": body}
    if action == "focus":
        _add_body("profile", profile)
        _add_body("targetId", tab_id)
        return {"method": "POST", "path": "/tabs/focus", "body": body}
    if action == "close":
        return {"method": "DELETE", "path": f"/tabs/{tab_id or ''}", "query": {"profile": profile} if profile else {}}
    if action == "navigate":
        _add_body("profile", profile)
        _add_body("targetId", tab_id)
        _add_body("url", kwargs.get("url"))
        return {"method": "POST", "path": "/navigate", "body": body}
    if action == "snapshot":
        _add_query("profile", profile)
        _add_query("targetId", tab_id)
        _add_query("maxChars", kwargs.get("max_chars"))
        _add_query("maxRefs", kwargs.get("max_refs"))
        return {"method": "GET", "path": "/snapshot", "query": query}
    if action == "console":
        _add_query("profile", profile)
        _add_query("targetId", tab_id)
        _add_query("level", kwargs.get("level"))
        _add_query("limit", kwargs.get("limit"))
        return {"method": "GET", "path": "/console", "query": query}
    if action == "errors":
        _add_query("profile", profile)
        _add_query("targetId", tab_id)
        _add_query("limit", kwargs.get("limit"))
        return {"method": "GET", "path": "/errors", "query": query}
    if action == "requests":
        _add_query("profile", profile)
        _add_query("targetId", tab_id)
        _add_query("limit", kwargs.get("limit"))
        _add_query("method", kwargs.get("method"))
        _add_query("outcome", kwargs.get("outcome"))
        return {"method": "GET", "path": "/requests", "query": query}
    if action == "screenshot":
        _add_body("profile", profile)
        _add_body("targetId", tab_id)
        _add_body("ref", kwargs.get("ref"))
        return {"method": "POST", "path": "/screenshot", "body": body}
    if action == "pdf":
        _add_body("profile", profile)
        _add_body("targetId", tab_id)
        return {"method": "POST", "path": "/pdf", "body": body}
    if action == "download":
        _add_body("profile", profile)
        _add_body("targetId", tab_id)
        _add_body("ref", kwargs.get("ref"))
        _add_body("path", kwargs.get("path"))
        return {"method": "POST", "path": "/download", "body": body}
    if action == "wait_download":
        _add_body("profile", profile)
        _add_body("targetId", tab_id)
        _add_body("path", kwargs.get("path"))
        _add_body("timeoutMs", kwargs.get("time_ms"))
        return {"method": "POST", "path": "/wait-download", "body": body}
    if action == "highlight":
        _add_body("profile", profile)
        _add_body("targetId", tab_id)
        _add_body("ref", kwargs.get("ref"))
        _add_body("timeMs", kwargs.get("time_ms"))
        return {"method": "POST", "path": "/highlight", "body": body}
    if action == "trace_start":
        _add_body("profile", profile)
        _add_body("targetId", tab_id)
        return {"method": "POST", "path": "/trace/start", "body": body}
    if action == "trace_stop":
        _add_body("profile", profile)
        _add_body("targetId", tab_id)
        _add_body("path", kwargs.get("path"))
        return {"method": "POST", "path": "/trace/stop", "body": body}
    if action == "cookies":
        _add_query("profile", profile)
        _add_query("targetId", tab_id)
        return {"method": "GET", "path": "/cookies", "query": query}
    if action == "cookies_get":
        _add_query("profile", profile)
        _add_query("targetId", tab_id)
        return {"method": "GET", "path": "/cookies/get", "query": query}
    if action == "cookies_set":
        _add_body("profile", profile)
        _add_body("targetId", tab_id)
        _add_body("cookies", kwargs.get("cookies"))
        return {"method": "POST", "path": "/cookies/set", "body": body}
    if action == "cookies_clear":
        _add_body("profile", profile)
        _add_body("targetId", tab_id)
        return {"method": "POST", "path": "/cookies/clear", "body": body}
    if action == "storage_state":
        _add_query("profile", profile)
        _add_query("targetId", tab_id)
        return {"method": "GET", "path": "/storage/state", "query": query}
    if action == "storage_get":
        _add_query("profile", profile)
        _add_query("targetId", tab_id)
        _add_query("storageKind", kwargs.get("storage_kind"))
        return {"method": "GET", "path": "/storage/get", "query": query}
    if action == "storage_set":
        _add_body("profile", profile)
        _add_body("targetId", tab_id)
        _add_body("storageKind", kwargs.get("storage_kind"))
        _add_body("items", kwargs.get("items"))
        return {"method": "POST", "path": "/storage/set", "body": body}
    if action == "storage_clear":
        _add_body("profile", profile)
        _add_body("targetId", tab_id)
        _add_body("storageKind", kwargs.get("storage_kind"))
        return {"method": "POST", "path": "/storage/clear", "body": body}
    if action == "upload":
        _add_body("profile", profile)
        _add_body("targetId", tab_id)
        _add_body("ref", kwargs.get("ref"))
        _add_body("inputRef", kwargs.get("input_ref"))
        _add_body("paths", kwargs.get("paths"))
        _add_body("timeoutMs", kwargs.get("time_ms"))
        return {"method": "POST", "path": "/upload", "body": body}
    if action == "dialog":
        _add_body("profile", profile)
        _add_body("targetId", tab_id)
        _add_body("accept", kwargs.get("accept"))
        _add_body("promptText", kwargs.get("prompt_text"))
        _add_body("timeoutMs", kwargs.get("time_ms"))
        return {"method": "POST", "path": "/dialog", "body": body}
    if action == "act":
        _add_body("profile", profile)
        _add_body("targetId", tab_id)
        _add_body("kind", kwargs.get("kind"))
        _add_body("ref", kwargs.get("ref"))
        _add_body("startRef", kwargs.get("start_ref"))
        _add_body("endRef", kwargs.get("end_ref"))
        _add_body("text", kwargs.get("text"))
        _add_body("key", kwargs.get("key"))
        _add_body("values", kwargs.get("values"))
        _add_body("fields", kwargs.get("fields"))
        _add_body("timeMs", kwargs.get("time_ms"))
        _add_body("width", kwargs.get("width"))
        _add_body("height", kwargs.get("height"))
        return {"method": "POST", "path": "/act", "body": body}
    raise ValueError(f"unsupported browser proxy action: {action}")
