from __future__ import annotations

from typing import Any, Callable


class StructuredToolExecutor:
    def __init__(
        self,
        *,
        run_command_text_result_fn: Callable[[str], Any],
        interrupt_requested_fn: Callable[[], bool],
        interrupt_result_fn: Callable[[], tuple[str, list[Any]]],
        runtime_owner: Any | None = None,
    ) -> None:
        self._run_command_text_result = run_command_text_result_fn
        self._interrupt_requested = interrupt_requested_fn
        self._interrupt_result = interrupt_result_fn
        self.runtime_owner = runtime_owner

    def __call__(self, text: str) -> tuple[str, list[Any]]:
        result = self._run_command_text_result(text)
        return result.assistant_text, list(result.tool_events or [])

    def run_structured(self, text: str) -> Any:
        return self._run_command_text_result(text)

    def interrupt_requested(self) -> bool:
        return bool(self._interrupt_requested())

    def interrupt_result(self) -> tuple[str, list[Any]]:
        return self._interrupt_result()
