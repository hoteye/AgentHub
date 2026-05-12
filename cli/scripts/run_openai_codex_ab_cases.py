#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from cli.scripts.script_runtime_helpers import ensure_script_import_paths, resolve_model_and_reasoning_settings
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from script_runtime_helpers import ensure_script_import_paths, resolve_model_and_reasoning_settings

_SCRIPT_PATHS = ensure_script_import_paths(__file__)
PROJECT_ROOT = _SCRIPT_PATHS.repo_root

CLI_ROOT = _SCRIPT_PATHS.cli_root
HARNESS_PATH = CLI_ROOT / "scripts" / "benchmark_emptydir_ab.py"

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


@dataclass(frozen=True)
class CaseSpec:
    name: str
    prompt: str
    validate: str = ""


CASES: tuple[CaseSpec, ...] = (
    CaseSpec(
        name="case_01_emptydir",
        prompt=(
            "当前目录中忽略以 . 开头的隐藏文件后，是否为空？"
            "如果为空，只用一句中文说明；如果不为空，列出一层文件名。"
            "不要创建或修改任何文件。"
        ),
    ),
    CaseSpec(
        name="case_02_python_hello",
        prompt=(
            "当前目录是空的。请创建一个最小 Python 项目："
            "main.py 输出 hello world，README.md 写运行方法。"
            "完成后简要说明创建了哪些文件。"
        ),
        validate="python main.py",
    ),
    CaseSpec(
        name="case_03_rg_todo",
        prompt=(
            "请在当前目录创建 sample.py，里面放两个 TODO 注释；"
            "再告诉我如何用 rg 搜到它们。不要安装额外依赖。"
        ),
        validate='rg -n "TODO" sample.py',
    ),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python cli/scripts/run_openai_codex_ab_cases.py",
        description="Run the fixed 3-case OpenAI gpt-5.4 Codex-vs-AgentHub empty-dir A/B harness.",
    )
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--model", default="")
    parser.add_argument("--reasoning-effort", default="")
    parser.add_argument("--openai-base-url", default=DEFAULT_OPENAI_BASE_URL)
    parser.add_argument("--agenthub-interaction-profile", default="codex_openai")
    parser.add_argument(
        "--codex-provider-id",
        default="",
        help="Optional Codex provider id for ephemeral config. Defaults to harness auto-detection.",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        help="Optional case name filter. Repeat to select multiple cases.",
    )
    parser.add_argument(
        "--retry-attempts",
        type=int,
        default=2,
        help="Maximum attempts per case when AgentHub falls back off provider path.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=420)
    parser.add_argument(
        "--out-root",
        default="",
        help="Optional output directory. Defaults to a new /tmp temp directory.",
    )
    return parser


def _selected_cases(requested_names: list[str] | None) -> list[CaseSpec]:
    if not requested_names:
        return list(CASES)
    wanted = {str(name or "").strip() for name in requested_names if str(name or "").strip()}
    return [case for case in CASES if case.name in wanted]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload


def _agenthub_provider_used(attempt_dir: Path) -> bool:
    detail = _read_json(attempt_dir / "agenthub.detail.json")
    if not isinstance(detail, dict):
        return False
    protocol_path = dict(detail.get("protocol_diagnostics") or {}).get("protocol_path") or {}
    if isinstance(protocol_path, dict):
        return bool(protocol_path.get("provider_used"))
    return False


def _workspace_inventory(attempt_dir: Path, name: str) -> list[str]:
    payload = _read_json(attempt_dir / f"{name}.workspace.files.json")
    if not isinstance(payload, list):
        return []
    items: list[str] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        path_text = str(item.get("path") or "").strip()
        if path_text:
            items.append(path_text)
    return items


def _summary_excerpt(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "agenthub_exit_code": int(dict(summary.get("agenthub_run") or {}).get("exit_code") or 0),
        "codex_exit_code": int(dict(summary.get("codex_run") or {}).get("exit_code") or 0),
        "agenthub_elapsed_seconds": float(dict(summary.get("agenthub_run") or {}).get("elapsed_seconds") or 0),
        "codex_elapsed_seconds": float(dict(summary.get("codex_run") or {}).get("elapsed_seconds") or 0),
        "codex_provider_id": str(summary.get("codex_provider_id") or "").strip(),
        "codex_bin": str(summary.get("codex_bin") or "").strip(),
        "agenthub_assistant_text": str(summary.get("agenthub_assistant_text") or "").strip(),
        "codex_assistant_text": str(summary.get("codex_assistant_text") or "").strip(),
        "layer_summary": dict(summary.get("layer_summary") or {}),
        "log_manifest": dict(summary.get("log_manifest") or {}),
    }


def _run_attempt(
    *,
    case: CaseSpec,
    attempt_dir: Path,
    provider: str,
    model: str,
    reasoning_effort: str,
    openai_base_url: str,
    interaction_profile: str,
    codex_provider_id: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = attempt_dir / "prompt.txt"
    prompt_path.write_text(case.prompt + "\n", encoding="utf-8")
    command = [
        sys.executable,
        str(HARNESS_PATH),
        "--prompt-file",
        str(prompt_path),
        "--out-dir",
        str(attempt_dir),
        "--provider",
        provider,
        "--model",
        model,
        "--reasoning-effort",
        reasoning_effort,
        "--openai-base-url",
        openai_base_url,
        "--codex-config-mode",
        "ephemeral",
        "--agenthub-config-mode",
        "project_local",
        "--agenthub-interaction-profile",
        interaction_profile,
        "--codex-provider-id",
        codex_provider_id,
        "--timeout-seconds",
        str(timeout_seconds),
    ]
    if case.validate:
        command.extend(["--validate", case.validate])
    started_at = _now_iso()
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    ended_at = _now_iso()
    (attempt_dir / "runner.command.txt").write_text(shlex.join(command) + "\n", encoding="utf-8")
    (attempt_dir / "runner.stdout.log").write_text(result.stdout, encoding="utf-8")
    (attempt_dir / "runner.stderr.log").write_text(result.stderr, encoding="utf-8")
    summary = _read_json(attempt_dir / "summary.json")
    if not isinstance(summary, dict):
        summary = {}
    provider_used = _agenthub_provider_used(attempt_dir)
    return {
        "attempt_dir": str(attempt_dir),
        "started_at": started_at,
        "ended_at": ended_at,
        "runner_exit_code": int(result.returncode),
        "provider_used": provider_used,
        "summary_present": bool(summary),
        "summary_excerpt": _summary_excerpt(summary),
        "agenthub_files": _workspace_inventory(attempt_dir, "agenthub"),
        "codex_files": _workspace_inventory(attempt_dir, "codex"),
    }


def _layer_path(case_result: dict[str, Any], key: str) -> str:
    log_manifest = dict(case_result.get("log_manifest") or {})
    return str(log_manifest.get(key) or "").strip()


def _bool_text(value: Any) -> str:
    return "yes" if bool(value) else "no"


def _case_markdown(case_result: dict[str, Any]) -> list[str]:
    layer_summary = dict(case_result.get("layer_summary") or {})
    request_raw = dict(layer_summary.get("request_raw") or {})
    tool_schema = dict(layer_summary.get("tool_schema") or {})
    tool_call_chain = dict(layer_summary.get("tool_call_chain") or {})
    workspace_side_effects = dict(layer_summary.get("workspace_side_effects") or {})
    lines = [
        f"## {case_result['name']}",
        "",
        f"- prompt: {case_result['prompt']}",
        f"- attempts_used: {case_result['attempts_used']}",
        f"- passed: {'yes' if case_result['passed'] else 'no'}",
        f"- agenthub_provider_used: {'yes' if case_result['agenthub_provider_used'] else 'no'}",
        f"- final_attempt_dir: `{case_result['final_attempt_dir']}`",
        f"- agenthub_elapsed_seconds: {case_result['agenthub_elapsed_seconds']}",
        f"- codex_elapsed_seconds: {case_result['codex_elapsed_seconds']}",
        f"- codex_bin: `{case_result['codex_bin'] or '-'}`",
        f"- agenthub_files: {', '.join(case_result['agenthub_files']) if case_result['agenthub_files'] else '-'}",
        f"- codex_files: {', '.join(case_result['codex_files']) if case_result['codex_files'] else '-'}",
        "",
        "### Layer 1 Request Raw",
        "",
        f"- layer_file: `{_layer_path(case_result, 'layer_request_raw') or '-'}`",
        f"- instructions_equal: {_bool_text(request_raw.get('instructions_equal'))}",
        f"- input_equal: {_bool_text(request_raw.get('input_equal'))}",
        f"- tools_equal: {_bool_text(request_raw.get('tools_equal'))}",
        f"- model_equal: {_bool_text(request_raw.get('model_equal'))}",
        f"- reasoning_equal: {_bool_text(request_raw.get('reasoning_equal'))}",
        f"- prompt_cache_key_present_equal: {_bool_text(request_raw.get('prompt_cache_key_present_equal'))}",
        f"- prompt_cache_key_shape_equal: {_bool_text(request_raw.get('prompt_cache_key_shape_equal'))}",
        "",
        "### Layer 2 Tool Schema",
        "",
        f"- layer_file: `{_layer_path(case_result, 'layer_tool_schema') or '-'}`",
        f"- agenthub_tool_count: {tool_schema.get('agenthub_tool_count', '-')}",
        f"- codex_tool_count: {tool_schema.get('codex_tool_count', '-')}",
        f"- agenthub_only: {tool_schema.get('agenthub_only') or []}",
        f"- codex_only: {tool_schema.get('codex_only') or []}",
        f"- shared_different_schema: {tool_schema.get('shared_different_schema') or []}",
        "",
        "### Layer 3 Tool Call Chain",
        "",
        f"- layer_file: `{_layer_path(case_result, 'layer_tool_call_chain') or '-'}`",
        f"- tool_name_sequence_equal: {_bool_text(tool_call_chain.get('tool_name_sequence_equal'))}",
        f"- common_prefix_len: {tool_call_chain.get('common_prefix_len', '-')}",
        f"- agenthub_tool_names: {tool_call_chain.get('agenthub_tool_names') or []}",
        f"- codex_tool_names: {tool_call_chain.get('codex_tool_names') or []}",
        "",
        "### Layer 4 Workspace Side Effects",
        "",
        f"- layer_file: `{_layer_path(case_result, 'layer_workspace_side_effects') or '-'}`",
        f"- all_files_equal: {_bool_text(workspace_side_effects.get('all_files_equal'))}",
        f"- visible_files_equal: {_bool_text(workspace_side_effects.get('visible_files_equal'))}",
        f"- agenthub_only_all_paths: {workspace_side_effects.get('agenthub_only_all_paths') or []}",
        f"- codex_only_all_paths: {workspace_side_effects.get('codex_only_all_paths') or []}",
        "",
        "### Answers",
        "",
        f"- AgentHub: {case_result['agenthub_assistant_text'] or '-'}",
        f"- Codex: {case_result['codex_assistant_text'] or '-'}",
        "",
    ]
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    resolved_model, resolved_reasoning_effort = resolve_model_and_reasoning_settings(
        provider=str(args.provider),
        model=str(args.model or ""),
        reasoning_effort=str(args.reasoning_effort or ""),
        catalog_cwd=CLI_ROOT,
        interaction_profile=str(args.agenthub_interaction_profile or ""),
    )
    selected_cases = _selected_cases(args.cases)
    if not selected_cases:
        parser.error("no matching cases selected")

    out_root = (
        Path(args.out_root).resolve()
        if str(args.out_root or "").strip()
        else Path(tempfile.mkdtemp(prefix="agenthub_openai_codex_ab_", dir="/tmp"))
    )
    out_root.mkdir(parents=True, exist_ok=True)

    case_results: list[dict[str, Any]] = []
    for case in selected_cases:
        case_root = out_root / case.name
        attempts: list[dict[str, Any]] = []
        chosen_attempt: dict[str, Any] | None = None
        for attempt_index in range(1, max(int(args.retry_attempts), 1) + 1):
            attempt_dir = case_root / f"attempt_{attempt_index:02d}"
            attempt_result = _run_attempt(
                case=case,
                attempt_dir=attempt_dir,
                provider=str(args.provider),
                model=resolved_model,
                reasoning_effort=resolved_reasoning_effort,
                openai_base_url=str(args.openai_base_url),
                interaction_profile=str(args.agenthub_interaction_profile),
                codex_provider_id=str(args.codex_provider_id),
                timeout_seconds=int(args.timeout_seconds),
            )
            attempts.append(attempt_result)
            summary_excerpt = dict(attempt_result.get("summary_excerpt") or {})
            runner_exit_code = int(attempt_result.get("runner_exit_code") or 0)
            agenthub_exit_code = int(summary_excerpt.get("agenthub_exit_code") or 0)
            codex_exit_code = int(summary_excerpt.get("codex_exit_code") or 0)
            if runner_exit_code == 0 and agenthub_exit_code == 0 and codex_exit_code == 0 and attempt_result["provider_used"]:
                chosen_attempt = attempt_result
                break
            chosen_attempt = attempt_result

        assert chosen_attempt is not None
        summary_excerpt = dict(chosen_attempt.get("summary_excerpt") or {})
        case_results.append(
            {
                "name": case.name,
                "prompt": case.prompt,
                "validate": case.validate,
                "attempts_used": len(attempts),
                "attempts": attempts,
                "passed": bool(
                    int(chosen_attempt.get("runner_exit_code") or 0) == 0
                    and int(summary_excerpt.get("agenthub_exit_code") or 0) == 0
                    and int(summary_excerpt.get("codex_exit_code") or 0) == 0
                    and chosen_attempt.get("provider_used")
                ),
                "agenthub_provider_used": bool(chosen_attempt.get("provider_used")),
                "final_attempt_dir": str(chosen_attempt.get("attempt_dir") or ""),
                "agenthub_elapsed_seconds": summary_excerpt.get("agenthub_elapsed_seconds"),
                "codex_elapsed_seconds": summary_excerpt.get("codex_elapsed_seconds"),
                "codex_provider_id": str(summary_excerpt.get("codex_provider_id") or "").strip(),
                "codex_bin": str(summary_excerpt.get("codex_bin") or "").strip(),
                "agenthub_assistant_text": str(summary_excerpt.get("agenthub_assistant_text") or "").strip(),
                "codex_assistant_text": str(summary_excerpt.get("codex_assistant_text") or "").strip(),
                "agenthub_files": list(chosen_attempt.get("agenthub_files") or []),
                "codex_files": list(chosen_attempt.get("codex_files") or []),
                "layer_summary": dict(summary_excerpt.get("layer_summary") or {}),
                "log_manifest": dict(summary_excerpt.get("log_manifest") or {}),
            }
        )

    report = {
        "generated_at": _now_iso(),
        "out_root": str(out_root),
        "provider": str(args.provider),
        "model": resolved_model,
        "reasoning_effort": resolved_reasoning_effort,
        "openai_base_url": str(args.openai_base_url),
        "agenthub_interaction_profile": str(args.agenthub_interaction_profile),
        "codex_provider_id": (
            next(
                (
                    str(item.get("codex_provider_id") or "").strip()
                    for item in case_results
                    if str(item.get("codex_provider_id") or "").strip()
                ),
                str(args.codex_provider_id or "").strip(),
            )
        ),
        "retry_attempts": int(args.retry_attempts),
        "timeout_seconds": int(args.timeout_seconds),
        "cases": case_results,
        "passed": all(bool(item.get("passed")) for item in case_results),
    }
    report_path = out_root / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md_lines = [
        f"# OpenAI {report['model']} Codex-vs-AgentHub A/B Report",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- out_root: `{report['out_root']}`",
        f"- provider: `{report['provider']}`",
        f"- model: `{report['model']}`",
        f"- reasoning_effort: `{report['reasoning_effort']}`",
        f"- interaction_profile: `{report['agenthub_interaction_profile']}`",
        f"- codex_provider_id: `{report['codex_provider_id'] or 'auto'}`",
        f"- codex_bin: `{next((item.get('codex_bin') for item in case_results if item.get('codex_bin')), '-')}`",
        f"- passed: {'yes' if report['passed'] else 'no'}",
        "",
    ]
    for case_result in case_results:
        md_lines.extend(_case_markdown(case_result))
    report_md_path = out_root / "report.md"
    report_md_path.write_text("\n".join(md_lines).strip() + "\n", encoding="utf-8")

    print(json.dumps({"out_root": str(out_root), "report_json": str(report_path), "report_md": str(report_md_path)}, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
