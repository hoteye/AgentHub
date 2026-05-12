from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any

from cli.agent_cli.runtime_kernels.routing import normalize_kernel_engine
from cli.agent_cli.ui import slash_controller_popup_runtime
from cli.agent_cli.ui.presentation import (
    AUTO_LOCALE,
    SUPPORTED_LOCALES,
    normalize_locale_id,
    save_user_presentation_preferences,
    user_presentation_config_path,
)
from cli.agent_cli.ui.theme import builtin_theme_ids


def handle_local_slash_command(
    controller: Any,
    text: str,
    *,
    attachments: list[Any] | None = None,
) -> bool:
    def _handle_plan(arg_text: str) -> bool:
        handler = controller._handle_local_plan_command
        parameters = inspect.signature(handler).parameters
        accepts_attachments = "attachments" in parameters or any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
        )
        if accepts_attachments:
            return bool(handler(arg_text, attachments=list(attachments or [])))
        return bool(handler(arg_text))

    return slash_controller_popup_runtime.handle_local_slash_command(
        text,
        handle_lang_fn=controller._handle_local_lang_command,
        handle_theme_fn=controller._handle_local_theme_command,
        handle_setup_fn=controller._handle_local_setup_command,
        handle_plan_fn=_handle_plan,
        handle_tab_rename_fn=controller._handle_local_tab_rename_command,
        handle_tab_new_fn=controller._handle_local_tab_new_command,
        handle_approval_inbox_fn=controller._handle_local_approval_inbox_command,
        handle_preview_fn=controller._handle_local_preview_command,
        handle_fork_fn=controller._handle_local_fork_command,
        handle_master_fn=controller._handle_local_master_command,
        handle_fork_child_fn=controller._handle_local_fork_child_command,
        handle_close_fn=controller._handle_local_close_command,
    )


def handle_local_lang_command(
    controller: Any,
    arg_text: str,
    *,
    save_preferences_fn: Callable[..., Any] = save_user_presentation_preferences,
) -> None:
    slash_controller_popup_runtime.handle_local_lang_command(
        arg_text,
        supported_locales=tuple(SUPPORTED_LOCALES),
        auto_locale=AUTO_LOCALE,
        normalize_locale_id_fn=normalize_locale_id,
        user_config_path_getter=lambda: str(user_presentation_config_path()),
        save_preferences_fn=save_preferences_fn,
        resolve_effective_presentation_fn=controller._resolve_effective_presentation,
        apply_presentation_fn=controller._apply_presentation,
        current_locale_getter=lambda: controller._presentation.locale,
        desired_locale_for_preference_fn=controller._desired_locale_for_preference,
        lang_override_source_getter=controller._lang_override_source,
        translate_fn=controller._t,
        write_notice_fn=controller._write_system_notice,
    )


def handle_local_theme_command(
    controller: Any,
    arg_text: str,
    *,
    save_preferences_fn: Callable[..., Any] = save_user_presentation_preferences,
) -> None:
    slash_controller_popup_runtime.handle_local_theme_command(
        arg_text,
        supported_themes=tuple(builtin_theme_ids()),
        user_config_path_getter=lambda: str(user_presentation_config_path()),
        save_preferences_fn=save_preferences_fn,
        resolve_effective_presentation_fn=controller._resolve_effective_presentation,
        apply_presentation_fn=controller._apply_presentation,
        current_theme_id_getter=lambda: controller._presentation.theme_id,
        theme_override_source_getter=controller._theme_override_source,
        translate_fn=controller._t,
        write_notice_fn=controller._write_system_notice,
    )


