from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
from pathlib import Path
from typing import Any


_SCRIPT_PATH = Path(__file__).resolve()
for _candidate in _SCRIPT_PATH.parents:
    if _candidate.name == "cli":
        CLI_ROOT = _candidate
        REPO_ROOT = _candidate.parent
        break
else:  # pragma: no cover - defensive fallback
    CLI_ROOT = _SCRIPT_PATH.parents[3]
    REPO_ROOT = CLI_ROOT.parent
for _entry in (str(REPO_ROOT), str(CLI_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from cli.scripts.experiments.weather_web_search.replay_weather_header_tool_axes_model_helpers import (
    DEFAULT_AGENTHUB_TIMELINE,
    DEFAULT_CODEX_TIMELINE,
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OUT_DIR,
    DEFAULT_PROXY_LOG,
    DROP_REQUEST_HEADERS,
    ReplayCase,
    WEATHER_DETAIL_MARKERS,
)
from cli.scripts.experiments.weather_web_search.replay_weather_header_tool_axes_header_helpers import (
    _build_header_family,
    _generate_codex_session_headers,
    _normalize_header_name,
    _swap_tools,
)
from cli.scripts.experiments.weather_web_search.replay_weather_header_tool_axes_reporting_helpers import (
    _summarize_case,
    _write_markdown_report,
)
from cli.scripts.experiments.weather_web_search.replay_weather_header_tool_axes_request_helpers import (
    _load_agenthub_request,
    _load_codex_request,
    _load_proxy_headers,
    _load_runtime_provider_request_target,
    _read_jsonl,
)
from cli.scripts.experiments.weather_web_search.replay_weather_header_tool_axes_response_helpers import (
    _classify_result,
    _extract_message_text,
    _extract_response_items,
    _parse_event_stream,
)
from cli.scripts.experiments.weather_web_search.replay_weather_header_tool_axes_runtime_helpers import (
    _attempt_path,
    _execute_request,
    _run_attempt,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay weather requests across header/tool axes.")
    parser.add_argument("--agenthub-timeline", type=Path, default=DEFAULT_AGENTHUB_TIMELINE)
    parser.add_argument("--codex-timeline", type=Path, default=DEFAULT_CODEX_TIMELINE)
    parser.add_argument("--proxy-log", type=Path, default=DEFAULT_PROXY_LOG)
    parser.add_argument("--config-toml", type=Path, default=None)
    parser.add_argument("--auth-json", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--runs", type=int, default=4)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=180.0)
    return parser.parse_args()


def _replay_cases() -> list[ReplayCase]:
    return [
        ReplayCase(body_family=body_family, header_family=header_family, tool_family=tool_family)
        for body_family in ("agenthub", "codex")
        for header_family in ("agenthub", "codex")
        for tool_family in ("agenthub", "codex")
    ]


def _print_attempt_progress(case: ReplayCase, run_index: int, attempt: dict[str, Any]) -> None:
    result = attempt.get("result") or {}
    classification = dict(result.get("classification") or {})
    print(
        json.dumps(
            {
                "case": case.label,
                "run": run_index,
                "http_ok": bool(result.get("http_ok")),
                "elapsed_ms": int(result.get("elapsed_ms") or 0),
                "with_web": int(classification.get("web_search_count") or 0) > 0,
                "short_no_web": bool(classification.get("short_no_web")),
                "output_len": int(classification.get("output_len") or 0),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def main() -> int:
    args = parse_args()
    request_bodies = {
        "agenthub": _load_agenthub_request(args.agenthub_timeline),
        "codex": _load_codex_request(args.codex_timeline),
    }
    tool_families = {
        "agenthub": list(request_bodies["agenthub"].get("tools") or []),
        "codex": list(request_bodies["codex"].get("tools") or []),
    }
    agenthub_headers, codex_headers = _load_proxy_headers(args.proxy_log)
    url, api_key = _load_runtime_provider_request_target(args.config_toml, args.auth_json, cli_root=CLI_ROOT)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    cases = _replay_cases()
    attempts_by_case: dict[str, list[dict[str, Any]]] = {case.label: [] for case in cases}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, int(args.max_workers))) as executor:
        future_map = {
            executor.submit(
                _run_attempt,
                case=case,
                run_index=run_index,
                out_dir=args.out_dir,
                url=url,
                api_key=api_key,
                request_bodies=request_bodies,
                tool_families=tool_families,
                agenthub_headers=agenthub_headers,
                codex_headers=codex_headers,
                timeout_seconds=float(args.timeout),
            ): (case, run_index)
            for case in cases
            for run_index in range(1, int(args.runs) + 1)
        }
        for future in concurrent.futures.as_completed(future_map):
            case, run_index = future_map[future]
            attempt = future.result()
            attempts_by_case[case.label].append(attempt)
            _print_attempt_progress(case, run_index, attempt)

    ordered_summary = {
        case.label: _summarize_case(
            sorted(attempts_by_case[case.label], key=lambda item: int(item.get("run_index") or 0))
        )
        for case in cases
    }
    summary_path = args.out_dir / "summary.json"
    summary_path.write_text(json.dumps(ordered_summary, ensure_ascii=False, indent=2))
    report_path = _write_markdown_report(
        out_dir=args.out_dir,
        summary=ordered_summary,
        runs_per_case=int(args.runs),
        timeout_seconds=float(args.timeout),
    )
    print(json.dumps({"summary_path": str(summary_path), "report_path": str(report_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
