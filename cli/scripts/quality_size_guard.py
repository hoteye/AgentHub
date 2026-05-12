from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="File size guard for python modules.")
    parser.add_argument("--root", default="cli/agent_cli", help="Root directory to scan.")
    parser.add_argument("--soft", type=int, default=350, help="Soft line limit.")
    parser.add_argument("--hard", type=int, default=500, help="Hard line limit.")
    parser.add_argument(
        "--baseline",
        default="cli/scripts/size_guard_baseline.json",
        help="Baseline json path for temporary hard-limit allowlist.",
    )
    return parser.parse_args()


def count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        return sum(1 for _ in handle)


def load_baseline(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return dict(data.get("allow_over_hard", {}))


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    baseline_path = Path(args.baseline)

    if not root.exists():
        print(f"[size-guard] root not found: {root}")
        return 2

    allow_over_hard = load_baseline(baseline_path)
    files = sorted(root.rglob("*.py"))
    counts: list[tuple[int, Path]] = [(count_lines(path), path) for path in files]

    soft_hits = [(lines, path) for lines, path in counts if lines > args.soft]
    hard_hits = [(lines, path) for lines, path in counts if lines > args.hard]

    print(
        f"[size-guard] scanned={len(counts)} soft_limit={args.soft} hard_limit={args.hard}"
    )
    print(
        f"[size-guard] soft_violations={len(soft_hits)} hard_violations={len(hard_hits)}"
    )

    if soft_hits:
        print("[size-guard] soft violations (top 20):")
        for lines, path in sorted(soft_hits, reverse=True)[:20]:
            print(f"  {lines:4d} {path.as_posix()}")

    failures: list[str] = []
    for lines, path in hard_hits:
        key = path.as_posix()
        allowed = allow_over_hard.get(key)
        if allowed is None:
            failures.append(
                f"{key} has {lines} lines (> {args.hard}) and is not in baseline allowlist"
            )
            continue
        if lines > allowed:
            failures.append(
                f"{key} has {lines} lines, exceeds baseline cap {allowed} (hard {args.hard})"
            )

    if failures:
        print("[size-guard] hard gate failed:")
        for failure in failures:
            print(f"  - {failure}")
        print("[size-guard] hint: split file or tighten baseline intentionally.")
        return 1

    print("[size-guard] pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
