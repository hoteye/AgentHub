#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from cli.scripts.script_runtime_helpers import ensure_script_import_paths
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from script_runtime_helpers import ensure_script_import_paths  # type: ignore[no-redef]

_SCRIPT_PATHS = ensure_script_import_paths(__file__)
CLI_ROOT = _SCRIPT_PATHS.cli_root
REPO_ROOT = _SCRIPT_PATHS.repo_root

DEFAULT_CODEX_BIN = "/home/lyc/project/AgentHubRef/codex_ref/codex-rs/target/debug/codex"


try:
    from cli.scripts.local_web_search_codex_ref_ab_cases import (
        CASES as CASES,
    )
    from cli.scripts.local_web_search_codex_ref_ab_cases import (
        SearchCase as SearchCase,
    )
    from cli.scripts.local_web_search_codex_ref_ab_cases import (
        _extract_json_object as _extract_json_object,
    )
    from cli.scripts.local_web_search_codex_ref_ab_cases import (
        _host as _host,
    )
    from cli.scripts.local_web_search_codex_ref_ab_cases import (
        _host_matches as _host_matches,
    )
    from cli.scripts.local_web_search_codex_ref_ab_cases import (
        _read_jsonl as _read_jsonl,
    )
    from cli.scripts.local_web_search_codex_ref_ab_cases import (
        _selected_cases,
    )
    from cli.scripts.local_web_search_codex_ref_ab_cases import (
        _text_matches_expected as _text_matches_expected,
    )
    from cli.scripts.local_web_search_codex_ref_ab_cases import (
        _url_matches_expected as _url_matches_expected,
    )
    from cli.scripts.local_web_search_codex_ref_ab_report import (
        _case_summary,
        _markdown_report,
        _write_json,
        _write_text,
    )
    from cli.scripts.local_web_search_codex_ref_ab_runtime import (
        _codex_version,
        _run_codex_case,
        _run_local_case,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from local_web_search_codex_ref_ab_cases import (  # type: ignore[no-redef]
        CASES as CASES,
    )
    from local_web_search_codex_ref_ab_cases import (
        SearchCase as SearchCase,
    )
    from local_web_search_codex_ref_ab_cases import (
        _extract_json_object as _extract_json_object,
    )
    from local_web_search_codex_ref_ab_cases import (
        _host as _host,
    )
    from local_web_search_codex_ref_ab_cases import (
        _host_matches as _host_matches,
    )
    from local_web_search_codex_ref_ab_cases import (
        _read_jsonl as _read_jsonl,
    )
    from local_web_search_codex_ref_ab_cases import (
        _selected_cases,
    )
    from local_web_search_codex_ref_ab_cases import (
        _text_matches_expected as _text_matches_expected,
    )
    from local_web_search_codex_ref_ab_cases import (
        _url_matches_expected as _url_matches_expected,
    )
    from local_web_search_codex_ref_ab_report import (  # type: ignore[no-redef]
        _case_summary,
        _markdown_report,
        _write_json,
        _write_text,
    )
    from local_web_search_codex_ref_ab_runtime import (  # type: ignore[no-redef]
        _codex_version,
        _run_codex_case,
        _run_local_case,
    )


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python cli/scripts/local_web_search_codex_ref_ab.py",
        description="Compare AgentHub local web_search against the compiled codex_ref binary on website lookup cases.",
    )
    parser.add_argument("--codex-bin", default=DEFAULT_CODEX_BIN)
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--reasoning-effort", default="low")
    parser.add_argument("--sandbox", default="danger-full-access")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--case", action="append", dest="cases", help="Optional case id filter. Repeatable."
    )
    parser.add_argument("--out-dir", default="")
    parser.add_argument(
        "--fetch-top", action="store_true", help="Also run local web_fetch on the local top result."
    )
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    codex_bin = Path(args.codex_bin).expanduser().resolve()
    if not codex_bin.exists() or not codex_bin.is_file():
        raise SystemExit(f"codex binary not found: {codex_bin}")
    cases = _selected_cases(args.cases)
    if not cases:
        raise SystemExit("no matching cases selected")
    out_dir = (
        Path(args.out_dir).expanduser().resolve()
        if str(args.out_dir or "").strip()
        else Path(tempfile.mkdtemp(prefix="agenthub_local_web_search_codex_ref_ab_"))
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    case_rows: list[dict[str, Any]] = []
    for case in cases:
        local = _run_local_case(case, limit=int(args.limit), fetch_top=bool(args.fetch_top))
        codex = _run_codex_case(
            case,
            codex_bin=codex_bin,
            model=str(args.model),
            reasoning_effort=str(args.reasoning_effort or ""),
            sandbox=str(args.sandbox),
            timeout_seconds=int(args.timeout_seconds),
            out_dir=out_dir,
        )
        case_rows.append(_case_summary(case, local, codex))
    summary = {
        "total": len(case_rows),
        "both_hit": sum(1 for case in case_rows if case["parity"]["classification"] == "both_hit"),
        "local_only": sum(
            1 for case in case_rows if case["parity"]["classification"] == "local_only"
        ),
        "codex_only": sum(
            1 for case in case_rows if case["parity"]["classification"] == "codex_only"
        ),
        "both_miss": sum(
            1 for case in case_rows if case["parity"]["classification"] == "both_miss"
        ),
    }
    report = {
        "suite": "local_web_search_codex_ref_ab",
        "generated_at": _iso_now(),
        "repo_root": str(REPO_ROOT),
        "cli_root": str(CLI_ROOT),
        "out_dir": str(out_dir),
        "codex_bin": str(codex_bin),
        "codex_version": _codex_version(codex_bin),
        "model": str(args.model),
        "reasoning_effort": str(args.reasoning_effort or ""),
        "sandbox": str(args.sandbox),
        "summary": summary,
        "cases": case_rows,
    }
    json_path = out_dir / "local_web_search_codex_ref_ab.report.json"
    md_path = out_dir / "local_web_search_codex_ref_ab.report.md"
    _write_json(json_path, report)
    _write_text(md_path, _markdown_report(report))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"out_dir={out_dir}")
        print(f"json_report={json_path}")
        print(f"markdown_report={md_path}")
        print(
            "summary="
            + ",".join(
                f"{key}={summary[key]}"
                for key in ("total", "both_hit", "local_only", "codex_only", "both_miss")
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
