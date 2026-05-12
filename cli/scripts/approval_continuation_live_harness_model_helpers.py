from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class LiveCase:
    name: str
    tool_name: str
    decision: str
    target_file: str
    expected_content: str
    model_override: str = ""


DEFAULT_CASES: tuple[LiveCase, ...] = (
    LiveCase(
        name="approve_exec_command",
        tool_name="exec_command",
        decision="approve",
        target_file="approval_live_approve.txt",
        expected_content="approval-approved",
    ),
    LiveCase(
        name="reject_exec_command",
        tool_name="exec_command",
        decision="reject",
        target_file="approval_live_reject.txt",
        expected_content="approval-rejected",
    ),
    LiveCase(
        name="approve_apply_patch",
        tool_name="apply_patch",
        decision="approve",
        target_file="approval_patch_approve.txt",
        expected_content="approval-patch-approved",
    ),
    LiveCase(
        name="reject_apply_patch",
        tool_name="apply_patch",
        decision="reject",
        target_file="approval_patch_reject.txt",
        expected_content="approval-patch-rejected",
    ),
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _default_out_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="approval_continuation_live_")).resolve()


def _selected_cases(names: list[str]) -> list[LiveCase]:
    if not names:
        return list(DEFAULT_CASES)
    selected: list[LiveCase] = []
    available = {case.name: case for case in DEFAULT_CASES}
    for name in names:
        if name not in available:
            raise SystemExit(f"unknown case `{name}`; available: {', '.join(sorted(available))}")
        selected.append(available[name])
    return selected
