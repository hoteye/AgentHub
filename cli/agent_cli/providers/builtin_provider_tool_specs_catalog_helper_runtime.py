from __future__ import annotations

from typing import Any, Callable


def function_spec(
    *,
    function_tool: Callable[..., dict[str, Any]],
    provider_description: Callable[[str], str],
    name: str,
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "name": name,
        "description": provider_description(name),
    }
    if properties is not None:
        kwargs["properties"] = properties
    if required is not None:
        kwargs["required"] = required
    return function_tool(**kwargs)


def read_file_properties() -> dict[str, Any]:
    return {
        "file_path": {
            "type": "string",
            "description": "Absolute path to the file",
        },
        "offset": {
            "type": "number",
            "description": "The line number to start reading from. Must be 1 or greater.",
        },
        "limit": {
            "type": "number",
            "description": "The maximum number of lines to return.",
        },
        "mode": {
            "type": "string",
            "description": 'Optional mode selector: "slice" for simple ranges (default) or "indentation" to expand around an anchor line.',
        },
        "indentation": {
            "type": "object",
            "properties": {
                "anchor_line": {
                    "type": "number",
                    "description": "Anchor line to center the indentation lookup on (defaults to offset).",
                },
                "max_levels": {
                    "type": "number",
                    "description": "How many parent indentation levels (smaller indents) to include.",
                },
                "include_siblings": {
                    "type": "boolean",
                    "description": "When true, include additional blocks that share the anchor indentation.",
                },
                "include_header": {
                    "type": "boolean",
                    "description": "Include doc comments or attributes directly above the selected block.",
                },
                "max_lines": {
                    "type": "number",
                    "description": "Hard cap on the number of lines returned when using indentation mode.",
                },
            },
            "additionalProperties": False,
        },
    }


def list_dir_properties() -> dict[str, Any]:
    return {
        "dir_path": {
            "type": "string",
            "description": "Absolute path to the directory to list.",
        },
        "offset": {
            "type": "integer",
            "description": "The entry number to start listing from. Must be 1 or greater.",
        },
        "limit": {
            "type": "integer",
            "description": "The maximum number of entries to return.",
        },
        "depth": {
            "type": "integer",
            "description": "The maximum directory depth to traverse. Must be 1 or greater.",
        },
    }


def file_search_properties() -> dict[str, Any]:
    return {
        "query": {"type": "string"},
        "path": {"type": "string"},
        "limit": {"type": "integer"},
    }


def file_read_properties() -> dict[str, Any]:
    return {
        "path": {"type": "string"},
        "offset": {"type": "integer"},
        "limit": {"type": "integer"},
        "max_chars": {"type": "integer"},
    }


def file_list_properties() -> dict[str, Any]:
    return {
        "path": {"type": "string"},
        "limit": {"type": "integer"},
    }


def web_fetch_properties() -> dict[str, Any]:
    return {
        "url": {"type": "string"},
        "max_chars": {"type": "integer"},
    }


def open_properties() -> dict[str, Any]:
    return {
        "ref": {"type": "string"},
        "line": {"type": "integer"},
    }


def click_properties() -> dict[str, Any]:
    return {
        "ref_id": {"type": "string"},
        "id": {"type": "integer"},
    }


def find_properties() -> dict[str, Any]:
    return {
        "ref_id": {"type": "string"},
        "pattern": {"type": "string"},
    }


def policy_doc_import_properties() -> dict[str, Any]:
    return {
        "path": {"type": "string"},
        "library_root": {"type": "string"},
        "no_recursive": {"type": "boolean"},
    }


def policy_doc_list_properties() -> dict[str, Any]:
    return {
        "library_root": {"type": "string"},
        "limit": {"type": "integer"},
    }


def policy_doc_search_properties() -> dict[str, Any]:
    return {
        "query": {"type": "string"},
        "library_root": {"type": "string"},
        "limit": {"type": "integer"},
    }


def policy_doc_read_properties() -> dict[str, Any]:
    return {
        "doc_id": {"type": "string"},
        "path": {"type": "string"},
        "library_root": {"type": "string"},
        "max_chars": {"type": "integer"},
    }