def handle_local_setup_command(controller: Any, arg_text: str) -> bool:
    if str(arg_text or "").strip():
        return False
    from cli.agent_cli.ui.setup_modal import present_setup_overlay, setup_command_from_payload

    agent = getattr(getattr(controller, "runtime", None), "agent", None)
    provider_status = getattr(agent, "provider_status", None)
    status = dict(provider_status() or {}) if callable(provider_status) else {}

    initial_payload = {
        "provider": str(
            status.get("provider_name") or status.get("provider_public_name") or "openai"
        ).strip()
        or "openai",
        "base_url": str(status.get("provider_base_url") or "").strip(),
    }

    def _on_submit(payload: dict[str, str]) -> None:
        command_text = setup_command_from_payload(payload)
        controller._write_system_notice("Running setup...")
        asyncio.create_task(controller._enqueue_runtime_request(command_text, [], priority="later"))

    return present_setup_overlay(
        app=controller,
        payload=initial_payload,
        on_submit=_on_submit,
        on_cancel=lambda: None,
    )


def handle_local_plan_command(
    controller: Any,
    arg_text: str,
    *,
    attachments: list[Any] | None = None,
) -> bool:
    prompt_text = str(arg_text or "").strip()
    controller.runtime.collaboration_mode = "plan"
    if prompt_text:
        asyncio.create_task(
            controller._enqueue_runtime_request(
                prompt_text,
                list(attachments or []),
                priority="next",
            )
        )
        return True
    controller._write_system_notice("switched to Plan mode")
    return True


def handle_local_tab_rename_command(controller: Any, arg_text: str) -> bool:
    mgr = getattr(controller, "_tab_manager", None)
    if mgr is None:
        return False
    label = " ".join(str(arg_text or "").split())
    if not mgr.rename_tab(getattr(mgr, "active_tab_id", ""), label):
        return False
    refresh_top_title = getattr(controller, "_refresh_top_title_bar", None)
    if callable(refresh_top_title):
        refresh_top_title()
    key = "system.tab_rename_cleared" if not label else "system.tab_rename_saved"
    controller._write_system_notice(controller._t(key, label=label))
    return True


def handle_local_tab_new_command(controller: Any, arg_text: str) -> bool:
    mgr = getattr(controller, "_tab_manager", None)
    if mgr is None:
        return False
    requested = str(arg_text or "").strip().lower().replace("-", "_")
    engine = normalize_kernel_engine(requested)
    if engine is None:
        controller._write_system_notice(controller._t("system.tab_new_usage"))
        return True
    tab_id = mgr.create_tab(engine=engine)
    if not tab_id:
        controller._write_system_notice(controller._t("system.tab_new_failed", engine=engine))
        return True
    refresh_top_title = getattr(controller, "_refresh_top_title_bar", None)
    if callable(refresh_top_title):
        refresh_top_title()
    focus_input = getattr(controller, "_focus_input", None)
    if callable(focus_input):
        focus_input()
    controller._write_system_notice(
        controller._t("system.tab_new_created", tab_id=tab_id, engine=engine)
    )
    return True


def handle_local_master_command(controller: Any, arg_text: str) -> bool:
    if str(arg_text or "").strip():
        controller._write_system_notice(controller._t("system.master_usage"))
        return True
    mgr = getattr(controller, "_tab_manager", None)
    if mgr is None:
        return False
    if not mgr.mark_master(getattr(mgr, "active_tab_id", "")):
        return False
    refresh_top_title = getattr(controller, "_refresh_top_title_bar", None)
    if callable(refresh_top_title):
        refresh_top_title()
    active_tab_id = str(getattr(mgr, "active_tab_id", "") or "")
    display_label = active_tab_id
    display_label_fn = getattr(mgr, "display_tab_label", None)
    if callable(display_label_fn):
        display_label = str(display_label_fn(active_tab_id) or active_tab_id)
    controller._write_system_notice(controller._t("system.master_marked", tab_id=display_label))
    return True


