from __future__ import annotations

import base64
import concurrent.futures
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qsl, quote, urlparse, urlunparse

from shared.web_automation.config import BrowserAutomationConfig, load_config
from shared.web_automation.request_policy import (
    is_persistent_browser_profile_mutation,
    normalize_browser_request_path,
    resolve_requested_browser_profile,
)
from shared.web_automation.routes import BrowserRouteDispatcher, BrowserRouteResponse

_WS_BACKED_BROWSER_PROXY_PATHS = frozenset(
    {
        "/act",
        "/navigate",
        "/pdf",
        "/screenshot",
        "/snapshot",
    }
)


@dataclass(frozen=True)
class BrowserProxyFile:
    path: str
    base64: str
    mime_type: str | None = None


class BrowserProxyExecutor:
    def __init__(
        self,
        config: BrowserAutomationConfig | None = None,
        *,
        dispatcher: BrowserRouteDispatcher | None = None,
    ) -> None:
        self._config = config or load_config()
        self._dispatcher = dispatcher or BrowserRouteDispatcher()

    def run(
        self,
        *,
        method: str = "GET",
        path: str = "/",
        query: Mapping[str, object] | None = None,
        body: object = None,
        timeout_ms: int | None = None,
        profile: str | None = None,
    ) -> dict[str, Any]:
        if not self._config.proxy_enabled:
            raise RuntimeError("browser proxy disabled")

        normalized_method = str(method or "GET").strip().upper() or "GET"
        normalized_path = normalize_browser_request_path(path)
        normalized_query = dict(query or {})
        normalized_body = dict(body) if isinstance(body, Mapping) else {}

        requested_profile = resolve_requested_browser_profile(
            query=normalized_query,
            body=normalized_body,
            profile=profile,
        )
        self._assert_profile_allowed(
            method=normalized_method,
            path=normalized_path,
            requested_profile=requested_profile,
        )

        response = self._dispatch_with_timeout(
            method=normalized_method,
            path=normalized_path,
            query=normalized_query,
            body=normalized_body,
            profile=profile,
            timeout_ms=timeout_ms,
        )
        result_body = dict(response.body)
        if self._config.proxy_allow_profiles and normalized_path == "/profiles":
            result_body = _filter_profiles_payload(result_body, self._config.proxy_allow_profiles)
        return {
            "status": response.status,
            "result": result_body,
            "files": [file.__dict__ for file in self._collect_files(response)],
        }

    def _assert_profile_allowed(self, *, method: str, path: str, requested_profile: str | None) -> None:
        allow_profiles = [item.strip() for item in self._config.proxy_allow_profiles if str(item).strip()]
        if not allow_profiles:
            return
        if is_persistent_browser_profile_mutation(method, path):
            raise ValueError(
                "browser proxy cannot mutate persistent browser profiles when allow_profiles is configured"
            )
        if path == "/profiles":
            if requested_profile and requested_profile not in allow_profiles:
                raise ValueError("browser profile not allowed")
            return
        profile_to_check = requested_profile or self._config.default_profile
        if profile_to_check not in allow_profiles:
            raise ValueError("browser profile not allowed")

    def _collect_files(self, response: BrowserRouteResponse) -> list[BrowserProxyFile]:
        file_paths = _collect_browser_proxy_paths(response.body)
        files: list[BrowserProxyFile] = []
        for file_path in file_paths:
            file = _read_browser_proxy_file(
                file_path,
                max_bytes=max(1, int(self._config.proxy_max_file_bytes)),
            )
            if file is not None:
                files.append(file)
        return files

    def _dispatch_with_timeout(
        self,
        *,
        method: str,
        path: str,
        query: Mapping[str, object],
        body: Mapping[str, object],
        profile: str | None,
        timeout_ms: int | None,
    ) -> BrowserRouteResponse:
        if timeout_ms is None:
            return self._dispatcher.dispatch(
                method=method,
                path=path,
                query=query,
                body=body,
                profile=profile,
            )
        bounded_timeout_s = max(0.001, int(timeout_ms) / 1000.0)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                self._dispatcher.dispatch,
                method=method,
                path=path,
                query=query,
                body=body,
                profile=profile,
            )
            try:
                return future.result(timeout=bounded_timeout_s)
            except concurrent.futures.TimeoutError as exc:
                status = self._read_proxy_status(profile=profile, path=path)
                raise TimeoutError(
                    _format_browser_proxy_timeout_message(
                        method=method,
                        path=path,
                        profile=profile,
                        timeout_ms=int(timeout_ms),
                        ws_backed=_is_ws_backed_browser_proxy_path(path),
                        status=status,
                    )
                ) from exc

    def _read_proxy_status(self, *, profile: str | None, path: str) -> dict[str, Any] | None:
        if path == "/profiles":
            return None
        try:
            response = self._dispatcher.dispatch(
                method="GET",
                path="/",
                query={"profile": profile} if profile else {},
                body={},
                profile=profile,
            )
        except Exception:
            return None
        if response.status >= 400:
            return None
        return dict(response.body)


