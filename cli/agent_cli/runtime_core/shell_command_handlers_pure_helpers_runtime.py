from __future__ import annotations

from dataclasses import dataclass
import json
import shlex
from typing import Any, Callable

from cli.agent_cli.slash_parser import SlashInvocation, slash_keyword_map, slash_switch_set


@dataclass(frozen=True, slots=True)
class ExecCommandInputs:
    command: str
    workdir: str | None
    shell_override: str | None
    shell: str | None
    tty: bool
    login: Any
    yield_time_ms: Any
    timeout_ms: Any
    max_output_tokens: Any
    sandbox_permissions: Any
    justification: Any
    prefix_rule: Any
    additional_permissions_json: Any


@dataclass(frozen=True, slots=True)
class ExecCommandRequest:
    command: str
    workdir: str | None
    shell_override: str | None
    shell: str | None
    tty: bool
    login: bool
    yield_time_ms: int | None
    timeout_ms: int | None
    max_output_tokens: int | None
    sandbox_permissions: str | None
    justification: str | None
    prefix_rule: tuple[str, ...] | None
    additional_permissions: dict[str, Any] | None


def requested_shell_option(shell: Any) -> str | None:
    raw = str(shell or "").strip()
    return raw or None


def resolved_shell_value(session_shell: Any, fallback: str | None) -> str | None:
    resolved = str(session_shell or fallback or "").strip()
    return resolved or None


def shell_contract_payload(
    payload: dict[str, Any],
    *,
    shell_override: str | None,
    resolved_shell: str | None,
) -> dict[str, Any]:
    enriched = dict(payload or {})
    if shell_override:
        enriched["shell_override"] = shell_override
    if resolved_shell:
        enriched["resolved_shell"] = resolved_shell
        enriched.setdefault("shell", resolved_shell)
    return enriched


def enrich_tool_event_shell_contract(
    event: Any,
    *,
    shell_override: str | None,
    resolved_shell: str | None,
) -> Any:
    event.payload = shell_contract_payload(
        dict(getattr(event, "payload", None) or {}),
        shell_override=shell_override,
        resolved_shell=resolved_shell,
    )
    return event


def slash_parsed_args(slash_invocation: SlashInvocation | None) -> tuple[list[str], dict[str, Any]] | None:
    if slash_invocation is None:
        return None
    options: dict[str, Any] = dict(slash_keyword_map(slash_invocation))
    for switch_name in slash_switch_set(slash_invocation):
        options[switch_name] = True
    return [str(item) for item in slash_invocation.positionals], options


def parse_exec_command_inputs(
    *,
    runtime: Any,
    arg_text: str,
    slash_invocation: SlashInvocation | None,
    normalize_shell_option_fn: Callable[[Any, Any], str | None],
) -> ExecCommandInputs:
    slash_args = slash_parsed_args(slash_invocation)
    if slash_args is not None:
        positionals, options = slash_args
    else:
        positionals, options = runtime._parse_args(arg_text)
    return ExecCommandInputs(
        command=str(options.get("cmd") or " ".join(positionals)).strip(),
        workdir=str(options.get("workdir") or "").strip() or None,
        shell_override=requested_shell_option(options.get("shell")),
        shell=normalize_shell_option_fn(runtime, requested_shell_option(options.get("shell"))),
        tty=bool(options.get("tty")),
        login=options.get("login"),
        yield_time_ms=options.get("yield-time-ms"),
        timeout_ms=options.get("timeout-ms"),
        max_output_tokens=options.get("max-output-tokens"),
        sandbox_permissions=options.get("sandbox-permissions"),
        justification=options.get("justification"),
        prefix_rule=options.get("prefix-rule"),
        additional_permissions_json=options.get("additional-permissions-json"),
    )


def resolve_exec_command_request(
    inputs: ExecCommandInputs,
    *,
    bool_option: Callable[..., bool],
    int_option: Callable[..., int | None],
) -> ExecCommandRequest:
    command = inputs.command
    workdir = inputs.workdir
    if not workdir:
        implicit_workdir, normalized_command = _leading_cd_workdir(command)
        if implicit_workdir:
            workdir = implicit_workdir
            command = normalized_command
    return ExecCommandRequest(
        command=command,
        workdir=workdir,
        shell_override=inputs.shell_override,
        shell=inputs.shell,
        tty=inputs.tty,
        login=bool_option(inputs.login, default=True),
        yield_time_ms=int_option(inputs.yield_time_ms, default=10000),
        timeout_ms=int_option(inputs.timeout_ms),
        max_output_tokens=int_option(inputs.max_output_tokens),
        sandbox_permissions=_normalized_optional_text(inputs.sandbox_permissions),
        justification=_normalized_optional_text(inputs.justification),
        prefix_rule=_normalized_prefix_rule(inputs.prefix_rule),
        additional_permissions=_normalized_json_object_option(
            inputs.additional_permissions_json,
            field_name="additional_permissions",
        ),
    )


def _normalized_optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalized_prefix_rule(value: Any) -> tuple[str, ...] | None:
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        items = [str(part or "").strip() for part in value]
    else:
        items = [str(value or "").strip()] if value is not None else []
    normalized = tuple(item for item in items if item)
    return normalized or None


def _normalized_json_object_option(value: Any, *, field_name: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return dict(value)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {field_name}: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"invalid {field_name}: expected JSON object")
    return dict(parsed)


def _leading_cd_workdir(command: str) -> tuple[str | None, str]:
    text = str(command or "").strip()
    if not text:
        return None, text
    prefix, separator, remainder = text.partition("&&")
    if not separator:
        return None, text
    remainder = remainder.strip()
    if not remainder:
        return None, text
    try:
        tokens = shlex.split(prefix.strip(), posix=True)
    except ValueError:
        return None, text
    if not tokens or tokens[0] != "cd":
        return None, text
    operands = tokens[1:]
    if operands[:1] == ["--"]:
        operands = operands[1:]
    if len(operands) != 1:
        return None, text
    workdir = str(operands[0] or "").strip()
    if not workdir:
        return None, text
    return workdir, remainder
