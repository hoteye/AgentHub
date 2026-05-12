from __future__ import annotations

import base64
import json
import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from typing import Any

from shared.web_automation.artifacts import create_artifact_path, sanitize_artifact_filename
from shared.web_automation.config import BrowserAutomationConfig


class HttpBrowserProxyError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.data = dict(data or {})


@dataclass(frozen=True)
class BrowserProxyHttpAuth:
    token: str = ""
    password: str = ""


def _build_browser_proxy_url(base_url: str, path: str, query: dict[str, object]) -> str:
    normalized_path = path if str(path).startswith("/") else f"/{path}"
    full_url = urljoin(base_url.rstrip("/") + "/", normalized_path.lstrip("/"))
    normalized_query = {
        key: value
        for key, value in query.items()
        if value is not None and value != ""
    }
    if not normalized_query:
        return full_url
    return f"{full_url}?{urlencode([(key, str(value)) for key, value in normalized_query.items()])}"


def _decode_http_browser_proxy_body(body_text: str) -> dict[str, Any]:
    if not str(body_text).strip():
        return {}
    try:
        payload = json.loads(body_text)
    except json.JSONDecodeError as exc:
        raise HttpBrowserProxyError("browser proxy returned non-JSON response") from exc
    if not isinstance(payload, dict):
        raise HttpBrowserProxyError("browser proxy returned invalid JSON object")
    return dict(payload)


def _decode_http_browser_proxy_payload(
    body_text: str,
    *,
    default_status: int,
    max_file_bytes: int,
) -> dict[str, Any]:
    payload = _decode_http_browser_proxy_body(body_text)
    if "result" in payload or "files" in payload:
        status = int(payload.get("status") or default_status)
        result = payload.get("result")
        normalized_result = dict(result) if isinstance(result, dict) else {}
        files, path_mapping = _normalize_remote_proxy_files(payload.get("files"), max_file_bytes=max_file_bytes)
        if path_mapping:
            _apply_remote_proxy_paths(normalized_result, path_mapping)
        return {
            "status": status,
            "result": normalized_result,
            "files": files,
        }
    return {"status": default_status, "result": payload, "files": []}


def _http_browser_proxy_error(*, status: int, body_text: str) -> HttpBrowserProxyError:
    data: dict[str, Any] = {}
    message = f"browser proxy request failed with HTTP {status}"
    if str(body_text).strip():
        try:
            payload = json.loads(body_text)
        except json.JSONDecodeError:
            message = f"{message}: {body_text.strip()}"
        else:
            if isinstance(payload, dict):
                data = dict(payload)
                body_error = str(payload.get("error") or "").strip()
                if body_error:
                    message = body_error
    return HttpBrowserProxyError(message, status=status, data=data)


