from __future__ import annotations

import json
from pathlib import Path

from cli.scripts import quality_size_guard


def _repo_baseline_path() -> Path:
    return Path(__file__).resolve().parents[1] / "scripts" / "size_guard_baseline.json"


def test_size_guard_baseline_json_min_contract() -> None:
    baseline_path = _repo_baseline_path()
    data = json.loads(baseline_path.read_text(encoding="utf-8"))

    assert isinstance(data, dict)
    assert isinstance(data.get("hard_limit"), int)
    assert data["hard_limit"] > 0

    allow_over_hard = data.get("allow_over_hard")
    assert isinstance(allow_over_hard, dict)
    assert allow_over_hard
    for key, value in allow_over_hard.items():
        assert isinstance(key, str)
        assert key.endswith(".py")
        assert key.startswith("cli/")
        assert isinstance(value, int)
        assert value > 0


def test_quality_size_guard_load_baseline_consumes_allow_over_hard_only(tmp_path: Path) -> None:
    baseline = tmp_path / "size_guard_baseline.json"
    payload = {
        "hard_limit": 999,
        "allow_over_hard": {
            "cli/agent_cli/runtime.py": 1234,
            "cli/agent_cli/runtime_core/demo.py": 520,
        },
        "other_metadata": {"owner": "quality"},
    }
    baseline.write_text(json.dumps(payload), encoding="utf-8")

    loaded = quality_size_guard.load_baseline(baseline)

    assert loaded == payload["allow_over_hard"]
    assert "other_metadata" not in loaded


def test_quality_size_guard_load_baseline_missing_file_returns_empty(tmp_path: Path) -> None:
    missing = tmp_path / "missing_baseline.json"
    loaded = quality_size_guard.load_baseline(missing)
    assert loaded == {}
