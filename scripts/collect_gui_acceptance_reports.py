#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _load_report(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect GUI acceptance reports into one suite summary.")
    parser.add_argument("--report-dir", required=True, help="Directory containing individual GUI acceptance JSON reports.")
    parser.add_argument("--output", required=True, help="Path to write the suite summary JSON.")
    args = parser.parse_args()

    report_dir = Path(args.report_dir).resolve()
    output_path = Path(args.output).resolve()

    report_items: list[dict] = []
    for path in sorted(report_dir.glob("*.json")):
        if path.resolve() == output_path:
            continue
        payload = _load_report(path)
        report_items.append(
            {
                "file": path.name,
                "scenario": str(payload.get("scenario") or path.stem),
                "pass": bool(payload.get("pass")),
                "executed_at": str(payload.get("executed_at") or ""),
                "failure_category": payload.get("failure_category"),
                "failure_detail": payload.get("failure_detail"),
                "report": payload,
            }
        )

    summary = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "report_dir": str(report_dir),
        "report_count": len(report_items),
        "pass_count": sum(1 for item in report_items if item["pass"]),
        "fail_count": sum(1 for item in report_items if not item["pass"]),
        "passed": bool(report_items) and all(item["pass"] for item in report_items),
        "reports": report_items,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
