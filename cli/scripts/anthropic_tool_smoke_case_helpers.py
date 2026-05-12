from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

try:
    from cli.scripts.anthropic_tool_smoke_validation_helpers import (
        KNOWN_ASK_USER_DEFAULT_MODE_ERROR,
        KNOWN_ASK_USER_HEADLESS_CANCEL_ERROR,
        ValidatorFn,
        _validate_agent_one_shot,
        _validate_ask_user_question_default_mode,
        _validate_bash_pwd,
        _validate_edit_file,
        _validate_glob_find_file,
        _validate_grep_find_text,
        _validate_read_file,
        _validate_send_message_two_turn,
        _validate_update_plan_then_read,
        _validate_web_fetch,
        _validate_web_search,
        _validate_write_file,
        _validate_write_stdin_background,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from anthropic_tool_smoke_validation_helpers import (  # type: ignore[no-redef]
        KNOWN_ASK_USER_DEFAULT_MODE_ERROR,
        KNOWN_ASK_USER_HEADLESS_CANCEL_ERROR,
        ValidatorFn,
        _validate_agent_one_shot,
        _validate_ask_user_question_default_mode,
        _validate_bash_pwd,
        _validate_edit_file,
        _validate_glob_find_file,
        _validate_grep_find_text,
        _validate_read_file,
        _validate_send_message_two_turn,
        _validate_update_plan_then_read,
        _validate_web_fetch,
        _validate_web_search,
        _validate_write_file,
        _validate_write_stdin_background,
    )


@dataclass(frozen=True)
class CaseDefinition:
    case_id: str
    title: str
    mode: str
    workspace: str
    prompt: str = ""
    prompts: tuple[str, ...] = ()
    web_enabled: bool = False
    validator: ValidatorFn | None = None


CASE_DEFINITIONS: tuple[CaseDefinition, ...] = (
    CaseDefinition(
        case_id="bash_pwd",
        title="Bash runs pwd in the temp workspace",
        mode="single",
        workspace="temp",
        prompt="Use the Bash tool to run 'pwd' in the current workspace, then reply with only the absolute path that Bash returned.",
        validator=_validate_bash_pwd,
    ),
    CaseDefinition(
        case_id="write_stdin_background",
        title="Bash background execution continues through write_stdin",
        mode="single",
        workspace="temp",
        prompt=(
            "Use Bash with run_in_background=true to start a command that prints START_LINE, sleeps for 1 second, "
            "and then prints END_LINE. Then use write_stdin to wait for that same session to finish. "
            "Reply with exactly those two lines in order, and do not use Bash a second time."
        ),
        validator=_validate_write_stdin_background,
    ),
    CaseDefinition(
        case_id="glob_find_file",
        title="Glob finds a known file path",
        mode="single",
        workspace="temp",
        prompt="Use the Glob tool, not Grep or Bash, to find the file named notes.txt anywhere under the current workspace. Reply with only the relative path.",
        validator=_validate_glob_find_file,
    ),
    CaseDefinition(
        case_id="grep_find_text",
        title="Grep locates a known sentinel string",
        mode="single",
        workspace="temp",
        prompt="Use the Grep tool, not Glob or Bash, to locate the text BETA_NEEDLE in the current workspace. Reply with only the matching relative file path.",
        validator=_validate_grep_find_text,
    ),
    CaseDefinition(
        case_id="read_file",
        title="Read returns a bounded file slice",
        mode="single",
        workspace="temp",
        prompt="Use the Read tool, not Bash, to read the first 2 lines of sample.txt in the current workspace. Reply with exactly those two lines.",
        validator=_validate_read_file,
    ),
    CaseDefinition(
        case_id="write_file",
        title="Write creates a new file with exact content",
        mode="single",
        workspace="temp",
        prompt="Use the Write tool to create a new file named written_demo.txt with exactly this content: line-one on the first line and line-two on the second line. Then reply with only written_demo.txt.",
        validator=_validate_write_file,
    ),
    CaseDefinition(
        case_id="edit_file",
        title="Edit replaces a token after reading the file",
        mode="single",
        workspace="temp",
        prompt="First use Read to inspect edit_target.txt. Then use the Edit tool to replace OLD_TOKEN with NEW_TOKEN in that file. Reply with only NEW_TOKEN.",
        validator=_validate_edit_file,
    ),
    CaseDefinition(
        case_id="update_plan_then_read",
        title="update_plan emits todo_list and the turn continues",
        mode="single",
        workspace="temp",
        prompt=(
            "Before any other work, call update_plan with exactly two steps: step 1 is 'Read sample.txt' marked in_progress, "
            "step 2 is 'Reply with first line' marked pending. Then use Read on sample.txt and reply with only the first line."
        ),
        validator=_validate_update_plan_then_read,
    ),
    CaseDefinition(
        case_id="ask_user_question_default_mode",
        title="AskUserQuestion reaches the interactive headless boundary in Default mode",
        mode="single",
        workspace="temp",
        prompt="Do not assume a choice. Use AskUserQuestion to ask the user whether they prefer Option A or Option B for a demo decision, and do not provide any other substantive answer.",
        validator=_validate_ask_user_question_default_mode,
    ),
    CaseDefinition(
        case_id="web_search",
        title="WebSearch uses the native Anthropic web-search path",
        mode="single",
        workspace="temp",
        prompt="Use the WebSearch tool, not WebFetch, to search the web for 'Python official website'. Reply with only the official domain.",
        web_enabled=True,
        validator=_validate_web_search,
    ),
    CaseDefinition(
        case_id="web_fetch",
        title="WebFetch reads a concrete public URL",
        mode="single",
        workspace="temp",
        prompt="Use WebFetch, not Bash, to fetch https://example.com and reply with only the page H1 text.",
        web_enabled=True,
        validator=_validate_web_fetch,
    ),
    CaseDefinition(
        case_id="agent_one_shot",
        title="Agent launches a bounded read-only child",
        mode="single",
        workspace="repo",
        prompt="Use Agent once for one bounded read-only side task. Have the child inspect the current repo root and return the two most relevant top-level entries for understanding this workspace. Do not edit files. Return the child findings in Chinese.",
        validator=_validate_agent_one_shot,
    ),
    CaseDefinition(
        case_id="send_message_two_turn",
        title="SendMessage continues an existing delegated child in serve mode",
        mode="serve",
        workspace="repo",
        prompts=(
            "Use Agent with run_in_background=true for a read-only repo scan. Do not poll. Continue normally and rely on the completion notification before consuming the result.",
            "Continue the existing delegated child with SendMessage. Ask it to narrow the prior findings down to the single most relevant path and one sentence of rationale.",
        ),
        validator=_validate_send_message_two_turn,
    ),
)


CASE_BY_ID = {case.case_id: case for case in CASE_DEFINITIONS}


def _populate_temp_workspace(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "subdir").mkdir(exist_ok=True)
    (path / "sample.txt").write_text("alpha\nBETA_NEEDLE\ngamma\n", encoding="utf-8")
    (path / "subdir" / "notes.txt").write_text("first\nsecond\nthird\n", encoding="utf-8")
    (path / "edit_target.txt").write_text("before\nOLD_TOKEN\nafter\n", encoding="utf-8")
    (path / "delegate_a.txt").write_text("CODE_A_731\n", encoding="utf-8")
    (path / "delegate_b.txt").write_text("CODE_B_842\n", encoding="utf-8")


def _selected_cases(requested: Sequence[str] | None) -> list[CaseDefinition]:
    if not requested:
        return list(CASE_DEFINITIONS)
    selected: list[CaseDefinition] = []
    unknown: list[str] = []
    for case_id in requested:
        case = CASE_BY_ID.get(str(case_id))
        if case is None:
            unknown.append(str(case_id))
            continue
        selected.append(case)
    if unknown:
        raise SystemExit(f"unknown case ids: {', '.join(unknown)}")
    return selected
