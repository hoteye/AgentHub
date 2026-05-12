from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


@dataclass(frozen=True)
class _SessionClosed:
    detail: str


class MCPTransportError(RuntimeError):
    def __init__(self, message: str, *, error_code: str = "transport-error", status_code: int | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


class StdioMcpSession:
    def __init__(
        self,
        *,
        process: subprocess.Popen[str],
        timeout_sec: float,
    ) -> None:
        self._process = process
        self._timeout_sec = max(float(timeout_sec), 0.01)
        self._reader_items: "queue.Queue[dict[str, Any] | Exception | _SessionClosed]" = queue.Queue()
        self._notification_items: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self._request_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._next_request_id = 0
        self._closed = False
        self._reader = threading.Thread(target=self._reader_loop, name="mcp-stdio-reader", daemon=True)
        self._reader.start()

    @property
    def process(self) -> subprocess.Popen[str]:
        return self._process

    def request(self, method: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        with self._request_lock:
            self._next_request_id += 1
            request_id = self._next_request_id
            self._send_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": str(method or "").strip(),
                    "params": dict(params or {}),
                }
            )
            while True:
                item = self._read_next_item()
                if isinstance(item, Exception):
                    raise item
                if isinstance(item, _SessionClosed):
                    raise MCPTransportError(item.detail, error_code="closed")
                if not isinstance(item, dict):
                    continue
                if self._capture_notification(item):
                    continue
                if item.get("id") != request_id:
                    continue
                error = item.get("error")
                if isinstance(error, dict):
                    detail = str(error.get("message") or "request failed").strip() or "request failed"
                    data = error.get("data")
                    if isinstance(data, Mapping):
                        detail_data = str(data.get("detail") or "").strip()
                        if detail_data:
                            detail = f"{detail}: {detail_data}"
                    raise MCPTransportError(detail, error_code="remote-error")
                result = item.get("result")
                if not isinstance(result, dict):
                    raise MCPTransportError("stdio session returned invalid result payload", error_code="protocol-error")
                return dict(result)

    def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        self._send_message(
            {
                "jsonrpc": "2.0",
                "method": str(method or "").strip(),
                "params": dict(params or {}),
            }
        )

    def tools_list(self) -> list[dict[str, Any]]:
        result = self.request("tools/list", {})
        raw_tools = result.get("tools")
        if not isinstance(raw_tools, list):
            return []
        return [dict(item) for item in raw_tools if isinstance(item, dict)]

    def tools_call(self, *, name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self.request(
            "tools/call",
            {
                "name": str(name or "").strip(),
                "arguments": dict(arguments or {}),
            },
        )

    def prompts_list(self) -> list[dict[str, Any]]:
        result = self.request("prompts/list", {})
        raw_prompts = result.get("prompts")
        if not isinstance(raw_prompts, list):
            return []
        return [dict(item) for item in raw_prompts if isinstance(item, dict)]

    def prompts_get(self, *, name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self.request(
            "prompts/get",
            {
                "name": str(name or "").strip(),
                "arguments": dict(arguments or {}),
            },
        )

    def resources_list(self) -> list[dict[str, Any]]:
        result = self.request("resources/list", {})
        raw_resources = result.get("resources")
        if not isinstance(raw_resources, list):
            return []
        return [dict(item) for item in raw_resources if isinstance(item, dict)]

    def resources_read(self, *, uri: str) -> dict[str, Any]:
        return self.request(
            "resources/read",
            {
                "uri": str(uri or "").strip(),
            },
        )

    def drain_notifications(self) -> list[dict[str, Any]]:
        notifications: list[dict[str, Any]] = []
        while True:
            try:
                notifications.append(self._notification_items.get_nowait())
            except queue.Empty:
                break
        return notifications

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        stdin = self._process.stdin
        if stdin is not None:
            try:
                stdin.close()
            except Exception:
                pass
        if self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=self._timeout_sec)
            except subprocess.TimeoutExpired:
                self._process.kill()
                try:
                    self._process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass
            except Exception:
                pass

    def _send_message(self, payload: Mapping[str, Any]) -> None:
        if self._closed:
            raise MCPTransportError("stdio session is closed", error_code="closed")
        stdin = self._process.stdin
        if stdin is None or self._process.poll() is not None:
            raise MCPTransportError(_closed_process_detail(self._process), error_code="closed")
        encoded = json.dumps(dict(payload), ensure_ascii=True)
        with self._write_lock:
            try:
                stdin.write(encoded + "\n")
                stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise MCPTransportError(_closed_process_detail(self._process), error_code="closed") from exc

    def _read_next_item(self) -> dict[str, Any] | Exception | _SessionClosed:
        try:
            return self._reader_items.get(timeout=self._timeout_sec)
        except queue.Empty as exc:
            raise MCPTransportError("stdio session request timeout", error_code="timeout") from exc

    def _reader_loop(self) -> None:
        stdout = self._process.stdout
        if stdout is None:
            self._reader_items.put(MCPTransportError("stdio session missing stdout", error_code="protocol-error"))
            return
        while True:
            try:
                raw_line = stdout.readline()
            except Exception as exc:
                self._reader_items.put(MCPTransportError(f"stdio session read failed: {exc}", error_code="protocol-error"))
                return
            if raw_line == "":
                self._reader_items.put(_SessionClosed(_closed_process_detail(self._process)))
                return
            line = str(raw_line or "").strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                self._reader_items.put(
                    MCPTransportError(
                        f"stdio session returned invalid json: {exc.msg}",
                        error_code="protocol-error",
                    )
                )
                return
            if not isinstance(message, dict):
                self._reader_items.put(MCPTransportError("stdio session returned non-object message", error_code="protocol-error"))
                return
            self._reader_items.put(dict(message))

    def _capture_notification(self, payload: Mapping[str, Any]) -> bool:
        if "id" in payload:
            return False
        method = str(payload.get("method") or "").strip()
        if not method:
            return False
        self._notification_items.put(
            {
                "method": method,
                "params": dict(payload.get("params") or {}) if isinstance(payload.get("params"), Mapping) else {},
            }
        )
        return True


def _build_stdio_command(command: Sequence[str], args: Sequence[str]) -> tuple[str, ...]:
    if not command:
        return ()
    normalized = tuple(str(part) for part in command if str(part))
    if not normalized:
        return ()
    normalized_args = tuple(str(part) for part in args if str(part))
    return (*normalized, *normalized_args)


def _connect_stdio_session(
    command: Sequence[str],
    env: Mapping[str, str],
    *,
    timeout_sec: float,
) -> StdioMcpSession:
    try:
        process = subprocess.Popen(
            tuple(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=dict(env),
            bufsize=1,
        )
    except OSError as exc:
        raise MCPTransportError(f"stdio process start failed: {exc}", error_code="start-failed") from exc
    return StdioMcpSession(process=process, timeout_sec=timeout_sec)


def _merged_env(env: Mapping[str, str]) -> dict[str, str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update({str(k): str(v) for k, v in env.items()})
    return merged_env


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): value for key, value in value.items()}


def _closed_process_detail(process: subprocess.Popen[str]) -> str:
    returncode = process.poll()
    if returncode is None:
        return "stdio session closed"
    stderr = ""
    stream = process.stderr
    if stream is not None:
        try:
            stderr = str(stream.read() or "").strip()
        except Exception:
            stderr = ""
    if stderr:
        return f"stdio process exited: {stderr}"
    return f"stdio process exited with code {returncode}"


def _validated_http_url(config: Any):
    url = str(getattr(config, "url", "") or "").strip()
    if not url:
        raise MCPTransportError(f"{getattr(config, 'transport', '-')}", error_code="invalid-config")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise MCPTransportError(f"unsupported url scheme: {parsed.scheme or '-'}", error_code="invalid-config")
    if not parsed.netloc:
        raise MCPTransportError("url must include host", error_code="invalid-config")
    return parsed
