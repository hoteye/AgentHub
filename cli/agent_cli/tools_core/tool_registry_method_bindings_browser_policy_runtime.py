from __future__ import annotations

from typing import Any, Optional

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import tool_library_runtime


def browser(
    self: Any,
    action: str,
    *,
    profile: str | None = None,
    tab_id: str | None = None,
    tab: str | None = None,
    url: str | None = None,
    path: str | None = None,
    line: int | None = None,
    id: int | None = None,
    level: str | None = None,
    limit: int | None = None,
    outcome: str | None = None,
    method: str | None = None,
    storage_kind: str | None = None,
    ref: str | None = None,
    start_ref: str | None = None,
    end_ref: str | None = None,
    kind: str | None = None,
    text: str | None = None,
    fn: str | None = None,
    key: str | None = None,
    cookies: list[dict[str, Any]] | None = None,
    items: dict[str, Any] | None = None,
    values: list[str] | None = None,
    fields: list[dict[str, Any]] | None = None,
    time_ms: int | None = None,
    width: int | None = None,
    height: int | None = None,
    paths: list[str] | None = None,
    input_ref: str | None = None,
    accept: bool | None = None,
    prompt_text: str | None = None,
    transport: str | None = None,
) -> ToolEvent:
    return tool_library_runtime.browser(
        self,
        action=action,
        profile=profile,
        tab_id=tab_id,
        tab=tab,
        url=url,
        path=path,
        line=line,
        id=id,
        level=level,
        limit=limit,
        outcome=outcome,
        method=method,
        storage_kind=storage_kind,
        ref=ref,
        start_ref=start_ref,
        end_ref=end_ref,
        kind=kind,
        text=text,
        fn=fn,
        key=key,
        cookies=cookies,
        items=items,
        values=values,
        fields=fields,
        time_ms=time_ms,
        width=width,
        height=height,
        paths=paths,
        input_ref=input_ref,
        accept=accept,
        prompt_text=prompt_text,
        transport=transport,
    )


def browser_result(self: Any, action: str, **kwargs: Any) -> CommandExecutionResult:
    return tool_library_runtime.browser_result(self, action, **kwargs)


def open(self: Any, ref: str, *, line: int = 1) -> ToolEvent:
    return tool_library_runtime.open_tool(self, ref, line=line)


def open_result(self: Any, ref: str, *, line: int = 1) -> CommandExecutionResult:
    return tool_library_runtime.open_result(self, ref, line=line)


def click(self: Any, ref_id: str, *, id: int) -> ToolEvent:
    return tool_library_runtime.click(self, ref_id, id=id)


def click_result(self: Any, ref_id: str, *, id: int) -> CommandExecutionResult:
    return tool_library_runtime.click_result(self, ref_id, id=id)


def find(self: Any, ref_id: str, *, pattern: str) -> ToolEvent:
    return tool_library_runtime.find(self, ref_id, pattern=pattern)


def find_result(self: Any, ref_id: str, *, pattern: str) -> CommandExecutionResult:
    return tool_library_runtime.find_result(self, ref_id, pattern=pattern)


def policy_doc_import(
    self: Any,
    path: str,
    *,
    library_root: Optional[str] = None,
    recursive: bool = True,
) -> ToolEvent:
    return tool_library_runtime.policy_doc_import(
        self,
        path,
        library_root=library_root,
        recursive=recursive,
    )


def policy_doc_list(
    self: Any,
    *,
    library_root: Optional[str] = None,
    limit: int = 50,
) -> ToolEvent:
    return tool_library_runtime.policy_doc_list(
        self,
        library_root=library_root,
        limit=limit,
    )


def policy_doc_search(
    self: Any,
    query: str,
    *,
    library_root: Optional[str] = None,
    limit: int = 10,
) -> ToolEvent:
    return tool_library_runtime.policy_doc_search(
        self,
        query=query,
        library_root=library_root,
        limit=limit,
    )


def policy_doc_read(
    self: Any,
    *,
    doc_id: Optional[str] = None,
    path: Optional[str] = None,
    library_root: Optional[str] = None,
    max_chars: int = 12000,
) -> ToolEvent:
    return tool_library_runtime.policy_doc_read(
        self,
        doc_id=doc_id,
        path=path,
        library_root=library_root,
        max_chars=max_chars,
    )


def policy_doc_import_result(
    self: Any,
    path: str,
    *,
    library_root: Optional[str] = None,
    recursive: bool = True,
) -> CommandExecutionResult:
    return tool_library_runtime.policy_doc_import_result(
        self,
        path,
        library_root=library_root,
        recursive=recursive,
    )


def policy_doc_list_result(
    self: Any,
    *,
    library_root: Optional[str] = None,
    limit: int = 50,
) -> CommandExecutionResult:
    return tool_library_runtime.policy_doc_list_result(
        self,
        library_root=library_root,
        limit=limit,
    )


def policy_doc_search_result(
    self: Any,
    query: str,
    *,
    library_root: Optional[str] = None,
    limit: int = 10,
) -> CommandExecutionResult:
    return tool_library_runtime.policy_doc_search_result(
        self,
        query=query,
        library_root=library_root,
        limit=limit,
    )


def policy_doc_read_result(
    self: Any,
    *,
    doc_id: Optional[str] = None,
    path: Optional[str] = None,
    library_root: Optional[str] = None,
    max_chars: int = 12000,
) -> CommandExecutionResult:
    return tool_library_runtime.policy_doc_read_result(
        self,
        doc_id=doc_id,
        path=path,
        library_root=library_root,
        max_chars=max_chars,
    )


BROWSER_POLICY_METHOD_BINDINGS = (
    ("browser", browser),
    ("browser_result", browser_result),
    ("open", open),
    ("open_result", open_result),
    ("click", click),
    ("click_result", click_result),
    ("find", find),
    ("find_result", find_result),
    ("policy_doc_import", policy_doc_import),
    ("policy_doc_list", policy_doc_list),
    ("policy_doc_search", policy_doc_search),
    ("policy_doc_read", policy_doc_read),
    ("policy_doc_import_result", policy_doc_import_result),
    ("policy_doc_list_result", policy_doc_list_result),
    ("policy_doc_search_result", policy_doc_search_result),
    ("policy_doc_read_result", policy_doc_read_result),
)
