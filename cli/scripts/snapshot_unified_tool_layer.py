#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

CLI_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CLI_ROOT.parent
DEFAULT_CASES = (
    ("openai", "gpt-5.4"),
    ("openai", "gpt-5.3-reference"),
    ("claude", "claude-sonnet-4-6"),
    ("glm", "glm-5"),
    ("deepseek", "deepseek-chat"),
)


def _ensure_import_paths() -> None:
    for candidate in (str(REPO_ROOT), str(CLI_ROOT)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)


_ensure_import_paths()

_script_runtime_helpers = importlib.import_module("cli.scripts.script_runtime_helpers")
apply_provider_home_override_env = _script_runtime_helpers.apply_provider_home_override_env

_report_runtime = importlib.import_module("cli.scripts.snapshot_unified_tool_layer_report_runtime")
resolve_effective_script_provider_home_dir = (
    _report_runtime.resolve_effective_script_provider_home_dir
)

_reporting = importlib.import_module("cli.scripts.snapshot_unified_tool_layer_reporting")
_print_table = _reporting.print_table


@dataclass(frozen=True)
class SnapshotCase:
    provider: str
    model: str

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"

    def env_overrides(self, *, provider_home: str = "") -> dict[str, str]:
        env = {
            "AGENT_CLI_PROVIDER": self.provider,
            "AGENT_CLI_MODEL": self.model,
        }
        return apply_provider_home_override_env(env, provider_home=provider_home)


def _parse_case(value: str) -> SnapshotCase:
    text = str(value or "").strip()
    provider, sep, model = text.partition(":")
    if not sep or not provider.strip() or not model.strip():
        raise argparse.ArgumentTypeError(f"invalid --case {value!r}; expected provider:model")
    return SnapshotCase(provider=provider.strip(), model=model.strip())


def _default_cases() -> list[SnapshotCase]:
    return [SnapshotCase(provider=provider, model=model) for provider, model in DEFAULT_CASES]


def _function_name_from_spec(spec):
    return _report_runtime._function_name_from_spec(spec)


def _alias_exposure_snapshot(*, exposed_names: set[str]):
    return _report_runtime._alias_exposure_snapshot(exposed_names=exposed_names)


def _canonical_inventory():
    return _report_runtime._canonical_inventory()


def _provider_home_report_fields(provider_home: str):
    return _report_runtime._provider_home_report_fields(
        provider_home,
        resolve_provider_home_dir_fn=resolve_effective_script_provider_home_dir,
    )


def _case_snapshot(case: SnapshotCase, *, provider_home: str):
    return _report_runtime._case_snapshot(
        case,
        provider_home=provider_home,
        resolve_provider_home_dir_fn=resolve_effective_script_provider_home_dir,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/snapshot_unified_tool_layer.py",
        description="Emit unified tool layer snapshots (canonical inventory + provider projections).",
    )
    parser.add_argument(
        "--case",
        action="append",
        type=_parse_case,
        dest="cases",
        help="Snapshot case in provider:model form. Repeat to override defaults.",
    )
    parser.add_argument(
        "--provider-home",
        default="",
        help=(
            "Optional provider runtime home override passed via AGENTHUB_PROVIDER_HOME for case loading. "
            "Probe-cache reads default to runtime-managed provider home resolution."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the default table summary.",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Optional file path for the full JSON report.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _ensure_import_paths()
    from cli.agent_cli.tools_core.tool_capabilities import utc_now_iso

    parser = build_parser()
    args = parser.parse_args(argv)
    cases = list(args.cases or _default_cases())
    if not cases:
        raise SystemExit("no snapshot cases configured")

    report = {
        "generated_at": utc_now_iso(),
        **_provider_home_report_fields(str(args.provider_home or "")),
        "canonical_tool_inventory": _canonical_inventory(),
        "cases": [
            _case_snapshot(case, provider_home=str(args.provider_home or "")) for case in cases
        ],
    }

    if args.out:
        out_path = Path(str(args.out)).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_table(report)
        if args.out:
            print()
            print(f"snapshot_path={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
