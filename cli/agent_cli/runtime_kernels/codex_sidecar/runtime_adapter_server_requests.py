from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_kernels.codex_sidecar import approval as codex_approval
from cli.agent_cli.runtime_kernels.codex_sidecar.protocol import JsonRpcServerRequest
from cli.agent_cli.runtime_kernels.codex_sidecar.server_requests import (
    CodexServerRequestEnvelope,
    unsupported_server_request_response,
)


class CodexSidecarRuntimeServerRequestsMixin:
    def _drain_server_requests_for_turn(
        self,
        *,
        mapper: Any,
        thread_id: str,
        turn_id: str,
    ) -> None:
        def matches_server_request(request: Any) -> bool:
            return _server_request_matches_turn(
                request.params,
                thread_id=thread_id,
                turn_id=turn_id,
                method=request.method,
            )

        server_request = self.kernel.client.get_server_request_matching(
            matches_server_request,
            timeout=0,
        )
        while server_request is not None:
            mapper.raw_events.append(
                {
                    "type": "codex_sidecar.server_request",
                    "method": server_request.method,
                    "params": dict(server_request.params or {}),
                    "raw_event": dict(server_request.raw or {}),
                }
            )
            self._handle_server_request(server_request)
            server_request = self.kernel.client.get_server_request_matching(
                matches_server_request,
                timeout=0,
            )

    def _handle_server_request(self, request: Any) -> None:
        envelope = self._server_request_registry.dispatch(
            self,
            request,
            respond=self.kernel.client.respond_to_server_request,
            unsupported_response=unsupported_server_request_response,
        )
        if envelope.status == "unsupported":
            activity = _activity_for_unsupported_server_request(envelope)
            callback = self.activity_callback
            if callable(callback):
                try:
                    callback(activity)
                except Exception:
                    pass

    def _handle_approval_server_request(
        self,
        envelope: CodexServerRequestEnvelope,
    ) -> None:
        request = _server_request_from_envelope(envelope)
        tool_event = codex_approval.register_approval(self, request)
        approval_id = str((tool_event.payload or {}).get("approval_id") or "").strip()
        if approval_id:
            with self._pending_sidecar_approval_lock:
                self._pending_sidecar_approval_requests[approval_id] = request
        activity = codex_approval.activity_for_approval(
            request,
            approval_id=approval_id,
            available_decisions=list((tool_event.payload or {}).get("available_decisions") or []),
        )
        callback = self.activity_callback
        if callable(callback):
            try:
                callback(activity)
            except Exception:
                pass

    def _handle_tool_request_user_input(
        self,
        envelope: CodexServerRequestEnvelope,
    ) -> dict[str, object]:
        handler = getattr(self, "request_user_input_handler", None)
        if not callable(handler):
            self._emit_server_request_diagnostic(
                envelope,
                "Codex sidecar user input request cancelled",
                "request_user_input_handler is not configured",
            )
            return {"answers": {}}
        params = dict(envelope.params or {})
        payload = {"questions": _normalize_codex_request_user_input_questions(params)}
        try:
            response = handler(payload)
        except Exception as exc:
            self._emit_server_request_diagnostic(
                envelope,
                "Codex sidecar user input request failed",
                str(exc),
            )
            return {"answers": {}}
        if not isinstance(response, dict):
            self._emit_server_request_diagnostic(
                envelope,
                "Codex sidecar user input request returned invalid response",
                f"response_type={type(response).__name__}",
            )
            return {"answers": {}}
        return {"answers": dict(response.get("answers") or {})}

    def _handle_mcp_elicitation_request(
        self,
        envelope: CodexServerRequestEnvelope,
    ) -> dict[str, object]:
        handler = getattr(self, "request_user_input_handler", None)
        if not callable(handler):
            self._emit_server_request_diagnostic(
                envelope,
                "Codex sidecar MCP elicitation cancelled",
                "request_user_input_handler is not configured",
            )
            return {"action": "cancel", "content": None}
        params = dict(envelope.params or {})
        mode = str(params.get("mode") or "").strip()
        message = str(params.get("message") or "").strip()
        server_name = str(params.get("serverName") or "").strip()
        if mode == "url":
            url = str(params.get("url") or "").strip()
            question = f"{message}\n{url}".strip() if url else message
        else:
            question = message or f"MCP server {server_name} requested input."
        payload = {
            "questions": [
                {
                    "id": "mcp_elicitation",
                    "header": server_name or "MCP",
                    "question": question or "MCP server requested input.",
                    "options": [
                        {"label": "Accept", "description": "Send an accept response."},
                        {"label": "Decline", "description": "Send a decline response."},
                    ],
                }
            ]
        }
        try:
            response = handler(payload)
        except Exception as exc:
            self._emit_server_request_diagnostic(
                envelope,
                "Codex sidecar MCP elicitation failed",
                str(exc),
            )
            return {"action": "cancel", "content": None}
        if not isinstance(response, dict):
            self._emit_server_request_diagnostic(
                envelope,
                "Codex sidecar MCP elicitation returned invalid response",
                f"response_type={type(response).__name__}",
            )
            return {"action": "cancel", "content": None}
        answers = dict(response.get("answers") or {})
        selected = ""
        raw_answer = answers.get("mcp_elicitation")
        if isinstance(raw_answer, dict):
            values = raw_answer.get("answers")
            if isinstance(values, list) and values:
                selected = str(values[0] or "").strip().lower()
        else:
            self._emit_server_request_diagnostic(
                envelope,
                "Codex sidecar MCP elicitation answer ignored",
                "missing answers.mcp_elicitation.answers",
            )
        if selected.startswith("accept"):
            return {"action": "accept", "content": {}}
        if selected.startswith("decline"):
            return {"action": "decline", "content": None}
        return {"action": "cancel", "content": None}

    def _emit_server_request_diagnostic(
        self,
        envelope: CodexServerRequestEnvelope,
        title: str,
        detail: str,
    ) -> None:
        callback = self.activity_callback
        if not callable(callback):
            return
        try:
            callback(_activity_for_server_request_diagnostic(envelope, title, detail))
        except Exception:
            pass


