from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Sequence, TextIO


class AppServerBrowserProxyError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = dict(data or {})


class AppServerBrowserProxyClient:
    def __init__(
        self,
        *,
        command: Sequence[str] | None = None,
        stdin: TextIO | None = None,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self._command = list(command or [sys.executable, "-m", "cli.app_server"])
        self._stdin = stdin
        self._stdout = stdout
        self._stderr = stderr
        self._cwd = str(Path(cwd).resolve()) if cwd is not None else None
        self._env = dict(env or {})
        self._process: subprocess.Popen[str] | None = None
        self._initialized = False

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
        self.initialize()
        request_id = f"browser_proxy_{uuid.uuid4().hex[:12]}"
        params: dict[str, Any] = {
            "method": str(method or "GET"),
            "path": str(path or "").strip(),
        }
        if query is not None:
            params["query"] = dict(query)
        if body is not None:
            params["body"] = body
        if profile is not None:
            params["profile"] = str(profile)
        if timeout_ms is not None:
            params["timeoutMs"] = int(timeout_ms)
        return self._request("browser/proxy", params=params, request_id=request_id)

    def initialize(self) -> None:
        if self._initialized:
            return
        self._ensure_started()
        response = self._request(
            "initialize",
            params={"clientInfo": {"name": "agenthub-browser-proxy", "version": "1.0"}},
            request_id="init_browser_proxy",
            require_initialized=False,
        )
        if not isinstance(response, dict):
            raise AppServerBrowserProxyError("invalid initialize result")
        self._send({"method": "initialized", "params": {"browserProxy": True}})
        self._initialized = True

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
        except Exception:
            pass
        try:
            process.terminate()
            process.wait(timeout=2)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def __enter__(self) -> AppServerBrowserProxyClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _ensure_started(self) -> None:
        if self._stdin is not None and self._stdout is not None:
            return
        if self._process is None:
            self._process = subprocess.Popen(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self._cwd,
                env={**os.environ, **self._env} if self._env else None,
            )
            self._stdin = self._process.stdin
            self._stdout = self._process.stdout
            self._stderr = self._process.stderr
        if self._stdin is None or self._stdout is None:
            raise AppServerBrowserProxyError("app server transport is unavailable")

    def _request(
        self,
        method: str,
        *,
        params: dict[str, Any],
        request_id: str,
        require_initialized: bool = True,
    ) -> dict[str, Any]:
        if require_initialized:
            self._ensure_started()
        self._send({"id": request_id, "method": method, "params": params})
        response = self._read_response(request_id)
        error = response.get("error")
        if isinstance(error, dict):
            raise AppServerBrowserProxyError(
                str(error.get("message") or "app server request failed"),
                code=int(error["code"]) if error.get("code") is not None else None,
                data=dict(error.get("data") or {}) if isinstance(error.get("data"), dict) else {},
            )
        result = response.get("result")
        if not isinstance(result, dict):
            raise AppServerBrowserProxyError("invalid app server result payload")
        return dict(result)

    def _send(self, payload: dict[str, Any]) -> None:
        self._ensure_started()
        assert self._stdin is not None
        self._stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._stdin.flush()

    def _read_response(self, request_id: str) -> dict[str, Any]:
        self._ensure_started()
        assert self._stdout is not None
        while True:
            line = self._stdout.readline()
            if line == "":
                stderr_text = ""
                if self._stderr is not None:
                    try:
                        stderr_text = self._stderr.read()
                    except Exception:
                        stderr_text = ""
                detail = f" {stderr_text.strip()}" if str(stderr_text).strip() else ""
                raise AppServerBrowserProxyError(f"app server connection closed before response.{detail}".rstrip())
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("id") == request_id:
                return payload


class AppServerBrowserProxyTransport:
    def __init__(self, client: AppServerBrowserProxyClient | None = None) -> None:
        self._client = client or AppServerBrowserProxyClient()

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
        self._client.close()
