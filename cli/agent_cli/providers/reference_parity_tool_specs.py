from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.providers.builtin_provider_tool_specs import _BUILTIN_PROVIDER_SPEC_ORDER
from cli.agent_cli.providers.reference_parity import (
    reference_apply_patch_tool_type,
    reference_collab_tools_enabled,
    reference_default_mode_request_user_input,
    reference_supports_experimental_tool,
    reference_request_permission_enabled,
    reference_web_search_external_web_access,
    load_reference_apply_patch_grammar,
)
from cli.agent_cli.providers import reference_parity_tool_specs_helpers as specs_helpers
from cli.agent_cli.providers import reference_parity_tool_specs_collab_helpers as collab_specs_helpers
from cli.agent_cli.providers.config_catalog import ProviderConfig, optional_bool

_REFERENCE_UPDATE_PLAN_DESCRIPTION = """Updates the task plan.
Provide an optional explanation and a list of plan items, each with a step and status.
At most one step can be in_progress at a time.
"""
_REFERENCE_EXEC_COMMAND_JUSTIFICATION_DESCRIPTION = """Only set if sandbox_permissions is \\"require_escalated\\".
                    Request approval from the user to run this command outside the sandbox.
                    Phrased as a simple question that summarizes the purpose of the
                    command as it relates to the task at hand - e.g. 'Do you want to
                    fetch and pull the latest version of this git branch?'"""
_REFERENCE_EXEC_COMMAND_PREFIX_RULE_DESCRIPTION = """Only specify when sandbox_permissions is `require_escalated`.
                        Suggest a prefix command pattern that will allow you to fulfill similar requests from the user in the future.
                        Should be a short but reasonable prefix, e.g. [\\"git\\", \\"pull\\"] or [\\"uv\\", \\"run\\"] or [\\"pytest\\"]."""
_REFERENCE_REQUEST_USER_INPUT_DESCRIPTION_TEMPLATE = (
    "Request user input for one to three short questions and wait for the response. "
    "This tool is only available in {allowed_modes}."
)
_REFERENCE_APPLY_PATCH_DESCRIPTION = (
    "Use the `apply_patch` tool to edit files. This is a FREEFORM tool, so do not wrap the patch in JSON."
)


def _reference_parity_scalar_schema(type_name: str, description: str | None = None) -> Dict[str, Any]:
    schema: Dict[str, Any] = {}
    if description is not None:
        schema["description"] = description
    schema["type"] = type_name
    return schema


def _reference_parity_array_schema(*, items: Dict[str, Any], description: str | None = None) -> Dict[str, Any]:
    schema: Dict[str, Any] = {}
    if description is not None:
        schema["description"] = description
    schema["items"] = items
    schema["type"] = "array"
    return schema


def _reference_parity_object_schema(
    *,
    properties: Dict[str, Any],
    required: List[str] | None = None,
) -> Dict[str, Any]:
    schema: Dict[str, Any] = {
        "additionalProperties": False,
        "properties": {key: properties[key] for key in sorted(properties)},
    }
    if required:
        schema["required"] = list(required)
    schema["type"] = "object"
    return schema


def _reference_request_user_input_description(config: ProviderConfig) -> str:
    allowed_modes = "Default or Plan mode" if reference_default_mode_request_user_input(config) else "Plan mode"
    return _REFERENCE_REQUEST_USER_INPUT_DESCRIPTION_TEMPLATE.format(allowed_modes=allowed_modes)


def _reference_expert_review_available(config: ProviderConfig) -> bool:
    raw_provider = dict(getattr(config, "raw_provider", {}) or {})
    raw_model = dict(getattr(config, "raw_model", {}) or {})
    mappings = [
        raw_provider,
        raw_model,
        dict(raw_provider.get("provider_status") or {}) if isinstance(raw_provider.get("provider_status"), dict) else {},
        dict(raw_provider.get("expert_review_gate_snapshot") or {})
        if isinstance(raw_provider.get("expert_review_gate_snapshot"), dict)
        else {},
    ]
    for mapping in mappings:
        if "expert_review_available" not in mapping:
            continue
        return optional_bool(mapping.get("expert_review_available"), False)
    return False


def _reference_expert_review_tool() -> Dict[str, Any]:
    return _reference_parity_function_tool(
        name="expert_review",
        description=(
            "Request a read-only expert review from a secondary eligible provider. "
            "Use this for critical read-only review of the current mainline work when a separate provider or model should verify the answer before finalizing it. "
            "Do not use it as a substitute for normal mainline reasoning or ordinary tool execution."
        ),
        properties={
            "task": _reference_parity_scalar_schema("string", "What the reviewer should check."),
        },
        required=["task"],
    )


