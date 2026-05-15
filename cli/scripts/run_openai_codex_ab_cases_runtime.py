from __future__ import annotations

import json
import shlex
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CLI_ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = CLI_ROOT / "scripts" / "benchmark_emptydir_ab.py"


def _selected_cases(requested_names: list[str] | None, cases: Sequence[Any]) -> list[Any]:
    if not requested_names:
        return list(cases)
    wanted = {str(name or "").strip() for name in requested_names if str(name or "").strip()}
    return [case for case in cases if case.name in wanted]


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
        "agenthub_elapsed_seconds": float(
            dict(summary.get("agenthub_run") or {}).get("elapsed_seconds") or 0
        ),
        "codex_elapsed_seconds": float(
            dict(summary.get("codex_run") or {}).get("elapsed_seconds") or 0
        ),
        "codex_provider_id": str(summary.get("codex_provider_id") or "").strip(),
        "codex_bin": str(summary.get("codex_bin") or "").strip(),
        "agenthub_assistant_text": str(summary.get("agenthub_assistant_text") or "").strip(),
        "codex_assistant_text": str(summary.get("codex_assistant_text") or "").strip(),
        "layer_summary": dict(summary.get("layer_summary") or {}),
        "log_manifest": dict(summary.get("log_manifest") or {}),
    }


def _run_attempt(
    *,
    case: Any,
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


def run_case_attempts(
    *,
    selected_cases: Sequence[Any],
    out_root: Path,
    provider: str,
    model: str,
    reasoning_effort: str,
    openai_base_url: str,
    interaction_profile: str,
    codex_provider_id: str,
    retry_attempts: int,
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    case_results: list[dict[str, Any]] = []
    for case in selected_cases:
        case_root = out_root / case.name
        attempts: list[dict[str, Any]] = []
        chosen_attempt: dict[str, Any] | None = None
        for attempt_index in range(1, max(int(retry_attempts), 1) + 1):
            attempt_dir = case_root / f"attempt_{attempt_index:02d}"
            attempt_result = _run_attempt(
                case=case,
                attempt_dir=attempt_dir,
                provider=provider,
                model=model,
                reasoning_effort=reasoning_effort,
                openai_base_url=openai_base_url,
                interaction_profile=interaction_profile,
                codex_provider_id=codex_provider_id,
                timeout_seconds=timeout_seconds,
            )
            attempts.append(attempt_result)
            summary_excerpt = dict(attempt_result.get("summary_excerpt") or {})
            runner_exit_code = int(attempt_result.get("runner_exit_code") or 0)
            agenthub_exit_code = int(summary_excerpt.get("agenthub_exit_code") or 0)
            codex_exit_code = int(summary_excerpt.get("codex_exit_code") or 0)
            if (
                runner_exit_code == 0
                and agenthub_exit_code == 0
                and codex_exit_code == 0
                and attempt_result["provider_used"]
            ):
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
                "agenthub_assistant_text": str(
                    summary_excerpt.get("agenthub_assistant_text") or ""
                ).strip(),
                "codex_assistant_text": str(
                    summary_excerpt.get("codex_assistant_text") or ""
                ).strip(),
                "agenthub_files": list(chosen_attempt.get("agenthub_files") or []),
                "codex_files": list(chosen_attempt.get("codex_files") or []),
                "layer_summary": dict(summary_excerpt.get("layer_summary") or {}),
                "log_manifest": dict(summary_excerpt.get("log_manifest") or {}),
            }
        )
    return case_results


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


def build_report(
    *,
    out_root: Path,
    provider: str,
    model: str,
    reasoning_effort: str,
    openai_base_url: str,
    agenthub_interaction_profile: str,
    codex_provider_id: str,
    retry_attempts: int,
    timeout_seconds: int,
    case_results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "generated_at": _now_iso(),
        "out_root": str(out_root),
        "provider": provider,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "openai_base_url": openai_base_url,
        "agenthub_interaction_profile": agenthub_interaction_profile,
        "codex_provider_id": (
            next(
                (
                    str(item.get("codex_provider_id") or "").strip()
                    for item in case_results
                    if str(item.get("codex_provider_id") or "").strip()
                ),
                str(codex_provider_id or "").strip(),
            )
        ),
        "retry_attempts": retry_attempts,
        "timeout_seconds": timeout_seconds,
        "cases": case_results,
        "passed": all(bool(item.get("passed")) for item in case_results),
    }


def write_report_files(*, report: dict[str, Any], out_root: Path) -> tuple[Path, Path]:
    report_path = out_root / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    case_results = list(report["cases"])
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
    return report_path, report_md_path


__all__ = (
    "HARNESS_PATH",
    "_agenthub_provider_used",
    "_bool_text",
    "_case_markdown",
    "_layer_path",
    "_now_iso",
    "_read_json",
    "_run_attempt",
    "_selected_cases",
    "_summary_excerpt",
    "_workspace_inventory",
    "build_report",
    "run_case_attempts",
    "write_report_files",
)
