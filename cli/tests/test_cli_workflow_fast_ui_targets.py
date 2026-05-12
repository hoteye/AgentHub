from __future__ import annotations

import re
from pathlib import Path

import yaml


def test_fast_ui_baseline_job_keeps_key_pytest_targets() -> None:
    workflow_path = (
        Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cli-cross-platform.yml"
    )
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    jobs = dict(payload.get("jobs") or {})
    assert "fast-ui-baseline" in jobs
    job = dict(jobs["fast-ui-baseline"] or {})

    steps = [dict(item) for item in list(job.get("steps") or []) if isinstance(item, dict)]
    step_by_name = {str(step.get("name") or "").strip(): step for step in steps}

    assert "Run clipboard platform-selection tests" in step_by_name
    clipboard_step = step_by_name["Run clipboard platform-selection tests"]
    assert str(clipboard_step.get("working-directory") or "").strip() == "cli"
    clipboard_run = str(clipboard_step.get("run") or "")
    assert " ".join(clipboard_run.split()) == "python -m pytest -q tests/test_paste_pipeline.py"

    assert "Run focus and paste UI baseline" in step_by_name
    focus_step = step_by_name["Run focus and paste UI baseline"]
    assert str(focus_step.get("working-directory") or "").strip() == "cli"
    focus_run = str(focus_step.get("run") or "")
    assert "python -m pytest -q -o addopts='' tests/test_app_ui_smoke.py -k" in focus_run
    key_match = re.search(r'-k\s+"(.+)"', focus_run, re.S)
    assert key_match is not None
    actual_key_expr = " ".join((key_match.group(1) if key_match else "").split())
    assert actual_key_expr == " ".join(
        (
            "ctrl_v_uses_clipboard_text or "
            "right_click_on_composer_accepts_native_paste_event or "
            "right_click_copies_selected_composer_text_instead_of_pasting or "
            "right_click_copy_suppresses_following_native_paste_event or "
            "transcript_left_mouse_up_copies_selection_to_clipboard or "
            "transcript_second_right_click_mouse_down_pastes_without_mouse_up or "
            "prompt_composer_keeps_initial_focus or "
            "app_mouse_up_outside_composer_refocuses_prompt or "
            "app_mouse_up_on_composer_does_not_refocus_again or "
            "transcript_mouse_copy_keeps_focus"
        ).split()
    )
