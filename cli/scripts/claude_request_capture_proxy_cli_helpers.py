from __future__ import annotations

import argparse
import shlex
from pathlib import Path

try:
    from .claude_request_capture_proxy_config_helpers import DEFAULT_UPSTREAM_BASE_URL
    from .claude_request_capture_proxy_config_helpers import resolve_upstream_base_url
    from .claude_request_capture_proxy_config_helpers import write_claude_proxy_settings
    from .claude_request_capture_proxy_server_helpers import create_capture_proxy_server
except ImportError:
    from claude_request_capture_proxy_config_helpers import DEFAULT_UPSTREAM_BASE_URL
    from claude_request_capture_proxy_config_helpers import resolve_upstream_base_url
    from claude_request_capture_proxy_config_helpers import write_claude_proxy_settings
    from claude_request_capture_proxy_server_helpers import create_capture_proxy_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python cli/scripts/claude_request_capture_proxy.py",
        description=(
            "Run a local reverse proxy for Claude-compatible traffic, forward to an upstream base URL, "
            "and persist raw request headers and bodies."
        ),
    )
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=8787)
    parser.add_argument(
        "--upstream-base-url",
        default="",
        help=(
            "Optional upstream Claude-compatible base URL. "
            "Defaults to the current Claude settings/config base URL, then falls back to "
            f"{DEFAULT_UPSTREAM_BASE_URL}."
        ),
    )
    parser.add_argument(
        "--claude-home",
        default=str(Path.home()),
        help="Claude home root used to resolve ~/.claude/settings.json and ~/.claude/config.json.",
    )
    parser.add_argument(
        "--write-claude-settings",
        nargs="?",
        const="auto",
        default="",
        help=(
            "Optionally write a Claude --settings JSON that points ANTHROPIC_BASE_URL to this local proxy "
            "while preserving the current Claude API key. Pass no value to write "
            "<out-dir>/claude_proxy_settings.json."
        ),
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--response-preview-bytes", type=int, default=8192)
    parser.add_argument("--upstream-timeout-seconds", type=float, default=300.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    claude_home = Path(str(args.claude_home)).expanduser()
    upstream_base_url, upstream_source, current = resolve_upstream_base_url(
        explicit_upstream_base_url=str(args.upstream_base_url),
        home_dir=claude_home,
    )
    server = create_capture_proxy_server(
        host=str(args.listen_host),
        port=int(args.listen_port),
        upstream_base_url=upstream_base_url,
        out_dir=Path(str(args.out_dir)),
        response_preview_bytes=int(args.response_preview_bytes),
        upstream_timeout_seconds=float(args.upstream_timeout_seconds),
    )
    host, port = server.server_address
    proxy_base_url = f"http://{host}:{port}"
    settings_output = str(args.write_claude_settings or "").strip()
    settings_file_path = ""
    if settings_output:
        settings_path = (
            (Path(str(args.out_dir)).resolve() / "claude_proxy_settings.json")
            if settings_output == "auto"
            else Path(settings_output).expanduser().resolve()
        )
        write_claude_proxy_settings(
            output_path=settings_path,
            proxy_base_url=proxy_base_url,
            home_dir=claude_home,
        )
        settings_file_path = str(settings_path)
    print(f"listening_url=http://{host}:{port}")
    print(f"export_ANTHROPIC_BASE_URL={proxy_base_url}")
    print(f"upstream_base_url={upstream_base_url}")
    print(f"upstream_source={upstream_source}")
    if current is not None:
        print(f"claude_settings_path={current.settings_path}")
        print(f"claude_config_path={current.config_path}")
    print(f"out_dir={Path(str(args.out_dir)).resolve()}")
    if settings_file_path:
        print(f"claude_settings_file={settings_file_path}")
        print(
            "claude_settings_hint="
            + shlex.join(["claude", "--settings", settings_file_path, "-p", "只回复 ok"])
        )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0
