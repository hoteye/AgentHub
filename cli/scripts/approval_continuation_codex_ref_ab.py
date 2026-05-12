#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

try:
    from cli.scripts.script_runtime_helpers import (
        ensure_script_import_paths,
        resolve_script_provider_run_settings,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from script_runtime_helpers import (  # type: ignore[no-redef]
        ensure_script_import_paths,
        resolve_script_provider_run_settings,
    )


_SCRIPT_PATHS = ensure_script_import_paths(__file__)

try:
    from cli.scripts.approval_continuation_codex_ref_ab_case_helpers import (
        CASES,
        AbCase,
        _prompt_for_case,
        _selected_cases,
    )
    from cli.scripts.approval_continuation_codex_ref_ab_config_helpers import (
        CLI_ROOT,
        DEFAULT_CODEX_APP_SERVER_TEST_CLIENT,
        DEFAULT_CODEX_BIN,
        DEFAULT_CODEX_REF_ROOT,
        DEFAULT_OPENAI_BASE_URL,
        DEFAULT_TIMEOUT_SECONDS,
        LIVE_HARNESS,
        REPO_ROOT,
        _build_codex_home,
        _default_codex_provider_id,
        _is_official_openai_base_url,
        _resolve_run_settings as _resolve_run_settings_from_provider,
    )
    from cli.scripts.approval_continuation_codex_ref_ab_model_helpers import (
        CommandResult,
        _file_state,
        _now_iso,
        _read_json,
        _write_json,
        _write_text,
    )
    from cli.scripts.approval_continuation_codex_ref_ab_reporting_helpers import (
        _redacted_settings,
        _write_commands_txt,
        _write_summary_md,
    )
    from cli.scripts.approval_continuation_codex_ref_ab_runtime_helpers import (
        _agenthub_report_for_case,
        _case_verdict,
        _parse_codex_stdout,
        _run_case,
        _run_command,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from approval_continuation_codex_ref_ab_case_helpers import (  # type: ignore[no-redef]
        CASES,
        AbCase,
        _prompt_for_case,
        _selected_cases,
    )
    from approval_continuation_codex_ref_ab_config_helpers import (  # type: ignore[no-redef]
        CLI_ROOT,
        DEFAULT_CODEX_APP_SERVER_TEST_CLIENT,
        DEFAULT_CODEX_BIN,
        DEFAULT_CODEX_REF_ROOT,
        DEFAULT_OPENAI_BASE_URL,
        DEFAULT_TIMEOUT_SECONDS,
        LIVE_HARNESS,
        REPO_ROOT,
        _build_codex_home,
        _default_codex_provider_id,
        _is_official_openai_base_url,
        _resolve_run_settings as _resolve_run_settings_from_provider,
    )
    from approval_continuation_codex_ref_ab_model_helpers import (  # type: ignore[no-redef]
        CommandResult,
        _file_state,
        _now_iso,
        _read_json,
        _write_json,
        _write_text,
    )
    from approval_continuation_codex_ref_ab_reporting_helpers import (  # type: ignore[no-redef]
        _redacted_settings,
        _write_commands_txt,
        _write_summary_md,
    )
    from approval_continuation_codex_ref_ab_runtime_helpers import (  # type: ignore[no-redef]
        _agenthub_report_for_case,
        _case_verdict,
        _parse_codex_stdout,
        _run_case,
        _run_command,
    )


def _resolve_run_settings(args: argparse.Namespace) -> dict[str, str]:
    return _resolve_run_settings_from_provider(
        args,
        resolver=resolve_script_provider_run_settings,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run AgentHub OpenAI approval continuation vs codex_ref app-server approval A/B cases.",
    )
    parser.add_argument("--out-root", default="", help="Output root. Defaults to a new /tmp directory.")
    parser.add_argument("--provider", default="", help="AgentHub provider. Defaults to current selection, usually openai.")
    parser.add_argument("--model", default="", help="AgentHub model key or model id. Defaults to current selection.")
    parser.add_argument("--reasoning-effort", default="", help="Defaults to current selection or catalog default.")
    parser.add_argument("--openai-base-url", default="", help="Defaults to current selected provider base_url.")
    parser.add_argument("--codex-provider-id", default="", help="Defaults to openai for official OpenAI, openai-relay otherwise.")
    parser.add_argument("--codex-bin", default=str(DEFAULT_CODEX_BIN))
    parser.add_argument("--codex-app-server-test-client", default=str(DEFAULT_CODEX_APP_SERVER_TEST_CLIENT))
    parser.add_argument("--api-key-name", default="OPENAI_API_KEY", help="Deprecated; API keys are resolved by provider management.")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--case", action="append", default=[], help="Case name to run. Repeat to restrict.")
    parser.add_argument("--run-live", action="store_true", help="Actually call live providers. Omitted means dry-run.")
    return parser


def run_harness(args: argparse.Namespace) -> dict[str, Any]:
    out_root = (
        Path(args.out_root).expanduser().resolve()
        if str(args.out_root or "").strip()
        else Path(tempfile.mkdtemp(prefix="approval_continuation_codex_ref_ab_", dir="/tmp")).resolve()
    )
    out_root.mkdir(parents=True, exist_ok=True)
    settings = _resolve_run_settings(args)
    provider = settings["provider"]
    if provider != "openai":
        raise SystemExit(f"approval codex_ref A/B currently supports provider=openai only, got `{provider}`")
    base_url = str(args.openai_base_url or "").strip() or settings["base_url"] or DEFAULT_OPENAI_BASE_URL
    codex_provider_id = str(args.codex_provider_id or "").strip() or _default_codex_provider_id(base_url)
    codex_bin = Path(str(args.codex_bin)).expanduser().resolve()
    codex_app_server_test_client = Path(str(args.codex_app_server_test_client)).expanduser().resolve()
    if args.run_live and not codex_bin.exists():
        raise SystemExit(f"missing codex binary: {codex_bin}")
    if args.run_live and not codex_app_server_test_client.exists():
        raise SystemExit(f"missing codex app-server test client: {codex_app_server_test_client}")
    dry_run = not bool(args.run_live)
    resolved_api_key = str(settings.get("api_key") or "").strip()
    api_key = resolved_api_key
    if not api_key and dry_run:
        api_key = "dry-run-api-key"
    if not api_key:
        raise SystemExit("missing resolved API key from provider management snapshot")
    results = [
        _run_case(
            case=case,
            case_root=out_root / case.name,
            provider=provider,
            agenthub_model=settings["agenthub_model"],
            codex_model=settings["codex_model"],
            reasoning_effort=settings["reasoning_effort"],
            base_url=base_url,
            api_key=api_key,
            codex_provider_id=codex_provider_id,
            codex_bin=codex_bin,
            codex_app_server_test_client=codex_app_server_test_client,
            timeout_seconds=int(args.timeout_seconds or DEFAULT_TIMEOUT_SECONDS),
            dry_run=dry_run,
        )
        for case in _selected_cases([str(item) for item in list(args.case or [])])
    ]
    pass_count = sum(1 for item in results if item.get("verdict") == "pass")
    fail_count = sum(1 for item in results if item.get("verdict") not in {"pass", "dry_run"})
    report = {
        "schema_version": "approval_continuation_codex_ref_ab_v1",
        "created_at": _now_iso(),
        "dry_run": dry_run,
        "out_root": str(out_root),
        "provider": provider,
        "agenthub_model": settings["agenthub_model"],
        "codex_model": settings["codex_model"],
        "reasoning_effort": settings["reasoning_effort"],
        "base_url": base_url,
        "codex_provider_id": codex_provider_id,
        "codex_bin": str(codex_bin),
        "codex_app_server_test_client": str(codex_app_server_test_client),
        "auth": {
            "path": settings["auth_path"],
            "api_key_name": str(args.api_key_name or "OPENAI_API_KEY"),
            "api_key_present": bool(resolved_api_key),
        },
        "case_count": len(results),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "verdict": "dry_run" if dry_run else "pass" if fail_count == 0 else "fail",
        "settings": _redacted_settings(settings),
        "results": results,
    }
    _write_json(out_root / "report.json", report)
    _write_summary_md(out_root / "summary.md", report)
    _write_commands_txt(out_root / "commands.txt", results)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_harness(args)
    return 0 if report.get("verdict") in {"pass", "dry_run"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
