from __future__ import annotations

import shlex
import time
from typing import Any, Callable, Dict, List, Optional, Pattern

from cli.agent_cli.models import AgentIntent, PromptAttachment, ToolEvent, default_response_items
from cli.agent_cli.runtime_core.command_parsing import parse_args
from cli.agent_cli.providers import openai_planner_synthesis_runtime as synthesis_runtime_helpers
from cli.agent_cli.providers.planner_postprocessing import sanitize_final_answer_text


def chat_route_synthesis(
    planner: Any,
    *,
    route_name: str,
    route_config: Any,
    timeout: int | None,
    user_text: str,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    attachments: Optional[List[PromptAttachment]] = None,
    call_with_provider_retries_fn: Callable[[Callable[[], Any]], Any],
    timeline_debug_enabled_fn: Callable[[], bool],
    log_timeline_fn: Callable[..., Any],
    json_ready_fn: Callable[[Any], Any],
) -> AgentIntent:
    synthesis_started_at = time.perf_counter()
    kwargs = synthesis_runtime_helpers.chat_route_request_kwargs(
        model=route_config.model,
        messages=planner._synthesis_messages(
            user_text=user_text,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            attachments=attachments,
        ),
        extra_body=planner._chat_route_extra_body(route_config),
    )
    if timeline_debug_enabled_fn():
        log_timeline_fn(
            "openai_planner.chat_route_synthesis.request_raw",
            route_name=route_name,
            provider_name=str(route_config.provider_name or ""),
            base_url=str(route_config.base_url or ""),
            request=json_ready_fn(kwargs),
        )
    request_client = planner._route_request_client(route_name, route_config, timeout)
    response = call_with_provider_retries_fn(lambda: request_client.chat.completions.create(**kwargs))
    if timeline_debug_enabled_fn():
        log_timeline_fn(
            "openai_planner.chat_route_synthesis.response_raw",
            route_name=route_name,
            provider_name=str(route_config.provider_name or ""),
            base_url=str(route_config.base_url or ""),
            response=json_ready_fn(response),
        )
    choices = list(getattr(response, "choices", []) or [])
    message = getattr(choices[0], "message", None) if choices else None
    assistant_text = synthesis_runtime_helpers.chat_route_assistant_text(
        response=response,
        chat_message_text=planner._chat_message_text(getattr(message, "content", "") if message is not None else ""),
        executed_events=executed_events,
    )
    response_items = list(default_response_items(assistant_text=assistant_text))
    return AgentIntent(
        assistant_text=assistant_text,
        response_items=response_items,
        command_text=None,
        status_hint="tool",
        tool_events=list(executed_events),
        turn_events=planner._compose_turn_events(
            assistant_text=assistant_text,
            response_items=response_items,
            executed_item_events=list(executed_item_events or []),
        ),
        timings={
            "synthesis_model_ms": int((time.perf_counter() - synthesis_started_at) * 1000),
            "synthesis_rounds": 1,
        },
    )


def collect_stream_text(
    *,
    kwargs: Dict[str, Any],
    client: Any,
    call_with_provider_retries_fn: Callable[[Callable[[], Any]], Any],
    attach_responses_503_risks_fn: Callable[[Exception, Dict[str, Any]], None],
    log_responses_request_fn: Callable[[str, Dict[str, Any]], None],
    log_responses_response_fn: Callable[[str, Any], None],
) -> str:
    collected_text, _ = collect_stream_response(
        kwargs=kwargs,
        client=client,
        call_with_provider_retries_fn=call_with_provider_retries_fn,
        attach_responses_503_risks_fn=attach_responses_503_risks_fn,
        log_responses_request_fn=log_responses_request_fn,
        log_responses_response_fn=log_responses_response_fn,
    )
    return collected_text


def collect_stream_response(
    *,
    kwargs: Dict[str, Any],
    client: Any,
    call_with_provider_retries_fn: Callable[[Callable[[], Any]], Any],
    attach_responses_503_risks_fn: Callable[[Exception, Dict[str, Any]], None],
    log_responses_request_fn: Callable[[str, Dict[str, Any]], None],
    log_responses_response_fn: Callable[[str, Any], None],
) -> tuple[str, Any | None]:
    request_kwargs = dict(kwargs)
    request_kwargs["stream"] = True
    log_responses_request_fn("openai_planner.collect_stream_text", request_kwargs)
    try:
        stream = call_with_provider_retries_fn(lambda: client.responses.create(**request_kwargs))
    except Exception as exc:
        attach_responses_503_risks_fn(exc, request_kwargs)
        raise
    if hasattr(stream, "output"):
        log_responses_response_fn("openai_planner.collect_stream_text", stream)
        return str(getattr(stream, "output_text", "") or "").strip(), stream
    collected_text = synthesis_runtime_helpers.stream_text_from_events(stream)
    final_response = None
    get_final_response = getattr(stream, "get_final_response", None)
    if callable(get_final_response):
        try:
            final_response = get_final_response()
            log_responses_response_fn("openai_planner.collect_stream_text", final_response)
        except Exception:
            pass
    return collected_text, final_response


