from __future__ import annotations

from typing import Any, Dict, List, Optional

from cli.agent_cli.debug_timeline import json_ready, log_timeline, timeline_debug_enabled
from cli.agent_cli.models import PromptAttachment
from cli.agent_cli.providers.chat_message_utils import ChatMessageUtilsMixin
from cli.agent_cli.providers.chat_protocol_routing import ChatProtocolRoutingMixin


class ChatCompletionsProtocolMixin(ChatProtocolRoutingMixin, ChatMessageUtilsMixin):

    def _request_extra_body(self) -> Dict[str, Any]:
        if not self.supports_reasoning:
            return {}
        if self.reasoning_mode == "enable_thinking":
            return {"enable_thinking": True}
        if self.reasoning_mode == "thinking.type":
            return {"thinking": {"type": "enabled", "clear_thinking": False}}
        return {}

    def _chat_completion_create(
        self,
        *,
        client: Any | None = None,
        timeout: int | None = None,
        model: str | None = None,
        trace_stage: str | None = None,
        trace_payload: Dict[str, Any] | None = None,
        **request_kwargs: Any,
    ) -> Any:
        payload = dict(request_kwargs)
        if model:
            payload["model"] = model
        stage = str(trace_stage or "chat_completions").strip() or "chat_completions"
        trace_meta = {
            "provider_name": str(getattr(getattr(self, "config", None), "provider_name", "") or ""),
            "base_url": str(getattr(getattr(self, "config", None), "base_url", "") or ""),
            **dict(trace_payload or {}),
        }
        timeline_enabled = getattr(self, "_chat_protocol_timeline_debug_enabled", timeline_debug_enabled)
        timeline_logger = getattr(self, "_chat_protocol_log_timeline", log_timeline)
        json_ready_fn = getattr(self, "_chat_protocol_json_ready", json_ready)
        if timeline_enabled():
            timeline_logger(
                f"{stage}.request_raw",
                request=json_ready_fn(payload),
                message_count=len(list(payload.get("messages") or [])) if isinstance(payload.get("messages"), list) else 0,
                stream=bool(payload.get("stream")),
                **trace_meta,
            )
        client = client or self.client
        if timeout:
            with_options = getattr(client, "with_options", None)
            if callable(with_options):
                client = with_options(timeout=timeout)
            else:
                payload.setdefault("timeout", timeout)
        response = client.chat.completions.create(**payload)
        if timeline_enabled():
            timeline_logger(
                f"{stage}.response_raw",
                response=json_ready_fn(response),
                **trace_meta,
            )
        return response

    def _chat_json_payload(self, *, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        if not self.policy_llm_assist:
            return {}
        try:
            route = self._effective_route_resolution("policy_helper", self._policy_helper_route())
            route_config = route.config or self.config
            request_kwargs: Dict[str, Any] = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
            }
            response = self._chat_completion_create(
                client=self._route_client("policy_helper", route_config),
                timeout=route.timeout or self.policy_llm_timeout,
                model=route_config.model,
                trace_stage="chat_completions.route_policy_helper",
                trace_payload={
                    "route_name": "policy_helper",
                    "route_source": str(route.source or ""),
                    "provider_name": str(route_config.provider_name or ""),
                    "base_url": str(route_config.base_url or ""),
                },
                **request_kwargs,
            )
            choice = response.choices[0]
            message = choice.message
            return self._parse_json_payload(self._message_content_text(getattr(message, "content", "")))
        except Exception:
            return {}

    def _chat_messages(
        self,
        user_text: str,
        history: List[Dict[str, str]],
        *,
        attachments: Optional[List[PromptAttachment]] = None,
        input_items: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        conversation_history = self._history_for_conversation(history, input_items=input_items)
        return self._chat_messages_from_input_items(
            self._conversation_input_items(
                user_text,
                conversation_history,
                attachments=attachments,
                input_items=input_items,
            ),
            system_prompt=self.system_prompt,
        )

    def _history_for_conversation(
        self,
        history: List[Dict[str, str]],
        *,
        input_items: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, str]]:
        if self._input_items_have_assistant_turn(input_items):
            return []
        return list(history or [])
