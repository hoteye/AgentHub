from __future__ import annotations

import json
from pathlib import Path

from cli.scripts import quality_size_guard


def test_count_lines_counts_physical_lines_with_utf8_ignore_mode(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_bytes(b"alpha = 1\n\xffbroken\nomega = 2\n")

    lines = quality_size_guard.count_lines(target)

    assert lines == 3


def test_load_baseline_reads_allow_over_hard_mapping_only(tmp_path: Path) -> None:
    baseline = tmp_path / "size_guard_baseline.json"
    payload = {
        "hard_limit": 500,
        "allow_over_hard": {
            "cli/agent_cli/runtime.py": 900,
            "cli/agent_cli/runtime_core/demo.py": 520,
        },
        "notes": {"owner": "quality"},
    }
    baseline.write_text(json.dumps(payload), encoding="utf-8")

    loaded = quality_size_guard.load_baseline(baseline)

    assert loaded == payload["allow_over_hard"]
    assert "notes" not in loaded
