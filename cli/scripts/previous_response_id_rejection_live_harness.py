#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from cli.scripts.previous_response_id_rejection_live_harness_analysis_helpers import (
        analyze_observed_requests,
    )
    from cli.scripts.previous_response_id_rejection_live_harness_model_helpers import (
        DEFAULT_EXPECTED_OUTPUT,
        DEFAULT_PROMPT,
        _HOP_BY_HOP_HEADERS,
        _REJECTION_BODY,
        ObservedRequest,
        ProxyConfig,
        _body_item_types,
        _decode_body,
        _default_out_dir,
        _join_upstream_path,
        _now_iso,
        _redacted_headers,
        _tool_names,
        _upstream_target_url,
        _write_json,
    )
    from cli.scripts.previous_response_id_rejection_live_harness_proxy_helpers import (
        PreviousResponseIdProxyServer,
        _ThreadedHTTPServer,
        build_previous_response_id_proxy_handler,
        create_previous_response_id_proxy_server,
    )
    from cli.scripts.previous_response_id_rejection_live_harness_runtime_helpers import (
        _PlannerStub,
        _load_api_key,
        _provider_config,
        _tool_executor,
        _tool_spec,
        _unexpected_terminal_handler,
        run_previous_response_id_rejection_harness,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from previous_response_id_rejection_live_harness_analysis_helpers import (  # type: ignore[no-redef]
        analyze_observed_requests,
    )
    from previous_response_id_rejection_live_harness_model_helpers import (  # type: ignore[no-redef]
        DEFAULT_EXPECTED_OUTPUT,
        DEFAULT_PROMPT,
        _HOP_BY_HOP_HEADERS,
        _REJECTION_BODY,
        ObservedRequest,
        ProxyConfig,
        _body_item_types,
        _decode_body,
        _default_out_dir,
        _join_upstream_path,
        _now_iso,
        _redacted_headers,
        _tool_names,
        _upstream_target_url,
        _write_json,
    )
    from previous_response_id_rejection_live_harness_proxy_helpers import (  # type: ignore[no-redef]
        PreviousResponseIdProxyServer,
        _ThreadedHTTPServer,
        build_previous_response_id_proxy_handler,
        create_previous_response_id_proxy_server,
    )
    from previous_response_id_rejection_live_harness_runtime_helpers import (  # type: ignore[no-redef]
        _PlannerStub,
        _load_api_key,
        _provider_config,
        _tool_executor,
        _tool_spec,
        _unexpected_terminal_handler,
        run_previous_response_id_rejection_harness,
    )


def run_harness(args: argparse.Namespace) -> dict[str, Any]:
    return run_previous_response_id_rejection_harness(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Live harness for the previous_response_id rejection -> full replay fallback path.",
    )
    parser.add_argument("--auth-json", default="/home/lyc/project/AgentHub/cli/.config/auth.json")
    parser.add_argument("--api-key-name", default="OPENAI_API_KEY")
    parser.add_argument("--base-url", default="https://relay05.gaccode.com/codex/v1")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--effort", default="xhigh")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--expected-output", default=DEFAULT_EXPECTED_OUTPUT)
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--upstream-timeout-seconds", type=float, default=180.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    summary = run_harness(args)
    return 0 if summary.get("verdict") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
