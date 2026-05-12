from __future__ import annotations

import re
import statistics
from datetime import datetime
from typing import Any


def _common_date_variants(value: datetime) -> tuple[str, ...]:
    year = value.year
    month = value.month
    day = value.day
    return (
        f"{year}年{month}月{day}日",
        f"{year}-{month:02d}-{day:02d}",
        f"{year}-{month}-{day}",
        f"{year}/{month:02d}/{day:02d}",
        f"{year}/{month}/{day}",
        f"{month}月{day}日",
    )


def _contains_expected_date(text: str, expected: datetime) -> bool:
    normalized = re.sub(r"\s+", "", str(text or ""))
    if not normalized:
        return False
    return any(variant in normalized for variant in _common_date_variants(expected))


def turn_payload(*, prompt: str, response: Any, expected_date: datetime) -> dict[str, Any]:
    assistant_text = str(getattr(response, "assistant_text", "") or "")
    timings = dict(getattr(response, "timings", {}) or {})
    status = dict(getattr(response, "status", {}) or {})
    tool_events = list(getattr(response, "tool_events", []) or [])
    return {
        "prompt": prompt,
        "assistant_text": assistant_text,
        "assistant_preview": assistant_text[:200],
        "expected_date": expected_date.date().isoformat(),
        "expected_date_match": _contains_expected_date(assistant_text, expected_date),
        "provider_runtime_state": status.get("provider_runtime_state"),
        "provider_model": status.get("provider_model"),
        "initial_model_ms": timings.get("initial_model_ms"),
        "total_ms": timings.get("total_ms"),
        "planning_rounds": timings.get("planning_rounds"),
        "tool_call_count": timings.get("tool_call_count"),
        "tool_event_count": len(tool_events),
        "tool_names": [str(getattr(item, "name", "") or "") for item in tool_events],
    }


def health_for_case(payload: dict[str, Any]) -> str:
    if payload.get("timeout") or payload.get("parse_error"):
        return "error"
    if payload.get("provider_runtime_state") != "ready":
        return "error"
    turns = list(payload.get("turns") or [])
    if len(turns) != 2:
        return "error"
    if not all(str(item.get("assistant_text") or "").strip() for item in turns):
        return "error"
    if all(bool(item.get("expected_date_match")) for item in turns):
        return "ok"
    return "warning"


def _case_wall_ms(item: dict[str, Any]) -> int | None:
    for key in ("orchestrator_wall_ms", "wall_ms"):
        value = item.get(key)
        if isinstance(value, int):
            return value
    return None


def summary_for_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    ok_count = sum(1 for item in results if item.get("health") == "ok")
    warning_count = sum(1 for item in results if item.get("health") == "warning")
    error_count = sum(1 for item in results if item.get("health") == "error")
    wall_values = [wall_ms for item in results if (wall_ms := _case_wall_ms(item)) is not None]
    ok_rows = [item for item in results if item.get("health") == "ok"]
    fastest_ok_case: dict[str, Any] | None = None
    if ok_rows:
        fastest = min(ok_rows, key=lambda item: _case_wall_ms(item) if _case_wall_ms(item) is not None else 10**9)
        fastest_wall_ms = _case_wall_ms(fastest)
        fastest_ok_case = {
            "provider": str(fastest.get("provider") or ""),
            "model": str(fastest.get("model") or ""),
            "label": f"{str(fastest.get('provider') or '')}:{str(fastest.get('model') or '')}",
            "orchestrator_wall_ms": fastest_wall_ms,
        }
    return {
        "cases": len(results),
        "ok": ok_count,
        "warning": warning_count,
        "error": error_count,
        "avg_case_wall_ms": round(statistics.mean(wall_values), 1) if wall_values else None,
        "fastest_ok_case": fastest_ok_case,
    }


def print_table(results: list[dict[str, Any]]) -> None:
    print("Cases")
    print("case | health | turn1_ms | turn2_ms | total_ms | state | date_check | note")
    print("--- | --- | ---: | ---: | ---: | --- | --- | ---")
    for item in results:
        turns = list(item.get("turns") or [])
        turn1 = turns[0] if len(turns) > 0 else {}
        turn2 = turns[1] if len(turns) > 1 else {}
        date_check = (
            f"{'Y' if turn1.get('expected_date_match') else 'N'}/"
            f"{'Y' if turn2.get('expected_date_match') else 'N'}"
            if turns
            else "-"
        )
        note = ""
        if item.get("timeout"):
            note = "timeout"
        elif item.get("exception"):
            note = str(item.get("exception"))
        elif item.get("parse_error"):
            note = "parse_error"
        elif turn2.get("assistant_preview"):
            note = str(turn2.get("assistant_preview") or "").replace("\n", " ")[:60]
        print(
            f"{item.get('provider')}:{item.get('model')} | "
            f"{item.get('health', '-')} | "
            f"{turn1.get('total_ms', '-')} | "
            f"{turn2.get('total_ms', '-')} | "
            f"{item.get('orchestrator_wall_ms', item.get('wall_ms', '-'))} | "
            f"{item.get('provider_runtime_state', '-')} | "
            f"{date_check} | "
            f"{note}"
        )

    summary = summary_for_results(results)
    print("\nSummary")
    print(f"cases={summary['cases']}")
    print(f"ok={summary['ok']}")
    print(f"warning={summary['warning']}")
    print(f"error={summary['error']}")
    if summary["avg_case_wall_ms"] is not None:
        print(f"avg_case_wall_ms={summary['avg_case_wall_ms']}")
    if isinstance(summary["fastest_ok_case"], dict):
        fastest = summary["fastest_ok_case"]
        print(
            "fastest_ok_case="
            f"{fastest.get('label')} "
            f"({fastest.get('orchestrator_wall_ms')} ms)"
        )
