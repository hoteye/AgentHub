from __future__ import annotations

from pathlib import Path


def _workflow_text() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    workflow_path = repo_root / ".github" / "workflows" / "cli-cross-platform.yml"
    return workflow_path.read_text(encoding="utf-8")


def test_cli_cross_platform_workflow_includes_modularity_guards_job_and_scripts() -> None:
    text = _workflow_text()

    assert "modularity-guards:" in text
    assert 'name: "modularity-guards | ubuntu | py3.13"' in text
    assert "runs-on: ubuntu-latest" in text

    assert "- name: Enforce file-size guard" in text
    assert "python cli/scripts/quality_size_guard.py" in text
    assert "--root cli/agent_cli" in text
    assert "--soft 350" in text
    assert "--hard 500" in text
    assert "--baseline cli/scripts/size_guard_baseline.json" in text

    assert "- name: Enforce import boundaries on changed files" in text
    assert "python cli/scripts/import_boundary_guard.py" in text
    assert '--base-ref "${{ github.base_ref }}"' in text

    assert "- name: Enforce provider config access boundary on changed files" in text
    assert "python cli/scripts/provider_config_boundary_guard.py" in text
    assert "--root cli" in text
    assert '--base-ref "${{ github.base_ref }}"' in text

    assert "- name: Enforce changed-files test gate" in text
    assert "python cli/scripts/changed_files_test_gate.py" in text
    assert "--working-dir cli" in text
    assert '--base-ref "${{ github.base_ref }}"' in text