def _insert_reference_tool_by_builtin_order(
    specs: List[Dict[str, Any]],
    tool_spec: Dict[str, Any],
) -> None:
    tool_name = str(tool_spec.get("name") or "").strip()
    if not tool_name:
        specs.append(tool_spec)
        return
    try:
        target_order = _BUILTIN_PROVIDER_SPEC_ORDER.index(tool_name)
    except ValueError:
        specs.append(tool_spec)
        return
    insert_at = len(specs)
    for index, item in enumerate(specs):
        candidate_name = str(item.get("name") or "").strip()
        if not candidate_name:
            continue
        try:
            candidate_order = _BUILTIN_PROVIDER_SPEC_ORDER.index(candidate_name)
        except ValueError:
            continue
        if candidate_order > target_order:
            insert_at = index
            break
    specs.insert(insert_at, tool_spec)


def _reference_exec_command_properties(config: ProviderConfig) -> Dict[str, Any]:
    request_permission_enabled = reference_request_permission_enabled(config)
    sandbox_permissions_description = (
        "Sandbox permissions for the command. Use \"with_additional_permissions\" to request additional sandboxed filesystem or network access (preferred), or \"require_escalated\" to request running without sandbox restrictions; defaults to \"use_default\"."
        if request_permission_enabled
        else "Sandbox permissions for the command. Set to \"require_escalated\" to request running without sandbox restrictions; defaults to \"use_default\"."
    )
    properties: Dict[str, Any] = {
        "cmd": _reference_parity_scalar_schema("string", "Shell command to execute."),
        "justification": _reference_parity_scalar_schema("string", _REFERENCE_EXEC_COMMAND_JUSTIFICATION_DESCRIPTION),
        "login": _reference_parity_scalar_schema("boolean", "Whether to run the shell with -l/-i semantics. Defaults to true."),
        "max_output_tokens": _reference_parity_scalar_schema("number", "Maximum number of tokens to return. Excess output will be truncated."),
        "prefix_rule": _reference_parity_array_schema(
            items=_reference_parity_scalar_schema("string"),
            description=_REFERENCE_EXEC_COMMAND_PREFIX_RULE_DESCRIPTION,
        ),
        "sandbox_permissions": _reference_parity_scalar_schema(
            "string",
            sandbox_permissions_description,
        ),
        "shell": _reference_parity_scalar_schema("string", "Shell binary to launch. Defaults to the user's default shell."),
        "tty": _reference_parity_scalar_schema(
            "boolean",
            "Whether to allocate a TTY for the command. Defaults to false (plain pipes); set to true to open a PTY and access TTY process.",
        ),
        "workdir": _reference_parity_scalar_schema(
            "string",
            "Optional working directory to run the command in; defaults to the turn cwd. Prefer setting this instead of prepending `cd` to the command.",
        ),
        "yield_time_ms": _reference_parity_scalar_schema("number", "How long to wait (in milliseconds) for output before yielding."),
    }
    if request_permission_enabled:
        properties["additional_permissions"] = _reference_parity_object_schema(
            properties={
                "file_system": _reference_parity_object_schema(
                    properties={
                        "read": _reference_parity_array_schema(
                            items=_reference_parity_scalar_schema("string"),
                            description="Additional filesystem paths to grant read access for this command.",
                        ),
                        "write": _reference_parity_array_schema(
                            items=_reference_parity_scalar_schema("string"),
                            description="Additional filesystem paths to grant write access for this command.",
                        ),
                    }
                ),
                "network": _reference_parity_object_schema(
                    properties={
                        "enabled": _reference_parity_scalar_schema(
                            "boolean",
                            "Whether to grant network access for this command.",
                        ),
                    }
                ),
            },
        )
    return properties


def _reference_parity_function_tool(
    *,
    name: str,
    description: str,
    properties: Dict[str, Any],
    required: List[str],
) -> Dict[str, Any]:
    return {
        "description": description,
        "name": name,
        "parameters": _reference_parity_object_schema(properties=properties, required=required),
        "strict": False,
        "type": "function",
    }


def _reference_grep_files_tool() -> Dict[str, Any]:
    return _reference_parity_function_tool(
        name="grep_files",
        description="Finds files whose contents match the pattern and lists them by modification time.",
        properties={
            "pattern": _reference_parity_scalar_schema("string", "Regular expression pattern to search for."),
            "include": _reference_parity_scalar_schema(
                "string",
                'Optional glob that limits which files are searched (e.g. "*.rs" or "*.{ts,tsx}").',
            ),
            "path": _reference_parity_scalar_schema(
                "string",
                "Directory or file path to search. Defaults to the session's working directory.",
            ),
            "limit": _reference_parity_scalar_schema(
                "number",
                "Maximum number of file paths to return (defaults to 100).",
            ),
        },
        required=["pattern"],
    )


