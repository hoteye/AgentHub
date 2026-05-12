from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path


CLI_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CLI_ROOT.parent
AGENTHUB_MAIN = CLI_ROOT / "agent_cli" / "__main__.py"
CODEX_BIN = Path(shutil.which("codex") or "/home/lyc/.nvm/versions/node/v20.19.4/bin/codex")
CLAUDE_BIN = Path(shutil.which("claude") or "/usr/local/bin/claude")
DEFAULT_OUT_ROOT_PREFIX = "agenthub_file_write_ab_"
DEFAULT_TIMEOUT_SECONDS = 240


@dataclass(frozen=True)
class CaseSpec:
    name: str
    initial_files: tuple[tuple[str, str], ...]
    prompts: tuple[str, ...]
    expected_files: tuple[tuple[str, str], ...]


DEFAULT_CASES: tuple[CaseSpec, ...] = (
    CaseSpec(
        name="create_file_single_turn",
        initial_files=(),
        prompts=(
            "当前目录是空的。请创建 `hello.txt`，内容严格为 `hello from file_write ab`。完成后只回复 `done`。",
        ),
        expected_files=(("hello.txt", "hello from file_write ab"),),
    ),
    CaseSpec(
        name="read_then_overwrite_single_turn",
        initial_files=(("f.txt", "original\n"),),
        prompts=(
            "先读取 `f.txt` 的当前内容，再把它完整覆盖为 `rewritten once`。完成后只回复 `done`。",
        ),
        expected_files=(("f.txt", "rewritten once"),),
    ),
    CaseSpec(
        name="read_then_write_multi_turn",
        initial_files=(("f.txt", "original\n"),),
        prompts=(
            "读取 `f.txt` 并告诉我当前内容。",
            "现在把 `f.txt` 完整覆盖为 `rewritten after read`。完成后只回复 `done`。",
        ),
        expected_files=(("f.txt", "rewritten after read"),),
    ),
)


def add_claude_observability_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--claude-settings-file",
        default="",
        help="Optional Claude --settings JSON file path. This matches the benchmark-style Claude connection path.",
    )
    parser.add_argument(
        "--claude-base-url",
        default="",
        help="Optional Claude-compatible base URL override. If set without --claude-settings-file, a temporary Claude settings file is generated per run.",
    )
    parser.add_argument(
        "--claude-debug",
        nargs="?",
        const="all",
        default="",
        help="Enable Claude debug logging. Pass an optional filter such as api or tool.",
    )
    parser.add_argument(
        "--claude-include-hook-events",
        action="store_true",
        help="Include Claude hook events in stream-json output.",
    )
    parser.add_argument(
        "--claude-include-partial-messages",
        action="store_true",
        help="Include Claude partial assistant messages in stream-json output.",
    )
    return parser


def _selected_cases(case_filters: list[str]) -> list[CaseSpec]:
    if not case_filters:
        return list(DEFAULT_CASES)
    wanted = {text.strip() for text in case_filters if text.strip()}
    selected = [case for case in DEFAULT_CASES if case.name in wanted]
    if not selected:
        raise SystemExit(f"no matching cases for --case: {sorted(wanted)}")
    return selected
