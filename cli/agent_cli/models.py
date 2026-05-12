from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cli.agent_cli import models_activity_runtime as models_activity_runtime_service
from cli.agent_cli import models_dataclass_runtime as models_dataclass_runtime_service
from cli.agent_cli import models_event_runtime as models_event_runtime_service
from cli.agent_cli import models_mapping_runtime as models_mapping_runtime_service


@dataclass
class ToolEvent:
    name: str
    ok: bool
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)


def tool_event_is_soft_failure(tool_event: ToolEvent) -> bool:
    return models_event_runtime_service.tool_event_is_soft_failure(tool_event)


def tool_event_is_interrupt(tool_event: ToolEvent) -> bool:
    return models_event_runtime_service.tool_event_is_interrupt(tool_event)


def tool_events_include_interrupt(events: list[ToolEvent]) -> bool:
    return models_event_runtime_service.tool_events_include_interrupt(events)


def tool_event_is_approval_request(tool_event: ToolEvent) -> bool:
    return models_event_runtime_service.tool_event_is_approval_request(tool_event)


def tool_events_include_approval_requests(events: list[ToolEvent]) -> bool:
    return models_event_runtime_service.tool_events_include_approval_requests(events)


REFERENCE_CONVERSATION_INTERRUPTED_TEXT = (
    "Conversation interrupted - tell the model what to do differently."
)


def is_user_interrupt_assistant_text(text: str) -> bool:
    return models_event_runtime_service.is_user_interrupt_assistant_text(
        text, REFERENCE_CONVERSATION_INTERRUPTED_TEXT
    )


def shell_command_assistant_text(default_text: str, event: ToolEvent | None) -> str:
    return models_event_runtime_service.shell_command_assistant_text(default_text, event)


def tool_event_result_text(tool_event: ToolEvent) -> str:
    return models_event_runtime_service.tool_event_result_text(tool_event)


def _reference_wrapped_shell_command(payload: dict[str, Any], fallback: str) -> str:
    return models_event_runtime_service.reference_wrapped_shell_command(payload, fallback)


def _command_detail_line_is_structured(line: str) -> bool:
    key, separator, _value = str(line or "").strip().partition("=")
    if separator != "=" or not key:
        return False
    return all(char.isalnum() or char in {"_", "-", "."} for char in key)


def command_display_text_from_assistant_text(assistant_text: str) -> str:
    lines = [
        raw_line.strip() for raw_line in str(assistant_text or "").splitlines() if raw_line.strip()
    ]
    if not lines:
        return ""
    if len(lines) == 1:
        return lines[0]
    if all(_command_detail_line_is_structured(line) for line in lines[1:]):
        return lines[0]
    return ""


def command_display_text_from_tool_events(tool_events: list[ToolEvent]) -> str:
    if (
        tool_events
        and str(getattr(tool_events[0], "name", "") or "").strip() == "approval_decision"
    ):
        return ""
    for event in list(tool_events or []):
        summary = str(getattr(event, "summary", "") or "").strip()
        if summary:
            return summary
    return ""


def default_command_display_text(
    *,
    assistant_text: str,
    tool_events: list[ToolEvent] | None = None,
) -> str:
    return command_display_text_from_assistant_text(
        assistant_text
    ) or command_display_text_from_tool_events(list(tool_events or []))


@dataclass
class ActivityEvent:
    title: str
    status: str = "info"
    detail: str = ""
    kind: str = "activity"
    code: str = ""
    params: dict[str, Any] = field(default_factory=dict)


def activity_code(event: ActivityEvent) -> str:
    return models_activity_runtime_service.activity_code(event)


def activity_dedupe_key(event: ActivityEvent) -> tuple[str, str, str, str, str]:
    return models_activity_runtime_service.activity_dedupe_key(event)


@dataclass
class ShellLifecycleEnvelope:
    phase: str
    kind: str
    call_id: str
    session_id: str = ""
    process_id: str = ""
    source: str = "shell_session_manager"
    stream: str = ""
    status: str = ""


@dataclass
class PromptAttachment:
    path: str
    name: str
    extension: str = ""
    exists: bool = False
    is_dir: bool = False
    source: str = "file_reference"


