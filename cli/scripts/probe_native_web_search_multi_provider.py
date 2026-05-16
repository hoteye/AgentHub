#!/usr/bin/env python3
# ruff: noqa: E402,I001
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


CLI_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CLI_ROOT.parent
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_WORKERS = 4
DEFAULT_QUERY = "agenthub native web_search capability probe"
PROBE_REPORT_SCHEMA_VERSION = "native_web_search_probe_report/v1"


def _ensure_import_paths() -> None:
    for candidate in (str(REPO_ROOT), str(CLI_ROOT)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)


_ensure_import_paths()


from cli.scripts.script_runtime_helpers import (
    resolve_effective_script_provider_home_dir,
)
from cli.scripts.probe_native_web_search_backend_probes import (
    _classify_probe_exception,
    _error_text,
    _probe_with_loaded_config,
    _response_text_preview,
)
from cli.scripts.probe_native_web_search_cases import (
    ProbeCase,
    default_cases as _default_cases,
    parse_case as _parse_case,
)
from cli.scripts.probe_native_web_search_reporting import (
    PROBE_CACHE_SCHEMA_VERSION,
    PROBE_TOOL_KEY,
    _print_table,
    _probe_cache_payload,
    _summary_rows,
)
from cli.scripts.probe_native_web_search_worker_process import (
    common_worker_command as _common_worker_command_impl,
    run_case_subprocess as _run_case_subprocess_impl,
)
from cli.agent_cli.tools_core.tool_capabilities import (
    DEFAULT_WEB_SEARCH_PROBE_CACHE_FILENAME,
    DEFAULT_WEB_SEARCH_PROBE_CACHE_TTL_SECONDS,
    utc_now_iso,
)
from cli.scripts.probe_native_web_search_multi_provider_runtime import (
    provider_home_report_fields as _provider_home_report_fields_impl,
)
from cli.scripts.probe_native_web_search_multi_provider_runtime import (
    run_worker as _run_worker_impl,
)

DEFAULT_CACHE_TTL_SECONDS = int(DEFAULT_WEB_SEARCH_PROBE_CACHE_TTL_SECONDS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/probe_native_web_search_multi_provider.py",
        description="Probe native web_search capability across multiple provider:model pairs.",
    )
    parser.add_argument(
        "--case",
        action="append",
        type=_parse_case,
        dest="cases",
        help="Probe case in provider:model form. Repeat to override defaults.",
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_QUERY,
        help=f"Probe query text. Defaults to {DEFAULT_QUERY!r}.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-case timeout in seconds. Defaults to {DEFAULT_TIMEOUT_SECONDS:g}.",
    )
    parser.add_argument(
        "--provider-home",
        default="",
        help=(
            "Optional provider runtime home override passed via AGENTHUB_PROVIDER_HOME. "
            "Defaults to runtime-managed provider home resolution."
        ),
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help=f"Max concurrent worker subprocesses. Defaults to {DEFAULT_MAX_WORKERS}.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the default table summary.",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Optional path to write the full JSON report.",
    )
    parser.add_argument(
        "--cache-out",
        default="",
        help=(
            "Optional path to write normalized probe-cache JSON entries. "
            f"The runtime default filename is {DEFAULT_WEB_SEARCH_PROBE_CACHE_FILENAME!r} under provider-home."
        ),
    )
    parser.add_argument(
        "--cache-ttl-seconds",
        type=int,
        default=DEFAULT_CACHE_TTL_SECONDS,
        help=f"TTL in seconds for generated probe cache entries. Defaults to {DEFAULT_CACHE_TTL_SECONDS}.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print worker commands without executing requests.",
    )
    parser.add_argument(
        "--worker",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--provider",
        default="",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--model",
        default="",
        help=argparse.SUPPRESS,
    )
    return parser


def _common_worker_command(
    case: ProbeCase,
    *,
    query: str,
    timeout_seconds: float,
    provider_home: str,
) -> list[str]:
    return _common_worker_command_impl(
        case,
        script_path=Path(__file__).resolve(),
        query=query,
        timeout_seconds=timeout_seconds,
        provider_home=provider_home,
    )


def _provider_home_report_fields(provider_home: str) -> dict[str, str]:
    return _provider_home_report_fields_impl(
        provider_home,
        cwd=CLI_ROOT,
        resolve_provider_home_dir=resolve_effective_script_provider_home_dir,
    )


def _run_worker(args: argparse.Namespace) -> int:
    return _run_worker_impl(
        args,
        cli_root=CLI_ROOT,
        import_paths_ensurer=_ensure_import_paths,
        provider_home_reporter=_provider_home_report_fields,
        probe_runner=_probe_with_loaded_config,
        classify_probe_exception=_classify_probe_exception,
    )


def _run_case_subprocess(
    case: ProbeCase,
    *,
    query: str,
    timeout_seconds: float,
    provider_home: str,
) -> dict[str, Any]:
    return _run_case_subprocess_impl(
        case,
        cli_root=CLI_ROOT,
        script_path=Path(__file__).resolve(),
        query=query,
        timeout_seconds=timeout_seconds,
        provider_home=provider_home,
        response_text_preview_fn=_response_text_preview,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.worker:
        return _run_worker(args)

    cases = list(args.cases or _default_cases())
    if not cases:
        raise SystemExit("no probe cases configured")

    if args.dry_run:
        for case in cases:
            print(
                " ".join(
                    _common_worker_command(
                        case,
                        query=str(args.query or "").strip(),
                        timeout_seconds=float(args.timeout),
                        provider_home=str(args.provider_home),
                    )
                )
            )
        return 0

    max_workers = max(1, min(int(args.max_workers), len(cases)))
    results: list[dict[str, Any]] = []
    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(
                _run_case_subprocess,
                case,
                query=str(args.query or "").strip(),
                timeout_seconds=float(args.timeout),
                provider_home=str(args.provider_home),
            ): case
            for case in cases
        }
        for future in as_completed(future_map):
            case = future_map[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(
                    {
                        "case": case.label,
                        "provider": case.provider,
                        "model": case.model,
                        "status": "error",
                        "confidence": "high",
                        "issue": _error_text(exc),
                        "elapsed_ms": 0,
                    }
                )

    results.sort(key=lambda item: str(item.get("case") or ""))
    provider_home_fields = _provider_home_report_fields(str(args.provider_home or ""))
    report = {
        "version": PROBE_REPORT_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "tool": PROBE_TOOL_KEY,
        "probe_cache_schema_version": PROBE_CACHE_SCHEMA_VERSION,
        "query": str(args.query or "").strip(),
        "timeout_seconds": float(args.timeout),
        **provider_home_fields,
        "probe_cache_default_filename": DEFAULT_WEB_SEARCH_PROBE_CACHE_FILENAME,
        "probe_cache_default_path": str(
            Path(provider_home_fields["provider_home"]).expanduser()
            / DEFAULT_WEB_SEARCH_PROBE_CACHE_FILENAME
        ),
        "cases": [case.label for case in cases],
        "results": results,
        "summary": _summary_rows(results),
        "probe_cache": _probe_cache_payload(
            results,
            default_ttl_seconds=max(0, int(args.cache_ttl_seconds)),
        ),
    }

    if args.out:
        out_path = Path(str(args.out)).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.cache_out:
        cache_out_path = Path(str(args.cache_out)).expanduser()
        cache_out_path.parent.mkdir(parents=True, exist_ok=True)
        cache_out_path.write_text(
            json.dumps(report["probe_cache"], ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_table(results)
        print()
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        if args.out:
            print(f"report_path={args.out}")
        if args.cache_out:
            print(f"probe_cache_path={args.cache_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
