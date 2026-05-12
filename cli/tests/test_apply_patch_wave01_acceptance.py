from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "apply_patch_wave01_acceptance.py"
    spec = importlib.util.spec_from_file_location("apply_patch_wave01_acceptance", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load script module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_main_writes_acceptance_bundle_reports(tmp_path: Path) -> None:
    module = _load_module()

    exit_code = module.main(
        [
            "--out-dir",
            str(tmp_path),
            "--json",
        ]
    )

    assert exit_code == 0
    report = json.loads((tmp_path / "apply_patch_wave01_acceptance.report.json").read_text(encoding="utf-8"))
    assert report["suite"] == "apply_patch_wave01_acceptance"
    assert report["passed"] is True

    surface_by_label = {item["label"]: item for item in report["surface_matrix"]}
    assert surface_by_label["codex_openai:gpt-5.4"]["has_apply_patch"] is True
    assert surface_by_label["codex_openai:gpt-5.4"]["has_write"] is False
    assert surface_by_label["codex_openai:gpt-5.4"]["has_edit"] is False
    assert surface_by_label["codex_openai:gpt-5.1"]["has_apply_patch"] is True
    assert surface_by_label["codex_openai:gpt-5.1"]["has_write"] is False
    assert surface_by_label["codex_openai:gpt-5.1"]["has_edit"] is False
    assert surface_by_label["claude_code:claude-sonnet-4-6"]["has_apply_patch"] is False
    assert surface_by_label["claude_code:claude-sonnet-4-6"]["has_write"] is True
    assert surface_by_label["claude_code:claude-sonnet-4-6"]["has_edit"] is True

    cases = {case["case_id"]: case for case in report["cases"]}
    assert cases["raw_multi_file_patch"]["passed"] is True
    assert cases["raw_multi_file_patch"]["steps"][-1]["completed_items"][-1]["name"] == "apply_patch"
    assert cases["write_overwrite_after_read"]["passed"] is True
    assert cases["write_overwrite_after_read"]["steps"][-1]["completed_items"][-1]["name"] == "Write"
    assert cases["edit_replace_all_after_read"]["passed"] is True
    assert cases["edit_replace_all_after_read"]["steps"][-1]["completed_items"][-1]["name"] == "Edit"
    assert cases["write_stale_rejection_after_read"]["error"]
    assert cases["edit_stale_rejection_after_read"]["error"]

    markdown = (tmp_path / "apply_patch_wave01_acceptance.report.md").read_text(encoding="utf-8")
    assert "## AgentHub Surface Snapshot" in markdown
    assert "### raw_multi_file_patch" in markdown
    assert "### codex_ref" in markdown


def test_selected_cases_filters_known_case_ids() -> None:
    module = _load_module()

    selected = module._selected_cases(["write_create", "raw_multi_file_patch"])

    assert [case.case_id for case in selected] == ["raw_multi_file_patch", "write_create"]