PROMPT_ATTACHMENT_SOURCE_FILE_REFERENCE = (
    models_mapping_runtime_service.PROMPT_ATTACHMENT_SOURCE_FILE_REFERENCE
)
PROMPT_ATTACHMENT_SOURCE_USER_LOCAL_IMAGE_ATTACHMENT = (
    models_mapping_runtime_service.PROMPT_ATTACHMENT_SOURCE_USER_LOCAL_IMAGE_ATTACHMENT
)
PROMPT_ATTACHMENT_SOURCE_TOOL_LOCAL_IMAGE_READ = (
    models_mapping_runtime_service.PROMPT_ATTACHMENT_SOURCE_TOOL_LOCAL_IMAGE_READ
)


def prompt_attachment_source_kind(source: str) -> str:
    return models_mapping_runtime_service.prompt_attachment_source_kind(source)


@dataclass
class ReferenceContextItem:
    item_type: str = "reference"
    source: str = ""
    label: str = ""
    path: str = ""
    uri: str = ""
    ref: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ThreadHistoryTurn:
    turn_id: str = ""
    timestamp: str = ""
    user_text: str = ""
    commentary_text: str = ""
    assistant_text: str = ""
    assistant_history_text: str = ""
    handled_as_command: bool = False
    status: dict[str, Any] = field(default_factory=dict)
    protocol_diagnostics: dict[str, Any] = field(default_factory=dict)
    runtime_state: dict[str, Any] = field(default_factory=dict)
    attachments: list[PromptAttachment] = field(default_factory=list)
    tool_events: list[ToolEvent] = field(default_factory=list)
    activity_events: list[ActivityEvent] = field(default_factory=list)
    reference_context_items: list[ReferenceContextItem] = field(default_factory=list)
    response_items: list[ResponseInputItem] = field(default_factory=list)
    turn_events: list[dict[str, Any]] = field(default_factory=list)
    command_display_text: str = ""


@dataclass
class FunctionCallOutputContentItem:
    item_type: str = "input_text"
    text: str = ""
    image_url: str = ""
    detail: str | None = None


def function_call_output_content_items_to_text(
    content_items: list[FunctionCallOutputContentItem],
) -> str | None:
    return models_event_runtime_service.function_call_output_content_items_to_text(content_items)


@dataclass
class FunctionCallOutputPayload:
    body: str | list[FunctionCallOutputContentItem] = ""
    success: bool | None = None


def _function_call_output_text_item(text: str) -> FunctionCallOutputContentItem:
    return FunctionCallOutputContentItem(text=text)


def function_call_output_payload_from_text_segments(
    text_segments: list[str],
    *,
    success: bool | None = None,
) -> FunctionCallOutputPayload:
    return FunctionCallOutputPayload(
        body=models_event_runtime_service.function_output_content_items_from_text_segments(
            text_segments,
            item_from_text=_function_call_output_text_item,
        ),
        success=success,
    )


def function_call_output_payload_text_segments(payload: FunctionCallOutputPayload) -> list[str]:
    body = payload.body
    if isinstance(body, list):
        return [
            str(item.text or "").strip()
            for item in body
            if str(item.item_type or "") == "input_text" and str(item.text or "").strip()
        ]
    text = str(body or "").strip()
    return [text] if text else []


@dataclass
class ResponseInputItem:
    item_type: str = "message"
    role: str = ""
    content: Any = field(default_factory=list)
    content_present: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnContextInputItem:
    source: str = ""
    item: ResponseInputItem = field(default_factory=ResponseInputItem)


@dataclass
class TurnContextRollout:
    cwd: str = ""
    shell: str = ""
    current_date: str = ""
    timezone: str = ""
    approval_policy: str = ""
    sandbox_mode: str = ""
    model: str = ""
    network_access_enabled: bool | None = None
    items: list[TurnContextInputItem] = field(default_factory=list)
    reference_context_items: list[ReferenceContextItem] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)


@dataclass
class RolloutItem:
    item_type: str
    thread_id: str = ""
    timestamp: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    turn: ThreadHistoryTurn | None = None
    turn_context: TurnContextRollout | None = None


@dataclass
class PromptResponse:
    user_text: str
    assistant_text: str
    commentary_text: str = ""
    response_items: list[ResponseInputItem] = field(default_factory=list)
    attachments: list[PromptAttachment] = field(default_factory=list)
    reference_context_items: list[ReferenceContextItem] = field(default_factory=list)
    tool_events: list[ToolEvent] = field(default_factory=list)
    activity_events: list[ActivityEvent] = field(default_factory=list)
    status: dict[str, Any] = field(default_factory=dict)
    protocol_diagnostics: dict[str, Any] = field(default_factory=dict)
    timings: dict[str, Any] = field(default_factory=dict)
    handled_as_command: bool = False
    turn_events: list[dict[str, Any]] = field(default_factory=list)
    command_display_text: str = ""

    def __post_init__(self) -> None:
        if self.handled_as_command and not str(self.command_display_text or "").strip():
            self.command_display_text = default_command_display_text(
                assistant_text=self.assistant_text,
                tool_events=self.tool_events,
            )


