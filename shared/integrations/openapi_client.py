from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from .auth import merge_headers
from .http_client import HttpClient, HttpRequest, HttpResponse


def _join_url(base_url: str, path: str) -> str:
    left = str(base_url or "").rstrip("/")
    right = str(path or "").lstrip("/")
    if not left:
        return "/" + right if right else ""
    if not right:
        return left
    return left + "/" + right


@dataclass(frozen=True)
class OperationSpec:
    name: str
    method: str
    path_template: str
    default_headers: dict[str, str] = field(default_factory=dict)
    expected_statuses: tuple[int, ...] = (200,)

    def render_path(self, *, path_params: Optional[Mapping[str, Any]] = None) -> str:
        rendered = str(self.path_template or "")
        for key, value in (path_params or {}).items():
            rendered = rendered.replace("{" + str(key) + "}", str(value))
        return rendered


class OpenAPIClient:
    def __init__(
        self,
        base_url: str,
        *,
        http_client: Optional[HttpClient] = None,
        default_headers: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.base_url = str(base_url or "").rstrip("/")
        self.http_client = http_client or HttpClient()
        self.default_headers = merge_headers(default_headers)

    def call(
        self,
        operation: OperationSpec,
        *,
        path_params: Optional[Mapping[str, Any]] = None,
        query: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, Any]] = None,
        json_body: Any = None,
        timeout_seconds: float = 10.0,
    ) -> HttpResponse:
        path = operation.render_path(path_params=path_params)
        url = _join_url(self.base_url, path)
        return self.http_client.request(
            HttpRequest(
                method=operation.method,
                url=url,
                headers=merge_headers(self.default_headers, operation.default_headers, headers),
                query=dict(query or {}),
                json_body=json_body,
                timeout_seconds=float(timeout_seconds or 10.0),
                expected_statuses=tuple(int(item) for item in operation.expected_statuses),
            )
        )
