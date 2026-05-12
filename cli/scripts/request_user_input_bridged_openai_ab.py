#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_PROMPT = (
    "Use the request_user_input tool exactly once to ask me which plan I prefer. "
    "Ask one question with id preference, header Choose, question Which plan should I use?, "
    "and two options: Plan A (Recommended) and Plan B. "
    "After the tool returns, respond in Chinese with exactly 收到：<choice>. "
    "Do not ask in plain text."
)


try:
    from cli.scripts.request_user_input_bridged_openai_ab_process_helpers import (
        run_agenthub_probe,
        run_codex_probe,
    )
    from cli.scripts.request_user_input_bridged_openai_ab_projection_helpers import (
        _completed_status,
        _final_answer_summary,
        _is_completed,
        _is_missing_turn_completed_after_final_answer,
        _parity_verdict,
        _public_request_shape,
        _turn_completion_outcome,
    )
    from cli.scripts.request_user_input_bridged_openai_ab_provider_helpers import (
        _agenthub_config,
        _codex_config,
    )
    from cli.scripts.request_user_input_bridged_openai_ab_reporting_helpers import (
        build_aggregate_summary,
        build_summary,
    )
    from cli.scripts.request_user_input_bridged_openai_ab_runtime_helpers import (
        ProbeResult,
        _json_line,
        _read_message,
        _read_post_answer_until_completed,
        _read_until,
        _send,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from request_user_input_bridged_openai_ab_process_helpers import (  # type: ignore[no-redef]
        run_agenthub_probe,
        run_codex_probe,
    )
    from request_user_input_bridged_openai_ab_projection_helpers import (  # type: ignore[no-redef]
        _completed_status,
        _final_answer_summary,
        _is_completed,
        _is_missing_turn_completed_after_final_answer,
        _parity_verdict,
        _public_request_shape,
        _turn_completion_outcome,
    )
    from request_user_input_bridged_openai_ab_provider_helpers import (  # type: ignore[no-redef]
        _agenthub_config,
        _codex_config,
    )
    from request_user_input_bridged_openai_ab_reporting_helpers import (  # type: ignore[no-redef]
        build_aggregate_summary,
        build_summary,
    )
    from request_user_input_bridged_openai_ab_runtime_helpers import (  # type: ignore[no-redef]
        ProbeResult,
        _json_line,
        _read_message,
        _read_post_answer_until_completed,
        _read_until,
        _send,
    )


def run_once(
    *,
    out_dir: Path,
    repo_root: Path,
    codex_bin: Path,
    agenthub_auth: Path,
    codex_auth: Path,
    prompt: str,
    answer: str,
    base_url: str,
    model: str,
    effort: str,
    completion_timeout: float,
) -> dict[str, Any]:
    agenthub = run_agenthub_probe(
        out_dir=out_dir,
        repo_root=repo_root,
        auth_src=agenthub_auth,
        prompt=prompt,
        answer=answer,
        base_url=base_url,
        model=model,
        effort=effort,
        completion_timeout=completion_timeout,
    )
    codex = run_codex_probe(
        out_dir=out_dir,
        repo_root=repo_root,
        codex_bin=codex_bin,
        auth_src=codex_auth,
        prompt=prompt,
        answer=answer,
        base_url=base_url,
        model=model,
        effort=effort,
        completion_timeout=completion_timeout,
    )
    summary = build_summary(
        agenthub,
        codex,
        prompt=prompt,
        answer=answer,
        base_url=base_url,
        model=model,
        effort=effort,
    )
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a live bridged request_user_input A/B: AgentHub OpenAI vs codex_ref app-server.")
    parser.add_argument("--repo-root", default="/home/lyc/project/AgentHub")
    parser.add_argument("--codex-bin", default="/home/lyc/project/AgentHubRef/codex_ref/codex-rs/target/debug/codex")
    parser.add_argument("--agenthub-auth", default="/home/lyc/project/AgentHub/cli/.config/auth.json")
    parser.add_argument("--codex-auth", default="~/.codex/auth.json")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--base-url", default="https://relay03.gaccode.com/codex/v1")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--effort", default="xhigh")
    parser.add_argument("--completion-timeout", type=float, default=60.0)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--answer", default="Plan B")
    parser.add_argument("--runs", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    codex_bin = Path(args.codex_bin).resolve()
    agenthub_auth = Path(args.agenthub_auth).expanduser().resolve()
    codex_auth = Path(args.codex_auth).expanduser().resolve()
    out_dir = (
        Path(args.out_dir).resolve()
        if str(args.out_dir or "").strip()
        else Path(tempfile.mkdtemp(prefix="request_user_input_bridged_ab_"))
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.runs < 1:
        raise SystemExit("--runs must be >= 1")
    if args.runs == 1:
        summary = run_once(
            out_dir=out_dir,
            repo_root=repo_root,
            codex_bin=codex_bin,
            agenthub_auth=agenthub_auth,
            codex_auth=codex_auth,
            prompt=args.prompt,
            answer=args.answer,
            base_url=args.base_url,
            model=args.model,
            effort=args.effort,
            completion_timeout=args.completion_timeout,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    run_summaries: list[dict[str, Any]] = []
    run_records: list[dict[str, Any]] = []
    for run_index in range(1, args.runs + 1):
        run_dir = out_dir / f"run_{run_index:02d}"
        run_dir.mkdir(parents=True, exist_ok=True)
        summary = run_once(
            out_dir=run_dir,
            repo_root=repo_root,
            codex_bin=codex_bin,
            agenthub_auth=agenthub_auth,
            codex_auth=codex_auth,
            prompt=args.prompt,
            answer=args.answer,
            base_url=args.base_url,
            model=args.model,
            effort=args.effort,
            completion_timeout=args.completion_timeout,
        )
        run_summaries.append(summary)
        run_records.append(
            {
                "run": run_index,
                "summary_path": str(run_dir / "summary.json"),
                "comparison": summary.get("comparison"),
            }
        )
    aggregate_summary = {
        "prompt": args.prompt,
        "answer": args.answer,
        "base_url": args.base_url,
        "model": args.model,
        "effort": args.effort,
        "runs": args.runs,
        "aggregate": build_aggregate_summary(run_summaries),
        "run_summaries": run_records,
    }
    aggregate_path = out_dir / "summary.json"
    aggregate_path.write_text(json.dumps(aggregate_summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(aggregate_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