@dataclass
class CommandExecutionResult:
    assistant_text: str = ""
    tool_events: list[ToolEvent] = field(default_factory=list)
    item_events: list[dict[str, Any]] = field(default_factory=list)
    turn_events: list[dict[str, Any]] = field(default_factory=list)
    command_display_text: str = ""

    def __iter__(self):
        yield self.assistant_text
        yield list(self.tool_events or [])


@dataclass
class AgentIntent:
    assistant_text: str = ""
    commentary_text: str = ""
    response_items: list[ResponseInputItem] = field(default_factory=list)
    command_text: str | None = None
    status_hint: str = "idle"
    protocol_diagnostics: dict[str, Any] = field(default_factory=dict)
    tool_events: list[ToolEvent] = field(default_factory=list)
    turn_events: list[dict[str, Any]] = field(default_factory=list)
    activity_events: list[ActivityEvent] = field(default_factory=list)
    timings: dict[str, Any] = field(default_factory=dict)


ToolEvent.from_dict = classmethod(models_dataclass_runtime_service.tool_event_from_dict)
ToolEvent.to_dict = models_dataclass_runtime_service.tool_event_to_dict
ActivityEvent.from_dict = classmethod(models_dataclass_runtime_service.activity_event_from_dict)
ActivityEvent.to_dict = models_dataclass_runtime_service.activity_event_to_dict
ShellLifecycleEnvelope.from_dict = classmethod(
    models_dataclass_runtime_service.shell_lifecycle_envelope_from_dict
)
ShellLifecycleEnvelope.to_dict = models_dataclass_runtime_service.shell_lifecycle_envelope_to_dict
PromptAttachment.from_path = classmethod(
    models_dataclass_runtime_service.prompt_attachment_from_path
)
PromptAttachment.from_dict = classmethod(
    models_dataclass_runtime_service.prompt_attachment_from_dict
)
PromptAttachment.to_dict = models_dataclass_runtime_service.prompt_attachment_to_dict
ReferenceContextItem.from_attachment = classmethod(
    models_dataclass_runtime_service.reference_context_item_from_attachment
)
ReferenceContextItem.from_dict = classmethod(
    models_dataclass_runtime_service.reference_context_item_from_dict
)
ReferenceContextItem.to_dict = models_dataclass_runtime_service.reference_context_item_to_dict
ThreadHistoryTurn.from_dict = classmethod(
    lambda cls, payload: models_dataclass_runtime_service.thread_history_turn_from_dict(
        cls,
        payload,
        prompt_attachment_from_dict_fn=PromptAttachment.from_dict,
        tool_event_from_dict_fn=ToolEvent.from_dict,
        activity_event_from_dict_fn=ActivityEvent.from_dict,
        reference_context_item_from_dict_fn=ReferenceContextItem.from_dict,
        response_input_item_from_dict_fn=ResponseInputItem.from_dict,
    )
)
ThreadHistoryTurn.to_dict = models_dataclass_runtime_service.thread_history_turn_to_dict
ThreadHistoryTurn.from_legacy_turn_payload = classmethod(
    models_dataclass_runtime_service.thread_history_turn_from_legacy_turn_payload
)
FunctionCallOutputContentItem.from_dict = classmethod(
    models_dataclass_runtime_service.function_call_output_content_item_from_dict
)
FunctionCallOutputContentItem.to_dict = (
    models_dataclass_runtime_service.function_call_output_content_item_to_dict
)
FunctionCallOutputPayload.from_output = classmethod(
    lambda cls, output, *, success=None: models_dataclass_runtime_service.function_call_output_payload_from_output(
        cls,
        output,
        success=success,
        item_from_dict_fn=FunctionCallOutputContentItem.from_dict,
        item_from_text_fn=_function_call_output_text_item,
    )
)
FunctionCallOutputPayload.from_text_segments = classmethod(
    lambda cls, text_segments, *, success=None: cls(
        body=models_event_runtime_service.function_output_content_items_from_text_segments(
            text_segments,
            item_from_text=_function_call_output_text_item,
        ),
        success=success,
    )
)
FunctionCallOutputPayload.wire_value = (
    lambda self: models_dataclass_runtime_service.function_call_output_payload_wire_value(
        self,
        item_to_dict_fn=lambda item: item.to_dict(),
    )
)
FunctionCallOutputPayload.to_text = (
    models_dataclass_runtime_service.function_call_output_payload_to_text
)
FunctionCallOutputPayload.text_segments = function_call_output_payload_text_segments
ResponseInputItem.from_dict = classmethod(
    models_dataclass_runtime_service.response_input_item_from_dict
)
ResponseInputItem.to_dict = models_dataclass_runtime_service.response_input_item_to_dict
TurnContextInputItem.from_dict = classmethod(
    lambda cls, payload: models_dataclass_runtime_service.turn_context_input_item_from_dict(
        cls,
        payload,
        response_input_item_from_dict_fn=ResponseInputItem.from_dict,
    )
)
TurnContextInputItem.to_dict = models_dataclass_runtime_service.turn_context_input_item_to_dict
TurnContextRollout.from_dict = classmethod(
    lambda cls, payload: models_dataclass_runtime_service.turn_context_rollout_from_dict(
        cls,
        payload,
        turn_context_input_item_from_dict_fn=TurnContextInputItem.from_dict,
        reference_context_item_from_dict_fn=ReferenceContextItem.from_dict,
    )
)
TurnContextRollout.to_dict = models_dataclass_runtime_service.turn_context_rollout_to_dict
RolloutItem.from_dict = classmethod(
    lambda cls, payload: models_dataclass_runtime_service.rollout_item_from_dict(
        cls,
        payload,
        thread_history_turn_from_dict_fn=ThreadHistoryTurn.from_dict,
        thread_history_turn_from_legacy_turn_payload_fn=ThreadHistoryTurn.from_legacy_turn_payload,
        turn_context_rollout_from_dict_fn=TurnContextRollout.from_dict,
    )
)
RolloutItem.to_dict = models_dataclass_runtime_service.rollout_item_to_dict


