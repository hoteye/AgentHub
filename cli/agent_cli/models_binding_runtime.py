from __future__ import annotations

from typing import Any

__all__ = ["apply_model_runtime_bindings"]


def apply_model_runtime_bindings(namespace: dict[str, object]) -> None:
    from cli.agent_cli import models_dataclass_runtime as models_dataclass_runtime_service
    from cli.agent_cli import models_event_runtime as models_event_runtime_service

    def _get(name: str) -> Any:
        return namespace[name]

    namespace.setdefault("models_dataclass_runtime_service", models_dataclass_runtime_service)
    namespace.setdefault("models_event_runtime_service", models_event_runtime_service)

    def _dataclass_service() -> Any:
        return _get("models_dataclass_runtime_service")

    def _event_service() -> Any:
        return _get("models_event_runtime_service")

    dataclass_service = _dataclass_service()
    namespace["ToolEvent"].from_dict = classmethod(dataclass_service.tool_event_from_dict)
    namespace["ToolEvent"].to_dict = dataclass_service.tool_event_to_dict
    namespace["ActivityEvent"].from_dict = classmethod(dataclass_service.activity_event_from_dict)
    namespace["ActivityEvent"].to_dict = dataclass_service.activity_event_to_dict
    namespace["ShellLifecycleEnvelope"].from_dict = classmethod(
        dataclass_service.shell_lifecycle_envelope_from_dict
    )
    namespace["ShellLifecycleEnvelope"].to_dict = dataclass_service.shell_lifecycle_envelope_to_dict
    namespace["PromptAttachment"].from_path = classmethod(
        dataclass_service.prompt_attachment_from_path
    )
    namespace["PromptAttachment"].from_dict = classmethod(
        dataclass_service.prompt_attachment_from_dict
    )
    namespace["PromptAttachment"].to_dict = dataclass_service.prompt_attachment_to_dict
    namespace["ReferenceContextItem"].from_attachment = classmethod(
        dataclass_service.reference_context_item_from_attachment
    )
    namespace["ReferenceContextItem"].from_dict = classmethod(
        dataclass_service.reference_context_item_from_dict
    )
    namespace["ReferenceContextItem"].to_dict = dataclass_service.reference_context_item_to_dict
    namespace["ThreadHistoryTurn"].from_dict = classmethod(
        lambda cls, payload: _dataclass_service().thread_history_turn_from_dict(
            cls,
            payload,
            prompt_attachment_from_dict_fn=_get("PromptAttachment").from_dict,
            tool_event_from_dict_fn=_get("ToolEvent").from_dict,
            activity_event_from_dict_fn=_get("ActivityEvent").from_dict,
            reference_context_item_from_dict_fn=_get("ReferenceContextItem").from_dict,
            response_input_item_from_dict_fn=_get("ResponseInputItem").from_dict,
        )
    )
    namespace["ThreadHistoryTurn"].to_dict = dataclass_service.thread_history_turn_to_dict
    namespace["ThreadHistoryTurn"].from_legacy_turn_payload = classmethod(
        dataclass_service.thread_history_turn_from_legacy_turn_payload
    )
    namespace["FunctionCallOutputContentItem"].from_dict = classmethod(
        dataclass_service.function_call_output_content_item_from_dict
    )
    namespace["FunctionCallOutputContentItem"].to_dict = (
        dataclass_service.function_call_output_content_item_to_dict
    )
    namespace["FunctionCallOutputPayload"].from_output = classmethod(
        lambda cls, output, *, success=None: (
            _dataclass_service().function_call_output_payload_from_output(
                cls,
                output,
                success=success,
                item_from_dict_fn=_get("FunctionCallOutputContentItem").from_dict,
                item_from_text_fn=_get("_function_call_output_text_item"),
            )
        )
    )
    namespace["FunctionCallOutputPayload"].from_text_segments = classmethod(
        lambda cls, text_segments, *, success=None: cls(
            body=_event_service().function_output_content_items_from_text_segments(
                text_segments,
                item_from_text=_get("_function_call_output_text_item"),
            ),
            success=success,
        )
    )
    namespace[
        "FunctionCallOutputPayload"
    ].wire_value = lambda self: _dataclass_service().function_call_output_payload_wire_value(
        self,
        item_to_dict_fn=lambda item: item.to_dict(),
    )
    namespace["FunctionCallOutputPayload"].to_text = (
        dataclass_service.function_call_output_payload_to_text
    )
    namespace["FunctionCallOutputPayload"].text_segments = namespace[
        "function_call_output_payload_text_segments"
    ]
    namespace["ResponseInputItem"].from_dict = classmethod(
        dataclass_service.response_input_item_from_dict
    )
    namespace["ResponseInputItem"].to_dict = dataclass_service.response_input_item_to_dict
    namespace["TurnContextInputItem"].from_dict = classmethod(
        lambda cls, payload: _dataclass_service().turn_context_input_item_from_dict(
            cls,
            payload,
            response_input_item_from_dict_fn=_get("ResponseInputItem").from_dict,
        )
    )
    namespace["TurnContextInputItem"].to_dict = dataclass_service.turn_context_input_item_to_dict
    namespace["TurnContextRollout"].from_dict = classmethod(
        lambda cls, payload: _dataclass_service().turn_context_rollout_from_dict(
            cls,
            payload,
            turn_context_input_item_from_dict_fn=_get("TurnContextInputItem").from_dict,
            reference_context_item_from_dict_fn=_get("ReferenceContextItem").from_dict,
        )
    )
    namespace["TurnContextRollout"].to_dict = dataclass_service.turn_context_rollout_to_dict
    namespace["RolloutItem"].from_dict = classmethod(
        lambda cls, payload: _dataclass_service().rollout_item_from_dict(
            cls,
            payload,
            thread_history_turn_from_dict_fn=_get("ThreadHistoryTurn").from_dict,
            thread_history_turn_from_legacy_turn_payload_fn=_get(
                "ThreadHistoryTurn"
            ).from_legacy_turn_payload,
            turn_context_rollout_from_dict_fn=_get("TurnContextRollout").from_dict,
        )
    )
    namespace["RolloutItem"].to_dict = dataclass_service.rollout_item_to_dict

    from cli.agent_cli import models_response_items as _models_response_items
    from cli.agent_cli import models_response_projection as _models_response_projection
    from cli.agent_cli import models_tool_io as _models_tool_io
    from cli.agent_cli import models_turn_events as _models_turn_events

    namespace["_models_response_items"] = _models_response_items
    namespace["_models_response_projection"] = _models_response_projection
    namespace["_models_tool_io"] = _models_tool_io
    namespace["_models_turn_events"] = _models_turn_events

    namespace["compose_turn_events_from_response_items"] = (
        _models_response_items.compose_turn_events_from_response_items
    )
    namespace["default_response_items"] = _models_response_items.default_response_items
    namespace["prompt_response_turn_events"] = _models_response_items.prompt_response_turn_events
    namespace["response_item_text"] = _models_response_items.response_item_text
    namespace["response_items_phase_text"] = _models_response_items.response_items_phase_text
    namespace["response_items_to_text"] = _models_response_items.response_items_to_text
    namespace["response_message_item"] = _models_response_items.response_message_item

    namespace["function_call_input_items_from_tool_events"] = (
        _models_tool_io.function_call_input_items_from_tool_events
    )
    namespace["tool_output_input_items_from_tool_events"] = (
        _models_tool_io.tool_output_input_items_from_tool_events
    )

    namespace["function_call_input_items_from_turn_events"] = (
        _models_response_projection.function_call_input_items_from_turn_events
    )
    namespace["reasoning_input_items_from_turn_events"] = (
        _models_response_projection.reasoning_input_items_from_turn_events
    )
    namespace["replay_input_items_from_turn_events"] = (
        _models_response_projection.replay_input_items_from_turn_events
    )
    namespace["response_items_with_tool_outputs"] = (
        _models_response_projection.response_items_with_tool_outputs
    )
    namespace["tool_output_input_items_from_turn_events"] = (
        _models_response_projection.tool_output_input_items_from_turn_events
    )

    namespace["_rebase_turn_item_events"] = _models_turn_events._rebase_turn_item_events
    namespace["_response_item_to_turn_item"] = _models_turn_events._response_item_to_turn_item
    namespace["_response_item_tool_key"] = _models_turn_events._response_item_tool_key
    namespace["_turn_event_content_text"] = _models_turn_events._turn_event_content_text
    namespace["_turn_event_content_types"] = _models_turn_events._turn_event_content_types
    namespace["_turn_event_usage_int"] = _models_turn_events._turn_event_usage_int
    namespace["completed_todo_list_turn_events"] = (
        _models_turn_events.completed_todo_list_turn_events
    )
    namespace["generic_tool_call_item_events"] = _models_turn_events.generic_tool_call_item_events
    namespace["latest_open_todo_list_item"] = _models_turn_events.latest_open_todo_list_item
    namespace["shell_tool_call_item_events"] = _models_turn_events.shell_tool_call_item_events
    namespace["todo_list_items_from_plan_payload"] = (
        _models_turn_events.todo_list_items_from_plan_payload
    )
    namespace["todo_list_turn_event_from_plan_payload"] = (
        _models_turn_events.todo_list_turn_event_from_plan_payload
    )
    namespace["todo_list_turn_item_from_plan_payload"] = (
        _models_turn_events.todo_list_turn_item_from_plan_payload
    )
    namespace["tool_events_to_turn_events"] = _models_turn_events.tool_events_to_turn_events