def handle_local_fork_child_command(controller: Any, arg_text: str) -> bool:
    if str(arg_text or "").strip():
        controller._write_system_notice(controller._t("system.fork_child_usage"))
        return True
    mgr = getattr(controller, "_tab_manager", None)
    if mgr is None:
        return False
    source_tab_id = getattr(mgr, "active_tab_id", "")
    tab_id = mgr.fork_child_tab(source_tab_id)
    if not tab_id:
        controller._write_system_notice(controller._t("system.fork_child_failed"))
        return True
    refresh_top_title = getattr(controller, "_refresh_top_title_bar", None)
    if callable(refresh_top_title):
        refresh_top_title()
    focus_input = getattr(controller, "_focus_input", None)
    if callable(focus_input):
        focus_input()
    display_label_fn = getattr(mgr, "display_tab_label", None)
    child_label = tab_id
    parent_label = source_tab_id
    if callable(display_label_fn):
        child_label = str(display_label_fn(tab_id) or tab_id)
        parent_label = str(display_label_fn(source_tab_id) or source_tab_id)
    controller._write_system_notice(
        controller._t(
            "system.fork_child_created",
            child_tab_id=child_label,
            parent_tab_id=parent_label,
        )
    )
    return True


def _approval_inbox_line(controller: Any, row: dict[str, Any]) -> str:
    tab_id = str(row.get("tab_id") or "").strip()
    label = str(row.get("label") or tab_id).strip() or tab_id
    active_marker = " *" if bool(row.get("is_active")) else ""
    approvals = [item for item in list(row.get("approvals") or []) if isinstance(item, dict)]
    ids = [
        str(item.get("approval_id") or "").strip()
        for item in approvals
        if str(item.get("approval_id") or "").strip()
    ]
    summaries = [
        controller._short(str(item.get("summary") or "").strip(), 48)
        for item in approvals
        if str(item.get("summary") or "").strip()
    ]
    detail = ", ".join(ids) if ids else "-"
    if summaries:
        detail = f"{detail} - {'; '.join(summaries[:2])}"
    return f"- {tab_id}{active_marker} [{controller._short(label, 28)}]: {len(ids)} approval(s): {detail}"


def handle_local_approval_inbox_command(controller: Any, arg_text: str) -> bool:
    tokens = str(arg_text or "").split()
    if len(tokens) > 2:
        controller._write_system_notice(controller._t("system.approval_inbox_usage"))
        return True
    rows_fn = getattr(controller, "_tab_approval_inbox_rows", None)
    rows = list(rows_fn() or []) if callable(rows_fn) else []
    if tokens:
        if len(tokens) != 2 or tokens[0].lower() != "go":
            controller._write_system_notice(controller._t("system.approval_inbox_usage"))
            return True
        target_tab_id = str(tokens[1] or "").strip()
        mgr = getattr(controller, "_tab_manager", None)
        if mgr is None or mgr.get(target_tab_id) is None:
            controller._write_system_notice(
                controller._t("system.approval_inbox_tab_not_found", tab_id=target_tab_id)
            )
            return True
        if target_tab_id == getattr(mgr, "active_tab_id", ""):
            controller._write_system_notice(
                controller._t("system.approval_inbox_already_active", tab_id=target_tab_id)
            )
            return True
        if not mgr.switch_to_tab(target_tab_id):
            controller._write_system_notice(
                controller._t("system.approval_inbox_tab_not_found", tab_id=target_tab_id)
            )
            return True
        refresh_top_title = getattr(controller, "_refresh_top_title_bar", None)
        if callable(refresh_top_title):
            refresh_top_title()
        focus_input = getattr(controller, "_focus_input", None)
        if callable(focus_input):
            focus_input()
        controller._write_system_notice(
            controller._t("system.approval_inbox_switched", tab_id=target_tab_id)
        )
        return True
    if not rows:
        controller._write_system_notice(controller._t("system.approval_inbox_empty"))
        return True
    total = sum(
        max(0, int(row.get("total") or len(list(row.get("approvals") or [])))) for row in rows
    )
    lines = [
        controller._t("system.approval_inbox_heading", count=total),
        *[_approval_inbox_line(controller, row) for row in rows],
        controller._t("system.approval_inbox_hint"),
    ]
    controller._write_system_notice("\n".join(lines))
    return True


def handle_local_preview_command(controller: Any, arg_text: str) -> bool:
    normalized = str(arg_text or "").strip().lower() or "toggle"
    controller._handle_preview_control_request(normalized)
    return True
