from __future__ import annotations

import base64
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from typing import Any

from shared.web_automation.config import BrowserAutomationConfig, load_config
from shared.web_automation.proxy_client_app_server import (
    AppServerBrowserProxyClient,
    AppServerBrowserProxyError,
    AppServerBrowserProxyTransport,
)
from shared.web_automation.proxy_client_http_helpers import (
    BrowserProxyHttpAuth,
    HttpBrowserProxyError,
    _apply_remote_proxy_paths,
    _apply_remote_proxy_urls,
    _artifact_source_name_from_url,
    _build_browser_proxy_url,
    _collect_result_artifact_paths,
    _collect_result_artifact_urls,
    _decode_http_browser_proxy_payload,
    _http_browser_proxy_error,
    _is_allowed_remote_artifact_url,
    _persist_remote_proxy_file,
    _resolve_http_proxy_auth_headers,
)


class HttpBrowserProxyClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        password: str | None = None,
        inject_loopback_auth: bool | None = None,
        config: BrowserAutomationConfig | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self._config = config or load_config()
        self._env = dict(env or {})
        self._base_url = str(base_url or self._config.proxy_base_url or "").strip().rstrip("/")
        self._token = str(token or self._config.proxy_auth_token or "").strip()
        self._password = str(password or self._config.proxy_auth_password or "").strip()
        if inject_loopback_auth is None:
            self._inject_loopback_auth = bool(self._config.proxy_inject_loopback_auth)
        else:
            self._inject_loopback_auth = bool(inject_loopback_auth)
        if not self._base_url:
            raise HttpBrowserProxyError("browser proxy base_url is required")
        parsed = urlparse(self._base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HttpBrowserProxyError("browser proxy base_url must be an absolute http(s) URL")

    def browser_proxy(
        self,
        *,
        method: str = "GET",
        path: str,
        query: dict[str, object] | None = None,
        body: object = None,
        profile: str | None = None,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        normalized_path = str(path or "").strip()
        if not normalized_path:
            raise HttpBrowserProxyError("path is required")
        normalized_query = dict(query or {})
        if profile and "profile" not in normalized_query:
            normalized_query["profile"] = profile
        url = _build_browser_proxy_url(self._base_url, normalized_path, normalized_query)
        payload_bytes = None
        headers = {"Accept": "application/json"}
        if body is not None:
            payload_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        headers.update(
            _resolve_http_proxy_auth_headers(
                url,
                explicit_auth=BrowserProxyHttpAuth(token=self._token, password=self._password),
                config=self._config,
                env=self._env,
                inject_loopback_auth=self._inject_loopback_auth,
            )
        )
        request = Request(
            url,
            data=payload_bytes,
            headers=headers,
            method=str(method or "GET").strip().upper() or "GET",
        )
        timeout_s = max(0.001, int(timeout_ms or 20000) / 1000.0)
        try:
            with urlopen(request, timeout=timeout_s) as response:
                status = int(getattr(response, "status", 200) or 200)
                body_text = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            status = int(exc.code)
            body_text = exc.read().decode("utf-8", errors="replace")
            raise _http_browser_proxy_error(status=status, body_text=body_text) from exc
        except URLError as exc:
            raise HttpBrowserProxyError(f"browser proxy request failed: {exc.reason}") from exc
        payload = _decode_http_browser_proxy_payload(
            body_text,
            default_status=status,
            max_file_bytes=max(1, int(self._config.proxy_max_file_bytes)),
        )
        files = list(payload.get("files") or [])
        fetched_by_path = self._fetch_remote_artifacts_by_path(result=payload.get("result"))
        if fetched_by_path:
            files.extend(fetched_by_path)
        fetched_by_url = self._fetch_remote_artifacts_by_url(result=payload.get("result"))
        if fetched_by_url:
            files.extend(fetched_by_url)
        payload["files"] = files
        return payload

    def _fetch_remote_artifacts_by_path(self, *, result: object) -> list[dict[str, Any]]:
        normalized_result = dict(result) if isinstance(result, dict) else {}
        source_paths = _collect_result_artifact_paths(normalized_result)
        if not source_paths:
            return []
        fetched: list[dict[str, Any]] = []
        path_mapping: dict[str, str] = {}
        for source_path in source_paths:
            artifact = self._fetch_remote_artifact_by_path(source_path)
            if artifact is None:
                continue
            fetched.append(artifact)
            path_mapping[str(artifact.get("source_path") or source_path)] = str(artifact.get("path") or "")
        if path_mapping:
            _apply_remote_proxy_paths(normalized_result, path_mapping)
            if isinstance(result, dict):
                result.clear()
                result.update(normalized_result)
        return fetched

    def _fetch_remote_artifacts_by_url(self, *, result: object) -> list[dict[str, Any]]:
        normalized_result = dict(result) if isinstance(result, dict) else {}
        source_urls = _collect_result_artifact_urls(normalized_result, base_url=self._base_url)
        if not source_urls:
            return []
        fetched: list[dict[str, Any]] = []
        url_mapping: dict[str, str] = {}
        for source_url in source_urls:
            artifact = self._fetch_remote_artifact_by_url(source_url)
            if artifact is None:
                continue
            fetched.append(artifact)
            url_mapping[str(artifact.get("source_url") or source_url)] = str(artifact.get("path") or "")
        if url_mapping:
            _apply_remote_proxy_urls(normalized_result, url_mapping)
            if isinstance(result, dict):
                result.clear()
                result.update(normalized_result)
        return fetched

    def _fetch_remote_artifact_by_path(self, source_path: str) -> dict[str, Any] | None:
        if not str(source_path or "").strip():
            return None
        artifact_url = _build_browser_proxy_url(self._base_url, "/artifact", {"path": source_path})
        headers = {"Accept": "*/*"}
        headers.update(
            _resolve_http_proxy_auth_headers(
                artifact_url,
                explicit_auth=BrowserProxyHttpAuth(token=self._token, password=self._password),
                config=self._config,
                env=self._env,
                inject_loopback_auth=self._inject_loopback_auth,
            )
        )
        request = Request(artifact_url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=5.0) as response:
                if int(getattr(response, "status", 200) or 200) >= 400:
                    return None
                content = response.read()
                mime_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip() or None
        except HTTPError as exc:
            if int(exc.code) == 404:
                return None
            raise HttpBrowserProxyError(f"browser proxy artifact fetch failed with HTTP {int(exc.code)}") from exc
        except URLError:
            return None
        if len(content) > max(1, int(self._config.proxy_max_file_bytes)):
            raise HttpBrowserProxyError(f"browser proxy file exceeds {int(self._config.proxy_max_file_bytes)} bytes")
        local_path = _persist_remote_proxy_file(path=source_path, content=content, mime_type=mime_type)
        return {
            "path": local_path,
            "source_path": source_path,
            "base64": base64.b64encode(content).decode("ascii"),
            "mime_type": mime_type,
            "size_bytes": len(content),
        }

    def _fetch_remote_artifact_by_url(self, source_url: str) -> dict[str, Any] | None:
        if not _is_allowed_remote_artifact_url(source_url, base_url=self._base_url):
            return None
        headers = {"Accept": "*/*"}
        headers.update(
            _resolve_http_proxy_auth_headers(
                source_url,
                explicit_auth=BrowserProxyHttpAuth(token=self._token, password=self._password),
                config=self._config,
                env=self._env,
                inject_loopback_auth=self._inject_loopback_auth,
            )
        )
        request = Request(source_url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=5.0) as response:
                if int(getattr(response, "status", 200) or 200) >= 400:
                    return None
                content = response.read()
                mime_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip() or None
        except HTTPError as exc:
            if int(exc.code) == 404:
                return None
            raise HttpBrowserProxyError(f"browser proxy artifact fetch failed with HTTP {int(exc.code)}") from exc
        except URLError:
            return None
        if len(content) > max(1, int(self._config.proxy_max_file_bytes)):
            raise HttpBrowserProxyError(f"browser proxy file exceeds {int(self._config.proxy_max_file_bytes)} bytes")
        source_name = _artifact_source_name_from_url(source_url)
        local_path = _persist_remote_proxy_file(path=source_name, content=content, mime_type=mime_type)
        return {
            "path": local_path,
            "source_url": source_url,
            "base64": base64.b64encode(content).decode("ascii"),
            "mime_type": mime_type,
            "size_bytes": len(content),
        }


class HttpBrowserProxyTransport:
    def __init__(self, client: HttpBrowserProxyClient | None = None, **client_kwargs: Any) -> None:
        self._client = client or HttpBrowserProxyClient(**client_kwargs)

    def run(
        self,
        *,
        method: str = "GET",
        path: str,
        query: dict[str, object] | None = None,
        body: object = None,
        profile: str | None = None,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        return self._client.browser_proxy(
            method=method,
            path=path,
            query=query,
            body=body,
            profile=profile,
            timeout_ms=timeout_ms,
        )

    def close(self) -> None:
        return None


def create_browser_proxy_transport(
    *,
    config: BrowserAutomationConfig | None = None,
    env: dict[str, str] | None = None,
):
    resolved = config or load_config()
    transport = str(resolved.proxy_transport or "local").strip().lower()
    if transport == "http":
        return HttpBrowserProxyTransport(config=resolved, env=env)
    return AppServerBrowserProxyTransport()
