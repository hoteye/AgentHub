from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from .auth import merge_headers, redact_headers
from .retry import RetryPolicy, retry_call


def _normalize_query(query: Optional[Mapping[str, Any]]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for key, value in (query or {}).items():
        name = str(key or "").strip()
        if not name:
            continue
        if isinstance(value, (list, tuple)):
            for item in value:
                pairs.append((name, str(item)))
            continue
        pairs.append((name, str(value)))
    return pairs


def _append_query(url: str, query: Optional[Mapping[str, Any]]) -> str:
    pairs = _normalize_query(query)
    if not pairs:
        return url
    parsed = urlparse(str(url or ""))
    existing = parsed.query
    new_query = urlencode(pairs, doseq=True)
    combined_query = "&".join(item for item in (existing, new_query) if item)
    return urlunparse(parsed._replace(query=combined_query))


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, Any] = field(default_factory=dict)
    body_bytes: bytes | None = None
    body_text: str | None = None
    json_body: Any = None
    timeout_seconds: float = 10.0
    expected_statuses: tuple[int, ...] | None = None


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    url: str
    headers: dict[str, str]
    body_bytes: bytes
    text: str
    json_data: Any

    @property
    def ok(self) -> bool:
        return 200 <= int(self.status_code) < 300

    def to_log_dict(self) -> dict[str, Any]:
        return {
            "status_code": int(self.status_code),
            "url": self.url,
            "headers": redact_headers(self.headers),
        }


class HttpClientError(RuntimeError):
    def __init__(self, message: str, *, request: HttpRequest, response: HttpResponse | None = None) -> None:
        super().__init__(message)
        self.request = request
        self.response = response


class HttpClient:
    def __init__(
        self,
        *,
        default_headers: Optional[Mapping[str, Any]] = None,
        retry_policy: Optional[RetryPolicy] = None,
        open_url: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.default_headers = merge_headers(default_headers)
        self.retry_policy = retry_policy or RetryPolicy()
        self._open_url = open_url or urlopen

    @staticmethod
    def _build_body(headers: dict[str, str], request: HttpRequest) -> bytes | None:
        if request.json_body is not None:
            if "Content-Type" not in headers and "content-type" not in {key.lower() for key in headers}:
                headers["Content-Type"] = "application/json; charset=utf-8"
            return json.dumps(request.json_body, ensure_ascii=False).encode("utf-8")
        if request.body_bytes is not None:
            return request.body_bytes
        if request.body_text is not None:
            return request.body_text.encode("utf-8")
        return None

    @staticmethod
    def _build_response(response_obj: Any) -> HttpResponse:
        body_bytes = response_obj.read()
        body_text = body_bytes.decode("utf-8", errors="replace")
        header_items = dict(response_obj.headers.items())
        content_type = str(header_items.get("Content-Type") or header_items.get("content-type") or "")
        json_data: Any = None
        if "json" in content_type.lower():
            try:
                json_data = json.loads(body_text)
            except json.JSONDecodeError:
                json_data = None
        return HttpResponse(
            status_code=int(response_obj.getcode()),
            url=str(response_obj.geturl()),
            headers=header_items,
            body_bytes=body_bytes,
            text=body_text,
            json_data=json_data,
        )

    def request(self, request: HttpRequest) -> HttpResponse:
        method = str(request.method or "GET").upper()
        url = _append_query(request.url, request.query)
        headers = merge_headers(self.default_headers, request.headers)
        body = self._build_body(headers, request)
        raw_request = Request(url, data=body, headers=headers, method=method)
        expected_statuses = tuple(request.expected_statuses or ())

        def _send() -> HttpResponse:
            try:
                response_obj = self._open_url(raw_request, timeout=float(request.timeout_seconds or 10.0))
            except HTTPError as exc:
                response_obj = exc
            return self._build_response(response_obj)

        def _should_retry(response: Optional[HttpResponse], error: Optional[BaseException]) -> bool:
            if error is not None:
                return isinstance(error, self.retry_policy.retry_exception_types)
            if response is None:
                return False
            return int(response.status_code) in self.retry_policy.retry_statuses

        response = retry_call(_send, should_retry=_should_retry, policy=self.retry_policy)
        if expected_statuses and int(response.status_code) not in expected_statuses:
            raise HttpClientError(
                f"unexpected status code: {response.status_code}",
                request=request,
                response=response,
            )
        if not expected_statuses and not response.ok:
            raise HttpClientError(
                f"http request failed with status {response.status_code}",
                request=request,
                response=response,
            )
        return response

    def request_json(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Mapping[str, Any]] = None,
        query: Optional[Mapping[str, Any]] = None,
        json_body: Any = None,
        timeout_seconds: float = 10.0,
        expected_statuses: Optional[Iterable[int]] = None,
    ) -> HttpResponse:
        return self.request(
            HttpRequest(
                method=str(method or "GET"),
                url=str(url or ""),
                headers=merge_headers(headers),
                query=dict(query or {}),
                json_body=json_body,
                timeout_seconds=float(timeout_seconds or 10.0),
                expected_statuses=tuple(int(item) for item in (expected_statuses or ())),
            )
        )
