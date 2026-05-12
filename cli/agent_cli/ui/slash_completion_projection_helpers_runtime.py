from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from cli.agent_cli.runtime_policy import APPROVAL_POLICIES, SANDBOX_MODES, WEB_SEARCH_MODES
from cli.agent_cli.slash_surface import option_keywords as surface_option_keywords
from cli.agent_cli.slash_surface import option_value_choices as surface_option_value_choices
from cli.agent_cli.slash_surface import pending_value_keyword as surface_pending_value_keyword
from cli.agent_cli.ui import slash_completion_pure_helpers_runtime as _pure_helpers
from cli.agent_cli.ui.presentation import (
    AUTO_LOCALE,
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    normalize_locale_id,
)
from cli.agent_cli.ui.theme import builtin_theme_ids

SELECTION_WRITE_SCOPES = _pure_helpers.SELECTION_WRITE_SCOPES

_LOCALIZED_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "slash.arg.lang.apply_save": {
        "en": "apply and save language",
        "zh-CN": "应用并保存语言",
        "ja": "言語を適用して保存",
        "fr": "appliquer et enregistrer la langue",
    },
    "slash.arg.theme.apply_save": {
        "en": "apply and save theme",
        "zh-CN": "应用并保存主题",
        "ja": "テーマを適用して保存",
        "fr": "appliquer et enregistrer le theme",
    },
    "slash.arg.provider.switch_save_user": {
        "en": "switch provider and save as user default",
        "zh-CN": "切换 provider 并保存为用户默认值",
        "ja": "provider を切り替えてユーザー既定として保存",
        "fr": "changer de provider et l'enregistrer comme valeur utilisateur par defaut",
    },
    "slash.arg.models.show_for_provider": {
        "en": "show models for provider",
        "zh-CN": "显示该 provider 的模型",
        "ja": "provider のモデルを表示",
        "fr": "afficher les modeles du provider",
    },
    "slash.arg.model.switch_save_user": {
        "en": "switch model and save as user default",
        "zh-CN": "切换模型并保存为用户默认值",
        "ja": "モデルを切り替えてユーザー既定として保存",
        "fr": "changer de modele et l'enregistrer comme valeur utilisateur par defaut",
    },
    "slash.arg.model.reasoning_effort": {
        "en": "reasoning effort",
        "zh-CN": "推理强度",
        "ja": "推論強度",
        "fr": "effort de raisonnement",
    },
    "slash.arg.shell.mode": {
        "en": "shell mode",
        "zh-CN": "shell 模式",
        "ja": "シェルモード",
        "fr": "mode shell",
    },
    "slash.arg.browser.action": {
        "en": "browser action",
        "zh-CN": "浏览器动作",
        "ja": "ブラウザー操作",
        "fr": "action du navigateur",
    },
    "slash.arg.option": {
        "en": "{command} option",
        "zh-CN": "{command} 选项",
        "ja": "{command} オプション",
        "fr": "option {command}",
    },
    "slash.arg.value_for": {
        "en": "value for {flag}",
        "zh-CN": "{flag} 的值",
        "ja": "{flag} の値",
        "fr": "valeur pour {flag}",
    },
}


def _localized_text(key: str, fallback: str, *, locale: str | None = None, **kwargs: object) -> str:
    normalized_locale = normalize_locale_id(locale) or DEFAULT_LOCALE
    localized = _LOCALIZED_DESCRIPTIONS.get(key, {})
    template = localized.get(normalized_locale) or localized.get(DEFAULT_LOCALE) or fallback
    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template
    return template


def _localized_candidate_description(candidate: dict[str, str], *, locale: str | None) -> str:
    description_key = str(candidate.get("description_key") or "").strip()
    if not description_key:
        return str(candidate.get("description") or "").strip()
    return _localized_text(
        description_key,
        str(candidate.get("description") or "").strip(),
        locale=locale,
        command=str(candidate.get("command") or "").strip(),
    )


def _localized_candidate(candidate: dict[str, str], *, locale: str | None) -> dict[str, str]:
    item = dict(candidate)
    item["description"] = _localized_candidate_description(item, locale=locale)
    item.pop("description_key", None)
    item.pop("command", None)
    return item


def slash_value_candidate_description(flag_name: str, *, locale: str | None = None) -> str:
    normalized_flag = str(flag_name or "").strip()
    return _localized_text(
        "slash.arg.value_for",
        f"value for {normalized_flag}",
        locale=locale,
        flag=normalized_flag,
    )


def slash_pending_flag(command_name: str, completed_tokens: tuple[str, ...]) -> str | None:
    normalized_command = str(command_name or "").strip().lower()
    if normalized_command == "provider":
        return None
    return surface_pending_value_keyword(command_name, completed_tokens)


def slash_flag_value_candidates(
    command_name: str,
    flag_name: str,
    *,
    reasoning_efforts: Sequence[str],
    approval_statuses: Sequence[str],
) -> tuple[str, ...]:
    normalized_command = str(command_name or "").strip().lower()
    normalized_flag = str(flag_name or "").strip().lower().removeprefix("--")
    mapping = {
        ("provider", "write"): SELECTION_WRITE_SCOPES,
        ("model", "reasoning-effort"): tuple(reasoning_efforts),
        ("model", "write"): SELECTION_WRITE_SCOPES,
        ("connect", "auth-mode"): ("api_key", "oauth", "wellknown", "none"),
        ("connect", "write"): ("user", "project"),
        ("runtime_config", "approval-policy"): APPROVAL_POLICIES,
        ("runtime_config", "sandbox-mode"): SANDBOX_MODES,
        ("runtime_config", "web-search-mode"): WEB_SEARCH_MODES,
        ("runtime_config", "network-access"): ("enabled", "disabled"),
        ("approvals", "status"): tuple(approval_statuses),
    }
    static = surface_option_value_choices(normalized_command, normalized_flag)
    if static:
        return static
    return tuple(mapping.get((normalized_command, normalized_flag), ()))


