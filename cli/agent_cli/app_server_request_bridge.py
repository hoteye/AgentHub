from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from cli.agent_cli.runtime_core.tool_call_context_runtime import (
    current_app_server_turn_id,
    current_provider_tool_call_id,
)


@dataclass
class _PendingServerRequest:
    request_id: Any
    method: str
    params: dict[str, Any]
    thread_id: str
    response_event: threading.Event = field(default_factory=threading.Event)
    response_payload: dict[str, Any] | None = None
    response_error: dict[str, Any] | None = None


def _handle_server_request_response(
    *,
    message: dict[str, Any],
    pending_server_requests_lock: threading.Lock,
    pending_server_requests: dict[str, _PendingServerRequest],
    emit_notification: Callable[[str, dict[str, Any]], None],
) -> bool:
    if "method" in message:
        return False
    request_id = message.get("id")
    if request_id is None:
        return False
    request_key = str(request_id)
    with pending_server_requests_lock:
        pending = pending_server_requests.get(request_key)
    if pending is None:
        return False
    result = message.get("result")
    error = message.get("error")
    pending.response_payload = dict(result) if isinstance(result, dict) else None
    pending.response_error = dict(error) if isinstance(error, dict) else None
    emit_notification(
        "serverRequest/resolved",
        {
            "threadId": pending.thread_id,
            "requestId": pending.request_id,
        },
    )
    pending.response_event.set()
    return True


def _abort_pending_server_requests(
    *,
    pending_server_requests_lock: threading.Lock,
    pending_server_requests: dict[str, _PendingServerRequest],
) -> None:
    with pending_server_requests_lock:
        pending_requests = list(pending_server_requests.values())
        pending_server_requests.clear()
    for pending in pending_requests:
        pending.response_error = {
            "code": -32050,
            "message": "Client disconnected before resolving server request",
        }
        pending.response_event.set()


def _make_request_user_input_handler(
    *,
    request_id: Any,
    request_thread_id: Callable[[Any], str],
    request_user_input_via_client: Callable[..., dict[str, Any] | None],
) -> Callable[[dict[str, Any]], dict[str, Any] | None]:
    thread_id = request_thread_id(request_id)

    def handler(payload: dict[str, Any]) -> dict[str, Any] | None:
        return request_user_input_via_client(
            payload=payload,
            thread_id=thread_id,
        )

    return handler


def _request_user_input_via_client(
    *,
    payload: dict[str, Any],
    thread_id: str,
    pending_server_requests_lock: threading.Lock,
    pending_server_requests: dict[str, _PendingServerRequest],
    emit: Callable[[dict[str, Any]], None],
) -> dict[str, Any] | None:
    questions: list[dict[str, Any]] = []
    for item in list(payload.get("questions") or []):
        if not isinstance(item, dict):
            continue
        normalized_question: dict[str, Any] = {
            "id": str(item.get("id") or "").strip(),
            "header": str(item.get("header") or "").strip(),
            "question": str(item.get("question") or "").strip(),
            "isOther": bool(item.get("isOther") if "isOther" in item else item.get("is_other")),
            "isSecret": bool(item.get("isSecret") if "isSecret" in item else item.get("is_secret")),
        }
        options = item.get("options")
        if isinstance(options, list):
            normalized_question["options"] = [
                {
                    "label": str(option.get("label") or "").strip(),
                    "description": str(option.get("description") or "").strip(),
                }
                for option in options
                if isinstance(option, dict)
            ]
        else:
            normalized_question["options"] = None
        questions.append(normalized_question)
    turn_id = current_app_server_turn_id() or f"turn_{uuid.uuid4().hex}"
    item_id = current_provider_tool_call_id() or f"call_{uuid.uuid4().hex}"
    pending = _PendingServerRequest(
        request_id=f"server_req_{uuid.uuid4().hex}",
        method="item/tool/requestUserInput",
        params={
            "threadId": thread_id,
            "turnId": turn_id,
            "itemId": item_id,
            "questions": questions,
        },
        thread_id=thread_id,
    )
    with pending_server_requests_lock:
        pending_server_requests[str(pending.request_id)] = pending
    try:
        emit(
            {
                "id": pending.request_id,
                "method": pending.method,
                "params": pending.params,
            }
        )
        pending.response_event.wait()
        if pending.response_error is not None:
            return None
        if pending.response_payload is None:
            return None
        return dict(pending.response_payload)
    finally:
        with pending_server_requests_lock:
            pending_server_requests.pop(str(pending.request_id), None)
