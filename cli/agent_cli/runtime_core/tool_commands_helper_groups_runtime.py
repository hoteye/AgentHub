from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime_core.tool_commands_helper_groups_runtime_plugins import (
    handle_plugin_disable,
    handle_plugin_enable,
    handle_plugin_install,
    handle_plugin_reload,
    handle_plugin_remove,
)
from cli.agent_cli.runtime_core.tool_commands_helper_groups_runtime_web import (
    handle_click,
    handle_find,
    handle_open,
)
from cli.agent_cli.runtime_core.tool_commands_params_runtime import (
    file_read_arguments,
    parse_file_list_args,
    parse_file_read_args,
    parse_file_search_args,
    parse_glob_files_args,
    parse_grep_files_args,
    parse_list_dir_args,
    parse_office_run_args,
    parse_read_file_args,
    parse_view_image_args,
    read_file_arguments,
)

ToolCommandResult = Optional[Tuple[str, List[ToolEvent]] | CommandExecutionResult]


def _canonical_workspace_path(runtime, raw_path: str) -> str:
    tools = getattr(runtime, "tools", None)
    normalized = str(raw_path or "").strip()
    normalize_fn = getattr(tools, "_normalize_workspace_file_path", None)
    if callable(normalize_fn):
        try:
            candidate = str(normalize_fn(normalized) or "").strip()
        except Exception:
            candidate = ""
        if candidate:
            return candidate
    if Path(normalized).is_absolute():
        return normalized
    return normalized


def _canonical_read_file_path(runtime, file_path: str) -> str:
    return _canonical_workspace_path(runtime, file_path)


def _canonical_list_dir_path(runtime, dir_path: str | None) -> str:
    normalized = str(dir_path or "").strip()
    if not normalized:
        normalized = "."
    return _canonical_workspace_path(runtime, normalized)


def _install_runtime_view_image_capabilities(runtime) -> Callable[[], None]:
    tools = getattr(runtime, "tools", None)
    if tools is None:
        return lambda: None
    from cli.agent_cli.providers.reference_parity import (
        reference_view_image_detail,
        reference_view_image_input_capable,
    )
    from cli.agent_cli.runtime_tools_surface_runtime import runtime_provider_config

    config = runtime_provider_config(runtime)
    if config is None:
        return lambda: None
    marker = object()
    previous_detail = getattr(tools, "_view_image_detail", marker)
    previous_capable = getattr(tools, "_view_image_input_capable", marker)
    setattr(tools, "_view_image_detail", reference_view_image_detail(config))
    setattr(tools, "_view_image_input_capable", reference_view_image_input_capable(config))

    def _restore() -> None:
        if previous_detail is marker:
            try:
                delattr(tools, "_view_image_detail")
            except AttributeError:
                pass
        else:
            setattr(tools, "_view_image_detail", previous_detail)
        if previous_capable is marker:
            try:
                delattr(tools, "_view_image_input_capable")
            except AttributeError:
                pass
        else:
            setattr(tools, "_view_image_input_capable", previous_capable)

    return _restore


def handle_glob_files(
    runtime,
    *,
    arg_text: str,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    command_usage_text: Callable[[str], str],
) -> ToolCommandResult:
    parsed = parse_glob_files_args(runtime._parse_args, arg_text)
    pattern = parsed["pattern"]
    if not pattern:
        return text_only_result(
            command_usage_text("glob_files")
            or "Usage: /glob_files <pattern> [path <dir>] [limit <n>]"
        )
    structured = call_structured(
        runtime.tools,
        "glob_files_result",
        pattern,
        path=parsed["path"],
        limit=parsed["limit"],
    )
    if structured is not None:
        return structured
    return single_event_result(
        "Find workspace files by pattern.",
        runtime.tools.glob_files(pattern, path=parsed["path"], limit=parsed["limit"]),
        arguments=parsed,
        tool_name="glob_files",
        prefer_result_text=True,
    )


