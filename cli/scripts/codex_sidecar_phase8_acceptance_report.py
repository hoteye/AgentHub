from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

CheckStatus = Literal["pass", "fail", "skip"]


@dataclass(slots=True)
class CheckResult:
    name: str
    status: CheckStatus
    duration_seconds: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    command: list[str] = field(default_factory=list)
    stdout_tail: list[str] = field(default_factory=list)
    stderr_tail: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in {"pass", "skip"}


def write_report(path: Path, results: list[CheckResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "overall_status": "pass" if all(result.ok for result in results) else "fail",
        "results": [asdict(result) for result in results],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _skip(name: str, reason: str) -> CheckResult:
    return CheckResult(name=name, status="skip", details={"reason": reason})


def _tail_lines(text: str, *, limit: int = 40) -> list[str]:
    return str(text or "").splitlines()[-limit:]


def print_results(results: list[CheckResult]) -> None:
    for result in results:
        prefix = result.status.upper()
        line = f"{prefix} {result.name}"
        if result.duration_seconds:
            line += f" ({result.duration_seconds:.3f}s)"
        if result.error:
            line += f": {result.error}"
        elif result.status == "skip":
            reason = str(result.details.get("reason") or "").strip()
            if reason:
                line += f": {reason}"
        print(line)
