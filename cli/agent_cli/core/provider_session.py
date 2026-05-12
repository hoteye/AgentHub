from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol

from cli.agent_cli.models import (
    ResponseInputItem,
    ToolEvent,
)
from .provider_session_tool_results_runtime import (
    default_tool_result_items,
    tool_result_payload,
)


@dataclass
class ProviderToolCall:
    call_id: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    item_type: str = "function_call"
    raw_item: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderSessionResult:
    output_text: str = ""
    tool_calls: List[ProviderToolCall] = field(default_factory=list)
    response_items: List[ResponseInputItem] = field(default_factory=list)
    continuation_input_items: List[Dict[str, Any]] = field(default_factory=list)
    raw_response: Any = None
    response_id: Optional[str] = None
    trace: Dict[str, Any] = field(default_factory=dict)


class ProviderSession(Protocol):
    def send(
        self,
        *,
        input_items: List[Dict[str, Any]],
        allow_tools: bool = True,
        previous_response_id: Optional[str] = None,
        prompt_cache_key: Optional[str] = None,
        turn_event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> ProviderSessionResult: ...

    def build_tool_result_items(
        self,
        *,
        call_id: str,
        command_text: Optional[str],
        assistant_text: str,
        events: List[ToolEvent],
    ) -> List[Dict[str, Any]]:
        return default_tool_result_items(
            call_id=call_id,
            command_text=command_text,
            assistant_text=assistant_text,
            events=events,
            tool_result_projection_policy=str(getattr(self, "tool_result_projection_policy", "") or "").strip(),
            workspace_root=str(getattr(self, "workspace_root", "") or "").strip() or None,
            tool_output_thread_id=str(getattr(self, "tool_output_thread_id", "") or "").strip() or None,
        )
