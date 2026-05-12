from __future__ import annotations

import argparse
import io
import json
import sys
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence, TextIO

from cli.agent_cli.main import main as agenthub_main

from .real_cases import list_real_case_ids, load_real_case_cassette
from .runtime_replay import build_runtime_for_replay, recorded_user_prompt
from .schema import ReplayCassette


@dataclass
class HeadlessReplayTurnResult:
    turn_index: int
    prompt: str
    exit_code: int
    stdout_text: str
    stderr_text: str
    json_payload: dict[str, Any] | None = None
    jsonl_events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.json_payload or {})
        return {
            "turn_index": self.turn_index,
            "prompt": self.prompt,
            "exit_code": self.exit_code,
            "assistant_text": str(payload.get("assistant_text") or ""),
            "commentary_text": str(payload.get("commentary_text") or ""),
            "stderr_text": self.stderr_text,
            "status": dict(payload.get("status") or {}),
            "response_items": list(payload.get("response_items") or []),
            "tool_events": list(payload.get("tool_events") or []),
            "turn_events": list(payload.get("turn_events") or []),
            "stdout_text": self.stdout_text if not payload else "",
        }


def _normalize_turn_indices(
    cassette: ReplayCassette,
    turn_indices: Sequence[int] | None,
) -> set[int]:
    all_indices = {int(round_item.index) for round_item in list(cassette.rounds or [])}
    if not turn_indices:
        return all_indices
    normalized = {int(item) for item in turn_indices if int(item) > 0}
    unknown = sorted(normalized.difference(all_indices))
    if unknown:
        raise ValueError(f"unknown turn indices: {unknown}")
    return normalized


def run_headless_replay_case(
    cassette: ReplayCassette,
    *,
    output_format: str = "json",
    turn_indices: Sequence[int] | None = None,
    approval_policy: str = "never",
    sandbox_mode: str | None = None,
) -> list[HeadlessReplayTurnResult]:
    mode = str(output_format or "json").strip().lower()
    if mode not in {"text", "json", "jsonl"}:
        raise ValueError(f"unsupported output_format: {output_format!r}")

    selected_turns = _normalize_turn_indices(cassette, turn_indices)
    runtime = build_runtime_for_replay(cassette)
    results: list[HeadlessReplayTurnResult] = []

    for round_item in list(cassette.rounds or []):
        prompt = recorded_user_prompt(round_item)
        argv = [
            "--headless",
            "--prompt",
            prompt,
            "--approval-policy",
            str(approval_policy or "never"),
        ]
        if str(sandbox_mode or "").strip():
            argv.extend(["--sandbox-mode", str(sandbox_mode).strip()])
        if mode == "json":
            argv.append("--json")
        elif mode == "jsonl":
            argv.append("--jsonl")
        if int(round_item.index or 0) > 1 and str(runtime.thread_id or "").strip():
            argv.extend(["--resume", str(runtime.thread_id)])

        stdout = io.StringIO()
        stderr = io.StringIO()
        exit_code = agenthub_main(
            argv,
            runtime=runtime,
            stdout=stdout,
            stderr=stderr,
        )
        stdout_text = stdout.getvalue()
        stderr_text = stderr.getvalue()
        json_payload = json.loads(stdout_text) if mode == "json" and stdout_text.strip() else None
        jsonl_events = (
            [json.loads(line) for line in stdout_text.splitlines() if line.strip()]
            if mode == "jsonl"
            else []
        )

        if int(round_item.index or 0) in selected_turns:
            results.append(
                HeadlessReplayTurnResult(
                    turn_index=int(round_item.index or 0),
                    prompt=prompt,
                    exit_code=exit_code,
                    stdout_text=stdout_text,
                    stderr_text=stderr_text,
                    json_payload=json_payload,
                    jsonl_events=jsonl_events,
                )
            )

    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cli.replay_integration.headless_replay",
        description="Run AgentHub headless against recorded multi-turn replay cassettes.",
    )
    parser.add_argument(
        "--list-cases",
        action="store_true",
        help="list supported real replay case ids and exit",
    )
    parser.add_argument(
        "--case",
        choices=list_real_case_ids(),
        help="formal real replay case id to run",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json", "jsonl"),
        default="json",
        help="headless output format to emit",
    )
    parser.add_argument(
        "--turn",
        type=int,
        action="append",
        help="1-based turn index to return; earlier turns are still replayed internally",
    )
    return parser


def _render_text(results: Iterable[HeadlessReplayTurnResult]) -> str:
    blocks: list[str] = []
    for result in results:
        assistant_text = str((result.json_payload or {}).get("assistant_text") or "").strip()
        if not assistant_text:
            assistant_text = result.stdout_text.strip()
        blocks.append(
            "\n".join(
                [
                    f"Turn {result.turn_index}",
                    f"Prompt: {result.prompt}",
                    f"Exit Code: {result.exit_code}",
                    f"Assistant: {assistant_text}",
                ]
            ).strip()
        )
    return "\n\n".join(blocks).strip()


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.list_cases:
        print("\n".join(list_real_case_ids()), file=output_stream)
        return 0
    if not args.case:
        parser.print_usage(error_stream)
        print("headless replay error: --case is required unless --list-cases is used", file=error_stream)
        return 2

    results = run_headless_replay_case(
        load_real_case_cassette(args.case),
        output_format=args.format,
        turn_indices=args.turn,
    )

    if args.format == "json":
        print(
            json.dumps([result.to_dict() for result in results], ensure_ascii=False, indent=2),
            file=output_stream,
        )
        return 0

    if args.format == "jsonl":
        for result in results:
            output_stream.write(result.stdout_text)
            if result.stdout_text and not result.stdout_text.endswith("\n"):
                output_stream.write("\n")
        return 0

    rendered = _render_text(results)
    if rendered:
        print(rendered, file=output_stream)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
