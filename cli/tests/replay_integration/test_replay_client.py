from __future__ import annotations

from pathlib import Path

import pytest

from cli.agent_cli.providers.adapters.openai_responses import OpenAIResponsesSession
from cli.replay_integration.reference_baseline_logs import (
    ReferenceBaselineTurnLog,
    build_cassette_from_reference_baseline_turn_logs,
)
from cli.replay_integration.replay_client import ReplayMismatchError, ReplayOpenAIClient

ROOT = Path(__file__).resolve().parents[3]


def _resolved_log_root() -> Path:
    base = ROOT / "docs" / "ab_acceptance"
    preferred = base / "reference_logs"
    if preferred.exists():
        return preferred
    candidates = sorted(path for path in base.iterdir() if path.is_dir() and path.name.endswith("_logs"))
    if candidates:
        return candidates[0]
    return preferred

def _state_probe_cassette():
    log_root = _resolved_log_root()
    return build_cassette_from_reference_baseline_turn_logs(
        [
            ReferenceBaselineTurnLog(
                stdout_path=log_root / "20260331_multiturn_state_probe_turn1.stdout.jsonl",
                stderr_path=log_root / "20260331_multiturn_state_probe_turn1.stderr.jsonl",
            ),
            ReferenceBaselineTurnLog(
                stdout_path=log_root / "20260331_multiturn_state_probe_turn2.stdout.jsonl",
                stderr_path=log_root / "20260331_multiturn_state_probe_turn2.stderr.jsonl",
            ),
            ReferenceBaselineTurnLog(
                stdout_path=log_root / "20260331_multiturn_state_probe_turn3.stdout.jsonl",
                stderr_path=log_root / "20260331_multiturn_state_probe_turn3.stderr.jsonl",
            ),
        ],
        name="reference-ref-state-probe",
    )

def test_replay_openai_client_replays_reference_baseline_turns_through_openai_responses_session() -> None:
    cassette = _state_probe_cassette()
    client = ReplayOpenAIClient(cassette)
    first_round = cassette.rounds[0]
    session = OpenAIResponsesSession(
        client=client,
        model=str(first_round.request["model"]),
        instructions=str(first_round.request["instructions"]),
        tool_specs=list(first_round.request.get("tools") or []),
        reasoning_effort="high",
        prompt_cache_key=str(first_round.request.get("prompt_cache_key") or ""),
    )

    observed = []
    for round_item in cassette.rounds:
        result = session.send(
            input_items=list(round_item.request.get("input") or []),
            allow_tools=bool(round_item.request.get("tools")),
            prompt_cache_key=str(round_item.request.get("prompt_cache_key") or "") or None,
        )
        observed.append(result.output_text)

    assert observed == [
        "记住了",
        "张三",
        "你告诉我你叫张三，我回复“记住了”。",
    ]
    assert len(client.responses.requests) == 3

def test_replay_openai_client_rejects_request_shape_drift() -> None:
    cassette = _state_probe_cassette()
    client = ReplayOpenAIClient(cassette)
    first_round = cassette.rounds[0]
    session = OpenAIResponsesSession(
        client=client,
        model=str(first_round.request["model"]),
        instructions=str(first_round.request["instructions"]),
        tool_specs=list(first_round.request.get("tools") or []),
        reasoning_effort="high",
        prompt_cache_key=str(first_round.request.get("prompt_cache_key") or ""),
    )

    with pytest.raises(ReplayMismatchError):
        session.send(
            input_items=[
                {
                    "role": "user",
                    "content": "我叫李四。请只回复“记住了”。",
                }
            ],
            allow_tools=True,
            prompt_cache_key=str(first_round.request.get("prompt_cache_key") or "") or None,
        )
