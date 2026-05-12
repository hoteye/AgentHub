from __future__ import annotations

from typing import Any, Dict, Optional

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import tool_library_runtime


def office_skills(self: Any) -> ToolEvent:
    return tool_library_runtime.office_skills(self)


def office_skills_result(self: Any) -> CommandExecutionResult:
    return tool_library_runtime.office_skills_result(self)


def office_run(self: Any, skill_name: str, *, args: Optional[Dict[str, Any]] = None) -> ToolEvent:
    return tool_library_runtime.office_run(self, skill_name, args=args)


def office_run_result(self: Any, skill_name: str, *, args: Optional[Dict[str, Any]] = None) -> CommandExecutionResult:
    return tool_library_runtime.office_run_result(self, skill_name, args=args)


def view_image(self: Any, path: str) -> ToolEvent:
    return tool_library_runtime.view_image(self, path)


def view_image_result(self: Any, path: str) -> CommandExecutionResult:
    return tool_library_runtime.view_image_result(self, path)


def web_search(
    self: Any,
    query: str,
    *,
    limit: int = 5,
    domains: Optional[list[str]] = None,
    recency_days: Optional[int] = None,
    market: Optional[str] = None,
) -> ToolEvent:
    return tool_library_runtime.web_search(
        self,
        query=query,
        limit=limit,
        domains=domains,
        recency_days=recency_days,
        market=market,
    )


def web_search_result(
    self: Any,
    query: str,
    *,
    limit: int = 5,
    domains: Optional[list[str]] = None,
    recency_days: Optional[int] = None,
    market: Optional[str] = None,
) -> CommandExecutionResult:
    return tool_library_runtime.web_search_result(
        self,
        query=query,
        limit=limit,
        domains=domains,
        recency_days=recency_days,
        market=market,
    )


def web_fetch(
    self: Any,
    url: str,
    *,
    max_chars: int = 12000,
) -> ToolEvent:
    return tool_library_runtime.web_fetch(
        self,
        url=url,
        max_chars=max_chars,
    )


def web_fetch_result(self: Any, url: str, *, max_chars: int = 12000) -> CommandExecutionResult:
    return tool_library_runtime.web_fetch_result(
        self,
        url=url,
        max_chars=max_chars,
    )


MISC_METHOD_BINDINGS = (
    ("office_skills", office_skills),
    ("office_skills_result", office_skills_result),
    ("office_run", office_run),
    ("office_run_result", office_run_result),
    ("view_image", view_image),
    ("view_image_result", view_image_result),
    ("web_search", web_search),
    ("web_search_result", web_search_result),
    ("web_fetch", web_fetch),
    ("web_fetch_result", web_fetch_result),
)