def handle_grep_files(
    runtime,
    *,
    arg_text: str,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    command_usage_text: Callable[[str], str],
) -> ToolCommandResult:
    parsed = parse_grep_files_args(runtime._parse_args, arg_text)
    pattern = parsed["pattern"]
    if not pattern:
        return text_only_result(
            command_usage_text("grep_files")
            or "Usage: /grep_files <pattern> [include <glob>] [path <dir>] [limit <n>]"
        )
    structured = call_structured(
        runtime.tools,
        "grep_files_result",
        pattern,
        include=parsed["include"],
        path=parsed["path"],
        limit=parsed["limit"],
        output_mode=parsed["output_mode"],
        case_insensitive=parsed["case_insensitive"],
        file_type=parsed["file_type"],
        line_numbers=parsed["line_numbers"],
        after_context=parsed["after_context"],
        before_context=parsed["before_context"],
        context=parsed["context"],
        offset=parsed["offset"],
        multiline=parsed["multiline"],
    )
    if structured is not None:
        return structured
    return single_event_result(
        "Search workspace file paths.",
        runtime.tools.grep_files(
            pattern,
            include=parsed["include"],
            path=parsed["path"],
            limit=parsed["limit"],
            output_mode=parsed["output_mode"],
            case_insensitive=parsed["case_insensitive"],
            file_type=parsed["file_type"],
            line_numbers=parsed["line_numbers"],
            after_context=parsed["after_context"],
            before_context=parsed["before_context"],
            context=parsed["context"],
            offset=parsed["offset"],
            multiline=parsed["multiline"],
        ),
        arguments=parsed,
        tool_name="grep_files",
        prefer_result_text=True,
    )


def handle_list_dir(
    runtime,
    *,
    arg_text: str,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    command_usage_text: Callable[[str], str],
) -> ToolCommandResult:
    parsed = parse_list_dir_args(runtime._parse_args, arg_text)
    canonical_dir_path = _canonical_list_dir_path(runtime, parsed["dir_path"])
    structured = call_structured(
        runtime.tools,
        "list_dir_result",
        dir_path=canonical_dir_path,
        offset=parsed["offset"],
        limit=parsed["limit"],
        depth=parsed["depth"],
    )
    if structured is not None:
        return structured
    arguments = dict(parsed)
    arguments["dir_path"] = canonical_dir_path
    return single_event_result(
        "List workspace directory.",
        runtime.tools.list_dir(
            dir_path=canonical_dir_path,
            offset=parsed["offset"],
            limit=parsed["limit"],
            depth=parsed["depth"],
        ),
        arguments=arguments,
        tool_name="list_dir",
        prefer_result_text=True,
    )


def handle_read_file(
    runtime,
    *,
    arg_text: str,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    command_usage_text: Callable[[str], str],
) -> ToolCommandResult:
    parsed = parse_read_file_args(runtime._parse_args, arg_text)
    file_path = parsed["file_path"]
    if not file_path:
        return text_only_result(
            command_usage_text("read_file")
            or "Usage: /read_file <file_path> [offset <line>] [limit <n>]"
        )
    canonical_file_path = _canonical_read_file_path(runtime, file_path)
    structured = call_structured(
        runtime.tools,
        "read_file_result",
        canonical_file_path,
        offset=parsed["offset"],
        limit=parsed["limit"],
        mode=parsed["mode"],
        indentation=parsed["indentation"],
    )
    if structured is not None:
        return structured
    read_kwargs = dict(read_file_arguments(parsed))
    read_kwargs.pop("file_path", None)
    arguments = read_file_arguments(parsed)
    arguments["file_path"] = canonical_file_path
    return single_event_result(
        "Read workspace file.",
        runtime.tools.read_file(canonical_file_path, **read_kwargs),
        arguments=arguments,
        tool_name="read_file",
        prefer_result_text=True,
    )


