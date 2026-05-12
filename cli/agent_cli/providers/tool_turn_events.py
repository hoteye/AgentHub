from __future__ import annotations

from typing import Any, Dict, List, Optional

from cli.agent_cli import models_mapping_runtime as models_mapping_runtime_service
from cli.agent_cli.models import (
    CommandExecutionResult,
    FunctionCallOutputPayload,
    ResponseInputItem,
    compose_turn_events_from_response_items,
    response_items_to_text,
    tool_events_to_turn_events,
)
from cli.agent_cli.media_content_runtime import (
    image_content_items_from_output,
    input_image_item_from_image_block,
)
from cli.agent_cli.image_transport_runtime import (
    image_transport_family_for_tool,
    image_transport_subject,
    normalize_image_transport_family,
)


class ToolTurnEventsMixin:
    @classmethod
    def _document_output_projection(cls, output: Any) -> Dict[str, Any] | None:
        del cls
        return models_mapping_runtime_service.view_document_output_projection(output)

    @classmethod
    def _image_output_items(cls, output: Any) -> List[Dict[str, Any]] | None:
        del cls
        return image_content_items_from_output(
            output,
            image_item_normalizer=input_image_item_from_image_block,
        )

    @classmethod
    def _synthetic_function_call_output_event(
        cls,
        execution: CommandExecutionResult,
        *,
        start_index: int,
        existing_item_events: List[Dict[str, Any]],
    ) -> Dict[str, Any] | None:
        for raw_event in list(existing_item_events or []):
            if not isinstance(raw_event, dict):
                continue
            item = raw_event.get("item")
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "").strip() in {
                "function_call_output",
                "custom_tool_call_output",
                "shell_call_output",
                "local_shell_call_output",
            }:
                return None

        selected_event = None
        explicit_output = None
        document_projection = None
        projected_output = None
        output_items = None
        for raw_event in reversed(list(execution.tool_events or [])):
            payload = dict(getattr(raw_event, "payload", {}) or {})
            if bool(payload.get("function_call_output_model_visible")) and payload.get("function_call_output") is not None:
                selected_event = raw_event
                explicit_output = payload.get("function_call_output")
                document_projection = None
                output_items = None
                break
            document_projection = cls._document_output_projection(payload.get("function_call_output"))
            if document_projection is None:
                document_projection = cls._document_output_projection(payload)
            if document_projection is not None and bool(document_projection.get("model_visible")):
                selected_event = raw_event
                projected_output = document_projection.get("output")
                break
            output_items = cls._image_output_items(payload.get("function_call_output"))
            if output_items is None:
                output_items = cls._image_output_items(payload)
            if output_items:
                selected_event = raw_event
                break
        if selected_event is None:
            return None

        payload = dict(getattr(selected_event, "payload", {}) or {})
        call_id = str(payload.get("provider_call_id") or payload.get("call_id") or "").strip()
        if not call_id:
            return None
        output_item_type = (
            "custom_tool_call_output"
            if str(payload.get("provider_tool_type") or "").strip().lower() == "custom_tool_call"
            else "function_call_output"
        )
        if explicit_output is not None:
            output_payload = FunctionCallOutputPayload.from_output(
                explicit_output,
                success=bool(getattr(selected_event, "ok", False)),
            )
            item: Dict[str, Any] = {
                "id": f"item_{int(start_index)}",
                "type": output_item_type,
                "call_id": call_id,
                "output": output_payload.wire_value(),
            }
            if output_payload.success is not None:
                item["success"] = output_payload.success
            return {
                "type": "item.completed",
                "item": item,
            }
        if document_projection is not None and bool(document_projection.get("model_visible")):
            output_payload = FunctionCallOutputPayload.from_output(
                projected_output,
                success=bool(getattr(selected_event, "ok", False)),
            )
            item: Dict[str, Any] = {
                "id": f"item_{int(start_index)}",
                "type": output_item_type,
                "call_id": call_id,
                "output": output_payload.wire_value(),
            }
            projection_mode = str(document_projection.get("projection_mode") or "").strip()
            projection_state = str(document_projection.get("projection_state") or "").strip()
            projection_subject = str(document_projection.get("subject") or "").strip()
            if projection_mode:
                item["document_projection_mode"] = projection_mode
            if projection_state:
                item["document_projection_state"] = projection_state
            if projection_subject:
                item["document_projection_subject"] = projection_subject
            if output_payload.success is not None:
                item["success"] = output_payload.success
            return {
                "type": "item.completed",
                "item": item,
            }
        if not output_items:
            return None
        output_payload = FunctionCallOutputPayload.from_output(
            output_items,
            success=bool(getattr(selected_event, "ok", False)),
        )
        image_transport_family = cls._image_transport_family(selected_event)
        item: Dict[str, Any] = {
            "id": f"item_{int(start_index)}",
            "type": output_item_type,
            "call_id": call_id,
            "output": output_payload.wire_value(),
        }
        if image_transport_family:
            item["image_transport_family"] = image_transport_family
        image_transport_subject = cls._image_transport_subject(payload, output_items)
        if image_transport_subject:
            item["image_transport_subject"] = image_transport_subject
        if output_payload.success is not None:
            item["success"] = output_payload.success
        return {
            "type": "item.completed",
            "item": item,
        }

    @staticmethod
    def _normalize_image_transport_family(value: str) -> str:
        return normalize_image_transport_family(value)

    @classmethod
    def _image_transport_family(cls, tool_event: Any) -> str:
        payload = dict(getattr(tool_event, "payload", {}) or {})
        tool_name = str(getattr(tool_event, "name", "") or payload.get("tool_name") or "").strip().lower()
        return image_transport_family_for_tool(tool_name=tool_name, payload=payload)

    @staticmethod
    def _image_transport_subject(payload: Dict[str, Any], output_items: List[Dict[str, Any]]) -> str:
        return image_transport_subject(payload=payload, output_items=output_items)

    @staticmethod
    def _next_item_index(events: List[Dict[str, Any]]) -> int:
        highest = -1
        for event in list(events or []):
            if not isinstance(event, dict):
                continue
            item = event.get("item")
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "").strip()
            if not item_id.startswith("item_"):
                continue
            try:
                highest = max(highest, int(item_id.split("_", 1)[1]))
            except (TypeError, ValueError):
                continue
        return highest + 1

    @classmethod
    def _rebase_item_events(
        cls,
        item_events: List[Dict[str, Any]],
        *,
        start_index: int,
    ) -> List[Dict[str, Any]]:
        mapping: Dict[str, str] = {}
        next_index = int(start_index)
        rebased: List[Dict[str, Any]] = []
        for raw_event in list(item_events or []):
            if not isinstance(raw_event, dict):
                continue
            copied = dict(raw_event)
            item = copied.get("item")
            if not isinstance(item, dict):
                rebased.append(copied)
                continue
            item_copy = dict(item)
            source_id = str(item_copy.get("id") or "").strip()
            if source_id:
                replacement = mapping.get(source_id)
                if replacement is None:
                    replacement = f"item_{next_index}"
                    mapping[source_id] = replacement
                    next_index += 1
                item_copy["id"] = replacement
            copied["item"] = item_copy
            rebased.append(copied)
        return rebased

    @classmethod
    def _compose_turn_events(
        cls,
        *,
        assistant_text: str,
        response_items: List[ResponseInputItem],
        executed_item_events: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return compose_turn_events_from_response_items(
            assistant_text=assistant_text,
            response_items=list(response_items or []),
            executed_item_events=[
                dict(item)
                for item in list(executed_item_events or [])
                if isinstance(item, dict)
            ],
        )

    def _canonical_turn_events(
        self,
        *,
        assistant_text: str,
        response_items: List[ResponseInputItem],
        executed_item_events: List[Dict[str, Any]],
        existing_turn_events: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        normalized_existing = [
            dict(item)
            for item in list(existing_turn_events or [])
            if isinstance(item, dict)
        ]
        if normalized_existing:
            final_text = response_items_to_text(list(response_items or [])).strip() or str(assistant_text or "").strip()
            return self._rewrite_existing_turn_events(normalized_existing, final_text=final_text)
        return self._compose_turn_events(
            assistant_text=assistant_text,
            response_items=response_items,
            executed_item_events=list(executed_item_events or []),
        )

    @staticmethod
    def _rewrite_existing_turn_events(
        existing_turn_events: List[Dict[str, Any]],
        *,
        final_text: str,
    ) -> List[Dict[str, Any]]:
        normalized = [dict(item) for item in list(existing_turn_events or []) if isinstance(item, dict)]
        if not normalized:
            return []
        final_text = str(final_text or "").strip()
        if not final_text:
            return normalized
        updated = [dict(item) for item in normalized]
        replaced = False
        for idx in range(len(updated) - 1, -1, -1):
            event = dict(updated[idx])
            if str(event.get("type") or "").strip() != "item.completed":
                continue
            item = event.get("item")
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "").strip() != "agent_message":
                continue
            item_copy = dict(item)
            item_copy["text"] = final_text
            event["item"] = item_copy
            updated[idx] = event
            replaced = True
            break
        if replaced:
            return updated
        inserted = {
            "type": "item.completed",
            "item": {
                "id": "item_0",
                "type": "agent_message",
                "text": final_text,
            },
        }
        turn_completed_idx = None
        for idx, event in enumerate(updated):
            if str((event or {}).get("type") or "").strip() == "turn.completed":
                turn_completed_idx = idx
                break
        if turn_completed_idx is None:
            if not updated or str(updated[0].get("type") or "").strip() != "turn.started":
                updated.insert(0, {"type": "turn.started"})
            updated.append(inserted)
            updated.append(
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
                }
            )
            return updated
        updated.insert(turn_completed_idx, inserted)
        return updated

    @staticmethod
    def _tool_item_events_from_turn_events(turn_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tool_item_types = {"command_execution", "mcp_tool_call", "todo_list", "function_call_output", "custom_tool_call_output"}
        item_events: List[Dict[str, Any]] = []
        for raw_event in list(turn_events or []):
            if not isinstance(raw_event, dict):
                continue
            item = raw_event.get("item")
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "").strip() not in tool_item_types:
                continue
            item_events.append(dict(raw_event))
        return item_events

    @classmethod
    def _normalized_execution_events(cls, execution: CommandExecutionResult) -> List[Dict[str, Any]]:
        raw_item_events = [
            dict(item)
            for item in list(execution.item_events or [])
            if isinstance(item, dict)
        ]
        if not raw_item_events and execution.turn_events:
            raw_item_events = cls._tool_item_events_from_turn_events(
                [
                    dict(item)
                    for item in list(execution.turn_events or [])
                    if isinstance(item, dict)
                ]
            )
        rebased_item_events = cls._rebase_item_events(raw_item_events, start_index=0)
        synthetic_output_event = cls._synthetic_function_call_output_event(
            execution,
            start_index=cls._next_item_index(rebased_item_events),
            existing_item_events=rebased_item_events,
        )
        if synthetic_output_event is not None:
            rebased_item_events.append(synthetic_output_event)
        return rebased_item_events
