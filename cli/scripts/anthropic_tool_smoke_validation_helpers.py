from __future__ import annotations

from typing import Any, Callable

try:
    from cli.scripts.anthropic_tool_smoke_payload_helpers import (
        _assistant_text,
        _canonical_tool_names,
        _projected_tool_names,
        _temp_path,
        _tool_event,
        _turn_item_types,
        _validation_result,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from anthropic_tool_smoke_payload_helpers import (  # type: ignore[no-redef]
        _assistant_text,
        _canonical_tool_names,
        _projected_tool_names,
        _temp_path,
        _tool_event,
        _turn_item_types,
        _validation_result,
    )


KNOWN_ASK_USER_DEFAULT_MODE_ERROR = "request_user_input is unavailable in Default mode"
KNOWN_ASK_USER_HEADLESS_CANCEL_ERROR = "request_user_input was cancelled before receiving a response"

ValidatorFn = Callable[[dict[str, Any]], dict[str, Any]]


def _validate_bash_pwd(run: dict[str, Any]) -> dict[str, Any]:
    payload = dict(run.get("payload") or {})
    canonical = _canonical_tool_names(payload)
    projected = _projected_tool_names(payload)
    assistant = _assistant_text(payload)
    expected = str(run.get("cwd") or "")
    errors: list[str] = []
    if "exec_command" not in canonical:
        errors.append("missing canonical exec_command event")
    if "Bash" not in projected:
        errors.append("missing projected Bash tool name")
    if assistant != expected:
        errors.append(f"assistant_text={assistant!r} expected {expected!r}")
    if errors:
        return _validation_result("failed", "Bash pwd smoke failed", errors)
    return _validation_result("passed", "Bash executed and returned the workspace path", [])


def _validate_write_stdin_background(run: dict[str, Any]) -> dict[str, Any]:
    payload = dict(run.get("payload") or {})
    canonical = _canonical_tool_names(payload)
    projected = _projected_tool_names(payload)
    assistant = _assistant_text(payload)
    errors: list[str] = []
    if "exec_command" not in canonical:
        errors.append("missing canonical exec_command event")
    if "write_stdin" not in canonical:
        errors.append("missing canonical write_stdin event")
    if "Bash" not in projected:
        errors.append("missing projected Bash tool name")
    if "write_stdin" not in projected:
        errors.append("missing projected write_stdin tool name")
    if assistant != "START_LINE\nEND_LINE":
        errors.append(f"assistant_text={assistant!r} expected START_LINE/END_LINE")
    tool_event = _tool_event(payload, "write_stdin") or {}
    session_id = str((tool_event.get("payload") or {}).get("session_id") or "")
    if not session_id:
        errors.append("write_stdin payload did not include a session_id")
    if errors:
        return _validation_result("failed", "Bash background + write_stdin smoke failed", errors)
    return _validation_result(
        "passed",
        "Bash background execution was continued through write_stdin",
        [],
        {"session_id": session_id},
    )


def _validate_glob_find_file(run: dict[str, Any]) -> dict[str, Any]:
    payload = dict(run.get("payload") or {})
    canonical = _canonical_tool_names(payload)
    projected = _projected_tool_names(payload)
    assistant = _assistant_text(payload)
    errors: list[str] = []
    if "glob_files" not in canonical:
        errors.append("missing canonical glob_files event")
    if "Glob" not in projected:
        errors.append("missing projected Glob tool name")
    if "subdir/notes.txt" not in assistant:
        errors.append(f"assistant_text={assistant!r} did not contain subdir/notes.txt")
    if errors:
        return _validation_result("failed", "Glob file-discovery smoke failed", errors)
    return _validation_result("passed", "Glob located the target file without falling back to shell", [])


def _validate_grep_find_text(run: dict[str, Any]) -> dict[str, Any]:
    payload = dict(run.get("payload") or {})
    canonical = _canonical_tool_names(payload)
    projected = _projected_tool_names(payload)
    assistant = _assistant_text(payload)
    errors: list[str] = []
    if "grep_files" not in canonical:
        errors.append("missing canonical grep_files event")
    if "Grep" not in projected:
        errors.append("missing projected Grep tool name")
    if "sample.txt" not in assistant:
        errors.append(f"assistant_text={assistant!r} did not contain sample.txt")
    if errors:
        return _validation_result("failed", "Grep content-search smoke failed", errors)
    return _validation_result("passed", "Grep found the sentinel text through the structured file query tool", [])


def _validate_read_file(run: dict[str, Any]) -> dict[str, Any]:
    payload = dict(run.get("payload") or {})
    canonical = _canonical_tool_names(payload)
    projected = _projected_tool_names(payload)
    assistant = _assistant_text(payload)
    errors: list[str] = []
    if "read_file" not in canonical:
        errors.append("missing canonical read_file event")
    if "Read" not in projected:
        errors.append("missing projected Read tool name")
    if assistant != "alpha\nBETA_NEEDLE":
        errors.append(f"assistant_text={assistant!r} did not match the requested file slice")
    if errors:
        return _validation_result("failed", "Read smoke failed", errors)
    return _validation_result("passed", "Read returned the requested file slice", [])


def _validate_write_file(run: dict[str, Any]) -> dict[str, Any]:
    payload = dict(run.get("payload") or {})
    canonical = _canonical_tool_names(payload)
    projected = _projected_tool_names(payload)
    assistant = _assistant_text(payload)
    target = _temp_path(run, "written_demo.txt")
    errors: list[str] = []
    if "apply_patch" not in canonical and "Write" not in canonical:
        errors.append("missing file-write tool event")
    if "Write" not in projected:
        errors.append("missing projected Write tool name")
    if "written_demo.txt" not in assistant:
        errors.append(f"assistant_text={assistant!r} did not mention written_demo.txt")
    if not target.exists():
        errors.append(f"expected file was not created: {target}")
    else:
        content = target.read_text(encoding="utf-8")
        if content != "line-one\nline-two\n":
            errors.append(f"written_demo.txt content mismatch: {content!r}")
    if errors:
        return _validation_result("failed", "Write smoke failed", errors)
    return _validation_result("passed", "Write created the expected file content", [])


def _validate_edit_file(run: dict[str, Any]) -> dict[str, Any]:
    payload = dict(run.get("payload") or {})
    canonical = _canonical_tool_names(payload)
    projected = _projected_tool_names(payload)
    assistant = _assistant_text(payload)
    target = _temp_path(run, "edit_target.txt")
    errors: list[str] = []
    if "read_file" not in canonical:
        errors.append("Edit flow did not read the file first")
    if "apply_patch" not in canonical and "Edit" not in canonical:
        errors.append("missing file-edit tool event")
    if "Edit" not in projected:
        errors.append("missing projected Edit tool name")
    if assistant != "NEW_TOKEN":
        errors.append(f"assistant_text={assistant!r} expected NEW_TOKEN")
    if not target.exists():
        errors.append(f"edited file missing: {target}")
    else:
        content = target.read_text(encoding="utf-8")
        if "NEW_TOKEN" not in content or "OLD_TOKEN" in content:
            errors.append(f"edit_target.txt content mismatch: {content!r}")
    if errors:
        return _validation_result("failed", "Edit smoke failed", errors)
    return _validation_result("passed", "Edit replaced the target token after reading the file", [])


def _validate_update_plan_then_read(run: dict[str, Any]) -> dict[str, Any]:
    payload = dict(run.get("payload") or {})
    canonical = _canonical_tool_names(payload)
    assistant = _assistant_text(payload)
    turn_types = _turn_item_types(payload)
    errors: list[str] = []
    if "update_plan" not in canonical:
        errors.append("missing update_plan tool event")
    if "read_file" not in canonical:
        errors.append("missing read_file tool event")
    if "todo_list" not in turn_types:
        errors.append("turn events did not emit a todo_list item")
    if assistant != "alpha":
        errors.append(f"assistant_text={assistant!r} expected alpha")
    if errors:
        return _validation_result("failed", "update_plan smoke failed", errors)
    return _validation_result("passed", "update_plan emitted a todo list and the turn continued with Read", [])


def _validate_ask_user_question_default_mode(run: dict[str, Any]) -> dict[str, Any]:
    payload = dict(run.get("payload") or {})
    canonical = _canonical_tool_names(payload)
    projected = _projected_tool_names(payload)
    tool_event = _tool_event(payload, "request_user_input") or {}
    tool_payload = dict(tool_event.get("payload") or {})
    tool_error = str(tool_payload.get("error") or "").strip()
    errors: list[str] = []
    if "request_user_input" not in canonical:
        errors.append("missing canonical request_user_input event")
    if "AskUserQuestion" not in projected:
        errors.append("missing projected AskUserQuestion tool name")
    if errors:
        return _validation_result("failed", "AskUserQuestion smoke failed before the runtime-limit check", errors)
    if tool_error == KNOWN_ASK_USER_DEFAULT_MODE_ERROR:
        return _validation_result(
            "expected_blocked",
            "AskUserQuestion was selected correctly and then blocked by Default-mode runtime policy",
            [KNOWN_ASK_USER_DEFAULT_MODE_ERROR],
        )
    if tool_error == KNOWN_ASK_USER_HEADLESS_CANCEL_ERROR:
        return _validation_result(
            "expected_blocked",
            "AskUserQuestion was selected correctly; one-shot headless cancelled because no user response bridge was attached",
            [KNOWN_ASK_USER_HEADLESS_CANCEL_ERROR],
        )
    if bool(tool_event.get("ok")):
        return _validation_result(
            "passed",
            "AskUserQuestion executed successfully; the previous Default-mode limitation no longer reproduced",
            ["request_user_input succeeded in the current runtime configuration"],
        )
    return _validation_result(
        "failed",
        "AskUserQuestion failed with an unexpected runtime result",
        [f"unexpected error: {tool_error or '-'}"],
    )


def _validate_web_search(run: dict[str, Any]) -> dict[str, Any]:
    payload = dict(run.get("payload") or {})
    canonical = _canonical_tool_names(payload)
    projected = _projected_tool_names(payload)
    assistant = _assistant_text(payload).lower()
    tool_event = _tool_event(payload, "web_search") or {}
    tool_payload = dict(tool_event.get("payload") or {})
    route = dict(tool_payload.get("web_search_route") or {})
    errors: list[str] = []
    if "web_search" not in canonical:
        errors.append("missing canonical web_search event")
    if "WebSearch" not in projected:
        errors.append("missing projected WebSearch tool name")
    if "python.org" not in assistant:
        errors.append(f"assistant_text={assistant!r} did not mention python.org")
    if str(tool_payload.get("engine") or "").strip() != "anthropic_native_web_search":
        errors.append(f"engine={tool_payload.get('engine')!r} expected anthropic_native_web_search")
    if str(route.get("selected_backend_id") or "").strip() != "provider_native_anthropic_web_search":
        errors.append(f"selected_backend_id={route.get('selected_backend_id')!r} expected provider_native_anthropic_web_search")
    if errors:
        return _validation_result("failed", "WebSearch smoke failed", errors)
    return _validation_result("passed", "WebSearch used Anthropic native web search", [])


def _validate_web_fetch(run: dict[str, Any]) -> dict[str, Any]:
    payload = dict(run.get("payload") or {})
    canonical = _canonical_tool_names(payload)
    projected = _projected_tool_names(payload)
    assistant = _assistant_text(payload)
    errors: list[str] = []
    if "web_fetch" not in canonical:
        errors.append("missing canonical web_fetch event")
    if "WebFetch" not in projected:
        errors.append("missing projected WebFetch tool name")
    if "Example Domain" not in assistant:
        errors.append(f"assistant_text={assistant!r} did not mention Example Domain")
    if errors:
        return _validation_result("failed", "WebFetch smoke failed", errors)
    return _validation_result("passed", "WebFetch fetched and summarized the concrete URL", [])


def _validate_agent_one_shot(run: dict[str, Any]) -> dict[str, Any]:
    payload = dict(run.get("payload") or {})
    canonical = _canonical_tool_names(payload)
    projected = _projected_tool_names(payload)
    assistant = _assistant_text(payload)
    tool_event = _tool_event(payload, "spawn_agent") or {}
    tool_payload = dict(tool_event.get("payload") or {})
    result_contract = dict(tool_payload.get("result_contract") or {})
    errors: list[str] = []
    if "spawn_agent" not in canonical:
        errors.append("missing canonical spawn_agent event")
    if "Agent" not in projected:
        errors.append("missing projected Agent tool name")
    if str(tool_payload.get("function_call_name") or "").strip() != "Agent":
        errors.append("spawn_agent payload did not preserve the projected Agent tool name")
    if not bool(tool_event.get("ok")):
        errors.append("spawn_agent tool event was not successful")
    if str(result_contract.get("status") or "").strip() != "completed":
        errors.append(f"result_contract.status={result_contract.get('status')!r} expected 'completed'")
    if len(assistant) < 20:
        errors.append("assistant_text was unexpectedly short for delegated output")
    if errors:
        return _validation_result("failed", "Agent one-shot delegation smoke failed", errors)
    return _validation_result("passed", "Agent launched a bounded read-only delegated child", [])


def _validate_send_message_two_turn(run: dict[str, Any]) -> dict[str, Any]:
    turns = dict(run.get("turns") or {})
    first = dict(turns.get("turn1") or {})
    second = dict(turns.get("turn2") or {})
    first_payload = dict(first.get("payload") or {})
    second_payload = dict(second.get("payload") or {})
    first_event = _tool_event(first_payload, "spawn_agent") or {}
    second_event = _tool_event(second_payload, "send_input") or {}
    first_agent_id = str((first_event.get("payload") or {}).get("agent_id") or "").strip()
    second_agent_id = str((second_event.get("payload") or {}).get("agent_id") or "").strip()
    errors: list[str] = []
    if "spawn_agent" not in _canonical_tool_names(first_payload):
        errors.append("turn1 missing canonical spawn_agent event")
    if "Agent" not in _projected_tool_names(first_payload):
        errors.append("turn1 missing projected Agent tool name")
    if "send_input" not in _canonical_tool_names(second_payload):
        errors.append("turn2 missing canonical send_input event")
    if "SendMessage" not in _projected_tool_names(second_payload):
        errors.append("turn2 missing projected SendMessage tool name")
    if not first_agent_id or not second_agent_id:
        errors.append("delegated agent id was missing from one of the turns")
    elif first_agent_id != second_agent_id:
        errors.append(f"agent_id changed across turns: {first_agent_id!r} -> {second_agent_id!r}")
    if str((first_event.get("payload") or {}).get("delegation_mode") or "").strip() != "background":
        errors.append("turn1 did not report background delegation mode")
    if not _assistant_text(second_payload):
        errors.append("turn2 assistant_text was empty")
    if errors:
        return _validation_result("failed", "SendMessage multi-turn smoke failed", errors)
    return _validation_result("passed", "SendMessage resumed the existing delegated child through the same session", [])