def _reference_read_file_tool() -> Dict[str, Any]:
    return _reference_parity_function_tool(
        name="read_file",
        description="Reads a local file with 1-indexed line numbers, supporting slice and indentation-aware block modes.",
        properties={
            "file_path": _reference_parity_scalar_schema("string", "Absolute path to the file"),
            "offset": _reference_parity_scalar_schema(
                "number",
                "The line number to start reading from. Must be 1 or greater.",
            ),
            "limit": _reference_parity_scalar_schema(
                "number",
                "The maximum number of lines to return.",
            ),
            "mode": _reference_parity_scalar_schema(
                "string",
                'Optional mode selector: "slice" for simple ranges (default) or "indentation" to expand around an anchor line.',
            ),
            "indentation": _reference_parity_object_schema(
                properties={
                    "anchor_line": _reference_parity_scalar_schema(
                        "number",
                        "Anchor line to center the indentation lookup on (defaults to offset).",
                    ),
                    "max_levels": _reference_parity_scalar_schema(
                        "number",
                        "How many parent indentation levels (smaller indents) to include.",
                    ),
                    "include_siblings": _reference_parity_scalar_schema(
                        "boolean",
                        "When true, include additional blocks that share the anchor indentation.",
                    ),
                    "include_header": _reference_parity_scalar_schema(
                        "boolean",
                        "Include doc comments or attributes directly above the selected block.",
                    ),
                    "max_lines": _reference_parity_scalar_schema(
                        "number",
                        "Hard cap on the number of lines returned when using indentation mode.",
                    ),
                },
            ),
        },
        required=["file_path"],
    )


def _reference_list_dir_tool() -> Dict[str, Any]:
    return _reference_parity_function_tool(
        name="list_dir",
        description="Lists entries in a local directory with 1-indexed entry numbers and simple type labels.",
        properties={
            "dir_path": _reference_parity_scalar_schema("string", "Absolute path to the directory to list."),
            "offset": _reference_parity_scalar_schema(
                "number",
                "The entry number to start listing from. Must be 1 or greater.",
            ),
            "limit": _reference_parity_scalar_schema(
                "number",
                "The maximum number of entries to return.",
            ),
            "depth": _reference_parity_scalar_schema(
                "number",
                "The maximum directory depth to traverse. Must be 1 or greater.",
            ),
        },
        required=["dir_path"],
    )


def reference_parity_responses_minimal_tool_specs(config: ProviderConfig) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = [
        _reference_parity_function_tool(
            name="exec_command",
            description="Runs a command in a PTY, returning output or a session ID for ongoing interaction.",
            properties=_reference_exec_command_properties(config),
            required=["cmd"],
        ),
        _reference_parity_function_tool(
            name="write_stdin",
            description="Writes characters to an existing unified exec session and returns recent output.",
            properties={
                "chars": _reference_parity_scalar_schema("string", "Bytes to write to stdin (may be empty to poll)."),
                "max_output_tokens": _reference_parity_scalar_schema("number", "Maximum number of tokens to return. Excess output will be truncated."),
                "session_id": _reference_parity_scalar_schema("number", "Identifier of the running unified exec session."),
                "yield_time_ms": _reference_parity_scalar_schema("number", "How long to wait (in milliseconds) for output before yielding."),
            },
            required=["session_id"],
        ),
    ]
    specs.extend(
        specs_helpers.plan_and_user_input_specs(
            config=config,
            function_tool_fn=_reference_parity_function_tool,
            scalar_schema_fn=_reference_parity_scalar_schema,
            array_schema_fn=_reference_parity_array_schema,
            object_schema_fn=_reference_parity_object_schema,
            request_user_input_description_fn=_reference_request_user_input_description,
            update_plan_description=_REFERENCE_UPDATE_PLAN_DESCRIPTION,
        )
    )
    tail_specs: List[Dict[str, Any]] = []
    specs_helpers.append_apply_patch_and_tail_specs(
        specs=tail_specs,
        apply_patch_tool_type=reference_apply_patch_tool_type(config),
        apply_patch_description=_REFERENCE_APPLY_PATCH_DESCRIPTION,
        load_apply_patch_grammar_fn=load_reference_apply_patch_grammar,
        function_tool_fn=_reference_parity_function_tool,
        scalar_schema_fn=_reference_parity_scalar_schema,
        external_web_access=reference_web_search_external_web_access(config),
    )
    if tail_specs and (
        tail_specs[0].get("name") == "apply_patch" or str(tail_specs[0].get("type") or "").strip() == "custom"
    ):
        specs.append(tail_specs.pop(0))
    if reference_supports_experimental_tool(config, "grep_files"):
        specs.append(_reference_grep_files_tool())
    if reference_supports_experimental_tool(config, "read_file"):
        specs.append(_reference_read_file_tool())
    if reference_supports_experimental_tool(config, "list_dir"):
        specs.append(_reference_list_dir_tool())
    specs.extend(tail_specs)
    if reference_collab_tools_enabled(config):
        specs.extend(
            collab_specs_helpers.reference_collab_tool_specs(
                function_tool_fn=_reference_parity_function_tool,
                scalar_schema_fn=_reference_parity_scalar_schema,
                array_schema_fn=_reference_parity_array_schema,
                object_schema_fn=_reference_parity_object_schema,
            )
        )
    return specs
