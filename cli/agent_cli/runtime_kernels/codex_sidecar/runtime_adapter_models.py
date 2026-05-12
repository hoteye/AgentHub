from __future__ import annotations

from typing import Any


def _model_item_from_sidecar(item: dict[str, Any]) -> dict[str, Any]:
    model_id = str(item.get("model") or item.get("id") or "").strip()
    display_name = str(item.get("displayName") or item.get("display_name") or model_id).strip()
    provider_name = str(item.get("providerName") or item.get("provider_name") or "openai").strip()
    supported_efforts = item.get("supportedReasoningEfforts")
    if not isinstance(supported_efforts, list):
        supported_efforts = item.get("supported_reasoning_efforts")
    return {
        "model_key": model_id,
        "model_id": model_id,
        "display_name": display_name,
        "provider_name": provider_name or "openai",
        "planner_kind": "codex_sidecar",
        "wire_api": "codex_app_server",
        "supports_reasoning": bool(supported_efforts),
        "supported_reasoning_efforts": list(supported_efforts or []),
        "default_reasoning_effort": str(
            item.get("defaultReasoningEffort") or item.get("default_reasoning_effort") or ""
        ),
        "input_modalities": list(item.get("inputModalities") or item.get("input_modalities") or []),
        "supports_personality": bool(
            item.get("supportsPersonality") or item.get("supports_personality")
        ),
        "hidden": bool(item.get("hidden")),
        "upgrade": item.get("upgrade"),
        "upgrade_info": item.get("upgradeInfo") or item.get("upgrade_info"),
        "availability_nux": item.get("availabilityNux") or item.get("availability_nux"),
    }


def _provider_status_path(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return "-"
