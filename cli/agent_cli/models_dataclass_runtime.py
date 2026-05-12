from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli import models_class_runtime as models_class_runtime_service
from cli.agent_cli import models_mapping_runtime as models_mapping_runtime_service
from cli.agent_cli import models_thread_serialization as models_thread_serialization_service
from cli.agent_cli import models_event_runtime as models_event_runtime_service


def tool_event_from_dict(cls: type[Any], payload: dict[str, Any]) -> Any:
    return cls(**models_mapping_runtime_service.tool_event_from_dict_data(payload))


def tool_event_to_dict(self: Any) -> dict[str, Any]:
    return models_mapping_runtime_service.tool_event_to_dict_data(
        name=self.name,
        ok=self.ok,
        summary=self.summary,
        payload=self.payload,
    )


def activity_event_from_dict(cls: type[Any], payload: dict[str, Any]) -> Any:
    return cls(**models_mapping_runtime_service.activity_event_from_dict_data(payload))


def activity_event_to_dict(self: Any) -> dict[str, Any]:
    return models_mapping_runtime_service.activity_event_to_dict_data(
        title=self.title,
        status=self.status,
        detail=self.detail,
        kind=self.kind,
        code=self.code,
        params=self.params,
    )


def shell_lifecycle_envelope_from_dict(cls: type[Any], payload: dict[str, Any]) -> Any:
    return cls(**models_mapping_runtime_service.shell_lifecycle_envelope_from_dict_data(payload))


def shell_lifecycle_envelope_to_dict(self: Any) -> dict[str, Any]:
    return models_mapping_runtime_service.shell_lifecycle_envelope_to_dict_data(
        phase=self.phase,
        kind=self.kind,
        call_id=self.call_id,
        session_id=self.session_id,
        process_id=self.process_id,
        source=self.source,
        stream=self.stream,
        status=self.status,
    )


def prompt_attachment_from_path(cls: type[Any], path_text: str, *, source: str = "file_reference") -> Any:
    return cls(**models_mapping_runtime_service.prompt_attachment_from_path_data(path_text, source=source))


def prompt_attachment_from_dict(cls: type[Any], payload: dict[str, Any]) -> Any:
    return cls(**models_mapping_runtime_service.prompt_attachment_from_dict_data(payload))


def prompt_attachment_to_dict(self: Any) -> dict[str, Any]:
    return models_mapping_runtime_service.prompt_attachment_to_dict_data(
        path=self.path,
        name=self.name,
        extension=self.extension,
        exists=self.exists,
        is_dir=self.is_dir,
        source=self.source,
    )


def reference_context_item_from_attachment(cls: type[Any], attachment: Any) -> Any:
    return cls(**models_mapping_runtime_service.reference_context_item_from_attachment_data(attachment))


def reference_context_item_from_dict(cls: type[Any], payload: dict[str, Any]) -> Any:
    return cls(**models_mapping_runtime_service.reference_context_item_from_dict_data(payload))


def reference_context_item_to_dict(self: Any) -> dict[str, Any]:
    return models_mapping_runtime_service.reference_context_item_to_dict_data(
        item_type=self.item_type,
        source=self.source,
        label=self.label,
        path=self.path,
        uri=self.uri,
        ref=self.ref,
        description=self.description,
        metadata=self.metadata,
    )


def thread_history_turn_from_dict(
    cls: type[Any],
    payload: dict[str, Any],
    *,
    prompt_attachment_from_dict_fn: Callable[[dict[str, Any]], Any],
    tool_event_from_dict_fn: Callable[[dict[str, Any]], Any],
    activity_event_from_dict_fn: Callable[[dict[str, Any]], Any],
    reference_context_item_from_dict_fn: Callable[[dict[str, Any]], Any],
    response_input_item_from_dict_fn: Callable[[dict[str, Any]], Any],
) -> Any:
    return cls(
        **models_class_runtime_service.thread_history_turn_from_dict(
            payload,
            prompt_attachment_from_dict_fn=prompt_attachment_from_dict_fn,
            tool_event_from_dict_fn=tool_event_from_dict_fn,
            activity_event_from_dict_fn=activity_event_from_dict_fn,
            reference_context_item_from_dict_fn=reference_context_item_from_dict_fn,
            response_input_item_from_dict_fn=response_input_item_from_dict_fn,
        )
    )


def thread_history_turn_to_dict(self: Any) -> dict[str, Any]:
    return models_thread_serialization_service.thread_history_turn_to_dict(
        turn_id=self.turn_id,
        timestamp=self.timestamp,
        user_text=self.user_text,
        commentary_text=self.commentary_text,
        assistant_text=self.assistant_text,
        assistant_history_text=self.assistant_history_text,
        command_display_text=self.command_display_text,
        handled_as_command=self.handled_as_command,
        status=self.status,
        protocol_diagnostics=self.protocol_diagnostics,
        runtime_state=self.runtime_state,
        attachments=self.attachments,
        tool_events=self.tool_events,
        activity_events=self.activity_events,
        reference_context_items=self.reference_context_items,
        response_items=self.response_items,
        turn_events=self.turn_events,
    )