def run_browser_proxy_command(
    params_json: str | None = None,
    *,
    executor: BrowserProxyExecutor | None = None,
) -> str:
    if not params_json:
        raise ValueError("params_json is required")
    params = json.loads(params_json)
    if not isinstance(params, Mapping):
        raise ValueError("params_json must decode to an object")
    path = str(params.get("path") or "").strip()
    if not path:
        raise ValueError("path is required")
    proxy = executor or BrowserProxyExecutor()
    payload = proxy.run(
        method=str(params.get("method") or "GET"),
        path=path,
        query=params.get("query") if isinstance(params.get("query"), Mapping) else None,
        body=params.get("body"),
        timeout_ms=int(params["timeoutMs"]) if params.get("timeoutMs") is not None else None,
        profile=str(params.get("profile") or "").strip() or None,
    )
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _collect_browser_proxy_paths(payload: object) -> list[str]:
    paths: set[str] = set()

    def _walk(value: object) -> None:
        if isinstance(value, Mapping):
            direct_path = value.get("path")
            if isinstance(direct_path, str) and direct_path.strip():
                paths.add(direct_path.strip())
            image_path = value.get("imagePath")
            if isinstance(image_path, str) and image_path.strip():
                paths.add(image_path.strip())
            for item in value.values():
                _walk(item)
            return
        if isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(payload)
    return sorted(paths)


def _read_browser_proxy_file(file_path: str, *, max_bytes: int) -> BrowserProxyFile | None:
    candidate = Path(str(file_path or "").strip())
    if not candidate.is_file():
        return None
    size_bytes = candidate.stat().st_size
    if size_bytes > max_bytes:
        raise ValueError(f"browser proxy file exceeds {max_bytes} bytes")
    content = candidate.read_bytes()
    mime_type = mimetypes.guess_type(candidate.name)[0] or None
    return BrowserProxyFile(
        path=str(candidate.resolve()),
        base64=base64.b64encode(content).decode("ascii"),
        mime_type=mime_type,
    )


def _format_browser_proxy_timeout_message(
    *,
    method: str,
    path: str,
    profile: str | None,
    timeout_ms: int,
    ws_backed: bool,
    status: Mapping[str, object] | None,
) -> str:
    parts = [f"browser proxy timed out for {method} {path} after {timeout_ms}ms"]
    parts.append("ws-backed browser action" if ws_backed else "browser action")
    if profile:
        parts.append(f"profile={profile}")
    if status:
        status_bits: list[str] = []
        for key in ("running", "profile", "mode", "transport", "active_tab", "tabs", "cdp_http", "cdp_ready", "cdp_url"):
            if key in status:
                value = status[key]
                if key == "cdp_url":
                    value = _redact_browser_proxy_url(value)
                status_bits.append(f"{key}={value}")
        if status_bits:
            parts.append("status(" + ", ".join(status_bits) + ")")
    return "; ".join(parts)


def _is_ws_backed_browser_proxy_path(path: str) -> bool:
    return str(path or "").strip() in _WS_BACKED_BROWSER_PROXY_PATHS


def _redact_browser_proxy_url(raw_url: object) -> str:
    text = str(raw_url or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if not parsed.scheme or not parsed.netloc:
        return text
    username = parsed.username or ""
    password = parsed.password or ""
    hostname = parsed.hostname or ""
    port = parsed.port
    auth_prefix = ""
    if username:
        auth_prefix = username
        if password:
            auth_prefix += ":***"
        auth_prefix += "@"
    host = hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if port is not None:
        host = f"{host}:{port}"
    redacted_query: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.strip().lower()
        if lowered in {"token", "api_key", "apikey", "access_token", "password", "secret"}:
            redacted_query.append((key, "***"))
        else:
            redacted_query.append((key, value))
    query = "&".join(
        f"{quote(key, safe='')}={quote(value, safe='*')}"
        for key, value in redacted_query
    )
    return urlunparse(
        (
            parsed.scheme,
            auth_prefix + host,
            parsed.path,
            parsed.params,
            query,
            parsed.fragment,
        )
    )


def _filter_profiles_payload(payload: dict[str, Any], allow_profiles: list[str]) -> dict[str, Any]:
    allowed = {str(item).strip() for item in allow_profiles if str(item).strip()}
    filtered = dict(payload)
    profiles = filtered.get("profiles")
    if not isinstance(profiles, list):
        return filtered
    filtered["profiles"] = [
        dict(item)
        for item in profiles
        if isinstance(item, Mapping) and str(item.get("name") or "").strip() in allowed
    ]
    filtered["count"] = len(filtered["profiles"])
    filtered["profile_names"] = [str(item.get("name") or "") for item in filtered["profiles"]]
    return filtered
