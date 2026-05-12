"""Regression tests for grep_files flag parsing end-to-end.

Covers: parse_args flag table registration, slash_surface boolean keyword
normalization, and the combined normalize → parse_grep_files_args pipeline.
"""
from __future__ import annotations

import pytest

from cli.agent_cli.runtime_core import parse_args
from cli.agent_cli.runtime_core.tool_commands_params_runtime import parse_grep_files_args
from cli.agent_cli.slash_surface import normalize_command_text


def _parse(raw_arg_text: str) -> dict:
    normalized = normalize_command_text(f"/grep_files {raw_arg_text}")
    arg_text = normalized.split(" ", 1)[1] if " " in normalized else ""
    return parse_grep_files_args(parse_args, arg_text)


# ---------------------------------------------------------------------------
# parse_args flag table: --flag form (provider-generated commands)
# ---------------------------------------------------------------------------

def test_parse_args_output_mode_content() -> None:
    p = parse_grep_files_args(parse_args, "P0 --output-mode content")
    assert p["pattern"] == "P0"
    assert p["output_mode"] == "content"


def test_parse_args_output_mode_count() -> None:
    p = parse_grep_files_args(parse_args, "P0 --output-mode count")
    assert p["output_mode"] == "count"


def test_parse_args_line_numbers_flag() -> None:
    p = parse_grep_files_args(parse_args, "P0 --line-numbers")
    assert p["line_numbers"] is True
    assert p["pattern"] == "P0"


def test_parse_args_case_insensitive_flag() -> None:
    p = parse_grep_files_args(parse_args, "P0 --case-insensitive")
    assert p["case_insensitive"] is True
    assert p["pattern"] == "P0"


def test_parse_args_multiline_flag() -> None:
    p = parse_grep_files_args(parse_args, "P0 --multiline")
    assert p["multiline"] is True
    assert p["pattern"] == "P0"


def test_parse_args_context_flag() -> None:
    p = parse_grep_files_args(parse_args, "P0 --context 3")
    assert p["context"] == 3
    assert p["pattern"] == "P0"


def test_parse_args_after_before_flags() -> None:
    p = parse_grep_files_args(parse_args, "P0 --after 2 --before 1")
    assert p["after_context"] == 2
    assert p["before_context"] == 1


def test_parse_args_blocked_domains_web_search() -> None:
    from cli.agent_cli.runtime_core.tool_commands_params_runtime import parse_web_search_args
    p = parse_web_search_args(parse_args, "query --blocked-domains example.com,bad.org")
    assert p["blocked_domains"] == ["example.com", "bad.org"]


def test_parse_args_flags_do_not_pollute_pattern() -> None:
    p = parse_grep_files_args(
        parse_args,
        "mypattern --output-mode content --line-numbers --limit 5 --case-insensitive",
    )
    assert p["pattern"] == "mypattern"
    assert p["output_mode"] == "content"
    assert p["line_numbers"] is True
    assert p["limit"] == 5
    assert p["case_insensitive"] is True


# ---------------------------------------------------------------------------
# slash_surface normalization: bare keyword form (human-typed commands)
# ---------------------------------------------------------------------------

def test_normalize_bare_case_insensitive() -> None:
    p = _parse("P0 case-insensitive")
    assert p["pattern"] == "P0"
    assert p["case_insensitive"] is True


def test_normalize_bare_multiline() -> None:
    p = _parse("P0 multiline")
    assert p["pattern"] == "P0"
    assert p["multiline"] is True


def test_normalize_bare_line_numbers() -> None:
    p = _parse("P0 line-numbers")
    assert p["pattern"] == "P0"
    assert p["line_numbers"] is True


def test_normalize_bare_multiline_and_line_numbers() -> None:
    p = _parse("P0 multiline line-numbers")
    assert p["pattern"] == "P0"
    assert p["multiline"] is True
    assert p["line_numbers"] is True


def test_normalize_mixed_bare_and_flag() -> None:
    p = _parse("P0 case-insensitive --output-mode content --limit 5")
    assert p["pattern"] == "P0"
    assert p["case_insensitive"] is True
    assert p["output_mode"] == "content"
    assert p["limit"] == 5


def test_normalize_value_keyword_path_and_limit() -> None:
    p = _parse("P0 limit 10 path cli/")
    assert p["pattern"] == "P0"
    assert p["limit"] == 10
    assert p["path"] == "cli/"
