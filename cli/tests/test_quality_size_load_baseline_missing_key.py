from __future__ import annotations

import json
from pathlib import Path

from cli.scripts import quality_size_guard


def test_load_baseline_returns_empty_dict_when_allow_over_hard_key_missing(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "size_guard_baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "meta": {"owner": "test"},
                "some_other_key": {"cli/agent_cli/runtime.py": 600},
            }
        ),
        encoding="utf-8",
    )

    loaded = quality_size_guard.load_baseline(baseline)

    assert loaded == {}
