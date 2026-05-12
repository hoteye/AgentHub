from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from queue import Empty, Queue
from typing import Any

from cli.agent_cli.runtime_kernels.codex_sidecar.errors import (
    CodexSidecarProcessError,
    CodexSidecarProtocolError,
    CodexSidecarRequestError,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.protocol import (
    JsonObject,
    JsonRpcNotification,
    JsonRpcServerRequest,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.supervisor import CodexSidecarSupervisor


class CodexSidecarClient:
    def __init__(
        self,
        supervisor: CodexSidecarSupervisor,
        *,
        request_timeout: float = 30.0,
    ) -> None:
        self.supervisor = supervisor
        self.request_timeout = request_timeout
        self._request_id = 0
        self._responses: dict[int, Queue[JsonObject]] = {}
        self._notifications: Queue[JsonRpcNotification] = Queue()
        self._server_requests: Queue[JsonRpcServerRequest] = Queue()
        self._deferred_notifications: list[JsonRpcNotification] = []
        self._deferred_server_requests: list[JsonRpcServerRequest] = []
        self._started = False
        self._request_lock = threading.Lock()
        self._responses_lock = threading.Lock()
        self._notifications_lock = threading.Lock()
        self._server_requests_lock = threading.Lock()

    def start(self) -> None:
        if self._started and self.supervisor.is_running:
            return
        proc = self.supervisor.start()
        if proc.stdout is None or proc.stdin is None:
            raise CodexSidecarProcessError("sidecar stdio is unavailable")
        threading.Thread(target=self._read_stdout, daemon=True).start()
        self._started = True

    def initialize(
        self,
        *,
        client_name: str = "agenthub_codex_sidecar",
        client_title: str = "AgentHub Codex Sidecar",
        client_version: str = "0.1.0",
        experimental_api: bool = True,
    ) -> JsonObject:
        result = self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": client_name,
                    "title": client_title,
                    "version": client_version,
                },
                "capabilities": {
                    "experimentalApi": experimental_api,
                },
            },
        )
        self.notify("initialized")
        return result

    def request(self, method: str, params: JsonObject | None = None) -> JsonObject:
        self.start()
        with self._request_lock:
            self._request_id += 1
            request_id = self._request_id
            response_queue: Queue[JsonObject] = Queue(maxsize=1)
            with self._responses_lock:
                self._responses[request_id] = response_queue
            message: JsonObject = {"id": request_id, "method": method}
            if params is not None:
                message["params"] = params
            try:
                self._send(message)
            except Exception:
                with self._responses_lock:
                    self._responses.pop(request_id, None)
                raise
        try:
            return self._wait_for_response(request_id, response_queue)
        finally:
            with self._responses_lock:
                self._responses.pop(request_id, None)

    def notify(self, method: str, params: JsonObject | None = None) -> None:
        self.start()
        message: JsonObject = {"method": method}
        if params is not None:
            message["params"] = params
        self._send(message)

    def respond_to_server_request(
        self,
        request: JsonRpcServerRequest | int | str,
        response: JsonObject,
    ) -> None:
        self.start()
        if isinstance(request, JsonRpcServerRequest):
            request_id = request.request_id
        else:
            request_id = request
        payload = dict(response or {})
        if isinstance(payload.get("error"), dict):
            message: JsonObject = {"id": request_id, "error": dict(payload["error"])}
        else:
            message = {"id": request_id, "result": payload}
        self._send(message)

    def get_server_request(self, timeout: float | None = None) -> JsonRpcServerRequest | None:
        request = self._pop_deferred_server_request()
        if request is not None:
            return request
        try:
            return self._server_requests.get(timeout=timeout or 0)
        except Empty:
            return None

    def get_server_request_matching(
        self,
        predicate: Callable[[JsonRpcServerRequest], bool],
        *,
        timeout: float | None = None,
    ) -> JsonRpcServerRequest | None:
        deadline = time.monotonic() + max(0.0, timeout or 0.0)
        while True:
            request = self._pop_deferred_server_request(predicate)
            if request is not None:
                return request
            remaining = max(0.0, deadline - time.monotonic())
            try:
                request = self._server_requests.get(timeout=remaining)
            except Empty:
                return None
            if predicate(request):
                return request
            self._defer_server_request(request)

    def get_notification(self, timeout: float | None = None) -> JsonRpcNotification | None:
        notification = self._pop_deferred_notification()
        if notification is not None:
            return notification
        try:
            return self._notifications.get(timeout=timeout or 0)
        except Empty:
            return None

    def get_notification_matching(
        self,
        predicate: Callable[[JsonRpcNotification], bool],
        *,
        timeout: float | None = None,
    ) -> JsonRpcNotification | None:
        deadline = time.monotonic() + max(0.0, timeout or 0.0)
        while True:
            notification = self._pop_deferred_notification(predicate)
            if notification is not None:
                return notification
            remaining = max(0.0, deadline - time.monotonic())
            try:
                notification = self._notifications.get(timeout=remaining)
            except Empty:
                return None
            if predicate(notification):
                return notification
            self._defer_notification(notification)

    def drain_notifications(self) -> list[JsonRpcNotification]:
        notifications: list[JsonRpcNotification] = []
        while True:
            notification = self.get_notification(timeout=0)
            if notification is None:
                return notifications
            notifications.append(notification)

    def drain_server_requests(self) -> list[JsonRpcServerRequest]:
        requests: list[JsonRpcServerRequest] = []
        while True:
            request = self.get_server_request(timeout=0)
            if request is None:
                return requests
            requests.append(request)

    def close(self) -> None:
        self.supervisor.close()
        self._started = False
        with self._notifications_lock:
            self._deferred_notifications.clear()
        with self._server_requests_lock:
            self._deferred_server_requests.clear()

    def _send(self, message: JsonObject) -> None:
        proc = self._require_process()
        if proc.stdin is None:
            raise CodexSidecarProcessError("sidecar stdin is unavailable")
        if proc.poll() is not None:
            raise CodexSidecarProcessError(
                "sidecar exited before send: "
                f"code={proc.returncode}, stderr={self.supervisor.stderr_tail()}"
            )
        line = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        try:
            proc.stdin.write(line + "\n")
            proc.stdin.flush()
        except OSError as exc:
            raise CodexSidecarProcessError(str(exc)) from exc

    def _wait_for_response(
        self,
        request_id: int,
        response_queue: Queue[JsonObject],
    ) -> JsonObject:
        deadline = time.monotonic() + self.request_timeout
        while True:
            proc = self._require_process()
            if proc.poll() is not None and response_queue.empty():
                raise CodexSidecarProcessError(
                    f"sidecar exited while waiting for id={request_id}: "
                    f"code={proc.returncode}, stderr={self.supervisor.stderr_tail()}"
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CodexSidecarRequestError(
                    f"timeout waiting for id={request_id}; stderr={self.supervisor.stderr_tail()}"
                )
            try:
                payload = response_queue.get(timeout=min(0.25, remaining))
            except Empty:
                continue
            if "error" in payload:
                error = payload.get("error")
                message = (
                    str(error.get("message") or "JSON-RPC error")
                    if isinstance(error, dict)
                    else "JSON-RPC error"
                )
                raise CodexSidecarRequestError(
                    f"{message}: {json.dumps(error, ensure_ascii=False)}"
                )
            result = payload.get("result")
            return dict(result or {}) if isinstance(result, dict) else {"value": result}

    def _read_stdout(self) -> None:
        proc = self._require_process()
        assert proc.stdout is not None
        for line in proc.stdout:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                self._notifications.put(
                    JsonRpcNotification(
                        method="$agenthub/protocolError",
                        params={"error": str(exc), "line": stripped},
                    )
                )
                continue
            if isinstance(payload, dict):
                self._route_payload(payload)
                continue
            self._notifications.put(
                JsonRpcNotification(
                    method="$agenthub/protocolError",
                    params={
                        "error": "non-object JSON-RPC payload",
                        "value": payload,
                    },
                )
            )

    def _require_process(self) -> Any:
        proc = self.supervisor.process
        if proc is None:
            raise CodexSidecarProcessError("sidecar is not started")
        return proc

    def _pop_deferred_notification(
        self,
        predicate: Callable[[JsonRpcNotification], bool] | None = None,
    ) -> JsonRpcNotification | None:
        with self._notifications_lock:
            if predicate is None:
                return self._deferred_notifications.pop(0) if self._deferred_notifications else None
            for index, notification in enumerate(self._deferred_notifications):
                if predicate(notification):
                    return self._deferred_notifications.pop(index)
        return None

    def _defer_notification(self, notification: JsonRpcNotification) -> None:
        with self._notifications_lock:
            self._deferred_notifications.append(notification)

    def _pop_deferred_server_request(
        self,
        predicate: Callable[[JsonRpcServerRequest], bool] | None = None,
    ) -> JsonRpcServerRequest | None:
        with self._server_requests_lock:
            if predicate is None:
                return (
                    self._deferred_server_requests.pop(0)
                    if self._deferred_server_requests
                    else None
                )
            for index, request in enumerate(self._deferred_server_requests):
                if predicate(request):
                    return self._deferred_server_requests.pop(index)
        return None

    def _defer_server_request(self, request: JsonRpcServerRequest) -> None:
        with self._server_requests_lock:
            self._deferred_server_requests.append(request)

    def _route_payload(self, payload: JsonObject) -> None:
        if _is_notification(payload):
            try:
                self._notifications.put(_notification_from_payload(payload))
            except CodexSidecarProtocolError as exc:
                self._notifications.put(
                    JsonRpcNotification(
                        method="$agenthub/protocolError",
                        params={"error": str(exc), "payload": payload},
                        raw=payload,
                    )
                )
            return
        if _is_server_request(payload):
            try:
                self._server_requests.put(_server_request_from_payload(payload))
            except CodexSidecarProtocolError as exc:
                self._notifications.put(
                    JsonRpcNotification(
                        method="$agenthub/protocolError",
                        params={"error": str(exc), "payload": payload},
                        raw=payload,
                    )
                )
            return
        raw_request_id = payload.get("id")
        if isinstance(raw_request_id, int):
            request_id = raw_request_id
        elif isinstance(raw_request_id, str) and raw_request_id.isdigit():
            request_id = int(raw_request_id)
        else:
            self._notifications.put(
                JsonRpcNotification(
                    method="$agenthub/protocolError",
                    params={"error": "JSON-RPC response id is required", "payload": payload},
                    raw=payload,
                )
            )
            return
        with self._responses_lock:
            response_queue = self._responses.get(request_id)
        if response_queue is None:
            self._notifications.put(
                JsonRpcNotification(
                    method="$agenthub/unmatchedResponse",
                    params={"requestId": request_id, "payload": payload},
                    raw=payload,
                )
            )
            return
        response_queue.put(payload)


def _is_notification(payload: JsonObject) -> bool:
    return "method" in payload and "id" not in payload


def _is_server_request(payload: JsonObject) -> bool:
    return "method" in payload and "id" in payload and "params" in payload


def _notification_from_payload(payload: JsonObject) -> JsonRpcNotification:
    method = str(payload.get("method") or "")
    if not method:
        raise CodexSidecarProtocolError("notification method is required")
    params = payload.get("params")
    return JsonRpcNotification(
        method=method,
        params=dict(params or {}) if isinstance(params, dict) else {"value": params},
        raw=payload,
    )


def _server_request_from_payload(payload: JsonObject) -> JsonRpcServerRequest:
    method = str(payload.get("method") or "")
    if not method:
        raise CodexSidecarProtocolError("server request method is required")
    request_id = payload.get("id")
    if not isinstance(request_id, int | str):
        raise CodexSidecarProtocolError("server request id is required")
    params = payload.get("params")
    return JsonRpcServerRequest(
        request_id=request_id,
        method=method,
        params=dict(params or {}) if isinstance(params, dict) else {"value": params},
        raw=payload,
    )
