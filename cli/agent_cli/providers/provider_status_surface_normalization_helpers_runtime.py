from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from cli.agent_cli.providers import security_endpoint_classify_runtime as endpoint_security_runtime
from cli.agent_cli.providers.availability_projection import availability_surface_fields
from cli.agent_cli.providers.config_catalog_selection import (
    _is_truthy,
    _resolve_oauth_access_token,
    candidate_api_key_names,
    first_configured_key,
)


@dataclass(frozen=True)
class NormalizedProviderCatalogEntryStatusInputs:
    auth_mode: str
    auth_status: str
    token_source: str
    no_auth_guardrail_reason: str
    no_auth_guardrail_pass: bool
    provider_default_model_id: str
    provider_api_key_present: bool
    availability_fields: Dict[str, Any]


def normalized_provider_catalog_entry_status_inputs(
    *,
    provider_name: str,
    provider_entry: Any,
    default_model_entry: Any,
    env_mapping: Mapping[str, Any] | None,
    auth_data: Mapping[str, Any] | None,
    auth_path: Path | None,
    availability_registry: Any | None,
    stale_after_seconds: int,
) -> NormalizedProviderCatalogEntryStatusInputs:
    raw_provider = dict(getattr(provider_entry, "raw_provider", {}) or {})
    provider_auth = dict(getattr(provider_entry, "auth", {}) or {})
    if provider_auth and not isinstance(raw_provider.get("auth"), Mapping):
        raw_provider["auth"] = dict(provider_auth)

    model_id = (
        str(getattr(default_model_entry, "model_id", "") or "").strip()
        or str(getattr(provider_entry, "default_model", "") or "").strip()
    )
    base_url = str(getattr(provider_entry, "base_url", "") or "").strip() or None
    auth_mode = str(getattr(provider_entry, "auth_mode", "") or "api_key").strip().lower() or "api_key"

    env_payload = dict(env_mapping or {})
    auth_payload = dict(auth_data or {})
    api_key_present = False
    auth_status = ""
    token_source = ""

    if auth_mode == "api_key":
        candidate_names = candidate_api_key_names(provider_name, raw_provider, model_id, base_url)
        api_key_present = bool(
            first_configured_key(env_payload, candidate_names)
            or first_configured_key(auth_payload, candidate_names)
        )
        auth_status = "ready" if api_key_present else "missing"
    elif auth_mode in {"oauth", "wellknown"}:
        injected_token, auth_status, token_source = _resolve_oauth_access_token(
            provider_name=provider_name,
            provider_block=raw_provider,
            auth_mode=auth_mode,
            auth_data=auth_payload,
            auth_path=auth_path,
        )
        api_key_present = bool(injected_token)
    else:
        auth_status = "ready" if auth_mode == "none" else ""

    allow_no_auth = _is_truthy(raw_provider.get("allow_no_auth"))
    no_auth_guardrail_pass = endpoint_security_runtime.no_auth_guardrail_pass(
        auth_mode=auth_mode,
        allow_no_auth=allow_no_auth,
        base_url=base_url,
    )
    no_auth_guardrail_reason = str(
        endpoint_security_runtime.no_auth_guardrail_reason(
            auth_mode=auth_mode,
            allow_no_auth=allow_no_auth,
            base_url=base_url,
        )
        or ""
    ).strip()
    availability_fields = dict(
        availability_surface_fields(
            availability_registry,
            provider_name=provider_name,
            model=model_id,
            stale_after_seconds=stale_after_seconds,
        )
    )

    return NormalizedProviderCatalogEntryStatusInputs(
        auth_mode=auth_mode,
        auth_status=auth_status,
        token_source=token_source,
        no_auth_guardrail_reason=no_auth_guardrail_reason,
        no_auth_guardrail_pass=bool(no_auth_guardrail_pass),
        provider_default_model_id=model_id,
        provider_api_key_present=bool(api_key_present),
        availability_fields=availability_fields,
    )


__all__ = [
    "NormalizedProviderCatalogEntryStatusInputs",
    "normalized_provider_catalog_entry_status_inputs",
]
