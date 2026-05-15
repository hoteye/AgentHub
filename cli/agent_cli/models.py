from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cli.agent_cli import models_activity_runtime as models_activity_runtime_service
from cli.agent_cli import models_command_display_runtime as models_command_display_runtime_service
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
    return models_command_display_runtime_service._command_detail_line_is_structured(line)


def command_display_text_from_assistant_text(assistant_text: str) -> str:
    return models_command_display_runtime_service.command_display_text_from_assistant_text(
        assistant_text
    )


def command_display_text_from_tool_events(tool_events: list[ToolEvent]) -> str:
    return models_command_display_runtime_service.command_display_text_from_tool_events(tool_events)


def default_command_display_text(
    *,
    assistant_text: str,
    tool_events: list[ToolEvent] | None = None,
) -> str:
    return models_command_display_runtime_service.default_command_display_text(
        assistant_text=assistant_text,
        tool_events=tool_events,
    )


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


from cli.agent_cli import models_binding_runtime as _models_binding_runtime  # noqa: E402

_models_binding_runtime.apply_model_runtime_bindings(globals())
