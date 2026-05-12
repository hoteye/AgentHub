from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from cli.agent_cli.models import PromptAttachment, PromptResponse

if TYPE_CHECKING:
    from cli.agent_cli.runtime import AgentCliRuntime


RuntimeRequestPriority = Literal["now", "next", "later"]
_RUNTIME_REQUEST_PRIORITIES: tuple[RuntimeRequestPriority, ...] = ("now", "next", "later")


def normalize_runtime_request_priority(
    value: str | None,
    *,
    default: RuntimeRequestPriority = "next",
) -> RuntimeRequestPriority:
    token = str(value or "").strip().lower()
    if token in _RUNTIME_REQUEST_PRIORITIES:
        return token  # type: ignore[return-value]
    return default


@dataclass(slots=True)
class QueuedRuntimeRequest:
    text: str
    attachments: list[PromptAttachment]
    display_text: str | None = None
    display_attachments: list[PromptAttachment] | None = None
    priority: RuntimeRequestPriority = "next"
    metadata: dict[str, object] | None = None


class FallbackAgent:
    @staticmethod
    def provider_status() -> dict[str, str]:
        return {
            "provider_ready": "false",
            "provider_name": "fallback",
            "provider_model": "-",
            "provider_tools": "-",
            "provider_label": "fallback | - | -",
            "provider_base_url": "-",
            "provider_source": "fallback",
            "provider_config_path": "-",
            "provider_auth_path": "-",
        }


class FallbackRuntime:
    def __init__(self) -> None:
        self.agent = FallbackAgent()
        self.activity_callback = None
        self.turn_event_callback = None
        self.thread_id = None
        self.thread_name = None

    @staticmethod
    def slash_command_matches(query: str) -> list[dict[str, str]]:
        _ = query
        return []

    @staticmethod
    def slash_command_completion(query: str) -> str | None:
        _ = query
        return None

    def handle_prompt(
        self, text: str, *, attachments: list[PromptAttachment] | None = None
    ) -> PromptResponse:
        return PromptResponse(
            user_text=text,
            assistant_text="Runtime initialization failed. Running in fallback UI mode.",
            attachments=list(attachments or []),
            handled_as_command=False,
            status=self.agent.provider_status(),
            tool_events=[],
            activity_events=[],
        )

    @staticmethod
    def interrupt_active_run() -> dict[str, object]:
        return {"ok": False, "interrupted": False}

    @staticmethod
    def pending_steer_supported() -> bool:
        return False

    @staticmethod
    def steer_active_run(
        text: str,
        *,
        attachments: list[PromptAttachment] | None = None,
    ) -> dict[str, object]:
        del text, attachments
        return {"accepted": False, "fallback_queue": True, "reason": "unsupported"}

    @staticmethod
    def take_pending_steer_input_items(*, limit: int | None = None) -> list[dict[str, object]]:
        del limit
        return []


def resolve_runtime(runtime: AgentCliRuntime | None):
    if runtime is not None:
        return runtime
    try:
        from cli.agent_cli.runtime_factory import build_persistent_runtime
        from cli.agent_cli.runtime_policy import RuntimePolicy

        return build_persistent_runtime(
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
            resume_active_thread=False,
        )
    except Exception:
        return FallbackRuntime()
