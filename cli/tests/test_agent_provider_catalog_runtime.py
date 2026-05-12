from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from cli.agent_cli.agent_provider_catalog_runtime import available_model_items, available_provider_items
from cli.agent_cli.providers.availability_models import AvailabilityRecord, ProbeStatus
from cli.agent_cli.providers.config_catalog import ModelCatalogEntry, ProviderCatalog, ProviderCatalogEntry


def _public_provider_name(*, provider_name: str, model: str = "", base_url: str = "", planner_kind: str = "") -> str:
    del model, base_url, planner_kind
    return {
        "anthropic-glm": "anthropic",
        "glm-claude-mode": "anthropic",
        "google_oauth_probe": "openai",
    }.get(provider_name, provider_name)


def _default_model_entry(provider_name: str, catalog: ProviderCatalog):
    provider_entry = catalog.providers.get(provider_name)
    if provider_entry is None:
        return None
    return catalog.models.get(provider_entry.default_model)


def _vendor_for_name(name: str):
    return SimpleNamespace(name=name)


class _AvailabilityRegistry:
    def __init__(self, records):
        self._records = records

    def get(self, provider_name: str, model: str):
        return self._records.get((provider_name, model))

    def status(self, provider_name: str, model: str):
        record = self.get(provider_name, model)
        return record.status if record is not None else ProbeStatus.UNKNOWN


def test_available_model_items_hides_internal_compat_and_route_variants_by_default() -> None:
    catalog = ProviderCatalog(
        providers={
            "openai": ProviderCatalogEntry(provider_name="openai", default_model="gpt_54"),
            "anthropic": ProviderCatalogEntry(provider_name="anthropic", default_model="claude_sonnet_46"),
            "anthropic-glm": ProviderCatalogEntry(provider_name="anthropic-glm", default_model="anthropic_glm_glm_5"),
        },
        models={
            "gpt_54": ModelCatalogEntry(
                key="gpt_54",
                provider_name="openai",
                model_id="gpt-5.4",
                display_name="GPT-5.4",
            ),
            "gpt_54_route_variant": ModelCatalogEntry(
                key="gpt_54_route_variant",
                provider_name="openai",
                model_id="gpt-5.4",
                display_name="GPT-5.4 Route Variant",
                raw_model={"routes": {"tool_followup": {"provider": "glm", "model": "glm_5"}}},
            ),
            "claude_sonnet_46": ModelCatalogEntry(
                key="claude_sonnet_46",
                provider_name="anthropic",
                model_id="claude-sonnet-4-6",
                display_name="Claude Sonnet 4.6",
            ),
            "claude-sonnet-4-6": ModelCatalogEntry(
                key="claude-sonnet-4-6",
                provider_name="anthropic",
                model_id="claude-sonnet-4-6",
                display_name="claude-sonnet-4-6",
            ),
            "anthropic_glm_glm_5": ModelCatalogEntry(
                key="anthropic_glm_glm_5",
                provider_name="anthropic-glm",
                model_id="glm-5",
                display_name="GLM-5 Anthropic Compat",
            ),
        },
    )

    items = available_model_items(
        catalog,
        provider_name=None,
        include_hidden=False,
        public_provider_name_fn=_public_provider_name,
        default_model_entry_fn=_default_model_entry,
        vendor_for_name_fn=_vendor_for_name,
    )

    assert [item["model_key"] for item in items] == ["claude_sonnet_46", "gpt_54"]
    assert [item["provider_name"] for item in items] == ["anthropic", "openai"]


def test_available_model_items_include_hidden_surfaces_filtered_entries_with_hidden_flag() -> None:
    catalog = ProviderCatalog(
        providers={
            "openai": ProviderCatalogEntry(provider_name="openai", default_model="gpt_54"),
            "anthropic-glm": ProviderCatalogEntry(provider_name="anthropic-glm", default_model="anthropic_glm_glm_5"),
        },
        models={
            "gpt_54": ModelCatalogEntry(
                key="gpt_54",
                provider_name="openai",
                model_id="gpt-5.4",
                display_name="GPT-5.4",
            ),
            "gpt_54_route_variant": ModelCatalogEntry(
                key="gpt_54_route_variant",
                provider_name="openai",
                model_id="gpt-5.4",
                display_name="GPT-5.4 Route Variant",
                raw_model={"routes": {"tool_followup": {"provider": "glm", "model": "glm_5"}}},
            ),
            "anthropic_glm_glm_5": ModelCatalogEntry(
                key="anthropic_glm_glm_5",
                provider_name="anthropic-glm",
                model_id="glm-5",
                display_name="GLM-5 Anthropic Compat",
            ),
        },
    )

    items = available_model_items(
        catalog,
        provider_name=None,
        include_hidden=True,
        public_provider_name_fn=_public_provider_name,
        default_model_entry_fn=_default_model_entry,
        vendor_for_name_fn=_vendor_for_name,
    )

    by_key = {item["model_key"]: item for item in items}
    assert by_key["gpt_54"]["hidden"] is False
    assert by_key["gpt_54_route_variant"]["hidden"] is True
    assert by_key["anthropic_glm_glm_5"]["hidden"] is True


def test_available_provider_items_include_management_status_fields() -> None:
    catalog = ProviderCatalog(
        providers={
            "openai": ProviderCatalogEntry(
                provider_name="openai",
                default_model="gpt_54",
                auth_mode="api_key",
                base_url="https://api.openai.com/v1",
            ),
            "anthropic": ProviderCatalogEntry(
                provider_name="anthropic",
                default_model="claude_sonnet_46",
                auth_mode="oauth",
                auth={"token_ref": "anthropic-main"},
                base_url="https://api.anthropic.com",
            ),
        },
        models={
            "gpt_54": ModelCatalogEntry(
                key="gpt_54",
                provider_name="openai",
                model_id="gpt-5.4",
                display_name="GPT-5.4",
            ),
            "claude_sonnet_46": ModelCatalogEntry(
                key="claude_sonnet_46",
                provider_name="anthropic",
                model_id="claude-sonnet-4-6",
                display_name="Claude Sonnet 4.6",
            ),
        },
    )
    registry = _AvailabilityRegistry(
        {
            ("openai", "gpt-5.4"): AvailabilityRecord(
                provider_name="openai",
                model="gpt-5.4",
                status=ProbeStatus.AVAILABLE,
            ),
        }
    )

    items = available_provider_items(
        catalog,
        public_provider_name_fn=_public_provider_name,
        default_model_entry_fn=_default_model_entry,
        vendor_for_name_fn=_vendor_for_name,
        env_mapping={"OPENAI_API_KEY": "sk-test"},
        auth_data={},
        auth_path=Path("/tmp/auth.json"),
        availability_registry=registry,
    )

    by_provider = {item["provider_name"]: item for item in items}
    assert by_provider["openai"]["provider_auth_ready"] is True
    assert by_provider["openai"]["provider_status_state"] == "ready"
    assert by_provider["openai"]["provider_base_eligible"] is True
    assert by_provider["openai"]["provider_api_key_present"] is True
    assert by_provider["anthropic"]["auth_status"] == "missing"
    assert by_provider["anthropic"]["provider_auth_ready"] is False
    assert by_provider["anthropic"]["provider_status_state"] == "auth_blocked"
    assert by_provider["anthropic"]["provider_status_reason"] == "auth_not_ready"
