from __future__ import annotations

from typing import Any, Dict

from cli.agent_cli.tools_core.browser_proxy_client import (
    _browser_preview_text,
    _browser_text,
    _normalize_browser_act_kind,
    _normalize_browser_console_level,
)
from cli.agent_cli.tools_core import (
    browser_action_normalization_runtime as normalization_runtime,
)

def browser_event_name(action: str) -> str:
    return normalization_runtime.browser_event_name(action)


def resolve_browser_target(
    payload: Dict[str, Any],
    *,
    client: Any,
    action: str,
    profile: str | None,
    requested_target: str | None,
) -> str | None:
    return normalization_runtime.resolve_browser_target(
        payload,
        client=client,
        action=action,
        profile=profile,
        requested_target=requested_target,
        browser_text_fn=_browser_text,
    )


def normalize_browser_payload(
    payload: Dict[str, Any],
    *,
    client: Any,
    action: str,
    profile: str | None,
    requested_target: str | None,
    requested_url: str | None,
    requested_ref: str | None,
    requested_start_ref: str | None = None,
    requested_end_ref: str | None = None,
    requested_kind: str | None = None,
    requested_width: int | None = None,
    requested_height: int | None = None,
    requested_values: list[str] | None = None,
    requested_fields: list[dict[str, Any]] | None = None,
    requested_paths: list[str] | None = None,
    requested_input_ref: str | None = None,
    requested_accept: bool | None = None,
    requested_prompt_text: str | None = None,
) -> Dict[str, Any]:
    return normalization_runtime.normalize_browser_payload(
        payload,
        client=client,
        action=action,
        profile=profile,
        requested_target=requested_target,
        requested_url=requested_url,
        requested_ref=requested_ref,
        requested_start_ref=requested_start_ref,
        requested_end_ref=requested_end_ref,
        requested_kind=requested_kind,
        requested_width=requested_width,
        requested_height=requested_height,
        requested_values=requested_values,
        requested_fields=requested_fields,
        requested_paths=requested_paths,
        requested_input_ref=requested_input_ref,
        requested_accept=requested_accept,
        requested_prompt_text=requested_prompt_text,
        browser_text_fn=_browser_text,
        browser_preview_text_fn=_browser_preview_text,
        normalize_browser_act_kind_fn=_normalize_browser_act_kind,
        normalize_browser_console_level_fn=_normalize_browser_console_level,
        resolve_browser_target_fn=lambda raw_payload, **kwargs: resolve_browser_target(
            raw_payload,
            client=kwargs["client"],
            action=kwargs["action"],
            profile=kwargs["profile"],
            requested_target=kwargs["requested_target"],
        ),
    )


def browser_request_error(
    *,
    action: str,
    kind: str | None,
    ref: str | None,
    start_ref: str | None,
    end_ref: str | None,
    width: int | None,
    height: int | None,
) -> str | None:
    return normalization_runtime.browser_request_error(
        action=action,
        kind=kind,
        ref=ref,
        start_ref=start_ref,
        end_ref=end_ref,
        width=width,
        height=height,
        normalize_browser_act_kind_fn=_normalize_browser_act_kind,
        browser_text_fn=_browser_text,
    )