def slash_submit_after_apply(command_name: str, *, pending_flag: str | None) -> bool:
    normalized = str(command_name or "").strip().lower()
    if pending_flag is not None:
        return (
            normalized in {"provider", "model"}
            and str(pending_flag).strip().lower().removeprefix("--") == "write"
        )
    return False


def slash_positional_candidates(
    command_name: str,
    completed_tokens: tuple[str, ...],
    *,
    runtime: Any,
    browser_actions: Sequence[str],
    reasoning_efforts: Sequence[str] = (),
    locale: str | None = None,
) -> list[dict[str, str]]:
    normalized = str(command_name or "").strip().lower()
    if normalized == "lang":
        candidates = [
            _pure_helpers.slash_candidate(
                item,
                "apply and save language",
                description_key="slash.arg.lang.apply_save",
                submit_after_apply=True,
                name=f"lang:{item}",
            )
            for item in [*SUPPORTED_LOCALES, AUTO_LOCALE]
        ]
        return [_localized_candidate(item, locale=locale) for item in candidates]
    if normalized == "theme":
        candidates = [
            _pure_helpers.slash_candidate(
                item,
                "apply and save theme",
                description_key="slash.arg.theme.apply_save",
                submit_after_apply=True,
                name=f"theme:{item}",
            )
            for item in builtin_theme_ids()
        ]
        return [_localized_candidate(item, locale=locale) for item in candidates]
    if normalized == "provider" and len(completed_tokens) == 0:
        candidates: list[dict[str, str]] = []
        for item in _pure_helpers.available_provider_names(runtime):
            candidates.extend(_pure_helpers.selection_scope_action_candidates(normalized, item))
        return [_localized_candidate(item, locale=locale) for item in candidates]
    if normalized == "models" and len(completed_tokens) == 0:
        candidates = [
            _pure_helpers.slash_candidate(
                item,
                "show models for provider",
                description_key="slash.arg.models.show_for_provider",
                submit_after_apply=True,
                name=f"models:{item}",
            )
            for item in _pure_helpers.available_provider_names(runtime)
        ]
        return [_localized_candidate(item, locale=locale) for item in candidates]
    if normalized == "model" and len(completed_tokens) == 0:
        candidates: list[dict[str, str]] = []
        for item in _pure_helpers.available_model_items(
            runtime,
            provider_name=_pure_helpers.current_provider_name(runtime),
        ):
            model_name = str(
                item.get("model_key") or item.get("display_name") or item.get("model_id") or ""
            ).strip()
            if not model_name:
                continue
            candidates.extend(
                _pure_helpers.selection_scope_action_candidates_with_metadata(
                    normalized,
                    model_name,
                    availability_hint=_pure_helpers.model_availability_hint(runtime, item),
                )
            )
        return [_localized_candidate(item, locale=locale) for item in candidates]
    if normalized == "model" and len(completed_tokens) == 1:
        selected_model = str(completed_tokens[0] or "").strip()
        candidates = [
            _pure_helpers.slash_candidate(
                item,
                "reasoning effort",
                description_key="slash.arg.model.reasoning_effort",
                submit_after_apply=True,
                name=f"model:reasoning-effort:{item}",
            )
            for item in _pure_helpers.reasoning_effort_names_for_model(
                runtime,
                selected_model,
                provider_name=_pure_helpers.current_provider_name(runtime),
                fallback=tuple(reasoning_efforts),
            )
        ]
        return [_localized_candidate(item, locale=locale) for item in candidates]
    if normalized == "shell" and len(completed_tokens) == 0:
        candidates = [
            _pure_helpers.slash_candidate(
                item,
                "shell mode",
                description_key="slash.arg.shell.mode",
            )
            for item in ("start", "write", "terminate")
        ]
        return [_localized_candidate(item, locale=locale) for item in candidates]
    if normalized == "browser" and len(completed_tokens) == 0:
        candidates = [
            _pure_helpers.slash_candidate(
                item,
                "browser action",
                description_key="slash.arg.browser.action",
            )
            for item in browser_actions
        ]
        return [_localized_candidate(item, locale=locale) for item in candidates]
    return []


def slash_flag_candidates(
    command_name: str,
    *,
    slash_command_spec_getter: Callable[[str], dict[str, str] | None],
    locale: str | None = None,
) -> list[dict[str, str]]:
    normalized_command = str(command_name or "").strip().lower()
    if normalized_command in {"provider", "model"}:
        return []
    keywords = surface_option_keywords(normalized_command)
    if keywords:
        candidates = [
            _pure_helpers.slash_candidate(
                keyword,
                f"{command_name} option",
                description_key="slash.arg.option",
                command=command_name,
                name=f"{command_name}:{keyword}",
            )
            for keyword in keywords
        ]
        return [_localized_candidate(item, locale=locale) for item in candidates]
    spec = slash_command_spec_getter(normalized_command)
    if spec is None:
        return []
    candidates = [
        _pure_helpers.slash_candidate(
            flag_name,
            f"{command_name} option",
            description_key="slash.arg.option",
            command=command_name,
            name=f"{command_name}:{flag_name}",
        )
        for flag_name in _pure_helpers.usage_flag_names(str(spec.get("usage") or ""))
    ]
    return [_localized_candidate(item, locale=locale) for item in candidates]