def _normalize_remote_proxy_files(
    files: object,
    *,
    max_file_bytes: int,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if files is None:
        return [], {}
    if not isinstance(files, list):
        raise HttpBrowserProxyError("browser proxy returned invalid files payload")
    normalized: list[dict[str, Any]] = []
    path_mapping: dict[str, str] = {}
    for item in files:
        if not isinstance(item, dict):
            raise HttpBrowserProxyError("browser proxy returned invalid file descriptor")
        path = str(item.get("path") or "").strip()
        content_base64 = str(item.get("base64") or "").strip()
        if not path or not content_base64:
            raise HttpBrowserProxyError("browser proxy file descriptor requires path and base64")
        try:
            content = base64.b64decode(content_base64, validate=True)
        except Exception as exc:
            raise HttpBrowserProxyError(f"browser proxy file base64 is invalid for {path}") from exc
        if len(content) > max_file_bytes:
            raise HttpBrowserProxyError(f"browser proxy file exceeds {max_file_bytes} bytes")
        mime_type = str(item.get("mime_type") or item.get("mimeType") or "").strip() or None
        local_path = _persist_remote_proxy_file(path=path, content=content, mime_type=mime_type)
        path_mapping[path] = local_path
        normalized.append(
            {
                "path": local_path,
                "source_path": path,
                "base64": content_base64,
                "mime_type": mime_type,
                "size_bytes": len(content),
            }
        )
    return normalized, path_mapping


def _collect_result_artifact_paths(payload: object) -> list[str]:
    paths: set[str] = set()

    def _walk(value: object) -> None:
        if isinstance(value, dict):
            direct_path = value.get("path")
            if isinstance(direct_path, str) and direct_path.strip():
                paths.add(direct_path.strip())
            image_path = value.get("imagePath")
            if isinstance(image_path, str) and image_path.strip():
                paths.add(image_path.strip())
            for child in value.values():
                _walk(child)
            return
        if isinstance(value, list):
            for child in value:
                _walk(child)

    _walk(payload)
    return sorted(paths)


def _persist_remote_proxy_file(*, path: str, content: bytes, mime_type: str | None) -> str:
    source_name = Path(str(path or "").strip()).name
    if not source_name:
        extension = mimetypes.guess_extension(str(mime_type or "").strip()) or ".bin"
        source_name = f"proxy-artifact{extension}"
    safe_name = sanitize_artifact_filename(source_name, default="proxy-artifact.bin")
    target = create_artifact_path("proxy", f"{uuid.uuid4().hex[:12]}-{safe_name}")
    target.write_bytes(content)
    return str(target.resolve())


def _apply_remote_proxy_paths(result: object, mapping: dict[str, str]) -> None:
    if not mapping:
        return

    def _walk(value: object) -> None:
        if isinstance(value, dict):
            for key in ("path", "imagePath"):
                current = value.get(key)
                if isinstance(current, str) and current in mapping:
                    value[key] = mapping[current]
            for child in value.values():
                _walk(child)
            return
        if isinstance(value, list):
            for child in value:
                _walk(child)

    _walk(result)


def _apply_remote_proxy_urls(result: object, mapping: dict[str, str]) -> None:
    if not mapping:
        return

    def _walk(value: object, *, parent_key: str | None = None) -> None:
        if isinstance(value, dict):
            direct_url = value.get("url")
            if (
                isinstance(direct_url, str)
                and direct_url in mapping
                and _dict_looks_like_artifact(value, parent_key=parent_key)
                and not str(value.get("path") or "").strip()
            ):
                value["path"] = mapping[direct_url]
            for alias_key, path_key in (
                ("artifactUrl", "path"),
                ("downloadUrl", "path"),
                ("fileUrl", "path"),
                ("imageUrl", "imagePath"),
            ):
                alias_value = value.get(alias_key)
                if isinstance(alias_value, str) and alias_value in mapping and not str(value.get(path_key) or "").strip():
                    value[path_key] = mapping[alias_value]
            for child_key, child in value.items():
                _walk(child, parent_key=str(child_key))
            return
        if isinstance(value, list):
            for child in value:
                _walk(child, parent_key=parent_key)

    _walk(result)


def _resolve_http_proxy_auth_headers(
    url: str,
    *,
    explicit_auth: BrowserProxyHttpAuth,
    config: BrowserAutomationConfig,
    env: dict[str, str],
    inject_loopback_auth: bool,
) -> dict[str, str]:
    if explicit_auth.token:
        return {"Authorization": f"Bearer {explicit_auth.token}"}
    if explicit_auth.password:
        return {"X-AgentHub-Password": explicit_auth.password}
    if not inject_loopback_auth or not _is_loopback_http_url(url):
        return {}
    env_token = str(env.get("AGENTHUB_BROWSER_PROXY_TOKEN") or "").strip()
    env_password = str(env.get("AGENTHUB_BROWSER_PROXY_PASSWORD") or "").strip()
    token = env_token or str(config.proxy_auth_token or "").strip()
    password = env_password or str(config.proxy_auth_password or "").strip()
    if token:
        return {"Authorization": f"Bearer {token}"}
    if password:
        return {"X-AgentHub-Password": password}
    return {}


def _is_loopback_http_url(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    hostname = str(parsed.hostname or "").strip().lower()
    if not hostname:
        return False
    return hostname in {"localhost", "127.0.0.1", "::1", "::ffff:127.0.0.1"}


def _collect_result_artifact_urls(payload: object, *, base_url: str) -> list[str]:
    urls: set[str] = set()

    def _walk(value: object, *, parent_key: str | None = None) -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                child_key_text = str(child_key)
                if (
                    isinstance(child, str)
                    and _is_allowed_remote_artifact_url(child, base_url=base_url)
                    and _is_artifact_url_candidate(
                        key=child_key_text,
                        value=child,
                        container=value,
                        parent_key=parent_key,
                    )
                ):
                    urls.add(child.strip())
                _walk(child, parent_key=child_key_text)
            return
        if isinstance(value, list):
            for child in value:
                _walk(child, parent_key=parent_key)

    _walk(payload)
    return sorted(urls)


def _is_artifact_url_candidate(
    *,
    key: str,
    value: str,
    container: dict[str, Any],
    parent_key: str | None,
) -> bool:
    del value
    normalized_key = str(key or "").strip()
    if normalized_key in {"artifactUrl", "downloadUrl", "fileUrl", "imageUrl"}:
        return True
    if normalized_key != "url":
        return False
    return _dict_looks_like_artifact(container, parent_key=parent_key)


def _dict_looks_like_artifact(value: dict[str, Any], *, parent_key: str | None) -> bool:
    if str(parent_key or "").strip() in {"artifact", "download", "file", "trace", "screenshot", "pdf"}:
        return True
    artifact_keys = {"artifact_id", "kind", "content_type", "suggested_filename", "path", "imagePath"}
    return any(str(key) in artifact_keys for key in value.keys())


def _is_allowed_remote_artifact_url(raw_url: str, *, base_url: str) -> bool:
    parsed = urlparse(str(raw_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    parsed_base = urlparse(str(base_url or "").strip())
    default_port = 443 if parsed.scheme == "https" else 80
    base_port = 443 if parsed_base.scheme == "https" else 80
    if (
        parsed.scheme != parsed_base.scheme
        or str(parsed.hostname or "").strip().lower() != str(parsed_base.hostname or "").strip().lower()
        or int(parsed.port or default_port) != int(parsed_base.port or base_port)
    ):
        return False
    normalized_path = str(parsed.path or "").strip()
    return normalized_path.endswith("/artifact") or "/artifact/" in normalized_path


def _artifact_source_name_from_url(source_url: str) -> str:
    parsed = urlparse(str(source_url or "").strip())
    query = parse_qs(parsed.query)
    query_path = str((query.get("path") or [""])[-1] or "").strip()
    if query_path:
        query_name = Path(query_path).name
        if query_name:
            return query_name
    path_name = Path(str(parsed.path or "").strip()).name
    if path_name:
        return path_name
    return "proxy-artifact.bin"
