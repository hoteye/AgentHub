from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from cli.agent_cli.runtime_kernels.codex_sidecar.protocol import JsonObject


@dataclass(slots=True)
class CodexSidecarModelCatalog:
    kernel: Any
    ttl_seconds: float = 60.0
    _models: JsonObject | None = None
    _models_fetched_at: float = 0.0
    _capabilities: JsonObject | None = None
    _capabilities_fetched_at: float = 0.0
    _last_error: str = ""
    _metadata: dict[str, Any] = field(default_factory=dict)

    def list_models(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        include_hidden: bool | None = None,
        force_refresh: bool = False,
    ) -> JsonObject:
        cacheable = cursor is None
        if cacheable and not force_refresh and self._fresh(self._models_fetched_at):
            return dict(self._models or {"data": [], "nextCursor": None})
        try:
            result = self.kernel.list_models(
                cursor=cursor,
                limit=limit,
                include_hidden=include_hidden,
            )
        except Exception as exc:
            self._last_error = str(exc)
            if cacheable and self._models is not None:
                return dict(self._models)
            return {"data": [], "nextCursor": None, "error": self._last_error}
        if cacheable:
            self._models = dict(result)
            self._models_fetched_at = time.monotonic()
        self._last_error = ""
        return dict(result)

    def read_provider_capabilities(self, *, force_refresh: bool = False) -> JsonObject:
        if not force_refresh and self._fresh(self._capabilities_fetched_at):
            return dict(self._capabilities or {})
        try:
            result = self.kernel.read_model_provider_capabilities()
        except Exception as exc:
            self._last_error = str(exc)
            if self._capabilities is not None:
                return dict(self._capabilities)
            return {"error": self._last_error}
        self._capabilities = dict(result)
        self._capabilities_fetched_at = time.monotonic()
        self._last_error = ""
        return dict(result)

    def invalidate(self) -> None:
        self._models = None
        self._models_fetched_at = 0.0
        self._capabilities = None
        self._capabilities_fetched_at = 0.0
        self._last_error = ""

    def status_fields(self) -> dict[str, str]:
        models = self._models or {}
        data = models.get("data")
        model_count = len(data) if isinstance(data, list) else 0
        capabilities = self._capabilities or {}
        return {
            "codex_model_catalog_source": "sidecar" if model_count else "sidecar_unavailable",
            "codex_model_count": str(model_count),
            "codex_provider_capabilities": _compact_capabilities(capabilities),
            "codex_model_catalog_error": self._last_error,
        }

    def _fresh(self, fetched_at: float) -> bool:
        return fetched_at > 0 and (time.monotonic() - fetched_at) < max(0.0, self.ttl_seconds)


def _compact_capabilities(value: JsonObject) -> str:
    if not value or "error" in value:
        return ""
    enabled = [
        key for key in ("namespaceTools", "imageGeneration", "webSearch") if bool(value.get(key))
    ]
    return ",".join(enabled)
