from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from .schema import ReplayCassette, ReplayManifest, ReplayRound, ReplayToolCall


MANIFEST_FILENAME = "manifest.json"
ROUNDS_FILENAME = "rounds.jsonl"
TOOL_CALLS_FILENAME = "tool_calls.jsonl"


@dataclass(frozen=True)
class ReplayCassettePaths:
    root: Path
    manifest_path: Path
    rounds_path: Path
    tool_calls_path: Path

    @classmethod
    def from_root(cls, root: str | Path) -> "ReplayCassettePaths":
        resolved_root = Path(root).resolve()
        return cls(
            root=resolved_root,
            manifest_path=resolved_root / MANIFEST_FILENAME,
            rounds_path=resolved_root / ROUNDS_FILENAME,
            tool_calls_path=resolved_root / TOOL_CALLS_FILENAME,
        )


def _read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _read_jsonl(path: Path) -> List[dict]:
    records: List[dict] = []
    if not path.exists():
        return records
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"{path} contains a non-object JSONL record")
        records.append(payload)
    return records


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def load_replay_cassette(root: str | Path) -> ReplayCassette:
    paths = ReplayCassettePaths.from_root(root)
    manifest = ReplayManifest.from_dict(_read_json(paths.manifest_path))
    rounds = [ReplayRound.from_dict(item) for item in _read_jsonl(paths.rounds_path)]
    tool_calls = [ReplayToolCall.from_dict(item) for item in _read_jsonl(paths.tool_calls_path)]
    return ReplayCassette(manifest=manifest, rounds=rounds, tool_calls=tool_calls)


def save_replay_cassette(root: str | Path, cassette: ReplayCassette) -> ReplayCassettePaths:
    paths = ReplayCassettePaths.from_root(root)
    _write_json(paths.manifest_path, cassette.manifest.to_dict())
    _write_jsonl(paths.rounds_path, [item.to_dict() for item in list(cassette.rounds or [])])
    _write_jsonl(paths.tool_calls_path, [item.to_dict() for item in list(cassette.tool_calls or [])])
    return paths
