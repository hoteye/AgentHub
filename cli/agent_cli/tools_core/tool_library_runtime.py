from __future__ import annotations

from typing import Any, Dict, List, Optional

from cli.agent_cli.tools_core import tool_library_policy_runtime
from cli.agent_cli.tools_core import (
    tool_library_browser_runtime,
    tool_library_document_runtime,
    tool_library_web_runtime,
)
from cli.agent_cli.tools_core import tool_library_file_runtime as tool_library_file_runtime_helpers

glob_files = tool_library_file_runtime_helpers.glob_files
glob_files_result = tool_library_file_runtime_helpers.glob_files_result
grep_files = tool_library_file_runtime_helpers.grep_files
grep_files_result = tool_library_file_runtime_helpers.grep_files_result
list_dir = tool_library_file_runtime_helpers.list_dir
list_dir_result = tool_library_file_runtime_helpers.list_dir_result
read_file = tool_library_file_runtime_helpers.read_file
read_file_result = tool_library_file_runtime_helpers.read_file_result
file_list = tool_library_file_runtime_helpers.file_list
file_list_result = tool_library_file_runtime_helpers.file_list_result
file_search = tool_library_file_runtime_helpers.file_search
file_search_result = tool_library_file_runtime_helpers.file_search_result
file_read = tool_library_file_runtime_helpers.file_read
file_read_result = tool_library_file_runtime_helpers.file_read_result


def office_skills(registry: Any) -> Any:
    return tool_library_document_runtime.office_skills(registry)


def office_skills_result(registry: Any) -> Any:
    return tool_library_document_runtime.office_skills_result(registry)


def office_run(registry: Any, skill_name: str, *, args: Optional[Dict[str, Any]] = None) -> Any:
    return tool_library_document_runtime.office_run(registry, skill_name, args=args)


def office_run_result(registry: Any, skill_name: str, *, args: Optional[Dict[str, Any]] = None) -> Any:
    return tool_library_document_runtime.office_run_result(registry, skill_name, args=args)


def view_image(registry: Any, path: str) -> Any:
    return tool_library_document_runtime.view_image(registry, path)


def view_image_result(registry: Any, path: str) -> Any:
    return tool_library_document_runtime.view_image_result(registry, path)


def web_search(
    registry: Any,
    query: str,
    *,
    limit: int = 5,
    domains: Optional[List[str]] = None,
    recency_days: Optional[int] = None,
    market: Optional[str] = None,
) -> Any:
    return tool_library_web_runtime.web_search(
        registry,
        query,
        limit=limit,
        domains=domains,
        recency_days=recency_days,
        market=market,
    )


def web_search_result(
    registry: Any,
    query: str,
    *,
    limit: int = 5,
    domains: Optional[List[str]] = None,
    recency_days: Optional[int] = None,
    market: Optional[str] = None,
) -> Any:
    return tool_library_web_runtime.web_search_result(
        registry,
        query,
        limit=limit,
        domains=domains,
        recency_days=recency_days,
        market=market,
    )


def web_fetch(registry: Any, url: str, *, max_chars: int = 12000) -> Any:
    return tool_library_web_runtime.web_fetch(registry, url, max_chars=max_chars)


def web_fetch_result(registry: Any, url: str, *, max_chars: int = 12000) -> Any:
    return tool_library_web_runtime.web_fetch_result(registry, url, max_chars=max_chars)


def browser(
    registry: Any,
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
) -> Any:
    return tool_library_browser_runtime.browser(
        registry,
        action,
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


def browser_result(registry: Any, action: str, **kwargs: Any) -> Any:
    return tool_library_browser_runtime.browser_result(registry, action, **kwargs)


def open_tool(registry: Any, ref: str, *, line: int = 1) -> Any:
    return tool_library_browser_runtime.open_tool(registry, ref, line=line)


def open_result(registry: Any, ref: str, *, line: int = 1) -> Any:
    return tool_library_browser_runtime.open_result(registry, ref, line=line)


def click(registry: Any, ref_id: str, *, id: int) -> Any:
    return tool_library_browser_runtime.click(registry, ref_id, id=id)


def click_result(registry: Any, ref_id: str, *, id: int) -> Any:
    return tool_library_browser_runtime.click_result(registry, ref_id, id=id)


def find(registry: Any, ref_id: str, *, pattern: str) -> Any:
    return tool_library_browser_runtime.find(registry, ref_id, pattern=pattern)


def find_result(registry: Any, ref_id: str, *, pattern: str) -> Any:
    return tool_library_browser_runtime.find_result(registry, ref_id, pattern=pattern)


def policy_doc_import(registry: Any, path: str, *, library_root: Optional[str] = None, recursive: bool = True) -> Any:
    return tool_library_policy_runtime.policy_doc_import(
        registry,
        path,
        library_root=library_root,
        recursive=recursive,
    )


def policy_doc_list(registry: Any, *, library_root: Optional[str] = None, limit: int = 50) -> Any:
    return tool_library_policy_runtime.policy_doc_list(
        registry,
        library_root=library_root,
        limit=limit,
    )


def policy_doc_search(registry: Any, query: str, *, library_root: Optional[str] = None, limit: int = 10) -> Any:
    return tool_library_policy_runtime.policy_doc_search(
        registry,
        query,
        library_root=library_root,
        limit=limit,
    )


def policy_doc_read(
    registry: Any,
    *,
    doc_id: Optional[str] = None,
    path: Optional[str] = None,
    library_root: Optional[str] = None,
    max_chars: int = 12000,
) -> Any:
    return tool_library_policy_runtime.policy_doc_read(
        registry,
        doc_id=doc_id,
        path=path,
        library_root=library_root,
        max_chars=max_chars,
    )


def policy_doc_import_result(registry: Any, path: str, *, library_root: Optional[str] = None, recursive: bool = True) -> Any:
    return tool_library_policy_runtime.policy_doc_import_result(
        registry,
        path,
        library_root=library_root,
        recursive=recursive,
    )


def policy_doc_list_result(registry: Any, *, library_root: Optional[str] = None, limit: int = 50) -> Any:
    return tool_library_policy_runtime.policy_doc_list_result(
        registry,
        library_root=library_root,
        limit=limit,
    )


def policy_doc_search_result(registry: Any, query: str, *, library_root: Optional[str] = None, limit: int = 10) -> Any:
    return tool_library_policy_runtime.policy_doc_search_result(
        registry,
        query,
        library_root=library_root,
        limit=limit,
    )


def policy_doc_read_result(
    registry: Any,
    *,
    doc_id: Optional[str] = None,
    path: Optional[str] = None,
    library_root: Optional[str] = None,
    max_chars: int = 12000,
) -> Any:
    return tool_library_policy_runtime.policy_doc_read_result(
        registry,
        doc_id=doc_id,
        path=path,
        library_root=library_root,
        max_chars=max_chars,
    )
