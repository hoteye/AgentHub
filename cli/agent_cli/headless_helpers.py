from __future__ import annotations

import argparse
from collections.abc import Callable

from cli.agent_cli.runtime_permission_mode import PERMISSION_MODES
from cli.agent_cli.runtime_policy import RuntimePolicy

HEADLESS_OUTPUT_FORMAT_TEXT = "text"
HEADLESS_OUTPUT_FORMAT_JSON = "json"
HEADLESS_OUTPUT_FORMAT_STREAM_JSON = "stream-json"
HEADLESS_OUTPUT_FORMAT_CODEX_JSONL = "codex-jsonl"
HEADLESS_OUTPUT_FORMAT_CHOICES = (
    HEADLESS_OUTPUT_FORMAT_TEXT,
    HEADLESS_OUTPUT_FORMAT_JSON,
    HEADLESS_OUTPUT_FORMAT_STREAM_JSON,
    HEADLESS_OUTPUT_FORMAT_CODEX_JSONL,
)


def build_parser(
    *, theme_ids_provider: Callable[[], tuple[str, ...] | list[str]]
) -> argparse.ArgumentParser:
    theme_help = ", ".join(f"`{theme_id}`" for theme_id in theme_ids_provider())
    parser = argparse.ArgumentParser(
        prog="agent_cli",
        description="Reference-like CLI for AgentHub local automation and provider-backed workflows.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="run without the Textual TUI",
    )
    parser.add_argument(
        "--prompt",
        help="single prompt or slash command to execute in headless mode",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="read one prompt from stdin in headless mode",
    )
    parser.add_argument(
        "--output-format",
        choices=HEADLESS_OUTPUT_FORMAT_CHOICES,
        default=None,
        help="headless output contract (`text`, `json`, `stream-json`, or `codex-jsonl`)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="compatibility alias for `--output-format json`",
    )
    parser.add_argument(
        "--jsonl",
        action="store_true",
        help="compatibility alias for `--output-format stream-json`",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="run a long-lived headless stdio server using NDJSON requests",
    )
    parser.add_argument(
        "--engine",
        choices=("agenthub_python", "python", "codex_sidecar", "codex", "openai"),
        default=None,
        help="select the runtime engine (`agenthub_python` or `codex_sidecar`)",
    )
    parser.add_argument(
        "--provider-status",
        action="store_true",
        help="shortcut for running /provider verbose in headless mode",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="store_true",
        help="show the AgentHub CLI version and exit",
    )
    parser.add_argument(
        "--resume",
        metavar="THREAD_ID",
        help="resume an existing thread before executing the headless prompt",
    )
    parser.add_argument(
        "--resume-path",
        metavar="ROLLOUT_PATH",
        help="resume an existing thread from a rollout path before executing the headless prompt",
    )
    parser.add_argument(
        "--resume-last",
        action="store_true",
        help="resume the last active persisted thread before executing the prompt",
    )
    parser.add_argument(
        "--permission-mode",
        choices=PERMISSION_MODES,
        help=(
            "set high-level runtime permission profile "
            "(`default`, `plan`, `acceptEdits`, `dontAsk`, `bypassPermissions`; "
            "aliases: `accept-edits`, `dont-ask`, `bypass-permissions`)"
        ),
    )
    parser.add_argument(
        "--approval-policy",
        choices=("never", "on-request", "on-failure", "untrusted"),
        help="set the runtime approval policy for this headless session",
    )
    parser.add_argument(
        "--sandbox-mode",
        choices=("read-only", "workspace-write", "danger-full-access"),
        help="set the runtime sandbox mode label for this headless session",
    )
    parser.add_argument(
        "--web-search-mode",
        choices=("disabled", "cached", "live"),
        help="set the runtime web search mode for this headless session",
    )
    parser.add_argument(
        "--network-access",
        choices=("enabled", "disabled"),
        help="set whether runtime network access is enabled for this headless session",
    )
    parser.add_argument(
        "--lang",
        metavar="LOCALE",
        help="set the TUI language (`en`, `zh-CN`, `ja`, `fr`, or `auto`)",
    )
    parser.add_argument(
        "--theme",
        metavar="THEME_ID",
        help=f"set the TUI theme ({theme_help})",
    )
    parser.add_argument(
        "-d",
        "--debug",
        nargs="?",
        const="*",
        metavar="FILTER",
        help=(
            "enable benchmark-style debug logging with optional category filter "
            "(for example `api,tool` or `!api`)"
        ),
    )
    parser.add_argument(
        "--debug-file",
        metavar="PATH",
        help="write benchmark-style debug logs to a file (implicitly enables --debug)",
    )
    return parser


def has_headless_request(args: argparse.Namespace) -> bool:
    output_format = str(getattr(args, "output_format", "") or "").strip()
    return bool(
        args.headless
        or args.prompt is not None
        or args.stdin
        or bool(output_format)
        or args.json
        or args.jsonl
        or args.serve
        or args.provider_status
    )


def runtime_policy_from_args(args: argparse.Namespace) -> RuntimePolicy:
    return RuntimePolicy.normalized(
        permission_mode=getattr(args, "permission_mode", None),
        approval_policy=getattr(args, "approval_policy", None),
        sandbox_mode=getattr(args, "sandbox_mode", None),
        web_search_mode=getattr(args, "web_search_mode", None),
        network_access_enabled=getattr(args, "network_access", None),
    )


def headless_output_format_from_args(args: argparse.Namespace) -> str:
    raw = str(getattr(args, "output_format", "") or "").strip().lower()
    if raw in HEADLESS_OUTPUT_FORMAT_CHOICES:
        return raw
    if bool(getattr(args, "jsonl", False)):
        return HEADLESS_OUTPUT_FORMAT_STREAM_JSON
    if bool(getattr(args, "json", False)):
        return HEADLESS_OUTPUT_FORMAT_JSON
    return HEADLESS_OUTPUT_FORMAT_TEXT


def normalize_headless_output_args(args: argparse.Namespace) -> str | None:
    explicit_output_format = str(getattr(args, "output_format", "") or "").strip().lower() or None
    json_flag = bool(getattr(args, "json", False))
    jsonl_flag = bool(getattr(args, "jsonl", False))
    if json_flag and jsonl_flag:
        return "--json cannot be combined with --jsonl"
    if bool(getattr(args, "serve", False)) and explicit_output_format is not None:
        return "--serve cannot be combined with --output-format"

    alias_output_format: str | None = None
    if json_flag:
        alias_output_format = HEADLESS_OUTPUT_FORMAT_JSON
    elif jsonl_flag:
        alias_output_format = HEADLESS_OUTPUT_FORMAT_STREAM_JSON

    if (
        explicit_output_format is not None
        and alias_output_format is not None
        and explicit_output_format != alias_output_format
    ):
        conflicting_flag = "--json" if json_flag else "--jsonl"
        return (
            f"--output-format={explicit_output_format} cannot be combined with {conflicting_flag}"
        )

    resolved_output_format = (
        explicit_output_format or alias_output_format or HEADLESS_OUTPUT_FORMAT_TEXT
    )
    args.output_format = resolved_output_format
    args.json = resolved_output_format == HEADLESS_OUTPUT_FORMAT_JSON
    args.jsonl = resolved_output_format in {
        HEADLESS_OUTPUT_FORMAT_STREAM_JSON,
        HEADLESS_OUTPUT_FORMAT_CODEX_JSONL,
    }
    return None