def handle_file_list(
    runtime,
    *,
    arg_text: str,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
) -> ToolCommandResult:
    parsed = parse_file_list_args(runtime._parse_args, arg_text)
    structured = call_structured(runtime.tools, "file_list_result", path=parsed["path"], limit=parsed["limit"])
    if structured is not None:
        return structured
    arguments = dict(parsed)
    arguments["path"] = parsed["path"] or "."
    return single_event_result(
        "List workspace files.",
        runtime.tools.file_list(path=parsed["path"], limit=parsed["limit"]),
        arguments=arguments,
    )


def handle_file_search(
    runtime,
    *,
    arg_text: str,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    command_usage_text: Callable[[str], str],
) -> ToolCommandResult:
    parsed = parse_file_search_args(runtime._parse_args, arg_text)
    query = parsed["query"]
    if not query:
        return text_only_result(command_usage_text("file_search") or "Usage: /file_search <query> [path <dir>] [limit <n>]")
    structured = call_structured(runtime.tools, "file_search_result", query, path=parsed["path"], limit=parsed["limit"])
    if structured is not None:
        return structured
    return single_event_result(
        "Search workspace files.",
        runtime.tools.file_search(query, path=parsed["path"], limit=parsed["limit"]),
        arguments=parsed,
    )


def handle_file_read(
    runtime,
    *,
    arg_text: str,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    command_usage_text: Callable[[str], str],
) -> ToolCommandResult:
    parsed = parse_file_read_args(runtime._parse_args, arg_text)
    target_path = parsed["path"]
    if not target_path:
        return text_only_result(
            command_usage_text("file_read") or "Usage: /file_read <path> [offset <line>] [limit <n>]"
        )
    structured = call_structured(
        runtime.tools,
        "file_read_result",
        target_path,
        offset=parsed["offset"],
        limit=parsed["limit"],
        max_chars=parsed["max_chars"],
    )
    if structured is not None:
        return structured
    file_read_kwargs = dict(file_read_arguments(parsed))
    file_read_kwargs.pop("path", None)
    return single_event_result(
        "Read workspace file.",
        runtime.tools.file_read(target_path, **file_read_kwargs),
        arguments=file_read_arguments(parsed),
    )


def handle_office_skills(
    runtime,
    *,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
) -> ToolCommandResult:
    structured = call_structured(runtime.tools, "office_skills_result")
    if structured is not None:
        return structured
    return single_event_result("List Office and PDF skills.", runtime.tools.office_skills())


def handle_office_run(
    runtime,
    *,
    arg_text: str,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    command_usage_text: Callable[[str], str],
) -> ToolCommandResult:
    parsed = parse_office_run_args(runtime._parse_args, arg_text)
    if not parsed["positionals"]:
        return text_only_result(command_usage_text("office_run") or "Usage: /office_run <skill> <file>")
    structured = call_structured(runtime.tools, "office_run_result", parsed["skill_name"], args=parsed["args"])
    if structured is not None:
        return structured
    return single_event_result(
        "Run Office or PDF skill.",
        runtime.tools.office_run(parsed["skill_name"], args=parsed["args"]),
        arguments={"skill_name": parsed["skill_name"], "args": parsed["args"] or None},
    )


def handle_view_image(
    runtime,
    *,
    arg_text: str,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    command_usage_text: Callable[[str], str],
) -> ToolCommandResult:
    target_path = parse_view_image_args(runtime._parse_args, arg_text)
    if not target_path:
        return text_only_result(command_usage_text("view_image") or "Usage: /view_image <path>")
    restore_view_image_capabilities = _install_runtime_view_image_capabilities(runtime)
    try:
        structured = call_structured(runtime.tools, "view_image_result", target_path)
        if structured is not None:
            return structured
        return single_event_result(
            "View local image.",
            runtime.tools.view_image(target_path),
            arguments={"path": target_path},
        )
    finally:
        restore_view_image_capabilities()
