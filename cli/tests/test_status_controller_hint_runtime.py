from __future__ import annotations

from cli.agent_cli.ui import status_controller_hint_runtime


def _short(value: str, _: int) -> str:
    return value


def _crop_one_line(value: str, _: int) -> str:
    return value


def _tool_label(value: str) -> str:
    return str(value or "").replace("_", " ")


def _boolish(value: object) -> bool | None:
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def test_build_operator_surface_hint_includes_tenant_scope() -> None:
    text = status_controller_hint_runtime.build_operator_surface_hint(
        {
            "task_id": "bg123",
            "tenant_id": "tenant_alpha",
            "workspace_scope": "workspace_beta",
            "status": "running",
            "workflow_state": "running",
        },
        width=240,
        short_fn=_short,
        crop_one_line_fn=_crop_one_line,
        tool_label_fn=_tool_label,
        boolish_status_fn=_boolish,
    )
    assert "task bg123" in text
    assert "tenant tenant alpha" in text
    assert "scope workspace beta" in text


def test_operator_hint_from_command_includes_tenant_scope() -> None:
    text = status_controller_hint_runtime.operator_hint_from_command(
        "background_task_status",
        key_values={
            "task_id": "bg456",
            "tenant_id": "tenant_gamma",
            "workspace_scope": "workspace_delta",
            "status": "completed",
            "result_state": "pending_review",
        },
        assistant_text="background task status",
        normalized_count_fn=lambda value: str(value),
        tool_label_fn=_tool_label,
        flag_label_fn=lambda value: str(value),
    )
    assert "task bg456" in text
    assert "tenant tenant gamma" in text
    assert "scope workspace delta" in text

