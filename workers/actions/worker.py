#!/usr/bin/env python3
"""Structured worker for allowlisted action execution."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

from shared.integrations import HttpClient, HttpClientError, HttpRequest, build_bearer_auth_headers, merge_headers, redact_headers
from .protocol import ActionError, ActionRequest, ActionResult


ActionHandler = Callable[[ActionRequest], ActionResult]


def _resolve_within_root(path: str, *, allowed_root: str) -> Path:
    root = Path(allowed_root).expanduser().resolve()
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = root / target
    resolved = target.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ActionError(f"path escapes allowed_root: {resolved}") from exc
    return resolved


class ControlledActionWorker:
    def __init__(self, *, http_client: HttpClient | None = None) -> None:
        self.http_client = http_client or HttpClient()
        self._handlers: dict[str, ActionHandler] = {
            "noop": self._handle_noop,
            "write_json_file": self._handle_write_json_file,
            "append_jsonl": self._handle_append_jsonl,
            "http_request": self._handle_http_request,
        }

    def supported_actions(self) -> list[str]:
        return sorted(self._handlers.keys())

    def execute(self, request: ActionRequest | dict[str, Any]) -> ActionResult:
        action_request = request if isinstance(request, ActionRequest) else ActionRequest.from_mapping(request)
        action_name = str(action_request.action or "").strip()
        if not action_name:
            raise ActionError("action is required")
        handler = self._handlers.get(action_name)
        if handler is None:
            raise ActionError(f"action not allowed: {action_name}")
        return handler(action_request)

    def _base_result(self, request: ActionRequest, *, summary: str, output: dict[str, Any]) -> ActionResult:
        return ActionResult(
            ok=True,
            action=request.action,
            summary=summary,
            output=output,
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            run_id=request.run_id,
            agent_id=request.agent_id,
        )

    def _handle_noop(self, request: ActionRequest) -> ActionResult:
        return self._base_result(
            request,
            summary="noop action completed",
            output={"parameters": dict(request.parameters)},
        )

    def _handle_write_json_file(self, request: ActionRequest) -> ActionResult:
        allowed_root = str(request.parameters.get("allowed_root") or "").strip()
        path = str(request.parameters.get("path") or "").strip()
        if not allowed_root:
            raise ActionError("allowed_root is required")
        if not path:
            raise ActionError("path is required")
        data = request.parameters.get("data")
        target = _resolve_within_root(path, allowed_root=allowed_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return self._base_result(
            request,
            summary=f"json file written: {target.name}",
            output={"path": str(target), "bytes_written": len(target.read_bytes())},
        )

    def _handle_append_jsonl(self, request: ActionRequest) -> ActionResult:
        allowed_root = str(request.parameters.get("allowed_root") or "").strip()
        path = str(request.parameters.get("path") or "").strip()
        if not allowed_root:
            raise ActionError("allowed_root is required")
        if not path:
            raise ActionError("path is required")
        record = request.parameters.get("record")
        target = _resolve_within_root(path, allowed_root=allowed_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return self._base_result(
            request,
            summary=f"jsonl record appended: {target.name}",
            output={"path": str(target)},
        )

    @staticmethod
    def _string_mapping(value: Any, *, field_name: str) -> dict[str, str]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise ActionError(f"{field_name} must be an object")
        return {str(key): str(item) for key, item in value.items()}

    @staticmethod
    def _host_allowed(url: str, allowed_hosts: list[str]) -> bool:
        parsed = urlparse(str(url or ""))
        if parsed.scheme not in {"http", "https"}:
            return False
        host = str(parsed.hostname or "").lower()
        if not host:
            return False
        allowed = {str(item or "").strip().lower() for item in allowed_hosts if str(item or "").strip()}
        return host in allowed

    @staticmethod
    def _auth_headers(parameters: Mapping[str, Any]) -> dict[str, str]:
        auth = parameters.get("auth")
        if auth is None:
            return {}
        if not isinstance(auth, Mapping):
            raise ActionError("auth must be an object")
        auth_type = str(auth.get("type") or "").strip().lower()
        if auth_type == "bearer_env":
            token_env = str(auth.get("token_env") or "").strip()
            if not token_env:
                raise ActionError("auth.token_env is required for bearer_env")
            token = str(os.environ.get(token_env) or "").strip()
            if not token:
                raise ActionError(f"auth token env not set: {token_env}")
            return build_bearer_auth_headers(token)
        raise ActionError(f"auth type not supported: {auth_type}")

    def _handle_http_request(self, request: ActionRequest) -> ActionResult:
        parameters = dict(request.parameters)
        method = str(parameters.get("method") or "GET").strip().upper()
        url = str(parameters.get("url") or "").strip()
        if not url:
            raise ActionError("url is required")
        raw_allowed_hosts = parameters.get("allowed_hosts")
        if not isinstance(raw_allowed_hosts, list) or not raw_allowed_hosts:
            raise ActionError("allowed_hosts must be a non-empty list")
        allowed_hosts = [str(item or "").strip() for item in raw_allowed_hosts if str(item or "").strip()]
        if not self._host_allowed(url, allowed_hosts):
            raise ActionError(f"url host not allowed: {url}")
        headers = merge_headers(
            self._auth_headers(parameters),
            self._string_mapping(parameters.get("headers"), field_name="headers"),
        )
        query = parameters.get("query")
        if query is not None and not isinstance(query, Mapping):
            raise ActionError("query must be an object")
        expected_statuses = parameters.get("expected_statuses")
        if expected_statuses is not None and not isinstance(expected_statuses, list):
            raise ActionError("expected_statuses must be a list")
        try:
            response = self.http_client.request(
                HttpRequest(
                    method=method,
                    url=url,
                    headers=headers,
                    query=dict(query or {}),
                    body_text=str(parameters.get("body_text")) if parameters.get("body_text") is not None else None,
                    json_body=parameters.get("json_body"),
                    timeout_seconds=float(parameters.get("timeout_seconds") or 10.0),
                    expected_statuses=tuple(int(item) for item in (expected_statuses or ())),
                )
            )
        except HttpClientError as exc:
            detail = f"http request failed: {exc}"
            if exc.response is not None:
                detail = f"{detail} (status={exc.response.status_code})"
            raise ActionError(detail) from exc
        return self._base_result(
            request,
            summary=f"http request completed: {method} {urlparse(url).netloc}",
            output={
                "status_code": int(response.status_code),
                "url": response.url,
                "request_headers": redact_headers(headers),
                "response_headers": dict(response.headers),
                "text": response.text,
                "json_data": response.json_data,
            },
        )


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Controlled action worker")
    parser.add_argument("--request-json", help="JSON payload containing one action request")
    args = parser.parse_args(argv)

    if not args.request_json:
        parser.error("--request-json is required")

    request_payload = json.loads(args.request_json)
    worker = ControlledActionWorker()
    try:
        result = worker.execute(request_payload)
    except ActionError as exc:
        payload = ActionResult(
            ok=False,
            action=str(request_payload.get("action") or ""),
            summary="action failed",
            error=str(exc),
            request_id=str(request_payload.get("request_id") or "").strip() or None,
            correlation_id=str(request_payload.get("correlation_id") or "").strip() or None,
            run_id=str(request_payload.get("run_id") or "").strip() or None,
            agent_id=str(request_payload.get("agent_id") or "").strip() or None,
        ).to_dict()
    else:
        payload = result.to_dict()
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
