#!/usr/bin/env python3
from __future__ import annotations

try:
    from .claude_request_capture_proxy_cli_helpers import build_parser
    from .claude_request_capture_proxy_cli_helpers import main
    from .claude_request_capture_proxy_config_helpers import DEFAULT_UPSTREAM_BASE_URL
    from .claude_request_capture_proxy_config_helpers import ClaudeHomeConfig
    from .claude_request_capture_proxy_config_helpers import ProxyConfig
    from .claude_request_capture_proxy_config_helpers import _first_text
    from .claude_request_capture_proxy_config_helpers import _read_json_file
    from .claude_request_capture_proxy_config_helpers import _write_json
    from .claude_request_capture_proxy_config_helpers import load_claude_home_config
    from .claude_request_capture_proxy_config_helpers import resolve_upstream_base_url
    from .claude_request_capture_proxy_config_helpers import write_claude_proxy_settings
    from .claude_request_capture_proxy_http_helpers import _HOP_BY_HOP_HEADERS
    from .claude_request_capture_proxy_http_helpers import _decode_body
    from .claude_request_capture_proxy_http_helpers import _header_items
    from .claude_request_capture_proxy_http_helpers import _join_upstream_path
    from .claude_request_capture_proxy_http_helpers import _now_iso
    from .claude_request_capture_proxy_http_helpers import _upstream_target_url
    from .claude_request_capture_proxy_server_helpers import CaptureProxyServer
    from .claude_request_capture_proxy_server_helpers import _ThreadedHTTPServer
    from .claude_request_capture_proxy_server_helpers import build_capture_proxy_handler
    from .claude_request_capture_proxy_server_helpers import create_capture_proxy_server
except ImportError:
    from claude_request_capture_proxy_cli_helpers import build_parser
    from claude_request_capture_proxy_cli_helpers import main
    from claude_request_capture_proxy_config_helpers import DEFAULT_UPSTREAM_BASE_URL
    from claude_request_capture_proxy_config_helpers import ClaudeHomeConfig
    from claude_request_capture_proxy_config_helpers import ProxyConfig
    from claude_request_capture_proxy_config_helpers import _first_text
    from claude_request_capture_proxy_config_helpers import _read_json_file
    from claude_request_capture_proxy_config_helpers import _write_json
    from claude_request_capture_proxy_config_helpers import load_claude_home_config
    from claude_request_capture_proxy_config_helpers import resolve_upstream_base_url
    from claude_request_capture_proxy_config_helpers import write_claude_proxy_settings
    from claude_request_capture_proxy_http_helpers import _HOP_BY_HOP_HEADERS
    from claude_request_capture_proxy_http_helpers import _decode_body
    from claude_request_capture_proxy_http_helpers import _header_items
    from claude_request_capture_proxy_http_helpers import _join_upstream_path
    from claude_request_capture_proxy_http_helpers import _now_iso
    from claude_request_capture_proxy_http_helpers import _upstream_target_url
    from claude_request_capture_proxy_server_helpers import CaptureProxyServer
    from claude_request_capture_proxy_server_helpers import _ThreadedHTTPServer
    from claude_request_capture_proxy_server_helpers import build_capture_proxy_handler
    from claude_request_capture_proxy_server_helpers import create_capture_proxy_server


if __name__ == "__main__":
    raise SystemExit(main())
