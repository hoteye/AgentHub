from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any


def _summarize_case(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    successes = [item for item in attempts if bool((item.get("result") or {}).get("http_ok"))]
    classifications = [dict((item.get("result") or {}).get("classification") or {}) for item in successes]
    elapsed = [int((item.get("result") or {}).get("elapsed_ms") or 0) for item in successes]
    output_lengths = [int(classification.get("output_len") or 0) for classification in classifications]
    short_examples = [
        str(classification.get("output_text") or "").strip()
        for classification in classifications
        if classification.get("short_no_web")
    ]
    web_examples = [
        str(classification.get("output_text") or "").strip()
        for classification in classifications
        if int(classification.get("web_search_count") or 0) > 0
    ]
    return {
        "n": len(attempts),
        "http_ok": len(successes),
        "with_web": sum(1 for classification in classifications if int(classification.get("web_search_count") or 0) > 0),
        "short_no_web": sum(1 for classification in classifications if bool(classification.get("short_no_web"))),
        "weather_answer_like": sum(1 for classification in classifications if bool(classification.get("weather_answer_like"))),
        "avg_elapsed_ms": round(statistics.mean(elapsed), 1) if elapsed else 0.0,
        "avg_output_len": round(statistics.mean(output_lengths), 1) if output_lengths else 0.0,
        "short_example": short_examples[0] if short_examples else "",
        "web_example": web_examples[0] if web_examples else "",
    }


def _write_markdown_report(
    *,
    out_dir: Path,
    summary: dict[str, Any],
    runs_per_case: int,
    timeout_seconds: float,
) -> Path:
    report_path = out_dir / "report.md"
    lines = [
        "# Weather Header/Tool Mixed Replay",
        "",
        "## Scope",
        "",
        "- prompt family: `北京明天天气怎么样？`",
        "- provider/model path: `openai / gpt-5.4 / responses`",
        f"- runs per case: `{runs_per_case}`",
        f"- timeout seconds: `{timeout_seconds}`",
        "- metric notes:",
        "  - `with_web`: response contained provider-native `web_search_call`",
        "  - `short_no_web`: no `web_search_call` and final text length <= 120 chars",
        "  - `weather_answer_like`: weather-detail answer proxy for this fixed Beijing-weather prompt",
        "",
        "## Matrix Summary",
        "",
        "| Case | HTTP OK | with_web | weather_answer_like | short_no_web | avg_elapsed_ms | avg_output_len |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, payload in summary.items():
        lines.append(
            f"| `{label}` | {payload['http_ok']}/{payload['n']} | {payload['with_web']}/{payload['http_ok'] or payload['n']} | "
            f"{payload['weather_answer_like']}/{payload['http_ok'] or payload['n']} | "
            f"{payload['short_no_web']}/{payload['http_ok'] or payload['n']} | {payload['avg_elapsed_ms']} | {payload['avg_output_len']} |"
        )
    lines.extend(
        [
            "",
            "## Case Notes",
            "",
        ]
    )
    for label, payload in summary.items():
        lines.append(f"### `{label}`")
        lines.append("")
        if payload.get("short_example"):
            lines.append(f"- short example: `{payload['short_example']}`")
        if payload.get("web_example"):
            lines.append(f"- web example: `{payload['web_example']}`")
        if not payload.get("short_example") and not payload.get("web_example"):
            lines.append("- no successful sample text captured")
        lines.append("")
    report_path.write_text("\n".join(lines) + "\n")
    return report_path
