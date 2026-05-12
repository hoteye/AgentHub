from __future__ import annotations

from collections.abc import Callable
from typing import Any


def configure_model_selection(
    *,
    agent: Any,
    model: str | None,
    reasoning_effort: str | None,
    persist: bool = False,
    write_scope: str | None = None,
) -> dict[str, Any]:
    configurator = getattr(agent, "configure_model_selection", None)
    if callable(configurator):
        try:
            return dict(
                configurator(
                    model=model,
                    reasoning_effort=reasoning_effort,
                    persist=persist,
                    write_scope=write_scope,
                )
                or {}
            )
        except TypeError:
            # Older test doubles may not accept the newer persist kwarg yet.
            return dict(
                configurator(
                    model=model,
                    reasoning_effort=reasoning_effort,
                )
                or {}
            )
    if model is not None:
        switch_model = getattr(agent, "switch_model", None)
        if not callable(switch_model):
            raise RuntimeError("model switching is not supported by the active agent")
        switch_model(model)
    if reasoning_effort is not None:
        set_reasoning_effort = getattr(agent, "set_reasoning_effort", None)
        if callable(set_reasoning_effort):
            set_reasoning_effort(reasoning_effort)
        elif model is None:
            raise RuntimeError("reasoning effort switching is not supported by the active agent")
    return dict(getattr(agent, "provider_status", lambda: {})() or {})


def configure_named_selection(
    *,
    agent: Any,
    configurator_name: str,
    disabled_error: str,
    target_name: str,
    model: str | None,
    provider: str | None,
    reasoning_effort: str | None,
    timeout: Any,
    clear: bool,
) -> dict[str, Any]:
    configurator = getattr(agent, configurator_name, None)
    if not callable(configurator):
        raise RuntimeError(disabled_error)
    return dict(
        configurator(
            target_name,
            model=model,
            provider=provider,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            clear=clear,
        )
        or {}
    )


def slash_command_rows(specs: list[Any]) -> list[dict[str, str]]:
    return [
        {
            "name": str(spec.name),
            "usage": str(spec.usage),
            "description": str(spec.description),
            "description_key": str(getattr(spec, "description_key", "") or ""),
        }
        for spec in specs
    ]


def build_local_plan(*, local_plan_disabled_note: str) -> dict[str, Any]:
    return {
        "title": "local-plan-disabled",
        "summary": "Built-in local automation planning is disabled.",
        "target_conversation": None,
        "notes": [local_plan_disabled_note],
        "steps": [],
    }


def preview_local_plan(
    *,
    text: str,
    last_plan: dict[str, Any] | None,
    last_plan_text: str | None,
    build_local_plan_fn: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    if last_plan is not None and last_plan_text == text:
        return dict(last_plan)
    return build_local_plan_fn(text)


def local_plan_attempt_state(
    *,
    text: str,
    build_local_plan_fn: Callable[[str], dict[str, Any]],
) -> tuple[dict[str, Any], str, bool]:
    return build_local_plan_fn(text), text, False


def local_plan_preview_state(
    *,
    text: str,
    last_plan: dict[str, Any] | None,
    last_plan_text: str | None,
    build_local_plan_fn: Callable[[str], dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    payload = preview_local_plan(
        text=text,
        last_plan=last_plan,
        last_plan_text=last_plan_text,
        build_local_plan_fn=build_local_plan_fn,
    )
    return payload, dict(payload), text


def normalized_planner_input_item(
    item: Any,
    *,
    response_input_item_from_dict_fn: Callable[[dict[str, Any]], Any],
    planner_message_input_item_fn: Callable[[str, str], dict[str, Any] | None],
) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    item_type = str(item.get("type") or "").strip()
    normalized_item_type = item_type or str(item.get("item_type") or "").strip()
    if normalized_item_type:
        return response_input_item_from_dict_fn(item).to_dict()
    role = str(item.get("role") or "user").strip().lower() or "user"
    content = item.get("content")
    text_chunks: list[str] = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            text = str(block.get("text") or "").strip()
            if text:
                text_chunks.append(text)
    elif isinstance(content, str):
        text = content.strip()
        if text:
            text_chunks.append(text)
    return planner_message_input_item_fn(role, "\n".join(text_chunks))
