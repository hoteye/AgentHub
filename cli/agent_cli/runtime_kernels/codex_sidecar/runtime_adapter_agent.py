from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_kernels.base import KernelSession
from cli.agent_cli.runtime_kernels.codex_sidecar.model_catalog import CodexSidecarModelCatalog
from cli.agent_cli.runtime_kernels.codex_sidecar.runtime_adapter_models import (
    _model_item_from_sidecar,
    _provider_status_path,
)


class CodexSidecarRuntimeAgent:
    def __init__(
        self,
        *,
        session: KernelSession,
        artifact_metadata: dict[str, Any] | None = None,
        model_catalog: CodexSidecarModelCatalog | None = None,
    ) -> None:
        self._session = session
        self._artifact_metadata = dict(artifact_metadata or {})
        self._model_catalog = model_catalog

    def provider_status(self) -> dict[str, str]:
        projected_config = dict(self._artifact_metadata.get("projected_config") or {})
        provider = self.display_provider_name(self._session.model_provider) or "codex"
        model = self._session.model or "-"
        status = {
            "provider_ready": "true",
            "provider_name": provider,
            "provider_public_name": provider,
            "provider_model": model,
            "provider_tools": "codex-sidecar",
            "provider_label": f"{provider} | {model} | codex-sidecar",
            "provider_base_url": "-",
            "provider_source": "codex_sidecar",
            "provider_config_path": _provider_status_path(
                projected_config,
                "codex_sidecar_source_config_path",
                "codex_sidecar_config_path",
            ),
            "provider_auth_path": _provider_status_path(
                projected_config,
                "codex_sidecar_source_auth_path",
                "codex_sidecar_auth_path",
            ),
            "kernel_engine": "codex_sidecar",
            "kernel_session_id": self._session.session_id,
            "thread_id": self._session.thread_id,
        }
        artifact_path = str(self._artifact_metadata.get("path") or "").strip()
        artifact_source = str(self._artifact_metadata.get("source") or "").strip()
        artifact_version = str(self._artifact_metadata.get("version") or "").strip()
        if artifact_path:
            status["codex_sidecar_path"] = artifact_path
        if artifact_source:
            status["codex_sidecar_source"] = artifact_source
        if artifact_version:
            status["codex_sidecar_version"] = artifact_version
        for key, value in projected_config.items():
            if key == "codex_sidecar_model_provider":
                continue
            normalized_value = str(value or "").strip()
            if normalized_value:
                status[str(key)] = normalized_value
        if self._model_catalog is not None:
            status.update(self._model_catalog.status_fields())
        return status

    def available_models(
        self,
        provider_filter: str | None = None,
        *,
        include_hidden: bool = False,
    ) -> list[dict[str, Any]]:
        if self._model_catalog is None:
            return []
        payload = self._model_catalog.list_models(include_hidden=include_hidden)
        data = payload.get("data")
        if not isinstance(data, list):
            return []
        normalized_filter = str(provider_filter or "").strip().lower()
        items = []
        for item in data:
            if not isinstance(item, dict):
                continue
            model_item = _model_item_from_sidecar(item)
            raw_provider = str(model_item.get("provider_name") or "").strip()
            display_provider = self.display_provider_name(raw_provider) or raw_provider
            if display_provider:
                model_item["provider_name"] = display_provider
                model_item["config_provider_name"] = display_provider
            items.append(model_item)
        if not normalized_filter:
            return items
        return [
            item
            for item in items
            if normalized_filter
            in {
                str(item.get("provider_name") or "").strip().lower(),
                self.sidecar_provider_id_for(str(item.get("provider_name") or "").strip()).lower(),
            }
        ]

    def display_provider_name(self, provider_name: str | None = None) -> str:
        raw_provider = str(provider_name or self._session.model_provider or "").strip()
        projected_config = dict(self._artifact_metadata.get("projected_config") or {})
        agenthub_provider = str(
            projected_config.get("codex_sidecar_agenthub_provider") or ""
        ).strip()
        sidecar_provider = str(projected_config.get("codex_sidecar_model_provider") or "").strip()
        if (
            raw_provider
            and sidecar_provider
            and raw_provider == sidecar_provider
            and agenthub_provider
        ):
            return agenthub_provider
        return raw_provider or agenthub_provider

    def sidecar_provider_id_for(self, provider_name: str | None = None) -> str:
        raw_provider = str(provider_name or "").strip()
        projected_config = dict(self._artifact_metadata.get("projected_config") or {})
        agenthub_provider = str(
            projected_config.get("codex_sidecar_agenthub_provider") or ""
        ).strip()
        sidecar_provider = str(projected_config.get("codex_sidecar_model_provider") or "").strip()
        if (
            raw_provider
            and agenthub_provider
            and raw_provider == agenthub_provider
            and sidecar_provider
        ):
            return sidecar_provider
        return raw_provider