def _server_request_matches_turn(
    params: dict[str, Any],
    *,
    thread_id: str,
    turn_id: str,
    method: str,
) -> bool:
    if method.startswith("$agenthub/"):
        return True
    raw_thread_id = str(params.get("threadId") or params.get("thread_id") or "").strip()
    if raw_thread_id and raw_thread_id != thread_id:
        return False
    raw_turn_id = str(params.get("turnId") or params.get("turn_id") or "").strip()
    if raw_turn_id and turn_id and raw_turn_id != turn_id:
        return False
    return bool(raw_thread_id or raw_turn_id)


def _server_request_from_envelope(envelope: CodexServerRequestEnvelope) -> JsonRpcServerRequest:
    return JsonRpcServerRequest(
        request_id=envelope.request_id,
        method=envelope.method,
        params=dict(envelope.params or {}),
        raw=dict(envelope.raw or {}),
    )


def _activity_for_unsupported_server_request(envelope: CodexServerRequestEnvelope) -> Any:
    from cli.agent_cli.models import ActivityEvent

    return ActivityEvent(
        title="Unsupported Codex sidecar request",
        status="error",
        detail=f"{envelope.method}\nrequest_id={envelope.request_id}",
        kind="codex_sidecar",
        code="codex_sidecar.unsupported_server_request",
        params={
            **envelope.to_event(),
            "params": dict(envelope.params or {}),
        },
    )


def _activity_for_server_request_diagnostic(
    envelope: CodexServerRequestEnvelope,
    title: str,
    detail: str,
) -> Any:
    from cli.agent_cli.models import ActivityEvent

    return ActivityEvent(
        title=title,
        status="warning",
        detail=f"{detail}\nrequest_id={envelope.request_id}",
        kind="codex_sidecar",
        code="codex_sidecar.server_request_diagnostic",
        params={
            **envelope.to_event(),
            "diagnostic": str(detail or "").strip(),
        },
    )


def _normalize_codex_request_user_input_questions(params: dict[str, Any]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for item in list(params.get("questions") or []):
        if not isinstance(item, dict):
            continue
        raw_options = item.get("options")
        options = []
        if isinstance(raw_options, list):
            options = [
                {
                    "label": str(option.get("label") or "").strip(),
                    "description": str(option.get("description") or "").strip()
                    or str(option.get("label") or "").strip(),
                }
                for option in raw_options
                if isinstance(option, dict) and str(option.get("label") or "").strip()
            ]
        if not options:
            options = [
                {"label": "OK", "description": "Continue."},
                {"label": "Cancel", "description": "Cancel this request."},
            ]
        questions.append(
            {
                "id": str(item.get("id") or "").strip(),
                "header": str(item.get("header") or "").strip() or "Input",
                "question": str(item.get("question") or "").strip() or "Provide input.",
                "options": options,
            }
        )
    return questions