from cli.agent_cli import models_response_items as _models_response_items  # noqa: E402
from cli.agent_cli import models_response_projection as _models_response_projection  # noqa: E402
from cli.agent_cli import models_tool_io as _models_tool_io  # noqa: E402
from cli.agent_cli import models_turn_events as _models_turn_events  # noqa: E402

compose_turn_events_from_response_items = (
    _models_response_items.compose_turn_events_from_response_items
)
default_response_items = _models_response_items.default_response_items
prompt_response_turn_events = _models_response_items.prompt_response_turn_events
response_item_text = _models_response_items.response_item_text
response_items_phase_text = _models_response_items.response_items_phase_text
response_items_to_text = _models_response_items.response_items_to_text
response_message_item = _models_response_items.response_message_item

function_call_input_items_from_tool_events = (
    _models_tool_io.function_call_input_items_from_tool_events
)
tool_output_input_items_from_tool_events = _models_tool_io.tool_output_input_items_from_tool_events

function_call_input_items_from_turn_events = (
    _models_response_projection.function_call_input_items_from_turn_events
)
reasoning_input_items_from_turn_events = (
    _models_response_projection.reasoning_input_items_from_turn_events
)
replay_input_items_from_turn_events = (
    _models_response_projection.replay_input_items_from_turn_events
)
response_items_with_tool_outputs = _models_response_projection.response_items_with_tool_outputs
tool_output_input_items_from_turn_events = (
    _models_response_projection.tool_output_input_items_from_turn_events
)

_rebase_turn_item_events = _models_turn_events._rebase_turn_item_events
_response_item_to_turn_item = _models_turn_events._response_item_to_turn_item
_response_item_tool_key = _models_turn_events._response_item_tool_key
_turn_event_content_text = _models_turn_events._turn_event_content_text
_turn_event_content_types = _models_turn_events._turn_event_content_types
_turn_event_usage_int = _models_turn_events._turn_event_usage_int
completed_todo_list_turn_events = _models_turn_events.completed_todo_list_turn_events
generic_tool_call_item_events = _models_turn_events.generic_tool_call_item_events
latest_open_todo_list_item = _models_turn_events.latest_open_todo_list_item
shell_tool_call_item_events = _models_turn_events.shell_tool_call_item_events
todo_list_items_from_plan_payload = _models_turn_events.todo_list_items_from_plan_payload
todo_list_turn_event_from_plan_payload = _models_turn_events.todo_list_turn_event_from_plan_payload
todo_list_turn_item_from_plan_payload = _models_turn_events.todo_list_turn_item_from_plan_payload
tool_events_to_turn_events = _models_turn_events.tool_events_to_turn_events