def synthesis_messages(
    *,
    user_text: str,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    attachments: Optional[List[PromptAttachment]] = None,
    attachment_payloads_fn: Callable[[Optional[List[PromptAttachment]]], List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    return synthesis_runtime_helpers.synthesis_messages(
        user_text=user_text,
        executed_events=executed_events,
        executed_item_events=executed_item_events,
        attachments=attachments,
        attachment_payloads_fn=attachment_payloads_fn,
    )


def normalize_command_text(
    command_text: Optional[str],
    *,
    followup_command_pattern: Pattern[str],
    normalize_shell_command_fn: Callable[[str], str],
) -> Optional[str]:
    if command_text is None:
        return None
    compact = " ".join(str(command_text).strip().split())
    if not compact:
        return None
    followup_match = followup_command_pattern.search(compact)
    if followup_match:
        compact = compact[: followup_match.start()].strip()
    if not compact:
        return None
    if compact.lower().startswith("/shell "):
        shell_command = normalize_shell_command_fn(compact[len("/shell ") :])
        return f"/shell {shell_command}" if shell_command else None
    if compact.lower().startswith("/exec_command"):
        arg_text = compact[len("/exec_command") :].strip()
        positionals, options = parse_args(arg_text)
        raw_command = str(options.get("cmd") or " ".join(positionals)).strip()
        normalized_command = normalize_shell_command_fn(raw_command)
        if not normalized_command:
            return None
        rebuilt = f"/exec_command {shlex.quote(normalized_command)}"
        workdir = str(options.get("workdir") or "").strip()
        if workdir:
            rebuilt += f" --workdir {shlex.quote(workdir)}"
        shell = str(options.get("shell") or "").strip()
        if shell:
            rebuilt += f" --shell {shlex.quote(shell)}"
        if options.get("tty"):
            rebuilt += " --tty"
        login = str(options.get("login") or "").strip()
        if login:
            rebuilt += f" --login {shlex.quote(login)}"
        yield_time_ms = str(options.get("yield-time-ms") or "").strip()
        if yield_time_ms:
            rebuilt += f" --yield-time-ms {shlex.quote(yield_time_ms)}"
        max_output_tokens = str(options.get("max-output-tokens") or "").strip()
        if max_output_tokens:
            rebuilt += f" --max-output-tokens {shlex.quote(max_output_tokens)}"
        sandbox_permissions = str(options.get("sandbox-permissions") or "").strip()
        if sandbox_permissions:
            rebuilt += f" --sandbox-permissions {shlex.quote(sandbox_permissions)}"
        justification = str(options.get("justification") or "").strip()
        if justification:
            rebuilt += f" --justification {shlex.quote(justification)}"
        prefix_rule = str(options.get("prefix-rule") or "").strip()
        if prefix_rule:
            rebuilt += f" --prefix-rule {shlex.quote(prefix_rule)}"
        additional_permissions_json = str(options.get("additional-permissions-json") or "").strip()
        if additional_permissions_json:
            rebuilt += f" --additional-permissions-json {shlex.quote(additional_permissions_json)}"
        return rebuilt
    return compact if compact.startswith("/") else None


def extract_command_text(
    raw_text: str,
    *,
    command_pattern: Pattern[str],
    normalize_command_text_fn: Callable[[Optional[str]], Optional[str]],
) -> Optional[str]:
    match = command_pattern.search(str(raw_text or ""))
    if not match:
        return None
    return normalize_command_text_fn(match.group(1))


def intent_from_raw_text(
    raw_text: str,
    *,
    allow_command_pattern_fallback: bool,
    extract_json_payload_fn: Callable[[str], Optional[Dict[str, Any]]],
    normalize_command_text_fn: Callable[[Optional[str]], Optional[str]],
    extract_command_text_fn: Callable[[str], Optional[str]],
    command_pattern: Pattern[str],
) -> AgentIntent:
    payload = extract_json_payload_fn(raw_text)
    if payload is not None:
        command_text = normalize_command_text_fn(payload.get("command_text"))
        assistant_text = sanitize_final_answer_text(str(payload.get("assistant_text") or "").strip())
        if not assistant_text and not command_text:
            assistant_text = "模型未返回内容。"
        status_hint = str(payload.get("status_hint") or ("tool" if command_text else "llm")).strip() or "llm"
        return AgentIntent(
            assistant_text=assistant_text,
            response_items=default_response_items(assistant_text=assistant_text),
            command_text=command_text,
            status_hint=status_hint,
        )

    assistant_text = sanitize_final_answer_text(str(raw_text or "").strip())
    if not allow_command_pattern_fallback:
        final_text = assistant_text or "模型未返回内容。"
        return AgentIntent(
            assistant_text=final_text,
            response_items=default_response_items(assistant_text=final_text),
            command_text=None,
            status_hint="llm",
        )
    command_text = extract_command_text_fn(raw_text)
    if command_text:
        assistant_text = command_pattern.sub("", assistant_text).strip(" \r\n\t:：")
        return AgentIntent(
            assistant_text=assistant_text,
            response_items=default_response_items(assistant_text=assistant_text),
            command_text=command_text,
            status_hint="tool",
        )
    final_text = assistant_text or "模型未返回内容。"
    return AgentIntent(
        assistant_text=final_text,
        response_items=default_response_items(assistant_text=final_text),
        command_text=None,
        status_hint="llm",
    )
