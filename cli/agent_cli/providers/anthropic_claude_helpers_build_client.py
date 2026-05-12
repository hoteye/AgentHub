from __future__ import annotations

from typing import Any

from cli.agent_cli.providers.config_catalog import ProviderConfig

DEFAULT_ANTHROPIC_TIMEOUT_SECONDS = 60.0


def _positive_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def build_anthropic_client(config: ProviderConfig) -> Any:
    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise RuntimeError(
            "Anthropic provider requires the `anthropic` package. Install cli/requirements.txt first."
        ) from exc

    raw_provider = dict(config.raw_provider or {})
    auth_token = str(raw_provider.get("auth_token") or "").strip()
    auth_token_env = str(raw_provider.get("auth_token_env") or "").strip()
    if auth_token:
        kwargs: dict[str, Any] = {"auth_token": auth_token, "max_retries": 0}
    elif auth_token_env and str(config.api_key or "").strip():
        kwargs = {"auth_token": config.api_key, "max_retries": 0}
    else:
        kwargs = {"api_key": config.api_key, "max_retries": 0}
    if str(config.base_url or "").strip():
        kwargs["base_url"] = str(config.base_url)
    raw_model = dict(config.raw_model or {})
    kwargs["timeout"] = (
        _positive_float(raw_model.get("model_timeout"))
        or _positive_float(raw_model.get("timeout"))
        or DEFAULT_ANTHROPIC_TIMEOUT_SECONDS
    )
    return Anthropic(**kwargs)
