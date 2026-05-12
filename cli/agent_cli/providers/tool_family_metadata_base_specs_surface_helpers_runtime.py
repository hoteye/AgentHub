from __future__ import annotations

from typing import Any, Callable, Dict, Tuple


SurfaceUsageTextFn = Callable[[str], str]
StaticContractMetadataFn = Callable[[], Dict[str, Any]]


def workspace_and_remote_tool_specs(
    *,
    surface_usage_text_fn: SurfaceUsageTextFn,
    browser_runtime_actions: Tuple[str, ...],
    browser_provider_actions: Tuple[str, ...],
    expert_review_contract_metadata: StaticContractMetadataFn,
) -> Tuple[Dict[str, Any], ...]:
    return (
        {
            "name": "grep_files",
            "label": "Grep Files",
            "description": "Canonical local code discovery tool. Search workspace text and return matching file paths.",
            "model_default_exposure": "canonical",
            "usage_text": f"Usage: {surface_usage_text_fn('grep_files')}",
            "provider_description": (
                "Canonical local code discovery tool. "
                "Search workspace text and return matching file paths. "
                "Prefer this before read_file for Reference-aligned local inspection."
            ),
        },
        {
            "name": "read_file",
            "label": "Read File",
            "description": "Canonical local file inspection tool. Read one workspace file by slice or indentation mode.",
            "model_default_exposure": "canonical",
            "usage_text": f"Usage: {surface_usage_text_fn('read_file')}",
            "provider_description": (
                "Canonical local file inspection tool. "
                "Read one workspace file region after grep_files/list_dir discovery."
            ),
        },
        {
            "name": "list_dir",
            "label": "List Directory",
            "description": "Canonical local structure discovery tool with pagination and depth controls.",
            "model_default_exposure": "canonical",
            "usage_text": f"Usage: {surface_usage_text_fn('list_dir')}",
            "provider_description": (
                "Canonical local structure discovery tool. "
                "List workspace directory entries with pagination and depth before read_file."
            ),
        },
        {
            "name": "file_list",
            "label": "File List",
            "description": "Legacy compatibility alias for directory listing. Prefer list_dir for Reference-aligned workspace inspection.",
            "model_default_exposure": "compatibility_alias",
            "usage_text": f"Usage: {surface_usage_text_fn('file_list')}",
            "provider_description": (
                "Legacy compatibility alias for directory listing. "
                "Prefer list_dir(dir_path, offset, limit, depth) for Reference-aligned behavior."
            ),
        },
        {
            "name": "file_search",
            "label": "File Search",
            "description": "Legacy compatibility alias for code discovery. Prefer grep_files for Reference-aligned file discovery.",
            "model_default_exposure": "compatibility_alias",
            "usage_text": f"Usage: {surface_usage_text_fn('file_search')}",
            "provider_description": (
                "Legacy compatibility alias for local code discovery. "
                "Prefer grep_files(pattern, include, path, limit), then read_file/file_read for exact line inspection."
            ),
        },
        {
            "name": "file_read",
            "label": "File Read",
            "description": "Legacy compatibility alias for read_file.",
            "model_default_exposure": "compatibility_alias",
            "usage_text": f"Usage: {surface_usage_text_fn('file_read')}",
            "provider_description": (
                "Legacy compatibility alias for read_file. "
                "Prefer read_file(file_path, offset, limit, mode, indentation) for Reference-style local inspection."
            ),
        },
        {
            "name": "office_skills",
            "label": "Office Skills",
            "description": "List file-level Office/PDF skills exposed by the parent project.",
            "usage_text": "Usage: /office_skills",
            "provider_description": "List available Office and PDF skills.",
        },
        {
            "name": "office_run",
            "label": "Run Office Skill",
            "description": "Run a single Office/PDF skill against a local file.",
            "usage_text": f"Usage: {surface_usage_text_fn('office_run')}",
            "provider_description": "Run an Office or PDF skill against a local file path.",
        },
        {
            "name": "web_search",
            "label": "Web Search",
            "description": "Search the public web for current information and return structured results.",
            "usage_text": f"Usage: {surface_usage_text_fn('web_search')}",
            "provider_description": (
                "Search the public web for current information. "
                "Use this for news, changing facts, online documentation, or sources outside the local workspace."
            ),
        },
        {
            "name": "view_image",
            "label": "View Image",
            "description": "View a local image from the filesystem.",
            "usage_text": "Usage: /view_image <path>",
            "provider_description": (
                "View a local image from the filesystem. "
                "Only use this when you have a concrete local image path to inspect."
            ),
        },
        {
            "name": "expert_review",
            "label": "Expert Review",
            "description": "Request a read-only expert review from a secondary eligible provider.",
            "usage_text": "Usage: /expert_review '{\"task\":\"...\"}'",
            "provider_description": (
                "Request a read-only expert review from a secondary eligible provider. "
                "Use this for critical read-only review of the current mainline work when a separate provider or model should verify the answer before finalizing it. "
                "Do not use it as a substitute for normal mainline reasoning, ordinary tool execution, or direct final answering. "
                "Only call it when the tool is exposed in this session; reviewer reasoning effort is fixed by runtime policy."
            ),
            **expert_review_contract_metadata(),
        },
        {
            "name": "web_fetch",
            "label": "Web Fetch",
            "description": "Fetch one webpage and extract readable text from it.",
            "usage_text": f"Usage: {surface_usage_text_fn('web_fetch')}",
            "provider_description": (
                "Fetch one webpage or documentation page and extract readable text from it. "
                "Use this after web_search when you need source details before answering."
            ),
        },
        {
            "name": "browser",
            "label": "Browser",
            "description": "Control the managed browser session (status/start/stop/profiles/tabs/open/focus/close/navigate/snapshot/screenshot/pdf/download/wait_download/console/errors/requests/highlight/trace_start/trace_stop/cookies/cookies_get/cookies_set/cookies_clear/storage/storage_state/storage_get/storage_set/storage_clear/act/upload/dialog).",
            "model_default_exposure": "canonical",
            "usage_text": f"Usage: {surface_usage_text_fn('browser')}",
            "provider_description": (
                "Control the managed browser (status/start/stop/profiles/tabs/open/focus/close/navigate/snapshot/"
                "screenshot/pdf/download/wait_download/console/errors/requests/highlight/trace_start/trace_stop/"
                "cookies/cookies_get/cookies_set/cookies_clear/storage_state/storage_get/storage_set/storage_clear/"
                "act/upload/dialog). For action=act, kind=evaluate is gated by browser config and uses fn as the page "
                "function source."
            ),
            "mutates_ui": True,
            "slash_actions": browser_runtime_actions,
            "provider_actions": browser_provider_actions,
        },
    )
