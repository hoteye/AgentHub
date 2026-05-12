from __future__ import annotations

from typing import Any, List, Optional, Tuple

from cli.agent_cli.models import ToolEvent


def try_execute_local_plan(runtime: Any, text: str) -> Optional[Tuple[str, List[ToolEvent]]]:
    # Built-in desktop automation planning is disabled on the active Ubuntu-first host path.
    runtime._should_try_local_plan(text)
    return None