def thread_history_turn_from_legacy_turn_payload(cls: type[Any], payload: dict[str, Any]) -> Any:
    return cls.from_dict(
        models_thread_serialization_service.thread_history_turn_from_legacy_turn_payload(payload)
    )


def function_call_output_content_item_from_dict(cls: type[Any], payload: dict[str, Any]) -> Any:
    return cls(**models_mapping_runtime_service.function_call_output_content_item_from_dict_data(payload))


def function_call_output_content_item_to_dict(self: Any) -> dict[str, Any]:
    return models_mapping_runtime_service.function_call_output_content_item_to_dict_data(
        item_type=self.item_type,
        text=self.text,
        image_url=self.image_url,
        detail=self.detail,
    )


def function_call_output_payload_from_output(
    cls: type[Any],
    output: Any,
    *,
    success: bool | None = None,
    item_from_dict_fn: Callable[[dict[str, Any]], Any],
    item_from_text_fn: Callable[[str], Any],
) -> Any:
    return cls(
        body=models_class_runtime_service.function_call_output_payload_body(
            output,
            item_from_dict_fn=item_from_dict_fn,
            item_from_text_fn=item_from_text_fn,
        ),
        success=success,
    )


def function_call_output_payload_wire_value(
    self: Any,
    *,
    item_to_dict_fn: Callable[[Any], dict[str, Any]],
) -> Any:
    return models_class_runtime_service.function_call_output_payload_wire_value(
        self.body,
        item_to_dict_fn=item_to_dict_fn,
    )


def function_call_output_payload_to_text(self: Any) -> str | None:
    return models_event_runtime_service.text_from_function_output_body(self.body)


def response_input_item_from_dict(cls: type[Any], payload: dict[str, Any]) -> Any:
    return cls(**models_thread_serialization_service.response_input_item_from_dict(payload))


def response_input_item_to_dict(self: Any) -> dict[str, Any]:
    return models_thread_serialization_service.response_input_item_to_dict(
        self.item_type,
        self.role,
        self.content,
        self.content_present,
        self.extra,
    )


def turn_context_input_item_from_dict(
    cls: type[Any],
    payload: dict[str, Any],
    *,
    response_input_item_from_dict_fn: Callable[[dict[str, Any]], Any],
) -> Any:
    return cls(
        **models_class_runtime_service.turn_context_input_item_from_dict(
            payload,
            response_input_item_from_dict_fn=response_input_item_from_dict_fn,
        )
    )


def turn_context_input_item_to_dict(self: Any) -> dict[str, Any]:
    return models_thread_serialization_service.turn_context_input_item_to_dict(
        source=self.source,
        item_payload=self.item.to_dict(),
    )


def turn_context_rollout_from_dict(
    cls: type[Any],
    payload: dict[str, Any],
    *,
    turn_context_input_item_from_dict_fn: Callable[[dict[str, Any]], Any],
    reference_context_item_from_dict_fn: Callable[[dict[str, Any]], Any],
) -> Any:
    return cls(
        **models_class_runtime_service.turn_context_rollout_from_dict(
            payload,
            turn_context_input_item_from_dict_fn=turn_context_input_item_from_dict_fn,
            reference_context_item_from_dict_fn=reference_context_item_from_dict_fn,
        )
    )


def turn_context_rollout_to_dict(self: Any) -> dict[str, Any]:
    return models_thread_serialization_service.turn_context_rollout_to_dict(
        cwd=self.cwd,
        shell=self.shell,
        current_date=self.current_date,
        timezone=self.timezone,
        approval_policy=self.approval_policy,
        sandbox_mode=self.sandbox_mode,
        model=self.model,
        network_access_enabled=self.network_access_enabled,
        items=self.items,
        reference_context_items=self.reference_context_items,
        state=self.state,
    )


def rollout_item_from_dict(
    cls: type[Any],
    payload: dict[str, Any],
    *,
    thread_history_turn_from_dict_fn: Callable[[dict[str, Any]], Any],
    thread_history_turn_from_legacy_turn_payload_fn: Callable[[dict[str, Any]], Any],
    turn_context_rollout_from_dict_fn: Callable[[dict[str, Any]], Any],
) -> Any:
    return cls(
        **models_class_runtime_service.rollout_item_from_dict(
            payload,
            thread_history_turn_from_dict_fn=thread_history_turn_from_dict_fn,
            thread_history_turn_from_legacy_turn_payload_fn=thread_history_turn_from_legacy_turn_payload_fn,
            turn_context_rollout_from_dict_fn=turn_context_rollout_from_dict_fn,
        )
    )


def rollout_item_to_dict(self: Any) -> dict[str, Any]:
    return models_thread_serialization_service.rollout_item_to_dict(
        item_type=self.item_type,
        thread_id=self.thread_id,
        timestamp=self.timestamp,
        payload=self.payload,
        turn=self.turn,
        turn_context=self.turn_context,
    )
